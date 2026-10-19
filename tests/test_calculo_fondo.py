"""Cálculo de conflictos y avisos en SEGUNDO PLANO (`ui/ventana/calculo_fondo`, 2026-10-19): con un modelo
grande el redibujo tras un cambio es provisional y un hilo calcula sobre una copia con los MISMOS métodos y
claves de `_memo` en un proceso aparte (en las pruebas, un hilo). Al terminar, el plano queda IGUAL que calculándolo en el redibujo."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_rendimiento_plano import _azar, _cargar, _estrellas, _foto, win  # noqa: E402,F401


def _esperar(win):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    fin = time.time() + 120
    while getattr(win, "_provisional", False) and time.time() < fin:
        time.sleep(0.02)                                 # el trabajador (aquí un hilo: PDFCAD_PROCESO=0)
        app.processEvents()
    assert not win._provisional


def _directo(win, monkeypatch):
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 10 ** 9)
    win._memo_redibujo = None
    win._marcas = None
    r = _foto(win)
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    return r


def test_en_segundo_plano_da_lo_mismo(win, monkeypatch):
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    tol = 0.5 / win.scale * win.zoom
    _cargar(win, _azar(5, 90) + _estrellas(3, tol)[:80])
    win._redraw()
    assert win._provisional and win._conflict_hits == [] and win._normas_avisos == []
    _esperar(win)
    fondo = _foto(win)
    assert fondo["_conflict_hits"] and fondo["accesorios"] and fondo["avisos"]
    assert fondo == _directo(win, monkeypatch)


def test_cambios_seguidos_se_queda_con_el_ultimo(win, monkeypatch):
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    _cargar(win, _azar(9, 120))
    win._redraw()
    for k in range(3):                                   # cambios mientras el hilo trabaja
        p = win.pipes[k + 2]
        x, y = p["pts"][-1]
        p["pts"][-1] = (x + 17.0 * (k + 1), y - 9.0)
        p["inv_start"] = -4.0 - k
        win._redraw()
    _esperar(win)
    fondo = _foto(win)
    assert fondo == _directo(win, monkeypatch)


def test_quien_los_necesita_espera(win, monkeypatch):
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    _cargar(win, _azar(4, 80))
    win._redraw()
    assert win._provisional
    tablas = win._tablas_de_datos()                      # espera al hilo y redibuja
    assert not win._provisional and win._accesorios is not None
    ref = _directo(win, monkeypatch)
    assert [(a.clase, a.x, a.y) for a in win._normas_avisos] == [(a[0], a[3], a[4]) for a in ref["avisos"]]
    assert tablas is not None


def test_sin_marcas_previas_al_terminar_aparecen_todas(win, monkeypatch):
    """Como al abrir un proyecto: no hay marcas de antes que dejar a la vista."""
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    _cargar(win, _azar(6, 90))
    win._marcas = None
    win._redraw()
    assert win._provisional
    _esperar(win)
    fondo = _foto(win)
    assert fondo["items"] and fondo == _directo(win, monkeypatch)
