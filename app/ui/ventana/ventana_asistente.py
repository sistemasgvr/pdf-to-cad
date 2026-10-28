"""2.0.0 — El Asistente (IA) en UN panel a la derecha, en vez de ventanas sueltas.

    Chat        · «Pregúntale al proyecto» (ia_chat.PreguntaDialog, el MISMO de siempre, incrustado)
    Conflictos  · «Resolver conflictos» (ia_soluciones.SolucionesDialog, incrustado)
    Ayuda       · «¿Cómo hago…?» (manual_ia_panel.PanelAyudaIA, el del manual)

Cada pestaña se crea la primera vez que se abre. Las funciones de siempre (`abrir_pregunta`,
`abrir_soluciones`) siguen devolviendo el mismo diálogo: solo cambia DÓNDE se ve.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R

PESTANAS = ["chat", "conflictos", "ayuda"]


class PanelAsistente(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        cab = QtWidgets.QHBoxLayout()               # el título «Asistente» lo pone la cabecera del panel
        cab.setContentsMargins(14, 0, 8, 0)
        self.ic = QtWidgets.QLabel()
        cfg = R.boton_icono("cog-outline", "Configurar IA…", lambda: win.abrir_ajustes(2))
        cab.addWidget(cfg)
        cerrar = R.boton_icono("close", "Cerrar el asistente", lambda: win.mostrar_asistente(False))
        cab.addWidget(cerrar)
        seg = QtWidgets.QFrame()
        seg.setObjectName("segmentado")
        sl = QtWidgets.QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.grupo = QtWidgets.QButtonGroup(self)
        for i, clave in enumerate(("Chat", "Conflictos", "Ayuda")):
            b = QtWidgets.QPushButton()
            _bind(b, "setText", clave)
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)   # nunca ensancha el panel
            b.setMinimumWidth(40)
            self.grupo.addButton(b, i)
            sl.addWidget(b, 1)
        lay.addLayout(cab)
        cab.insertWidget(0, seg, 1)
        self.pila = QtWidgets.QStackedWidget()
        self._paginas = {}
        for clave in PESTANAS:
            hueco = QtWidgets.QWidget()
            QtWidgets.QVBoxLayout(hueco).setContentsMargins(0, 0, 0, 0)
            self._paginas[clave] = hueco
            self.pila.addWidget(hueco)
        lay.addWidget(self.pila, 1)
        self.grupo.idClicked.connect(lambda i: self.preparar(PESTANAS[i]))
        _theme.THEME_BUS.changed.connect(lambda _n: self._estilo())
        self._estilo()

    def _estilo(self):
        self.ic.setPixmap(_icon("mdi:creation", color=_theme.tokens().accent).pixmap(20, 20))

    # ── contenido de cada pestaña (se crea al abrirla) ──
    def _poner(self, clave, widget):
        hueco = self._paginas[clave]
        if hueco.layout().indexOf(widget) < 0:
            widget.setWindowFlags(QtCore.Qt.Widget)
            hueco.layout().addWidget(widget)
            if hasattr(widget, "finished"):                # «Cerrar» del diálogo = cerrar el asistente
                widget.finished.connect(lambda *_a: self.win.mostrar_asistente(False))
        widget.show()

    def chat(self):
        from ui.dialogos.ia_chat import PreguntaDialog
        dlg = getattr(self.win, "_ia_chat", None)
        if dlg is None:
            dlg = self.win._ia_chat = PreguntaDialog(self.win)
        if hasattr(dlg, "incrustado"):
            dlg.incrustado()                               # sin la cabecera repetida (2.0.0)
        self._poner("chat", dlg)
        return dlg

    def conflictos(self):
        from ui.dialogos.ia_soluciones import SolucionesDialog
        dlg = getattr(self.win, "_dlg_soluciones", None)
        if dlg is None:
            dlg = self.win._dlg_soluciones = SolucionesDialog(self.win)
        self._poner("conflictos", dlg)
        return dlg

    def ayuda(self):
        panel = getattr(self, "_ayuda", None)
        if panel is None:
            from traduccion import i18n as _i18n
            from ui.dialogos.manual_ia_panel import PanelAyudaIA
            doc = _i18n.load_doc("manual")
            panel = self._ayuda = PanelAyudaIA(doc, getattr(self.win, "_config_ia", None), self._abrir_capitulo)
            cont = QtWidgets.QWidget()
            cl = QtWidgets.QVBoxLayout(cont)
            cl.setContentsMargins(14, 0, 14, 12)
            cl.addWidget(panel)
            manual = QtWidgets.QPushButton()
            _bind(manual, "setText", "Manual de usuario")
            manual.setIcon(_icon("mdi:book-open-variant"))
            manual.clicked.connect(lambda: self.win.show_manual())
            cl.addWidget(manual, 0, QtCore.Qt.AlignLeft)
            cl.addStretch(1)
            self._paginas["ayuda"].layout().addWidget(cont)
        return panel

    def _abrir_capitulo(self, n):
        from ui.dialogos.manual_dialog import ManualDialog
        dlg = ManualDialog(self.win)
        dlg.indice.setCurrentRow(n)
        dlg.exec()

    def preparar(self, pestana=None):
        """Muestra la pestaña pedida (o la que estaba) creando su contenido si hace falta."""
        if pestana is None:
            pestana = PESTANAS[max(0, self.pila.currentIndex())]
        i = PESTANAS.index(pestana)
        getattr(self, pestana)()
        self.grupo.button(i).setChecked(True)
        self.pila.setCurrentIndex(i)
