"""Una utilidad a medio dibujar no se pierde (reporte del usuario 2026-11-09: dibujó sobre un escaneo continuando
una tubería reconocida, guardó y abrió la Vista 3D con la línea aún EN CURSO —sin Enter— y no estaba en ningún lado).
Guardar, la Vista 3D, exportar y cambiar de herramienta la terminan como Enter; Esc la sigue cancelando."""
import json
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6 import QtCore, QtGui, QtWidgets

L = QtCore.Qt.LeftButton


@pytest.fixture
def win(monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Yes)
    from ui.ventana.app_window import Main
    w = Main()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    w.pipes = [{"layer": "AGUA", "pts": [(100.0, 100.0), (600.0, 100.0)], "diam": 8.0, "diam_elegido": True}]
    w._refresh_lists(); w._redraw()
    yield w
    dlg = getattr(w, "_vista3d_dlg", None)
    if dlg is not None:
        dlg.close()
    w._dirty = False
    w.close()


def _dibujar(w, puntos, extender=False):
    w.chk_ext_same.setChecked(extender)
    w.set_mode("pipe")
    for x, y in puntos:
        w.on_click(x, y, L)


def test_guardar_termina_la_linea_en_curso(win, tmp_path):
    _dibujar(win, [(100, 400), (600, 400), (600, 900)])
    assert len(win.pipes) == 1 and len(win.cur_pts) == 3          # aún en curso
    ruta = str(tmp_path / "p.digproj")
    win._write_project(ruta)
    m = json.loads(zipfile.ZipFile(ruta).read("model.json"))
    assert len(m["pipes"]) == 2 and len(m["pipes"][1]["pts"]) == 3 and not win.cur_pts


def test_extender_y_guardar_sin_enter_queda_en_la_misma_utilidad(win, tmp_path):
    _dibujar(win, [(600, 100), (1000, 100), (1000, 500)], extender=True)  # 1.er clic en la punta
    assert win._extending and win._ext_pipe == 0
    ruta = str(tmp_path / "p.digproj")
    win._write_project(ruta)
    m = json.loads(zipfile.ZipFile(ruta).read("model.json"))
    assert len(m["pipes"]) == 1 and len(m["pipes"][0]["pts"]) == 4


def test_vista3d_incluye_la_linea_en_curso(win):
    import time
    _dibujar(win, [(100, 400), (600, 400)])
    dlg = win.abrir_vista3d()
    t = time.time()
    while (dlg._trabajo is not None or dlg._t.isActive()) and time.time() - t < 30:
        QtWidgets.QApplication.processEvents(); time.sleep(0.01)
    assert len(win.pipes) == 2 and dlg.escena.cuentas["utilidades"] == 2


def test_cambiar_de_herramienta_termina_la_linea(win):
    _dibujar(win, [(100, 400), (600, 400)], extender=False)
    win.set_mode("idle")
    assert len(win.pipes) == 2 and not win.cur_pts
    _dibujar(win, [(100, 700)])                                     # un solo punto no es línea: se suelta
    win.set_mode("idle")
    assert len(win.pipes) == 2 and not win.cur_pts


def test_esc_sigue_cancelando(win, tmp_path):
    _dibujar(win, [(100, 400), (600, 400)])
    win._on_escape()
    win.set_mode("idle")
    assert len(win.pipes) == 1 and not win.cur_pts
