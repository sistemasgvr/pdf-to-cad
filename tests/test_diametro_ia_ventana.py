"""La tarjeta «Diámetro según la IA» del inspector (`ui/ventana/ventana_diametro_ia`): solo con IA configurada y
un aviso «Diámetro del plano» pendiente; pregunta A PEDIDO (importar no pregunta nada); «Usar» aplica y se deshace;
elegir otra utilidad cancela el pedido. Con un servidor Ollama SIMULADO."""
import json
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ollama_falso import OllamaFalso  # noqa: E402


def _resp(rot, conf="alta"):
    return json.dumps({"rotulo": rot, "confianza": conf, "motivo": "su guía llega a esta línea", "pista": None})


def _cerca(d=18.0, guia="esta"):
    return [dict(id="R1", texto=f'LAT CB-226 / {d:g}" RCP', diam_in=d, material="RCP", util="", es_de=True,
                 dist_pt=2.0, guia=guia, otra=None, caja=[40.0, -30.0, 80.0, -24.0], estacion=False, union=False,
                 varios=1)]


def _pipe(y=0.0, cerca=True):
    dp = {"estado": "sin_dato"}
    if cerca:
        dp["cerca"] = _cerca()
    return {"layer": "DRENAJE", "pts": [(50.0, 100.0 + y), (350.0, 100.0 + y)], "diam": 12.0, "diam_plano": dp,
            "origen": "reconocido"}


def _ventana(srv=None, pipes=None):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    w = Main()
    w._diam_ia_auto = False  # cada prueba manual controla cuándo se consulta; abajo se prueba el automático
    img = QtGui.QImage(600, 600, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)                              # con hoja: el redibujo calcula los avisos
    w._info = lambda *a, **k: None
    w.informar = lambda *a, **k: setattr(w, "_informado", a)
    w._config_ia = (lambda: {"proveedor": "ollama", "url": srv.url, "modelo": "qwen3-vl:8b"}) if srv else \
        (lambda: {"proveedor": "plantilla"})
    w.scale, w.zoom = 20.0 / 72.0, 1.0                   # 1"=20' (los avisos se calculan con escala)
    w.pipes = list(pipes if pipes is not None else [_pipe(), _pipe(200.0)])
    w._refresh_lists()
    w._redraw()
    w._resultados_al_dia()
    return w


def _elegir(w, i):
    assert w._mostrar_en_panel(i)
    w._diam_ia_refrescar()


def _esperar(w, cond, s=10.0):
    from PySide6 import QtWidgets
    t0 = time.time()
    while not cond() and time.time() - t0 < s:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    return cond()


def test_tarjeta_solo_con_ia_y_aviso():
    w = _ventana()
    _elegir(w, 0)
    assert not w.tarjeta_diam_ia.isVisibleTo(w.gprop)              # sin IA configurada: como hoy
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        w = _ventana(srv)
        _elegir(w, 0)
        assert w.tarjeta_diam_ia.isVisibleTo(w.gprop)
        assert w.btn_diam_ia_preguntar.isVisibleTo(w.gprop)
        w.pipes[0]["diam"], w.pipes[0]["diam_elegido"] = 18.0, True    # ya tiene su diámetro: sin aviso
        w._redraw()
        w._resultados_al_dia()
        _elegir(w, 0)
        assert not w.tarjeta_diam_ia.isVisibleTo(w.gprop)
        assert srv.pedidos == []                                    # nada se pidió solo


def test_preguntar_y_usar():
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        w = _ventana(srv)
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        assert _esperar(w, lambda: w._diam_ia_pedido is None and w._diam_ia_sug(0) is not None)
        assert w._diam_ia_sug(0).diam_in == 18.0
        assert w.btn_diam_ia_usar.isVisibleTo(w.gprop) and "18" in w.btn_diam_ia_usar.text()
        assert len(srv.pedidos) == 2
        w.usar_diametro_ia()
        assert w.pipes[0]["diam"] == 18.0 and w.pipes[0].get("diam_elegido")
        w._resultados_al_dia()
        assert not any(a.clase == "grosor" and a.pipe == 0 for a in w._normas_avisos)
        w.undo()
        assert w.pipes[0]["diam"] == 12.0 and not w.pipes[0].get("diam_elegido")


def test_usar_con_familia_sin_ese_tamano():
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        p = _pipe()
        p["pipe_family"] = "familia-inexistente"
        w = _ventana(srv, [p])
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        assert _esperar(w, lambda: w._diam_ia_pedido is None and w._diam_ia_sug(0) is not None)
        w.usar_diametro_ia()
        assert w.pipes[0]["diam"] == 12.0                           # nada se tocó
        assert getattr(w, "_informado", None)                       # «elige el tamaño en el panel»


