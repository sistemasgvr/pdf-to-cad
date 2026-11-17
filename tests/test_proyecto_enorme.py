"""Proyecto enorme (pedido del usuario 2026-11-14: 29 000 utilidades, ~88 000 marcas; navegar, abrir y cada acción
eran lentos): resumen por zona de las marcas con la vista alejada, listas del Inventario llenadas de una vez, líneas
juntadas por pluma al pintar e índices de vértices que duran mientras el modelo no cambia. Todo con el MISMO resultado."""
import os
import sys

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, RAIZ)

from PySide6 import QtCore, QtGui, QtTest, QtWidgets  # noqa: E402

PROYECTO = os.path.join(os.path.dirname(__file__), "escenarios", "cruces", "escenarios_complejos.digproj")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


# ───────────────────────── resumen por zona ─────────────────────────

def test_zonas_cuentan_por_clase_y_toman_el_color_de_lo_mas_grave():
    from ui.comun import capa_marcas_resumen as R
    xs = np.array([10.0, 20.0, 30.0, 500.0])
    ys = np.array([10.0, 15.0, 20.0, 500.0])
    clases = np.array([R.ACCESORIO, R.AVISO, R.CONFLICTO, R.AVISO])
    pesos = np.array([1, 3, 2, 1])                                   # una insignia con 3 avisos, «C-1 · C-2»
    z = R.Zonas(xs, ys, clases, 100.0, pesos)
    assert z.n == 2
    k = int(np.argmax(z.total))
    assert int(z.total[k]) == 6 and int(z.grave[k]) == R.CONFLICTO
    assert z.por_clase[k, R.AVISO] == 3 and z.por_clase[k, R.CONFLICTO] == 2 and z.por_clase[k, R.ACCESORIO] == 1
    assert 0 <= z.x[k] <= 100 and 0 <= z.y[k] <= 100               # dentro de su zona
    texto = z.texto(k)
    assert texto.index("2 conflicto") < texto.index("3 aviso") < texto.index("1 accesorio")
    assert R.Zonas(np.zeros(0), np.zeros(0), np.zeros(0, dtype=int), 50.0).n == 0


@pytest.fixture
def win():
    _app()
    from ui.ventana import app_window
    w = app_window.Main()
    w.resize(1400, 860)
    w.show()
    w._open_project_path(PROYECTO)
    QtTest.QTest.qWait(1500)
    yield w
    w._dirty = False
    w.close()


@pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")
def test_de_lejos_un_globo_por_zona_y_de_cerca_las_marcas_de_siempre(win, monkeypatch):
    from ui.comun import capa_marcas_resumen as R
    g = win._marcas
    vp = win.canvas.viewport()
    todas = sum(len(c.marcas) for c in g.capas.values())
    assert todas > 10 and not win._marcas_resumidas()                # pocas marcas: como siempre

    def foto():
        img = QtGui.QImage(vp.size(), QtGui.QImage.Format_RGB32)
        vp.render(img)
        return img
    antes = foto()
    monkeypatch.setattr(R, "UMBRAL", 5)                              # «demasiadas» a la vista
    g._res_estado = None
    assert win._marcas_resumidas()
    escala = abs(win.canvas.transform().m11())
    z = g.zonas(escala)
    assert z.n >= 1 and int(z.total.sum()) >= len(win._conflictos)   # cada conflicto y observación cuenta
    assert int(z.por_clase[:, R.CONFLICTO].sum() + z.por_clase[:, R.OBSERVACION].sum()) == len(win._conflictos)
    resumida = foto()
    assert resumida != antes                                         # se pinta otra cosa: los globos
    k = int(np.argmax(z.total))
    p = QtCore.QPointF(float(z.x[k]), float(z.y[k]))
    assert g.zona_en(p, vp) is not None and "Clic" in g.tooltip_en(p, vp)
    # otra vista de la MISMA escena (capturas del informe) nunca se resume
    otra = QtWidgets.QGraphicsView(win.canvas.scene())
    otra.resize(400, 300)
    assert not g.en_resumen(otra.viewport())
    # las marcas que no se ven no se eligen a ciegas; el clic en un globo acerca la vista
    eligio = []
    monkeypatch.setattr(win, "_elegir_accesorio_en", lambda x, y: eligio.append(1) or True)
    monkeypatch.setattr(win, "_try_click_conflict", lambda x, y: eligio.append(2) or True)
    m0 = win.canvas.transform().m11()
    win.on_click(p.x(), p.y(), QtCore.Qt.LeftButton)
    assert not eligio and win.canvas.transform().m11() > m0 * 1.5
    # sin resumen (de cerca): exactamente el dibujo de siempre
    monkeypatch.setattr(R, "UMBRAL", 10 ** 9)
    g._res_estado = None
    win.canvas.setTransform(QtGui.QTransform.fromScale(m0, m0))
    assert not win._marcas_resumidas()
    win.on_click(p.x(), p.y(), QtCore.Qt.LeftButton)
    assert eligio                                                    # de cerca, las marcas se eligen como siempre


# ───────────────────────── listas del Inventario ─────────────────────────

