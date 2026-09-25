"""Perfil AGUA del reconocimiento (2026-09-24).

Reutiliza el núcleo de siempre (`recognition_geom`) con su propia clasificación de
capas y tres reglas de perfil (`GeomOptions`) que eléctrico y drenaje NO usan:
`join_touching_ends`, `gap_turn_blocks`, `markers_on_curves`. La foto de
Eléctrico/Drenaje de los 4 PDFs de prueba no cambió ni un vértice.
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

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU06 = DOCS / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"


@pytest.mark.parametrize("name, kind", [
    ("X|C-WATR-UNGD-E", "water_ungd"),
    ("X|C-WATR-UNGD-N", "water_ungd"),
    ("X|C-WATR-UNGD-A", "water_ungd"),
    ("X|C-WATR-UNGD-D", "water_ungd"),
    ("X|C-WATR-UNGD-E-SHORT", "water_ungd"),
    ("X|C-WATER-UNGD-E-SHORT", "water_ungd"),
    ("X|C-WATR_UGND-E-ADD", "water_ungd"),
    ("X|C-WATR-PIPE", "water_ungd"),
    ("X|C-WATER-PIPE-LTRL", "water_ungd"),
    ("X|C-WATR-UNGD-N-(BY OTHERS)", "water_ungd"),
    ("X|CU-WATR-UNGD-N", "water_ungd"),              # BOE nivel 2
    ("X|V-WATR-VALT", "structure"),
    ("X|V-WATR-MANH", "structure"),
    ("X|V-FIRE-STRU", "structure"),
    ("X|C-WATR-ANNO-TEXT-E", None),
    ("X|C-WATR-UNGD-CASE-E", None),                  # camisa
    ("X|C-WATR-FITT-N", None),
    ("X|C-WATER-FH", None),                          # hidrante (símbolo)
    ("X|C-WATR-GV-E", None),
    ("X|V-WATR-VALV", None),                         # válvula = accesorio, no estructura
    ("X|V-WATR-METR", None),
    ("X|V-FIRE-HYDR", None),
    ("X|C-HYDR-CTCH-FPTH", None),                    # hidrología, no agua
    ("X|C-ELEC-UNGD-E", None),
    ("X|C-STRM-UNGD-N", None),
])
def test_clasificacion_de_capas_de_agua(name, kind):
    assert rec.classify_ocg(name, "AGUA") == kind


def test_capas_de_agua_no_entran_en_otros_perfiles():
    for name in ("X|C-WATR-UNGD-E", "X|V-WATR-VALT", "X|C-WATR-PIPE"):
        assert rec.classify_ocg(name, "ELECTRICO") is None
        assert rec.classify_ocg(name, "DRENAJE") is None


def test_seleccion_por_defecto_todas_y_etiquetas():
    assert "AGUA" in rec.SUPPORTED_UTILITIES
    assert rec.normalize_utilities() == rec.SUPPORTED_UTILITIES      # todas marcadas al abrir
    assert rec.normalize_utilities(["agua"]) == ("AGUA",)
    assert rec.normalize_utilities(["AGUA", "ELECTRICO"]) == ("ELECTRICO", "AGUA")
    assert rec.utilities_label(("ELECTRICO", "DRENAJE")) == "Eléctrico y Drenaje"
    assert rec.utilities_label(("ELECTRICO", "DRENAJE", "AGUA")) == "Eléctrico, Drenaje y Agua"
    assert rec.utility_line_kind("AGUA") == "water_ungd"
    labels = [label for _, label in rec.recognition_choices()]
    assert labels[0].startswith("Eléctrico, Drenaje, Agua") and "Solo Agua" in labels


def test_reglas_de_agua_no_se_activan_en_otros_perfiles():
    agua = rec.UTILITY_GEOM_OPTIONS["AGUA"]
    assert agua.join_touching_ends and agua.gap_turn_blocks and agua.markers_on_curves
    for util in ("ELECTRICO", "DRENAJE"):
        o = rec.UTILITY_GEOM_OPTIONS.get(util, rec.geom.GeomOptions())
        assert not (o.join_touching_ends or o.gap_turn_blocks or o.markers_on_curves)


def _pls(pdf, page):
    res = rec.recognize_page(pdf, page - 1, utility="AGUA", zoom=2.0)
    return [([(q[0] / 2, q[1] / 2) for q in pl.pts_pdf], pl.kinds) for pl in res.drawable]


def _through(pls, p, tol=1.0):
    for pts, _ in pls:
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if L < 1e-6:
                continue
            t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (L * L)
            if 0 < t < 1 and math.dist(p, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) <= tol:
                return True
    return False


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h23_acometida_con_quiebre_sigue_su_tinta():
    """Bajada–diagonal–bajada de la bóveda a la principal (C-WATR-UNGD-N): antes
    cada pieza se estiraba sola a la bóveda o a una T (27 pt sin tinta)."""
    pls = _pls(DU10, 23)
    assert _through(pls, (1066.2, 652.0))            # la diagonal existe
    for pts, kinds in pls:                           # y está unida a sus dos bajadas
        for k, p in enumerate(pts):
            if math.dist(p, (1058.9, 659.2)) <= 1.0 or math.dist(p, (1073.4, 644.9)) <= 1.0:
                assert kinds[k] in ("corner", "bend"), (p, kinds[k])


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h10_escalon_no_se_atajea_en_diagonal():
    """Dos diagonales colineales con un escalón (vertical + horizontal) entre
    ellas: la línea sigue la tinta, no un atajo de 34 pt en blanco; la rama
    horizontal nace en T sobre la vertical."""
    pls = _pls(DU06, 10)
    assert not _through(pls, (969.6, 1323.9))
    assert any(math.dist(p, (957.4, 1311.8)) <= 1.0 and k == "tee" for pts, kinds in pls
               for p, k in zip(pts, kinds))


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h3_barra_en_el_quiebre_no_se_estira():
    """Barra «/» de la línea abandonada sobre un quiebre curvo: es marca, no un
    tramo que baje 17 pt hasta la línea vecina."""
    pls = _pls(DU06, 3)
    assert not _through(pls, (1071.3, 923.5))
