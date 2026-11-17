"""Superficies — pedido del usuario 2026-11-14:
1. Vista 3D: estilos de la superficie (relieve, cotas en franjas, malla) y curvas de nivel.
2. Propiedades al elegir una superficie (en el Inventario o en el lienzo): ruta del archivo original y las estadísticas
   clásicas de Civil 3D.
3. Las superficies en el perfil longitudinal de la app (y del plugin: ver el arnés PerfilPruebas, M12)."""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import perfil_datos as PD  # noqa: E402
from nucleo import perfil_recorrido as PR  # noqa: E402
from nucleo import perfil_superficies as PS  # noqa: E402
from nucleo import superficie_estadisticas as E  # noqa: E402
from nucleo import superficies as S  # noqa: E402
from nucleo import superficies_leer as L  # noqa: E402

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "superficies")
XML = os.path.join(DIR, "TERRENO.xml")


def _terreno():
    s = L.leer("TERRENO.xml", open(XML, "rb").read())[0]
    return s.puntos, s.triangulos[~s.invisibles]


# ───────────────────────── 1. estilos de la Vista 3D ─────────────────────────

def test_estilos_y_curvas_de_nivel_en_el_shader():
    from nucleo import mallas3d as M
    from ui.comun import visor3d_shaders as SH
    assert SH.ESTILOS_SUPERFICIE == ("relieve", "cotas", "malla")
    for u in ("uEstiloSup", "uCurvas", "uIntervalo", "uZBase", "uRangoZ", "uBordes"):
        assert u in SH.FRAG
    assert "@" not in SH.FRAG                                       # constantes ya puestas
    # intervalo automático: unas 15 curvas en el desnivel, en un paso «redondo»
    assert M.intervalo_curvas(180.6, 183.9) == 0.25
    assert M.intervalo_curvas(0, 300) == 20.0 and M.intervalo_curvas(5, 5) == 1.0
    # franjas de cota: morado abajo, rojo arriba (la leyenda usa la misma cuenta que el shader)
    bajo, alto = SH.arcoiris(0.0), SH.arcoiris(1.0)
    assert bajo[2] > bajo[1] and alto[0] > 0.9 and alto[2] < 0.2


def test_la_superficie_lleva_color_por_cota_y_la_geometria_no_cambia():
    from nucleo import mallas3d as M
    from nucleo import modelo3d as M3
    pts, tri = _terreno()
    con, sin = M.tin(pts, tri, M3.COLOR_TERRENO), M.tin(pts, tri, M3.COLOR_TERRENO, relieve=False)
    assert np.array_equal(con[:, :6], sin[:, :6])
    z = pts[tri].reshape(-1, 3)[:, 2]
    assert np.allclose(con[:, 6:9], M.color_por_cota(z, z.min(), z.max()), atol=1e-6)


def test_visor_rango_y_uniformes_del_estilo():
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from nucleo import modelo3d as M3
    from ui.comun import superficie3d as S3
    from ui.comun.visor3d import Visor3D
    pts, tri = _terreno()
    esc = M3.construir([], [], 1.0, superficies=[dict(px=np.column_stack([pts[:, 0], -pts[:, 1]]), z=pts[:, 2],
                                                      tri=tri)])
    v = Visor3D()
    v.set_escena(esc)
    r = S3.rango(esc)
    assert r[0] + esc.origen[2] == pytest.approx(pts[:, 2].min(), abs=1e-3)
    assert r[1] + esc.origen[2] == pytest.approx(pts[:, 2].max(), abs=1e-3)
    assert S3.intervalo(v) == 0.25
    v.intervalo_curvas = 1.0
    assert S3.intervalo(v) == 1.0
    vistos = {}

    class P:
        def setUniformValue1f(self, n, x):
            vistos[n] = x

        def setUniformValue(self, n, x):
            vistos[n] = x
    v.estilo_superficie, v.curvas_nivel = "malla", True
    S3.uniformes(v, P())
    assert vistos["uEstiloSup"] == 2.0 and vistos["uCurvas"] == 1.0 and vistos["uIntervalo"] == 1.0
    assert vistos["uZBase"] == pytest.approx(esc.origen[2])


# ───────────────────────── 2. propiedades ─────────────────────────

def test_estadisticas_de_un_plano_inclinado():
    # 100 × 100 ft con 10 % de pendiente en X: cota 0 → 10
    pts = np.array([[0, 0, 0], [100, 0, 10], [100, 100, 10], [0, 100, 0]], float)
    tri = np.array([[0, 1, 2], [0, 2, 3]])
    st = E.estadisticas(pts, tri, None, "foot")
    assert st["n_puntos"] == 4 and st["n_triangulos"] == 2
    assert (st["z_min"], st["z_max"], st["z_media"]) == (0.0, 10.0, 5.0)
    assert st["area_2d_ft2"] == pytest.approx(10000.0)
    assert st["area_3d_ft2"] == pytest.approx(10000.0 * np.hypot(1, 0.1))
    assert st["pendiente_media_pct"] == pytest.approx(10.0) and st["pendiente_max_pct"] == pytest.approx(10.0)
    assert st["lado_min_ft"] == pytest.approx(100.0)
    # X/Y en metros: áreas y pendientes en pies (la cota ya viene en pies)
    pm = pts * np.array([0.3048, 0.3048, 1.0])
    sm = E.estadisticas(pm, tri, None, "meter")
    assert sm["area_2d_ft2"] == pytest.approx(10000.0) and sm["pendiente_media_pct"] == pytest.approx(10.0)
    assert sm["x_max"] == pytest.approx(30.48)                     # la extensión, en la unidad del dibujo


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from geo import georef
    from ui.ventana.app_window import Main
    w = Main()
    hoja = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=20.0, scale_ft_per_pt=20 / 72.0,
                unit="in", landscape=True)
    w.blank_canvas = True
    w.paper = dict(hoja)
    w._load_blank_page(hoja)
    w._info = lambda *a, **k: None
    w.georef = georef.Georef([[0.05, 0, 639740.0], [0, -0.05, 9336890.0], [0, 0, 1]], 32717)
    yield w
    i18n_core._current_lang = previo
    w._dirty = False
    w.close()


