"""La hoja se ve nítida a CUALQUIER zoom, sin tocar coordenadas ni composición.

Pedido del usuario (2026-10-13, «Componer hoja» de un mapa de Phoenix: al acercarse la hoja
quedaba borrosa): el compositor re-dibujaba lo visible a 4 px/pt como mucho y «Capas de la
hoja», la vista previa y el editor nunca pasaban de la resolución de su imagen. Ahora el
recorte va a la resolución de la pantalla (`recorte_nitido`). En hojas con fuentes Type3 (el
mapa de Phoenix: cada letra declara una caja ~20× su tamaño y MuPDF la dibuja entera aunque
caiga fuera) el recorte descarta las letras de fuera: mismos píxeles, de 6 s a <1 s.
"""
import math
import os
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from hoja import composite as C  # noqa: E402
from ui.comun import fondo_pdf, recorte_nitido as R  # noqa: E402

PHOENIX = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/QS Water_Indian School_South.pdf")
LX, LY = 300.7, 200.3


# ── PDFs sintéticos ──────────────────────────────────────────────────────────
def _pdf_type3(rotate=0, n=400, seed=7):
    """Hoja con letras de una fuente Type3 como la del mapa de Phoenix: FontBBox
    [-10 -10 10 10] con FontMatrix identidad (caja declarada = 20× el cuerpo), letras de
    1.2 pt a varios giros, más unas líneas."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    def obj(texto, stream=None):
        x = doc.get_new_xref()
        doc.update_object(x, texto)
        if stream is not None:
            doc.update_stream(x, stream)
        return x

    a = obj("<<>>", b"1 0 -10 -10 10 10 d1 0 0 m 0.6 0 l 0.6 0.8 l 0 0.8 l f")
    b = obj("<<>>", b"1 0 -10 -10 10 10 d1 0 0 m 0.6 0 l 0.3 0.8 l f")
    procs = obj(f"<< /a {a} 0 R /b {b} 0 R >>")
    enc = obj("<< /Type /Encoding /Differences [65 /a /b] >>")
    font = obj(f"<< /Type /Font /Subtype /Type3 /FontBBox [-10 -10 10 10] /FontMatrix [1 0 0 1 0 0] "
               f"/CharProcs {procs} 0 R /Encoding {enc} 0 R /FirstChar 65 /LastChar 66 "
               f"/Widths [1 1] /Resources << >> >>")
    rng = np.random.default_rng(seed)
    ops = [b"0.4 w 10 10 m 390 290 l S 20 280 m 380 20 l S"]
    for _ in range(n):
        x, y = rng.uniform(5, 395), rng.uniform(5, 295)
        g = rng.uniform(0, 2 * math.pi)
        c, s = math.cos(g), math.sin(g)
        ops.append(f"BT /T3 2 Tf {c:.4f} {s:.4f} {-s:.4f} {c:.4f} {x:.3f} {y:.3f} Tm (ABBA) Tj ET".encode())
    cont = obj("<<>>", b"\n".join(ops))
    doc.xref_set_key(page.xref, "Contents", f"{cont} 0 R")
    doc.xref_set_key(page.xref, "Resources", f"<< /Font << /T3 {font} 0 R >> >>")
    if rotate:
        page.set_rotation(rotate)
    return fitz.open("pdf", doc.tobytes())


def _pdf_texto(path=None, w=600, h=400, pages=2):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=w, height=h)
        pg.draw_line((50, LY), (w - 50, LY), width=0.5)
        pg.draw_line((LX, 20), (LX, h - 20), width=0.5)
        pg.insert_text((50, 60), f"hoja {i + 1}")
    if path is None:
        return fitz.open("pdf", doc.tobytes())
    doc.save(str(path)); doc.close()
    return str(path)


def _igual(pix, ref):
    return ((pix.x, pix.y, pix.width, pix.height, pix.n) == (ref.x, ref.y, ref.width, ref.height, ref.n)
            and pix.samples == ref.samples)


def _recortes(page, escalas, k=4, seed=3):
    rng = np.random.default_rng(seed)
    W, H = page.rect.width, page.rect.height
    for s in escalas:
        for _ in range(k):
            w, h = rng.uniform(8, W / 2), rng.uniform(8, H / 2)
            x, y = rng.uniform(0, W - w), rng.uniform(0, H - h)
            yield s, (x, y, x + w, y + h)


# ── recorte_nitido (sin Qt) ──────────────────────────────────────────────────
@pytest.mark.parametrize("rotate", [0, 90])
def test_type3_mismos_pixeles_que_el_render_de_siempre(rotate):
    doc = _pdf_type3(rotate)
    page = doc[0]
    assert R.usa_type3(page)
    hojas = R.Hojas()
    cajas = hojas.cajas(page)
    assert cajas is not None and len(cajas) == 400 * 4
    # caja declarada: ~40 pt para letras de 1.2 pt (como Phoenix)
    assert np.median(np.maximum(cajas[:, 2] - cajas[:, 0], cajas[:, 3] - cajas[:, 1])) > 30
    for s, rect in _recortes(page, (2.0, 6.0, 15.0, 40.0)):
        clip = fitz.Rect(*rect)
        pix = hojas.render(page, rect, s)
        ref = page.get_pixmap(matrix=fitz.Matrix(s, s), clip=clip, alpha=False)
        assert _igual(pix, ref), (s, rect)


def test_type3_el_recorte_descarta_las_letras_de_fuera():
    """En un recorte chico MuPDF solo dibuja las letras cuya caja toca el recorte."""
    page = _pdf_type3()[0]
    cajas = R.Hojas().cajas(page)
    clip = fitz.Rect(150, 100, 170, 112)
    zona = R._zona_a_conservar(cajas, clip, 20.0)
    total = float(((cajas[:, 2] - cajas[:, 0]) * (cajas[:, 3] - cajas[:, 1])).sum())
    assert R._area_dibujada(cajas, zona) < 0.35 * total
    # toda letra que toca el recorte queda ENTERA dentro de la zona (no se descarta)
    toca = ((cajas[:, 0] <= clip.x1) & (cajas[:, 2] >= clip.x0)
            & (cajas[:, 1] <= clip.y1) & (cajas[:, 3] >= clip.y0))
    x0, y0, x1, y1 = zona
    t = cajas[toca]
    assert toca.any() and (t[:, 0] >= x0).all() and (t[:, 2] <= x1).all()
    assert (t[:, 1] >= y0).all() and (t[:, 3] <= y1).all()


def test_sin_type3_es_el_render_de_siempre():
    doc = _pdf_texto()
    page = doc[0]
    hojas = R.Hojas()
    assert not R.usa_type3(page) and hojas.cajas(page) is None
    for s, rect in _recortes(page, (3.0, 12.0, 50.0), k=3):
        pix = hojas.render(page, rect, s)
        assert _igual(pix, page.get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(*rect), alpha=False))
    # sin tope de 4 px/pt: la escala que pide la pantalla (con el tope de píxeles)
    assert hojas.escala(page, (100, 100, 140, 120), 30.0, minimo=4.0) == 30.0
    assert hojas.escala(page, (0, 0, 600, 400), 30.0, minimo=4.0) == pytest.approx(math.sqrt(R.MAX_PX / 240000))


def test_tope_por_letras_type3_nunca_menos_que_antes():
    page = _pdf_type3(n=1500)[0]
    hojas = R.Hojas()
    cajas = hojas.cajas(page)
    rect = (0, 0, 400, 300)
    e = hojas.escala(page, rect, 40.0, minimo=4.0)
    area = R._area_dibujada(cajas, R._zona_a_conservar(cajas, fitz.Rect(*rect), e))
    assert 4.0 <= e < 40.0
    assert area * e * e <= R.TOPE_LETRAS_MPX * 1e6 * 1.001 or e == 4.0
    # hoja con pocas letras: la escala de la pantalla
    rala = _pdf_type3(n=30)[0]
    assert R.Hojas().escala(rala, (150, 100, 160, 106), 40.0, minimo=4.0) == 40.0


def test_capas_cambiadas_soltar_rehace_la_lista():
    doc = fitz.open()
    pg = doc.new_page(width=200, height=200)
    ocg = doc.add_ocg("A", on=True)
    pg.draw_rect(fitz.Rect(20, 20, 180, 180), color=(0, 0, 0), fill=(0, 0, 0), oc=ocg)
    hojas = R.Hojas()
    lleno = hojas.render(doc[0], (50, 50, 60, 60), 4.0)
    doc.set_layer_ui_config(0, 2)                       # apagar la capa
    hojas.soltar()
    vacio = hojas.render(doc[0], (50, 50, 60, 60), 4.0)
    assert set(lleno.samples) == {0} and set(vacio.samples) == {255}


@pytest.mark.skipif(not PHOENIX.is_file(), reason="PDF de Phoenix no disponible")
def test_phoenix_mismos_pixeles_y_rapido():
    doc = fitz.open(str(PHOENIX))
    page = doc[0]
    hojas = R.Hojas()
    assert hojas.cajas(page) is not None
    for s, rect in _recortes(page, (8.0,), k=2):
        assert _igual(hojas.render(page, rect, s),
                      page.get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(*rect), alpha=False))
    # el recorte que pedía el reporte (~16 px/pt, una vista): antes ~3 s, a 24 px/pt 6 s
    rect = (200.0, 300.0, 300.0, 362.0)
    e = hojas.escala(page, rect, 18.0, minimo=4.0)
    t = time.perf_counter()
    hojas.render(page, rect, e)
    assert e >= 8.0 and time.perf_counter() - t < 1.5


# ── vistas (Qt offscreen) ────────────────────────────────────────────────────
@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


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


def _centro_columna(scene, x, y, lado=40, px=8):
    """x de la tinta (columna) alrededor de (x, y) de la escena, dibujada a `px` px por px."""
    n = lado * px
    img = QtGui.QImage(n, n, QtGui.QImage.Format_Grayscale8); img.fill(255)
    p = QtGui.QPainter(img)
    scene.render(p, QtCore.QRectF(0, 0, n, n), QtCore.QRectF(x - lado / 2, y - lado / 2, lado, lado))
    p.end()
    a = 255.0 - np.frombuffer(img.constBits(), np.uint8).reshape(n, img.bytesPerLine())[:, :n]
    col = a.sum(axis=0)
    return x - lado / 2 + (col * (np.arange(n) + 0.5)).sum() / col.sum() / px


def _abrir(win, tmp_path):
    win._open_pdf_path(_pdf_texto(tmp_path / "plano.pdf"))
    win._load_page(0)                                  # (el asistente está apagado en la prueba)
    QtWidgets.QApplication.instance().processEvents()


def test_editor_hoja_normal_nitida_mas_alla_de_su_imagen(win, tmp_path):
    _abrir(win, tmp_path)
    cv = win.canvas
    assert cv.fondo_escala == 1.0 and isinstance(cv.pixmap_item, fondo_pdf.FondoItem)
    x, y = LX * win.zoom, 120 * win.zoom
    cv.resetTransform(); cv.scale(6.0, 6.0); cv.centerOn(x, y)
    cv.nitidez.actualizar()
    n = cv.pixmap_item.nitido
    assert n is not None and n.parentItem() is cv.pixmap_item
    escala = cv.nitidez._clave[-1]
    assert escala > 4 * win.zoom                        # antes: nunca más que la imagen (3.5)
    p0 = n.mapToScene(QtCore.QPointF(0, 0))
    ox, oy = p0.x() / win.zoom * escala, p0.y() / win.zoom * escala
    assert abs(ox - round(ox)) < 1e-6 and abs(oy - round(oy)) < 1e-6
    assert abs(_centro_columna(cv.scene(), x, y) - x) < 0.25     # la línea, donde debe
    # el imán sigue mirando la imagen de siempre (mismo punto)
    win.snap = True
    sx, _ = win._snap(x + 6, y)
    assert abs(sx - x) <= 1.0
    cv.resetTransform(); cv.nitidez.actualizar()
    assert cv.pixmap_item.nitido is None


def test_capas_de_la_hoja_normal_nitida(app):
    from ui.asistente import layer_dialog
    doc = _pdf_texto()
    try:
        dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
        z = layer_dialog._PREVIEW_ZOOM
        dlg.view.resetTransform(); dlg.view.scale(5.0, 5.0); dlg.view.centerOn(LX * z, LY * z)
        dlg._nitidez.actualizar()
        assert dlg._pix_item.nitido is not None and dlg._nitidez._clave[-1] > 4 * z
        dlg.reject()
    finally:
        doc.close()


def test_vista_previa_normal_nitida(win, tmp_path):
    from reconocimiento import recognition as rec
    from ui.asistente import recognition_dialog as rd
    _abrir(win, tmp_path)
    cv = win.canvas
    fondo = {"escala": cv.fondo_escala, "tam": cv.tam_hoja(), "zoom": win.zoom, "pagina": win._pagina_fondo}
    res = rec.RecognitionResult("ELECTRICO", 0, 20 / 72.0)
    dlg = rd.RecognitionPreviewDialog(win, cv.pixmap_item.pixmap().toImage(), res, "ELECTRICO", fondo=fondo)
    try:
        assert dlg.view.sceneRect() == QtCore.QRectF(cv.pixmap_item.pixmap().rect())
        dlg.view.resetTransform(); dlg.view.scale(5.0, 5.0); dlg.view.centerOn(LX * win.zoom, LY * win.zoom)
        dlg._nitidez.actualizar()
        assert dlg._pixmap_item.nitido is not None
    finally:
        dlg.reject()


def test_compositor_nitido_mas_alla_de_4_px_por_pt(app):
    from ui.asistente import composite_dialog
    doc = _pdf_texto()
    data = doc.tobytes()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg.resize(1400, 800); dlg.show()
        # «Área a tomar»: a 12× el recorte va a ~14 px/pt (antes 4) y cae EXACTO
        dlg.crop.resetTransform(); dlg.crop.scale(12.0, 12.0); dlg.crop.centerOn(LX, LY)
        dlg._crop_sharp.update_quality()
        it = dlg._crop_sharp._item
        escala = dlg._crop_sharp._key[-1]
        assert it is not None and escala > 4.0
        assert abs(it.transform().m11() - 1.0 / escala) < 1e-12
        ox, oy = it.pos().x() * escala, it.pos().y() * escala
        assert abs(ox - round(ox)) < 1e-6 and abs(oy - round(oy)) < 1e-6
        assert abs(_centro_columna(dlg.crop.scene(), LX, LY + 15, lado=10, px=24) - LX) < 0.05
        # «Hoja compuesta»: igual en cada pieza
        dlg._take(full=True)
        dlg.view.resetTransform(); dlg.view.scale(12.0, 12.0); dlg.view.centerOn(LX, LY)
        dlg.view._update_quality()
        pieza = dlg.view.items[0]
        assert pieza._sharp is not None and pieza._sharp_key[-1] > 4.0
    finally:
        dlg.close_docs()


def test_type3_primero_rapido_y_con_la_vista_quieta_a_resolucion_completa(app, monkeypatch):
    """Hoja con muchas letras Type3: al moverse, el recorte con tope de letras; con la
    vista quieta, otro con más resolución; volver a pedir el primero no lo empeora."""
    from ui.asistente import composite_dialog
    monkeypatch.setattr(R, "TOPE_LETRAS_MPX", 40.0)
    import ui.asistente.pdf_view_quality as Q
    import ui.asistente.composite_view as V
    monkeypatch.setattr(Q, "TOPE_LETRAS_MPX", 40.0)
    monkeypatch.setattr(V, "TOPE_LETRAS_MPX", 40.0)
    data = _pdf_type3(n=1500).tobytes()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        dlg.resize(1400, 800); dlg.show()
        sh = dlg._crop_sharp
        dlg.crop.resetTransform(); dlg.crop.scale(12.0, 12.0); dlg.crop.centerOn(200, 150)
        sh.update_quality()
        rapido = sh._key[-1]
        assert 4.0 <= rapido < 12 * 1.15 * 0.98 and sh._refine.isActive()
        sh.update_quality(refine=True)
        fino = sh._key[-1]
        assert fino > rapido
        sh.update_quality()                         # misma vista: se queda el fino
        assert sh._key[-1] == fino and not sh._refine.isActive()
        # «Hoja compuesta»: igual
        dlg._take(full=True)
        v = dlg.view
        v.resetTransform(); v.scale(12.0, 12.0); v.centerOn(200, 150)
        v._update_quality()
        pieza = v.items[0]
        rapido = pieza._sharp_key[-1]
        assert v._refine.isActive()
        v._update_quality(refine=True)
        assert pieza._sharp_key[-1] > rapido
    finally:
        dlg.close_docs()


def test_type3_en_el_editor_se_refina(win, tmp_path, monkeypatch):
    import ui.comun.fondo_pdf as F
    monkeypatch.setattr(F, "TOPE_LETRAS_MPX", 300.0)
    ruta = tmp_path / "t3.pdf"
    _pdf_type3(n=1500).save(str(ruta))
    win._open_pdf_path(str(ruta)); win._load_page(0)
    cv = win.canvas
    cv.resetTransform(); cv.scale(4.0, 4.0); cv.centerOn(200 * win.zoom, 150 * win.zoom)
    cv.nitidez.actualizar()
    rapido = cv.nitidez._clave[-1]
    assert cv.pixmap_item.nitido is not None and cv.nitidez._refino.isActive()
    cv.nitidez.actualizar(refinar=True)
    assert cv.nitidez._clave[-1] > rapido
    cv.nitidez.programar()                          # la vista se mueve: no refina sola
    assert not cv.nitidez._refino.isActive()
