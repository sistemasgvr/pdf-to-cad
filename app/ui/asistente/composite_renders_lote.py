"""composite_renders_lote.py — las piezas del compositor dibujadas en VARIOS procesos antes de armar la vista.

`precargar(vista, piezas)` reparte las piezas que no están en la memoria de dibujos (`composite_renders`) entre unos
pocos procesos (`hoja/render_lote.dibujar`: la misma llamada a MuPDF que la ventana), espera con el bucle de eventos
VIVO (la capa «Cargando…» sigue pintando y avisando «i de n») y guarda cada imagen en `composite_renders` con la
misma clave, el mismo recorte y la misma máscara de polígono que `CompositeView._render_piece_raw`. Luego
`rebuild` sigue igual: encuentra cada pieza ya dibujada.

Solo con varias piezas que faltan (`MIN_PIEZAS`), con procesos (`ui.comun.proceso.activo`) y con los bytes del PDF a
mano (`composite_renders.marcar`). Si algo falla, no pasa nada: la vista las dibuja como siempre.
"""
from __future__ import annotations

import concurrent.futures as cf
import multiprocessing as mp

from PySide6 import QtCore, QtGui

from hoja import render_lote

MIN_PIEZAS = 4
MB_POR_PROCESO = 700
ESPERA_MS = 30

_grupo = {"ex": None, "n": 0}


def _ejecutor(n: int):
    """Grupo de procesos que se REUSA entre aperturas (arrancar uno cuesta ~1 s)."""
    from ui.comun import proceso_hijo
    ex = _grupo["ex"]
    if ex is not None and _grupo["n"] >= n:
        return ex
    if ex is not None:
        ex.shutdown(wait=False, cancel_futures=True)
    ex = cf.ProcessPoolExecutor(max_workers=n, mp_context=mp.get_context("spawn"),
                                initializer=proceso_hijo.morir_con_el_padre)
    _grupo.update(ex=ex, n=n)
    app = QtCore.QCoreApplication.instance()
    if app is not None and not getattr(app, "_pdfcad_lote_salida", False):
        app._pdfcad_lote_salida = True
        app.aboutToQuit.connect(soltar)
    return ex


def soltar() -> None:
    ex, _grupo["ex"] = _grupo["ex"], None
    if ex is not None:
        ex.shutdown(wait=False, cancel_futures=True)


def _imagen(w, h, stride, samples) -> QtGui.QPixmap:
    # lo mismo que `composite_view._qpixmap` con un `fitz.Pixmap`
    img = QtGui.QImage(samples, w, h, stride, QtGui.QImage.Format_RGB888).copy()
    return QtGui.QPixmap.fromImage(img)


def precargar(vista, piezas) -> int:
    """`piezas` = [(pieza, escala)]. Devuelve cuántas dejó en la memoria."""
    from hoja import composite as C
    from hoja import pdf_layers
    from nucleo import avance
    from traduccion.i18n_core import t as _tr
    from ui.asistente import composite_renders as CR
    from ui.comun import proceso, proceso_hijo
    if not proceso.activo():
        return 0
    faltan = []                                    # (pieza, escala, clave, recorte en pt, x0, y0)
    for p, escala in piezas:
        doc = vista.docs[p.source]
        k = CR.clave(doc, p, escala)
        if k is None or CR.buscar(k) is not None or getattr(doc, "_pdfcad_datos", None) is None:
            continue
        page = vista.page(p)
        x0, y0, x1, y1 = C.clip_rect_pt(vista.page_size(p), p.clip)
        r = (page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
        faltan.append((p, escala, k, r, x0, y0))
    if len(faltan) < MIN_PIEZAS:
        return 0
    n = proceso_hijo.paralelos(len(faltan), MB_POR_PROCESO)
    if n < 2:
        return 0
    try:
        ex = _ejecutor(n)
        # por documento, en `n` tandas (cada tanda manda los bytes del PDF una vez)
        por_doc: dict = {}
        for f in faltan:
            por_doc.setdefault(f[0].source, []).append(f)
        futuros = {}
        with proceso_hijo.con_hijos():
            for src, lista in por_doc.items():
                doc = vista.docs[src]
                datos, ons = doc._pdfcad_datos, pdf_layers.encendidas(doc)
                k_tandas = max(1, min(n, len(lista)))
                for j in range(k_tandas):
                    tanda = lista[j::k_tandas]
                    fut = ex.submit(render_lote.dibujar, datos, ons, [(f[0].page, f[1], f[3]) for f in tanda])
                    futuros[fut] = tanda
    except Exception:                              # noqa: BLE001 — sin procesos: la vista dibuja como siempre
        return 0
    texto = _tr("Dibujando cada hoja en la hoja compuesta…")
    hechas = 0
    pendientes = set(futuros)
    lazo = QtCore.QEventLoop()
    while pendientes:
        listos = {f for f in pendientes if f.done()}
        for fut in listos:
            pendientes.discard(fut)
            try:
                res = fut.result()
            except Exception:                      # noqa: BLE001 — esa tanda la dibuja la vista
                continue
            for (p, escala, k, _r, x0, y0), (w, h, stride, ox, oy, samples) in zip(futuros[fut], res):
                pm = vista.mask_polygon(_imagen(w, h, stride, samples), p, x0, y0, escala, origin=(ox, oy))
                CR.guardar(k, pm, (ox, oy))
                hechas += 1
        avance.avisar(texto, hechas, len(faltan))
        if pendientes:
            QtCore.QTimer.singleShot(ESPERA_MS, lazo.quit)
            lazo.exec(QtCore.QEventLoop.ExcludeUserInputEvents)
    return hechas

