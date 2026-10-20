"""«Esquinas libres» en «Área a tomar» (pedido del usuario 2026-10-19): en los tres flujos
—PDF con capas, PDF vectorial aplanado y escaneo— el área se ajusta esquina por esquina,
con una casilla para encenderlo y apagarlo. Hojas sintéticas chicas: solo la zona del corte."""
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

from hoja import composite as C  # noqa: E402
from ui.asistente import composite_dialog  # noqa: E402
from reconocimiento import recognition  # noqa: E402

# corte inclinado: el lado derecho va de (300, 0) a (340, 300) → x = 300 + 40·y/300
QUAD_PT = [(10.0, 0.0), (300.0, 0.0), (340.0, 300.0), (10.0, 300.0)]
QUAD = [(x / 400.0, y / 300.0) for x, y in QUAD_PT]
ROWS = (60.0, 150.0, 240.0)


def _edge_x(y):
    return 300.0 + 40.0 * y / 300.0


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _sheet(layers=True):
    """Hoja 400×300 con tres líneas de la red de x=20 a 380 (y = ROWS). Con capas, en la
    eléctrica; sin capas (aplanada), sin ningún OCG."""
    doc = fitz.open()
    ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True) if layers else 0
    page = doc.new_page(width=400, height=300)
    for y in ROWS:
        page.draw_line((20, y), (380, y), color=(0, 0, 0), width=0.8, oc=ocg)
    return doc.tobytes()


def _dialog(data, comp=None, manual=False):
    return composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], comp, {}, 0, manual=manual)


def _quad_area(dlg):
    """Marca el rectángulo de la caja y lleva la esquina superior derecha a (300, 0)."""
    dlg.crop.set_selection(QtCore.QRectF(10, 0, 330, 300))
    dlg.crop._move_corner("tr", QtCore.QPointF(300, 0))


def _right_ends(page, layers=True):
    """x máxima de cada una de las tres líneas tal como las ve el reconocimiento (recortadas)."""
    kind = next(iter(recognition.DRAW_KINDS))
    kind_for = (lambda ocg: recognition.classify_ocg(ocg)) if layers else (lambda ocg: kind if ocg else None)
    lines, _vaults, _counts, _kinds = recognition.gather_paths(page, kind_for)
    ends = {}
    for path in lines:
        pts = [(q.x, q.y) if hasattr(q, "x") else (q[0], q[1])
               for it in path["items"] for q in (it[1], it[-1])]
        y = round(sum(q[1] for q in pts) / len(pts))
        ends[y] = max(ends.get(y, -1e9), max(q[0] for q in pts))
    return ends


@pytest.mark.parametrize("layers", [True, False])
def test_area_esquina_por_esquina_en_pdf_vectorial(app, layers):
    dlg = _dialog(_sheet(layers))
    try:
        assert not dlg.chk_corners.isChecked() and not dlg.crop.free     # apagada: el rectángulo de siempre
        dlg.chk_corners.setChecked(True)
        assert dlg.crop.free
        _quad_area(dlg)
        dlg._take(full=False)                     # la hoja elegida está en edición: se actualiza
        piece = dlg.comp.pieces[0]
        assert piece.polygon == pytest.approx(QUAD)
        assert piece.clip == pytest.approx([10 / 400, 0.0, 340 / 400, 1.0])
        assert piece.covers == {}                 # «Sin línea de borde» no aplica a un cuadrilátero
        comp, sources, hidden = dlg.result_tuple()
    finally:
        dlg.close_docs()
    # la hoja compuesta y el reconocimiento cortan por el lado INCLINADO, no por la caja
    src = fitz.open(stream=sources[0]["data"], filetype="pdf")
    built = C.build_document(comp, [src], hidden)
    work = fitz.open(stream=built.tobytes(), filetype="pdf")
    built.close()
    size = (400.0, 300.0)
    _, _, dx, dy = C.sheet_geometry(comp, lambda p: size)
    fn = C.piece_map(comp.pieces[0], size, comp.target_scale())
    ends = _right_ends(work[0], layers)
    assert len(ends) == 3
    for y in ROWS:
        ex, ey = fn(_edge_x(y), y)
        assert ends[round(ey + dy)] == pytest.approx(ex + dx, abs=0.05)
    work.close(); src.close()


def test_rectangulo_sigue_igual_con_la_casilla_encendida(app):
    """Encendida pero sin mover ninguna esquina: es un rectángulo y todo va como siempre
    (sin polígono, con «Sin línea de borde»)."""
    dlg = _dialog(_sheet())
    try:
        dlg.chk_corners.setChecked(True)
        dlg.crop.set_selection(QtCore.QRectF(10, 0, 330, 300))
        assert dlg.crop.normalized_polygon() == []
        dlg._take(full=False)
        assert dlg.comp.pieces[0].polygon == []
        assert dlg.comp.pieces[0].clip == pytest.approx([10 / 400, 0.0, 340 / 400, 1.0])
    finally:
        dlg.close_docs()


def test_apagar_la_casilla_vuelve_al_rectangulo(app):
    dlg = _dialog(_sheet())
    try:
        dlg.chk_corners.setChecked(True)
        _quad_area(dlg)
        dlg._apply_crop_edit()
        assert dlg.comp.pieces[0].polygon
        dlg.chk_corners.setChecked(False)
        assert not dlg.crop.free and dlg.crop.polygon == []
        assert dlg.crop._selection == QtCore.QRectF(10, 0, 330, 300)          # la caja del cuadrilátero
        assert all(dlg.crop._handles[n].isVisible() for n in ("top", "right", "bottom", "left"))
        dlg._apply_crop_edit()
        assert dlg.comp.pieces[0].polygon == []
    finally:
        dlg.close_docs()


