"""«Reconocer más capas…» — lo reconocido que YA está dibujado en el editor no entra otra vez.

Pedido del usuario 2026-11-12 (recomendación 1 de la revisión): una vez importadas las tuberías por
capas y avanzado el lienzo, poder reconocer otras capas de la misma hoja sin perder lo hecho. Lo nuevo
entra ENCIMA; si el usuario vuelve a marcar una utilidad que ya importó, sus líneas saldrían dos veces:
`quitar_repetidas` deja fuera cada línea nueva que corre entera sobre una del editor de la misma capa
(utilidad) y el mismo estado (activa / abandonada). PURO: sin Qt.
"""
from __future__ import annotations

import math


def _dist_seg(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _muestras(pts, paso):
    """Vértices + puntos cada `paso` a lo largo de la línea."""
    out = []
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i][:2], pts[i + 1][:2]
        largo = math.hypot(bx - ax, by - ay)
        n = max(1, int(largo / paso)) if paso > 0 else 1
        for k in range(n):
            out.append((ax + (bx - ax) * k / n, ay + (by - ay) * k / n))
    if pts:
        out.append(tuple(pts[-1][:2]))
    return out


def _caja(pts, margen=0.0):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs) - margen, min(ys) - margen, max(xs) + margen, max(ys) + margen


def _sobre(px, py, pts, tol) -> bool:
    return any(_dist_seg(px, py, *pts[i][:2], *pts[i + 1][:2]) <= tol for i in range(len(pts) - 1))


def repetida(nueva: dict, existentes: list, tol: float) -> bool:
    """¿Toda la línea `nueva` corre a ≤ `tol` de las líneas del editor de su capa y estado?"""
    pts = nueva.get("pts") or []
    if len(pts) < 2:
        return False
    capa, ab = nueva.get("layer"), bool(nueva.get("ab"))
    cx0, cy0, cx1, cy1 = _caja(pts, tol)
    cerca = []
    for p in existentes:
        q = p.get("pts") or []
        if len(q) < 2 or p.get("layer") != capa or bool(p.get("ab")) != ab:
            continue
        x0, y0, x1, y1 = _caja(q)
        if x1 < cx0 or x0 > cx1 or y1 < cy0 or y0 > cy1:
            continue
        cerca.append(q)
    if not cerca:
        return False
    return all(any(_sobre(x, y, q, tol) for q in cerca) for x, y in _muestras(pts, 4.0 * tol))


def quitar_repetidas(existentes: list, nuevas: list, tol: float):
    """→ (las nuevas que no están dibujadas, cuántas se quitaron)."""
    quedan = [p for p in nuevas if not repetida(p, existentes, tol)]
    return quedan, len(nuevas) - len(quedan)
