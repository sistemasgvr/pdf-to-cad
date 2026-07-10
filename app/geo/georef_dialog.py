"""
georef_dialog.py — Diálogo "Georreferenciar" (puntos de control PDF ↔ mapa).

Izquierda: el PDF actual (clic = punto en píxeles). Derecha: mapa Leaflet con
imagen satelital Esri (+ calles OSM) dentro de un QWebEngineView; clic = lon/lat.
Se emparejan N puntos (≥2 similarity, ≥3 affine), se convierte lon/lat→UTM con
pyproj y se ajusta la transformación píxel→UTM con scikit-image; se muestra el RMS.

Requiere PySide6-WebEngine (import a nivel de módulo) y, al calcular, pyproj/skimage.
"""
import json
import urllib.parse
import urllib.request

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

from geo import georef as georef_mod

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "pdf-to-cad-georef/1.0 (staff-engineering)"

MAP_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>html,body,#map{height:100%;margin:0}</style></head>
<body><div id="map"></div><script>
var map = L.map('map').setView([-12.05,-77.05], 12);
var esri = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {maxZoom:20, attribution:'Esri World Imagery'}).addTo(map);
var osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'OpenStreetMap'});
L.control.layers({'Satélite (Esri)':esri, 'Calles (OSM)':osm}).addTo(map);
var mk = null;
map.on('click', function(e){
    if (mk) { map.removeLayer(mk); }
    mk = L.marker(e.latlng).addTo(map);
    if (window.bridge) { window.bridge.mapClicked(e.latlng.lat, e.latlng.lng); }
});
function setView(lat, lon, z){ map.setView([lat, lon], z||17); if(mk){map.removeLayer(mk);} }
new QWebChannel(qt.webChannelTransport, function(ch){ window.bridge = ch.objects.bridge; });
</script></body></html>
"""


class _Bridge(QtCore.QObject):
    clickedMap = QtCore.Signal(float, float)

    @QtCore.Slot(float, float)
    def mapClicked(self, lat, lng):
        self.clickedMap.emit(lat, lng)


class _PdfView(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float)

    def __init__(self, qimg):
        super().__init__(); sc = QtWidgets.QGraphicsScene(self); self.setScene(sc)
        self._pm = sc.addPixmap(QtGui.QPixmap.fromImage(qimg))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(28, 28, 28))
        QtCore.QTimer.singleShot(0, lambda: self.fitInView(self._pm, QtCore.Qt.KeepAspectRatio))

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8; self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint()); self.clicked.emit(sp.x(), sp.y())
        super().mousePressEvent(e)

    def add_mark(self, x, y, color):
        pen = QtGui.QPen(QtGui.QColor(color)); pen.setCosmetic(True)
        it = self.scene().addEllipse(x - 5, y - 5, 10, 10, pen, QtGui.QBrush(QtGui.QColor(color)))
        return it


class GeorefDialog(QtWidgets.QDialog):
    def __init__(self, parent, qimg, init_georef=None):
        super().__init__(parent)
        self.setWindowTitle("Georreferenciar plano"); self.resize(1200, 760)
        self.result_georef = None
        self.pairs = []                 # [{"px":(x,y), "lonlat":(lon,lat), "mark":item}]
        self._pending_px = None; self._pending_mark = None

        root = QtWidgets.QVBoxLayout(self)
        warn = QtWidgets.QLabel("⚠ Calzar sobre imagen satelital da coordenadas APROXIMADAS (metros de "
                                "error): útil para trazado/anteproyecto, NO grado construcción. El dato "
                                "topográfico real proviene del levantamiento/Excel.")
        warn.setWordWrap(True); warn.setStyleSheet("color:#e0c060;"); root.addWidget(warn)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.pdf = _PdfView(qimg); self.pdf.clicked.connect(self._on_pdf_click); split.addWidget(self.pdf)
        right = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        srow = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit(); self.search.setPlaceholderText("Buscar dirección o lugar…")
        self.search.returnPressed.connect(self._do_search)
        b_search = QtWidgets.QPushButton("Buscar"); b_search.clicked.connect(self._do_search)
        srow.addWidget(self.search, 1); srow.addWidget(b_search); rv.addLayout(srow)
        self.web = QWebEngineView()
        self.bridge = _Bridge(); self.bridge.clickedMap.connect(self._on_map_click)
        self.channel = QWebChannel(); self.channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.web.setHtml(MAP_HTML, QtCore.QUrl("https://leafletjs.com/"))
        rv.addWidget(self.web, 1)
        split.addWidget(right); split.setSizes([560, 640]); root.addWidget(split, 1)

        self.hint = QtWidgets.QLabel("1) clic en un punto del PDF · 2) el MISMO punto en el mapa. "
                                     "Mínimo 2 pares (3–4 recomendado).")
        self.hint.setStyleSheet("color:#9cf;"); root.addWidget(self.hint)

        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(QtWidgets.QLabel("EPSG UTM:"))
        self.epsg = QtWidgets.QLineEdit(); self.epsg.setFixedWidth(90); self.epsg.setPlaceholderText("auto")
        if init_georef is not None and init_georef.epsg:
            self.epsg.setText(str(init_georef.epsg))
        crow.addWidget(self.epsg)
        self.b_calc = QtWidgets.QPushButton("Calcular ajuste"); self.b_calc.clicked.connect(self._compute)
        crow.addWidget(self.b_calc)
        self.lbl_rms = QtWidgets.QLabel("RMS: —"); crow.addWidget(self.lbl_rms, 1)
        b_del = QtWidgets.QPushButton("Borrar par seleccionado"); b_del.clicked.connect(self._del_pair)
        crow.addWidget(b_del)
        root.addLayout(crow)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "PDF (px)", "lon, lat"])
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setMaximumHeight(160)
        root.addWidget(self.table)

        self.bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        self.bb.accepted.connect(self.accept); self.bb.rejected.connect(self.reject); root.addWidget(self.bb)

        # precargar pares de una georref previa
        if init_georef is not None and init_georef.points:
            for p in init_georef.points:
                px = tuple(p.get("px", ()))
                ll = tuple(p.get("lonlat", ())) if p.get("lonlat") else None
                if len(px) == 2 and ll and len(ll) == 2:
                    m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
                    self.pairs.append({"px": px, "lonlat": ll, "mark": m})
            self._refresh_table()

    # ── puntos de control ──
    def _on_pdf_click(self, x, y):
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        self._pending_px = (x, y)
        self._pending_mark = self.pdf.add_mark(x, y, "#ff9a28")
        self.hint.setText("Punto del PDF fijado. Ahora haz clic en el MISMO punto en el mapa.")

    def _on_map_click(self, lat, lng):
        if self._pending_px is None:
            self.hint.setText("Primero haz clic en un punto del PDF, luego en el mapa."); return
        px = self._pending_px
        if self._pending_mark:                      # confirma el marcador (verde)
            self.pdf.scene().removeItem(self._pending_mark)
        self.pdf.add_mark(px[0], px[1], "#5fd35f")
        self.pairs.append({"px": px, "lonlat": (lng, lat), "mark": None})
        self._pending_px = None; self._pending_mark = None
        if not self.epsg.text().strip():
            self.epsg.setText(str(georef_mod.utm_epsg_from_lonlat(lng, lat)))
        self._refresh_table()
        self.hint.setText(f"{len(self.pairs)} par(es). Agrega más o pulsa 'Calcular ajuste'.")

    def _refresh_table(self):
        self.table.setRowCount(len(self.pairs))
        for r, p in enumerate(self.pairs):
            px = p["px"]; ll = p["lonlat"]
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(r + 1)))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(f"{px[0]:.1f}, {px[1]:.1f}"))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{ll[0]:.6f}, {ll[1]:.6f}"))

    def _del_pair(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.pairs):
            self.pairs.pop(r); self._refresh_table()

    # ── búsqueda Nominatim ──
    def _do_search(self):
        q = self.search.text().strip()
        if not q: return
        url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.load(resp)
        except Exception as e:
            self.hint.setText(f"Error de búsqueda: {e}"); return
        if not data:
            self.hint.setText("Sin resultados para esa búsqueda."); return
        lat = float(data[0]["lat"]); lon = float(data[0]["lon"])
        self.web.page().runJavaScript(f"setView({lat},{lon},17)")
        self.hint.setText("Mapa: " + str(data[0].get("display_name", ""))[:70])

    # ── ajuste ──
    def _compute(self):
        if len(self.pairs) < 2:
            QtWidgets.QMessageBox.information(self, "Faltan puntos", "Coloca al menos 2 pares de control."); return
        try:
            epsg = int(self.epsg.text().strip())
        except ValueError:
            QtWidgets.QMessageBox.information(self, "EPSG", "Indica un EPSG UTM válido (p. ej. 32718)."); return
        try:
            world = [georef_mod.lonlat_to_utm(ll[0], ll[1], epsg) for ll in (p["lonlat"] for p in self.pairs)]
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "pyproj", f"No se pudo reproyectar a UTM (¿falta pyproj?).\n\n{e}"); return
        px = [p["px"] for p in self.pairs]
        kind = "affine" if len(px) >= 3 else "similarity"
        try:
            matrix, rms, ttype = georef_mod.fit(px, world, kind=kind)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ajuste", f"No se pudo ajustar la transformación.\n\n{e}"); return
        pts = [{"px": list(p["px"]), "lonlat": list(p["lonlat"])} for p in self.pairs]
        self.result_georef = georef_mod.Georef(matrix=matrix, epsg=epsg, kind=ttype, rms=rms, points=pts)
        color = "#5fd35f" if rms <= 2.0 else "#e06060"
        self.lbl_rms.setText(f"RMS: {rms:.2f} m  ({ttype}, {len(px)} pts)")
        self.lbl_rms.setStyleSheet(f"color:{color};")
        if rms > 2.0:
            self.hint.setText("RMS alto (>2 m): revisa los pares o agrega más puntos bien repartidos.")
        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)
