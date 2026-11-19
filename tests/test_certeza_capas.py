"""Certeza por capa de LÍNEA de imagen (`hoja/certeza_capas`, plan 2026-11-18 «Ejes de la red en imagen», Tarea 6).

Por cada capa de línea de imagen se decide de qué utilidad es y si es SEGURO aplicarla sola (nombre del PDF, leyenda
o texto dicen UNA utilidad; la capa es el único color de la hoja o los rótulos de diámetro la señalan; nada en
contra) o si hay que preguntarle al usuario."""
import os
import tempfile
import zlib

import cv2
import fitz
import numpy as np
import pytest

from hoja import estilos_sugeridos as ES, imagen_ejes as IE, interpretacion_guardada as IG, pdf_styles
from hoja.certeza_capas import CapaCerteza
from hoja import certeza_capas as CC

SD_SOUTH = r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/QS SD_Indian School_South.pdf"
AZUL = (0, 77, 168)
ROJO = (200, 30, 30)
ESC = 2.0
_TMP = tempfile.mkdtemp(prefix="pdfcad_certeza_")
_n_img = [0]
_RES = {}


# ── ayudantes ────────────────────────────────────────────────────────────────────────────────

def _indexada(doc, page, rect, idx, paleta):
    alto, ancho = idx.shape
    _n_img[0] += 1
    marca = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, _n_img[0], 1), False)
    xref = page.insert_image(rect, stream=marca.tobytes("png"), keep_proportion=False)
    tabla = bytes(v for c in paleta for v in c).hex()
    datos = zlib.compress(np.ascontiguousarray(idx, np.uint8).tobytes())
    cab = ("<</Type/XObject/Subtype/Image/Width %d/Height %d/BitsPerComponent 8"
           "/ColorSpace[/Indexed/DeviceRGB %d <%s>]/Filter/FlateDecode" % (ancho, alto, len(paleta) - 1, tabla))
    doc.update_object(xref, cab + ">>")
    doc.update_stream(xref, datos, compress=False)
    doc.update_object(xref, cab + "/Length %d>>" % len(datos))


def _pdf_tiras(nombre, dibujar, paleta, textos=(), lado=300, tiras=3):
    """Hoja de `lado` pt con la red en `tiras` imágenes indexadas (índice 0 = blanco)."""
    W = H = int(lado * ESC)
    idx = np.zeros((H, W), np.uint8)
    dibujar(idx)
    doc = fitz.open()
    page = doc.new_page(width=lado, height=lado)
    paso = H // tiras
    for k in range(tiras):
        y0, y1 = k * paso, (H if k == tiras - 1 else (k + 1) * paso)
        _indexada(doc, page, fitz.Rect(0, y0 / ESC, lado, y1 / ESC), idx[y0:y1], [(255, 255, 255)] + list(paleta))
    for pos, txt in textos:
        page.insert_text(pos, txt, fontsize=6)
    ruta = os.path.join(_TMP, nombre)
    doc.save(ruta)
    return fitz.open(ruta)


def _horizontal(idx):
    cv2.rectangle(idx, (60, 296), (540, 303), 1, -1)          # y = 150 pt, 4 pt de grosor


def _pdf_dos_colores():
    def dib(idx):
        _horizontal(idx)
        cv2.rectangle(idx, (446, 60), (453, 540), 2, -1)       # vertical roja a x = 225 pt
    return _pdf_tiras("dos_colores.pdf", dib, [AZUL, ROJO])


def _pdf_sd_con_rotulo_water():
    return _pdf_tiras("sd_water.pdf", _horizontal, [AZUL], textos=[((100, 146), '8" WATER')])


def _sd_south():
    if not os.path.exists(SD_SOUTH):
        pytest.skip("falta el PDF de Phoenix SD South")
    if "doc" not in _RES:
        _RES["doc"] = fitz.open(SD_SOUTH)
    return _RES["doc"]


def _sugerir(page, nombres=()):
    clave = (page.parent.name, page.number, tuple(nombres))
    if clave not in _RES:
        with pdf_styles.lectura_unica(page.parent):
            _RES[clave] = ES.sugerir(page, nombres=nombres)
    return _RES[clave]


_NOMBRES_SD = ["QS SD_Indian School_South.pdf"]


# ── Phoenix SD ───────────────────────────────────────────────────────────────────────────────

def test_phoenix_sd_es_drenaje_seguro():
    caps = _sugerir(_sd_south()[3], nombres=_NOMBRES_SD).capas
    c, = [c for c in caps if c.capa.endswith("[0,77,168]]")]
    assert c.utilidad == "DRENAJE" and c.seguro and "nombre" in c.a_favor and "rotulos" in c.a_favor
    assert c.simbolos                                    # sumideros en las puntas
    assert all(IE.tipo_imagen(s) == "sym" and IE.rgb_de(s) == AZUL for s in c.simbolos)


