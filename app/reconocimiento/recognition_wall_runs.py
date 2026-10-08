"""Paredes A TRAZOS y tapones de una tubería dibujada con sus dos paredes. PURO.

Complemento de `recognition_walls` (ET-004 h.1, 2026-10-02): la tubería existente sigue
con las dos paredes a trazos («oculta») y un tapón corto une las puntas de las dos
paredes donde cambia el dibujo.

  - `dash_runs`: guiones colineales (≤ `RUN_LAT_PT` de la misma recta, ±
    `RUN_PAR_DEG`, huecos ≤ `RUN_GAP_PT`, ≥ `RUN_MIN_DASHES`) forman UNA pared a trazos
    (un `_Stroke` recto con sus intervalos de tinta). Si en algún hueco hay tinta que
    cruza la recta, es una línea con letras, no una pared (`run_lettered`).
  - `run_axis_dashes`: el eje de dos paredes a trazos sale A TRAZOS, con la unión de
    los guiones de las dos (no se inventa tinta en los huecos ni cambia el patrón de
    guiones de la capa).
  - `caps`: trazo corto que une la punta de una pared con la de la otra (tapón).
  - `joint_leftovers`: en el quiebre de una pared a trazos el guión que DOBLA no es
    recto y no entra en ningún tramo; sale con las paredes y en su lugar va la esquina
    del eje (conector fin de un tramo → vértice → inicio del otro).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from reconocimiento.recognition_walls import WALL_MIN_LEN_PT, WALL_SEP_TOL_PT, _closest

Pt = Tuple[float, float]

RUN_LAT_PT = 0.3        # un guión está sobre la recta de la pared
RUN_PAR_DEG = 1.5
RUN_GAP_PT = 12.0       # hueco máx entre guiones de una pared a trazos
RUN_MIN_DASHES = 3
RUN_MIN_DASH_PT = 1.0   # menos: un punto/astilla, no un guión
RUN_OVERLAP_PT = 2.0    # dos guiones colineales que se pisan (dos copias de la pared con el
                        # linetype desfasado, ET-004 h.1: hasta 0.53 pt) son la misma tinta: se unen
RUN_STRAIGHT_PT = 0.2   # un guión con vértices intermedios cuenta si es recto
CAP_TOL_PT = 0.5        # el tapón toca las dos puntas


def _unit(a: Pt, b: Pt) -> Tuple[float, float, float]:
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L, L) if L > 1e-9 else (1.0, 0.0, 0.0)


def dash_runs(strokes, min_len: float, max_len: float, stroke_cls) -> list:
    """Paredes a trazos armadas con los guiones cortos (`min_len` ≤ … < `max_len`) de
    `strokes`. Devuelve `stroke_cls` rectos con `dashes` = intervalos de tinta."""
    def straight(pts):
        a, b = pts[0], pts[-1]
        ux, uy, L = _unit(a, b)
        return L > 0 and all(abs((q[0] - a[0]) * -uy + (q[1] - a[1]) * ux) <= RUN_STRAIGHT_PT for q in pts[1:-1])
    cand = [k for k, s in enumerate(strokes) if min_len <= s.L < max_len and straight(s.pts)]
    ends = {k: (strokes[k].pts[0], strokes[k].pts[-1]) for k in cand}
    cell = 20.0
    grid: Dict[Tuple[int, int], List[int]] = {}
    for k in cand:
        a, b = ends[k]
        grid.setdefault((int((a[0] + b[0]) / 2 // cell), int((a[1] + b[1]) / 2 // cell)), []).append(k)
    parent = {k: k for k in cand}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    sin_tol = math.sin(math.radians(RUN_PAR_DEG))
    for k in cand:
        a, b = ends[k]
        ux, uy, L = _unit(a, b)
        gx, gy = int((a[0] + b[0]) / 2 // cell), int((a[1] + b[1]) / 2 // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j <= k:
                        continue
                    c, d = ends[j]
                    vx, vy, _M = _unit(c, d)
                    if abs(ux * vy - uy * vx) > sin_tol:
                        continue
                    if any(abs((p[0] - a[0]) * -uy + (p[1] - a[1]) * ux) > RUN_LAT_PT for p in (c, d)):
                        continue
                    t = sorted(((c[0] - a[0]) * ux + (c[1] - a[1]) * uy, (d[0] - a[0]) * ux + (d[1] - a[1]) * uy))
                    gap = max(t[0] - L, -t[1])
                    if -RUN_OVERLAP_PT < gap <= RUN_GAP_PT:
                        parent[find(j)] = find(k)
    comps: Dict[int, List[int]] = {}
    for k in cand:
        comps.setdefault(find(k), []).append(k)
    out = []
    for ks in comps.values():
        if len(ks) < RUN_MIN_DASHES:
            continue
        # orden a lo largo (rumbo de un guión: basta para ordenar)
        a0, b0 = ends[ks[0]]
        ux, uy, _L = _unit(a0, b0)
        iv = []
        for k in ks:
            c, d = ends[k]
            tc = (c[0] - a0[0]) * ux + (c[1] - a0[1]) * uy
            td = (d[0] - a0[0]) * ux + (d[1] - a0[1]) * uy
            iv.append((min(tc, td), max(tc, td), k, c if tc <= td else d, d if tc <= td else c))
        iv.sort()
        reach = [iv[0][1]]
        for x in iv[1:]:
            reach.append(max(reach[-1], x[1]))
        if any(iv[i + 1][0] - reach[i] > RUN_GAP_PT for i in range(len(iv) - 1)):
            continue
        # Tramos RECTOS: la pared puede quebrarse (vértice de la tubería); se parte
        # donde un guión se sale ≥ RUN_LAT_PT de la recta del tramo. Las puntas son las
        # REALES del primer y último guión (el rumbo de un guión corto, extrapolado
        # 170 pt, ya se aparta ~1 pt de la pared).
        start = 0
        while start < len(iv):
            end = start
            for k in range(start + 1, len(iv)):
                p0, p1 = iv[start][3], iv[k][4]
                vx, vy, L = _unit(p0, p1)
                if any(abs((q[0] - p0[0]) * -vy + (q[1] - p0[1]) * vx) > RUN_LAT_PT
                       for x in iv[start:k + 1] for q in (x[3], x[4])):
                    break
                end = k
            piece = iv[start:end + 1]
            start = end + 1
            if len(piece) < RUN_MIN_DASHES:
                continue
            p0 = min(piece, key=lambda x: x[0])[3]
            p1 = max(piece, key=lambda x: x[1])[4]
            vx, vy, L = _unit(p0, p1)
            if L < max_len:
                continue
            dashes = []
            for x in piece:
                lo = (x[3][0] - p0[0]) * vx + (x[3][1] - p0[1]) * vy
                hi = (x[4][0] - p0[0]) * vx + (x[4][1] - p0[1]) * vy
                if dashes and lo <= dashes[-1][1] + 0.05:
                    dashes[-1] = (dashes[-1][0], max(dashes[-1][1], hi))
                else:
                    dashes.append((lo, hi))
            run = stroke_cls([p0, p1], [part for x in piece for part in strokes[x[2]].parts])
            run.dashes = dashes
            out.append(run)
    return out


def run_lettered(run, skip: set, ink, letter_in_gap) -> bool:
    """¿Hay tinta que cruza la recta en algún hueco ENTRE los guiones de la pared?"""
    (a, b) = run.pts
    ux, uy, _L = _unit(a, b)
    for (s0, e0), (s1, _e1) in zip(run.dashes, run.dashes[1:]):
        end = (a[0] + ux * e0, a[1] + uy * e0)
        if letter_in_gap(end, (ux, uy), 0.0, s1 - e0, ink, skip):
            return True
    return False


def run_axis_dashes(a, b, line: Sequence[Pt]) -> List[List[Pt]]:
    """Guiones del eje: unión de los guiones de las dos paredes, sobre la recta del eje."""
    m0, m1 = line[0], line[-1]
    ux, uy, Lm = _unit(m0, m1)
    iv = []
    for run in (a, b):
        p0, p1 = run.pts
        vx, vy, _L = _unit(p0, p1)
        for s, e in run.dashes:
            for t in ((s, e),):
                q0 = (p0[0] + vx * t[0], p0[1] + vy * t[0])
                q1 = (p0[0] + vx * t[1], p0[1] + vy * t[1])
                r = sorted(((q0[0] - m0[0]) * ux + (q0[1] - m0[1]) * uy, (q1[0] - m0[0]) * ux + (q1[1] - m0[1]) * uy))
                lo, hi = max(0.0, r[0]), min(Lm, r[1])
                if hi - lo > 0.05:
                    iv.append([lo, hi])
    iv.sort()
    merged: List[List[float]] = []
    for lo, hi in iv:
        if merged and lo <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [[(m0[0] + ux * lo, m0[1] + uy * lo), (m0[0] + ux * hi, m0[1] + uy * hi)] for lo, hi in merged]


def caps(strokes, a, b, pairs, sep: float, skip: set) -> set:
    """Índices de los trazos cortos que unen la punta de `a` con la de `b` (tapón)."""
    out = set()
    for k, s in enumerate(strokes):
        if k in skip or len(s.pts) != 2 or s.L > 1.6 * sep + 1.0:
            continue
        p, q = s.pts
        for pa, pb, _cut in pairs:
            if (math.dist(p, pa) <= CAP_TOL_PT and math.dist(q, pb) <= CAP_TOL_PT) or \
                    (math.dist(q, pa) <= CAP_TOL_PT and math.dist(p, pb) <= CAP_TOL_PT):
                out.add(k)
    return out


def _extend(line: Sequence[Pt], e0: float, e1: float) -> List[Pt]:
    """La polilínea prolongada `e0` antes de su inicio y `e1` después de su fin."""
    out = list(line)
    if e0 > 0:
        (ax, ay), (bx, by) = out[0], out[1]
        L = math.hypot(bx - ax, by - ay) or 1.0
        out[0] = (ax - (bx - ax) / L * e0, ay - (by - ay) / L * e0)
    if e1 > 0:
        (cx, cy), (dx, dy) = out[-2], out[-1]
        L = math.hypot(dx - cx, dy - cy) or 1.0
        out[-1] = (dx + (dx - cx) / L * e1, dy + (dy - cy) / L * e1)
    return out


def _line_cross(p: Pt, u: Pt, q: Pt, v: Pt) -> Optional[Pt]:
    den = u[0] * v[1] - u[1] * v[0]
    if abs(den) < math.sin(math.radians(1.0)):
        return None
    t = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / den
    return (p[0] + u[0] * t, p[1] + u[1] * t)


WALL_JOINT_MIN_TURN_DEG = 2.0   # unión con quiebre real (de frente la une el núcleo)
WALL_JOINT_MAX_TURN_DEG = 100.0  # más cerrado es otra tubería que llega a la estructura («V»)


def _turn(a: Sequence[Pt], sa: int, b: Sequence[Pt], sb: int) -> float:
    """Giro (°) entre el tramo final de `a` (punta sa) y el de `b` (punta sb)."""
    p, p_in = (a[0], a[1]) if sa == 0 else (a[-1], a[-2])
    q, q_in = (b[0], b[1]) if sb == 0 else (b[-1], b[-2])
    u = (p[0] - p_in[0], p[1] - p_in[1]); v = (q_in[0] - q[0], q_in[1] - q[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-9 or nv < 1e-9:
        return 0.0
    c = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(c))


def joint_leftovers(strokes, drop: set, changes: List[dict]):
    """Uniones de dos tramos de pared (el guión que DOBLA en el vértice de una pared
    a trazos no es recto y no entra en ningún tramo). Los guiones sueltos que caen
    enteros en la banda de las paredes, prolongadas hasta la unión, salen con ellas,
    y en su lugar va la esquina del eje: fin de un tramo → cruce de los dos ejes →
    inicio del otro (sin ese conector el núcleo ya no une los dos tramos). Solo en
    uniones con esa tinta: una línea que sigue de frente tras un buzón no se toca.
    Devuelve (trazos que salen, conectores)."""
    mids = [(c["mid"], c["sep"]) for c in changes if c["kind"] == "walls" and c.get("dashed")]
    joints = []                              # (i, lado i, j, lado j, D)
    for i, (line, sep) in enumerate(mids):
        for j in range(i + 1, len(mids)):
            other, s2 = mids[j]
            D = WALL_MIN_LEN_PT + 2 * 12.0 + 4.0 * max(sep, s2)   # un guión que dobla + dos huecos
            # solo las DOS puntas más cercanas (un tramo corto tiene las dos a tiro)
            d, si, sj = min((math.dist(p, q), si, sj) for si, p in ((0, line[0]), (1, line[-1]))
                            for sj, q in ((0, other[0]), (1, other[-1])))
            if d <= D and WALL_JOINT_MIN_TURN_DEG <= _turn(line, si, other, sj) <= WALL_JOINT_MAX_TURN_DEG:
                joints.append((i, si, j, sj, D))
    out: set = set()
    connectors = []
    for i, si, j, sj, D in joints:
        li, lj = mids[i][0], mids[j][0]
        bi = _extend(li, D if si == 0 else 0.0, D if si == 1 else 0.0)
        bj = _extend(lj, D if sj == 0 else 0.0, D if sj == 1 else 0.0)
        lim_i, lim_j = mids[i][1] / 2.0 + WALL_SEP_TOL_PT, mids[j][1] / 2.0 + WALL_SEP_TOL_PT
        p, p_in = (li[0], li[1]) if si == 0 else (li[-1], li[-2])
        q, q_in = (lj[0], lj[1]) if sj == 0 else (lj[-1], lj[-2])
        # el guión que DOBLA: entero en la banda y tocando la de los dos tramos
        bent = [k for k, st in enumerate(strokes)
                if k not in drop and st.dashes is None and st.L < WALL_MIN_LEN_PT
                and all(min(math.dist(x, p), math.dist(x, q)) <= D for x in st.pts)
                and all(min(_closest(x, bi)[0] - lim_i, _closest(x, bj)[0] - lim_j) <= 0 for x in st.pts)
                and any(_closest(x, bi)[0] <= lim_i for x in st.pts)
                and any(_closest(x, bj)[0] <= lim_j for x in st.pts)]
        if not bent:
            continue                         # sin tinta que doble en la unión: no se agrega nada
        out |= set(bent)
        L1, L2 = math.dist(p_in, p), math.dist(q_in, q)
        u = ((p[0] - p_in[0]) / L1, (p[1] - p_in[1]) / L1)
        v = ((q[0] - q_in[0]) / L2, (q[1] - q_in[1]) / L2)
        x = _line_cross(p, u, q, v)
        # el vértice va ADELANTE de las dos puntas (las paredes siguen hasta él)
        if x is not None and math.dist(x, p) <= D and math.dist(x, q) <= D and                 (x[0] - p[0]) * u[0] + (x[1] - p[1]) * u[1] >= -0.5 and                 (x[0] - q[0]) * v[0] + (x[1] - q[1]) * v[1] >= -0.5:
            connectors.append([p, x, q])
    return out, connectors
