"""leyenda_cruce.py — cruza la LEYENDA DEL PDF con las líneas de la hoja (PURO, sin Qt).

2.º reporte del usuario (2026-10-07, DU08 h.26): la leyenda del PDF se mostraba como una
lista aparte; al hacer clic en «EXISTING ELECTRICAL» solo se marcaban las dos líneas «e»
y las muchas «E», «TE» y «SE» de la hoja (eléctricas, según la misma leyenda) no se
veían en ningún sitio. Ahora cada tipo de línea de la hoja (`leyenda_estandar.Fila`) lleva
la fila de la leyenda que lo describe:

  · `estado_de_texto`: «EXISTING» → E, «PROPOSED»/«NEW» → N, «… ABANDONED» → A, «TO BE
    ABANDONED» → D (los planos lo dibujan con «//»; también la errata «ABANONDED»),
    «TO BE REMOVED» → M;
  · `utilidad_de_fila`: por el código de sus letras («TE» → eléctrico) o, sin letras
    («PROPOSED STORM DRAIN», continua), por las palabras de la descripción;
  · `estado_por_leyenda`: una capa sin estado en el nombre (`_Xref`, `U-TRPW-DBNK-P`) lo
    toma de las filas con SUS letras —misma caja: «g» existente, «G» propuesta— si todas
    dicen lo mismo (las variantes abandonadas usan las mismas letras y no cuentan); en
    «W» la leyenda usa la mayúscula para existente y propuesta: queda sin estado;
  · `emparejar`: filas de la leyenda de la misma utilidad, aérea o no, mismo estado, el
    mismo código de letras si lo hay (si no, otro de la misma utilidad: «S» leída, «SS» en
    la leyenda) y, si alguna coincide, la misma caja.
Las filas se dan como objetos con `text`, `code`, `raw`, `overhead` (`pdf_legend.LegendRow`).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

from reconocimiento import recognition_letters as letters_mod

_TO_BE_ABANDONED = re.compile(r"TO\s+BE\s+ABAN")
_TO_BE_REMOVED = re.compile(r"TO\s+BE\s+(REMOVED|DEMOLISHED)")
_NEW = re.compile(r"\b(PROPOSED|NEW)\b")
# palabras de la descripción → utilidad (filas sin letras)
_WORDS = (("ELECTRICO", ("ELECTRIC",)), ("TELECOM", ("TELECOM", "TELEPHONE", "COMMUNICATION", "FIBER")),
          ("AGUA", ("WATER",)), ("GAS", ("GAS",)), ("ALCANTARILLADO", ("SEWER", "SANITARY")),
          ("DRENAJE", ("STORM", "DRAIN")))
_ABANDONED_VARIANTS = ("A", "D", "M")


def estado_de_texto(text: str) -> str:
    """Estado §8.1.6 que dice la descripción de una fila de la leyenda, o ""."""
    up = (text or "").upper()
    if _TO_BE_ABANDONED.search(up):
        return "D"
    if "ABAN" in up:
        return "A"
    if _TO_BE_REMOVED.search(up):
        return "M"
    if _NEW.search(up):
        return "N"
    if "FUTURE" in up:
        return "F"
    if "TEMPORARY" in up:
        return "T"
    if "EXIST" in up:
        return "E"
    return ""


def utilidad_de_fila(row) -> Optional[str]:
    """Utilidad de una fila de la leyenda (también las aéreas: «e(oh)» → eléctrico)."""
    if row.code:
        return letters_mod.code_utility(row.code)
    up = (row.text or "").upper()
    hits = [u for u, words in _WORDS if any(w in up for w in words)]
    return hits[0] if len(hits) == 1 else None


def _core(raw: str) -> str:
    return letters_mod.raw_core(raw or "")


def estado_por_leyenda(code: str, raw: str, rows: Sequence) -> str:
    """Estado de unas letras («g», «TE») según la leyenda: el de las filas con esas
    mismas letras, si todas dicen lo mismo; "" si no hay filas o se contradicen."""
    if not code:
        return ""
    st = {estado_de_texto(r.text) for r in rows
          if not r.overhead and r.code == code and _core(r.raw) == _core(raw)} - {""}
    base = st - set(_ABANDONED_VARIANTS)
    if len(base) == 1:
        return base.pop()
    if not base and len(st) == 1:
        return st.pop()
    return ""


def emparejar(utilidad: str, aerea: bool, estado: str, code: str, letras: Iterable[str],
              rows: Sequence, paredes: bool = True) -> List[int]:
    """Índices de las filas de la leyenda que describen ese tipo de línea de la hoja.
    `paredes` = la hoja tiene paredes de tubería de esa utilidad y estado: sin ellas, una
    fila cuya muestra las dibuja («EXISTING SANITARY SEWER (24" OR LARGER)», `walls`) no
    la describe (DU08 h.26, reporte del usuario 2026-10-09), salvo que sea la única."""
    cands = [i for i, r in enumerate(rows)
             if bool(r.overhead) == aerea and utilidad_de_fila(r) == utilidad]
    if estado:
        cands = [i for i in cands if estado_de_texto(rows[i].text) == estado]
    else:
        cands = [i for i in cands if estado_de_texto(rows[i].text) not in _ABANDONED_VARIANTS] or cands
    if code:
        # otro código de la misma utilidad vale si el mismo no está («S» leída, «SS» en la
        # leyenda; «SD» leída y «PROPOSED STORM DRAIN» continua, sin letras)
        cands = [i for i in cands if rows[i].code == code] or cands
    else:
        cands = [i for i in cands if not rows[i].code] or cands
    cores = {_core(x) for x in letras}
    exact = [i for i in cands if _core(rows[i].raw) in cores]
    cands = exact or cands
    if not paredes:
        cands = [i for i in cands if not getattr(rows[i], "walls", False)] or cands
    out, seen = [], set()
    for i in cands:
        if rows[i].text not in seen:
            seen.add(rows[i].text)
            out.append(i)
    return out