def test_proyecto_sin_evidencia_no_pregunta():
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        w = _ventana(srv, [_pipe(cerca=False)])
        _elegir(w, 0)
        assert w.tarjeta_diam_ia.isVisibleTo(w.gprop)
        assert not w.btn_diam_ia_preguntar.isVisibleTo(w.gprop)
        assert "Vuelve a reconocer" in w.lbl_diam_ia.text()
        assert srv.pedidos == []


def test_elegir_otra_cancela_y_no_pisa():
    suelta = threading.Event()

    def lento(c):
        suelta.wait(5)
        return _resp("R1")
    with OllamaFalso(lento) as srv:
        w = _ventana(srv)
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        _elegir(w, 1)                                              # otra utilidad mientras la IA piensa
        suelta.set()
        _esperar(w, lambda: False, 1.0)
        assert w._diam_ia_sug(0) is None                            # el pedido cancelado no deja resultado
        assert w.btn_diam_ia_preguntar.isVisibleTo(w.gprop)         # la tarjeta de la 2.ª, sin pisar


def test_no_es_correcto_ensena():
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        w = _ventana(srv)
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        assert _esperar(w, lambda: w._diam_ia_pedido is None and w._diam_ia_sug(0) is not None)
        n = len(w._ia_memoria().registros("ensenanzas"))
        w.rechazar_diametro_ia()
        assert len(w._ia_memoria().registros("ensenanzas")) == n + 1
        assert not w.btn_diam_ia_usar.isVisibleTo(w.gprop)


def test_normativa_automatica_pendiente_aprobar_y_deshacer():
    p = _pipe()
    p["diam_plano"]["cerca"] = []
    p["tipo"] = "COLECTOR PRINCIPAL"
    with OllamaFalso(lambda c: _resp(None)) as srv:
        w = _ventana(srv, [p])
        w._diam_ia_auto = True
        _elegir(w, 0)
        assert _esperar(w, lambda: getattr(w, "_diam_ia_pedido", None) is None
                        and w._diam_ia_sug(0) is not None and "recorrido" in w.lbl_diam_ia.text())
        s = w._diam_ia_sug(0)
        assert s.origen == "normativa" and s.diam_in == 24
        assert "recorrido" in w.lbl_diam_ia.text() and "Criterio:" in w.lbl_diam_ia.text()
        assert "Fuente:" in w.lbl_diam_ia.text() and "Referencia:" in w.lbl_diam_ia.text()
        assert w.btn_diam_ia_detalles.isVisibleTo(w.gprop)
        assert w.pipes[0]["diam"] == 12 and not w.pipes[0].get("diam_elegido")
        assert srv.pedidos == []  # una regla inequívoca se resuelve localmente
        w.usar_diametro_ia()
        assert w.pipes[0]["diam"] == 24 and w.pipes[0]["diam_elegido"]
        w.undo()
        assert w.pipes[0]["diam"] == 12 and not w.pipes[0].get("diam_elegido")


def test_otro_diametro_y_cancelar(monkeypatch):
    from PySide6 import QtWidgets
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        w = _ventana(srv)
        _elegir(w, 0)
        w.preguntar_diametro_ia()
        assert _esperar(w, lambda: w._diam_ia_sug(0) is not None)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", lambda *a: (30.0, False))
        w.cambiar_diametro_ia()
        assert w.pipes[0]["diam"] == 12
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", lambda *a: (30.0, True))
        w.cambiar_diametro_ia()
        assert w.pipes[0]["diam"] == 30 and w.pipes[0]["diam_elegido"]
        w.undo()
        assert w.pipes[0]["diam"] == 12


def test_abrir_aviso_consulta_ia_sin_boton_y_no_repite():
    with OllamaFalso(lambda c: _resp("R1")) as srv:
        w = _ventana(srv)
        w._diam_ia_auto = True
        _elegir(w, 0)
        assert _esperar(w, lambda: getattr(w, "_diam_ia_pedido", None) is None
                        and w._diam_ia_sug(0) is not None)
        assert w._diam_ia_sug(0).diam_in == 18
        assert len(srv.pedidos) == 2
        w._diam_ia_refrescar()
        assert len(srv.pedidos) == 2
        assert w.pipes[0]["diam"] == 12


