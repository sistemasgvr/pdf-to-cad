"""Gemini como proveedor de la IA (2026-11-11), contra un servidor SIMULADO (`tests/gemini_falso.py`): sin red."""
import json

import pytest

from ia import civil3d_agente as A
from ia import proveedor as P
from ia import proveedor_gemini as PG
from ia import reporte_error as RE
from gemini_falso import GeminiFalso


@pytest.fixture
def servidor(monkeypatch):
    """Un Gemini simulado y la URL del proveedor apuntando a él."""
    def hacer(responder, **kw):
        g = GeminiFalso(responder, **kw)
        monkeypatch.setattr(PG, "URL_GEMINI", g.url)
        return g
    hechos = []
    yield lambda r, **kw: hechos.append(hacer(r, **kw)) or hechos[-1]
    for g in hechos:
        g.cerrar()


def _prov(modelo="gemini-2.5-flash", clave="clave-buena"):
    return P.crear({"proveedor": "gemini", "modelo": modelo, "clave": clave})


def test_config_de_gemini_pone_url_y_modelo_por_defecto_y_no_muestra_la_clave():
    c = P.Config.de({"proveedor": "gemini", "url": "http://100.82.39.116:11434", "clave": " abc "})
    assert c.url == PG.URL_GEMINI and c.modelo == PG.MODELO_GEMINI and c.clave == "abc"
    assert "abc" not in repr(c)
    assert isinstance(P.crear(c), PG.Gemini)
    # Ollama sigue igual
    o = P.Config.de({"proveedor": "ollama", "url": "http://x:1/", "modelo": "qwen"})
    assert (o.url, o.modelo) == ("http://x:1", "qwen") and isinstance(P.crear(o), P.Ollama)


