"""«Cancelar» en el asistente abierto desde el editor deja el editor como estaba.

Reporte del usuario (2026-10-07): con lo reconocido ya importado, Herramientas →
«Componer hoja de trabajo…» y Cancelar dejaba la hoja SIN líneas: al aceptar el
compositor la hoja se recargaba y el modelo se vaciaba antes de «Capas» y de la
vista previa. Ahora cualquier salida sin importar repone hoja, líneas, deshacer y
«cambios sin guardar» (`respaldo_editor`); importar sí reemplaza.
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402

LINEA = {"layer": "DRENAJE", "pts": [(10, 10), (200, 10), (200, 120)], "name": "", "diam": 12.0}
HOJA = [0.0, 0.0, 1.0, 1.0]
AREA = [0.0, 0.0, 0.5, 1.0]


def _pdf(path, pages=3):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=600, height=400)
        pg.insert_text((50, 60), f"plano hoja {i + 1}")
        pg.draw_line((50, 200), (550, 200))
    doc.save(str(path)); doc.close()
    return str(path)


class _FakeWorker(QtCore.QObject):
    """Reemplaza a `RecognitionWorker`: resultado (o error) al instante."""
    done = QtCore.Signal(object, str)
    progress = QtCore.Signal(int, int, str)
    started = []
    error = ""

    def __init__(self, pdf_path, page_index, **kw):
        super().__init__()
        self.page_index = page_index

    def start(self):
        _FakeWorker.started.append(self)
        if _FakeWorker.error:
            self.done.emit(None, _FakeWorker.error)
            return
        res = rec.RecognitionResult("ELECTRICO", self.page_index, 20 / 72.0, polylines=["j"],
                                    polylines_joined=["j"], polylines_raw=["r"])
        self.done.emit([res], "")


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app, monkeypatch):
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(app_window, "RecognitionWorker", _FakeWorker)
    _FakeWorker.started, _FakeWorker.error = [], ""
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    # «Hay cambios sin guardar. ¿Deseas guardarlos?» → Descartar (lo peor para el caso)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.Discard)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def _editor_con_lineas(win, tmp_path, clip, manual=False):
    """Como tras el asistente: hoja 2 en el editor y una línea importada sin guardar."""
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win.composite = C.Composite([C.Piece(0, 1, list(clip))], manual=manual, bridges=not manual)
    win._apply_composite()
    QtWidgets.QApplication.instance().processEvents()   # huella «guardado» de la hoja recién cargada
    win._push()
    win.pipes.append(dict(LINEA))
    for _ in range(2):            # el 2.º refresco completa los campos por defecto de las cajas
        win._refresh_lists(); win._update_ui(); win._redraw()


def _foto(win):
    pm = win.canvas.pixmap_item.pixmap()
    return dict(pipes=json.dumps(win.pipes, sort_keys=True, default=str),
                structures=json.dumps(win.structures, sort_keys=True, default=str),
                doc=win.doc, page=win.page_idx, work=win.work_pdf_path, tmp=win._tmp_composite,
                comp=win.composite.to_dict(), hidden=list(win.hidden_ocgs), scale=win.scale,
                image=(pm.size(), pm.cacheKey()), undo=len(win._undo), dirty=win._dirty)


def _stubs(monkeypatch, win, compositor, capas, vista_previa):
    """Respuestas de cada paso, en orden. Devuelve lo que vio la vista previa."""
    from ui.ventana import app_window
    rd = app_window.recognition_dialog
    vio = []

    def compose(parent, sources, comp, hidden, **kw):
        nuevo = compositor.pop(0)
        return None if nuevo is None else (nuevo, list(sources), dict(hidden or {}))

    def layers(parent, doc, page_idx, **kw):
        r = capas.pop(0)
        return ([], page_idx, ("ELECTRICO",), set()) if r == "ok" else r

    def preview(parent, qimg, results, **kw):
        vio.append(dict(pipes=len(win.pipes), work=win.work_pdf_path, tmp=win._tmp_composite))
        return vista_previa.pop(0)

    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", compose)
    monkeypatch.setattr(app_window.layer_dialog, "choose_sheet_layers", layers)
    monkeypatch.setattr(rd, "show_recognition_preview", preview)
    monkeypatch.setattr(rd, "choose_layer_roles", lambda *a, **k: None)
    return vio


def _otra():
    return C.Composite([C.Piece(0, 1, [0.0, 0.0, 0.6, 1.0])])


@pytest.mark.parametrize("base", [HOJA, AREA], ids=["hoja_entera", "area"])
@pytest.mark.parametrize("donde", ["compositor", "capas", "vista_previa", "capas_volver_compositor",
                                   "error", "ajustar_capas", "importar_sin_tramos"])
def test_cancelar_deja_el_editor_como_estaba(win, app, tmp_path, monkeypatch, base, donde):
    from ui.ventana import app_window
    from ui.asistente.layer_dialog import LAYERS_BACK
    rd = app_window.recognition_dialog
    _editor_con_lineas(win, tmp_path, base)
    antes = _foto(win)
    pasos = {
        "compositor": ([None], [], []),
        "capas": ([_otra()], [None], []),
        "vista_previa": ([_otra()], ["ok"], [rd.PREVIEW_CANCEL]),
        "capas_volver_compositor": ([_otra(), None], [LAYERS_BACK], []),
        "error": ([_otra()], ["ok"], []),
        "ajustar_capas": ([_otra()], ["ok"], [rd.PREVIEW_ADJUST_LAYERS, rd.PREVIEW_CANCEL]),
        "importar_sin_tramos": ([_otra()], ["ok"], [rd.PREVIEW_IMPORT]),
    }[donde]
    vio = _stubs(monkeypatch, win, *pasos)
    if donde == "error":
        _FakeWorker.error = "falló"
    if donde == "importar_sin_tramos":
        monkeypatch.setattr(win, "_import_recognized_pipes", lambda results: False)

    win.compose_sheet()
    app.processEvents()           # «Ajustar capas…» cancelado vuelve a la vista previa (QTimer)

    if vio:                                         # el caso del reporte: a mitad de camino
        assert vio[0]["pipes"] == 0                 # el editor ya estaba vacío
    if donde == "ajustar_capas":
        assert len(vio) == 2 and len(_FakeWorker.started) == 1    # misma vista previa, sin reconocer
    despues = _foto(win)
    assert despues == antes
    assert not win.doc.is_closed                     # el PDF de la hoja de antes, vivo
    assert "plano hoja 2" in win.doc[win.page_idx].get_text()
    assert win._respaldo is None
    if antes["tmp"]:
        assert os.path.isfile(antes["tmp"])          # el temporal de la hoja de antes sigue
    for paso in vio:                                 # y el de la hoja nueva se borró
        if paso["tmp"]:
            assert not os.path.isfile(paso["tmp"])
    assert win._has_real_changes()                   # sigue «sin guardar»


def test_importar_reemplaza_y_suelta_la_hoja_de_antes(win, app, tmp_path, monkeypatch):
    from ui.ventana import app_window
    rd = app_window.recognition_dialog
    _editor_con_lineas(win, tmp_path, AREA)
    doc_antes, tmp_antes = win.doc, win._tmp_composite
    _stubs(monkeypatch, win, [C.Composite([C.Piece(0, 2, HOJA)])], ["ok"], [rd.PREVIEW_IMPORT])
    nueva = {"layer": "ELECTRICO", "pts": [(0, 0), (90, 0)], "name": ""}
    monkeypatch.setattr(win, "_import_recognized_pipes",
                        lambda results: win.pipes.append(dict(nueva)) or True)
    win.compose_sheet()
    app.processEvents()
    assert [p["layer"] for p in win.pipes] == ["ELECTRICO"]
    assert win.page_idx == 2 and not win.doc.is_closed
    assert doc_antes.is_closed and not os.path.isfile(tmp_antes)
    assert win._respaldo is None


def test_hoja_guardada_sigue_guardada_al_cancelar(win, app, tmp_path, monkeypatch):
    from ui.ventana import app_window
    _editor_con_lineas(win, tmp_path, HOJA)
    win._dirty = False                               # como recién guardado
    app.processEvents()
    assert not win._has_real_changes()
    _stubs(monkeypatch, win, [_otra()], ["ok"], [app_window.recognition_dialog.PREVIEW_CANCEL])
    win.compose_sheet()
    app.processEvents()
    assert len(win.pipes) == 1
    assert not win._has_real_changes() and not win.windowTitle().startswith("*")


def test_sin_trabajo_cancelar_en_capas_deja_la_hoja_nueva(win, app, tmp_path, monkeypatch):
    """Editor sin nada que perder: como siempre, cancelar en «Capas» deja cargada la hoja
    nueva (para dibujar a mano) y no se guarda ningún respaldo."""
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win.composite = C.Composite([C.Piece(0, 1, HOJA)])
    win._apply_composite()
    _stubs(monkeypatch, win, [C.Composite([C.Piece(0, 2, HOJA)])], [None], [])
    win.compose_sheet()
    app.processEvents()
    assert win.page_idx == 2 and "plano hoja 3" in win.doc[2].get_text()
    assert win._respaldo is None


def test_escaneo_sin_cambios_no_borra_lo_dibujado(win, app, tmp_path, monkeypatch):
    _editor_con_lineas(win, tmp_path, HOJA, manual=True)
    antes = _foto(win)
    misma = C.Composite.from_dict(win.composite.to_dict())
    misma.last_view = [0, 1]                         # solo dónde miraba el compositor
    _stubs(monkeypatch, win, [misma], [], [])
    aplicadas = []
    monkeypatch.setattr(win, "_apply_composite", lambda: aplicadas.append(1))
    win.compose_scan_sheet()
    app.processEvents()
    assert not aplicadas and _foto(win) == antes and win._respaldo is None


def test_escaneo_con_otra_hoja_la_carga(win, app, tmp_path, monkeypatch):
    _editor_con_lineas(win, tmp_path, HOJA, manual=True)
    doc_antes = win.doc
    otra = C.Composite([C.Piece(0, 1, AREA)], manual=True, bridges=False)
    _stubs(monkeypatch, win, [otra], [], [])
    win.compose_scan_sheet()
    app.processEvents()
    assert win.pipes == [] and win.composite.pieces[0].clip == AREA
    assert doc_antes.is_closed and win._respaldo is None
