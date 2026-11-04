"""Cada aviso de una utilidad SOBRE la línea que se dibuja (PURO: sin Qt).

Reporte del usuario 2026-11-03 (DU10): avisos «fuera de la línea, sin ningún sentido». Las reglas calculan su
punto sobre los VÉRTICES de la utilidad, y el vértice de una curva es una esquina virtual: el arco pasa lejos de
ella (86 de 774 avisos de reconocimiento a más de 0.05 ft de su línea, hasta 24.8 ft). Aquí cada aviso pasa al
punto más cercano de lo dibujado. En un tramo recto no cambia nada, ni un decimal.

`Aviso.lugar` conserva el punto de la regla: identifica la aprobación (`normas_aprobacion.clave`), y así lo aprobado
en un proyecto guardado sigue aprobado aunque el aviso ahora se muestre sobre el arco.
"""
from __future__ import annotations

from nucleo import limpieza_tramos, model_ops

# Su punto ES el del accesorio: la etiqueta lo busca ahí (`accesorios_view.preparar`)
CLASES_FIJAS = frozenset({"accesorio"})
TOL_PX = 1e-6


def dibujo(pipes, structures, i, ft):
    """La polilínea que se dibuja de la utilidad i (= `Main._pipe_display_pts`): cada vértice curvo, su arco."""
    pts = pipes[i].get("pts") or []
    if len(pts) < 3:
        return pts
    _cv, geos = limpieza_tramos.curvas(pipes, structures, i, ft)
    if not geos:
        return pts
    out = [pts[0]]
    for j in range(1, len(pts)):
        if j in geos:
            out.extend(geos[j]["arc"])
        else:
            out.append(pts[j])
    return out


def _mas_cercano(x, y, poli):
    """(distancia², qx, qy): el punto de la polilínea más cercano a (x, y)."""
    mejor, bx, by = float("inf"), x, y
    for (ax, ay), (cx, cy) in zip(poli, poli[1:]):
        dx, dy = cx - ax, cy - ay
        L2 = dx * dx + dy * dy
        k = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2)) if L2 > 0 else 0.0
        qx, qy = ax + k * dx, ay + k * dy
        d = (qx - x) ** 2 + (qy - y) ** 2
        if d < mejor:
            mejor, bx, by = d, qx, qy
    return mejor, bx, by


def sobre_lo_dibujado(avisos, pipes, structures, ft):
    """Lleva cada aviso de una utilidad al punto más cercano de su línea dibujada. `ft` = pies por px del
    lienzo. Devuelve la misma lista."""
    if not ft:
        return avisos
    dibujos = {}
    with model_ops.indice_vertices():
        for a in avisos:
            i = a.pipe
            if a.clase in CLASES_FIJAS or i is None or not 0 <= i < len(pipes) or pipes[i].get("world"):
                continue
            poli = dibujos.get(i)
            if poli is None:
                poli = dibujos[i] = dibujo(pipes, structures, i, ft)
            if len(poli) < 2:
                continue
            d, qx, qy = _mas_cercano(a.x, a.y, poli)
            if d > TOL_PX * TOL_PX:
                a.lugar = a.lugar or (a.x, a.y)
                a.x, a.y = qx, qy
    return avisos
