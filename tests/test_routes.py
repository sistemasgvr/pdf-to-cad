"""Rutas por buena continuación (strokes). Headless, sin Qt.

Los casos 2–8 y el cruce en X parten de las polilíneas ya cortadas que
devuelve el reconocimiento (un extremo por cada lado del nodo). El caso 1
y las invariantes del DU06 pasan por `reconstruct` / `recognize_page`.
"""
import math
from pathlib import Path

import pytest

import recognition_geom as G
from recognition_geom import Pattern, Polyline
from routes import build_routes
from test_recognition_geom import PDF, Sheet, needs_pdf

ROOT = Path(__file__).resolve().parent.parent


def P(*pts, kinds=None):
    pts = list(pts)
    return Polyline(pts, list(kinds) if kinds else ["end"] * len(pts))


def L(pl):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pl.pts, pl.pts[1:]))


def near(a, b, tol=0.6):
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _by_touch(routes, pt, tol=1.0):
    return [r for r in routes if any(near(p, pt, tol) for p in r.pl.pts)]


def _invariants(src, routes):
    """Partición, longitudes y ningún punto nuevo (solo se pierden los
    vértices de unión duplicados)."""
    from collections import Counter
    members = [i for r in routes for i in r.members]
    assert sorted(members) == list(range(len(src)))
    assert abs(sum(L(r.pl) for r in routes) - sum(L(p) for p in src)) < 1e-6
    key = lambda p: (round(p[0], 4), round(p[1], 4))
    inn, out = Counter(key(p) for pl in src for p in pl.pts), Counter(key(p) for r in routes for p in r.pl.pts)
    assert not (out - inn)                    # ningún punto inventado
    assert sum((inn - out).values()) == sum(r.n_segments - 1 for r in routes)


# ─────────────────────────── sintéticos (polilíneas ya cortadas) ───────────────────────────
def test_T_reconstruida_queda_en_dos_rutas():
    """Horizontal continua + ramal que muere en ella. El tee queda en el medio
    de la ruta principal; el ramal lo tiene en el extremo de unión."""
    sh = Sheet()
    sh.dashed((100, 400), (700, 400))
    sh.dashed((400, 400), (400, 200))
    res = sh.run()
    routes = build_routes(res.polylines, res.pattern)
    assert len(routes) == 2, [(r.n_segments, r.pl.kinds) for r in routes]
    H = max(routes, key=lambda r: L(r.pl))
    assert "tee" in H.pl.kinds
    assert H.pl.kinds[0] != "tee" and H.pl.kinds[-1] != "tee"
    branch = min(routes, key=lambda r: L(r.pl))
    # §4.5: el inicio es el extremo libre; el tee es el extremo de unión.
    assert branch.pl.kinds[0] == "end"
    assert branch.pl.kinds[-1] == "tee"
    _invariants(res.polylines, routes)


