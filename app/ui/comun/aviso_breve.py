"""2.0.0 — Aviso breve («toast»): una tarjeta abajo a la derecha que se va sola (como el prototipo).

Para RESULTADOS que no piden decidir nada («DXF exportado», «Todo en orden», «Bancoducto guardado»),
con una acción opcional («Abrir carpeta», «Deshacer»). Las preguntas y los errores siguen siendo
cuadros de diálogo. Uno a la vez: uno nuevo reemplaza al anterior. Lo usa `Main.aviso_breve`, que sin
la ventana en pantalla (pruebas) muestra el mensaje de siempre.
"""
from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

DURACION_MS = 6000            # sin acción
DURACION_ACCION_MS = 9000     # con «Deshacer» / «Abrir carpeta»: más tiempo para usarla
ANCHO = 380


class AvisoBreve(QtWidgets.QFrame):
    def __init__(self, win, titulo, detalle="", accion=None, tono="ok"):
        super().__init__(win)
        self.setObjectName("flotante")
        self.setFixedWidth(ANCHO)
        t = _theme.tokens()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 8, 10)
        lay.setSpacing(10)
        ic = QtWidgets.QLabel()
        nombre, color = {"ok": ("mdi:check-circle-outline", t.success),
                         "aviso": ("mdi:alert-outline", t.warning),
                         "info": ("mdi:information-outline", t.accent)}.get(tono, ("mdi:check-circle-outline", t.success))
        ic.setPixmap(_icon(nombre, color=color).pixmap(20, 20))
        lay.addWidget(ic, 0, QtCore.Qt.AlignTop)
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(1)
        self.lbl_titulo = QtWidgets.QLabel(titulo)
        self.lbl_titulo.setProperty("rol", "h3")
        self.lbl_titulo.setWordWrap(True)
        tx.addWidget(self.lbl_titulo)
        self.lbl_detalle = QtWidgets.QLabel(detalle)
        self.lbl_detalle.setProperty("rol", "t3")
        self.lbl_detalle.setWordWrap(True)
        self.lbl_detalle.setVisible(bool(detalle))
        self.lbl_detalle.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        tx.addWidget(self.lbl_detalle)
        lay.addLayout(tx, 1)
        self.btn_accion = None
        if accion is not None:
            texto, fn = accion
            self.btn_accion = QtWidgets.QPushButton(texto)
            self.btn_accion.setProperty("kind", "ghost")
            self.btn_accion.setCursor(QtCore.Qt.PointingHandCursor)
            self.btn_accion.clicked.connect(lambda: (self.cerrar(), fn()))
            lay.addWidget(self.btn_accion, 0, QtCore.Qt.AlignVCenter)
        cerrar = QtWidgets.QToolButton()
        cerrar.setIcon(_icon("mdi:close", color=t.text_muted))
        cerrar.setAutoRaise(True)
        cerrar.setToolTip(_tr("Cerrar"))
        cerrar.clicked.connect(self.cerrar)
        lay.addWidget(cerrar, 0, QtCore.Qt.AlignTop)
        self.setStyleSheet(f"QFrame#flotante{{background:{t.surface};border:1px solid {t.border};"
                           f"border-radius:12px;}}")
        self._t = QtCore.QTimer(self, singleShot=True, timeout=self.cerrar)
        self._t.start(DURACION_ACCION_MS if accion is not None else DURACION_MS)
        win.installEventFilter(self)
        self._win = win

    def colocar(self):
        """Abajo a la derecha del área central (sobre la barra de estado)."""
        w = self._win
        cw = w.centralWidget()
        caja = cw.geometry() if cw is not None else w.rect()
        self.adjustSize()
        self.move(caja.right() - self.width() - 16, caja.bottom() - self.height() - 16)
        self.raise_()

    def eventFilter(self, obj, ev):
        if obj is self._win and ev.type() == QtCore.QEvent.Resize:
            self.colocar()
        return False

    def enterEvent(self, e):                             # con el ratón encima no se va
        self._t.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._t.start(DURACION_MS // 2)
        super().leaveEvent(e)

    def cerrar(self):
        try:
            self._win.removeEventFilter(self)
        except RuntimeError:
            pass
        if getattr(self._win, "_aviso_breve", None) is self:
            self._win._aviso_breve = None
        self.hide()
        self.deleteLater()


def mostrar(win, titulo, detalle="", accion=None, tono="ok"):
    anterior = getattr(win, "_aviso_breve", None)
    if anterior is not None:
        try:
            anterior.cerrar()
        except RuntimeError:
            pass
    a = AvisoBreve(win, titulo, detalle, accion, tono)
    win._aviso_breve = a
    a.show()
    a.colocar()
    return a
