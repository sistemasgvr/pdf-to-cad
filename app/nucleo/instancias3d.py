"""Tubos y esferas de la vista 3D como INSTANCIAS para la GPU (PURO: numpy, sin Qt).

Pedido del usuario 2026-10-16: «los mismos resultados con menos recursos de PC». Casi todo
lo que dibuja la vista 3D es un CÍRCULO barrido por un recorrido (`mallas3d.barrido_camino`:
tuberías, brazos y campanas de los accesorios, el cuerpo curvo de los codos, la vertical de
una conexión, el cuerpo de un buzón redondo) y las esferas de los avisos. Antes cada uno se
guardaba como TRIÁNGULOS sueltos (15 floats por vértice, 6 vértices por cara: un tramo de
12 lados = 4 320 bytes). Ahora un tramo es UNA fila de `CAMPOS_INST` floats (sus dos anillos:
centro, ejes «lado/arriba», inglete y color) y la GPU arma los triángulos con UNA malla
unidad por cantidad de lados (`malla_unidad`): ~30–40 veces menos memoria y nada de
triángulos que calcular.

Mientras `mallas3d.instanciar(Instancias())` está activo (lo usa `modelo3d.construir`),
`barrido_camino` con un perfil circular centrado y `esfera` anotan aquí su forma y devuelven
una malla vacía; fuera de ese bloque (pruebas, otras vistas) devuelven triángulos como
siempre. `expandir` rehace en la CPU EXACTAMENTE los triángulos de antes (mismas operaciones,
mismo orden de cada tramo): es el respaldo de un equipo sin instancing (OpenGL < 3.3) y la
prueba de que el resultado es el mismo.

Fila de una instancia (`CAMPOS_INST` = 34 floats):
  0–2 P0 · 3–5 lado0 · 6–8 arriba0 · 9–11 b0 · 12 f0      anillo de un extremo
  13–15 P1 · 16–18 lado1 · 19–21 arriba1 · 22–24 b1 · 25 f1  anillo del otro
  26–29 color · 30 id · 31 r · 32 radio mínimo (0 = tamaño real) · 33 libre
Un anillo es P + off, off = r·(cos θ·lado + sen θ·arriba); en un vértice interior el inglete
suma (off·b)·f·b (b = dirección del giro, f = 1/cos(giro/2) − 1). TAPA: P0 = centro, b0 =
su normal. ESFERA: P0 = centro, r = radio.
"""
from __future__ import annotations

import numpy as np

CAMPOS_INST = 34
SEG, TAPA, ESFERA = "seg", "tapa", "esfera"
P0, P1, COLOR, ID, R, RMIN = slice(0, 3), slice(13, 16), slice(26, 30), 30, 31, 32
_TROZO = 20000                                 # filas por vez al expandir (memoria acotada)


class Instancias:
    """Junta las instancias de una escena: {(tipo, lados): [filas]}."""

    def __init__(self):
        self._partes = {}

    def _agregar(self, clave, filas):
        self._partes.setdefault(clave, []).append(filas)

    def tubo(self, P, T, lado, arriba, bdir, fac, pts, lados, color, ident, tapas, minimo):
        """Un recorrido de `barrido_camino` (sus anillos ya calculados) como tramos + tapas."""
        n = len(P)
        B, F = np.zeros((n, 3)), np.zeros(n)
        if n > 2:
            B[1:-1], F[1:-1] = bdir, fac[:, 0]
        r = float(pts[0, 0])
        rmin = float(np.max(np.linalg.norm(pts, axis=1))) if minimo else 0.0
        seg = np.zeros((n - 1, CAMPOS_INST))
        seg[:, 0:3], seg[:, 3:6], seg[:, 6:9], seg[:, 9:12], seg[:, 12] = P[:-1], lado[:-1], arriba[:-1], B[:-1], F[:-1]
        seg[:, 13:16], seg[:, 16:19], seg[:, 19:22], seg[:, 22:25], seg[:, 25] = P[1:], lado[1:], arriba[1:], B[1:], F[1:]
        seg[:, COLOR], seg[:, ID], seg[:, R], seg[:, RMIN] = color, ident, r, rmin
        self._agregar((SEG, lados), seg)
        tap = []
        for ok, k, nor in ((tapas[0], 0, -T[0]), (tapas[1], -1, T[-1])):
            if ok:
                f = np.zeros(CAMPOS_INST)
                f[0:3], f[3:6], f[6:9], f[9:12] = P[k], lado[k], arriba[k], nor
                f[COLOR], f[ID], f[R], f[RMIN] = color, ident, r, rmin
                tap.append(f)
        if tap:
            self._agregar((TAPA, lados), np.array(tap))

    def esfera(self, c, r, color, ident, anillos, lados):
        f = np.zeros((1, CAMPOS_INST))
        f[0, 0:3], f[0, COLOR], f[0, ID], f[0, R] = c, color, ident, r
        self._agregar((ESFERA, (anillos, lados)), f)

    def arreglos(self):
        """{(tipo, lados): filas (k, CAMPOS_INST) float64}."""
        return {k: np.concatenate(v) for k, v in self._partes.items() if v}


