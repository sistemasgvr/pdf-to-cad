"""Rótulos de la Vista 3D: pendiente de cada tramo y ángulo de cada quiebre (PURO).

Pedido del usuario 2026-10-16 (opción «Ángulos y pendientes» de la Vista 3D): sobre el EJE de
cada utilidad visible, en el medio de cada tramo su pendiente (%, la de Civil 3D: cada tramo es
una tubería, `model_ops.pendientes_tramos`) y en cada vértice interior su giro (deflexión sobre
el eje prolongado, como los accesorios). Se dibujan con QPainter encima del modelo
(`ui/comun/etiquetas3d`), con el id de su utilidad (se resaltan con ella).
"""
from __future__ import annotations

import math

from nucleo import accesorios as acc
from nucleo import model_ops

GIRO_MIN_DEG = 0.01               # menos es un vértice en recta: sin rótulo


def rotulos(ar, pipes, visibles, alto_de):
    """[(id, punto 3D en pies del mundo, texto)]. `alto_de(p)` = alto interior (ft) para el eje."""
    out = []
    for i in visibles:
        p = pipes[i]
        pts = p.get("pts") or []
        if len(pts) < 2 or p.get("world"):
            continue
        alto = alto_de(p)
        pend = model_ops.pendientes_tramos(p, ar.ft)
        for k, s in enumerate(pend):
            if s is None:
                continue
            mx, my = (pts[k][0] + pts[k + 1][0]) / 2.0, (pts[k][1] + pts[k + 1][1]) / 2.0
            z = model_ops.z_en_tramo(p, k, mx, my)
            if z is None:
                continue
            out.append((i + 1, (*ar.mundo(mx, my, 0)[:2], z + alto), f"{s:.2f} %"))
        for k in range(1, len(pts) - 1):
            a, v, b = pts[k - 1], pts[k], pts[k + 1]
            r1 = math.atan2(v[1] - a[1], v[0] - a[0])
            r2 = math.atan2(b[1] - v[1], b[0] - v[0])
            giro = abs(math.degrees((r2 - r1 + math.pi) % (2 * math.pi) - math.pi))
            z = model_ops.z_en_tramo(p, k, v[0], v[1])
            if giro < GIRO_MIN_DEG or z is None:
                continue
            out.append((i + 1, (*ar.mundo(v[0], v[1], 0)[:2], z + alto * 1.5), acc.texto_angulo(giro)))
    return out
