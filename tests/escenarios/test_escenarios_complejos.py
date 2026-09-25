"""Valida la segunda tanda de escenarios (accesorios sólidos y casos no
contemplados) en lo que se puede comprobar sin Civil 3D. Lo que pasa DENTRO de
Civil 3D se revisa a mano con el texto de cada celda."""
import json
import os
import re
import sys
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_escenarios_complejos as G   # noqa: E402

WYESOLIDO_CS = os.path.join(G.base._RAIZ, "API-CIVIL", "proyecto1", "proyecto1", "WyeSolido.cs")


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory):
    ruta = str(tmp_path_factory.mktemp("esc2") / "escenarios_complejos.digproj")
    win, datos = G.generar(ruta)
    return ruta, win, datos


def test_marcadores_de_la_app(proyecto):
    _ruta, win, datos = proyecto
    fallos = [f"{cod}: esperado {esp}, obtenido {obt}"
              for cod, _pt, esp, obt in G.validar(win, datos) if esp != obt]
    assert not fallos, "\n".join(fallos)


def test_marcadores_apilados(proyecto):
    _ruta, win, datos = proyecto
    fallos = [f"{cod}: esperados {esp}, hay {obt}"
              for cod, _pt, esp, obt in G.cuentas(win, datos) if esp != obt]
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
    assert len(w2.cross_connections) == len(win.cross_connections) == 8
    assert abs(w2.scale - win.scale) < 1e-12


def test_exporta_dxf(proyecto):
    _ruta, win, _datos = proyecto
    import ezdxf
    import dxf_export
    doc = ezdxf.new(setup=True)
    dxf_export.merge_into(win, doc, marks=True)

    def xd(e):
        return e.get_xdata("PDFCAD") if e.has_xdata("PDFCAD") else []
    ents = list(doc.modelspace())
    tubos = [e for e in ents if xd(e) and xd(e)[0][1] == "PDFCAD_PIPE"]
    assert len(tubos) == len(win.pipes)
    assert sum(1 for e in ents if xd(e) and xd(e)[0][1] == "PDFCAD_CROSS_CONNECT") == 8
    nombres = {v for e in tubos for _c, v in xd(e) if v.startswith("NET_NAME=") and v != "NET_NAME="}
    assert nombres == {"NET_NAME=Linea Este", "NET_NAME=Ramal Sur"}
    assert sum(1 for e in tubos if any(v == "ABANDONED=1" for _c, v in xd(e))) == 1


def test_espejo_de_wyesolido():
    """Las cifras de las celdas salen de G.WS; tienen que ser las del plugin."""
    with open(WYESOLIDO_CS, encoding="utf-8") as f:
        cs = dict(re.findall(r"private const double (\w+) = ([\d.]+);", f.read()))
    distintas = {k: (v, cs.get(k)) for k, v in G.WS.items()
                 if k not in cs or abs(float(cs[k]) - v) > 1e-12}
    assert not distintas, f"WyeSolido.cs cambió; regenera el .digproj: {distintas}"
