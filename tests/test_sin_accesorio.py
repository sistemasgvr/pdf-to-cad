"""«No hay codo / T / Y / cruz» (pedido del usuario 2026-10-30): marcar que en un punto no va accesorio. Deja de
calcularse (plano, normativas, 3D), el conflicto que lo originó y el cruce con accesorio de ese punto dejan de
marcarse, se deshace con Ctrl+Z, va al .digproj y al DXF (PDFCAD_SIN_ACCESORIO para el plugin)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import sin_accesorio as SA  # noqa: E402


def test_nucleo_filtrar_suprimir_y_conflicto():
    accs = [dict(x=0, y=0, tipo="codo", pipes=[0]), dict(x=100, y=0, tipo="cruz", pipes=[1, 2])]
    m = SA.marca(accs[1])
    assert SA.filtrar(accs, [m], 3.0) == accs[:1]
    assert SA.suprime([m], "cruce", 101, 0, 3.0) and not SA.suprime([m], "cruce", 50, 0, 3.0)

    class C:
        clave, x, y, pipes = "codos", 5.0, 0.0, [0]
    assert SA.de_conflicto(accs, C, 3.0, 10.0) is accs[0]
    m2 = SA.marca(accs[0], C)
    assert SA.suprime([m2], "codos", 30, 0, 3.0)        # se marcó desde ese conflicto (aunque no esté en el codo)
    assert not SA.suprime([m2], "retorno", 30, 0, 3.0)


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
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _cruz(w):
    """Dos tuberías de agua que se cruzan en X a la misma cota: la app pone una cruz (sin conflicto)."""
    w.pipes = [dict(layer="AGUA", pts=[(100, 300), (900, 300)], name="", diam=8.0, pipe_size="",
                    inv_start=-4.0, inv_end=-4.0),
               dict(layer="AGUA", pts=[(500, 100), (500, 600)], name="", diam=8.0, pipe_size="",
                    inv_start=-4.0, inv_end=-4.0)]
    w._refresh_lists(); w._redraw()


def test_no_hay_cruz_en_un_cruce_a_la_misma_cota(win):
    _cruz(win)
    a = win.accesorio_en(500, 300, 5)
    assert a is not None and a["tipo"] == "cruz"
    n_conf = len(win._conflictos)
    pasos = len(win._undo)
    assert win.marcar_sin_accesorio(a)
    assert len(win._undo) == pasos + 1 and len(win.sin_accesorio) == 1
    accs, _normas, _f = win._calcular_accesorios(win.scale / win.zoom)
    assert not any(x["tipo"] == "cruz" for x in accs)            # ya no se calcula
    assert len(win._conflictos) == n_conf                       # y no aparece un conflicto en su lugar
    assert not any(abs(h[0] - 500) < 2 and abs(h[1] - 300) < 2 for h in win._conflict_hits)
    win.undo()
    assert win.sin_accesorio == []
    accs, _normas, _f = win._calcular_accesorios(win.scale / win.zoom)
    assert any(x["tipo"] == "cruz" for x in accs)


def test_menu_del_plano_ofrece_no_hay_y_volver_a_poner(win):
    from PySide6 import QtWidgets
    _cruz(win)
    menu = QtWidgets.QMenu()
    win._menu_sin_accesorio(menu, 500, 300)
    textos = [x.text() for x in menu.actions() if x.text()]
    assert textos == ["No hay cruz"]
    menu.actions()[0].trigger()
    menu2 = QtWidgets.QMenu()
    win._menu_sin_accesorio(menu2, 500, 300)
    assert [x.text() for x in menu2.actions() if x.text()] == ["Volver a poner la cruz"]
    menu2.actions()[0].trigger()
    assert win.sin_accesorio == []


def test_va_al_proyecto_y_al_dxf(win):
    import ezdxf
    import project_io
    from exportar import dxf_export
    import config as C
    _cruz(win)
    win.marcar_sin_accesorio(win.accesorio_en(500, 300, 5))
    model = project_io.build_model_dict(win)
    assert project_io.parse_model(model)["sin_accesorio"] == win.sin_accesorio
    doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
    dxf_export.merge_into(win, doc, marks=True)
    pts = [e for e in doc.modelspace().query("POINT") if e.dxf.layer == "PDFCAD_SIN_ACCESORIO"]
    assert len(pts) == 1
    xd = pts[0].get_xdata("PDFCAD")
    assert ("1000", "PDFCAD_SIN_ACCESORIO") in [(str(c), v) for c, v in xd] and any(v == "TIPO=cruz" for _c, v in xd)
    x, y = win._to_cad(500, 300)
    assert pts[0].dxf.location[0] == pytest.approx(x) and pts[0].dxf.location[1] == pytest.approx(y)


def test_no_hay_codo_desde_un_conflicto_de_codos(win):
    # dos codos con un tramo de 0.4 ft entre ellos: conflicto «Tramo muy corto entre codos»
    win.pipes = [dict(layer="AGUA", pts=[(100, 100), (500, 100), (504, 104), (504, 600)], name="", diam=8.0,
                      pipe_size="", inv_start=-4.0, inv_end=-4.0)]
    win._refresh_lists(); win._redraw()
    codos = [c for c in win._conflictos if c.clave == "codos"]
    assert codos, [c.clave for c in win._conflictos]
    c = codos[0]
    a = win.accesorio_de_conflicto(c.id)
    assert a is not None and a["tipo"] == "codo"
    win.marcar_sin_accesorio(a, c)
    assert not any(k.clave == "codos" for k in win._conflictos)
    accs, _n, _f = win._calcular_accesorios(win.scale / win.zoom)
    assert SA.en(win.sin_accesorio, a["x"], a["y"], 1) is not None
    assert all(SA.en(win.sin_accesorio, x["x"], x["y"], 3) is None for x in accs)


def test_3d_no_dibuja_el_accesorio_marcado():
    from nucleo import modelo3d
    pipes = [dict(layer="AGUA", pts=[(100, 300), (900, 300)], diam=8.0, inv_start=-4.0, inv_end=-4.0),
             dict(layer="AGUA", pts=[(500, 100), (500, 600)], diam=8.0, inv_start=-4.0, inv_end=-4.0)]
    e0 = modelo3d.construir(pipes, [], 0.1)
    n0 = sum(1 for o in e0.objetos.values() if o["tipo"] == "accesorio")
    e1 = modelo3d.construir(pipes, [], 0.1, sin_accesorio=[dict(x=500.0, y=300.0, tipo="cruz", conf=None)])
    n1 = sum(1 for o in e1.objetos.values() if o["tipo"] == "accesorio")
    assert n0 >= 1 and n1 == n0 - 1
