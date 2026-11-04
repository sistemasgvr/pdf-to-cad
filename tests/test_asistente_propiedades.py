"""Elegir algo en el plano o en el Inventario cierra el Asistente y muestra sus propiedades (pedido 2026-11-04).
Lo que hace el propio Asistente (enlaces del chat, conflictos) mueve el plano sin cerrarlo."""
import pytest

from test_diametro_ia_ventana import _ventana


@pytest.fixture
def w():
    win = _ventana()
    win.mostrar_asistente(True, "chat")
    assert _en_asistente(win)
    return win


def _en_asistente(win):
    return win.pila_derecha.currentIndex() == 1 and win.btn_asistente.isChecked()


def _sobre_la_linea(win, i=0):
    (ax, ay), (bx, by) = win.pipes[i]["pts"][:2]
    return (ax + bx) / 2, (ay + by) / 2


def _clic(win, x, y):
    from PySide6 import QtCore
    win.on_click(x, y, QtCore.Qt.LeftButton)


def test_clic_en_una_linea_cierra_el_asistente_y_la_elige(w):
    _clic(w, *_sobre_la_linea(w, 1))
    assert not _en_asistente(w)
    assert w.pila_derecha.currentIndex() == 0 and w.sel_pipe == 1


def test_clic_en_la_linea_ya_elegida_tambien(w):
    _clic(w, *_sobre_la_linea(w))
    w.mostrar_asistente(True, "chat")
    _clic(w, *_sobre_la_linea(w))
    assert not _en_asistente(w)


def test_ctrl_clic_tambien(w, monkeypatch):
    from PySide6 import QtCore, QtWidgets
    monkeypatch.setattr(QtWidgets.QApplication, "keyboardModifiers", lambda: QtCore.Qt.ControlModifier)
    _clic(w, *_sobre_la_linea(w))
    assert not _en_asistente(w)


def test_clic_en_el_vacio_no_lo_cierra(w):
    _clic(w, 590.0, 5.0)
    assert _en_asistente(w)


def test_dibujando_no_lo_cierra(w):
    w.mode = "erase"
    _clic(w, *_sobre_la_linea(w))
    assert _en_asistente(w)


def test_clic_en_el_inventario_lo_cierra(w):
    w.pipe_list.itemClicked.emit(w.pipe_list.item(1))
    assert not _en_asistente(w)


def test_ir_a_un_aviso_desde_otra_vista_lo_cierra(w):
    x, y = _sobre_la_linea(w)
    w._ir_a_elemento(x, y, "pipe", 1)
    assert not _en_asistente(w) and w.sel_pipe == 1


@pytest.mark.parametrize("objeto,indice", [("pipe", 1), (None, -1)])
def test_lo_que_hace_el_asistente_no_lo_cierra(w, objeto, indice):
    x, y = _sobre_la_linea(w)
    w._ir_a_elemento(x, y, objeto, indice, activar=False)      # enlaces del chat y lista de conflictos
    assert _en_asistente(w)


def test_ir_a_un_lugar_sin_elemento_no_lo_cierra(w):
    w._ir_a_elemento(100.0, 100.0)                             # un conflicto: no hay propiedades que mostrar
    assert _en_asistente(w)


def test_la_conversacion_sigue_al_volver(w):
    chat = w._ia_chat
    _clic(w, *_sobre_la_linea(w))
    w.mostrar_asistente(True)
    assert w._ia_chat is chat and _en_asistente(w)


def test_con_la_ventana_a_la_vista_se_ven_los_campos_de_la_linea(w):
    from PySide6 import QtWidgets
    w.resize(1280, 800)
    w.show()
    app = QtWidgets.QApplication.instance()
    app.processEvents()
    assert not w.gprop.isVisible()
    _clic(w, *_sobre_la_linea(w, 1))
    app.processEvents()
    assert w.gprop.isVisible() and w.prop_name.isVisible()
    w.hide()
