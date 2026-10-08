"""composite_measure.py — herramienta de dos clics de la hoja compuesta.

Modos (uno a la vez, los elige el diálogo):

  - «measure»: dos clics → distancia en pies (escala de la hoja compuesta) y
    rumbo. La línea y su rótulo quedan a la vista hasta el próximo clic; si los
    dos puntos caen en la misma pieza, el diálogo ofrece «Calibrar escala».
  - «straighten»: dos clics sobre una línea de UNA pieza que debería ir
    horizontal o vertical → el diálogo la gira (eje más cercano, automático).

Entre el primer y el segundo clic la línea sigue al ratón con su lectura
(rótulo de tamaño fijo). Shift = la deja horizontal/vertical. Esc cancela el
punto pendiente; con nada pendiente, sale de la herramienta.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ui.asistente.alignment_tools import MeasureTag
from traduccion.i18n import t as _tr

MODES = ("measure", "straighten")


def bearing(a, b) -> float:
    """Rumbo de a→b (°, antihorario, y hacia abajo) llevado a (−90, 90]."""
    ang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
    ang = (ang + 90.0) % 180.0 - 90.0
    return 90.0 if ang == -90.0 else ang


def constrain(a, b) -> Tuple[float, float]:
    """Shift: el segundo punto alineado con el primero en horizontal o vertical."""
    return (b[0], a[1]) if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else (a[0], b[1])


class MeasureTool(QtCore.QObject):
    measured = QtCore.Signal(int, object, object)      # pieza (−1 si no es una sola), a, b
    straighten = QtCore.Signal(int, object, object)
    cleared = QtCore.Signal()
    exited = QtCore.Signal()

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.mode: Optional[str] = None
        self.result = None                 # (pieza, a, b) de la última medida
        self._start = None                 # (pieza, a) del primer clic
        pen = QtGui.QPen(QtGui.QColor("#00a3c4"), 2)
        pen.setCosmetic(True)
        self._line = QtWidgets.QGraphicsLineItem()
        self._line.setPen(pen)
        self._line.setZValue(215)
        self._line.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self._tag = MeasureTag()
        for it in (self._line, self._tag):
            view.scene().addItem(it)
            it.hide()

    # ── estado ──────────────────────────────────────────────────────────
    def set_mode(self, mode: Optional[str]):
        self.mode = mode if mode in MODES else None
        self.clear()
        self.apply_cursor()

    def apply_cursor(self):
        """Cruz en todo el lienzo mientras la herramienta está activa (las piezas
        tienen su propia mano de arrastre, que aquí no corresponde)."""
        cross = QtCore.Qt.CrossCursor
        self.view.viewport().setCursor(cross if self.mode else QtCore.Qt.ArrowCursor)
        for it in self.view.items:
            it.setCursor(cross if self.mode else QtCore.Qt.OpenHandCursor)

    def clear(self):
        had = self.result is not None or self._start is not None
        self._start = None
        self.result = None
        self._line.hide()
        self._tag.hide()
        if had:
            self.cleared.emit()

    def pending(self) -> bool:
        return self._start is not None

    def cancel(self) -> bool:
        """Esc: suelta el punto pendiente o la medida; si no había nada, sale
        de la herramienta. True = el Esc se usó (el diálogo no debe cerrarse)."""
        if self._start is not None or self.result is not None:
            self.clear()
            return True
        if self.mode:
            self.exited.emit()
            return True
        return False

    # ── lectura ─────────────────────────────────────────────────────────
    def label(self, a, b) -> str:
        feet = math.hypot(b[0] - a[0], b[1] - a[1]) * self.view.comp.target_scale()
        return _tr("{d:.2f} ft · {a:.2f}°").format(d=feet, a=bearing(a, b))

    def _show(self, a, b):
        self._line.setLine(a[0], a[1], b[0], b[1])
        self._line.show()
        self._tag.set_text(self.label(a, b))
        self._tag.setPos((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        self._tag.show()

    # ── ratón ───────────────────────────────────────────────────────────
    def press(self, point: QtCore.QPointF, piece: int, modifiers) -> bool:
        """Clic izquierdo con la herramienta activa. True = consumido."""
        if not self.mode:
            return False
        p = (point.x(), point.y())
        if self._start is None:
            if self.mode == "straighten" and piece < 0:
                return True                # hay que empezar sobre una pieza
            self.clear()
            self._start = (piece, p)
            if self.mode == "straighten":
                self.view.select(piece)        # se ve qué pieza va a girar
            self._show(p, p)
            return True
        index, a = self._start
        if modifiers & QtCore.Qt.ShiftModifier:
            p = constrain(a, p)
        self._start = None
        if math.hypot(p[0] - a[0], p[1] - a[1]) < 1e-6:
            self.clear()
            return True
        if self.mode == "straighten":
            self.clear()
            self.straighten.emit(index, a, p)
            return True
        self._show(a, p)
        self.result = (index if piece == index else -1, a, p)
        self.measured.emit(*self.result)
        return True

    def move(self, point: QtCore.QPointF, modifiers):
        if self._start is None:
            return
        a = self._start[1]
        p = (point.x(), point.y())
        if modifiers & QtCore.Qt.ShiftModifier:
            p = constrain(a, p)
        self._show(a, p)
