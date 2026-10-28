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
from hoja import composite as C
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


# ── memoria por CONTENIDO (pedido del usuario 2026-10-28: agregar o quitar un PDF no debe repetir lo
# ya hecho). Las uniones de dos hojas y cada composición armada dependen solo de esas hojas (no de
# los demás PDF ni de su número en la lista): se guardan por la huella de su PDF y se reusan con los
# números de ahora. Mismo resultado que calcularlas de nuevo.
MAX_MEMO = 20000                 # uniones de dos hojas guardadas
MAX_ARMADAS = 64                 # composiciones armadas guardadas
_UNIONES: Dict[tuple, object] = OrderedDict()
_ARMADAS: Dict[tuple, dict] = OrderedDict()
_HERMANOS: Dict[tuple, object] = OrderedDict()


def _guardar(memo: Dict, clave, valor, tope: int):
    memo[clave] = valor
    while len(memo) > tope:
        memo.pop(next(iter(memo)))


class _Encajes(G.Encajes):
    def __init__(self, huellas: Sequence[str]):
        self.h = huellas

    def _clave(self, tipo, fa, fb, lado, *resto):
        return (tipo, self.h[fa.doc], fa.hoja, self.h[fb.doc], fb.hoja, fa.doc == fb.doc, lado) + resto

    def _usar(self, clave, fa, fb, calc):
        if clave in _UNIONES:
            c = _UNIONES[clave]
        else:
            c = calc()
            _guardar(_UNIONES, clave, None if c is None else dataclasses.replace(c, a=(-1, -1), b=(-1, -1)), MAX_MEMO)
        return None if c is None else dataclasses.replace(c, a=fa.clave, b=fb.clave)

    def cad(self, fa, fb, lado, ra, rb):
        ia = fa.rotulos.index(ra) if ra is not None and ra in fa.rotulos else None
        ib = fb.rotulos.index(rb) if rb is not None and rb in fb.rotulos else None
        return self._usar(self._clave("cad", fa, fb, lado, ia, ib), fa, fb,
                          lambda: super(_Encajes, self).cad(fa, fb, lado, ra, rb))

    def mapa(self, fa, fb, lado, escala=None, guia=None):
        return self._usar(self._clave("mapa", fa, fb, lado, escala, guia), fa, fb,
                          lambda: super(_Encajes, self).mapa(fa, fb, lado, escala, guia))


def _clave_armada(g, huellas, nombres) -> tuple:
    h = lambda n: (huellas[n[0]], n[1])  # noqa: E731
    docs = sorted({n[0] for n in g.nodos})
    return (g.tipo, tuple(h(n) for n in g.nodos), tuple(g.transf.get(n) for n in g.nodos),
            tuple(sorted((h(c.a), h(c.b), c.lado, c.escala, c.t, c.corte_a, c.corte_b) for c in g.costuras)),
            tuple(nombres[d] if d < len(nombres) else "" for d in docs))


def _armar(g, an, docs, nombres, huellas):
    """`G.armar` con memoria: la misma composición (mismas hojas, uniones y nombres) no se arma dos veces."""
    clave = _clave_armada(g, huellas, nombres)
    if clave in _ARMADAS:
        d = _ARMADAS[clave]
        comp = C.Composite.from_dict(d["comp"])
        for p in comp.pieces:
            p.source = huellas.index(d["huellas"][p.source])
        g.composite = comp
        return comp
    comp = G.armar(g, an, docs, lambda d_, h_: VP.detect_scale(docs[d_][h_]), nombres)
    usadas = sorted({p.source for p in comp.pieces})
    guardada = C.Composite.from_dict(comp.to_dict())
    for p in guardada.pieces:
        p.source = usadas.index(p.source)
    _guardar(_ARMADAS, clave, {"comp": guardada.to_dict(), "huellas": [huellas[i] for i in usadas]}, MAX_ARMADAS)
    return comp


