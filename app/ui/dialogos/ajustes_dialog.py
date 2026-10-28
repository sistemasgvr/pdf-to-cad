"""2.0.0 — «Ajustes»: UNA ventana con barra lateral (como el prototipo) que reúne lo que antes estaba repartido
en Archivo → Opciones, Ver, Herramientas (familias) e IA. Nada nuevo en la lógica: cada sección usa lo de siempre.

    General                · idioma (`i18n.set_lang`), tema (`theme.apply_theme`), ocultar solos los paneles
                             (`act_panel_izq/der`)
    Civil 3D               · versión e idioma del catálogo (los combos de siempre `cmb_civil`/`cmb_lang`, reflejados)
    Asistente IA           · `ia_config_dialog.IAConfigDialog` incrustado (Guardar = lo mismo que «Configurar IA…»),
                             carpeta de aprendizaje y «Pasar a producción…» (solo en desarrollo)
    Familias personalizadas · instalar / desinstalar (los diálogos de siempre)
    Atajos de teclado      · la misma lista que Ayuda → Atajos, con buscador
    Acerca de              · versión, novedades de esta versión e historial completo
"""
import html

from PySide6 import QtCore, QtWidgets

from nucleo.model import CHANGELOG, VERSION
from traduccion import i18n as _i18n
from traduccion.i18n import t as _tr
from ui.comun import rediseno as R
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

SECCIONES = [("tune-vertical", "General"), ("application-cog-outline", "Civil 3D"), ("robot-outline", "Asistente IA"),
             ("puzzle-outline", "Familias personalizadas"), ("keyboard-outline", "Atajos de teclado"),
             ("information-outline", "Acerca de")]
GENERAL, CIVIL, IA, FAMILIAS, ATAJOS, ACERCA = range(6)


