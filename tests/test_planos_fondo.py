"""Planos de fondo y utilidades como CAPAS de AutoCAD (pedidos del usuario 2026-10-24 y 2026-10-26).

Con una utilidad agregada desde otro PDF la hoja del editor muestra los planos fundidos. En el
desplegable «Capas» cada plano (grupo de hojas) y cada utilidad dibujada se enciende y apaga: los
planos cambian SOLO la imagen de fondo (`ui.ventana.ventana_planos`; cualquier combinación, o
ninguno = papel vacío) y las utilidades apagadas no se pintan ni se eligen (`ventana_capas`). Al
agregar, siempre se pasa por «Componer hoja» con las hojas ubicadas marcadas.

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


def _planos(win, *encendidos):
    from ui.comun import capas_popup as CP
    for g in win._grupos_planos():
        if (g in encendidos) != (g in win._planos_encendidos()):
            win._cambiar_capa(CP.PLANO, g, g in encendidos)
    assert win._planos_encendidos() == sorted(encendidos)


def _esperar(app, cond, seg=30.0):
    import time
    fin = time.time() + seg
    while time.time() < fin:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if cond():
            return True
        time.sleep(0.01)
    return False


# ── puro ────────────────────────────────────────────────────────────────────
def test_grupos_y_plano_de_un_grupo():
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1], x=600),
                        C.Piece(2, 0, [0, 0, 1, 1], grupo=1)], marco=[-36.0, -36.0, 1236.0, 436.0],
                       utilidades_grupo={0: ["AGUA"], 1: ["ALCANTARILLADO"]})
    assert H.grupos(comp) == [0, 1]
    assert H.grupos(C.Composite([C.Piece(0, 0, [0, 0, 1, 1])])) == []          # una sola utilidad: sin planos
    sub = H.solo_grupo(comp, 0)
    assert [(p.source, p.page) for p in sub.pieces] == [(0, 0), (0, 1)]
    assert sub.marco == comp.marco and sub.utilidades_grupo == {}
    dos = H.solo_grupos(comp, {1, 0})
    assert [(p.source, p.page) for p in dos.pieces] == [(0, 0), (0, 1), (2, 0)] and dos.marco == comp.marco
    from ui.ventana.ventana_planos import clave_planos
    assert clave_planos([0, 1], [0, 1]) is None                    # todos = la hoja de trabajo
    assert clave_planos([1], [0, 1, 2]) == frozenset({1})
    assert clave_planos([], [0, 1]) == frozenset()                  # ninguno
    d = comp.to_dict()
    assert d["utilidades_grupo"] == {"0": ["AGUA"], "1": ["ALCANTARILLADO"]}
    assert C.Composite.from_dict(d).utilidades_grupo == comp.utilidades_grupo
    assert "utilidades_grupo" not in C.Composite([C.Piece(0, 0, [0, 0, 1, 1])]).to_dict()   # el dict de siempre


def test_marcas_de_utilidades_apagadas_no_se_pintan(app):
    from ui.comun.capa_marcas import GrupoMarcas
    sc = QtWidgets.QGraphicsScene()
    g = GrupoMarcas(sc, 1.0)
    for x in (0.0, 100.0, 200.0):
        it = QtWidgets.QGraphicsEllipseItem(-4, -4, 8, 8)
        it.setPos(x, 0.0)
        it.setZValue(10)
        g.agregar(it)
    capa = g.capas[10]
    duenas = {0.0: frozenset({"AGUA"}), 100.0: frozenset({"AGUA", "GAS"}), 200.0: frozenset()}
    todo = QtCore.QRectF(-50, -50, 400, 100)
    g.fijar_ocultas({"AGUA"}, lambda x, y: duenas[x])
    assert capa.cerca(todo).tolist() == [1, 2]          # la de AGUA sola se oculta; sin dueña, se ve
    g.fijar_ocultas({"AGUA", "GAS"}, lambda x, y: duenas[x])
    assert capa.cerca(todo).tolist() == [2]
    g.fijar_ocultas(set(), lambda x, y: duenas[x])
    assert capa.cerca(todo).tolist() == [0, 1, 2]


# ── la ventana ──────────────────────────────────────────────────────────────
def test_planos_como_capas_cualquier_combinacion(win, pdfs, monkeypatch, app):
    from ui.comun import capas_popup as CP
    original, puntos, _vio = _con_agua_y_cloaca(win, pdfs, monkeypatch)
    assert win.composite.utilidades_grupo == {0: ["AGUA"], 1: ["ALCANTARILLADO"]}
    est = win._estado_capas()
    assert [(f.clave, f.nombre, f.encendida) for f in est.planos] == [(0, "Agua", True), (1, "Alcantarillado", True)]
    assert [(f.clave, f.encendida) for f in est.utilidades] == [("AGUA", True), ("ALCANTARILLADO", True)]
    assert win._vista_fondo is None
    todos = _img(win)
    assert _azul(_rgb(todos, puntos["agua"])) and _rojo(_rgb(todos, puntos["cloaca"]))
    antes = dict(pipes=[dict(p) for p in win.pipes], undo=len(win._undo), tam=win.canvas.tam_hoja(), dirty=win._dirty)
    # apagar el plano del agua: solo el del alcantarillado
    _planos(win, 1)
    assert win._vista_fondo == frozenset({1})
    solo = _img(win)
    assert _rojo(_rgb(solo, puntos["cloaca"])) and not _azul(_rgb(solo, puntos["agua"]))
    page = win._pagina_fondo()
    assert page is not None and page.parent is win._planos_docs[frozenset({1})][1]
    # solo el del editor: el MISMO plano que se veía antes de agregar
    _planos(win, 0)
    assert np.array_equal(_img(win), original)
    # ninguno: papel vacío, sin imán a la tinta ni teselas
    _planos(win)
    assert win._fondo_apagado and not win.canvas.pixmap_item.isVisible()
    assert win._pagina_fondo() is None and win._snap(*puntos["agua"]) == puntos["agua"]
    assert win.btn_capas.text().startswith("Capas · 2")
    # todos otra vez, y nada de lo dibujado cambió
    win._encender_capas()
    assert win.canvas.pixmap_item.isVisible() and not win._fondo_apagado and win._vista_fondo is None
    assert np.array_equal(_img(win), todos)
    assert win.pipes == antes["pipes"] and len(win._undo) == antes["undo"]
    assert win.canvas.tam_hoja() == pytest.approx(antes["tam"]) and win._dirty == antes["dirty"]
    # el panel: una fila por capa; clic en la fila = apagar
    win.btn_capas.abrir()
    panel = win.btn_capas.panel
    assert {(w.fila.tipo, w.fila.clave) for w in panel.filas} == {
        (CP.UTILIDAD, "AGUA"), (CP.UTILIDAD, "ALCANTARILLADO"), (CP.PLANO, 0), (CP.PLANO, 1)}
    panel.fila(CP.PLANO, 0).conmutar.emit()
    assert win._planos_encendidos() == [1] and not panel.fila(CP.PLANO, 0).fila.encendida
    panel.close()


def _hay_azul_en(win, x, y, r=3):
    """¿La escena pinta azul (línea de agua) junto a (x, y)? Sin el fondo."""
    win.canvas.ocultar_fondo(True)
    img = QtGui.QImage(2 * r + 1, 2 * r + 1, QtGui.QImage.Format_RGB888)
    img.fill(QtGui.QColor(255, 255, 255))
    p = QtGui.QPainter(img)
    win.canvas.scene().render(p, QtCore.QRectF(img.rect()), QtCore.QRectF(x - r, y - r, 2 * r + 1, 2 * r + 1))
    p.end()
    win.canvas.ocultar_fondo(win._fondo_apagado)
    return any(_azul(img.pixelColor(i, j).getRgb()) for i in range(img.width()) for j in range(img.height()))


def test_apagar_una_utilidad_no_se_pinta_ni_se_elige(win, pdfs, monkeypatch, app):
    from ui.comun import capas_popup as CP
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    a, b = win.pipes[0]["pts"][0], win.pipes[0]["pts"][1]
    medio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    win.structures.append({"x": a[0], "y": a[1], "cod": "BZ-X"})
    win.sel_pipe = -1
    win._redraw()
    assert win._pipe_at(*medio) == 0 and _hay_azul_en(win, *medio)
    antes = dict(pipes=[dict(p) for p in win.pipes], undo=len(win._undo), dirty=win._dirty)
    win._cambiar_capa(CP.UTILIDAD, "AGUA", False)
    assert win.capas_apagadas == {"AGUA"}
    assert win._pipe_at(*medio) == -1 and not _hay_azul_en(win, *medio)
    assert len(win.structures) - 1 in win._estructuras_ocultas
    assert win.btn_capas.text().startswith("Capas · 1")
    assert win.pipe_list.item(0).foreground().color() != win.pipe_list.item(1).foreground().color()
    # el modelo, el deshacer y «sin guardar» no cambian (es solo la vista)
    assert win.pipes == antes["pipes"] and len(win._undo) == antes["undo"] and win._dirty == antes["dirty"]
    win._cambiar_capa(CP.UTILIDAD, "AGUA", True)
    assert win._pipe_at(*medio) == 0 and _hay_azul_en(win, *medio) and not win._estructuras_ocultas
    win._solo_capa(CP.UTILIDAD, "ALCANTARILLADO")                  # «Ver solo esta»
    assert win.capas_apagadas == {"AGUA"}


def test_capas_y_planos_se_guardan_y_vuelven(win, pdfs, monkeypatch, app, tmp_path):
    from ui.comun import capas_popup as CP
    _original, puntos, _vio = _con_agua_y_cloaca(win, pdfs, monkeypatch)
    _planos(win, 1)
    solo = _img(win)
    win._cambiar_capa(CP.UTILIDAD, "AGUA", False)
    ruta = tmp_path / "dos planos.digproj"
    win._write_project(str(ruta))
    from ui.ventana import app_window
    w2 = app_window.Main()
    try:
        w2._open_project_path(str(ruta))
        app.processEvents()
        assert w2._vista_fondo == frozenset({1}) and w2._planos_encendidos() == [1]
        assert w2.capas_apagadas == {"AGUA"}
        assert np.array_equal(_img(w2), solo)
        assert w2._pagina_fondo() is None               # su PDF se arma aparte, sin esperar…
        assert _esperar(app, lambda: frozenset({1}) in w2._planos_docs)
        assert w2._pagina_fondo() is not None           # …y luego las teselas y el imán lo usan
        _planos(w2, 0, 1)                               # todos: de la hoja de trabajo
        img = _img(w2)
        assert _azul(_rgb(img, puntos["agua"])) and _rojo(_rgb(img, puntos["cloaca"]))
        _planos(w2)                                     # ninguno, guardado y reabierto
        w2._write_project(str(ruta))
    finally:
        w2._dirty = False
        w2.close()
        app.processEvents()
    w3 = app_window.Main()
    try:
        w3._open_project_path(str(ruta))
        app.processEvents()
        assert w3._fondo_apagado and not w3.canvas.pixmap_item.isVisible() and w3._planos_encendidos() == []
    finally:
        w3._dirty = False
        w3.close()
        app.processEvents()


def test_hoja_nueva_vuelve_a_todos(win, pdfs, monkeypatch, app):
    _con_agua_y_cloaca(win, pdfs, monkeypatch)
    _planos(win, 0)
    assert win._vista_fondo == frozenset({0}) and win._planos_docs
    rutas = [e[2] for e in win._planos_docs.values()]
    _planos(win)
    win._load_page(0)                                   # otra hoja en el editor
    assert win._vista_fondo is None and not win._planos_docs and not any(os.path.exists(r) for r in rutas)
    assert not win._fondo_apagado and win.canvas.pixmap_item.isVisible()


# ── agregar: siempre por «Componer hoja» ────────────────────────────────────
def test_agregar_pasa_por_componer_hoja(win, pdfs, monkeypatch, app):
    agua, cloaca = pdfs
    TA._editor_con_agua(win, agua)
    tubo = [TA._px(win, 0, *TA.TUBO["cloaca"][0]), TA._px(win, 0, *TA.TUBO["cloaca"][1])]
    TA._px_esperado[0] = tubo[0]
    TA._Reconocer.lineas = [tubo]
    TA._stubs(monkeypatch, win, cloaca, "import")
    from ui.ventana import app_window
    visto = {}

    def componer(parent, sources, comp, hidden, **kw):
        # el compositor recibe las hojas ubicadas ya marcadas; el usuario deja SOLO una
        visto["piezas"] = [(p.source, p.page) for p in comp.pieces]
        visto["sugerencia"] = kw.get("sugerencia")
        uno = C.Composite.from_dict(comp.to_dict())
        uno.pieces = [p for p in uno.pieces if p.page == 1]       # la 17-10 del alcantarillado
        return uno, sources, hidden
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", componer)
    win.capas_apagadas = {"ALCANTARILLADO"}                       # (apagada de antes: lo agregado se ve)
    win.agregar_utilidad()
    assert sorted(visto["piezas"]) == [(0, 0), (0, 1)] and visto["sugerencia"] is False
    assert [(p.source, p.page, p.grupo) for p in win.composite.pieces if p.grupo] == [(1, 1, 1)]
    assert [p["layer"] for p in win.pipes] == ["AGUA", "ALCANTARILLADO"]
    assert win._agregando is None and win._respaldo is None
    assert not win.capas_apagadas


def test_cancelar_componer_hoja_no_toca_el_editor(win, pdfs, monkeypatch, app):
    agua, cloaca = pdfs
    TA._editor_con_agua(win, agua)
    antes = (win.doc, win.composite.to_dict(), [dict(p) for p in win.pipes])
    TA._stubs(monkeypatch, win, cloaca, "import")
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", lambda *a, **k: None)
    win.agregar_utilidad()
    assert (win.doc, win.composite.to_dict(), win.pipes) == antes
    assert win._agregando is None and win._respaldo is None
