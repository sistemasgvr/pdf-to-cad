"""Costura exacta entre hojas contiguas (composite_seam + trim_border).

Dos hojas sintéticas como el DU06 13→14: match line GRUESA y algo inclinada,
cotas FINAS en espejo a 20/40/60 pt por fuera de ella, el dibujo de cada viewport
pasa unos pt de la línea (vectores idénticos en las dos hojas) y símbolos
repetidos que dan picos falsos. La segunda hoja está trasladada T respecto de
la primera."""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")

import composite as C  # noqa: E402
import composite_seam as S  # noqa: E402

T = (-200.0, 12.0)            # hoja B = hoja A + T
ML_X = 300.0                  # match line en la hoja A (en y = 150)
TILT = 0.004                  # x = ML_X + TILT·(y − 150): ~0.23°, como el DU06


def _ml(y: float) -> float:
    return ML_X + TILT * (y - 150.0)


def _clip_seg(a, b, xmin, xmax):
    """Recorta el segmento a la franja xmin ≤ x ≤ xmax (como el viewport del plano)."""
    (ax, ay), (bx, by) = a, b
    if ax > bx:
        (ax, ay), (bx, by) = (bx, by), (ax, ay)
    if bx < xmin or ax > xmax:
        return None
    k = (by - ay) / (bx - ax) if bx != ax else 0.0
    if ax < xmin:
        ay += k * (xmin - ax); ax = xmin
    if bx > xmax:
        by -= k * (bx - xmax); bx = xmax
    return (ax, ay), (bx, by)


def _world():
    """Dibujo del modelo (coords de la hoja A) alrededor de la costura."""
    segs = []
    for k in range(4):                                     # diagonales a 45° que cruzan la costura
        y0 = 90.0 + 35.0 * k
        segs.append(("V-SITE", (240.0, y0 + 60.0), (330.0, y0 - 30.0)))
    for y in (70.0, 205.0):                                # bordes de vía horizontales
        segs.append(("C-ROAD", (200.0, y), (360.0, y)))
    for k in range(6):                                     # detalles enteros junto a la costura
        segs.append(("C-ALGN", (285.0 + 2 * k, 100.0 + 17 * k), (292.0 + 3 * k, 108.0 + 17 * k)))
        segs.append(("C-WATR", (304.0 - k, 180.0 + 5 * k), (309.0 - k, 176.0 + 5 * k)))
    for k in range(10):                                    # símbolo repetido (parquímetros)
        segs.append(("V-PKNG", (262.0 + 12.6 * k, 225.0), (262.0 + 12.6 * k, 231.0)))
    return segs


def _sheet(doc, ocgs, shift, x_lo, x_hi, ml_x, dims_dir):
    page = doc.new_page(width=400, height=300)
    sx, sy = shift
    for layer, a, b in _world():
        a = (a[0] + sx, a[1] + sy); b = (b[0] + sx, b[1] + sy)
        c = _clip_seg(a, b, x_lo, x_hi)
        if c:
            page.draw_line(c[0], c[1], color=(0, 0, 0), width=0.72, oc=ocgs[layer])
    # match line gruesa a guiones, inclinada
    y = 40.0 + sy
    while y < 262.0 + sy:
        y1 = min(y + 36.0, 262.0 + sy)
        page.draw_line((ml_x(y), y), (ml_x(y1), y1), color=(0, 0, 0), width=1.98, oc=ocgs["C-ANNO"])
        y = y1 + 18.0
    # cotas finas en espejo, por FUERA de la match line
    for k in (1, 2, 3):
        x = ml_x(150.0 + sy) + dims_dir * 20.0 * k
        page.draw_line((x, 60.0 + sy), (x, 240.0 + sy), color=(0, 0, 0), width=0.72, oc=ocgs["C-ANNO"])
    page.insert_text((20, 290), "SCALE: 1\"=20'", fontsize=8)
    return page


def _two_sheets():
    doc = fitz.open()
    ocgs = {n: doc.add_ocg(n, on=True) for n in ("V-SITE", "C-ROAD", "C-ALGN", "C-WATR", "V-PKNG", "C-ANNO")}
    # A: el viewport llega 16 pt más allá de la match line; B empieza 12 pt antes
    _sheet(doc, ocgs, (0.0, 0.0), 20.0, _ml(150) + 16.0, _ml, +1)
    _sheet(doc, ocgs, T, _ml(150) + T[0] - 12.0, 380.0, lambda y: _ml(y - T[1]) + T[0], -1)
    return doc


def test_seam_rule_elige_la_match_line_gruesa_y_su_inclinacion():
    doc = _two_sheets()
    lines = S.page_lines(doc[0])
    # el lado quedó sobre la cota fina (x=320): igual gana la match line gruesa
    rule = S.seam_rule(lines, (150.0, 40.0, 320.0, 262.0), "right")
    assert rule is not None and math.isclose(rule.width, 1.98, abs_tol=0.01)
    assert abs(rule.at(150.0) - ML_X) < 0.05 and abs(rule.b - TILT) < 5e-4
    rule_b = S.seam_rule(S.page_lines(doc[1]), (96.0, 52.0, 250.0, 274.0), "left")
    assert S.rules_match(rule, rule_b)
    assert abs(S.rule_across(rule, rule_b, 150.0, T[1]) - T[0]) < 0.05


