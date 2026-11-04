"""diametro_vecinas.py — las líneas conectadas a la que revisa la IA del diámetro y su papel (PURO; pedido del usuario
2026-11-03: «me tiene que decir: a esta línea me estoy refiriendo»).

Lo que la IA diga de una línea vecina sale de aquí: la app MIDE quién es la principal, quién el ramal y quién sigue de
frente, y la IA solo lo cita por su id (L1, L2…). Antes la ficha solo traía las vecinas con diámetro confirmado, así
que la IA deducía el papel de cada una y hablaba de líneas que nadie podía ubicar.

Papeles, siempre entre líneas de la MISMA capa y estado (`diametro_continuidad`):
  · principal — esta línea llega a su interior, o llega de costado a un nodo donde otras dos siguen de frente.
  · ramal     — lo contrario: esa línea llega a esta.
  · sigue     — extremo con extremo y de frente (también la confirmada más allá de líneas sin dato: `lados`).
  · toca      — se tocan, sin que la geometría diga más.
Un contacto es geometría: no prueba una conexión hidráulica.

`tramo_sin_diametro` = las líneas sin dato que siguen de frente a esta sin un buzón o caja entre medio: las únicas a
las que se ofrece llevar el mismo diámetro, y solo con la aprobación del usuario.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence

from nucleo.diametro_continuidad import (GIRO_SIGUE_DEG, MAX_SALTOS, TOL_FT, TOL_PX, _confirmado, _estructura_en,
                                         _interior, _nombre, _salida, _sigue)

MAX_VECINAS = 8
_ORDEN = {"principal": 0, "sigue": 1, "ramal": 2, "toca": 3}


def _mismas(i: int, pipes) -> List[int]:
    p = pipes[i]
    return [j for j, o in enumerate(pipes) if len(o.get("pts") or []) >= 2 and not o.get("world")
            and o.get("layer") == p.get("layer") and bool(o.get("ab")) == bool(p.get("ab"))]


def _de_frente(a, b) -> bool:
    """¿Dos líneas que salen de un mismo nodo con estas direcciones siguen de frente?"""
    return math.degrees(math.acos(max(-1.0, min(1.0, -(a[0] * b[0] + a[1] * b[1]))))) <= GIRO_SIGUE_DEG


def _en_nodo(i, extremo, llegan, pipes, tol, mismas, roles):
    """Las líneas que comparten con i su `extremo`: quién sigue, quién es principal y quién solo toca."""
    q = pipes[i]["pts"][0 if extremo == 0 else -1]
    sig = _sigue(pipes, i, extremo, tol, mismas)
    if sig is not None:
        for j, _e in llegan:
            roles[j] = ("sigue" if j == sig[0] else "ramal", q)
        return
    salidas = [(j, _salida(pipes[j]["pts"], e)) for j, e in llegan]
    pasan = {j for j, a in salidas for k, b in salidas if j != k and _de_frente(a, b)}
    for j, _e in llegan:
        roles[j] = ("principal" if j in pasan else "toca", q)


def vecinas(i: int, pipes: Sequence[dict], ft_px: Optional[float] = None, lados=()) -> List[dict]:
    """[{id, linea, nombre, rol, diam_in (None = sin confirmar), punto}] de la línea i, primero las que más pesan.
    `lados` = los de `diametro_continuidad.analizar`: la confirmada puede estar más allá de líneas sin dato."""
    pts = pipes[i].get("pts") or []
    if len(pts) < 2:
        return []
    tol = TOL_FT / ft_px if ft_px else TOL_PX
    mismas = _mismas(i, pipes)
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    caja = (min(xs) - tol, min(ys) - tol, max(xs) + tol, max(ys) + tol)
    roles, nodos = {}, {0: [], -1: []}
    for j in mismas:
        op = pipes[j]["pts"]
        if j == i or (max(q[0] for q in op) < caja[0] or min(q[0] for q in op) > caja[2]
                      or max(q[1] for q in op) < caja[1] or min(q[1] for q in op) > caja[3]):
            continue
        for q in (pts[0], pts[-1]):
            if _interior(q, op, tol):
                roles[j] = ("principal", q)
        if j in roles:
            continue
        for q in (op[0], op[-1]):
            if _interior(q, pts, tol):
                roles[j] = ("ramal", q)
        if j in roles:
            continue
        for extremo, q in ((0, pts[0]), (-1, pts[-1])):
            for e2, r in ((0, op[0]), (-1, op[-1])):
                if math.dist(q, r) <= tol:
                    nodos[extremo].append((j, e2))
    for extremo, llegan in nodos.items():
        if llegan:
            _en_nodo(i, extremo, llegan, pipes, tol, mismas, roles)
    out = [dict(linea=j, nombre=_nombre(pipes, j), rol=rol, diam_in=_confirmado(pipes[j]),
                punto=[round(q[0], 1), round(q[1], 1)]) for j, (rol, q) in roles.items()]
    out.sort(key=lambda v: (_ORDEN[v["rol"]], v["linea"]))
    for lado in lados or ():
        if lado["linea"] not in roles:
            roles[lado["linea"]] = None
            out.append(dict(linea=lado["linea"], nombre=lado["nombre"], rol="sigue", diam_in=lado["diam_in"], punto=None))
    out = out[:MAX_VECINAS]
    for k, v in enumerate(out):
        v["id"] = f"L{k + 1}"
    return out


def tramo_sin_diametro(i: int, pipes: Sequence[dict], ft_px: Optional[float] = None, estructuras=()) -> List[int]:
    """Las líneas sin diámetro confirmado que siguen de frente a i, hasta un buzón/caja, una «Y» o una confirmada."""
    pts = pipes[i].get("pts") or []
    if len(pts) < 2:
        return []
    tol = TOL_FT / ft_px if ft_px else TOL_PX
    mismas = _mismas(i, pipes)
    out: List[int] = []
    for extremo in (0, -1):
        actual, e = i, extremo
        for _ in range(MAX_SALTOS):
            if _estructura_en(pipes[actual]["pts"][0 if e == 0 else -1], estructuras, tol):
                break
            sig = _sigue(pipes, actual, e, tol, mismas)
            if sig is None or sig[0] == i or sig[0] in out or _confirmado(pipes[sig[0]]) is not None:
                break
            out.append(sig[0])
            actual, e = sig[0], (-1 if sig[1] == 0 else 0)  # sale por la otra punta
    return out