def test_relleno_no_es_capa_de_linea():
    caps = _sugerir(_sd_south()[3], nombres=_NOMBRES_SD).capas
    assert caps and not any(c.capa.endswith("[128,166,212]]") for c in caps)
    assert all(IE.tipo_imagen(c.capa) == "line" for c in caps)


# ── sintéticas ───────────────────────────────────────────────────────────────────────────────

def test_dos_colores_es_dudoso():
    caps = ES.sugerir(_pdf_dos_colores()[0], nombres=["plano.pdf"]).capas
    assert caps and not any(c.seguro for c in caps)
    assert all("varios_colores" in c.en_contra or "sin_evidencia" in c.en_contra for c in caps)


def test_un_color_y_nombre_es_seguro():
    c, = ES.sugerir(_pdf_tiras("QS SD_solo.pdf", _horizontal, [AZUL])[0], nombres=["QS SD_solo.pdf"]).capas
    assert c.seguro and c.utilidad == "DRENAJE" and c.a_favor == ["nombre"] and not c.en_contra


def test_rotulo_de_otra_utilidad_contradice():
    c, = ES.sugerir(_pdf_sd_con_rotulo_water()[0], nombres=["QS SD_x.pdf"]).capas
    assert not c.seguro and "contradice:AGUA" in c.en_contra


def test_interpretacion_guardada_roundtrip_con_capas():
    s = ES.Sugerencia(capas=[CapaCerteza("x", "DRENAJE", True, ["nombre"], [], [])])
    assert IG.decodificar(IG.codificar(s)) == s


# ── reglas, con trazos armados a mano ────────────────────────────────────────────────────────

def _linea(rgb, pts, fino=False, w=2.0):
    P = fitz.Point
    capa = IE.nombre("line", rgb, IE.FINO if fino else None)
    return {"type": "s", "layer": capa, "color": tuple(v / 255 for v in rgb), "width": w,
            "items": [("l", P(a), P(b)) for a, b in zip(pts, pts[1:])], "imagen": True}


def _vector(color, pts):
    P = fitz.Point
    d = {"type": "s", "color": color, "width": 0.5, "dashes": "[] 0", "fill": None,
         "items": [("l", P(a), P(b)) for a, b in zip(pts, pts[1:])]}
    d["layer"] = pdf_styles.style_name(d)
    return d


def test_fino_cuenta_como_el_mismo_color_pero_no_es_seguro_sin_sus_rotulos():
    paths = [_linea(AZUL, [(0, 0), (100, 0)]), _linea(AZUL, [(0, 50), (100, 50)], fino=True, w=0.5)]
    caps = {c.capa: c for c in CC.evaluar(paths, [], None, ["QS SD_a.pdf"])}
    grueso, fino = caps[IE.nombre("line", AZUL)], caps[IE.nombre("line", AZUL, IE.FINO)]
    assert grueso.seguro and "varios_colores" not in grueso.en_contra
    assert not fino.seguro and fino.utilidad == "DRENAJE" and "fino" in fino.en_contra


def test_otro_color_vectorial_quita_la_certeza_y_el_negro_no():
    base = [_linea(AZUL, [(0, 0), (100, 0)]), _vector((0, 0, 0), [(0, 10), (100, 10)]),
            _vector((0.5, 0.5, 0.5), [(0, 20), (100, 20)])]
    c, = CC.evaluar(base, [], None, ["QS SD_a.pdf"])
    assert c.seguro
    c, = CC.evaluar(base + [_vector((0.0, 0.7, 0.0), [(0, 30), (100, 30)])], [], None, ["QS SD_a.pdf"])
    assert not c.seguro and "varios_colores" in c.en_contra


def test_negro_de_imagen_nunca_seguro_solo_por_el_nombre():
    c, = CC.evaluar([_linea((0, 0, 0), [(0, 0), (100, 0)])], [], None, ["QS SD_a.pdf"])
    assert not c.seguro and c.utilidad == "DRENAJE" and "acromatico" in c.en_contra


def test_nombre_y_texto_que_no_coinciden_contradicen():
    c, = CC.evaluar([_linea(AZUL, [(0, 0), (100, 0)])], [], "AGUA", ["QS SD_a.pdf"])
    assert not c.seguro and "contradice:AGUA" in c.en_contra


def test_hoja_vectorial_sin_capas_de_imagen_sin_cambios():
    doc = fitz.open()
    pg = doc.new_page(width=300, height=300)
    pg.draw_line((10, 10), (200, 10), color=(0, 0, 1), width=0.5)
    s = ES.sugerir(pg)
    assert s.capas == [] and s.motivo == ES.SIN_ROTULOS
