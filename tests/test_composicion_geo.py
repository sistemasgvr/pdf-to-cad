"""Composición sugerida por la GEORREFERENCIA de cada hoja (`hoja/composicion_geo`, sin Qt).

Reporte del usuario (2026-11-19, «QS SD_Indian School» North + South): la sugerencia salía en 8 grupos (32 uniones
descartadas) cuando es UNA sola composición. Cada hoja sabe su celda en el mundo; las uniones que el dibujo no
confirma se sacan de ahí, con la escala calibrada por las que sí confirma.
"""
import math
import os

import pytest

from geo.auto import indice_mapas
from hoja import composicion_encaje as E
from hoja import composicion_geo as CG
from hoja import composicion_sugerida as G
from hoja.composicion_ficha import Ficha

K = 1.389                          # pies del mundo por pt (1"=100')


def _ficha(doc, hoja, x, y):
    f = Ficha(doc, hoja, (3168.0, 2448.0))
    f.geo = (2868, "%d-%d" % (hoja, doc), x, y)
    return f


def _costura(fa, fb, lado):
    """La unión verdadera B = A + t (misma plantilla): t = Δ/k con la «y» al revés."""
    t = ((fa.geo[2] - fb.geo[2]) / K, -(fa.geo[3] - fb.geo[3]) / K)
    return E.Costura(fa.clave, fb.clave, lado, 1.0, t, "solape", 100.0)


def test_calibra_la_escala_y_predice_las_uniones_que_faltan():
    fs = [_ficha(0, i, 600000.0 + 2640.0 * i, 906300.0 + 15.0 * i) for i in range(4)]
    fichas = {f.clave: f for f in fs}
    ks = CG.calibrar([_costura(fs[0], fs[1], "right")], fichas)
    assert ks[0] == pytest.approx(K)
    s, t = CG.prediccion(fs[2], fs[3], ks)
    real = _costura(fs[2], fs[3], "right")
    assert s == pytest.approx(1.0) and math.dist(t, real.t) < 1e-6


def test_lo_que_el_dibujo_no_confirma_se_une_por_georreferencia():
    fs = [_ficha(0, i, 600000.0 + 2640.0 * i, 906300.0) for i in range(3)]
    fichas = {f.clave: f for f in fs}
    hechas = [_costura(fs[0], fs[1], "right")]

    class SinDibujo(G.Encajes):
        def mapa(self, fa, fb, lado, escala=None, guia=None):
            return None
    descartadas = G._por_georreferencia([(fs[1], "right", fs[2])], hechas, fichas, None, SinDibujo())
    assert descartadas == 0 and len(hechas) == 2
    c = hechas[1]
    assert c.metodo == "georef" and c.votos < hechas[0].votos
    assert math.dist(c.t, _costura(fs[1], fs[2], "right").t) < 1e-6


def test_sin_georreferencia_ni_escala_queda_como_antes():
    fs = [_ficha(0, i, 0.0, 0.0) for i in range(2)]
    fs[1].geo = None
    assert G._por_georreferencia([(fs[0], "right", fs[1])], [], {f.clave: f for f in fs}, None, G.Encajes()) == 1


def test_el_centro_de_la_celda_es_el_de_su_recuadro():
    # el promedio de los vértices del polígono de «16-25» quedaba ~360 ft corrido (más vértices de un lado)
    c = indice_mapas.cargar("phoenix_qs").celdas["16-25"]
    xs = [p[0] for p in c.poligono]
    ys = [p[1] for p in c.poligono]
    assert c.centro_caja() == ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


CARPETA = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "DOCS DE PRUEBA IND")
SD = [os.path.join(CARPETA, "QS SD_Indian School_%s.pdf" % n) for n in ("North", "South")]


@pytest.mark.skipif(not all(os.path.exists(p) for p in SD), reason="faltan los PDF QS SD de Phoenix")
def test_sd_north_y_south_son_una_sola_composicion():
    import fitz
    from hoja import composicion_ficha as cf
    fpd = [[cf.ficha(p, d) for p in fitz.open(ruta)] for d, ruta in enumerate(SD)]
    an = G.analizar(fpd)
    assert [len(g.nodos) for g in an.grupos] == [36] and an.descartadas == 0     # antes: 8 grupos, 32 descartadas
    reales = [c for c in an.grupos[0].costuras if c.metodo != "georef"]
    for c in reales:                       # la georreferencia predice cada unión del dibujo (sin usarla)
        p = CG.prediccion(an.fichas[c.a], an.fichas[c.b], CG.calibrar([x for x in reales if x is not c], an.fichas))
        assert math.dist(p[1], c.t) <= 1.5
