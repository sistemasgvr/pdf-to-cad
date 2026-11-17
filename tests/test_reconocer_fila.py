"""▶ y ▶ Todo del panel «Reconocer» en segundo plano (plan 2026-11-16, «reconocimiento desde el editor», Tarea 6).

Cada ▶ reconoce UNA parte de la hoja del editor en el trabajador «reconocer» (`recognition_trabajo.reconocer_parte`)
y el resultado entra solo al plano (`Main.importar_parte`), sin vista previa; ▶ Todo las hace en cola, en el orden
de `reconocer_estado.orden_todo`. Ventana real (Qt offscreen) sobre DU06 h.3 (índice 2)."""
import copy
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

fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtWidgets  # noqa: E402

from nucleo import reconocer_estado as RE  # noqa: E402
from reconocimiento import lectura_retenida as LR  # noqa: E402
from reconocimiento import recognition_trabajo as RT  # noqa: E402
from ui.comun import proceso  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
HOJA = 2                                                   # DU06 h.3 (la de test_importar_parte)
needs_pdf = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
SELLOS = ("reconocida", "reconocida_idx", "reconocida_firma")


@pytest.fixture
def win(monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    from ui.asistente import recognition_dialog
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)

    def sin_vista_previa(*a, **k):
        raise AssertionError("el ▶ no abre la vista previa")
    monkeypatch.setattr(recognition_dialog, "show_recognition_preview", sin_vista_previa)
    w = app_window.Main()
    w._open_pdf_path(str(DU06))
    w._load_page(HOJA)
    LR.soltar()
    yield w
    _esperar_hilo()
    LR.soltar()
    w._dirty = False
    w.close()
    app.processEvents()


def _app():
    return QtWidgets.QApplication.instance()


def _esperar(cond, s=600):
    fin = time.time() + s
    while not cond():
        _app().processEvents()
        time.sleep(0.02)
        assert time.time() < fin, "tiempo agotado"


def _esperar_hilo():
    """Sin proceso el hilo de un trabajo cancelado sigue hasta el final (no se puede matar): que termine antes de
    soltar la lectura que usa."""
    tr = proceso._TRABAJADORES.get(proceso.RETENEDOR)
    hilo = getattr(tr, "_hilo", None) if tr is not None else None
    while hilo is not None and hilo.is_alive():
        _app().processEvents()
        time.sleep(0.05)


def _listo(w, *partes, estado="pendiente"):
    """La hoja «interpretada» (Tarea 9 lo hará al abrir): las filas pedidas pendientes, las demás bloqueadas."""
    e = RE.nuevo()
    for p, f in e.filas.items():
        f.estado = estado if (not partes or p in partes) else "bloqueada"
    w.reconocer_estado = e
    w._refrescar_panel_reconocer()
    return e


def _foto(lista, sin=SELLOS):
    return json.dumps([{k: v for k, v in d.items() if k not in sin} for d in lista], sort_keys=True, default=repr)


def _a_mano(x0=5.0, y0=5.0):
    return {"layer": "AGUA", "pts": [(x0, y0), (x0 + 40.0, y0)], "ab": False, "diam": 12.0, "diam_unit": "in",
            "material": "PVC"}


class _Falso:
    """Trabajador de mentira: anota cada parte pedida y la termina al volver al bucle de eventos."""

    def __init__(self, fallan=()):
        self.partes, self.fallan = [], set(fallan)

    def enviar(self, t):
        parte = t.args[2]
        self.partes.append(parte)
        if parte == "VALVULAS":
            res = {"valvulas": [], "avisos": []}
        elif parte == "DIAMETROS":
            res = list(t.kwargs.get("resultados_previos") or [])
        elif parte == "ROTULOS":
            res = {"anotaciones": []}
        else:
            res = []
        err = "falló a propósito" if parte in self.fallan else ""
        t._dueno = self
        QtCore.QTimer.singleShot(0, lambda: t._fin(None if err else res, err))
        return t

    def cancelar(self, t):
        t._fin(None, "cancelado")


