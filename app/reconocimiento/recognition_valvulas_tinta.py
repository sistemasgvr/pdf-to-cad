"""¿Se ve el glifo de una válvula en la hoja? (lo usa `recognition_valvulas._de_imagen`).

Cada pregunta dibuja SU recuadro a 10× (`DisplayList.get_pixmap(clip=)`) y busca un píxel del color del glifo. En una
hoja compuesta grande (Southwest Gas, 54 hojas: 1 575 glifos) cada dibujo cuesta ~20 ms aunque el recuadro sea chico:
MuPDF recorre la lista de dibujo entera (~9 ms) y traza enteras las calles y tuberías que pasan por él. Dibujar un
recuadro mayor y recortarlo NO da los mismos píxeles (el recorte cambia qué objetos entran y el suavizado del borde),
así que el dibujo de cada glifo es el de siempre y lo que cambia es DÓNDE: con muchos glifos se reparten entre varios
procesos (cada uno abre la hoja con las mismas capas encendidas). Mismas llamadas, mismos píxeles, mismo resultado.
El proceso hijo solo importa fitz, `hoja.pdf_layers` y `ui.comun.proceso_hijo` (sin Qt), no el reconocimiento.
"""
from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

import fitz

ZOOM = 10                    # px por pt del dibujo de cada glifo
TINTA_TOL = 150              # suma de diferencias RGB: el suavizado del borde aclara el color del glifo
PARALELO_MIN = 200           # con menos glifos, arrancar los procesos tarda más que dibujarlos aquí
MB_POR_PROCESO = 700         # la hoja compuesta de Southwest abierta con su lista de dibujo: ~400–500 MB

Pedido = Tuple[Tuple[float, float, float, float], Tuple[int, int, int]]     # (recuadro sin girar, color RGB 0–255)


def rgb_de(color) -> Tuple[int, int, int]:
    """El color del glifo (0–1, como lo da `get_texttrace`) en 0–255; sin color RGB, negro."""
    color = tuple(color or ())
    return tuple(int(round(c * 255)) for c in (color + (0, 0, 0))[:3]) if len(color) == 3 else (0, 0, 0)


def hay_tinta(lista, recuadro, rgb) -> bool:
    """Lo de siempre: el recuadro dibujado a `ZOOM` tiene un píxel a < `TINTA_TOL` del color."""
    pix = lista.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=fitz.Rect(*recuadro), alpha=False)
    px = pix.samples
    n = pix.n
    return any(abs(px[i] - rgb[0]) + abs(px[i + 1] - rgb[1]) + abs(px[i + 2] - rgb[2]) < TINTA_TOL
               for i in range(0, len(px) - n + 1, n))


def _lote(ruta: str, hoja: int, encendidas, pedidos: Sequence[Pedido]) -> List[bool]:
    """En el proceso hijo: la misma hoja con las mismas capas, cada pedido dibujado igual que aquí."""
    from hoja import pdf_layers
    with fitz.open(ruta) as doc:
        pdf_layers.poner_encendidas(doc, encendidas)
        lista = doc[hoja].get_displaylist()
        return [hay_tinta(lista, r, c) for r, c in pedidos]


def _procesos(n: int) -> int:
    if n < PARALELO_MIN or os.environ.get("PDFCAD_PROCESO", "1") == "0":
        return 1
    try:
        from ui.comun import proceso_hijo                  # (sin Qt: solo cuenta núcleos y RAM)
        return proceso_hijo.paralelos(proceso_hijo.MAX_PARALELOS, mb_por_trabajo=MB_POR_PROCESO)
    except Exception:
        return 1


def se_ven(page, lista, pedidos: Sequence[Pedido]) -> List[bool]:
    """`hay_tinta` de cada pedido, en orden. Si `adelantar` ya lanzó ESTOS mismos pedidos de esta hoja, sus
    respuestas; si no, con muchos y la hoja en un archivo, en varios procesos; si algo falla (memoria, permisos),
    aquí mismo. `lista` = la lista de dibujo de la hoja (None: se arma si hace falta)."""
    pedidos = list(pedidos)
    hecho = _recoger(page, pedidos)
    if hecho is not None:
        return hecho
    n_proc = _procesos(len(pedidos))
    ruta = getattr(page.parent, "name", "") or ""
    if n_proc > 1 and os.path.isfile(ruta):
        try:
            return _en_procesos(page, ruta, pedidos, n_proc)
        except Exception:
            pass
    if lista is None:
        lista = page.get_displaylist()
    return [hay_tinta(lista, r, c) for r, c in pedidos]


