"""La hoja se lee UNA vez por reconocimiento (`pdf_styles.lectura_unica`, 2026-10-20) y el
resultado es el mismo que leyéndola cada vez."""
import contextlib
from pathlib import Path

import fitz
import pytest

from hoja import pdf_styles
from reconocimiento import recognition_trabajo as RT

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


def _hoja_con_capas_y_recorte():
    doc = fitz.open()
    oc = doc.add_ocg("C-ELEC-UNGD-E")
    page = doc.new_page()
    page.draw_line((30, 40), (250, 40), oc=oc)
    page.draw_line((30, 60), (250, 60), dashes="[4 2] 0", oc=oc)
    page.draw_line((30, 80), (250, 80))
    # un recorte (nivel > 0) como el de una vista o una pieza de la hoja compuesta
    src = fitz.open()
    sp = src.new_page(width=200, height=200)
    sp.draw_line((10, 10), (190, 190), oc=src.add_ocg("C-STRM-UNGD-E"))
    page.show_pdf_page(fitz.Rect(300, 300, 500, 500), src, 0, clip=fitz.Rect(0, 0, 120, 120))
    return doc


def _hoja_sin_capas():
    doc = fitz.open()
    page = doc.new_page()
    page.draw_line((40, 40), (200, 40), width=.73)
    page.draw_line((40, 80), (200, 80), width=.36, dashes="[4 2] 0")
    page.draw_rect((40, 120, 70, 140), color=None, fill=(0, 0, 0))
    return doc


def _contar_lecturas(monkeypatch):
    n = {"k": 0}
    original = fitz.Page.get_drawings

    def contar(self, *a, **k):
        n["k"] += 1
        return original(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_drawings", contar)
    return n


@pytest.mark.parametrize("armar", [_hoja_con_capas_y_recorte, _hoja_sin_capas])
def test_misma_lista_que_leyendo_cada_vez(armar, monkeypatch):
    doc = armar()
    page = doc[0]
    sin = {ext: pdf_styles.drawings(page, extended=ext) for ext in (False, True)}
    n = _contar_lecturas(monkeypatch)
    with pdf_styles.lectura_unica(doc):
        for _ in range(3):
            for ext in (False, True):
                assert pdf_styles.drawings(page, extended=ext) == sin[ext]
        with pdf_styles.lectura_unica(doc):              # anidado: el de afuera manda
            assert pdf_styles.drawings(page) == sin[False]
    assert n["k"] == 1                                    # una sola lectura nativa (la extendida)
    assert "_pdfcad_lectura_unica" not in doc.__dict__    # se suelta al salir
    pdf_styles.drawings(page)
    assert n["k"] == 2                                    # fuera del bloque: lee como siempre


def test_otra_lectura_si_cambian_las_capas_visibles():
    doc = _hoja_con_capas_y_recorte()
    page = doc[0]
    with pdf_styles.lectura_unica(doc):
        todas = pdf_styles.drawings(page)
        num = next(c["number"] for c in doc.layer_ui_configs() if c["text"] == "C-ELEC-UNGD-E")
        doc.set_layer_ui_config(num, action=2)            # apagar
        sin_elec = pdf_styles.drawings(page)
        doc.set_layer_ui_config(num, action=0)
        assert pdf_styles.drawings(page) == todas
    assert len(sin_elec) < len(todas)


def _firma(res):
    return [(r.utility, [[list(map(float, p)) for p in pl.pts_pdf] for pl in r.drawable],
             [list(pl.kinds) for pl in r.drawable], [sorted((pl.fillets or {}).items()) for pl in r.drawable],
             sorted(map(str, r.warnings)), len(r.vaults_geo or [])) for r in res]


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_mismo_reconocimiento_con_menos_lecturas(monkeypatch):
    us = ("ELECTRICO", "DRENAJE", "TELECOM")
    n = _contar_lecturas(monkeypatch)
    nuevo = RT.reconocer_hoja(str(DU06), 12, zoom=3.5, utilities=us)
    lecturas = n["k"]
    n["k"] = 0
    monkeypatch.setattr(pdf_styles, "lectura_unica", lambda doc: contextlib.nullcontext())
    viejo = RT.reconocer_hoja(str(DU06), 12, zoom=3.5, utilities=us)
    assert _firma(nuevo) == _firma(viejo)
    assert lecturas == 1 and n["k"] == 1 + 2 * len(us)    # antes: las letras + 2 por utilidad
