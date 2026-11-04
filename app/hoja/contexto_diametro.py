"""Texto contextual del PDF alrededor del recorrido (no implica asociación de diámetro)."""
from __future__ import annotations

import fitz

from hoja.recorte_diametro import _cercano, zona


def bloques(page, leer_forma=False):
    """Los bloques de texto de la hoja (`page.get_text("blocks")`); en un mapa sin capas cuyo texto no se extrae
    (Type3 sin ToUnicode, `hoja.leyenda_mapa.aplica`), las corridas leídas por la forma de las letras
    (`hoja.texto_pdf`) con el mismo formato (coords de la hoja sin girar, como `get_text`). Con `leer_forma`, también si
    `get_text` da algo: en esos mapas casi siempre es basura («rstru rztvw»)."""
    out = page.get_text("blocks")
    if not leer_forma and any(len(b) >= 7 and b[6] == 0 and str(b[4]).strip() for b in out):
        return out
    try:
        from hoja import leyenda_mapa, texto_pdf
        if not leyenda_mapa.aplica(page):
            return out
        corridas = texto_pdf.corridas(page)
    except Exception:                                     # noqa: BLE001 (sin texto se pregunta igual)
        return out
    extra = []
    for n, c in enumerate(corridas):
        esq = [(x, y) for g in c.glifos if g.tinta is not None for x in (g.tinta[0], g.tinta[2])
               for y in (g.tinta[1], g.tinta[3])] or [c.origen, c.fin]
        xs, ys = [p[0] for p in esq], [p[1] for p in esq]
        if c.texto.strip():
            extra.append((min(xs), min(ys), max(xs), max(ys), c.texto, n, 0))
    return extra if leer_forma and extra else list(out) + extra


def textos(page, pts, bloques=None):
    region = zona(pts, {}, margen_pt=60) & page.rect
    cerca = []
    for b in (page.get_text("blocks") if bloques is None else bloques):
        if len(b) < 7 or b[6] != 0:
            continue
        caja = fitz.Rect(b[:4]) * page.rotation_matrix
        x0,y0,x1,y1 = caja
        txt = b[4]
        if x1 < region.x0 or x0 > region.x1 or y1 < region.y0 or y0 > region.y1:
            continue
        centro=((x0+x1)/2,(y0+y1)/2)
        q=_cercano(pts,centro)
        dist=(q[0]-centro[0])**2+(q[1]-centro[1])**2
        cerca.append((dist," ".join(str(txt).split())[:280],[round(v,2) for v in caja]))
    return [dict(id=f"T{k+1}",texto=txt,caja_pt=caja,asociacion="contexto; no confirmado como rótulo de esta línea")
            for k,(_,txt,caja) in enumerate(sorted(cerca)[:12])]
