"""Avisos de normativa APROBADOS (quedan registrados, ya no se marcan) y Excel de la
Tabla de datos con la SECCIÓN de cada utilidad (estado, familia, tamaño o diámetro,
material) de ida y vuelta."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import normas_aprobacion as na  # noqa: E402
from nucleo import tabla_excel  # noqa: E402
from nucleo.normas_validar import Aviso  # noqa: E402

ESC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escenarios", "cruces", "escenarios_prueba.digproj")


# ─────────────────────────── puro ───────────────────────────

def test_aprobar_marcar_y_registro():
    pipes = [dict(layer="AGUA", tipo="DP", pipe_size="12 in"), dict(layer="AGUA", tipo="DP", pipe_size="8 in")]
    av = [Aviso(10, 20, "diametro", "Diámetro 12 in: debe ser 8 in.", 0),
          Aviso(50, 60, "diametro", "Diámetro 8 in…", 1), Aviso(5, 5, "tipo", "info", 1, info=True)]
    reg = []
    assert na.aprobar(reg, av, pipes, "Lo pidió el cliente", usuario="ana") == 2      # la informativa no
    assert reg[0]["nota"] == "Lo pidió el cliente" and reg[0]["usuario"] == "ana" and reg[0]["fecha"]
    assert na.pendientes(av) == []
    # otra vez (se recalculan los avisos): el registro los vuelve a marcar
    nuevos = [Aviso(10.4, 20.3, "diametro", "x", 0), Aviso(50, 60, "diametro", "x", 1)]
    assert na.marcar(nuevos, pipes, reg) == [] and all(a.aprobado for a in nuevos)
    # cambia lo que la normativa revisa (otro tamaño): vuelve a quedar pendiente; el registro queda «viejo»
    pipes[0]["pipe_size"] = "16 in"
    viejos = na.marcar(nuevos, pipes, reg)
    assert nuevos[0].aprobado is None and nuevos[1].aprobado and len(viejos) == 1
    assert na.quitar(reg, [nuevos[1]], pipes) == 1 and len(reg) == 1


def test_reindexar_al_borrar_una_utilidad():
    pipes = [dict(layer="A"), dict(layer="A"), dict(layer="A")]
    av = [Aviso(0, 0, "tipo", "m", 0), Aviso(9, 9, "tipo", "m", 2)]
    reg = []
    na.aprobar(reg, av, pipes, usuario="")
    na.reindexar(reg, 1)
    del pipes[1]
    a = Aviso(9, 9, "tipo", "m", 1)
    na.marcar([a], pipes, reg)
    assert a.aprobado and len(reg) == 2
    na.reindexar(reg, 0)
    assert [r["utilidad"] for r in reg] == [0]


def test_seccion_desde_el_excel_con_catalogo():
    pipes = [dict(layer="AGUA", pipe_family="", pipe_size="", diam=12.0),
             dict(layer="AGUA", pipe_family="F1", pipe_size="8 in", diam=8.0)]
    fams = [("F1", {"Familia uno"}), ("F2", {"Familia dos"})]
    cat = lambda p: (fams, lambda f: ["6 in", "8 in", "12 in"] if f else [])  # noqa: E731
    leido = {"utilidades": [
        {"N°": 1, "Estado": "Abandonada", "Familia": "Familia dos", "Tamaño": "Por defecto", "Diámetro (in)": 12},
        {"N°": 2, "Estado": "Activa", "Familia": "Familia uno", "Tamaño": "8 in", "Diámetro (in)": "6"}]}
    cambios, errores = tabla_excel.cambios(pipes, [], leido, catalogo=cat)
    assert not errores
    assert {(c.indice, c.campo, c.despues) for c in cambios} == {
        (0, "ab", True), (0, "pipe_family", "F2"), (0, "pipe_size", "12 in"), (1, "pipe_size", "6 in")}
    assert any("Familia dos" in tabla_excel.texto(c) for c in cambios)          # el nombre, no el id
    # familia nueva sin decir tamaño: conserva el diámetro si esa familia lo tiene
    tabla_excel.aplicar(pipes, [], cambios)
    assert pipes[0]["ab"] and pipes[0]["pipe_family"] == "F2" and pipes[1]["pipe_size"] == "6 in"
    assert pipes[1]["diam"] == 6.0                                                # el diámetro sale del tamaño
    # lo que no existe en el catálogo no se aplica, y con bancoducto la sección no se toca
    malo = {"utilidades": [{"N°": 2, "Familia": "Otra"}, {"N°": 2, "Diámetro (in)": 7},
                           {"N°": 1, "Estado": "rota"}]}
    cambios, errores = tabla_excel.cambios(pipes, [], malo, catalogo=cat)
    assert not cambios and len(errores) == 3
    cambios, errores = tabla_excel.cambios(pipes, [], {"utilidades": [{"N°": 2, "Tamaño": "12 in"}]},
                                           catalogo=cat, con_bancoducto={1})
    assert not cambios and "bancoducto" in errores[0]


# ─────────────────────────── en la ventana ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    w._redraw()
    yield w
    for d in ("_tabla_dlg", "_normas_dlg"):
        if getattr(w, d, None) is not None:
            getattr(w, d).close()
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_aprobar_avisos_en_la_ventana_queda_registrado(win, tmp_path):
    from ui.dialogos import normas_dialog
    total = len(na.pendientes(win._normas_avisos))
    dlg = normas_dialog.abrir(win, en_avisos=True)
    items = [dlg.lst_avisos.topLevelItem(k) for k in range(3)]
    for it in items:
        it.setSelected(True)
    assert dlg.btn_aprobar.isEnabled() and not dlg.btn_quitar.isEnabled()
    assert dlg.aprobar(nota="Revisado con el ingeniero") == 3
    assert len(na.pendientes(win._normas_avisos)) == total - 3
    assert win.btn_normas.text().startswith("⚠ ") and str(total - 3) in win.btn_normas.text()
    aprobados = [a for a in win._normas_avisos if a.aprobado]
    assert len(aprobados) == 3 and aprobados[0].aprobado["nota"] == "Revisado con el ingeniero"
    # la Tabla de datos lo registra (estado, quién, cuándo, nota)
    tb = next(t for t in win._tablas_de_datos() if t.clave == "avisos")
    col = tb.columnas.index("Estado")
    assert sum(1 for f in tb.filas if f[col] == "Aprobado") == 3
    assert any(f[tb.columnas.index("Nota")] == "Revisado con el ingeniero" for f in tb.filas)
    # se guarda en el proyecto y vuelve al abrirlo
    ruta = str(tmp_path / "p.digproj")
    win._write_project(ruta)
    win._open_project_path(ruta); win._redraw()
    assert len(win.normas_aprobados) == 3 and sum(1 for a in win._normas_avisos if a.aprobado) == 3
    # Ctrl+Z quita la aprobación; cambiar la utilidad la invalida (vuelve a pendiente, registro «ya no aplica»)
    i = next(a.pipe for a in win._normas_avisos if a.aprobado)
    win._push(); win.pipes[i]["tipo"] = "OTRO"; win.pipes[i]["pipe_size"] = "99 in"; win._redraw()
    assert sum(1 for a in win._normas_avisos if a.aprobado) < 3
    dlg = normas_dialog.abrir(win, en_avisos=True)
    assert dlg._registros_viejos()
    win.undo()
    assert sum(1 for a in win._normas_avisos if a.aprobado) == 3


def test_quitar_aprobacion(win):
    from ui.dialogos import normas_dialog
    av = na.pendientes(win._normas_avisos)[:2]
    win.aprobar_avisos(av, "")
    dlg = normas_dialog.abrir(win, en_avisos=True)
    for k in range(dlg.lst_avisos.topLevelItemCount()):
        it = dlg.lst_avisos.topLevelItem(k)
        n = it.data(0, normas_dialog._ROL)
        it.setSelected(n is not None and win._normas_avisos[n].aprobado is not None)
    assert dlg.btn_quitar.isEnabled()
    assert dlg.quitar_aprobacion() == 2 and not win.normas_aprobados


def test_excel_seccion_en_la_ventana(win, tmp_path, monkeypatch):
    import openpyxl
    from ui.dialogos import tabla_datos_dialog
    fams = [("FAM|A", {"Familia A", "A"})]       # «A» = como la muestra la tabla (presión: sin subcarpeta)
    monkeypatch.setattr(win, "_catalogo_excel", lambda: (lambda p: (fams, lambda f: ["8 in", "12 in", "16 in"]
                                                                    if f else [])))
    dlg = tabla_datos_dialog.abrir(win)
    ruta = str(tmp_path / "datos.xlsx")
    tabla_excel.exportar(dlg.tablas, ruta)
    wb = openpyxl.load_workbook(ruta)
    ws = wb["Utilidades"]
    cab = [c.value for c in ws[1]]
    for col in ("Estado", "Familia", "Tamaño", "Diámetro (in)", "Material"):         # editables (verdes)
        assert ws.cell(row=1, column=cab.index(col) + 1).fill.fgColor.rgb.endswith(tabla_excel.VERDE)
    c = lambda nombre: cab.index(nombre) + 1  # noqa: E731
    ws.cell(row=2, column=c("Estado")).value = "Abandonada"
    ws.cell(row=2, column=c("Familia")).value = "Familia A"
    ws.cell(row=2, column=c("Diámetro (in)")).value = 16
    ws.cell(row=3, column=c("Material")).value = "PVC"
    wb.save(ruta)
    antes = dict(win.pipes[0])
    aplicados = dlg.importar(ruta, confirmar=False)
    assert {(x.indice, x.campo) for x in aplicados} == {
        (0, "ab"), (0, "pipe_family"), (0, "pipe_size"), (1, "material")}
    p = win.pipes[0]
    assert p["ab"] and p["pipe_family"] == "FAM|A" and p["pipe_size"] == "16 in" and p["diam"] == 16.0
    assert win.pipes[1]["material"] == "PVC"
    # volver a exportar lo aplicado = sin cambios
    dlg.refrescar()
    tabla_excel.exportar(dlg.tablas, ruta)
    assert tabla_excel.cambios(win.pipes, win.structures, tabla_excel.importar(ruta),
                               catalogo=win._catalogo_excel()) == ([], [])
    win.undo()
    assert win.pipes[0].get("pipe_family") == antes.get("pipe_family") and not win.pipes[0].get("ab")