# ─────────────────────────── mallas unidad (para la GPU) ───────────────────────────

def circulo(lados):
    """El círculo unidad de `mallas3d.perfil_circulo` (mismos números, bit a bit)."""
    a = np.linspace(0.0, 2.0 * np.pi, lados, endpoint=False)
    return np.stack([np.cos(a), np.sin(a)], axis=1)


def esfera_unidad(anillos, lados):
    """Normales de `mallas3d.esfera` en el orden de sus triángulos (mismos números)."""
    th = np.linspace(0, np.pi, anillos + 1)
    ph = np.linspace(0, 2 * np.pi, lados + 1)
    T, P = np.meshgrid(th, ph, indexing="ij")
    u = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], axis=-1)
    a, b = u[:-1, :-1], u[1:, :-1]
    cc, d = u[1:, 1:], u[:-1, 1:]
    return np.stack([a, b, cc, a, cc, d], axis=2).reshape(-1, 3)


def _ijs(lados):
    i = np.arange(lados)
    return i, (i + 1) % lados


def malla_unidad(tipo, lados):
    """Vértices de la malla unidad (n, 3) float32 que la GPU repite por instancia:
    tramo = (cos θ, sen θ, extremo 0/1); tapa = (cos θ, sen θ, 1 = centro); esfera = normal."""
    if tipo == ESFERA:
        return esfera_unidad(*lados).astype(np.float32)
    c = circulo(lados)
    i, j = _ijs(lados)
    if tipo == SEG:
        orden = np.stack([i, i, j, i, j, j], axis=1).reshape(-1)
        ext = np.tile([0.0, 1.0, 1.0, 0.0, 1.0, 0.0], lados)
        return np.column_stack([c[orden], ext]).astype(np.float32)
    orden = np.stack([i, i, j], axis=1).reshape(-1)               # tapa: centro, i, j
    centro = np.tile([1.0, 0.0, 0.0], lados)
    return np.column_stack([np.where(centro[:, None] > 0, 0.0, c[orden]), centro]).astype(np.float32)


# ─────────────────────────── en la CPU: los triángulos de siempre ───────────────────────────

def _anillo(F, k, pts):
    """Anillos (filas, lados, 3) del extremo k (0 o 1) de las filas F, como `barrido_camino`."""
    o = 0 if k == 0 else 13
    P, lado, arriba = F[:, o:o + 3], F[:, o + 3:o + 6], F[:, o + 6:o + 9]
    b, f = F[:, o + 9:o + 12], F[:, o + 12:o + 13]
    off = pts[:, :, 0:1] * lado[:, None, :] + pts[:, :, 1:2] * arriba[:, None, :]
    comp = np.sum(off * b[:, None, :], axis=2, keepdims=True)
    off = off + comp * f[:, None, :] * b[:, None, :]
    return P[:, None, :] + off


def _vertices(pos, nor, filas, rep):
    out = np.empty((len(pos), 15), np.float32)
    out[:, 0:3], out[:, 3:6] = pos, nor
    out[:, 6:10] = np.repeat(filas[:, COLOR], rep, axis=0)
    out[:, 10] = np.repeat(filas[:, ID], rep)
    out[:, 11:14] = pos
    out[:, 14] = 0.0
    return out


