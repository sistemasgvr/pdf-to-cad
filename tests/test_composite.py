"""Hoja compuesta (composite.py): transformaciones, imán y materialización.

PDFs sintéticos con capas OCG; sin Qt.
"""
import math
import os
import sys

import fitz
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import composite as C  # noqa: E402
import pdf_layers  # noqa: E402


def _src_doc(rotation=0, layer="C-ELEC-UNGD-E"):
    """Hoja 200x100 con dos líneas en una capa OCG y una tercera sin capa."""
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    ocg = doc.add_ocg(layer, on=True)
    other = doc.add_ocg("G-ANNO-TEXT", on=True)
    page.draw_line((10, 10), (190, 10), color=(1, 0, 0), oc=ocg)
    page.draw_line((10, 10), (10, 90), color=(0, 0, 1), oc=ocg)
    page.draw_line((50, 50), (150, 50), color=(0, 1, 0), oc=other)
    page.insert_text((60, 80), 'SCALE: 1"=20\'', fontsize=8)
    if rotation:
        page.set_rotation(rotation)
    return doc


def _reopen(doc):
    data = doc.tobytes()
    return fitz.open(stream=data, filetype="pdf")


def _lines(page):
    out = {}
    for d in page.get_drawings():
        it = d["items"][0]
        key = "rojo" if d["color"][0] > 0.5 else "azul" if d["color"][2] > 0.5 else "verde"
        out[key] = ((it[1].x, it[1].y), (it[2].x, it[2].y))
    return out


@pytest.mark.parametrize("rotation", [0, 90, 30, 180])
def test_piece_map_coincide_con_show_pdf_page(rotation):
    src = _src_doc()
    piece = C.Piece(0, 0, [0, 0, 1, 1], x=15, y=25, rotation=rotation, src_scale=20 / 72)
    comp = C.Composite([piece])
    dst = _reopen(C.build_document(comp, [src]))
    fn = C.piece_map(piece, (200, 100), comp.target_scale())
    w, h, dx, dy = C.sheet_geometry(comp, lambda p: (200, 100))
    got = _lines(dst[0])
    for a, b, key in (((10, 10), (190, 10), "rojo"), ((10, 10), (10, 90), "azul")):
        for p, q in zip((a, b), got[key]):
            ex, ey = fn(*p)
            assert math.isclose(ex + dx, q[0], abs_tol=0.05), (rotation, key, p, q)
            assert math.isclose(ey + dy, q[1], abs_tol=0.05), (rotation, key, p, q)


def test_escala_distinta_agranda_la_pieza():
    src = _src_doc()
    # hoja origen a 1"=40' en una compuesta a 1"=20' → factor 2
    piece = C.Piece(0, 0, [0, 0, 1, 1], src_scale=40 / 72)
    comp = C.Composite([piece], scale_ft_per_pt=20 / 72)
    assert C.piece_size(piece, (200, 100), comp.target_scale()) == (400, 200)
    dst = _reopen(C.build_document(comp, [src]))
    (a, b) = _lines(dst[0])["rojo"]
    assert math.isclose(b[0] - a[0], 360, abs_tol=0.05)


def test_clip_parcial_recorta_los_vectores():
    src = _src_doc()
    piece = C.Piece(0, 0, [0, 0, 0.5, 1])  # mitad izquierda: la roja se corta en x=100
    dst = _reopen(C.build_document(C.Composite([piece]), [src]))
    sys.path.insert(0, os.path.join(ROOT, "app"))
    import recognition as rec
    lp, _, counts, _ = rec.gather_paths(dst[0], lambda o: "elec_ungd" if "ELEC" in o else None)
    xs = [q.x if hasattr(q, "x") else q[0] for p in lp for it in p["items"] for q in (it[1], it[2])]
    assert max(xs) <= C.MARGIN_PT + 100 + 0.05
    assert counts and all("ELEC" in k for k in counts)


