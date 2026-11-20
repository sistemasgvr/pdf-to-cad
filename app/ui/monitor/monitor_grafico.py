"""Gráfica de memoria del monitor: memoria de TODOS los procesos de la app y la de la ventana, en el tiempo; las
pausas de la ventana se marcan como franjas debajo."""
from __future__ import annotations

from typing import List

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme
from ui.monitor.monitor_util import mb


class GraficoMemoria(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self._serie: List[tuple] = []
        self._pausas: List[tuple] = []        # (fin, dur)
        self.setToolTip(_tr("Memoria de la app en el tiempo. Las franjas de abajo son las pausas de la ventana."))

    def poner(self, serie, pausas) -> None:
        self._serie = list(serie)
        self._pausas = list(pausas)
        self.update()

    def paintEvent(self, _ev):                        # noqa: N802
        tk = theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(52, 10, -12, -26)
        p.setPen(QtGui.QPen(QtGui.QColor(tk.border_soft), 1))
        for k in range(5):
            y = r.top() + r.height() * k / 4
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))
        f = p.font()
        f.setPixelSize(11)
        p.setFont(f)
        if len(self._serie) < 2:
            p.setPen(QtGui.QColor(tk.text_muted))
            p.drawText(r, QtCore.Qt.AlignCenter, _tr("Esperando datos de memoria…"))
            return
        t0, t1 = self._serie[0][0], self._serie[-1][0]
        span = max(1.0, t1 - t0)
        top = max(max((s[1] or 0) for s in self._serie), 1.0) * 1.15

        def pt(t, v):
            return QtCore.QPointF(r.left() + (t - t0) / span * r.width(), r.bottom() - (v / top) * r.height())

        # pausas de la ventana
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(tk.danger))
        for fin, d in self._pausas:
            if fin < t0:
                continue
            x0 = r.left() + (fin - d - t0) / span * r.width()
            x1 = r.left() + (fin - t0) / span * r.width()
            p.drawRect(QtCore.QRectF(max(r.left(), x0), r.bottom() + 4, max(2.0, x1 - x0), 5))
        for idx, color, ancho in ((1, tk.accent, 2.0), (2, tk.text_muted, 1.5)):
            camino = QtGui.QPainterPath()
            primero = True
            for s in self._serie:
                if s[idx] is None:
                    continue
                q = pt(s[0], s[idx])
                if primero:
                    camino.moveTo(q)
                    primero = False
                else:
                    camino.lineTo(q)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(color), ancho))
            p.drawPath(camino)
        p.setPen(QtGui.QColor(tk.text_muted))
        for k in range(5):
            v = top * (4 - k) / 4
            y = r.top() + r.height() * k / 4
            p.drawText(QtCore.QRectF(0, y - 8, 46, 16), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, mb(v))
        minutos = span / 60
        p.drawText(QtCore.QRectF(r.left(), r.bottom() + 10, 200, 16), QtCore.Qt.AlignLeft,
                   _tr("hace {n} min").format(n=f"{minutos:.0f}" if minutos >= 1 else f"{minutos:.1f}"))
        p.drawText(QtCore.QRectF(r.right() - 120, r.bottom() + 10, 120, 16), QtCore.Qt.AlignRight, _tr("ahora"))
        # leyenda
        x = r.left() + 8
        for color, texto in ((tk.accent, _tr("Toda la app")), (tk.text_muted, _tr("Ventana"))):
            p.setPen(QtGui.QPen(QtGui.QColor(color), 3))
            p.drawLine(QtCore.QPointF(x, r.top() + 8), QtCore.QPointF(x + 14, r.top() + 8))
            p.setPen(QtGui.QColor(tk.text))
            ancho = p.fontMetrics().horizontalAdvance(texto)
            p.drawText(QtCore.QPointF(x + 19, r.top() + 12), texto)
            x += 19 + ancho + 18
