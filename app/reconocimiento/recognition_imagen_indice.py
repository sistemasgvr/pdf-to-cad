"""Índices por celdas para `recognition_imagen_rectas` (PURO, sin Qt ni fitz).

Reporte del usuario (2026-11-19): una hoja compuesta de 36 mapas pasó ~2 horas en «Leyendo los diámetros y rótulos
del plano…»: el enderezado de la red en imagen comparaba cada línea con todas las demás (con 4 hojas ya eran 140 de
182 s). Con estos índices se miran solo las líneas y bóvedas de las celdas vecinas, recorridas en el ORDEN de siempre:
mismo resultado (mismos desempates)."""
from __future__ import annotations

import math
from typing import Tuple

from reconocimiento import recognition_vault_snap as vault_snap

Pt = Tuple[float, float]


def dist_seg(q: Pt, a: Pt, b: Pt) -> Tuple[float, Pt]:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    s = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    p = (a[0] + s * vx, a[1] + s * vy)
    return math.hypot(q[0] - p[0], q[1] - p[1]), p


def dist_en(q: Pt, pts, ks) -> Tuple[float, Pt]:
    """Distancia (y pie) de `q` a los tramos `ks` de `pts`, en su orden: el primero mínimo gana."""
    mejor = (math.inf, q)
    for k in ks:
        d = dist_seg(q, pts[k], pts[k + 1])
        if d[0] < mejor[0]:
            mejor = d
    return mejor


def _celdas(c: float, x0, y0, x1, y1):
    for gx in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
        for gy in range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1):
            yield gx, gy


class Rejilla:
    """Tramos de las líneas por celdas. `cerca(q, r)` = [(línea, [índices de sus tramos])] de las líneas con algún
    tramo cuya caja toca el cuadrado de lado 2r alrededor de `q`, en el orden de la lista original. Una línea que
    está a ≤ r de `q` siempre sale (y con todos sus tramos a ≤ r)."""

    def __init__(self, lineas, celda: float):
        self.c = max(celda, 1e-6)
        self.celdas: dict = {}
        self.orden = {id(pl): k for k, pl in enumerate(lineas)}
        self.de: dict = {}
        self.version: dict = {}
        for pl in lineas:
            self.poner(pl)

    def poner(self, pl) -> None:
        v = self.version.get(id(pl), 0) + 1             # los tramos de una versión vieja se ignoran
        self.version[id(pl)] = v
        self.de[id(pl)] = pl
        self.orden.setdefault(id(pl), len(self.orden))   # (una línea nueva va al final del orden)
        pts = pl.pts_pdf
        for k, (a, b) in enumerate(zip(pts, pts[1:])):
            for g in _celdas(self.c, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])):
                self.celdas.setdefault(g, []).append((id(pl), v, k))

    def quitar(self, pl) -> None:
        self.de.pop(id(pl), None)

    def cerca(self, q: Pt, r: float) -> list:
        vistos: dict = {}
        for g in _celdas(self.c, q[0] - r, q[1] - r, q[0] + r, q[1] + r):
            for i, v, k in self.celdas.get(g, ()):
                if i in self.de and self.version[i] == v:
                    vistos.setdefault(i, set()).add(k)
        return [(self.de[i], sorted(ks)) for i, ks in sorted(vistos.items(), key=lambda t: self.orden[t[0]])]

    def toca(self, q: Pt, r: float, salvo=()) -> bool:
        """¿Alguna línea que no sea de `salvo` pasa a ≤ r de `q`?"""
        return any(all(pl is not x for x in salvo) and dist_en(q, pl.pts_pdf, ks)[0] <= r
                   for pl, ks in self.cerca(q, r))


class Bovedas:
    """Bóvedas por celdas de su caja con margen `pad`: `en(q)` = las que pueden contener `q`, en su orden."""

    def __init__(self, vaults, pad: float, celda: float):
        self.c = max(celda, 1e-6)
        self.v = list(vaults)
        self.celdas: dict = {}
        for i, vg in enumerate(self.v):
            b = vault_snap.boundary(vg)
            if b is None:
                continue
            if b[0] == "circle":
                cx, cy, r = b[1]
                x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
            else:
                xs, ys = [p[0] for p in b[1]], [p[1] for p in b[1]]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            for g in _celdas(self.c, x0 - pad, y0 - pad, x1 + pad, y1 + pad):
                self.celdas.setdefault(g, []).append(i)

    def en(self, q: Pt) -> list:
        g = (int(math.floor(q[0] / self.c)), int(math.floor(q[1] / self.c)))
        return [self.v[i] for i in self.celdas.get(g, ())]
