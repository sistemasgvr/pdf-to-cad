"""Layer switches retain scene objects; cold PDF backgrounds never block the UI."""
import copy
import importlib
import os

import numpy as np
import pytest

from test_agregar_utilidad import app, pdfs, win  # noqa: F401
from test_planos_fondo import _con_agua_y_cloaca, _img
from ui.comun import capas_popup as CP, proceso


def _no_redraw(*a, **kw):
    raise AssertionError("A visibility switch entered the full geometry redraw")


def test_utility_switch_keeps_items_and_model(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    x, y = win.pipes[0]["pts"][0]
    win.structures.append(dict(x=x, y=y, cod="BZ", standalone=True, utility="AGUA"))
    win.sel_pipe = -1
    win._redraw()
    scene_items = {id(it) for it in win.canvas.scene().items()}
    structure_items = [it for i, _curve, _owners, items in win._estructuras_vista
                       if i == len(win.structures) - 1 for it in items]
    line_layer, marks = win._capa_lineas[1], win._marcas
    before = (copy.deepcopy((win.pipes, win.structures)), tuple(win._undo), win._dirty)
    monkeypatch.setattr(win, "_redraw", _no_redraw)
    for on in (False, True, False, True):
        win._cambiar_capa(CP.UTILIDAD, "AGUA", on)
        assert win._capa_lineas[1] is line_layer and win._marcas is marks
        assert {id(it) for it in win.canvas.scene().items()} == scene_items
        assert all(it.isVisible() == on for it in structure_items)
        assert bool(win._estructuras_ocultas) == (not on)
    assert ((win.pipes, win.structures), tuple(win._undo), win._dirty) == before


def test_background_switch_keeps_utility_geometry(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    line_layer, marks = win._capa_lineas[1], win._marcas
    before = (copy.deepcopy((win.pipes, win.structures)), tuple(win._undo))
    monkeypatch.setattr(win, "_redraw", _no_redraw)
    for groups in ({0}, {1}, {0, 1}, set(), {0, 1}, {0}):
        assert win._poner_planos(groups)
        assert win._capa_lineas[1] is line_layer and win._marcas is marks
    assert ((win.pipes, win.structures), tuple(win._undo)) == before


def test_segment_labels_update_without_full_redraw(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    p = win.pipes[0]
    a, b = p["pts"]
    p["pts"] = [a, ((a[0] + b[0]) / 2, a[1]), b]
    p["seg_edit_enabled"] = True
    win.sel_pipe = -1
    win._redraw()
    layer = win._capa_lineas[1]
    assert win._items_rotulos_tramos
    monkeypatch.setattr(win, "_redraw", _no_redraw)
    win._cambiar_capa(CP.UTILIDAD, "AGUA", False)
    assert not win._items_rotulos_tramos
    win._cambiar_capa(CP.UTILIDAD, "AGUA", True)
    assert len(win._items_rotulos_tramos) == 2
    assert win._capa_lineas[1] is layer


class _Worker:
    def __init__(self):
        self.tasks = []

    def enviar(self, task):
        self.tasks.append(task)

    def finish(self, index=0, error=""):
        task = self.tasks[index]
        if error:
            task._fin(None, error)
            return None
        module, fn = task.objetivo.split(":")
        result = getattr(importlib.import_module(module), fn)(*task.args, **task.kwargs)
        task._fin(result, "")
        return result


def _async(win, monkeypatch):
    worker = _Worker()
    monkeypatch.setattr(proceso, "activo", lambda: True)
    monkeypatch.setattr(proceso, "trabajador", lambda *a: worker)
    monkeypatch.setattr(win, "_redraw", _no_redraw)
    monkeypatch.setattr(win, "_fondo_de", _no_redraw)
    return worker


def test_cold_background_is_async_and_cached_states_are_instant(win, pdfs, monkeypatch):
    original, _points, _ = _con_agua_y_cloaca(win, pdfs, monkeypatch)
    combined = _img(win)
    worker = _async(win, monkeypatch)
    assert win._poner_planos({0})
    assert win._planos_encendidos() == [0]
    assert win._vista_fondo is None and len(worker.tasks) == 1
    assert np.array_equal(_img(win), combined)  # first request only enqueues work
    result = worker.finish()
    assert win._vista_fondo == frozenset({0})
    assert np.array_equal(_img(win), original)
    assert not os.path.exists(result["img"]) and not os.path.exists(result["gris"])
    for groups, expected in (({0, 1}, combined), ({0}, original), ({0, 1}, combined)):
        win._poner_planos(groups)
        assert np.array_equal(_img(win), expected)
    assert len(worker.tasks) == 1


def test_rapid_background_switches_only_publish_latest(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    combined = _img(win)
    worker = _async(win, monkeypatch)
    win._poner_planos({0})
    win._poner_planos({1})
    assert len(worker.tasks) == 1 and win._planos_encendidos() == [1]
    stale = worker.finish(0)
    assert win._vista_fondo is None and np.array_equal(_img(win), combined)
    assert not os.path.exists(stale["img"]) and not os.path.exists(stale["gris"])
    assert len(worker.tasks) == 2
    worker.finish(1)
    assert win._vista_fondo == frozenset({1}) and win._planos_objetivo is None


def test_hide_all_during_preparation_does_not_restore_old_background(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    worker = _async(win, monkeypatch)
    win._poner_planos({0})
    win._poner_planos(set())
    worker.finish()
    assert win._planos_encendidos() == [] and win._fondo_apagado
    assert not win.canvas.pixmap_item.isVisible()
    assert win._planos_objetivo is None and len(worker.tasks) == 1


def test_background_result_from_previous_sheet_is_discarded(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    worker = _async(win, monkeypatch)
    win._poner_planos({0})
    win._soltar_planos()
    result = worker.finish()
    assert win._vista_fondo is None and not win._planos_docs
    assert all(not os.path.exists(result[k]) for k in ("img", "gris", "pdf"))


def test_failed_background_preserves_current_view_without_sync_fallback(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    combined = _img(win)
    worker = _async(win, monkeypatch)
    win._poner_planos({0})
    worker.finish(error="memoria")
    assert win._planos_encendidos() == [0, 1] and win._planos_objetivo is None
    assert win._vista_fondo is None and np.array_equal(_img(win), combined)


def test_return_to_current_background_cancels_pending_presentation(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    combined = _img(win)
    worker = _async(win, monkeypatch)
    win._poner_planos({0})
    win._poner_planos({0, 1})
    worker.finish()
    assert win._vista_fondo is None and win._planos_objetivo is None
    assert np.array_equal(_img(win), combined) and len(worker.tasks) == 1


def test_real_worker_keeps_event_loop_running(win, pdfs, monkeypatch, app):
    from PySide6 import QtCore
    from test_planos_fondo import _esperar
    original, _points, _ = _con_agua_y_cloaca(win, pdfs, monkeypatch)
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    monkeypatch.setattr(win, "_redraw", _no_redraw)
    ticks = []
    timer = QtCore.QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    try:
        assert win._poner_planos({0})
        assert win._planos_cambio_tarea is not None
        assert _esperar(app, lambda: win._planos_cambio_tarea is None, seg=30)
        assert ticks and win._vista_fondo == frozenset({0})
        assert np.array_equal(_img(win), original)
    finally:
        timer.stop()
        proceso.trabajador("planos").parar()


def _con_rotulos_y_marca(win, pdfs, monkeypatch):
    """Utilidad con rótulos T1/T2 y una marca en su capa en cada redibujo."""
    from PySide6 import QtWidgets
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    p = win.pipes[0]
    a, b = p["pts"]
    p["pts"] = [a, ((a[0] + b[0]) / 2, a[1]), b]
    p["seg_edit_enabled"] = True
    original = win._draw_accesorios

    def con_marca(*args, **kw):
        res = original(*args, **kw)
        marca = QtWidgets.QGraphicsEllipseItem(-3, -3, 6, 6)
        marca.setZValue(123)
        marca.setPos(10, 10)
        win._marca(marca)
        return res
    monkeypatch.setattr(win, "_draw_accesorios", con_marca)
    return p


def test_rotulos_de_tramo_no_dejan_marcas_fantasma_al_redibujar(win, pdfs, monkeypatch):
    """Quitar los rótulos viejos no puede cambiar la lista `_overlay` que usa `GrupoMarcas`: la capa de
    marcas creada después quedaba fuera de ella y el redibujo siguiente no la quitaba de la escena."""
    from ui.comun.capa_marcas import _Capa
    p = _con_rotulos_y_marca(win, pdfs, monkeypatch)
    for diam in (6, 8, 10, 12):                         # cada uno es otro modelo: marcas nuevas
        p["diam"] = diam
        win._redraw()
    assert win._marcas.nuevas is win._overlay
    capas = [it for it in win.canvas.scene().items() if isinstance(it, _Capa) and it.zValue() == 123]
    assert len(capas) == 1


def test_refrescar_hojas_conserva_la_lista_de_marcas(win, pdfs, monkeypatch):
    _con_rotulos_y_marca(win, pdfs, monkeypatch)
    win._redraw()
    win.act_marcas_hojas.setChecked(True)
    win._refrescar_hojas()
    win._refrescar_hojas()
    assert win._marcas.nuevas is win._overlay


def test_buzones_visibles_no_calculan_duenas_sin_capas_apagadas(win, pdfs, monkeypatch):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    x, y = win.pipes[0]["pts"][0]
    win.structures.append(dict(x=x, y=y, cod="BZ", standalone=True, utility="AGUA"))
    win.sel_pipe = -1
    win._redraw()
    assert not win._duenas_memo                          # nada apagado: nada que preguntar
    win._cambiar_capa(CP.UTILIDAD, "AGUA", False)
    assert win._estructuras_ocultas and win._duenas_memo
