"""Hoja compuesta enorme: el editor ya no falla con «code=5: Overly large image».

Reporte del usuario (2026-10-09): con 18 piezas en el compositor, «No se pudo armar la
hoja compuesta: code=5: Overly large image». El editor dibujaba la hoja ENTERA como una
sola imagen a zoom 3.5 y MuPDF no crea imágenes de más de 1 GiB. Ahora (`fondo_pdf`):
si cabe, la imagen de siempre; si no, reducida con las MISMAS coordenadas y un recorte
nítido de lo visible al acercarse. Las pruebas de la ventana bajan el límite
(`chica`): una hoja de 600×400 pt recorre los mismos caminos que 18 hojas del DU06.
"""
import json
import os
import zipfile

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from ui.comun import fondo_pdf  # noqa: E402

LX, LY = 300.7, 200.3          # línea vertical y horizontal de cada hoja (pt)


def _pdf(path, w=600, h=400, pages=2):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=w, height=h)
        pg.draw_line((50, LY), (w - 50, LY), width=0.5)
        pg.draw_line((LX, 20), (LX, h - 20), width=0.5)
        pg.insert_text((50, 60), f"hoja {i + 1}")
    doc.save(str(path)); doc.close()
    return str(path)


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def chica(monkeypatch):
    """Límite y presupuesto chicos: una hoja de prueba pasa por «enorme»."""
    monkeypatch.setattr(fondo_pdf, "LIMITE_BYTES", 2_000_000)
    monkeypatch.setattr(fondo_pdf, "PRESUPUESTO_PX", 400_000)


@pytest.fixture
def win(app, monkeypatch):
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.Discard)
    w = app_window.Main()
    w.resize(1200, 800)
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def _compuesta(win, tmp_path):
    """Dos hojas lado a lado: hoja compuesta materializada (PDF temporal)."""
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win.composite = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1], x=600.0)])
    win._apply_composite()
    QtWidgets.QApplication.instance().processEvents()


# ── fondo_pdf (puro) ─────────────────────────────────────────────────────────
def test_si_cabe_es_la_imagen_de_siempre():
    doc = fitz.open(); page = doc.new_page(width=600, height=400)
    page.draw_line((10, 10), (590, 390))
    f = fondo_pdf.render_pix(page, 3.5)
    ref = page.get_pixmap(matrix=fitz.Matrix(3.5, 3.5), alpha=False)
    assert f.escala == 1.0 and (f.ancho, f.alto) == (ref.width, ref.height)
    assert f.pix.samples == ref.samples


def test_hoja_que_mupdf_no_dibuja_entera(monkeypatch):
    """El caso real: 9000×3500 pt a zoom 3.5 = 386 Mpx (> 1 GiB en RGB)."""
    monkeypatch.setattr(fondo_pdf, "PRESUPUESTO_PX", 1_000_000)      # barato en la prueba
    doc = fitz.open(); page = doc.new_page(width=9000, height=3500)
    page.draw_line((10, 10), (8990, 3490))
    with pytest.raises(Exception, match="(?i)large"):
        page.get_pixmap(matrix=fitz.Matrix(3.5, 3.5), alpha=False)      # el error del usuario
    f = fondo_pdf.render_pix(page, 3.5)
    assert f.escala < 1.0 and (f.ancho, f.alto) == (31500, 12250)
    assert abs(f.pix.width - f.ancho * f.escala) <= 1 and abs(f.pix.height - f.alto * f.escala) <= 1
    assert f.pix.width * f.pix.height <= 1_000_000 * 1.01


def test_gris_identico_al_de_siempre():
    rng = np.random.default_rng(7)
    w, h, stride = 37, 53, 37 * 3 + 5
    buf = rng.integers(0, 256, size=h * stride, dtype=np.uint8).tobytes()
    arr = np.frombuffer(buf, np.uint8).reshape(h, stride)[:, :w * 3].reshape(h, w, 3)
    viejo = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)
    assert np.array_equal(fondo_pdf.gris(buf, w, h, stride), viejo)


def test_png_de_mas_de_256_mb(app):
    """Qt no abre imágenes por encima de su tope (256 MB): el proyecto no se reabría."""
    img = QtGui.QImage(1000, 600, QtGui.QImage.Format_RGB888)
    img.fill(QtGui.QColor("white"))
    ba = QtCore.QByteArray(); buf = QtCore.QBuffer(ba); buf.open(QtCore.QIODevice.WriteOnly)
    img.save(buf, "PNG")
    antes = QtGui.QImageReader.allocationLimit()
    try:
        QtGui.QImageReader.setAllocationLimit(1)        # 1 MB: la misma falla, a escala
        assert QtGui.QImage.fromData(bytes(ba), "PNG").isNull()
        q = fondo_pdf.leer_png(bytes(ba))
        assert not q.isNull() and (q.width(), q.height()) == (1000, 600)
    finally:
        QtGui.QImageReader.setAllocationLimit(antes)


