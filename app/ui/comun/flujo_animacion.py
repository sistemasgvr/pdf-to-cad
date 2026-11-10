"""Animación del FLUJO en el plano (pedido del usuario 2026-11-10: al elegir hacia dónde va el fluido, «que se
muestren por 5 segundos animaciones de flechas de cómo está el flujo»).

Flechitas en un tono OSCURO del color de la utilidad (con borde blanco: sobre la línea, del mismo color, se leen) que
CORREN por cada rama de la
utilidad hacia donde va el fluido (`nucleo/flujo.ramas`: una rama hacia una punta, o dos que llegan al punto
intermedio). Separación y velocidad en px de PANTALLA (se ven igual a cualquier zoom); se apaga sola al cabo de
`DURACION_MS`, desvaneciéndose el último `DESVANECER_MS`. Son ítems de la escena (no un widget encima del lienzo:
eso rompe la caché de desplazamiento) que no reciben el ratón y no van en `_overlay`: el redibujo no los toca.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

DURACION_MS = 5000
DESVANECER_MS = 700
CUADRO_MS = 33
PASO_PX = 46.0                  # separación entre flechas (pantalla)
VELOCIDAD_PX_S = 80.0           # avance (pantalla)
MAX_FLECHAS = 400


def _forma():
    p = QtGui.QPainterPath()
    p.moveTo(8.0, 0.0)
    p.lineTo(-5.5, -7.0)
    p.lineTo(-2.0, 0.0)
    p.lineTo(-5.5, 7.0)
    p.closeSubpath()
    return p


class AnimacionFlujo(QtCore.QObject):
    terminada = QtCore.Signal()

    def __init__(self, vista, ramas, color, z, duracion_ms=DURACION_MS, parent=None):
        super().__init__(parent or vista)
        self.vista = vista
        self.ramas = [self._medir(r) for r in ramas if len(r) >= 2]
        self.color = QtGui.QColor(color).darker(165)
        self.z = z
        self.duracion = int(duracion_ms)
        self._items = []
        self._reloj = QtCore.QElapsedTimer()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(CUADRO_MS)
        self._timer.timeout.connect(self._cuadro)

    @staticmethod
    def _medir(rama):
        acum = [0.0]
        for a, b in zip(rama, rama[1:]):
            acum.append(acum[-1] + math.dist(a, b))
        return list(rama), acum

    def activa(self):
        return self._timer.isActive()

    def iniciar(self):
        if not self.ramas:
            self.terminada.emit()
            return
        self._reloj.start()
        self._timer.start()
        self._cuadro()

    def detener(self):
        self._timer.stop()
        sc = self.vista.scene() if self.vista is not None else None
        for it in self._items:
            try:
                if sc is not None and it.scene() is sc:
                    sc.removeItem(it)
            except RuntimeError:
                pass
        self._items = []
        self.terminada.emit()

    def _item(self, k):
        while len(self._items) <= k:
            pluma = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.4)
            pluma.setCosmetic(True)
            it = QtWidgets.QGraphicsPathItem(_forma())
            it.setPen(pluma)
            it.setBrush(self.color)
            it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            it.setZValue(self.z)
            self.vista.scene().addItem(it)
            self._items.append(it)
        return self._items[k]

    def posiciones(self, t_ms, escala):
        """[(x, y, ángulo en grados)] de las flechas en el instante t_ms con la vista a `escala` (px de pantalla por
        px de la hoja)."""
        paso = PASO_PX / max(escala, 1e-9)
        fase = (t_ms / 1000.0 * VELOCIDAD_PX_S / max(escala, 1e-9)) % paso
        out = []
        for pts, acum in self.ramas:
            largo = acum[-1]
            d, j = fase, 0
            while d < largo and len(out) < MAX_FLECHAS:
                while j < len(acum) - 2 and acum[j + 1] < d:
                    j += 1
                (ax, ay), (bx, by) = pts[j][:2], pts[j + 1][:2]
                seg = acum[j + 1] - acum[j]
                f = 0.0 if seg <= 1e-12 else (d - acum[j]) / seg
                out.append((ax + (bx - ax) * f, ay + (by - ay) * f, math.degrees(math.atan2(by - ay, bx - ax))))
                d += paso
        return out

    def _cuadro(self):
        try:
            if self.vista is None or self.vista.scene() is None:
                self.detener()
                return
            t = self._reloj.elapsed()
            if t >= self.duracion:
                self.detener()
                return
            pos = self.posiciones(t, self.vista.transform().m11())
            alfa = min(1.0, (self.duracion - t) / DESVANECER_MS)
            for k, (x, y, ang) in enumerate(pos):
                it = self._item(k)
                it.setPos(x, y)
                it.setRotation(ang)
                it.setOpacity(alfa)
                it.setVisible(True)
            for it in self._items[len(pos):]:
                it.setVisible(False)
        except RuntimeError:                          # la escena se borró (abrir otro proyecto): se termina
            self._timer.stop()
            self._items = []
            self.terminada.emit()
