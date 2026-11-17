"""composite_agregar.py — ¿la hoja compuesta nueva solo AGREGA hojas a la del editor? (PURO, sin Qt ni fitz).

Pedido del usuario (2026-11-17): con la composición ya en el editor, «Componer hoja de trabajo» para sumar una hoja
de otro PDF borraba todo (`_load_page` → `_reset_model`) y por eso preguntaba antes si guardar o descartar. Si la
hoja nueva conserva TODAS las piezas de antes en el MISMO lugar de la hoja de trabajo (mismas coordenadas de página),
lo dibujado y lo reconocido siguen valiendo tal cual: solo cambia la imagen de fondo y aparece el área nueva.

`solo_agrega` lo decide comparando, por cada pieza de antes, su contenido (PDF por huella, hoja, recorte, polígono,
giro, escala) y su rectángulo EN LA PÁGINA de trabajo (pt de la pieza + el corrimiento de `sheet_geometry`). Una
pieza de antes que falta o se movió, otra escala de la hoja, capas ocultas distintas en un PDF de antes, o una hoja
nueva a la izquierda / arriba (cambia el origen de la página) = no: hay que rearmar todo.
"""
from __future__ import annotations

import json
from typing import Callable, Sequence, Tuple

from hoja import composite as C

TOL_PT = 1e-6


def _contenido(p: C.Piece, huellas: Sequence[str]) -> str:
    d = p.to_dict()
    d.pop("x", None)
    d.pop("y", None)
    d["source"] = huellas[p.source] if 0 <= p.source < len(huellas) else None
    return json.dumps(d, sort_keys=True, default=str)


def _rect_en_pagina(comp: C.Composite, p: C.Piece, tam: Callable) -> Tuple[float, ...]:
    _w, _h, dx, dy = C.sheet_geometry(comp, tam)
    x0, y0, x1, y1 = C.piece_rect(p, tam(p), comp.target_scale())
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy)


def solo_agrega(antes: C.Composite, huellas_antes: Sequence[str], ocultas_antes: dict,
                nueva: C.Composite, huellas_nuevas: Sequence[str], ocultas_nuevas: dict,
                tam_antes: Callable, tam_nuevo: Callable) -> bool:
    """True si `nueva` = `antes` + piezas nuevas, sin mover nada de lo que ya había en la página de trabajo.
    `tam_*(pieza)` = (ancho, alto) en pt de su hoja de origen; `ocultas_*` = capas ocultas por índice de PDF."""
    if antes is None or nueva is None or not antes.pieces:
        return False
    if bool(antes.manual) != bool(nueva.manual) or len(nueva.pieces) <= len(antes.pieces):
        return False
    if antes.is_single_full_page():
        return False                       # la hoja entera no lleva el margen de la compuesta: otro origen
    if antes.marco is not None or nueva.marco is not None:
        return False
    if abs(antes.target_scale() - nueva.target_scale()) > 1e-12:
        return False
    norm = lambda h: sorted(h or ())        # noqa: E731
    for s in {p.source for p in antes.pieces}:
        if s >= len(huellas_nuevas) or s >= len(huellas_antes) or huellas_antes[s] != huellas_nuevas[s]:
            return False
        if norm((ocultas_antes or {}).get(str(s))) != norm((ocultas_nuevas or {}).get(str(s))):
            return False
    libres = list(range(len(nueva.pieces)))
    for p in antes.pieces:
        clave = _contenido(p, huellas_antes)
        r = _rect_en_pagina(antes, p, tam_antes)
        hallada = None
        for k in libres:
            q = nueva.pieces[k]
            if _contenido(q, huellas_nuevas) != clave:
                continue
            rq = _rect_en_pagina(nueva, q, tam_nuevo)
            if all(abs(a - b) <= TOL_PT for a, b in zip(r, rq)):
                hallada = k
                break
        if hallada is None:
            return False
        libres.remove(hallada)
    return True
