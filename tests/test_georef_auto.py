"""Georreferencia automática por lo que dice la hoja (2026-11-18, `app/geo/auto/`): cuartos de sección de Phoenix."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(RAIZ, "app"), RAIZ):
    if p not in sys.path:
        sys.path.insert(0, p)

from geo.auto import indice_mapas  # noqa: E402


def test_tabla_phoenix_16_10():
    ix = indice_mapas.cargar("phoenix_qs")
    c = ix.celdas["16-10"]
    assert ix.epsg == 2868 and len(ix.celdas) >= 3700
    assert c.plss == ("2N", "1E", 26, "NE")
    x, y = c.centroide()
    assert abs(x - 606045) < 30 and abs(y - 906300) < 30
    assert ix.celdas["17-10"].centroide()[1] > y      # la fila crece hacia el norte
    assert ix.celdas["16-11"].centroide()[0] > x      # la columna hacia el este
    assert "phoenix_qs" in indice_mapas.disponibles()


def test_celdas_con_el_mismo_numero_son_cuadros_distintos():
    """«24-04» (R1W, al oeste del meridiano) y «24-4» (R1E) no son la misma celda."""
    ix = indice_mapas.cargar("phoenix_qs")
    dos = dict(ix.por_numero(24, 4))
    assert set(dos) == {"24-04", "24-4"}
    assert dos["24-04"].plss[1] == "1W" and dos["24-4"].plss[1] == "1E"
    assert dos["24-04"].centroide()[0] < dos["24-4"].centroide()[0]
    assert [k for k, _ in ix.por_numero(16, 10)] == ["16-10"]

from geo.auto import fuentes  # noqa: E402

PDFS_DIR = os.environ.get("PDFCAD_PDFS_INDIAN", "C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
PDFS = pytest.mark.skipif(not os.path.isdir(PDFS_DIR), reason="faltan los PDF de Indian School")


def _doc(nombre):
    import fitz
    return fitz.open(os.path.join(PDFS_DIR, nombre + ".pdf"))


def test_confirma_por_plss_o_ciudad():
    ix = indice_mapas.cargar("phoenix_qs"); c = ix.celdas["16-10"]
    assert fuentes.confirma("NE 1/4 SEC.26, T.2N, R.1E", c, ix)
    assert fuentes.confirma("Water Services · City of Phoenix", c, ix)
    assert not fuentes.confirma("SW 1/4 SEC.26, T.2N, R.1E", c, ix)      # PLSS de otra celda
    assert not fuentes.confirma("QS 16-10  City of Tucson", c, ix)
    # con número repetido, el PLSS elige: 24-04 es R1W
    dos = dict(ix.por_numero(24, 4))
    assert fuentes.confirma("NW 1/4 SEC. 2, T.2N, R.1W", dos["24-04"], ix)
    assert not fuentes.confirma("NW 1/4 SEC. 2, T.2N, R.1W", dos["24-4"], ix)


class _Ficha:
    def __init__(self, celda, vista=(0, 0, 100, 100)):
        self.celda, self.vista, self.lineas = celda, vista, []


class _Pagina:
    def __init__(self, texto):
        self.texto = texto

    def get_text(self):
        return self.texto

    @property
    def parent(self):
        return None

    def get_fonts(self, full=False):
        return []


def test_sin_celda_celda_desconocida_o_sin_confirmar_no_ubica():
    p = _Pagina("NE 1/4 SEC.26, T.2N, R.1E")
    assert fuentes.ubicar(p, _Ficha(None)) is None
    assert fuentes.ubicar(p, _Ficha((999, 1))) is None
    assert fuentes.ubicar(_Pagina("QS 16-10"), _Ficha((16, 10))) is None        # sin jurisdicción
    assert fuentes.ubicar(_Pagina("City of Phoenix"), _Ficha((24, 4))) is None  # ambigua sin PLSS
    u = fuentes.ubicar(p, _Ficha((16, 10)))
    assert u.etiqueta == "16-10" and u.anclas[0].hoja_pt == (50, 50)


@PDFS
def test_ubicar_hoja_water_south():
    from hoja import composicion_ficha as cf
    p = _doc("QS Water_Indian School_South")[0]
    u = fuentes.ubicar(p, cf.ficha(p, 0))
    assert u.epsg == 2868 and u.cs_code == "AZHP-CIF" and len(u.anclas) == 1
    assert u.anclas[0].mundo == pytest.approx(indice_mapas.cargar("phoenix_qs").celdas["16-10"].centroide())

# ─────────────────────────── ajuste de la hoja compuesta ───────────────────────────
import functools  # noqa: E402
import math  # noqa: E402

from geo import georef  # noqa: E402
import json  # noqa: E402

from geo.auto import ajuste  # noqa: E402

DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
ZOOM = 3.5


@functools.lru_cache(maxsize=None)
def _compuesta(nombre):
    """Hoja compuesta sugerida del PDF entero (como la arma «Componer hoja»)."""
    from hoja import composicion_ficha as cf
    from hoja import composicion_sugerida as CS
    d = _doc(nombre)
    an = CS.analizar([cf.fichas(d, 0)])
    g = max(an.grupos, key=lambda g: len(g.nodos))
    comp = CS.armar(g, an, [d], lambda *_: 20 / 72.0)
    fichas = {(0, n[1]): f for n, f in an.fichas.items()}
    return comp, d, fichas


def _georref_compuesta(nombre):
    comp, d, fichas = _compuesta(nombre)
    return ajuste.georref_hoja(comp, [d], ZOOM, fichas)


@PDFS
def test_sewer_north_queda_en_sus_cuadros():
    r = _georref_compuesta("QS Sewer_Indian School_North")
    print("Sewer North: RMS %.1f ft, máx %.1f ft, %d piezas" % (r.rms_ft, max(r.residuos.values()), len(r.residuos)))
    assert r.aceptada and r.epsg == 2868 and r.cs_code == "AZHP-CIF"
    assert len(r.residuos) >= 16
    assert r.rms_ft <= 10 and max(r.residuos.values()) <= 15


@PDFS
def test_cruces_de_calles_caen_en_su_lugar_real():
    """Verdad independiente: el cruce de los ejes de calle DIBUJADO en el PDF, llevado por la georreferencia,
    cae junto al cruce de la capa pública de intersecciones de Phoenix."""
    from hoja import composite as C
    datos = json.load(open(os.path.join(DATOS, "phoenix_cruces.json"), encoding="utf-8"))
    comp, d, fichas = _compuesta(datos["pdf"])
    r = ajuste.georref_hoja(comp, [d], ZOOM, fichas)
    g = georef.Georef(r.matrix, r.epsg, "similarity")

    def size(pz):
        return d[pz.page].rect.width, d[pz.page].rect.height
    _, _, dx, dy = C.sheet_geometry(comp, size)
    errores = []
    for cr in datos["cruces"]:
        pz = next(p for p in comp.pieces if p.page == cr["hoja"])
        x, y = C.piece_map(pz, size(pz), comp.target_scale())(*cr["pdf_pt"])
        e, n = g.to_world((x + dx) * ZOOM, (y + dy) * ZOOM)
        errores.append(math.hypot(e - cr["mundo"][0], n - cr["mundo"][1]))
    print("cruces de calles: error", ["%.1f ft" % v for v in errores])
    assert max(errores) <= 25


@PDFS
def test_water_south_queda_dudosa():
    r = _georref_compuesta("QS Water_Indian School_South")
    print("Water South: RMS %.1f ft (%s)" % (r.rms_ft, r.motivo))
    assert not r.aceptada and r.rms_ft > 25


@PDFS
def test_hoja_suelta_usa_la_escala_del_recuadro_y_giro_cero():
    """Una sola hoja (con /Rotate 90): ancla con la escala del recuadro, norte arriba; el cruce cae en su lugar."""
    from hoja import composite as C
    d = _doc("QS Sewer_Indian School_North")
    sola = fitz_doc_hoja(d, 2)
    r = ajuste.georref_hoja(None, [sola], ZOOM)
    assert r.aceptada and r.matrix[0][1] == pytest.approx(0, abs=1e-9) and r.matrix[1][0] == pytest.approx(0, abs=1e-9)
    cr = json.load(open(os.path.join(DATOS, "phoenix_cruces.json"), encoding="utf-8"))["cruces"][0]
    e, n = georef.Georef(r.matrix, r.epsg).to_world(cr["pdf_pt"][0] * ZOOM, cr["pdf_pt"][1] * ZOOM)
    print("hoja suelta: cruce a %.1f ft" % math.hypot(e - cr["mundo"][0], n - cr["mundo"][1]))
    assert math.hypot(e - cr["mundo"][0], n - cr["mundo"][1]) <= 25
    assert C is not None


def fitz_doc_hoja(d, i):
    import fitz
    nuevo = fitz.open()
    nuevo.insert_pdf(d, from_page=i, to_page=i)
    return nuevo
