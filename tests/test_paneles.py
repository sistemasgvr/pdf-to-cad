"""Paneles laterales de la ventana principal (pedido del usuario 2026-10-05):
  - se ocultan solos como una pestaña en su borde y se despliegan encima del plano
    (side_panels.py), como las paletas de Civil 3D;
  - nada se corta ni pide scroll horizontal a su ancho mínimo, en español e inglés
    (responsive.py: botones/casillas que parten el texto, títulos con «…», filas
    de botones de 1 a 3 columnas)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from ui.comun import responsive as R  # noqa: E402
from ui.comun import side_panels  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    viejo = a.styleSheet()
    a.setStyleSheet(theme.build_stylesheet(theme.DARK))      # medidas con el QSS real (sin guardar el tema)
    yield a
    a.setStyleSheet(viejo)


# ─────────────────────────── controles responsivos ───────────────────────────

def test_wrap_lines_palabras_enteras_y_espacios_iniciales():
    adv = len                                       # 1 px por carácter
    assert R.wrap_lines("  Abrir diseñador de Duct Bank", 12, adv) == ["  Abrir", "diseñador de", "Duct Bank"]
    assert R.wrap_lines("Supercalifragilístico x", 5, adv) == ["Supercalifragilístico", "x"]
    assert R.palabra_mas_larga("  Abrir uno", adv) == len("  Abrir")


def test_boton_y_casilla_parten_el_texto(app):
    cont = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(cont)
    b = R.WrapButton("Volver a tratar como buzón/caja")
    c = R.WrapCheckBox("Ver etiquetas de buzón y en el DXF exportado")
    v.addWidget(b); v.addWidget(c)
    cont.resize(600, 200); cont.show(); app.processEvents()
    assert "\n" not in QtWidgets.QAbstractButton.text(b)
    alto = b.height()
    cont.resize(170, 200); app.processEvents()
    assert "\n" in QtWidgets.QAbstractButton.text(b) and "\n" in QtWidgets.QAbstractButton.text(c)
    assert b.text() == "Volver a tratar como buzón/caja"            # text() = texto completo
    assert b.height() > alto                                         # crece hacia abajo, no hacia el lado
    assert cont.minimumSizeHint().width() <= 170
    b.setText("Otro texto")                                          # el idioma cambia el texto: se re-parte
    assert b.text() == "Otro texto"
    cont.deleteLater()


def test_titulo_de_grupo_se_acorta(app):
    g = R.ResponsiveGroupBox("Propiedades del elemento curvo — selecciona uno de la lista")
    QtWidgets.QVBoxLayout(g).addWidget(QtWidgets.QLabel("x"))
    g.resize(200, 80); g.show(); app.processEvents()
    assert QtWidgets.QGroupBox.title(g).endswith("...") or "…" in QtWidgets.QGroupBox.title(g)
    assert g.title().startswith("Propiedades del elemento curvo")   # title() = completo
    assert g.toolTip() == g.title()
    assert g.minimumSizeHint().width() < 150
    g.deleteLater()


def test_rejilla_adaptable_baja_a_una_columna(app):
    cont = QtWidgets.QWidget()
    lay = R.GridAdaptable(cont, max_cols=2)
    bs = [R.WrapButton(t) for t in ("Cambiar tipo", "Editar/mover", "Ver datos extendidos", "Eliminar")]
    for b in bs:
        lay.addWidget(b)
    cont.resize(520, 200); cont.show(); app.processEvents()
    assert lay.columnas(520) == 2 and bs[0].y() == bs[1].y() and bs[2].y() > bs[0].y()
    angosto = max(b.minimumSizeHint().width() for b in bs) + 10
    cont.resize(angosto, 400); app.processEvents()
    assert lay.columnas(angosto) == 1 and len({b.y() for b in bs}) == 4
    bs[2].hide(); app.processEvents()                                # el oculto no ocupa fila
    assert bs[3].y() < 3 * (bs[0].height() + 6) + 1
    cont.deleteLater()


# ─────────────────────────── ventana real ───────────────────────────

@pytest.fixture
def win(app, monkeypatch):
    from traduccion import i18n
    from traduccion import i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.resize(1400, 820); w.show()
    w.pipes = [{"layer": "DRENAJE", "pts": [(100, 100), (400, 100), (400, 400)], "name": "Linea Norte",
                "diam": 12.0, "inv_start": 100.0, "inv_end": 98.0},
               {"layer": "ELECTRICO", "pts": [(500, 500), (800, 500), (800, 700)], "name": "", "diam": 4.0}]
    w.structures.append({"x": 800.0, "y": 700.0, "cod": "SÓLIDO-1", "net": "conduit", "solid": True,
                         "shape": "rect", "solid_height_ft": 6.0,
                         "outline": [(780, 680), (820, 680), (820, 720), (780, 720)]})
    w._refresh_lists()
    app.processEvents()
    yield w
    for p in (w.panel_izq, w.panel_der):
        p.close()
    w._dirty = False
    w.close()
    i18n.set_lang("es")
    i18n_core._current_lang = previo
    import gc; gc.collect()


def test_ocultar_y_fijar_cada_panel(win, app):
    for panel, dock, act, lado in ((win.panel_izq, win._ldock, win.act_panel_izq, "left"),
                                   (win.panel_der, win._rdock, win.act_panel_der, "right")):
        act.setChecked(True); app.processEvents()                    # desde el menú Ver
        assert panel.autohide and not dock.isVisible() and panel.tab_dock.isVisible()
        assert panel.content.parent() is panel.overlay
        assert side_panels._settings().value(f"panel_{panel.key}_auto") is True
        panel.open(); app.processEvents()
        assert panel.is_open() and panel.tab.isChecked()
        g, c = panel.overlay.geometry(), win.centralWidget().geometry()
        assert g.top() == c.top() and g.height() == c.height() and g.width() >= side_panels.MIN_W
        assert (g.left() == c.left()) if lado == "left" else (g.right() == c.right())
        panel.btn_pin_overlay.click(); app.processEvents()           # chincheta: se vuelve a fijar
        assert not panel.autohide and dock.isVisible() and not panel.tab_dock.isVisible()
        assert dock.widget() is panel.content and not act.isChecked()


def test_se_recoge_al_alejar_el_raton_salvo_escribiendo(win, app, monkeypatch):
    panel = win.panel_der
    panel.set_autohide(True); panel.open(); app.processEvents()
    lejos = win.mapToGlobal(QtCore.QPoint(200, 300))                 # sobre el plano
    monkeypatch.setattr(QtGui.QCursor, "pos", staticmethod(lambda: lejos))
    win.prop_name.setFocus(); app.processEvents()
    if QtWidgets.QApplication.focusWidget() is win.prop_name:        # escribiendo: no se recoge solo
        for _ in range(10):
            panel._check_close()
        assert panel.is_open()
    win.centralWidget().setFocus(); app.processEvents()
    for _ in range(side_panels.CLOSE_DELAY_MS // side_panels.POLL_MS + 1):
        panel._check_close()
    assert not panel.is_open()


def test_clic_en_el_plano_lo_recoge(win, app):
    panel = win.panel_izq
    panel.set_autohide(True); panel.open(); app.processEvents()
    vp = win.canvas.viewport()
    pos = QtCore.QPointF(vp.width() - 20, vp.height() / 2)
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, pos, vp.mapToGlobal(pos),
                           QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)
    app.processEvents()
    assert not panel.is_open()


def test_propiedades_se_guardan_con_el_panel_recogido(win, app):
    win.panel_der.set_autohide(True); app.processEvents()             # recogido: el desplegable no está «visible»
    win._show_tab(0); win._sel_pipe(0)
    assert win.prop_family.isVisibleTo(win.gprop) == win.lbl_prop_family.isVisibleTo(win.gprop)
    win.pipes[0]["pipe_family"] = "X"
    win._prop_changed()                                               # no borra ni pisa nada por estar recogido
    assert win.pipes[0]["name"] == "Linea Norte"


def _cortados(sc):
    vp = sc.viewport(); vw = vp.width(); cont = sc.widget()
    malos = []
    if cont.minimumSizeHint().width() > vw:
        malos.append(f"contenido {cont.minimumSizeHint().width()} > {vw}")
    for x in cont.findChildren(QtWidgets.QWidget):
        if not x.isVisibleTo(cont) or x.width() <= 0 or isinstance(x, QtWidgets.QScrollBar):
            continue
        if x.mapTo(vp, QtCore.QPoint(x.width(), 0)).x() > vw + 1:
            malos.append(f"se sale: {type(x).__name__} «{getattr(x, 'text', lambda: '')() if hasattr(x, 'text') else ''}»")
    return malos


@pytest.mark.parametrize("lang", ["es", "en"])
def test_nada_se_corta_al_ancho_minimo(win, app, lang):
    from traduccion import i18n
    from nucleo.model import TAB_BZ, TAB_CL, TAB_CURVE, TAB_DB, TAB_PIPE
    i18n.set_lang(lang); app.processEvents()
    win.resizeDocks([win._ldock, win._rdock], [side_panels.MIN_W] * 2, QtCore.Qt.Horizontal)
    app.processEvents()
    sl = win._ldock.findChild(QtWidgets.QScrollArea)
    sr = win._rdock.findChild(QtWidgets.QScrollArea)
    problemas = []
    for i in range(win.toolbox.count()):
        win.toolbox.setCurrentIndex(i); app.processEvents()
        problemas += [f"izq «{win.toolbox.itemText(i)}»: {m}" for m in _cortados(sl)]
    win._show_tab(TAB_PIPE); win._sel_pipe(0); app.processEvents()
    problemas += [f"Utilidades: {m}" for m in _cortados(sr)]
    win.btn_seg_edit.setChecked(True); app.processEvents()
    problemas += [f"Cotas por tramo: {m}" for m in _cortados(sr)]
    win.btn_seg_edit.setChecked(False)
    win._show_tab(TAB_BZ)
    for row in range(win.bz_list.count()):
        win.bz_list.setCurrentRow(row); app.processEvents()
        problemas += [f"Buzones fila {row}: {m}" for m in _cortados(sr)]
    for ti in (TAB_CURVE, TAB_CL, TAB_DB):
        win._show_tab(ti); app.processEvents()
        problemas += [f"pestaña {ti}: {m}" for m in _cortados(sr)]
    assert not problemas, "\n".join(problemas)
