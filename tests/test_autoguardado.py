"""Autoguardado y recuperación (autoguardado.py; pedido del usuario 2026-10-05):
copia periódica de los cambios sin guardar, que se ofrece al abrir la app si la
sesión anterior se cerró de golpe, y se borra al guardar, descartar o cerrar bien."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui, QtWidgets  # noqa: E402

import autoguardado as A  # noqa: E402


def _ventana(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import i18n
    import i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    i18n_core._current_lang = "es"
    from app_window import Main
    w = Main()
    img = QtGui.QImage(400, 300, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w._dirty = False
    app.processEvents()
    return app, w


def _cambio(w, nombre="Linea Norte"):
    w.pipes.append({"layer": "DRENAJE", "pts": [(10, 10), (200, 10)], "name": nombre, "diam": 12.0})
    w._refresh_lists()
    w._dirty = True


@pytest.fixture
def win(monkeypatch):
    app, w = _ventana(monkeypatch)
    yield w
    w._dirty = False
    w.close()
    import gc; gc.collect()


def test_copia_solo_con_cambios_reales(win):
    ag = win.autoguardado
    ag.iniciar()
    assert not ag.guardar_ahora()                       # sin cambios: nada que copiar
    _cambio(win)
    assert ag.guardar_ahora() and ag.esperar()
    for parte in ("model.json", "page.png", "meta.json"):
        assert os.path.isfile(os.path.join(ag.dir, parte))
    meta = json.load(open(os.path.join(ag.dir, "meta.json"), encoding="utf-8"))
    assert meta["utilidades"] == 1 and meta["sesion"] == ag.sesion
    assert not ag.guardar_ahora()                       # mismo contenido: no se repite
    png = os.path.getmtime(os.path.join(ag.dir, "page.png"))
    _cambio(win, "Otra")
    assert ag.guardar_ahora() and ag.esperar()
    datos = json.load(open(os.path.join(ag.dir, "model.json"), encoding="utf-8"))
    assert [p["name"] for p in datos["pipes"]] == ["Linea Norte", "Otra"]
    assert os.path.getmtime(os.path.join(ag.dir, "page.png")) == png   # lo pesado no se reescribe


def test_no_se_ofrece_la_copia_de_una_ventana_abierta(win):
    ag = win.autoguardado
    ag.iniciar(); _cambio(win)
    ag.guardar_ahora(); ag.esperar()
    assert A.recuperables(ag.base) == []                # su lock está tomado


def test_guardar_o_cerrar_borra_la_copia(win, tmp_path):
    ag = win.autoguardado
    ag.iniciar(); _cambio(win)
    ag.guardar_ahora(); ag.esperar()
    win._write_project(str(tmp_path / "p.digproj"))
    assert not os.path.exists(ag.dir)
    _cambio(win, "nuevo")
    ag.guardar_ahora(); ag.esperar()
    assert os.path.isdir(ag.dir)
    win._dirty = False                                  # p.ej. «No guardar» al cerrar
    win.close()
    assert not os.path.exists(ag.dir) and not ag.activo


def test_cierre_de_golpe_se_recupera(monkeypatch, tmp_path):
    app, w = _ventana(monkeypatch)
    w.project_path = str(tmp_path / "mi_proyecto.digproj")
    w.autoguardado.iniciar()
    _cambio(w, "Sin guardar")
    w.autoguardado.guardar_ahora(); w.autoguardado.esperar()
    w.autoguardado._lock.unlock()                       # el proceso «murió»: lock huérfano
    w.autoguardado._lock = None
    copias = A.recuperables(w.autoguardado.base)
    assert len(copias) == 1 and copias[0]["nombre"] == "mi_proyecto.digproj"
    # Al abrir otra vez la app se ofrece y se recupera.
    app, w2 = _ventana(monkeypatch)
    import dialogs
    monkeypatch.setattr(dialogs, "preguntar_recuperacion", lambda *a, **k: "recuperar")
    assert w2.iniciar_autoguardado()
    assert [p["name"] for p in w2.pipes] == ["Sin guardar"]
    assert w2.project_path == str(tmp_path / "mi_proyecto.digproj")   # Ctrl+S va al original
    assert w2._has_real_changes()                                       # sigue sin guardar
    assert A.recuperables(w2.autoguardado.base) == []                   # la copia vieja se usó
    for v in (w, w2):
        v._dirty = False; v.close()


def test_descartar_y_mas_tarde(monkeypatch):
    app, w = _ventana(monkeypatch)
    w.autoguardado.iniciar(); _cambio(w)
    w.autoguardado.guardar_ahora(); w.autoguardado.esperar()
    w.autoguardado._lock.unlock(); w.autoguardado._lock = None
    import dialogs
    app, w2 = _ventana(monkeypatch)
    monkeypatch.setattr(dialogs, "preguntar_recuperacion", lambda *a, **k: "despues")
    assert not w2.iniciar_autoguardado() and len(A.recuperables(w2.autoguardado.base)) == 1
    app, w3 = _ventana(monkeypatch)
    monkeypatch.setattr(dialogs, "preguntar_recuperacion", lambda *a, **k: "descartar")
    assert not w3.iniciar_autoguardado() and A.recuperables(w3.autoguardado.base) == []
    for v in (w, w2, w3):
        v._dirty = False; v.close()


def test_pdf_de_trabajo_se_copia_una_vez(win, tmp_path):
    pdf = tmp_path / "plano.pdf"
    pdf.write_bytes(b"%PDF-1.4 prueba")
    win.pdf_path = str(pdf)
    ag = win.autoguardado
    ag.iniciar(); _cambio(win)
    ag.guardar_ahora(); ag.esperar()
    dst = os.path.join(ag.dir, "source.pdf")
    assert open(dst, "rb").read() == b"%PDF-1.4 prueba"
    t0 = os.path.getmtime(dst)
    _cambio(win, "otra")
    ag.guardar_ahora(); ag.esperar()
    assert os.path.getmtime(dst) == t0                  # sin cambios en el PDF: no se copia otra vez
    win.pdf_path = None
    _cambio(win, "sin pdf")
    ag.guardar_ahora(); ag.esperar()
    assert not os.path.exists(dst)                      # la copia refleja el estado actual
