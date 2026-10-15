"""Valida `presentacion_1_3_1.digproj` (cada regla del Excel de normativas corregido
`normativas_1_3_1.xlsx` + novedades): cada celda da exactamente los avisos y arreglos que dice su
texto."""
import json
import os
import sys
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_presentacion_131 as G   # noqa: E402
import presentacion_131_casos as C     # noqa: E402


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory):
    ruta = str(tmp_path_factory.mktemp("pres") / "presentacion_1_3_1.digproj")
    win, datos = G.generar(ruta)
    yield ruta, win, datos
    win._dirty = False


def test_cada_caso_da_lo_que_dice_su_texto(proyecto):
    _ruta, win, datos = proyecto
    malos = G.comparar(win, datos)
    assert not malos, "\n".join(f"{c} {q}: esperado {e}, obtenido {o}" for c, q, e, o in malos)


def test_alerta_de_choque_y_solido(proyecto):
    _ruta, win, datos = proyecto
    assert len(win._choque_hits) == 1
    assert [s["cod"] for s in win.structures if s.get("solid")] == ["SÓLIDO-1"]
    assert any(db.assigned() == datos["X11"]["pipes"] for db in win.duct_banks)


def test_guarda_sin_pdf_y_reabre_con_tipo_y_amperaje(proyecto):
    ruta, win, _datos = proyecto
    with zipfile.ZipFile(ruta) as z:
        modelo = json.loads(z.read("model.json"))
    assert modelo["blank_canvas"] is True
    from ui.ventana.app_window import Main
    w2 = Main()
    w2._open_project_path(ruta)
    assert [(p.get("tipo"), p.get("amperaje")) for p in w2.pipes] == \
           [(p.get("tipo"), p.get("amperaje")) for p in win.pipes]
    w2._dirty = False


def test_exporta_tipo_y_amperaje_al_dxf(proyecto):
    _ruta, win, datos = proyecto
    import ezdxf
    from exportar import dxf_export
    doc = ezdxf.new(setup=True)
    dxf_export.merge_into(win, doc, marks=True)
    claves = [{v.split("=", 1)[0]: v.split("=", 1)[1] for _c, v in e.get_xdata("PDFCAD") if "=" in str(v)}
              for e in doc.modelspace() if e.has_xdata("PDFCAD")]
    assert any(c.get("XD_TIPO") == C.DIM and c.get("XD_AMPERAJE") == "500" for c in claves)


def test_el_excel_trae_cada_regla_nueva():
    cat = G.normativas()
    gas = {f["tipo"]: (f["diametros"], f["diam_min"], f["diam_max"]) for f in cat["diametros"] if f["utilidad"] == "GAS"}
    assert gas == {C.RES: ([0.5, 1, 1.5, 2], None, None), C.COM: ([2, 4], None, None), C.DP: ([], 6, None)}
    amp = sorted(tuple(f["amperaje"]) for f in cat["electricas"] if f.get("amperaje"))
    assert (400, None) in amp and (0, 320) in amp
    assert any(f.get("radio_fijo") == [3, 4] for f in cat["electricas"])


def test_cada_hoja_del_excel_tiene_casos_que_cumplen_y_que_no():
    hojas = {}
    for _c, _t, hoja, _r, _e, _f, avisos in C.CASOS_N:
        hojas.setdefault(hoja, set()).add(bool(avisos))
    assert set(hojas) == {"TIPOS", "PRESION-DIAMETROS", "PRESION-ACCESORIOS", "ELECT-TELECOM"}
    assert all(v == {True, False} for h, v in hojas.items() if h != "TIPOS")
