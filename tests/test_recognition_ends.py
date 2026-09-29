"""Dónde TERMINA cada línea (`recognition_ends`, pedido del usuario 2026-09-28).

1. `trim_inkless_tails`: una línea que llega a otra por un tramo final SIN tinta propia
   (más largo que el hueco del linetype y sin letra suya) no llega ahí: termina donde
   termina su tinta.
2. `extend_to_cut`: una línea cuya tinta muere en su letra (o en un hueco simple) justo
   antes del borde de la vista termina en el CORTE.
Casos sintéticos (px = pt) y la hoja que reportó el usuario (DU08 h.26).
"""
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import recognition as rec
import recognition_ends as ends
import recognition_geom as geom

# «—t—» de telecom en DU08: hueco con letra 9 pt, letra 7.2 pt → hueco simple 4.5 pt
PAT = SimpleNamespace(gap_max=9.0, letter=7.2, glyph_bridge=36.0)
BOX = [(0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)]      # recorte de la vista


# ───────────── colas sin tinta ─────────────
def _stub(tail_ink_to):
    """Ramal vertical x=50 de y=10 a un tee en y=40 sobre otra línea (horizontal
    y=40); su tinta llega hasta `tail_ink_to`."""
    stub = geom.Polyline([(50.0, 10.0), (50.0, 40.0)], ["end", "tee"])
    main = geom.Polyline([(0.0, 40.0), (100.0, 40.0)], ["end", "end"])
    ink = [((50.0, 10.0), (50.0, tail_ink_to)), ((0.0, 40.0), (100.0, 40.0))]
    return [stub, main], ink


FAR = [geom.Glyph(500.0, 500.0, 7.2)]                         # la capa tiene letras (lejos)


def test_cola_sin_tinta_se_recorta_donde_termina_la_tinta():
    pls, ink = _stub(30.0)                                     # 10 pt sin tinta hasta el tee
    out = ends.trim_inkless_tails(pls, ink, PAT, FAR, geom.Polyline)
    assert out[0].kinds[-1] == "end"
    assert out[0].pts[-1] == pytest.approx((50.0, 30.0), abs=0.1)
    assert out[1] is pls[1]                                    # la otra línea no se toca


def test_hueco_del_linetype_antes_del_tee_no_se_recorta():
    pls, ink = _stub(36.0)                                     # 4 pt: un hueco simple
    out = ends.trim_inkless_tails(pls, ink, PAT, FAR, geom.Polyline)
    assert out[0] is pls[0]


def test_capa_sin_letras_admite_el_hueco_entero():
    pls, ink = _stub(31.5)                                     # 8.5 pt ≤ gap_max: hueco de guiones
    assert ends.trim_inkless_tails(pls, ink, PAT, [], geom.Polyline)[0] is pls[0]


def test_letra_propia_en_la_cola_no_se_recorta():
    pls, ink = _stub(30.0)
    glyph = geom.Glyph(50.0, 34.0, 7.2)                        # su «t», sobre el ramal
    assert ends.trim_inkless_tails(pls, ink, PAT, [glyph], geom.Polyline)[0] is pls[0]


def test_letra_de_la_otra_linea_no_justifica_la_cola():
    """Caso DU08 h.26: en el hueco está la «t» de la línea a la que se «une»."""
    pls, ink = _stub(30.0)
    glyph = geom.Glyph(50.0, 40.5, 7.2)                        # centrada sobre la horizontal
    out = ends.trim_inkless_tails(pls, ink, PAT, [glyph], geom.Polyline)
    assert out[0].kinds[-1] == "end" and out[0].pts[-1][1] == pytest.approx(30.0, abs=0.1)


# ───────────── hasta el corte ─────────────
def _line_to_border(x_end):
    """Línea horizontal y=50 que termina en `x_end`, antes del borde x=200."""
    return [(100.0, 50.0), (x_end, 50.0)], ["end", "end"]


def _no_others():
    return []


def test_linea_que_muere_en_su_letra_termina_en_el_corte():
    pts, kinds = _line_to_border(188.0)
    glyphs = [(193.0, 50.2, 7.2)]                               # su letra entre la tinta y el borde
    P, K = ends.extend_to_cut(pts, kinds, [BOX], glyphs, PAT, _no_others)
    assert K == ["end", "cut"] and P[-1] == pytest.approx((200.0, 50.0))
    assert P[0] == pts[0] and K[0] == "end"                    # el otro extremo no está junto al borde


def test_hueco_largo_sin_letra_no_llega_al_corte():
    pts, kinds = _line_to_border(188.0)                        # 12 pt vacíos (hueco simple 4.5)
    P, K = ends.extend_to_cut(pts, kinds, [BOX], [(10.0, 10.0, 7.2)], PAT, _no_others)
    assert K[-1] == "end" and P[-1] == (188.0, 50.0)


