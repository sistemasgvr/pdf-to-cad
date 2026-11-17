"""Pedido 2026-11-13: todo clic en un conflicto lleva a su lugar en el lienzo (chat de la IA, Resolver conflictos,
Tabla de datos…) y el círculo amarillo que lo marca parpadea 10 s (antes 5)."""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, RAIZ)

from PySide6 import QtCore, QtTest, QtWidgets  # noqa: E402

PROYECTO = os.path.join(os.path.dirname(__file__), "escenarios", "cruces", "escenarios_complejos.digproj")
pytestmark = pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")


@pytest.fixture
def win():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana import app_window
    w = app_window.Main()
    w.resize(1400, 860)
    w.show()
    w._open_project_path(PROYECTO)
    QtTest.QTest.qWait(1500)
    assert w._conflictos, "el proyecto de escenarios debe tener conflictos"
    yield w
    w._dirty = False                                   # sin la pregunta modal «¿Guardar cambios?» al cerrar
    w.close()


def _centro_cerca(w, x, y):
    """El punto queda a la vista (cerca del borde de la hoja el lienzo no puede ponerlo justo al centro)."""
    p = w.canvas.mapFromScene(QtCore.QPointF(x, y))
    return w.canvas.viewport().rect().adjusted(20, 20, -20, -20).contains(p)


def _lejos(w, c):
    """Acerca y se va a la esquina opuesta de la hoja: el conflicto queda fuera de la vista."""
    w.canvas.resetTransform()
    w.canvas.scale(8, 8)
    r = w.canvas.sceneRect()
    w.canvas.centerOn(r.right() if c.x < r.center().x() else r.left(),
                      r.bottom() if c.y < r.center().y() else r.top())
    w._quitar_marca_lugar()
    assert not _centro_cerca(w, c.x, c.y), "la prueba necesita empezar con el conflicto fuera de la vista"


def test_el_circulo_dura_10_segundos():
    from ui.ventana.ventana_herramientas import HerramientasMixin
    assert HerramientasMixin.MARCA_LUGAR_MS == 10000


def test_un_conflicto_del_chat_lleva_al_lienzo_aunque_la_ia_no_haya_leido_el_proyecto(win):
    c = win._conflictos[0]
    win._ia_cache_datos = None                         # la IA todavía no armó sus datos
    _lejos(win, c)
    assert win._ia_ir_a(c.id.lower())                  # «c-1» también
    assert _centro_cerca(win, c.x, c.y)
    assert win._marca_lugar is not None
    from ui.dialogos import ia_chat_html as H          # y en la respuesta queda como ficha enlazada
    from ui.comun import theme
    html = H.formato(f"Revisa {c.id} primero.", lambda k: win._ia_conflicto(k) is not None, theme.tokens())
    assert f"href='ref:{c.id}'" in html


def test_clic_en_el_conflicto_ya_elegido_de_resolver_lleva_al_lienzo(win):
    win.mostrar_asistente(True, "conflictos")
    QtTest.QTest.qWait(500)
    dlg = win._dlg_soluciones
    it = dlg.lista.currentItem()                       # el panel ya eligió la primera (no la fila de título)
    QtTest.QTest.qWait(300)
    c = dlg._actual[0]
    _lejos(win, c)
    dlg._clic_en_lista(it)                             # la fila que ya estaba elegida (antes no hacía nada)
    assert _centro_cerca(win, c.x, c.y)
    assert win._marca_lugar is not None


def test_ir_al_lugar_desde_la_tabla_o_normativas_muestra_el_lienzo(win):
    c = win._conflictos[0]
    otra = QtWidgets.QWidget()                         # como la Tabla de datos incrustada en el centro
    win.centro.addWidget(otra)
    win.centro.setCurrentWidget(otra)
    _lejos(win, c)
    win._ir_a_elemento(c.x, c.y)
    assert win.centro.currentWidget() is win.canvas    # antes el plano se movía detrás de la tabla
    assert _centro_cerca(win, c.x, c.y)


