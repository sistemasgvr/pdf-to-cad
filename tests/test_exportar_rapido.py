"""«Exportar DXF» más rápido sin cambiar el resultado (pedido del usuario 2026-10-17, proyecto de
16 761 utilidades): el PDF ya digitalizado se REUSA (`exportar/cache_digitalizado`), leer y guardar el
DXF van en otro hilo (`ui/comun/en_hilo`) y la limpieza de tramos diminutos mira solo las utilidades
cercanas (`limpieza_tramos.cajas_de`, ver también `test_limpieza.py`)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
ezdxf = pytest.importorskip("ezdxf")
from PySide6 import QtWidgets  # noqa: E402


def _pdf(path, texto):
    doc = fitz.open()
    pg = doc.new_page(width=600, height=400)
    pg.insert_text((50, 60), texto)
    pg.draw_line((50, 200), (550, 200))
    doc.save(str(path)); doc.close()
    return str(path)


def test_clave_cambia_con_el_pdf_y_las_hojas(tmp_path):
    from exportar import cache_digitalizado as CD
    a, b = _pdf(tmp_path / "a.pdf", "A"), _pdf(tmp_path / "b.pdf", "B")
    assert CD.clave(a, [0]) == CD.clave(a, [0])
    assert CD.clave(a, [0]) != CD.clave(b, [0])
    assert CD.clave(a, [0]) != CD.clave(a, None)


def test_la_cache_guarda_los_mas_recientes(tmp_path, monkeypatch):
    from exportar import cache_digitalizado as CD
    monkeypatch.setattr(CD, "MAX_ARCHIVOS", 2)
    dxf = tmp_path / "base.dxf"
    dxf.write_text("0\nEOF\n")
    for k in ("uno", "dos", "tres"):
        CD.guardar(k, str(dxf))
        os.utime(CD.buscar(k), (os.path.getmtime(CD.buscar(k)) + {"uno": 0, "dos": 1, "tres": 2}[k],) * 2)
    CD._recortar()
    assert CD.buscar("uno") is None and CD.buscar("dos") and CD.buscar("tres")


class _Senal:
    def __init__(self):
        self.fns = []

    def connect(self, fn):
        self.fns.append(fn)

    def emit(self, *a):
        for fn in self.fns:
            fn(*a)


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


def test_segunda_exportacion_reusa_el_pdf_digitalizado(win, tmp_path, monkeypatch):
    from ui.ventana import app_window
    pdf = _pdf(tmp_path / "plano.pdf", "Plano")
    win._open_pdf_path(pdf)
    win._load_page(0)                                  # la hoja en el editor (sin el asistente)
    creados = []

    class FakeWorker:                                  # «digitaliza»: una línea en el DXF base
        def __init__(self, src, out, pages=None):
            creados.append(src)
            self.out, self.done = out, _Senal()

        def start(self):
            d = ezdxf.new("R2010")
            d.modelspace().add_line((0, 0), (12.5, 7.25), dxfattribs={"layer": "BASE"})
            d.saveas(self.out)
            self.done.emit(self.out, "")
    monkeypatch.setattr(app_window, "PipelineWorker", FakeWorker)
    salidas = iter([tmp_path / "uno.dxf", tmp_path / "dos.dxf", tmp_path / "tres.dxf"])
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(next(salidas)), ""))

    def lineas(ruta):
        return sorted((tuple(e.dxf.start), tuple(e.dxf.end)) for e in ezdxf.readfile(str(ruta)).modelspace()
                      if e.dxftype() == "LINE" and e.dxf.layer == "BASE")
    win.run_pipeline("todo")
    assert len(creados) == 1 and lineas(tmp_path / "uno.dxf")
    win.run_pipeline("todo")                           # mismo PDF: no se digitaliza otra vez
    assert len(creados) == 1
    assert lineas(tmp_path / "dos.dxf") == lineas(tmp_path / "uno.dxf")
    assert not os.path.exists(str(tmp_path / "dos.dxf") + ".base.tmp.dxf")
    win._open_pdf_path(_pdf(tmp_path / "otro.pdf", "Plano cambiado"))   # otro PDF: se digitaliza
    win._load_page(0)
    win.run_pipeline("todo")
    assert len(creados) == 2


def test_en_hilo_devuelve_resultado_y_error(win):
    from ui.comun import en_hilo
    assert en_hilo.ejecutar(win, lambda: 41 + 1, "Probando…") == (42, "", False)
    r, err, cancelado = en_hilo.ejecutar(win, lambda: 1 / 0, "Probando…")
    assert r is None and "ZeroDivisionError" in err and not cancelado
