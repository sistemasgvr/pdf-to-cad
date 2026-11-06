"""Símbolo de una válvula de compuerta en el lienzo (2026-11-04): el «moño» (dos triángulos) a lo largo de la
tubería, con su largo y su brida REALES en el plano. Alejado, cuando el real mide menos de `MIN_PX` en
pantalla, lo pinta en su lugar un moño de `MIN_PX` (ítem aparte que ignora el zoom), para que siempre se vea.
Cada ítem tiene su caja fija: ninguno cambia de tamaño con el zoom."""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

MIN_PX = 14.0                  # largo mínimo en pantalla


def _escala_vista(item):
    sc = item.scene()
    vistas = sc.views() if sc is not None else []
    return vistas[0].transform().m11() if vistas else 1.0


def _moño(painter, L, H, color, ok, hueca=False):
    """`hueca` = reconocida «por confirmar» (sin relleno, borde de su color a trazos)."""
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(20, 20, 20) if ok else QtGui.QColor(230, 40, 40), 1.6)
    if ok and hueca:
        pen = QtGui.QPen(QtGui.QColor(color), 1.8, QtCore.Qt.DashLine)
    pen.setCosmetic(True)
    painter.setPen(pen)
    relleno = QtGui.QColor(color)
    if hueca:
        relleno.setAlpha(40)
    painter.setBrush(relleno if ok else QtGui.QColor(230, 40, 40, 90))
    a, h = L / 2, H / 2
    painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(-a, -h), QtCore.QPointF(0, 0), QtCore.QPointF(-a, h)]))
    painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(a, -h), QtCore.QPointF(0, 0), QtCore.QPointF(a, h)]))
    painter.drawLine(QtCore.QPointF(0, 0), QtCore.QPointF(0, -h * 0.9))                 # vástago
    painter.drawLine(QtCore.QPointF(-h * 0.3, -h * 0.9), QtCore.QPointF(h * 0.3, -h * 0.9))


class ValvulaItem(QtWidgets.QGraphicsItem):
    """Moño de tamaño real (`fijo=False`, px del plano) o de `MIN_PX` en pantalla (`fijo=True`); cada uno se
    pinta solo cuando le toca."""

    def __init__(self, x, y, ux, uy, largo, alto, color, ok=True, fijo=False, hueca=False):
        super().__init__()
        self._real = (float(largo), float(alto))
        self._fijo = fijo
        if fijo:
            k = MIN_PX / max(float(largo), 1e-9)
            self._L, self._H = MIN_PX, float(alto) * k
            self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        else:
            self._L, self._H = self._real
        self._color, self._ok, self._hueca = QtGui.QColor(color), ok, hueca
        self.setPos(float(x), float(y))
        self.setRotation(math.degrees(math.atan2(uy, ux)))

    def _real_pequeña(self):
        return self._real[0] * _escala_vista(self) < MIN_PX

    def boundingRect(self):
        m = max(self._L, self._H) / 2 + 2.0
        return QtCore.QRectF(-m, -m, 2 * m, 2 * m)

    def shape(self):
        p = QtGui.QPainterPath()
        p.addRect(QtCore.QRectF(-self._L / 2, -self._H / 2, self._L, self._H))
        return p

    def paint(self, painter, _opcion, _widget=None):
        if self._real_pequeña() != self._fijo:      # le toca al otro
            return
        _moño(painter, self._L, self._H, self._color, self._ok, self._hueca)


def agregar(scene, x, y, ux, uy, largo, alto, color, ok, z, globo="", hueca=False):
    """Los dos ítems de una válvula (real y mínimo), en la escena; devuelve la lista (va al overlay)."""
    out = []
    for fijo in (False, True):
        it = ValvulaItem(x, y, ux, uy, largo, alto, color, ok, fijo, hueca)
        it.setZValue(z)
        if globo:
            it.setToolTip(globo)
        scene.addItem(it)
        out.append(it)
    return out
