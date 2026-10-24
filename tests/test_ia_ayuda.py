"""Ayuda → Manual: «¿Cómo hago…?» con la IA (pedido del usuario 2026-10-23), con un Ollama SIMULADO. Y el
informe automático en segundo plano: no bloquea la ventana, se puede cancelar."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ia import ayuda_manual as AM  # noqa: E402
from ia import proveedor as P  # noqa: E402
from ollama_falso import OllamaFalso  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")
MANUAL = os.path.join(AQUI, "..", "app", "docs", "manual.es.html")


def _doc():
    with open(MANUAL, encoding="utf-8") as f:
        return f.read()


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _esperar(cond, s=20):
    from PySide6 import QtWidgets
    fin = time.time() + s
    while not cond() and time.time() < fin:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    return cond()


def test_busca_los_capitulos_que_vienen_al_caso_y_manda_poco():
    ix = AM.indice(_doc())
    casos = {"¿cómo exporto a Civil 3D?": "Exportar y abrir en Civil 3D",
             "cómo dibujo una tubería": "Dibujar una tubería",
             "como georreferencio el plano": "Georreferenciar (opcional)",
             "cómo unir dos utilidades": "Unir utilidades",
             "como hago el informe en word": "Informe automático"}
    for q, cap in casos.items():
        contexto, caps = ix.contexto(ix.buscar(q))
        assert cap in [c for _n, c in caps[:2]], (q, caps)      # entre los dos primeros (el resumen de IA nombra módulos)
        assert 0 < len(contexto) <= AM.MAX_CONTEXTO
    # varias formas de hacerlo: el panel del plano también, no solo la Vista 3D (reporte del usuario)
    contexto, caps = ix.contexto(ix.buscar("como cambio una cota de una tuberia?"))
    assert {"Datos de la tubería", "Vista 3D"} <= {c for _n, c in caps}
    assert "Elevación inicial / final: Cota del fondo" in contexto
    assert AM.indice(_doc()) is ix                                    # el índice se arma una vez
    assert ix.buscar("zzqx wqk") == []


def test_responde_con_el_manual_y_la_guarda():
    ix = AM.indice(_doc())
    with OllamaFalso(lambda c: "Usa **Archivo → Exportar**.") as srv:
        prov = P.crear({"proveedor": "ollama", "url": srv.url})
        q = "¿Cómo exporto a Civil 3D? (prueba %d)" % time.time_ns()
        texto, origen, caps = AM.responder(prov, ix, q)
        assert origen == "ia" and "Exportar" in texto and caps
        pedido = srv.pedidos[-1]
        assert pedido["options"]["num_predict"] == AM.MAXIMO_TOKENS
        assert len(pedido["messages"][-1]["content"]) < AM.MAX_CONTEXTO + 400       # solo los trozos del caso
        n = len(srv.pedidos)
        assert AM.responder(prov, ix, "  " + q.upper() + " ")[1] == "memoria"     # la misma pregunta: guardada
        assert len(srv.pedidos) == n


def test_manual_con_el_campo_de_la_ia():
    _app()
    from ui.dialogos.manual_dialog import ManualDialog

    with OllamaFalso(lambda c: "Paso 1: **Ver → Vista 3D**.") as srv:
        class Ventana:
            def _config_ia(self):
                return {"proveedor": "ollama", "url": srv.url, "modelo": "qwen3-vl:8b"}
        from PySide6 import QtCore, QtWidgets
        padre = QtWidgets.QWidget()
        padre._config_ia = Ventana()._config_ia
        dlg = ManualDialog(padre)
        panel = dlg.ayuda_ia
        assert _esperar(lambda: any("messages" not in p for p in srv.pedidos))     # precarga del modelo
        panel.campo.setText("cómo abro la vista 3D %d" % time.time_ns())
        panel.preguntar()
        assert "cap:" in panel.respuesta.toHtml()                                  # capítulos al instante
        assert _esperar(lambda: not panel.ocupado)
        assert "Vista 3D" in panel.respuesta.toPlainText()
        n = int(panel._caps[0][0])
        panel._enlace(QtCore.QUrl(f"cap:{n}"))
        assert dlg.indice.currentRow() == n
    # sin IA: los capítulos son la respuesta
    dlg2 = ManualDialog(None)
    dlg2.ayuda_ia.preguntar("cómo dibujo una tubería")
    assert not dlg2.ayuda_ia.ocupado and "Dibujar una tubería" in dlg2.ayuda_ia.respuesta.toPlainText()


def test_informe_en_segundo_plano_no_bloquea_y_se_cancela(tmp_path):
    _app()
    from nucleo.informe_datos import Opciones
    from ui.comun import busy
    from ui.ventana.app_window import Main
    w = Main()
    w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    w._resultados_al_dia()
    ruta = str(tmp_path / "inf.docx")
    w.generar_informe(ruta, Opciones(True, True, True, False), esperar=False)
    trabajo = w._informe_en_curso
    assert trabajo is not None and trabajo.activo
    assert not busy.overlay_for(w).active                                     # la ventana sigue usable
    assert w.generar_informe(ruta, Opciones(), esperar=False) is None         # uno a la vez
    w.cancelar_informe()
    assert w._informe_en_curso is None and not os.path.exists(ruta)
    assert w.generar_informe(ruta, Opciones(True, True, True, False)) == ruta and os.path.exists(ruta)
    assert w._informe_en_curso is None
    w._dirty = False
