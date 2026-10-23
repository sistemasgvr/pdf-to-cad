"""Grosor (diámetro) en los mapas SIN capas: lo que el mapa escribe junto a cada tramo, y solo lo
SEGURO se pone (pedido del usuario 2026-10-23, «QS Water_Indian School_South»): lo dudoso o sin dato
queda con el diámetro por defecto y un aviso en el editor, como en el flujo CAD.
  · `leer`: qué rótulos son de una tubería, de una acometida o de nada (camisa, accesorio);
  · `asignar`: el rótulo paralelo y pegado; entre dos líneas = de ninguna; en la prolongación de la punta;
  · tramos del SIG: una ruta que cruza tuberías de distinto diámetro se parte; un tramo sin rótulo
    toma el de sus vecinos si dicen lo mismo; entre dos distintos, dudoso;
  · acometidas: su rótulo o la nota de la leyenda;
  · con el PDF de Phoenix (si está): hojas 4 y 10 de Water South.
"""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fitz = pytest.importorskip("fitz")

from hoja import acometidas_mapa, pdf_styles  # noqa: E402
from nucleo import diametro_plano  # noqa: E402
from reconocimiento import recognition_grosor_mapa as G  # noqa: E402
from reconocimiento import recognition_grosor_mapa_hoja as H  # noqa: E402
from reconocimiento import recognition_grosor_tramos as T  # noqa: E402

PHOENIX = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
WATER_S = PHOENIX / "QS Water_Indian School_South.pdf"
needs_phoenix = pytest.mark.skipif(not WATER_S.is_file(), reason="PDF de Phoenix no disponible")

RED = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.38,"[] 0",null,1.0,null]'
TAP = acometidas_mapa.capa(pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.19,"[] 0",null,1.0,null]', "AGUA")


@dataclass
class _L:                    # lo que usa el módulo de `RecognizedPolyline` (`partir` usa `replace`)
    layer_ocg: str
    pts_pdf: list
    kinds: list
    fillets: dict = field(default_factory=dict)
    grosor: dict = field(default_factory=dict)
    diam_in: Optional[float] = None


def _pl(pts, kinds=None, layer=RED, diam=None):
    pts = [tuple(map(float, p)) for p in pts]
    return _L(layer, pts, list(kinds or (["end"] + ["bend"] * (len(pts) - 2) + ["end"])), diam_in=diam)


def _rot(texto, centro, d=(1.0, 0.0), tam=1.7):
    pulg, mat, aco = G.leer(texto)
    return G.RotuloMapa(tuple(map(float, centro)), d, tam, 0.55 * tam * len(texto), pulg, mat, aco, texto)


def _tap(pl):
    return acometidas_mapa.es_capa(pl.layer_ocg)


def _aplicar(lineas, rots, diam_tap=None):
    cuenta = G.aplicar(lineas, rots, _tap, 1.0, diam_tap)
    out = list(lineas)
    G.partir(out, cuenta["partir"])
    return out, cuenta


# ── qué dice cada rótulo ──────────────────────────────────────────────────
@pytest.mark.parametrize("texto, esperado", [
    ('8"', (8.0, "", False)), ('12" DIP', (12.0, "DIP", False)), ('12" DIP (CP)', (12.0, "DIP", False)),
    ('6" DIP  FL', (6.0, "DIP", False)), ('8" Unk', (8.0, "UNK", False)), ('30" MOD PSD', (30.0, "", False)),
    ('8" DIP PER 15-1989-0039', (8.0, "DIP", False)), ('1.5"', (1.5, "", False)),
    ("278' 2\"", (2.0, "", True)), ('2" 62\'', (2.0, "", True)), ('TAP IN MH 6"', (6.0, "", True)),
    ('6" TAP', (6.0, "", True)),
    ('72" STEEL CASING', None), ('2" ARV', None), ('2" BLOW OFF', None), ('MH 48"', None),
    ("SCALE: 1\" = 100'", None), ('#2038"', None), ('404"', None), ('6" D', None),
])
def test_que_dice_cada_rotulo(texto, esperado):
    assert G.leer(texto) == esperado


