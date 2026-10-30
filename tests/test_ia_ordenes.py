"""El chat de la IA HACE cambios con confirmación (pedido del usuario 2026-10-30): la IA traduce el pedido a una
acción del catálogo, la app la valida, dice qué hará y sus consecuencias, y solo con «Sí, hazlo» la aplica (un paso
de deshacer); con «No» repregunta y el mensaje siguiente corrige el pedido. Con un Ollama SIMULADO."""
import json
import os
import shutil
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ia import acciones as AC  # noqa: E402
from ollama_falso import OllamaFalso  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")


def test_que_es_una_orden():
    for q in ("Mueve AGUA-5 3 ft al norte", "baja las cotas de GAS-2 un pie", "por favor borra AGUA-1",
              "cambia el diámetro de AGUA-3 a 8 pulgadas", "abre la vista 3D", "resuelve C-4", "move AGUA-5 north"):
        assert AC.es_orden(q), q
    for q in ("¿cuántos conflictos hay?", "¿por qué ocurre C-3?", "¿cómo exporto a Civil 3D?"):
        assert not AC.es_orden(q), q


class _Datos:
    def __init__(self, refs):
        self.refs = refs

    def ref(self, c):
        return self.refs.get(str(c).upper())


def test_validar_y_describir_los_pone_la_app():
    d = _Datos({"AGUA-5": {"objeto": "pipe", "indice": 4}, "C-2": {"objeto": "conflicto", "indice": -1}})
    o = AC.validar({"accion": "mover_utilidad", "parametros": {"utilidad": "agua-5", "dx_ft": 0, "dy_ft": 3}}, d)
    assert not o.error and o.parametros["pipes"] == [4]
    assert "3.00 ft" in AC.describir(o) and "AGUA-5" in AC.describir(o)
    o = AC.validar({"accion": "cambiar_cotas", "parametros": {"utilidad": "AGUA-9", "delta_ft": -1}}, d)
    assert "AGUA-9" in o.error                                       # código inexistente: no se inventa
    o = AC.validar({"accion": "cambiar_material", "parametros": {"utilidades": ["AGUA-5"], "material": "oro"}},
                   d, materiales=["PVC", "Acero"])
    assert o.error                                                   # material fuera de la lista
    o = AC.validar({"accion": "cambiar_cotas", "parametros": {"utilidad": "AGUA-5"}}, d)
    assert o.error                                                   # falta cuánto: se pregunta


def _ventana(tmp_path, srv):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    proy = str(tmp_path / "Escenarios.digproj")
    shutil.copy(ESC, proy)
    w = Main()
    w._info = lambda *a, **k: None
    w._config_ia = lambda: {"proveedor": "ollama", "url": srv.url, "modelo": "qwen3-vl:8b"}
    w._open_project_path(proy)
    w._resultados_al_dia()
    return w


def _esperar(cond, s=20):
    from PySide6 import QtWidgets
    fin = time.time() + s
    while not cond() and time.time() < fin:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert cond()


