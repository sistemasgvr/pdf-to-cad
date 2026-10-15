"""Reporte del usuario 2026-10-15:
1. Eléctrico/telecom: un vértice simple (sin caja) se puede convertir en curva, y quitarla
   no deja una caja inventada.
2. Las marcas de vértices y buzones no crecen sin fin al acercarse (tope en pantalla).
3. El diámetro sin familia se ve, se elige y no se pierde (por defecto o leído del plano).
4. Una conexión vertical aprobada sigue las cotas ACTUALES de sus utilidades."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import edicion_bloque, model_ops, vertice_curva  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
CRUCES = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")


# ─────────────────────────── 1. vértice → curva ───────────────────────────

def _electrica(pts=((0, 0), (200, 0), (200, 200), (400, 200))):
    return dict(layer="ELECTRICO", pts=[tuple(q) for q in pts], diam=4.0)


def test_vertices_libres_y_curva_que_se_quita_sin_dejar_caja():
    p = _electrica()
    caja = dict(x=200.0, y=200.0, net="conduit", cod="CAJA-1")        # el vértice 2 ya tiene una caja
    estructuras = [caja]
    assert vertice_curva.vertices_libres(p, estructuras) == [1]       # puntas y vértice con caja: no
    assert vertice_curva.vertices_libres(dict(p, layer="AGUA"), []) == []      # presión: no
    assert vertice_curva.vertice_en(p, estructuras, 205, 3, 10) == 1
    assert vertice_curva.vertice_en(p, estructuras, 260, 3, 10) is None
    s = vertice_curva.a_curva(estructuras, p, 1)
    nuevas = model_ops.rebuild_structures([p], estructuras)           # conductos: se conserva
    cv = next(e for e in nuevas if e.get("curve"))
    assert cv["cod"].startswith("CV-") and cv["radius_ft"] == 0.0 and vertice_curva.se_quita(cv)
    assert not vertice_curva.se_quita(dict(caja, curve=True))          # era caja: vuelve a ser caja
    assert s["vertice"]


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _lienzo(w):
    """Hoja en blanco con una línea eléctrica de tres tramos (sin cajas)."""
    hoja = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=40.0, scale_ft_per_pt=40 / 72.0,
                unit="in", landscape=True)
    w.blank_canvas = True
    w.paper = dict(hoja)
    w._load_blank_page(hoja)
    w.pipes.append(dict(layer="ELECTRICO", pts=[(100.0, 100.0), (600.0, 100.0), (600.0, 600.0), (1100.0, 600.0)],
                        ab=False, diam=4.0, diam_unit="in", inv_start=-4.0, inv_end=-4.0))
    w._rebuild_structures(); w._refresh_lists()
    w._show_tab(0); w.pipe_list.setCurrentRow(0)
    w._redraw()


def test_convertir_vertice_en_curva_en_la_ventana(win):
    from PySide6 import QtWidgets
    _lienzo(win)
    assert not win.structures                                          # eléctrico: sin cajas automáticas
    # con la utilidad elegida sus vértices interiores se ven
    from ui.comun.marcas_lienzo import Marca
    assert sum(isinstance(it, Marca) for it in win._overlay) == 2
    menu = QtWidgets.QMenu()
    win._menu_vertice(menu, 601.0, 99.0)
    assert [a.text() for a in menu.actions() if a.text()] == ["Convertir este vértice en curva"]
    win.convertir_vertice_en_curva(0, 1)
    cv = [s for s in win.structures if s.get("curve")]
    assert len(cv) == 1 and cv[0]["cod"] == "CV-1" and (cv[0]["x"], cv[0]["y"]) == (600.0, 100.0)
    assert win.sel_curve == win.structures.index(cv[0])
    assert win.curve_is_bz.text() == "Quitar la curva (vuelve a ser un vértice)"
    # al DXF va como esquina curva (PDFCAD_CURVE), igual que un codo reconocido
    import ezdxf
    from exportar import dxf_export
    doc = ezdxf.new(setup=True)
    dxf_export.merge_into(win, doc, marks=True)
    marcas = [str(v) for e in doc.modelspace() if e.has_xdata("PDFCAD") for _c, v in e.get_xdata("PDFCAD")]
    assert "PDFCAD_CURVE" in marcas
    win._curve_is_bz_toggled()                                          # quitarla: no queda ninguna caja
    assert win.structures == []
    win.undo()
    assert [s.get("curve") for s in win.structures] == [True]


# ─────────────────────────── 2. tope en pantalla ───────────────────────────

def test_las_marcas_no_crecen_sin_fin_al_acercarse():
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun.marcas_lienzo import Marca
    m = Marca(0, 0, 6, QtGui.QPen(), QtGui.QBrush(), tope_px=8)
    assert m.radio_en(0.5) == 6                       # lejos: como siempre (6 px del plano = 3 en pantalla)
    assert m.radio_en(1.0) == 6
    assert m.radio_en(10.0) == pytest.approx(0.8)     # de cerca: 8 px en pantalla, no 60


# ─────────────────────────── 3. diámetro sin familia ───────────────────────────

def test_diametro_sin_familia_cuenta():
    assert model_ops.diametro(dict(diam=12.0)) == (12.0, True)               # precargado
    assert model_ops.diametro(dict(diam=8.0)) == (8.0, False)                # leído del plano
    assert model_ops.diametro(dict(diam=12.0, diam_elegido=True)) == (12.0, False)
    assert model_ops.diametro(dict(diam=24.0, pipe_size="24 in")) == (24.0, False)
    assert model_ops.diametro({}) == (12.0, True)
    # copiar/pegar sin familia lleva el diámetro (antes quedaba en 12")
    src, dst = dict(diam=8.0, diam_elegido=True), dict(diam=12.0)
    edicion_bloque.aplicar([dst], [0], {"tamano": edicion_bloque.valores_de(src)["tamano"]})
    assert dst["diam"] == 8.0 and dst["pipe_size"] == "" and model_ops.diametro(dst) == (8.0, False)


def test_panel_muestra_y_elige_el_diametro_sin_familia(win):
    _lienzo(win)
    p = win.pipes[0]
    p["diam"] = 8.0; p["diam_elegido"] = True
    win._show_tab(0); win.pipe_list.setCurrentRow(-1); win.pipe_list.setCurrentRow(0)
    cb = win.prop_size
    assert cb.isEnabled() and cb.currentText() == '8"' and win.lbl_prop_size.text() == "Diámetro:"
    win.prop_name.setText("Línea A"); win._prop_changed()               # editar el nombre no lo pisa
    assert p["diam"] == 8.0
    cb.setCurrentIndex(cb.findData(edicion_bloque.dato_diam(6)))
    assert p["diam"] == 6.0 and p["diam_elegido"] and not p.get("pipe_size")
    cb.setCurrentIndex(0)                                                # «12" (Por defecto)»
    assert model_ops.diametro(p) == (12.0, True)


# ─────────────────────────── 4. cotas de las conexiones verticales ───────────────────────────

def test_conexion_vertical_sigue_las_cotas_actuales(win):
    win._open_project_path(CRUCES); win._redraw()
    c = win.cross_connections[0]
    ia = c["pipe_a"]
    viejo = c["z_a"]
    win.pipes[ia]["inv_start"] = float(win.pipes[ia].get("inv_start") or 0.0) - 3.0
    win.pipes[ia]["inv_end"] = float(win.pipes[ia].get("inv_end") or 0.0) - 3.0
    win.pipes[ia].pop("vertex_inv_in", None); win.pipes[ia].pop("vertex_inv_out", None)
    win._redraw()
    assert c["z_a"] == pytest.approx(viejo - 3.0, abs=1e-6)
    # el DXF lleva la cota nueva
    import ezdxf
    from exportar import dxf_export
    doc = ezdxf.new(setup=True)
    dxf_export.merge_into(win, doc, marks=True)
    zs = [v for e in doc.modelspace() if e.has_xdata("PDFCAD")
          for _c, v in e.get_xdata("PDFCAD") if str(v).startswith("Z_A=")]
    assert f"Z_A={c['z_a']}" in zs
