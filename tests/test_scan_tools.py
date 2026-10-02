"""Herramientas de la hoja compuesta para escaneos (pedido del usuario 2026-10-02):
barra única, transportador con imán y ajuste fino, medir/calibrar, enderezar
con eje automático y «Fundir bordes» (vista y PDF)."""
import io
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import fitz
import pytest
from PIL import Image, ImageDraw
from PySide6 import QtCore, QtWidgets, QtTest

import composite as C
import composite_scan as CS
from alignment_tools import AngleDrag
from composite_dialog import CompositeDialog


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def line_scan(pages=1, paper=236):
    """Escaneo gris claro con una raya negra vertical en x=100 (de 300×200 pt)."""
    doc = fitz.open()
    for _ in range(pages):
        img = Image.new("RGB", (300, 200), (paper,) * 3)
        ImageDraw.Draw(img).line([(100, 0), (100, 200)], fill="black", width=4)
        s = io.BytesIO(); img.save(s, format="PNG")
        page = doc.new_page(width=300, height=200)
        page.insert_image(page.rect, stream=s.getvalue())
    return doc


def open_dialog(doc):
    return CompositeDialog(None, [{"name": "scan.pdf", "data": doc.tobytes()}], None, {}, manual=True)


def center(dlg, i):
    p = dlg.comp.pieces[i]
    w, h = C.piece_size(p, dlg.view.page_size(p), dlg.comp.target_scale())
    return p.x + w / 2, p.y + h / 2


# ── puro ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("value,fine,coarse,expected,axis", [
    (-0.33, False, False, 0.0, True),      # el caso reportado: volver a 0 con el puntero
    (0.6, False, False, 0.0, True),
    (1.3, False, False, 1.3, False),
    (89.4, False, False, 90.0, True),
    (-179.5, False, False, 180.0, True),
    (-0.33, True, False, -0.33, False),    # Ctrl: el imán no estorba los ajustes finos
    (0.03, True, False, 0.0, True),
    (47.0, False, True, 45.0, False),      # Shift: pasos de 15°
    (0.123, False, False, 0.0, True),
    (12.34, False, False, 12.3, False),
])
def test_snap_angle(value, fine, coarse, expected, axis):
    out, on_axis = CS.snap_angle(value, fine=fine, coarse=coarse)
    assert out == pytest.approx(expected) and on_axis == axis


def test_angle_drag_fine_gain_and_magnet():
    d = AngleDrag(0.0, 0.0)
    assert d.move(10.0, QtCore.Qt.ControlModifier)[0] == pytest.approx(1.0)   # ×0.1
    assert d.move(10.7, QtCore.Qt.NoModifier)[0] == pytest.approx(1.7)
    d = AngleDrag(-0.33, 0.0)
    assert d.move(0.2, QtCore.Qt.NoModifier) == (0.0, True)


def test_nearest_axis_and_auto_straighten():
    assert CS.nearest_axis(91.2) == 90.0 and CS.nearest_axis(-44) == 0.0
    assert C.ruler_correction((0, 0), (100, 3), None) == pytest.approx(math.degrees(math.atan2(3, 100)))
    assert C.ruler_correction((0, 0), (4, 100), None) == pytest.approx(
        C.ruler_correction((0, 0), (4, 100), True))


def test_rotate_and_scale_keep_pivot():
    piece = C.Piece(0, 0, [0.1, 0.2, 0.8, 0.9], x=40, y=-10, rotation=12, src_scale=20 / 72)
    size, target = (300.0, 200.0), 20 / 72
    pivot = (120.0, 60.0)
    src = C.piece_unmap(piece, size, target)(*pivot)
    CS.rotate_piece(piece, size, target, -3.5, pivot)
    assert piece.rotation == pytest.approx(356.5)
    assert C.piece_map(piece, size, target)(*src) == pytest.approx(pivot)
    CS.scale_piece(piece, size, target, 25 / 72, pivot)
    assert C.piece_map(piece, size, target)(*src) == pytest.approx(pivot)
    assert CS.calibrated_scale(20 / 72, 50.0, 100.0) == pytest.approx(40 / 72)
    assert CS.calibrated_scale(20 / 72, 0.0, 100.0) is None


def test_seam_blend_is_saved():
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1])], manual=True)
    assert comp.blends() and C.Composite.from_dict(comp.to_dict()).seam_blend
    comp.seam_blend = False
    assert not C.Composite.from_dict(comp.to_dict()).blends()
    assert not C.Composite(manual=False).blends()       # el PDF vectorial no se toca


