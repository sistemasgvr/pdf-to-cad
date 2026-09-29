"""Tinta REPETIDA con desfase: la misma línea dibujada dos veces en la misma capa. PURO.

DU06 h.4 (reporte del usuario 2026-09-29, «la línea está doble… es una sola línea por
cada utilidad»): el banco de ductos `N-COMM-DUCT-BANK-PL` trae el mismo recorrido DOS
veces (dos entidades del xref superpuestas), cada una con su linetype «—TE—» empezado en
otro punto: los guiones de una caen sobre los huecos y las letras de la otra.
`recognition.dedup_paths` solo quita trazos IDÉNTICOS; estos se solapan en parte, y el
núcleo armaba dos polilíneas encimadas (vertical + codo + diagonal dos veces, con T y
empalmes entre ellas que el plano no tiene).

En un linetype normal dos trazos de la misma capa NUNCA corren uno encima del otro (los
guiones van separados por huecos). Un tramo de trazo que corre SOBRE otro trazo de la
capa (≤ `DUP_INK_TOL_PT`, mismo rumbo, ≥ `DUP_INK_MIN_OVERLAP_PT` de largo) es tinta
repetida: se recorta de los trazos más cortos lo que ya dibuja uno más largo, y lo que
queda —lo que la otra copia pone en los huecos— sigue como trazo propio. No se pierde
nada que se vea ni se agrega nada. Auditoría de los 4 PDFs: DU06 h.4/h.5/h.11 (banco de
ductos), LABOE h.5 (telecom propuesta), el borde del cajetín de DU10 en capas de
utilidad y solapes chicos (2–70 pt) en eléctrico, agua, alcantarillado y gas.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

Pt = Tuple[float, float]

DUP_INK_TOL_PT = 0.25          # dos trazos a ≤ esto uno del otro = la misma tinta (cuantización 0.06)
DUP_INK_MIN_OVERLAP_PT = 2.0   # solape mínimo a lo largo (dos guiones que solo se tocan no cuentan)
DUP_INK_PAR_DEG = 1.5          # rumbo: un guión recto es colineal con el de la otra copia (±1° en el núcleo)
DUP_INK_ARC_CHORD_PT = 6.0     # cuerdas más cortas son de un ARCO aplanado: las de la otra copia caen en
DUP_INK_ARC_PAR_DEG = 10.0     # otra fase y giran unos grados (r=18 pt: 6° por cuerda)
DUP_INK_MIN_PIECE_PT = 0.75    # un resto más corto que esto no es tinta que se vea
DUP_INK_REMNANT_PT = 3.0       # un resto corto con sus dos puntas SOBRE la tinta conservada…
DUP_INK_REMNANT_TOL_PT = 0.5   # …(a ≤ esto) es la misma curva con otro aplanado: se quita


def _xy(q) -> Pt:
    return (float(q.x), float(q.y)) if hasattr(q, "x") else (float(q[0]), float(q[1]))


def _chains(path: dict):
    """Cadenas de puntos de un path SOLO de rectas ('l'); None si trae otra cosa
    (curvas Bézier, rectángulos: letras y símbolos, no se tocan)."""
    chains: List[List[Pt]] = []
    cur: List[Pt] = []
    for it in path.get("items") or []:
        if it[0] != "l":
            return None
        p1, p2 = _xy(it[1]), _xy(it[2])
        if not cur or math.dist(cur[-1], p1) > 1e-6:
            if len(cur) >= 2:
                chains.append(cur)
            cur = [p1]
        cur.append(p2)
    if len(cur) >= 2:
        chains.append(cur)
    return chains


def _seg_dist(q: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


class _Grid:
    def __init__(self, cell: float = 8.0):
        self.c = cell
        self.g: Dict[Tuple[int, int], List[Tuple[Pt, Pt]]] = {}

    def _cells(self, a: Pt, b: Pt, pad: float = 0.0):
        c = self.c
        for gx in range(int((min(a[0], b[0]) - pad) // c), int((max(a[0], b[0]) + pad) // c) + 1):
            for gy in range(int((min(a[1], b[1]) - pad) // c), int((max(a[1], b[1]) + pad) // c) + 1):
                yield gx, gy

    def add(self, a: Pt, b: Pt, sign: int = 0) -> None:
        for key in self._cells(a, b):
            self.g.setdefault(key, []).append((a, b, sign))

    def near(self, a: Pt, b: Pt, pad: float) -> List[Tuple[Pt, Pt, int]]:
        seen, out = set(), []
        for key in self._cells(a, b, pad):
            for s in self.g.get(key, ()):
                if id(s) not in seen:
                    seen.add(id(s)); out.append(s)
        return out


def _turn_signs(chain: List[Pt]) -> List[int]:
    """Hacia dónde gira la cadena en cada cuerda (+1/−1; 0 = recto): el giro con la
    cuerda siguiente (la última, con la anterior)."""
    n = len(chain) - 1
    out = []
    for k in range(n):
        j = k + 1 if k + 1 < n else k - 1
        if j < 0:
            out.append(0)
            continue
        i0, i1 = min(k, j), max(k, j)
        ux, uy = chain[i0 + 1][0] - chain[i0][0], chain[i0 + 1][1] - chain[i0][1]
        vx, vy = chain[i1 + 1][0] - chain[i1][0], chain[i1 + 1][1] - chain[i1][1]
        ang = math.degrees(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))
        out.append(0 if abs(ang) < 0.1 else (1 if ang > 0 else -1))
    return out


def _covered(a: Pt, b: Pt, kept: _Grid, sign: int = 0) -> List[Tuple[float, float]]:
    """Intervalos [t0, t1] (largo sobre a→b) que ya dibuja la tinta conservada:
    un segmento conservado paralelo (±DUP_INK_PAR_DEG; en cuerdas cortas de arco,
    ±DUP_INK_ARC_PAR_DEG, y girando hacia el mismo lado) cuyo solape con a→b va
    entero a ≤ DUP_INK_TOL_PT."""
    L = math.dist(a, b)
    if L < 1e-9:
        return []
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    arc = L < DUP_INK_ARC_CHORD_PT
    par = math.sin(math.radians(DUP_INK_ARC_PAR_DEG if arc else DUP_INK_PAR_DEG))
    out = []
    for c, d, sk in kept.near(a, b, DUP_INK_TOL_PT + 0.5):
        Lk = math.dist(c, d)
        if Lk < 1e-9:
            continue
        if arc != (Lk < DUP_INK_ARC_CHORD_PT):
            # cuerda de ARCO sobre un guión RECTO (o al revés): es la curva que llega
            # TANGENTE a otra línea (a r=126 pt queda a <0.25 pt de ella los últimos
            # 8 pt: DU08 h.26), no la misma curva dibujada dos veces
            continue
        if arc and sign and sk and sign * sk * ((d[0] - c[0]) * ux + (d[1] - c[1]) * uy) < 0:
            # dos curvas que nacen TANGENTES y giran a lados opuestos (una «Y» de
            # curvas: sus primeras cuerdas van ~3 pt a <0.25 pt, DU10 h.5): no es la
            # misma curva. El signo se compara en el MISMO sentido de avance.
            continue
        if abs((d[0] - c[0]) * uy - (d[1] - c[1]) * ux) > par * Lk:
            continue
        tc = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
        td = (d[0] - a[0]) * ux + (d[1] - a[1]) * uy
        t0, t1 = max(0.0, min(tc, td)), min(L, max(tc, td))
        if t1 - t0 < 1e-6:
            continue
        p0 = (a[0] + ux * t0, a[1] + uy * t0)
        p1 = (a[0] + ux * t1, a[1] + uy * t1)
        if _seg_dist(p0, c, d) <= DUP_INK_TOL_PT and _seg_dist(p1, c, d) <= DUP_INK_TOL_PT:
            out.append((t0, t1))
    return out


def _cut_chain(chain: List[Pt], kept: _Grid) -> List[List[Pt]]:
    """Trozos de la cadena que NO dibuja ya la tinta conservada."""
    # intervalos cubiertos sobre el largo acumulado de la cadena
    S = [0.0]
    for a, b in zip(chain, chain[1:]):
        S.append(S[-1] + math.dist(a, b))
    cov = []
    signs = _turn_signs(chain)
    for k, (a, b) in enumerate(zip(chain, chain[1:])):
        cov += [(S[k] + t0, S[k] + t1) for t0, t1 in _covered(a, b, kept, signs[k])]
    if not cov:
        return [chain]
    cov.sort()
    merged = [list(cov[0])]
    for t0, t1 in cov[1:]:
        if t0 <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], t1)
        else:
            merged.append([t0, t1])
    merged = [(t0, t1) for t0, t1 in merged if t1 - t0 >= DUP_INK_MIN_OVERLAP_PT]
    if not merged:
        return [chain]
    free, s = [], 0.0
    for t0, t1 in merged:
        if t0 > s:
            free.append((s, t0))
        s = max(s, t1)
    if s < S[-1]:
        free.append((s, S[-1]))

    def at(t):
        k = max(0, min(len(S) - 2, next((i for i in range(len(S) - 1) if S[i + 1] >= t), len(S) - 2)))
        a, b = chain[k], chain[k + 1]
        L = S[k + 1] - S[k]
        f = 0.0 if L < 1e-12 else (t - S[k]) / L
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), k

    pieces = []
    for t0, t1 in free:
        if t1 - t0 < DUP_INK_MIN_PIECE_PT:
            continue
        p0, k0 = at(t0)
        p1, k1 = at(t1)
        pieces.append([p0] + [chain[i] for i in range(k0 + 1, k1 + 1) if S[i] > t0 + 1e-6 and S[i] < t1 - 1e-6] + [p1])
    return pieces


def _on_kept(q: Pt, kept: _Grid) -> bool:
    return any(_seg_dist(q, c, d) <= DUP_INK_REMNANT_TOL_PT for c, d, _s in kept.near(q, q, DUP_INK_REMNANT_TOL_PT + 0.5))


def trim_repeated_ink(paths: Sequence[dict], make_rect=None) -> Tuple[List[dict], int]:
    """Paths de UNA capa con la tinta repetida recortada. Los trazos más largos se
    conservan enteros; de cada uno de los demás se quita lo que corre sobre la tinta
    ya conservada. Devuelve (paths, nº de trazos recortados o quitados). `make_rect`
    arma el `rect` de un path nuevo a partir de (x0, y0, x1, y1)."""
    info = []
    for i, p in enumerate(paths):
        ch = _chains(p) if not p.get("fill") else None
        if ch and (p.get("closePath") or any(len(c) >= 4 and math.dist(c[0], c[-1]) < 0.05 for c in ch)):
            ch = None          # figura CERRADA (caja, símbolo): no es una línea, ni se recorta ni
                               # recorta (DU08 h.40: una cajita de la capa «-D» dibujada dos veces)
        L = sum(math.dist(a, b) for c in (ch or []) for a, b in zip(c, c[1:]))
        info.append((i, ch, L))
    kept = _Grid()
    result: Dict[int, object] = {}
    n_trim = 0
    for i, ch, _L in sorted(info, key=lambda t: (-t[2], t[0])):
        path = paths[i]
        if not ch:
            result[i] = path
            continue
        new_chains, changed = [], False
        for c in ch:
            pieces = _cut_chain(c, kept)
            if pieces != [c]:
                changed = True
                pieces = [pc for pc in pieces
                          if not (sum(math.dist(a, b) for a, b in zip(pc, pc[1:])) < DUP_INK_REMNANT_PT
                                  and _on_kept(pc[0], kept) and _on_kept(pc[-1], kept))]
            new_chains += pieces
        for c in new_chains:
            for (a, b), s in zip(zip(c, c[1:]), _turn_signs(c)):
                kept.add(a, b, s)
        if not changed:
            result[i] = path
            continue
        n_trim += 1
        if not new_chains:
            result[i] = None
            continue
        q = dict(path)
        q["items"] = [("l", a, b) for c in new_chains for a, b in zip(c, c[1:])]
        xs = [pt[0] for c in new_chains for pt in c]
        ys = [pt[1] for c in new_chains for pt in c]
        if make_rect is not None:
            q["rect"] = make_rect(min(xs), min(ys), max(xs), max(ys))
        q["closePath"] = False
        result[i] = q
    return [result[i] for i in range(len(paths)) if result[i] is not None], n_trim
