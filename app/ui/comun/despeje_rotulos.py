"""Despeje de rótulos del lienzo (pedido del usuario 2026-10-17, «nivel de detalle como Google Maps o
Civil 3D»): con la vista entera de un mapa de 16 761 utilidades las etiquetas de los accesorios y los
C-n se amontonaban. Como en los visores de mapas, de las etiquetas que se TAPAN en pantalla se dibuja
solo una —la de más prioridad—; los puntos (rombo, círculo de cruce, triángulo, insignia) siempre. Al
acercarse se separan y aparecen todas.

PURO (numpy, sin Qt): `despejar(cajas)` decide, en orden de prioridad, cuáles caben sin tocar una ya
puesta (voraz, como el «label placement» de los mapas). Rejilla dispersa de celdas: cada rótulo solo se
compara con los ya puestos de sus celdas.
"""
from __future__ import annotations

import math

import numpy as np

CELDA_PX = 64.0                   # celda de la rejilla, px de pantalla
HOLGURA_PX = 1.0                  # dos rótulos que solo se rozan no se tapan


def despejar(cajas):
    """`cajas` = array (n, 4) de (x0, y0, x1, y1) en px de pantalla, en ORDEN DE PRIORIDAD. Devuelve un
    array booleano: True = se dibuja (no toca ninguna caja anterior que se dibuja)."""
    n = len(cajas)
    puestos = np.zeros(n, dtype=bool)
    if n == 0:
        return puestos
    c = np.asarray(cajas, dtype=float)
    x0, y0 = c[:, 0] + HOLGURA_PX, c[:, 1] + HOLGURA_PX
    x1, y1 = c[:, 2] - HOLGURA_PX, c[:, 3] - HOLGURA_PX
    cx0, cy0 = np.floor(x0 / CELDA_PX).astype(np.int64), np.floor(y0 / CELDA_PX).astype(np.int64)
    cx1, cy1 = np.floor(x1 / CELDA_PX).astype(np.int64), np.floor(y1 / CELDA_PX).astype(np.int64)
    rejilla = {}
    L, T, R, B = x0.tolist(), y0.tolist(), x1.tolist(), y1.tolist()
    for i, (a0, b0, a1, b1) in enumerate(zip(cx0.tolist(), cy0.tolist(), cx1.tolist(), cy1.tolist())):
        l, t, r, b = L[i], T[i], R[i], B[i]
        if not (r >= l and b >= t) or not math.isfinite(l + t + r + b):
            continue
        celdas = [(gx, gy) for gx in range(a0, a1 + 1) for gy in range(b0, b1 + 1)]
        choca = False
        for celda in celdas:
            for j in rejilla.get(celda, ()):
                if l <= R[j] and r >= L[j] and t <= B[j] and b >= T[j]:
                    choca = True
                    break
            if choca:
                break
        if choca:
            continue
        puestos[i] = True
        for celda in celdas:
            rejilla.setdefault(celda, []).append(i)
    return puestos