def test_rotulos_diminutos_son_la_referencia_a_un_detalle():
    """El recuadro «W-16-19-1» repite en miniatura (letra 0.37 pt) los rótulos de un detalle."""
    rs = [_rot('54" PCCP', (0, 0), tam=1.7), _rot('8"', (9, 0), tam=1.69), _rot('12" RCP', (5, 5), tam=0.37)]
    assert [r.texto for r in G.sin_miniaturas(rs)] == ['54" PCCP', '8"']
    # hoja compuesta con un mapa a otra escala (letra 0.89): la típica es la de SU pieza
    otra = [G.replace(_rot('6"', (0, 50), tam=0.89), pieza=1), G.replace(_rot('8"', (9, 50), tam=0.9), pieza=1)]
    assert len(G.sin_miniaturas(rs + otra + otra)) == 6


# ── a qué línea va cada rótulo ────────────────────────────────────────────
def test_rotulo_paralelo_y_pegado_a_su_tuberia():
    a, b = _pl([(0, 0), (100, 0)]), _pl([(0, 20), (100, 20)])
    out, cuenta = _aplicar([a, b], [_rot('8" DIP', (50, -1.5)),
                                    _rot('6"', (50, 5), d=(0.0, 1.0))])       # perpendicular: de nadie
    assert a.grosor["estado"] == "leido" and a.diam_in == 8.0 and a.grosor["material"] == "DIP"
    assert b.grosor == {"estado": "sin_dato"} and b.diam_in is None
    assert (cuenta["con"], cuenta["revisar"], cuenta["sin"]) == (1, 0, 1)


def test_rotulo_entre_dos_lineas_pegadas_no_es_de_ninguna():
    """La de 54" PCCP y una de 12" a 2.5 pt: el «54" PCCP» escrito ENTRE las dos no se sabe de cuál es."""
    a, b = _pl([(0, 0), (100, 0)]), _pl([(0, 2.5), (100, 2.5)])
    _aplicar([a, b], [_rot('54" PCCP', (50, 1.1))])
    for pl in (a, b):
        assert pl.grosor["estado"] == "dudoso" and pl.grosor["fuente"] == "cerca"
        assert pl.grosor["candidatos"] == [54.0] and pl.diam_in is None


def test_rotulo_por_fuera_de_dos_lineas_pegadas_es_de_la_mas_cercana():
    """Dos de 8" a 1.3 pt, cada una con su rótulo por fuera (QS Sewer North h.3)."""
    a, b = _pl([(0, 0), (100, 0)]), _pl([(0, 1.3), (100, 1.3)])
    _aplicar([a, b], [_rot('8"', (50, -4.4)), _rot('6"', (50, 5.7))])
    assert (a.diam_in, b.diam_in) == (8.0, 6.0)


def test_rotulo_en_la_prolongacion_de_su_linea():
    """Dos líneas contra incendios a 1.8 pt con «FIRELINE / 8" DIP» bajo la punta de cada una."""
    a, b = _pl([(0, 0), (0, 19)]), _pl([(1.8, 0), (1.8, 19)])
    _aplicar([a, b], [_rot('8" DIP', (0.05, 23.4), d=(0.0, -1.0)), _rot('6" DIP', (1.85, 23.4), d=(0.0, -1.0))])
    assert (a.diam_in, b.diam_in) == (8.0, 6.0)


def test_rotulo_de_una_tuberia_corta_en_otro_rumbo_no_es_de_la_principal():
    """«12" CIP» escrito en horizontal junto a una tubería vertical corta, a 5 pt de la de 54"."""
    principal = _pl([(0, 0), (200, 0)])
    vertical = _pl([(110, 0), (110, 30)])
    _aplicar([principal, vertical], [_rot('54" PCCP', (40, -1.1)), _rot('12" CIP', (114, 5))])
    assert principal.diam_in == 54.0 and principal.grosor["textos"] == ['54" PCCP']
    assert vertical.grosor["estado"] == "dudoso" and vertical.grosor["candidatos"] == [12.0]


# ── tramos del SIG ────────────────────────────────────────────────────────
def test_ruta_que_cruza_dos_diametros_se_parte():
    """Rótulos 12" en el primer tramo y 8" en el tercero: el del medio no tiene y no se sabe dónde cambia."""
    ruta = _pl([(0, 0), (100, 0), (200, 0), (300, 0)], ["end", "junction", "junction", "end"])
    out, cuenta = _aplicar([ruta], [_rot('12"', (50, -1.5)), _rot('8"', (250, -1.5))])
    assert [(q.pts_pdf[0][0], q.pts_pdf[-1][0], q.grosor["estado"], q.diam_in) for q in out] == [
        (0.0, 100.0, "leido", 12.0), (100.0, 200.0, "dudoso", None), (200.0, 300.0, "leido", 8.0)]
    assert out[1].grosor["fuente"] == "cambio" and out[1].grosor["candidatos"] == [8.0, 12.0]
    assert all(q.grosor.get("partida") for q in out) and cuenta["partidas"] == 1


