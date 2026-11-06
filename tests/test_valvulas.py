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
    vs = [V.nueva(V.ubicar([p], [], 500, 0, FT, 20))]
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
    m = T[T[:, 10] == np.float32(ident[0])]
    pos, _nor, _capa = V3.malla(8.0, "FLG")
    assert len(m) == len(pos)                                       # la pieza entera, triángulo por triángulo
    # centro en el eje de la tubería y vástago hacia arriba (Z del bloque = vertical)
    assert np.mean(m[:, 0]) == pytest.approx(50.0, abs=0.05) and abs(np.mean(m[:, 1])) < 0.01
    assert m[:, 2].max() - o["eje_z"] == pytest.approx(pos[:, 2].max(), abs=0.02)
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
    win.perfil_vista.resize(900, 320)
    assert not win.perfil_vista.grab().isNull()            # se dibuja sin errores
    # quitar la válvula la saca del perfil
    win.quitar_valvula(0)
    assert win._perfil_datos is not None and win._perfil_datos.valvulas == []
