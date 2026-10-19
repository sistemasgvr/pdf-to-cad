"""Las utilidades del lienzo en UNA capa (pedido del usuario 2026-10-18, proyecto de 16 761 utilidades:
cada segmento era un `QGraphicsLineItem` —~27 mil ítems— y abrir, el zoom y la cruz del cursor los
recorrían todos).

`CapaLineas` es un solo ítem de la escena que pinta, en el MISMO orden de antes (el de las utilidades),
cada segmento con la MISMA pluma cosmética y la misma llamada de dibujo (`drawLines`, segmento por
segmento: mismas puntas que un `QGraphicsLineItem` cada uno), así que se ve igual. Solo pinta las
utilidades cuya caja toca lo que hay que repintar (con la cruz, dos franjas finas: el recorte del
sistema va en px FÍSICOS de la ventana, ver `capa_marcas`). No da tooltip ni se elige con el ratón:
los segmentos de antes tampoco (la ventana busca las utilidades en el modelo).
"""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets


def lineas_de(pts):
    """Segmentos (`QLineF`) y caja (x0, y0, x1, y1) de una polilínea en px de la escena."""
    lineas = [QtCore.QLineF(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return lineas, (min(xs), min(ys), max(xs), max(ys))


class CapaLineas(QtWidgets.QGraphicsItem):
    def __init__(self, z):
        super().__init__()
        self.entradas = []                               # (segmentos, pluma)
        self.de = {}                                     # clave de quien agrega (utilidad) → nº de entrada
        self._cajas = []
        self._np = None
        self._ancho = 0.0                                # mayor grosor de pluma (px de pantalla)
        self._caja = QtCore.QRectF()
        self.setZValue(z)
        self.setFlag(QtWidgets.QGraphicsItem.ItemUsesExtendedStyleOption)

    def agregar(self, lineas, caja, pluma, clave=None):
        if not lineas:
            return
        if clave is not None:
            self.de[clave] = len(self.entradas)
        self.entradas.append((lineas, pluma))
        self._cajas.append(caja)
        self._np = None
        self._ancho = max(self._ancho, pluma.widthF())

    def cerrar(self):
        """Fija la caja del ítem (una vez, tras agregar todo)."""
        self._np = np.asarray(self._cajas, dtype=float).reshape(-1, 4)
        if len(self._np):
            x0, y0 = self._np[:, 0].min(), self._np[:, 1].min()
            x1, y1 = self._np[:, 2].max(), self._np[:, 3].max()
            self.prepareGeometryChange()
            self._caja = QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)

    def cambiar_pluma(self, clave, pluma):
        """Otra pluma para la entrada `clave` (la utilidad que se elige o se suelta), en su MISMO lugar del
        orden: queda igual que haberla agregado así. La caja del ítem crece si la pluma es más gruesa."""
        k = self.de.get(clave)
        if k is None:
            return
        lineas, _vieja = self.entradas[k]
        self.entradas[k] = (lineas, pluma)
        if pluma.widthF() > self._ancho:
            self.prepareGeometryChange()
            self._ancho = pluma.widthF()
        self.update()

    def boundingRect(self):
        # la pluma es cosmética (px de pantalla): el margen en la escena depende del zoom; uno holgado
        m = self._ancho + 2.0
        return self._caja.adjusted(-m, -m, m, m)

    def paint(self, painter, opcion, widget=None):
        if self._np is None:
            self.cerrar()
        if not len(self.entradas):
            return
        W = QtGui.QTransform(painter.worldTransform())
        escala = max(math.hypot(W.m11(), W.m12()), 1e-9)
        m = (self._ancho / 2.0 + 2.0) / escala           # media pluma + suavizado, en px de la escena
        zonas = [opcion.exposedRect]
        D = QtGui.QTransform(painter.deviceTransform())
        motor = painter.paintEngine()
        inv_d, ok = D.inverted()
        if ok and motor is not None and not motor.systemClip().isEmpty():
            zonas = [inv_d.mapRect(QtCore.QRectF(r)).intersected(opcion.exposedRect)
                     for r in motor.systemClip()]
        c = self._np
        toca = np.zeros(len(c), dtype=bool)
        for z in zonas:
            if z.isEmpty():
                continue
            toca |= ((c[:, 2] >= z.left() - m) & (c[:, 0] <= z.right() + m)
                     & (c[:, 3] >= z.top() - m) & (c[:, 1] <= z.bottom() + m))
        actual = None
        for k in np.flatnonzero(toca).tolist():
            lineas, pluma = self.entradas[k]
            if pluma is not actual:
                painter.setPen(pluma)
                actual = pluma
            painter.drawLines(lineas)
