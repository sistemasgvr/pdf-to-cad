"""Quiebres del plano → curvas de radio mínimo (quiebres_curvas.py, sin Qt).

Pedido del usuario (2026-10-06, captura de una línea eléctrica con dos quiebres): según
los ingenieros, un quiebre de una utilidad que NO va a presión está mal dibujado y en
obra es una curva. Cada quiebre pasa a CV con el radio AUTOMÁTICO (6 × el ancho
interior: el mínimo de la regla, la curva más chica posible), solo donde entra tal cual
la dibujan el editor y el plugin y sin cambiar ninguna otra curva. Agua y gas no.
"""
import math

from nucleo import model_ops
from nucleo import quiebres_curvas as qc

FPP = 0.1                     # pies por px: el radio automático de 12" (6 ft) mide 60 px


def _pipe(pts, kinds, layer="ELECTRICO", diam=12):
    return {"layer": layer, "pts": [tuple(map(float, q)) for q in pts], "vertex_kinds": list(kinds),
            "diam": diam, "world": False}


def _importar(pipes):
    """Como `Main._import_recognized_pipes`: buzones de gravedad, ocultos en los quiebres."""
    st = model_ops.rebuild_structures(pipes, [])
    model_ops.hide_soft_vertex_structures(pipes, st)
    model_ops.attach_fillets(pipes, st)
    return st


def _geo_editor(pipes, st, ip, vi):
    """Arco de la CV del vértice `vi` como lo dibuja el editor (`Main._curve_arc_info`)."""
    p = pipes[ip]
    cv = model_ops.curve_vertex_indices(p, st, pipes)
    return qc._geo(p["pts"], vi, qc._radio_px(cv[vi], p, FPP), set(cv), FPP)


def test_quiebre_de_conduit_pasa_a_curva_de_radio_minimo():
    pipes = [_pipe([(0, 0), (1000, 0), (1707.1, 707.1)], ["end", "bend", "end"])]
    st = _importar(pipes)
    assert st == []                                # conduit: ninguna caja en sus vértices
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1 and sin_lugar == []
    s = nuevas[0]
    assert (s["x"], s["y"]) == (1000.0, 0.0)
    assert s["curve"] and s["quiebre"] and s["radius_ft"] == 0.0 and s["net"] == "conduit"
    st = model_ops.rebuild_structures(pipes, st)
    assert [x["cod"] for x in st] == ["CV-1"]
    g = _geo_editor(pipes, st, 0, 1)
    assert not g["clamped"]
    assert math.isclose(g["r"], 60.0) and math.isclose(g["T"], 60.0 * math.tan(math.radians(22.5)))


def test_gravedad_convierte_el_buzon_oculto_del_quiebre():
    pipes = [_pipe([(0, 0), (1000, 0), (1000, 800)], ["vault", "corner", "vault"], layer="DRENAJE")]
    st = _importar(pipes)
    assert [s["hidden"] for s in st] == [False, True, False]
    nuevas, _ = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1 and nuevas[0] is st[1]
    st = model_ops.rebuild_structures(pipes, st)
    cods = {(s["x"], s["y"]): s for s in st}
    cv = cods[(1000.0, 0.0)]
    assert cv["curve"] and not cv["hidden"] and cv["cod"] == "CV-1" and cv.get("quiebre")
    assert cods[(0.0, 0.0)]["cod"].startswith("BZ-") and not cods[(0.0, 0.0)].get("curve")
    assert not _geo_editor(pipes, st, 0, 1)["clamped"]


def test_agua_y_gas_no_cambian():
    for layer in ("AGUA", "GAS"):
        pipes = [_pipe([(0, 0), (1000, 0), (1000, 800)], ["end", "corner", "end"], layer=layer)]
        st = _importar(pipes)
        assert qc.curvas_en_quiebres(pipes, st, FPP) == ([], [])
        assert st == []


def test_solo_quiebres_reales():
    """Casi recto (≤2°: el plugin lo endereza) y vértices que no son quiebre (ramal,
    bóveda, borde de bóveda, codo de la tinta) no cambian; una tubería dibujada a mano
    (sin `vertex_kinds`) tampoco."""
    giro_1 = (2000, 1000 * math.tan(math.radians(1.5)))
    pipes = [_pipe([(0, 0), (1000, 0), giro_1], ["end", "bend", "end"])]
    for k in ("tee", "junction", "vault", "stop", "edge", "fillet", "cut"):
        pipes.append(_pipe([(0, 5000), (1000, 5000), (1000, 6000)], ["end", k, "end"]))
    pipes.append({"layer": "ELECTRICO", "pts": [(5000.0, 0.0), (6000.0, 0.0), (6000.0, 900.0)], "world": False})
    st = _importar(pipes)
    assert qc.curvas_en_quiebres(pipes, st, FPP) == ([], [])


def test_vertice_curve_sin_codo_tambien_es_quiebre():
    """2.º reporte (2026-10-07, DU06 h.5 eléctrico): una línea dibujada como UN trazo de
    rectas que el núcleo marcó «curve» —o una curva que no entró en ningún arco— quedaba
    con esquinas en el editor. Sin codo, ese vértice es un quiebre y pasa a curva mínima;
    los vértices de un codo reconocido («fillet») siguen con su radio."""
    pipes = [_pipe([(0, 0), (1000, 0), (1966, 259), (2832, 759)], ["end", "curve", "curve", "end"])]
    st = _importar(pipes)
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert [(s["x"], s["y"]) for s in nuevas] == [(1000.0, 0.0), (1966.0, 259.0)] and sin_lugar == []
    assert all(s["quiebre"] and s["radius_ft"] == 0.0 for s in nuevas)
    st = model_ops.rebuild_structures(pipes, st)
    for vi in (1, 2):
        assert not _geo_editor(pipes, st, 0, vi)["clamped"]


