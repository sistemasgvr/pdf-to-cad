"""Asas de escala en el borde de la pieza elegida (pedido del usuario 2026-11-17):
arrastrar escala con la asa opuesta quieta, imán, Ctrl/Shift, doble clic, giro y
esquinas libres, y el resultado es el de «Escala pieza»."""
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import fitz
import pytest
from PIL import Image, ImageDraw
from PySide6 import QtCore, QtWidgets, QtTest

from hoja import composite as C
from ui.asistente import composite_asas as A
from ui.asistente.composite_dialog import CompositeDialog, TAB_SHEET


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def line_scan(pages=1):
    doc = fitz.open()
    for _ in range(pages):
        img = Image.new("RGB", (300, 200), (236,) * 3)
        ImageDraw.Draw(img).line([(100, 0), (100, 200)], fill="black", width=4)
        s = io.BytesIO(); img.save(s, format="PNG")
        page = doc.new_page(width=300, height=200)
        page.insert_image(page.rect, stream=s.getvalue())
    return doc


def vector_doc():
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.draw_line((20, 150), (380, 150), width=1)
    page.insert_text((30, 40), "PLAN 1\"=20'", fontsize=10)
    return doc


def dialog(doc, manual=True):
    return CompositeDialog(None, [{"name": "a.pdf", "data": doc.tobytes()}], None, {}, manual=manual)


def corners(dlg, i=0):
    return [(q.x(), q.y()) for q in dlg.view.items[i].paper_polygon()]


# ── puro ────────────────────────────────────────────────────────────────
def test_arrastre_iman_fino_y_pasos():
    s0 = 20 / 72
    a = A.ArrastreEscala(s0, 100.0, 100.0, objetivo=s0, notables=[s0, 30 / 72], px_por_pt=1.0)
    assert a.mover(150.0) == (pytest.approx(30 / 72), True)            # imán a otra escala (150 = 30/20·100)
    assert a.mover(165.0) == (pytest.approx(round(20 * 1.65, 2) / 72), False)
    a = A.ArrastreEscala(s0, 100.0, 100.0, objetivo=s0, notables=[s0], px_por_pt=1.0)
    assert a.mover(140.0, fino=True)[0] == pytest.approx(20 * 1.04 / 72)   # Ctrl: ×0.1 y sin imán
    assert a.mover(140.0, pasos=True)[0] == pytest.approx(s0 * 1.05)       # Shift: pasos de 5 %
    a = A.ArrastreEscala(s0, 100.0, 100.0, objetivo=s0, notables=[s0], px_por_pt=1.0)
    assert a.mover(-500.0)[0] == pytest.approx(0.1 / 72)                    # nunca menos que 1" = 0.1'


def test_etiqueta():
    assert A.etiqueta(40 / 72, 20 / 72) == '1" = 40\' · 200 %'


# ── en la ventana ───────────────────────────────────────────────────────
def _vp(dlg, pt):
    return dlg.view.mapFromScene(QtCore.QPointF(*pt))


