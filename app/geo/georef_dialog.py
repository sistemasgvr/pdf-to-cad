"""
georef_dialog.py — Diálogo "Georreferenciar" (puntos de control PDF ↔ calles reales de LA).

Reemplaza al viejo diálogo multi-pestaña (mapa Leaflet/monumentos/DWG de
referencia/superponer) por un flujo único, adaptado de `auxiliar/pdf_georef.py`:

    Izquierda: el plano YA cargado en el proyecto (PDF + utilidades dibujadas),
               clic = punto en píxeles de escena, con IMÁN a la línea de
               utilidad/centerline más cercana (vértice, segmento, o el cruce
               EXACTO si hay 2 líneas distintas que se cortan cerca del clic).
    Derecha:   mapa de centerlines + parcelas reales de Los Ángeles
               (NavigateLA) sobre mapa base, clic = punto en pies EPSG:2229,
               mismo imán (vértice/segmento/cruce exacto). Buscador de
               dirección/intersección (geocoder Esri + respaldo Nominatim,
               vía urllib — sin dependencias nuevas), corre en 2º plano
               (QThread) para no congelar la ventana mientras descarga.

Ctrl+Z (en cualquiera de los 2 paneles) deshace el último punto pendiente o
el último lote de pares agregado de una.

Con ≥3 pares se ajusta una transformación de similaridad (reusa
`geo.georef.fit`, el mismo núcleo que ya usa el resto de la app) y el botón
"Guardar georreferenciación" fija `self.georef` en la ventana principal y
GUARDA el proyecto de una — no hace falta pasar por "Guardar proyecto" aparte.

Todo en EPSG:2229 (State Plane CA Zona V, ftUS) — el único CRS que tiene
sentido para las calles de NavigateLA, y el mismo que usa el resto del
proyecto (imperial, pies).

Dependencias: matplotlib (ya en requirements.txt), pyproj (reproyección UTM
del geocoder), y opcionalmente contextily (mapa base de fondo — si no está
instalado, el mapa sigue funcionando solo con las centerlines/parcelas).
"""
import json
import math
import os
import urllib.parse
import urllib.request

from PySide6 import QtCore, QtGui, QtWidgets

os.environ.setdefault("QT_API", "pyside6")   # matplotlib debe usar el MISMO binding Qt que el resto de la app
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor as MplCursor

try:
    import contextily as cx
    HAS_CTX = True
except Exception:
    HAS_CTX = False
if HAS_CTX:
    try:
        # cache de tiles en disco: la 1ª descarga de una zona tarda lo normal,
        # pero volver a dibujar el mapa (cada punto agregado, pan/zoom) ya NO
        # vuelve a bajar los tiles de red — la parte más lenta del diálogo.
        _tile_cache_dir = os.path.join(os.path.expanduser("~"), ".pdf_to_cad_tile_cache")
        os.makedirs(_tile_cache_dir, exist_ok=True)
        cx.set_cache_dir(_tile_cache_dir)
    except Exception:
        pass

from geo import georef as georef_mod

TARGET_EPSG = 2229                    # State Plane CA Zona V, ftUS — nativo NavigateLA
DEFAULT_BUFFER_FT = 1300              # ≈ 400 m, radio inicial de descarga de centerlines
SNAP_PX = 10                          # imán del lado PDF, en píxeles de escena
SNAP_FT = 15.0                        # imán del lado mapa, en pies (≈ 4.5 m) — antes 30, jalaba de más
BASEMAP_ZOOM = 18                     # nivel de tile de respaldo si falla el cálculo adaptativo
MAX_BASEMAP_ZOOM = 17                 # tope: el coste de redibujar crece con el CUADRADO del
                                      # tamaño del mosaico; con 18 el mapa se volvía inusable

