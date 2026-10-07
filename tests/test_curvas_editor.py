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
DU10 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf")


@pytest.mark.parametrize("pdf, page, utility", [
    pytest.param(DU08, 25, "ELECTRICO", marks=pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")),
    pytest.param(DU08, 25, "TELECOM", marks=pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")),
    # reporte 2026-09-29: curva en «S» de telecom `-E`, banco de ductos, drenaje r≈145 pt
    pytest.param(DU06, 3, "TELECOM", marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
    pytest.param(DU06, 3, "DRENAJE", marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
    # 2026-09-30: la «U» de telecom (178.7°) partida en dos codos del mismo arco
    pytest.param(DU06, 4, "TELECOM", marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
    # 2026-09-30: DU10 h.3, codo chico a guiones + curva r=126 pt tras un parche de trazo continuo
    pytest.param(DU10, 2, "ELECTRICO", marks=pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")),
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


def _xd(e):
    try:
        return [s for code, s in e.get_xdata("PDFCAD") if code == 1000]
    except Exception:
        return []


@pytest.mark.parametrize("pdf, page, utility, esquina", [
    # esquina de 90° de la línea «—TE—» (conduit: no hay caja en el vértice, se crea la CV)
    pytest.param(DU08, 25, "ELECTRICO", (839.2, 532.1),
                 marks=pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")),
    # quiebre de 62° entre dos buzones (gravedad: el buzón oculto del quiebre pasa a curva)
    pytest.param(DU06, 3, "DRENAJE", (1359.6, 1156.4),
                 marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
    # 2.º reporte (2026-10-07): línea eléctrica dibujada como UN trazo de tres rectas bajo la
    # bóveda; el núcleo marcó sus quiebres «curve» y quedaban como esquinas
    pytest.param(DU06, 4, "ELECTRICO", (906.24, 858.78),
                 marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
    pytest.param(DU06, 4, "ELECTRICO", (910.08, 869.16),
                 marks=pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")),
])
def test_quiebre_del_plano_entra_como_curva_minima(win, tmp_path, pdf, page, utility, esquina):
    """Pedido 2026-10-06 (regla de los ingenieros): un quiebre de una utilidad que no va a
    presión es una curva mal dibujada. Al importar entra como CV con el radio AUTOMÁTICO
    (6 × 12" = 6 ft, el mínimo de la regla), el editor la dibuja entera (sin recorte) y el
    DXF la manda al plugin como esquina curva sin radio escrito, sin buzón en ese vértice."""
    ezdxf = pytest.importorskip("ezdxf")
    win._open_pdf_path(str(pdf))
    win._load_page(page)
    res = rec.recognize_page(win.work_pdf_path or win.pdf_path, page, utility=utility,
                             zoom=win.zoom, doc=None)
    win._import_recognized_pipes([res])
    Z = win.zoom
    s = win._structure_curve_at(esquina[0] * Z, esquina[1] * Z)
    assert s is not None and s.get("quiebre") and not s.get("radius_ft") and not s.get("hidden")
    assert s["cod"].startswith("CV-")
    pipe = win._pipe_at_vertex(s["x"], s["y"])
    info = win._curve_arc_info(s, pipe)
    assert info is not None and not info["clamped"]
    assert math.isclose(info["r_px"], 6.0 * Z / win.scale, rel_tol=1e-6)
    quiebres = [x for x in win.structures if x.get("quiebre")]
    for x in quiebres:                                           # todas enteras en el editor
        i = win._curve_arc_info(x, win._pipe_at_vertex(x["x"], x["y"]))
        assert i is not None and not i["clamped"], (x["x"] / Z, x["y"] / Z)

    import config as C
    doc = ezdxf.new("R2010", setup=True)
    C.apply_imperial_header(doc)
    win._merge_into(doc, marks=True)
    out = tmp_path / "quiebres.dxf"
    doc.saveas(out)
    msp = ezdxf.readfile(out).modelspace()
    cx, cy = win._to_cad(s["x"], s["y"])
    en_punto = [_xd(e) for e in msp.query("POINT")
                if math.hypot(e.dxf.location.x - cx, e.dxf.location.y - cy) < 0.01]
    assert [x[0] for x in en_punto] == ["PDFCAD_CURVE"]           # una esquina curva, ningún buzón
    assert "RADIUS_FT=" in en_punto[0]                            # radio automático (lo calcula el plugin)
    vi = model_ops.nearest_vertex(pipe["pts"], s["x"], s["y"], 0.5)
    idx = win.pipes.index(pipe)
    fila = next(x for x in (_xd(e) for e in msp.query("LWPOLYLINE")) if f"PIPE_IDX={idx}" in x)
    no_bz = next(v for v in fila if v.startswith("NO_MANHOLE_VERTS="))[len("NO_MANHOLE_VERTS="):]
    assert str(vi) in no_bz.split(",")
    assert len([e for e in msp.query("POINT") if _xd(e)[:1] == ["PDFCAD_CURVE"]]) >= len(quiebres)