def test_tramo_sin_rotulo_entre_dos_iguales_toma_su_diametro():
    ruta = _pl([(0, 0), (100, 0), (200, 0), (300, 0)], ["end", "junction", "junction", "end"])
    out, cuenta = _aplicar([ruta], [_rot('8" CIP', (50, -1.5)), _rot('8" TRANS', (250, -1.5))])
    assert out == [ruta] and ruta.diam_in == 8.0 and cuenta["partidas"] == 0
    assert ruta.grosor["estado"] == "leido" and ruta.grosor["material"] == ""   # dos materiales


def test_un_tramo_no_tiene_dos_diametros_gana_la_mayoria_clara():
    ruta = _pl([(0, 0), (300, 0)])
    _aplicar([ruta], [_rot('8"', (50, -1.5)), _rot('8"', (150, -1.5)), _rot('6"', (250, -1.5))])
    assert ruta.diam_in == 8.0
    otra = _pl([(0, 0), (300, 0)])
    _aplicar([otra], [_rot('8"', (50, -1.5)), _rot('6"', (250, -1.5))])
    assert otra.grosor["estado"] == "dudoso" and otra.grosor["fuente"] == "mezcla"


def test_rotulo_que_ya_dice_la_tuberia_de_al_lado_no_es_de_esta():
    """El «6"» escrito en horizontal en la punta de una vertical de 6", sobre la principal de 8"."""
    principal = _pl([(0, 0), (200, 0)])
    vertical = _pl([(100, -0.1), (100, -60)])
    _aplicar([principal, vertical], [_rot('8"', (40, -1.5)), _rot('6"', (97.5, -2.0)),
                                     _rot('6"', (101.5, -30), d=(0.0, -1.0))])
    assert principal.diam_in == 8.0 and vertical.diam_in == 6.0


def test_tramos_sin_unir_toman_el_diametro_de_su_ruta():
    """Variante «Unir tramos» apagada: cada tramo sabe su diámetro por su ruta unida."""
    unida = [_pl([(0, 0), (100, 0), (200, 0)], ["end", "junction", "end"])]
    sueltas = [_pl([(0, 0), (100, 0)], ["end", "junction"]), _pl([(100, 0), (200, 0)], ["junction", "end"])]
    rots = [_rot('8"', (50, -1.5))]
    H.aplicar_variantes(unida, sueltas, rots, lambda p: True, _tap, 1.0, None, True)
    assert [q.diam_in for q in sueltas] == [8.0, 8.0] and unida[0].diam_in == 8.0
    cuenta = H.aplicar_variantes([_pl([(0, 0), (100, 0), (200, 0)], ["end", "junction", "end"])],
                                 [_pl([(0, 0), (100, 0)], ["end", "junction"]),
                                  _pl([(100, 0), (200, 0)], ["junction", "end"])],
                                 rots, lambda p: True, _tap, 1.0, None, False)
    assert (cuenta["con"], cuenta["sin"]) == (2, 0)


def test_estados_por_tramo():
    v, c = 8.0, T.CONFLICTO
    assert T.estados([v, None, v], [[], [], []], [[], [], []]) == [("leido", v)] * 3
    assert T.estados([None, v], [[], []], [[], []]) == [("leido", v)] * 2          # punta de la ruta
    assert T.estados([None, None], [[], []], [[], [6.0]]) == [("sin",), ("dudoso", (6.0,), "cerca")]
    assert T.estados([c, v], [[6.0, 8.0], []], [[], []])[0] == ("dudoso", (6.0, 8.0), "mezcla")


# ── acometidas ────────────────────────────────────────────────────────────
def test_acometida_su_rotulo_o_la_nota_de_la_leyenda():
    main = _pl([(0, 0), (200, 0)])
    t1 = _pl([(30, 0), (30, 8)], ["tee", "end"], layer=TAP, diam=0.75)
    t2 = _pl([(80, 0), (80, 8)], ["tee", "end"], layer=TAP, diam=0.75)
    t3 = _pl([(150, 0), (150, 1.9)], ["tee", "end"], layer=TAP, diam=0.75)
    _aplicar([main, t1, t2, t3], [_rot("278' 2\"", (31.2, 5), d=(0.0, -1.0)),
                                  _rot('12" DIP', (151.2, 5), d=(0.0, -1.0))], diam_tap=0.75)
    assert (t1.diam_in, t1.grosor["fuente"]) == (2.0, "rotulo")
    assert (t2.diam_in, t2.grosor["fuente"]) == (0.75, "leyenda")
    assert t3.diam_in == 0.75                    # «12" DIP» no es una acometida