# ── PDF ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("blend", [True, False])
def test_seam_blend_in_pdf_keeps_ink_under_overlap(blend):
    """La pieza B (papel gris) se superpone a la raya de A: fundida, la raya
    sigue a la vista y el papel de la superposición no se oscurece."""
    doc = line_scan()
    a = C.Piece(0, 0, [0, 0, 1, 1])
    b = C.Piece(0, 0, [0, 0, 1, 1], x=60.0)
    comp = C.Composite([a, b], manual=True, bridges=False, seam_blend=blend)
    built = C.build_document(comp, [doc])
    _, _, dx, dy = C.sheet_geometry(comp, lambda p: (300.0, 200.0))
    pix = built[0].get_pixmap()
    ink = pix.pixel(round(100 + dx), round(100 + dy))       # raya de A, bajo B
    paper = pix.pixel(round(200 + dx), round(100 + dy))     # papel de A y de B
    assert ink == ((0, 0, 0) if blend else (236, 236, 236))
    assert paper == (236, 236, 236)
    built.close(); doc.close()


# ── diálogo ─────────────────────────────────────────────────────────────
def test_single_toolbar_row(app):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        bar = dlg.tool_bar
        for b in (dlg.btn_rule, dlg.btn_protractor, dlg.btn_measure, dlg.btn_straighten,
                  dlg.btn_blend, dlg.piece_tools):
            assert b.parent() is bar
        assert not dlg.findChildren(QtWidgets.QCheckBox)       # sin casilla «Vertical»
        assert dlg.btn_rule.popupMode() == QtWidgets.QToolButton.MenuButtonPopup
        assert dlg.ruler_lock in dlg.btn_rule.menu().actions()
        assert dlg.btn_blend.isChecked()
        bar.resize(320, bar.height()); bar._fit()
        assert bar.compact and dlg.btn_measure.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly
        bar.resize(2400, bar.height()); bar._fit()
        assert not bar.compact and dlg.btn_measure.toolButtonStyle() == QtCore.Qt.ToolButtonTextBesideIcon
    finally:
        dlg.close_docs(); doc.close()


def test_protractor_handle_snaps_back_to_zero(app):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg.view.fit_all()
        dlg.view.select(0)
        dlg.btn_protractor.setChecked(True)
        c0 = center(dlg, 0)
        dlg._on_protractor_angle(-0.33)
        assert dlg.comp.pieces[0].rotation == pytest.approx(359.67)
        app.processEvents()
        prot = dlg.view.protractor
        handle = dlg.view.mapFromScene(prot.pos()) + prot.handle_point().toPoint()
        vp = dlg.view.viewport()
        QtTest.QTest.mousePress(vp, QtCore.Qt.LeftButton, pos=handle)
        QtTest.QTest.mouseMove(vp, handle + QtCore.QPoint(0, -1))      # ~0.5° hacia arriba
        QtTest.QTest.mouseRelease(vp, QtCore.Qt.LeftButton, pos=handle + QtCore.QPoint(0, -1))
        assert dlg.comp.pieces[0].rotation % 360 == pytest.approx(0.0)
        assert prot.on_axis
        assert center(dlg, 0) == pytest.approx(c0)                     # gira sobre su centro
        dlg._on_protractor_angle(93.4)
        app.processEvents()
        handle = dlg.view.mapFromScene(prot.pos()) + prot.handle_point().toPoint()
        QtTest.QTest.mouseDClick(vp, QtCore.Qt.LeftButton, pos=handle)
        assert dlg.comp.pieces[0].rotation == pytest.approx(90.0)       # al eje más cercano
    finally:
        dlg.close_docs(); doc.close()


def test_keys_rotate_selected_piece(app):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg.view.select(0)
        c0 = center(dlg, 0)
        QtTest.QTest.keyClick(dlg.view, QtCore.Qt.Key_Plus)
        assert dlg.comp.pieces[0].rotation == pytest.approx(0.1)
        QtTest.QTest.keyClick(dlg.view, QtCore.Qt.Key_Minus, QtCore.Qt.ControlModifier)
        assert dlg.comp.pieces[0].rotation == pytest.approx(0.09)
        QtTest.QTest.keyClick(dlg.view, QtCore.Qt.Key_Asterisk)      # Shift + «+» en teclado español
        assert dlg.comp.pieces[0].rotation == pytest.approx(1.09)
        assert center(dlg, 0) == pytest.approx(c0)
    finally:
        dlg.close_docs(); doc.close()


