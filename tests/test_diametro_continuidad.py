"""Diámetro por CONTINUIDAD con la red (pedido 2026-11-03): una línea que sigue de frente a otra con diámetro
confirmado, sin estructura entre medio, lleva ese diámetro; un ramal no es mayor que su principal
(`nucleo/diametro_continuidad`), y la IA lo propone en primera persona (`ia/diametro_ia`, `ia/diametro_ia_replica`)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT), str(ROOT / "tests")]

from ia import diametro_ia as DI  # noqa: E402
from ia import diametro_ia_replica as DR  # noqa: E402
from ia import proveedor as PV  # noqa: E402
from nucleo import diametro_continuidad as DC  # noqa: E402
from ollama_falso import OllamaFalso  # noqa: E402


def _p(pts, d=None, layer="DRENAJE"):
    p = {"layer": layer, "pts": pts, "diam": d or 12.0, "diam_plano": {"estado": "sin_dato", "cerca": []}}
    if d:
        p["diam_elegido"] = True
    return p


def test_sigue_de_frente_toma_el_diametro_de_la_confirmada():
    pipes = [_p([(0, 0), (100, 0)], 18.0), _p([(100, 0), (200, 2)]), _p([(200, 2), (300, 2)], 18.0)]
    c = DC.analizar(1, pipes, ft_px=0.25)
    assert [o["diam_in"] for o in c["opciones"]] == [18.0] and c["opciones"][0]["fuerza"] == "alta"
    assert "DRENAJE-1" in c["opciones"][0]["texto"] and "DRENAJE-3" in c["opciones"][0]["texto"]


def test_atraviesa_lineas_sin_diametro_y_dice_donde():
    pipes = [_p([(0, 0), (100, 0)], 24.0), _p([(100, 0), (200, 0)]), _p([(200, 0), (300, 0)])]
    c = DC.analizar(2, pipes, ft_px=0.5)
    o = c["opciones"][0]
    assert o["diam_in"] == 24.0 and o["fuerza"] == "media" and "50 ft" in o["texto"]


def test_dos_lados_distintos_dan_dos_opciones_y_un_giro_no_es_continuidad():
    pipes = [_p([(0, 0), (100, 0)], 18.0), _p([(100, 0), (200, 0)]), _p([(200, 0), (300, 0)], 24.0)]
    assert sorted(o["diam_in"] for o in DC.analizar(1, pipes)["opciones"]) == [18.0, 24.0]
    esquina = [_p([(0, 0), (100, 0)], 18.0), _p([(100, 0), (100, 100)])]          # giro de 90°: no sigue
    assert DC.analizar(1, esquina)["opciones"] == []


def test_ramal_no_mayor_que_su_principal():
    pipes = [_p([(0, 0), (300, 0)], 12.0), _p([(150, 0), (150, 100)]), _p([(150, 100), (150, 200)], 18.0)]
    c = DC.analizar(1, pipes)
    assert c["max_in"] == 12.0 and c["opciones"] == []                             # 18" sería mayor que la principal


def test_otra_utilidad_o_abandonada_no_cuentan():
    pipes = [_p([(0, 0), (100, 0)], 18.0, layer="AGUA"), _p([(100, 0), (200, 0)])]
    assert DC.analizar(1, pipes)["opciones"] == []


def _prov(f):
    return PV.crear({"proveedor": "ollama", "url": f.url, "modelo": "qwen3-vl:8b"})


def test_la_ia_propone_por_continuidad_sin_preguntar_al_modelo():
    pipes = [_p([(0, 0), (100, 0)], 18.0), _p([(100, 0), (200, 0)])]
    f = DI.ficha(pipes[1], "Drenaje", largo_ft=25, continuidad=DC.analizar(1, pipes, ft_px=0.25))
    with OllamaFalso(lambda c: "{}") as srv:
        s = DI.sugerir(_prov(srv), f)
        assert (s.diam_in, s.origen, s.confianza) == (18.0, "continuidad", "alta") and srv.pedidos == []
        assert s.motivo.startswith("Esta línea sigue de frente") and "18" in s.motivo


def test_replica_contesta_la_pregunta_y_mantiene_la_eleccion():
    pipes = [_p([(0, 0), (100, 0)], 18.0), _p([(100, 0), (200, 0)])]
    f = DI.ficha(pipes[1], "Drenaje", largo_ft=25, continuidad=DC.analizar(1, pipes, ft_px=0.25))
    antes = DI.Sugerencia(18.0, None, "alta", "sigue de frente", "", "continuidad")
    resp = json.dumps({"respuesta": "Te propuse 18\" porque la línea DRENAJE-1 sigue de frente con ese diámetro.",
                       "eleccion": "C1", "confianza": "alta", "pregunta": None})
    with OllamaFalso(lambda c: resp) as srv:
        s = DR.replicar(_prov(srv), f, antes, [], "¿Por qué?")
        contenido = srv.pedidos[-1]["messages"][-1]["content"]
    assert s.diam_in == 18.0 and s.origen == "continuidad" and s.motivo.startswith("Te propuse")
    assert "Tu elección anterior: C1" in contenido and "C1: 18" in contenido


def test_replica_no_cita_cifras_inventadas():
    pipes = [_p([(0, 0), (100, 0)], 18.0), _p([(100, 0), (200, 0)])]
    f = DI.ficha(pipes[1], "Drenaje", largo_ft=25, continuidad=DC.analizar(1, pipes, ft_px=0.25))
    resp = json.dumps({"respuesta": "Por el caudal de 350 gpm te propongo 18\".", "eleccion": "C1",
                       "confianza": "alta", "pregunta": None})
    with OllamaFalso(lambda c: resp) as srv:
        s = DR.replicar(_prov(srv), f, None, [], "¿y eso?")
    assert s.diam_in == 18.0 and "350" not in s.motivo
