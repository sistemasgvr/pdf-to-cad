"""Avisos de normativa en el lienzo, NO invasivos (pedido del usuario 2026-10-09).

Un circulito pequeño ámbar con «!» (rojo si la regla es de nivel ERROR, celeste con «i» si es solo
informativo) donde
está el aviso: tamaño fijo en pantalla, algo transparente y sin texto encima del plano.
Al pasar el ratón, el globo dice qué pasa. Los avisos de un mismo punto van juntos en
UNA insignia. Los de los accesorios ya se ven en su etiqueta («Codo 45° ⚠»), así que
aquí solo se dibujan si esas etiquetas están ocultas. «Sin tipo» no va en el plano (en un
proyecto recién importado serían decenas): se ve en el panel de la utilidad, en la lista
de avisos y en el contador de la barra de estado.

Los avisos del RECONOCIMIENTO (diámetro que el plano no dijo con certeza, `diametro_plano`) van en
turquesa con «?» (pedido del usuario 2026-10-23: se confundían con los de normativa; el turquesa no es
de ninguna utilidad ni el morado de las curvas)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import diametro_plano
from nucleo.model import Z_HANDLE
from ui.comun.capa_marcas import sello
from ui.comun.ui_common import QA_OFFPATTERN, tooltip_bloque
from traduccion.i18n import t as _tr

_AMBAR = QtGui.QColor(240, 170, 20, 215)
_CELESTE = QtGui.QColor(70, 150, 230, 200)
_ROJO = QtGui.QColor(225, 60, 50, 220)
_TURQUESA = QtGui.QColor(QA_OFFPATTERN)
_TURQUESA.setAlpha(225)
RECONOCIMIENTO = "rec"            # `info` de la insignia de un grupo de solo avisos de reconocimiento


class InsigniaAviso(QtWidgets.QGraphicsItem):
    R = 7.0

    def __init__(self, info, error=False):
        super().__init__()
        if info == RECONOCIMIENTO:
            self._color, self._letra = _TURQUESA, "?"
        else:
            self._color = _CELESTE if info else _ROJO if error else _AMBAR
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


def dibujar(scene, avisos, tol_px, con_accesorios_visibles, poner=None, reusar=None, guardar=None):
    """Agrega las insignias a `scene` (o con `poner(item)`: la capa de marcas del lienzo,
    `capa_marcas`) y devuelve los items (van al overlay). `reusar`/`guardar`: como en
    `accesorios_view.dibujar`."""
    grupos = []                                       # [[x, y, [avisos]]]
    # Rejilla de celdas de `tol_px`: con cientos de avisos (ángulos de un plano reconocido)
    # comparar cada uno con todos los grupos trababa el redibujo. Mismo resultado: el grupo
    # MÁS ANTIGUO a ≤ tol (el primero de la lista de antes).
    celda = max(float(tol_px), 1e-6)
    rejilla = {}
    for a in avisos:
        if a.clase == "accesorio" and con_accesorios_visibles:
            continue
        if a.clase == "tipo" or a.aprobado:
            continue          # «sin tipo»: en el panel, la lista y la barra de estado (no llena el plano)
        cx, cy = int(a.x // celda), int(a.y // celda)
        cerca = [n for dx in (-1, 0, 1) for dy in (-1, 0, 1) for n in rejilla.get((cx + dx, cy + dy), ())
                 if (grupos[n][0] - a.x) ** 2 + (grupos[n][1] - a.y) ** 2 <= tol_px * tol_px]
        if cerca:
            grupos[min(cerca)][2].append(a)
        else:
            rejilla.setdefault((cx, cy), []).append(len(grupos))
            grupos.append([a.x, a.y, [a]])
    items = []
    for x, y, lista in grupos:
        info = (RECONOCIMIENTO if all(a.clase == diametro_plano.CLASE for a in lista)
                else all(a.info for a in lista))
        error = not info and any(getattr(a, "nivel", "") == "ERROR" for a in lista if not a.info)
        it = reusar(("aviso", info, error, x, y)) if reusar else None
        if it is None:
            it = sello(InsigniaAviso(info, error), ("aviso", info, error))
            it.setPos(x, y)
            if guardar:
                guardar(("aviso", info, error, x, y), it)
        quien = sorted({a.pipe + 1 for a in lista if a.pipe is not None and a.pipe >= 0})
        cab = _tr("Utilidad {n}").format(n=", ".join(f"#{k}" for k in quien)) if quien else ""
        texto = "\n".join(([cab] if cab else []) + [("ⓘ " if a.info else "⚠ ") + a.mensaje for a in lista])
        it.setToolTip(tooltip_bloque(texto))
        (poner or scene.addItem)(it)
        items.append(it)
    return items