def test_chat_en_vivo_con_sistema_json_e_imagen(servidor):
    g = servidor(lambda c: '{"ok": true, "texto": "hola mundo"}')
    trozos = []
    r = _prov().chat([{"role": "user", "content": "lee", "images": ["iVBORw0KGgo="]},
                      {"role": "assistant", "content": "listo"}, {"role": "user", "content": "otra"}],
                     sistema="Eres útil", json=True, al_texto=trozos.append, maximo=50)
    assert json.loads(r.texto)["texto"] == "hola mundo" and "".join(trozos) == r.texto and r.tokens > 0
    pedido = g.pedidos[0]
    assert pedido["systemInstruction"]["parts"][0]["text"] == "Eres útil"
    assert [c["role"] for c in pedido["contents"]] == ["user", "model", "user"]
    assert pedido["contents"][0]["parts"][1] == {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo="}}
    gen = pedido["generationConfig"]
    assert gen["responseMimeType"] == "application/json" and gen["maxOutputTokens"] == 50
    assert gen["thinkingConfig"] == {"thinkingBudget": 0}          # 2.5 Flash: respuesta rápida, sin pensar
    # la clave va en la cabecera, nunca en la URL
    assert g.claves[0] == "clave-buena" and all("clave-buena" not in r for r in g.rutas)
    assert ":streamGenerateContent?alt=sse" in g.rutas[0]


def test_modelo_que_piensa_recibe_margen_de_tokens(servidor):
    g = servidor(lambda c: "OK")
    _prov("gemini-2.5-pro").chat([{"role": "user", "content": "x"}], maximo=20)
    gen = g.pedidos[0]["generationConfig"]
    assert gen["maxOutputTokens"] == 20 + PG.MARGEN_PENSAR and gen["thinkingConfig"]["thinkingBudget"] > 0


def test_buscar_modelos_solo_los_de_chat(servidor):
    servidor(lambda c: "")
    assert _prov().modelos() == ["gemini-2.5-flash", "gemini-2.5-pro"]


def test_probar_y_errores_de_clave_y_limite(servidor):
    servidor(lambda c: "OK")
    ok, msg = _prov().probar()
    assert ok and "gemini-2.5-flash" in msg
    ok, msg = _prov(clave="mala").probar()
    assert not ok and "400" in msg
    with pytest.raises(P.ErrorIA) as e:
        _prov(clave="mala").chat([{"role": "user", "content": "x"}])
    assert "API key not valid" in e.value.detalle and "mala" not in (e.value.url + str(e.value))
    assert RE.armar(e.value, "Prueba", registrar=False).titulo == "La clave de Gemini no sirve"
    with pytest.raises(P.ErrorIA) as e:
        _prov(clave="").chat([{"role": "user", "content": "x"}])
    assert RE.armar(e.value, "Prueba", registrar=False).titulo == "La clave de Gemini no sirve"


def test_limite_de_pedidos(servidor):
    servidor(lambda c: "OK", codigo_error=429)
    with pytest.raises(P.ErrorIA) as e:
        _prov().chat([{"role": "user", "content": "x"}])
    assert e.value.codigo_http == 429
    assert RE.armar(e.value, "Prueba", registrar=False).titulo == "Se alcanzó el límite de Gemini"


def test_agente_con_herramientas_ida_y_vuelta(servidor):
    """El agente de Civil 3D / del chat: Gemini pide una herramienta, la app responde y Gemini contesta. La parte
    original (con su `thoughtSignature`) vuelve tal cual en el turno siguiente."""
    llamada = {"functionCall": {"name": "buscar_tuberias", "args": {"red": "AGUA"}}, "thoughtSignature": "firma"}

    def responder(c):
        return [llamada] if len(c["contents"]) == 1 else "Hay 3 tuberías."
    g = servidor(responder)
    cfg = P.Config.de({"proveedor": "gemini", "clave": "clave-buena"})
    pedir = A.pedir_agente(cfg)
    tools = [{"type": "function", "function": {"name": "buscar_tuberias", "description": "Busca",
                                                "parameters": {"type": "object", "properties": {"red": {"type": "string"}},
                                                               "additionalProperties": False}}}]
    msgs = [{"role": "system", "content": "Sistema"}, {"role": "user", "content": "¿cuántas?"}]
    m = pedir(msgs, tools)
    assert m["tool_calls"][0]["function"] == {"name": "buscar_tuberias", "arguments": {"red": "AGUA"}}
    decl = g.pedidos[0]["tools"][0]["functionDeclarations"][0]
    assert decl["name"] == "buscar_tuberias" and decl["parametersJsonSchema"]["additionalProperties"] is False
    assert g.pedidos[0]["systemInstruction"]["parts"][0]["text"] == "Sistema"
    msgs += [{"role": "assistant", "content": "", "tool_calls": m["tool_calls"]},
             {"role": "tool", "tool_name": "buscar_tuberias", "content": "3", "images": ["/9j/abc"]}]
    m2 = pedir(msgs, tools)
    assert m2["content"] == "Hay 3 tuberías." and not m2["tool_calls"]
    conts = g.pedidos[1]["contents"]
    assert conts[1] == {"role": "model", "parts": [llamada]}
    assert conts[2]["role"] == "user"
    assert conts[2]["parts"][0] == {"functionResponse": {"name": "buscar_tuberias", "response": {"content": "3"}}}
    assert conts[2]["parts"][1]["inlineData"]["mimeType"] == "image/jpeg"
    # el agente completo funciona igual que con Ollama
    assert _prov().herramientas() and _prov().vision()


def test_ollama_sigue_usando_su_agente():
    cfg = P.Config.de({"proveedor": "ollama"})
    assert A.pedir_agente(cfg).__qualname__.startswith("pedir_ollama")


def test_dialogo_configurar_ia_recuerda_modelo_y_clave_por_proveedor(qtbot=None):
    """Elegir Gemini muestra la clave (oculta) y su modelo; volver a Ollama repone el suyo; Guardar escribe los dos."""
    from PySide6 import QtCore, QtWidgets
    from ui.dialogos.ia_config_dialog import IAConfigDialog
    from ui.ventana.ventana_ia import IAMixin
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    s = QtCore.QSettings("pdf-to-cad", "app")
    for k in ("proveedor", "modelo", "modelo_gemini", "clave_gemini", "url"):
        s.remove("ia/" + k)
    s.setValue("ia/proveedor", "ollama")
    s.setValue("ia/modelo", "qwen3-vl:8b")

    class Win(QtWidgets.QWidget, IAMixin):
        pass
    win = Win()
    dlg = IAConfigDialog(win)
    assert dlg.ed_clave.isHidden() and dlg.ed_clave.echoMode() == QtWidgets.QLineEdit.Password
    dlg.cmb_prov.setCurrentIndex(dlg.cmb_prov.findData("gemini"))
    assert not dlg.ed_clave.isHidden() and dlg.ed_url.isHidden()
    assert dlg.cmb_modelo.currentText() == PG.MODELO_GEMINI
    dlg.cmb_modelo.setEditText("gemini-2.5-pro")
    dlg.ed_clave.setText("mi-clave")
    dlg.cmb_prov.setCurrentIndex(dlg.cmb_prov.findData("ollama"))
    assert dlg.cmb_modelo.currentText() == "qwen3-vl:8b"
    dlg.cmb_prov.setCurrentIndex(dlg.cmb_prov.findData("gemini"))
    assert dlg.cmb_modelo.currentText() == "gemini-2.5-pro"
    dlg.accept()
    c = win._config_ia()
    assert (c["proveedor"], c["modelo"], c["clave"]) == ("gemini", "gemini-2.5-pro", "mi-clave")
    assert s.value("ia/modelo") == "qwen3-vl:8b"                 # el de Ollama no se pisa
    s.setValue("ia/proveedor", "ollama")
    assert win._config_ia()["modelo"] == "qwen3-vl:8b"
    for k in ("proveedor", "modelo", "modelo_gemini", "clave_gemini"):
        s.remove("ia/" + k)


def test_saturado_un_reintento_y_luego_mensaje_claro(servidor, monkeypatch):
    """503 «high demand» (gemini-3.8-flash, 2026-11-11): un reintento; si sigue, «Gemini está saturado»."""
    monkeypatch.setattr(PG, "REINTENTO_S", 0.01)
    g = servidor(lambda c: "OK", saturado=1)
    assert _prov().chat([{"role": "user", "content": "x"}]).texto == "OK"
    servidor(lambda c: "OK", saturado=5)
    with pytest.raises(P.ErrorIA) as e:
        _prov().chat([{"role": "user", "content": "x"}])
    assert e.value.codigo_http == 503
    assert RE.armar(e.value, "Prueba", registrar=False).titulo == "Gemini está saturado"


def test_modelo_que_no_responde_no_deja_esperando(servidor, monkeypatch):
    """gemini-3.7-flash colgaba minutos: «Probar» corta a ESPERA_PROBAR_S y el chat a ESPERA_GEMINI_S."""
    import time
    monkeypatch.setattr(PG, "ESPERA_PROBAR_S", 0.5)
    servidor(lambda c: "OK", demora=3)
    t0 = time.perf_counter()
    ok, msg = _prov("gemini-3.7-flash").probar()
    assert not ok and time.perf_counter() - t0 < 2.5 and "saturado" in msg
    p = _prov("gemini-3.7-flash")
    p.espera_s = 0.5
    with pytest.raises(P.ErrorIA) as e:
        p.chat([{"role": "user", "content": "x"}])
    assert RE.armar(e.value, "Prueba", registrar=False).titulo == "Gemini está saturado"


def test_modelo_retirado_dice_que_elijas_otro_no_ollama():
    err = P.ErrorIA("Gemini respondió 404: NOT_FOUND This model models/gemini-2.5-flash is no longer available "
                    "to new users.", codigo_http=404)
    rep = RE.armar(err, "Prueba", registrar=False)
    assert rep.titulo == "Ese modelo de Gemini ya no está disponible" and "Ollama" not in rep.que_hacer


def test_el_recomendado_va_primero(servidor):
    servidor(lambda c: "", modelos=[{"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]}
                                    for n in ("gemini-2.5-flash", "gemini-3.8-flash", PG.MODELO_GEMINI)])
    assert _prov().modelos()[0] == PG.MODELO_GEMINI
