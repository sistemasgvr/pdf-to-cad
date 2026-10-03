"""Tubería dibujada con sus dos paredes (reporte del usuario 2026-10-02, ET-004
`C-SSWR-PIPE`): una sola utilidad, la línea del medio. Y lo que NO es pared."""
import math
import os

import fitz
import pytest

import recognition as rec
import recognition_walls as W

REAL = r"C:/Users/bernu/OneDrive/Documentos/NUEVOS DOCS PRUEBA/proyecto02.10.digproj.src.pdf"


def sheet(tmp_path, strokes, name="w.pdf"):
    """strokes: [(capa, [puntos], cerrado)] dibujados como trazos continuos."""
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    ocgs = {}
    for ocg, pts, closed in strokes:
        ocgs.setdefault(ocg, doc.add_ocg(ocg))
        sh = page.new_shape()
        sh.draw_polyline([fitz.Point(*p) for p in pts])
        sh.finish(color=(0.5, 0, 1), width=0.48, oc=ocgs[ocg], closePath=closed)
        sh.commit()
    out = tmp_path / name
    doc.save(str(out))
    doc.close()
    return str(out)


def dashed(ocg, a, b, dash=12.0, gap=3.0):
    L = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    out, t = [], 0.0
    while t < L:
        e = min(L, t + dash)
        out.append((ocg, [(a[0] + ux * t, a[1] + uy * t), (a[0] + ux * e, a[1] + uy * e)], False))
        t = e + gap
    return out


def lines(path, utility="ALCANTARILLADO"):
    res = rec.recognize_page(path, 0, utility=utility, zoom=1.0)
    return res, [pl for pl in res.drawable]


def test_dos_paredes_son_una_sola_linea_al_medio(tmp_path):
    pdf = sheet(tmp_path, [("C-SSWR-PIPE", [(100, 200), (700, 200)], False),
                           ("C-SSWR-PIPE", [(100, 201.3), (700, 201.3)], False)])
    res, pls = lines(pdf)
    assert len(pls) == 1
    pts = pls[0].pts_pdf
    assert all(abs(y - 200.65) <= 0.05 for _x, y in pts)
    assert sorted(round(x) for x, _y in (pts[0], pts[-1])) == [100, 700]
    assert any(w.startswith("Tuberías dibujadas con sus dos paredes: 1") for w in res.warnings)
    assert len(res.walls_px) == 1


def test_paredes_en_L_dan_la_esquina_del_eje(tmp_path):
    pdf = sheet(tmp_path, [("C-SSWR-PIPE", [(100, 100), (600, 100), (600, 500)], False),
                           ("C-SSWR-PIPE", [(100, 101.3), (598.7, 101.3), (598.7, 500)], False)])
    _res, pls = lines(pdf)
    assert len(pls) == 1
    corner = min(pls[0].pts_pdf, key=lambda p: math.dist(p, (600, 100)))
    assert corner == pytest.approx((599.35, 100.65), abs=0.05)


def test_midline_a_inglete_es_exacta():
    a = [(0, 0), (100, 0), (100, 100)]
    b = [(0, 2), (98, 2), (98, 100)]
    m = W.midline(a, b)
    assert m == [pytest.approx((0, 1)), pytest.approx((99, 1)), pytest.approx((99, 100))]


@pytest.mark.parametrize("center", ["continuo", "a trazos"])
def test_paredes_y_eje_se_usa_el_eje(tmp_path, center):
    walls = [("C-SSWR-PIPE", [(100, 198.5), (700, 198.5)], False),
             ("C-SSWR-PIPE", [(100, 201.5), (700, 201.5)], False)]
    axis = ([("C-SSWR-PIPE", [(100, 200), (700, 200)], False)] if center == "continuo"
            else dashed("C-SSWR-PIPE", (100, 200), (700, 200)))
    res, pls = lines(sheet(tmp_path, walls + axis))
    assert len(pls) == 1
    assert all(abs(y - 200) <= 0.05 for _x, y in pls[0].pts_pdf)
    assert any(w.startswith("Tuberías dibujadas con paredes y eje: 1") for w in res.warnings)


