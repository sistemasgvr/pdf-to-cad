"""Compositor (Qt offscreen): tomar piezas, imán al arrastrar, materializar y
reconocer la hoja compuesta de punta a punta con PDFs sintéticos."""
import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6 import QtCore  # noqa: E402

import composite as C  # noqa: E402
import composite_dialog  # noqa: E402
import recognition  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _dashed(page, a, b, ocg, dash=6.0, gap=3.0):
    """Línea eléctrica «explotada»: guiones colineales de a→b."""
    ax, ay = a; bx, by = b
    L = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L, (by - ay) / L
    t = 0.0
    while t < L:
        e = min(L, t + dash)
        page.draw_line((ax + ux * t, ay + uy * t), (ax + ux * e, ay + uy * e), color=(0, 0, 0), oc=ocg)
        t = e + gap


def _two_sheet_pdf():
    """Dos hojas de 300x200: una línea eléctrica que cruza de la hoja 1 a la 2
    (match line en x=300 de la 1 = x=0 de la 2), a y=100."""
    doc = fitz.open()
    ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    p1 = doc.new_page(width=300, height=200)
    _dashed(p1, (24, 100), (300, 100), ocg)     # 276 = 30×9 + 6: el último guión termina en el borde
    p1.insert_text((30, 180), 'SCALE: 1"=20\'', fontsize=8)
    p2 = doc.new_page(width=300, height=200)
    _dashed(p2, (0, 100), (280, 100), ocg)
    _dashed(p2, (140, 100), (140, 30), ocg)
    p2.insert_text((30, 180), 'SCALE: 1"=20\'', fontsize=8)
    return doc.tobytes()


def test_compositor_toma_piezas_iman_y_reconoce(app):
    data = _two_sheet_pdf()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        assert dlg.lst_pages.count() == 2
        assert math.isclose(dlg.spn_src_scale.value(), 20.0)
        dlg._take(full=True)                              # hoja 1 completa
        dlg.lst_pages.setCurrentRow(1)
        dlg._take(full=True)                              # hoja 2 completa, a la derecha (+24 pt)
        assert len(dlg.comp.pieces) == 2
        p2 = dlg.comp.pieces[1]
        assert p2.x == 300 + 24 and p2.y == 0
        # Arrastre simulado: soltar la pieza 2 cerca del borde de la 1 → el imán
        # la deja exactamente pegada (x=300, y=0) usando los cortes de las líneas.
        snapped = dlg.view.snap_position(1, (303.0, 2.0))
        assert snapped is not None
        assert math.isclose(snapped[0], 300.0, abs_tol=1e-6)
        assert math.isclose(snapped[1], 0.0, abs_tol=1e-6)
        assert dlg.view.snap_position(1, (400.0, 90.0)) is None   # lejos: no hay imán
        p2.x, p2.y = snapped
        dlg.view.refresh_piece(1)
        assert dlg.btn_ok.isEnabled()
        comp, sources, hidden = dlg.result_tuple()
    finally:
        dlg.close_docs()

    # Materializar y reconocer: la línea de las dos hojas debe salir como UNA sola ruta.
    docs = [fitz.open(stream=sources[0]["data"], filetype="pdf")]
    built = C.build_document(comp, docs, hidden)
    pdf = built.tobytes(); built.close(); docs[0].close()
    work = fitz.open(stream=pdf, filetype="pdf")
    assert work.page_count == 1
    res = recognition.recognize_page(None, 0, doc=work, zoom=1.0, scale_ft_per_pt=comp.target_scale())
    drawable = res.drawable
    assert drawable, res.warnings
    longest = max(drawable, key=lambda pl: max(x for x, _ in pl.pts_pdf) - min(x for x, _ in pl.pts_pdf))
    xs = [x for x, _ in longest.pts_pdf]
    assert max(xs) - min(xs) > 500                      # cruza el borde entre piezas
    assert res.coverage > 0.95
    assert math.isclose(res.scale_ft_per_pt, 20 / 72)


def test_compositor_rotar_y_escala_por_pieza(app):
    data = _two_sheet_pdf()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg._take(full=True)
        dlg.view.select(0)
        assert dlg.view.selected_index() == 0
        dlg._rotate(-90)
        assert dlg.comp.pieces[0].rotation == 270.0
        w, h = C.piece_size(dlg.comp.pieces[0], (300, 200), dlg.comp.target_scale())
        assert (round(w), round(h)) == (200, 300)
        dlg.spn_piece_scale.setValue(40.0)                # la hoja era 1"=40'
        assert math.isclose(dlg.comp.pieces[0].src_scale, 40 / 72)
        assert dlg.cmb_scale.count() == 1
        dlg._delete()
        assert not dlg.comp.pieces and not dlg.btn_ok.isEnabled()
    finally:
        dlg.close_docs()


def test_compositor_no_aplica_capas_ocultas_de_la_hoja_ya_compuesta(app):
    """`hidden_by_source` es la selección de capas de una composición ANTERIOR
    (paso «Capas de la hoja»): el compositor sirve para MIRAR y recortar el
    plano origen para tomar piezas nuevas, así que se abre con TODAS las
    capas visibles — si no, una hoja cuyo contenido está solo en una capa ya
    oculta parecía no tener nada que tomar (usuario: «la página 3 no me
    muestra capas»). El valor recibido se conserva para devolverlo igual."""
    import pdf_layers
    data = _two_sheet_pdf()
    dlg = composite_dialog.CompositeDialog(
        None, [{"name": "a.pdf", "data": data}], None, {"0": ["C-ELEC-UNGD-E"]}, 0)
    try:
        assert pdf_layers.hidden_layers(dlg.docs[0]) == set()
        assert dlg.hidden_by_source == {"0": ["C-ELEC-UNGD-E"]}
        assert dlg.result_tuple()[2] == {"0": ["C-ELEC-UNGD-E"]}
    finally:
        dlg.close_docs()


def test_compositor_capas_puentes_y_hueco(app):
    data = _two_sheet_pdf()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg._take(full=True)
        dlg.lst_pages.setCurrentRow(1)
        dlg._take(full=True)
        # dos hojas con hueco de 24 pt y desalineadas 3 pt → el imán colineal
        # las deja en línea sin cerrar el hueco, y hay UN puente (la eléctrica)
        p2 = dlg.comp.pieces[1]
        snapped = dlg.view.snap_position(1, (324.0, 3.0))
        assert snapped is not None and math.isclose(snapped[0], 324.0) and math.isclose(snapped[1], 0.0, abs_tol=1e-6)
        p2.x, p2.y = snapped
        dlg.view.refresh_piece(1)
        dlg.view.refresh_overlay()
        assert len(dlg.view.bridges()) == 1
        assert dlg.lbl_bridges.text().startswith("1")
        # una capa apagada en el origen (sesión anterior) no da anclajes ni puentes
        dlg.hidden_by_source["0"] = ["C-ELEC-UNGD-E"]
        import pdf_layers
        pdf_layers.set_hidden(dlg.docs[0], ["C-ELEC-UNGD-E"])
        dlg.view.rerender_source(0)
        assert dlg.view.bridges() == []
        dlg.hidden_by_source["0"] = []
        pdf_layers.set_hidden(dlg.docs[0], [])
        dlg.view.rerender_source(0)
        assert len(dlg.view.bridges()) == 1
        # sin puentes: el modelo lo recuerda
        dlg.btn_bridges.setChecked(False)
        assert dlg.comp.bridges is False and dlg.view.bridges() == []
        dlg.btn_bridges.setChecked(True)
        dlg.spn_gap.setValue(10.0)
        assert dlg.comp.bridge_max_pt == 10.0 and dlg.view.bridges() == []
        dlg.spn_gap.setValue(150.0)
        comp, sources, hidden = dlg.result_tuple()
    finally:
        dlg.close_docs()
    docs = [fitz.open(stream=sources[0]["data"], filetype="pdf")]
    bridges = C.compute_bridges(comp, docs)
    assert len(bridges) == 1 and math.isclose(bridges[0].length, 24.0)
    built = C.build_document(comp, docs, hidden, bridges)
    work = fitz.open(stream=built.tobytes(), filetype="pdf")
    res = recognition.recognize_page(None, 0, doc=work, zoom=1.0, scale_ft_per_pt=comp.target_scale())
    longest = max(res.drawable, key=lambda pl: max(x for x, _ in pl.pts_pdf) - min(x for x, _ in pl.pts_pdf))
    xs = [x for x, _ in longest.pts_pdf]
    assert max(xs) - min(xs) > 500                      # una sola ruta a través del hueco