def test_capas_ocg_se_conservan_y_se_pueden_apagar():
    src = _src_doc()
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 0, [0, 0, 1, 1], x=300)])
    dst = _reopen(C.build_document(comp, [src]))
    names = {c["text"] for c in dst.layer_ui_configs()}
    assert names == {"C-ELEC-UNGD-E", "G-ANNO-TEXT"}
    layers = {d.get("layer") for d in dst[0].get_drawings(extended=True) if d.get("type") != "clip"}
    assert "C-ELEC-UNGD-E" in layers and "G-ANNO-TEXT" in layers
    assert len(dst[0].get_drawings()) == 6           # 2 piezas × 3 líneas
    pdf_layers.set_hidden(dst, {"C-ELEC-UNGD-E"})
    assert len(dst[0].get_drawings()) == 2           # solo la verde de cada pieza
    assert "SCALE" in dst[0].get_text()              # el texto viaja con la pieza


def test_capas_ocultas_por_origen_llegan_apagadas():
    a, b = _src_doc(), _src_doc()
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(1, 0, [0, 0, 1, 1], x=300)])
    dst = _reopen(C.build_document(comp, [a, b], {"1": ["C-ELEC-UNGD-E"]}))
    assert len(dst[0].get_drawings()) == 4           # pieza 0 completa + solo verde de la 1
    assert pdf_layers.hidden_layers(dst) == {"C-ELEC-UNGD-E"}


def test_hoja_origen_rotada():
    src = _src_doc(rotation=90)                      # visible: 100 de ancho × 200 de alto
    page = src[0]
    assert (page.rect.width, page.rect.height) == (100, 200)
    piece = C.Piece(0, 0, [0, 0, 1, 1])
    comp = C.Composite([piece])
    dst = _reopen(C.build_document(comp, [src]))
    assert math.isclose(dst[0].rect.width, 100 + 2 * C.MARGIN_PT)
    assert math.isclose(dst[0].rect.height, 200 + 2 * C.MARGIN_PT)
    # la línea roja (borde superior del original) queda vertical en la hoja visible
    a, b = _lines(dst[0])["rojo"]
    assert math.isclose(a[0], b[0], abs_tol=0.05)


def test_edge_points_en_el_borde_del_clip():
    src = _src_doc()
    pts = C.edge_points(src[0], [0, 0, 0.5, 1])      # x=100 corta la roja (y=10) y la verde (y=50)
    assert len(pts) == 2
    assert sorted(round(y, 3) for _, y in pts) == [10.0, 50.0]
    assert all(math.isclose(x, 100.0, abs_tol=1e-6) for x, _ in pts)


def test_magnet_delta_gana_el_grupo_coherente():
    moving = [(0, 0), (0, 10), (0, 20)]
    static = [(2.0, 0.5), (2.0, 10.5), (2.0, 20.5), (-5.0, 6.0)]   # el último es espurio
    d = C.magnet_delta(moving, static)
    assert d is not None
    assert math.isclose(d[0], 2.0) and math.isclose(d[1], 0.5)
    assert C.magnet_delta(moving, [(50, 50)]) is None
    assert C.magnet_delta([], static) is None


def test_roundtrip_dict_y_single_full_page():
    comp = C.Composite([C.Piece(0, 3, [0, 0, 1, 1], src_scale=20 / 72)])
    assert comp.is_single_full_page()
    comp2 = C.Composite.from_dict(comp.to_dict())
    assert comp2.to_dict() == comp.to_dict()
    comp.pieces[0].rotation = 90
    assert not comp.is_single_full_page()
    assert C.Composite.from_dict(None) is None
    assert C.Piece.from_dict({"clip": "basura"}).clip == [0.0, 0.0, 1.0, 1.0]


def _dashed(page, a, b, ocg, dash=6.0, gap=3.0):
    ax, ay = a; bx, by = b
    L = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L, (by - ay) / L
    t = 0.0
    while t < L:
        e = min(L, t + dash)
        page.draw_line((ax + ux * t, ay + uy * t), (ax + ux * e, ay + uy * e), color=(0, 0, 0), oc=ocg)
        t = e + gap


