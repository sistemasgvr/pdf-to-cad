"""El chat como agente: mira el plano, se escribe su plan, señala y propone con evidencia. Nada se aplica sin el usuario."""
import base64
import json

import pytest

from ollama_falso import OllamaFalso
from test_diametro_ia_ventana import _esperar, _pipe, _ventana


# ── el bucle del agente (puro) ──
class _Cliente:
    instrucciones = ""

    def __init__(self):
        self.vistas = 0

    def herramientas(self):
        return [{"name": "ver", "description": "", "inputSchema": {}}]

    def llamar(self, nombre, args=None):
        from ia.civil3d_agente import ConImagen
        self.vistas += 1
        return True, ConImagen(f"vista {self.vistas}", [f"img{self.vistas}"])


def _llamada(funcion="ver", **args):
    return {"content": "", "tool_calls": [{"function": {"name": funcion, "arguments": args}}]}


def test_la_imagen_llega_al_modelo_y_solo_la_ultima():
    from ia.civil3d_agente import Agente
    vistos = []

    def pedir(msgs, _h):
        vistos.append([m.get("images") for m in msgs if m.get("images")])
        return _llamada() if len(vistos) < 3 else {"content": "Listo."}
    r = Agente(_Cliente(), pedir).preguntar("x")
    assert r.texto == "Listo." and vistos[1] == [["img1"]] and vistos[2] == [["img2"]]


def test_al_agotar_los_pasos_cierra_sin_herramientas():
    from ia.civil3d_agente import Agente
    tools = []

    def pedir(_m, h):
        tools.append(len(h))
        return _llamada() if h else {"content": "No hay certeza."}
    r = Agente(_Cliente(), pedir, max_pasos=3, cerrar=True).preguntar("x")
    assert r.texto == "No hay certeza." and tools == [1, 1, 1, 0]


def test_su_plan_entra_en_sus_propias_instrucciones():
    from ia.civil3d_agente import Agente
    from ia.herramientas import ClienteProyecto
    from test_copiloto_herramientas import datos
    sistemas = []

    def pedir(msgs, _h):
        sistemas.append(msgs[0]["content"])
        if len(sistemas) == 1:
            return _llamada("definir_plan", objetivo="Hallar el diámetro", pasos="Mirar el membrete", como_saber="Rótulo")
        return {"content": "Hecho."}
    Agente(ClienteProyecto(datos()), pedir, sistema="BASE").preguntar("x")
    assert "Mirar el membrete" not in sistemas[0] and "Mirar el membrete" in sistemas[1] and "BASE" in sistemas[1]


def test_lo_que_elige_el_usuario_entra_en_el_contexto():
    from ia.herramientas import ClienteProyecto
    from test_copiloto_herramientas import datos
    c = ClienteProyecto(datos(), seleccion="GAS-3")
    assert "GAS-3" in c.instrucciones


def test_senalame_esto_es_del_proyecto():
    from ia import alcance as A
    from test_copiloto_herramientas import datos
    assert A.revisar("señálame esto", datos()) == A.OK
    assert A.revisar("¿quién ganó el mundial?", datos()) == A.AJENO


# ── herramientas en la ventana ──
@pytest.fixture
def w():
    import fitz
    win = _ventana(pipes=[_pipe(), _pipe(200.0)])
    doc = fitz.open()
    pagina = doc.new_page(width=600, height=600)
    pagina.insert_text((60, 90), 'EX. 6" WATER', fontsize=9)
    win.doc, win.page_idx, win.zoom = doc, 0, 1.0
    return win


def _cliente(win):
    return win.agente_cliente(win._ia_datos(), lambda: False)


def test_ver_plano_devuelve_captura_y_texto(w):
    c = _cliente(w)
    ok, salida = c.llamar("ver_plano", {"codigo": "DRENAJE-1", "que_buscar": "rótulo", "margen_pt": 60})
    assert ok and base64.b64decode(salida.imagenes[0])[:4] == b"\x89PNG"
    assert 'EX. 6" WATER' in salida and w.pipes[0]["diam"] == 12.0 and not w._undo


def test_repetir_la_misma_vista_no_da_otra_captura(w):
    c = _cliente(w)
    args = {"codigo": "DRENAJE-1", "que_buscar": "x", "margen_pt": 60}
    c.llamar("ver_plano", args)
    ok, salida = c.llamar("ver_plano", args)
    assert not getattr(salida, "imagenes", None) and "ya" in salida.lower()


def test_ver_plano_sin_pdf_lo_dice(w):
    w.doc = None
    ok, salida = _cliente(w).llamar("ver_plano", {"codigo": "DRENAJE-1", "que_buscar": "x"})
    assert not ok and salida


def test_codigo_que_no_existe(w):
    assert _cliente(w).llamar("ver_plano", {"codigo": "NADA-9", "que_buscar": "x"})[0] is False