def test_cruce_X_se_empareja_de_frente():
    src = [
        P((0, 0), (100, 0), kinds=("end", "junction")),
        P((100, 0), (200, 0), kinds=("junction", "end")),
        P((100, 0), (100, 100), kinds=("junction", "end")),
        P((100, 0), (100, -100), kinds=("junction", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 2
    assert all(r.n_segments == 2 for r in routes)
    _invariants(src, routes)


def test_Y_simetrica_no_se_une():
    a = 100 * math.cos(math.radians(30))
    b = 100 * math.sin(math.radians(30))
    src = [
        P((0, 0), (100, 0), kinds=("end", "junction")),
        P((100, 0), (100 + a, b), kinds=("junction", "end")),
        P((100, 0), (100 + a, -b), kinds=("junction", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 3
    assert all(r.n_segments == 1 for r in routes)


def test_Y_asimetrica_sigue_el_de_frente():
    def ray(deg):
        return (100 + 100 * math.cos(math.radians(deg)), 100 * math.sin(math.radians(deg)))
    src = [
        P((0, 0), (100, 0), kinds=("end", "junction")),
        P((100, 0), ray(5), kinds=("junction", "end")),
        P((100, 0), ray(40), kinds=("junction", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 2, [(r.n_segments, r.pl.kinds) for r in routes]
    straight = max(routes, key=lambda r: r.n_segments)
    assert straight.n_segments == 2
    assert near(straight.pl.pts[-1], ray(5), 1e-6) or near(straight.pl.pts[0], ray(5), 1e-6)
    branch = min(routes, key=lambda r: r.n_segments)
    assert branch.n_segments == 1
    assert near(branch.pl.pts[-1], ray(40), 1e-6) or near(branch.pl.pts[0], ray(40), 1e-6)


def test_esquina_en_L_grado2_es_una_ruta():
    src = [
        P((0, 0), (100, 0), kinds=("end", "corner")),
        P((100, 0), (100, 100), kinds=("corner", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 1 and routes[0].n_segments == 2
    _invariants(src, routes)


def test_horquilla_a_170_no_se_une():
    tip = (100 + 100 * math.cos(math.radians(170)), 100 * math.sin(math.radians(170)))
    src = [
        P((0, 0), (100, 0), kinds=("end", "end")),
        P((100, 0), tip, kinds=("end", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 2 and all(r.n_segments == 1 for r in routes)


def test_boveda_atravesada_y_stub_en_el_borde():
    src = [
        P((0, 400), (200, 400), (400, 400), kinds=("edge", "vault", "edge")),
        P((200, 450), (200, 430), kinds=("end", "stop")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 2
    through = max(routes, key=lambda r: L(r.pl))
    assert through.pl.kinds == ["edge", "vault", "edge"]
    assert "stop" in min(routes, key=lambda r: L(r.pl)).pl.kinds


def test_cut_nunca_se_une():
    src = [
        P((0, 0), (100, 0), kinds=("end", "cut")),
        P((100, 0), (200, 0), kinds=("cut", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 2 and all(r.n_segments == 1 for r in routes)


def test_dos_stop_en_bordes_opuestos_no_se_inventan():
    src = [
        P((100, 400), (180, 400), kinds=("end", "stop")),
        P((220, 400), (300, 400), kinds=("stop", "end")),
    ]
    routes = build_routes(src, None)
    assert len(routes) == 2


def test_determinismo_y_lookahead_no_inventa_puntos():
    src = [
        P((0, 0), (10, 2), (80, 0), kinds=("end", "bend", "junction")),
        P((80, 0), (160, 0), kinds=("junction", "end")),
        P((80, 0), (80, 40), kinds=("junction", "end")),
    ]
    pat = Pattern(22.0, 7.0, 10.0, 4.5, 8.0, 14.0, 40.0, 1.5)
    a = build_routes(src, pat)
    b = build_routes(src, pat)
    assert [(r.pl.pts, r.pl.kinds, r.members) for r in a] == [(r.pl.pts, r.pl.kinds, r.members) for r in b]
    _invariants(src, a)


# ─────────────────────────── DU06 ───────────────────────────
@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
@pytest.mark.parametrize("page", [2, 3, 8, 12, 13])
def test_du06_invariantes_de_rutas(page):
    import fitz
    import recognition as rec

    doc = fitz.open(str(PDF))
    try:
        page_obj = doc[page]

        def kind_for(ocg):
            return rec.classify_ocg(ocg)

        line_paths, vault_paths, _, _ = rec.gather_paths(page_obj, kind_for, set())
        by = {}
        for pth in line_paths:
            by.setdefault(pth.get("layer") or "", []).append(pth)
        for paths in by.values():
            g = G.reconstruct(paths, vault_paths)
            routes = build_routes(g.polylines, g.pattern)
            assert len(routes) <= len(g.polylines)
            if g.polylines:
                _invariants(g.polylines, routes)
        raw = rec.recognize_page(PDF, page_index=page, zoom=1.0, doc=doc, join_routes=False)
        joined = rec.recognize_page(PDF, page_index=page, zoom=1.0, doc=doc, join_routes=True)
        assert raw.coverage == joined.coverage
        assert len(raw.uncovered_px) == len(joined.uncovered_px)
        assert len(joined.drawable) <= len(raw.drawable)
        assert joined.n_routes == sum(1 for p in joined.drawable)
        assert joined.n_segments_total == sum(p.n_segments for p in joined.drawable)
    finally:
        doc.close()


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_du06_hoja13_prop_comm_y_haynes_en_pocas_rutas():
    """Las dos «PROP COMM DB» y la vertical de Haynes St no se parten: ≤ 3 rutas."""
    import fitz
    import recognition as rec

    doc = fitz.open(str(PDF))
    try:
        page = doc[12]
        labels = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                t = "".join(s["text"] for s in line["spans"]).upper()
                if "PROP COMM DB" in t or t.strip() == "HAYNES ST":
                    labels.append(line["bbox"])
        assert len(labels) >= 3, labels

        def kind_for(ocg):
            return rec.classify_ocg(ocg)

        line_paths, vault_paths, _, _ = rec.gather_paths(page, kind_for, set())
        paths = [p for p in line_paths if (p.get("layer") or "").endswith("C-ELEC-UNGD-E")
                 or "C-ELEC-UNGD-E" in (p.get("layer") or "")]
        g = G.reconstruct(paths, vault_paths)
        routes = build_routes(g.polylines, g.pattern)

        def near_label(route, bb, pad=40.0):
            x0, y0, x1, y1 = bb
            return any(x0 - pad <= p[0] <= x1 + pad and y0 - pad <= p[1] <= y1 + pad
                       for p in route.pl.pts) and L(route.pl) > 200

        hit = {id(r) for bb in labels for r in routes if near_label(r, bb)}
        assert 1 <= len(hit) <= 3, [(r.n_segments, r.pl.kinds) for r in routes]
    finally:
        doc.close()


# ─────────────── rutas ya emitidas (con codos): `join_emitted` ───────────────
# Pedido del usuario 2026-09-30 (DU06 h.5, telecom): la «U» cuyo hueco de letras
# cierra `connect_text_gaps` quedaba en dos rutas justo donde se une.
from dataclasses import dataclass, field  # noqa: E402

import model_ops  # noqa: E402
import recognition_trace as trace  # noqa: E402
from routes import join_emitted  # noqa: E402


@dataclass
class _E:
    """Lo que `join_emitted` usa de una `RecognizedPolyline`."""
    pts_pdf: list
    kinds: list
    fillets: dict = field(default_factory=dict)
    layer_ocg: str = "capa"
    abandoned: bool = False
    n_segments: int = 1
    review: str = ""


def _emitted(parts, k0="end", k1="junction", **kw):
    P, K, F = trace._encode(parts, k0, k1)
    return _E(P, K, F, **kw)


def _arc(r, deg0, deg1, c=(0.0, 0.0)):
    a0, a1 = math.radians(deg0), math.radians(deg1)
    pa = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
    pb = (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
    return pa, pb, (pa, pb, c, r, a0, a1 - a0)


def _u_halves():
    """«U» de r = 30 partida en (−30, 0): la mitad de abajo va AL REVÉS."""
    a1, b1, arc1 = _arc(30.0, 90, 180)
    top = _emitted([((100.0, 30.0), a1, None), (a1, b1, arc1)])
    a2, b2, arc2 = _arc(30.0, 270, 180)
    low = _emitted([((100.0, -30.0), a2, None), (a2, b2, arc2)])
    return top, low


def _editor_ok(pl):
    for i, fl in pl.fillets.items():
        g = model_ops.fillet_geo(pl.pts_pdf[i - 1], pl.pts_pdf[i], pl.pts_pdf[i + 1], fl["r_px"])
        assert g and not g["clamped"]
        assert math.dist(g["t1"], fl["a"]) < 1e-6 and math.dist(g["t2"], fl["b"]) < 1e-6


def test_emitidas_curva_partida_en_su_hueco_es_una_ruta():
    top, low = _u_halves()
    pts_in = {(round(x, 6), round(y, 6)) for p in (top, low) for x, y in p.pts_pdf}
    arcs_in = {(round(f["center"][0], 6), round(f["center"][1], 6), f["r_px"])
               for p in (top, low) for f in p.fillets.values()}
    gone = join_emitted([top, low])
    assert gone == [low]
    assert top.pts_pdf[0] == (100.0, 30.0) and top.pts_pdf[-1] == (100.0, -30.0)
    assert {(round(x, 6), round(y, 6)) for x, y in top.pts_pdf} == pts_in      # nada inventado ni movido
    k = min(range(len(top.pts_pdf)), key=lambda i: math.dist(top.pts_pdf[i], (-30.0, 0.0)))
    assert top.kinds[k] == "bend" and top.kinds[0] == top.kinds[-1] == "end"
    assert {(round(f["center"][0], 6), round(f["center"][1], 6), f["r_px"])
            for f in top.fillets.values()} == arcs_in
    assert top.n_segments == 2
    _editor_ok(top)                                   # el editor dibuja los mismos arcos (a/b invertidos bien)


def test_emitidas_no_se_unen_si_no_es_la_misma_trayectoria():
    def fresh():
        return list(_u_halves())
    a, b = fresh(); b.kinds[-1] = "cut"                              # borde de la vista
    assert join_emitted([a, b]) == []
    a, b = fresh(); b.layer_ocg = "otra"                             # otra capa
    assert join_emitted([a, b]) == []
    a, b = fresh(); b.abandoned = True                               # otro estado (AB)
    assert join_emitted([a, b]) == []
    a, b = fresh()
    ramal = _E([(-30.0, 0.0), (-80.0, 0.0)], ["junction", "end"])    # «Y»: tres extremos
    assert join_emitted([a, b, ramal]) == []
    a, b = fresh()
    pasa = _E([(-30.0, -50.0), (-30.0, 50.0)], ["end", "end"])       # una línea pasa por el nodo
    assert join_emitted([a, b, pasa]) == []
    # vuelta cerrada > 100°: dos líneas que se juntan en «V», no una trayectoria
    v1 = _E([(0.0, 0.0), (100.0, 0.0)], ["end", "junction"])
    v2 = _E([(100.0, 0.0), (100 - 100 * math.cos(math.radians(30)), 50.0)], ["junction", "end"])
    assert join_emitted([v1, v2]) == []
    # lazo: dos piezas que ya comparten las dos puntas (contorno de un tubo)
    l1 = _E([(0.0, 0.0), (0.0, 100.0), (17.0, 100.0), (17.0, 0.0)], ["vault", "corner", "corner", "vault"])
    l2 = _E([(0.0, 0.0), (17.0, 0.0)], ["vault", "vault"])
    assert join_emitted([l1, l2]) == []


def test_emitidas_esquina_de_grado_2_como_build_routes():
    """Mismo umbral que `_pair` en grado 2 (≤100°) con el rumbo local; con «tee», ≤35°."""
    a = _E([(0.0, 0.0), (100.0, 0.0)], ["end", "bend"])
    b = _E([(100.0, 0.0), (100.0, 80.0)], ["bend", "end"])
    assert len(join_emitted([a, b])) == 1 and a.pts_pdf == [(0.0, 0.0), (100.0, 0.0), (100.0, 80.0)]
    a = _E([(0.0, 0.0), (100.0, 0.0)], ["end", "tee"])
    b = _E([(100.0, 0.0), (100.0, 80.0)], ["tee", "end"])
    assert join_emitted([a, b]) == []


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_du06_h5_telecom_la_u_sigue_su_trayectoria():
    """Caja → vertical → toda la «U» → recta de arriba: UNA ruta, con los mismos codos
    que las polilíneas sin unir (la curva no cambia) y dibujables por el editor."""
    import recognition as rec
    r = rec.recognize_page(PDF, 4, utility="TELECOM", zoom=1.0)
    duct = [p for p in r.polylines_joined if p.layer_ocg.endswith("N-COMM-DUCT-BANK-PL")]
    raw = [p for p in r.polylines_raw if p.layer_ocg.endswith("N-COMM-DUCT-BANK-PL")]
    low = (663.06, 1251.96)
    u = [p for p in duct if any(math.dist(q, low) < 0.05 for q in p.pts_pdf)]
    assert len(u) == 1
    u = u[0]
    ends = sorted([u.pts_pdf[0], u.pts_pdf[-1]])
    assert math.dist(ends[0], (691.92, 1132.08)) < 0.05 and math.dist(ends[1], (755.82, 1195.86)) < 0.05
    assert {u.kinds[0], u.kinds[-1]} == {"vault", "end"}
    assert len(u.fillets) == 5 and u.n_segments == 2

    def arcs(pls):
        return sorted((round(f["center"][0], 3), round(f["center"][1], 3), round(f["r_px"], 3))
                      for p in pls for f in p.fillets.values())
    halves = [p for p in raw if any(math.dist(q, low) < 0.05 for q in p.pts_pdf)]
    assert len(halves) == 2 and arcs([u]) == arcs(halves)             # los mismos codos: la curva no cambia
    for i, fl in u.fillets.items():
        g = model_ops.fillet_geo(u.pts_pdf[i - 1], u.pts_pdf[i], u.pts_pdf[i + 1], fl["r_px"])
        assert g and not g["clamped"]
        assert math.dist(g["t1"], fl["a"]) < 0.05 and math.dist(g["t2"], fl["b"]) < 0.05
