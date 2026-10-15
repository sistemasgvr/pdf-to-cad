"""Marcas de vértices, buzones y asas en el lienzo con TOPE de tamaño en pantalla.

Pedido del usuario 2026-10-15: al acercarse mucho, los vértices y buzones (círculos de
radio fijo EN EL PLANO) se veían enormes y tapaban los tramos cortos; alejado se veían
bien. `Marca` mide R en px del plano, como antes, pero al pintar no pasa de `tope_px`
píxeles de PANTALLA: lejos se ve exactamente igual que antes y de cerca deja de crecer.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

TOPE_PX = 8.0                 # radio máximo en pantalla de un buzón/vértice (px)
TOPE_ASA_PX = 6.0             # medio lado máximo de un asa de edición (px)


class Marca(QtWidgets.QGraphicsItem):
    """Círculo (o cuadrado) centrado en (x, y) de radio `r` px del plano, que en pantalla
    no pasa de `tope_px`."""

    def __init__(self, x, y, r, pen, brush, tope_px=TOPE_PX, cuadrada=False):
        super().__init__()
        self._r, self._tope = float(r), float(tope_px)
        self._pen, self._brush, self._cuadrada = QtGui.QPen(pen), QtGui.QBrush(brush), cuadrada
        self.setPos(float(x), float(y))

    def radio_en(self, escala):
        """Radio en px del plano con la vista a `escala` (px de pantalla por px del plano)."""
        return min(self._r, self._tope / escala) if escala > 1e-9 else self._r

    def boundingRect(self):
        m = self._r + max(self._pen.widthF(), 1.0) + 1.0
        return QtCore.QRectF(-m, -m, 2 * m, 2 * m)

    def paint(self, painter, _opcion, _widget=None):
        t = painter.worldTransform()
        r = self.radio_en(math.hypot(t.m11(), t.m12()))
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(self._pen)
        painter.setBrush(self._brush)
        caja = QtCore.QRectF(-r, -r, 2 * r, 2 * r)
        if self._cuadrada:
            painter.drawRect(caja)
        else:
            painter.drawEllipse(caja)


def agregar(scene, x, y, r, pen, brush, z, tope_px=TOPE_PX, cuadrada=False):
    """Crea la marca, la pone en `scene` con su Z y la devuelve (va al overlay)."""
    it = Marca(x, y, r, pen, brush, tope_px, cuadrada)
    it.setZValue(z)
    scene.addItem(it)
    return it
