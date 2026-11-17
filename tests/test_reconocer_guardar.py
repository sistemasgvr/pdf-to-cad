"""Guardar y reabrir el panel «Reconocer» (plan 2026-11-16, «reconocimiento desde el editor», Tarea 10).

El `.digproj` lleva el estado de las filas (`reconocer_estado.a_dict`) y una interpretación LIVIANA de la hoja
(capas, leyenda, estilos sugeridos, símbolos, rótulos, escala, firma y los roles elegidos): nunca la lectura cruda
ni las letras. Al reabrir el panel queda igual y el primer ▶ vuelve a leer la hoja UNA vez con el mismo resultado.
Un proyecto viejo (sin ese bloque) abre sin interpretar: lo ya importado queda «reconocida» y «Interpretar la hoja»
disponible (Review Focus 5).
"""
import copy
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")

import project_io  # noqa: E402
from hoja import interpretacion_guardada as IG  # noqa: E402
from hoja.estilos_sugeridos import Sugerencia  # noqa: E402
from hoja.leyenda_mapa import FilaMapa, LeyendaMapa  # noqa: E402
from nucleo import reconocer_estado as RE  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")


# ── datos (sin ventana) ──────────────────────────────────────────────────
def _leyenda():
    fila = FilaMapa("Standard Main", "WATER", "AGUA", "LINEA", False, (1.0, 2.0, 3.0, 4.0),
                    {'PDF_STYLE:["#000",0.71]': 120.5}, ((7, (0.0, 0.0, 1.0)), (9, (1.0, 0.0, 0.0))), "ESRI", "W")
    return LeyendaMapa([fila], "AGUA", 0.27, [(0.0, 0.0, 50.0, 60.0)], "LEGEND", 0.75, "ACP",
                       por_hoja=[[fila]], piezas=[None])


def _interp():
    return {"firma": "abc", "escala": 1.6667,
            "layers": [{"name": "C-STRM-UNGD-E", "path_count": 12, "utility": "DRENAJE",
                        "letter_utilities": ["DRENAJE"], "letter_codes": {"sd": "DRENAJE"},
                        "letter_paths": {"DRENAJE": {((1.0, 2.0, 3.0, 4.0), 2), ((5.0, 6.0, 7.0, 8.0), 3)}},
                        "letter_raw": {"sd": [("s", (0.0, 0.0, 1.0, 1.0))]}}],
            "leyenda": _leyenda(), "visibles": ["C-STRM-UNGD-E"],
            "sugeridos": Sugerencia("AGUA", ["a", "b"], "a", None, "ok", {"AGUA": 3}, 7),
            "letras": {"C-STRM-UNGD-E": object()},           # la lectura de letras: NUNCA al .digproj
            "simbolos": [{"fuente": "capa", "nombre": "V-WATR-VALV"}], "rotulos_n": 4}


def test_interpretacion_ligera_ida_y_vuelta():
    interp = _interp()
    d = IG.ligera(interp, roles={"AGUA": {"lineas": {"x", "y"}}})
    texto = json.dumps(d)                                    # va a model.json tal cual
    vuelta, roles = IG.de_ligera(json.loads(texto))
    assert "letras" not in vuelta and "letras" not in json.loads(texto)["interpretacion"]
    esperado = {k: v for k, v in interp.items() if k != "letras"}
    assert vuelta == esperado
    assert isinstance(vuelta["leyenda"], LeyendaMapa) and isinstance(vuelta["sugeridos"], Sugerencia)
    assert vuelta["leyenda"].filas[0].simbolo == interp["leyenda"].filas[0].simbolo   # tuplas, no listas
    assert roles == {"AGUA": {"lineas": {"x", "y"}}}


def test_no_reconstruye_clases_fuera_de_la_lista():
    """Un .digproj ajeno no puede pedir construir cualquier clase."""
    malo = {"interpretacion": {"x": {"__dc__": "os:system", "campos": {}}}}
    with pytest.raises(ValueError):
        IG.de_ligera(malo)


def _win(estado, interp=None, roles=None):
    return SimpleNamespace(reconocer_estado=estado, _interpretacion=interp, _layer_roles_by_utility=roles or {})


