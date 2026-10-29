"""2.0.0 — Panel «Hoja y PDF» del riel (como el prototipo).

Tarjeta del PDF con sus hojas ◀ ▶, «Componer hoja» (la acción principal), escaneos y agregar utilidad, planos de
fondo (los de «Capas»), vista (opacidad, fondo blanco/negro, minimapa y marcas de las hojas), escala y
georreferencia. Todo llama a lo de siempre (`win._acc[...]`, `_prev_page`, `canvas.set_pdf_opacity`,
`_cambiar_capa`, `_prompt_scale`…). `refrescar()` lo llama la barra superior al cambiar de hoja o proyecto.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R


def _fila_control(etiqueta_es, control):
    w = R.transparente(QtWidgets.QWidget())
    f = QtWidgets.QHBoxLayout(w)
    f.setContentsMargins(0, 0, 0, 0)
    lbl = R.texto(etiqueta_es, "t2")
    lbl.setFixedWidth(110)
    f.addWidget(lbl)
    f.addWidget(control, 1)
    return w


def _segmentado(claves, al_elegir):
    seg = QtWidgets.QFrame()
    seg.setObjectName("segmentado")
    sl = QtWidgets.QHBoxLayout(seg)
    sl.setContentsMargins(3, 3, 3, 3)
    grupo = QtWidgets.QButtonGroup(seg)
    for i, clave in enumerate(claves):
        b = QtWidgets.QPushButton()
        _bind(b, "setText", clave)
        b.setProperty("kind", "seg")
        b.setCheckable(True)
        grupo.addButton(b, i)
        sl.addWidget(b, 1)
    grupo.idClicked.connect(al_elegir)
    seg.grupo = grupo
    return seg


class PanelHoja(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        R.transparente(self)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        cont, cl = R.columna((12, 6, 12, 12), 8)
        cl.addWidget(self._tarjeta())
        componer = QtWidgets.QPushButton()
        _bind(componer, "setText", "Componer hoja de trabajo…", pre="  ")
        componer.setProperty("kind", "primary")
        self.btn_componer = componer
        a = win._acc.get("Componer hoja de trabajo…")
        if a is not None:
            componer.clicked.connect(a.trigger)
        cl.addWidget(componer)
        for ic, clave, det in (("file-image-outline", "Componer PDF imagen/escaneo…", "Regla, transportador y enderezar"),
                               ("file-plus-outline", "Agregar utilidad desde otro PDF…", "Se ubica sola por el mapa base")):
            a = win._acc.get(clave)
            if a is not None:
                cl.addWidget(R.FilaAccion(ic, clave, det, accion=a))
        self.sec_planos = R.seccion("Planos de fondo")
        cl.addWidget(self.sec_planos)
        self.caja_planos = R.transparente(QtWidgets.QWidget())
        QtWidgets.QVBoxLayout(self.caja_planos).setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.caja_planos)
        cl.addWidget(R.seccion("Vista"))
        self.opacidad = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacidad.setRange(0, 100)
        self.opacidad.valueChanged.connect(self._opacidad)
        cl.addWidget(_fila_control("Opacidad del PDF", self.opacidad))
        self.fondo = _segmentado(("Blanco", "Negro"), self._fondo)
        cl.addWidget(_fila_control("Fondo", self.fondo))
        cl.addWidget(R.fila_interruptor("Minimapa de las hojas", "", getattr(win, "act_minimapa_hojas", None)))
        cl.addWidget(R.fila_interruptor("Marcas de las hojas", "", getattr(win, "act_marcas_hojas", None)))
        cl.addWidget(R.seccion("Escala"))
        fila_e = QtWidgets.QHBoxLayout()
        self.lbl_escala = QtWidgets.QLabel()
        fila_e.addWidget(self.lbl_escala, 1)
        cambiar = QtWidgets.QPushButton()
        _bind(cambiar, "setText", "Cambiar…")
        cambiar.clicked.connect(lambda: win._prompt_scale())
        fila_e.addWidget(cambiar)
        cl.addLayout(fila_e)
        cl.addWidget(R.seccion("Georreferencia"))
        fila_g = QtWidgets.QHBoxLayout()
        self.punto_geo = QtWidgets.QLabel("●")
        fila_g.addWidget(self.punto_geo)
        self.lbl_geo = QtWidgets.QLabel()
        self.lbl_geo.setWordWrap(True)
        fila_g.addWidget(self.lbl_geo, 1)
        cl.addLayout(fila_g)
        botones = QtWidgets.QHBoxLayout()
        for clave, ic, fantasma in (("Georreferenciar…", "earth", False), ("Quitar georreferencia", "earth-off", True)):
            a = win._acc.get(clave)
            if a is None:
                continue
            b = QtWidgets.QPushButton()
            _bind(b, "setText", "Quitar" if fantasma else clave)
            b.setIcon(_icon("mdi:" + ic))
            if fantasma:
                b.setProperty("kind", "ghost")
                _bind(b, "setToolTip", clave)
            b.clicked.connect(a.trigger)
            botones.addWidget(b)
        botones.addStretch(1)
        cl.addLayout(botones)
        cl.addStretch(1)
        lay.addWidget(R.AreaVertical(cont))
        _theme.THEME_BUS.changed.connect(lambda _n: self.refrescar())
        self.refrescar()

    def _tarjeta(self):
        tarjeta = QtWidgets.QFrame()
        tarjeta.setObjectName("tarjeta")
        tl = QtWidgets.QVBoxLayout(tarjeta)
        tl.setContentsMargins(12, 10, 12, 8)
        fila = QtWidgets.QHBoxLayout()
        self.ic_pdf = QtWidgets.QLabel()
        fila.addWidget(self.ic_pdf, 0, QtCore.Qt.AlignTop)
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(0)
        self.lbl_pdf = QtWidgets.QLabel()
        self.lbl_pdf.setProperty("rol", "h3")
        self.lbl_pdf.setWordWrap(True)
        self.lbl_det = QtWidgets.QLabel()
        self.lbl_det.setProperty("rol", "t3")
        self.lbl_det.setWordWrap(True)
        tx.addWidget(self.lbl_pdf)
        tx.addWidget(self.lbl_det)
        fila.addLayout(tx, 1)
        tl.addLayout(fila)
        self.nav = R.transparente(QtWidgets.QWidget())
        nav = QtWidgets.QHBoxLayout(self.nav)
        nav.setContentsMargins(0, 0, 0, 0)
        self.btn_ant = R.boton_icono("chevron-left", "Hoja anterior", lambda: self.win._prev_page())
        self.lbl_hoja = QtWidgets.QLabel()
        self.lbl_hoja.setProperty("rol", "t2")
        self.btn_sig = R.boton_icono("chevron-right", "Hoja siguiente", lambda: self.win._next_page())
        nav.addWidget(self.btn_ant)
        nav.addWidget(self.lbl_hoja)
        nav.addWidget(self.btn_sig)
        nav.addStretch(1)
        tl.addWidget(self.nav)
        return tarjeta

    def _opacidad(self, v):
        c = self.win.canvas
        if c.pixmap_item is None or abs(c.pdf_opacity * 100 - v) < 0.5:
            return
        c.set_pdf_opacity(v / 100.0)
        if hasattr(self.win, "lbl_opacity"):
            self.win.lbl_opacity.setText(f"{v}%")

    def _fondo(self, i):
        c = self.win.canvas
        if (i == 1) != (c.pdf_bg_color.value() < 128):
            c.set_pdf_bg(QtGui.QColor(0, 0, 0) if i == 1 else QtGui.QColor(255, 255, 255))
            self.win._redraw()                         # las zonas borradas toman el color del fondo

    def refrescar(self):
        w = self.win
        t = _theme.tokens()
        self.ic_pdf.setPixmap(_icon("mdi:file-pdf-box", color=t.danger).pixmap(28, 28))
        self.btn_componer.setIcon(_icon("mdi:view-grid-outline", color=t.text_on_accent))
        pdf = getattr(w, "pdf_path", None)
        self.lbl_pdf.setText(os.path.basename(pdf) if pdf else _tr("Sin PDF abierto"))
        comp = getattr(w, "composite", None)
        piezas = len(getattr(comp, "pieces", None) or []) if comp is not None else 0
        doc = getattr(w, "doc", None)
        if piezas > 1:
            self.lbl_det.setText(_tr("Hoja compuesta · {n} hojas").format(n=piezas))
        elif doc is not None:
            self.lbl_det.setText(_tr("{n} hoja(s)").format(n=doc.page_count))
        else:
            self.lbl_det.setText(_tr("Abre o arrastra un PDF/proyecto."))
        hay = doc is not None and doc.page_count > 1
        self.nav.setVisible(False)       # 2026-10-28: sin cambio de hoja en «Hoja y PDF» (pedido del usuario)
        if hay:
            self.lbl_hoja.setText(_tr("Hoja {n} de {m}").format(n=w.page_idx + 1, m=doc.page_count))
            self.btn_ant.setEnabled(w.page_idx > 0)
            self.btn_sig.setEnabled(w.page_idx < doc.page_count - 1)
        c = w.canvas
        self.opacidad.blockSignals(True)
        self.opacidad.setValue(round(c.pdf_opacity * 100))
        self.opacidad.blockSignals(False)
        self.opacidad.setEnabled(c.pixmap_item is not None)
        self.fondo.grupo.button(1 if c.pdf_bg_color.value() < 128 else 0).setChecked(True)
        self.lbl_escala.setText(w.btn_scale.text().strip() if hasattr(w, "btn_scale") else "")
        geo = w.georef.active() if hasattr(w, "georef") else False
        self.punto_geo.setStyleSheet(f"color:{t.success if geo else t.text3}; font-size:10px;")
        self.lbl_geo.setText(w.lbl_geo.text() if hasattr(w, "lbl_geo") else "")
        self._planos()

    def _planos(self):
        lay = self.caja_planos.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget() is not None:
                it.widget().hide()
                it.widget().deleteLater()
        try:
            planos = self.win._estado_capas().planos
        except Exception:                              # sin hoja abierta
            planos = []
        self.sec_planos.setVisible(bool(planos))
        self.caja_planos.setVisible(bool(planos))
        for f in planos:
            fila = R.fila_interruptor(f.nombre, f.detalle or "", encendido=f.encendida, traducir=False)
            fila.interruptor.toggled.connect(lambda on, f=f: self.win._cambiar_capa(f.tipo, f.clave, on))
            lay.addWidget(fila)
