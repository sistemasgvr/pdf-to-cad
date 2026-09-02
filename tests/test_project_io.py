"""Pruebas de humo de la serialización del proyecto (project_io.py), sin Qt.

Cubren la lógica pura que antes vivía enterrada en la ventana y que tenía bugs
sutiles de persistencia:
  - Las llaves de las cotas por vértice (vertex_inv / _out / _in) vuelven a int al
    abrir (json las guarda como str) → si no, la edición por tramo salía vacía.
  - Las zonas de borrado antiguas (listas sueltas) se envuelven a dict.
  - El objeto Georef (incluido cs_code) se reconstruye.
  - Round-trip build → parse conserva los datos.
"""
import types

import civil_catalog as _cc
import project_io
from geo import georef


class _Derot:
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0


def _fake_win():
    g = georef.Georef(
        matrix=[[2.5, 0.3, 6_444_000.0], [0.3, -2.5, 1_883_000.0], [0.0, 0.0, 1.0]],
        epsg=2229, kind="similarity", rms=1.1, cs_code="CA83VF")
    return types.SimpleNamespace(
        pipes=[{"layer": "AGUA", "pts": [(0, 0), (10, 0)],
                "vertex_inv_out": {1: 100.5}, "vertex_inv_in": {1: 99.0}}],
        leaders=[], text_marks=[],
        erase_regions=[{"pts": [(0, 0)], "enabled": True}],
        structures=[{"cod": "BZ-1", "x": 5, "y": 0}],
        ref_centerlines=[],
        georef=g, work_unit="ft", civil_year=2025,
        scale=20 / 72.0, zoom=3.5, rot=0, W=800, H=600, derot=_Derot(),
        pdf_path=r"C:\planos\11-prueba.pdf")


def test_build_model_dict_incluye_campos_clave():
    win = _fake_win()
    m = project_io.build_model_dict(win)
    assert m["version"]
    assert m["civil_year"] == 2025
    assert m["georef"]["cs_code"] == "CA83VF"
    assert m["tf"]["scale"] == win.scale
    assert m["tf"]["derot"] == [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    assert m["pdf_name"] == "11-prueba.pdf"


def test_parse_castea_llaves_de_cotas_a_int():
    # Como quedaría en el JSON: llaves string y erase_regions vieja (lista suelta).
    model = {
        "tf": {"scale": 0.2, "zoom": 3.0, "rot": 0, "W": 800, "H": 600,
               "derot": [1, 0, 0, 1, 0, 0]},
        "pipes": [{"pts": [(0, 0), (1, 1)],
                   "vertex_inv": {"1": "100.25"},
                   "vertex_inv_out": {"2": "98.5"}}],
        "erase_regions": [[(0, 0), (1, 0), (1, 1)]],   # formato viejo: lista, no dict
        "georef": {"matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "epsg": 2229,
                   "kind": "similarity", "cs_code": "CA83VF"},
        "civil_year": 2027, "civil_lang": "enu",
    }
    data = project_io.parse_model(model)
    p = data["pipes"][0]
    assert p["vertex_inv"] == {1: 100.25}          # int y float, no str
    assert p["vertex_inv_out"] == {2: 98.5}
    assert p["unit"] == "ft"
    assert data["erase_regions"][0] == {"pts": [(0, 0), (1, 0), (1, 1)], "enabled": True}
    assert data["georef"].active() and data["georef"].cs_code == "CA83VF"
    assert data["civil_year"] == 2027 and data["civil_lang"] == "enu"
    assert data["work_unit"] == "ft"


def test_parse_retrocompat_campos_ausentes():
    model = {"tf": {"scale": 0.2, "zoom": 1, "rot": 0, "W": 10, "H": 10,
                    "derot": [1, 0, 0, 1, 0, 0]}}
    data = project_io.parse_model(model)
    assert data["pipes"] == [] and data["structures"] == [] and data["ref_centerlines"] == []
    assert not data["georef"].active()      # sin georref → inactiva
    assert data["civil_year"] is None


def test_roundtrip_build_parse_conserva_datos():
    win = _fake_win()
    _cc.set_current_lang("esp")
    try:
        m = project_io.build_model_dict(win)
    finally:
        _cc.set_current_lang(None)
    data = project_io.parse_model(m)
    assert data["scale"] == win.scale
    assert data["structures"] == win.structures
    assert data["georef"].cs_code == "CA83VF"
    # las cotas por vértice sobreviven como int (build las tiene int, json→parse las
    # mantiene int porque aquí no pasó por json; el test de arriba cubre el caso str)
    assert data["pipes"][0]["vertex_inv_out"] == {1: 100.5}
