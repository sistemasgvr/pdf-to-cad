"""Reiniciar la app cuando no responde, sin perder el avance (2026-11-21): el monitor cierra la ventana trabada y la
abre otra vez, que recupera SOLA la última copia automática de esa ventana."""
import json
import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import reinicio as R  # noqa: E402


def _copia(base, nombre, pid, fecha):
    d = os.path.join(base, nombre)
    os.makedirs(d)
    for f in ("model.json", "page.png"):
        open(os.path.join(d, f), "wb").write(b"x")
    json.dump({"version": 1, "sesion": nombre, "fecha": fecha, "pid": pid, "nombre": nombre},
              open(os.path.join(d, "meta.json"), "w"))


def test_la_copia_que_se_recupera_es_la_de_esa_ventana(tmp_path):
    base = str(tmp_path)
    _copia(base, "a", 111, 100.0)
    _copia(base, "b", 222, 200.0)             # más reciente, pero de OTRA ventana
    _copia(base, "c", 111, 150.0)
    assert R.ultima_copia(base, 111)["sesion"] == "c"
    assert R.ultima_copia(base, 999)["sesion"] == "b"      # sin copia propia: la más reciente
    assert R.ultima_copia(base)["sesion"] == "b"
    assert R.ultima_copia(str(tmp_path / "no_existe")) is None
    os.makedirs(os.path.join(base, "d"))                    # sin meta.json = a medias: no cuenta
    assert R.ultima_copia(base)["sesion"] == "b"


def test_el_comando_lleva_recuperar_y_el_pid():
    cmd = R.comando(1234)
    assert cmd[-2:] == ["--recuperar", "1234"] and cmd[0] == sys.executable
    assert cmd[1].endswith("main.py")


def test_reiniciar_cierra_la_ventana_trabada_y_abre_otra():
    colgada = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    obrero = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    lanzados = []
    try:
        assert R.vivo(colgada.pid)
        assert R.reiniciar(colgada.pid, [obrero.pid], lanzar=lanzados.append)
        assert not R.vivo(colgada.pid) and not R.vivo(obrero.pid)
        assert lanzados and lanzados[0][-2:] == ["--recuperar", str(colgada.pid)]
    finally:
        for p in (colgada, obrero):
            p.kill()


def test_no_abre_otra_encima_si_la_ventana_no_muere(monkeypatch):
    monkeypatch.setattr(R, "cerrar", lambda pids, excepto=(): list(pids))     # nada se pudo cerrar
    lanzados = []
    assert not R.reiniciar(4242, [], lanzar=lanzados.append) and not lanzados


def test_no_se_mata_a_si_mismo_ni_al_monitor():
    assert R.cerrar([os.getpid()]) == []                    # (no se toca: sigue vivo y no se reporta)
    assert R.vivo(os.getpid())


def test_la_app_reiniciada_recupera_sola_sin_preguntar(monkeypatch, tmp_path):
    from PySide6 import QtGui, QtWidgets
    from traduccion import i18n, i18n_core
    from ui.dialogos import dialogs
    from ui.ventana import autoguardado as A
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main

    def ventana():
        w = Main()
        img = QtGui.QImage(400, 300, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor(255, 255, 255))
        w.canvas.set_image(img)
        w._dirty = False
        return w

    w = ventana()
    w.autoguardado.iniciar()
    w.pipes.append({"layer": "DRENAJE", "pts": [(10, 10), (200, 10)], "name": "Antes de colgarse", "diam": 12.0})
    w._refresh_lists()
    w._dirty = True
    w.autoguardado.guardar_ahora()
    w.autoguardado.esperar()
    meta = json.load(open(os.path.join(w.autoguardado.dir, "meta.json")))
    assert meta["pid"] == os.getpid()                       # la copia dice de qué ventana es
    w.autoguardado._lock.unlock()                           # «murió» (el candado huérfano no estorba)
    w.autoguardado._lock = None
    w2 = ventana()
    monkeypatch.setattr(dialogs, "preguntar_recuperacion",
                        lambda *a, **k: pytest.fail("al reiniciar por falta de respuesta no se pregunta"))
    assert w2.iniciar_autoguardado(auto=meta["pid"])
    assert [p["name"] for p in w2.pipes] == ["Antes de colgarse"]
    for v in (w, w2):
        v._dirty = False
        v.close()
