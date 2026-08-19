"""
PDF Georef LA — Georreferenciación rápida de PDFs de ingeniería para Los Ángeles
--------------------------------------------------------------------------------
Flujo:
  1. Abrir PDF (vectorial o escaneado).
  2. Buscar dirección/intersección (geocoder Nominatim).
  3. Descargar centerlines de calles de NavigateLA (LA City ArcGIS REST) del área.
  4. Marcar >=3 puntos de control (clic en PDF, luego clic en mapa — con snap a
     vértices/intersecciones de los centerlines).
  5. Calcular transformación afín (mínimos cuadrados) + RMSE.
  6. Exportar DXF georreferenciado en State Plane California Zone V (EPSG:2229, ft).

Dependencias (instalar con pip):
    PyQt5 PyMuPDF matplotlib numpy pyproj requests ezdxf geopy contextily shapely
"""

import sys
import io
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import requests
import fitz  # PyMuPDF
import ezdxf
from pyproj import Transformer
from geopy.geocoders import Nominatim
from shapely.geometry import LineString, Point

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QPushButton, QLabel,
    QLineEdit, QHBoxLayout, QVBoxLayout, QMessageBox, QListWidget, QSplitter,
    QComboBox, QDoubleSpinBox, QGroupBox, QStatusBar, QListWidgetItem,
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

try:
    import contextily as cx
    HAS_CTX = True
except ImportError:
    HAS_CTX = False


# ---------------------------------------------------------------------------
# Constantes de proyecciones y endpoints
# ---------------------------------------------------------------------------
# CRS destino para LA: State Plane California V, US Survey Feet (Civil 3D-friendly)
TARGET_EPSG = 2229                     # NAD83 / California zone 5 (ftUS)
WEB_MERC_EPSG = 3857                   # NavigateLA sirve en Web Mercator
WGS84_EPSG = 4326                      # lat/lon del geocoder

# LA City street centerlines (layer 36 del Street_Information MapServer)
LA_CENTERLINE_URL = (
    "https://maps.lacity.org/lahub/rest/services/"
    "Street_Information/MapServer/36/query"
)

# Buffer alrededor del punto geocodificado para descargar centerlines (metros)
DEFAULT_BUFFER_M = 400

# Transformadores pyproj
_to_target = Transformer.from_crs(WEB_MERC_EPSG, TARGET_EPSG, always_xy=True)
_to_webmerc = Transformer.from_crs(WGS84_EPSG, WEB_MERC_EPSG, always_xy=True)


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------
@dataclass
class ControlPoint:
    """Un par de puntos: PDF (u,v) <-> mundo (X,Y en Web Mercator metros)."""
    pdf_uv: Tuple[float, float]
    world_xy: Tuple[float, float]  # en Web Mercator (EPSG:3857)
    label: str = ""


@dataclass
class GeorefState:
    pdf_path: Optional[str] = None
    pdf_page_image: Optional[np.ndarray] = None   # imagen renderizada de la página
    pdf_page_size_pt: Tuple[float, float] = (0, 0)  # tamaño en puntos PDF
    pdf_dpi: int = 150
    centerlines: List[LineString] = field(default_factory=list)  # en Web Mercator
    control_points: List[ControlPoint] = field(default_factory=list)
    affine: Optional[np.ndarray] = None  # matriz 2x3 (u,v)->(X,Y en Web Mercator)
    rmse_m: Optional[float] = None


# ---------------------------------------------------------------------------
# Utilidades: descargar centerlines de LA
# ---------------------------------------------------------------------------
def fetch_la_centerlines(lat: float, lon: float,
                         buffer_m: float = DEFAULT_BUFFER_M) -> List[LineString]:
    """
    Descarga centerlines de calles de LA en un radio 'buffer_m' alrededor de
    (lat, lon). Devuelve lista de LineStrings en Web Mercator (metros).
    """
    x, y = _to_webmerc.transform(lon, lat)
    xmin, ymin = x - buffer_m, y - buffer_m
    xmax, ymax = x + buffer_m, y + buffer_m

    params = {
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": WEB_MERC_EPSG,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": WEB_MERC_EPSG,
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
                              max_dist_m: float = 25.0
                              ) -> Tuple[float, float]:
    """
    Snap un punto (Web Mercator m) al vértice de centerline más cercano.
    Si no hay vértice dentro de max_dist_m, snap al punto más cercano SOBRE la
    línea. Si tampoco, devuelve el punto original.
    """
    p = Point(xy)
    best_pt = None
    best_d = float("inf")

    # 1) preferir vértices exactos (intersecciones/nodos)
    for ln in centerlines:
        for vx, vy in ln.coords:
            d = ((vx - xy[0]) ** 2 + (vy - xy[1]) ** 2) ** 0.5
            if d < best_d:
                best_d = d
                best_pt = (vx, vy)
    if best_pt is not None and best_d <= max_dist_m:
        return best_pt

    # 2) si no, punto proyectado a la línea más cercana
    best_pt = None
    best_d = float("inf")
    for ln in centerlines:
        proj = ln.interpolate(ln.project(p))
        d = p.distance(proj)
        if d < best_d:
            best_d = d
            best_pt = (proj.x, proj.y)
    if best_pt is not None and best_d <= max_dist_m:
        return best_pt

    return xy


