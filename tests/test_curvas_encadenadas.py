"""Reporte del usuario 2026-09-29 (DU06 h.4, las cuatro imágenes):

1. Curva en «S» sin recta entre medio (telecom `-E`, derecha → izquierda → derecha, la
   del medio compartida con la `-D`): quedaba en cuerdas. Ahora cada arco es un codo
   tangente al arco vecino (`recognition_arc_chain.common_tangent`).
2. Curva abierta de drenaje reconocida hasta la mitad y el resto en quiebres: la 1.ª
   pasada tomó por recta una cuerda de la propia curva. Ahora un codo que se queda
   CORTO frente a su tinta se rehace con la tinta (un solo arco de bóveda a bóveda).
3. Línea doble: el banco de ductos viene dibujado DOS veces en la misma capa con el
   linetype desfasado (`recognition_dupink`): ahora es una sola línea.
4. Línea cortada en el texto «105+00»: la letra «TE» del linetype cae entre el fin de un
   tramo curvo y el guión siguiente; la unión de frente con letra en el hueco vale en
   todas las utilidades (antes solo en alcantarillado).
"""
import math
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from reconocimiento import recognition as rec
from reconocimiento import recognition_arc_chain as chain
from reconocimiento import recognition_arcs as ra
from reconocimiento import recognition_dupink as dup

SAG = 0.025          # flecha del aplanado de AutoCAD


