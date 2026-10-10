"""Compositor: la imagen de cada pieza cae EXACTA sobre `piece_map` a cualquier zoom.

Reporte del usuario (2026-10-09, escaneos): al unir piezas y hacer zoom «como que se
mueve». La imagen base (vista general, ~0.5–0.7 px/pt) se estiraba a la caja teórica
de la pieza, pero MuPDF redondea el recorte hacia afuera: quedaba corrida hasta 1 px
(1–2 pt); al acercar, el recorte nítido aparecía en su sitio y la pieza saltaba.
"""
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import fitz
import pytest
from PySide6 import QtCore, QtWidgets

from hoja import composite as C
from ui.asistente.composite_view import CompositeView

W, H = 2592.0, 1728.0


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _vista(rotation, polygon=None, clip=(0.1037, 0.0513, 0.8711, 0.9377), manual=True):
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    page.draw_line((1500.37, 0), (1500.37, H), width=0.3)
    piece = C.Piece(0, 0, list(clip), rotation=rotation, x=13.37, y=7.91, polygon=polygon)
    comp = C.Composite([piece], manual=manual, bridges=False)
    view = CompositeView(comp, [doc])
    view.resize(1000, 700)
    view.rebuild()
    return doc, view, view.items[0], C.piece_map(piece, (W, H), comp.target_scale())


@pytest.mark.parametrize("rotation", [0.0, 0.37, -1.23, 33.0, 90.0, 180.0, 270.0])
def test_imagen_base_sobre_piece_map(app, rotation):
    doc, view, it, fn = _vista(rotation)
    try:
        ox, oy = it._origin
        pm = it.pixmap()
        for u, v in ((0, 0), (pm.width(), 0), (pm.width(), pm.height()), (17.3, 41.9)):
            got = it.mapToScene(QtCore.QPointF(u, v))
            want = fn((ox + u) / it.ov, (oy + v) / it.ov)
            assert abs(got.x() - want[0]) < 1e-6 and abs(got.y() - want[1]) < 1e-6
        # zona de clic y contorno siguen siendo la caja envolvente de la pieza
        x0, y0, x1, y1 = C.piece_rect(it.piece, (W, H), view.comp.target_scale())
        r = it.scene_box()
        assert abs(r.left() - x0) < 1e-6 and abs(r.right() - x1) < 1e-6
        assert abs(r.top() - y0) < 1e-6 and abs(r.bottom() - y1) < 1e-6
        assert view.piece_at(QtCore.QPointF(x0 + 0.5, y0 + 0.5)) == 0      # esquina de la caja
        assert view.piece_at(QtCore.QPointF(x0 - 0.5, y0 - 0.5)) == -1
    finally:
        doc.close()


@pytest.mark.parametrize("rotation", [0.0, 0.37, -1.23, 90.0])
def test_recorte_nitido_sobre_piece_map(app, rotation):
    doc, view, it, fn = _vista(rotation)
    try:
        cx, cy = fn(1500.37, 900.0)
        it.update_sharp(QtCore.QRectF(cx - 40, cy - 40, 80, 80), 4.0, 24e6)
        sharp = it._sharp
        assert sharp is not None
        scale = it._sharp_key[-1]
        # píxel (u, v) del recorte = punto ((ox' + u)/scale, …) de la hoja: lo mismo que la base
        p0 = sharp.mapToParent(QtCore.QPointF(0, 0))
        ox_s = (p0.x() + it._origin[0]) * scale / it.ov
        oy_s = (p0.y() + it._origin[1]) * scale / it.ov
        assert abs(ox_s - round(ox_s)) < 1e-6 and abs(oy_s - round(oy_s)) < 1e-6
        for u, v in ((0, 0), (sharp.pixmap().width(), sharp.pixmap().height()), (5.5, 9.25)):
            got = sharp.mapToScene(QtCore.QPointF(u, v))
            want = fn((ox_s + u) / scale, (oy_s + v) / scale)
            assert abs(got.x() - want[0]) < 1e-6 and abs(got.y() - want[1]) < 1e-6
    finally:
        doc.close()


def test_pieza_poligonal_y_vectorial(app):
    """Cuadrilátero de escaneo y pieza del compositor vectorial: misma colocación."""
    for polygon, manual in (([(0.2, 0.1), (0.9, 0.2), (0.8, 0.9), (0.1, 0.8)], True), (None, False)):
        doc, view, it, fn = _vista(7.5, polygon=polygon, clip=(0.1, 0.1, 0.9, 0.9), manual=manual)
        try:
            ox, oy = it._origin
            got = it.mapToScene(QtCore.QPointF(10, 20))
            want = fn((ox + 10) / it.ov, (oy + 20) / it.ov)
            assert math.hypot(got.x() - want[0], got.y() - want[1]) < 1e-6
        finally:
            doc.close()
