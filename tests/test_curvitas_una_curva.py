"""Varias curvitas seguidas → UNA curva, y el quiebre que no entraba por vértices casi
rectos (reporte del usuario 2026-10-19, DU06 UD-205 en la hoja compuesta: la «—SC—» de
telecom junto a «CB-216 LAT» gira 44° con un solo arco del PDF y salían tres codos de
r = 67.6, 18 y 13.5 pt; y su quiebre de abajo, junto a la otra «SC», no entraba como curva
porque dos vértices de 0.75° a 1.3 ft le quitaban el lugar). La regla vale en TODAS las
utilidades: `fit_fillets` es la misma para todas y `quiebres_curvas` para las que no van a
presión."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from nucleo import model_ops  # noqa: E402
from nucleo import quiebres_curvas as qc  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_quiebres as RQ  # noqa: E402
from reconocimiento import recognition_trace as trace  # noqa: E402
from reconocimiento import recognition_unir_codos as U  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
needs_du06 = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")


def _editor(pts, kinds, fillets):
    """Cada codo es exactamente el que dibuja el editor (sin recorte)."""
    for i, g in fillets.items():
        caps = [model_ops.FILLET_CAP_CURVA if kinds[j] == "fillet" else model_ops.FILLET_CAP_RECTA
                for j in (i - 1, i + 1)]
        geo = model_ops.fillet_geo(pts[i - 1], pts[i], pts[i + 1], g["r_px"], max_frac=caps[0],
                                   max_frac_next=caps[1], tol_r=0.0)
        assert geo is not None and not geo["clamped"]
        assert math.dist(geo["t1"], g["a"]) < 1e-6 and math.dist(geo["t2"], g["b"]) < 1e-6


def _arco(ctr, r, a0, a1, n):
    return [(ctr[0] + r * math.cos(a0 + (a1 - a0) * k / n), ctr[1] + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def _parte(a, b, ctr, r):
    a0 = math.atan2(a[1] - ctr[1], a[0] - ctr[0])
    sw = (math.atan2(b[1] - ctr[1], b[0] - ctr[0]) - a0 + math.pi) % (2 * math.pi) - math.pi
    return (a, b, (a, b, ctr, r, a0, sw))


# ───────────────────────── reconocimiento: unir_codos ─────────────────────────

def test_recta_arco_recta_que_circular_trace_parte_vuelve_a_ser_un_codo():
    """La tinta del reporte: recta, arco aplanado (cuerdas de ~1.85 pt) de r = 14.4 que
    gira 44° y la diagonal, cuya punta se tuerce 0.12 pt. `circular_trace` lo parte en
    varios círculos; queda UNO, tangente a la recta y a la diagonal, con el radio del PDF."""
    R, D = 14.4, math.radians(44)
    arco = [(20.0 + R * math.sin(t), R - R * math.cos(t)) for t in [D * k / 6 for k in range(7)]]
    fin = arco[-1]
    u = (math.cos(D), math.sin(D))
    tinta = [(0.0, 0.0)] + arco + [(fin[0] + 7.3 * u[0], fin[1] + 7.3 * u[1]),
                                   (fin[0] + 31 * u[0], fin[1] + 31 * u[1] + 0.12)]
    pts, kinds, fil = trace._encode(trace.circular_trace(tinta, 1.0), "end", "end")
    assert len(fil) >= 2                                  # lo de antes: varias curvitas
    p2, k2, f2 = U.unir_codos(pts, kinds, fil, 1.0)
    assert k2 == ["end", "fillet", "end"] and list(f2) == [1]
    g = f2[1]
    assert g["r_px"] == pytest.approx(R, abs=0.05) and not g["loose"] and g["unidos"] == len(fil)
    assert p2[1] == pytest.approx((20.0 + R * math.tan(D / 2), 0.0), abs=0.05)     # esquina sobre y = 0
    _editor(p2, k2, f2)


@pytest.mark.parametrize("f", [1.0, 3.5])
def test_cadena_de_codos_del_mismo_circulo(f):
    """Tres codos seguidos sobre el MISMO círculo (r = 30 pt, 90° en tres trozos de 30°)
    entre dos rectas: un codo de 90° (a cualquier zoom)."""
    R = 30.0 * f
    ctr = (100.0 * f, R)
    cortes = [math.radians(a) for a in (-90, -60, -30, 0)]
    A = (ctr[0], 0.0)
    partes = [((0.0, 0.0), A, None)]
    for a0, a1 in zip(cortes, cortes[1:]):
        p, q = (ctr[0] + R * math.cos(a0), ctr[1] + R * math.sin(a0)), (ctr[0] + R * math.cos(a1), ctr[1] + R * math.sin(a1))
        partes.append(_parte(p, q, ctr, R))
    B = (ctr[0] + R, ctr[1])
    partes.append((B, (B[0], B[1] + 80.0 * f), None))
    pts, kinds, fil = trace._encode(partes, "end", "end")
    assert len(fil) == 3
    p2, k2, f2 = U.unir_codos(pts, kinds, fil, f)
    assert len(f2) == 1
    (i, g), = f2.items()
    assert g["r_px"] == pytest.approx(R, rel=1e-3)
    assert p2[i] == pytest.approx((ctr[0] + R, 0.0), abs=1e-3 * f)
    assert g["a"] == pytest.approx(A, abs=1e-2 * f) and g["b"] == pytest.approx(B, abs=1e-2 * f)
    _editor(p2, k2, f2)


def _espiral(r0, r1, giro_deg, paso=1.0):
    """Tinta de una curva de radio VARIABLE (de r0 a r1) entre dos rectas, aplanada."""
    pts = [(-40.0, 0.0), (0.0, 0.0)]
    x, y, th = 0.0, 0.0, 0.0
    total = math.radians(giro_deg)
    while th < total:
        r = r0 + (r1 - r0) * th / total
        dth = min(paso / r, total - th)
        x += r * (math.sin(th + dth) - math.sin(th))
        y += r * (math.cos(th) - math.cos(th + dth))
        th += dth
        pts.append((x, y))
    pts.append((x + 40.0 * math.cos(total), y + 40.0 * math.sin(total)))
    return pts


def test_con_tinta_un_arco_se_une_y_un_radio_variable_no():
    """La tinta manda: si la tinta ES un arco, las curvitas pasan a ser ese arco; si es una
    curva de radio variable (que necesita varios arcos para seguirla a 0.12 pt, como las de
    DU06 h.5 y DU08 h.22), se quedan como están."""
    R = 25.0
    arco = _espiral(R, R, 70)                         # recta, arco de r = 25 que gira 70°, recta
    ctr = (0.0, R)
    cortes = [math.radians(a) for a in (-90, -70, -45, -20)]
    partes = [((-40.0, 0.0), (0.0, 0.0), None)]
    for a0, a1 in zip(cortes, cortes[1:]):
        partes.append(_parte((ctr[0] + R * math.cos(a0), ctr[1] + R * math.sin(a0)),
                             (ctr[0] + R * math.cos(a1), ctr[1] + R * math.sin(a1)), ctr, R))
    partes.append(((ctr[0] + R * math.cos(cortes[-1]), ctr[1] + R * math.sin(cortes[-1])), arco[-1], None))
    pts, kinds, fil = trace._encode(partes, "end", "end")
    assert len(fil) == 3
    _p, _k, f2 = U.unir_codos(pts, kinds, fil, 1.0, strokes=[arco])
    assert len(f2) == 1 and next(iter(f2.values()))["r_px"] == pytest.approx(R, abs=0.1)
    espiral = _espiral(40.0, 12.0, 90)
    pts, kinds, fil = trace._encode(trace.circular_trace(espiral, 1.0), "end", "end")
    assert len(fil) >= 2
    assert U.unir_codos(pts, kinds, fil, 1.0, strokes=[espiral]) == (pts, kinds, fil)


def test_curva_compuesta_de_verdad_y_la_s_no_cambian():
    # dos radios muy distintos (60 y 120), tangentes entre sí: un solo arco se apartaría
    R1, R2 = 60.0, 120.0
    O1 = (100.0, R1)
    M = (O1[0] + R1 * math.cos(math.radians(-45)), O1[1] + R1 * math.sin(math.radians(-45)))
    O2 = (M[0] + (O1[0] - M[0]) / R1 * R2, M[1] + (O1[1] - M[1]) / R1 * R2)
    B = (O2[0] + R2, O2[1])
    partes = [((0.0, 0.0), (100.0, 0.0), None), _parte((100.0, 0.0), M, O1, R1), _parte(M, B, O2, R2),
              (B, (B[0], B[1] + 200.0), None)]
    pts, kinds, fil = trace._encode(partes, "end", "end")
    assert len(fil) == 2
    assert U.unir_codos(pts, kinds, fil, 1.0) == (pts, kinds, fil)
    # «S»: el segundo arco gira al revés (centro reflejado en M) y vuelve a la horizontal
    O3 = (2 * M[0] - O1[0], 2 * M[1] - O1[1])
    S_fin = (O3[0], O3[1] + R1)
    partes = [((0.0, 0.0), (100.0, 0.0), None), _parte((100.0, 0.0), M, O1, R1), _parte(M, S_fin, O3, R1),
              (S_fin, (S_fin[0] + 100.0, S_fin[1]), None)]
    pts, kinds, fil = trace._encode(partes, "end", "end")
    assert len(fil) == 2
    assert U.unir_codos(pts, kinds, fil, 1.0) == (pts, kinds, fil)


def test_codo_que_muere_en_un_nodo_sigue_muriendo_en_el():
    """Dos codos del mismo círculo que nacen en un tee (la tangencia ES el nodo): el codo
    único también nace en el tee, que no se mueve."""
    R = 40.0
    ctr = (0.0, R)
    m = (R * math.cos(math.radians(-45)), ctr[1] + R * math.sin(math.radians(-45)))
    B = (R, R)
    partes = [_parte((0.0, 0.0), m, ctr, R), _parte(m, B, ctr, R), (B, (R, R + 100.0), None)]
    pts, kinds, fil = trace._encode(partes, "tee", "end")
    # la recta que pasa por el tee: el vértice anterior sobre ella
    pts = [(-100.0, 0.0)] + pts
    kinds = ["end"] + kinds
    fil = {i + 1: g for i, g in fil.items()}
    p2, k2, f2 = U.unir_codos(pts, kinds, fil, 1.0)
    assert len(f2) == 1
    (i, g), = f2.items()
    assert (0.0, 0.0) in p2 and k2[p2.index((0.0, 0.0))] == "tee"
    assert g["a"] == pytest.approx((0.0, 0.0), abs=1e-6) and g["node_a"]
    assert g["r_px"] == pytest.approx(R, rel=1e-6)


def test_fit_fillets_los_une_en_todas_las_utilidades():
    """`fit_fillets` (la misma para las seis utilidades) devuelve UN codo para la cadena."""
    R = 30.0
    ctr = (100.0, R)
    cortes = [math.radians(a) for a in (-90, -50, 0)]
    partes = [((0.0, 0.0), (100.0, 0.0), None)]
    for a0, a1 in zip(cortes, cortes[1:]):
        partes.append(_parte((ctr[0] + R * math.cos(a0), ctr[1] + R * math.sin(a0)),
                             (ctr[0] + R * math.cos(a1), ctr[1] + R * math.sin(a1)), ctr, R))
    partes.append(((ctr[0] + R, ctr[1]), (ctr[0] + R, ctr[1] + 80.0), None))
    pts, kinds, fil = trace._encode(partes, "end", "end")
    p2, k2, f2 = U.unir_codos(pts, kinds, fil, rec.FILLET_FIT_TOL_PT)
    assert len(f2) == 1


# ───────────────────── importación: quiebres con vértices casi rectos ─────────────────────

FPP = 0.1      # pies por px: radio automático de 12" (6 ft) = 60 px; a 45°, T = 24.9 px


def _pipe(pts, kinds, layer="TELECOM", diam=12):
    return {"layer": layer, "pts": [tuple(map(float, q)) for q in pts], "vertex_kinds": list(kinds),
            "diam": diam, "world": False}


def _importar(pipes):
    st = model_ops.rebuild_structures(pipes, [])
    model_ops.hide_soft_vertex_structures(pipes, st)
    model_ops.attach_fillets(pipes, st)
    return st


@pytest.mark.parametrize("layer", ["ELECTRICO", "TELECOM"])
def test_vertices_casi_rectos_no_dejan_sin_curva_al_quiebre(layer):
    pipes = [_pipe([(0, 0), (980, 0.1), (990, 0.05), (1000, 0), (1707.1, 707.1)],
                   ["end", "bend", "bend", "corner", "end"], layer=layer)]
    st = _importar(pipes)
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1 and sin_lugar == []
    assert pipes[0]["pts"] == [(0.0, 0.0), (1000.0, 0.0), (1707.1, 707.1)]
    assert pipes[0]["vertex_kinds"] == ["end", "corner", "end"]
    p = pipes[0]
    cv = model_ops.curve_vertex_indices(p, st, pipes)
    g = qc._geo(p["pts"], 1, qc._radio_px(cv[1], p, FPP), set(cv), FPP)
    assert not g["clamped"] and g["r"] == pytest.approx(60.0)


def test_un_vertice_que_si_gira_o_que_es_union_no_se_quita():
    # gira 3°: no es «prácticamente recto» (el plugin tampoco lo endereza)
    pipes = [_pipe([(0, 0), (985, 0.79), (1000, 0), (1707.1, 707.1)], ["end", "bend", "corner", "end"])]
    st = _importar(pipes)
    _nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert (1000.0, 0.0) in sin_lugar and len(pipes[0]["pts"]) == 4
    # casi recto, pero otra utilidad llega justo ahí: es una unión
    pipes = [_pipe([(0, 0), (980, 0.05), (1000, 0), (1707.1, 707.1)], ["end", "bend", "corner", "end"]),
             _pipe([(980, 0.05), (980, 500)], ["tee", "end"])]
    st = _importar(pipes)
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert nuevas == [] and sin_lugar == [(1000.0, 0.0)]
    assert len(pipes[0]["pts"]) == 4


def test_gravedad_quita_el_vertice_pegado_y_su_buzon_oculto():
    """Drenaje: un vértice casi recto a 10 px del quiebre (su buzón se reconcilia por
    coordenada): antes el quiebre quedaba sin curva y sin aviso; ahora se quita con su
    buzón oculto y el buzón oculto del quiebre pasa a ser la curva."""
    pipes = [_pipe([(0, 0), (990, 0.05), (1000, 0), (1000, 800)], ["vault", "bend", "corner", "vault"],
                   layer="DRENAJE")]
    st = _importar(pipes)
    # los dos vértices pegados comparten UN buzón oculto (se reconcilia por coordenada)
    assert [(s["x"], s["y"]) for s in st if s["hidden"]] == [(990.0, 0.05)]
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1 and sin_lugar == []
    assert pipes[0]["pts"] == [(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0)]
    assert not any(math.dist((s["x"], s["y"]), (990, 0.05)) < 1 for s in st)
    st = model_ops.rebuild_structures(pipes, st)
    cv = [s for s in st if s.get("curve")]
    assert len(cv) == 1 and (cv[0]["x"], cv[0]["y"]) == (1000.0, 0.0) and cv[0].get("quiebre")


def test_el_codo_vecino_de_la_tinta_no_cambia():
    """Junto al quiebre hay un codo de la tinta y, entre los dos, un vértice casi recto:
    se quita solo si el codo vecino sigue igual (mismo radio, sin recorte, mismo arco)."""
    pipes = [_pipe([(0, 0), (400, 0), (700, 300), (990, 590.05), (1000, 600), (1000, 1200)],
                   ["end", "fillet", "bend", "bend", "corner", "end"])]
    pipes[0]["fillets"] = {1: 10.0}                      # codo de la tinta: r = 10 ft (100 px)
    st = _importar(pipes)
    p = pipes[0]
    cv0, geos0 = model_ops.curve_vertex_indices(p, st, pipes), None
    from nucleo import limpieza_tramos as LT
    _cv, geos0 = LT.curvas(pipes, st, 0, FPP)
    arco0 = geos0[1]
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1 and sin_lugar == []
    assert (990.0, 590.05) not in p["pts"]
    _cv, geos1 = LT.curvas(pipes, st, 0, FPP)
    assert geos1[1]["r"] == pytest.approx(arco0["r"]) and not geos1[1]["clamped"]
    assert math.dist(geos1[1]["t2"], arco0["t2"]) < 0.25 / FPP
    del cv0


# ─────────────── vista previa = importación ───────────────

Z = 3.5
ESCALA = 20.0 / 72.0


def test_la_vista_previa_dibuja_sin_los_vertices_que_se_quitan():
    pts = [(0.0, 0.0), (980.0, 0.1), (990.0, 0.05), (1000.0, 0.0), (1707.1, 707.1)]
    pl = rec.RecognizedPolyline("C-TELE-UNGD-E", "TELECOM", pts, rec.utility_line_kind("TELECOM"),
                                ["end", "bend", "bend", "corner", "end"])
    res = rec.RecognitionResult("TELECOM", 0, ESCALA, polylines=[pl])
    curvas = RQ.curvas_de_quiebres([res], Z)[id(res)]
    assert curvas[(980.0, 0.1)] == {RQ.QUITADO: True} and curvas[(990.0, 0.05)] == {RQ.QUITADO: True}
    assert RQ.codos_de(pl, curvas) == {3: curvas[(1000.0, 0.0)]}
    pl2, fil = RQ.dibujo_de(pl, curvas)
    assert pl2.pts_pdf == [(0.0, 0.0), (1000.0, 0.0), (1707.1, 707.1)] and pl2.kinds == ["end", "corner", "end"]
    assert list(fil) == [1] and fil[1]["quiebre"]
    assert pl.pts_pdf == pts                             # el resultado del reconocimiento no cambia
    # sin nada que quitar: la misma polilínea
    assert RQ.dibujo_de(pl, {})[0] is pl


# ─────────────── DU06 h.7 (UD-205): solo la zona del reporte ───────────────

PAG, ZONA = 6, (450.0, 900.0, 1150.0, 1250.0)          # recorte alrededor de CB-216 LAT


@pytest.fixture(scope="module")
def du06_ud205():
    import fitz
    with fitz.open(str(DU06)) as doc:
        W, H = doc[PAG].rect.width, doc[PAG].rect.height
        x0, y0, x1, y1 = ZONA
        res = rec.recognize_page(None, PAG, utility="TELECOM", zoom=Z, doc=doc,
                                 crop=(x0 / W, y0 / H, x1 / W, y1 / H))
    res.utility = "TELECOM"
    return res


def _pt(q):
    return (q[0] / Z + ZONA[0], q[1] / Z + ZONA[1])


@needs_du06
def test_du06_ud205_la_sc_gira_con_una_sola_curva(du06_ud205):
    pls = [p for p in du06_ud205.drawable if any(math.dist(_pt(q), (784.6, 1058.8)) < 3 for q in p.pts_pdf)]
    assert len(pls) == 1
    pl = pls[0]
    codos = [(i, g) for i, g in pl.fillets.items() if 760 < _pt(pl.pts_pdf[i])[0] < 800]
    assert len(codos) == 1, [round(g["r_px"] / Z, 2) for g in pl.fillets.values()]
    i, g = codos[0]
    # el arco del PDF: tangente a y = 1058.82 y a la diagonal de 44°, r = 14.4 pt
    assert g["r_px"] / Z == pytest.approx(14.4, abs=0.8)
    assert _pt(pl.pts_pdf[i]) == pytest.approx((784.6, 1058.85), abs=0.3)
    assert abs(_pt(g["a"])[1] - 1058.85) < 0.1
    _editor(pl.pts_pdf, pl.kinds, pl.fillets)


@needs_du06
def test_du06_ud205_el_quiebre_junto_a_la_sc_de_abajo_es_curva(du06_ud205):
    curvas = RQ.curvas_de_quiebres([du06_ud205], Z)[id(du06_ud205)]
    pl = next(p for p in du06_ud205.drawable if any(math.dist(_pt(q), (815.6, 1088.75)) < 1 for q in p.pts_pdf))
    pl2, fil = RQ.dibujo_de(pl, curvas)
    k = next(i for i, q in enumerate(pl2.pts_pdf) if math.dist(_pt(q), (815.6, 1088.75)) < 1)
    assert k in fil and fil[k].get("quiebre")
    # radio mínimo de la regla: 6 × 12" = 6 ft; sin vértices entre el codo de arriba y él
    assert fil[k]["r_px"] * ESCALA / Z == pytest.approx(6.0, abs=0.01)
    assert pl2.kinds[k - 1] == "fillet"
