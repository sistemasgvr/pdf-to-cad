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
    fin = time.time() + 60
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


def test_abrir_la_vista_3d_no_espera_al_calculo(win, monkeypatch):
    """Estrés 2026-11-18 (29 mil utilidades): abrir la 3D con el cálculo a medias rehacía el plano en la ventana
    (~20 s sin responder, ni al cierre). Ahora abre al instante y se pone al día cuando llegan los resultados."""
    from ui.dialogos import vista3d_dialog
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    abiertas = []
    monkeypatch.setattr(vista3d_dialog, "abrir", lambda w, **k: abiertas.append(w) or "dlg")
    _cargar(win, _azar(5, 90))
    win._redraw()
    assert win._provisional
    assert win.abrir_vista3d() == "dlg" and abiertas
    assert win._provisional                              # no calculó en la ventana
    _esperar(win)


def test_si_el_calculo_aparte_falla_se_reintenta_aparte(win, monkeypatch):
    """Un proceso del cálculo que muere no se recalcula en la ventana (la trababa ~20 s): se reintenta una vez
    aparte, con el mismo resultado."""
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    monkeypatch.setattr(calculo_fondo, "proceso_activo", lambda: True)
    real = calculo_fondo.calcular
    estado = {"fallar": True, "en_ventana": 0}

    def calcular(*a, **k):
        if estado["fallar"]:
            raise RuntimeError("el proceso murió")
        return real(*a, **k)
    monkeypatch.setattr(calculo_fondo, "calcular", calcular)
    reintentar = win._reintentar_calculo

    def _reintentar(calc=None):
        estado["fallar"] = False
        reintentar(calc)
    monkeypatch.setattr(win, "_reintentar_calculo", _reintentar)
    redraw = win._redraw

    def _redraw(*a, **k):
        estado["en_ventana"] += bool(getattr(win, "_forzar_sincronico", False))
        return redraw(*a, **k)
    monkeypatch.setattr(win, "_redraw", _redraw)
    _cargar(win, _azar(5, 90))
    win._redraw()
    assert win._provisional
    _esperar(win)
    assert not estado["fallar"] and estado["en_ventana"] == 0
    fondo = _foto(win)
    monkeypatch.setattr(win, "_redraw", redraw)
    assert fondo == _directo(win, monkeypatch)


def test_si_falla_con_el_modelo_ya_cambiado_se_calcula_el_de_ahora(win, monkeypatch):
    """Antes, un cálculo que fallaba cuando el modelo ya era otro no lanzaba ninguno nuevo: el plano quedaba
    provisional (sin conflictos ni avisos al día) hasta el próximo cambio."""
    from ui.ventana import calculo_fondo
    monkeypatch.setattr(calculo_fondo, "UMBRAL", 1)
    real = calculo_fondo.calcular
    estado = {"fallar": True}

    def calcular(*a, **k):
        if estado["fallar"]:
            raise RuntimeError("el proceso murió")
        return real(*a, **k)
    monkeypatch.setattr(calculo_fondo, "calcular", calcular)
    _cargar(win, _azar(5, 90))
    win._redraw()                                        # cálculo A (fallará)
    p = win.pipes[2]
    x, y = p["pts"][-1]
    p["pts"][-1] = (x + 11.0, y - 7.0)
    win._redraw()                                        # otro modelo mientras A sigue
    estado["fallar"] = False
    _esperar(win)
    fondo = _foto(win)
    assert fondo == _directo(win, monkeypatch)
