"""Primitivas de malla para la vista 3D (PURO: numpy, sin Qt ni OpenGL).

Cada primitiva devuelve un arreglo float32 (n, 15) de vértices de TRIÁNGULOS:
    x, y, z,  nx, ny, nz,  r, g, b, a,  id,  ex, ey, ez,  radio
`ex, ey, ez, radio` = punto del EJE y radio de la sección en las TUBERÍAS (`barrido_camino
(minimo=True)`): el visor las engrosa desde su eje si en pantalla quedarían más finas que
~2 px (de lejos no desaparecen). radio = 0: tamaño real siempre (accesorios, buzones…).
`id` identifica el objeto (utilidad, estructura…) para resaltarlo y elegirlo con el
ratón; 0 = no se puede elegir. Coordenadas en PIES (Z hacia arriba).

`Picks` junta los volúmenes simples (cápsulas) que sirven para saber qué hay bajo
el cursor (`elegir`: rayo contra cápsulas, vectorizado).
"""
from __future__ import annotations

import math

import numpy as np

CAMPOS = 15
VACIA = np.zeros((0, CAMPOS), np.float32)


def _vertices(pos, nor, color, ident):
    n = len(pos)
    out = np.empty((n, CAMPOS), np.float32)
    out[:, 0:3] = pos
    out[:, 3:6] = nor
    out[:, 6:10] = color
    out[:, 10] = ident
    out[:, 11:14] = pos
    out[:, 14] = 0.0
    return out



def juntar(partes):
    partes = [p for p in partes if p is not None and len(p)]
    return np.concatenate(partes).astype(np.float32) if partes else VACIA.copy()


def perfil_circulo(radio, lados=16):
    """Perfil circular: (puntos (n, 2), normales (n, 2), suave=True)."""
    a = np.linspace(0.0, 2.0 * math.pi, lados, endpoint=False)
    c = np.stack([np.cos(a), np.sin(a)], axis=1)
    return c * radio, c, True


def perfil_rect(ancho, alto, dx=0.0, dy=0.0):
    """Perfil rectangular centrado en (dx, dy) (lado, arriba): caras planas."""
    w, h = ancho / 2.0, alto / 2.0
    pts = np.array([[w, -h], [w, h], [-w, h], [-w, -h]]) + [dx, dy]
    return pts, None, False


def barrido(a, b, perfil, color, ident, tapas=(True, True)):
    """Prisma/cilindro del perfil entre los puntos 3D `a` y `b`."""
    return barrido_camino([a, b], perfil, color, ident, tapas)


