"""2.0.0 — Aviso breve («toast»): una tarjeta abajo a la derecha que se va sola (como el prototipo).

Para RESULTADOS que no piden decidir nada («DXF exportado», «Todo en orden», «Bancoducto guardado»),
con una acción opcional («Abrir carpeta», «Deshacer»). Las preguntas y los errores siguen siendo
cuadros de diálogo. Uno a la vez: uno nuevo reemplaza al anterior. Lo usa `Main.aviso_breve`, que sin
la ventana en pantalla (pruebas) muestra el mensaje de siempre.

Abajo lleva una barra de CUENTA REGRESIVA (pedido del usuario 2026-10-30) de `BARRA_PX` de alto y el ancho del
aviso: se vacía hasta que el aviso se va; con el ratón encima se PAUSA (el aviso no se va) y al salir sigue desde
donde quedó. Mientras se ve, la barra de herramientas del plano se corre a la izquierda para no taparse
(`ventana_flotantes.colocar`).
"""
from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

DURACION_MS = 5000            # sin acción
DURACION_ACCION_MS = 15000     # con «Deshacer» / «Abrir carpeta»: más tiempo para usarla
ANCHO = 380
BARRA_PX = 5                 # alto de la barra de cuenta regresiva
PASO_MS = 30                  # cada cuánto se repinta la barra


class _Cuenta(QtWidgets.QWidget):
    """La barra de abajo: lo que queda del tiempo, del color del acento sobre una pista tenue."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(BARRA_PX)
        self.fraccion = 1.0
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

    def paintEvent(self, _e):
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1, 0, -1, -1)          # dentro del borde del aviso
        forma = QtGui.QPainterPath()                                     # esquinas de abajo como las del aviso
        rad = 11.0
        forma.moveTo(r.left(), r.top())
        forma.lineTo(r.right(), r.top())
        forma.lineTo(r.right(), r.bottom() - rad)
        forma.quadTo(r.right(), r.bottom(), r.right() - rad, r.bottom())
        forma.lineTo(r.left() + rad, r.bottom())
        forma.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - rad)
        forma.closeSubpath()
        p.setClipPath(forma)
        p.fillRect(r, QtGui.QColor(t.surface_alt))
        lleno = QtCore.QRectF(r.left(), r.top(), r.width() * max(0.0, min(1.0, self.fraccion)), r.height())
        p.fillRect(lleno, QtGui.QColor(t.accent))
        p.end()


class AvisoBreve(QtWidgets.QFrame):
    def __init__(self, win, titulo, detalle="", accion=None, tono="ok"):
        super().__init__(win)
        self.setObjectName("flotante")
        self.setFixedWidth(ANCHO)
        t = _theme.tokens()
        externo = QtWidgets.QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)
        cuerpo = QtWidgets.QWidget()
        cuerpo.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        externo.addWidget(cuerpo)
        self.cuenta = _Cuenta()
        externo.addWidget(self.cuenta)
        lay = QtWidgets.QHBoxLayout(cuerpo)
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
        self._total = DURACION_ACCION_MS if accion is not None else DURACION_MS
        self._queda = float(self._total)                 # ms que faltan (se descuenta solo sin el ratón encima)
        self._reloj = QtCore.QElapsedTimer()
        self._reloj.start()
        self._t = QtCore.QTimer(self, interval=PASO_MS, timeout=self._avanzar)
        self._t.start()
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

    def _avanzar(self):
        self._queda -= self._reloj.restart()
        self.cuenta.fraccion = self._queda / self._total if self._total else 0.0
        self.cuenta.update()
        if self._queda <= 0:
            self.cerrar()

    def enterEvent(self, e):                             # con el ratón encima: pausa (no se va)
        self._avanzar()
        self._t.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):                             # al salir sigue desde donde quedó
        self._reloj.restart()
        self._t.start()
        super().leaveEvent(e)

    def cerrar(self):
        try:
            self._win.removeEventFilter(self)
        except RuntimeError:
            pass
        if getattr(self._win, "_aviso_breve", None) is self:
            self._win._aviso_breve = None
        self._t.stop()
        self.hide()
        self.deleteLater()
        _recolocar_barra(self._win)


def _recolocar_barra(win):
    """La barra de herramientas del plano se corre (o vuelve) según el aviso."""
    if getattr(win, "barra_plano", None) is not None:
        from ui.ventana import ventana_flotantes
        ventana_flotantes.colocar(win)


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
    _recolocar_barra(win)
    return a
