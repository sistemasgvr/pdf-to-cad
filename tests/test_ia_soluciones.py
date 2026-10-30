"""Punto 3 (pedido del usuario 2026-10-23): soluciones de cada conflicto que la APP calcula y PRUEBA en una copia, la
IA recomienda una y lo explica (guardado); y en Normativas, «Explicar con IA» guardado por regla. Con un servidor
Ollama SIMULADO (`ollama_falso`)."""
import json
import os
import shutil
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ia import explicar_norma as EN, memoria as M, proveedor as P, soluciones_ia  # noqa: E402
from nucleo import informe_datos, model_ops, soluciones  # noqa: E402
from nucleo.conflictos import Conflicto  # noqa: E402
from ollama_falso import OllamaFalso  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")


def _cfg(srv):
    return P.Config.de({"proveedor": "ollama", "url": srv.url})


# ── propuestas (puro) ──
def test_cruce_propone_bajar_o_subir_lo_justo_y_la_separacion_de_la_normativa():
    pipes = [{"layer": "AGUA", "pts": [(0, 0), (100, 0)], "diam": 12, "inv_start": 10.0, "inv_end": 10.0},
             {"layer": "DRENAJE", "pts": [(50, -50), (50, 50)], "diam": 24, "inv_start": 10.0, "inv_end": 10.0}]
    cat = {"reglas": [{"activa": True, "utilidad": "AGUA", "con_utilidad": "DRENAJE", "revisar": "sep_v", "min": 1.0}]}
    c = Conflicto("C-1", "cruce", 50.0, 0.0, "", [0, 1], [10.0, 10.0])
    props = soluciones.proponer(c, pipes, None, cat)
    agua = {(p.accion, p.delta_ft) for p in props if p.pipe == 0}
    # agua (1 ft de alto) bajo el drenaje: corona en 10 → baja 1; con 1 ft libre → baja 2. Encima: sobre 10 + 2
    assert agua == {("bajar", -1.0), ("bajar", -2.0), ("subir", 2.0), ("subir", 3.0)}
    assert all(p.id.startswith("P") for p in props) and len({p.id for p in props}) == len(props)
    sin_cotas = Conflicto("C-2", "cruce", 50.0, 0.0, "", [0, 1], [None, 10.0])
    assert soluciones.proponer(sin_cotas, pipes, None, cat) == []


def test_desplazar_cotas_mantiene_el_perfil_y_la_pendiente():
    p = {"layer": "AGUA", "pts": [(0, 0), (10, 0), (20, 0)], "inv_start": 10.0, "inv_end": 8.0,
         "vertex_inv_out": {1: 9.5}, "vertex_inv_in": {1: 9.0}}
    antes = [model_ops.cotas_tramo(p, k) for k in range(2)]
    soluciones.desplazar_cotas(p, -1.25)
    despues = [model_ops.cotas_tramo(p, k) for k in range(2)]
    assert despues == [(a - 1.25, b - 1.25) for a, b in antes]


def test_escalon_propone_igualar_y_se_aplica():
    p = {"layer": "AGUA", "pts": [(0, 0), (10, 0), (20, 0)], "inv_start": 10.0, "inv_end": 10.0,
         "vertex_inv_out": {1: 9.0}, "vertex_inv_in": {1: 10.0}}
    c = Conflicto("C-1", "escalon", 10.0, 0.0, "", [0], [10.0, 9.0])
    props = soluciones.proponer(c, [p], None)
    assert [x.accion for x in props] == ["igualar_salida", "igualar_llegada"]
    soluciones.aplicar([p], props[0])
    assert model_ops.cotas_tramo(p, 1)[0] == pytest.approx(10.0)


# ── en la ventana: validar, aplicar y deshacer ──
def _ventana(tmp_path, srv=None):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    proy = str(tmp_path / "Escenarios.digproj")
    shutil.copy(ESC, proy)
    w = Main()
    w._info = lambda *a, **k: None
    w._config_ia = (lambda: {"proveedor": "ollama", "url": srv.url, "modelo": "qwen3-vl:8b"}) if srv else \
        (lambda: {"proveedor": "plantilla"})
    w._open_project_path(proy)
    w._resultados_al_dia()
    return w


