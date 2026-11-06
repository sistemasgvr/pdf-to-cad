"""Errores de la IA (reporte del usuario 2026-11-06: «El servidor de IA respondió 500: no user query found in
messages» con el servidor funcionando). Causa: lo enviado no cabía en la ventana de contexto y Ollama quitaba los
mensajes más viejos, también la pregunta. Ahora el agente ajusta lo que envía; y todo error se muestra con un
reporte claro (qué pasó, qué hacer, captura al equipo de desarrollo, detalles) que queda en el registro."""
import datetime
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ia import civil3d_agente as A  # noqa: E402
from ia import proveedor as P  # noqa: E402
from ia import reporte_error as RE  # noqa: E402


def _herramientas(n=28, largo=500):
    return [{"type": "function", "function": {"name": f"h{i}", "description": "x" * largo,
                                              "parameters": {"type": "object", "properties": {}}}}
            for i in range(n)]


def test_ajustar_nunca_pierde_la_pregunta_y_cabe():
    tools = _herramientas()
    hist = []
    for k in range(10):
        hist += [{"role": "user", "content": f"pregunta vieja {k} " + "a" * 2000},
                 {"role": "assistant", "content": "respuesta " + "b" * 2000}]
    msgs = [{"role": "system", "content": "S" * 4000}] + hist + [{"role": "user", "content": "LA PREGUNTA"}]
    for k in range(14):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "h1", "arguments": {}}}]})
        msgs.append({"role": "tool", "tool_name": "h1", "content": f"resultado {k} " + "r" * 6000})
    antes = json.dumps(msgs)
    out = A.ajustar(msgs, tools)
    assert json.dumps(msgs) == antes                                  # no cambia lo original
    assert out[0] == msgs[0]
    assert any(m["role"] == "user" and m["content"] == "LA PREGUNTA" for m in out)
    assert A.tokens(out) <= P.CONTEXTO_TOKENS - A.RESERVA_RESPUESTA - A.tokens(tools)
    assert out[-1]["content"].startswith("resultado 13")              # el último resultado sigue
    assert not any("pregunta vieja" in (m.get("content") or "") for m in out)


def test_ajustar_no_toca_nada_si_cabe():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "hola"}]
    assert A.ajustar(msgs, _herramientas(2, 10)) == msgs


def test_el_agente_envia_siempre_la_pregunta():
    vistos = []

    class Cli:
        instrucciones = ""

        def herramientas(self):
            return []

        def llamar(self, nombre, args):
            return True, "r" * 6000

    def pedir(mensajes, herramientas):
        vistos.append(mensajes)
        if len(vistos) < 12:
            return {"content": "", "tool_calls": [{"function": {"name": "estado_dibujo", "arguments": {}}}]}
        return {"content": "listo"}
    ag = A.Agente(Cli(), pedir)
    ag.app.llamar = lambda n, a: (True, "r" * 6000)
    ag.preguntar("propon una solucion")
    for m in vistos:
        assert any(x["role"] == "user" and x["content"] == "propon una solucion" for x in m)
        assert A.tokens(m) <= P.CONTEXTO_TOKENS - A.RESERVA_RESPUESTA - A.tokens(ag._tools)


def test_reporte_claro_con_detalles_y_registro(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    e = P.ErrorIA("El servidor de IA respondió 500: {\"error\":\"no user query found in messages\"}",
                  codigo_http=500, detalle="{\"error\":\"no user query found in messages\"}",
                  url="http://localhost:11434/api/chat", modelo="qwen3.8:latest")
    rep = RE.armar(e, "Chat Civil 3D", pregunta="propon una solucion", pasos=["buscar_conflictos", "buscar_conflictos"],
                   ahora=datetime.datetime(2026, 11, 6, 12, 11, 5))
    assert rep.titulo == "La conversación no cupo en la memoria de la IA"
    assert rep.codigo.startswith("E-261106-121105-")
    d = dict(rep.detalles)
    assert d["Modelo"] == "qwen3.8:latest" and d["Servidor"].endswith("/api/chat")
    assert d["Respuesta del servidor"].startswith("HTTP 500") and d["Consultó"] == "buscar_conflictos"
    assert d["Dónde"] == "Chat Civil 3D" and d["Tipo de error"] == "ErrorIA"
    assert rep.registro and rep.codigo in open(rep.registro, encoding="utf-8").read()
    assert rep.codigo in RE.texto_corto(rep)


def test_causas_conocidas_y_generica(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    casos = {"No se pudo conectar con el servidor de IA (http://x): [WinError 10061] denegó": "No se pudo conectar",
             "El servidor de IA respondió 404: model 'qwen9' not found": "no está instalado",
             "timed out": "tardó demasiado",
             "model requires more system memory (9 GiB) than is available": "sin memoria",
             "Se cortó la conexión con PdfCadMcp.exe.": "Civil 3D"}
    for msg, esperado in casos.items():
        assert esperado in RE.armar(P.ErrorIA(msg), "x").titulo, msg
    try:
        {}["falta"]
    except KeyError as e:
        rep = RE.armar(e, "x")
    assert rep.titulo == "Algo salió mal" and "test_reporte_error.py" in dict(rep.detalles)["En el código"]


def test_tarjeta_html_en_los_dos_temas(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    from ui.comun import error_html, theme
    rep = RE.armar(P.ErrorIA("boom <b>"), "Chat Civil 3D")
    for tk in (theme.LIGHT, theme.DARK):
        h = error_html.tarjeta(rep, tk, "copiarerror:0")
        assert "captura" in h and rep.codigo in h and "copiarerror:0" in h and "<b>boom" not in h


def test_si_responde_sin_consultar_se_le_insiste_una_vez():
    """Reporte 2026-11-06: «Comparé el modelo 3D contra el PDF…» con «Sin consultar el dibujo»."""
    vistos = []

    class Cli:
        instrucciones = ""

        def herramientas(self):
            return []

    respuestas = [{"content": "Comparé: coinciden 11 tuberías."},
                  {"content": "", "tool_calls": [{"function": {"name": "comparar_con_pdf", "arguments": {}}}]},
                  {"content": "Coinciden 11 tuberías (recién consultado)."}]

    def pedir(mensajes, herramientas):
        vistos.append([dict(m) for m in mensajes])
        return respuestas[len(vistos) - 1]
    ag = A.Agente(Cli(), pedir)
    ag.app.llamar = lambda n, a: (True, "{}")
    res = ag.preguntar("Compara el modelo 3d contra el pdf")
    assert len(vistos) == 3 and res.texto.endswith("(recién consultado).")
    assert vistos[1][-1]["role"] == "user" and vistos[1][-1]["content"].startswith(A.RECORDATORIO)
    assert [n for n, _ok in res.llamadas] == ["comparar_con_pdf"]
    # una charla sin pedido de datos no se repite
    vistos.clear()
    respuestas[:] = [{"content": "¡De nada!"}]
    assert ag.preguntar("gracias").texto == "¡De nada!" and len(vistos) == 1


def test_las_cotas_son_elevaciones_en_las_instrucciones():
    assert "ELEVACIONES" in A.SISTEMA and "comparar_con_app" in A.SISTEMA
    assert A.pide_datos("y las cotas?") and A.pide_datos("¿Cuántos buzones hay?") and not A.pide_datos("gracias")