def barrido_camino(camino, perfil, color, ident, tapas=(True, True), minimo=False):
    """El perfil barrido por TODO un recorrido 3D de una vez (vectorizado). Los anillos
    se COMPARTEN entre tramos: en cada vértice el anillo va sobre la bisectriz (inglete,
    estirado 1/cos(giro/2) en el sentido del giro), así una curva queda lisa, sin
    escalones entre tramos. `minimo` = tubería: lleva su eje y radio para el grosor
    mínimo en pantalla."""
    P = np.asarray(camino, float)
    if len(P) < 2:
        return VACIA
    P = P[np.concatenate([[True], np.linalg.norm(np.diff(P, axis=0), axis=1) > 1e-6])]
    if len(P) < 2:
        return VACIA
    T = np.diff(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    t = np.empty_like(P)
    t[0], t[-1] = T[0], T[-1]
    if len(P) > 2:
        sm = T[:-1] + T[1:]
        ns = np.linalg.norm(sm, axis=1, keepdims=True)
        t[1:-1] = np.where(ns > 1e-6, sm / np.maximum(ns, 1e-12), T[1:])
    ref = np.where(np.abs(t[:, 2:3]) < 0.95, [0.0, 0.0, 1.0], [1.0, 0.0, 0.0])
    lado = np.cross(t, ref)
    lado /= np.linalg.norm(lado, axis=1, keepdims=True)
    arriba = np.cross(lado, t)
    pts, nor, suave = perfil
    off = pts[None, :, 0:1] * lado[:, None, :] + pts[None, :, 1:2] * arriba[:, None, :]      # (m+1, n, 3)
    if len(P) > 2:                                                      # inglete en los vértices
        giro = T[1:] - T[:-1]
        ng = np.linalg.norm(giro, axis=1, keepdims=True)
        bdir = np.where(ng > 1e-9, giro / np.maximum(ng, 1e-12), 0.0)
        cos_m = np.clip(np.sum(t[1:-1] * T[1:], axis=1, keepdims=True), 0.25, 1.0)
        comp = np.sum(off[1:-1] * bdir[:, None, :], axis=2, keepdims=True)
        off[1:-1] += comp * (1.0 / cos_m[:, None, :] - 1.0) * bdir[:, None, :]
    R = P[:, None, :] + off
    n = len(pts)
    i = np.arange(n); j = (i + 1) % n
    ai, aj, bi, bj = R[:-1][:, i], R[:-1][:, j], R[1:][:, i], R[1:][:, j]
    pos = np.stack([ai, bi, bj, ai, bj, aj], axis=2)                                           # (m, n, 6, 3)
    if suave:
        nn = nor[None, :, 0:1] * lado[:, None, :] + nor[None, :, 1:2] * arriba[:, None, :]
        na, nb = nn[:-1], nn[1:]
        nrm = np.stack([na[:, i], nb[:, i], nb[:, j], na[:, i], nb[:, j], na[:, j]], axis=2)
    else:
        nf = np.cross(bi - ai, aj - ai)
        nf /= np.maximum(np.linalg.norm(nf, axis=2, keepdims=True), 1e-12)
        fuera = np.sign(np.sum(nf * ((ai + aj) / 2 - P[:-1, None, :]), axis=2, keepdims=True))
        nf *= np.where(fuera == 0, 1, fuera)
        nrm = np.repeat(nf[:, :, None, :], 6, axis=2)
    partes = [_vertices(pos.reshape(-1, 3), nrm.reshape(-1, 3), color, ident)]
    if minimo:                                   # eje de cada vértice: el centro de SU anillo
        ea, eb = np.broadcast_to(P[:-1, None, :], ai.shape), np.broadcast_to(P[1:, None, :], ai.shape)
        partes[0][:, 11:14] = np.stack([ea, eb, eb, ea, eb, ea], axis=2).reshape(-1, 3)
    if tapas[0]:
        partes.append(_tapa(R[0], P[0], -T[0], color, ident))
    if tapas[1]:
        partes.append(_tapa(R[-1], P[-1], T[-1], color, ident))
    if minimo:
        for parte in partes[1:]:
            parte[:, 11:14] = parte[0, :3]       # el primer vértice de la tapa es su centro (el eje)
        radio = float(np.max(np.linalg.norm(pts, axis=1)))
        for parte in partes:
            parte[:, 14] = radio
    return juntar(partes)


def subcamino(P, s, a, b):
    """Parte del recorrido P (con largos acumulados s) entre los largos a y b."""
    def punto(x):
        k = int(np.clip(np.searchsorted(s, x) - 1, 0, len(s) - 2))
        L = s[k + 1] - s[k]
        t = 0.0 if L < 1e-12 else (x - s[k]) / L
        return P[k] + (P[k + 1] - P[k]) * t
    medio = [P[k] for k in range(len(P)) if a < s[k] < b]
    return np.array([punto(a)] + medio + [punto(b)])


def trozos(camino, trazo, hueco):
    """El recorrido partido en tramos de `trazo` separados por `hueco` (línea a trazos)."""
    P = np.asarray(camino, float)
    if len(P) < 2 or trazo <= 0:
        return [P]
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    out, x = [], 0.0
    while x < s[-1] - 1e-6:
        fin = min(x + trazo, s[-1])
        if fin - x > 1e-3:
            out.append(subcamino(P, s, x, fin))
        x += trazo + hueco
    return out


def _tapa(anillo, centro, normal, color, ident):
    n = len(anillo)
    i = np.arange(n); j = (i + 1) % n
    pos = np.stack([np.repeat(centro[None], n, 0), anillo[i], anillo[j]], axis=1).reshape(-1, 3)
    return _vertices(pos, np.repeat(normal[None], len(pos), 0), color, ident)


def esfera(c, r, color, ident, anillos=6, lados=10):
    c = np.asarray(c, float)
    th = np.linspace(0, math.pi, anillos + 1)
    ph = np.linspace(0, 2 * math.pi, lados + 1)
    T, P = np.meshgrid(th, ph, indexing="ij")
    u = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], axis=-1)
    a, b = u[:-1, :-1], u[1:, :-1]
    cc, d = u[1:, 1:], u[:-1, 1:]
    nor = np.stack([a, b, cc, a, cc, d], axis=2).reshape(-1, 3)
    return _vertices(c + nor * r, nor, color, ident)


