"""Valida la parte de los escenarios que se puede comprobar sin Civil 3D: los
marcadores de cruce de la app, el guardado/reapertura del .digproj y el DXF.
Lo que pasa DENTRO de Civil 3D se revisa a mano con el texto de cada celda."""
import json
import os
import sys
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_escenarios as G   # noqa: E402


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory):
    ruta = str(tmp_path_factory.mktemp("esc") / "escenarios.digproj")
    win, datos = G.generar(ruta)
    return ruta, win, datos


def test_marcadores_de_la_app(proyecto):
    _ruta, win, datos = proyecto
    fallos = [f"{cod}: esperado {esp}, obtenido {obt}"
              for cod, _pt, esp, obt in G.validar(win, datos) if esp != obt]
    assert not fallos, "\n".join(fallos)


def test_ningun_caso_toca_a_otro(proyecto):
    _ruta, win, datos = proyecto
    assert G.marcadores_fuera_de_lugar(win, datos) == []


def test_guarda_sin_pdf_y_reabre_igual(proyecto):
    ruta, win, _datos = proyecto
    with zipfile.ZipFile(ruta) as z:
        assert "source.pdf" not in z.namelist()
        modelo = json.loads(z.read("model.json"))
    assert modelo["blank_canvas"] is True

    from app_window import Main
    w2 = Main()
    w2._open_project_path(ruta)
    assert w2.blank_canvas and w2.doc is None
    assert len(w2.pipes) == len(win.pipes)
    assert len(w2.cross_connections) == len(win.cross_connections) == 7
    assert abs(w2.scale - win.scale) < 1e-12


def test_exporta_dxf(proyecto):
    _ruta, win, _datos = proyecto
    import ezdxf
    import dxf_export
    doc = ezdxf.new(setup=True)
    dxf_export.merge_into(win, doc, marks=True)

    def marcador(e):
        xd = e.get_xdata("PDFCAD") if e.has_xdata("PDFCAD") else []
        return xd[0][1] if xd else ""
    ents = list(doc.modelspace())
    assert sum(marcador(e) == "PDFCAD_PIPE" for e in ents) == len(win.pipes)
    assert sum(marcador(e) == "PDFCAD_CROSS_CONNECT" for e in ents) == 7
    nombres = [e for e in ents if marcador(e) == "PDFCAD_PIPE"
               and any(v == "NET_NAME=Linea Norte" for _c, v in e.get_xdata("PDFCAD"))]
    assert len(nombres) == 2
