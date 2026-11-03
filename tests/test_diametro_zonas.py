"""La IA del diámetro elige qué zona del plano mirar cuando duda (pedido 2026-11-03): lados, membrete, leyenda y notas,
con la captura y el texto de esa zona; igual con capas, en los mapas y en los PDF sin capas."""
import json
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT), str(ROOT / "tests")]

from hoja import zonas_diametro as ZD  # noqa: E402
from ia import diametro_ia as DI  # noqa: E402
from ia import diametro_ia_replica as DR  # noqa: E402
from ia import diametro_zonas as DZ  # noqa: E402
from ia import proveedor as PV  # noqa: E402
from ollama_falso import OllamaFalso  # noqa: E402


def _ficha():
    return dict(utilidad="GAS", utilidad_nombre="Gas", nombre="GAS-3", capa="", sistema="", estado_capa="",
                abandonada=False, largo_ft=40.0, por_defecto_in=12.0, estado_plano="sin_dato", paredes_in=None, perfil_in=[],
                rotulos=[], normativa=[], mapa=False, acometida=False, vecinas=[], tramo=[])


class Explorador:
    """Dos zonas: las notas con un diámetro de gas y el membrete sin ninguno."""

    def __init__(self, opciones=None):
        self.vistas = []
        self.opciones = opciones if opciones is not None else [dict(diam_in=2.0, texto='ALL GAS MAINS 2" STL', normativa=True)]

    def menu(self):
        return [dict(id="notas", titulo="las notas", documento="a.pdf", pagina=3, adelanto="ALL GAS MAINS", diametros=[2.0]),
                dict(id="membrete", titulo="el membrete", documento="a.pdf", pagina=1, adelanto="SHEET 1", diametros=[])]

    def ver(self, zona):
        self.vistas.append(zona["id"])
        return dict(texto="ALL GAS MAINS 2 in", opciones=self.opciones if zona["id"] == "notas" else [], captura=None)


def _guion(*respuestas):
    cola = list(respuestas)
    return lambda _c: json.dumps(cola.pop(0)) if cola else "{}"


def _revisar(explorador, *respuestas, s=None):
    s = s or DI.Sugerencia(None, None, "baja", "no encontré", "", "ia")
    with OllamaFalso(_guion(*respuestas)) as falso:
        prov = PV.crear({"proveedor": "ollama", "url": falso.url, "modelo": "qwen3-vl:8b"})
        return DZ.revisar(prov, _ficha(), s, explorador), falso.pedidos


def test_elige_la_zona_y_halla_el_diametro():
    ex = Explorador()
    s, pedidos = _revisar(ex, {"zona": "notas", "motivo": "una nota general lo diría"},
                          {"eleccion": "Z1", "confianza": "alta", "motivo": "la nota dice que vale para el gas"})
    assert ex.vistas == ["notas"] and (s.diam_in, s.origen) == (2.0, "zona")
    assert s.zonas[0]["id"] == "notas" and s.zonas[0]["motivo"].startswith("una nota")
    assert "ALL GAS MAINS" in pedidos[0]["messages"][-1]["content"]              # eligió con el adelanto a la vista


def test_si_no_halla_sigue_con_otra_zona_y_no_inventa():
    ex = Explorador()
    s, _ = _revisar(ex, {"zona": "membrete", "motivo": "a"}, {"zona": "notas", "motivo": "b"},
                    {"eleccion": None, "confianza": "media", "motivo": "no vale"})
    assert ex.vistas == ["membrete", "notas"] and s.diam_in is None
    assert "el membrete" in s.motivo and "las notas" in s.motivo


def test_ella_puede_decidir_no_mirar():
    ex = Explorador()
    s, pedidos = _revisar(ex, {"zona": None, "motivo": "nada promete"})
    assert ex.vistas == [] and len(pedidos) == 1 and s.motivo == "no encontré"


def test_zona_que_no_existe_no_se_mira():
    ex = Explorador()
    s, _ = _revisar(ex, {"zona": "cocina", "motivo": "?"})
    assert ex.vistas == [] and s.diam_in is None