def test_eje_en_otra_capa_de_la_utilidad(tmp_path):
    pdf = sheet(tmp_path, [("C-SSWR-PIPE", [(100, 198.5), (700, 198.5)], False),
                           ("C-SSWR-PIPE", [(100, 201.5), (700, 201.5)], False),
                           ("C-SSWR-UNGD-N", [(100, 200), (700, 200)], False)])
    _res, pls = lines(pdf)
    assert len(pls) == 1 and pls[0].layer_ocg == "C-SSWR-UNGD-N"


def test_tres_paralelas_no_se_tocan(tmp_path):
    """Marco del cajetín / varias tuberías juntas: tres paralelas sin eje al medio."""
    pdf = sheet(tmp_path, [("C-SSWR-PIPE", [(100, 200 + d), (700, 200 + d)], False) for d in (0, 1.3, 4.0)])
    res, pls = lines(pdf)
    assert not res.walls_px
    assert not any("paredes" in w for w in res.warnings)


def test_dos_tuberias_de_distinto_largo_no_son_paredes(tmp_path, monkeypatch):
    """No van juntas de inicio a fin: la regla no actúa y el resultado es el de antes."""
    pdf = sheet(tmp_path, [("C-ELEC-UNGD-N", [(100, 200), (700, 200)], False),
                           ("C-ELEC-UNGD-N", [(100, 203), (400, 203)], False)])
    res, pls = lines(pdf, "ELECTRICO")
    assert not res.walls_px
    monkeypatch.setattr(rec.walls_mod, "merge_walls", lambda paths, others=(), make_rect=None: (list(paths), []))
    _res, before = lines(pdf, "ELECTRICO")
    assert [p.pts_pdf for p in pls] == [p.pts_pdf for p in before]


def test_lineas_con_letras_no_son_paredes(tmp_path):
    """DU10 h.25: líneas de agua «—W—» paralelas con los guiones en fase."""
    strokes = []
    for y in (200.0, 203.6):
        x = 100.0
        while x < 650:
            strokes.append(("C-WATR-UNGD-E", [(x, y), (x + 32, y)], False))
            # «W» en el hueco: zigzag que cruza la línea
            strokes.append(("C-WATR-UNGD-E", [(x + 34.4, y - 2.4), (x + 35.8, y + 2.4),
                                              (x + 37.2, y - 2.4), (x + 38.6, y + 2.4)], False))
            x += 42.2
    res, _pls = lines(sheet(tmp_path, strokes), utility="AGUA")
    assert not res.walls_px


def test_figura_cerrada_no_es_pared():
    """DU06 h.4: dos cuadrados anidados de un símbolo en la capa de la línea."""
    def sq(x0, y0, s):
        p = [(x0, y0), (x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s), (x0, y0)]
        return {"items": [("l", fitz.Point(*a), fitz.Point(*b)) for a, b in zip(p, p[1:])],
                "closePath": False, "fill": None}
    out, changes = W.merge_walls([sq(605.3, 1138.7, 35.5), sq(607.7, 1141.1, 30.6)])
    assert not changes and len(out) == 2


def test_corte_en_angulo_del_clip():
    """Pared cortada por el borde de la vista en diagonal: cada pared termina a
    distinta altura; el eje termina en el medio de los dos cortes."""
    def path(a, b, cut):
        return {"items": [("l", a, b)], "closePath": False, "fill": None, "cut_pts": [cut]}
    a = path((2902.9, 339.4), (2912.0, 430.6), (2912.0, 430.6))
    b = path((2904.1, 339.3), (2912.0, 418.6), (2912.0, 418.6))
    out, changes = W.merge_walls([a, b])
    assert len(changes) == 1 and len(out) == 1
    assert out[0]["cut_pts"] == [pytest.approx((2912.0, 424.6), abs=0.05)]


