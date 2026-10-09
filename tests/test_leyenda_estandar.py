"""Leyenda según el ESTÁNDAR BOE en «Capas de la hoja» (pedido del usuario 2026-10-07).

DU06 no trae leyenda («Este PDF no trae una leyenda de líneas»): con el manual BOE
(tipos de línea por utilidad, fig. 3.1.7.1; estado del nombre de la capa, §8.1.6) se
arma una con las líneas de la hoja, y cada utilidad o fila resalta lo suyo. Además la
tarjeta de una capa por sus letras («T» de G-XREF en DU06 h.5) muestra el RESTO de las
líneas de su utilidad: las «t» de C-TELE-UNGD-E van pegadas y al importar también son
telecom, pero no se veían.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from hoja import leyenda_estandar as le  # noqa: E402
from hoja import leyenda_trazos  # noqa: E402

DU06 = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
needs_du06 = pytest.mark.skipif(not DU06.exists(), reason="PDF de prueba DU06 no está en el repo")


def _layer(name, **kw):
    return dict({"name": name, "short": name.split("|")[-1], "utility": "OTRAS", "name_group": "OTRAS",
                 "letters": "", "letter_utilities": [], "letter_codes": {}, "letter_paths": {},
                 "name_utility": "", "read_codes": [], "letter_raw": {}, "on": True, "path_count": 9}, **kw)


# ─────────────────────────────── lógica pura ───────────────────────────────
def test_estado_del_nombre_del_xref_o_de_las_letras():
    assert le.estado_capa(_layer("X-REF-EXIST_TELECOM|C-TELE-UNGD-E")) == ("E", le.FROM_NAME)
    assert le.estado_capa(_layer("X|C-ELEC-UGND-N__UA4")) == ("N", le.FROM_NAME)      # sin el paquete
    assert le.estado_capa(_layer("X|CU-STRM-UNGD-D")) == ("D", le.FROM_NAME)          # disciplina nivel 2
    assert le.estado_capa(_layer("X|C-NGAS-A")) == ("A", le.FROM_NAME)
    assert le.estado_capa(_layer("T-PROP-COMM")) == ("N", le.FROM_NAME)
    # la «N» de `N-COMM-…` es la disciplina, no el estado
    assert le.estado_capa(_layer("N-COMM-DUCT-BANK-PL")) == ("", "")
    assert le.estado_capa(_layer("PS-REF-PROP_WATER|C-WATR-PIPE")) == ("N", le.FROM_XREF)
    assert le.estado_capa(_layer("G-XREF"), ["T"]) == ("N", le.FROM_LETTERS)          # mayúscula = propuesta
    assert le.estado_capa(_layer("G-XREF"), ["t"]) == ("E", le.FROM_LETTERS)
    assert le.estado_capa(_layer("G-XREF"), ["T", "t"]) == ("", "")


def test_abreviatura_boe():
    assert le.abbr_capa(_layer("C-TELE-UNGD-E"), "TELECOM") == "TEL"
    assert le.abbr_capa(_layer("C-COMM-FO-UNGD-N"), "TELECOM") == "FO"
    assert le.abbr_capa(_layer("C-FIRE-UNGD-E"), "AGUA") == "FPW"
    assert le.abbr_capa(_layer("C-WATR-UNGD-E"), "AGUA") == "PW"
    assert le.abbr_capa(_layer("C-ELEC-UNGD-E"), "ELECTRICO") == "ELEC"
    assert le.linetype("TEL")[0] == "TELEPHONE / COMM"


def test_rol_de_la_capa_como_el_reconocimiento():
    assert le.rol_capa(_layer("X|C-TELE-UNGD-E"), "TELECOM") == (le.LINE, False)
    assert le.rol_capa(_layer("X|C-TELE-VALT-E"), "TELECOM") == (le.STRUCTURE, False)
    assert le.rol_capa(_layer("X|C-TELE-UNGD-E"), "ELECTRICO") == (None, False)
    assert le.rol_capa(_layer("X|C-ELEC-OVHD-E"), "ELECTRICO") == (le.OVERHEAD, False)  # aérea: no se reconoce
    assert le.rol_capa(_layer("X|C-ELEC-OVHD-E"), "TELECOM") == (None, False)
    mixta = _layer("G-XREF", letter_utilities=["AGUA", "TELECOM"],
                   letter_paths={(1,): "TELECOM", (2,): "AGUA"})
    assert le.rol_capa(mixta, "TELECOM") == (le.LINE, True)
    assert le.rol_capa(mixta, "GAS") == (None, False)
    # su nombre dice telecom, sus letras («SE») eléctrico: manda la letra, la capa entera
    se = _layer("X|N-COMM-DUCT-BANK-PL-SE", letter_utilities=["ELECTRICO"], name_utility="TELECOM")
    assert le.rol_capa(se, "ELECTRICO") == (le.LINE, False)
    assert le.rol_capa(se, "TELECOM") == (None, False)


def test_trazo_de_una_capa_mezclada(monkeypatch):
    monkeypatch.setattr(le.letters_mod, "path_key", lambda d: d["k"])
    mixta = _layer("G-XREF", letter_utilities=["AGUA", "TELECOM"],
                   letter_paths={(1,): "TELECOM", (2,): "AGUA"})
    assert le.es_trazo_de(mixta, "TELECOM", {"k": (1,), "fill": None}) == le.LINE
    assert le.es_trazo_de(mixta, "TELECOM", {"k": (2,), "fill": None}) is None
    assert le.es_trazo_de(mixta, "TELECOM", {"k": (3,), "fill": None}) is None      # sin letras: no
    assert le.es_trazo_de(mixta, "TELECOM", {"k": (1,), "fill": (1, 1, 1)}) is None  # relleno: no


def test_reconocer_una_utilidad_con_todas_sus_capas_ocultas():
    """4.º pedido (2026-10-07): marcar una utilidad para reconocer con sus capas ocultas
    «no puede ser». Cuentan sus capas de LÍNEA (por nombre o por letras; sin líneas, las de
    sus estructuras): su caja sola no basta."""
    capas = [_layer("X|C-TELE-UNGD-E"), _layer("X|C-TELE-VALT-E"), _layer("X|C-WATR-UNGD-E"),
             _layer("G-XREF", letter_utilities=["AGUA", "TELECOM"],
                    letter_paths={(1,): "TELECOM", (2,): "AGUA"}),
             _layer("X|C-NGAS-VALT"), _layer("X|C-SSWR-UNGD-E", path_count=0)]
    assert le.capas_que_reconoce(capas, "TELECOM") == (["X|C-TELE-UNGD-E", "G-XREF"], ["X|C-TELE-VALT-E"])
    todas = ["TELECOM", "AGUA", "GAS", "ALCANTARILLADO"]
    assert le.sin_capas_visibles(capas, [], todas) == []
    assert le.sin_capas_visibles(capas, ["X|C-TELE-UNGD-E", "G-XREF"], todas) == ["TELECOM"]
    assert le.sin_capas_visibles(capas, ["X|C-TELE-UNGD-E"], todas) == []          # G-XREF (sus «T») se ve
    assert le.sin_capas_visibles(capas, ["X|C-WATR-UNGD-E", "G-XREF"], todas) == ["AGUA"]
    assert le.sin_capas_visibles(capas, ["X|C-WATR-UNGD-E", "G-XREF"], ["TELECOM"]) == []   # no la pidió
    assert le.sin_capas_visibles(capas, ["X|C-NGAS-VALT"], todas) == ["GAS"]       # solo estructuras
    # alcantarillado no tiene trazos en la hoja: no hay nada que avisar


def test_leyenda_agrupa_por_utilidad_y_estado():
    layers = [
        _layer("R-EXIST|C-TELE-UNGD-E", read_codes=["T"], letter_raw={"T": "t"}),
        _layer("R-EXIST2|C-TELE-UNGD-E", read_codes=["T"], letter_raw={"T": "t"}),
        _layer("R-EXIST|C-TELE-UNGD-D", read_codes=["T"], letter_raw={"T": "t"}),
        _layer("G-XREF", letter_utilities=["TELECOM"], letter_codes={"TELECOM": "T"},
               letter_paths={(1,): "TELECOM"}, read_codes=["T"], letter_raw={"T": "T"}),
        _layer("R|C-TELE-VALT-E"),
        _layer("R|C-ELEC-UNGD-E", read_codes=["E"], letter_raw={"E": "e"}),
        _layer("R|C-ELEC-UNGD-N", path_count=0),                 # sin trazos en la hoja: no
        _layer("R|V-ROAD-CURB"),
    ]
    grupos = {g.utilidad: g for g in le.leyenda(layers)}
    assert list(grupos) == ["ELECTRICO", "TELECOM"]              # orden de «Capas del plano»
    tele = grupos["TELECOM"]
    assert tele.abbr == "TEL"
    filas = [(f.rol, f.estado, f.letras, f.marcas, f.continua, f.por_letras, len(f.capas)) for f in tele.filas]
    assert filas == [(le.LINE, "E", ["t"], "", False, False, 2),
                     (le.LINE, "D", ["t"], "//", False, False, 1),
                     (le.LINE, "N", ["T"], "", True, True, 1),
                     (le.STRUCTURE, "", [], "", False, False, 1)]
    assert [f.estado for f in grupos["ELECTRICO"].filas] == ["E"]


# ─────────────────────────────── DU06 h.5 ───────────────────────────────
@pytest.fixture(scope="module")
def du06_h5():
    if not DU06.exists():
        pytest.skip("PDF de prueba DU06 no está en el repo")
    import fitz
    from hoja import pdf_layers
    from PySide6 import QtWidgets
    from ui.asistente import layer_dialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open(str(DU06))
    dlg = layer_dialog.SheetLayersDialog(None, doc, 4, layers=pdf_layers.page_layers(doc, 4), legend_sources=[])
    yield app, dlg
    dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


@needs_du06
def test_du06_sin_leyenda_muestra_la_del_estandar(du06_h5):
    _app, dlg = du06_h5
    grupos = {g.utilidad: g for g in dlg.info.standard_groups()}
    assert set(grupos) == {"AGUA", "ALCANTARILLADO", "DRENAJE", "GAS", "ELECTRICO", "TELECOM"}
    tele = [(f.estado, [n.split("|")[-1] for n in f.capas]) for f in grupos["TELECOM"].filas if f.rol == le.LINE]
    assert ("E", ["C-TELE-UNGD-E"]) in tele and ("D", ["C-TELE-UNGD-D"]) in tele
    assert any(e == "N" and "G-XREF" in capas for e, capas in tele)
    assert "estándar BOE" in dlg.info.lbl_legend.text()


@needs_du06
def test_du06_tarjeta_t_muestra_el_resto_de_telecom(du06_h5):
    """La tarjeta «Telecomunicaciones «T»» (G-XREF): sus líneas con halo y, en línea
    fina, las de C-TELE-UNGD-E/-D que van al lado (las flechas del reporte)."""
    _app, dlg = du06_h5
    strong, soft, _what = dlg._focus_sets({"layers": ["G-XREF"]})
    assert {d["layer"] for d in strong["TELECOM"]} == {"G-XREF"}
    finos = {d["layer"].split("|")[-1] for d in soft["TELECOM"]}
    assert {"C-TELE-UNGD-E", "C-TELE-UNGD-D"} <= finos and "G-XREF" not in finos
    dlg.info._cards["G-XREF"].activated.emit("G-XREF")
    assert dlg._hl_items and "G-XREF" in dlg.info.lbl_focus.text()
    dlg.info.btn_focus_off.click()                               # «Ver todo»
    assert dlg._hl_items == [] and not dlg.info.focus_bar.isVisibleTo(dlg.info)


@needs_du06
def test_du06_clic_en_la_utilidad_y_en_una_fila(du06_h5):
    _app, dlg = du06_h5
    strong, _soft, what = dlg._utility_sets({"utility": "TELECOM", "label": "Telecom"})
    capas = {d["layer"].split("|")[-1] for d in strong["TELECOM"]}
    assert {"C-TELE-UNGD-E", "C-TELE-UNGD-D", "G-XREF", "C-TELE-VALT-E"} <= capas
    assert "7" in what
    fila = next(f for g in dlg.info.standard_groups() if g.utilidad == "TELECOM"
                for f in g.filas if f.estado == "D")
    strong, _soft, _what = dlg._utility_sets({"utility": "TELECOM", "layers": fila.capas, "role": fila.rol})
    assert {d["layer"].split("|")[-1] for d in strong["TELECOM"]} == {"C-TELE-UNGD-D"}
    dlg.info.std.toggle_utility("TELECOM")
    assert dlg._hl_items
    dlg.info.std.toggle_utility("TELECOM")                     # otro clic: la desmarca
    assert dlg._hl_items == []


@needs_du06
@pytest.mark.parametrize("page_i", [4, 2, 1])
def test_du06_la_leyenda_toma_lo_mismo_que_el_reconocimiento(page_i):
    """Qué capas son líneas/estructuras de cada utilidad: lo mismo que toma
    `recognize_page` (por nombre y por las letras de su línea), solo lo VISIBLE: en
    h.3 las bóvedas de un xref recortado fuera de la vista no se pintan, no se
    reconocen y tampoco van a la leyenda ni se resaltan. En h.2 hay bóvedas de capas que
    no están en la lista de capas del PDF (`…(A2_TRIM)|V-ELEC-MANH`): se toman por nombre."""
    import fitz
    from hoja import pdf_layers
    from reconocimiento import recognition as rec
    with fitz.open(str(DU06)) as doc:
        Ls = {L["name"]: L for L in pdf_layers.page_layers(doc, page_i)}
        page = doc[page_i]
        letters = rec.page_letters(page)
        pares = leyenda_trazos.trazos_visibles(page, le.capas_de_utilidad(Ls.values()))
        vis = {d["layer"] for d, _shown in pares}
        for n in vis - set(Ls):
            Ls[n] = le.capa_sin_lista(n)
        grupos = {g.utilidad: g for g in le.leyenda([L for L in Ls.values() if L["name"] in vis])}
        for u in rec.SUPPORTED_UTILITIES:
            lp, vp = rec.utility_line_paths(page, u, letters)
            mine = {r: {d["layer"] for d, _shown in pares
                        if le.es_trazo_de(Ls[d["layer"]], u, d) == r} for r in (le.LINE, le.STRUCTURE)}
            assert mine[le.LINE] == {p.get("layer") for p in lp}, u
            assert mine[le.STRUCTURE] == {p.get("layer") for p in vp}, u
            filas = grupos[u].filas if u in grupos else []
            assert {n for f in filas if f.rol == le.LINE for n in f.capas} == mine[le.LINE], u
            assert {n for f in filas if f.rol == le.STRUCTURE for n in f.capas} == mine[le.STRUCTURE], u


@needs_du06
def test_du06_g_xref_trae_dos_utilidades(du06_h5):
    """4.º reporte (2026-10-07): en DU06 h.5 `G-XREF` trae las líneas «—T—» de telecom y un
    tramo «—W—» de agua. La leyenda del Agua lo lista (propuesta, «W») y al marcarla se
    resalta SOLO ese tramo; la fila de Telecom de esa capa, solo sus «T»."""
    _app, dlg = du06_h5
    grupos = {g.utilidad: g for g in dlg.info.standard_groups()}
    fila = next(f for f in grupos["AGUA"].filas if f.rol == le.LINE and "G-XREF" in f.capas)
    assert fila.estado == "N" and "W" in fila.letras and fila.por_letras
    tramo = (900.0, 970.0, 1005.0, 996.0)                       # el «—W—» (recta, quiebre, W, recta)

    def dentro(d):
        r = d["rect"]
        return tramo[0] <= r.x0 and r.x1 <= tramo[2] and tramo[1] <= r.y0 and r.y1 <= tramo[3]
    strong, _soft, _what = dlg._utility_sets({"utility": "AGUA", "layers": ["G-XREF"], "role": le.LINE})
    assert len(strong["AGUA"]) == 3 and all(dentro(d) for d in strong["AGUA"])
    strong, _soft, _what = dlg._utility_sets({"utility": "TELECOM", "layers": ["G-XREF"], "role": le.LINE})
    assert strong["TELECOM"] and not any(dentro(d) for d in strong["TELECOM"])


@needs_du06
def test_du06_tooltip_con_la_muestra_en_grande(du06_h5):
    """4.º pedido: al pasar el ratón por una fila de la leyenda, la miniatura en GRANDE."""
    from ui.asistente import layer_std_legend as lsl
    _app, dlg = du06_h5
    std = dlg.info.std
    key = next(k for k in std._rows if k[1] == "AGUA" and "G-XREF" in k[2])
    tip = std._rows[key]["w"].toolTip()
    w = round(lsl.SAMPLE_W * lsl.TIP_SCALE)
    assert "data:image/png;base64," in tip and f"width='{w}'" in tip
    assert "Clic" in tip                                          # la descripción, debajo
    pm = lsl.sample_pixmap(std._rows[key]["fila"])
    assert pm.width() / pm.devicePixelRatio() == w


@needs_du06
def test_du06_varias_utilidades_a_la_vez_y_se_ve_cual_esta_activa(du06_h5):
    """3.er pedido (2026-10-07): casillas para activar MÁS DE UNA utilidad, y que en el
    panel se note cuál está activa (con halo en la hoja)."""
    from PySide6 import QtCore
    _app, dlg = du06_h5
    std = dlg.info.std
    std.toggle_utility("TELECOM")
    std.toggle_utility("ELECTRICO")
    utils = {k[1] for k in std.active_keys()}
    assert utils == {"TELECOM", "ELECTRICO"}
    assert std._heads["TELECOM"]["chk"].checkState() == QtCore.Qt.Checked
    assert std._heads["AGUA"]["chk"].checkState() == QtCore.Qt.Unchecked
    on = next(k for k in std.active_keys() if k[1] == "TELECOM")
    assert "solid" in std._rows[on]["w"].styleSheet()            # marco del color de su utilidad
    assert "Telecomunicaciones" in dlg.info.lbl_focus.text() and "Eléctrico" in dlg.info.lbl_focus.text()
    strong, _soft, _what = dlg._union_sets({"specs": dlg.info.active()})
    assert set(strong) == {"TELECOM", "ELECTRICO"} and dlg._hl_items
    # una fila de agua además: la utilidad queda a medias
    fila = next(k for k in std._heads["AGUA"]["keys"])
    std.set_row(fila, True)
    assert std._heads["AGUA"]["chk"].checkState() == QtCore.Qt.PartiallyChecked
    # la tarjeta por letras se suma a lo marcado
    dlg.info._cards["G-XREF"].activated.emit("G-XREF")
    assert dlg.info._cards["G-XREF"].highlighted and len(dlg.info.active()) > len(std.active_keys())
    dlg.info.btn_focus_off.click()                               # «Ver todo»: nada activo
    assert std.active_keys() == [] and not dlg.info._cards["G-XREF"].highlighted and dlg._hl_items == []
