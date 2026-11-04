"""Los atajos de velocidad del reconocimiento dan EXACTAMENTE lo mismo que la cuenta de antes (reporte del usuario
2026-11-02: «lo siento más lento»; el costo crecía mucho más rápido que el número de hojas)."""
import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest

from reconocimiento import recognition as rec
from reconocimiento import recognition_geom as geom
from reconocimiento import recognition_grosor as grosor
from reconocimiento import recognition_grosor_texto as texto


@pytest.mark.parametrize("giro", [0, 90, 180, 270])
def test_transformador_igual_que_pymupdf(giro):
    pagina = fitz.open().new_page(width=2592.123, height=1728.77)
    pagina.set_rotation(giro)
    m = pagina.rotation_matrix
    fn = rec.transformador_mupdf(m)
    azar = random.Random(giro)
    for _ in range(5000):
        x, y = azar.uniform(-500, 30000), azar.uniform(-500, 30000)
        p = fitz.Point(x, y) * m
        assert fn(x, y) == (p.x, p.y)


def _muros(azar, n=300):
    out = []
    for _ in range(n):
        x, y = azar.uniform(0, 4000), azar.uniform(0, 4000)
        if azar.random() < 0.5:
            out.append(((x, y), (x + azar.uniform(50, 400), y + azar.uniform(-4, 4))))
        else:
            out.append(((x, y), (x + azar.uniform(-4, 4), y + azar.uniform(50, 400))))
    return out


def test_paredes_con_filtro_igual_que_contra_todos(monkeypatch):
    azar = random.Random(11)
    muros = _muros(azar)
    lineas = []
    for _ in range(60):
        x, y = azar.uniform(0, 4000), azar.uniform(0, 4000)
        lineas.append([(x, y), (x + azar.uniform(100, 800), y + azar.uniform(-3, 3))])
    # una tubería con sus dos paredes de verdad, para que no todo sea None
    lineas.append([(500.0, 500.0), (1500.0, 500.0)])
    muros += [((500.0, 500.0 - 42.0), (1500.0, 500.0 - 42.0)), ((500.0, 500.0 + 42.0), (1500.0, 500.0 + 42.0))]
    con = [grosor.paredes(p, muros, 3.5 * 12 / 20.0, 3.5) for p in lineas]
    monkeypatch.setattr(grosor, "_muros_cerca", lambda todos, a, b, margen: todos)
    assert con == [grosor.paredes(p, muros, 3.5 * 12 / 20.0, 3.5) for p in lineas]


def _encima_de_antes(lineas, horiz):
    """La cuenta de antes: línea por línea, de la más cercana hacia atrás."""
    out = {}
    for k, i in enumerate(horiz):
        bb, tam = lineas[i][1], lineas[i][2]
        for j in reversed(horiz[:k]):
            bj, tj = lineas[j][1], lineas[j][2]
            if bb[1] - bj[3] > texto.BLOQUE_SALTO * max(tam, tj):
                continue
            if bb[1] - bj[1] <= 0.1 * tam:
                continue
            if abs(tam - tj) > 0.02 * max(tam, tj):
                continue
            al = texto.BLOQUE_ALINEADO * max(tam, tj)
            if abs(bb[0] - bj[0]) <= al or abs(bb[2] - bj[2]) <= al or abs((bb[0] + bb[2]) - (bj[0] + bj[2])) <= 2 * al:
                out[i] = j
                break
    return out


def test_encima_igual_que_la_cuenta_de_antes():
    azar = random.Random(3)
    lineas = []
    for _ in range(600):
        x, y = azar.choice((100.0, 400.0, 900.0)) + azar.uniform(-1, 1), azar.uniform(0, 3000)
        tam = azar.choice((8.0, 10.0, 12.57, 12.95))
        lineas.append(("t", (x, y, x + azar.uniform(40, 200), y + tam), tam, (1.0, 0.0)))
    horiz = sorted(range(len(lineas)), key=lambda i: (lineas[i][1][1], lineas[i][1][0]))
    assert texto._encima(lineas, horiz) == _encima_de_antes(lineas, horiz)
    assert texto._encima(lineas, []) == {}


def _corridas(azar, n=150):
    corridas = []
    for _ in range(n):
        x, y = azar.uniform(0, 800), azar.choice((100.0, 101.0, 300.0, 500.0)) + azar.uniform(-1.0, 1.0)
        L = azar.uniform(5, 200)
        a, b = (x, y), (x + L, y + azar.uniform(-0.4, 0.4))
        ux, uy = geom._unit(b[0] - a[0], b[1] - a[1])
        corridas.append(geom.Run(a, b, ux, uy))
    return corridas


@pytest.mark.parametrize("absorber", [False, True])
def test_fundir_corridas_con_filtro_igual_que_todas_contra_todas(monkeypatch, absorber):
    pat = geom.Pattern(dash_long=20.0, dash_short=None, gap_max=12.0, letter=5.0, join_gap=24.0, glyph_bridge=48.0,
                       vault_bridge=48.0, corner_tol=6.0)
    azar = random.Random(7)
    base = _corridas(azar)
    con = geom.merge_overlapping_runs(list(base), pat, absorber)
    monkeypatch.setattr(geom, "RUNS_MERGE_GAP_PT", 1e9)
    sin = geom.merge_overlapping_runs(list(base), pat, absorber)
    assert [(r.a, r.b) for r in con] == [(r.a, r.b) for r in sin]
    assert len(con) < len(base)


DU06 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


@pytest.mark.skipif(not os.path.isfile(DU06), reason="PDF de prueba DU06 no está en el repo")
@pytest.mark.parametrize("hoja", [3, 4, 12])
def test_capas_visibles_igual_que_recortar_todo(hoja):
    from hoja import leyenda_trazos, pdf_layers, pdf_styles
    with fitz.open(DU06) as doc, pdf_styles.lectura_unica(doc):
        pdf_layers.set_hidden(doc, ())
        page = doc[hoja]
        todos = {d.get("layer") or "" for d, _s in leyenda_trazos.trazos_visibles(page, None)}
        assert leyenda_trazos.capas_visibles(page) == todos


@pytest.mark.skipif(not os.path.isfile(DU06), reason="PDF de prueba DU06 no está en el repo")
def test_letras_de_la_misma_hoja_se_leen_una_vez_y_dependen_de_las_capas(monkeypatch):
    from hoja import pdf_layers
    lecturas = []
    original = rec._leer_letras
    monkeypatch.setattr(rec, "_leer_letras", lambda p, d=None: (lecturas.append(p.number), original(p, d))[1])
    rec._LETRAS_MEMO.clear()
    with fitz.open(DU06) as doc:
        primera = rec.page_letters(doc[4])
    with fitz.open(DU06) as doc:                         # otro documento, el mismo archivo y estado
        assert rec.page_letters(doc[4]) is primera
        assert lecturas == [4]
        nombres = [c["text"] for c in doc.layer_ui_configs()]
        pdf_layers.set_hidden(doc, nombres[:1])          # otras capas encendidas: otra lectura
        rec.page_letters(doc[4])
        assert lecturas == [4, 4]
    rec._LETRAS_MEMO.clear()
