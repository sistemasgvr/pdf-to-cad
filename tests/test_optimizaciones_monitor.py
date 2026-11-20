"""Optimizaciones del 2026-11-20 (lo que señaló el monitor con los QS SD de Phoenix): cada una da EXACTAMENTE lo
mismo que el código de antes."""
import os
import random
import sys
from collections import Counter, defaultdict

import numpy as np
import pytest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]

from hoja import composicion_costuras as CC  # noqa: E402
from hoja import composicion_encaje as CE  # noqa: E402
from hoja import imagen_paleta as IP  # noqa: E402
from hoja import leyendas_imagen as LI  # noqa: E402


def test_empaquetar_da_los_mismos_valores():
    rng = np.random.default_rng(1)
    for forma in ((7, 5, 3), (64, 33, 4), (1, 1, 3)):
        img = rng.integers(0, 256, forma, dtype=np.uint8)
        a = img[..., :3].astype(np.uint32)
        viejo = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
        nuevo = IP._empaquetar(img)
        assert nuevo.dtype == np.uint32 and nuevo.shape == viejo.shape
        assert (nuevo == viejo).all()
    vista = rng.integers(0, 256, (20, 30, 3), dtype=np.uint8)[::2, ::3]      # no contigua
    a = vista.astype(np.uint32)
    assert (IP._empaquetar(vista) == ((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2])).all()


def _votar_viejo(A, B, sc, guia=None):
    bk = defaultdict(list)
    for t in B:
        bk[round(t[2] * 10)].append(t)
    tv, ej = Counter(), defaultdict(list)
    for s in A:
        for t in bk.get(round(s[2] * 10), ()):
            if t[0] != s[0] or abs(t[1] - s[1] * sc) > CE.MAPA_TOL_PT + 0.01 * t[1]:
                continue
            dx = t[3] - s[3] * sc
            dy = t[4] - s[4] * sc
            if guia is not None and (abs(dx - guia[0]) > CE.MAPA_GUIA_VENTANA_PT
                                     or abs(dy - guia[1]) > CE.MAPA_GUIA_VENTANA_PT):
                continue
            if abs(t[5] - s[5] * sc - dx) > CE.MAPA_TOL_PT or abs(t[6] - s[6] * sc - dy) > CE.MAPA_TOL_PT:
                continue
            k = (round(dx / CE.MAPA_BIN_PT), round(dy / CE.MAPA_BIN_PT))
            tv[k] += 1
            ej[k].append((s, t))
    return tv, ej


def _segs(rng, n, base=None):
    out = []
    for i in range(n):
        if base is not None and rng.random() < 0.6:
            s = base[rng.randrange(len(base))]
            d = (rng.choice([0, 0, 0.1, 5.0]), rng.choice([0, 0, -0.2, 3.0]))
            out.append((s[0], s[1] * rng.choice([1, 1, 1.004]), s[2], s[3] + d[0], s[4] + d[1], s[5] + d[0], s[6] + d[1]))
            continue
        x, y = rng.uniform(0, 500), rng.uniform(0, 500)
        L = rng.choice([rng.uniform(1, 80), 10.0, 20.0])
        r = rng.choice([0, 0.5, 45.0, 90.0])
        out.append((rng.choice(["n", "a", "r"]), L, r, x, y, x + L, y))
    return out


@pytest.mark.parametrize("semilla", range(8))
def test_votar_igual_que_antes(semilla):
    rng = random.Random(semilla)
    A = _segs(rng, 400)
    B = _segs(rng, 500, A)
    for sc in (1.0, 1.02856, 0.97):
        for guia in (None, (5.0, 3.0)):
            tv0, ej0 = _votar_viejo(A, B, sc, guia)
            tv1, ej1 = CE._votar(A, B, sc, guia)
            assert tv0 == tv1
            assert dict(ej0) == dict(ej1)            # mismas listas y en el mismo orden


@pytest.mark.parametrize("semilla", range(6))
def test_costo_del_corte_bit_a_bit(semilla, monkeypatch):
    rng = random.Random(semilla)

    def trazos(n):
        out = []
        for _ in range(n):
            c0 = rng.uniform(-50, 50)
            c1 = c0 if rng.random() < 0.1 else c0 + rng.uniform(-30, 30)
            s0 = rng.uniform(0, 400)
            out.append((c0, c1, s0, s0 + rng.uniform(-80, 80)))
        return out
    ta, tb = trazos(300), trazos(250)
    ga = [rng.random() < 0.4 for _ in ta]
    gb = [rng.random() < 0.4 for _ in tb]
    nuevo = CC._costo_corte(ta, ga, tb, gb)
    monkeypatch.setattr(CC, "COSTO_EN_PYTHON", True)
    viejo = CC._costo_corte(ta, ga, tb, gb)
    for k in range(400):
        x = -60 + k * 0.3
        assert nuevo(x) == viejo(x)                   # el mismo float, no «casi»


