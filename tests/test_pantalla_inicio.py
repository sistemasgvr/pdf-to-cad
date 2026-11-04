"""Pantalla de inicio sobre el lienzo vacío (pedido del usuario 2026-11-03): Nuevo lienzo, Abrir PDF, Abrir
proyecto y los recientes; se oculta en cuanto hay una hoja."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.resize(1300, 800)
    w.show()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_se_ve_sin_hoja_y_se_oculta_con_hoja(win):
    from PySide6 import QtGui, QtWidgets
    win._inicio_al_dia()
    assert win.pantalla_inicio.isVisible()
    img = QtGui.QImage(200, 100, QtGui.QImage.Format_RGB32)
    img.fill(0xFFFFFF)
    win.canvas.set_image(img)
    win._inicio_al_dia()
    assert not win.pantalla_inicio.isVisible()
    QtWidgets.QApplication.processEvents()


def test_tarjetas_llaman_a_las_acciones_de_siempre(win, monkeypatch):
    llamadas = []
    for nombre in ("new_blank_canvas", "open_pdf", "open_project"):
        monkeypatch.setattr(win, nombre, lambda n=nombre: llamadas.append(n))
    from ui.ventana.ventana_inicio import PantallaInicio
    p = PantallaInicio(win, win.canvas)
    for tj in p.tarjetas:
        tj.click()
    assert llamadas == ["new_blank_canvas", "open_pdf", "open_project"]


def test_recientes_abre_el_proyecto(win, monkeypatch, tmp_path):
    from ui.ventana import ventana_recientes as R
    from ui.ventana.ventana_inicio import _FilaReciente
    f = tmp_path / "obra.digproj"
    f.write_bytes(b"x")
    R.anotar(str(f))
    abiertos = []
    monkeypatch.setattr(win, "_open_project_path", lambda p: abiertos.append(p))
    p = win.pantalla_inicio
    p.refrescar(forzar=True)
    filas = [p.lista.itemAt(i).widget() for i in range(p.lista.count())]
    filas = [w for w in filas if isinstance(w, _FilaReciente)]
    assert len(filas) == 1
    filas[0].click()
    assert abiertos == [os.path.abspath(str(f))]
