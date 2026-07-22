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

# Geocodificador de Esri: a diferencia de Nominatim, SÍ resuelve intersecciones
# ("Calle A & Calle B"), que es como se ubican los planos de solo calles.
# findAddressCandidates sin token está permitido para visualización.
ESRI_GEOCODE = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
NOMINATIM = "https://nominatim.openstreetmap.org/search"   # respaldo (direcciones simples)
USER_AGENT = "pdf-to-cad-georef/1.0 (staff-engineering)"

MAP_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/esri-leaflet@3.0.12/dist/esri-leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>html,body,#map{height:100%;margin:0}</style></head>
<body><div id="map"></div><script>
var map = L.map('map').setView([34.20,-118.44], 12);   // San Fernando Valley, Los Ángeles
var esri = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {maxZoom:20, attribution:'Esri World Imagery'}).addTo(map);
var osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'OpenStreetMap'});
var bases = {'Satélite (Esri)':esri, 'Calles (OSM)':osm};

// ── Capas de referencia de la Ciudad de Los Ángeles (NavigateLA / Bureau of
// Engineering). Son opcionales: solo muestran datos dentro de LA y sirven para
// calzar contra geometría autoritativa (ejes de calle, parcelas, control
// geodésico) en vez de la imagen satelital aproximada. Requieren esri-leaflet;
// si la librería o el servicio no cargan, el mapa sigue funcionando igual.
var overlays = {};
var LA_BOE = 'https://maps.lacity.org/arcgis/rest/services/Mapping/NavigateLA/MapServer';
if (window.L && L.esri) {
    try {
        overlays['LA · Ejes de calle'] = L.esri.dynamicMapLayer({url: LA_BOE, layers:[337], opacity:0.9});
        overlays['LA · Parcelas']      = L.esri.dynamicMapLayer({url: LA_BOE, layers:[395], opacity:0.6});
        // Control geodésico: puntos CLICABLES (feature layers). Al hacer clic en un
        // monumento se envían sus coordenadas OFICIALES publicadas (X,Y en State
        // Plane CA Zona 5, pies — EPSG:2229) además de su lon/lat.
        var monStyle = function(feature, latlng){
            return L.circleMarker(latlng, {radius:5, color:'#ffd21e', weight:2,
                                           fillColor:'#ffd21e', fillOpacity:0.7});
        };
        var onMon = function(e){
            var p = e.layer.feature.properties || {};
            var ll = e.latlng;
            var X = parseFloat(p.X), Y = parseFloat(p.Y);
            var label = p.MapLabel || p.TOOLTIP || '';
            if (window.bridge && isFinite(X) && isFinite(Y)) {
                window.bridge.monumentClicked(X, Y, ll.lat, ll.lng, String(label));
            }
        };
        var ctrl = L.esri.featureLayer({url: LA_BOE + '/225', pointToLayer: monStyle});
        var bench = L.esri.featureLayer({url: LA_BOE + '/231', pointToLayer: monStyle});
        ctrl.on('click', onMon); bench.on('click', onMon);
        overlays['LA · Control geodésico (clic = coord oficial)'] = ctrl;
        overlays['LA · Benchmarks'] = bench;
    } catch(err) { /* sin capas LA si algo falla */ }
}
L.control.layers(bases, overlays).addTo(map);
var mk = null;
map.on('click', function(e){
    if (mk) { map.removeLayer(mk); }
    mk = L.marker(e.latlng).addTo(map);
    if (window.bridge) { window.bridge.mapClicked(e.latlng.lat, e.latlng.lng); }
});
function setView(lat, lon, z){ map.setView([lat, lon], z||17); if(mk){map.removeLayer(mk);} }
var searchPin = null;
// Deja un pin naranja en el resultado de búsqueda (p. ej. una intersección),
// sin contar como punto de control: solo ayuda a ubicar el sitio a ojo.
function dropPin(lat, lon, z){
    map.setView([lat, lon], z||18);
    if (searchPin) { map.removeLayer(searchPin); }
    searchPin = L.circleMarker([lat, lon], {radius:8, color:'#ff7a00', weight:3,
                                            fillColor:'#ff7a00', fillOpacity:0.3}).addTo(map);
    searchPin.bindPopup('Intersección buscada').openPopup();
}
new QWebChannel(qt.webChannelTransport, function(ch){ window.bridge = ch.objects.bridge; });
</script></body></html>
"""


class _Bridge(QtCore.QObject):
    clickedMap = QtCore.Signal(float, float)
    clickedMonument = QtCore.Signal(float, float, float, float, str)   # X, Y (2229 ft), lat, lng, label

    @QtCore.Slot(float, float)
    def mapClicked(self, lat, lng):
        self.clickedMap.emit(lat, lng)

    @QtCore.Slot(float, float, float, float, str)
    def monumentClicked(self, x, y, lat, lng, label):
        self.clickedMonument.emit(x, y, lat, lng, label)


class _PdfView(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float)
    guide = QtCore.Signal()                     # clic derecho → abre la guía

    def __init__(self, qimg):
        super().__init__(); sc = QtWidgets.QGraphicsScene(self); self.setScene(sc)
        self._pm = sc.addPixmap(QtGui.QPixmap.fromImage(qimg))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(28, 28, 28))
        self.setToolTip("Clic izquierdo: fija el punto de control · Rueda: zoom · Clic derecho: guía de uso")
        QtCore.QTimer.singleShot(0, lambda: self.fitInView(self._pm, QtCore.Qt.KeepAspectRatio))

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8; self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint()); self.clicked.emit(sp.x(), sp.y())
        elif e.button() == QtCore.Qt.RightButton:
            self.guide.emit(); return           # no propaga: el clic derecho abre la guía
        super().mousePressEvent(e)

    def add_mark(self, x, y, color):
        pen = QtGui.QPen(QtGui.QColor(color)); pen.setCosmetic(True)
        it = self.scene().addEllipse(x - 5, y - 5, 10, 10, pen, QtGui.QBrush(QtGui.QColor(color)))
        return it


class GeorefDialog(QtWidgets.QDialog):
    def __init__(self, parent, qimg, init_georef=None):
        super().__init__(parent)
        self._main = parent                     # ventana principal (para scale/zoom/pdf_path)
        self._qimg = qimg                       # imagen del plano (para el modo Superponer)
        self.setWindowTitle("Georreferenciar plano"); self.resize(1200, 760)
        self.result_georef = None
        self._overlay = None                    # OverlayView del modo Superponer (perezoso)
        # Cada par: {"px":(x,y), "lonlat":(lon,lat), "world":(X,Y)|None,
        #            "kind":"map"|"mon", "label":str, "mark":item}
        # kind="mon" = clic en un monumento de NavigateLA → "world" trae la
        # coordenada OFICIAL en State Plane CA Zona 5 (EPSG:2229, pies).
        self.pairs = []
        self._pending_px = None; self._pending_mark = None
        self._search_loc = None       # (lon, lat, label) del último resultado de búsqueda
        self._residuals = []          # error por punto (unidades del CRS) tras el último ajuste

        root = QtWidgets.QVBoxLayout(self)
        warn = QtWidgets.QLabel("⚠ Calzar sobre imagen satelital da coordenadas APROXIMADAS (metros de "
                                "error): útil para trazado/anteproyecto, NO grado construcción. El dato "
                                "topográfico real proviene del levantamiento/Excel.")
        warn.setWordWrap(True); warn.setStyleSheet("color:#e0c060;"); root.addWidget(warn)

        # Banner de estado: si el plano YA venía georreferenciado, se avisa arriba.
        self.lbl_prev = QtWidgets.QLabel(""); self.lbl_prev.setWordWrap(True)
        if init_georef is not None and init_georef.active():
            unit = georef_mod.epsg_unit(init_georef.epsg)
            rms = f", RMS {init_georef.rms:.2f} {unit}" if init_georef.rms is not None else ""
            self.lbl_prev.setText(f"✓ Este plano YA está georreferenciado (EPSG:{init_georef.epsg}{rms}). "
                                  "Puedes recalcular con nuevos puntos o cerrar sin cambios.")
            self.lbl_prev.setStyleSheet("color:#5fd35f;font-weight:bold;")
            root.addWidget(self.lbl_prev)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.pdf = _PdfView(qimg); self.pdf.clicked.connect(self._on_pdf_click)
        self.pdf.guide.connect(self._show_guide); split.addWidget(self.pdf)
        right = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        srow = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Buscar calle o intersección… ej: Chandler & Colfax")
        self.search.returnPressed.connect(self._do_search)
        b_search = QtWidgets.QPushButton("Buscar"); b_search.clicked.connect(self._do_search)
        b_use = QtWidgets.QPushButton("Usar como punto")
        b_use.setToolTip("Empareja el punto fijado en el PDF con la coordenada EXACTA de la "
                         "intersección buscada (sin apuntar a ojo en el mapa).")
        b_use.clicked.connect(self._use_search_point)
        srow.addWidget(self.search, 1); srow.addWidget(b_search); srow.addWidget(b_use); rv.addLayout(srow)
        self.web = QWebEngineView()
        self.bridge = _Bridge(); self.bridge.clickedMap.connect(self._on_map_click)
        self.bridge.clickedMonument.connect(self._on_monument_click)
        self.channel = QWebChannel(); self.channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.web.setHtml(MAP_HTML, QtCore.QUrl("https://leafletjs.com/"))
        rv.addWidget(self.web, 1)

        # Panel derecho con pestañas: MAPA (satélite/monumentos) o DWG de
        # referencia (Nivel 3: calzar contra un plano ya en coordenadas reales).
        self.ref_tabs = QtWidgets.QTabWidget()
        self.ref_tabs.addTab(right, "Mapa")
        dwg_tab = QtWidgets.QWidget(); dl = QtWidgets.QVBoxLayout(dwg_tab); dl.setContentsMargins(0, 0, 0, 0)
        drow = QtWidgets.QHBoxLayout()
        b_dwg = QtWidgets.QPushButton("Cargar DWG/DXF de referencia…"); b_dwg.clicked.connect(self._load_dwg)
        drow.addWidget(b_dwg); drow.addStretch(1); dl.addLayout(drow)
        self.lbl_dwg = QtWidgets.QLabel("<i>Carga un DXF (o DWG con ODA) que ya esté en coordenadas reales. "
                                        "Luego: clic en el PDF y clic en el MISMO punto del dibujo → "
                                        "coordenada real directa (grado topográfico).</i>")
        self.lbl_dwg.setWordWrap(True); dl.addWidget(self.lbl_dwg)
        self._dwg_slot = QtWidgets.QVBoxLayout(); dl.addLayout(self._dwg_slot, 1)
        self._dwg_view = None
        self.ref_tabs.addTab(dwg_tab, "DWG referencia")

        # ── Pestaña: Superponer (colocar el PDF sobre las calles reales) ──
        ov_tab = QtWidgets.QWidget(); ol = QtWidgets.QVBoxLayout(ov_tab); ol.setContentsMargins(0, 0, 0, 0)
        orow = QtWidgets.QHBoxLayout()
        self.ov_search = QtWidgets.QLineEdit(); self.ov_search.setPlaceholderText("Zona/intersección… ej: Chandler & Colfax")
        self.ov_search.returnPressed.connect(self._overlay_search)
        ob = QtWidgets.QPushButton("Cargar calles"); ob.clicked.connect(self._overlay_search)
        orow.addWidget(self.ov_search, 1); orow.addWidget(ob); ol.addLayout(orow)
        crow2 = QtWidgets.QHBoxLayout()
        # escala: pasos gruesos (±5%) y finos (±1%) para calzar sin pasarse
        for txt, fn, tip in (("－－", lambda: self._ov(lambda v: v.scale_image(0.95)), "Reducir 5%"),
                             ("－", lambda: self._ov(lambda v: v.scale_image(0.99)), "Reducir 1% (fino)"),
                             ("＋", lambda: self._ov(lambda v: v.scale_image(1.01)), "Agrandar 1% (fino)"),
                             ("＋＋", lambda: self._ov(lambda v: v.scale_image(1.05)), "Agrandar 5%"),
                             ("⟲", lambda: self._ov(lambda v: v.rotate_image(-1)), "Rotar −1°"),
                             ("⟳", lambda: self._ov(lambda v: v.rotate_image(1)), "Rotar +1°"),
                             ("⟲⟲", lambda: self._ov(lambda v: v.rotate_image(-10)), "Rotar −10°"),
                             ("⟳⟳", lambda: self._ov(lambda v: v.rotate_image(10)), "Rotar +10°")):
            b = QtWidgets.QPushButton(txt); b.setFixedWidth(40); b.setToolTip(tip); b.clicked.connect(fn); crow2.addWidget(b)
        b_align = QtWidgets.QPushButton("🎯 Calce por puntos"); b_align.setToolTip(
            "Clic en un punto del PLANO y luego su gemelo en la CALLE real. Repite con VARIOS puntos "
            "bien separados (más puntos = más preciso). Pulsa este botón otra vez para terminar.")
        b_align.clicked.connect(self._overlay_start_align); crow2.addWidget(b_align)
        crow2.addWidget(QtWidgets.QLabel("Opacidad:"))
        self.ov_op = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.ov_op.setRange(10, 100); self.ov_op.setValue(60)
        self.ov_op.valueChanged.connect(lambda v: self._ov(lambda ov: ov.set_img_opacity(v / 100.0)))
        crow2.addWidget(self.ov_op, 1); ol.addLayout(crow2)
        self.lbl_ov = QtWidgets.QLabel("<i>1) Carga las calles de la zona · 2) arrastra la imagen y usa "
                                       "±/⟲⟳ para acomodarla sobre las calles reales · 3) «Usar superposición».</i>")
        self.lbl_ov.setWordWrap(True); ol.addWidget(self.lbl_ov)
        self._ov_slot = QtWidgets.QVBoxLayout(); ol.addLayout(self._ov_slot, 1)
        b_ov_use = QtWidgets.QPushButton("✓ Usar superposición como georreferencia"); b_ov_use.clicked.connect(self._overlay_apply)
        ol.addWidget(b_ov_use)
        self.ref_tabs.addTab(ov_tab, "Superponer")

        split.addWidget(self.ref_tabs); split.setSizes([560, 640]); root.addWidget(split, 1)

        self.hint = QtWidgets.QLabel("1) clic en un punto del PDF · 2) el MISMO punto en el mapa "
                                     "(o en un monumento amarillo de LA = coordenada oficial). "
                                     "Mínimo 2 pares (3–4 recomendado).")
        self.hint.setStyleSheet("color:#9cf;"); root.addWidget(self.hint)

        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(QtWidgets.QLabel("EPSG:"))
        self.epsg = QtWidgets.QLineEdit(); self.epsg.setFixedWidth(90); self.epsg.setPlaceholderText("auto")
        self.epsg.setToolTip("UTM WGS84 (auto por lon/lat) o State Plane. LA usa EPSG:2229 (pies). "
                             "Al usar monumentos oficiales se fija 2229 automáticamente.")
        if init_georef is not None and init_georef.epsg:
            self.epsg.setText(str(init_georef.epsg))
        crow.addWidget(self.epsg)
        self.b_calc = QtWidgets.QPushButton("Calcular ajuste"); self.b_calc.clicked.connect(self._compute)
        crow.addWidget(self.b_calc)
        self.lbl_rms = QtWidgets.QLabel("RMS: —"); crow.addWidget(self.lbl_rms, 1)
        b_del = QtWidgets.QPushButton("Borrar par seleccionado"); b_del.clicked.connect(self._del_pair)
        b_del.setToolTip("Quita el par seleccionado (o el último) y su marca del PDF.")
        crow.addWidget(b_del)
        b_help = QtWidgets.QPushButton("❓ Guía"); b_help.clicked.connect(self._show_guide)
        b_help.setToolTip("Cómo georreferenciar paso a paso (también con clic derecho).")
        crow.addWidget(b_help)
        root.addLayout(crow)

        # Mensaje de suficiencia: dice si ya hay puntos bastantes para georeferenciar.
        self.lbl_status = QtWidgets.QLabel(""); self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "PDF (px)", "Referencia", "Origen", "Error"])
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setMaximumHeight(160)
        self.table.setToolTip("La columna Error (tras Calcular) muestra cuánto se desvía cada punto. "
                              "Borra el de mayor error y recalcula para afinar.")
        root.addWidget(self.table)

        self.bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        self.bb.accepted.connect(self.accept); self.bb.rejected.connect(self.reject); root.addWidget(self.bb)

        # precargar pares de una georref previa
        if init_georef is not None and init_georef.points:
            for p in init_georef.points:
                px = tuple(p.get("px", ()))
                ll = tuple(p.get("lonlat", ())) if p.get("lonlat") else None
                wd = tuple(p.get("world", ())) if p.get("world") else None
                if len(px) == 2 and ((ll and len(ll) == 2) or (wd and len(wd) == 2)):
                    m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
                    self.pairs.append({"px": px, "lonlat": ll, "world": wd,
                                       "kind": p.get("kind", "mon" if wd else "map"),
                                       "label": p.get("label", ""), "mark": m})
            self._refresh_table()
        self._update_status()

    # ── guía / tutorial ──
    _GUIDE_HTML = """
    <h3>Cómo georreferenciar el plano</h3>
    <p>Objetivo: decirle al programa a qué punto real corresponde cada punto del
    plano. Con 3–4 puntos calcula la fórmula y todo lo que dibujes sale en
    coordenadas reales.</p>
    <p><b>Elige una fuente de coordenadas (de más a menos precisa):</b></p>
    <ol>
      <li><b>DWG de referencia</b> (grado topográfico) — pestaña <i>DWG referencia</i> →
          <i>Cargar DWG/DXF…</i>. Clic en el punto del PDF y luego en el MISMO punto del dibujo.</li>
      <li><b>Monumento oficial</b> — en <i>Mapa</i> activa <i>«LA · Control geodésico»</i>.
          Clic en el punto del PDF y luego en el punto amarillo → coordenada oficial (EPSG:2229).</li>
      <li><b>Intersección de calles</b> (planos de solo calles) — escribe
          <i>«Calle A &amp; Calle B»</i> en Buscar → cae un pin en el nodo exacto. Clic en esa
          esquina del PDF → botón <i>«Usar como punto»</i>.</li>
      <li><b>Clic en el mapa</b> (aproximado) — clic en el PDF y luego a ojo en el mapa.</li>
    </ol>
    <p><b>Pasos:</b></p>
    <ol>
      <li>Repite hasta tener <b>3–4 puntos</b> bien repartidos (esquinas del plano).</li>
      <li>Cuando el mensaje diga <b>«suficientes»</b>, pulsa <b>«Calcular ajuste»</b>.</li>
      <li>Mira la columna <b>Error</b>: si un punto sale en <span style="color:#e06060">rojo</span>,
          bórralo y recalcula.</li>
      <li><b>Aceptar</b> → aparece «Plano georreferenciado».</li>
    </ol>
    <p><i>Consejo: puntos en las 4 esquinas dan mejor ajuste que 2 juntos. El clic
    derecho abre esta guía en cualquier momento.</i></p>
    """

    def contextMenuEvent(self, e):
        menu = QtWidgets.QMenu(self)
        act = menu.addAction("📖  Cómo georreferenciar (guía)")
        act.triggered.connect(self._show_guide)
        menu.exec(e.globalPos())

    def _show_guide(self):
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Guía · Georreferenciar"); dlg.resize(580, 560)
        lay = QtWidgets.QVBoxLayout(dlg)
        tb = QtWidgets.QTextBrowser(); tb.setHtml(self._GUIDE_HTML); lay.addWidget(tb)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); bb.accepted.connect(dlg.accept); lay.addWidget(bb)
        dlg.exec()

    def _update_status(self):
        """Actualiza el mensaje de suficiencia y habilita 'Calcular ajuste'
        solo cuando hay al menos 2 puntos de control."""
        n = len(self.pairs)
        self.b_calc.setEnabled(n >= 2)
        if n == 0:
            msg, color = "Aún sin puntos. Coloca al menos 2 (3–4 recomendado).", "#9cf"
        elif n == 1:
            msg, color = "1 punto · falta al menos 1 más para poder georeferenciar.", "#e0c060"
        elif n == 2:
            msg, color = ("✓ 2 puntos: SUFICIENTES para georeferenciar (ajuste simple). "
                          "Con 3–4 mejora. Pulsa «Calcular ajuste».", "#5fd35f")
        else:
            msg, color = (f"✓ {n} puntos: SUFICIENTES (ajuste afín, recomendado). "
                          "Pulsa «Calcular ajuste».", "#5fd35f")
        self.lbl_status.setText(msg); self.lbl_status.setStyleSheet(f"color:{color};font-weight:bold;")

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
        m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
        self.pairs.append({"px": px, "lonlat": (lng, lat), "world": None,
                           "kind": "map", "label": "", "mark": m})
        self._pending_px = None; self._pending_mark = None
        if not self.epsg.text().strip():
            # En el área de Los Ángeles usamos State Plane 2229 (pies) para que
            # todas las hojas queden en el mismo CRS que los DWG del proyecto;
            # en otras zonas, el UTM WGS84 que corresponda por lon/lat.
            in_la = (-119.5 <= lng <= -117.0) and (33.0 <= lat <= 35.0)
            self.epsg.setText("2229" if in_la else str(georef_mod.utm_epsg_from_lonlat(lng, lat)))
        self._refresh_table()

    def _on_monument_click(self, x, y, lat, lng, label):
        """Clic en un monumento de NavigateLA: usa su coordenada OFICIAL (X,Y en
        EPSG:2229, pies) como referencia — grado topográfico, sin pasar por el
        satélite. Necesita un punto del PDF fijado previamente."""
        if self._pending_px is None:
            self.hint.setText("Primero fija el punto en el PDF; luego clic en el monumento."); return
        px = self._pending_px
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
        self.pairs.append({"px": px, "lonlat": (lng, lat), "world": (x, y),
                           "kind": "mon", "label": label or "", "mark": m})
        self._pending_px = None; self._pending_mark = None
        if not self.epsg.text().strip():
            self.epsg.setText("2229")               # monumentos de LA → State Plane CA Zona 5 (pies)
        self._refresh_table()
        self.hint.setText(f"{len(self.pairs)} par(es) · monumento oficial agregado. "
                          "Agrega más o pulsa 'Calcular ajuste'.")

    def _use_search_point(self):
        """Empareja el punto fijado en el PDF con la coordenada EXACTA de la
        intersección buscada (geocoder), evitando el error de apuntar a ojo en
        el mapa. Es la vía más precisa cuando no hay monumentos cerca."""
        if self._search_loc is None:
            QtWidgets.QMessageBox.information(self, "Usar como punto",
                "Primero busca una calle o intersección en el cuadro de arriba "
                "(por ejemplo: Chandler & Colfax) y pulsa «Buscar»."); return
        if self._pending_px is None:
            QtWidgets.QMessageBox.information(self, "Usar como punto",
                "Primero haz clic en el punto del PDF (verás una marca naranja) "
                "y luego pulsa «Usar como punto»."); return
        lon, lat, label = self._search_loc
        px = self._pending_px
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
        self.pairs.append({"px": px, "lonlat": (lon, lat), "world": None,
                           "kind": "geo", "label": label or "", "mark": m})
        self._pending_px = None; self._pending_mark = None
        if not self.epsg.text().strip():
            in_la = (-119.5 <= lon <= -117.0) and (33.0 <= lat <= 35.0)
            self.epsg.setText("2229" if in_la else str(georef_mod.utm_epsg_from_lonlat(lon, lat)))
        self._refresh_table()
        self.hint.setText(f"Punto emparejado con «{label[:50]}» (intersección exacta).")

    # ── Superponer (colocar el PDF sobre las calles reales) ──
    def _ov(self, fn):
        """Ejecuta fn(overlay_view) si el visor de superposición ya existe."""
        if self._overlay is not None:
            fn(self._overlay)

    def _overlay_search(self):
        """Geocodifica la zona, descarga las calles reales (2229) y coloca la
        imagen del PDF encima para acomodarla."""
        q = self.ov_search.text().strip()
        if not q:
            return
        loc = self._geocode(self._norm_query(q))
        if loc is None:
            self.lbl_ov.setText("No se encontró la zona. Prueba «Calle A & Calle B»."); return
        lat, lon, _label = loc
        ref = self._refine_intersection(self._norm_query(q), lon, lat)
        if ref is not None:
            lon, lat = ref
        try:
            cx, cy = georef_mod.lonlat_to_utm(lon, lat, 2229)      # centro en 2229 (pies)
            from geo.la_reference import fetch_streets_2229, fetch_parcels_2229
            segs = fetch_streets_2229(cx, cy)
            parcels = fetch_parcels_2229(cx, cy)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Superponer",
                f"No se pudieron traer las calles (¿internet/pyproj?).\n\n{e}"); return
        if self._overlay is None:                                  # crea el visor la primera vez
            from geo.overlay import OverlayView
            scale = getattr(self._main, "scale", 20 / 72.0); zoom = getattr(self._main, "zoom", 3.5) or 3.5
            self._overlay = OverlayView(self._qimg, feet_per_pixel=scale / zoom)
            self._overlay.alignHint.connect(self.lbl_ov.setText)
            self._ov_slot.addWidget(self._overlay)
        self._overlay.set_origin(cx, cy)                           # escena local (evita coords en millones)
        self._overlay.set_reference(segs, parcels=parcels, marker=(cx, cy))
        self._overlay.set_initial_size(900)                        # arranca visible (~900 ft); se calza luego
        self._overlay.place_at(cx, cy)
        if not self.epsg.text().strip():
            self.epsg.setText("2229")
        if not segs:                                               # geocodificó fuera de la Ciudad de LA
            self.lbl_ov.setText("⚠ No llegaron calles en esa zona (¿la búsqueda cayó fuera de LA?). "
                                "Escribe la intersección como «Calle A & Calle B» e inténtalo de nuevo.")
        else:
            self.lbl_ov.setText(f"✓ {len(segs)} calles cargadas (círculo rojo = intersección). Acomoda con "
                                "arrastrar y ±/⟲⟳, o usa «🎯 Calce por puntos» (varios, bien separados).")

    def _overlay_start_align(self):
        if self._overlay is None:
            QtWidgets.QMessageBox.information(self, "Superponer", "Primero carga las calles de la zona."); return
        if self._overlay.is_aligning():        # segundo clic al botón = terminar el calce
            self._overlay.finish_align()
        else:
            self._overlay.start_align()

    def _overlay_apply(self):
        """Deriva la georreferencia de la ubicación actual de la imagen superpuesta."""
        if self._overlay is None:
            QtWidgets.QMessageBox.information(self, "Superponer", "Primero carga las calles de la zona."); return
        gp = self._overlay.georef_points()
        px = [p for p, _ in gp]; world = [w for _, w in gp]
        try:
            matrix, rms, ttype = georef_mod.fit(px, world, kind="affine")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Superponer", f"No se pudo ajustar.\n\n{e}"); return
        pts = [{"px": list(p), "lonlat": None, "world": list(w), "kind": "overlay", "label": ""}
               for (p, w) in gp]
        self.result_georef = georef_mod.Georef(matrix=matrix, epsg=2229, kind=ttype, rms=rms, points=pts)
        self.lbl_rms.setText(f"RMS: {rms:.2f} ft  (superposición)")
        self.lbl_rms.setStyleSheet("color:#5fd35f;")
        self.lbl_ov.setText("✓ Georreferencia por superposición lista. Pulsa Aceptar. "
                            "Verifica con la capa REF_LA_CALLES al exportar.")
        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)

    # ── DWG/DXF de referencia (Nivel 3) ──
    def _load_dwg(self):
        import os
        from geo.dwg_ref import load_reference, DxfRefView
        start = os.path.dirname(self._main.pdf_path) if getattr(self._main, "pdf_path", None) else ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Cargar DWG/DXF de referencia", start, "CAD (*.dxf *.dwg)")
        if not path:
            return
        try:
            segs, bounds = load_reference(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "DWG/DXF de referencia", str(e)); return
        if self._dwg_view is not None:                    # reemplaza un dibujo anterior
            self._dwg_view.setParent(None); self._dwg_view.deleteLater()
        self._dwg_view = DxfRefView(segs, bounds)
        self._dwg_view.worldClicked.connect(self._on_dxf_click)
        self._dwg_slot.addWidget(self._dwg_view)
        import os as _os
        self.lbl_dwg.setText(f"<b>{_os.path.basename(path)}</b> · clic en el PDF y luego en el MISMO punto "
                             "del dibujo. Ajusta el EPSG si el DWG no está en 2229.")
        if not self.epsg.text().strip():
            self.epsg.setText("2229")                     # asunción por defecto (LA / DWG del proyecto)

    def _on_dxf_click(self, wx, wy):
        """Clic en el DWG de referencia: usa su coordenada REAL directa. Requiere
        un punto del PDF fijado. Es la vía más precisa (grado topográfico)."""
        if self._pending_px is None:
            QtWidgets.QMessageBox.information(self, "DWG de referencia",
                "Primero haz clic en el punto del PDF (marca naranja) y luego en el mismo punto del dibujo."); return
        px = self._pending_px
        if self._pending_mark:
            self.pdf.scene().removeItem(self._pending_mark)
        m = self.pdf.add_mark(px[0], px[1], "#5fd35f")
        self.pairs.append({"px": px, "lonlat": None, "world": (wx, wy),
                           "kind": "dwg", "label": "DWG", "mark": m})
        self._pending_px = None; self._pending_mark = None
        self._refresh_table()
        self.hint.setText(f"{len(self.pairs)} par(es) · punto del DWG agregado "
                          f"(X={wx:.2f}, Y={wy:.2f}). Agrega más o pulsa «Calcular ajuste».")

    def _refresh_table(self):
        self.table.setRowCount(len(self.pairs))
        # El error por punto solo se muestra si corresponde al conjunto actual
        # (mismo número de pares que el último ajuste); si cambiaron, se oculta.
        show_res = len(self._residuals) == len(self.pairs) and bool(self.pairs)
        try:
            unit = georef_mod.epsg_unit(int(self.epsg.text().strip()))
        except Exception:
            unit = "m"
        thr = 3.0 if unit == "ft" else 2.0
        for r, p in enumerate(self.pairs):
            px = p["px"]; kind = p.get("kind")
            if kind in ("mon", "dwg") and p.get("world"):
                ref = f"X={p['world'][0]:.2f}  Y={p['world'][1]:.2f}"
                origen = "Monumento LA (2229)" if kind == "mon" else "DWG referencia"
            elif kind == "geo":
                ll = p["lonlat"]; ref = f"{ll[0]:.6f}, {ll[1]:.6f}"; origen = "Intersección (buscador)"
            else:
                ll = p["lonlat"]; ref = f"{ll[0]:.6f}, {ll[1]:.6f}"; origen = "Mapa (clic)"
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(r + 1)))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(f"{px[0]:.1f}, {px[1]:.1f}"))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(ref))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(origen))
            err_item = QtWidgets.QTableWidgetItem(f"{self._residuals[r]:.2f} {unit}" if show_res else "—")
            if show_res and self._residuals[r] > thr:
                err_item.setForeground(QtGui.QColor("#e06060"))     # punto sospechoso: mucho error
            self.table.setItem(r, 4, err_item)
        self._update_status()

    def _del_pair(self):
        r = self.table.currentRow()
        if r < 0 and self.pairs:            # sin selección: borra el último agregado
            r = len(self.pairs) - 1
        if 0 <= r < len(self.pairs):
            p = self.pairs.pop(r)
            if p.get("mark") is not None:   # quita también su punto del PDF
                self.pdf.scene().removeItem(p["mark"])
            self._residuals = []            # el error por punto queda obsoleto
            self._refresh_table()

    # ── búsqueda Nominatim ──
    @staticmethod
    def _norm_query(q):
        """Normaliza búsquedas de intersección: 'Chandler cruce con Colfax',
        'CHANDLER Y COLFAX', 'Chandler and Colfax' → 'Chandler & Colfax'.
        Insensible a mayúsculas. Si no menciona ciudad, añade Los Ángeles."""
        import re
        s = q
        for sep in (" cruce con ", " esquina con ", " con ", " y ", " and ", " x "):
            s = re.sub(re.escape(sep), " & ", s, flags=re.IGNORECASE)
        low = s.lower()
        if not any(c in low for c in ("los angeles", "los ángeles", ", ca", ", california")):
            s = s + ", Los Angeles, CA"
        return s

    def _do_search(self):
        q = self.search.text().strip()
        if not q: return
        query = self._norm_query(q)
        loc = self._geocode(query)
        if loc is None:
            self.hint.setText(f"Sin resultados para «{query}». Prueba 'Calle A & Calle B'."); return
        lat, lon, label = loc
        # Si es intersección, intenta refinar al NODO EXACTO de los ejes de calle
        # de NavigateLA (más autoritativo que el geocoder). Si no, usa el geocoder.
        refined = self._refine_intersection(query, lon, lat)
        if refined is not None:
            lon, lat = refined
            label = f"{label.split(',')[0]} · nodo exacto (ejes LA)"
        self._search_loc = (lon, lat, label)     # disponible para «Usar como punto»
        self.web.page().runJavaScript(f"dropPin({lat},{lon},18)")
        self.hint.setText(f"Intersección: {label[:60]} · clic en el PDF y luego «Usar como punto» "
                          "(exacto) o clic en el mapa.")

    def _geocode(self, query):
        """Devuelve (lat, lon, label) usando el geocodificador de Esri (resuelve
        intersecciones); si falla, cae a Nominatim (solo direcciones simples).
        Devuelve None si no hay resultado."""
        try:
            url = ESRI_GEOCODE + "?" + urllib.parse.urlencode(
                {"SingleLine": query, "f": "json", "maxLocations": 1, "outFields": "Match_addr"})
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.load(resp)
            cands = data.get("candidates", [])
            if cands:
                loc = cands[0]["location"]
                return float(loc["y"]), float(loc["x"]), cands[0].get("address", query)
        except Exception:
            pass
        try:                                    # respaldo Nominatim
            url = NOMINATIM + "?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.load(resp)
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", query)
        except Exception as e:
            self.hint.setText(f"Error de búsqueda: {e}")
        return None

    # ── intersección EXACTA desde los ejes de calle de NavigateLA (capa 337) ──
    _CL_URL = "https://maps.lacity.org/arcgis/rest/services/Mapping/NavigateLA/MapServer/337/query"
    _ST_SUFFIX = {"AVE", "AVENUE", "BLVD", "BOULEVARD", "ST", "STREET", "DR", "DRIVE",
                  "PL", "PLACE", "WAY", "RD", "ROAD", "LN", "LANE", "CT", "COURT",
                  "PKWY", "PARKWAY", "TER", "TERRACE", "CYN", "CANYON"}

    @classmethod
    def _street_stname(cls, side):
        """De 'Chandler Blvd' → 'CHANDLER'; de 'Van Nuys Blvd' → 'VAN NUYS'."""
        toks = side.strip().upper().replace(".", "").split()
        while toks and toks[-1] in cls._ST_SUFFIX:
            toks.pop()
        return " ".join(toks)

    @staticmethod
    def _seg_intersect(p1, p2, p3, p4):
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p1, p2, p3, p4
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-15:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        return None

    def _centerline_segs(self, stname, lon, lat, d=0.012):
        bbox = f"{lon - d},{lat - d},{lon + d},{lat + d}"
        p = {"where": f"STNAME='{stname}'", "geometry": bbox, "geometryType": "esriGeometryEnvelope",
             "inSR": "4326", "spatialRel": "esriSpatialRelIntersects", "outFields": "STNAME",
             "returnGeometry": "true", "outSR": "4326", "f": "json"}
        url = self._CL_URL + "?" + urllib.parse.urlencode(p)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        segs = []
        for f in data.get("features", []):
            for path in f.get("geometry", {}).get("paths", []):
                for i in range(len(path) - 1):
                    segs.append((path[i], path[i + 1]))
        return segs

    def _refine_intersection(self, query, lon, lat):
        """Si `query` es una intersección 'A & B', busca el nodo EXACTO donde se
        cruzan los ejes de calle de NavigateLA (más cercano al punto geocodificado).
        Devuelve (lon, lat) o None si no aplica/no se encuentra. Nunca lanza."""
        if " & " not in query:
            return None
        left, rest = query.split(" & ", 1)
        right = rest.split(",", 1)[0]
        a, b = self._street_stname(left), self._street_stname(right)
        if not a or not b:
            return None
        try:
            A = self._centerline_segs(a, lon, lat)
            B = self._centerline_segs(b, lon, lat)
            pts = []
            for s1 in A:
                for s2 in B:
                    r = self._seg_intersect(s1[0], s1[1], s2[0], s2[1])
                    if r:
                        pts.append(r)
            if not pts:
                return None
            return min(pts, key=lambda p: (p[0] - lon) ** 2 + (p[1] - lat) ** 2)   # el más cercano al geocoder
        except Exception:
            return None

    # ── ajuste ──
    def _compute(self):
        if len(self.pairs) < 2:
            QtWidgets.QMessageBox.information(self, "Faltan puntos", "Coloca al menos 2 pares de control."); return
        try:
            epsg = int(self.epsg.text().strip())
        except ValueError:
            QtWidgets.QMessageBox.information(self, "EPSG", "Indica un EPSG válido (UTM, p. ej. 32611, o State Plane 2229)."); return
        # Cada punto de control se lleva al MISMO CRS de destino (epsg):
        #   - monumento (kind="mon") y epsg==2229 → coordenada oficial X,Y directa
        #     (grado topográfico, sin reproyectar).
        #   - resto → reproyecta su lon/lat a epsg con pyproj.
        world = []
        try:
            for p in self.pairs:
                kind = p.get("kind")
                # DWG y monumento-2229 ya vienen en el CRS de destino → directo.
                if kind == "dwg" and p.get("world"):
                    world.append(tuple(p["world"]))
                elif kind == "mon" and p.get("world") and epsg == 2229:
                    world.append(tuple(p["world"]))
                else:
                    ll = p.get("lonlat")
                    if not ll:
                        raise ValueError("Un punto sin lon/lat no se puede reproyectar; "
                                         "usa EPSG:2229 (monumentos) o recoloca ese punto.")
                    world.append(georef_mod.lonlat_to_utm(ll[0], ll[1], epsg))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Reproyección",
                                          f"No se pudo llevar los puntos al EPSG:{epsg} (¿falta pyproj?).\n\n{e}"); return
        px = [p["px"] for p in self.pairs]
        kind = "affine" if len(px) >= 3 else "similarity"
        try:
            matrix, rms, ttype = georef_mod.fit(px, world, kind=kind)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ajuste", f"No se pudo ajustar la transformación.\n\n{e}"); return
        # Detección de ESPEJO: con píxel-Y hacia abajo y Norte hacia arriba, un
        # ajuste correcto tiene determinante NEGATIVO. Positivo = plano espejado
        # (típico con puntos de control casi en línea, o un par cruzado).
        det = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
        if det > 0:
            self.lbl_rms.setText("⚠ Ajuste ESPEJADO"); self.lbl_rms.setStyleSheet("color:#e06060;font-weight:bold;")
            self.hint.setText("⚠ El ajuste salió ESPEJADO (el plano quedaría volteado). Casi siempre es "
                              "porque los puntos están CASI EN LÍNEA (corredor) o un par está cruzado. "
                              "Usa 3–4 puntos formando un TRIÁNGULO amplio (en calles distintas / ambos "
                              "lados) y recalcula.")
            QtWidgets.QMessageBox.warning(self, "Ajuste espejado",
                "El ajuste salió espejado: el plano se exportaría volteado.\n\n"
                "Causa típica: los puntos de control están casi en línea recta (todo el corredor), "
                "así la orientación perpendicular queda indeterminada.\n\n"
                "Solución: coloca 3–4 puntos que formen un TRIÁNGULO amplio — en calles distintas o "
                "a ambos lados del corredor — y vuelve a «Calcular ajuste».")
            self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
            return
        pts = [{"px": list(p["px"]),
                "lonlat": list(p["lonlat"]) if p.get("lonlat") else None,
                "world": list(p["world"]) if p.get("world") else None,
                "kind": p.get("kind", "map"), "label": p.get("label", "")}
               for p in self.pairs]
        self.result_georef = georef_mod.Georef(matrix=matrix, epsg=epsg, kind=ttype, rms=rms, points=pts)
        # Error por punto (residual): distancia entre la coordenada real y la que
        # predice el ajuste. Sirve para detectar el punto mal colocado.
        g = georef_mod.Georef(matrix=matrix, epsg=epsg, kind=ttype)
        self._residuals = [((g.to_world(x, y)[0] - E) ** 2 + (g.to_world(x, y)[1] - N) ** 2) ** 0.5
                           for (x, y), (E, N) in zip(px, world)]
        unit = georef_mod.epsg_unit(epsg)                # "ft" (2229) o "m" (UTM)
        thr = 3.0 if unit == "ft" else 2.0               # umbral de RMS aceptable
        color = "#5fd35f" if rms <= thr else "#e06060"
        self.lbl_rms.setText(f"RMS: {rms:.2f} {unit}  ({ttype}, {len(px)} pts)")
        self.lbl_rms.setStyleSheet(f"color:{color};")
        self._refresh_table()                            # muestra el error por punto
        if rms > thr:
            worst = max(range(len(self._residuals)), key=lambda i: self._residuals[i])
            self.hint.setText(f"RMS alto (>{thr:.0f} {unit}): el punto #{worst + 1} es el peor "
                              f"({self._residuals[worst]:.2f} {unit}). Bórralo y recalcula, o agrega más.")
        else:
            self.hint.setText(f"✓ Ajuste OK (RMS {rms:.2f} {unit}). Pulsa Aceptar para georreferenciar.")
        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)
