"""Red en IMAGEN → rectas de buzón a buzón (`recognition_imagen_rectas`, sin Qt).

Pedido del usuario (2026-11-19, Phoenix «QS SD_Indian School»): de la red que viene como imagen solo el eje, «todo
recto»: sin el serrucho de la banda pixelada, sin curvas en quiebres mínimos, las puntas en el centro del buzón y sin
los trocitos que deja la rejilla de un sumidero. Las capas vectoriales no cambian.
"""
import math

from nucleo import model_ops
from nucleo import quiebres_curvas as qc
from reconocimiento import recognition_imagen_rectas as R
from reconocimiento.recognition import RecognizedPolyline

IMG = 'PDF_STYLE:["img","line",[0,77,168]]'
VEC = 'PDF_STYLE:["Negro",0.7]'


def _pl(pts, kinds, capa=IMG):
    return RecognizedPolyline(capa, "DRENAJE", [tuple(map(float, q)) for q in pts], "drain_ungd", kinds=list(kinds))


def _caja(cx, cy, m=4.0):
    return {"center": (cx, cy), "corners": [(cx - m, cy - m), (cx + m, cy - m), (cx + m, cy + m), (cx - m, cy + m)],
            "circle": None, "shape": "rect"}


def test_serrucho_entre_dos_buzones_queda_recto_de_centro_a_centro():
    pl = _pl([(3, 0.4), (20, -0.8), (40, 0.9), (60, -0.7), (80, 0.6), (97, -0.3)],
             ["stop", "bend", "corner", "bend", "corner", "stop"])
    lineas = [pl]
    R.enderezar(lineas, [_caja(0, 0), _caja(100, 0)], zoom=1.0)
    assert lineas[0].pts_pdf == [(0.0, 0.0), (100.0, 0.0)]
    assert lineas[0].kinds == ["vault", "vault"]


def test_quiebre_de_verdad_se_queda_y_el_codo_del_plano_se_conserva():
    # 2026-11-19 (SD South «24" RCP R=244.72»): el codo que reconoce el núcleo es el ARCO del plano (regla de las
    # otras utilidades); borrarlo dejaba suelta la esquina de las tangentes, lejos de la tinta
    codo = {"a": (90, 0), "b": (108, 6), "center": (95, 30), "r_px": 30}
    pl = _pl([(0, 0), (50, 0.5), (100, 0), (150, 40)], ["end", "bend", "curve", "end"])
    pl.fillets = {2: dict(codo)}
    R.enderezar([pl], [], zoom=1.0)
    assert pl.pts_pdf == [(0.0, 0.0), (100.0, 0.0), (150.0, 40.0)]
    assert pl.kinds == ["end", "curve", "end"] and pl.fillets == {1: codo}


def test_codo_al_unir_y_dar_vuelta_conserva_su_lado():
    codo = {"a": (90, 0), "b": (108, 6), "center": (95, 30), "r_px": 30}
    a = _pl([(150, 40), (100, 0), (60, 0)], ["end", "curve", "junction"])
    a.fillets = {1: {"a": codo["b"], "b": codo["a"], "center": codo["center"], "r_px": 30}}
    b = _pl([(0, 0), (60, 0)], ["end", "junction"])
    lineas = [a, b]
    R.enderezar(lineas, [], zoom=1.0)
    assert len(lineas) == 1
    pl = lineas[0]
    i = next(iter(pl.fillets))
    assert pl.pts_pdf[i] == (100.0, 0.0)
    f = pl.fillets[i]
    antes, despues = pl.pts_pdf[i - 1], pl.pts_pdf[i + 1]
    # «a» es la tangencia del lado del vértice anterior; «b», la del siguiente
    import math
    assert math.dist(f["a"], antes) < math.dist(f["b"], antes) and math.dist(f["b"], despues) < math.dist(f["a"], despues)


def test_linea_cortada_por_un_texto_encima_se_une():
    # SD South «N 62ND DR»: el rótulo tapa la línea y deja un hueco de 24 pt; las dos piezas siguen la misma recta
    a = _pl([(0, 0), (0, 100)], ["vault", "end"])
    b = _pl([(0.4, 124), (0.6, 220)], ["end", "vault"])
    lineas = [a, b]
    R.enderezar(lineas, [], zoom=1.0)
    assert len(lineas) == 1 and lineas[0].pts_pdf == [(0.0, 0.0), (0.6, 220.0)]


def test_dos_lineas_paralelas_o_de_costado_no_se_unen():
    a = _pl([(0, 0), (0, 100)], ["vault", "end"])
    de_costado = _pl([(5, 110), (5, 200)], ["end", "vault"])       # 5 pt al lado: otra tubería
    girada = _pl([(0, 110), (40, 150)], ["end", "vault"])          # sigue en otro rumbo
    lineas = [a, de_costado, girada]
    R.enderezar(lineas, [], zoom=1.0)
    assert len(lineas) == 3


