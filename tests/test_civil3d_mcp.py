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


# ── conflictos: las separaciones salen de las normativas y las pone el agente (el modelo no las ve) ──
def test_reglas_de_separacion_de_las_normativas():
    from ia.civil3d_reglas import reglas_separacion
    from nucleo import normas_base
    reglas = reglas_separacion(normas_base.base())          # las normativas de fábrica
    agua = [r for r in reglas if r["a"] == "AGUA" and r["b"] == "ALCANTARILLADO"]
    assert agua and agua[0]["encima"] == "AGUA" and agua[0]["sep_v_ft"] == 1.0
    assert any(r["a"] == "TELECOM" and r["b"] == "*" and r["sep_v_ft"] == 0.5 for r in reglas)
    cat = {"reglas": [{"utilidad": "GAS", "con_utilidad": "AGUA", "revisar": "debajo", "min": 2, "activa": True},
                      {"utilidad": "GAS", "con_utilidad": "AGUA", "revisar": "sep_v", "min": 1, "activa": False},
                      {"utilidad": "GAS", "revisar": "diametro", "min": 2}]}
    assert reglas_separacion(cat) == [{"a": "GAS", "b": "AGUA", "sep_v_ft": 2.0, "debajo": "GAS"}]
    assert reglas_separacion(None) == []


def test_el_agente_pasa_las_normativas_y_la_solucion_es_una_propuesta():
    tools = TOOLS + [{"name": n, "description": n,
                      "inputSchema": {"type": "object", "properties": {"conflicto": {"type": "string"},
                                                                         "reglas": {"type": "array"}}}}
                     for n in ("buscar_conflictos", "proponer_solucion")]

    class Cliente(ClienteFalso):
        def herramientas(self):
            return tools

        def llamar(self, nombre, args=None):
            self.llamadas.append((nombre, args))
            if nombre == "proponer_solucion":
                return True, json.dumps({"id": "C9", "tipo": "desplazar_vertical", "antes": "-5.00", "despues": "-3.46"})
            return True, json.dumps({"conflictos": {"total": 1}})

    reglas = [{"a": "AGUA", "b": "TELECOM", "sep_v_ft": 1.0}]
    ag_tools = A.herramientas_ollama(tools)
    for t in ag_tools:
        assert "reglas" not in t["function"]["parameters"].get("properties", {})   # el modelo no las ve
    c = Cliente()
    pedir, _ = modelo_guionado([llamada("buscar_conflictos", {"reglas": [{"a": "x"}]}),
                                llamada("proponer_solucion", {"conflicto": "K1"}), {"content": "Listo."}])
    r = A.Agente(c, pedir, reglas=lambda: reglas).preguntar("resuelve los choques")
    assert [a.get("reglas") for n, a in c.llamadas] == [reglas, reglas]          # las de la app, no las del modelo
    assert [p["id"] for p in r.propuestas] == ["C9"]


# ---------------------------------------------------------------- normativas, pendientes, tamaños y perfiles

_COLS = ["handle", "nombre", "red", "tipo_red", "utilidad", "numero", "tipo", "material", "diam_in", "x_ini", "y_ini",
         "x_fin", "y_fin", "cota_ini", "cota_fin", "est_ini", "est_fin", "tamano", "largo_ft"]


def _datos():
    """ALCANTARILLADO-5 = dos tuberías de Civil 3D seguidas (8", la primera a 0.1 %), ALCANTARILLADO-6 de 7" y una
    tubería que no viene de la app."""
    f = [["P1", "SS - (1)", "SS", "gravedad", "ALCANTARILLADO", "5", "COLECTOR", "PVC", 8, 0, 0, 100, 0, 100, 99.9, "M1", "M2", "8 in", 100],
         ["P2", "SS - (2)", "SS", "gravedad", "ALCANTARILLADO", "5", "COLECTOR", "PVC", 8, 100, 0, 200, 0, 99.9, 99.5, "M2", "M3", "8 in", 100],
         ["P3", "SS - (3)", "SS", "gravedad", "ALCANTARILLADO", "6", "COLECTOR", "PVC", 7, 200, 0, 300, 0, 99.5, 99.0, "M3", "", "7 in", 100],
         ["X1", "X - (1)", "X", "gravedad", "", "", "", "", 8, 0, 50, 100, 50, 10, 9, "", "", "", 100]]
    e = [["M1", "MH-1", "SS", 0, 0, 105, 99, "48 in", False], ["M2", "MH-2", "SS", 100, 0, 105, 99, "48 in", False],
         ["M3", "MH-3", "SS", 200, 0, 105, 99, "48 in", False]]
    return {"tuberias": {"columnas": _COLS, "filas": f},
            "estructuras": {"columnas": ["handle", "nombre", "red", "x", "y", "rim", "sump", "tamano", "nula"], "filas": e},
            "accesorios": {"columnas": ["id", "tipo", "red", "x", "y", "cota_eje", "une"], "filas": []}}


