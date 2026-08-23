"""
PDF Georef LA — v2
- PySide6
- Geocoder ArcGIS de LA City (el mismo que usa NavigateLA) + Nominatim fallback
- Zoom con toolbar + scroll del ratón sobre el cursor en PDF y mapa

Instalar dependencias:
    pip install -r requirements.txt
Ejecutar:
    python pdf_georef.py
"""

import os
os.environ["QT_API"] = "pyside6"  # matplotlib usará PySide6

import sys
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import requests
import fitz  # PyMuPDF
import ezdxf
from PIL import Image
from pyproj import Transformer
from geopy.geocoders import Nominatim
from shapely.geometry import LineString, Point

import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QPushButton, QLabel,
    QLineEdit, QHBoxLayout, QVBoxLayout, QMessageBox, QListWidget, QSplitter,
    QDoubleSpinBox, QGroupBox, QStatusBar, QListWidgetItem,
)

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure

try:
    import contextily as cx
    HAS_CTX = True
except ImportError:
    HAS_CTX = False


# URLs directas de tile providers (evita depender de contextily.providers,
# que puede caer en tiles cacheados 403 del OSM público).
TILE_PROVIDERS = [
    ("CartoDB Voyager",
     "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"),
    ("CartoDB Positron",
     "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"),
    ("Esri World Street",
     "https://server.arcgisonline.com/ArcGIS/rest/services/"
     "World_Street_Map/MapServer/tile/{z}/{y}/{x}"),
    ("Esri World Imagery",
     "https://server.arcgisonline.com/ArcGIS/rest/services/"
     "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
]


def clear_contextily_cache():
    """
    Borra el cache de contextily. Necesario si tiles previos quedaron
    envenenados con respuestas 403 (por ejemplo del OSM público).
    """
    import shutil
    from pathlib import Path
    candidates = [
        Path.home() / ".cache" / "contextily",                    # Linux/Mac
        Path(os.environ.get("LOCALAPPDATA", "")) / "contextily" / "Cache",  # Win
        Path(os.environ.get("LOCALAPPDATA", "")) / "contextily",           # Win alt
    ]
    for p in candidates:
        try:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
TARGET_EPSG = 2229          # State Plane California V, ftUS (nativo NavigateLA)
WGS84_EPSG = 4326

LA_CENTERLINE_URL = (
    "https://maps.lacity.org/lahub/rest/services/"
    "Street_Information/MapServer/36/query"
)
# Geocoder oficial de LA (mismo motor que NavigateLA)
LA_GEOCODER_URL = (
    "https://maps.lacity.org/arcgis/rest/services/Locators/"
    "Centerline_WebMerc/GeocodeServer/findAddressCandidates"
)
# Geocoder World de ArcGIS (público, sin token, excelente con intersecciones)
ESRI_WORLD_GEOCODER_URL = (
    "https://geocode.arcgis.com/arcgis/rest/services/"
    "World/GeocodeServer/findAddressCandidates"
)

DEFAULT_BUFFER_M = 400

_to_target_from_wgs = Transformer.from_crs(WGS84_EPSG, TARGET_EPSG, always_xy=True)


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
@dataclass
class ControlPoint:
    pdf_uv: Tuple[float, float]
    world_xy: Tuple[float, float]  # EPSG:2229 (ftUS), nativo NavigateLA
    label: str = ""


@dataclass
class GeorefState:
    pdf_path: Optional[str] = None
    pdf_page_image: Optional[np.ndarray] = None
    pdf_page_size_pt: Tuple[float, float] = (0, 0)
    pdf_dpi: int = 150
    centerlines: List[LineString] = field(default_factory=list)
    control_points: List[ControlPoint] = field(default_factory=list)
    affine: Optional[np.ndarray] = None
    rmse_m: Optional[float] = None


# ---------------------------------------------------------------------------
# Geocoding: LA ArcGIS -> Nominatim
# ---------------------------------------------------------------------------
def _ensure_la_context(q: str) -> str:
    """Si el query no menciona LA/California, se lo añade para desambiguar."""
    ql = q.lower()
    if "los angeles" in ql or " ca" in ql or "california" in ql or ", la" in ql:
        return q
    return f"{q}, Los Angeles, CA"


def _variants(query: str) -> List[str]:
    """Genera variantes del query normalizando conectores de intersección."""
    base = [
        query,
        query.replace(" at ", " & ").replace(" AT ", " & "),
        query.replace(" and ", " & ").replace(" AND ", " & "),
        query.replace(" & ", " and ").replace(" and ", " and "),
    ]
    out = []
    for q in base:
        q1 = q.strip()
        for v in (q1, _ensure_la_context(q1)):
            if v not in out:
                out.append(v)
    return out


def geocode_esri_world(query: str) -> Optional[Tuple[float, float, str, int]]:
    """
    Geocoder mundial de ArcGIS. Público, sin API key.
    Muy bueno con intersecciones tipo 'Colfax & Chandler, Los Angeles'.
    Devuelve (lat, lon, address, score) o None.
    """
    params = {
        "singleLine": query,
        "outFields": "Match_addr,Addr_type,Type,Score",
        "maxLocations": 3,
        "f": "json",
        # Bias a Los Angeles: bbox aprox LA county (WGS84)
        "searchExtent": "-118.95,33.65,-117.55,34.85",
    }
    try:
        r = requests.get(ESRI_WORLD_GEOCODER_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    cands = data.get("candidates", [])
    if not cands:
        return None
    top = cands[0]
    score = int(top.get("score", 0))
    if score < 70:
        return None
    loc = top["location"]
    # Esri World devuelve lon/lat en WGS84 por defecto
    return loc["y"], loc["x"], top.get("address", query), score


def geocode_la_arcgis(query: str) -> Optional[Tuple[float, float, str, int]]:
    params = {
        "SingleLine": query,
        "outFields": "*",
        "outSR": WGS84_EPSG,
        "maxLocations": 3,
        "f": "json",
    }
    try:
        r = requests.get(LA_GEOCODER_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    cands = data.get("candidates", [])
    if not cands:
        return None
    top = cands[0]
    score = int(top.get("score", 0))
    if score < 60:
        return None
    loc = top["location"]
    return loc["y"], loc["x"], top.get("address", query), score


def geocode_nominatim(query: str) -> Optional[Tuple[float, float, str, int]]:
    try:
        geoc = Nominatim(user_agent="pdf_georef_la_v2")
        loc = geoc.geocode(query, timeout=20)
        if loc:
            return loc.latitude, loc.longitude, loc.address, 100
    except Exception:
        pass
    return None


def geocode(query: str) -> Tuple[float, float, str]:
    """
    Cascada de geocoders. Devuelve (lat, lon, address).
    Prueba en orden: Esri World → LA Locator → Nominatim.
    """
    attempts = []  # para debug si todo falla

    for q in _variants(query):
        r = geocode_esri_world(q)
        attempts.append(("Esri World", q, r))
        if r:
            lat, lon, addr, score = r
            return lat, lon, f"{addr} [Esri, score {score}]"

    for q in _variants(query):
        r = geocode_la_arcgis(q)
        attempts.append(("LA City", q, r))
        if r:
            lat, lon, addr, score = r
            return lat, lon, f"{addr} [LA, score {score}]"

    for q in _variants(query):
        r = geocode_nominatim(q)
        attempts.append(("Nominatim", q, r))
        if r:
            lat, lon, addr, _ = r
            return lat, lon, f"{addr} [OSM]"

    tried = "\n".join(f"  • {name}: '{q}' → {'sin resultado' if r is None else 'OK'}"
                      for name, q, r in attempts[:6])
    raise RuntimeError(
        f"No se encontró '{query}'.\n\n"
        f"Se probó (primeros intentos):\n{tried}\n\n"
        f"Formatos que suelen funcionar:\n"
        f"  • Colfax Ave & Chandler Blvd, Los Angeles, CA\n"
        f"  • 5th St & Spring St, Los Angeles\n"
        f"  • 200 N Spring St, Los Angeles, CA 90012"
    )


# ---------------------------------------------------------------------------
# Centerlines
# ---------------------------------------------------------------------------
def fetch_la_centerlines(lat: float, lon: float,
                         buffer_m: float = DEFAULT_BUFFER_M) -> List[LineString]:
    """
    Descarga centerlines en EPSG:2229 NATIVO (State Plane CA V, ftUS).
    Sin reproyecciones intermedias — máxima precisión.
    """
    # Punto central en 2229 (ft)
    x, y = _to_target_from_wgs.transform(lon, lat)
    # buffer_m viene en metros; convertir a pies
    buffer_ft = buffer_m * 3.28084
    xmin, ymin = x - buffer_ft, y - buffer_ft
    xmax, ymax = x + buffer_ft, y + buffer_ft
    params = {
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": TARGET_EPSG,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": TARGET_EPSG,
        "f": "geojson",
    }
    r = requests.get(LA_CENTERLINE_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    lines: List[LineString] = []
    for feat in data.get("features", []):
        geom = feat.get("geometry", {})
        if geom.get("type") == "LineString":
            lines.append(LineString(geom["coordinates"]))
        elif geom.get("type") == "MultiLineString":
            for coords in geom["coordinates"]:
                lines.append(LineString(coords))
    return lines


def snap_to_centerline_vertex(xy: Tuple[float, float],
                              centerlines: List[LineString],
                              max_dist_ft: float = 80.0) -> Tuple[float, float]:
    """
    Snap en unidades de EPSG:2229 (feet). 80 ft ≈ 25 m.
    """
    p = Point(xy)
    best_pt, best_d = None, float("inf")
    for ln in centerlines:
        for vx, vy in ln.coords:
            d = ((vx - xy[0]) ** 2 + (vy - xy[1]) ** 2) ** 0.5
            if d < best_d:
                best_d, best_pt = d, (vx, vy)
    if best_pt is not None and best_d <= max_dist_ft:
        return best_pt
    best_pt, best_d = None, float("inf")
    for ln in centerlines:
        proj = ln.interpolate(ln.project(p))
        d = p.distance(proj)
        if d < best_d:
            best_d, best_pt = d, (proj.x, proj.y)
    if best_pt is not None and best_d <= max_dist_ft:
        return best_pt
    return xy


# ---------------------------------------------------------------------------
# Afín
# ---------------------------------------------------------------------------
def compute_affine(cps: List[ControlPoint]) -> Tuple[np.ndarray, float]:
    if len(cps) < 3:
        raise ValueError("Se necesitan al menos 3 puntos de control.")
    n = len(cps)
    A = np.zeros((2 * n, 6)); b = np.zeros(2 * n)
    for i, cp in enumerate(cps):
        u, v = cp.pdf_uv; X, Y = cp.world_xy
        A[2 * i]     = [u, v, 1, 0, 0, 0]
        A[2 * i + 1] = [0, 0, 0, u, v, 1]
        b[2 * i], b[2 * i + 1] = X, Y
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    M = np.array([[sol[0], sol[1], sol[2]],
                  [sol[3], sol[4], sol[5]]])
    resid = 0.0
    for cp in cps:
        u, v = cp.pdf_uv; X, Y = cp.world_xy
        Xp = M[0, 0] * u + M[0, 1] * v + M[0, 2]
        Yp = M[1, 0] * u + M[1, 1] * v + M[1, 2]
        resid += (X - Xp) ** 2 + (Y - Yp) ** 2
    return M, (resid / len(cps)) ** 0.5


def apply_affine(M: np.ndarray, u: float, v: float) -> Tuple[float, float]:
    return (M[0, 0] * u + M[0, 1] * v + M[0, 2],
            M[1, 0] * u + M[1, 1] * v + M[1, 2])


# ---------------------------------------------------------------------------
# Canvas con clic + scroll zoom + toolbar
# ---------------------------------------------------------------------------
class ClickCanvas(FigureCanvas):
    def __init__(self, on_click):
        self.fig = Figure(figsize=(5, 5), tight_layout=True)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect("equal", adjustable="datalim")
        self._on_click_cb = on_click
        self.toolbar: Optional[NavigationToolbar] = None
        self.mpl_connect("button_press_event", self._on_click)
        self.mpl_connect("scroll_event", self._on_scroll)

    def set_toolbar(self, toolbar):
        self.toolbar = toolbar

    def _in_nav_mode(self) -> bool:
        return bool(self.toolbar and self.toolbar.mode)

    def _on_click(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        if self._in_nav_mode():
            return
        self._on_click_cb(event.xdata, event.ydata)

    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        step = 1.25
        scale = 1 / step if event.button == "up" else step
        x, y = event.xdata, event.ydata
        xl = self.ax.get_xlim(); yl = self.ax.get_ylim()
        self.ax.set_xlim(x - (x - xl[0]) * scale, x + (xl[1] - x) * scale)
        self.ax.set_ylim(y - (y - yl[0]) * scale, y + (yl[1] - y) * scale)
        self.draw_idle()

    def clear(self):
        self.ax.cla()
        self.ax.set_aspect("equal", adjustable="datalim")

    def redraw(self):
        self.draw_idle()


# ---------------------------------------------------------------------------
# Ventana
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Georef LA — v2")
        self.resize(1500, 900)

        self.state = GeorefState()
        self._pending_pdf_uv: Optional[Tuple[float, float]] = None
        self._map_view_limits = None
        self._pdf_view_limits = None

        self._build_ui()
        self._refresh_lists()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central)

        controls = QVBoxLayout()

        gb = QGroupBox("1. PDF"); v = QVBoxLayout(gb)
        b = QPushButton("Abrir PDF…"); b.clicked.connect(self.on_open_pdf); v.addWidget(b)
        self.lbl_pdf = QLabel("(ninguno)"); v.addWidget(self.lbl_pdf)
        controls.addWidget(gb)

        gb = QGroupBox("2. Centerlines de LA"); v = QVBoxLayout(gb)
        v.addWidget(QLabel("Dirección o intersección:"))
        self.ed_addr = QLineEdit()
        self.ed_addr.setPlaceholderText("Ej: COLFAX AVE & CHANDLER BLVD")
        self.ed_addr.returnPressed.connect(self.on_fetch)
        v.addWidget(self.ed_addr)
        h = QHBoxLayout(); h.addWidget(QLabel("Radio (m):"))
        self.sp_buffer = QDoubleSpinBox()
        self.sp_buffer.setRange(100, 3000); self.sp_buffer.setValue(DEFAULT_BUFFER_M)
        self.sp_buffer.setSingleStep(50); h.addWidget(self.sp_buffer)
        v.addLayout(h)
        b = QPushButton("Buscar y descargar"); b.clicked.connect(self.on_fetch); v.addWidget(b)
        self.lbl_ref = QLabel("(sin datos)"); v.addWidget(self.lbl_ref)
        controls.addWidget(gb)

        gb = QGroupBox("3. Puntos de control (≥3)"); v = QVBoxLayout(gb)
        v.addWidget(QLabel("• Clic en PDF → clic en mapa\n"
                           "• Snap a intersección más cercana\n"
                           "• Rueda del ratón: zoom sobre cursor"))
        self.lst_cp = QListWidget(); v.addWidget(self.lst_cp)
        h = QHBoxLayout()
        b1 = QPushButton("Eliminar sel."); b1.clicked.connect(self.on_del_cp)
        b2 = QPushButton("Limpiar todos"); b2.clicked.connect(self.on_clear_cp)
        h.addWidget(b1); h.addWidget(b2); v.addLayout(h)
        controls.addWidget(gb)

        gb = QGroupBox("4. Transformación"); v = QVBoxLayout(gb)
        b = QPushButton("Ajustar afín + RMSE"); b.clicked.connect(self.on_fit); v.addWidget(b)
        self.lbl_rmse = QLabel("RMSE: —"); v.addWidget(self.lbl_rmse)
        controls.addWidget(gb)

        gb = QGroupBox("5. Exportar"); v = QVBoxLayout(gb)
        b = QPushButton("Exportar DXF georreferenciado…")
        b.clicked.connect(self.on_export_dxf); v.addWidget(b)
        v.addWidget(QLabel(f"CRS: EPSG:{TARGET_EPSG}\n(State Plane CA V, ftUS)"))
        controls.addWidget(gb)

        controls.addStretch(1)
        left = QWidget(); left.setLayout(controls); left.setFixedWidth(340)
        root.addWidget(left)

        splitter = QSplitter(Qt.Horizontal)

        pdf_w = QWidget(); pv = QVBoxLayout(pdf_w)
        pv.addWidget(QLabel("PDF  —  clic izquierdo: marcar punto  |  rueda: zoom"))
        self.canvas_pdf = ClickCanvas(self._on_pdf_click)
        self.toolbar_pdf = NavigationToolbar(self.canvas_pdf, self)
        self.canvas_pdf.set_toolbar(self.toolbar_pdf)
        pv.addWidget(self.toolbar_pdf); pv.addWidget(self.canvas_pdf)
        splitter.addWidget(pdf_w)

        map_w = QWidget(); mv = QVBoxLayout(map_w)
        mv.addWidget(QLabel("Mapa LA  —  clic: marcar (snap a intersección)  |  rueda: zoom"))
        self.canvas_map = ClickCanvas(self._on_map_click)
        self.toolbar_map = NavigationToolbar(self.canvas_map, self)
        self.canvas_map.set_toolbar(self.toolbar_map)
        mv.addWidget(self.toolbar_map); mv.addWidget(self.canvas_map)
        splitter.addWidget(map_w)

        splitter.setSizes([750, 750])
        root.addWidget(splitter, stretch=1)

        self.status = QStatusBar(); self.setStatusBar(self.status)
        self.status.showMessage("Listo.")

    # ---- Acciones ----
    def on_open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            doc = fitz.open(path)
            page = doc.load_page(0)
            zoom = self.state.pdf_dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, 3
            )
            self.state.pdf_path = path
            self.state.pdf_page_image = img
            self.state.pdf_page_size_pt = (page.rect.width, page.rect.height)
            doc.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No pude abrir el PDF:\n{e}"); return
        self._pdf_view_limits = None
        self.lbl_pdf.setText(os.path.basename(path))
        self._draw_pdf()
        self.status.showMessage(f"PDF cargado: {path}")

    def on_fetch(self):
        addr = self.ed_addr.text().strip()
        if not addr:
            QMessageBox.warning(self, "Falta dirección", "Escribe una dirección o intersección."); return
        self.status.showMessage("Geocodificando…"); QApplication.processEvents()
        try:
            lat, lon, matched = geocode(addr)
            self.status.showMessage(
                f"Coincidencia: '{matched}' ({lat:.6f}, {lon:.6f}). Descargando centerlines…"
            ); QApplication.processEvents()
            lines = fetch_la_centerlines(lat, lon, self.sp_buffer.value())
            if not lines:
                raise RuntimeError("La API no devolvió centerlines en esa zona. Prueba un radio mayor.")
            self.state.centerlines = lines
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e)); return
        self._map_view_limits = None
        self.lbl_ref.setText(f"{len(lines)} tramos — {matched}")
        self._draw_map()
        self.status.showMessage("Centerlines cargados. Marca puntos de control.")

    def on_del_cp(self):
        row = self.lst_cp.currentRow()
        if row < 0:
            return
        del self.state.control_points[row]
        self._refresh_lists(); self._draw_pdf(); self._draw_map()

    def on_clear_cp(self):
        self.state.control_points.clear(); self._pending_pdf_uv = None
        self._refresh_lists(); self._draw_pdf(); self._draw_map()

    def on_fit(self):
        try:
            M, rmse = compute_affine(self.state.control_points)
        except Exception as e:
            QMessageBox.warning(self, "No se puede ajustar", str(e)); return
        self.state.affine = M; self.state.rmse_m = rmse  # (nombre legado; ahora está en ft)
        rmse_ft = rmse  # ya está en ft (EPSG:2229 nativo)
        self.lbl_rmse.setText(f"RMSE: {rmse_ft:.3f} ft")
        color = "green" if rmse_ft < 1 else ("orange" if rmse_ft < 3 else "red")
        self.lbl_rmse.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.status.showMessage(
            f"Ajuste OK con {len(self.state.control_points)} puntos. RMSE {rmse_ft:.3f} ft."
        )

    def on_export_dxf(self):
        if self.state.affine is None:
            QMessageBox.warning(self, "Sin transformación", "Primero calcula la transformación."); return
        if self.state.pdf_page_image is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar DXF", "georef.dxf", "DXF (*.dxf)")
        if not path:
            return

        doc = ezdxf.new(dxfversion="R2018", setup=True)
        doc.header["$INSUNITS"] = 2  # ftUS
        msp = doc.modelspace()
        doc.layers.add("PDF_FRAME", color=8)
        doc.layers.add("PDF_IMAGE", color=7)
        doc.layers.add("CONTROL_POINTS", color=1)
        doc.layers.add("CENTERLINES_REF", color=4)

        img = self.state.pdf_page_image
        H, W = img.shape[:2]

        # --- 1) Guardar el PDF renderizado como PNG junto al DXF ---
        dxf_dir = os.path.dirname(os.path.abspath(path))
        dxf_base = os.path.splitext(os.path.basename(path))[0]
        png_name = f"{dxf_base}_pdf.png"
        png_path = os.path.join(dxf_dir, png_name)
        try:
            Image.fromarray(img).save(png_path)
        except Exception as e:
            QMessageBox.warning(self, "Aviso",
                f"No pude guardar la imagen del PDF ({e}).\n"
                f"El DXF se exportará sin la imagen raster.")
            png_path = None

        # --- 2) Contorno del PDF (rectángulo transformado) ---
        corners_uv = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
        corners_ft = [self._uv_to_target_ft(u, v) for u, v in corners_uv]
        msp.add_lwpolyline(corners_ft, dxfattribs={"layer": "PDF_FRAME"})

        # --- 3) Insertar imagen del PDF en el DXF (georreferenciada) ---
        if png_path is not None:
            try:
                # Esquinas relevantes: bottom-left es el insert point de AutoCAD
                bl_ft = self._uv_to_target_ft(0, H)       # esquina inferior-izquierda
                br_ft = self._uv_to_target_ft(W, H)       # esquina inferior-derecha
                tl_ft = self._uv_to_target_ft(0, 0)       # esquina superior-izquierda

                # Ancho, alto y rotación de la imagen en coords mundo
                dx = br_ft[0] - bl_ft[0]
                dy = br_ft[1] - bl_ft[1]
                width_units  = math.hypot(dx, dy)
                height_units = math.hypot(tl_ft[0] - bl_ft[0], tl_ft[1] - bl_ft[1])
                rotation_deg = math.degrees(math.atan2(dy, dx))

                image_def = doc.add_image_def(
                    filename=png_name,   # ruta relativa junto al DXF
                    size_in_pixel=(W, H),
                )
                image = msp.add_image(
                    insert=bl_ft,
                    size_in_units=(width_units, height_units),
                    image_def=image_def,
                    rotation=rotation_deg,
                    dxfattribs={"layer": "PDF_IMAGE"},
                )
                # Nivel de transparencia bajo para no tapar los centerlines
                try:
                    image.dxf.image_display = 1  # mostrar imagen
                except Exception:
                    pass
            except Exception as e:
                QMessageBox.warning(self, "Aviso",
                    f"No pude insertar la imagen en el DXF ({e}).\n"
                    f"El PNG queda en:\n{png_path}\n"
                    f"Puedes insertarlo manualmente con IMAGEATTACH.")

        # --- 4) Puntos de control ---
        for i, cp in enumerate(self.state.control_points, 1):
            X_ft, Y_ft = cp.world_xy  # YA en EPSG:2229 nativo
            msp.add_circle((X_ft, Y_ft), radius=3, dxfattribs={"layer": "CONTROL_POINTS"})
            msp.add_text(f"CP{i}", dxfattribs={"layer": "CONTROL_POINTS", "height": 4}
                         ).set_placement((X_ft + 4, Y_ft + 4))

        # --- 5) Centerlines de referencia (nativos NavigateLA, sin reproyección) ---
        for ln in self.state.centerlines:
            pts_ft = list(ln.coords)
            if len(pts_ft) >= 2:
                msp.add_lwpolyline(pts_ft, dxfattribs={"layer": "CENTERLINES_REF"})

        # --- 6) GeoData para Civil 3D ---
        try:
            geodata = msp.new_geodata()
            geodata.setup_local_grid(design_point=(0, 0), reference_point=(0, 0))
            geodata.coordinate_system_definition = f"EPSG:{TARGET_EPSG}"
        except Exception:
            pass

        try:
            doc.saveas(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e)); return

        extra = f"\nImagen del PDF: {png_name}" if png_path else ""
        QMessageBox.information(
            self, "Listo",
            f"DXF exportado:\n{path}{extra}\n\n"
            f"CRS: EPSG:{TARGET_EPSG} (State Plane CA V, ftUS) — nativo NavigateLA\n"
            f"RMSE: {self.state.rmse_m:.3f} ft\n\n"
            f"En Civil 3D: si no ves la imagen, usa el comando IMAGEFRAME=2\n"
            f"o verifica que el PNG esté en la misma carpeta que el DXF."
        )

    def _uv_to_target_ft(self, u, v):
        # La afín ya mapea PDF -> EPSG:2229 (ft) directamente
        return apply_affine(self.state.affine, u, v)

    # ---- Clics ----
    def _on_pdf_click(self, x, y):
        if self.state.pdf_page_image is None:
            return
        self._pending_pdf_uv = (float(x), float(y))
        self._pdf_view_limits = (self.canvas_pdf.ax.get_xlim(),
                                 self.canvas_pdf.ax.get_ylim())
        self._draw_pdf()
        self.status.showMessage(f"Punto PDF ({x:.1f}, {y:.1f}). Ahora clic en el mapa.")

    def _on_map_click(self, x, y):
        if self._pending_pdf_uv is None:
            self.status.showMessage("Primero clic en el PDF."); return
        if not self.state.centerlines:
            self.status.showMessage("Primero descarga centerlines."); return
        snapped = snap_to_centerline_vertex(
            (float(x), float(y)), self.state.centerlines, max_dist_ft=80.0
        )
        cp = ControlPoint(pdf_uv=self._pending_pdf_uv, world_xy=snapped,
                          label=f"CP{len(self.state.control_points) + 1}")
        self.state.control_points.append(cp)
        self._pending_pdf_uv = None
        self._map_view_limits = (self.canvas_map.ax.get_xlim(),
                                 self.canvas_map.ax.get_ylim())
        self._refresh_lists(); self._draw_pdf(); self._draw_map()
        self.status.showMessage(f"Añadido {cp.label}. Total: {len(self.state.control_points)}.")

    # ---- Dibujado ----
    def _draw_pdf(self):
        c = self.canvas_pdf; c.clear()
        if self.state.pdf_page_image is None:
            c.redraw(); return
        c.ax.imshow(self.state.pdf_page_image, origin="upper")
        for i, cp in enumerate(self.state.control_points, 1):
            u, v = cp.pdf_uv
            c.ax.plot(u, v, "o", color="red", markersize=8, markeredgecolor="white")
            c.ax.annotate(f"CP{i}", (u, v), color="red",
                          xytext=(6, 6), textcoords="offset points", fontweight="bold")
        if self._pending_pdf_uv is not None:
            u, v = self._pending_pdf_uv
            c.ax.plot(u, v, "x", color="yellow", markersize=12, markeredgewidth=3)
        c.ax.set_xticks([]); c.ax.set_yticks([])
        if self._pdf_view_limits is not None:
            c.ax.set_xlim(self._pdf_view_limits[0])
            c.ax.set_ylim(self._pdf_view_limits[1])
        c.redraw()

    def _draw_map(self):
        c = self.canvas_map; c.clear()
        if not self.state.centerlines:
            c.redraw(); return
        xs, ys = [], []
        for ln in self.state.centerlines:
            for x, y in ln.coords:
                xs.append(x); ys.append(y)
            xx, yy = zip(*ln.coords)
            c.ax.plot(xx, yy, "-", color="#2a5", linewidth=1.2)
        pad = 100  # ft (era 30 m)
        c.ax.set_xlim(min(xs) - pad, max(xs) + pad)
        c.ax.set_ylim(min(ys) - pad, max(ys) + pad)
        if HAS_CTX:
            for name, url in TILE_PROVIDERS:
                try:
                    cx.add_basemap(
                        c.ax,
                        crs=f"EPSG:{TARGET_EPSG}",  # axis en 2229; ctx reproyecta tiles
                        source=url,
                        attribution=f"© {name}",
                        attribution_size=6,
                    )
                    break
                except Exception:
                    continue
        for i, cp in enumerate(self.state.control_points, 1):
            X, Y = cp.world_xy
            c.ax.plot(X, Y, "o", color="red", markersize=8, markeredgecolor="white")
            c.ax.annotate(f"CP{i}", (X, Y), color="red",
                          xytext=(6, 6), textcoords="offset points", fontweight="bold")
        c.ax.set_xticks([]); c.ax.set_yticks([])
        if self._map_view_limits is not None:
            c.ax.set_xlim(self._map_view_limits[0])
            c.ax.set_ylim(self._map_view_limits[1])
        c.redraw()

    def _refresh_lists(self):
        self.lst_cp.clear()
        for i, cp in enumerate(self.state.control_points, 1):
            u, v = cp.pdf_uv; X, Y = cp.world_xy
            self.lst_cp.addItem(QListWidgetItem(
                f"CP{i}   PDF({u:.0f},{v:.0f})  →  SP({X:.2f},{Y:.2f}) ft"
            ))


def main():
    # Borrar tiles cacheados de sesiones previas (por si OSM devolvió 403 antes)
    clear_contextily_cache()
    app = QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()