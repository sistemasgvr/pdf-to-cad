"""Superficies (terreno) — versión 2.1.0. Pedido del usuario 2026-11-11: importar una o varias superficies
(LandXML / GeoTIFF del cliente), que salgan SIEMPRE junto a las redes y que a Civil 3D llegue EXACTAMENTE la misma
superficie. Archivos de ejemplo del cliente en tests/fixtures/superficies/ (Civil 3D 2024, UTM en metros, sin EPSG)."""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import superficies as S  # noqa: E402
from nucleo import superficies_leer as L  # noqa: E402

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "superficies")
XML = os.path.join(DIR, "TERRENO.xml")
TIF = os.path.join(DIR, "TERRENO.tif")


def _leer(ruta):
    with open(ruta, "rb") as f:
        return L.leer(os.path.basename(ruta), f.read())


# ───────────────────────── lectura ─────────────────────────

def test_landxml_del_cliente():
    (s,) = _leer(XML)
    assert (s.nombre, s.formato, s.unidad, s.crs) == ("TERRENO", "LandXML", "meter", "")
    assert len(s.puntos) == 576 and len(s.triangulos) == 949
    assert s.puntos[:, 2].min() == pytest.approx(180.598894833428) and s.puntos[:, 2].max() == pytest.approx(183.90578900642)
    # LandXML «Norte Este Cota»: X = Este (~639 747), Y = Norte (~9 336 843)
    assert 6.39e5 < s.puntos[:, 0].min() < 6.4e5 and 9.33e6 < s.puntos[:, 1].min() < 9.34e6


def test_geotiff_del_cliente():
    s = _leer(TIF)[0]
    assert (s.formato, s.unidad) == ("GeoTIFF", "meter")
    assert len(s.puntos) > 40_000 and len(s.triangulos) > 80_000
    # el DEM y el LandXML son la MISMA superficie del cliente: mismo rango de cotas y mismo lugar (±1 celda)
    x = _leer(XML)[0]
    assert s.puntos[:, 2].min() == pytest.approx(x.puntos[:, 2].min(), abs=0.05)
    assert S.recuadro(s.puntos) == pytest.approx(S.recuadro(x.puntos), abs=0.25)
    assert not np.isnan(s.puntos).any()          # sin «nodata»


def test_geotiff_con_huecos_y_pixel_es_area(tmp_path):
    from PIL import Image, TiffImagePlugin
    z = np.arange(12, dtype=np.float32).reshape(3, 4)
    z[1, 1] = -9999
    im = Image.fromarray(z, mode="F")
    info = TiffImagePlugin.ImageFileDirectory_v2()
    info[33550] = (2.0, 2.0, 0.0)
    info[33922] = (0.0, 0.0, 0.0, 100.0, 50.0, 0.0)
    info[34735] = (1, 1, 0, 2, 1025, 0, 1, 1, 3076, 0, 1, 9002)      # PixelIsArea, pies
    info[42113] = "-9999"
    ruta = tmp_path / "dem.tif"
    im.save(ruta, tiffinfo=info)
    s = _leer(str(ruta))[0]
    assert len(s.puntos) == 11 and s.unidad == "foot"
    assert tuple(s.puntos[0]) == (101.0, 49.0, 0.0)            # centro de la celda (0, 0)
    # 3 × 4 celdas → 2 × 3 cuadros; los 4 que tocan el hueco quedan con 1 triángulo o ninguno
    assert len(s.triangulos) == 2 * 2 + 4               # 2 celdas llenas + 4 con 3 esquinas


@pytest.mark.parametrize("contenido, motivo", [
    (b"no es xml", "no se puede leer"), (b"<Otro/>", "no es un LandXML"),
    (b'<LandXML><Surfaces><Surface name="a"><Definition surfType="Grid"/></Surface></Surfaces></LandXML>', "Grid"),
])
def test_errores_legibles(contenido, motivo):
    with pytest.raises(L.ErrorSuperficie, match=motivo):
        L.leer("x.xml", contenido)
    with pytest.raises(L.ErrorSuperficie, match="Formato no admitido"):
        L.leer("x.dwg", b"")


# ───────────────────────── sistema, unidades y LandXML exacto ─────────────────────────

