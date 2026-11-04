"""IA del diámetro en los PDF vectoriales SIN capas (mapas SIG; pedido del usuario 2026-11-02).

  · `recognition_grosor_mapa_cerca.poner_cerca`: los rótulos junto a cada tubería dudosa o sin dato, con el formato de
    `grosor["cerca"]` del flujo CAD y su relación con la línea (junto / entre / otra / lejos); no cambia estados;
  · `ia/diametro_ia`: el pedido explica el mapa y `comprobar` exige más certeza a los rótulos que no van pegados;
  · con el PDF de Phoenix (si está): la hoja 4 de Water South deja la evidencia en cada línea dudosa o sin dato.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("fitz")

from ia import diametro_ia as DI  # noqa: E402
from nucleo import diametro_plano  # noqa: E402
from reconocimiento import recognition_grosor_mapa_cerca as MC  # noqa: E402
from test_grosor_mapa import WATER_S, _pl, _rot, needs_phoenix  # noqa: E402


def _sin_dato(*pls):
    for pl in pls:
        pl.grosor = {"estado": "sin_dato"}
    return pls


def _por_texto(pl):
    return {e["texto"]: e for e in pl.grosor["cerca"]}


def test_rotulo_pegado_es_junto_y_el_de_la_otra_tuberia_es_otra():
    a, b = _sin_dato(_pl([(0, 0), (100, 0)]), _pl([(0, 20), (100, 20)]))
    n = MC.poner_cerca([a, b], [_rot('8" DIP', (50, -1.5)), _rot('12"', (50, 21.5))], lambda p: False, 1.0)
    assert n == 2
    ea, eb = _por_texto(a), _por_texto(b)
    assert ea['8" DIP']["guia"] == "junto" and ea['8" DIP']["id"] == "R1" and ea['8" DIP']["mapa"]
    assert ea['12"']["guia"] == "otra" and eb['12"']["guia"] == "junto"
    # mismo formato que el flujo CAD: lo copia `de_grosor` y lo usa la ficha
    e = ea['8" DIP']
    assert {"id", "texto", "diam_in", "material", "util", "es_de", "dist_pt", "guia", "otra", "caja", "estacion",
            "union", "varios", "puntas", "punta_pt"} <= set(e)
    assert e["diam_in"] == 8.0 and e["material"] == "DIP" and len(e["caja"]) == 4
    assert diametro_plano.de_grosor(a.grosor)["cerca"] == a.grosor["cerca"]


def test_entre_dos_tuberias_pegadas_y_rotulo_cruzado_lejos():
    a, b = _sin_dato(_pl([(0, 0), (100, 0)]), _pl([(0, 2.5), (100, 2.5)]))
    MC.poner_cerca([a, b], [_rot('54" PCCP', (50, 1.1)), _rot('6"', (50, 6), d=(0.0, 1.0))], lambda p: False, 1.0)
    assert _por_texto(a)['54" PCCP']["guia"] == "entre" and _por_texto(b)['54" PCCP']["guia"] == "entre"
    assert _por_texto(a)['6"']["guia"] == "lejos" and not _por_texto(a)['6"']["paralelo"]


def test_solo_agrega_cerca_en_las_dudosas_o_sin_dato():
    a, b = _pl([(0, 0), (100, 0)]), _pl([(0, 20), (100, 20)])
    a.grosor = {"estado": "leido", "diam_in": 8.0}
    b.grosor = {"estado": "dudoso", "candidatos": [8.0, 12.0], "fuente": "mezcla"}
    MC.poner_cerca([a, b], [_rot('8"', (50, -1.5))], lambda p: False, 1.0)
    assert "cerca" not in a.grosor and a.grosor["estado"] == "leido"
    assert b.grosor["estado"] == "dudoso" and b.grosor["candidatos"] == [8.0, 12.0] and "cerca" in b.grosor


def test_sin_rotulos_queda_vacia():
    (a,) = _sin_dato(_pl([(0, 0), (100, 0)]))
    MC.poner_cerca([a], [], lambda p: False, 1.0)
    assert a.grosor["cerca"] == []                        # la IA puede proponer por normativa


# ── la IA ─────────────────────────────────────────────────────────────
def _e(id_, d, guia, **k):
    return dict(id=id_, texto=f'{d:g}"', diam_in=d, material="", util="", es_de=True, dist_pt=1.0, guia=guia,
                otra=None, caja=[0, 0, 1, 1], estacion=False, union=False, varios=1, normativa=True, mapa=True, **k)


def _ficha(*rot):
    return dict(utilidad="AGUA", utilidad_nombre="Agua", capa="Estilo Negro 0.38 pt", sistema="", estado_capa="",
                abandonada=False, largo_ft=None, por_defecto_in=8.0, estado_plano="dudoso", paredes_in=None,
                perfil_in=[], rotulos=list(rot), mapa=True, acometida=False)


def _resp(rot, conf):
    return {"rotulo": rot, "confianza": conf, "motivo": "m", "pista": ""}


def test_comprobar_en_mapa():
    f = _ficha(_e("R1", 8.0, "junto"), _e("R2", 12.0, "entre"), _e("R3", 6.0, "otra"),
               _e("R4", 2.0, "junto", acometida=True))
    assert DI.comprobar(_resp("R1", "media"), f).diam_in == 8.0
    assert DI.comprobar(_resp("R2", "media"), f).diam_in is None          # entre dos: solo con certeza alta
    assert DI.comprobar(_resp("R2", "alta"), f).diam_in == 12.0
    assert DI.comprobar(_resp("R3", "alta"), f).diam_in is None           # pegado a otra tubería
    assert DI.comprobar(_resp("R4", "alta"), f).diam_in is None           # de una acometida
    assert not DI.elegible(f["rotulos"][3], f) and DI.elegible(f["rotulos"][1], f)


def test_pedido_explica_el_mapa():
    _s, mensajes = DI.pedido(_ficha(_e("R1", 8.0, "junto"), _e("R2", 12.0, "otra")))
    texto = mensajes[-1]["content"]
    assert "mapa sin capas" in texto and "paralelo y pegado a ESTA línea" in texto
    assert "OTRA tubería del mapa" in texto


@needs_phoenix
def test_phoenix_water_south_h4_deja_la_evidencia():
    from reconocimiento import recognition as rec
    r = rec.recognize_page(str(WATER_S), page_index=3, utility="AGUA", layer_roles=None, zoom=1.0)
    red = [pl for pl in r.polylines if (pl.grosor or {}).get("estado")]
    dudosas = [pl for pl in red if pl.grosor["estado"] in ("dudoso", "sin_dato")]
    assert dudosas and all("cerca" in pl.grosor for pl in dudosas)
    assert not any("cerca" in pl.grosor for pl in red if pl.grosor["estado"] == "leido")
    assert any(e["guia"] in ("junto", "entre") for pl in dudosas for e in pl.grosor["cerca"])
    pipes = rec.pipes_from_recognition(r, layer="AGUA", zoom=1.0)
    con = [p for p in pipes if "cerca" in (p.get("diam_plano") or {})]
    assert len(con) == len([p for p in pipes if (p.get("diam_plano") or {}).get("estado") in ("dudoso", "sin_dato")])
    f = DI.ficha(con[0], "Agua")
    assert f["mapa"] and "mapa sin capas" in DI.texto_ficha(f)
