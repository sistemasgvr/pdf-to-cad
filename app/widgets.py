"""widgets.py — Widgets Qt reutilizables y autocontenidos de la UI.

Piezas pequeñas que no dependen de la ventana principal (solo de PySide6):
- InlineEdit: editor de texto embebido (Enter aplica, Shift+Enter salto de línea).
- _SegInvSpinBox: spinbox de la tabla "Cotas por tramo" (Enter confirma en celda).
- _NoWheelFilter: filtro global que bloquea la rueda sobre spinboxes/combos.
- ZoomPanView: QGraphicsView de solo lectura con zoom (rueda) y pan (botón
  central). La usan las vistas previas del asistente (capas de la hoja y
  reconocimiento). Movida verbatim desde recognition_dialog._PreviewView.

Extraído de app_window.py sin cambios de comportamiento (solo reubicación).
"""
from PySide6 import QtCore, QtGui, QtWidgets

import theme as _theme


class InlineEdit(QtWidgets.QTextEdit):
    """Editor embebido. Enter = aplicar; Ctrl+Shift+Enter o Shift+Enter = salto de
    línea. El commit se difiere con un timer para no destruir el widget dentro de
    su propio evento (eso provocaba cierres inesperados)."""
    committed = QtCore.Signal(str)

    def __init__(self, text):
        super().__init__(); self.setPlainText(text); self._done = False
        self._apply_theme()
        _theme.THEME_BUS.changed.connect(self._apply_theme)

    def _apply_theme(self, *_):
        t = _theme.tokens()
        self.setStyleSheet(f"background:{t.input_bg};color:{t.success};"
                           f"border:2px solid {t.focus};border-radius:3px;")

    def _commit(self):
        if not self._done:
            self._done = True; txt = self.toPlainText()
            QtCore.QTimer.singleShot(0, lambda: self.committed.emit(txt))

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            m = e.modifiers()
            if (m & QtCore.Qt.ShiftModifier):     # Shift(+Ctrl)+Enter → salto de línea
                self.insertPlainText("\n"); return
            self._commit(); return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e); self._commit()


class _SegInvSpinBox(QtWidgets.QDoubleSpinBox):
    """QDoubleSpinBox de la tabla "Cotas por tramo": Enter/Return confirma el
    valor tecleado ahí mismo. Embebido en una celda de QTableWidget (vía
    setCellWidget), el widget contenedor puede quedarse con la tecla Enter
    antes de que dispare editingFinished normalmente — se maneja acá a mano
    para no depender de esa cadena de eventos."""
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.interpretText()
            event.accept()
            # Diferido: el slot conectado reconstruye la tabla (destruye este
            # mismo spinbox) — no hacerlo en medio de este keyPressEvent.
            QtCore.QTimer.singleShot(0, self.editingFinished.emit)
            return
        super().keyPressEvent(event)


class _NoWheelFilter(QtCore.QObject):
    """Bloquea la rueda del ratón sobre QSpinBox / QDoubleSpinBox / QComboBox
    (y sus derivados). Motivo: al desplazarse por un panel con la rueda,
    quedar el puntero sobre uno de esos campos incrementa/decrementa el valor
    o cambia el item del combo sin querer — el usuario perdía datos ya
    introducidos por un gesto que solo pretendía mover la vista.

    Se instala una sola vez sobre la QApplication y cubre TODOS los widgets
    existentes y futuros, sin tener que subclasificarlos uno por uno. El
    evento wheel se ignora en esos widgets (así lo hereda el padre y sigue
    desplazando el panel); en el resto de widgets pasa tal cual.
    """
    _WHEEL_BLOCKED = (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox)

    def eventFilter(self, obj, ev):
        if (ev.type() == QtCore.QEvent.Wheel
                and isinstance(obj, self._WHEEL_BLOCKED)):
            ev.ignore()
            return True
        return False


class ZoomPanView(QtWidgets.QGraphicsView):
    """Vista previa con zoom (rueda) y pan (botón central). Sin edición."""
    viewChanged = QtCore.Signal()
    def __init__(self):
        super().__init__()
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHints(
            QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self._pan = False
        self._pan0 = None

    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)
        self.viewChanged.emit()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.viewChanged.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.viewChanged.emit()

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = True
            self._pan0 = e.position().toPoint()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan and self._pan0 is not None:
            d = e.position().toPoint() - self._pan0
            self._pan0 = e.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = False
            self._pan0 = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)