def test_mismo_sistema_xy_intactos_y_cotas_a_pies():
    (s,) = _leer(XML)
    p = S.normalizar(s, "", "EPSG:32717", "meter", S.UNIDAD_PIES)
    assert np.array_equal(p[:, :2], s.puntos[:, :2])               # X/Y exactos (los de las redes)
    assert np.allclose(p[:, 2], s.puntos[:, 2] / 0.3048)


def test_destino_por_la_georreferencia():
    assert S.destino(None) == ("", "", "foot")
    crs, uxy, uz = S.destino(2229)
    assert (crs, uxy, uz) == ("EPSG:2229", "USSurveyFoot", "USSurveyFoot")
    assert S.destino(32717)[1] == "meter"


def test_reproyectar_a_state_plane():
    pytest.importorskip("pyproj")
    from pyproj import Transformer
    (s,) = _leer(XML)
    p = S.normalizar(s, "EPSG:32717", "EPSG:2229", "USSurveyFoot", "USSurveyFoot")
    x, y = Transformer.from_crs("EPSG:32717", "EPSG:2229", always_xy=True).transform(*s.puntos[0, :2])
    assert (p[0, 0], p[0, 1]) == (x, y)
    assert p[0, 2] == pytest.approx(s.puntos[0, 2] * 3937 / 1200)


@pytest.mark.parametrize("ruta", [XML, TIF])
def test_landxml_escrito_vuelve_bit_a_bit(ruta):
    """Lo que viaja a Civil 3D = lo que tiene la app: mismos puntos (bit a bit), triángulos y caras ocultas."""
    s = _leer(ruta)[0]
    p = S.normalizar(s, "", "EPSG:32717", "meter", S.UNIDAD_PIES)
    datos = S.escribir_landxml("T", p, s.triangulos, "foot", s.invisibles)
    (r,) = L.leer_landxml(datos)
    assert r.unidad == "foot" and np.array_equal(r.puntos, p)
    assert np.array_equal(r.triangulos, s.triangulos) and np.array_equal(r.invisibles, s.invisibles)
    assert b"CoordinateSystem" not in datos


def test_contorno_muestras_y_cota():
    (s,) = _leer(XML)
    (lazo,) = S.contorno(s.triangulos, s.invisibles)
    assert lazo[0] == lazo[-1] and len(lazo) > 100
    for x, y, z in S.muestras(s.puntos, s.triangulos):
        assert S.cota_en(s.puntos, s.triangulos, x, y) == pytest.approx(z, abs=1e-7)
    assert S.cota_en(s.puntos, s.triangulos, 0, 0) is None
    assert S.area_xy(s.puntos, s.triangulos) == pytest.approx(1773.216201296465, rel=1e-9)   # area2DSurf del archivo


def test_xdata_cabe_en_dxf():
    """Cada texto (1000) del XDATA: ≤ 255 caracteres (tope de AutoCAD)."""
    (s,) = _leer(XML)
    reg = S.registro(s, "TERRENO.xml", "a" * 40, 0, "")
    items = S.xdata(reg, s.puntos, s.triangulos, "p_superficies/TERRENO.xml", "C:/" + "x" * 300, "b" * 40, "foot")
    assert items[0] == (1000, "PDFCAD_SUPERFICIE")
    assert all(len(v) <= 255 for _c, v in items)
    claves = {v.split("=", 1)[0] for _c, v in items[1:]}
    assert {"NAME", "ARCHIVO", "SHA1", "N_PUNTOS", "N_TRIANGULOS", "ZMIN", "ZMAX", "UNIDAD", "MUESTRA_1"} <= claves
    assert "ARCHIVO_ABS" not in claves                     # ruta larga: se omite


def test_nombres_libres():
    assert S.nombre_libre("T", ["T", "T (2)"]) == "T (3)"
    assert S.nombre_archivo('a/b:"c"') == "a_b__c_.xml"


# ───────────────────────── ventana ─────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    hoja = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=20.0, scale_ft_per_pt=20 / 72.0,
                unit="in", landscape=True)
    w.blank_canvas = True
    w.paper = dict(hoja)
    w._load_blank_page(hoja)
    w._info = lambda *a, **k: None
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _georef(w, epsg=32717):
    """Píxel → UTM: el plano cubre la superficie del cliente (0.05 m por px)."""
    from geo import georef
    w.georef = georef.Georef([[0.05, 0, 639740.0], [0, -0.05, 9336890.0], [0, 0, 1]], epsg)


def _todas(cands):
    return [c for c in cands if c.sup is not None]


