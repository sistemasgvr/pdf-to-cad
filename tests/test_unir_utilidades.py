"""Unir varias utilidades en una: lógica pura (unir_utilidades.py) y la ventana
real (Ctrl+clic en el lienzo, Ctrl+J/menú, deshacer, bancoducto y conexiones)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unir_utilidades as U  # noqa: E402

FT = 0.5                                    # pies por px → tolerancia 0.5 ft = 1 px


def _p(pts, **k):
    d = dict(layer="AGUA", pts=pts, name="", diam=8.0)
    d.update(k)
    return d


@pytest.mark.parametrize("b_pts", [
    [(100, 0), (150, 10), (200, 0)],        # A.fin – B.inicio
    [(200, 0), (150, 10), (100, 0)],        # A.fin – B.fin (B al revés)
])
def test_orientaciones_por_el_final(b_pts):
    pl = U.planificar([_p([(0, 0), (50, 0), (100, 0)]), _p(b_pts)], [0, 1], 0, FT)
    assert pl.ok and pl.pipe["pts"] == [(0, 0), (50, 0), (100, 0), (150, 10), (200, 0)]


@pytest.mark.parametrize("b_pts", [
    [(-100, 0), (-50, 5), (0, 0)],          # B.fin – A.inicio
    [(0, 0), (-50, 5), (-100, 0)],          # B.inicio – A.inicio (B al revés)
])
def test_orientaciones_por_el_inicio(b_pts):
    pl = U.planificar([_p([(0, 0), (100, 0)], name="BASE"), _p(b_pts, name="otra")], [0, 1], 0, FT)
    assert pl.ok and pl.pipe["pts"] == [(-100, 0), (-50, 5), (0, 0), (100, 0)]
    assert pl.pipe["name"] == "BASE"                     # los datos de la base mandan


def test_cotas_de_cada_tramo_se_conservan():
    a = _p([(0, 0), (50, 0), (100, 0)], inv_start=10.0, inv_end=9.0)
    b = _p([(200, 0), (150, 10), (100, 0)], inv_start=7.0, inv_end=8.5)   # al revés: sale 8.5
    p = U.planificar([a, b], [0, 1], 0, FT).pipe
    assert (p["inv_start"], p["inv_end"]) == (10.0, 7.0)
    assert p["vertex_inv_in"][2] == 9.0 and p["vertex_inv_out"][2] == 8.5   # llega 9, sale 8.5
    assert p["vertex_inv_out"][1] == pytest.approx(9.5) and p["vertex_inv_in"][3] == pytest.approx(7.75)


def test_codos_y_tipos_de_vertice_se_corren():
    a = _p([(0, 0), (50, 0), (100, 0)], vertex_kinds=["end", "fillet", "stop"], fillets={"1": 12.0})
    b = _p([(100, 0), (150, 10), (200, 0)], vertex_kinds=["end", "fillet", "end"], fillets={1: 30.0})
    p = U.planificar([a, b], [0, 1], 0, FT).pipe
    assert p["vertex_kinds"] == ["end", "fillet", "stop", "fillet", "end"]   # la bóveda del empalme se queda
    assert p["fillets"] == {1: 12.0, 3: 30.0}


def test_hueco_pequeno_se_cierra_con_tramo_recto():
    pl = U.planificar([_p([(0, 0), (100, 0)]), _p([(106, 0), (200, 0)])], [0, 1], 0, FT)
    assert pl.ok and pl.pipe["pts"] == [(0, 0), (100, 0), (106, 0), (200, 0)]
    assert pl.empalmes[0].hueco_ft == pytest.approx(3.0)
    assert not U.planificar([_p([(0, 0), (100, 0)]), _p([(106, 0), (200, 0)])], [0, 1], 0, FT,
                            permitir_hueco=False).ok


def test_tres_en_cadena_en_cualquier_orden():
    pl = U.planificar([_p([(100, 0), (200, 0)]), _p([(300, 0), (200, 0)]), _p([(0, 0), (100, 0)])],
                      [0, 1, 2], 0, FT)
    assert pl.ok and pl.pipe["pts"] == [(0, 0), (100, 0), (200, 0), (300, 0)] and sorted(pl.unidas) == [1, 2]


@pytest.mark.parametrize("pipes,texto", [
    ([_p([(0, 0), (200, 0)]), _p([(100, 0), (100, 100)])], "ramal"),
    ([_p([(0, 0), (100, 0)]), _p([(100, 0), (200, 0)], layer="GAS")], "otro tipo"),
    ([_p([(0, 0), (100, 0)]), _p([(300, 0), (400, 0)])], "100.00 ft"),
])
def test_no_se_unen(pipes, texto):
    pl = U.planificar(pipes, [0, 1], 0, FT)
    assert not pl.ok and texto in pl.error


def test_avisa_los_datos_que_cambian():
    pl = U.planificar([_p([(0, 0), (100, 0)]), _p([(100, 0), (200, 0)], diam=6.0, material="PVC")],
                      [0, 1], 0, FT)
    assert any("6" in a for a in pl.avisos) and any("PVC" in a for a in pl.avisos)


# ─────────────────────────────── ventana ───────────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    import i18n
    import i18n_core
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from app_window import Main
    from duct_bank import DuctBank
    w = Main()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.pipes = [_p([(100, 100), (400, 100)], name="A"),
               _p([(700, 100), (400, 100)], name="B"),            # al revés
               _p([(600, 0), (600, 300)], layer="GAS")]              # cruza a la B en (600, 100)
    db = DuctBank(name="DB"); db.assign([1]); w.duct_banks = [db]
    w.cross_connections = [{"x": 600.0, "y": 100.0, "pipe_a": 1, "pipe_b": 2, "z_a": None, "z_b": None}]
    w._refresh_lists(); w._redraw()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Yes)
    w.avisos = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda _p, _t, msg, *a: w.avisos.append(msg))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda _p, _t, msg, *a: w.avisos.append(msg))
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def test_ctrl_clic_en_lienzo_y_unir(win):
    win._show_tab(0); win.pipe_list.setCurrentRow(0)
    win._toggle_pipe_selection(1)                          # Ctrl+clic sobre la B en el lienzo
    assert win._selected_pipe_rows() == [0, 1]
    win.unir_utilidades()
    assert len(win.pipes) == 2 and win.pipes[0]["pts"] == [(100, 100), (400, 100), (700, 100)]
    assert win.pipes[0]["name"] == "A" and win.sel_pipe == 0
    assert win.duct_banks[0].assigned() == [0]             # el bancoducto de la B pasa a la unida
    assert win.cross_connections[0]["pipe_a"] == 0 and win.cross_connections[0]["pipe_b"] == 1
    win.undo()
    assert len(win.pipes) == 3 and win.pipes[1]["name"] == "B"
    assert win.duct_banks[0].assigned() == [1] and win.cross_connections[0]["pipe_a"] == 1


def test_ctrl_clic_quita_de_la_seleccion(win):
    win._show_tab(0); win.pipe_list.setCurrentRow(0)
    win._toggle_pipe_selection(1)
    win._toggle_pipe_selection(1)
    assert win._selected_pipe_rows() == [0]


def test_unir_con_una_sola_o_de_otro_tipo_avisa(win):
    win._show_tab(0); win.pipe_list.setCurrentRow(0)
    win.unir_utilidades()
    assert "Selecciona dos" in win.avisos[-1] and len(win.pipes) == 3
    win._toggle_pipe_selection(2)
    win.unir_utilidades()
    assert "otro tipo" in win.avisos[-1] and len(win.pipes) == 3


def test_ctrl_j_en_el_menu(win):
    acts = [a for a in win.findChildren(type(win.act_show_acc)) if a.shortcut().toString() == "Ctrl+J"]
    assert acts
