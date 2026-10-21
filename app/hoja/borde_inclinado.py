"""borde_inclinado.py — el área de una hoja cuyo borde no es recto con la hoja (pedido del usuario
2026-10-21, «Southwest Gas Combined 811 Records»: el mapa termina en una línea gruesa 0.56° inclinada
y el área rectangular dejaba una cuña de papel en blanco).

`cuadrilatero(page, rect)`: para cada lado del rectángulo (hoja VISIBLE, pt) busca una línea larga y
RECTA, algo inclinada respecto del lado (`GIRO_MIN_DEG`…`GIRO_MAX_DEG`), pegada a él (≤ `BANDA_FRAC`
del alto/ancho), que lo cubre casi entero y SIN NADA VISIBLE por fuera: la cuña entre la línea y el
lado se DIBUJA (`vacio`, a `ZOOM` px/pt) y no puede tener tinta (las cajas de los trazos del PDF
engañan: la de un trazo de varias partes o la del marco de la hoja cruzan la línea aunque su tinta
no). Ese lado pasa a ser la línea. Devuelve las 4 esquinas (sup-izq, sup-der, inf-der, inf-izq) o
None si el área sigue siendo el rectángulo. Lo que queda fuera es solo papel en blanco: el
reconocimiento ve la misma tinta. PURO: solo fitz (y numpy).
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple

import fitz

Rect = Tuple[float, float, float, float]
Pt = Tuple[float, float]

GIRO_MIN_DEG = 0.05        # menos: el lado ya es recto (eso lo hace «Sin línea de borde»)
GIRO_MAX_DEG = 10.0        # más: no es un borde del plano, es otra cosa
CUBRE_MIN = 0.7            # la línea cubre al menos esto del lado
BANDA_FRAC = 0.06          # y corre a ≤ esto del alto/ancho del área desde el lado…
BANDA_MIN_PT = 20.0        # …o a ≤ esto (pt)
MUEVE_MIN_PT = 1.0         # una esquina que se mueve menos: el área sigue siendo el rectángulo
HOLGURA_PT = 1.0           # además del medio grosor de la línea (su suavizado no es tinta de afuera)
MARGEN_PT = 0.5            # el lado va por FUERA de la línea: medio grosor + esto
SALE_MAX_PT = 5.0          # una esquina que cae más afuera del rectángulo: no es su marco
SOBRE_BORDE_PT = 1.0       # la línea puede empezar sobre el borde del recorte (unas décimas afuera)
ZOOM = 2.0                 # px/pt al dibujar la cuña
TINTA_MAX_PX = 6           # píxeles con tinta tolerados por fuera (polvo de suavizado)
OSCURO = 200               # un canal por debajo de esto = tinta


def _segmentos(paths, m) -> List[Tuple[float, float, float, float, float]]:
    """Rectas de los trazos (x0, y0, x1, y1, grosor) en la hoja visible; las seguidas y colineales
    de un mismo trazo, juntas (una línea de borde puede venir en varios tramos)."""
    out = []
    for p in paths:
        if p.get("type") not in ("s", "fs"):
            continue
        w = float(p.get("width") or 0.0)
        cad = None
        for it in p.get("items") or ():
            if it[0] in ("qu", "re"):           # marco cerrado en UN elemento: sus cuatro lados
                if cad:
                    out.append(cad)
                    cad = None
                q = it[1] if it[0] == "qu" else fitz.Rect(it[1]).quad
                vs = [q.ul * m, q.ur * m, q.lr * m, q.ll * m]
                out.extend((a.x, a.y, b.x, b.y, w) for a, b in zip(vs, vs[1:] + vs[:1]))
                continue
            if it[0] != "l":
                if cad:
                    out.append(cad)
                    cad = None
                continue
            a, b = it[1] * m, it[2] * m
            if cad is not None and abs(cad[2] - a.x) < 0.5 and abs(cad[3] - a.y) < 0.5:
                u = math.atan2(cad[3] - cad[1], cad[2] - cad[0])
                v = math.atan2(b.y - a.y, b.x - a.x)
                if abs((u - v + math.pi) % (2 * math.pi) - math.pi) < math.radians(0.3):
                    cad = (cad[0], cad[1], b.x, b.y, w)
                    continue
            if cad:
                out.append(cad)
            cad = (a.x, a.y, b.x, b.y, w)
        if cad:
            out.append(cad)
    return out


def franja(page: fitz.Page, lado: str, rect: Rect, banda: float):
    """Píxeles con tinta (u a lo largo del lado, v a través; pt de la hoja visible) de la franja
    del área pegada a ese lado, de ancho `banda` + 1 pt: se dibuja UNA vez por lado."""
    import numpy as np
    x0, y0, x1, y1 = rect
    horiz = lado in ("top", "bottom")
    borde = {"top": y0, "bottom": y1, "left": x0, "right": x1}[lado]
    afuera = 1.0 if lado in ("bottom", "right") else -1.0
    v_in = borde - afuera * (banda + SOBRE_BORDE_PT)
    lo_v, hi_v = min(v_in, borde), max(v_in, borde)
    caja = fitz.Rect(x0, lo_v, x1, hi_v) if horiz else fitz.Rect(lo_v, y0, hi_v, y1)
    vacio_ = (np.zeros(0), np.zeros(0))
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=caja * page.derotation_matrix,
                              alpha=False)
    except Exception:
        return None
    if pix.width == 0 or pix.height == 0:
        return vacio_
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    ys, xs = np.nonzero(img[:, :, :3].min(axis=2) < OSCURO)
    px = caja.x0 + (xs + 0.5) / ZOOM                  # centro del píxel, hoja visible
    py = caja.y0 + (ys + 0.5) / ZOOM
    return (px, py) if horiz else (py, px)


def vacio(tinta, lado: str, p_lo: Pt, p_hi: Pt, holgura: float) -> bool:
    """¿Nada con tinta entre la línea (p_lo → p_hi, coords del lado) y el lado? `tinta` = la
    `franja` de ese lado (None si no se pudo dibujar: entonces no)."""
    if tinta is None:
        return False
    u, v = tinta
    if len(u) == 0:
        return True
    afuera = 1.0 if lado in ("bottom", "right") else -1.0
    (ua, va), (ub, vb) = p_lo, p_hi
    pend = (vb - va) / (ub - ua) if ub != ua else 0.0
    fuera = afuera * (v - (va + pend * (u - ua))) > holgura
    return int(fuera.sum()) <= TINTA_MAX_PX


def _linea_de_lado(lado: str, rect: Rect, segs, tinta_de: Callable,
                   giro_min: float = GIRO_MIN_DEG) -> Optional[Tuple[Pt, Pt]]:
    """La línea que hace de borde en ese lado (coords de la hoja), corrida hacia afuera medio grosor
    + `MARGEN_PT` (la línea del marco queda ENTERA dentro), o None."""
    x0, y0, x1, y1 = rect
    horiz = lado in ("top", "bottom")
    largo = (x1 - x0) if horiz else (y1 - y0)
    banda = max(BANDA_MIN_PT, BANDA_FRAC * ((y1 - y0) if horiz else (x1 - x0)))
    borde = {"top": y0, "bottom": y1, "left": x0, "right": x1}[lado]
    afuera = 1.0 if lado in ("bottom", "right") else -1.0       # hacia dónde queda «por fuera»
    lo, hi = (x0, x1) if horiz else (y0, y1)
    cands = []
    for ax, ay, bx, by, w in segs:
        # en coordenadas del lado: u a lo largo, v a través
        (ua, va), (ub, vb) = ((ax, ay), (bx, by)) if horiz else ((ay, ax), (by, bx))
        if ub < ua:
            ua, va, ub, vb = ub, vb, ua, va
        if ub - ua <= 0:
            continue
        giro = math.degrees(math.atan2(abs(vb - va), ub - ua))
        if not giro_min <= giro <= GIRO_MAX_DEG:
            continue
        if min(ub, hi) - max(ua, lo) < CUBRE_MIN * largo:
            continue
        pend = (vb - va) / (ub - ua)
        v_lo, v_hi = va + pend * (lo - ua), va + pend * (hi - ua)
        # dentro del área y pegada al lado, en todo el lado
        if not all(-SOBRE_BORDE_PT <= afuera * (borde - v) <= banda for v in (v_lo, v_hi)):
            continue
        dist = max(afuera * (borde - v_lo), afuera * (borde - v_hi))
        cands.append((dist, (lo, v_lo), (hi, v_hi), w))
    if not cands:
        return None
    tinta = tinta_de(lado, banda)
    for dist, p_lo, p_hi, w in sorted(cands, key=lambda c: c[0]):     # la más afuera primero
        if vacio(tinta, lado, p_lo, p_hi, w / 2.0 + HOLGURA_PT):
            d = afuera * (w / 2.0 + MARGEN_PT)
            (ua, va), (ub, vb) = (p_lo[0], p_lo[1] + d), (p_hi[0], p_hi[1] + d)
            return ((ua, va), (ub, vb)) if horiz else ((va, ua), (vb, ub))
    return None


def _cruce(p1: Pt, p2: Pt, q1: Pt, q2: Pt) -> Optional[Pt]:
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = q2[0] - q1[0], q2[1] - q1[1]
    den = d1x * d2y - d1y * d2x
    if abs(den) < 1e-12:
        return None
    t = ((q1[0] - p1[0]) * d2y - (q1[1] - p1[1]) * d2x) / den
    return p1[0] + t * d1x, p1[1] + t * d1y


def cuadrilatero(page: fitz.Page, rect: Rect, paths=None, segs=None) -> Optional[List[Pt]]:
    """Esquinas (sup-izq, sup-der, inf-der, inf-izq) del área con sus bordes inclinados, o None.
    `segs` = rectas ya leídas (x0, y0, x1, y1, grosor, …) en la hoja visible (la composición
    sugerida pasa las de los bordes de su ficha); si no, se leen de `paths` o de la hoja."""
    if segs is None:
        if paths is None:
            paths = page.get_drawings(extended=True)
        segs = _segmentos(paths, page.rotation_matrix)
    else:
        segs = [tuple(s[:5]) for s in segs]
    x0, y0, x1, y1 = rect
    segs = [s for s in segs
            if max(s[0], s[2]) >= x0 - 1 and min(s[0], s[2]) <= x1 + 1
            and max(s[1], s[3]) >= y0 - 1 and min(s[1], s[3]) <= y1 + 1]
    lineas = {"top": ((x0, y0), (x1, y0)), "right": ((x1, y0), (x1, y1)),
              "bottom": ((x0, y1), (x1, y1)), "left": ((x0, y0), (x0, y1))}
    franjas: dict = {}

    def tinta_de(lado, banda):
        if lado not in franjas:
            franjas[lado] = franja(page, lado, rect, banda)
        return franjas[lado]
    hallados = {}
    for lado in ("top", "right", "bottom", "left"):
        ln = _linea_de_lado(lado, rect, segs, tinta_de)
        if ln is not None:
            hallados[lado] = ln
    if not hallados:
        return None                       # ningún borde inclinado: el rectángulo de siempre
    # con un borde inclinado, los demás lados del MISMO marco aunque vayan paralelos al lado
    for lado in ("top", "right", "bottom", "left"):
        if lado not in hallados:
            ln = _linea_de_lado(lado, rect, segs, tinta_de, giro_min=0.0)
            if ln is not None:
                hallados[lado] = ln
    lineas.update(hallados)
    pts = []
    for a, b in (("left", "top"), ("top", "right"), ("right", "bottom"), ("bottom", "left")):
        p = _cruce(*lineas[a], *lineas[b])
        if p is None:
            return None
        pts.append(p)
    esquinas = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    if all(math.hypot(p[0] - c[0], p[1] - c[1]) < MUEVE_MIN_PT for p, c in zip(pts, esquinas)):
        return None
    # cada esquina a ≤ SALE_MAX_PT del rectángulo. Lo poco que se sale por correr la línea medio
    # grosor hacia afuera se DEJA: llevarla al borde cortaba la propia línea del marco en la esquina,
    # y afuera del recorte del PDF no se ve nada (el de la vista sigue recortando)
    t = SALE_MAX_PT
    if not all(x0 - t <= p[0] <= x1 + t and y0 - t <= p[1] <= y1 + t for p in pts):
        return None
    return pts


def normalizado(pts: Sequence[Pt], tam: Tuple[float, float]) -> List[List[float]]:
    W, H = tam
    return [[p[0] / W, p[1] / H] for p in pts]
