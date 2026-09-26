"""wizard_widgets.py — piezas de UI compartidas por los pasos del asistente de
PDF vectorial (Componer hoja → Capas de la hoja → Vista previa) y el editor.

  · `StepBar`: barra «1 Componer hoja › 2 Capas de la hoja › 3 Vista previa»
    con el paso actual resaltado; los pasos ANTERIORES son clicables para
    volver (pedido del usuario: «no podemos volver a la pantalla anterior»).
  · `show_opacity_popup`: el desplegable de opacidad del PDF del editor
    (deslizable 10–100 % + botón fondo blanco/negro), movido aquí tal cual para
    que el editor, «Capas de la hoja» y la vista previa usen EXACTAMENTE el mismo.
  · `OpacityButton`: botón «Opacidad» para una vista con un PDF de fondo
    (un QGraphicsPixmapItem): maneja la opacidad del item y un rectángulo de
    fondo blanco/negro debajo de él, igual que `canvas.Canvas`.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr, N_
from icons import icon as _icon
import theme as _theme

# Pasos del asistente (textos traducibles; `_tr` al mostrar).
WIZARD_STEPS = (N_("Componer hoja"), N_("Capas de la hoja"), N_("Vista previa"))

_SLIDER_QSS = (
    "QSlider::groove:horizontal { height: 10px; border-radius: 5px;"
    " background: #202020; border: 1px solid #6a6a6a; }"
    "QSlider::sub-page:horizontal { background: #4a90ff; border: 1px solid #8ec2ff;"
    " border-radius: 5px; }"
    "QSlider::add-page:horizontal { background: #2b2b2b; border: 1px solid #565656;"
    " border-radius: 5px; }"
    "QSlider::handle:horizontal { width: 26px; height: 22px; margin: -7px 0;"
    " border-radius: 6px; background: #ffffff; border: 2px solid #2f6ad9; }"
    "QSlider::handle:horizontal:hover { background: #eaf1ff; border: 2px solid #6ba3ff; }"
    "QSlider::handle:horizontal:pressed { background: #cfe0ff; border: 2px solid #8ec2ff; }")


class StepBar(QtWidgets.QWidget):
    """Migas de pan del asistente. `stepClicked(i)` al pulsar un paso anterior."""
    stepClicked = QtCore.Signal(int)

    def __init__(self, current: int, back_enabled: bool = True, parent=None):
        super().__init__(parent)
        t = _theme.tokens()
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(4)
        self.buttons: list[QtWidgets.QToolButton] = []
        for i, name in enumerate(WIZARD_STEPS):
            if i:
                sep = QtWidgets.QLabel("›")
                sep.setStyleSheet(f"color:{t.text_muted}; font-size:15px;")
                row.addWidget(sep)
            btn = QtWidgets.QToolButton()
            btn.setText(f"{i + 1}  {_tr(name)}")
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            done = i < current
            clickable = done and back_enabled
            if i == current:
                style = (f"background:{t.accent}; color:{t.text_on_accent}; font-weight:bold;"
                         " border-radius:12px; padding:3px 12px;")
            elif done:
                style = (f"color:{t.accent}; padding:3px 8px; border-radius:12px;"
                         + (" text-decoration: underline;" if clickable else ""))
            else:
                style = f"color:{t.text_muted}; padding:3px 8px;"
            btn.setStyleSheet(f"QToolButton {{ {style} }}")
            btn.setEnabled(clickable or i == current)
            if clickable:
                btn.setCursor(QtCore.Qt.PointingHandCursor)
                btn.setToolTip(_tr("Volver a «{paso}»").format(paso=_tr(name)))
                btn.clicked.connect(lambda _c=False, i=i: self.stepClicked.emit(i))
            row.addWidget(btn)
            self.buttons.append(btn)
        row.addStretch(1)


def wizard_header(steps: StepBar) -> QtWidgets.QWidget:
    """Cabecera de un paso del asistente: la barra de pasos a TODO el ancho de
    la ventana (en el panel lateral se cortaba: «Comp…er hoja») con una línea
    debajo. Es la ÚNICA navegación hacia atrás (un botón «◀» aparte la repetía)."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)
    lay.addWidget(steps)
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setStyleSheet(f"color:{_theme.tokens().border};")
    lay.addWidget(line)
    return w


def wizard_footer(left: list, hint: str, buttons: list) -> QtWidgets.QWidget:
    """Pie de un paso del asistente, a todo el ancho: opciones de vista a la
    izquierda (p. ej. «Opacidad»), una ayuda breve y los botones de decisión a
    la derecha (Cancelar · Continuar)."""
    w = QtWidgets.QWidget()
    col = QtWidgets.QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0); col.setSpacing(8)
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setStyleSheet(f"color:{_theme.tokens().border};")
    col.addWidget(line)
    row = QtWidgets.QHBoxLayout(); row.setSpacing(10)
    for x in left:
        row.addWidget(x)
    lbl = QtWidgets.QLabel(hint)
    lbl.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
    lbl.setWordWrap(True)
    row.addWidget(lbl, 1)
    for b in buttons:
        b.setMinimumSize(130, 34)
        row.addWidget(b)
    col.addLayout(row)
    return w


