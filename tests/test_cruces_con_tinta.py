"""Líneas que CRUZAN otra línea no pierden la tinta del otro lado.

Reporte del usuario (2026-09-30, DU10 h.11 alcantarillado `C-SSWR-UNGD-E`):
(1) una «X» —dos rectas que se cruzan de punta a punta sobre la principal; el PDF la
dibuja como dos «V» que se tocan— salía como un «<»: el núcleo retrocedía las dos
puntas de la derecha hasta el cruce (37 pt de tinta) para formar una esquina;
(2) los laterales «ss» que cruzan la principal perdían su mitad de arriba: la punta
retrocedía 35.7 pt hasta la principal para formar la T.
Ahora un extremo no retrocede sobre más de `RETRACT_INK_MAX_PT` de guiones propios:
la «X» queda como dos rectas enteras y el lateral hace su T en la principal y sigue
del otro lado. Una T cuyo guión solo se pasa unos pt de la línea no cambia.
"""
import math
from pathlib import Path

import pytest

import recognition_geom as G
from test_recognition_geom import Sheet


def _covers(polys, a, b, tol=1.0):
    """La unión de las polilíneas cubre el segmento a→b (muestreo cada 2 pt)."""
    L = math.dist(a, b)
    for k in range(int(L // 2) + 1):
        t = min(1.0, 2.0 * k / L)
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if not any(_seg_dist(q, p0, p1) <= tol for pl in polys for p0, p1 in zip(pl.pts, pl.pts[1:])):
            return False
    return True


def _seg_dist(q, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.dist(q, (a[0] + t * vx, a[1] + t * vy))


def test_x_de_dos_v_son_dos_rectas_que_se_cruzan():
    # (medidas < `corner_tol` = 25 pt de este patrón, como los 37 pt < 42.5 del DU10)
    sh = Sheet()
    sh.dashed((100, 400), (900, 400))
    sh.polyline("LINES", [(485, 385), (500, 400), (513.5, 386.5)])  # «V» de arriba
    sh.polyline("LINES", [(485, 415), (500, 400), (513.5, 413.5)])  # «Λ» de abajo
    res = sh.run()
    assert _covers(res.polylines, (485, 385), (513.5, 413.5))
    assert _covers(res.polylines, (485, 415), (513.5, 386.5))
    # ninguna «V»/«<»: ninguna polilínea gira en el cruce uniendo dos brazos del mismo lado
    for pl in res.polylines:
        for i in range(1, len(pl.pts) - 1):
            u = (pl.pts[i - 1][0] - pl.pts[i][0], pl.pts[i - 1][1] - pl.pts[i][1])
            v = (pl.pts[i + 1][0] - pl.pts[i][0], pl.pts[i + 1][1] - pl.pts[i][1])
            cos = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
            assert cos < -0.9 or math.hypot(*u) < 1 or math.hypot(*v) < 1, pl.pts


def test_lateral_que_cruza_la_principal_sigue_del_otro_lado():
    sh = Sheet()
    sh.dashed((100, 400), (900, 400))
    sh.line("LINES", (300, 378), (300, 397))                        # guión arriba de la principal
    sh.line("LINES", (300, 403), (300, 424))                        # …y abajo (misma recta)
    res = sh.run()
    assert _covers(res.polylines, (300, 378), (300, 424))
    # …y sigue conectado a la principal: un nodo sobre ella en (300, 400)
    assert any(_seg_dist((300, 400), p, p) <= 1.5 for pl in res.polylines
               for p, k in zip(pl.pts, pl.kinds) if k in ("tee", "junction"))


def test_t_con_el_guion_apenas_pasado_sigue_siendo_t():
    sh = Sheet()
    sh.dashed((100, 400), (900, 400))
    sh.line("LINES", (300, 300), (300, 402.5))                      # se pasa 2.5 pt
    res = sh.run()
    stem = [pl for pl in res.polylines if all(abs(p[0] - 300) < 1 for p in pl.pts)]
    assert len(stem) == 1 and max(p[1] for p in stem[0].pts) == pytest.approx(400, abs=0.6)
    assert "tee" in (stem[0].kinds[0], stem[0].kinds[-1])


DU10 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf")


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h11_alcantarillado_x_y_laterales_completos():
    import recognition as rec
    r = rec.recognize_page(DU10, 10, utility="ALCANTARILLADO", zoom=1.0)
    pls = [G.Polyline(p.pts_pdf, p.kinds) for p in r.drawable]
    assert _covers(pls, (675.7, 682.8), (727.7, 735.6))             # las dos diagonales de la «X»
    assert _covers(pls, (675.4, 736.5), (728.0, 684.2))
    assert _covers(pls, (555.1, 673.3), (554.8, 745.3))             # laterales «ss» enteros
    assert _covers(pls, (925.9, 675.4), (925.6, 747.4))
