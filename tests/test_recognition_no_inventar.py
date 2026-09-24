"""«No inventar»: casos del DU08 h.21 que reportó el usuario (2026-09-24).

1. La MISMA capa dibujada dos veces (xref insertado dos veces): el núcleo
   encadenaba cada guión con su gemelo (líneas de ida y vuelta) y un tick de fin
   de tramo contaba como dos guiones, dejaba de ser «tick» y su recta se
   prolongaba 30–40 pt sin tinta hasta la línea paralela → `dedup_paths`.
2. Dos líneas que se juntan (ramales de una «Y», curvas que convergen) se
   cosían en una «V» → esquina con ángulo interior < 73° no se forma.
3. Una curva «retrocedía» 11 pt sin tinta para formar esquina → CURVE_BACKSLIDE_PT.
4. Dos ramales que mueren en T del mismo lado de una línea se unían a través de
   ella en la unión de rutas → en un nodo T solo se sigue «de frente».
"""
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")

import recognition as rec  # noqa: E402
import recognition_geom as G  # noqa: E402
import routes  # noqa: E402
from test_recognition_geom import Sheet  # noqa: E402

DU08 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")


def _interior_angles(pts):
    out = []
    for i in range(1, len(pts) - 1):
        u = (pts[i - 1][0] - pts[i][0], pts[i - 1][1] - pts[i][1])
        v = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu > 1e-6 and lv > 1e-6:
            out.append(math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / (lu * lv))))))
    return out


def test_dedup_paths_quita_solo_los_identicos():
    sh = Sheet()
    sh.line("LINES", (100, 100), (200, 100))
    sh.line("LINES", (100, 100), (200, 100))          # repetido tal cual
    sh.line("LINES", (200, 100), (100, 100))          # repetido al revés
    sh.line("LINES", (100, 100.3), (200, 100.3))      # otro trazo a 0.3 pt: se queda
    lines, _ = sh.paths()
    kept = rec.dedup_paths(lines)
    assert len(lines) == 4 and len(kept) == 2


def test_capa_duplicada_no_da_lineas_de_ida_y_vuelta():
    sh = Sheet()
    sh.dashed((100, 400), (600, 400))
    sh.dashed((100, 400), (600, 400))                 # la capa entera otra vez
    lines, vaults = sh.paths()
    res = G.reconstruct(rec.dedup_paths(lines), vaults)
    assert len(res.polylines) == 1
    assert all(a > 90 for a in _interior_angles(res.polylines[0].pts))


@pytest.mark.parametrize("dy", [60.0, 110.0, 180.0])
def test_dos_lineas_que_se_juntan_no_forman_una_v(dy):
    """Dos líneas que llegan al MISMO punto desde el mismo lado (ángulo interior
    ≈ atan(dy/300): 11°–31°) son dos líneas, no una que se devuelve."""
    sh = Sheet()
    sh.dashed((100, 400), (400, 400))
    sh.dashed((100, 400 - dy), (400, 400))
    res = sh.run()
    for pl in res.polylines:
        assert all(a >= G.CORNER_MIN_INTERIOR_DEG - 1 for a in _interior_angles(pl.pts)), pl.pts


def test_esquina_real_en_l_se_sigue_formando():
    sh = Sheet()
    sh.dashed((100, 400), (400, 400))
    sh.dashed((400, 400), (400, 150))
    res = sh.run()
    assert len(res.polylines) == 1
    assert any(k == "corner" for k in res.polylines[0].kinds)


