"""render_lote.py — dibujar varios recortes de UN PDF en otro proceso (PURO, sin Qt).

Lo usa el compositor (`ui/asistente/composite_renders_lote`) para dibujar las piezas de la hoja compuesta en varios
procesos a la vez (2026-11-20, monitor: con 36 mapas la ventana se trababa ~10 s dibujándolas de a una). Es la MISMA
llamada que hacía la ventana (`page.get_pixmap(matrix=Matrix(escala, escala), alpha=False, clip=recorte)`) sobre los
mismos bytes del PDF y con las capas en el mismo estado (`pdf_layers.poner_encendidas`): MuPDF da los mismos píxeles.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple


def dibujar(datos: bytes, ons, pedidos: Sequence[Tuple[int, float, Tuple[float, float, float, float]]]) -> List[tuple]:
    """`pedidos` = [(hoja, escala, (x0, y0, x1, y1) del recorte en coords de la hoja)] → por pedido
    (ancho, alto, stride, x, y, samples)."""
    import fitz
    from hoja import pdf_layers
    out = []
    with fitz.open(stream=datos, filetype="pdf") as doc:
        pdf_layers.poner_encendidas(doc, ons)
        for hoja, escala, r in pedidos:
            pix = doc[int(hoja)].get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False, clip=fitz.Rect(*r))
            out.append((pix.width, pix.height, pix.stride, pix.x, pix.y, bytes(pix.samples)))
            del pix
    return out
