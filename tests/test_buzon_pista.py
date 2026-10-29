"""Buzón (pedido del usuario 2026-10-28): donde no se puede, dice POR QUÉ; donde sí, el círculo verde muestra
el punto SOBRE la línea y el buzón queda ahí (no donde estaba el cursor)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.mensajes = []
    w._info = lambda m, *a, **k: w.mensajes.append(m)
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_buzon_se_pega_a_la_linea_y_dice_por_que_no(win):
    win.pipes = [dict(layer="ALCANTARILLADO", pts=[(0.0, 0.0), (300.0, 0.0)], diam=8.0),
                 dict(layer="AGUA", pts=[(0.0, 200.0), (300.0, 200.0)], diam=8.0)]
    win._rebuild_structures()
    win.set_mode("insert_bz")
    # junto a la de gravedad: pista verde EN la línea
    win._pista_buzon(100.0, 4.0)
    it = win._pista_bz
    assert it is not None and (it.pos().x(), it.pos().y()) == (100.0, 0.0)
    # junto a la de presión: sin pista, con el motivo
    win._pista_buzon(100.0, 203.0)
    assert win._pista_bz is None and "presión" in win.mensajes[-1]
    # clic lejos: no inserta, dice por qué y sigue en el modo
    win._do_insert_manhole(100.0, 100.0)
    assert win.mode == "insert_bz" and len(win.pipes[0]["pts"]) == 2 and "Acércate" in win.mensajes[-1]
    # clic junto a la de gravedad: el vértice nuevo queda SOBRE la línea
    win._do_insert_manhole(100.0, 4.0)
    assert win.pipes[0]["pts"][1] == (100.0, 0.0) and win.mode == "idle"


def test_herramienta_buzon_bloqueada_explica_al_clic(win):
    win.pipes = [dict(layer="AGUA", pts=[(0.0, 0.0), (300.0, 0.0)], diam=8.0)]
    h = win.herramientas
    h.sincronizar()
    k = next(i for i, b in enumerate(h.botones) if b._metodo == "insert_manhole")
    assert h.botones[k]._bloqueado
    h._elegir(k)
    assert win.mode != "insert_bz" and "presión" in win.mensajes[-1]
