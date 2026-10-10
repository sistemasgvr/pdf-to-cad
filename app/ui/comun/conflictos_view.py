"""Número de cada conflicto en el lienzo: una etiqueta «C-n» junto a su marca (tamaño
fijo en pantalla), con el detalle en el tooltip. La lista sale de `nucleo/conflictos.py`."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun.ui_common import tooltip_bloque

Z_ETIQUETA = 10_000


def dibujar(scene, conflictos, tol_px=4.0):
    """Agrega a `scene` una etiqueta por lugar (los conflictos del mismo punto juntos:
    «C-10 · C-13»). Devuelve los ítems (para borrarlos)."""
    from nucleo.conflictos import agrupar
    items = []
    ign = QtWidgets.QGraphicsItem.ItemIgnoresTransformations
    fondo = QtGui.QBrush(QtGui.QColor(150, 15, 15, 235))
    borde = QtGui.QPen(QtGui.QColor(255, 255, 255, 220), 1.0)
    borde.setCosmetic(True)
    for grupo in agrupar(conflictos, tol_px):
        c = grupo[0]
        texto = QtWidgets.QGraphicsSimpleTextItem(" · ".join(k.id for k in grupo))
        f = texto.font(); f.setPixelSize(10); f.setBold(True); texto.setFont(f)
        texto.setBrush(QtGui.QColor(255, 255, 255))
        r = texto.boundingRect().adjusted(-3, -1, 3, 1)
        caja = QtWidgets.QGraphicsRectItem(r)
        caja.setBrush(fondo); caja.setPen(borde)
        texto.setParentItem(caja)
        caja.setPos(c.x, c.y)
        caja.setFlag(ign)
        # Arriba a la IZQUIERDA de la marca: a la derecha va la etiqueta del accesorio («Cruz 90°»).
        caja.setTransform(QtGui.QTransform().translate(-r.width() - 9, -r.height() - 9))
        caja.setZValue(Z_ETIQUETA)
        caja.setToolTip(tooltip_bloque("\n\n".join(f"{k.id} · {_tr(k.titulo)}\n{k.mensaje}" for k in grupo)))
        caja.setData(0, " ".join(k.id for k in grupo))
        scene.addItem(caja)
        items.append(caja)
    return items
