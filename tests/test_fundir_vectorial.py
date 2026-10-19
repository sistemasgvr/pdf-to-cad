"""«Fundir bordes» también en los PDF VECTORIALES, con y sin capas (pedido del usuario 2026-10-19).

Lo que ya hacían los escaneos (modo oscurecer: donde dos piezas se superponen se ve la tinta de
las dos) ahora en el compositor de PDF ploteados y de mapas sin capas. Cubre:
  · solo se funden las piezas que se SUPERPONEN a una anterior (`composite_fundir.solapadas`):
    borde con borde el PDF sale igual que siempre;
  · la pieza vectorial fundida va como grupo AISLADO: lo blanco de una no tapa la tinta de la
    otra, pero DENTRO de cada hoja todo sigue igual (el fondo blanco de un rótulo sigue tapando);
  · los lectores de vectores (reconocimiento, «Capas de la hoja», leyenda de mapas) ven los
    mismos trazos, con los mismos recortes, con y sin fundir;
  · el botón «Fundir bordes» en el compositor vectorial.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import fitz
import pytest
from PySide6 import QtWidgets

from hoja import composite as C
from hoja import composite_fundir as F
from hoja import leyenda_mapa_lectura as lectura
from hoja import leyenda_trazos
from reconocimiento import recognition as R
from ui.asistente.composite_dialog import CompositeDialog

W, H = 300.0, 200.0
CAPA = "C-ELEC-UNGD-N"


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def hoja_vectorial(capas=True, fondo=True):
    """Hoja de 300×200 pt: fondo blanco opaco (como un mapa SIG), raya vertical en x=100,
    horizontal en y=50 tapada en 200–240 por un recuadro blanco (el fondo de un rótulo) y
    guiones por toda la hoja (para el reconocimiento)."""
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    oc = doc.add_ocg(CAPA) if capas else 0
    if fondo:
        page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    page.draw_line((100, 0), (100, H), color=(0, 0, 0), width=4, oc=oc)
    page.draw_line((150, 50), (290, 50), color=(0, 0, 0), width=2, oc=oc)
    page.draw_rect(fitz.Rect(200, 40, 240, 60), color=None, fill=(1, 1, 1))
    for x in range(5, 295, 12):
        page.draw_line((x, 150), (x + 8, 150), color=(0, 0, 0), width=1, oc=oc)
    return doc


def armar(doc, piezas, blend=True):
    comp = C.Composite([C.Piece.from_dict(p.to_dict()) for p in piezas], bridges=False, seam_blend=blend)
    return comp, C.build_document(comp, [doc])


def superpuestas(dx=60.0):
    """A = la hoja entera; B = la misma hoja corrida `dx` pt: se superponen W − dx."""
    return [C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 0, [0, 0, 1, 1], x=dx)]


def pixel(built, comp, x, y):
    _, _, dx, dy = C.sheet_geometry(comp, lambda p: (W, H))
    return built[0].get_pixmap().pixel(round(x + dx), round(y + dy))


def grupos(page):
    return [d for d in page.get_drawings(extended=True) if d.get("type") == "group"]


# ── puro ────────────────────────────────────────────────────────────────
def test_interseccion_y_ancho():
    a = [(0, 0), (100, 0), (100, 50), (0, 50)]
    b = [(90, -10), (200, -10), (200, 60), (90, 60)]
    assert F.ancho(F.interseccion(a, b)) == pytest.approx(10.0)
    assert F.ancho(F.interseccion(a, [(100, 0), (200, 0), (200, 50), (100, 50)])) == pytest.approx(0.0)
    assert F.interseccion(a, [(150, 0), (200, 0), (200, 50), (150, 50)]) == []
    rombo = [(50, -30), (80, 25), (50, 80), (20, 25)]          # girado, sentido contrario
    assert F.ancho(F.interseccion(a, rombo)) > 20


def test_solo_se_funden_las_piezas_superpuestas():
    caja = lambda x0, x1: [(x0, 0), (x1, 0), (x1, 100), (x0, 100)]   # noqa: E731
    assert F.solapadas([caja(0, 100), caja(100, 200)]) == set()            # borde con borde
    assert F.solapadas([caja(0, 100), caja(99.5, 200)]) == set()           # imán: centésimas
    assert F.solapadas([caja(0, 100), caja(80, 200), caja(300, 400)]) == {1}
    assert F.solapadas([caja(0, 100), caja(300, 400), caja(350, 450)]) == {2}


def test_fundir_vale_para_todos_los_flujos():
    vect = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 0, [0, 0, 1, 1], x=W)])
    assert vect.blends() and not vect.manual
    sizes = lambda p: (W, H)                                       # noqa: E731
    assert C.blended_pieces(vect, sizes) == set()                  # borde con borde: nada cambia
    vect.pieces[1].x = W - 40
    assert C.blended_pieces(vect, sizes) == {1}
    vect.seam_blend = False
    assert C.blended_pieces(vect, sizes) == set()
    scan = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 0, [0, 0, 1, 1], x=W)], manual=True)
    assert C.blended_pieces(scan, sizes) == {0, 1}                 # escaneo: como siempre, todas


# ── PDF ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("capas", [True, False])
def test_superpuestas_se_ve_la_tinta_de_las_dos(capas):
    doc = hoja_vectorial(capas=capas)
    comp, built = armar(doc, superpuestas())
    assert len(grupos(built[0])) == 1 and grupos(built[0])[0]["isolated"]
    assert pixel(built, comp, 100, 120) == (0, 0, 0)        # raya de A bajo el fondo blanco de B
    # dentro de cada hoja nada cambia: el recuadro blanco de B sigue tapando SU línea…
    assert pixel(built, comp, 295, 50) == (255, 255, 255)
    # …y el de A la suya (B pone ahí solo papel)
    assert pixel(built, comp, 205, 50) == (255, 255, 255)
    comp0, built0 = armar(doc, superpuestas(), blend=False)
    assert pixel(built0, comp0, 100, 120) == (255, 255, 255)   # sin fundir, B la tapa
    assert grupos(built0[0]) == []


def test_borde_con_borde_el_pdf_no_cambia():
    doc = hoja_vectorial()
    piezas = [C.Piece(0, 0, [0, 0, 0.5, 1]), C.Piece(0, 0, [0.5, 0, 1, 1], x=W / 2)]
    _, con = armar(doc, piezas, blend=True)
    _, sin = armar(doc, piezas, blend=False)
    assert con[0].read_contents() == sin[0].read_contents()
    assert grupos(con[0]) == [] and "PdfcadDarken" not in con.xref_object(con[0].xref, compressed=True)


def test_franja_blanca_de_la_match_line_sigue_tapando():
    """Las franjas `covers` van FUERA del modo oscurecer: tapan la línea de borde también
    en una pieza fundida."""
    doc = hoja_vectorial(fondo=False)
    comp, built = armar(doc, superpuestas())
    assert pixel(built, comp, 100, 120) == (0, 0, 0)          # sin fondo, la raya de A se ve
    piezas = superpuestas()
    piezas[1].covers = {"left": 45.0}                         # franja de B: x 59.5–105 de la hoja
    comp, built = armar(doc, piezas)
    assert C.blended_pieces(comp, lambda p: (W, H)) == {1}
    assert pixel(built, comp, 100, 120) == (255, 255, 255)    # la franja de B tapa la raya de A


# ── los lectores de vectores ven lo mismo ───────────────────────────────
def _firma(page):
    _, vp, _, _ = R.gather_paths(page, lambda o: "structure" if o else None)
    r = lambda v: round(v, 3)                                  # noqa: E731
    return sorted((p.get("layer") or "", r(p["rect"].x0), r(p["rect"].y0), r(p["rect"].x1), r(p["rect"].y1),
                   bool(p.get("clipped")), len(p.get("clip_polys") or ())) for p in vp)


@pytest.mark.parametrize("capas", [True, False])
def test_reconocimiento_ve_los_mismos_trazos(capas):
    """La 1.ª pieza va sin fundir y la 2.ª fundida (grupo en el nivel 0): el recorte de la
    primera no puede seguir recortando a la segunda (`recognition._cerrar_recortes`)."""
    doc = hoja_vectorial(capas=capas)
    piezas = [C.Piece(0, 0, [0, 0, 0.6, 1]), C.Piece(0, 0, [0.4, 0, 1, 1], x=W * 0.4 + 20)]
    _, con = armar(doc, piezas, blend=True)
    _, sin = armar(doc, piezas, blend=False)
    assert len(grupos(con[0])) == 1
    firma = _firma(sin[0])
    assert firma and _firma(con[0]) == firma
    assert len(leyenda_trazos.trazos_visibles(con[0])) == len(leyenda_trazos.trazos_visibles(sin[0]))


def test_cada_pieza_fundida_sigue_siendo_una_pieza_para_la_leyenda():
    doc = hoja_vectorial(capas=False)
    piezas = superpuestas() + [C.Piece(0, 0, [0, 0, 1, 1], x=2 * W)]
    _, con = armar(doc, piezas, blend=True)
    _, sin = armar(doc, piezas, blend=False)
    assert lectura.inicios_de_piezas(con[0]) == lectura.inicios_de_piezas(sin[0])
    assert len(lectura.inicios_de_piezas(con[0])) == 3


# ── compositor vectorial ────────────────────────────────────────────────
def test_boton_fundir_bordes_en_el_compositor_vectorial(app):
    doc = hoja_vectorial()
    dlg = CompositeDialog(None, [{"name": "plano.pdf", "data": doc.tobytes()}], None, {}, 0)
    try:
        assert not dlg.comp.manual
        assert dlg.btn_blend.parent() is dlg.tool_bar and dlg.btn_blend.isChecked()
        assert dlg.view.comp.blends()
        dlg.btn_blend.setChecked(False)
        assert not dlg.comp.seam_blend and not dlg.view.comp.blends()
        assert "desactivado" in dlg.lbl_status.text()
        dlg.btn_blend.setChecked(True)
        assert dlg.comp.seam_blend and "tinta de las dos" in dlg.lbl_status.text()
        assert C.Composite.from_dict(dlg.comp.to_dict()).seam_blend
    finally:
        dlg.close_docs(); doc.close()