def test_estado_ida_y_vuelta_por_project_io():
    e = RE.nuevo()
    e.firma_hoja = "abc"
    RE.tras_reconocer(e, "DRENAJE", "f1", 12, [{"texto": "x", "rect": [1.0, 2.0, 3.0, 4.0]}])
    e.filas["AGUA"].estado, e.filas["AGUA"].motivo = "bloqueada", RE.M_SIN_CAPAS
    e.filas["GAS"].unir_tramos = False
    model = {"reconocer": json.loads(json.dumps(project_io.reconocer_a_dict(_win(e, _interp(), {"AGUA": {}}))))}
    r = project_io.reconocer_de_model(model, pipes=[])
    assert RE.a_dict(r["estado"]) == RE.a_dict(e)
    assert r["interpretacion"]["layers"] == _interp()["layers"]
    assert r["roles"] == {"AGUA": {}}


def test_reconociendo_al_guardar_vuelve_a_su_estado():
    e = RE.nuevo()
    e.filas["AGUA"].estado = "reconociendo"
    e.filas["GAS"].estado, e.filas["GAS"].firma = "reconociendo", "f"
    r = project_io.reconocer_de_model({"reconocer": project_io.reconocer_a_dict(_win(e))}, pipes=[])
    assert r["estado"].filas["AGUA"].estado == "pendiente"
    assert r["estado"].filas["GAS"].estado == "reconocida"


def test_proyecto_viejo_lo_importado_queda_reconocido():
    rec_ = {"origen": "reconocido"}                     # lo que pone el reconocimiento (también antes del panel)
    pipes = [{"layer": "DRENAJE", "pts": [(0, 0), (1, 1)], **rec_}, {"layer": "DRENAJE", "pts": [(0, 0), (2, 2)], **rec_},
             {"layer": "AGUA", "pts": [(0, 0), (1, 0)], **rec_}, {"layer": "OTRA", "pts": [(0, 0), (0, 1)], **rec_},
             {"layer": "GAS", "pts": [(0, 0), (3, 0)]}]  # dibujada a mano: no cuenta como reconocida
    r = project_io.reconocer_de_model({"pipes": pipes}, pipes=pipes)
    e = r["estado"]
    assert r["interpretacion"] is None and r["roles"] is None
    assert e.filas["DRENAJE"].estado == "reconocida" and e.filas["DRENAJE"].firma is None
    assert e.filas["DRENAJE"].hechos == 2 and e.filas["AGUA"].estado == "reconocida"
    assert all(f.estado == "sin_interpretar" for p, f in e.filas.items() if p not in ("DRENAJE", "AGUA"))
    # «Interpretar la hoja» después: lo ya reconocido se conserva
    e2 = RE.de_interpretacion(e, {"layers": [], "simbolos": [], "rotulos_n": 0}, "firma-nueva")
    assert e2.filas["DRENAJE"].estado == "reconocida" and e2.firma_hoja == "firma-nueva"
    assert e2.filas["GAS"].estado == "bloqueada"


def test_guardar_no_falla_por_un_dato_raro_en_la_interpretacion():
    """Un tipo que la interpretación guardada no sabe escribir no impide guardar: va sin la interpretación."""
    from types import SimpleNamespace
    win = SimpleNamespace(reconocer_estado=RE.nuevo(), _interpretacion={"layers": [], "raro": object()},
                          _layer_roles_by_utility={"AGUA": {"lineas": ["C-WATR"]}})
    d = project_io.reconocer_a_dict(win)
    assert d["interpretacion"] is None and d["estado"] == RE.a_dict(win.reconocer_estado)
    assert d["roles"] == {"AGUA": {"lineas": ["C-WATR"]}}


def test_hoja_agregada_va_y_vuelve():
    from types import SimpleNamespace
    ov = {"ruta": "x.pdf", "tmp": "x.pdf", "hoja": 0, "firma": "f-agregada", "desde": 1, "grupo": 1}
    win = SimpleNamespace(reconocer_estado=RE.nuevo(), _interpretacion=None, _layer_roles_by_utility={}, _rec_hoja=ov)
    d = project_io.reconocer_a_dict(win)
    assert d["hoja_agregada"] == {"hoja": 0, "firma": "f-agregada", "desde": 1, "grupo": 1}   # sin el temporal
    r = project_io.reconocer_de_model({"reconocer": json.loads(json.dumps(d))}, pipes=[])
    assert r["hoja_agregada"] == d["hoja_agregada"]


def test_proyecto_vacio_sin_bloque():
    r = project_io.reconocer_de_model({}, pipes=[])
    assert all(f.estado == "sin_interpretar" for f in r["estado"].filas.values())


# ── ventana real ─────────────────────────────────────────────────────────
from test_flujo_abrir_interpretar import (_componer, _esperar, _esperar_hilos, esperar_interpretacion,  # noqa: E402
                                          ventana)  # noqa: F401,E402  (fixture)
