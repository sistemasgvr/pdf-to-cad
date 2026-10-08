"""Utilidad sin nombre → red «TIPO-NÚMERO» (número en la lista, se renumera al
borrar): model_ops, la lista y el DXF (NET_NAME_DEFAULT, que el plugin usa si la
red no trae nombre propio)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import model_ops  # noqa: E402


def _p(layer, pts, name=""):
    return {"layer": layer, "pts": pts, "name": name, "diam": 4.0}


def test_nombre_por_defecto_y_union():
    pipes = [_p("TELECOM", [(0, 0), (10, 0)]), _p("TELECOM", [(10, 0), (20, 0)]),
             _p("TELECOM", [(20, 0), (30, 0)], name="Troncal")]
    assert model_ops.nombre_por_defecto(pipes[1], 1) == "TELECOM-2"
    assert model_ops.red_civil_de_union(pipes, 1, 0) == "TELECOM-1"
    assert model_ops.red_civil_de_union(pipes, 1, 2) == "Troncal"      # el nombre escrito manda
    assert model_ops.red_de(pipes[0]) == "TELECOM"                     # accesorios: sin cambio


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    from traduccion import i18n
    from traduccion import i18n_core
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.pipes = [_p("TELECOM", [(0, 0), (100, 0)]), _p("ELECTRICO", [(0, 50), (100, 50)], name="Norte"),
               _p("TELECOM", [(0, 200), (100, 200)])]
    w._refresh_lists()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def _nombres_dxf(w):
    import ezdxf
    from exportar import dxf_export
    doc = ezdxf.new("R2018")
    dxf_export.merge_into(w, doc)
    out = {}
    for e in doc.modelspace().query("LWPOLYLINE"):
        if e.has_xdata("PDFCAD"):
            d = dict(str(v).split("=", 1) for _c, v in e.get_xdata("PDFCAD") if "=" in str(v))
            out[int(d["PIPE_IDX"])] = (d["NET_NAME"], d["NET_NAME_DEFAULT"])
    return out


def test_lista_sugerencia_y_dxf_se_renumeran(win):
    textos = [win.pipe_list.item(i).text() for i in range(win.pipe_list.count())]
    assert "TELECOM-1" in textos[0] and "Norte" in textos[1] and "TELECOM-3" in textos[2]
    win._show_tab(0); win._sel_pipe(2)
    assert win.prop_name.text() == "" and win.prop_name.placeholderText() == "TELECOM-3"
    assert _nombres_dxf(win)[2] == ("", "TELECOM-3")
    win._delete_pipes([0]); win._refresh_lists()
    assert "TELECOM-2" in win.pipe_list.item(1).text()
    assert _nombres_dxf(win) == {0: ("Norte", "ELECTRICO-1"), 1: ("", "TELECOM-2")}
