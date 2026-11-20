"""Continuidad de la red leída de una IMAGEN (reporte del usuario 2026-11-20, QS SD North de Phoenix, cinco capturas:
«si te digo que tiene que ser continua, tiene que ser continua… no podemos tener dobles innecesarios, quiebres
innecesarios»). `recognition_imagen_nudos` (lo llama `recognition_imagen_rectas.enderezar`): horquillas y enredos
de trozos cortos, puntas que no llegan a su buzón, el marco de la caja de un símbolo, la línea que pasa por el
sumidero hasta el buzón de enfrente, la llegada en T por su recta y las líneas repetidas del mismo largo."""
import os
import sys

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]

from reconocimiento import recognition_imagen_rectas as RR  # noqa: E402
from reconocimiento.recognition import RecognizedPolyline  # noqa: E402

CAPA = 'PDF_STYLE:["img","line",[0,77,168]]'
SYM = 'PDF_STYLE:["img","sym",[0,77,168]]'


def _pl(pts, kinds=None):
    return RecognizedPolyline(layer_ocg=CAPA, utility_hint="DRENAJE", pts_pdf=[tuple(p) for p in pts],
                              kind="drain_ungd", kinds=kinds or ["end"] + ["bend"] * (len(pts) - 2) + ["end"])


def _buzon(x, y, r=4.0):
    return {"layer": SYM, "importable": True, "center": (x, y), "circle": (float(x), float(y), r)}


def test_horquilla_en_la_punta_de_la_banda_se_va():
    """La banda termina en una «Y» de dos ramalitos de 6 pt: la línea queda sola y recta, sin ramalitos."""
    linea = _pl([(0, 100), (200, 100)])
    a = _pl([(200, 100), (205, 97)], ["junction", "end"])
    b = _pl([(200, 100), (205, 103)], ["junction", "end"])
    pls = [linea, a, b]
    RR.enderezar(pls, [], 1.0)
    assert pls == [linea]
    assert all(abs(y - 100) < 1e-6 for _x, y in linea.pts_pdf)
    assert 200 <= linea.pts_pdf[-1][0] <= 206


def test_ramalito_suelto_de_un_vertice_se_va():
    """El ramalito de 7 pt que sale de la línea hacia un rótulo («No debe ir»)."""
    linea = _pl([(0, 100), (100, 100), (200, 100)])
    ramalito = _pl([(100, 100), (96, 94)], ["tee", "end"])
    pls = [linea, ramalito]
    RR.enderezar(pls, [], 1.0)
    assert ramalito not in pls and linea in pls


def test_enredo_en_una_cajita_pasa_recto():
    """La línea entra a la cajita «J» por arriba y sale por abajo; dentro, el esqueleto dejó trocitos y un rodeo."""
    arriba = _pl([(100, 0), (100, 95), (98, 97)])
    abajo = _pl([(101, 105), (100, 200)])
    t1 = _pl([(98, 97), (96, 100), (99, 102)], ["junction", "bend", "end"])
    t2 = _pl([(98, 97), (102, 99)], ["junction", "end"])
    pls = [arriba, abajo, t1, t2]
    RR.enderezar(pls, [], 1.0)
    assert len(pls) == 1
    pts = pls[0].pts_pdf
    assert min(p[1] for p in pts) <= 0.01 and max(p[1] for p in pts) >= 199.99
    assert all(abs(x - 100) <= 1.5 for x, _y in pts)


def test_la_punta_que_no_llega_a_su_buzon_llega_al_centro():
    """La línea muere 3 pt antes del borde del sumidero «P» (o del «DW», del «M»): llega a su centro."""
    linea = _pl([(0, 100), (90, 100)])
    pls = [linea]
    RR.enderezar(pls, [_buzon(97, 100)], 1.0)
    assert linea.pts_pdf[-1] == (97.0, 100.0) and linea.kinds[-1] == "vault"


def test_la_punta_que_pasa_de_costado_junto_a_un_buzon_no_se_tuerce():
    linea = _pl([(0, 100), (90, 100)])
    pls = [linea]
    RR.enderezar(pls, [_buzon(96, 104.5)], 1.0)          # el buzón queda de costado: no es su llegada
    assert linea.pts_pdf[-1] == (90, 100) and linea.kinds[-1] != "vault"


def test_el_marco_del_sumidero_no_es_red():
    """Los bordes (capa fina) de la caja del sumidero hexagonal salían como dos rayas o una «U»."""
    red = _pl([(0, 300), (300, 300)])
    arriba = _pl([(64, 80), (79, 80)])
    abajo = _pl([(64, 90), (79, 90)])
    u = _pl([(156, 42), (140, 42), (140, 52), (156, 52)])
    pls = [red, arriba, abajo, u]
    simbolos = [(65, 80.2, 72.5, 87.5), (146, 42.4, 153.4, 49.6)]
    RR.enderezar(pls, [], 1.0, simbolos=simbolos)
    assert pls == [red]


