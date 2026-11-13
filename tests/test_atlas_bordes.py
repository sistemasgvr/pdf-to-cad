"""Atlas cuyas hojas dicen sus vecinas en los BORDES (Southwest Gas «Combined 811 Records», reporte
2026-11-13): la celda «14-6» en grande y «15-6» arriba, «13-6» abajo, «14-5» a la izquierda y «14-7»
a la derecha; sin mapa índice ni prefijo Q la composición sugerida no unía nada. Las hojas se tocan
borde con borde por su marco (no se solapan): se unen poniendo el lado del marco de una sobre el de
la otra."""
import math
import os

import fitz
import pytest

from hoja import composicion_ficha as F, composicion_sugerida as G

W, H = 1200.0, 1000.0
MARCO = (200.0, 120.0, 1000.0, 840.0)       # el mapa: 800 × 720 pt
CELDA = 100.0                              # pt del mundo por… (el mapa es 800 pt de mundo por hoja)


def _hoja(doc, fila, col):
    pg = doc.new_page(width=W, height=H)
    x0, y0, x1, y1 = MARCO
    # el mapa va dentro de su RECORTE (como el de ArcGIS): calles del «mundo» continuas entre hojas
    src = fitz.open()
    m = src.new_page(width=x1 - x0, height=y1 - y0)
    ox, oy = col * (x1 - x0), -fila * (y1 - y0)
    for k in range(-2, 14):
        gx = 37.0 + 160.0 * k - (ox % 160.0)
        if 0 < gx < x1 - x0:
            m.draw_line((gx, 0), (gx, y1 - y0), color=(0.6, 0.6, 0.1), width=0.5)
        gy = 53.0 + 144.0 * k - (oy % 144.0)
        if 0 < gy < y1 - y0:
            m.draw_line((0, gy), (x1 - x0, gy), color=(0.1, 0.5, 0.1), width=0.5)
        if 0 < gx < x1 - x0:                      # diagonales cortas: dos rumbos para el encaje
            m.draw_line((gx, 10), (gx + 30, 40), color=(0.8, 0.1, 0.1), width=0.5)
    pg.show_pdf_page(fitz.Rect(MARCO), src, 0)
    pg.draw_rect(fitz.Rect(MARCO), color=(0, 0, 0), width=2.0)
    # rótulos: la celda en grande y las vecinas junto a cada borde
    pg.insert_text((1020, 960), f"{fila}-{col}", fontsize=34)
    pg.insert_text((W / 2 - 15, 60), f"{fila + 1}-{col}", fontsize=14)
    pg.insert_text((W / 2 - 15, H - 50), f"{fila - 1}-{col}", fontsize=14)
    pg.insert_text((40, H / 2), f"{fila}-{col - 1}", fontsize=14)
    pg.insert_text((W - 90, H / 2), f"{fila}-{col + 1}", fontsize=14)
    pg.insert_text((600, 500), "863-1", fontsize=6)      # un número suelto no es una vecina
    return pg


def _atlas(celdas):
    doc = fitz.open()
    for f, c in celdas:
        _hoja(doc, f, c)
    return fitz.open(stream=doc.tobytes(), filetype="pdf")


def test_vecinas_escritas_en_los_bordes_dan_la_celda():
    doc = _atlas([(14, 6)])
    f = F.ficha(doc[0], 0)
    assert f.celda == (14, 6) and f.por_bordes and f.tipo == "cuadricula"
    assert f.vecinas == {(15, 6): (0, -1), (13, 6): (0, 1), (14, 5): (-1, 0), (14, 7): (1, 0)}
    assert f.marco and len(f.marco) == 4


def test_atlas_de_2x2_un_solo_grupo_borde_con_borde():
    doc = _atlas([(14, 6), (14, 7), (15, 6), (15, 7)])
    fs = F.fichas(doc, 0)
    an = G.analizar([fs])
    assert [len(g.nodos) for g in an.grupos] == [4]
    g = an.grupos[0]
    assert {c.metodo for c in g.costuras} == {"marco"} and g.residuo < 1.0
    # 14-7 queda a la derecha de 14-6, borde con borde (una raya de marco sobre la otra)
    a6, bx6, by6 = g.transf[(0, 0)]
    a7, bx7, by7 = g.transf[(0, 1)]
    x_der_6 = a6 * MARCO[2] + bx6
    x_izq_7 = a7 * MARCO[0] + bx7
    assert abs(x_der_6 - x_izq_7) < 0.2 and abs((a6 * MARCO[1] + by6) - (a7 * MARCO[1] + by7)) < 0.2
    # 15-6 queda ARRIBA de 14-6
    a15, bx15, by15 = g.transf[(0, 2)]
    assert abs((a15 * MARCO[3] + by15) - (a6 * MARCO[1] + by6)) < 0.2


def test_sin_rotulos_en_los_bordes_sigue_sin_celda():
    doc = fitz.open()
    pg = doc.new_page(width=W, height=H)
    pg.insert_text((1020, 960), "14-6", fontsize=34)
    f = F.ficha(fitz.open(stream=doc.tobytes(), filetype="pdf")[0], 0)
    assert f.celda is None


SW = os.path.join(os.path.expanduser("~"), "Downloads", "Southwest Gas Combined 811 Records.pdf")


@pytest.mark.skipif(not os.path.exists(SW), reason="sin el PDF de Southwest Gas")
def test_southwest_gas_las_54_hojas_en_un_grupo():
    doc = fitz.open(SW)
    fs = F.fichas(doc, 0)
    an = G.analizar([fs])
    assert [len(g.nodos) for g in an.grupos] == [54]
    assert an.grupos[0].residuo < 3.0
