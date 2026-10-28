"""«Agregar utilidad» sin trabar la ventana ni llenar la memoria (reporte del usuario 2026-10-24).

Con el agua de un plano ya importada, agregar el alcantarillado de los mismos mapas «se lajeaba».
Medido con 12 + 12 mapas de Phoenix: «Capas de la hoja» 18 s con la ventana congelada en tramos
de hasta 4 s, cargar la hoja calcada 4.6 s (3 s leyendo un texto que se descartaba) y armar la
hoja combinada 6 s; los 3 procesos de las teselas guardaban todas las hojas vistas (~640 MB cada
uno). Con 36 + 36 mapas, ~3 veces más: Windows marcaba «No responde» y la memoria se agotaba.

Lo pesado va al proceso trabajador con los MISMOS resultados: la imagen de la hoja compuesta
(`fondo_trabajo`), lo que «Capas de la hoja» lee al abrirse (`capas_trabajo`), y las teselas
sueltan las hojas que ya nadie mira. Estas pruebas encienden el proceso (`PDFCAD_PROCESO=1`).
"""
import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from hoja import capas_trabajo, leyenda_estandar as le, leyenda_mapa, leyenda_trazos, pdf_layers  # noqa: E402
from ui.comun import fondo_pdf, fondo_trabajo, proceso  # noqa: E402
from ui.comun import teselas as T, teselas_servidor as TS  # noqa: E402

PHX = r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND"
WATER_S = os.path.join(PHX, "QS Water_Indian School_South.pdf")


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def con_proceso(app, monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    yield
    for t in list(proceso._TRABAJADORES.values()):
        t.parar()
    proceso._TRABAJADORES.clear()


def _plano(ruta, ocg=True, w=900, h=700):
    """Una hoja con dos capas (una de ellas «C-SSWR-UNGD-E», de utilidad), texto y un recorte."""
    doc = fitz.open()
    pg = doc.new_page(width=w, height=h)
    red = doc.add_ocg("C-SSWR-UNGD-E", on=True) if ocg else 0
    base = doc.add_ocg("V-ROAD-CNTR", on=True) if ocg else 0
    for i in range(14):
        pg.draw_line((20 + 61.3 * i, 15), (35 + 61.3 * i, h - 15), width=0.35, oc=base)
        pg.draw_line((15, 20 + 47.7 * i), (w - 15, 30 + 47.7 * i), width=0.9, color=(1, 0, 0), oc=red)
    pg.draw_circle((w / 2, h / 2), 33.3, width=0.8, oc=red)
    pg.insert_text((60, 80), "MATCH LINE 12+34", fontsize=9)
    doc.save(str(ruta))
    return str(ruta)


def _px(qimg) -> np.ndarray:
    img = qimg.convertToFormat(QtGui.QImage.Format_RGB888)
    return np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 3].copy()


# ── la imagen de la hoja ────────────────────────────────────────────────────
@pytest.mark.parametrize("enorme", [False, True])
def test_fondo_en_el_proceso_mismos_pixeles_y_grises(con_proceso, tmp_path, monkeypatch, enorme):
    if enorme:                                   # hoja que pasa por «enorme»: imagen reducida
        monkeypatch.setattr(fondo_pdf, "LIMITE_BYTES", 2_000_000)
        monkeypatch.setattr(fondo_pdf, "PRESUPUESTO_PX", 400_000)
    doc = fitz.open(_plano(tmp_path / "hoja.pdf"))
    doc.set_layer_ui_config(1, 2)               # una capa apagada: el proceso la apaga igual (por número)
    r = fondo_trabajo.en_proceso(doc, 0, 3.5)
    assert r is not None
    q, g, escala, ancho, alto = fondo_trabajo.aqui(doc[0], 3.5)
    assert (r[2], r[3], r[4]) == (escala, ancho, alto)
    assert (escala < 1.0) == enorme
    assert np.array_equal(_px(r[0]), _px(q))
    assert np.array_equal(r[1], g)
    sin = fondo_trabajo.en_proceso(doc, 0, 3.0, grises=False)
    assert sin[1] is None and np.array_equal(_px(sin[0]), _px(fondo_trabajo.aqui(doc[0], 3.0, grises=False)[0]))


def test_sin_proceso_o_sin_archivo_se_dibuja_aqui(app, tmp_path, monkeypatch):
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    doc = fitz.open(_plano(tmp_path / "hoja.pdf"))
    assert fondo_trabajo.en_proceso(doc, 0, 3.5) is None
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    en_memoria = fitz.open(stream=doc.tobytes(), filetype="pdf")
    assert fondo_trabajo.ruta_de(en_memoria) == "" and fondo_trabajo.en_proceso(en_memoria, 0, 3.5) is None
    from hoja import composite as C
    assert not fondo_trabajo.conviene(C.Composite([C.Piece(0, 0, [0, 0, 1, 1])]))
    assert fondo_trabajo.conviene(C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1])]))


