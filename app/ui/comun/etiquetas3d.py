"""Etiquetas «C-n» de los conflictos en la Vista 3D: se dibujan con QPainter ENCIMA del
modelo, en la proyección de cada esfera roja (la seleccionada, en magenta). Con
`rotulo=True`, los rótulos de pendiente/ángulo (`nucleo/rotulos3d`): caja oscura neutra,
centrada en su punto."""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui


def dibujar(pintor, etiquetas, m, w, h, sel_id=0, hov_id=0, rotulo=False):
    """`etiquetas` = [(id, punto 3D, texto)]; `m` = matriz vista-proyección (numpy 4×4)."""
    if not etiquetas:
        return
    pintor.save()
    pintor.setRenderHint(QtGui.QPainter.Antialiasing, True)
    f = pintor.font(); f.setPixelSize(11); f.setBold(True); pintor.setFont(f)
    fm = QtGui.QFontMetrics(f)
    for ident, p, texto in etiquetas:
        c = m @ np.array([p[0], p[1], p[2], 1.0])
        if c[3] <= 1e-6:
            continue                                         # detrás de la cámara
        nx, ny = c[0] / c[3], c[1] / c[3]
        if abs(nx) > 1.1 or abs(ny) > 1.1:
            continue
        x, y = (nx + 1.0) / 2.0 * w, (1.0 - ny) / 2.0 * h
        ancho = fm.horizontalAdvance(texto) + 8
        caja = QtCore.QRectF(x - ancho / 2.0, y - (8 if rotulo else 22), ancho, 16)
        activo = ident in (sel_id, hov_id)
        pintor.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2.0 if activo else 1.0))
        if rotulo:
            pintor.setBrush(QtGui.QColor(255, 79, 216) if ident == sel_id else QtGui.QColor(25, 30, 40, 215))
        else:
            pintor.setBrush(QtGui.QColor(255, 79, 216) if ident == sel_id else QtGui.QColor(160, 15, 15, 235))
        pintor.drawRoundedRect(caja, 4, 4)
        pintor.setPen(QtGui.QColor(255, 255, 255))
        pintor.drawText(caja, QtCore.Qt.AlignCenter, texto)
    pintor.restore()