def test_leyenda_en_imagen_solo_mira_las_de_su_medida():
    class Doc:
        def __init__(self):
            self.extraidas = 0

        def extract_image(self, xref):
            self.extraidas += 1
            return {"image": b"otra"}

    class Pag:
        number = 0

        def __init__(self, doc, imgs):
            self.parent, self._imgs = doc, imgs

        def get_images(self, full=True):
            return self._imgs

    d = Doc()
    tiras = [(i, 0, 20, 52, 4, "Indexed", "", f"Im{i}", "FlateDecode", 0) for i in range(500)]
    assert LI.conocida(Pag(d, tiras)) is None and d.extraidas == 0
    d2 = Doc()
    assert LI.conocida(Pag(d2, tiras + [(999, 0, 828, 8696, 8, "DeviceRGB", "", "Im", "FlateDecode", 0)])) is None
    assert d2.extraidas == 1


SOUTHWEST = (r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/APUNTES ING/"
             r"Southwest Gas Combined 811 Records (1) 37.pdf")


@pytest.mark.skipif(not os.path.isfile(SOUTHWEST), reason="sin el PDF de Southwest Gas")
def test_cada_leyenda_conocida_tiene_su_medida_en_tamanos():
    import hashlib
    import fitz
    with fitz.open(SOUTHWEST) as d:
        vistas = {}
        for im in d[0].get_images(full=True):
            h = hashlib.sha1(d.extract_image(im[0])["image"]).hexdigest()
            vistas[h] = (im[2], im[3])
        for h in LI.CONOCIDAS:
            if h in vistas:
                assert vistas[h] in LI.TAMANOS
        assert LI.conocida(d[0]) is not None


# ── piezas del compositor dibujadas en varios procesos ─────────────────────────────────────────────────────
def _pdf_con_capas(paginas=6):
    import fitz
    doc = fitz.open()
    a = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    b = doc.add_ocg("V-ROAD-CURB", on=True)
    for i in range(paginas):
        pg = doc.new_page(width=600, height=400)
        pg.insert_text((50, 60), f"hoja {i + 1}", fontsize=14)
        for k in range(40):
            pg.draw_line((20 + k * 13, 80), (40 + k * 11, 380 - i * 5), color=(0.1 * (k % 9), 0.2, 0.6),
                         width=0.4 + 0.07 * k, oc=a if k % 2 else b)
        pg.draw_circle((300 + i * 9, 200), 47.3, color=(1, 0, 0), width=1.7, oc=a)
    data = doc.tobytes()
    doc.close()
    return data


def test_dibujo_en_otro_proceso_da_los_mismos_bytes():
    import fitz
    from hoja import pdf_layers, render_lote
    data = _pdf_con_capas(3)
    doc = fitz.open(stream=data, filetype="pdf")
    pdf_layers.set_hidden(doc, ["V-ROAD-CURB"])
    pedidos = [(0, 0.7, (0, 0, 600, 400)), (1, 1.37, (33.3, 17.1, 401.9, 250.2)), (2, 2.11, (100, 100, 590, 399))]
    for (hoja, esc, r), (w, h, stride, x, y, samples) in zip(
            pedidos, render_lote.dibujar(data, pdf_layers.encendidas(doc), pedidos)):
        pix = doc[hoja].get_pixmap(matrix=fitz.Matrix(esc, esc), alpha=False, clip=fitz.Rect(*r))
        assert (w, h, stride, x, y) == (pix.width, pix.height, pix.stride, pix.x, pix.y)
        assert samples == bytes(pix.samples)


