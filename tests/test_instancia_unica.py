"""Una sola instancia de la app (2026-11-17): la segunda le pasa el archivo a la primera y termina."""
import os
import subprocess
import sys
import time
import uuid

from PySide6 import QtCore, QtWidgets

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(RAIZ, "app"), RAIZ]

from ui.comun import instancia_unica as IU  # noqa: E402

_SEGUNDA = r"""
import sys
sys.path[:0] = [{app!r}, {raiz!r}]
from PySide6 import QtCore
app = QtCore.QCoreApplication([])
from ui.comun import instancia_unica as IU
sys.exit(3 if IU.ya_abierta({ruta!r}, canal={canal!r}) else 0)
"""


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _segunda(canal, ruta):
    codigo = _SEGUNDA.format(app=os.path.join(RAIZ, "app"), raiz=RAIZ, ruta=ruta, canal=canal)
    return subprocess.Popen([sys.executable, "-c", codigo])


def _esperar(app, cond, s=20):
    t = time.time()
    while not cond() and time.time() - t < s:
        app.processEvents()
        time.sleep(0.01)


def test_sin_otra_instancia_no_hay_nadie():
    _app()
    assert IU.ya_abierta("", canal="pdfcad-prueba-" + uuid.uuid4().hex) is False


def test_la_segunda_pasa_el_archivo_a_la_primera(tmp_path):
    app = _app()
    canal = "pdfcad-prueba-" + uuid.uuid4().hex
    recibidas = []
    srv = IU.escuchar(app, recibidas.append, canal=canal)
    assert srv is not None
    ruta = str(tmp_path / "proyecto.digproj")
    p = _segunda(canal, ruta)
    _esperar(app, lambda: p.poll() is not None and recibidas)
    assert p.wait(10) == 3                          # encontró la abierta y terminó
    assert recibidas == [os.path.abspath(ruta)]
    p = _segunda(canal, "")                         # sin archivo: solo traer la ventana al frente
    _esperar(app, lambda: p.poll() is not None and len(recibidas) == 2)
    assert p.wait(10) == 3 and recibidas[1] == ""
    srv.close()


def test_canal_distinto_por_usuario():
    assert IU.nombre("ana") != IU.nombre("luis")
    assert IU.nombre("Ana") == IU.nombre("ana")
