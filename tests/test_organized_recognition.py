"""The arranged preview must recognize each source with its own layer choices."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from organized_layer_dialog import OrganizedLayersDialog
from organized_layers import selected_sheets
from organized_recognition_dialog import OrganizedRecognitionDialog, _rotated_point
from pdf_view_quality import FocusedPageQuality, render_scale
from workers import OrganizedRecognitionWorker
from widgets import ZoomPanView


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pdf_bytes():
    with fitz.open() as doc:
        doc.new_page(width=120, height=80)
        return doc.tobytes()


def test_capas_de_hojas_organizadas_ofrece_casillas_de_utilidad_a_reconocer():
    """«Utilidades a reconocer» son casillas seleccionables (como el panel
    «Utilidades» de al lado), no un desplegable de 3 combinaciones fijas —
    y siempre queda al menos una marcada."""
    _app()
    with fitz.open() as doc:
        page = doc.new_page(width=120, height=80)
        ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
        page.draw_line((0, 0), (100, 0), color=(0, 0, 0), oc=ocg)
        dlg = OrganizedLayersDialog(
            None, [doc], [{"name": "a.pdf", "start": 0, "count": 1}],
            {"main": 0}, {})
        try:
            assert set(dlg._recog_checks) == {"ELECTRICO", "DRENAJE"}
            assert dlg._recog_checks["ELECTRICO"].isChecked()
            assert dlg._recog_checks["DRENAJE"].isChecked()
            dlg._recog_checks["ELECTRICO"].setChecked(False)
            dlg._recog_checks["DRENAJE"].setChecked(False)   # no deja las dos sin marcar
            assert dlg._recog_checks["DRENAJE"].isChecked()
        finally:
            dlg._timer.stop()
            dlg.deleteLater()


def test_rotation_maps_overlay_to_rotated_page():
    assert _rotated_point(10, 20, 120, 80, 0) == (10, 20)
    assert _rotated_point(10, 20, 120, 80, 90) == (60, 10)
    assert _rotated_point(10, 20, 120, 80, 180) == (110, 60)
    assert _rotated_point(10, 20, 120, 80, 270) == (20, 110)


def test_worker_uses_each_pdf_and_its_hidden_layers(tmp_path, monkeypatch):
    base = tmp_path / "base.pdf"
    base.write_bytes(_pdf_bytes())
    extra = _pdf_bytes()
    sources = [{"name": "base.pdf", "start": 0, "count": 1},
               {"name": "extra.pdf", "start": 1, "count": 1}]
    sheets = selected_sheets({"main": 0, "right": 1}, sources)
    calls = []

    def fake_recognize(_path, *, page_index, doc, hidden_ocgs, crop=None,
                       utility=None, **_kwargs):
        calls.append((page_index, doc.page_count, list(hidden_ocgs), crop, utility))
        return object()

    import recognition
    monkeypatch.setattr(recognition, "recognize_page", fake_recognize)
    worker = OrganizedRecognitionWorker(
        str(base), [{"name": "extra.pdf", "data": extra}], sheets,
        {"0": ["BASE-HIDDEN"], "1": ["EXTRA-HIDDEN"]},
        crops={"right": [0.25, 0, 0.75, 1]},
        utilities=("ELECTRICO", "DRENAJE"))
    emitted = []
    worker.done.connect(lambda rows, error: emitted.append((rows, error)))
    worker.run()

    rows, error = emitted[0]
    assert not error
    assert [row["sheet"]["slot"] for row in rows] == ["main", "right"]
    assert calls == [(0, 1, ["BASE-HIDDEN"], None, "ELECTRICO"),
                     (0, 1, ["BASE-HIDDEN"], None, "DRENAJE"),
                     (0, 1, ["EXTRA-HIDDEN"], [0.25, 0, 0.75, 1], "ELECTRICO"),
                     (0, 1, ["EXTRA-HIDDEN"], [0.25, 0, 0.75, 1], "DRENAJE")]
    assert all(len(row["results"]) == 2 for row in rows)
    assert [(row["width"], row["height"]) for row in rows] == [(120, 80), (60, 80)]


def test_combined_preview_opens_with_rotated_pages(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from recognition import RecognitionResult
    image = QtGui.QImage(120, 80, QtGui.QImage.Format_RGB888)
    image.fill(QtGui.QColor("white"))
    samples = bytes(image.constBits())
    rows = []
    for slot in ("main", "right"):
        rows.append({
            "sheet": {"slot": slot, "source_name": "plan.pdf", "page": 0},
            "result": RecognitionResult("ELECTRICO", 0, 1.0),
            "width": 120, "height": 80, "stride": image.bytesPerLine(),
            "samples": samples,
        })
    dialog = OrganizedRecognitionDialog(None, rows, {"right": 90})
    assert dialog.list.count() == 2
    assert dialog._items["right"].pixmap().width() == 80
    dialog.close()
    del app


def test_focused_sheet_rerenders_sharper_without_moving_overlay(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with fitz.open(stream=_pdf_bytes(), filetype="pdf") as doc:
        view = ZoomPanView()
        view.resize(500, 400)
        image = QtGui.QImage(120, 80, QtGui.QImage.Format_RGB888)
        image.fill(QtGui.QColor("white"))
        item = view.scene().addPixmap(QtGui.QPixmap.fromImage(image))
        view.setSceneRect(QtCore.QRectF(0, 0, 120, 80))
        quality = FocusedPageQuality(
            view, [doc], [{"slot": "main", "source": 0, "page": 0}],
            {}, {"main": item}, 1.0)
        before = item.sceneBoundingRect()
        view.scale(3, 3)
        quality.update_quality()
        assert item.pixmap().width() > 120
        after = item.sceneBoundingRect()
        assert abs(before.width() - after.width()) < 1
        assert abs(before.height() - after.height()) < 1
        view.close()
    del app


def test_render_scale_obeys_pixel_budget():
    with fitz.open(stream=_pdf_bytes(), filetype="pdf") as doc:
        assert render_scale(doc[0], 2.5) == 2.5
        assert render_scale(doc[0], 100) == 4.0
