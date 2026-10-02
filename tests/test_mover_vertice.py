"""Mover un vértice (o la utilidad entera) en el lienzo arrastra su buzón / caja /
sólido y conserva sus datos (ventana real, Qt offscreen)."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

import i18n  # noqa: E402
import i18n_core  # noqa: E402


@pytest.fixture
def win(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from app_window import Main
    w = Main()
    # 0: drenaje (gravedad: BZ en cada vértice); 1: otro drenaje que nace en el vértice 2 de la 0
    w.pipes = [{"layer": "DRENAJE", "pts": [(0, 0), (200, 0), (400, 0)], "name": ""},
               {"layer": "DRENAJE", "pts": [(400, 0), (400, 300)], "name": ""},
               {"layer": "ELECTRICO", "pts": [(0, 500), (300, 500)], "name": ""}]
    w._refresh_lists()
    # caja eléctrica (conduit) con contorno en el vértice 1 de la eléctrica
    w.structures.append({"x": 300.0, "y": 500.0, "cod": "CAJA-1", "net": "conduit",
                         "outline": [(290, 490), (310, 490), (310, 510), (290, 510)]})
    w._refresh_lists()
    w._show_tab(0)
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def _at(w, x, y):
    return [s for s in w.structures if math.hypot(s["x"] - x, s["y"] - y) < 0.5]


def _drag(w, pi, x0, y0, x1, y1):
    w.sel_pipe = pi
    w.begin_move(x0, y0)
    w.do_move((x0 + x1) / 2, (y0 + y1) / 2)
    w.do_move(x1, y1)
    w.end_move()


def test_buzon_sigue_al_vertice_y_conserva_cotas(win):
    bz = _at(win, 200, 0)[0]
    bz["rim"] = 101.5; bz["sump"] = 95.25
    cod = bz["cod"]
    _drag(win, 0, 200, 0, 230, 40)
    assert win.pipes[0]["pts"][1] == (230, 40)
    assert not _at(win, 200, 0)
    s = _at(win, 230, 40)
    assert len(s) == 1 and s[0]["cod"] == cod and s[0]["rim"] == 101.5 and s[0]["sump"] == 95.25
    win.undo()
    assert _at(win, 200, 0) and not _at(win, 230, 40)


def test_caja_con_contorno_sigue_al_vertice(win):
    _drag(win, 2, 300, 500, 320, 530)
    s = _at(win, 320, 530)
    assert len(s) == 1 and s[0]["cod"] == "CAJA-1"
    assert list(s[0]["outline"][0]) == [310, 520]


def test_mover_utilidad_entera_deja_el_nudo_compartido(win):
    n0 = len(win.structures)
    _drag(win, 0, 100, 80, 100, 130)               # clic fuera de la línea: mueve la utilidad entera
    assert win.pipes[0]["pts"][0] == (0, 50)
    assert _at(win, 0, 50) and _at(win, 200, 50)   # sus buzones propios la acompañan
    assert _at(win, 400, 0)                        # el nudo con la otra utilidad no se mueve
    assert len(win.structures) >= n0 - 1


# ── snap del extremo arrastrado (sólido, vértice de otra utilidad) y al dibujar ──

@pytest.fixture
def win_solido(win):
    # sólido de 40×40 px centrado en (600, 500); la eléctrica termina a 14 px de su borde
    win.pipes.append({"layer": "ELECTRICO", "pts": [(400, 500), (566, 500)], "name": ""})
    win.structures.append({"x": 600.0, "y": 500.0, "cod": "SÓLIDO-1", "net": "conduit", "solid": True,
                           "outline": [(580, 480), (620, 480), (620, 520), (580, 520)]})
    win.canvas.resetTransform()                     # 1 px de escena = 1 px de pantalla (radio 12)
    return win


def test_extremo_arrastrado_se_pega_al_solido(win_solido):
    w = win_solido
    pi = len(w.pipes) - 1
    _drag(w, pi, 566, 500, 572, 503)               # suelta a 8 px del borde izquierdo (x=580)
    assert w.pipes[pi]["pts"][-1] == (580.0, 503.0)


def test_extremo_arrastrado_se_pega_a_otro_vertice(win_solido):
    w = win_solido
    pi = len(w.pipes) - 1
    _drag(w, pi, 400, 500, 305, 507)               # cerca del vértice (300, 500) de la otra eléctrica
    assert w.pipes[pi]["pts"][0] == (300, 500)


def test_vertice_interior_no_se_engancha(win):
    win.canvas.resetTransform()
    _drag(win, 0, 200, 0, 395, 5)                  # vértice interior: queda donde se suelta
    assert win.pipes[0]["pts"][1] == (395, 5)


def test_dibujar_se_pega_al_solido(win_solido):
    w = win_solido
    hit = w._pipe_soft_snap(627, 499, layer="ELECTRICO")
    assert hit and hit["kind"] == "solid" and hit["pt"] == (620.0, 499.0)
    hit = w._pipe_soft_snap(624, 476, layer="AGUA")      # la esquina, desde cualquier utilidad
    assert hit and hit["kind"] == "solid" and hit["pt"] == (620, 480)
