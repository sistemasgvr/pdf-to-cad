"""Smoke: detect.py clasifica PDF ploteado vs raster."""
from pathlib import Path

import pytest

import detect

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"

pytest.importorskip("fitz")


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_du06_page0_is_vector():
    import fitz
    doc = fitz.open(PDF)
    try:
        kind, info = detect.classify_page(doc[0])
    finally:
        doc.close()
    assert kind == "vector"
    assert info["n_paths"] >= 80
    assert info["kind"] == "vector"


def test_classify_page_raster_when_few_paths_no_image(monkeypatch):
    """Sin trazos ni imagen dominante → raster (fallback)."""
    class _FakePage:
        rotation = 0
        mediabox = type("MB", (), {"width": 100, "height": 100})()
        rect = type("R", (), {"width": 100, "height": 100})()

        def get_drawings(self):
            return []

        def get_images(self, full=True):
            return []

        def get_image_rects(self, xref):
            return []

        def get_text(self):
            return ""

        def get_fonts(self):
            return []

        parent = None

    kind, info = detect.classify_page(_FakePage())
    assert kind == "raster"
    assert info["n_paths"] == 0


SCAN = ROOT / "tests" / "fixtures" / "escaneado_vectorizado.pdf"


@pytest.mark.skipif(not SCAN.is_file(), reason="fixture no disponible")
def test_escaneo_vectorizado_es_raster_no_ploteado():
    """Un plano escaneado y pasado por un vectorizador trae miles de trazos
    (12 321) pero ningún texto, fuente ni capa OCG: NO es un plot CAD y no debe
    entrar al asistente de hojas/capas (lo reportó el usuario)."""
    import fitz
    doc = fitz.open(SCAN)
    try:
        kind, info = detect.classify_page(doc[0])
    finally:
        doc.close()
    assert kind == "raster" and info["traced"]
    assert info["n_paths"] > 1000 and info["text_chars"] == 0 and info["n_ocgs"] == 0


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_du06_todas_las_hojas_son_vector():
    import fitz
    doc = fitz.open(PDF)
    try:
        kinds = {detect.classify_page(doc[i])[0] for i in range(doc.page_count)}
    finally:
        doc.close()
    assert kinds == {"vector"}


def test_escaneo_con_anotaciones_vectoriales_es_raster(tmp_path):
    """Imagen a página completa + anotaciones vectoriales con texto (markups
    de Bluebeam) → sigue siendo un escaneo."""
    import fitz
    doc = fitz.open(); page = doc.new_page(width=800, height=600)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), 0); pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    for k in range(120):
        page.draw_line((10 + k * 6, 20), (10 + k * 6, 80), color=(1, 0, 0))
    page.insert_text((50, 500), "NOTA DE REVISION " * 5, fontsize=10)
    kind, info = detect.classify_page(page)
    assert kind == "raster" and info["max_image_cover"] >= 0.99
