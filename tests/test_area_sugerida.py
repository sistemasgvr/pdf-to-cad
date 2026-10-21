"""«Área sugerida» en «Área a tomar» (pedido del usuario 2026-10-20): qué área se sugiere en
cada tipo de hoja y que usarla da la MISMA pieza que marcar ese rectángulo a mano (el
reconocimiento no cambia)."""
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
from hoja import composicion_ficha as F  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
PHX = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
DU06 = DOCS / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"
DU10 = DOCS / "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf"
LABOE = DOCS / "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf"
WATER_S = PHX / "QS Water_Indian School_South.pdf"
SD_N = PHX / "QS SD_Indian School_North.pdf"


def _hoja(pdf: Path, n: int):
    if not pdf.is_file():
        pytest.skip(f"PDF de prueba no disponible: {pdf.name}")
    return fitz.open(str(pdf))[n - 1]


# ── núcleo ──────────────────────────────────────────────────────────────
def test_hoja_sin_dibujo_no_sugiere_nada():
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_text((50, 50), "NOTAS GENERALES", fontsize=12)
    assert AS.sugerir(page) == []


def test_clip_normalizado():
    a = AS.Area((60.0, 40.0, 540.0, 360.0), "vista")
    assert a.clip((600.0, 400.0)) == [0.1, 0.1, 0.9, 0.9]


def test_planta_cortada_en_sus_match_lines():
    page = _hoja(DU06, 4)
    f = F.ficha(page)
    areas = AS.sugerir(page, f)
    assert len(areas) == 1 and areas[0].tipo == "planta"
    a = areas[0]
    assert len(a.estaciones) == 2                       # una match line a cada lado
    v = f.vista
    assert v[0] - 2 <= a.rect[0] < a.rect[2] <= v[2] + 2 and v[1] - 2 <= a.rect[1] < a.rect[3] <= v[3] + 2


def test_plano_y_perfil_sugiere_la_planta():
    """LABOE h.26: perfil arriba y planta abajo (dos viewports): la planta."""
    page = _hoja(LABOE, 26)
    a = AS.sugerir(page)[0]
    assert a.rect[1] > 0.4 * page.rect.height


def test_vista_de_planta_sin_match_lines():
    """DU08 h.36: perfil (con capas PROF) arriba, planta abajo, sin rótulos de match line."""
    page = _hoja(DU08, 36)
    a = AS.sugerir(page)[0]
    assert a.tipo == "vista" and a.rect[1] > 0.4 * page.rect.height and a.parte > 0.9


def test_hoja_de_notas_aplanada_no_sugiere_el_marco():
    assert AS.sugerir(_hoja(DU10, 30)) == []


def test_mapa_su_marco():
    page = _hoja(WATER_S, 6)
    f = F.ficha(page)
    a = AS.sugerir(page, f)[0]
    assert a.tipo == "mapa" and a.etiqueta == "16-15" and AS.iguales(a.rect, f.vista)


def test_mapa_sin_recorte_su_marco_de_lineas():
    """Drenaje de Phoenix: el marco no es un recorte, son cuatro líneas; la leyenda queda fuera."""
    page = _hoja(SD_N, 1)
    a = AS.sugerir(page)[0]
    W, H = page.rect.width, page.rect.height
    assert a.tipo == "mapa"
    assert 0.5 < (a.rect[2] - a.rect[0]) * (a.rect[3] - a.rect[1]) / (W * H) < 0.85
    assert a.rect[3] < 0.97 * H                         # la franja de la leyenda (abajo) no entra


# ── ventana ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _esperar(app, cond, segundos=120.0):
    fin = time.time() + segundos
    while time.time() < fin and not cond():
        app.processEvents()
        time.sleep(0.02)
    assert cond()


def _pieza(dlg):
    p = dlg.comp.pieces[0]
    return [round(v, 9) for v in p.clip], p.covers, p.polygon, p.source, p.page, round(p.src_scale, 12)


def test_usar_el_area_sugerida_da_la_misma_pieza_que_marcarla_a_mano(app, monkeypatch):
    from PySide6 import QtCore
    from ui.asistente import composite_dialog, composite_area_suggest as UI
    if not DU06.is_file():
        pytest.skip("PDF DU06 no disponible")
    monkeypatch.setenv("PDFCAD_AREA_SUGERIDA", "1")
    UI._CACHE.clear()
    fuente = [{"name": DU06.name, "data": DU06.read_bytes()}]
    dlg = composite_dialog.CompositeDialog(None, fuente, None, {}, 3)
    try:
        dlg._go_tab(composite_dialog.TAB_AREA)
        _esperar(app, lambda: bool(dlg._area_lista))
        assert dlg.area_box.isVisibleTo(dlg) and dlg._area_item.isVisible()
        assert dlg.btn_area_usar.isVisibleTo(dlg)
        rect = dlg._area_rect()
        dlg._area_usar()
        _esperar(app, lambda: not dlg._crop_timer.isActive(), 5)
        app.processEvents()
        assert not dlg._area_item.isVisible() and not dlg.btn_area_usar.isVisibleTo(dlg)   # ✔ marcada
        sugerida = _pieza(dlg)
    finally:
        dlg.close_docs(); dlg.deleteLater()
    # lo mismo a mano: el usuario marca ese rectángulo
    monkeypatch.setenv("PDFCAD_AREA_SUGERIDA", "0")
    dlg = composite_dialog.CompositeDialog(None, fuente, None, {}, 3)
    try:
        dlg._go_tab(composite_dialog.TAB_AREA)
        dlg.crop.set_selection(QtCore.QRectF(rect))
        _esperar(app, lambda: not dlg._crop_timer.isActive(), 5)
        app.processEvents()
        assert _pieza(dlg) == sugerida
        assert not dlg.area_box.isVisibleTo(dlg)        # apagada: ni tarjeta
    finally:
        dlg.close_docs(); dlg.deleteLater()
