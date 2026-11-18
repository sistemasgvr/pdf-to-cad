"""Abrir un PDF = componer la hoja → el editor al instante; la hoja se INTERPRETA en segundo plano y el panel
«Reconocer» se llena solo (plan 2026-11-16, «reconocimiento desde el editor», Tarea 9). Sin paso «Capas de la hoja»
ni vista previa obligatoria.

Ventana real (Qt offscreen). PDF vectorial DU06 (h.3, índice 2), un escaneo, ◀ ▶, «Agregar utilidad» (PDF
sintéticos de `test_agregar_utilidad`) y un mapa sin capas de Phoenix (Water South h.4): su fila de agua queda lista
(los estilos que asignaba la leyenda en «Capas de la hoja») y el ▶ da las MISMAS líneas que el flujo de antes.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("pymupdf")
from PySide6 import QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from reconocimiento import lectura_retenida as LR  # noqa: E402
from ui.comun import proceso  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
WATER_S = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/QS Water_Indian School_South.pdf")
ESCANEO = ROOT / "tests" / "fixtures" / "escaneado_vectorizado.pdf"


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def esperar_interpretacion(w, s=600):
    """La interpretación corre en un hilo (PDFCAD_PROCESO=0) o en el trabajador: esperar a que termine."""
    fin = time.time() + s
    while w.interpretando():
        _app().processEvents()
        time.sleep(0.02)
        assert time.time() < fin, "la interpretación no terminó"
    _app().processEvents()


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


def _prohibir_asistente_viejo(monkeypatch):
    from ui.asistente import layer_dialog, recognition_dialog

    def no(*_a, **_k):
        raise AssertionError("el flujo nuevo no abre «Capas de la hoja» ni la vista previa")
    monkeypatch.setattr(layer_dialog, "choose_sheet_layers", no)
    monkeypatch.setattr(recognition_dialog, "show_recognition_preview", no)


def _componer(monkeypatch, hoja=None, manual=False, vistos=None):
    """«Componer hoja» acepta la hoja `hoja` entera (o la que traía)."""
    from ui.ventana import app_window

    def componer(parent, sources, comp, hidden, current_page=0, manual=False, **kw):
        if vistos is not None:
            vistos.append(dict(current_page=current_page, manual=manual))
        if comp is not None and comp.pieces:
            return comp, sources, hidden
        pagina = current_page if hoja is None else hoja
        with fitz.open(stream=sources[0]["data"], filetype="pdf") as d:
            import vector_pipeline as VP
            escala = float(VP.detect_scale(d[pagina])) if not manual else 20.0 / 72.0
        return (C.Composite([C.Piece(0, pagina, [0.0, 0.0, 1.0, 1.0], src_scale=escala)], manual=manual,
                            bridges=False), sources, hidden)
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", componer)


@pytest.fixture
def ventana(monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    app = _app()
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)
    _prohibir_asistente_viejo(monkeypatch)
    w = app_window.Main()
    yield w
    _esperar_hilos()
    LR.soltar()
    w._dirty = False
    w.close()
    app.processEvents()


def _filas(w, estado):
    return sorted(p for p, f in w.reconocer_estado.filas.items() if f.estado == estado)


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_abrir_pdf_vectorial_va_al_editor_y_el_panel_se_llena(ventana, monkeypatch):
    w = ventana
    _componer(monkeypatch, hoja=2)
    w._open_pdf_path(str(DU06))
    # el editor ya tiene la hoja, sin nada reconocido, y el panel está en «Reconocer»
    assert w.canvas.pixmap_item is not None and w.page_idx == 2
    assert w.pipes == [] and w.structures == []
    assert w.paneles_riel.currentIndex() == 4
    esperar_interpretacion(w)
    e = w.reconocer_estado
    assert e.firma_hoja == w._firma_hoja_actual() == w._interpretacion["firma"]
    assert "DRENAJE" in _filas(w, "pendiente") and e.filas["DRENAJE"].fuentes > 0
    assert not _filas(w, "sin_interpretar") and not _filas(w, "reconocida")
    assert w.pipes == []                                     # nada se reconoce solo
    assert not w.panel_reconocer.btn_interpretar.isVisibleTo(w.panel_reconocer)


@pytest.mark.skipif(not ESCANEO.is_file(), reason="fixture de escaneo no disponible")
def test_escaneo_va_al_dibujo_a_mano_sin_interpretar(ventana, monkeypatch):
    w = ventana
    vistos = []
    _componer(monkeypatch, manual=True, vistos=vistos)
    pedidas = []
    monkeypatch.setattr(w, "_interpretar_hoja", lambda: pedidas.append(1))
    w._open_pdf_path(str(ESCANEO))
    assert vistos and vistos[0]["manual"] is True             # el compositor de escaneos, como hoy
    assert w.canvas.pixmap_item is not None and w.composite.manual
    assert not pedidas and not w.interpretando()
    assert w._reconocer_escaneo
    assert _filas(w, "sin_interpretar") == sorted(w.reconocer_estado.filas)
    assert not w.panel_reconocer.btn_interpretar.isVisibleTo(w.panel_reconocer)


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_cambiar_de_hoja_interpreta_la_nueva_sin_vista_previa(ventana, monkeypatch):
    w = ventana
    _componer(monkeypatch, hoja=2)
    w._open_pdf_path(str(DU06))
    esperar_interpretacion(w)
    firma_antes = w.reconocer_estado.firma_hoja
    w._next_page()                                           # ◀ ▶ del editor
    assert w.page_idx == 3
    assert w.interpretando() or w.reconocer_estado.firma_hoja != firma_antes
    esperar_interpretacion(w)
    e = w.reconocer_estado
    assert e.firma_hoja == w._firma_hoja_actual() != firma_antes
    assert _filas(w, "pendiente") and not _filas(w, "reconocida") and w.pipes == []


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_resultado_de_otra_hoja_se_descarta(ventana, monkeypatch):
    w = ventana
    _componer(monkeypatch, hoja=2)
    w._open_pdf_path(str(DU06))
    assert w.interpretando()
    w._load_page(3)                                          # otra hoja antes de que termine
    esperar_interpretacion(w)
    _esperar_hilos()
    _app().processEvents()
    assert w._interpretacion is None
    assert _filas(w, "sin_interpretar") == sorted(w.reconocer_estado.filas)


def test_la_ventana_no_espera_a_la_interpretacion(ventana, monkeypatch, tmp_path):
    """Con el trabajador de verdad, `_interpretar_hoja` vuelve antes de que el trabajo termine."""
    w = ventana
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    doc = fitz.open()
    pg = doc.new_page(width=800, height=600)
    for k in range(100):                                     # ≥80 trazos + texto = PDF vectorial (`detect`)
        pg.draw_line((20, 20 + 5 * k), (780, 25 + 5 * k), color=(0, 0, 1), width=1.5)
    pg.insert_text((30, 580), "WATER MAIN 8 IN DIP - PLAN VIEW SHEET 1", fontsize=10)
    pdf = tmp_path / "plano.pdf"
    doc.save(str(pdf))
    _componer(monkeypatch, hoja=0)
    t0 = time.time()
    w._open_pdf_path(str(pdf))
    assert w.interpretando()                                 # la ventana ya está libre
    assert time.time() - t0 < 30
    esperar_interpretacion(w, 180)
    assert w._interpretacion is not None
    assert not _filas(w, "sin_interpretar")
    proceso.trabajador(proceso.RETENEDOR).parar()


# ── «Agregar utilidad»: la hoja nueva junto a la del editor, solo sus filas, lo de antes intacto ──
def test_agregar_utilidad_interpreta_solo_la_hoja_nueva(ventana, monkeypatch, tmp_path):
    import test_agregar_utilidad as TA
    from ui.ventana import app_window
    w = ventana
    agua = TA._pdf(tmp_path / "QS Water_Prueba.pdf", TA.AGUA, [0, 1], TA.TUBO["agua"])
    cloaca = TA._pdf(tmp_path / "QS Sewer_Prueba.pdf", TA.CLOACA, [1, 0], TA.TUBO["cloaca"], girar=(0,))
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    TA._editor_con_agua(w, agua)                             # (la hoja del agua, como en test_agregar_utilidad)
    monkeypatch.undo()                                       # (vuelve todo lo parcheado arriba)
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    _prohibir_asistente_viejo(monkeypatch)
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    antes = dict(pipes=json.dumps(w.pipes, sort_keys=True, default=repr), undo=len(w._undo),
                 tam=w.canvas.tam_hoja())
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames", lambda *a, **k: ([cloaca], ""))
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet",
                        lambda parent, sources, comp, hidden, **kw: (comp, sources, hidden))
    w.agregar_utilidad()
    # lo de antes, intacto; la hoja del editor ya tiene las dos utilidades
    assert json.dumps(w.pipes, sort_keys=True, default=repr) == antes["pipes"]
    assert len(w._undo) == antes["undo"] and w.canvas.tam_hoja() == pytest.approx(antes["tam"])
    assert [e["name"] for e in w.src_pdfs] == ["QS Water_Prueba.pdf", "QS Sewer_Prueba.pdf"]
    assert w._agregando is None and w._respaldo is None and w._dirty
    # se interpreta la hoja CALCADA (solo el PDF nuevo), no la combinada
    ov = w._rec_hoja
    assert ov is not None and ov["ruta"] != w.work_pdf_path and os.path.isfile(ov["ruta"])
    assert w._rec_ruta_hoja() == (ov["ruta"], ov["hoja"])
    esperar_interpretacion(w)
    assert w.reconocer_estado.firma_hoja == ov["firma"] == w._interpretacion["firma"]
    with fitz.open(ov["ruta"]) as d:                         # la hoja calcada: solo el alcantarillado (rojo)
        colores = {tuple(round(c, 2) for c in (dd.get("color") or ())) for dd in d[ov["hoja"]].get_drawings()}
    assert (1.0, 0.0, 0.0) in colores and (0.0, 0.0, 1.0) not in colores
    assert json.dumps(w.pipes, sort_keys=True, default=repr) == antes["pipes"]
    # otra hoja / otro PDF: la hoja calcada se suelta (y su archivo temporal)
    ruta = ov["ruta"]
    w._soltar_reconocer()
    assert w._rec_hoja is None
    _esperar(lambda: not os.path.isfile(ruta), 30)           # (el trabajador suelta la hoja y se borra)


# ── Phoenix sin capas: la fila de agua lista sin «Capas y estilos…», el ▶ como el flujo de antes ──
@pytest.mark.skipif(not WATER_S.is_file(), reason="PDF Water South no disponible")
def test_phoenix_agua_lista_tras_interpretar_y_el_play_da_lo_mismo(ventana, monkeypatch):
    from reconocimiento import recognition_trabajo as RT
    from ui.asistente import layer_dialog, roles_iniciales as RI
    from ui.asistente.layer_dialog_editor import previa_de_interpretacion
    w = ventana
    _componer(monkeypatch, hoja=3)
    w._open_pdf_path(str(WATER_S))
    esperar_interpretacion(w)
    f = w.reconocer_estado.filas["AGUA"]
    assert f.estado == "pendiente" and f.fuentes > 0          # no bloqueada: la leyenda asignó sus estilos
    roles = w._roles_de_la_hoja(w.page_idx)
    # = lo que dejaba «Capas de la hoja» al continuar sin tocar nada (el diálogo de verdad)
    monkeypatch.undo()
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    previa = previa_de_interpretacion(w.doc, w.page_idx, w._interpretacion)
    dlg = layer_dialog.SheetLayersDialog(w, w.doc, w.page_idx, layers=previa.layers, previa=previa,
                                         roles_by_utility={}, legend_sources=w._legend_sources())
    try:
        assert dlg.roles_by_utility() == roles
    finally:
        dlg.reject()
        dlg.deleteLater()
    assert RI.roles_iniciales(w._interpretacion["layers"], w._interpretacion["leyenda"],
                              w._interpretacion.get("sugeridos")) == roles
    # ▶ AGUA = el flujo de antes (asistente con esos roles → importar)
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    w.reconocer_parte("AGUA")
    _esperar(lambda: w._rec_actual is None)
    assert w.reconocer_estado.filas["AGUA"].estado == "reconocida" and w.pipes
    sellos = ("reconocida", "reconocida_idx", "reconocida_firma")
    foto = lambda lista: json.dumps([{k: v for k, v in d.items() if k not in sellos} for d in lista],  # noqa: E731
                                    sort_keys=True, default=repr)
    nuevo = (foto(w.pipes), foto(w.structures))
    viejo = RT.reconocer_hoja(w.work_pdf_path or w.pdf_path, w.page_idx, zoom=w.zoom, utilities=("AGUA",),
                              hidden_ocgs=w.hidden_ocgs, roles_by_utility=roles, letters_off=w._letters_off,
                              scale_ft_per_pt=w._scale_override)
    for r in viejo:
        r.valvulas = []                                      # las válvulas son otra fila
    w._reset_model()
    w._import_recognized_pipes(viejo)
    assert (foto(w.pipes), foto(w.structures)) == nuevo


def test_reabrir_con_utilidad_agregada_reconoce_en_su_hoja(ventana, monkeypatch, tmp_path):
    """Revisión 2026-11-16: el .digproj guarda qué hoja es la de la utilidad agregada; al reabrir, el ▶ y «Capas y
    estilos…» usan esa hoja (rearmada de su grupo) y no la combinada (mezclaría los dos PDF)."""
    import test_agregar_utilidad as TA
    from ui.ventana import app_window
    w = ventana
    agua = TA._pdf(tmp_path / "QS Water_Prueba.pdf", TA.AGUA, [0, 1], TA.TUBO["agua"])
    cloaca = TA._pdf(tmp_path / "QS Sewer_Prueba.pdf", TA.CLOACA, [1, 0], TA.TUBO["cloaca"], girar=(0,))
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    TA._editor_con_agua(w, agua)
    monkeypatch.undo()
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    _prohibir_asistente_viejo(monkeypatch)
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames", lambda *a, **k: ([cloaca], ""))
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet",
                        lambda parent, sources, comp, hidden, **kw: (comp, sources, hidden))
    w.agregar_utilidad()
    esperar_interpretacion(w)
    firma = w._rec_hoja["firma"]
    ruta = tmp_path / "agregada.digproj"
    w._write_project(str(ruta))
    w2 = app_window.Main()
    try:
        w2._open_project_path(str(ruta))
        ov = w2._rec_hoja
        assert ov is not None and ov["firma"] == firma and ov["ruta"] is None
        assert w2.reconocer_estado.firma_hoja == firma == w2._firma_lectura()
        hoja_ruta, hoja = w2._rec_ruta_hoja()                # se arma con el primer uso
        assert hoja_ruta and hoja_ruta != w2.work_pdf_path and os.path.isfile(hoja_ruta)
        with fitz.open(hoja_ruta) as d:                      # solo el alcantarillado (rojo), no el agua (azul)
            colores = {tuple(round(c, 2) for c in (dd.get("color") or ())) for dd in d[hoja].get_drawings()}
        assert (1.0, 0.0, 0.0) in colores and (0.0, 0.0, 1.0) not in colores
        doc, h, propio = w2._doc_de_lectura()                # «Capas y estilos…» abre esa hoja
        try:
            assert propio and doc.name == hoja_ruta and h == hoja
        finally:
            doc.close()
        w2._soltar_reconocer()
        _esperar(lambda: not os.path.isfile(hoja_ruta), 30)
    finally:
        _esperar_hilos()
        w2._dirty = False
        w2.close()
