"""Válvulas en la Vista 3D (2026-11-04/05), PURO: la MISMA pieza que dibuja el plugin en Civil 3D.

La forma sale de `valvula_receta` (la misma receta que `ValvulaReceta.cs` del plugin, para cualquier diámetro) y
sus triángulos de `valvula_malla`, con el color de su capa (V-PRES-VALV-DIA cuerpo ACI 5, V-PRES-VALV-INT
vástago y tuerca ACI 40, las capas que crea el plugin).

Colocación = la del plugin (`ImportarRedValvulas.cs`, igual a `BaseBloque` del plugin de válvulas del equipo):
x = eje de la tubería en 3D (con su pendiente, del inicio al fin del tramo), z = la vertical hecha perpendicular a
x, y = z × x, escala 1/12 (pulgadas → pies), centro en el eje de la tubería. La tubería se corta en las dos caras
de la válvula (el plugin la parte ahí)."""
from __future__ import annotations

import math

import numpy as np

from nucleo import mallas3d as M
from nucleo import model_ops
from nucleo import valvula_malla as VM
from nucleo import valvula_receta as VR

# colores de las capas que crea el plugin (ACI de AutoCAD): 5 = azul, 40 = naranja
COLOR_CAPA = {0: (0.0, 0.0, 1.0, 1.0), 1: (1.0, 191 / 255, 0.0, 1.0)}

_MALLAS = {}


def malla(n, union):
    """(posiciones ft (m, 3), normales (m, 3), capa por vértice) de la válvula de n pulgadas, una vez."""
    clave = (round(float(n), 4), VR.tipo_de(float(n), union))
    if clave not in _MALLAS:
        pos, nor, capa = VM.malla(VR.receta(n, union))
        _MALLAS[clave] = (pos / 12.0, nor, capa)
    return _MALLAS[clave]


def base(eje):
    """(x, y, z) del bloque: `BaseBloque` (sin invertir, giro 0)."""
    x = np.asarray(eje, float)
    x = x / max(np.linalg.norm(x), 1e-12)
    up = np.array([0.0, 0.0, 1.0])
    zz = up - x * float(up @ x)
    if np.linalg.norm(zz) < 1e-6:
        alt = np.array([0.0, 1.0, 0.0])
        zz = alt - x * float(alt @ x)
    z = zz / np.linalg.norm(zz)
    y = np.cross(z, x)
    return x, y / np.linalg.norm(y), z


def colocar(n, union, centro, eje):
    """(posiciones, normales, capa) de la válvula en el mundo (ft)."""
    pos, nor, capa = malla(n, union)
    x, y, z = base(eje)
    R = np.stack([x, y, z])                           # local (px, py, pz) → px·x + py·y + pz·z
    return pos @ R + np.asarray(centro, float), nor @ R, capa


def dibujar(ar, pipes, valvulas, id0, z_eje):
    """Pone cada válvula (dicts de `nucleo/valvulas.Lugar`: x, y, pipe, tramo, diam_in, union, largo_ft…) en
    el armado `ar`. Devuelve (cuántas, cortes {utilidad: [(centro xy, dir xy, alcance)]})."""
    cortes, n = {}, 0
    for v in valvulas or ():
        i, k = int(v["pipe"]), int(v["tramo"])
        if not (0 <= i < len(pipes)):
            continue
        p = pipes[i]
        pts = p.get("pts") or []
        if len(pts) < 2 or not (0 <= k < len(pts) - 1):
            continue
        x, y = float(v["x"]), float(v["y"])
        ze = z_eje(i, x, y)
        if ze is None:
            continue
        a, b = pts[k], pts[k + 1]
        z0, z1 = model_ops.cotas_tramo(p, k)
        eje = np.array([(b[0] - a[0]) * ar.ft, -(b[1] - a[1]) * ar.ft, z1 - z0])
        if np.linalg.norm(eje) < 1e-9:
            continue
        centro = np.array(ar.mundo(x, y, ze))
        d_in = float(v.get("diam_in") or 0)
        union = v.get("union") or "FLG"
        pos, nor, capa = colocar(d_in, union, centro, eje)
        ident = id0 + n + 1
        for c, color in COLOR_CAPA.items():
            m = capa == c
            if m.any():
                ar.op.append(M._vertices(pos[m], nor[m], color, ident))
        ex, _ey, _ez = base(eje)
        L = float(v["largo_ft"])
        A, B = centro - ex * L / 2.0, centro + ex * L / 2.0
        ar.picks.capsula(tuple(A), tuple(B), float(v.get("brida_ft") or L) / 2.0, ident)
        ar.registrar(ident, "accesorio", ident, pos, acc_tipo="valvula", pipes=[i], capa=p.get("layer"),
                     x=x, y=y, eje_z=float(ze), diam_in=d_in, bloque=v.get("bloque") or "",
                     union=v.get("union") or "", material=v.get("material") or "", largo_ft=L,
                     estimada=bool(v.get("estimada")))
        plano = math.hypot(ex[0], ex[1])
        if plano > 1e-9:                               # el tubo se corta en las dos caras (medido en planta)
            d = (ex[0] / plano, ex[1] / plano)
            c = (float(centro[0]), float(centro[1]))
            cortes.setdefault(i, []).extend([(c, d, L / 2.0 * plano), (c, (-d[0], -d[1]), L / 2.0 * plano)])
        n += 1
    return n, cortes
