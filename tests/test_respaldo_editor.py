"""«Cancelar» en el asistente abierto desde el editor deja el editor como estaba.

Reporte del usuario (2026-10-07): con lo reconocido ya importado, Herramientas →
«Componer hoja de trabajo…» y Cancelar dejaba la hoja SIN líneas: al aceptar el
compositor la hoja se recargaba y el modelo se vaciaba antes de «Capas» y de la
vista previa. Ahora cualquier salida sin cambiar la hoja repone hoja, líneas, deshacer y
«cambios sin guardar» (`respaldo_editor`).

Desde el flujo nuevo (plan 2026-11-16, Tarea 9) el asistente es SOLO «Componer hoja»: aceptar con otra
hoja la carga en el editor y la interpreta para el panel «Reconocer» (sin «Capas de la hoja» ni vista
previa); cancelar, aceptar sin cambios o no poder cargar la hoja nueva dejan el editor como estaba.
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from ui.ventana import app_window as _aw  # noqa: E402

_ASISTENTE = _aw.Main._run_recognition_wizard         # el de verdad (el fixture lo cambia)

LINEA = {"layer": "DRENAJE", "pts": [(10, 10), (200, 10), (200, 120)], "name": "", "diam": 12.0}
HOJA = [0.0, 0.0, 1.0, 1.0]
AREA = [0.0, 0.0, 0.5, 1.0]


def _pdf(path, pages=3):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=600, height=400)
        pg.insert_text((50, 60), f"plano hoja {i + 1}")
        pg.draw_line((50, 200), (550, 200))
    doc.save(str(path)); doc.close()
    return str(path)


_INTERPRETADAS = []          # cada `_interpretar_hoja` pedida (la interpretación tiene sus pruebas: aquí no corre)


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app, monkeypatch):
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    _INTERPRETADAS.clear()
    monkeypatch.setattr(app_window.Main, "_interpretar_hoja", lambda self: _INTERPRETADAS.append(self.page_idx))
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    # «Hay cambios sin guardar. ¿Deseas guardarlos?» → Descartar (lo peor para el caso)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.Discard)
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: QtWidgets.QMessageBox.Cancel)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def _editor_con_lineas(win, tmp_path, clip, manual=False):
    """Como tras el asistente: hoja 2 en el editor y una línea importada sin guardar."""
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win.composite = C.Composite([C.Piece(0, 1, list(clip))], manual=manual, bridges=not manual)
    win._apply_composite()
    QtWidgets.QApplication.instance().processEvents()   # huella «guardado» de la hoja recién cargada
    win._push()
    win.pipes.append(dict(LINEA))
    for _ in range(2):            # el 2.º refresco completa los campos por defecto de las cajas
        win._refresh_lists(); win._update_ui(); win._redraw()


def _foto(win):
    pm = win.canvas.pixmap_item.pixmap()
    return dict(pipes=json.dumps(win.pipes, sort_keys=True, default=str),
                structures=json.dumps(win.structures, sort_keys=True, default=str),
                doc=win.doc, page=win.page_idx, work=win.work_pdf_path, tmp=win._tmp_composite,
                comp=win.composite.to_dict(), hidden=list(win.hidden_ocgs), scale=win.scale,
                image=(pm.size(), pm.cacheKey()), undo=len(win._undo), dirty=win._dirty)


def _stubs(monkeypatch, win, compositor):
    """Respuestas de «Componer hoja», en orden. «Capas de la hoja» y la vista previa ya no se abren."""
    from ui.ventana import app_window
    from ui.asistente import layer_dialog
    rd = app_window.recognition_dialog

    def compose(parent, sources, comp, hidden, **kw):
        nuevo = compositor.pop(0)
        return None if nuevo is None else (nuevo, list(sources), dict(hidden or {}))

    def no(*_a, **_k):
        raise AssertionError("el flujo nuevo no abre «Capas de la hoja» ni la vista previa")

    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", compose)
    monkeypatch.setattr(layer_dialog, "choose_sheet_layers", no)
    monkeypatch.setattr(rd, "show_recognition_preview", no)


def _otra():
    return C.Composite([C.Piece(0, 1, [0.0, 0.0, 0.6, 1.0])])


def _que_falle_al_cargar(monkeypatch, win):
    """La hoja nueva se arma, se empieza a cargar (el modelo y el panel se vacían) y falla."""
    cargar = win._load_sheet_busy

    def fallar(i):
        cargar(i)
        raise RuntimeError("falló al cargar la hoja")
    monkeypatch.setattr(win, "_load_sheet_busy", fallar)


@pytest.mark.parametrize("base", [HOJA, AREA], ids=["hoja_entera", "area"])
@pytest.mark.parametrize("donde", ["compositor", "cargar_falla", "sin_cambios"])
def test_cancelar_deja_el_editor_como_estaba(win, app, tmp_path, monkeypatch, base, donde):
    _editor_con_lineas(win, tmp_path, base)
    antes = _foto(win)
    tmp_nuevo = []
    if donde == "compositor":
        _stubs(monkeypatch, win, [None])
    elif donde == "cargar_falla":
        _stubs(monkeypatch, win, [_otra()])
        _que_falle_al_cargar(monkeypatch, win)
        escribir = win._write_tmp_composite

        def anotar(*a, **k):
            tmp_nuevo.append(escribir(*a, **k))
            return tmp_nuevo[-1]
        monkeypatch.setattr(win, "_write_tmp_composite", anotar)
    else:
        misma = C.Composite.from_dict(win.composite.to_dict())
        misma.last_view = [0, 1]                     # solo dónde miraba el compositor
        _stubs(monkeypatch, win, [misma])

    win.compose_sheet()
    app.processEvents()

    despues = _foto(win)
    assert despues == antes
    assert not win.doc.is_closed                     # el PDF de la hoja de antes, vivo
    assert "plano hoja 2" in win.doc[win.page_idx].get_text()
    assert win._respaldo is None
    assert not _INTERPRETADAS                        # la hoja no cambió: nada que interpretar
    if antes["tmp"]:
        assert os.path.isfile(antes["tmp"])          # el temporal de la hoja de antes sigue
    for tmp in tmp_nuevo:                            # y el de la hoja nueva se borró
        assert not os.path.isfile(tmp)
    assert win._has_real_changes()                   # sigue «sin guardar»


def test_aceptar_otra_hoja_la_carga_e_interpreta_y_suelta_la_de_antes(win, app, tmp_path, monkeypatch):
    _editor_con_lineas(win, tmp_path, AREA)
    doc_antes, tmp_antes = win.doc, win._tmp_composite
    _stubs(monkeypatch, win, [C.Composite([C.Piece(0, 2, HOJA)])])
    preguntas = []                                   # otra hoja (no solo agrega): se pregunta AL FINAL
    monkeypatch.setattr(win, "_preguntar_reemplazar_hoja", lambda: preguntas.append(1) or "reemplazar")
    win.compose_sheet()
    app.processEvents()
    assert preguntas == [1]
    assert win.pipes == []                           # hoja nueva: lo reconocido se pide con el ▶ del panel
    assert win.page_idx == 2 and not win.doc.is_closed
    assert doc_antes.is_closed and not os.path.isfile(tmp_antes)
    assert win._respaldo is None
    assert _INTERPRETADAS == [2]                     # la hoja nueva se interpreta para el panel


def test_hoja_guardada_sigue_guardada_al_cancelar(win, app, tmp_path, monkeypatch):
    _editor_con_lineas(win, tmp_path, HOJA)
    win._dirty = False                               # como recién guardado
    app.processEvents()
    assert not win._has_real_changes()
    _stubs(monkeypatch, win, [None])
    win.compose_sheet()
    app.processEvents()
    assert len(win.pipes) == 1
    assert not win._has_real_changes() and not win.windowTitle().startswith("*")


def test_sin_trabajo_aceptar_deja_la_hoja_nueva(win, app, tmp_path, monkeypatch):
    """Editor sin nada que perder: aceptar deja cargada la hoja nueva y no se guarda ningún respaldo."""
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win.composite = C.Composite([C.Piece(0, 1, HOJA)])
    win._apply_composite()
    _stubs(monkeypatch, win, [C.Composite([C.Piece(0, 2, HOJA)])])
    win.compose_sheet()
    app.processEvents()
    assert win.page_idx == 2 and "plano hoja 3" in win.doc[2].get_text()
    assert win._respaldo is None and _INTERPRETADAS == [2]


def test_escaneo_sin_cambios_no_borra_lo_dibujado(win, app, tmp_path, monkeypatch):
    _editor_con_lineas(win, tmp_path, HOJA, manual=True)
    antes = _foto(win)
    misma = C.Composite.from_dict(win.composite.to_dict())
    misma.last_view = [0, 1]                         # solo dónde miraba el compositor
    _stubs(monkeypatch, win, [misma])
    aplicadas = []
    monkeypatch.setattr(win, "_apply_composite", lambda: aplicadas.append(1))
    win.compose_scan_sheet()
    app.processEvents()
    assert not aplicadas and _foto(win) == antes and win._respaldo is None


def test_escaneo_con_otra_hoja_la_carga(win, app, tmp_path, monkeypatch):
    monkeypatch.setattr(_aw.Main, "_preguntar_reemplazar_hoja", lambda self: "reemplazar")   # hay líneas: se pregunta al final
    _editor_con_lineas(win, tmp_path, HOJA, manual=True)
    doc_antes = win.doc
    otra = C.Composite([C.Piece(0, 1, AREA)], manual=True, bridges=False)
    _stubs(monkeypatch, win, [otra])
    win.compose_scan_sheet()
    app.processEvents()
    assert win.pipes == [] and win.composite.pieces[0].clip == AREA
    assert doc_antes.is_closed and win._respaldo is None
    assert not _INTERPRETADAS and win._reconocer_escaneo    # escaneo: a mano, nada que interpretar


def test_abrir_pdf_y_cancelar_el_compositor_no_carga_nada(win, app, tmp_path, monkeypatch):
    """Pedido del usuario 2026-10-28: al abrir un PDF, cancelar (o cerrar) «Componer hoja» no carga
    nada en el editor: no se importó nada. Con un editor vacío queda vacío; con otro PDF abierto,
    ése sigue (mismo documento abierto, misma hoja, mismas líneas)."""
    from ui.ventana import app_window
    import detect
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", _ASISTENTE)
    monkeypatch.setattr(detect, "classify_page", lambda page: ("vector", {"n_paths": 500}))
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", lambda *a, **k: None)
    win._open_pdf_path(_pdf(tmp_path / "nuevo.pdf"))
    app.processEvents()
    assert win.canvas.pixmap_item is None and win.doc is None and win.pdf_path is None
    assert not getattr(win, "src_pdfs", None) and "nuevo" not in win.windowTitle()
    # con un PDF ya en el editor (y una línea): sigue tal cual
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    _editor_con_lineas(win, tmp_path, HOJA)
    antes = _foto(win)
    ruta = win.pdf_path
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: False)
    win._open_pdf_path(_pdf(tmp_path / "otro.pdf"))
    app.processEvents()
    assert _foto(win) == antes and win.pdf_path == ruta and not win.doc.is_closed
    assert not _INTERPRETADAS


def test_abrir_pdf_vectorial_compone_e_interpreta_sin_capas_ni_vista_previa(win, app, tmp_path, monkeypatch):
    from ui.ventana import app_window
    import detect
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", _ASISTENTE)
    monkeypatch.setattr(detect, "classify_page", lambda page: ("vector", {"n_paths": 500}))
    _stubs(monkeypatch, win, [C.Composite([C.Piece(0, 1, HOJA)])])
    win._open_pdf_path(_pdf(tmp_path / "nuevo.pdf"))
    app.processEvents()
    assert win.canvas.pixmap_item is not None and win.page_idx == 1 and win.pipes == []
    assert _INTERPRETADAS == [1] and win._respaldo is None


def test_componer_sin_cambios_no_rearma_ni_recarga(win, app, tmp_path, monkeypatch):
    """Pedido del usuario 2026-10-28: volver a «Componer hoja» y seguir sin cambiar nada no vuelve a armar la
    hoja compuesta ni a cargarla (ni a interpretarla). Si la hoja compuesta cambia, sí se rearma."""
    monkeypatch.setattr(_aw.Main, "_preguntar_reemplazar_hoja", lambda self: "reemplazar")   # hay líneas: se pregunta al final
    _editor_con_lineas(win, tmp_path, AREA)
    misma = C.Composite.from_dict(win.composite.to_dict())
    _stubs(monkeypatch, win, [misma])
    armadas, cargadas = [], []
    aplicar, cargar = win._apply_composite, win._load_sheet_busy
    monkeypatch.setattr(win, "_apply_composite", lambda: armadas.append(1) or aplicar())
    monkeypatch.setattr(win, "_load_sheet_busy", lambda i: cargadas.append(i) or cargar(i))
    win.compose_sheet()
    app.processEvents()
    assert not armadas and not cargadas and not _INTERPRETADAS and len(win.pipes) == 1
    # otra hoja compuesta: se arma de nuevo
    _stubs(monkeypatch, win, [_otra()])
    win.compose_sheet()
    app.processEvents()
    assert len(armadas) == 1 and len(cargadas) == 1 and _INTERPRETADAS == [win.page_idx]


def test_recomponer_con_cambios_interpreta_y_sin_cambios_no(win, app, tmp_path, monkeypatch):
    monkeypatch.setattr(_aw.Main, "_preguntar_reemplazar_hoja", lambda self: "reemplazar")   # hay líneas: se pregunta al final
    from ui.ventana import app_window
    _editor_con_lineas(win, tmp_path, HOJA, manual=True)
    llamadas = []
    cambiar = [None]

    def componer(parent, sources, comp, hidden, **kw):
        llamadas.append(kw.get("manual", False))
        nuevo = C.Composite.from_dict(comp.to_dict())
        nuevo.manual = kw.get("manual", False)
        sources = list(sources)
        if cambiar[0] == "hoja":
            nuevo.pieces.append(C.Piece(0, 2, HOJA, x=650))
        elif cambiar[0] == "area":
            nuevo.pieces[-1].clip = list(AREA)
        elif cambiar[0] == "pdf":
            path = _pdf(tmp_path / "otro.pdf")
            sources.append({"name": "otro.pdf", "path": path, "data": Path(path).read_bytes()})
            nuevo.pieces.append(C.Piece(1, 0, HOJA, x=1300))
        return nuevo, sources, dict(hidden)

    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", componer)
    piezas = []
    for cambio, esperados in [(None, 1), ("hoja", 2), ("area", 3), ("pdf", 4), (None, 4)]:
        cambiar[0] = cambio
        win.compose_sheet()
        for _ in range(3):
            app.processEvents()
        assert len(_INTERPRETADAS) == esperados
        assert win._respaldo is None
        assert not win.composite.manual
        piezas.append(len(win.composite.pieces))
    assert llamadas == [False] * 5
    assert piezas == [1, 2, 2, 3, 3]
    assert len(win.src_pdfs) == 2


def test_cancelar_conserva_el_panel_reconocer(win, app, tmp_path, monkeypatch):
    """Lo reconocido desde el panel «Reconocer» (filas, resultados en memoria y la interpretación de la hoja) sigue
    si la hoja nueva no llega a quedar: `_reset_model` lo vacía al cargarla y «Cancelar» lo repone
    (`respaldo_editor.CLAVES`)."""
    from nucleo import reconocer_estado as RE
    _editor_con_lineas(win, tmp_path, HOJA)
    e = RE.nuevo()
    e.filas["AGUA"].estado, e.filas["AGUA"].hechos = "reconocida", 3
    win.reconocer_estado = e
    resultado = object()
    win._resultados_partes = {"AGUA": [resultado]}
    win._rec_cache().put(("clave",), [[resultado]])
    interp = {"firma": "f", "layers": []}
    win._interpretacion = interp
    _stubs(monkeypatch, win, [_otra()])
    _que_falle_al_cargar(monkeypatch, win)
    win.compose_sheet()
    app.processEvents()
    assert win.reconocer_estado.filas["AGUA"].estado == "reconocida"
    assert win._resultados_partes["AGUA"][0] is resultado
    assert win._rec_cache().get(("clave",)) is not None
    assert win._interpretacion == interp


# ── «Componer hoja» con la hoja ya en el editor: sin preguntar al entrar, agregar hojas conserva todo
# (pedido del usuario 2026-11-17) ──────────────────────────────────────────────────────────────────

def _dos_hojas(win, tmp_path):
    """Hoja compuesta de dos piezas (hojas 1 y 2, una al lado de la otra) con una línea dibujada."""
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win.composite = C.Composite([C.Piece(0, 0, list(HOJA), 0.0, 0.0), C.Piece(0, 1, list(HOJA), 600.0, 0.0)])
    win._apply_composite()
    QtWidgets.QApplication.instance().processEvents()
    win._push()
    win.pipes.append(dict(LINEA))
    win._refresh_lists(); win._redraw()


def _mas(win, x, y):
    piezas = [C.Piece.from_dict(p.to_dict()) for p in win.composite.pieces]
    return C.Composite(piezas + [C.Piece(0, 2, list(HOJA), x, y)])


def test_entrar_al_compositor_no_pregunta_guardar(win, tmp_path, monkeypatch):
    _dos_hojas(win, tmp_path)
    win._dirty = True
    preguntas = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: preguntas.append(a) or QtWidgets.QMessageBox.Cancel)
    _stubs(monkeypatch, win, [None])
    win.compose_sheet()
    assert preguntas == []
    assert win.pipes and win.pipes[-1]["pts"] == LINEA["pts"]


@pytest.mark.parametrize("donde", ["derecha", "abajo"])
def test_agregar_una_hoja_conserva_lo_dibujado_sin_preguntar(win, tmp_path, monkeypatch, donde):
    _dos_hojas(win, tmp_path)
    W, H = win.canvas.tam_hoja()
    lineas, undo = json.dumps(win.pipes, default=str), len(win._undo)
    nuevo = _mas(win, 1200.0, 0.0) if donde == "derecha" else _mas(win, 0.0, 400.0)
    _stubs(monkeypatch, win, [nuevo])
    monkeypatch.setattr(win, "_preguntar_reemplazar_hoja", lambda: pytest.fail("no debe preguntar"))
    assert win.compose_sheet() is None or True
    assert len(win.composite.pieces) == 3
    assert json.dumps(win.pipes, default=str) == lineas and len(win._undo) == undo
    W2, H2 = win.canvas.tam_hoja()
    assert (W2 > W) if donde == "derecha" else (H2 > H)
    assert _INTERPRETADAS                                   # el área nueva se interpreta


def test_hoja_a_la_izquierda_pregunta_y_volver_al_compositor_no_pierde_nada(win, tmp_path, monkeypatch):
    _dos_hojas(win, tmp_path)
    lineas = json.dumps(win.pipes, default=str)
    izquierda = _mas(win, -600.0, 0.0)
    vistos = []
    from ui.ventana import app_window

    def compose(parent, sources, comp, hidden, **kw):
        vistos.append(comp.to_dict() if comp else None)
        return (izquierda, list(sources), dict(hidden or {})) if len(vistos) == 1 else None
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", compose)
    respuestas = ["volver"]
    monkeypatch.setattr(win, "_preguntar_reemplazar_hoja", lambda: respuestas.pop(0))
    win.compose_sheet()
    assert vistos[1] == izquierda.to_dict()                 # vuelve al compositor con lo que había elegido
    assert json.dumps(win.pipes, default=str) == lineas and len(win.composite.pieces) == 2
