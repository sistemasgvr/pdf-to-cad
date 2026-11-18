"""Hojas de otra utilidad que no coinciden una a una con las del editor (`hoja.calcado_parcial`)."""
import pytest

from hoja import calcado_parcial as P


def _h(f, h, tx, ty, w=100.0, hh=100.0, votos=10):
    return P.HojaUbicada(f, h, (1.0, 0.0, tx, ty), (0.0, 0.0, w, hh), votos=votos)


def test_hoja_que_cae_mitad_y_mitad_cubre_las_dos_del_editor():
    libres = [(0, 0, 100, 100), (100, 0, 200, 100)]
    rep = P.repartir([_h(0, 0, 50, 0)], libres)
    assert len(rep) == 1
    _hoja, r, ks = rep[0]
    assert r == (50, 0, 150, 100)          # una sola pieza: los dos trozos se juntan
    assert ks == [0, 1]


def test_dos_hojas_que_se_solapan_se_parten_por_la_mitad():
    libres = [(0, 0, 200, 100)]
    rep = P.repartir([_h(0, 0, 0, 0, w=120), _h(0, 1, 90, 0, w=110)], libres)
    rs = sorted(r for _h_, r, _k in rep)
    assert rs == [(0, 0, 105, 100), (105, 0, 200, 100)]


def test_no_pisa_lo_ya_cubierto_ni_sale_de_la_hoja_del_editor():
    libres = [(100, 0, 200, 100)]
    ocupado = [(0, 0, 100, 100)]
    rep = P.repartir([_h(0, 0, 50, -20, hh=200)], libres, ocupado)
    assert [r for _h_, r, _k in rep] == [(100, 0, 150, 100)]


def test_clip_en_hoja_es_el_inverso():
    h = P.HojaUbicada(0, 0, (2.0, 0.0, 10.0, 20.0), (0, 0, 300, 300))
    clip = P.clip_en_hoja(h, (30.0, 40.0, 110.0, 220.0), (200.0, 400.0))
    assert clip == [10 / 200, 10 / 400, 50 / 200, 100 / 400]


def test_una_hoja_con_celda_toma_su_cuadro_entero_en_una_pieza():
    """2026-11-18: la hoja que sabe su celda dibuja el cuadro de su celda, en UNA pieza (antes se recortaba a
    las piezas del editor que tocaba: «Hoja 4 · 6 piezas» y huecos)."""
    # dos celdas del editor lado a lado; cada hoja nueva es más grande que su celda (márgenes, cajetín)
    libres = [(0.0, 0.0, 100.0, 100.0), (100.0, 0.0, 200.0, 100.0)]
    a = P.HojaUbicada(0, 0, (1.0, 0.0, -30.0, -20.0), (0.0, 0.0, 170.0, 150.0), votos=10, celda=(0,))
    b = P.HojaUbicada(0, 1, (1.0, 0.0, 70.0, -20.0), (0.0, 0.0, 170.0, 150.0), votos=9, celda=(1,))
    rep, tomado = P.repartir_celdas([a, b], [libres[0], libres[1]], libres)
    assert [(h.hoja, r, ks) for h, r, ks in rep] == [(0, libres[0], [0]), (1, libres[1], [1])]
    assert tomado == [libres[0], libres[1]]
    # lo ya cubierto por la 1.ª pasada no se repite
    rep, _t = P.repartir_celdas([a], [libres[0]], libres, ocupado=[(0.0, 0.0, 50.0, 100.0)])
    assert [r for _h, r, _k in rep] == [(50.0, 0.0, 100.0, 100.0)]


def test_prevision_por_celda_compone_las_similaridades():
    from hoja import calcado_completar as CC
    m = (0.8, 0.0, 12.0, -7.0)
    assert CC._compuesta(m, CC._inversa(m)) == pytest.approx((1.0, 0.0, 0.0, 0.0))
    # misma plantilla: la hoja de la celda vecina cae corrida lo mismo que su pieza del editor
    pieza_a, pieza_b = (0.5, 0.0, 0.0, 0.0), (0.5, 0.0, 300.0, 0.0)
    previsto = CC._compuesta(CC._compuesta(pieza_b, CC._inversa(pieza_a)), m)
    assert previsto == pytest.approx((0.8, 0.0, 312.0, -7.0))
    assert CC._celda_txt("17-13") == (17, 13) and CC._celda_txt("") is None
