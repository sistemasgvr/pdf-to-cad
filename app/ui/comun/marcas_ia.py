"""Lo que la IA del diámetro te señala en el plano (pedido del usuario 2026-11-03): cada línea con un halo y su nombre,
cada rótulo con un recuadro y su id. Se quedan mientras dura la conversación de esa línea, sin cambiar la selección
(elegir otra línea cerraría el chat). Son ítems de la escena, no widgets: un hijo sobre el lienzo rompe su caché.
Colores de control de calidad: ninguno es de una utilidad.
"""
import shiboken6
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo.model import Z_HANDLE
from ui.comun.ui_common import QA_OFFPATTERN, QA_UNCOVERED

Z_MARCA = Z_HANDLE + 4
HALO_PX = 7
ALFA_HALO = 130


class _Etiqueta(QtWidgets.QGraphicsItem):
    """Texto en una pastilla oscura, del mismo tamaño en pantalla a cualquier zoom."""

    def __init__(self, texto, color):
        super().__init__()
        self._texto, self._color = texto, QtGui.QColor(color)
        self._fuente = QtGui.QFont()
        self._fuente.setPointSize(9)
        self._fuente.setBold(True)
        r = QtGui.QFontMetricsF(self._fuente).boundingRect(texto)
        self._caja = QtCore.QRectF(8, -10 - r.height(), r.width() + 12, r.height() + 6)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)

    def boundingRect(self):  # noqa: N802 (API Qt)
        return self._caja.adjusted(-2, -2, 2, 2)

    def paint(self, painter, _opcion, _widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(self._color, 1.5))
        painter.setBrush(QtGui.QColor(24, 28, 38))
        painter.drawRoundedRect(self._caja, 4, 4)
        painter.setPen(QtGui.QColor(255, 255, 255))
        painter.setFont(self._fuente)
        painter.drawText(self._caja, QtCore.Qt.AlignCenter, self._texto)


class MarcasIA:
    def __init__(self, canvas):
        self._canvas = canvas
        self.items = []

    def quitar(self):
        for it in self.items:
            if shiboken6.isValid(it) and it.scene() is not None:   # la escena pudo vaciarse al cambiar de hoja
                it.scene().removeItem(it)
        self.items = []

    def vigentes(self) -> bool:
        return bool(self.items) and all(shiboken6.isValid(it) and it.scene() is not None for it in self.items)

    def _sumar(self, it, z=Z_MARCA):
        it.setZValue(z)
        self._canvas.scene().addItem(it)
        self.items.append(it)
        return it

    def poner(self, lineas=(), rotulos=()):
        """`lineas` = [(puntos, etiqueta, punto de la etiqueta)], `rotulos` = [(x0, y0, x1, y1, etiqueta)]."""
        self.quitar()
        if self._canvas.scene() is None:
            return
        halo = QtGui.QColor(QA_UNCOVERED)
        halo.setAlpha(ALFA_HALO)
        pluma = QtGui.QPen(halo, HALO_PX, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        pluma.setCosmetic(True)
        for pts, etiqueta, donde in lineas:
            camino = QtGui.QPainterPath(QtCore.QPointF(*pts[0]))
            for q in pts[1:]:
                camino.lineTo(*q)
            it = self._sumar(QtWidgets.QGraphicsPathItem(camino))
            it.setPen(pluma)
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            self._sumar(_Etiqueta(etiqueta, QA_UNCOVERED), Z_MARCA + 1).setPos(*donde)
        pluma = QtGui.QPen(QtGui.QColor(QA_OFFPATTERN), 2)
        pluma.setCosmetic(True)
        for x0, y0, x1, y1, etiqueta in rotulos:
            it = self._sumar(QtWidgets.QGraphicsRectItem(x0, y0, x1 - x0, y1 - y0))
            it.setPen(pluma)
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            self._sumar(_Etiqueta(etiqueta, QA_OFFPATTERN), Z_MARCA + 1).setPos(x1, y0)
