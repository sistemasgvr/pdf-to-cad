"""Reporte del usuario 2026-11-16: «Revisar y limpiar el dibujo» lleva al lugar con zoom (fitInView) y, al cerrar
la ventana, ya no se podía alejar: el contador de zoom del lienzo no seguía a la vista y llegaba a su tope de
alejar con la vista todavía cerca."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from ui.comun import canvas as C  # noqa: E402


def _lienzo():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    cv = C.Canvas(None)
    cv.resize(800, 600)
    img = QtGui.QImage(2000, 1500, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor("white"))
    cv.set_image(img)
    return cv


def _escala(cv):
    return abs(cv.transform().m11())


def test_tras_ir_a_un_lugar_con_fitinview_se_puede_alejar_hasta_la_hoja_entera():
    cv = _lienzo()
    base = _escala(cv)
    cv.fitInView(QtCore.QRectF(900, 700, 120, 120), QtCore.Qt.KeepAspectRatio)   # = _ir_a_lugar de la limpieza
    assert _escala(cv) > 4 * base
    while cv.apply_zoom(0.8):
        pass
    assert _escala(cv) <= base, "no se pudo alejar hasta ver la hoja entera"


def _encuadre(cv):
    r, vp = cv.sceneRect(), cv.viewport().rect().adjusted(2, 2, -2, -2)
    return min(vp.width() / r.width(), vp.height() / r.height())


def test_con_el_lienzo_cambiado_de_tamano_igual_se_aleja_hasta_la_hoja_entera():
    """2.º reporte (mismo día): el nivel se medía contra el encuadre del momento de cargar la hoja; con el lienzo
    de otro tamaño después, alejar se topaba antes de ver la hoja entera."""
    cv = _lienzo()
    cv.resize(160, 120)
    cv.fitInView(QtCore.QRectF(900, 700, 120, 120), QtCore.Qt.KeepAspectRatio)
    while cv.apply_zoom(0.8):
        pass
    assert _escala(cv) <= _encuadre(cv) * 1.0001, "no se pudo alejar hasta ver la hoja entera"


def test_el_tope_de_acercar_sigue_igual():
    cv = _lienzo()
    base = _escala(cv)
    while cv.apply_zoom(1.25):
        pass
    assert _escala(cv) <= base * C._ZOOM_MAX * 1.0001
    cv.fitInView(cv.sceneRect(), QtCore.Qt.KeepAspectRatio)
    assert abs(cv._zoom_level - 1.0) < 1e-6
