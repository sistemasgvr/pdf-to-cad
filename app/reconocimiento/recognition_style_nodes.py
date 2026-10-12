"""recognition_style_nodes.py — buzones en los CORTES de la red de un mapa sin capas (PURO).

Los mapas SIG de redes por gravedad (Quarter Section de Phoenix, «QS Sewer»; pedido del
usuario 2026-10-10, PDF aplanado sin capas, la red en un ESTILO: negro 0.73 pt) dibujan
cada tubería como UN trazo de buzón a buzón: donde terminan dos o más trazos de la red hay
un buzón (medido en la hoja 17-10: los 104 puntos así caen todos en el círculo de un
buzón). El símbolo del buzón no está en los vectores (es un glifo de la fuente Type3), así
que sin este paso esos quiebres salían como `bend`/`corner` y, al importar, se volvían
CURVAS (`quiebres_curvas`) en vez de buzones.

Este paso, sobre la salida y sin tocar el núcleo ni mover nada:
  · Solo capas por ESTILO (`pdf_styles.PREFIX`) de utilidades por GRAVEDAD: en una capa
    CAD con nombre la regla no se usa (ahí la línea va partida por guiones y letras).
  · Nodo = extremo compartido por ≥2 trazos de la capa de ≥`MIN_CHAIN_PT` (las flechas de
    sentido y los ticks no cuentan), a ≤`NODE_TOL_PT` entre sí.
  · El vértice de la polilínea sobre el nodo (≤`SNAP_PT`) pasa a «vault»; si la línea
    pasa de largo (dos tuberías colineales: el núcleo las juntó sin vértice) se inserta
    el vértice «vault» en el pie del nodo sobre su parte RECTA dibujada. Nunca en la
    esquina de un codo (un buzón no es una curva: ese caso se cuenta y se deja).
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

from hoja import pdf_styles
from reconocimiento import recognition_vault_through as through_mod

Pt = Tuple[float, float]

MIN_CHAIN_PT = 10.0          # trazo de la red: más corto es flecha, tick o astilla
NODE_TOL_PT = 0.6            # extremos de trazos distintos a ≤ esto = el mismo nodo
SNAP_PT = 1.0                # vértice de la polilínea a ≤ esto del nodo (pt, × zoom en px)
KEEP_KINDS = ("cut", "edge", "vault", "stop")   # ya son nodos o cortes: no se tocan


def is_style_layer(ocg: str) -> bool:
    return (ocg or "").startswith(pdf_styles.PREFIX)


def _chains(path: dict) -> List[List[Pt]]:
    """Ristras CONECTADAS del trazo (un trazo puede traer varios subtrazos)."""
    out: List[List[Pt]] = []
    cur: List[Pt] = []
    for it in path.get("items") or ():
        kind = it[0]
        if kind not in ("l", "c"):
            if cur:
                out.append(cur)
            cur = []
            continue
        a, b = (float(it[1][0]), float(it[1][1])), (float(it[-1][0]), float(it[-1][1]))   # Point o tupla
        if cur and math.dist(cur[-1], a) > 0.05:
            out.append(cur)
            cur = []
        if not cur:
            cur.append(a)
        cur.append(b)
    if cur:
        out.append(cur)
    return out


def _length(pts: Sequence[Pt]) -> float:
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def feature_nodes(paths: Sequence[dict]) -> List[Pt]:
    """Nodos (coords PDF) de una capa: extremos compartidos por ≥2 trazos de la red."""
    ends: List[Tuple[Pt, int]] = []
    for i, p in enumerate(paths):
        for chain in _chains(p):
            if len(chain) < 2 or _length(chain) < MIN_CHAIN_PT:
                continue
            if math.dist(chain[0], chain[-1]) <= NODE_TOL_PT:
                continue                               # cerrado: un símbolo, no una tubería
            ends.append((chain[0], i))
            ends.append((chain[-1], i))
    nodes: List[List] = []                             # [x, y, {trazos}]
    for (x, y), i in ends:
        for n in nodes:
            if math.hypot(n[0] - x, n[1] - y) <= NODE_TOL_PT:
                n[2].add(i)
                break
        else:
            nodes.append([x, y, {i}])
    return [(n[0], n[1]) for n in nodes if len(n[2]) >= 2]


def _inside_fillet(pl, j: int) -> bool:
    """¿El vértice j es la esquina de un codo?"""
    return j in (pl.fillets or {})


def mark_feature_nodes(polylines: Sequence, nodes_px: Dict[str, List[Pt]], zoom: float) -> dict:
    """Marca «vault» en las polilíneas de las capas de `nodes_px` (nodos ya en px). Modifica
    `polylines` en su lugar. Devuelve {"at": [(x, y) px], "fillet": nodos sobre un codo}."""
    tol = SNAP_PT * zoom
    hits: List[Pt] = []
    on_fillet = 0
    for pl in polylines:
        nodes = nodes_px.get(pl.layer_ocg)
        if not nodes or len(pl.pts_pdf) < 2 or len(pl.kinds) != len(pl.pts_pdf):
            continue
        for q in nodes:
            near = [j for j, p in enumerate(pl.pts_pdf) if math.dist(p, q) <= tol]
            if near:
                j = min(near, key=lambda j: math.dist(pl.pts_pdf[j], q))
                if _inside_fillet(pl, j):
                    on_fillet += 1
                    continue
                if pl.kinds[j] not in KEEP_KINDS:
                    pl.kinds[j] = "vault"
                hits.append(tuple(pl.pts_pdf[j]))
                continue
            best = None
            for k, s, e in through_mod._straight_parts(pl):
                f = through_mod._foot(q, s, e)
                if f is None:
                    continue
                foot, t, off = f
                if 0.0 < t < 1.0 and off <= tol and (best is None or off < best[0]):
                    best = (off, k, foot)
            if best is not None:
                _, k, foot = best
                through_mod._insert_vertex(pl, k, foot, "vault")
                hits.append(tuple(foot))
    return {"at": hits, "fillet": on_fillet}