def test_la_linea_pasa_por_el_sumidero_hasta_el_buzon_de_enfrente():
    """«Debe pasar recto»: la línea llega por la izquierda, entre ella y el buzón de la derecha está el sumidero."""
    linea = _pl([(0, 85), (55, 85)])
    m = _buzon(85, 85, 5.3)
    pls = [linea]
    RR.enderezar(pls, [m], 1.0, simbolos=[(65, 81, 72, 88), (79.7, 79.7, 90.3, 90.3)])
    assert linea.pts_pdf[-1] == (85.0, 85.0) and linea.kinds[-1] == "vault"
    assert all(abs(y - 85) < 1e-6 for _x, y in linea.pts_pdf)


def test_sin_punta_suelta_no_se_inventa_linea_entre_dos_buzones():
    a, b = _buzon(50, 85, 5.3), _buzon(85, 85, 5.3)
    otra = _pl([(0, 300), (300, 300)])
    pls = [otra]
    RR.enderezar(pls, [a, b], 1.0, simbolos=[(63, 81, 71, 89)])
    assert pls == [otra] and len(otra.pts_pdf) == 2


def test_el_ramal_llega_en_t_por_su_recta():
    """«Debe llegar recto»: el último tramo torcía para caer en un vértice de la principal."""
    principal = _pl([(0, 100), (100, 100), (200, 100)])
    ramal = _pl([(104, 0), (104, 94), (100, 100)], ["end", "bend", "tee"])
    pls = [principal, ramal]
    RR.enderezar(pls, [], 1.0)
    x, y = ramal.pts_pdf[-1]
    assert abs(y - 100) < 1e-6 and abs(x - 104) < 0.3 and ramal.kinds[-1] == "tee"
    assert len(ramal.pts_pdf) == 2


def test_la_misma_linea_dos_veces_queda_una():
    """Dos copias del mismo largo (la conexión del buzón al sumidero, dos veces en la capa fina): queda una."""
    a = _pl([(0, 100), (0, 116)], ["vault", "vault"])
    b = _pl([(0, 116), (0, 100)], ["vault", "vault"])
    pls = [a, b]
    RR.enderezar(pls, [], 1.0)
    assert len(pls) == 1


def test_simbolos_apilados_unidos_por_un_taquito_quedan_unidos():
    """Captura 12: «M», taquito de banda (símbolo 6×6), rejilla, en columna: la línea pasa de uno al otro; la punta
    suelta pegada a la rejilla llega a su centro."""
    entra = _pl([(100, 0), (100, 45)])                   # llega al «M» por arriba
    sale = _pl([(104.8, 71.8), (130, 100)])              # sale de la rejilla hacia abajo a la derecha
    simbolos = [(95, 45, 105, 55), (97, 55.5, 103, 61.5), (95.5, 62, 104.5, 71)]
    m = _buzon(100, 50, 5.3)
    pls = [entra, sale]
    RR.enderezar(pls, [m], 1.0, simbolos=simbolos)
    puntos = {tuple(round(v, 3) for v in q) for pl in pls for q in pl.pts_pdf}
    assert (100.0, 50.0) in puntos and (100.0, 66.5) in puntos       # centro del «M» y de la rejilla
    assert (100.0, 66.5) in [tuple(q) for q in sale.pts_pdf]          # sale pasa por la rejilla (unida a la conexión)


def test_sin_taquito_no_se_unen_dos_simbolos_vecinos():
    otra = _pl([(0, 300), (300, 300)])
    pls = [otra]
    RR.enderezar(pls, [], 1.0, simbolos=[(95, 45, 105, 55), (106, 45, 116, 55)])
    assert pls == [otra]


def test_la_conexion_llega_al_buzon_no_a_la_union_pegada():
    """«No debería desviarse»: la rejilla bajaba en diagonal a la unión de la curva, a 14 pt del «M»."""
    curva = _pl([(0, 100), (85.5, 100)], ["end", "junction"])
    tramito = _pl([(85.5, 100), (100, 100)], ["junction", "vault"])
    sigue = _pl([(100, 100), (300, 100)], ["vault", "end"])
    diagonal = _pl([(100, 84), (85.5, 100)], ["vault", "junction"])
    pls = [curva, tramito, sigue, diagonal]
    RR.enderezar(pls, [_buzon(100, 100), _buzon(100, 84)], 1.0)
    rectas = [pl.pts_pdf for pl in pls]
    assert [(100, 84), (100, 100)] in rectas or [(100, 100), (100, 84)] in rectas
