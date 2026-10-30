"""La propuesta y sus acciones se pueden leer y alcanzar en un inspector estrecho."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from test_diametro_ia_ventana import _ventana, _elegir, _esperar


@pytest.fixture
def ui(monkeypatch, tmp_path):
    from PySide6 import QtGui, QtWidgets
    from ui.comun import theme
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    font, css = app.font(), app.styleSheet()
    fuente = Path("C:/Windows/Fonts/segoeui.ttf")
    if fuente.is_file():
        QtGui.QFontDatabase.addApplicationFont(str(fuente))
        app.setFont(QtGui.QFont("Segoe UI", 10))
    monkeypatch.setattr(theme, "_arrow_dir", str(tmp_path))
    app.setStyleSheet(theme.build_stylesheet(theme.DARK))
    yield app
    app.setStyleSheet(css)
    app.setFont(font)


@pytest.mark.parametrize("ancho,repeticiones", [(300, 1), (340, 1), (440, 1), (300, 8)])
def test_propuesta_no_se_recorta_y_acciones_visibles(ui, ancho, repeticiones):
    from PySide6 import QtCore, QtGui, QtWidgets
    from ia.diametro_ia import Sugerencia
    w = _ventana(SimpleNamespace(url="http://127.0.0.1:9"))
    w.resize(1280, 800)
    w._rdock.setFixedWidth(ancho)
    _elegir(w, 0)
    w.show()
    app = QtWidgets.QApplication.instance()
    for _ in range(5):
        app.processEvents()
    area = w.pila_derecha.widget(0)
    area.verticalScrollBar().setValue(0)
    motivo = ('Propuesta normativa, fuente LA Sewer Design Manual F200; mínimo 8" para colector. '
              'Capa PS89616000-A1-US-C3D-PROP_SEWER_PIPE_ALGN|C-SSWR-UNGD-N. '
              'Tipo supuesto: COLECTOR. Revisa la propuesta antes de aprobar. ') * repeticiones
    analisis = dict(opcion=dict(criterio='mínimo 8" (COLECTOR).',fuente="LA Sewer Design Manual F200",
                                tipo="COLECTOR",tipo_supuesto=True),
                    entrada=dict(contexto=dict(trayecto=dict(largo_ft=58.3,giros_mayores_10_grados=2),contactos=[{}])))
    s = Sugerencia(8, None, "media", motivo, "", "normativa", analisis)
    w._diam_ia_pedido = (42, 0, w._diam_ia_clave(w._diam_ia_ficha(0)))
    w._diam_ia_listo(42, s)

    def accesibles():
        vp = area.viewport()
        lbl = w.lbl_diam_ia
        return (lbl.height() >= lbl.heightForWidth(lbl.width())
                and all(vp.rect().contains(QtCore.QRect(b.mapTo(vp, QtCore.QPoint()), b.size()))
                        for b in (w.btn_diam_ia_usar, w.btn_diam_ia_no)))

    try:
        assert _esperar(w, accesibles, s=3), dict(
            texto=w.lbl_diam_ia.geometry().getRect(), hfw=w.lbl_diam_ia.heightForWidth(w.lbl_diam_ia.width()),
            tarjeta=w.tarjeta_diam_ia.geometry().getRect(), contenido=area.widget().geometry().getRect(),
            viewport=area.viewport().size().toTuple(), scroll=area.verticalScrollBar().value(),
            maximo=area.verticalScrollBar().maximum(),
            botones=[(b.mapTo(area.viewport(),QtCore.QPoint()).toTuple(),b.size().toTuple())
                     for b in (w.btn_diam_ia_usar,w.btn_diam_ia_no)])
        assert area.widget().width() <= area.viewport().width()
        lbl = w.lbl_diam_ia
        assert lbl.height() >= lbl.heightForWidth(lbl.width())
        assert all(c in lbl.text() for c in ("Propuesta:","Por qué:","Criterio:","Fuente:","Referencia:"))
        for b in (w.btn_diam_ia_usar, w.btn_diam_ia_no):
            assert b.width() >= b.minimumSizeHint().width()
        assert w.pipes[0]["diam"] == 12  # mostrar la tarjeta no equivale a aprobar
        # Refrescar la misma respuesta respeta el desplazamiento manual.
        area.verticalScrollBar().setValue(0)
        w._diam_ia_refrescar()
        for _ in range(4):
            app.processEvents()
        assert area.verticalScrollBar().value() == 0
    finally:
        w.hide()


def test_el_texto_se_encoge_al_ampliar_o_cambiar_respuesta(ui):
    from ui.ventana.ventana_diametro_ia import _TextoAnalisis
    lbl = _TextoAnalisis()
    lbl.setWordWrap(True)
    lbl.resize(180,100)
    lbl.setText("Una explicación de la propuesta que puede ocupar varias líneas. "*12)
    lbl.show()
    ui.processEvents()
    alto = lbl.minimumHeight()
    lbl.resize(400,lbl.height())
    ui.processEvents()
    assert lbl.minimumHeight() < alto
    lbl.setText("Respuesta corta.")
    ui.processEvents()
    assert lbl.minimumHeight() < 60
    lbl.hide()
