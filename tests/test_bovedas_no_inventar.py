"""Líneas junto a una bóveda: nada sin tinta y la línea sigue por sus letras.

Reporte del usuario (2026-10-09, DU06, banco de ductos «—SC—» de telecomunicaciones):
  · h.10 (744, 1107): la diagonal baja, pasa las letras «SC» y sigue en curva hasta la
    caja. El núcleo la estiraba RECTA 46 pt sin tinta hasta el borde de la caja
    (`_vault_entry` hacia adelante) en vez de seguir por sus letras → regla en TODAS las
    utilidades: una continuación con letra en el hueco, antes que la bóveda, gana.
  · h.12 (775, 1084): el trazo cruza la caja y empieza a curvarse bajo «SC». El núcleo
    recortaba su punta hacia atrás hasta el borde (sobrepaso «corto» de 28 pt): vuelta
    en U sin tinta y el arco perdido → una CURVA que atravesó la bóveda no se recorta
    sobre más de `RETRACT_INK_MAX_PT` de su tinta; la línea sigue por «SC» con su codo y
    la caja va en la línea (`recognition_vault_through`).
"""
import math
from pathlib import Path

import pytest

from reconocimiento import recognition as rec
from reconocimiento import recognition_vault_through as vt

ROOT = Path(__file__).resolve().parent.parent
DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF de prueba DU06 no está en el repo")


def _near(p, q, tol):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


def _through(res, pt, tol=1.0):
    """Polilíneas con un vértice a ≤ tol de pt."""
    return [pl for pl in res.polylines if any(_near(p, pt, tol) for p in pl.pts_pdf)]


@pytest.fixture(scope="module")
def h10():
    if not DU06.is_file():
        pytest.skip("sin PDF")
    return rec.recognize_page(DU06, 9, utility="TELECOM", zoom=1.0)


@pytest.fixture(scope="module")
def h12():
    if not DU06.is_file():
        pytest.skip("sin PDF")
    return rec.recognize_page(DU06, 11, utility="TELECOM", zoom=1.0)


@needs_pdf
def test_du06_h10_la_diagonal_sigue_por_sus_letras(h10):
    # nada llega a (789.6, 1130.4): la recta inventada hasta el borde de la caja
    assert not any(_near(p, (789.6, 1130.4), 3.0) for pl in h10.polylines for p in pl.pts_pdf)
    # una sola línea: viene de la izquierda, pasa «SC» y entra a la caja (nodo en su centro)
    caja = _through(h10, (808.5, 1119.3))
    assert len(caja) == 1
    pl = caja[0]
    k = next(i for i, p in enumerate(pl.pts_pdf) if _near(p, (808.5, 1119.3), 1.0))
    assert pl.kinds[k] == "vault"
    assert any(_near(p, (478.4, 1078.7), 1.0) for p in pl.pts_pdf)
    # el codo antes de la caja (la curva que sigue después de «SC»)
    assert any(_near(pl.pts_pdf[i], (767.8, 1119.2), 1.0) for i in pl.fillets)


@needs_pdf
def test_du06_h12_la_linea_cruza_la_caja_y_sigue_con_su_codo(h12):
    # sin la vuelta en U hasta el borde de la caja
    assert not any(_near(p, (756.6, 1086.3), 1.5) for pl in h12.polylines for p in pl.pts_pdf)
    caja = _through(h12, (742.1, 1084.3))
    assert len(caja) == 1
    pl = caja[0]
    k = next(i for i, p in enumerate(pl.pts_pdf) if _near(p, (742.1, 1084.3), 1.0))
    assert pl.kinds[k] == "vault"                  # la caja va en la línea
    # el codo bajo «SC»: esquina donde se cortan la horizontal y la diagonal, r ≈ 45 pt
    codo = [pl.fillets[i] for i in pl.fillets if _near(pl.pts_pdf[i], (784.0, 1084.4), 1.5)]
    assert codo and 40.0 <= codo[0]["r_px"] <= 52.0
    # la diagonal de después de «SC» es la MISMA línea
    assert any(_near(p, (882.7, 1041.8), 1.0) for p in pl.pts_pdf)
    vg = [v for v in h12.vaults_geo if _near(v["center"], (742.1, 1084.35), 1.0)]
    assert vg and vg[0]["orphan"] is False


# ── recognition_vault_through (puro) ─────────────────────────────────────────
def _pl(pts, kinds, fillets=None):
    return rec.RecognizedPolyline("CAPA", "TELECOM", [tuple(p) for p in pts], "tele_ungd",
                                  kinds=list(kinds), fillets=dict(fillets or {}))


def _caja(x0, y0, x1, y1):
    return {"center": ((x0 + x1) / 2, (y0 + y1) / 2), "corners": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}


def test_recta_que_atraviesa_la_caja_lleva_su_vertice():
    pl = _pl([(0, 50), (100, 50), (200, 80)], ["end", "fillet", "end"],
             {1: {"a": (90, 50), "b": (109, 53), "center": (90, 80), "r_px": 30}})
    hits = vt.mark_through_vaults([pl], [_caja(30, 40, 50, 62)], zoom=1.0)
    assert hits and hits[0]["vault"] == 0
    assert pl.pts_pdf[1] == (40.0, 50.0) and pl.kinds[1] == "vault"
    assert set(pl.fillets) == {2}                  # el codo corre al índice siguiente
    assert pl.pts_pdf[2] == (100, 50)


