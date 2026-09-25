"""Pruebas del diálogo «Capas de la hoja» (layer_dialog) — offscreen, sin ventana.

Cubre lo que no es puro: agrupación por utilidad en la lista, casilla de
utilidad (apaga sus capas y filtra) + buscador, Mostrar/Ocultar sobre lo filtrado y el cambio de hoja
con conservación de las capas marcadas.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtWidgets

import layer_dialog
import pdf_layers

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
PAGE = 13

needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _rows(dlg):
    """[(utilidad, nombre|None, oculto, marcado)] en el orden de la lista."""
    out = []
    for i in range(dlg.lst.count()):
        it = dlg.lst.item(i)
        out.append((it.data(layer_dialog._ROLE_UTILITY), it.data(layer_dialog._ROLE_NAME),
                    it.isHidden(), it.checkState() == QtCore.Qt.Checked))
    return out


@pytest.fixture
def dlg():
    _app()
    doc = fitz.open(str(PDF))
    d = layer_dialog.SheetLayersDialog(None, doc, PAGE)
    yield d
    d._timer.stop()
    d.deleteLater()
    doc.close()


@needs_pdf
def test_lista_agrupada_por_utilidad_con_cabeceras(dlg):
    rows = _rows(dlg)
    order = [k for k, _ in pdf_layers.UTILITIES]
    # Cabeceras (name None) en el orden de UTILITIES y cada capa bajo su cabecera.
    headers = [u for u, name, _, _ in rows if name is None]
    assert headers == [u for u in order if u in headers]
    cur = None
    for u, name, _, _ in rows:
        if name is None:
            cur = u
        else:
            assert u == cur and pdf_layers.utility_of(name) == u
    assert "ELECTRICO" in headers and "OTRAS" in headers
    # Todas visibles al inicio y el conteo cuenta solo capas (no cabeceras).
    n_layers = sum(1 for _, name, _, _ in rows if name is not None)
    assert dlg.hidden_names() == []
    assert dlg.lbl_count.text().endswith(f"{n_layers} capas") or f"{n_layers}" in dlg.lbl_count.text()


@needs_pdf
def test_selector_de_utilidad_permite_electrico_y_drenaje(dlg):
    """Casillas (no un desplegable), una por utilidad reconocible: se pueden
    combinar libremente, pero no queda ninguna sin marcar."""
    assert set(dlg._recog_checks) == {"ELECTRICO", "DRENAJE", "AGUA"}
    # por defecto, la selección de siempre; Agua se marca a mano
    assert dlg._recog_checks["ELECTRICO"].isChecked() and dlg._recog_checks["DRENAJE"].isChecked()
    assert not dlg._recog_checks["AGUA"].isChecked()
    assert dlg.recognition_utilities() == ("ELECTRICO", "DRENAJE")
    dlg._recog_checks["ELECTRICO"].setChecked(False)
    assert dlg.recognition_utilities() == ("DRENAJE",)
    dlg._recog_checks["DRENAJE"].setChecked(False)   # no deja las dos sin marcar
    assert dlg._recog_checks["DRENAJE"].isChecked()
    assert dlg.recognition_utilities() == ("DRENAJE",)


@needs_pdf
def test_utilidad_desmarcada_apaga_sus_capas_y_filtra(dlg):
    """Desmarcar una utilidad la quita de la lista Y apaga sus capas en la hoja;
    al volver a marcarla cada capa recupera el estado que tenía."""
    n_layers = sum(1 for _, name, _, _ in _rows(dlg) if name)
    dlg.chk_all.setChecked(False)                 # ninguna utilidad → lista vacía y todo apagado
    assert all(hidden for _, _, hidden, _ in _rows(dlg))
    assert len(dlg.hidden_names()) == n_layers
    dlg._util_checks["ELECTRICO"].setChecked(True)
    rows = _rows(dlg)
    shown = [(u, name) for u, name, hidden, _ in rows if not hidden]
    assert shown and all(u == "ELECTRICO" for u, _ in shown)
    assert all(pdf_layers.utility_of(n) != "ELECTRICO" for n in dlg.hidden_names())
    assert not dlg.chk_all.isChecked()
    # Buscador combinado con el filtro de utilidad (solo filtra, no apaga).
    dlg.search.setText("VALT")
    shown = [name for u, name, hidden, _ in _rows(dlg) if not hidden and name]
    assert shown and all("VALT" in n.upper() for n in shown)
    assert all(pdf_layers.utility_of(n) != "ELECTRICO" for n in dlg.hidden_names())
    dlg.search.setText("")
    # Volver a marcar todas las utilidades habilitadas repone «Todas» y enciende todo.
    for cb in dlg._util_checks.values():
        if cb.isEnabled():
            cb.setChecked(True)
    assert dlg.chk_all.isChecked() and dlg.hidden_names() == []
    # Memoria: una capa apagada a mano sigue apagada tras apagar/encender su utilidad.
    elec = [name for u, name, _, _ in _rows(dlg) if name and u == "ELECTRICO"]
    target = elec[0]
    for i in range(dlg.lst.count()):
        it = dlg.lst.item(i)
        if it.data(layer_dialog._ROLE_NAME) == target:
            it.setCheckState(QtCore.Qt.Unchecked)
    dlg._util_checks["ELECTRICO"].setChecked(False)
    assert set(elec) <= set(dlg.hidden_names())
    dlg._util_checks["ELECTRICO"].setChecked(True)
    assert dlg.hidden_names() == [target]


@needs_pdf
def test_ocultar_todas_actua_sobre_lo_filtrado(dlg):
    dlg.chk_all.setChecked(False)                 # apaga todas las utilidades
    dlg._util_checks["ELECTRICO"].setChecked(True)
    n_all = sum(1 for _, name, _, _ in _rows(dlg) if name)
    n_elec = sum(1 for u, name, _, _ in _rows(dlg) if name and u == "ELECTRICO")
    dlg._set_all(False)                           # solo sobre lo que se ve (eléctrico)
    assert len(dlg.hidden_names()) == n_all
    dlg._set_all(True)
    hidden = dlg.hidden_names()
    assert len(hidden) == n_all - n_elec and all(pdf_layers.utility_of(n) != "ELECTRICO" for n in hidden)


@needs_pdf
def test_cambio_de_hoja_conserva_marcadas_y_actualiza_conteos(dlg):
    elec = [name for u, name, _, _ in _rows(dlg) if name and u == "ELECTRICO"]
    target = elec[0]
    for i in range(dlg.lst.count()):
        it = dlg.lst.item(i)
        if it.data(layer_dialog._ROLE_NAME) == target:
            it.setCheckState(QtCore.Qt.Unchecked)
    assert dlg.hidden_names() == [target]
    assert dlg.page_index() == PAGE and "14" in dlg.lbl_sheet.text()

    dlg._go_sheet(PAGE - 1)
    assert dlg.page_index() == PAGE - 1 and "13" in dlg.lbl_sheet.text()
    assert dlg.hidden_names() == [target]                     # se conserva
    assert target in pdf_layers.hidden_layers(dlg._doc)      # y está aplicada al doc
    assert dlg.btn_prev.isEnabled() and dlg.btn_next.isEnabled()
    # Fuera de rango / misma hoja: no hace nada.
    dlg._go_sheet(-1); dlg._go_sheet(dlg._doc.page_count)
    assert dlg.page_index() == PAGE - 1

    dlg._go_sheet(0)
    assert not dlg.btn_prev.isEnabled() and dlg.btn_next.isEnabled()
    dlg.reject()                                              # restaura visibilidad previa
    assert pdf_layers.hidden_layers(dlg._doc) == set()


@needs_pdf
def test_cambio_de_hoja_resetea_el_filtro_de_utilidad_y_el_buscador(dlg):
    """El filtro de «Utilidades»/buscador es solo de VISTA: si se deja puesto
    de una hoja anterior, la lista de la nueva hoja podía verse vacía aunque
    sí tuviera capas (usuario: «la página 3 no me muestra capas»). Lo OCULTO
    en el documento (marcar/desmarcar capas) sí se conserva — eso lo cubre
    test_cambio_de_hoja_conserva_marcadas_y_actualiza_conteos."""
    dlg._util_checks["ELECTRICO"].setChecked(False)   # apaga y filtra Eléctrico
    dlg.search.setText("no-va-a-matchear-nada")
    assert not any(u == "ELECTRICO" and name for u, name, hidden, _ in _rows(dlg) if not hidden)

    dlg._go_sheet(PAGE - 1)
    assert dlg._util_checks["ELECTRICO"].isChecked() and dlg.chk_all.isChecked()
    assert dlg.search.text() == ""
    rows = _rows(dlg)
    assert any(u == "ELECTRICO" and name and not hidden for u, name, hidden, _ in rows)
