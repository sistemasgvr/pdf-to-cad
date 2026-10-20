"""Guardar el DXF con `exportar/dxf_rapido` da EL MISMO archivo que ezdxf (2026-10-19): solo cambian, como
entre dos guardados cualesquiera, la hora de guardado, el GUID de versión y la marca de ezdxf."""
import io
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import pytest  # noqa: E402

from exportar import dxf_rapido  # noqa: E402


def _escribir(doc, rapido):
    s = io.StringIO()
    if rapido:
        with dxf_rapido.escritura_rapida():
            doc.write(s)
    else:
        doc.write(s)
    return s.getvalue().split("\n")


_PROPIAS_DEL_GUARDADO = {"$TDUPDATE", "$TDUUPDATE", "$VERSIONGUID", "$TDINDWG", "$TDUSRTIMER"}


def _de_cada_guardado(lineas, k):
    """Líneas que ezdxf cambia en CADA guardado: hora y GUID de la cabecera y su marca «1.4.4 @ fecha»."""
    return (k >= 2 and lineas[k - 2].strip() in _PROPIAS_DEL_GUARDADO) or bool(
        re.match(r"^\d+\.\d+\.\d+(\S*)? @ \d{4}-", lineas[k]))


def _iguales(doc):
    a, b = _escribir(doc, False), _escribir(doc, True)
    assert len(a) == len(b)
    distintas = [k for k, (x, y) in enumerate(zip(a, b)) if x != y]
    assert all(_de_cada_guardado(a, k) for k in distintas), [(k, a[k - 2], a[k], b[k]) for k in distintas][:5]
    return a


def _doc_variado():
    doc = ezdxf.new("R2010", setup=True)
    doc.appids.add("PDFCAD")
    msp = doc.modelspace()
    doc.layers.add("UTIL", color=3)
    msp.add_line((0, 0), (10.25, 3.5), dxfattribs={"layer": "UTIL", "color": 1, "lineweight": 35})
    msp.add_line((1, 2, 3), (4, 5, 6))
    msp.add_text("Hola «ñ» 12\"", dxfattribs={"height": 2.5, "rotation": 30, "insert": (5, 6)})
    pl = msp.add_lwpolyline([(0, 0, 0, 0, 0.5), (3, 4), (7, 1)], format="xyseb", close=True)
    pl.set_xdata("PDFCAD", [(1000, "PDFCAD_PIPE"), (1000, "DIAMETER=8"), (1040, 3.25), (1070, 7)])
    msp.add_circle((2, 2), 1.5)
    msp.add_arc((0, 0), 3, 10, 200)
    msp.add_mtext("línea 1\\Plínea 2", dxfattribs={"char_height": 1.2})
    msp.add_point((1, 1, 0))
    h = msp.add_hatch(color=2)
    h.paths.add_polyline_path([(0, 0), (4, 0), (4, 4)], is_closed=True)
    msp.add_spline([(0, 0), (1, 2), (3, 1), (4, 4)])
    msp.add_ellipse((0, 0), major_axis=(3, 0), ratio=0.5)
    blk = doc.blocks.new("MARCA")
    blk.add_circle((0, 0), 1)
    msp.add_blockref("MARCA", (8, 8), dxfattribs={"xscale": 2, "rotation": 15})
    return doc


def test_mismo_archivo_con_entidades_variadas():
    _iguales(_doc_variado())


def test_guardar_queda_igual_y_vuelve_el_escritor_de_ezdxf(tmp_path):
    from ezdxf.entities import dxfns
    antes = dxfns.DXFNamespace.export_dxf_attribs
    doc = _doc_variado()
    dxf_rapido.guardar(doc, tmp_path / "a.dxf")
    assert dxfns.DXFNamespace.export_dxf_attribs is antes
    leido = ezdxf.readfile(tmp_path / "a.dxf")
    assert len(leido.modelspace()) == len(doc.modelspace())


def test_mismo_archivo_con_un_proyecto_real():
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ruta = os.path.join(os.path.dirname(__file__), "escenarios", "presentacion_1_3_1.digproj")
    if not os.path.exists(ruta):
        pytest.skip("sin el proyecto de presentación")
    from ui.ventana.app_window import Main
    w = Main()
    w._info = lambda *a, **k: None
    w._open_project_path(ruta)
    doc = ezdxf.new("R2010", setup=True)
    w._merge_into(doc, marks=True)
    w._set_geodata(doc)
    w._set_plan_view(doc)
    texto = _iguales(doc)
    assert any("PDFCAD_PIPE" in t for t in texto)
    w._dirty = False
    w.close()
