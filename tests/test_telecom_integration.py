"""Telecomunicaciones punta a punta en la ventana real (`Main`, Qt offscreen).

Mismo camino que el usuario: PDF → reconocer (perfil TELECOM) → importar
(`_import_recognized_pipes`, el botón «Continuar e importar») → exportar el DXF
de anotaciones → leer el XDATA que consume el plugin (`ImportarRed.cs`).
"""
import math
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
ezdxf = pytest.importorskip("ezdxf")
from PySide6 import QtWidgets  # noqa: E402

import recognition as rec  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"
needs_pdf = pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")


def _xdata(e):
    try:
        return {s.split("=", 1)[0]: s.split("=", 1)[1]
                for code, s in e.get_xdata("PDFCAD") if code == 1000 and "=" in s}
    except Exception:
        return {}


@pytest.fixture
def win(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import theme
    theme.save_preference = lambda *_a, **_k: None          # no tocar QSettings del usuario
    import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


@needs_pdf
def test_telecom_de_pdf_a_dxf(win, tmp_path):
    win._open_pdf_path(str(DU10))
    page = 4                                                  # DU10 h.5: dos conductos al manhole
    win._load_page(page)
    res = rec.recognize_page(win.work_pdf_path or win.pdf_path, page, utility="TELECOM",
                             zoom=win.zoom, doc=None)
    assert res.drawable and res.coverage >= 0.99
    win._import_recognized_pipes([res])
    new = [p for p in win.pipes if p["layer"] == "TELECOM"]
    assert len(new) == len(res.drawable)
    assert all(("TELE" in str(p.get("xdata")) or "COMM" in str(p.get("xdata"))) for p in new)
    # red de CONDUCTOS (como el eléctrico): caja solo en la bóveda real, con sus medidas
    cajas = [s for s in win.structures if s.get("net") == "conduit"]
    assert cajas and all(str(s.get("cod", "")).startswith("CAJA-") for s in cajas)
    assert any(s.get("width_ft") and s.get("length_ft") for s in cajas)

    import config as C
    doc = ezdxf.new("R2010", setup=True)
    C.apply_imperial_header(doc)
    win._merge_into(doc, marks=True)
    out = tmp_path / "telecom.dxf"
    doc.saveas(out)
    d2 = ezdxf.readfile(out)
    pipes = [x for x in (_xdata(e) for e in d2.modelspace()) if "NET_KIND" in x and "DIAMETER" in x]
    assert pipes and all(x["NET_KIND"] == "conduit" for x in pipes)
    assert any(x.get("XD_CAPA", "").startswith("C-TELE") for x in pipes)
    sts = [x for x in (_xdata(e) for e in d2.modelspace()) if "STRUCT_ID" in x]
    assert any(x.get("SHAPE") == "rect" and float(x.get("WIDTH_FT") or 0) > 0 for x in sts)
