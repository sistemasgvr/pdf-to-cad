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
    ([_p([(0, 0), (100, 0)]), _p([(100, 0), (200, 0)], layer="GAS")], "otro tipo"),
    ([_p([(0, 0), (100, 0)]), _p([(300, 0), (400, 0)])], "100.00 ft"),
])
def test_no_se_unen(pipes, texto):
    pl = U.planificar(pipes, [0, 1], 0, FT)
    assert not pl.ok and texto in pl.error


def test_ramal_parte_la_de_paso_en_la_t():
    # B nace a mitad de A: A se parte en (100, 0); la unión sigue A(0→100)→B o
    # A(200→100)→B y el otro trozo de A queda aparte con sus datos.
    pl = U.planificar([_p([(0, 0), (200, 0)], name="A"), _p([(100, 0), (100, 100)], name="B")], [0, 1], 0, FT)
    assert pl.ok and pl.unidas == [1] and len(pl.sobrantes) == 1
    assert pl.pipe["name"] == "A" and pl.pipe["pts"][-1] == (100, 100) and (100.0, 0.0) in pl.pipe["pts"]
    assert len(pl.pipe["pts"]) == 3 and all(e.hueco_ft == 0 for e in pl.empalmes)
    sob = pl.sobrantes[0]["pts"]
    assert sorted([sob[0], sob[-1]]) in ([(0, 0), (100.0, 0.0)], [(100.0, 0.0), (200, 0)])
    assert any("se parte en la T" in a for a in pl.avisos)


def test_ramal_en_un_vertice_y_cotas_del_trozo():
    # C nace en el vértice interior (100, 0) de A; A trae cotas: cada trozo conserva las suyas.
    a = _p([(0, 0), (100, 0), (200, 0)], inv_start=100.0, inv_end=98.0)
    b = _p([(-100, 0), (0, 0)])                       # sigue a A por su inicio
    c = _p([(100, 0), (100, 100)])
    pl = U.planificar([a, b, c], [0, 1, 2], 0, FT)
    assert pl.ok and pl.pipe["pts"] == [(-100, 0), (0, 0), (100, 0), (100, 100)]
    sob = pl.sobrantes[0]
    assert sob["pts"] == [(100, 0), (200, 0)]
    assert sob["inv_start"] == pytest.approx(99.0) and sob["inv_end"] == pytest.approx(98.0)


def test_ramal_en_mitad_de_tramo_con_cotas_y_tipos():
    a = _p([(0, 0), (200, 0)], inv_start=100.0, inv_end=98.0, vertex_kinds=["end", "end"])
    b = _p([(50, 0), (50, 80)])
    pl = U.planificar([a, b], [0, 1], 0, FT)
    assert pl.ok
    zs = [pl.pipe.get("inv_start"), pl.pipe.get("inv_end")]
    sob = pl.sobrantes[0]
    # la T queda en (50, 0) con la cota del tramo en ese punto (99.5)
    z_t = sob["inv_start"] if sob["pts"][0] == (50.0, 0.0) else sob["inv_end"]
    assert z_t == pytest.approx(99.5)
    assert "tee" in (sob.get("vertex_kinds") or []) and None not in zs


def test_ramales_que_no_caben_en_una_linea():
    # Cruz: A horizontal y B, C, D nacen en su mitad → cuatro puntas libres.
    pipes = [_p([(0, 0), (200, 0)]), _p([(100, 0), (100, 100)]), _p([(100, 0), (100, -100)]),
             _p([(150, 0), (150, 50)])]
    pl = U.planificar(pipes, [0, 1, 2, 3], 0, FT)
    assert not pl.ok and "no caben en una sola línea" in pl.error


def test_un_hueco_no_vuelve_a_la_t():
    # Con huecos de hasta 10 ft el recorrido no puede saltar de la punta de A a la T.
    pl = U.planificar([_p([(0, 0), (20, 0)]), _p([(10, 0), (10, 30)])], [0, 1], 0, FT)
    assert pl.ok and all(e.hueco_ft == 0 for e in pl.empalmes) and len(pl.pipe["pts"]) == 3


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


def test_unir_con_ramal_deja_el_trozo_aparte(win):
    win.pipes = [_p([(100, 100), (700, 100)], name="A"), _p([(400, 100), (400, 400)], name="R")]
    win.duct_banks, win.cross_connections = [], []
    win._refresh_lists(); win._show_tab(0); win.pipe_list.setCurrentRow(0)
    win._toggle_pipe_selection(1)
    win.unir_utilidades()
    assert len(win.pipes) == 2
    unida, trozo = win.pipes
    assert unida["name"] == "A" and unida["pts"][-1] == (400, 400) and (400.0, 100.0) in unida["pts"]
    assert len(trozo["pts"]) == 2 and (400.0, 100.0) in trozo["pts"] and trozo["name"] == "A"
    win.undo()
    assert [p["pts"] for p in win.pipes] == [[(100, 100), (700, 100)], [(400, 100), (400, 400)]]