# ── editor ───────────────────────────────────────────────────────────────────
def test_editor_con_hoja_enorme(win, chica, tmp_path):
    _compuesta(win, tmp_path)
    cv = win.canvas
    page = win.doc[0]
    tam = fondo_pdf.tam_px(page, win.zoom)
    assert cv.fondo_escala < 1.0
    assert cv.tam_hoja() == tam and win.pageH_px == tam[1]
    assert cv.sceneRect() == QtCore.QRectF(0, 0, *tam)
    r = cv.pixmap_item.sceneBoundingRect()
    assert abs(r.width() - tam[0]) <= 1 / cv.fondo_escala and abs(r.height() - tam[1]) <= 1 / cv.fondo_escala
    pm = cv.pixmap_item.pixmap()
    assert win.gray.shape == (pm.height(), pm.width())
    assert win._pagina_fondo() is not None

    # imán a la tinta: mismas coordenadas de siempre (la vertical de la 1.ª hoja)
    _, _, dx, dy = C.sheet_geometry(win.composite, lambda p: (600.0, 400.0))
    x_linea = (LX + dx) * win.zoom
    y = (120 + dy) * win.zoom
    win.snap = True
    sx, sy = win._snap(x_linea + 6, y)
    assert abs(sx - x_linea) <= 1.0 / cv.fondo_escala

    # al acercarse: recorte nítido EXACTO (px del recorte = px de MuPDF a su escala)
    cv.resetTransform(); cv.centerOn(x_linea, y)
    cv.nitidez.actualizar()
    n = cv.pixmap_item.nitido
    assert n is not None and n.parentItem() is cv.pixmap_item
    escala = cv.nitidez._clave[-1]
    p0 = n.mapToScene(QtCore.QPointF(0, 0))
    ox, oy = p0.x() / win.zoom * escala, p0.y() / win.zoom * escala
    assert abs(ox - round(ox)) < 1e-6 and abs(oy - round(oy)) < 1e-6
    assert abs(n.sceneTransform().m11() - win.zoom / escala) < 1e-9
    vis = cv.mapToScene(cv.viewport().rect()).boundingRect().intersected(cv.sceneRect())
    assert n.sceneBoundingRect().contains(vis)
    # la línea cae donde debe en la imagen nítida
    img = QtGui.QImage(80, 80, QtGui.QImage.Format_Grayscale8); img.fill(255)
    p = QtGui.QPainter(img)
    cv.scene().render(p, QtCore.QRectF(0, 0, 80, 80), QtCore.QRectF(x_linea - 40, y - 40, 80, 80))
    p.end()
    a = 255.0 - np.frombuffer(img.constBits(), np.uint8).reshape(80, img.bytesPerLine())[:, :80]
    col = a.sum(axis=0)
    centro = (col * (np.arange(80) + 0.5)).sum() / col.sum()
    assert abs(centro - 40) <= 1.0

    # alejarse quita el recorte
    cv.resetTransform(); cv.scale(0.05, 0.05)
    cv.nitidez.actualizar()
    assert cv.pixmap_item.nitido is None

    # capas cambiadas: misma imagen reducida, el recorte se rehace
    item = cv.pixmap_item
    win._refresh_current_pdf_image()
    assert cv.pixmap_item is item and cv.fondo_escala < 1.0


def test_iman_igual_que_con_la_hoja_normal(win, tmp_path, monkeypatch):
    """Con la hoja enorme el imán mira la tinta a resolución completa: mismo punto."""
    _compuesta(win, tmp_path)
    win.snap = True
    _, _, dx, dy = C.sheet_geometry(win.composite, lambda p: (600.0, 400.0))
    puntos = [((LX + dx) * win.zoom + 6, (120 + dy) * win.zoom),
              ((LX + dx + 600) * win.zoom - 5, (LY + dy) * win.zoom + 7)]
    normal = [win._snap(x, y) for x, y in puntos]
    monkeypatch.setattr(fondo_pdf, "LIMITE_BYTES", 2_000_000)
    monkeypatch.setattr(fondo_pdf, "PRESUPUESTO_PX", 400_000)
    win._load_page(0)
    assert win.canvas.fondo_escala < 1.0
    for (ax, ay), (bx, by) in zip(normal, [win._snap(x, y) for x, y in puntos]):
        assert abs(ax - bx) < 0.05 and abs(ay - by) < 0.05


def test_hoja_normal_sin_cambios(win, tmp_path):
    """Sin bajar el límite: la hoja compuesta de dos hojas se ve como siempre."""
    _compuesta(win, tmp_path)
    cv = win.canvas
    assert cv.fondo_escala == 1.0 and type(cv.pixmap_item) is QtWidgets.QGraphicsPixmapItem
    pm = cv.pixmap_item.pixmap()
    ref = win.doc[0].get_pixmap(matrix=fitz.Matrix(win.zoom, win.zoom), alpha=False)
    assert (pm.width(), pm.height()) == (ref.width, ref.height) == cv.tam_hoja()
    assert cv.sceneRect() == QtCore.QRectF(0, 0, ref.width, ref.height)
    cv.resetTransform(); cv.nitidez.actualizar()
    assert cv.nitidez.item is None                     # inactiva


