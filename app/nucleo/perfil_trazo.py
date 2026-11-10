"""Geometría REAL en planta de los pasos del perfil (reporte del usuario 2026-11-10: el resalte del recorrido A→B
no seguía la curva de la utilidad e iba por la esquina). PURO (sin Qt).

Una utilidad con curva (estructura CV en un vértice interior) se dibuja con el arco tangente de
`model_ops.fillet_geo` — el mismo del editor, la Vista 3D y el plugin (`limpieza_tramos.curvas`, mismos topes). El
perfil sigue partido en los vértices de siempre (mismos nodos); cada tramo k → k+1 en planta es:
  - si el vértice k es curva: la segunda mitad de su arco (del punto medio a la tangencia de salida);
  - el recto entre tangencias;
  - si el vértice k+1 es curva: la primera mitad de su arco (de la tangencia de entrada al punto medio).
Así el nodo de una curva cae en el punto medio del arco y los pasos suman el largo del eje que arma Civil 3D
(`PerfilGrafoCivil`: tubos curvos con su bulge); antes se medía pasando por la esquina (más largo).
Cada punto lleva su parámetro sobre la CUERDA del tramo (0 = vértice k, 1 = vértice k+1): con él se recorta la
parte [t0, t1] de una arista partida por una T y se lleva un punto de la cuerda a su estación.
Sin curvas, la traza es la cuerda tal cual (el resultado de antes).
"""
from __future__ import annotations

import math

from nucleo import limpieza_tramos as LT


def curvas(pipes, structures, i, ft):
    """{vértice: geometría del arco} de la utilidad i ({} sin escala o sin curvas)."""
    if not ft or not (0 <= i < len(pipes)) or len((pipes[i] or {}).get("pts") or []) < 3:
        return {}
    try:
        return LT.curvas(pipes, structures or [], i, ft)[1]
    except (ZeroDivisionError, ValueError, TypeError):
        return {}


def _repartir(seg, a, b):
    """[(t, punto)] de la polilínea `seg` con t de a a b proporcional al largo recorrido."""
    acum = [0.0]
    for p, q in zip(seg, seg[1:]):
        acum.append(acum[-1] + math.dist(p, q))
    tot = acum[-1]
    if tot <= 1e-12:
        return [(a, tuple(seg[0])), (b, tuple(seg[-1]))]
    return [(a + (b - a) * s / tot, tuple(q)) for s, q in zip(acum, seg)]


def tramo(pts, geos, k):
    """[(t, punto)] del tramo k (de pts[k] a pts[k+1]) tal como se dibuja, con t sobre su cuerda."""
    P, Q = tuple(pts[k]), tuple(pts[k + 1])
    L = math.dist(P, Q)
    ga, gb = geos.get(k), geos.get(k + 1)
    if L <= 1e-12 or (ga is None and gb is None):
        return [(0.0, P), (1.0, Q)]
    out = []
    ta = 0.0
    if ga is not None:
        arco = ga["arc"]
        m = len(arco) // 2
        ta = min(float(ga["T"]) / L, 1.0)
        out += _repartir(arco[m:], 0.0, ta)            # del punto medio a la tangencia de salida
    else:
        out.append((0.0, P))
    if gb is not None:
        arco = gb["arc"]
        m = len(arco) // 2
        tb = max(1.0 - float(gb["T"]) / L, ta)
        out += _repartir(arco[:m + 1], tb, 1.0)       # de la tangencia de entrada al punto medio
    else:
        out.append((1.0, Q))
    limpio = [out[0]]
    for t, q in out[1:]:
        if math.dist(q, limpio[-1][1]) > 1e-9:
            limpio.append((t, q))
        else:
            limpio[-1] = (max(limpio[-1][0], t), limpio[-1][1])
    return limpio


def _medio_arco(g):
    """Largo EXACTO de media curva (r·Δ/2; la polilínea del arco es apenas más corta)."""
    r, T = float(g["r"]), float(g["T"])
    return r * (math.pi - 2.0 * math.atan2(r, T)) / 2.0


def largo_tramo(pts, geos, k, t0=0.0, t1=1.0):
    """Largo (px) de la parte [t0, t1] del tramo k tal como se dibuja: rectos + arcos exactos."""
    P, Q = pts[k], pts[k + 1]
    L = math.dist(P, Q)
    ga, gb = geos.get(k), geos.get(k + 1)
    if L <= 1e-12:
        return 0.0
    piezas = []
    ta, tb = 0.0, 1.0
    if ga is not None:
        ta = min(float(ga["T"]) / L, 1.0)
        piezas.append((0.0, ta, _medio_arco(ga)))
    if gb is not None:
        tb = max(1.0 - float(gb["T"]) / L, ta)
    if tb > ta:
        piezas.append((ta, tb, (tb - ta) * L))
    if gb is not None:
        piezas.append((tb, 1.0, _medio_arco(gb)))
    tot = 0.0
    for a, b, lg in piezas:
        dentro = min(b, t1) - max(a, t0)
        if dentro > 0 and b - a > 1e-12:
            tot += lg * dentro / (b - a)
    return tot


def recortar(puntos, t0, t1):
    """La parte [t0, t1] de `puntos` ([(t, punto)] con t creciente)."""
    def en(t):
        for (ta, pa), (tb, pb) in zip(puntos, puntos[1:]):
            if ta - 1e-12 <= t <= tb + 1e-12:
                f = 0.0 if tb - ta <= 1e-12 else (t - ta) / (tb - ta)
                return (pa[0] + (pb[0] - pa[0]) * f, pa[1] + (pb[1] - pa[1]) * f)
        return puntos[0][1] if t <= puntos[0][0] else puntos[-1][1]
    if t0 <= 1e-12 and t1 >= 1 - 1e-12:
        return list(puntos)
    out = [(t0, en(t0))]
    out += [(t, q) for t, q in puntos if t0 + 1e-12 < t < t1 - 1e-12]
    out.append((t1, en(t1)))
    return out


def de_arista(pts, geos, ar, invertida):
    """(puntos, s, acum) del paso: la traza de la arista `ar` en el sentido del paso, `s` = parámetro de cada punto
    sobre la cuerda del paso (0 = su p0, 1 = su p1) y `acum` = largo EXACTO (px, arcos con r·Δ) desde el inicio del
    paso hasta cada punto. None si la arista no tiene curvas (la traza es su cuerda)."""
    if ar.tramo not in geos and ar.tramo + 1 not in geos:
        return None
    parte = recortar(tramo(pts, geos, ar.tramo), ar.t0, ar.t1)
    d = ar.t1 - ar.t0
    s = [0.0 if abs(d) <= 1e-12 else (t - ar.t0) / d for t, _q in parte]
    q = [p for _t, p in parte]
    acum = [largo_tramo(pts, geos, ar.tramo, ar.t0, t) for t, _q in parte]
    if invertida:
        q.reverse()
        s = [1.0 - v for v in reversed(s)]
        acum = [acum[-1] - v for v in reversed(acum)]
    return tuple(q), tuple(s), tuple(acum)

