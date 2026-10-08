"""Codos muy abiertos (giro ≥ WIDE_FILLET_DEG) → dos codos sobre el MISMO arco.

Pedido del usuario 2026-09-30 (DU06 h.5, telecom `N-COMM-DUCT-BANK-PL`): una curva
casi en «U» (178.7°, r = 28 px) tenía la esquina del codo —intersección de las
tangentes— a 2514 px del arco, fuera de la hoja: en la vista previa se veía un
«trazo gigante». Se escribe como dos codos de Δ/2 unidos en el punto medio del arco;
el arco dibujado (A, B, centro, radio) no cambia y el editor lo dibuja igual.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from nucleo import model_ops as MO  # noqa: E402
from reconocimiento import recognition_trace as trace_mod  # noqa: E402

DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"


def _fillet(turn_deg, r=10.0, L=600.0):
    """Esquina C=(0,0), recta de llegada desde P=(L,0), giro `turn_deg`."""
    phi = math.radians(180.0 - turn_deg)            # ángulo interior entre las patas
    P, C, N = (L, 0.0), (0.0, 0.0), (L * math.cos(phi), L * math.sin(phi))
    g = MO.fillet_geo(P, C, N, r)
    return [P, C, N], {"a": g["t1"], "b": g["t2"], "center": g["center"], "r_px": r,
                       "loose": False, "dev_px": 0.1, "node_a": False, "node_b": False}


def test_codo_de_176_grados_se_parte_en_dos_sobre_el_mismo_arco():
    pts, f = _fillet(176.0)
    assert math.dist(pts[1], f["a"]) > 250                  # la esquina original, lejísimos
    P, K, F = trace_mod.split_wide_fillets(pts, ["end", "fillet", "end"], {1: f})
    assert K == ["end", "fillet", "bend", "fillet", "end"] and sorted(F) == [1, 3]
    M = P[2]
    assert math.dist(M, f["center"]) == pytest.approx(10.0, abs=1e-9)      # sobre el círculo
    f1, f2 = F[1], F[3]
    assert f1["a"] == f["a"] and f2["b"] == f["b"] and f1["b"] == M == f2["a"]
    assert f1["split_b"] and f2["split_a"] and f1["r_px"] == f2["r_px"] == 10.0
    # esquinas cerca: T = r·tan(44°) ≈ r
    for i, fl in ((1, f1), (3, f2)):
        assert math.dist(P[i], fl["a"]) == pytest.approx(10.0 * math.tan(math.radians(44.0)), rel=1e-6)
    # el editor (= plugin) dibuja cada mitad EXACTAMENTE sobre el arco reconocido
    for i, fl in ((1, f1), (3, f2)):
        g = MO.fillet_geo(P[i - 1], P[i], P[i + 1], fl["r_px"])
        assert g and not g["clamped"]
        assert math.dist(g["t1"], fl["a"]) < 1e-6 and math.dist(g["t2"], fl["b"]) < 1e-6
        assert math.dist(g["center"], f["center"]) < 1e-6


def test_codo_de_casi_180_que_el_editor_no_podia_dibujar():
    """Con Δ > 179° `fillet_geo` no dibuja el codo (ángulo interior < 1°); partido sí."""
    phi = math.radians(0.5)                                  # giro 179.5°
    pts = [(5000.0, 0.0), (0.0, 0.0), (5000.0 * math.cos(phi), 5000.0 * math.sin(phi))]
    g0 = MO.fillet_geo(pts[0], pts[1], pts[2], 10.0)
    assert g0 is None
    # A/B/centro del codo de 179.5° (tangente a las dos rectas)
    T = 10.0 / math.tan(phi / 2)
    f = {"a": (T, 0.0), "b": (T * math.cos(phi), T * math.sin(phi)),
         "center": (T, 10.0), "r_px": 10.0, "loose": False, "dev_px": 0.0, "node_a": False, "node_b": False}
    P, K, F = trace_mod.split_wide_fillets(pts, ["end", "fillet", "end"], {1: f})
    assert len(P) == 5 and all(MO.fillet_geo(P[i - 1], P[i], P[i + 1], 10.0) for i in (1, 3))


def test_codos_que_no_se_tocan():
    pts, f = _fillet(120.0)                                  # por debajo del umbral
    assert trace_mod.split_wide_fillets(pts, ["end", "fillet", "end"], {1: f}) == \
        (pts, ["end", "fillet", "end"], {1: f})
    pts, f = _fillet(170.0)                                  # otro codo pegado: recta compartida
    P = [pts[0], pts[1], pts[2], (pts[2][0] + 50, pts[2][1] + 400)]
    K = ["end", "fillet", "fillet", "end"]
    assert trace_mod.split_wide_fillets(P, K, {1: f, 2: dict(f)})[0] == P
    pts, f = _fillet(170.0)                                  # la tangencia no entra en la recta
    short = [(f["a"][0] * 0.5, 0.0), pts[1], pts[2]]         # P antes de A: el editor lo recortaría
    assert trace_mod.split_wide_fillets(short, ["end", "fillet", "end"], {1: f})[0] == short


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no está en el repo")
def test_du06_h5_telecom_la_u_queda_en_dos_codos():
    from reconocimiento import recognition as rec
    r = rec.recognize_page(DU06, 4, utility="TELECOM", zoom=1.0)
    fil = [(pl, i, f) for pl in r.drawable for i, f in pl.fillets.items()]
    W, H = 2592, 1728                                        # hoja 36×24 in a 72 dpi
    for pl, i, f in fil:                                     # ninguna esquina fuera de la hoja
        x, y = pl.pts_pdf[i]
        assert -50 < x < W + 50 and -50 < y < H + 50, (pl.layer_ocg, pl.pts_pdf[i])
    # la «U» (centro ≈ (663.8, 1223.7), r ≈ 28.3 px): la única partida, dos codos del mismo círculo
    u = [(pl, i, f) for pl, i, f in fil if f.get("split_a") or f.get("split_b")]
    assert len(u) == 2 and u[0][0] is u[1][0]
    pl = u[0][0]
    (_, i1, f1), (_, i2, f2) = sorted(u, key=lambda t: t[1])
    assert i2 == i1 + 2 and pl.kinds[i1 + 1] == "bend" and f1["b"] == f2["a"] == pl.pts_pdf[i1 + 1]
    assert math.dist(f1["center"], (663.8, 1223.7)) < 0.2 and f1["center"] == f2["center"]
    assert f1["r_px"] == pytest.approx(28.27, abs=0.05) and f1["r_px"] == f2["r_px"]
    for i, fl in ((i1, f1), (i2, f2)):                       # editor = reconocimiento
        g = MO.fillet_geo(pl.pts_pdf[i - 1], pl.pts_pdf[i], pl.pts_pdf[i + 1], fl["r_px"])
        assert g and not g["clamped"]
        assert math.dist(g["t1"], fl["a"]) < 0.05 and math.dist(g["t2"], fl["b"]) < 0.05


# ─── DU10 h.3 eléctrico: dos curvas que quedaban como polilínea (2026-09-30) ───
DU10 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf")


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h3_electrico_ninguna_curva_queda_como_polilinea():
    """(1) `C-ELEC-UNGD-E`: codo chico (r = 10.8 pt) a guiones. El linetype deja casi
    la mitad del arco en huecos y la cobertura solo contaba el guión curvo del medio
    (35 %); la última cuerda del arco + la recta vertical eran un «trozo» de 3 puntos
    y el codo se apoyaba en el extremo de la línea. Ahora: tangente a la horizontal
    y = 633.7 y a la vertical x = 910.08 del PDF.
    (2) `C-ELEC-3MI-UGND-N`: curva r = 126 pt que la 2.ª pasada encontraba, pero
    `fit_continuous` descartaba el reajuste del tramo final porque el tee del extremo
    se corría a la tangencia de su línea (como sin parche)."""
    from reconocimiento import recognition as rec
    r = rec.recognize_page(DU10, 2, utility="ELECTRICO", zoom=1.0)
    assert not any("curve" in pl.kinds for pl in r.drawable)
    fil = [(pl, i, f) for pl in r.drawable for i, f in pl.fillets.items()]

    def at(C, tol=0.3):
        got = [x for x in fil if math.dist(x[0].pts_pdf[x[1]], C) < tol]
        assert len(got) == 1, (C, [x[0].pts_pdf[x[1]] for x in fil if math.dist(x[0].pts_pdf[x[1]], C) < 20])
        return got[0]
    pl, i, f = at((910.08, 633.78))
    assert f["r_px"] == pytest.approx(10.82, abs=0.1) and not f["loose"] and f["dev_px"] < 0.1
    assert abs(f["a"][1] - 633.72) < 0.1 and abs(f["b"][0] - 910.08) < 0.1        # tangencias sobre la tinta
    pl2, i2, f2 = at((1367.87, 670.0), tol=0.5)
    assert f2["r_px"] == pytest.approx(126.1, abs=0.5) and not f2["loose"] and f2["dev_px"] < 0.1
    for p, k, fl in ((pl, i, f), (pl2, i2, f2)):                                 # editor = reconocimiento
        g = MO.fillet_geo(p.pts_pdf[k - 1], p.pts_pdf[k], p.pts_pdf[k + 1], fl["r_px"])
        assert g and not g["clamped"]
        assert {round(v, 2) for v in (math.dist(g["t1"], fl["a"]), math.dist(g["t2"], fl["b"]))} <= {0.0, 0.01}


DU08 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_recta_escondida_solo_la_que_llega_al_fin_de_la_linea():
    """La recta «escondida» en un guión de dos cuerdas (arco que muere dentro del
    guión) solo sirve de recta del codo si llega al FIN de la línea. h.22: en una
    curva en «S» esa recta está ENTRE los dos arcos y usarla le quitaba las anclas al
    codo que ya salía bien (r = 127 pt en (527.2, 907.2)). h.40: la curva que muere en
    el guión que llega al extremo (548 → 572) ahora es codo, tangente a esa recta."""
    from reconocimiento import recognition as rec
    r = rec.recognize_page(DU08, 21, utility="ELECTRICO", zoom=1.0)
    near = [f for pl in r.drawable for i, f in pl.fillets.items() if math.dist(pl.pts_pdf[i], (527.2, 907.2)) < 1.0]
    assert len(near) == 1 and near[0]["r_px"] == pytest.approx(127.0, abs=1.0)
    r = rec.recognize_page(DU08, 39, utility="ELECTRICO", zoom=1.0)
    (pl, i, f), = [(pl, i, f) for pl in r.drawable for i, f in pl.fillets.items()
                   if math.dist(pl.pts_pdf[i], (534.1, 1141.5)) < 1.0]
    assert f["r_px"] == pytest.approx(124.9, abs=0.5) and not f["loose"]
    assert abs(f["b"][1] - 1141.44) < 0.05 and pl.pts_pdf[-1] == pytest.approx((572.04, 1141.38), abs=0.05)


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h35_telecom_una_curva_un_codo_y_llega_al_tee():
    """La tinta es UN arco (r ≈ 116 pt: (1231, 803), (1203, 847), (1140, 880) a 116 ± 0.3
    del mismo centro). Antes salían dos codos aproximados (desvío 0.65 pt) y la línea
    terminaba a 7.7 pt del tee de la horizontal; ahora un codo exacto que muere en ese tee."""
    from reconocimiento import recognition as rec
    r = rec.recognize_page(DU08, 34, utility="TELECOM", zoom=1.0)
    pls = [pl for pl in r.drawable if pl.pts_pdf and math.dist(pl.pts_pdf[0], (1237.7, 748.2)) < 1.0]
    assert len(pls) == 1
    pl = pls[0]
    assert len(pl.fillets) == 1
    (f,) = pl.fillets.values()
    assert f["r_px"] == pytest.approx(116.2, abs=0.5) and f["dev_px"] < 0.3
    tee = [q for o in r.drawable if o is not pl for q in o.pts_pdf if math.dist(q, pl.pts_pdf[-1]) < 0.05]
    assert tee, pl.pts_pdf[-1]                                  # el extremo ES el vértice de la otra línea
