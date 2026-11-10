"""Sentido del FLUJO en las utilidades por gravedad y a presión (pedidos del usuario 2026-11-09: «indicar hacia dónde
va el fluido, de una manera fácil, en las propiedades de la utilidad y en el perfil»; luego «también para las de
presión; eléctrico y telecom son las únicas que no deben tener»). PURO (sin Qt).

`pipe["flujo"]`, como «Flow Direction» de Civil 3D:
- 1  = del INICIO al FIN de la utilidad (el orden de sus vértices, «Start to End»);
- -1 = del FIN al INICIO («End to Start»);
- sin la clave = AUTOMÁTICO. En gravedad: en el perfil, hacia el extremo más bajo del recorrido (la regla de siempre:
  las estaciones automáticas empiezan en la solera más baja y el fluido corre hacia el inicio). A presión no hay
  pendiente que lo diga: queda SIN INDICAR.
Solo se usa para validar el perfil (contrapendiente, gravedad) y para dibujar las flechas: nada se mueve.
"""
from __future__ import annotations

import math

from nucleo.model import network_kind

ADELANTE, ATRAS, AUTO = 1, -1, 0
REDES = ("gravity", "pressure")          # las de conductos (eléctrico, telecom) no llevan sentido del flujo


def aplica(p):
    """True si la utilidad lleva sentido del flujo (gravedad o presión)."""
    return isinstance(p, dict) and network_kind(p.get("layer") or "") in REDES


def fijo(p):
    """El sentido indicado por el usuario (1 / -1), o 0 = automático."""
    v = p.get("flujo") if isinstance(p, dict) else None
    return v if v in (ADELANTE, ATRAS) else AUTO


def poner(p, sentido):
    """Indica el sentido (1 / -1) o lo vuelve automático (0). True si cambió."""
    antes = fijo(p)
    if sentido in (ADELANTE, ATRAS):
        p["flujo"] = int(sentido)
    else:
        p.pop("flujo", None)
    return fijo(p) != antes


def en_paso(p, invertida):
    """El sentido indicado de la utilidad visto desde un paso del perfil: 1 = hacia las estaciones mayores (B),
    -1 = hacia el inicio (A), 0 = automático. `invertida` = el paso recorre la utilidad del fin al inicio."""
    f = fijo(p)
    return -f if (f and invertida) else f


def de_paso(hacia, invertida):
    """Lo inverso de `en_paso`: el valor de `pipe["flujo"]` para que el fluido vaya `hacia` (1 = B, -1 = A, 0 =
    automático) en un paso que recorre la utilidad al derecho (`invertida` False) o al revés."""
    if hacia not in (ADELANTE, ATRAS):
        return AUTO
    return -hacia if invertida else hacia


def invertido(p):
    """El valor de `flujo` para la MISMA utilidad con sus vértices al revés (el fluido sigue igual)."""
    f = fijo(p)
    return -f if f else AUTO


def rumbo_pantalla(pts):
    """Ángulo (grados, Y del lienzo hacia abajo) de la utilidad del inicio al fin: la flecha del panel apunta como se
    ve en el plano. Si las puntas coinciden (lazo), el del primer tramo. None sin tramos."""
    if not pts or len(pts) < 2:
        return None
    a, b = pts[0], pts[-1]
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6:
        a, b = pts[0], pts[1]
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9:
        return None
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def flechas_plano(pts, sentido):
    """[(x, y, ángulo en grados)] de una flecha a la mitad de cada tramo, apuntando hacia donde va el fluido
    (`sentido` 1 / -1). [] si es automático."""
    if sentido not in (ADELANTE, ATRAS):
        return []
    out = []
    for a, b in zip(pts, pts[1:]):
        if sentido == ATRAS:
            a, b = b, a
        dx, dy = b[0] - a[0], b[1] - a[1]
        if math.hypot(dx, dy) < 1e-9:
            continue
        out.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.degrees(math.atan2(dy, dx))))
    return out
