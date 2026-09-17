"""Plan windows keep source coordinates and discard only geometry outside."""
import fitz
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtTest import QTest

import recognition
import organized_layer_dialog
from sheet_crop_dialog import SheetCropDialog
from sheet_crops import (drawing_polygon, move_rect, normalize, page_rect,
                         resize_corner, resize_side)


def test_crop_normalization_and_pdf_rectangle():
    assert normalize({"main": [0.8, 0.9, 0.1, 0.2],
                      "right": [0, 0, 1, 1]},
                     {"main": 0, "right": 1}) == {
        "main": [0.1, 0.2, 0.8, 0.9]}
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=100)
        assert page_rect(page, [0.1, 0.2, 0.8, 0.9]) == fitz.Rect(20, 20, 160, 90)


def test_narrow_area_keeps_its_direction_and_corner_cannot_flip():
    narrow = [0.45, 0.05, 0.452, 0.95]
    assert normalize({"main": narrow}) == {"main": narrow}
    rect = (45.0, 5.0, 46.0, 95.0)
    moved = move_rect(rect, 10, -20, (0, 0, 100, 100))
    assert moved == (55.0, 0.0, 56.0, 90.0)
    resized = resize_corner((45.0, 5.0, 48.0, 95.0), "tr", -100, 5,
                            (0, 0, 100, 100), minimum=2)
    assert resized == (45.0, 5.0, 47.0, 95.0)
    assert resize_side((20, 10, 120, 70), "top", 25,
                       (0, 0, 200, 100)) == (20, 25, 120, 70)
    assert resize_side((20, 10, 120, 70), "right", 140,
                       (0, 0, 200, 100)) == (20, 10, 140, 70)
    assert resize_side((20, 10, 120, 70), "bottom", 85,
                       (0, 0, 200, 100)) == (20, 10, 120, 85)
    assert resize_side((20, 10, 120, 70), "left", 200,
                       (0, 0, 200, 100)) == (118, 10, 120, 70)


def test_recognition_paths_are_clipped_to_selected_plan_area():
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=100)
        ocg = doc.add_ocg("C-ELEC-UNGD-E")
        page.draw_line((0, 25), (200, 25), oc=ocg)
        page.draw_line((0, 80), (200, 80), oc=ocg)
        crop = page_rect(page, [0.25, 0.1, 0.75, 0.5])
        lines, vaults, counts, _kinds = recognition.gather_paths(
            page, recognition.classify_ocg, crop_polygon=drawing_polygon(page, crop))
        assert len(lines) == 1
        assert not vaults
        assert counts == {"C-ELEC-UNGD-E": 1}
        segment = lines[0]["items"][0]
        assert segment[0] == "l"
        assert abs(segment[1][0] - 50) < 1e-6
        assert abs(segment[2][0] - 150) < 1e-6
        result = recognition.recognize_page(
            "unused.pdf", doc=doc, crop=[0.25, 0.1, 0.75, 0.5], zoom=1.0)
        assert sum(row["path_count"] for row in result.ocg_summary) == 1
        for polyline in result.drawable:
            assert all(-1e-6 <= x <= 100 + 1e-6 and -1e-6 <= y <= 40 + 1e-6
                       for x, y in polyline.pts_pdf)


def test_rotated_crop_polygon_maps_to_unrotated_drawing_coordinates():
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=100)
        page.set_rotation(90)
        crop = page_rect(page, [0, 0, 0.5, 1])
        polygon = drawing_polygon(page, crop)
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        assert max(xs) - min(xs) == 200
        assert max(ys) - min(ys) == 50