# ---------------------------------------------------------------------------
# Cálculo de transformación afín
# ---------------------------------------------------------------------------
def compute_affine(cps: List[ControlPoint]) -> Tuple[np.ndarray, float]:
    """
    Ajusta por mínimos cuadrados una transformación afín 2D:
        [X]   [a b tx] [u]
        [Y] = [c d ty] [v]
                       [1]
    Devuelve (matriz 2x3, RMSE en metros).
    """
    if len(cps) < 3:
        raise ValueError("Se necesitan al menos 3 puntos de control.")

    n = len(cps)
    A = np.zeros((2 * n, 6))
    b = np.zeros(2 * n)
    for i, cp in enumerate(cps):
        u, v = cp.pdf_uv
        X, Y = cp.world_xy
        A[2 * i]     = [u, v, 1, 0, 0, 0]
        A[2 * i + 1] = [0, 0, 0, u, v, 1]
        b[2 * i]     = X
        b[2 * i + 1] = Y

    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    M = np.array([[sol[0], sol[1], sol[2]],
                  [sol[3], sol[4], sol[5]]])

    # RMSE
    resid = 0.0
    for cp in cps:
        u, v = cp.pdf_uv
        X, Y = cp.world_xy
        Xp = M[0, 0] * u + M[0, 1] * v + M[0, 2]
        Yp = M[1, 0] * u + M[1, 1] * v + M[1, 2]
        resid += (X - Xp) ** 2 + (Y - Yp) ** 2
    rmse = (resid / len(cps)) ** 0.5
    return M, rmse


def apply_affine(M: np.ndarray, u: float, v: float) -> Tuple[float, float]:
    X = M[0, 0] * u + M[0, 1] * v + M[0, 2]
    Y = M[1, 0] * u + M[1, 1] * v + M[1, 2]
    return X, Y


