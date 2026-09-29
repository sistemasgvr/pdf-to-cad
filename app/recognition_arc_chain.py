"""Curvas ENCADENADAS y codos que no cubren su tinta. PURO (sin Qt ni fitz).

Reporte del usuario 2026-09-29 (DU06 h.4):
- Curva en «S» sin recta entre medio (telecom `-E`: derecha → izquierda → derecha, la
  del medio compartida con la línea `-D`): cada arco del plano es tangente al SIGUIENTE,
  no a una recta de tinta. La 2.ª pasada solo aceptaba rectas de tinta a los lados y la
  curva quedaba en cuerdas. Aquí: `common_tangent` = la recta tangente interior a los
  dos círculos seguidos que giran al revés (curva inversa), que hace de recta del codo
  a cada lado. Dos arcos seguidos del mismo giro se juntan si un círculo los ajusta
  (`merge_same_circle`).
- Curva abierta de drenaje (r≈145 pt) reconocida hasta la mitad: la 1.ª pasada tomó
  por «recta» una cuerda que está DENTRO de la curva y el resto quedó en quiebres. La
  2.ª pasada la daba por dibujada porque su tinta está sobre el círculo del codo, sin
  mirar hasta DÓNDE llega el arco. Aquí: `explains` exige la tinta DENTRO del arco
  (A→B) y `overshoot` mide cuánta tinta curva sigue sobre el círculo después de una
  tangencia (si se aparta de la recta más que la tolerancia, el codo está corto).
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

ON_CIRCLE_PT = 1.5          # tinta de un codo: a ≤ esto de su círculo (= `_explained` de siempre)
SHORT_DEV_PT = 0.75         # = INK_FIT_MAX_PT: tinta curva que sigue después de la tangencia y se
                            # aparta de la recta más que esto → el codo no llega hasta donde llega el arco
TANGENT_OVERLAP_PT = 1.0    # dos círculos de una curva inversa que se solapan hasta esto (ruido del
                            # ajuste) se toman como tangentes entre sí
MERGE_RMS_PT = 0.08         # dos grupos seguidos del mismo giro son UN arco si un círculo les ajusta así
                            # (trozos del mismo arco: ~0.05; dos arcos de r 313 y 286 dan 0.12 y el
                            # círculo común ya no es tangente a sus rectas: DU08 h.25)
MERGE_MAX_PT = 0.5          # …ningún punto se aparta más que esto
MERGE_GAP_PT = 60.0         # …a lo sumo esto entre uno y otro (= ARC_GROUP_GAP_PT: letras «ss» y huecos)
MERGE_R_RATIO = 1.5         # …y el radio de CADA grupo coherente con el del círculo común (÷/× 1.5): dos
                            # codos chicos (r≈14.5) a 63 pt, uno a cada lado de una bóveda, caben en un
                            # círculo de r=126 con 0.5 pt (DU10 h.9, «—SC—») y no son un arco; los
                            # trozos de una curva de r=400–900 pt entre letras sí (alcantarillado DU08)


def _wrap(a: float) -> float:
    return (a + 3.0 * math.pi) % (2.0 * math.pi) - math.pi


def arc_params(ctr: Pt, A: Pt, B: Pt):
    """(ángulo de A, giro con signo A→B por el camino corto) de un codo."""
    a0 = math.atan2(A[1] - ctr[1], A[0] - ctr[0])
    return a0, _wrap(math.atan2(B[1] - ctr[1], B[0] - ctr[0]) - a0)


def _progress(q: Pt, ctr: Pt, a0: float, sweep: float) -> float:
    """Ángulo de q medido desde A en el sentido del arco (rad; <0 antes de A)."""
    t = _wrap(math.atan2(q[1] - ctr[1], q[0] - ctr[0]) - a0)
    return t if sweep >= 0 else -t


def explains(pts: Sequence[Pt], ctr: Pt, r: float, A: Pt, B: Pt, f: float = 1.0) -> bool:
    """¿El arco A→B dibuja esta tinta? ≥ la mitad de los puntos sobre su círculo Y
    dentro del arco (con un margen de ON_CIRCLE_PT a cada lado)."""
    if not pts or r <= 1e-9:
        return False
    a0, sw = arc_params(ctr, A, B)
    m = ON_CIRCLE_PT * f / r
    hit = 0
    for q in pts:
        if abs(math.dist(q, ctr) - r) > ON_CIRCLE_PT * f:
            continue
        t = _progress(q, ctr, a0, sw)
        if -m <= t <= abs(sw) + m:
            hit += 1
    return hit >= 0.5 * len(pts)


def overshoot(pts: Sequence[Pt], ctr: Pt, r: float, A: Pt, B: Pt, f: float = 1.0) -> float:
    """Separación máxima (px) de la recta tangente de la tinta que sigue SOBRE el
    círculo del codo antes de A o después de B: r·(1 − cos θ) con θ lo que se pasa.
    0 si la tinta queda dentro del arco o no está sobre su círculo."""
    if not pts or r <= 1e-9:
        return 0.0
    on = [q for q in pts if abs(math.dist(q, ctr) - r) <= ON_CIRCLE_PT * f]
    if len(on) < 0.5 * len(pts):
        return 0.0
    a0, sw = arc_params(ctr, A, B)
    worst = 0.0
    for q in on:
        t = _progress(q, ctr, a0, sw)
        over = -t if t < 0 else (t - abs(sw) if t > abs(sw) else 0.0)
        if over > 0:
            worst = max(worst, r * (1.0 - math.cos(min(over, math.pi / 2))))
    return worst


STRAIGHT_NEAR_PT = 2.5      # tinta recta de ESTA línea: a ≤ esto del círculo (= corredor de tinta)
STRAIGHT_MIN_LEN_PT = 8.0   # guión recto que cuenta: no el brazo de una letra del linetype («E» de
                            # 4.5 pt junto a la línea, DU10 h.21; las letras miden ≤7.2 pt)


def _along(q: Pt, pts: Sequence[Pt]):
    """(distancia de q a la polilínea, dirección unitaria del tramo más cercano)."""
    best = (1e18, (0.0, 0.0))
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        if L2 < 1e-12:
            continue
        t = max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        d = math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)
        if d < best[0]:
            L = math.sqrt(L2)
            best = (d, (vx / L, vy / L))
    return best


def straight_off_arc(straights, ctr: Pt, r: float, A: Pt, B: Pt, pts: Sequence[Pt], f: float = 1.0) -> bool:
    """¿Hay tinta RECTA de ESTA línea (sobre la polilínea `pts` a ≤1 pt y con su
    rumbo ±10°) dentro del arco A→B que se aparta del círculo más que SHORT_DEV_PT?
    (≥2 muestras). Entonces el arco pasa por encima de una recta del plano: DU10 h.10,
    la «Y» de curvas eléctricas que baja a una vertical — el arco se comía los 13 pt
    de vertical y salía de 103° en vez de 90°. Misma regla que la 2.ª pasada
    (`_straight_off_arc`), para los codos de la 1.ª. La tinta de OTRA línea no cuenta
    (la principal que sigue de largo en el tee donde nace un ramal curvo: DU08 h.23)."""
    if r <= 1e-9:
        return False
    a0, sw = arc_params(ctr, A, B)
    m = ON_CIRCLE_PT * f / r
    cos_par = math.cos(math.radians(10.0))
    bad = 0
    for a, b in straights:
        L = math.dist(a, b)
        if L < STRAIGHT_MIN_LEN_PT * f:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        for k in range(9):
            q = (a[0] + (b[0] - a[0]) * k / 8, a[1] + (b[1] - a[1]) * k / 8)
            dev = abs(math.dist(q, ctr) - r)
            if dev > STRAIGHT_NEAR_PT * f or dev <= SHORT_DEV_PT * f:
                continue
            t = _progress(q, ctr, a0, sw)
            if not (m < t < abs(sw) - m):
                continue
            d, (sx, sy) = _along(q, pts)
            if d <= 1.0 * f and abs(ux * sx + uy * sy) >= cos_par:
                bad += 1
    return bad >= 2


def is_short(entry, groups, f: float = 1.0) -> bool:
    """¿El codo `entry` (plan de `fit_fillets`) se queda corto frente a la tinta
    curva de su propio círculo? (la tinta sigue curvando pasada una tangencia)."""
    ctr, r, A, B = entry[5], entry[6], entry[3], entry[4]
    return any(overshoot(g.pts, ctr, r, A, B, f) > SHORT_DEV_PT * f for g in groups)


def groups_on(entry, groups, f: float = 1.0) -> list:
    """Grupos de tinta que están sobre el círculo de un codo (≥ la mitad de sus puntos)."""
    ctr, r = entry[5], entry[6]
    return [g for g in groups
            if sum(1 for q in g.pts if abs(math.dist(q, ctr) - r) <= ON_CIRCLE_PT * f) >= 0.5 * len(g.pts)]


def entry_explains(entry, g, f: float = 1.0) -> bool:
    return explains(g.pts, entry[5], entry[6], entry[3], entry[4], f)


def merge_same_circle(groups: list, circle_fit, make_group, f: float = 1.0) -> list:
    """Grupos SEGUIDOS (a ≤ MERGE_GAP_PT) del mismo giro que un solo círculo ajusta
    (RMS ≤ MERGE_RMS_PT, máx. ≤ MERGE_MAX_PT) con un radio coherente con el de cada
    uno (MERGE_R_RATIO) son un solo arco: el agrupador exige 0.1 pt (trozos del mismo
    aplanado) y un tramo corto junto a una inflexión o una letra sale con otro radio
    (r 33.7 dentro de un arco de 45.8). `make_group(pts, chords, s0, s1, n)` arma el
    grupo nuevo."""
    out: list = []
    for g in groups:
        if out and out[-1].sign == g.sign and g.s0 - out[-1].s1 <= MERGE_GAP_PT * f:
            h = out[-1]
            fit = circle_fit(h.pts + g.pts)
            if (fit is not None and fit[3] <= MERGE_RMS_PT * f and fit[4] <= MERGE_MAX_PT * f
                    and all(1.0 / MERGE_R_RATIO <= x.r / fit[2] <= MERGE_R_RATIO for x in (h, g))):
                merged = make_group(h.pts + g.pts, h.chords + g.chords, h.s0, max(h.s1, g.s1),
                                    h.n_pieces + g.n_pieces)
                if merged is not None:
                    out[-1] = merged
                    continue
        out.append(g)
    return out


def common_tangent(h, g, f: float = 1.0) -> Optional[Tuple[Pt, Pt, Pt]]:
    """Recta tangente a los círculos de dos arcos SEGUIDOS (h antes que g) que giran
    al REVÉS (curva inversa, la «S»: tangente interior), en el sentido de avance:
    (u, Th, Tg) = dirección y puntos de tangencia en cada círculo, o None. Con n =
    normal izquierda de u, el centro de un arco que gira a la izquierda (signo +) está
    en T + r·n: n·(cg − ch) = sg·rg − sh·rh.
    Dos arcos seguidos del MISMO giro no: si un círculo los ajusta ya son uno
    (`merge_same_circle`); si no, casi siempre uno de los dos es la punta de una recta
    que el aplanado mezcló con la primera cuerda del arco (DU06 h.4, `-D`: «r=71» =
    fin de la vertical + inicio del arco de r=45) y la tangente común entre ellos
    inventaba una curva compuesta."""
    if h.sign == g.sign:
        return None
    ch, cg = (h.cx, h.cy), (g.cx, g.cy)
    Dx, Dy = cg[0] - ch[0], cg[1] - ch[1]
    m2 = Dx * Dx + Dy * Dy
    if m2 < 1e-12:
        return None
    m = math.sqrt(m2)
    k = g.sign * g.r - h.sign * h.r
    if abs(k) > m:
        if abs(k) - m > TANGENT_OVERLAP_PT * f:
            return None
        k = math.copysign(m, k)
    root = math.sqrt(max(0.0, m2 - k * k))
    # rumbo esperado: salida de h y entrada de g
    def arc_dir(grp, E):
        tx, ty = -(E[1] - grp.cy), E[0] - grp.cx
        L = math.hypot(tx, ty)
        tx, ty = (tx / L, ty / L) if L > 1e-12 else (0.0, 0.0)
        return (tx, ty) if grp.sign > 0 else (-tx, -ty)
    dh, dg = arc_dir(h, h.E1), arc_dir(g, g.E0)
    best = None
    for sgn in (1.0, -1.0):
        nx = (k * Dx - sgn * root * Dy) / m2
        ny = (k * Dy + sgn * root * Dx) / m2
        u = (ny, -nx)
        score = u[0] * (dh[0] + dg[0]) + u[1] * (dh[1] + dg[1])
        if best is None or score > best[0]:
            best = (score, u, (nx, ny))
    _s, u, (nx, ny) = best
    if _s <= 0:
        return None
    Th = (ch[0] - h.sign * h.r * nx, ch[1] - h.sign * h.r * ny)
    Tg = (cg[0] - g.sign * g.r * nx, cg[1] - g.sign * g.r * ny)
    return u, Th, Tg


NEIGH_MIN_ARC_PT = 3.0      # cada arco de una «S» tiene al menos esto de tinta curva (r·giro): un
                            # trocito de 1 pt (r≈3) junto a una marca del linetype no es una curva
                            # del plano y con la tangente común salía un «codo» de 0.3 pt (LABOE h.28)


def neighbours(groups: Sequence, straight_between, gap_max: float, ink_min: float, f: float = 1.0):
    """{id(grupo): (anterior, siguiente)} de arcos SEGUIDOS: sin tinta recta (≥ ink_min)
    entre el fin de uno y el inicio del otro, y a ≤ gap_max; los dos con al menos
    NEIGH_MIN_ARC_PT de arco."""
    order = sorted((g for g in groups if g.r * math.radians(g.sweep) >= NEIGH_MIN_ARC_PT * f),
                   key=lambda g: g.s0)
    out = {id(g): [None, None] for g in groups}
    for h, g in zip(order, order[1:]):
        if g.s0 - h.s1 > gap_max:
            continue
        lo, hi = sorted((h.s1, g.s0))
        if straight_between(lo, hi) >= ink_min:
            continue
        out[id(h)][1] = g
        out[id(g)][0] = h
    return out
