"""Vista 3D: Esc quita la selección hecha en 3D (el foco se queda en la ventana 3D) y el panel «Editar»
cambia cotas por tramo, rasantes y diámetro con los mismos datos que el plano (pedido del usuario
2026-10-20)."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtCore, QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    monkeypatch.setattr("ui.dialogos.vista3d_dialog._ajustes",
                        lambda: QtCore.QSettings(os.path.join(os.environ["PDFCAD_RECUPERACION"], "v3d.ini"),
                                                 QtCore.QSettings.IniFormat))
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    w.pipes = [dict(layer="AGUA", pts=[(100, 100), (400, 100), (600, 300)], name="", diam=8.0, pipe_size="",
                    inv_start=-4.0, inv_end=-6.0),
               dict(layer="GAS", pts=[(100, 500), (600, 500)], name="", diam=6.0, pipe_size="",
                    inv_start=-3.0, inv_end=-3.0)]
    w._refresh_lists(); w._redraw()
    yield w
    dlg = getattr(w, "_vista3d_dlg", None)
    if dlg is not None:
        dlg.close()
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _abrir(win):
    from PySide6 import QtWidgets
    dlg = win.abrir_vista3d()
    t = time.time()
    while (dlg._trabajo is not None or dlg._t.isActive()) and time.time() - t < 20:
        QtWidgets.QApplication.processEvents(); time.sleep(0.01)
    QtWidgets.QApplication.processEvents()
    return dlg


def test_elegir_en_3d_no_trae_la_ventana_principal_y_esc_quita_la_seleccion(win, monkeypatch):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest
    dlg = _abrir(win)
    activada = []
    monkeypatch.setattr(win, "activateWindow", lambda: activada.append(1))
    dlg._elegido(1)
    assert win.sel_pipe == 0 and dlg.visor.sel_id == 1 and not activada     # elegida en el plano, sin robar el foco
    dlg.visor.setFocus()
    QTest.keyClick(dlg.visor, QtCore.Qt.Key_Escape)
    assert dlg.visor.sel_id == 0 and win.sel_pipe == -1 and not dlg.editor.isVisible()
    dlg._elegido(1)
    dlg._ficha_al_plano()                                                  # «Ver en el plano» sí la trae
    assert activada


def test_editar_cotas_y_diametro_desde_3d_llega_al_plano_y_se_deshace(win):
    dlg = _abrir(win)
    dlg._elegido(1)
    ed = dlg.editor
    assert not ed.isVisible()                      # 2.0.0: «Ficha | Editar», arranca en la ficha
    dlg.mostrar_editor()
    assert ed.isVisible() and ed.tabla.rowCount() == 2 and ed.cmb_diam.isEnabled()
    p = win.pipes[0]
    # fin de T1 (vértice intermedio): queda la edición por tramo activada, como el botón del plano
    sp = ed.tabla.cellWidget(0, 2)
    antes = sp.value()
    sp.stepBy(5)
    assert ed.tabla.item(0, 3).text() != "" and p.get("vertex_inv_in") in (None, {})   # pendiente al instante
    assert ed.aplicar() == 1
    assert p["vertex_inv_in"][1] == pytest.approx(antes + 0.5) and p["seg_edit_enabled"]
    assert win.tbl_seg_inv.cellWidget(0, 2).value() == pytest.approx(antes + 0.5)
    pasos = len(win._undo)
    # rasante inicial = inicio de T1 (y el spinbox del panel del plano)
    ed.tabla.cellWidget(0, 1).setValue(-3.5)
    ed.aplicar()
    assert p["inv_start"] == pytest.approx(-3.5) and win.prop_inv0.value() == pytest.approx(-3.5)
    assert len(win._undo) == pasos + 1                                     # un paso de deshacer por cambio
    # diámetro por el desplegable del panel: mismo efecto
    from PySide6.QtTest import QTest
    ed.cmb_diam.setCurrentIndex(ed.cmb_diam.findText('12"'))
    assert p["diam"] == pytest.approx(8.0)                                # primero la vista previa en 3D…
    QTest.qWait(120)                                                      # …y enseguida el cambio real
    assert p["diam"] == pytest.approx(12.0) and p.get("diam_elegido") and win.prop_size.currentText() == '12"'
    win.undo()
    assert win.pipes[0]["diam"] == pytest.approx(8.0)
    win.undo()
    assert win.pipes[0]["inv_start"] == pytest.approx(-4.0)


def test_el_editor_sigue_lo_que_cambia_en_el_plano(win):
    dlg = _abrir(win)
    dlg._elegido(2)
    win._push(); win.pipes[1]["inv_end"] = -7.25; win._redraw()
    dlg.actualizar(forzar=True)
    _abrir(win)
    assert dlg.editor.tabla.cellWidget(0, 2).value() == pytest.approx(-7.25)


def test_vista_previa_al_instante_y_cambio_real_al_soltar(win):
    """Cada ↑ se ve YA en la 3D (parche local sobre una copia: el proyecto no cambia todavía); al soltar, el
    cambio real en UN paso de deshacer aunque se hayan tocado dos cotas."""
    dlg = _abrir(win)
    dlg._elegido(1)
    ed, p = dlg.editor, win.pipes[0]
    esc0, pasos = dlg.escena, len(win._undo)
    ed.tabla.cellWidget(0, 1).stepBy(3)
    ed.tabla.cellWidget(1, 2).stepBy(-2)
    assert ed._previa()
    assert dlg.escena is not esc0 and p["inv_start"] == pytest.approx(-4.0) and len(win._undo) == pasos
    o = dlg.escena.objetos[1]
    assert o["z0"] == pytest.approx(-3.7)                                   # la 3D ya muestra la cota nueva
    assert ed.aplicar() == 2
    assert p["inv_start"] == pytest.approx(-3.7) and p["inv_end"] == pytest.approx(-6.2)
    assert len(win._undo) == pasos + 1


def test_el_armado_completo_espera_al_plano_y_cancela_el_anterior(win, monkeypatch):
    from ui.comun import proceso
    dlg = _abrir(win)
    enviadas = []
    monkeypatch.setattr(proceso.Trabajador, "enviar", lambda self, t: enviadas.append(t) or t)
    win._provisional = True                                                # el plano aún calcula avisos
    win.pipes[0]["inv_end"] = -9.0
    dlg.actualizar()
    assert not enviadas and dlg._t.isActive()
    win._provisional = False
    dlg.actualizar()
    assert len(enviadas) == 1 and dlg._trabajo is enviadas[0]
    canceladas = []
    monkeypatch.setattr(enviadas[0], "cancelar", lambda: canceladas.append(1))
    win.pipes[0]["inv_end"] = -9.5
    dlg.actualizar()
    assert canceladas and len(enviadas) == 2
    dlg._t.stop(); dlg._trabajo = None