def test_rebuild_con_procesos_da_las_mismas_imagenes(monkeypatch):
    """`CompositeView.rebuild` con las piezas dibujadas en varios procesos = dibujadas en la ventana."""
    import fitz
    from PySide6 import QtWidgets
    from hoja import composite as C
    from hoja import pdf_layers
    from ui.asistente import composite_renders as CR
    from ui.asistente import composite_renders_lote as LOTE
    from ui.asistente import composite_view as CV
    from ui.comun import proceso_hijo
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    data = _pdf_con_capas(6)
    comp = C.Composite([C.Piece(0, i, [0.05 * (i % 3), 0.02, 0.97, 0.9 + 0.01 * i], 620 * i, 0,
                                polygon=[[0.1, 0.1], [0.9, 0.05], [0.95, 0.9], [0.05, 0.95]] if i == 2 else [])
                        for i in range(6)])

    def vista():
        doc = fitz.open(stream=data, filetype="pdf")
        pdf_layers.set_hidden(doc, ["V-ROAD-CURB"])
        CR.marcar(doc, data)
        return CV.CompositeView(comp, [doc])

    def imagenes(v):
        out = []
        for it in v.items:
            pm, origen = v.render_piece_raw(it.piece, v.overview_scale(it.piece))
            img = pm.toImage().convertToFormat(pm.toImage().format())
            out.append((origen, img.width(), img.height(), bytes(img.constBits()[:img.sizeInBytes()])))
        return out

    monkeypatch.setenv("PDFCAD_PROCESO", "0")              # en la ventana, como siempre
    CR.soltar()
    v1 = vista()
    v1.rebuild()
    antes = imagenes(v1)
    monkeypatch.setenv("PDFCAD_PROCESO", "1")              # en varios procesos
    monkeypatch.setattr(proceso_hijo, "paralelos", lambda n, mb=0: 2)
    CR.soltar()
    dibujadas_aqui = []
    orig = CV.CompositeView._render_piece_raw
    monkeypatch.setattr(CV.CompositeView, "_render_piece_raw",
                        lambda self, p, s: dibujadas_aqui.append(p.page) or orig(self, p, s))
    try:
        v2 = vista()
        v2.rebuild()
        assert dibujadas_aqui == []                        # todas salieron de los procesos
        assert imagenes(v2) == antes
    finally:
        LOTE.soltar()


def test_puentes_en_una_sola_shape_dibujan_lo_mismo(monkeypatch):
    """Los guiones de los puentes en UNA `Shape` (un solo `commit`) = uno por `draw_line` como antes: mismos trazos
    con su capa, color y grosor, en el mismo orden, y los mismos píxeles con y sin la capa del puente."""
    import fitz
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_composite import _gap_pdf, _reopen
    from hoja import composite as C
    from hoja import pdf_layers
    doc = _gap_pdf()
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1], x=340)])
    puentes = C.compute_bridges(comp, [doc])
    assert len(puentes) == 2

    def hoja(de_a_uno):
        monkeypatch.setattr(C, "PUENTES_DE_A_UNO", de_a_uno)
        dst = _reopen(C.build_document(comp, [doc], None, puentes))
        trazos = [(tuple(round(v, 4) for v in d["rect"]), d.get("color"), d.get("width"), d.get("layer"),
                   [(it[0], *(tuple(round(c, 4) for c in q) for q in it[1:])) for it in d["items"]])
                  for d in dst[0].get_drawings(extended=True) if d.get("type") not in ("clip", "group")]
        pix = [dst[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).samples]
        pdf_layers.set_hidden(dst, {"C-ELEC-UNGD-E"})
        pix.append(dst[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).samples)
        return trazos, pix

    viejo, nuevo = hoja(True), hoja(False)
    assert viejo[0] == nuevo[0]
    assert viejo[1] == nuevo[1]


def _sin_id(b: bytes) -> bytes:
    import re
    return re.sub(rb"/ID\[<[0-9A-F]+><[0-9A-F]+>\]", b"", b)          # PyMuPDF pone un /ID al azar en cada PDF


