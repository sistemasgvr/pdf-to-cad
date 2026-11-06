"""Dibujar accesorios (pedido del usuario 2026-11-06): «Dibujar → Accesorios» (codo, Tee, Wye, cruz). La forma que
se dibuja es la que produce ESE accesorio (`accesorios.accesorios`), validada; en la ventana: el botón con menú, el
clic sobre un accesorio que lo elige en el Inventario y sus propiedades en el panel derecho."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import accesorios as A  # noqa: E402
from nucleo import dibujar_accesorios as DA  # noqa: E402

FT = 0.1                                   # 0.1 ft por px


def _agua(pts, diam=8.0, **k):
    return dict(layer="AGUA", pts=list(pts), name="", diam=diam, pipe_size="x", inv_start=100.0, inv_end=99.0, **k)


def _accs(pipes):
    return A.accesorios(pipes, lambda i, k, x, y: __import__("nucleo.model_ops", fromlist=["x"]).z_en_tramo(
        pipes[i], k, x, y), FT)


def _dibuja(tipo, pipes, clic, cursor, angulo=None):
    base = (DA.punta if tipo == "codo" else DA.en_tramo)(pipes, [], *clic, FT, 20)
    assert base.ok, base.motivo
    pr = DA.propuesta(tipo, base, *cursor, pipes, FT, angulo=angulo)
    assert pr.ok, pr.motivo
    DA.aplicar(pipes, pr)
    return pr


@pytest.mark.parametrize("ang", DA.ANGULOS_CODO)
def test_codo_desde_la_punta_con_el_angulo_exacto(ang):
    pipes = [_agua([(0, 0), (1000, 0)])]
    _dibuja("codo", pipes, (998, 3), (1300, 400), ang)
    assert len(pipes) == 1 and len(pipes[0]["pts"]) == 3
    accs = _accs(pipes)
    assert len(accs) == 1 and accs[0]["tipo"] == "codo" and accs[0]["angulo"] == pytest.approx(ang, abs=1e-6)
    # la cota del vértice viejo sigue igual y el tramo nuevo baja lo justo para que el codo mida el ángulo en 3D (a 90°: a nivel)
    assert pipes[0]["vertex_inv_out"][1] == pytest.approx(99.0) and pipes[0]["inv_end"] <= 99.0


def test_codo_desde_el_inicio_corre_las_cotas():
    pipes = [_agua([(0, 0), (500, 0), (1000, 0)], vertex_inv_out={1: 99.7}, vertex_inv_in={1: 99.7})]
    _dibuja("codo", pipes, (2, 2), (-300, -300), 45.0)
    p = pipes[0]
    assert len(p["pts"]) == 4 and p["vertex_inv_out"][2] == pytest.approx(99.7)
    assert p["vertex_inv_out"][1] == pytest.approx(100.0)
    assert [a["tipo"] for a in _accs(pipes)] == ["codo"]


def test_codo_no_en_punta_ocupada_ni_en_gravedad_ni_tramo_corto():
    a, b = _agua([(0, 0), (1000, 0)]), _agua([(1000, 0), (1000, 500)])
    assert not DA.punta([a, b], [], 1000, 0, FT, 20).ok                    # ya llega otra: no es punta libre
    grav = dict(layer="ALCANTARILLADO", pts=[(0, 0), (1000, 0)], diam=8.0)
    base = DA.punta([grav], [], 1000, 0, FT, 20)
    assert not base.ok and "agua" in base.motivo
    corto = _agua([(0, 0), (500, 300), (515, 300)])                         # 1.5 ft desde un vértice
    assert not DA.punta([corto], [], 515, 300, FT, 20).ok


@pytest.mark.parametrize("tipo,esperado,ang", [("tee", "tee", 90.0), ("wye", "wye", 45.0), ("cruz", "cruz", 90.0)])
def test_tee_wye_cruz_sobre_un_tramo_recto(tipo, esperado, ang):
    pipes = [_agua([(0, 0), (1000, 0)])]
    pr = _dibuja(tipo, pipes, (500, 2), (700, 300))
    assert len(pipes) == 2 and pipes[1]["layer"] == "AGUA" and pipes[1]["diam"] == 8.0
    assert pipes[1]["inv_start"] == pytest.approx(99.5)                     # la cota del tramo en ese punto
    accs = _accs(pipes)
    assert [a["tipo"] for a in accs] == [esperado]
    assert accs[0]["angulo"] == pytest.approx(ang, abs=1e-6)
    assert (accs[0]["x"], accs[0]["y"]) == pytest.approx((500, 0))
    assert pr.largo_ft >= DA.largo_min_ft(8.0)


def test_lejos_de_vertices_otras_uniones_y_corto():
    pipes = [_agua([(0, 0), (1000, 0), (1000, 800)]), _agua([(300, 0), (300, 500)])]
    base = DA.en_tramo(pipes, [], 995, 2, FT, 20)                           # junto al codo: se corre
    assert base.ok and base.movida and (1000 - base.x) * FT >= 2 * 1.7 * 8 / 12 - 1e-6
    base = DA.en_tramo(pipes, [], 301, 1, FT, 20)                           # junto a la Tee: se corre
    assert base.ok and abs(base.x - 300) * FT >= 2 * 1.7 * 8 / 12 - 1e-6
    base = DA.en_tramo(pipes, [], 600, 0, FT, 20)
    pr = DA.propuesta("tee", base, 600, 5, pipes, FT)                        # cursor pegado: muy corto
    assert not pr.ok and "corto" in pr.motivo.lower()


def test_no_toca_otra_tuberia_de_la_misma_red_y_avisa_si_cruza_otra():
    pipes = [_agua([(0, 0), (1000, 0)]), _agua([(0, 200), (1000, 200)])]
    base = DA.en_tramo(pipes, [], 500, 0, FT, 20)
    pr = DA.propuesta("tee", base, 500, 400, pipes, FT)
    assert not pr.ok and "misma red" in pr.motivo
    otra = dict(layer="ELECTRICO", pts=[(0, 100), (1000, 100)], diam=4.0)
    pipes = [_agua([(0, 0), (1000, 0)]), otra]
    pr = DA.propuesta("tee", DA.en_tramo(pipes, [], 500, 0, FT, 20), 500, 300, pipes, FT)
    assert pr.ok and any("Cruza" in a for a in pr.avisos)


def test_la_normativa_avisa_pero_no_bloquea():
    from nucleo import normas_validar as NV
    from nucleo.normas_base import R
    from nucleo.normas_reglas import CODO
    cat = {"version": 2, "tipos": {}, "reglas": [R("AGUA", "", CODO, "angulo", valores=[45, 90])]}
    pipes = [_agua([(0, 0), (1000, 0)])]
    base = DA.punta(pipes, [], 1000, 0, FT, 20)
    pr = DA.propuesta("codo", base, 1300, 300, pipes, FT, angulo=22.5, normas=NV.activas(cat))
    assert pr.ok and any("Normativa" in a for a in pr.avisos)


def test_wye_hacia_atras_y_al_otro_lado():
    pipes = [_agua([(0, 0), (1000, 0)])]
    pr = _dibuja("wye", pipes, (500, 0), (300, -300))
    (x0, y0), (x1, y1) = pipes[1]["pts"]
    assert (x0, y0) == pytest.approx((500, 0)) and x1 < 500 and y1 < 0
    assert math.degrees(math.atan2(abs(y1 - y0), abs(x1 - x0))) == pytest.approx(45.0)
    assert pr.acc["ramal"] == 1


# ── en la ventana ──────────────────────────────────────────────────────────
@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.aviso_breve = lambda *a, **k: None
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0              # 0.1 ft por px
    w.pipes = [_agua([(100, 300), (900, 300)])]
    w._refresh_lists(); w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_boton_accesorios_con_menu(win):
    from PySide6 import QtWidgets
    from ui.ventana import ventana_dibujar_acc as VA
    b = win.herramientas.btn_accesorios
    assert b.text() == "Accesorios" and b.menu() is not None
    m = b.menu()
    VA.llenar_menu(win, m)
    textos = [a.text() for a in m.actions() if not isinstance(a, QtWidgets.QWidgetAction)]
    assert textos == ["Válvula", "Codo", "Tee · ramal a 90°", "Wye · ramal a 45°", "Cruz"]
    codo = next(a for a in m.actions() if a.text() == "Codo").menu()
    assert [a.text() for a in codo.actions()] == ["Codo de 11.25°", "Codo de 22.5°", "Codo de 45°", "Codo de 90°"]
    win.pipes = [dict(layer="ALCANTARILLADO", pts=[(0, 0), (500, 0)], diam=8.0)]
    VA.llenar_menu(win, m)
    assert not any(a.isEnabled() for a in m.actions() if not isinstance(a, QtWidgets.QWidgetAction))


def test_dibujar_tee_en_dos_clics_con_deshacer(win):
    win.dibujar_accesorio("tee")
    assert win.mode == "insert_acc"
    pasos = len(win._undo)
    win._pista_accesorio(500, 302)
    win._clic_accesorio(500, 302)                  # paso 1
    win._pista_accesorio(520, 600)
    assert win._pista_acc                          # vista previa
    win._clic_accesorio(520, 600)                  # paso 2
    assert len(win.pipes) == 2 and win.pipes[1]["pts"][0] == pytest.approx((500, 300))
    assert len(win._undo) == pasos + 1 and win.mode == "insert_acc"
    assert [a["tipo"] for a in win._accs_lista] == ["tee"]
    win._escape_accesorio()
    assert win.mode == "idle"
    win.undo()
    assert len(win.pipes) == 1


def test_codo_y_esc_vuelve_al_paso_1(win):
    win.dibujar_accesorio("codo", 45.0)
    win._clic_accesorio(898, 300)
    assert win._acc_dib["base"] is not None
    win._escape_accesorio()                         # vuelve al paso 1, sigue en el modo
    assert win.mode == "insert_acc" and win._acc_dib["base"] is None
    win._clic_accesorio(898, 300)
    win._clic_accesorio(1200, 500)
    assert len(win.pipes[0]["pts"]) == 3
    assert [a["tipo"] for a in win._accs_lista] == ["codo"]
    assert win._accs_lista[0]["angulo"] == pytest.approx(45.0, abs=1e-6)


def test_clic_en_un_accesorio_lo_elige_en_el_inventario_y_muestra_sus_propiedades(win):
    from nucleo.model import TAB_ACC
    ramal = _agua([(500, 300), (500, 800)], diam=6.0)
    ramal["inv_start"] = ramal["inv_end"] = 99.5           # a la cota de la principal en ese punto: Tee
    win.pipes.append(ramal)
    win._do_insert_valvula(250, 302)
    win._refresh_lists(); win._redraw()
    win.on_click(500, 301, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.LeftButton)
    assert win._current_tab() == TAB_ACC
    f = win._fila_acc_elegida()
    assert f is not None and f.clase == "acc" and f.tipo == "tee"
    assert not win.gprop_acc.isHidden()
    assert win._acc_campos["tipo"][1].text() == "Tee"
    assert '8" × 6"' in win._acc_campos["diam"][1].text()
    assert win.acc_union.isHidden() and not win.chk_acc_poner.isHidden()
    # la válvula: unión y material editables (un paso de deshacer cada uno)
    x, y = win._valv_lugares[0].x, win._valv_lugares[0].y
    win.on_click(x, y, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.LeftButton)
    f = win._fila_acc_elegida()
    assert f is not None and f.clase == "valv"
    assert not win.acc_union.isHidden()
    win.acc_union.setCurrentIndex(win.acc_union.findData("RG"))
    assert win.valvulas[0]["union"] == "RG"
    assert win._fila_acc_elegida() is not None and win._fila_acc_elegida().clase == "valv"   # sigue elegida
    win.acc_material.setCurrentIndex(win.acc_material.findData("PVC"))
    assert win.valvulas[0]["material"] == "PVC"
    # «Poner este accesorio» apagado = «No hay T»
    win.on_click(500, 301, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.LeftButton)
    win.chk_acc_poner.setChecked(False)
    assert len(win.sin_accesorio) == 1 and win.sin_accesorio[0]["tipo"] == "tee"


def test_accesorio_elegido_se_resalta_y_la_lista_va_en_orden_alfabetico(win):
    from PySide6 import QtCore
    from ui.ventana.ventana_lista_accesorios import orden_alfabetico
    ramal = _agua([(500, 300), (500, 800)], diam=6.0)
    ramal["inv_start"] = ramal["inv_end"] = 99.5
    win.pipes.append(ramal)
    win.pipes[0]["pts"].append((900, 900))           # un codo en (900, 300)
    win.pipes[0]["inv_start"] = win.pipes[0]["inv_end"] = 99.5
    win._do_insert_valvula(250, 302)
    win._refresh_lists(); win._redraw()
    win.on_click(500, 301, QtCore.Qt.LeftButton)
    assert win._acc_resalte                           # tuberías que une, más gruesas + anillo
    assert all(it.scene() is win.canvas.scene() for it in win._acc_resalte)
    win._redraw()
    assert all(it.scene() is win.canvas.scene() for it in win._acc_resalte)   # sigue tras redibujar
    win._on_escape()
    assert not win._acc_resalte
    textos = [f.texto for f in win._acc_filas]
    assert [t.split(" ")[0] for t in textos] == ["Codo", "Tee", "Válvula"]
    assert sorted(["Válvula 8\"", "Tee", "codo 90°", "Codo 11.25°", "#10", "#2"], key=orden_alfabetico) == \
        ["#2", "#10", "Codo 11.25°", "codo 90°", "Tee", "Válvula 8\""]
