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

from nucleo import model_ops, unir_ramales
from nucleo.model import NETWORK_KIND

VERTICE = "acometida"        # tipo del vértice que la acometida agrega en su tubería


def es_acometida(p) -> bool:
    return bool(p.get("acometida"))


def unir_a_principal(pipes, indices, tol_px: float) -> int:
    """Pone en la tubería el vértice donde llega cada acometida (ver el docstring).
    `indices` = las tuberías recién importadas. Devuelve cuántos vértices agregó."""
    nuevas = [pipes[i] for i in indices if 0 <= i < len(pipes)]
    n = 0
    for tap in nuevas:
        if not es_acometida(tap) or NETWORK_KIND.get(tap.get("layer") or "") == "pressure":
            continue
        pts, kinds = tap.get("pts") or [], tap.get("vertex_kinds") or []
        if len(pts) < 2 or len(kinds) != len(pts):
            continue
        for j in (0, len(pts) - 1):
            if kinds[j] != "tee":
                continue
            q = pts[j]
            for main in nuevas:
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
                if donde is not None and donde[0] == "s" and not any(
                        math.dist(q, v) <= model_ops._TOL for m in nuevas if not es_acometida(m)
                        and m.get("layer") == tap.get("layer") for v in m.get("pts") or ()):
                    k = unir_ramales._insertar_vertice(main, donde[1], donde[2])
                    mk = main.get("vertex_kinds")
                    if isinstance(mk, list) and len(mk) == len(main["pts"]):
                        mk[k] = VERTICE
                    n += 1
                break
    return n
