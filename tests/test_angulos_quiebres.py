"""Quiebres a pasos de 0.25° (`recognition_angulos`, pedido del usuario 2026-10-17).

«En cada quiebre, en lugar de generar un ángulo con decimales raros (45.648°), que se
ajuste por pasos de 0.25°: sale más preciso el dibujo y más real, también en los codos».
1. Geometría pura: cada deflexión queda múltiplo EXACTO de 0.25°, moviendo lo mínimo; lo
   que ya era múltiplo (90°, recta) no se mueve; los contactos (T, punta con punta, lazo)
   siguen igual; los codos conservan su radio (o su tangencia en el nodo).
2. Reconocimiento real: PDF con capas (guiones) y mapa SIN capas (trazo continuo).
"""
import math
import os
from types import SimpleNamespace

import pytest

from nucleo import model_ops
from reconocimiento import recognition_angulos as RA

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _pl(pts, kinds=None, fillets=None):
    kinds = kinds or (["end"] + ["bend"] * (len(pts) - 2) + ["end"])
    return SimpleNamespace(pts_pdf=[tuple(map(float, p)) for p in pts], kinds=list(kinds), fillets=fillets or {})


def _polar(p, ang_deg, L):
    a = math.radians(ang_deg)
    return (p[0] + L * math.cos(a), p[1] + L * math.sin(a))


def _camino(p0, rumbos_largos):
    pts = [p0]
    for ang, L in rumbos_largos:
        pts.append(_polar(pts[-1], ang, L))
    return pts


def _quiebres(pts):
    return [RA.deflexion_deg(pts[k - 1], pts[k], pts[k + 1]) for k in range(1, len(pts) - 1)]


def _exactos(pts, tol=1e-6, zoom=1.0):
    """Cada quiebre a pasos de 0.25° (un micro-tramo cuenta como un punto)."""
    return all(RA.fuera_de_paso_deg(d) <= tol for d in RA.deflexiones_deg(pts, RA.MICRO_PT * zoom))