@needs_pdf
def test_play_agua_agrega_al_editor_sin_vista_previa(win):
    e = _listo(win, "AGUA", "DRENAJE")
    pasos = len(win._undo)
    win.reconocer_parte("AGUA")
    assert e.filas["AGUA"].estado == "reconociendo"
    assert win.canvas._recognition_readonly                # navegar sí, editar no (como hoy)
    _esperar(lambda: win._rec_actual is None)
    assert not win.canvas._recognition_readonly
    f = win.reconocer_estado.filas["AGUA"]
    assert f.estado == "reconocida" and f.hechos > 0
    assert f.firma == win._firma_parte_actual("AGUA")
    assert all({"texto", "nivel", "rect"} <= set(v) for v in f.verificar)
    assert win.pipes and all(p.get("reconocida") == "AGUA" for p in win.pipes)
    assert all(p.get("reconocida_firma") == win._firma_lectura() for p in win.pipes)
    assert len(win._undo) == pasos + 1                     # un solo paso de deshacer
    nuevo = (_foto(win.pipes), _foto(win.structures))
    # mismas líneas que el asistente de siempre con esa utilidad
    viejo = RT.reconocer_hoja(win.work_pdf_path or win.pdf_path, HOJA, zoom=win.zoom, utilities=("AGUA",),
                              hidden_ocgs=win.hidden_ocgs, roles_by_utility=win._roles_de_la_hoja(HOJA),
                              letters_off=win._letters_off, scale_ft_per_pt=win._scale_override)
    for r in viejo:
        r.valvulas = []                                    # las válvulas son otra fila
    win._reset_model()
    win._import_recognized_pipes(viejo)
    assert (_foto(win.pipes), _foto(win.structures)) == nuevo


def test_todo_respeta_el_orden(win, monkeypatch):
    falso = _Falso(fallan={"DRENAJE"})
    monkeypatch.setattr(proceso, "trabajador", lambda nombre="principal": falso)
    e = _listo(win, "DRENAJE", "AGUA", "ALCANTARILLADO", "VALVULAS", "DIAMETROS", "ROTULOS")
    win.reconocer_todo()
    _esperar(lambda: win._rec_actual is None and not win._rec_cola, 30)
    assert falso.partes == ["DRENAJE", "AGUA", "ALCANTARILLADO", "VALVULAS", "DIAMETROS", "ROTULOS"]
    assert e.filas["DRENAJE"].estado == "error"          # una falla no detiene la cola
    assert all(e.filas[p].estado == "reconocida" for p in ("AGUA", "ALCANTARILLADO", "VALVULAS", "DIAMETROS",
                                                           "ROTULOS"))
    assert e.filas["GAS"].estado == "bloqueada"
    assert win._recog_busy is None and not win.canvas._recognition_readonly


def test_todo_vuelve_a_mirar_cada_fila_cuando_le_toca(win, monkeypatch):
    falso = _Falso(fallan={"AGUA"})
    monkeypatch.setattr(proceso, "trabajador", lambda nombre="principal": falso)
    e = _listo(win, "AGUA", "VALVULAS", "DIAMETROS")
    win.reconocer_todo()
    _esperar(lambda: win._rec_actual is None and not win._rec_cola, 30)
    # el agua falló: válvulas y diámetros ya no se pueden (ninguna utilidad reconocida)
    assert falso.partes == ["AGUA"]
    assert e.filas["VALVULAS"].estado == "pendiente" and e.filas["DIAMETROS"].estado == "pendiente"


