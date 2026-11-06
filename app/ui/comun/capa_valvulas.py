"""capa_valvulas.py — las válvulas en el lienzo: un solo ítem de la escena (como `capa_lineas`).

Cada válvula es un moño (dos triángulos que se tocan en el centro) a lo largo de su tubería, del color de su utilidad y
de tamaño fijo en pantalla. Lleno = segura; hueco = por confirmar. Encender o apagar la capa es `setVisible`.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

RADIO_PX = 7.0                     # medio largo del moño en pantalla
MARGEN = 300.0                     # holgura de la caja: el moño no escala con el zoom


def mono(x, y, r, rumbo_deg) -> QtGui.QPolygonF:
    """Lazo del moño centrado en (x, y); `rumbo_deg` con la y hacia arriba, como `valvulas.relacion`."""
    a = math.radians(rumbo_deg)
    ux, uy = math.cos(a), -math.sin(a)
    nx, ny = -uy * 0.62, ux * 0.62
    puntos = [(ux + nx, uy + ny), (ux - nx, uy - ny), (-ux + nx, -uy + ny), (-ux - nx, -uy - ny)]
    return QtGui.QPolygonF([QtCore.QPointF(x + r * px, y + r * py) for px, py in puntos])


class CapaValvulas(QtWidgets.QGraphicsItem):
    """`entradas` = [(x, y, rumbo, QColor, hueca)]."""

    def __init__(self, z, entradas, elegida=-1):
        super().__init__()
        self.entradas = entradas
        self.elegida = elegida
        self.setZValue(z)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self.setFlag(QtWidgets.QGraphicsItem.ItemUsesExtendedStyleOption)
        xs = [e[0] for e in entradas] or [0.0]
        ys = [e[1] for e in entradas] or [0.0]
        self._caja = QtCore.QRectF(min(xs) - MARGEN, min(ys) - MARGEN, max(xs) - min(xs) + 2 * MARGEN,
                                   max(ys) - min(ys) + 2 * MARGEN)

    def boundingRect(self):
        return self._caja

    def paint(self, painter, option, _widget=None):
        escala = max(1e-6, painter.worldTransform().m11() or abs(painter.worldTransform().m12()))
        r = RADIO_PX / escala
        vista = option.exposedRect.adjusted(-2 * r, -2 * r, 2 * r, 2 * r)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        for k, (x, y, rumbo, color, hueca) in enumerate(self.entradas):
            if not vista.contains(x, y):
                continue
            pluma = QtGui.QPen(color, 1.6)
            pluma.setCosmetic(True)
            painter.setPen(pluma)
            painter.setBrush(QtCore.Qt.NoBrush if hueca else QtGui.QBrush(color))
            painter.drawPolygon(mono(x, y, r, rumbo))
            if k == self.elegida:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawEllipse(QtCore.QPointF(x, y), r * 1.7, r * 1.7)
