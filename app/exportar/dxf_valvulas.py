"""dxf_valvulas.py — las válvulas (`Main.valvulas`) al DXF (pedido del usuario 2026-11-05).

Un punto por válvula en la capa `PDFCAD_VALVULAS`, con XDATA `PDFCAD`:

    PDFCAD_VALVULA, TIPO, UTILIDAD, ESTADO, DIAMETER, ROT_DEG, ORIGEN, CERTEZA, PIPE_IDX (−1 = sin tubería)

ROT_DEG = rumbo de su tubería en coordenadas CAD (con georreferencia incluida). `ImportarRed.cs` no las lee todavía:
las claves que no conoce se ignoran.
"""
from __future__ import annotations

import math

CAPA = "PDFCAD_VALVULAS"


def _rumbo_cad(win, v, rumbo) -> float:
    a = math.radians(rumbo)
    p0 = win._to_cad(v["x"], v["y"])
    p1 = win._to_cad(v["x"] + math.cos(a), v["y"] - math.sin(a))
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 180.0


def exportar(win, doc, msp) -> int:
    """Escribe las válvulas; devuelve cuántas."""
    from vector_pipeline import ensure_layer
    filas = win._filas_valvulas() if getattr(win, "valvulas", None) else []
    if not filas:
        return 0
    if "PDFCAD" not in doc.appids:
        doc.appids.add("PDFCAD")
    ensure_layer(doc, CAPA)
    for v, pipe, diam, rumbo in filas:
        punto = msp.add_point(win._to_cad(v["x"], v["y"]), dxfattribs={"layer": CAPA})
        punto.set_xdata("PDFCAD", [
            (1000, "PDFCAD_VALVULA"), (1000, f"TIPO={v.get('tipo') or ''}"), (1000, f"UTILIDAD={v.get('utilidad') or ''}"),
            (1000, f"ESTADO={v.get('estado') or ''}"), (1000, f"DIAMETER={'' if diam is None else f'{diam:g}'}"),
            (1000, f"ROT_DEG={_rumbo_cad(win, v, rumbo):.3f}"), (1000, f"ORIGEN={v.get('origen') or ''}"),
            (1000, f"CERTEZA={v.get('certeza') or ''}"), (1000, f"PIPE_IDX={-1 if pipe is None else int(pipe)}")])
    return len(filas)
