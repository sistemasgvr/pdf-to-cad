"""Válvulas con tubería a cada lado (2026-11-21, pedido del usuario: «es ilógico que haya una válvula sin una tubería
conectada»). El SIG parte la línea en el símbolo de la válvula y, a veces, no dibuja el tramo que la une a la
principal: la tubería termina junto a la válvula y la línea sigue más allá, sin nada en medio. PURO.

Regla: la punta LIBRE de una tubería (ninguna otra pasa por ella) a ≤ `RADIO_PUNTA` × el tamaño del símbolo de una
válvula de su utilidad se prolonga por su MISMA recta, atravesando la válvula, hasta la primera tubería de esa
utilidad que corte ese rayo en `LARGO_MAX` × el tamaño del símbolo (ángulo ≥ `ANGULO_MIN`°). La punta queda sobre
esa tubería (una T); no se mueve ningún otro vértice. Sin tubería delante, no cambia nada."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

RADIO_PUNTA = 2.0          # la punta libre está a ≤ esto × el símbolo de la válvula
LARGO_MAX = 8.0            # y se prolonga a lo más esto × el símbolo (contado desde la punta)
ANGULO_MIN = 20.0          # la tubería que se encuentra no puede ir casi paralela
TOCA_PX = 0.6              # una punta que cae a ≤ esto de otra tubería ya está conectada
SIMBOLO_MIN_PX = 4.0


def _dist_seg(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
    return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def _rayo(o, d, a, b) -> Optional[Tuple[float, float]]:
    """(t, ángulo°) donde el rayo o + t·d corta el tramo a–b (t > 0), o None."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = d[0] * ey - d[1] * ex
    if abs(den) < 1e-12:
        return None
    wx, wy = a[0] - o[0], a[1] - o[1]
    t = (wx * ey - wy * ex) / den
    u = (wx * d[1] - wy * d[0]) / den
    if t <= 1e-9 or u < -1e-9 or u > 1 + 1e-9:
        return None
    L = math.hypot(ex, ey)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, abs(d[0] * ex + d[1] * ey) / L))))
    return t, ang


def _libre(pipes, i, pt, cerca) -> bool:
    for j in cerca(pt[0], pt[1], TOCA_PX + 1.0):
        if j == i:
            continue
        q = pipes[j].get("pts") or ()
        for a, b in zip(q, q[1:]):
            if _dist_seg(pt[0], pt[1], a, b) <= TOCA_PX:
                return False
    return True


def _salida(pts, lado) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """(punta, dirección unitaria hacia afuera de la tubería) del extremo `lado` (0 = inicio, 1 = fin)."""
    if len(pts) < 2:
        return None
    p, q = (pts[0], pts[1]) if lado == 0 else (pts[-1], pts[-2])
    L = math.hypot(p[0] - q[0], p[1] - q[1])
    if L <= 1e-9:
        return None
    return (p[0], p[1]), ((p[0] - q[0]) / L, (p[1] - q[1]) / L)


def conectar(pipes: List[dict], valvulas: Sequence[dict], cerca=None) -> List[Tuple[int, int, float]]:
    """Prolonga EN SITIO las puntas libres junto a cada válvula. → [(utilidad, lado, largo px)] de lo que cambió."""
    if cerca is None:
        cerca = lambda x, y, r: range(len(pipes))          # noqa: E731
    hechos = []
    for v in valvulas or ():
        sim = max(float(v.get("sim_w") or 0.0), float(v.get("sim_h") or 0.0), SIMBOLO_MIN_PX)
        x, y, util = float(v["x"]), float(v["y"]), v.get("utilidad") or ""
        for i in cerca(x, y, sim * RADIO_PUNTA):
            p = pipes[i]
            if util and p.get("layer") != util:
                continue
            pts = p.get("pts") or ()
            for lado in (0, 1):
                s = _salida(pts, lado)
                if s is None or math.hypot(s[0][0] - x, s[0][1] - y) > sim * RADIO_PUNTA:
                    continue
                o, d = s
                if not _libre(pipes, i, o, cerca):
                    continue
                mejor = None
                for j in cerca(o[0] + d[0] * sim * LARGO_MAX / 2, o[1] + d[1] * sim * LARGO_MAX / 2,
                               sim * LARGO_MAX / 2 + 1.0):
                    if j == i or (util and pipes[j].get("layer") != util):
                        continue
                    q = pipes[j].get("pts") or ()
                    for a, b in zip(q, q[1:]):
                        r = _rayo(o, d, a, b)
                        if r and r[0] <= sim * LARGO_MAX and r[1] >= ANGULO_MIN and (mejor is None or r[0] < mejor):
                            mejor = r[0]
                if mejor is None:
                    continue
                nuevo = (o[0] + d[0] * mejor, o[1] + d[1] * mejor) + tuple(pts[-1 if lado else 0][2:])
                pts[-1 if lado else 0] = nuevo if isinstance(pts[0], tuple) else list(nuevo)
                if p.get("vertex_kinds"):
                    p["vertex_kinds"][-1 if lado else 0] = "tee"
                hechos.append((i, lado, mejor))
    return hechos
