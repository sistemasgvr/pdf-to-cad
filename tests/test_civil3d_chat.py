"""Pestaña «Civil 3D» del Asistente: conectar, preguntar, propuesta → «Aplicar» del usuario (cliente MCP y modelo
FALSOS: sin Civil 3D ni Ollama)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

PROPUESTA = {"id": "C1", "handle": "2A4F", "elemento": "SEWER - (3)", "tipo": "cota_fin", "antes": "98.20",
             "despues": "97.80", "consecuencias": ["Pendiente 0.10 % → 0.50 %."],
             "advertencias": ["Queda 0.30 ft bajo el fondo (sump) de MH-12."]}


class Cli:
    instrucciones = ""

    def __init__(self, conectado=True):
        self.conectado, self.llamadas = conectado, []

    def herramientas(self):
        return [{"name": "resumen_modelo"}, {"name": "proponer_cambio"}, {"name": "confirmar_cambio"}]

    def llamar(self, n, a=None):
        self.llamadas.append(n)
        if not self.conectado:
            return False, "Civil 3D no está conectado. … (o comando PDFCAD_IA)."
        if n == "estado":
            return True, json.dumps({"dibujo": "base_map.dwg", "redes_gravedad": 2, "redes_presion": 1})
        if n == "proponer_cambio":
            return True, json.dumps(PROPUESTA)
        if n == "confirmar_cambio":
            return True, json.dumps({"aplicado": True})
        return True, json.dumps({"redes": [{"red": "SEWER", "tuberias": 12}]})

    def cerrar(self):
        pass


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _esperar(app, cond, s=5):
    t0 = time.time()
    while not cond() and time.time() - t0 < s:
        app.processEvents()
    return cond()


def _chat(monkeypatch, cli, pasos):
    from ia import civil3d_agente as A
    from ui.dialogos import ia_civil3d as C

    class Win(QtWidgets.QWidget):
        def _config_ia(self):
            return {"proveedor": "ollama", "url": "http://x", "modelo": "qwen"}

        def configurar_ia(self):
            pass

    monkeypatch.setattr(C.ChatCivil3D, "_cliente_vivo",
                        lambda self, nuevo=False: setattr(self, "_cliente", cli) or cli)
    monkeypatch.setattr(A, "pedir_ollama", lambda cfg: (lambda m, t: pasos.pop(0)))
    return C.ChatCivil3D(Win())


def _llamada(n):
    return {"content": "", "tool_calls": [{"function": {"name": n, "arguments": {}}}]}


def test_propuesta_y_aplicar_solo_con_el_boton(qapp, monkeypatch):
    cli = Cli()
    ch = _chat(monkeypatch, cli, [_llamada("proponer_cambio"), _llamada("confirmar_cambio"),
                                  {"content": "¿Lo aplico?"}])
    ch.reconectar()
    assert _esperar(qapp, lambda: isinstance(ch._civil, dict))
    assert "base_map.dwg" in ch.lbl_estado.text() and "3" in ch.lbl_estado.text()
    assert ch.aviso.isHidden()
    ch.enviar("baja la rasante")
    assert _esperar(qapp, lambda: ch._activo is None)
    tu = ch.turnos[0]
    assert tu["texto"] == "¿Lo aplico?" and tu["propuestas"][0]["estado"] == "pendiente"
    assert "confirmar_cambio" not in cli.llamadas                  # el modelo no pudo
    assert "aplicar:0.0" in ch.vista.toHtml() or "Aplicar" in ch.vista.toPlainText()
    ch._decidir("0.0", True)
    assert _esperar(qapp, lambda: tu["propuestas"][0]["estado"] == "aplicado")
    assert cli.llamadas.count("confirmar_cambio") == 1


def test_sin_civil3d_avisa_como_encenderlo(qapp, monkeypatch):
    ch = _chat(monkeypatch, Cli(conectado=False), [])
    ch.reconectar()
    assert _esperar(qapp, lambda: ch._civil is not None)
    assert not ch.aviso.isHidden() and "PDFCAD_IA" in ch.aviso.text()
    assert "sin conectar" in ch.lbl_estado.text()


def test_responder_si_no_o_corregir_una_propuesta(qapp, monkeypatch):
    """Reporte 2026-11-10: «sí, aplícalo» la aplica la app (como el botón); «no, cámbialo a -10» descarta la vieja y
    el modelo tiene que proponer la nueva; «no» la descarta."""
    cli = Cli()
    pasos = [_llamada("proponer_cambio"), {"content": "Propuse -20."},
             _llamada("proponer_cambio"), {"content": "Propuse -10."},
             _llamada("proponer_cambio"), {"content": "Propuse otra."}]
    ch = _chat(monkeypatch, cli, pasos)
    ch.enviar("cambia la cota a -20")
    assert _esperar(qapp, lambda: ch._activo is None)
    ch.enviar("No, cámbialo a -10")                                # corrección: la vieja se descarta
    assert _esperar(qapp, lambda: ch._activo is None)
    assert _esperar(qapp, lambda: ch.turnos[0]["propuestas"][0]["estado"] == "descartado")
    assert ch.turnos[0]["propuestas"][0]["resultado"] == "Reemplazada por tu corrección"
    assert ch.turnos[1]["propuestas"][0]["estado"] == "pendiente"
    n = len(pasos)
    ch.enviar("sí, aplícalo")                                      # lo hace la app, sin preguntarle al modelo
    assert len(pasos) == n and ch.turnos[2].get("local")
    assert _esperar(qapp, lambda: ch.turnos[1]["propuestas"][0]["estado"] == "aplicado")
    assert cli.llamadas.count("confirmar_cambio") == 1
    ch.enviar("baja la cota")
    assert _esperar(qapp, lambda: ch._activo is None)
    ch.enviar("no")
    assert _esperar(qapp, lambda: ch.turnos[3]["propuestas"][0]["estado"] == "descartado")
    assert cli.llamadas.count("confirmar_cambio") == 1