def test_importar_dibuja_capas_quitar_deshacer(win):
    _georef(win)
    assert win.importar_superficies([XML, TIF], elegir=_todas) == 2
    assert [r["nombre"] for r in win.superficies] == ["TERRENO", "TERRENO (2)"]
    win._redraw()
    caminos = [it for it in win._sup_items if it.data(0)]
    assert len(caminos) == 2
    # el contorno cae donde está la superficie: (639 747 E, 9 336 843 N) → px
    r = caminos[0].path().boundingRect()
    assert r.left() == pytest.approx((639747.309 - 639740) / 0.05, abs=1) and r.width() > 500
    est = win._estado_capas()
    assert [f.nombre for f in est.superficies] == ["TERRENO", "TERRENO (2)"] and all(f.quitable for f in est.superficies)
    from ui.comun import capas_popup as CP
    win._cambiar_capa(CP.SUPERFICIE, 0, False)
    assert len([it for it in win._sup_items if it.data(0)]) == 1
    win._encender_capas()
    win._quitar_capa(CP.SUPERFICIE, 1)
    assert len(win.superficies) == 1
    win.undo()
    assert len(win.superficies) == 2


def test_sin_georreferencia_se_importa_pero_no_se_dibuja(win):
    assert win.importar_superficies([XML], elegir=_todas) == 1
    win._redraw()
    assert not getattr(win, "_sup_items", [])


def test_proyecto_guarda_y_abre_las_superficies(win, tmp_path):
    _georef(win)
    win.importar_superficies([TIF], elegir=_todas)
    ruta = str(tmp_path / "p.digproj")
    win._write_project(ruta)
    from ui.ventana.app_window import Main
    w2 = Main()
    w2._info = lambda *a, **k: None
    try:
        w2._open_project_path(ruta)
        assert [r["nombre"] for r in w2.superficies] == ["TERRENO"]
        pts, tri, _inv, _u = w2._sup_geometria(w2.superficies[0])
        assert len(pts) == w2.superficies[0]["n_puntos"] and len(tri) == w2.superficies[0]["n_triangulos"]
        assert np.array_equal(pts, win._sup_geometria(win.superficies[0])[0])
    finally:
        w2._dirty = False
        w2.close()


def test_dxf_lleva_la_misma_superficie(win, tmp_path):
    """El DXF trae el punto PDFCAD_SUPERFICIE y, al lado, el LandXML: sus puntos son EXACTAMENTE los de la app."""
    import ezdxf
    from exportar import dxf_export
    _georef(win)
    win.importar_superficies([XML], elegir=_todas)
    win._out = str(tmp_path / "red.dxf")
    doc = ezdxf.new("R2010")
    dxf_export.merge_into(win, doc, marks=True)
    (pt,) = [e for e in doc.modelspace() if e.dxf.layer == S.CAPA]
    xd = dict(v.split("=", 1) for _c, v in pt.get_xdata("PDFCAD")[1:])
    ruta = tmp_path / xd["ARCHIVO"]
    datos = ruta.read_bytes()
    assert L.sha1(datos) == xd["SHA1"] and xd["UNIDAD"] == "foot"
    (r,) = L.leer_landxml(datos)
    pts, tri, _inv, _u = win._sup_geometria(win.superficies[0])
    assert np.array_equal(r.puntos, pts) and np.array_equal(r.triangulos, tri)
    assert int(xd["N_PUNTOS"]) == 576 and int(xd["N_TRIANGULOS"]) == 949
    x, y, z = (float(v) for v in xd["MUESTRA_1"].split(","))
    assert S.cota_en(r.puntos, r.triangulos, x, y) == pytest.approx(z, abs=1e-7)


