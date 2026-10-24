"""acometidas.py — las ACOMETIDAS reconocidas entran en redes por gravedad y conductos (PURO).

Pedido del usuario (2026-10-14, «QS Sewer» de Phoenix): en agua se importaban la tubería y
las acometidas a los predios; en alcantarillado solo la principal. En una red a PRESIÓN el
plugin parte la tubería en la T (`PartirTramosEnTes`); en gravedad cada vértice lleva una
estructura (`model_ops.rebuild_structures`) y el plugin no parte nada, así que:

  · `unir_a_principal`: la punta «tee» de la acometida (la que `recognition_taps` dejó sobre
    la tubería) pasa a ser un VÉRTICE de esa tubería (`VERTICE`), con la cota del tramo; así
    las dos comparten el nodo en Civil 3D.
  · `model_ops.hide_soft_vertex_structures` deja NULAS (ocultas: «Estructura nula» del
    plugin) las estructuras de ese vértice y de toda la acometida: no son buzones. Un buzón
    real donde llega (vértice duro de otra tubería, bóveda) sigue visible.

Solo entre las tuberías de la MISMA importación y capa; las demás no se tocan. Presión, nada.
"""
from __future__ import annotations

import math

from nucleo import avance, model_ops, unir_ramales
from nucleo.indice_plano import IndiceUtilidades
from nucleo.model import NETWORK_KIND
from traduccion.i18n_core import t as _tr

VERTICE = "acometida"        # tipo del vértice que la acometida agrega en su tubería


def es_acometida(p) -> bool:
    return bool(p.get("acometida"))


def unir_a_principal(pipes, indices, tol_px: float) -> int:
    """Pone en la tubería el vértice donde llega cada acometida (ver el docstring).
    `indices` = las tuberías recién importadas. Devuelve cuántos vértices agregó."""
    nuevas = [pipes[i] for i in indices if 0 <= i < len(pipes)]
    n = 0
    # por celdas, MISMO recorrido y orden (2026-10-23: con 36 mapas de alcantarillado eran 7 000
    # acometidas × 5 000 tuberías): solo las tuberías con un tramo que PUEDE quedar a ≤ tol de la
    # punta, y los vértices de las principales de cada capa (al día con los que se insertan aquí)
    indice = IndiceUtilidades(nuevas) if len(nuevas) > 1 else None
    vertices = {}
    for m in nuevas:
        if not es_acometida(m):
            for v in m.get("pts") or ():
                _poner(vertices, m.get("layer"), v)
    for k_av, tap in enumerate(nuevas):
        avance.avisar(_tr("Uniendo cada acometida a su tubería…"), k_av + 1, len(nuevas))
        if not es_acometida(tap) or NETWORK_KIND.get(tap.get("layer") or "") == "pressure":
            continue
        pts, kinds = tap.get("pts") or [], tap.get("vertex_kinds") or []
        if len(pts) < 2 or len(kinds) != len(pts):
            continue
        for j in (0, len(pts) - 1):
            if kinds[j] != "tee":
                continue
            q = pts[j]
            for mi in (indice.cerca(q[0], q[1], tol_px) if indice is not None else range(len(nuevas))):
                main = nuevas[mi]
                if main is tap or es_acometida(main) or main.get("layer") != tap.get("layer"):
                    continue
                mp = main.get("pts") or []
                if len(mp) < 2:
                    continue
                donde = unir_ramales.punto_interior(q, mp, tol_px)
                if donde is None and not any(math.dist(q, v) <= tol_px for v in (mp[0], mp[-1])):
                    continue
                # junto a un vértice (buzón, otra acometida) la estructura ya es la de ese
                # vértice (`rebuild_structures` junta a ≤ _TOL), también si es de otra tubería:
                # un vértice nuevo ahí movería el buzón a la T
                if donde is not None and donde[0] == "s" and not _junto(vertices, tap.get("layer"), q):
                    k = unir_ramales._insertar_vertice(main, donde[1], donde[2])
                    mk = main.get("vertex_kinds")
                    if isinstance(mk, list) and len(mk) == len(main["pts"]):
                        mk[k] = VERTICE
                    _poner(vertices, main.get("layer"), main["pts"][k])
                    n += 1
                break
    return n


def _poner(vertices, capa, v):
    """Vértice de una tubería principal en su celda (de lado `model_ops._TOL`), por capa."""
    c = model_ops._TOL
    vertices.setdefault(capa, {}).setdefault((math.floor(v[0] / c), math.floor(v[1] / c)), []).append(v)


def _junto(vertices, capa, q):
    """¿Algún vértice de una principal de esa capa a ≤ `model_ops._TOL` de q? (la misma cuenta
    de siempre, solo en las celdas vecinas)."""
    c = model_ops._TOL
    celdas = vertices.get(capa) or {}
    cx, cy = math.floor(q[0] / c), math.floor(q[1] / c)
    return any(math.dist(q, v) <= model_ops._TOL
               for dx in (-1, 0, 1) for dy in (-1, 0, 1) for v in celdas.get((cx + dx, cy + dy), ()))
