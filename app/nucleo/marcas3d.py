"""Marcas de la Vista 3D (PURO): avisos de normativa (esfera ámbar, celeste si es solo
información) y CONFLICTOS numerados (esfera roja + etiqueta «C-n», `nucleo/conflictos.py`),
apoyadas encima de la utilidad a la que se refieren. Las usa `modelo3d.construir`."""
from __future__ import annotations

import math

from nucleo import mallas3d as M
from nucleo import model_ops

COLOR_AVISO = (1.0, 0.72, 0.1, 1.0)
COLOR_INFO = (0.35, 0.65, 1.0, 1.0)
COLOR_CONFLICTO = (0.9, 0.12, 0.12, 1.0)
R_CONFLICTO_FT = 0.8
JUNTOS_FT = 1.0          # conflictos a menos de esto comparten etiqueta


def marca_en_utilidad(ar, pipes, i, x, y):
    """Punto 3D (eje + alto) de la utilidad i más cercano a (x, y), o None."""
    from nucleo.modelo3d import seccion
    if i is None or not (0 <= i < len(pipes)):
        return None
    p = pipes[i]
    pts = p.get("pts") or []
    mejor = None
    for k in range(len(pts) - 1):
        z = model_ops.z_en_tramo(p, k, x, y)
        a, b = pts[k], pts[k + 1]
        L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / L2))
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        dd = math.dist(q, (x, y))
        if mejor is None or dd < mejor[0]:
            mejor = (dd, z)
    _p, alto = seccion(p)
    return None if mejor is None else ar.mundo(x, y, mejor[1] + alto)


def _mas_cercana(pipes, x, y):
    return min(range(len(pipes)), key=lambda i: min(math.dist(q, (x, y)) for q in pipes[i].get("pts") or [(1e18, 1e18)]),
               default=None)


def marcas(ar, pipes, avisos, conflictos, id_aviso, id_conflicto):
    """Dibuja las marcas en `ar`. Devuelve [(id, punto 3D, texto)] de las etiquetas «C-n»."""
    from nucleo.modelo3d import diametro_ft
    for m, a in enumerate(avisos or []):
        if a.get("clase") == "tipo" or a.get("aprobado"):  # como en el plano: «sin tipo» y aprobados no
            continue
        q = marca_en_utilidad(ar, pipes, a.get("pipe", -1), a["x"], a["y"])
        if q is None:
            continue
        ident = id_aviso + m + 1
        r = max(0.6, diametro_ft(pipes[a["pipe"]]) * 0.5)
        c = (q[0], q[1], q[2] + r)
        ar.op.append(M.esfera(c, r, COLOR_INFO if a.get("info") else COLOR_AVISO, ident))
        ar.picks.capsula(c, c, r, ident)
        ar.registrar(ident, "aviso", m, [q], mensaje=a.get("mensaje", ""), info=bool(a.get("info")))
    etiquetas = []
    for n, k in enumerate(conflictos or []):
        cand = [i for i in k.get("pipes") or [] if 0 <= i < len(pipes) and pipes[i].get("pts")]
        i = cand[0] if cand else _mas_cercana(pipes, k["x"], k["y"])
        q = marca_en_utilidad(ar, pipes, i, k["x"], k["y"])
        if q is None:
            continue
        if len(cand) > 1:                             # sobre la más alta de las que chocan
            q = max((marca_en_utilidad(ar, pipes, j, k["x"], k["y"]) for j in cand), key=lambda p: p[2])
        ident = id_conflicto + n + 1
        c = (q[0], q[1], q[2] + R_CONFLICTO_FT)
        ar.op.append(M.esfera(c, R_CONFLICTO_FT, COLOR_CONFLICTO, ident))
        ar.picks.capsula(c, c, R_CONFLICTO_FT, ident)
        ar.registrar(ident, "conflicto", n, [q], codigo=k.get("id", ""), titulo=k.get("titulo", ""),
                     mensaje=k.get("mensaje", ""), pipes=list(k.get("pipes") or []), cotas=list(k.get("cotas") or []),
                     x=k["x"], y=k["y"])
        punto = (c[0], c[1], c[2] + R_CONFLICTO_FT)
        junto = next((e for e in etiquetas if math.dist(e[1], punto) <= JUNTOS_FT), None)
        if junto is None:                              # el mismo lugar: una sola etiqueta «C-10 · C-13»
            etiquetas.append([ident, punto, k.get("id", "")])
        else:
            junto[2] += " · " + k.get("id", "")
    return [tuple(e) for e in etiquetas]
