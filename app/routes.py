"""routes.py — Rutas de una utilidad (strokes por buena continuación).

Después de `recognition_geom.reconstruct` cada T/junction corta la polilínea.
Este módulo, puro (sin Qt ni fitz), las vuelve a encadenar por el principio de
buena continuación (Thomson & Richardson, every-best-fit): en cada nodo se
sigue de frente; el que se desvía empieza otra ruta. Si no hay trayectoria
clara, no se une nada.

No inventa puntos ni mueve los existentes. Solo concatena polilíneas que ya
comparten un vértice. Se llama una vez por capa OCG: no cruza capas ni mezcla
activas con abandonadas (eso lo garantiza quien llama).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

from recognition_geom import Pattern, Polyline

Pt = Tuple[float, float]

NODE_TOL_PT = 0.6           # dos extremos a ≤0.6 pt son el mismo nodo (new_node une a 0.5)
LOOKAHEAD_FACTOR = 3.0      # rumbo de llegada medido a 3 guiones largos del nodo (~66 pt)
LOOKAHEAD_MIN_PT = 20.0     # …y nunca menos de 20 pt
THETA_JUNCTION_DEG = 35.0   # en nodo de grado ≥3: continúa "de frente" si gira ≤35°
THETA_DEG2_DEG = 100.0      # en nodo de grado 2: una esquina (≤100°) sigue siendo la misma ruta
AMBIGUOUS_DELTA_DEG = 10.0  # si el 2.º mejor par difiere <10° del mejor, no hay trayectoria clara
TERMINAL_KINDS = ("cut",)   # marco de la vista: nunca se cruza
# El vértice de unión se queda con el kind más fuerte (no se degrada a "end").
_KIND_RANK = {
    "vault": 0, "junction": 1, "tee": 2, "corner": 3, "bend": 4,
    "edge": 5, "stop": 6, "cut": 7, "curve": 8, "end": 9,
}
# Dónde empieza la ruta: un extremo real, luego un stop, luego lo que quede.
_START_RANK = {"cut": 0, "end": 0, "stop": 1}


@dataclass
class Route:
    pl: Polyline
    n_segments: int
    members: List[int]


@dataclass
class _Edge:
    idx: int
    pl: Polyline
    node_a: int
    node_b: int


def build_routes(polylines: Sequence[Polyline], pattern: Optional[Pattern]) -> List[Route]:
    """Une tramos de UNA capa en rutas. `pattern` solo aporta el largo del guión
    (None → lookahead mínimo). El orden y la orientación son deterministas."""
    edges = [e for i, pl in enumerate(polylines) if len(pl.pts) >= 2
             for e in (_Edge(i, pl, -1, -1),)]
    if not edges:
        return []
    nodes, node_kind, node_cut = _cluster(edges)
    incident: Dict[int, List[Tuple[int, str]]] = {}
    for ei, e in enumerate(edges):
        incident.setdefault(e.node_a, []).append((ei, "a"))
        incident.setdefault(e.node_b, []).append((ei, "b"))
    lookahead = LOOKAHEAD_MIN_PT
    if pattern is not None and pattern.dash_long:
        lookahead = max(LOOKAHEAD_MIN_PT, LOOKAHEAD_FACTOR * pattern.dash_long)
    partner = _pair(edges, incident, node_kind, node_cut, lookahead, _tee_nodes(edges))
    return _walk(edges, partner, nodes)


def _cluster(edges: List[_Edge]):
    """Solo los extremos crean nodos. Un `cut` en el nodo lo deja terminal."""
    nodes: List[Pt] = []
    kinds: List[str] = []
    cuts: List[bool] = []
    cell = 2.0
    buckets: Dict[Tuple[int, int], List[int]] = {}

    def node_of(p: Pt, kind: str) -> int:
        cx, cy = int(math.floor(p[0] / cell)), int(math.floor(p[1] / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in buckets.get((cx + dx, cy + dy), ()):
                    if math.hypot(nodes[i][0] - p[0], nodes[i][1] - p[1]) <= NODE_TOL_PT:
                        if _KIND_RANK.get(kind, 9) < _KIND_RANK.get(kinds[i], 9):
                            kinds[i] = kind
                        cuts[i] = cuts[i] or kind in TERMINAL_KINDS
                        return i
        i = len(nodes)
        nodes.append(p); kinds.append(kind); cuts.append(kind in TERMINAL_KINDS)
        buckets.setdefault((cx, cy), []).append(i)
        return i

    for e in edges:
        e.node_a = node_of(e.pl.pts[0], e.pl.kinds[0] if e.pl.kinds else "end")
        e.node_b = node_of(e.pl.pts[-1], e.pl.kinds[-1] if e.pl.kinds else "end")
    return nodes, kinds, cuts


def _tee_nodes(edges: List[_Edge]) -> set:
    """Nodos donde algún extremo es una T: muere SOBRE otra línea que pasa de
    largo (un vértice interior de esa otra, que por eso no crea nodo aquí)."""
    out = set()
    for e in edges:
        if e.pl.kinds and e.pl.kinds[0] == "tee":
            out.add(e.node_a)
        if e.pl.kinds and e.pl.kinds[-1] == "tee":
            out.add(e.node_b)
    return out


def _heading_into(pts: Sequence[Pt], side: str, lookahead: float) -> Tuple[float, float]:
    """Rumbo con el que la polilínea LLEGA al extremo `side` (apunta hacia el nodo)."""
    seq = list(pts) if side == "a" else list(reversed(pts))
    node = seq[0]
    remain = lookahead
    back = seq[-1]
    for a, b in zip(seq, seq[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L >= remain - 1e-9:
            t = remain / L if L > 1e-12 else 0.0
            back = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            break
        remain -= L
        back = b
    return _unit(node[0] - back[0], node[1] - back[1])


def _defl(h1: Tuple[float, float], h2: Tuple[float, float]) -> float:
    """Giro para salir de quien llega por h1 y seguir por el contrario de h2. 0° = de frente."""
    dot = max(-1.0, min(1.0, h1[0] * -h2[0] + h1[1] * -h2[1]))
    return math.degrees(math.acos(dot))


def _pair(edges, incident, node_kind, node_cut, lookahead, tee_nodes=frozenset()):
    partner: Dict[Tuple[int, str], Tuple[int, str]] = {}
    for n, inc in incident.items():
        if node_cut[n] or node_kind[n] in TERMINAL_KINDS or len(inc) < 2:
            continue
        # En una T la línea que PASA también llega al nodo (no crea extremos, pero
        # está): el grado real es ≥3 y solo se sigue «de frente». Si no, dos ramales
        # que mueren del MISMO lado de la línea se cosían en una «V» a través de
        # ella (DU08 h.21 (763, 871) y (710, 892): el rumbo medido 66 pt atrás en
        # curvas daba ~90° y pasaba el umbral de 100° de un nodo de grado 2).
        deg2 = len(inc) == 2 and n not in tee_nodes
        theta = THETA_DEG2_DEG if deg2 else THETA_JUNCTION_DEG
        cands = []
        for (e, se), (f, sf) in combinations(inc, 2):
            if e == f:
                continue                      # un lazo no se empareja consigo mismo
            he = _heading_into(edges[e].pl.pts, se, lookahead)
            hf = _heading_into(edges[f].pl.pts, sf, lookahead)
            cands.append((_defl(he, hf), (e, se), (f, sf)))
        cands.sort(key=lambda t: t[0])
        free = {end: True for end in inc}
        for k, (d, e, f) in enumerate(cands):
            if d > theta:
                break
            if not free[e] or not free[f]:
                continue
            rival = min((d2 for d2, e2, f2 in cands[k + 1:]
                         if free.get(e2, False) and free.get(f2, False) and ({e2, f2} & {e, f})),
                        default=None)
            if rival is not None and rival - d < AMBIGUOUS_DELTA_DEG:
                free[e] = free[f] = False     # no hay trayectoria clara: se corta
                continue
            partner[e] = f
            partner[f] = e
            free[e] = free[f] = False
    return partner


def _walk(edges: List[_Edge], partner, nodes: Sequence[Pt]) -> List[Route]:
    visited = set()

    def chain_from(ei: int, entry: str) -> List[Tuple[int, bool]]:
        """Entra a `ei` por `entry` y avanza hasta un extremo sin pareja (o cierra el lazo)."""
        chain: List[Tuple[int, bool]] = []
        seen = set()
        cur, side = ei, entry
        while cur not in seen:
            seen.add(cur)
            chain.append((cur, side == "a"))          # a→b si se entra por a
            exit_side = "b" if side == "a" else "a"
            nxt = partner.get((cur, exit_side))
            if nxt is None:
                break
            cur, side = nxt
        return chain

    def component(seed: int) -> List[int]:
        stack, seen = [seed], set()
        while stack:
            e = stack.pop()
            if e in seen:
                continue
            seen.add(e)
            for s in ("a", "b"):
                nxt = partner.get((e, s))
                if nxt:
                    stack.append(nxt[0])
        return list(seen)

    def start_key(ei: int, side: str):
        pl = edges[ei].pl
        kind = (pl.kinds[0] if side == "a" else pl.kinds[-1]) if pl.kinds else "end"
        p = pl.pts[0] if side == "a" else pl.pts[-1]
        return (_START_RANK.get(kind, 2), p[0], p[1], ei)

    order = sorted(range(len(edges)),
                   key=lambda ei: (0 if any((ei, s) not in partner for s in ("a", "b")) else 1, ei))
    routes: List[Route] = []
    for seed in order:
        if seed in visited:
            continue
        comp = component(seed)
        ends = [(e, s) for e in comp for s in ("a", "b") if (e, s) not in partner]
        if ends:
            start_e, start_side = min(ends, key=lambda es: start_key(*es))
            chain = chain_from(start_e, start_side)
        else:
            chain = chain_from(seed, "a")            # lazo: se rota al vértice de menor x
        for ei, _ in chain:
            visited.add(ei)
        routes.append(_concat(edges, chain, nodes))
    return routes


def _concat(edges: List[_Edge], chain: List[Tuple[int, bool]], nodes: Sequence[Pt]) -> Route:
    pts: List[Pt] = []
    kinds: List[str] = []
    members: List[int] = []
    for ei, forward in chain:
        pl = edges[ei].pl
        members.append(edges[ei].idx)
        p = list(pl.pts) if forward else list(reversed(pl.pts))
        k = list(pl.kinds) if forward else list(reversed(pl.kinds))
        if len(k) != len(p):
            k = ["end"] * len(p)
        if not pts:
            pts, kinds = p, k
            continue
        kinds[-1] = _stronger(kinds[-1], k[0])
        pts.extend(p[1:])
        kinds.extend(k[1:])
    # Un lazo cierra donde el último nodo coincide con el primero (a la
    # tolerancia de nodo, no exacta: los extremos unidos pueden diferir <0.6 pt).
    if len(pts) >= 3 and _near(pts[0], pts[-1], NODE_TOL_PT):
        pts, kinds = _rotate_loop(pts, kinds)
    return Route(Polyline(pts, kinds), len(chain), members)


def _rotate_loop(pts: List[Pt], kinds: List[str]):
    closed = _near(pts[0], pts[-1], NODE_TOL_PT)
    body = list(range(len(pts) - 1)) if closed else list(range(len(pts)))
    i = min(body, key=lambda j: (pts[j][0], pts[j][1]))
    if closed:
        rot_p = pts[i:-1] + pts[:i]
        rot_k = kinds[i:-1] + kinds[:i]
        return rot_p + [rot_p[0]], rot_k + [rot_k[0]]
    return pts[i:] + pts[:i], kinds[i:] + kinds[:i]


def _stronger(a: str, b: str) -> str:
    return a if _KIND_RANK.get(a, 9) <= _KIND_RANK.get(b, 9) else b


def _unit(dx: float, dy: float) -> Tuple[float, float]:
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else (1.0, 0.0)


def _near(p: Pt, q: Pt, tol: float = 1e-6) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
