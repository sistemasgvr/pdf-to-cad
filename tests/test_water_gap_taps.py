"""UD-213: las tomas de medidores junto al hueco no son giros de la principal."""
import math
from pathlib import Path

import pytest

from reconocimiento import recognition as rec
from reconocimiento import recognition_geom as G


@pytest.mark.parametrize("angulo", [0, 37, 90, 181])
@pytest.mark.parametrize("curva", [False, True])
def test_tomas_perpendiculares_no_cortan_corrida(angulo, curva):
    c, s = math.cos(math.radians(angulo)), math.sin(math.radians(angulo))

    def p(x, y):
        return (x * c - y * s + 100, x * s + y * c + 100)

    principal = [G.Dash(p(0, 0), p(20, 0)), G.Dash(p(30, 0), p(50, 0))]
    tomas = [(p(20, 0), p(20, -30)), (p(30, -30), p(30, 0))]
    curvas = [list(t) for t in tomas] if curva else []
    guiones = principal if curva else principal + [G.Dash(*t) for t in tomas]
    pat = G.Pattern(20, None, 10, 5, 15, 20, 30, 15)
    runs = G.build_runs(G.group_collinear(guiones), pat, [], [], curvas,
                        gap_turn_blocks=True, perpendicular_gap_taps=True)
    assert any(all(d in r.dashes for d in principal) for r in runs)


def test_giro_hacia_hueco_sigue_bloqueando_atajo():
    """Escalón: la diagonal vuelve a su eje por un desvío real de dos tramos."""
    dashes = [G.Dash((0, 0), (20, 20)), G.Dash((40, 40), (60, 60)),
              G.Dash((20, 20), (20, 40)), G.Dash((20, 40), (40, 40))]
    pat = G.Pattern(20, None, 30, 5, 35, 40, 50, 35)
    runs = G.build_runs(G.group_collinear(dashes), pat, [], [],
                        gap_turn_blocks=True, perpendicular_gap_taps=True)
    assert not any(dashes[0] in r.dashes and dashes[1] in r.dashes for r in runs)


PDF = Path(__file__).resolve().parent.parent / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"


def test_regla_de_tomas_solo_en_agua():
    for utilidad in rec.SUPPORTED_UTILITIES:
        opts = rec.UTILITY_GEOM_OPTIONS.get(utilidad, G.GeomOptions())
        assert opts.perpendicular_gap_taps == (utilidad == "AGUA")


@pytest.mark.skipif(not PDF.is_file(), reason="PDF DU06 no disponible")
@pytest.mark.parametrize("zoom", [1.0, 3.5])
def test_ud213_principal_continua_con_tomas_en_t(zoom):
    res = rec.recognize_page(str(PDF), 14, utility="AGUA", zoom=zoom)
    tomas = [(704.2, 923.6), (1047.7, 924.9), (1052.8, 924.9), (1354.9, 926.1)]
    lineas = [([(x / zoom, y / zoom) for x, y in pl.pts_pdf], pl.kinds)
              for pl in res.drawable if pl.layer_ocg.endswith("C-WATR-UNGD-E")]
    # Una sola principal debe contener las cuatro T: antes estaba en cuatro piezas.
    assert any(all(any(math.dist(q, p) < 1 and k == "tee" for q, k in zip(pts, kinds))
                       for p in tomas) for pts, kinds in lineas)
    # Cada toma termina en su propia T; no pasa a otra toma haciendo una U.
    for p in tomas:
        assert any(len(pts) == 2 and kinds[-1] == "tee" and math.dist(pts[-1], p) < 1
                   for pts, kinds in lineas)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF DU06 no disponible")
def test_ud213_en_hoja_compuesta_conserva_las_tomas():
    import fitz
    from hoja import composite as C

    with fitz.open(PDF) as src:
        clip = [333 / 2592, 800 / 1728, 1600 / 2592, 1300 / 1728]
        piezas = [C.Piece(source=0, page=14, clip=clip, x=0, y=0),
                  C.Piece(source=0, page=15, clip=clip, x=1267, y=0)]
        with C.build_document(C.Composite(pieces=piezas, bridges=False), [src]) as doc:
            res = rec.recognize_page(str(PDF), 0, doc=doc, utility="AGUA", zoom=3.5)
    tomas = [(x - 333 + C.MARGIN_PT, y - 800 + C.MARGIN_PT)
             for x, y in [(704.2, 923.6), (1047.7, 924.9), (1052.8, 924.9), (1354.9, 926.1)]]
    assert any(all(any(math.dist((x / 3.5, y / 3.5), p) < 1 and k == "tee"
                       for (x, y), k in zip(pl.pts_pdf, pl.kinds)) for p in tomas)
               for pl in res.drawable)
