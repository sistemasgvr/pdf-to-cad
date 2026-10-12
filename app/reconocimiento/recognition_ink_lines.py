"""recognition_ink_lines.py — líneas CONTINUAS de una capa por estilo: la tinta es el eje (PURO).

El núcleo (`recognition_geom.reconstruct`) está hecho para el tipo de línea CAD
«explotado»: guiones + letras + huecos, que arma en rectas y une por intersecciones.
Un mapa SIG aplanado (Quarter Section de Phoenix, pedido del usuario 2026-10-10) dibuja
cada tubería como UN trazo continuo de buzón a buzón, con las curvas en cuerdas cortas;
ahí el núcleo partía la curva en rectas y la esquina caía hasta 5 pt FUERA de la tinta
(«no inventar»). En esas capas la tinta YA es la línea:

  · `continuous_layer(paths)`: la capa es de trazos continuos si casi ninguna punta
    tiene enfrente, a un hueco de guion, otra punta en su misma recta (un linetype a
    guiones las tiene casi todas) y la mayor parte de la tinta va en trazos largos.
  · `ink_reconstruct(paths, vault_paths, opts)`: un `GeomResult` cuyas polilíneas son
    los trazos tal cual (curvas Bézier en puntos), sin mover nada: los vértices
    interiores «bend», las puntas «junction» (la comparte otro trazo), «tee» (muere
    sobre otro trazo), «cut» (cortada por el clip del PDF) o «end». Las bóvedas
    salen del núcleo como siempre (sin líneas). Unir trazos (rutas), codos desde la
    tinta, imán a bóvedas… siguen igual río abajo.
Solo se usa en capas por ESTILO (`pdf_styles`): las capas CAD con nombre no cambian.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from reconocimiento import recognition_geom as geom

Pt = Tuple[float, float]

NODE_TOL_PT = 0.6            # puntas a ≤ esto: el mismo nodo
TEE_TOL_PT = 0.5             # punta a ≤ esto del interior de otro trazo: T
LONG_CHAIN_PT = 25.0         # trazo «largo»
GAP_MIN_PT, GAP_MAX_PT = 0.8, 20.0   # hueco de guion: otra punta enfrente a esta distancia…
GAP_DIR_DEG = 10.0           # …en la misma recta (±)
MAX_GAP_SHARE = 0.25         # continua: ≤ esto de las puntas con hueco de guion enfrente
MIN_LONG_SHARE = 0.6         # …y ≥ esto de la tinta en trazos largos
SYMBOL_MAX_PT = 20.0         # trazo CERRADO más chico que esto: símbolo, no tubería
BEZIER_STEP_PT = 2.0         # muestreo de una curva Bézier
SIMPLIFY_PT = 0.5            # tolerancia del trazo simplificado (= núcleo, SOFT_SIMPLIFY_PT)


def _p(q) -> Pt:
    return float(q[0]), float(q[1])


def _bezier(p0, p1, p2, p3, n: int) -> List[Pt]:
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def chains(path: dict) -> List[List[Pt]]:
    """Ristras CONECTADAS de un trazo (un trazo puede traer varios subtrazos)."""
    out: List[List[Pt]] = []
    cur: List[Pt] = []
    for it in path.get("items") or ():
        kind = it[0]
        if kind not in ("l", "c"):
            if len(cur) >= 2:
                out.append(cur)
            cur = []
            continue
        a = _p(it[1])
        if cur and math.dist(cur[-1], a) > 0.05:
            if len(cur) >= 2:
                out.append(cur)
            cur = []
        if not cur:
            cur.append(a)
        if kind == "l":
            cur.append(_p(it[2]))
        else:
            p0, p1, p2, p3 = a, _p(it[2]), _p(it[3]), _p(it[4])
            n = max(2, math.ceil((math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)) / BEZIER_STEP_PT))
            cur.extend(_bezier(p0, p1, p2, p3, n))
    if len(cur) >= 2:
        out.append(cur)
    return out


def _length(pts: Sequence[Pt]) -> float:
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def _closed_symbol(ch: Sequence[Pt]) -> bool:
    if math.dist(ch[0], ch[-1]) > NODE_TOL_PT:
        return False
    xs, ys = [p[0] for p in ch], [p[1] for p in ch]
    return max(max(xs) - min(xs), max(ys) - min(ys)) < SYMBOL_MAX_PT


def _unit(a: Pt, b: Pt):
    L = math.dist(a, b)
    return None if L < 1e-9 else ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _end_dirs(ch: Sequence[Pt]):
    """[(punta, dirección hacia AFUERA)] de una ristra abierta."""
    return [(ch[0], _unit(ch[1], ch[0])), (ch[-1], _unit(ch[-2], ch[-1]))]


def layer_chains(paths: Sequence[dict]) -> List[List[Pt]]:
    """Ristras de la capa sin símbolos cerrados chicos (válvulas, hidrantes)."""
    return [ch for p in paths for ch in chains(p) if not _closed_symbol(ch)]


def continuous_layer(paths: Sequence[dict]) -> bool:
    """¿Trazos continuos (mapa SIG / línea continua) y no un tipo de línea a guiones?"""
    chs = layer_chains(paths)
    total = sum(_length(c) for c in chs)
    if not chs or total <= 0:
        return False
    long_share = sum(_length(c) for c in chs if _length(c) >= LONG_CHAIN_PT) / total
    ends = [(p, d) for ch in chs for p, d in _end_dirs(ch) if d is not None]
    cos_tol = math.cos(math.radians(GAP_DIR_DEG))
    grid = {}
    for i, (p, _d) in enumerate(ends):
        grid.setdefault((int(p[0] // GAP_MAX_PT), int(p[1] // GAP_MAX_PT)), []).append(i)
    facing = 0
    for i, (p, d) in enumerate(ends):
        gx, gy = int(p[0] // GAP_MAX_PT), int(p[1] // GAP_MAX_PT)
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j == i:
                        continue
                    q, e = ends[j]
                    gap = math.dist(p, q)
                    if not GAP_MIN_PT <= gap <= GAP_MAX_PT:
                        continue
                    u = _unit(p, q)
                    # la otra punta está ADELANTE de esta, en su recta, y mira hacia acá
                    if u and d[0] * u[0] + d[1] * u[1] >= cos_tol and e[0] * u[0] + e[1] * u[1] <= -cos_tol:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        facing += hit
    return facing <= MAX_GAP_SHARE * len(ends) and long_share >= MIN_LONG_SHARE


def _douglas_peucker(pts: List[Pt], tol: float) -> List[Pt]:
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        worst, k = -1.0, -1
        for m in range(i + 1, j):
            d = _seg_dist(pts[m], a, b)[1]
            if d > worst:
                worst, k = d, m
        if worst > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, k in zip(pts, keep) if k]


def _thin(pts: List[Pt]) -> List[Pt]:
    """Sin puntos repetidos y sin el ZIGZAG del trazo: un mapa SIG mete cuerdas de
    0.4–1.5 pt que van y vuelven ±0.3 pt alrededor de la línea (Phoenix 17-10: una
    tubería recta con 11 cuerdas y giros de ±17°). Douglas–Peucker a `SIMPLIFY_PT`, la
    misma tolerancia de los quiebres del núcleo (`SOFT_SIMPLIFY_PT`): la línea queda a
    ≤ esto de su tinta."""
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, out[-1]) > 1e-6:
            out.append(p)
    if len(out) <= 2:
        return out
    if math.dist(out[0], out[-1]) <= NODE_TOL_PT:          # cerrada: partir en el punto más lejano
        far = max(range(len(out)), key=lambda m: math.dist(out[0], out[m]))
        return _douglas_peucker(out[:far + 1], SIMPLIFY_PT)[:-1] + _douglas_peucker(out[far:], SIMPLIFY_PT)
    return _douglas_peucker(out, SIMPLIFY_PT)


def _seg_dist(p: Pt, a: Pt, b: Pt) -> Tuple[float, float]:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < 1e-12:
        return 0.0, math.dist(p, a)
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2
    t = min(1.0, max(0.0, t))
    return t, math.dist(p, (a[0] + t * vx, a[1] + t * vy))


def ink_reconstruct(paths: Sequence[dict], vault_paths: Sequence[dict] = (),
                    opts: "geom.GeomOptions" = None) -> "geom.GeomResult":
    """`GeomResult` con la TINTA como polilíneas (ver el docstring del módulo)."""
    base = geom.reconstruct([], vault_paths, opts or geom.GeomOptions())
    cut_pts = [_p(q) for p in paths for q in (p.get("cut_pts") or ())]
    chs = [_thin(ch) for ch in layer_chains(paths)]
    chs = [ch for ch in chs if len(ch) >= 2 and _length(ch) > 0]
    ends = [(i, 0, ch[0]) for i, ch in enumerate(chs)] + [(i, -1, ch[-1]) for i, ch in enumerate(chs)]
    polylines = []
    for i, ch in enumerate(chs):
        kinds = ["bend"] * len(ch)
        for j in (0, len(ch) - 1):
            p = ch[j]
            if any(math.dist(p, q) <= NODE_TOL_PT for q in cut_pts):
                kinds[j] = "cut"
            elif any(o != i and math.dist(p, q) <= NODE_TOL_PT for o, _s, q in ends):
                kinds[j] = "junction"
            elif any(o != i and _seg_dist(p, a, b)[1] <= TEE_TOL_PT
                     for o, oc in enumerate(chs) for a, b in zip(oc, oc[1:])):
                kinds[j] = "tee"
            else:
                kinds[j] = "end"
        polylines.append(geom.Polyline(list(ch), kinds))
    n = len(chs)
    return geom.GeomResult(polylines=polylines, nodes=base.nodes, vaults=base.vaults, pattern=None,
                           coverage=1.0, uncovered=[], vault_orphans=base.vault_orphans,
                           offpattern=[], n_dashes=n, n_glyphs=0, n_curves=0, n_noise=0,
                           markers=[], glyphs=[])
