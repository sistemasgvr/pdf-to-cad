"""composite_renders.py — las imágenes de las piezas del compositor quedan en memoria entre aperturas.

Pedido del usuario (2026-11-17): con la hoja compuesta ya armada, volver a «Componer hoja de trabajo» para sumar una
hoja volvía a dibujar TODAS las piezas (`CompositeView.rebuild` → `render_piece_raw`, ~0.5 s por pieza: con 54 hojas,
casi medio minuto) aunque ninguna había cambiado. Aquí se guarda cada imagen con TODO lo que la decide: el contenido
del PDF (sha1 de sus bytes, `marcar`), la hoja, el recorte, el polígono, la escala del dibujo y el estado de las capas
del documento. Mismo dato → la MISMA imagen (es la que se dibujó); cualquier cambio → se dibuja de nuevo.

Memoria acotada (`MAX_MB`, las más viejas se sueltan). Un documento sin `marcar` no usa la memoria.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

MAX_MB = 512

_IMAGENES: "OrderedDict[tuple, tuple]" = OrderedDict()     # clave → (pixmap, origen, bytes)
_bytes = 0
_HUELLAS: dict = {}                                         # id(bytes) → (bytes, sha1)


def marcar(doc, data) -> None:
    """Anota en `doc` la huella de sus bytes (el PDF de origen tal cual)."""
    try:
        hit = _HUELLAS.get(id(data))
        if hit is not None and hit[0] is data:
            h = hit[1]
        else:
            h = hashlib.sha1(data).hexdigest()
            if len(_HUELLAS) > 64:
                _HUELLAS.clear()
            _HUELLAS[id(data)] = (data, h)
        doc._pdfcad_huella = h
        doc._pdfcad_datos = data              # (los bytes, sin copiar: `composite_renders_lote` los manda a dibujar)
    except Exception:                                       # noqa: BLE001 — sin huella, sin memoria
        pass


def clave(doc, piece, escala: float):
    h = getattr(doc, "_pdfcad_huella", None)
    if not h:
        return None
    try:
        capas = tuple((c.get("number"), bool(c.get("on"))) for c in (doc.layer_ui_configs() or ()))
    except Exception:                                       # noqa: BLE001
        capas = None
    return (h, int(piece.page), tuple(float(v) for v in piece.clip),
            tuple(tuple(float(c) for c in pt) for pt in (piece.polygon or ())), repr(float(escala)), capas)


def buscar(k):
    if k is None:
        return None
    hit = _IMAGENES.get(k)
    if hit is None:
        return None
    _IMAGENES.move_to_end(k)
    return hit[0], hit[1]


def guardar(k, pixmap, origen) -> None:
    global _bytes
    if k is None or pixmap is None:
        return
    tam = max(0, pixmap.width() * pixmap.height() * 4)
    if tam > MAX_MB * 1024 * 1024:
        return
    viejo = _IMAGENES.pop(k, None)
    if viejo is not None:
        _bytes -= viejo[2]
    _IMAGENES[k] = (pixmap, origen, tam)
    _bytes += tam
    while _bytes > MAX_MB * 1024 * 1024 and _IMAGENES:
        _k, (_p, _o, b) = _IMAGENES.popitem(last=False)
        _bytes -= b


def soltar() -> None:
    global _bytes
    _IMAGENES.clear()
    _bytes = 0