def test_un_diametro_de_otra_utilidad_ni_se_ofrece():
    ex = Explorador([dict(diam_in=8.0, texto='8" WATER MAIN', normativa=True)])
    s, pedidos = _revisar(ex, {"zona": "notas", "motivo": "a"}, {"zona": "membrete", "motivo": "b"})
    assert s.diam_in is None and len(pedidos) == 2                               # sin opciones no hay qué decidir


def test_confianza_baja_o_cifra_inventada():
    s, _ = _revisar(Explorador(), {"zona": "notas", "motivo": "a"}, {"eleccion": "Z1", "confianza": "baja", "motivo": "x"})
    assert s.diam_in is None
    s, _ = _revisar(Explorador(), {"zona": "notas", "motivo": "a"},
                    {"eleccion": "Z1", "confianza": "alta", "motivo": 'la nota dice 99"'})
    assert s.diam_in == 2.0 and "99" not in s.motivo and "ALL GAS MAINS" in s.motivo


def test_necesita():
    assert DZ.necesita(DI.Sugerencia(None, None, "baja", "", "", "ia"))
    assert DZ.necesita(DI.Sugerencia(8.0, None, "media", "", "", "normativa"))
    assert not DZ.necesita(DI.Sugerencia(8.0, "R1", "alta", "", "", "ia"))
    assert not DZ.necesita(DI.Sugerencia(8.0, None, "alta", "", "", "continuidad"))
    assert not DZ.necesita(DI.Sugerencia(None, None, "baja", "", "", "ia", zonas=[{"id": "notas"}]))


def test_el_usuario_pide_una_zona_en_el_chat():
    assert DZ.zona_pedida("revisa el membrete") == "membrete"
    assert DZ.zona_pedida("mira arriba de la línea") == "arriba"
    assert DZ.zona_pedida("la principal está a la izquierda") is None
    ex = Explorador()
    with OllamaFalso(_guion({"eleccion": "Z1", "confianza": "alta", "motivo": "ahí está"})) as falso:
        prov = PV.crear({"proveedor": "ollama", "url": falso.url, "modelo": "qwen3-vl:8b"})
        s = DR.replicar(prov, _ficha(), None, [], "busca en las notas", explorador=ex)
    assert ex.vistas == ["notas"] and s.diam_in == 2.0


def test_en_el_chat_ella_pide_ver_una_zona():
    ex = Explorador()
    with OllamaFalso(_guion({"respuesta": "voy a mirar", "eleccion": None, "confianza": "media", "ver": "notas"},
                            {"eleccion": "Z1", "confianza": "media", "motivo": "ahí está"})) as falso:
        prov = PV.crear({"proveedor": "ollama", "url": falso.url, "modelo": "qwen3-vl:8b"})
        s = DR.replicar(prov, _ficha(), None, [], "no me convence", explorador=ex)
    assert s.diam_in == 2.0 and "Zonas que puedes pedir" in falso.pedidos[0]["messages"][-1]["content"]


def test_diametros_del_texto_de_una_zona():
    assert ZD.diametros('ALL SERVICES 3/4" STL, MAINS 1-1/4" OR 2"') == [0.75, 1.25, 2.0]
    assert ZD.diametros("SCALE: 1\" = 100'") == []
    assert ZD.diametros('2-4" CONDUIT') == []


def _plano(tmp_path, girada=False):
    doc = fitz.open()
    pg = doc.new_page(width=1000, height=800)
    pg.insert_text((400, 300), 'TEXTO DEL LADO 6" GAS', fontsize=8)
    pg.insert_text((60, 60), "LEGEND", fontsize=9)
    pg.insert_text((60, 80), 'G = 2" GAS MAIN', fontsize=8)
    pg.insert_text((700, 60), "GENERAL NOTES", fontsize=9)
    pg.insert_text((700, 80), 'ALL SERVICES 3/4" STL', fontsize=8)
    pg.insert_text((100, 770), "SHEET 3 OF 9   DRAWN BY X   PROJECT 5", fontsize=8)
    if girada:
        pg.set_rotation(90)
    ruta = tmp_path / "p.pdf"
    doc.save(ruta)
    return str(ruta)


