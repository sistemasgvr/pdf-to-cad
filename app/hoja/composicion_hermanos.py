"""composicion_hermanos.py — el PDF «hermano» que trae las hojas vecinas que faltan.

Pedido del usuario 2026-10-14: los mapas de Phoenix vienen partidos en dos PDF que son
UN solo mapa («QS Water_Indian School_North» = fila 17, «…_South» = fila 16). Si el
mapa índice de las hojas nombra vecinas que no están en los PDF abiertos, se busca en
la MISMA carpeta un PDF de la misma utilidad (por el nombre) cuyas hojas sean esas
celdas; la interfaz PREGUNTA antes de agregarlo.

PURO: solo fitz (lee el texto de las hojas, no el dibujo).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple

import fitz

from hoja import composicion_ficha as F

UTILIDADES = {
    "AGUA": {"water", "agua", "wtr", "potable"},
    "ALCANTARILLADO": {"sewer", "sanitary", "sswr", "alcantarillado", "ss"},
    "DRENAJE": {"sd", "storm", "drain", "drainage", "drenaje", "pluvial"},
    "GAS": {"gas", "ngas"},
    "ELECTRICO": {"elec", "electric", "electrical", "electrico", "power"},
    "TELECOM": {"tel", "telecom", "comm", "fiber", "telecomunicaciones"},
}
MAX_CANDIDATOS = 12          # PDFs de la carpeta que se abren como mucho
MAX_MB = 400                 # uno más grande no se abre para mirar
MIN_PARECIDO = 0.3


@dataclass
class Hermano:
    ruta: str
    celdas: List[Tuple[int, int]]       # celdas que faltaban y trae este PDF
    hojas: int


def tokens(nombre: str) -> Set[str]:
    base = os.path.splitext(os.path.basename(nombre))[0].lower()
    return {t for t in re.split(r"[^0-9a-záéíóúñ]+", base) if t}


def utilidad(nombre: str) -> Optional[str]:
    tk = tokens(nombre)
    hits = [u for u, pal in UTILIDADES.items() if tk & pal]
    return hits[0] if len(hits) == 1 else None


def parecido(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / max(1, len(ta | tb))


def candidatos(ruta: str, cargadas: Iterable[str] = ()) -> List[str]:
    """PDFs de la carpeta de `ruta` con la misma utilidad en el nombre (si la dice),
    del más parecido al menos."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    ya = {os.path.normcase(os.path.abspath(p)) for p in list(cargadas) + [ruta]}
    util = utilidad(ruta)
    out = []
    try:
        nombres = os.listdir(carpeta)
    except OSError:
        return []
    for n in nombres:
        p = os.path.join(carpeta, n)
        if not n.lower().endswith(".pdf") or os.path.normcase(os.path.abspath(p)) in ya:
            continue
        try:
            if os.path.getsize(p) > MAX_MB * 1024 * 1024:
                continue
        except OSError:
            continue
        if util is not None and utilidad(n) != util:
            continue
        pc = parecido(ruta, n)
        if pc >= MIN_PARECIDO:
            out.append((pc, p))
    out.sort(key=lambda it: (-it[0], it[1]))
    return [p for _, p in out[:MAX_CANDIDATOS]]


def celdas_de(page: fitz.Page) -> Tuple[Optional[Tuple[int, int]], Set[Tuple[int, int]]]:
    """(celda de la hoja, celdas de su mapa índice) solo con el texto."""
    lineas, _bloques = F._textos(page)
    celda, vecinas = F._celda(lineas)
    return celda, set(vecinas)


def buscar(rutas: Sequence[str], faltan: Iterable[Tuple[int, int]], cancelado=None) -> Optional[Hermano]:
    """El PDF de la carpeta que trae más de las celdas que `faltan` (al menos su
    primera hoja tiene que ser una de ellas o nombrar como vecina a una presente)."""
    faltan = set(faltan)
    if not faltan:
        return None
    vistos: Set[str] = set()
    mejor: Optional[Hermano] = None
    for ruta in rutas:
        if not ruta:
            continue
        for cand in candidatos(ruta, rutas):
            if cancelado is not None and cancelado():
                return mejor
            if cand in vistos:
                continue
            vistos.add(cand)
            try:
                doc = fitz.open(cand)
            except Exception:
                continue
            try:
                if doc.page_count < 1:
                    continue
                c0, _v = celdas_de(doc[0])
                if c0 is None:
                    continue
                trae = set()
                for i in range(doc.page_count):
                    if cancelado is not None and cancelado():
                        break
                    c, _v = celdas_de(doc[i]) if i else (c0, _v)
                    if c is not None and c in faltan:
                        trae.add(c)
                if trae and (mejor is None or len(trae) > len(mejor.celdas)):
                    mejor = Hermano(cand, sorted(trae), doc.page_count)
            finally:
                doc.close()
    return mejor
