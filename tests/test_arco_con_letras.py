"""Curva con el RÓTULO dentro (reporte del usuario 2026-10-19, DU06 UD-201 en la hoja
compuesta): la «—SC—» de `G-XREF` gira 90° con un arco de r = 18 pt hacia una caja de
empalme y la «SC» va DENTRO del arco. El guión de después no se le asignaba a telecom (sus
puntas curvas miden <1 pt: ni esquina ni hueco para el reparto por letras) y la curva no
se veía (la tinta curva es ~30 % del arco: el resto son las letras). En la misma caja, la
«—SC—» del banco de ductos sale hacia la derecha y quedaba cortada en sus letras: su punta
de afuera se tomaba por la llegada a la caja."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from reconocimiento import recognition_arc_letters as AL  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
needs_du06 = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")

R0 = 18.0
CTR = (40.0, 18.0)


def _arc(deg):
    return (CTR[0] + R0 * math.cos(math.radians(deg)), CTR[1] + R0 * math.sin(math.radians(deg)))


def _box(deg, size=7.0):
    c = _arc(deg)
    return (c[0] - size / 2, c[1] - size / 2, c[0] + size / 2, c[1] + size / 2)


# guión horizontal que llega al arco con dos cuerdas del aplanado (como AutoCAD) y guión
# vertical que sale de él con otras dos; el rótulo va en medio, sobre el arco
LLEGA = [(0.0, 0.0), (40.0, 0.0), _arc(-83.6), _arc(-77.2)]
SALE = [(58.0, 58.0), (58.0, 18.0), _arc(-6.4), _arc(-12.8)]
LETRAS = [_box(-60.0), _box(-35.0)]


def test_puntas_curvas_de_los_guiones():
    tips = AL.arc_tips([LLEGA, SALE])
    assert len(tips) == 2
    a, b = sorted(tips, key=lambda t: t.chain)
    assert a.J == (40.0, 0.0) and a.d == (1.0, 0.0) and a.sign == 1
    assert b.J == (58.0, 18.0) and b.d == (0.0, -1.0) and b.sign == -1
    # un guión recto (sin cuerdas curvas en la punta) no es punta curva
    assert AL.arc_tips([[(0.0, 0.0), (40.0, 0.0)]]) == []


def test_el_reparto_une_las_dos_puntas_y_las_letras_del_arco():
    got = AL.letter_gaps([LLEGA, SALE], set(), LETRAS)
    assert len(got) == 1
    (ca, cb), letras = got[0]
    assert {ca, cb} == {0, 1} and sorted(letras) == [0, 1]


def test_sin_letras_sobre_el_arco_no_se_une():
    assert AL.letter_gaps([LLEGA, SALE], set(), []) == []
    # letras lejos del arco (otra línea, un rótulo) no cuentan
    lejos = [(b[0] + 20, b[1] - 20, b[2] + 20, b[3] - 20) for b in LETRAS]
    assert AL.letter_gaps([LLEGA, SALE], set(), lejos) == []
    # una sola letra pegada a una punta: el resto del arco sin tinta ni letra
    assert AL.letter_gaps([LLEGA, SALE], set(), [_box(-70.0, 4.0)]) == []


def test_puntas_que_no_son_del_mismo_arco_no_se_unen():
    # la de salida corrida 6 pt: las dos rectas ya no llegan con el mismo largo a la esquina
    sale = [(q[0] + 6.0, q[1]) for q in SALE]
    assert AL.letter_gaps([LLEGA, sale], set(), LETRAS) == []


def test_el_codo_en_la_polilinea():
    # lo que dejaba el núcleo: esquina corrida y la punta curva como vértice suelto
    pts = [(0.0, 0.0), (55.6, 0.5), (58.0, 18.0), (58.0, 58.0)]
    kinds = ["end", "corner", "curve", "stop"]
    p2, k2, f2 = AL.letter_arcs(pts, kinds, {}, [LLEGA, SALE], LETRAS)
    assert k2 == ["end", "fillet", "stop"]
    assert p2[1] == pytest.approx((58.0, 0.0), abs=1e-6)
    f = f2[1]
    assert f["r_px"] == pytest.approx(R0, abs=0.01) and f["letters"] and not f["loose"]
    assert f["a"] == pytest.approx((40.0, 0.0), abs=0.01) and f["b"] == pytest.approx((58.0, 18.0), abs=0.01)
    # sin letras, la polilínea no cambia
    assert AL.letter_arcs(pts, kinds, {}, [LLEGA, SALE], []) == (pts, kinds, {})


def test_no_quita_un_nodo_de_la_red():
    pts = [(0.0, 0.0), (55.6, 0.5), (58.0, 18.0), (58.0, 58.0)]
    kinds = ["end", "tee", "curve", "stop"]
    assert AL.letter_arcs(pts, kinds, {}, [LLEGA, SALE], LETRAS)[1] == kinds


# ─────────────────────────────── DU06 h.3 (UD-201) ───────────────────────────────
def _dist_to(pts, q):
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        best = min(best, math.hypot(q[0] - a[0] - t * vx, q[1] - a[1] - t * vy))
    return best


@pytest.fixture(scope="module")
def du06_h3_telecom():
    import fitz
    from reconocimiento import recognition as rec
    with fitz.open(str(DU06)) as doc:
        return rec.recognize_page(None, 2, utility="TELECOM", zoom=1.0, doc=doc)


@needs_du06
def test_du06_h3_la_sc_de_g_xref_llega_a_la_caja_con_su_arco(du06_h3_telecom):
    pls = [p for p in du06_h3_telecom.drawable if p.layer_ocg.endswith("G-XREF")
           and _dist_to(p.pts_pdf, (1350.0, 981.12)) <= 0.3]
    assert len(pls) == 1
    pl = pls[0]
    codos = [f for f in pl.fillets.values() if f.get("letters")]
    assert len(codos) == 1
    f = codos[0]
    # el arco del PDF: tangente a y = 981.12 y a x = 1391.76, r = 18 pt (tinta de las puntas
    # sobre él a ≤0.05 pt), con la «SC» encima
    assert f["r_px"] == pytest.approx(18.0, abs=0.1)
    assert f["a"] == pytest.approx((1373.76, 981.12), abs=0.15)
    assert f["b"] == pytest.approx((1391.76, 999.12), abs=0.15)
    # …y baja por su recta hasta el borde de la caja de empalme (1378–1405 × 1027.6–1045.6)
    assert pl.kinds[-1] == "stop" or pl.kinds[0] == "stop"
    fin = pl.pts_pdf[-1] if pl.kinds[-1] == "stop" else pl.pts_pdf[0]
    assert fin == pytest.approx((1391.76, 1027.56), abs=1.2)


@needs_du06
def test_du06_h3_el_banco_de_ductos_sale_de_la_caja_por_sus_letras(du06_h3_telecom):
    pls = [p for p in du06_h3_telecom.drawable if p.layer_ocg.endswith("N-COMM-DUCT-BANK-PL")
           and _dist_to(p.pts_pdf, (1416.0, 1036.6)) <= 0.5]
    assert len(pls) == 1, "la línea sigue por su «SC» junto a la caja"
    pl = pls[0]
    ends = [(pl.pts_pdf[0], pl.kinds[0]), (pl.pts_pdf[-1], pl.kinds[-1])]
    # nace en el borde de la caja (no en su centro) y sigue más allá de la curva
    assert any(k == "stop" and q == pytest.approx((1405.26, 1036.56), abs=1.2) for q, k in ends)
    assert _dist_to(pl.pts_pdf, (1474.74, 1051.02)) <= 0.5
    # la curva después de las letras: UNA, tangente a la recta que sale de la caja
    near = [f for f in pl.fillets.values() if math.dist(f["center"], (1424.5, 1091.7)) < 5.0]
    assert len(near) == 1 and near[0]["r_px"] == pytest.approx(55.0, abs=1.5)
    assert abs(near[0]["center"][1] - near[0]["r_px"] - 1036.56) <= 0.3


@needs_du06
def test_du06_h3_reparto_por_letras_el_trazo_que_baja_es_telecom():
    import fitz
    from reconocimiento import recognition as rec
    from reconocimiento import recognition_letter_lines as lines
    with fitz.open(str(DU06)) as doc:
        page = doc[2]
        uses = rec.letter_uses(rec.page_letters(page))
        use = next(u for k, u in uses.items() if k.endswith("G-XREF"))
        draws = [p for p in page.get_drawings() if (p.get("layer") or "") == "G-XREF"
                 and 1380.0 <= p["rect"].x0 and p["rect"].x1 <= 1393.0 and 980.0 <= p["rect"].y0
                 and p["rect"].y1 <= 1037.0]
    # el guión que baja a la caja y las dos letras del arco
    assert len(draws) == 3
    assert all(use.paths.get(lines.path_key(p)) == "TELECOM" for p in draws)