@pytest.mark.parametrize("clave", ["choque", "redes", "cruce", "escalon"])
def test_las_propuestas_se_prueban_y_la_aplicada_resuelve_y_se_deshace(tmp_path, clave):
    w = _ventana(tmp_path)
    c = next(c for c in w._conflictos if c.clave == clave)
    cc, props = w.soluciones_de(c.id)
    assert props and props[0].valida                                 # la mejor primero, ya probada
    assert all(p.resuelve is not None for p in props)
    p = props[0]
    antes = json.dumps(w.pipes[p.pipe], sort_keys=True, default=str)
    assert w.aplicar_propuesta(p)
    w._resultados_al_dia()
    assert not any(x.clave == c.clave and abs(x.x - c.x) <= 3 and abs(x.y - c.y) <= 3 for x in w._conflictos)
    w.undo()
    assert json.dumps(w.pipes[p.pipe], sort_keys=True, default=str) == antes
    w._dirty = False


def test_sin_propuesta_automatica_no_inventa(tmp_path):
    w = _ventana(tmp_path)
    c = next(c for c in w._conflictos if c.clave == "codos")
    assert w.soluciones_de(c.id)[1] == []
    w._dirty = False


# ── la IA recomienda (y se guarda) ──
def _caso():
    pipes = [{"layer": "AGUA", "pts": [(0, 0), (100, 0)], "diam": 12, "inv_start": 10.0, "inv_end": 10.0},
             {"layer": "DRENAJE", "pts": [(50, -50), (50, 50)], "diam": 24, "inv_start": 10.0, "inv_end": 10.0}]
    c = Conflicto("C-1", "cruce", 50.0, 0.0, "Cruce", [0, 1], [10.0, 10.0])
    props = soluciones.proponer(c, pipes, None)
    for p in props:
        p.resuelve = p.id != "P1"
    return informe_datos.ficha_conflicto(c, pipes), props


def test_la_ia_solo_puede_recomendar_una_valida_y_se_guarda(tmp_path):
    ficha, props = _caso()
    with OllamaFalso(lambda c: "RECOMENDADA: P1\nBajar el agua es lo más simple.") as srv:
        mem = M.Memoria(str(tmp_path / "P - IA"))
        rec, txt, origen = soluciones_ia.recomendar(P.crear(_cfg(srv)), ficha, props, mem)
        assert rec == "P2" and origen == "ia" and txt == "Bajar el agua es lo más simple."   # P1 no es válida
        assert soluciones_ia.recomendar(P.crear(_cfg(srv)), ficha, props, mem)[2] == "memoria"
        assert len(srv.pedidos) == 1
    with OllamaFalso(lambda c: "RECOMENDADA: P3\nSubir 7.77 ft.") as srv:            # cifra inventada
        otra = M.Memoria(archivo=str(tmp_path / "otro" / "entrenamiento_ia.json"))   # sin lo ya recomendado
        rec, txt, origen = soluciones_ia.recomendar(P.crear(_cfg(srv)), ficha, props, otra)
        assert origen == "plantilla" and rec == "P2"


def test_lo_aplicado_queda_como_ensenanza(tmp_path):
    ficha, props = _caso()
    mem = M.Memoria(str(tmp_path / "P - IA"))
    soluciones_ia.aprender(mem, ficha, props[1])
    reg = mem.registros(M.ENSENANZAS)[-1]
    assert reg["tipo"] == M.SOLUCION and props[1].texto in reg["texto"]
    assert mem.buscar("cruce agua drenaje")[0] is reg or mem.buscar("cruce agua drenaje")[0] == reg


