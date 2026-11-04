"""Diámetros en un PDF vectorial sin capas ni leyenda, con la utilidad puesta a mano a cada estilo (pedido 2026-11-03,
«Southwest Gas Combined 811 Records»): rótulos en piezas sueltas, emparejar por el largo, IA y rótulos del DXF."""
import math
import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from hoja import pdf_styles  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_grosor_registros as GR  # noqa: E402

REAL = Path.home() / "OneDrive/Documentos/DOCS DE PRUEBA IND/APUNTES ING/Southwest Gas Combined 811 Records (1) 37.pdf"


@pytest.mark.parametrize("texto, esperado", [
    ('3/4"', (0.75, "")), ('1-1/4" STL `57', (1.25, "STL")), ('2" STL', (2.0, "STL")), ('3/4"STL', (0.75, "STL")),
    ("95' 1/2\" PE '88", (0.5, "PE")), ('12" PVC', (12.0, "PVC")), ('30" Unk', (30.0, "UNK")),
    ('72" STEEL CASING', None), ("SCALE: 1\" = 100'", None), ('2" ARV', None), ("57'", None), ('"', None),
])
def test_leer(texto, esperado):
    assert GR.leer(texto) == esperado


def _hoja(tmp_path, rotulo_lejos=True):
    """Seis líneas con su rótulo en piezas al lado y una séptima cuyo rótulo va apartado y sin ser paralelo."""
    doc = fitz.open()
    pg = doc.new_page(width=800, height=500)
    for k in range(6):
        x = 60 + 90 * k
        pg.draw_line((x, 100), (x, 100 + 40 + 5 * k), color=(1, 0.4, 0.1), width=0.5)
        for dy, texto in ((0, f"{(40 + 5 * k) * 1.5:.0f}'"), (22, '3/4"'), (44, "STL"), (66, "`57")):
            pg.insert_text((x + 8, 100 + 90 - dy), texto, fontsize=6, rotate=90)
    pg.draw_line((700, 100), (700, 180), color=(1, 0.4, 0.1), width=0.5)
    if rotulo_lejos:
        pg.insert_text((640, 150), "120' 1\" PE `88", fontsize=6)
    ruta = tmp_path / "registros.pdf"
    doc.save(ruta)
    return str(ruta)


def _reconocer(ruta):
    doc = fitz.open(ruta)
    capas = {d.get("layer") for d in pdf_styles.drawings(doc[0]) if (d.get("layer") or "").startswith(pdf_styles.PREFIX)}
    roles = {rec.ROLE_LINEAS: sorted(capas), rec.ROLE_BUZONES: []}
    r = rec.recognize_page(ruta, utility="GAS", layer_roles=roles, zoom=1, scale_ft_per_pt=1, doc=doc)
    return r, [p for p in r.polylines if len(p.pts_pdf) > 1]


def test_rotulo_en_piezas_y_por_su_largo(tmp_path):
    r, lineas = _reconocer(_hoja(tmp_path))
    junto = [p for p in lineas if p.pts_pdf[0][0] < 600]
    assert len(junto) == 6 and all(p.diam_in == 0.75 for p in junto)
    assert all(p.grosor["material"] == "STL" and "`57" in p.grosor["textos"][0] for p in junto)
    lejos = next(p for p in lineas if p.pts_pdf[0][0] > 600)
    assert lejos.diam_in == 1.0 and lejos.grosor["estado"] == "leido"
    assert any(a["texto"].startswith("120'") for a in r.anotaciones)     # van al DXF como rótulos


def test_sin_rotulo_queda_sin_dato_y_con_la_ficha_para_la_ia(tmp_path):
    _r, lineas = _reconocer(_hoja(tmp_path, rotulo_lejos=False))
    sola = next(p for p in lineas if p.pts_pdf[0][0] > 600)
    assert sola.diam_in is None and sola.grosor["estado"] == "sin_dato" and "cerca" in sola.grosor


@pytest.mark.skipif(not REAL.exists(), reason="PDF real del usuario")
def test_southwest_gas_real():
    doc = fitz.open(REAL)
    nombres = {pdf_styles.style_label(d["layer"]): d["layer"] for d in pdf_styles.drawings(doc[0])
               if (d.get("layer") or "").startswith(pdf_styles.PREFIX)}
    red = nombres["#008585 0.48 pt · continuo"]
    roles = {rec.ROLE_LINEAS: [red, nombres["#FF6921 0.24 pt · continuo"]], rec.ROLE_BUZONES: []}
    r = rec.recognize_page(str(REAL), utility="GAS", layer_roles=roles, zoom=1, scale_ft_per_pt=20 / 72, doc=doc)
    lineas = [p for p in r.polylines if len(p.pts_pdf) > 1]
    leidas = [p for p in lineas if (p.grosor or {}).get("estado") == "leido"]
    assert len(leidas) >= 0.85 * len(lineas) and len(r.anotaciones) >= 600
    principal = [p.diam_in for p in leidas if p.layer_ocg == red
                 and sum(math.dist(a, b) for a, b in zip(p.pts_pdf, p.pts_pdf[1:])) > 150]
    assert principal and set(principal) <= {1.25, 2.0, 3.0, 4.0}         # la red nunca toma los 3/4" de sus servicios
    assert all("cerca" in p.grosor for p in lineas if p.grosor.get("estado") != "leido")
