"""El compositor no vuelve a dibujar las piezas que ya dibujó (pedido del usuario 2026-11-17: al volver a «Componer
hoja» para sumar una hoja, se rehacía TODA la composición). `composite_renders` guarda cada imagen con lo que la
decide; la imagen que sale de la memoria es la misma que dibujarla de nuevo."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("pymupdf")
from PySide6 import QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from ui.asistente import composite_renders as CR  # noqa: E402
from ui.asistente import composite_view as CV  # noqa: E402


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _bytes(paginas=3):
    doc = fitz.open()
    for i in range(paginas):
        pg = doc.new_page(width=600, height=400)
        pg.insert_text((50, 60), f"hoja {i + 1}")
        pg.draw_line((50, 200), (550, 200 + 10 * i))
    data = doc.tobytes()
    doc.close()
    return data


def _vista(data, comp):
    doc = fitz.open(stream=data, filetype="pdf")
    CR.marcar(doc, data)
    return CV.CompositeView(comp, [doc]), doc


def _imagen(pm):
    img = pm.toImage()
    return bytes(img.constBits()[:img.sizeInBytes()])


def test_volver_a_abrir_no_dibuja_otra_vez_y_da_la_misma_imagen(app, monkeypatch):
    CR.soltar()
    data = _bytes()
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1], 0, 0), C.Piece(0, 1, [0, 0, 1, 1], 600, 0)])
    v1, d1 = _vista(data, comp)
    v1.rebuild()
    primeras = [(_imagen(it._raw_pm if hasattr(it, "_raw_pm") else v1.render_piece(it.piece, v1.overview_scale(it.piece))))
                for it in v1.items]
    # otra apertura del compositor (otro documento, mismos bytes) con una hoja MÁS
    comp2 = C.Composite([C.Piece.from_dict(p.to_dict()) for p in comp.pieces] + [C.Piece(0, 2, [0, 0, 1, 1], 1200, 0)])
    v2, d2 = _vista(data, comp2)
    dibujadas = []
    orig = CV.CompositeView._render_piece_raw
    monkeypatch.setattr(CV.CompositeView, "_render_piece_raw",
                        lambda self, p, s: dibujadas.append(p.page) or orig(self, p, s))
    v2.rebuild()
    assert dibujadas == [2]                                  # solo la hoja nueva
    # la imagen de la memoria = dibujarla de nuevo
    for p in comp.pieces:
        s = v2.overview_scale(p)
        pm_mem, o_mem = v2.render_piece_raw(p, s)
        pm_new, o_new = orig(v2, p, s)
        assert o_mem == o_new and _imagen(pm_mem) == _imagen(pm_new)
    assert primeras
    for d in (d1, d2):
        d.close()


def test_otras_capas_u_otro_recorte_se_dibujan_de_nuevo(app):
    CR.soltar()
    data = _bytes()
    p = C.Piece(0, 0, [0, 0, 1, 1])
    v, d = _vista(data, C.Composite([p]))
    k1 = CR.clave(d, p, 1.0)
    otra = C.Piece(0, 0, [0, 0, 0.5, 1])
    assert CR.clave(d, otra, 1.0) != k1 and CR.clave(d, p, 0.5) != k1
    sin = fitz.open(stream=data, filetype="pdf")             # sin marcar: no usa la memoria
    assert CR.clave(sin, p, 1.0) is None
    for x in (d, sin):
        x.close()