def prisma(contorno, z0, z1, color, ident):
    """Prisma vertical de un contorno 2D (polígono convexo, en orden) entre z0 y z1."""
    q = np.asarray(contorno, float)
    if len(q) < 3 or z1 - z0 < 1e-6:
        return VACIA
    n = len(q)
    abajo = np.column_stack([q, np.full(n, z0)])
    arriba = np.column_stack([q, np.full(n, z1)])
    i = np.arange(n); j = (i + 1) % n
    centro = q.mean(axis=0)
    e = q[j] - q[i]
    nf = np.column_stack([e[:, 1], -e[:, 0], np.zeros(n)])
    nf /= np.maximum(np.linalg.norm(nf, axis=1, keepdims=True), 1e-12)
    fuera = np.sign(np.sum(nf[:, :2] * ((q[i] + q[j]) / 2 - centro), axis=1, keepdims=True))
    nf *= np.where(fuera == 0, 1, fuera)
    pos = np.stack([abajo[i], abajo[j], arriba[j], abajo[i], arriba[j], arriba[i]], axis=1).reshape(-1, 3)
    partes = [_vertices(pos, np.repeat(nf, 6, axis=0), color, ident),
              _tapa(arriba, np.append(centro, z1), np.array([0.0, 0.0, 1.0]), color, ident),
              _tapa(abajo, np.append(centro, z0), np.array([0.0, 0.0, -1.0]), color, ident)]
    return juntar(partes)


def cilindro_vertical(c, r, z0, z1, color, ident, lados=20):
    pts = perfil_circulo(r, lados)
    return barrido((c[0], c[1], z0), (c[0], c[1], z1), pts, color, ident)


def plano(xmin, ymin, xmax, ymax, z, color):
    pos = np.array([[xmin, ymin, z], [xmax, ymin, z], [xmax, ymax, z],
                    [xmin, ymin, z], [xmax, ymax, z], [xmin, ymax, z]])
    return _vertices(pos, np.tile([0.0, 0.0, 1.0], (6, 1)), color, 0)


# ─────────────────────────── elegir con el ratón ───────────────────────────

class Picks:
    """Cápsulas (segmento + radio) con el id de su objeto."""

    def __init__(self):
        self._a, self._b, self._r, self._id = [], [], [], []

    def capsula(self, a, b, r, ident):
        self._a.append(a); self._b.append(b); self._r.append(r); self._id.append(ident)

    def __len__(self):
        return len(self._id)

    def arreglos(self):
        if not self._id:
            z = np.zeros((0, 3))
            return z, z, np.zeros(0), np.zeros(0)
        return (np.asarray(self._a, float), np.asarray(self._b, float),
                np.asarray(self._r, float), np.asarray(self._id, float))


def elegir(picks, origen, direccion, r_min=0.0):
    """id del objeto más cercano que corta el rayo (0 = nada);
    `r_min` = radio mínimo (pies) para poder señalar una tubería fina de lejos."""
    A, B, R, I = picks if isinstance(picks, tuple) else picks.arreglos()
    if not len(I):
        return 0
    o = np.asarray(origen, float); d = np.asarray(direccion, float)
    d = d / np.linalg.norm(d)
    u = B - A
    w0 = A - o
    a = np.sum(u * u, axis=1)
    b = u @ d
    e = w0 @ d
    c = np.sum(u * w0, axis=1)
    den = a - b * b
    with np.errstate(divide="ignore", invalid="ignore"):
        sc = np.where(den > 1e-12, (b * e - c) / den, 0.0)
    sc = np.clip(np.nan_to_num(sc), 0.0, 1.0)
    p_seg = A + u * sc[:, None]
    tr = np.maximum((p_seg - o) @ d, 0.0)
    dist = np.linalg.norm(o + d[None] * tr[:, None] - p_seg, axis=1)
    ok = dist <= np.maximum(R, r_min)
    if not ok.any():
        return 0
    k = np.argmin(np.where(ok, tr, np.inf))
    return int(I[k])
