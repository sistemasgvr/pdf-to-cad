"""Normativas en tablas (formato del Excel del usuario, 2026-10-09): catálogo, Excel
(ida y vuelta con desplegables), validación de utilidades y accesorios, tabla de datos
y la ventana real (Tipo + «+», Ver → Avisos, ventanas)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import normas_catalogo as nc  # noqa: E402
from nucleo import normas_excel, normas_validar as nv  # noqa: E402

FT = 0.1


def _p(layer="AGUA", tipo="", diam=None, pts=((0, 0), (100, 0)), **k):
    d = dict(layer=layer, pts=[tuple(q) for q in pts], tipo=tipo, name="")
    if diam is not None:
        d.update(diam=float(diam), pipe_size=f"{diam:g} in")
    d.update(k)
    return d


# ─────────────────────────── catálogo y Excel ───────────────────────────

def test_lectura_de_celdas():
    assert nc.lista_numeros("6; 8; 12; 16") == [6, 8, 12, 16]
    assert nc.lista_numeros("1;1,5;2") == [1, 1.5, 2]
    assert nc.lista_numeros(4) == [4]
    assert nc.rango("0-320") == [0, 320] and nc.rango("101-200") == [101, 200] and nc.rango(None) is None
    assert nc.texto_lista([11.25, 22.5]) == "11,25; 22,5"
    assert nc.mismo("Instalación  domiciliaria", "INSTALACION DOMICILIARIA")


def test_tipos_y_agregar_tipo():
    cat = nc.nuevo()
    assert nc.tipos_de(cat, "AGUA") == ["DISTRIBUCION PRINCIPAL", "ALIMENTACION Y CONDUCCION",
                                         "INSTALACION DOMICILIARIA"]
    assert nc.tipos_de(cat, "GAS") == []
    assert nc.agregar_tipo(cat, "GAS", "Distribución  secundaria") == "DISTRIBUCION SECUNDARIA"
    nc.agregar_tipo(cat, "GAS", "distribucion secundaria")              # repetido: no se duplica
    assert nc.tipos_de(cat, "GAS") == ["DISTRIBUCION SECUNDARIA"]


def test_guardar_y_cargar():
    cat = nc.nuevo()
    nc.agregar_tipo(cat, "TELECOM", "FIBRA")
    nc.guardar(cat)
    assert nc.tipos_de(nc.cargar(), "TELECOM") == ["FIBRA"]


def test_excel_ida_y_vuelta_con_desplegables(tmp_path):
    import openpyxl
    cat = nc.nuevo()
    nc.agregar_tipo(cat, "ELECTRICO", "ALUMBRADO")
    ruta = tmp_path / "normas.xlsx"
    normas_excel.exportar(cat, ruta)
    leido, faltan = normas_excel.importar(ruta)
    assert not faltan and leido == nc.normalizar(cat)
    wb = openpyxl.load_workbook(ruta)
    assert wb.sheetnames == ["TIPOS", "PRESION-DIAMETROS", "PRESION-ACCESORIOS", "ELECT-TELECOM"]
    assert "TablaTipos" in wb["TIPOS"].tables
    dvs = {str(dv.sqref): dv.formula1 for dv in wb["PRESION-DIAMETROS"].data_validations.dataValidation}
    assert "TIPOS!$K$1:$P$1" in dvs["A2:A500"] and "OFFSET(TIPOS!$K$2" in dvs["B2:B500"]
    assert wb["TIPOS"].column_dimensions["K"].hidden


def test_excel_con_hoja_que_falta_y_tipos_sumados(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PRESION-DIAMETROS"
    ws.append(["UTILIDAD", "TIPO", "DIAMETRO (in)", "SOLO SE PERMITE EN"])
    ws.append(["AGUA", "RIEGO", "2; 3", None])
    ruta = tmp_path / "x.xlsx"
    wb.save(ruta)
    cat, faltan = normas_excel.importar(ruta)
    assert "TIPOS" in faltan and nc.tipos_de(cat, "AGUA") == ["RIEGO"]   # el tipo de la tabla entra solo
    assert cat["diametros"][0]["diametros"] == [2, 3]


# ─────────────────────────── validación de utilidades ───────────────────────────

def _avisos(pipes, accs=()):
    return nv.validar(nc.nuevo(), pipes, list(accs), FT)


def test_sin_tipo_y_diametros_del_tipo():
    av = _avisos([_p(tipo=""), _p(tipo="DISTRIBUCION PRINCIPAL", diam=2), _p(tipo="DISTRIBUCION PRINCIPAL", diam=10),
                  _p(tipo="DISTRIBUCION PRINCIPAL", diam=8), _p(tipo="DISTRIBUCION PRINCIPAL", diam=4)])
    por = {}
    for a in av:
        por.setdefault(a.pipe, []).append(a)
    assert [a.clase for a in por[0]] == ["tipo"]
    assert "INSTALACION DOMICILIARIA" in por[1][0].mensaje                 # es de otro tipo
    assert "no permitido" in por[2][0].mensaje
    assert 3 not in por                                                     # 8" en principal: cumple
    assert por[4][0].info and "cul-de-sacs" in por[4][0].mensaje            # nota propia: informativo


def test_nota_que_repite_el_tipo_en_plural_no_avisa():
    # «INSTALACIONES DOMICILIARIAS» (nota del Excel) = el tipo «INSTALACION DOMICILIARIA».
    for t_, d in (("INSTALACION DOMICILIARIA", 1.5), ("ALIMENTACION Y CONDUCCION", 20),
                  ("DISTRIBUCION PRINCIPAL", 8)):
        assert _avisos([_p(tipo=t_, diam=d)]) == [], t_


def test_electrico_por_amperaje_y_largo():
    dom = "INSTALACION DOMICILIARIA"
    largo = [(0, 0), (1500, 0)]                                             # 150 ft
    av = _avisos([_p("ELECTRICO", dom, 3, largo), _p("ELECTRICO", dom, 3, largo, amperaje=350),
                  _p("ELECTRICO", dom, 4, largo, amperaje=350), _p("ELECTRICO", "DISTRIBUCION PRINCIPAL", 2),
                  _p("TELECOM", "", 2), _p("TELECOM", "", 4)])
    msgs = {a.pipe: a.mensaje for a in av}
    assert "amperaje" in msgs[0].lower()
    assert "4" in msgs[1] and "321-400 A" in msgs[1]
    assert 2 not in msgs and 5 not in msgs
    assert "mínimo 3" in msgs[3] and "mínimo 4" in msgs[4]


def test_electrico_con_bancoducto_no_se_revisa():
    av = nv.validar(nc.nuevo(), [_p("TELECOM", "", 2)], [], FT, con_bancoducto={0})
    assert not av


# ─────────────────────────── accesorios ───────────────────────────

def _acc(tipo, capa="AGUA", tronco=(0,), ramal=None, angulo=90.0):
    return {"x": 0.0, "y": 0.0, "tipo": tipo, "angulo": angulo, "capa": capa, "red": capa,
            "pipes": sorted(set(tronco) | ({ramal} if ramal is not None else set())),
            "tronco": list(tronco), "ramal": ramal}


@pytest.mark.parametrize("d_tronco,d_ramal,esperado", [
    (12, 8, None), (12, 6, "debe ser 8"), (6, 4, "no hay un tamaño menor")])
def test_tee_ramal_un_tamano_menor(d_tronco, d_ramal, esperado):
    dp = "DISTRIBUCION PRINCIPAL"
    pipes = [_p(tipo=dp, diam=d_tronco), _p(tipo=dp, diam=d_ramal)]
    av = [a for a in _avisos(pipes, [_acc("tee", ramal=1)]) if a.clase == "accesorio"]
    if esperado is None:
        assert not av
    else:
        assert len(av) == 1 and esperado in av[0].mensaje


def test_tee_domiciliaria_solo_mira_el_ramal():
    pipes = [_p(tipo="DISTRIBUCION PRINCIPAL", diam=8), _p(tipo="INSTALACION DOMICILIARIA", diam=1),
             _p(tipo="INSTALACION DOMICILIARIA", diam=3)]
    assert not [a for a in _avisos(pipes, [_acc("tee", ramal=1)]) if a.clase == "accesorio"]
    av = [a for a in _avisos(pipes, [_acc("tee", ramal=2)]) if a.clase == "accesorio"]
    assert len(av) == 1 and "T domiciliaria" in av[0].mensaje


def test_wye_cruz_y_codos():
    dp, dom = "DISTRIBUCION PRINCIPAL", "INSTALACION DOMICILIARIA"
    pipes = [_p(tipo=dp, diam=12), _p(tipo=dom, diam=1), _p("GAS", "", 4)]
    av = lambda a: [x.mensaje for x in _avisos(pipes, [a]) if x.clase == "accesorio"]  # noqa: E731
    assert av(_acc("wye", ramal=0, tronco=(0,))) and "no permitida" in av(_acc("wye", ramal=0, tronco=(0,)))[0]
    assert "6\", 8\"" in av(_acc("cruz"))[0]                                 # principal de 12": no
    assert av(_acc("codo", angulo=30.0)) and not av(_acc("codo", angulo=45.2))
    assert not av(_acc("codo", tronco=(1,), angulo=30.0))                    # domiciliaria: cualquier ángulo
    assert av(_acc("codo", capa="GAS", tronco=(2,), angulo=30.0))


def test_tee_real_desde_la_geometria():
    """Ramal que nace a mitad de la principal: `accesorios` dice cuál es el ramal."""
    from nucleo import accesorios
    dp = "DISTRIBUCION PRINCIPAL"
    pipes = [_p(tipo=dp, diam=12, pts=[(0, 0), (200, 0)]), _p(tipo=dp, diam=6, pts=[(100, 0), (100, 150)])]
    accs = accesorios.accesorios(pipes, None, FT)
    assert [(a["tipo"], a["ramal"], a["tronco"]) for a in accs] == [("tee", 1, [0])]
    av = [a for a in nv.validar(nc.nuevo(), pipes, accs, FT) if a.clase == "accesorio"]
    assert len(av) == 1 and "debe ser 8" in av[0].mensaje


# ─────────────────────────── tabla de datos ───────────────────────────

def test_tabla_de_datos_y_excel(tmp_path):
    import openpyxl
    from nucleo import tabla_datos
    from nucleo.duct_bank import DuctBank
    pipes = [_p(tipo="DISTRIBUCION PRINCIPAL", diam=8), _p("ELECTRICO", "", pts=[(0, 50), (300, 50)])]
    structs = [{"cod": "BZ-1", "x": 0.0, "y": 0.0, "net": "gravity", "rim": 100.0, "sump": 95.0},
               {"cod": "CV-1", "x": 300.0, "y": 50.0, "curve": True, "radius_ft": 5.0}]
    db = DuctBank(name="DB1"); db.assign([1])
    av = nv.validar(nc.nuevo(), pipes, [], FT)
    tablas = tabla_datos.armar(pipes, structs, [db], av, lambda x, y: (x * FT, -y * FT), FT)
    ut, bz, cu, bd, avs = tablas
    assert [f[0] for f in ut.filas] == [1, 2] and ut.filas[0][3] == "DISTRIBUCION PRINCIPAL"
    assert ut.filas[0][8] == pytest.approx(10.0) and ut.filas[1][14] == "DB1"
    assert [f[0] for f in bz.filas] == ["BZ-1"] and len(cu.filas) == 1 and len(bd.filas) == 1
    assert len(avs.filas) == 1                                               # la eléctrica sin tipo
    ruta = tmp_path / "datos.xlsx"
    tabla_datos.exportar_excel(tablas, ruta)
    wb = openpyxl.load_workbook(ruta)
    assert len(wb.sheetnames) == 5 and wb.worksheets[0].max_row == 3


# ─────────────────────────── ventana ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    from traduccion import i18n, i18n_core
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 0.35, 3.5
    w.pipes = [_p("AGUA", "", 8, pts=[(100, 100), (600, 100)]), _p("ELECTRICO", "", pts=[(100, 300), (600, 300)])]
    w._refresh_lists(); w._redraw()
    w.avisos = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda _p, _t, msg, *a: w.avisos.append(msg))
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_ventana_tipo_avisos_y_mas(win, monkeypatch):
    from PySide6 import QtWidgets
    assert sum(1 for a in win._normas_avisos if a.clase == "tipo") == 2
    assert win.btn_normas.isVisibleTo(win) or win.btn_normas.text()
    win._show_tab(0); win.pipe_list.setCurrentRow(0)
    assert [win.prop_tipo.itemText(k) for k in range(win.prop_tipo.count())][1:] == nc.tipos_de(nc.nuevo(), "AGUA")
    assert not win.prop_amp.isVisibleTo(win.gprop)
    win.prop_tipo.setCurrentIndex(win.prop_tipo.findData("DISTRIBUCION PRINCIPAL"))
    assert win.pipes[0]["tipo"] == "DISTRIBUCION PRINCIPAL"
    assert not [a for a in win._normas_avisos if a.pipe == 0]
    # «+»: tipo nuevo, guardado en las normativas y elegido
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Riego", True))
    win._agregar_tipo()
    assert win.pipes[0]["tipo"] == "RIEGO" and "RIEGO" in nc.tipos_de(nc.cargar(), "AGUA")
    win.undo()
    assert win.pipes[0]["tipo"] == "DISTRIBUCION PRINCIPAL"


def test_ver_avisos_y_ventanas(win):
    win._mostrar_avisos(False)
    assert not (win.chk_show_conflicts.isChecked() or win.act_show_acc.isChecked() or win.act_show_normas.isChecked())
    win._mostrar_avisos(True)
    assert [a.text() for a in win.menu_avisos.actions() if a.text()][-2:] == ["Mostrar todos", "Ocultar todos"]
    win.open_normativas(en_avisos=True)
    assert win._normas_dlg.lst_avisos.topLevelItemCount() == 2
    win.abrir_tabla_datos()
    assert win._tabla_dlg.pestanas.count() == 5
    win._tabla_dlg.close(); win._normas_dlg.close()