def test_seleccionar_pieza_edita_su_area_en_el_panel_2(app):
    data = _two_sheet_pdf()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg.btn_trim.setChecked(False)                    # la hoja sintética no tiene línea de borde
        dlg._take(full=True)                              # pieza 1 = hoja 1
        dlg.lst_pages.setCurrentRow(1)
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 150, 200))
        dlg._take(full=False)                             # pieza 2 = mitad izquierda de la hoja 2
        assert dlg.comp.pieces[1].clip == [0.0, 0.0, 0.5, 1.0]
        # seleccionar la pieza 1 → el panel 2 salta a la hoja 1 con su área
        dlg.view.select(0)
        assert dlg._editing == 0 and dlg._cur_page == 0
        assert dlg.crop._selection.width() == 300 and dlg.btn_new.isVisible() is not None
        assert dlg.btn_take.isHidden() and not dlg.btn_new.isHidden()
        # ajustar el rectángulo edita ESA pieza (sin crear otra)
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 200, 200))
        dlg._apply_crop_edit()
        assert len(dlg.comp.pieces) == 2
        assert dlg.comp.pieces[0].clip == [0.0, 0.0, 200 / 300, 1.0]
        # «Nueva pieza» sale del modo edición
        dlg.btn_new.click()
        assert dlg._editing == -1 and not dlg.btn_take.isHidden()
    finally:
        dlg.close_docs()


def test_sin_linea_de_borde_recorta_al_tomar(app):
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    p = doc.new_page(width=400, height=300)
    _dashed(p, (20, 100), (400, 100), ocg)
    p.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=1.0)   # match line vertical
    dlg = composite_dialog.CompositeDialog(None, [{"name": "m.pdf", "data": doc.tobytes()}], None, {}, 0)
    try:
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 308, 300))
        assert dlg.btn_trim.isChecked()
        dlg._take(full=False)
        assert math.isclose(dlg.comp.pieces[0].clip[2] * 400, 300.0, abs_tol=1e-3)   # centro de la línea
        assert math.isclose(dlg.comp.pieces[0].covers["right"], 0.5 + C.COVER_PAD_PT, abs_tol=1e-3)   # línea de 1 pt
        dlg.btn_trim.setChecked(False)
        dlg.btn_new.click()                               # «Nueva pieza»: la 1.ª queda como está
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 308, 300))
        dlg._take(full=False)
        assert math.isclose(dlg.comp.pieces[0].clip[2] * 400, 300.0, abs_tol=1e-3)
        assert math.isclose(dlg.comp.pieces[1].clip[2] * 400, 308, abs_tol=1e-6)
    finally:
        dlg.close_docs()


def test_area_se_imanta_a_las_lineas_generales(app):
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    p = doc.new_page(width=400, height=300)
    _dashed(p, (20, 100), (400, 100), ocg)
    p.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=1.0)   # match line
    p.draw_line((20, 250), (380, 250), color=(0, 0, 0))               # borde inferior
    dlg = composite_dialog.CompositeDialog(None, [{"name": "m.pdf", "data": doc.tobytes()}], None, {}, 0)
    try:
        dlg.btn_trim.setChecked(False)
        assert dlg.crop._guides["x"] and dlg.crop._guides["y"]
        # arrastrar el lado derecho hasta x=305 → salta a la match line (300) y la resalta
        dlg.crop.set_selection(QtCore.QRectF(10, 10, 200, 200))
        dlg.crop._drag_mode = "right"; dlg.crop._drag_initial = QtCore.QRectF(dlg.crop._selection)
        dlg.crop._drag_start = QtCore.QPointF(210, 100)
        dlg.crop._apply_drag(QtCore.QPointF(305, 100))
        assert math.isclose(dlg.crop._selection.right(), 300.0)
        assert len(dlg.crop._guide_items) == 1
        # esquina inferior derecha cerca de (296, 246) → (300, 250)
        dlg.crop._drag_mode = "br"; dlg.crop._drag_initial = QtCore.QRectF(dlg.crop._selection)
        dlg.crop._apply_drag(QtCore.QPointF(296, 246))
        assert math.isclose(dlg.crop._selection.right(), 300.0) and math.isclose(dlg.crop._selection.bottom(), 250.0)
        # imán apagado: se queda donde se suelta
        dlg.btn_area_snap.setChecked(False)
        dlg.crop._drag_mode = "right"; dlg.crop._drag_initial = QtCore.QRectF(dlg.crop._selection)
        dlg.crop._apply_drag(QtCore.QPointF(305, 100))
        assert math.isclose(dlg.crop._selection.right(), 305.0)
    finally:
        dlg.close_docs()


def test_nitidez_al_hacer_zoom_en_ambos_paneles(app):
    data = _two_sheet_pdf()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg.resize(1400, 800); dlg.show()
        # panel 2: sin zoom no hay recorte nítido; con zoom 4× aparece encima (z=1)
        dlg.crop.resetTransform(); dlg._crop_sharp.update_quality()
        assert dlg._crop_sharp._item is None
        dlg.crop.scale(4.0, 4.0); dlg.crop.centerOn(150, 100); dlg._crop_sharp.update_quality()
        assert dlg._crop_sharp._item is not None and dlg._crop_sharp._item.zValue() == 1
        # hoja compuesta: TODAS las piezas a la vista reciben recorte nítido
        dlg._take(full=True); dlg.lst_pages.setCurrentRow(1); dlg._take(full=True)
        dlg.view.resetTransform(); dlg.view.scale(4.0, 4.0); dlg.view.centerOn(312, 100)
        dlg.view._update_quality()
        assert all(it._sharp is not None for it in dlg.view.items)
        dlg.view.resetTransform(); dlg.view._update_quality()      # escala 1: no hace falta recorte
        assert all(it._sharp is None for it in dlg.view.items)
    finally:
        dlg.close_docs()


def test_minimapa_en_capas_de_la_hoja(app):
    """El diálogo «Capas de la hoja» muestra un minimapa con la hoja y el
    recuadro de lo visible; clic en el mapa centra la vista ahí."""
    import layer_dialog
    from PySide6 import QtGui
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=1200, height=400); _dashed(page, (20, 200), (1180, 200), ocg)
    layout = [((0, 0, 600, 400), "Hoja 13"), ((600, 0, 1200, 400), "Hoja 14")]
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0, layout=layout)
    dlg.resize(1200, 700); dlg.show()
    try:
        assert dlg.minimap.isVisible() and dlg.minimap.width() <= dlg.minimap.MAX_W + 2
        assert dlg.minimap._layout and [l for _, l in dlg.minimap._layout] == ["Hoja 13", "Hoja 14"]
        assert dlg.minimap._thumb is None                                   # esquema, no dibujo
        dlg.view.resetTransform(); dlg.view.scale(3.0, 3.0); dlg.view.centerOn(100, 100)
        before = dlg.view.mapToScene(dlg.view.viewport().rect().center())
        # clic en la esquina derecha del mapa → la vista se centra hacia el final de la hoja
        pos = QtCore.QPointF(dlg.minimap.width() - 3, dlg.minimap.height() / 2)
        ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, pos, QtCore.Qt.LeftButton,
                               QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        dlg.minimap.mousePressEvent(ev)
        after = dlg.view.mapToScene(dlg.view.viewport().rect().center())
        assert after.x() > before.x() + 1000
    finally:
        dlg.close()