def test_dialogo_estados_y_boton(win, tmp_path):
    from ui.dialogos.superficies_dialog import SuperficiesDialog, LISTA, AVISO, ERROR
    malo = tmp_path / "malo.xml"
    malo.write_bytes(b"<x/>")
    win._superficies_datos = {}
    cands = win._sup_candidatos([XML, str(malo)])
    dlg = SuperficiesDialog(cands, "EPSG:32717", True)
    assert [tj.estado_actual()[0] for tj in dlg.tarjetas] == [LISTA, ERROR]
    assert dlg.btn_ok.text() == "Importar 1 superficie" and dlg.btn_ok.isEnabled()
    dlg.tarjetas[0].crs.setText("abc")
    assert dlg.tarjetas[0].estado_actual()[0] == ERROR and not dlg.btn_ok.isEnabled()
    dlg.tarjetas[0].crs.setText("32717")
    dlg.tarjetas[0].nombre.setText("Terreno cliente")
    (c,) = dlg.elegidos()
    assert (c.nombre, c.crs) == ("Terreno cliente", "EPSG:32717")
    sin_geo = SuperficiesDialog(win._sup_candidatos([XML]), "", False)
    assert sin_geo.tarjetas[0].estado_actual()[0] == AVISO and sin_geo.btn_ok.isEnabled()
    # reporte 2026-11-12: el código de Civil 3D («UTM84-17S», Configuración de dibujo → Unidades y huso) se acepta
    dlg.tarjetas[0].crs.setText("UTM84-17S")
    assert dlg.tarjetas[0].estado_actual()[0] == LISTA and dlg.btn_ok.isEnabled()
    assert "EPSG:32717" in dlg.tarjetas[0].crs_desc.text()
    assert dlg.elegidos()[0].crs == "EPSG:32717"


_NAMEMAPPER = """GenericId,NameType,Flavor,NumericId,NameId,DupSort,AliasFlag,Flags,Deprecation,Remarks,Comment
1,16,EPSG,2229,"NAD83 / California zone 5 (ftUS)",0,0,0,0,,
1,16,Autodesk,0,"CA83-VF",0,0,0,0,,
1,16,CsMap,0,"CA83-VF",0,0,0,0,,
2,16,EPSG,32717,"WGS 84 / UTM zone 17S",0,0,0,0,,
2,16,CsMap,0,"UTM84-17S",0,0,0,0,,
3,12,EPSG,6326,"WGS84",0,0,0,0,,
3,12,CsMap,0,"WGS84",0,0,0,0,,
"""


@pytest.mark.parametrize("texto, crs", [
    ("32717", "EPSG:32717"), ("epsg:2229", "EPSG:2229"),
    ("UTM84-17S", "EPSG:32717"), ("utm84-17s", "EPSG:32717"),
    ("CA83-VF", "EPSG:2229"), ("CA83VF", "EPSG:2229"),           # la app escribe «CA83VF»; el diccionario «CA83-VF»
    ("ESRI:102100", "EPSG:3857"), ("", "")])
def test_sistema_por_epsg_codigo_civil3d_o_pyproj(texto, crs, tmp_path, monkeypatch):
    from nucleo import sistemas_cs as C
    (tmp_path / "NameMapper.csv").write_text(_NAMEMAPPER, encoding="latin-1")
    monkeypatch.setenv("PDFCAD_CSMAP_DIR", str(tmp_path))
    C._tabla.cache_clear()
    try:
        got, err, _ = C.resolver(texto)
        assert (got, err) == (crs, "")
    finally:
        C._tabla.cache_clear()


def test_sistema_sin_diccionario_de_autodesk_y_errores(tmp_path, monkeypatch):
    """Sin Civil 3D/Map instalado: UTM y lat/long por su patrón; lo demás, mensaje que dice qué escribir."""
    from nucleo import sistemas_cs as C
    monkeypatch.setenv("PDFCAD_CSMAP_DIR", str(tmp_path / "no_existe"))
    C._tabla.cache_clear()
    try:
        assert C.resolver("UTM84-17S")[0] == "EPSG:32717" and C.resolver("UTM84-17N")[0] == "EPSG:32617"
        assert C.resolver("UTM83-11")[0] == "EPSG:26911" and C.resolver("LL84")[0] == "EPSG:4326"
        assert "UTM84-17S" in C.resolver("XYZ-99")[1] and C.resolver("99999999")[1]
    finally:
        C._tabla.cache_clear()


