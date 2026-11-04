"""Entrada 1 del MCP de Civil 3D: agente con un modelo y un cliente FALSOS, y el handshake con el
PdfCadMcp.exe real (si está compilado; sin Civil 3D las herramientas responden «sin conexión»)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from ia import civil3d_agente as A  # noqa: E402
from ia import civil3d_mcp as M  # noqa: E402

TOOLS = [{"name": n, "description": n, "inputSchema": {"type": "object", "properties": {}}}
         for n in ("estado", "resumen_modelo", "proponer_cambio", "confirmar_cambio", "cancelar_cambio")]


class ClienteFalso:
    instrucciones = "Reglas del host."

    def __init__(self):
        self.llamadas = []

    def herramientas(self):
        return TOOLS

    def llamar(self, nombre, args=None):
        self.llamadas.append((nombre, args))
        if nombre == "resumen_modelo":
            return True, json.dumps({"redes": [{"red": "SEWER", "tuberias": 3}]})
        if nombre == "proponer_cambio":
            return True, json.dumps({"id": "C1", "antes": "100.00", "despues": "100.50", "advertencias": []})
        if nombre == "confirmar_cambio":
            return True, json.dumps({"aplicado": True})
        return True, "x" * 10000


def modelo_guionado(pasos):
    """Devuelve los mensajes en orden; guarda lo que recibió en cada paso."""
    vistos = []

    def pedir(mensajes, herramientas):
        vistos.append((list(mensajes), herramientas))
        return pasos[len(vistos) - 1]
    return pedir, vistos


def llamada(nombre, args=None):
    return {"content": "", "tool_calls": [{"function": {"name": nombre, "arguments": args or {}}}]}


def test_el_modelo_no_ve_las_herramientas_del_usuario():
    tools = A.herramientas_ollama(TOOLS)
    nombres = {x["function"]["name"] for x in tools}
    assert nombres == {"estado", "resumen_modelo", "proponer_cambio"}


def test_pregunta_con_herramienta_y_respuesta():
    c = ClienteFalso()
    pedir, vistos = modelo_guionado([llamada("resumen_modelo"), {"content": "<think>…</think>Hay 3 tuberías."}])
    r = A.Agente(c, pedir).preguntar("¿cuántas tuberías?")
    assert r.texto == "Hay 3 tuberías."
    assert r.llamadas == [("resumen_modelo", True)]
    assert vistos[1][0][-1]["role"] == "tool"                  # el resultado vuelve al modelo
    assert "Reglas del host." in vistos[0][0][0]["content"]     # instrucciones del host en el sistema


def test_propuesta_vuelve_a_la_ventana_y_el_modelo_no_puede_confirmar():
    c = ClienteFalso()
    pedir, _ = modelo_guionado([llamada("proponer_cambio", {"handle": "A1"}), llamada("confirmar_cambio", {"id": "C1"}),
                                {"content": "¿Lo aplico?"}])
    ag = A.Agente(c, pedir)
    r = ag.preguntar("sube la cota")
    assert [p["id"] for p in r.propuestas] == ["C1"]
    assert ("confirmar_cambio", False) in r.llamadas
    assert all(n != "confirmar_cambio" for n, _ in c.llamadas)   # nunca llegó al plugin
    ok, _ = ag.confirmar("C1")                                    # el botón del usuario sí
    assert ok and c.llamadas[-1] == ("confirmar_cambio", {"id": "C1"})


def test_tope_de_pasos_y_resultados_recortados():
    c = ClienteFalso()
    pedir, vistos = modelo_guionado([llamada("estado")] * 3)
    r = A.Agente(c, pedir, max_pasos=3).preguntar("bucle")
    assert "3" in r.texto
    assert len(vistos[1][0][-1]["content"]) < A.MAX_RESULTADO + 100


def test_historial_sin_trafico_de_herramientas():
    c = ClienteFalso()
    pedir, vistos = modelo_guionado([llamada("estado"), {"content": "uno"}, {"content": "dos"}])
    ag = A.Agente(c, pedir)
    ag.preguntar("a")
    ag.preguntar("b")
    roles = [m["role"] for m in vistos[2][0]]
    assert roles == ["system", "user", "assistant", "user"]


def test_sin_conexion_con_civil3d_lo_dice():
    class SinCivil(ClienteFalso):
        def llamar(self, nombre, args=None):
            return False, "Civil 3D no está conectado. … (o comando PDFCAD_IA)."
    pedir, _ = modelo_guionado([llamada("estado")])
    r = A.Agente(SinCivil(), pedir).preguntar("hola")
    assert r.sin_conexion and "PDFCAD_IA" in r.texto


@pytest.mark.skipif(not M.ruta_exe(), reason="PdfCadMcp.exe sin compilar")
def test_handshake_con_el_host_real():
    with M.ClienteMCP(perfil=M.PERFIL_BASICO) as c:
        nombres = {h["name"] for h in c.herramientas()}
        assert "resumen_modelo" in nombres and "historial" not in nombres   # perfil básico
        assert "pies" in c.instrucciones
        ok, texto = c.llamar("estado")
        if not ok:                     # sin Civil 3D con la IA encendida: dice cómo encenderla
            assert "PDFCAD_IA" in texto
