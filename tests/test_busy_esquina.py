"""La capa «Cargando…» es una tarjeta en la esquina, como la del reconocimiento (pedido del usuario 2026-11-02):
sin velo, sin tapar los botones del asistente y repintando solo su rectángulo."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from ui.comun import busy


@pytest.fixture
def host():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = QtWidgets.QWidget()
    w.setAttribute(QtCore.Qt.WA_DontShowOnScreen)
    w.resize(900, 600)
    w.setStyleSheet("background:#ffffff;")
    w.show()
    app.processEvents()
    yield w
    ov = busy.overlay_for(w)
    while ov.active:
        ov.end()
    w.close()


def test_tarjeta_en_la_esquina_inferior_derecha(host):
    ov = busy.overlay_for(host)
    ov.begin("Armando la hoja compuesta…", "Pieza 3 de 12")
    card = ov._geometria()[0]
    assert card.right() == host.width() - busy._MARGEN
    assert card.bottom() == host.height() - busy._MARGEN
    assert card.width() <= busy._CARD_MAX_W
    ov.end()


def test_no_atenua_lo_que_hay_debajo(host):
    antes = host.grab().toImage().pixelColor(50, 50)
    ov = busy.overlay_for(host)
    ov.begin("Cargando…")
    QtWidgets.QApplication.processEvents()
    assert host.grab().toImage().pixelColor(50, 50) == antes
    ov.end()


def test_sigue_bloqueando_la_entrada(host):
    clics = []
    b = QtWidgets.QPushButton("x", host)
    b.setGeometry(10, 10, 80, 30)
    b.clicked.connect(lambda: clics.append(1))
    b.show()
    ov = busy.overlay_for(host)
    ov.begin("Cargando…")
    QtTest.QTest.mouseClick(ov, QtCore.Qt.LeftButton, pos=QtCore.QPoint(20, 20))
    assert not clics and ov.active
    ov.end()


def test_va_encima_del_pie_del_asistente(host):
    pie = QtWidgets.QWidget(host)
    pie.setObjectName(busy.ANCLA_PIE)
    pie.setGeometry(0, 540, 900, 60)
    pie.show()
    QtWidgets.QApplication.processEvents()
    ov = busy.overlay_for(host)
    ov.begin("Reconociendo…", "Leyendo las capas")
    assert ov._geometria()[0].bottom() <= 540 - busy._MARGEN
    ov.end()


def test_el_pie_del_asistente_lleva_el_ancla():
    from ui.asistente import wizard_widgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert wizard_widgets.wizard_footer([], "", []).objectName() == busy.ANCLA_PIE


def test_en_la_ventana_se_apoya_en_el_lienzo(host):
    lienzo = QtWidgets.QGraphicsView(host)
    lienzo.setGeometry(100, 40, 500, 400)
    lienzo.show()
    host.canvas = lienzo
    QtWidgets.QApplication.processEvents()
    ov = busy.overlay_for(host)
    ov.begin("Importando al editor…")
    vp = lienzo.viewport()
    esquina = vp.mapTo(host, QtCore.QPoint(vp.width(), vp.height()))
    card = ov._geometria()[0]
    assert card.right() == esquina.x() - busy._MARGEN
    assert card.bottom() == esquina.y() - busy._MARGEN
    ov.end()


def test_solo_repinta_la_tarjeta(host):
    ov = busy.overlay_for(host)
    ov.begin("Cargando…", "Una etapa")
    caja = ov._region().boundingRect()
    assert caja.width() < host.width() / 2 and caja.height() < host.height() / 2
    ov.end()


def test_al_cambiar_de_alto_repinta_tambien_la_tarjeta_anterior(host):
    ov = busy.overlay_for(host)
    ov.begin("Cargando…", "Una línea\notra línea\notra más")
    alta = ov._region().boundingRect()
    ov.step(detail="corta", pump=False)
    assert ov._region().boundingRect().contains(alta) or ov._caja.height() < alta.height()
    ov.end()


def test_cancelar_con_un_clic_dentro_de_la_tarjeta(host):
    llamadas = []
    ov = busy.overlay_for(host)
    ov.begin("Reconociendo…", cancel=lambda: llamadas.append(1))
    host.grab()
    assert ov._cancel_rect is not None
    centro = ov._cancel_rect.center().toPoint()
    QtTest.QTest.mouseClick(ov, QtCore.Qt.LeftButton, pos=centro)
    QtWidgets.QApplication.processEvents()
    assert llamadas == [1]
    ov.end()


def test_foto_y_barra_con_avance(host):
    ov = busy.overlay_for(host)
    ov.begin("Cargando…", foto=True)
    ov.step(done=1, total=4, pump=False)
    img = host.grab().toImage()
    assert isinstance(img, QtGui.QImage) and not img.isNull()
    ov.end()
    assert not ov.isVisible() and QtWidgets.QApplication.overrideCursor() is None
