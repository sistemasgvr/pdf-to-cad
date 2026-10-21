"""Hojas cuyo marco no es recto con la hoja (pedido del usuario 2026-10-21, «Southwest Gas Combined
811 Records»): el área sugerida y la composición sugerida siguen el borde inclinado (esquinas
libres) y lo que queda fuera es solo papel en blanco — el reconocimiento ve la MISMA tinta."""
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")

from hoja import area_sugerida as AS  # noqa: E402
from hoja import borde_inclinado as B  # noqa: E402
from hoja import composite as C  # noqa: E402

SW_GAS = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/APUNTES ING/"
              r"Southwest Gas Combined 811 Records (1) 37.pdf")
RECT = (100.0, 100.0, 700.0, 500.0)


def _hoja(abajo_izq=490.0, abajo_der=498.0, tinta_afuera=False):
    """Marco grueso de un mapa dentro de RECT: abajo inclinado (o recto si los dos valen igual),
    con el mapa dentro y papel en blanco entre el marco y el borde del rectángulo."""
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    sh = page.new_shape()
    sh.draw_polyline([(104, 104), (696, 104), (696, abajo_der), (104, abajo_izq), (104, 104)])
    sh.finish(color=(0, 0, 0), width=2.0, closePath=False)
    for k in range(10):                                    # el mapa
        y = 140 + 30 * k
        sh.draw_line((130, y), (670, y + 5))
    sh.finish(color=(0, 0.5, 0.5), width=0.5)
    if tinta_afuera:                                        # algo dibujado DEBAJO del marco
        sh.draw_line((300, 496), (360, 497))
        sh.finish(color=(0.8, 0, 0), width=0.5)
    sh.commit()
    return doc, page