def _dist_seg(q, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


def _dist_linea(q, pts):
    return min(_dist_seg(q, a, b) for a, b in zip(pts, pts[1:]))


# ─────────────────────────── geometría pura ───────────────────────────
def test_cada_quiebre_queda_a_pasos_de_un_cuarto_de_grado():
    pts = _camino((100.0, 100.0), [(3.1, 300.0), (48.748, 180.0), (61.05, 220.0), (-30.37, 150.0)])
    pl = _pl(pts)
    antes = _quiebres(pts)
    assert any(RA.fuera_de_paso_deg(d) > 0.05 for d in antes)        # 45.648°, 12.302°…
    aj = RA.ajustar_quiebres([pl], 1.0)
    assert _exactos(pl.pts_pdf)
    assert aj.quiebres == 3 and not aj.sin_ajustar
    for d0, d1 in zip(antes, _quiebres(pl.pts_pdf)):
        assert abs(d1 - d0) <= RA.PASO_DEG / 2 + 1e-9                 # el múltiplo más cercano
    # se aparta poco de la línea de antes (tramos de 150–300 px: ≤ 0.3 px) y nada cambia de tipo
    assert all(_dist_linea(q, pts) <= 0.3 for q in pl.pts_pdf)
    assert len(pl.pts_pdf) == len(pts) and pl.kinds == ["end", "bend", "bend", "bend", "end"]
    assert 0 < aj.max_desvio_px <= 0.3


def test_lo_que_ya_era_multiplo_no_se_mueve():
    pts = _camino((10.0, 20.0), [(17.3, 200.0), (17.3, 50.0), (107.3, 120.0), (62.3, 80.0), (73.55, 90.0)])
    pl = _pl(pts)                          # recta con un vértice, 90°, −45°, 11.25° (rumbo cualquiera)
    aj = RA.ajustar_quiebres([pl], 1.0)
    assert aj.quiebres == 0 and not aj.movidos
    assert all(math.dist(p, q) <= 1e-9 for p, q in zip(pts, pl.pts_pdf))


def test_un_tramo_suelto_no_tiene_quiebre_que_ajustar():
    pl = _pl([(0.0, 0.0), (300.0, 37.77)])
    RA.ajustar_quiebres([pl], 1.0)
    assert pl.pts_pdf == [(0.0, 0.0), (300.0, 37.77)]


def test_la_T_sigue_sobre_su_linea():
    tronco = _pl(_camino((0.0, 0.0), [(0.4, 400.0), (20.83, 300.0)]))
    # ramal que nace a mitad del primer tramo del tronco
    pie = (200.0, 200.0 * math.tan(math.radians(0.4)))
    ramal = _pl(_camino(pie, [(91.7, 150.0), (128.31, 120.0)]), ["tee", "bend", "end"])
    RA.ajustar_quiebres([tronco, ramal], 1.0)
    assert _exactos(tronco.pts_pdf) and _exactos(ramal.pts_pdf)
    a, b = tronco.pts_pdf[0], tronco.pts_pdf[1]
    assert _dist_seg(ramal.pts_pdf[0], a, b) <= 1e-4                  # sigue sobre el tronco


def test_punta_con_punta_comparten_rejilla():
    """Dos tramos de una ruta (o una «Y») que se tocan en la punta: el ángulo ENTRE ellos
    también es un quiebre (un codo en Civil 3D)."""
    a = _pl(_camino((0.0, 0.0), [(5.0, 250.0), (37.21, 180.0)]))
    b = _pl([a.pts_pdf[-1]] + _camino(a.pts_pdf[-1], [(67.58, 200.0), (66.0, 90.0)])[1:])
    RA.ajustar_quiebres([a, b], 1.0)
    assert _exactos(a.pts_pdf) and _exactos(b.pts_pdf)
    assert math.dist(a.pts_pdf[-1], b.pts_pdf[0]) <= 1e-4
    entre = RA.deflexion_deg(a.pts_pdf[-2], a.pts_pdf[-1], b.pts_pdf[1])
    assert RA.fuera_de_paso_deg(entre) <= 1e-6


def test_codo_conserva_su_radio():
    pts = _camino((0.0, 0.0), [(0.0, 300.0), (47.648, 260.0)])
    r = 60.0
    g = model_ops.fillet_geo(pts[0], pts[1], pts[2], r)
    pl = _pl(pts, ["end", "fillet", "end"], {1: {"a": g["t1"], "b": g["t2"], "center": g["center"], "r_px": r}})
    RA.ajustar_quiebres([pl], 1.0)
    q = pl.pts_pdf
    assert _exactos(q)
    assert abs(abs(_quiebres(q)[0]) - 47.75) <= 1e-6
    fl = pl.fillets[1]
    g2 = model_ops.fillet_geo(q[0], q[1], q[2], r)
    assert fl["r_px"] == pytest.approx(r)
    for k1, k2 in (("a", "t1"), ("b", "t2"), ("center", "center")):
        assert math.dist(fl[k1], g2[k2]) <= 1e-6                       # lo que dibuja el editor


def test_codo_que_muere_en_un_nodo_sigue_en_el_nodo():
    pts = _camino((0.0, 0.0), [(0.0, 300.0), (33.33, 80.0)])
    delta = math.radians(33.33)
    r = math.dist(pts[1], pts[2]) / math.tan(delta / 2)              # tangencia justo en el nodo
    g = model_ops.fillet_geo(pts[0], pts[1], pts[2], r)
    assert math.dist(g["t2"], pts[2]) <= 1e-6
    pl = _pl(pts, ["end", "fillet", "tee"], {1: {"a": g["t1"], "b": g["t2"], "center": g["center"],
                                                  "r_px": r, "node_b": True}})
    RA.ajustar_quiebres([pl], 1.0)
    assert _exactos(pl.pts_pdf)
    assert math.dist(pl.fillets[1]["b"], pl.pts_pdf[2]) <= 1e-6        # sigue muriendo en el nodo


@pytest.mark.parametrize("origen", [(0.0, 0.0), (2350.0, 3570.0)])
def test_dos_lineas_encimadas_no_disparan_el_punto(origen):
    """La punta de una línea sobre DOS líneas casi paralelas (la misma línea dibujada dos veces,
    DU06 h.4 telecom): no se pide la intersección de las dos (se iba a cientos de px). Lejos
    del origen de la hoja, como en un plano real: promediar los dos contactos con normales que
    difieren unos grados no puede depender de dónde está el origen (se iba 72 px)."""
    ox, oy = origen
    mv = lambda pts: [(x + ox, y + oy) for x, y in pts]  # noqa: E731
    l1 = _pl(mv([(0.0, 0.0), (400.0, 0.0), (520.0, 80.0)]))
    # la otra copia cruza la primera a 4° justo en (150, 0) y termina en la misma punta
    a4 = math.radians(4.0)
    l2 = _pl(mv([(150.0 - 120 * math.cos(a4), -120 * math.sin(a4)),
                 (150.0 + 150 * math.cos(a4), 150 * math.sin(a4)), (520.0, 80.0)]))
    # la rama nace en ese cruce: su punta queda sobre las DOS (ya ajustadas)
    rama = _pl(mv(_camino((150.0, 0.0), [(87.3, 100.0), (130.9, 90.0)])), ["tee", "bend", "end"])
    aj = RA.ajustar_quiebres([l1, l2, rama], 1.0)
    for pl in (l1, l2, rama):
        assert _exactos(pl.pts_pdf)
    assert aj.max_desvio_px <= 1.0 and not aj.sin_ajustar
    assert math.dist(rama.pts_pdf[0], (150.0 + ox, oy)) <= 1.0


def test_lazo_cerrado_sigue_cerrado():
    pts = _camino((0.0, 0.0), [(0.0, 200.0), (93.7, 150.0), (181.3, 190.0)])
    pts.append(pts[0])
    pl = _pl(pts)
    RA.ajustar_quiebres([pl], 1.0)
    assert math.dist(pl.pts_pdf[0], pl.pts_pdf[-1]) <= 1e-6
    assert _exactos(pl.pts_pdf)


def test_micro_tramo_entre_dos_buzones_cuenta_como_un_punto():
    """Mapas de Phoenix: dos vértices de buzón a 0.02–0.1 pt. Su «rumbo» es ruido: girarlo lo
    daba vuelta y la línea quedaba sin ajustar. Ahora el micro-tramo se mueve entero y el
    ángulo exacto es el de los tramos de verdad a cada lado."""
    a = _camino((0.0, 0.0), [(2.37, 300.0)])
    b = _polar(a[-1], 151.0, 0.08)                                  # 0.08 px «hacia atrás»
    pts = a + [b] + _camino(b, [(38.61, 250.0), (12.2, 200.0)])[1:]
    pl = _pl(pts, ["end", "vault", "vault", "bend", "end"])
    aj = RA.ajustar_quiebres([pl], 1.0)
    assert not aj.sin_ajustar and _exactos(pl.pts_pdf)
    q = pl.pts_pdf
    assert math.dist(q[1], q[2]) == pytest.approx(0.08, abs=1e-9)     # el micro-tramo, igual
    assert all(_dist_linea(p, pts) <= 0.5 for p in q)


def test_bovedas_siguen_a_su_vertice():
    pl = _pl(_camino((0.0, 0.0), [(0.0, 300.0), (41.41, 200.0)]), ["end", "vault", "end"])
    viejo = pl.pts_pdf[1]
    aj = RA.ajustar_quiebres([pl], 1.0)
    assert RA.reubicar([viejo, (999.0, 999.0)], aj.movidos) == [pl.pts_pdf[1], (999.0, 999.0)]


# ─────────────────────────── reconocimiento real ───────────────────────────
fitz = pytest.importorskip("fitz")

from reconocimiento import recognition as rec  # noqa: E402


def _guiones(page, pts, ocg, dash=12.0, gap=6.0):
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        t = 0.0
        while t < L:
            e = min(L, t + dash)
            page.draw_line((a[0] + ux * t, a[1] + uy * t), (a[0] + ux * e, a[1] + uy * e),
                           color=(0, 0, 0), width=0.7, oc=ocg)
            t = e + gap


def test_pdf_con_capas_quiebres_a_pasos(tmp_path):
    doc = fitz.open()
    ocg = doc.add_ocg("C-ELEC-UNGD-E", on=True)
    page = doc.new_page(width=700, height=500)
    linea = _camino((60.0, 100.0), [(1.3, 250.0), (34.648, 180.0), (88.2, 150.0)])   # giros de 33.35° y 53.55°
    _guiones(page, linea, ocg)
    page.insert_text((30, 480), 'SCALE: 1"=20\'', fontsize=8)
    target = tmp_path / "capas.pdf"
    doc.save(target)
    r = rec.recognize_page(target, utility="ELECTRICO", zoom=1.0, scale_ft_per_pt=1.0)
    lineas = [pl for pl in r.drawable if len(pl.pts_pdf) >= 3]
    assert lineas
    for pl in lineas:
        assert _exactos(pl.pts_pdf)
        assert all(_dist_linea(q, linea) <= 1.0 for q in pl.pts_pdf)     # sobre la tinta
    assert any(w.startswith("Ángulos de los quiebres a pasos de 0.25°") for w in r.warnings)


def test_mapa_sin_capas_quiebres_a_pasos(tmp_path):
    from hoja import pdf_layers
    doc = fitz.open()
    page = doc.new_page(width=700, height=500)
    linea = _camino((60.0, 400.0), [(-2.2, 260.0), (-38.77, 170.0), (-91.4, 140.0)])
    sh = page.new_shape()
    sh.draw_polyline(linea)
    sh.finish(color=(0, 0, 0), width=0.73, closePath=False)
    sh.commit()
    target = tmp_path / "mapa.pdf"
    doc.save(target)
    with fitz.open(target) as d:
        estilo = next(L["name"] for L in pdf_layers.page_layers(d, 0, letters=False)
                      if L["short"].startswith("Negro 0.73 pt"))
    for util in ("AGUA", "ALCANTARILLADO"):
        r = rec.recognize_page(target, utility=util, zoom=1.0, scale_ft_per_pt=1.0,
                               layer_roles={rec.ROLE_LINEAS: [estilo], rec.ROLE_BUZONES: []})
        assert r.drawable
        for pl in r.drawable:
            assert _exactos(pl.pts_pdf)
            assert all(_dist_linea(q, linea) <= 0.5 for q in pl.pts_pdf)