def test_votos_de_vectores_identicos_dan_la_traslacion_exacta():
    doc = _two_sheets()
    ra = (150.0, 40.0, 300.0, 262.0); rb = (100.0, 52.0, 250.0, 274.0)
    va = S.band_segments(S.page_lines(doc[0]), ra, "right")
    vb = S.band_segments(S.page_lines(doc[1]), rb, "left")
    votes = S.seam_votes(va, vb)
    found = S.translation_from_votes(votes, 1, T[0], T[1] + 30.0, C.SEAM_ALONG_TOL_PT)
    assert found is not None
    assert abs(found[0] - T[1]) < 0.02 and abs(found[1] - T[0]) < 0.02
    # sin la restricción de las match lines el parquímetro repetido daría otro pico:
    # con un «a través» equivocado (un paso del símbolo) no se acepta nada
    assert S.translation_from_votes(votes, 1, T[0] + 12.6, T[1], C.SEAM_ALONG_TOL_PT) is None


def test_trim_border_encuentra_la_match_line_por_fuera_y_prefiere_la_gruesa():
    doc = _two_sheets()
    page = doc[0]
    W, H = page.rect.width, page.rect.height
    # el lado quedó 4 pt ANTES de la match line: igual se corta en ella (no falta plano)
    clip, covers = C.trim_border(page, [150 / W, 40 / H, (ML_X - 4) / W, 262 / H])
    assert abs(clip[2] * W - ML_X) < 0.6 and "right" in covers
    # el lado quedó sobre la cota fina de 0.72 pt (20 pt por fuera): gana la match line
    clip, _ = C.trim_border(page, [150 / W, 40 / H, (ML_X + 21) / W, 262 / H])
    assert abs(clip[2] * W - ML_X) < 0.6
    # …o sobre la de 60 pt (las tres cotas parecen una grilla): igual, la match
    # line a guiones gruesa manda
    clip, _ = C.trim_border(page, [150 / W, 40 / H, (ML_X + 61) / W, 262 / H])
    assert abs(clip[2] * W - ML_X) < 0.6


@pytest.mark.parametrize("jitter,drop_dy,trim,snap", [(-4.0, 25.0, True, False), (0.0, -30.0, True, False),
                                                       (21.0, 5.0, True, False), (-4.0, 25.0, False, False),
                                                       (6.0, -20.0, False, False), (45.0, 10.0, True, True),
                                                       (61.0, -10.0, False, False)])
