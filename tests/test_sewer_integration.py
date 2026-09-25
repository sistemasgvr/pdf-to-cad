"""Alcantarillado punta a punta en la ventana real (`Main`, Qt offscreen).

Mismo camino que el usuario: PDF → reconocer (perfil ALCANTARILLADO) → importar
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
def test_alcantarillado_de_pdf_a_dxf(win, tmp_path):
    win._open_pdf_path(str(DU10))
    page = 6                                                  # DU10 h.7
    win._load_page(page)
    res = rec.recognize_page(win.work_pdf_path or win.pdf_path, page, utility="ALCANTARILLADO",
                             zoom=win.zoom, doc=None)
    assert res.drawable and res.coverage >= 0.99
    # ningún anillo de buzón llega como tubería (la línea del plano no es un círculo)
    for pl in res.drawable:
        assert sum(1 for k in pl.kinds if k == "curve") < 6, pl.pts_pdf
    circles = [vg for vg in res.vaults_geo if vg["shape"] == "circle" and vg["importable"]]
    assert circles and all(3.0 <= vg["width_ft"] <= 7.0 for vg in circles)

    n_before = len(win.pipes)
    win._import_recognized_pipes([res])
    new = win.pipes[n_before:]
    assert len(new) == len(res.drawable)
    assert all(p["layer"] == "ALCANTARILLADO" for p in new)
    assert all((p.get("xdata") or {}).get("auto", {}).get("Sistema", "").startswith("SSWR")
               or "SSWR" in str(p.get("xdata")) for p in new)
    # red por GRAVEDAD: buzones como estructuras, los reconocidos con su forma circular
    structs = [s for s in win.structures if s.get("net") == "gravity"]
    round_ = [s for s in structs if s.get("shape") == "circle"]
    assert round_, [s.get("shape") for s in structs]
    assert all(3.0 <= float(s.get("width_ft") or 0) <= 7.0 for s in round_)

    # DXF de anotaciones (lo que genera «Exportar DXF → solo anotaciones»)
    import config as C
    doc = ezdxf.new("R2010", setup=True)
    C.apply_imperial_header(doc)
    win._merge_into(doc, marks=True)
    out = tmp_path / "alcantarillado.dxf"
    doc.saveas(out)
    d2 = ezdxf.readfile(out)
    assert d2.header["$INSUNITS"] == 2 and d2.header["$MEASUREMENT"] == 0
    pipes = [x for x in (_xdata(e) for e in d2.modelspace()) if "NET_KIND" in x and "DIAMETER" in x]
    assert pipes and all(x["NET_KIND"] == "gravity" for x in pipes)
    assert any(x.get("XD_CAPA", "").startswith("C-SSWR-UNGD") for x in pipes)
    sts = [x for x in (_xdata(e) for e in d2.modelspace()) if "STRUCT_ID" in x]
    assert any(x.get("SHAPE") == "circle" and 3.0 <= float(x.get("WIDTH_FT") or 0) <= 7.0 for x in sts)
    assert all(x.get("NET_KIND") == "gravity" for x in sts if x.get("SHAPE"))