def _arc(ctr, r, a0, a1):
    step = 2.0 * math.acos(1.0 - SAG / r)
    n = max(2, int(math.ceil(abs(a1 - a0) / step)))
    return [(ctr[0] + r * math.cos(a0 + (a1 - a0) * k / n), ctr[1] + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def _fit(pts, kinds, strokes, through=None):
    pcs, sls = ra.arc_pieces(strokes, 1.0)
    return rec.fit_fillets(pts, kinds, tol_px=1.0, arcs=pcs, ink_lines=sls, through_ink=through or {})


# ───────────────────────── curva en «S» (tangente común) ─────────────────────────
def _s_curve(r1=45.0, r2=45.0, turn=math.radians(50)):
    """Recta horizontal → arco a la derecha (r1) → arco a la izquierda (r2), tangentes
    entre sí (sin recta entre medio) → recta horizontal. Coordenadas con y hacia abajo
    como en el PDF."""
    c1 = (100.0, r1)                                    # gira hacia +y: centro debajo
    a1 = _arc(c1, r1, -math.pi / 2, -math.pi / 2 + turn)
    Q = a1[-1]
    n = (math.cos(-math.pi / 2 + turn), math.sin(-math.pi / 2 + turn))     # radio de c1 en Q
    c2 = (Q[0] + n[0] * r2, Q[1] + n[1] * r2)
    a2 = _arc(c2, r2, math.pi / 2 + turn, math.pi / 2)
    start = (0.0, 0.0)
    end = (a2[-1][0] + 100.0, a2[-1][1])
    return start, a1, a2, end, c1, c2


def test_tangente_comun_de_una_curva_inversa():
    _s, a1, a2, _e, c1, c2 = _s_curve()
    pcs, _ = ra.arc_pieces([a1 + a2[1:]], 1.0)
    groups = ra.group_arcs(pcs, a1 + a2[1:], 1.0)
    assert len(groups) == 2 and groups[0].sign != groups[1].sign
    u, Th, Tg = chain.common_tangent(groups[0], groups[1])
    assert math.dist(Th, a1[-1]) < 0.3 and math.dist(Tg, a1[-1]) < 0.3        # punto de inflexión
    assert abs(math.degrees(math.atan2(u[1], u[0])) - 50.0) < 0.5            # rumbo de la tangente


def test_curva_en_S_sin_recta_entre_medio_son_dos_codos():
    """Antes: la 2.ª pasada solo aceptaba rectas de TINTA a los lados y la «S» quedaba en
    cuerdas. Ahora: dos codos con su radio, que comparten el ancla en la inflexión."""
    start, a1, a2, end, _c1, _c2 = _s_curve()
    st = [start] + a1 + a2[1:] + [end]
    # centerline del núcleo: la curva quedó en vértices `curve`/`corner`
    pts = [start, (95.0, 0.0), a1[len(a1) // 2], a1[-1], a2[len(a2) // 2], (a2[-1][0] + 5, a2[-1][1]), end]
    kinds = ["end", "bend", "corner", "curve", "corner", "bend", "end"]
    out, k2, fil = _fit(pts, kinds, [st])
    assert len(fil) == 2, (k2, fil)
    radii = sorted(round(f["r_px"], 1) for f in fil.values())
    assert radii[0] == pytest.approx(45.0, abs=0.5) and radii[1] == pytest.approx(45.0, abs=0.5)
    i1, i2 = sorted(fil)
    assert i2 == i1 + 2                                  # esquina · ancla compartida · esquina
    assert math.dist(out[i1 + 1], a1[-1]) < 1.0          # el ancla es la inflexión
    assert not any(f["loose"] for f in fil.values())


# ───────────────────────── codo corto frente a su tinta ─────────────────────────
def test_explains_y_overshoot_miran_hasta_donde_llega_el_arco():
    ctr, r = (0.0, 0.0), 100.0
    ink = _arc(ctr, r, 0.0, math.radians(60))
    A = (r, 0.0)
    B = (r * math.cos(math.radians(30)), r * math.sin(math.radians(30)))     # arco hasta la MITAD
    assert not chain.explains(ink[: len(ink) // 5], ctr, r, B, (0.0, r))    # tinta fuera del arco
    assert chain.explains(ink[: len(ink) // 2], ctr, r, A, B)
    # la tinta sigue 30° más allá de B: se aparta de la recta r·(1−cos 30°) ≈ 13 pt
    assert chain.overshoot(ink, ctr, r, A, B) == pytest.approx(r * (1 - math.cos(math.radians(30))), abs=0.5)
    full = (r * math.cos(math.radians(60)), r * math.sin(math.radians(60)))
    assert chain.overshoot(ink, ctr, r, A, full) < 0.1


# ───────────────────────── tinta repetida con desfase ─────────────────────────
def _dash_paths(a, b, dash, gap, phase=0.0, width=0.7):
    """Guiones rectos a→b como paths de get_drawings (items 'l')."""
    L = math.dist(a, b)
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    out, t = [], -phase
    while t < L:
        t0, t1 = max(0.0, t), min(L, t + dash)
        if t1 - t0 > 0.5:
            p = (a[0] + u[0] * t0, a[1] + u[1] * t0)
            q = (a[0] + u[0] * t1, a[1] + u[1] * t1)
            out.append({"items": [("l", fitz.Point(*p), fitz.Point(*q))], "layer": "L", "width": width,
                        "rect": fitz.Rect(min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1]))})
        t += dash + gap
    return out


def _ink_len(paths):
    return sum(math.dist(it[1], it[2]) for p in paths for it in p["items"])


def test_la_misma_linea_dos_veces_desfasada_queda_una_vez():
    a, b = (0.0, 100.0), (600.0, 100.0)
    copy1 = _dash_paths(a, b, 144.0, 29.0)
    copy2 = _dash_paths(a, b, 144.0, 29.0, phase=60.0)
    out, n = dup.trim_repeated_ink(copy1 + copy2, lambda *r: fitz.Rect(*r))
    assert n > 0
    # la tinta que queda = la UNIÓN de las dos copias (nada repetido, nada perdido)
    xs = sorted((min(it[1][0], it[2][0]), max(it[1][0], it[2][0])) for p in out for it in p["items"])
    for (x0, x1), (y0, y1) in zip(xs, xs[1:]):
        assert y0 >= x1 - 0.01                           # ningún trozo encima de otro
    assert _ink_len(out) <= 600.0 + 0.01


def test_paralelas_a_2pt_y_ramales_de_una_y_no_se_tocan():
    par = _dash_paths((0.0, 100.0), (600.0, 100.0), 144.0, 29.0) + \
        _dash_paths((0.0, 102.0), (600.0, 102.0), 144.0, 29.0, phase=60.0)
    out, n = dup.trim_repeated_ink(par, lambda *r: fitz.Rect(*r))
    assert n == 0 and len(out) == len(par)
    ang = math.radians(3.0)                             # dos ramales que salen del mismo punto a 3°
    y = _dash_paths((0.0, 0.0), (300.0, 0.0), 144.0, 29.0) + \
        _dash_paths((0.0, 0.0), (300.0 * math.cos(ang), 300.0 * math.sin(ang)), 144.0, 29.0)
    out, n = dup.trim_repeated_ink(y, lambda *r: fitz.Rect(*r))
    assert n == 0


def _chain_path(pts):
    return {"items": [("l", fitz.Point(*a), fitz.Point(*b)) for a, b in zip(pts, pts[1:])], "layer": "L",
            "rect": fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts),
                              max(p[0] for p in pts), max(p[1] for p in pts))}


def test_la_misma_curva_dos_veces_se_recorta_pero_una_Y_de_curvas_no():
    """Dos copias del MISMO arco (otra fase) = tinta repetida. Dos curvas que nacen
    TANGENTES en el mismo punto y giran a lados opuestos (una «Y» de curvas: sus
    primeras cuerdas van ~3 pt a <0.25 pt, DU10 h.5) son dos líneas: no se tocan."""
    r = 45.0
    a1 = _arc((0.0, r), r, -math.pi / 2, 0.0)                        # gira a la derecha (y hacia abajo)
    a2 = _arc((0.0, r), r, -math.pi / 2 + 0.3, 0.2)                  # la misma curva, otro tramo
    out, n = dup.trim_repeated_ink([_chain_path(a1), _chain_path(a2)], lambda *q: fitz.Rect(*q))
    assert n == 1
    left = _arc((0.0, -r), r, math.pi / 2, math.pi / 2 - 1.2)       # nace en (0,0) hacia +x y gira al otro lado
    right = _arc((0.0, r), r, -math.pi / 2, -math.pi / 2 + 1.2)
    out, n = dup.trim_repeated_ink([_chain_path(left), _chain_path(right)], lambda *q: fitz.Rect(*q))
    assert n == 0


def test_dos_codos_chicos_lejanos_no_son_un_arco_grande():
    """DU10 h.9: dos codos r≈14.5 a 63 pt, uno a cada lado de una bóveda, caben en un
    círculo de r≈126 con 0.2 pt; no se funden (el radio de cada uno no es coherente)."""
    r = 14.5
    c1 = (0.0, -r); c2 = (55.0, -r)
    g1 = _arc(c1, r, math.pi / 2 + 0.25, math.pi / 2 - 0.25)
    g2 = _arc(c2, r, math.pi / 2 + 0.25, math.pi / 2 - 0.25)
    pts = [(-40.0, 0.0), (110.0, 0.0)]
    pcs, _ = ra.arc_pieces([g1, g2], 1.0)
    groups = ra.group_arcs(pcs, pts, 1.0)
    assert len(groups) == 2 and all(g.r == pytest.approx(r, abs=1.0) for g in groups)


# ───────────────────────── la hoja real (DU06 h.4) ─────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
needs_du06 = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no está en el repo")
Z = 3.5


def _fillets(res):
    return [(pl, i, f) for pl in res.drawable for i, f in (pl.fillets or {}).items()]


@needs_du06
def test_du06_h4_drenaje_curva_abierta_es_un_solo_codo():
    res = rec.recognize_page(DU06, 3, utility="DRENAJE", zoom=Z)
    pl = next(p for p in res.drawable
              if any(math.dist((x / Z, y / Z), (812.4, 1466.9)) < 1.0 for x, y in p.pts_pdf))
    kinds = list(pl.kinds)
    assert kinds.count("fillet") == 1 and "bend" not in kinds and "curve" not in kinds, kinds
    f = next(iter(pl.fillets.values()))
    assert f["r_px"] / Z == pytest.approx(144.5, abs=1.0) and not f["loose"]
    # el arco llega hasta la bóveda de la derecha (antes paraba en x≈886.8)
    ends = [(f["a"][0] / Z, f["a"][1] / Z), (f["b"][0] / Z, f["b"][1] / Z)]
    assert max(q[0] for q in ends) == pytest.approx(940.3, abs=0.5)


@needs_du06
def test_du06_h4_telecom_curva_en_S_y_curva_compartida():
    res = rec.recognize_page(DU06, 3, utility="TELECOM", zoom=Z)
    fil = _fillets(res)

    def near(x, y, tol=3.0, layer="-E"):
        return [(pl, i, f) for pl, i, f in fil
                if pl.layer_ocg.endswith(layer) and math.dist((pl.pts_pdf[i][0] / Z, pl.pts_pdf[i][1] / Z), (x, y)) <= tol]
    s1 = near(511.9, 1453.7)                              # arco a la derecha de la «S»
    s2 = near(539.5, 1488.4)                              # arco a la izquierda (el de la `-D`)
    assert s1 and s2
    assert s1[0][2]["r_px"] / Z == pytest.approx(44.4, abs=0.8)
    # el arco de la `-E` es el mismo de la `-D` (tinta compartida): ≤0.3 pt
    d = near(515.95, 1488.09, layer="-D")
    assert d
    fe, fd = s2[0][2], d[0][2]
    assert math.dist(fe["center"], fd["center"]) / Z < 0.5
    assert abs(fe["r_px"] - fd["r_px"]) / Z < 0.3


@needs_du06
def test_du06_h4_banco_de_ductos_una_sola_linea_y_continua():
    res = rec.recognize_page(DU06, 3, utility="TELECOM", zoom=Z)
    duct = [[(x / Z, y / Z) for x, y in pl.pts_pdf] for pl in res.drawable if "DUCT-BANK" in pl.layer_ocg]

    def seg_d(q, a, b):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)
    # en la zona del reporte (vertical x≈1392 → codo → diagonal → codo → horizontal)
    # ninguna polilínea corre ENCIMA de otra de la misma capa (≥10 pt a ≤1 pt)
    def inside(q):
        return 1250.0 <= q[0] <= 1420.0 and 820.0 <= q[1] <= 1115.0
    for i, P in enumerate(duct):
        for j, Q in enumerate(duct):
            if i == j:
                continue
            over = 0.0
            for a, b in zip(P, P[1:]):
                n = max(1, int(math.dist(a, b) / 2.0))
                for k in range(n):
                    q = (a[0] + (b[0] - a[0]) * (k + 0.5) / n, a[1] + (b[1] - a[1]) * (k + 0.5) / n)
                    if inside(q) and min(seg_d(q, c, d) for c, d in zip(Q, Q[1:])) <= 1.0:
                        over += math.dist(a, b) / n
            assert over < 10.0, (P[0], Q[0], over)
    # la vertical x≈1392 sigue por el codo a la diagonal (una sola polilínea)
    vert = [P for P in duct if any(abs(q[0] - 1392.1) < 0.5 and q[1] < 800 for q in P)]
    assert vert and any(q[0] < 1300 and q[1] > 1090 for q in vert[0])
    # y la línea no se corta en «105+00» (la «TE» cae bajo el texto)
    assert any(min(seg_d((1565.0, 1110.8), a, b) for a, b in zip(P, P[1:])) < 1.0 for P in duct)