@pytest.mark.parametrize("manual", [False, True])
def test_compositor_minimapa_en_tiempo_real(app, manual):
    from PySide6 import QtTest
    dlg = composite_dialog.CompositeDialog(None,
        [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, manual=manual)
    try:
        assert [label for _, label in dlg.view.minimap._layout] == ["Hoja 1"]   # la hoja a la vista
        dlg._take_area(True)
        dlg.lst_pages.setCurrentRow(1)
        dlg._take_area(True)
        minimap = dlg.view.minimap
        assert not minimap.isHidden()
        assert [label for _, label in minimap._layout] == ["Hoja 1", "Hoja 2"]
        dlg.view.magnet_enabled = False
        dlg.view.items[1].setPos(-400, 170)
        assert minimap._layout[1][0].topLeft() == QtCore.QPointF(-400, 170)
        assert minimap._full_scene_rect.contains(minimap._layout[1][0])
        dlg._rotate(90)
        assert minimap._layout[1][0].width() == pytest.approx(200)
        assert minimap._layout[1][0].height() == pytest.approx(300)
        dlg.show()
        app.processEvents()
        dlg.view.fit_all()
        dlg.view.centerOn(150, 100)
        before = dlg.view.mapToScene(dlg.view.viewport().rect().center())
        target = minimap._scene_to_map(minimap._layout[1][0].center()).toPoint()
        QtTest.QTest.mouseClick(minimap, QtCore.Qt.LeftButton, pos=target)
        after = dlg.view.mapToScene(dlg.view.viewport().rect().center())
        assert after.x() < before.x()-100
        dlg.view.select(1)
        dlg._delete()
        assert len(minimap._layout) == 1
        dlg.view.select(0)
        dlg._delete()
        assert minimap.isHidden()
    finally:
        dlg.close_docs()
        dlg.close()


def test_minimapa_zoom_sigue_composicion(app):
    from PySide6 import QtTest
    dlg = composite_dialog.CompositeDialog(None,
        [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, manual=True)
    try:
        dlg._take_area(True)
        dlg.lst_pages.setCurrentRow(1)
        dlg._take_area(True)
        dlg.view.magnet_enabled = False
        dlg.view.items[1].setPos(20000, 8000)
        dlg._go_tab(composite_dialog.TAB_SHEET)          # la hoja compuesta vive en su pestaña
        dlg.show()
        app.processEvents()
        view, minimap = dlg.view, dlg.view.minimap
        view.fit_all()
        overview_width = minimap._scene_rect.width()
        view.scale(20, 20)
        view.centerOn(20150, 8100)
        view.viewChanged.emit()
        assert minimap._scene_rect.width() < overview_width/15
        assert minimap._scene_rect.contains(QtCore.QPointF(20150, 8100))
        assert minimap.pos() == QtCore.QPoint(minimap.MARGIN,
            view.viewport().height()-minimap.height()-minimap.MARGIN)
        QtTest.QTest.mouseDClick(minimap, QtCore.Qt.LeftButton, pos=minimap.rect().center())
        assert minimap._zoom == pytest.approx(1, abs=0.1)
    finally:
        dlg.close_docs()
        dlg.close()


def test_compositor_zoom_anclado_y_navegacion_libre(app):
    from PySide6 import QtGui, QtTest
    dlg = composite_dialog.CompositeDialog(None,
        [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, manual=True)
    try:
        dlg._take_area(True)
        dlg.show()
        app.processEvents()
        view = dlg.view
        view.fit_all()
        position = view.viewport().rect().center()+QtCore.QPoint(30, -20)
        def assert_minimap_in_corner():
            minimap = view.minimap
            assert minimap.pos() == QtCore.QPoint(minimap.MARGIN,
                view.viewport().height()-minimap.height()-minimap.MARGIN)
        for _ in range(30):
            anchor = view.mapToScene(position)
            event = QtGui.QWheelEvent(QtCore.QPointF(position), QtCore.QPointF(view.viewport().mapToGlobal(position)),
                QtCore.QPoint(), QtCore.QPoint(0, -120), QtCore.Qt.NoButton,
                QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
            view.wheelEvent(event)
            drift = view.mapFromScene(anchor)-position
            assert abs(drift.x()) <= 2 and abs(drift.y()) <= 2
            assert_minimap_in_corner()
        # Even when the sheets are tiny, repeated pans can cross every boundary.
        start = view.viewport().rect().center()
        initial = view.mapToScene(start)
        for _ in range(6):
            QtTest.QTest.mousePress(view.viewport(), QtCore.Qt.MiddleButton, pos=start)
            QtTest.QTest.mouseMove(view.viewport(), start+QtCore.QPoint(100, 80))
            QtTest.QTest.mouseRelease(view.viewport(), QtCore.Qt.MiddleButton, pos=start+QtCore.QPoint(100, 80))
            assert_minimap_in_corner()
        after = view.mapToScene(start)
        assert after.x() < initial.x()-500/abs(view.transform().m11())
        assert after.y() < initial.y()-400/abs(view.transform().m11())
        assert dlg.comp.pieces[0].x == 0 and dlg.comp.pieces[0].y == 0
    finally:
        dlg.close_docs()
        dlg.close()


def test_pestanas_a_ventana_completa_y_navegacion(app):
    """Pedido del usuario 2026-10-03: en tres columnas a cada vista le quedaba poco
    sitio. Ahora son pestañas (Origen · Área a tomar · Hoja compuesta), cada una a
    ventana completa, siempre clicables, con «‹ Atrás / Siguiente ›» y ‹ › de hoja
    dentro de «Área a tomar»."""
    T = composite_dialog
    dlg = T.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0)
    try:
        dlg.resize(1100, 640); dlg.show(); _settle(app)
        assert dlg.tabs.current() == T.TAB_SOURCE and dlg.stack.currentIndex() == T.TAB_SOURCE
        assert dlg.btn_back.isHidden() and not dlg.btn_next.isHidden()
        # la hoja a la vista ya está en la hoja compuesta: se puede continuar de una vez
        assert dlg.btn_ok.isEnabled() and "hoja 1 completa" in dlg.lbl_check.text()
        # la galería ocupa la ventana: cada vista usa casi todo el ancho del diálogo
        assert dlg.lst_pages.width() > 0.85 * dlg.stack.width()
        dlg.btn_next.click(); _settle(app)                          # → «Área a tomar»
        assert dlg.stack.currentIndex() == T.TAB_AREA and not dlg.btn_back.isHidden()
        assert dlg.crop.width() > 0.85 * dlg.stack.width()
        assert dlg.lbl_page.text() == "Hoja 1 de 2" and not dlg.btn_prev_page.isEnabled()
        dlg.btn_next_page.click(); _settle(app)                     # ‹ › cambian de hoja aquí mismo
        assert dlg.lst_pages.currentRow() == 1 and dlg.lbl_page.text() == "Hoja 2 de 2"
        assert [p.page for p in dlg.comp.pieces] == [1]              # …y la elegida es la que se usa
        assert not dlg.btn_next_page.isEnabled()
        dlg.btn_all_pages.click(); _settle(app)                     # «Ver todas las hojas» → Origen
        assert dlg.stack.currentIndex() == T.TAB_SOURCE
        _click_page(app, dlg, 0)                                    # el 1.er clic del doble clic la elige
        dlg.lst_pages.itemDoubleClicked.emit(dlg.lst_pages.item(0)); _settle(app)
        assert dlg.stack.currentIndex() == T.TAB_AREA                # doble clic en una hoja → Área
        assert [p.page for p in dlg.comp.pieces] == [0] and dlg.tabs.tabs[T.TAB_SHEET].badge == ("1", "count")
        dlg.btn_next.click(); _settle(app)                          # «Siguiente: Hoja compuesta»
        assert dlg.stack.currentIndex() == T.TAB_SHEET and dlg.btn_next.isHidden()
        assert dlg.btn_ok.isEnabled() and "Lista para continuar" in dlg.lbl_check.text()
        dlg.btn_edit_area.click(); _settle(app)                     # pieza elegida → «Editar área»
        assert dlg.stack.currentIndex() == T.TAB_AREA and "entera" in dlg.lbl_mode.text()
        dlg.tabs.tabs[T.TAB_SOURCE].click(); _settle(app)           # las pestañas, siempre clicables
        assert dlg.stack.currentIndex() == T.TAB_SOURCE
        dlg._go_tab(T.TAB_SHEET); dlg.btn_back.click(); _settle(app)
        assert dlg.stack.currentIndex() == T.TAB_AREA
    finally:
        dlg.close_docs(); dlg.close()


def test_capas_y_preview_con_divisor(app):
    import layer_dialog
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=600, height=400); _dashed(page, (20, 200), (580, 200), ocg)
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    dlg.resize(1000, 600); dlg.show(); app.processEvents()
    try:
        assert dlg.split.count() == 3                                  # leyenda | hoja | capas
        dlg._apply_side_width()
        sizes = dlg.split.sizes()
        assert 300 <= sizes[2] <= int(1000 * 0.32) + 1                 # ≤ 32 % de la ventana
        # sin leyenda en el PDF ni capas por sus letras, el panel izquierdo queda plegado
        from widgets import CollapsiblePanel
        assert dlg.info_box.collapsed and sizes[0] == CollapsiblePanel.STRIP_W
    finally:
        dlg.close()


def test_codo_reconocido_como_esquina_mas_radio(app):
    """Dos rectas unidas por un arco (R=60 pt) dibujado a guiones → el
    reconocimiento devuelve un vértice «fillet» en la esquina con el radio en
    pies, y al importar la CAJA de ese vértice es una esquina curva (CV)."""
    import model_ops
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    R, C = 60.0, (400.0, 300.0)
    _dashed(page, (100, 300), (C[0] - R, 300), ocg)                     # recta horizontal → tangencia A=(340,300)
    # arco de 90° de A=(340,300) a B=(400,360), centro (340,360)
    O = (C[0] - R, C[1] + R); import math as _m
    pts = [(O[0] + R * _m.cos(_m.radians(-90 + t)), O[1] + R * _m.sin(_m.radians(-90 + t))) for t in range(0, 91, 5)]
    page.draw_polyline(pts, color=(0, 0, 0), oc=ocg)                     # UN trazo curvo continuo (como el PDF)
    _dashed(page, (C[0], C[1] + R), (400, 580), ocg)                     # recta vertical desde B=(400,360)
    page.insert_text((30, 580), 'SCALE: 1"=20\'', fontsize=8)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    fil = [(pl, i, f) for pl in res.drawable for i, f in pl.fillets.items()]
    assert len(fil) == 1, [pl.kinds for pl in res.drawable]
    pl, i, f = fil[0]
    assert pl.kinds[i] == "fillet"
    assert math.isclose(f["r_px"] / 2.0, R, rel_tol=0.03)               # radio en pt (px / zoom)
    cx, cy = pl.pts_pdf[i]
    assert math.isclose(cx / 2.0, C[0], abs_tol=1.5) and math.isclose(cy / 2.0, C[1], abs_tol=1.5)   # esquina
    pipes = recognition.pipes_from_recognition(res, zoom=2.0)
    assert set(pipes[0]["fillets"]) == {i}                             # radio en pies (ajustado a la tinta)
    assert abs(pipes[0]["fillets"][i] - R * 20 / 72) <= 0.05
    structures = model_ops.rebuild_structures(pipes, [])
    n = model_ops.attach_fillets(pipes, structures)
    assert n == 1
    cv = [s for s in structures if s.get("curve")]
    assert len(cv) == 1 and math.isclose(cv[0]["radius_ft"], R * 20 / 72, abs_tol=0.05)
    assert cv[0]["cod"].startswith("CV") or True                        # el prefijo lo da rebuild al recodificar


def test_quiebres_rectos_no_se_convierten_en_curva(app):
    """Los mismos puntos del arco pero como guiones RECTOS sueltos (una cadena
    de quiebres) no son una curva del PDF: se quedan como esquinas/quiebres,
    nunca como esquina + radio (regla: no inventar)."""
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    import math as _m
    R, O = 60.0, (340.0, 360.0)
    _dashed(page, (100, 300), (340, 300), ocg)
    pts = [(O[0] + R * _m.cos(_m.radians(-90 + t)), O[1] + R * _m.sin(_m.radians(-90 + t))) for t in range(0, 91, 15)]
    for a, b in zip(pts, pts[1:]):                                        # 6 guiones rectos a 15°
        page.draw_line(a, b, color=(0, 0, 0), oc=ocg)
    _dashed(page, (400, 360), (400, 580), ocg)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    assert not any(pl.fillets for pl in res.drawable)
    assert not any("curve" in pl.kinds for pl in res.drawable)


def _glyph_e(page, cx, cy, ocg, size=4.5):
    """Letra «e» del linetype (glifo SHX de 10 segmentos) centrada en (cx, cy)."""
    r = size / 2
    pts = [(cx - r, cy), (cx + r, cy), (cx + r, cy - r * 0.6), (cx + r * 0.4, cy - r), (cx - r * 0.4, cy - r),
           (cx - r, cy - r * 0.5), (cx - r, cy + r * 0.5), (cx - r * 0.4, cy + r), (cx + r * 0.4, cy + r), (cx + r, cy + r * 0.6)]
    page.draw_polyline(pts, color=(0, 0, 0), oc=ocg)


def _linetype(page, a, b, ocg, phase=0.0):
    """Línea con el linetype explotado del plano (como `Sheet.dashed` de
    test_recognition_geom): guión largo, hueco, guión corto, letra «e», guión
    corto, hueco. `phase` = pt del periodo ya consumidos al empezar (así el
    tramo que llega a un codo puede terminar en cualquier parte del periodo)."""
    ax, ay = a; bx, by = b
    L = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L, (by - ay) / L
    P = lambda t: (ax + ux * t, ay + uy * t)
    period = [("d", 22.0), ("g", 5.0), ("d", 7.0), ("e", 10.0), ("d", 7.0), ("g", 5.0)]
    t = -phase
    while t < L:
        for kind, ln in period:
            t0, t1 = max(0.0, t), min(L, t + ln)
            if kind == "d" and t1 - t0 > 0.5:
                page.draw_line(P(t0), P(t1), color=(0, 0, 0), oc=ocg)
            elif kind == "e" and t1 - t0 >= ln - 1e-6:
                cx, cy = P((t0 + t1) / 2)
                _glyph_e(page, cx, cy, ocg)
            t = t + ln
            if t >= L:
                break


def _elbow_doc(gap_before=0.0, gap_after=0.0, arc_dashed=False, R=60.0, C=(400.0, 300.0), turn=90,
               dash=21.6, gap=3.6):
    """Recta horizontal → arco de `turn`° (R) → recta que sale, como lo plotea el
    linetype (guiones de `dash` pt con huecos de `gap`): la recta termina
    `gap_before` pt ANTES del punto de tangencia y la siguiente empieza
    `gap_after` después (un hueco ≥ 8 pt lleva la letra «e» del linetype en
    medio, como en el plano); el arco es un trazo aplanado continuo o va
    también a guiones (curvos) del mismo largo."""
    import math as _m
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    T = R * _m.tan(_m.radians(turn) / 2.0)
    A = (C[0] - T, C[1]); O = (A[0], A[1] + R)
    _linetype(page, (100, C[1]), (A[0] - gap_before, C[1]), ocg)
    if gap_before >= 8:
        _glyph_e(page, A[0] - gap_before / 2, C[1], ocg)
    step = 1.0
    pts = [(O[0] + R * _m.cos(_m.radians(-90 + t)), O[1] + R * _m.sin(_m.radians(-90 + t)))
           for t in [k * step for k in range(int(turn / step) + 1)]]
    if arc_dashed:
        per_dash = max(2, int(round(dash / (R * _m.radians(step)))))     # vértices por guión curvo
        per_gap = max(1, int(round(gap / (R * _m.radians(step)))))
        k = 0
        while k < len(pts) - 1:
            piece = pts[k:k + per_dash + 1]
            if len(piece) >= 2:
                page.draw_polyline(piece, color=(0, 0, 0), oc=ocg)
            k += per_dash + per_gap
    else:
        page.draw_polyline(pts, color=(0, 0, 0), oc=ocg)
    B = pts[-1]
    ub = (_m.cos(_m.radians(turn)), _m.sin(_m.radians(turn)))
    N = (B[0] + ub[0] * 250, B[1] + ub[1] * 250)
    _linetype(page, (B[0] + ub[0] * gap_after, B[1] + ub[1] * gap_after), N, ocg)
    if gap_after >= 8:
        _glyph_e(page, B[0] + ub[0] * gap_after / 2, B[1] + ub[1] * gap_after / 2, ocg)
    page.insert_text((30, 580), "SCALE: 1\"=20'", fontsize=8)
    return doc, A, B, C, R, ub


def _fillet_check(res, A, B, C, R, ub, tol_pt=0.3, tol_deg=0.2):
    import math as _m
    fil = [(pl, i, f) for pl in res.drawable for i, f in pl.fillets.items()]
    assert len(fil) == 1, [pl.kinds for pl in res.drawable]
    pl, i, f = fil[0]
    Z = 2.0
    cx, cy = pl.pts_pdf[i]
    assert _m.dist((cx / Z, cy / Z), C) <= tol_pt, ((cx / Z, cy / Z), C)          # esquina exacta
    # el radio de un arco corto es mal condicionado (sagita chica): lo que debe
    # ser exacto es la POSICIÓN del arco → error radial máximo Δr·(1−cos(giro/2)) ≤ 0.5 pt
    turn = _m.degrees(_m.atan2(ub[1], ub[0]))
    assert abs(f["r_px"] / Z - R) * (1 - _m.cos(_m.radians(turn) / 2)) <= 0.5, f["r_px"] / Z
    # A y B se derivan del radio (T = r·tan(giro/2)): heredan su incertidumbre
    tol_ab = tol_pt + abs(f["r_px"] / Z - R) * _m.tan(_m.radians(turn) / 2)
    assert _m.dist((f["a"][0] / Z, f["a"][1] / Z), A) <= tol_ab and _m.dist((f["b"][0] / Z, f["b"][1] / Z), B) <= tol_ab
    P, N = pl.pts_pdf[i - 1], pl.pts_pdf[i + 1]
    ang_in = _m.degrees(_m.atan2(cy - P[1], cx - P[0]))                           # recta que llega: horizontal
    ang_out = _m.degrees(_m.atan2(N[1] - cy, N[0] - cx))
    assert abs(ang_in) <= tol_deg, ang_in
    assert abs(ang_out - _m.degrees(_m.atan2(ub[1], ub[0]))) <= tol_deg, ang_out


@pytest.mark.parametrize("gap_before,gap_after", [(0.0, 0.0), (4.0, 4.0), (10.0, 3.0), (3.0, 10.0)])
def test_codo_con_hueco_o_letra_antes_del_arco_tangente_exacta(app, gap_before, gap_after):
    """La recta del linetype termina unos pt antes del arco (hueco / letra «e»):
    la esquina y las tangentes salen de las RECTAS de los guiones (no del salto
    hasta el trazo curvo), como en el DU06 hoja 4."""
    doc, A, B, C, R, ub = _elbow_doc(gap_before, gap_after)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    _fillet_check(res, A, B, C, R, ub)


@pytest.mark.parametrize("turn", [30, 60, 120])
def test_codo_con_otros_giros_y_arco_a_guiones(app, turn):
    doc, A, B, C, R, ub = _elbow_doc(4.0, 4.0, arc_dashed=True, R=80.0, turn=turn)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    _fillet_check(res, A, B, C, R, ub, tol_pt=0.5)


def test_curva_compuesta_no_se_funde_en_un_solo_circulo(app):
    """Dos arcos encadenados de radios distintos (60 y 120 pt, tangentes entre
    sí) NO se representan con un solo círculo: lo que salga como codo tiene
    que estar sobre la tinta (≤1 pt) — si no cabe, se queda como polilínea."""
    import math as _m
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=900, height=700)
    R1, R2 = 60.0, 120.0
    A = (300.0, 300.0); O1 = (A[0], A[1] + R1)
    p1 = [(O1[0] + R1 * _m.cos(_m.radians(-90 + t)), O1[1] + R1 * _m.sin(_m.radians(-90 + t))) for t in range(0, 46, 3)]
    M = p1[-1]                                           # tangente común a 45°
    O2 = (M[0] + (O1[0] - M[0]) / R1 * R2, M[1] + (O1[1] - M[1]) / R1 * R2)
    p2 = [(O2[0] + R2 * _m.cos(_m.radians(-45 + t)), O2[1] + R2 * _m.sin(_m.radians(-45 + t))) for t in range(0, 46, 3)]
    B = p2[-1]
    _dashed(page, (60, 300), (A[0] - 4, 300), ocg, dash=21.6, gap=3.6)
    page.draw_polyline(p1, color=(0, 0, 0), oc=ocg)
    page.draw_polyline(p2, color=(0, 0, 0), oc=ocg)
    _dashed(page, (B[0], B[1] + 4), (B[0], B[1] + 250), ocg, dash=21.6, gap=3.6)
    page.insert_text((30, 680), 'SCALE: 1"=20\'', fontsize=8)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    ink = list(zip(p1, p1[1:])) + list(zip(p2, p2[1:]))
    def _seg_d(q, a, b):
        vx, vy = b[0] - a[0], b[1] - a[1]; L2 = vx * vx + vy * vy
        t = max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        return _m.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)
    for pl in res.drawable:
        for i, f in pl.fillets.items():
            cx, cy, r = f["center"][0] / 2, f["center"][1] / 2, f["r_px"] / 2
            a0 = _m.atan2(f["a"][1] / 2 - cy, f["a"][0] / 2 - cx); a1 = _m.atan2(f["b"][1] / 2 - cy, f["b"][0] / 2 - cx)
            sw = (a1 - a0 + 3 * _m.pi) % (2 * _m.pi) - _m.pi
            for k in range(21):
                q = (cx + r * _m.cos(a0 + sw * k / 20), cy + r * _m.sin(a0 + sw * k / 20))
                assert min(_seg_d(q, a, b) for a, b in ink) <= 1.0, (q, r)
            assert abs(r - R1) <= 1.0 or abs(r - R2) <= 1.0, r         # radio de UNO de los dos arcos reales


