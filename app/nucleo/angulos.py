"""Validación: ningún ángulo del lienzo fuera del paso de 0.25° (PURO: sin Qt).

Pedido del usuario 2026-10-16: «no puedo encontrar ángulos de 45.684°: eso es
imposible», en CUALQUIER utilidad, también en las uniones y los accesorios de presión.
Se revisan los ángulos que se ven y que Civil 3D construye, que son RELATIVOS (no
dependen de cómo esté girada la hoja ni de la georreferencia):

  • quiebre: la deflexión en cada vértice interior de una utilidad (un codo, una curva
    o el quiebre de un buzón);
  • unión: el ángulo entre dos utilidades del mismo tipo donde la punta de una llega a
    la otra (a un vértice o a mitad de un tramo) — Tee, Wye, cruz o codo entre dos.

Un ángulo vale si es múltiplo de `PASO_DEG` ± `TOL_DEG` (el texto de los accesorios
muestra dos decimales). El dibujo a mano ya sale así (`trazo_asistido`); esto encuentra
lo que no: dibujos viejos, vértices movidos con «Mover con precisión», uniones de
«Unir utilidades» o lo reconocido del PDF (eso lo arregla el reconocimiento).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from nucleo.trazo_asistido import PASO_DEG

TOL_DEG = 0.01
UNION_FT = 0.5            # punta sobre otra utilidad (como las junturas del plugin)


@dataclass
class Fuera:
    x: float
    y: float
    angulo: float           # deflexión del quiebre o ángulo entre las dos utilidades (0–180)
    cercano: float          # el múltiplo de 0.25° más cercano
    pipe: int
    otra: int = -1          # en una unión, la otra utilidad
    vertice: int = -1       # en un quiebre, el vértice

    @property
    def union(self):
        return self.otra >= 0


def fuera_de_paso(ang, tol=TOL_DEG):
    r = ang / PASO_DEG
    return abs(r - round(r)) * PASO_DEG > tol


def mas_cercano(ang):
    return round(ang / PASO_DEG) * PASO_DEG


def texto(ang):
    """45.684 → «45.684°», 45.75 → «45.75°», 45 → «45°»."""
    s = f"{ang:.3f}".rstrip("0").rstrip(".")
    return s + "°"


def _dir(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _entre(a, b):
    """Ángulo 0–180° entre dos direcciones (radianes)."""
    return math.degrees(abs((a - b + math.pi) % (2 * math.pi) - math.pi))


def _vivas(pipes):
    for i, p in enumerate(pipes or []):
        pts = p.get("pts") or []
        if not p.get("world") and len(pts) >= 2:
            yield i, p, [tuple(q) for q in pts]


def quiebres(pipes):
    """Vértices interiores cuya deflexión no es múltiplo de 0.25°."""
    out = []
    for i, _p, pts in _vivas(pipes):
        for k in range(1, len(pts) - 1):
            a, v, b = pts[k - 1], pts[k], pts[k + 1]
            if v == a or v == b:
                continue
            giro = 180.0 - _entre(_dir(v, a), _dir(v, b))
            if giro > TOL_DEG and fuera_de_paso(giro):
                out.append(Fuera(v[0], v[1], giro, mas_cercano(giro), i, vertice=k))
    return out


def uniones(pipes, ft_per_px):
    """Puntas que llegan a otra utilidad del mismo tipo con un ángulo fuera del paso."""
    if not ft_per_px or ft_per_px <= 0:
        return []
    tol = UNION_FT / ft_per_px
    vivas = list(_vivas(pipes))
    celda = max(tol * 40.0, 1.0)
    rejilla = {}
    for j, p, pts in vivas:
        for k in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            for cx in range(int(math.floor((min(ax, bx) - tol) / celda)), int(math.floor((max(ax, bx) + tol) / celda)) + 1):
                for cy in range(int(math.floor((min(ay, by) - tol) / celda)), int(math.floor((max(ay, by) + tol) / celda)) + 1):
                    rejilla.setdefault((cx, cy), []).append((j, k))
    capa = {j: p.get("layer") for j, p, _pts in vivas}
    puntos = {j: pts for j, _p, pts in vivas}
    out, vistos = [], set()
    for i, p, pts in vivas:
        for q, vecino in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            if q == vecino:
                continue
            d_i = _dir(q, vecino)
            peor = None
            for j, k in rejilla.get((int(math.floor(q[0] / celda)), int(math.floor(q[1] / celda))), ()):
                if j == i or capa[j] != p.get("layer"):
                    continue
                a, b = puntos[j][k], puntos[j][k + 1]
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                if L2 <= 1e-12:
                    continue
                t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
                if math.hypot(a[0] + dx * t - q[0], a[1] + dy * t - q[1]) > tol:
                    continue
                ang = _entre(d_i, _dir(a, b))
                if fuera_de_paso(ang) and (peor is None or abs(ang - mas_cercano(ang)) > abs(peor[0] - mas_cercano(peor[0]))):
                    peor = (ang, j)
            if peor is None:
                continue
            ang, j = peor
            clave = (min(i, j), max(i, j), round(q[0] / tol), round(q[1] / tol))
            if clave in vistos:
                continue
            vistos.add(clave)
            out.append(Fuera(q[0], q[1], ang, mas_cercano(ang), i, otra=j))
    return out


def revisar(pipes, ft_per_px):
    """Todos los ángulos fuera del paso de 0.25°: quiebres y uniones."""
    return quiebres(pipes) + uniones(pipes, ft_per_px)


def avisos(pipes, ft_per_px):
    """Los ángulos fuera del paso como avisos del lienzo (`normas_validar.Aviso`, clase
    «angulo»): insignia ámbar, lista de avisos, aprobación y Tabla de datos."""
    from nucleo.normas_validar import Aviso
    from traduccion.i18n_core import t
    out = []
    for f in revisar(pipes, ft_per_px):
        if f.union:
            msg = t("Unión con la utilidad #{n} a {a}: no sigue el paso de 0.25° (el más cercano: {c}).").format(
                n=f.otra + 1, a=texto(f.angulo), c=texto(f.cercano))
        else:
            msg = t("Quiebre de {a}: no sigue el paso de 0.25° (el más cercano: {c}).").format(
                a=texto(f.angulo), c=texto(f.cercano))
        out.append(Aviso(f.x, f.y, "angulo", msg, f.pipe))
    return out
