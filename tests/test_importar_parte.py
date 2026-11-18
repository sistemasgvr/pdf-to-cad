"""Importar UNA parte reconocida encima de lo dibujado (plan 2026-11-16, «reconocimiento desde el editor», Tarea 4).

Cada ▶ del panel «Reconocer» trae una parte (una utilidad, las válvulas, los diámetros o los rótulos) y
`Main.importar_parte` la suma al editor: un solo paso de deshacer, sin repetir lo ya dibujado y sin la maquinaria de
respaldo del asistente. Ventana real (Qt offscreen) sobre DU06 h.3 (índice 2)."""
import copy
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("pymupdf")
from PySide6 import QtWidgets  # noqa: E402

from nucleo import valvulas as V  # noqa: E402
from reconocimiento import lectura_retenida as LR  # noqa: E402
from reconocimiento import recognition_trabajo as RT  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
HOJA = 2                                                   # DU06 h.3
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")


@pytest.fixture
def win(monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    w = app_window.Main()
    w._open_pdf_path(str(DU06))
    w._load_page(HOJA)
    LR.soltar()
    yield w
    LR.soltar()
    w._dirty = False
    w.close()
    app.processEvents()


def _parte(w, parte, previos=None):
    return RT.reconocer_parte(w.work_pdf_path or w.pdf_path, HOJA, parte, "prueba", zoom=w.zoom,
                              resultados_previos=previos)


def _foto(lista, sin=("reconocida", "reconocida_idx")):
    return json.dumps([{k: v for k, v in d.items() if k not in sin} for d in lista], sort_keys=True, default=repr)


def _a_mano(x0=5.0, y0=5.0):
    return {"layer": "AGUA", "pts": [(x0, y0), (x0 + 40.0, y0)], "ab": False, "diam": 12.0, "diam_unit": "in",
            "material": "PVC"}


@needs_pdf
def test_importar_agua_igual_que_el_flujo_viejo(win):
    r = _parte(win, "AGUA")
    assert r[0].drawable
    n = win.importar_parte("AGUA", copy.deepcopy(r))
    assert n > 0
    nuevo = (_foto(win.pipes), _foto(win.structures))
    assert all(p.get("reconocida") == "AGUA" for p in win.pipes)
    assert sorted(p["reconocida_idx"] for p in win.pipes) == sorted(set(p["reconocida_idx"] for p in win.pipes))
    win._reset_model()
    win._import_recognized_pipes(copy.deepcopy(r))
    assert (_foto(win.pipes), _foto(win.structures)) == nuevo


@needs_pdf
def test_no_repite_lo_dibujado(win):
    r = _parte(win, "AGUA")
    n1 = win.importar_parte("AGUA", copy.deepcopy(r))
    antes = _foto(win.pipes)
    pasos = len(win._undo)
    assert win.importar_parte("AGUA", copy.deepcopy(r)) == 0
    assert _foto(win.pipes) == antes and n1 > 0
    assert len(win._undo) == pasos                           # nada cambió: ningún paso de deshacer


@needs_pdf
def test_un_paso_de_deshacer(win):
    win.pipes.append(_a_mano())
    win._refresh_lists()
    antes = _foto(win.pipes)
    r = _parte(win, "AGUA")
    pasos = len(win._undo)
    win.importar_parte("AGUA", copy.deepcopy(r))
    assert len(win._undo) == pasos + 1
    assert win._dirty
    otra = next(p for p in win.pipes if p.get("reconocida") == "AGUA")
    win._push()
    otra["pts"] = [(x + 30.0, y) for x, y in otra["pts"]]                  # el usuario la movió
    pasos = len(win._undo) - 2
    win.importar_parte("AGUA", copy.deepcopy(r), reemplazar=True)      # quitar + poner = UN paso
    assert all(p is not otra for p in win.pipes)
    assert len(win._undo) == pasos + 3
    win.undo()
    assert any(p["pts"] == otra["pts"] for p in win.pipes)              # deshacer = vuelve la movida
    win.undo(); win.undo()
    assert _foto(win.pipes) == antes


@needs_pdf
def test_reemplazar_no_toca_lo_dibujado_a_mano(win):
    mano = _a_mano()
    win.pipes.append(mano)
    win._refresh_lists()
    r = _parte(win, "AGUA")
    win.importar_parte("AGUA", copy.deepcopy(r))
    marcadas = _foto([p for p in win.pipes if p.get("reconocida") == "AGUA"])
    # el usuario edita una reconocida y dibuja otra a mano; reemplazar quita solo las reconocidas
    mano2 = _a_mano(5.0, 60.0)
    win.pipes.append(mano2)
    n = win.importar_parte("AGUA", copy.deepcopy(r), reemplazar=True)
    assert n > 0
    assert sum(1 for p in win.pipes if p is mano or p is mano2) == 2
    assert _foto([p for p in win.pipes if p.get("reconocida") == "AGUA"]) == marcadas
    sueltas = [s for s in win.structures if s.get("standalone") and s.get("utility") == "AGUA"]
    assert len(sueltas) == len({(round(s["x"], 3), round(s["y"], 3)) for s in sueltas})   # sin repetir


@needs_pdf
def test_valvulas_antes_que_su_red_se_pegan_despues(win):
    r = _parte(win, "AGUA")
    v = _parte(win, "VALVULAS", previos=copy.deepcopy(r))   # reconocidas junto a la red…
    agua = [x for x in v["valvulas"] if x.get("utilidad") == "AGUA"]
    assert agua
    assert win.importar_parte("VALVULAS", v) == len(v["valvulas"])   # …pero importadas ANTES que ella
    sin_tubo = [x for x in win.valvulas if x.get("utilidad") == "AGUA"]
    assert all((x["x"], x["y"]) == (x["x_pdf"], x["y_pdf"]) for x in sin_tubo)   # no había dónde pegarlas
    win.importar_parte("AGUA", r)
    pegadas = 0
    for x in win.valvulas:
        if x.get("utilidad") != "AGUA":
            continue
        rel = V.relacion(dict(x=x["x"], y=x["y"], utilidad="AGUA"), win.pipes, 0.01 * win.zoom)
        pegadas += rel is not None
    assert pegadas >= len(agua) // 2 and pegadas > 0         # ahora sí están sobre su tubería


@needs_pdf
def test_diametros_actualiza_las_reconocidas_sin_pisar_lo_elegido(win):
    r = _parte(win, "AGUA") + _parte(win, "DRENAJE")
    win.importar_parte("AGUA", [r[0]])
    win.importar_parte("DRENAJE", [r[1]])
    elegida = next(p for p in win.pipes if p.get("reconocida") == "DRENAJE")
    elegida["diam"], elegida["diam_elegido"] = 99.0, True
    # simula lo que dicen los perfiles: todas las líneas de agua con 6"
    previos = RT.reconocer_parte(win.work_pdf_path or win.pdf_path, HOJA, "DIAMETROS", "prueba", zoom=win.zoom,
                                 resultados_previos=r)
    for res in previos:
        for pl in res.drawable:
            pl.grosor = {"estado": "leido", "diam_in": 6.0, "fuente": "perfil"}
            pl.diam_in = 6.0
    por_defecto = [p for p in win.pipes if p.get("reconocida") and not p.get("diam_elegido")]
    assert por_defecto
    pasos = len(win._undo)
    n = win.importar_parte("DIAMETROS", previos)
    assert n > 0 and len(win._undo) == pasos + 1
    assert elegida["diam"] == 99.0                           # lo elegido por el usuario no se toca
    sin_elegir = [p for p in win.pipes if p.get("reconocida") and p is not elegida]
    assert all(p["diam_plano"]["estado"] == "leido" for p in sin_elegir)
    assert all(p["diam"] == 6.0 and p["diam_elegido"] for p in por_defecto)


@needs_pdf
def test_reemplazar_no_borra_lo_dibujado_a_mano_unido_a_una_reconocida(win):
    from nucleo import unir_utilidades as U
    r = _parte(win, "AGUA")
    win.importar_parte("AGUA", copy.deepcopy(r), firma="f1")
    k = next(i for i, p in enumerate(win.pipes) if p.get("reconocida") == "AGUA")
    fin = win.pipes[k]["pts"][-1]
    win.pipes.append(dict(_a_mano(), pts=[tuple(fin), (fin[0] + 40.0, fin[1] + 40.0)]))   # sigue a mano
    fpp = win.scale / win.zoom
    plan = U.planificar(win.pipes, [k, len(win.pipes) - 1], k, fpp)
    assert plan.ok
    win.pipes[k] = plan.pipe
    del win.pipes[-1]
    unida = win.pipes[k]
    win.importar_parte("AGUA", copy.deepcopy(r), reemplazar=True, firma="f1")
    assert any(p is unida for p in win.pipes)              # lo dibujado a mano sigue (con lo unido a ella)


@needs_pdf
def test_diametros_solo_de_la_misma_lectura(win):
    r = _parte(win, "AGUA")
    win.importar_parte("AGUA", [r[0]], firma="f1")
    assert all(p["reconocida_firma"] == "f1" for p in win.pipes)
    for pl in r[0].drawable:
        pl.grosor = {"estado": "leido", "diam_in": 6.0, "fuente": "perfil"}
        pl.diam_in = 6.0
    assert win.importar_parte("DIAMETROS", r, firma="otra") == 0
    assert win.importar_parte("DIAMETROS", r, firma="f1") > 0