def test_borde_inclinado_el_area_lo_sigue_y_la_linea_queda_entera_dentro():
    _doc, page = _hoja()
    q = B.cuadrilatero(page, RECT)
    assert q is not None and len(q) == 4
    (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = q
    # abajo: corre por FUERA de la línea (1 pt de medio grosor + 0.5), inclinado como ella
    assert bly == pytest.approx(490.0 + 1.5, abs=0.2) and bry == pytest.approx(498.0 + 1.5, abs=0.2)
    # los otros lados del mismo marco (paralelos) también: por fuera de su línea
    assert tlx == pytest.approx(104 - 1.5, abs=0.2) and tly == pytest.approx(104 - 1.5, abs=0.2)
    assert trx == pytest.approx(696 + 1.5, abs=0.2)


def test_marco_recto_queda_el_rectangulo():
    _doc, page = _hoja(abajo_izq=495.0, abajo_der=495.0)
    assert B.cuadrilatero(page, RECT) is None


def test_con_tinta_por_fuera_de_la_linea_no_es_el_borde():
    _doc, page = _hoja(tinta_afuera=True)
    q = B.cuadrilatero(page, RECT)
    assert q is None or q[2][1] >= 500.0 - 0.01        # el lado de abajo no se mueve a la línea


def test_composicion_sugerida_pieza_con_esquinas():
    """`composicion_sugerida.armar`: la pieza de una hoja con el marco inclinado va con su polígono."""
    from hoja import composicion_ficha as F, composicion_sugerida as G
    doc, page = _hoja()
    paths = page.get_drawings(extended=True)
    f = F.Ficha(0, 0, (page.rect.width, page.rect.height), vista=RECT,
                lineas=F._trazos(paths, page, RECT, F.BANDA_CAD_PT, F.BANDA_CAD_PT))
    g = G.Grupo("estaciones", [(0, 0)], [], transf={(0, 0): (1.0, 0.0, 0.0)})
    comp = G.armar(g, G.Analisis({(0, 0): f}, [g]), [doc], lambda *_a: 1.0)
    pz = comp.pieces[0]
    assert len(pz.polygon) == 4 and pz.covers == {}
    assert pz.polygon[3][1] * 600 == pytest.approx(491.5, abs=0.3)
    # marco recto: la pieza de siempre, sin polígono
    doc2, page2 = _hoja(abajo_izq=495.0, abajo_der=495.0)
    f2 = F.Ficha(0, 0, (800.0, 600.0), vista=RECT,
                 lineas=F._trazos(page2.get_drawings(extended=True), page2, RECT, F.BANDA_CAD_PT, F.BANDA_CAD_PT))
    g2 = G.Grupo("estaciones", [(0, 0)], [], transf={(0, 0): (1.0, 0.0, 0.0)})
    assert G.armar(g2, G.Analisis({(0, 0): f2}, [g2]), [doc2], lambda *_a: 1.0).pieces[0].polygon == []


# ── con el PDF del reporte ──────────────────────────────────────────────
def _sw():
    if not SW_GAS.is_file():
        pytest.skip("PDF de Southwest Gas no disponible")
    return fitz.open(str(SW_GAS))


def _tinta_reconocida(src, clip, polygon):
    from hoja import pdf_styles
    from reconocimiento import recognition as R
    comp = C.Composite(pieces=[C.Piece(0, 0, clip, polygon=polygon)], bridges=False)
    d = fitz.open(stream=C.build_document(comp, [src], {}, []).tobytes(), filetype="pdf")
    with pdf_styles.lectura_unica(d):
        lines, *_ = R.gather_paths(d[0], lambda o: "elec_ungd", set(), None)
    out = []
    for p in lines:
        for it in p.get("items") or ():
            pts = tuple((round(float(c.x), 2), round(float(c.y), 2)) for c in it[1:] if hasattr(c, "x"))
            out.append((it[0], pts, p.get("layer")))
    return sorted(out, key=repr)


def test_southwest_gas_area_sugerida_sigue_el_marco_y_el_reconocimiento_ve_la_misma_tinta():
    src = _sw()
    page = src[0]
    W, H = page.rect.width, page.rect.height
    a = AS.sugerir(page)[0]
    assert len(a.poligono) == 4
    (tlx, _), _, (_, bry), (blx, bly) = a.poligono
    assert tlx - blx > 8 and bry - bly > 12              # izquierda y abajo, inclinados
    clip = a.clip((W, H))
    rect = _tinta_reconocida(src, clip, [])
    cuad = _tinta_reconocida(src, clip, [[x / W, y / H] for x, y in a.poligono])
    assert len(rect) > 5000 and rect == cuad


# ── ventana ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_usar_area_inclinada_da_la_misma_pieza_que_marcar_las_esquinas_a_mano(app, monkeypatch):
    from PySide6 import QtCore
    from ui.asistente import composite_dialog, composite_area_suggest as UI
    _sw()
    monkeypatch.setenv("PDFCAD_AREA_SUGERIDA", "1")
    UI._CACHE.clear()
    fuente = [{"name": SW_GAS.name, "data": SW_GAS.read_bytes()}]

    def esperar(cond, s=120.0):
        fin = time.time() + s
        while time.time() < fin and not cond():
            app.processEvents()
            time.sleep(0.02)
        assert cond()
    dlg = composite_dialog.CompositeDialog(None, fuente, None, {}, 0)
    try:
        dlg._go_tab(composite_dialog.TAB_AREA)
        esperar(lambda: bool(dlg._area_lista))
        assert dlg._area_lista[0].poligono
        esquinas = [QtCore.QPointF(p) for p in dlg._area_esquinas()]
        dlg._area_usar()
        esperar(lambda: not dlg._crop_timer.isActive(), 5)
        app.processEvents()
        assert dlg.chk_corners.isChecked() and not dlg.btn_area_usar.isVisibleTo(dlg)
        pz = dlg.comp.pieces[0]
        sugerida = ([round(v, 9) for v in pz.clip], pz.polygon)
        assert len(pz.polygon) == 4
    finally:
        dlg.close_docs(); dlg.deleteLater()
    monkeypatch.setenv("PDFCAD_AREA_SUGERIDA", "0")
    dlg = composite_dialog.CompositeDialog(None, fuente, None, {}, 0)
    try:
        dlg._go_tab(composite_dialog.TAB_AREA)
        dlg.chk_corners.setChecked(True)
        dlg.crop.set_polygon(esquinas)                    # el usuario mueve las esquinas ahí
        esperar(lambda: not dlg._crop_timer.isActive(), 5)
        app.processEvents()
        pz = dlg.comp.pieces[0]
        assert ([round(v, 9) for v in pz.clip], pz.polygon) == sugerida
    finally:
        dlg.close_docs(); dlg.deleteLater()
