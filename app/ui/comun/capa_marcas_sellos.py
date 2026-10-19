"""Sellos de las marcas del lienzo (ver `capa_marcas`): la clave de ASPECTO de cada marca, su caja y
su rótulo en px de pantalla, y la imagen de un aspecto a una escala de pantalla y fase de subpíxel."""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

FASES = 2                         # fases de subpíxel por eje de cada sello


def sello(it, clave=None, partes=None, rotulo=False):
    """Marca `it` con su clave de ASPECTO (la capa la dibuja una vez y la copia); devuelve `it`.
    La clave debe llevar TODO lo que cambia su dibujo (texto, colores, estado…), nunca el punto.
    `rotulo` = la marca entera es un rótulo (se oculta si tapa a otro de más prioridad).

    `partes` (en vez de `clave`): la marca se dibuja por PARTES con su propio sello cada una, en
    orden: [(clave, fases, rect, pintar, rotulo)] con `rect` = lo que pinta en coordenadas de la marca
    y `pintar(painter)`. Sirve cuando una parte varía mucho (el texto de una etiqueta: «Codo 12.34°»)
    y otra se repite (su fondo): con un sello por etiqueta entera serían miles de imágenes."""
    try:
        it._pdfcad_sello = (((clave, FASES, None, None, bool(rotulo)),) if partes is None
                            else tuple(tuple(p) + (False,) * (5 - len(p)) for p in partes))
    except AttributeError:
        pass
    return it


def _caja_local(it):
    """(izq, arriba, der, abajo) en px de PANTALLA de lo que pinta la marca respecto de su punto (se
    guarda en la marca: una marca reusada no lo recalcula)."""
    caja = getattr(it, "_pdfcad_caja", None)
    if caja is not None:
        return caja
    r = it.boundingRect()
    if it.childItems():
        r = r | it.childrenBoundingRect()
    t = it.transform()
    if not t.isIdentity():
        r = t.mapRect(r)
    caja = (r.left(), r.top(), r.right(), r.bottom())
    try:
        it._pdfcad_caja = caja
    except AttributeError:
        pass
    return caja


def _caja_rotulo(it):
    """Caja (px de pantalla respecto del punto) de las partes RÓTULO de la marca, o None si no tiene."""
    caja = getattr(it, "_pdfcad_rot", False)
    if caja is not False:
        return caja
    caja, r = None, None
    for _clave, _fases, rect, _pintar, rot in getattr(it, "_pdfcad_sello", None) or ():
        if not rot:
            continue
        if rect is not None:
            q = QtCore.QRectF(rect)
        else:
            q = it.boundingRect()
            if it.childItems():
                q = q | it.childrenBoundingRect()
        r = q if r is None else r | q
    if r is not None:
        t = it.transform()
        if not t.isIdentity():
            r = t.mapRect(r)
        caja = (r.left(), r.top(), r.right(), r.bottom())
    try:
        it._pdfcad_rot = caja
    except AttributeError:
        pass
    return caja


def _extension(it):
    """Radio en px de PANTALLA de lo que pinta la marca alrededor de su punto."""
    return max(abs(v) for v in _caja_local(it)) + 2.0


def _pintar(painter, it, base, opcion, widget):
    """Pinta `it` (y sus hijos) con `base` = su transformación local → pantalla."""
    if not it.isVisible():
        return
    painter.save()
    painter.setWorldTransform(base)
    opcion.exposedRect = it.boundingRect()
    it.paint(painter, opcion, widget)
    painter.restore()
    for h in sorted(it.childItems(), key=lambda c: c.zValue()):
        _pintar(painter, h, h.transform() * QtGui.QTransform.fromTranslate(h.pos().x(), h.pos().y()) * base,
                opcion, widget)


class _Sello:
    """Imagen de un aspecto a una escala de pantalla y una FASE de subpíxel: `pm` y su esquina
    (`ox`, `oy`) en px FÍSICOS (enteros) respecto del píxel donde cae el punto de la marca."""
    __slots__ = ("pm", "ox", "oy")

    def __init__(self, pm, ox, oy):
        self.pm, self.ox, self.oy = pm, ox, oy


def _hacer_sello(it, parte, dpr, fx, fy, hints, widget):
    """Dibuja `it` (con sus hijos) —o solo su `parte` (rect, pintar)— con su punto en la fase
    (`fx`, `fy`) ∈ [0, 1) de un píxel físico: el mismo dibujo que Qt haría con el punto ahí."""
    rect, pintar = parte
    t = it.transform()
    if rect is None:
        r = it.boundingRect()
        if it.childItems():
            r = r | it.childrenBoundingRect()
    else:
        r = QtCore.QRectF(rect)
    if not t.isIdentity():
        r = t.mapRect(r)
    ox, oy = math.floor(r.left() * dpr + fx) - 2, math.floor(r.top() * dpr + fy) - 2
    w, h = math.ceil(r.right() * dpr + fx) + 2 - ox, math.ceil(r.bottom() * dpr + fy) + 2 - oy
    img = QtGui.QImage(max(1, w), max(1, h), QtGui.QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHints(hints)
    base = t * QtGui.QTransform.fromTranslate((fx - ox) / dpr, (fy - oy) / dpr)
    if pintar is None:
        _pintar(p, it, base, QtWidgets.QStyleOptionGraphicsItem(), widget)
    else:
        p.setWorldTransform(base)
        pintar(p)
    p.end()
    return _Sello(QtGui.QPixmap.fromImage(img), ox, oy), img.width() * img.height() * 4