def test_curva_minima_que_no_entra_queda_como_quiebre():
    """90° con tramos de 20 px: la curva de 6 ft (T = 60 px) no entra. No se achica el
    radio (sería menor que el de la regla): el quiebre queda y se avisa."""
    pipes = [_pipe([(0, 0), (20, 0), (20, 20)], ["end", "corner", "end"])]
    st = _importar(pipes)
    assert qc.curvas_en_quiebres(pipes, st, FPP) == ([], [(20.0, 0.0)])
    assert st == []


def test_la_curva_sigue_al_diametro():
    """Radio automático: con 4" la misma esquina sí entra (r = 2 ft = 20 px)."""
    pipes = [_pipe([(0, 0), (25, 0), (25, 25)], ["end", "corner", "end"], diam=4)]
    st = _importar(pipes)
    nuevas, _ = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1
    assert math.isclose(_geo_editor(pipes, st, 0, 1)["r"], 20.0)


def _con_codo_de_tinta(largo_tramo):
    """Codo leído de la tinta en v1 (90°, r = 8 ft = 80 px → T = 80 px) y un quiebre de
    45° en v2, a `largo_tramo` px del codo."""
    v2 = (300.0, largo_tramo)
    pipes = [_pipe([(0, 0), (300, 0), v2, (v2[0] + 500, v2[1] + 500)], ["end", "fillet", "bend", "end"])]
    pipes[0]["fillets"] = {1: 8.0}
    st = _importar(pipes)
    return pipes, st


def test_no_recorta_el_codo_leido_de_la_tinta():
    """Con una curva al lado, el tope del codo en ese tramo baja a 0.48: con un tramo de
    100 px su tangencia (80 px) ya no entraría → el quiebre queda como estaba."""
    pipes, st = _con_codo_de_tinta(100.0)
    antes = _geo_editor(pipes, st, 0, 1)
    assert not antes["clamped"]
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert nuevas == [] and sin_lugar == [(300.0, 100.0)]
    assert qc._igual(antes, _geo_editor(pipes, st, 0, 1))


def test_curva_junto_al_codo_de_tinta_si_hay_lugar():
    """Tramo de 300 px: entran las dos (80 + 24.9 px + el recto mínimo) y el codo leído
    de la tinta queda idéntico."""
    pipes, st = _con_codo_de_tinta(300.0)
    antes = _geo_editor(pipes, st, 0, 1)
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert len(nuevas) == 1 and sin_lugar == []
    st = model_ops.rebuild_structures(pipes, st)
    assert qc._igual(antes, _geo_editor(pipes, st, 0, 1))
    assert not _geo_editor(pipes, st, 0, 2)["clamped"]


def test_dos_quiebres_seguidos_dejan_el_tramo_recto_minimo():
    """Quiebres de 76° y 74° a 100 px: cada curva entra con el tope de doble curva
    (T = 46.9 y 45.2 px ≤ 0.48 × 100), pero entre las dos no queda el tramo recto mínimo
    del plugin (1 × ancho = 10 px + margen) y el plugin achicaría las dos: queda la que
    más gira; la otra sigue como quiebre."""
    def hacia(p, deg, d):
        return (p[0] + d * math.cos(math.radians(deg)), p[1] + d * math.sin(math.radians(deg)))
    v1 = (1000.0, 0.0)
    v2 = hacia(v1, 76, 100)
    pipes = [_pipe([(0, 0), v1, v2, hacia(v2, 2, 1000)], ["end", "bend", "bend", "end"])]
    st = _importar(pipes)
    nuevas, sin_lugar = qc.curvas_en_quiebres(pipes, st, FPP)
    assert [(s["x"], s["y"]) for s in nuevas] == [v1]
    assert sin_lugar == [v2]
    st = model_ops.rebuild_structures(pipes, st)
    assert not _geo_editor(pipes, st, 0, 1)["clamped"]


def test_vertice_compartido_o_en_una_boveda_no_cambia():
    # otra línea termina en el quiebre (unión): la CV sería de las dos
    pipes = [_pipe([(0, 0), (1000, 0), (1000, 800)], ["end", "bend", "end"]),
             _pipe([(1000, 0), (1000, -900)], ["end", "end"], layer="TELECOM")]
    st = _importar(pipes)
    assert qc.curvas_en_quiebres(pipes, st, FPP) == ([], [])
    # dentro del contorno de una bóveda (llegada a la caja)
    pipes = [_pipe([(0, 0), (1000, 0), (1000, 800)], ["end", "bend", "end"])]
    st = [{"cod": "CAJA-1", "x": 990.0, "y": -30.0, "net": "conduit", "hidden": False, "world": False,
           "outline": [(960.0, -60.0), (1040.0, -60.0), (1040.0, 40.0), (960.0, 40.0)]}]
    assert qc.curvas_en_quiebres(pipes, st, FPP) == ([], [])


def test_dos_veces_no_duplica():
    pipes = [_pipe([(0, 0), (1000, 0), (1707.1, 707.1)], ["end", "bend", "end"])]
    st = _importar(pipes)
    assert len(qc.curvas_en_quiebres(pipes, st, FPP)[0]) == 1
    assert qc.curvas_en_quiebres(pipes, st, FPP) == ([], [])
    assert len(st) == 1
