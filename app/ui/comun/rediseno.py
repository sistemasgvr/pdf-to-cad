"""Piezas del rediseño 2.0.0 (las mismas del prototipo), con los colores del tema activo.

    Interruptor      · encendido/apagado; puede reflejar un QAction checable (mismo estado, mismo método)
    fila_interruptor · título + detalle + interruptor
    fila_accion      · fila clicable tipo menú: icono, título, detalle y atajo (dispara un QAction)
    seccion          · etiqueta de sección en mayúsculas
    CampoBuscar      · campo con lupa y atajo dibujados
    Tecla            · un atajo de teclado como tecla
    titulo_panel     · cabecera de un panel: título + botones
Nada de esto tiene lógica propia: cada pieza llama a una acción o método que ya existía.
"""
import re

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon, icono_conmutable as _icono_conmutable
from traduccion.i18n import bind as _bind, t as _tr


class Interruptor(QtWidgets.QAbstractButton):
    """Interruptor (reemplaza a la casilla en paneles y ajustes)."""

    def __init__(self, encendido=False, tip="", accion=None):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(34, 20)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)
            self.setAccessibleName(tip)
        if accion is not None:                         # refleja el QAction (menús de antes, atajos, QSettings)
            self.setChecked(accion.isChecked())
            self.toggled.connect(lambda on: accion.isChecked() != on and accion.setChecked(on))
            accion.toggled.connect(lambda on: self.isChecked() != on and self.setChecked(on))
        else:
            self.setChecked(encendido)

    def sizeHint(self):                                # noqa: N802
        return QtCore.QSize(34, 20)

    def paintEvent(self, _e):                          # noqa: N802
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        apagado = QtGui.QColor(t.text3)
        apagado.setAlpha(120)
        if not self.isEnabled():
            apagado.setAlpha(50)
        p.setBrush(QtGui.QColor(t.accent) if self.isChecked() and self.isEnabled() else apagado)
        p.drawRoundedRect(QtCore.QRectF(self.rect()), 10, 10)
        p.setBrush(QtGui.QColor("#ffffff"))
        x = self.width() - 18 if self.isChecked() else 2
        p.drawEllipse(QtCore.QRectF(x, 2, 16, 16))


