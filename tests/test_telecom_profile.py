"""Perfil TELECOM del reconocimiento (2026-09-25).

Reutiliza el núcleo de siempre (`recognition_geom`) con su propia clasificación de
capas (`_classify_telecom`) y UNA regla de perfil que los demás no usan:
`stroke_letters` — las letras del linetype de telecom son trazos sueltos: la «t» de
«—t—» (asta con gancho + travesaño) y la «TE»/«SE» del banco de ductos de Metro
(«—SC—», trazos rectos). Sin la regla pasaban por codo/guión y la línea saltaba
sin tinta de una letra a otra (110 tramos sin tinta en los 4 PDFs → 0).
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import recognition as rec  # noqa: E402
import recognition_geom as geom  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU06 = DOCS / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"


@pytest.mark.parametrize("name, kind", [
    ("PS89616000-B3-UT-REF-EXIST_TELECOM|C-TELE-UNGD-E", "tele_ungd"),
    ("X|C-TELE-UNGD-A", "tele_ungd"),
    ("X|C-TELE-UNGD-D", "tele_ungd"),
    ("X|C-TELE-UNGD-N", "tele_ungd"),
    ("X|C-TELE-UNGD-N-", "tele_ungd"),
    ("X|C-COMM-UGND-E", "tele_ungd"),
    ("X|C-FIBR-PIPE", "tele_ungd"),
    ("X|CU-TELE-UNGD-N", "tele_ungd"),                      # BOE nivel 2
    ("X|T-PROP-COMM", "tele_ungd"),                         # alineamiento propuesto (C3D)
    ("X|T-PROP-COMM_ATT", "tele_ungd"),
    ("X|N-COMM-DUCT-BANK-PL", "tele_ungd"),                 # banco de ductos de Metro «—SC—»
    ("X|N-COMM-DUCT-BANK-PL-SC", "tele_ungd"),
    ("X|N-COMM-DUCT-BANK-PL-SE", "tele_ungd"),
    ("X|C-TELE-VALT-E", "structure"),
    ("X|C-TELE-VALT-N", "structure"),
    ("X|V-COMM-MANH", "structure"),
    ("X|V-COMM-VALT", "structure"),
    ("X|V-COMM-PBOX", "structure"),                         # caja de paso: estructura, no se importa sola
    ("X|N-Comm-Junction Box-SC", "structure"),
    ("X|C-TELE-OVHD-E", None),                              # aérea: poste a poste, no conducto
    ("X|C-TELE-ANNO-TEXT-E", None),
    ("X|V-CATV-PBOX-TEXL", None),
    ("X|V-COMM-CABT", None),                                # gabinete / riser = accesorios
    ("X|V-COMM-RISR", None),
    ("X|C-ELEC-UNGD-E", None),
])
def test_clasificacion_de_capas_de_telecom(name, kind):
    assert rec.classify_ocg(name, "TELECOM") == kind


def test_capas_de_telecom_no_entran_en_otros_perfiles():
    for name in ("X|C-TELE-UNGD-E", "X|T-PROP-COMM", "X|N-COMM-DUCT-BANK-PL", "X|V-COMM-MANH"):
        for util in rec.SUPPORTED_UTILITIES:
            if util != "TELECOM":
                assert rec.classify_ocg(name, util) is None, (name, util)


def test_telecom_es_perfil_y_red_de_conductos():
    from model import NETWORK_KIND
    assert "TELECOM" in rec.SUPPORTED_UTILITIES and "TELECOM" in rec.DEFAULT_UTILITIES
    assert rec.utility_line_kind("TELECOM") == "tele_ungd" and "tele_ungd" in rec.DRAW_KINDS
    assert NETWORK_KIND["TELECOM"] == "conduit"             # CAJA solo en bóvedas reales
    # cajas de paso / junction boxes sin línea no se importan como caja suelta
    assert not rec.is_vault_ocg("X|V-COMM-PBOX") and not rec.is_vault_ocg("X|N-Comm-Junction Box")
    assert rec.is_vault_ocg("X|V-COMM-MANH") and rec.is_vault_ocg("X|C-TELE-VALT-E")


def test_stroke_letters_solo_en_telecom():
    assert rec.UTILITY_GEOM_OPTIONS["TELECOM"].stroke_letters
    for util in rec.SUPPORTED_UTILITIES:
        if util != "TELECOM":
            assert not rec.UTILITY_GEOM_OPTIONS.get(util, geom.GeomOptions()).stroke_letters, util


class _Rect:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


def _poly(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return {"layer": "X|C-TELE-UNGD-E", "rect": _Rect(min(xs), min(ys), max(xs), max(ys)),
            "items": [("l", a, b) for a, b in zip(pts, pts[1:])], "closePath": False}


# «t» real del DU10 h.5 (línea vertical en x=1017.1), relativa al extremo del guión:
# asta perpendicular con gancho (4 trazos) + travesaño de 2.4 pt a lo largo de la línea.
_T_STEM = [(-4.5, 4.3), (1.3, 4.3), (2.3, 4.0), (2.7, 3.3), (2.7, 2.6)]
_T_BAR = [(-2.1, 5.3), (-2.1, 2.9)]


def _linea_con_t(n=6, period=36.0, dash=21.6, x=100.0):
    """Línea vertical «—t—…» con la «t» real en cada hueco y otra paralela a 15 pt."""
    paths = []
    for k in range(n):
        y0 = 10.0 + k * period
        paths.append(_poly([(x, y0), (x, y0 + dash)]))
        ty = y0 + dash
        for shape in (_T_STEM, _T_BAR):
            paths.append(_poly([(x + px, ty + py) for px, py in shape]))
    paths.append(_poly([(x + 15.0, 10.0), (x + 15.0, 10.0 + n * period)]))
    return paths


def test_la_t_es_letra_y_la_linea_sigue_recta():
    paths = _linea_con_t()
    antes = geom.reconstruct(paths, (), geom.GeomOptions())
    ahora = geom.reconstruct(paths, (), geom.GeomOptions(stroke_letters=True))
    assert any(abs(p[0] - 100.0) > 1.0 and abs(p[0] - 115.0) > 1.0
               for pl in antes.polylines for p in pl.pts)          # sin la regla: se sale de su recta
    assert all(abs(p[0] - 100.0) <= 0.5 or abs(p[0] - 115.0) <= 0.5
               for pl in ahora.polylines for p in pl.pts)
    assert ahora.n_curves == 0 and ahora.coverage >= 0.99


def test_una_t_aislada_no_basta():
    """Asta con gancho + travesaño UNA sola vez: no se repite → no es letra."""
    _d, _g, curves = geom.classify_paths(_linea_con_t(n=1), stroke_letters=True)
    assert len(curves) == 1


def _pls(pdf, page):
    res = rec.recognize_page(pdf, page - 1, utility="TELECOM", zoom=1.0)
    return res, [([tuple(q) for q in pl.pts_pdf], pl.kinds, pl.abandoned) for pl in res.drawable]


def _through(pls, p, tol=1.0):
    for pts, _k, _ab in pls:
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if L < 1e-6:
                continue
            t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (L * L)
            if 0 < t < 1 and math.dist(p, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) <= tol:
                return True
    return False


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h5_la_t_no_arma_lineas_paralelas():
    """Dos conductos verticales con «t» que llegan al manhole: antes cada «t»
    armaba una paralela a 2.4 pt (x=1015.0 / 1000.6) y diagonales sin tinta."""
    _res, pls = _pls(DU10, 5)
    assert not _through(pls, (1015.0, 680.0), tol=0.5)
    assert not _through(pls, (1000.6, 680.0), tol=0.5)
    assert _through(pls, (1017.1, 656.0)) and _through(pls, (1002.7, 656.0))


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h11_el_asta_de_la_te_no_baja_a_la_paralela():
    """«—TE—» del banco de ductos de Metro: el asta de la «T» (7.2 pt, solo toca el
    travesaño) se prolongaba 42 pt hasta la línea de abajo."""
    _res, pls = _pls(DU06, 11)
    assert not _through(pls, (944.6, 1230.0))
    assert not _through(pls, (963.5, 1230.0))


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h38_el_brazo_de_la_e_no_inventa_una_paralela():
    """«—SE—» con solo dos «E» en el tramo: el brazo de cada «E» (3.9 pt al lado
    del eje) se unía con el de la otra → paralela de 81 pt sin tinta."""
    _res, pls = _pls(DU08, 38)
    assert not _through(pls, (1390.5, 1420.0))


LABOE = DOCS / "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf"


@pytest.mark.skipif(not LABOE.is_file(), reason="PDF LABOE no disponible")
def test_laboe_h26_curva_a_guiones_cortos_con_doble_barra_sigue_abandonada():
    """Curva «-D» de guiones cortos (11.5 pt) con «//»: sus guiones no son astas de
    letra (con esa confusión perdía el tramo del «//» y dejaba de ser AB)."""
    _res, pls = _pls(LABOE, 26)
    curve = [(pts, ab) for pts, _k, ab in pls if any(math.dist(q, (162.0, 1409.9)) <= 1.5 for q in pts)]
    assert curve and all(ab for _pts, ab in curve)
