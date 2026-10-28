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
  · `NoEscapeClose`: las ventanas de los pasos no se cierran con Esc.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr, N_
from ui.comun.icons import icon as _icon
from ui.comun import theme as _theme

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


class NoEscapeClose:
    """Mezcla para las VENTANAS de los pasos del asistente (Componer hoja, Capas
    de la hoja, Vista previa): Esc no las cierra (pedido del usuario 2026-10-05:
    un toque sin querer tiraba el paso entero y volvía al editor). Si la ventana
    tiene algo que Esc deba deshacer (un resaltado), lo hace `_escape()`. Los
    controles que ya usan Esc (medir, menús, desplegables) la reciben antes; las
    preguntas y los cuadros chicos («Ajustar capas…», «¿Tomar el área?») siguen
    cerrando con Esc. Para salir quedan «Cancelar» y la X de la ventana."""

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape or event.matches(QtGui.QKeySequence.Cancel):
            self._escape()
            event.accept()
            return
        super().keyPressEvent(event)

    def _escape(self) -> bool:
        """Lo que Esc deshace en esta ventana (True si hizo algo). Nada por defecto."""
        return False


class StepBar(QtWidgets.QWidget):
    """Migas de pan del asistente. `stepClicked(i)` al pulsar un paso anterior."""
    stepClicked = QtCore.Signal(int)

    def __init__(self, current: int, back_enabled: bool = True, parent=None):
        super().__init__(parent)
        t = _theme.tokens()
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(4)
        row.addStretch(1)                              # 2.0.0: pasos centrados, como el prototipo
        self.buttons: list[QtWidgets.QToolButton] = []
        for i, name in enumerate(WIZARD_STEPS):
            if i:
                sep = QtWidgets.QLabel("›")
                sep.setStyleSheet(f"color:{t.text3}; font-size:15px; background: transparent;")
                row.addWidget(sep)
            btn = QtWidgets.QToolButton()
            done = i < current
            clickable = done and back_enabled
            # paso hecho = BOTÓN con el tinte del acento y ✓ (pedido del usuario 2026-10-14: subrayado
            # parecía un enlace y en el tema oscuro no se leía); el actual, relleno de acento
            btn.setText(("✓ " if done else "") + f"{i + 1}  {_tr(name)}")
            btn.setAutoRaise(False)
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            if i == current:
                css = (f"QToolButton {{ background:{t.soft}; color:{t.soft_text}; font-weight:600;"
                       f" border:none; border-radius:15px; padding:5px 14px; }}")
            elif done:
                css = (f"QToolButton {{ background:transparent; color:{t.text}; border:none;"
                       f" border-radius:15px; padding:5px 14px; }}"
                       f" QToolButton:hover {{ background:{t.hover}; }}"
                       f" QToolButton:disabled {{ color:{t.text_muted}; }}")
            else:
                css = (f"QToolButton {{ background:transparent; color:{t.text3}; border:none;"
                       f" padding:5px 10px; }}")
            btn.setStyleSheet(css)
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
    line.setStyleSheet(f"color:{_theme.tokens().border_soft};")
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
    line.setStyleSheet(f"color:{_theme.tokens().border_soft};")
    col.addWidget(line)
    row = QtWidgets.QHBoxLayout(); row.setSpacing(10)
    for x in left:
        row.addWidget(x)
    lbl = QtWidgets.QLabel(hint)
    lbl.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
    lbl.setWordWrap(True)
    row.addWidget(lbl, 1)
    for k, b in enumerate(buttons):
        b.setMinimumSize(130, 34)
        if k == len(buttons) - 1 and not b.property("danger") and not b.property("secondary"):
            b.setProperty("kind", "primary")           # 2.0.0: avanzar = la acción principal, en color
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


# ── 2.0.0: herramientas FLOTANTES sobre la hoja (como el prototipo) ──────────
class _Flotador(QtCore.QObject):
    def __init__(self, vista, widget, donde, margen):
        super().__init__(vista)
        self.vista, self.widget, self.donde, self.margen = vista, widget, donde, margen
        vista.installEventFilter(self)
        widget.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.LayoutRequest):
            QtCore.QTimer.singleShot(0, self.colocar)
        return False

    def colocar(self):
        v, w, m = self.vista, self.widget, self.margen
        try:
            hint = w.sizeHint()
        except RuntimeError:
            return
        W, H = v.width(), v.height()
        ancho = w.minimumWidth() if w.minimumWidth() == w.maximumWidth() else hint.width()
        if ancho > W - 2 * m:                      # nunca más ancha que la vista (lo que no quepa se recorta)
            ancho = max(w.minimumSizeHint().width(), W - 2 * m)
        # texto que se parte en líneas: el alto que de verdad necesita a ese ancho
        alto = (max(w.heightForWidth(ancho), w.minimumSizeHint().height()) if w.hasHeightForWidth()
                else hint.height())
        if (w.width(), w.height()) != (ancho, alto):   # solo si cambia (cada resize vuelve a llamar aquí)
            w.resize(ancho, alto)
        if self.donde == "arriba":
            w.move(max(m, (W - w.width()) // 2), m)
        elif self.donde == "abajo":
            w.move(max(m, (W - w.width()) // 2), H - w.height() - m)
        elif self.donde == "arriba_derecha":
            w.move(max(m, W - w.width() - m - 14), m)
        w.raise_()


def flotar(vista: QtWidgets.QWidget, widget: QtWidgets.QWidget, donde: str = "abajo", margen: int = 12):
    """Pone `widget` (sus botones de siempre) flotando sobre `vista`: «abajo»/«arriba» (al centro) o «arriba_derecha»."""
    oculto = widget.testAttribute(QtCore.Qt.WA_WState_ExplicitShowHide) and widget.isHidden()                    # se respeta: p. ej. una tarjeta que aparece sola
    widget.setParent(vista)
    f = _Flotador(vista, widget, donde, margen)
    widget.setVisible(not oculto)
    f.colocar()
    return f


def pastilla(widgets) -> QtWidgets.QFrame:
    """Una pastilla flotante (QFrame#flotante) con esos widgets en fila."""
    t = _theme.tokens()
    f = QtWidgets.QFrame()
    f.setObjectName("flotante")
    f.setStyleSheet(f"QFrame#flotante {{ background:{t.surface}; border:1px solid {t.border}; border-radius:12px; }}")
    lay = QtWidgets.QHBoxLayout(f)
    lay.setContentsMargins(8, 5, 8, 5)
    lay.setSpacing(6)
    for w in widgets:
        if isinstance(w, QtWidgets.QLayoutItem):
            continue
        lay.addWidget(w)
    return f
