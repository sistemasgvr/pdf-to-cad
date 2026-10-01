"""Imán de puntas a bóvedas (`recognition_vault_snap`, pedido del usuario 2026-10-01).

«En cada buzón las líneas quedan separadas… que cuando esté muy cerca se haga snap y
se una solito», sin alterar el reconocimiento y solo con la línea bien cerca.
1. Casos sintéticos (px = pt × zoom): la punta se desliza por SU recta hasta el
   contorno (rectángulo, girado o círculo); lejos, de costado, dentro, compartida con
   otra línea o comiéndose un codo, no se mueve.
2. El import: la estructura de la bóveda queda EN la punta unida (no suelta al centro),
   también en un buzón redondo de gravedad.
3. La captura del usuario (DU06 h.5, sólido eléctrico de 6.33 × 8.33 ft).
"""
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import recognition_vault_snap as vs
import model_ops

RECT = {"corners": [(100.0, 100.0), (160.0, 100.0), (160.0, 140.0), (100.0, 140.0)],
        "center": (130.0, 120.0)}


def _pl(pts, kinds, fillets=None):
    return SimpleNamespace(pts_pdf=[tuple(p) for p in pts], kinds=list(kinds), fillets=fillets or {})


# ─────────────────────────── geometría pura ───────────────────────────
def test_punta_stop_a_1pt_fuera_llega_al_borde():
    """El caso de la captura: el núcleo corta la llegada 1 pt antes del contorno."""
    pl = _pl([(40.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    out = vs.snap_ends_to_vaults([pl], [RECT], zoom=1.0)
    assert len(out) == 1 and out[0]["vault"] == 0
    assert pl.pts_pdf[-1] == pytest.approx((100.0, 120.0))
    assert pl.kinds[-1] == "stop" and pl.pts_pdf[0] == (40.0, 120.0)


def test_umbral_en_pt_escala_con_el_zoom():
    """3 pt a zoom 3.5 = 10.5 px: 2.9 pt se une; 3.2 pt no."""
    z = 3.5
    rect = {"corners": [(x * z, y * z) for x, y in RECT["corners"]]}
    cerca = _pl([(40 * z, 120 * z), ((100 - 2.9) * z, 120 * z)], ["end", "stop"])
    lejos = _pl([(40 * z, 130 * z), ((100 - 3.2) * z, 130 * z)], ["end", "stop"])
    vs.snap_ends_to_vaults([cerca, lejos], [rect], zoom=z)
    assert cerca.pts_pdf[-1] == pytest.approx((100 * z, 120 * z))
    assert lejos.pts_pdf[-1] == pytest.approx(((100 - 3.2) * z, 130 * z))


def test_punta_libre_solo_bien_cerca_y_hacia_adelante():
    a = _pl([(40.0, 110.0), (98.8, 110.0)], ["end", "end"])          # 1.2 pt → se une
    b = _pl([(40.0, 125.0), (97.5, 125.0)], ["end", "end"])          # 2.5 pt → no
    c = _pl([(220.0, 130.0), (161.0, 130.0)], ["end", "end"])        # del otro lado, 1 pt → se une
    vs.snap_ends_to_vaults([a, b, c], [RECT], zoom=1.0)
    assert a.pts_pdf[-1] == pytest.approx((100.0, 110.0)) and a.kinds[-1] == "stop"
    assert b.pts_pdf[-1] == (97.5, 125.0) and b.kinds[-1] == "end"
    assert c.pts_pdf[-1] == pytest.approx((160.0, 130.0))


def test_stop_que_paso_por_encima_se_recorta_al_borde_y_end_no():
    """La línea cruzó la bóveda y el núcleo la cortó 1 pt DESPUÉS del borde de salida:
    la «stop» vuelve al borde; una punta libre así no (no se borra tinta)."""
    stop = _pl([(40.0, 110.0), (161.0, 110.0)], ["end", "stop"])
    libre = _pl([(40.0, 130.0), (161.0, 130.0)], ["end", "end"])
    vs.snap_ends_to_vaults([stop, libre], [RECT], zoom=1.0)
    assert stop.pts_pdf[-1] == pytest.approx((160.0, 110.0))
    assert libre.pts_pdf[-1] == (161.0, 130.0)


def test_de_costado_dentro_o_en_otro_nodo_no_se_mueve():
    costado = _pl([(40.0, 99.0), (99.5, 99.0)], ["end", "stop"])     # corre 1 pt por fuera del lado
    dentro = _pl([(40.0, 120.0), (110.0, 120.0)], ["end", "stop"])   # ya está unida
    tee = _pl([(130.0, 40.0), (130.0, 99.0)], ["end", "tee"])
    cut = _pl([(150.0, 40.0), (150.0, 99.0)], ["end", "cut"])
    vs.snap_ends_to_vaults([costado, dentro, tee, cut], [RECT], zoom=1.0)
    assert costado.pts_pdf[-1] == (99.5, 99.0)
    assert dentro.pts_pdf[-1] == (110.0, 120.0)
    assert tee.pts_pdf[-1] == (130.0, 99.0) and cut.pts_pdf[-1] == (150.0, 99.0)


def test_punta_compartida_con_otra_linea_no_se_mueve():
    """Dos líneas que se tocan en la punta están unidas entre sí: moverlas las separa."""
    a = _pl([(40.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    b = _pl([(99.0, 60.0), (99.0, 120.0)], ["end", "stop"])
    vs.snap_ends_to_vaults([a, b], [RECT], zoom=1.0)
    assert a.pts_pdf[-1] == (99.0, 120.0) and b.pts_pdf[-1] == (99.0, 120.0)


def test_puntas_que_coinciden_y_van_al_mismo_punto_se_mueven_juntas():
    """La misma llegada en dos capas (DU06 h.14): las dos puntas van al MISMO punto."""
    a = _pl([(40.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    b = _pl([(60.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    c = _pl([(99.0, 120.0), (40.0, 121.0)], ["stop", "end"])      # casi igual, otra punta
    out = vs.snap_ends_to_vaults([a, b, c], [RECT], zoom=1.0)
    assert len(out) == 3
    assert a.pts_pdf[-1] == b.pts_pdf[-1] == c.pts_pdf[0]
    assert a.pts_pdf[-1] == pytest.approx((100.0, 120.0), abs=0.05)


def test_puntas_que_coinciden_pero_irian_a_puntos_distintos_no_se_mueven():
    a = _pl([(40.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    b = _pl([(40.0, 140.0), (99.0, 120.0)], ["end", "stop"])      # llega en diagonal
    vs.snap_ends_to_vaults([a, b], [RECT], zoom=1.0)
    assert a.pts_pdf[-1] == b.pts_pdf[-1] == (99.0, 120.0)


def test_contornos_anidados_gana_el_cruce_mas_cercano():
    """Contorno dentro de otro (caja + tapa): la punta va al primero que corta su recta."""
    otra = {"corners": [(101.5, 105.0), (150.0, 105.0), (150.0, 135.0), (101.5, 135.0)]}
    pl = _pl([(40.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    out = vs.snap_ends_to_vaults([pl], [otra, RECT], zoom=1.0)
    assert out[0]["vault"] == 1 and pl.pts_pdf[-1] == pytest.approx((100.0, 120.0))


def test_boveda_girada_y_buzon_redondo():
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    girada = {"corners": [(200 + c * x - s * y, 200 + s * x + c * y)
                          for x, y in ((-20, -10), (20, -10), (20, 10), (-20, 10))]}
    # llega por el eje largo del rectángulo girado, 1 pt antes del lado corto
    q = (200 - c * 21, 200 - s * 21)
    pl = _pl([(200 - c * 80, 200 - s * 80), q], ["end", "stop"])
    buzon = {"circle": (400.0, 400.0, 9.0), "center": (400.0, 400.0)}
    pr = _pl([(300.0, 400.0), (390.0, 400.0)], ["end", "stop"])       # anillo + 1 pt
    vs.snap_ends_to_vaults([pl, pr], [girada, buzon], zoom=1.0)
    assert pl.pts_pdf[-1] == pytest.approx((200 - c * 20, 200 - s * 20))
    assert pr.pts_pdf[-1] == pytest.approx((391.0, 400.0))


def test_no_se_come_el_arco_de_un_codo_vecino():
    """Recortar la punta hacia atrás no puede dejarla dentro del arco del codo (el editor
    recortaría el radio); prolongarla sí se puede."""
    # codo en C=(158, 60): baja hasta la punta (158, 141) — la tangencia queda en y=140.5
    fil = {1: {"a": (120.0, 60.0), "b": (158.0, 140.5), "center": (120.0, 98.0), "r_px": 38.0}}
    pl = _pl([(60.0, 60.0), (158.0, 60.0), (158.0, 141.0)], ["end", "fillet", "stop"], fil)
    vs.snap_ends_to_vaults([pl], [RECT], zoom=1.0)
    assert pl.pts_pdf[-1] == (158.0, 141.0)                           # se quedó: cruce a 1 pt atrás


def test_vault_contains_con_margen():
    assert vs.vault_contains(RECT, (99.0, 120.0), pad=1.5)
    assert not vs.vault_contains(RECT, (97.0, 120.0), pad=1.5)
    assert vs.vault_contains({"circle": (0.0, 0.0, 9.0)}, (9.5, 0.0), pad=1.0)
    assert not vs.vault_contains({"center": (0.0, 0.0)}, (0.0, 0.0))     # sin geometría


# ─────────────────────────── import: estructura unida ───────────────────────────
def _pipe(pts, kinds, layer):
    return {"layer": layer, "pts": list(pts), "vertex_kinds": list(kinds)}


def test_import_conduit_caja_en_la_punta_unida():
    """Eléctrico: la caja (SÓLIDO) de la bóveda va en el vértice por donde llega la línea,
    no suelta en el centro del símbolo."""
    pl = _pl([(40.0, 120.0), (99.0, 120.0)], ["end", "stop"])
    vg = dict(RECT, center=(140.0, 110.0), shape="rect", width_ft=6.0, length_ft=8.0, importable=True)
    vs.snap_ends_to_vaults([pl], [vg], zoom=1.0)
    pipes = [_pipe(pl.pts_pdf, pl.kinds, "ELECTRICO")]
    structures = model_ops.rebuild_structures(pipes, [])
    model_ops.attach_vault_geometry(structures, [vg], net="conduit", utility="ELECTRICO", pipes=pipes)
    (st,) = structures
    assert (st["x"], st["y"]) == pytest.approx((100.0, 120.0)) and not st.get("standalone")
    assert st.get("solid")


def test_import_gravedad_buzon_redondo_una_sola_estructura():
    """Alcantarillado: la BZ de la punta que llega al anillo se lleva el buzón (círculo,
    diámetro); antes quedaban dos estructuras: la de la punta y otra suelta al centro."""
    vg = {"center": (400.0, 400.0), "circle": (400.0, 400.0, 30.0), "corners": None,
          "shape": "circle", "width_ft": 5.0, "length_ft": 5.0, "importable": True}
    pipes = [_pipe([(200.0, 400.0), (370.0, 400.0)], ["end", "stop"], "ALCANTARILLADO")]
    structures = model_ops.rebuild_structures(pipes, [])
    assert len(structures) == 2                                       # BZ en cada vértice
    _geo, sueltas = model_ops.attach_vault_geometry(structures, [vg], net="gravity",
                                                    utility="ALCANTARILLADO", pipes=pipes)
    assert sueltas == 0 and len(structures) == 2
    bz = [s for s in structures if s.get("shape") == "circle"]
    assert len(bz) == 1 and (bz[0]["x"], bz[0]["y"]) == (370.0, 400.0)


# ─────────────────────────── la hoja de la captura ───────────────────────────
DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_h5_solido_electrico_de_la_captura():
    import recognition as rec
    z = 3.5                                                            # zoom del editor
    res = rec.recognize_page(str(DU06), 4, utility="ELECTRICO", zoom=z)
    vg = next(v for v in res.vaults_geo
              if abs(v["width_ft"] - 6.333) < 0.01 and abs(v["length_ft"] - 8.333) < 0.01)
    xs = sorted({round(x, 3) for x, _ in vg["corners"]})
    llegan = [pl.pts_pdf[e] for pl in res.drawable for e in (0, -1)
              if pl.kinds[e] == "stop" and vs.vault_contains(vg, pl.pts_pdf[e], pad=0.01 * z)]
    assert len(llegan) == 2                                           # izquierda y derecha
    assert sorted(round(q[0], 3) for q in llegan) == pytest.approx([xs[0], xs[-1]], abs=1e-3)
    assert any("Puntas unidas a su bóveda" in w for w in res.warnings)
    pipes = rec.pipes_from_recognition(res, layer="ELECTRICO", zoom=z)
    structures = model_ops.rebuild_structures(pipes, [])
    model_ops.attach_vault_geometry(structures, res.vaults_geo, net="conduit", utility="ELECTRICO",
                                    pipes=pipes)
    st = next(s for s in structures if s.get("outline") == [tuple(map(float, c)) for c in vg["corners"]])
    assert not st.get("standalone")
    assert any(math.hypot(st["x"] - q[0], st["y"] - q[1]) < 1e-6 for q in llegan)