def test_editar_una_pieza_con_cuadrilatero_enciende_la_casilla(app):
    comp = C.Composite([C.Piece(0, 0, [10 / 400, 0.0, 340 / 400, 1.0], polygon=QUAD),
                        C.Piece(0, 0, [0.0, 0.0, 0.5, 0.5], x=500.0)])
    dlg = _dialog(_sheet(), comp=comp)
    try:
        assert not dlg.chk_corners.isChecked()
        dlg.view.select(0)
        assert dlg.chk_corners.isChecked() and dlg.crop.free
        got = [(p.x(), p.y()) for p in dlg.crop.polygon]
        assert got == pytest.approx(QUAD_PT)
        assert dlg.comp.pieces[0].polygon == pytest.approx(QUAD)                 # mostrarla no la cambia
    finally:
        dlg.close_docs()


def test_escaneo_casilla_encendida_y_se_puede_apagar(app):
    dlg = _dialog(_sheet(layers=False), manual=True)
    try:
        assert dlg.chk_corners.isChecked() and dlg.crop.free                    # como siempre en el escaneo
        dlg.chk_corners.setChecked(False)
        dlg.crop.set_selection(QtCore.QRectF(30, 20, 240, 160))
        assert dlg.crop.polygon == [] and dlg.crop._shape.isVisible()
        dlg._take(full=False)
        assert dlg.comp.pieces[0].polygon == []
    finally:
        dlg.close_docs()


def test_lados_paralelos_e_iman_de_esquina(app):
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=1.0)      # match line vertical
    page.draw_line((20, 250), (380, 250), color=(0, 0, 0), width=1.0)      # borde inferior
    dlg = _dialog(doc.tobytes())
    try:
        dlg.chk_corners.setChecked(True)
        crop = dlg.crop
        crop.set_selection(QtCore.QRectF(10, 10, 200, 200))
        # esquina cerca de la intersección (296, 246) → (300, 250)
        crop._drag_mode = "br"; crop._drag_start = QtCore.QPointF(210, 210)
        crop._apply_drag(QtCore.QPointF(296, 246))
        assert (crop.polygon[2].x(), crop.polygon[2].y()) == pytest.approx((300, 250))
        # el lado de arriba baja 5 pt entero (sus dos esquinas)
        crop._drag_mode = "top"; crop._drag_start = QtCore.QPointF(100, 10)
        crop._initial_polygon = list(crop.polygon)
        crop._apply_drag(QtCore.QPointF(100, 15))
        assert crop.polygon[0].y() == pytest.approx(15) and crop.polygon[1].y() == pytest.approx(15)
        assert (crop.polygon[2].x(), crop.polygon[2].y()) == pytest.approx((300, 250))
        # imán apagado: la esquina queda donde se suelta
        dlg.btn_area_snap.setChecked(False)
        crop._drag_mode = "br"
        crop._apply_drag(QtCore.QPointF(296, 246))
        assert (crop.polygon[2].x(), crop.polygon[2].y()) == pytest.approx((296, 246))
    finally:
        dlg.close_docs()


def test_extremos_y_puentes_sobre_el_lado_inclinado():
    doc = fitz.open(stream=_sheet(), filetype="pdf")
    page = doc[0]
    anchors = C.edge_anchors(page, [10 / 400, 0.0, 340 / 400, 1.0], polygon=QUAD)
    right = sorted((a for a in anchors if a.x > 200), key=lambda a: a.y)
    assert [(a.x, a.y) for a in right] == pytest.approx([(_edge_x(y), y) for y in ROWS], abs=1e-6)
    assert all(a.ux == pytest.approx(1.0) and a.on_edge for a in right)
    # sin cuadrilátero, lo de siempre: el corte en la caja (x = 340)
    plain = [a for a in C.edge_anchors(page, [10 / 400, 0.0, 340 / 400, 1.0]) if a.x > 200]
    assert all(a.x == pytest.approx(340) for a in plain)
    doc.close()
    # hoja girada: el cuadrilátero pasa a coords de get_drawings igual que un rectángulo
    from hoja.composite_esquinas import drawing_quad
    from hoja.sheet_crops import drawing_polygon
    rot = fitz.open(stream=_sheet(), filetype="pdf")
    rot[0].set_rotation(90)
    w, h = rot[0].rect.width, rot[0].rect.height
    box = [(0.1, 0.2), (0.7, 0.2), (0.7, 0.9), (0.1, 0.9)]
    assert drawing_quad(rot[0], box) == pytest.approx(drawing_polygon(rot[0], fitz.Rect(0.1 * w, 0.2 * h, 0.7 * w, 0.9 * h)))
    rot.close()
    # el puente sigue recto hasta el borde del cuadrilátero, no hasta la caja
    shape = [(0.0, 0.0), (10.0, 0.0), (14.0, 10.0), (0.0, 10.0)]
    assert C._ray_exit(shape, (5.0, 5.0), (1.0, 0.0)) == pytest.approx((12.0, 5.0))
    assert C._ray_exit((0.0, 0.0, 14.0, 10.0), (5.0, 5.0), (1.0, 0.0)) == pytest.approx((14.0, 5.0))
    br = C.Bridge(0, (5.0, 5.0), 1, (20.0, 5.0), "L", "L", ua=(1.0, 0.0), ub=(-1.0, 0.0))
    assert br.polyline(shape, (16.0, 0.0, 30.0, 10.0)) == pytest.approx([(5.0, 5.0), (12.0, 5.0), (16.0, 5.0), (20.0, 5.0)])
