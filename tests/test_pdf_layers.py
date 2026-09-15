"""Pruebas de pdf_layers (capas OCG: listado y visibilidad) — headless, sin Qt."""
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

import pdf_layers
import recognition as rec

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
PAGE = 13   # UD-212: 101 capas con geometría, incluye C-ELEC-UNGD-E

needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")


def test_short_name():
    assert pdf_layers.short_name("PS89616000-A1-UE-REF-EXIST_ELEC|C-ELEC-UNGD-E") == "C-ELEC-UNGD-E"
    assert pdf_layers.short_name("C-ROAD-CNTR") == "C-ROAD-CNTR"


def test_doc_sin_ocg_devuelve_vacio():
    doc = fitz.open()
    doc.new_page()
    assert pdf_layers.page_layers(doc, 0) == []
    assert pdf_layers.hidden_layers(doc) == set()
    pdf_layers.set_hidden(doc, {"nada"})   # no debe fallar


@needs_pdf
def test_page_layers_lista_y_ordena():
    doc = fitz.open(str(PDF))
    configs = list(doc.layer_ui_configs() or [])
    layers = pdf_layers.page_layers(doc, PAGE)
    # Todas las OCG del doc (como Okular), no solo las con trazos en la hoja
    assert len(layers) == len(configs)
    assert len(layers) > 50
    names = [L["name"] for L in layers]
    assert any("C-ELEC-UNGD-E" in n for n in names)
    # Orden: con trazos primero (más → menos); path_count=0 al final
    with_paths = [L for L in layers if L["path_count"] > 0]
    without = [L for L in layers if L["path_count"] == 0]
    assert with_paths, "la hoja de prueba debe tener capas con trazos"
    assert [L["path_count"] for L in with_paths] == sorted(
        (L["path_count"] for L in with_paths), reverse=True)
    if without:
        assert layers.index(with_paths[-1]) < layers.index(without[0])
        shorts = [L["short"].upper() for L in without]
        assert shorts == sorted(shorts)
    assert all(L["on"] for L in layers)            # todo visible al abrir
    assert all(L["short"] == pdf_layers.short_name(L["name"]) for L in layers)


@needs_pdf
def test_set_hidden_afecta_render_y_drawings():
    doc = fitz.open(str(PDF))
    page = doc[PAGE]
    layers = pdf_layers.page_layers(doc, PAGE)
    logo = [L["name"] for L in layers if "G-LOGO" in L["name"]]
    assert logo, "la hoja debe tener el logo (capa ruidosa) para la prueba"
    n_all = len(page.get_drawings())
    n_logo = sum(L["path_count"] for L in layers if L["name"] in logo)

    pdf_layers.set_hidden(doc, logo)
    assert pdf_layers.hidden_layers(doc) == set(logo)
    after = page.get_drawings()
    # Desaparecen al menos los trazos de esa capa (pueden irse más: `layer` es la
    # OCG más interna y un trazo anidado en varias se apaga con cualquiera).
    assert len(after) <= n_all - n_logo
    assert not any(d.get("layer") in logo for d in after)
    # page_layers sigue listando la capa oculta (la enciende un instante) y con on=False
    again = pdf_layers.page_layers(doc, PAGE)
    hidden_rows = [L for L in again if L["name"] in logo]
    assert hidden_rows and all(not L["on"] for L in hidden_rows)
    assert pdf_layers.hidden_layers(doc) == set(logo)   # restauró el estado previo

    pdf_layers.set_hidden(doc, ())
    assert pdf_layers.hidden_layers(doc) == set()
    assert len(page.get_drawings()) == n_all


@needs_pdf
def test_recognize_page_respeta_hidden_ocgs():
    base = rec.recognize_page(PDF, page_index=PAGE, zoom=1.0)
    elec = [s["ocg"] for s in base.ocg_summary if "C-ELEC-UNGD" in s["ocg"]]
    assert elec and base.drawable
    res = rec.recognize_page(PDF, page_index=PAGE, zoom=1.0, hidden_ocgs=elec)
    assert res.hidden_ocgs == sorted(elec)
    assert not res.drawable
    assert not any(s["ocg"] in elec for s in res.ocg_summary)
