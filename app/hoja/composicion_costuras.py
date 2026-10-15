"""composicion_costuras.py — dónde cortar dos hojas de un MAPA que se solapan (composición sugerida).

Las hojas vecinas de un mapa por cuadrícula (Quarter Section de Phoenix) se solapan
55–80 pt. Cada pieza de la hoja compuesta se recorta por una recta dentro de ese
solape; la recta se elige (medido en Phoenix, 2026-10-14):

  · dentro del solape de TINTA, no del de las vistas (`_tinta`: en alcantarillado la
    vista es ~25 pt más ancha que el mapa y quedaba una franja en blanco);
  · donde menos tinta de UNA sola hoja se pierde (cada hoja dibuja su red entera pero
    solo parte de la de la vecina) y menos tramos casi paralelos toca (la calle del
    borde lleva su tubería paralela: una recta encima la parte a lo largo);
  · común a toda la fila/columna de la rejilla si cabe (sin escalones en las esquinas).

PURO. Lo usa `composicion_sugerida.armar`.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

Nodo = Tuple[int, int]                       # (pdf, hoja)

CORTE_MARGEN_PT = 2.0         # el corte queda al menos esto dentro del solape común
TINTA_PERCENTIL = 0.005       # borde de la tinta de una hoja: sin el 0.5 % más extremo (una flecha suelta)
CORTE_PASO_PT = 0.5
CORTE_RASANTE_DEG = 20.0      # cruzar un trazo a menos de esto de la costura no deja un punto de unión firme
GEMELO_PT = 0.3               # el mismo trazo en las dos hojas (ya llevadas a la hoja compuesta)
RASANTE_HOLGURA_PT = 1.5      # un trazo casi paralelo «molesta» a menos de esto del corte…
RASANTE_COSTO_PT = 20.0       # …y cuesta como perder esto de tinta


def _franja(g, fichas: dict, n, eje: int, lo: float, hi: float):
    """Trazos de la hoja `n` (hoja compuesta) que tocan la franja [lo, hi] a través de
    la costura: (c0, c1, s0, s1) con c = coordenada A TRAVÉS (x si la costura es vertical)."""
    a, bx, by = g.transf[n]
    out = []
    for x0, y0, x1, y1, *_r in fichas[n].lineas:
        X0, Y0, X1, Y1 = a * x0 + bx, a * y0 + by, a * x1 + bx, a * y1 + by
        c0, c1, s0, s1 = (X0, X1, Y0, Y1) if eje == 0 else (Y0, Y1, X0, X1)
        if max(c0, c1) < lo - 1.0 or min(c0, c1) > hi + 1.0:
            continue
        out.append((c0, c1, s0, s1))
    return out


def _gemelos(A, B) -> List[bool]:
    """¿Cada trazo de A está también en B (mismos extremos ±GEMELO_PT, en cualquier sentido)?"""
    idx: Dict[Tuple[int, int], list] = defaultdict(list)
    for t in B:
        idx[(round(t[0]), round(t[2]))].append(t)
    out = []
    for c0, c1, s0, s1 in A:
        ok = False
        for k0, k1 in ((c0, s0), (c1, s1)):
            for dc in (-1, 0, 1):
                for ds in (-1, 0, 1):
                    for t in idx.get((round(k0) + dc, round(k1) + ds), ()):
                        if ((abs(t[0] - c0) <= GEMELO_PT and abs(t[2] - s0) <= GEMELO_PT
                             and abs(t[1] - c1) <= GEMELO_PT and abs(t[3] - s1) <= GEMELO_PT)
                                or (abs(t[0] - c1) <= GEMELO_PT and abs(t[2] - s1) <= GEMELO_PT
                                    and abs(t[1] - c0) <= GEMELO_PT and abs(t[3] - s0) <= GEMELO_PT)):
                            ok = True
                            break
                    if ok:
                        break
                if ok:
                    break
            if ok:
                break
        out.append(ok)
    return out


def _costo_corte(trazos_a, gem_a, trazos_b, gem_b):
    """Función costo(x) de cortar en x (a se queda con lo que está ANTES de x, b con lo
    de DESPUÉS): tinta que solo dibuja una hoja y quedaría del lado de la otra (se
    pierde), más los tramos casi paralelos que el corte toca (la unión quedaría
    indefinida a lo largo). Phoenix: cada hoja dibuja SU red entera pero solo parte de
    la de la vecina dentro del solape, y la calle del borde lleva su tubería paralela."""
    tan = math.tan(math.radians(CORTE_RASANTE_DEG))
    solos = []          # (c0, c1, largo, lado): lado +1 = de a (se pierde lo que pasa de x), −1 = de b
    rasantes = []
    for trazos, gem, lado in ((trazos_a, gem_a, 1), (trazos_b, gem_b, -1)):
        for (c0, c1, s0, s1), g_ in zip(trazos, gem):
            lo, hi = min(c0, c1), max(c0, c1)
            L = math.hypot(c1 - c0, s1 - s0)
            if abs(c1 - c0) <= tan * abs(s1 - s0):
                rasantes.append((lo - RASANTE_HOLGURA_PT, hi + RASANTE_HOLGURA_PT))
            if not g_:
                solos.append((lo, hi, L, lado))

    def costo(x: float) -> float:
        perdido = 0.0
        for lo, hi, L, lado in solos:
            if hi <= lo:
                frac = 1.0 if (lado > 0 and lo > x) or (lado < 0 and hi < x) else 0.0
            elif lado > 0:
                frac = min(1.0, max(0.0, (hi - x) / (hi - lo)))
            else:
                frac = min(1.0, max(0.0, (x - lo) / (hi - lo)))
            perdido += frac * L
        return perdido + RASANTE_COSTO_PT * sum(1 for lo, hi in rasantes if lo < x < hi)
    return costo


def _mejor_corte(lo: float, hi: float, costos) -> float:
    """Posición del corte en [lo, hi] que menos tinta pierde (a igualdad, la más
    cercana al medio). Sin nada que perder, el medio."""
    a, b = lo + CORTE_MARGEN_PT, hi - CORTE_MARGEN_PT
    medio = (lo + hi) / 2.0
    if b <= a or not costos:
        return medio
    best = None
    x = a
    while x <= b + 1e-9:
        key = (round(sum(c(x) for c in costos), 1), abs(x - medio))
        if best is None or key < best[0]:
            best = (key, x)
        x += CORTE_PASO_PT
    return best[1]


def tinta(f, v):
    """Hasta dónde DIBUJA la hoja dentro de su vista (alcantarillado de Phoenix: la
    vista es ~25 pt más ancha que el mapa). El corte tiene que caer donde las DOS
    hojas tienen tinta; si no, queda una franja en blanco en la hoja compuesta."""
    xs = sorted(c for l in f.lineas for c in (l[0], l[2]))
    ys = sorted(c for l in f.lineas for c in (l[1], l[3]))
    if len(xs) < 50:
        return v
    k = int(len(xs) * TINTA_PERCENTIL)
    return (max(v[0], xs[k]), max(v[1], ys[k]), min(v[2], xs[-1 - k]), min(v[3], ys[-1 - k]))


def costuras_rectas(g, R: dict, fichas: Optional[dict] = None, T: Optional[dict] = None) -> dict:
    """Mapa: corte DENTRO del solape (de la TINTA `T` de cada hoja si se da; `R` son
    las vistas, que mandan en los bordes sin vecina), lejos de la tinta paralela a la
    costura. Si todas las parejas de una misma frontera (columna/fila de la rejilla) se
    solapan en una franja común, el corte es una recta común (sin escalones en las
    esquinas); si no, uno por pareja."""
    T = T or R
    pos = g.rejilla
    en = {p: n for n, p in pos.items()}
    lados: Dict[Nodo, Dict[str, float]] = {n: {"left": R[n][0], "top": R[n][1], "right": R[n][2], "bottom": R[n][3]}
                                           for n in g.nodos}
    for eje, (i0, i1, lado, op) in ((0, (2, 0, "right", "left")), (1, (3, 1, "bottom", "top"))):
        fronteras: Dict[int, List[Tuple[Nodo, Nodo]]] = defaultdict(list)
        for n, p in pos.items():
            q = (p[0] + 1, p[1]) if eje == 0 else (p[0], p[1] + 1)
            if q in en:
                fronteras[p[eje]].append((n, en[q]))
        for _k, pares in fronteras.items():
            lo = max(T[b][i1] for a, b in pares)
            hi = min(T[a][i0] for a, b in pares)
            def costo_de(a, b, lo_, hi_):
                if not fichas:
                    return []
                A_ = _franja(g, fichas, a, eje, lo_, hi_)
                B_ = _franja(g, fichas, b, eje, lo_, hi_)
                return [_costo_corte(A_, _gemelos(A_, B_), B_, _gemelos(B_, A_))]
            comun = None
            if hi > lo:
                comun = _mejor_corte(lo, hi, [c for a, b in pares for c in costo_de(a, b, lo, hi)])
            for a, b in pares:
                if comun is not None:
                    corte = comun
                else:
                    lo2, hi2 = T[b][i1], T[a][i0]
                    corte = _mejor_corte(lo2, hi2, costo_de(a, b, lo2, hi2))
                lados[a][lado] = corte
                lados[b][op] = corte
    return {n: (d["left"], d["top"], d["right"], d["bottom"]) for n, d in lados.items()}
