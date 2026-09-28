"""Pruebas del diálogo «Capas de la hoja» (layer_dialog) — offscreen, sin ventana.

Cubre lo que no es puro: árbol agrupado por utilidad, casilla de GRUPO (apaga
sus capas y recuerda su estado), buscador, Mostrar/Ocultar sobre lo filtrado,
«Reconocer» con «Todas», cambio de hoja con conservación de las capas marcadas,
volver a «Componer hoja» desde la cabecera y la opacidad del PDF.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtWidgets

import layer_dialog
import pdf_layers
import recognition as rec_mod

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
PAGE = 13

needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _rows(dlg):
    """[(utilidad, nombre|None, oculto, marcado)] en el orden del árbol (grupo y sus capas)."""
    out = []
    for i in range(dlg.tree.topLevelItemCount()):
        grp = dlg.tree.topLevelItem(i)
        for it in [grp] + [grp.child(j) for j in range(grp.childCount())]:
            out.append((it.data(0, layer_dialog._ROLE_UTILITY), it.data(0, layer_dialog._ROLE_NAME),
                        it.isHidden(), it.checkState(0) == QtCore.Qt.Checked))
    return out


def _layer(dlg, name):
    return next(it for it in dlg._layer_items() if it.data(0, layer_dialog._ROLE_NAME) == name)


@pytest.fixture
def dlg():
    _app()
    doc = fitz.open(str(PDF))
    d = layer_dialog.SheetLayersDialog(None, doc, PAGE, can_go_back=True)
    yield d
    d._timer.stop()
    d.deleteLater()
    doc.close()


@needs_pdf
def test_arbol_agrupado_por_utilidad(dlg):
    rows = _rows(dlg)
    order = [k for k, _ in pdf_layers.UTILITIES]
    groups = [u for u, name, _, _ in rows if name is None]
    assert groups == [u for u in order if u in groups]
    cur = None
    for u, name, _, _ in rows:
        if name is None:
            cur = u
        else:
            assert u == cur and pdf_layers.utility_of(name) == u
    assert "ELECTRICO" in groups and "OTRAS" in groups
    # grupos plegados al abrir; todas visibles; el conteo cuenta solo capas
    assert not any(dlg.group_item(u).isExpanded() for u in groups)
    n_layers = sum(1 for _, name, _, _ in rows if name is not None)
    assert dlg.hidden_names() == []
    assert f"{n_layers}" in dlg.lbl_count.text()


@needs_pdf
def test_reconocer_todas_y_una_por_una(dlg):
    """«Todas» + una casilla por utilidad; sin ninguna marcada no se continúa."""
    assert set(dlg._recog_checks) == set(rec_mod.SUPPORTED_UTILITIES)
    enabled = [k for k, cb in dlg._recog_checks.items() if cb.isEnabled()]
    assert enabled and all(dlg._recog_checks[k].isChecked() for k in enabled)
    assert dlg.chk_recog_all.checkState() == QtCore.Qt.Checked
    dlg._recog_checks["ELECTRICO"].setChecked(False)
    assert dlg.chk_recog_all.checkState() == QtCore.Qt.PartiallyChecked
    assert "ELECTRICO" not in dlg.recognition_utilities()
    dlg.chk_recog_all.click()                              # parcial → todas
    assert all(dlg._recog_checks[k].isChecked() for k in enabled)
    dlg.chk_recog_all.click()                              # todas → ninguna
    assert not any(dlg._recog_checks[k].isChecked() for k in enabled)
    assert not dlg.btn_ok.isEnabled() and not dlg.lbl_recog_warn.isHidden()
    dlg._recog_checks["DRENAJE"].setChecked(True)           # una por una
    assert dlg.btn_ok.isEnabled() and dlg.lbl_recog_warn.isHidden()
    assert "DRENAJE" in dlg.recognition_utilities()


@needs_pdf
def test_casilla_de_grupo_apaga_la_utilidad_y_recuerda(dlg):
    """La casilla de la utilidad apaga TODAS sus capas; al volver a marcarla cada
    capa recupera el estado que tenía (una apagada a mano sigue apagada)."""
    elec = [name for u, name, _, _ in _rows(dlg) if name and u == "ELECTRICO"]
    dlg.set_utility_visible("ELECTRICO", False)
    assert set(elec) == set(dlg.hidden_names())
    assert dlg.group_item("ELECTRICO").checkState(0) == QtCore.Qt.Unchecked
    dlg.set_utility_visible("ELECTRICO", True)
    assert dlg.hidden_names() == []
    target = elec[0]
    _layer(dlg, target).setCheckState(0, QtCore.Qt.Unchecked)       # capa a mano
    assert dlg.group_item("ELECTRICO").checkState(0) == QtCore.Qt.PartiallyChecked
    assert f"{len(elec) - 1}/{len(elec)}" in dlg.group_item("ELECTRICO").text(0)
    dlg.set_utility_visible("ELECTRICO", False)
    assert set(elec) <= set(dlg.hidden_names())
    dlg.set_utility_visible("ELECTRICO", True)
    assert dlg.hidden_names() == [target]


@needs_pdf
def test_buscador_y_ocultar_todas_sobre_lo_filtrado(dlg):
    dlg.search.setText("VALT")
    shown = [name for u, name, hidden, _ in _rows(dlg) if not hidden and name]
    assert shown and all("VALT" in n.upper() for n in shown)
    assert all(dlg.group_item(u).isExpanded() for u, name, hidden, _ in _rows(dlg)
               if name and not hidden)                               # se ven los resultados
    dlg._set_all(False)                                              # solo lo que se ve
    assert set(dlg.hidden_names()) == set(shown)
    dlg.search.setText("")
    dlg._set_all(True)
    assert dlg.hidden_names() == []


@needs_pdf
def test_cambio_de_hoja_conserva_marcadas_y_limpia_el_buscador(dlg):
    elec = [name for u, name, _, _ in _rows(dlg) if name and u == "ELECTRICO"]
    target = elec[0]
    _layer(dlg, target).setCheckState(0, QtCore.Qt.Unchecked)
    assert dlg.hidden_names() == [target]
    assert dlg.page_index() == PAGE and "14" in dlg.lbl_sheet.text()
    dlg.search.setText("no-va-a-matchear-nada")

    dlg._go_sheet(PAGE - 1)
    assert dlg.page_index() == PAGE - 1 and "13" in dlg.lbl_sheet.text()
    assert dlg.search.text() == ""
    assert dlg.hidden_names() == [target]                     # se conserva
    assert target in pdf_layers.hidden_layers(dlg._doc)      # y está aplicada al doc
    assert any(u == "ELECTRICO" and name and not hidden for u, name, hidden, _ in _rows(dlg))
    assert dlg.btn_prev.isEnabled() and dlg.btn_next.isEnabled()
    dlg._go_sheet(-1); dlg._go_sheet(dlg._doc.page_count)     # fuera de rango: nada
    assert dlg.page_index() == PAGE - 1
    dlg._go_sheet(0)
    assert not dlg.btn_prev.isEnabled() and dlg.btn_next.isEnabled()
    dlg.reject()                                              # restaura visibilidad previa
    assert pdf_layers.hidden_layers(dlg._doc) == set()


@needs_pdf
def test_volver_a_componer_restaura_y_avisa(dlg):
    """El paso «1 Componer hoja» de la cabecera (única navegación hacia atrás)
    deshace la visibilidad y `choose_sheet_layers` devuelve LAYERS_BACK."""
    assert dlg.steps.buttons[0].isEnabled()
    assert not hasattr(dlg, "btn_back")                       # sin botón «◀» repetido
    _layer(dlg, next(n for u, n, _, _ in _rows(dlg) if n)).setCheckState(0, QtCore.Qt.Unchecked)
    dlg._render()
    dlg.steps.buttons[0].click()
    assert dlg.went_back and dlg.result() == QtWidgets.QDialog.Rejected
    assert pdf_layers.hidden_layers(dlg._doc) == set()


@needs_pdf
def test_opacidad_del_pdf(dlg):
    dlg.opacity.set_opacity(0.4)
    assert abs(dlg._pix_item.opacity() - 0.4) < 1e-6 and "40" in dlg.opacity.text()
    assert dlg.opacity.backdrop is not None and dlg.opacity.backdrop.zValue() < dlg._pix_item.zValue()
    dlg.opacity.toggle_bg()
    assert dlg.opacity.is_black() and dlg.opacity.backdrop.brush().color().value() == 0
    dlg._render()                                             # un re-render conserva la opacidad
    assert abs(dlg._pix_item.opacity() - 0.4) < 1e-6


def test_sin_vuelta_atras_no_hay_boton():
    _app()
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=300, height=200)
    page.draw_line((10, 100), (290, 100), oc=ocg)
    d = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        assert not d.steps.buttons[0].isEnabled()
        assert d.lbl_sheet.isHidden()                          # una sola hoja: sin navegador
    finally:
        d._timer.stop(); d.deleteLater()
