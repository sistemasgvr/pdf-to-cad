"""Válvulas de compuerta en agua y gas (pedido del usuario 2026-11-04): herramienta «Válvula» como el buzón, SOLO
en tramos rectos, con espacio para el codo/T/curva de cada lado; deshacer, .digproj y DXF (PDFCAD_VALVULA)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import valvulas as V  # noqa: E402

FT = 0.1                                   # 0.1 ft por px


def _agua(pts, diam=8.0, **k):
    return dict(layer="AGUA", pts=list(pts), name="", diam=diam, pipe_size="x", **k)


def test_pieza_del_catalogo():
    assert V.pieza(8, "FLG")[:3] == ("VALV_8_FLG", "FLG", 11.5)
    b, u, L, _od, avisos = V.pieza(8, "RG")
    assert (b, u) == ("VALV_8_RG", "RG") and L == pytest.approx(11.5 + 3 + 0.17 * 8) and not avisos
    b, u, _L, _od, avisos = V.pieza(20, "RG")            # RG solo hasta 16": bridas + engranes
    assert (b, u) == ("VALV_20_FLG_GEAR", "FLG") and avisos
    b, _u, L, _od, avisos = V.pieza(5, "FLG")             # fuera de la tabla: interpolada y avisada
    assert b == "VALV_5_FLG" and 9.0 < L < 10.0 and avisos
    assert V.material_de("", "PVC C900") == "PVC" and V.material_de("", "") == "DI-A"
    assert V.material_de("CI", "PVC") == "CI"


def test_en_el_tramo_recto_y_se_corre_lejos_del_codo():
    p = _agua([(0, 0), (1000, 0), (1000, 500)])
    lug = V.ubicar([p], [], 500, 3, FT, 20)
    assert lug.ok and (lug.x, lug.y) == pytest.approx((500, 0)) and not lug.movida
    assert lug.bloque == "VALV_8_FLG" and lug.tramo == 0 and (lug.ux, lug.uy) == pytest.approx((1, 0))
    # junto al codo: se corre hasta dejar el codo (1.7·D) + 1 ft de tubo + media válvula
    lug = V.ubicar([p], [], 995, 3, FT, 20)
    esperado = 1000 - (1.7 * 8 / 12 + 1.0 + 11.5 / 24) / FT
    assert lug.ok and lug.movida and lug.x == pytest.approx(esperado)
    # punta libre: solo 1 ft de tubo + media válvula
    lug = V.ubicar([p], [], 2, 0, FT, 20)
    assert lug.ok and lug.x == pytest.approx((1.0 + 11.5 / 24) / FT)


def test_no_cabe_en_tramo_corto_ni_va_en_gravedad_ni_fuera_del_catalogo():
    corto = _agua([(0, 0), (30, 0), (30, 300)])           # 3 ft rectos con un codo al final
    lug = V.ubicar([corto], [], 15, 0, FT, 20)
    assert not lug.ok and "3.0 ft" in lug.motivo
    grav = dict(layer="ALCANTARILLADO", pts=[(0, 0), (1000, 0)], diam=8.0, pipe_size="x")
    assert not V.ubicar([grav], [], 500, 0, FT, 20).ok
    chica = _agua([(0, 0), (1000, 0)], diam=2.0)
    lug = V.ubicar([chica], [], 500, 0, FT, 20)
    assert not lug.ok and "3\" a 72\"" in lug.motivo


def test_no_encima_de_una_tee_ni_de_otra_valvula():
    a = _agua([(0, 0), (1000, 0)])
    b = _agua([(500, 0), (500, 400)])                     # llega a la mitad de a: Tee
    lug = V.ubicar([a, b], [], 505, 0, FT, 20)
    assert lug.ok and abs(lug.x - 500) * FT >= 1.7 * 8 / 12 + 1.0 + 11.5 / 24 - 1e-6
    otras = [{"x": 200.0, "y": 0.0, "largo_ft": 11.5 / 12}]
    lug = V.ubicar([a], [], 205, 0, FT, 20, otras=otras)
    assert lug.ok and abs(lug.x - 200) * FT >= 11.5 / 12 + 1.0 - 1e-6


def test_una_guardada_queda_fuera_si_cambia_la_tuberia():
    p = _agua([(0, 0), (1000, 0)])
    vs = [V.de_lugar(V.ubicar([p], [], 500, 0, FT, 20))]
    assert [l.ok for l in V.ubicar_todas([p], [], vs, FT)] == [True]
    p["pts"] = [(0, 0), (480, 0), (480, 500)]                # ahora no está sobre la tubería
    lug = V.ubicar_todas([p], [], vs, FT)[0]
    assert not lug.ok and lug.motivo


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w.aviso_breve = lambda *a, **k: None
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0              # 0.1 ft por px
    w.pipes = [_agua([(100, 300), (900, 300), (900, 800)], inv_start=-4.0, inv_end=-4.0)]
    w._refresh_lists(); w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_poner_deshacer_menu_y_quitar(win):
    from PySide6 import QtWidgets
    win.insertar_valvula()
    assert win.mode == "insert_valv"
    pasos = len(win._undo)
    win._do_insert_valvula(500, 302)
    assert win.mode == "idle" and len(win._undo) == pasos + 1 and len(win.valvulas) == 1
    assert (win.valvulas[0]["x"], win.valvulas[0]["y"]) == pytest.approx((500, 300))   # sobre la línea
    assert win._valv_lugares[0].ok
    menu = QtWidgets.QMenu()
    assert win._menu_valvula(menu, 500, 300)
    assert win.cambiar_valvula(0, union="RG") and win.valvulas[0]["union"] == "RG"
    assert win.quitar_valvula(0) and win.valvulas == []
    win.undo()
    assert len(win.valvulas) == 1 and win.valvulas[0]["union"] == "RG"
    win.undo(); win.undo()
    assert win.valvulas == []


def test_va_al_proyecto_y_al_dxf(win):
    import ezdxf
    import project_io
    from exportar import dxf_export
    import config as C
    win._do_insert_valvula(895, 300)                      # junto al codo: se corre
    assert len(win.valvulas) == 1
    model = project_io.build_model_dict(win)
    assert project_io.parse_model(model)["valvulas"] == win.valvulas
    doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
    dxf_export.merge_into(win, doc, marks=True)
    pts = [e for e in doc.modelspace().query("POINT") if e.dxf.layer == "PDFCAD_VALVULA"]
    assert len(pts) == 1 and win._valvulas_omitidas == 0
    xd = dict(v.split("=", 1) for _c, v in pts[0].get_xdata("PDFCAD")[1:])
    assert xd["PIPE_IDX"] == "0" and xd["BLOQUE"] == "VALV_8_FLG" and xd["UNION"] == "FLG"
    assert float(xd["DIAMETER"]) == 8 and float(xd["LARGO_IN"]) == pytest.approx(11.5)
    assert float(xd["CAJA_TOPE_Z"]) == 0.0 and float(xd["CAJA_DIAM_IN"]) == 5.25   # caja hasta la superficie
    v = win.valvulas[0]
    x, y = win._to_cad(v["x"], v["y"])
    assert pts[0].dxf.location[0] == pytest.approx(x) and pts[0].dxf.location[1] == pytest.approx(y)
    x2, y2 = win._to_cad(v["x"] + 1, v["y"])
    import math
    n = math.hypot(x2 - x, y2 - y)
    assert float(xd["DIR_X"]) == pytest.approx((x2 - x) / n, abs=1e-6)
    assert float(xd["DIR_Y"]) == pytest.approx((y2 - y) / n, abs=1e-6)
    # una válvula fuera de lugar no sale
    win.pipes[0]["pts"] = [(100, 500), (900, 500)]
    doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
    dxf_export.merge_into(win, doc, marks=True)
    assert not [e for e in doc.modelspace().query("POINT") if e.dxf.layer == "PDFCAD_VALVULA"]
    assert win._valvulas_omitidas == 1


# ── Vista 3D: la misma pieza que pone el plugin en Civil 3D ──────────────────────

def _lugar_dict(lug):
    return dict(x=lug.x, y=lug.y, pipe=lug.pipe, tramo=lug.tramo, bloque=lug.bloque, largo_ft=lug.largo_ft,
                brida_ft=lug.brida_ft, diam_in=lug.diam_in, union=lug.union, material=lug.material)


def test_3d_pieza_del_catalogo_en_el_eje_y_tubo_cortado_en_sus_caras():
    import numpy as np
    from nucleo import modelo3d, valvulas3d as V3
    p = _agua([(0, 0), (1000, 0), (1000, 600)], inv_start=-4.0, inv_end=-6.0)
    lug = V.ubicar([p], [], 500, 0, FT, 20)
    e = modelo3d.construir([p], [], FT, valvulas=[_lugar_dict(lug)], origen=(0, 0, 0), suelo_z=0)
    ident = [k for k, o in e.objetos.items() if o.get("acc_tipo") == "valvula"]
    assert len(ident) == 1
    o = e.objetos[ident[0]]
    T = e.opacos
    todo = T[T[:, 10] == np.float32(ident[0])]
    gris = np.all(np.isclose(todo[:, 6:9], V3.COLOR_CAJA[:3]), axis=1)
    m, caja = todo[~gris], todo[gris]                               # la válvula y su caja (valve box)
    pos, _nor, _capa = V3.malla(8.0, "FLG")
    assert len(m) == len(pos)                                       # la pieza entera, triángulo por triángulo
    # centro en el eje de la tubería y vástago hacia arriba (Z del bloque = vertical)
    assert np.mean(m[:, 0]) == pytest.approx(50.0, abs=0.05) and abs(np.mean(m[:, 1])) < 0.01
    assert m[:, 2].max() - o["eje_z"] == pytest.approx(pos[:, 2].max(), abs=0.02)
    # caja: vertical sobre el centro, de la corona (eje + 4") hasta la cota 0 (aún sin terreno)
    assert len(caja) and np.mean(caja[:, 0]) == pytest.approx(50.0, abs=0.05)
    assert caja[:, 2].min() == pytest.approx(o["eje_z"] + 8 / 24, abs=1e-3)
    assert caja[:, 2].max() == pytest.approx(0.0, abs=1e-3)
    assert np.ptp(caja[:, 0]) == pytest.approx(V.CAJA_DIAM_IN / 12, abs=0.01)
    assert o["eje_z"] == pytest.approx(modelo3d._z_eje([p], 0, lug.x, lug.y))
    # el tubo llega exacto a las dos caras de la válvula y no pasa por dentro
    tubo = T[T[:, 10] == np.float32(1)]
    L = lug.largo_ft
    assert not ((tubo[:, 0] > 50 - L / 2 + 0.01) & (tubo[:, 0] < 50 + L / 2 - 0.01)).any()
    assert tubo[tubo[:, 0] < 50, 0].max() == pytest.approx(50 - L / 2, abs=0.01)
    assert tubo[tubo[:, 0] > 50, 0].min() == pytest.approx(50 + L / 2, abs=0.01)


def test_3d_eje_con_la_pendiente_y_ficha():
    import numpy as np
    from nucleo import ficha3d, valvulas3d as V3
    x, y, z = V3.base((1.0, 0.0, 0.1))                    # tubería que sube: X sigue la pendiente
    assert np.allclose(x, np.array([1, 0, 0.1]) / np.linalg.norm([1, 0, 0.1]))
    assert z[2] > 0.99 and abs(float(x @ z)) < 1e-12 and np.allclose(np.cross(z, x), y)
    titulo, filas = ficha3d.de_accesorio(dict(acc_tipo="valvula", diam_in=8.0, bloque="VALV_8_FLG", union="FLG",
                                              material="DI-A", largo_ft=11.5 / 12, pipes=[0], capa="AGUA",
                                              eje_z=-4.3), [{}], [])
    assert "8" in titulo and ("Pieza", "VALV_8_FLG") in filas


def test_3d_desde_la_ventana(win):
    win._do_insert_valvula(500, 300)
    from ui.dialogos.vista3d_armado import ArmadoMixin   # noqa: F401  (el armado de la ventana 3D)
    dlg = win.abrir_vista3d()
    import time
    from PySide6 import QtWidgets
    t = time.time()
    while (dlg._trabajo is not None or dlg._t.isActive()) and time.time() - t < 20:
        QtWidgets.QApplication.processEvents(); time.sleep(0.01)
    QtWidgets.QApplication.processEvents()
    vs = [o for o in dlg.escena.objetos.values() if o.get("acc_tipo") == "valvula"]
    assert len(vs) == 1 and vs[0]["bloque"] == "VALV_8_FLG"
    k = [k for k, o in dlg.escena.objetos.items() if o.get("acc_tipo") == "valvula"][0]
    assert "VALV_8_FLG" in dlg.texto_de(k)
    win.quitar_valvula(0)
    t = time.time()
    while (dlg._trabajo is not None or dlg._t.isActive()) and time.time() - t < 20:
        QtWidgets.QApplication.processEvents(); time.sleep(0.01)
    assert not [o for o in dlg.escena.objetos.values() if o.get("acc_tipo") == "valvula"]
    dlg.close()


# Caja envolvente del CUERPO (capa V-PRES-VALV-DIA, pulgadas) de bloques del catálogo `Valvulas_AWWA_3D.dwg` del
# plugin de válvulas del equipo, medida en AutoCAD (2026-11-05). La receta debe reproducirlas.
CATALOGO_DWG = {
    "VALV_3_FLG": ((-4.0, -3.75, -3.75), (4.0, 3.75, 12.24)),
    "VALV_8_RG": ((-7.93, -6.48, -6.47), (7.93, 6.48, 22.14)),
    "VALV_16_FLG": ((-8.0, -11.75, -11.75), (8.0, 11.75, 37.98)),
    "VALV_24_FLG_GEAR": ((-15.05, -16.0, -15.99), (15.04, 17.5, 73.47)),
    "VALV_54_FLG_GEAR": ((-23.01, -33.12, -33.08), (22.97, 33.12, 145.31)),
}


def test_receta_igual_al_catalogo_del_plugin_de_valvulas():
    import numpy as np
    from nucleo import valvula_malla as VM, valvula_receta as VR
    for nombre, (lo, hi) in CATALOGO_DWG.items():
        n = float(nombre.split("_")[1])
        rec = VR.receta(n, "RG" if nombre.endswith("_RG") else "FLG")
        assert rec.bloque == nombre and not rec.estimada
        pos, _nor, capa = VM.malla(rec)
        P = pos[capa == 0]
        assert np.allclose(P.min(0), lo, atol=0.08) and np.allclose(P.max(0), hi, atol=0.08), nombre
    # cualquier diámetro: entre dos de la tabla, sus medidas quedan entre las de ellas
    r5, r4, r6 = VR.receta(5), VR.receta(4), VR.receta(6)
    assert r5.estimada and r4.largo < r5.largo < r6.largo and r4.od_extremo < r5.od_extremo < r6.od_extremo


def test_espejo_de_la_receta_en_el_plugin():
    """Las constantes y la tabla de `ValvulaReceta.cs` (plugin) = las de `valvula_receta` (app)."""
    import os
    import re
    from nucleo import valvula_receta as VR
    cs = open(os.path.join(os.path.dirname(__file__), "..", "API-CIVIL", "proyecto1", "proyecto1",
                           "ValvulaReceta.cs"), encoding="utf-8").read()
    for nombre, valor in vars(VR).items():
        if nombre.isupper() and isinstance(valor, (int, float)) and not isinstance(valor, bool):
            m = re.search(r"\b%s\s*=\s*([-0-9.]+)" % nombre, cs)
            assert m, nombre
            assert float(m.group(1)) == pytest.approx(float(valor)), nombre
    filas = re.findall(r"\{\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,"
                       r"\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\}", cs)
    tabla = {float(f[0]): tuple(float(x) for x in f[1:]) for f in filas}
    assert tabla == {float(k): tuple(float(x) for x in v) for k, v in VR.TABLA.items()}


# ── Perfil longitudinal: la válvula con su símbolo y su rótulo (como el plugin) ──────────

def test_rotulo_del_perfil_igual_al_del_plugin():
    from nucleo import perfil_textos as T
    assert T.lineas_valvula(123.456, 8, "FLG", False, 101.234) == [
        "PIPE STA 1+23.46", '8" FLG GATE VALVE', "TOP ELEV 101.23'"]
    assert T.lineas_valvula(50, 6, "RG", False, 99)[1] == '6" MJ GATE VALVE'
    assert T.lineas_valvula(1000, 24, "RG", True, 90.5)[1] == '24" FLG GATE VALVE W/ GEAR OP'


def test_valvula_en_el_perfil(win):
    win._do_insert_valvula(500, 300)
    v = win.valvulas[0]
    win.abrir_perfil()
    win._pick(500, 300)
    win._redraw()
    d = win._perfil_datos
    assert d is not None and len(d.valvulas) == 1
    va = d.valvulas[0]
    paso = d.pasos[va.paso]
    # estación: la distancia desde la punta del recorrido hasta el centro de la válvula
    import math
    pa = paso.p0
    assert va.e == pytest.approx(paso.e0 + math.hypot(v["x"] - pa[0], v["y"] - pa[1]) * FT, abs=1e-6)
    assert va.lineas[1] == '8" FLG GATE VALVE' and va.largo_ft == pytest.approx(11.5 / 12)
    assert va.z_caja == 0.0                                             # caja: de la corona hasta la cota 0
    assert d.z_max >= va.z_caja - 1e-9                                  # cabe en el perfil
    win.perfil_vista.resize(900, 320)
    assert not win.perfil_vista.grab().isNull()            # se dibuja sin errores
    # quitar la válvula la saca del perfil
    win.quitar_valvula(0)
    assert win._perfil_datos is not None and win._perfil_datos.valvulas == []

# ── reconocidas del PDF (dev_santos_v2, 2026-11-05) ───────────────────────────────────────────────────────
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT / "app"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
def win_rec(monkeypatch):
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
def test_ventana_capa_deshacer_guardar_y_dxf(win_rec, tmp_path):
    win = win_rec
    from exportar import dxf_export
    from nucleo import tabla_datos
    win._open_pdf_path(str(DU06))
    win._load_page(11)
    res = trabajo.reconocer_hoja(win.work_pdf_path or win.pdf_path, 11, zoom=win.zoom, utilities=("AGUA", "GAS"))
    win._import_recognized_pipes(res)
    n = len(win.valvulas)
    assert n == 5 and V.CAPA in win._capas_utilidad()
    assert any(f.clave == V.CAPA for f in win._estado_capas().utilidades)

    win._cambiar_capa("utilidad", V.CAPA, False)
    assert not any(it.isVisible() for it in win._valv_items)
    assert win._valvula_en(win.valvulas[0]["x"], win.valvulas[0]["y"]) < 0
    win._cambiar_capa("utilidad", V.CAPA, True)
    assert all(it.isVisible() for it in win._valv_items)

    win._borrar_valvula(0)
    assert len(win.valvulas) == n - 1
    win.undo()
    assert len(win.valvulas) == n

    tablas = win._tablas_de_datos()
    assert any(t.clave == "valvulas" and len(t.filas) == n for t in tablas)
    assert tabla_datos.CERTEZA_VALVULA["segura"]

    from project_io import build_model_dict, parse_model
    assert len(parse_model(build_model_dict(win))["valvulas"]) == n

    # un solo modelo (unión con dev_deyvy): salen al DXF las que caben en su tramo recto, con sus datos del plano
    doc = ezdxf.new()
    dxf_export._export_valvulas(win, doc, doc.modelspace())
    puntos = [e for e in doc.modelspace() if e.dxftype() == "POINT" and e.dxf.layer == "PDFCAD_VALVULA"]
    lugares = win._lugares_valvulas()
    assert len(puntos) == sum(1 for v, l in zip(win.valvulas, lugares) if V.exportable(v, l))
    if puntos:
        datos = _xdata(puntos[0])
        assert {"TIPO", "UTILIDAD", "ESTADO", "DIAMETER", "ORIGEN", "PIPE_IDX", "UNION", "BLOQUE"} <= set(datos)
        assert datos["UTILIDAD"] == "AGUA" and datos["ORIGEN"] == "capa"


def test_la_caja_de_la_valvula_llega_al_terreno_del_proyecto():
    """El suelo sale de `nucleo/terreno` (hoy plano en la cota 0); con otro terreno, la caja llega a ese suelo."""
    from nucleo import terreno
    assert V.caja(-5.0, 12.0) == (-4.5, 0.0)
    assert V.caja(1.0, 12.0) is None                        # la corona ya está sobre el suelo
    anterior = terreno.usar(terreno.TerrenoPlano(3.5))
    try:
        assert V.caja(-5.0, 12.0, x=10, y=20) == (-4.5, 3.5)
    finally:
        terreno.usar(anterior)
    assert terreno.cota_en(1, 2) == 0.0
