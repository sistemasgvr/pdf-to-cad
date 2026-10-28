"""2.0.0 — Panel «Dibujar» del riel (como el prototipo): una cuadrícula de herramientas arriba y, debajo, las
opciones de la elegida.

Las opciones son las secciones de SIEMPRE del acordeón (`win.toolbox`, con sus widgets y `_sec_idx`): solo se
ocultan sus cabeceras y cada herramienta abre la suya (`_open_section`) y la arranca con el mismo método de antes
(`toggle_pipe`, `start_leader`, …; volver a pulsarla la detiene, como el botón grande de su sección).
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R

# (icono, texto, sección del acordeón | None, método que la arranca | None, ayuda)
HERRAMIENTAS = [
    ("vector-polyline", "Utilidad", "pipe", "toggle_pipe", "Dibujar utilidad"),
    ("arrow-top-right", "Leader", "leader", "start_leader", "Colocar Leader"),
    ("format-textbox", "Texto", "text", "toggle_text_mode", "Texto libre"),
    ("eraser", "Borrar", "erase", "toggle_erase", "Borrar zona"),
    ("vector-line", "Centerline", "centerline", "toggle_centerline", "Trazar centerline"),
    ("cursor-move", "Mover", "move_precise", None, "Mover con precisión"),
    ("circle-double", "Buzón", None, "insert_manhole", "Insertar buzón en línea…"),
    ("vector-square", "Duct Bank", "ductbank", None, "Duct Bank"),
]
MODOS = {"pipe": ("pipe",), "leader": ("leader1", "leader2", "leader3"), "text": ("text",), "erase": ("erase",),
         "centerline": ("centerline",)}


class Herramientas(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        R.transparente(self)
        g = QtWidgets.QGridLayout(self)
        g.setContentsMargins(12, 6, 12, 4)
        g.setSpacing(6)
        self.botones = []
        for i, (ic, txt, seccion, metodo, ayuda) in enumerate(HERRAMIENTAS):
            b = QtWidgets.QToolButton()
            _bind(b, "setText", txt)
            _bind(b, "setToolTip", ayuda)
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QtCore.QSize(20, 20))
            b.setCheckable(True)
            b.setMinimumSize(60, 56)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=i: self._elegir(k))
            b._icono, b._seccion = ic, seccion
            self.botones.append(b)
            g.addWidget(b, i // 4, i % 4)
        _theme.THEME_BUS.changed.connect(lambda _n: self.sincronizar())

    def _elegir(self, k):
        _ic, _txt, seccion, metodo, _ayuda = HERRAMIENTAS[k]
        w = self.win
        if seccion is not None:
            w._open_section(seccion)                   # sus opciones de siempre (y vuelve a «inactivo»)
        if metodo == "start_leader":
            w.start_leader(True)
        elif metodo is not None:
            getattr(w, metodo)()
        self.sincronizar()

    def sincronizar(self):
        """Marca la herramienta de la sección abierta (o la del modo activo)."""
        t = _theme.tokens()
        w = self.win
        idx = w.toolbox.currentIndex()
        abierta = next((k for k, i in w._sec_idx.items() if i == idx), None)
        for b in self.botones:
            activa = b._seccion is not None and b._seccion == abierta
            dibujando = b._seccion in MODOS and w.mode in MODOS[b._seccion]
            b.setChecked(activa)
            color = t.text_on_accent if dibujando else (t.soft_text if activa else t.text_muted)
            b.setIcon(_icon("mdi:" + b._icono, color=color))
            if dibujando:
                css = f"background:{t.accent}; color:{t.text_on_accent}; border:1px solid {t.accent};"
            elif activa:
                css = f"background:{t.soft}; color:{t.soft_text}; border:1px solid {t.accent};"
            else:
                css = f"background:{t.surface}; color:{t.text_muted}; border:1px solid {t.border_soft};"
            b.setStyleSheet(f"QToolButton {{ {css} border-radius:10px; font-size:11px; padding:6px 2px; }}"
                            f" QToolButton:hover {{ border-color:{t.accent}; }}")


def poner_herramientas(win, contenido_izq):
    """La cuadrícula ARRIBA del acordeón; el acordeón sin cabeceras (cada herramienta abre su sección)."""
    win.herramientas = Herramientas(win)
    contenido_izq.layout().insertWidget(0, win.herramientas)
    for b in win.toolbox.findChildren(QtWidgets.QAbstractButton, "qt_toolbox_toolboxbutton"):
        b.hide()
    if win.toolbox.currentIndex() == win._sec_idx.get("view"):
        # sin señales: la ventana aún se está armando; `_build_ui` aplica la sección abierta al final
        win.toolbox.blockSignals(True)
        win.toolbox.setCurrentIndex(win._sec_idx["pipe"])
        win.toolbox.blockSignals(False)
