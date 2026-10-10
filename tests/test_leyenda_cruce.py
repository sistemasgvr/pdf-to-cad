"""«Leyenda de esta hoja» con la leyenda DEL PDF (2.º reporte del usuario, 2026-10-07).

DU08 h.26, filtrando solo eléctrico: al hacer clic en «EXISTING ELECTRICAL» solo se
marcaban dos líneas «e»; las muchas «E», «TE» y «SE» de la hoja (eléctricas según la
misma leyenda) no se marcaban con nada, y quedaba la duda de por qué «SE»/«TE» salen con
eléctrico. Ahora la leyenda va POR UTILIDAD en todas las utilidades: cada tipo de línea
de la hoja con la descripción del PDF que le corresponde (existente «e», a abandonar
«e //», propuesta «E», «TE», «SE», aérea «e(oh)» que no se reconoce) y el clic en la
utilidad marca todas sus líneas, mayúscula o minúscula.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from hoja import leyenda_cruce as cruce  # noqa: E402
from hoja import leyenda_estandar as le  # noqa: E402

DU08 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")
needs_du08 = pytest.mark.skipif(not DU08.exists(), reason="PDF de prueba DU08 no disponible")


def _row(text, raw="", code=None, overhead=False):
    return SimpleNamespace(text=text, raw=raw, code=code if code is not None else raw.split("(")[0].upper(),
                           overhead=overhead)


# Filas de la leyenda de DU08 h.3 (las que importan aquí)
ROWS = [_row("EXISTING ABANDONED ELECTRICAL", "e"), _row("EXISTING ELECTRICAL", "e"),
        _row("EXISTING ELECTRICAL - TO BE ABANDONED", "e"),
        _row("EXISTING OVERHEAD ELECTRICAL", "e(oh)", "E", True),
        _row("EXISTING OVERHEAD ELECTRICAL - TO BE ABANONDED", "e(oh)", "E", True),
        _row("EXISTING GAS", "g"), _row("EXISTING WATER", "W"), _row("EXISTING WATER - TO BE ABANDONED", "w"),
        _row("PROPOSED ELECTRICAL", "E"), _row("PROPOSED GAS", "G"), _row("PROPOSED SANITARY SEWER", "SS"),
        _row("PROPOSED STORM DRAIN", "", ""), _row("PROPOSED WATER", "W"),
        _row("PROPOSED SYSTEM ELECTRICAL DUCTBANK (METRO SYSTEMS)", "SE"),
        _row("PROPOSED TRACK ELECTRIFICATION DUCTBANK (METRO SYSTEMS)", "TE")]
TEXT = {r.text: i for i, r in enumerate(ROWS)}


def _layer(name, **kw):
    return dict({"name": name, "short": name.split("|")[-1], "path_count": 9, "on": True}, **kw)


def test_estado_de_cada_descripcion():
    assert [cruce.estado_de_texto(r.text) for r in ROWS[:5]] == ["A", "E", "D", "E", "D"]   # errata «ABANONDED»
    assert cruce.estado_de_texto("PROPOSED TELECOM") == "N"
    assert cruce.estado_de_texto("UTILITY TO BE REMOVED") == "M"


def test_utilidad_de_cada_fila():
    assert cruce.utilidad_de_fila(ROWS[3]) == "ELECTRICO"                 # aérea «e(oh)»
    assert cruce.utilidad_de_fila(ROWS[TEXT["PROPOSED STORM DRAIN"]]) == "DRENAJE"   # sin letras
    assert cruce.utilidad_de_fila(ROWS[TEXT["PROPOSED TRACK ELECTRIFICATION DUCTBANK (METRO SYSTEMS)"]]) == "ELECTRICO"


def test_estado_por_las_letras_de_la_leyenda():
    assert cruce.estado_por_leyenda("G", "G", ROWS) == "N"
    assert cruce.estado_por_leyenda("G", "g", ROWS) == "E"
    assert cruce.estado_por_leyenda("TE", "TE", ROWS) == "N"
    assert cruce.estado_por_leyenda("W", "W", ROWS) == ""                 # «W» existente y propuesta
    assert cruce.estado_por_leyenda("E", "e", ROWS) == "E"               # las variantes abandonadas no cuentan


def test_cada_tipo_de_linea_con_su_descripcion():
    def desc(u, estado, code, letras, aerea=False):
        return [ROWS[i].text for i in cruce.emparejar(u, aerea, estado, code, letras, ROWS)]
    assert desc("ELECTRICO", "E", "E", ["e"]) == ["EXISTING ELECTRICAL"]
    assert desc("ELECTRICO", "D", "E", ["e"]) == ["EXISTING ELECTRICAL - TO BE ABANDONED"]
    assert desc("ELECTRICO", "N", "E", ["E"]) == ["PROPOSED ELECTRICAL"]
    assert desc("ELECTRICO", "N", "TE", ["TE"]) == ["PROPOSED TRACK ELECTRIFICATION DUCTBANK (METRO SYSTEMS)"]
    assert desc("ELECTRICO", "E", "", [], aerea=True) == ["EXISTING OVERHEAD ELECTRICAL"]
    assert desc("ALCANTARILLADO", "N", "S", ["S"]) == ["PROPOSED SANITARY SEWER"]   # «S» leída, «SS» en la leyenda
    assert desc("DRENAJE", "N", "SD", ["SD"]) == ["PROPOSED STORM DRAIN"]           # continua, sin letras
    assert desc("AGUA", "", "W", ["W"]) == ["EXISTING WATER", "PROPOSED WATER"]     # sin estado: las dos


def test_fila_con_paredes_solo_si_la_hoja_las_tiene():
    """Reporte del usuario 2026-10-09 (DU08 h.26): «EXISTING SANITARY SEWER (24" OR LARGER)»
    se dibuja con PAREDES (eje + dos paralelas, capa `C-SSWR-UNGD-WALL-E`). Sin paredes de
    alcantarillado existente en la hoja, esa fila no describe sus líneas; con ellas, sí (y la
    sencilla también: puede haber tuberías chicas). Si es la única fila, se queda."""
    plain = _row("EXISTING SANITARY SEWER", "ss")
    big = SimpleNamespace(**vars(_row('EXISTING SANITARY SEWER (24" OR LARGER)', "ss")), walls=True)
    rows = [plain, big]

    def desc(paredes, rs=rows):
        return [rs[i].text for i in cruce.emparejar("ALCANTARILLADO", False, "E", "SS", ["ss"], rs, paredes=paredes)]
    assert desc(False) == ["EXISTING SANITARY SEWER"]
    assert desc(True) == ["EXISTING SANITARY SEWER", 'EXISTING SANITARY SEWER (24" OR LARGER)']
    assert desc(False, [big]) == ['EXISTING SANITARY SEWER (24" OR LARGER)']
    layers = [_layer("R|C-SSWR-UNGD-E", read_codes=["SS"], letter_raw={"SS": "ss"})]
    fila = le.leyenda(layers, pdf_rows=rows)[0].filas[0]
    assert [rows[i].text for i in fila.pdf] == ["EXISTING SANITARY SEWER"]
    fila = le.leyenda(layers + [_layer("R|C-SSWR-UNGD-WALL-E")], pdf_rows=rows)[0].filas[0]
    assert len(fila.pdf) == 2
    fila = le.leyenda(layers + [_layer("R|C-STRM-UNGD-WALL-E")], pdf_rows=rows)[0].filas[0]
    assert len(fila.pdf) == 1                                   # paredes de OTRA utilidad no cuentan

def test_leyenda_por_utilidad_con_la_del_pdf():
    layers = [
        _layer("R|C-ELEC-UNGD-E", read_codes=["E"], letter_raw={"E": "e"}),
        _layer("R|C-ELEC-UNGD-D", letter_raw={"E": "e"}),                      # una sola «e» leída
        _layer("R|C-ELEC-3MI-UGND-N", read_codes=["E"], letter_raw={"E": "E"}),
        _layer("R|U-TRPW-DBNK-P", letter_utilities=["ELECTRICO"], letter_codes={"ELECTRICO": "TE"},
               read_codes=["TE"], letter_raw={"TE": "TE"}),
        _layer("R|C-ELEC-OVHD-E"),
        _layer("R|V-ELEC-POLE"),
    ]
    g = le.leyenda(layers, pdf_rows=ROWS)[0]
    got = [(f.rol, f.estado, f.code, [ROWS[i].text for i in f.pdf][:1]) for f in g.filas]
    assert got == [(le.LINE, "E", "E", ["EXISTING ELECTRICAL"]),
                   (le.LINE, "D", "E", ["EXISTING ELECTRICAL - TO BE ABANDONED"]),
                   (le.LINE, "N", "E", ["PROPOSED ELECTRICAL"]),
                   (le.LINE, "N", "TE", ["PROPOSED TRACK ELECTRIFICATION DUCTBANK (METRO SYSTEMS)"]),
                   (le.OVERHEAD, "E", "", ["EXISTING OVERHEAD ELECTRICAL"]),
                   (le.STRUCTURE, "", "", [])]
    te = next(f for f in g.filas if f.code == "TE")
    assert te.origen == le.FROM_LEGEND                     # su nombre no dice el estado; la leyenda sí


# ─────────────────────────────── DU08 h.26 ───────────────────────────────
@pytest.fixture(scope="module")
def du08_h26():
    if not DU08.exists():
        pytest.skip("PDF de prueba DU08 no disponible")
    import fitz
    from PySide6 import QtWidgets
    from ui.asistente import layer_dialog
    from ui.asistente import layer_dialog_info
    from ui.asistente.layer_info_panel import LegendWorker
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    got = {}
    worker = LegendWorker([{"name": "DU08.pdf", "path": str(DU08)}])
    worker.done.connect(lambda res: got.setdefault("res", res))
    worker.run()
    doc = fitz.open(str(DU08))
    sources = [{"name": "DU08.pdf", "path": str(DU08)}]
    cache = {layer_dialog_info._sources_key(sources): got["res"]}
    dlg = layer_dialog.SheetLayersDialog(None, doc, 25, legend_sources=sources, legend_cache=cache)
    yield app, dlg
    dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


def _short(names):
    return {n.split("|")[-1] for n in names}


@needs_du08
def test_du08_todas_las_lineas_electricas_con_su_descripcion(du08_h26):
    _app, dlg = du08_h26
    elec = next(g for g in dlg.info.standard_groups() if g.utilidad == "ELECTRICO")
    rows = dlg.info._rows
    desc = {f.code or f.rol: rows[f.pdf[0]][1].text for f in elec.filas if f.pdf}
    assert desc["E"] in ("EXISTING ELECTRICAL", "PROPOSED ELECTRICAL")
    assert desc["TE"].startswith("PROPOSED TRACK ELECTRIFICATION DUCTBANK")
    assert desc["SE"].startswith("PROPOSED SYSTEM ELECTRICAL DUCTBANK")
    assert desc[le.OVERHEAD] == "EXISTING OVERHEAD ELECTRICAL"
    textos = {rows[i][1].text for f in elec.filas for i in f.pdf}
    assert {"EXISTING ELECTRICAL", "EXISTING ELECTRICAL - TO BE ABANDONED", "PROPOSED ELECTRICAL"} <= textos
    for g in dlg.info.standard_groups():                     # en TODAS las utilidades: toda línea descrita
        assert all(f.pdf for f in g.filas if f.rol != le.STRUCTURE), g.utilidad


@needs_du08
def test_du08_h26_alcantarillado_sin_la_fila_de_24_pulgadas(du08_h26):
    """Reporte del usuario 2026-10-09: el tooltip de «EXISTING SANITARY SEWER» traía también
    la muestra de «(24" OR LARGER)», recortada sin su pared de arriba. La hoja no tiene
    paredes de alcantarillado (`C-SSWR-UNGD-WALL-E` sin trazos): esa fila no la describe. La
    muestra del PDF va completa, con sus paredes, en la leyenda completa."""
    _app, dlg = du08_h26
    rows = dlg.info._rows
    sewer = next(g for g in dlg.info.standard_groups() if g.utilidad == "ALCANTARILLADO")
    exist = next(f for f in sewer.filas if f.rol == le.LINE and f.estado == "E")
    assert [rows[i][1].text for i in exist.pdf] == ["EXISTING SANITARY SEWER"]
    big = next(r for _s, r in rows if r.text.startswith("EXISTING SANITARY SEWER (24"))
    assert big.walls and big.sample[3] - big.sample[1] >= 15          # eje + las dos paredes
    assert not any(r.walls for _s, r in rows if r.text in ("EXISTING SANITARY SEWER", "PROPOSED SANITARY SEWER"))


@needs_du08
def test_du08_clic_en_electrico_marca_e_E_TE_SE_y_no_las_aereas(du08_h26):
    _app, dlg = du08_h26
    strong, _soft, _what = dlg._utility_sets({"utility": "ELECTRICO"})
    capas = _short(d["layer"] for d in strong["ELECTRICO"] if d.get("layer"))
    assert {"C-ELEC-UNGD-E", "C-ELEC-3MI-UGND-N", "U-TRPW-DBNK-P", "N-COMM-DUCT-BANK-PL-SE"} <= capas
    assert "C-ELEC-OVHD-E" not in capas                     # aérea: no se reconoce
    # la fila «PROPOSED ELECTRICAL» de la leyenda completa marca las «E»
    i = next(i for i, (_s, r) in enumerate(dlg.info._rows) if r.text == "PROPOSED ELECTRICAL")
    dlg.info._on_pdf_row(i)
    assert dlg._hl_items and "PROPOSED ELECTRICAL" in dlg.info.lbl_focus.text()
    dlg.info.btn_focus_off.click()
    assert dlg._hl_items == []