def test_hueco_simple_llega_al_corte():
    pts, kinds = _line_to_border(196.0)                        # 4 pt: la letra quedó fuera
    P, K = ends.extend_to_cut(pts, kinds, [BOX], [(10.0, 10.0, 7.2)], PAT, _no_others)
    assert K[-1] == "cut"


def test_capa_sin_letras_usa_el_hueco_entero():
    """DU08 h.26 drenaje: guiones con huecos de 10 pt y ninguna letra en la capa."""
    pat = SimpleNamespace(gap_max=10.0, letter=5.0, glyph_bridge=40.0)
    pts, kinds = _line_to_border(191.0)                        # 9 pt vacíos
    assert ends.extend_to_cut(pts, kinds, [BOX], [], pat, _no_others)[1][-1] == "cut"
    assert ends.extend_to_cut(pts, kinds, [BOX], [(10.0, 10.0, 5.0)], pat, _no_others)[1][-1] == "end"


def test_letra_de_otra_linea_al_lado_no_cuenta():
    pts, kinds = _line_to_border(188.0)
    glyphs = [(193.0, 53.0, 7.2)]                              # 3 pt fuera de la prolongación
    assert ends.extend_to_cut(pts, kinds, [BOX], glyphs, PAT, _no_others)[1][-1] == "end"


def test_tinta_propia_hasta_el_borde_cubre_la_prolongacion():
    pts, kinds = _line_to_border(180.0)
    ink = ends.ink_index([((182.0, 50.1), (200.0, 50.1))])
    P, K = ends.extend_to_cut(pts, kinds, [BOX], [(10.0, 10.0, 7.2)], PAT, _no_others, ink=ink)
    assert K[-1] == "cut"


def test_otra_linea_de_la_capa_en_la_prolongacion_la_bloquea():
    pts, kinds = _line_to_border(188.0)
    glyphs = [(193.0, 50.2, 7.2)]
    other = lambda: [((196.0, 40.0), (196.0, 60.0))]           # cruza la prolongación
    assert ends.extend_to_cut(pts, kinds, [BOX], glyphs, PAT, other)[1][-1] == "end"


def test_escala_px_por_pt():
    """En el lienzo (zoom 3.5) las tolerancias se escalan igual."""
    Z = 3.5
    box = [(x * Z, y * Z) for x, y in BOX]
    pts, kinds = [(100.0 * Z, 50.0 * Z), (188.0 * Z, 50.0 * Z)], ["end", "end"]
    glyphs = [(193.0 * Z, 50.2 * Z, 7.2 * Z)]
    P, K = ends.extend_to_cut(pts, kinds, [box], glyphs, PAT, _no_others, scale=Z)
    assert K[-1] == "cut" and P[-1] == pytest.approx((200.0 * Z, 50.0 * Z))


# ───────────── hoja real ─────────────
DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"


def _seg_d(q, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h26_ramal_de_telecom_no_se_une_a_la_linea_de_abajo():
    """Reporte del usuario: el ramal curvo de telecom termina en el aire en
    (1305.7, 437.6) y se «unía» 9 pt más abajo a la otra línea, justo en el hueco de
    la «t» de ÉSA línea."""
    res = rec.recognize_page(DU08, 25, utility="TELECOM", zoom=1.0)
    for pl in res.drawable:
        P = pl.pts_pdf
        assert not any(_seg_d((1309.0, 440.5), a, b) < 0.5 for a, b in zip(P, P[1:]))   # el tramo sin tinta
    stub = [pl for pl in res.drawable if any(math.dist(q, (1305.7, 437.6)) < 1.0 for q in pl.pts_pdf)]
    assert stub
    k = [pl.kinds[i] for pl in stub for i, q in enumerate(pl.pts_pdf) if math.dist(q, (1305.7, 437.6)) < 1.0]
    assert k == ["end"]


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h26_lineas_que_mueren_en_su_letra_llegan_al_corte():
    """Reporte del usuario: junto al borde derecho de la vista (x≈1507.5) las líneas
    terminaban en su letra («E», «W», «SS»), como si empezaran después de ella."""
    for util, y in (("ELECTRICO", 491.6), ("AGUA", 467.9), ("AGUA", 731.9), ("ALCANTARILLADO", 691.7),
                    ("DRENAJE", 614.3)):
        res = rec.recognize_page(DU08, 25, utility=util, zoom=1.0)
        ends_ = [(pl.pts_pdf[i], pl.kinds[i]) for pl in res.drawable for i in (0, -1)
                 if abs(pl.pts_pdf[i][1] - y) < 1.0 and 1490.0 < pl.pts_pdf[i][0] < 1510.0]
        assert ends_, (util, y)
        assert all(k == "cut" and q[0] == pytest.approx(1507.3, abs=0.6) for q, k in ends_), (util, y, ends_)
