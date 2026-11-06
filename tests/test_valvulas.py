"""Válvulas: lectura por capa, leyenda, forma y a mano, sin tocar las líneas, y de la ventana al DXF."""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
ezdxf = pytest.importorskip("ezdxf")

from nucleo import valvulas as V  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_trabajo as trabajo  # noqa: E402
from reconocimiento import recognition_valvulas as RV  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
IND = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
DU06 = DOCS / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"
WATER_S = IND / "QS Water_Indian School_South.pdf"
SOUTHWEST = IND / "APUNTES ING" / "Southwest Gas Combined 811 Records (1) 37.pdf"


def _necesita(ruta):
    return pytest.mark.skipif(not ruta.is_file(), reason=f"{ruta.name} no disponible")


class _Linea:
    def __init__(self, pts):
        self.pts_pdf = pts


class _Resultado:
    def __init__(self, utility, *lineas):
        self.utility = utility
        self.drawable = [_Linea(p) for p in lineas]


@pytest.mark.parametrize("capa, si", [
    ("E0129|V-WATR-VALV", True), ("x|V-NGAS-VALV", True), ("x|C-WATR-GV-E", True), ("x|V-IRRG-VALV", True),
    ("x|C-WATR-UNGD-E", False), ("x|V-WATR-METR", False), ("x|V-FIRE-HYDR", False), ("x|C-ANNO-VALV-TEXT", False)])
def test_capas_de_valvula(capa, si):
    assert RV.es_capa_valvula(capa) is si


def test_utilidad_y_tipo_por_la_capa():
    assert RV.utilidad_de_capa("x|V-NGAS-VALV") == "GAS"
    assert RV.utilidad_de_capa("x|V-UTIL-VALV") == ""
    assert RV.tipo_de_capa("x|C-WATR-GV-E") == "Compuerta"
    assert RV.tipo_de_capa("x|V-WATR-VALV") == ""            # la forma no da el tipo


@pytest.mark.parametrize("texto, tipo, estado", [
    ("Standard Vlv - Closed", "De línea", "cerrada"), ("Blow-Off Vlv - Open", "Purga", "abierta"),
    ("Sgl Check Vlv - Open", "Retención", "abierta"), ("Dbl Check Vlv - Closed", "Retención doble", "cerrada"),
    ("Water PRVs", "Reguladora de presión", ""), ("Butterfly valve", "Mariposa", ""), ("A.V.", "", "")])
def test_tipo_y_estado_por_el_texto(texto, tipo, estado):
    assert (RV.tipo_de(texto), RV.estado_de(texto)) == (tipo, estado)


def _trazo(puntos):
    P = fitz.Point
    return {"items": [("l", P(a), P(b)) for a, b in zip(puntos, puntos[1:] + puntos[:1])]}


def test_mono_y_lo_que_no_lo_es():
    assert RV.es_mono(_trazo([(0, 0), (3, 0), (0, 4), (3, 4)]))
    assert not RV.es_mono(_trazo([(0, 0), (3, 0), (3, 4), (0, 4)]))          # rectángulo
    assert not RV.es_mono(_trazo([(0, 0), (30, 0), (0, 40), (30, 40)]))      # demasiado grande


def test_completar_forma_solo_sobre_una_linea_y_hereda_utilidad():
    linea = [(0.0, 10.0), (100.0, 10.0)]
    sobre = V.nueva(50, 10.5, origen=V.FORMA, certeza=V.POR_CONFIRMAR)
    lejos = V.nueva(50, 80, origen=V.FORMA, certeza=V.POR_CONFIRMAR)
    out = RV.completar([sobre, lejos], [_Resultado("AGUA", linea)], 1.0)
    assert len(out) == 1 and out[0]["utilidad"] == "AGUA" and out[0]["en_linea"]


def test_completar_quita_las_de_una_utilidad_no_reconocida_y_deja_la_suelta():
    linea = [(0.0, 10.0), (100.0, 10.0)]
    gas = V.nueva(50, 10, "GAS")
    suelta = V.nueva(50, 80, "AGUA")
    out = RV.completar([gas, suelta], [_Resultado("AGUA", linea)], 1.0)
    assert [v["utilidad"] for v in out] == ["AGUA"] and not out[0]["en_linea"]
    assert RV.avisos(out) == ["Válvulas sin línea cerca: 1"]


def test_tuberia_de_su_utilidad_hasta_5_pt_y_sin_utilidad_solo_encima():
    linea = [(0.0, 10.0), (100.0, 10.0)]
    res = [_Resultado("AGUA", linea)]
    assert RV.completar([V.nueva(50, 14, "AGUA")], res, 1.0)[0]["en_linea"]
    assert not RV.completar([V.nueva(50, 16, "AGUA")], res, 1.0)[0]["en_linea"]
    sin = RV.completar([V.nueva(50, 14)], res, 1.0)[0]
    assert sin["utilidad"] == "" and not sin["en_linea"]
    assert RV.completar([V.nueva(50, 14, origen=V.FORMA, certeza=V.POR_CONFIRMAR)], res, 1.0) == []