def _gap_pdf():
    """Dos hojas 300x200 con una eléctrica horizontal (y=100) y un bordillo
    (y=150, capa C-ROAD-CURB): en ambas la línea muere en x=300 / nace en x=0."""
    doc = fitz.open()
    elec = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    curb = doc.add_ocg("C-ROAD-CURB", on=True)
    p1 = doc.new_page(width=300, height=200)
    _dashed(p1, (20, 100), (300, 100), elec)
    p1.draw_line((20, 150), (300, 150), color=(0, 0, 1), oc=curb)
    p2 = doc.new_page(width=300, height=200)
    _dashed(p2, (0, 100), (280, 100), elec)
    p2.draw_line((0, 150), (280, 150), color=(0, 0, 1), oc=curb)
    return doc


def test_edge_anchors_tienen_direccion_y_capa():
    doc = _gap_pdf()
    # el último guión (1 pt) no cuenta; el anclaje es el guión real anterior (x=296)
    right = [a for a in C.edge_anchors(doc[0], [0, 0, 1, 1]) if a.x > 290]
    assert {a.layer for a in right} == {"C-ELEC-UNGD-E", "C-ROAD-CURB"}
    assert all(math.isclose(a.ux, 1.0, abs_tol=1e-6) and abs(a.uy) < 1e-6 for a in right)
    left = [a for a in C.edge_anchors(doc[1], [0, 0, 1, 1]) if a.x < 1]
    assert all(math.isclose(a.ux, -1.0, abs_tol=1e-6) for a in left)
    # trazo que CRUZA el borde: el anclaje es el corte y la dirección sale hacia afuera
    doc2 = fitz.open(); pg = doc2.new_page(width=100, height=100)
    pg.draw_line((50, 50), (150, 150), color=(0, 0, 0))
    (an,) = C.edge_anchors(pg, [0, 0, 1, 1])
    assert math.isclose(an.x, 100) and math.isclose(an.y, 100)
    assert math.isclose(an.ux, math.sqrt(0.5), abs_tol=1e-6) and math.isclose(an.uy, math.sqrt(0.5), abs_tol=1e-6)


def test_iman_colineal_alinea_con_hueco():
    doc = _gap_pdf()
    pa = C.Piece(0, 0, [0, 0, 1, 1]); pb = C.Piece(0, 1, [0, 0, 1, 1], x=340, y=3.0)   # hueco 40, desalineada 3
    comp = C.Composite([pa, pb])
    A = C.map_anchors(pa, (300, 200), comp.target_scale(), C.edge_anchors(doc[0], pa.clip))
    B = C.map_anchors(pb, (300, 200), comp.target_scale(), C.edge_anchors(doc[1], pb.clip))
    assert C.magnet_delta([b.xy for b in B], [a.xy for a in A]) is None      # no coinciden: hay hueco
    d = C.collinear_delta(B, A)
    assert d is not None and math.isclose(d[0], 0.0, abs_tol=1e-6) and math.isclose(d[1], -3.0, abs_tol=1e-6)
    assert C.collinear_delta(B, A, max_gap=10.0) is None                     # hueco mayor que el permitido


def test_puentes_unen_extremos_y_reconocen_una_ruta():
    doc = _gap_pdf()
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1], x=340)])
    bridges = C.compute_bridges(comp, [doc])
    assert len(bridges) == 2
    by_layer = {b.layer_a: b for b in bridges}
    assert set(by_layer) == {"C-ELEC-UNGD-E", "C-ROAD-CURB"}
    br = by_layer["C-ELEC-UNGD-E"]
    assert math.isclose(br.a[0], 296) and math.isclose(br.b[0], 340) and math.isclose(br.a[1], 100)
    assert math.isclose(br.length, 44)
    # capas distintas nunca se emparejan aunque estén enfrentadas
    comp.bridge_max_pt = 10.0
    assert C.compute_bridges(comp, [doc]) == []
    comp.bridge_max_pt = C.BRIDGE_MAX_PT
    comp.bridges = False
    assert C.compute_bridges(comp, [doc]) == []
    comp.bridges = True
    # materializar con puentes → el puente está en la capa eléctrica y la ruta es una sola
    import recognition as rec
    dst = _reopen(C.build_document(comp, [doc], None, bridges))
    elec = [d for d in dst[0].get_drawings(extended=True) if d.get("layer") == "C-ELEC-UNGD-E"]
    xs = sorted(x for d in elec for it in d["items"] for q in (it[1], it[2]) for x in [q.x])
    assert xs[0] < C.MARGIN_PT + 21 and xs[-1] > C.MARGIN_PT + 340 + 279
    res = rec.recognize_page(None, 0, doc=dst, zoom=1.0, scale_ft_per_pt=comp.target_scale())
    assert len(res.drawable) == 1
    pdf_layers.set_hidden(dst, {"C-ELEC-UNGD-E"})           # el puente se apaga con su capa
    assert not [d for d in dst[0].get_drawings() if abs(d["rect"].y0 - (100 + C.MARGIN_PT)) < 0.01]
    # sin puentes: dos rutas
    dst2 = _reopen(C.build_document(comp, [doc]))
    assert len(rec.recognize_page(None, 0, doc=dst2, zoom=1.0).drawable) == 2


