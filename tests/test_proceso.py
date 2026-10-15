"""Trabajo en un proceso aparte (`ui.comun.proceso`, pedido del usuario 2026-10-14)."""
import os
import sys

import pytest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]

from PySide6 import QtCore  # noqa: E402

from ui.comun import proceso  # noqa: E402


@pytest.fixture
def con_proceso(monkeypatch):
    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    t = proceso.Trabajador("prueba")
    yield t
    t.parar()


def test_el_trabajo_corre_en_otro_proceso_y_avisa_su_avance(con_proceso):
    vistos = []
    t = proceso.Tarea("ui.comun.proceso_hijo:eco", ("hola",), {"pasos": 3})
    t.avance.connect(vistos.append)
    out = {}
    lazo = QtCore.QEventLoop()
    t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    con_proceso.enviar(t)
    QtCore.QTimer.singleShot(60000, lazo.quit)
    lazo.exec()
    assert out["e"] == "" and out["r"][0] == "hola" and out["r"][1] != os.getpid()
    assert vistos == [(1, 3), (2, 3), (3, 3)]
    pid = out["r"][1]
    t2 = proceso.Tarea("ui.comun.proceso_hijo:eco", (2,))     # el trabajador se reusa
    t2.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    con_proceso.enviar(t2)
    lazo.exec()
    assert out["r"] == (2, pid)


def test_error_y_cancelar(con_proceso):
    out = {}
    lazo = QtCore.QEventLoop()
    t = proceso.Tarea("ui.comun.proceso_hijo:no_existe")
    t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    con_proceso.enviar(t)
    QtCore.QTimer.singleShot(60000, lazo.quit)
    lazo.exec()
    assert out["r"] is None and "no_existe" in out["e"]
    t2 = proceso.Tarea("ui.comun.proceso_hijo:eco", (1,), {"pasos": 0})
    t2.terminado.connect(lambda r, e: out.update(r2=r, e2=e))
    con_proceso.enviar(t2)
    t2.cancelar()
    assert out["e2"] == "cancelado" and out["r2"] is None
