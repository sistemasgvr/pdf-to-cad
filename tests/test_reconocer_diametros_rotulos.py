"""Filas «Diámetros» y «Rótulos del plano» del panel «Reconocer» (plan 2026-11-16, «reconocimiento desde el editor»,
Tarea 11).

  · En una hoja COMPUESTA los perfiles de los laterales están en las hojas de ORIGEN (la compuesta toma solo la
    planta): el ▶ de Diámetros los lee ahí (`Main._perfiles_de`) y da los MISMOS diámetros que hoy
    `recognition_trabajo.reconocer_hoja(perfiles_de=…)`.
  · La fila Diámetros dice cuántas tuberías quedan dudosas o sin dato (`diametro_plano.avisos`) y nombra las
    utilidades que aún no se reconocieron.
  · ▶ Rótulos = los rótulos de `reconocer_hoja`; su ⋯ ofrece «Leer rótulos ilegibles con la IA…» (la acción del
    menú IA).

Compuesta de dos plantas de DU06 (h.4 y h.5, índices 3 y 4) recortadas con el área sugerida: los perfiles CB-208…
de h.5 quedan FUERA de la compuesta."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("pymupdf")
from PySide6 import QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from nucleo import diametro_plano  # noqa: E402
from nucleo import reconocer_estado as RE  # noqa: E402
from reconocimiento import lectura_retenida as LR  # noqa: E402
from reconocimiento import recognition_trabajo as RT  # noqa: E402
from ui.comun import proceso  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
HOJAS = (3, 4)
UTILES = ("DRENAJE", "AGUA", "ALCANTARILLADO", "GAS")
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _esperar(cond, s=600):
    fin = time.time() + s
    while not cond():
        _app().processEvents()
        time.sleep(0.02)
        assert time.time() < fin, "tiempo agotado"


def _esperar_hilos():
    tr = proceso._TRABAJADORES.get(proceso.RETENEDOR)
    hilo = getattr(tr, "_hilo", None) if tr is not None else None
    while hilo is not None and hilo.is_alive():
        _app().processEvents()
        time.sleep(0.05)


_COMPOSITE = {}


def _composite():
    """Las plantas de h.4 y h.5 una al lado de la otra (área sugerida = la planta, sin los perfiles)."""
    if "comp" not in _COMPOSITE:
        import vector_pipeline as VP
        from hoja import area_sugerida as AS
        piezas, x = [], 0.0
        with fitz.open(str(DU06)) as src:
            for h in HOJAS:
                pg = src[h]
                r = AS.sugerir(pg)[0].rect
                W, H = pg.rect.width, pg.rect.height
                piezas.append(C.Piece(0, h, [r[0] / W, r[1] / H, r[2] / W, r[3] / H], x=x, y=0.0,
                                      src_scale=float(VP.detect_scale(pg))))
                x += (r[2] - r[0]) + 60.0
        _COMPOSITE["comp"] = C.Composite(piezas, bridges=False)
    return C.Composite.from_dict(_COMPOSITE["comp"].to_dict())


def _pdf_compuesta(tmp_path):
    with fitz.open(str(DU06)) as src:
        doc = C.build_document(_composite(), [src])
        ruta = str(tmp_path / "compuesta.pdf")
        doc.save(ruta)
        doc.close()
    return ruta


def _del_perfil(results):
    return sorted({(r.utility, (p.grosor or {}).get("diam_in"), (p.grosor or {}).get("fuente"))
                   for r in results for p in r.drawable if (p.grosor or {}).get("perfil_in")})


def _grosores(results):
    return {str(r.utility): [json.dumps(p.grosor or {}, sort_keys=True, default=repr) for p in r.drawable]
            for r in results}


@pytest.fixture(autouse=True)
def _soltar():
    LR.soltar()
    yield
    LR.soltar()


# ── el trabajo, sin ventana ──────────────────────────────────────────────────────────────────────────────
@needs_pdf
def test_compuesta_los_perfiles_de_origen_dan_los_mismos_diametros(tmp_path):
    ruta = _pdf_compuesta(tmp_path)
    perfiles = [(str(DU06), h) for h in HOJAS]
    kw = dict(zoom=1.0, hidden_ocgs=(), roles_by_utility={}, letters_off=(), join_routes=True, scale_ft_per_pt=None)
    hoy = RT.reconocer_hoja(ruta, 0, zoom=1.0, utilities=UTILES, perfiles_de=perfiles)
    assert ("GAS", 4.0, "perfil") in _del_perfil(hoy), "los perfiles de h.5 están FUERA de la compuesta"
    previas = [r for u in UTILES for r in RT.reconocer_parte(ruta, 0, u, "f", **kw)]
    v = RT.reconocer_parte(ruta, 0, "VALVULAS", "f", resultados_previos=previas, **kw)
    RT.poner_valvulas(previas, v)
    sin = RT.reconocer_parte(ruta, 0, "DIAMETROS", "f", resultados_previos=[*previas], **kw)
    assert not any(f == "perfil" for _u, _d, f in _del_perfil(sin)), "sin las hojas de origen no hay perfiles"
    previas = [r for u in UTILES for r in RT.reconocer_parte(ruta, 0, u, "f", **kw)]
    RT.poner_valvulas(previas, v)
    partes = RT.reconocer_parte(ruta, 0, "DIAMETROS", "f", resultados_previos=previas, perfiles_de=perfiles, **kw)
    assert _grosores(partes) == _grosores(hoy)
    hechos = next((list(r.anotaciones) for r in hoy if r.anotaciones), [])
    assert hechos
    assert repr(RT.reconocer_parte(ruta, 0, "ROTULOS", "f", **kw)["anotaciones"]) == repr(hechos)


# ── en el editor ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def ventana(monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    app = _app()
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.asistente import layer_dialog, recognition_dialog
    from ui.ventana import app_window
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)

    def no(*_a, **_k):
        raise AssertionError("el ▶ no abre «Capas de la hoja» ni la vista previa")
    monkeypatch.setattr(layer_dialog, "choose_sheet_layers", no)
    monkeypatch.setattr(recognition_dialog, "show_recognition_preview", no)
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet",
                        lambda parent, sources, comp, hidden, current_page=0, manual=False, **kw:
                        (_composite(), sources, hidden))
    w = app_window.Main()
    w._open_pdf_path(str(DU06))
    _esperar(lambda: not w.interpretando())
    yield w
    _esperar_hilos()
    LR.soltar()
    w._dirty = False
    w.close()
    app.processEvents()


def _play(w, parte):
    w.reconocer_parte(parte)
    _esperar(lambda: w._rec_actual is None)
    assert w.reconocer_estado.filas[parte].estado == "reconocida", (parte, w.reconocer_estado.filas[parte])


def _detalle(w, parte):
    return w.panel_reconocer.filas[parte].detalle.text()


@needs_pdf
def test_diametros_en_la_compuesta_como_hoy_y_su_fila_dice_lo_que_falta(ventana):
    w = ventana
    assert len(w.composite.pieces) == 2
    assert w._perfiles_de() == [(str(DU06), h) for h in HOJAS]
    e = w.reconocer_estado
    for u in RE.UTILIDADES:
        if u not in UTILES and e.filas[u].estado == "pendiente":
            e.filas[u].estado = "bloqueada"           # solo las de la prueba
    _play(w, "DRENAJE")
    # la fila nombra las utilidades que aún no se reconocieron
    det = _detalle(w, "DIAMETROS")
    for u in ("AGUA", "ALCANTARILLADO", "GAS"):
        assert w.panel_reconocer.filas["DIAMETROS"].ok
        assert RE.ETIQUETAS[u] in det, det
    assert RE.ETIQUETAS["DRENAJE"] not in det
    for u in UTILES[1:]:
        _play(w, u)
    assert RE.ETIQUETAS["GAS"] not in _detalle(w, "DIAMETROS")
    _play(w, "DIAMETROS")
    # los mismos diámetros que `reconocer_hoja` con los perfiles de las hojas de origen
    ruta, hoja = w._rec_ruta_hoja()
    hoy = {r.utility: r for r in RT.reconocer_hoja(
        ruta, hoja, zoom=w.zoom, utilities=UTILES, hidden_ocgs=tuple(w.hidden_ocgs or ()),
        roles_by_utility=w._roles_de_la_hoja(w.page_idx), scale_ft_per_pt=w._scale_override,
        perfiles_de=w._perfiles_de())}
    comparadas, del_perfil = 0, 0
    for p in w.pipes:
        u, k = p.get("reconocida"), p.get("reconocida_idx")
        if u not in hoy or not isinstance(k, int):
            continue
        esperado = diametro_plano.de_grosor(hoy[u].drawable[k].grosor)
        assert (p.get("diam_plano") or {}) == (esperado or {}), (u, k)
        comparadas += 1
        del_perfil += (esperado or {}).get("fuente") == "perfil"
    assert comparadas > 20 and del_perfil, (comparadas, del_perfil)
    # «N dudosas · M sin dato», contados como los avisos del editor
    avisos = diametro_plano.avisos(w.pipes)
    dudosas = sum(1 for a in avisos if w.pipes[a.pipe]["diam_plano"]["estado"] == "dudoso")
    sin_dato = len(avisos) - dudosas
    assert dudosas + sin_dato > 0
    det = _detalle(w, "DIAMETROS")
    if dudosas:
        assert (f"{dudosas} dudosas" if dudosas != 1 else "1 dudosa") in det, det
    if sin_dato:
        assert f"{sin_dato} sin dato" in det, det


@needs_pdf
def test_rotulos_como_hoy_y_su_menu_lee_los_ilegibles_con_la_ia(ventana, monkeypatch):
    w = ventana
    _play(w, "ROTULOS")
    ruta, hoja = w._rec_ruta_hoja()
    hoy = RT.reconocer_hoja(ruta, hoja, zoom=w.zoom, utilities=("DRENAJE",), scale_ft_per_pt=w._scale_override)
    hechos = next((list(r.anotaciones) for r in hoy if r.anotaciones), [])
    from nucleo import anotaciones as AN                     # lo que hoy deja la importación (sin repetir)
    assert hechos and repr(w.anotaciones) == repr(AN.juntar([], hechos))
    llamadas = []
    monkeypatch.setattr(type(w), "leer_anotaciones_con_ia", lambda self: llamadas.append(1))
    menu = w.panel_reconocer.filas["ROTULOS"].menu
    acc = [a for a in menu.actions() if a.text() == "Leer rótulos ilegibles con la IA…"]
    assert len(acc) == 1
    acc[0].trigger()
    assert llamadas == [1]
    # la misma acción que el menú IA
    assert any(a.text() == "Leer rótulos ilegibles con la IA…" for a in w.findChildren(type(acc[0]))
               if a is not acc[0])