@pytest.mark.skipif(not os.path.exists(REAL), reason="PDF del reporte no disponible")
def test_pdf_del_reporte_tres_tuberias_sin_duplicar():
    res = rec.recognize_page(REAL, 0, utility="ALCANTARILLADO", zoom=1.0)
    pls = res.drawable
    assert len(pls) == 3                          # antes: 6 (cada tubería dos veces)
    assert len(res.walls_px) == 13
    for pl in pls:                                # cada eje va al medio de sus paredes
        assert pl.kinds[0] == "cut" and pl.kinds[-1] == "cut" or "tee" in pl.kinds
    horiz = next(pl for pl in pls if any(abs(y - 333.2) < 0.2 for _x, y in pl.pts_pdf))
    assert any(p == pytest.approx((2464.6, 334.4), abs=0.1) for p in horiz.pts_pdf)


def dashed_poly(ocg, pts, dash=9.0, gap=4.5):
    """Polilínea a trazos (el patrón sigue de un tramo al siguiente)."""
    out, carry = [], 0.0
    for a, b in zip(pts, pts[1:]):
        out += dashed(ocg, a, b, dash, gap)
    return out


def test_paredes_a_trazos_dan_un_eje_a_trazos(tmp_path):
    """ET-004 h.1: tubería existente con las dos paredes a trazos («oculta»)."""
    walls = dashed("C-STRM-PIPE", (100, 300), (500, 300)) + dashed("C-STRM-PIPE", (100, 301.2), (500, 301.2))
    res, pls = lines(sheet(tmp_path, walls), "DRENAJE")
    assert len(pls) == 1
    assert all(abs(y - 300.6) <= 0.05 for _x, y in pls[0].pts_pdf)
    assert pls[0].pts_pdf[0][0] == pytest.approx(100, abs=0.5) or pls[0].pts_pdf[-1][0] == pytest.approx(100, abs=0.5)
    assert any(w.startswith("Tuberías dibujadas con sus dos paredes: 1") for w in res.warnings)


def test_paredes_a_trazos_con_quiebre(tmp_path):
    a = [(100, 300), (400, 300), (600, 400)]
    off = 1.2 / math.cos(math.atan2(100, 200) / 2)      # paralela a inglete
    k = math.tan(math.atan2(100, 200) / 2) * 1.2
    b = [(100, 301.2), (400 - k, 301.2), (600 - 1.2 * math.sin(math.atan2(100, 200)), 400 + 1.2 * math.cos(math.atan2(100, 200)))]
    res, pls = lines(sheet(tmp_path, dashed_poly("C-STRM-PIPE", a) + dashed_poly("C-STRM-PIPE", b)), "DRENAJE")
    assert len(res.walls_px) == 2                     # un tramo recto por lado del quiebre
    assert len(pls) == 1                              # …y una sola tubería
    assert off > 1.2


def test_tapon_entre_paredes_se_omite(tmp_path):
    pdf = sheet(tmp_path, [("C-SSWR-PIPE", [(100, 200), (700, 200)], False),
                           ("C-SSWR-PIPE", [(100, 201.3), (700, 201.3)], False),
                           ("C-SSWR-PIPE", [(700, 200), (700, 201.3)], False)])     # tapón
    _res, pls = lines(pdf)
    assert len(pls) == 1 and len(pls[0].pts_pdf) == 2


def test_banda_rellena_entre_paredes(tmp_path):
    """ET-004 `C-STRM-PIPE`: cuerpo relleno (triangulado) + las dos paredes."""
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    oc = doc.add_ocg("C-STRM-PIPE")
    for y in (300.0, 301.2):
        sh = page.new_shape(); sh.draw_line((100, y), (500, y))
        sh.finish(color=(0, 0, 1), width=0.48, oc=oc, closePath=False); sh.commit()
    x = 100.0
    while x < 500:
        sh = page.new_shape()
        sh.draw_polyline([(x, 300.2), (x + 50, 300.2), (x + 50, 301.0), (x, 301.0)])
        sh.finish(color=(0, 1, 0), fill=(0, 1, 0), width=0, oc=oc, closePath=True); sh.commit()
        x += 50
    out = tmp_path / "band.pdf"; doc.save(str(out)); doc.close()
    _res, pls = lines(str(out), "DRENAJE")
    assert len(pls) == 1
    assert all(abs(y - 300.6) <= 0.05 for _x, y in pls[0].pts_pdf)


