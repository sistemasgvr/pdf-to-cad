"""«Reconocer más capas de esta hoja…»: reconocer otras capas SIN perder lo dibujado.

Recomendación del usuario (2026-11-12): una vez importadas las tuberías por capas y avanzado el lienzo,
«Componer hoja…» recargaba la hoja y lo importado reemplazaba todo. Ahora el asistente arranca en «Capas»
sobre la misma hoja y lo reconocido entra ENCIMA, sin repetir lo que ya está dibujado.
"""
import json

import pytest

from tests.test_respaldo_editor import (  # noqa: F401  (fixtures)
    LINEA, HOJA, AREA, _editor_con_lineas, _foto, _stubs, _FakeWorker, app, win)
from nucleo import reconocer_mas


def test_quitar_repetidas_solo_lo_que_corre_entero_sobre_su_capa():
    hecho = [{"layer": "DRENAJE", "pts": [(0, 0), (100, 0), (100, 50)]}]
    igual = {"layer": "DRENAJE", "pts": [(0.5, 0.4), (100.3, 0), (100, 49.6)]}
    parte = {"layer": "DRENAJE", "pts": [(20, 0), (80, 0)]}
    sigue = {"layer": "DRENAJE", "pts": [(50, 0), (180, 0)]}          # se sale de lo dibujado
    otra_capa = {"layer": "AGUA", "pts": [(0, 0), (100, 0)]}
    abandonada = {"layer": "DRENAJE", "ab": True, "pts": [(0, 0), (100, 0)]}
    quedan, n = reconocer_mas.quitar_repetidas(hecho, [igual, parte, sigue, otra_capa, abandonada], 2.0)
    assert n == 2
    assert quedan == [sigue, otra_capa, abandonada]


class _Worker(_FakeWorker):
    """Resultado sin polilíneas propias: lo que se importa lo da `pipes_from_recognition`."""
    def start(self):
        from reconocimiento import recognition as rec
        _FakeWorker.started.append(self)
        self.done.emit([rec.RecognitionResult("ELECTRICO", self.page_index, 20 / 72.0)], "")


def _nuevas(monkeypatch, pipes):
    from reconocimiento import recognition as rec
    from ui.ventana import app_window
    monkeypatch.setattr(app_window, "RecognitionWorker", _Worker)
    monkeypatch.setattr(rec, "pipes_from_recognition", lambda *a, **k: [dict(p) for p in pipes])


@pytest.mark.parametrize("base", [HOJA, AREA], ids=["hoja_entera", "area"])
def test_lo_reconocido_entra_encima_sin_repetir(win, app, tmp_path, monkeypatch, base):
    from ui.ventana import app_window
    rd = app_window.recognition_dialog
    _editor_con_lineas(win, tmp_path, base)
    win.pipes[0]["name"] = "editada a mano"
    doc, img = win.doc, win.canvas.pixmap_item.pixmap().cacheKey()
    nueva = {"layer": "ELECTRICO", "pts": [(10, 300), (400, 300)], "name": ""}
    _nuevas(monkeypatch, [dict(LINEA), nueva])                     # la de DRENAJE ya está dibujada
    vio = _stubs(monkeypatch, win, [], ["ok"], [rd.PREVIEW_IMPORT])
    win.reconocer_mas_capas()
    app.processEvents()
    assert len(vio) == 1, win.lbl_info.text()
    assert [(p["layer"], p.get("name")) for p in win.pipes] == [("DRENAJE", "editada a mano"), ("ELECTRICO", "")]
    assert win.doc is doc and not doc.is_closed                    # la misma hoja, sin rearmarla
    assert win.canvas.pixmap_item.pixmap().cacheKey() == img
    assert win._respaldo is None and win._reconociendo_mas is None
    win.undo()                                                     # un paso: lo reconocido
    assert [p["layer"] for p in win.pipes] == ["DRENAJE"]


def test_capas_apagadas_en_el_asistente_no_cambian_el_editor(win, app, tmp_path, monkeypatch):
    from ui.ventana import app_window
    rd = app_window.recognition_dialog
    _editor_con_lineas(win, tmp_path, HOJA)
    ocultas = list(win.hidden_ocgs)
    _nuevas(monkeypatch, [{"layer": "ELECTRICO", "pts": [(10, 300), (400, 300)], "name": ""}])
    _stubs(monkeypatch, win, [], [(["capa X"], win.page_idx, ("ELECTRICO",), set())], [rd.PREVIEW_IMPORT])
    win.reconocer_mas_capas()
    app.processEvents()
    assert [p["layer"] for p in win.pipes] == ["DRENAJE", "ELECTRICO"]
    assert list(win.hidden_ocgs) == ocultas


@pytest.mark.parametrize("donde", ["capas", "vista_previa", "sin_nada_nuevo"])
def test_salir_sin_importar_deja_el_editor_como_estaba(win, app, tmp_path, monkeypatch, donde):
    from ui.ventana import app_window
    rd = app_window.recognition_dialog
    _editor_con_lineas(win, tmp_path, AREA)
    antes = _foto(win)
    _nuevas(monkeypatch, [dict(LINEA)])                            # solo lo ya dibujado
    pasos = {"capas": ([], [None], []),
             "vista_previa": ([], ["ok"], [rd.PREVIEW_CANCEL]),
             "sin_nada_nuevo": ([], ["ok"], [rd.PREVIEW_IMPORT])}[donde]
    _stubs(monkeypatch, win, *pasos)
    win.reconocer_mas_capas()
    app.processEvents()
    despues = _foto(win)
    assert json.loads(despues.pop("pipes")) == json.loads(antes.pop("pipes"))
    assert despues == antes
    assert win._respaldo is None and win._reconociendo_mas is None


def test_otra_hoja_en_capas_no_se_importa(win, app, tmp_path, monkeypatch):
    from ui.ventana import app_window
    rd = app_window.recognition_dialog
    _editor_con_lineas(win, tmp_path, HOJA)
    antes = _foto(win)
    _nuevas(monkeypatch, [{"layer": "ELECTRICO", "pts": [(10, 300), (400, 300)], "name": ""}])
    _stubs(monkeypatch, win, [], [([], win.page_idx + 1, ("ELECTRICO",), set())], [rd.PREVIEW_IMPORT])
    win.reconocer_mas_capas()
    app.processEvents()
    assert [p["layer"] for p in win.pipes] == ["DRENAJE"]
    assert _foto(win)["page"] == antes["page"]
