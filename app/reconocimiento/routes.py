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

from reconocimiento.recognition_geom import Pattern, Polyline

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


# ─────────────── rutas YA emitidas (con sus codos): seguir la trayectoria ───────────────
EMIT_HEADING_MIN_PT = 1.0    # rumbo local: primer tramo de al menos esto (en un codo = su tangente)
_PASS_KINDS = ("junction", "tee", "end")   # sin tercera línea en el nodo: la ruta solo pasa → «bend»


def join_emitted(lines, scale: float = 1.0) -> list:
    """Une rutas de la MISMA capa y estado (AB) que comparten un extremo y siguen su
    trayectoria, DESPUÉS de ajustar los codos. Solo concatena: ningún vértice ni codo
    cambia, así que el arco que dibuja el editor es el mismo. `lines` son
    `RecognizedPolyline` (px a `scale` = zoom) de UNA capa; se modifican en sitio.

    Es la regla de `_pair` con el rumbo LOCAL (el primer tramo; si nace en un codo,
    la tangente exacta del arco) en vez del medido a ~66 pt, que en una curva cerrada
    daba >100° aunque la línea siga de frente, y para nodos que aparecen después de
    `build_routes` (el hueco de letras que cierra `connect_text_gaps`: la «U» de
    telecom de DU06 h.5 quedaba en dos rutas). Nodo = solo esos DOS extremos (≤
    `NODE_TOL_PT`) y ninguna otra línea de la capa pasando por ahí; giro ≤
    `THETA_DEG2_DEG` (≤ `THETA_JUNCTION_DEG` si un extremo es «tee»); nunca «cut» ni
    si cerraría un lazo (LABOE h.30: el tubo de alcantarillado dibujado como
    rectángulo de 17 pt salía en dos piezas que ya comparten las dos esquinas).
    Una bifurcación («Y», tres extremos) no se toca: no hay una sola trayectoria.
    Devuelve las rutas absorbidas (quien llama las quita de su lista)."""
    live = [pl for pl in lines if len(pl.pts_pdf) >= 2]
    gone = []
    tol, min_len = NODE_TOL_PT * scale, EMIT_HEADING_MIN_PT * scale
    pasos = _Pasos(live, tol)
    pares = _Pares(live, tol, min_len, pasos)
    while True:
        best = pares.mejor()
        if best is None:
            return gone
        _d, i, si, j, sj = best
        a, b = live[i], live[j]
        nodo = a.pts_pdf[0] if si == 0 else a.pts_pdf[-1]
        _absorb(a, si, b, sj)
        pasos.quitar(b)
        pasos.poner(a)                                # (ahora llega hasta donde llegaba la otra)
        gone.append(live.pop(j))
        pares.tras_unir(a, b, nodo)


