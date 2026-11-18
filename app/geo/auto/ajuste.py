"""Georreferencia automática de la hoja de trabajo (2026-11-18): las anclas de cada pieza (`fuentes.ubicar`) se
llevan a px del lienzo (pt de la hoja de trabajo × zoom) y se ajusta UNA transformación px → mundo por
similaridad (`georef.fit`). Con una sola ancla: su escala (`Ancla.escala`), sin giro (los mapas van con el norte
arriba: giro medido 0.000°). Se mide el error; si no convence queda DUDOSA y nadie la aplica sola. PURO: sin Qt."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from geo import georef
from geo.auto import fuentes as F

RMS_MAX_FT = 25.0       # error medio aceptado (pies del mundo)
PIEZA_MAX_FT = 60.0     # ninguna pieza más lejos que esto de su lugar
ESCALA_TOL = 0.02       # la escala ajustada vs la de las anclas (recuadro del mapa)


@dataclass
class Resultado:
    matrix: list
    epsg: int
    cs_code: str
    rms_ft: float
    residuos: Dict[str, float] = field(default_factory=dict)   # etiqueta de la pieza → pies
    escala_ft_pt: float = 0.0                                    # ajustada (mundo por pt de la hoja de trabajo)
    aceptada: bool = False
    motivo: str = ""
    puntos: list = field(default_factory=list)                   # para `Georef.points` (el diálogo los muestra)
    etiquetas: List[str] = field(default_factory=list)
    fuente: str = ""


def _anclas_en_trabajo(comp, docs, fichas=None):
    """[(etiqueta, (x, y) pt de la hoja de trabajo, Ancla, Ubicacion)] de cada pieza ubicada.
    `docs[i]` = fitz.Document del PDF de origen i; `fichas` = {(fuente, hoja): Ficha} ya calculadas (opcional)."""
    from hoja import composite as C
    from hoja import composicion_ficha as cf
    piezas = comp.pieces if comp is not None else []
    sola = comp is None or comp.is_single_full_page()

    def size(pz):
        r = docs[pz.source][pz.page].rect
        return r.width, r.height

    dx = dy = 0.0
    if not sola:
        _, _, dx, dy = C.sheet_geometry(comp, size)
    out = []
    for pz in piezas:
        page = docs[pz.source][pz.page]
        f = (fichas or {}).get((pz.source, pz.page))
        if f is None:
            f = cf.ficha(page, pz.source)
        u = F.ubicar(page, f)
        if u is None:
            continue
        mapa = None if sola else C.piece_map(pz, size(pz), comp.target_scale())
        for a in u.anclas:
            if sola:
                q = a.hoja_pt
            else:
                x, y = mapa(*a.hoja_pt)
                q = (x + dx, y + dy)
            out.append((u.etiqueta, q, a, u))
    return out


def georref_hoja(comp, docs, zoom: float, fichas=None) -> Optional[Resultado]:
    """Georreferencia de la hoja de trabajo (px del lienzo = pt × zoom) o None si ninguna pieza dice dónde está.
    `comp` None = hoja suelta de `docs[0]`, hoja 0."""
    if comp is None:
        from hoja import composite as C
        comp = C.Composite([C.Piece(0, 0, [0.0, 0.0, 1.0, 1.0], 0.0, 0.0)])
    anclas = _anclas_en_trabajo(comp, docs, fichas)
    if not anclas:
        return None
    epsg, cs, fuente = anclas[0][3].epsg, anclas[0][3].cs_code, anclas[0][3].fuente
    anclas = [a for a in anclas if a[3].epsg == epsg]            # un solo sistema por hoja
    px = [(q[0] * zoom, q[1] * zoom) for _, q, _, _ in anclas]
    mundo = [a.mundo for _, _, a, _ in anclas]
    escalas = [a.escala for _, _, a, _ in anclas if a.escala > 0]
    esc_anclas = statistics.median(escalas) if escalas else 0.0
    if len(anclas) >= 2:
        M, _, _ = georef.fit(px, mundo, "similarity")
        M = [list(map(float, fila)) for fila in M]
    elif esc_anclas > 0:
        k = esc_anclas / zoom
        (x, y), (e, n) = px[0], mundo[0]
        M = [[k, 0.0, e - k * x], [0.0, -k, n + k * y], [0.0, 0.0, 1.0]]
    else:
        return None
    residuos, puntos = {}, []
    for (et, _, a, _), p, w in zip(anclas, px, mundo):
        e = M[0][0] * p[0] + M[0][1] * p[1] + M[0][2]
        n = M[1][0] * p[0] + M[1][1] * p[1] + M[1][2]
        residuos[et] = math.hypot(e - w[0], n - w[1])
        puntos.append({"px": [p[0], p[1]], "world": [w[0], w[1]], "label": et, "fuente": fuente, "celda": et})
    rms = math.sqrt(sum(r * r for r in residuos.values()) / len(residuos))
    esc = math.hypot(M[0][0], M[1][0]) * zoom
    r = Resultado(M, epsg, cs, rms, residuos, esc, False, "", puntos, [et for et, *_ in anclas], fuente)
    if rms > RMS_MAX_FT:
        r.motivo = "rms"
    elif max(residuos.values()) > PIEZA_MAX_FT:
        r.motivo = "pieza"
    elif len(anclas) >= 2 and esc_anclas > 0 and abs(esc / esc_anclas - 1.0) > ESCALA_TOL:
        r.motivo = "escala"
    else:
        r.aceptada = True
    return r


def trabajo(comp_dict: Optional[dict], fuentes: Sequence[bytes], zoom: float, progreso=None) -> Optional[dict]:
    """Para el trabajador (`proceso.Tarea("geo.auto.ajuste:trabajo")`): abre los PDF de origen (bytes, como
    `Main.src_pdfs`) y devuelve el resultado como dict (o None)."""
    import dataclasses

    import fitz
    from hoja import composite as C
    docs = [fitz.open(stream=b, filetype="pdf") for b in fuentes]
    try:
        comp = C.Composite.from_dict(comp_dict) if comp_dict else None
        r = georref_hoja(comp, docs, zoom)
        return None if r is None else dataclasses.asdict(r)
    finally:
        for d in docs:
            d.close()
