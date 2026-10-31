"""Vista 3D → «Resolver» un conflicto C-n (pedido del usuario 2026-10-30): las propuestas probadas por la app, la
sugerida (IA si está; si no, la de la app), vista previa en 3D sin tocar el proyecto, «Aplicar» en un paso de
deshacer y ◀ ▶ entre los pendientes."""
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
    w._config_ia = lambda: {"proveedor": "ninguno"}          # sin IA: sugiere la app
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    # dos cruces a la MISMA cota (agua × gas): dos conflictos C-n
    w.pipes = [dict(layer="AGUA", pts=[(100, 300), (900, 300)], name="", diam=8.0, pipe_size="",
                    inv_start=-4.0, inv_end=-4.0),
               dict(layer="GAS", pts=[(300, 100), (300, 600)], name="", diam=6.0, pipe_size="",
                    inv_start=-4.0, inv_end=-4.0),
               dict(layer="GAS", pts=[(700, 100), (700, 600)], name="", diam=6.0, pipe_size="",
                    inv_start=-4.0, inv_end=-4.0)]
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


def test_resolver_un_conflicto_desde_3d(win):
    ids = [c.id for c in win._conflictos]
    assert len(ids) >= 2
    dlg = _abrir(win)
    assert dlg.ir_a_conflicto(ids[0])
    r = dlg.resolver
    assert dlg._caja_resolver.isVisibleTo(dlg) and r.cid == ids[0]
    assert r._props and r._elegida and r._rec                       # sugerida (la de la app, sin IA)
    assert r.lbl_pos.text().startswith("1 ")
    p = r._propuesta()
    z0 = win._pipe_z_at(p.pipe, 0, *win.pipes[p.pipe]["pts"][0])
    assert r._previa == p.pipe                                       # se ve en 3D…
    assert win._pipe_z_at(p.pipe, 0, *win.pipes[p.pipe]["pts"][0]) == z0   # …y el proyecto no cambió
    pasos = len(win._undo)
    r.aplicar()
    assert len(win._undo) == pasos + 1 and r._previa is None
    assert win._pipe_z_at(p.pipe, 0, *win.pipes[p.pipe]["pts"][0]) != z0
    assert "resuelto" in r.lbl_estado.text()
    win.undo()
    assert win._pipe_z_at(p.pipe, 0, *win.pipes[p.pipe]["pts"][0]) == pytest.approx(z0)


def test_siguiente_y_soltar_la_vista_previa(win):
    ids = [c.id for c in win._conflictos]
    dlg = _abrir(win)
    dlg.ir_a_conflicto(ids[0])
    r = dlg.resolver
    r.mover(1)
    assert r.cid == ids[1]
    dlg.deseleccionar()                                              # Esc: sin selección, sin vista previa
    assert r._previa is None and not dlg._caja_resolver.isVisibleTo(dlg)


def test_con_ia_ella_marca_la_alternativa_sugerida(win):
    from PySide6 import QtWidgets
    from ollama_falso import OllamaFalso
    ids = [c.id for c in win._conflictos]
    pedido = {}

    def responder(c):
        pedido["ok"] = True
        return "RECOMENDADA: P2\nEs la que menos mueve la red."
    with OllamaFalso(responder) as srv:
        win._config_ia = lambda: {"proveedor": "ollama", "url": srv.url, "modelo": "qwen3-vl:8b"}
        dlg = _abrir(win)
        dlg.ir_a_conflicto(ids[0])
        r = dlg.resolver
        validas = [p.id for p in r._props if p.valida]
        t = time.time()
        while r._origen not in ("ia", "memoria", "plantilla") and time.time() - t < 10:
            QtWidgets.QApplication.processEvents(); time.sleep(0.01)
        assert pedido and r._origen == "ia"
        esperada = "P2" if "P2" in validas else validas[0]
        assert r._rec == esperada and r._elegida == esperada
        assert r._tarjetas[0].p.id == esperada                      # la sugerida arriba, con su porqué
        assert "menos mueve" in r.texto.text()
        win._dirty = False


def test_clic_en_la_rueda_navega_a_los_cuatro_lados(win):
    import numpy as np
    from PySide6 import QtCore, QtGui
    dlg = _abrir(win)
    v = dlg.visor
    c = QtCore.QPointF(100, 100)
    for tipo, b in ((QtCore.QEvent.MouseButtonPress, QtCore.Qt.MiddleButton),
                    (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        v.mousePressEvent(QtGui.QMouseEvent(tipo, c, c, QtCore.Qt.MiddleButton, b, QtCore.Qt.NoModifier)) \
            if tipo == QtCore.QEvent.MouseButtonPress else \
            v.mouseReleaseEvent(QtGui.QMouseEvent(tipo, c, c, QtCore.Qt.MiddleButton, b, QtCore.Qt.NoModifier))
    assert v.autopan_activo()
    der, arriba = v.cam.ejes()
    o0, d0 = v.cam.objetivo.copy(), v.cam.dist
    p = QtCore.QPointF(200, 100)                          # cursor a la derecha
    v.mouseMoveEvent(QtGui.QMouseEvent(QtCore.QEvent.MouseMove, p, p, QtCore.Qt.NoButton, QtCore.Qt.NoButton,
                                       QtCore.Qt.NoModifier))
    v._autopan_paso()
    assert float(np.dot(v.cam.objetivo - o0, der)) > 0 and v.cam.dist == d0      # se ve más a la derecha
    o1 = v.cam.objetivo.copy()
    p = QtCore.QPointF(100, 200)                          # cursor abajo
    v.mouseMoveEvent(QtGui.QMouseEvent(QtCore.QEvent.MouseMove, p, p, QtCore.Qt.NoButton, QtCore.Qt.NoButton,
                                       QtCore.Qt.NoModifier))
    v._autopan_paso()
    assert float(np.dot(v.cam.objetivo - o1, arriba)) < 0
    v.mousePressEvent(QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, c, c, QtCore.Qt.LeftButton,
                                        QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
    assert not v.autopan_activo()                         # otro clic lo termina
    # rueda APRETADA: sus giros desplazan (no acercan); de lado desplazan a los lados
    d1, o2 = v.cam.dist, v.cam.objetivo.copy()
    ev = QtGui.QWheelEvent(c, c, QtCore.QPoint(0, 0), QtCore.QPoint(0, 120), QtCore.Qt.MiddleButton,
                           QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
    v.wheelEvent(ev)
    assert v.cam.dist == d1 and not np.allclose(v.cam.objetivo, o2)
    o3 = v.cam.objetivo.copy()
    ev = QtGui.QWheelEvent(c, c, QtCore.QPoint(0, 0), QtCore.QPoint(120, 0), QtCore.Qt.NoButton,
                           QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
    v.wheelEvent(ev)
    assert v.cam.dist == d1 and float(np.dot(v.cam.objetivo - o3, der)) != 0
