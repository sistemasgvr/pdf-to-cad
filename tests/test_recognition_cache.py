"""El reconocimiento de la hoja queda en memoria (`recognition_cache`).

Pedido del usuario (2026-10-06): volver a «Componer hoja» desde el editor y seguir
sin cambiar nada no debe reconocer otra vez; cualquier cambio sí.
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_cache as RC  # noqa: E402


def _comp(page=0, clip=(0, 0, 1, 1)):
    return C.Composite([C.Piece(0, page, list(clip))])


def _key(**kw):
    args = dict(document=("abc",), composite=_comp(), page_index=0, hidden_ocgs=["A", "B"],
                utilities=("ELECTRICO", "AGUA"), roles_by_utility={}, letters_off=set(),
                scale_ft_per_pt=None, zoom=3.5)
    args.update(kw)
    return RC.recognition_key(args.pop("document"), args.pop("composite"), args.pop("page_index"), **args)


def test_misma_entrada_misma_clave():
    assert _key() == _key()
    assert _key(hidden_ocgs=["B", "A", "A"]) == _key()            # orden y repetidos no cuentan
    assert _key(roles_by_utility={"AGUA": {}}) == _key()           # sin roles = automático
    comp = _comp()
    comp.last_view = [0, 3]                                        # solo dónde miraba el compositor
    assert _key(composite=comp) == _key()


@pytest.mark.parametrize("change", [
    dict(document=("otro",)),
    dict(composite=_comp(page=1)),
    dict(composite=_comp(clip=(0, 0, 0.5, 1))),
    dict(page_index=1),
    dict(hidden_ocgs=["A"]),
    dict(utilities=("ELECTRICO",)),
    dict(roles_by_utility={"AGUA": {rec.ROLE_LINEAS: ["C-WATR-UNGD"]}}),
    dict(letters_off={"U-TRPW-DBNK-P"}),
    dict(scale_ft_per_pt=20 / 72.0),
    dict(zoom=1.0),
])
def test_cualquier_cambio_da_otra_clave(change):
    assert _key(**change) != _key()


def test_huellas_de_los_pdf(monkeypatch):
    calls = []
    real = RC.hashlib.sha1
    monkeypatch.setattr(RC.hashlib, "sha1", lambda data: calls.append(1) or real(data))
    fp = RC.SourceFingerprints()
    data = b"%PDF-1.7 uno"
    first = fp([{"data": data}])
    assert fp([{"name": "copia del dict", "data": data}]) == first     # mismo bytes: no se relee
    assert len(calls) == 1
    assert fp([{"data": b"%PDF-1.7 dos"}]) != first
    assert fp([{"data": b"%PDF-1.7 uno"}]) == first                   # mismo contenido, otro objeto


def test_cache_recuerda_las_ultimas():
    cache = RC.RecognitionCache(max_entries=2)
    cache.put("a", ["ra"]); cache.put("b", ["rb"])
    assert cache.get("a") == ["ra"]                    # «a» pasa a ser la más reciente
    cache.put("c", ["rc"])
    assert cache.get("b") is None and cache.get("a") == ["ra"] and cache.get("c") == ["rc"]
    cache.put(None, ["x"]); cache.put("d", [])         # sin clave o sin resultado: nada
    assert len(cache) == 2
    cache.clear()
    assert cache.get("a") is None


def test_unir_tramos_se_aplica_al_resultado_guardado():
    res = rec.RecognitionResult("ELECTRICO", 0, 20 / 72.0, polylines=["j"],
                                polylines_joined=["j"], polylines_raw=["r1", "r2"])
    RC.set_join_routes([res], False)
    assert res.polylines == ["r1", "r2"] and not res.join_routes
    RC.set_join_routes([res], True)
    assert res.polylines == ["j"] and res.join_routes


# ───────────────────── en la ventana real (Qt offscreen) ─────────────────────

class _FakeWorker(QtCore.QObject):
    """Reemplaza a `RecognitionWorker`: cuenta cuántas veces se reconoce."""
    done = QtCore.Signal(object, str)
    progress = QtCore.Signal(int, int, str)
    started = []

    def __init__(self, pdf_path, page_index, **kw):
        super().__init__()
        self.page_index = page_index
        self.kw = kw

    def start(self):
        _FakeWorker.started.append(self)
        res = rec.RecognitionResult("ELECTRICO", self.page_index, 20 / 72.0, polylines=["j"],
                                    polylines_joined=["j"], polylines_raw=["r"])
        self.done.emit([res], "")


@pytest.fixture
def win(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None          # no tocar QSettings del usuario
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(app_window, "RecognitionWorker", _FakeWorker)
    _FakeWorker.started = []
    w = app_window.Main()
    img = QtGui.QImage(40, 30, QtGui.QImage.Format_RGB888); img.fill(QtGui.QColor("white"))
    w.canvas.set_image(img)
    w.src_pdfs = [{"name": "plano.pdf", "data": b"%PDF-1.7 plano"}]
    w.composite = _comp()
    w.work_pdf_path = "plano.pdf"
    w.hidden_ocgs = ["C-ANNO"]
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def test_sin_cambios_no_reconoce_otra_vez(win, monkeypatch):
    from ui.ventana import app_window
    shown = []
    monkeypatch.setattr(app_window.recognition_dialog, "show_recognition_preview",
                        lambda parent, qimg, results, **kw: shown.append(list(results)) or
                        app_window.recognition_dialog.PREVIEW_CANCEL)
    app = QtWidgets.QApplication.instance()

    win._start_recognition(0)
    assert len(_FakeWorker.started) == 1 and len(shown) == 1
    first = shown[0][0]

    # Volver a componer sin cambiar nada: misma vista previa, sin otro reconocimiento.
    win._join_routes = False                    # «Unir tramos» como lo dejó el usuario
    win._start_recognition(0)
    app.processEvents()
    assert len(_FakeWorker.started) == 1 and len(shown) == 2
    assert shown[1][0] is first and first.polylines == ["r"]

    # Un cambio (otra capa oculta) sí reconoce de nuevo.
    win.hidden_ocgs = ["C-ANNO", "C-ELEC-UNGD"]
    win._start_recognition(0)
    assert len(_FakeWorker.started) == 2 and shown[2][0] is not first

    # Otra composición, también.
    win.hidden_ocgs = ["C-ANNO"]
    win.composite = _comp(clip=(0, 0, 0.5, 1))
    win._start_recognition(0)
    assert len(_FakeWorker.started) == 3

    # Cerrar el proyecto olvida lo reconocido.
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.Discard)
    win.close_project()
    assert len(win._recog_cache) == 0
