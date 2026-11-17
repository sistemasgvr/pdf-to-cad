"""Superficies importadas en el perfil longitudinal de la app (pedido del usuario 2026-11-14: «que las superficies
agregadas en la app se vean reflejadas también en el perfil»). PURO (numpy).

`IndiceTin` = el TIN en px del plano con un índice por celdas (con millones de triángulos de un GeoTIFF, probar todos
por cada muestra no sirve); `cotas(xy)` = la cota interpolada en el triángulo que contiene cada punto (la MISMA cuenta
que `superficies.cota_en`; fuera del TIN = NaN). `muestrear(pasos, superficies)` = la línea de terreno de cada
superficie a lo largo del recorrido del perfil: [(nombre, [(estación, cota | None)])], con None donde el recorrido
sale de la superficie (la línea se corta ahí, no se inventa).
"""
from __future__ import annotations

import math

import numpy as np

MUESTRAS_MAX = 600                     # muestras por perfil (además de los extremos de cada paso)
PASO_MIN_FT = 0.5
SPAN_MAX = 8                           # triángulos que cubren más celdas por eje se prueban siempre (raros)


class IndiceTin:
    def __init__(self, px, z, tri):
        self.px = np.asarray(px, np.float64).reshape(-1, 2)
        self.z = np.asarray(z, np.float64).reshape(-1)
        self.tri = np.asarray(tri, np.int64).reshape(-1, 3)
        t = self.px[self.tri] if len(self.tri) else np.zeros((0, 3, 2))
        self._t = t
        if not len(t):
            self._claves = np.zeros(0, np.int64)
            self._ids = np.zeros(0, np.int64)
            self._grandes = np.zeros(0, np.int64)
            self.celda, self.x0, self.y0 = 1.0, 0.0, 0.0
            return
        lo, hi = t.min(axis=1), t.max(axis=1)
        self.x0, self.y0 = float(lo[:, 0].min()), float(lo[:, 1].min())
        ancho = float(hi[:, 0].max() - self.x0) or 1.0
        alto = float(hi[:, 1].max() - self.y0) or 1.0
        self.celda = max(math.sqrt(ancho * alto / max(len(t), 1)) * 2.0, 1e-6)
        i0 = np.floor((lo[:, 0] - self.x0) / self.celda).astype(np.int64)
        j0 = np.floor((lo[:, 1] - self.y0) / self.celda).astype(np.int64)
        nx = np.floor((hi[:, 0] - self.x0) / self.celda).astype(np.int64) - i0 + 1
        ny = np.floor((hi[:, 1] - self.y0) / self.celda).astype(np.int64) - j0 + 1
        grandes = (nx > SPAN_MAX) | (ny > SPAN_MAX)
        self._grandes = np.nonzero(grandes)[0]
        ids_todos = np.arange(len(t))
        claves, ids = [], []
        for dx in range(int(min(nx[~grandes].max(initial=1), SPAN_MAX))):
            for dy in range(int(min(ny[~grandes].max(initial=1), SPAN_MAX))):
                m = ~grandes & (dx < nx) & (dy < ny)
                claves.append(self._clave(i0[m] + dx, j0[m] + dy))
                ids.append(ids_todos[m])
        claves = np.concatenate(claves) if claves else np.zeros(0, np.int64)
        ids = np.concatenate(ids) if ids else np.zeros(0, np.int64)
        orden = np.lexsort((ids, claves))                        # por celda y, dentro, en el orden del TIN
        self._claves, self._ids = claves[orden], ids[orden]

    @staticmethod
    def _clave(i, j):
        return (np.asarray(i, np.int64) + (1 << 20)) * (1 << 21) + (np.asarray(j, np.int64) + (1 << 20))

    def _candidatos(self, x, y):
        k = int(self._clave(math.floor((x - self.x0) / self.celda), math.floor((y - self.y0) / self.celda)))
        a, b = np.searchsorted(self._claves, k), np.searchsorted(self._claves, k, side="right")
        c = self._ids[a:b]
        return np.concatenate([c, self._grandes]) if len(self._grandes) else c

    def cota(self, x, y):
        """Cota en (x, y) px o NaN fuera del TIN (el primer triángulo que lo contiene, en el orden del TIN)."""
        c = self._candidatos(x, y)
        if not len(c):
            return float("nan")
        c = np.sort(c)
        t = self._t[c]
        x0, y0 = t[:, 0, 0], t[:, 0, 1]
        d1x, d1y = t[:, 1, 0] - x0, t[:, 1, 1] - y0
        d2x, d2y = t[:, 2, 0] - x0, t[:, 2, 1] - y0
        det = d1x * d2y - d2x * d1y
        with np.errstate(divide="ignore", invalid="ignore"):
            u = ((x - x0) * d2y - d2x * (y - y0)) / det
            v = (d1x * (y - y0) - (x - x0) * d1y) / det
        dentro = np.nonzero((u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (det != 0))[0]
        if not len(dentro):
            return float("nan")
        k = dentro[0]
        zz = self.z[self.tri[c[k]]]
        return float(zz[0] + u[k] * (zz[1] - zz[0]) + v[k] * (zz[2] - zz[0]))

    def cotas(self, xy):
        return np.array([self.cota(float(x), float(y)) for x, y in np.asarray(xy, np.float64).reshape(-1, 2)])


def estaciones(pasos):
    """Estaciones donde se mide: los extremos de cada paso y, entre ellos, cada largo/`MUESTRAS_MAX` (≥ PASO_MIN_FT)."""
    if not pasos:
        return []
    total = sum(max(p.e1 - p.e0, 0.0) for p in pasos)
    paso = max(total / MUESTRAS_MAX, PASO_MIN_FT)
    out = []
    for i, p in enumerate(pasos):
        n = max(1, int(math.ceil((p.e1 - p.e0) / paso)))
        for k in range(n + (1 if i == len(pasos) - 1 else 0)):
            out.append((i, p.e0 + (p.e1 - p.e0) * k / n))
    return out


def muestrear(pasos, superficies):
    """[(nombre, [(estación, cota | None)])] de cada superficie con alguna cota en el recorrido."""
    puntos = estaciones(pasos)
    if not puntos:
        return []
    xy = [pasos[i].punto_en(e) for i, e in puntos]
    out = []
    for nombre, indice in superficies:
        zs = indice.cotas(xy)
        if not np.any(np.isfinite(zs)):
            continue
        out.append((nombre, [(e, float(z) if np.isfinite(z) else None) for (_i, e), z in zip(puntos, zs)]))
    return out
