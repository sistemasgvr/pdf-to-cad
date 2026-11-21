"""2026-11-21: al armar la Vista 3D con miles de válvulas la ventana quedaba trabada minutos: cada válvula volvía a
comparar la geometría de TODAS las utilidades para validar el índice (`_utilidades_cerca`)."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    yield w
    w._dirty = False
    w.close()


def _red(w, n):
    w.scale, w.zoom = 1.0, 1.0
    w.pipes = [{"layer": "AGUA", "pts": [(i * 40.0, j * 40.0), (i * 40.0 + 30.0, j * 40.0)], "diam": 12.0,
                "diam_elegido": True, "name": f"P{i}-{j}"} for i in range(n) for j in range(n)]
    w.valvulas = [dict(x=i * 40.0 + 15.0, y=j * 40.0, utilidad="AGUA", union="FLG", material="", tipo="",
                       origen="usuario", sim_w=2.0, sim_h=2.0) for i in range(n) for j in range(n)]


def test_las_valvulas_de_la_vista_3d_no_revalidan_el_indice_por_valvula(win, monkeypatch):
    from nucleo import indice_plano
    from ui.dialogos import vista3d_armado
    _red(win, 30)                                           # 900 utilidades, 900 válvulas
    llamadas = []
    original = indice_plano._firma
    monkeypatch.setattr(indice_plano, "_firma", lambda pipes: (llamadas.append(1), original(pipes))[1])

    class Falso(vista3d_armado.ArmadoMixin):
        win = None
    f = Falso()
    f.win = win
    t0 = time.perf_counter()
    r = f._valvulas3d(win.pipes)
    assert len(llamadas) <= 4, len(llamadas)                # antes: una por válvula (cientos)
    assert time.perf_counter() - t0 < 20
    copia = [dict(p) for p in win.pipes]                    # una copia (el armado de fondo) también va rápido
    llamadas.clear()
    assert len(f._valvulas3d(copia)) == len(r)
    assert len(llamadas) <= 4