_TECLAS_ES = {"Shift": "Mayúsc", "Del": "Supr", "Ins": "Insert", "PgUp": "RePág", "PgDown": "AvPág",
              "Return": "Intro", "Enter": "Intro", "Backspace": "Retroceso", "Space": "Espacio",
              "Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}
_TECLAS_EN = {"Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}


def atajo_legible(atajo) -> str:
    """«Ctrl + Mayúsc + N» (en inglés «Ctrl + Shift + N»): un QKeySequence o su texto. El texto nativo de
    Windows en español daba «Control+Mayúsculas+N» (pedido del usuario 2026-10-28)."""
    from traduccion.i18n_core import get_lang
    if isinstance(atajo, QtGui.QKeySequence):
        atajo = atajo.toString(QtGui.QKeySequence.PortableText)
    tabla = _TECLAS_ES if get_lang() == "es" else _TECLAS_EN
    combos = []
    for combo in str(atajo or "").split(", "):
        partes = re.findall(r"\+$|[^+]+", combo)       # «Ctrl++» = Ctrl y la tecla «+»
        combos.append(" + ".join(tabla.get(p.strip(), p.strip()) for p in partes if p.strip()))
    return ", ".join(c for c in combos if c)


class Tecla(QtWidgets.QLabel):
    """Atajo de teclado dibujado como tecla («Ctrl K»)."""

    def __init__(self, txt):
        super().__init__(txt)
        self.setObjectName("tecla")
        self._estilo()
        _theme.THEME_BUS.changed.connect(lambda _n: self._estilo())

    def _estilo(self):
        t = _theme.tokens()
        self.setStyleSheet(f"QLabel#tecla {{ background:{t.surface_alt}; color:{t.text3}; border:1px solid "
                           f"{t.border_soft}; border-radius:5px; padding:0 5px; font-size:11px; }}")


def texto(clave_es, rol=None, ajustar=False, traducir=True):
    lbl = QtWidgets.QLabel()
    if traducir:
        _bind(lbl, "setText", clave_es)
    else:
        lbl.setText(clave_es)
    if rol:
        lbl.setProperty("rol", rol)
    lbl.setWordWrap(ajustar)
    return lbl


def transparente(w):
    """Contenedor sin fondo propio (la hoja de estilo global pinta cada QWidget con el fondo de la ventana)."""
    w.setObjectName(w.objectName() or "sinFondo")
    w.setStyleSheet(f"QWidget#{w.objectName()} {{ background: transparent; }}")
    return w


def seccion(clave_es, derecha=None):
    w = transparente(QtWidgets.QWidget())
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 8, 0, 0)
    lbl = QtWidgets.QLabel()
    lbl.setProperty("rol", "sec")
    lbl.setText(_tr(clave_es).upper())             # en mayúsculas: se re-traduce con el idioma
    from traduccion.i18n import LANG_BUS
    LANG_BUS.changed.connect(lambda *_a: lbl.setText(_tr(clave_es).upper()))
    lay.addWidget(lbl)
    lay.addStretch(1)
    if derecha is not None:
        lay.addWidget(derecha)
    return w


class FilaAccion(QtWidgets.QPushButton):
    """Fila clicable tipo menú: icono, título, detalle (una línea) y atajo. Dispara `accion` (QAction)
    o llama a `fn`. Hereda el texto/atajo del QAction si no se dan."""

    def __init__(self, icono, titulo_es, detalle_es="", accion=None, fn=None, atajo=None, peligro=False):
        super().__init__()
        self.setProperty("kind", "ghost")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { text-align:left; padding:0; }")
        self._icono, self._peligro = icono, peligro
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        self.ic = QtWidgets.QLabel()
        lay.addWidget(self.ic, 0, QtCore.Qt.AlignTop if detalle_es else QtCore.Qt.AlignVCenter)
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(0)
        self.lbl = texto(titulo_es, ajustar=True)
        tx.addWidget(self.lbl)
        if detalle_es:
            tx.addWidget(texto(detalle_es, "t3", True))
        lay.addLayout(tx, 1)
        if atajo is None and accion is not None and not accion.shortcut().isEmpty():
            atajo = accion.shortcut()
        if atajo:
            lay.addWidget(Tecla(atajo_legible(atajo)), 0, QtCore.Qt.AlignVCenter)
        self._alto_min = 52 if detalle_es else 36
        self.setMinimumHeight(self._alto_min)
        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        if accion is not None:
            self.clicked.connect(accion.trigger)
            if accion.toolTip() and accion.toolTip() != accion.text().replace("&", ""):
                self.setToolTip(accion.toolTip())
        elif fn is not None:
            self.clicked.connect(lambda: fn())
        self._estilo()
        _theme.THEME_BUS.changed.connect(lambda _n: self._estilo())

    def _estilo(self):
        t = _theme.tokens()
        color = t.danger if self._peligro else t.text_muted
        self.ic.setPixmap(_icon("mdi:" + self._icono, color=color).pixmap(18, 18))
        self.lbl.setStyleSheet(f"color:{t.danger};" if self._peligro else "")

    # El alto sigue al ANCHO (2026-10-28, captura del usuario: con el panel angosto el título partido en dos
    # líneas tapaba el detalle y éste quedaba cortado): QPushButton no pregunta a su layout por el alto.
    def hasHeightForWidth(self):                       # noqa: N802
        return True

    def heightForWidth(self, w):                       # noqa: N802
        return max(self._alto_min, self.layout().totalHeightForWidth(w))

    def sizeHint(self):                                # noqa: N802
        h = self.layout().sizeHint()
        return QtCore.QSize(h.width(), self.heightForWidth(self.width() or h.width()))

    def minimumSizeHint(self):                         # noqa: N802
        h = self.layout().minimumSize()
        return QtCore.QSize(min(h.width(), 120), h.height())

    def resizeEvent(self, e):                          # noqa: N802
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            # los contenedores (QVBoxLayout dentro de un scroll) no siempre preguntan heightForWidth:
            # el mínimo = el alto que pide este ancho, así nunca queda cortada
            alto = self.heightForWidth(e.size().width())
            if alto != self.minimumHeight():
                self.setMinimumHeight(alto)


def fila_interruptor(clave_es, detalle_es="", accion=None, encendido=False, traducir=True):
    """`traducir=False` para textos que ya vienen traducidos o son datos (nombre de un plano)."""
    w = transparente(QtWidgets.QWidget())
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 3, 0, 3)
    lay.setSpacing(10)
    tx = QtWidgets.QVBoxLayout()
    tx.setSpacing(0)
    tx.addWidget(texto(clave_es, ajustar=True, traducir=traducir))
    if detalle_es:
        tx.addWidget(texto(detalle_es, "t3", True, traducir=traducir))
    lay.addLayout(tx, 1)
    w.interruptor = Interruptor(encendido, _tr(clave_es) if traducir else clave_es, accion)
    lay.addWidget(w.interruptor, 0, QtCore.Qt.AlignVCenter)
    return w