def expandir(clave, F):
    """Los triángulos (n, 15) float32 de las filas F de `clave`, iguales a los de antes."""
    tipo, lados = clave
    if not len(F):
        return np.zeros((0, 15), np.float32)
    if tipo == ESFERA:
        nor = esfera_unidad(*lados)
        pos = (F[:, None, 0:3] + nor[None] * F[:, None, R:R + 1]).reshape(-1, 3)
        return _vertices(pos, np.tile(nor, (len(F), 1)), F, len(nor))
    c = circulo(lados)
    pts = c[None] * F[:, R][:, None, None]
    i, j = _ijs(lados)
    if tipo == SEG:
        A, Bn = _anillo(F, 0, pts), _anillo(F, 1, pts)
        ai, aj, bi, bj = A[:, i], A[:, j], Bn[:, i], Bn[:, j]
        pos = np.stack([ai, bi, bj, ai, bj, aj], axis=2).reshape(-1, 3)
        na = c[None, :, 0:1] * F[:, None, 3:6] + c[None, :, 1:2] * F[:, None, 6:9]
        nb = c[None, :, 0:1] * F[:, None, 16:19] + c[None, :, 1:2] * F[:, None, 19:22]
        nrm = np.stack([na[:, i], nb[:, i], nb[:, j], na[:, i], nb[:, j], na[:, j]], axis=2).reshape(-1, 3)
        out = _vertices(pos, nrm, F, 6 * lados)
        if (F[:, RMIN] > 0).any():
            ea = np.broadcast_to(F[:, None, 0:3], ai.shape)
            eb = np.broadcast_to(F[:, None, 13:16], ai.shape)
            eje = np.stack([ea, eb, eb, ea, eb, ea], axis=2).reshape(-1, 3)
            m = np.repeat(F[:, RMIN] > 0, 6 * lados)
            out[m, 11:14] = eje[m]
            out[:, 14] = np.repeat(F[:, RMIN], 6 * lados)
        return out
    A = _anillo(F, 0, pts)                                            # TAPA
    cen = np.broadcast_to(F[:, None, 0:3], A[:, i].shape)
    pos = np.stack([cen, A[:, i], A[:, j]], axis=2).reshape(-1, 3)
    out = _vertices(pos, np.repeat(F[:, 9:12], 3 * lados, axis=0), F, 3 * lados)
    m = np.repeat(F[:, RMIN] > 0, 3 * lados)
    if m.any():
        out[m, 11:14] = np.repeat(F[:, 0:3], 3 * lados, axis=0).astype(np.float32)[m]   # el centro de la tapa
        out[:, 14] = np.repeat(F[:, RMIN], 3 * lados)
    return out


def expandir_todo(inst):
    """Todas las instancias como triángulos (en trozos, para no pedir toda la memoria de golpe)."""
    partes = []
    for clave, F in inst.items():
        for k in range(0, len(F), _TROZO):
            partes.append(expandir(clave, F[k:k + _TROZO]))
    return np.concatenate(partes) if partes else np.zeros((0, 15), np.float32)


def extremos(inst):
    """(mínimo, máximo) de los vértices de todas las instancias (los MISMOS que darían sus
    triángulos en float32), sin armarlos enteros. None si no hay."""
    lo, hi = [], []
    for (tipo, lados), F in inst.items():
        for k in range(0, len(F), _TROZO):
            G = F[k:k + _TROZO]
            if tipo == ESFERA:
                nor = esfera_unidad(*lados)
                q = (G[:, None, 0:3] + nor[None] * G[:, None, R:R + 1]).reshape(-1, 3)
            else:
                pts = circulo(lados)[None] * G[:, R][:, None, None]
                q = _anillo(G, 0, pts).reshape(-1, 3)
                if tipo == SEG:
                    q = np.concatenate([q, _anillo(G, 1, pts).reshape(-1, 3)])
            q = q.astype(np.float32)
            lo.append(q.min(axis=0)); hi.append(q.max(axis=0))
    if not lo:
        return None
    return np.min(lo, axis=0), np.max(hi, axis=0)


def centrar(inst, origen):
    """Las filas con P0/P1 respecto a `origen` (como los triángulos), en float32 para la GPU."""
    out = {}
    for clave, F in inst.items():
        G = F.copy()
        G[:, P0] -= origen
        if clave[0] == SEG:
            G[:, P1] -= origen
        out[clave] = G.astype(np.float32)
    return out


def bytes_de(inst):
    return sum(F.nbytes for F in inst.values())