# Tile providers con URL directa (evita depender de contextily.providers, que a
# veces cae en tiles cacheados 403 del OSM público). Se prueban en orden hasta
# que uno cargue, empezando por el último que funcionó (ver _basemap_provider_i).
# Esri va PRIMERO: CartoDB pasó a exigir clave de API y ya no devuelve el tile,
# sino una imagen con la marca "API KEY REQUIRED" — y como responde HTTP 200,
# add_basemap no falla y el respaldo nunca se activaba: el mapa salía cubierto
# de marcas de agua. Los servicios de Esri siguen siendo abiertos.
_TILE_PROVIDERS = [
    ("Esri World Street", "https://server.arcgisonline.com/ArcGIS/rest/services/"
                           "World_Street_Map/MapServer/tile/{z}/{y}/{x}"),
    ("Esri World Imagery", "https://server.arcgisonline.com/ArcGIS/rest/services/"
                            "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    ("CartoDB Voyager", "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"),
]

ESRI_GEOCODE = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "pdf-to-cad-georef/2.0 (staff-engineering)"


# ─────────────────────────── geocodificación (urllib, sin deps nuevas) ───────────────────────────
def norm_query(q):
    """Normaliza intersecciones ('Chandler y Colfax', 'Chandler at Colfax', …
    → 'Chandler & Colfax') y añade contexto de Los Ángeles si falta."""
    import re
    s = q
    for sep in (" cruce con ", " esquina con ", " con ", " y ", " and ", " at ", " x "):
        s = re.sub(re.escape(sep), " & ", s, flags=re.IGNORECASE)
    low = s.lower()
    if not any(c in low for c in ("los angeles", "los ángeles", ", ca", ", california")):
        s = s + ", Los Angeles, CA"
    return s


def _split_intersection(query):
    """('colfax', 'chandler') si la consulta es una intersección, si no None.
    Se aplica sobre el texto YA normalizado por norm_query (que convierte
    'and'/'y'/'con'/'at' en '&' y añade el contexto de Los Ángeles)."""
    s = norm_query(query)
    for tail in (", Los Angeles, CA", ", Los Angeles", ", CA", ", California"):
        if s.lower().endswith(tail.lower()):
            s = s[: -len(tail)]
    if "&" not in s:
        return None
    parts = [p.strip(" ,") for p in s.split("&")]
    parts = [p for p in parts if p]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def geocode_2229(query):
    """(x_ft, y_ft, etiqueta) en EPSG:2229. Escalera de resolución:

    1) Si la consulta es una INTERSECCIÓN, se resuelve contra la capa de ejes
       de calle de NavigateLA cruzando las dos calles por nombre. Es la misma
       fuente que usa NavigateLA, así que acepta "colfax and chandler" sin
       exigir el sufijo ("COLFAX AVE & CHANDLER BLVD"), que es justo lo que
       fallaba: los geocodificadores genéricos sí necesitan el sufijo.
    2) Si no es intersección (o no se encontró), se usa el geocodificador
       genérico de siempre y se reproyecta a 2229.
    """
    pair = _split_intersection(query)
    if pair:
        try:
            from geo.la_reference import find_intersection_2229
            hit = find_intersection_2229(pair[0], pair[1])
            if hit:
                x, y, label = hit
                return x, y, label
        except Exception:
            pass                      # cae al geocodificador genérico
    lat, lon, matched = geocode(query)
    x, y = georef_mod.lonlat_to_utm(lon, lat, TARGET_EPSG)
    return x, y, matched


def geocode(query):
    """(lat, lon, label) usando Esri World (bueno con intersecciones); si falla,
    Nominatim. Lanza RuntimeError si ninguno encuentra nada."""
    q = norm_query(query)
    try:
        url = ESRI_GEOCODE + "?" + urllib.parse.urlencode(
            {"SingleLine": q, "f": "json", "maxLocations": 1, "outFields": "Match_addr"})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        cands = data.get("candidates", [])
        if cands:
            loc = cands[0]["location"]
            return float(loc["y"]), float(loc["x"]), cands[0].get("address", query)
    except Exception:
        pass
    try:
        url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.load(resp)
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", query)
    except Exception as e:
        raise RuntimeError(f"No se encontró '{query}' ({e}).")
    raise RuntimeError(
        f"No se encontró '{query}'.\n\nFormatos que suelen funcionar:\n"
        f"  • Colfax Ave & Chandler Blvd, Los Angeles, CA\n"
        f"  • 5th St & Spring St, Los Angeles\n"
        f"  • 200 N Spring St, Los Angeles, CA 90012")


# ─────────────────────────── imán a línea (vértice, si no punto sobre segmento) ───────────────────────────
def _closest_on_segment(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return a
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return (ax + t * dx, ay + t * dy)


def snap_to_lines_idx(pt, polylines, max_dist):
    """Como snap_to_lines, pero además devuelve el ÍNDICE de la polilínea
    elegida (o None si ninguna calificó) — para saber CUÁL línea se clicó
    cuando hay varias candidatas (p.ej. emparejar centerlines dibujados)."""
    x, y = pt
    best_v, best_vd, best_vi = None, float("inf"), None
    for idx, pts in enumerate(polylines):
        for (vx, vy) in pts:
            d = math.hypot(vx - x, vy - y)
            if d < best_vd:
                best_vd, best_v, best_vi = d, (vx, vy), idx
    if best_v is not None and best_vd <= max_dist:
        return best_v, best_vi
    best_s, best_sd, best_si = None, float("inf"), None
    for idx, pts in enumerate(polylines):
        for i in range(len(pts) - 1):
            proj = _closest_on_segment((x, y), pts[i], pts[i + 1])
            d = math.hypot(proj[0] - x, proj[1] - y)
            if d < best_sd:
                best_sd, best_s, best_si = d, proj, idx
    if best_s is not None and best_sd <= max_dist:
        return best_s, best_si
    return None, None


def snap_to_lines(pt, polylines, max_dist):
    """polylines: lista de listas de (x,y). Snap al vértice más cercano dentro
    de max_dist; si no hay ninguno, al punto más cercano sobre cualquier
    segmento (también dentro de max_dist). Si nada califica, devuelve pt tal cual."""
    snapped, _idx = snap_to_lines_idx(pt, polylines, max_dist)
    return snapped if snapped is not None else pt


def _seg_intersect(a1, a2, b1, b2):
    """Punto de cruce EXACTO entre el segmento a1-a2 y b1-b2, o None si no se
    cruzan (dentro de una pequeña tolerancia en los extremos, por si el cruce
    real cae justo en el nodo de una de las 2 polilíneas)."""
    x1, y1 = a1; x2, y2 = a2; x3, y3 = b1; x4, y4 = b2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / d
    if -0.02 <= t <= 1.02 and -0.02 <= u <= 1.02:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def snap_to_intersection(pt, polylines, max_dist):
    """Si hay un cruce GEOMÉTRICO real entre 2 polilíneas DISTINTAS cerca de
    pt (p.ej. 2 calles que se cruzan), devuelve (punto_exacto_del_cruce,
    (idx_i, idx_j)) — más preciso que el vértice más cercano, porque el cruce
    real puede no caer justo en ningún vértice digitalizado. (None, None) si
    no hay ningún cruce a menos de max_dist."""
    x, y = pt
    search = max_dist * 3
    best, bd, best_idx = None, float("inf"), None
    n = len(polylines)
    for i in range(n):
        pi = polylines[i]
        for j in range(i + 1, n):
            pj = polylines[j]
            for a in range(len(pi) - 1):
                if min(math.hypot(pi[a][0] - x, pi[a][1] - y),
                       math.hypot(pi[a + 1][0] - x, pi[a + 1][1] - y)) > search:
                    continue
                for b in range(len(pj) - 1):
                    if min(math.hypot(pj[b][0] - x, pj[b][1] - y),
                           math.hypot(pj[b + 1][0] - x, pj[b + 1][1] - y)) > search:
                        continue
                    ip = _seg_intersect(pi[a], pi[a + 1], pj[b], pj[b + 1])
                    if ip is None:
                        continue
                    d = math.hypot(ip[0] - x, ip[1] - y)
                    if d < bd:
                        bd, best, best_idx = d, ip, (i, j)
    if best is not None and bd <= max_dist:
        return best, best_idx
    return None, None


# ─────────────────────────── vista del plano (PDF + utilidades) ───────────────────────────
class _PdfPickView(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float)

    def __init__(self, qimg, pipe_lines=None, cl_lines=None):
        super().__init__(); sc = QtWidgets.QGraphicsScene(self); self.setScene(sc)
        # El PDF va SOLO como pixmap (capa propia, con su propia opacidad —
        # ver set_pdf_opacity); las utilidades/centerlines se dibujan aparte
        # como líneas VECTORIALES (cosmetic pen) encima, así no se pixelan al
        # hacer zoom y la opacidad del PDF no las afecta.
        self._pm = sc.addPixmap(QtGui.QPixmap.fromImage(qimg))
        self._pm.setZValue(0)
        pen_u = QtGui.QPen(QtGui.QColor(120, 200, 255, 220)); pen_u.setCosmetic(True); pen_u.setWidthF(1.6)
        for pts in (pipe_lines or []):
            for a, b in zip(pts, pts[1:]):
                it = sc.addLine(a[0], a[1], b[0], b[1], pen_u); it.setZValue(4)
        pen_cl = QtGui.QPen(QtGui.QColor(255, 60, 220)); pen_cl.setCosmetic(True); pen_cl.setWidthF(2.4)
        pen_cl.setStyle(QtCore.Qt.DashLine)
        for pts in (cl_lines or []):
            for a, b in zip(pts, pts[1:]):
                it = sc.addLine(a[0], a[1], b[0], b[1], pen_cl); it.setZValue(4)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(28, 28, 28))
        self.setToolTip("Clic izquierdo: punto de control (imán a la utilidad/centerline más cercana)\n"
                        "Rueda: zoom · Rueda presionada + arrastrar: desplazar (como en Civil3D)")
        self.setMouseTracking(True)
        self._pan = False; self._pan0 = None
        # Cruz de ejes X/Y en MORADO al 50% de transparencia (antes amarillo).
        pen_h = QtGui.QPen(QtGui.QColor(128, 0, 128, 128)); pen_h.setCosmetic(True); pen_h.setWidthF(2.2)
        self._hline = sc.addLine(0, 0, 0, 0, pen_h); self._vline = sc.addLine(0, 0, 0, 0, pen_h)
        self._hline.setZValue(1000); self._vline.setZValue(1000)
        self._hline.setVisible(False); self._vline.setVisible(False)
        QtCore.QTimer.singleShot(0, lambda: self.fitInView(self._pm, QtCore.Qt.KeepAspectRatio))

    def set_pdf_opacity(self, v):
        self._pm.setOpacity(v)

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8; self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = True; self._pan0 = e.position(); self.setCursor(QtCore.Qt.ClosedHandCursor); return
        if e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint()); self.clicked.emit(sp.x(), sp.y())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        sp = self.mapToScene(e.position().toPoint())
        rect = self.scene().sceneRect()
        self._hline.setLine(rect.left(), sp.y(), rect.right(), sp.y())
        self._vline.setLine(sp.x(), rect.top(), sp.x(), rect.bottom())
        self._hline.setVisible(True); self._vline.setVisible(True)
        if self._pan:
            d = e.position() - self._pan0; self._pan0 = e.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = False; self.setCursor(QtCore.Qt.ArrowCursor); return
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._hline.setVisible(False); self._vline.setVisible(False)
        super().leaveEvent(e)

    def add_mark(self, x, y, color):
        pen = QtGui.QPen(QtGui.QColor(color)); pen.setCosmetic(True)
        return self.scene().addEllipse(x - 6, y - 6, 12, 12, pen, QtGui.QBrush(QtGui.QColor(color)))