def test_compositor_une_sin_grada(jitter, drop_dy, trim, snap):
    """Flujo del usuario (DU06 13→14): recorta cada hoja con el lado de la costura
    `jitter` pt más allá de la match line (−4 = se quedó corto; 21 = sobre la
    cota fina), toma las dos piezas con «sin línea de borde» y suelta la segunda
    descolocada. El dibujo tiene que quedar CONTINUO: el mismo punto del modelo
    cae en el mismo lugar de la hoja compuesta desde las dos piezas (antes: grada
    de 8 pt con jitter −4 y de 43 pt si el lado caía en la cota). Sin «sin línea
    de borde» los cortes quedan donde el usuario los dejó: la pieza se corre a
    través lo que marquen las match lines (queda un hueco o se solapa), nunca
    escalonada. `snap`: el lado pasa antes por el imán del área (30 pt, hoja entera
    a la vista), que desde 45 pt afuera engancha una cota fina."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from PySide6 import QtCore
    import composite_dialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
    data = _two_sheets().tobytes()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        for pno, (x0, y0, x1, y1) in ((0, (150.0, 40.0, ML_X + jitter, 262.0)),
                                      (1, (ML_X + T[0] - jitter, 60.0, 250.0, 274.0))):
            dlg.btn_trim.setChecked(trim)
            dlg.lst_pages.setCurrentRow(pno)
            if snap:
                g = C.guide_lines(dlg.docs[0][pno])["x"]
                edge = x1 if pno == 0 else x0
                hit = C.snap_edge(g, edge, y0, y1, 30.0)
                if hit:
                    x1, x0 = (hit[0], x0) if pno == 0 else (x1, hit[0])
            r = dlg.crop._page_rect
            sx, sy = r.width() / 400.0, r.height() / 300.0
            dlg.crop._selection = QtCore.QRectF(x0 * sx, y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy)
            dlg._take(full=False)
        p1, p2 = dlg.comp.pieces
        tgt = dlg.comp.target_scale()
        w1, _ = C.piece_size(p1, (400.0, 300.0), tgt)
        P = (250.0, 150.0)                                   # punto del modelo (hoja A)
        # dónde tendría que ir p2 a lo largo, y se suelta `drop_dy` más allá
        p2.x, p2.y = p1.x + w1 + 2.0, p1.y
        m1 = C.piece_map(p1, (400.0, 300.0), tgt)(*P)
        m2 = C.piece_map(p2, (400.0, 300.0), tgt)(P[0] + T[0], P[1] + T[1])
        snapped = dlg.view.snap_position(1, (p1.x + w1 + 2.0, p2.y + m1[1] - m2[1] + drop_dy))
        assert snapped is not None
        p2.x, p2.y = snapped
        m2 = C.piece_map(p2, (400.0, 300.0), tgt)(P[0] + T[0], P[1] + T[1])
        assert abs(m2[0] - m1[0]) < 0.05 and abs(m2[1] - m1[1]) < 0.05, (m2[0] - m1[0], m2[1] - m1[1])
    finally:
        dlg.close_docs()


def test_iman_del_area_prefiere_la_match_line_gruesa_a_la_cota_mas_larga():
    """DU10: la cota fina (0.72 pt) a 20 pt de la match line cubre MÁS que la
    match line a guiones (349 vs 301 pt); el imán del área tiene que saltar a la
    match line gruesa, no a la cota (el recorte quedaba 20–60 pt pasado)."""
    doc = fitz.open(); page = doc.new_page(width=400, height=300)
    for y in range(40, 260, 54):                                   # match line: guiones de 36 pt, 1.98
        page.draw_line((300, y), (300, y + 36), color=(0, 0, 0), width=1.98)
    page.draw_line((320, 30), (320, 280), color=(0, 0, 0), width=0.72)    # cota fina más larga
    g = C.guide_lines(page)["x"]
    assert C.snap_edge(g, 318.0, 0.0, 300.0, 30.0)[0] == pytest.approx(300.0)
    # y «sin línea de borde» con el lado en el blanco a 25 pt: alcanza la gruesa
    clip, _ = C.trim_border(page, [0.0, 0.0, 325 / 400, 1.0])
    assert clip[2] * 400 == pytest.approx(300.0, abs=0.01)


def test_hoja_sin_capas_pide_mas_votos():
    """DU08 viene «aplanado» (ningún trazo con capa): no se puede exigir ≥2 capas
    como defensa contra un símbolo repetido, así que se piden el doble de pares."""
    few = [(-200.0, 12.0 + 0.01 * k, "") for k in range(S.REG_MIN_VOTES)]
    many = [(-200.0, 12.0 + 0.01 * k, "") for k in range(2 * S.REG_MIN_VOTES)]
    assert S.translation_from_votes(few, 1, -200.0, 0.0, 90.0) is None
    found = S.translation_from_votes(many, 1, -200.0, 0.0, 90.0)
    assert found is not None and abs(found[0] - 12.05) < 0.05
    # con capa, un solo símbolo repetido (una capa) no alcanza aunque sean muchos
    one_layer = [(-200.0, 12.0, "V-PKNG") for _ in range(3 * S.REG_MIN_VOTES)]
    assert S.translation_from_votes(one_layer, 1, -200.0, 0.0, 90.0) is None


def test_sin_dibujo_compartido_la_continuidad_de_las_lineas_fija_la_costura():
    """LABOE h.8→9: los viewports terminan justo en la match line, no hay ningún
    vector idéntico en las dos hojas. Las líneas que la cruzan (prolongadas hasta
    ella) siguen con el mismo rumbo al otro lado: su cruce da el desplazamiento
    a lo largo."""
    doc = fitz.open()
    ocgs = {n: doc.add_ocg(n, on=True) for n in ("V-SITE", "C-ROAD", "C-ALGN", "C-WATR", "V-PKNG", "C-ANNO")}
    _sheet(doc, ocgs, (0.0, 0.0), 20.0, _ml(150), _ml, +1)                 # corta EN la match line
    _sheet(doc, ocgs, T, _ml(150) + T[0], 380.0, lambda y: _ml(y - T[1]) + T[0], -1)
    ra = (150.0, 40.0, _ml(150), 262.0); rb = (_ml(150) + T[0], 52.0, 250.0, 274.0)
    la, lb = S.page_lines(doc[0]), S.page_lines(doc[1])
    rule_a, rule_b = S.seam_rule(la, ra, "right"), S.seam_rule(lb, rb, "left")
    assert S.rules_match(rule_a, rule_b)
    votes = S.seam_votes(S.band_segments(la, ra, "right", rule=rule_a), S.band_segments(lb, rb, "left", rule=rule_b))
    assert S.translation_from_votes(votes, 1, T[0], T[1], 90.0) is None     # nada compartido
    cv = S.crossing_votes(S.rule_crossings(la, ra, "right", rule_a), S.rule_crossings(lb, rb, "left", rule_b))
    along = S.along_from_crossings(cv, T[1] + 30.0, 90.0)
    assert along is not None and abs(along - T[1]) < 0.1
