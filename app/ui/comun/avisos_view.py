"""Avisos de normativa en el lienzo, NO invasivos (pedido del usuario 2026-10-09).

Un circulito pequeño ámbar con «!» (o celeste con «i» si es solo informativo) donde
está el aviso: tamaño fijo en pantalla, algo transparente y sin texto encima del plano.
Al pasar el ratón, el globo dice qué pasa. Los avisos de un mismo punto van juntos en
UNA insignia. Los de los accesorios ya se ven en su etiqueta («Codo 45° ⚠»), así que
aquí solo se dibujan si esas etiquetas están ocultas. «Sin tipo» no va en el plano (en un
proyecto recién importado serían decenas): se ve en el panel de la utilidad, en la lista
de avisos y en el contador de la barra de estado."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo.model import Z_HANDLE
from ui.comun.ui_common import tooltip_bloque
from traduccion.i18n import t as _tr

_AMBAR = QtGui.QColor(240, 170, 20, 215)
_CELESTE = QtGui.QColor(70, 150, 230, 200)


class InsigniaAviso(QtWidgets.QGraphicsItem):
    R = 7.0

    def __init__(self, info):
        super().__init__()
        self._color = _CELESTE if info else _AMBAR
        self._letra = "i" if info else "!"
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setZValue(Z_HANDLE + 4)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        r = self.R + 1.5
        return QtCore.QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter, _opt, _w=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 30, 0, 160), 1.0))
        painter.setBrush(self._color)
        painter.drawEllipse(QtCore.QPointF(0, 0), self.R, self.R)
        f = QtGui.QFont(); f.setPixelSize(11); f.setBold(True)
        painter.setFont(f)
        painter.setPen(QtGui.QColor(25, 25, 25))
        painter.drawText(self.boundingRect(), QtCore.Qt.AlignCenter, self._letra)


def dibujar(scene, avisos, tol_px, con_accesorios_visibles):
    """Agrega las insignias a `scene` y devuelve los items (van al overlay)."""
    grupos = []                                       # [[x, y, [avisos]]]
    for a in avisos:
        if a.clase == "accesorio" and con_accesorios_visibles:
            continue
        if a.clase == "tipo":
            continue          # «sin tipo»: en el panel, la lista y la barra de estado (no llena el plano)
        for g in grupos:
            if (g[0] - a.x) ** 2 + (g[1] - a.y) ** 2 <= tol_px * tol_px:
                g[2].append(a)
                break
        else:
            grupos.append([a.x, a.y, [a]])
    items = []
    for x, y, lista in grupos:
        it = InsigniaAviso(all(a.info for a in lista))
        it.setPos(x, y)
        quien = sorted({a.pipe + 1 for a in lista if a.pipe is not None and a.pipe >= 0})
        cab = _tr("Utilidad {n}").format(n=", ".join(f"#{k}" for k in quien)) if quien else ""
        texto = "\n".join(([cab] if cab else []) + [("ⓘ " if a.info else "⚠ ") + a.mensaje for a in lista])
        it.setToolTip(tooltip_bloque(texto))
        scene.addItem(it)
        items.append(it)
    return items
