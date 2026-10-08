"""Extremos de línea: dónde TERMINA de verdad cada línea (después del núcleo). PURO.

Dos reglas, pedidas por el usuario el 2026-09-28 en DU08 h.26 («no inventar»,
«terminar en el corte del plano»), aplicadas sobre las polilíneas del núcleo sin
tocar el núcleo:

1. `trim_inkless_tails` — una línea que llega a un tee/empalme de OTRA línea por un
   tramo final SIN tinta propia más largo que el hueco del linetype no llega ahí: el
   núcleo prolongó su extremo por su propia recta hasta la otra línea. Caso: el ramal
   curvo de telecom de 12 pt que termina en el aire y se «unía» 9 pt más abajo a la
   línea vecina, justo en el hueco de SU letra «t» (la letra es de la otra línea).
   Se corta donde termina la tinta.
2. `extend_to_cut` — una línea cuyo último guión muere antes del borde de la vista
   porque el linetype pone una letra (o un hueco) justo antes del recorte, termina en
   el CORTE: se prolonga por su recta hasta el borde del polígono de recorte de su
   capa (extremo `cut`). En la hoja compuesta el borde es el de la pieza: las dos
   piezas llegan así a la misma costura.
"""
from __future__ import annotations

import math
from typing import Tuple

Pt = Tuple[float, float]

TAIL_INK_NEAR_PT = 2.5       # tinta propia a esta distancia del tramo = el tramo tiene tinta (la
                             # centerline puede ir hasta 2 pt corrida de su guión: DU10 h.23)
TAIL_INK_PAR_DEG = 25.0      # …y con su rumbo (la línea a la que llega, que cruza, no cuenta)
TAIL_EXTRA_PT = 1.0          # un tramo sin tinta de hasta gap_max + esto es un hueco del linetype
GLYPH_OWN_PT = 1.5           # una letra a más de esto de OTRA línea de la capa es de esta línea
CUT_EXT_MAX_PT = 40.0        # tope absoluto de la prolongación hasta el corte
CUT_GLYPH_ON_RAY_PT = 1.0    # la letra del linetype está centrada sobre la prolongación
CUT_INK_NEAR_PT = 1.0        # tinta propia paralela a esto de la prolongación la cubre
CUT_BLOCK_PT = 0.5           # otra línea de la capa a esto de la prolongación la bloquea


