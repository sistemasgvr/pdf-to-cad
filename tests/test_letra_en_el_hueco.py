"""La LETRA del linetype en el hueco = la línea SIGUE (pedido del usuario 2026-10-06).

DU06 h.5 telecom: la línea «—T—» baja en diagonal, pasa por su «T» y sigue en curva hacia
la vertical; quedaba cortada en dos (la esquina de la curva caía detrás de su punta y la
«T» —dos trazos rectos— llegaba a medias al núcleo). En la misma hoja, una línea de agua
«—W—» de la capa genérica `G-XREF` se pintaba como telecom: el reparto por letras la unía
con una «esquina» falsa a una línea «—T—» que pasa de largo. DU06 h.9 y h.10 eléctrico: la
línea gira justo en su rótulo «SE» y quedaba cortada.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

import recognition as rec  # noqa: E402
import recognition_letter_lines as lines  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
needs_du06 = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
Z = 2.0


def _dist_to(pts, q):
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        best = min(best, math.hypot(q[0] - a[0] - t * vx, q[1] - a[1] - t * vy))
    return best


def _lines(hoja, utility):
    import fitz
    with fitz.open(str(DU06)) as doc:
        res = rec.recognize_page(None, hoja - 1, utility=utility, zoom=Z, doc=doc)
    return [[(x / Z, y / Z) for x, y in p.pts_pdf] for p in res.drawable]


def _one_line_through(pls, *points, tol=0.6):
    return [pts for pts in pls if all(_dist_to(pts, q) <= tol for q in points)]


@needs_du06
def test_du06_h5_telecom_sigue_por_su_letra_t():
    pls = _lines(5, "TELECOM")
    # tinta: la diagonal termina en (1039.9, 974.3), la curva de abajo nace en (1044.2, 984.7)
    assert _one_line_through(pls, (1033.7, 930.0), (1039.9, 974.3), (1044.2, 984.7), (1045.2, 1030.0))


@needs_du06
def test_du06_h5_linea_de_agua_de_g_xref_no_es_telecom():
    import fitz
    with fitz.open(str(DU06)) as doc:
        page = doc[4]
        uses = rec.letter_uses(rec.page_letters(page))
        use = next(u for k, u in uses.items() if k.endswith("G-XREF"))
        water = [p for p in page.get_drawings() if (p.get("layer") or "").endswith("G-XREF")
                 and abs(p["rect"].x0 - 939.2) < 0.2 and abs(p["rect"].x1 - 1002.1) < 0.2]
        letter_t = [p for p in page.get_drawings() if (p.get("layer") or "").endswith("G-XREF")
                    and 1037.5 < p["rect"].x0 < 1039.5 and p["rect"].x1 < 1046.0 and 977.5 < p["rect"].y0 < 979.0]
    assert len(water) == 1 and use.paths.get(lines.path_key(water[0])) is None
    assert len(letter_t) == 2 and all(use.paths.get(lines.path_key(p)) == "TELECOM" for p in letter_t)
    pls = _lines(5, "TELECOM")
    assert not any(_dist_to(pts, (970.0, 975.5)) <= 1.0 for pts in pls)


@needs_du06
@pytest.mark.parametrize("hoja, a, b", [(9, (1113.2, 1029.4), (1147.2, 1040.6)),
                                       (10, (666.5, 1067.8), (702.2, 1066.3))])
def test_du06_electrico_sigue_por_su_rotulo_se(hoja, a, b):
    pls = _lines(hoja, "ELECTRICO")
    assert _one_line_through(pls, a, b)
