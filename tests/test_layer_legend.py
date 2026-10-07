"""Panel «Leyenda» del paso «Capas de la hoja» (pedido del usuario 2026-10-05).

  · qué capas se toman por las LETRAS de su línea, y la decisión del usuario de
    usarlas o no (vuelven a su grupo por nombre, se guardan en el proyecto y el
    reconocimiento las respeta);
  · la LEYENDA que trae el propio PDF (`pdf_legend`): muestra + descripción de cada
    línea; las tarjetas dicen qué significa su código según el plano.
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

fitz = pytest.importorskip("fitz")

import pdf_layers  # noqa: E402
import pdf_legend  # noqa: E402
import project_io  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"
LABOE = DOCS / "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf"
DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
needs_du08 = pytest.mark.skipif(not DU08.exists(), reason="PDF de prueba DU08 no disponible")


# ─────────────────────────────── lógica pura ───────────────────────────────
def _layer(name, **kw):
    return dict({"name": name, "short": name.split("|")[-1], "utility": "OTRAS", "name_group": "OTRAS",
                 "letters": "", "letter_utilities": [], "letter_codes": {}, "letter_paths": {},
                 "name_utility": "", "read_codes": [], "letter_raw": {}, "on": True, "path_count": 9}, **kw)


def test_sin_letras_la_capa_vuelve_a_su_grupo_por_nombre():
    te = _layer("X|U-TRPW-DBNK-P", utility="ELECTRICO", letters="TE", letter_utilities=["ELECTRICO"],
                letter_codes={"ELECTRICO": "TE"})
    se = _layer("X|N-COMM-DUCT-BANK-PL-SE", utility="ELECTRICO", name_group="TELECOM", letters="SE",
                letter_utilities=["ELECTRICO"], name_utility="TELECOM")
    out = {L["short"]: L for L in pdf_layers.without_letters([te, se], {"X|U-TRPW-DBNK-P", "X|N-COMM-DUCT-BANK-PL-SE"})}
    assert out["U-TRPW-DBNK-P"]["utility"] == "OTRAS" and not out["U-TRPW-DBNK-P"]["letter_utilities"]
    assert out["N-COMM-DUCT-BANK-PL-SE"]["utility"] == "TELECOM" and not out["N-COMM-DUCT-BANK-PL-SE"]["letters"]
    assert pdf_layers.without_letters([te], set())[0] is te


def test_la_decision_se_guarda_en_el_proyecto():
    model = {"tf": dict(scale=1, zoom=1, rot=0, W=1, H=1, derot=[1, 0, 0, 1, 0, 0]), "letters_off": ["X|_Xref"]}
    assert project_io.parse_model(model)["letters_off"] == ["X|_Xref"]
    assert project_io.parse_model({"tf": model["tf"]})["letters_off"] == []


def test_descripcion_de_un_codigo_segun_la_leyenda():
    from layer_info_panel import legend_texts
    R = pdf_legend.LegendRow
    src = {"name": "DU08.pdf"}
    rows = [(src, R(2, (0, 0, 1, 1), "EXISTING ABANDONED GAS", "g", "G")),
            (src, R(2, (0, 0, 1, 1), "EXISTING GAS", "g", "G")),
            (src, R(2, (0, 0, 1, 1), "PROPOSED GAS", "G", "G")),
            (src, R(2, (0, 0, 1, 1), "PROPOSED TRACK ELECTRIFICATION DUCTBANK", "TE", "TE")),
            (src, R(32, (0, 0, 1, 1), "PROPOSED TRACTION ELECTRIFICATION DUCTBANK", "TE", "TE"))]
    assert legend_texts(rows, "G", "G") == ["PROPOSED GAS"]                 # misma caja: propuesta
    assert legend_texts(rows, "G", "g") == ["EXISTING GAS"]                 # sin la variante abandonada
    assert legend_texts(rows, "TE", "TE") == ["PROPOSED TRACK ELECTRIFICATION DUCTBANK"]   # la 1.ª hoja
    assert legend_texts(rows, "SS") == []


# ─────────────────────────────── PDF reales ───────────────────────────────
@needs_du08
def test_leyenda_del_pdf_du08():
    with fitz.open(str(DU08)) as doc:
        assert pdf_legend.legend_pages(doc)[:2] in ([2, 32], [32, 2])
        rows = pdf_legend.document_legend(doc)
    by = {}
    for r in rows:
        by.setdefault(r.code, []).append(r.text)
    assert any("ELECTRIFICATION" in t for t in by["TE"]) and by["TE"]
    assert any("SIGNAL & COMMUNICATION" in t for t in by["SC"])
    assert "PROPOSED STORM DRAIN" in by[""]                 # muestra sin letras: fila igual
    assert {"E", "G", "SS", "SD", "T", "W", "UNK", "SE"} <= set(by)
    assert all(r.text.startswith(("EXISTING", "PROPOSED")) for r in rows)


@pytest.mark.skipif(not LABOE.exists(), reason="PDF de prueba LABOE no disponible")
def test_leyenda_laboe_sin_etiquetas_del_plano():
    """Las hojas 8 y 9 tienen etiquetas con flecha alineadas: no son leyenda."""
    with fitz.open(str(LABOE)) as doc:
        rows = pdf_legend.document_legend(doc)
        assert pdf_legend.page_legend(doc[7]) == [] and pdf_legend.page_legend(doc[8]) == []
    assert len(rows) >= 30 and all(r.text.startswith(("EXISTING", "PROPOSED")) for r in rows)


@pytest.mark.skipif(not DU06.exists(), reason="PDF de prueba DU06 no está en el repo")
def test_pdf_sin_leyenda():
    with fitz.open(str(DU06)) as doc:
        assert pdf_legend.document_legend(doc) == []


@pytest.fixture(scope="module")
def du08_legend():
    if not DU08.exists():
        pytest.skip("PDF de prueba DU08 no disponible")
    from layer_info_panel import LegendWorker
    got = {}
    worker = LegendWorker([{"name": "DU08.pdf", "path": str(DU08)}])
    worker.done.connect(lambda res: got.setdefault("res", res))
    worker.run()                                     # en el hilo de la prueba
    return got["res"]


def _dialog(legend):
    from PySide6 import QtWidgets
    import layer_dialog, layer_dialog_info
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open(str(DU08))
    sources = [{"name": "DU08.pdf", "path": str(DU08)}]
    cache = {layer_dialog_info._sources_key(sources): legend}
    dlg = layer_dialog.SheetLayersDialog(None, doc, 25, legend_sources=sources, legend_cache=cache)
    return app, doc, dlg


@needs_du08
def test_panel_por_letras_y_decision_de_usarlas(du08_legend):
    app, doc, dlg = _dialog(du08_legend)
    try:
        cards = {n.split("|")[-1]: c for n, c in dlg.info._cards.items()}
        assert {"U-TRPW-DBNK-P", "N-COMM-DUCT-BANK-PL-SE", "_Xref"} <= set(cards)
        assert "TRACK ELECTRIFICATION" in cards["U-TRPW-DBNK-P"].lbl_legend.text()
        assert "PROPOSED GAS" in cards["_Xref"].lbl_legend.text()
        te = cards["U-TRPW-DBNK-P"]
        assert dlg.group_item("ELECTRICO") is not None and te.chk.isChecked()
        te.chk.setChecked(False)                                   # «no usar sus letras»
        layer = next(L for L in dlg._layers if L["name"] == te.name)
        assert layer["utility"] == "OTRAS" and not layer["letters"]
        assert dlg.letters_off() == [te.name]
        te.chk.setChecked(True)
        assert dlg.letters_off() == []
    finally:
        dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


@needs_du08
def test_clic_resalta_sus_lineas_y_otro_clic_lo_quita(du08_legend):
    app, doc, dlg = _dialog(du08_legend)
    try:
        card = next(c for n, c in dlg.info._cards.items() if n.endswith("U-TRPW-DBNK-P"))
        card.activated.emit(card.name)
        assert len(dlg._hl_items) >= 2                             # velo + líneas
        card.activated.emit(card.name)
        assert dlg._hl_items == []
        # fila de la leyenda «PROPOSED GAS» (G mayúscula): solo las líneas propuestas
        dlg.info._request(("code", "G", "G"), {"codes": ["G"], "raw": "G"})
        assert dlg._hl_items
    finally:
        dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


@needs_du08
def test_leyenda_marca_las_de_esta_hoja(du08_legend):
    app, doc, dlg = _dialog(du08_legend)
    try:
        assert "leyenda del PDF" in dlg.info.lbl_legend.text()
        assert dlg.info.btn_all.isVisibleTo(dlg.info)
        assert dlg.info.legend_box.count() == 0                    # la leyenda completa va plegada
        dlg.info._toggle_all()
        assert dlg.info.legend_box.count() == len(dlg.info._rows) > 30
        here = dlg.info.std.matched()
        assert {dlg.info._rows[i][1].text for i in here} >= {"EXISTING ELECTRICAL", "PROPOSED ELECTRICAL"}
    finally:
        dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


@needs_du08
def test_reconocimiento_respeta_la_decision():
    from PySide6 import QtCore
    import workers
    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    te = "PS89616000_B3-NX-REF-MODL-001|U-TRPW-DBNK-P"
    got = {}
    w = workers.RecognitionWorker(str(DU08), 25, zoom=2.0, utilities=("ELECTRICO",), letters_off={te})
    w.done.connect(lambda res, err: got.update(res=res, err=err))
    w.run()
    assert not got["err"]
    layers = {p.layer_ocg for p in got["res"][0].drawable}
    assert te not in layers and any(n.endswith("PL-SE") for n in layers)