def test_trim_border_lines_deja_fuera_la_match_line():
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    ocg = doc.add_ocg("C-ANNO-TEXT-N", on=True)
    page.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=1.0, oc=ocg)   # match line vertical
    page.draw_line((20, 250), (380, 250), color=(0, 0, 0), width=0.5)           # línea de borde inferior
    page.draw_line((20, 100), (380, 100), color=(0, 0, 1))                       # línea interior larga: no cuenta
    page.draw_line((310, 50), (310, 80), color=(0, 0, 0))                        # corta: no cuenta
    # área del usuario: llega hasta x=308 (la match line queda 8 pt por dentro) y hasta y=260
    clip, covers = C.trim_border(page, [0.0, 0.0, 308 / 400, 260 / 300])
    assert math.isclose(clip[2] * 400, 300.0, abs_tol=1e-6)       # x1 = CENTRO de la línea
    assert math.isclose(clip[3] * 300, 250.0, abs_tol=1e-6)
    assert clip[0] == 0.0 and clip[1] == 0.0
    # franja blanca por lado = ancho/2 + COVER_PAD
    assert math.isclose(covers["right"], 0.5 + C.COVER_PAD_PT) and math.isclose(covers["bottom"], 0.25 + C.COVER_PAD_PT)
    assert set(covers) == {"right", "bottom"}
    # sin líneas de borde → el clip no cambia y no hay franjas
    assert C.trim_border(page, [0.0, 0.0, 0.5, 0.5]) == ([0.0, 0.0, 0.5, 0.5], {})
    # hoja girada 90°: el mismo recorte, expresado en coords visibles; los lados giran con la hoja
    page.set_rotation(90)
    Wv, Hv = page.rect.width, page.rect.height        # 300 × 400
    clip_r, covers_r = C.trim_border(page, [(300 - 260) / Wv, 0.0, 1.0, 308 / Hv])
    assert math.isclose(clip_r[3] * Hv, 300.0, abs_tol=1e-6)
    assert math.isclose(clip_r[0] * Wv, 300 - 250, abs_tol=1e-6)
    assert set(covers_r) == {"bottom", "left"}


def test_anclajes_ignoran_letras_y_trazos_minusculos():
    doc = fitz.open(); page = doc.new_page(width=200, height=100)
    page.draw_line((10, 50), (200, 50), color=(0, 0, 0))                 # línea real → 1 anclaje
    for i in range(8):                                                   # "letra" de 8 trazos de 1.5 pt en el borde
        page.draw_line((198.5 + (i % 2), 20 + i), (200, 20 + i), color=(0, 0, 0))
    page.draw_line((199, 80), (200, 80), color=(0, 0, 0))               # trazo de 1 pt → fuera
    anchors = C.edge_anchors(page, [0, 0, 1, 1])
    assert [round(a.y) for a in anchors] == [50]