def test_rutas_no_cosen_dos_ramales_en_una_t():
    """Dos ramales mueren en T sobre una línea que pasa, del mismo lado y
    abriéndose ~90° entre sí: antes el nodo contaba como de grado 2 y se unían."""
    P = (100.0, 100.0)
    a = G.Polyline([(40.0, 40.0), P], ["end", "tee"])
    b = G.Polyline([P, (160.0, 40.0)], ["tee", "end"])
    through = G.Polyline([(0.0, 100.0), P, (200.0, 100.0)], ["end", "tee", "end"])
    rs = routes.build_routes([a, b, through], None)
    assert not any(len(r.members) > 1 and {0, 1} <= set(r.members) for r in rs)
    # sin la T (esquina suelta de grado 2) sí sigue siendo una misma ruta
    a2 = G.Polyline([(40.0, 40.0), P], ["end", "corner"])
    b2 = G.Polyline([P, (160.0, 40.0)], ["corner", "end"])
    assert len(routes.build_routes([a2, b2], None)) == 1


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 (carpeta de pruebas) no disponible")
def test_du08_h21_electrico_sin_tramos_inventados():
    Z = 2.0
    res = rec.recognize_page(DU08, 20, utility="ELECTRICO", zoom=Z)
    doc = fitz.open(str(DU08))
    try:
        lp, _vp, _c, _k = rec.gather_paths(doc[20], lambda o: rec.classify_ocg(o, "ELECTRICO"), set(), None)
    finally:
        doc.close()
    px = lambda q: (q[0] * Z, q[1] * Z)                               # noqa: E731
    by = {}
    for p_ in lp:
        by.setdefault(p_.get("layer") or "", []).append(p_)
    ink = {lay: rec.ink_samples(rec.ink_strokes(v, px)) for lay, v in by.items()}
    boxes = []                                  # dentro de la bóveda la línea va a su nodo
    for vg in res.vaults_geo or []:
        if vg.get("corners"):
            xs = [c[0] for c in vg["corners"]]; ys = [c[1] for c in vg["corners"]]
            boxes.append((min(xs) - 3 * Z, min(ys) - 3 * Z, max(xs) + 3 * Z, max(ys) + 3 * Z))
    in_vault = lambda q: any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in boxes)  # noqa: E731
    for pl in res.drawable:
        # ninguna línea se devuelve sobre sí misma ni hace una «V» (los codos «fillet»
        # guardan la esquina de tangentes, que puede ser cerrada)
        for i, ang in enumerate(_interior_angles(pl.pts_pdf), start=1):
            if pl.kinds[i] != "fillet":
                assert ang >= 60, (pl.layer_ocg, pl.pts_pdf[i], ang)
        # todo tramo > 6 pt tiene tinta de su capa debajo
        pts_ink = ink.get(pl.layer_ocg, [])
        for i, (a, b) in enumerate(zip(pl.pts_pdf, pl.pts_pdf[1:])):
            L = math.dist(a, b) / Z
            if L <= 6 or (pl.fillets or {}).get(i) or (pl.fillets or {}).get(i + 1):
                continue
            n = max(2, int(L / 1.5))
            qs = [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(n + 1)]
            out = [q for q in qs if not in_vault(q)]
            if len(out) < 0.5 * len(qs):
                continue
            qs = out
            hit = sum(1 for q in qs if any(math.dist(q, s[:2]) <= 2 * Z for s in pts_ink))
            assert hit / len(qs) >= 0.5, (pl.layer_ocg, a, b)


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 (carpeta de pruebas) no disponible")
def test_du08_h21_una_sola_linea_llega_y_la_curva_muere_en_su_tinta():
    """Segunda revisión del usuario (2026-09-24):
    1. Bóveda 9.3×17.3 ft en (1152–1186, 1159–1222): la curva de la izquierda viene
       en DOS trazos que comparten la punta (1162.6, 1134.5); la primera mitad se
       prolongaba por su recta hasta el borde y a la bóveda llegaban dos líneas.
    2. La curva existente que viene de la izquierda muere sobre la vertical en
       (719.1, 902); se le atribuía el trozo que sigue a la diagonal (unido por la
       letra «e») y se inventaba un nodo en (721.4, 911) sin tinta."""
    Z = 2.0
    res = rec.recognize_page(DU08, 20, utility="ELECTRICO", zoom=Z)
    pls = [[(q[0] / Z, q[1] / Z) for q in pl.pts_pdf] for pl in res.drawable]
    # 1. una sola línea cruza el borde superior de la bóveda por el lado izquierdo
    left_top = [pts for pts in pls
                if any(1154 <= x <= 1165 and 1156 <= y <= 1160 for x, y in pts)]
    assert len(left_top) == 1, left_top
    # 2. ningún vértice en el punto inventado; la curva termina en T sobre la vertical
    assert not any(math.dist(p, (721.4, 911.0)) <= 2.0 for pts in pls for p in pts)
    assert any(math.dist(pts[k], (719.1, 902.0)) <= 1.5 and math.dist(pts[k - 1], (719.2, 891.9)) <= 1.5
               for pts in pls for k in range(1, len(pts)))
    # …y la diagonal sigue hasta el círculo (718.8, 925.4)
    assert any(math.dist(pts[0], (718.8, 925.4)) <= 1.5 or math.dist(pts[-1], (718.8, 925.4)) <= 1.5
               for pts in pls if any(p[0] > 735 for p in pts))


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 (carpeta de pruebas) no disponible")
def test_du08_h49_ticks_y_curvas_sin_tramos_inventados():
    """Tercera revisión del usuario (2026-09-24), DU08 h.49:
    1. La curva termina en su tick «|» horizontal en (702.4, 1225): el tick y una
       patita del símbolo vecino se estiraban ~29 pt en blanco hasta una esquina
       en (666, 1225) → «T» inexistente.
    2. Dos líneas de capas distintas terminan cada una en su tick, pegados en
       x≈895: se tienen que ver LAS DOS T (1275.8 y 1284.8).
    3. El último tramo recto de la curva que muere sobre la vertical (668,982)→
       (661,989) se tomaba por una barra «/»; la curva se unía a una patita a
       17 pt en (667, 983–1004) sin tinta."""
    Z = 2.0
    res = rec.recognize_page(DU08, 48, utility="ELECTRICO", zoom=Z)
    pls = [[(q[0] / Z, q[1] / Z) for q in pl.pts_pdf] for pl in res.drawable]
    segs = [(a, b) for pts in pls for a, b in zip(pts, pts[1:])]

    def seg_through(p, tol=1.0):
        for a, b in segs:
            L = math.dist(a, b)
            if L < 1e-6:
                continue
            t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (L * L)
            if 0 < t < 1 and math.dist(p, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) <= tol:
                return True
        return False
    # 1. nada cruza el papel en blanco entre el tick y la vertical
    assert not seg_through((680.0, 1225.0)) and not seg_through((665.4, 1240.0))
    # 2. los dos ticks con su T
    for tick_x, tee_y, y0, y1 in ((895.0, 1284.8, 1277.6, 1292.0), (894.7, 1275.8, 1268.6, 1283.0)):
        assert any(len(pts) == 3 and math.dist(pts[1], (tick_x, tee_y)) <= 0.5
                   and {round(pts[0][1]), round(pts[2][1])} == {round(y0), round(y1)} for pts in pls)
    # 3. no hay tramo en (667, 990); la curva llega a su PUNTA, cortada por el clip
    #    de la vista en x=661.14 (4.ª revisión: «debe iniciar desde la punta»)
    assert not seg_through((667.4, 993.0))
    assert any(math.dist(end, (661.1, 988.8)) <= 0.5 for pts in pls for end in (pts[0], pts[-1])
               if any(p[0] > 685 for p in pts))


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 (carpeta de pruebas) no disponible")
def test_du08_h49_borde_de_la_vista_y_letras_partidas():
    """Cuarta revisión del usuario (2026-09-24), DU08 h.49: el clip de la vista está
    en x=661.14 y la referencia ya viene recortada ahí.
    1. Las líneas que llegan al borde terminan en su PUNTA (nodo `cut`), no en una T
       con la vertical que cruzan: (661.1, 958.8) y (661.1, 988.8).
    2. La vertical corre SOBRE el borde; su último guión (x=661.10, 1326–1333) se
       descartaba por quedar 0.04 pt fuera: la línea llega hasta 1333.4.
    3. Las «E» del linetype partidas por el clip (astas sueltas) no son línea: no
       quedan ganchitos pegados a la vertical."""
    Z = 2.0
    res = rec.recognize_page(DU08, 48, utility="ELECTRICO", zoom=Z)
    pls = [([(q[0] / Z, q[1] / Z) for q in pl.pts_pdf], pl.kinds) for pl in res.drawable]
    ends = [(pts[k], kinds[k]) for pts, kinds in pls for k in (0, -1)]
    for tip in ((661.1, 958.8), (661.1, 988.8), (661.1, 1333.4)):
        assert any(math.dist(p, tip) <= 0.5 and k == "cut" for p, k in ends), tip
    for hook in ((665.9, 1194.4), (665.4, 1257.7), (665.0, 1321.1), (667.2, 1004.3)):
        assert not any(math.dist(p, hook) <= 1.0 for pts, _ in pls for p in pts), hook
