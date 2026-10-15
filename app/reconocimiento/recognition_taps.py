"""recognition_taps.py — las ACOMETIDAS de un mapa sin capas llegan a su tubería (PURO).

Las acometidas («As-Built Tap», `hoja.acometidas_mapa`) son trazos que NACEN sobre la tinta
de la red; la tubería reconocida es esa tinta simplificada (a ≤ medio grosor del trazo,
`recognition_ink_lines.simplify_tol`), así que la punta queda a unas décimas de pt de ella.
Este paso, sobre la salida, la lleva al punto MÁS CERCANO de la tubería (≤ `SNAP_PT`) y la
marca «tee»: la T es exacta en el editor y el plugin parte ahí la tubería
(`PartirTramosEnTes`, red a presión). La tubería no se toca.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from hoja import acometidas_mapa, pdf_styles
from reconocimiento import recognition_indice as indice_mod

Pt = Tuple[float, float]

SNAP_PT = 0.8                # punta de la acometida a ≤ esto de la tubería (pt; × zoom en px)


def _foot(p: Pt, a: Pt, b: Pt) -> Tuple[float, Pt]:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    q = (a[0] + t * vx, a[1] + t * vy)
    return math.dist(p, q), q


def is_tap(pl) -> bool:
    return acometidas_mapa.es_capa(getattr(pl, "layer_ocg", "") or "")


def snap_taps(polylines: Sequence, zoom: float) -> List[Pt]:
    """Lleva la punta de cada acometida a su tubería (ver el docstring). Modifica
    `polylines` en su lugar; devuelve el punto (px) de cada T."""
    mains = [pl for pl in polylines if len(pl.pts_pdf) >= 2 and not is_tap(pl)
             and (pl.layer_ocg or "").startswith(pdf_styles.PREFIX) and not pdf_styles.is_symbol(pl.layer_ocg)]
    if not mains:
        return []
    boxes = [(min(x for x, _ in pl.pts_pdf), min(y for _, y in pl.pts_pdf),
              max(x for x, _ in pl.pts_pdf), max(y for _, y in pl.pts_pdf)) for pl in mains]
    lim = SNAP_PT * zoom
    # solo los tramos a ≤ lim de la punta, en el orden de siempre (`recognition_indice`)
    tramos = [list(zip(m.pts_pdf, m.pts_pdf[1:])) for m in mains]
    indice = indice_mod.IndiceTramos(tramos, lim)
    out: List[Pt] = []
    for pl in polylines:
        if not is_tap(pl) or len(pl.pts_pdf) < 2 or len(pl.kinds) != len(pl.pts_pdf):
            continue
        for j in (0, len(pl.pts_pdf) - 1):
            p = pl.pts_pdf[j]
            best = None
            for k, t in indice.cerca(p):
                bx = boxes[k]
                if not (bx[0] - lim <= p[0] <= bx[2] + lim and bx[1] - lim <= p[1] <= bx[3] + lim):
                    continue
                a, b = tramos[k][t]
                d, q = _foot(p, a, b)
                if d <= lim and (best is None or d < best[0]):
                    best = (d, q)
            if best is not None:
                pl.pts_pdf[j] = (float(best[1][0]), float(best[1][1]))
                pl.kinds[j] = "tee"
                out.append(pl.pts_pdf[j])
                break                                  # una punta por acometida
    return out