class CampoBuscar(QtWidgets.QLineEdit):
    """Campo con lupa a la izquierda y atajo a la derecha (opcional)."""

    def __init__(self, placeholder_es, atajo=""):
        super().__init__()
        self.setProperty("kind", "buscar")
        _bind(self, "setPlaceholderText", placeholder_es)
        self.atajo = atajo
        self.setMinimumHeight(34)

    def paintEvent(self, e):                           # noqa: N802
        super().paintEvent(e)
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.drawPixmap(10, (self.height() - 16) // 2, _icon("mdi:magnify", color=t.text3).pixmap(16, 16))
        if self.atajo and not self.text():
            p.setPen(QtGui.QColor(t.text3))
            f = p.font()
            f.setPixelSize(11)
            p.setFont(f)
            p.drawText(self.rect().adjusted(0, 0, -10, 0), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self.atajo)


def titulo_panel(clave_es, botones=()):
    w = transparente(QtWidgets.QWidget())
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = texto(clave_es, "h2")
    lay.addWidget(lbl, 1)
    for b in botones:
        lay.addWidget(b)
    return w


def boton_icono(icono, tip_es, fn=None, checkable=False, px=18):
    b = QtWidgets.QToolButton()
    if checkable:                                     # conmutable: blanco al estar seleccionado
        def poner():
            b.setIcon(_icono_conmutable("mdi:" + icono))
    else:
        def poner():
            b.setIcon(_icon("mdi:" + icono))
    poner()
    b.setIconSize(QtCore.QSize(px, px))
    _bind(b, "setToolTip", tip_es)
    _bind(b, "setAccessibleName", tip_es)
    b.setCheckable(checkable)
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b._icono = icono
    _theme.THEME_BUS.changed.connect(lambda _n: poner())
    if fn is not None:
        b.clicked.connect(lambda: fn())
    return b


def columna(margenes=(14, 12, 14, 12), espacio=8):
    w = transparente(QtWidgets.QWidget())
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(*margenes)
    lay.setSpacing(espacio)
    return w, lay


class AreaVertical(QtWidgets.QScrollArea):
    """Scroll solo vertical: el contenido toma siempre el ancho del panel (nunca se sale por la derecha)."""

    def __init__(self, widget):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setWidget(widget)

    def resizeEvent(self, e):                          # noqa: N802
        super().resizeEvent(e)
        if self.widget() is not None:
            self.widget().setFixedWidth(self.viewport().width())


def acciones_de(menu):
    """Las acciones finales de un QMenu y sus submenús, en orden. OJO: NO usa `QAction.menu()` (en PySide6
    el envoltorio que devuelve puede borrar el submenú de verdad al recolectarse)."""
    subs = {m.menuAction(): m for m in menu.findChildren(QtWidgets.QMenu, options=QtCore.Qt.FindDirectChildrenOnly)}
    for a in menu.actions():
        if a in subs:
            yield from acciones_de(subs[a])
        elif not a.isSeparator():
            yield a