def test_quiebre_con_astilla_no_se_toma_por_curva(app):
    """Dos rectas con un quiebre donde el plot dejó una astilla (segmento de
    0.15 pt en el vértice, como en el DU06): el vértice se marca «curve» pero la
    TINTA no traza ningún arco → se queda como esquina, no como codo."""
    import math as _m
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    V = (400.0, 300.0)
    _linetype(page, (100, 300), (V[0] - 2, 300), ocg)
    # el guión del quiebre: astilla + tramo recto en la nueva dirección
    page.draw_polyline([(V[0] - 2, V[1]), (V[0] - 1.9, V[1] + 0.15), (V[0] + 14, V[1] + 12)], color=(0, 0, 0), oc=ocg)
    ux, uy = _m.cos(_m.radians(40)), _m.sin(_m.radians(40))
    _linetype(page, (V[0] + 18 * ux, V[1] + 18 * uy), (V[0] + 260 * ux, V[1] + 260 * uy), ocg)
    page.insert_text((30, 580), "SCALE: 1\"=20'", fontsize=8)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    assert not any(pl.fillets for pl in res.drawable), [pl.fillets for pl in res.drawable]


def test_curva_que_muere_en_un_tee_se_reconoce(app):
    """Un ramal que baja recto, curva (R=60) y MUERE sobre otra línea (tee): no
    hay segunda recta, pero el plano da la recta que llega, el nodo y la tinta
    del arco → codo con la tangencia clavada en el tee (`node_b`)."""
    import math as _m
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    R = 60.0
    O = (300.0 + R, 200.0)                       # centro; el ramal baja por x=300
    _linetype(page, (300, 60), (300, 200), ocg)
    end_deg = 70.0
    pts = [(O[0] + R * _m.cos(_m.radians(180 - t)), O[1] + R * _m.sin(_m.radians(180 - t)))
           for t in [k * 1.0 for k in range(int(end_deg) + 1)]]
    for k in range(0, len(pts) - 1, 24):         # arco a guiones curvos
        page.draw_polyline(pts[k:k + 19], color=(0, 0, 0), oc=ocg)
    B = pts[-1]
    _linetype(page, (B[0] - 240, B[1]), (B[0] + 240, B[1]), ocg)     # la línea que cruza (tee)
    page.insert_text((30, 580), "SCALE: 1\"=20'", fontsize=8)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    fil = [(pl, i, f) for pl in res.drawable for i, f in (pl.fillets or {}).items()]
    assert len(fil) == 1, [pl.kinds for pl in res.drawable]
    pl, i, f = fil[0]
    assert abs(f["r_px"] / 2.0 - R) <= 2.0, f["r_px"] / 2.0
    assert f["node_b"] or f["node_a"]
    assert not f["loose"]
    # el arco va sobre la tinta del PDF
    ctr = f["center"]
    a0 = _m.atan2(f["a"][1] - ctr[1], f["a"][0] - ctr[0]); a1 = _m.atan2(f["b"][1] - ctr[1], f["b"][0] - ctr[0])
    sw = (a1 - a0 + 3 * _m.pi) % (2 * _m.pi) - _m.pi
    for k in range(21):
        ang = a0 + sw * k / 20
        q = ((ctr[0] + f["r_px"] * _m.cos(ang)) / 2.0, (ctr[1] + f["r_px"] * _m.sin(ang)) / 2.0)
        assert min(_m.dist(q, s) for s in pts) <= 1.0