def test_boton_menu_y_panel_de_capas(win):
    """El botón está en Herramientas, en «Hoja y PDF» y en la paleta (acción con nombre); «Capas ▾» muestra la
    sección SUPERFICIES con su botón «Quitar»."""
    from ui.comun import capas_popup as CP
    assert "Importar superficies…" in win._acc
    _georef(win)
    win.importar_superficies([XML], elegir=_todas)
    panel = CP.PanelCapas(win._estado_capas, win._cambiar_capa, win._solo_capa, win._encender_capas,
                          al_quitar=win._quitar_capa)
    fila = panel.fila(CP.SUPERFICIE, 0)
    assert fila is not None and fila.fila.nombre == "TERRENO"
    secciones = [w.text() for w in panel.findChildren(QtWidgets_label()) if w.objectName() == "seccionCapas"]
    assert "SUPERFICIES (terreno)" in secciones
    fila.conmutar.emit()                                    # bombilla: apaga
    assert win.superficies[0]["visible"] is False and win.btn_capas.text()
    fila = panel.fila(CP.SUPERFICIE, 0)
    fila.btn_quitar.click()
    assert win.superficies == [] and panel.fila(CP.SUPERFICIE, 0) is None


def _toasts(win, monkeypatch):
    """Captura los avisos breves (como si la ventana estuviera en pantalla)."""
    from ui.comun import aviso_breve
    vistos = []
    monkeypatch.setattr(win, "_incrustar_ok", lambda: True)
    monkeypatch.setattr(aviso_breve, "mostrar", lambda w, titulo, detalle="", accion=None, tono="ok":
                        vistos.append((tono, titulo, detalle, accion)))
    return vistos


def test_inventario_dice_si_cada_superficie_llego_bien(win, monkeypatch):
    """Pedido 2026-11-12: Inventario → «Superficies» con el estado de cada una y por qué."""
    from ui.ventana.ventana_lista_superficies import OK, AVISO, ERROR
    from nucleo.model import TAB_SUP
    _georef(win)
    win.importar_superficies([XML, TIF], elegir=_todas)
    win._show_tab(TAB_SUP)
    assert win._current_tab() == TAB_SUP and win.tab_combo.currentText() == "Superficies"
    assert win.sup_list.count() == 2 and [n for n, _r, _d in win._sup_revision] == [OK, OK]
    assert "TERRENO" in win.sup_list.item(0).text() and "Importada bien" in win.sup_list.item(0).text()
    win.sup_list.setCurrentRow(0)
    info = win.lbl_sup_info.text()
    assert "576 puntos y 949 triángulos" in info and "EPSG:32717" in info and "Cotas de" in info
    # sistema equivocado: queda lejos de la hoja → aviso con la pista
    win.superficies[1]["crs"] = "EPSG:32617"
    win._llenar_lista_superficies()
    assert win._sup_revision[1][0] == AVISO and "Fuera de la hoja" in win.sup_list.item(1).text()
    # archivo que falta en el proyecto → error
    win._superficies_datos.pop(win.superficies[0]["sha1"])
    win._sup_leidas = {}
    win._sup_geo = {}
    win._llenar_lista_superficies()
    assert win._sup_revision[0][0] == ERROR and "Falta el archivo" in win.sup_list.item(0).text()


def test_sin_georreferencia_el_inventario_avisa(win):
    from ui.ventana.ventana_lista_superficies import AVISO
    win.importar_superficies([XML], elegir=_todas)
    nivel, resumen, det = win._sup_revision[0]
    assert nivel == AVISO and resumen == "No se ve en el plano" and any("Civil 3D" in d for d in det)


def test_toast_de_exito_aviso_y_fallo(win, monkeypatch, tmp_path):
    """Al importar sale un aviso breve: éxito (verde), con aviso o con lo que falló (ámbar), y «Ver en el
    inventario» abre la sección."""
    from nucleo.model import TAB_SUP
    vistos = _toasts(win, monkeypatch)
    _georef(win)
    win.importar_superficies([XML], elegir=_todas)
    tono, titulo, detalle, accion = vistos[-1]
    assert (tono, titulo) == ("ok", "Superficie importada") and "TERRENO" in detalle
    accion[1]()
    assert win._current_tab() == TAB_SUP
    malo = tmp_path / "roto.xml"
    malo.write_bytes(b"<no es landxml/>")
    win.importar_superficies([TIF, str(malo)], elegir=_todas)       # una bien, otra que no se lee
    tono, titulo, detalle, _a = vistos[-1]
    assert tono == "aviso" and titulo == "Importadas 1 de 2" and "roto.xml" in detalle
    n = len(win.superficies)
    assert win.importar_superficies([str(malo)], elegir=_todas) == 0 and len(win.superficies) == n
    tono, titulo, detalle, _a = vistos[-1]
    assert (tono, titulo) == ("aviso", "No se importó") and "roto.xml" in detalle
    from geo import georef
    win.georef = georef.Georef()                                    # sin georreferencia: aviso, no éxito
    win.importar_superficies([XML], elegir=_todas)
    tono, titulo, detalle, _a = vistos[-1]
    assert (tono, titulo) == ("aviso", "Importada, con un aviso") and "No se ve en el plano" in detalle