def test_nombres_al_dia_dan_el_mismo_pdf(monkeypatch):
    """`_NombresDestino` elige el MISMO «fzFrmN» que el recorrido de PyMuPDF: el PDF sale igual byte a byte (salvo
    el /ID al azar), también con hojas de origen que ya traen recursos «fzFrm…» (una compuesta compuesta otra vez)."""
    import fitz
    from hoja import composite as C
    src = fitz.open()
    for i in range(5):
        pg = src.new_page(width=500, height=400)
        pg.insert_text((40, 50 + i), f"hoja {i}", fontsize=12 + i)
        for k in range(3):
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8 + k, 5 + i), False)
            pix.clear_with(40 * k + i)
            pg.insert_image(fitz.Rect(50 + 60 * k, 100, 100 + 60 * k, 140), pixmap=pix)
        pg.draw_line((10, 300), (490, 310 + i))
    otra = fitz.open()                                   # ya compuesta: trae «fzFrm0» adentro
    otra.new_page(width=500, height=400).show_pdf_page(fitz.Rect(0, 0, 500, 400), src, 1)
    docs = [src, otra]
    piezas = [C.Piece(0, i % 5, [0.02, 0.02, 0.98, 0.98], 520 * (i % 4), 420 * (i // 4)) for i in range(9)]
    piezas.append(C.Piece(1, 0, [0, 0, 1, 1], 0, 1300))
    comp = C.Composite(piezas)
    monkeypatch.setattr(C, "NOMBRES_DE_SIEMPRE", True)
    viejo = _sin_id(C.build_document(comp, docs, {}, []).tobytes())
    monkeypatch.setattr(C, "NOMBRES_DE_SIEMPRE", False)
    nuevo = _sin_id(C.build_document(comp, docs, {}, []).tobytes())
    assert viejo == nuevo


def test_tesela_comprimida_vuelve_igual():
    from hoja import imagen_ejes as IE
    rng = np.random.default_rng(3)
    img = np.full((300, 200, 3), 255, np.uint8)
    img[50:60] = rng.integers(0, 256, (10, 200, 3), dtype=np.uint8)
    c = IE._Comprimida(img)
    x = c.imagen()
    assert x.shape == img.shape and x.dtype == img.dtype and (x == img).all()
    x[0, 0, 0] = 1                                         # escribible, como la tesela original
    assert [i.shape for i in IE._Imagenes([c, c])] == [img.shape, img.shape] and len(IE._Imagenes([c])) == 1


def test_vaciar_la_cache_de_mupdf_no_cambia_la_copia():
    import fitz
    from hoja import composite as C
    data = _pdf_con_capas(2)
    d = fitz.open(stream=data, filetype="pdf")
    d[0].get_drawings()
    a = fitz.open(); a.insert_pdf(d, from_page=0, to_page=0)
    C.vaciar_cache_mupdf()
    b = fitz.open(); b.insert_pdf(d, from_page=0, to_page=0)
    assert _sin_id(a.tobytes()) == _sin_id(b.tobytes())


# ── índices de `resolve_nodes` (2026-11-20) ───────────────────────────────────────────────────────────────
def test_indice_de_puntos_da_todos_los_del_cuadrado_en_orden():
    from reconocimiento import recognition_geom_indice as GI
    rng = random.Random(5)
    pts = [(rng.uniform(-300, 300), rng.uniform(-300, 300)) for _ in range(800)]
    idx = GI.IndicePuntos(pts, 37.0)
    for _ in range(200):
        p, r = (rng.uniform(-320, 320), rng.uniform(-320, 320)), rng.choice([0.5, 3.0, 25.0, 90.0])
        todos = [i for i, q in enumerate(pts) if abs(q[0] - p[0]) <= r and abs(q[1] - p[1]) <= r]
        assert idx.vecinos(p, r) == todos


def test_indice_de_corridas_no_deja_fuera_ninguna_que_el_bucle_aceptaria():
    from reconocimiento import recognition_geom as G
    from reconocimiento import recognition_geom_indice as GI
    rng = random.Random(9)
    runs = []
    for _ in range(400):
        a = (rng.uniform(0, 600), rng.uniform(0, 600))
        ang = rng.uniform(0, math.pi)
        L = rng.uniform(1, 120)
        b = (a[0] + L * math.cos(ang), a[1] + L * math.sin(ang))
        runs.append(G.Run(a, b, math.cos(ang + rng.uniform(-0.02, 0.02)), math.sin(ang), []))
    idx = GI.IndiceCorridas(runs, 40.0, G._desvio_tangente)
    for _ in range(300):
        p = (rng.uniform(0, 600), rng.uniform(0, 600))
        for margen in (2.0, 8.0):
            c = idx.candidatos(p, margen)
            assert c == sorted(c)
            for j, r in enumerate(runs):
                t, perp = r.param(p)
                if 0.0 < t < 1.0 and perp <= margen:            # lo que aceptan las «T» (perp a la cuerda)
                    assert j in c


import math  # noqa: E402

DU06 = r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"


@pytest.mark.skipif(not os.path.isfile(DU06), reason="sin el PDF DU06")
@pytest.mark.parametrize("hoja,utilidad", [(3, "ELECTRICO"), (3, "DRENAJE"), (4, "TELECOM"), (12, "AGUA")])
def test_reconocer_con_y_sin_indices_da_lo_mismo(hoja, utilidad, monkeypatch):
    import pickle
    from reconocimiento import recognition as rec
    from reconocimiento import recognition_geom as G

    def foto():
        r = rec.recognize_page(DU06, hoja, utility=utilidad, zoom=1.0)
        return pickle.dumps([(pl.pts_pdf, pl.kinds, pl.fillets, pl.abandoned) for pl in r.drawable]
                            + [r.warnings, len(r.vaults_geo or [])])
    monkeypatch.setattr(G, "SIN_INDICES", True)
    viejo = foto()
    monkeypatch.setattr(G, "SIN_INDICES", False)
    assert foto() == viejo
