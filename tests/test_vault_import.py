"""Bóvedas reconocidas que la vista previa muestra → todas llegan al editor.

Reporte del usuario 2026-10-05: «se reconoció el buzón sin líneas conectadas y al
importar no está». Antes quedaban fuera las bóvedas sin línea de capas de cajas de
paso / postes / propuestas (`V-ELEC-PBOX`, `V-COMM-PBOX`, `U-PROP-…-MH`, `Junction
Box`: 79 en los 4 PDFs de prueba) y TODAS las de agua/gas (red a presión: 50). Ahora
entran como caja suelta (rectangular = SÓLIDO, en Civil 3D un Solid3d aislado) sin
tocar las líneas.
"""
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import model_ops  # noqa: E402
import recognition as rec  # noqa: E402
from recognition_geom import Vault  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU06 = DOCS / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")


def _vault(layer, x0=100.0, y0=100.0, w=30.0, h=20.0):
    return Vault(x0, y0, x0 + w, y0 + h, n_paths=1, layer=layer, shape="rect",
                 outline=[(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], width=h, length=w)


@pytest.mark.parametrize("layer", ["X|V-COMM-PBOX", "X|V-ELEC-POLE", "X|U-PROP-ESFV-ELEC-MH",
                                   "X|N-Comm-Junction Box", "X|V-WATR-VALT"])
def test_boveda_sin_linea_de_cualquier_capa_se_importa(layer):
    v = _vault(layer)
    key = (round(v.center[0], 1), round(v.center[1], 1))
    out = rec._vaults_geometry([(False, layer, SimpleNamespace(vaults=[v]))], lambda q: (q[0] * 2, q[1] * 2),
                               20 / 72, 2.0, vault_orph={key: 1}, vault_seen={key: 1})
    assert len(out) == 1 and out[0]["orphan"] and out[0]["importable"]


def test_boveda_de_red_a_presion_entra_como_solido_suelto():
    """Agua/gas: la red no lleva estructuras (sus vértices siguen sin nodos); la
    bóveda reconocida entra como caja suelta: rectangular = SÓLIDO."""
    pipes = [{"layer": "AGUA", "pts": [(0, 0), (100, 0), (200, 0)], "vertex_kinds": ["end", "vault", "end"]}]
    structures = model_ops.rebuild_structures(pipes, [])
    assert structures == []                                          # presión: sin nodos
    vg = [{"center": (100.0, 0.0), "corners": [(90, -8), (110, -8), (110, 8), (90, 8)], "shape": "rect",
           "width_ft": 4.5, "length_ft": 5.0, "angle_deg": 0.0, "orphan": False, "importable": True,
           "layer": "X|V-WATR-VALT"},
          {"center": (400.0, 300.0), "corners": None, "circle": (400.0, 300.0, 9.0), "shape": "circle",
           "width_ft": 3.0, "length_ft": 3.0, "angle_deg": 0.0, "orphan": True, "importable": True}]
    done, created = model_ops.attach_vault_geometry(structures, vg, net="pressure", utility="AGUA", pipes=pipes)
    assert (done, created) == (2, 2)
    solid = next(s for s in structures if s["shape"] == "rect")
    ring = next(s for s in structures if s["shape"] == "circle")
    assert solid["standalone"] and solid["net"] == "pressure" and solid["solid"]
    assert solid["cod"].startswith("SÓLIDO-") and (solid["x"], solid["y"]) == (100.0, 0.0)
    assert solid["utility"] == "AGUA" and solid["xdata"]["auto"]          # capa de origen como referencia
    assert ring["standalone"] and not ring.get("solid") and ring["cod"].startswith("CAJA-")
    # rebuild las conserva sin agregar nodos, nada se oculta y re-importar no duplica
    again = model_ops.rebuild_structures(pipes, structures)
    assert len(again) == 2 and model_ops.hide_soft_vertex_structures(pipes, again) == 0
    assert model_ops.attach_vault_geometry(again, vg, net="pressure", utility="AGUA", pipes=pipes) == (2, 0)
    assert pipes[0]["pts"] == [(0, 0), (100, 0), (200, 0)]           # la línea, intacta


def test_dxf_lleva_el_solido_de_presion():
    """El DXF exporta el SÓLIDO de agua/gas (el plugin lo dibuja como Solid3d); una
    caja de presión que no es sólido sigue fuera (esa red no lleva nodos)."""
    ezdxf = pytest.importorskip("ezdxf")
    import dxf_export
    structures = []
    vg = [{"center": (100.0, 0.0), "corners": [(90, -8), (110, -8), (110, 8), (90, 8)], "shape": "rect",
           "width_ft": 4.5, "length_ft": 5.0, "angle_deg": 0.0, "importable": True},
          {"center": (400.0, 300.0), "corners": None, "circle": (400.0, 300.0, 9.0), "shape": "circle",
           "width_ft": 3.0, "length_ft": 3.0, "angle_deg": 0.0, "importable": True}]
    model_ops.attach_vault_geometry(structures, vg, net="pressure", utility="GAS")
    win = SimpleNamespace(structures=structures, show_bz_labels=False, civil_year=None,
                          _to_cad=lambda x, y: (x / 10.0, -y / 10.0))
    doc = ezdxf.new("R2010")
    doc.appids.add("PDFCAD")
    dxf_export._export_structures(win, doc, doc.modelspace())
    rows = []
    for e in doc.modelspace():
        if e.has_xdata("PDFCAD"):
            rows.append({s.split("=", 1)[0]: s.split("=", 1)[1]
                         for code, s in e.get_xdata("PDFCAD") if code == 1000 and "=" in s})
    assert len(rows) == 1
    assert rows[0]["NET_KIND"] == "pressure" and rows[0]["SOLID"] == "1"
    assert math.isclose(float(rows[0]["SOLID_CX"]), 10.0) and rows[0]["STRUCT_ID"].startswith("SÓLIDO-")


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
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


def _on_vault(s, vg):
    cx, cy = vg["center"]
    return (math.hypot(float(s["x"]) - cx, float(s["y"]) - cy) <= 12.0
            or model_ops._dentro_de_boveda(vg, float(s["x"]), float(s["y"])))


@needs_pdf
@pytest.mark.parametrize("page,utility", [(13, "AGUA"), (9, "TELECOM")])
def test_cada_boveda_de_la_vista_previa_llega_al_editor(win, page, utility):
    """DU06 h.14: válvula de agua sin línea (red a presión); h.10: caja de paso de
    telecom (`V-COMM-PBOX`) sin línea. Antes ninguna de las dos se importaba."""
    win._open_pdf_path(str(DU06))
    win._load_page(page)
    res = rec.recognize_page(win.work_pdf_path or win.pdf_path, page, utility=utility, zoom=win.zoom)
    assert any(vg["orphan"] for vg in res.vaults_geo)
    lines = [list(pl.pts_pdf) for pl in res.drawable]
    win._import_recognized_pipes([res])
    assert [p["pts"] for p in win.pipes] == [[(float(x), float(y)) for x, y in pts] for pts in lines]
    for vg in res.vaults_geo:
        assert any(_on_vault(s, vg) for s in win.structures), vg.get("layer")
    alone = [s for s in win.structures if s.get("standalone")]
    assert alone and all(s.get("utility") == utility for s in alone)
