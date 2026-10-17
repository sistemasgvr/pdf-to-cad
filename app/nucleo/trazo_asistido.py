"""Ángulos del dibujo a mano en PASOS de 0.25° (PURO: sin Qt).

Pedidos del usuario 2026-10-15/16: a mano alzada la línea nunca sale del todo recta y
cada quiebre chico se vuelve un vértice con su accesorio; y en el lienzo no puede haber
ángulos como 45.684°: todo ángulo (quiebre de una utilidad, unión entre utilidades,
accesorios de presión) va en pasos de `PASO_DEG` = 0.25°.

Cada tramo nuevo sale del punto anterior con un rumbo `cuantizar(rumbo, base)`: `base`
es el rumbo del tramo anterior (así el QUIEBRE es múltiplo de 0.25°) o, en el primer
tramo, el de la utilidad donde empieza (la UNIÓN) o 0° (ejes de la hoja). El largo es lo
que el cursor avanzó por esa dirección (proyección). Las direcciones múltiplo de 45° son
vectores EXACTOS de una tabla: en horizontal la y no cambia ni un decimal, en vertical la
x tampoco y en diagonal |Δx| == |Δy|. «Asistir» suma IMANES (`imanes`): si el cursor pasa
a ≤ `tol` px de seguir recto, girar 45°/90°… o de los ejes de la hoja, va ahí.
Rumbos en grados en coordenadas de la HOJA (x a la derecha, y hacia abajo).
"""
from __future__ import annotations

import math

PASO_DEG = 0.25
_R = math.sqrt(0.5)
# Direcciones cada 45° (k = 0..7), exactas.
DIRECCIONES = ((1.0, 0.0), (_R, _R), (0.0, 1.0), (-_R, _R),
               (-1.0, 0.0), (-_R, -_R), (0.0, -1.0), (_R, -_R))


def rumbo(p0, p):
    """Rumbo p0 → p en grados [0, 360) (hoja: y hacia abajo)."""
    return math.degrees(math.atan2(p[1] - p0[1], p[0] - p0[0])) % 360.0


def cuantizar(ang, base=0.0, paso=PASO_DEG):
    """`ang` llevado al múltiplo de `paso` más cercano contando desde `base`."""
    d = (ang - base + 180.0) % 360.0 - 180.0
    return (base + round(d / paso) * paso) % 360.0


def en_paso(ang, base=0.0, paso=PASO_DEG, tol=1e-6):
    """¿`ang` − `base` es múltiplo de `paso` (± tol grados)?"""
    d = (ang - base) / paso
    return abs(d - round(d)) * paso <= tol


def unitario(ang):
    """Vector unitario del rumbo `ang`; exacto en los múltiplos de 45°."""
    k = ang / 45.0
    if abs(k - round(k)) < 1e-9:
        return DIRECCIONES[int(round(k)) % 8]
    a = math.radians(ang)
    return (math.cos(a), math.sin(a))


def sobre(p0, u, t):
    """Punto a `t` de p0 por la dirección u (la misma expresión en x e y: exacto)."""
    return (p0[0] + u[0] * t, p0[1] + u[1] * t)


def imanes(base, absoluto=True):
    """Rumbos a los que «Asistir» pega: seguir recto y girar 45°, 90°… desde `base`;
    con `absoluto`, también los ejes y diagonales de la hoja."""
    out = [(base + 45.0 * k) % 360.0 for k in range(8)]
    if absoluto:
        out += [45.0 * k for k in range(8)]
    return out


def restringir(p0, p, base=0.0, imanes_=(), tol=0.0):
    """(punto, rumbo) del tramo p0 → cursor p: el rumbo es un imán a ≤ `tol` (distancia
    del cursor a su recta) o, si no, el múltiplo de 0.25° más cercano desde `base`."""
    dx, dy = p[0] - p0[0], p[1] - p0[1]
    mejor, d_mejor = None, tol
    for a in imanes_:
        u = unitario(a)
        if dx * u[0] + dy * u[1] <= 0:
            continue
        d = abs(dx * u[1] - dy * u[0])
        if d <= d_mejor:
            mejor, d_mejor = a, d
    ang = mejor if mejor is not None else cuantizar(rumbo(p0, p), base)
    u = unitario(ang)
    t = dx * u[0] + dy * u[1]
    return sobre(p0, u, max(0.0, t)), ang


