"""La IA del diámetro señala de qué habla (pedido 2026-11-03): sin colores que el usuario no ve, con el papel de cada
línea medido por la app, marcas y enlaces en el plano, y aprobar en las líneas que siguen de frente."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ia import diametro_agente as DA  # noqa: E402
from ia import diametro_ia as DI  # noqa: E402
from ia import diametro_ia_replica as DR  # noqa: E402
from ia import proveedor as PV  # noqa: E402
from nucleo import diametro_vecinas as DV  # noqa: E402
from ollama_falso import OllamaFalso  # noqa: E402
from test_diametro_ia_ventana import _elegir, _esperar, _pipe, _ventana  # noqa: E402


def _linea(pts, diam=None, layer="ALCANTARILLADO"):
    p = {"layer": layer, "pts": pts, "diam": diam or 12.0}
    if diam:
        p["diam_elegido"] = True
    return p


def _roles(i, pipes):
    return {v["linea"]: v["rol"] for v in DV.vecinas(i, pipes)}


def test_ramal_que_llega_al_interior_de_la_principal():
    pipes = [_linea([(0, 0), (100, 0)]), _linea([(50, 0), (50, 80)])]
    assert _roles(1, pipes) == {0: "principal"}
    assert _roles(0, pipes) == {1: "ramal"}


def test_ramal_que_llega_a_un_nodo_donde_la_principal_esta_partida():
    pipes = [_linea([(0, 0), (50, 0)]), _linea([(50, 0), (100, 0)]), _linea([(50, 0), (50, 80)])]
    assert _roles(2, pipes) == {0: "principal", 1: "principal"}
    assert _roles(0, pipes) == {1: "sigue", 2: "ramal"}


def test_otra_utilidad_no_es_vecina_y_la_que_toca_no_se_inventa_papel():
    pipes = [_linea([(0, 0), (100, 0)]), _linea([(50, 0), (50, 80)], layer="AGUA"),
             _linea([(100, 0), (100, 50)]), _linea([(100, 0), (160, 60)])]
    assert _roles(0, pipes) == {2: "toca", 3: "toca"}


def test_vecina_sin_confirmar_no_da_diametro():
    pipes = [_linea([(0, 0), (100, 0)]), _linea([(50, 0), (50, 80)]), _linea([(100, 0), (200, 0)], 15.0)]
    vs = {v["linea"]: v["diam_in"] for v in DV.vecinas(1, pipes)}
    assert vs == {0: None}
    assert {v["linea"]: v["diam_in"] for v in DV.vecinas(0, pipes)} == {1: None, 2: 15.0}


def test_tramo_para_en_un_buzon_en_una_confirmada_y_en_una_esquina():
    pipes = [_linea([(0, 0), (100, 0)]), _linea([(100, 0), (200, 0)]), _linea([(200, 0), (300, 0)], 15.0),
             _linea([(0, 0), (0, 90)])]
    assert DV.tramo_sin_diametro(0, pipes) == [1]
    buzon = [{"x": 100.0, "y": 0.0}]
    assert DV.tramo_sin_diametro(0, pipes, estructuras=buzon) == []


def test_sin_colores():
    assert DA.sin_colores("La línea MAGENTA es un ramal lateral") == "Esta línea es un ramal lateral"
    assert DA.sin_colores("revisé la línea en magenta y el rótulo en turquesa") == "revisé esta línea y el rótulo"
    assert DA.sin_colores("el rótulo R1 en la imagen llega a ella") == "el rótulo R1 llega a ella"


def test_una_pregunta_o_el_dato_de_otra_linea_no_es_un_diametro_de_esta():
    assert DR.afirmados('pero porque 8 si la línea principal es 15"') == []
    assert DR.afirmados('¿será de 18"?') == []
    assert DR.afirmados('la principal es 15", esta es de 8"') == [8.0]
    assert DR.afirmados('es la principal de 15"') == [15.0]
    assert DR.afirmados('Es un lateral de 18"') == [18.0]
    assert DR.afirmados('no es 8, es 15"') == [15.0]
    assert DR.afirmados(['¿y 10"?', 'es de 12"']) == [12.0]


def _ficha(vecinas):
    return dict(utilidad="ALCANTARILLADO", utilidad_nombre="Alcantarillado", nombre="ALCANTARILLADO-3", capa="C-SSWR",
                sistema="", estado_capa="", abandonada=False, largo_ft=22.8, por_defecto_in=12.0, estado_plano="sin_dato",
                paredes_in=None, perfil_in=[], rotulos=[], mapa=False, acometida=False, vecinas=vecinas, tramo=[],
                normativa=[dict(id="N1", diam_in=8.0, criterio='mínimo 8"', fuente="F200", tipo="", tipo_supuesto=False)])


def _v(id_, nombre, rol, d=None):
    return dict(id=id_, linea=int(id_[1:]), nombre=nombre, rol=rol, diam_in=d, punto=[1.0, 2.0])


def _replicar(f, mensaje, anterior=None, respuesta="{}"):
    with OllamaFalso(lambda c: respuesta) as falso:
        prov = PV.crear({"proveedor": "ollama", "url": falso.url, "modelo": "qwen3-vl:8b"})
        return DR.replicar(prov, f, anterior, [], mensaje), falso.pedidos


def test_cual_es_el_ramal_lo_contesta_la_geometria_sin_el_modelo():
    antes = DI.Sugerencia(8.0, None, "media", "te propongo 8", "", "normativa")
    s, pedidos = _replicar(_ficha([_v("L1", "ALCANTARILLADO-1", "principal")]), "pero cual es el ramal", antes)
    assert pedidos == [] and s.diam_in == 8.0 and s.senaladas == ["L1"]
    assert "Esta línea es el ramal" in s.motivo and "sin diámetro confirmado" in s.motivo
    s, _ = _replicar(_ficha([_v("L1", "A-1", "ramal", 6.0)]), "¿cuál es la principal?", antes)
    assert "Esta línea es la principal" in s.motivo and '6" confirmados' in s.motivo
    s, _ = _replicar(_ficha([]), "cual es el ramal", antes)
    assert "No encontré" in s.motivo and s.senaladas == []


def test_una_pregunta_de_diametro_sigue_yendo_al_modelo():
    resp = json.dumps({"respuesta": "La línea magenta es L1", "eleccion": "N1", "confianza": "media", "senala": ["L1", "L9"]})
    s, pedidos = _replicar(_ficha([_v("L1", "ALCANTARILLADO-1", "principal")]), 'pero porque 8 si la línea principal es 15"',
                           respuesta=resp)
    texto = pedidos[-1]["messages"][-1]["content"]
    assert "L1: ALCANTARILLADO-1" in texto and "U1:" not in texto
    assert "magenta" not in s.motivo.lower() and s.diam_in == 8.0 and s.senaladas == ["L1"]


def test_enlaces_con_nombre_y_codigo():
    f = _ficha([_v("L1", "ALCANTARILLADO-1", "principal")])
    txt = DA.enlazar("llega a L1, o sea ALCANTARILLADO-1; L7 no existe", f)
    assert txt.count("href='ia:L1'") == 2 and "L7" in txt and "ia:L7" not in txt


def test_ventana_senala_enlaza_y_aprueba_en_las_que_siguen():
    a, b, c = _pipe(), _pipe(), _pipe()
    a["pts"], b["pts"], c["pts"] = [(50.0, 100.0), (150.0, 100.0)], [(150.0, 100.0), (250.0, 100.0)], [(150.0, 100.0), (150.0, 220.0)]
    for p in (a, b, c):                              # gravedad lleva un buzón visible en cada vértice: ahí se corta
        p["layer"] = "ELECTRICO"
    with OllamaFalso(lambda q: json.dumps({"rotulo": "R1", "confianza": "alta", "motivo": "su guía llega", "pista": None})) as srv:
        w = _ventana(srv, [a, b, c])
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        assert _esperar(w, lambda: w._diam_ia_pedido is None and (w._diam_ia_sug(0) or None) is not None and
                        w._diam_ia_sug(0).diam_in == 18.0)
        w._diam_ia_refrescar()
        assert w.btn_diam_ia_vecinas.isVisibleTo(w.gprop) and "1" in w.btn_diam_ia_vecinas.text()
        assert w._diam_ia_mi.vigentes()                             # el rótulo y la línea que sigue, marcados
        n = len(w._diam_ia_mi.items)
        f = w._diam_ia_ficha(0)
        ramal = next(v for v in f["vecinas"] if v["linea"] == 2)
        assert ramal["rol"] == "ramal"
        w._diam_ia_ir("ia:" + ramal["id"])                          # clic en el chat: marca y no cambia la selección
        assert w.sel_pipe == 0 and len(w._diam_ia_mi.items) > n
        w.usar_diametro_en_vecinas()
        assert (w.pipes[0]["diam"], w.pipes[1]["diam"], w.pipes[2]["diam"]) == (18.0, 18.0, 12.0)
        w.undo()                                                    # un solo paso de deshacer
        assert (w.pipes[0]["diam"], w.pipes[1]["diam"]) == (12.0, 12.0)
        w._diam_ia_quitar_senales()
        assert not w._diam_ia_mi.items
