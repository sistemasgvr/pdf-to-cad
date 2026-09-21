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

    kind, info = detect.classify_page(_FakePage())
    assert kind == "raster"
    assert info["n_paths"] == 0
