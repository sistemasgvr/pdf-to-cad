"""Capas virtuales de los ejes de una red en IMAGEN (`hoja/imagen_ejes`, plan 2026-11-18, Tarea 4).

`pdf_styles.drawings` suma, en hojas SIN capas con imágenes gráficas (mapas «QS SD» de Phoenix), los
ejes de cada color de la imagen como trazos virtuales en capas `PDF_STYLE:["img",…]`. En cualquier
otra hoja no cambia nada.
"""

import os
import zlib

import cv2
import fitz
import numpy as np
import pytest

from hoja import composite, imagen_ejes as IE, imagen_paleta as IP, imagen_solo as IS, pdf_styles

SD_SOUTH = r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/QS SD_Indian School_South.pdf"
_B = r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/"
_D = r"C:/Users/bernu/OneDrive/Documentos/docs prueba/"
AZUL = (0, 77, 168)                  # #004DA8
TRAMA = (128, 166, 212)              # #80A6D4
ESC = 2.0                            # px de la imagen sintética por pt


# ── ayudantes ────────────────────────────────────────────────────────────────────────────────

_n_img = [0]


def _indexada(doc, page, rect, idx, paleta):
    """Inserta en `rect` una imagen INDEXADA (índices `idx` uint8, `paleta` lista de rgb)."""
    alto, ancho = idx.shape
    # marcador DISTINTO cada vez: PyMuPDF reusa el xref de una imagen idéntica ya insertada
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


def _pdf_tiras(tmp_path, dibujar, ancho_pt=300, alto_pt=300, tiras=3, rotar=0, negros=(), nombre="tiras.pdf"):
    """Hoja con la imagen de la red partida en `tiras` imágenes indexadas horizontales (como las
    tiras de Phoenix SD; ninguna cubre ≥ 60 % de la hoja: no es un escaneo). `dibujar(idx)` pinta
    los índices (1 = AZUL, 2 = TRAMA) en px de la imagen entera (`ESC` px/pt). `negros` = líneas
    vectoriales ((x0, y0), (x1, y1)) en pt encima."""
    W, H = int(ancho_pt * ESC), int(alto_pt * ESC)
    idx = np.zeros((H, W), np.uint8)
    dibujar(idx)
    doc = fitz.open()
    page = doc.new_page(width=ancho_pt, height=alto_pt)
    paso = H // tiras
    for k in range(tiras):
        y0, y1 = k * paso, (H if k == tiras - 1 else (k + 1) * paso)
        _indexada(doc, page, fitz.Rect(0, y0 / ESC, ancho_pt, y1 / ESC), idx[y0:y1], [(255, 255, 255), AZUL, TRAMA])
    for a, b in negros:
        page.draw_line(a, b, color=(0, 0, 0), width=0.6)
    page.insert_text((20, 290), "Sintetico 18\" HDPE", fontsize=6)
    if rotar:
        page.set_rotation(rotar)
    ruta = tmp_path / nombre
    doc.save(ruta)
    return fitz.open(ruta)


def _red(idx):
    """Una tubería horizontal a y = 150 pt (8 px = 4 pt de grosor) y un cuadro relleno de 20 px."""
    cv2.rectangle(idx, (60, 296), (540, 303), 1, -1)
    cv2.rectangle(idx, (440, 440), (459, 459), 1, -1)


def _red_y_trama(idx):
    _red(idx)
    raya = np.zeros_like(idx)
    for k in range(-200, 260, 12):
        cv2.line(raya, (80 + k, 560), (280 + k, 380), 1, 2)
    raya[:382], raya[558:], raya[:, :82], raya[:, 278:] = 0, 0, 0, 0
    idx[raya.astype(bool)] = 2


def _ejes(paths, tipo="line"):
    return [p for p in paths if IE.tipo_imagen(p.get("layer") or "") == tipo]


_SD = {}


def _sd_south():
    if not os.path.exists(SD_SOUTH):
        pytest.skip("falta el PDF de Phoenix SD South")
    if "south" not in _SD:
        _SD["south"] = fitz.open(SD_SOUTH)
    return _SD["south"]


