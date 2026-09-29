"""Codos reconocidos → EDITOR: el arco que dibuja el lienzo es el reconocido.

Reporte del usuario (2026-09-28, DU08 h.26): dos curvas eléctricas que salen de la
misma recta (una sube y otra baja) tienen sus esquinas a 3.8 pt (13 px a zoom 3.5).
El editor buscaba la PRIMERA estructura curva a ≤14 px de cada vértice y usaba su
posición como esquina: la curva de abajo se dibujaba con la esquina y el radio de la
de arriba y se veía apartada de la tinta. Ahora toma la MÁS CERCANA y la esquina es
el vértice de la tubería.
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

pytest.importorskip("fitz")
from PySide6 import QtWidgets  # noqa: E402

import model_ops  # noqa: E402
import recognition as rec  # noqa: E402

DU08 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")


def test_pipe_at_vertex_y_nearest_vertex_toman_el_mas_cercano():
    a = {"pts": [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]}
    b = {"pts": [(0.0, 50.0), (113.0, 0.0), (200.0, 50.0)]}          # vértice a 13 px del de `a`
    assert model_ops.pipe_at_vertex([b, a], 101.0, 0.0) is a
    assert model_ops.pipe_at_vertex([a, b], 112.0, 0.0) is b
    assert model_ops.nearest_vertex([(0, 0), (10, 0), (12, 0)], 11.5, 0.0) == 2
    assert model_ops.nearest_vertex([(0, 0)], 50.0, 0.0) is None


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


DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"


@pytest.mark.parametrize("pdf, page, utility", [
    pytest.param(DU08, 25, "ELECTRICO", marks=pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")),
    pytest.param(DU08, 25, "TELECOM", marks=pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")),
    # reporte 2026-09-29: curva en «S» de telecom `-E`, banco de ductos, drenaje r≈145 pt
    pytest.param(DU06, 3, "TELECOM", marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
    pytest.param(DU06, 3, "DRENAJE", marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
])
def test_el_editor_dibuja_el_arco_reconocido(win, pdf, page, utility):
    """Cada codo reconocido se dibuja en el lienzo con SU esquina y SU radio:
    tangencias del editor = tangencias reconocidas (≤0.1 pt), sin recorte. También
    los dos codos de una curva en «S» que comparten el punto de inflexión."""
    win._open_pdf_path(str(pdf))
    win._load_page(page)
    res = rec.recognize_page(win.work_pdf_path or win.pdf_path, page, utility=utility,
                             zoom=win.zoom, doc=None)
    win._import_recognized_pipes([res])
    Z = win.zoom
    fil = [(pl, i, f) for pl in res.drawable for i, f in (pl.fillets or {}).items()]
    assert len(fil) >= (3 if utility != "DRENAJE" else 1)
    checked = 0
    for pl, i, f in fil:
        C = pl.pts_pdf[i]
        pipe = next(p for p in win.pipes if any(math.dist(C, q) < 0.5 for q in p["pts"]))
        s = win._structure_curve_at(*C)
        assert s is not None and math.dist((s["x"], s["y"]), C) < 0.5          # SU estructura CV
        info = win._curve_arc_info(s, pipe)
        assert info is not None and not info["clamped"], (C, f["r_px"] / Z)
        assert math.dist(info["corner"], C) < 1e-6
        # las tangencias del lienzo son las reconocidas
        dA = min(math.dist(info["p1"], f["a"]), math.dist(info["p1"], f["b"])) / Z
        dB = min(math.dist(info["p2"], f["a"]), math.dist(info["p2"], f["b"])) / Z
        assert dA <= 0.1 and dB <= 0.1, (C[0] / Z, C[1] / Z, dA, dB)
        checked += 1
    assert checked == len(fil)
