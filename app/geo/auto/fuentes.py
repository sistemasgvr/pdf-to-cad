"""Fuentes de georreferencia automática (2026-11-18): cada una mira una hoja y, si la reconoce, dice dónde está en
el mundo con ANCLAS (punto de la hoja visible en pt → punto del mundo). Se prueban en orden (`FUENTES`) y gana la
primera que responde. Hoy: índice de mapas en cuadrícula (cuartos de sección de Phoenix). Más adelante, sin tocar
el resto: GeoPDF, coordenadas escritas en la hoja, PLSS de la BLM. PURO: sin Qt."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from geo.auto import indice_mapas as IM

Pt = Tuple[float, float]

# «NE 1/4 SEC.26, T.2N, R.1E» (cajetín de los mapas de Phoenix y de muchos planos del oeste de EE. UU.)
RX_PLSS = re.compile(r"\b(NE|NW|SE|SW)\s*1\s*/\s*4\s*(?:OF\s*)?SEC(?:TION)?\.?\s*(\d{1,2})\s*,?\s*"
                     r"T\.?\s*(\d{1,2}\s*[NS])\s*,?\s*R\.?\s*(\d{1,2}\s*[EW])\b")


@dataclass
class Ancla:
    hoja_pt: Pt                 # hoja de ORIGEN visible, en pt
    mundo: Pt                   # en el sistema `Ubicacion.epsg`
    motivo: str = ""
    escala: float = 0.0         # unidades del mundo por pt de la hoja (0 = no se sabe)


@dataclass
class Ubicacion:
    epsg: int
    cs_code: str
    anclas: List[Ancla] = field(default_factory=list)
    fuente: str = ""
    etiqueta: str = ""          # lo que dice la hoja («16-10»)


def plss_de_texto(texto: str) -> List[Tuple[str, str, int, str]]:
    out = []
    for m in RX_PLSS.finditer(texto.upper()):
        out.append((m.group(3).replace(" ", ""), m.group(4).replace(" ", ""), int(m.group(2)), m.group(1)))
    return out


def confirma(texto: str, celda: IM.Celda, indice: IM.Indice) -> bool:
    """¿El texto de la hoja confirma que es ESA celda de ESA jurisdicción? Si trae una sección PLSS, vale solo si
    es la de la celda; si no trae, vale si nombra la jurisdicción (`indice.palabras`). Un «17-10» solo no basta:
    otra ciudad puede usar el mismo número."""
    plss = plss_de_texto(texto)
    if plss:
        return tuple(celda.plss) in plss
    t = texto.upper()
    return any(p in t for p in indice.palabras)


def texto_de(page) -> str:
    """El texto legible de la hoja: `get_text`, y si su fuente es Type3 sin mapa de caracteres (mapas SIG de
    Phoenix), el leído por la forma de cada letra (`texto_pdf`)."""
    from hoja import texto_pdf
    partes = [page.get_text()]
    if texto_pdf.necesita_decodificar(page):
        partes += texto_pdf.textos(page)
    return "\n".join(partes)


def _cs_code(epsg: int) -> str:
    try:
        from nucleo import sistemas_cs
        return sistemas_cs.codigo_civil3d(epsg) or ""
    except Exception:
        return ""


def celda_en_mundo(celda: Tuple[int, int], texto: str) -> Optional[Tuple[str, str, int, Pt]]:
    """(índice, clave de la celda, EPSG, centro del recuadro de su polígono) de la celda `(fila, columna)` que el `texto` de la
    hoja confirma (`confirma`), o None si ningún índice la tiene o queda ambigua. Lo usa también la composición
    sugerida (`hoja/composicion_geo`): ubica cada hoja sin leer otra vez la hoja."""
    for id_ in IM.disponibles():
        ix = IM.cargar(id_)
        buenas = [(k, c) for k, c in ix.por_numero(*celda) if confirma(texto, c, ix)]
        if len(buenas) == 1:
            k, c = buenas[0]
            return id_, k, ix.epsg, c.centro_caja()
    return None


def por_indice(page, ficha, texto: Optional[str] = None) -> Optional[Ubicacion]:
    """Índice de mapas en cuadrícula: la celda que dice la hoja, confirmada por su texto → ancla = centro del
    recuadro del mapa → centroide del polígono de la celda (medido: Sewer/Water North ~4 ft)."""
    if ficha is None or ficha.celda is None:
        return None
    from hoja import composicion_encaje as E
    v = E.caja(ficha)
    if v is None:
        return None
    for id_ in IM.disponibles():
        ix = IM.cargar(id_)
        cand = ix.por_numero(*ficha.celda)
        if not cand:
            continue
        if texto is None:
            texto = texto_de(page)
        buenas = [(k, c) for k, c in cand if confirma(texto, c, ix)]
        if len(buenas) != 1:
            continue                                   # sin confirmar o ambigua: no se adivina
        k, c = buenas[0]
        centro = ((v[0] + v[2]) / 2.0, (v[1] + v[3]) / 2.0)
        esc = ix.recuadro_ft / (v[2] - v[0]) if ix.recuadro_ft and v[2] > v[0] else 0.0
        return Ubicacion(ix.epsg, _cs_code(ix.epsg), [Ancla(centro, c.centro_caja(), id_ + ":" + k, esc)], id_, k)
    return None


FUENTES: List[Callable] = [por_indice]


def ubicar(page, ficha, texto: Optional[str] = None) -> Optional[Ubicacion]:
    for f in FUENTES:
        u = f(page, ficha, texto)
        if u is not None:
            return u
    return None
