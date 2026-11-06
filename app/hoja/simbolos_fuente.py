"""simbolos_fuente.py — símbolos de una hoja sin capas ni leyenda dibujados con una FUENTE (pedido 2026-11-05).

Southwest Gas (ArcGIS) dibuja sus marcas con fuentes de símbolos: `ESRIAMFMGas`, `ESRIDefaultMarker`… Son texto, no
vectores, así que `get_drawings` no los ve, y sin leyenda nada dice qué es cada uno. Aquí cada glifo de esas fuentes es
una capa virtual más de «Capas de la hoja» (un círculo en su lugar, como `leyenda_mapa.simbolos_capas`): el usuario
decide cuál es una válvula con el rol «Válvulas». Sin asignar, no se reconocen ni cambian nada.
"""
from __future__ import annotations

import re
from typing import List

import fitz

from hoja import pdf_styles

FUENTES = re.compile(r"ESRI|WINGDINGS|WEBDINGS|MARKER", re.I)
RADIO_MIN = 0.3


def _circulo(cx, cy, r) -> list:
    k = 0.5523 * r
    P = fitz.Point
    return [("c", P(cx + r, cy), P(cx + r, cy + k), P(cx + k, cy + r), P(cx, cy + r)),
            ("c", P(cx, cy + r), P(cx - k, cy + r), P(cx - r, cy + k), P(cx - r, cy)),
            ("c", P(cx - r, cy), P(cx - r, cy - k), P(cx - k, cy - r), P(cx, cy - r)),
            ("c", P(cx, cy - r), P(cx + k, cy - r), P(cx + r, cy - k), P(cx + r, cy))]


def capas(page) -> List[dict]:
    """Un trazo virtual por glifo de una fuente de símbolos; [] si la hoja no usa ninguna."""
    if not any(FUENTES.search(f[3] or "") for f in page.get_fonts()):
        return []
    out = []
    for span in page.get_texttrace():
        fuente = span.get("font") or ""
        if not FUENTES.search(fuente):
            continue
        color = [round(float(c), 2) for c in span.get("color") or ()]
        for ch in span.get("chars") or ():
            x0, y0, x1, y1 = ch[3]
            r = max((x1 - x0) / 2.0, (y1 - y0) / 2.0, RADIO_MIN)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            out.append({"type": "s", "items": _circulo(cx, cy, r), "closePath": True,
                        "rect": fitz.Rect(cx - r, cy - r, cx + r, cy + r), "color": (0.0, 0.0, 0.0), "fill": None,
                        "width": 0.1, "dashes": "[] 0", "even_odd": False, "stroke_opacity": 1.0, "fill_opacity": None,
                        "lineCap": (0, 0, 0), "lineJoin": 0, "seqno": -1, "level": 0, "symbol": True,
                        "layer": pdf_styles.symbol_name(fuente, ((int(ch[1]), color),))})
    return out