def test_acometida_con_un_rotulo_cerca_que_no_es_seguro_queda_dudosa():
    """Tres rótulos apilados bajo una sola acometida reconocida (las otras dos no se reconocen)."""
    tap = _pl([(0, 0), (0, 13)], ["tee", "end"], layer=TAP, diam=0.75)
    _aplicar([tap], [_rot("597' 1.5\"", (-1.0, 18), d=(0.0, -1.0)), _rot("57' 1\"", (1.2, 17), d=(0.0, -1.0))],
             diam_tap=0.75)
    assert tap.grosor["estado"] == "dudoso" and tap.diam_in is None
    assert tap.grosor["candidatos"] == [1.0, 1.5]


# ── el aviso del editor ───────────────────────────────────────────────────
def test_aviso_del_editor_para_un_tramo_dudoso_del_mapa():
    cerca = diametro_plano.mensaje({"estado": "dudoso", "fuente": "cerca", "candidatos": [54.0],
                                    "textos": ['54" PCCP']}, 6.0)
    cambio = diametro_plano.mensaje({"estado": "dudoso", "fuente": "cambio", "candidatos": [8.0, 12.0]}, 6.0)
    assert "54" in cerca and "54\" PCCP" in cerca
    assert "8" in cambio and "12" in cambio
    from nucleo import model_ops
    pipes = [{"pts": [(0, 0), (10, 0)], "layer": "AGUA", "diam": model_ops.DIAM_DEFECTO_IN, "diam_elegido": False,
              "diam_plano": diametro_plano.de_grosor({"estado": "dudoso", "fuente": "cambio",
                                                       "candidatos": [8.0, 12.0]})},
             {"pts": [(0, 5), (10, 5)], "layer": "AGUA", "diam": 8.0, "diam_elegido": True,
              "diam_plano": diametro_plano.de_grosor({"estado": "leido", "diam_in": 8.0, "fuente": "rotulo"})}]
    avisos = diametro_plano.avisos(pipes)
    assert [a.pipe for a in avisos] == [0]


# ── con el PDF de Phoenix ─────────────────────────────────────────────────
def _red(r):
    return [pl for pl in r.drawable if not acometidas_mapa.es_capa(pl.layer_ocg)]


def _en(lineas, p, tol=1.0):
    from reconocimiento.recognition_grosor_partir import _dist_seg
    return [pl for pl in lineas if any(_dist_seg(p, a, b) <= tol for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:]))]


@needs_phoenix
def test_phoenix_water_south_h4():
    """La principal de 54" PCCP (antes tomaba los 48" de la ruta unida con otra tubería) y el resto
    de la hoja: cada tubería con su rótulo, las dudosas y las sin dato con su aviso al importar."""
    from reconocimiento import recognition as rec
    r = rec.recognize_page(str(WATER_S), page_index=3, utility="AGUA", layer_roles=None, zoom=1.0)
    red = _red(r)
    estados = [(pl.grosor or {}).get("estado") for pl in red]
    assert estados.count("leido") >= 60 and estados.count("dudoso") <= 15 and None not in estados
    (main,) = [pl for pl in _en(red, (300.0, 153.0), 2.0) if pl.diam_in == 54.0]
    assert main.grosor["estado"] == "leido" and "54\" PCCP" in main.grosor["textos"]
    assert any(w.startswith("Diámetros del plano (rótulos junto a la tubería)") for w in r.warnings)
    pipes = rec.pipes_from_recognition(r, layer="AGUA", zoom=1.0)
    avisos = diametro_plano.avisos(pipes)
    dudosas = sum(1 for p in pipes if (p.get("diam_plano") or {}).get("estado") in ("dudoso", "sin_dato"))
    assert len(avisos) == dudosas and dudosas > 0


@needs_phoenix
def test_phoenix_water_south_h10_lineas_contra_incendios_a_2_pt():
    from reconocimiento import recognition as rec
    r = rec.recognize_page(str(WATER_S), page_index=9, utility="AGUA", layer_roles=None, zoom=1.0)
    for x in (281.3, 283.0):
        (pl,) = _en(_red(r), (x, 440.0), 0.5)
        assert pl.diam_in == 8.0 and pl.grosor["material"] == "DIP"