class _Pasos:
    """Las rutas por celdas de su caja, para «¿otra línea pasa por este nodo?» (`_passes`). En una hoja
    compuesta de 54 mapas (14 mil rutas) cada nodo candidato probaba TODAS las rutas en cada vuelta: 91
    millones de pruebas, 5 de los 12 minutos del reconocimiento (2026-11-15). `en(q)` = las rutas cuya
    caja, agrandada 2·tol, contiene q: toda ruta con un tramo a ≤ tol de q está (la prueba exacta la
    sigue haciendo `_passes`, y es un «alguna»: el orden no importa)."""

    def __init__(self, live, tol: float):
        self.margen = 2.0 * tol
        self.celda = max(64.0 * tol, 1e-6)
        self.celdas: Dict[Tuple[int, int], list] = {}
        self.vivas: Dict[int, tuple] = {}
        for pl in live:
            self.poner(pl)

    def poner(self, pl) -> None:
        xs = [p[0] for p in pl.pts_pdf]
        ys = [p[1] for p in pl.pts_pdf]
        m, c = self.margen, self.celda
        x0, y0, x1, y1 = min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m
        self.vivas[id(pl)] = (pl, x0, y0, x1, y1)
        for cx in range(int(x0 // c), int(x1 // c) + 1):
            for cy in range(int(y0 // c), int(y1 // c) + 1):
                self.celdas.setdefault((cx, cy), []).append(id(pl))

    def quitar(self, pl) -> None:
        self.vivas.pop(id(pl), None)

    def en(self, q: Pt) -> list:
        c = self.celda
        out, vistas = [], set()
        for k in self.celdas.get((int(q[0] // c), int(q[1] // c)), ()):
            v = self.vivas.get(k)
            if v is not None and k not in vistas and v[1] <= q[0] <= v[3] and v[2] <= q[1] <= v[4]:
                vistas.add(k)
                out.append(v[0])
        return out


def _extremos(live, tol):
    """Los extremos (línea, lado, punto) y su rejilla de celdas 4·tol."""
    ends = [(i, s, pl.pts_pdf[0] if s == 0 else pl.pts_pdf[-1])
            for i, pl in enumerate(live) for s in (0, 1)]
    cell = max(tol, 1e-6) * 4
    grid: Dict[Tuple[int, int], List[int]] = {}
    for n, (_i, _s, p) in enumerate(ends):
        grid.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(n)
    return ends, grid, cell


def _par_en(live, ends, grid, cell, n, tol, min_len, pasos):
    """El par que une el nodo del extremo `n` (solo si `n` es el primero de su nodo): (giro, i, si, j, sj) o None."""
    i, si, p = ends[n]
    kx, ky = int(p[0] // cell), int(p[1] // cell)
    # grado del nodo: TODOS los extremos de la capa (también los de otro estado AB)
    near = sorted(m for dx in (-1, 0, 1) for dy in (-1, 0, 1) for m in grid.get((kx + dx, ky + dy), ())
                  if math.dist(ends[m][2], p) <= tol and live[ends[m][0]].layer_ocg == live[i].layer_ocg)
    if len(near) != 2 or near[0] != n:
        return None                                   # nodo de grado ≠ 2 (o ya visto)
    j, sj, q = ends[near[1]]
    if i == j or not _same_net(live[i], live[j]):
        return None                                   # lazo, u otro estado (AB): no es la misma utilidad
    far_i = live[i].pts_pdf[-1 if si == 0 else 0]
    far_j = live[j].pts_pdf[-1 if sj == 0 else 0]
    if math.dist(far_i, far_j) <= tol:
        return None                                   # cerraría un lazo (contorno de un tubo): no es trayectoria
    ka = live[i].kinds[0 if si == 0 else -1]
    kb = live[j].kinds[0 if sj == 0 else -1]
    if "cut" in (ka, kb):
        return None
    if any(_passes(o, p, tol) for o in (live if pasos is None else pasos.en(p))
           if o.layer_ocg == live[i].layer_ocg):
        return None                                   # otra línea pasa por el nodo: es una T
    d = _defl(_local_heading(live[i].pts_pdf, si == 0, min_len),
              _local_heading(live[j].pts_pdf, sj == 0, min_len))
    theta = THETA_JUNCTION_DEG if "tee" in (ka, kb) else THETA_DEG2_DEG
    return (d, i, si, j, sj) if d <= theta else None


def _best_emitted_pair(live, tol, min_len, pasos=None):
    """El mejor par de TODA la capa (menor giro; empate: menor i, luego j). Es lo que `_Pares` mantiene sin
    volver a mirar todos los nodos en cada unión (las pruebas comparan uno con otro)."""
    ends, grid, cell = _extremos(live, tol)
    best = None
    for n in range(len(ends)):
        par = _par_en(live, ends, grid, cell, n, tol, min_len, pasos)
        if par is not None and (best is None or (par[0], par[1], par[3]) < (best[0], best[1], best[3])):
            best = par
    return best


class _Pares:
    """Los pares que se pueden unir, sin volver a mirar toda la capa tras cada unión (2026-11-15: en la compuesta
    de Southwest, 14 mil rutas, `_best_emitted_pair` miraba los 28 mil extremos 56 veces).

    Lo que decide un nodo (`_par_en`) depende solo de los extremos a ≤ tol, de las dos líneas que llegan (sus
    puntas, su rumbo, si cerrarían un lazo) y de las líneas que pasan por él. Unir `b` a `a` solo cambia eso
    cerca del NODO de la unión y de las dos PUNTAS de `a` (la otra punta de `b` es ahora de `a`): ahí se vuelve a
    mirar, con margen (`RADIO` × tol), y lo demás queda como estaba. El elegido es el MISMO: menor giro y, en
    empate, menor índice ACTUAL de las dos líneas (quitar una línea corre los índices de las siguientes sin
    cambiar su orden)."""
    RADIO = 3.0

    def __init__(self, live, tol, min_len, pasos):
        self.live, self.tol, self.min_len, self.pasos = live, tol, min_len, pasos
        ends, grid, cell = _extremos(live, tol)
        self.pares: Dict[Tuple[int, int], tuple] = {}            # (id línea, lado) del primer extremo → par
        for n in range(len(ends)):
            self._mirar(ends, grid, cell, n)

    def _mirar(self, ends, grid, cell, n) -> None:
        par = _par_en(self.live, ends, grid, cell, n, self.tol, self.min_len, self.pasos)
        if par is not None:
            d, i, si, j, sj = par
            self.pares[(id(self.live[i]), si)] = (d, self.live[i], si, self.live[j], sj, ends[n][2])

    def mejor(self):
        if not self.pares:
            return None
        indice = {id(pl): k for k, pl in enumerate(self.live)}
        d, a, sa, b, sb, _p = min(self.pares.values(), key=lambda v: (v[0], indice[id(v[1])], indice[id(v[3])]))
        return d, indice[id(a)], sa, indice[id(b)], sb

    def tras_unir(self, a, b, nodo) -> None:
        lugares = [nodo, a.pts_pdf[0], a.pts_pdf[-1]]
        r = self.RADIO * self.tol
        self.pares = {k: v for k, v in self.pares.items()
                      if v[1] is not a and v[1] is not b and v[3] is not a and v[3] is not b
                      and not any(math.dist(v[5], q) <= r for q in lugares)}
        ends, grid, cell = _extremos(self.live, self.tol)
        vistos = set()
        for q in lugares:
            kx0, ky0 = int((q[0] - r) // cell), int((q[1] - r) // cell)
            kx1, ky1 = int((q[0] + r) // cell), int((q[1] + r) // cell)
            for kx in range(kx0, kx1 + 1):
                for ky in range(ky0, ky1 + 1):
                    for n in grid.get((kx, ky), ()):
                        if n not in vistos and math.dist(ends[n][2], q) <= r:
                            vistos.add(n)
                            self._mirar(ends, grid, cell, n)


def _same_net(a, b) -> bool:
    return a.layer_ocg == b.layer_ocg and bool(a.abandoned) == bool(b.abandoned)


def _local_heading(pts, first: bool, min_len: float) -> Tuple[float, float]:
    """Rumbo con el que la ruta LLEGA a su extremo, con el primer tramo ≥ `min_len`."""
    seq = pts if first else pts[::-1]
    q = seq[0]
    back = next((p for p in seq[1:] if math.dist(p, q) >= min_len), seq[-1])
    return _unit(q[0] - back[0], q[1] - back[1])


def _passes(pl, q: Pt, tol: float) -> bool:
    """La ruta pasa por q por su INTERIOR (un extremo suyo ahí no cuenta)."""
    pts = pl.pts_pdf
    if math.dist(pts[0], q) <= tol or math.dist(pts[-1], q) <= tol:
        return False
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L < 1e-9:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        t = (q[0] - a[0]) * ux + (q[1] - a[1]) * uy
        if -tol <= t <= L + tol and abs((q[0] - a[0]) * uy - (q[1] - a[1]) * ux) <= tol:
            return True
    return False


def _reversed_fillets(fillets: dict, n: int) -> dict:
    """Codos de la polilínea invertida: índice n-1-i y los lados a/b cambiados."""
    out = {}
    for i, g in fillets.items():
        h = dict(g)
        for x, y in (("a", "b"), ("node_a", "node_b"), ("split_a", "split_b")):
            if x in g or y in g:
                h.pop(x, None); h.pop(y, None)
                if y in g:
                    h[x] = g[y]
                if x in g:
                    h[y] = g[x]
        out[n - 1 - i] = h
    return out


def _absorb(a, sa: int, b, sb: int) -> None:
    """`a` se queda con `b` pegada por el extremo compartido (sin invertir `a`)."""
    n = len(b.pts_pdf)
    bp, bk, bf = list(b.pts_pdf), list(b.kinds), dict(b.fillets or {})
    if (sa == 1) == (sb == 1):                        # `b` tiene que llegar/salir por el otro lado
        bp, bk, bf = bp[::-1], bk[::-1], _reversed_fillets(bf, n)
    ap, ak, af = list(a.pts_pdf), list(a.kinds), dict(a.fillets or {})
    if sa == 1:                                       # a … nodo … b
        first, fk, ff, second, sk, sf = ap, ak, af, bp, bk, bf
    else:                                             # b … nodo … a
        first, fk, ff, second, sk, sf = bp, bk, bf, ap, ak, af
    joint = _stronger(fk[-1], sk[0])
    if joint in _PASS_KINDS:
        joint = "bend"
    shift = len(first) - 1
    a.pts_pdf = first + second[1:]
    a.kinds = fk[:-1] + [joint] + sk[1:]
    a.fillets = {**ff, **{i + shift: g for i, g in sf.items()}}
    a.n_segments = int(a.n_segments or 0) + int(b.n_segments or 0)
    a.review = a.review or b.review


def _unit(dx: float, dy: float) -> Tuple[float, float]:
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else (1.0, 0.0)


def _near(p: Pt, q: Pt, tol: float = 1e-6) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