def test_senalar_marca_en_el_plano_sin_cambiar_el_proyecto(w):
    c = _cliente(w)
    ok, _s = c.llamar("senalar", {"codigos": ["DRENAJE-1", "DRENAJE-2"]})
    assert ok and len(w._agente_marcas().items) == 4 and not w._undo
    c.llamar("quitar_senales", {})
    assert not w._agente_marcas().items


def test_senalar_lo_que_no_existe_lo_dice(w):
    ok, s = _cliente(w).llamar("senalar", {"codigos": ["NADA-1"]})
    assert not ok and "NADA-1" in s


def test_buscar_funcion_encuentra_funciones_de_la_app(w):
    ok, s = _cliente(w).llamar("buscar_funcion", {"texto": "vista 3d"})
    assert ok and "3D" in s


def test_funcion_de_ver_se_usa_y_las_demas_piden_confirmacion(w):
    c = _cliente(w)
    antes = w.act_show_acc.isChecked()
    ok, _s = c.llamar("usar_funcion", {"nombre": w.act_show_acc.text()})
    assert ok and w.act_show_acc.isChecked() != antes and not c.propuestas
    ok, s = c.llamar("usar_funcion", {"nombre": "Revisar y limpiar el dibujo…"})
    assert ok and c.propuestas[-1]["tipo"] == "funcion"


def test_proponer_diametro_exige_haber_mirado(w):
    c = _cliente(w)
    ok, _s = c.llamar("proponer_diametro", {"codigo": "DRENAJE-1", "pulgadas": 6, "evidencia": 'EX. 6" WATER'})
    assert not ok and not c.propuestas


def test_proponer_diametro_leido_en_el_texto(w):
    c = _cliente(w)
    c.llamar("ver_plano", {"codigo": "DRENAJE-1", "que_buscar": "x", "margen_pt": 60})
    ok, _s = c.llamar("proponer_diametro", {"codigo": "DRENAJE-1", "pulgadas": 6, "evidencia": 'EX. 6" WATER'})
    assert ok and c.propuestas[-1]["leido"] and w.pipes[0]["diam"] == 12.0 and not w._undo


def test_valor_que_no_esta_en_el_texto_queda_como_lectura_visual(w):
    c = _cliente(w)
    c.llamar("ver_plano", {"codigo": "DRENAJE-1", "que_buscar": "x", "margen_pt": 60})
    c.llamar("proponer_diametro", {"codigo": "DRENAJE-1", "pulgadas": 8, "evidencia": "lo vi"})
    assert not c.propuestas[-1]["leido"]


@pytest.mark.parametrize("accion", ["borrar_utilidades", "mover_utilidad", "inventada"])
def test_no_puede_proponer_borrar_ni_mover(w, accion):
    c = _cliente(w)
    assert c.llamar("proponer_accion", {"accion": accion, "parametros": {"utilidades": ["DRENAJE-1"]}})[0] is False
    assert not c.propuestas


def test_proponer_accion_queda_para_confirmar(w):
    c = _cliente(w)
    ok, _s = c.llamar("proponer_accion", {"accion": "cambiar_material", "parametros": {"utilidades": ["DRENAJE-1"],
                                                                                      "material": "PVC"}})
    assert ok and c.propuestas[-1]["tipo"] == "orden" and not w._undo


# ── en el chat ──
def _chat_con(respuestas, doc_de=None):
    """Ollama simulado con `tools`: responde la lista `respuestas` en orden (dicts de mensaje o texto)."""
    r = list(respuestas)

    def responder(_c):
        x = r.pop(0) if r else "Listo."
        return x
    return OllamaFalso(responder, modelos=("qwen3.8:latest",), capacidades=("completion", "tools", "vision"))


def _agente_falso(win, monkeypatch, pasos):
    from ia import civil3d_agente
    r = list(pasos)
    monkeypatch.setattr(civil3d_agente, "pedir_ollama", lambda _c: (lambda _m, _h: r.pop(0) if r else {"content": "Listo."}))


def _preguntar(win, srv, texto):
    from ui.dialogos.ia_chat import PreguntaDialog
    d = PreguntaDialog(win)
    win._config_ia = lambda: {"proveedor": "ollama", "url": srv.url, "modelo": "qwen3.8:latest"}
    d.enviar(texto)
    _esperar(win, lambda: d._activo is None and d.turnos[0]["estado"] != "escribiendo", s=20)
    return d


def test_propuesta_del_agente_sale_como_tarjeta_y_se_aprueba(w, monkeypatch):
    _agente_falso(w, monkeypatch, [_llamada("ver_plano", codigo="DRENAJE-1", que_buscar="rótulo", margen_pt=60),
                                   _llamada("proponer_diametro", codigo="DRENAJE-1", pulgadas=6, evidencia='EX. 6" WATER'),
                                   {"content": "Te propongo 6."}])
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "revisa el diámetro de DRENAJE-1")
        cop = next(t["cop"] for t in d.turnos if (t.get("cop") or {}).get("tipo") == "linea")
        assert cop["estado"] == "confirmar" and cop["sug"].diam_in == 6 and not w._undo
        assert d.turnos[0]["res"].pasos and "cap:" in d.vista.toHtml()
        t = next(k for k, x in enumerate(d.turnos) if x.get("cop") is cop)
        d._enlace_copiloto(f"aprobar:{t}")
        assert w.pipes[0]["diam"] == 6.0 and w.bitacora[-1]["tipo"] == "decision"


