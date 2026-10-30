"""Selección bidireccional por tinta y aislamiento del minimapa del editor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import fitz
import pytest
from PySide6 import QtCore, QtTest, QtWidgets

from ui.asistente.layer_dialog import SheetLayersDialog, _ROLE_NAME
from ui.ventana import ventana_flotantes
from ui.ventana.ventana_hojas import colocar_minimapa
from ui.comun.widgets import MiniMap, ZoomPanView


@pytest.fixture
def style_dialog():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    for a, b in [((30, 50), (180, 50)), ((220, 200), (370, 200))]:
        page.draw_line(a, b, color=(1, 0, 0), width=1)
    # Su caja contiene (100, 100), pero su tinta pasa lejos de ese punto.
    page.draw_line((30, 80), (180, 230), color=(0, 0, 1), width=1)
    page.draw_line((30, 150), (180, 150), color=(0, 1, 0), width=1)
    dlg = SheetLayersDialog(None, doc, 0)
    dlg.show()
    app.processEvents()
    dlg._fit_view()
    yield dlg
    dlg.reject()
    dlg.deleteLater()
    app.processEvents()
    doc.close()


def _point(dlg, x, y):
    p = fitz.Point(x, y) * dlg._page.rotation_matrix
    return dlg.view.mapFromScene(QtCore.QPointF(p.x * dlg._render_zoom(), p.y * dlg._render_zoom()))


def test_click_pdf_selects_whole_family_without_moving_camera(style_dialog):
    dlg = style_dialog
    hidden = dlg.hidden_names()
    camera = dlg.view.transform()
    center = dlg.view.mapToScene(dlg.view.viewport().rect().center())
    QtTest.QTest.mouseClick(dlg.view.viewport(), QtCore.Qt.LeftButton, pos=_point(dlg, 100, 50))
    item = dlg.tree.currentItem()
    assert item is not None and item.isSelected() and item.parent().isExpanded()
    assert '#FF0000' in item.text(0)
    assert dlg._assignment_name == item.data(0, _ROLE_NAME)
    assert dlg.view.transform() == camera
    assert dlg.view.mapToScene(dlg.view.viewport().rect().center()) == center
    assert dlg.hidden_names() == hidden
    # El halo incluye ambas líneas rojas, no solo la pulsada.
    assert dlg._hl_items[-1].path().boundingRect().bottom() >= 200 * dlg._render_zoom()


def test_tree_selection_has_visual_state_and_keyboard_highlight(style_dialog):
    dlg = style_dialog
    item = next(it for it in dlg._layer_items() if '#00FF00' in it.text(0))
    dlg.tree.setCurrentItem(item)
    assert item.isSelected()
    assert dlg._hl_items and '#00FF00' in dlg.info.lbl_focus.text()


def test_empty_space_and_pan_do_not_select_bounding_box(style_dialog):
    dlg = style_dialog
    QtTest.QTest.mouseClick(dlg.view.viewport(), QtCore.Qt.LeftButton, pos=_point(dlg, 100, 100))
    assert dlg.tree.currentItem() is None
    QtTest.QTest.mouseClick(dlg.view.viewport(), QtCore.Qt.MiddleButton, pos=_point(dlg, 100, 50))
    assert dlg.tree.currentItem() is None


def test_pick_uses_clipped_ink(style_dialog):
    dlg = style_dialog
    drawings = dlg._all_drawings()
    original, _ = next((d, s) for d, s in drawings if d.get('color') == (1, 0, 0))
    # La parte roja que sigue en su caja original quedó fuera del recorte.
    shown = dict(original, items=[('l', fitz.Point(30, 50), fitz.Point(60, 50))])
    dlg._drawings = [(original, shown)]
    dlg._style_picker.select_at(_point(dlg, 100, 50))
    assert dlg.tree.currentItem() is None
    dlg._style_picker.select_at(_point(dlg, 45, 50))
    assert '#FF0000' in dlg.tree.currentItem().text(0)


def test_calibrating_does_not_pick_styles(style_dialog):
    dlg = style_dialog
    # El filtro de calibración tiene prioridad sobre la selección.
    dlg._calib_filter = QtCore.QObject(dlg)
    try:
        QtTest.QTest.mouseClick(dlg.view.viewport(), QtCore.Qt.LeftButton, pos=_point(dlg, 100, 50))
        assert dlg.tree.currentItem() is None
    finally:
        dlg._calib_filter = None


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_pick_respects_rotation_zoom_and_search(style_dialog, rotation):
    dlg = style_dialog
    dlg._page.set_rotation(rotation)
    dlg._drawings = None
    dlg._render(first=True)
    dlg.search.setText('no coincide')
    dlg.view.scale(1.5, 1.5)
    dlg._style_picker.select_at(_point(dlg, 100, 50))
    assert '#FF0000' in dlg.tree.currentItem().text(0)
    assert not dlg.tree.currentItem().isHidden()
    assert dlg.search.text() == ''


def test_editor_overlays_hide_while_modal_assistant_is_open():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = QtWidgets.QMainWindow()
    canvas = ZoomPanView()
    canvas.pixmap_item = object()
    win.setCentralWidget(canvas)
    win.canvas = canvas
    win.show()
    app.processEvents()
    assert ventana_flotantes._a_la_vista(win)
    mm = win._mm_editor = MiniMap(canvas)
    mm.setParent(win, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
    mm.puede_verse = lambda: ventana_flotantes._a_la_vista(win)
    win._mm_quiere = True
    mm.set_layout([(QtCore.QRectF(0, 0, 400, 300), 'Hoja 1')], QtCore.QRectF(0, 0, 400, 300))
    colocar_minimapa(win)
    assert mm.isVisible()
    assistant = QtWidgets.QDialog(win)
    assistant.setWindowModality(QtCore.Qt.ApplicationModal)
    assistant.show()
    app.processEvents()
    assert not ventana_flotantes._a_la_vista(win)
    colocar_minimapa(win)
    assert not mm.isVisible()
    assistant.hide()
    app.processEvents()
    assert ventana_flotantes._a_la_vista(win)
    colocar_minimapa(win)
    assert mm.isVisible()
    win.close()
