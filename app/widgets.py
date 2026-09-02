"""widgets.py — Widgets Qt reutilizables y autocontenidos de la UI.

Piezas pequeñas que no dependen de la ventana principal (solo de PySide6):
- InlineEdit: editor de texto embebido (Enter aplica, Shift+Enter salto de línea).
- _SegInvSpinBox: spinbox de la tabla "Cotas por tramo" (Enter confirma en celda).
- _NoWheelFilter: filtro global que bloquea la rueda sobre spinboxes/combos.

Extraído de app_window.py sin cambios de comportamiento (solo reubicación).
"""
from PySide6 import QtCore, QtWidgets


class InlineEdit(QtWidgets.QTextEdit):
    """Editor embebido. Enter = aplicar; Ctrl+Shift+Enter o Shift+Enter = salto de
    línea. El commit se difiere con un timer para no destruir el widget dentro de
    su propio evento (eso provocaba cierres inesperados)."""
    committed = QtCore.Signal(str)

    def __init__(self, text):
        super().__init__(); self.setPlainText(text); self._done = False
        self.setStyleSheet("background:#111;color:#7f7;border:1px solid #7f7;")

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
