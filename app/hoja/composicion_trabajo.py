"""composicion_trabajo.py — el análisis de la «Composición sugerida» como trabajo de fondo (PURO).

`calcular` (movido tal cual de `ui.asistente.composite_suggest`): fichas de TODAS las hojas,
uniones, grupos armados y el PDF hermano. `analizar` es lo que corre el proceso trabajador
«fondo» (`ui.comun.proceso`, pedido del usuario 2026-10-14): la caché de fichas queda EN el
trabajador (decenas de MB por PDF que antes vivían en la ventana) y el resultado vuelve sin
los trazos de los bordes de cada ficha (`Ficha.lineas`: la ventana no los usa).
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import fitz

import vector_pipeline as VP
from hoja import composicion_ficha as F
from hoja import composicion_hermanos as H
from hoja import composicion_sugerida as G

MAX_FICHAS_EN_MEMORIA = 6          # PDFs cuyas fichas se guardan (cada una pesa decenas de MB)


@dataclass
class Resultado:
    clave: tuple
    analisis: Optional[G.Analisis]
    hermano: Optional[H.Hermano] = None
    nombres: List[str] = field(default_factory=list)
    error: str = ""


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def clave_de(fuentes: Sequence[dict]) -> tuple:
    return tuple(_hash(f["data"]) for f in fuentes)


def calcular(fuentes: Sequence[dict], progreso=None, cancelado=None,
             fichas_cache: Optional[Dict[str, list]] = None) -> Optional[Resultado]:
    """Todo el análisis: fichas de TODAS las hojas, uniones, grupos armados y el PDF
    hermano. Lo corre el hilo; las pruebas lo llaman directo. None = cancelado."""
    def avisar(etapa, i=0, n=0):
        if progreso is not None:
            progreso(etapa, i, n)
    clave = clave_de(fuentes)
    nombres = [f.get("name", "") for f in fuentes]
    docs = [fitz.open(stream=f["data"], filetype="pdf") for f in fuentes]
    try:
        total = sum(d.page_count for d in docs)
        hechas = 0
        fpd = []
        for i, (f, d) in enumerate(zip(fuentes, docs)):
            h = clave[i]
            if fichas_cache is not None and h in fichas_cache:
                fs = [dataclasses.replace(x, doc=i) for x in fichas_cache[h]]
            else:
                base = hechas
                fs = F.fichas(d, i, progreso=lambda k, n, b=base: avisar("hojas", b + k, total),
                              cancelado=cancelado)
                if cancelado is not None and cancelado():
                    return None
                if fichas_cache is not None:
                    fichas_cache[h] = [dataclasses.replace(x) for x in fs]
                    while len(fichas_cache) > MAX_FICHAS_EN_MEMORIA:
                        fichas_cache.pop(next(iter(fichas_cache)))
            hechas += d.page_count
            fpd.append(fs)
        avisar("uniones")
        an = G.analizar(fpd, cancelado)
        for k, g in enumerate(an.grupos):
            if cancelado is not None and cancelado():
                return None
            avisar("armar", k + 1, len(an.grupos))
            G.armar(g, an, docs, lambda d_, h_: VP.detect_scale(docs[d_][h_]), nombres)
        hermano = None
        rutas = [f.get("path") for f in fuentes if f.get("path")]
        if an.faltan() and rutas:
            avisar("hermano")
            hermano = H.buscar(rutas, an.faltan(), cancelado)
        return Resultado(clave, an, hermano, nombres)
    finally:
        for d in docs:
            d.close()


_FICHAS: Dict[str, list] = OrderedDict()      # caché del proceso trabajador


def analizar(fuentes: Sequence[dict], progreso=None) -> Optional[Resultado]:
    """`calcular` en el trabajador, con su caché, devolviendo el resultado liviano."""
    res = calcular(fuentes, (lambda e, i, n: progreso(e, i, n)) if progreso else None, None, _FICHAS)
    if res is not None and res.analisis is not None:
        res.analisis.fichas = {k: dataclasses.replace(f, lineas=[]) for k, f in res.analisis.fichas.items()}             if isinstance(res.analisis.fichas, dict) else res.analisis.fichas
    return res