def test_measure_then_calibrate_whole_sheet(app, monkeypatch):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg.view.fit_all()
        dlg.btn_measure.setChecked(True)
        vp = dlg.view.viewport()
        for p in (QtCore.QPointF(50, 100), QtCore.QPointF(250, 100)):
            QtTest.QTest.mouseClick(vp, QtCore.Qt.LeftButton, pos=dlg.view.mapFromScene(p))
        index, a, b = dlg.view.measure.result
        assert index == 0 and dlg.btn_calibrate.isVisibleTo(dlg)
        measured = math.hypot(b[0] - a[0], b[1] - a[1]) * dlg.comp.target_scale()
        assert "ft" in dlg.lbl_status.text()
        old = dlg.comp.pieces[0].src_scale
        pos = (dlg.comp.pieces[0].x, dlg.comp.pieces[0].y)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble",
                            staticmethod(lambda *args, **kw: (measured * 2, True)))
        dlg.btn_calibrate.click()
        piece = dlg.comp.pieces[0]
        assert piece.src_scale == pytest.approx(old * 2)
        # una sola hoja: la hoja compuesta adopta la escala y nada se mueve
        assert dlg.comp.scale_ft_per_pt is None and (piece.x, piece.y) == pos
        assert dlg._scale_cache[(0, 0)] == pytest.approx(old * 2)
        assert '1" = 40' in dlg.lbl_summary.text()
    finally:
        dlg.close_docs(); doc.close()


def test_calibrate_one_page_keeps_the_rest(app):
    doc = line_scan(pages=2)
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg.lst_pages.setCurrentRow(1)
        dlg._take_area(True)
        other = C.Piece.from_dict(dlg.comp.pieces[1].to_dict())
        old_target = dlg.comp.target_scale()
        dlg.apply_page_scale(0, 0, old_target * 1.25, pivot=(0, (10.0, 10.0)))
        assert dlg.comp.target_scale() == pytest.approx(old_target)
        p0, p1 = dlg.comp.pieces
        assert C.piece_factor(p0, old_target) == pytest.approx(1.25)
        assert C.piece_map(p0, (300.0, 200.0), old_target)(10.0, 10.0) == pytest.approx((10.0, 10.0))
        assert p1.to_dict() == other.to_dict()
        assert dlg.cmb_scale.isVisible() or dlg.cmb_scale.count() == 2
    finally:
        dlg.close_docs(); doc.close()


def test_esc_leaves_tool_without_closing_dialog(app):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg.btn_straighten.setChecked(True)
        assert dlg.btn_measure.isChecked() is False
        dlg.btn_measure.setChecked(True)                 # se excluyen
        assert not dlg.btn_straighten.isChecked() and dlg.view.measure.mode == "measure"
        QtTest.QTest.keyClick(dlg.view, QtCore.Qt.Key_Escape)
        assert dlg.isVisible() and dlg.view.measure.mode is None
        assert not dlg.btn_measure.isChecked()
    finally:
        dlg.close_docs(); doc.close()


def test_ruler_rotation_handle_snaps_and_hides_when_locked(app):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg.view.fit_all()
        dlg.btn_rule.setChecked(True)
        ruler = dlg.view.alignment_ruler
        ruler.configure(length=200, width=30, angle=0)
        ruler.setPos(50, 150)
        app.processEvents()
        vp = dlg.view.viewport()
        origin = dlg.view.mapFromScene(ruler.mapToScene(QtCore.QPointF(0, 0)))
        handle = dlg.view.mapFromScene(ruler.mapToScene(QtCore.QPointF(200, 0)))
        r = math.hypot(handle.x() - origin.x(), handle.y() - origin.y())
        target = origin + QtCore.QPoint(1, -round(r))          # casi vertical (≈89.7°)
        QtTest.QTest.mousePress(vp, QtCore.Qt.LeftButton, pos=handle)
        QtTest.QTest.mouseMove(vp, target)
        QtTest.QTest.mouseRelease(vp, QtCore.Qt.LeftButton, pos=target)
        assert ruler.angle() == pytest.approx(90.0)
        assert dlg.comp.alignment_ruler["angle"] == pytest.approx(90.0)
        dlg.ruler_lock.setChecked(True)
        assert not ruler.handle.isVisible()
    finally:
        dlg.close_docs(); doc.close()


def test_blend_view_shows_ink_under_overlap(app):
    doc = line_scan()
    dlg = open_dialog(doc)
    try:
        dlg._take_area(True)
        dlg._take_area(True)
        dlg.comp.pieces[1].x, dlg.comp.pieces[1].y = 60.0, 0.0
        dlg.view.refresh_all()
        dlg.show(); app.processEvents()
        dlg.view.scene().clearSelection()
        dlg.view.fitInView(QtCore.QRectF(0, 0, 360, 200), QtCore.Qt.KeepAspectRatio)
        app.processEvents()
        at = dlg.view.mapFromScene(QtCore.QPointF(100, 100))
        paper = dlg.view.mapFromScene(QtCore.QPointF(200, 100))
        img = dlg.view.viewport().grab().toImage()
        assert img.pixelColor(at).value() < 80                  # raya de A bajo el papel de B
        assert abs(img.pixelColor(paper).value() - 236) <= 3    # la superposición no oscurece
        dlg.btn_blend.setChecked(False)
        app.processEvents()
        img = dlg.view.viewport().grab().toImage()
        assert img.pixelColor(at).value() > 200                 # sin fundir, B la tapa
    finally:
        dlg.close_docs(); doc.close()
