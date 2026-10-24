"""Etiquetas «C-n» de los conflictos en la Vista 3D: se dibujan con QPainter ENCIMA del
modelo, en la proyección de cada esfera roja (la seleccionada, en magenta). Con
`rotulo=True`, los rótulos de pendiente/ángulo (`nucleo/rotulos3d`): caja oscura neutra,
centrada en su punto.

`Capa` (2026-10-20, AGUA 2: 35 766 rótulos = 3.2 s por cuadro) prepara UNA vez por escena los puntos
en numpy y el ancho de cada texto; en cada cuadro elige qué se ve (`rotulos3d_lod`: en pantalla, nivel
de detalle y sin taparse), lo recuerda mientras la cámara no cambie y pinta cada rótulo desde un SELLO
(la misma caja y texto dibujados una vez por texto en una imagen; el elegido y el señalado, directo).
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui

from ui.comun import rotulos3d_lod as LOD

ALTO = 16
MAX_SELLOS = 6000                  # imágenes guardadas (una por texto distinto); más = se vacía
_ANCHOS = {}                       # ancho de cada texto (la fuente es siempre la misma): lo comparten las capas


def _fuente(pintor=None):
    f = QtGui.QFont(pintor.font()) if pintor is not None else QtGui.QFont()
    f.setPixelSize(11)
    f.setBold(True)
    return f


def _pintar(pintor, caja, texto, ident, sel_id, hov_id, rotulo):
    activo = ident in (sel_id, hov_id)
    pintor.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2.0 if activo else 1.0))
    if rotulo:
        pintor.setBrush(QtGui.QColor(255, 79, 216) if ident == sel_id else QtGui.QColor(25, 30, 40, 215))
    else:
        pintor.setBrush(QtGui.QColor(255, 79, 216) if ident == sel_id else QtGui.QColor(160, 15, 15, 235))
    pintor.drawRoundedRect(caja, 4, 4)
    pintor.setPen(QtGui.QColor(255, 255, 255))
    pintor.drawText(caja, QtCore.Qt.AlignCenter, texto)


class Capa:
    """Rótulos de una escena listos para dibujar muchas veces."""

    def __init__(self, etiquetas, largos=None, rotulo=False):
        self.rotulo = rotulo
        self.ids = np.array([e[0] for e in etiquetas], dtype=np.int64)
        self.P = np.array([e[1] for e in etiquetas], dtype=float).reshape(-1, 3)
        self.textos = [e[2] for e in etiquetas]
        self.largos = (np.array(largos, dtype=float) if largos is not None and len(largos) == len(etiquetas)
                       else np.full(len(etiquetas), np.nan))
        self.anchos = None
        self._clave = None
        self._elegidos = None
        self._sellos = {}

    def __len__(self):
        return len(self.textos)

    def _medir(self, fm):
        """Ancho de cada rótulo (texto + 8 px), midiendo cada texto distinto UNA vez (también entre escenas:
        cada parche de la Vista 3D trae una escena nueva con casi los mismos textos)."""
        por_texto = _ANCHOS
        if len(por_texto) > 200000:
            por_texto.clear()
        self.anchos = np.array([por_texto.setdefault(t, fm.horizontalAdvance(t) + 8) for t in self.textos],
                               dtype=float)

    def visibles(self, m, w, h, k_px, sel_id=0, hov_id=0):
        """(índices, x, y) de lo que se ve con esta cámara (memorizado mientras no cambie)."""
        if self.anchos is None:
            self._medir(QtGui.QFontMetrics(_fuente()))
        clave = (np.asarray(m, float).tobytes(), w, h, round(k_px, 6), sel_id, hov_id)
        if clave != self._clave:
            primero = [i for i in (sel_id, hov_id) if i]
            self._elegidos = LOD.elegir(self.P, self.ids, self.anchos, self.largos, m, w, h, k_px, ALTO,
                                        -8.0 if self.rotulo else -22.0, primero)
            self._clave = clave
        return self._elegidos

    def _sello(self, texto, ancho, dpr):
        clave = (texto, dpr)
        s = self._sellos.get(clave)
        if s is None:
            if len(self._sellos) >= MAX_SELLOS:
                self._sellos.clear()
            img = QtGui.QImage(int(np.ceil((ancho + 4) * dpr)), int(np.ceil((ALTO + 4) * dpr)),
                               QtGui.QImage.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(0)
            p = QtGui.QPainter(img)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.setFont(_fuente())
            _pintar(p, QtCore.QRectF(2, 2, ancho, ALTO), texto, -1, 0, 0, self.rotulo)
            p.end()
            s = self._sellos[clave] = img
        return s

    def dibujar(self, pintor, m, w, h, k_px, sel_id=0, hov_id=0):
        if not len(self):
            return
        idx, xs, ys = self.visibles(m, w, h, k_px, sel_id, hov_id)
        if not len(idx):
            return
        pintor.save()
        pintor.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pintor.setFont(_fuente(pintor))
        dpr = pintor.device().devicePixelRatioF() if pintor.device() is not None else 1.0
        dy = -8.0 if self.rotulo else -22.0
        for k, x, y in zip(idx[::-1].tolist(), xs[::-1].tolist(), ys[::-1].tolist()):   # lo importante, encima
            ancho = float(self.anchos[k])
            caja = QtCore.QRectF(x - ancho / 2.0, y + dy, ancho, ALTO)
            ident = int(self.ids[k])
            if ident in (sel_id, hov_id):
                _pintar(pintor, caja, self.textos[k], ident, sel_id, hov_id, self.rotulo)
            else:
                pintor.drawImage(QtCore.QPointF(round(caja.x() * dpr) / dpr - 2, round(caja.y() * dpr) / dpr - 2),
                                 self._sello(self.textos[k], ancho, dpr))
        pintor.restore()


def dibujar(pintor, etiquetas, m, w, h, sel_id=0, hov_id=0, rotulo=False, k_px=None, largos=None):
    """Una vez (sin memorizar): `etiquetas` = [(id, punto 3D, texto)]; `m` = matriz vista-proyección
    (numpy 4×4); `k_px` = px que mide 1 ft a 1 ft de la cámara (None = sin nivel de detalle)."""
    capa = Capa(etiquetas, largos if k_px is not None else None, rotulo)
    capa.dibujar(pintor, m, w, h, k_px or 1.0, sel_id, hov_id)
