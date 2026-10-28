"""2.0.0 — «Componer hoja» como el prototipo: a la IZQUIERDA la lista de hojas (siempre a la vista, con su casilla)
y la composición sugerida; a la DERECHA «Área a tomar» / «Hoja compuesta».

Son los MISMOS widgets: la página «Origen» de siempre (PDF, galería `lst_pages` con sus casillas, «Tomar área de
esta hoja») pasa entera a la columna de la izquierda y su galería se ve como lista. Su pestaña se oculta y
`_go_tab(TAB_SOURCE)` lleva a «Área a tomar» (que ahora muestra la hoja elegida en la lista).
"""
from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr

ANCHO_COLUMNA = 300
MINI_W = 72


def rearmar(dlg, tab_source):
    root = dlg.layout()
    i_tabs = root.indexOf(dlg.tabs)
    sug_w = getattr(dlg, "_sug_tarjeta", None)           # la tarjeta de la composición sugerida
    for w in (dlg.tabs, dlg.stack, sug_w):
        if w is not None:
            root.removeWidget(w)
    origen = dlg.pages[tab_source]
    dlg.stack.removeWidget(origen)
    dlg.stack.insertWidget(tab_source, QtWidgets.QWidget())   # el lugar de «Origen» queda vacío
    # ── columna de hojas ──
    col = QtWidgets.QFrame()
    col.setObjectName("columnaHojas")
    col.setFixedWidth(ANCHO_COLUMNA)
    cl = QtWidgets.QVBoxLayout(col)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(6)
    tit = QtWidgets.QLabel(_tr("Hojas"))
    tit.setProperty("rol", "h2")
    cl.addWidget(tit)
    origen.layout().setContentsMargins(0, 4, 0, 0)
    cl.addWidget(origen, 1)
    origen.show()                                   # el stack la había dejado oculta
    if sug_w is not None:
        cl.addWidget(sug_w)
    g = dlg.lst_pages
    g.setViewMode(QtWidgets.QListView.ListMode)
    g.setWrapping(False)
    g.setGridSize(QtCore.QSize())
    g.setIconSize(QtCore.QSize(MINI_W, int(MINI_W * 0.72)))
    g.setSpacing(2)
    dlg.lbl_source_hint.setProperty("rol", "t3")
    dlg.lbl_source_hint.setStyleSheet("")
    # ── la hoja ──
    der = QtWidgets.QVBoxLayout()
    der.setSpacing(8)
    der.addWidget(dlg.tabs)
    der.addWidget(dlg.stack, 1)
    cuerpo = QtWidgets.QHBoxLayout()
    cuerpo.setSpacing(14)
    cuerpo.addWidget(col)
    cuerpo.addLayout(der, 1)
    root.insertLayout(i_tabs, cuerpo, 1)
    dlg.tabs.tabs[tab_source].hide()
    if getattr(dlg, "btn_all_pages", None) is not None:
        dlg.btn_all_pages.hide()                      # la lista de hojas ya está a la vista
    dlg.columna_hojas = col
    _flotantes(dlg, tab_source)


def _flotantes(dlg, tab_source):
    """«Área a tomar»: sus acciones en una pastilla abajo y el «Área sugerida» arriba a la derecha, flotando
    sobre la hoja (los mismos botones de siempre); la pestaña se llama «Esta hoja»."""
    from ui.asistente.wizard_widgets import flotar, pastilla
    dlg.tabs.tabs[tab_source + 1].setText(_tr("Esta hoja"))
    dlg.tabs.updateGeometry()
    pagina = dlg.pages[tab_source + 1]
    lay = pagina.layout()
    fila = None
    for k in range(lay.count()):
        sub = lay.itemAt(k).layout()
        if sub is not None and sub.indexOf(dlg.btn_take) >= 0:
            fila = sub
            break
    if fila is not None:
        ws = [fila.itemAt(k).widget() for k in range(fila.count()) if fila.itemAt(k).widget() is not None]
        dlg.pastilla_area = pastilla(ws)
        flotar(dlg.crop, dlg.pastilla_area, "abajo")
    i = lay.indexOf(dlg.crop)
    tarjeta = lay.itemAt(i - 1).widget() if i > 0 else None
    if tarjeta is not None and tarjeta.metaObject().className() == "QFrame":
        lay.removeWidget(tarjeta)
        tarjeta.setFixedWidth(340)
        dlg.tarjeta_area = tarjeta
        flotar(dlg.crop, tarjeta, "arriba_derecha")