def test_no_toca_lo_que_ya_llega_ni_lo_que_pasa_de_costado():
    caja = _caja(30, 40, 50, 60)
    llega = _pl([(0, 50), (30, 50)], ["end", "stop"])
    pasa = _pl([(0, 50), (100, 50)], ["end", "end"])
    assert vt.mark_through_vaults([llega, pasa], [caja], zoom=1.0) == []      # ya tiene su línea
    muere = _pl([(0, 50), (40, 50)], ["end", "end"])
    assert vt.mark_through_vaults([muere], [caja], zoom=1.0) == []            # muere dentro
    costado = _pl([(0, 25), (100, 125)], ["end", "end"])          # corta solo la esquina
    assert vt.mark_through_vaults([costado], [_caja(30, 40, 50, 60)], zoom=1.0) == []
    assert costado.kinds == ["end", "end"]


def test_no_pone_la_caja_dentro_del_arco_de_un_codo():
    # la caja cae sobre el arco del codo (entre sus tangencias): ahí no hay recta dibujada
    pl = _pl([(0, 50), (40, 50), (40, 100)], ["end", "fillet", "end"],
             {1: {"a": (20, 50), "b": (40, 70), "center": (20, 70), "r_px": 20}})
    assert vt.mark_through_vaults([pl], [_caja(30, 45, 40, 55)], zoom=1.0) == []


def test_reusa_un_vertice_suelto_en_el_pie():
    pl = _pl([(0, 50), (40.2, 50), (100, 50)], ["end", "bend", "end"])
    vt.mark_through_vaults([pl], [_caja(30, 40, 50, 60)], zoom=1.0)
    assert len(pl.pts_pdf) == 3 and pl.kinds[1] == "vault"


# ── casos de la revisión de los 4 PDFs (docs prueba) ─────────────────────────
DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"
LABOE = DOCS / "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf"


@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_h3_la_linea_sale_de_la_caja_y_sigue_por_sus_letras():
    """El trazo centro→borde de la caja no se da vuelta: la «—SC—» sale de la caja,
    pasa sus letras y sigue en diagonal; sin el zigzag hasta la esquina de la caja."""
    res = rec.recognize_page(DU10, 2, utility="TELECOM", zoom=1.0)
    assert not any(_near(p, (916.8, 807.3), 1.5) for pl in res.polylines for p in pl.pts_pdf)
    pl = _through(res, (897.1, 798.5))
    assert len(pl) == 1
    pts, kinds = pl[0].pts_pdf, pl[0].kinds
    k = next(i for i, p in enumerate(pts) if _near(p, (897.1, 798.5), 1.0))
    assert kinds[k] == "vault" and kinds[k + 1] == "edge"
    assert any(_near(p, (963.5, 780.1), 1.5) for p in pts)        # la diagonal es la misma línea


@pytest.mark.skipif(not LABOE.is_file(), reason="PDF LABOE no disponible")
def test_laboe_h26_el_ramal_llega_a_su_T_dentro_de_la_caja():
    """Trazo del ramal TODO dentro de la caja: no sale al revés como un tramo fuera de
    ella; su tinta marca el nodo en la «T» con la línea que atraviesa."""
    res = rec.recognize_page(LABOE, 25, utility="DRENAJE", zoom=1.0)
    assert not any(_near(p, (395.9, 1241.7), 1.5) for pl in res.polylines for p in pl.pts_pdf)
    nodos = [p for pl in res.polylines for p, k in zip(pl.pts_pdf, pl.kinds) if k == "vault"
             and 390 <= p[0] <= 440 and 1195 <= p[1] <= 1250]
    assert nodos and all(_near(p, (404.2, 1233.4), 1.0) for p in nodos)


@pytest.mark.skipif(not LABOE.is_file(), reason="PDF LABOE no disponible")
def test_laboe_h26_nada_suelto_dentro_del_buzon():
    res = rec.recognize_page(LABOE, 25, utility="ALCANTARILLADO", zoom=1.0)
    dentro = lambda p: math.hypot(p[0] - 500.1, p[1] - 1145.6) <= 12.0  # noqa: E731
    assert not any(dentro(pl.pts_pdf[0]) and dentro(pl.pts_pdf[-1]) for pl in res.polylines if pl.pts_pdf)


DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h21_la_diagonal_sigue_por_sc_hasta_la_caja():
    """La continuación por letras gana también si su punta ya está en la caja: la
    diagonal no se prolonga hasta la esquina de la caja (zigzag sin tinta)."""
    res = rec.recognize_page(DU08, 20, utility="TELECOM", zoom=1.0)
    assert not any(_near(p, (872.3, 788.9), 1.5) for pl in res.polylines for p in pl.pts_pdf)
    pl = _through(res, (851.4, 779.7))
    assert len(pl) == 1 and any(_near(p, (887.3, 781.0), 1.5) for p in pl[0].pts_pdf)
