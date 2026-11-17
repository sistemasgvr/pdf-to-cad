"""Pedido 2026-11-13: al pulsar «Modo claro / oscuro» a veces tardaba y parecía colgada. Ahora sale un aviso con
un girador ANTES del cambio, no se congela mientras Qt cambia el tema, y un clic de más no vuelve a alternar."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from PySide6 import QtCore, QtTest, QtWidgets  # noqa: E402


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _esperar(cond, ms=3000):
    reloj = QtCore.QElapsedTimer()
    reloj.start()
    while not cond() and reloj.elapsed() < ms:
        QtTest.QTest.qWait(10)
    return cond()


def test_aviso_antes_durante_y_despues_del_cambio():
    app = _app()
    from ui.comun import cambio_tema, theme
    ventana = QtWidgets.QWidget()
    ventana.resize(600, 400)
    ventana.show()
    llamadas, fin = [], []
    visto_al_aplicar = []

    def aplicar():
        aviso = next(w for w in app.topLevelWidgets() if isinstance(w, cambio_tema.AvisoCambioTema))
        visto_al_aplicar.append(aviso.isVisible())
        theme.apply_theme(app, "dark" if theme.tokens().name == "light" else "light")
        visto_al_aplicar.append(aviso.updatesEnabled())     # apply_theme no lo congela
        llamadas.append(1)

    aviso = cambio_tema.cambiar(ventana, aplicar, "Cambiando a modo oscuro…", al_terminar=lambda: fin.append(1))
    assert aviso.isVisible() and llamadas == []             # aparece ANTES de cambiar
    assert _esperar(lambda: llamadas == [1])
    assert visto_al_aplicar == [True, True]
    assert fin == [] or len(fin) == 1
    assert _esperar(lambda: fin == [1])
    assert not any(isinstance(w, cambio_tema.AvisoCambioTema) and w.isVisible() for w in app.topLevelWidgets())
    ventana.close()


def test_apply_theme_congela_las_ventanas_pero_no_el_aviso(monkeypatch):
    app = _app()
    from ui.comun import cambio_tema, theme
    ventana = QtWidgets.QWidget()
    ventana.show()
    aviso = cambio_tema.AvisoCambioTema(ventana, "x")
    aviso.mostrar()
    congeladas = []
    original = QtWidgets.QWidget.setUpdatesEnabled

    def espiar(w, v):
        if not v:
            congeladas.append(w)
        return original(w, v)
    monkeypatch.setattr(QtWidgets.QWidget, "setUpdatesEnabled", espiar)
    theme.apply_theme(app, theme.tokens().name)
    assert ventana in congeladas and aviso not in congeladas
    aviso.terminar()
    ventana.close()


def test_un_clic_de_mas_mientras_cambia_no_vuelve_a_alternar(monkeypatch):
    _app()
    from ui.comun import theme
    from ui.ventana.ventana_herramientas import HerramientasMixin

    class Ventana(HerramientasMixin, QtWidgets.QWidget):
        pass
    win = Ventana()
    win.resize(500, 300)
    win.show()
    veces = []
    monkeypatch.setattr(theme, "toggle", lambda app: veces.append(1))
    win._toggle_theme()
    win._toggle_theme()                                     # doble clic: el segundo se ignora
    assert _esperar(lambda: veces == [1] and not win._cambiando_tema)
    win._toggle_theme()                                     # terminado, otro clic sí alterna
    assert _esperar(lambda: veces == [1, 1] and not win._cambiando_tema)
    win.hide()
    win._toggle_theme()                                     # sin ventana en pantalla: al instante, como antes
    assert veces == [1, 1, 1]
    win.close()


def test_aviso_es_un_toast_abajo_a_la_derecha_con_barra_de_carga():
    """Pedido 2026-11-14: no un recuadro en el medio de la pantalla, sino la tarjeta de siempre (abajo a la
    derecha, con barra de carga) que llega al final cuando el tema ya cambió."""
    app = _app()
    from ui.comun import cambio_tema
    ventana = QtWidgets.QWidget()
    ventana.resize(900, 600)
    ventana.show()
    QtTest.QTest.qWait(50)
    valores = []
    aviso = cambio_tema.cambiar(ventana, lambda: valores.append(aviso.barra.value()), "Cambiando a modo oscuro…")
    geo = QtCore.QRect(ventana.mapToGlobal(QtCore.QPoint(0, 0)), ventana.size())
    t = aviso.frameGeometry()
    assert t.right() <= geo.right() and t.bottom() <= geo.bottom()
    assert t.left() > geo.center().x() and t.top() > geo.center().y()      # en la esquina de abajo a la derecha
    assert isinstance(aviso.barra, QtWidgets.QProgressBar) and aviso.barra.value() < 1000
    assert _esperar(lambda: valores != [])
    assert 0 < valores[0] < 1000                                           # avanzó antes de cambiar el tema
    assert aviso.barra.value() == 1000                                     # y llega al final al terminar
    assert _esperar(lambda: not aviso.isVisible())
    ventana.close()
