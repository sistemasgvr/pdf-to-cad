"""Recorte del plano para la IA que sugiere el diámetro (`ia/diametro_ia`; fitz, sin Qt).

La zona de los rótulos candidatos junto a la línea, a `LADO_PX` de lado mayor: la línea de ESTA utilidad en
MAGENTA (no es color de ninguna utilidad) y cada rótulo enmarcado en turquesa con su id («R1»…), los mismos ids
de la petición. Así el modelo no tiene que adivinar de qué línea y de qué rótulo se le habla (en la prueba con
qwen3.5 sin marcas, leía bien el texto pero se lo daba a la línea equivocada).
Coordenadas en pt de la VISTA de la hoja (px del editor ÷ zoom); la hoja girada se dibuja como se ve.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

import fitz

LADO_PX = 1024
MARGEN_PT = 30.0
ZONA_MIN_PT = 120.0
ZONA_MAX_PT = 260.0           # a 1024 px ≈ 4 px/pt: una letra de 6 pt mide ~24 px
MAGENTA = (1.0, 0.0, 1.0)
TURQUESA = (0.0, 0.55, 0.6)
LINEA_PX = 3.0


def _cercano(pts, q):
    """Punto de la polilínea más cercano a q."""
    best, bp = float("inf"), pts[0]
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        p = (a[0] + t * vx, a[1] + t * vy)
        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
        if d < best:
            best, bp = d, p
    return bp


def zona(pts: Sequence[Tuple[float, float]], cajas: Dict[str, tuple], margen_pt=MARGEN_PT,
         puntos: Sequence[Tuple[float, float]] = ()) -> fitz.Rect:
    """Rótulos + las puntas de sus guías (`puntos`) + el punto de la línea más cercano a cada uno (o la línea
    entera sin rótulos), con margen."""
    limites = list(puntos)
    if cajas:
        for c in cajas.values():
            cr = fitz.Rect(c)
            limites += [(cr.x0, cr.y0), (cr.x1, cr.y1)]
            p = _cercano(pts, ((cr.x0 + cr.x1) / 2.0, (cr.y0 + cr.y1) / 2.0))
            limites.append(p)
    else:
        limites += list(pts)
    if not limites:
        raise ValueError("La línea no tiene puntos")
    # Rect() incluye el origen al unir puntos sin área: una línea sin rótulos
    # acababa mostrando media hoja en vez de su entorno inmediato.
    r = fitz.Rect(min(p[0] for p in limites), min(p[1] for p in limites),
                  max(p[0] for p in limites), max(p[1] for p in limites))
    r = fitz.Rect(r.x0 - margen_pt, r.y0 - margen_pt, r.x1 + margen_pt, r.y1 + margen_pt)
    if cajas and max(r.width, r.height) > ZONA_MAX_PT:
        # demasiado grande (rótulos a 120 pt: la letra quedaba chica para un modelo chico): la ventana de
        # ZONA_MAX_PT centrada entre el 1.er rótulo (el más cercano, R1) y su punto de la línea
        c = fitz.Rect(next(iter(cajas.values())))
        q = _cercano(pts, ((c.x0 + c.x1) / 2.0, (c.y0 + c.y1) / 2.0))
        cx, cy = ((c.x0 + c.x1) / 2.0 + q[0]) / 2.0, ((c.y0 + c.y1) / 2.0 + q[1]) / 2.0
        m = ZONA_MAX_PT / 2.0
        r = fitz.Rect(max(r.x0, cx - m), max(r.y0, cy - m), min(r.x1, cx + m), min(r.y1, cy + m))
    for eje in (0, 1):                                     # nunca más chica que ZONA_MIN_PT de lado
        lo, hi = (r.x0, r.x1) if eje == 0 else (r.y0, r.y1)
        if hi - lo < ZONA_MIN_PT:
            m = (lo + hi) / 2.0
            lo, hi = m - ZONA_MIN_PT / 2.0, m + ZONA_MIN_PT / 2.0
        r = fitz.Rect(lo, r.y0, hi, r.y1) if eje == 0 else fitz.Rect(r.x0, lo, r.x1, hi)
    return r


def recorte(page, pts_pt: Sequence[Tuple[float, float]], cajas_pt: Dict[str, tuple],
            lado_px: int = LADO_PX, margen_pt: float = MARGEN_PT,
            puntos: Sequence[Tuple[float, float]] = (), trayecto_completo=False) -> bytes:
    """PNG de la zona (`zona`) con la línea y los rótulos marcados (`puntos` = puntas de sus guías)."""
    z = zona(pts_pt, {} if trayecto_completo else cajas_pt, margen_pt,
             () if trayecto_completo else puntos) & page.rect
    if z.is_empty:
        raise ValueError("La línea queda fuera de la página")
    if trayecto_completo:
        cajas_pt = {rid:c for rid,c in cajas_pt.items() if fitz.Rect(c).intersects(z)}
    escala = lado_px / max(z.width, z.height)
    # `clip` va en coords de la VISTA (page.rect, ya girada): medido con /Rotate 90, no se des-gira
    pix = page.get_pixmap(matrix=fitz.Matrix(escala, escala), clip=z, alpha=False)
    ancho_px, alto_px = z.width * escala, z.height * escala
    doc = fitz.open()
    hoja = doc.new_page(width=ancho_px, height=alto_px)
    hoja.insert_image(hoja.rect, pixmap=pix)

    def px(p):
        return fitz.Point((p[0] - z.x0) * escala, (p[1] - z.y0) * escala)
    forma = hoja.new_shape()
    forma.draw_polyline([px(p) for p in pts_pt])
    forma.finish(color=MAGENTA, width=LINEA_PX, closePath=False)
    for rid, c in cajas_pt.items():
        a, b = px((c[0], c[1])), px((c[2], c[3]))
        forma.draw_rect(fitz.Rect(a, b) + (-3, -3, 3, 3))
        forma.finish(color=TURQUESA, width=2.0)
    forma.commit()
    for rid, c in cajas_pt.items():                       # el id encima de su caja, blanco sobre turquesa
        a = px((c[0], c[1]))
        ancho = 9.0 * len(rid) + 8.0
        # siempre DENTRO del recorte (un rótulo que empieza fuera dejaba su id afuera: compuesta DU06)
        x = min(max(a.x - 3, 0.0), ancho_px - ancho)
        y = min(max(a.y - 24, 0.0), alto_px - 20)
        etiqueta = fitz.Rect(x, y, x + ancho, y + 20)
        hoja.draw_rect(etiqueta, color=TURQUESA, fill=TURQUESA)
        hoja.insert_text((etiqueta.x0 + 4, etiqueta.y1 - 5), rid, fontsize=14, fontname="hebo", color=(1, 1, 1))
    salida = hoja.get_pixmap(alpha=False)
    if max(salida.width, salida.height) != lado_px:        # redondeo de la página: al lado exacto
        k = lado_px / max(salida.width, salida.height)
        salida = hoja.get_pixmap(matrix=fitz.Matrix(k, k), alpha=False)
    return salida.tobytes("png")