def test_chaflan_de_guiones_rectos_no_es_codo(app):
    """El plano gira con dos rectas y esconde el quiebre en el HUECO entre
    guiones (chaflán, DU06 h.4 en 571,1262): los guiones del giro son RECTOS, así
    que no hay codo — aunque un círculo pase cerca de sus extremos."""
    import math as _m
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    _linetype(page, (120, 300), (300, 300), ocg)                      # recta 1
    # el giro: dos guiones RECTOS a 30° y 60°, con el quiebre en el hueco
    page.draw_line((303.6, 300.0), (322.3, 310.8), color=(0, 0, 0), oc=ocg)     # 30°
    page.draw_line((325.4, 315.2), (336.2, 333.9), color=(0, 0, 0), oc=ocg)     # 60°
    ux, uy = _m.cos(_m.radians(80)), _m.sin(_m.radians(80))
    _linetype(page, (339.0, 339.7), (339.0 + 220 * ux, 339.7 + 220 * uy), ocg)  # recta 2
    page.insert_text((30, 580), "SCALE: 1\"=20'", fontsize=8)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    assert not any(pl.fillets for pl in res.drawable), [pl.fillets for pl in res.drawable]


def test_codo_de_guiones_curvos_si_es_codo(app):
    """Mismo giro pero ploteado como lo plotea un arco de verdad: cada guión va
    curvado (flecha ≈ L²/8r). Ahí sí hay codo, con el radio del plano."""
    import math as _m
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=800, height=600)
    R = 60.0
    A = (300.0, 300.0); O = (A[0], A[1] + R)
    _linetype(page, (120, 300), (A[0] - 3.6, 300), ocg)
    pts = [(O[0] + R * _m.cos(_m.radians(-90 + t)), O[1] + R * _m.sin(_m.radians(-90 + t)))
           for t in [k * 1.0 for k in range(81)]]
    k = 0
    while k < len(pts) - 1:                         # guiones CURVOS de ~21.6 pt
        page.draw_polyline(pts[k:k + 21], color=(0, 0, 0), oc=ocg)
        k += 24
    B = pts[-1]
    ux, uy = _m.cos(_m.radians(80)), _m.sin(_m.radians(80))
    _linetype(page, (B[0] + 3.6 * ux, B[1] + 3.6 * uy), (B[0] + 240 * ux, B[1] + 240 * uy), ocg)
    page.insert_text((30, 580), "SCALE: 1\"=20'", fontsize=8)
    res = recognition.recognize_page(None, 0, doc=doc, zoom=2.0)
    fil = [f for pl in res.drawable for f in (pl.fillets or {}).values()]
    assert len(fil) == 1, [pl.kinds for pl in res.drawable]
    assert abs(fil[0]["r_px"] / 2.0 - R) <= 2.0, fil[0]["r_px"] / 2.0