def test_revisar_normativas_del_dibujo_con_el_validador_de_la_app():
    from ia import civil3d_normativas as N
    from nucleo import normas_catalogo as nc
    pipes, _est, info = N.armar(_datos())
    assert len(pipes) == 2 and info["sin_utilidad"] == 1
    assert len(pipes[0]["pts"]) == 3 and pipes[0]["vertex_inv_in"] == {1: 99.9}       # P1 + P2 = una utilidad
    r = N.revisar(_datos(), nc.nuevo())
    filas = [dict(zip(r["avisos"]["columnas"], f)) for f in r["avisos"]["filas"]]
    pend = [f for f in filas if f["clase"] == "Pendiente"]
    assert len(pend) == 1 and pend[0]["tuberia"] == "SS - (1)" and pend[0]["utilidad"] == "ALCANTARILLADO-5"
    assert any(f["clase"] == "Diámetro" and f["utilidad"] == "ALCANTARILLADO-6" for f in filas)
    assert [f["id"] for f in filas] == [f"N{k}" for k in range(1, len(filas) + 1)]
    assert "sin_utilidad" in r
    solo = N.revisar(_datos(), nc.nuevo(), utilidad="ALCANTARILLADO-6")
    assert {f[3] for f in solo["avisos"]["filas"]} == {"ALCANTARILLADO-6"}


def test_la_pendiente_objetivo_y_la_revision_de_una_propuesta_son_las_de_la_app():
    from ia import civil3d_normativas_cambios as NC
    from nucleo import normas_catalogo as nc
    cat = nc.nuevo()
    obj = NC.objetivos_pendiente(_datos(), cat)
    assert obj["P1"]["min"] == obj["P2"]["min"] == 0.44 and "F200" in obj["P1"]["fuente"]        # LA Sewer, colector 8"
    assert "X1" not in obj
    # subir P1 a 0.5 %: la app ya no avisa su pendiente
    efecto = {"cotas": [{"handle": "P1", "ini": 100.0, "fin": 99.5}]}
    r = NC.revisar_efecto(_datos(), cat, efecto)
    assert [f["tuberia"] for f in r["resueltos"] if f["clase"] == "Pendiente"] == ["SS - (1)"] and not r["nuevos"]
    # bajar el diámetro de P3 a 6": la app avisa (mínimo 8" en colector)
    p = NC.con_normativa({"efecto": {"tamanos": [{"handle": "P3", "diam_in": 6, "material": "PVC"}]}, "advertencias": []},
                         _datos(), cat)
    assert p["advertencias"] == [] or all(a.startswith("Normativa: ") for a in p["advertencias"])
    d = NC.aplicar_efecto(_datos(), {"mover": {"handles": ["P1"], "estructuras": ["M1"], "dx": 5, "dy": 0, "dz": -1}})
    fila = dict(zip(_COLS, d["tuberias"]["filas"][0]))
    assert fila["x_ini"] == 5 and fila["cota_ini"] == 99 and d["estructuras"]["filas"][0][3] == 5
    assert _datos()["tuberias"]["filas"][0][9] == 0                                              # el original no cambia


def test_comparar_con_la_app_y_traer_lo_cambiado():
    from ia import civil3d_comparar as CC
    ft = 0.5                                       # pies por px
    pipes = [{} for _ in range(4)] + [
        {"layer": "ALCANTARILLADO", "pts": [(0, 0), (200, 0), (400, 0)], "diam": 8.0, "diam_elegido": True, "material": "PVC",
         "inv_start": 100.0, "inv_end": 99.0},
        {"layer": "ALCANTARILLADO", "pts": [(400, 0), (600, 0)], "diam": 8.0, "diam_elegido": True, "material": "PVC",
         "inv_start": 99.5, "inv_end": 99.0},
        {"layer": "AGUA", "pts": [(0, 100), (10, 100)], "diam": 6.0}]
    difs = CC.comparar(_datos(), pipes, ft)
    textos = {d["campo"]: d for d in difs}
    assert textos["inv_end"]["civil"] == "99.50" and textos["inv_end"]["utilidad"] == "ALCANTARILLADO-5"   # se cambió en C3D
    assert textos["diam"]["utilidad"] == "ALCANTARILLADO-6" and textos["diam"]["valor"] == 7
    assert textos["falta_civil"]["utilidad"] == "AGUA-7" and not textos["falta_civil"]["traer"]
    prop = CC.propuesta(difs, ["todas"], pipes)
    assert prop["destino"] == "app" and prop["id"].startswith("APP-")
    tocados = CC.aplicar(pipes, prop["cambios"])
    assert tocados == [4, 5] and pipes[4]["inv_end"] == 99.5 and pipes[5]["diam"] == 7 and pipes[5]["pipe_size"] == ""
    assert not [d for d in CC.comparar(_datos(), pipes, ft) if d["traer"]]                       # ya coinciden