# ─────────────────────────── mapa de centerlines (matplotlib, clic + scroll zoom) ───────────────────────────
class _MapCanvas(FigureCanvas):
    clicked = QtCore.Signal(float, float)
    _PAN_REDRAW_MS = 90       # tope de redibujados durante el arrastre

    def __init__(self):
        # tight_layout=True recalculaba la disposición en CADA redibujado (y hay
        # uno por cada movimiento del ratón al desplazar): se sustituye por un
        # margen fijo, que se calcula una sola vez.
        self.fig = Figure(figsize=(4, 4))
        self.fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect("equal", adjustable="datalim")
        self.setMouseTracking(True)
        self._pan = False; self._pan0 = None
        # Limitador de redibujados durante el arrastre (ver mouseMoveEvent)
        self._pan_dirty = False
        self._pan_timer = QtCore.QTimer(self)
        self._pan_timer.timeout.connect(self._pan_flush)
        self.mpl_connect("button_press_event", self._on_click)
        self.mpl_connect("scroll_event", self._on_scroll)
        # Cruz de ejes X/Y siguiendo el ratón — la MISMA ayuda visual que ya
        # tenía el panel del PDF (ver _PdfPickView.mouseMoveEvent). useblit
        # redibuja solo la cruz sobre una copia cacheada del fondo, así no
        # cuesta un redibujado completo del mapa en cada movimiento.
        # Cruz de ejes X/Y en MORADO al 50% de transparencia (antes amarillo),
        # a juego con la cruz del panel del PDF.
        self._cursor = MplCursor(self.ax, useblit=True,
                                 color="#800080", linewidth=1.2, alpha=0.5)

    def _on_click(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        self.clicked.emit(event.xdata, event.ydata)

    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        scale = 0.8 if event.button == "up" else 1.25
        x, y = event.xdata, event.ydata
        xl = self.ax.get_xlim(); yl = self.ax.get_ylim()
        self.ax.set_xlim(x - (x - xl[0]) * scale, x + (xl[1] - x) * scale)
        self.ax.set_ylim(y - (y - yl[0]) * scale, y + (yl[1] - y) * scale)
        self.draw_idle()

    # navegación con botón central IDÉNTICA a la del panel del PDF (rueda =
    # zoom, ver _on_scroll; rueda presionada + arrastrar = mover libremente).
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = True; self._pan0 = e.position(); self.setCursor(QtCore.Qt.ClosedHandCursor); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan and self._pan0 is not None:
            d = e.position() - self._pan0; self._pan0 = e.position()
            xl = self.ax.get_xlim(); yl = self.ax.get_ylim()
            w = self.width() or 1; h = self.height() or 1
            dx = -(d.x() / w) * (xl[1] - xl[0])
            dy = (d.y() / h) * (yl[1] - yl[0])
            self.ax.set_xlim(xl[0] + dx, xl[1] + dx)
            self.ax.set_ylim(yl[0] + dy, yl[1] + dy)
            # LIMITADOR: un redibujado completo del mapa cuesta bastante (el
            # mapa base es la mayor parte). Sin esto se pedía uno por CADA
            # evento de ratón — llegan muchos más de los que se pueden servir,
            # la cola crece y el arrastre se siente pegajoso y con retraso.
            # Se redibuja como mucho cada `_PAN_REDRAW_MS`; al soltar se hace
            # un último redibujado para dejar la vista exacta.
            self._pan_dirty = True
            if not self._pan_timer.isActive():
                self._pan_flush()
                self._pan_timer.start(self._PAN_REDRAW_MS)
            return
        super().mouseMoveEvent(e)

    def _pan_flush(self):
        """Redibuja si hubo movimiento, y ADAPTA el intervalo al coste real del
        redibujado en esta máquina y con estos datos. Si se pidieran más
        redibujados de los que se pueden servir, la cola crecería y el arrastre
        se sentiría cada vez más retrasado; midiendo cuánto tarda y esperando
        algo más que eso, el movimiento sigue al ratón sin acumular retraso."""
        if not self._pan_dirty:
            if not self._pan:
                self._pan_timer.stop()
            return
        self._pan_dirty = False
        import time as _t
        t0 = _t.perf_counter()
        self.draw()                      # síncrono: así se puede medir
        cost_ms = (_t.perf_counter() - t0) * 1000.0
        self._pan_timer.setInterval(
            max(self._PAN_REDRAW_MS, min(400, int(cost_ms * 1.2))))

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = False; self.setCursor(QtCore.Qt.ArrowCursor)
            self._pan_timer.stop()
            self._pan_dirty = False
            self.draw_idle()          # vista final exacta
            return
        super().mouseReleaseEvent(e)

    def clear(self):
        self.ax.cla(); self.ax.set_aspect("equal", adjustable="datalim")

    def redraw(self):
        self.draw_idle()


# ─────────────────────────── búsqueda en 2º plano (no congela la UI) ───────────────────────────
class _FetchWorker(QtCore.QObject):
    """Geocodifica + descarga calles/parcelas en un QThread aparte — antes esto
    corría en el hilo de UI (con processEvents()) y el diálogo se sentía
    trabado mientras tanto; ahora la ventana sigue respondiendo."""
    done = QtCore.Signal(object)      # (lines, parcels, matched, arc_centers)
    failed = QtCore.Signal(str)

    def __init__(self, buffer_ft, addr=None, center=None):
        """addr: dirección a geocodificar. center: (X,Y) en pies 2229 ya
        conocido (p.ej. al reabrir un plano ya georreferenciado) — se salta
        el geocode y descarga directo alrededor de ese punto."""
        super().__init__()
        self.addr = addr; self.buffer_ft = buffer_ft; self.center = center

    def run(self):
        try:
            if self.center is not None:
                cx_ft, cy_ft = self.center; matched = "zona ya georreferenciada"
            else:
                cx_ft, cy_ft, matched = geocode_2229(self.addr)
            from geo.la_reference import (fetch_streets_2229, fetch_parcels_2229,
                                          arc_centers)
            # Las dos descargas son independientes y de red: en PARALELO tardan
            # lo que la más lenta, no la suma (antes eran secuenciales).
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(max_workers=2) as ex:
                f_lines = ex.submit(fetch_streets_2229, cx_ft, cy_ft, self.buffer_ft)
                f_parc = ex.submit(fetch_parcels_2229, cx_ft, cy_ft, self.buffer_ft)
                lines = f_lines.result()
                parcels = f_parc.result()
            # Centros de los redondeos de las parcelas: puntos magnéticos muy
            # precisos para colocar puntos de control. Se calculan aquí (hilo
            # aparte) para no bloquear la UI al dibujar.
            try:
                centers = arc_centers(parcels)
            except Exception:
                centers = []
            self.done.emit((lines, parcels, matched, centers))
        except Exception as e:
            self.failed.emit(str(e))


class GeorefDialog(QtWidgets.QDialog):
    def __init__(self, parent, plan_qimage, pipes, ref_centerlines=None, init_georef=None):
        super().__init__(parent)
        self._main = parent
        self.setWindowTitle("Georreferenciar plano")
        # Redimensionable/maximizable (QDialog no trae el botón de maximizar
        # por defecto) y con tamaño inicial ajustado al monitor, para que no
        # quede más grande que la pantalla en equipos con monitores chicos.
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMaximizeButtonHint
                            | QtCore.Qt.WindowMinimizeButtonHint)
        self.setSizeGripEnabled(True)
        # Pantalla del PADRE (no la primaria): en equipos con el plano abierto en
        # un monitor chico, self.screen() antes de mostrarse podía devolver el
        # primario y el diálogo salía más ancho que la pantalla real.
        scr = (parent.screen() if parent else None) or self.screen() \
            or QtWidgets.QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else QtCore.QRect(0, 0, 1400, 860)
        # Se abre MAXIMIZADA (pedido del usuario): ocupa toda la pantalla
        # disponible del monitor donde vive la ventana padre. `showMaximized`
        # se llama en showEvent para que el WM la reciba una vez ya visible.
        # Se guarda un tamaño "razonable" como fallback por si el usuario luego
        # sale del maximizado.
        w = min(1360, max(720, avail.width() - 80))
        h = min(860, max(540, avail.height() - 120))
        self.resize(w, h)
        self.move(avail.x() + max(0, (avail.width() - w) // 2),
                  avail.y() + max(0, (avail.height() - h) // 2))
        self._init_w = avail.width()
        self._start_maximized = True
        self.result_georef = None
        self._pipe_lines = [p.get("pts", []) for p in (pipes or []) if len(p.get("pts", [])) >= 2]
        # Centerlines DIBUJADOS a mano (distintos de las utilidades): se muestran
        # en el plano como referencia y el imán de puntos de control se pega a
        # ellos igual que a las utilidades.
        self._ref_cl_lines = [c.get("pts", []) for c in (ref_centerlines or []) if len(c.get("pts", [])) >= 2]
        self.centerlines = []             # [[ (x,y) en ft 2229, ... ], ...] — calles REALES (NavigateLA)
        self.parcels = []                 # [[ (x,y) en ft 2229, ... ], ...] — parcelas REALES (NavigateLA)
        self.arc_centers = []             # [(x,y,radio)] centros de esquinas redondeadas (imán)
        self.pairs = []                   # [{"px":(x,y), "world":(X,Y), "label":str, "mark":item}]
        self._pending_px = None; self._pending_mark = None
        self._undo_stack = []             # lotes de pares agregados de una (1 clic = 1; centerline = N) para Ctrl+Z
        self._map_markers = []            # artistas matplotlib de los pares (se redibujan sin rehacer el mapa base)
        self._basemap_provider_i = 0      # último proveedor de tiles que funcionó — se prueba primero la próxima vez
        self._fetch_thread = None; self._fetch_worker = None

        root = QtWidgets.QVBoxLayout(self)
        warn = QtWidgets.QLabel(
            "⚠ El calce contra centerlines de LA da coordenadas de trazado/anteproyecto — el dato "
            "topográfico real proviene del levantamiento/Excel.")
        warn.setWordWrap(True); warn.setStyleSheet("color:#e0c060;"); root.addWidget(warn)

        self.lbl_prev = QtWidgets.QLabel(""); self.lbl_prev.setWordWrap(True)
        if init_georef is not None and init_georef.active():
            rms = f", RMS {init_georef.rms:.2f} ft" if init_georef.rms is not None else ""
            self.lbl_prev.setText(f"✓ Este plano YA está georreferenciado (EPSG:{init_georef.epsg}{rms}). "
                                  "Puedes recalcular con nuevos puntos o cerrar sin cambios.")
            self.lbl_prev.setStyleSheet("color:#5fd35f;font-weight:bold;")
            root.addWidget(self.lbl_prev)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        pdf_w = QtWidgets.QWidget(); pv = QtWidgets.QVBoxLayout(pdf_w); pv.setContentsMargins(0, 0, 0, 0)
        oprow = QtWidgets.QHBoxLayout()
        oprow.addWidget(QtWidgets.QLabel("Opacidad PDF:"))
        self.sl_pdf_op = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_pdf_op.setRange(10, 100); self.sl_pdf_op.setValue(100)
        self.sl_pdf_op.valueChanged.connect(lambda v: self.pdf.set_pdf_opacity(v / 100))
        oprow.addWidget(self.sl_pdf_op, 1)
        pv.addLayout(oprow)
        self.pdf = _PdfPickView(plan_qimage, self._pipe_lines, self._ref_cl_lines)
        self.pdf.clicked.connect(self._on_pdf_click)
        pv.addWidget(self.pdf, 1)
        split.addWidget(pdf_w)

        map_w = QtWidgets.QWidget(); mv = QtWidgets.QVBoxLayout(map_w); mv.setContentsMargins(0, 0, 0, 0)
        srow = QtWidgets.QHBoxLayout()
        self.ed_addr = QtWidgets.QLineEdit()
        self.ed_addr.setPlaceholderText("Dirección o intersección… ej: Colfax Ave & Chandler Blvd")
        self.ed_addr.returnPressed.connect(self._on_fetch)
        srow.addWidget(self.ed_addr, 1)
        srow.addWidget(QtWidgets.QLabel("Radio (ft):"))
        self.sp_buffer = QtWidgets.QDoubleSpinBox()
        self.sp_buffer.setRange(300, 10000); self.sp_buffer.setValue(DEFAULT_BUFFER_FT); self.sp_buffer.setSingleStep(150)
        srow.addWidget(self.sp_buffer)
        self.b_fetch = QtWidgets.QPushButton("Buscar y descargar"); self.b_fetch.clicked.connect(self._on_fetch)
        srow.addWidget(self.b_fetch)
        mv.addLayout(srow)
        mv.addWidget(QtWidgets.QLabel("Calles de LA (NavigateLA)  —  clic: punto de control (imán a la intersección)  |  rueda: zoom"))
        # Contenedor para poder poner el loader ENCIMA del mapa (overlay).
        map_holder = QtWidgets.QWidget(); mh = QtWidgets.QGridLayout(map_holder)
        mh.setContentsMargins(0, 0, 0, 0); mh.setSpacing(0)
        self.canvas_map = _MapCanvas(); self.canvas_map.clicked.connect(self._on_map_click)
        mh.addWidget(self.canvas_map, 0, 0)
        # Loader: panel semitransparente con un "spinner" de texto animado y
        # un mensaje. Se muestra durante la búsqueda de dirección / descarga.
        self.loader = QtWidgets.QFrame(map_holder)
        self.loader.setStyleSheet(
            "QFrame{background:rgba(20,20,20,180);border:1px solid #4a4a4a;border-radius:8px;}"
            "QLabel{color:#f0f0f0;background:transparent;border:none;font-size:13px;}")
        ll = QtWidgets.QVBoxLayout(self.loader); ll.setContentsMargins(18, 14, 18, 14); ll.setSpacing(8)
        self.loader_spin = QtWidgets.QLabel("⣾"); self.loader_spin.setAlignment(QtCore.Qt.AlignCenter)
        self.loader_spin.setStyleSheet("font-size:28px;color:#7ecbff;background:transparent;border:none;")
        self.loader_msg = QtWidgets.QLabel("Cargando…"); self.loader_msg.setAlignment(QtCore.Qt.AlignCenter)
        ll.addWidget(self.loader_spin); ll.addWidget(self.loader_msg)
        mh.addWidget(self.loader, 0, 0, QtCore.Qt.AlignCenter)
        self.loader.hide()
        self._loader_frames = ["⣾", "⣷", "⣯", "⣟", "⡿", "⢿", "⣻", "⣽"]
        self._loader_i = 0
        self._loader_timer = QtCore.QTimer(self)
        self._loader_timer.timeout.connect(self._loader_tick)
        mv.addWidget(map_holder, 1)
        split.addWidget(map_w)

        # Que ninguno de los dos paneles imponga un ancho mínimo grande: así el
        # diálogo respeta el tamaño acotado a la pantalla y no se ensancha de más.
        self.pdf.setMinimumSize(220, 220)
        self.canvas_map.setMinimumSize(220, 220)
        half = max(240, self._init_w // 2)
        split.setSizes([half, half]); root.addWidget(split, 1)

        self.hint = QtWidgets.QLabel("1) Busca y descarga las calles de la zona · 2) clic en el plano (izquierda) "
                                     "· 3) clic en la calle correspondiente (derecha). Mínimo 3 pares — puedes "
                                     "marcar puntos A LO LARGO de toda la calle, no solo en las esquinas: "
                                     "más puntos bien repartidos mejoran el ajuste (RMSE).")
        self.hint.setStyleSheet("color:#9cf;"); root.addWidget(self.hint)

        rmse_tip = ("RMSE (Root Mean Square Error / error cuadrático medio): el error PROMEDIO, en pies, "
                   "entre cada punto de control y donde el ajuste calculado lo ubica.\n\n"
                   "No es el error de un punto — es el error de TODOS a la vez: si un punto quedó mal "
                   "clickeado, el RMSE sube aunque los demás estén perfectos. Mientras más bajo, mejor "
                   "(verde <3 ft, amarillo <8 ft, rojo ≥8 ft).")
        crow = QtWidgets.QHBoxLayout()
        self.b_fit = QtWidgets.QPushButton("Ajustar + RMSE"); self.b_fit.clicked.connect(self._compute)
        self.b_fit.setToolTip("Calcula la transformación (rotación + escala uniforme + traslación) que mejor "
                              "hace coincidir todos los pares plano↔calle real, y muestra el RMSE. No deforma "
                              "el plano: solo lo gira y escala parejo.\n\n" + rmse_tip)
        crow.addWidget(self.b_fit)
        self.lbl_rms = QtWidgets.QLabel("RMSE: —"); self.lbl_rms.setToolTip(rmse_tip); crow.addWidget(self.lbl_rms, 1)
        b_del = QtWidgets.QPushButton("Eliminar sel."); b_del.setProperty("danger", True)
        b_del.clicked.connect(self._del_pair); crow.addWidget(b_del)
        b_clear = QtWidgets.QPushButton("Limpiar todos"); b_clear.setProperty("danger", True)
        b_clear.clicked.connect(self._clear_pairs); crow.addWidget(b_clear)
        root.addLayout(crow)

        self.lst = QtWidgets.QListWidget(); self.lst.setMaximumHeight(140); root.addWidget(self.lst)

        # Código de sistema de coordenadas (Huso) que el plugin aplicará al dibujo
        # en Civil 3D al IMPORTAR la red. Es el código CS-MAP nativo (ej. "CA83VF"
        # para NAD83 California zona V en pies = EPSG:2229). Se copia del diálogo
        # nativo "Huso" de Civil 3D si no se sabe de memoria. Se valida allí.
        csrow = QtWidgets.QHBoxLayout()
        csrow.addWidget(QtWidgets.QLabel("Sistema de coordenadas (Huso) — código:"))
        self.ed_cs_code = QtWidgets.QLineEdit()
        self.ed_cs_code.setPlaceholderText("ej: CA83VF  (código CS-MAP; vacío = no setear Huso)")
        self.ed_cs_code.setToolTip(
            "Código nativo CS-MAP del sistema de coordenadas que quedará seteado en el\n"
            "dibujo de Civil 3D al importar la red. Debe corresponder al EPSG con que\n"
            "georreferenciaste (para EPSG:2229 → 'CA83VF'). Cópialo del diálogo nativo\n"
            "de Civil 3D (Configuración de dibujo → Unidades y huso) si no lo sabes.\n"
            "Vacío = el dibujo no se setea (lo puedes poner luego a mano).")
        if init_georef is not None and getattr(init_georef, "cs_code", ""):
            self.ed_cs_code.setText(init_georef.cs_code)
        csrow.addWidget(self.ed_cs_code, 1)
        root.addLayout(csrow)

        bb = QtWidgets.QHBoxLayout()
        self.b_save = QtWidgets.QPushButton("💾 Guardar georreferenciación")
        # Habilitado de entrada si el plano YA está georreferenciado, para poder
        # guardar aunque solo se cambie el código de Huso (sin recalcular).
        self.b_save.setEnabled(bool(init_georef is not None and init_georef.active()))
        self.b_save.clicked.connect(self._save)
        bb.addStretch(1); bb.addWidget(self.b_save)
        b_cancel = QtWidgets.QPushButton("Cerrar sin guardar"); b_cancel.clicked.connect(self.reject)
        bb.addWidget(b_cancel)
        root.addLayout(bb)

        # precargar pares de una georreferencia previa (si el punto trae "world")
        # y descargar sola la zona real (calles/parcelas) alrededor de esos
        # puntos, para que el mapa NO quede vacío al reabrir — se puede editar
        # (agregar/quitar puntos, recalcular) sin tener que rebuscar la dirección.
        if init_georef is not None and init_georef.points:
            world_pts = []
            for p in init_georef.points:
                px = tuple(p.get("px", ())); wd = tuple(p.get("world", ())) if p.get("world") else None
                if len(px) == 2 and wd and len(wd) == 2:
                    m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
                    self.pairs.append({"px": px, "world": wd, "label": p.get("label", ""), "mark": m})
                    world_pts.append(wd)
            self._refresh_list()
            if world_pts:
                cx_ft = sum(w[0] for w in world_pts) / len(world_pts)
                cy_ft = sum(w[1] for w in world_pts) / len(world_pts)
                xs = [w[0] for w in world_pts]; ys = [w[1] for w in world_pts]
                spread = max(max(xs) - min(xs), max(ys) - min(ys))
                buffer_ft = min(self.sp_buffer.maximum(), max(DEFAULT_BUFFER_FT, spread * 0.75 + 300))
                self.sp_buffer.setValue(buffer_ft)
                self._start_fetch(_FetchWorker(buffer_ft, center=(cx_ft, cy_ft)),
                                  "Cargando la zona de la georreferenciación existente…")

        # Ctrl+Z deshace el último punto/lote agregado — funciona en todo el
        # diálogo (plano y mapa comparten la misma lista de pares).
        undo_sc = QtGui.QShortcut(QtGui.QKeySequence.Undo, self)
        undo_sc.activated.connect(self._undo)

        # Bandera de "cambios sin guardar" (para confirmar al cerrar con la X).
        # Se pone en True al agregar/quitar puntos o editar el código de Huso, y
        # vuelve a False al guardar. Se inicializa AQUÍ (al final) para que la
        # precarga de pares/estado de arriba no la marque como cambios.
        self._dialog_dirty = False
        self.ed_cs_code.textChanged.connect(lambda *_: setattr(self, "_dialog_dirty", True))

    def showEvent(self, e):
        super().showEvent(e)
        # Maximizar tras el primer show: en Qt hay que llamarlo cuando el WM ya
        # tiene la ventana registrada; hacerlo en __init__ no siempre pega. La
        # bandera `_start_maximized` se apaga tras la primera vez para que si el
        # usuario sale del maximizado y reabre el dialogo, se respete su tamaño.
        if getattr(self, "_start_maximized", False):
            self._start_maximized = False
            self.showMaximized()

    def keyPressEvent(self, e):
        # La tecla Escape NO debe cerrar la ventana (evita perder el trabajo por
        # un toque accidental). El resto de teclas sigue igual.
        if e.key() == QtCore.Qt.Key_Escape:
            e.ignore(); return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        # Cerrar con la X teniendo cambios sin guardar → confirmar. (El botón
        # "Cerrar sin guardar" usa reject() y NO pasa por aquí, así que es una
        # salida explícita sin preguntar; Guardar usa accept(), tampoco pregunta.)
        if getattr(self, "_dialog_dirty", False):
            r = QtWidgets.QMessageBox.question(
                self, "Cerrar sin guardar",
                "Hiciste cambios en la georreferenciación que no se han guardado.\n\n"
                "¿Cerrar de todas formas y descartarlos?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if r != QtWidgets.QMessageBox.Yes:
                e.ignore(); return
        # evita "QThread: Destroyed while thread is still running" si se
        # cierra el diálogo justo mientras una búsqueda está en curso.
        if self._fetch_thread is not None:
            self._fetch_thread.quit(); self._fetch_thread.wait(2000)
        super().closeEvent(e)

    # ── acciones ──
    def _on_fetch(self):
        addr = self.ed_addr.text().strip()
        if not addr:
            QtWidgets.QMessageBox.information(self, "Falta dirección", "Escribe una dirección o intersección."); return
        self._start_fetch(_FetchWorker(self.sp_buffer.value(), addr=addr),
                          "Buscando dirección y descargando calles/parcelas…")

    def _loader_tick(self):
        self._loader_i = (self._loader_i + 1) % len(self._loader_frames)
        self.loader_spin.setText(self._loader_frames[self._loader_i])

    def _show_loader(self, msg):
        self.loader_msg.setText(msg)
        self.loader.adjustSize(); self.loader.show(); self.loader.raise_()
        self._loader_i = 0
        self._loader_timer.start(90)

    def _hide_loader(self):
        self._loader_timer.stop()
        self.loader.hide()

    def _start_fetch(self, worker, hint_text):
        if self._fetch_thread is not None:
            return                       # ya hay una búsqueda en curso
        self.b_fetch.setEnabled(False)
        self.hint.setText(hint_text)
        self._show_loader(hint_text)
        self._fetch_thread = QtCore.QThread(self)
        self._fetch_worker = worker
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.done.connect(self._on_fetch_done)
        self._fetch_worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker.done.connect(self._fetch_thread.quit)
        self._fetch_worker.failed.connect(self._fetch_thread.quit)
        self._fetch_thread.finished.connect(self._fetch_cleanup)
        self._fetch_thread.start()

    def _fetch_cleanup(self):
        if self._fetch_worker is not None:
            self._fetch_worker.deleteLater()
        self._fetch_thread = None; self._fetch_worker = None
        self.b_fetch.setEnabled(True)
        self._hide_loader()

    def _on_fetch_done(self, result):
        lines, parcels, matched, centers = result
        if not lines:
            self.hint.setText("No se encontraron calles en esa zona. Prueba un radio mayor.")
            return
        self.centerlines = lines; self.parcels = parcels
        self.arc_centers = centers or []
        self.hint.setText(f"{len(lines)} tramos, {len(parcels)} parcelas, {len(self.arc_centers)} esquinas redondeadas — "
                          f"{matched}. Marca puntos de control — clic cerca de un cruce imanta al cruce exacto")
        self._draw_map_base()

    def _on_fetch_failed(self, msg):
        QtWidgets.QMessageBox.critical(self, "Error", msg)

    def _on_pdf_click(self, x, y):
        all_plan_lines = self._pipe_lines + self._ref_cl_lines
        ip, _idx = snap_to_intersection((x, y), all_plan_lines, SNAP_PX)
        sx, sy = ip if ip is not None else snap_to_lines((x, y), all_plan_lines, SNAP_PX)
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        self._pending_px = (sx, sy)
        self._pending_mark = self.pdf.add_mark(sx, sy, "#ff9a28")
        self.hint.setText("Punto del plano fijado. Ahora clic en la calle correspondiente (derecha).")

    def _snap_arc_center(self, pt, max_dist=SNAP_FT):
        """(x, y) del centro de radio más cercano dentro de `max_dist`, o None.
        Son las esquinas redondeadas de las parcelas: su centro es un punto
        geométrico exacto, ideal como punto de control."""
        best = None; bd = max_dist * max_dist
        for (cx, cy, _r) in getattr(self, "arc_centers", None) or []:
            d2 = (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2
            if d2 < bd:
                bd = d2; best = (cx, cy)
        return best

    def _on_map_click(self, x, y):
        if self._pending_px is None:
            self.hint.setText("Primero clic en el plano (izquierda)."); return
        if not self.centerlines:
            self.hint.setText("Primero descarga las calles de la zona."); return
        # Prioridad del imán, de más preciso a menos:
        #   1) CENTRO del radio de una esquina redondeada de parcela — es un
        #      punto geométrico exacto (no un vértice aproximado del arco), así
        #      que da el mejor punto de control cuando lo hay cerca.
        #   2) cruce exacto de dos ejes de calle
        #   3) punto más cercano sobre un eje de calle
        ac = self._snap_arc_center((x, y))
        if ac is not None:
            sx, sy = ac
        else:
            ip, _idx = snap_to_intersection((x, y), self.centerlines, SNAP_FT)
            sx, sy = ip if ip is not None else snap_to_lines((x, y), self.centerlines, SNAP_FT)
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        m = self.pdf.add_mark(self._pending_px[0], self._pending_px[1], "#5fd35f")
        pair = {"px": self._pending_px, "world": (sx, sy), "label": "", "mark": m}
        self.pairs.append(pair); self._undo_stack.append([pair])
        self._pending_px = None; self._pending_mark = None
        self._dialog_dirty = True
        self._refresh_list(); self._draw_map_markers()
        self.hint.setText(f"Punto {len(self.pairs)} agregado. Repite (mínimo 3) y pulsa «Ajustar».")

    def _del_pair(self):
        r = self.lst.currentRow()
        if r < 0 and self.pairs:
            r = len(self.pairs) - 1
        if 0 <= r < len(self.pairs):
            p = self.pairs.pop(r)
            if p.get("mark") is not None:
                self.pdf.scene().removeItem(p["mark"])
            self._dialog_dirty = True
            self._refresh_list(); self._draw_map_markers()
            self.b_save.setEnabled(False); self.lbl_rms.setText("RMSE: —")

    def _clear_pairs(self):
        for p in self.pairs:
            if p.get("mark") is not None:
                self.pdf.scene().removeItem(p["mark"])
        self.pairs.clear(); self._pending_px = None; self._undo_stack.clear()
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark); self._pending_mark = None
        self._dialog_dirty = True
        self._refresh_list(); self._draw_map_markers()
        self.b_save.setEnabled(False); self.lbl_rms.setText("RMSE: —")

    def _undo(self):
        """Ctrl+Z: cancela el punto pendiente (si hay uno a medias), o si no,
        deshace el último par agregado."""
        if self._pending_px is not None:
            if self._pending_mark:
                self.pdf.scene().removeItem(self._pending_mark)
            self._pending_px = None; self._pending_mark = None
            self.hint.setText("Punto pendiente cancelado (Ctrl+Z)."); return
        while self._undo_stack:
            batch = self._undo_stack.pop()
            removed = False
            for p in batch:
                if p in self.pairs:
                    self.pairs.remove(p)
                    if p.get("mark") is not None:
                        self.pdf.scene().removeItem(p["mark"])
                    removed = True
            if removed:
                break
        self._dialog_dirty = True
        self._refresh_list(); self._draw_map_markers()
        self.b_save.setEnabled(False); self.lbl_rms.setText("RMSE: —")
        self.hint.setText("Último punto/lote deshecho (Ctrl+Z).")

    def _compute(self):
        if len(self.pairs) < 3:
            QtWidgets.QMessageBox.information(self, "Faltan puntos", "Se necesitan al menos 3 puntos de control."); return
        px = [p["px"] for p in self.pairs]; world = [p["world"] for p in self.pairs]
        try:
            # Similaridad (rotación + escala uniforme + traslación): no deforma el
            # plano y su RMSE es real incluso con 3 puntos (ver geo.georef.fit).
            matrix, rms, ttype = georef_mod.fit(px, world, kind="similarity")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ajuste", f"No se pudo ajustar la transformación.\n\n{e}"); return
        det = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
        if det > 0:
            self.lbl_rms.setText("⚠ Ajuste ESPEJADO"); self.lbl_rms.setStyleSheet("color:#e06060;font-weight:bold;")
            QtWidgets.QMessageBox.warning(self, "Ajuste espejado",
                "El ajuste salió espejado: el plano se guardaría volteado.\n\n"
                "Causa típica: los puntos de control están casi en línea recta. Usa 3–4 puntos que "
                "formen un triángulo amplio (en calles distintas o a ambos lados) y recalcula.")
            self.b_save.setEnabled(False); return
        self._fit_result = (matrix, rms, ttype)
        color = "#5fd35f" if rms < 3 else ("#e0c060" if rms < 8 else "#e06060")
        self.lbl_rms.setText(f"RMSE: {rms:.2f} ft  ({ttype}, {len(px)} pts)")
        self.lbl_rms.setStyleSheet(f"color:{color};font-weight:bold;")
        self.hint.setText(f"✓ Ajuste OK (RMSE {rms:.2f} ft). Pulsa «Guardar georreferenciación».")
        self.b_save.setEnabled(True)

    def _save(self):
        cs_code = self.ed_cs_code.text().strip()
        if not getattr(self, "_fit_result", None):
            # Sin ajuste nuevo: si el plano YA está georreferenciado, permitir
            # guardar igual (p.ej. el usuario solo cambió el código de Huso) —
            # se reusa la transformación existente y solo se actualiza cs_code.
            g = getattr(self._main, "georef", None)
            if g is not None and g.active():
                g.cs_code = cs_code
                self.result_georef = g
                self._main._dirty = True
                self._main._update_geo_status()
                try:
                    self._main.save_project()
                    self._dialog_dirty = False
                    self.accept()
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error al guardar", str(e))
                return
            QtWidgets.QMessageBox.information(self, "Falta ajustar",
                "Primero pulsa «Ajustar + RMSE» para calcular la georreferenciación.")
            return
        matrix, rms, ttype = self._fit_result
        pts = [{"px": list(p["px"]), "world": list(p["world"]), "label": p.get("label", "")}
               for p in self.pairs]
        self.result_georef = georef_mod.Georef(matrix=matrix, epsg=TARGET_EPSG, kind=ttype,
                                               rms=rms, points=pts, cs_code=cs_code)
        self._main.georef = self.result_georef; self._main._dirty = True
        self._main._update_geo_status(); self._main._redraw()
        try:
            self._main.save_project()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error al guardar",
                f"La georreferenciación se aplicó, pero no se pudo guardar el proyecto.\n\n{e}")
            return
        saved_to = self._main.project_path
        if not saved_to:
            # No había project_path y el usuario canceló «Guardar como…» —
            # se deja el resultado ya aplicado en memoria, pero el diálogo
            # abierto para reintentar «Guardar» cuando quiera.
            self.hint.setText("Georreferenciación calculada, pero falta guardarla en disco "
                              "(cancelaste «Guardar como…»). Pulsa «Guardar georreferenciación» de nuevo.")
            return
        QtWidgets.QMessageBox.information(self, "Georreferenciación guardada",
            f"✓ Guardado en el proyecto:\n{saved_to}\n\nEPSG: {TARGET_EPSG}\nRMSE: {rms:.2f} ft")
        self._dialog_dirty = False
        self.accept()

    # ── dibujado ──
    def _pick_basemap_zoom(self, c, width_ft):
        """Nivel de tile en función del ancho REAL de la zona y del tamaño del
        panel. `width_ft` se pasa explícitamente: no se puede leer de
        ax.get_xlim() porque, con aspecto igual y adjustable='datalim',
        matplotlib reajusta los límites por su cuenta y devolvería otro ancho.

        Se acota a MAX_BASEMAP_ZOOM porque el coste de redibujar crece con el
        CUADRADO del tamaño de la imagen, y ahí está el grueso del tiempo:
        medido en este mapa, zoom 18 ≈ 2570 px ≈ 350 ms por redibujado, zoom 17
        ≈ 1290 px ≈ 160 ms, zoom 16 ≈ 640 px ≈ 80 ms. Para un panel de ~950 px
        el 18 es resolución desperdiciada.
        """
        try:
            width_px = max(300, c.width())
            if width_ft <= 0:
                return MAX_BASEMAP_ZOOM
            # ftUS → m y resolución de Web Mercator a la latitud de LA (~34°).
            # Factor 1.5: algo de margen para acercarse sin que se vea borroso
            # (el mapa base no se recompone al hacer zoom).
            width_m = width_ft * 0.3048006096
            need_m_per_px = width_m / (width_px * 1.5)
            z = math.log2(156543.03392 * math.cos(math.radians(34.17)) / need_m_per_px)
            return max(14, min(MAX_BASEMAP_ZOOM, int(round(z))))
        except Exception:
            return MAX_BASEMAP_ZOOM

    def _draw_map_base(self):
        """Redibuja calles + parcelas + mapa base — SOLO cuando llegan datos
        nuevos (tras «Buscar y descargar»). Antes esto se repetía en cada
        clic (agregar/borrar un par), rehaciendo el mapa base entero cada vez
        — la causa principal de la lentitud al marcar puntos."""
        c = self.canvas_map; c.clear(); self._map_markers = []
        if not self.centerlines:
            c.redraw(); return
        xs, ys = [], []
        # RENDIMIENTO: una sola LineCollection por capa en vez de un ax.plot()
        # por polilínea. Con un radio de varias cuadras eran ~230 artistas
        # (≈200 parcelas + ~30 calles) que matplotlib volvía a dibujar ENTEROS
        # en cada desplazamiento y cada zoom — por eso el mapa se sentía
        # inusable. Con LineCollection son 2 artistas y el redibujado es
        # inmediato. Se conservan las tres capas (mapa base, ejes de calle y
        # parcelas), solo cambia CÓMO se dibujan.
        from matplotlib.collections import LineCollection
        if self.parcels:
            segs_p = [[(p[0], p[1]) for p in pts] for pts in self.parcels if len(pts) >= 2]
            if segs_p:
                c.ax.add_collection(LineCollection(
                    segs_p, colors="#999", linewidths=0.6, alpha=0.65, zorder=2))
        segs_c = []
        for pts in self.centerlines:
            if len(pts) < 2:
                continue
            seg = [(p[0], p[1]) for p in pts]
            segs_c.append(seg)
            xs += [p[0] for p in seg]; ys += [p[1] for p in seg]
        if segs_c:
            c.ax.add_collection(LineCollection(
                segs_c, colors="#2a5", linewidths=1.3, zorder=3))
        # Puntos MEDIOS de cada esquina redondeada de las parcelas (sobre la
        # curva misma, no el centro del círculo). Sirven como imán preciso al
        # marcar puntos de control. Un solo scatter para todos (rendimiento).
        # Marcador relleno con borde blanco: destaca sobre el mapa base sin
        # depender del tono de fondo.
        if getattr(self, "arc_centers", None):
            c.ax.scatter([a[0] for a in self.arc_centers],
                         [a[1] for a in self.arc_centers],
                         s=32, facecolors="#3ecf5c", edgecolors="#ffffff",
                         linewidths=1.0, zorder=4)
        if not xs:
            c.redraw(); return
        pad = 100
        c.ax.set_xlim(min(xs) - pad, max(xs) + pad)
        c.ax.set_ylim(min(ys) - pad, max(ys) + pad)
        if HAS_CTX:
            # Zoom de tile ADAPTADO al tamaño real del panel. Antes era fijo en
            # 18, que para un radio de varias cuadras compone un mosaico de
            # ~2000x2000 px; matplotlib tiene que reescalar esa imagen entera en
            # CADA desplazamiento y zoom, y medido cuesta ~450 ms por
            # redibujado (con 1024 son ~160 ms y con 512 ~85 ms) — esa era la
            # causa principal de que el mapa se sintiera lento, muy por encima
            # del coste de las calles y parcelas.
            # Se elige el nivel que da algo más de resolución que píxeles tiene
            # el panel: se ve igual de nítido y se redibuja mucho más rápido.
            zoom = self._pick_basemap_zoom(c, (max(xs) - min(xs)) + 2 * pad)
            n = len(_TILE_PROVIDERS)
            order = [(k + self._basemap_provider_i) % n for k in range(n)]
            for k in order:
                _name, _url = _TILE_PROVIDERS[k]
                try:
                    cx.add_basemap(c.ax, crs=f"EPSG:{TARGET_EPSG}", source=_url,
                                   zoom=zoom, attribution=f"© {_name}", attribution_size=6,
                                   zorder=0, interpolation="nearest")
                    self._basemap_provider_i = k
                    break
                except Exception:
                    continue
        c.ax.set_xticks([]); c.ax.set_yticks([])
        self._draw_map_markers()

    def _draw_map_markers(self):
        """Solo agrega/quita los marcadores de pares — NO toca el mapa base
        (calles/parcelas/basemap), así agregar o quitar un punto es instantáneo."""
        c = self.canvas_map
        for art in self._map_markers:
            try:
                art.remove()
            except Exception:
                pass
        self._map_markers = []
        for i, p in enumerate(self.pairs, 1):
            X, Y = p["world"]
            ln, = c.ax.plot(X, Y, "o", color="red", markersize=8, markeredgecolor="white", zorder=5)
            an = c.ax.annotate(str(i), (X, Y), color="red", xytext=(6, 6),
                               textcoords="offset points", fontweight="bold", zorder=6)
            self._map_markers.append(ln); self._map_markers.append(an)
        c.redraw()

    def _refresh_list(self):
        self.lst.clear()
        for i, p in enumerate(self.pairs, 1):
            x, y = p["px"]; X, Y = p["world"]
            tag = f"  [{p['label']}]" if p.get("label") else ""
            self.lst.addItem(QtWidgets.QListWidgetItem(
                f"{i}   plano({x:.0f},{y:.0f})  →  calle({X:.2f},{Y:.2f}) ft{tag}"))