def test_filas_de_una_vez_igual_que_una_por_una_y_globo_al_pedirlo():
    _app()
    from ui.comun import ui_common as U
    a, b = QtWidgets.QListWidget(), QtWidgets.QListWidget()
    ic = U.swatch_icon(QtGui.QColor("#3366ff"))
    textos = [f"{i}. fila" for i in range(500)]
    iconos = [ic if i % 3 else None for i in range(500)]
    for t, i in zip(textos, iconos):
        U.fila_lista(a, t, i)
    assert U.filas_lista(b, textos, iconos) == 0
    assert [b.item(k).text() for k in range(b.count())] == [a.item(k).text() for k in range(a.count())]
    assert [b.item(k).icon().isNull() for k in range(500)] == [a.item(k).icon().isNull() for k in range(500)]
    assert b._pdfcad_limpia and U.filas_lista(b, ["otra"]) == 500
    # el globo = el texto de la fila, calculado al pedirlo; una fila con globo propio lo conserva
    U.GloboDeFila(b)
    b.item(1).setToolTip("propio")
    assert b.item(0).toolTip() == "" and b.item(1).toolTip() == "propio"


@pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")
def test_inventario_buscar_y_apagar_capas_siguen_funcionando_con_las_listas_de_una_vez(win):
    lista = win.pipe_list
    assert lista.count() == len(win.pipes) and lista.item(0).text().startswith("1. ")
    assert not any(lista.item(k).isHidden() for k in range(lista.count()))
    win.buscar_inventario.setText(lista.item(0).text()[:6])
    win._filtrar_inventario()
    ocultas = [lista.item(k).isHidden() for k in range(lista.count())]
    assert not ocultas[0] and any(ocultas)
    win.buscar_inventario.setText("")
    win._filtrar_inventario()
    assert not any(lista.item(k).isHidden() for k in range(lista.count()))   # vuelven todas
    capa = win.pipes[0]["layer"]
    win.capas_apagadas = {capa}
    win._atenuar_lista_utilidades()
    tenue = lista.item(0).foreground()
    win.capas_apagadas = set()
    win._atenuar_lista_utilidades()
    assert lista.item(0).foreground() != tenue                       # y deja de estar en gris
    # buzones y curvas: mismas filas que estructuras a la vista
    assert win.bz_list.count() == len(win._bz_rows) and win.curve_list.count() == len(win._curve_rows)


# ───────────────────────── líneas juntadas por pluma ─────────────────────────

def test_lineas_juntadas_por_pluma_se_ven_igual(monkeypatch):
    _app()
    from ui.comun import capa_lineas as CL
    rnd = np.random.default_rng(5)

    def escena():
        sc = QtWidgets.QGraphicsScene()
        capa = CL.CapaLineas(1.0)
        plumas = [QtGui.QPen(QtGui.QColor(c), 2.0) for c in ("#2563eb", "#16a34a", "#dc2626")]
        for p in plumas:
            p.setCosmetic(True)
        r = np.random.default_rng(5)
        for k in range(600):
            pts = (r.random((3, 2)) * 400).tolist()
            lineas, caja = CL.lineas_de(pts)
            capa.agregar(lineas, caja, plumas[(k // 40) % 3], k)   # corridas de 40 con la misma pluma
        capa.cerrar()
        sc.addItem(capa)
        return sc, capa

    def foto(sc):
        img = QtGui.QImage(420, 420, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor("white"))
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        sc.render(p, QtCore.QRectF(0, 0, 420, 420), QtCore.QRectF(-10, -10, 420, 420))
        p.end()
        return img
    assert rnd is not None
    monkeypatch.setattr(CL, "CORRIDAS_MIN", 10 ** 9)                 # una por una, como antes
    sc, _capa = escena()
    una = foto(sc)
    monkeypatch.setattr(CL, "CORRIDAS_MIN", 10)                      # juntadas por pluma
    sc2, capa2 = escena()
    assert foto(sc2) == una
    assert capa2._corridas is not None and len(capa2._corridas) == 15   # 600 / 40
    capa2.cambiar_pluma(7, QtGui.QPen(QtGui.QColor("#facc15"), 4.0))
    assert capa2._corridas is None                                   # otra pluma: se rehacen


# ───────────────────────── índices que duran mientras el modelo no cambia ─────────────────────────

def test_memoria_de_indices_solo_mientras_no_cambia_el_modelo():
    from nucleo import model_ops as M
    pipes = [dict(layer="ALCANTARILLADO", pts=[(float(k), 0.0), (float(k) + 5, 30.0)]) for k in range(0, 400, 10)]
    pipes += [dict(layer="ALCANTARILLADO", pts=[(1000.0, 0.0), (1010.0, 0.0)]) for _ in range(40)]
    memoria = {}
    with M.indice_vertices(memoria):
        a = M.pipe_at_vertex(pipes, 15.0, 30.0)
    guardado = dict(memoria)
    with M.indice_vertices(memoria):                                 # el mismo índice, sin rearmarlo
        assert M.pipe_at_vertex(pipes, 15.0, 30.0) is a
    assert all(memoria[k] is v for k, v in guardado.items())
    with M.indice_vertices():                                        # sin memoria: como siempre
        assert M.pipe_at_vertex(pipes, 15.0, 30.0) is a
