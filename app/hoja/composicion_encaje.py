"""composicion_encaje.py — confirmar con el DIBUJO que dos hojas se unen, y cómo.

El texto del plano propone las parejas (`composicion_ficha`); aquí se mide la unión
exacta y se descarta lo que el dibujo no confirma (pedido del usuario 2026-10-14:
«si no estamos seguros, no sugerirlo»):

  · Plano CAD (`costura_cad`): las dos match lines coinciden A TRAVÉS de la costura y
    los vectores idénticos que ambas hojas comparten junto a ella fijan el
    desplazamiento A LO LARGO; sin dibujo compartido, la continuidad de las líneas que
    cruzan. Es la misma costura exacta del compositor (`composite_seam`), sin la
    pieza soltada a mano: la pista a lo largo sale de los rótulos.
  · Mapa por cuadrícula (`encaje_mapa`): las hojas vecinas se SOLAPAN (55–80 pt en
    Phoenix) y dibujan idénticos los trazos de esa franja; votan la traslación (y la
    escala, si los PDF se imprimieron a tamaños distintos: Norte/Sur 0.5294). Se exige
    un pico claro, coincidencias en ≥2 direcciones (las líneas a trazos repetidas dan
    picos falsos A LO LARGO de sí mismas) y que la vecina quede del lado que dice el
    mapa índice.

Convención: B = escala·A + t, en pt de la hoja VISIBLE de cada una. PURO (numpy).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from hoja import composite_seam as S
from hoja.composicion_ficha import Ficha, Linea, Rect, Rotulo

OPUESTO = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}

# A lo largo, ventanas crecientes alrededor de la pista de los rótulos: con una ventana
# amplia cada voto se reparte entre todos sus gemelos posibles (líneas sin capa de
# LABOE: 51×61 cruces) y el pico real pierde peso; el compositor interactivo usa 90.
CAD_VENTANAS_PT = (30.0, 60.0, 90.0, 150.0, 300.0, 600.0)
CAD_PICO_DOMINIO = 1.5        # el hallazgo tiene que ser también el pico GLOBAL de votos crudos
CAD_RECORTE_VECINO_PT = 1.5   # los votos del pico (para contar cuántos lo apoyan)
REGLA_MIN_FRAC_VISTA = 0.15   # 2.º intento: la match line cubre al menos esto del lado de la vista

MAPA_FRANJA = 0.3             # franja de cada borde donde se buscan los trazos comunes
MAPA_MIN_LARGO = 4.0
MAPA_BIN_PT = 2.0
MAPA_TOL_PT = 0.4             # los dos extremos de un par idéntico coinciden ±esto
MAPA_MIN_VOTOS = 12
MAPA_DOMINIO = 2.0            # el pico supera así al segundo (fuera de sus vecinos)
MAPA_RMS_MAX = 0.5
MAPA_MIN_DIRECCIONES = 2      # coincidencias en ≥2 rumbos separados ≥ 30°
MAPA_GUIA_VENTANA_PT = 40.0
MAPA_GUIA_DOMINIO = 1.5       # guiada: el pico dentro de la ventana también tiene que destacar…
MAPA_GUIA_RMS_MAX = 0.3       # …y ajustar mejor (en SD las líneas a guiones dan picos vecinos)


@dataclass
class Costura:
    """Unión confirmada de la hoja `a` con la `b` por el lado `lado` de `a`."""
    a: Tuple[int, int]
    b: Tuple[int, int]
    lado: str
    escala: float
    t: Tuple[float, float]
    metodo: str                 # vectores | continuidad | solape | guiada
    votos: float
    segundo: float = 0.0
    rms: float = 0.0
    corte_a: Optional[float] = None   # coordenada del corte (match line) en la hoja a
    corte_b: Optional[float] = None   # …y en la hoja b

    def mapa(self, x: float, y: float) -> Tuple[float, float]:
        return self.escala * x + self.t[0], self.escala * y + self.t[1]


# ─────────────────────────── plano CAD ───────────────────────────
def _l6(f: Ficha) -> List[S.Line]:
    return [l[:6] for l in f.lineas]


def _a_lo_largo(r: Rotulo, lado: str) -> float:
    return r.y if lado in ("left", "right") else r.x


def regla(f: Ficha, lado: str, lineas6=None) -> Optional[S.SeamRule]:
    """Match line junto a ese lado de la vista (la más gruesa, ajustada como recta).
    La vista entera puede ser bastante más alta que la match line (DU10: raya a
    guiones de ~300 pt en un lado de 1060): si no cubre el 30 % se acepta con el 15 %."""
    if f.vista is None:
        return None
    l6 = lineas6 if lineas6 is not None else _l6(f)
    r = S.seam_rule(l6, f.vista, lado)
    if r is None:
        r = S.seam_rule(l6, f.vista, lado, min_frac=REGLA_MIN_FRAC_VISTA)
    return r


def _votos_en(votes: Sequence[S.Vote], axis: int, along: float, across: float) -> int:
    o = 1 - axis
    return sum(1 for v in votes if abs(v[axis] - along) <= CAD_RECORTE_VECINO_PT
               and abs(v[o] - across) <= CAD_RECORTE_VECINO_PT)


def _pico_global(votes: Sequence[S.Vote], axis: int, along: float, across: Optional[float]) -> bool:
    """¿`along` es el pico de TODOS los votos del lado (sin ventana ni pesos)? Así una
    ventana chica alrededor de la pista no toma un pico local falso."""
    o = 1 - axis
    bins: Counter = Counter()
    for v in votes:
        if across is not None and abs(v[o] - across) > S.REG_ACROSS_TOL_PT:
            continue
        bins[round(v[axis])] += 1
    if not bins:
        return False
    k0 = round(along)
    aqui = bins[k0 - 1] + bins[k0] + bins[k0 + 1]
    otro = max((bins[k - 1] + bins[k] + bins[k + 1] for k in bins if abs(k - k0) > 3), default=0)
    return aqui >= CAD_PICO_DOMINIO * otro


def costura_cad(fa: Ficha, fb: Ficha, lado: str, ra: Optional[Rotulo] = None,
                rb: Optional[Rotulo] = None) -> Optional[Costura]:
    """Unión exacta de dos hojas de un plano CAD por la match line del `lado` de A
    (y el opuesto de B). None si las match lines no coinciden o ni los vectores
    comunes ni la continuidad de las líneas la confirman."""
    if fa.vista is None or fb.vista is None:
        return None
    lb = OPUESTO[lado]
    la6, lb6 = _l6(fa), _l6(fb)
    rule_a, rule_b = regla(fa, lado, la6), regla(fb, lb, lb6)
    if not S.rules_match(rule_a, rule_b):
        return None
    axis = 1 if lado in ("left", "right") else 0
    x0, y0, x1, y1 = fa.vista
    s_mid = (y0 + y1) / 2.0 if axis == 1 else (x0 + x1) / 2.0
    pista = (_a_lo_largo(rb, lb) - _a_lo_largo(ra, lado)) if (ra is not None and rb is not None) else 0.0
    votes = S.seam_votes(S.band_segments(la6, fa.vista, lado, rule=rule_a),
                         S.band_segments(lb6, fb.vista, lb, rule=rule_b))
    metodo = "vectores"
    found = None
    across0 = S.rule_across(rule_a, rule_b, s_mid, pista)
    for ventana in CAD_VENTANAS_PT:
        f = S.translation_from_votes(votes, axis, across0, pista, ventana)
        if f is not None and _pico_global(votes, axis, f[0], across0):
            found = f
            break
    n = 0
    if found is not None:
        n = _votos_en(votes, axis, found[0], found[1])
    else:
        cross = S.crossing_votes(S.rule_crossings(la6, fa.vista, lado, rule_a),
                                 S.rule_crossings(lb6, fb.vista, lb, rule_b))
        along = None
        for ventana in CAD_VENTANAS_PT:
            a = S.along_from_crossings(cross, pista, ventana)
            if a is not None and _pico_global(cross, 0, a, None):
                along = a
                break
        if along is None:
            return None
        found = (along, S.rule_across(rule_a, rule_b, s_mid, along))
        n = sum(1 for v in cross if abs(v[0] - along) <= CAD_RECORTE_VECINO_PT)
        metodo = "continuidad"
    along, across = found
    t = (across, along) if axis == 1 else (along, across)
    sb_mid = s_mid + along
    return Costura(fa.clave, fb.clave, lado, 1.0, t, metodo, float(n),
                   corte_a=rule_a.at(s_mid), corte_b=rule_b.at(sb_mid))


# ─────────────────────────── mapas (solape) ───────────────────────────
Seg = Tuple[Tuple[float, ...], float, float, float, float, float, float]   # color, largo, rumbo, x0, y0, x1, y1


def caja(f: Ficha) -> Optional[Rect]:
    """Vista del mapa; sin marco (SD), la caja de sus trazos (ya sin plantilla)."""
    if f.vista is not None:
        return f.vista
    if not f.lineas:
        return None
    xs = [v for l in f.lineas for v in (l[0], l[2])]
    ys = [v for l in f.lineas for v in (l[1], l[3])]
    return min(xs), min(ys), max(xs), max(ys)


def segmentos(lineas: Sequence[Linea], rect: Optional[Rect], lado: str, frac: float = MAPA_FRANJA) -> List[Seg]:
    """Trazos de la franja `lado` del recuadro, normalizados (extremo menor primero)."""
    out: List[Seg] = []
    if rect is None:
        return out
    x0, y0, x1, y1 = rect
    w, h = (x1 - x0) * frac, (y1 - y0) * frac
    for ax, ay, bx, by, _w, _capa, col in lineas:
        if lado == "right" and min(ax, bx) < x1 - w:
            continue
        if lado == "left" and max(ax, bx) > x0 + w:
            continue
        if lado == "bottom" and min(ay, by) < y1 - h:
            continue
        if lado == "top" and max(ay, by) > y0 + h:
            continue
        L = math.hypot(bx - ax, by - ay)
        if L < MAPA_MIN_LARGO:
            continue
        if (ax, ay) > (bx, by):
            ax, ay, bx, by = bx, by, ax, ay
        out.append((col, L, math.degrees(math.atan2(by - ay, bx - ax)) % 180.0, ax, ay, bx, by))
    return out


def plantilla(fichas: Sequence[Ficha], frac: float = 0.5) -> set:
    """Trazos en la MISMA posición en ≥ frac de las hojas de un PDF: marco, cajetín,
    leyenda. No dicen nada de la unión (votarían «sin desplazamiento»)."""
    c: Counter = Counter()
    for f in fichas:
        c.update({(l[6], round(l[0]), round(l[1]), round(l[2]), round(l[3])) for l in f.lineas})
    n = len(fichas)
    return {k for k, v in c.items() if v >= max(2, frac * n)}


def sin_plantilla(f: Ficha, tpl: set) -> None:
    if tpl:
        f.lineas = [l for l in f.lineas if (l[6], round(l[0]), round(l[1]), round(l[2]), round(l[3])) not in tpl]


def escalas(A: Sequence[Seg], B: Sequence[Seg], n: int = 3) -> List[float]:
    """Escalas candidatas B/A: cociente de largos de trazos con el mismo rumbo."""
    ba: Dict[int, List[float]] = defaultdict(list)
    bb: Dict[int, List[float]] = defaultdict(list)
    for s in A:
        if s[1] >= 15:
            ba[round(s[2] * 20)].append(s[1])
    for s in B:
        if s[1] >= 15:
            bb[round(s[2] * 20)].append(s[1])
    v: Counter = Counter()
    for k, la in ba.items():
        lb = bb.get(k)
        if not lb or len(la) * len(lb) > 40000:
            continue
        r = np.round(np.log(np.array(lb)[None, :] / np.array(la)[:, None]) * 400).astype(int).ravel()
        v.update(r.tolist())
    return [math.exp(k / 400.0) for k, _ in v.most_common(n)]


def _direcciones(angs: Sequence[float]) -> int:
    """Cuántos rumbos distintos (≥30° entre sí, ≥3 pares cada uno) apoyan el pico."""
    c = Counter(int(a // 10) % 18 for a in angs)
    grupos: List[float] = []
    for k, n in c.most_common():
        if n < 3:
            break
        a = k * 10 + 5
        if all(min(abs(a - g), 180 - abs(a - g)) >= 30 for g in grupos):
            grupos.append(a)
    return len(grupos)


def _hacia(fa_rect: Rect, fb_rect: Rect, s: float, t: Tuple[float, float], lado: str) -> bool:
    """¿La vecina queda del lado esperado? (su centro, llevado a la hoja A)."""
    cx = ((fb_rect[0] + fb_rect[2]) / 2.0 - t[0]) / s
    cy = ((fb_rect[1] + fb_rect[3]) / 2.0 - t[1]) / s
    ax, ay = (fa_rect[0] + fa_rect[2]) / 2.0, (fa_rect[1] + fa_rect[3]) / 2.0
    w, h = fa_rect[2] - fa_rect[0], fa_rect[3] - fa_rect[1]
    dx, dy = cx - ax, cy - ay
    return {"right": dx > 0.5 * w and abs(dy) < 0.5 * h, "left": dx < -0.5 * w and abs(dy) < 0.5 * h,
            "bottom": dy > 0.5 * h and abs(dx) < 0.5 * w, "top": dy < -0.5 * h and abs(dx) < 0.5 * w}[lado]


def _votar(A: Sequence[Seg], B: Sequence[Seg], sc: float, guia=None):
    """Pares idénticos (color, largo·sc, rumbo) con sus dos extremos de acuerdo →
    traslaciones agrupadas cada MAPA_BIN_PT."""
    bk: Dict[int, List[Seg]] = defaultdict(list)
    for t in B:
        bk[round(t[2] * 10)].append(t)
    tv: Counter = Counter()
    ej: Dict[Tuple[int, int], list] = defaultdict(list)
    for s in A:
        for t in bk.get(round(s[2] * 10), ()):
            if t[0] != s[0] or abs(t[1] - s[1] * sc) > MAPA_TOL_PT + 0.01 * t[1]:
                continue
            dx = t[3] - s[3] * sc
            dy = t[4] - s[4] * sc
            if guia is not None and (abs(dx - guia[0]) > MAPA_GUIA_VENTANA_PT or abs(dy - guia[1]) > MAPA_GUIA_VENTANA_PT):
                continue
            if abs(t[5] - s[5] * sc - dx) > MAPA_TOL_PT or abs(t[6] - s[6] * sc - dy) > MAPA_TOL_PT:
                continue
            k = (round(dx / MAPA_BIN_PT), round(dy / MAPA_BIN_PT))
            tv[k] += 1
            ej[k].append((s, t))
    return tv, ej


def _ajuste(pares):
    """Escala + traslación por mínimos cuadrados sobre los extremos, sin los raros."""
    P = np.array([(s[3], s[4]) for s, _ in pares] + [(s[5], s[6]) for s, _ in pares])
    Q = np.array([(t[3], t[4]) for _, t in pares] + [(t[5], t[6]) for _, t in pares])
    keep = np.ones(len(P), bool)
    s2, t2, res = 1.0, np.zeros(2), np.zeros(len(P))
    for _ in range(4):
        p, q = P[keep], Q[keep]
        pm, qm = p.mean(0), q.mean(0)
        s2 = float(((p - pm) * (q - qm)).sum() / max(1e-9, ((p - pm) ** 2).sum()))
        t2 = qm - s2 * pm
        res = np.hypot(*(Q - (s2 * P + t2)).T)
        nuevo = res <= max(0.3, 3.0 * float(np.median(res[keep])))
        if (nuevo == keep).all():
            break
        keep = nuevo
    rms = float(np.sqrt((res[keep] ** 2).mean())) if keep.any() else math.inf
    return s2, (float(t2[0]), float(t2[1])), rms, int(keep.sum())


def encaje_mapa(fa: Ficha, fb: Ficha, lado: str, escala: Optional[float] = None,
                guia: Optional[Tuple[float, float]] = None) -> Optional[Costura]:
    """Unión de dos hojas de un mapa que se solapan, B al `lado` de A. `escala`
    None = mismo PDF (1.0) o buscarla; `guia` = traslación esperada (pares vecinos ya
    confirmados entre los mismos PDF): solo se aceptan votos a ≤40 pt de ella."""
    ra, rb = caja(fa), caja(fb)
    if ra is None or rb is None:
        return None
    A = segmentos(fa.lineas, ra, lado)
    B = segmentos(fb.lineas, rb, OPUESTO[lado])
    if len(A) < MAPA_MIN_VOTOS or len(B) < MAPA_MIN_VOTOS:
        return None
    if escala is not None:
        cands = [escala]
    elif fa.doc == fb.doc:
        cands = [1.0]
    else:
        cands = escalas(A, B)
    best = None
    for sc in cands:
        tv, ej = _votar(A, B, sc, guia)
        if not tv:
            continue
        top = tv.most_common(8)
        (k, n) = top[0]
        seg = next((m for kk, m in top[1:] if abs(kk[0] - k[0]) > 1 or abs(kk[1] - k[1]) > 1), 0)
        pares = [p for kk in ej for p in ej[kk] if abs(kk[0] - k[0]) <= 1 and abs(kk[1] - k[1]) <= 1]
        if best is None or n > best[0]:
            best = (n, seg, pares, sc)
    if best is None:
        return None
    n, seg, pares, sc = best
    s2, t, rms, m = _ajuste(pares)
    if guia is None:
        if n < MAPA_MIN_VOTOS or n < MAPA_DOMINIO * seg:
            return None
    elif n < MAPA_MIN_VOTOS // 2 or n < MAPA_GUIA_DOMINIO * seg or rms > MAPA_GUIA_RMS_MAX:
        return None
    if rms > MAPA_RMS_MAX or abs(s2 / sc - 1.0) > 0.002:
        return None
    if _direcciones([s[2] for s, _ in pares]) < MAPA_MIN_DIRECCIONES:
        return None
    if not _hacia(ra, rb, s2, t, lado):
        return None
    return Costura(fa.clave, fb.clave, lado, s2, t, "guiada" if guia is not None else "solape",
                   float(m), float(seg), rms)