@needs_pdf
def test_repetir_sin_cambios_usa_la_cache(win, monkeypatch):
    _listo(win, "AGUA")
    win.reconocer_parte("AGUA")
    _esperar(lambda: win._rec_actual is None)
    antes, pasos = _foto(win.pipes), len(win._undo)

    def no(*_a, **_k):
        raise AssertionError("no debe pedir otro trabajo")
    monkeypatch.setattr(proceso, "trabajador", no)
    monkeypatch.setattr(win, "_preguntar_reemplazo", lambda parte: "agregar")
    win.reconocer_parte("AGUA")
    assert win._rec_actual is None
    assert _foto(win.pipes) == antes and len(win._undo) == pasos    # nada nuevo: ni líneas ni paso de deshacer
    assert win.reconocer_estado.filas["AGUA"].estado == "reconocida"


@needs_pdf
def test_cancelar_deja_el_editor_igual(win, monkeypatch):
    """Con el trabajador de verdad (proceso aparte): cancelar lo mata; el próximo ▶ vuelve a leer la hoja."""
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    try:
        win.pipes.append(_a_mano())
        win._refresh_lists()
        e = _listo(win, "AGUA")
        antes, pasos = _foto(win.pipes), len(win._undo)
        capas = []
        orig = win._rec_avance
        monkeypatch.setattr(win, "_rec_avance", lambda t, gen, a: (capas.append(a[0]), orig(t, gen, a)))
        win.reconocer_parte("AGUA")
        _esperar(lambda: "capa" in capas or win._rec_actual is None, 300)
        assert win._rec_actual is not None, "terminó antes de poder cancelarlo"
        win.cancelar_reconocer()
        assert win._rec_actual is None and win._recog_busy is None
        assert e.filas["AGUA"].estado == "pendiente"
        assert not win.canvas._recognition_readonly
        for _ in range(30):
            _app().processEvents()
            time.sleep(0.02)
        assert _foto(win.pipes) == antes and len(win._undo) == pasos
        win.reconocer_parte("AGUA")                         # la hoja se vuelve a leer en un proceso nuevo
        _esperar(lambda: win._rec_actual is None, 600)
        assert e.filas["AGUA"].estado == "reconocida"
        assert sum(1 for p in win.pipes if p.get("reconocida") == "AGUA") > 0
    finally:
        proceso.trabajador(proceso.RETENEDOR).parar()


@needs_pdf
def test_resultado_tardio_tras_abrir_otro_proyecto_se_descarta(win):
    _listo(win, "AGUA")
    win.reconocer_parte("AGUA")
    t = win._rec_actual["tarea"]
    win._open_pdf_path(str(DU06))                        # otro proyecto mientras reconoce
    win._load_page(HOJA)
    assert win._rec_actual is None and win._recog_busy is None
    assert all(f.estado != "reconociendo" for f in win.reconocer_estado.filas.values())
    _esperar_hilo()
    for _ in range(20):
        _app().processEvents()
        time.sleep(0.02)
    # lo que llegue tarde de aquel ▶ no toca nada
    t.avance.emit(("hecha", 0, 1, "AGUA", [[(0.0, 0.0), (10.0, 10.0)]]))
    t.terminado.emit([object()], "")
    _app().processEvents()
    assert win.pipes == [] and not win._undo
    assert win._recog_dibujo is None
    assert win.reconocer_estado.filas["AGUA"].estado != "reconocida"


def test_desactualizada_pregunta(win, monkeypatch):
    falso = _Falso()
    monkeypatch.setattr(proceso, "trabajador", lambda nombre="principal": falso)
    e = _listo(win, "AGUA")
    e.filas["AGUA"].estado = "desactualizada"
    importados = []
    monkeypatch.setattr(win, "importar_parte",
                        lambda parte, res, reemplazar=False, firma=None: importados.append((parte, reemplazar)) or 0)
    preguntas = []
    respuesta = [None]
    monkeypatch.setattr(win, "_preguntar_reemplazo", lambda parte: preguntas.append(parte) or respuesta[0])
    win.reconocer_parte("AGUA")                            # «Cancelar»: nada
    assert preguntas == ["AGUA"] and falso.partes == [] and e.filas["AGUA"].estado == "desactualizada"
    respuesta[0] = "reemplazar"
    win.reconocer_parte("AGUA")
    _esperar(lambda: win._rec_actual is None, 30)
    assert importados == [("AGUA", True)] and e.filas["AGUA"].estado == "reconocida"
    e.filas["AGUA"].estado = "desactualizada"
    respuesta[0] = "agregar"
    win.reconocer_parte("AGUA")                            # misma firma: de la caché, sin preguntar al trabajador
    _esperar(lambda: win._rec_actual is None, 30)
    assert importados[-1] == ("AGUA", False) and falso.partes == ["AGUA"]