def test_crop_picker_and_arranged_layer_preview(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=100)
        doc.new_page(width=200, height=100)
        page = doc[0]
        picker = SheetCropDialog(None, page, "Principal")
        picker.view.set_selection(QtCore.QRectF(20, 10, 100, 60))
        picker._accept_selection()
        assert picker.result_crop == [0.1, 0.1, 0.6, 0.7]
        picker.close()

        narrow_picker = SheetCropDialog(None, page, "Principal")
        narrow_picker.view.set_selection(QtCore.QRectF(40, 10, 3, 70))
        narrow_picker.view._active_handle = "center"
        narrow_picker.view.keyPressEvent(QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Right, QtCore.Qt.ControlModifier))
        assert abs(narrow_picker.view._selection.left() - 40.1) < 1e-6
        assert narrow_picker.view._selection.width() == 3
        narrow_picker._accept_selection()
        assert abs((narrow_picker.result_crop[2] - narrow_picker.result_crop[0]) - 3 / 200) < 1e-9
        narrow_picker.close()

        sources = [{"name": "plan.pdf", "start": 0, "count": 2}]
        layout = {"main": 0, "right": 1}
        dialog = organized_layer_dialog.OrganizedLayersDialog(
            None, [doc], sources, layout, {})
        assert not dialog.btn_crop.isEnabled()
        dialog.show()
        app.processEvents()
        main_point = dialog.view.mapFromScene(
            dialog._pix_items["main"].sceneBoundingRect().center())
        QTest.mouseClick(dialog.view.viewport(), QtCore.Qt.LeftButton, pos=main_point)
        assert dialog._selected_slot == "main"
        assert dialog.btn_crop.isEnabled()
        right_point = dialog.view.mapFromScene(
            dialog._pix_items["right"].sceneBoundingRect().center())
        QTest.mouseClick(dialog.view.viewport(), QtCore.Qt.LeftButton, pos=right_point)
        assert dialog._selected_slot == "right"
        QTest.mouseClick(dialog.view.viewport(), QtCore.Qt.LeftButton, pos=main_point)
        assert dialog._selected_slot == "main"
        before = dialog._pix_items["main"].pixmap().width()
        monkeypatch.setattr(organized_layer_dialog, "choose_sheet_crop",
                            lambda *_args: [0.1, 0.1, 0.6, 0.7])
        dialog._choose_crop()
        assert dialog._pix_items["main"].pixmap().width() < before
        dialog.accept()
        assert dialog.result_crops["main"] == [0.1, 0.1, 0.6, 0.7]
        dialog.close()
    del app


def test_crop_handle_drag_moves_without_resizing(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=100)
        dialog = SheetCropDialog(None, page, "Principal")
        dialog.show()
        app.processEvents()
        view = dialog.view
        view.set_selection(QtCore.QRectF(20, 10, 100, 60))
        centre = view.mapFromScene(view._selection.center())
        QTest.mousePress(view.viewport(), QtCore.Qt.LeftButton, pos=centre)
        QTest.mouseMove(view.viewport(), centre + QtCore.QPoint(20, 0))
        QTest.mouseRelease(view.viewport(), QtCore.Qt.LeftButton,
                           pos=centre + QtCore.QPoint(20, 0))
        assert view._selection.left() > 20
        assert view._selection.width() == 100
        assert view._selection.height() == 60
        corner = view.mapFromScene(view._selection.bottomRight())
        QTest.mousePress(view.viewport(), QtCore.Qt.LeftButton, pos=corner)
        QTest.mouseMove(view.viewport(), corner + QtCore.QPoint(15, 10))
        QTest.mouseRelease(view.viewport(), QtCore.Qt.LeftButton,
                           pos=corner + QtCore.QPoint(15, 10))
        assert view._selection.width() > 100
        assert view._selection.height() > 60
        width = view._selection.width()
        bottom = view._selection.bottom()
        top_handle = view.mapFromScene(view._handles["top"].pos())
        QTest.mousePress(view.viewport(), QtCore.Qt.LeftButton, pos=top_handle)
        QTest.mouseMove(view.viewport(), top_handle + QtCore.QPoint(0, 15))
        QTest.mouseRelease(view.viewport(), QtCore.Qt.LeftButton,
                           pos=top_handle + QtCore.QPoint(0, 15))
        assert view._selection.top() > 10
        assert view._selection.width() == width
        assert view._selection.bottom() == bottom
        dialog.close()
    del app
