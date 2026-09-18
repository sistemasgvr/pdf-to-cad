"""recognition_geom.py — Reconstrucción de corridas de utilidad desde trazos PDF (puro).

En un PDF ploteado la utilidad NO viene como polilínea: viene el linetype
"explotado" (`── e ── e ──`): guiones de 1 segmento, letras «e» como glifos y
huecos. Este módulo reconstruye cada corrida y su topología:

  1. `classify_paths`   → guiones / letras / curvas (por forma, no por capa).
  2. `learn_pattern`    → longitudes y huecos típicos del linetype de ESTE plano
                          (las tolerancias salen del plano, no son constantes).
  3. `group_collinear`  → guiones sobre la misma recta (ángulo ±1°, offset ≤1.5 pt:
                          dos líneas paralelas cercanas NUNCA se mezclan).
  4. `build_runs`       → corridas: se une un hueco solo si es del patrón, o si
                          hay una letra encima, o si hay una bóveda en medio.
  5. `resolve_nodes`    → bóvedas, esquinas, quiebres suaves, T. Regla de oro: un
                          extremo SOLO se mueve a lo largo de su propia recta;
                          todo nodo es intersección de rectas o pie de perpendicular
                          (ninguna corrida se inclina jamás).
  6. `assemble`         → polilíneas inicio → quiebres → fin, con el tipo de cada
                          vértice, y métricas de cobertura para QA.

Coordenadas: puntos PDF (pt) tal como los da `page.get_drawings()`. La
conversión a píxeles del lienzo la hace quien llama (`recognition.py`).
Sin dependencias de Qt ni de fitz (acepta cualquier objeto con .x/.y).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

Pt = Tuple[float, float]
Line = Tuple[float, float, float, float]      # (px, py, ux, uy)

# ── Umbrales geométricos fijos (los del patrón se aprenden del plano) ─────────
GLYPH_MAX_DIM_PT = 12.0      # una letra/tick del linetype cabe en 12×12 pt
STRAIGHT_TOL_PT = 0.35       # polilínea "recta" si nada se aparta más del chord
MIN_DASH_PT = 1.0            # segmentos menores son basura numérica
COLLINEAR_ANG_DEG = 1.0      # misma recta: rumbo ±1°
COLLINEAR_PERP_PT = 1.5      # ...y ambos extremos a ≤1.5 pt de la recta
CORNER_MIN_ANG_DEG = 8.0     # menos que esto = quiebre suave (bend), no esquina
CURVE_SPLIT_ANG_DEG = 35.0   # una polilínea se parte en vértices más agudos
CURVE_SIMPLIFY_PT = 0.5      # Douglas-Peucker sobre curvas
VAULT_CLUSTER_PT = 4.0       # bboxes a ≤4 pt = misma bóveda
COVERAGE_TOL_PT = 2.5        # guión cubierto si sus puntos están a ≤2 pt
OFFPATTERN_FACTOR = 1.5      # trazo continuo solo, más largo que 1.5×guión = anotación
PATTERN_DASH_FACTOR = 2.0    # un guión del patrón cuenta hasta 2×dash_long (un poco más largo no es leader)
NODE_OFF_LINE_PT = 3.0       # nodo compartido válido si la recta pasa a ≤3 pt
RUN_FIT_TOL_PT = 0.75        # la polilínea sigue los guiones a ≤0.75 pt (se parte donde se apartan más)
MIN_JUNCTION_DASHES = 3      # solo líneas de red (≥3 guiones) definen el nodo interior de una bóveda
MARKER_MIN_ANG_DEG = 30.0    # un trazo corto que CRUZA la línea con este ángulo o más es marcador («/»)
MARKER_ON_LINE_PT = 1.0      # …si su punto medio cae a ≤1 pt de la recta del guión que cruza
LOOP_VAULT_MIN_PT = 12.0     # lazo rectangular cerrado de la propia capa = bóveda si su lado ≥12 pt…
LOOP_VAULT_MAX_PT = 120.0    # …y ≤120 pt (más grande ya no es un símbolo)
CHAIN_KINDS = ("corner", "bend", "edge")   # nodos de grado 2 que se encadenan (bóveda: regla propia)


# ─────────────────────────── modelos ───────────────────────────
@dataclass
class Dash:
    a: Pt
    b: Pt

    @property
    def length(self) -> float:
        return _dist(self.a, self.b)

    @property
    def angle(self) -> float:   # rumbo en [0, 180)
        return math.degrees(math.atan2(self.b[1] - self.a[1], self.b[0] - self.a[0])) % 180.0

    @property
    def mid(self) -> Pt:
        return ((self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2)


@dataclass
class Glyph:
    cx: float
    cy: float
    size: float


@dataclass
class Vault:
    x0: float
    y0: float
    x1: float
    y1: float
    n_paths: int = 1
    ref: Optional[Pt] = None      # punto de referencia (círculo del manhole / cajita interior)

    @property
    def center(self) -> Pt:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def reference(self) -> Pt:
        """Donde "nace" la línea dentro de la bóveda: la forma cerrada más
        pequeña (manhole, cajita, punto de centro) o, si no hay, el centro."""
        return self.ref if self.ref is not None else self.center

    def bbox(self, pad: float = 0.0) -> Tuple[float, float, float, float]:
        return (self.x0 - pad, self.y0 - pad, self.x1 + pad, self.y1 + pad)

    @property
    def radius(self) -> float:
        return max(self.x1 - self.x0, self.y1 - self.y0) / 2


@dataclass
class Pattern:
    dash_long: float
    dash_short: Optional[float]
    gap_max: float        # hueco más grande que forma parte del patrón
    letter: float         # tamaño típico de la letra
    join_gap: float       # hueco máximo sin evidencia
    glyph_bridge: float   # hueco máximo si hay letra encima
    vault_bridge: float   # hueco máximo si hay bóveda en medio
    corner_tol: float     # extremos a esta distancia cierran esquina / T


@dataclass
class Node:
    x: float
    y: float
    kind: str             # end | corner | bend | junction | tee | vault | edge | stop | cut
    vault_idx: int = -1


@dataclass
class Run:
    """Corrida recta (mid vacío) o curva (mid = vértices interiores)."""
    a: Pt
    b: Pt
    ux: float                 # dirección del chord a→b (unitaria)
    uy: float
    dashes: List[Dash] = field(default_factory=list)
    mid: List[Pt] = field(default_factory=list)
    ta: Optional[Tuple[float, float]] = None   # tangente en a (curvas), sentido a→b
    tb: Optional[Tuple[float, float]] = None   # tangente en b (curvas), sentido a→b
    node_a: int = -1
    node_b: int = -1
    inner: List[Tuple[float, int]] = field(default_factory=list)  # (t, node) 0<t<1, solo rectas
    origin: int = -1          # corrida original (las piezas partidas en una bóveda la comparten)
    synthetic: bool = False   # tramo borde→referencia dentro de una bóveda (sin guiones)
    split: bool = False       # pieza que resultó de partir una corrida que atraviesa una bóveda
    # Sintéticos: rumbo con que la línea de origen ENTRA a la bóveda. Con eso se
    # decide si la polilínea sigue derecho por la bóveda (no con el rumbo del
    # tramito borde→referencia, que es diagonal).
    chain_dir: Optional[Tuple[float, float]] = None
    continuous: bool = False  # trazo continuo sin patrón (curva/transición rescatada)

    @property
    def is_curve(self) -> bool:
        return bool(self.mid)

    @property
    def length(self) -> float:
        pts = [self.a] + self.mid + [self.b]
        return sum(_dist(p, q) for p, q in zip(pts, pts[1:]))

    def line(self, side: str) -> Line:
        """Recta tangente en el extremo `side` ('a'|'b'), orientada a→b."""
        if side == "a":
            u = self.ta or (self.ux, self.uy)
            return (self.a[0], self.a[1], u[0], u[1])
        u = self.tb or (self.ux, self.uy)
        return (self.b[0], self.b[1], u[0], u[1])

    def param(self, p: Pt) -> Tuple[float, float]:
        """(t a lo largo del chord, distancia perpendicular). Solo rectas."""
        dx, dy = self.b[0] - self.a[0], self.b[1] - self.a[1]
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            return 0.0, _dist(p, self.a)
        t = ((p[0] - self.a[0]) * dx + (p[1] - self.a[1]) * dy) / L2
        return t, _dist(p, (self.a[0] + t * dx, self.a[1] + t * dy))

    def at(self, t: float) -> Pt:
        return (self.a[0] + t * (self.b[0] - self.a[0]), self.a[1] + t * (self.b[1] - self.a[1]))


@dataclass
class Polyline:
    pts: List[Pt]
    kinds: List[str]      # tipo de nodo por vértice (mismo largo que pts)

    @property
    def length(self) -> float:
        return sum(_dist(p, q) for p, q in zip(self.pts, self.pts[1:]))


@dataclass
class GeomResult:
    polylines: List[Polyline]
    nodes: List[Node]
    vaults: List[Vault]
    pattern: Optional[Pattern]
    coverage: float                   # 0..1 por longitud de guión
    uncovered: List[Dash]
    vault_orphans: List[int]          # índices en `vaults` sin línea cerca
    # Trazos continuos largos sin patrón (leaders, flechas, símbolos): no son la
    # utilidad, pero se devuelven para mostrarlos y que el usuario decida.
    offpattern: List[Polyline] = field(default_factory=list)
    n_dashes: int = 0
    n_glyphs: int = 0
    n_curves: int = 0
    n_noise: int = 0                  # corridas descartadas por cortas/aisladas


# ─────────────────────────── helpers ───────────────────────────
def _xy(p) -> Pt:
    return (float(p.x), float(p.y)) if hasattr(p, "x") else (float(p[0]), float(p[1]))


def _dist(p: Pt, q: Pt) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _unit(dx: float, dy: float) -> Tuple[float, float]:
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else (1.0, 0.0)


def _ang_diff(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _median(xs: Sequence[float], default: float = 0.0) -> float:
    if not xs:
        return default
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# — rectas (px, py, ux, uy) —
def _line_angle(L: Line) -> float:
    return math.degrees(math.atan2(L[3], L[2])) % 180.0


def _perp_line(L: Line, p: Pt) -> float:
    return abs((p[0] - L[0]) * L[3] - (p[1] - L[1]) * L[2])


def _foot_on(L: Line, p: Pt) -> Pt:
    t = (p[0] - L[0]) * L[2] + (p[1] - L[1]) * L[3]
    return (L[0] + t * L[2], L[1] + t * L[3])


def _isect(L1: Line, L2: Line) -> Optional[Pt]:
    d = L1[2] * L2[3] - L1[3] * L2[2]
    if abs(d) < 1e-9:
        return None
    dx, dy = L2[0] - L1[0], L2[1] - L1[1]
    t = (dx * L2[3] - dy * L2[2]) / d
    return (L1[0] + t * L1[2], L1[1] + t * L1[3])


def _concurrent_point(lines: Sequence[Line], near: Pt, reach: float) -> Optional[Pt]:
    """Punto común de varias rectas: promedio de las intersecciones de pares no
    paralelos que caen a ≤ reach de `near`. None si no hay ninguna."""
    pts = []
    for x in range(len(lines)):
        for y in range(x + 1, len(lines)):
            if _ang_diff(_line_angle(lines[x]), _line_angle(lines[y])) < CORNER_MIN_ANG_DEG:
                continue
            P = _isect(lines[x], lines[y])
            if P is not None and _dist(P, near) <= reach:
                pts.append(P)
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _segment_bbox_range(r: Run, bb: Tuple[float, float, float, float]) -> Optional[Tuple[float, float]]:
    """Rango t (0..1) en que el chord de la corrida atraviesa el bbox (Liang–Barsky)."""
    dx, dy = r.b[0] - r.a[0], r.b[1] - r.a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, r.a[0] - bb[0]), (dx, bb[2] - r.a[0]), (-dy, r.a[1] - bb[1]), (dy, bb[3] - r.a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (t0, t1)


def _path_bbox(path: dict) -> Optional[Tuple[float, float, float, float]]:
    r = path.get("rect")
    if r is not None:
        return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
    return None


def _path_chains(path: dict) -> List[List[Pt]]:
    """Cadenas de puntos de los items ('l' rectos; curvas por sus puntos de
    control; 're'/'qu' como cuadrilátero cerrado)."""
    chains: List[List[Pt]] = []
    cur: List[Pt] = []
    for it in path.get("items") or []:
        cmd = it[0]
        if cmd == "l":
            p1, p2 = _xy(it[1]), _xy(it[2])
            if not cur or _dist(cur[-1], p1) > 1e-6:
                if cur:
                    chains.append(cur)
                cur = [p1]
            cur.append(p2)
        elif cmd == "c":
            pts = [_xy(it[i]) for i in range(1, 5)]
            if not cur or _dist(cur[-1], pts[0]) > 1e-6:
                if cur:
                    chains.append(cur)
                cur = [pts[0]]
            cur.extend(pts[1:])
        elif cmd in ("re", "qu"):
            if cur:
                chains.append(cur)
                cur = []
            q = it[1]
            if cmd == "re":
                pts = [(float(q.x0), float(q.y0)), (float(q.x1), float(q.y0)),
                       (float(q.x1), float(q.y1)), (float(q.x0), float(q.y1))]
            else:
                pts = [_xy(q.ul), _xy(q.ur), _xy(q.lr), _xy(q.ll)]
            chains.append(pts + [pts[0]])
    if cur:
        chains.append(cur)
    return chains


def _is_straight(chain: List[Pt], tol: float = STRAIGHT_TOL_PT) -> bool:
    a, b = chain[0], chain[-1]
    L = _dist(a, b)
    if L < 1e-9:
        return False
    for p in chain[1:-1]:
        cross = abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / L
        if cross > tol:
            return False
    return True


def _douglas_peucker(pts: List[Pt], eps: float) -> List[Pt]:
    if len(pts) <= 2:
        return list(pts)
    a, b = pts[0], pts[-1]
    L = _dist(a, b)
    best, bi = -1.0, -1
    for i in range(1, len(pts) - 1):
        p = pts[i]
        d = (abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / L
             if L > 1e-9 else _dist(p, a))
        if d > best:
            best, bi = d, i
    if best <= eps:
        return [a, b]
    left = _douglas_peucker(pts[:bi + 1], eps)
    right = _douglas_peucker(pts[bi:], eps)
    return left[:-1] + right


def _turning_deg(chain: List[Pt]) -> float:
    """Giro total (grados) a lo largo de una polilínea."""
    total = 0.0
    for i in range(1, len(chain) - 1):
        u1 = _unit(chain[i][0] - chain[i - 1][0], chain[i][1] - chain[i - 1][1])
        u2 = _unit(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1])
        dot = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        total += math.degrees(math.acos(dot))
    return total


def _split_at_corners(chain: List[Pt], ang_deg: float = CURVE_SPLIT_ANG_DEG) -> List[List[Pt]]:
    """Parte una polilínea en los vértices con giro brusco (esquinas reales)."""
    out: List[List[Pt]] = []
    cur = [chain[0]]
    for i in range(1, len(chain) - 1):
        cur.append(chain[i])
        u1 = _unit(chain[i][0] - chain[i - 1][0], chain[i][1] - chain[i - 1][1])
        u2 = _unit(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1])
        dot = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        if math.degrees(math.acos(dot)) > ang_deg:
            out.append(cur)
            cur = [chain[i]]
    cur.append(chain[-1])
    out.append(cur)
    return out


# ─────────────────────────── 0. recorte por clip ───────────────────────────
class _Rect:
    """bbox mínimo compatible con `path["rect"]` (x0, y0, x1, y1)."""
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


def _point_in_polygon(p: Pt, poly: Sequence[Pt]) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > y) != (by > y):
            xi = ax + (y - ay) * (bx - ax) / (by - ay)
            if x < xi:
                inside = not inside
    return inside


def _seg_poly_params(a: Pt, b: Pt, poly: Sequence[Pt]) -> List[float]:
    """Parámetros t∈(0,1) donde el segmento a→b cruza los lados del polígono."""
    ts = []
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = len(poly)
    for i in range(n):
        c, d = poly[i], poly[(i + 1) % n]
        ex, ey = d[0] - c[0], d[1] - c[1]
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den
        u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den
        if 1e-9 < t < 1 - 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            ts.append(t)
    return ts


def _clip_chain(chain: List[Pt], poly: Sequence[Pt], cuts: Optional[List[Pt]] = None) -> List[List[Pt]]:
    """Trozos de la cadena que quedan DENTRO del polígono (cadenas nuevas).
    Los puntos creados por el corte se agregan a `cuts`."""
    out: List[List[Pt]] = []
    cur: List[Pt] = []
    for a, b in zip(chain, chain[1:]):
        ts = sorted({0.0, 1.0, *_seg_poly_params(a, b, poly)})
        for t0, t1 in zip(ts, ts[1:]):
            p0 = (a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1]))
            p1 = (a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1]))
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            if cuts is not None:
                if 0.0 < t0 < 1.0:
                    cuts.append(p0)
                if 0.0 < t1 < 1.0:
                    cuts.append(p1)
            if _point_in_polygon(mid, poly):
                if cur and _dist(cur[-1], p0) <= 1e-6:
                    cur.append(p1)
                else:
                    if len(cur) >= 2:
                        out.append(cur)
                    cur = [p0, p1]
            else:
                if len(cur) >= 2:
                    out.append(cur)
                cur = []
    if len(cur) >= 2:
        out.append(cur)
    return out


def clip_path(path: dict, polygons: Sequence[Sequence[Pt]]) -> Optional[dict]:
    """Recorta un path de get_drawings() por uno o más polígonos de clip del PDF
    (el marco de la vista de planta, XCLIPs de referencias…). Devuelve un path
    equivalente solo con items 'l' (lo que quedó dentro) o None si no queda nada.
    Sin esto, la geometría "supera el final" que el usuario ve en pantalla."""
    chains = _path_chains(path)
    cuts: List[Pt] = []
    for poly in polygons:
        if len(poly) < 3:
            continue
        chains = [piece for ch in chains for piece in _clip_chain(ch, poly, cuts)]
    if not chains:
        return None
    uniq: List[Pt] = []
    for c in cuts:                                   # cada cruce aparece dos veces (sale/entra)
        if not any(_dist(c, u) <= 1e-6 for u in uniq):
            uniq.append(c)
    cuts = uniq
    items = [("l", p, q) for ch in chains for p, q in zip(ch, ch[1:])]
    xs = [pt[0] for ch in chains for pt in ch]
    ys = [pt[1] for ch in chains for pt in ch]
    return {
        "items": items, "rect": _Rect(min(xs), min(ys), max(xs), max(ys)),
        "layer": path.get("layer"), "fill": path.get("fill"), "color": path.get("color"),
        "closePath": False, "clipped": True, "cut_pts": cuts,
    }


# ─────────────────────────── 1. clasificar ───────────────────────────
def classify_paths(paths: Sequence[dict]) -> Tuple[List[Dash], List[Glyph], List[List[Pt]]]:
    """Paths de la capa de LÍNEAS → (guiones, letras, curvas).
    Guion = tramo recto. Letra = trazo compuesto que cabe en GLYPH_MAX_DIM_PT.
    Curva = polilínea suave grande (codo/arco), se conserva con sus vértices."""
    dashes: List[Dash] = []
    glyphs: List[Glyph] = []
    curves: List[List[Pt]] = []
    for path in paths:
        bb = _path_bbox(path)
        chains = _path_chains(path)
        if not chains:
            continue
        n_items = sum(max(0, len(c) - 1) for c in chains)
        has_curve = any(it[0] in ("c", "qu", "re") for it in (path.get("items") or []))
        maxdim = max(bb[2] - bb[0], bb[3] - bb[1]) if bb else 0.0
        # Un path cerrado "a→b→a" (o varios trozos rectos sobre la misma recta)
        # es UN guión, aunque tenga 2+ items y sea corto.
        if not has_curve and all(len(c) >= 2 and _is_straight(c) for c in chains):
            allpts = [q for c in chains for q in c]
            far = max(allpts, key=lambda q: _dist(q, allpts[0]))
            L = _dist(allpts[0], far)
            if L >= MIN_DASH_PT and all(
                    abs((far[0] - allpts[0][0]) * (q[1] - allpts[0][1]) - (far[1] - allpts[0][1]) * (q[0] - allpts[0][0])) / L
                    <= STRAIGHT_TOL_PT for q in allpts):
                far2 = max(allpts, key=lambda q: _dist(q, far))
                dashes.append(Dash(far, far2))
                continue
        if maxdim <= GLYPH_MAX_DIM_PT and (n_items >= 2 or has_curve or path.get("fill") is not None):
            # Un CODO (arco abierto y suave, «⌒») que conecta un conduit con el
            # borde de una bóveda es geometría, no una letra: gira ≤200° en
            # total y sus extremos quedan separados. Una «e» gira ~400°.
            if (len(chains) == 1 and len(chains[0]) >= 3 and path.get("fill") is None
                    and maxdim >= 3.0 and _dist(chains[0][0], chains[0][-1]) >= 0.5 * maxdim
                    and _turning_deg(chains[0]) <= 200.0):
                simp = _douglas_peucker(chains[0], CURVE_SIMPLIFY_PT)
                if len(simp) >= 3:
                    curves.append(simp)
                elif _dist(simp[0], simp[-1]) >= MIN_DASH_PT:
                    dashes.append(Dash(simp[0], simp[-1]))
                continue
            cx = (bb[0] + bb[2]) / 2 if bb else chains[0][0][0]
            cy = (bb[1] + bb[3]) / 2 if bb else chains[0][0][1]
            glyphs.append(Glyph(cx, cy, maxdim))
            continue
        for ch in chains:
            pts = [ch[0]] + [p for p, q in zip(ch[1:], ch) if _dist(p, q) > 1e-6]
            if len(pts) < 2:
                continue
            for sub in _split_at_corners(pts):
                if len(sub) < 2:
                    continue
                if _is_straight(sub):
                    d = Dash(sub[0], sub[-1])
                    if d.length >= MIN_DASH_PT:
                        dashes.append(d)
                    continue
                simp = _douglas_peucker(sub, CURVE_SIMPLIFY_PT)
                if len(simp) >= 3:
                    curves.append(simp)
                else:
                    d = Dash(simp[0], simp[-1])
                    if d.length >= MIN_DASH_PT:
                        dashes.append(d)
    return dashes, glyphs, curves


def strip_crossing_markers(dashes: List[Dash]) -> Tuple[List[Dash], List[Glyph]]:
    """Linetype de utilidad ABANDONADA: «──/── e ──». La barra «/» es un trazo
    recto corto que cruza la línea, así que `classify_paths` la ve como guión y
    luego quedaría "sin cubrir". Aquí se detecta (corta, ≥30° respecto de un
    guión cuya recta pasa por su punto medio) y pasa a ser un glifo más, como
    la letra: no cuenta para el patrón ni para la cobertura."""
    cell = 2.0 * GLYPH_MAX_DIM_PT
    grid: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for i, d in enumerate(dashes):
        x0, x1 = sorted((d.a[0], d.b[0])); y0, y1 = sorted((d.a[1], d.b[1]))
        # el guión se indexa con un margen de GLYPH_MAX_DIM_PT (ver `t` abajo)
        for cx in range(int((x0 - GLYPH_MAX_DIM_PT) // cell), int((x1 + GLYPH_MAX_DIM_PT) // cell) + 1):
            for cy in range(int((y0 - GLYPH_MAX_DIM_PT) // cell), int((y1 + GLYPH_MAX_DIM_PT) // cell) + 1):
                grid[(cx, cy)].append(i)
    keep: List[Dash] = []
    markers: List[Glyph] = []
    for i, d in enumerate(dashes):
        L = d.length
        if L > GLYPH_MAX_DIM_PT:
            keep.append(d)
            continue
        m = d.mid
        hit = False
        for j in grid.get((int(m[0] // cell), int(m[1] // cell)), ()):
            if j == i:
                continue
            o = dashes[j]
            if _ang_diff(o.angle, d.angle) < MARKER_MIN_ANG_DEG:
                continue
            # punto medio sobre la recta del otro guión, dentro de su extensión o
            # en el hueco pegado a él (la barra puede caer entre dos guiones)
            ux, uy = _unit(o.b[0] - o.a[0], o.b[1] - o.a[1])
            t = (m[0] - o.a[0]) * ux + (m[1] - o.a[1]) * uy
            perp = abs((m[0] - o.a[0]) * uy - (m[1] - o.a[1]) * ux)
            if perp <= MARKER_ON_LINE_PT and -GLYPH_MAX_DIM_PT <= t <= o.length + GLYPH_MAX_DIM_PT:
                hit = True
                break
        if hit:
            markers.append(Glyph(m[0], m[1], L))
        else:
            keep.append(d)
    return keep, markers


# ─────────────────────────── 2. patrón ───────────────────────────
class _Group:
    """Guiones sobre una misma recta (origen + unitario)."""

    def __init__(self, seed: Dash):
        self.origin = seed.a
        self.ux, self.uy = _unit(seed.b[0] - seed.a[0], seed.b[1] - seed.a[1])
        self.angle = seed.angle
        self.dashes: List[Dash] = [seed]

    def perp(self, p: Pt) -> float:
        return abs((p[0] - self.origin[0]) * self.uy - (p[1] - self.origin[1]) * self.ux)

    def t(self, p: Pt) -> float:
        return (p[0] - self.origin[0]) * self.ux + (p[1] - self.origin[1]) * self.uy

    def fit_error(self, d: Dash) -> Optional[float]:
        """Distancia perpendicular máxima de los extremos a la recta, o None si
        el guión no cabe (rumbo o offset fuera de tolerancia)."""
        if _ang_diff(self.angle, d.angle) > COLLINEAR_ANG_DEG:
            return None
        e = max(self.perp(d.a), self.perp(d.b))
        return e if e <= COLLINEAR_PERP_PT else None

    def intervals(self) -> List[Tuple[float, float, Dash]]:
        out = []
        for d in self.dashes:
            ta, tb = self.t(d.a), self.t(d.b)
            out.append((min(ta, tb), max(ta, tb), d))
        return out


def _consecutive_gaps(groups: List[_Group]) -> List[float]:
    gaps: List[float] = []
    for g in groups:
        ivs = sorted(g.intervals(), key=lambda iv: (iv[0], iv[1]))
        for (a0, a1, _), (b0, b1, _) in zip(ivs, ivs[1:]):
            gap = b0 - a1
            if gap > 0:
                gaps.append(gap)
    return gaps


def learn_pattern(dashes: Sequence[Dash], glyphs: Sequence[Glyph],
                  vaults: Sequence[Vault], groups: List[_Group]) -> Pattern:
    """Tolerancias derivadas del propio plano (escala-independiente)."""
    lengths = [round(d.length) for d in dashes]
    letter = _median([g.size for g in glyphs], default=5.0) or 5.0
    if lengths:
        # Longitudes FRECUENTES (≥20 % del modo): el guión largo es la mayor de
        # ellas y el corto la menor. No se usa la mediana: un patrón con dos
        # guiones cortos por cada largo la sesgaría hacia el corto.
        cnt = Counter(lengths)
        top = max(cnt.values())
        frequent = [L for L, c in cnt.items() if c >= 0.2 * top and L >= 2]
        dash_long = float(max(frequent)) if frequent else float(max(lengths))
        shorts = [L for L in frequent if L < 0.6 * dash_long]
        dash_short = float(min(shorts)) if shorts else None
    else:
        dash_long, dash_short = 20.0, None
    # Huecos del patrón: percentil 90 de los huecos "pequeños" (≤ 6 letras).
    # El máximo NO sirve: un par de huecos por texto/wipeout lo dispararía.
    gaps = _consecutive_gaps(groups)
    small = sorted(g for g in gaps if g <= 6 * letter)
    gap_max = small[min(len(small) - 1, int(0.9 * len(small)))] if small else 2 * letter
    gap_max = max(math.ceil(gap_max), 2.0)
    join_gap = max(2.0 * gap_max, 1.5 * letter, 6.0)
    glyph_bridge = max(4.0 * gap_max, 2.0 * join_gap)
    # Solo bóvedas compactas (símbolos): un clúster alargado de otra capa de
    # trazos no infla el puente ni une huecos que no son de ESTA capa.
    compact = _compact_vaults(vaults)
    vmax = max((v.radius * 2 for v in compact), default=0.0)
    vault_bridge = min(max(1.5 * vmax + join_gap, glyph_bridge),
                       LOOP_VAULT_MAX_PT + join_gap)
    corner_tol = max(2.5 * gap_max, 2.0 * letter, 10.0)
    return Pattern(dash_long, dash_short, gap_max, letter, join_gap,
                   glyph_bridge, vault_bridge, corner_tol)


# ─────────────────────────── 3. rectas ───────────────────────────
def group_collinear(dashes: Sequence[Dash]) -> List[_Group]:
    """Cada guión va al grupo que MEJOR ajusta (menor offset), no al primero
    que lo acepta: una línea con deriva de 1–2 pt genera dos semillas casi
    coincidentes y, con "el primero que acepta", se repartían los guiones
    intercalados → dos corridas superpuestas sobre la misma línea."""
    groups: List[_Group] = []
    for d in sorted(dashes, key=lambda x: -x.length):   # semilla = guión más largo
        best, best_e = None, None
        for g in groups:
            e = g.fit_error(d)
            if e is not None and (best_e is None or e < best_e):
                best, best_e = g, e
        if best is None:
            groups.append(_Group(d))
        else:
            best.dashes.append(d)
    return groups


# ─────────────────────────── 4. corridas ───────────────────────────
def _evidence_in_gap(g: _Group, t0: float, t1: float, pts: Sequence[Pt], perp_tol: float) -> bool:
    return any(t0 < g.t(p) < t1 and g.perp(p) <= perp_tol for p in pts)


def _split_by_fit(r: Run, tol: float = RUN_FIT_TOL_PT) -> List[Run]:
    """Parte una corrida recta donde sus guiones se apartan más de `tol` del
    chord (Douglas-Peucker sobre los extremos de los guiones, en orden). Así
    la polilínea final sigue la línea de la capa con esa precisión y cualquier
    nodo proyectado sobre ella (T, convergencia) queda SOBRE los guiones."""
    if r.is_curve or len(r.dashes) < 2:
        return [r]
    pts = []
    for d in sorted(r.dashes, key=lambda d: r.param(d.mid)[0]):
        a, b = (d.a, d.b) if r.param(d.a)[0] <= r.param(d.b)[0] else (d.b, d.a)
        pts.extend([a, b])
    simp = _douglas_peucker(pts, tol)
    if len(simp) <= 2:
        return [r]
    # Índices de corte: cada punto de `simp` es un extremo de guión en `pts`.
    cuts = [0]
    j = 0
    for q in simp[1:-1]:
        while j < len(pts) and _dist(pts[j], q) > 1e-9:
            j += 1
        if 0 < j < len(pts) - 1:
            cuts.append(j)
    cuts.append(len(pts) - 1)
    out = []
    for k0, k1 in zip(cuts, cuts[1:]):
        a, b = pts[k0], pts[k1]
        # guiones cuyo punto medio cae entre a y b (a lo largo del chord original)
        ta, tb = r.param(a)[0], r.param(b)[0]
        dashes = [d for d in r.dashes if ta - 1e-9 <= r.param(d.mid)[0] <= tb + 1e-9]
        if not dashes:
            continue
        ux, uy = _unit(b[0] - a[0], b[1] - a[1])
        out.append(Run(a, b, ux, uy, dashes, origin=r.origin))
    return out or [r]


def _compact_vaults(vaults: Sequence[Vault]) -> List[Vault]:
    """Símbolos de bóveda (caja compacta). Un clúster alargado no puentea huecos."""
    out = []
    for v in vaults:
        long = max(v.x1 - v.x0, v.y1 - v.y0)
        short = max(min(v.x1 - v.x0, v.y1 - v.y0), 1e-6)
        if long <= LOOP_VAULT_MAX_PT and long / short <= 4.0:
            out.append(v)
    return out


def build_runs(groups: List[_Group], pat: Pattern, glyphs: Sequence[Glyph],
               vaults: Sequence[Vault], curves: Sequence[List[Pt]] = ()) -> List[Run]:
    glyph_pts = [(gl.cx, gl.cy) for gl in glyphs]
    compact = _compact_vaults(vaults)
    vault_pts = [v.center for v in compact]
    vault_perp = max((v.radius for v in compact), default=0.0) + pat.join_gap
    runs: List[Run] = []
    for g in groups:
        ivs = sorted(g.intervals(), key=lambda iv: iv[0])

        def make_run(chunk: List[Tuple[float, float, Dash]]):
            a_iv = min(chunk, key=lambda iv: iv[0])
            b_iv = max(chunk, key=lambda iv: iv[1])
            a = a_iv[2].a if g.t(a_iv[2].a) <= g.t(a_iv[2].b) else a_iv[2].b
            b = b_iv[2].b if g.t(b_iv[2].b) >= g.t(b_iv[2].a) else b_iv[2].a
            ux, uy = _unit(b[0] - a[0], b[1] - a[1])
            runs.append(Run(a, b, ux, uy, [iv[2] for iv in chunk]))

        cur: List[Tuple[float, float, Dash]] = []
        cur_end = -1e18   # fin (t) de la corrida en construcción
        for iv in ivs:
            if cur:
                gap = iv[0] - cur_end
                ok = gap <= pat.join_gap
                if not ok and gap <= pat.glyph_bridge:
                    ok = _evidence_in_gap(g, cur_end, iv[0], glyph_pts, pat.letter)
                if not ok and gap <= pat.vault_bridge:
                    ok = _evidence_in_gap(g, cur_end, iv[0], vault_pts, vault_perp)
                if not ok:
                    make_run(cur); cur = []; cur_end = -1e18
            cur.append(iv)
            cur_end = max(cur_end, iv[1])
        if cur:
            make_run(cur)
    for pts in curves:
        a, b = pts[0], pts[-1]
        ux, uy = _unit(b[0] - a[0], b[1] - a[1])
        runs.append(Run(a, b, ux, uy, [], list(pts[1:-1]),
                        _unit(pts[1][0] - a[0], pts[1][1] - a[1]),
                        _unit(b[0] - pts[-2][0], b[1] - pts[-2][1])))
    return runs


def merge_overlapping_runs(runs: List[Run], pat: Pattern) -> List[Run]:
    """Dos corridas rectas con el mismo rumbo, a ≤1.5 pt una de otra y con
    rangos que se solapan describen la MISMA línea (deriva repartida entre dos
    semillas): se funden en una sola corrida con la unión de sus guiones."""
    runs = list(runs)
    changed = True
    while changed:
        changed = False
        for i in range(len(runs)):
            ri = runs[i]
            if ri.is_curve:
                continue
            Li = ri.line("a")
            for j in range(i + 1, len(runs)):
                rj = runs[j]
                if rj.is_curve or _ang_diff(_line_angle(Li), _line_angle(rj.line("a"))) > COLLINEAR_ANG_DEG:
                    continue
                if _perp_line(Li, rj.a) > COLLINEAR_PERP_PT or _perp_line(Li, rj.b) > COLLINEAR_PERP_PT:
                    continue          # más lejos = paralelas distintas (nunca se funden)
                ta, _ = ri.param(rj.a); tb, _ = ri.param(rj.b)
                lo, hi = min(ta, tb), max(ta, tb)
                overlap = (min(hi, 1.0) - max(lo, 0.0)) * ri.length
                if overlap < 0.5 * pat.dash_long:
                    continue
                # Unión: extremos más alejados sobre el rumbo de la corrida más larga.
                base = ri if ri.length >= rj.length else rj
                Lb = base.line("a")
                pts = [ri.a, ri.b, rj.a, rj.b]
                ts = [((p[0] - Lb[0]) * Lb[2] + (p[1] - Lb[1]) * Lb[3]) for p in pts]
                a = _foot_on(Lb, pts[ts.index(min(ts))]); b = _foot_on(Lb, pts[ts.index(max(ts))])
                ux, uy = _unit(b[0] - a[0], b[1] - a[1])
                runs[i] = Run(a, b, ux, uy, ri.dashes + rj.dashes)
                del runs[j]
                changed = True
                break
            if changed:
                break
    return runs


def _run_pts(r: Run) -> List[Pt]:
    return [r.a] + list(r.mid) + [r.b]


def _near_run(p: Pt, r: Run, tol: float) -> bool:
    """Extremo, codo o interior de la corrida (no solo sus puntas)."""
    pts = _run_pts(r)
    return any(_pt_seg_dist(p, u, v) <= tol for u, v in zip(pts, pts[1:]))


def _glyph_bridges_end(r: Run, side: str, anchors: Sequence[Run],
                       glyphs: Sequence[Glyph], pat: Pattern) -> bool:
    """El extremo sigue una corrida de patrón casi colineal y hay letra en el
    hueco (la misma evidencia que `build_runs`). No alarga más allá del trazo."""
    pe = r.a if side == "a" else r.b
    L = r.line(side)
    o = (-L[2], -L[3]) if side == "a" else (L[2], L[3])
    glyph_pts = [(g.cx, g.cy) for g in glyphs]
    for a in anchors:
        if a is r or not a.dashes:
            continue
        La = a.line("a")
        if _ang_diff(_line_angle(L), _line_angle(La)) > COLLINEAR_ANG_DEG:
            continue
        if _perp_line(La, pe) > COLLINEAR_PERP_PT:
            continue
        for q in (a.a, a.b):
            d = _dist(pe, q)
            if d < 1e-6 or d > pat.glyph_bridge:
                continue
            if (q[0] - pe[0]) * o[0] + (q[1] - pe[1]) * o[1] < 0.866 * d:
                continue
            if _perp_line(L, q) > COLLINEAR_PERP_PT:
                continue
            if any(_pt_seg_dist(g, pe, q) <= pat.letter for g in glyph_pts):
                return True
    return False


def split_offpattern(runs: List[Run], pat: Pattern,
                     vaults: Sequence[Vault] = (),
                     glyphs: Sequence[Glyph] = ()) -> Tuple[List[Run], List[Polyline]]:
    """Separa las corridas con patrón de las que son un solo trazo continuo largo.

    La utilidad se plotea con el linetype explotado. Un guión cuenta hasta
    2× el guión largo (uno un poco más largo no es un leader). Un ramal de
    ESTA capa se conserva si UN extremo toca otra corrida (punta, codo o
    interior) o hay letra en el hueco colineal. El otro extremo queda libre.
    Un trazo continuo solo, largo y sin contacto con la red, es leader."""
    limit = OFFPATTERN_FACTOR * pat.dash_long
    pattern_max = PATTERN_DASH_FACTOR * pat.dash_long
    tiny = 0.5 * (pat.dash_short or pat.dash_long * 0.3)
    keep: List[Run] = []
    off_runs: List[Run] = []
    for r in runs:
        if len(r.dashes) == 1 and r.length < tiny:
            continue                      # remate de flecha / basura: ni línea ni ancla
        # Con patrón = al menos dos guiones del tamaño del patrón (hasta 2×).
        # Un trazo continuo largo más un remate colineal no cuenta.
        n_pattern = sum(1 for d in r.dashes if MIN_DASH_PT <= d.length <= pattern_max)
        (keep if n_pattern >= 2 or r.length <= limit else off_runs).append(r)
    # Anclas: corridas de la red y codos cortos de la misma capa. Un remate de
    # flecha (3 pt) no valida un leader.
    anchors = [r for r in keep if (
        sum(1 for d in r.dashes if MIN_DASH_PT <= d.length <= pattern_max) >= 2
        or r.length >= 0.8 * pat.dash_long
        or (r.is_curve and r.length <= pat.corner_tol))]
    vboxes = [v.bbox(pat.corner_tol) for v in vaults]
    in_vault = lambda q: any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in vboxes)

    def touches(r: Run, side: str) -> bool:
        p = r.a if side == "a" else r.b
        if any(_near_run(p, a, pat.corner_tol) for a in anchors):
            return True
        return _glyph_bridges_end(r, side, anchors, glyphs, pat)

    off: List[Polyline] = []
    for r in off_runs:
        # Ramal: basta UN extremo. Leader: ninguno toca la red ni hay letra.
        if touches(r, "a") or touches(r, "b") or in_vault(r.a) or in_vault(r.b):
            r.continuous = True
            keep.append(r)
        else:
            pts = _run_pts(r)
            off.append(Polyline(pts, ["end"] + ["curve"] * len(r.mid) + ["end"]))
    return keep, off


# ─────────────────────────── 5. nodos ───────────────────────────
def _is_closed_shape(path: dict) -> bool:
    """Círculo, rectángulo o polilínea cerrada (manhole, cajita, punto de centro).
    También una «U» (rectángulo de 3 lados, como dibuja el DU06 varias bóvedas
    en C-ELEC-VALT-E): ≥3 tramos que giran siempre al mismo lado ~180° y cuyos
    extremos quedan a menos de un lado del bbox (el 4.º lado está implícito)."""
    items = path.get("items") or []
    if any(it[0] in ("c", "re", "qu") for it in items) or path.get("closePath"):
        return True
    chains = _path_chains(path)
    if not chains or len(chains[0]) < 4:
        return False
    ch = chains[0]
    if _dist(ch[0], ch[-1]) <= 0.5:
        return True
    signed = 0.0
    for i in range(1, len(ch) - 1):
        u1 = _unit(ch[i][0] - ch[i - 1][0], ch[i][1] - ch[i - 1][1])
        u2 = _unit(ch[i + 1][0] - ch[i][0], ch[i + 1][1] - ch[i][1])
        signed += math.degrees(math.atan2(u1[0] * u2[1] - u1[1] * u2[0], u1[0] * u2[0] + u1[1] * u2[1]))
    xs = [q[0] for q in ch]; ys = [q[1] for q in ch]
    long = max(max(xs) - min(xs), max(ys) - min(ys))
    return abs(signed) >= 150.0 and _dist(ch[0], ch[-1]) <= 1.05 * long


def _vault_reference(paths: Sequence[dict], bb: Tuple[float, float, float, float]) -> Optional[Pt]:
    """Centro de la forma cerrada MÁS PEQUEÑA del clúster (manhole circular,
    cajita de tiro, marca de centro), siempre que quede dentro del bbox."""
    best = None
    for p in paths:
        pb = _path_bbox(p)
        if pb is None or not _is_closed_shape(p):
            continue
        w, h = pb[2] - pb[0], pb[3] - pb[1]
        size = max(w, h)
        if size < 2.0:
            continue                      # marcas/ticks del perímetro: no son la referencia
        # Debe estar dentro del bbox del clúster y ser estrictamente más chica
        # que el contorno exterior (si es el contorno mismo, no es referencia).
        if size >= 0.95 * max(bb[2] - bb[0], bb[3] - bb[1]) and len(paths) > 1:
            continue
        cx, cy = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
        if not (bb[0] - 0.5 <= cx <= bb[2] + 0.5 and bb[1] - 0.5 <= cy <= bb[3] + 0.5):
            continue
        if best is None or size < best[0]:
            best = (size, (cx, cy))
    return best[1] if best else None


def cluster_vaults(paths: Sequence[dict]) -> List[Vault]:
    """Paths de las capas de bóvedas → una Vault por símbolo compacto.

    Solo entran formas cerradas compactas (caja/círculo). El linetype explotado
    (guiones abiertos) se descarta antes de agrupar, así no infla el bbox de un
    símbolo vecino ni atrae extremos. Las capas de buzones (VALT, MANH, …) sí
    pueden agruparse entre sí: son el mismo nodo físico.
    """
    candidates = []
    for p in paths:
        bb = _path_bbox(p)
        if bb is None or not _is_closed_shape(p):
            continue
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        long, short = max(w, h), max(min(w, h), 1e-6)
        if long / short > 4.0 or long > LOOP_VAULT_MAX_PT:
            continue
        candidates.append(p)
    out = _cluster_vaults_layer(candidates)
    out.sort(key=lambda v: (v.y0, v.x0))
    return out


def _cluster_vaults_layer(paths: Sequence[dict]) -> List[Vault]:
    boxes = [_path_bbox(p) for p in paths]
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if (a[0] - VAULT_CLUSTER_PT <= b[2] and b[0] - VAULT_CLUSTER_PT <= a[2]
                    and a[1] - VAULT_CLUSTER_PT <= b[3] and b[1] - VAULT_CLUSTER_PT <= a[3]):
                parent[find(i)] = find(j)
    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(boxes)):
        groups[find(i)].append(i)
    out = []
    for idxs in groups.values():
        bbs = [boxes[i] for i in idxs]
        bb = (min(b[0] for b in bbs), min(b[1] for b in bbs),
              max(b[2] for b in bbs), max(b[3] for b in bbs))
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        long, short = max(w, h), max(min(w, h), 1e-6)
        cluster = [paths[i] for i in idxs]
        closed = any(_is_closed_shape(p) for p in cluster)
        # Guión / linetype: alargado, o sin caja/círculo (un trazo abierto).
        if long / short > 4.0 or long > LOOP_VAULT_MAX_PT or not closed:
            continue
        ref = _vault_reference(cluster, bb)
        out.append(Vault(*bb, len(bbs), ref))
    return out


def detect_loop_vaults(runs: List[Run], pat: Pattern) -> Tuple[List[Vault], Set[int]]:
    """Bóvedas dibujadas en la PROPIA capa de líneas (caso «abandonada»: el
    plot pone el contorno de la bóveda en C-ELEC-UNGD-A con el mismo linetype).
    Un lazo cerrado de 4 corridas rectas, perpendiculares entre sí, con
    esquinas que se tocan y lados entre LOOP_VAULT_MIN_PT y LOOP_VAULT_MAX_PT
    no es red: es el símbolo. Devuelve las Vault nuevas y los índices de las
    corridas que forman cada lazo (se descartan como línea)."""
    tol = max(4.0, pat.gap_max)
    straight = [i for i, r in enumerate(runs) if not r.is_curve and not r.synthetic
                and LOOP_VAULT_MIN_PT - tol <= r.length <= LOOP_VAULT_MAX_PT + tol]
    ends = [(i, "a", runs[i].a) for i in straight] + [(i, "b", runs[i].b) for i in straight]

    def near(p: Pt, exclude: Set[int]):
        for j, side, q in ends:
            if j not in exclude and _dist(p, q) <= tol:
                yield j, side

    def other(j: int, side: str) -> Pt:
        return runs[j].b if side == "a" else runs[j].a

    def perpendicular(i: int, j: int) -> bool:
        return _ang_diff(_line_angle(runs[i].line("a")), _line_angle(runs[j].line("a"))) >= 90.0 - CORNER_MIN_ANG_DEG

    found: Dict[frozenset, List[Pt]] = {}
    for i in straight:
        start, cur = runs[i].a, runs[i].b
        corners = [start, cur]
        # caminar i → j → k → l y volver al inicio
        for j, sj in near(cur, {i}):
            if not perpendicular(i, j):
                continue
            pj = other(j, sj)
            for k, sk in near(pj, {i, j}):
                if not perpendicular(j, k):
                    continue
                pk = other(k, sk)
                for l, sl in near(pk, {i, j, k}):
                    if not perpendicular(k, l) or _dist(other(l, sl), start) > tol:
                        continue
                    key = frozenset((i, j, k, l))
                    if key not in found:
                        found[key] = corners + [pj, pk]
    vaults: List[Vault] = []
    drop: Set[int] = set()
    for key, pts in found.items():
        if key & drop:
            continue
        x0, x1 = min(q[0] for q in pts), max(q[0] for q in pts)
        y0, y1 = min(q[1] for q in pts), max(q[1] for q in pts)
        if not (LOOP_VAULT_MIN_PT <= x1 - x0 <= LOOP_VAULT_MAX_PT and LOOP_VAULT_MIN_PT <= y1 - y0 <= LOOP_VAULT_MAX_PT):
            continue
        vaults.append(Vault(x0, y0, x1, y1, len(key)))
        drop |= key
    return vaults, drop


def _line_bbox_hits(p: Pt, u: Tuple[float, float], bb: Tuple[float, float, float, float]) -> Optional[Tuple[float, float]]:
    """Recta infinita p + t·u contra un bbox: (t_entrada, t_salida) o None."""
    t0, t1 = -1e18, 1e18
    for pp, q in ((-u[0], p[0] - bb[0]), (u[0], bb[2] - p[0]), (-u[1], p[1] - bb[1]), (u[1], bb[3] - p[1])):
        if abs(pp) < 1e-12:
            if q < 0:
                return None
            continue
        t = q / pp
        if pp < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (t0, t1)


def resolve_nodes(runs: List[Run], pat: Pattern, vaults: Sequence[Vault],
                  cut_pts: Sequence[Pt] = ()) -> Tuple[List[Node], List[int]]:
    """Asigna nodos a extremos e inserta vértices interiores.
    Devuelve (nodos, índices de bóvedas huérfanas)."""
    nodes: List[Node] = []
    free: Dict[Tuple[int, str], bool] = {(i, s): True for i in range(len(runs)) for s in ("a", "b")}

    def endpoint(i: int, side: str) -> Pt:
        return runs[i].a if side == "a" else runs[i].b

    def outward(i: int, side: str) -> Tuple[float, float]:
        L = runs[i].line(side)
        return (-L[2], -L[3]) if side == "a" else (L[2], L[3])

    def set_endpoint(i: int, side: str, p: Pt, node_idx: int):
        r = runs[i]
        if side == "a":
            r.a = p; r.node_a = node_idx
        else:
            r.b = p; r.node_b = node_idx
        free[(i, side)] = False

    def new_node(p: Pt, kind: str, vi: int = -1) -> int:
        for k, n in enumerate(nodes):          # mismo punto visto desde otra corrida
            if _dist((n.x, n.y), p) <= 0.5:
                if kind in ("vault", "junction") and n.kind != "vault":
                    n.kind = kind
                return k
        nodes.append(Node(p[0], p[1], kind, vi))
        return len(nodes) - 1

    def slide_ok(i: int, side: str, P: Pt) -> bool:
        """Deslizar el extremo `side` hasta P no puede tragarse más de media
        corrida (si no, un tick o un guión corto colapsa o se da vuelta)."""
        r = runs[i]
        if r.is_curve:
            return True
        t, _ = r.param(P)
        return t <= 0.5 if side == "a" else t >= 0.5

    def attach(i: int, side: str, P: Pt, node_idx: int) -> bool:
        """Lleva el extremo a P deslizándolo por su propia recta. False si P
        no está sobre esa recta (la corrida no se inclina)."""
        L = runs[i].line(side)
        if _perp_line(L, P) > NODE_OFF_LINE_PT:
            return False
        set_endpoint(i, side, _foot_on(L, P) if not runs[i].is_curve else P, node_idx)
        return True

    # — 5a. bóvedas: quiebre en el borde + tramo a la referencia —
    # Regla del usuario: la línea llega a la bóveda por su propia recta hasta el
    # BORDE (vértice de quiebre) y desde ahí un tramo al punto de referencia
    # (manhole / cajita). Nunca se inclina la corrida. Si un stub no "apunta"
    # a la referencia (bóveda grande, entrada lejos), se deja en el borde y el
    # usuario completa a mano.
    for i, r in enumerate(runs):
        if r.origin < 0:
            r.origin = i

    # Fase A: partir en el borde las corridas que ATRAVIESAN una bóveda.
    for vi, v in enumerate(vaults):
        bb = v.bbox(1.0)
        i = 0
        while i < len(runs):
            r = runs[i]
            if r.is_curve or r.synthetic:
                i += 1; continue
            rng = _segment_bbox_range(r, bb)
            if rng is None:
                i += 1; continue
            # Atraviesa si entra y SALE del bbox dejando un trozo real a cada
            # lado (≥ medio guión corto). Un extremo que solo asoma dentro de
            # la bóveda (rng toca 0 o 1) no es un cruce: lo trata la Fase B.
            stub = max(2.0, 0.5 * (pat.dash_short or 0.3 * pat.dash_long)) / max(r.length, 1e-9)
            if not (rng[0] > stub and rng[1] < 1.0 - stub):
                i += 1; continue
            E1, E2 = r.at(rng[0]), r.at(rng[1])
            da = [d for d in r.dashes if r.param(d.mid)[0] <= rng[0]]
            db = [d for d in r.dashes if r.param(d.mid)[0] >= rng[1]]
            r1 = Run(r.a, E1, r.ux, r.uy, da, origin=r.origin, split=True)
            r2 = Run(E2, r.b, r.ux, r.uy, db, origin=r.origin, split=True)
            runs[i] = r1
            runs.insert(i + 1, r2)
            i += 2
    free.clear()
    free.update({(i, s): True for i in range(len(runs)) for s in ("a", "b")})

    # — T-ends: un extremo que muere SOBRE otra corrida recta (a ≤NODE_OFF_LINE_PT
    #   de su recta y en su interior) es una T con ESA corrida: no llega a una
    #   bóveda vecina, no forma esquina con un tercer extremo ni se prolonga
    #   hacia otro sitio (hoja 9: diagonal que muere sobre la horizontal,
    #   horizontal que muere sobre el tick «|» de fin de tramo, ramal
    #   abandonado que nace sobre su propia línea junto a la bóveda activa).
    def _interior(r: Run, t: float) -> bool:
        m = min(0.5 * pat.join_gap, 0.25 * r.length) / max(r.length, 1e-9)
        return m < t < 1.0 - m

    t_end: Dict[Tuple[int, str], Tuple[int, float]] = {}
    all_ends = [(k, side, endpoint(k, side), outward(k, side)) for (k, side) in free]
    for (i, s) in list(free):
        pe = endpoint(i, s)
        best = None
        for j, r in enumerate(runs):
            if j == i or r.is_curve or r.synthetic or r.origin == runs[i].origin:
                continue
            t, perp = r.param(pe)
            if perp <= NODE_OFF_LINE_PT and _interior(r, t) and (best is None or perp < best[0]):
                best = (perp, j, t)
        if best is None:
            continue
        j = best[1]
        Li = runs[i].line(s)
        o = outward(i, s)
        # Dos corridas casi paralelas y encimadas (doble trazo) no son una T:
        # el otro extremo de i también cae sobre la recta de j.
        if _ang_diff(_line_angle(Li), _line_angle(runs[j].line("a"))) < CORNER_MIN_ANG_DEG:
            other_end = runs[i].b if s == "a" else runs[i].a
            if runs[j].param(other_end)[1] <= 2 * NODE_OFF_LINE_PT:
                continue
        # Si otro extremo (que no sea de esa misma corrida) muere pegado a este,
        # o continúa colineal delante de él dentro del hueco del patrón (la
        # línea sigue: cruce en X con hueco), es continuación/esquina, no T.
        cont = False
        for k, _, q, oq in all_ends:
            if k in (i, j):
                continue
            d = _dist(q, pe)
            if d <= 2 * NODE_OFF_LINE_PT:
                cont = True
                break
            # …colineal, delante, y MIRÁNDOSE (el otro trozo apunta hacia este):
            # así no cuenta el extremo de una línea paralela vecina.
            if d <= pat.join_gap and _perp_line(Li, q) <= 2 * NODE_OFF_LINE_PT                     and (q[0] - pe[0]) * o[0] + (q[1] - pe[1]) * o[1] >= 0.866 * d                     and (pe[0] - q[0]) * oq[0] + (pe[1] - q[1]) * oq[1] >= 0.866 * d:
                cont = True
                break
        if cont:
            continue
        t_end[(i, s)] = (j, best[2])
    # Tick «|» de fin de tramo: guión corto y solo sobre el que muere otra
    # corrida. Sus propios extremos son EXTREMOS: no forman esquina ni T con
    # nada ni se prolongan (hoja 9: el ramal que pasa a 4 pt de su punta
    # nunca se une a él).
    short = 2.5 * (pat.dash_short or 0.3 * pat.dash_long)
    capped = {j for j, _ in t_end.values()
              if len(runs[j].dashes) == 1 and not runs[j].continuous and runs[j].length <= short}

    # Fase B: extremos que llegan a una bóveda.
    # Reglas del usuario (apuntes + revisión):
    #   · SIEMPRE un vértice donde la línea choca con el borde (entrada y salida).
    #   · Dentro de la bóveda no se inventa nada a partir del símbolo (círculo,
    #     cajita): el nodo interior se calcula SOLO con las líneas de red que
    #     llegan (≥MIN_JUNCTION_DASHES guiones): intersección de sus propias
    #     rectas; si no concurren exactamente, un quiebre extra para que cada una
    #     siga su eje hasta donde más se acerca al nodo.
    #   · Si llega una sola línea (o solo stubs/curvas), cada una termina en el
    #     borde y ahí queda su caja ("stop"): sin referencia no se dibuja.
    orphans: List[int] = []
    for vi, v in enumerate(vaults):
        bb = v.bbox(1.0)
        reach = pat.join_gap
        bb_reach = v.bbox(reach)
        ends = [(i, s) for (i, s), fr in free.items() if fr and (i, s) not in t_end
                and bb_reach[0] <= endpoint(i, s)[0] <= bb_reach[2]
                and bb_reach[1] <= endpoint(i, s)[1] <= bb_reach[3]]
        if not ends:
            orphans.append(vi)
            continue

        def entry_point(i: int, s: str):
            """(E, |desplazamiento|) donde la recta del extremo toca el borde, o
            None si la bóveda queda claramente detrás / de costado."""
            r = runs[i]
            L = r.line(s)
            pe = endpoint(i, s)
            o = outward(i, s)
            hits = _line_bbox_hits(pe, o, bb)
            if hits is None:
                c = v.center
                to_c = _unit(c[0] - pe[0], c[1] - pe[1])
                if o[0] * to_c[0] + o[1] * to_c[1] < math.cos(math.radians(45.0)):
                    return None
                corners = ((v.x0, v.y0), (v.x1, v.y0), (v.x0, v.y1), (v.x1, v.y1))
                pad = min(_perp_line(L, cc) for cc in corners) + 1.0
                hits = _line_bbox_hits(pe, o, v.bbox(pad))
            if hits is None:
                return None
            if hits[1] < 0:                       # bóveda detrás del extremo
                if -hits[1] > reach:
                    return None
                t = hits[1]                       # sobrepaso corto: recortar al cruce cercano
            else:
                t = hits[0]                       # primer cruce hacia adelante
            return (pe[0] + t * o[0], pe[1] + t * o[1]), abs(t)

        # Un solo extremo por corrida: el que menos hay que mover para tocar el borde.
        best_by_run: Dict[int, Tuple[float, str, Pt]] = {}
        beside: List[Tuple[int, str]] = []
        for i, s in ends:
            ep = entry_point(i, s)
            if ep is None:
                beside.append((i, s))
                continue
            E, move = ep
            if i not in best_by_run or move < best_by_run[i][0]:
                best_by_run[i] = (move, s, E)
        # Los extremos que mueren junto a la bóveda sin entrar quedan LIBRES: las
        # pasadas de esquina/T los conectan a lo que haya (p.ej. un stub que
        # muere sobre la vertical justo debajo del borde).

        arrivals = [(i, s, E) for i, (_, s, E) in best_by_run.items()]
        limit = OFFPATTERN_FACTOR * pat.dash_long
        # "Línea de red" (define el nodo) vs stub: se mide sobre TODA la corrida
        # original (los trozos partidos por ajuste comparten `origin`), o por
        # longitud si es una transición continua larga.
        def is_strong(i: int) -> bool:
            """Línea de red = la CADENA alcanzable por extremos cercanos (≤ hueco
            del patrón) suma ≥3 guiones o ≥3 guiones largos de longitud. Un
            guión inclinado suelto que solo es la cola de una línea larga cuenta
            con toda la línea, no solo con él."""
            if runs[i].split:
                return True
            seen, stack, n_d, n_l = {i}, [i], 0, 0.0
            while stack:
                k = stack.pop()
                rk = runs[k]
                n_d += sum(1 for d in rk.dashes if d.length <= limit)
                n_l += rk.length
                if n_d >= MIN_JUNCTION_DASHES or n_l >= 3.0 * pat.dash_long:
                    return True
                for j, rj in enumerate(runs):
                    if j in seen or rj.synthetic:
                        continue
                    # Solo continúa por extremos que quedan EN LA DIRECCIÓN del eje
                    # (cono ±45°); dos stubs paralelos vecinos no se suman entre sí.
                    linked = False
                    for e1, d1 in ((rk.a, (-rk.ux, -rk.uy)), (rk.b, (rk.ux, rk.uy))):
                        for e2 in (rj.a, rj.b):
                            dd = _dist(e1, e2)
                            if dd <= reach and (dd < 1e-6 or
                                    ((e2[0] - e1[0]) * d1[0] + (e2[1] - e1[1]) * d1[1]) >= 0.7 * dd):
                                linked = True
                    if linked:
                        seen.add(j); stack.append(j)
            return False

        strong = [(i, s, E) for i, s, E in arrivals if is_strong(i)]
        # Dos llegadas colineales por lados OPUESTOS (los guiones se interrumpen
        # dentro por el símbolo) son la misma línea que atraviesa — cuenta aunque
        # una de las dos sea un stub corto (imagen 2 del usuario). Un trazo
        # CONTINUO (sin patrón) que solo NACE en el borde y sale hacia afuera
        # (caso abandonada, hoja 9) no cuenta: es otra conexión, no la línea que
        # sigue; sí cuenta si el trazo entra en la bóveda (transición que la
        # cruza, hoja 12).
        half_side = 0.5 * min(v.x1 - v.x0, v.y1 - v.y0)

        def enters(i: int) -> bool:
            rng = _segment_bbox_range(runs[i], bb)
            return rng is not None and (rng[1] - rng[0]) * runs[i].length >= half_side

        virtual_through: List[Line] = []
        pair_members: List[Tuple[int, str, Pt]] = []
        for x in range(len(arrivals)):
            for y in range(x + 1, len(arrivals)):
                (i1, s1, E1), (i2, s2, E2) = arrivals[x], arrivals[y]
                if any(runs[i].continuous and not enters(i) for i in (i1, i2)):
                    continue
                L1, L2 = runs[i1].line(s1), runs[i2].line(s2)
                if _ang_diff(_line_angle(L1), _line_angle(L2)) >= CORNER_MIN_ANG_DEG:
                    continue
                o1, o2 = outward(i1, s1), outward(i2, s2)
                opposite = o1[0] * o2[0] + o1[1] * o2[1] <= -math.cos(math.radians(CORNER_MIN_ANG_DEG))
                if opposite and _perp_line(L1, E2) <= 2 * NODE_OFF_LINE_PT:
                    virtual_through.append(L1)
                    pair_members += [arrivals[x], arrivals[y]]
        for m in pair_members:
            if m not in strong:
                strong.append(m)
        # Hay referencia para un nodo interior solo si alguna línea de red
        # ATRAVIESA la bóveda (cruce real, como en los apuntes: izquierda/arriba/
        # derecha). Si todas solo llegan y ninguna sigue del otro lado, no se
        # inventa nada: cada una para en el borde.
        has_through = any(runs[i].split for i, _, _ in strong) or bool(virtual_through)
        if has_through:
            # Nodo interior P a partir de las llegadas:
            #   · si ≥2 líneas ATRAVIESAN la bóveda → su intersección (P sobre ambas);
            #   · si 1 atraviesa → el punto sobre ella más cercano a donde concurren las demás;
            #   · si ninguna atraviesa → punto concurrente de las que llegan (o su promedio).
            # Las que atraviesan pasan derecho por P; las que llegan de un lado
            # siguen su eje hasta el pie y de ahí un quiebre corto a P.
            thr_lines: Dict[int, Line] = {}
            for i, s, _ in strong:
                if runs[i].split and runs[i].origin not in thr_lines:
                    thr_lines[runs[i].origin] = runs[i].line(s)
            for k, L in enumerate(virtual_through):
                thr_lines[-1 - k] = L
            all_lines = [runs[i].line(s) for i, s, _ in strong]
            Es = [E for _, _, E in strong]
            centroid = (sum(e[0] for e in Es) / len(Es), sum(e[1] for e in Es) / len(Es))
            P = None
            if len(thr_lines) >= 2:
                P = _concurrent_point(list(thr_lines.values()), centroid, v.radius + reach)
            if P is None and len(thr_lines) >= 1:
                Lt = next(iter(thr_lines.values()))
                Q = _concurrent_point(all_lines, centroid, v.radius + reach)
                P = _foot_on(Lt, Q if Q is not None else centroid)
            if P is None:
                P = _concurrent_point(all_lines, centroid, v.radius + reach)
            if P is None or not (bb_reach[0] <= P[0] <= bb_reach[2] and bb_reach[1] <= P[1] <= bb_reach[3]):
                P = centroid
            # Sin referencia suficiente = alguna línea tendría que recorrer dentro
            # de la bóveda más de 0.75 × su lado menor para llegar al nodo (p.ej.
            # una vertical que entra por abajo y curvas que salen por arriba de
            # una bóveda alta): entonces NO se inventa nada y todas paran en el borde.
            inner_max = math.hypot(v.x1 - v.x0, v.y1 - v.y0) + reach
            if any(_dist(E, P) > inner_max for E in Es):
                for i, s, E in arrivals:
                    set_endpoint(i, s, E, new_node(E, "stop", vi))
                continue
            node_P = new_node(P, "vault", vi)
            made: Dict[Tuple[int, int], int] = {}

            def synth(a_node: int, b_node: int, origin: int, cdir) -> None:
                if (a_node, b_node) in made:
                    return
                a, b = (nodes[a_node].x, nodes[a_node].y), (nodes[b_node].x, nodes[b_node].y)
                if _dist(a, b) < 1e-6:
                    return
                syn = Run(a, b, *_unit(b[0] - a[0], b[1] - a[1]), [], origin=origin, synthetic=True)
                syn.node_a, syn.node_b, syn.chain_dir = a_node, b_node, cdir
                runs.append(syn)
                free[(len(runs) - 1, "a")] = False; free[(len(runs) - 1, "b")] = False
                made[(a_node, b_node)] = len(runs) - 1

            for i, s, E in strong:
                r = runs[i]
                o = outward(i, s)
                edge = new_node(E, "edge")
                set_endpoint(i, s, E, edge)
                # Un solo tramo recto borde → nodo (imagen 1 del usuario: sin
                # quiebre intermedio aunque la recta no pase por el nodo).
                synth(edge, node_P, r.origin, o)
            for i, s, E in arrivals:
                if (i, s, E) not in strong:
                    set_endpoint(i, s, E, new_node(E, "stop", vi))
        else:
            # Una sola línea (o solo stubs/curvas): todas terminan en el borde.
            for i, s, E in arrivals:
                set_endpoint(i, s, E, new_node(E, "stop", vi))

    # Extremos creados por el clip del PDF: nodo 'cut' (duro), fuera de toda pareja.
    for (i, s), fr in list(free.items()):
        if fr:
            pe = endpoint(i, s)
            if any(_dist(pe, c) <= 0.5 for c in cut_pts):
                set_endpoint(i, s, pe, new_node(pe, "cut"))

    vault_reach_boxes = [v.bbox(pat.join_gap) for v in vaults]

    def near_vault(p: Pt) -> bool:
        return any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] for b in vault_reach_boxes)

    # — 5b. esquinas y quiebres suaves en UNA pasada voraz por distancia —
    # La pareja de extremos más cercana gana (así en un arco cada guión se une
    # con el siguiente y nunca "salta" uno). El tipo lo decide el ángulo entre
    # las rectas: ≥8° esquina (nodo = intersección), <8° quiebre suave
    # (nodo = punto medio). Nunca se promedian intersecciones de 3+ extremos:
    # un tercer ramal solo se suma si su recta pasa de verdad por el nodo.
    ends_free = [(i, s) for (i, s), fr in free.items() if fr and (i, s) not in t_end and i not in capped]
    pairs = []
    for x in range(len(ends_free)):
        for y in range(x + 1, len(ends_free)):
            e, f = ends_free[x], ends_free[y]
            if e[0] == f[0]:
                continue
            pe, pf = endpoint(*e), endpoint(*f)
            d = _dist(pe, pf)
            if d > 2 * pat.corner_tol:
                continue
            if runs[e[0]].continuous and runs[f[0]].continuous and not near_vault(pe):
                continue      # dos curvas/continuas que coinciden en la punta lejos de toda
                              # bóveda (p.ej. cortadas por el marco) NO son una esquina; junto
                              # a una bóveda sí (codo «⌒» + conduit)
            L1, L2 = runs[e[0]].line(e[1]), runs[f[0]].line(f[1])
            if _ang_diff(_line_angle(L1), _line_angle(L2)) >= CORNER_MIN_ANG_DEG:
                P = _isect(L1, L2)
                if P is None or _dist(P, pe) > pat.corner_tol or _dist(P, pf) > pat.corner_tol:
                    continue
                if not slide_ok(*e, P) or not slide_ok(*f, P):
                    continue
                pairs.append((d, e, f, P, "corner"))
            else:
                if d > pat.join_gap:
                    continue
                # Quiebre suave solo si el otro extremo está DELANTE (cono ±30°)
                # y casi sobre la misma recta: dos paralelas a 20 pt que terminan
                # a la misma altura NO son un quiebre.
                if _perp_line(L1, pf) > 2 * NODE_OFF_LINE_PT or _perp_line(L2, pe) > 2 * NODE_OFF_LINE_PT:
                    continue
                oe, of_ = outward(*e), outward(*f)
                cos30 = 0.866
                if d > 1.0 and (pf[0] - pe[0]) * oe[0] + (pf[1] - pe[1]) * oe[1] < cos30 * d:
                    continue      # (a ≤1 pt los extremos se solapan: el cono no dice nada)
                if d > 1.0 and (pe[0] - pf[0]) * of_[0] + (pe[1] - pf[1]) * of_[1] < cos30 * d:
                    continue
                pairs.append((d, e, f, ((pe[0] + pf[0]) / 2, (pe[1] + pf[1]) / 2), "bend"))
    pairs.sort(key=lambda t: t[0])
    corner_nodes: List[int] = []
    for _, e, f, P, kind in pairs:
        if not free[e] or not free[f]:
            continue
        node_idx = new_node(P, kind)
        if kind == "bend":
            set_endpoint(*e, P, node_idx); set_endpoint(*f, P, node_idx)
        else:
            attach(*e, P, node_idx); attach(*f, P, node_idx)
            corner_nodes.append(node_idx)
    # Un tercer ramal también puede morir sobre un quiebre suave de otra línea
    # (Y: una recta que llega justo al hueco entre dos guiones de un arco).
    attach_nodes = corner_nodes + [k for k, n in enumerate(nodes) if n.kind in ("stop", "vault", "bend")]
    for (i, s), fr in list(free.items()):          # tercer/cuarto ramal concurrente
        if not fr or (i, s) in t_end or i in capped:
            continue
        pe = endpoint(i, s)
        L = runs[i].line(s)
        other = runs[i].node_b if s == "a" else runs[i].node_a
        best = None
        for n in attach_nodes:
            if n == other:
                continue                            # una corrida no cierra bucle sobre sí misma
            P = (nodes[n].x, nodes[n].y)
            d = _dist(P, pe)
            reach = 0.5 * pat.join_gap if nodes[n].kind == "bend" else pat.corner_tol
            if (d <= reach and _perp_line(L, P) <= NODE_OFF_LINE_PT and slide_ok(i, s, P)
                    and (best is None or d < best[0])):
                best = (d, n)
        if best is not None:
            n = best[1]
            if nodes[n].kind in ("corner", "bend"):
                nodes[n].kind = "junction"
            attach(i, s, (nodes[n].x, nodes[n].y), n)

    # — 5c-bis. T-ends: se pegan a la corrida sobre la que mueren —
    for (i, s), (j, t) in t_end.items():
        if not free[(i, s)]:
            continue
        pe = endpoint(i, s)
        r = runs[j]
        Ls, Lb = runs[i].line(s), r.line("a")
        P = None
        if _ang_diff(_line_angle(Ls), _line_angle(Lb)) >= CORNER_MIN_ANG_DEG:
            P = _isect(Ls, Lb)                      # sigue su propia recta hasta cortar
            if P is not None and (_dist(P, pe) > pat.corner_tol or not slide_ok(i, s, P)):
                P = None
        if P is None:
            P = r.at(t)                             # rasante: pie sobre la corrida
        tj, _ = r.param(P)
        node_idx = -1
        for tt, n in r.inner:                       # otro ramal ya pegado en ese punto
            if abs(tt - tj) * r.length <= NODE_OFF_LINE_PT:
                node_idx = n
                P = (nodes[n].x, nodes[n].y)
                nodes[n].kind = "junction"
                break
        if node_idx < 0:                            # un nodo existente (esquina, T…) a ≤3 pt sobre j
            for n, nd in enumerate(nodes):
                q = (nd.x, nd.y)
                if _dist(q, P) <= NODE_OFF_LINE_PT and r.param(q)[1] <= NODE_OFF_LINE_PT                         and nd.kind not in ("vault", "stop", "edge", "cut"):
                    node_idx = n
                    P = q
                    nd.kind = "junction"
                    tj, _ = r.param(P)
                    if n not in (r.node_a, r.node_b) and not any(nn == n for _, nn in r.inner):
                        r.inner.append((tj, n))
                    break
        if node_idx < 0:
            node_idx = new_node(P, "tee")
            r.inner.append((tj, node_idx))
        set_endpoint(i, s, P, node_idx)

    # — 5d. T: extremo libre cuya recta corta el interior de otra corrida recta —
    for (i, s), fr in list(free.items()):
        if not fr or i in capped:
            continue
        pe = endpoint(i, s)
        Ls = runs[i].line(s)
        best = None
        for j, r in enumerate(runs):
            if j == i or r.is_curve:
                continue
            Lb = r.line("a")
            if _ang_diff(_line_angle(Ls), _line_angle(Lb)) < CORNER_MIN_ANG_DEG:
                continue
            P = _isect(Ls, Lb)
            if P is None or _dist(P, pe) > pat.corner_tol or not slide_ok(i, s, P):
                continue
            t, _ = r.param(P)
            margin = pat.join_gap / max(r.length, 1e-9)
            if margin < t < 1.0 - margin:
                d = _dist(P, pe)
                if best is None or d < best[0]:
                    best = (d, j, t, P)
        if best is None:
            continue
        _, j, t, P = best
        node_idx = new_node(P, "tee")
        if not any(abs(tt - t) < 1e-6 for tt, _ in runs[j].inner):
            runs[j].inner.append((t, node_idx))
        set_endpoint(i, s, P, node_idx)

    # — 5d-bis. convergencia rasante: un extremo libre que muere a ≤3 pt de
    # otra corrida con ángulo casi paralelo (dos conduits que se juntan) nace
    # de ella: vértice compartido sobre esa corrida, nunca dos líneas casi
    # encimadas sin unión.
    for (i, s), fr in list(free.items()):
        if not fr or i in capped:
            continue
        pe = endpoint(i, s)
        Ls = runs[i].line(s)
        best = None
        for j, r in enumerate(runs):
            if j == i or r.is_curve or r.synthetic or r.origin == runs[i].origin:
                continue
            if _ang_diff(_line_angle(Ls), _line_angle(r.line("a"))) >= CORNER_MIN_ANG_DEG:
                continue
            t, perp = r.param(pe)
            margin = pat.join_gap / max(r.length, 1e-9)
            if perp <= NODE_OFF_LINE_PT and margin < t < 1.0 - margin:
                if best is None or perp < best[0]:
                    best = (perp, j, t)
        if best is None:
            continue
        _, j, t = best
        P = runs[j].at(t)
        node_idx = new_node(P, "tee")
        if not any(abs(tt - t) < 1e-6 for tt, _ in runs[j].inner):
            runs[j].inner.append((t, node_idx))
        set_endpoint(i, s, P, node_idx)

    # — 5e. extremos sueltos —
    for (i, s), fr in free.items():
        if fr:
            p = endpoint(i, s)
            set_endpoint(i, s, p, new_node(p, "end"))
    return nodes, orphans


# ─────────────────────────── 6. polilíneas ───────────────────────────
def assemble(runs: List[Run], nodes: List[Node]) -> List[Polyline]:
    """Encadena corridas a través de nodos de grado 2 (esquina, bóveda, quiebre)
    y corta en nodos de grado ≥3 (junction / T): el vértice queda compartido."""
    incident: Dict[int, List[Tuple[int, str]]] = defaultdict(list)
    for i, r in enumerate(runs):
        incident[r.node_a].append((i, "a"))
        incident[r.node_b].append((i, "b"))
        for _, n in r.inner:
            incident[n].append((i, "inner"))

    def run_vertices(i: int, forward: bool) -> Tuple[List[Pt], List[str]]:
        r = runs[i]
        pts = [(nodes[r.node_a].x, nodes[r.node_a].y)]
        kinds = [nodes[r.node_a].kind]
        if r.is_curve:
            pts += list(r.mid); kinds += ["curve"] * len(r.mid)
        else:
            for _, n in sorted(r.inner):
                pts.append((nodes[n].x, nodes[n].y)); kinds.append(nodes[n].kind)
        pts.append((nodes[r.node_b].x, nodes[r.node_b].y)); kinds.append(nodes[r.node_b].kind)
        return (pts, kinds) if forward else (pts[::-1], kinds[::-1])

    def out_dir(i: int, side: str) -> Tuple[float, float]:
        """Dirección saliente de la corrida i por su extremo `side`. En un tramo
        sintético (borde→referencia) es el rumbo de la línea que entra."""
        r = runs[i]
        if r.synthetic and r.chain_dir is not None:
            return r.chain_dir if side == "b" else (-r.chain_dir[0], -r.chain_dir[1])
        L = r.line(side)
        return (-L[2], -L[3]) if side == "a" else (L[2], L[3])

    def chain_next(node_idx: int, cur: int) -> Optional[Tuple[int, str]]:
        inc = incident[node_idx]
        kind = nodes[node_idx].kind
        ends = [(j, s) for j, s in inc if s != "inner"]
        if len(inc) == 2 and len(ends) == 2 and kind in CHAIN_KINDS:
            nxt = [(j, s) for j, s in ends if j != cur]
            return nxt[0] if nxt else None
        # Nodo compartido (bóveda / junction) con varias corridas: la línea sigue
        # derecho solo hacia la ÚNICA corrida colineal y de sentido contrario
        # (como la trazaría a mano: una polilínea que atraviesa la bóveda).
        if kind not in ("vault", "junction"):
            return None
        mine = [(j, s) for j, s in ends if j == cur]
        if len(mine) != 1:
            return None
        # Las dos mitades de una corrida partida en la bóveda (mismo origen)
        # se siguen entre sí: la línea que atraviesa es UNA polilínea.
        same = [(j, s) for j, s in ends if j != cur and runs[j].origin == runs[cur].origin >= 0]
        if len(same) == 1:
            return same[0]
        ux, uy = out_dir(*mine[0])
        if len(ends) == 2 and not any(s == "inner" for _, s in inc):
            # Dos líneas que se encuentran en la bóveda: una sola polilínea solo si
            # el giro es moderado (≤45°); un giro brusco son dos conduits distintos.
            nxt = [(j, s) for j, s in ends if j != cur]
            if nxt:
                vx, vy = out_dir(*nxt[0])
                if ux * vx + uy * vy <= -math.cos(math.radians(45.0)):
                    return nxt[0]
            return None
        cands = []
        for j, s in ends:
            if j == cur:
                continue
            vx, vy = out_dir(j, s)
            if ux * vx + uy * vy <= -math.cos(math.radians(CORNER_MIN_ANG_DEG)):
                cands.append((j, s))
        return cands[0] if len(cands) == 1 else None

    used = [False] * len(runs)
    out: List[Polyline] = []

    def extend(i: int, entry: str) -> Tuple[List[Pt], List[str]]:
        """Recorre desde la corrida i (entrando por `entry`) hacia adelante,
        encadenando nodos, y marca cada corrida usada. Devuelve los vértices
        desde el extremo de entrada hacia el final de la cadena."""
        pts: List[Pt] = []
        kinds: List[str] = []
        cur, side = i, entry
        while True:
            used[cur] = True
            p, k = run_vertices(cur, forward=(side == "a"))
            if pts:
                p, k = p[1:], k[1:]
            pts.extend(p); kinds.extend(k)
            exit_node = runs[cur].node_b if side == "a" else runs[cur].node_a
            nxt = chain_next(exit_node, cur)
            if nxt is None or used[nxt[0]]:
                break
            cur, side = nxt
        return pts, kinds

    for seed in range(len(runs)):
        if used[seed]:
            continue
        # Hacia adelante (a→b) y hacia atrás (b→a) desde la semilla; la propia
        # semilla se emite una sola vez. Así ninguna corrida se repite aunque las
        # decisiones en un nodo no sean simétricas.
        fwd_pts, fwd_kinds = extend(seed, "a")
        used[seed] = False
        back_pts, back_kinds = extend(seed, "b")
        n_seed = len(run_vertices(seed, True)[0])      # la semilla aparece en ambos: se quita de uno
        pts = back_pts[::-1] + fwd_pts[n_seed:]
        kinds = back_kinds[::-1] + fwd_kinds[n_seed:]
        cp, ck = [pts[0]], [kinds[0]]
        for p, k in zip(pts[1:], kinds[1:]):
            if _dist(cp[-1], p) >= 0.5:
                cp.append(p); ck.append(k)
            elif k in ("vault", "tee", "junction"):
                ck[-1] = k
        if len(cp) >= 2:
            out.append(Polyline(cp, ck))
    return out


SOFT_KINDS = ("corner", "bend", "curve")   # edge/stop nunca se simplifican: son regla del usuario
SOFT_SIMPLIFY_PT = 0.5       # quiebres/esquinas blandos a ≤0.5 pt de la cuerda se quitan (transiciones).
                             # Era 1.5: dejaba la polilínea hasta 1.5 pt fuera de los guiones en
                             # quiebres suaves/bóvedas (DU06 h.14: p90 0.83 → 0.28 pt con 0.5).
CURVE_SIMPLIFY_SOFT_PT = 1.0 # …pero en tramos con vértices de curva se conserva la forma (≤1 pt)


def simplify_soft(pl: Polyline, eps: float = SOFT_SIMPLIFY_PT) -> Polyline:
    """Douglas-Peucker sobre tramos de vértices blandos consecutivos (arcos
    discontinuos, quiebres mínimos). Los vértices duros (bóveda, T, junction,
    extremo) se conservan siempre."""
    if len(pl.pts) <= 2:
        return pl
    hard = [i for i, k in enumerate(pl.kinds) if k not in SOFT_KINDS]
    if not hard or hard[0] != 0:
        hard = [0] + hard
    if hard[-1] != len(pl.pts) - 1:
        hard.append(len(pl.pts) - 1)
    pts: List[Pt] = []
    kinds: List[str] = []
    for h0, h1 in zip(hard, hard[1:]):
        seg = pl.pts[h0:h1 + 1]
        eps_seg = min(eps, CURVE_SIMPLIFY_SOFT_PT) if "curve" in pl.kinds[h0 + 1:h1] else eps
        simp = _douglas_peucker(seg, eps_seg)
        keep_idx = {h0}
        j = h0
        for q in simp[1:-1]:
            while j <= h1 and _dist(pl.pts[j], q) > 1e-9:
                j += 1
            keep_idx.add(j)
        keep_idx.add(h1)
        for i in range(h0, h1 + 1):
            if i in keep_idx and (not pts or i != h0):
                pts.append(pl.pts[i]); kinds.append(pl.kinds[i])
            elif i == h0 and not pts:
                pts.append(pl.pts[i]); kinds.append(pl.kinds[i])
    return Polyline(pts, kinds)


# ─────────────────────────── QA ───────────────────────────
def _pt_seg_dist(p: Pt, a: Pt, b: Pt) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return _dist(p, (a[0] + t * dx, a[1] + t * dy))


def coverage(dashes: Sequence[Dash], polylines: Sequence[Polyline],
             tol: float = COVERAGE_TOL_PT) -> Tuple[float, List[Dash]]:
    segs = [(pl.pts[i], pl.pts[i + 1]) for pl in polylines for i in range(len(pl.pts) - 1)]
    total = covered = 0.0
    missing: List[Dash] = []
    for d in dashes:
        total += d.length
        # Cada punto de muestra debe estar cerca de ALGÚN segmento (un guión
        # puede cruzar un vértice y repartirse entre dos segmentos).
        ok = all(any(_pt_seg_dist(q, a, b) <= tol for a, b in segs)
                 for q in (d.a, d.mid, d.b))
        if ok:
            covered += d.length
        else:
            missing.append(d)
    return (covered / total if total > 0 else 1.0), missing


def _polylines_from_uncovered(
    missing: Sequence[Dash], keep: Sequence[Polyline], pat: Pattern,
) -> List[Polyline]:
    """Guiones de ESTA capa que no cubrió ninguna polilínea: si forman una
    corrida colineal propia (hueco del patrón), se dibujan. No se usan paths
    de otras capas."""
    if not missing:
        return []
    keep_segs = [(pl.pts[i], pl.pts[i + 1]) for pl in keep for i in range(len(pl.pts) - 1)]
    leftover = []
    for d in missing:
        if keep_segs and any(
            _pt_seg_dist(d.mid, a, b) <= COVERAGE_TOL_PT for a, b in keep_segs
        ):
            continue
        leftover.append(d)
    if not leftover:
        return []
    extra: List[Polyline] = []
    min_len = max(pat.dash_long, 8.0)
    for g in group_collinear(leftover):
        for r in merge_overlapping_runs(build_runs([g], pat, [], []), pat):
            if r.length < min_len:
                continue
            pts = [r.a] + list(r.mid) + [r.b]
            kinds = ["end"] + ["curve"] * len(r.mid) + ["end"]
            extra.append(Polyline(pts, kinds))
    return extra


# ─────────────────────────── orquestación ───────────────────────────
def reconstruct(line_paths: Sequence[dict], vault_paths: Sequence[dict] = ()) -> GeomResult:
    dashes, glyphs, curves = classify_paths(line_paths)
    dashes, markers = strip_crossing_markers(dashes)     # «/» del linetype abandonado
    glyphs = glyphs + markers
    # Puntos donde el CLIP del PDF cortó la geometría (marco de la vista): un
    # extremo ahí no es un extremo real → no forma esquinas/T ni se prolonga.
    cut_pts: List[Pt] = [pt for pth in line_paths for pt in (pth.get("cut_pts") or [])]
    vaults = cluster_vaults(vault_paths)
    if not dashes and not curves:
        return GeomResult([], [], vaults, None, 1.0, [], list(range(len(vaults))), [],
                          0, len(glyphs), 0, 0)
    groups = group_collinear(dashes)
    pat = learn_pattern(dashes, glyphs, vaults, groups)
    runs = merge_overlapping_runs(build_runs(groups, pat, glyphs, vaults, curves), pat)
    for k, r in enumerate(runs):          # identidad de la corrida ANTES de partirla por ajuste
        r.origin = k
    # Contornos de bóveda dibujados en la misma capa (abandonadas): pasan a
    # ser bóvedas y sus corridas dejan de ser línea.
    loop_vaults, drop = detect_loop_vaults(runs, pat)
    if loop_vaults:
        vaults = sorted(vaults + loop_vaults, key=lambda v: (v.y0, v.x0))
        # Las corridas del lazo y los restos que quedan DENTRO del contorno
        # (esquinas partidas, guiones del borde) son símbolo, no línea.
        inside = [v.bbox(2.0) for v in loop_vaults]
        in_box = lambda p: any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] for b in inside)
        runs = [r for k, r in enumerate(runs)
                if k not in drop and not (in_box(r.a) and in_box(r.b) and all(in_box(m) for m in r.mid))]
    runs = [piece for r in runs for piece in _split_by_fit(r)]
    runs, offpattern = split_offpattern(runs, pat, vaults, glyphs)
    nodes, orphans = resolve_nodes(runs, pat, vaults, cut_pts)
    polys = [simplify_soft(pl) for pl in assemble(runs, nodes)]
    # Ruido: corridas cortas, aisladas y sin nodo topológico (restos de símbolos).
    min_len = max(2.0 * pat.dash_long, 3.0 * pat.join_gap)
    floor = max(1.5 * (pat.dash_short or 0.3 * pat.dash_long), 8.0)   # un guión corto suelto = tick
    vreach = [v.bbox(pat.join_gap) for v in vaults]
    touches_vault = lambda pl: any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]
                                   for p in pl.pts for b in vreach)
    keep, noise_polys = [], []
    for pl in polys:
        topo = any(k in ("vault", "tee", "junction", "corner", "bend", "edge", "stop") for k in pl.kinds)
        # Un tramo de ESTA capa con longitud de ≥1 guión del patrón no es ruido
        # (p.ej. un ramal corto que el overlay dejaba en gris).
        is_noise = (pl.length < floor or (pl.length < min_len and not topo)) and not touches_vault(pl)
        if pl.length >= pat.dash_long:
            is_noise = False
        (noise_polys if is_noise else keep).append(pl)
    noise = len(noise_polys)
    # Cobertura solo sobre los guiones que SÍ son utilidad: se descuentan los
    # cubiertos por trazos off-pattern y por el ruido descartado.
    excl_segs = [(pl.pts[i], pl.pts[i + 1]) for pl in offpattern + noise_polys
                 for i in range(len(pl.pts) - 1)]
    vboxes = [v.bbox(1.0) for v in vaults]
    pattern_dashes = [d for d in dashes if not any(
        _pt_seg_dist(d.a, a, b) <= COVERAGE_TOL_PT and _pt_seg_dist(d.b, a, b) <= COVERAGE_TOL_PT
        for a, b in excl_segs)
        # dentro de una bóveda la línea va al punto de referencia, no sobre los guiones
        and not any(b[0] <= d.mid[0] <= b[2] and b[1] <= d.mid[1] <= b[3] for b in vboxes)]
    cov, missing = coverage(pattern_dashes, keep)
    extra = _polylines_from_uncovered(missing, keep, pat)
    if extra:
        keep.extend(extra)
        cov, missing = coverage(pattern_dashes, keep)
    return GeomResult(keep, nodes, vaults, pat, cov, missing, orphans, offpattern,
                      len(dashes), len(glyphs), len(curves), noise)