def test_arrastrar_una_esquina_escala_con_la_opuesta_quieta(app):
    doc = line_scan()
    dlg = dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg._go_tab(TAB_SHEET); app.processEvents()
        dlg.view.fit_all(); dlg.view.select(0); app.processEvents()
        asas = dlg.asas_escala.asas
        assert all(a.isVisible() for a in asas)
        c = corners(dlg)
        assert (asas[4].pos().x(), asas[4].pos().y()) == pytest.approx(c[2])  # esquina abajo-derecha
        s0 = dlg.comp.pieces[0].src_scale
        vp = dlg.view.viewport()
        start = _vp(dlg, c[2])
        assert dlg.view.itemAt(start) is asas[4]
        end = start + QtCore.QPoint(80, 50)
        QtTest.QTest.mousePress(vp, QtCore.Qt.LeftButton, pos=start)
        QtTest.QTest.mouseMove(vp, start + QtCore.QPoint(40, 25))
        assert dlg.asas_escala.rotulo.isVisible() and "%" in dlg.asas_escala.rotulo.texto
        QtTest.QTest.mouseMove(vp, end)
        QtTest.QTest.mouseRelease(vp, QtCore.Qt.LeftButton, pos=end)
        p = dlg.comp.pieces[0]
        assert p.src_scale > s0 * 1.05
        c2 = corners(dlg)
        assert c2[0] == pytest.approx(c[0], abs=1e-6)                 # la esquina opuesta no se movió
        f = (c2[2][0] - c2[0][0]) / (c[2][0] - c[0][0])
        assert (c2[2][1] - c2[0][1]) / (c[2][1] - c[0][1]) == pytest.approx(f)   # uniforme
        assert f == pytest.approx(p.src_scale / s0)
        assert dlg.spn_piece_scale.value() == pytest.approx(p.src_scale * 72, abs=0.006)
        assert not dlg.asas_escala.rotulo.isVisible()
        # la escala de la hoja compuesta queda la de antes: la pieza se ve más grande
        assert dlg.comp.target_scale() == pytest.approx(s0)
        # doble clic en una asa = de vuelta a la escala de la hoja compuesta
        app.processEvents()
        h = _vp(dlg, (asas[0].pos().x(), asas[0].pos().y()))
        # QTest manda solo el «doble clic»: antes, el 1.er clic (sin moverse, nada cambia)
        s1 = p.src_scale
        QtTest.QTest.mouseClick(vp, QtCore.Qt.LeftButton, pos=h)
        assert dlg.comp.pieces[0].src_scale == s1
        QtTest.QTest.mouseDClick(vp, QtCore.Qt.LeftButton, pos=h)
        assert dlg.comp.pieces[0].src_scale == pytest.approx(s0)
        assert dlg.comp.scale_ft_per_pt is None                       # todo igual que al empezar
        assert corners(dlg)[2] == pytest.approx(c2[2], abs=1e-6)        # quieta la opuesta a la del doble clic
    finally:
        dlg.close_docs(); doc.close()


def test_iman_a_la_escala_de_otra_pieza_y_vuelve_a_automatica(app):
    doc = line_scan(pages=2)
    dlg = dialog(doc)
    try:
        dlg._take_area(True)
        dlg.lst_pages.setCurrentRow(1)
        dlg._take_area(True)
        dlg.comp.pieces[1].src_scale = dlg.comp.pieces[0].src_scale * 1.5
        dlg.view.refresh_all()
        dlg.show(); app.processEvents()
        dlg._go_tab(TAB_SHEET); app.processEvents()
        dlg.view.select(1); app.processEvents()
        ctrl = dlg.asas_escala
        pts = ctrl.puntos(1)
        piv = (pts[0].x(), pts[0].y())
        a = pts[4]
        objetivo = dlg.comp.target_scale()
        s0 = dlg.comp.pieces[1].src_scale
        assert ctrl.empezar(4, a)
        # el ratón casi donde la pieza queda a la escala de la otra (100 %): imán
        k = objetivo / s0 * 1.002
        ctrl.mover(QtCore.QPointF(piv[0] + (a.x() - piv[0]) * k, piv[1] + (a.y() - piv[1]) * k))
        assert ctrl.rotulo.iman
        assert dlg.comp.pieces[1].src_scale == pytest.approx(objetivo)
        ctrl.soltar()
        assert dlg.comp.scale_ft_per_pt is None
        q = ctrl.puntos(1)[0]
        assert (q.x(), q.y()) == pytest.approx(piv, abs=1e-6)
        assert not dlg.cmb_scale.isVisible()                           # una sola escala
    finally:
        dlg.close_docs(); doc.close()


