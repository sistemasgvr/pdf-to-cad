"""Pruebas de humo del modelo Georef: round-trip to_dict / from_dict.

Asegura que lo que se persiste en el proyecto (.digproj) — matriz, epsg y el
código de sistema de coordenadas (Huso) `cs_code` — sobrevive el guardado y la
carga sin perderse ni cambiar.
"""
from geo import georef


def _sample():
    # Matriz de similaridad reflejada (det<0), como la que produce fit().
    M = [[2.5, 0.3, 6_444_000.0], [0.3, -2.5, 1_883_000.0], [0.0, 0.0, 1.0]]
    return georef.Georef(matrix=M, epsg=2229, kind="similarity", rms=1.23,
                         points=[{"px": [10, 20], "world": [1.0, 2.0], "label": "A"}],
                         cs_code="CA83VF")


def test_roundtrip_conserva_cs_code_y_campos():
    g = _sample()
    d = g.to_dict()
    assert d is not None
    assert d["cs_code"] == "CA83VF"
    assert d["epsg"] == 2229
    assert d["matrix"] == g.matrix

    g2 = georef.Georef.from_dict(d)
    assert g2.cs_code == "CA83VF"
    assert g2.epsg == 2229
    assert g2.matrix == g.matrix
    assert g2.active()


def test_from_dict_vacio_da_georef_inactiva():
    g = georef.Georef.from_dict(None)
    assert not g.active()
    assert g.cs_code == ""


def test_cs_code_por_defecto_es_vacio():
    g = georef.Georef(matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], epsg=2229)
    assert g.cs_code == ""
