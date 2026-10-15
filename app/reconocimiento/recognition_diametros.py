"""recognition_diametros.py — el DIÁMETRO que el plano escribe junto a cada tubería (PURO).

Mapas SIG aplanados (Quarter Section de Phoenix; pedido del usuario 2026-10-14: «la leyenda
indica cada uno de los detalles… hay que trabajarlo de esa manera»): cada tramo de la red
lleva su rótulo PARALELO a la línea y pegado a ella — «6"», «8" DIP», «12" CIP», «48"» — y
cada acometida con otro tamaño que el de la nota de la leyenda («.75"»), su estación y su
diámetro: «278' 2"». El texto se lee con `hoja.texto_pdf` (Type3 sin mapa de caracteres).

  · `rotulos(page)`: [(centro, dirección, tamaño de letra, pulgadas, es_de_acometida)] en
    coordenadas de la hoja sin girar.
  · `asignar(polylines, rotulos_px, es_acometida)`: cada rótulo va a la tubería MÁS CERCANA
    (≤ `DIST_MAX` × tamaño de letra) que corre paralela a él (±25°, `PARALELO_MIN`); los de
    acometida solo a acometidas y los otros solo a la red. Una tubería toma el valor de
    ≥ `MAYORIA` de sus rótulos (una red unida de frente puede juntar tramos con su propio
    rótulo: 6" y 8" a los lados de una reducción); si no hay mayoría queda sin diámetro
    del plano y se cuenta para el aviso. Escribe `pl.diam_in`; no mueve nada.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable, Dict, List, Sequence, Tuple

from reconocimiento import recognition_indice as indice_mod

RX_DIAM = re.compile(r"""^\s*(\d{1,2}(?:\.\d+)?)\s*"\s*([A-Z]{2,6})?\s*$""")      # «8"», «12" DIP»
RX_ACOMETIDA = re.compile(r"""^\s*\d+'\s*(\d{1,2}(?:\.\d+)?)\s*"\s*$""")         # «278' 2"»
DIST_MAX = 4.0               # × tamaño de letra: el rótulo va pegado a su línea
PARALELO_MIN = 0.9           # |cos| entre el texto y el tramo (±25°)
MAYORIA = 0.6                # de los rótulos de una tubería que deben decir lo mismo

Rotulo = Tuple[Tuple[float, float], Tuple[float, float], float, float, bool]


def rotulos(page) -> List[Rotulo]:
    """Rótulos de diámetro de la hoja (ver el docstring del módulo)."""
    from hoja import texto_pdf
    out: List[Rotulo] = []
    for c in texto_pdf.corridas(page):
        m, mt = RX_DIAM.match(c.texto), RX_ACOMETIDA.match(c.texto)
        if not (m or mt):
            continue
        try:
            pulg = float((m or mt).group(1))
        except ValueError:
            continue
        if pulg <= 0:
            continue
        # centro del texto: medio de la línea base, subido media altura de letra
        cx = (c.origen[0] + c.fin[0]) / 2.0 + c.dir[1] * 0.35 * c.tam
        cy = (c.origen[1] + c.fin[1]) / 2.0 - c.dir[0] * 0.35 * c.tam
        out.append(((cx, cy), (float(c.dir[0]), float(c.dir[1])), float(c.tam), pulg, bool(mt)))
    return out


def _cerca(c, d, pl) -> Tuple[float, float]:
    """(distancia del centro del rótulo a la polilínea, |cos| con el tramo más cercano)."""
    best = (math.inf, 0.0)
    for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(vx, vy)
        if L < 1e-9:
            continue
        t = max(0.0, min(1.0, ((c[0] - a[0]) * vx + (c[1] - a[1]) * vy) / (L * L)))
        dist = math.hypot(a[0] + t * vx - c[0], a[1] + t * vy - c[1])
        if dist < best[0]:
            best = (dist, abs(vx * d[0] + vy * d[1]) / L)
    return best


def asignar(polylines: Sequence, rotulos_px: Sequence[Rotulo],
            es_acometida: Callable[[object], bool]) -> Dict[str, int]:
    """Pone `diam_in` a cada tubería con rótulos (ver el docstring). Devuelve la cuenta:
    {"con": tuberías con diámetro del plano, "mezcla": sin mayoría, "rotulos": usados}."""
    lines = [pl for pl in polylines if len(pl.pts_pdf) >= 2]
    boxes = [(min(x for x, _ in pl.pts_pdf), min(y for _, y in pl.pts_pdf),
              max(x for x, _ in pl.pts_pdf), max(y for _, y in pl.pts_pdf)) for pl in lines]
    votos: Dict[int, List[float]] = {}
    usados = 0
    # cada rótulo mira solo las tuberías con un tramo a su alcance (`recognition_indice`;
    # todas contra todos eran minutos en una hoja compuesta); mismo orden, mismo resultado
    acometida = [bool(es_acometida(pl)) for pl in lines]
    alcance = DIST_MAX * max((r[2] for r in rotulos_px), default=0.0)
    indice = indice_mod.IndiceTramos([list(zip(pl.pts_pdf, pl.pts_pdf[1:])) for pl in lines], alcance)
    for c, d, tam, pulg, de_acometida in rotulos_px:
        lim = DIST_MAX * tam
        best = None
        for k in sorted({k for k, _j in indice.cerca(c)}):
            pl, bx = lines[k], boxes[k]
            if acometida[k] != de_acometida:
                continue
            if not (bx[0] - lim <= c[0] <= bx[2] + lim and bx[1] - lim <= c[1] <= bx[3] + lim):
                continue
            dist, par = _cerca(c, d, pl)
            if dist <= lim and par >= PARALELO_MIN and (best is None or dist < best[0]):
                best = (dist, k)
        if best is not None:
            votos.setdefault(best[1], []).append(pulg)
            usados += 1
    con = mezcla = 0
    for k, vs in votos.items():
        valor, n = Counter(vs).most_common(1)[0]
        if n >= MAYORIA * len(vs):
            lines[k].diam_in = valor
            con += 1
        else:
            mezcla += 1
            if not getattr(lines[k], "review", ""):
                lines[k].review = "diam_mix"           # «Para verificar»: clic → ir a ella
    return {"con": con, "mezcla": mezcla, "rotulos": usados}
