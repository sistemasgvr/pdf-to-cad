"""Georreferencia automática en la ventana (2026-11-18, `ventana_georef_auto`): se aplica sola si las piezas
dicen dónde están, se deshace con Ctrl+Z, no pisa la hecha a mano y no toca planos sin celda."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(RAIZ, "app"), RAIZ):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_georef_auto import PDFS, PDFS_DIR, _compuesta  # noqa: E402

DU06 = os.path.join(RAIZ, "tests", "fixtures")


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    i18n_core._current_lang = "es"
    monkeypatch.setenv("PDFCAD_GEOREF_AUTO", "1")
    avisos = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: avisos.append(a[1:]))
    from ui.ventana.app_window import Main
    w = Main()
    w._info = lambda *a, **k: None
    w._avisos = avisos
    yield w
    w._dirty = False


def _poner(win, nombre, paginas=None):
    """La composición sugerida del PDF (o solo algunas de sus piezas) como hoja del editor, sin materializarla:
    la georreferencia solo necesita la composición y los PDF de origen."""
    from hoja import composite as C
    comp, _d, _f = _compuesta(nombre)
    comp = C.Composite.from_dict(comp.to_dict())
    if paginas is not None:
        comp.pieces = [p for p in comp.pieces if p.page in paginas]
    with open(os.path.join(PDFS_DIR, nombre + ".pdf"), "rb") as f:
        win.src_pdfs = [{"name": nombre + ".pdf", "data": f.read()}]
    win.composite = comp


@PDFS
def test_mapas_qs_se_georreferencian_solos_y_se_deshace(win):
    _poner(win, "QS Sewer_Indian School_North", paginas={2, 3, 4})
    win._georef_automatica()
    assert win._georef_auto_esperar()
    g = win.georef
    assert g.active() and g.epsg == 2868 and g.cs_code == "AZHP-CIF" and g.kind == "similarity"
    assert len(g.points) == 3 and g.rms <= 10
    assert any("cuarto de sección" in str(a) for a in win._avisos)
    win.undo()
    assert not win.georef.active()


@PDFS
def test_no_pisa_una_georreferencia_hecha_a_mano(win):
    from geo import georef
    a_mano = georef.Georef([[1.0, 0, 5], [0, -1.0, 9], [0, 0, 1]], 2229, "similarity", 0.5, [], "CA83VF")
    win.georef = a_mano
    _poner(win, "QS Sewer_Indian School_North", paginas={2, 3})
    win._georef_automatica()
    assert win._georef_auto_esperar()
    assert win.georef is a_mano and win.georef.epsg == 2229


@PDFS
def test_composicion_con_error_queda_dudosa_y_no_se_aplica(win):
    # (2026-11-19: Water South ya cierra a 0.7 ft con el centro del recuadro de cada celda; el error se provoca
    # corriendo una pieza 100 pt ≈ 140 ft)
    _poner(win, "QS Water_Indian School_South")
    win.composite.pieces[3].x += 100.0
    win._georef_automatica()
    assert win._georef_auto_esperar()
    assert not win.georef.active() and win._georef_auto_dudosa is not None
    assert win._georef_auto_dudosa["rms_ft"] > 25
    win.aplicar_georef_auto(win._georef_auto_dudosa)            # «Aplicar igual»
    assert win.georef.active()


def test_plano_cad_sin_celda_no_cambia(win):
    """DU06 (plano CAD, hojas sin celda): nada se georreferencia."""
    import glob
    pdfs = glob.glob(os.path.join(RAIZ, "**", "*DU06*.pdf"), recursive=True) + \
        glob.glob(os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "docs prueba", "*DU06*.pdf"))
    if not pdfs:
        pytest.skip("falta el PDF DU06")
    from hoja import composite as C
    with open(pdfs[0], "rb") as f:
        win.src_pdfs = [{"name": "DU06.pdf", "data": f.read()}]
    win.composite = C.Composite([C.Piece(0, 3, [0.0, 0.0, 1.0, 1.0])])
    win._georef_automatica()
    assert win._georef_auto_esperar()
    assert not win.georef.active() and win._georef_auto_ultimo is None
