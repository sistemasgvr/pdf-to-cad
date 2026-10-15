"""Un VÉRTICE de eléctrico o telecom pasa a CURVA, y vuelve (PURO: sin Qt).

Pedido del usuario 2026-10-15. En las redes de conductos (eléctrico, telecom) no hay
cajas automáticas en los vértices (`model_ops.rebuild_structures`, regla de 2026-09-28):
la curva solo se podía hacer convirtiendo una caja, así que un vértice simple no tenía cómo
volverse curva. Aquí la curva se crea con la MISMA marca CV que ya usan los codos
reconocidos de estas redes (`model_ops.attach_fillets`): radio automático (0 = 6 × diámetro,
como el editor y el plugin) y `vertice=True`. `rebuild_structures` conserva las estructuras
de conductos, así que la marca no se pierde.

Quitar la curva de un vértice que no tenía caja (`vertice` o `quiebre` del plano) la
BORRA: el vértice vuelve a ser un vértice simple. Antes «Volver a tratar como buzón/caja»
dejaba ahí una CAJA que nunca existió.
"""
from __future__ import annotations

import math

from nucleo import model_ops
from nucleo.model import network_kind


def es_conductos(pipe):
    return network_kind((pipe or {}).get("layer") or "") == "conduit"


def _ocupado(pt, structures, tol=model_ops._TOL):
    return any(not s.get("world") and s.get("x") is not None
               and math.hypot(float(s["x"]) - pt[0], float(s["y"]) - pt[1]) <= tol for s in structures or [])


def vertices_libres(pipe, structures):
    """Índices de los vértices INTERIORES de una utilidad de conductos sin nada encima (ni
    caja ni curva): los que pueden pasar a curva. Las puntas no: una curva necesita dos tramos."""
    if not es_conductos(pipe) or pipe.get("world"):
        return []
    pts = pipe.get("pts") or []
    return [k for k in range(1, len(pts) - 1) if not _ocupado(pts[k], structures)]


def vertice_en(pipe, structures, x, y, tol_px):
    """El vértice libre de `pipe` más cercano a (x, y) a ≤ tol_px, o None."""
    pts = pipe.get("pts") or []
    mejor = None
    for k in vertices_libres(pipe, structures):
        d = math.hypot(pts[k][0] - x, pts[k][1] - y)
        if d <= tol_px and (mejor is None or d < mejor[0]):
            mejor = (d, k)
    return None if mejor is None else mejor[1]


def a_curva(structures, pipe, k):
    """Agrega la marca de curva (CV, radio automático) en el vértice k. Devuelve la estructura
    (sin código: `rebuild_structures` le pone CV-N)."""
    x, y = pipe["pts"][k]
    s = {"cod": "", "x": float(x), "y": float(y), "rim": None, "sump": None, "part": "", "part_size": "",
         "net": "conduit", "covered": True, "world": False, "hidden": False,
         "curve": True, "radius_ft": 0.0, "vertice": True}
    structures.append(s)
    return s


def se_quita(s):
    """¿Quitar esta curva la BORRA (el vértice no tenía caja)? Curvas de conductos hechas en un
    vértice simple: a mano (`vertice`) o desde un quiebre del plano (`quiebre`)."""
    return bool(s.get("curve")) and (s.get("net") or "") == "conduit" and bool(s.get("vertice") or s.get("quiebre"))