def _seg_dist(q: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


class _Grid:
    def __init__(self, items, cell=8.0):
        self.c = cell
        self.g = {}
        for it in items:
            a, b = it[0], it[1]
            for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                    self.g.setdefault((gx, gy), []).append(it)

    def near(self, q):
        cx, cy = int(q[0] // self.c), int(q[1] // self.c)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.extend(self.g.get((cx + dx, cy + dy), ()))
        return out


def _parallel(p: Pt, r: Pt, ux: float, uy: float) -> bool:
    L = math.dist(p, r)
    if L < 1e-9:
        return True                                      # punto de tinta suelto
    return abs((r[0] - p[0]) * ux + (r[1] - p[1]) * uy) >= math.cos(math.radians(TAIL_INK_PAR_DEG)) * L


def _plain_gap(pattern, has_letters: bool = True) -> float:
    """Hueco SIMPLE entre guiones (sin letra): `gap_max` del patrón incluye el hueco
    donde va la letra (telecom DU08: 9 pt con letra de 7.2; el simple mide 3.6). En
    una capa SIN letras (`has_letters=False`) todos sus huecos son simples: el
    `letter` del patrón es solo el valor por defecto (5 pt; DU08 h.26 drenaje, guiones
    con huecos de 10 pt)."""
    gm = getattr(pattern, "gap_max", 0.0) or 0.0
    if not has_letters:
        return gm
    return max(gm - (getattr(pattern, "letter", 0.0) or 0.0), 0.5 * gm)


def _own_glyph_on(glyphs, a: Pt, b: Pt, others: "_Grid", self_id) -> bool:
    """¿Hay una letra/marca de la capa sobre el tramo a→b que sea de ESTA línea (no
    centrada sobre otra línea de la capa)?"""
    for gl in glyphs or ():
        c = (gl.cx, gl.cy)
        if _seg_dist(c, a, b) > gl.size / 2.0 + 0.5:
            continue
        if any(pid != self_id and _seg_dist(c, p, q) <= GLYPH_OWN_PT for p, q, pid in others.near(c)):
            continue                                     # la letra es de la otra línea
        return True
    return False


def trim_inkless_tails(polylines, ink_segs, pattern, glyphs, make_polyline):
    """Polilíneas (coords PDF) con sus extremos tee/junction recortados donde termina
    la tinta si el tramo final sin tinta propia supera el hueco del linetype
    (`pattern.gap_max` + TAIL_EXTRA_PT) y no tiene una letra propia. Devuelve una
    lista nueva (las no tocadas son las mismas)."""
    if not polylines or not ink_segs:
        return list(polylines)
    ink = _Grid([(a, b, None) for a, b in ink_segs])
    others = _Grid([(p, q, i) for i, pl in enumerate(polylines) for p, q in zip(pl.pts, pl.pts[1:])])
    gap = _plain_gap(pattern, bool(glyphs)) + TAIL_EXTRA_PT
    out = []
    for i, pl in enumerate(polylines):
        pts, kinds = list(pl.pts), list(pl.kinds)
        changed = False
        for end, step in ((0, 1), (len(pts) - 1, -1)):
            if len(pts) < 2 or kinds[end] not in ("tee", "junction"):
                continue
            a, b = pts[end], pts[end + step]
            L = math.dist(a, b)
            if L < 1e-9:
                continue
            n = max(1, int(L / 0.25))
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            tail = L
            for k in range(n + 1):
                q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                # tinta PROPIA: cerca (la centerline se aparta ≤1 pt de la tinta) y con el
                # rumbo del tramo (la otra línea, que cruza, no cuenta)
                hits = [(p, r) for p, r, _ in ink.near(q)
                        if _seg_dist(q, p, r) <= TAIL_INK_NEAR_PT and _parallel(p, r, ux, uy)]
                if hits:
                    # la línea termina donde termina ESE trazo (su punta proyectada), no
                    # donde la muestra entra en la tolerancia (quedaba 2.4 pt más allá)
                    s_ink = min((c[0] - a[0]) * ux + (c[1] - a[1]) * uy for p, r in hits for c in (p, r))
                    tail = min(L, max(L * k / n, s_ink))
                    break
            if tail <= gap:
                continue
            X = (a[0] + (b[0] - a[0]) * tail / L, a[1] + (b[1] - a[1]) * tail / L)
            if _own_glyph_on(glyphs, a, X, others, i):
                continue
            if tail >= L - 0.5:
                # todo el tramo sin tinta: el extremo pasa al vértice siguiente
                if len(pts) <= 2:
                    continue
                del pts[end]; del kinds[end]
                end = 0 if step > 0 else len(pts) - 1
                kinds[end] = "end"
            else:
                pts[end], kinds[end] = X, "end"
            changed = True
        out.append(make_polyline(pts, kinds) if changed else pl)
    return out


def _ray_exit(E: Pt, u: Pt, polys, tmax: float):
    """Primer cruce (t, X) del rayo E + t·u (0 < t ≤ tmax) con un lado de los
    polígonos de recorte, o None."""
    best = None
    for poly in polys:
        m = len(poly)
        for k in range(m):
            p, q = poly[k], poly[(k + 1) % m]
            ex, ey = q[0] - p[0], q[1] - p[1]
            den = u[0] * ey - u[1] * ex
            if abs(den) < 1e-12:
                continue
            t = ((p[0] - E[0]) * ey - (p[1] - E[1]) * ex) / den
            s = ((p[0] - E[0]) * u[1] - (p[1] - E[1]) * u[0]) / den
            if 1e-6 < t <= tmax and -1e-6 <= s <= 1 + 1e-6 and (best is None or t < best[0]):
                best = (t, (E[0] + u[0] * t, E[1] + u[1] * t))
    return best


def _inside(q: Pt, poly) -> bool:
    x, y = q
    inside = False
    for k in range(len(poly)):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % len(poly)]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def ink_index(segs, scale: float = 1.0) -> "_Grid":
    """Índice de los trazos de la capa (mismas coords que `extend_to_cut`)."""
    return _Grid([(a, b, None) for a, b in segs], cell=8.0 * scale)


def _longest_bare_run(E: Pt, u: Pt, t: float, ink: "_Grid", glyphs, scale: float) -> float:
    """Tramo más largo de E→E+t·u sin tinta propia paralela (≤ CUT_INK_NEAR_PT) ni
    letra del linetype centrada encima."""
    on = []
    for gx, gy, gsize in glyphs or ():
        if abs((gx - E[0]) * u[1] - (gy - E[1]) * u[0]) <= CUT_GLYPH_ON_RAY_PT * scale:
            on.append(((gx - E[0]) * u[0] + (gy - E[1]) * u[1], gsize / 2.0 + 0.5 * scale))
    near = CUT_INK_NEAR_PT * scale
    n = max(1, int(t / (0.25 * scale)))
    run = best = 0.0
    for k in range(1, n + 1):
        sk = t * k / n
        q = (E[0] + u[0] * sk, E[1] + u[1] * sk)
        if any(abs(sk - sc) <= h for sc, h in on) or (ink is not None and any(
                _seg_dist(q, p, r) <= near and _parallel(p, r, u[0], u[1]) for p, r, _ in ink.near(q))):
            run = 0.0
        else:
            run += t / n
            best = max(best, run)
    return best


def extend_to_cut(pts, kinds, clip_polys, glyphs, pattern, others_fn, scale: float = 1.0, ink=None):
    """(pts, kinds) con los extremos libres (`end`) llevados hasta el borde del
    recorte de su capa (solo los polígonos que contienen el extremo) cuando lo que
    hay entre el extremo y el borde es la propia línea: su tinta (`ink`, de
    `ink_index`), sus letras centradas sobre la prolongación y huecos SIMPLES
    (≤ `_plain_gap` + 1 pt: sin letra visible, la letra quedó entera fuera). Un
    hueco «con letra» sin la letra no basta (DU08 h.43: 17 pt sin tinta hacia el
    borde), ni una letra de OTRA línea al lado (DU10 h.23: la diagonal que muere en
    el «SS» de la horizontal). Otra línea de la capa sobre la prolongación
    (`others_fn()` → sus segmentos) la bloquea. El extremo nuevo es `cut` (la línea
    sigue fuera de la vista).

    Va DESPUÉS del ajuste de codos (px del lienzo, `scale` = px por pt; `glyphs` =
    (cx, cy, lado) en px): la prolongación sigue la recta tangente del codo. Antes
    del ajuste, en una curva que llega al borde, se prolongaba la cuerda del último
    tramo curvo y el codo se perdía (DU08 h.22, DU10 h.15/h.20, LABOE h.28)."""
    if not clip_polys or len(pts) < 2 or pattern is None:
        return pts, kinds
    pts, kinds = list(pts), list(kinds)
    gap = (_plain_gap(pattern, bool(glyphs)) + TAIL_EXTRA_PT) * scale
    for end, nb in ((0, 1), (len(pts) - 1, len(pts) - 2)):
        if kinds[end] != "end":
            continue
        E, P = pts[end], pts[nb]
        L = math.dist(E, P)
        if L < 1e-6:
            continue
        u = ((E[0] - P[0]) / L, (E[1] - P[1]) / L)
        hit = _ray_exit(E, u, [pg for pg in clip_polys if _inside(E, pg)], CUT_EXT_MAX_PT * scale)
        if hit is None:
            continue
        t, X = hit
        if t > gap and _longest_bare_run(E, u, t, ink, glyphs, scale) > gap:
            continue
        others_segs = others_fn()
        if any(_seg_dist(q, E, X) <= CUT_BLOCK_PT * scale for a, b in others_segs for q in (a, b)) or any(
                _crosses(E, X, a, b) for a, b in others_segs):
            continue
        pts[end], kinds[end] = X, "cut"
    return pts, kinds


def _crosses(p1: Pt, p2: Pt, q1: Pt, q2: Pt) -> bool:
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0
