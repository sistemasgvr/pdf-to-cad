"""recognition_vault_through.py — la línea que ATRAVIESA su bóveda lleva su caja (PURO).

Regla del núcleo (apuntes del usuario): el nodo «vault» —la CAJA— existe cuando una
línea de red ATRAVIESA la bóveda; el núcleo lo pone partiendo en el borde la corrida
que la cruza (`recognition_geom.resolve_nodes`, Fase A). Pero solo parte corridas
RECTAS: una entidad CAD que entra curva, cruza la caja recta y sale curva (DU06 h.12
(742, 1084), «—SC—», reporte del usuario 2026-10-09) pasaba por encima sin nodo y, al
importar, la caja quedaba suelta encima de la línea.

Este paso cumple la misma regla sobre la salida, sin tocar el núcleo ni mover nada:
  · Solo bóvedas a las que no llega ninguna línea (ningún vértice vault/stop/edge
    dentro o sobre su contorno, ±`zoom` px).
  · La línea la atraviesa si una parte RECTA de lo que se dibuja (entre las
    tangencias de sus codos) pasa por el medio de la bóveda —el centro a ≤ la mitad
    de su lado menor, `MAX_OFF_FRAC`, como las llegadas del núcleo— y sus dos puntas
    quedan fuera: entra y sale.
  · El vértice «vault» va en el pie del centro sobre esa recta (o, si ya hay ahí un
    vértice suelto de la línea, ese pasa a «vault»): la línea dibujada es la misma.
  · Una línea por bóveda: la que pasa más cerca del centro.
"""
import math
from typing import List, Sequence, Tuple

from reconocimiento import recognition_vault_snap as snap_mod

Pt = Tuple[float, float]

MAX_OFF_FRAC = 0.5          # centro de la bóveda a ≤ esto × su lado menor de la recta
REUSE_PX_FRAC = 0.5         # vértice suelto a ≤ esto × zoom del pie: se reusa
NODE_KINDS = ("vault", "stop", "edge")
SOFT_KINDS = ("bend", "corner", "curve")


def _straight_parts(pl) -> List[Tuple[int, Pt, Pt]]:
    """(k, s, e): la parte RECTA dibujada del tramo k→k+1 (de la tangencia de salida
    del codo en k a la de entrada del codo en k+1)."""
    pts, fl = pl.pts_pdf, pl.fillets or {}
    out = []
    for k in range(len(pts) - 1):
        s = tuple(fl[k]["b"]) if k in fl else tuple(pts[k])
        e = tuple(fl[k + 1]["a"]) if k + 1 in fl else tuple(pts[k + 1])
        out.append((k, s, e))
    return out


def _min_side(b) -> float:
    kind, g = b
    if kind == "circle":
        return 2.0 * g[2]
    n = len(g)
    return min(math.dist(g[i], g[(i + 1) % n]) for i in range(n))


def _foot(c: Pt, s: Pt, e: Pt):
    """(pie de c sobre el segmento s→e, t en [0,1] sin acotar, distancia a la recta)."""
    vx, vy = e[0] - s[0], e[1] - s[1]
    L2 = vx * vx + vy * vy
    if L2 < 1e-12:
        return None
    t = ((c[0] - s[0]) * vx + (c[1] - s[1]) * vy) / L2
    q = (s[0] + t * vx, s[1] + t * vy)
    return q, t, math.dist(q, c)


def _bbox(vg: dict):
    b = snap_mod.boundary(vg)
    if b is None:
        return None
    kind, g = b
    if kind == "circle":
        return g[0] - g[2], g[1] - g[2], g[0] + g[2], g[1] + g[2]
    return min(p[0] for p in g), min(p[1] for p in g), max(p[0] for p in g), max(p[1] for p in g)


def _overlap(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _insert_vertex(pl, k: int, q: Pt, kind: str) -> int:
    """Inserta q (tipo `kind`) entre los vértices k y k+1; corre los índices de los codos."""
    pl.pts_pdf.insert(k + 1, (float(q[0]), float(q[1])))
    pl.kinds.insert(k + 1, kind)
    if pl.fillets:
        pl.fillets = {(j + 1 if j > k else j): f for j, f in pl.fillets.items()}
    return k + 1


def mark_through_vaults(polylines: Sequence, vaults_geo: Sequence[dict], zoom: float) -> List[dict]:
    """Pone el vértice «vault» donde una línea atraviesa una bóveda sin nodo (ver el
    docstring del módulo). Modifica `polylines` en su lugar. Devuelve
    [{"vault": índice, "at": (x, y) px}, …]."""
    done = []
    lines = [pl for pl in polylines if len(pl.pts_pdf) >= 2 and len(pl.kinds) == len(pl.pts_pdf)]

    def has_node(vg) -> bool:
        return any(k in NODE_KINDS and snap_mod.vault_contains(vg, p, pad=zoom)
                   for pl in lines for p, k in zip(pl.pts_pdf, pl.kinds))

    boxes = [_bbox(vg) for vg in vaults_geo]
    with_node = [boundary is not None and has_node(vg)
                 for vg, boundary in ((vg, snap_mod.boundary(vg)) for vg in vaults_geo)]
    for vi, vg in enumerate(vaults_geo):
        b = snap_mod.boundary(vg)
        if b is None or with_node[vi]:
            continue                                   # ya le llega una línea
        # Bóvedas que se SOLAPAN son el mismo nodo (regla del núcleo): una anidada en
        # otra que ya tiene su nodo no lleva otro (DU08 h.36: dos cajas a 13 pt).
        if any(j != vi and with_node[j] and boxes[j] and boxes[vi] and _overlap(boxes[vi], boxes[j])
               for j in range(len(vaults_geo))):
            continue
        c = snap_mod.vault_centroid(vg)
        lim = MAX_OFF_FRAC * _min_side(b)
        best = None
        for pl in lines:
            if (snap_mod.vault_contains(vg, pl.pts_pdf[0], pad=zoom)
                    or snap_mod.vault_contains(vg, pl.pts_pdf[-1], pad=zoom)):
                continue                               # nace o muere en ella: no la atraviesa
            for k, s, e in _straight_parts(pl):
                f = _foot(c, s, e)
                if f is None:
                    continue
                q, t, off = f
                if not (0.0 <= t <= 1.0) or off > lim or not snap_mod.vault_contains(vg, q):
                    continue
                if best is None or off < best[0]:
                    best = (off, pl, k, q)
        if best is None:
            continue
        _, pl, k, q = best
        reuse = [j for j in (k, k + 1) if j not in (pl.fillets or {})
                 and pl.kinds[j] in SOFT_KINDS and math.dist(pl.pts_pdf[j], q) <= REUSE_PX_FRAC * zoom]
        if reuse:
            j = reuse[0]
            pl.kinds[j] = "vault"
            at = tuple(pl.pts_pdf[j])
        else:
            _insert_vertex(pl, k, q, "vault")
            at = q
        done.append({"vault": vi, "at": at})
    return done