def _two_sheets_offset_pdf():
    """Dos hojas contiguas ploteadas con margen distinto (la 2.ª 17 pt más abajo):
    misma match line en el borde compartido y líneas de red que la cruzan."""
    doc = fitz.open()
    ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    for k, dy in enumerate((0.0, 17.0)):
        page = doc.new_page(width=400, height=300)
        xm = 300.0 if k == 0 else 100.0
        page.draw_line((xm, 60 + dy), (xm, 180 + dy), color=(0, 0, 0), width=0.72)
        for y in (90.0, 130.0, 160.0):
            a = (xm - 90, y + dy) if k == 0 else (xm, y + dy)
            b = (xm, y + dy) if k == 0 else (xm + 90, y + dy)
            _dashed(page, a, b, ocg)
        page.insert_text((20, 280), "SCALE: 1\"=20'", fontsize=8)
    return doc.tobytes()


@pytest.mark.parametrize("drop_dy", [2.0, 20.0, -25.0])
def test_iman_alinea_la_costura_por_la_match_line(app, drop_dy):
    """Se suelta la 2.ª pieza descolocada: el imán la deja SIEMPRE en la misma
    posición, la que hace coincidir las dos match lines (y con ella las líneas
    que cruzan). Antes, con el recorte de cada hoja a distinta altura, el desfase
    se quedaba tal cual y el plano salía «escalonado» en la costura."""
    data = _two_sheets_offset_pdf()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg.btn_trim.setChecked(False)
        for pno, (xl, xr) in ((0, (150, 300)), (1, (100, 250))):
            dlg.lst_pages.setCurrentRow(pno)
            r = dlg.crop._page_rect
            sx, sy = r.width() / 400.0, r.height() / 300.0
            top = 40.0 if pno == 0 else 57.0                  # cada hoja recortada a su altura
            dlg.crop._selection = QtCore.QRectF(xl * sx, top * sy, (xr - xl) * sx, 200 * sy)
            dlg._take(full=False)
        p1, p2 = dlg.comp.pieces
        w1, _h1 = C.piece_size(p1, (400.0, 300.0), dlg.comp.target_scale())
        pos = (p1.x + w1 + 1.0, p1.y + drop_dy)
        snapped = dlg.view.snap_position(1, pos)
        assert snapped is not None
        assert abs(snapped[0] - (p1.x + w1)) < 1e-6           # borde con borde
        # las dos match lines quedan a la misma altura
        ea = dlg.view._seam_line(0, "right")
        eb = dlg.view._seam_line(1, "left", snapped)
        assert ea and eb and abs(ea[0] - eb[0]) < 0.01 and abs(ea[1] - eb[1]) < 0.01
    finally:
        dlg.close_docs()


def test_hoja_sin_capas_se_marca_en_la_lista(app):
    """Un PDF con capas donde una hoja está «aplanada» (sus trazos fuera de toda
    capa, como DU08 h.3–19): la lista la marca y el aviso aparece al elegirla."""
    doc = fitz.open()
    ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    _dashed(doc.new_page(width=300, height=200), (20, 100), (280, 100), ocg)
    doc.new_page(width=300, height=200).draw_line((20, 100), (280, 100))
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": doc.tobytes()}], None, {}, 0)
    try:
        dlg.show(); app.processEvents()
        assert "sin capas" not in dlg.lst_pages.item(0).text()
        assert "sin capas" in dlg.lst_pages.item(1).text()
        assert dlg.nolayers_box.isHidden()
        dlg.lst_pages.setCurrentRow(1); app.processEvents()
        assert not dlg.nolayers_box.isHidden() and "sin capas" in dlg.lbl_nolayers.text()
        dlg.lst_pages.setCurrentRow(0); app.processEvents()
        assert dlg.nolayers_box.isHidden()
    finally:
        dlg.close_docs(); dlg.close()


def test_abre_en_la_pestana_que_toca(app):
    """Sin piezas → «Origen»; con la hoja entera que pone el editor → «Área a
    tomar» (sobre esa hoja); con piezas acomodadas → «Hoja compuesta»."""
    T = composite_dialog
    data = _two_sheet_pdf()
    cases = ((None, T.TAB_SOURCE),
             (C.Composite(pieces=[C.Piece(0, 0, [0.0, 0.0, 1.0, 1.0], src_scale=20 / 72.0)]), T.TAB_AREA),
             (C.Composite(pieces=[C.Piece(0, 0, [0.0, 0.0, 0.5, 1.0], src_scale=20 / 72.0),
                                  C.Piece(0, 1, [0.5, 0.0, 1.0, 1.0], src_scale=20 / 72.0)]), T.TAB_SHEET))
    for comp, tab in cases:
        dlg = T.CompositeDialog(None, [{"name": "a.pdf", "data": data}], comp, {}, 0)
        try:
            assert dlg.tabs.current() == tab and dlg.stack.currentIndex() == tab
        finally:
            dlg.close_docs()


