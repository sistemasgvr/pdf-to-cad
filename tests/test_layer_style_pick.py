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


@pytest.fixture
def layered_dialog():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open()
    layers = {name: doc.add_ocg(name) for name in
              ('C-WATR-UNGD-E', 'C-ELEC-UNGD-E', 'G-ROAD', 'G-XREF')}
    page = doc.new_page(width=400, height=300)
    for name, a, b in [('C-WATR-UNGD-E', (30, 50), (180, 50)),
                       ('C-WATR-UNGD-E', (220, 100), (370, 100)),
                       ('C-ELEC-UNGD-E', (30, 150), (180, 150)),
                       ('G-ROAD', (30, 200), (180, 200)),
                       ('G-XREF', (30, 250), (180, 250)),
                       ('G-XREF', (220, 250), (370, 250))]:
        page.draw_line(a, b, color=(0, 0, 0), width=1, oc=layers[name])
    data = doc.tobytes()
    doc.close()
    doc = fitz.open(stream=data, filetype='pdf')
    dlg = SheetLayersDialog(None, doc, 0)
    dlg.show()
    app.processEvents()
    dlg._fit_view()
    yield dlg
    dlg.reject()
    dlg.deleteLater()
    app.processEvents()
    doc.close()


def test_layered_pdf_click_identifies_actual_layer_not_color(layered_dialog):
    dlg = layered_dialog
    camera = dlg.view.transform()
    center = dlg.view.mapToScene(dlg.view.viewport().rect().center())
    hidden = dlg.hidden_names()
    QtTest.QTest.mouseClick(dlg.view.viewport(), QtCore.Qt.LeftButton, pos=_point(dlg, 100, 50))
    item = dlg.tree.currentItem()
    assert item.data(0, _ROLE_NAME) == 'C-WATR-UNGD-E'
    assert item.parent().isExpanded() and item.isSelected()
    assert dlg._assignment_name == 'C-WATR-UNGD-E'
    assert dlg._hl_items[-1].path().boundingRect().bottom() == pytest.approx(100 * dlg._render_zoom())
    assert dlg.view.transform() == camera
    assert dlg.view.mapToScene(dlg.view.viewport().rect().center()) == center
    assert dlg.hidden_names() == hidden
    dlg._style_picker.select_at(_point(dlg, 100, 150))
    assert dlg.tree.currentItem().data(0, _ROLE_NAME) == 'C-ELEC-UNGD-E'


def test_layered_pdf_other_layers_and_tree_selection_highlight(layered_dialog):
    dlg = layered_dialog
    dlg._style_picker.select_at(_point(dlg, 100, 200))
    assert dlg.tree.currentItem().data(0, _ROLE_NAME) == 'G-ROAD'
    assert 'G-ROAD' in dlg.info.lbl_focus.text()
    dlg.tree.setCurrentItem(dlg._items_by_name['C-WATR-UNGD-E'][0])
    assert 'C-WATR-UNGD-E' in dlg.info.lbl_focus.text()


def test_layered_pdf_hidden_layer_is_not_pickable(layered_dialog):
    dlg = layered_dialog
    dlg._items_by_name['C-WATR-UNGD-E'][0].setCheckState(0, QtCore.Qt.Unchecked)
    dlg._style_picker.select_at(_point(dlg, 100, 50))
    assert dlg.tree.currentItem() is None
    dlg._timer.stop()


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_layered_pdf_pick_respects_camera_and_filter(layered_dialog, rotation):
    dlg = layered_dialog
    dlg._page.set_rotation(rotation)
    dlg._render(first=True)
    dlg.view.scale(1.5, 1.5)
    dlg.search.setText('otra capa')
    camera = dlg.view.transform()
    dlg._style_picker.select_at(_point(dlg, 100, 50))
    assert dlg.tree.currentItem().data(0, _ROLE_NAME) == 'C-WATR-UNGD-E'
    assert dlg.search.text() == ''
    assert dlg.view.transform() == camera


def test_shared_layer_pick_highlights_only_the_recognized_family(layered_dialog):
    from reconocimiento import recognition_letters
    from ui.asistente.layer_dialog import _ROLE_UTILITY
    dlg = layered_dialog
    paths = [d for d, _s in dlg._all_drawings() if d.get('layer') == 'G-XREF']
    layer = next(L for L in dlg._layers if L['name'] == 'G-XREF')
    layer['letter_utilities'] = ['AGUA', 'GAS']
    layer['letter_paths'] = {recognition_letters.path_key(d): u for d, u in zip(paths, ['AGUA', 'GAS'])}
    dlg._fill_list()
    dlg._style_picker.select_at(_point(dlg, 300, 250))
    item = dlg.tree.currentItem()
    assert item.data(0, _ROLE_NAME) == 'G-XREF' and item.data(0, _ROLE_UTILITY) == 'GAS'
    strong, _soft, _text = dlg._focus_sets({'layers': ['G-XREF'], 'path_utility': 'GAS'})
    assert set(strong) == {'GAS'} and len(strong['GAS']) == 1
    assert strong['GAS'][0]['rect'].x0 == 220