def test_shift_y_ctrl_con_el_raton(app):
    doc = line_scan()
    dlg = dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg._go_tab(TAB_SHEET); app.processEvents()
        dlg.view.select(0); app.processEvents()
        ctrl = dlg.asas_escala
        pts = ctrl.puntos(0)
        s0 = dlg.comp.pieces[0].src_scale
        piv, a = pts[2], pts[6]                   # asa 6 (esquina abajo-izq.), fija la 2 (arriba-der.)
        assert ctrl.empezar(6, a)
        lejos = QtCore.QPointF(piv.x() + (a.x() - piv.x()) * 1.33, piv.y() + (a.y() - piv.y()) * 1.33)
        ctrl.mover(lejos, QtCore.Qt.ShiftModifier)
        assert dlg.comp.pieces[0].src_scale == pytest.approx(s0 * 1.35)
        ctrl.mover(lejos, QtCore.Qt.ControlModifier)            # sin moverse: no cambia
        assert dlg.comp.pieces[0].src_scale == pytest.approx(round(s0 * 1.33 * 72, 2) / 72)
        ctrl.soltar()
        q = ctrl.puntos(0)[2]
        assert (q.x(), q.y()) == pytest.approx((piv.x(), piv.y()), abs=1e-6)
    finally:
        dlg.close_docs(); doc.close()


@pytest.mark.parametrize("manual", [True, False])
def test_con_giro_y_esquinas_libres(app, manual):
    doc = line_scan() if manual else vector_doc()
    dlg = dialog(doc, manual=manual)
    try:
        dlg._take_area(True)
        p = dlg.comp.pieces[0]
        p.rotation = 30.0
        p.polygon = [(0.1, 0.05), (0.9, 0.0), (0.95, 0.9), (0.05, 1.0)]
        dlg.view.refresh_all()
        dlg.show(); app.processEvents()
        dlg._go_tab(TAB_SHEET); app.processEvents()
        dlg.view.select(0); app.processEvents()
        ctrl = dlg.asas_escala
        pts = ctrl.puntos(0)
        assert [(q.x(), q.y()) for q in pts[0::2]] == pytest.approx(corners(dlg))
        s0 = p.src_scale
        piv, a = pts[7], pts[3]                    # medio de un lado ↔ medio del opuesto
        assert ctrl.empezar(3, a)
        ctrl.mover(QtCore.QPointF(piv.x() + (a.x() - piv.x()) * 0.7, piv.y() + (a.y() - piv.y()) * 0.7))
        ctrl.soltar()
        assert p.src_scale == pytest.approx(round(s0 * 0.7 * 72, 2) / 72)
        assert p.rotation == 30.0
        q = ctrl.puntos(0)[7]
        assert (q.x(), q.y()) == pytest.approx((piv.x(), piv.y()), abs=1e-6)
    finally:
        dlg.close_docs(); doc.close()


def test_sin_pieza_elegida_no_hay_asas_y_mover_la_pieza_sigue(app):
    doc = line_scan()
    dlg = dialog(doc)
    try:
        dlg._take_area(True)
        dlg.show(); app.processEvents()
        dlg._go_tab(TAB_SHEET); app.processEvents()
        dlg.view.scene().clearSelection(); app.processEvents()
        assert not any(a.isVisible() for a in dlg.asas_escala.asas)
        dlg.view.select(0); app.processEvents()
        c = corners(dlg)
        vp = dlg.view.viewport()
        mid = _vp(dlg, ((c[0][0] + c[2][0]) / 2, (c[0][1] + c[2][1]) / 2))
        x0 = dlg.comp.pieces[0].x
        s0 = dlg.comp.pieces[0].src_scale
        QtTest.QTest.mousePress(vp, QtCore.Qt.LeftButton, pos=mid)
        QtTest.QTest.mouseMove(vp, mid + QtCore.QPoint(30, 0))
        QtTest.QTest.mouseRelease(vp, QtCore.Qt.LeftButton, pos=mid + QtCore.QPoint(30, 0))
        assert dlg.comp.pieces[0].x > x0 and dlg.comp.pieces[0].src_scale == s0
        app.processEvents(); app.processEvents()
        assert (dlg.asas_escala.asas[0].pos().x(), dlg.asas_escala.asas[0].pos().y()) == pytest.approx(corners(dlg)[0])
    finally:
        dlg.close_docs(); doc.close()
