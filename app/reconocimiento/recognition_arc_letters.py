"""Curva con el RÓTULO dentro: el texto del linetype va sobre el arco (PURO, sin Qt ni fitz).

Reporte del usuario 2026-10-19 (DU06 h.3, hoja compuesta UD-201…UD-214): la línea
«—SC—» de `G-XREF` gira 90° con un arco de r = 18 pt hacia una caja de empalme y las
letras «SC» van DENTRO del arco, giradas con él. AutoCAD dibuja el guión que llega
recto hasta el inicio del arco y unas pocas cuerdas del arco aplanado (≈2 pt cada
una); el resto del arco es el rótulo. Así:

  · el reparto línea por línea de una capa genérica por sus letras
    (`recognition_letter_lines`) no unía el guión de después —sus puntas son cuerdas
    de <1 pt que giran 90°: ni esquina, ni hueco, ni continuación— y ese guión, sin
    letras propias, quedaba sin utilidad (la línea no llegaba a la caja);
  · los codos de la tinta exigen ≥45 % de tinta sobre el arco, y aquí la tinta curva
    es solo ~30 %: lo demás son las letras.

Las letras del linetype sobre el arco SON la línea (la misma regla que «letra en el
hueco = la línea sigue»), así que aquí cuentan como su tinta. Nada se inventa: el
círculo es el TANGENTE a las dos rectas de tinta que pasa por las cuerdas curvas de
las dos puntas (RMS ≤ `FIT_RMS_PT`), las tangencias caen donde termina cada recta
(≤ `JOINT_TOL_PT`) y las letras tapan el resto del arco (≥ `COVER_MIN`).

  · `arc_tips`: puntas curvas de los guiones (recta ≥ `DASH_MIN_PT` + cuerdas cortas
    que giran siempre al mismo lado).
  · `letter_gaps`: pares de puntas unidas por un arco con letras (para el reparto).
  · `letter_arcs`: el codo en la polilínea reconocida (después de los codos de la
    tinta; solo donde no hay ya un codo).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

DASH_MIN_PT = 8.0          # el guión recto antes de la punta curva (= letter_lines.DASH_MIN_PT)
TIP_MAX_PT = 30.0          # largo máximo de la punta curva (unas pocas cuerdas del aplanado)
TIP_CHORD_MIN_PT = 0.3     # cuerdas más cortas: cuantización del final del trazo, no dan rumbo
TIP_TURN_MAX_DEG = 25.0    # giro por cuerda del arco aplanado (más = letra o esquina)
GAP_MAX_PT = 40.0          # cada recta llega a la esquina a ≤ esto (= hueco máximo del linetype)
TURN_MIN_DEG = 15.0        # menos: lo une la continuación de frente (letter_lines/núcleo)
TURN_MAX_DEG = 160.0
SYM_TOL_FRAC = 0.2         # las dos rectas llegan a la esquina con el mismo largo (arco tangente)…
SYM_TOL_PT = 1.0           # …± esto
FIT_RMS_PT = 0.15          # el aplanado de AutoCAD está SOBRE el círculo (flecha 0.025 pt)
FIT_MAX_PT = 0.35
JOINT_TOL_PT = 1.0         # la tangencia cae donde la recta de tinta pasa a ser curva
LETTER_RING_PT = 2.5       # el centro de una letra del rótulo va sobre el arco ±esto
LETTER_PAD_PT = 1.0        # margen de la caja de la letra al medir lo que tapa del arco
INK_ON_ARC_PT = 0.75       # muestra del arco con tinta curva a ≤ esto
COVER_MIN = 0.85           # tinta curva + letras sobre el arco A→B
CORRIDOR_PT = 2.5          # = FILLET_INK_CORRIDOR_PT: tangencias sobre la polilínea reconocida
DROP_TOL_PT = 1.5          # vértices que el codo quita: dentro del triángulo A–C–B ±esto
ANCHOR_TOL_PT = 0.5        # vértice vecino sobre la recta de tinta…
ANCHOR_MOVE_PT = 1.5       # …o (blando) llevado a ella si está a ≤ esto
SOFT_KINDS = ("bend", "corner", "curve")
GLYPH_MAX_DIM_PT = 12.0    # = recognition_geom.GLYPH_MAX_DIM_PT: una letra cabe en 12×12 pt


def _unit(dx: float, dy: float) -> Pt:
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else (0.0, 0.0)


def _cross(u: Pt, v: Pt) -> float:
    return u[0] * v[1] - u[1] * v[0]


def _seg_dist(q: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - t * vx, q[1] - a[1] - t * vy)


# ─────────────────────────────── puntas curvas ───────────────────────────────
class Tip:
    """Punta curva de un guión: `J` = donde termina la recta de tinta (inicio del arco),
    `d` = rumbo de esa recta hacia la punta, `pts` = J…punta (cuerdas del arco), `sign`
    = lado al que gira (+1/−1), `chain` / `last` = cadena y extremo."""
    __slots__ = ("J", "d", "S0", "pts", "sign", "chain", "last")

    def __init__(self, J, d, S0, pts, sign, chain, last):
        self.J, self.d, self.S0, self.pts, self.sign, self.chain, self.last = J, d, S0, pts, sign, chain, last


def _tip(ch, last: bool, f: float) -> Optional[Tuple]:
    pts = list(ch) if last else list(ch[::-1])
    # la recta del guión: el último tramo ≥ DASH_MIN_PT antes de la punta
    k = None
    for m in range(len(pts) - 2, -1, -1):
        if math.dist(pts[m], pts[m + 1]) >= DASH_MIN_PT * f:
            k = m
            break
        if sum(math.dist(pts[j], pts[j + 1]) for j in range(m, len(pts) - 1)) > TIP_MAX_PT * f:
            return None
    if k is None or k + 1 >= len(pts) - 1:
        return None
    S0, J = pts[k], pts[k + 1]
    d = _unit(J[0] - S0[0], J[1] - S0[1])
    tip = [J] + [q for q in pts[k + 2:]]
    dirs = [d]
    for a, b in zip(tip, tip[1:]):
        if math.dist(a, b) >= TIP_CHORD_MIN_PT * f:
            dirs.append(_unit(b[0] - a[0], b[1] - a[1]))
    if len(dirs) < 3:                                 # ≥ 2 cuerdas: una sola no prueba un arco
        return None
    sign = 0
    for u, v in zip(dirs, dirs[1:]):
        t = math.degrees(math.atan2(_cross(u, v), u[0] * v[0] + u[1] * v[1]))
        if abs(t) < 0.05:
            continue
        if abs(t) > TIP_TURN_MAX_DEG:
            return None
        s = 1 if t > 0 else -1
        if sign and s != sign:
            return None
        sign = s
    if not sign:
        return None
    return J, d, S0, tip, sign


def arc_tips(chains: Sequence[Sequence[Pt]], skip=(), f: float = 1.0) -> List[Tip]:
    """Puntas curvas de los guiones de `chains` (cadenas de puntos; `f` = px/pt)."""
    out = []
    for ci, ch in enumerate(chains):
        if ci in skip or len(ch) < 3:
            continue
        for last in (False, True):
            t = _tip(ch, last, f)
            if t is not None:
                out.append(Tip(*t, ci, last))
    return out


# ─────────────────────────────── arco entre dos puntas ───────────────────────────────
def _fit_tangent(members, C, ua, ub, s0):
    """Círculo tangente a las dos rectas (centro sobre la bisectriz a distancia s de C)
    que mejor pasa por `members` (= `recognition._fit_circle_tangent`)."""
    from reconocimiento import recognition as R          # perezoso: recognition importa este módulo
    return R._fit_circle_tangent(members, C, ua, ub, s0)


def _between(geo, boxes, f):
    """Letras (índices de `boxes`) sobre el arco de `geo`, entre el fin de la tinta curva
    de una punta y el de la otra, y la fracción del arco A→B tapada por tinta curva o letras."""
    cx, cy = geo["ctr"]; r = geo["r"]
    a0 = math.atan2(geo["A"][1] - cy, geo["A"][0] - cx)
    sweep = (math.atan2(geo["B"][1] - cy, geo["B"][0] - cx) - a0 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi

    def frac(q):                                          # 0 = A, 1 = B, sobre el arco
        d = (math.atan2(q[1] - cy, q[0] - cx) - a0 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
        return d / sweep if abs(sweep) > 1e-9 else 0.0
    ea, eb = frac(geo["tip_a"][-1]), frac(geo["tip_b"][-1])
    ring, pad = LETTER_RING_PT * f, LETTER_PAD_PT * f
    used = []
    for k, (x0, y0, x1, y1) in enumerate(boxes):
        m = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        if abs(math.hypot(m[0] - cx, m[1] - cy) - r) > ring:
            continue
        if ea < frac(m) < eb:
            used.append(k)
    if not used:
        return [], 0.0
    chords = list(zip(geo["tip_a"], geo["tip_a"][1:])) + list(zip(geo["tip_b"], geo["tip_b"][1:]))
    hit = 0
    for j in range(37):
        ang = a0 + sweep * j / 36
        q = (cx + r * math.cos(ang), cy + r * math.sin(ang))
        if any(_seg_dist(q, a, b) <= INK_ON_ARC_PT * f for a, b in chords):
            hit += 1
        elif any(boxes[k][0] - pad <= q[0] <= boxes[k][2] + pad and boxes[k][1] - pad <= q[1] <= boxes[k][3] + pad
                 for k in used):
            hit += 1
    return used, hit / 37.0


def arc_between(ta: Tip, tb: Tip, boxes, f: float = 1.0):
    """Arco del plano entre la punta `ta` (la línea llega) y `tb` (la línea sigue), con
    letras del rótulo encima, o None. Dict: C (esquina), A/B (tangencias), ctr, r, ua/ub
    (rumbo de llegada y de salida), rms, letters (índices de `boxes`), cover."""
    ua, ub = ta.d, (-tb.d[0], -tb.d[1])
    den = _cross(ta.d, tb.d)
    if abs(den) < 1e-9:
        return None
    vx, vy = tb.J[0] - ta.J[0], tb.J[1] - ta.J[1]
    s = (vx * tb.d[1] - vy * tb.d[0]) / den              # J_a + s·d_a = J_b + t·d_b
    t = (vx * ta.d[1] - vy * ta.d[0]) / den
    if not (0.0 < s <= GAP_MAX_PT * f and 0.0 < t <= GAP_MAX_PT * f):
        return None
    if abs(s - t) > SYM_TOL_FRAC * max(s, t) + SYM_TOL_PT * f:
        return None
    turn = math.degrees(math.atan2(_cross(ua, ub), ua[0] * ub[0] + ua[1] * ub[1]))
    if not (TURN_MIN_DEG <= abs(turn) <= TURN_MAX_DEG):
        return None
    side = 1 if turn > 0 else -1
    if ta.sign != side or tb.sign != -side:               # las dos puntas curvan HACIA el arco
        return None
    C = (ta.J[0] + s * ta.d[0], ta.J[1] + s * ta.d[1])
    phi = math.pi - math.radians(abs(turn))               # ángulo interior entre las rectas
    T0 = (s + t) / 2.0
    members = list(ta.pts) + list(tb.pts)
    fit = _fit_tangent(members, C, ua, ub, T0 * math.tan(phi / 2.0) / math.sin(phi / 2.0))
    if fit is None:
        return None
    cx, cy, r, rms = fit
    dmax = max(abs(math.hypot(q[0] - cx, q[1] - cy) - r) for q in members)
    if rms > FIT_RMS_PT * f or dmax > FIT_MAX_PT * f:
        return None
    T = r / math.tan(phi / 2.0)
    A = (C[0] - ua[0] * T, C[1] - ua[1] * T)
    B = (C[0] + ub[0] * T, C[1] + ub[1] * T)
    if math.dist(A, ta.J) > JOINT_TOL_PT * f or math.dist(B, tb.J) > JOINT_TOL_PT * f:
        return None
    geo = {"C": C, "A": A, "B": B, "ctr": (cx, cy), "r": r, "ua": ua, "ub": ub, "rms": rms,
           "tip_a": list(ta.pts), "tip_b": list(tb.pts)}
    used, cover = _between(geo, boxes, f)
    if not used or cover < COVER_MIN:
        return None
    geo["letters"], geo["cover"] = used, cover
    return geo


def _pairs(tips: Sequence[Tip], boxes, f: float):
    """[(punta que llega, punta que sigue, geo)] sin repetir punta (la de menor RMS)."""
    cell = 2.0 * GAP_MAX_PT * f
    grid = defaultdict(list)
    for k, tp in enumerate(tips):
        grid[(int(tp.J[0] // cell), int(tp.J[1] // cell))].append(k)
    found = []
    for k, ta in enumerate(tips):
        gx, gy = int(ta.J[0] // cell), int(ta.J[1] // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for m in grid.get((gx + dx, gy + dy), ()):
                    tb = tips[m]
                    if m == k or tb.chain == ta.chain:
                        continue
                    geo = arc_between(ta, tb, boxes, f)
                    if geo is not None:
                        found.append((geo["rms"], k, m, geo))
    found.sort(key=lambda e: e[0])
    taken, out = set(), []
    for _rms, k, m, geo in found:
        if k in taken or m in taken:
            continue
        taken.update((k, m))
        out.append((tips[k], tips[m], geo))
    return out


def letter_gaps(chains, skip, boxes, f: float = 1.0):
    """Para el reparto por letras: [((cadena que llega, cadena que sigue), [letras])]
    con `boxes` = cajas (x0, y0, x1, y1) de las cadenas que caben en una letra."""
    tips = arc_tips(chains, skip, f)
    if len(tips) < 2 or not boxes:
        return []
    return [((ta.chain, tb.chain), geo["letters"]) for ta, tb, geo in _pairs(tips, boxes, f)]


# ─────────────────────────────── el codo en la polilínea ───────────────────────────────
def _cumlen(pts):
    S = [0.0]
    for a, b in zip(pts, pts[1:]):
        S.append(S[-1] + math.dist(a, b))
    return S


def _project(pts, S, q):
    """(s, distancia) del punto `q` sobre la polilínea."""
    best = (math.inf, 0.0)
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        d = math.hypot(q[0] - a[0] - t * vx, q[1] - a[1] - t * vy)
        if d < best[0]:
            best = (d, S[k] + t * math.sqrt(L2))
    return best[1], best[0]


def _in_triangle_dist(q, A, C, B):
    """Distancia de q al triángulo A–C–B (0 dentro)."""
    s1, s2, s3 = _cross((C[0] - A[0], C[1] - A[1]), (q[0] - A[0], q[1] - A[1])), \
        _cross((B[0] - C[0], B[1] - C[1]), (q[0] - C[0], q[1] - C[1])), \
        _cross((A[0] - B[0], A[1] - B[1]), (q[0] - B[0], q[1] - B[1]))
    if (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0):
        return 0.0
    return min(_seg_dist(q, A, C), _seg_dist(q, C, B), _seg_dist(q, B, A))


def _anchor(q, kind, P, u, T, before, f):
    """El vértice vecino del codo sobre la recta de tinta (P, u), del lado correcto de la
    tangencia T: tal cual, llevado a la recta (blando, ≤ ANCHOR_MOVE_PT) o None."""
    off = _cross(u, (q[0] - P[0], q[1] - P[1]))
    along = (q[0] - T[0]) * u[0] + (q[1] - T[1]) * u[1]
    if (along > JOINT_TOL_PT * f) if before else (along < -JOINT_TOL_PT * f):
        return None
    if abs(off) <= ANCHOR_TOL_PT * f:
        return q
    if kind in SOFT_KINDS and abs(off) <= ANCHOR_MOVE_PT * f:
        return (q[0] + u[1] * off, q[1] - u[0] * off)
    return None


def _apply(pts, kinds, fillets, geo, f):
    """Pone el codo de `geo` en la polilínea (o None si no encaja sin tocar nada más)."""
    n = len(pts)
    S = _cumlen(pts)
    A, B, C, ua, ub = geo["A"], geo["B"], geo["C"], geo["ua"], geo["ub"]
    (sA, dA), (sB, dB) = _project(pts, S, A), _project(pts, S, B)
    if max(dA, dB) > CORRIDOR_PT * f:
        return None
    if sA > sB:                                           # la polilínea va al revés del par
        A, B, ua, ub = B, A, (-ub[0], -ub[1]), (-ua[0], -ua[1])
        sA, sB = sB, sA
    edge = JOINT_TOL_PT * f
    inner = [k for k in range(n) if sA - edge < S[k] < sB + edge]
    lo = inner[0] if inner else next((k for k in range(n) if S[k] >= sB + edge), n)
    hi = inner[-1] if inner else lo - 1
    if lo < 1 or hi > n - 2:
        return None
    if any(j in fillets for j in range(lo - 1, hi + 2)):
        return None                                       # ya hay un codo ahí o en su ancla
    for k in inner:
        if kinds[k] not in SOFT_KINDS or _in_triangle_dist(pts[k], A, C, B) > DROP_TOL_PT * f:
            return None
    pa = _anchor(pts[lo - 1], kinds[lo - 1], A, ua, A, True, f)
    pb = _anchor(pts[hi + 1], kinds[hi + 1], B, ub, B, False, f)
    if pa is None or pb is None:
        return None
    new_pts = list(pts[:lo - 1]) + [pa, C, pb] + list(pts[hi + 2:])
    new_kinds = list(kinds[:lo]) + ["fillet"] + list(kinds[hi + 1:])
    shift = (hi - lo + 1) - 1
    new_fil = {}
    for i, fl in fillets.items():
        new_fil[i if i < lo else i - shift] = fl
    new_fil[lo] = {"a": A, "b": B, "center": geo["ctr"], "r_px": geo["r"], "loose": False,
                   "dev_px": round(geo["rms"], 2), "node_a": False, "node_b": False, "letters": True}
    return new_pts, new_kinds, new_fil


def letter_arcs(pts, kinds, fillets, strokes, glyph_boxes, f: float = 1.0):
    """Codos de las curvas con el rótulo encima, en la polilínea reconocida (px; `f` =
    px/pt). `strokes` = trazos de tinta de la línea, `glyph_boxes` = cajas de las letras
    del linetype que reconoció el núcleo. Solo agrega codos (donde no hay ya uno); si
    nada encaja devuelve lo mismo."""
    if len(pts) < 3 or not strokes or not glyph_boxes:
        return pts, kinds, fillets
    glyph = GLYPH_MAX_DIM_PT * f
    small = {k for k, st in enumerate(strokes)
             if max(q[0] for q in st) - min(q[0] for q in st) <= glyph
             and max(q[1] for q in st) - min(q[1] for q in st) <= glyph}
    tips = arc_tips(strokes, small, f)                      # una letra no es punta de guión
    if len(tips) < 2:
        return pts, kinds, fillets
    pairs = _pairs(tips, list(glyph_boxes), f)
    if not pairs:
        return pts, kinds, fillets
    pts, kinds, fillets = list(pts), list(kinds), dict(fillets or {})
    added = False
    for _ta, _tb, geo in pairs:
        got = _apply(pts, kinds, fillets, geo, f)
        if got is not None:
            pts, kinds, fillets = got
            added = True
    if added:
        from reconocimiento import recognition_arcs as arcs_mod
        arcs_mod.fit_to_editor(pts, kinds, fillets, f)      # editor = plugin = esto
    return pts, kinds, fillets
