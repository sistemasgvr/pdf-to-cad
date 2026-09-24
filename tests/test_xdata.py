"""Datos extendidos (xdata): capa OCG de origen como referencia + campos del
usuario, desde el reconocimiento hasta el .digproj y el DXF."""
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import xdata  # noqa: E402


def test_parse_layer_drenaje_con_xref():
    f = xdata.parse_layer("PS89616000-A1-UD-REF-PROP_SD|C-STRM-UNGD-N")
    assert f[xdata.F_OCG] == "PS89616000-A1-UD-REF-PROP_SD|C-STRM-UNGD-N"
    assert f[xdata.F_XREF] == "PS89616000-A1-UD-REF-PROP_SD"
    assert f[xdata.F_LAYER] == "C-STRM-UNGD-N"
    assert f[xdata.F_DISC].startswith("C — Civil")
    assert f[xdata.F_SYSTEM].startswith("STRM — Pluvial")
    assert f[xdata.F_LOCATION] == "UNGD — Subterránea"
    assert f[xdata.F_STATUS] == "N — Nueva (obra nueva)"
    assert xdata.F_MODS not in f


@pytest.mark.parametrize("name,status,system,mods", [
    ("C-ELEC-UNGD-E", "E — Existente", "ELEC — Eléctrico", None),
    ("C-ELEC-UNGD-A", "A — Abandonada", "ELEC — Eléctrico", None),
    ("C-ELEC-UNGD-D", "Existente a demoler", "ELEC — Eléctrico", None),
    ("C-ELEC-3MI-UGND-N", "N — Nueva (obra nueva)", "ELEC — Eléctrico", "3MI"),     # paquete DU10
    ("C-STRM-UNGD-NPLT", None, "STRM — Pluvial (drenaje de tormenta)", "NPLT (no imprimible)"),
    ("C-STRM-UNGD-STRC-N", "N — Nueva (obra nueva)", "STRM — Pluvial (drenaje de tormenta)", "STRC (estructura)"),
    ("C-STRM-CTCH-BASN-E", "E — Existente", "STRM — Pluvial (drenaje de tormenta)", "CTCH-BASN (sumidero)"),
])
def test_parse_layer_variantes(name, status, system, mods):
    f = xdata.parse_layer(name)
    assert xdata.F_XREF not in f and f[xdata.F_LAYER] == name
    assert f[xdata.F_SYSTEM] == system
    if status is None:
        assert xdata.F_STATUS not in f
    else:
        assert status in f[xdata.F_STATUS]
    assert f.get(xdata.F_MODS) == mods


def test_capa_desconocida_y_vacia():
    f = xdata.parse_layer("XYZ-CAPA-RARA")                 # no sigue el estándar: se muestra tal cual
    assert f[xdata.F_LAYER] == "XYZ-CAPA-RARA" and f[xdata.F_SYSTEM] == "XYZ"
    assert xdata.F_DISC not in f
    assert xdata.parse_layer("") == {} and xdata.make(None) is None


def test_usuario_no_pisa_lo_automatico_y_valida():
    obj = {"xdata": xdata.make("C-STRM-UNGD-N", "DU06 · Hoja 4")}
    assert xdata.get(obj)[xdata.AUTO][xdata.F_ORIGIN] == "DU06 · Hoja 4"
    xdata.set_user(obj, {"Contratista": "ACME", " ": "x"})
    assert xdata.get(obj)[xdata.USER] == {"Contratista": "ACME"}
    xdata.set_auto(obj, xdata.auto_fields("C-STRM-UNGD-E"))        # re-importar: el usuario queda
    assert xdata.get(obj)[xdata.USER] == {"Contratista": "ACME"}
    assert "E — Existente" in xdata.get(obj)[xdata.AUTO][xdata.F_STATUS]
    auto = xdata.get(obj)[xdata.AUTO]
    assert xdata.validate_user([("Capa", "x")], auto)                 # nombre de un campo automático
    assert xdata.validate_user([("A", "1"), ("a", "2")], auto)        # repetido
    assert xdata.validate_user([("", "valor")], auto)                 # valor sin nombre
    assert xdata.validate_user([("Obs", "ok"), ("", "")], auto) is None
    plain = {}
    xdata.set_user(plain, {})
    assert "xdata" not in plain


def test_items_del_dxf():
    obj = {"xdata": xdata.make("PS|C-STRM-UNGD-N", "DU06 · Hoja 4")}
    xdata.set_user(obj, {"Observación": "Revisar cota", "Nº plano": "UD-204"})
    items = xdata.dxf_items(obj)
    assert "XD_CAPA_OCG=PS|C-STRM-UNGD-N" in items and "XD_CAPA=C-STRM-UNGD-N" in items
    assert "XD_ORIGEN=DU06 · Hoja 4" in items
    assert "XDU_OBSERVACION=Revisar cota" in items and "XDU_NO_PLANO=UD-204" in items
    long = {"xdata": {"auto": {}, "user": {"Nota": "x" * 400}}}
    assert all(len(s) <= 250 for s in xdata.dxf_items(long))


def test_origen_por_pieza_de_la_hoja_compuesta():
    pieces = [((0, 0, 100, 100), "a.pdf · Hoja 3"), ((100, 0, 200, 100), "a.pdf · Hoja 4")]
    assert xdata.origin_label([(120, 50), (180, 50)], pieces, "?") == "a.pdf · Hoja 4"
    assert xdata.origin_label([(500, 50)], pieces, "?") == "?"


