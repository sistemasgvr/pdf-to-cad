"""Texto contextual del PDF alrededor del recorrido (no implica asociación de diámetro)."""
from __future__ import annotations

import fitz

from hoja.recorte_diametro import _cercano, zona


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