def calcular(fuentes: Sequence[dict], progreso=None, cancelado=None,
             fichas_cache: Optional[Dict[str, list]] = None, paralelo: int = 1) -> Optional[Resultado]:
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
                aviso = lambda k, n, b=base: avisar("hojas", b + k, total)  # noqa: E731
                fs = None
                if paralelo > 1 and d.page_count >= HOJAS_PARA_PARALELO:
                    try:
                        fs = _fichas_en_paralelo(f, d, i, paralelo, aviso)
                    except Exception:             # sin procesos (memoria, permisos): de a una
                        fs = None
                if fs is None:
                    fs = F.fichas(d, i, progreso=aviso, cancelado=cancelado)
                if cancelado is not None and cancelado():
                    return None
                if fichas_cache is not None:
                    fichas_cache[h] = [dataclasses.replace(x) for x in fs]
                    while len(fichas_cache) > MAX_FICHAS_EN_MEMORIA:
                        fichas_cache.pop(next(iter(fichas_cache)))
            hechas += d.page_count
            fpd.append(fs)
        avisar("uniones")
        con_memoria = len(set(clave)) == len(clave)     # el mismo PDF dos veces: sin memoria
        an = G.analizar(fpd, cancelado, enc=_Encajes(clave) if con_memoria else G.Encajes())
        for k, g in enumerate(an.grupos):
            if cancelado is not None and cancelado():
                return None
            avisar("armar", k + 1, len(an.grupos))
            if con_memoria:
                _armar(g, an, docs, nombres, clave)
            else:
                G.armar(g, an, docs, lambda d_, h_: VP.detect_scale(docs[d_][h_]), nombres)
        hermano = None
        rutas = [f.get("path") for f in fuentes if f.get("path")]
        if an.faltan() and rutas:
            ck = (tuple(rutas), tuple(an.faltan()))
            if ck in _HERMANOS:
                hermano = _HERMANOS[ck]
            else:
                avisar("hermano")
                hermano = H.buscar(rutas, an.faltan(), cancelado)
                if cancelado is None or not cancelado():
                    _guardar(_HERMANOS, ck, hermano, 32)
        return Resultado(clave, an, hermano, nombres)
    finally:
        for d in docs:
            d.close()


_FICHAS: Dict[str, list] = OrderedDict()      # caché del proceso trabajador

HOJAS_PARA_PARALELO = 6      # con menos, arrancar los procesos tarda más que leerlas
HOJAS_POR_ENCARGO = 3        # hojas que lee cada proceso de una vez (el avance va de a tantas)


def _fichas_de(fuente, doc_index: int, paginas: Sequence[int]) -> list:
    """Fichas de esas hojas (lo que hace `composicion_ficha.fichas`, hoja por hoja)."""
    d = fitz.open(fuente) if isinstance(fuente, str) else fitz.open(stream=fuente, filetype="pdf")
    try:
        out = []
        for h in paginas:
            try:
                out.append(F.ficha(d[h], doc_index))
            except Exception:
                out.append(F.Ficha(doc_index, h, (d[h].rect.width, d[h].rect.height)))
        return out
    finally:
        d.close()


def _fichas_en_paralelo(f: dict, d, doc_index: int, n_proc: int, aviso) -> list:
    """Las fichas de todas las hojas repartidas en `n_proc` procesos (cada hoja es
    independiente: mismo resultado que de a una). Con el archivo a mano, cada proceso lo abre;
    si no, recibe los bytes UNA vez por proceso."""
    import concurrent.futures as cf
    import multiprocessing as mp
    import os
    ruta = f.get("path")
    fuente = ruta if ruta and os.path.isfile(ruta) else f["data"]
    n = d.page_count
    paso = HOJAS_POR_ENCARGO if isinstance(fuente, str) else max(1, -(-n // n_proc))
    encargos = [list(range(k, min(n, k + paso))) for k in range(0, n, paso)]
    por_hoja: Dict[int, object] = {}
    with cf.ProcessPoolExecutor(max_workers=n_proc, mp_context=mp.get_context("spawn")) as ex:
        futuros = [ex.submit(_fichas_de, fuente, doc_index, e) for e in encargos]
        for fut in cf.as_completed(futuros):
            for fi in fut.result():
                por_hoja[fi.hoja] = fi
            aviso(len(por_hoja), n)
    return [por_hoja[h] for h in range(n)]


def analizar(fuentes: Sequence[dict], progreso=None) -> Optional[Resultado]:
    """`calcular` en el trabajador, con su caché, devolviendo el resultado liviano. Las hojas
    se leen en varios procesos a la vez (`proceso_hijo.paralelos`; las fichas pesan poco)."""
    from ui.comun import proceso_hijo
    n_proc = proceso_hijo.paralelos(proceso_hijo.MAX_PARALELOS, mb_por_trabajo=400)
    res = calcular(fuentes, (lambda e, i, n: progreso(e, i, n)) if progreso else None, None, _FICHAS,
                   paralelo=n_proc)
    if res is not None and res.analisis is not None:
        res.analisis.fichas = {k: dataclasses.replace(f, lineas=[]) for k, f in res.analisis.fichas.items()}             if isinstance(res.analisis.fichas, dict) else res.analisis.fichas
    return res