def test_reconocimiento_lleva_la_capa_a_la_pipe():
    import recognition as rec
    pl = rec.RecognizedPolyline("XREF|C-STRM-UNGD-N", "DRENAJE", [(0, 0), (10, 0)], "drain_ungd",
                                ["end", "end"])
    res = types.SimpleNamespace(drawable=[pl], scale_ft_per_pt=20.0 / 72.0)
    (p,) = rec.pipes_from_recognition(res, layer="DRENAJE", origin=lambda pts: "DU06 · Hoja 4")
    assert p["layer"] == "DRENAJE"                                    # sigue siendo drenaje
    auto = p["xdata"]["auto"]
    assert auto[xdata.F_LAYER] == "C-STRM-UNGD-N" and auto[xdata.F_ORIGIN] == "DU06 · Hoja 4"
    json.dumps(p["xdata"])                                            # va tal cual al .digproj


def test_estructura_reconocida_y_rebuild_conservan_xdata():
    from model_ops import attach_vault_geometry, rebuild_structures
    pipes = [{"layer": "DRENAJE", "pts": [(0.0, 0.0), (100.0, 0.0)]}]
    structures = rebuild_structures(pipes, [])
    vg = [{"center": (100.0, 0.0), "shape": "rect", "width_ft": 4.0, "length_ft": 6.0, "angle_deg": 0.0,
           "layer": "XREF|C-STRM-UNGD-STRC-N", "importable": True}]
    attach_vault_geometry(structures, vg, net="gravity", utility="DRENAJE", origin=lambda c: "DU06 · Hoja 4")
    s = next(o for o in structures if o.get("xdata"))
    assert s["xdata"]["auto"][xdata.F_LAYER] == "C-STRM-UNGD-STRC-N"
    xdata.set_user(s, {"Tapa": "36 in"})
    again = rebuild_structures(pipes, structures)                    # se regenera por coordenada
    s2 = next(o for o in again if o.get("xdata"))
    assert s2["xdata"]["user"] == {"Tapa": "36 in"} and abs(s2["x"] - 100.0) < 1e-9


def test_dxf_exporta_xdata_de_pipe_y_estructura():
    ezdxf = pytest.importorskip("ezdxf")
    import dxf_export
    from test_project_io import _fake_dxf_win
    win = _fake_dxf_win()
    win.duct_banks = []
    win.pipes[0]["xdata"] = xdata.make("C-ELEC-UNGD-E", "DU06 · Hoja 13")
    xdata.set_user(win.pipes[0], {"Observación": "cable 3#4/0"})
    win.structures = [{"cod": "CAJA-1", "x": 100.0, "y": 200.0, "net": "conduit", "covered": True,
                       "xdata": xdata.make("C-ELEC-UNGD-VALT-E")}]
    doc = ezdxf.new("R2018", setup=True)
    dxf_export.merge_into(win, doc, marks=True)

    def tags(e):
        return {str(t.value).split("=", 1)[0]: str(t.value).split("=", 1)[1]
                for t in e.get_xdata("PDFCAD") if t.code == 1000 and "=" in str(t.value)}
    msp = doc.modelspace()
    (poly,) = [e for e in msp if e.dxftype() == "LWPOLYLINE"]
    xp = tags(poly)
    assert xp["XD_CAPA"] == "C-ELEC-UNGD-E" and xp["XD_ORIGEN"] == "DU06 · Hoja 13"
    assert xp["XDU_OBSERVACION"] == "cable 3#4/0" and xp["PIPE_IDX"] == "0"   # lo de siempre sigue
    pts = [e for e in msp if e.dxftype() == "POINT" and e.get_xdata("PDFCAD")
           and any(str(t.value) == "PDFCAD_STRUCT" for t in e.get_xdata("PDFCAD"))]
    assert pts and tags(pts[0])["XD_CAPA"] == "C-ELEC-UNGD-VALT-E"


def test_modal_campos_del_pdf_bloqueados_y_del_usuario_editables():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from PySide6 import QtCore
    import xdata_dialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
    obj = {"xdata": xdata.make("XREF|C-STRM-UNGD-N", "DU06 · Hoja 4")}
    xdata.set_user(obj, {"Contratista": "ACME"})
    dlg = xdata_dialog.XDataDialog(None, "Utilidad #1", xdata.get(obj))
    n_auto = len(xdata.get(obj)[xdata.AUTO])
    assert dlg.table.rowCount() == n_auto + 1
    for r in range(n_auto):                                  # del PDF: no editables ni borrables
        assert not (dlg.table.item(r, 1).flags() & QtCore.Qt.ItemIsEditable)
        dlg.table.selectRow(r)
        assert not dlg.btn_remove.isEnabled()
    dlg.table.selectRow(n_auto)
    assert dlg.btn_remove.isEnabled()
    dlg._add_user_row()
    r = dlg.table.rowCount() - 1
    dlg.table.item(r, 0).setText("Observación"); dlg.table.item(r, 1).setText("revisar")
    assert dlg.user_fields() == {"Contratista": "ACME", "Observación": "revisar"}
    dlg.table.clearSelection(); dlg.table.selectRow(n_auto); dlg._remove_row()
    assert dlg.user_fields() == {"Observación": "revisar"}
    dlg.table.item(dlg.table.rowCount() - 1, 0).setText("Capa")   # choca con un campo del PDF
    assert xdata.validate_user(dlg.user_rows(), dlg._auto)
    dlg.close()
