"""Etiquetas «T1», «T2»… de la edición por tramo, que no se solapan (pedido del usuario 2026-10-16).

Antes cada etiqueta medía 24 px de la hoja, centrada encima del tramo: con tramos cortos o
muy juntos se montaban unas sobre otras (y de cerca se veían enormes). Ahora:
  · el tamaño sigue al tramo (`FRACCION` de su largo, entre `PX_MIN` y `PX_MAX`);
  · va al COSTADO del tramo (arriba primero), y si choca con otra etiqueta prueba el otro lado,
    más lejos o más chica (`ubicar`, en px de la hoja: la regla vale a cualquier zoom);
  · en pantalla nunca pasa de `TOPE_PX` de alto (`EtiquetaTramo` se achica al pintar).
Relleno del color de la línea con contorno negro grueso, como antes (dos capas: silueta
negra engordada detrás y el relleno encima).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

PX_MAX = 24.0             # alto de letra máximo en px de la hoja (el tamaño de antes)
PX_MIN = 5.0
FRACCION = 0.45           # alto de letra respecto al largo del tramo
TOPE_PX = 20.0            # alto máximo en PANTALLA
ANCHO_LETRA = 0.62        # ancho de un carácter / alto de letra (negrita, aproximado)
SEPARACION = 0.3          # aire entre el tramo y la etiqueta (fracción del alto)
VERTICE_PX = 14.0         # lado del cuadro que se deja libre en cada vértice (buzón, codo, avisos)


def _rect(cx, cy, w, h):
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def _solape(r, s):
    w = min(r[2], s[2]) - max(r[0], s[0])
    h = min(r[3], s[3]) - max(r[1], s[1])
    return w * h if w > 0 and h > 0 else 0.0


def ubicar(tramos, ocupados=None, evitar=()):
    """`tramos` = [(texto, a, b)] en px de la hoja. Devuelve [(texto, mx, my, dx, dy, px)]:
    el punto medio del tramo, dónde va el CENTRO de la etiqueta respecto a él y el alto de
    letra. `ocupados` = rectángulos (x0, y0, x1, y1) ya puestos (se le agregan los nuevos);
    `evitar` = vértices donde van otras marcas (buzón, codo, avisos): se les deja un cuadro libre."""
    ocupados = [] if ocupados is None else ocupados
    for q in evitar:
        ocupados.append(_rect(q[0], q[1], VERTICE_PX, VERTICE_PX))
    out = []
    for texto, a, b in tramos:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        # primero ARRIBA (como antes); en un tramo vertical, a la IZQUIERDA: a la derecha del
        # vértice van las etiquetas de los accesorios («Codo 45°»)
        if ny > 1e-9 or (abs(ny) <= 1e-9 and nx > 0):
            nx, ny = -nx, -ny
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        px0 = min(PX_MAX, max(PX_MIN, L * FRACCION))
        mejor = None
        for escala in (1.0, 0.75, 0.55):
            px = max(PX_MIN * 0.6, px0 * escala)
            w, h = len(texto) * ANCHO_LETRA * px, px
            medio = abs(nx) * w / 2.0 + abs(ny) * h / 2.0        # media extensión hacia el costado
            for lejos in (1.0, 2.2, 3.4):
                for lado in (1.0, -1.0):
                    d = (medio + SEPARACION * px) * lejos
                    dx, dy = nx * lado * d, ny * lado * d
                    r = _rect(mx + dx, my + dy, w, h)
                    choque = sum(_solape(r, s) for s in ocupados)
                    if mejor is None or choque < mejor[0]:
                        mejor = (choque, dx, dy, px, r)
                    if choque == 0.0:
                        break
                if mejor[0] == 0.0:
                    break
            if mejor[0] == 0.0:
                break
        _c, dx, dy, px, r = mejor
        ocupados.append(r)
        out.append((texto, mx, my, dx, dy, px))
    return out


class EtiquetaTramo(QtWidgets.QGraphicsItem):
    """La etiqueta con su centro a (dx, dy) del punto medio del tramo (la posición del ítem).
    Al pintar se achica (y se acerca al tramo en la misma proporción) si en pantalla pasaría
    de `TOPE_PX` de alto."""

    def __init__(self, texto, color, px, dx, dy, halo=None):
        super().__init__()
        self._color = QtGui.QColor(color)
        self._px = float(px)
        self._dx, self._dy = float(dx), float(dy)
        self._halo = float(halo if halo is not None else max(1.0, px * 0.21))
        f = QtGui.QFont(); f.setPixelSize(max(1, int(round(px)))); f.setBold(True)
        camino = QtGui.QPainterPath()
        camino.addText(0.0, 0.0, f, texto)
        r = camino.boundingRect()
        self._camino = camino.translated(-r.center())             # centrado en (0, 0)
        m = self._halo
        self._caja = self._camino.boundingRect().adjusted(-m, -m, m, m).translated(self._dx, self._dy)

    def boundingRect(self):
        return self._caja

    def factor(self, escala):
        """Cuánto se achica a la escala de la vista (1 = su tamaño en la hoja)."""
        return min(1.0, TOPE_PX / (self._px * escala)) if escala > 1e-9 else 1.0

    def paint(self, painter, _opcion, _widget=None):
        t = painter.worldTransform()
        f = self.factor(math.hypot(t.m11(), t.m12()))
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(self._dx * f, self._dy * f)
        painter.scale(f, f)
        halo = QtGui.QPen(QtGui.QColor(0, 0, 0), self._halo)
        halo.setJoinStyle(QtCore.Qt.RoundJoin); halo.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(halo); painter.setBrush(QtGui.QColor(0, 0, 0))
        painter.drawPath(self._camino)
        painter.setPen(QtCore.Qt.NoPen); painter.setBrush(self._color)
        painter.drawPath(self._camino)