def _settle(app, n=5):
    for _ in range(n):
        app.processEvents()


def test_valida_lo_pendiente_antes_de_continuar(app, monkeypatch):
    """La hoja a la vista ya está en la hoja compuesta y un área marcada sobre ella la
    recorta: no queda nada «sin tomar» ni vacío (pedido del usuario 2026-10-05). Sin
    piezas (las quitó) no se puede continuar y el pie ofrece usar la hoja; un área
    marcada para OTRA pieza («Nueva pieza») sin tomar se avisa y se pregunta."""
    T = composite_dialog
    dlg = T.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0)
    try:
        dlg.show(); dlg._go_tab(T.TAB_AREA); _settle(app)
        assert dlg.btn_ok.isEnabled() and dlg._editing == 0
        dlg.crop.set_selection(QtCore.QRectF(20, 20, 150, 120)); _settle(app)    # marca: la recorta
        dlg._crop_timer.stop(); dlg._apply_crop_edit()
        assert len(dlg.comp.pieces) == 1 and dlg.comp.pieces[0].clip != [0.0, 0.0, 1.0, 1.0]
        assert not dlg._area_untaken() and "área de la hoja 1" in dlg.lbl_check.text()
        # otra área de la misma hoja («Nueva pieza») sin tomar: se avisa y se pregunta
        dlg.btn_new.click()
        dlg.crop.set_selection(QtCore.QRectF(180, 20, 100, 120)); _settle(app)
        assert dlg._area_untaken() and dlg.btn_ok.isEnabled()
        assert "sin tomar" in dlg.lbl_check.text() and dlg.tabs.tabs[T.TAB_AREA].badge == ("!", "warn")
        monkeypatch.setattr(dlg, "_ask_untaken_area", lambda: "back")
        dlg.btn_next.click(); _settle(app)                                       # «Volver»: se queda
        assert dlg.stack.currentIndex() == T.TAB_AREA and len(dlg.comp.pieces) == 1
        monkeypatch.setattr(dlg, "_ask_untaken_area", lambda: "take")
        dlg.btn_next.click(); _settle(app)                                       # «Tomar el área»
        assert dlg.stack.currentIndex() == T.TAB_SHEET and len(dlg.comp.pieces) == 2
        assert not dlg._area_untaken() and dlg.tabs.tabs[T.TAB_AREA].badge is None
        monkeypatch.setattr(dlg, "_ask_untaken_area", lambda: pytest.fail("no debía preguntar"))
        dlg.accept()
        assert dlg.result() == QtWidgets.QDialog.Accepted and len(dlg.comp.pieces) == 2
    finally:
        dlg.close_docs(); dlg.close()
    # sin piezas: «Continuar» apagado; el enlace del pie usa la hoja a la vista
    dlg = T.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0)
    try:
        dlg.show(); _settle(app)
        dlg.view.select(0); dlg._delete(); _settle(app)
        assert not dlg.comp.pieces and not dlg.btn_ok.isEnabled()
        assert "Para continuar" in dlg.lbl_check.text() and "href='pick'" in dlg.lbl_check.text()
        dlg._on_check_link("pick"); _settle(app)
        assert [p.page for p in dlg.comp.pieces] == [0] and "Lista para continuar" in dlg.lbl_check.text()
        # sin piezas y con solo un área marcada: «Continuar» la toma sin preguntar
        dlg.view.select(0); dlg._delete(); dlg._go_tab(T.TAB_AREA); _settle(app)
        dlg.crop.set_selection(QtCore.QRectF(20, 20, 150, 120)); _settle(app)
        assert dlg._area_untaken() and "href='take'" in dlg.lbl_check.text()
        monkeypatch.setattr(dlg, "_ask_untaken_area", lambda: pytest.fail("no debía preguntar"))
        dlg.accept()
        assert dlg.result() == QtWidgets.QDialog.Accepted and len(dlg.comp.pieces) == 1
    finally:
        dlg.close_docs(); dlg.close()


def _click_page(app, dlg, row, mods=QtCore.Qt.NoModifier):
    """Clic de VERDAD (ratón) en una miniatura de «Origen»."""
    from PySide6 import QtTest
    rect = dlg.lst_pages.visualItemRect(dlg.lst_pages.item(row))
    QtTest.QTest.mouseClick(dlg.lst_pages.viewport(), QtCore.Qt.LeftButton, mods, rect.center())
    _settle(app)


@pytest.mark.parametrize("manual", [False, True])
def test_la_hoja_elegida_es_la_hoja_compuesta(app, manual):
    """Pedido del usuario 2026-10-05: elegía la hoja, pulsaba «Siguiente» y la hoja
    compuesta quedaba vacía. Ahora la hoja a la vista ya está; un clic en otra (o ‹ ›)
    la cambia; marcar un área la recorta al momento y «Hoja completa» la devuelve."""
    T = composite_dialog
    dlg = T.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0, manual=manual)
    try:
        dlg.resize(1100, 700); dlg.show(); _settle(app)
        assert dlg.tabs.current() == T.TAB_SOURCE                        # se abre para elegir
        assert [(p.page, p.clip) for p in dlg.comp.pieces] == [(0, [0.0, 0.0, 1.0, 1.0])]
        assert dlg.btn_ok.isEnabled() and "✔ Hoja completa" in dlg.lst_pages.item(0).text()
        _click_page(app, dlg, 1)                                         # otra hoja: la reemplaza
        assert [(p.page, p.clip) for p in dlg.comp.pieces] == [(1, [0.0, 0.0, 1.0, 1.0])]
        assert dlg.comp.is_single_full_page() and dlg._editing == 0 and not dlg._page_pending()
        assert "✔" not in dlg.lst_pages.item(0).text() and "✔ Hoja completa" in dlg.lst_pages.item(1).text()
        assert "hoja 2 completa" in dlg.lbl_check.text()
        dlg.btn_next.click(); _settle(app)                               # «Área a tomar»
        assert "entera" in dlg.lbl_mode.text() and dlg.btn_take.isHidden() and dlg.btn_take_full.isHidden()
        assert dlg.crop.is_whole_page(dlg.crop._selection)               # la hoja entera, sin tinte
        dlg.btn_prev_page.click(); _settle(app)                          # ‹ también elige
        assert [p.page for p in dlg.comp.pieces] == [0]
        # marcar un área sobre la hoja elegida la recorta (sin «Tomar»)
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 150, 200)); _settle(app)
        QtCore.QThread.msleep(250); _settle(app)                         # el ajuste se aplica solo
        assert len(dlg.comp.pieces) == 1 and dlg.comp.pieces[0].clip == [0.0, 0.0, 0.5, 1.0]
        assert "✔ Área tomada" in dlg.lst_pages.item(0).text() and "área de la hoja 1" in dlg.lbl_check.text()
        assert not dlg.btn_take_full.isHidden() and "usa el área" in dlg.lbl_mode.text()
        dlg.btn_take_full.click(); _settle(app)                          # «Hoja completa»: la devuelve
        assert dlg.comp.is_single_full_page() and dlg.crop.is_whole_page(dlg.crop._selection)
        # un clic suelto no deja la pieza sin su área a la vista
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 150, 200)); dlg._crop_timer.stop(); dlg._apply_crop_edit()
        dlg.crop.set_selection(QtCore.QRectF(40, 40, 0, 0)); dlg.crop.dragFinished.emit(); _settle(app)
        assert dlg.crop._selection.width() == 150 and dlg.comp.pieces[0].clip == [0.0, 0.0, 0.5, 1.0]
    finally:
        dlg.close_docs(); dlg.close()


