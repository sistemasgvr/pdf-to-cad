"""«Exportar DXF» digitaliza la hoja que está en el EDITOR.

Reporte del usuario (2026-09-30): abrir un PDF, importar, y luego en «Componer hoja»
quitar esa hoja y tomar una de OTRO PDF; al exportar, el DXF traía la hoja del primer
PDF (desfasada de las utilidades) porque el worker recibía `pdf_path` (el PDF que se
abrió primero) en vez del PDF de trabajo.
"""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtWidgets  # noqa: E402


def _pdf(path, text, pages=1):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=600, height=400)
        pg.insert_text((50, 60 + 20 * i), f"{text} hoja {i + 1}")
        pg.draw_line((50, 200), (550, 200))
    doc.save(str(path)); doc.close()
    return str(path)


@pytest.fixture
def win(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def test_exporta_la_hoja_compuesta_de_otro_pdf(win, tmp_path, monkeypatch):
    from ui.ventana import app_window
    from hoja import composite as composite_mod
    a = _pdf(tmp_path / "primero.pdf", "A", pages=3)
    b = _pdf(tmp_path / "segundo.pdf", "B", pages=2)
    win._open_pdf_path(a)
    # «Componer hoja»: se quita la hoja de A y se toma la hoja 2 de B, entera
    with open(b, "rb") as fp:
        win.src_pdfs.append({"name": "segundo.pdf", "data": fp.read(), "path": b})
    win.composite = composite_mod.Composite([composite_mod.Piece(1, 1, [0.0, 0.0, 1.0, 1.0])])
    win._apply_composite()
    assert win.pdf_path == a                          # el abierto primero no cambia…
    got = {}

    class FakeWorker:
        def __init__(self, pdf, out, pages=None):
            got.update(pdf=pdf, pages=pages)
            self.done = type("S", (), {"connect": lambda *_: None})()

        def start(self):
            pass
    monkeypatch.setattr(app_window, "PipelineWorker", FakeWorker)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(tmp_path / "salida.dxf"), ""))
    win.run_pipeline("todo")
    # …pero se digitaliza la hoja del editor: hoja 2 del SEGUNDO PDF
    assert got["pdf"] == win.work_pdf_path and Path(got["pdf"]) == Path(b)
    assert got["pages"] == [1]
    doc = fitz.open(got["pdf"])
    assert "B hoja 2" in doc[got["pages"][0]].get_text()
    doc.close()
    if getattr(win, "_prog", None):
        win._prog.close()
