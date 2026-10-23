"""recognition_grosor_tramos.py — el diámetro de una ruta de un mapa, TRAMO por TRAMO del SIG (PURO;
lo usa `recognition_grosor_mapa`).

Un mapa SIG dibuja la red como trazos sueltos, uno por tramo de la base de datos (entre válvulas,
uniones o accesorios), y UN tramo tiene UN diámetro. El reconocimiento une los trazos que siguen de
frente en una ruta (`routes`), así que una ruta puede cruzar varias tuberías: en QS Water South h.4
una de 965 pt junta 48" PCCP, 54" PCCP, 8" DIP y 6" DIP (antes tomaba el valor de la mayoría para
toda la ruta). Aquí:

  · `limites`: los vértices donde empieza otro tramo (unión, otro trazo, buzón; no el de un codo);
  · `valor`: el diámetro de un tramo por sus rótulos — todos iguales, o una mayoría clara (≥ 2 que
    dicen lo mismo y al menos el doble que los demás: un tramo no tiene dos diámetros, el que
    sobra es de otra línea); si no, `CONFLICTO`;
  · `estados`: un tramo sin rótulos toma el diámetro de sus vecinos si los dos dicen lo mismo (o
    el único que tiene, al final de la ruta); entre dos diámetros distintos no se sabe dónde cambia:
    dudoso con los dos;
  · `piezas`: tramos seguidos con el mismo estado = una pieza; la ruta se parte entre piezas.
"""
from __future__ import annotations

import bisect
from collections import Counter
from typing import List, Optional, Sequence, Tuple

from reconocimiento import recognition_grosor_partir as P

CONFLICTO = "conflicto"
MAYORIA_MIN = 2               # rótulos que dicen lo mismo para ganarle a otro en el mismo tramo
MAYORIA_VECES = 2.0           # …y al menos estas veces los que dicen otra cosa

Estado = Tuple                # ("leido", v) | ("dudoso", (candidatos…), fuente) | ("sin",)


def limites(pl, clases: Sequence[str]) -> List[int]:
    """Vértices que separan tramos (y las dos puntas). Nunca el vértice de un codo: partir ahí lo
    perdería."""
    n = len(pl.pts_pdf)
    codos = set((getattr(pl, "fillets", None) or {}).keys())
    return [0] + [i for i in range(1, n - 1) if clases[i] != "bend" and i not in codos] + [n - 1]


def tramo_de(pts, lims: Sequence[int], p) -> int:
    """Índice del tramo donde cae el pie de p."""
    _s, _d, seg = P.proyeccion(pts, p)
    return max(0, min(len(lims) - 2, bisect.bisect_right(lims, seg) - 1))


def valor(pulgadas: Sequence[float]):
    """Diámetro del tramo por sus rótulos, None sin rótulos, `CONFLICTO` si no se sabe."""
    if not pulgadas:
        return None
    c = Counter(pulgadas).most_common()
    if len(c) == 1:
        return c[0][0]
    resto = sum(m for _v, m in c[1:])
    if c[0][1] >= MAYORIA_MIN and c[0][1] >= MAYORIA_VECES * resto:
        return c[0][0]
    return CONFLICTO


def estados(valores: Sequence, candidatos: Sequence[Sequence[float]], dudas: Sequence[Sequence[float]]) -> List[Estado]:
    """Estado de cada tramo (ver el docstring). `candidatos[f]` = lo que dicen los rótulos de un tramo
    en conflicto; `dudas[f]` = lo que dicen rótulos que QUIZÁ son de él (`asignar`): un tramo que solo
    toma el diámetro de sus vecinos queda dudoso si uno de esos dice otra cosa."""
    n = len(valores)
    out: List[Optional[Estado]] = [None] * n
    for f, v in enumerate(valores):
        if v is CONFLICTO:
            out[f] = ("dudoso", tuple(sorted(set(candidatos[f]))), "mezcla")
        elif v is not None:
            out[f] = ("leido", v)
    tomado = [False] * n
    f = 0
    while f < n:
        if out[f] is not None:
            f += 1
            continue
        g = f
        while g < n and out[g] is None:
            g += 1
        izq = out[f - 1] if f > 0 else None
        der = out[g] if g < n else None
        vi = izq[1] if izq and izq[0] == "leido" else None
        vd = der[1] if der and der[0] == "leido" else None
        if izq is None and der is None:
            st: Estado = ("sin",)
        elif (vi is not None and (vd == vi or der is None)) or (vd is not None and izq is None):
            st = ("leido", vi if vi is not None else vd)
            for h in range(f, g):
                tomado[h] = True
        else:
            cands = set()
            for e in (izq, der):
                if e and e[0] == "leido":
                    cands.add(e[1])
                elif e and e[0] == "dudoso":
                    cands |= set(e[1])
            st = ("dudoso", tuple(sorted(cands)), "cambio")
        for h in range(f, g):
            out[h] = st
        f = g
    for f in range(n):
        st = out[f]
        if (tomado[f] or st[0] == "sin") and dudas[f]:
            v = st[1] if st[0] == "leido" else None
            otros = sorted({d for d in dudas[f] if d != v})
            if otros:
                out[f] = ("dudoso", tuple(sorted(set(otros) | ({v} if v is not None else set()))), "cerca")
    return out


def piezas(lims: Sequence[int], ests: Sequence[Estado]) -> List[Tuple[int, int, Estado, List[int]]]:
    """[(vértice inicial, vértice final, estado, tramos)] juntando tramos seguidos con el mismo estado
    (los dudosos seguidos van en una pieza, con todos sus candidatos; un tramo sin dato junto a uno
    dudoso —ruta sin rótulos propios, con uno que quizá es suyo— va con él: no se parte por eso)."""
    out: List[list] = []
    for f, st in enumerate(ests):
        clave = st if st[0] == "leido" else ("dudoso",)
        if out and out[-1][4] == clave:
            out[-1][1] = lims[f + 1]
            out[-1][3].append(f)
            prev = out[-1][2]
            if st[0] == "dudoso" and prev[0] == "dudoso":
                out[-1][2] = ("dudoso", tuple(sorted(set(prev[1]) | set(st[1]))), prev[2])
            elif st[0] == "dudoso":
                out[-1][2] = st
        else:
            out.append([lims[f], lims[f + 1], st, [f], clave])
    return [(a, b, st, fs) for a, b, st, fs, _c in out]