def _sd_h4_capas():
    page = _sd_south()[3]
    return page, IE.capas(page)


# ── nombres y etiquetas ──────────────────────────────────────────────────────────────────────

def test_nombres_y_ayudantes():
    linea = IE.nombre("line", (0, 77, 168))
    sim = IE.nombre("sym", (0, 77, 168), "cuadro 4×4")
    rel = IE.nombre("fill", (128, 166, 212))
    assert linea == 'PDF_STYLE:["img","line",[0,77,168]]'
    assert rel == 'PDF_STYLE:["img","fill",[128,166,212]]'
    assert sim.startswith('PDF_STYLE:["img","sym",[0,77,168],') and IE.tipo_imagen(sim) == "sym"
    assert [IE.es_imagen(n) for n in (linea, sim, rel)] == [True] * 3
    assert [IE.tipo_imagen(n) for n in (linea, rel)] == ["line", "fill"]
    assert IE.rgb_de(sim) == (0, 77, 168)
    otro = pdf_styles.PREFIX + '["s",[0.0,0.0,1.0],0.5,"[] 0",null,1.0,null]'
    for n in (otro, "C-STRM-UGND", "", None):
        assert not IE.es_imagen(n) and IE.tipo_imagen(n) is None and IE.rgb_de(n) is None
    assert pdf_styles.style_label(linea) == "Azul #004DA8 · imagen"
    assert pdf_styles.style_label(sim) == "Símbolo #004DA8 (cuadro 4×4 pt) · imagen"
    assert pdf_styles.style_label(rel) == "Relleno #80A6D4 · imagen"
    assert pdf_styles.is_symbol(sim) and not pdf_styles.is_symbol(linea) and not pdf_styles.is_symbol(rel)
    assert pdf_styles.style_width(linea) is None and pdf_styles._partes(linea) is None


# ── sintéticas ───────────────────────────────────────────────────────────────────────────────

def test_capas_sintetico_nombres_y_etiquetas(tmp_path):
    page = _pdf_tiras(tmp_path, _red, negros=[((150, 100), (150, 200))])[0]
    trazos = IE.capas(page)
    names = {p["layer"] for p in trazos}
    assert 'PDF_STYLE:["img","line",[0,77,168]]' in names
    assert pdf_styles.style_label('PDF_STYLE:["img","line",[0,77,168]]') == "Azul #004DA8 · imagen"
    sim = next(n for n in names if IE.tipo_imagen(n) == "sym")
    assert pdf_styles.is_symbol(sim) and IE.rgb_de(sim) == AZUL
    # el eje: forma de get_drawings, a lo largo del centro del trazo, de punta a punta, sin cortarse
    (eje,) = _ejes(trazos)
    assert eje["type"] == "s" and eje["seqno"] == -2 and eje["level"] == 0 and eje["imagen"] is True
    assert eje["dashes"] == "[] 0" and eje["fill"] is None
    assert eje["color"] == pytest.approx((0, 77 / 255, 168 / 255))
    assert eje["width"] == pytest.approx(4.0, abs=0.6)
    assert all(it[0] == "l" for it in eje["items"])
    pts = [it[1] for it in eje["items"]] + [eje["items"][-1][2]]
    assert all(abs(p.y - 150.0) <= 0.3 for p in pts)
    xs = sorted(p.x for p in pts)
    assert abs(xs[0] - 30.0) <= 0.75 and abs(xs[-1] - 270.5) <= 0.75
    ys = [p.y for p in pts]
    assert tuple(eje["rect"]) == pytest.approx((xs[0], min(ys), xs[-1], max(ys)))
    # el símbolo: círculo virtual en su centro, marcado `symbol`
    (s,) = _ejes(trazos, "sym")
    assert s["symbol"] is True and s["seqno"] == -2 and s["imagen"] is True
    assert fitz.Rect(s["rect"]).contains(fitz.Point(225, 225))


