"""Triángulos de la válvula para la Vista 3D (2026-11-05), PURO (numpy): cada pieza de `valvula_receta` como
superficie. Sin booleanas: las piezas se tocan o se meten unas en otras como los sólidos que el plugin une
(`ValvulaReceta.cs`); lo que queda dentro no se ve. Las bridas llevan sus agujeros de pernos y todas las piezas
huecas su paso interior, como en Civil 3D. Pulgadas, mismo sistema que la receta."""
from __future__ import annotations

import math

import numpy as np

LADOS = 48            # lados de los cilindros grandes
LADOS_CHICO = 24      # cilindros delgados (rayos, vástago, eje del volante)
LADOS_AGUJERO = 12
LADOS_TORO = (48, 12)


def _anillo(r, n, desfase=0.0):
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False) + desfase
    return np.cos(a) * r, np.sin(a) * r, a


def _quads(p00, p01, p11, p10):
    """Dos triángulos por cuadrilátero (arreglos (m, 3) de las 4 esquinas en orden)."""
    return np.stack([p00, p01, p11, p00, p11, p10], axis=1).reshape(-1, 3)


def _lateral(eje, a, b, r, n, afuera=True):
    """Superficie lateral de un cilindro de radio r a lo largo de `eje` (0/1/2) entre a y b, centrado en 0."""
    u, v, ang = _anillo(r, n)
    u2, v2 = np.roll(u, -1), np.roll(v, -1)
    k = [i for i in range(3) if i != eje]

    def P(t, uu, vv):
        q = np.zeros((len(uu), 3))
        q[:, eje] = t
        q[:, k[0]] = uu
        q[:, k[1]] = vv
        return q
    pos = _quads(P(a, u, v), P(b, u, v), P(b, u2, v2), P(a, u2, v2))
    nu, nv = np.cos(ang), np.sin(ang)
    nu2, nv2 = np.roll(nu, -1), np.roll(nv, -1)
    n0 = P(0.0, nu, nv); n1 = P(0.0, nu2, nv2)
    nor = np.stack([n0, n0, n1, n0, n1, n1], axis=1).reshape(-1, 3)
    if not afuera:
        pos = pos.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
        nor = -nor.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
    return pos, nor


def _disco(eje, t, r_ext, r_int, n, signo):
    """Corona (o disco si r_int = 0) en el plano eje = t, normal `signo` sobre el eje."""
    k = [i for i in range(3) if i != eje]
    u, v, _a = _anillo(1.0, n)
    u2, v2 = np.roll(u, -1), np.roll(v, -1)

    def P(r, uu, vv):
        q = np.zeros((len(uu), 3))
        q[:, eje] = t
        q[:, k[0]] = uu * r
        q[:, k[1]] = vv * r
        return q
    if r_int > 0:
        pos = _quads(P(r_int, u, v), P(r_ext, u, v), P(r_ext, u2, v2), P(r_int, u2, v2))
    else:
        c = np.zeros((n, 3)); c[:, eje] = t
        pos = np.stack([c, P(r_ext, u, v), P(r_ext, u2, v2)], axis=1).reshape(-1, 3)
    return _orientar(pos, eje, signo)


def _orientar(pos, eje, signo):
    """Gira cada triángulo para que su normal apunte a `signo` sobre `eje`; normales planas."""
    tri = pos.reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    al_reves = nrm[:, eje] * signo < 0
    tri[al_reves] = tri[al_reves][:, ::-1]
    nor = np.zeros((len(tri), 3)); nor[:, eje] = signo
    return tri.reshape(-1, 3), np.repeat(nor, 3, axis=0)