def test_trim_border_lines_match_line_discontinua_y_gruesa():
    doc = fitz.open(); page = doc.new_page(width=400, height=300)
    # match line a guiones gruesos (2 pt), en dos columnas a 1 pt, cubriendo ~70 % del lado
    for i, y in enumerate(range(20, 280, 40)):
        x = 300.0 + (i % 2)
        page.draw_line((x, y), (x, y + 28), color=(0, 0, 0), width=2.0)
    page.draw_line((20, 100), (380, 100), color=(0, 0, 1))
    clip, covers = C.trim_border(page, [0.0, 0.0, 310 / 400, 1.0])
    mean = (4 * 300 + 3 * 301) / 7                                  # centro medio de las dos columnas
    assert math.isclose(clip[2] * 400, mean, abs_tol=1e-3)     # (fitz.Point es float32)
    # la franja cubre la deriva (columna interior 300 queda mean−300 más adentro) + ancho/2 + pad
    assert math.isclose(covers["right"], (mean - 300) + 1.0 + C.COVER_PAD_PT, abs_tol=1e-3)
    # pocos guiones (20 %) no son una línea de borde
    doc2 = fitz.open(); pg2 = doc2.new_page(width=400, height=300)
    pg2.draw_line((300, 20), (300, 80), color=(0, 0, 0), width=2.0)
    assert C.trim_border_lines(pg2, [0.0, 0.0, 310 / 400, 1.0]) == [0.0, 0.0, 0.775, 1.0]


