"""encaje_mapa_base.py — dónde cae una hoja de OTRO PDF sobre una hoja del editor.

Pedido del usuario 2026-10-23: los mapas llegan en un PDF por utilidad (Phoenix: «QS
Water…», «QS Sewer…», dos PDF de cada una). Tras importar una utilidad, la siguiente se
agrega a la MISMA hoja del editor. Las dos hojas de una misma cuadrícula dibujan el mismo
mapa base (lotes, derecho de vía, calles) con los MISMOS vectores, solo a otra escala y en
otro lugar de la página (agua 17-10 → alcantarillado 17-10: ×1.02856, ~1 500 trazos
idénticos, 0.003 pt de error).

`encajar(origen, destino)` busca la similaridad origen → destino (pt de la hoja VISIBLE de
cada una) igual que `composicion_encaje.encaje_mapa`, pero en toda la hoja y sin mirar el
color ni el grosor (cada utilidad dibuja el mapa base con los suyos): escalas candidatas
por el cociente de largos de trazos con el mismo rumbo, traslación por votos de pares
idénticos (los dos extremos de acuerdo) y ajuste por mínimos cuadrados. Si el dibujo no
lo confirma con claridad (pico dominante, ≥2 rumbos, error chico) devuelve None: nunca se
ubica una hoja «más o menos». `verificar` prueba de una vez una similaridad ya conocida
(dos PDF con la misma plantilla repiten la misma en todas sus hojas).

PURO: fitz (leer los trazos) y numpy.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

MIN_LARGO_PT = 4.0          # trazos más cortos (letras, símbolos) no cuentan
ESCALA_MIN_LARGO_PT = 15.0  # los cocientes de largos solo con trazos así de largos
ESCALA_PASO = 1.0 / 400.0   # resolución de las escalas candidatas (log)
ESCALAS_CANDIDATAS = 4
ANGULO_PASO_DEG = 0.5       # dos trazos «con el mismo rumbo»
TOL_PT = 0.5                # los dos extremos de un par idéntico coinciden ±esto
VOTO_PT = 1.0               # celdas de la votación de traslaciones
MIN_VOTOS = 25
DOMINIO = 3.0               # el pico supera así al segundo (fuera de sus vecinos)
RMS_MAX_PT = 0.25
MIN_RUMBOS = 2              # coincidencias en ≥2 rumbos separados ≥30° (si no, desliza a lo largo)
GIRO_LIBRE_DEG = 0.05       # un giro menor que esto es cero (los mapas de la ciudad van al norte)
MAX_PARES_CUBETA = 6_000_000  # una cubeta de rumbo con más pares se salta (memoria)


@dataclass
class Encaje:
    """Similaridad origen → destino: X = a·x − b·y + tx, Y = b·x + a·y + ty (pt)."""
    a: float
    b: float
    tx: float
    ty: float
    votos: int = 0          # pares de trazos idénticos que la apoyan
    segundo: int = 0        # votos del mejor pico distinto
    rms: float = 0.0        # error de los extremos (pt)

    @property
    def escala(self) -> float:
        return math.hypot(self.a, self.b)

    @property
    def giro_deg(self) -> float:
        return math.degrees(math.atan2(self.b, self.a))

    def mapa(self, x: float, y: float) -> Tuple[float, float]:
        return self.a * x - self.b * y + self.tx, self.b * x + self.a * y + self.ty

    def inversa(self, x: float, y: float) -> Tuple[float, float]:
        qx, qy = x - self.tx, y - self.ty
        n = self.a * self.a + self.b * self.b
        return (self.a * qx + self.b * qy) / n, (-self.b * qx + self.a * qy) / n

    def tupla(self) -> Tuple[float, float, float, float]:
        return self.a, self.b, self.tx, self.ty


# ─────────────────────────── trazos ───────────────────────────
def trazos(page, rect: Optional[Tuple[float, float, float, float]] = None,
           min_largo: float = MIN_LARGO_PT) -> np.ndarray:
    """Segmentos rectos de la hoja VISIBLE (con /Rotate aplicado), (N, 4) x0 y0 x1 y1, con
    el extremo menor primero. Con `rect`, solo los que tienen algún extremo dentro."""
    m = page.rotation_matrix
    ra, rb, rc, rd, re_, rf = m.a, m.b, m.c, m.d, m.e, m.f
    out: List[Tuple[float, float, float, float]] = []
    for p in page.get_cdrawings():
        if "s" not in (p.get("type") or ""):          # solo lo trazado (no rellenos puros)
            continue
        for it in p.get("items") or ():
            if it[0] != "l":
                continue
            (ax, ay), (bx, by) = it[1], it[2]
            out.append((ax * ra + ay * rc + re_, ax * rb + ay * rd + rf,
                        bx * ra + by * rc + re_, bx * rb + by * rd + rf))
    return preparar(np.array(out, float).reshape(-1, 4), rect, min_largo)


def preparar(S: np.ndarray, rect=None, min_largo: float = MIN_LARGO_PT) -> np.ndarray:
    """Filtra por largo (y `rect`) y ordena los extremos (el menor primero)."""
    if not len(S):
        return S.reshape(0, 4)
    L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])
    S = S[L >= min_largo]
    if rect is not None and len(S):
        x0, y0, x1, y1 = rect
        a = (S[:, 0] >= x0) & (S[:, 0] <= x1) & (S[:, 1] >= y0) & (S[:, 1] <= y1)
        b = (S[:, 2] >= x0) & (S[:, 2] <= x1) & (S[:, 3] >= y0) & (S[:, 3] <= y1)
        S = S[a | b]
    S = S.copy()
    sw = (S[:, 0] > S[:, 2]) | ((S[:, 0] == S[:, 2]) & (S[:, 1] > S[:, 3]))
    S[sw] = S[sw][:, [2, 3, 0, 1]]
    return S


def _rasgos(S: np.ndarray):
    L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])
    ang = np.degrees(np.arctan2(S[:, 3] - S[:, 1], S[:, 2] - S[:, 0])) % 180.0
    return L, ang


# ─────────────────────────── escala ───────────────────────────
def escalas(origen: np.ndarray, destino: np.ndarray, n: int = ESCALAS_CANDIDATAS) -> List[float]:
    """Escalas candidatas destino/origen: el cociente de largos más repetido entre trazos
    largos con el mismo rumbo (el mapa base comparte cientos)."""
    La, aa = _rasgos(origen)
    Lb, ab = _rasgos(destino)
    ma, mb = La >= ESCALA_MIN_LARGO_PT, Lb >= ESCALA_MIN_LARGO_PT
    ka = np.round(aa[ma] * 4).astype(int) % 720
    kb = np.round(ab[mb] * 4).astype(int) % 720
    La, Lb = La[ma], Lb[mb]
    votos: Counter = Counter()
    for k in np.unique(ka):
        la, lb = La[ka == k], Lb[kb == k]
        if not len(lb) or len(la) * len(lb) > MAX_PARES_CUBETA // 4:
            continue
        r = np.round(np.log(lb[None, :] / la[:, None]) / ESCALA_PASO).astype(int).ravel()
        votos.update(r.tolist())
    out: List[int] = []
    for k, _c in votos.most_common(60):
        if any(abs(k - o) <= 2 for o in out):
            continue
        out.append(k)
        if len(out) >= n:
            break
    return [math.exp(k * ESCALA_PASO) for k in out]


# ─────────────────────────── traslación ───────────────────────────
def _votar(origen: np.ndarray, destino: np.ndarray, s: float):
    """Pares idénticos (rumbo, largo·s y los dos extremos de acuerdo) → (votos por celda
    de traslación, pares por celda)."""
    La, aa = _rasgos(origen)
    Lb, ab = _rasgos(destino)
    paso = 1.0 / ANGULO_PASO_DEG
    ka = np.round(aa * paso).astype(int) % int(round(180 * paso))
    kb = np.round(ab * paso).astype(int) % int(round(180 * paso))
    claves: List[np.ndarray] = []
    pares: List[np.ndarray] = []
    for k in np.unique(ka):
        ia = np.nonzero(ka == k)[0]
        ib = np.nonzero(kb == k)[0]
        if not len(ib) or len(ia) * len(ib) > MAX_PARES_CUBETA:
            continue
        a = origen[ia] * s
        b = destino[ib]
        ok = np.abs(Lb[ib][None, :] - La[ia][:, None] * s) <= TOL_PT + 0.01 * Lb[ib][None, :]
        i, j = np.nonzero(ok)
        if not len(i):
            continue
        dx = b[j, 0] - a[i, 0]
        dy = b[j, 1] - a[i, 1]
        bien = (np.abs(b[j, 2] - a[i, 2] - dx) <= TOL_PT) & (np.abs(b[j, 3] - a[i, 3] - dy) <= TOL_PT)
        if not bien.any():
            continue
        i, j, dx, dy = i[bien], j[bien], dx[bien], dy[bien]
        claves.append(np.stack([np.round(dx / VOTO_PT), np.round(dy / VOTO_PT)], 1).astype(np.int64))
        pares.append(np.stack([ia[i], ib[j]], 1))
    if not claves:
        return None
    return np.concatenate(claves), np.concatenate(pares)


def _ajuste(origen: np.ndarray, destino: np.ndarray, pares: np.ndarray, giro: bool):
    """Similaridad por mínimos cuadrados sobre los extremos de los pares (sin los raros).
    → (a, b, tx, ty, rms, extremos usados)."""
    P = np.vstack([origen[pares[:, 0], :2], origen[pares[:, 0], 2:]])
    Q = np.vstack([destino[pares[:, 1], :2], destino[pares[:, 1], 2:]])
    keep = np.ones(len(P), bool)
    a = 1.0; b = 0.0; t = np.zeros(2); res = np.zeros(len(P))
    for _ in range(6):
        p, q = P[keep], Q[keep]
        pm, qm = p.mean(0), q.mean(0)
        pc, qc = p - pm, q - qm
        n = float((pc ** 2).sum()) or 1e-12
        a = float((pc * qc).sum()) / n
        b = float((pc[:, 0] * qc[:, 1] - pc[:, 1] * qc[:, 0]).sum()) / n if giro else 0.0
        t = qm - np.array([a * pm[0] - b * pm[1], b * pm[0] + a * pm[1]])
        pred = np.stack([a * P[:, 0] - b * P[:, 1], b * P[:, 0] + a * P[:, 1]], 1) + t
        res = np.hypot(*(Q - pred).T)
        nuevo = res <= max(0.3, 3.0 * float(np.median(res[keep])))
        if (nuevo == keep).all():
            break
        keep = nuevo
    rms = float(np.sqrt((res[keep] ** 2).mean())) if keep.any() else math.inf
    return a, b, float(t[0]), float(t[1]), rms, int(keep.sum())


def _rumbos(origen: np.ndarray, pares: np.ndarray) -> int:
    """Cuántos rumbos distintos (≥30° entre sí, ≥3 pares cada uno) apoyan el pico."""
    _L, ang = _rasgos(origen[pares[:, 0]])
    c = Counter(int(a // 10) % 18 for a in ang)
    grupos: List[float] = []
    for k, n in c.most_common():
        if n < 3:
            break
        a = k * 10 + 5
        if all(min(abs(a - g), 180 - abs(a - g)) >= 30 for g in grupos):
            grupos.append(a)
    return len(grupos)


_DESPL = 1 << 24              # celdas de traslación como UN entero (x mayor): ordenar filas era lo lento


def _pico(claves: np.ndarray):
    """(celda del pico, votos del pico con sus vecinas, votos del mejor pico lejano)."""
    cod = (claves[:, 0] + _DESPL) * (2 * _DESPL) + (claves[:, 1] + _DESPL)
    u, c = np.unique(cod, return_counts=True)
    ux, uy = u // (2 * _DESPL) - _DESPL, u % (2 * _DESPL) - _DESPL
    i = int(np.argmax(c))
    k = np.array([ux[i], uy[i]], dtype=np.int64)
    dmax = np.maximum(np.abs(ux - k[0]), np.abs(uy - k[1]))
    n = int(c[dmax <= 1].sum())
    lejos = dmax > 2
    seg = int(c[lejos].max()) if lejos.any() else 0
    return k, n, seg


def encajar(origen: np.ndarray, destino: np.ndarray, escala: Optional[float] = None) -> Optional[Encaje]:
    """Similaridad origen → destino por el mapa base que comparten, o None si el dibujo no
    la confirma. `escala` conocida (otra hoja del mismo par de PDF) ahorra buscarla."""
    if len(origen) < MIN_VOTOS or len(destino) < MIN_VOTOS:
        return None
    cands = [escala] if escala else escalas(origen, destino)
    mejor = None
    for s in cands:
        v = _votar(origen, destino, s)
        if v is None:
            continue
        claves, pares = v
        k, n, seg = _pico(claves)
        if mejor is None or n > mejor[0]:
            sel = np.abs(claves - k).max(1) <= 1
            mejor = (n, seg, pares[sel])
    if mejor is None:
        return None
    n, seg, pares = mejor
    if n < MIN_VOTOS or n < DOMINIO * seg or _rumbos(origen, pares) < MIN_RUMBOS:
        return None
    a, b, tx, ty, rms, _m = _ajuste(origen, destino, pares, giro=True)
    if abs(math.degrees(math.atan2(b, a))) < GIRO_LIBRE_DEG:
        a, b, tx, ty, rms, _m = _ajuste(origen, destino, pares, giro=False)
    if rms > RMS_MAX_PT:
        return None
    return Encaje(a, b, tx, ty, votos=n, segundo=seg, rms=rms)


def verificar(origen: np.ndarray, destino: np.ndarray, e: Encaje) -> Optional[Encaje]:
    """¿La similaridad `e` (de otra hoja del mismo par de PDF) vale también aquí? Cuenta los
    trazos de `origen` que, llevados por `e`, caen sobre uno idéntico de `destino`; si son
    bastantes, la reajusta con ellos (misma exigencia que `encajar`)."""
    if len(origen) < MIN_VOTOS or len(destino) < MIN_VOTOS:
        return None
    P = np.empty_like(origen)
    P[:, 0] = e.a * origen[:, 0] - e.b * origen[:, 1] + e.tx
    P[:, 1] = e.b * origen[:, 0] + e.a * origen[:, 1] + e.ty
    P[:, 2] = e.a * origen[:, 2] - e.b * origen[:, 3] + e.tx
    P[:, 3] = e.b * origen[:, 2] + e.a * origen[:, 3] + e.ty
    celda: Dict[Tuple[int, int], List[int]] = {}
    for j, (x, y) in enumerate(zip(np.floor(destino[:, 0] / 2.0), np.floor(destino[:, 1] / 2.0))):
        celda.setdefault((int(x), int(y)), []).append(j)
    pares: List[Tuple[int, int]] = []
    for i, (x0, y0, x1, y1) in enumerate(P):
        cx, cy = int(math.floor(x0 / 2.0)), int(math.floor(y0 / 2.0))
        hecho = False
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for j in celda.get((cx + ox, cy + oy), ()):
                    d = destino[j]
                    if (abs(d[0] - x0) <= TOL_PT and abs(d[1] - y0) <= TOL_PT
                            and abs(d[2] - x1) <= TOL_PT and abs(d[3] - y1) <= TOL_PT):
                        pares.append((i, j))
                        hecho = True
                        break
                if hecho:
                    break
            if hecho:
                break
    if len(pares) < MIN_VOTOS:
        return None
    pz = np.array(pares, int)
    if _rumbos(origen, pz) < MIN_RUMBOS:
        return None
    giro = abs(e.giro_deg) >= GIRO_LIBRE_DEG
    a, b, tx, ty, rms, _m = _ajuste(origen, destino, pz, giro=giro)
    if rms > RMS_MAX_PT:
        return None
    return Encaje(a, b, tx, ty, votos=len(pares), segundo=0, rms=rms)


def componer(e: Encaje, a: float, b: float, tx: float, ty: float) -> Encaje:
    """La similaridad (a, b, tx, ty) aplicada DESPUÉS de `e`."""
    return Encaje(a * e.a - b * e.b, a * e.b + b * e.a,
                  a * e.tx - b * e.ty + tx, b * e.tx + a * e.ty + ty,
                  votos=e.votos, segundo=e.segundo, rms=e.rms)


def de_tupla(m: Sequence[float]) -> Encaje:
    return Encaje(float(m[0]), float(m[1]), float(m[2]), float(m[3]))
