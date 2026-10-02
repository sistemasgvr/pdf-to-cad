"""Codos desde la TINTA: 2.ª pasada de `recognition.fit_fillets`. PURO (sin Qt ni fitz).

AutoCAD exporta cada arco del plano APLANADO en cuerdas cortas de flecha constante
(≈0.025 pt: la cuerda crece con √r — 1.3 pt en r=7 pt, 5.5 pt en r=150 pt, ~14 pt
en r=1000 pt) y cada recta como UN segmento. Medido en los 4 PDFs de prueba
(auditoría de curvas 2026-09-28). Por eso, en un trazo del PDF, una ristra de
cuerdas parecidas que giran poco y siempre al mismo lado es un trozo de ARCO, y
sus vértices están SOBRE el círculo (a la cuantización del PDF, 0.06 pt). Así se ve
la curva —cerrada o muy abierta, partida por letras y huecos del linetype— sin
depender de la centerline simplificada: una curva abierta suele quedar en 1–2
vértices `curve` con cuerdas de 50–300 pt, o solo en `bend`, y la 1.ª pasada no
la intenta.

La 1.ª pasada (ristras `curve` del núcleo) NO cambia: esta solo agrega codos donde
quedó tinta curva sin arco, con las mismas reglas de «no inventar»: el círculo se
ajusta a la tinta curva, tangente a RECTAS DE TINTA (el segmento recto del PDF que
llega al arco) o muriendo en un nodo / extremo / línea que pasa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import recognition_arc_chain as chain_mod

# El plan de codos (rectas, nodos, ajuste tangente, anclas) vive en
# `recognition_arc_plan.py`; este módulo solo LEE la tinta.

Pt = Tuple[float, float]

# ── trozos de arco en un trazo ──
ARC_TURN_MIN_DEG = 0.15      # giro por vértice: menos es ruido de la cuantización (0.06 pt)
ARC_TURN_MAX_DEG = 20.0      # más es esquina o letra (AutoCAD aplana con ≤ ~10°)
ARC_CHORD_RATIO = 1.6        # cuerdas vecinas del MISMO arco miden casi igual (flecha constante)
ARC_CHORD_MAX_PT = 30.0      # cuerda de un arco aplanado con r ≈ 4000 pt
ARC_PIECE_RMS_PT = 0.12      # los vértices del aplanado están sobre el círculo
ARC_PIECE_MIN_SWEEP_DEG = 0.3
ARC_R_MIN_PT = 2.0           # = el mínimo de la 1.ª pasada (r < 2·tol)
ARC_R_MAX_PT = 6000.0
GLYPH_PAD_PT = 0.3           # margen de la caja de una letra/marca del linetype
EDITOR_FIT_MAX_PT = 1.5      # exceso de tangencia que `fit_to_editor` absorbe ajustando el radio
# ── trozos de ESTA línea y su agrupación en arcos ──
ARC_CORRIDOR_PT = 2.5        # = FILLET_INK_CORRIDOR_PT: el trozo corre sobre la polilínea
ARC_ALIGN_DEG = 30.0         # …y con su rumbo (una letra del linetype la cruza)
ARC_GROUP_RMS_PT = 0.1       # trozos del MISMO arco (guiones separados por huecos/letras): el
ARC_GROUP_DEV_PT = 0.35      # aplanado es exacto, dos trozos del mismo arco coinciden a ~0.02 pt
ARC_GROUP_GAP_PT = 60.0      # hueco máximo entre trozos del mismo arco (letra + hueco del linetype)
ARC_GROUP_MIN_PTS = 4        # 3 puntos siempre caben en un círculo: no prueban nada
# ── rectas de tinta ──
STRAIGHT_MIN_PT = 1.5        # segmento de tinta RECTA (fuera de todo trozo de arco)


def _turn_deg(a: Pt, b: Pt, c: Pt) -> float:
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    return math.degrees(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))


def _unit(dx: float, dy: float) -> Pt:
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else (0.0, 0.0)


def _seg_dist(q: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


def circle_fit(pts: Sequence[Pt]):
    """Kåsa: (cx, cy, r, rms, desvío máx.) o None."""
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    u = [p[0] - mx for p in pts]; v = [p[1] - my for p in pts]
    suu = sum(a * a for a in u); svv = sum(b * b for b in v); suv = sum(a * b for a, b in zip(u, v))
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None
    rx = 0.5 * (sum(a ** 3 for a in u) + sum(a * b * b for a, b in zip(u, v)))
    ry = 0.5 * (sum(b ** 3 for b in v) + sum(b * a * a for a, b in zip(u, v)))
    cx = (rx * svv - ry * suv) / det + mx
    cy = (ry * suu - rx * suv) / det + my
    d = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    r = sum(d) / n
    dev = [abs(x - r) for x in d]
    return cx, cy, r, math.sqrt(sum(x * x for x in dev) / n), max(dev)


def _sweep_deg(pts: Sequence[Pt], cx: float, cy: float) -> float:
    """Giro con signo recorriendo `pts` alrededor del centro (suma de pasos)."""
    tot = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.atan2(b[1] - cy, b[0] - cx) - math.atan2(a[1] - cy, a[0] - cx)
        tot += (d + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
    return math.degrees(tot)


@dataclass
class ArcPiece:
    """Tramo de un trazo del PDF que es arco aplanado (vértices sobre el círculo)."""
    pts: List[Pt]
    cx: float
    cy: float
    r: float
    rms: float


@dataclass
class ArcGroup:
    """Un arco del plano en UNA polilínea: sus trozos de tinta (huecos y letras
    del linetype en medio), ordenados en el sentido de la polilínea."""
    pts: List[Pt]
    chords: List[Tuple[Pt, Pt]]
    cx: float
    cy: float
    r: float
    rms: float
    s0: float                 # parámetro (largo) sobre la polilínea del inicio y fin de la tinta
    s1: float
    sign: int                 # +1 gira a la izquierda (ángulo creciente), −1 a la derecha
    sweep: float              # giro de la tinta (°, positivo)
    n_pieces: int = 1

    @property
    def E0(self) -> Pt:
        return self.pts[0]

    @property
    def E1(self) -> Pt:
        return self.pts[-1]


def arc_pieces(strokes: Sequence[Sequence[Pt]], f: float = 1.0, glyph_boxes=()):
    """Trozos de arco y segmentos RECTOS de los trazos de una capa (px; `f` = px/pt).
    Una ristra es arco si cada vértice gira entre ARC_TURN_MIN/MAX_DEG, siempre al
    mismo lado, y las cuerdas vecinas miden casi igual (la primera/última del trazo
    puede ser más corta: el guión nace o muere sobre el arco). Una cuerda mucho más
    larga que las vecinas es RECTA (la tangente, o la recta entre dos curvas).
    `glyph_boxes` = cajas (x0, y0, x1, y1) de las letras y marcas del linetype que
    reconoció el núcleo: la panza de una «S», «e» o «G» también es un arco aplanado
    y corre pegada a la línea — no es curva del plano (DU06 h.4: un codo a través
    de «SS»)."""
    pieces: List[ArcPiece] = []
    masked_pieces: List[ArcPiece] = []
    straights: List[Tuple[Pt, Pt]] = []
    pad = GLYPH_PAD_PT * f
    boxes = [(b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad) for b in glyph_boxes]
    bgrid = _SegGrid(12.0 * f)
    for b in boxes:
        bgrid.add(b, (b[0], b[1]), (b[2], b[3]))

    def in_glyph(q):
        return any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in bgrid.near(q))
    for st in strokes:
        if not st:
            continue
        q = [tuple(st[0])]
        for p in st[1:]:
            if math.dist(p, q[-1]) > 1e-6:
                q.append(tuple(p))
        n = len(q)
        if n < 2:
            continue
        ch = [math.dist(q[k], q[k + 1]) for k in range(n - 1)]
        th = [_turn_deg(q[k - 1], q[k], q[k + 1]) for k in range(1, n - 1)]   # th[k] = giro en q[k+1]
        used = [False] * (n - 1)

        def compat(k: int) -> bool:
            """¿Las cuerdas k y k+1 son pasos del mismo arco aplanado?"""
            t = th[k]
            if not (ARC_TURN_MIN_DEG <= abs(t) <= ARC_TURN_MAX_DEG):
                return False
            a, b = ch[k], ch[k + 1]
            if max(a, b) > ARC_CHORD_MAX_PT * f:
                return False
            if max(a, b) <= ARC_CHORD_RATIO * min(a, b) + 0.1 * f:
                return True
            return (k == 0 and a <= b) or (k + 1 == n - 2 and b <= a)

        k = 0
        while k < n - 2:
            if not compat(k):
                k += 1
                continue
            left = th[k] > 0
            j = k
            while j + 1 < n - 2 and compat(j + 1) and (th[j + 1] > 0) == left:
                j += 1
            P = q[k:j + 3]
            fit = circle_fit(P)
            if fit is not None:
                cx, cy, r, rms, mx = fit
                if (ARC_R_MIN_PT * f <= r <= ARC_R_MAX_PT * f and rms <= ARC_PIECE_RMS_PT * f
                        and mx <= 2.5 * ARC_PIECE_RMS_PT * f
                        and abs(_sweep_deg(P, cx, cy)) >= ARC_PIECE_MIN_SWEEP_DEG):
                    piece = ArcPiece(list(P), cx, cy, r, rms)
                    if boxes and sum(in_glyph(p) for p in P) >= 0.5 * len(P):
                        masked_pieces.append(piece)
                    else:
                        pieces.append(piece)
                        for m in range(k, j + 2):
                            used[m] = True
            k = j + 1
        for m in range(n - 1):
            if not used[m] and ch[m] >= STRAIGHT_MIN_PT * f:
                straights.append((q[m], q[m + 1]))
    # A slash/text bounding box can cover real curve ink underneath it.
    # Recover that ink only when an unmasked neighbouring arc supports the
    # SAME circle. Never turn an isolated glyph into a curve or use the
    # recovered flattened chords as straight tangent legs.
    recovered = set()
    pending = list(masked_pieces)
    while pending:
        progress = False
        for pc in list(pending):
            if len(pc.pts) < 4:
                continue
            for seed in pieces:
                if len(seed.pts) < 4 or not (1/1.5 <= pc.r/seed.r <= 1.5):
                    continue
                if min(math.dist(a, b) for a in (pc.pts[0], pc.pts[-1])
                       for b in (seed.pts[0], seed.pts[-1])) > 12.0*f:
                    continue
                fit = circle_fit(pc.pts + seed.pts)
                if (fit is None or fit[3] > 0.08*f or fit[4] > 0.15*f
                        or not (1/1.2 <= fit[2]/seed.r <= 1.2)):
                    continue
                pieces.append(pc)
                recovered.update(zip(pc.pts, pc.pts[1:]))
                pending.remove(pc)
                progress = True
                break
        if not progress:
            break
    if recovered:
        straights = [(a, b) for a, b in straights if (a, b) not in recovered]
    return pieces, straights


def dash_arc_ends(pieces: Sequence[ArcPiece], f: float = 1.0) -> List[Tuple[Tuple[Pt, Pt], Tuple[Pt, Pt]]]:
    """«Trozos» de solo DOS cuerdas muy distintas → [(cuerda corta, cuerda larga)].
    Es un arco que nace o muere DENTRO de un guión recto: la cuerda corta es la
    primera/última cuerda del aplanado y la larga es la RECTA del guión. 3 puntos
    siempre caben en un círculo, así que el «trozo» no prueba ningún arco (DU10 h.3,
    codo r = 10.8 pt: 1.2 pt de arco + 7 pt de recta vertical). `arc_pieces` no
    cambia (también la usan los contactos): la 2.ª pasada de codos usa estos pares
    solo para ese arco (`ink_fillet_plan`, `arc_ends`)."""
    out = []
    for pc in pieces:
        if len(pc.pts) != 3:
            continue
        a, b, c = pc.pts
        l1, l2 = math.dist(a, b), math.dist(b, c)
        if max(l1, l2) <= ARC_CHORD_RATIO * min(l1, l2) + 0.1 * f or max(l1, l2) < STRAIGHT_MIN_PT * f:
            continue
        out.append(((b, c), (a, b)) if l1 > l2 else ((a, b), (b, c)))
    return out


class _SegGrid:
    def __init__(self, cell: float):
        self.cell = max(1e-6, cell)
        self.g: Dict[Tuple[int, int], list] = {}

    def add(self, item, a: Pt, b: Pt) -> None:
        c = self.cell
        for gx in range(int(min(a[0], b[0]) // c), int(max(a[0], b[0]) // c) + 1):
            for gy in range(int(min(a[1], b[1]) // c), int(max(a[1], b[1]) // c) + 1):
                self.g.setdefault((gx, gy), []).append(item)

    def near(self, q: Pt) -> list:
        c = self.cell
        cx, cy = int(q[0] // c), int(q[1] // c)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.extend(self.g.get((cx + dx, cy + dy), ()))
        return out


def assign_to_polylines(pieces: Sequence[ArcPiece], straights, polys: Sequence[Sequence[Pt]],
                        f: float = 1.0):
    """Reparte trozos de arco y rectas de tinta entre las polilíneas (px): cada uno a
    la que corre por encima (más puntos a ≤ corredor; empate: menor distancia)."""
    corridor = ARC_CORRIDOR_PT * f
    grid = _SegGrid(max(8.0 * f, 2 * corridor))
    for i, pl in enumerate(polys):
        for a, b in zip(pl, pl[1:]):
            grid.add((i, a, b), a, b)

    def best_poly(samples):
        score: Dict[int, List[float]] = {}
        for q in samples:
            dmin: Dict[int, float] = {}
            for i, a, b in grid.near(q):
                d = _seg_dist(q, a, b)
                if d <= corridor and d < dmin.get(i, 1e18):
                    dmin[i] = d
            for i, d in dmin.items():
                score.setdefault(i, []).append(d)
        if not score:
            return None
        return max(score, key=lambda i: (len(score[i]), -sum(score[i]) / len(score[i])))
    arcs_by = [[] for _ in polys]
    lines_by = [[] for _ in polys]
    for pc in pieces:
        P = pc.pts
        samp = [P[0], P[len(P) // 2], P[-1]] if len(P) > 3 else list(P)
        i = best_poly(samp)
        if i is not None:
            arcs_by[i].append(pc)
    for a, b in straights:
        i = best_poly([((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)])
        if i is not None:
            lines_by[i].append((a, b))
    return arcs_by, lines_by


def _cumlen(pts: Sequence[Pt]) -> List[float]:
    S = [0.0]
    for a, b in zip(pts, pts[1:]):
        S.append(S[-1] + math.dist(a, b))
    return S


def project(pts: Sequence[Pt], S: Sequence[float], q: Pt):
    """(parámetro s, distancia, índice del tramo) de q sobre la polilínea."""
    best = (0.0, 1e18, 0)
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        d = math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)
        if d < best[1]:
            best = (S[k] + t * math.sqrt(L2), d, k)
    return best


def group_arcs(pieces: Sequence[ArcPiece], pts: Sequence[Pt], f: float = 1.0) -> List[ArcGroup]:
    """Arcos de UNA polilínea: sus trozos de tinta en orden (sentido de la
    polilínea), los del mismo círculo juntos (guiones del linetype separados por
    huecos o letras). Un trozo que no corre SOBRE la polilínea y con su rumbo (asta
    o panza de una letra) no cuenta."""
    if len(pts) < 2 or not pieces:
        return []
    S = _cumlen(pts)
    corridor = ARC_CORRIDOR_PT * f
    items = []
    for pc in pieces:
        pr = [project(pts, S, q) for q in pc.pts]
        if max(p[1] for p in pr) > corridor:
            continue
        P = list(pc.pts)
        if pr[0][0] > pr[-1][0]:
            P.reverse(); pr.reverse()
        m = len(P) // 2
        tan = _unit(P[min(m + 1, len(P) - 1)][0] - P[max(m - 1, 0)][0],
                    P[min(m + 1, len(P) - 1)][1] - P[max(m - 1, 0)][1])
        k = pr[m][2]
        seg = _unit(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
        if tan[0] * seg[0] + tan[1] * seg[1] < math.cos(math.radians(ARC_ALIGN_DEG)):
            continue
        sw = _sweep_deg(P, pc.cx, pc.cy)
        items.append((pr[0][0], pr[-1][0], P, 1 if sw > 0 else -1))
    items.sort(key=lambda it: (it[0] + it[1]) / 2)
    groups: List[dict] = []
    for s0, s1, P, sg in items:
        g = groups[-1] if groups else None
        if g is not None and g["sign"] == sg and s0 - g["s1"] <= ARC_GROUP_GAP_PT * f:
            fit = circle_fit(g["pts"] + P)
            if (fit is not None and fit[3] <= ARC_GROUP_RMS_PT * f and fit[4] <= ARC_GROUP_DEV_PT * f):
                g["pts"] += P; g["chords"] += list(zip(P, P[1:])); g["s1"] = max(g["s1"], s1)
                g["n"] += 1
                continue
        groups.append({"pts": list(P), "chords": list(zip(P, P[1:])), "s0": s0, "s1": s1, "sign": sg, "n": 1})
    def make(P, chords, s0, s1, n):
        fit = circle_fit(P)
        if fit is None:
            return None
        cx, cy, r, rms, _mx = fit
        sw = _sweep_deg(P, cx, cy)
        return ArcGroup(P, chords, cx, cy, r, rms, s0, s1, 1 if sw > 0 else -1, abs(sw), n)
    out: List[ArcGroup] = []
    for g in groups:
        if len(g["pts"]) < ARC_GROUP_MIN_PTS:
            continue
        ag = make(g["pts"], g["chords"], g["s0"], g["s1"], g["n"])
        if ag is not None:
            out.append(ag)
    # dos grupos seguidos del mismo giro que un solo círculo ajusta son UN arco
    # (un tramo corto junto a una inflexión sale con otro radio: DU06 h.4)
    return chain_mod.merge_same_circle(out, circle_fit, make, f)


# ── ajustes de círculo (los usa el plan de codos) ──
def arc_cover(chords, ctr: Pt, r: float, a0: float, sweep: float, tol: float) -> float:
    """Fracción del arco (37 muestras) con tinta del arco a ≤ tol."""
    hit = 0
    for k in range(37):
        ang = a0 + sweep * k / 36
        q = (ctr[0] + r * math.cos(ang), ctr[1] + r * math.sin(ang))
        if any(_seg_dist(q, a, b) <= tol for a, b in chords):
            hit += 1
    return hit / 37


def fit_circle_two_nodes(members, Q0: Pt, Q1: Pt):
    """Círculo que PASA por los dos nodos y mejor ajusta la tinta (centro sobre la
    mediatriz, 1-D). (cx, cy, r, rms) o None."""
    mx, my = (Q0[0] + Q1[0]) / 2, (Q0[1] + Q1[1]) / 2
    nx, ny = _unit(-(Q1[1] - Q0[1]), Q1[0] - Q0[0])
    half = math.dist(Q0, Q1) / 2
    if half < 1e-9:
        return None

    def circ(t):
        cx, cy = mx + nx * t, my + ny * t
        return cx, cy, math.hypot(half, t)

    def cost(t):
        cx, cy, r = circ(t)
        return sum((math.hypot(q[0] - cx, q[1] - cy) - r) ** 2 for q in members)
    fit = circle_fit(members)
    t0 = ((fit[0] - mx) * nx + (fit[1] - my) * ny) if fit else 0.0
    span = max(4.0 * half, abs(t0) * 2 + half)
    lo, hi = t0 - span, t0 + span
    g = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = hi - g * (hi - lo); x2 = lo + g * (hi - lo)
    f1, f2 = cost(x1), cost(x2)
    for _ in range(80):
        if f1 > f2:
            lo, x1, f1 = x1, x2, f2; x2 = lo + g * (hi - lo); f2 = cost(x2)
        else:
            hi, x2, f2 = x2, x1, f1; x1 = hi - g * (hi - lo); f1 = cost(x1)
    t = (lo + hi) / 2
    cx, cy, r = circ(t)
    return cx, cy, r, math.sqrt(cost(t) / max(1, len(members)))


def fit_circle_line_node(members, P: Pt, u: Pt, Q: Pt, seed: Tuple[float, float, float]):
    """Círculo TANGENTE a la recta (P, u) —u hacia el arco— que PASA por el nodo Q y
    mejor ajusta la tinta. 1-D sobre el punto de tangencia t (a lo largo de u),
    buscado alrededor del de la tinta (`seed` = su círculo libre): en una curva
    abierta la tangencia cae lejos del nodo (DU10 h.18: 48 pt con r=125) y la
    búsqueda de la 1.ª pasada (≤ 4× la distancia del nodo a la recta) no llegaba.
    Devuelve (cx, cy, r, rms, A) o None."""
    nx, ny = -u[1], u[0]
    du = (Q[0] - P[0]) * u[0] + (Q[1] - P[1]) * u[1]
    dn = (Q[0] - P[0]) * nx + (Q[1] - P[1]) * ny
    if abs(dn) < 1e-6:
        return None

    def circle(t):
        r = ((t - du) ** 2 + dn * dn) / (2.0 * dn)       # que pase por Q
        return P[0] + u[0] * t + nx * r, P[1] + u[1] * t + ny * r, abs(r)

    def cost(t):
        cx, cy, r = circle(t)
        return sum((math.hypot(q[0] - cx, q[1] - cy) - r) ** 2 for q in members)
    t0 = (seed[0] - P[0]) * u[0] + (seed[1] - P[1]) * u[1]
    w = 0.5 * abs(du - t0) + 2.0
    lo, hi = t0 - w, min(t0 + w, du - 1e-3)
    if hi <= lo:
        return None
    g = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = hi - g * (hi - lo); x2 = lo + g * (hi - lo)
    f1, f2 = cost(x1), cost(x2)
    for _ in range(80):
        if f1 > f2:
            lo, x1, f1 = x1, x2, f2; x2 = lo + g * (hi - lo); f2 = cost(x2)
        else:
            hi, x2, f2 = x2, x1, f1; x1 = hi - g * (hi - lo); f1 = cost(x1)
    t = (lo + hi) / 2.0
    cx, cy, r = circle(t)
    if r < 1e-6:
        return None
    return cx, cy, r, math.sqrt(cost(t) / max(1, len(members))), (P[0] + u[0] * t, P[1] + u[1] * t)


def _tangent_at(Q: Pt, cx: float, cy: float) -> Pt:
    return _unit(-(Q[1] - cy), Q[0] - cx)


def fit_to_editor(pts, kinds, fillets, f: float = 1.0):
    """Cada codo tal como lo dibuja el editor y lo genera el plugin
    (`model_ops.fillet_geo`: rumbo esquina→vértice vecino, tope 1.0 del tramo o
    0.48 si el vecino también es codo). Si la tangencia no entra por ≤
    EDITOR_FIT_MAX_PT (codo que muere en un nodo con la otra tangencia 0.6 pt más
    allá del tee vecino: DU08 h.26), el radio reconocido se ajusta al máximo que
    entra: no sale «recortado» (a trazos) en el editor ni con otro radio en Civil 3D.
    Modifica `fillets` en el lugar."""
    import model_ops as MO
    for i, fl in fillets.items():
        if not (0 < i < len(pts) - 1):
            continue
        caps = [MO.FILLET_CAP_CURVA if kinds[j] == "fillet" else MO.FILLET_CAP_RECTA for j in (i - 1, i + 1)]
        geo = MO.fillet_geo(pts[i - 1], pts[i], pts[i + 1], fl["r_px"], max_frac=caps[0],
                            max_frac_next=caps[1], tol_r=0.0)
        if geo is None or not geo["clamped"] or geo["r"] <= 1e-9:
            continue
        if fl["r_px"] * geo["T"] / geo["r"] - geo["T"] > EDITOR_FIT_MAX_PT * f:
            continue                                 # recorte real: que el editor lo avise
        fl.update(r_px=geo["r"], a=geo["t1"], b=geo["t2"], center=geo["center"])
    return fillets


def relabel_false_curves(pts, kinds, pieces: Sequence[ArcPiece], f: float = 1.0, drawn=()):
    """Un vértice `curve` que quedó en la polilínea sin NINGÚN trozo de arco de tinta
    cerca no es curva del plano: es la esquina de una línea continua que el núcleo
    tomó por curva (agua, gas…), o un vértice de la recta junto a un codo que ya
    dibuja esa tinta (`drawn` = [(centro, r)] de los codos puestos). Se marca
    `corner` (giro ≥ 8°) o `bend`; así el aviso «curvas que quedan como polilínea»
    solo cuenta curvas de verdad. La geometría no cambia (los tres son vértices
    blandos para el editor)."""
    kinds = list(kinds)
    near = 3.0 * f

    def explained(pc):
        return any(sum(1 for q in pc.pts if abs(math.hypot(q[0] - c[0], q[1] - c[1]) - r) <= 1.5 * f)
                   >= 0.5 * len(pc.pts) for c, r in drawn)
    live = [pc for pc in pieces if not explained(pc)]
    for i, k in enumerate(kinds):
        if k != "curve" or i == 0 or i == len(kinds) - 1:
            continue
        q = pts[i]
        if any(_seg_dist(q, a, b) <= near for pc in live for a, b in zip(pc.pts, pc.pts[1:])):
            continue
        t = abs(_turn_deg(pts[i - 1], q, pts[i + 1]))
        kinds[i] = "corner" if t >= 8.0 else "bend"
    return kinds
