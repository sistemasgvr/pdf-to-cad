"""recognition_grosor_partir.py — una ruta con DOS diámetros se parte en el nodo donde cambia (PURO;
ver `recognition_grosor`).

Reporte del usuario 2026-10-22 (DU06): «que se reconozca lo más que se pueda… ya no dejarlo en
por defecto». La principal de DU06 h.5 es UNA polilínea de borde a borde de la vista (el núcleo
no la corta: los laterales llegan en T), pero sus rótulos dicen 84" hasta el pozo de x≈1095 y
81" después; en h.11, 81" hasta el pozo de x≈426 y 78" después. Con un solo `diam_in` por línea
quedaba sin diámetro (12" por defecto). Lo mismo con una ruta que une dos laterales distintos
cruzando la principal (h.4: 18" y 33" en una «V» por una esquina).

`vertice_de_corte`: los rótulos de la línea ordenados a lo largo de ella forman ZONAS de un mismo
diámetro (si un diámetro vuelve después de otro, no se parte: no se entiende); entre la última
marca de una zona y la primera de la siguiente se parte en el NODO que haya (bóveda > unión/T >
esquina > quiebre), y si hay dos del mismo tipo, en ninguno. `partir` corta la polilínea en ese
vértice: las piezas comparten el vértice; nada se mueve ni se agrega.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

NODOS = {"vault": 0, "junction": 1, "tee": 1, "corner": 2, "bend": 3}
CORTE_HOLGURA_PT = 4.0        # un nodo justo antes/después de la marca de una zona también vale
PIEZA_MIN_PT = 12.0           # cada pieza al menos esto de largo


def proyeccion(pts: Sequence[Pt], p: Pt) -> Tuple[float, float, int]:
    """(distancia a lo largo de la línea, distancia a ella, tramo) del pie de p."""
    mejor = (math.inf, 0.0, 0)
    s0 = 0.0
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        L = math.sqrt(L2)
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
        d = math.hypot(a[0] + t * vx - p[0], a[1] + t * vy - p[1])
        if d < mejor[0]:
            mejor = (d, s0 + t * L, i)
        s0 += L
    return mejor[1], mejor[0], mejor[2]


def rumbo_en(pts: Sequence[Pt], p: Pt) -> Tuple[float, float]:
    """Dirección unitaria del tramo de la línea más cercano a p."""
    _s, _d, i = proyeccion(pts, p)
    a, b = pts[i], pts[i + 1]
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return (b[0] - a[0]) / L, (b[1] - a[1]) / L


def _dist_seg(p: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(a[0] + t * vx - p[0], a[1] + t * vy - p[1])


def _cruzan(a: Pt, b: Pt, c: Pt, d: Pt) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) <= 0 and o(c, d, a) * o(c, d, b) <= 0


def dist_tramo_linea(a: Pt, b: Pt, pts: Sequence[Pt]) -> float:
    """Distancia del tramo a–b a la polilínea (0 si la cruza)."""
    mejor = math.inf
    for c, d in zip(pts, pts[1:]):
        if _cruzan(a, b, c, d):
            return 0.0
        mejor = min(mejor, _dist_seg(a, c, d), _dist_seg(b, c, d), _dist_seg(c, a, b), _dist_seg(d, a, b))
    return mejor


def _largos(pts: Sequence[Pt]) -> List[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def zonas(marcas: Sequence[Tuple[float, float]]) -> Optional[List[int]]:
    """Zona de cada marca [(posición, diámetro)] (en su orden): marcas seguidas a lo largo de la
    línea con el mismo diámetro son una zona. None si un diámetro vuelve después de otro."""
    orden = sorted(range(len(marcas)), key=lambda k: marcas[k][0])
    out = [0] * len(marcas)
    vistos: List[float] = []
    for k in orden:
        d = marcas[k][1]
        if not vistos or vistos[-1] != d:
            if d in vistos:
                return None
            vistos.append(d)
        out[k] = len(vistos) - 1
    return out


def vertices_de_corte(pts: Sequence[Pt], kinds: Sequence[str], marcas: Sequence[Tuple[float, float]],
                      zoom: float) -> Optional[List[int]]:
    """Vértices donde partir una línea con marcas [(posición, diámetro)] de varios diámetros (uno
    entre cada dos zonas, ver `zonas`), o None si no se entiende (un diámetro que vuelve, o sin
    un único nodo entre dos zonas)."""
    zs = zonas(marcas)
    if zs is None or len(kinds) != len(pts) or len(pts) < 3 or max(zs, default=0) < 1:
        return None
    rango = {}
    for (s, _d), z in zip(marcas, zs):
        lo, hi = rango.get(z, (s, s))
        rango[z] = (min(lo, s), max(hi, s))
    acum = _largos(pts)
    holgura = CORTE_HOLGURA_PT * zoom
    cortes: List[int] = []
    for z in range(max(zs)):
        fin, ini = rango[z][1], rango[z + 1][0]
        cand = [(NODOS[kinds[i]], i) for i in range(1, len(pts) - 1)
                if kinds[i] in NODOS and fin - holgura <= acum[i] <= ini + holgura
                and (not cortes or i > cortes[-1])]
        if not cand:
            return None
        mejor = min(c[0] for c in cand)
        tope = [i for c, i in cand if c == mejor]
        if len(tope) != 1:
            return None
        cortes.append(tope[0])
    bordes = [0] + cortes + [len(pts) - 1]
    if any(acum[j] - acum[i] < PIEZA_MIN_PT * zoom for i, j in zip(bordes, bordes[1:])):
        return None
    return cortes


def partir(pl, cortes: Sequence[int]) -> list:
    """Las piezas de la polilínea cortada en esos vértices (cada una con su parte de los vértices,
    tipos y codos; sin `grosor`: se calcula para cada pieza)."""
    out = []
    bordes = [0] + list(cortes) + [len(pl.pts_pdf) - 1]
    for i, j in zip(bordes, bordes[1:]):
        out.append(replace(
            pl, pts_pdf=list(pl.pts_pdf[i:j + 1]), kinds=list(pl.kinds[i:j + 1]),
            fillets={k - i: f for k, f in (pl.fillets or {}).items() if i < k < j}, grosor={}))
    return out
