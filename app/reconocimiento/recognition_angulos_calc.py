"""recognition_angulos_calc.py — la matemática de `recognition_angulos` (PURO: numpy).

Rumbos y deflexiones, rejilla de rumbos (φ + k·paso), contactos entre líneas, mínimos
cuadrados con filas duras (rumbos) y blandas (contactos) y el desvío lateral. Ver
`recognition_angulos` para el qué y el porqué.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

from reconocimiento import recognition_indice as indice_mod

Pt = Tuple[float, float]

EXACTO = 1e-9          # rad: deflexión que ya es múltiplo (coma flotante)
_REJILLA_N = 64        # muestras de φ en [0, s) antes de refinar
_DENSO_MAX = 300       # líneas de más vértices: la matriz se arma vértice por vértice


def wrap(x, s):
    """x llevado a [−s/2, s/2) (escalar o arreglo)."""
    return (x + s / 2.0) % s - s / 2.0


def wrap_pi(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def deflexion_deg(a: Pt, b: Pt, c: Pt) -> float:
    """Lo que gira la línea a→b→c en b (grados con signo; 0 = recta)."""
    t1 = math.atan2(b[1] - a[1], b[0] - a[0])
    t2 = math.atan2(c[1] - b[1], c[0] - b[0])
    return math.degrees(wrap_pi(t2 - t1))


def deflexiones_deg(pts, minimo: float = 0.0) -> List[float]:
    """Deflexión en cada quiebre de la polilínea (grados con signo), entre tramos de verdad:
    los más cortos que `minimo` (px) cuentan como un punto."""
    out, prev = [], None
    for a, b in zip(pts, pts[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) < max(minimo, 1e-9):
            continue
        rumbo = math.atan2(b[1] - a[1], b[0] - a[0])
        if prev is not None:
            out.append(math.degrees(wrap_pi(rumbo - prev)))
        prev = rumbo
    return out


def fuera_de_paso_deg(ang: float, paso: float = 0.25) -> float:
    """Cuánto se aparta `ang` (grados) del múltiplo de `paso` más cercano."""
    return abs(ang - paso * round(ang / paso))


def rejilla(rumbos, pesos, s: float) -> float:
    """φ ∈ [0, s) que minimiza Σ peso·(rumbo − rumbo de la rejilla más cercano)²."""
    x = np.mod(np.asarray(rumbos, float), s)
    w = np.asarray(pesos, float)
    if not len(x) or w.sum() <= 0:
        return 0.0
    grid = np.arange(_REJILLA_N) * (s / _REJILLA_N)
    d = wrap(x[None, :] - grid[:, None], s)
    phi = float(grid[int(np.argmin((d * d * w[None, :]).sum(axis=1)))])
    for _ in range(8):                          # con el redondeo fijo, φ = media ponderada
        d = wrap(x - phi, s)
        paso = float((w * d).sum() / w.sum())
        phi += paso
        if abs(paso) < 1e-15:
            break
    return phi % s


def rumbos(P: np.ndarray):
    v = P[1:] - P[:-1]
    return np.arctan2(v[:, 1], v[:, 0]), np.hypot(v[:, 0], v[:, 1])


def objetivo(theta: np.ndarray, L: np.ndarray, phi: float, s: float, minimo: float) -> np.ndarray:
    """Rumbo de cada tramo en la rejilla φ + k·s; un quiebre que ya era múltiplo queda igual
    (dos tramos casi en la misma frontera de redondeo no se separan)."""
    t = theta - wrap(theta - phi, s)
    prev = None
    for k in range(len(t)):
        if L[k] < minimo:
            continue
        if prev is not None:
            d = wrap_pi(theta[k] - theta[prev])
            m = round(d / s)
            if abs(d - m * s) < EXACTO:
                t[k] = t[prev] + m * s
        prev = k
    return t


def contactos(lineas: Sequence[np.ndarray], tol: float):
    """Contactos entre líneas: `V[(i, k)]` = vértices (j, l) en el mismo punto (j ≠ i, o la
    misma línea sin ser vecinos: lazo cerrado) y `S` = [((i, k), (j, l))]: la PUNTA k de i
    sobre el interior del tramo l→l+1 de j (una T)."""
    flat = [(i, k) for i, P in enumerate(lineas) for k in range(len(P))]
    pts = [tuple(lineas[i][k]) for i, k in flat]
    ip = indice_mod.IndicePuntos(pts, max(tol, 1e-6))
    V: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for n, (i, k) in enumerate(flat):
        q = pts[n]
        for o in ip.cerca(q):
            j, l = flat[o]
            if o == n or (j == i and abs(k - l) < 2):
                continue
            if math.hypot(pts[o][0] - q[0], pts[o][1] - q[1]) <= tol:
                V.setdefault((i, k), []).append((j, l))
    it = indice_mod.IndiceTramos([[(tuple(P[l]), tuple(P[l + 1])) for l in range(len(P) - 1)]
                                  for P in lineas], tol, celda=max(64.0, 4.0 * tol))
    S: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    for i, P in enumerate(lineas):
        for k in sorted({0, len(P) - 1}):
            q = P[k]
            con_v = {j for j, _l in V.get((i, k), ())}
            mejor: Dict[int, Tuple[float, int]] = {}
            for j, l in it.cerca((float(q[0]), float(q[1]))):
                if j == i or j in con_v:
                    continue
                a, b = lineas[j][l], lineas[j][l + 1]
                u = b - a
                L = float(math.hypot(u[0], u[1]))
                if L < 1e-9:
                    continue
                t = float(((q - a) @ u) / L)
                d = abs(float((q[0] - a[0]) * u[1] - (q[1] - a[1]) * u[0])) / L
                if tol < t < L - tol and d <= tol and (j not in mejor or d < mejor[j][0]):
                    mejor[j] = (d, l)
            S += [((i, k), (j, l)) for j, (_d, l) in sorted(mejor.items())]
    return V, S


class Uf:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def normal(t: float):
    return -math.sin(t), math.cos(t)


def resolver(P: np.ndarray, duras, rhs_d, blandas, peso: float) -> np.ndarray:
    """Vértices Q que cumplen EXACTO las filas `duras` ([(k, a)…]: Σ a·Q_k = rhs; rumbos de
    los tramos, lazo cerrado), cumplen los contactos `blandas` [(k, a, b): a·Q_k = b] con
    `peso` (si dos contactos se contradicen, el punto medio; nunca se dispara) y se apartan
    lo mínimo de P. Lagrange con H por vértice (2×2)."""
    m = len(P)
    H = np.zeros((m, 2, 2))
    H[:, 0, 0] = H[:, 1, 1] = 1.0
    g = np.array(P, float)
    for k, a, b, w in blandas:
        H[k] += peso * w * np.outer(a, a)
        g[k] += peso * w * b * a
    det = H[:, 0, 0] * H[:, 1, 1] - H[:, 0, 1] * H[:, 1, 0]
    Hi = np.empty_like(H)
    Hi[:, 0, 0], Hi[:, 1, 1] = H[:, 1, 1] / det, H[:, 0, 0] / det
    Hi[:, 0, 1], Hi[:, 1, 0] = -H[:, 0, 1] / det, -H[:, 1, 0] / det
    y = np.einsum("kij,kj->ki", Hi, g)          # solo contactos
    if not duras:
        return y
    if m > _DENSO_MAX:
        return resolver_largo(Hi, y, duras, rhs_d)
    A = np.zeros((len(duras), m, 2))
    for r, fila in enumerate(duras):
        for k, a in fila:
            A[r, k] += a
    AH = np.einsum("rki,kij->rkj", A, Hi)          # A·H⁻¹ (H simétrica por vértice)
    M = np.einsum("rki,ski->rs", AH, A)
    c = np.einsum("rki,ki->r", A, y) - np.asarray(rhs_d, float)
    return y - np.einsum("r,rki->ki", lagrange(M, c), AH)


def lagrange(M, c):
    try:
        lam = np.linalg.solve(M, c)
        if not np.all(np.isfinite(lam)):
            raise np.linalg.LinAlgError
    except np.linalg.LinAlgError:
        lam = np.linalg.lstsq(M, c, rcond=None)[0]
    return lam


def resolver_largo(Hi, y, duras, rhs_d):
    """Lo mismo que `resolver` para una línea de muchísimos vértices: cada fila toca 1–2
    vértices, así que M se arma vértice por vértice (la matriz densa crecería al cubo)."""
    por_v: Dict[int, list] = {}
    for r, fila in enumerate(duras):
        for k, a in fila:
            por_v.setdefault(k, []).append((r, a))
    M = np.zeros((len(duras), len(duras)))
    c = -np.asarray(rhs_d, float)
    for k, lst in por_v.items():
        ha = [(r, Hi[k] @ a) for r, a in lst]
        for r, a in lst:
            c[r] += float(a @ y[k])
            for r2, h in ha:
                M[r, r2] += float(a @ h)
    lam = lagrange(M, c)
    Q = y.copy()
    for k, lst in por_v.items():
        Q[k] -= Hi[k] @ sum(lam[r] * a for r, a in lst)
    return Q


def normales_de_borde(q, bordes, tol: float) -> List[np.ndarray]:
    """Normales (unitarias) de los bordes que pasan por q (≤ tol px): el lado de un polígono
    o la normal radial de un círculo. En una esquina, las dos."""
    out = []
    for borde in bordes or ():
        if not borde:
            continue
        kind, g = borde
        if kind == "circle":
            cx, cy, r = g
            d = math.hypot(q[0] - cx, q[1] - cy)
            if d > 1e-9 and abs(d - r) <= tol:
                out.append(np.array([(q[0] - cx) / d, (q[1] - cy) / d]))
            continue
        for a, c in zip(g, list(g[1:]) + [g[0]]):
            u = np.array([c[0] - a[0], c[1] - a[1]], float)
            L2 = float(u @ u)
            if L2 < 1e-12:
                continue
            w = np.array([q[0] - a[0], q[1] - a[1]], float)
            tt = float(w @ u) / L2
            if -1e-9 <= tt <= 1 + 1e-9 and abs(float(w[0] * u[1] - w[1] * u[0])) / math.sqrt(L2) <= tol:
                n = unit_normal(u)
                if n is not None:
                    out.append(n)
    return out


def lateral(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Cuánto se apartó cada vértice nuevo de la línea de antes (a sus dos tramos vecinos):
    deslizar una punta por su propia recta no aparta el dibujo de la tinta."""
    out = np.hypot(*(Q - P).T)
    if len(P) < 2:
        return out
    A, U = P[:-1], P[1:] - P[:-1]
    L2 = np.einsum("ki,ki->k", U, U)
    ok = L2 >= 1e-18
    L2s = np.where(ok, L2, 1.0)
    # vértice k contra el tramo anterior (k−1, k) y el siguiente (k, k+1)
    w1 = Q[1:] - A                                    # Q_k (k ≥ 1) contra el tramo k−1
    t1 = np.clip(np.einsum("ki,ki->k", w1, U) / L2s, 0.0, 1.0)
    d1 = np.where(ok, np.hypot(*(w1 - t1[:, None] * U).T), np.inf)
    w2 = Q[:-1] - A                                   # Q_k (k ≤ m−2) contra el tramo k
    t2 = np.clip(np.einsum("ki,ki->k", w2, U) / L2s, 0.0, 1.0)
    d2 = np.where(ok, np.hypot(*(w2 - t2[:, None] * U).T), np.inf)
    out[1:] = np.minimum(out[1:], d1)
    out[:-1] = np.minimum(out[:-1], d2)
    return out


def unit_normal(v):
    L = float(math.hypot(v[0], v[1]))
    if L < 1e-12:
        return None
    return np.array([-v[1] / L, v[0] / L])