def test_relleno_sintetico(tmp_path):
    page = _pdf_tiras(tmp_path, _red_y_trama)[0]
    trazos = IE.capas(page)
    fill = IE.nombre("fill", TRAMA)
    assert {p["layer"] for p in trazos} >= {IE.nombre("line", AZUL), fill}
    assert not any(IE.rgb_de(p["layer"]) == TRAMA and IE.tipo_imagen(p["layer"]) != "fill" for p in trazos)
    rel = [p for p in trazos if p["layer"] == fill]
    assert rel and all(p["imagen_relleno"] is True and p["type"] == "s" and len(p["items"]) == 4 for p in rel)
    caja = fitz.Rect(rel[0]["rect"])
    for p in rel[1:]:
        caja |= fitz.Rect(p["rect"])
    assert fitz.Rect(38, 188, 142, 282).contains(caja)


def test_hoja_girada_sintetica_eje_en_coordenadas_de_get_drawings(tmp_path):
    # Hoja girada 90°: una línea vectorial negra va EXACTAMENTE sobre la tubería de la imagen; el eje
    # debe caer sobre ella en las coordenadas de get_drawings (sin girar).
    page = _pdf_tiras(tmp_path, _red, negros=[((30, 150), (270, 150))], rotar=90)[0]
    assert page.rotation == 90
    (negra,) = [it for d in page.get_drawings() for it in d["items"]]
    (eje,) = _ejes(pdf_styles.drawings(page))
    for it in eje["items"]:
        for p in it[1:]:
            assert abs(p.y - negra[1].y) <= 0.3 and negra[1].x - 1 <= p.x <= negra[2].x + 1


