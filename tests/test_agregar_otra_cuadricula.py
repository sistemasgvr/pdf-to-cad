"""«Agregar utilidad»: la utilidad nueva viene en OTRA cuadrícula y dibujada DISTINTO.

Pedido del usuario 2026-11-17: una hoja del PDF nuevo puede caer mitad y mitad sobre dos hojas del
editor, y su mapa base puede ser otra exportación del mismo lugar (ningún trazo idéntico: cada lote
partido en otro vértice, otra escala, otro margen). Se ubica por la forma (`encaje_robusto`) y se
reparte entre las piezas del editor sin cubrir (`calcado_parcial`, `calcado_completar`).
"""
import math
import random

import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("cv2")
pytest.importorskip("scipy")

from hoja import composite as C  # noqa: E402
from hoja import hoja_calcada as H  # noqa: E402
from test_agregar_utilidad import AGUA, LADO_FT, _editor, _mapa_base, _pdf, TUBO  # noqa: E402


def _mundo():
    """El mapa base de las dos cuadrículas en coordenadas del terreno (pies): la 1 a la derecha."""
    out = []
    for c in (0, 1):
        out += [(x0 + c * LADO_FT, y0, x1 + c * LADO_FT, y1) for x0, y0, x1, y1 in _mapa_base(c)]
    return out


def _pdf_otra_cuadricula(path, ventanas, escala=0.8, off=(40.0, 40.0), tam=(900.0, 900.0)):
    """Un PDF «drenaje»: cada hoja muestra la ventana (x0, x1) del terreno, a otra escala, y con cada
    trazo partido en otro punto (otra exportación: ningún trazo es idéntico al del editor)."""
    rnd = random.Random(7)
    doc = fitz.open()
    for wx0, wx1 in ventanas:
        pg = doc.new_page(width=tam[0], height=tam[1])
        sh = pg.new_shape()

        def p(x, y):
            return fitz.Point(off[0] + escala * (x - wx0), off[1] + escala * y)
        for x0, y0, x1, y1 in _mundo():
            if not (wx0 <= min(x0, x1) and max(x0, x1) <= wx1):
                continue
            k = rnd.uniform(0.3, 0.7)
            xm, ym = x0 + k * (x1 - x0), y0 + k * (y1 - y0)
            sh.draw_line(p(x0, y0), p(xm, ym))
            sh.draw_line(p(xm, ym), p(x1, y1))
        sh.finish(color=(0, 0, 0), width=0.5)
        sh.draw_rect(fitz.Rect(5, 5, tam[0] - 5, tam[1] - 5))
        sh.finish(color=(0, 0, 0), width=0.5)
        sh.commit()
    doc.save(str(path))
    doc.close()
    return str(path)


def _en_compuesta(comp, agua, wx, wy):
    """Un punto del terreno (pies) en la hoja compuesta del editor."""
    celda = 0 if wx < LADO_FT else 1
    p = comp.pieces[celda]
    return C.piece_map(p, (agua[0].rect.width, agua[0].rect.height), comp.target_scale())(
        AGUA["off"][0] + AGUA["escala"] * (wx - celda * LADO_FT), AGUA["off"][1] + AGUA["escala"] * wy)


def test_hojas_que_caen_mitad_y_mitad_y_dibujadas_distinto(tmp_path):
    agua = fitz.open(_pdf(tmp_path / "agua.pdf", AGUA, [0, 1], TUBO["agua"]))
    ventanas = [(500.0, 1500.0), (900.0, 1900.0)]
    sd = fitz.open(_pdf_otra_cuadricula(tmp_path / "sd.pdf", ventanas))
    comp = _editor(agua)
    cal = H.calcar(comp, [agua], [sd], ["sd.pdf"])
    assert cal.comp is not None and cal.sin_pareja == []
    t = cal.comp.target_scale()
    rects = []
    for q in cal.comp.pieces:
        wx0 = ventanas[q.page][0]
        tam = (sd[q.page].rect.width, sd[q.page].rect.height)
        m = C.piece_map(q, tam, t)
        # un punto del terreno cae en el mismo lugar por la hoja nueva y por el editor (≤ 1 pt)
        for wx, wy in ((wx0 + 300.0, 300.0), (wx0 + 500.0, 700.0)):
            assert math.dist(_en_compuesta(comp, agua, wx, wy), m(40.0 + 0.8 * (wx - wx0), 40.0 + 0.8 * wy)) < 1.0
        rects.append(C.piece_rect(q, tam, t))
    # entre las dos cubren la hoja del editor de la 1.ª ventana a la 2.ª, sin salir de ella ni solaparse
    lado = LADO_FT * AGUA["escala"]
    assert min(r[0] for r in rects) <= 500.0 * AGUA["escala"] + 1.0     # (sin recuadro de mapa: la hoja entera)
    assert 1900.0 * AGUA["escala"] - 1.0 <= max(r[2] for r in rects) <= 2 * lado + 0.01   # (hasta su borde)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert min(a[2], b[2]) - max(a[0], b[0]) <= 0.01 or min(a[3], b[3]) - max(a[1], b[1]) <= 0.01


def test_pdf_de_otro_lugar_no_se_ubica(tmp_path):
    agua = fitz.open(_pdf(tmp_path / "agua.pdf", AGUA, [0, 1], TUBO["agua"]))
    otro = fitz.open()
    pg = otro.new_page(width=800, height=800)
    rnd = random.Random(99)
    sh = pg.new_shape()
    for _ in range(400):
        x, y = rnd.uniform(20, 700), rnd.uniform(20, 700)
        if rnd.random() < 0.5:
            sh.draw_line((x, y), (x + rnd.uniform(20, 80), y))
        else:
            sh.draw_line((x, y), (x, y + rnd.uniform(20, 80)))
    sh.finish(color=(0, 0, 0), width=0.3)
    sh.commit()
    cal = H.calcar(_editor(agua), [agua], [otro], ["otro.pdf"])
    assert cal.comp is None
