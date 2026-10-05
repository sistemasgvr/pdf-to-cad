"""recognition_letter_shapes.py — Lee UNA letra dibujada con trazos (puro, sin Qt ni fitz).

Las letras del linetype de una utilidad («—TE—», «—w—», «—ss—») llegan al PDF como
VECTORES de una fuente SHX de AutoCAD (txt, simplex, romans…), no como texto: no hay
nada que `get_text` pueda leer. Aquí se comparan esos trazos con una plantilla de
trazos por carácter (A–Z, a–z, «(», «)», «/»), dibujadas a mano con las proporciones
de las fuentes de línea simple:

  · la letra se normaliza a alto 1 y se centra en x; la plantilla se estira al ANCHO
    de la letra (las fuentes difieren sobre todo en el ancho) salvo que alguna de las
    dos sea delgada (`NARROW`: «I», «l», «(» no se estiran);
  · distancia = chaflán simétrico medio: de cada muestra de la letra al trazo más
    cercano de la plantilla y viceversa (en altos de letra), más un castigo por la
    diferencia de ancho (`WIDTH_PENALTY`).

Verificado con la leyenda de DU08 h.33 (todas las muestras: e, g, o, ss, sd, t, unk,
w, e(oh), t(oh), E, G, SS, T, W, SC, SE, TE). Una lectura con puntaje > `GOOD_SCORE`
no se da por buena (`recognition_letters` la descarta). Todas las plantillas se
evalúan juntas con numpy (~1 ms por letra) y cada forma se lee una sola vez
(`read_letter` guarda la respuesta por la forma redondeada).
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

Pt = Tuple[float, float]

NARROW = 0.3            # ancho/alto: por debajo, la letra (o la plantilla) no se estira en x
STEP = 0.06             # paso de muestreo de los trazos, en altos de letra
WIDTH_PENALTY = 0.08    # × |ln(ancho letra / ancho plantilla)|
GOOD_SCORE = 0.08       # lectura confiable (medido: letras reales 0.002–0.06; ruido ≥0.1)
_CACHE_STEP = 0.05      # la forma se redondea a esto (alto 1) para no leerla dos veces


def _ellipse(cx: float, cy: float, rx: float, ry: float, n: int = 24) -> List[Pt]:
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n))
            for k in range(n + 1)]


# Plantillas: trazos en una caja con y hacia ARRIBA (la base de la letra en y=0).
_BOWL_L = [(0.5, 0.47), (0.4, 0.57), (0.3, 0.6), (0.18, 0.6), (0.07, 0.53), (0, 0.4), (0, 0.22),
           (0.07, 0.07), (0.18, 0), (0.3, 0), (0.4, 0.04), (0.5, 0.13)]      # panza abierta a la derecha
_BOWL_R = [(0, 0.47), (0.1, 0.57), (0.2, 0.6), (0.32, 0.6), (0.43, 0.53), (0.5, 0.4), (0.5, 0.22),
           (0.43, 0.07), (0.32, 0), (0.2, 0), (0.1, 0.04), (0, 0.13)]        # …abierta a la izquierda
_C = [(0.75, 0.8), (0.65, 0.95), (0.5, 1), (0.3, 1), (0.12, 0.9), (0.03, 0.75), (0, 0.5),
      (0.03, 0.25), (0.12, 0.1), (0.3, 0), (0.5, 0), (0.65, 0.05), (0.75, 0.2)]
_P = [(0, 0), (0, 1), (0.5, 1), (0.65, 0.93), (0.7, 0.8), (0.7, 0.68), (0.65, 0.57), (0.5, 0.5), (0, 0.5)]
_ARCH = [(0, 0.42), (0.12, 0.55), (0.25, 0.6), (0.35, 0.6), (0.45, 0.55), (0.5, 0.42), (0.5, 0)]

TEMPLATES: Dict[str, List[List[Pt]]] = {
    "A": [[(0, 0), (0.4, 1), (0.8, 0)], [(0.15, 0.38), (0.65, 0.38)]],
    "B": [[(0, 0), (0, 1), (0.45, 1), (0.6, 0.95), (0.65, 0.88), (0.65, 0.62), (0.6, 0.55), (0.45, 0.5), (0, 0.5)],
          [(0.45, 0.5), (0.62, 0.45), (0.7, 0.38), (0.7, 0.12), (0.62, 0.05), (0.45, 0), (0, 0)]],
    "C": [_C],
    "D": [[(0, 0), (0, 1), (0.35, 1), (0.55, 0.92), (0.68, 0.75), (0.72, 0.5), (0.68, 0.25), (0.55, 0.08),
           (0.35, 0), (0, 0)]],
    "E": [[(0.62, 1), (0, 1), (0, 0), (0.62, 0)], [(0, 0.5), (0.38, 0.5)]],
    "F": [[(0.62, 1), (0, 1), (0, 0)], [(0, 0.5), (0.38, 0.5)]],
    "G": [_C + [(0.75, 0.45)], [(0.45, 0.45), (0.75, 0.45)]],
    "H": [[(0, 0), (0, 1)], [(0.7, 0), (0.7, 1)], [(0, 0.5), (0.7, 0.5)]],
    "I": [[(0, 0), (0, 1)]],
    "J": [[(0.5, 1), (0.5, 0.2), (0.42, 0.05), (0.25, 0), (0.1, 0.05), (0, 0.2), (0, 0.3)]],
    "K": [[(0, 0), (0, 1)], [(0.7, 1), (0, 0.33)], [(0.25, 0.57), (0.7, 0)]],
    "L": [[(0, 1), (0, 0), (0.6, 0)]],
    "M": [[(0, 0), (0, 1), (0.4, 0), (0.8, 1), (0.8, 0)]],
    "N": [[(0, 0), (0, 1), (0.7, 0), (0.7, 1)]],
    "O": [_ellipse(0.4, 0.5, 0.4, 0.5)],
    "P": [_P],
    "Q": [_ellipse(0.4, 0.5, 0.4, 0.5), [(0.45, 0.25), (0.8, -0.05)]],
    "R": [_P, [(0.4, 0.5), (0.7, 0)]],
    "S": [[(0.7, 0.85), (0.6, 0.97), (0.4, 1), (0.2, 0.97), (0.05, 0.85), (0.05, 0.65), (0.15, 0.55),
           (0.55, 0.45), (0.67, 0.35), (0.7, 0.15), (0.6, 0.03), (0.4, 0), (0.2, 0), (0.05, 0.12)]],
    "T": [[(0, 1), (0.7, 1)], [(0.35, 1), (0.35, 0)]],
    "U": [[(0, 1), (0, 0.3), (0.05, 0.1), (0.2, 0), (0.5, 0), (0.65, 0.1), (0.7, 0.3), (0.7, 1)]],
    "V": [[(0, 1), (0.4, 0), (0.8, 1)]],
    "W": [[(0, 1), (0.25, 0), (0.5, 1), (0.75, 0), (1, 1)]],
    "X": [[(0, 1), (0.7, 0)], [(0, 0), (0.7, 1)]],
    "Y": [[(0, 1), (0.35, 0.5), (0.7, 1)], [(0.35, 0.5), (0.35, 0)]],
    "Z": [[(0, 1), (0.7, 1), (0, 0), (0.7, 0)]],
    "a": [[(0.5, 0.6), (0.5, 0)], _BOWL_L],
    "b": [[(0, 1), (0, 0)], _BOWL_R],
    "c": [_BOWL_L],
    "d": [[(0.5, 1), (0.5, 0)], _BOWL_L],
    "e": [[(0, 0.3), (0.5, 0.3), (0.5, 0.38), (0.45, 0.5), (0.38, 0.57), (0.28, 0.6), (0.18, 0.6), (0.07, 0.53),
           (0, 0.4), (0, 0.22), (0.07, 0.07), (0.18, 0), (0.3, 0), (0.42, 0.04), (0.5, 0.12)]],
    "f": [[(0.4, 1), (0.3, 1), (0.2, 0.95), (0.15, 0.85), (0.15, 0)], [(0, 0.6), (0.35, 0.6)]],
    "g": [[(0.5, 0.6), (0.5, -0.1), (0.45, -0.25), (0.38, -0.32), (0.28, -0.35), (0.15, -0.35), (0.05, -0.3)],
          _BOWL_L],
    "h": [[(0, 1), (0, 0)], _ARCH],
    "k": [[(0, 1), (0, 0)], [(0.45, 0.6), (0, 0.2)], [(0.18, 0.35), (0.5, 0)]],
    "m": [[(0, 0.6), (0, 0)], [(0, 0.42), (0.1, 0.55), (0.2, 0.6), (0.3, 0.6), (0.38, 0.55), (0.42, 0.42), (0.42, 0)],
          [(0.42, 0.42), (0.5, 0.55), (0.6, 0.6), (0.7, 0.6), (0.8, 0.55), (0.84, 0.42), (0.84, 0)]],
    "n": [[(0, 0.6), (0, 0)], _ARCH],
    "o": [_ellipse(0.27, 0.3, 0.27, 0.3)],
    "p": [[(0, 0.6), (0, -0.35)], _BOWL_R],
    "q": [[(0.5, 0.6), (0.5, -0.35)], _BOWL_L],
    "r": [[(0, 0.6), (0, 0)], [(0, 0.35), (0.07, 0.5), (0.17, 0.58), (0.27, 0.6), (0.35, 0.6)]],
    "s": [[(0.47, 0.5), (0.4, 0.57), (0.27, 0.6), (0.15, 0.6), (0.04, 0.55), (0, 0.47), (0.04, 0.38), (0.12, 0.34),
           (0.35, 0.27), (0.44, 0.23), (0.48, 0.15), (0.48, 0.12), (0.44, 0.05), (0.32, 0), (0.17, 0), (0.05, 0.05),
           (0, 0.12)]],
    # «t» de simplex/romans (DU08 h.33): asta con gancho + travesaño a 2/3 del alto
    "t": [[(1.0, 7.2), (1.03, 1.37), (1.4, 0.29), (2.06, 0), (2.72, 0)], [(0, 4.8), (2.4, 4.8)]],
    "u": [[(0, 0.6), (0, 0.18), (0.05, 0.05), (0.15, 0), (0.3, 0), (0.4, 0.05), (0.5, 0.18)], [(0.5, 0.6), (0.5, 0)]],
    "v": [[(0, 0.6), (0.3, 0), (0.6, 0.6)]],
    "w": [[(0, 0.6), (0.2, 0), (0.4, 0.6), (0.6, 0), (0.8, 0.6)]],
    "x": [[(0, 0.6), (0.5, 0)], [(0, 0), (0.5, 0.6)]],
    "y": [[(0, 0.6), (0.3, 0)], [(0.6, 0.6), (0.3, 0), (0.2, -0.25), (0.1, -0.33), (0, -0.35)]],
    "z": [[(0, 0.6), (0.5, 0.6), (0, 0), (0.5, 0)]],
    "(": [[(0.3, 1.0), (0.12, 0.8), (0.03, 0.55), (0, 0.35), (0.03, 0.15), (0.12, -0.1), (0.3, -0.3)]],
    ")": [[(0, 1.0), (0.18, 0.8), (0.27, 0.55), (0.3, 0.35), (0.27, 0.15), (0.18, -0.1), (0, -0.3)]],
    "/": [[(0, 0), (0.5, 1)]],
}


def _bbox(strokes: Sequence[Sequence[Pt]]) -> Tuple[float, float, float, float]:
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), min(ys), max(xs), max(ys)


def _normalize(strokes: Sequence[Sequence[Pt]]) -> Tuple[List[List[Pt]], float]:
    """Alto 1, base en y=0, centrada en x=0. Devuelve (trazos, ancho/alto)."""
    x0, y0, x1, y1 = _bbox(strokes)
    h = max(y1 - y0, 1e-6)
    cx = (x0 + x1) / 2.0
    return [[((x - cx) / h, (y - y0) / h) for x, y in s] for s in strokes], (x1 - x0) / h


def _samples(strokes: Sequence[Sequence[Pt]], step: float = STEP) -> List[Pt]:
    out: List[Pt] = []
    for s in strokes:
        out.append(s[0])
        for a, b in zip(s, s[1:]):
            n = max(1, int(math.dist(a, b) / step))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


def _segments(strokes: Sequence[Sequence[Pt]]):
    segs = [(a, b) for s in strokes for a, b in zip(s, s[1:])]
    return segs or [(s[0], s[0]) for s in strokes]


class _Bank:
    """Todas las plantillas en arreglos planos (índice de plantilla por muestra/segmento)."""

    def __init__(self):
        self.chars = list(TEMPLATES)
        pts, pidx, a, b, sidx, widths = [], [], [], [], [], []
        for i, ch in enumerate(self.chars):
            norm, w = _normalize(TEMPLATES[ch])
            widths.append(w)
            sp = _samples(norm)
            pts += sp
            pidx += [i] * len(sp)
            for p, q in _segments(norm):
                a.append(p); b.append(q); sidx.append(i)
        n = len(self.chars)
        self.P, self.pidx = np.array(pts, float), np.array(pidx)
        self.A, self.B, self.sidx = np.array(a, float), np.array(b, float), np.array(sidx)
        self.w = np.array(widths, float)
        self.pstart = np.searchsorted(self.pidx, np.arange(n))
        self.sstart = np.searchsorted(self.sidx, np.arange(n))
        self.pcount = np.bincount(self.pidx, minlength=n)


_BANK: _Bank | None = None
_READ: Dict[tuple, Tuple[str, float]] = {}


def _bank() -> _Bank:
    global _BANK
    if _BANK is None:
        _BANK = _Bank()
    return _BANK


def _pt_seg2(P: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Distancias AL CUADRADO (n × m) de los puntos P a los segmentos A→B."""
    abx, aby = B[:, 0] - A[:, 0], B[:, 1] - A[:, 1]
    L2 = np.maximum(abx * abx + aby * aby, 1e-12)
    apx = P[:, 0, None] - A[None, :, 0]
    apy = P[:, 1, None] - A[None, :, 1]
    t = np.clip((apx * abx + apy * aby) / L2, 0.0, 1.0)
    dx = apx - t * abx
    dy = apy - t * aby
    return dx * dx + dy * dy