def test_guide_lines_y_snap_edge():
    doc = fitz.open(); page = doc.new_page(width=400, height=300)
    page.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=1.0)          # vertical continua
    for y in range(20, 280, 40):                                                 # vertical a guiones (col. 100/101)
        page.draw_line((100 + (y // 40) % 2, y), (100 + (y // 40) % 2, y + 28), color=(0, 0, 0))
    page.draw_line((20, 250), (380, 250), color=(0, 0, 0))                       # horizontal
    page.draw_line((200, 100), (230, 100), color=(0, 0, 0))                      # corta: no es guía
    for i in range(6):                                                           # letra: trazos de 1.5 pt
        page.draw_line((50, 150 + i), (51.5, 150 + i), color=(0, 0, 0))
    g = C.guide_lines(page)
    assert [round(x) for x, *_ in g["x"]] == [100, 300]      # 7 guiones: 4 en x=100, 3 en x=101 → media 100.4
    assert [round(y, 1) for y, *_ in g["y"]] == [250.0]
    # imán: el lado derecho en x=304 salta a 300; en x=330 no (fuera de tolerancia)
    assert C.snap_edge(g["x"], 304.0, 0.0, 300.0, 8.0)[0] == 300.0
    # entre dos guías a tiro gana la más larga aunque esté un poco más lejos
    page.draw_line((306, 120), (306, 180), color=(0, 0, 0))                     # corta (60 pt) en x=306
    g = C.guide_lines(page)
    assert C.snap_edge(g["x"], 307.0, 0.0, 300.0, 8.0)[0] == 300.0
    assert C.snap_edge(g["x"], 330.0, 0.0, 300.0, 8.0) is None
    # la extensión debe solapar: un lado entre y=285..295 no ve la guía (termina en 280)
    assert C.snap_edge(g["x"], 301.0, 285.0, 295.0, 8.0) is None
    # hoja girada: la guía vertical pasa a horizontal en coords visibles
    page.set_rotation(90)
    g2 = C.guide_lines(page)
    assert [round(y) for y, *_ in g2["y"]] == [100, 300, 306] and len(g2["x"]) == 1


def test_covers_se_materializan_como_franjas_blancas_sin_perder_vectores():
    doc = fitz.open(); page = doc.new_page(width=400, height=300)
    ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page.draw_line((20, 100), (380, 100), color=(0, 0, 0), oc=ocg)             # utilidad que cruza la match line
    page.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=2.0)          # match line
    clip, covers = C.trim_border(page, [0.0, 0.0, 310 / 400, 1.0])
    piece = C.Piece(0, 0, clip, covers=covers)
    comp = C.Composite([piece])
    rects = C.cover_rects(piece, (400, 300))
    assert len(rects) == 1 and math.isclose(rects[0][2], 300.0 + C.COVER_OUT_PT) and math.isclose(rects[0][0], 300.0 - covers["right"])
    dst = _reopen(C.build_document(comp, [doc]))
    draws = dst[0].get_drawings()
    fills = [d for d in draws if d.get("type") == "f" and d.get("fill") == (1.0, 1.0, 1.0)]
    assert len(fills) == 1                                                  # la franja blanca
    elec = [d for d in dst[0].get_drawings(extended=True) if d.get("layer") == "C-ELEC-UNGD-E"]
    assert elec and max(q.x for d in elec for it in d["items"] for q in (it[1], it[2])) >= C.MARGIN_PT + 300 - 0.01
    # round-trip del modelo
    assert C.Piece.from_dict(piece.to_dict()).covers == covers


@pytest.mark.parametrize("rotation", [0, 90, 37.5, 270])
def test_piece_unmap_es_inversa_de_piece_map(rotation):
    piece = C.Piece(0, 0, [0.1, 0.2, 0.8, 0.9], x=50, y=70, rotation=rotation, src_scale=40 / 72)
    fn = C.piece_map(piece, (600, 400), 20 / 72)
    inv = C.piece_unmap(piece, (600, 400), 20 / 72)
    for x, y in ((60, 80), (300, 200), (480, 360)):
        X, Y = fn(x, y)
        bx, by = inv(X, Y)
        assert math.isclose(bx, x, abs_tol=1e-9) and math.isclose(by, y, abs_tol=1e-9)


def test_edge_snap_delta_borde_con_borde():
    static = [(0.0, 0.0, 300.0, 200.0)]
    assert C.edge_snap_delta((303.0, 10.0, 603.0, 210.0), static, 8.0) == (-3.0, 0.0)   # costura vertical
    assert C.edge_snap_delta((-297.0, 10.0, 3.0, 210.0), static, 8.0) == (-3.0, 0.0)
    assert C.edge_snap_delta((20.0, 204.0, 320.0, 404.0), static, 8.0) == (0.0, -4.0)   # costura horizontal
    assert C.edge_snap_delta((320.0, 0.0, 620.0, 200.0), static, 8.0) is None            # lejos
    assert C.edge_snap_delta((303.0, 300.0, 603.0, 500.0), static, 8.0) is None          # sin solape vertical


def test_anclajes_con_franja_quedan_en_el_borde_interior_y_los_puentes_la_cruzan():
    doc = fitz.open(); page = doc.new_page(width=400, height=300)
    ocg = doc.add_ocg("C-ROAD-CURB", on=True)
    page.draw_line((20, 100), (380, 100), color=(0, 0, 0), oc=ocg)             # línea que cruza la match line
    page.draw_line((300, 20), (300, 280), color=(0, 0, 0), width=2.0)          # match line
    clip, covers = C.trim_border(page, [0.0, 0.0, 310 / 400, 1.0])
    anchors = C.edge_anchors(page, clip, insets=covers)
    (an,) = [a for a in anchors if abs(a.y - 100) < 0.1 and a.ux > 0.5]
    assert math.isclose(an.x, 300 - covers["right"], abs_tol=1e-3)               # borde interior de la franja
    # dos piezas de la misma hoja pegadas borde con borde: el puente mide 2 franjas
    a = C.Piece(0, 0, clip, covers=covers)
    clip_b, covers_b = C.trim_border(page, [290 / 400, 0.0, 1.0, 1.0])
    b = C.Piece(0, 0, clip_b, covers=covers_b, x=(clip[2] - clip[0]) * 400)
    comp = C.Composite([a, b])
    bridges = C.compute_bridges(comp, [doc])
    assert len(bridges) == 1 and math.isclose(bridges[0].length, covers["right"] + covers_b["left"], abs_tol=1e-3)
    # materializar: la línea es continua a través de la costura (el puente va sobre las franjas)
    dst = _reopen(C.build_document(comp, [doc], None, bridges))
    pix = dst[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(C.MARGIN_PT + 290, C.MARGIN_PT + 99.5,
                                                                    C.MARGIN_PT + 310, C.MARGIN_PT + 100.5))
    import numpy as np
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).mean(axis=2)
    assert arr.min(axis=0).max() < 160                                            # ninguna columna en blanco


def test_refine_delta_fija_los_dos_ejes_con_lineas_inclinadas():
    # extremos de A (estáticos) y B (móviles) desplazados (dx, dy) = (0.3, −0.2); líneas a 0°, 45° y 90°
    import math as _m
    def anc(x, y, ang, flip=False):
        ux, uy = _m.cos(_m.radians(ang)), _m.sin(_m.radians(ang))
        if flip: ux, uy = -ux, -uy
        return C.Anchor(x, y, ux, uy, "L")
    static = [anc(100, 10, 0), anc(100, 50, 45), anc(100, 90, 0), anc(120, 0, 90)]
    dx, dy = 0.3, -0.2
    moving = [C.Anchor(a.x + dx, a.y + dy, -a.ux, -a.uy, "L") for a in static]
    fx, fy = C.refine_delta(moving, static, 1.5, 200)
    assert math.isclose(fx, -dx, abs_tol=1e-6) and math.isclose(fy, -dy, abs_tol=1e-6)
    # solo horizontales: y determinado, x no
    static_h = [anc(100, 10, 0), anc(100, 50, 0), anc(100, 90, 0)]
    moving_h = [C.Anchor(a.x + dx, a.y + dy, -a.ux, -a.uy, "L") for a in static_h]
    fx, fy = C.refine_delta(moving_h, static_h, 1.5, 200)
    assert fx is None and math.isclose(fy, -dy, abs_tol=1e-6)


def test_puente_prolonga_cada_linea_por_su_recta_hasta_el_borde():
    a = C.Anchor(97.0, 50.0, 1.0, 0.0, "L"); b = C.Anchor(103.0, 50.2, -1.0, 0.0, "L")
    br = C.Bridge(0, a.xy, 1, b.xy, "L", "L", ua=(a.ux, a.uy), ub=(b.ux, b.uy))
    pts = br.polyline((0, 0, 100, 100), (100, 0, 200, 100))
    assert pts == [(97.0, 50.0), (100.0, 50.0), (100.0, 50.2), (103.0, 50.2)]   # recto hasta el borde, escalón en la costura
    # línea a 45°: sale del rectángulo por su recta
    a = C.Anchor(97.0, 50.0, math.sqrt(0.5), math.sqrt(0.5), "L")
    br = C.Bridge(0, a.xy, 1, (103.0, 56.0), "L", "L", ua=(a.ux, a.uy), ub=(-a.ux, -a.uy))
    pts = br.polyline((0, 0, 100, 100), (100, 0, 200, 100))
    assert math.isclose(pts[1][0], 100.0) and math.isclose(pts[1][1], 53.0)
    # patrón de guiones continuo a lo largo de la polilínea
    segs = C.bridge_segments_poly([(0, 0), (10, 0), (10, 10)], dash=4.0, gap_ratio=0.5)
    total = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in segs)
    assert 20 * (4 / 6) - 4 <= total <= 20 * (4 / 6) + 4 and len(segs) >= 3


def test_piece_layout_para_el_minimapa():
    comp = C.Composite([C.Piece(0, 13, [0, 0, 1, 1]), C.Piece(0, 14, [0, 0, 1, 1], x=0, y=210)])
    lay = C.piece_layout(comp, lambda p: (300, 200))
    assert [lbl for _, lbl in lay] == ["Hoja 14", "Hoja 15"]
    (r1, _), (r2, _) = lay
    assert r1 == (C.MARGIN_PT, C.MARGIN_PT, C.MARGIN_PT + 300, C.MARGIN_PT + 200)
    assert math.isclose(r2[1], C.MARGIN_PT + 210)                     # una debajo de la otra
    comp.pieces[1].source = 1
    lay = C.piece_layout(comp, lambda p: (300, 200), ["a.pdf", "b.pdf"])
    assert [lbl for _, lbl in lay] == ["a.pdf · Hoja 14", "b.pdf · Hoja 15"]