def test_juntar_no_repite():
    a = V.nueva(10, 10, "AGUA")
    assert len(V.juntar([a], [V.nueva(11, 10, "AGUA"), V.nueva(11, 10, "GAS"), V.nueva(40, 10, "AGUA")])) == 3


def test_relacion_da_la_tuberia_de_su_utilidad_y_el_rumbo():
    pipes = [dict(layer="GAS", pts=[(0, 0), (100, 0)]), dict(layer="AGUA", pts=[(50, -50), (50, 50)])]
    i, _d, rumbo = V.relacion(V.nueva(50, 0, "AGUA"), pipes, 2.0)
    assert i == 1 and rumbo == pytest.approx(90.0)


@_necesita(DU06)
def test_du06_capas_sin_tocar_las_lineas():
    con = trabajo.reconocer_hoja(str(DU06), 11, zoom=3.5, utilities=("AGUA", "GAS"))
    sin = []
    with fitz.open(DU06) as doc:
        for u in ("AGUA", "GAS"):
            sin.append(rec.recognize_page(str(DU06), 11, utility=u, zoom=3.5, doc=doc))
    assert [pl.pts_pdf for r in con for pl in r.drawable] == [pl.pts_pdf for r in sin for pl in r.drawable]
    assert len(con[0].valvulas) == 5 and all(v["utilidad"] == "AGUA" for v in con[0].valvulas)
    assert all(v["certeza"] == V.SEGURA and v["origen"] == V.CAPA_PDF for v in con[0].valvulas)


@_necesita(WATER_S)
def test_leyenda_da_tipo_y_estado():
    with fitz.open(WATER_S) as doc:
        vs = RV.leer_hoja(doc[3], 1.0)
    assert vs and all(v["origen"] == V.LEYENDA and v["utilidad"] == "AGUA" for v in vs)
    assert {"abierta", "cerrada"} & {v["estado"] for v in vs}
    assert any(v["tipo"] == "De línea" for v in vs)


@_necesita(DU08)
def test_aplanado_por_forma_queda_por_confirmar():
    with fitz.open(DU08) as doc:
        vs = RV.leer_hoja(doc[10], 1.0)
    assert vs and all(v["origen"] == V.FORMA and v["certeza"] == V.POR_CONFIRMAR for v in vs)


@_necesita(SOUTHWEST)
def test_simbolos_sin_significado_solo_a_mano():
    from hoja import pdf_styles
    with fitz.open(SOUTHWEST) as doc:
        page = doc[0]
        assert RV.leer_hoja(page, 1.0) == []
        capas = {p["layer"] for p in pdf_styles.drawings(page) if pdf_styles.is_symbol(p.get("layer") or "")}
        cruz = next(c for c in capas if "ESRIAMFMGas" in c and '[[14,' in c)
        vs = RV.leer_hoja(page, 1.0, roles_by_utility={"GAS": {rec.ROLE_VALVULAS: [cruz]}})
    assert vs and all(v["origen"] == V.MANUAL and v["utilidad"] == "GAS" for v in vs)


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def _xdata(e):
    return {s.split("=", 1)[0]: s.split("=", 1)[1] for c, s in e.get_xdata("PDFCAD") if c == 1000 and "=" in s}


@_necesita(DU06)
def test_ventana_capa_deshacer_guardar_y_dxf(win, tmp_path):
    from exportar import dxf_valvulas
    from nucleo import tabla_datos
    win._open_pdf_path(str(DU06))
    win._load_page(11)
    res = trabajo.reconocer_hoja(win.work_pdf_path or win.pdf_path, 11, zoom=win.zoom, utilities=("AGUA", "GAS"))
    win._import_recognized_pipes(res)
    n = len(win.valvulas)
    assert n == 5 and V.CAPA in win._capas_utilidad()
    assert any(f.clave == V.CAPA for f in win._estado_capas().utilidades)

    win._cambiar_capa("utilidad", V.CAPA, False)
    assert not win._capa_valvulas.isVisible() and win._valvula_en(win.valvulas[0]["x"], win.valvulas[0]["y"]) < 0
    win._cambiar_capa("utilidad", V.CAPA, True)
    assert win._capa_valvulas.isVisible()

    win._borrar_valvula(0)
    assert len(win.valvulas) == n - 1
    win.undo()
    assert len(win.valvulas) == n

    tablas = win._tablas_de_datos()
    assert any(t.clave == "valvulas" and len(t.filas) == n for t in tablas)
    assert tabla_datos.CERTEZA_VALVULA["segura"]

    from project_io import build_model_dict, parse_model
    assert len(parse_model(build_model_dict(win))["valvulas"]) == n

    doc = ezdxf.new()
    assert dxf_valvulas.exportar(win, doc, doc.modelspace()) == n
    puntos = [e for e in doc.modelspace() if e.dxftype() == "POINT" and e.dxf.layer == dxf_valvulas.CAPA]
    assert len(puntos) == n
    datos = _xdata(puntos[0])
    assert {"TIPO", "UTILIDAD", "ESTADO", "DIAMETER", "ROT_DEG", "ORIGEN", "CERTEZA", "PIPE_IDX"} <= set(datos)
    assert datos["UTILIDAD"] == "AGUA" and datos["ORIGEN"] == "capa"
