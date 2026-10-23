"""recognition_grosor_tinta.py — de qué utilidad es la TINTA donde cae cada guía (PURO; ver
`recognition_grosor`).

Pedido del usuario 2026-10-22: «si no estamos 100 % seguros de que esa información le pertenece a
esa utilidad, no hay que ponerla». Un rótulo que no nombra su utilidad la deduce de su material, y
un material vale para varias («PROP METRO 8" HDPE», el drenaje de la vía en DU08/DU10: agua,
alcantarillado, drenaje, gas, telecom); cada utilidad se reconoce aparte, así que la guía que llega
a ese drenaje se lo daba también a la tubería de agua o de gas que pasaba por ahí. La punta de la
guía cae sobre la tubería de la que habla: la utilidad de la tinta más cercana (capas de la
utilidad por su nombre, sin las de texto y anotaciones: ahí van las propias guías) decide. Si dos
utilidades quedan casi igual de cerca (un cruce) o no hay tinta de ninguna, no se sabe (None).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

RADIO_PT = 6.0          # la tinta de la tubería a esto de la punta (la punta cae sobre ella o su pared)
EMPATE_PT = 1.0         # otra utilidad así de cerca más: no se sabe de cuál habla
CELDA_PT = 12.0
NO_TUBERIA = ("ANNO", "TEXT", "TXT", "DIMS", "NOTE", "TTLB", "LABL", "LABEL")


def _dist(p: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(a[0] + t * vx - p[0], a[1] + t * vy - p[1])


def utilidades_en_puntas(dibujos: Sequence[dict], px: Callable[[Pt], Pt], zoom: float,
                         puntas: Sequence[Pt], capas_texto=(), ocultas=()) -> List[Optional[str]]:
    """La utilidad de la tinta en cada punta (px), o None."""
    from hoja import pdf_layers
    if not puntas:
        return []
    radio, celda = RADIO_PT * zoom, CELDA_PT * zoom
    # solo las celdas de alrededor de las puntas: la hoja compuesta trae cientos de miles de tramos
    buscadas = set()
    for p in puntas:
        cx, cy = int(math.floor(p[0] / celda)), int(math.floor(p[1] / celda))
        buscadas.update((cx + i, cy + j) for i in (-1, 0, 1) for j in (-1, 0, 1))
    capas_texto, ocultas = set(capas_texto or ()), set(ocultas or ())
    util_de: Dict[str, Optional[str]] = {}
    en: Dict[Tuple[int, int], List[Tuple[Pt, Pt, str]]] = defaultdict(list)
    for d in dibujos:
        capa = d.get("layer") or ""
        if capa not in util_de:
            corto = pdf_layers.short_name(capa).upper()
            u = pdf_layers.utility_of(capa)
            util_de[capa] = None if (not capa or capa in capas_texto or capa in ocultas
                                     or u == pdf_layers.UTILITY_OTHER
                                     or any(t in corto for t in NO_TUBERIA)) else u
        u = util_de[capa]
        if u is None:
            continue
        r = d.get("rect")
        if r is not None:
            # la caja del trazo (en la vista) no toca ninguna celda buscada: nada de él sirve
            cs = [px((r.x0, r.y0)), px((r.x1, r.y0)), px((r.x1, r.y1)), px((r.x0, r.y1))]
            x0, x1 = (int(math.floor(min(c[0] for c in cs) / celda)), int(math.floor(max(c[0] for c in cs) / celda)))
            y0, y1 = (int(math.floor(min(c[1] for c in cs) / celda)), int(math.floor(max(c[1] for c in cs) / celda)))
            if (x1 - x0 + 1) * (y1 - y0 + 1) <= 400 and not any(
                    (cx, cy) in buscadas for cx in range(x0, x1 + 1) for cy in range(y0, y1 + 1)):
                continue
        for it in d.get("items") or ():
            if it[0] == "l":
                pares = ((it[1], it[2]),)
            elif it[0] == "c":
                pares = ((it[1], it[4]),)
            elif it[0] == "re":
                r = it[1]
                pares = ((r.tl, r.tr), (r.tr, r.br), (r.br, r.bl), (r.bl, r.tl))
            else:
                continue
            for a0, b0 in pares:
                a, b = px((a0.x, a0.y)), px((b0.x, b0.y))
                x0, x1 = sorted((int(math.floor(a[0] / celda)), int(math.floor(b[0] / celda))))
                y0, y1 = sorted((int(math.floor(a[1] / celda)), int(math.floor(b[1] / celda))))
                if (x1 - x0 + 1) * (y1 - y0 + 1) > 400:
                    # tramo largo: solo las celdas buscadas de su caja
                    for c in buscadas:
                        if x0 <= c[0] <= x1 and y0 <= c[1] <= y1:
                            en[c].append((a, b, u))
                    continue
                for cx in range(x0, x1 + 1):
                    for cy in range(y0, y1 + 1):
                        if (cx, cy) in buscadas:
                            en[(cx, cy)].append((a, b, u))
    out: List[Optional[str]] = []
    for p in puntas:
        cx, cy = int(math.floor(p[0] / celda)), int(math.floor(p[1] / celda))
        mejor: Dict[str, float] = {}
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for a, b, u in en.get((cx + i, cy + j), ()):
                    dd = _dist(p, a, b)
                    if dd <= radio and dd < mejor.get(u, math.inf):
                        mejor[u] = dd
        if not mejor:
            out.append(None)
            continue
        orden = sorted(mejor.items(), key=lambda kv: kv[1])
        if len(orden) > 1 and orden[1][1] - orden[0][1] <= EMPATE_PT * zoom:
            out.append(None)
        else:
            out.append(orden[0][0])
    return out
