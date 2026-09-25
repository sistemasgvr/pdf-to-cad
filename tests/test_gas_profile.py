"""Perfil GAS del reconocimiento (2026-09-25).

Reutiliza el núcleo de siempre (`recognition_geom`) con su propia clasificación de
capas (`_classify_gas`) y UNA regla de perfil que los demás no usan:
`glyph_hooks` — la «G»/«g» del linetype «—G—» trae su gancho como path aparte y
pasaba por codo: la línea entraba en la letra y saltaba sin tinta a la vecina.
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
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"


@pytest.mark.parametrize("name, kind", [
    ("PS89616000-A1-UG-REF-EXIST_NGAS|C-NGAS-E", "gas_ungd"),     # capas de SOLO estado
    ("X|C-NGAS-A", "gas_ungd"),
    ("X|C-NGAS-D", "gas_ungd"),
    ("X|C-NGAS-UNGD-N", "gas_ungd"),
    ("X|C-NGAS-UGND-N", "gas_ungd"),
    ("X|C-NGAS-UGND-E", "gas_ungd"),
    ("X|C-NGAS-UGND-E-ADD", "gas_ungd"),
    ("X|C-NGAS-PIPE", "gas_ungd"),
    ("X|PROP-GAS-ALGN", "gas_ungd"),                                 # LABOE: alineamiento C3D
    ("X|CU-NGAS-UNGD-N", "gas_ungd"),                                # BOE nivel 2
    ("X|V-NGAS-VALT", "structure"),
    ("X|C-NGAS-STRC", "structure"),
    ("X|C-NGAS-ANNO-TEXT-E", None),
    ("X|C-NGAS-ANNO-TEXT-E-", None),
    ("X|V-NGAS-VALV", None),                                         # accesorios
    ("X|V-NGAS-METR", None),
    ("X|V-NGAS-RISR", None),
    ("X|C-NGAS-UNGD-CASE-E", None),
    ("X|C-ELEC-UNGD-E", None),
    ("X|C-WATR-UNGD-E", None),
])
def test_clasificacion_de_capas_de_gas(name, kind):
    assert rec.classify_ocg(name, "GAS") == kind


def test_capas_de_gas_no_entran_en_otros_perfiles():
    for name in ("X|C-NGAS-E", "X|C-NGAS-UNGD-N", "X|V-NGAS-VALT", "X|PROP-GAS-ALGN"):
        for util in rec.SUPPORTED_UTILITIES:
            if util != "GAS":
                assert rec.classify_ocg(name, util) is None, (name, util)


def test_gas_es_perfil_y_red_a_presion():
    from model import NETWORK_KIND
    assert "GAS" in rec.SUPPORTED_UTILITIES and "GAS" in rec.DEFAULT_UTILITIES
    assert rec.utility_line_kind("GAS") == "gas_ungd" and "gas_ungd" in rec.DRAW_KINDS
    assert rec.utility_label("GAS") == "Gas"
    assert NETWORK_KIND["GAS"] == "pressure"          # sin cajas automáticas, como el agua


def test_glyph_hooks_solo_en_gas():
    assert rec.UTILITY_GEOM_OPTIONS["GAS"].glyph_hooks
    for util in rec.SUPPORTED_UTILITIES:
        if util != "GAS":
            assert not rec.UTILITY_GEOM_OPTIONS.get(util, geom.GeomOptions()).glyph_hooks, util


# «g» real del DU10 h.7 (C-NGAS-D), relativa a su esquina: panza (14 pts) y gancho (7 pts).
_G_BOWL = [(4.1, -1.12), (3.38, -1.78), (2.72, -2.14), (1.7, -2.14), (0.98, -1.84), (0.32, -1.12),
           (-0.04, -0.1), (-0.04, 0.56), (0.32, 1.58), (0.98, 2.3), (1.64, 2.66), (2.72, 2.66),
           (3.38, 2.3), (4.1, 1.64)]
_G_HOOK = [(4.1, -2.14), (4.04, 3.32), (3.74, 4.34), (3.38, 4.7), (2.66, 5.06), (1.64, 5.06), (0.98, 4.7)]


class _Rect:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


def _poly(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return {"layer": "X|C-NGAS-E", "rect": _Rect(min(xs), min(ys), max(xs), max(ys)),
            "items": [("l", a, b) for a, b in zip(pts, pts[1:])], "closePath": False}


def _linea_con_g(n=6, period=60.0, dash=44.0, y=100.0):
    """Línea horizontal «—g—g—…» con la «g» real en cada hueco y, debajo, otra
    línea paralela a 30 pt (la vecina a la que saltaba el gancho)."""
    paths = []
    for k in range(n):
        x0 = 10.0 + k * period
        paths.append(_poly([(x0, y), (x0 + dash, y)]))
        gx = x0 + dash + (period - dash) / 2 - 2.05
        for shape in (_G_BOWL, _G_HOOK):
            paths.append(_poly([(gx + px, y + py) for px, py in shape]))
    paths.append(_poly([(10.0, y + 30.0), (10.0 + n * period, y + 30.0)]))
    return paths


def test_gancho_de_la_g_es_letra_y_la_linea_sigue_recta():
    paths = _linea_con_g()
    antes = geom.reconstruct(paths, (), geom.GeomOptions())
    ahora = geom.reconstruct(paths, (), geom.GeomOptions(glyph_hooks=True))
    # sin la regla, los ganchos pasan por codo y la línea se sale de su recta
    assert any(abs(p[1] - 100.0) > 1.0 and abs(p[1] - 130.0) > 1.0
               for pl in antes.polylines for p in pl.pts)
    # con la regla, todo vértice queda sobre una de las dos líneas
    assert all(abs(p[1] - 100.0) <= 0.5 or abs(p[1] - 130.0) <= 0.5
               for pl in ahora.polylines for p in pl.pts)
    assert ahora.n_curves == 0
    assert ahora.coverage >= 0.99


def test_gancho_aislado_no_se_toma_por_letra():
    """Un arco pequeño pegado a una letra UNA sola vez no se repite: sigue siendo
    codo (la regla exige ≥`GLYPH_STROKE_MIN_REPEAT` ganchos iguales)."""
    paths = _linea_con_g(n=1)
    _d, _g, curves = geom.classify_paths(paths, glyph_hooks=True)
    assert len(curves) == 1


def _pls(pdf, page):
    res = rec.recognize_page(pdf, page - 1, utility="GAS", zoom=2.0)
    return [[(q[0] / 2, q[1] / 2) for q in pl.pts_pdf] for pl in res.drawable]


def _through(pls, p, tol=1.0):
    for pts in pls:
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if L < 1e-6:
                continue
            t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (L * L)
            if 0 < t < 1 and math.dist(p, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) <= tol:
                return True
    return False


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h7_la_g_no_baja_a_la_linea_vecina():
    """C-NGAS-D con «g»: la línea entraba al gancho (410, 831) y bajaba 29 pt en
    blanco por x=401 hasta la paralela de abajo."""
    pls = _pls(DU10, 7)
    assert not _through(pls, (401.0, 843.0))
    assert _through(pls, (420.0, 826.0))              # la línea sigue por su tinta


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h3_la_g_no_hace_rodeos():
    """C-NGAS-E vertical con «G» cada ~68 pt: sin la regla la línea daba un rodeo
    de ~24 pt por el gancho de cada letra."""
    pls = _pls(DU06, 3)
    assert not _through(pls, (951.0, 1317.0))         # diagonal inventada desde el gancho
    assert _through(pls, (947.7, 1290.0))             # la vertical sigue por su tinta


DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h21_doble_barra_en_tramos_cortos_es_abandonada():
    """C-NGAS-D vertical (x≈1253, 230 pt) con «//» propio: junto a la T el CAD la
    parte en tramos de 26–34 pt y el «//» sale más seguido que el periodo (69 pt).
    Lo reportó el usuario: debe importarse AB."""
    res = rec.recognize_page(DU08, 20, utility="GAS", zoom=1.0)
    line = [p for p in res.drawable if p.layer_ocg.endswith("C-NGAS-D")
            and all(1245 <= q[0] <= 1260 for q in p.pts_pdf)
            and max(q[1] for q in p.pts_pdf) - min(q[1] for q in p.pts_pdf) > 200]
    assert line and all(p.abandoned for p in line)


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h22_linea_repetida_por_tres_xrefs_se_importa_una_vez():
    """`REF-EXIST_NGAS|C-NGAS-UGND-E`, `REF-EXIST_SSWR|C-NGAS-UGND-E-ADD` y
    `SERVICE_MAPS_CALLOUT|C-NGAS-UGND-E-ADD` traen la MISMA línea (y=1130): antes
    salían tres tuberías superpuestas. Se conserva la del xref de gas."""
    res = rec.recognize_page(DU08, 21, utility="GAS", zoom=1.0)
    same = [p for p in res.drawable if all(abs(q[1] - 1130.1) <= 1.0 for q in p.pts_pdf)]
    assert len(same) == 1
    assert same[0].layer_ocg == "PS89616000-B3-UG-REF-EXIST_NGAS|C-NGAS-UGND-E"


def test_add_suffix_solo_une_la_misma_capa():
    by = {"A|C-NGAS-UGND-E": [{"items": [("l", (0, 0), (50, 0))]}],
          "B|C-NGAS-UGND-E-ADD": [{"items": [("l", (0, 0), (50, 0))]}],
          "C|C-NGAS-UGND-D-ADD": [{"items": [("l", (0, 0), (50, 0))]}]}
    dup = rec.duplicate_ocgs(by, ignore_add_suffix=True)
    assert set(dup) == {"B|C-NGAS-UGND-E-ADD"}           # «-D» es otro estado: no se funde
    assert rec.duplicate_ocgs(by) == {}                   # drenaje: nombre exacto, como siempre
