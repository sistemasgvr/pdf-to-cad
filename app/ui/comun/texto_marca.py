"""Texto de una marca del lienzo («!», «↕», «✓» de los cruces) sin un `QGraphicsTextItem` por marca
(2026-10-19: con 16 812 cruces, crear un QGraphicsTextItem —con su QTextDocument— por cada uno trababa la
ventana ~2 s al abrir el proyecto «PRUEBA AGUA 2»).

`nuevo(texto, color, fuente)` devuelve un `TextoMarca`: un ítem liviano que mide y se pinta con un
`QGraphicsTextItem` MOLDE armado igual que antes (mismo texto, color, fuente y margen 0), uno por aspecto
y compartido por todas las marcas que se ven igual. `QGraphicsTextItem.paint` solo usa su documento y la
opción que recibe, así que pintar el molde en el lugar de cada marca da los mismos píxeles; la caja es la
misma. La posición, la transformación, la Z y las banderas siguen siendo de cada marca.
"""
from __future__ import annotations

from PySide6 import QtWidgets

_MOLDES = {}                     # (texto, color rgba, clave de la fuente) → QGraphicsTextItem


def molde(texto, color, fuente, clave_fuente=None):
    """El `QGraphicsTextItem` de ese aspecto, armado como lo armaba cada marca. `clave_fuente` =
    `fuente.key()` ya calculada (con miles de marcas, pedirla en cada una pesaba)."""
    clave = (texto, color.rgba(), fuente.key() if clave_fuente is None else clave_fuente)
    m = _MOLDES.get(clave)
    if m is None:
        m = QtWidgets.QGraphicsTextItem(texto)
        m.setDefaultTextColor(color)
        m.setFont(fuente)
        m.document().setDocumentMargin(0)
        _MOLDES[clave] = m
    return m


class TextoMarca(QtWidgets.QGraphicsItem):
    """Ítem de texto de una marca: mide y pinta con su molde (`molde`)."""

    def __init__(self, m):
        super().__init__()
        self._molde = m

    def boundingRect(self):
        return self._molde.boundingRect()

    def shape(self):
        return self._molde.shape()

    def paint(self, painter, option, widget=None):
        self._molde.paint(painter, option, widget)

    def toPlainText(self):
        return self._molde.toPlainText()


def nuevo(texto, color, fuente, clave_fuente=None):
    return TextoMarca(molde(texto, color, fuente, clave_fuente))
