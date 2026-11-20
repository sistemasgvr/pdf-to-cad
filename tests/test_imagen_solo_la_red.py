"""Redes leídas de una IMAGEN: solo las líneas de la red (pedido del usuario 2026-11-20, QS SD de Phoenix).

`recognition_imagen_rectas.enderezar`: el ramal que muere unos pt antes de otra línea llega a ella (T); los trocitos
sueltos por las dos puntas (bordes de la caja de un símbolo) se quitan, salvo los que van de un símbolo a otro; un buzón
de la imagen al que no llega ninguna línea no se importa."""
import os
import sys

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]

from reconocimiento import recognition_imagen_rectas as RR  # noqa: E402
from reconocimiento.recognition import RecognizedPolyline  # noqa: E402

CAPA = 'PDF_STYLE:["img","line",[0,77,168]]'


def _pl(pts, kinds=None):
    return RecognizedPolyline(layer_ocg=CAPA, utility_hint="DRENAJE", pts_pdf=[tuple(p) for p in pts],
                              kind="drain_ungd", kinds=kinds or ["end"] + ["bend"] * (len(pts) - 2) + ["end"])


def test_el_ramal_que_muere_antes_de_la_principal_llega_a_ella():
    principal = _pl([(0, 100), (300, 100)])
    ramal = _pl([(120, 20), (120, 92)])                  # termina 8 pt antes de la principal
    lejos = _pl([(220, 20), (220, 70)])                  # 30 pt: no se toca
    pls = [principal, ramal, lejos]
    RR.enderezar(pls, [], 1.0)
    assert ramal.pts_pdf[-1] == (120.0, 100.0) and ramal.kinds[-1] == "tee"
    assert lejos.pts_pdf[-1] == (220, 70) and lejos.kinds[-1] == "end"


def test_casi_paralela_no_se_prolonga():
    principal = _pl([(0, 100), (300, 100)])
    rasante = _pl([(20, 96), (140, 99)])                 # va casi paralela (≈1.4°): no es una T
    pls = [principal, rasante]
    RR.enderezar(pls, [], 1.0)
    assert rasante.kinds[-1] == "end"


def test_trocito_suelto_se_va_y_la_conexion_entre_dos_simbolos_se_queda():
    red = _pl([(0, 200), (400, 200)])
    borde = _pl([(50, 60), (59, 60)])                    # 9 pt, junto a UN símbolo: borde de su caja
    conexion = _pl([(150, 50), (150, 61)])               # 11 pt, del símbolo de arriba al de abajo
    pls = [red, borde, conexion]
    simbolos = [(48, 50, 61, 59),                         # el del borde (sus dos puntas lo tocan)
                (145, 40, 155, 50), (144, 61, 156, 70)]   # los dos de la conexión
    RR.enderezar(pls, [], 1.0, simbolos=simbolos)
    assert borde not in pls and conexion in pls and red in pls


def test_buzon_de_la_imagen_sin_linea_no_se_importa():
    red = _pl([(0, 100), (300, 100)], ["vault", "vault"])
    con = {"layer": 'PDF_STYLE:["img","sym",[0,77,168]]', "importable": True, "center": (0, 100),
           "circle": (0.0, 100.0, 4.0)}
    sin = {"layer": 'PDF_STYLE:["img","sym",[0,77,168]]', "importable": True, "center": (150, 160),
           "circle": (150.0, 160.0, 4.0)}
    vectorial = {"layer": "C-STRM-MHOL", "importable": True, "center": (150, 300), "circle": (150.0, 300.0, 4.0)}
    RR.enderezar([red], [con, sin, vectorial], 1.0)
    assert con["importable"] is True
    assert sin["importable"] is False and sin.get("sin_linea")
    assert vectorial["importable"] is True                # las capas vectoriales no cambian
