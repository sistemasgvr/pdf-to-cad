"""Cotas de las conexiones verticales aprobadas, siempre al día (PURO: sin Qt).

Reporte del usuario 2026-10-15: al aprobar una conexión vertical se guardaban las cotas de
ESE momento (`z_a`, `z_b`) y, si después se cambiaba la rasante de una de las dos utilidades,
el DXF y la Vista 3D seguían con las viejas (la vertical salía al nivel anterior en Civil 3D).
`actualizar_cotas` las vuelve a leer de las tuberías, en el punto del cruce y con el MISMO
tramo que usa el lienzo para clasificar el cruce (el más cercano; en un vértice, el de menor
índice, como el recorrido de `_draw_pipe_conflicts`).
"""
from __future__ import annotations

import math

from nucleo import model_ops


def _dist_tramo(a, b, x, y):
    L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / L2))
    return math.hypot(a[0] + (b[0] - a[0]) * t - x, a[1] + (b[1] - a[1]) * t - y)


def cota_en(p, x, y):
    """Solera de la utilidad `p` en (x, y) px (tramo más cercano), o None."""
    pts = p.get("pts") or []
    if len(pts) < 2:
        return None
    k = min(range(len(pts) - 1), key=lambda k: _dist_tramo(pts[k], pts[k + 1], x, y))
    return model_ops.z_en_tramo(p, k, x, y)


def actualizar_cotas(pipes, conexiones):
    """Pone en cada conexión aprobada las cotas actuales de sus utilidades (en sitio).
    Devuelve cuántas cambiaron."""
    n = 0
    for c in conexiones or []:
        try:
            x, y = float(c["x"]), float(c["y"])
            ia, ib = int(c["pipe_a"]), int(c["pipe_b"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= ia < len(pipes) and 0 <= ib < len(pipes)):
            continue
        for clave, i in (("z_a", ia), ("z_b", ib)):
            z = cota_en(pipes[i], x, y)
            z = None if z is None else float(z)
            viejo = c.get(clave)
            if (viejo is None) != (z is None) or (z is not None and abs(float(viejo) - z) > 1e-9):
                c[clave] = z
                n += 1
    return n
