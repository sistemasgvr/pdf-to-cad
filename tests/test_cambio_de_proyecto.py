"""Reporte 2026-11-14: tras un proyecto muy grande se abrió otro más simple y quedaban cosas del anterior: las zonas de
sus hojas sobre el plano y el panel Resolver con sus conflictos. Al cambiar de proyecto no debe quedar nada."""
import json
import os
import sys
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, RAIZ)

from PySide6 import QtTest, QtWidgets  # noqa: E402

GRANDE = os.path.join(os.path.dirname(__file__), "escenarios", "cruces", "escenarios_complejos.digproj")
pytestmark = pytest.mark.skipif(not os.path.isfile(GRANDE), reason="falta el proyecto de escenarios")


def _chico(tmp_path):
    """El mismo proyecto con UNA utilidad y sin registro de conflictos."""
    ruta = str(tmp_path / "chico.digproj")
    with zipfile.ZipFile(GRANDE) as zi, zipfile.ZipFile(ruta, "w") as zo:
        for n in zi.namelist():
            b = zi.read(n)
            if n == "model.json":
                m = json.loads(b)
                m["pipes"] = m["pipes"][:1]
                m["structures"] = []
                m.pop("conflictos_registro", None)
                b = json.dumps(m).encode()
            zo.writestr(n, b)
    return ruta


def test_abrir_otro_proyecto_no_deja_zonas_ni_conflictos_del_anterior(tmp_path):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana import app_window
    w = app_window.Main()
    w.resize(1400, 860)
    w.show()
    try:
        w._open_project_path(GRANDE)
        QtTest.QTest.qWait(1200)
        viejos = {c.id for c in w._conflictos}
        assert viejos
        w.mostrar_asistente(True, "conflictos")
        QtTest.QTest.qWait(500)
        dlg = w._dlg_soluciones
        assert dlg.lista.count() > 0
        c = w._conflictos[0]
        w._ir_a_elemento(c.x, c.y, activar=False)                   # el círculo que parpadea
        assert w._marca_lugar is not None
        # el esquema de hojas de una hoja compuesta (el proyecto grande era de varios mapas)
        w._composite_layout = [((0, 0, 100, 100), "Mapa 1"), ((100, 0, 200, 100), "Mapa 2")]
        # un redibujo que no renumera (conflictos ocultos) tampoco puede dejar la lista anterior
        w.chk_show_conflicts.setChecked(False)
        w._dirty = False
        w._open_project_path(_chico(tmp_path))
        QtTest.QTest.qWait(1200)
        assert w._composite_layout is None and w._hojas_px() == []   # sin las zonas del anterior
        assert w._marca_lugar is None
        ids = {dlg.lista.item(k).data(_rol()) for k in range(dlg.lista.count())}
        assert not (ids & viejos), ids
        assert w._conflictos == [] and w.conflictos_resueltos() == []
        assert dlg._actual is None
        w.chk_show_conflicts.setChecked(True)                          # con conflictos: los del proyecto nuevo
        QtTest.QTest.qWait(500)
        nuevos = {c.id for c in w._conflictos}
        ids = {dlg.lista.item(k).data(_rol()) for k in range(dlg.lista.count())} - {None}
        assert ids == nuevos
        assert all(set(c.pipes or []) <= {0} for c in w._conflictos)
    finally:
        w.chk_show_conflicts.setChecked(True)
        w._dirty = False
        w.close()


def _rol():
    from ui.dialogos.ia_soluciones import _ROL
    return _ROL