def test_analisis_muestra_captura_y_datos_sin_aplicar(monkeypatch):
    import base64
    import hashlib
    import fitz
    from types import SimpleNamespace
    from PySide6 import QtWidgets
    from ia.diametro_ia import Sugerencia
    w = _ventana(SimpleNamespace(url="http://127.0.0.1:9"))
    doc = fitz.open()
    doc.new_page(width=600,height=600)
    w.doc = doc
    w.pipes[0]["diam_plano"]["cerca"] = []
    w.pipes[0]["tipo"] = "COLECTOR PRINCIPAL"
    _elegir(w,0)
    f = w._diam_ia_ficha(0)
    imagen = w._diam_ia_imagen(0,f)
    assert imagen and base64.b64decode(imagen).startswith(b"\x89PNG")
    analisis = dict(entrada=f,opcion=f["normativa"][0],imagen_usada=True,
                    imagen_sha256=hashlib.sha256(imagen.encode()).hexdigest(),motivo_modelo="Interpretación del recorrido")
    s = Sugerencia(24,None,"media","Por su recorrido y función prevista.","","normativa",analisis)
    clave = w._diam_ia_clave(f)
    w._diam_ia[clave] = s
    w._diam_ia_evidencias[clave] = dict(imagen=imagen,ficha=f,modelo="modelo-prueba")
    w._diam_ia_refrescar()
    capturado=[]
    monkeypatch.setattr(QtWidgets.QDialog,"exec",lambda dlg:capturado.append(dlg) or 0)
    w.ver_analisis_diametro_ia()
    tabs=capturado[0].findChild(QtWidgets.QTabWidget)
    assert tabs.count()==4
    assert not tabs.widget(0).widget().pixmap().isNull()
    assert json.loads(tabs.widget(1).toPlainText())==f
    assert "Interpretación del recorrido" in tabs.widget(2).toPlainText()
    assert all(t in w.lbl_diam_ia.text() for t in ("Propuesta:","Por qué:","Criterio:","Fuente:","Referencia:"))
    assert w.pipes[0]["diam"]==12


def test_composicion_envia_y_muestra_originales_fuera_del_recorte(monkeypatch):
    import fitz
    from PySide6 import QtWidgets
    from test_contexto_original import _datos
    from hoja import composite as C
    fuentes,comp,pts=_datos(90)
    with OllamaFalso(lambda c:'{"opcion":"N1","motivo":"Propuesta basada en el contexto"}',capacidades=("completion","vision")) as srv:
        w=_ventana(srv)
        w.src_pdfs=fuentes
        w.composite=comp
        doc=fitz.open(stream=fuentes[0]["data"],filetype="pdf")
        w.doc=C.build_document(comp,[doc])
        w.pipes[0]["pts"]=pts
        w.pipes[0]["diam_plano"]["cerca"]=[]
        w.pipes[0]["tipo"]="COLECTOR PRINCIPAL"
        _elegir(w,0)
        w.preguntar_diametro_ia()
        assert _esperar(w,lambda:getattr(w,"_diam_ia_pedido",None) is None and w._diam_ia_sug(0) is not None)
        s=w._diam_ia_sug(0)
        assert s.analisis["capturas_originales"]
        assert "CONSTRUCTION NOTES" in json.dumps(s.analisis["entrada"])
        assert "PROJECT METRO" in json.dumps(s.analisis["entrada"])
        assert "hoja original" in w.lbl_diam_ia.text()
        assert len(srv.pedidos[0]["messages"][-1]["images"])>1
        capturado=[]
        monkeypatch.setattr(QtWidgets.QDialog,"exec",lambda dlg:capturado.append(dlg) or 0)
        w.ver_analisis_diametro_ia()
        tabs=capturado[0].findChild(QtWidgets.QTabWidget)
        assert any("Original" in tabs.tabText(k) for k in range(tabs.count()))
        assert tabs.tabText(tabs.count()-1)=="Texto completo de origen"
        assert "KEEP EXISTING PIPE" in tabs.widget(tabs.count()-1).toPlainText()
        assert w.pipes[0]["diam"]==12 and not w.pipes[0].get("diam_elegido")


def test_progreso_tardio_no_pisa_otra_seleccion():
    w = _ventana()
    w._diam_ia_pedido = (8,0,"clave")
    w._diam_ia_t0 = time.monotonic()
    w._diam_ia_progreso(8,"Analizando captura y recorrido")
    assert "Analizando captura" in w.lbl_diam_ia.text()
    anterior = w.lbl_diam_ia.text()
    w._diam_ia_progreso(7,"Comprobando la propuesta")
    assert w.lbl_diam_ia.text()==anterior