from reconocimiento import lectura_retenida as LR  # noqa: E402


def _abiertas(monkeypatch):
    """Cuántas veces se LEE la hoja de nuevo (una firma que no estaba retenida)."""
    leidas = []
    original = LR.abrir

    def abrir(ruta, firma):
        if LR.retenida() != str(firma):
            leidas.append(firma)
        return original(ruta, firma)
    monkeypatch.setattr(LR, "abrir", abrir)
    return leidas


def _lineas(res):
    return sorted(json.dumps([[[round(p[0], 6), round(p[1], 6)] for p in pl.pts_pdf] for pl in r.drawable])
                  for r in res or [])


def _reabrir(w, ruta):
    w._dirty = False
    w._open_project_path(str(ruta))
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance().processEvents()


@needs_pdf
def test_reabrir_deja_el_panel_igual_y_el_primer_play_relee_una_vez(ventana, monkeypatch, tmp_path):
    w = ventana
    _componer(monkeypatch, hoja=2)
    w._open_pdf_path(str(DU06))
    esperar_interpretacion(w)
    w.reconocer_parte("DRENAJE")
    _esperar(lambda: w._rec_actual is None)
    assert w.reconocer_estado.filas["DRENAJE"].estado == "reconocida"
    antes = RE.a_dict(w.reconocer_estado)
    capas = copy.deepcopy(w._interpretacion["layers"])
    lineas = _lineas(w._resultados_partes["DRENAJE"])
    n_pipes = len(w.pipes)
    ruta = tmp_path / "proy.digproj"
    w._write_project(str(ruta))
    _esperar_hilos()
    LR.soltar()

    _reabrir(w, ruta)
    assert RE.a_dict(w.reconocer_estado) == antes
    assert w._interpretacion["layers"] == capas
    assert "letras" not in w._interpretacion
    p = w.panel_reconocer
    assert p.lista.isVisibleTo(p) and not p.btn_interpretar.isVisibleTo(p)
    assert len(w.pipes) == n_pipes and not w.interpretando()

    leidas = _abiertas(monkeypatch)
    w.reconocer_parte("DRENAJE")                             # ya reconocida: sin pantalla «agrega lo que falta»
    _esperar(lambda: w._rec_actual is None)
    assert len(leidas) == 1                                  # la hoja se lee UNA vez
    assert _lineas(w._resultados_partes["DRENAJE"]) == lineas
    assert len(w.pipes) == n_pipes                           # nada repetido


@needs_pdf
def test_proyecto_viejo_abre_sin_interpretar(ventana, monkeypatch, tmp_path):
    w = ventana
    _componer(monkeypatch, hoja=2)
    w._open_pdf_path(str(DU06))
    esperar_interpretacion(w)
    w.reconocer_parte("DRENAJE")
    _esperar(lambda: w._rec_actual is None)
    ruta = tmp_path / "nuevo.digproj"
    w._write_project(str(ruta))
    _esperar_hilos()
    viejo = tmp_path / "viejo.digproj"                       # el mismo proyecto, sin el bloque nuevo
    with zipfile.ZipFile(ruta) as zi, zipfile.ZipFile(viejo, "w", zipfile.ZIP_DEFLATED) as zo:
        for n in zi.namelist():
            datos = zi.read(n)
            if n == "model.json":
                m = json.loads(datos)
                assert "reconocer" in m
                m.pop("reconocer")
                datos = json.dumps(m).encode("utf-8")
            zo.writestr(n, datos)
    LR.soltar()
    pedidas = []
    monkeypatch.setattr(w, "_interpretar_hoja", lambda: pedidas.append(1))
    _reabrir(w, viejo)
    e = w.reconocer_estado
    assert not pedidas and w._interpretacion is None         # al abrir no se interpreta nada
    assert e.filas["DRENAJE"].estado == "reconocida" and e.filas["DRENAJE"].firma is None
    assert all(f.estado == "sin_interpretar" for p_, f in e.filas.items() if p_ != "DRENAJE")
    p = w.panel_reconocer
    assert p.btn_interpretar.isVisibleTo(p)                  # «Interpretar la hoja» disponible

    del w._interpretar_hoja                                  # interpretar de verdad: lo importado sigue reconocido
    w._interpretar_hoja()
    esperar_interpretacion(w)
    e = w.reconocer_estado
    assert e.filas["DRENAJE"].estado == "reconocida" and e.firma_hoja == w._firma_hoja_actual()
    assert not [p_ for p_, f in e.filas.items() if f.estado == "sin_interpretar"]