CON_OBSERVACIONES = os.path.join(os.path.dirname(__file__), "escenarios", "cruces", "escenarios_prueba.digproj")


@pytest.mark.skipif(not os.path.isfile(CON_OBSERVACIONES), reason="falta el proyecto de escenarios")
def test_resolver_separa_conflictos_y_observaciones(win):
    """Terminología 2026-11-13: el panel Resolver lista dos secciones con su título (que no se elige)."""
    from ui.dialogos.ia_soluciones import _CABECERA, _ROL
    win._dirty = False
    win._open_project_path(CON_OBSERVACIONES)
    QtTest.QTest.qWait(1500)
    assert any(c.es_conflicto for c in win._conflictos) and any(not c.es_conflicto for c in win._conflictos)
    win.mostrar_asistente(True, "conflictos")
    QtTest.QTest.qWait(500)
    dlg = win._dlg_soluciones
    filas = [dlg.lista.item(k) for k in range(dlg.lista.count())]
    cabeceras = [k for k, it in enumerate(filas) if it.data(_CABECERA)]
    assert len(cabeceras) == 2 and cabeceras[0] == 0
    assert filas[0].text().startswith("CONFLICTOS") and filas[cabeceras[1]].text().startswith("OBSERVACIONES")
    assert not filas[0].flags() & QtCore.Qt.ItemIsSelectable
    ids1 = [it.data(_ROL) for it in filas[1:cabeceras[1]]]
    ids2 = [it.data(_ROL) for it in filas[cabeceras[1] + 1:]]
    assert ids1 and all(i.startswith("C-") for i in ids1)
    assert ids2 and all(i.split("-")[0] in ("OC", "OU", "OG", "OV") for i in ids2)
    assert dlg.lista.currentItem() is filas[1]                # elige el primer conflicto, no el título
    o = next(c for c in win._conflictos if not c.es_conflicto)
    _lejos(win, o)
    assert win._ia_ir_a(o.id.lower())                        # el chat también lleva a una O-n
    assert _centro_cerca(win, o.x, o.y)


def _pies_a_la_vista(w):
    """Pies que muestra el lado corto del lienzo."""
    vp = w.canvas.viewport().rect()
    ft_px = w.scale / w.zoom
    return min(vp.width(), vp.height()) / abs(w.canvas.transform().m11()) * ft_px


def test_ir_a_un_conflicto_acerca_la_vista_hasta_verlo_de_cerca(win):
    """Pedido 2026-11-14: además de llevar al lugar, acercarse lo suficiente para verlo casi en detalle (~40 ft en el
    lado corto). Nunca aleja si ya se estaba más cerca, y lo que no es un conflicto no cambia el zoom."""
    c = win._conflictos[0]
    win.canvas.resetTransform()
    win.canvas._zoom_level = 1.0                              # la hoja entera, de lejos
    win.canvas.fitInView(win.canvas.pixmap_item, QtCore.Qt.KeepAspectRatio)
    lejos = _pies_a_la_vista(win)
    assert lejos > 3 * win.ACERCAR_CONFLICTO_FT
    win._ia_ir_a(c.id)                                       # desde el chat (o Resolver, Revisión, Tabla…)
    assert _pies_a_la_vista(win) == pytest.approx(win.ACERCAR_CONFLICTO_FT, rel=0.05)
    assert _centro_cerca(win, c.x, c.y)
    win.canvas.apply_zoom(4.0)                               # más cerca todavía: ir de nuevo no aleja
    cerca = _pies_a_la_vista(win)
    win._ir_a_elemento(c.x, c.y, activar=False)
    assert _pies_a_la_vista(win) == pytest.approx(cerca, rel=1e-6)
    win.canvas.apply_zoom(0.25)
    antes = _pies_a_la_vista(win)
    win._ir_a_elemento(c.x + 37.3, c.y + 41.9, activar=False)   # un lugar que no es conflicto: solo centra
    assert _pies_a_la_vista(win) == pytest.approx(antes, rel=1e-6)