@pytest.fixture
def arbitrary_vector_dialog():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open()
    names = {n: doc.add_ocg(n) for n in ('Arquitectura|Ejes', 'G-PROF', 'Muebles')}
    pg = doc.new_page(width=500, height=400)
    pg.draw_line((30, 40), (200, 40), oc=names['Arquitectura|Ejes'])
    # PDF mixto: geometría sin capa junto a OCG de cualquier disciplina.
    pg.draw_line((30, 100), (200, 100), width=2)
    pg.draw_line((30, 130), (200, 130), width=2)
    pg.draw_bezier((30, 200), (80, 150), (160, 250), (200, 200), color=(1, 0, 0))
    pg.draw_rect(fitz.Rect(30, 300, 200, 350), fill=(0, 1, 0))
    pg.draw_rect(fitz.Rect(250, 200, 450, 350), oc=names['G-PROF'])
    pg.draw_line((270, 260), (400, 260), oc=names['Muebles'])
    data = doc.tobytes()
    doc.close()
    doc = fitz.open(stream=data, filetype='pdf')
    dlg = SheetLayersDialog(None, doc, 0)
    dlg.show()
    app.processEvents()
    dlg._fit_view()
    yield dlg
    dlg.reject()
    dlg.deleteLater()
    app.processEvents()
    doc.close()


def test_any_discipline_and_unlisted_layer_can_be_identified(arbitrary_vector_dialog):
    dlg = arbitrary_vector_dialog
    name = 'Arquitectura|Ejes'
    # Simular un nombre presente en los vectores que el catálogo OCG no anunció.
    dlg._layers_raw = [L for L in dlg._layers_raw if L['name'] != name]
    dlg._layers = dlg._effective_layers()
    dlg._fill_list()
    dlg._style_picker.select_at(_point(dlg, 100, 40))
    assert dlg.tree.currentItem().data(0, _ROLE_NAME) == name
    assert dlg._hl_items


def test_unlayered_vectors_in_mixed_pdf_get_virtual_style_without_changing_original(arbitrary_vector_dialog):
    from hoja import pdf_styles
    dlg = arbitrary_vector_dialog
    native = [(p.get('layer'), tuple(p['rect'])) for p in dlg._page.get_drawings()]
    dlg._style_picker.select_at(_point(dlg, 100, 100))
    name = dlg.tree.currentItem().data(0, _ROLE_NAME)
    assert name.startswith(pdf_styles.PREFIX)
    assert '2.00 pt' in dlg.tree.currentItem().text(0)
    assert dlg._hl_items[-1].path().boundingRect().bottom() == pytest.approx(130 * dlg._render_zoom())
    # La misma familia se puede volver a identificar desde el árbol.
    dlg.tree.setCurrentItem(dlg._items_by_name['Muebles'][0])
    dlg.tree.setCurrentItem(dlg._items_by_name[name][0])
    assert dlg._hl_items[-1].path().boundingRect().bottom() == pytest.approx(130 * dlg._render_zoom())
    assert [(p.get('layer'), tuple(p['rect'])) for p in dlg._page.get_drawings()] == native


@pytest.mark.parametrize('x,y', [(30, 200), (30, 320)])
def test_curves_and_shape_edges_are_pickable(arbitrary_vector_dialog, x, y):
    dlg = arbitrary_vector_dialog
    dlg._style_picker.select_at(_point(dlg, x, y))
    assert dlg.tree.currentItem() is not None
    assert dlg._hl_items


def test_profile_vectors_are_inspectable_even_when_recognition_excludes_them(arbitrary_vector_dialog):
    dlg = arbitrary_vector_dialog
    recognized = {d.get('layer') for d, _s in dlg._all_drawings()}
    assert 'Muebles' not in recognized
    dlg._style_picker.select_at(_point(dlg, 320, 260))
    assert dlg.tree.currentItem().data(0, _ROLE_NAME) == 'Muebles'
    assert dlg._hl_items
    assert {d.get('layer') for d, _s in dlg._all_drawings()} == recognized


def test_unclassified_segment_in_shared_layer_is_still_inspectable(layered_dialog):
    from reconocimiento import recognition_letters
    dlg = layered_dialog
    paths = [d for d, _s in dlg._all_drawings() if d.get('layer') == 'G-XREF']
    layer = next(L for L in dlg._layers if L['name'] == 'G-XREF')
    layer['letter_paths'] = {recognition_letters.path_key(paths[0]): 'AGUA'}
    dlg._style_picker.select_at(_point(dlg, 300, 250))
    assert dlg.tree.currentItem().data(0, _ROLE_NAME) == 'G-XREF'
    strong, _soft, _label = dlg._focus_sets({'layers': ['G-XREF'], 'identificar': True})
    assert sum(len(ds) for ds in strong.values()) == 2


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


def test_excluded_virtual_style_remains_pickable_because_its_ink_is_visible(style_dialog):
    dlg = style_dialog
    item = next(it for it in dlg._layer_items() if '#FF0000' in it.text(0))
    item.setCheckState(0, QtCore.Qt.Unchecked)
    dlg._style_picker.select_at(_point(dlg, 100, 50))
    assert dlg.tree.currentItem() is item
    assert item.checkState(0) == QtCore.Qt.Unchecked
    dlg._timer.stop()


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
    dlg._pick_cache = ((id(dlg._doc), dlg._page_index), [(original, shown)])
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