# ── lo que lee «Capas de la hoja» ───────────────────────────────────────────
def _como_la_ventana(doc, hoja):
    page = doc[hoja]
    layers = pdf_layers.page_layers(doc, hoja)
    ley = (leyenda_mapa.leer(doc, page) if any(L.get("source") == "style" for L in layers)
           and leyenda_mapa.aplica(page) else None)
    prev = pdf_layers.hidden_layers(doc)
    pdf_layers.set_hidden(doc, ())
    quiere = le.capas_de_utilidad(layers)
    vis = {d.get("layer") or "" for d, _s in leyenda_trazos.trazos_visibles(page, quiere)}
    pdf_layers.set_hidden(doc, prev)
    return layers, ley, vis, quiere


@pytest.mark.parametrize("ocg", [True, False])
def test_capas_leidas_en_el_proceso_son_las_de_la_ventana(app, tmp_path, ocg):
    ruta = _plano(tmp_path / "hoja.pdf", ocg=ocg)
    doc = fitz.open(ruta)
    if ocg:
        doc.set_layer_ui_config(1, 2)
    res = capas_trabajo.leer(ruta, 0, pdf_layers.encendidas(doc), [])
    layers, ley, vis, quiere = _como_la_ventana(doc, 0)
    assert res["layers"] == layers and res["leyenda"] is ley is None
    assert {n for n in res["visibles"] if quiere(n)} == vis and vis


def test_capas_de_un_mapa_de_phoenix_con_su_leyenda(app):
    if not os.path.isfile(WATER_S):
        pytest.skip("PDF de Phoenix no disponible")
    import pickle
    doc = fitz.open(WATER_S)
    res = pickle.loads(pickle.dumps(capas_trabajo.leer(WATER_S, 3, pdf_layers.encendidas(doc), [])))
    layers, ley, vis, quiere = _como_la_ventana(doc, 3)
    assert res["layers"] == layers
    assert ley is not None and ley.filas and pickle.dumps(res["leyenda"]) == pickle.dumps(ley)
    assert {n for n in res["visibles"] if quiere(n)} == vis


def test_dialogo_de_capas_no_lee_la_hoja_en_la_ventana(con_proceso, tmp_path, monkeypatch):
    """Con `en_proceso`, al abrirse el diálogo no lee la hoja ni la dibuja en la ventana y devuelve
    lo mismo que sin él; marcar casillas que no cambian el dibujo no lo vuelve a dibujar."""
    from ui.asistente import layer_dialog
    ruta = _plano(tmp_path / "hoja.pdf")
    elegido = {}

    def correr(en_proceso):
        doc = fitz.open(ruta)
        parent = QtWidgets.QWidget()
        parent.resize(1200, 800)
        parent.show()

        def aceptar():
            w = QtWidgets.QApplication.activeModalWidget()
            if isinstance(w, layer_dialog.SheetLayersDialog):
                elegido[en_proceso] = {"vis": sorted(w._visible_layers()), "img": _px(w._pix_item.pixmap().toImage())}
                w.btn_ok.click()
        tim = QtCore.QTimer()
        tim.timeout.connect(aceptar)
        tim.start(100)
        try:
            return layer_dialog.choose_sheet_layers(parent, doc, 0, include_roles=True, en_proceso=en_proceso)
        finally:
            tim.stop()
            parent.close()

    sin = correr(False)
    leidas = []
    monkeypatch.setattr(layer_dialog.pdf_layers, "page_layers", lambda *a, **k: leidas.append(a) or [])
    monkeypatch.setattr(leyenda_trazos, "trazos_visibles", lambda *a, **k: leidas.append(a) or [])
    dibujos = []
    aqui = fondo_trabajo.aqui
    monkeypatch.setattr(fondo_trabajo, "aqui", lambda *a, **k: dibujos.append(a) or aqui(*a, **k))
    con = correr(True)
    assert con == sin and not leidas and not dibujos
    assert elegido[True]["vis"] == elegido[False]["vis"] and elegido[True]["vis"]
    assert np.array_equal(elegido[True]["img"], elegido[False]["img"])


def test_mismas_capas_encendidas_no_se_vuelve_a_dibujar(app, tmp_path, monkeypatch):
    from ui.asistente import layer_dialog
    doc = fitz.open(_plano(tmp_path / "hoja.pdf"))
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    dibujos = []
    aqui = fondo_trabajo.aqui
    monkeypatch.setattr(fondo_trabajo, "aqui", lambda *a, **k: dibujos.append(a) or aqui(*a, **k))
    dlg._render()
    assert not dibujos                           # nada cambió
    dlg._set_all(False)                          # ocultar todas: otra imagen
    dlg._render()
    assert len(dibujos) == 1
    dlg.close()


