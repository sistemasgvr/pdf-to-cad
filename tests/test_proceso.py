"""Trabajo en un proceso aparte (`ui.comun.proceso`, pedido del usuario 2026-10-14)."""
import os
import sys

import pytest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtCore, QtWidgets  # noqa: E402

from ui.comun import proceso  # noqa: E402


@pytest.fixture
def con_proceso(monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    t = proceso.Trabajador("prueba")
    yield t
    t.parar()


def test_el_trabajo_corre_en_otro_proceso_y_avisa_su_avance(con_proceso):
    vistos = []
    t = proceso.Tarea("ui.comun.proceso_hijo:eco", ("hola",), {"pasos": 3})
    t.avance.connect(vistos.append)
    out = {}
    lazo = QtCore.QEventLoop()
    t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    con_proceso.enviar(t)
    QtCore.QTimer.singleShot(60000, lazo.quit)
    lazo.exec()
    assert out["e"] == "" and out["r"][0] == "hola" and out["r"][1] != os.getpid()
    assert vistos == [(1, 3), (2, 3), (3, 3)]
    pid = out["r"][1]
    t2 = proceso.Tarea("ui.comun.proceso_hijo:eco", (2,))     # el trabajador se reusa
    t2.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    con_proceso.enviar(t2)
    lazo.exec()
    assert out["r"] == (2, pid)


def test_error_y_cancelar(con_proceso):
    out = {}
    lazo = QtCore.QEventLoop()
    t = proceso.Tarea("ui.comun.proceso_hijo:no_existe")
    t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    con_proceso.enviar(t)
    QtCore.QTimer.singleShot(60000, lazo.quit)
    lazo.exec()
    assert out["r"] is None and "no_existe" in out["e"]
    t2 = proceso.Tarea("ui.comun.proceso_hijo:eco", (1,), {"pasos": 0})
    t2.terminado.connect(lambda r, e: out.update(r2=r, e2=e))
    con_proceso.enviar(t2)
    t2.cancelar()
    assert out["e2"] == "cancelado" and out["r2"] is None


def test_caida_del_proceso_no_cierra_la_app_y_se_puede_reintentar(con_proceso):
    t = proceso.Tarea("ui.comun.proceso_hijo:eco", ("primero",))
    out = []
    lazo = QtCore.QEventLoop()
    t.terminado.connect(lambda r, e: (out.append((r, e)), lazo.quit()))
    con_proceso.enviar(t)
    con_proceso._proc.terminate()
    con_proceso._proc.join(5)
    timeout = QtCore.QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lazo.quit)
    timeout.start(15000)
    lazo.exec()
    assert len(out) == 1 and out[0][0] is None
    assert "Código de salida:" in out[0][1]
    nuevo = proceso.Tarea("ui.comun.proceso_hijo:eco", ("reintento",))
    nuevo.terminado.connect(lambda r, e: (out.append((r, e)), lazo.quit()))
    con_proceso.enviar(nuevo)
    timeout.start(15000)
    lazo.exec()
    timeout.stop()
    assert len(out) == 2 and out[1][1] == ""
    assert out[1][0][0] == "reintento"


def test_leyenda_corre_aislada_y_devuelve_error_recuperable(con_proceso):
    import fitz
    from ui.asistente.layer_info_panel import LegendWorker
    with fitz.open() as doc:
        doc.new_page().insert_text((30, 30), "Hoja sin leyenda")
        data = doc.tobytes()
    lazo = QtCore.QEventLoop()
    timeout = QtCore.QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lazo.quit)
    res, errores = [], []
    try:
        for contenido in (b"PDF invalido", data):
            worker = LegendWorker([{"name": "plano.pdf", "data": contenido}])
            worker.done.connect(res.append)
            worker.failed.connect(errores.append)
            worker.finished.connect(lazo.quit)
            worker.start()
            assert not worker.isRunning()  # no se usa un QThread con MuPDF dentro de la app
            timeout.start(15000)
            lazo.exec()
            assert worker._tarea is None
        assert len(errores) == 1 and "Traceback" in errores[0]
        assert res == [[{"name": "plano.pdf", "rows": [], "images": {}}]]
    finally:
        timeout.stop()
        proceso.trabajador("leyenda").parar()


def _vivo(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    try:
        return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def test_el_trabajador_no_queda_huerfano_si_la_ventana_muere(tmp_path):
    """Ventana cerrada de golpe (sin `aboutToQuit`): el trabajador esperaba trabajos para siempre con
    su memoria (2026-10-24). Ahora vigila a su padre y termina solo."""
    import subprocess
    import textwrap
    import time
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = tmp_path / "ventana.py"
    script.write_text(textwrap.dedent(f"""
        import os, sys
        sys.path[:0] = [{os.path.join(raiz, "app")!r}, {raiz!r}]
        os.environ["PDFCAD_PROCESO"] = "1"
        if __name__ == "__main__":
            from PySide6 import QtCore
            app = QtCore.QCoreApplication([])
            from ui.comun import proceso
            r, e = proceso.ejecutar("ui.comun.proceso_hijo:eco", 1)
            print(r[1], flush=True)
            os._exit(0)
    """), encoding="utf-8")
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180)
    pid = int(out.stdout.split()[-1])
    fin = time.time() + 30
    while _vivo(pid) and time.time() < fin:
        time.sleep(0.2)
    assert not _vivo(pid)
