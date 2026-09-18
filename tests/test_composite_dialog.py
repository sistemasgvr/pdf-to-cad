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
        assert math.isclose(dlg.comp.pieces[0].clip[2] * 400, 298.5, abs_tol=1e-6)   # por dentro de la línea
        dlg.btn_trim.setChecked(False)
        dlg.crop.set_selection(QtCore.QRectF(0, 0, 308, 300))
        dlg._take(full=False)
        assert math.isclose(dlg.comp.pieces[1].clip[2] * 400, 308, abs_tol=1e-6)
    finally:
        dlg.close_docs()
