import os
import sys
import threading
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6 import QtCore, QtWidgets
from ui.comun import errores, workers, proceso
from nucleo import diagnostico


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_excepcion_qt_y_de_hilo_se_registran_y_muestran_sin_salir(app, monkeypatch, tmp_path):
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    vistos = []
    monkeypatch.setattr(errores.GestorErrores, "_mostrar", lambda self, r, d: vistos.append((r, d)))
    gestor = errores.instalar(app)
    try:
        boton = QtWidgets.QPushButton()
        def fallar():
            raise ValueError("fallo de prueba en capas")
        boton.clicked.connect(fallar)
        boton.click()  # PySide llama sys.excepthook y conserva el bucle de eventos
        def fallar_en_hilo():                     # otro lugar: el MISMO error se avisa una sola vez (2026-11-16)
            raise ValueError("fallo de prueba en capas")
        hilo = threading.Thread(target=fallar_en_hilo)
        hilo.start()
        hilo.join()
        app.processEvents()
        assert len(vistos) == 2
        assert all("ValueError: fallo de prueba en capas" in r for r, _d in vistos)
        assert "fallar" in (tmp_path / f"sesion-{os.getpid()}.log").read_text(encoding="utf-8")
        # El mismo bucle sigue atendiendo acciones después de ambos errores.
        QtCore.QTimer.singleShot(0, lambda: vistos.append("sigue vivo"))
        app.processEvents()
        assert vistos[-1] == "sigue vivo"
    finally:
        del app._gestor_errores
        gestor.deleteLater()


def test_el_mismo_error_repetido_se_avisa_una_vez_y_no_en_bucle(app, monkeypatch, tmp_path):
    """Reporte del cliente 2026-11-16: un error al dibujar la Vista 3D salía en cada cuadro y el aviso volvía a
    aparecer al cerrarlo, en bucle. El mismo error (tipo + lugar) se avisa UNA vez; los demás solo se cuentan."""
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    vistos = []
    monkeypatch.setattr(errores.GestorErrores, "_mostrar", lambda self, r, d: vistos.append(r))
    gestor = errores.instalar(app)
    try:
        boton = QtWidgets.QPushButton()

        def pintar():
            raise OverflowError("int too big to convert")
        boton.clicked.connect(pintar)
        for _ in range(50):                       # como un repintado que falla en cada cuadro
            boton.click()
        app.processEvents()
        assert vistos == ["OverflowError: int too big to convert"]
        log = (tmp_path / f"sesion-{os.getpid()}.log").read_text(encoding="utf-8")
        assert log.count("Excepción no controlada") == errores.REPETICIONES_REGISTRADAS   # no 50 entradas
        assert "(repetición 2)" in log
    finally:
        del app._gestor_errores
        gestor.deleteLater()


def test_donde_paso_el_error_segun_la_pila():
    pila = 'Traceback (most recent call last):\n  File "D:\\app\\ui\\comun\\visor3d.py", line 222, in _subir\nOverflowError'
    assert errores._donde(pila) == "la Vista 3D"
    assert errores._donde("Traceback\n  File \"x\\otra_cosa.py\", line 1\nValueError") == ""


def test_registro_sin_permiso_no_oculta_error_original(monkeypatch):
    monkeypatch.setattr(os, "makedirs", lambda *a, **kw: (_ for _ in ()).throw(PermissionError()))
    assert diagnostico.registrar("original") is None


def test_resumen_del_error_muestra_la_causa_y_no_la_cabecera_traceback():
    assert diagnostico.resumen("Traceback (most recent call last):\n  línea\nValueError: capa inválida\n") == "ValueError: capa inválida"
    assert diagnostico.resumen("El proceso se detuvo\nCódigo: 0xC0000005") == "El proceso se detuvo"


def test_seleccion_vacia_y_reconstruccion_del_arbol_no_ejecutan_slots_con_filas_borradas(app):
    import fitz
    from ui.asistente.layer_dialog import SheetLayersDialog
    doc = fitz.open()
    page = doc.new_page()
    page.draw_line((20, 20), (100, 20), color=(1, 0, 0))
    dlg = SheetLayersDialog(None, doc, 0)
    try:
        dlg._focus_style(None)  # traceback enviado por el usuario
        fila = next(dlg._layer_items())
        dlg.tree.setCurrentItem(fila)
        assert dlg._assignment_name
        cambios = []
        dlg.tree.currentItemChanged.connect(lambda *a: cambios.append(a))
        dlg._fill_list()
        assert not cambios
        assert dlg.tree.currentItem() is None
        assert dlg._assignment_name is None and not dlg.assignment_utility.isEnabled()
        dlg.tree.setCurrentItem(next(dlg._layer_items()))
        assert dlg._assignment_name  # se puede seleccionar de nuevo
    finally:
        dlg.reject()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


def test_error_paralelo_cancela_una_vez_y_conserva_causa(app):
    w = workers.RecognitionWorker("no.pdf", 0, utilities=("AGUA", "DRENAJE"))
    w._partes = [None, None]
    class Tarea:
        hecha = False
        def cancelar(self):
            self.hecha = True
            w._fin_parte(1, None, "cancelado")
    w._tareas = [Tarea(), Tarea()]
    vistos = []
    w.done.connect(lambda r, e: vistos.append((r, e)))
    w._fin_parte(0, None, "violación de acceso")
    assert vistos == [(None, "violación de acceso")]
    assert all(t.hecha for t in w._tareas)


def test_caida_nativa_del_hijo_informa_codigo_real_y_no_memoria(app, monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    w = proceso.Trabajador("fallo")
    t = proceso.Tarea("reconocimiento:capas")
    t.id = 1
    w._actual = t
    w._proc = SimpleNamespace(exitcode=-1073741819, pid=123, is_alive=lambda: False)
    monkeypatch.setattr(w, "_mensajes", lambda: iter(()))
    monkeypatch.setattr(w, "_matar", lambda: setattr(w, "_proc", None))
    vistos = []
    t.terminado.connect(lambda r, e: vistos.append((r, e)))
    w._sondear()
    assert t.hecha and w._actual is None
    assert len(vistos) == 1 and "0xC0000005" in vistos[0][1]
    assert "reconocimiento:capas" in vistos[0][1]


def test_error_al_arrancar_proceso_termina_tarea(app, monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    w = proceso.Trabajador("arranque")
    def fallar():
        raise OSError("no se pudo crear el proceso")
    monkeypatch.setattr(w, "_arrancar", fallar)
    t = proceso.Tarea("no:importa")
    vistos = []
    t.terminado.connect(lambda r, e: vistos.append(e))
    w.enviar(t)
    assert t.hecha and w._actual is None and not w._timer.isActive()
    assert len(vistos) == 1 and "no se pudo crear el proceso" in vistos[0]