def test_sin_pantalla_la_pregunta_agrega(win):
    assert not win.isVisible()
    assert win._preguntar_reemplazo("AGUA") == "agregar"


@needs_pdf
def test_valvulas_tras_reabrir_reconoce_su_red_sin_importarla(win, monkeypatch):
    _listo(win, "AGUA", "VALVULAS")
    win.reconocer_parte("AGUA")
    _esperar(lambda: win._rec_actual is None)
    n_agua = sum(1 for p in win.pipes if p.get("reconocida") == "AGUA")
    assert n_agua
    win._resultados_partes.clear()                       # como al reabrir el proyecto: sin resultados en memoria
    win._rec_cache().clear()
    real = proceso.trabajador
    pedidas = []

    def espia(nombre="principal"):
        tr = real(nombre)

        class _E:
            def enviar(self, t):
                pedidas.append(t.args[2])
                return tr.enviar(t)
        return _E()
    monkeypatch.setattr(proceso, "trabajador", espia)
    win.reconocer_parte("VALVULAS")
    _esperar(lambda: win._rec_actual is None)
    assert pedidas == ["AGUA", "VALVULAS"]
    assert sum(1 for p in win.pipes if p.get("reconocida") == "AGUA") == n_agua   # el agua no se importa otra vez
    assert win.reconocer_estado.filas["VALVULAS"].estado == "reconocida"
    assert win.reconocer_estado.filas["AGUA"].estado == "reconocida"
    assert any(v.get("utilidad") == "AGUA" for v in win.valvulas)


class _Lento(_Falso):
    """No termina solo: el trabajo queda corriendo."""

    def enviar(self, t):
        self.partes.append(t.args[2])
        self.tarea = t
        t._dueno = self
        return t


def test_otro_reconocimiento_que_toma_la_tarjeta_cancela_el_play(win, monkeypatch):
    lento = _Lento()
    monkeypatch.setattr(proceso, "trabajador", lambda nombre="principal": lento)
    e = _listo(win, "AGUA")
    win.reconocer_parte("AGUA")
    t = lento.tarea
    assert e.filas["AGUA"].estado == "reconociendo" and win._rec_avance_abierto
    win._end_recognition_busy()                           # lo que hace el asistente de siempre al empezar
    assert win._rec_actual is None and not win._rec_avance_abierto
    assert e.filas["AGUA"].estado == "pendiente" and t.hecha
    t.terminado.emit([object()], "")                      # lo tardío no entra
    assert win.pipes == [] and e.filas["AGUA"].estado == "pendiente"


def test_la_cache_importa_un_resultado_intacto(win, monkeypatch):
    falso = _Falso()
    monkeypatch.setattr(proceso, "trabajador", lambda nombre="principal": falso)
    _listo(win, "VALVULAS")
    e = win.reconocer_estado
    e.filas["AGUA"].estado = "reconocida"
    win._resultados_partes = {"AGUA": []}
    vistos = []

    def importar(parte, res, reemplazar=False, firma=None):
        vistos.append(list(res["valvulas"]))
        res["valvulas"].append("cambiado por la importación")
        return 0
    monkeypatch.setattr(win, "importar_parte", importar)
    win.reconocer_parte("VALVULAS")
    _esperar(lambda: win._rec_actual is None, 30)
    win.reconocer_parte("VALVULAS")                       # de la caché
    assert falso.partes == ["VALVULAS"] and vistos == [[], []]