def test_matriz_sobre_superficie_centra_la_hoja_a_su_escala():
    """Centro de la hoja → centro de la superficie; 1 px = la escala de la hoja en la unidad del sistema; sin giro."""
    pies_por_px = 0.25
    cad = lambda x, y: (x * pies_por_px, (800 - y) * pies_por_px)          # como to_cad (Y hacia arriba)
    m = np.array(S.matriz_sobre_superficie(cad, 1000.0, 800.0, (639770.0, 9336860.0), "meter"))
    centro = m @ [500.0, 400.0, 1.0]
    assert centro[:2] == pytest.approx((639770.0, 9336860.0), abs=1e-6)
    assert m[0, 0] == pytest.approx(0.25 * 0.3048) and m[1, 1] == pytest.approx(-0.25 * 0.3048)
    assert m[0, 1] == pytest.approx(0) and m[1, 0] == pytest.approx(0)


def test_codigo_de_civil3d_para_el_huso(tmp_path, monkeypatch):
    from nucleo import sistemas_cs as C
    (tmp_path / "NameMapper.csv").write_text(_NAMEMAPPER, encoding="latin-1")
    monkeypatch.setenv("PDFCAD_CSMAP_DIR", str(tmp_path))
    C._tabla.cache_clear()
    try:
        assert C.codigo_civil3d("32717") == "UTM84-17S" and C.codigo_civil3d("utm84-17s") == "UTM84-17S"
        assert C.codigo_civil3d("CA83VF") == "CA83-VF" and C.codigo_civil3d("EPSG:2229") == "CA83-VF"
    finally:
        C._tabla.cache_clear()


def test_ubicar_el_plano_en_el_sistema_de_la_superficie(win, monkeypatch):
    """Pedido 2026-11-12: plano sin georreferencia → al importar se puede ubicar en el sistema de la superficie
    (centrado, sin giro, a la escala de la hoja). La superficie queda dibujada sobre la hoja y el dibujo de Civil 3D
    toma ese huso."""
    from ui.ventana.ventana_lista_superficies import OK
    vistos = _toasts(win, monkeypatch)
    assert not win.georef.active()
    assert win.importar_superficies([XML], elegir=_todas, ubicar="UTM84-17S") == 1
    g = win.georef
    assert g.active() and g.epsg == 32717 and g.cs_code == "UTM84-17S"
    w, h = win.canvas.tam_hoja()
    pts, _tri, _i, _u = win._sup_geometria(win.superficies[0])
    cx = (pts[:, 0].min() + pts[:, 0].max()) / 2
    cy = (pts[:, 1].min() + pts[:, 1].max()) / 2
    assert g.to_world(w / 2, h / 2) == pytest.approx((cx, cy), abs=1e-6)
    # escala de la hoja: 1 px = pies del cajetín en metros
    e0, _n0 = g.to_world(0, 0)
    e1, _n1 = g.to_world(100, 0)
    import geometry as G
    pies = G.to_cad(100, 0, win.scale, win.rot, win.W, win.H, win.derot, win.zoom)[0] - \
        G.to_cad(0, 0, win.scale, win.rot, win.W, win.H, win.derot, win.zoom)[0]
    assert e1 - e0 == pytest.approx(pies * 0.3048)
    win._redraw()
    assert [it for it in win._sup_items if it.data(0)] and win._sup_revision[0][0] == OK
    tono, titulo, detalle, _a = vistos[-1]
    assert tono == "ok" and "EPSG:32717 (UTM84-17S)" in detalle and "Georreferenciar" in detalle


def test_ctrl_z_deshace_tambien_la_ubicacion_del_plano(win):
    """Pedido 2026-11-12: Ctrl+Z tras «Ubicar el plano» quita la superficie Y la georreferencia; Ctrl+Y las repone.
    Una georreferencia hecha después (Georreferenciar/quitar) no se pierde al deshacer otra cosa."""
    win.importar_superficies([XML], elegir=_todas, ubicar="UTM84-17S")
    puesta = win.georef.to_dict()
    assert win.georef.active() and win.superficies
    win.undo()
    assert not win.georef.active() and not win.superficies
    win.redo()
    assert win.georef.to_dict() == puesta and win.superficies
    win.clear_georef()                                      # quitarla a mano también es un paso
    assert not win.georef.active()
    win.undo()
    assert win.georef.to_dict() == puesta


