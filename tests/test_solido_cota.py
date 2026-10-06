"""Cota superior AUTOMÁTICA del sólido: el EJE de la utilidad que llega (su solera
+ medio alto interior, como lo sube el plugin) queda justo a media altura del
sólido. La fijada por el usuario no cambia."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import model_ops  # noqa: E402


def test_alto_interior_y_cota_centrada():
    assert model_ops.alto_interior_ft({"pipe_size": "4 in", "diam": 4}) == pytest.approx(4 / 12)
    assert model_ops.alto_interior_ft({"pipe_size": "6 in x 11 in"}) == pytest.approx(11 / 12)   # W x H
    assert model_ops.alto_interior_ft({"diam": 12}) == pytest.approx(1.0)
    # solera 100, tubo de 1 ft → eje 100.5; sólido de 6 ft → tapa 103.5, base 97.5
    top = model_ops.solid_top_centrado(100.0, 1.0, 6.0)
    assert top == pytest.approx(103.5) and (top + (top - 6.0)) / 2 == pytest.approx(100.5)


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    import i18n
    import i18n_core
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from app_window import Main
    w = Main()
    w.pipes = [{"layer": "ELECTRICO", "pts": [(400, 500), (600, 500)], "name": "", "diam": 4.0,
                "pipe_size": "4 in", "inv_start": 101.0, "inv_end": 100.0}]
    w.structures = [{"x": 600.0, "y": 500.0, "cod": "SÓLIDO-1", "net": "conduit", "solid": True, "shape": "rect",
                     "solid_height_ft": 6.0, "outline": [(580, 480), (620, 480), (620, 520), (580, 520)]}]
    w._refresh_lists()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def _top_dxf(w, s):
    import dxf_export
    d = dict(str(v).split("=", 1) for _c, v in dxf_export._solid_items(w, s) if "=" in str(v))
    return float(d["SOLID_TOP_Z"])


def test_la_utilidad_llega_al_centro_del_solido(win):
    s = win.structures[0]
    z, auto = win._solid_top_value(s)
    assert auto and z == pytest.approx(100.0 + (4 / 12) / 2 + 3.0)       # eje 100.1667 = media altura
    assert _top_dxf(win, s) == pytest.approx(z)
    s["solid_height_ft"] = 10.0                                            # más alto: sigue centrado
    assert win._solid_top_value(s)[0] == pytest.approx(100.0 + (4 / 12) / 2 + 5.0)
    s["solid_top_z"] = 120.0                                               # fijada por el usuario: manda
    assert win._solid_top_value(s) == (120.0, False) and _top_dxf(win, s) == 120.0