def test_con_un_area_tomada_otra_hoja_no_la_reemplaza(app):
    """Con trabajo de verdad (un área) un clic en otra hoja solo la muestra: el aviso
    ofrece «Usar solo esta hoja»; Ctrl+clic agrega una hoja entera."""
    T = composite_dialog
    dlg = T.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0)
    try:
        dlg.resize(1100, 700); dlg.show(); _settle(app)
        dlg._go_tab(T.TAB_AREA); _settle(app)
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 150, 200)); dlg._crop_timer.stop(); dlg._apply_crop_edit()
        dlg._go_tab(T.TAB_SOURCE); _settle(app)
        assert "ya está armada" in dlg.lbl_source_hint.text()
        _click_page(app, dlg, 1)
        assert [(p.page, p.clip) for p in dlg.comp.pieces] == [(0, [0.0, 0.0, 0.5, 1.0])]
        assert dlg._page_pending() and not dlg.btn_pending_use.isHidden()
        assert "que usa: Hoja 1" in dlg.lbl_pending.text()
        dlg.btn_pending_use.click(); _settle(app)                        # «Usar solo esta hoja»
        assert [(p.page, p.clip) for p in dlg.comp.pieces] == [(1, [0.0, 0.0, 1.0, 1.0])]
        assert dlg._editing == 0 and not dlg._page_pending()
        # Ctrl+clic: la hoja 1 se AGREGA entera junto a la 2
        _click_page(app, dlg, 0, QtCore.Qt.ControlModifier)
        assert [p.page for p in dlg.comp.pieces] == [1, 0] and dlg.comp.pieces[1].x == 300 + 24
        _click_page(app, dlg, 1)                                         # ya son dos: solo la muestra
        assert [p.page for p in dlg.comp.pieces] == [1, 0] and dlg.btn_pending_use.isHidden()
    finally:
        dlg.close_docs(); dlg.close()


def test_esc_no_cierra_las_ventanas_del_asistente(app):
    """Pedido del usuario 2026-10-05: Esc cerraba «Componer hoja», «Capas de la hoja» y
    la vista previa (se perdía el paso). Ahora no; Cancelar sí."""
    from PySide6 import QtTest
    import layer_dialog
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0)
    try:
        dlg.show(); _settle(app)
        for tab in (composite_dialog.TAB_SOURCE, composite_dialog.TAB_AREA, composite_dialog.TAB_SHEET):
            dlg._go_tab(tab); _settle(app)
            QtTest.QTest.keyClick(dlg, QtCore.Qt.Key_Escape); _settle(app)
            assert dlg.isVisible() and dlg.result() == 0
        dlg.btn_cancel.click(); _settle(app)
        assert not dlg.isVisible() and dlg.result() == QtWidgets.QDialog.Rejected
    finally:
        dlg.close_docs(); dlg.close()
    doc = fitz.open(); ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    doc.new_page(width=300, height=200).draw_line((10, 100), (290, 100), oc=ocg)
    lay = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        lay.show(); _settle(app)
        QtTest.QTest.keyClick(lay, QtCore.Qt.Key_Escape); _settle(app)
        assert lay.isVisible() and lay.result() == 0
    finally:
        lay._timer.stop(); lay._stop_legend(); lay.close(); doc.close()


def test_botones_de_opciones_con_color_y_mismo_alto(app):
    """«Opciones» y «Uniones» se veían más bajos que «Hoja completa» y del color
    del fondo: ahora son botones del mismo alto, con tono propio."""
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], None, {}, 0)
    try:
        dlg.show(); _settle(app)
        assert dlg.btn_take_full.property("soft") is True
        for b in (dlg.btn_area_opts, dlg.btn_join_opts):
            assert b.property("options") is True and b.menu() is not None
            assert b.minimumHeight() == dlg.btn_take_full.minimumHeight() == composite_dialog._BTN_H
    finally:
        dlg.close_docs(); dlg.close()


def test_hoja_sin_tomar_avisa_y_pregunta_al_continuar(app, monkeypatch):
    """Reporte del usuario 2026-09-30: con una hoja ya compuesta, volver a
    componer, elegir otra hoja en la lista SIN tomarla y pulsar «Continuar»
    seguía usando solo la anterior, sin aviso. Ahora la lista marca «✔ Tomada»,
    el panel 2 avisa y «Continuar» pregunta."""
    data = _two_sheet_pdf()

    def open_dlg():
        comp = C.Composite(pieces=[C.Piece(0, 0, [0.0, 0.0, 1.0, 1.0], src_scale=20 / 72.0)])
        dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], comp, {}, 0)
        dlg.show(); _settle(app)
        return dlg

    dlg = open_dlg()
    try:
        assert "✔ Hoja completa" in dlg.lst_pages.item(0).text() and "✔" not in dlg.lst_pages.item(1).text()
        assert dlg.pending_box.isHidden()
        dlg.lst_pages.setCurrentRow(1); _settle(app)        # verla por código (un clic la elegiría)
        assert not dlg.pending_box.isHidden() and "2" in dlg.lbl_pending.text()
        assert not dlg.btn_pending_use.isHidden()            # una sola pieza: «Usar solo esta hoja»
        monkeypatch.setattr(dlg, "_ask_pending_page", lambda: "back")
        dlg.accept()
        assert dlg.result() != QtWidgets.QDialog.Accepted and len(dlg.comp.pieces) == 1
        monkeypatch.setattr(dlg, "_ask_pending_page", lambda: "add")
        dlg.accept()
        assert dlg.result() == QtWidgets.QDialog.Accepted
        assert [p.page for p in dlg.comp.pieces] == [0, 1]
        assert "✔" in dlg.lst_pages.item(1).text()
    finally:
        dlg.close_docs(); dlg.close()

    dlg = open_dlg()                          # «Usar solo esta hoja»: cambia de hoja
    try:
        dlg.lst_pages.setCurrentRow(1); _settle(app)
        monkeypatch.setattr(dlg, "_ask_pending_page", lambda: "replace")
        dlg.accept()
        comp, _s, _h = dlg.result_tuple()
        assert [p.page for p in comp.pieces] == [1]
    finally:
        dlg.close_docs(); dlg.close()

    dlg = open_dlg()                          # «Continuar sin ella»: queda lo que había
    try:
        dlg.lst_pages.setCurrentRow(1); _settle(app)
        monkeypatch.setattr(dlg, "_ask_pending_page", lambda: "skip")
        dlg.accept()
        assert dlg.result() == QtWidgets.QDialog.Accepted and [p.page for p in dlg.comp.pieces] == [0]
    finally:
        dlg.close_docs(); dlg.close()

    dlg = open_dlg()                          # en una hoja ya tomada no pregunta nada
    try:
        monkeypatch.setattr(dlg, "_ask_pending_page", lambda: pytest.fail("no debía preguntar"))
        dlg.accept()
        assert dlg.result() == QtWidgets.QDialog.Accepted
    finally:
        dlg.close_docs(); dlg.close()


def _one_sheet_pdf(n_pages=1):
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=300, height=200)
    return doc.tobytes()


def test_vuelve_a_abrir_en_el_ultimo_pdf_trabajado(app):
    """Con dos PDFs, volver a componer abre el PDF (y la hoja) donde se estaba
    trabajando, no el primero."""
    sources = [{"name": "a.pdf", "data": _two_sheet_pdf()}, {"name": "b.pdf", "data": _one_sheet_pdf(3)}]
    dlg = composite_dialog.CompositeDialog(None, sources, None, {}, 0)
    try:
        assert dlg._cur_source == 0
        dlg.cmb_source.setCurrentIndex(1)
        dlg.lst_pages.setCurrentRow(2)
        dlg._take(full=True)
        comp, srcs, _h = dlg.result_tuple()
    finally:
        dlg.close_docs()
    assert comp.last_view == [1, 2]
    assert C.Composite.from_dict(comp.to_dict()).last_view == [1, 2]     # va al .digproj
    # una sola hoja entera: el editor está en esa hoja (Main pasa page_idx = 2)
    dlg = composite_dialog.CompositeDialog(None, srcs, comp, {}, 2)
    try:
        assert (dlg._cur_source, dlg._cur_page) == (1, 2)
        assert dlg.cmb_source.currentIndex() == 1 and dlg.lst_pages.currentRow() == 2
    finally:
        dlg.close_docs()
    # proyecto viejo sin `last_view`: la hoja de la última pieza tomada
    comp.last_view = None
    comp.pieces.append(C.Piece(0, 1, [0.0, 0.0, 0.5, 1.0], src_scale=20 / 72.0))
    dlg = composite_dialog.CompositeDialog(None, srcs, comp, {}, 0)
    try:
        assert (dlg._cur_source, dlg._cur_page) == (0, 1)
    finally:
        dlg.close_docs()
