"""Perfil ALCANTARILLADO del reconocimiento (2026-09-25).

Mismo núcleo (`recognition_geom`) que eléctrico, drenaje y agua; el perfil solo
aporta su clasificación de capas (`_classify_sewer`) y sus `GeomOptions`. Red
por GRAVEDAD (`model.NETWORK_KIND`): los buzones reconocidos entran como
estructuras, igual que en drenaje.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import recognition as rec  # noqa: E402
from model import NETWORK_KIND  # noqa: E402


@pytest.mark.parametrize("name, kind", [
    ("X|C-SSWR-UNGD-E", "sewer_ungd"),
    ("X|C-SSWR-UNGD-N", "sewer_ungd"),
    ("X|C-SSWR-UNGD-A", "sewer_ungd"),
    ("X|C-SSWR-UNGD-D", "sewer_ungd"),
    ("X|C-SSWR-UNGD-E-ADD", "sewer_ungd"),
    ("X|C-SSWR-UGND-N", "sewer_ungd"),               # DU08 h.36–38, «—SS—» propuesta
    ("X|C-SSWR-PIPE", "sewer_ungd"),                 # estándar BOE
    ("X|CU-SSWR-UNGD-N", "sewer_ungd"),              # BOE nivel 2
    ("X|V-SSWR-MANH", "structure"),
    ("X|C-SSWR-STRC", "structure"),
    ("X|C-SSWR-UNGD-STRC-N", "structure"),           # LABOE: buzones propuestos
    ("X|C-SSWR-UNGD-STRC-N-301A", "structure"),
    ("X|V-SSWR-COUT", None),                         # cleanout = accesorio
    ("X|C-SSWR-UNDG-SCRN-N", None),                  # símbolo tramado del buzón, no línea
    ("X|C-SSWR-UNGD-WALL-E", None),                  # muros del conducto
    ("X|C-SSWR-UGND-CASE-N", None),                  # camisa
    ("X|C-SSWR-CASE-PATT", None),
    ("X|C-SSWR-ANNO-TEXT-E", None),
    ("X|C-SSWR-PROF-EXISTING", None),                # vista de perfil
    ("X|G-ANNO-TEXT-PROP-SEWER", None),
    ("X|C-STRM-UNGD-N", None),                       # drenaje pluvial ≠ sanitario
    ("X|C-WATR-UNGD-E", None),
    ("X|C-ELEC-UNGD-E", None),
])
def test_clasificacion_de_capas_de_alcantarillado(name, kind):
    assert rec.classify_ocg(name, "ALCANTARILLADO") == kind


def test_capas_de_alcantarillado_no_entran_en_otros_perfiles():
    for name in ("X|C-SSWR-UNGD-E", "X|V-SSWR-MANH", "X|C-SSWR-UGND-N", "X|C-SSWR-UNGD-STRC-N"):
        for util in ("ELECTRICO", "DRENAJE", "AGUA"):
            assert rec.classify_ocg(name, util) is None, (name, util)


def test_registro_del_perfil():
    assert "ALCANTARILLADO" in rec.SUPPORTED_UTILITIES
    assert rec.DEFAULT_UTILITIES == rec.SUPPORTED_UTILITIES          # todas marcadas al abrir
    assert rec.utility_line_kind("ALCANTARILLADO") == "sewer_ungd"
    assert "sewer_ungd" in rec.DRAW_KINDS
    assert rec.utility_label("ALCANTARILLADO") == "Alcantarillado"
    assert rec.normalize_utilities(["alcantarillado", "agua"]) == ("AGUA", "ALCANTARILLADO")
    assert NETWORK_KIND["ALCANTARILLADO"] == "gravity"
    labels = [label for _, label in rec.recognition_choices()]
    assert labels[0] == "Eléctrico, Drenaje, Agua, Alcantarillado y Gas" and "Solo Alcantarillado" in labels


def test_reglas_de_otros_perfiles_no_cambian():
    """Agregar alcantarillado no toca las GeomOptions de los perfiles existentes."""
    import recognition_geom as geom
    assert rec.UTILITY_GEOM_OPTIONS.get("ELECTRICO", geom.GeomOptions()) == geom.GeomOptions()
    assert rec.UTILITY_GEOM_OPTIONS["DRENAJE"] == geom.GeomOptions(
        separate_vaults=True, nearest_vault=True, absorb_inside_runs=True)
    assert rec.UTILITY_GEOM_OPTIONS["AGUA"] == geom.GeomOptions(
        join_touching_ends=True, gap_turn_blocks=True, markers_on_curves=True)


# ───────────── precisión: reglas propias del perfil (2026-09-25) ─────────────
import math  # noqa: E402

def test_anillo_de_buzon_y_tuberia_en_contorno():
    ring = {"layer": "C-SSWR-UNGD-E", "items": [
        ("l", (100 + 9 * math.cos(math.radians(a)), 100 + 9 * math.sin(math.radians(a))),
              (100 + 9 * math.cos(math.radians(a + 10)), 100 + 9 * math.sin(math.radians(a + 10))))
        for a in range(0, 330, 10)]}
    arc = {"layer": "C-SSWR-UNGD-E", "items": [
        ("l", (100 + 30 * math.cos(math.radians(a)), 100 + 30 * math.sin(math.radians(a))),
              (100 + 30 * math.cos(math.radians(a + 10)), 100 + 30 * math.sin(math.radians(a + 10))))
        for a in range(0, 90, 10)]}                                     # un codo (90°): NO es anillo
    rings, rest = rec.ring_symbol_paths([ring, arc])
    assert rings == [ring] and rest == [arc]
    box = {"layer": "C-SSWR-UNGD-N", "items": [("qu", _Q(1402.26, 1049.46, 1405.86, 1259.28))]}
    square = {"layer": "C-SSWR-UNGD-N", "items": [("qu", _Q(0, 0, 20, 20))]}   # no es delgado
    out, n = rec.outline_axis_paths([box, square])
    assert n == 1 and out[1] is square
    (_, p, q), = out[0]["items"]
    assert abs(p.x - 1404.06) < 1e-6 and abs(q.x - 1404.06) < 1e-6 and abs(abs(p.y - q.y) - 209.82) < 1e-3


class _Q:
    """fitz.Quad mínimo (esquinas ul, ur, lr, ll)."""
    def __init__(self, x0, y0, x1, y1):
        import fitz
        self.ul, self.ur, self.lr, self.ll = (fitz.Point(x0, y0), fitz.Point(x1, y0),
                                              fitz.Point(x1, y1), fitz.Point(x0, y1))


DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU06 = DOCS / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"


def _sewer(pdf, hoja):
    r = rec.recognize_page(pdf, hoja - 1, utility="ALCANTARILLADO")
    return r, [([tuple(q) for q in p.pts_pdf], p.kinds, p.layer_ocg.split("|")[-1]) for p in r.drawable]


def _near(pls, x, y, tol):
    return [(pts, k, lay) for pts, k, lay in pls if any(math.dist(q, (x, y)) <= tol for q in pts)]


def _lateral_feet(pls):
    return [[q for pts, k, lay in pls for q in pts if math.dist(q, (x, y)) <= 3.0]
            for x, y in ((632.64, 954.3), (272.64, 952.92))]


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h13_laterales_verticales_sobre_su_tinta(monkeypatch):
    """Reportado por el usuario: los laterales llegaban inclinados a la principal
    (el nodo quedaba en el CENTRO del hueco del linetype, 2 pt al costado)."""
    _, pls = _sewer(DU06, 13)
    for (x, _y), feet in zip(((632.64, 0), (272.64, 0)), _lateral_feet(pls)):
        assert feet and all(abs(q[0] - x) <= 0.3 for q in feet), feet
    # sin `precise_junctions` vuelve el defecto: la prueba sí lo detecta
    import dataclasses
    monkeypatch.setitem(rec.UTILITY_GEOM_OPTIONS, "ALCANTARILLADO", dataclasses.replace(
        rec.UTILITY_GEOM_OPTIONS["ALCANTARILLADO"], precise_junctions=False))
    _, pls = _sewer(DU06, 13)
    assert any(abs(q[0] - x) > 1.0 for (x, _y), feet in zip(((632.64, 0), (272.64, 0)), _lateral_feet(pls))
               for q in feet)


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h4_tuberia_en_contorno_es_su_eje_y_sin_anillos():
    r, pls = _sewer(DU06, 4)
    n = [(pts, k) for pts, k, lay in pls if lay == "C-SSWR-UNGD-N"]
    assert len(n) == 1 and len(n[0][0]) == 2
    (a, b), = [n[0][0]]
    assert abs(a[0] - 1404.06) < 0.1 and abs(b[0] - 1404.06) < 0.1 and abs(abs(a[1] - b[1]) - 209.8) < 0.5
    assert all(sum(1 for kk in k if kk == "curve") < 6 for pts, k, lay in pls)       # ningún anillo


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h36_una_sola_linea_llega_al_buzon():
    """Un guión corto del medio de la curva se prolongaba ENCIMA del siguiente
    hasta el buzón: dos tramos casi superpuestos."""
    _, pls = _sewer(DU08, 36)
    arrivals = [pts for pts, k, lay in _near(pls, 1310.0, 964.0, 3.0) if lay == "C-SSWR-UNGD-D"]
    assert len(arrivals) == 1


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h5_x_vecina_no_entra_al_buzon():
    """La diagonal de una «X» a la derecha del buzón no se desvía a él."""
    r, pls = _sewer(DU10, 5)
    for pts, k, lay in pls:
        for q, kk in zip(pts, k):
            if kk in ("edge", "vault"):
                assert not (math.dist(q, (969.5, 710.1)) < 1.0 and any(
                    math.dist(p, (972.2, 700.8)) < 1.0 for p in pts)), pts


# ───────────── continuidad (2026-09-25, hoja compuesta DU06 13+14) ─────────────
def _main_through(pls, x, y, tol=0.3):
    """Polilíneas que PASAN por (x, y) como vértice interior (la línea no se corta ahí)."""
    return [pts for pts, k, lay in pls
            if any(math.dist(q, (x, y)) <= tol for q in pts[1:-1])]


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_hoja_compuesta_13_14_la_principal_no_se_corta_en_el_lateral(tmp_path):
    """Reportado por el usuario: en la hoja compuesta DU06 13+14 la principal se
    cortaba en el hueco del linetype junto al lateral de x=632.6 (el lateral
    TOCA la punta del guión y `join_touching_ends` los cosía como esquina)."""
    import fitz
    import composite as C
    src = fitz.open(DU06)
    W, H = src[12].rect.width, src[12].rect.height
    a = C.Piece(source=0, page=12, clip=[0, 0, 1610 / W, 1])
    b = C.Piece(source=0, page=13, clip=[349.5 / W, 0, 1, 1], x=1610, y=-6)
    comp = C.Composite(pieces=[a, b])
    doc = C.build_document(comp, [src], bridges=C.compute_bridges(comp, [src]))
    out = tmp_path / "c.pdf"
    doc.save(out)
    doc.close()
    _, _, dx, dy = C.sheet_geometry(comp, lambda p: (W, H))
    X, Y = C.piece_map(a, (W, H), 20 / 72)(632.64, 954.3)
    r = rec.recognize_page(str(out), 0, utility="ALCANTARILLADO", scale_ft_per_pt=20 / 72)
    pls = [([tuple(q) for q in p.pts_pdf], p.kinds, "") for p in r.drawable]
    assert _main_through(pls, X + dx, Y + dy)
    assert not any(k[0] == "end" and math.dist(pts[0], (X + dx - 3.6, Y + dy)) < 1.0
                   or k[-1] == "end" and math.dist(pts[-1], (X + dx - 3.6, Y + dy)) < 1.0
                   for pts, k, _ in pls)


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h40_lateral_junto_al_buzon_es_una_t_y_la_principal_llega_al_buzon():
    _, pls = _sewer(DU08, 40)
    assert _main_through(pls, 984.6, 968.3)                          # la principal sigue al buzón
    lat = [pts for pts, k, lay in pls if len(pts) == 2 and math.dist(pts[0], (984.6, 895.1)) < 0.5]
    assert lat and math.dist(lat[0][1], (984.6, 968.3)) < 0.3         # el lateral muere EN ella


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h37_la_linea_no_se_corta_en_cada_doble_slash_ss():
    """«—//—ss—»: el trozo de línea entre el «//» y la «ss» se leía como asta de
    letra y la línea quedaba cortada 16–27 pt en cada ciclo."""
    _, pls = _sewer(DU08, 37)
    one = [pts for pts, k, lay in pls if any(math.dist(q, (576.8, 966.4)) < 0.5 for q in pts)
           and any(math.dist(q, (734.5, 1079.1)) < 0.5 for q in pts)]
    assert len(one) == 1
