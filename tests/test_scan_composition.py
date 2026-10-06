"""Scanned sheets: polygon clipping, straightening, persistence and manual flow."""
import io
import math
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
import fitz
from PIL import Image
from PySide6 import QtCore, QtWidgets, QtTest
import composite as C
from composite_dialog import CompositeDialog
from app_window import Main


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def scan_pdf(rotation=0):
    stream = io.BytesIO()
    Image.new("RGB", (300, 200), "black").save(stream, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_image(page.rect, stream=stream.getvalue())
    page.set_rotation(rotation)
    return doc


@pytest.mark.parametrize("page_rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("rotation", [0, 7.5, 90])
def test_polygon_pdf_mask_survives_rotation(page_rotation, rotation):
    doc = scan_pdf(page_rotation)
    polygon = [(0.2, 0.1), (0.9, 0.2), (0.8, 0.9), (0.1, 0.8)]
    piece = C.Piece(0, 0, [0.1, 0.1, 0.9, 0.9], rotation=rotation, polygon=polygon)
    comp = C.Composite([piece], manual=True, bridges=False)
    restored = C.Composite.from_dict(comp.to_dict())
    assert restored.manual and restored.pieces[0].polygon == polygon
    built = C.build_document(restored, [doc])
    size = (doc[0].rect.width, doc[0].rect.height)
    _, _, dx, dy = C.sheet_geometry(comp, lambda p: size)
    fn = C.piece_map(piece, size, comp.target_scale())
    pix = built[0].get_pixmap()
    for x, y, expected in [(0.5, 0.5, 0), (0.13, 0.13, 255)]:
        px, py = fn(x*size[0], y*size[1])
        assert pix.pixel(round(px+dx), round(py+dy)) == (expected,)*3
    built.close()
    doc.close()


def test_manual_dialog_crop_and_straighten(app):
    doc = scan_pdf()
    dlg = CompositeDialog(None, [{"name": "scan.pdf", "data": doc.tobytes()}], None, {}, manual=True)
    try:
        dlg.crop.set_selection(QtCore.QRectF(30, 20, 240, 160))
        dlg.crop._move_corner("tl", QtCore.QPointF(60, 30))
        dlg._take_area(False)
        piece = dlg.comp.pieces[0]
        assert piece.polygon[0] == (0.2, 0.15)
        assert not dlg.comp.bridges
        assert dlg.btn_ok.text() == "Importar hoja al editor"
        preview = dlg.view.render_piece(piece, 1).toImage()
        assert preview.pixelColor(3, 3).red() == 255
        assert preview.pixelColor(120, 80).red() == 0
        dlg._on_straighten(0, (0, 0), (100, 10))
        assert piece.rotation == pytest.approx(math.degrees(math.atan2(10, 100)))
        assert dlg.view.measure.result is None and dlg.view.measure.mode is None
        # Crossed corners are rejected instead of creating an invalid crop.
        previous = list(dlg.crop.polygon)
        dlg.crop._move_corner("tl", QtCore.QPointF(299, 199))
        assert dlg.crop.polygon == previous
    finally:
        dlg.close_docs()
        doc.close()


def test_manual_flow_skips_layers_and_recognition(monkeypatch):
    import app_window
    comp = C.Composite([C.Piece(0, 1, [0, 0, 1, 1])], manual=True, bridges=False)
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", lambda *a, **kw: (comp, [], {}))
    def unexpected(*args, **kwargs):
        pytest.fail("Manual composition must skip layers and recognition")
    monkeypatch.setattr(app_window.layer_dialog, "choose_sheet_layers", unexpected)
    win = SimpleNamespace(src_pdfs=[], composite=None, hidden_ocgs_by_source={}, page_idx=1,
                          _apply_composite=lambda: None, _info=lambda msg: None,
                          _start_recognition=unexpected)
    assert Main._wizard_sheet_flow(win, 1, manual=True)
    assert win._dirty and not win._recog_ready


def test_detected_scan_opens_manual_compositor(monkeypatch):
    import app_window
    doc = scan_pdf()
    calls = []
    win = QtWidgets.QWidget()
    win.doc, win.pdf_path = doc, "scan.pdf"
    win._load_sheet_busy = lambda index: pytest.fail("Scan must enter composition first")
    win._info = lambda message: None
    win._wizard_sheet_flow = lambda index, **kw: calls.append((index, kw)) or True
    try:
        Main._run_recognition_wizard(win)
        assert calls == [(0, {"manual": True})]
    finally:
        doc.close()


def test_straighten_clicks_and_pending_crop_commit(app):
    doc = scan_pdf()
    dlg = CompositeDialog(None, [{"name": "scan.pdf", "data": doc.tobytes()}], None, {}, manual=True)
    try:
        dlg._take_area(True)
        dlg.show()
        app.processEvents()
        dlg.view.fit_all()
        picked = []
        dlg.view.measure.straighten.connect(lambda *args: picked.append(args))
        dlg.btn_straighten.setChecked(True)
        a, b = QtCore.QPointF(80, 60), QtCore.QPointF(90, 172)      # casi vertical
        for p in (a, b):
            QtTest.QTest.mouseClick(dlg.view.viewport(), QtCore.Qt.LeftButton,
                                   pos=dlg.view.mapFromScene(p))
        index, measured_a, measured_b = picked[0]
        assert index == 0
        # eje automático: una línea casi vertical se endereza vertical
        expected = C.ruler_correction(measured_a, measured_b, vertical=True)
        assert abs(expected) < 10
        assert dlg.comp.pieces[0].rotation == pytest.approx(expected % 360)
        assert not dlg.btn_straighten.isChecked() and dlg.view.measure.mode is None
        dlg.crop._move_corner("tl", QtCore.QPointF(30, 20))
        assert dlg._crop_timer.isActive()
        dlg.accept()
        assert dlg.comp.pieces[0].polygon[0] == (0.1, 0.1)
    finally:
        dlg.close_docs()
        doc.close()


def test_overlay_ruler_stays_fixed_while_aligning_sheets(app):
    doc = scan_pdf()
    dlg = CompositeDialog(None, [{"name": "scan.pdf", "data": doc.tobytes()}], None, {}, manual=True)
    try:
        dlg._take_area(True)            # la hoja a la vista ya es la pieza 1 (en edición)
        dlg.view.select(-1)             # «Nueva pieza»: la siguiente es otra pieza
        dlg._take_area(True)
        dlg.btn_rule.setChecked(True)
        ruler = dlg.view.alignment_ruler
        ruler.configure(length=1200, width=90, angle=0, locked=True)
        ruler.setPos(0, 100)
        second = dlg.comp.pieces[1]
        dlg.view.select(1)
        old_y = second.y
        QtTest.QTest.keyClick(dlg.view, QtCore.Qt.Key_Up, QtCore.Qt.ControlModifier)
        assert second.y == pytest.approx(old_y-0.1)
        assert ruler.pos() == QtCore.QPointF(0, 100)
        assert ruler.isVisible() and ruler.locked
        restored = C.Composite.from_dict(dlg.comp.to_dict())
        assert restored.alignment_ruler == dlg.comp.alignment_ruler
        other = CompositeDialog(None, dlg.sources, restored, {}, manual=True)
        try:
            assert other.view.alignment_ruler.pos() == ruler.pos()
            assert other.view.alignment_ruler.length == 1200
            assert other.view.alignment_ruler.width == 90
            assert other.btn_rule.isChecked()
        finally:
            other.close_docs()
        # Guides never enter the PDF image.
        built = C.build_document(dlg.comp, dlg.docs)
        assert not built[0].get_drawings()
        built.close()
    finally:
        dlg.close_docs()
        doc.close()


def test_protractor_rotation_keeps_sheet_center_and_ruler(app):
    doc = scan_pdf()
    dlg = CompositeDialog(None, [{"name": "scan.pdf", "data": doc.tobytes()}], None, {}, manual=True)
    try:
        dlg._take_area(True)
        dlg.btn_rule.setChecked(True)
        dlg.btn_protractor.setChecked(True)
        ruler_pos = dlg.view.alignment_ruler.pos()
        center = dlg.view.protractor.pos()
        dlg._on_protractor_angle(17.25)
        assert dlg.comp.pieces[0].rotation == 17.25
        assert dlg.view.protractor.pos() == center
        assert dlg.view.alignment_ruler.pos() == ruler_pos
        assert dlg.spn_angle.value() == 17.25
        handle = dlg.view.protractor.handle_point()
        assert dlg.view.protractor.shape().contains(handle)
        assert not dlg.view.protractor.shape().contains(QtCore.QPointF())
    finally:
        dlg.close_docs()
        doc.close()


def test_overlay_ruler_can_be_dragged_without_moving_sheet(app):
    doc = scan_pdf()
    dlg = CompositeDialog(None, [{"name": "scan.pdf", "data": doc.tobytes()}], None, {}, manual=True)
    try:
        dlg._take_area(True)
        dlg.show()
        app.processEvents()
        dlg.view.fit_all()
        dlg.btn_rule.setChecked(True)
        ruler = dlg.view.alignment_ruler
        ruler.configure(length=280, width=35)
        ruler.setPos(0, 100)
        start = dlg.view.mapFromScene(ruler.mapToScene(QtCore.QPointF(150, -20)))
        end = start+QtCore.QPoint(10, 20)
        QtTest.QTest.mousePress(dlg.view.viewport(), QtCore.Qt.LeftButton, pos=start)
        QtTest.QTest.mouseMove(dlg.view.viewport(), end)
        QtTest.QTest.mouseRelease(dlg.view.viewport(), QtCore.Qt.LeftButton, pos=end)
        assert ruler.pos() != QtCore.QPointF(0, 100)
        assert dlg.comp.pieces[0].x == 0 and dlg.comp.pieces[0].y == 0
        assert dlg.comp.alignment_ruler["y"] == ruler.y()
    finally:
        dlg.close_docs()
        doc.close()


@pytest.mark.parametrize("a,b,vertical,expected", [
    ((0, 0), (100, 10), False, math.degrees(math.atan2(10, 100))),
    ((100, 10), (0, 0), False, math.degrees(math.atan2(10, 100))),
    ((0, 0), (10, 100), True, -math.degrees(math.atan2(10, 100))),
    ((0, 0), (0, 0), False, None)])
def test_ruler_direction(a, b, vertical, expected):
    result = C.ruler_correction(a, b, vertical)
    assert result is None if expected is None else result == pytest.approx(expected)