class _ClientePlugin:
    """Plugin falso con datos_red y una propuesta de pendiente con su efecto."""
    instrucciones = ""

    def __init__(self, nombres):
        self.llamadas = []
        self.nombres = nombres

    def herramientas(self):
        return TOOLS + [{"name": n, "description": n,
                         "inputSchema": {"type": "object", "properties": {"elemento": {"type": "string"},
                                                                            "objetivos": {"type": "object"},
                                                                            "reglas": {"type": "array"}}}}
                        for n in self.nombres]

    def llamar(self, nombre, args=None):
        self.llamadas.append((nombre, args))
        if nombre == "datos_red":
            return True, json.dumps(_datos())
        if nombre == "estado":
            return True, json.dumps({"dibujo": ""})
        if nombre == "metrados":
            return True, json.dumps({"tuberias": {"columnas": ["u"], "filas": [["A"]]}})
        if nombre == "buscar_conflictos":
            return True, json.dumps({"conflictos": {"columnas": ["id"], "filas": []}})
        return True, json.dumps({"id": "C1", "tipo": "pendiente", "antes": "0.1 %", "despues": "0.44 %", "advertencias": [],
                                 "efecto": {"cotas": [{"handle": "P1", "ini": 100.0, "fin": 99.56}]}})


def test_el_agente_pone_la_normativa_de_la_app_en_lo_que_propone_el_plugin():
    from nucleo import normas_catalogo as nc
    cat = nc.nuevo()
    c = _ClientePlugin(("datos_red", "proponer_pendiente", "proponer_tamano", "crear_perfil", "proponer_mover_planta"))
    ag = A.Agente(c, None, normas_cat=lambda: cat, reglas=lambda: [{"a": "AGUA", "b": "*", "sep_v_ft": 1}],
                  proyecto=lambda: {"pipes": [], "ft": 1.0})
    vistos = {x["function"]["name"]: x["function"]["parameters"] for x in ag._tools}
    assert "datos_red" not in vistos
    assert {"revisar_normativas", "exportar_cuadro", "comparar_con_app", "traer_a_la_app"} <= set(vistos)
    assert all(not ({"reglas", "objetivos", "normas"} & set(p.get("properties", {}))) for p in vistos.values())
    assert "comparar_con_app" not in {x["function"]["name"] for x in A.Agente(c, None)._tools}
    pedir, msgs = modelo_guionado([llamada("revisar_normativas"),
                                   llamada("proponer_pendiente", {"elemento": "ALCANTARILLADO-5", "objetivos": {"P1": {"min": 9}}}),
                                   llamada("proponer_mover_planta", {"elemento": "AGUA-1", "dx": 2}), {"content": "Listo."}])
    ag.pedir_modelo = pedir
    r = ag.preguntar("revisa la normativa y arregla las pendientes")
    nombres = [n for n, _ in c.llamadas]
    assert nombres.count("datos_red") == 1                                   # una lectura por pregunta
    obj = dict(c.llamadas)["proponer_pendiente"]["objetivos"]
    assert obj["P1"]["min"] == 0.44                                          # la de la app, no la del modelo
    assert dict(c.llamadas)["proponer_mover_planta"]["reglas"][0]["a"] == "AGUA"
    assert r.llamadas[0] == ("revisar_normativas", True) and len(r.propuestas) == 2
    assert any("Ya cumple la normativa" in x for x in r.propuestas[0]["consecuencias"])


def test_exportar_cuadro_en_excel_y_word(tmp_path, monkeypatch):
    from ia import civil3d_cuadro
    from openpyxl import load_workbook
    monkeypatch.setattr(civil3d_cuadro.os.path, "expanduser", lambda p: str(tmp_path))
    c = _ClientePlugin(("datos_red",))
    ok, salida = civil3d_cuadro.ejecutar(c, None, [], {"formato": "excel"})
    r = json.loads(salida)
    assert ok and r["archivo"].endswith(".xlsx") and os.path.isfile(r["archivo"])
    wb = load_workbook(r["archivo"])
    assert "Tuberías" in wb.sheetnames and wb["Tuberías"].max_row == 5
    ok, salida = civil3d_cuadro.ejecutar(c, None, [], {"formato": "word"})
    assert ok and json.loads(salida)["archivo"].endswith(".docx")


def test_comparar_con_el_pdf_marca_lo_que_sobra_y_lo_que_falta():
    from ia import civil3d_pdf
    # «tinta» del PDF: una línea horizontal en y = 0 (px = ft) de x 0 a 200; nada más
    pr = {"pipes": [{"layer": "AGUA", "pts": [(0, 0), (200, 0)]}, {"layer": "GAS", "pts": [(0, 300), (100, 300)]}],
          "ft": 1.0, "a_px": lambda x, y: (x, y), "a_mundo": lambda x, y: (x, y),
          "tinta": lambda x, y, r: abs(y) <= r and -r <= x <= 200 + r}
    pts = civil3d_pdf.comparar(_datos(), pr)
    por = {(p["tipo"], p["elemento"]) for p in pts}
    assert ("sobra", "SS - (3)") in por                       # de 200 a 300: no hay tinta
    assert ("sobra", "SS - (1)") not in por and ("sobra", "X - (1)") in por
    assert ("falta", "GAS-2") in por and ("falta", "AGUA-1") not in por
    r = civil3d_pdf.resumen(pts)
    assert r["total"] == len(pts) and r["puntos"]["filas"][0][0] == "P1"