class AjustesDialog(QtWidgets.QDialog):
    def __init__(self, win, seccion=GENERAL):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Ajustes"))
        self.resize(900, 620)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lado, ll = R.columna((12, 18, 12, 12), 4)
        lado.setObjectName("ladoAjustes")
        lado.setFixedWidth(240)
        ll.addWidget(R.texto("Ajustes", "h2"))
        ll.addSpacing(8)
        self.grupo = QtWidgets.QButtonGroup(self)
        for i, (ic, clave) in enumerate(SECCIONES):
            b = R.FilaAccion(ic, clave)
            b.setCheckable(True)
            self.grupo.addButton(b, i)
            ll.addWidget(b)
        ll.addStretch(1)
        lay.addWidget(lado)
        der, dl = R.columna((28, 22, 28, 18), 12)
        self.pila = QtWidgets.QStackedWidget()
        for f in (self._general, self._civil, self._ia, self._familias, self._atajos, self._acerca):
            self.pila.addWidget(R.AreaVertical(f()))
        dl.addWidget(self.pila, 1)
        fila = QtWidgets.QHBoxLayout()
        fila.addStretch(1)
        listo = QtWidgets.QPushButton()
        listo.setText(_tr("Listo"))
        listo.setProperty("kind", "primary")
        listo.setAutoDefault(False)
        listo.clicked.connect(self.accept)
        fila.addWidget(listo)
        dl.addLayout(fila)
        lay.addWidget(der, 1)
        self.grupo.idClicked.connect(self.ir)
        _theme.THEME_BUS.changed.connect(lambda _n: self._estilo())
        self._estilo()
        self.ir(seccion)

    def _estilo(self):
        t = _theme.tokens()
        self.findChild(QtWidgets.QWidget, "ladoAjustes").setStyleSheet(
            f"QWidget#ladoAjustes {{ background:{t.surface}; border-right:1px solid {t.border_soft}; }}"
            f" QPushButton:checked {{ background:{t.soft}; }}")

    def ir(self, i):
        self.grupo.button(i).setChecked(True)
        self.pila.setCurrentIndex(i)

    @staticmethod
    def _pagina(titulo_es, subtitulo_es=""):
        w, lay = R.columna((0, 0, 8, 0), 12)
        lay.addWidget(R.texto(titulo_es, "h1"))
        if subtitulo_es:
            lay.addWidget(R.texto(subtitulo_es, "t2", True))
        return w, lay

    @staticmethod
    def _fila(etiqueta_es, control):
        w = R.transparente(QtWidgets.QWidget())
        f = QtWidgets.QHBoxLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        lbl = R.texto(etiqueta_es, "t2")
        lbl.setFixedWidth(170)
        f.addWidget(lbl)
        f.addWidget(control, 1)
        return w

    # ── General ──
    def _general(self):
        w, lay = self._pagina("General", "Idioma, tema y comportamiento de los paneles.")
        self.cmb_idioma = QtWidgets.QComboBox()
        self.cmb_idioma.addItem(_tr("Español"), _tr("es"))
        self.cmb_idioma.addItem(_tr("Inglés"), _tr("en"))
        self.cmb_idioma.setCurrentIndex(max(0, self.cmb_idioma.findData(_i18n.get_lang())))
        self.cmb_idioma.currentIndexChanged.connect(
            lambda _i: _i18n.set_lang(self.cmb_idioma.currentData()))     # al instante, como en Opciones
        lay.addWidget(self._fila("Idioma", self.cmb_idioma))
        lay.addWidget(R.texto("El cambio se aplica al instante en menús y paneles principales. Algunas ventanas "
                              "ya abiertas pueden requerir cerrarse y volver a abrirse para verse completamente "
                              "en el nuevo idioma.", "t3", True))
        seg = QtWidgets.QFrame()
        seg.setObjectName("segmentado")
        sl = QtWidgets.QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        self.grupo_tema = QtWidgets.QButtonGroup(seg)
        for i, clave in enumerate(("Claro", "Oscuro")):
            b = QtWidgets.QPushButton(_tr(clave))
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setChecked((i == 1) == _theme.is_dark())
            self.grupo_tema.addButton(b, i)
            sl.addWidget(b, 1)
        self.grupo_tema.idClicked.connect(self._tema)
        lay.addWidget(self._fila("Tema", seg))
        lay.addWidget(R.seccion("Paneles"))
        for a, clave, det in ((getattr(self.win, "act_panel_izq", None), "Ocultar automáticamente el panel izquierdo",
                               "Queda una pestaña en el borde; se abre al pasar el ratón"),
                              (getattr(self.win, "act_panel_der", None), "Ocultar automáticamente el panel derecho", "")):
            if a is not None:
                lay.addWidget(R.fila_interruptor(clave, det, a))
        lay.addStretch(1)
        return w

    def _tema(self, i):
        nombre = "dark" if i == 1 else "light"
        if (nombre == "dark") != _theme.is_dark():
            _theme.apply_theme(QtWidgets.QApplication.instance(), nombre)

    # ── Civil 3D ──
    def _civil(self):
        w, lay = self._pagina("Civil 3D", "Versión e idioma del catálogo imperial que usa la exportación.")
        self.cmb_anio = QtWidgets.QComboBox()
        self.cmb_cat = QtWidgets.QComboBox()
        self._copiar_combos()
        self.cmb_anio.currentIndexChanged.connect(lambda i: self._a_la_ventana(self.win.cmb_civil, i))
        self.cmb_cat.currentIndexChanged.connect(lambda i: self._a_la_ventana(self.win.cmb_lang, i))
        lay.addWidget(self._fila("Versión", self.cmb_anio))
        lay.addWidget(self._fila("Idioma del catálogo", self.cmb_cat))
        lay.addWidget(R.texto("También se elige al exportar («Exportar a Civil 3D»).", "t3", True))
        lay.addStretch(1)
        return w

    def _copiar_combos(self):
        for mio, suyo in ((self.cmb_anio, getattr(self.win, "cmb_civil", None)),
                          (self.cmb_cat, getattr(self.win, "cmb_lang", None))):
            if suyo is None:
                continue
            mio.blockSignals(True)
            mio.clear()
            for i in range(suyo.count()):
                mio.addItem(suyo.itemText(i), suyo.itemData(i))
            mio.setCurrentIndex(suyo.currentIndex())
            mio.setToolTip(suyo.toolTip())
            mio.blockSignals(False)

    def _a_la_ventana(self, combo, i):
        if combo is not None and combo.currentIndex() != i:
            combo.setCurrentIndex(i)                   # sus manejadores de siempre (y rellena el idioma)
        self._copiar_combos()

    # ── Asistente IA ──
    def _ia(self):
        w, lay = self._pagina("Asistente IA", "Quién responde y dónde se guarda lo que aprende.")
        self._caja_ia = R.transparente(QtWidgets.QWidget())
        QtWidgets.QVBoxLayout(self._caja_ia).setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._caja_ia)
        self._poner_ia()
        lay.addWidget(R.seccion("Aprendizaje"))
        for ic, clave in (("folder-open-outline", "Abrir carpeta de aprendizaje"),
                          ("rocket-launch-outline", "Pasar a producción…")):
            a = getattr(self.win, "_acc", {}).get(clave)
            if a is not None:
                lay.addWidget(R.FilaAccion(ic, clave, accion=a))
        lay.addStretch(1)
        return w

    def _poner_ia(self):
        """La ventana «Configurar IA» de siempre, incrustada; «Guardar» hace lo mismo que antes."""
        from ui.dialogos.ia_config_dialog import IAConfigDialog
        dlg = IAConfigDialog(self.win)
        dlg.setWindowFlags(QtCore.Qt.Widget)
        caja = dlg.findChild(QtWidgets.QDialogButtonBox)
        if caja is not None and caja.button(QtWidgets.QDialogButtonBox.Ok) is not None:
            caja.button(QtWidgets.QDialogButtonBox.Ok).setProperty("kind", "primary")   # «Guardar» en color
        dlg.accepted.connect(self._ia_guardada)
        dlg.finished.connect(lambda _r: QtCore.QTimer.singleShot(0, self._rehacer_ia))
        self._caja_ia.layout().addWidget(dlg)
        dlg.show()
        self._dlg_ia = dlg

    def _rehacer_ia(self):
        viejo = getattr(self, "_dlg_ia", None)
        if viejo is not None:
            viejo.setParent(None)
            viejo.deleteLater()
        self._poner_ia()

    def _ia_guardada(self):
        hecho = getattr(self.win, "_ia_config_guardada", None)
        if hecho is not None:
            hecho()

    # ── Familias ──
    def _familias(self):
        w, lay = self._pagina("Familias personalizadas", "Piezas propias en el catálogo de Civil 3D (todas las "
                                                          "versiones e idiomas instalados).")
        for ic, clave in (("plus", "Instalar familia personalizada…"),
                          ("puzzle-remove-outline", "Desinstalar familia personalizada…")):
            a = getattr(self.win, "_acc", {}).get(clave)
            if a is not None:
                lay.addWidget(R.FilaAccion(ic, clave, accion=a))
        lay.addStretch(1)
        return w

    # ── Atajos ──
    def _atajos(self):
        from ui.dialogos import shortcuts_dialog as SD
        w, lay = self._pagina("Atajos de teclado", "Teclas y gestos de la app, agrupados por menú. Escribe para "
                                                   "filtrar.")
        grupos = [(g, rows) for g, rows in sorted(SD._menu_groups(self.win).items())]
        grupos += [(_tr(t), [(_tr(k), _tr(d)) for k, d in rows]) for t, rows in SD._FIXED]
        buscar = R.CampoBuscar("Buscar atajo o acción…")
        tb = QtWidgets.QTextBrowser()
        tb.setMinimumHeight(380)
        tb.setStyleSheet("QTextBrowser { border: none; background: transparent; }")

        def refrescar(texto=""):
            tb.setHtml(SD._render(grupos, texto, _theme.tokens()))
        buscar.textChanged.connect(refrescar)
        refrescar()
        lay.addWidget(buscar)
        lay.addWidget(tb, 1)
        return w

    # ── Acerca de ──
    def _acerca(self):
        w, lay = self._pagina("Asistente C3D", "")
        lay.addWidget(R.texto(_tr("Versión") + f" {VERSION}", "h3", traducir=False))
        lay.addWidget(R.texto("Convierte un PDF de plano a DXF y te deja marcar utilidades, Multileaders y notas "
                              "sobre la imagen, exportando todo en las mismas coordenadas para abrirlo en Civil 3D.",
                              "t2", True))
        lay.addWidget(R.seccion("Novedades"))
        ver, items = CHANGELOG[0]
        for _tipo, texto in items:
            lbl = QtWidgets.QLabel(html.escape(_tr(texto)))
            lbl.setWordWrap(True)
            lbl.setProperty("rol", "t2")
            lay.addWidget(lbl)
        b = QtWidgets.QPushButton(_tr("Historial completo"))
        b.setIcon(_icon("mdi:file-document-outline"))
        b.setProperty("kind", "ghost")
        b.clicked.connect(lambda: self.win.show_about())
        lay.addWidget(b, 0, QtCore.Qt.AlignLeft)
        lay.addStretch(1)
        return w


def abrir(win, seccion=GENERAL):
    AjustesDialog(win, seccion).exec()
