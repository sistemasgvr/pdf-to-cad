"""Panel derecho (pedido del usuario 2026-11-13, solo UX/UI):
- Con Asistente → Conflictos abierto el panel pedía ~856 px, no se podía achicar y se salía de la ventana; además ese
  mínimo quedaba PEGADO aunque se volviera a Chat o a Propiedades.
- Con nada seleccionado, Propiedades mostraba «Cambiar tipo», «Editar/mover», «Ver datos extendidos» y «Eliminar»."""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, RAIZ)

from PySide6 import QtCore, QtTest, QtWidgets  # noqa: E402

PROYECTO = os.path.join(os.path.dirname(__file__), "escenarios", "cruces", "escenarios_complejos.digproj")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pagina(minimo):
    w = QtWidgets.QWidget()
    w.setMinimumWidth(minimo)
    return w


def test_la_pila_pide_el_minimo_de_la_pagina_a_la_vista():
    _app()
    from ui.comun.pila_actual import PilaActual
    p = PilaActual()
    p.addWidget(_pagina(200))
    p.addWidget(_pagina(800))
    assert p.minimumSizeHint().width() == 200
    p.setCurrentIndex(1)
    assert p.minimumSizeHint().width() == 800
    p.setCurrentIndex(0)
    assert p.minimumSizeHint().width() == 200          # QStackedWidget daría 800 (la página oculta)


def test_el_panel_lateral_suelta_el_minimo_al_cambiar_de_pagina():
    _app()
    from ui.comun.pila_actual import MINIMO_BASE, PilaActual
    win = QtWidgets.QMainWindow()
    win.setCentralWidget(QtWidgets.QWidget())
    dock = QtWidgets.QDockWidget()
    dock.setMinimumWidth(300)
    dock.setProperty(MINIMO_BASE, 300)
    pila = PilaActual()
    pila.addWidget(_pagina(200))
    pila.addWidget(_pagina(800))
    dock.setWidget(pila)
    win.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    win.resize(1600, 800)
    win.show()
    QtTest.QTest.qWait(50)
    pila.setCurrentIndex(1)
    QtTest.QTest.qWait(50)
    assert dock.minimumWidth() >= 800
    pila.setCurrentIndex(0)
    QtTest.QTest.qWait(50)
    win.resizeDocks([dock], [320], QtCore.Qt.Horizontal)
    QtTest.QTest.qWait(50)
    assert dock.minimumWidth() == 300 and dock.width() <= 330   # antes quedaba en 800
    win.close()


def test_fila_apilable_pasa_a_columna_y_no_impide_achicar():
    _app()
    from ui.comun.responsive import FilaApilable
    fila = FilaApilable(8)
    for ancho in (140, 110, 260):
        b = QtWidgets.QPushButton("x")
        b.setMinimumWidth(ancho)
        fila.lay.addWidget(b)
    assert fila.minimumSizeHint().width() == 260        # el más ancho, no la suma (526)
    caja = QtWidgets.QWidget()                          # dentro de un panel, como en la app
    QtWidgets.QVBoxLayout(caja).addWidget(fila)
    caja.resize(600, 200)
    caja.show()
    QtTest.QTest.qWait(30)
    assert fila.lay.direction() == QtWidgets.QBoxLayout.LeftToRight
    caja.resize(300, 300)
    QtTest.QTest.qWait(30)
    assert caja.width() == 300 and fila.lay.direction() == QtWidgets.QBoxLayout.TopToBottom
    caja.close()


def _ventana():
    _app()
    from ui.comun import theme
    theme.apply_theme(QtWidgets.QApplication.instance(), "light")
    from ui.ventana import app_window
    win = app_window.Main()
    win.resize(1600, 860)
    win.show()
    win._open_project_path(PROYECTO)
    QtTest.QTest.qWait(1500)
    return win


def _cortados(raiz):
    """Hijos visibles que se salen por la derecha de `raiz` (contenido cortado)."""
    malos = []
    for w in raiz.findChildren(QtWidgets.QWidget):
        if not w.isVisibleTo(raiz) or w.width() <= 1:
            continue
        der = w.mapTo(raiz, QtCore.QPoint(w.width(), 0)).x()
        if der > raiz.width() + 1:
            malos.append((type(w).__name__, w.objectName(), der, raiz.width()))
    return malos


@pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")
def test_conflictos_se_achica_sin_cortar_y_no_deja_el_panel_trabado():
    win = _ventana()
    try:
        win.mostrar_asistente(True, "conflictos")
        QtTest.QTest.qWait(800)
        dlg = win._dlg_soluciones
        assert dlg.lista.count() > 0
        assert dlg.lista.currentItem() is not None       # el panel elige solo el primero (sin la fila de título)
        QtTest.QTest.qWait(500)
        for ancho in (900, 520, 300):
            win.resizeDocks([win._rdock], [ancho], QtCore.Qt.Horizontal)
            QtTest.QTest.qWait(300)
            # el panel baja hasta el mínimo de lo que MUESTRA (ni más: no queda pegado uno de antes)
            minimo = max(300, win.pila_derecha.minimumSizeHint().width(),
                         win.panel_der.dock_header.minimumSizeHint().width())   # la cabecera con su selector
            assert win._rdock.minimumWidth() <= minimo + 2, (ancho, win._rdock.minimumWidth(), minimo)
            if ancho < 900:                                  # resizeDocks no es exacto con lugar de sobra
                assert win._rdock.width() <= max(ancho, minimo) + 20, (ancho, win._rdock.width(), minimo)
            assert not _cortados(dlg), _cortados(dlg)
        # una columna pide mucho menos que dos (lista + ficha)
        assert dlg.minimumSizeHint().width() < dlg.izq.minimumSizeHint().width() + dlg._der_scroll.minimumSizeHint().width()
        assert dlg.div.orientation() == QtCore.Qt.Vertical          # angosto: lista arriba, ficha abajo
        win.mostrar_asistente(True, "chat")
        QtTest.QTest.qWait(300)
        win.mostrar_asistente(False)                                 # Propiedades
        QtTest.QTest.qWait(300)
        win.resizeDocks([win._rdock], [300], QtCore.Qt.Horizontal)
        QtTest.QTest.qWait(300)
        minimo = max(300, win.pila_derecha.minimumSizeHint().width(),
                         win.panel_der.dock_header.minimumSizeHint().width())   # la cabecera con su selector
        assert win._rdock.minimumWidth() <= minimo + 2                # el mínimo de Conflictos ya no queda pegado
        assert win._rdock.width() <= minimo + 20
    finally:
        win.close()


@pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")
def test_propiedades_sin_nada_elegido_muestra_el_estado_vacio():
    from nucleo.model import TAB_PIPE
    win = _ventana()
    try:
        win.mostrar_asistente(False)
        win._show_tab(TAB_PIPE)
        win.pipe_list.setCurrentRow(-1)
        win.pipe_list.clearSelection()
        win._update_ui()
        QtTest.QTest.qWait(100)
        botones = (win.btn_ct, win.btn_mv, win.btn_xd, win.btn_del)
        assert not win.vacio_propiedades.isHidden()
        assert all(b.isHidden() for b in botones)
        win.pipe_list.setCurrentRow(0)                               # algo elegido: sus propiedades de siempre
        QtTest.QTest.qWait(100)
        assert win.vacio_propiedades.isHidden()
        assert not win.gprop.isHidden()
    finally:
        win.close()


@pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")
def test_sin_nada_elegido_no_quedan_las_cotas_por_tramo_de_la_anterior():
    """Reporte 2026-11-14: tras elegir una utilidad y soltarla, «Cotas por tramo» seguía con sus tramos."""
    from nucleo.model import TAB_PIPE
    win = _ventana()
    try:
        win.mostrar_asistente(False)
        win._show_tab(TAB_PIPE)
        i = next(k for k, p in enumerate(win.pipes) if len(p.get("pts") or []) >= 3 and not p.get("world"))
        win.pipe_list.setCurrentRow(i)
        QtTest.QTest.qWait(100)
        assert not win.gprop_segs.isHidden()                         # con una utilidad elegida, sus tramos
        win.pipe_list.setCurrentRow(-1)
        win.pipe_list.clearSelection()
        win.sel_pipe = -1
        win._update_ui()
        QtTest.QTest.qWait(100)
        assert not win.vacio_propiedades.isHidden()
        assert win.gprop_segs.isHidden()
        win.pipe_list.setCurrentRow(i)                               # elegida otra vez: vuelven
        QtTest.QTest.qWait(100)
        assert not win.gprop_segs.isHidden()
    finally:
        win._dirty = False
        win.close()


@pytest.mark.skipif(not os.path.isfile(PROYECTO), reason="falta el proyecto de escenarios")
def test_propiedades_y_asistente_se_cambian_con_un_clic_y_siguen_la_seleccion():
    """Pedido 2026-11-14: con el Asistente abierto, ir a Propiedades tiene que ser fácil (segmentado en la cabecera) y
    elegir algo el USUARIO (clic o teclado) muestra sus propiedades; un enlace del chat no saca de la conversación."""
    win = _ventana()
    try:
        segs = win._modos_der
        assert len(segs) == 2                                         # cabecera fija y la del panel que se oculta
        win.mostrar_asistente(True, "chat")
        assert all(s.botones[1].isChecked() for s in segs)            # el modo a la vista, marcado
        segs[0].botones[0].click()                                    # un clic en «Propiedades»
        assert win.pila_derecha.currentIndex() == 0 and all(s.botones[0].isChecked() for s in segs)
        segs[0].botones[1].click()                                    # y de vuelta al Asistente
        assert win.pila_derecha.currentIndex() == 1
        # elegir con el teclado en la lista de utilidades → Propiedades
        win._show_tab(0)
        win.pipe_list.setCurrentRow(1)
        win.mostrar_asistente(True, "chat")
        win.pipe_list.setFocus()
        QtTest.QTest.keyClick(win.pipe_list, QtCore.Qt.Key_Down)
        assert win.pila_derecha.currentIndex() == 0
        # un enlace del chat (AGUA-n) elige la utilidad pero deja el Asistente abierto
        win.mostrar_asistente(True, "chat")
        win._ia_chat.enfocar() if hasattr(win._ia_chat, "enfocar") else None
        p = win.pipes[2]
        codigo = f"{(p.get('layer') or '').strip()}-3"
        assert win._ia_ir_a(codigo)
        assert win.pila_derecha.currentIndex() == 1
    finally:
        win._dirty = False
        win.close()


def test_selector_del_panel_no_impone_un_ancho_grande():
    """Los botones «seg» del tema son anchos (~150–180 px con la fuente de Windows a 1×): en la cabecera cada uno baja
    hasta lo que mide su texto, así la cabecera no hace al panel más ancho que su contenido (300 px)."""
    _app()
    from ui.ventana import ventana_panel_der_modos as M
    seg = M._segmentado(type("W", (), {"mostrar_asistente": lambda *_a: None})())
    for b in seg.botones:                                              # su texto + relleno: ni cortado ni de más
        assert b.minimumSizeHint().width() == b.fontMetrics().horizontalAdvance(b.text()) + 24
    assert seg.minimumSizeHint().width() <= sum(b.minimumSizeHint().width() for b in seg.botones) + 12