# ---------------------------------------------------------------------------
# Canvas matplotlib con clic
# ---------------------------------------------------------------------------
class ClickCanvas(FigureCanvas):
    """Canvas matplotlib que reporta clics (data coords) al callback dado."""

    def __init__(self, on_click):
        self.fig = Figure(figsize=(5, 5), tight_layout=True)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect("equal", adjustable="datalim")
        self._on_click_cb = on_click
        self.mpl_connect("button_press_event", self._on_click)

    def _on_click(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        self._on_click_cb(event.xdata, event.ydata)

    def clear(self):
        self.ax.cla()
        self.ax.set_aspect("equal", adjustable="datalim")

    def redraw(self):
        self.draw_idle()


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Georef LA")
        self.resize(1400, 850)

        self.state = GeorefState()
        self._pending_pdf_uv: Optional[Tuple[float, float]] = None

        self._build_ui()
        self._refresh_lists()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ----- Barra izquierda de controles -----
        controls = QVBoxLayout()

        # PDF
        gb_pdf = QGroupBox("1. PDF")
        v = QVBoxLayout(gb_pdf)
        b = QPushButton("Abrir PDF…")
        b.clicked.connect(self.on_open_pdf)
        v.addWidget(b)
        self.lbl_pdf = QLabel("(ninguno)")
        v.addWidget(self.lbl_pdf)
        controls.addWidget(gb_pdf)

        # Referencia geográfica
        gb_ref = QGroupBox("2. Cargar centerlines de LA")
        v = QVBoxLayout(gb_ref)
        v.addWidget(QLabel("Dirección o intersección:"))
        self.ed_addr = QLineEdit()
        self.ed_addr.setPlaceholderText("Ej: 5th St & Spring St, Los Angeles, CA")
        v.addWidget(self.ed_addr)
        h = QHBoxLayout()
        h.addWidget(QLabel("Radio (m):"))
        self.sp_buffer = QDoubleSpinBox()
        self.sp_buffer.setRange(100, 3000)
        self.sp_buffer.setValue(DEFAULT_BUFFER_M)
        self.sp_buffer.setSingleStep(50)
        h.addWidget(self.sp_buffer)
        v.addLayout(h)
        b = QPushButton("Buscar y descargar centerlines")
        b.clicked.connect(self.on_fetch)
        v.addWidget(b)
        self.lbl_ref = QLabel("(sin datos)")
        v.addWidget(self.lbl_ref)
        controls.addWidget(gb_ref)

        # Puntos de control
        gb_cp = QGroupBox("3. Puntos de control (>= 3)")
        v = QVBoxLayout(gb_cp)
        v.addWidget(QLabel("• Clic en PDF, luego clic en mapa\n"
                           "• El punto del mapa se snap-ea a la\n"
                           "  intersección/vértice más cercano"))
        self.lst_cp = QListWidget()
        v.addWidget(self.lst_cp)
        h = QHBoxLayout()
        b1 = QPushButton("Eliminar seleccionado")
        b1.clicked.connect(self.on_del_cp)
        b2 = QPushButton("Limpiar todos")
        b2.clicked.connect(self.on_clear_cp)
        h.addWidget(b1)
        h.addWidget(b2)
        v.addLayout(h)
        controls.addWidget(gb_cp)

        # Ajuste
        gb_fit = QGroupBox("4. Calcular transformación")
        v = QVBoxLayout(gb_fit)
        b = QPushButton("Ajustar afín + RMSE")
        b.clicked.connect(self.on_fit)
        v.addWidget(b)
        self.lbl_rmse = QLabel("RMSE: —")
        v.addWidget(self.lbl_rmse)
        controls.addWidget(gb_fit)

        # Export
        gb_ex = QGroupBox("5. Exportar")
        v = QVBoxLayout(gb_ex)
        b = QPushButton("Exportar DXF georreferenciado…")
        b.clicked.connect(self.on_export_dxf)
        v.addWidget(b)
        v.addWidget(QLabel(f"CRS destino: EPSG:{TARGET_EPSG}\n"
                           "(State Plane CA V, ftUS)"))
        controls.addWidget(gb_ex)

        controls.addStretch(1)

        left = QWidget()
        left.setLayout(controls)
        left.setFixedWidth(340)
        root.addWidget(left)

        # ----- Vistas: PDF | Mapa -----
        splitter = QSplitter(Qt.Horizontal)

        # PDF canvas
        pdf_wrap = QVBoxLayout()
        pdf_w = QWidget()
        pdf_w.setLayout(pdf_wrap)
        pdf_wrap.addWidget(QLabel("PDF (clic para marcar punto)"))
        self.canvas_pdf = ClickCanvas(self._on_pdf_click)
        pdf_wrap.addWidget(self.canvas_pdf)
        splitter.addWidget(pdf_w)

        # Mapa canvas
        map_wrap = QVBoxLayout()
        map_w = QWidget()
        map_w.setLayout(map_wrap)
        map_wrap.addWidget(QLabel("Mapa LA (clic para marcar; snap a intersección)"))
        self.canvas_map = ClickCanvas(self._on_map_click)
        map_wrap.addWidget(self.canvas_map)
        splitter.addWidget(map_w)

        splitter.setSizes([700, 700])
        root.addWidget(splitter, stretch=1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Listo.")

    # ---------- Acciones ----------
    def on_open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir PDF", "", "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            doc = fitz.open(path)
            page = doc.load_page(0)
            # Renderizar a imagen
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
            QMessageBox.critical(self, "Error", f"No pude abrir el PDF:\n{e}")
            return

        self.lbl_pdf.setText(path.split("/")[-1])
        self._draw_pdf()
        self.status.showMessage(f"PDF cargado: {path}")

    def on_fetch(self):
        addr = self.ed_addr.text().strip()
        if not addr:
            QMessageBox.warning(self, "Falta dirección",
                                "Escribe una dirección o intersección.")
            return
        try:
            geoc = Nominatim(user_agent="pdf_georef_la")
            loc = geoc.geocode(addr, timeout=20)
            if loc is None:
                raise RuntimeError("No se encontró la dirección.")
            lat, lon = loc.latitude, loc.longitude
            self.status.showMessage(f"Geocodificado a {lat:.6f}, {lon:.6f}. "
                                    f"Descargando centerlines…")
            QApplication.processEvents()
            lines = fetch_la_centerlines(lat, lon, self.sp_buffer.value())
            if not lines:
                raise RuntimeError("La API no devolvió centerlines en esa zona.")
            self.state.centerlines = lines
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self.lbl_ref.setText(f"{len(lines)} tramos cargados")
        self._draw_map()
        self.status.showMessage("Centerlines cargados. Ya puedes marcar puntos.")

    def on_del_cp(self):
        row = self.lst_cp.currentRow()
        if row < 0:
            return
        del self.state.control_points[row]
        self._refresh_lists()
        self._draw_pdf()
        self._draw_map()

    def on_clear_cp(self):
        self.state.control_points.clear()
        self._pending_pdf_uv = None
        self._refresh_lists()
        self._draw_pdf()
        self._draw_map()

    def on_fit(self):
        try:
            M, rmse = compute_affine(self.state.control_points)
        except Exception as e:
            QMessageBox.warning(self, "No se puede ajustar", str(e))
            return
        self.state.affine = M
        self.state.rmse_m = rmse
        # RMSE está en metros (Web Mercator). Convertir a pies para el usuario.
        rmse_ft = rmse * 3.28084
        self.lbl_rmse.setText(f"RMSE: {rmse:.2f} m  ({rmse_ft:.2f} ft)")
        color = "green" if rmse_ft < 3 else ("orange" if rmse_ft < 8 else "red")
        self.lbl_rmse.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.status.showMessage(
            f"Ajuste OK con {len(self.state.control_points)} puntos. "
            f"RMSE {rmse_ft:.2f} ft."
        )

    def on_export_dxf(self):
        if self.state.affine is None:
            QMessageBox.warning(self, "Sin transformación",
                                "Primero calcula la transformación.")
            return
        if self.state.pdf_page_image is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar DXF", "georef.dxf", "DXF (*.dxf)"
        )
        if not path:
            return

        # DXF de demo: dibuja el rectángulo del PDF (esquinas transformadas) +
        # marca cada punto de control. En tu app real, aquí exportarías las
        # utilidades dibujadas (líneas, con capas de diámetro/familia).
        doc = ezdxf.new(dxfversion="R2018", setup=True)
        doc.header["$INSUNITS"] = 2   # 2 = Feet (US Survey)
        msp = doc.modelspace()

        # Capa de referencia (contorno del PDF)
        doc.layers.add("PDF_FRAME", color=8)
        doc.layers.add("CONTROL_POINTS", color=1)
        doc.layers.add("CENTERLINES_REF", color=4)

        img = self.state.pdf_page_image
        H, W = img.shape[:2]
        corners_uv = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
        corners_ft = [self._uv_to_target_ft(u, v) for u, v in corners_uv]
        msp.add_lwpolyline(corners_ft, dxfattribs={"layer": "PDF_FRAME"})

        # Puntos de control como círculos + texto
        for i, cp in enumerate(self.state.control_points, 1):
            X_ft, Y_ft = self._world_m_to_target_ft(*cp.world_xy)
            msp.add_circle((X_ft, Y_ft), radius=2,
                           dxfattribs={"layer": "CONTROL_POINTS"})
            msp.add_text(
                f"CP{i}",
                dxfattribs={"layer": "CONTROL_POINTS", "height": 3},
            ).set_placement((X_ft + 3, Y_ft + 3))

        # Centerlines como referencia
        for ln in self.state.centerlines:
            pts_ft = [_to_target.transform(x, y) for x, y in ln.coords]
            if len(pts_ft) >= 2:
                msp.add_lwpolyline(pts_ft, dxfattribs={"layer": "CENTERLINES_REF"})

        # GeoData para que Civil 3D reconozca el CRS
        try:
            geodata = msp.new_geodata()
            geodata.setup_local_grid(
                design_point=(0, 0),
                reference_point=(0, 0),
            )
            geodata.coordinate_system_definition = f"EPSG:{TARGET_EPSG}"
        except Exception:
            pass  # no crítico

        try:
            doc.saveas(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e))
            return

        QMessageBox.information(
            self, "Listo",
            f"DXF exportado:\n{path}\n\n"
            f"CRS: EPSG:{TARGET_EPSG} (State Plane CA V, ftUS)\n"
            f"RMSE: {self.state.rmse_m * 3.28084:.2f} ft"
        )

    # ---------- Conversores auxiliares ----------
    def _uv_to_target_ft(self, u: float, v: float) -> Tuple[float, float]:
        M = self.state.affine
        Xm, Ym = apply_affine(M, u, v)
        return _to_target.transform(Xm, Ym)

    def _world_m_to_target_ft(self, X: float, Y: float) -> Tuple[float, float]:
        return _to_target.transform(X, Y)

    # ---------- Clics ----------
    def _on_pdf_click(self, x_data, y_data):
        if self.state.pdf_page_image is None:
            return
        # imshow origin='upper': y_data ya está en coord pixel (invertida vertical
        # con set_ylim). Guardamos (u, v) en pixeles de la imagen renderizada.
        self._pending_pdf_uv = (float(x_data), float(y_data))
        self._draw_pdf()
        self.status.showMessage(
            f"Punto PDF marcado en ({x_data:.1f}, {y_data:.1f}). "
            f"Ahora haz clic en el mapa en el mismo lugar."
        )

    def _on_map_click(self, x_data, y_data):
        if self._pending_pdf_uv is None:
            self.status.showMessage("Primero haz clic en el PDF.")
            return
        if not self.state.centerlines:
            self.status.showMessage("Primero descarga centerlines.")
            return
        snapped = snap_to_centerline_vertex(
            (float(x_data), float(y_data)),
            self.state.centerlines,
            max_dist_m=25.0,
        )
        cp = ControlPoint(
            pdf_uv=self._pending_pdf_uv,
            world_xy=snapped,
            label=f"CP{len(self.state.control_points) + 1}",
        )
        self.state.control_points.append(cp)
        self._pending_pdf_uv = None
        self._refresh_lists()
        self._draw_pdf()
        self._draw_map()
        self.status.showMessage(f"Añadido {cp.label}. "
                                f"Total: {len(self.state.control_points)}.")

    # ---------- Dibujado ----------
    def _draw_pdf(self):
        c = self.canvas_pdf
        c.clear()
        if self.state.pdf_page_image is None:
            c.redraw()
            return
        img = self.state.pdf_page_image
        c.ax.imshow(img, origin="upper")
        # Puntos de control
        for i, cp in enumerate(self.state.control_points, 1):
            u, v = cp.pdf_uv
            c.ax.plot(u, v, "o", color="red", markersize=8, markeredgecolor="white")
            c.ax.annotate(f"CP{i}", (u, v), color="red",
                          xytext=(6, 6), textcoords="offset points",
                          fontweight="bold")
        # Pendiente
        if self._pending_pdf_uv is not None:
            u, v = self._pending_pdf_uv
            c.ax.plot(u, v, "x", color="yellow", markersize=12, markeredgewidth=3)
        c.ax.set_xticks([])
        c.ax.set_yticks([])
        c.redraw()

    def _draw_map(self):
        c = self.canvas_map
        c.clear()
        if not self.state.centerlines:
            c.redraw()
            return
        # Bbox
        xs, ys = [], []
        for ln in self.state.centerlines:
            for x, y in ln.coords:
                xs.append(x); ys.append(y)
            xx, yy = zip(*ln.coords)
            c.ax.plot(xx, yy, "-", color="#2a5", linewidth=1.2)
        # Basemap OSM (contextily), en Web Mercator
        pad = 30
        c.ax.set_xlim(min(xs) - pad, max(xs) + pad)
        c.ax.set_ylim(min(ys) - pad, max(ys) + pad)
        if HAS_CTX:
            try:
                cx.add_basemap(c.ax, crs=f"EPSG:{WEB_MERC_EPSG}",
                               source=cx.providers.OpenStreetMap.Mapnik,
                               attribution_size=6)
            except Exception:
                pass
        # Puntos de control
        for i, cp in enumerate(self.state.control_points, 1):
            X, Y = cp.world_xy
            c.ax.plot(X, Y, "o", color="red", markersize=8, markeredgecolor="white")
            c.ax.annotate(f"CP{i}", (X, Y), color="red",
                          xytext=(6, 6), textcoords="offset points",
                          fontweight="bold")
        c.ax.set_xticks([])
        c.ax.set_yticks([])
        c.redraw()

    def _refresh_lists(self):
        self.lst_cp.clear()
        for i, cp in enumerate(self.state.control_points, 1):
            u, v = cp.pdf_uv
            X, Y = cp.world_xy
            item = QListWidgetItem(
                f"CP{i}   PDF({u:.0f},{v:.0f})  →  WM({X:.1f},{Y:.1f})"
            )
            self.lst_cp.addItem(item)


# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
