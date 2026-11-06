"""Ningún paso del asistente amontona sus controles (reporte del usuario 2026-11-04: en «Capas de la hoja» de
una hoja sin capas, Utilidad y Rol se pisaban, el árbol no se veía y la ayuda salía cortada).

La causa era general: un panel sin desplazamiento donde no cabe lo que lleva. Qt no cuenta el alto de un texto
que se parte en líneas, así que el mínimo de la ventana no lo protege y aplasta los controles. Estas pruebas abren
cada paso a tamaños reales de pantalla, con el tema de verdad, y miran la geometría de lo que queda a la vista.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets

from reconocimiento import recognition as rec
from traduccion import i18n
from ui.asistente import composite_dialog, layer_dialog, organized_layer_dialog
from ui.asistente import recognition_dialog as rd
from ui.comun import theme

ROOT = Path(__file__).resolve().parent.parent
DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
# ventana maximizada: laptop chica, laptop al 125 %, pantalla Full HD
TAMANOS = [(1280, 640), (1366, 680), (1536, 790), (1920, 1000)]
CONTROLES = (QtWidgets.QComboBox, QtWidgets.QLineEdit, QtWidgets.QAbstractButton, QtWidgets.QLabel,
             QtWidgets.QAbstractSpinBox)


@pytest.fixture
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    hoja, paleta, actual = a.styleSheet(), a.palette(), theme._current
    a.setStyle("Fusion")                  # sin `apply_theme`: ese guarda la preferencia
    theme._current = theme.DARK
    a.setPalette(theme._palette_dark())
    a.setStyleSheet(theme.build_stylesheet(theme.DARK))
    yield a
    a.setStyleSheet(hoja)
    a.setPalette(paleta)
    theme._current = actual
    i18n.set_lang("es")


@pytest.fixture(autouse=True)
def sin_maximizar(monkeypatch):
    """Cada prueba pone su tamaño: maximizar daría el de la pantalla simulada."""
    for mod in (composite_dialog, layer_dialog, rd):
        monkeypatch.setattr(mod, "maximize_on_show", lambda _d: None)


def _colocar(app, dlg, ancho, alto):
    """La ventana al tamaño pedido aunque su mínimo sea mayor: maximizada, la pantalla manda."""
    dlg.layout().setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
    dlg.setMinimumSize(0, 0)
    dlg.setWindowState(QtCore.Qt.WindowNoState)
    dlg.resize(ancho, alto)
    dlg.show()
    dlg.resize(ancho, alto)
    for _ in range(6):                    # NaturalHeightScroll ajusta con un temporizador de 0 ms
        app.processEvents()
        QtCore.QThread.msleep(5)
    assert (dlg.width(), dlg.height()) == (ancho, alto)


def _a_la_vista(w, raiz):
    return w.isVisible() and w.window() is raiz and w.width() > 0 and w.height() > 0


def _nombre(w):
    texto = w.text() if hasattr(w, "text") and callable(w.text) else ""
    return f"{type(w).__name__}«{str(texto)[:30]}»"


def amontonados(dlg):
    """Lo que está mal puesto: hermanos de un layout que se pisan y controles más bajos de lo que necesitan."""
    malos = []
    for lay in dlg.findChildren(QtWidgets.QLayout):
        if isinstance(lay, QtWidgets.QStackedLayout):
            continue
        hijos = []
        for i in range(lay.count()):
            it = lay.itemAt(i)
            w = it.widget()
            if w is not None and not _a_la_vista(w, dlg):
                continue
            if w is None and (it.layout() is None or it.isEmpty()):
                continue
            hijos.append((_nombre(w) if w is not None else "layout", it.geometry()))
        for a in range(len(hijos)):
            for b in range(a + 1, len(hijos)):
                cruce = hijos[a][1].intersected(hijos[b][1])
                if cruce.width() > 1 and cruce.height() > 1:
                    malos.append(f"se pisan {hijos[a][0]} y {hijos[b][0]} ({cruce.height()} px)")
    for w in dlg.findChildren(QtWidgets.QWidget):
        if not isinstance(w, CONTROLES) or not _a_la_vista(w, dlg):
            continue
        hace_falta = w.minimumSizeHint().height()
        if w.hasHeightForWidth():
            hace_falta = max(hace_falta, w.heightForWidth(w.width()))
        if w.height() < hace_falta - 1:
            malos.append(f"aplastado {_nombre(w)}: {w.height()} de {hace_falta} px")
    return malos


def _hoja_sin_capas(n=20):
    doc = fitz.open()
    p = doc.new_page(width=800, height=600)
    for i in range(n):
        p.draw_line((30, 20 + i * 25), (700, 20 + i * 25), color=(i / n, 0, 1 - i / n), width=0.2 + i * 0.1)
    return doc


def _hoja_con_capas():
    doc = fitz.open()
    capas = {n: doc.add_ocg(n) for n in ("C-WATR-UNGD-E", "C-ELEC-UNGD-E", "C-NGAS-UNGD-E", "G-ROAD")}
    p = doc.new_page(width=800, height=600)
    for i, (n, oc) in enumerate(capas.items()):
        p.draw_line((30, 50 + i * 60), (700, 50 + i * 60), color=(0, 0, 0), width=1, oc=oc)
    datos = doc.tobytes()
    doc.close()
    return fitz.open(stream=datos, filetype="pdf")


@pytest.mark.parametrize("ancho,alto", TAMANOS)
@pytest.mark.parametrize("idioma", ["es", "en"])
@pytest.mark.parametrize("hoja", [_hoja_sin_capas, _hoja_con_capas], ids=["sin_capas", "con_capas"])
def test_capas_de_la_hoja_no_amontona(app, hoja, idioma, ancho, alto):
    i18n.set_lang(idioma)
    doc = hoja()
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        _colocar(app, dlg, ancho, alto)
        dlg._apply_side_width()
        app.processEvents()
        assert amontonados(dlg) == []
    finally:
        dlg.reject()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


@pytest.mark.parametrize("ancho,alto", TAMANOS)
def test_el_arbol_de_capas_siempre_deja_ver_filas(app, ancho, alto):
    """Lo principal del panel: en una laptop chica se desplaza el panel, nunca se encoge la lista."""
    doc = _hoja_sin_capas()
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        _colocar(app, dlg, ancho, alto)
        assert dlg.tree.height() >= layer_dialog.ARBOL_MIN_PX
    finally:
        dlg.reject()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


def test_con_una_capa_elegida_y_su_utilidad_asignada_sigue_en_orden(app):
    """El texto de la capa con su leyenda y las filas de «Reconocer» que aparecen al asignar no aplastan nada."""
    doc = _hoja_sin_capas()
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        _colocar(app, dlg, 1366, 680)
        grupo = dlg.tree.topLevelItem(0)
        grupo.setExpanded(True)
        dlg.tree.setCurrentItem(grupo.child(0))
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("AGUA"))
        for _ in range(6):
            app.processEvents()
            QtCore.QThread.msleep(5)
        assert dlg.assignment_role.isEnabled()
        assert amontonados(dlg) == []
    finally:
        dlg.reject()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


def test_hoja_sin_capas_solo_lista_las_utilidades_que_ya_tienen_estilo(app):
    """Seis filas apagadas con «0 capas» ocupaban medio panel y no decían nada."""
    doc = _hoja_sin_capas()
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        _colocar(app, dlg, 1536, 790)
        assert not any(sw.isVisible() for sw in dlg._recog_switches.values())
        assert not dlg.chk_recog_all.isVisible()
        assert dlg.lbl_recog_warn.isVisible()
        grupo = dlg.tree.topLevelItem(0)
        grupo.setExpanded(True)
        dlg.tree.setCurrentItem(grupo.child(0))
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("GAS"))
        app.processEvents()
        visibles = [k for k, sw in dlg._recog_switches.items() if sw.isVisible()]
        assert visibles == ["GAS"]
        assert dlg.recognition_utilities() == ("GAS",)
    finally:
        dlg.reject()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


@pytest.mark.parametrize("ancho,alto", TAMANOS)
def test_componer_hoja_no_amontona(app, ancho, alto):
    doc = _hoja_con_capas()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": doc.tobytes()}], None, {}, 0)
    doc.close()
    try:
        _colocar(app, dlg, ancho, alto)
        for pestana in range(dlg.stack.count()):
            dlg._go_tab(pestana)
            app.processEvents()
            assert amontonados(dlg) == [], f"pestaña {pestana}"
    finally:
        dlg.close_docs() if hasattr(dlg, "close_docs") else None
        dlg.deleteLater()
        app.processEvents()


@pytest.mark.skipif(not DU06.is_file(), reason="PDF de prueba DU06 no está en el repo")
@pytest.mark.parametrize("ancho,alto", TAMANOS)
def test_vista_previa_no_amontona(app, ancho, alto):
    img = QtGui.QImage(800, 600, QtGui.QImage.Format_RGB888)
    img.fill(QtGui.QColor("white"))
    res = rec.recognize_page(DU06, 3, zoom=1.0)
    dlg = rd.RecognitionPreviewDialog(None, img, res, "ELECTRICO", page_count=19)
    try:
        _colocar(app, dlg, ancho, alto)
        assert amontonados(dlg) == []
    finally:
        dlg.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("ancho,alto", TAMANOS)
def test_capas_de_hojas_organizadas_no_amontona(app, ancho, alto):
    doc = _hoja_con_capas()
    dlg = organized_layer_dialog.OrganizedLayersDialog(
        None, [doc], [{"name": "a.pdf", "start": 0, "count": 1}], {"main": 0}, {})
    try:
        _colocar(app, dlg, ancho, alto)
        assert amontonados(dlg) == []
    finally:
        dlg._timer.stop()
        dlg.deleteLater()
        app.processEvents()
        doc.close()
