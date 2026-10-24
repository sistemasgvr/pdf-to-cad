"""Planos de fondo del editor y «Agregar todas / Elegir hojas…» (pedido del usuario 2026-10-24).

Con una utilidad agregada desde otro PDF la hoja del editor muestra los planos fundidos y los
rótulos de uno caen sobre los del otro: debajo del lienzo, una pestaña por plano («Todos», «Agua»,
«Alcantarillado»), como las presentaciones de AutoCAD, cambia SOLO la imagen de fondo
(`ui.ventana.ventana_planos`). Y al agregar, la opción de agregar todas las hojas ubicadas o pasar
por «Componer hoja» para elegirlas (`ventana_agregar._como_agregar`).

Usa los PDF sintéticos de `test_agregar_utilidad` (agua azul, alcantarillado rojo, mismo mapa base).
"""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import test_agregar_utilidad as TA  # noqa: E402
from test_agregar_utilidad import app, pdfs, win  # noqa: E402,F401  (fixtures)
from hoja import composite as C, hoja_calcada as H  # noqa: E402


def _img(win):
    img = win.canvas.pixmap_item.pixmap().toImage().convertToFormat(QtGui.QImage.Format_RGB888)
    return np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 3].copy()


def _rgb(arr, px):
    x, y = int(px[0]), int(px[1])
    return tuple(int(v) for v in arr[y, x * 3:x * 3 + 3])


def _azul(c):
    return c[2] > 150 and c[0] < 120


def _rojo(c):
    return c[0] > 150 and c[2] < 120


def _con_agua_y_cloaca(win, pdfs, monkeypatch):
    agua, cloaca = pdfs
    TA._editor_con_agua(win, agua)
    original = _img(win)
    tubo = [TA._px(win, 0, *TA.TUBO["cloaca"][0]), TA._px(win, 0, *TA.TUBO["cloaca"][1])]
    TA._px_esperado[0] = ((tubo[0][0] + tubo[1][0]) / 2, (tubo[0][1] + tubo[1][1]) / 2)
    TA._Reconocer.lineas = [tubo]
    vio = TA._stubs(monkeypatch, win, cloaca, "import")
    win.agregar_utilidad()
    puntos = {"cloaca": TA._px_esperado[0], "agua": TA._px(win, 0, 500.0, TA.TUBO["agua"][0][1])}
    return original, puntos, vio


# ── puro ────────────────────────────────────────────────────────────────────
def test_grupos_y_plano_de_un_grupo():
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1], x=600),
                        C.Piece(2, 0, [0, 0, 1, 1], grupo=1)], marco=[-36.0, -36.0, 1236.0, 436.0],
                       utilidades_grupo={0: ["AGUA"], 1: ["ALCANTARILLADO"]})
    assert H.grupos(comp) == [0, 1]
    assert H.grupos(C.Composite([C.Piece(0, 0, [0, 0, 1, 1])])) == []          # una sola utilidad: sin pestañas
    sub = H.solo_grupo(comp, 0)
    assert [(p.source, p.page) for p in sub.pieces] == [(0, 0), (0, 1)]
    assert sub.marco == comp.marco and sub.utilidades_grupo == {}
    d = comp.to_dict()
    assert d["utilidades_grupo"] == {"0": ["AGUA"], "1": ["ALCANTARILLADO"]}
    assert C.Composite.from_dict(d).utilidades_grupo == comp.utilidades_grupo
    assert "utilidades_grupo" not in C.Composite([C.Piece(0, 0, [0, 0, 1, 1])]).to_dict()   # el dict de siempre


# ── la ventana ──────────────────────────────────────────────────────────────
def test_pestanas_de_los_planos_y_cada_una_su_plano(win, pdfs, monkeypatch, app):
    original, puntos, _vio = _con_agua_y_cloaca(win, pdfs, monkeypatch)
    assert win.composite.utilidades_grupo == {0: ["AGUA"], 1: ["ALCANTARILLADO"]}
    bar = win.barra_planos
    assert win._fila_planos.isVisibleTo(win)
    assert [bar.tabText(i) for i in range(bar.count())] == ["Todos", "Agua", "Alcantarillado"]
    assert bar.currentIndex() == 0 and win._vista_fondo is None
    todos = _img(win)
    assert _azul(_rgb(todos, puntos["agua"])) and _rojo(_rgb(todos, puntos["cloaca"]))
    antes = dict(pipes=[dict(p) for p in win.pipes], undo=len(win._undo), tam=win.canvas.tam_hoja(), dirty=win._dirty)
    # el plano del alcantarillado: solo su PDF
    bar.setCurrentIndex(2)
    assert win._vista_fondo == 1
    solo = _img(win)
    assert _rojo(_rgb(solo, puntos["cloaca"])) and not _azul(_rgb(solo, puntos["agua"]))
    page = win._pagina_fondo()
    assert page is not None and page.parent is win._planos_docs[1][1]
    # el del editor: el MISMO plano que se veía antes de agregar
    bar.setCurrentIndex(1)
    assert np.array_equal(_img(win), original)
    # «Todos» otra vez, y nada de lo dibujado cambió
    bar.setCurrentIndex(0)
    assert np.array_equal(_img(win), todos)
    assert win.pipes == antes["pipes"] and len(win._undo) == antes["undo"]
    assert win.canvas.tam_hoja() == pytest.approx(antes["tam"]) and win._dirty == antes["dirty"]
    win._plano_siguiente(-1)                      # Ctrl+RePág desde «Todos» → el último
    assert bar.currentIndex() == 2 and win._vista_fondo == 1


