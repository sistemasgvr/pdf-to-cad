"""Normativas editables desde la aplicación (pedidos del usuario 2026-10-20 y 10-21: «la aplicación manda en
todo», una sola tabla de reglas): tablas de texto ida y vuelta, las mismas reglas que el Excel, desplegables que
dependen de la fila, renombrar un tipo y la ventana real."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import model  # noqa: E402
from nucleo import normas_catalogo as nc  # noqa: E402
from nucleo import normas_reglas as NR  # noqa: E402
from nucleo import normas_tablas as NT  # noqa: E402


def _textos(cat):
    return {t.clave: NT.filas(cat, t.clave) for t in NT.TABLAS}


def _fila(**k):
    f = ["SI"] + [""] * (len(NR.COLUMNAS) - 1)
    for col, v in k.items():
        f[NR.COLUMNAS.index(col if col in NR.COLUMNAS else col.replace("_", " "))] = v
    return f


def test_las_utilidades_son_las_de_la_aplicacion():
    assert nc.UTILIDADES == tuple(c for _n, c in model.TIPOS)


def test_tablas_de_texto_ida_y_vuelta_igual_que_el_catalogo():
    cat = nc.nuevo()
    vuelta, problemas = NT.catalogo(_textos(cat))
    assert problemas == []
    assert vuelta == nc.normalizar(cat)


def test_la_aplicacion_manda_utilidad_tipo_elemento_revisar_y_numeros():
    t = _textos(nc.nuevo())
    n = len(t["reglas"])
    t["tipos"].append(["AGUA POTABLE", "PRINCIPAL"])                               # utilidad que la app no tiene
    t["reglas"] += [
        _fila(UTILIDAD="AGUA", TIPO="TIPO INVENTADO", ELEMENTO="TUBERIA", REVISAR="Diámetro (in)", MIN="4"),
        _fila(UTILIDAD="AGUA", ELEMENTO="BUZON", REVISAR="Distancia entre buzones (ft)", MAX="400"),
        _fila(UTILIDAD="AGUA", ELEMENTO="VALVULA", REVISAR="Diámetro (in)", MIN="4"),
        _fila(UTILIDAD="AGUA", ELEMENTO="TUBERIA", REVISAR="Velocidad (fps)", MIN="3"),
        _fila(UTILIDAD="AGUA", ELEMENTO="TUBERIA", REVISAR="Diámetro (in)", MIN="cuatro"),
        _fila(UTILIDAD="AGUA", ELEMENTO="TUBERIA", REVISAR="Separación vertical en el cruce (ft)", MIN="1"),
        _fila(UTILIDAD="GAS", ELEMENTO="TUBERIA", REVISAR="Diámetro (in)", MIN="4", **{"SI AMPERAJE MIN (A)": "0"}),
        _fila(UTILIDAD="AGUA", ELEMENTO="CODO", REVISAR="Ángulo (°)"),
    ]
    cat, problemas = NT.catalogo(t)
    cols = {(f - n, col) for c, f, col, _m in problemas if c == "reglas"}
    assert ("tipos", "UTILIDAD") in {(c, col) for c, _f, col, _m in problemas}
    assert {(0, "TIPO"), (1, "ELEMENTO"), (2, "ELEMENTO"), (3, "REVISAR"), (4, "MIN"), (5, "CON UTILIDAD"),
            (7, "VALORES")} <= cols
    assert len(cat["reglas"]) == n and ["AGUA POTABLE", "PRINCIPAL"] not in cat["tipos"]


def test_opciones_que_dependen_de_la_fila():
    tipos = _textos(nc.nuevo())["tipos"]
    elem = [v for v, _a in NT.opciones("ELEMENTO", _fila(UTILIDAD="ALCANTARILLADO"), tipos)]
    assert elem == ["TUBERIA", "CURVA", "BUZON"]                                     # gravedad: sin accesorios
    assert "T - DOMICILIARIA" in [v for v, _a in NT.opciones("ELEMENTO", _fila(UTILIDAD="AGUA"), tipos)]
    rev = [v for v, _a in NT.opciones("REVISAR", _fila(UTILIDAD="AGUA", ELEMENTO="CODO"), tipos)]
    assert "Ángulo (°)" in rev and "Diámetro (in)" not in rev
    rev = [v for v, _a in NT.opciones("REVISAR", _fila(UTILIDAD="ELECTRICO", ELEMENTO="TUBERIA"), tipos)]
    assert "Amperaje (A)" in rev and "Pendiente (%)" in rev and "Quiebre sin buzón (°)" not in rev
    tp = [v for v, _a in NT.opciones("TIPO", _fila(UTILIDAD="AGUA"), tipos)]
    assert tp[0] == "" and set(tp[1:]) == set(nc.tipos_de(nc.nuevo(), "AGUA"))
    assert [v for v, _a in NT.opciones("VALORES", _fila(UTILIDAD="AGUA", REVISAR="Se permite"), tipos)] == ["SI", "NO"]
    assert NT.opciones("VALORES", _fila(UTILIDAD="AGUA", REVISAR="Diámetro (in)"), tipos) is None
    assert NT.opciones("NOTA", _fila(UTILIDAD="AGUA"), tipos) is None


def test_renombrar_un_tipo_lo_cambia_en_las_reglas():
    t = _textos(nc.nuevo())
    n = NT.renombrar_tipo(t, "AGUA", "DISTRIBUCION PRINCIPAL", "RED PRINCIPAL")
    assert n > 0
    k_u, k_t, k_v = (NR.COLUMNAS.index(c) for c in ("UTILIDAD", "TIPO", "VALORES"))
    assert not any(f[k_u] == "AGUA" and (f[k_t] == "DISTRIBUCION PRINCIPAL" or "DISTRIBUCION PRINCIPAL" in f[k_v])
                   for f in t["reglas"])
    assert any(f[k_u] == "AGUA" and "RED PRINCIPAL" in f[k_v] for f in t["reglas"])   # «Solo en tipos» también
    assert any(f[k_u] == "GAS" and f[k_t] == "DISTRIBUCION PRINCIPAL" for f in t["reglas"])   # otra utilidad no


def test_frase_de_una_regla():
    txt = NT.frase(_fila(UTILIDAD="ALCANTARILLADO", TIPO="COLECTOR", ELEMENTO="TUBERIA", REVISAR="Pendiente (%)",
                         MIN="0,44", FUENTE="F200"))
    assert txt.startswith("En ALCANTARILLADO · COLECTOR, TUBERIA") and "mínimo 0,44 %" in txt and "F200" in txt


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


def _fila_de(win, **k):
    return next(n for n, r in enumerate(win.normas_cat["reglas"]) if all(r.get(c) == v for c, v in k.items()))


def test_editar_guardar_y_validar_en_la_ventana(win):
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    assert not dlg.btn_guardar.isEnabled()
    fila = _fila_de(win, utilidad="AGUA", tipo="DISTRIBUCION PRINCIPAL", revisar="diametro", valores=[6, 8, 12, 16])
    _celda(dlg, "reglas", fila, "VALORES", "6; 12; 16")                  # el 8" ya no se permite
    assert dlg.tablas.sucio and dlg.btn_guardar.isEnabled()
    assert dlg.guardar()
    assert not dlg.tablas.sucio and not dlg.btn_guardar.isEnabled()
    assert any(a.clase == "diametro" and a.pipe == 0 for a in win._normas_avisos)
    assert nc.cargar() == win.normas_cat                                # guardado para todos los proyectos
    r = dlg.tablas.agregar_fila("reglas")
    _celda(dlg, "reglas", r, "REVISAR", "Diámetro (in)")
    _celda(dlg, "reglas", r, "MIN", ">=400")
    antes = win.normas_cat
    assert not dlg.guardar()
    assert win.normas_cat is antes and win.mensajes and "MIN" in win.mensajes[-1]
    it = dlg.tablas.vistas["reglas"].item(r, NR.COLUMNAS.index("MIN"))
    assert it.toolTip() and it.background().color().red() > 150
    dlg.descartar()
    assert not dlg.tablas.sucio and dlg.tablas.vistas["reglas"].rowCount() == len(win.normas_cat["reglas"])


def test_quitar_filas_y_renombrar_tipo_tambien_en_el_proyecto(win):
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    w = dlg.tablas.vistas["tipos"]
    fila = next(r for r in range(w.rowCount()) if w.item(r, 0).text() == "AGUA"
                and w.item(r, 1).text() == "DISTRIBUCION PRINCIPAL")
    w.item(fila, 1).setText("RED PRINCIPAL")
    k_t = NR.COLUMNAS.index("TIPO")
    assert any(f[k_t] == "RED PRINCIPAL" for f in dlg.tablas.textos_de("reglas"))
    n = dlg.tablas.vistas["reglas"].rowCount()
    dlg.tablas.vistas["reglas"].selectRow(0)
    assert dlg.tablas.quitar_filas("reglas") == 1
    assert dlg.guardar()
    assert ["AGUA", "RED PRINCIPAL"] in win.normas_cat["tipos"]
    assert ["AGUA", "DISTRIBUCION PRINCIPAL"] not in win.normas_cat["tipos"]
    assert len(win.normas_cat["reglas"]) == n - 1
    assert win.pipes[0]["tipo"] == "RED PRINCIPAL"                       # la utilidad del proyecto también
    win.undo()
    assert win.pipes[0]["tipo"] == "DISTRIBUCION PRINCIPAL"


def test_desplegables_con_lo_que_decide_la_app(win):
    from PySide6 import QtWidgets
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    w = dlg.tablas.vistas["reglas"]
    deleg = w.itemDelegate()
    fila = _fila_de(win, utilidad="AGUA", elemento="CODO")

    def editor(col):
        return deleg.createEditor(w.viewport(), QtWidgets.QStyleOptionViewItem(),
                                  w.model().index(fila, NR.COLUMNAS.index(col)))
    util = editor("UTILIDAD")
    assert isinstance(util, QtWidgets.QComboBox) and [util.itemData(k) for k in range(util.count())] == list(nc.UTILIDADES)
    rev = editor("REVISAR")
    assert "Ángulo (°)" in [rev.itemData(k) for k in range(rev.count())]
    assert "Distancia entre buzones (ft)" not in [rev.itemData(k) for k in range(rev.count())]
    assert not isinstance(editor("NOTA"), QtWidgets.QComboBox)                # texto libre
    assert not isinstance(editor("MIN"), QtWidgets.QComboBox)
    dlg.tablas.filtro.setCurrentIndex(dlg.tablas.filtro.findData("GAS"))
    k_u = NR.COLUMNAS.index("UTILIDAD")
    visibles = {w.item(r, k_u).text() for r in range(w.rowCount()) if not w.isRowHidden(r)}
    assert visibles == {"GAS"}
    assert w.item(fila, 0).toolTip().startswith("En AGUA")                   # la fila leída como frase


def test_no_pierde_cambios_al_redibujar_ni_un_tipo_del_panel(win):
    from ui.dialogos import normas_dialog
    dlg = normas_dialog.abrir(win)
    _celda(dlg, "reglas", 0, "NOTA", "NOTA NUEVA")
    nc.agregar_tipo(win.normas_cat, "GAS", "ALTA PRESION")             # como el «+» del panel
    win._redraw(); dlg.refrescar()
    assert dlg.tablas.sucio and "NOTA NUEVA" in dlg.tablas.textos_de("reglas")[0]
    assert dlg.guardar()
    assert ["GAS", "ALTA PRESION"] in win.normas_cat["tipos"]
    assert win.normas_cat["reglas"][0]["nota"] == "NOTA NUEVA"
