"""Centro de avisos (reporte 2026-11-18: el aviso ⚠ y la tarjeta «Interpretando la hoja…» se tapaban): todo lo que
aparece abajo a la derecha pasa por `ui/comun/centro_avisos` y se apila sin taparse ni salirse de la ventana."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from ui.comun import aviso_breve, centro_avisos  # noqa: E402
from ui.comun.tarjeta_avance import CapaTarjetas  # noqa: E402


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    w = QtWidgets.QMainWindow()
    w.setCentralWidget(QtWidgets.QWidget())
    w.resize(1000, 700)
    w.show()
    app.processEvents()
    yield w
    w.close()
    app.processEvents()


def _rects(win):
    return [t.geometry() for t in centro_avisos.centro(win).tarjetas()]


def _sin_tocarse(rects):
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not a.intersects(b), (a, b)


def test_carga_y_aviso_no_se_tapan(app, win):
    capa = CapaTarjetas(win)
    capa.begin("Interpretando la hoja…", "Leyendo las letras del mapa")
    aviso_breve.mostrar(win, "Georreferencia dudosa", "Revisa los pares", tono="aviso")
    app.processEvents()
    rects = _rects(win)
    assert len(rects) == 2
    _sin_tocarse(rects)
    caja = win.rect()
    assert all(caja.contains(r) for r in rects)
    # la carga abajo, el aviso encima
    carga, aviso = centro_avisos.centro(win).tarjetas()
    assert carga.geometry().top() > aviso.geometry().bottom()
    abajo = carga.geometry().bottom()
    capa.end()
    app.processEvents()
    assert centro_avisos.centro(win).tarjetas() == [aviso]
    assert aviso.geometry().bottom() == abajo              # el aviso baja al lugar que dejó la carga


def test_como_mucho_tres_avisos_y_uno_igual_lo_reemplaza(app, win):
    for i in range(5):
        aviso_breve.mostrar(win, "Aviso %d" % i)
    app.processEvents()
    textos = [t.lbl_titulo.text() for t in centro_avisos.centro(win).tarjetas()]
    assert textos == ["Aviso 2", "Aviso 3", "Aviso 4"]
    aviso_breve.mostrar(win, "Aviso 3")
    app.processEvents()
    textos = [t.lbl_titulo.text() for t in centro_avisos.centro(win).tarjetas()]
    assert textos == ["Aviso 2", "Aviso 4", "Aviso 3"]
    _sin_tocarse(_rects(win))


def test_sin_lugar_se_van_los_avisos_mas_viejos(app, win):
    win.resize(1000, 260)
    app.processEvents()
    capa = CapaTarjetas(win)
    capa.begin("Cargando", "detalle")
    for i in range(3):
        aviso_breve.mostrar(win, "Aviso %d" % i, "una explicación algo larga para que ocupe dos líneas")
    app.processEvents()
    tarjetas = centro_avisos.centro(win).tarjetas()
    assert tarjetas[0] in capa.tarjetas                    # la carga no se cierra
    assert [t.lbl_titulo.text() for t in tarjetas[1:]][-1] == "Aviso 2"   # el más nuevo sigue
    _sin_tocarse(_rects(win))
    assert all(win.rect().contains(r) for r in _rects(win))
    capa.end()


def _global(w):
    from PySide6 import QtCore
    return QtCore.QRect(w.mapToGlobal(QtCore.QPoint(0, 0)), w.size())


def test_cargando_va_abajo_y_las_demas_encima(app, win):
    """La tarjeta de «Cargando…» (la dibuja la capa de `busy`) tiene el lugar de abajo: nada la tapa."""
    from ui.comun import busy
    capa = CapaTarjetas(win)
    capa.begin("Interpretando la hoja…", "Leyendo las letras del mapa")
    aviso_breve.mostrar(win, "Georreferencia dudosa", tono="aviso")
    ov = busy.overlay_for(win)
    ov.begin("Ubicando las hojas elegidas…", "Buscando en cada hoja el mismo mapa base")
    app.processEvents()
    tarjeta_cargando = ov._geometria()[0].toAlignedRect()
    rects = _rects(win)
    _sin_tocarse(rects + [tarjeta_cargando])
    assert all(r.bottom() < tarjeta_cargando.top() for r in rects)
    ov.end()
    app.processEvents()
    assert max(r.bottom() for r in _rects(win)) > tarjeta_cargando.top()   # bajan al quedar libre
    capa.end()


def test_ventanita_del_tema_se_apila_con_las_demas(app, win):
    from ui.comun import cambio_tema
    capa = CapaTarjetas(win)
    capa.begin("Exportando a DXF…", "Guardando")
    aviso = cambio_tema.AvisoCambioTema(win, "Cambiando a tema oscuro…")
    aviso.mostrar()
    app.processEvents()
    tarjetas = centro_avisos.centro(win).tarjetas()
    assert aviso in tarjetas and len(tarjetas) == 2
    a, b = (_global(t) for t in tarjetas)
    assert not a.intersects(b)
    aviso.terminar()
    app.processEvents()
    assert centro_avisos.centro(win).tarjetas() == capa.tarjetas
    capa.end()