def test_el_plano_a_la_vista_se_guarda_y_vuelve(win, pdfs, monkeypatch, app, tmp_path):
    _original, puntos, _vio = _con_agua_y_cloaca(win, pdfs, monkeypatch)
    win.barra_planos.setCurrentIndex(2)
    solo = _img(win)
    ruta = tmp_path / "dos planos.digproj"
    win._write_project(str(ruta))
    from ui.ventana import app_window
    w2 = app_window.Main()
    try:
        w2._open_project_path(str(ruta))
        app.processEvents()
        assert w2._vista_fondo == 1 and w2.barra_planos.currentIndex() == 2
        assert np.array_equal(_img(w2), solo)
        assert w2._pagina_fondo() is None               # su PDF se arma aparte, sin esperar…
        assert _esperar(app, lambda: 1 in w2._planos_docs)
        assert w2._pagina_fondo() is not None           # …y luego las teselas y el imán lo usan
        w2.barra_planos.setCurrentIndex(0)              # «Todos» se dibuja de la hoja de trabajo
        img = _img(w2)
        assert _azul(_rgb(img, puntos["agua"])) and _rojo(_rgb(img, puntos["cloaca"]))
    finally:
        w2._dirty = False
        w2.close()
        app.processEvents()


def _esperar(app, cond, seg=30.0):
    import time
    fin = time.time() + seg
    while time.time() < fin:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_hoja_nueva_vuelve_a_todos(win, pdfs, monkeypatch, app):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    win.barra_planos.setCurrentIndex(1)
    assert win._vista_fondo == 0 and win._planos_docs
    rutas = [e[2] for e in win._planos_docs.values()]
    win._load_page(0)                                   # otra hoja en el editor
    assert win._vista_fondo is None and not win._planos_docs and not any(os.path.exists(r) for r in rutas)


# ── «Agregar todas» o «Elegir hojas…» ──────────────────────────────────────
def test_elegir_hojas_pasa_por_componer_hoja(win, pdfs, monkeypatch, app):
    agua, cloaca = pdfs
    TA._editor_con_agua(win, agua)
    tubo = [TA._px(win, 0, *TA.TUBO["cloaca"][0]), TA._px(win, 0, *TA.TUBO["cloaca"][1])]
    TA._px_esperado[0] = tubo[0]
    TA._Reconocer.lineas = [tubo]
    TA._stubs(monkeypatch, win, cloaca, "import")
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_como_agregar", lambda self, *a: "elegir")
    visto = {}

    def componer(parent, sources, comp, hidden, **kw):
        # el compositor recibe las hojas ubicadas ya marcadas; el usuario deja SOLO una
        visto["piezas"] = [(p.source, p.page) for p in comp.pieces]
        visto["sugerencia"] = kw.get("sugerencia")
        uno = C.Composite.from_dict(comp.to_dict())
        uno.pieces = [p for p in uno.pieces if p.page == 1]       # la 17-10 del alcantarillado
        return uno, sources, hidden
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", componer)
    win.agregar_utilidad()
    assert sorted(visto["piezas"]) == [(0, 0), (0, 1)] and visto["sugerencia"] is False
    assert [(p.source, p.page, p.grupo) for p in win.composite.pieces if p.grupo] == [(1, 1, 1)]
    assert [p["layer"] for p in win.pipes] == ["AGUA", "ALCANTARILLADO"]
    assert win._agregando is None and win._respaldo is None


def test_cancelar_la_pregunta_no_toca_el_editor(win, pdfs, monkeypatch, app):
    agua, cloaca = pdfs
    TA._editor_con_agua(win, agua)
    antes = (win.doc, win.composite.to_dict(), [dict(p) for p in win.pipes])
    TA._stubs(monkeypatch, win, cloaca, "import")
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_como_agregar", lambda self, *a: None)
    win.agregar_utilidad()
    assert (win.doc, win.composite.to_dict(), win.pipes) == antes
    assert win._agregando is None and win._respaldo is None