def test_sin_imagenes_o_escaneo_o_con_capas_no_hay_capas(tmp_path, monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("no debe decodificar ninguna imagen")
    monkeypatch.setattr(IS, "pintar", prohibido)
    # sin imágenes
    doc = fitz.open()
    pg = doc.new_page(width=300, height=300)
    pg.draw_line((20, 20), (280, 280), color=(0, 0, 1), width=2)
    assert IE.capas(pg) == []
    # escaneo: UNA imagen a toda la hoja
    doc = fitz.open()
    pg = doc.new_page(width=300, height=300)
    idx = np.zeros((600, 600), np.uint8)
    _red(idx)
    _indexada(doc, pg, pg.rect, idx, [(255, 255, 255), AZUL])
    assert IE.capas(pg) == []
    # imagen chica (logo, leyenda): menos de la cobertura mínima
    doc = fitz.open()
    pg = doc.new_page(width=300, height=300)
    _indexada(doc, pg, fitz.Rect(250, 250, 290, 290), idx[:80, :80], [(255, 255, 255), AZUL])
    assert IE.capas(pg) == []
    # con capas (OCG)
    doc = _pdf_tiras(tmp_path, _red)
    doc.add_ocg("C-STRM-UGND")
    assert IE.capas(doc[0]) == []


def test_drawings_suma_las_capas_al_final_y_memoriza(tmp_path, monkeypatch):
    doc = _pdf_tiras(tmp_path, _red)
    page = doc[0]
    nativos = [p for p in pdf_styles.drawings(page) if not IE.es_imagen(p.get("layer") or "")]
    todos = pdf_styles.drawings(page)
    assert todos[:len(nativos)] == nativos and len(todos) > len(nativos)
    assert all(IE.es_imagen(p["layer"]) for p in todos[len(nativos):])
    # dentro de lectura_unica las dos formas de la lectura usan UNA extracción; y fuera, la del documento
    llamadas = []
    original = IE._capas_de

    def contar(*a, **k):
        llamadas.append(1)
        return original(*a, **k)
    monkeypatch.setattr(IE, "_capas_de", contar)
    doc2 = fitz.open(doc.name)
    with pdf_styles.lectura_unica(doc2):
        pdf_styles.drawings(doc2[0])
        pdf_styles.drawings(doc2[0], extended=True)
    pdf_styles.drawings(doc2[0])
    assert len(llamadas) == 1


def test_teselas_dan_lo_mismo_que_la_hoja_entera(tmp_path, monkeypatch):
    # Con teselas chicas (la tubería cruza tres costuras) sale lo mismo que de una vez: el eje
    # cosido en UNA línea, el mismo símbolo y la trama como relleno.
    entera = IE.capas(_pdf_tiras(tmp_path, _red_y_trama, nombre="entera.pdf")[0])
    monkeypatch.setattr(IE, "LADO_PX", 256)
    monkeypatch.setattr(IE, "SOLAPE_PX", 96)
    partida = IE.capas(_pdf_tiras(tmp_path, _red_y_trama, nombre="partida.pdf")[0])
    assert {p["layer"] for p in partida} == {p["layer"] for p in entera}
    (a,), (b,) = _ejes(entera), _ejes(partida)
    pa = [it[1] for it in a["items"]] + [a["items"][-1][2]]
    pb = [it[1] for it in b["items"]] + [b["items"][-1][2]]
    assert all(abs(p.y - 150.0) <= 0.3 for p in pb)
    assert min(p.x for p in pb) == pytest.approx(min(p.x for p in pa), abs=0.3)
    assert max(p.x for p in pb) == pytest.approx(max(p.x for p in pa), abs=0.3)
    assert b["width"] == pytest.approx(a["width"], abs=0.3)
    assert [s["rect"] for s in _ejes(partida, "sym")] == [s["rect"] for s in _ejes(entera, "sym")]


NEGRO = (0, 0, 0)


def _red_y_negro(idx):
    _red(idx)
    cv2.rectangle(idx, (60, 96), (540, 103), 3, -1)          # una línea NEGRA en la imagen, a y = 50 pt


def _pdf_mixto(tmp_path, n_vectores, nombre):
    """Tiras con azul y negro en la imagen y `n_vectores` trazos vectoriales negros encima."""
    W, H = 600, 600
    idx = np.zeros((H, W), np.uint8)
    _red_y_negro(idx)
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    for k in range(3):
        _indexada(doc, page, fitz.Rect(0, k * 100, 300, (k + 1) * 100), idx[k * 200:(k + 1) * 200],
                  [(255, 255, 255), AZUL, TRAMA, NEGRO])
    for i in range(n_vectores):                               # mapa base vectorial (lotes)
        x = 10 + (i % 50) * 5.6
        y = 200 + (i // 50) * 9
        page.draw_line((x, y), (x + 3, y), color=(0, 0, 0), width=0.3)
    ruta = tmp_path / nombre
    doc.save(ruta)
    return fitz.open(ruta)


def test_negro_de_la_imagen_solo_sin_mapa_base_vectorial(tmp_path):
    # Con ≥ 500 trazos vectoriales negros/grises el mapa base es vector: el negro de la imagen no se
    # procesa (era ~80 % del tiempo en Phoenix SD). Con pocos, sí.
    mucho = _pdf_mixto(tmp_path, IE.ACROMATICO_VECTORES_MIN, "mucho.pdf")[0]
    assert len(mucho.get_drawings()) >= IE.ACROMATICO_VECTORES_MIN
    capas = {p["layer"] for p in pdf_styles.drawings(mucho) if IE.es_imagen(p.get("layer") or "")}
    assert IE.nombre("line", AZUL) in capas and not any(IE.rgb_de(n) == NEGRO for n in capas)
    poco = _pdf_mixto(tmp_path, 20, "poco.pdf")[0]
    capas = {p["layer"] for p in pdf_styles.drawings(poco) if IE.es_imagen(p.get("layer") or "")}
    assert {IE.nombre("line", AZUL), IE.nombre("line", NEGRO)} <= capas


def test_simbolos_agrupados_por_forma():
    capa = IE.agrupar_formas([(8, 9, "cuadro 8×9")] * 3 + [(9, 9, "cuadro 9×9")] * 2
                             + [(6, 6, "círculo 6")] + [(14, 14, "cuadro 14×14")])
    assert capa["cuadro 9×9"] == capa["cuadro 8×9"] == "cuadro 8×9"       # la más frecuente encabeza
    assert capa["círculo 6"] == "círculo 6" and capa["cuadro 14×14"] == "cuadro 14×14"
    assert IE.agrupar_formas([(8, 9, "cuadro 8×9"), (6, 6, "círculo 6")]) ==         {"cuadro 8×9": "cuadro 8×9", "círculo 6": "círculo 6"}
    # empate de frecuencia: decide el nombre (determinista, no el orden de llegada)
    assert IE.agrupar_formas([(9, 9, "cuadro 9×9"), (8, 9, "cuadro 8×9")]) ==         IE.agrupar_formas([(8, 9, "cuadro 8×9"), (9, 9, "cuadro 9×9")])


def test_simbolos_raros_van_a_una_capa_varios():
    # Tarea 5: en Phoenix SD 17–19 de 23–28 capas de símbolo tenían 1–3 piezas (formas sueltas): van
    # juntas a «varios» de su color; las frecuentes conservan su capa.
    sim = [(8, 9, "cuadro 8×9")] * 6 + [(6, 6, "círculo 6")] * 4 + [(1, 1, "otro 1×1")] * 2 + [(5, 3, "otro 5×3")]
    capa = IE.formas_de_capa(sim)
    assert capa["cuadro 8×9"] == "cuadro 8×9" and capa["círculo 6"] == "círculo 6"
    assert capa["otro 1×1"] == capa["otro 5×3"] == IE.FORMA_VARIOS
    assert IE.etiqueta(IE.nombre("sym", AZUL, IE.FORMA_VARIOS)) == "Símbolo #004DA8 (varios) · imagen"


def _red_con_borde_claro(idx):
    """Tubería azul con su contorno de 1 px en el tinte claro (TRAMA = 50 % del azul con blanco, como el
    contorno de las bandas de Phoenix SD) y, aparte, un cuadro TRAMA suelto (para que sea un color propio)."""
    cv2.rectangle(idx, (60, 296), (540, 303), 1, -1)
    cv2.rectangle(idx, (59, 295), (541, 304), 2, 1)
    cv2.rectangle(idx, (100, 440), (139, 479), 2, -1)


def test_borde_claro_de_la_banda_no_es_linea_de_su_tinte(tmp_path):
    # Phoenix SD h.1: el contorno de la banda en #80A6D4 salía como 651 trazos finos de «línea #80A6D4»
    # pegados a la tubería. El tinte que la familia del azul reclama como su borde no es tinta propia.
    cs = IE.capas(_pdf_tiras(tmp_path, _red_con_borde_claro)[0])
    assert not [p for p in _ejes(cs) if IE.rgb_de(p["layer"]) == TRAMA]
    assert _ejes(cs) and all(IE.rgb_de(p["layer"]) == AZUL for p in _ejes(cs))


def test_determinista(tmp_path):
    a = IE.capas(_pdf_tiras(tmp_path, _red_y_trama, nombre="a.pdf")[0])
    b = IE.capas(_pdf_tiras(tmp_path, _red_y_trama, nombre="b.pdf")[0])
    assert [(p["layer"], [tuple(map(tuple, it[1:])) for it in p["items"]]) for p in a] == \
           [(p["layer"], [tuple(map(tuple, it[1:])) for it in p["items"]]) for p in b]


# ── hojas reales ─────────────────────────────────────────────────────────────────────────────

def test_hoja_girada_eje_sobre_su_tinta():
    page, trazos = _sd_h4_capas()                                # /Rotate 90
    assert page.rotation == 90
    # las dos capas de línea del azul (bandas y la «fina», `imagen_grosores`): toda la tinta del color
    ejes = [p for p in trazos if p["layer"] in (IE.nombre("line", AZUL), IE.nombre("line", AZUL, IE.FINO))]
    assert len(ejes) > 50
    k = 4.0
    pix = page.get_pixmap(matrix=fitz.Matrix(k, k), alpha=False)          # la VISTA girada
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3)
    # la tinta del color: el azul y su antialias (el contorno de 1 px de la tubería «en caja» va en
    # tonos intermedios y su interior trae cajitas blancas)
    azul = (np.abs(img.astype(int) - AZUL).max(-1) <= 2) | IP.familia(img, IP.ColorImagen(AZUL, 1, True, ()))
    # la banda «a cuadros» entera es tinta, con sus cajitas blancas: el eje de las bandas pegadas va de bloque a
    # bloque (`imagen_bandas`) y el medio de cada tramo cae en una cajita (2026-11-19)
    azul = cv2.morphologyEx(azul.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)) > 0
    dist = cv2.distanceTransform((~azul).astype(np.uint8), cv2.DIST_L2, 5)
    m = page.rotation_matrix * fitz.Matrix(k, k)                          # get_drawings → vista
    ds = []
    for e in ejes:
        for it in e["items"]:
            q = ((it[1] + it[2]) / 2) * m
            ds.append(dist[min(int(q.y), pix.h - 1), min(int(q.x), pix.w - 1)])
    ds = np.array(ds)
    # medido 2026-11-18: 90 % a ≤ 1 px, 95 % a ≤ 3 px, 99.4 % a ≤ 5 px (lo demás: un vector negro
    # encima en el render normal). Con el giro mal puesto, casi ninguno caería sobre la tinta.
    assert (ds <= 1).mean() >= 0.85 and (ds <= 3).mean() >= 0.93 and (ds <= 6).mean() >= 0.99


