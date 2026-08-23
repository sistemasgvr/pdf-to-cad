"""
georef_dialog.py — Diálogo "Georreferenciar" (puntos de control PDF ↔ calles reales de LA).

Reemplaza al viejo diálogo multi-pestaña (mapa Leaflet/monumentos/DWG de
referencia/superponer) por un flujo único, adaptado de `auxiliar/pdf_georef.py`:

    Izquierda: el plano YA cargado en el proyecto (PDF + utilidades dibujadas),
               clic = punto en píxeles de escena, con IMÁN a la línea de
               utilidad más cercana (vértice o segmento).
    Derecha:   mapa de centerlines reales de Los Ángeles (NavigateLA), clic =
               punto en pies EPSG:2229, con imán al vértice/intersección más
               cercana. Buscador de dirección/intersección (geocoder Esri +
               respaldo Nominatim, vía urllib — sin dependencias nuevas).

Con ≥3 pares se ajusta una transformación afín (reusa `geo.georef.fit`, el
mismo núcleo que ya usa el resto de la app) y el botón "Guardar
georreferenciación" fija `self.georef` en la ventana principal y GUARDA el
proyecto de una — no hace falta pasar por "Guardar proyecto" aparte.

Todo en EPSG:2229 (State Plane CA Zona V, ftUS) — el único CRS que tiene
sentido para las calles de NavigateLA, y el mismo que usa el resto del
proyecto (imperial, pies).

Dependencias: matplotlib (ya en requirements.txt), pyproj (reproyección UTM
del geocoder), y opcionalmente contextily (mapa base satelital/calles de
fondo — si no está instalado, el mapa sigue funcionando solo con las
centerlines, sin imagen de fondo).
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
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure

try:
    import contextily as cx
    HAS_CTX = True
except Exception:
    HAS_CTX = False

from geo import georef as georef_mod

TARGET_EPSG = 2229                    # State Plane CA Zona V, ftUS — nativo NavigateLA
DEFAULT_BUFFER_FT = 1300              # ≈ 400 m, radio inicial de descarga de centerlines
SNAP_PX = 10                          # imán del lado PDF, en píxeles de escena
SNAP_FT = 30.0                        # imán del lado mapa, en pies (≈ 9 m)
BASEMAP_ZOOM = 18                     # nivel de tile fijo (más alto = más nítido, más tiles)

# Tile providers con URL directa (evita depender de contextily.providers, que a
# veces cae en tiles cacheados 403 del OSM público). Se prueban en orden hasta
# que uno cargue — mismo patrón que auxiliar/pdf_georef.py.
_TILE_PROVIDERS = [
    ("CartoDB Voyager", "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"),
    ("Esri World Imagery", "https://server.arcgisonline.com/ArcGIS/rest/services/"
                            "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    ("Esri World Street", "https://server.arcgisonline.com/ArcGIS/rest/services/"
                           "World_Street_Map/MapServer/tile/{z}/{y}/{x}"),
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


def snap_to_lines(pt, polylines, max_dist):
    """polylines: lista de listas de (x,y). Snap al vértice más cercano dentro
    de max_dist; si no hay ninguno, al punto más cercano sobre cualquier
    segmento (también dentro de max_dist). Si nada califica, devuelve pt tal cual."""
    x, y = pt
    best_v, best_vd = None, float("inf")
    for pts in polylines:
        for (vx, vy) in pts:
            d = math.hypot(vx - x, vy - y)
            if d < best_vd:
                best_vd, best_v = d, (vx, vy)
    if best_v is not None and best_vd <= max_dist:
        return best_v
    best_s, best_sd = None, float("inf")
    for pts in polylines:
        for i in range(len(pts) - 1):
            proj = _closest_on_segment((x, y), pts[i], pts[i + 1])
            d = math.hypot(proj[0] - x, proj[1] - y)
            if d < best_sd:
                best_sd, best_s = d, proj
    if best_s is not None and best_sd <= max_dist:
        return best_s
    return pt


# ─────────────────────────── vista del plano (PDF + utilidades) ───────────────────────────
class _PdfPickView(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float)

    def __init__(self, qimg):
        super().__init__(); sc = QtWidgets.QGraphicsScene(self); self.setScene(sc)
        self._pm = sc.addPixmap(QtGui.QPixmap.fromImage(qimg))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(28, 28, 28))
        self.setToolTip("Clic izquierdo: punto de control (imán a la utilidad más cercana)\n"
                        "Rueda: desplazar · Ctrl+Rueda: zoom")
        self.setMouseTracking(True)
        pen_h = QtGui.QPen(QtGui.QColor(255, 255, 255, 130)); pen_h.setCosmetic(True); pen_h.setWidthF(1.0)
        self._hline = sc.addLine(0, 0, 0, 0, pen_h); self._vline = sc.addLine(0, 0, 0, 0, pen_h)
        self._hline.setZValue(1000); self._vline.setZValue(1000)
        self._hline.setVisible(False); self._vline.setVisible(False)
        QtCore.QTimer.singleShot(0, lambda: self.fitInView(self._pm, QtCore.Qt.KeepAspectRatio))

    def wheelEvent(self, e):
        if e.modifiers() & QtCore.Qt.ControlModifier:
            f = 1.25 if e.angleDelta().y() > 0 else 0.8; self.scale(f, f)
            return
        # Sin Ctrl: la rueda DESPLAZA (vertical; con Shift, horizontal) en vez
        # de hacer zoom — más cómodo para recorrer el plano sin perder el nivel
        # de detalle alcanzado.
        dy = e.angleDelta().y(); dx = e.angleDelta().x()
        if e.modifiers() & QtCore.Qt.ShiftModifier and dx == 0:
            dx, dy = dy, dx
        hbar = self.horizontalScrollBar(); vbar = self.verticalScrollBar()
        if dx: hbar.setValue(hbar.value() - dx)
        if dy: vbar.setValue(vbar.value() - dy)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint()); self.clicked.emit(sp.x(), sp.y())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        sp = self.mapToScene(e.position().toPoint())
        rect = self.scene().sceneRect()
        self._hline.setLine(rect.left(), sp.y(), rect.right(), sp.y())
        self._vline.setLine(sp.x(), rect.top(), sp.x(), rect.bottom())
        self._hline.setVisible(True); self._vline.setVisible(True)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hline.setVisible(False); self._vline.setVisible(False)
        super().leaveEvent(e)

    def add_mark(self, x, y, color):
        pen = QtGui.QPen(QtGui.QColor(color)); pen.setCosmetic(True)
        return self.scene().addEllipse(x - 6, y - 6, 12, 12, pen, QtGui.QBrush(QtGui.QColor(color)))


# ─────────────────────────── mapa de centerlines (matplotlib, clic + scroll zoom) ───────────────────────────
class _MapCanvas(FigureCanvas):
    clicked = QtCore.Signal(float, float)

    def __init__(self):
        self.fig = Figure(figsize=(5, 5), tight_layout=True)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect("equal", adjustable="datalim")
        self.toolbar = None
        self.mpl_connect("button_press_event", self._on_click)
        self.mpl_connect("scroll_event", self._on_scroll)

    def set_toolbar(self, toolbar):
        self.toolbar = toolbar

    def _on_click(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        if self.toolbar and self.toolbar.mode:
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

    def clear(self):
        self.ax.cla(); self.ax.set_aspect("equal", adjustable="datalim")

    def redraw(self):
        self.draw_idle()


class GeorefDialog(QtWidgets.QDialog):
    def __init__(self, parent, plan_qimage, pipes, init_georef=None):
        super().__init__(parent)
        self._main = parent
        self.setWindowTitle("Georreferenciar plano"); self.resize(1400, 860)
        self.result_georef = None
        self._pipe_lines = [p.get("pts", []) for p in (pipes or []) if len(p.get("pts", [])) >= 2]
        self.centerlines = []             # [[ (x,y) en ft 2229, ... ], ...]
        self.pairs = []                   # [{"px":(x,y), "world":(X,Y), "label":str, "mark":item}]
        self._pending_px = None; self._pending_mark = None
        self._map_view_limits = None

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
        pv.addWidget(QtWidgets.QLabel("Plano (PDF + utilidades)  —  clic: punto de control (imán a la línea)  |  "
                                     "rueda: desplazar  |  Ctrl+rueda: zoom"))
        self.pdf = _PdfPickView(plan_qimage); self.pdf.clicked.connect(self._on_pdf_click)
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
        b_fetch = QtWidgets.QPushButton("Buscar y descargar"); b_fetch.clicked.connect(self._on_fetch)
        srow.addWidget(b_fetch)
        mv.addLayout(srow)
        mv.addWidget(QtWidgets.QLabel("Calles de LA (NavigateLA)  —  clic: punto de control (imán a la intersección)  |  rueda: zoom"))
        self.canvas_map = _MapCanvas(); self.canvas_map.clicked.connect(self._on_map_click)
        self.toolbar_map = NavigationToolbar(self.canvas_map, self); self.canvas_map.set_toolbar(self.toolbar_map)
        mv.addWidget(self.toolbar_map); mv.addWidget(self.canvas_map, 1)
        split.addWidget(map_w)

        split.setSizes([700, 700]); root.addWidget(split, 1)

        self.hint = QtWidgets.QLabel("1) Busca y descarga las calles de la zona · 2) clic en el plano (izquierda) "
                                     "· 3) clic en la calle correspondiente (derecha). Mínimo 3 pares.")
        self.hint.setStyleSheet("color:#9cf;"); root.addWidget(self.hint)

        crow = QtWidgets.QHBoxLayout()
        self.b_fit = QtWidgets.QPushButton("Ajustar afín + RMSE"); self.b_fit.clicked.connect(self._compute)
        crow.addWidget(self.b_fit)
        self.lbl_rms = QtWidgets.QLabel("RMSE: —"); crow.addWidget(self.lbl_rms, 1)
        b_del = QtWidgets.QPushButton("Eliminar sel."); b_del.clicked.connect(self._del_pair); crow.addWidget(b_del)
        b_clear = QtWidgets.QPushButton("Limpiar todos"); b_clear.clicked.connect(self._clear_pairs); crow.addWidget(b_clear)
        root.addLayout(crow)

        self.lst = QtWidgets.QListWidget(); self.lst.setMaximumHeight(140); root.addWidget(self.lst)

        bb = QtWidgets.QHBoxLayout()
        self.b_save = QtWidgets.QPushButton("💾 Guardar georreferenciación")
        self.b_save.setEnabled(False); self.b_save.clicked.connect(self._save)
        bb.addStretch(1); bb.addWidget(self.b_save)
        b_cancel = QtWidgets.QPushButton("Cerrar sin guardar"); b_cancel.clicked.connect(self.reject)
        bb.addWidget(b_cancel)
        root.addLayout(bb)

        # precargar pares de una georreferencia previa (si el punto trae "world")
        if init_georef is not None and init_georef.points:
            for p in init_georef.points:
                px = tuple(p.get("px", ())); wd = tuple(p.get("world", ())) if p.get("world") else None
                if len(px) == 2 and wd and len(wd) == 2:
                    m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
                    self.pairs.append({"px": px, "world": wd, "label": p.get("label", ""), "mark": m})
            self._refresh_list()

    # ── acciones ──
    def _on_fetch(self):
        addr = self.ed_addr.text().strip()
        if not addr:
            QtWidgets.QMessageBox.information(self, "Falta dirección", "Escribe una dirección o intersección."); return
        self.hint.setText("Geocodificando…"); QtWidgets.QApplication.processEvents()
        try:
            lat, lon, matched = geocode(addr)
            cx_ft, cy_ft = georef_mod.lonlat_to_utm(lon, lat, TARGET_EPSG)
            from geo.la_reference import fetch_streets_2229
            lines = fetch_streets_2229(cx_ft, cy_ft, radius=self.sp_buffer.value())
            if not lines:
                raise RuntimeError("No se encontraron calles en esa zona. Prueba un radio mayor.")
            self.centerlines = lines
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e)); return
        self._map_view_limits = None
        self.hint.setText(f"{len(lines)} tramos — {matched}. Marca puntos de control.")
        self._draw_map()

    def _on_pdf_click(self, x, y):
        sx, sy = snap_to_lines((x, y), self._pipe_lines, SNAP_PX)
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        self._pending_px = (sx, sy)
        self._pending_mark = self.pdf.add_mark(sx, sy, "#ff9a28")
        self.hint.setText("Punto del plano fijado. Ahora clic en la calle correspondiente (derecha).")

    def _on_map_click(self, x, y):
        if self._pending_px is None:
            self.hint.setText("Primero clic en el plano (izquierda)."); return
        if not self.centerlines:
            self.hint.setText("Primero descarga las calles de la zona."); return
        sx, sy = snap_to_lines((x, y), self.centerlines, SNAP_FT)
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        m = self.pdf.add_mark(self._pending_px[0], self._pending_px[1], "#5fd35f")
        self.pairs.append({"px": self._pending_px, "world": (sx, sy), "label": "", "mark": m})
        self._pending_px = None; self._pending_mark = None
        self._map_view_limits = (self.canvas_map.ax.get_xlim(), self.canvas_map.ax.get_ylim())
        self._refresh_list(); self._draw_map()
        self.hint.setText(f"Punto {len(self.pairs)} agregado. Repite (mínimo 3) y pulsa «Ajustar afín».")

    def _del_pair(self):
        r = self.lst.currentRow()
        if r < 0 and self.pairs:
            r = len(self.pairs) - 1
        if 0 <= r < len(self.pairs):
            p = self.pairs.pop(r)
            if p.get("mark") is not None:
                self.pdf.scene().removeItem(p["mark"])
            self._refresh_list(); self._draw_map()
            self.b_save.setEnabled(False); self.lbl_rms.setText("RMSE: —")

    def _clear_pairs(self):
        for p in self.pairs:
            if p.get("mark") is not None:
                self.pdf.scene().removeItem(p["mark"])
        self.pairs.clear(); self._pending_px = None
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark); self._pending_mark = None
        self._refresh_list(); self._draw_map()
        self.b_save.setEnabled(False); self.lbl_rms.setText("RMSE: —")

    def _compute(self):
        if len(self.pairs) < 3:
            QtWidgets.QMessageBox.information(self, "Faltan puntos", "Se necesitan al menos 3 puntos de control."); return
        px = [p["px"] for p in self.pairs]; world = [p["world"] for p in self.pairs]
        try:
            matrix, rms, ttype = georef_mod.fit(px, world, kind="affine")
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
        if not getattr(self, "_fit_result", None):
            return
        matrix, rms, ttype = self._fit_result
        pts = [{"px": list(p["px"]), "world": list(p["world"]), "label": p.get("label", "")}
               for p in self.pairs]
        self.result_georef = georef_mod.Georef(matrix=matrix, epsg=TARGET_EPSG, kind=ttype, rms=rms, points=pts)
        self._main.georef = self.result_georef; self._main._dirty = True
        self._main._update_geo_status(); self._main._redraw()
        self._main.save_project()
        saved_to = self._main.project_path
        if saved_to:
            QtWidgets.QMessageBox.information(self, "Georreferenciación guardada",
                f"✓ Guardado en el proyecto:\n{saved_to}\n\nEPSG: {TARGET_EPSG}\nRMSE: {rms:.2f} ft")
            self.accept()
        # si no había project_path, save_project() ya disparó "Guardar como…";
        # si el usuario canceló ese diálogo, se deja el resultado listo pero
        # el diálogo abierto para que pueda reintentar «Guardar».

    # ── dibujado ──
    def _draw_map(self):
        c = self.canvas_map; c.clear()
        if not self.centerlines:
            c.redraw(); return
        xs, ys = [], []
        for pts in self.centerlines:
            xx = [p[0] for p in pts]; yy = [p[1] for p in pts]
            xs += xx; ys += yy
            c.ax.plot(xx, yy, "-", color="#2a5", linewidth=1.2)
        pad = 100
        c.ax.set_xlim(min(xs) - pad, max(xs) + pad)
        c.ax.set_ylim(min(ys) - pad, max(ys) + pad)
        if HAS_CTX:
            # Zoom de tile FIJO y alto (en vez de "auto", que para un radio de
            # varias cuadras suele elegir un nivel bajo → imagen borrosa al
            # escalarla). Se prueban proveedores en orden hasta que uno cargue.
            for _name, _url in _TILE_PROVIDERS:
                try:
                    cx.add_basemap(c.ax, crs=f"EPSG:{TARGET_EPSG}", source=_url,
                                   zoom=BASEMAP_ZOOM, attribution=f"© {_name}", attribution_size=6)
                    break
                except Exception:
                    continue
        for i, p in enumerate(self.pairs, 1):
            X, Y = p["world"]
            c.ax.plot(X, Y, "o", color="red", markersize=8, markeredgecolor="white")
            c.ax.annotate(str(i), (X, Y), color="red", xytext=(6, 6), textcoords="offset points", fontweight="bold")
        c.ax.set_xticks([]); c.ax.set_yticks([])
        if self._map_view_limits is not None:
            c.ax.set_xlim(self._map_view_limits[0]); c.ax.set_ylim(self._map_view_limits[1])
        c.redraw()

    def _refresh_list(self):
        self.lst.clear()
        for i, p in enumerate(self.pairs, 1):
            x, y = p["px"]; X, Y = p["world"]
            self.lst.addItem(QtWidgets.QListWidgetItem(
                f"{i}   plano({x:.0f},{y:.0f})  →  calle({X:.2f},{Y:.2f}) ft"))
