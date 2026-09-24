"""Pruebas del preview del reconocimiento (recognition_dialog) — offscreen.

Cubre: cabecera con utilidad y hoja, capas usadas informativas (asignación
automática), botones «Cambiar de hoja…» / «Ajustar capas…» y su acción,
Continuar deshabilitado cuando no hay líneas.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
from PySide6 import QtGui, QtWidgets

import recognition as rec
import recognition_dialog as rd

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
PAGE = 13

needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _blank(w=200, h=100):
    img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB888)
    img.fill(QtGui.QColor("white"))
    return img


@pytest.fixture(scope="module")
def result():
    if not PDF.is_file():
        pytest.skip("sin PDF")
    return rec.recognize_page(PDF, PAGE, zoom=1.0)     # roles automáticos por nombre


@pytest.fixture(scope="module")
def drainage_result():
    if not PDF.is_file():
        pytest.skip("sin PDF")
    return rec.recognize_page(PDF, PAGE, utility="DRENAJE", zoom=1.0)


@needs_pdf
def test_preview_muestra_utilidad_hoja_y_capas_automaticas(result):
    _app()
    dlg = rd.RecognitionPreviewDialog(None, _blank(), result, "ELECTRICO", page_count=19)
    assert dlg.lbl_sheet.text() == "Hoja 14 / 19"
    assert dlg.action == rd.PREVIEW_CANCEL
    assert dlg.btn_ok.isEnabled()                       # hay líneas → se puede importar
    # Las capas se asignaron solas (sin diálogo de confirmación) y se listan.
    assert result.layer_roles[rec.ROLE_LINEAS] and result.layer_roles[rec.ROLE_BUZONES]
    texts = [dlg.findChildren(QtWidgets.QListWidget)[0].item(i).text()
             for i in range(dlg.findChildren(QtWidgets.QListWidget)[0].count())]
    assert "Líneas" in texts and "Bóvedas" in texts
    assert any("C-ELEC-UNGD-E" in t for t in texts) and any("C-ELEC-VALT-E" in t for t in texts)
    dlg.deleteLater()


@needs_pdf
def test_preview_combinado_muestra_electrico_y_drenaje(result, drainage_result):
    _app()
    dlg = rd.RecognitionPreviewDialog(
        None, _blank(), [result, drainage_result], page_count=19)
    assert len(dlg._results) == 2
    assert dlg._n_draw() == len(result.drawable) + len(drainage_result.drawable)
    labels = [widget.text() for widget in dlg.findChildren(QtWidgets.QLabel)]
    assert "Eléctrico y Drenaje" in labels
    texts = [dlg.findChildren(QtWidgets.QListWidget)[0].item(i).text()
             for i in range(dlg.findChildren(QtWidgets.QListWidget)[0].count())]
    assert "Eléctrico (E)" in texts and "Drenaje (SD)" in texts
    assert any("C-ELEC-UNGD" in text for text in texts)
    assert any("C-STRM-UNGD" in text for text in texts)
    dlg.deleteLater()


@needs_pdf
def test_preview_botones_devuelven_accion(result):
    _app()
    for btn_name, action in (("btn_sheet", rd.PREVIEW_CHANGE_SHEET),
                             ("btn_roles", rd.PREVIEW_ADJUST_LAYERS),
                             ("btn_ok", rd.PREVIEW_IMPORT)):
        dlg = rd.RecognitionPreviewDialog(None, _blank(), result, "ELECTRICO", page_count=19)
        getattr(dlg, btn_name).click()
        assert dlg.action == action and dlg.result() == QtWidgets.QDialog.Accepted
        dlg.deleteLater()


def test_preview_sin_lineas_deshabilita_continuar():
    _app()
    empty = rec.RecognitionResult(utility="ELECTRICO", page_index=0, scale_ft_per_pt=0.3,
                                  warnings=["No se encontraron líneas eléctricas subterráneas en esta hoja."])
    dlg = rd.RecognitionPreviewDialog(None, _blank(), empty, "ELECTRICO", page_count=3)
    assert not dlg.btn_ok.isEnabled()
    assert dlg.btn_roles.isEnabled() and dlg.btn_sheet.isEnabled()
    labels = [w.text() for w in dlg.findChildren(QtWidgets.QLabel)]
    assert any("Ajustar capas" in t for t in labels)
    assert dlg.lbl_sheet.text() == "Hoja 1 / 3"
    dlg.deleteLater()