def test_dos_propuestas_aprobar_una_no_caduca_la_otra(w, monkeypatch):
    _agente_falso(w, monkeypatch, [_llamada("ver_plano", codigo="DRENAJE-1", que_buscar="r", margen_pt=60),
                                   _llamada("proponer_diametro", codigo="DRENAJE-1", pulgadas=6, evidencia="a"),
                                   _llamada("ver_plano", codigo="DRENAJE-2", que_buscar="r", margen_pt=60),
                                   _llamada("proponer_diametro", codigo="DRENAJE-2", pulgadas=8, evidencia="b")])
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "revisa DRENAJE-1 y DRENAJE-2")
        ks = [k for k, x in enumerate(d.turnos) if (x.get("cop") or {}).get("tipo") == "linea"]
        assert len(ks) == 2
        d._enlace_copiloto(f"aprobar:{ks[0]}")
        d._enlace_copiloto(f"aprobar:{ks[1]}")
        assert [p["diam"] for p in w.pipes] == [6.0, 8.0]


def test_propuesta_de_accion_usa_la_confirmacion_de_siempre(w, monkeypatch):
    _agente_falso(w, monkeypatch, [_llamada("proponer_accion", accion="cambiar_material",
                                            parametros={"utilidades": ["DRENAJE-1"], "material": "PVC"})])
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "revisa el material de DRENAJE-1")
        k = next(k for k, x in enumerate(d.turnos) if x.get("orden"))
        assert w.pipes[0].get("material") != "PVC"
        d._confirmar_orden(k, True)
        assert w.pipes[0]["material"] == "PVC"


def test_funcion_que_pide_confirmacion(w, monkeypatch):
    llamadas = []
    monkeypatch.setattr(w, "revisar_dibujo", lambda *a, **k: llamadas.append(1))
    _agente_falso(w, monkeypatch, [_llamada("usar_funcion", nombre="Revisar y limpiar el dibujo…")])
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "revisa el dibujo de las líneas")
        k = next(k for k, x in enumerate(d.turnos) if (x.get("cop") or {}).get("tipo") == "funcion")
        d._enlace_copiloto(f"funno:{k}")
        assert d.turnos[k]["cop"]["estado"] == "cancelado" and not llamadas and not w._undo


def test_investigar_recorre_las_pendientes_y_detener_corta(w, monkeypatch):
    _agente_falso(w, monkeypatch, [{"content": "No hay certeza."}, {"content": "No hay certeza."}])
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "¿qué líneas de drenaje hay?")
        d._cop_inv = []
        d._cop_investigar_lista(["DRENAJE-1", "DRENAJE-2"])
        _esperar(w, lambda: not d._cop_inv and d._activo is None, s=20)
        assert sum("DRENAJE" in t["pregunta"] for t in d.turnos) == 2
        d._cop_investigar_lista(["DRENAJE-1", "DRENAJE-2"])
        d.enviar("x")                                  # «Detener»
        assert not d._cop_inv


def test_lo_que_lee_el_pdf_corre_en_el_hilo_de_la_ventana(w, monkeypatch):
    import threading
    hilos = []
    real = w.agente_captura
    monkeypatch.setattr(w, "agente_captura", lambda i, m: (hilos.append(threading.current_thread()), real(i, m))[1])
    _agente_falso(w, monkeypatch, [_llamada("ver_plano", codigo="DRENAJE-1", que_buscar="r", margen_pt=60)])
    with _chat_con([]) as srv:
        _preguntar(w, srv, "revisa el diámetro de DRENAJE-1")
    assert hilos == [threading.main_thread()]


def test_pedido_de_ver_que_no_esta_en_el_catalogo_llega_al_agente(w, monkeypatch):
    from ia import acciones as AC
    monkeypatch.setattr(AC, "interpretar", lambda *a, **k: {"accion": None, "pregunta": "¿Qué abro?"})
    _agente_falso(w, monkeypatch, [_llamada("buscar_funcion", texto="avisos"), {"content": "Encontré la función."}])
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "abre lo de los avisos de normativa")
        _esperar(w, lambda: d.turnos[0]["res"] is not None, s=20)
        assert "Encontré" in d.turnos[0]["texto"] and d._orden_pendiente is None


def test_orden_a_la_que_le_falta_un_dato_sigue_preguntando(w, monkeypatch):
    from ia import acciones as AC
    monkeypatch.setattr(AC, "interpretar", lambda *a, **k: {"accion": None, "pregunta": "¿Cuántos pies?"})
    with _chat_con([]) as srv:
        d = _preguntar(w, srv, "baja DRENAJE-1")
        assert "pies" in d.turnos[0]["texto"] and d._orden_pendiente
