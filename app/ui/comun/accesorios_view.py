"""Etiquetas de los accesorios de presión en el lienzo: «Codo 45°», «Tee 90°»…

Cada accesorio que Civil 3D pondrá (ver `accesorios.py`) lleva un rombo en su
punto y, al costado, una pastilla con su tipo y ángulo. Tamaño fijo en pantalla
(ignora el zoom). Color: neutro si cumple las normativas activas, ROJO si
incumple una obligatoria y ÁMBAR si solo una recomendada; el globo (tooltip)
dice qué norma y el ángulo permitido más cercano."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import accesorios as acc
from nucleo import normativas
from traduccion.i18n import t as _tr
from nucleo.model import Z_HANDLE
from ui.comun.ui_common import layer_qcolor, tooltip_bloque

_COLORES = {                    # (fondo, texto, borde)
    None: (QtGui.QColor(24, 28, 36, 225), QtGui.QColor(245, 245, 245), None),
    "obligatoria": (QtGui.QColor(200, 30, 30), QtGui.QColor(255, 255, 255), QtGui.QColor(120, 0, 0)),
    "recomendada": (QtGui.QColor(245, 170, 20), QtGui.QColor(20, 20, 20), QtGui.QColor(140, 90, 0)),
}


class EtiquetaAccesorio(QtWidgets.QGraphicsItem):
    """Rombo en el punto + pastilla desplazada arriba a la derecha."""

    R = 5.0
    DX, DY = 9.0, -22.0

    def __init__(self, texto, color_red, nivel):
        super().__init__()
        self._texto = texto
        self._red = color_red
        self._fondo, self._letra, borde = _COLORES.get(nivel, _COLORES[None])
        self._borde = borde or color_red
        self._font = QtGui.QFont(); self._font.setPixelSize(13); self._font.setBold(True)
        fm = QtGui.QFontMetricsF(self._font)
        w = fm.horizontalAdvance(texto) + 12; h = fm.height() + 4
        self._pastilla = QtCore.QRectF(self.DX, self.DY, w, h)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setZValue(Z_HANDLE + 6)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        r = self.R + 2
        return self._pastilla.united(QtCore.QRectF(-r, -r, 2 * r, 2 * r)).adjusted(-2, -2, 2, 2)

    def shape(self):
        p = QtGui.QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, _opt, _w=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.R
        rombo = QtGui.QPolygonF([QtCore.QPointF(0, -r), QtCore.QPointF(r, 0),
                                 QtCore.QPointF(0, r), QtCore.QPointF(-r, 0)])
        painter.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20), 1.2))
        painter.setBrush(self._red); painter.drawPolygon(rombo)
        # guía fina rombo → pastilla
        painter.setPen(QtGui.QPen(self._borde, 1.0))
        painter.drawLine(QtCore.QPointF(r * 0.7, -r * 0.7), self._pastilla.bottomLeft() + QtCore.QPointF(2, 0))
        painter.setPen(QtGui.QPen(self._borde, 1.5)); painter.setBrush(self._fondo)
        painter.drawRoundedRect(self._pastilla, 6, 6)
        painter.setPen(self._letra); painter.setFont(self._font)
        painter.drawText(self._pastilla, QtCore.Qt.AlignCenter, self._texto)


def texto_accesorio(a):
    return "{tipo} {ang}".format(tipo=_tr(normativas.NOMBRE_ACCESORIO.get(a["tipo"], a["tipo"])),
                                 ang=acc.texto_angulo(a["angulo"]))


def tooltip_accesorio(a, nivel, inc, regla):
    lineas = [_tr("En Civil 3D: {acc} de {ang} (accesorio sólido) en la red «{red}».").format(
        acc=_tr(normativas.NOMBRE_ACCESORIO.get(a["tipo"], a["tipo"])), ang=acc.texto_angulo(a["angulo"]),
        red=a["red"])]
    if a.get("giro") is not None:
        lineas.append(_tr("Medido sobre el eje: desvío de {g} respecto del lado recto prolongado.").format(
            g=acc.texto_angulo(a["giro"])))
    if a.get("fundido"):
        lineas.append(_tr("Reúne dos quiebres muy juntos: Civil 3D pone un solo codo."))
    if inc is not None:
        clase = _tr("Obligatoria") if nivel == "obligatoria" else _tr("Recomendada")
        lineas.append("")
        lineas.append("✗ " + _tr(regla.get("titulo", "")) + f" ({clase})")
        lineas.append(inc.mensaje)
    else:
        lineas.append("✓ " + _tr("Cumple las normativas activas."))
    lineas.append(_tr("Menú Normativas → Normativas de diseño… para ver o cambiar las reglas."))
    return "\n".join(lineas)


def dibujar(scene, accesorios, lista_incumplimientos, tol_px):
    """Agrega las etiquetas a `scene` y devuelve los items (van al overlay)."""
    items = []
    for a in accesorios:
        nivel, inc, regla = normativas.estado_de_punto(a["x"], a["y"], lista_incumplimientos, tol_px)
        texto = texto_accesorio(a) + (" ✗" if nivel else "")
        it = EtiquetaAccesorio(texto, layer_qcolor(a["capa"]), nivel)
        it.setPos(a["x"], a["y"])
        it.setToolTip(tooltip_bloque(tooltip_accesorio(a, nivel, inc, regla)))
        scene.addItem(it)
        items.append(it)
    return items
