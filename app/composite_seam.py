"""composite_seam.py — Costura EXACTA entre dos piezas de hojas contiguas.

Dos hojas contiguas de un plano dibujan la misma match line, y alrededor de
ella casi siempre comparten un trozo de dibujo (cada viewport pasa unos pt de la
línea): esos vectores son IDÉNTICOS en las dos hojas (mismo largo, rumbo y capa)
salvo una traslación. Con eso la costura queda fija sin adivinar:

  - **a través** de la costura: las dos match lines (la raya GRUESA, ajustada
    como recta porque suele ir algo inclinada: DU06 0.23°) tienen que coincidir.
    Si el recorte de una hoja quedó unos pt antes o después de la línea, la
    pieza se corre lo que haga falta (queda un hueco o se tapa), pero el dibujo
    no se «escalona». Una cota fina paralela (0.72 pt, a 20 pt de la match line)
    no cuenta: gana la más gruesa.
  - **a lo largo**: votan los pares de segmentos idénticos cuya traslación
    respeta el paso anterior (±`REG_ACROSS_TOL_PT`). Sin esa restricción ganaban
    picos falsos: las cotas de papel, que cada hoja dibuja en espejo, y símbolos
    repetidos (parquímetros) — medido en los 15 pares del DU06.
  - si las hojas no comparten ningún vector (el viewport termina justo en la
    línea), a lo largo manda la CONTINUIDAD: cada línea que llega a la match
    line sigue con el mismo rumbo al otro lado (`rule_crossings`).

Sin evidencia suficiente devuelve None y el compositor usa el imán de siempre.
PURO: solo lee trazos con fitz (vía la caché de `composite.page_drawings`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import fitz

import composite as C

SEAM_RULE_SEARCH_PT = 30.0    # la match line puede quedar hasta esto a cada lado del borde del recorte…
SEAM_RULE_FAR_PT = 90.0       # …o hasta esto si va a guiones (cotas a 60 pt, marco de la hoja a ~70)
SEAM_RULE_MIN_FRAC = 0.3      # …y tiene que cubrir al menos esta fracción del lado
SEAM_RULE_ANGLE_DEG = 1.0     # desvío máximo de un guión respecto del lado
SEAM_RULE_MIN_WIDTH = 1.2     # una match line es GRUESA (1.98 pt en DU06/08/10); las cotas de 0.72 no
SEAM_RULE_WIDTH_TOL = 0.1     # las dos match lines de una costura tienen el mismo grosor
SEAM_RULE_MAX_SHIFT_PT = 200.0  # corrección máxima a través de la costura (2 × SEAM_RULE_FAR_PT + margen)
REG_BAND_PT = 45.0            # franja a cada lado de la costura donde se buscan vectores comunes
REG_ACROSS_TOL_PT = 1.5       # un par idéntico solo vota si su traslación respeta las match lines
REG_MIN_VOTES = 5             # pares de acuerdo para fijar la costura a lo largo
REG_DOMINANCE = 1.5           # …y el pico tiene que superar así al segundo
REG_MAX_BUCKET = 80           # un segmento con más gemelos que esto (guiones de linetype) no vota
REG_SAME_PT = 0.05            # los dos extremos de un par idéntico coinciden ±esto

Line = Tuple[float, float, float, float, float, str]      # x0, y0, x1, y1, ancho, capa (hoja visible)


def page_lines(page: fitz.Page) -> List[Line]:
    """Segmentos rectos de la hoja VISIBLE con grosor y capa; caché en el documento
    con la misma clave que `composite.page_drawings`."""
    doc = page.parent
    drawings = C.page_drawings(page)
    cache = getattr(doc, "_pdfcad_lines", None)
    if cache is None:
        cache = {}
        try:
            doc._pdfcad_lines = cache
        except Exception:
            cache = None
    key = (page.number, page.rotation, id(drawings))
    if cache is not None and key in cache:
        return cache[key]
    rot = page.rotation_matrix
    ox, oy = page.rect.x0, page.rect.y0
    ra, rb, rc, rd, re_, rf = rot.a, rot.b, rot.c, rot.d, rot.e, rot.f
    out: List[Line] = []
    for path in drawings:
        if path.get("type") == "f":
            continue
        width = float(path.get("width") or 0.0)
        layer = path.get("layer") or ""
        for it in path.get("items") or ():
            if it[0] != "l":
                continue
            ax, ay, bx, by = it[1].x, it[1].y, it[2].x, it[2].y
            out.append((ax * ra + ay * rc + re_ - ox, ax * rb + ay * rd + rf - oy,
                        bx * ra + by * rc + re_ - ox, bx * rb + by * rd + rf - oy, width, layer))
    if cache is not None:
        cache[key] = out
    return out


# ─────────────────────────── match line ───────────────────────────
@dataclass
class SeamRule:
    """Match line de un lado: coord = a + b·s (s = coordenada A LO LARGO del lado,
    coord = la otra; pt de la hoja visible)."""
    a: float
    b: float
    width: float
    cover: float

    def at(self, s: float) -> float:
        return self.a + self.b * s


def _vertical(side: str) -> bool:
    return side in ("left", "right")


def seam_rule(lines: Sequence[Line], rect: Tuple[float, float, float, float], side: str,
              search: float = SEAM_RULE_SEARCH_PT, min_frac: float = SEAM_RULE_MIN_FRAC
              ) -> Optional[SeamRule]:
    """La match line que corre junto a ese lado del recorte (`rect` en pt de la
    hoja visible): la línea MÁS GRUESA (≥ SEAM_RULE_MIN_WIDTH), casi paralela al
    lado (±1°), fuera de las capas de utilidad, a ≤ `search` del borde (por
    dentro o por fuera) —o a ≤ SEAM_RULE_FAR_PT si va a guiones— que cubre ≥
    `min_frac` del lado. A igual grosor, la más cercana al borde. None si no hay."""
    x0, y0, x1, y1 = rect
    vert = _vertical(side)
    edge = {"left": x0, "right": x1, "top": y0, "bottom": y1}[side]
    s_lo, s_hi = (y0, y1) if vert else (x0, x1)
    if s_hi - s_lo <= 0:
        return None
    tan = math.tan(math.radians(SEAM_RULE_ANGLE_DEG))
    reach = max(search, SEAM_RULE_FAR_PT)
    util: Dict[str, bool] = {}
    by_w: Dict[int, List[Tuple[float, float, float, float]]] = {}
    for ax, ay, bx, by, w, layer in lines:
        if w < SEAM_RULE_MIN_WIDTH:
            continue
        if vert:
            dc, ds = abs(ax - bx), abs(ay - by)
            c, lo, hi = (ax + bx) / 2.0, min(ay, by), max(ay, by)
        else:
            dc, ds = abs(ay - by), abs(ax - bx)
            c, lo, hi = (ay + by) / 2.0, min(ax, bx), max(ax, bx)
        if ds < 2.0 or dc > tan * ds + 0.3 or abs(c - edge) > reach:
            continue
        lo, hi = max(lo, s_lo), min(hi, s_hi)
        if hi <= lo:
            continue
        if layer not in util:
            util[layer] = C.is_utility_layer(layer)
        if util[layer]:
            continue
        by_w.setdefault(round(w * 10), []).append((c, lo, hi, w))
    best: Optional[Tuple[float, float, List[Tuple[float, float, float, float]], float]] = None
    for segs in by_w.values():
        segs.sort()
        groups = [[segs[0]]]
        for sg in segs[1:]:
            if sg[0] - groups[-1][-1][0] <= C.LINE_CLUSTER_PT:
                groups[-1].append(sg)
            else:
                groups.append([sg])
        for g in groups:
            spans = sorted((lo, hi) for _, lo, hi, _ in g)
            cover, cur_lo, cur_hi, pieces = 0.0, spans[0][0], spans[0][1], 1
            for lo, hi in spans[1:]:
                if lo <= cur_hi:
                    cur_hi = max(cur_hi, hi)
                else:
                    cover += cur_hi - cur_lo; cur_lo, cur_hi = lo, hi
                    pieces += 1
            cover += cur_hi - cur_lo
            if cover < min_frac * (s_hi - s_lo):
                continue
            dist = abs(sum(t[0] for t in g) / len(g) - edge)
            dashed = pieces >= 3 and cover <= 0.9 * (max(h for _, h in spans) - spans[0][0])
            if dist > search and not dashed:
                continue
            w = max(t[3] for t in g)
            if best is None or (round(w, 1), -dist) > (round(best[0], 1), -best[3]):
                best = (w, cover, g, dist)
    if best is None:
        return None                       # sin raya gruesa: una cota fina en espejo engaña
    w, cover, g, _ = best
    # recta coord = a + b·s por mínimos cuadrados (peso = largo del guión)
    sw = sum(hi - lo for _, lo, hi, _ in g)
    sm = sum((hi - lo) * (lo + hi) / 2.0 for _, lo, hi, _ in g) / sw
    cm = sum((hi - lo) * c for c, lo, hi, _ in g) / sw
    sxx = sum((hi - lo) * ((lo + hi) / 2.0 - sm) ** 2 for _, lo, hi, _ in g)
    sxy = sum((hi - lo) * ((lo + hi) / 2.0 - sm) * (c - cm) for c, lo, hi, _ in g)
    b = sxy / sxx if sxx > 1e-6 else 0.0
    if abs(b) > tan:                                       # columnas sueltas, no una recta
        b = 0.0
    return SeamRule(cm - b * sm, b, w, cover)


def rules_match(ra: Optional[SeamRule], rb: Optional[SeamRule]) -> bool:
    """Las dos match lines de una costura: mismo grosor e inclinación."""
    return (ra is not None and rb is not None and abs(ra.width - rb.width) <= SEAM_RULE_WIDTH_TOL
            and abs(ra.b - rb.b) <= math.tan(math.radians(0.3)))


def rule_across(rule_o: SeamRule, rule_m: SeamRule, s_mid: float, along: float) -> float:
    """Traslación A TRAVÉS de la costura (hoja m = hoja o + t) que hace coincidir
    las dos match lines, evaluada en `s_mid` (a lo largo, hoja o) con el
    desplazamiento a lo largo `along` ya estimado (importa por la inclinación)."""
    return rule_m.at(s_mid + along) - rule_o.at(s_mid)


# ─────────────────────────── vectores comunes ───────────────────────────
Seg = Tuple[str, int, int, float, float, float, float]     # capa, largo·5, rumbo·5, x0, y0, x1, y1


def band_segments(lines: Sequence[Line], rect: Tuple[float, float, float, float], side: str,
                  band: float = REG_BAND_PT, rule: Optional[SeamRule] = None) -> List[Seg]:
    """Segmentos enteros a ≤ `band` del lado (por dentro o por fuera) y dentro de
    la extensión del lado (± band), listos para `seam_votes`. Con `rule` la franja
    va centrada en la match line y no en el corte: el dibujo que comparten las
    dos hojas está junto a la línea aunque el área se haya recortado lejos."""
    x0, y0, x1, y1 = rect
    vert = _vertical(side)
    edge = {"left": x0, "right": x1, "top": y0, "bottom": y1}[side]
    if rule is not None:
        edge = rule.at((y0 + y1) / 2.0 if vert else (x0 + x1) / 2.0)
    s_lo, s_hi = ((y0, y1) if vert else (x0, x1))
    s_lo -= band; s_hi += band
    out: List[Seg] = []
    for ax, ay, bx, by, _w, layer in lines:
        ca, cb, sa, sb = (ax, bx, ay, by) if vert else (ay, by, ax, bx)
        if abs(ca - edge) > band or abs(cb - edge) > band:
            continue
        if not (s_lo <= sa <= s_hi and s_lo <= sb <= s_hi):
            continue
        L = math.hypot(bx - ax, by - ay)
        if L < 2.0:
            continue
        if (ax, ay) > (bx, by):
            ax, ay, bx, by = bx, by, ax, ay
        ang = math.degrees(math.atan2(by - ay, bx - ax)) % 180.0
        out.append((layer, round(L * 5), round(ang * 5), ax, ay, bx, by))
    return out


Vote = Tuple[float, float, str, int, int]                  # tx, ty, capa, segmento en o, segmento en m


def seam_votes(segs_o: Sequence[Seg], segs_m: Sequence[Seg]) -> List[Vote]:
    """Traslaciones (tx, ty, capa, i_o, i_m) de cada par de segmentos IDÉNTICOS
    (hoja m = hoja o + t). Los segmentos con demasiados gemelos (guiones de un
    linetype) no votan: solo meten ruido periódico."""
    buckets: Dict[Tuple[str, int, int], List[Tuple[int, Seg]]] = {}
    for j, s in enumerate(segs_m):
        buckets.setdefault((s[0], s[1], s[2]), []).append((j, s))
    out: List[Vote] = []
    for i, s in enumerate(segs_o):
        cand = buckets.get((s[0], s[1], s[2]))
        if not cand or len(cand) > REG_MAX_BUCKET:
            continue
        for j, t in cand:
            tx, ty = t[3] - s[3], t[4] - s[4]
            if abs(t[5] - s[5] - tx) <= REG_SAME_PT and abs(t[6] - s[6] - ty) <= REG_SAME_PT:
                out.append((tx, ty, s[0], i, j))
    return out


def translation_from_votes(votes: Sequence[Vote], axis: int, across: float,
                           along_center: float, window: float) -> Optional[Tuple[float, float]]:
    """(a lo largo, a través) que proponen los pares idénticos cuya traslación a
    través coincide con la de las match lines `across` (±REG_ACROSS_TOL_PT) y
    que caen a ≤ `window` de `along_center` (`axis`: 1 = y en una costura
    vertical). El «a través» devuelto es el de los vectores: las dos match lines
    pueden estar dibujadas algunas décimas corridas (DU06 11→12: 0.4 pt) y el
    dibujo manda. None si el pico no tiene ≥ REG_MIN_VOTES de ≥2 capas (o el doble
    en una hoja sin capas) o no domina.

    Un segmento con VARIOS gemelos a tiro (algo que se repite a lo largo de la
    costura: LABOE h.9–10 repite cada 108 pt) reparte su voto entre ellos; lo
    único del dibujo vale 1. Sin eso los picos periódicos empataban al real."""
    other = 1 - axis
    sel = [v for v in votes
           if abs(v[other] - across) <= REG_ACROSS_TOL_PT and abs(v[axis] - along_center) <= window]
    if len(sel) < REG_MIN_VOTES:
        return None
    n_o: Dict[int, int] = {}
    n_m: Dict[int, int] = {}
    for v in sel:
        if len(v) > 4:
            n_o[v[3]] = n_o.get(v[3], 0) + 1
            n_m[v[4]] = n_m.get(v[4], 0) + 1
    vals = [(v[axis], v[2], v[other],
             1.0 / max(n_o[v[3]], n_m[v[4]]) if len(v) > 4 else 1.0) for v in sel]
    bins: Dict[int, float] = {}
    for a, _, _, w in vals:
        k = round(a * 2.0)
        bins[k] = bins.get(k, 0.0) + w

    def near(k: int) -> float:
        return bins.get(k - 1, 0.0) + bins.get(k, 0.0) + bins.get(k + 1, 0.0)
    peak = max(bins, key=lambda k: (near(k), bins[k]))
    top = near(peak)
    second = max((near(k) for k in bins if abs(k - peak) > 4), default=0.0)
    group = [(a, lay, c) for a, lay, c, _ in vals if abs(a * 2.0 - peak) <= 1.5]
    if top < REG_MIN_VOTES or top < REG_DOMINANCE * second:
        return None
    layers = {lay for _, lay, _ in group}
    # Un símbolo repetido da votos de UNA capa: se piden ≥2. En una hoja
    # «aplanada» (sin capas, DU08) no hay cómo distinguirlas: se pide el doble.
    if len(layers) < 2 and not (layers == {""} and top >= 2 * REG_MIN_VOTES):
        return None
    xs = sorted(a for a, _, _ in group)
    cs = sorted(c for _, _, c in group)
    return xs[len(xs) // 2], cs[len(cs) // 2]


# ─────────────────────── continuidad de las líneas ───────────────────────
CROSS_REACH_PT = 12.0          # un trazo que muere a ≤ esto de la match line la cruza (hueco del linetype)
CROSS_MIN_ANGLE_DEG = 20.0     # casi paralelo a la costura no dice nada a lo largo
CROSS_SAME_DEG = 0.3           # la misma línea sigue con el mismo rumbo al otro lado

Cross = Tuple[str, float, float]                            # capa, rumbo (0–180°), cruce a lo largo


def rule_crossings(lines: Sequence[Line], rect: Tuple[float, float, float, float], side: str,
                   rule: SeamRule, reach: float = CROSS_REACH_PT) -> List[Cross]:
    """Dónde cruza la match line cada línea que llega a ella por dentro de la
    pieza (prolongada: el último guión puede quedar a un hueco de la línea) o la
    atraviesa (el viewport suele seguir unos pt más allá)."""
    x0, y0, x1, y1 = rect
    vert = _vertical(side)
    inner = -1.0 if side in ("right", "bottom") else 1.0
    s_lo, s_hi = ((y0, y1) if vert else (x0, x1))
    out: List[Cross] = []
    for ax, ay, bx, by, _w, layer in lines:
        # (c, s): c = coord a través, s = a lo largo
        ca, sa, cb, sb = (ax, ay, bx, by) if vert else (ay, ax, by, bx)
        if not (s_lo - reach <= sa <= s_hi + reach):
            continue
        da, db = (ca - rule.at(sa)) * inner, (cb - rule.at(sb)) * inner
        if max(da, db) < 0.5 or min(da, db) > reach:
            continue            # no está por dentro, o no llega a la línea (sí si la cruza)
        dc, ds = cb - ca, sb - sa
        L = math.hypot(dc, ds)
        if L < 3.0:
            continue
        ang_seam = math.degrees(math.atan2(abs(dc), abs(ds)))   # 0 = paralelo a la costura
        if ang_seam < CROSS_MIN_ANGLE_DEG:
            continue
        den = dc - rule.b * ds
        if abs(den) < 1e-9:
            continue
        u = (rule.a + rule.b * sa - ca) / den
        s_cross = sa + ds * u
        heading = math.degrees(math.atan2(by - ay, bx - ax)) % 180.0
        out.append((layer, heading, s_cross))
    return out


def crossing_votes(cr_o: Sequence[Cross], cr_m: Sequence[Cross]) -> List[Vote]:
    """(Δ a lo largo, 0, capa, i_o, i_m) por cada pareja de cruces de la misma
    capa y rumbo a un lado y otro de la costura."""
    by: Dict[str, List[Tuple[int, Cross]]] = {}
    for j, c in enumerate(cr_m):
        by.setdefault(c[0], []).append((j, c))
    out: List[Vote] = []
    for i, c in enumerate(cr_o):
        for j, d in by.get(c[0], ()):
            dh = abs(c[1] - d[1]); dh = min(dh, 180.0 - dh)
            if dh <= CROSS_SAME_DEG:
                out.append((d[2] - c[2], 0.0, c[0], i, j))
    return out


def along_from_crossings(votes: Sequence[Vote], along_center: float, window: float) -> Optional[float]:
    """Desplazamiento a lo largo por CONTINUIDAD de las líneas que cruzan (sin
    vectores compartidos: LABOE h.8→9). Mismo criterio que los vectores."""
    found = translation_from_votes(votes, 0, 0.0, along_center, window)
    return None if found is None else found[0]


# ─────────────────────────── hoja compuesta ───────────────────────────
def pos_for_translation(p_o: C.Piece, size_o, p_m: C.Piece, size_m, target: float,
                        t: Tuple[float, float]) -> C.Pt:
    """Posición (x, y) de la pieza m en la hoja compuesta que deja el punto P de
    la hoja de o sobre el punto P + t de la hoja de m."""
    x0, y0, x1, y1 = C.clip_rect_pt(size_o, p_o.clip)
    P = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    qo = C.piece_map(p_o, size_o, target)(*P)
    qm = C.piece_map(p_m, size_m, target)(P[0] + t[0], P[1] + t[1])
    return p_m.x + qo[0] - qm[0], p_m.y + qo[1] - qm[1]


def current_translation(p_o: C.Piece, size_o, p_m: C.Piece, size_m, target: float) -> C.Pt:
    """Traslación t (hoja m = hoja o + t) que implica la posición actual de m."""
    x0, y0, x1, y1 = C.clip_rect_pt(size_o, p_o.clip)
    P = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    q = C.piece_map(p_o, size_o, target)(*P)
    pm = C.piece_unmap(p_m, size_m, target)(*q)
    return pm[0] - P[0], pm[1] - P[1]


def comparable(p_o: C.Piece, p_m: C.Piece, target: float) -> bool:
    """El registro por traslación solo vale sin giro y con el mismo factor."""
    return ((p_o.rotation % 360.0) == 0.0 and (p_m.rotation % 360.0) == 0.0
            and abs(C.piece_factor(p_o, target) - C.piece_factor(p_m, target)) <= 1e-9)
