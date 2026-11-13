"""Texto del plano en el proyecto y para la IA (pedido 2026-11-13: «que se capture toda la información de cada plano
—calles, todo lo que haya— y que la IA sepa responder», sin mandarle todo: busca lo que viene al caso)."""
import json
import os

import fitz
import pytest

from hoja import indice_texto as IT
from ia import alcance as A, consulta, herramientas as H
from ia.contexto import DatosProyecto


def _hoja():
    doc = fitz.open()
    pg = doc.new_page(width=800, height=600)
    pg.insert_text((100, 100), "THOMAS RD", fontsize=10)
    pg.insert_text((100, 300), "91ST AVE", fontsize=10)
    # rótulo de servicio escrito en tres trozos (ArcGIS escribe cada palabra aparte)
    pg.insert_text((400, 200), '1/2"', fontsize=8)
    pg.insert_text((420, 200), "PE", fontsize=8)
    pg.insert_text((434, 200), "'04", fontsize=8)
    pg.insert_text((600, 500), "0204519918", fontsize=7)
    pg.insert_text((600, 550), "PUEBLO DEL SOL MIDDLE SCHOOL", fontsize=7)
    pg.insert_text((50, 550), "NOTE: PROTECT EXISTING GAS MAIN", fontsize=7)
    return fitz.open(stream=doc.tobytes(), filetype="pdf")


def test_lee_todo_el_texto_con_su_tipo_y_junta_los_trozos():
    ix = IT.leer(_hoja()[0], zoom=2.0, origen="plano · Hoja 1")
    por = {l[0]: l for l in ix["lineas"]}
    assert por["THOMAS RD"][3] == "calle" and por["91ST AVE"][3] == "calle"
    assert '1/2" PE \'04' in por and por['1/2" PE \'04'][3] == "tuberia"          # un solo rótulo
    assert por["0204519918"][3] == "servicio"
    assert por["PUEBLO DEL SOL MIDDLE SCHOOL"][3] == "lugar"
    assert por["NOTE: PROTECT EXISTING GAS MAIN"][3] == "nota"
    x, y = por["THOMAS RD"][1:3]
    assert 200 < x < 300 and 180 < y < 200                                           # px del lienzo (zoom 2)
    assert ix["hojas"] == ["plano · Hoja 1"]


def test_hoja_compuesta_solo_lo_que_se_ve_y_su_hoja():
    piezas = [((0, 0, 300, 600), "A · 14-6"), ((300, 0, 800, 600), "A · 14-7")]
    ix = IT.leer(_hoja()[0], 1.0, piezas)
    assert ix["hojas"] == ["A · 14-6", "A · 14-7"]
    por = {l[0]: l for l in ix["lineas"]}
    assert por["THOMAS RD"][4] == 0 and por["0204519918"][4] == 1
    solo = IT.leer(_hoja()[0], 1.0, [((0, 0, 300, 600), "A")])               # lo de fuera no se ve
    assert "0204519918" not in {l[0] for l in solo["lineas"]}


def _datos():
    tp = IT.leer(_hoja()[0], 1.0, None, "plano · Hoja 1")
    pipes = [{"layer": "GAS", "pts": [(90.0, 120.0), (300.0, 120.0)], "diam": 2.0}]
    return DatosProyecto.armar(pipes, [], 0.1, "P", texto_plano=tp, zoom=1.0)


def test_la_ia_recibe_solo_lo_que_viene_al_caso():
    datos = _datos()
    assert "THOMAS RD" in datos.resumen and "calles distintas" in datos.resumen
    assert A.revisar("¿Dónde está Thomas Rd?", datos) == A.OK
    assert A.revisar("¿Dónde está el servicio 0204519918?", datos) == A.OK
    assert A.revisar("¿Cuál es la capital de Francia?", datos) == A.AJENO
    pedido, _ = consulta.armar_pedido("¿Dónde está Thomas Rd?", datos)
    seccion = pedido[pedido.index("Texto del plano que viene al caso"):pedido.index("## Pregunta")]
    assert "THOMAS RD" in seccion and "cerca de GAS-1" in seccion
    assert "0204519918" not in seccion and "SCHOOL" not in seccion                   # no va todo
    codigo = seccion.split("\n")[1].split(" | ")[0]
    assert codigo.startswith("TX-") and datos.ref(codigo) is not None                # lleva al lugar


def test_herramientas_buscar_texto_y_calles():
    c = H.ClienteProyecto(_datos())
    assert {"buscar_texto", "listar_calles"} <= {h["name"] for h in c.herramientas()}
    ok, salida = c.llamar("buscar_texto", {"texto": "school"})
    assert ok and "PUEBLO DEL SOL MIDDLE SCHOOL" in salida and "lugar" in salida
    ok, salida = c.llamar("listar_calles", {})
    assert "THOMAS RD" in salida and "91ST AVE" in salida
    ok, salida = c.llamar("buscar_texto", {"texto": "NO EXISTE"})
    assert "no dice" in salida


from tests.test_respaldo_editor import _editor_con_lineas, HOJA, app, win  # noqa: E402,F401  (ventana de prueba)


def test_ventana_lo_arma_lo_guarda_y_lo_reabre(win, app, tmp_path):
    _editor_con_lineas(win, tmp_path, HOJA)                   # hoja 2 del PDF en el editor
    app.processEvents()
    tp = win.texto_plano
    assert tp and tp["clave"] == win._texto_plano_clave()
    assert "plano hoja 2" in {l[0] for l in tp["lineas"]}
    datos = win._ia_datos()
    assert datos.texto is not None and len(datos.texto) == len(tp["lineas"])
    ruta = str(tmp_path / "p.digproj")
    win._write_project(ruta)
    import zipfile
    assert "texto_plano.json" in zipfile.ZipFile(ruta).namelist()
    assert "texto_plano" not in json.loads(zipfile.ZipFile(ruta).read("model.json"))   # aparte del modelo
    win.texto_plano = None
    win._dirty = False
    win._open_project_path(ruta)
    assert win.texto_plano and win.texto_plano["lineas"] == tp["lineas"]
    app.processEvents()
    assert win.texto_plano["clave"] == tp["clave"]            # misma hoja: no se rearmó


SW = os.path.join(os.path.expanduser("~"), "Downloads", "Southwest Gas Combined 811 Records.pdf")


@pytest.mark.skipif(not os.path.exists(SW), reason="sin el PDF de Southwest Gas")
def test_southwest_calles_y_servicios():
    tp = IT.leer(fitz.open(SW)[0], 1.0, None, "SW")
    tipos = IT.resumen(tp)["tipos"]
    assert tipos.get("calle", 0) >= 20 and tipos.get("servicio", 0) >= 30 and tipos.get("tuberia", 0) >= 100
    assert "THOMAS RD" in IT.resumen(tp)["calles"]