def cruce_rayo(p0, u, a, b):
    """Cruce del rayo p0 + u·t (t > 0) con el tramo a–b, o None si no lo corta."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = u[0] * ey - u[1] * ex
    if abs(den) < 1e-12:                     # paralelos
        return None
    wx, wy = a[0] - p0[0], a[1] - p0[1]
    t = (wx * ey - wy * ex) / den
    s = (wx * u[1] - wy * u[0]) / den
    if t <= 1e-9 or not (-1e-9 <= s <= 1.0 + 1e-9):
        return None
    return sobre(p0, u, t)


def cruce_rectas(p, u, q, w):
    """Cruce de las rectas p + u·s y q + w·r → (punto, s, r), o None si son paralelas."""
    den = u[0] * w[1] - u[1] * w[0]
    if abs(den) < 1e-12:
        return None
    dx, dy = q[0] - p[0], q[1] - p[1]
    s = (dx * w[1] - dy * w[0]) / den
    r = (dx * u[1] - dy * u[0]) / den
    return sobre(p, u, s), s, r


def deslizar_inicio(prev, p0, T, base):
    """Para llegar EXACTO a un punto fijo T (extremo de otra utilidad) sin romper el paso:
    corre p0 por la recta prev → p0 (no cambia su rumbo) hasta que el rumbo p0' → T sea
    múltiplo de 0.25° desde `base`. Sin `prev` (primer punto, libre), gira p0 alrededor de
    T. Devuelve p0' o None si no hace falta o no se puede."""
    ang = rumbo(p0, T)
    q = cuantizar(ang, base)
    if abs((ang - q + 180.0) % 360.0 - 180.0) < 1e-9:
        return None
    w = unitario(q)
    L = math.hypot(T[0] - p0[0], T[1] - p0[1])
    if prev is None:
        return sobre(T, w, -L)
    if math.hypot(p0[0] - prev[0], p0[1] - prev[1]) < 1e-9:
        return None
    u = unitario(rumbo(prev, p0))
    c = cruce_rectas(prev, u, T, w)
    if c is None or c[1] <= 1e-9 or c[2] >= -1e-9:   # p0' antes de prev o T detrás de p0'
        return None
    return c[0]


def rumbo_deg(p0, p):
    """Ángulo del tramo p0 → p en grados, antihorario desde el Este (para mostrar)."""
    return math.degrees(math.atan2(-(p[1] - p0[1]), p[0] - p0[0])) % 360.0


def _base_lejos(pts, k):
    """Rumbo de un tramo que NO toca el vértice k (la «red» de rumbos de la utilidad), o 0°."""
    for j in range(len(pts) - 1):
        if j not in (k - 1, k) and tuple(pts[j]) != tuple(pts[j + 1]):
            return rumbo(pts[j], pts[j + 1])
    return 0.0


def arrastre_en_paso(pts, k, p, tol):
    """Dónde queda el vértice k que se arrastra al cursor p para que sus ángulos sigan el
    paso de 0.25°: un vértice interior va al cruce de los rayos en el paso que salen de sus
    dos vecinos (cada uno contado desde el tramo de más allá); una punta, a su rayo en el
    paso desde el vecino. Si el cruce cae a más de `tol` del cursor (casi en línea), queda
    sobre la recta común; si no hay solución, el cursor tal cual."""
    pts = [tuple(q) for q in pts]
    n = len(pts)
    if n < 2 or not (0 <= k < n):
        return tuple(p)
    lejos = _base_lejos(pts, k)

    def rayo(v, mas_alla):
        """(vecino, rumbo en el paso del vecino hacia el cursor)."""
        base = rumbo(v, mas_alla) if mas_alla is not None and mas_alla != v else lejos
        return v, cuantizar(rumbo(v, p), base)

    lados = []
    if k > 0:
        lados.append(rayo(pts[k - 1], pts[k - 2] if k >= 2 else None))
    if k < n - 1:
        lados.append(rayo(pts[k + 1], pts[k + 2] if k + 2 < n else None))
    if len(lados) == 1:
        v, a = lados[0]
        u = unitario(a)
        return sobre(v, u, max(0.0, (p[0] - v[0]) * u[0] + (p[1] - v[1]) * u[1]))
    (va, a), (vb, b) = lados
    ua, ub = unitario(a), unitario(b)
    c = cruce_rectas(va, ua, vb, ub)
    if c is not None and c[1] > 0 and c[2] > 0 and math.hypot(c[0][0] - p[0], c[0][1] - p[1]) <= tol:
        return c[0]
    # Casi en línea: la recta de A sirve si B cae sobre ella (los dos rayos son la misma recta).
    if abs((vb[0] - va[0]) * ua[1] - (vb[1] - va[1]) * ua[0]) <= 1e-6 * max(1.0, math.hypot(vb[0] - va[0], vb[1] - va[1])):
        return sobre(va, ua, max(0.0, (p[0] - va[0]) * ua[0] + (p[1] - va[1]) * ua[1]))
    return tuple(p)
