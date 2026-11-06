"""Inventario → «Accesorios» (pedido del usuario 2026-11-05): lista de codos, Tees, Wyes, cruces y válvulas con
filtro por tipo; clic = ir al plano; clic derecho = «No hay …» / menú de la válvula."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _agua(pts, diam=8.0, **k):
    return dict(layer="AGUA", pts=list(pts), name="", diam=diam, pipe_size="x", inv_start=-4.0, inv_end=-4.0, **k)


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w.aviso_breve = lambda *a, **k: None
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0              # 0.1 ft por px
    # una L (codo en 900,300) y un ramal que nace a mitad del primer tramo (Tee en 400,300)
    w.pipes = [_agua([(100, 300), (900, 300), (900, 800)]), _agua([(400, 300), (400, 900)], diam=6.0)]
    w._refresh_lists(); w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _visibles(w):
    return [w.acc_list.item(i).text() for i in range(w.acc_list.count()) if not w.acc_list.item(i).isHidden()]


def test_lista_filtro_y_seleccion(win):
    from nucleo.model import TAB_ACC
    assert win.acc_list.count() == 0                       # sin la sección a la vista no se arma
    win._show_tab(TAB_ACC)
    assert win._current_tab() == TAB_ACC
    textos = _visibles(win)
    assert len(textos) == 2 and textos[0].startswith("Codo 90°") and textos[1].startswith("Tee")
    assert '8" × 6"' in textos[1] and "#1 #2" in textos[1]
    win._do_insert_valvula(250, 302)
    textos = _visibles(win)
    assert len(textos) == 3 and textos[2].startswith('Válvula 8"')
    chips = {clave: b for b, clave, _t in win._chips_acc}
    assert chips["valvula"].text() == "Válvulas (1)" and chips[""].text() == "Todos (3)"
    chips["tee"].click()
    assert [t.split(" ")[0] for t in _visibles(win)] == ["Tee"]
    chips["valvula"].click()
    assert [t.split(" ")[0] for t in _visibles(win)] == ["Válvula"]
    chips[""].click()
    win.acc_list.setCurrentRow(0)                          # → el plano va al codo y lo marca
    sc, it, _r = win._marca_lugar
    assert (it.pos().x(), it.pos().y()) == pytest.approx((900, 300), abs=1)
    assert "Codo" in win.lbl_acc_info.text()


def test_no_hay_accesorio_y_quitar_valvulas_desde_la_lista(win):
    from nucleo.model import TAB_ACC
    win._do_insert_valvula(250, 302)
    win._show_tab(TAB_ACC)
    filas = win._acc_filas
    pasos = len(win._undo)
    assert win.marcar_sin_accesorios([f.dato for f in filas if f.clase == "acc"])
    assert len(win._undo) == pasos + 1
    assert [f.tipo for f in win._acc_filas] == ["valvula"]
    assert win.quitar_valvulas([0]) and win.valvulas == [] and win.acc_list.count() == 0
    win.undo(); win.undo()
    assert [f.tipo for f in win._acc_filas] == ["codo", "tee", "valvula"]