def show_opacity_popup(anchor: QtWidgets.QWidget, opacity: float, on_opacity: Callable[[float], None],
                       is_black: Callable[[], bool], on_toggle_bg: Callable[[], None],
                       above: bool = True, on_value_text: Optional[Callable[[int], None]] = None):
    """Desplegable de opacidad del PDF (el del editor, tal cual): deslizable
    10–100 % y botón para alternar el fondo detrás del PDF entre blanco y negro.
    `above`: se abre encima del botón (barra de estado abajo) o debajo."""
    menu = QtWidgets.QMenu(anchor)
    box = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(box); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(8)
    pct = round(opacity * 100)
    lbl = QtWidgets.QLabel(_tr("Opacidad del PDF: {pct}%").format(pct=pct))
    sl = QtWidgets.QSlider(QtCore.Qt.Horizontal); sl.setRange(10, 100)
    sl.setValue(pct); sl.setMinimumWidth(240)
    # Accesibilidad: más contraste (canal oscuro + parte activa azul brillante)
    # y un handle más ancho/visible, fácil de agarrar. Solo estético.
    sl.setStyleSheet(_SLIDER_QSS)

    def _on_val(v):
        on_opacity(v / 100.0)
        lbl.setText(_tr("Opacidad del PDF: {pct}%").format(pct=v))
        if on_value_text is not None:
            on_value_text(v)
    sl.valueChanged.connect(_on_val)

    btn_bg = QtWidgets.QPushButton()

    def _refresh_bg_btn():
        # El texto muestra la acción que hará el clic (viceversa del estado actual).
        btn_bg.setText(_tr("Fondo blanco") if is_black() else _tr("Fondo negro"))

    def _toggle_bg():
        on_toggle_bg()
        _refresh_bg_btn()
    btn_bg.clicked.connect(_toggle_bg)
    _refresh_bg_btn()

    lay.addWidget(lbl); lay.addWidget(sl); lay.addWidget(btn_bg)
    wa = QtWidgets.QWidgetAction(menu); wa.setDefaultWidget(box); menu.addAction(wa)
    pos = anchor.mapToGlobal(QtCore.QPoint(0, 0))
    if above:
        # Se abre encima del botón; Qt reubica solo si no cabe.
        menu.exec(QtCore.QPoint(pos.x(), pos.y() - menu.sizeHint().height()))
    else:
        menu.exec(QtCore.QPoint(pos.x(), pos.y() + anchor.height()))
    return sl


class OpacityButton(QtWidgets.QPushButton):
    """«Opacidad» para una vista con el PDF de fondo. `pixmap_item()` devuelve el
    QGraphicsPixmapItem del PDF (puede cambiar de imagen: llamar a `sync()` tras
    cada render). Debajo se mantiene un rectángulo blanco/negro de su tamaño."""

    def __init__(self, pixmap_item: Callable[[], Optional[QtWidgets.QGraphicsPixmapItem]], parent=None):
        super().__init__(_icon("mdi:circle-half-full"), _tr("Opacidad"), parent)
        self.setProperty("secondary", True)
        self.setToolTip(_tr("Opacidad del PDF y color de fondo (blanco/negro)"))
        self.setMinimumHeight(32)
        self._item = pixmap_item
        self.opacity = 1.0
        self.bg_color = QtGui.QColor(255, 255, 255)
        self._bg: Optional[QtWidgets.QGraphicsRectItem] = None
        self.clicked.connect(self._open)

    @property
    def backdrop(self) -> Optional[QtWidgets.QGraphicsRectItem]:
        """Rectángulo de fondo (quien limpia la escena debe conservarlo)."""
        return self._bg

    def is_black(self) -> bool:
        return self.bg_color.value() < 128

    def set_opacity(self, value: float):
        self.opacity = max(0.1, min(1.0, float(value)))
        self.sync()

    def toggle_bg(self):
        self.bg_color = QtGui.QColor(255, 255, 255) if self.is_black() else QtGui.QColor(0, 0, 0)
        self.sync()

    def sync(self):
        """Aplica opacidad y fondo al item actual del PDF (tras cada render)."""
        item = self._item()
        if item is None or item.scene() is None:
            return
        item.setOpacity(self.opacity)
        rect = item.mapRectToScene(item.boundingRect())
        if self._bg is None or self._bg.scene() is not item.scene():
            self._bg = item.scene().addRect(rect, QtGui.QPen(QtCore.Qt.NoPen), QtGui.QBrush(self.bg_color))
        else:
            self._bg.setRect(rect)
            self._bg.setBrush(QtGui.QBrush(self.bg_color))
        self._bg.setZValue(item.zValue() - 1)
        self.setText(_tr("Opacidad") if self.opacity >= 0.999
                     else _tr("Opacidad {pct}%").format(pct=round(self.opacity * 100)))

    def _open(self):
        show_opacity_popup(self, self.opacity, self.set_opacity, self.is_black, self.toggle_bg, above=False)
