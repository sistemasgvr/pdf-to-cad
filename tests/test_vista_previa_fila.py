"""👁 de una fila del panel «Reconocer» + sus «Para verificar» guardados (plan 2026-11-16, Tarea 7).

Ventana real (Qt offscreen) sobre DU06 h.3 (índice 2), como `test_reconocer_fila`; el diálogo no se muestra: `exec`
se cambia por un espía que anota lo que mostraría y devuelve la acción elegida."""
import copy
import json
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
from PySide6 import QtWidgets  # noqa: E402

from nucleo import reconocer_estado as RE  # noqa: E402
from reconocimiento import lectura_retenida as LR  # noqa: E402
from ui.comun import proceso  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
HOJA = 2
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
SELLOS = ("reconocida", "reconocida_idx", "reconocida_firma")


@pytest.fixture
def win(monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    w = app_window.Main()
    w._open_pdf_path(str(DU06))
    w._load_page(HOJA)
    LR.soltar()
    yield w
    tr = proceso._TRABAJADORES.get(proceso.RETENEDOR)
    hilo = getattr(tr, "_hilo", None) if tr is not None else None
    while hilo is not None and hilo.is_alive():
        app.processEvents()
        time.sleep(0.05)
    LR.soltar()
    w._dirty = False
    w.close()
    app.processEvents()


def _esperar(cond, s=600):
    fin = time.time() + s
    while not cond():
        QtWidgets.QApplication.instance().processEvents()
        time.sleep(0.02)
        assert time.time() < fin, "tiempo agotado"


def _listo(w, *partes):
    e = RE.nuevo()
    for p, f in e.filas.items():
        f.estado = "pendiente" if p in partes else "bloqueada"
    w.reconocer_estado = e
    w._refrescar_panel_reconocer()
    return e


def _foto(lista):
    return json.dumps([{k: v for k, v in d.items() if k not in SELLOS} for d in lista], sort_keys=True, default=repr)


@pytest.fixture
def espia(monkeypatch):
    """`RecognitionPreviewDialog.exec` anota lo que mostraría y devuelve `espia.accion`."""
    from ui.asistente import recognition_dialog as rd
    s = type("Espia", (), {})()
    s.dialogos, s.accion = [], rd.PREVIEW_CANCEL

    def exec_(self):
        s.dialogos.append(self)
        s.visto = {"editor": self._editor, "ok": self.btn_ok.text(),
                   "pasos": self.steps.isVisibleTo(self), "atras": self.btn_atras.isVisibleTo(self),
                   "filas": len(self.review_panel.review_rows), "quiebres": repr(self._curvas_quiebres()),
                   "resumen": repr([(c.text() if hasattr(c, "text") else "")
                                    for c in self.summary.findChildren(QtWidgets.QLabel)])}
        self.action = s.accion
        return QtWidgets.QDialog.Accepted
    monkeypatch.setattr(rd.RecognitionPreviewDialog, "exec", exec_)
    s.rd = rd
    return s


@needs_pdf
def test_ojo_sin_resultado_reconoce_sin_importar_y_abre_la_vista(win, espia):
    e = _listo(win, "AGUA")
    pasos = len(win._undo)
    win.ver_parte("AGUA")
    _esperar(lambda: espia.dialogos)
    assert win.pipes == [] and len(win._undo) == pasos       # nada entró al editor
    assert e.filas["AGUA"].estado == "pendiente"              # la fila quedó como estaba
    assert espia.visto["editor"] and espia.visto["ok"] == "Importar"
    assert not espia.visto["pasos"] and not espia.visto["atras"]
    # con el resultado ya en la caché, el siguiente 👁 no pide otro trabajo
    espia.dialogos.clear()
    win.ver_parte("AGUA")
    assert win._rec_actual is None and len(espia.dialogos) == 1


@needs_pdf
def test_la_vista_muestra_lo_mismo_que_la_del_asistente(win, espia):
    from ui.asistente import recognition_dialog as rd
    _listo(win, "AGUA")
    win.ver_parte("AGUA")
    _esperar(lambda: espia.dialogos)
    dlg = espia.dialogos[0]
    viejo = rd.RecognitionPreviewDialog(win, win.canvas.pixmap_item.pixmap().toImage(), dlg._results,
                                        page_count=win.doc.page_count,
                                        fondo={"escala": win.canvas.fondo_escala, "tam": win.canvas.tam_hoja(),
                                               "zoom": win.zoom, "pagina": win._pagina_fondo})
    assert not viejo._editor and viejo.steps.isVisibleTo(viejo)    # el asistente de siempre conserva sus pasos
    assert viejo.btn_ok.text() == "Continuar e importar al editor" and viejo.btn_atras.isVisibleTo(viejo)
    assert len(viejo.review_panel.review_rows) == espia.visto["filas"]
    assert repr(viejo._curvas_quiebres()) == espia.visto["quiebres"]
    assert repr([c.text() for c in viejo.summary.findChildren(QtWidgets.QLabel)]) == espia.visto["resumen"]
    viejo.deleteLater()


@needs_pdf
def test_importar_desde_el_ojo_es_lo_mismo_que_el_play(win, espia):
    e = _listo(win, "AGUA")
    win.reconocer_parte("AGUA")
    _esperar(lambda: win._rec_actual is None)
    play = (_foto(win.pipes), _foto(win.structures), e.filas["AGUA"].hechos, e.filas["AGUA"].firma,
            json.dumps(e.filas["AGUA"].verificar, sort_keys=True))
    win._reset_model()
    e = _listo(win, "AGUA")
    espia.accion = espia.rd.PREVIEW_IMPORT
    win.ver_parte("AGUA")                                    # (el reinicio vació la caché: reconoce y abre la vista)
    _esperar(lambda: e.filas["AGUA"].estado == "reconocida")
    assert (_foto(win.pipes), _foto(win.structures), e.filas["AGUA"].hechos, e.filas["AGUA"].firma,
            json.dumps(e.filas["AGUA"].verificar, sort_keys=True)) == play
    assert e.filas["AGUA"].estado == "reconocida"


@needs_pdf
def test_cancelar_la_vista_no_toca_el_editor(win, espia):
    e = _listo(win, "AGUA")
    win.ver_parte("AGUA")
    _esperar(lambda: espia.dialogos)
    assert win.pipes == [] and e.filas["AGUA"].estado == "pendiente"


@needs_pdf
def test_ajustar_capas_de_la_vista_abre_capas_y_estilos_de_esa_utilidad(win, espia, monkeypatch):
    _listo(win, "AGUA")
    pedidos = []
    monkeypatch.setattr(win, "abrir_capas_estilos", lambda parte=None: pedidos.append(parte))
    espia.accion = espia.rd.PREVIEW_ADJUST_LAYERS
    win.ver_parte("AGUA")
    _esperar(lambda: pedidos)
    assert pedidos == ["AGUA"]


@needs_pdf
def test_tramos_sueltos_de_la_vista_quedan_en_la_fila(win, espia, monkeypatch):
    e = _listo(win, "AGUA")
    firma_unida = win._firma_parte_actual("AGUA")
    from ui.asistente import recognition_dialog as rd
    orig = rd.RecognitionPreviewDialog.exec

    def exec_sueltos(self):
        self.chk_routes.setChecked(False)
        return orig(self)
    monkeypatch.setattr(rd.RecognitionPreviewDialog, "exec", exec_sueltos)
    win.ver_parte("AGUA")
    _esperar(lambda: espia.dialogos)
    assert e.filas["AGUA"].unir_tramos is False
    assert win._firma_parte_actual("AGUA") != firma_unida


def test_por_verificar_se_recorren_desde_el_panel_y_se_guardan(win, monkeypatch):
    from ui.ventana import ventana_reconocer_cola as cola
    items = [{"texto": "Curva sin cerrar", "etiqueta": "Curvas", "nivel": "review", "rect": [10.0, 20.0, 30.0, 40.0]},
             {"texto": "Otra", "etiqueta": "Otra", "nivel": "review", "rect": None}]
    monkeypatch.setattr(cola, "_verificar", lambda parte, res: copy.deepcopy(items))
    e = _listo(win, "AGUA")
    win.importar_parte = lambda *a, **k: 0                   # la importación no es lo que se prueba
    win._rec_aplicar("AGUA", [], False, "F", "FP")
    f = e.filas["AGUA"]
    assert [v["texto"] for v in f.verificar] == ["Curva sin cerrar", "Otra"]        # siguen tras importar
    p = win.panel_reconocer
    p.abrir_verificar(None)
    assert p.caja_verificar.isVisibleTo(p) or p.caja_verificar.layout().count() >= 3
    marcas = []
    monkeypatch.setattr(win, "_marcar_lugar", lambda x, y: marcas.append((x, y)))
    win._verificar_ir("AGUA", 0)
    assert marcas == [(20.0, 30.0)] and f.verificar[0]["visto"] is True
    win._verificar_visto("AGUA", 1, True)
    e2 = RE.de_dict(json.loads(json.dumps(RE.a_dict(e))))
    assert [bool(v.get("visto")) for v in e2.filas["AGUA"].verificar] == [True, True]
    assert e2.filas["AGUA"].verificar[0]["rect"] == [10.0, 20.0, 30.0, 40.0]


def test_ojo_de_valvulas_muestra_sus_por_verificar_en_el_panel(win):
    e = _listo(win, "AGUA", "VALVULAS")
    e.filas["VALVULAS"].estado = "reconocida"
    e.filas["VALVULAS"].verificar = [{"texto": "Válvula dudosa", "nivel": "review", "rect": None}]
    avisos = []
    win._aviso_reconocer = avisos.append
    win._refrescar_panel_reconocer()
    win.ver_parte("VALVULAS")
    assert win.panel_reconocer._filtro_verificar == "VALVULAS"
    assert win.panel_reconocer.caja_verificar.layout().count() == 2          # su título y su punto
    win.ver_parte("ROTULOS")
    assert avisos                                                           # sin nada por verificar: lo dice


@needs_pdf
def test_play_despues_de_la_vista_previa_no_reconoce_otra_vez(win, espia, monkeypatch):
    """Pedido 2026-11-17: lo que reconoció la vista previa sirve al ▶ (Cancelar en la vista y luego ▶)."""
    e = _listo(win, "AGUA")
    win.ver_parte("AGUA")
    _esperar(lambda: espia.dialogos)
    _esperar(lambda: win._rec_actual is None)
    tareas = []
    orig = proceso.Tarea
    monkeypatch.setattr(proceso, "Tarea", lambda *a, **k: tareas.append(a) or orig(*a, **k))
    win.reconocer_parte("AGUA")
    _esperar(lambda: e.filas["AGUA"].estado == "reconocida")
    assert tareas == [] and win.pipes