def _hojas_foto():
    hojas = []
    for ruta, numeros in ((_B + "QS Water_Indian School_South.pdf", (3,)),
                          (_B + "QS Sewer_Indian School_South.pdf", (3,)),
                          (_B + "APUNTES ING/Southwest Gas Combined 811 Records (1) 36.pdf", (0,)),
                          (_B + "APUNTES ING/Southwest Gas Combined 811 Records (1) 37.pdf", (0,)),
                          (_D + "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf", (3,)),
                          (_D + "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf", (25,))):
        if os.path.exists(ruta):
            doc = fitz.open(ruta)
            hojas += [doc[n] for n in numeros if n < len(doc)]
    if not hojas:
        pytest.skip("faltan los PDF de prueba")
    return hojas


def test_sin_imagenes_igual_que_antes(monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("no debe decodificar ninguna imagen")
    monkeypatch.setattr(IS, "pintar", prohibido)
    for page in _hojas_foto():
        assert IE.capas(page) == []
        antes = page.get_drawings()
        paths = pdf_styles.drawings(page)
        assert not any(IE.es_imagen(p.get("layer") or "") for p in paths)
        # lo nativo, igual que get_drawings (con su capa por estilo si no tiene OCG)
        nativos = [p for p in paths if p.get("seqno", 0) >= 0]
        assert [{k: v for k, v in p.items() if k != "layer"} for p in nativos] == \
               [{k: v for k, v in p.items() if k != "layer"} for p in antes]


def test_compositor_no_ve_los_ejes():
    page = _sd_south()[3]
    assert not any(IE.es_imagen(p.get("layer") or "") for p in composite.page_drawings(page))


def test_rotulos_vectoriales_junto_al_eje():
    # hoja 4 de South, zona de PIONEER PREPARATORY: el rótulo «18" HDPE» (vector negro) queda a ≤ 3
    # letras de un eje azul, en las mismas coordenadas (las de get_drawings).
    page, trazos = _sd_h4_capas()
    zona = page.search_for("PIONEER")
    rotulos = page.search_for('18" HDPE')
    assert zona and rotulos
    # `search_for` da las coordenadas de la hoja SIN girar (las de get_drawings, PyMuPDF 1.28)
    cerca = [c for c in rotulos if min(abs(c.x0 - z.x0) + abs(c.y0 - z.y0) for z in zona) < 400]
    assert cerca
    segs = [(it[1], it[2]) for p in trazos if p["layer"] == IE.nombre("line", AZUL) for it in p["items"]]
    for c in cerca:
        letra = min(c.width, c.height)
        d = min(_dist_seg(c, a, b) for a, b in segs)
        assert d <= 3 * letra, (c, d, letra)


def _dist_seg(caja, a, b):
    """Distancia del rectángulo `caja` al segmento a–b (0 si se cortan)."""
    p = (caja.tl + caja.br) / 2
    ab = b - a
    n = ab.x * ab.x + ab.y * ab.y
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p - a).x * ab.x + (p - a).y * ab.y) / n))
    q = a + ab * t
    dx = max(caja.x0 - q.x, 0, q.x - caja.x1)
    dy = max(caja.y0 - q.y, 0, q.y - caja.y1)
    return float(np.hypot(dx, dy))