# ── las teselas sueltan las hojas que nadie mira ────────────────────────────
def test_teselas_sueltan_el_pdf_que_ya_no_se_ve(con_proceso, tmp_path, monkeypatch):
    monkeypatch.setattr(TS, "cuantos", lambda: 1)
    srv = TS.servidor()
    srv._t_olvidar.setInterval(50)
    try:
        a = fitz.open(_plano(tmp_path / "a.pdf"))
        b = fitz.open(_plano(tmp_path / "b.pdf", w=800))
        pix = a[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        item = fondo_pdf.nuevo_item(QtGui.QPixmap.fromImage(fondo_pdf.qimage(pix)), 1.0)
        sc = QtWidgets.QGraphicsScene()
        sc.addItem(item)
        vista = QtWidgets.QGraphicsView(sc)
        vista.show()
        sup = item.superficie

        def ver(doc, region):
            sup.fijar(doc[0], k=3.0, base=3.0)
            sup.pedir_region(region, 9.0)
            quiero = [c for _p, c, v in srv._duenos[id(sup)][2] if v]
            assert _esperar(lambda: all(c in srv._cache for c in quiero))
            return quiero
        ver(a, (100, 100, 400, 300))
        tok_a = a._pdfcad_tesela
        pr = next(p for p in srv._procs if p is not None)
        assert tok_a in pr.docs
        ver(b, (100, 100, 400, 300))
        assert _esperar(lambda: tok_a not in pr.docs and b._pdfcad_tesela in pr.docs)
        # vuelve a verse (Cancelar repone el editor): se le manda otra vez y dibuja lo mismo
        for c in ver(a, (450, 300, 800, 600)):
            t = srv._cache[c]
            s = T.escala_nivel(c[3])
            r = T.rect_tesela(c[3], c[4], c[5], a[0].rect.width, a[0].rect.height)
            ref = a[0].get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(*r), alpha=False)
            want = np.frombuffer(ref.samples, np.uint8).reshape(ref.height, ref.stride)[:, :ref.width * 3]
            assert np.array_equal(_px(t.pm.toImage()), want)
        assert tok_a in pr.docs
        vista.close()
    finally:
        srv.parar()


def _esperar(cond, seg=40.0):
    app = QtWidgets.QApplication.instance()
    fin = time.time() + seg
    while time.time() < fin:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if cond():
            return True
        time.sleep(0.01)
    return False


# ── la ventana ──────────────────────────────────────────────────────────────
def test_hoja_compuesta_no_lee_la_escala_del_texto(app, tmp_path, monkeypatch):
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    win = app_window.Main()
    try:
        win._open_pdf_path(_plano(tmp_path / "hoja.pdf"))
        monkeypatch.setattr(app_window.VP, "detect_scale", lambda page: (_ for _ in ()).throw(AssertionError))
        win._scale_override = 2.5
        win._load_page(0)
        assert win.scale == 2.5
    finally:
        win._dirty = False
        win.close()


def test_agregar_utilidad_con_proceso_da_lo_mismo_que_sin_el(app, tmp_path, monkeypatch):
    """El flujo entero (`test_agregar_utilidad`) con el trabajo en el proceso: mismo editor,
    misma hoja combinada, mismos píxeles y grises del fondo."""
    import json
    import test_agregar_utilidad as TA
    from ui.ventana import app_window
    agua = TA._pdf(tmp_path / "QS Water_Prueba.pdf", TA.AGUA, [0, 1], TA.TUBO["agua"])
    cloaca = TA._pdf(tmp_path / "QS Sewer_Prueba.pdf", TA.CLOACA, [1, 0], TA.TUBO["cloaca"], girar=(0,))
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(app_window, "RecognitionWorker", TA._Reconocer)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.No)
    fotos, en_proc = {}, []
    real = fondo_trabajo.en_proceso
    monkeypatch.setattr(fondo_trabajo, "en_proceso", lambda *a, **k: en_proc.append(real(*a, **k)) or en_proc[-1])
    try:
        for con in ("0", "1"):
            monkeypatch.setenv("PDFCAD_PROCESO", con)
            w = app_window.Main()
            try:
                TA._editor_con_agua(w, agua)
                tubo = [TA._px(w, 0, *TA.TUBO["cloaca"][0]), TA._px(w, 0, *TA.TUBO["cloaca"][1])]
                TA._px_esperado[0] = tubo[0]
                TA._Reconocer.lineas = [tubo]
                TA._stubs(monkeypatch, w, cloaca, "import")
                w.agregar_utilidad()
                assert [p["layer"] for p in w.pipes] == ["AGUA", "ALCANTARILLADO"]
                fotos[con] = (json.dumps(w.pipes, sort_keys=True, default=str), w.composite.to_dict(),
                              _px(w.canvas.pixmap_item.pixmap().toImage()), np.array(w.gray), w.canvas.tam_hoja())
            finally:
                w._dirty = False
                w.close()
                app.processEvents()
    finally:
        for t in list(proceso._TRABAJADORES.values()):
            t.parar()
        proceso._TRABAJADORES.clear()
    # el editor de agua, la hoja calcada y la hoja combinada (2026-10-28: «Capas» sin cambios ya no
    # vuelve a cargar la hoja calcada, `ventana_pasos`)
    assert len(en_proc) == 3 and all(r is not None for r in en_proc)
    a, b = fotos["0"], fotos["1"]
    assert a[0] == b[0] and a[1] == b[1] and a[4] == b[4]
    assert np.array_equal(a[2], b[2]) and np.array_equal(a[3], b[3])
