"""encaje_imagen_lote.py — `calcado_completar._por_imagen` repartido en procesos, con el MISMO resultado.

Reporte 2026-11-21 (vigilante del usuario, «Agregar utilidad» SD North + South sobre agua + alcantarillado):
«Buscando hojas que caen entre las del editor…» tardaba 106 s en UN proceso. Cada hoja nueva se dibuja y se
correlaciona con la hoja del editor (`encaje_imagen`), y una vez que la primera hoja de un PDF dio la escala y la
referencia de su celda, las demás ya no dependen unas de otras (solo de esa escala y de esa referencia): se reparten
en procesos y se toman EN ORDEN. Cada proceso abre los MISMOS bytes de cada PDF y recibe el lienzo del editor ya
dibujado: hace las mismas cuentas que se harían aquí, de a una. La celda de cada hoja (`composicion_ficha.ficha`,
~0.2 s por hoja) también se lee allá, por adelantado.

Sin los bytes de algún PDF (un documento armado en memoria), con pocas hojas o sin memoria para más de un proceso,
`crear` devuelve None y todo sigue de a una, aquí mismo. Si un proceso falla, esa hoja se calcula aquí.
PURO: fitz, numpy, OpenCV (los procesos, `concurrent.futures`).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

MB_POR_PROCESO = 900        # medido: ~?? MB por proceso (PDF abiertos, listas de dibujo, imágenes de la hoja)
MIN_HOJAS = 4               # con menos hojas no compensa lanzar procesos
PARALELO = True             # False = todo de a una, aquí (para comparar)

_EST: Dict[str, object] = {}  # lo de cada proceso del grupo (lo arma `_iniciar`)


def bytes_de(doc) -> Optional[bytes]:
    """Los bytes con que se abrió el PDF (o los de su archivo), para abrirlo igual en otro proceso."""
    b = getattr(doc, "stream", None)
    if b is not None:
        return bytes(b)
    nombre = getattr(doc, "name", "") or ""
    if nombre and os.path.isfile(nombre):
        with open(nombre, "rb") as f:
            return f.read()
    return None


# ─────────────────────────── en cada proceso del grupo ───────────────────────────
def _iniciar(editor: Sequence[Optional[bytes]], nuevas: Sequence[bytes], spec, img, r, origen, zona):
    from ui.comun import proceso_hijo
    proceso_hijo.morir_con_el_padre()
    import fitz
    from hoja import encaje_imagen as EI
    de = [fitz.open(stream=b, filetype="pdf") if b is not None else None for b in editor]
    dn = [fitz.open(stream=b, filetype="pdf") for b in nuevas]
    piezas = [(de[s][h], fitz.Rect(*clip), tuple(caja)) for s, h, clip, caja in spec]
    _EST.update(de=de, dn=dn, lz=EI.Lienzo.armado(piezas, img, r, origen, zona))


def ubicar_hoja(lz, page, previsto, escalas, z_min, zona):
    """Lo que hace `_por_imagen` con UNA hoja cuando la escala y la referencia ya no cambian: donde se prevé
    (`ubicar_cerca`) y, si ahí no está, buscarla con la escala conocida. → ((s, tx, ty, z, dominio), área útil) o None."""
    from hoja import calcado_completar as CC
    from hoja import encaje_imagen as EI
    u = EI.ubicar_cerca(lz, page, previsto) if previsto is not None else None
    if u is None:
        u = EI.ubicar(lz, page, escalas, z_min=z_min, zona=zona)
    if u is None:
        return None
    return (u.s, u.tx, u.ty, u.z, u.dominio), CC.area_util(page)


def _ubicar(f: int, h: int, previsto, escalas, z_min, zona):
    return ubicar_hoja(_EST["lz"], _EST["dn"][f][h], previsto, escalas, z_min, zona)


def _celda(f: int, h: int):
    from hoja import calcado_completar as CC
    return CC.celda_hoja(_EST["dn"][f][h])


# ─────────────────────────── aquí ───────────────────────────
class Lote:
    """El grupo de procesos de un `completar` (se lanza al primer encargo; `cerrar` al terminar)."""

    def __init__(self, n_proc: int, args):
        self.n_proc = n_proc
        self._args = args
        self._ex = None
        self._celdas: Dict[tuple, object] = {}

    def _enviar(self, fn, *args):
        """El encargo (un `Future`), o None si el grupo no pudo recibirlo (quien espera lo calcula aquí)."""
        import concurrent.futures as cf
        import multiprocessing as mp
        from ui.comun import proceso_hijo
        try:
            with proceso_hijo.con_hijos():           # (el trabajador «agregar» es «daemon»)
                if self._ex is None:
                    self._ex = cf.ProcessPoolExecutor(max_workers=self.n_proc, mp_context=mp.get_context("spawn"),
                                                      initializer=_iniciar, initargs=self._args)
                return self._ex.submit(fn, *args)
        except Exception:
            return None

    def adelantar_celdas(self, f: int, hojas: Sequence[int]):
        for h in hojas:
            if (f, h) not in self._celdas:
                self._celdas[(f, h)] = self._enviar(_celda, f, h)

    def celdas(self, f: int, hojas: Sequence[int], doc) -> Dict[int, object]:
        """{hoja: celda} (la de cada proceso; si alguno falló, la de aquí: es la misma cuenta)."""
        from hoja import calcado_completar as CC
        self.adelantar_celdas(f, hojas)
        out = {}
        for h in hojas:
            fut = self._celdas.pop((f, h), None)
            try:
                out[h] = fut.result()
            except Exception:                        # (sin encargo o un proceso que se cayó)
                out[h] = CC.celda_hoja(doc[h])
        return out

    def ubicar(self, f: int, h: int, pedido):
        return self._enviar(_ubicar, f, h, *pedido)

    @staticmethod
    def resultado(futuro, lz, page, pedido):
        try:
            return futuro.result()
        except Exception:                            # (sin encargo o un proceso que se cayó: la misma cuenta aquí)
            return ubicar_hoja(lz, page, *pedido)

    def cerrar(self):
        if self._ex is not None:
            self._ex.shutdown(wait=False, cancel_futures=True)
            self._ex = None


def crear(lz, fuentes_lz: Sequence[tuple], docs_editor, docs_nuevos, n_hojas: int) -> Optional[Lote]:
    """El lote para ubicar `n_hojas` hojas por imagen, o None (de a una, aquí). `fuentes_lz` = (fuente del editor,
    hoja) de cada pieza del lienzo, en su orden."""
    if not PARALELO or lz is None or n_hojas < MIN_HOJAS:
        return None
    try:
        from ui.comun import proceso_hijo
        n_proc = proceso_hijo.paralelos(n_hojas, MB_POR_PROCESO)
    except Exception:
        return None
    if n_proc < 2:
        return None
    usadas = sorted({s for s, _h in fuentes_lz})
    editor: List[Optional[bytes]] = [None] * len(docs_editor)
    for s in usadas:
        editor[s] = bytes_de(docs_editor[s])
        if editor[s] is None:
            return None
    nuevas = [bytes_de(d) for d in docs_nuevos]
    if any(b is None for b in nuevas):
        return None
    spec = [(s, h, (clip.x0, clip.y0, clip.x1, clip.y1), tuple(caja))
            for (s, h), (_page, clip, caja) in zip(fuentes_lz, lz.piezas)]
    return Lote(n_proc, (editor, nuevas, spec, lz.img, lz.r, lz.origen, lz.zona))
