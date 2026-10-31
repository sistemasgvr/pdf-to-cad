"""Puntos «SIN ACCESORIO» (pedido del usuario 2026-10-30): el usuario marca que en ese punto NO va el codo / Tee /
Wye / cruz que la app y el plugin pondrían. PURO (sin Qt).

Cada marca = {"x", "y" (px del lienzo, donde estaba el accesorio), "tipo" ("codo"|"tee"|"wye"|"cruz"),
"conf": [clave, x, y] o None (el conflicto C-n desde el que se marcó)}. Sin índices de utilidades: borrar o
unir utilidades no las desordena. Efecto: ese accesorio no se calcula (plano, normativas, 3D), el conflicto que
lo originó y el cruce con accesorio de ese punto dejan de marcarse, y el DXF lleva un `PDFCAD_SIN_ACCESORIO`
para que el plugin no ponga pieza ahí (las tuberías llegan al punto sin conectarse).
"""
from __future__ import annotations

import math

TOL_FT = 0.5                  # = accesorios.TOL_UNION_FT: el mismo punto del accesorio
CONF_PX = 40.0                # = conflictos.SIGUE_PX: el mismo conflicto aunque se mueva un poco
NOMBRES = {"codo": "codo", "tee": "T", "wye": "Y", "cruz": "cruz"}


def tol_px(ft_per_px):
    return TOL_FT / ft_per_px if ft_per_px else 3.0


def marca(acc, conflicto=None):
    """La marca de un accesorio (dict de `accesorios.accesorios`); `conflicto` = Conflicto C-n o None."""
    m = {"x": float(acc["x"]), "y": float(acc["y"]), "tipo": acc.get("tipo") or ""}
    m["conf"] = [conflicto.clave, float(conflicto.x), float(conflicto.y)] if conflicto is not None else None
    return m


def en(marcas, x, y, tol):
    """La marca a ≤ tol del punto (o None)."""
    for m in marcas or ():
        if math.hypot(m["x"] - x, m["y"] - y) <= tol:
            return m
    return None


def filtrar(accs, marcas, tol):
    """Los accesorios sin los marcados (misma lista si no hay marcas)."""
    if not marcas:
        return accs
    return [a for a in accs if en(marcas, a["x"], a["y"], tol) is None]


def suprime(marcas, clave, x, y, tol):
    """¿El conflicto (clave, x, y) desaparece por una marca? Sí si se marcó desde él o cae en el punto marcado."""
    for m in marcas or ():
        c = m.get("conf")
        if c and c[0] == clave and math.hypot(c[1] - x, c[2] - y) <= CONF_PX:
            return True
        if math.hypot(m["x"] - x, m["y"] - y) <= tol:
            return True
    return False


def de_conflicto(accs, c, tol, radio_px):
    """El accesorio que causa el conflicto C-n `c` (o None): el más cercano a su punto, a ≤ `radio_px`, que
    toca alguna de sus utilidades (si el conflicto las nombra)."""
    suyas = {i for i in (c.pipes or []) if i is not None}
    mejor = None
    for a in accs or ():
        if suyas and not (suyas & set(a.get("pipes") or ())):
            continue
        d = math.hypot(a["x"] - c.x, a["y"] - c.y)
        if d <= max(radio_px, tol) and (mejor is None or d < mejor[0]):
            mejor = (d, a)
    return mejor[1] if mejor else None