def test_pide_confirmacion_hace_el_cambio_y_se_deshace(tmp_path):
    from ia import contexto  # noqa: F401
    respuestas = []

    def responder(c):
        return respuestas.pop(0)
    with OllamaFalso(responder) as srv:
        w = _ventana(tmp_path, srv)
        datos = w._ia_datos()
        i = next(k for k, p in enumerate(w.pipes) if len(p.get("pts") or []) >= 2)
        codigo = next(c for c, r in datos.refs.items() if r["objeto"] == "pipe" and r["indice"] == i).upper()
        z0 = w._pipe_z_at(i, 0, *w.pipes[i]["pts"][0])
        from ui.dialogos.ia_chat import PreguntaDialog
        d = PreguntaDialog(w)
        # 1) falta un dato: la IA pregunta y el pedido queda pendiente
        respuestas.append(json.dumps({"accion": None, "pregunta": "¿Cuántos pies la bajo?"}))
        d.enviar(f"baja {codigo}")
        _esperar(lambda: d.turnos[-1]["estado"] == "listo")
        assert "pies" in d.turnos[-1]["texto"] and d._orden_pendiente
        # 2) la respuesta completa el pedido: confirmación con lo que hará y sus consecuencias
        respuestas.append(json.dumps({"accion": "cambiar_cotas", "parametros": {"utilidad": codigo, "delta_ft": -1},
                                      "entendido": "Bajar 1 ft"}))
        d.enviar("1 pie")
        _esperar(lambda: d.turnos[-1].get("orden") is not None)
        assert "Corrección del usuario" in srv.pedidos[-1]["messages"][-1]["content"]     # llevó el pedido anterior
        od = d.turnos[-1]["orden"]
        assert od["estado"] == "confirmar" and codigo in od["que"] and od["cons"]
        assert w._pipe_z_at(i, 0, *w.pipes[i]["pts"][0]) == z0                           # nada cambió aún
        assert "ordensi:" in d.vista.toHtml()
        # 3) «No»: no cambia nada y repregunta
        d._confirmar_orden(len(d.turnos) - 1, False)
        assert od["estado"] == "cancelado" and d._orden_pendiente["entendido"] == od["que"]
        assert w._pipe_z_at(i, 0, *w.pipes[i]["pts"][0]) == z0
        # 4) corrige y confirma: se hace, en un paso de deshacer
        respuestas.append(json.dumps({"accion": "cambiar_cotas", "parametros": {"utilidad": codigo, "delta_ft": -2},
                                      "entendido": "Bajar 2 ft"}))
        d.enviar("mejor 2 pies")
        _esperar(lambda: d.turnos[-1].get("orden") is not None)
        d._confirmar_orden(len(d.turnos) - 1, True)
        assert d.turnos[-1]["orden"]["estado"] == "hecho"
        assert abs(w._pipe_z_at(i, 0, *w.pipes[i]["pts"][0]) - (z0 - 2)) < 1e-6
        w.undo()
        assert abs(w._pipe_z_at(i, 0, *w.pipes[i]["pts"][0]) - z0) < 1e-6
        # 5) una pregunta normal sigue el camino de siempre
        respuestas.append(json.dumps({"accion": "ninguna"}))
        respuestas.append("Hay varios conflictos.")
        d.enviar("muestra cuántos conflictos hay")
        _esperar(lambda: d.turnos[-1]["estado"] == "listo" and d.turnos[-1]["res"] is not None)
        assert d.turnos[-1].get("orden") is None
        w._dirty = False


def test_mover_borrar_y_abrir(tmp_path):
    with OllamaFalso(lambda c: "{}") as srv:
        w = _ventana(tmp_path, srv)
        datos = w._ia_datos()
        i = next(k for k, p in enumerate(w.pipes) if len(p.get("pts") or []) >= 2)
        codigo = next(c for c, r in datos.refs.items() if r["objeto"] == "pipe" and r["indice"] == i).upper()
        pts0 = list(w.pipes[i]["pts"])
        o, que, cons = w.orden_preparar({"accion": "mover_utilidad", "parametros": {
            "utilidad": codigo, "dx_ft": 0, "dy_ft": 3}}, datos)
        assert not o.error and "norte" in que and any("Ctrl+Z" in c for c in cons)
        w.orden_ejecutar(o)
        pf = float(w.zoom) / w.scale
        assert all(abs(a[1] + 3 * pf - b[1]) < 1e-6 and abs(a[0] - b[0]) < 1e-6 for a, b in zip(w.pipes[i]["pts"], pts0))   # norte = −Y
        w.undo()
        n = len(w.pipes)
        o, _que, cons = w.orden_preparar({"accion": "borrar_utilidades", "parametros": {"utilidades": [codigo]}},
                                         datos)
        assert not o.error
        w.orden_ejecutar(o)
        assert len(w.pipes) == n - 1
        w.undo()
        assert len(w.pipes) == n
        o, que, cons = w.orden_preparar({"accion": "abrir", "parametros": {"ventana": "tabla"}}, datos)
        assert not o.error and "Tabla de datos" in que and cons == ["No cambia nada del proyecto."]
        w._dirty = False