def _menu(ruta, lineas):
    fuentes = [{"name": "p.pdf", "data": Path(ruta).read_bytes()}]
    plan = dict(fuente=0, pagina=0, documento="p.pdf", zona="hoja completa", region=[0, 0, 1000, 800], lineas=[lineas])
    return fuentes, {z["id"]: z for z in ZD.menu(fuentes, [plan])}


def test_menu_de_una_hoja_con_todo(tmp_path):
    fuentes, zonas = _menu(_plano(tmp_path), [(100, 300), (300, 300)])
    assert {"derecha", "membrete", "leyenda", "notas"} <= set(zonas)
    assert "SHEET" in zonas["membrete"]["adelanto"] and 0.75 in zonas["notas"]["diametros"]
    assert 6.0 in zonas["derecha"]["diametros"]
    visto = ZD.leer(fuentes, zonas["notas"])
    assert visto["opciones"][0]["diam_in"] == 0.75 and visto["captura"]["sha256_png"]


def test_una_zona_sin_texto_solo_vale_con_vision(tmp_path):
    ruta = _plano(tmp_path)
    fuentes = [{"name": "p.pdf", "data": Path(ruta).read_bytes()}]
    plan = dict(fuente=0, pagina=0, documento="p.pdf", region=[0, 0, 1000, 800], lineas=[[(600, 500), (700, 500)]])
    sin = {z["id"] for z in ZD.menu(fuentes, [plan])}
    con = {z["id"] for z in ZD.menu(fuentes, [plan], con_imagen=True)}
    assert "abajo" not in sin and "abajo" in con


def test_hoja_girada_y_sin_linea(tmp_path):
    _f, zonas = _menu(_plano(tmp_path, girada=True), [(100, 300), (300, 300)])
    assert "membrete" in zonas
    assert ZD.menu([], [dict(fuente=0, pagina=0, lineas=[])]) == []


def test_ventana_mira_una_zona_y_la_deja_en_el_analisis(tmp_path):
    """Punta a punta: sin rótulos, la IA pide las notas, la hoja se lee en la ventana y queda la propuesta."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from test_diametro_ia_ventana import _elegir, _esperar, _pipe, _ventana
    ruta = _plano(tmp_path)
    p = _pipe()
    p["layer"], p["pts"], p["diam_plano"]["cerca"] = "GAS", [(100.0, 300.0), (300.0, 300.0)], []
    guion = [{"zona": "notas", "motivo": "una nota general lo diría"},
             {"eleccion": "Z1", "confianza": "alta", "motivo": "vale para todos los servicios"}]

    def responder(c):
        sistema = (c.get("messages") or [{}])[0].get("content", "")
        if "elige UNA zona" in sistema or "Elige una Z" in sistema:
            return json.dumps(guion.pop(0))
        return json.dumps({"rotulo": None, "confianza": "media", "motivo": "no hay rótulos", "pista": None,
                           "opcion": None, "evidencias": []})
    with OllamaFalso(responder) as srv:
        w = _ventana(srv, [p])
        w.doc = fitz.open(ruta)
        w.src_pdfs = [{"name": "p.pdf", "data": Path(ruta).read_bytes()}]
        w.page_idx = 0
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        assert _esperar(w, lambda: w._diam_ia_pedido is None and (w._diam_ia_sug(0) or None) is not None, 20)
        s = w._diam_ia_sug(0)
        assert s.origen == "zona" and s.diam_in == 0.75 and s.zonas[0]["id"] == "notas"
        w._diam_ia_refrescar()
        assert "Propuesta" in w.lbl_diam_ia.text() and "las notas" in w.lbl_diam_ia.text()
        assert s.analisis["capturas_originales"]                        # su captura, en «Ver análisis»
        assert w._diam_ia_mi.vigentes()                                 # y marcada en el plano
