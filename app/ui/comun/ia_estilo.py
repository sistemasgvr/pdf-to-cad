"""Estilo común de las ventanas de la IA (pedido del usuario 2026-10-26: «interfaz limpia, bonita y moderna», en
tema claro y oscuro). Solo aspecto: ninguna ventana cambia lo que hace.

- `Encabezado`: icono en un círculo suave + título + subtítulo (la explicación de la ventana, en gris).
- `tarjeta(nombre)`: QSS de una tarjeta (fondo alterno, borde suave, esquinas redondeadas).
- `chip_qss()`: botones de sugerencia como «chips» (pregunta de ejemplo, enlace a un capítulo).
- `etiqueta_seccion(texto)`: título chico de una sección («Propuestas», «Recomendación»).
- `al_cambiar_tema(widget, fn)`: llama `fn` ahora y cada vez que cambia el tema (los colores salen de
  `theme.tokens()`; los iconos se retintan).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import icons, theme

ICONO_PX = 22
CIRCULO_PX = 40


def al_cambiar_tema(widget, fn):
    import shiboken6
    fn()

    def _otra_vez(*_a):
        if shiboken6.isValid(widget):                     # la ventana pudo cerrarse y borrarse
            fn()
    theme.THEME_BUS.changed.connect(_otra_vez)


def pix(nombre, color, px=ICONO_PX):
    return icons.icon(nombre, color=color, size=px * 2).pixmap(px, px)


def tarjeta(nombre, tk=None, borde_izq=None):
    """QSS de una tarjeta para `QFrame#nombre` (o cualquier widget con ese objectName)."""
    tk = tk or theme.tokens()
    izq = f"border-left: 3px solid {borde_izq};" if borde_izq else ""
    return (f"#{nombre} {{ background: {tk.surface_alt}; border: 1px solid {tk.border_soft}; border-radius: 8px;"
            f" {izq} }}")


def texto_en_tarjeta(browser):
    """Un QTextBrowser dentro de una tarjeta: sin borde ni fondo propio (se ve la tarjeta)."""
    browser.setFrameShape(QtWidgets.QFrame.NoFrame)
    browser.setStyleSheet("QTextBrowser { background: transparent; border: none; padding: 0; }")
    browser.viewport().setAutoFillBackground(False)


def chip_qss(tk=None):
    tk = tk or theme.tokens()
    return (f"QPushButton {{ background: {tk.surface_alt}; color: {tk.text}; border: 1px solid {tk.border};"
            f" border-radius: 15px; padding: 6px 14px; font-weight: normal; text-align: left; }}"
            f" QPushButton:hover {{ background: {tk.soft}; color: {tk.soft_text}; border: 1px solid {tk.accent}; }}")


def etiqueta_seccion(texto):
    lbl = QtWidgets.QLabel(texto)
    al_cambiar_tema(lbl, lambda: lbl.setStyleSheet(
        f"color: {theme.tokens().text_muted}; font-size: 12px; font-weight: 600; letter-spacing: 0.5px;"
        f" background: transparent;"))
    return lbl


class Encabezado(QtWidgets.QFrame):
    """Icono + título + subtítulo. `subtitulo` puede ser un QLabel ya creado (p. ej. el estado de la IA)."""

    def __init__(self, icono, titulo, subtitulo="", parent=None):
        super().__init__(parent)
        self.icono = icono
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(12)
        self.circulo = QtWidgets.QLabel()
        self.circulo.setFixedSize(CIRCULO_PX, CIRCULO_PX)
        self.circulo.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.circulo, 0, QtCore.Qt.AlignTop)
        textos = QtWidgets.QVBoxLayout()
        textos.setSpacing(2)
        self.titulo = QtWidgets.QLabel(titulo)
        self.titulo.setAccessibleName(titulo)
        if isinstance(subtitulo, QtWidgets.QLabel):
            self.subtitulo = subtitulo
        else:
            self.subtitulo = QtWidgets.QLabel(subtitulo)
            self.subtitulo.setVisible(bool(subtitulo))
        self.subtitulo.setWordWrap(True)
        textos.addWidget(self.titulo)
        textos.addWidget(self.subtitulo)
        lay.addLayout(textos, 1)
        self.derecha = QtWidgets.QHBoxLayout()          # botones de la cabecera (opcional)
        self.derecha.setSpacing(4)
        lay.addLayout(self.derecha)
        al_cambiar_tema(self, self._estilo)

    def _estilo(self):
        tk = theme.tokens()
        self.circulo.setStyleSheet(f"background: {tk.soft}; border-radius: {CIRCULO_PX // 2}px;")
        self.circulo.setPixmap(pix(self.icono, tk.soft_text if theme.is_dark() else tk.accent))
        self.titulo.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {tk.text}; background: transparent;")
        self.subtitulo.setStyleSheet(f"color: {tk.text_muted}; background: transparent;")
        self.setStyleSheet("Encabezado { background: transparent; }")


def boton_icono(nombre, tip, fn, color=None):
    """Botón plano de solo icono (cabeceras), con su globo y nombre accesible."""
    b = QtWidgets.QToolButton()
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setAutoRaise(True)
    b.setIconSize(QtCore.QSize(20, 20))
    b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
    b.clicked.connect(fn)
    al_cambiar_tema(b, lambda: b.setIcon(icons.icon(nombre, color=color or theme.tokens().text_muted)))
    return b