def _plano_con_agujeros(eje, t, r_ext, r_int, r_p, n_p, r_ag, signo):
    """Cara de la brida: corona r_int–r_ext con n_p agujeros de radio r_ag en el círculo r_p (ángulos
    (i+½)·360/n_p desde el primer eje del plano hacia el segundo, como el plugin)."""
    if n_p <= 0 or r_ag <= 0:
        return _disco(eje, t, r_ext, r_int, LADOS, signo)
    m = max(r_ag * 1.35, r_ag + 0.05)                # media celda alrededor de cada agujero
    m = min(m, r_p * math.sin(math.pi / n_p) * 0.95, r_ext - r_p - 0.01, r_p - r_int - 0.01)
    if m <= r_ag:
        return _disco(eje, t, r_ext, r_int, LADOS, signo)
    partes = [_disco(eje, t, r_ext, r_p + m, LADOS, signo)[0], _disco(eje, t, r_p - m, r_int, LADOS, signo)[0]]
    k = [i for i in range(3) if i != eje]
    paso = 2 * math.pi / n_p
    d_ang = m / r_p                                  # media celda en ángulo
    tramos = max(2, int(math.ceil((paso - 2 * d_ang) / (2 * math.pi / LADOS))))
    K = LADOS_AGUJERO * 2

    def P(r, ang):
        q = np.zeros((len(r), 3))
        q[:, eje] = t
        q[:, k[0]] = r * np.cos(ang)
        q[:, k[1]] = r * np.sin(ang)
        return q
    for i in range(n_p):
        th = (i + 0.5) * paso
        # celda con agujero: contorno del cuadrado (en coord. locales u = tangente, v = radial) y del círculo
        phi = np.linspace(0, 2 * math.pi, K, endpoint=False)
        cu, cv = np.cos(phi), np.sin(phi)
        s = m / np.maximum(np.abs(cu), np.abs(cv))
        su, sv = cu * s, cv * s
        hu, hv = cu * r_ag, cv * r_ag

        def a_polar(u, v):
            return r_p + v, th + u / r_p
        r1, a1 = a_polar(su, sv); r2, a2 = a_polar(hu, hv)
        q_s, q_h = P(r1, a1), P(r2, a2)
        partes.append(_quads(q_s, q_h, np.roll(q_h, -1, 0), np.roll(q_s, -1, 0)))
        # tramo de corona entre esta celda y la siguiente
        a0, a1_ = th + d_ang, th + paso - d_ang
        angs = np.linspace(a0, a1_, tramos + 1)
        r_lo, r_hi = np.full(tramos + 1, r_p - m), np.full(tramos + 1, r_p + m)
        lo, hi = P(r_lo, angs), P(r_hi, angs)
        partes.append(_quads(lo[:-1], hi[:-1], hi[1:], lo[1:]))
    return _orientar(np.concatenate(partes), eje, signo)


def _paredes_agujeros(x0, x1, r_p, n_p, r_ag):
    out_p, out_n = [], []
    paso = 2 * math.pi / n_p
    for i in range(n_p):
        th = (i + 0.5) * paso
        cy, cz = r_p * math.cos(th), r_p * math.sin(th)
        p, nn = _lateral(0, x0, x1, r_ag, LADOS_AGUJERO, afuera=False)
        p = p + [0.0, cy, cz]
        out_p.append(p); out_n.append(nn)
    return np.concatenate(out_p), np.concatenate(out_n)