def test_guardar_y_reabrir_hoja_enorme(win, chica, tmp_path):
    _compuesta(win, tmp_path)
    escala, tam = win.canvas.fondo_escala, win.canvas.tam_hoja()
    ruta = tmp_path / "grande.digproj"
    win._write_project(str(ruta))
    with zipfile.ZipFile(ruta) as z:
        model = json.loads(z.read("model.json"))
    assert model["fondo_escala"] == pytest.approx(escala) and tuple(model["fondo_tam"]) == tam
    win._open_project_path(str(ruta))
    assert win.canvas.fondo_escala == pytest.approx(escala)
    assert win.canvas.tam_hoja() == tam and win.pageH_px == tam[1]
    assert win.canvas.sceneRect() == QtCore.QRectF(0, 0, *tam)
    assert win._pagina_fondo() is not None             # el recorte nítido sigue funcionando


def test_proyecto_normal_no_guarda_claves_nuevas(win, tmp_path):
    _compuesta(win, tmp_path)
    import project_io
    model = project_io.build_model_dict(win)
    assert "fondo_escala" not in model and "fondo_tam" not in model
    data = project_io.parse_model(model)
    assert data["fondo_escala"] == 1.0 and data["fondo_tam"] is None


def test_cancelar_el_asistente_repone_la_hoja_enorme(win, chica, tmp_path):
    from ui.ventana import respaldo_editor
    _compuesta(win, tmp_path)
    win.pipes.append({"layer": "DRENAJE", "pts": [(10, 10), (200, 10)], "name": "", "diam": 12.0})
    escala, tam = win.canvas.fondo_escala, win.canvas.tam_hoja()
    r = respaldo_editor.tomar(win)
    img = QtGui.QImage(50, 40, QtGui.QImage.Format_RGB888); img.fill(QtGui.QColor("white"))
    win.canvas.set_image(img)                          # otra hoja (normal)
    assert win.canvas.fondo_escala == 1.0
    respaldo_editor.reponer(win, r)
    assert win.canvas.fondo_escala == pytest.approx(escala) and win.canvas.tam_hoja() == tam


def test_si_falla_armar_la_hoja_el_editor_no_queda_vacio(win, tmp_path, monkeypatch):
    from ui.ventana import app_window
    win._open_pdf_path(_pdf(tmp_path / "plano.pdf"))
    win._apply_composite()
    otra = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 1, 1], x=600.0)])
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet",
                        lambda parent, sources, comp, hidden, **kw: (otra, list(sources), dict(hidden or {})))

    def falla(*a, **k):
        raise RuntimeError("code=5: Overly large image")
    monkeypatch.setattr(app_window.Main, "_build_composite_doc", falla)
    assert win._wizard_sheet_flow(0) is False
    assert win.doc is not None and not win.doc.is_closed and win.doc.page_count == 2
    assert win.canvas.pixmap_item is not None and win.composite is None


# ── asistente ────────────────────────────────────────────────────────────────
def test_capas_de_la_hoja_enorme(app, chica, tmp_path):
    from ui.asistente import layer_dialog
    _pdf(tmp_path / "p.pdf")
    doc = fitz.open(str(tmp_path / "p.pdf"))
    try:
        dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
        tam = fondo_pdf.tam_px(doc[0], layer_dialog._PREVIEW_ZOOM)
        assert isinstance(dlg._pix_item, fondo_pdf.FondoItem)
        assert dlg.view.sceneRect() == QtCore.QRectF(0, 0, *tam)
        assert dlg._render_zoom() == pytest.approx(layer_dialog._PREVIEW_ZOOM, abs=0.01)
        item = dlg._pix_item
        dlg._render()                                  # marcar/desmarcar una capa
        assert dlg._pix_item is item
        dlg.view.resetTransform(); dlg.view.centerOn(LX * 3, LY * 3)
        dlg._nitidez.actualizar()
        assert item.nitido is not None
        dlg.reject()
    finally:
        doc.close()


def test_vista_previa_con_hoja_enorme(win, chica, tmp_path):
    from reconocimiento import recognition as rec
    from ui.asistente import recognition_dialog as rd
    _compuesta(win, tmp_path)
    cv = win.canvas
    fondo = {"escala": cv.fondo_escala, "tam": cv.tam_hoja(), "zoom": win.zoom, "pagina": win._pagina_fondo}
    res = rec.RecognitionResult("ELECTRICO", 0, 20 / 72.0)
    dlg = rd.RecognitionPreviewDialog(win, cv.pixmap_item.pixmap().toImage(), res, "ELECTRICO", fondo=fondo)
    try:
        assert dlg.view.sceneRect() == QtCore.QRectF(0, 0, *cv.tam_hoja())
        assert isinstance(dlg._pixmap_item, fondo_pdf.FondoItem)
        dlg.view.resetTransform(); dlg.view.centerOn(1000, 700)
        dlg._nitidez.actualizar()
        n = dlg._pixmap_item.nitido
        assert n is not None
        dlg._redraw_overlay()                          # redibujar lo reconocido no quita el recorte
        assert dlg._pixmap_item.nitido is n and n.scene() is dlg.view.scene()
    finally:
        dlg.reject()