def test_propiedades_de_la_superficie_en_el_inventario_y_en_el_lienzo(win):
    from nucleo.model import TAB_PIPE, TAB_SUP
    assert win.importar_superficies([XML], elegir=lambda cs: [c for c in cs if c.sup is not None]) == 1
    reg = win.superficies[0]
    assert reg["ruta"] == os.path.abspath(XML)                       # la ruta del archivo original
    win._redraw()
    win._show_tab(TAB_SUP)
    win.sup_list.setCurrentRow(0)
    win._update_ui()
    assert not win.gprop_sup.isHidden()
    c = win._sup_campos
    assert c["ruta"].text() == os.path.abspath(XML) and c["nombre"].text() == "TERRENO"
    assert c["puntos"].text() == "576" and c["triangulos"].text() == "949"
    pts, _t, _i, _u = win._sup_geometria(reg)
    assert c["cota_min"].text() == f"{pts[:, 2].min():.2f} ft"
    assert "%" in c["pend_media"].text() and "acres" in c["area_2d"].text()
    assert win.vacio_propiedades.isHidden()                         # algo elegido: sin «Nada seleccionado»
    tipo, _txt = win.cabecera_inspector._elegido()
    assert tipo == "sup"
    # lienzo: un clic en el contorno la elige (sin mover el plano); uno lejos, no
    win._show_tab(TAB_PIPE)
    camino = next(it for it in win._sup_items if it.data(0))
    p = camino.path().pointAtPercent(0.3)
    vista = win.canvas.transform()
    assert win._superficie_bajo_clic(p.x(), p.y()) == 0
    centro = camino.path().boundingRect().center()
    assert win._superficie_bajo_clic(centro.x(), centro.y()) is None   # adentro: no (cubre todo el plano)
    assert win._pick(p.x(), p.y())
    assert win._current_tab() == TAB_SUP and win.sup_list.currentRow() == 0
    assert win.canvas.transform() == vista and not win.gprop_sup.isHidden()


def test_proyecto_viejo_sin_ruta_lo_dice(win):
    from nucleo.model import TAB_SUP
    win.importar_superficies([XML], elegir=lambda cs: [c for c in cs if c.sup is not None])
    del win.superficies[0]["ruta"]
    win._show_tab(TAB_SUP)
    win.sup_list.setCurrentRow(0)
    win._update_ui()
    assert "TERRENO.xml" in win._sup_campos["ruta"].text() and "2.1.0" in win._sup_campos["ruta"].text()
    assert win.btn_sup_carpeta.isHidden()


# ───────────────────────── 3. perfil ─────────────────────────

def test_indice_tin_da_lo_mismo_que_cota_en():
    pts, tri = _terreno()
    ind = PS.IndiceTin(pts[:, :2], pts[:, 2], tri)
    rng = np.random.default_rng(3)
    lo, hi = pts[:, :2].min(axis=0), pts[:, :2].max(axis=0)
    xy = lo + (hi - lo) * rng.random((300, 2)) * 1.2 - (hi - lo) * 0.1     # también fuera
    for (x, y), z in zip(xy, ind.cotas(xy)):
        ref = S.cota_en(pts, tri, x, y)
        assert (np.isnan(z) and ref is None) or z == pytest.approx(ref, abs=1e-9)


def test_perfil_de_la_app_con_las_superficies(win):
    win.importar_superficies([XML], elegir=lambda cs: [c for c in cs if c.sup is not None])
    sups = win._superficies_perfil()
    assert [n for n, _i in sups] == ["TERRENO"]
    pts, tri, _inv, _u = win._sup_geometria(win.superficies[0])
    plano = win._sup_a_plano(pts[:, :2])
    lo, hi = plano.min(axis=0), plano.max(axis=0)
    y = (lo[1] + hi[1]) / 2
    # una tubería que cruza la superficie y sale de ella (a la derecha)
    pipes = [dict(layer="AGUA", pts=[(lo[0] + 20, y), (hi[0] + 400, y)], diam=8.0, inv_start=170.0, inv_end=169.0)]
    ft = win.scale / win.zoom
    rec = PR.desde(pipes, 0, lo[0] + 100, y, ft)
    perfil = PD.armar(pipes, [], [], rec, ft, superficies=sups)
    ((nombre, linea),) = perfil.superficies
    assert nombre == "TERRENO"
    dentro = [(e, z) for e, z in linea if z is not None]
    assert dentro and any(z is None for _e, z in linea)            # fuera de la superficie la línea se corta
    paso = perfil.pasos[0]
    e, z = dentro[len(dentro) // 2]
    x, yy = paso.punto_en(e)
    assert z == pytest.approx(S.cota_en(np.column_stack([plano, pts[:, 2]]), tri, x, yy), abs=1e-6)
    assert perfil.z_max >= max(z for _e, z in dentro) - 1e-9        # el rango vertical la abarca
    # sin superficies: el perfil de siempre
    assert PD.armar(pipes, [], [], rec, ft).superficies == []
    # apagada en «Capas»: no va al perfil y cambia la firma del perfil
    antes = win._firma_superficies_perfil()
    win._cambiar_superficie(0, False)
    assert win._superficies_perfil() == [] and win._firma_superficies_perfil() != antes
