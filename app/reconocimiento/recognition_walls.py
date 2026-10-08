"""Tubería dibujada con sus DOS PAREDES (o paredes + eje) en la capa de la línea. PURO.

Reporte del usuario 2026-10-02 (plano ET-004, `C-SSWR-PIPE`): hay cadistas que no
dibujan la línea de la tubería sino sus dos paredes —dos trazos paralelos a la
distancia del diámetro a escala (1.3 pt en ese plano)— y el reconocimiento sacaba dos
utilidades pegadas. Otros dibujan las paredes Y el eje. Regla del usuario: «si las
líneas van juntas de inicio a fin, es una sola utilidad»; se toma la línea del MEDIO.

Pared = trazo ABIERTO de solo rectas, de ≥ `WALL_MIN_LEN_PT`, cuyo gemelo de la misma
capa corre a separación CONSTANTE (`WALL_MIN_SEP_PT`–`WALL_MAX_SEP_PT`, ±
`WALL_SEP_TOL_*`) a lo largo de ≥ `WALL_COVER` de cada uno, con las puntas juntas
(≤ max(`WALL_END_TOL_PT`, `WALL_END_TOL_SEP` × separación)) y largo ≥
`WALL_MIN_ASPECT` × separación. Los trazos que se tocan punta con punta (una pared
exportada segmento por segmento) se encadenan antes.

NO son paredes (auditoría de los 4 PDFs de prueba, 2026-10-02):
  - tres o más paralelas gemelas (marco del cajetín de DU10 en capas de utilidad, a
    0.46/2.3/2.9 pt; cuatro líneas de telecom a 20.6 pt en DU10 h.27; tres líneas de
    agua «—W—» en DU10 h.25) → grupo, no se toca. Salvo el caso paredes + eje: la del
    medio a la mitad exacta → se quitan las dos de afuera;
  - figuras cerradas (dos cuadrados anidados de un símbolo en DU06 h.4);
  - guiones de un linetype con LETRAS: si un trazo sigue de frente tras un hueco y en
    ese hueco hay tinta de la capa (la «W»), es una línea con letras, no una pared.
Si sobre la línea media ya hay tinta de alguna capa de líneas de la utilidad
(≥ `WALL_CENTER_COVER`), el eje existe: se quitan las paredes y se usa ese eje.

Formas de dibujar la tubería halladas (ET-004 h.1/h.2 drenaje, 2026-10-02):
  1. dos paredes continuas (el reporte, `C-SSWR-PIPE` a 1.3 pt);
  2. paredes + eje (en la misma capa o en otra de la utilidad);
  3. paredes + CUERPO relleno (banda verde triangulada): un relleno grande que cae
     entero entre las paredes (`_band_fills`) sale con ellas — un relleno no es eje;
  4. paredes A TRAZOS (tubería existente), a veces dos copias desfasadas que se pisan,
     con quiebres y un TAPÓN que une las puntas: `recognition_wall_runs`.
Una «letra» en un hueco es tinta CHICA (≤ `WALL_GLYPH_MAX_PT`): la pared de otra
tubería que cruza el hueco junto al buzón no lo es. Los cambios se avisan solo si
quedan como línea reconocida (`recognition._recognized_walls`).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

WALL_MIN_SEP_PT = 0.5       # menos: la MISMA línea dibujada dos veces algo corrida (LABOE h.32
                            # `PROP_SEWER_PIPE_NTWK` a 0.42 pt: el núcleo ya la toma como una sola);
                            # 0.5 pt = tubo de 3" a 1"=40'
WALL_MAX_SEP_PT = 30.0      # ≈ 12 ft a 1"=40' / 8 ft a 1"=20': tuberías grandes
WALL_SEP_TOL_PT = 0.2       # la separación es CONSTANTE: ± max(esto, …
WALL_SEP_TOL_FRAC = 0.08    # … esta fracción de la separación)
WALL_MIN_LEN_PT = 20.0      # un guión o un trazo de letra no es una pared
WALL_MIN_ASPECT = 8.0       # largo ≥ 8 × separación (lados de un símbolo no)
WALL_COVER = 0.9            # cada pared corre junto a la otra en ≥ 90 % de su largo
WALL_END_TOL_PT = 2.0       # las puntas van juntas: ≤ max(esto, …
WALL_END_TOL_SEP = 2.0      # … esta cantidad de separaciones) — en un giro se escalonan
WALL_TOUCH_PT = 0.05        # trazos que se tocan punta con punta = la misma pared
WALL_GAP_MAX_PT = 40.0      # hueco hasta el guión siguiente que se mira por letras
WALL_GAP_HALF_W_PT = 1.0    # media franja del hueco donde una letra cruza su línea
WALL_SEQ_MAX_PT = 300.0     # hasta dónde se siguen los guiones de esa recta buscando letras
WALL_CENTER_COVER = 0.5     # tinta sobre la línea media → paredes + eje
WALL_CENTER_TOL_PT = 0.3    # … a ≤ max(esto, 15 % de la separación) del medio
WALL_GLYPH_MAX_PT = 8.0     # un relleno más chico es una letra/símbolo, no el cuerpo de la tubería
WALL_CUT_TOL_PT = 0.1       # punta sobre un punto de corte del clip (`clip_path`: exacto)


def _xy(q) -> Pt:
    return (float(q.x), float(q.y)) if hasattr(q, "x") else (float(q[0]), float(q[1]))


def _all_points(path: dict) -> List[Pt]:
    """Todos los puntos de un path: Point, Rect (esquinas), Quad o tuplas recortadas."""
    out: List[Pt] = []
    for it in path.get("items") or []:
        for q in it[1:]:
            if hasattr(q, "x0"):
                out += [(q.x0, q.y0), (q.x1, q.y0), (q.x1, q.y1), (q.x0, q.y1)]
            elif hasattr(q, "ul"):
                out += [(v.x, v.y) for v in (q.ul, q.ur, q.lr, q.ll)]
            elif hasattr(q, "x"):
                out.append((float(q.x), float(q.y)))
            elif isinstance(q, (tuple, list)) and len(q) == 2:
                out.append((float(q[0]), float(q[1])))
    return out


def _chains(path: dict) -> Optional[List[List[Pt]]]:
    """Cadenas de un path de SOLO rectas; None si trae curvas, rectángulos o relleno."""
    if path.get("fill") is not None:
        return None
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


def _length(c: Sequence[Pt]) -> float:
    return sum(math.dist(a, b) for a, b in zip(c, c[1:]))


def _closest(q: Pt, c: Sequence[Pt]) -> Tuple[float, Pt, float]:
    """(distancia, punto más cercano, parámetro de largo) de q a la polilínea c."""
    best = (math.inf, c[0], 0.0)
    s = 0.0
    for a, b in zip(c, c[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        L = math.sqrt(L2)
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        p = (a[0] + vx * t, a[1] + vy * t)
        d = math.dist(q, p)
        if d < best[0]:
            best = (d, p, s + L * t)
        s += L
    return best


def _samples(c: Sequence[Pt], step: float) -> List[Pt]:
    out: List[Pt] = []
    for a, b in zip(c, c[1:]):
        L = math.dist(a, b)
        n = max(1, int(math.ceil(L / step)))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    out.append(c[-1])
    return out


def _sep_tol(sep: float) -> float:
    return max(WALL_SEP_TOL_PT, WALL_SEP_TOL_FRAC * sep)


class _Stroke:
    __slots__ = ("pts", "parts", "L", "box", "cut", "dashes")

    def __init__(self, pts: List[Pt], parts: List[Tuple[int, int]]):
        self.pts = pts
        self.parts = parts                 # [(path, cadena)] que la forman
        self.L = _length(pts)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        self.box = (min(xs), min(ys), max(xs), max(ys))
        self.cut = (False, False)          # ¿punta inicial / final cortada por el clip del PDF?
        self.dashes = None                 # pared A TRAZOS: intervalos de tinta (`recognition_wall_runs`)

    def mark_cuts(self, cuts: Sequence[Pt]):
        self.cut = tuple(any(math.dist(e, c) <= WALL_CUT_TOL_PT for c in cuts)
                         for e in (self.pts[0], self.pts[-1]))


def _strokes(chains_by_path: Dict[int, List[List[Pt]]]) -> List[_Stroke]:
    """Cadenas abiertas, encadenando las que se tocan punta con punta (exactamente dos
    en ese punto: una pared exportada tramo por tramo)."""
    items = [(pi, ci, c) for pi, cs in chains_by_path.items() for ci, c in enumerate(cs)]
    ends: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    key = lambda p: (round(p[0] / WALL_TOUCH_PT), round(p[1] / WALL_TOUCH_PT))  # noqa: E731
    for k, (_pi, _ci, c) in enumerate(items):
        for side, p in ((0, c[0]), (1, c[-1])):
            ends.setdefault(key(p), []).append((k, side))
    used = [False] * len(items)
    out: List[_Stroke] = []

    def leg(k, side):
        """(largo, dirección hacia afuera) del tramo de la cadena k en esa punta."""
        c = items[k][2]
        a, b = (c[-2], c[-1]) if side else (c[1], c[0])
        L = math.dist(a, b)
        return _length(c), ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 1e-9 else (1.0, 0.0)

    def other(k, side):
        lst = ends.get(key(items[k][2][-1 if side else 0]), [])
        nb = [(j, s) for j, s in lst if j != k]
        if len(lst) != 2 or len(nb) != 1:
            return None
        # un trazo corto que gira fuerte (el TAPÓN que une las dos paredes) no es
        # la misma pared; una pared exportada tramo por tramo sí gira en sus vértices
        (Lk, (ux, uy)), (Lj, (vx, vy)) = leg(k, side), leg(*nb[0])
        if min(Lk, Lj) < WALL_MIN_LEN_PT and -(ux * vx + uy * vy) < math.cos(math.radians(60)):
            return None
        return nb[0]

    for k in range(len(items)):
        if used[k]:
            continue
        # ir al principio de la cadena (sin dar vueltas en un lazo)
        start, side, seen = k, 0, {k}
        while True:
            nb = other(start, side)
            if nb is None or nb[0] in seen:
                break
            start, side = nb[0], 1 - nb[1]
            seen.add(start)
        pts: List[Pt] = []
        parts: List[Tuple[int, int]] = []
        cur, rev = start, side == 1
        while cur is not None and not used[cur]:
            used[cur] = True
            pi, ci, c = items[cur]
            seq = list(reversed(c)) if rev else list(c)
            pts += seq if not pts else seq[1:]
            parts.append((pi, ci))
            nb = other(cur, 0 if rev else 1)
            cur, rev = (nb[0], nb[1] == 1) if nb else (None, False)
        if len(pts) >= 2 and math.dist(pts[0], pts[-1]) > WALL_TOUCH_PT:   # cerrada = figura
            out.append(_Stroke(pts, parts))
    return out


def _twin(a: _Stroke, b: _Stroke) -> Optional[float]:
    """Separación si a y b son paredes gemelas (constante, de punta a punta)."""
    if min(a.L, b.L) < WALL_MIN_LEN_PT or (a.dashes is None) != (b.dashes is None):
        return None
    pad = WALL_MAX_SEP_PT
    if (a.box[0] > b.box[2] + pad or b.box[0] > a.box[2] + pad
            or a.box[1] > b.box[3] + pad or b.box[1] > a.box[3] + pad):
        return None
    step = max(0.5, min(3.0, min(a.L, b.L) / 40.0))
    da = [_closest(q, b.pts)[0] for q in _samples(a.pts, step)]
    near = sorted(d for d in da if d <= WALL_MAX_SEP_PT)
    if len(near) < 0.5 * len(da):
        return None
    sep = near[len(near) // 2]
    if not WALL_MIN_SEP_PT <= sep <= WALL_MAX_SEP_PT or min(a.L, b.L) < WALL_MIN_ASPECT * sep:
        return None
    if _cover(a, b, sep, step) < WALL_COVER or _cover(b, a, sep, step) < WALL_COVER:
        return None
    end_tol = sep + max(WALL_END_TOL_PT, WALL_END_TOL_SEP * sep)
    if any(math.dist(p, q) > end_tol and not cut for p, q, cut in _end_pairs(a, b)):
        return None
    return sep


def _end_pairs(a: _Stroke, b: _Stroke):
    """Puntas que se corresponden: ((de a, de b, ¿las dos cortadas por el clip?) × 2)."""
    straight = math.dist(a.pts[0], b.pts[0]) + math.dist(a.pts[-1], b.pts[-1])
    crossed = math.dist(a.pts[0], b.pts[-1]) + math.dist(a.pts[-1], b.pts[0])
    if straight <= crossed:
        return ((a.pts[0], b.pts[0], a.cut[0] and b.cut[0]),
                (a.pts[-1], b.pts[-1], a.cut[1] and b.cut[1]))
    return ((a.pts[0], b.pts[-1], a.cut[0] and b.cut[1]),
            (a.pts[-1], b.pts[0], a.cut[1] and b.cut[0]))


def _cover(a: _Stroke, b: _Stroke, sep: float, step: float) -> float:
    """Fracción de `a` que corre a la separación de `b`. No cuenta lo que pasa más
    allá de una punta de `b` cortada por el clip (un corte en ángulo deja las dos
    paredes de distinto largo)."""
    tol = _sep_tol(sep)
    ok = n = 0
    for q in _samples(a.pts, step):
        d, _p, t = _closest(q, b.pts)
        if (t <= 1e-6 and b.cut[0]) or (t >= b.L - 1e-6 and b.cut[1]):
            continue
        n += 1
        ok += abs(d - sep) <= tol
    return ok / n if n else 0.0


def midline(a: Sequence[Pt], b: Sequence[Pt]) -> List[Pt]:
    """Línea media de dos paredes: cada vértice de una con su punto más cercano de la
    otra, ordenados a lo largo de `a` (en un quiebre a inglete, el medio de las dos
    esquinas es la esquina del eje)."""
    if math.dist(a[0], b[0]) + math.dist(a[-1], b[-1]) > math.dist(a[0], b[-1]) + math.dist(a[-1], b[0]):
        b = list(reversed(b))
    marks: List[Tuple[float, Pt]] = []
    s = 0.0
    for i, p in enumerate(a):
        if i:
            s += math.dist(a[i - 1], p)
        _d, q, _t = _closest(p, b)
        marks.append((s, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)))
    for q in b[1:-1]:
        _d, p, t = _closest(q, a)
        marks.append((t, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)))
    marks.sort(key=lambda m: m[0])
    out: List[Pt] = []
    for _t, m in marks:
        if not out or math.dist(out[-1], m) > 0.05:
            out.append(m)
    # vértices colineales sobrantes fuera (proyección de una esquina sobre el tramo vecino)
    clean = [out[0]]
    for i in range(1, len(out) - 1):
        a0, m, b0 = clean[-1], out[i], out[i + 1]
        vx, vy = b0[0] - a0[0], b0[1] - a0[1]
        L = math.hypot(vx, vy)
        if L > 1e-9 and abs((m[0] - a0[0]) * vy - (m[1] - a0[1]) * vx) / L <= 0.02:
            continue
        clean.append(m)
    clean.append(out[-1])
    return clean


def _segments_of(paths_chains) -> List[Tuple[Pt, Pt]]:
    return [(a, b) for c in paths_chains for a, b in zip(c, c[1:])]


def _letter_in_gap(end: Pt, u: Pt, g0: float, g1: float, ink, skip: set) -> bool:
    """¿Hay tinta de la capa que CRUZA la recta (end, u) entre g0 y g1 (una letra)?"""
    ux, uy = u
    for pi, a, b in ink:
        if pi in skip:
            continue
        ta = (a[0] - end[0]) * ux + (a[1] - end[1]) * uy
        tb = (b[0] - end[0]) * ux + (b[1] - end[1]) * uy
        if max(ta, tb) <= g0 + 0.2 or min(ta, tb) >= g1 - 0.2:
            continue
        sa = (a[0] - end[0]) * -uy + (a[1] - end[1]) * ux
        sb = (b[0] - end[0]) * -uy + (b[1] - end[1]) * ux
        if min(sa, sb) <= WALL_GAP_HALF_W_PT and max(sa, sb) >= -WALL_GAP_HALF_W_PT and                 (abs(sa - sb) > 0.3 or abs(sa) <= WALL_GAP_HALF_W_PT):
            return True
    return False


def _lettered(s: _Stroke, skip: set, ink: List[Tuple[int, Pt, Pt]], big: set = frozenset()) -> bool:
    """¿La «pared» es un guión de un linetype con LETRAS? Se recorre la recta del
    trazo hacia afuera por cada punta: los trozos de tinta de la capa que siguen
    sobre ella (≤0.3 pt) son sus otros guiones, y si en ALGÚN hueco entre ellos
    (≤ `WALL_GAP_MAX_PT`, hasta `WALL_SEQ_MAX_PT`) hay tinta que cruza la recta, es
    una línea con letras (la «W» del agua en DU10 h.25: el último guión no tiene la
    letra en su hueco, pero sí los anteriores). `skip` = paths del par."""
    for end, prev in ((s.pts[0], s.pts[1]), (s.pts[-1], s.pts[-2])):
        L = math.dist(prev, end)
        if L < 1e-9:
            continue
        ux, uy = (end[0] - prev[0]) / L, (end[1] - prev[1]) / L
        pieces = []
        for pi, a, b in ink:
            if pi in skip:
                continue
            la = (a[0] - end[0]) * -uy + (a[1] - end[1]) * ux
            lb = (b[0] - end[0]) * -uy + (b[1] - end[1]) * ux
            if abs(la) > 0.3 or abs(lb) > 0.3:
                continue
            ta = (a[0] - end[0]) * ux + (a[1] - end[1]) * uy
            tb = (b[0] - end[0]) * ux + (b[1] - end[1]) * uy
            lo, hi = min(ta, tb), max(ta, tb)
            if hi > 0.3 and lo < WALL_SEQ_MAX_PT:
                pieces.append((max(lo, 0.0), hi))
        pos = 0.0
        for lo, hi in sorted(pieces):
            if hi <= pos:
                continue
            if lo > pos + 0.3:
                if lo - pos > WALL_GAP_MAX_PT:
                    break                    # la línea terminó: lo que sigue es otra cosa
                if _letter_in_gap(end, (ux, uy), pos, lo, ink, skip | big):
                    return True
            pos = max(pos, hi)
    return False


def _max_dim(path: dict) -> float:
    pts = _all_points(path)
    if not pts:
        return 0.0
    return max(max(p[0] for p in pts) - min(p[0] for p in pts), max(p[1] for p in pts) - min(p[1] for p in pts))


def _band_fills(line: Sequence[Pt], sep: float, big_fills: set, paths: Sequence[dict]) -> set:
    """Rellenos grandes que caen ENTEROS dentro de la banda entre las paredes."""
    out = set()
    if not big_fills:
        return out
    lim = sep / 2.0 + WALL_SEP_TOL_PT
    # el relleno suele seguir hasta el centro del buzón: se mira el eje prolongado
    ext = max(3.0, 2.0 * sep)
    (ax, ay), (bx, by) = line[0], line[1]
    L0 = math.hypot(bx - ax, by - ay) or 1.0
    (cx, cy), (dx, dy) = line[-2], line[-1]
    L1 = math.hypot(dx - cx, dy - cy) or 1.0
    line = [(ax - (bx - ax) / L0 * ext, ay - (by - ay) / L0 * ext)] + list(line[1:-1]) +            [(dx + (dx - cx) / L1 * ext, dy + (dy - cy) / L1 * ext)] if len(line) > 2 else            [(ax - (bx - ax) / L0 * ext, ay - (by - ay) / L0 * ext), (bx + (bx - ax) / L0 * ext, by + (by - ay) / L0 * ext)]
    xs = [p[0] for p in line]; ys = [p[1] for p in line]
    box = (min(xs) - lim, min(ys) - lim, max(xs) + lim, max(ys) + lim)
    for pi in big_fills:
        pts = _all_points(paths[pi])
        if pts and all(box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3] for p in pts) and                 all(_closest(p, line)[0] <= lim for p in pts):
            out.add(pi)
    return out


def _covered(line: Sequence[Pt], segs: List[Tuple[Pt, Pt]], tol: float) -> float:
    pts = _samples(line, max(0.5, min(3.0, _length(line) / 40.0)))
    hit = 0
    for q in pts:
        for a, b in segs:
            if (min(a[0], b[0]) - tol <= q[0] <= max(a[0], b[0]) + tol
                    and min(a[1], b[1]) - tol <= q[1] <= max(a[1], b[1]) + tol
                    and _closest(q, (a, b))[0] <= tol):
                hit += 1
                break
    return hit / max(1, len(pts))


def merge_walls(paths: Sequence[dict], others: Sequence[dict] = (), make_rect=None
                ) -> Tuple[List[dict], List[dict]]:
    """Paths de UNA capa con cada par de paredes cambiado por su línea media (o
    quitado si ya hay eje). `others` = paths de las demás capas de líneas de la
    utilidad (un eje en otra capa también cuenta). Devuelve (paths, cambios), cada
    cambio {"kind": "walls"|"center", "sep": pt, "mid": [pts]}."""
    chains: Dict[int, List[List[Pt]]] = {}
    ink: List[Tuple[int, Pt, Pt]] = []
    for pi, p in enumerate(paths):
        ch = _chains(p)
        if ch is not None and not p.get("closePath"):
            chains[pi] = ch
        from_pts = ch if ch is not None else None
        if from_pts is None:                 # letras con curvas, rellenos: su tinta también cuenta
            pts = _all_points(p)
            ink += [(pi, a, b) for a, b in zip(pts, pts[1:])]
        else:
            ink += [(pi, a, b) for c in from_pts for a, b in zip(c, c[1:])]
    # Relleno de la capa: no es un eje. Uno grande (no una letra) entre dos paredes es
    # el CUERPO de la tubería (ET-004 `C-STRM-PIPE`: banda verde triangulada + paredes).
    fills = {pi for pi, p in enumerate(paths) if p.get("fill") is not None}
    big_fills = {pi for pi in fills if _max_dim(paths[pi]) > WALL_GLYPH_MAX_PT}
    # una LETRA del linetype es un trazo chico; la pared de otra tubería que cruza el
    # hueco junto al buzón (ET-004 h.1, 54 pt) no lo es
    big = {pi for pi, p in enumerate(paths) if _max_dim(p) > WALL_GLYPH_MAX_PT}
    from reconocimiento.recognition_wall_runs import dash_runs, run_lettered, run_axis_dashes, caps, joint_leftovers
    strokes = _strokes(chains)
    strokes += dash_runs(strokes, 1.0, WALL_MIN_LEN_PT, _Stroke)      # paredes a trazos
    for st in strokes:
        st.mark_cuts([_xy(c) for pi, _ci in st.parts for c in (paths[pi].get("cut_pts") or ())])
    long_ = [k for k, s in enumerate(strokes) if s.L >= WALL_MIN_LEN_PT]
    twins: Dict[int, Dict[int, float]] = {k: {} for k in long_}
    for i, a in enumerate(long_):
        for b in long_[i + 1:]:
            sep = _twin(strokes[a], strokes[b])
            if sep is not None:
                twins[a][b] = sep
                twins[b][a] = sep
    changes: List[dict] = []
    drop: set = set()                       # trazos (índice) que salen
    drop_paths: set = set()                 # rellenos del cuerpo de la tubería que salen
    add: List[Tuple[List[List[Pt]], List[Pt]]] = []   # (trazos del eje, sus puntas cortadas)
    other_segs = _segments_of(c for p in others for c in (_chains(p) or []))
    done: set = set()
    for k in long_:
        if k in done or not twins[k]:
            continue
        group = {k} | set(twins[k])
        for j in list(group):
            group |= set(twins.get(j, {}))
        if len(group) == 3 and all(len(twins[m]) == 2 for m in group):
            # ¿paredes + eje? Las dos más separadas son las paredes; la otra, el eje,
            # a la misma distancia de las dos (la mitad de la separación).
            g = sorted(group)
            o1, o2 = max(((x, y) for i, x in enumerate(g) for y in g[i + 1:]), key=lambda xy: twins[xy[0]][xy[1]])
            c = next(m for m in g if m not in (o1, o2))
            full, s1, s2 = twins[o1][o2], twins[c][o1], twins[c][o2]
            if abs(s1 - s2) <= _sep_tol(full) and abs(s1 + s2 - full) <= _sep_tol(full):
                drop |= {o1, o2}
                drop_paths |= _band_fills(strokes[c].pts, full, big_fills, paths)
                changes.append({"kind": "center", "sep": full, "mid": strokes[c].pts})
            done |= group
            continue
        done |= group
        if len(group) != 2:
            continue                         # marco, tabla, varias líneas juntas: no se toca
        a, b = sorted(group)
        sep = twins[a][b]
        skip = {pi for pi, _ci in strokes[a].parts + strokes[b].parts}
        if any(_lettered(strokes[k], skip | big_fills, ink, big) or
               (strokes[k].dashes and run_lettered(strokes[k], skip | big, ink, _letter_in_gap))
               for k in (a, b)):
            continue                         # guiones de un linetype con letras
        ends = _end_pairs(strokes[a], strokes[b])
        drop |= caps(strokes, strokes[a], strokes[b], ends, sep, drop | {a, b})   # tapones
        line = midline(strokes[a].pts, strokes[b].pts)
        tol = max(WALL_CENTER_TOL_PT, 0.15 * sep)
        body = _band_fills(line, sep, big_fills, paths)
        drop_paths |= body
        own = [(x, y) for pi, x, y in ink if pi not in skip and pi not in fills]
        if _covered(line, own + other_segs, tol) >= WALL_CENTER_COVER:
            drop |= {a, b}                   # ya hay eje: se usa ese
            changes.append({"kind": "center", "sep": sep, "mid": line})
            continue
        drop |= {a, b}
        (_p0, _q0, cut0), (_p1, _q1, cut1) = ends
        pieces = run_axis_dashes(strokes[a], strokes[b], line) if strokes[a].dashes else [line]
        if pieces:
            add.append((pieces, [q for q, c in ((pieces[0][0], cut0), (pieces[-1][-1], cut1)) if c]))
        changes.append({"kind": "walls", "sep": sep, "mid": line, "dashed": bool(strokes[a].dashes)})
    if not drop:
        return list(paths), []
    leftover, connectors = joint_leftovers(strokes, drop, changes)
    drop |= leftover
    if connectors:
        add.append((connectors, []))
    drop_paths -= {pi for k in range(len(strokes)) if k not in drop for pi, _ci in strokes[k].parts}
    gone: Dict[int, set] = {}
    for k in drop:
        for pi, ci in strokes[k].parts:
            gone.setdefault(pi, set()).add(ci)
    out: List[dict] = []
    template = None
    for pi, p in enumerate(paths):
        if pi in drop_paths:
            continue
        if pi not in gone:
            out.append(p)
            continue
        template = template or p
        rest = [c for ci, c in enumerate(chains[pi]) if ci not in gone[pi]]
        if rest:
            out.append(_with_chains(p, rest, make_rect))
    for pieces, cuts in add:
        for line in pieces:                  # un path por guión (como los de las paredes)
            q = _with_chains(template or {}, [line], make_rect)
            # corte del clip: el medio de los cortes de las paredes
            q["cut_pts"] = [c for c in cuts if math.dist(c, line[0]) < 1e-6 or math.dist(c, line[-1]) < 1e-6]
            q.pop("contact_pts", None)
            out.append(q)
    return out, changes


def _with_chains(path: dict, chains: List[List[Pt]], make_rect) -> dict:
    q = dict(path)
    q["items"] = [("l", a, b) for c in chains for a, b in zip(c, c[1:])]
    xs = [p[0] for c in chains for p in c]
    ys = [p[1] for c in chains for p in c]
    if make_rect is not None:
        q["rect"] = make_rect(min(xs), min(ys), max(xs), max(ys))
    q["closePath"] = False
    return q
