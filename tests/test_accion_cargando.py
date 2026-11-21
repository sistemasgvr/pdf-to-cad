"""Aro de «cargando» en el control pulsado (2026-11-21): se ve mientras lo que el clic lanzó sigue en marcha."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtCore, QtTest, QtWidgets

from nucleo import actividad
from ui.comun import accion_cargando as AC


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def filtro(qapp):
    f = AC.AccionCargando(qapp)
    yield f
    qapp.removeEventFilter(f)
    f._dejar()


def _boton(parent=None, texto="Importar"):
    b = QtWidgets.QPushButton(texto, parent)
    b.resize(120, 32)
    b.show()
    return b


def _bombear(ms=40):
    QtTest.QTest.qWait(ms)


def _aros(b):
    return [a for a in b.findChildren(AC._Aro) if a.isVisible()]


def test_un_clic_instantaneo_no_deja_aro(filtro):
    b = _boton()
    b.clicked.connect(lambda: None)
    QtTest.QTest.mouseClick(b, QtCore.Qt.LeftButton)
    _bombear()
    assert not _aros(b) and not filtro._marcas


def test_el_aro_dura_lo_que_dura_el_trabajo_que_lanzo_el_clic(filtro):
    b = _boton()
    ficha = {}
    b.clicked.connect(lambda: ficha.setdefault("f", actividad.iniciar("trabajo de prueba")))
    QtTest.QTest.mouseClick(b, QtCore.Qt.LeftButton)
    _bombear()
    assert _aros(b)                                   # sigue en marcha → el aro gira
    actividad.terminar(ficha["f"])
    _bombear(AC.GRACIA_MS + 200)
    assert not _aros(b) and not filtro._marcas        # terminó → se va (tras la gracia)


def test_un_paso_que_acaba_y_lanza_otro_no_parpadea(filtro):
    b = _boton()
    ficha = {}
    b.clicked.connect(lambda: ficha.setdefault("f", actividad.iniciar("paso 1")))
    QtTest.QTest.mouseClick(b, QtCore.Qt.LeftButton)
    _bombear()
    actividad.terminar(ficha["f"])
    _bombear(100)                                     # dentro de la gracia
    assert _aros(b)
    f2 = actividad.iniciar("paso 2")                  # el siguiente paso, lanzado por el primero
    _bombear(AC.GRACIA_MS + 200)
    assert _aros(b)                                   # sigue girando por el paso 2
    actividad.terminar(f2)
    _bombear(AC.GRACIA_MS + 200)
    assert not _aros(b)


def test_casillas_selectores_y_botones_de_menu_no_llevan_aro(filtro):
    c = QtWidgets.QCheckBox("x"); c.show()
    t = QtWidgets.QPushButton("t"); t.setCheckable(True); t.show()
    menu = QtWidgets.QMenu(); m = QtWidgets.QToolButton(); m.setMenu(menu); m.setPopupMode(QtWidgets.QToolButton.InstantPopup); m.show()
    sin = _boton(); sin.setProperty(AC.SIN_ARO, True)
    apagado = _boton(); apagado.setEnabled(False)
    assert not any(AC.marcable(w) for w in (c, t, m, sin, apagado))
    t.setProperty(AC.CON_ARO, True)
    assert AC.marcable(t) and AC.marcable(_boton())


def test_la_capa_cargando_anota_su_actividad(qapp):
    from ui.comun import busy
    host = QtWidgets.QWidget(); host.resize(300, 200); host.show()
    antes = len(actividad.vivas())
    with busy.busy(host, "Probando"):
        assert len(actividad.vivas()) == antes + 1
    assert len(actividad.vivas()) == antes


def test_continuar_espera_mientras_se_arma_la_hoja_compuesta():
    """2026-11-21: «Continuar» estaba activo con la composición a medias (búsqueda del PDF agregado en marcha)."""
    from hoja import composite_checks as CK
    assert CK.ready(CK.checks(2))
    ocupado = CK.checks(2, ocupado=True)
    assert [c.code for c in ocupado] == ["busy"] and not CK.ready(ocupado)


def test_indicador_de_la_barra_gira_con_cualquier_trabajo_y_se_apaga(qapp):
    """Acciones por menú, atajo o paleta (sin botón): un aro en la barra superior mientras haya trabajo."""
    from ui.comun import indicador_actividad as IA
    w = IA.IndicadorActividad()
    w.show()
    ficha = actividad.iniciar("trabajo sin botón")
    _bombear(IA.RETRASO_MS + 150)
    assert w.activo() and "trabajo sin botón" in w.toolTip()
    actividad.terminar(ficha)
    _bombear(IA.GRACIA_MS + 150)
    assert not w.activo()
    f2 = actividad.iniciar("instantáneo")                 # lo que dura menos que el retraso no se ve
    actividad.terminar(f2)
    _bombear(IA.RETRASO_MS + 100)
    assert not w.activo()
    w._dejar()


def test_un_boton_que_qt_ya_borro_no_rompe_la_accion(filtro):
    """Reporte 2026-11-21: «Acción interrumpida · RuntimeError: Internal C++ object (_Aro) already deleted»."""
    import shiboken6
    b = _boton()
    ficha = {}
    b.clicked.connect(lambda: ficha.setdefault("f", actividad.iniciar("trabajo largo")))
    QtTest.QTest.mouseClick(b, QtCore.Qt.LeftButton)
    _bombear()
    assert _aros(b)
    shiboken6.delete(b)                               # el botón (y su aro) desaparecen con trabajo en marcha
    _bombear(60)
    actividad.terminar(ficha["f"])                    # …y el trabajo termina después: nada debe fallar
    _bombear(AC.GRACIA_MS + 200)
    assert not filtro._marcas


def test_el_aro_borrado_solo_se_olvida(filtro):
    import shiboken6
    b = _boton()
    marca = AC._Marca(b)
    marca.mostrar(repintar=True)
    shiboken6.delete(marca.aro)
    marca.mostrar(repintar=True)                      # rehace el aro en vez de usar el borrado
    assert marca.aro_vivo() is not None
    marca.quitar()
    assert marca.aro is None