def scores(strokes: Sequence[Sequence[Pt]]) -> np.ndarray:
    """Puntaje de cada plantilla (orden de `TEMPLATES`; menor = más parecida)."""
    bk = _bank()
    norm, lw = _normalize(strokes)
    lp = np.array(_samples(norm), float)
    segs = _segments(norm)
    la = np.array([p for p, _ in segs], float)
    lb = np.array([q for _, q in segs], float)
    k = np.where((bk.w >= NARROW) & (lw >= NARROW), lw / np.maximum(bk.w, 1e-6), 1.0)
    A, B, P = bk.A.copy(), bk.B.copy(), bk.P.copy()
    A[:, 0] *= k[bk.sidx]; B[:, 0] *= k[bk.sidx]; P[:, 0] *= k[bk.pidx]
    d_letter = np.sqrt(np.minimum.reduceat(_pt_seg2(lp, A, B), bk.sstart, axis=1)).mean(0)  # letra → plantilla
    d_templ = np.add.reduceat(np.sqrt(_pt_seg2(P, la, lb).min(1)), bk.pstart) / bk.pcount  # plantilla → letra
    pen = WIDTH_PENALTY * np.abs(np.log(max(lw, 0.05) / np.maximum(bk.w, 0.05)))
    return 0.5 * (d_letter + d_templ) + pen


def read_letter(strokes: Sequence[Sequence[Pt]]) -> Tuple[str, float]:
    """(carácter, puntaje) de la plantilla más parecida a los trazos de UNA letra."""
    x0, y0, _x1, y1 = _bbox(strokes)
    h = max(y1 - y0, 1e-6)
    key = tuple(sorted(tuple((round((x - x0) / h / _CACHE_STEP), round((y - y0) / h / _CACHE_STEP))
                             for x, y in s) for s in strokes))
    hit = _READ.get(key)
    if hit is None:
        sc = scores(strokes)
        i = int(np.argmin(sc))
        hit = (_bank().chars[i], float(sc[i]))
        if len(_READ) > 20000:
            _READ.clear()
        _READ[key] = hit
    return hit
