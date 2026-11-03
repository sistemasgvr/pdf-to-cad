"""Las líneas provisionales del reconocimiento sobre el lienzo, dibujadas con un presupuesto de tiempo
por tanda. Son de paso: nunca entran al modelo, al deshacer ni a la exportación."""
from __future__ import annotations

from collections import deque
import time

from PySide6 import QtCore, QtGui
from ui.comun.ui_common import layer_qcolor

MS_POR_TANDA = 4
SEGMENTOS_POR_ITEM = 2048
SEGMENTOS_POR_TICK = 4096


class TrazadoProgresivo(QtCore.QObject):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas, self.scene = canvas, canvas.scene()
        self.queue = deque()
        self.items = {}
        self.active = True
        self._timer = QtCore.QTimer(self, interval=16, timeout=self._tick)

    def agregar(self, utility, strokes):
        if not self.active:
            return
        self.queue.extend((utility, points, 0) for points in strokes if len(points) >= 2)
        if self.queue:
            self._timer.start()

    def reemplazar(self, utility, strokes):
        self.queue = deque(t for t in self.queue if t[0] != utility)
        for item in self.items.pop(utility, ()):
            try:
                if item.scene() is self.scene:
                    self.scene.removeItem(item)
            except RuntimeError:
                pass
        self.agregar(utility, strokes)

    def _tick(self):
        if not self.active or self.canvas.scene() is not self.scene:
            self.cerrar()
            return
        deadline = time.perf_counter() + MS_POR_TANDA / 1000
        count, path, utility = 0, None, None

        def publish():
            if path is not None and not path.isEmpty():
                pen = QtGui.QPen(layer_qcolor(utility), 2.)
                pen.setCosmetic(True)
                item = self.scene.addPath(path, pen)
                item.setZValue(1e6)
                item.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                self.items.setdefault(utility, []).append(item)

        while self.queue and count < SEGMENTOS_POR_TICK:
            u, points, pos = self.queue.popleft()
            if path is None or u != utility:
                publish()
                path, utility = QtGui.QPainterPath(), u
            path.moveTo(*points[pos])
            while pos < len(points) - 1:
                pos += 1
                path.lineTo(*points[pos])
                count += 1
                if count % SEGMENTOS_POR_ITEM == 0:
                    publish()
                    path = QtGui.QPainterPath()
                    path.moveTo(*points[pos])
                if count >= SEGMENTOS_POR_TICK or (count % 32 == 0 and time.perf_counter() >= deadline):
                    break
            if pos < len(points) - 1:
                self.queue.appendleft((u, points, pos))
            if time.perf_counter() >= deadline:
                break
        publish()
        if not self.queue:
            self._timer.stop()

    def cerrar(self):
        self.active = False
        self._timer.stop()
        self.queue.clear()
        for group in self.items.values():
            for item in group:
                try:
                    if item.scene() is self.scene:
                        self.scene.removeItem(item)
                except RuntimeError:
                    pass
        self.items.clear()
