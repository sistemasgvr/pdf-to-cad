"""pdf_legend.py — La LEYENDA de líneas que trae el propio PDF (sin Qt).

Los juegos de planos de utilidades traen una hoja de «NOTES, ABBREVIATIONS, AND
LEGEND» (DU08 h.3 y h.33, DU10 h.1 y h.33, LABOE h.3, h.6…): una columna de filas con
una MUESTRA de cada línea —el linetype con sus letras, «—TE—»— y su DESCRIPCIÓN
(«PROPOSED TRACTION ELECTRIFICATION DUCTBANK (METRO SYSTEMS)»). El paso «Capas de la
hoja» la muestra (pedido del usuario 2026-10-05: «una leyenda de capas de acuerdo al
documento, para que el usuario conozca cada capa») y cada código del linetype queda
con la descripción que le da el propio plano.

  · `legend_pages(doc)`: hojas cuyo texto dice LEGEND / LEYENDA (~50 ms por hoja).
  · `page_legend(page)`: fila = línea de texto con una muestra a su IZQUIERDA en la
    misma franja (los dibujos contiguos hasta el texto); quedan solo las COLUMNAS de
    ≥`ROW_MIN` filas alineadas con muestra larga (≥`SAMPLE_MIN_PT`) y letras en
    ≥`CODE_SHARE` de ellas: el cajetín, las tablas y los textos sueltos no.
  · `document_legend(doc)`: todas las hojas con leyenda, sin repetir filas.
Las letras se leen con `recognition_letters` (las mismas que clasifican las capas).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import recognition_letter_lines as lines
import recognition_letters as letters

LEGEND_WORDS = re.compile(r"\b(LEGEND|LEYENDA)\b", re.IGNORECASE)
# palabras de una fila de leyenda de utilidades: ordenan las hojas (la más completa primero)
ROW_WORDS = re.compile(r"^\s*(EXIST|PROP|ABAND|EXISTENTE|PROPUEST|ABANDON)", re.IGNORECASE | re.MULTILINE)
MAX_PAGES = 3             # hojas con leyenda que se leen (se repiten de hoja en hoja: ~1 s cada una)
SAMPLE_MIN_PT = 60.0      # la muestra de una línea es larga (DU08: 162 pt); un símbolo, no
SAMPLE_MAX_PT = 450.0     # …y empieza a menos de esto del texto
SAMPLE_MAX_H_PT = 12.0    # …y es HORIZONTAL: una etiqueta con su flecha (LABOE h.8/h.9) es más alta
SAMPLE_GAP_PT = 25.0      # dibujos de la muestra contiguos (los huecos del linetype son menores)
TEXT_GAP_PT = 3.0         # la muestra termina antes del texto
ROW_BAND = 0.6            # franja de la fila: ± esto × alto del texto (mín. 4 pt)
ROW_MIN = 3               # una leyenda es una COLUMNA de varias filas alineadas…
ROW_PITCH_TOL = 0.35      # …a paso regular (± 35 % del paso típico)…
CODE_SHARE = 0.3          # …y la mayoría de sus muestras lleva letras
COLUMN_TOL_PT = 8.0       # textos de la misma columna: mismo x de inicio (± esto)


@dataclass
class LegendRow:
    page: int
    sample: Tuple[float, float, float, float]   # x0, y0, x1, y1 (pt) de la muestra
    text: str                                   # descripción tal como la trae el PDF
    raw: str = ""                               # letras como se leyeron («e», «TE», «e(oh)»)
    code: str = ""                              # código normalizado («E», «TE»), "" sin letras
    overhead: bool = False
    utility: Optional[str] = None               # utilidad del código (`letters.LETTER_CODES`)


def legend_pages(doc, should_stop: Optional[Callable[[], bool]] = None) -> List[int]:
    """Índices de las hojas cuyo texto menciona una leyenda, la más completa primero
    (más filas «EXISTING…/PROPOSED…»); a igual cantidad, en el orden del PDF."""
    found = []
    for i in range(doc.page_count):
        if should_stop and should_stop():
            break
        try:
            text = doc[i].get_text()
        except Exception:
            continue
        if LEGEND_WORDS.search(text):
            found.append((-len(ROW_WORDS.findall(text)), i))
    return [i for _score, i in sorted(found)]


def _letter_sites(drawings) -> List[Tuple[Tuple[float, float], str]]:
    """[(centro del hueco, texto leído)] de todos los rótulos de linetype de la hoja."""
    by_layer = defaultdict(list)
    for d in drawings:
        by_layer[d.get("layer") or ""].append(d)
    out = []
    for paths in by_layer.values():
        chains, _owner = lines.stroke_chains(paths)
        gaps, _touch = lines.gaps(lines.dash_ends(chains))
        for (o, u, g, sure, _a, _b), members in zip(gaps, lines.group_members(chains, gaps)):
            got = letters.read_text([loc for _ci, loc in members], sure) if members else None
            if got:
                out.append(((o[0] + u[0] * g / 2.0, o[1] + u[1] * g / 2.0), got[0]))
    return out


def _sample_box(band: Sequence[dict], text_x0: float):
    """Los dibujos CONTIGUOS que terminan junto al texto (de derecha a izquierda)."""
    left = text_x0 - TEXT_GAP_PT
    picked = []
    for d in sorted(band, key=lambda d: -d["rect"].x1):
        r = d["rect"]
        if r.x1 < left - SAMPLE_GAP_PT:
            break
        picked.append(r)
        left = min(left, r.x0)
    if not picked:
        return None
    return (min(r.x0 for r in picked), min(r.y0 for r in picked),
            max(r.x1 for r in picked), max(r.y1 for r in picked))


def _regular_run(col):
    """Las filas de la columna que van a PASO REGULAR: una leyenda se dibuja fila tras
    fila a la misma distancia (una fila que no se leyó deja un paso doble o triple);
    las etiquetas sueltas de un plano no. Tandas de ≥`ROW_MIN` filas."""
    col = sorted(col, key=lambda c: c[1])
    if len(col) < ROW_MIN:
        return []

    def fits(gap, pitch):
        return pitch > 0 and any(abs(gap - k * pitch) <= ROW_PITCH_TOL * pitch for k in (1, 2, 3))
    out, start = [], 0
    while start < len(col) - 1:
        pitch = col[start + 1][1] - col[start][1]
        end = start + 1
        while end + 1 < len(col) and fits(col[end + 1][1] - col[end][1], pitch):
            end += 1
        if end - start + 1 >= ROW_MIN:
            out += col[start:end + 1]
        start = end if end > start + 1 else start + 1
    return out


def page_legend(page) -> List[LegendRow]:
    """Filas de leyenda de una hoja (vacío si la hoja no tiene una)."""
    drawings = [d for d in page.get_drawings() if d.get("type") not in ("clip", "group")]
    candidates = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if len(text) < 4 or not re.search(r"[A-Za-z]{3}", text):
                continue
            x0, y0, x1, y1 = line["bbox"]
            yc, h = (y0 + y1) / 2.0, max(y1 - y0, 1.0)
            band_h = max(4.0, ROW_BAND * h)
            band = [d for d in drawings
                    if abs((d["rect"].y0 + d["rect"].y1) / 2.0 - yc) <= band_h
                    and d["rect"].height <= 3.0 * h
                    and d["rect"].x1 <= x0 - TEXT_GAP_PT and d["rect"].x0 >= x0 - SAMPLE_MAX_PT]
            box = _sample_box(band, x0) if band else None
            if box is None or box[2] - box[0] < SAMPLE_MIN_PT or box[3] - box[1] > SAMPLE_MAX_H_PT:
                continue
            candidates.append((x0, yc, band_h, box, text))
    if not candidates:
        return []
    sites = _letter_sites(drawings)
    columns = defaultdict(list)
    for cand in candidates:
        columns[round(cand[0] / COLUMN_TOL_PT)].append(cand)
    rows: List[LegendRow] = []
    for col in columns.values():
        built = []
        for x0, yc, band_h, box, text in _regular_run(col):
            found = [t for (p, t) in sites
                     if abs(p[1] - yc) <= band_h and box[0] - 2.0 <= p[0] <= box[2] + 2.0]
            raw = max(set(found), key=found.count) if found else ""
            code, overhead = letters.normalize_code(raw)
            built.append(LegendRow(page.number, box, text, raw, code, overhead,
                                   None if overhead else letters.code_utility(code)))
        if len(built) >= ROW_MIN and sum(1 for r in built if r.code) >= CODE_SHARE * len(built):
            rows += built
    return sorted(rows, key=lambda r: (r.sample[0] // 200, r.sample[1]))


def document_legend(doc, should_stop: Optional[Callable[[], bool]] = None) -> List[LegendRow]:
    """La leyenda del documento: filas de sus hojas con leyenda (las `MAX_PAGES` más
    completas; se para antes si una hoja ya no agrega nada), sin repetir (misma
    descripción y mismo código = la misma fila)."""
    out, seen = [], set()
    for n, i in enumerate(legend_pages(doc, should_stop)):
        if n >= MAX_PAGES or (should_stop and should_stop()):
            break
        new = 0
        for row in page_legend(doc[i]):
            key = (row.code, row.overhead, " ".join(row.text.upper().split()))
            if key not in seen:
                seen.add(key)
                out.append(row)
                new += 1
        if out and not new:
            break                                # repite la leyenda de la hoja anterior
    return out


def render_sample(page, row: LegendRow, zoom: float = 3.0) -> bytes:
    """PNG de la muestra de una fila (con 2 pt de aire)."""
    import fitz
    x0, y0, x1, y1 = row.sample
    clip = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2) & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    return pix.tobytes("png")