class _Lanzados:
    """Los dibujos repartidos en procesos, todavía corriendo."""

    def __init__(self, ex, futuros, n):
        self.ex, self.futuros, self.n = ex, futuros, n


def _lanzar(page, ruta: str, pedidos: List[Pedido], n_proc: int) -> _Lanzados:
    import concurrent.futures as cf
    import multiprocessing as mp
    from hoja import pdf_layers
    from ui.comun import proceso_hijo                  # (sin Qt)
    encendidas = pdf_layers.encendidas(page.parent)
    partes = [list(range(k, len(pedidos), n_proc)) for k in range(n_proc)]      # mezclados: cargas parecidas
    # (el reconocimiento corre en el trabajador de la app, que es «daemon»: `con_hijos` le deja lanzar el grupo)
    with proceso_hijo.con_hijos():
        ex = cf.ProcessPoolExecutor(max_workers=n_proc, mp_context=mp.get_context("spawn"),
                                    initializer=proceso_hijo.morir_con_el_padre)
        try:
            futuros = {ex.submit(_lote, ruta, page.number, encendidas, [pedidos[i] for i in idx]): idx
                       for idx in partes}
        except Exception:
            ex.shutdown(wait=False, cancel_futures=True)
            raise
    return _Lanzados(ex, futuros, len(pedidos))


def _esperar(lanzados: _Lanzados) -> List[bool]:
    import concurrent.futures as cf
    try:
        out: List[bool] = [False] * lanzados.n
        for fut in cf.as_completed(lanzados.futuros):
            for i, r in zip(lanzados.futuros[fut], fut.result()):
                out[i] = r
        return out
    finally:
        lanzados.ex.shutdown(wait=True, cancel_futures=True)


def _en_procesos(page, ruta: str, pedidos: List[Pedido], n_proc: int) -> List[bool]:
    return _esperar(_lanzar(page, ruta, pedidos, n_proc))


_ADELANTADOS = "_pdfcad_valvulas_tinta"      # en el documento: {hoja: (pedidos, _Lanzados)}


def adelantar(page, pedidos: Sequence[Pedido]) -> None:
    """Lanza ya los dibujos de `pedidos` en otros procesos (si irían en procesos: muchos, hoja en un archivo) y
    los deja en el documento para que `se_ven` con los MISMOS pedidos los recoja. Nunca falla."""
    pedidos = list(pedidos)
    try:
        n_proc = _procesos(len(pedidos))
        ruta = getattr(page.parent, "name", "") or ""
        if n_proc > 1 and os.path.isfile(ruta):
            page.parent.__dict__.setdefault(_ADELANTADOS, {})[page.number] = (
                pedidos, _lanzar(page, ruta, pedidos, n_proc))
    except Exception:                                  # noqa: BLE001
        pass


def _recoger(page, pedidos) -> Optional[List[bool]]:
    hechos = page.parent.__dict__.get(_ADELANTADOS) or {}
    par = hechos.pop(page.number, None)
    if par is None:
        return None
    suyos, lanzados = par
    if suyos != pedidos:                               # otra pregunta: lo lanzado no sirve
        lanzados.ex.shutdown(wait=False, cancel_futures=True)
        return None
    try:
        return _esperar(lanzados)
    except Exception:                                  # noqa: BLE001
        return None


def soltar(doc) -> None:
    """Termina lo que `adelantar` lanzó y nadie recogió (el reconocimiento falló o la hoja no lo pidió)."""
    for _pedidos, lanzados in (doc.__dict__.pop(_ADELANTADOS, None) or {}).values():
        lanzados.ex.shutdown(wait=False, cancel_futures=True)