def test_trocito_de_rejilla_se_va_y_piezas_de_frente_se_unen():
    a = _pl([(0, 0), (50, 0.5)], ["vault", "junction"])
    b = _pl([(50, 0.5), (100, 0)], ["junction", "vault"])
    trocito = _pl([(50, 0.5), (53, 4)], ["junction", "end"])          # 4.6 pt con una punta suelta
    lineas = [a, b, trocito]
    R.enderezar(lineas, [_caja(0, 0), _caja(100, 0)], zoom=1.0)
    assert len(lineas) == 1
    assert lineas[0].pts_pdf == [(0.0, 0.0), (100.0, 0.0)]


def test_la_misma_tuberia_dos_veces_queda_una():
    larga = _pl([(0, 0), (100, 0)], ["end", "end"])
    copia = _pl([(10, 1.5), (80, 1.2)], ["end", "end"])
    lineas = [larga, copia]
    R.enderezar(lineas, [], zoom=1.0)
    assert lineas == [larga]


def test_ramal_en_t_vuelve_a_quedar_sobre_la_principal_enderezada():
    principal = _pl([(0, 0), (50, 1.0), (100, 0)], ["end", "bend", "end"])
    ramal = _pl([(50, 1.0), (50, 60)], ["tee", "end"])
    lineas = [principal, ramal]
    R.enderezar(lineas, [], zoom=1.0)
    assert principal.pts_pdf == [(0.0, 0.0), (100.0, 0.0)]
    assert math.isclose(ramal.pts_pdf[0][1], 0.0, abs_tol=1e-9)


def test_capas_vectoriales_no_cambian():
    pl = _pl([(0, 0), (20, 0.8), (40, 0)], ["end", "bend", "end"], capa=VEC)
    antes = list(pl.pts_pdf)
    R.enderezar([pl], [_caja(0, 0)], zoom=1.0)
    assert pl.pts_pdf == antes and pl.kinds == ["end", "bend", "end"]


def test_importar_sin_curvas_en_los_quiebres_de_la_red_en_imagen():
    def pipes(solo):
        p = {"layer": "DRENAJE", "pts": [(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0)],
             "vertex_kinds": ["vault", "corner", "vault"], "diam": 12, "world": False}
        if solo:
            p["solo_rectas"] = True
        return [p]
    for solo, esperadas in ((False, 1), (True, 0)):
        ps = pipes(solo)
        st = model_ops.rebuild_structures(ps, [])
        model_ops.hide_soft_vertex_structures(ps, st)
        nuevas, _ = qc.curvas_en_quiebres(ps, st, 0.1)
        assert len(nuevas) == esperadas


def test_miles_de_lineas_no_comparan_todo_con_todo():
    # reporte 2026-11-19: una compuesta de 36 mapas pasó ~2 horas aquí (cada línea contra todas). Con índices por
    # celdas, 4 000 líneas en una rejilla (con serrucho, uniones de frente y buzones) tardan segundos
    import time
    lineas, cajas = [], []
    for fila in range(40):
        y = fila * 50.0
        for col in range(50):
            x = col * 40.0
            lineas.append(_pl([(x, y), (x + 20, y + 0.6), (x + 40, y)], ["junction", "bend", "junction"]))
        lineas.append(_pl([(0, y), (0, y + 30)], ["junction", "end"]))
        cajas.append(_caja(2000.0, y))
    t = time.time()
    R.enderezar(lineas, cajas, zoom=1.0)
    assert time.time() - t < 20
    # cada fila = UNA línea: la vertical y las 50 piezas unidas de frente, recta, con su quiebre real de 90°
    assert len(lineas) == 40
    assert all([(round(x, 6), round(y, 6)) for x, y in pl.pts_pdf] ==
               [(0.0, pl.pts_pdf[1][1] + 30.0), (0.0, pl.pts_pdf[1][1]), (2000.0, pl.pts_pdf[1][1])] for pl in lineas)


def test_misma_tuberia_con_diametro_de_un_solo_lado_se_une_y_lo_toma():
    a = _pl([(0, 0), (0, 100)], ["vault", "cut"])
    b = _pl([(0.05, 100.05), (0, 200)], ["cut", "vault"])
    b.diam_in = 24.0
    lineas = [a, b]
    R.enderezar(lineas, [], zoom=1.0)
    assert len(lineas) == 1 and lineas[0].diam_in == 24.0
    c = _pl([(0, 300), (0, 400)], ["vault", "cut"]); c.diam_in = 18.0
    d = _pl([(0, 400), (0, 500)], ["cut", "vault"]); d.diam_in = 24.0
    otras = [c, d]
    R.enderezar(otras, [], zoom=1.0)
    assert len(otras) == 2                              # dos diámetros distintos: dos tuberías
