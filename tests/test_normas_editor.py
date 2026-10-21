"""Normativas editables desde la aplicación (pedido del usuario 2026-10-20: «que todo sea editable desde
la aplicación… la aplicación manda en todo»): tablas de texto ida y vuelta, las mismas reglas que el
Excel, utilidades/tipos/accesorios que decide la app, renombrar un tipo y la ventana real."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import model  # noqa: E402
from nucleo import normas_catalogo as nc  # noqa: E402
from nucleo import normas_tablas as NT  # noqa: E402


def _textos(cat):
    return {t.clave: NT.filas(cat, t.clave) for t in NT.TABLAS}


def test_las_utilidades_son_las_de_la_aplicacion():
    assert nc.UTILIDADES == tuple(c for _n, c in model.TIPOS)


def test_tablas_de_texto_ida_y_vuelta_igual_que_el_catalogo():
    cat = nc.nuevo()
    vuelta, problemas = NT.catalogo(_textos(cat))
    assert problemas == []
    assert vuelta == nc.normalizar(cat)


def test_la_aplicacion_manda_utilidad_tipo_accesorio_y_numeros():
    t = _textos(nc.nuevo())
    t["tipos"].append(["AGUA POTABLE", "PRINCIPAL"])                   # utilidad que la app no tiene
    t["diametros"].append(["AGUA", "TIPO INVENTADO", "6", "", "", ""])  # tipo que no está en Tipos
    t["accesorios"].append(["AGUA", "Valvula", "", "", "", "", ""])     # accesorio que la app no reconoce
    t["electricas"].append(["ELECTRICO", "SIMPLE", "", "cuatrocientos", "", "", "", "", "", "", "", "", ""])
    cat, problemas = NT.catalogo(t)
    cols = {(c, col) for c, _f, col, _m in problemas}
    assert ("tipos", "UTILIDAD") in cols and ("diametros", "TIPO") in cols
    assert ("accesorios", "ACCESORIO") in cols and ("electricas", "AMPERAJE MIN (A)") in cols
    filas = {(c, f) for c, f, _col, _m in problemas}
    assert ("tipos", len(t["tipos"]) - 1) in filas and ("diametros", len(t["diametros"]) - 1) in filas
    assert ["AGUA POTABLE", "PRINCIPAL"] not in cat["tipos"]
    assert not any(f["tipo"] == "TIPO INVENTADO" for f in cat["diametros"])


def test_excel_tambien_rechaza_una_utilidad_que_no_es_de_la_app(tmp_path):
    from nucleo import normas_excel
    import openpyxl
    ruta = str(tmp_path / "n.xlsx")
    normas_excel.exportar(nc.nuevo(), ruta)
    wb = openpyxl.load_workbook(ruta)
    wb["TIPOS"].append(["CABLE", "PRINCIPAL"])
    wb.save(ruta)
    problemas = []
    cat, _faltan = normas_excel.importar(ruta, problemas)
    assert any("CABLE" in p and "utilidad de la aplicación" in p for p in problemas)
    assert ["CABLE", "PRINCIPAL"] not in cat["tipos"]


def test_renombrar_un_tipo_lo_cambia_en_las_demas_tablas():
    t = _textos(nc.nuevo())
    n = NT.renombrar_tipo(t, "AGUA", "DISTRIBUCION PRINCIPAL", "RED PRINCIPAL")
    assert n > 0
    assert not any(f[0] == "AGUA" and "DISTRIBUCION PRINCIPAL" in f for k in ("diametros", "accesorios")
                   for f in t[k])
    assert any(f[0] == "GAS" and f[1] == "DISTRIBUCION PRINCIPAL" for f in t["diametros"])   # otra utilidad no


def test_tipos_y_columnas_que_decide_la_app():
    tab = {t.clave: t for t in NT.TABLAS}
    assert NT.tipo_columna(tab["diametros"], "UTILIDAD") == NT.UTILIDAD
    assert NT.tipo_columna(tab["diametros"], "TIPO") == NT.TIPO
    assert NT.tipo_columna(tab["tipos"], "TIPO") == NT.TEXTO                 # ahí se crean
    assert NT.tipo_columna(tab["accesorios"], "PROHIBIDO USO") == NT.TIPO
    assert NT.tipo_columna(tab["accesorios"], "ACCESORIO") == NT.ACCESORIO
    assert NT.tipo_columna(tab["diametros"], "SOLO SE PERMITE EN") == NT.TEXTO   # nota libre
    assert NT.tipo_columna(tab["electricas"], "ESTRUCTURA") == NT.ESTRUCTURA
    assert NT.tipo_columna(tab["electricas"], "AMPERAJE MIN (A)") == NT.NUMERO
    assert NT.tipo_columna(tab["diametros"], "DIAMETRO (in)") == NT.LISTA
    assert all(nc.ACCESORIOS[nc.clave(a)] for a in nc.NOMBRES_ACCESORIOS)


# ─────────────────────────── ventana ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    from traduccion import i18n, i18n_core
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 0.35, 3.5
    w.pipes = [dict(layer="AGUA", pts=[(100, 100), (600, 100)], tipo="DISTRIBUCION PRINCIPAL", name="",
                    diam=8.0, pipe_size="8 in")]
    w._refresh_lists(); w._redraw()
    w._usar_normas(nc.nuevo())
    w.mensajes = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda _p, _t, msg, *a: w.mensajes.append(msg))
    yield w
    dlg = getattr(w, "_normas_dlg", None)
    if dlg is not None:
        dlg.tablas.sucio = False
        dlg.close()
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _celda(dlg, clave, fila, col, valor):
    w = dlg.tablas.vistas[clave]
    tabla = next(t for t in NT.TABLAS if t.clave == clave)
    w.item(fila, tabla.columnas.index(col)).setText(valor)


def test_editar_guardar_y_validar_en_la_ventana(win):
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    assert not dlg.btn_guardar.isEnabled()
    fila = next(k for k, f in enumerate(NT.filas(win.normas_cat, "diametros"))
                if f[0] == "AGUA" and "6; 8" in f[2])
    _celda(dlg, "diametros", fila, "DIAMETRO (in)", "6; 12; 16")      # el 8" ya no se permite
    assert dlg.tablas.sucio and dlg.btn_guardar.isEnabled()
    assert dlg.guardar()
    assert not dlg.tablas.sucio and not dlg.btn_guardar.isEnabled()
    assert any(a.clase == "diametro" and a.pipe == 0 for a in win._normas_avisos)
    from nucleo import normas_catalogo
    assert normas_catalogo.cargar() == win.normas_cat                  # guardado para todos los proyectos
    # fila nueva con un número mal escrito: no se aplica nada y la celda queda en rojo
    r = dlg.tablas.agregar_fila("electricas")
    _celda(dlg, "electricas", r, "AMPERAJE MIN (A)", ">=400")
    antes = win.normas_cat
    assert not dlg.guardar()
    assert win.normas_cat is antes and win.mensajes and "AMPERAJE MIN (A)" in win.mensajes[-1]
    it = dlg.tablas.vistas["electricas"].item(r, NT.TABLAS[3].columnas.index("AMPERAJE MIN (A)"))
    assert it.toolTip() and it.background().color().red() > 150
    dlg.descartar()
    assert not dlg.tablas.sucio and dlg.tablas.vistas["electricas"].rowCount() == len(win.normas_cat["electricas"])


def test_quitar_filas_y_renombrar_tipo_tambien_en_el_proyecto(win):
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    w = dlg.tablas.vistas["tipos"]
    fila = next(r for r in range(w.rowCount()) if w.item(r, 0).text() == "AGUA"
                and w.item(r, 1).text() == "DISTRIBUCION PRINCIPAL")
    w.item(fila, 1).setText("RED PRINCIPAL")
    assert any(f[0] == "AGUA" and f[1] == "RED PRINCIPAL" for f in dlg.tablas.textos_de("diametros"))
    n = dlg.tablas.vistas["accesorios"].rowCount()
    dlg.tablas.vistas["accesorios"].selectRow(0)
    assert dlg.tablas.quitar_filas("accesorios") == 1
    assert dlg.guardar()
    assert ["AGUA", "RED PRINCIPAL"] in win.normas_cat["tipos"]
    assert ["AGUA", "DISTRIBUCION PRINCIPAL"] not in win.normas_cat["tipos"]
    assert len(win.normas_cat["accesorios"]) == n - 1
    assert win.pipes[0]["tipo"] == "RED PRINCIPAL"                       # la utilidad del proyecto también
    win.undo()
    assert win.pipes[0]["tipo"] == "DISTRIBUCION PRINCIPAL"


def test_desplegables_con_lo_que_decide_la_app(win):
    from PySide6 import QtWidgets
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    w = dlg.tablas.vistas["diametros"]
    deleg = w.itemDelegate()
    util = deleg.createEditor(w.viewport(), QtWidgets.QStyleOptionViewItem(), w.model().index(0, 0))
    assert isinstance(util, QtWidgets.QComboBox)
    assert [util.itemData(k) for k in range(util.count())] == list(nc.UTILIDADES)
    tipo = deleg.createEditor(w.viewport(), QtWidgets.QStyleOptionViewItem(), w.model().index(0, 1))
    tipos = [tipo.itemData(k) for k in range(tipo.count())]
    assert tipos[0] == "" and set(tipos[1:]) == set(nc.tipos_de(win.normas_cat, w.item(0, 0).text()))
    nota = deleg.createEditor(w.viewport(), QtWidgets.QStyleOptionViewItem(), w.model().index(0, 5))
    assert not isinstance(nota, QtWidgets.QComboBox)                       # texto libre


def test_no_pierde_cambios_al_redibujar_ni_un_tipo_del_panel(win):
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    _celda(dlg, "diametros", 0, "SOLO SE PERMITE EN", "NOTA NUEVA")
    nc.agregar_tipo(win.normas_cat, "GAS", "ALTA PRESION")             # como el «+» del panel
    win._redraw(); dlg.refrescar()
    assert dlg.tablas.sucio and "NOTA NUEVA" in dlg.tablas.textos_de("diametros")[0]
    assert dlg.guardar()
    assert ["GAS", "ALTA PRESION"] in win.normas_cat["tipos"]
    assert win.normas_cat["diametros"][0]["nota"] == "NOTA NUEVA"