def _caja(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    caras = [((0, 3, 2, 1), (0, 0, -1)), ((4, 5, 6, 7), (0, 0, 1)), ((0, 1, 5, 4), (0, -1, 0)),
             ((2, 3, 7, 6), (0, 1, 0)), ((1, 2, 6, 5), (1, 0, 0)), ((3, 0, 4, 7), (-1, 0, 0))]
    pos, nor = [], []
    for (a, b, c, d), nn in caras:
        pos += [v[a], v[b], v[c], v[a], v[c], v[d]]
        nor += [nn] * 6
    return np.array(pos, float), np.array(nor, float)


def _toro(c, R, r):
    n1, n2 = LADOS_TORO
    a = np.linspace(0, 2 * math.pi, n1 + 1)[:, None]
    b = np.linspace(0, 2 * math.pi, n2 + 1)[None, :]
    # aro en el plano XZ, eje Y
    nx = np.cos(a) * np.cos(b); nz = np.sin(a) * np.cos(b); ny = np.sin(b) * np.ones_like(a)
    px = (R + r * np.cos(b)) * np.cos(a); pz = (R + r * np.cos(b)) * np.sin(a); py = r * np.sin(b) * np.ones_like(a)
    P = np.stack([px, py, pz], -1) + np.asarray(c, float)
    N = np.stack([nx, ny, nz], -1)
    pos = _quads(P[:-1, :-1].reshape(-1, 3), P[1:, :-1].reshape(-1, 3), P[1:, 1:].reshape(-1, 3),
                 P[:-1, 1:].reshape(-1, 3))
    nor = _quads(N[:-1, :-1].reshape(-1, 3), N[1:, :-1].reshape(-1, 3), N[1:, 1:].reshape(-1, 3),
                 N[:-1, 1:].reshape(-1, 3))
    tri = pos.reshape(-1, 3, 3)
    g = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    al_reves = np.sum(g * nor.reshape(-1, 3, 3)[:, 0], axis=1) < 0
    tri[al_reves] = tri[al_reves][:, ::-1]
    nr = nor.reshape(-1, 3, 3); nr[al_reves] = nr[al_reves][:, ::-1]
    return tri.reshape(-1, 3), nr.reshape(-1, 3)


def _coherente(pos, nor):
    """Cada triángulo con su vuelta de acuerdo a su normal (la cara de afuera, como las demás mallas)."""
    tri = pos.reshape(-1, 3, 3).copy()
    nr = nor.reshape(-1, 3, 3).copy()
    g = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    al_reves = np.sum(g * nr.mean(axis=1), axis=1) < 0
    tri[al_reves] = tri[al_reves][:, ::-1]
    nr[al_reves] = nr[al_reves][:, ::-1]
    return tri.reshape(-1, 3), nr.reshape(-1, 3)


def pieza(p):
    """(posiciones, normales) en pulgadas de una pieza de la receta."""
    return _coherente(*_pieza(p))


def _pieza(p):
    f = p[0]
    if f in ("tubo", "brida"):
        x0, x1, r, ri = p[2], p[3], p[4], p[5]
        partes = [_lateral(0, x0, x1, r, LADOS), _lateral(0, x0, x1, ri, LADOS, afuera=False)]
        if f == "brida":
            rp, n_p, ra = p[6], p[7], p[8]
            partes += [_plano_con_agujeros(0, x0, r, ri, rp, n_p, ra, -1),
                       _plano_con_agujeros(0, x1, r, ri, rp, n_p, ra, 1)]
            if n_p > 0 and ra > 0:
                partes.append(_paredes_agujeros(x0, x1, rp, n_p, ra))
        else:
            partes += [_disco(0, x0, r, ri, LADOS, -1), _disco(0, x1, r, ri, LADOS, 1)]
        return np.concatenate([a for a, _ in partes]), np.concatenate([b for _, b in partes])
    if f == "caja":
        return _caja(p[2], p[3])
    if f == "cil":
        _, _, eje, c, largo, r = p
        e = "xyz".index(eje)
        lados = LADOS if r > 2.0 else LADOS_CHICO
        partes = [_lateral(e, 0.0, largo, r, lados), _disco(e, 0.0, r, 0.0, lados, -1),
                  _disco(e, largo, r, 0.0, lados, 1)]
        pos = np.concatenate([a for a, _ in partes]) + np.asarray(c, float)
        return pos, np.concatenate([b for _, b in partes])
    if f == "toro":
        return _toro(p[2], p[3], p[4])
    raise ValueError(f)


def malla(rec):
    """(posiciones, normales, capa por vértice) en pulgadas de la receta entera."""
    pos, nor, capa = [], [], []
    for p in rec.piezas:
        a, b = pieza(p)
        pos.append(a); nor.append(b); capa.append(np.full(len(a), p[1], np.int8))
    return np.concatenate(pos), np.concatenate(nor), np.concatenate(capa)