def test_superficie_en_la_vista_3d_en_lugar_del_suelo_plano(win):
    """Pedido 2026-11-12: la Vista 3D muestra el terreno importado (sus triángulos, a su cota) en lugar del plano
    genérico; apagada en «Capas», vuelve el plano."""
    from nucleo import modelo3d as M3
    _georef(win)
    win.importar_superficies([XML], elegir=_todas)
    sups = win._superficies_3d()
    assert len(sups) == 1 and len(sups[0]["tri"]) == 949
    ft = win.scale / win.zoom
    esc = M3.construir([], [], ft, superficies=sups)
    assert esc.con_superficie and not esc.vacia and len(esc.suelo) == 949 * 3
    z = esc.suelo[:, 2] + esc.origen[2]                      # cotas reales del terreno (pies)
    pts, _t, _i, _u = win._sup_geometria(win.superficies[0])
    assert z.min() == pytest.approx(pts[:, 2].min(), abs=1e-3) and z.max() == pytest.approx(pts[:, 2].max(), abs=1e-3)
    assert np.all(esc.suelo[:, 5] >= 0)                      # normales hacia arriba
    # mismo lugar en planta que el contorno del plano: x = px × ft, y = −py × ft
    x = esc.suelo[:, 0] + esc.origen[0]
    assert x.min() == pytest.approx(sups[0]["px"][:, 0].min() * ft, rel=1e-5)
    plano = M3.construir([], [], ft)
    assert plano.vacia
    win._cambiar_superficie(0, False)
    assert win._superficies_3d() == []


def test_dialogo_sin_georef_ofrece_ubicar_o_importar_asi(win):
    from ui.dialogos.superficies_dialog import SuperficiesDialog, LISTA, AVISO
    win._superficies_datos = {}
    dlg = SuperficiesDialog(win._sup_candidatos([TIF]), "", False, escala='1"=20\'')
    tj = dlg.tarjetas[0]
    assert dlg.rb_ubicar is not None and not dlg.rb_ubicar.isEnabled() and dlg.rb_asi.isChecked()
    assert not dlg.ubicar() and tj.estado_actual()[0] == AVISO and "UTM84-17S" in dlg.lbl_ubicar.text()
    tj.crs.setText("UTM84-17S")                              # con el sistema escrito se sugiere ubicar
    assert dlg.rb_ubicar.isEnabled() and dlg.ubicar() and tj.estado_actual()[0] == LISTA
    assert "UTM84-17S" in dlg.lbl_ubicar.text() and '1"=20\'' in dlg.lbl_ubicar.text()
    assert dlg.crs_para_ubicar()[:2] == ("EPSG:32717", "UTM84-17S")
    dlg.rb_asi.click()                                       # el usuario elige importar así: se respeta
    tj.crs.setText("32717")
    assert not dlg.ubicar() and tj.estado_actual()[0] == AVISO
    con_geo = SuperficiesDialog(win._sup_candidatos([XML]), "EPSG:32717", True)
    assert con_geo.rb_ubicar is None and not con_geo.ubicar()


def test_menu_y_panel_abren_el_selector_de_archivos(win, monkeypatch):
    """Reporte 2026-11-12: el menú y la fila de «Hoja y PDF» mandan `checked` (bool) como `rutas` →
    «'bool' object is not iterable». Desde el menú real se abre el selector y luego el diálogo."""
    from PySide6 import QtWidgets
    from ui.dialogos import superficies_dialog as SD
    _georef(win)
    pedidos = []
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (pedidos.append(1), ([XML], ""))[1]))
    monkeypatch.setattr(SD.SuperficiesDialog, "exec", lambda self: QtWidgets.QDialog.Accepted)
    win._acc["Importar superficies…"].trigger()
    assert pedidos and [r["nombre"] for r in win.superficies] == ["TERRENO"]
    win.importar_superficies(False)                         # como lo llama un botón (clicked(bool))
    assert len(pedidos) == 2 and len(win.superficies) == 2


def QtWidgets_label():
    from PySide6 import QtWidgets
    return QtWidgets.QLabel