# ── normativas: «Explicar con IA» guardado por regla ──
def test_explicar_regla_se_guarda_y_solo_se_repide_si_cambia():
    from nucleo import normas_base, normas_reglas as NR, normas_tablas as NT
    filas = NT.filas(normas_base.base(), "reglas")
    with OllamaFalso(lambda c: "Esta regla revisa la pendiente de las tuberías.") as srv:
        prov = P.crear(_cfg(srv))
        txt, origen = EN.explicar(prov, filas[0])
        assert origen == "ia" and txt.startswith("Esta regla")
        assert EN.explicar(prov, filas[0])[1] == "memoria" and EN.guardada(filas[0]) == txt
        otra = list(filas[0])
        otra[NR.COLUMNAS.index("NOTA")] = "cambiada"
        EN.explicar(prov, otra)
        assert len(srv.pedidos) == 2                                         # la regla cambió: se pide otra vez
    d = json.load(open(os.environ["PDFCAD_ENTRENAMIENTO_IA"], encoding="utf-8"))
    assert {v["ambito"] for v in d["redaccion"].values()} == {"normas"}


def test_panel_de_normativas(tmp_path):
    from PySide6 import QtWidgets
    from ui.dialogos.normas_dialog import NormasDialog
    with OllamaFalso(lambda c: "Explicación de la regla.") as srv:
        w = _ventana(tmp_path, srv)
        d = NormasDialog(w)
        v = d.tablas.vistas["reglas"]
        v.setCurrentCell(2, 0)
        assert d.panel_ia.btn.isEnabled()
        d.panel_ia.explicar()
        fin = time.time() + 10
        while "Explicación de la regla." not in d.panel_ia.texto.toPlainText() or not srv.pedidos:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.01)
            assert time.time() < fin
        v.setCurrentCell(3, 0)
        v.setCurrentCell(2, 0)
        assert "Explicación de la regla." in d.panel_ia.texto.toPlainText() and len(srv.pedidos) == 1
        assert not d.panel_ia.btn.isEnabled()                               # guardada: no hace falta pedirla
        w._dirty = False


def test_preguntas_de_replica_sobre_la_regla(tmp_path):
    """2026-10-29: tras la explicación se puede preguntar de nuevo («no entendí»); la IA recibe la regla, la
    explicación y lo ya preguntado; lo ajeno (código, cambiar reglas) no llega a la IA."""
    from PySide6 import QtWidgets
    from ui.dialogos.normas_dialog import NormasDialog
    def responder(c):
        ultimo = c["messages"][-1]["content"]
        if "PREGUNTA_DEL_USUARIO" not in ultimo:
            return "Explicación de la regla."
        return ("Sí, cambia el diámetro en el panel." if "app" in ultimo
                else "Quiere decir que la tubería debe ser más grande.")
    with OllamaFalso(responder) as srv:
        w = _ventana(tmp_path, srv)
        d = NormasDialog(w)
        v = d.tablas.vistas["reglas"]
        p = d.panel_ia
        fila = next(r for r in range(v.rowCount()) if EN.datos(d.tablas.fila_de("reglas", r))
                    and not EN.guardada(d.tablas.fila_de("reglas", r)))
        v.setCurrentCell(fila, 0)
        assert p.fila_preg.isHidden()                                        # sin explicación, no se pregunta

        def esperar(txt):
            fin = time.time() + 10
            while txt not in p.texto.toPlainText() or p._pensando is not None or p._explic is None:
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
                assert time.time() < fin
        p.explicar()
        esperar("Explicación de la regla.")
        assert not p.fila_preg.isHidden()
        p.ed_preg.setText("¿qué significa eso?")
        p.preguntar()
        esperar("más grande")
        p.ed_preg.setText("¿y qué hago en la app?")
        p.preguntar()
        esperar("cambia el diámetro")
        msgs = srv.pedidos[-1]["messages"]
        textos = " ".join(m["content"] for m in msgs)
        assert "Explicación de la regla." in textos and "¿qué significa eso?" in textos and "más grande" in textos
        n = len(srv.pedidos)
        p.ed_preg.setText("hazme un script en python que lea la tabla")
        p.preguntar()
        esperar("No escribo código")
        assert len(srv.pedidos) == n                                         # no llegó a la IA
        v.setCurrentCell(fila + 1, 0)                                         # otra regla: conversación nueva
        assert p._conv == [] and "Tú:" not in p.texto.toPlainText()
        w._dirty = False
