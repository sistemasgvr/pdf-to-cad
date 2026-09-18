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
    clip = C.trim_border_lines(page, [0.0, 0.0, 308 / 400, 260 / 300])
    assert math.isclose(clip[2] * 400, 300 - 1.5, abs_tol=1e-6)   # x1 = línea − (ancho/2 + 1)
    assert math.isclose(clip[3] * 300, 250 - 1.25, abs_tol=1e-6)
    assert clip[0] == 0.0 and clip[1] == 0.0
    # sin líneas de borde → el clip no cambia
    assert C.trim_border_lines(page, [0.0, 0.0, 0.5, 0.5]) == [0.0, 0.0, 0.5, 0.5]
    # hoja girada 90°: el mismo recorte, expresado en coords visibles
    page.set_rotation(90)
    Wv, Hv = page.rect.width, page.rect.height        # 300 × 400
    clip_r = C.trim_border_lines(page, [(300 - 260) / Wv, 0.0, 1.0, 308 / Hv])
    assert math.isclose(clip_r[3] * Hv, 300 - 1.5, abs_tol=1e-6)
    assert math.isclose(clip_r[0] * Wv, 300 - (250 - 1.25), abs_tol=1e-6)


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
    clip = C.trim_border_lines(page, [0.0, 0.0, 310 / 400, 1.0])
    assert math.isclose(clip[2] * 400, 300 - 2.0, abs_tol=1e-6)   # columna más interior (300) − (ancho/2 + 1)
    # pocos guiones (20 %) no son una línea de borde
    doc2 = fitz.open(); pg2 = doc2.new_page(width=400, height=300)
    pg2.draw_line((300, 20), (300, 80), color=(0, 0, 0), width=2.0)
    assert C.trim_border_lines(pg2, [0.0, 0.0, 310 / 400, 1.0]) == [0.0, 0.0, 0.775, 1.0]
