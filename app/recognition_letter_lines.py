"""recognition_letter_lines.py — Geometría de las líneas para leer sus letras (puro).

Lo usa `recognition_letters`: dónde va el rótulo del linetype en cada línea y qué
trazos son de la MISMA línea, para repartir una capa línea por línea.

  · `stroke_chains` / `dash_ends` / `gaps`: huecos entre dos guiones COLINEALES
    enfrentados (≤`GAP_MAX_PT`), con el sentido de lectura de la cola del guión.
  · `group_members`: los trazos que caben en cada hueco, en el marco del hueco.
  · `split_by_line`: une cada línea (guiones del mismo hueco, puntas que se tocan o
    forman esquina, guiones de una curva, sus letras y barras) y le da la utilidad de
    SUS letras; devuelve la utilidad de cada trazo y qué parte de la tinta asignó.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import recognition_geom as geom

Pt = Tuple[float, float]

DASH_MIN_PT = 8.0        # guión de la línea: tramo recto ≥ esto en la punta del trazo (asta de letra ≤7.2)
GAP_MAX_PT = 40.0        # hueco máximo entre dos guiones (el texto del linetype va dentro)
AXIS_TOL_PT = 0.6        # los dos guiones del hueco van sobre la misma recta…
PARALLEL_COS = math.cos(math.radians(2.0))   # …y con el mismo rumbo
TEXT_HALF_PT = 10.0      # las letras caben a ≤ esto del eje
TOUCH_PT = 1.0           # puntas a ≤ esto = la misma línea (vértice, arco)
CORNER_MIN_DEG = 8.0     # dos guiones que giran menos que esto no forman esquina (es un hueco)
CONTINUITY_DEG = 30.0    # dos guiones de una curva se miran de frente con hasta esto de giro…
CONTINUITY_BACK_PT = 2.0  # …y el rumbo de cada punta se toma con sus últimos 2 pt
MARKER_MAX_PT = 18.0     # barra «/» (= `geom.MARKER_MAX_LEN_PT`)…
MARKER_ATTACH_PT = 1.5   # …que cruza un guión a ≤ esto de su centro: es de esa línea
SITE_PT = 10.0           # lecturas a ≤ esto una de otra = el MISMO sitio (copias superpuestas)
LINE_INK_MIN_PT = 3.0    # tinta «de línea» para la cobertura del reparto (sin letras ni astillas)
LINE_SHARE = 0.6         # una línea es del código que tiene ≥60 % de sus sitios
OVERHEAD_SHARE = 0.3     # una línea con ≥30 % de lecturas «(oh)» es AÉREA (no se reconoce)


def path_key(path: dict) -> tuple:
    """Clave estable de un trazo del PDF (sirve entre `get_drawings` normal y extendido,
    y con otras capas apagadas: el `seqno` cambia, el rectángulo no)."""
    r = path.get("rect")
    if r is None:
        return ("id", id(path))
    x0, y0, x1, y1 = (r.x0, r.y0, r.x1, r.y1) if hasattr(r, "x0") else tuple(r)
    return (round(float(x0), 1), round(float(y0), 1), round(float(x1), 1), round(float(y1), 1),
            len(path.get("items") or ()))


def site_count(points) -> int:
    """Sitios distintos (a más de `SITE_PT`) entre los puntos dados."""
    reps: List[Pt] = []
    for p in points:
        if all(math.dist(p, r) > SITE_PT for r in reps):
            reps.append(p)
    return len(reps)


def stroke_chains(paths: Sequence[dict]) -> Tuple[List[List[Pt]], List[int]]:
    """Cadenas de tinta de los trazos SIN relleno (guiones y letras SHX son trazo;
    logos y rótulos rellenos no: la «M» del logo de Metro se leía «W» al revés) y el
    índice del trazo de cada una."""
    chains, owner = [], []
    for i, p in enumerate(paths):
        if p.get("fill") is not None:
            continue
        for ch in geom._path_chains(p):
            if len(ch) >= 2 and any(math.dist(ch[0], q) > 1e-6 for q in ch[1:]):
                chains.append(ch)
                owner.append(i)
    return chains, owner


def dash_ends(chains):
    """Puntas de guión: (punto, dirección hacia afuera, cadena, ¿es la COLA del trazo?)."""
    ends = []
    for ci, ch in enumerate(chains):
        for a, b, tail in ((ch[1], ch[0], False), (ch[-2], ch[-1], True)):
            L = math.dist(a, b)
            if L >= DASH_MIN_PT:
                ends.append((b, ((b[0] - a[0]) / L, (b[1] - a[1]) / L), ci, tail))
    return ends


def _grid(points, cell):
    grid = defaultdict(list)
    for k, p in enumerate(points):
        grid[(int(p[0] // cell), int(p[1] // cell))].append(k)
    return grid


def _near(grid, p, cell):
    gx, gy = int(p[0] // cell), int(p[1] // cell)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            yield from grid.get((gx + dx, gy + dy), ())


def gaps(ends):
    """Huecos entre guiones colineales enfrentados: [(origen, dirección, largo, seguro,
    cadena_a, cadena_b)] y las puntas que se tocan de frente [(cadena_a, cadena_b)].
    El sentido de lectura sale de la COLA de un guión (AutoCAD dibuja cada guión en el
    sentido de la polilínea): `seguro` = una sola de las dos puntas es cola."""
    grid = _grid([e[0] for e in ends], GAP_MAX_PT)
    found, touching, seen = [], [], set()
    for k, (p, u, ck, tk) in enumerate(ends):
        best = None
        for m in _near(grid, p, GAP_MAX_PT):
            q, w, cm, _tm = ends[m]
            if cm == ck or u[0] * w[0] + u[1] * w[1] > -PARALLEL_COS:
                continue
            vx, vy = q[0] - p[0], q[1] - p[1]
            along = vx * u[0] + vy * u[1]
            if -0.5 <= along <= GAP_MAX_PT and abs(vy * u[0] - vx * u[1]) <= AXIS_TOL_PT:
                if best is None or along < best[0]:
                    best = (along, m)
        if best is None:
            continue
        key = (min(k, best[1]), max(k, best[1]))
        if key in seen:
            continue
        seen.add(key)
        q, w, cm, tm = ends[best[1]]
        if best[0] <= 0.5:
            touching.append((ck, cm))
        elif not tk and tm:
            found.append((q, w, best[0], True, cm, ck))
        else:
            found.append((p, u, best[0], tk and not tm, ck, cm))
    return found, touching


def to_local(ch, origin, u):
    """Cadena en el marco del hueco: x a lo largo de la línea, y hacia la izquierda (arriba
    del texto que se lee en el sentido `u`, con el eje y del PDF hacia abajo)."""
    return [((q[0] - origin[0]) * u[0] + (q[1] - origin[1]) * u[1],
             (q[0] - origin[0]) * u[1] - (q[1] - origin[1]) * u[0]) for q in ch]


def group_members(chains, found_gaps):
    """Por hueco, las cadenas que caben en él: [(índice, cadena en el marco del hueco)]."""
    cell = 2 * TEXT_HALF_PT
    grid = defaultdict(list)
    for ci, ch in enumerate(chains):
        xs = [q[0] for q in ch]; ys = [q[1] for q in ch]
        if max(xs) - min(xs) <= cell and max(ys) - min(ys) <= cell:
            grid[(int(min(xs) // cell), int(min(ys) // cell))].append((min(xs), min(ys), max(xs), max(ys), ci))
    out = []
    for origin, u, glen, _sure, _ca, _cb in found_gaps:
        end = (origin[0] + u[0] * glen, origin[1] + u[1] * glen)
        nx, ny = abs(u[1]) * TEXT_HALF_PT, abs(u[0]) * TEXT_HALF_PT
        bx0, bx1 = min(origin[0], end[0]) - nx - 0.5, max(origin[0], end[0]) + nx + 0.5
        by0, by1 = min(origin[1], end[1]) - ny - 0.5, max(origin[1], end[1]) + ny + 0.5
        members = []
        for cx in range(int(bx0 // cell) - 1, int(bx1 // cell) + 1):
            for cy in range(int(by0 // cell) - 1, int(by1 // cell) + 1):
                for x0, y0, x1, y1, ci in grid.get((cx, cy), ()):
                    if x0 < bx0 or x1 > bx1 or y0 < by0 or y1 > by1:
                        continue
                    loc = to_local(chains[ci], origin, u)
                    if all(-0.5 <= x <= glen + 0.5 and abs(y) <= TEXT_HALF_PT for x, y in loc):
                        members.append((ci, loc))
        out.append(members)
    return out


# ─────────────────────────── una línea = un grupo de trazos ───────────────────────────
class _Union:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def _link_touching(chains, skip, uf):
    """Une las cadenas cuyas puntas se tocan (≤`TOUCH_PT`): vértices, arcos."""
    pts, who = [], []
    for ci, ch in enumerate(chains):
        if ci not in skip:
            pts += [ch[0], ch[-1]]
            who += [ci, ci]
    grid = _grid(pts, TOUCH_PT)
    for k, p in enumerate(pts):
        for m in _near(grid, p, TOUCH_PT):
            if who[m] != who[k] and math.dist(p, pts[m]) <= TOUCH_PT:
                uf.join(who[k], who[m])


def _link_corners(ends, uf):
    """Une dos guiones cuyas puntas forman ESQUINA (las rectas se cortan a ≤`GAP_MAX_PT`
    por delante de ambas): AutoCAD reinicia el patrón en cada vértice y a veces el
    tramo termina en un hueco, así que la línea no se toca en el vértice."""
    grid = _grid([e[0] for e in ends], GAP_MAX_PT)
    min_sin = math.sin(math.radians(CORNER_MIN_DEG))
    for k, (p, u, ck, _t) in enumerate(ends):
        for m in _near(grid, p, GAP_MAX_PT):
            q, w, cm, _tm = ends[m]
            if m <= k or cm == ck:
                continue
            den = u[0] * w[1] - u[1] * w[0]
            if abs(den) < min_sin:
                continue                      # casi paralelas: eso es un hueco, no una esquina
            vx, vy = q[0] - p[0], q[1] - p[1]
            s = (vx * w[1] - vy * w[0]) / den
            t = (vx * u[1] - vy * u[0]) / den
            if -0.5 <= s <= GAP_MAX_PT and -0.5 <= t <= GAP_MAX_PT:
                uf.join(ck, cm)


def _link_continuity(chains, skip, uf):
    """Une dos trazos que siguen la MISMA línea a través de un hueco aunque no sean
    colineales: en una curva a guiones cada guión gira un poco y sus puntas ya no
    están sobre una misma recta (DU06 h.4 `U-Rearr-Tel`, esquina redondeada «—T—»).
    Puntas enfrentadas (±`CONTINUITY_DEG`) a ≤`GAP_MAX_PT`, la otra cerca de la
    prolongación de la primera (desvío ≤ 0.6 pt + 25 % de la distancia)."""
    ends = []
    for ci, ch in enumerate(chains):
        if ci in skip:
            continue
        for pts in (ch, ch[::-1]):
            P = pts[-1]
            back = next((q for q in reversed(pts[:-1]) if math.dist(P, q) >= CONTINUITY_BACK_PT), None)
            if back is None:
                continue                          # trazo de menos de 2 pt: no da rumbo
            L = math.dist(P, back)
            ends.append((P, ((P[0] - back[0]) / L, (P[1] - back[1]) / L), ci))
    grid = _grid([e[0] for e in ends], GAP_MAX_PT)
    cos_lim = math.cos(math.radians(CONTINUITY_DEG))
    for p, u, ci in ends:
        best = None
        for m in _near(grid, p, GAP_MAX_PT):
            q, w, cj = ends[m]
            if cj == ci or u[0] * w[0] + u[1] * w[1] > -cos_lim:
                continue
            vx, vy = q[0] - p[0], q[1] - p[1]
            along = vx * u[0] + vy * u[1]
            if 0.0 < along <= GAP_MAX_PT and abs(vy * u[0] - vx * u[1]) <= 0.6 + 0.25 * along:
                if best is None or along < best[0]:
                    best = (along, cj)
        if best is not None:
            uf.join(ci, best[1])


def _link_markers(chains, skip, uf):
    """Barras «/» que cruzan un guión (no están en un hueco): son de esa línea."""
    segs = [(a, b, ci) for ci, ch in enumerate(chains) for a, b in zip(ch, ch[1:])
            if math.dist(a, b) >= DASH_MIN_PT]
    cell = 2 * DASH_MIN_PT
    grid = defaultdict(list)
    for si, (a, b, _ci) in enumerate(segs):
        for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
            for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                grid[(gx, gy)].append(si)
    for ci, ch in enumerate(chains):
        if ci in skip:
            continue
        xs = [q[0] for q in ch]; ys = [q[1] for q in ch]
        if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) > MARKER_MAX_PT:
            continue
        mid = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
        for si in grid.get((int(mid[0] // cell), int(mid[1] // cell)), ()):
            a, b, cj = segs[si]
            if cj == ci:
                continue
            vx, vy = b[0] - a[0], b[1] - a[1]
            t = ((mid[0] - a[0]) * vx + (mid[1] - a[1]) * vy) / (vx * vx + vy * vy)
            if 0.0 <= t <= 1.0 and math.hypot(mid[0] - a[0] - t * vx, mid[1] - a[1] - t * vy) <= MARKER_ATTACH_PT:
                uf.join(cj, ci)
                break


def split_by_line(paths, chains, owner, ends, found_gaps, touching, members_by_gap, readings,
                  utility_of: Callable[[str], Optional[str]]) -> Tuple[Dict[tuple, str], float]:
    """Utilidad de cada trazo (clave `path_key`) según las letras de SU línea, y la
    fracción de la tinta de líneas de la capa (cadenas ≥`LINE_INK_MIN_PT` que no son
    letra) que queda asignada. `readings`: [(cadena del guión, sitio, código, aérea)];
    `utility_of(código)` → utilidad o None (código desconocido o ruido)."""
    uf = _Union(len(chains))
    members = set()
    for (_o, _u, _l, _s, ca, cb), group in zip(found_gaps, members_by_gap):
        uf.join(ca, cb)
        for ci, _loc in group:
            members.add(ci)
            uf.join(ca, ci)
    for ca, cb in touching:
        uf.join(ca, cb)
    _link_touching(chains, members, uf)
    _link_corners(ends, uf)
    _link_continuity(chains, members, uf)
    _link_markers(chains, members, uf)
    votes = defaultdict(lambda: defaultdict(list))
    for ca, site, code, overhead in readings:
        votes[uf.find(ca)]["(OH)" if overhead else code].append(site)
    line_util: Dict[int, str] = {}
    for root, by in votes.items():
        n_oh = site_count(by.pop("(OH)", []))
        counts = Counter({c: site_count(s) for c, s in by.items()})
        if not counts or n_oh >= OVERHEAD_SHARE * (sum(counts.values()) + n_oh):
            continue
        code, n = counts.most_common(1)[0]
        util = utility_of(code)
        if util and n >= LINE_SHARE * sum(counts.values()):
            line_util[root] = util
    weight = defaultdict(Counter)
    ink = assigned = 0.0
    for ci, ch in enumerate(chains):
        length = sum(math.dist(a, b) for a, b in zip(ch, ch[1:]))
        util = line_util.get(uf.find(ci))
        if util:
            weight[owner[ci]][util] += length
        if ci not in members and length >= LINE_INK_MIN_PT:
            ink += length
            assigned += length if util else 0.0
    by_path = {path_key(paths[pi]): w.most_common(1)[0][0] for pi, w in weight.items()}
    return by_path, (assigned / ink if ink > 0 else 0.0)
