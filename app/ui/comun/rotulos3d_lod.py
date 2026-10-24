"""Qué rótulos de la Vista 3D se dibujan en cada cuadro (PURO: numpy, sin Qt; junto a
`despeje_rotulos`) — nivel de detalle como el plano (pedido del usuario 2026-10-20: con «Ángulos y
pendientes por tramo» y AGUA 2 eran 35 766 rótulos dibujados en CADA cuadro, 3.2 s por cuadro: la
navegación se trababa y no se podía ni hacer zoom).

Como el plano (`ui/comun/despeje_rotulos`) y los visores de mapas:
  1. Solo lo que cae en la pantalla y delante de la cámara (todos los puntos se proyectan juntos).
  2. Nivel de detalle: un rótulo con LARGO (el tramo que rotula, ft) se muestra solo si ese tramo mide en
     pantalla al menos lo que su rótulo; de lejos los tramos son cortos y sus rótulos no salen.
  3. De los que se TAPAN, uno solo —el de más prioridad: los de lo elegido/señalado primero, luego el
     tramo más largo en pantalla— (`despejar`, voraz), y como mucho `MAXIMO`.
Mismo resultado para la misma cámara: el visor lo memoriza mientras la cámara no cambie.
"""
from __future__ import annotations

import numpy as np

from ui.comun.despeje_rotulos import despejar

MAXIMO = 300                        # rótulos a la vez (más no se leen)
HOLGURA_PX = 6.0                    # el tramo tiene que medir en pantalla el rótulo + esto
CELDA = (32.0, 16.0)                # rejilla para descartar de entrada los que caen juntos (px)
CANDIDATOS = 4                      # a `despejar` llegan como mucho MAXIMO × esto


def elegir(P, ids, anchos, largos, m, w, h, k_px, alto=16.0, dy=-8.0, primero=(), maximo=MAXIMO):
    """Rótulos a dibujar, en orden de prioridad: (índices, x, y) con (x, y) = centro del rótulo en px.

    `P` (n, 3) puntos; `ids` (n,) id de su objeto; `anchos` (n,) px de cada rótulo; `largos` (n,) ft
    del tramo que rotula (NaN = sin nivel de detalle, siempre que quepa); `m` matriz vista-proyección 4×4;
    `k_px` = (alto de la vista / 2) / tan(fov / 2): px que mide 1 ft a 1 ft de la cámara; `dy` = desfase
    vertical de la caja respecto del punto; `primero` = ids que van antes (elegido, señalado)."""
    vacio = (np.zeros(0, int), np.zeros(0), np.zeros(0))
    n = len(P)
    if not n:
        return vacio
    c = np.c_[P, np.ones(n)] @ np.asarray(m, float).T
    cw = c[:, 3]
    ok = cw > 1e-6
    cw_s = np.where(ok, cw, 1.0)
    x = (c[:, 0] / cw_s + 1.0) / 2.0 * w
    y = (1.0 - c[:, 1] / cw_s) / 2.0 * h
    medio = anchos / 2.0
    ok &= (x + medio >= 0) & (x - medio <= w) & (y + dy + alto >= 0) & (y + dy <= h)
    pantalla = np.where(np.isnan(largos), np.inf, largos * k_px / cw_s)
    ok &= pantalla >= anchos + HOLGURA_PX
    idx = np.nonzero(ok)[0]
    if not len(idx):
        return vacio
    antes = np.isin(ids[idx], np.asarray(list(primero), dtype=ids.dtype)) if primero else np.zeros(len(idx), bool)
    # orden: primero lo elegido; luego el tramo más largo en pantalla; empate = el orden de la lista
    orden = np.lexsort((idx, -np.minimum(pantalla[idx], 1e12), ~antes))
    idx = idx[orden]
    # descarte de entrada: de los que caen en la misma celda solo el primero (se taparían igual)
    cx = np.floor(x[idx] / CELDA[0]).astype(np.int64)
    cy = np.floor((y[idx] + dy) / CELDA[1]).astype(np.int64)
    _u, primeros = np.unique(cx * 1_000_003 + cy, return_index=True)
    idx = idx[np.sort(primeros)][:maximo * CANDIDATOS]
    cajas = np.c_[x[idx] - medio[idx], y[idx] + dy, x[idx] + medio[idx], y[idx] + dy + alto]
    puestos = despejar(cajas)
    idx = idx[puestos][:maximo]
    return idx, x[idx], y[idx]