# ── revisión de código 2026-11-16 ──
@needs_pdf
def test_deshacer_un_play_deja_la_fila_como_estaba(win):
    """Ctrl+Z quita lo que trajo el ▶ y su fila vuelve a «pendiente»; rehacer la deja reconocida otra vez."""
    e = _listo(win, "AGUA", "DRENAJE")
    win.reconocer_parte("AGUA")
    _esperar(lambda: win._rec_actual is None)
    assert e.filas["AGUA"].estado == "reconocida" and win.pipes and "AGUA" in win._resultados_partes
    firma = e.filas["AGUA"].firma
    win.undo()
    f = win.reconocer_estado.filas["AGUA"]
    assert win.pipes == [] and f.estado == "pendiente" and f.firma is None and f.hechos == 0
    assert "AGUA" not in win._resultados_partes             # válvulas y diámetros ya no la usan
    assert RE.puede(win.reconocer_estado, "VALVULAS")[0] is False
    win.redo()
    f = win.reconocer_estado.filas["AGUA"]
    assert win.pipes and f.estado == "reconocida" and f.firma == firma


def test_deshacer_otra_cosa_no_toca_las_filas(win):
    """Deshacer un cambio que no es un ▶ deja las filas como están."""
    e = _listo(win, "AGUA")
    e.filas["AGUA"].estado, e.filas["AGUA"].firma, e.filas["AGUA"].hechos = "reconocida", "f", 3
    win._push()
    win.pipes.append(_a_mano())
    win.undo()
    f = win.reconocer_estado.filas["AGUA"]
    assert (f.estado, f.firma, f.hechos) == ("reconocida", "f", 3)


def test_unir_tramos_deja_la_fila_desactualizada(win):
    e = _listo(win, "ELECTRICO")
    f = e.filas["ELECTRICO"]
    f.estado, f.firma = "reconocida", win._firma_parte_actual("ELECTRICO")
    win._unir_tramos_parte("ELECTRICO", False)
    assert f.estado == "desactualizada" and f.unir_tramos is False


def test_reemplazar_en_proyecto_viejo_quita_lo_reconocido_y_no_lo_dibujado(win):
    """Sin la marca del panel (proyecto de antes), «Reemplazar» quita las reconocidas por su `origen`."""
    vieja = dict(_a_mano(), origen="reconocido")
    a_mano = _a_mano(100.0, 100.0)
    win.pipes = [vieja, a_mano]
    win._quitar_reconocidas("AGUA")
    assert win.pipes == [a_mano]


@needs_pdf
def test_ajustar_capas_usa_la_interpretacion_sin_releer_la_hoja(win, monkeypatch):
    """Reporte 2026-11-16 («esta opción demora bastante»): «Ajustar capas…» leía `page_layers` en la ventana (~14 s
    en la compuesta de DU06). Con la hoja interpretada usa sus capas: las MISMAS que daría leerla."""
    from hoja import pdf_layers
    from ui.asistente import recognition_dialog
    _listo(win, "DRENAJE")
    esperadas = [L for L in pdf_layers.without_letters(pdf_layers.page_layers(win.doc, HOJA), win._letters_off)
                 if L["name"] not in set(win.hidden_ocgs)]
    win._interpretacion = {"layers": pdf_layers.page_layers(win.doc, HOJA), "firma": None}

    def no_leer(*_a, **_k):
        raise AssertionError("no debe volver a leer la hoja")
    monkeypatch.setattr(pdf_layers, "page_layers", no_leer)
    vistas = []
    monkeypatch.setattr(recognition_dialog, "choose_layer_roles",
                        lambda parent, layers, utility=None, current_roles=None: vistas.append(layers) or None)
    win.ajustar_capas_parte("DRENAJE")
    assert vistas == [esperadas]
