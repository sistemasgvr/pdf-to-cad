"""Botón verde «+» junto al tamaño (utilidad y buzón): ventana real, Qt offscreen,
sobre el ProgramData sintético de test_catalogo_tamanos."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from traduccion import i18n  # noqa: E402
from traduccion import i18n_core  # noqa: E402
from catalogo import catalogo_tamanos as T  # noqa: E402
from ui.dialogos import catalogo_tamanos_dialog  # noqa: E402
from catalogo import civil_catalog as cc  # noqa: E402
from nucleo.model import TAB_BZ, TAB_PIPE  # noqa: E402
from test_catalogo_tamanos import BUZON, TUBO, pd  # noqa: E402,F401  (pd = fixture)


@pytest.fixture
def win(pd, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.civil_year = 2025
    cc.set_current_lang("esp")
    monkeypatch.setattr(w, "_info", lambda *a, **k: None)
    w.show()                       # el panel solo guarda familia/tamaño si está a la vista
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def _sin_ventana(monkeypatch, valores):
    """La ventana «Agregar tamaño» es modal: se reemplaza por lo que haría al aceptar."""
    def abrir(parent, kind, fid, familia, year, lang):
        T.agregar(kind, fid, valores, [(year, lang)])
        return T.texto_tamano(kind, fid, valores, year, lang)
    monkeypatch.setattr(catalogo_tamanos_dialog, "abrir", abrir)


def test_mas_de_utilidad_agrega_y_elige_el_tamano(win, monkeypatch):
    win.pipes = [{"layer": "DRENAJE", "pts": [(0, 0), (200, 0)], "name": "",
                  "pipe_family": TUBO, "pipe_size": "12 in"}]
    win._refresh_lists()
    win._show_tab(TAB_PIPE)
    win._sel_pipe(0)
    assert win.btn_add_size.isEnabled()
    assert win.btn_add_size.parent() is win.prop_size.parent()            # al lado del desplegable
    tamanos = [win.prop_size.itemText(i) for i in range(win.prop_size.count())]
    assert "15 in" not in tamanos
    _sin_ventana(monkeypatch, {"PID": 15})
    win._agregar_tamano("pipe")
    assert win.prop_size.currentText() == "15 in"
    assert win.pipes[0]["pipe_size"] == "15 in"
    # Con «(por defecto)» no hay familia que ampliar.
    win.prop_family.setCurrentIndex(0)
    assert not win.btn_add_size.isEnabled()


def test_mas_de_buzon(win, monkeypatch):
    win.pipes = [{"layer": "DRENAJE", "pts": [(0, 0), (200, 0)], "name": ""}]
    win._refresh_lists()
    s = next(s for s in win.structures if abs(s["x"]) < 0.5)
    s["part"] = BUZON
    win._show_tab(TAB_BZ)
    win._sel_bz(win.structures.index(s))
    assert win.btn_add_bz_size.isEnabled()
    _sin_ventana(monkeypatch, {"SIW": 30, "SIL": 30})
    win._agregar_tamano("structure")
    assert win.bz_size.currentText() == T.texto_tamano("structure", BUZON, {"SIW": 30, "SIL": 30}, 2025, "esp")
    assert s["part_size"] == win.bz_size.currentText()


def test_ventana_arranca_vacia_y_sin_boton(pd):
    """Sin medida escrita no se puede agregar (antes arrancaba en 0.01 y se
    colaba un 0.01 in en el catálogo)."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    cc.set_current_lang("esp")
    d = catalogo_tamanos_dialog.AgregarTamanoDialog(None, "structure", BUZON, "Buzon", 2025, "esp")
    assert all(sp.value() == 0 and sp.text().strip() == "" for sp in d.ejes.values())
    assert not d.btn_ok.isEnabled()
    d.ejes["SIW"].setValue(30)
    assert not d.btn_ok.isEnabled()                       # falta el largo
    d.ejes["SIL"].setValue(30)
    assert d.btn_ok.isEnabled()
    d.deleteLater()


def test_custom_copiada_de_autodesk_no_manda_guid(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "pipe_family_xml", lambda y, f: str(tmp_path / "x.xml"))
    assert cc.family_guid(2025, "AeccRectangularConcretePipe_Imperial CBA", "pipe") == ""
