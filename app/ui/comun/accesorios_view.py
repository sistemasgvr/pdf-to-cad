"""Etiquetas de los accesorios de presión en el lienzo: «Codo 45°», «Tee 90°»…

Cada accesorio que Civil 3D pondrá (ver `accesorios.py`) lleva un rombo en su
punto y, al costado, una pastilla con su tipo y ángulo. Tamaño fijo en pantalla
(ignora el zoom). Color: neutro si cumple las normativas y ÁMBAR si tiene un aviso
(`normas_validar`); el globo (tooltip) dice cuál."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import accesorios as acc
from nucleo.normas_validar import NOMBRE_ACC
from traduccion.i18n import t as _tr
from nucleo.model import Z_HANDLE
from ui.comun.capa_marcas import sello
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

    def __init__(self, texto, color_red, nivel, medidas=None):
        """`medidas`: dict que comparten las etiquetas de UN redibujo (`dibujar`): la fuente, su clave y el
        ancho de cada texto se calculan una vez (con ~20 mil etiquetas pesaba ~1 s); mismos valores."""
        super().__init__()
        self._texto = texto
        self._red = color_red
        self._fondo, self._letra, borde = _COLORES.get(nivel, _COLORES[None])
        self._borde = borde or color_red
        if medidas is None:
            medidas = {}
        fuente = medidas.get(None)
        if fuente is None:
            f = QtGui.QFont(); f.setPixelSize(13); f.setBold(True)
            fm = QtGui.QFontMetricsF(f)
            fuente = medidas[None] = (f, f.key(), fm, fm.height() + 4)
        self._font, self._clave_fuente, fm, h = fuente
        w = medidas.get(texto)
        if w is None:
            w = medidas[texto] = fm.horizontalAdvance(texto) + 12
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
        self._pintar_rombo(painter)
        self._pintar_fondo(painter)
        self._pintar_texto(painter)

    def partes_sello(self):
        """Para `capa_marcas.sello`: el rombo es el PUNTO (siempre se ve); la guía con la pastilla
        (se repite en miles de etiquetas) y el texto (uno por texto) son el RÓTULO (nivel de detalle)."""
        p = self._pastilla
        tam = (round(p.width(), 4), round(p.height(), 4))
        r = self.R + 2
        rombo = ("acc-rombo", self._red.rgba())
        fondo = ("acc-fondo",) + tam + (self._borde.rgba(), self._fondo.rgba())
        texto = ("acc-texto", self._texto, self._clave_fuente, self._letra.rgba()) + tam
        guia = QtCore.QRectF(QtCore.QPointF(self.R * 0.7, -self.R * 0.7), p.bottomLeft() + QtCore.QPointF(2, 0))
        return ((rombo, 2, QtCore.QRectF(-r, -r, 2 * r, 2 * r), self._pintar_rombo, False),
                (fondo, 2, p.united(guia.normalized()).adjusted(-2, -2, 2, 2), self._pintar_fondo, True),
                (texto, 1, p.adjusted(-2, -2, 2, 2), self._pintar_texto, True))

    def _pintar_rombo(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.R
        rombo = QtGui.QPolygonF([QtCore.QPointF(0, -r), QtCore.QPointF(r, 0),
                                 QtCore.QPointF(0, r), QtCore.QPointF(-r, 0)])
        painter.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20), 1.2))
        painter.setBrush(self._red); painter.drawPolygon(rombo)

    def _pintar_fondo(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.R
        # guía fina rombo → pastilla
        painter.setPen(QtGui.QPen(self._borde, 1.0))
        painter.drawLine(QtCore.QPointF(r * 0.7, -r * 0.7), self._pastilla.bottomLeft() + QtCore.QPointF(2, 0))
        painter.setPen(QtGui.QPen(self._borde, 1.5)); painter.setBrush(self._fondo)
        painter.drawRoundedRect(self._pastilla, 6, 6)

    def _pintar_texto(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(self._letra); painter.setFont(self._font)
        painter.drawText(self._pastilla, QtCore.Qt.AlignCenter, self._texto)


def texto_accesorio(a):
    return "{tipo} {ang}".format(tipo=_tr(NOMBRE_ACC.get(a["tipo"], a["tipo"])),
                                 ang=acc.texto_angulo(a["angulo"]))


def tooltip_accesorio(a, avisos):
    lineas = [_tr("En Civil 3D: {acc} de {ang} (accesorio sólido) en la red «{red}».").format(
        acc=_tr(NOMBRE_ACC.get(a["tipo"], a["tipo"])), ang=acc.texto_angulo(a["angulo"]),
        red=a["red"])]
    if a.get("giro") is not None:
        lineas.append(_tr("Medido sobre el eje: desvío de {g} respecto del lado recto prolongado.").format(
            g=acc.texto_angulo(a["giro"])))
    if a.get("fundido"):
        lineas.append(_tr("Reúne dos quiebres muy juntos: Civil 3D pone un solo codo."))
    if avisos:
        lineas.append("")
        lineas += ["⚠ " + av.mensaje for av in avisos]
    else:
        lineas.append("✓ " + _tr("Cumple las normativas."))
    lineas.append(_tr("Menú Normativas → Normativas de diseño… para ver las tablas."))
    return "\n".join(lineas)


def preparar(accesorios, avisos, tol_px):
    """Lo que dice cada etiqueta: [(texto, capa, nivel, x, y, globo)]. Solo depende del modelo (la
    ventana lo reusa entre redibujos)."""
    # Avisos por celdas (`indice_plano`): antes cada accesorio recorría TODOS los avisos.
    # Mismo resultado que `en_punto` (no informativos ni aprobados, a ≤ tol, en su orden).
    from nucleo.indice_plano import IndicePuntos
    vivos = [v for v in avisos if not v.info and not v.aprobado]
    indice = IndicePuntos([(v.x, v.y) for v in vivos], tol_px if tol_px > 0 else 1.0)
    out = []
    for a in accesorios:
        suyos = [vivos[k] for k in indice.en_radio(a["x"], a["y"], tol_px)]
        nivel = "recomendada" if suyos else None
        texto = texto_accesorio(a) + (" ⚠" if nivel else "")
        out.append((texto, a["capa"], nivel, a["x"], a["y"], tooltip_bloque(tooltip_accesorio(a, suyos))))
    return out


def dibujar(scene, accesorios, avisos, tol_px, poner=None, reusar=None, guardar=None, preparadas=None):
    """Agrega las etiquetas a `scene` (o con `poner(item)`: la capa de marcas del lienzo,
    `capa_marcas`) y devuelve los items (van al overlay). `reusar(clave)`/`guardar(clave, item)`: la
    misma etiqueta del redibujo anterior si sale igual (`capa_marcas.GrupoMarcas`). `preparadas` =
    `preparar(...)` ya hecho."""
    return list(dibujar_iter(scene, accesorios, avisos, tol_px, poner, reusar, guardar, preparadas))


def dibujar_iter(scene, accesorios, avisos, tol_px, poner=None, reusar=None, guardar=None, preparadas=None):
    """Como `dibujar`, entregando cada etiqueta ya puesta (la ventana las carga por tandas en planos
    gigantes: `marcas_por_tandas`)."""
    if preparadas is None:
        preparadas = preparar(accesorios, avisos, tol_px)
    medidas = {}
    for texto, capa, nivel, x, y, globo in preparadas:
        clave = ("accesorio", texto, capa, nivel, x, y)
        it = reusar(clave) if reusar else None
        if it is None:
            color = layer_qcolor(capa)
            it = EtiquetaAccesorio(texto, color, nivel, medidas)
            sello(it, partes=it.partes_sello())
            it.setPos(x, y)
            cajas = medidas.get(("cajas", it._pastilla.width(), it._pastilla.height()))
            if cajas is not None:                    # (misma pastilla = mismas cajas en la capa de marcas)
                it._pdfcad_caja, it._pdfcad_rot = cajas
            if guardar:
                guardar(clave, it)
        it.setToolTip(globo)
        (poner or scene.addItem)(it)
        k = ("cajas", it._pastilla.width(), it._pastilla.height())
        if k not in medidas:
            caja, rot = getattr(it, "_pdfcad_caja", None), getattr(it, "_pdfcad_rot", False)
            if caja is not None and rot is not False:
                medidas[k] = (caja, rot)
        yield it
