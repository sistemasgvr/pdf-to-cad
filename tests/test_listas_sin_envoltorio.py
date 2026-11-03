"""Las filas de las listas las crea Qt, nunca Python (`ui_common.fila_lista`; reporte del usuario 2026-11-02: el programa
se cerraba solo al importar). Los volcados: `QListWidget.clear` → destructor del ítem → `Shiboken::Object::destroy` →
`releaseWrapper` con el envoltorio ya muerto. Sin envoltorio esa ruta no existe."""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun.ui_common import fila_lista

APP = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _envoltorios_de_filas():
    return [w for w in shiboken6.getAllValidWrappers() if isinstance(w, QtWidgets.QListWidgetItem)]


def test_ningun_archivo_crea_filas_desde_python():
    crea = re.compile(r"QListWidgetItem\s*\(")
    malos = [f"{p.relative_to(APP)}:{n}" for p in APP.rglob("*.py")
             for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if crea.search(linea)]
    assert not malos, "usar ui_common.fila_lista: " + ", ".join(malos)


def test_fila_lista_deja_todo_en_la_lista_y_ningun_envoltorio(app):
    lista = QtWidgets.QListWidget()
    icono = QtGui.QIcon(QtGui.QPixmap(8, 8))
    antes = len(_envoltorios_de_filas())
    for i in range(50):
        it = fila_lista(lista, f"fila {i}", icono if i % 2 else None)
        it.setData(QtCore.Qt.UserRole, i)
        it.setToolTip(f"globo {i}")
    del it
    assert len(_envoltorios_de_filas()) == antes
    assert lista.count() == 50
    assert lista.item(7).text() == "fila 7" and lista.item(7).data(QtCore.Qt.UserRole) == 7
    assert lista.item(7).toolTip() == "globo 7"
    assert not lista.item(7).icon().isNull() and lista.item(8).icon().isNull()
    lista.clear()
    assert lista.count() == 0


def test_vaciar_con_un_item_a_la_mano_no_lo_deja_valido(app):
    lista = QtWidgets.QListWidget()
    a_la_mano = fila_lista(lista, "x")
    lista.clear()
    assert not shiboken6.isValid(a_la_mano)


def _ventana(pipes, structures):
    from traduccion import i18n_core
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    win = Main()
    win.pipes[:] = pipes
    win.structures[:] = structures
    return win


def test_la_ventana_rellena_y_vacia_sus_listas_sin_envoltorios(app):
    pipes = [dict(layer=("AGUA", "ELECTRICO", "DRENAJE")[i % 3], pts=[(10.0 * i, 0.0), (10.0 * i + 8, 20.0)], name="",
                  net="", diam=8, ab=i % 5 == 0) for i in range(120)]
    win = _ventana(pipes, [])
    win.leaders.append({"orient": "d"})
    win.erase_regions.append({"pts": [(0, 0), (1, 0), (1, 1)], "enabled": False})
    win.ref_centerlines.append({"cod": "CL-1", "pts": [(0, 0), (9, 9)]})
    win.structures.append({"cod": "BZ-9", "x": 500.0, "y": 500.0, "hidden": True, "world": True, "standalone": True})
    for _ in range(3):                        # importar llama dos veces seguidas: la 2.ª vaciaba lo de la 1.ª
        win._refresh_lists()
        app.processEvents()
    assert win.pipe_list.count() == 120
    assert "(AB)" in win.pipe_list.item(0).text() and "(AB)" not in win.pipe_list.item(1).text()
    assert not win.pipe_list.item(0).icon().isNull()
    assert win.sleader_list.item(0).data(QtCore.Qt.UserRole) == 0
    assert win.region_list.item(0).checkState() == QtCore.Qt.Unchecked
    assert win.cl_list.item(0).text().startswith("CL-1") and not win.cl_list.item(0).icon().isNull()
    assert win.bz_list.count() + win.curve_list.count() == len(win.structures)
    win.pipe_list.setCurrentRow(5)            # elegir una fila sigue llegando a la utilidad
    assert win.pipe_list.currentRow() == 5 and win._selected_pipe_rows() == [5]
    assert _envoltorios_de_filas() == []
    win._dirty = False
    win.close()


def test_sin_consola_el_trabajador_atiende_el_siguiente_trabajo(monkeypatch):
    import queue
    import sys
    from ui.comun import proceso_hijo
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(proceso_hijo, "bajar_prioridad", lambda: None)
    entrada, salida = queue.Queue(), queue.Queue()
    entrada.put((1, "ui.comun.proceso_hijo:eco", ("a",), {}))
    entrada.put((2, "ui.comun.proceso_hijo:eco", ("b",), {}))
    entrada.put(None)
    proceso_hijo.bucle(entrada, salida, 0)
    assert salida.get_nowait()[:2] == ("ok", 1)
    assert salida.get_nowait()[:2] == ("ok", 2)


def test_main_sin_consola_deja_stdout_y_stderr_utilizables(tmp_path):
    """Como un proceso hijo en el .exe: `main.py` se ejecuta con los dos en None y nada puede fallar al escribir."""
    import subprocess
    import sys
    salida = tmp_path / "res.txt"
    codigo = (
        "import runpy, sys\n"
        "sys.stdout = None; sys.stderr = None\n"
        f"runpy.run_path({str(APP / 'main.py')!r}, run_name='__mp_main__')\n"
        "sys.stdout.write('x'); sys.stdout.flush(); sys.stderr.write('y'); sys.stderr.flush()\n"
        f"open({str(salida)!r}, 'w').write('bien')\n")
    subprocess.run([sys.executable, "-c", codigo], check=True, timeout=60)
    assert salida.read_text() == "bien"
