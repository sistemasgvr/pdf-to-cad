"""Monitor de rendimiento (`ui/monitor`, pedido del usuario 2026-11-20): lee la sesión del vigilante en vivo, en
su propio proceso, y sabe si la ventana responde AHORA por su latido compartido."""
import json
import os
import sys
import time

import pytest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import vigilante as V, vigilante_vivo as VV  # noqa: E402


def _linea(ruta, **e):
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(e) + "\n")


def _sesion(tmp_path):
    d = tmp_path / "sesion"
    d.mkdir()
    t = time.time() - 60
    v, w = str(d / "proc-100.jsonl"), str(d / "proc-200.jsonl")
    _linea(v, t=t, tipo="inicio", pid=100, proc="ventana", hilo="MainThread", nombre="ventana")
    _linea(w, t=t + 1, tipo="inicio", pid=200, proc="pdfcad-principal", hilo="MainThread", nombre="pdfcad-principal")
    _linea(v, t=t + 2, tipo="sistema", pid=100, ram_total_mb=16000, ram_libre_mb=8000,
           procesos=[{"pid": 100, "priv_mb": 300, "cpu_pct": 5}, {"pid": 200, "priv_mb": 900, "cpu_pct": 95}])
    _linea(w, t=t + 3, tipo="trabajo_inicio", pid=200, hilo="MainThread",
           objetivo="reconocimiento.recognition_trabajo:reconocer_hoja")
    _linea(w, t=t + 4, tipo="etapa_inicio", pid=200, hilo="MainThread", texto="Leyendo los vectores de la hoja…")
    _linea(v, t=t + 5, tipo="congelamiento", pid=100, hilo="vigilante-guardia", dur=1.8, no_responde=False,
           carga="Armando la hoja compuesta…", etapa="", bloques=[], fuente="volcados",
           perfil={"muestras": 6, "propio": [["pymupdf.mupdf:fz_run_page", 1.7]],
                   "total": [["ui.ventana.app_window:Main._load_page", 1.8], ["pymupdf.mupdf:fz_run_page", 1.7]]})
    return d, v, w, t


def test_lee_en_vivo_con_lineas_a_medias(tmp_path):
    d, v, w, t = _sesion(tmp_path)
    ses = VV.Sesion(str(d))
    assert ses.actualizar() == 6
    assert len(ses.sucesos) == 5                       # el «sistema» no va a `sucesos` (va a la serie)
    p = ses.procesos[200]
    assert p.trabajo[0].endswith(":reconocer_hoja") and p.etapa[0].startswith("Leyendo")
    assert ses.pid_ventana == 100 and ses.serie[-1][1] == 1200
    with open(w, "a", encoding="utf-8") as f:          # una línea a medias: se espera a que se complete
        f.write('{"t": %s, "tipo": "trabajo", "pid": 200, "hilo": "MainThread", "objetivo": "x:y", ' % (t + 9))
    assert ses.actualizar() == 0
    with open(w, "a", encoding="utf-8") as f:
        f.write('"dur": 6.0}\n')
    assert ses.actualizar() == 1
    assert ses.procesos[200].trabajo is None and ses.procesos[200].trabajos == 1


def test_estado_de_la_ventana_por_su_latido(tmp_path):
    d, *_ = _sesion(tmp_path)
    ses = VV.Sesion(str(d))
    ses.actualizar()
    assert ses.ventana()[0] == VV.SIN_DATO
    lat = V.Latido(str(d / "latido-100.bin"))
    try:
        ahora = time.time()
        lat.escribir(ahora)
        assert ses.ventana(ahora + 0.1)[0] == VV.RESPONDE
        assert ses.ventana(ahora + 1.0)[0] == VV.OCUPADA
        estado, s = ses.ventana(ahora + 7.0)
        assert estado == VV.NO_RESPONDE and s == pytest.approx(7.0, abs=0.01)
        lat.escribir(-1.0)
        assert ses.ventana()[0] == VV.CERRADA
    finally:
        lat.cerrar()


def test_la_ventana_del_monitor_muestra_la_sesion(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from ui.monitor import monitor_ventana as MV
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    d, *_ = _sesion(tmp_path)
    monkeypatch.setattr(V, "base", lambda: str(tmp_path))
    w = MV.Monitor(str(d))
    try:
        assert w.p_ahora.tabla.model().rowCount() == 2
        assert w.p_congela.tabla.model().rowCount() == 1
        assert w.p_trabajos.tabla.model().rowCount() == 1       # el que está en curso
        assert w.c_congela.valor.text() == "1"
        w.p_congela.tabla.selectRow(0)
        assert w.p_congela.perfil.tabla.model().rowCount() == 2
        assert "Armando la hoja compuesta" in w.p_congela.perfil.lbl.text()
        assert w.lbl_estado.text()                               # sin latido: «Sin datos de la ventana»
    finally:
        w.close()
        w.deleteLater()


def test_el_monitor_corre_en_otro_proceso_y_uno_a_la_vez(tmp_path, monkeypatch):
    from ui.monitor import lanzar
    d, *_ = _sesion(tmp_path)
    monkeypatch.setattr(V, "base", lambda: str(tmp_path))
    assert lanzar.abrir(str(d))
    try:
        assert lanzar.abierto() and lanzar._proc["p"].pid != os.getpid()
        assert not lanzar.abrir(str(d))
        time.sleep(3)
        assert lanzar.abierto(), "el monitor se cerró solo"
    finally:
        lanzar._proc["p"].terminate()
        lanzar._proc["p"].join(10)