def test_otra_tuberia_que_cruza_un_hueco_no_es_letra(tmp_path):
    """ET-004 h.1: la pared de otra tubería cruza un hueco de la pared a trazos junto
    al buzón; una letra es un trazo chico, una pared de 50 pt no."""
    walls = dashed("C-STRM-PIPE", (100, 300), (500, 300)) + dashed("C-STRM-PIPE", (100, 301.2), (500, 301.2))
    cross = [("C-STRM-PIPE", [(108, 280), (115, 330)], False)]
    res, _pls = lines(sheet(tmp_path, walls + cross), "DRENAJE")
    assert len(res.walls_px) == 1


# La regla vale en TODAS las utilidades (pedido del usuario 2026-10-02): mismas
# formas en una capa de línea de cada una.
LINE_LAYER = {"ELECTRICO": "C-ELEC-UNGD-N", "DRENAJE": "C-STRM-PIPE", "AGUA": "C-WATR-PIPE",
              "ALCANTARILLADO": "C-SSWR-PIPE", "GAS": "C-NGAS-PIPE", "TELECOM": "C-TELE-PIPE"}


def test_hay_capa_de_prueba_para_cada_utilidad():
    assert set(LINE_LAYER) == set(rec.SUPPORTED_UTILITIES)
    for u, ocg in LINE_LAYER.items():
        assert rec.classify_ocg(ocg, u) == rec.utility_line_kind(u)


@pytest.mark.parametrize("utility", sorted(LINE_LAYER))
def test_paredes_en_todas_las_utilidades(tmp_path, utility):
    ocg = LINE_LAYER[utility]
    pdf = sheet(tmp_path, [(ocg, [(100, 200), (600, 200), (600, 500)], False),
                           (ocg, [(100, 201.3), (598.7, 201.3), (598.7, 500)], False)])
    res, pls = lines(pdf, utility)
    assert len(pls) == 1
    assert pls[0].pts_pdf[0] == pytest.approx((100, 200.65), abs=0.05)
    assert min(pls[0].pts_pdf, key=lambda p: math.dist(p, (600, 200))) == pytest.approx((599.35, 200.65), abs=0.05)
    assert any(w.startswith("Tuberías dibujadas con sus dos paredes: 1") for w in res.warnings)


@pytest.mark.parametrize("utility", sorted(LINE_LAYER))
def test_paredes_y_eje_en_todas_las_utilidades(tmp_path, utility):
    ocg = LINE_LAYER[utility]
    pdf = sheet(tmp_path, [(ocg, [(100, 198.5), (700, 198.5)], False),
                           (ocg, [(100, 201.5), (700, 201.5)], False),
                           (ocg, [(100, 200), (700, 200)], False)])
    res, pls = lines(pdf, utility)
    assert len(pls) == 1
    assert all(abs(y - 200) <= 0.05 for _x, y in pls[0].pts_pdf)
    assert any(w.startswith("Tuberías dibujadas con paredes y eje: 1") for w in res.warnings)


@pytest.mark.parametrize("utility", sorted(LINE_LAYER))
def test_paredes_a_trazos_en_todas_las_utilidades(tmp_path, utility):
    ocg = LINE_LAYER[utility]
    walls = dashed(ocg, (100, 300), (500, 300)) + dashed(ocg, (100, 301.2), (500, 301.2))
    res, pls = lines(sheet(tmp_path, walls), utility)
    assert len(pls) == 1
    assert all(abs(y - 300.6) <= 0.05 for _x, y in pls[0].pts_pdf)


@pytest.mark.parametrize("utility", sorted(LINE_LAYER))
def test_contorno_cerrado_en_todas_las_utilidades(tmp_path, utility):
    """Paredes + tapones en UN rectángulo cerrado delgado (DU06 h.4 alcantarillado): su eje."""
    ocg = LINE_LAYER[utility]
    pdf = sheet(tmp_path, [(ocg, [(100, 200), (500, 200), (500, 203.6), (100, 203.6)], True)])
    res, pls = lines(pdf, utility)
    assert len(pls) == 1
    assert all(abs(y - 201.8) <= 0.05 for _x, y in pls[0].pts_pdf)
    assert any(w.startswith("Tuberías dibujadas como contorno") for w in res.warnings)
