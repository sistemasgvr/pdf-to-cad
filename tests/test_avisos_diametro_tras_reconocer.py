"""Los avisos «Diámetro del plano» salen solo cuando se reconoció la fila «Diámetros» del panel Reconocer (pedido del
usuario 2026-11-17: aparecían al importar las tuberías, antes de reconocer los diámetros). Sin el panel nuevo
(proyecto de antes, hoja nunca interpretada con él) siguen como siempre."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("pymupdf")
from PySide6 import QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from nucleo import reconocer_estado as RE  # noqa: E402

TUBO = {"layer": "AGUA", "pts": [(10.0, 10.0), (300.0, 10.0)], "name": "", "diam": 12.0,
        "diam_plano": {"estado": "sin_dato"}}


@pytest.fixture
def win(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(app_window.Main, "_interpretar_hoja", lambda self: None)
    doc = fitz.open()
    doc.new_page(width=600, height=400)
    ruta = str(tmp_path / "h.pdf")
    doc.save(ruta); doc.close()
    w = app_window.Main()
    w._open_pdf_path(ruta)
    w.composite = C.Composite([C.Piece(0, 0, [0, 0, 1, 1])])
    w._apply_composite()
    w.pipes.append(dict(TUBO))
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def _grosor(w):
    w._redraw()
    return [a for a in (w._normas_avisos or []) if a.clase == "grosor"]


def test_sin_reconocer_diametros_no_hay_avisos_y_al_reconocerlos_si(win):
    e = RE.nuevo()
    e.firma_hoja = "hoja"
    e.filas["AGUA"].estado = "reconocida"
    e.filas["DIAMETROS"].estado = "pendiente"
    win.reconocer_estado = e
    assert _grosor(win) == []
    e.filas["DIAMETROS"].estado = "reconocida"
    assert len(_grosor(win)) == 1
    e.filas["DIAMETROS"].estado = "desactualizada"            # ya se reconoció una vez: siguen
    assert len(_grosor(win)) == 1


def test_proyecto_sin_el_panel_nuevo_los_muestra_como_siempre(win):
    win.reconocer_estado = RE.de_proyecto_viejo(win.pipes)    # firma_hoja None: nunca se interpretó
    assert len(_grosor(win)) == 1
    assert RE.avisos_diametro(None)
