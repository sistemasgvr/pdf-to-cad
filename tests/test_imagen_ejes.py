"""Ejes de una red que viene como IMAGEN dentro de un PDF vectorial (mapas «QS SD» de Phoenix).

Archivo compartido por las tareas del plan `2026-11-18-ejes-de-imagen`: aquí van los ayudantes
(`_pdf_sintetico`, `_sd_south`, …) y las pruebas de cada módulo.
"""

import math
import os

import cv2
import fitz
import numpy as np
import pytest

from hoja import imagen_paleta as IP
from hoja import imagen_solo as IS

SD_SOUTH = r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/QS SD_Indian School_South.pdf"
IS_ESCALA_SINT = 2.0                 # px de la imagen sintética por pt de la hoja
AZUL = (0, 77, 168)                  # #004DA8, el de la red de Phoenix SD


# ── ayudantes ────────────────────────────────────────────────────────────────────────────────

def _png(ancho_px, alto_px, trazos):
    """PNG RGB blanco con trazos ((x0, y0), (x1, y1), grosor) en px de la imagen, en AZUL."""
    im = np.full((alto_px, ancho_px, 3), 255, np.uint8)
    bgr = AZUL[::-1]
    for (a, b, g) in trazos:
        cv2.line(im, tuple(int(v) for v in a), tuple(int(v) for v in b), bgr, int(g))
    ok, png = cv2.imencode(".png", im)
    assert ok
    return png.tobytes()


def _pdf_sintetico(tmp_path, trazos_azules=(), vectores_negros=(), ancho_pt=300, alto_pt=300,
                   rotar=0, nombre="sint.pdf"):
    """PDF de una hoja con una imagen PNG a toda la hoja (`IS_ESCALA_SINT` px/pt) y vectores negros
    encima. Trazos y vectores en px de la imagen: ((x0, y0), (x1, y1), grosor)."""
    doc = fitz.open()
    page = doc.new_page(width=ancho_pt, height=alto_pt)
    png = _png(int(ancho_pt * IS_ESCALA_SINT), int(alto_pt * IS_ESCALA_SINT), trazos_azules)
    page.insert_image(fitz.Rect(0, 0, ancho_pt, alto_pt), stream=png)
    for (a, b, g) in vectores_negros:
        page.draw_line(fitz.Point(a) / IS_ESCALA_SINT, fitz.Point(b) / IS_ESCALA_SINT,
                       color=(0, 0, 0), width=g)
    if rotar:
        page.set_rotation(rotar)
    ruta = tmp_path / nombre
    doc.save(ruta)
    return fitz.open(ruta)


def _pdf_sin_imagenes(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_line((20, 20), (280, 280), color=(0, 0, 1), width=2)
    ruta = tmp_path / "sin_imagenes.pdf"
    doc.save(ruta)
    return fitz.open(ruta)


def _pdf_con_ocg_e_imagen(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    capa = doc.add_ocg("C-STRM-UGND")
    page.insert_image(fitz.Rect(0, 0, 300, 300), stream=_png(600, 600, [((100, 300), (500, 300), 6)]))
    page.draw_line((20, 20), (280, 20), color=(0, 0, 0), width=1, oc=capa)
    ruta = tmp_path / "ocg.pdf"
    doc.save(ruta)
    return fitz.open(ruta)


_SD = {}


def _sd_south():
    if not os.path.exists(SD_SOUTH):
        pytest.skip("falta el PDF de Phoenix SD South")
    if "south" not in _SD:
        _SD["south"] = fitz.open(SD_SOUTH)
    return _SD["south"]


def _es_azul(img, tol=2):
    return np.abs(img.astype(int) - AZUL).max(-1) <= tol


def _render(page, clip, escala):
    """Render normal de la hoja (vectores incluidos) con el mismo encuadre que `IS.pintar`."""
    mat = fitz.Matrix(escala, 0, 0, escala, -clip.x0 * escala, -clip.y0 * escala)
    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]


# ── Tarea 1: imagen_solo ─────────────────────────────────────────────────────────────────────

def test_vector_encima_no_corta_la_imagen(tmp_path):
    doc = _pdf_sintetico(tmp_path, trazos_azules=[((100, 300), (500, 300), 6)],
                         vectores_negros=[((300, 100), (300, 500), 0.5)])
    page = doc[0]
    escala = 4.0
    img = IS.pintar(page, page.rect, escala)
    assert img.shape == (1200, 1200, 3) and img.dtype == np.uint8
    fila = round(300 / IS_ESCALA_SINT * escala)
    x0 = round(100 / IS_ESCALA_SINT * escala) + 4
    x1 = round(500 / IS_ESCALA_SINT * escala) - 4
    assert _es_azul(img[fila, x0:x1]).all()
    # La prueba tiene sentido: en el render normal la línea negra corta el trazo en x = 600 px.
    normal = _render(page, page.rect, escala)
    assert not _es_azul(normal[fila, x0:x1]).all()
    assert (normal[fila, 595:606].max(-1) < 100).any()
    # Y lo que no es imagen sale blanco (ni rastro de la línea negra fuera del trazo).
    assert (img[100:200, 600] == 255).all()


def test_solo_imagenes_coincide_con_render_en_el_color(tmp_path):
    doc = _pdf_sintetico(tmp_path, trazos_azules=[((100, 300), (500, 300), 6),
                                                  ((120, 140), (480, 420), 4)],
                         vectores_negros=[((300, 520), (500, 560), 1)])
    page = doc[0]
    clip = fitz.Rect(40, 60, 260, 230)      # zona sin vectores encima
    img = IS.pintar(page, clip, 4.0)
    normal = _render(page, clip, 4.0)
    assert img.shape == normal.shape
    a, b = _es_azul(img), _es_azul(normal)
    assert a.sum() > 1000
    nucleo = np.ones((3, 3), np.uint8)
    # cada píxel azul de uno tiene un azul del otro a ≤1 px
    assert (a & ~cv2.dilate(b.astype(np.uint8), nucleo).astype(bool)).sum() == 0
    assert (b & ~cv2.dilate(a.astype(np.uint8), nucleo).astype(bool)).sum() == 0


def test_sin_imagenes_o_con_capas_no_hay_nada(tmp_path):
    assert IS.imagenes_utiles(_pdf_sin_imagenes(tmp_path)[0]) == []
    assert IS.imagenes_utiles(_pdf_con_ocg_e_imagen(tmp_path)[0]) == []
    assert IS.px_por_pt([]) == 0.0
    assert list(IS.teselas(_pdf_sin_imagenes(tmp_path)[0], 4.0)) == []


def test_imagenes_utiles_y_px_por_pt_sintetico(tmp_path):
    doc = _pdf_sintetico(tmp_path, trazos_azules=[((100, 300), (500, 300), 6)])
    imgs = IS.imagenes_utiles(doc[0])
    assert len(imgs) == 1
    assert IS.px_por_pt(imgs) == pytest.approx(IS_ESCALA_SINT)


def test_hoja_girada_pintar_en_coordenadas_de_get_drawings(tmp_path):
    # Hoja de 400 × 300 pt con /Rotate 90; una línea vectorial justo ENCIMA del trazo azul y otro
    # trazo azul sin nada encima. `get_drawings` y `get_image_info` dan coordenadas SIN girar.
    doc = _pdf_sintetico(tmp_path, ancho_pt=400, alto_pt=300, rotar=90,
                         trazos_azules=[((100, 200), (700, 200), 6), ((200, 400), (200, 560), 6)],
                         vectores_negros=[((100, 200), (700, 200), 0.5)])
    page = doc[0]
    assert page.rotation == 90 and page.rect == fitz.Rect(0, 0, 300, 400)
    (linea,) = [it for d in page.get_drawings() for it in d["items"]]
    p, q = linea[1], linea[2]
    assert (p.y, q.y) == (100, 100)                   # horizontal sin girar: y = 200 px / 2
    caja = IS.rect_sin_girar(page)
    assert caja == fitz.Rect(0, 0, 400, 300)
    escala = 3.0
    img = IS.pintar(page, caja, escala)
    assert img.shape == (900, 1200, 3)
    azul = _es_azul(img)
    # El trazo azul cae donde dice get_drawings (a escala), sin la línea negra encima.
    fila = round(p.y * escala)
    xs = np.nonzero(azul[fila])[0]
    assert abs(xs.min() - p.x * escala) <= 6 and abs(xs.max() - q.x * escala) <= 6
    ys = np.nonzero(azul[:, round((p.x + q.x) / 2 * escala)])[0]
    assert abs(ys.mean() - p.y * escala) <= 1.0
    # Mismo dibujo que get_pixmap de la vista girada, llevado al espacio sin girar (k=1 para /Rotate 90).
    clip = fitz.Rect(40, 150, 200, 290)               # zona del trazo sin vector, coords sin girar
    sola = IS.pintar(page, clip, escala)
    vista_clip = clip * page.rotation_matrix
    pix = page.get_pixmap(matrix=fitz.Matrix(escala, escala), clip=vista_clip, alpha=False)
    vista = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3)
    vuelta = np.rot90(vista, 1)
    assert vuelta.shape == sola.shape
    a, b = _es_azul(sola), _es_azul(vuelta)
    assert a.sum() > 500
    nucleo = np.ones((3, 3), np.uint8)
    assert (a & ~cv2.dilate(b.astype(np.uint8), nucleo).astype(bool)).sum() == 0
    assert (b & ~cv2.dilate(a.astype(np.uint8), nucleo).astype(bool)).sum() == 0


def test_teselas_cubren_las_imagenes(tmp_path):
    doc = _pdf_sintetico(tmp_path, trazos_azules=[((100, 300), (500, 300), 6)])
    page = doc[0]
    tes = list(IS.teselas(page, 4.0, lado_px=512, solape_px=64))
    assert len(tes) == 9                               # 1200 px en pasos de 448: 3 × 3
    union = fitz.Rect(tes[0][0])
    for r, img in tes:
        union |= r
        assert img.shape[:2] == (round(r.height * 4.0), round(r.width * 4.0))
    assert union == page.rect
    # el trazo aparece igual en una tesela que en el dibujo entero
    r, img = tes[3]                                    # 2.ª fila, 1.ª columna
    entero = IS.pintar(page, page.rect, 4.0)
    x0, y0 = round(r.x0 * 4), round(r.y0 * 4)
    assert (img == entero[y0:y0 + img.shape[0], x0:x0 + img.shape[1]]).mean() > 0.999


def test_phoenix_sd_h4_px_por_pt():
    page = _sd_south()[3]
    imgs = IS.imagenes_utiles(page)
    assert len(imgs) > 100
    assert 4.1 < IS.px_por_pt(imgs) < 4.25


def test_phoenix_sd_h4_pintar_trae_la_red_azul():
    page = _sd_south()[3]
    imgs = IS.imagenes_utiles(page)
    # La copia filtrada conserva todas las imágenes y ningún trazo ni letra.
    filtrada = IS._copia_filtrada(page)[0]
    assert filtrada.get_drawings() == [] and filtrada.get_text().strip() == ""
    assert len(filtrada.get_image_info()) == len(page.get_image_info())
    # En el centro de la hoja: la red azul está y los vectores negros de encima no.
    r = IS.rect_sin_girar(page)
    clip = fitz.Rect(r.x0 + r.width * .3, r.y0 + r.height * .3, r.x0 + r.width * .7, r.y0 + r.height * .7)
    escala = IS.px_por_pt(imgs)
    img = IS.pintar(page, clip, escala)
    normal = _render(page, clip, escala)
    assert img.shape == normal.shape
    assert _es_azul(img).sum() > 1000
    assert ((normal.max(-1) < 60) & (img.min(-1) > 200)).sum() > 1000


# ── Tarea 2: imagen_paleta ───────────────────────────────────────────────────────────────────

def _img_con(cuentas):
    """Imagen con exactamente `cuentas` {rgb: píxeles} (relleno blanco hasta completar filas)."""
    px = np.concatenate([np.tile(np.array(c, np.uint8), (n, 1)) for c, n in cuentas.items()])
    falta = (-len(px)) % 1000
    if falta:
        px = np.concatenate([px, np.full((falta, 3), 255, np.uint8)])
    return px.reshape(-1, 1000, 3)


def _img_rgb_con_antialias(color):
    im = np.full((600, 600, 3), 255, np.uint8)
    cv2.line(im, (50, 100), (550, 450), tuple(color), 8, cv2.LINE_AA)
    return im


def _img_degradado_ruidoso():
    rng = np.random.default_rng(1)
    base = np.linspace(0, 255, 300)[None, :, None] * np.ones((300, 1, 3))
    return np.clip(base + rng.normal(0, 40, (300, 300, 3)), 0, 255).astype(np.uint8)


def _paleta_real(page):
    imgs = IS.imagenes_utiles(page)
    r = IS.rect_sin_girar(page)
    clip = fitz.Rect(r.x0 + r.width * .3, r.y0 + r.height * .3, r.x0 + r.width * .5, r.y0 + r.height * .5)
    return IP.paleta([IS.pintar(page, clip, IS.px_por_pt(imgs))], indexada=IP.indexada(page))


def test_paleta_indexada_exacta():
    img = _img_con({(0, 77, 168): 5000, (128, 166, 212): 9000, (255, 255, 255): 10**6})
    assert [c.rgb for c in IP.paleta([img], indexada=True)] == [(128, 166, 212), (0, 77, 168)]   # por píxeles


def test_paleta_rgb_agrupa_antialias():
    img = _img_rgb_con_antialias(color=(200, 30, 30))          # bordes mezclados con blanco
    cols = IP.paleta([img], indexada=False)
    assert len(cols) == 1 and cols[0].rgb == IP.normalizar((200, 30, 30), False) == (192, 32, 32)


def test_foto_no_da_colores():
    assert IP.paleta([_img_degradado_ruidoso()], indexada=False) == []
    assert IP.es_fotografica(_img_degradado_ruidoso())
    assert not IP.es_fotografica(_img_rgb_con_antialias((200, 30, 30)))


def test_mascara_exacta_y_rgb():
    img = _img_con({(0, 77, 168): 500, (0, 79, 170): 500, (0, 90, 168): 500, (255, 255, 255): 1000})
    m = IP.mascara(img, IP.ColorImagen((0, 77, 168), 1, True))
    assert m.sum() == 1000                                     # ±2 por canal
    rojo = _img_rgb_con_antialias((200, 30, 30))
    cols = IP.paleta([rojo], indexada=False)
    m = IP.mascara(rojo, cols[0])
    assert m.sum() > 2000 and m[0, 0] == False  # noqa: E712


def test_indexada_sintetica_es_rgb(tmp_path):
    doc = _pdf_sintetico(tmp_path, trazos_azules=[((100, 300), (500, 300), 6)])
    assert IP.indexada(doc[0]) is False
    assert IP.indexada(_pdf_sin_imagenes(tmp_path)[0]) is False


def test_phoenix_sd_h4_colores():
    page = _sd_south()[3]
    assert IP.indexada(page)
    cols = {c.rgb for c in _paleta_real(page)}
    assert (0, 77, 168) in cols and (128, 166, 212) in cols


def test_antialias_gris_se_une_a_su_linea_y_la_trama_suelta_no():
    # Línea negra indexada con rampa de grises (2 niveles) en los bordes + un bloque de trama
    # (50 % del azul) que NO toca nada: la rampa colapsa en negro, la trama sigue siendo color.
    im = np.full((300, 400, 3), 255, np.uint8)
    im[100:106, 20:380] = (0, 0, 0)
    im[99:100, 20:380] = (60, 60, 60)
    im[98:99, 20:380] = (130, 130, 130)
    im[106:107, 20:380] = (60, 60, 60)
    im[107:108, 20:380] = (130, 130, 130)
    im[200:260, 50:200] = (128, 166, 212)
    cols = IP.paleta([im], indexada=True)
    assert [c.rgb for c in cols] == [(0, 0, 0), (128, 166, 212)] or \
        [c.rgb for c in cols] == [(128, 166, 212), (0, 0, 0)]
    negro = [c for c in cols if c.rgb == (0, 0, 0)][0]
    assert negro.pixeles == 360 * (6 + 2 + 2)


def test_rgb_varias_lineas_antialias_no_es_foto():
    im = np.full((600, 600, 3), 255, np.uint8)
    for k, col in enumerate([(200, 30, 30), (30, 160, 40), (40, 60, 200), (220, 140, 0)]):
        cv2.line(im, (30, 80 + 130 * k), (570, 120 + 130 * k), col, 7, cv2.LINE_AA)
    assert not IP.es_fotografica(im)
    assert len(IP.paleta([im], indexada=False)) == 4


def test_foto_en_grises_con_ruido_es_foto():
    rng = np.random.default_rng(2)
    g = np.clip(np.linspace(0, 255, 300)[None, :] + rng.normal(0, 45, (300, 300)), 0, 255)
    im = np.repeat(g.astype(np.uint8)[:, :, None], 3, axis=2)
    assert IP.es_fotografica(im)


def test_phoenix_sd_h4_paleta_corta():
    cols = _paleta_real(_sd_south()[3])
    rgbs = [c.rgb for c in cols]
    assert len(cols) <= 15, rgbs
    assert (0, 77, 168) in rgbs and (128, 166, 212) in rgbs


# ── Tarea 3: imagen_trazos ───────────────────────────────────────────────────────────────────

from hoja import imagen_trazos as IT  # noqa: E402

_LIENZO = (500, 500)


def _trazo(m, a, b, g):
    """Rectángulo de grosor g entre a y b (puntas planas, como un guión de PDF)."""
    a, b = np.array(a, float), np.array(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]]) * g / 2
    poli = np.array([a + n, b + n, b - n, a - n]) * 16
    cv2.fillConvexPoly(m, np.round(poli).astype(np.int32), 1, cv2.LINE_8, 4)
    return m


def _mask_linea(a, b, grosor):
    return _trazo(np.zeros(_LIENZO, np.uint8), a, b, grosor).astype(bool)


_n_guiones = 0


def _mask_guiones(a, b, largo, hueco, grosor):
    global _n_guiones
    m = np.zeros(_LIENZO, np.uint8)
    a, b = np.array(a, float), np.array(b, float)
    total = np.linalg.norm(b - a)
    d = (b - a) / total
    s, n = 0.0, 0
    while s + largo <= total:
        _trazo(m, a + d * s, a + d * (s + largo), grosor)
        s += largo + hueco
        n += 1
    _n_guiones = n
    return m.astype(bool)


def _rejilla(m, cx, cy, lado, g=2, paso=10):
    h = lado // 2
    cv2.rectangle(m, (cx - h, cy - h), (cx + h, cy + h), 1, g)
    for k in range(-h + paso, h, paso):
        cv2.line(m, (cx + k, cy - h), (cx + k, cy + h), 1, g)
        cv2.line(m, (cx - h, cy + k), (cx + h, cy + k), 1, g)
    return m


_REJ = (220, 200, 40)          # centro x, y y lado de la rejilla de prueba


def _mask_linea_con_rejilla():
    m = _trazo(np.zeros(_LIENZO, np.uint8), (40, 200), (400, 200), 6)
    return _rejilla(m, *_REJ).astype(bool)


def _fuera_del_simbolo(linea):
    cx, cy, lado = _REJ
    h = lado / 2 - 2
    return all(not (abs(x - cx) < h and abs(y - cy) < h) for x, y in linea)


def _mask_rayado():
    m = np.zeros(_LIENZO, np.uint8)
    cv2.rectangle(m, (100, 100), (300, 260), 1, 2)
    raya = np.zeros_like(m)
    for k in range(-160, 220, 12):
        cv2.line(raya, (100 + k, 260), (260 + k, 100), 1, 2)
    raya[:102, :] = 0
    raya[259:, :] = 0
    raya[:, :102] = 0
    raya[:, 299:] = 0
    return (m | raya).astype(bool)


def _mask_paralelas(sep_px):
    m = _trazo(np.zeros(_LIENZO, np.uint8), (40, 200), (400, 200), 6)
    _trazo(m, (40, 200 + 6 + sep_px), (400, 200 + 6 + sep_px), 6)
    return m.astype(bool)


def _largo(l):
    return sum(float(np.hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(l, l[1:]))


def test_trazo_recto_eje_al_centro_y_largo_completo():
    m = _mask_linea((40, 100), (400, 100), grosor=6)
    p = IT.trazos(m, 4.0)
    (a, b), = [(l[0], l[-1]) for l in p.lineas]
    a, b = sorted([a, b])
    assert abs(a[1] - 100) <= 0.25 and abs(b[1] - 100) <= 0.25
    assert abs(a[0] - 40) <= 1.0 and abs(b[0] - 400) <= 1.0          # punta alargada w/2
    assert abs(p.grosores[0] - 6 / 4.0) < 0.3
    assert p.simbolos == [] and not p.relleno


def test_trazo_diagonal_al_centro():
    m = _mask_linea((60, 60), (420, 330), grosor=6)
    (l,) = IT.trazos(m, 4.0).lineas
    d = np.array([360, 270]) / 450.0
    for x, y in l:                                         # distancia a la recta dibujada
        assert abs((x - 60) * d[1] - (y - 60) * d[0]) <= 0.35
    assert abs(_largo(l) - 450) <= 2.0


def test_discontinua_da_un_trazo_por_guion_sin_unir():
    m = _mask_guiones((40, 100), (400, 100), largo=30, hueco=12, grosor=6)
    p = IT.trazos(m, 4.0)
    assert len(p.lineas) == _n_guiones                 # nada se cierra
    for l in p.lineas:                                 # cada guión con su largo dibujado
        assert abs(_largo(l) - 30) <= 1.5


def test_curva_y_te():
    m = np.zeros(_LIENZO, np.uint8)
    cv2.ellipse(m, (250, 250), (150, 150), 0, 200, 340, 1, 6)
    (l,) = IT.trazos(m.astype(bool), 4.0).lineas
    r = [np.hypot(x - 250, y - 250) for x, y in l]
    assert len(l) >= 5 and max(abs(v - 150) for v in r[1:-1]) <= 0.5
    # «T»: tres trazos que comparten exactamente el punto del nudo
    m = _trazo(np.zeros(_LIENZO, np.uint8), (40, 300), (400, 300), 6)
    _trazo(m, (220, 300), (220, 450), 6)
    p = IT.trazos(m.astype(bool), 4.0)
    assert len(p.lineas) == 3
    puntas = [pt for l in p.lineas for pt in (l[0], l[-1])]
    nudo = max(set(puntas), key=puntas.count)
    assert puntas.count(nudo) == 3
    assert abs(nudo[0] - 220) <= 2 and abs(nudo[1] - 300) <= 2


def test_simbolo_sobre_linea_se_separa():
    p = IT.trazos(_mask_linea_con_rejilla(), 4.0)
    assert len(p.simbolos) == 1 and p.simbolos[0].forma.startswith("cuadro")
    s = p.simbolos[0]
    assert abs(s.cx - 220) <= 2 and abs(s.cy - 200) <= 2
    assert len(p.lineas) == 2 and all(_fuera_del_simbolo(l) for l in p.lineas)


def test_simbolo_compacto_circulo():
    m = np.zeros(_LIENZO, np.uint8)
    cv2.circle(m, (200, 200), 12, 1, -1)
    p = IT.trazos(m.astype(bool), 4.0)
    assert p.lineas == [] and [s.forma for s in p.simbolos] == ["círculo 6"]


def test_rayado_es_relleno():
    p = IT.trazos(_mask_rayado(), 4.0)
    assert p.relleno and p.lineas == []


def test_paralelas_cercanas_no_se_juntan():
    p = IT.trazos(_mask_paralelas(sep_px=4), 4.0)
    assert len(p.lineas) == 2


def test_ruido_y_vacia():
    m = np.zeros(_LIENZO, bool)
    assert IT.trazos(m, 4.0) == IT.Piezas([], [], [], False)
    m[10:13, 10:13] = True                                    # 9 px < RUIDO_PX
    assert IT.trazos(m, 4.0).lineas == []


def _mask_banda_en_caja():
    """Tubería «en caja» de Phoenix SD: contorno de 1 px que encierra bloques rellenos y cajitas
    blancas alternados; tronco horizontal (y = 150, 13 px) con un ramal en «T» hacia abajo
    (x = 220), una rejilla fina pegada a la punta izquierda y un aro con letra a la derecha."""
    m = np.zeros(_LIENZO, np.uint8)
    m[144, 60:380] = 1
    m[156, 60:380] = 1
    m[144:157, 60] = 1
    m[144:157, 379] = 1
    for a in range(61, 379, 40):                               # bloques de 20 px, cajitas de 20 px
        m[144:157, a:min(a + 20, 379)] = 1
    m[144:171, 214:227] = 1                                    # cruce del ramal
    m[156:301, 214] = 1
    m[156:301, 226] = 1
    m[300, 214:227] = 1
    for b in range(171, 300, 40):
        m[b:min(b + 20, 300), 214:227] = 1
    for k in range(0, 25, 4):                                  # rejilla 24 × 24 de líneas de 1 px
        m[138:163, 36 + k] = 1
        m[138 + k, 36:61] = 1
    cv2.circle(m, (394, 150), 14, 1, 3)                        # aro con letra
    cv2.line(m, (388, 156), (388, 144), 1, 2)
    cv2.line(m, (388, 144), (394, 151), 1, 2)
    cv2.line(m, (394, 151), (400, 144), 1, 2)
    cv2.line(m, (400, 144), (400, 156), 1, 2)
    return m.astype(bool)


def test_guiones_gruesos_sueltos_en_fila_son_lineas_no_simbolos():
    # Guiones de 20 × 13 px SIN contorno (otros planos): compactos, pero en fila = un trazo por guión.
    m = np.zeros(_LIENZO, np.uint8)
    for k in range(6):
        a = 40 + k * 42
        m[194:207, a:a + 20] = 1
    p = IT.trazos(m.astype(bool), 4.0)
    assert p.simbolos == [] and len(p.lineas) == 6           # nada se une
    for l, g in zip(p.lineas, p.grosores):
        assert all(abs(v[1] - 200) <= 0.5 for v in l)
        assert abs(_largo(l) - 20) <= 1.5 and abs(g - 13 / 4.0) <= 0.4


def test_banda_en_caja_es_un_eje_continuo_con_su_ramal():
    m = _mask_banda_en_caja()
    p = IT.trazos(m, 4.0)
    assert len(p.simbolos) == 2
    formas = sorted(s.forma.split()[0] for s in p.simbolos)
    assert formas == ["cuadro", "círculo"] or formas == ["círculo", "cuadro"] or "cuadro" in formas
    assert all(g > 2.5 for g in p.grosores)                   # ni una «pared» fina de 0.24 pt
    assert len(p.lineas) == 3                                  # tronco (dos tramos) + ramal
    puntas = [pt for l in p.lineas for pt in (l[0], l[-1])]
    nudo = max(set(puntas), key=puntas.count)
    assert puntas.count(nudo) == 3 and abs(nudo[0] - 220) <= 2 and abs(nudo[1] - 150) <= 2
    horiz = [l for l in p.lineas if abs(l[0][1] - l[-1][1]) < 2]
    vert = [l for l in p.lineas if abs(l[0][0] - l[-1][0]) < 2]
    assert len(horiz) == 2 and len(vert) == 1
    for l in horiz:
        assert all(abs(v[1] - 150) <= 0.5 for v in l if v != nudo)
    assert all(abs(v[0] - 220) <= 0.5 for v in vert[0] if v != nudo)
    xs = sorted(v[0] for l in horiz for v in l)
    assert xs[0] < 70 and xs[-1] > 370                         # de la rejilla al aro
    assert max(v[1] for v in vert[0]) > 295


def test_rectangulo_suelto_sigue_siendo_simbolo():
    m = np.zeros(_LIENZO, np.uint8)
    m[190:203, 100:120] = 1
    p = IT.trazos(m.astype(bool), 4.0)
    assert p.lineas == [] and [s.forma for s in p.simbolos] == ["cuadro 5×3"]


def test_paleta_guarda_los_absorbidos_y_la_mascara_los_toma():
    im = np.full((300, 400, 3), 255, np.uint8)
    im[100:106, 20:380] = (0, 0, 0)
    im[99:100, 20:380] = (60, 60, 60)
    im[98:99, 20:380] = (130, 130, 130)
    im[106:107, 20:380] = (60, 60, 60)
    im[107:108, 20:380] = (130, 130, 130)
    negro = [c for c in IP.paleta([im], indexada=True) if c.rgb == (0, 0, 0)][0]
    assert negro.absorbidos == ((60, 60, 60), (130, 130, 130))
    assert IP.mascara(im, negro).sum() == 360 * 10
    assert IP.mascara(im, IP.ColorImagen((0, 0, 0), 1, True)).sum() == 360 * 6


def test_aro_fino_con_letra_es_simbolo():
    m = np.zeros(_LIENZO, np.uint8)
    cv2.circle(m, (200, 200), 13, 1, 2)
    cv2.line(m, (195, 206), (195, 194), 1, 1)                  # letra suelta dentro
    cv2.line(m, (195, 194), (204, 206), 1, 1)
    cv2.line(m, (204, 206), (204, 194), 1, 1)
    p = IT.trazos(m.astype(bool), 4.0)
    assert p.lineas == [] and len(p.simbolos) == 1 and p.simbolos[0].forma.startswith("círculo")


# ── núcleo + familia (antialias) ─────────────────────────────────────────────────────────────

TRAMA = (128, 166, 212)                                   # #80A6D4: el 50 % exacto del azul
_P0, _ANG, _LARGO_BANDA = np.array([70.0, 330.0]), math.radians(30), 330.0


def _paleta16():
    blanco = np.array([255.0, 255, 255])
    azul = np.array(AZUL, float)
    tintes = [np.round(azul + (blanco - azul) * k / 14) for k in range(1, 14)]
    return np.array([blanco, azul, np.array(TRAMA, float)] + tintes)


def _cuantizar(img):
    pal = _paleta16()
    d = ((img[:, :, None, :].astype(float) - pal[None, None]) ** 2).sum(-1)
    return pal[d.argmin(-1)].astype(np.uint8)


def _img_banda_inclinada(rejilla=False, trama=False):
    """Banda «en caja» a 30° dibujada con antialias (8× y reducida) y llevada a 16 colores
    indexados: contorno de 1 px que la paleta casi no ve, bloques rellenos y cajitas blancas."""
    k = 8
    alto, ancho = 500, 500
    big = np.zeros((alto * k, ancho * k), np.uint8)
    u = np.array([math.cos(_ANG), -math.sin(_ANG)])
    n = np.array([-u[1], u[0]])

    def poli(pts, img=big):
        cv2.fillConvexPoly(img, np.round(((np.array(pts) + 0.5) * k - 0.5) * 16).astype(np.int32),  # centros de píxel
                           255, cv2.LINE_AA, 4)

    def linea(a, b, g, img=big):
        d = (np.array(b) - np.array(a)) / np.linalg.norm(np.array(b) - np.array(a))
        q = np.array([-d[1], d[0]]) * g / 2
        poli([np.array(a) + q, np.array(b) + q, np.array(b) - q, np.array(a) - q], img)

    a, b = _P0, _P0 + u * _LARGO_BANDA
    for s in (-6.0, 6.0):                                      # contorno de 1 px
        linea(a + n * s, b + n * s, 1.0)
    linea(a - n * 6.5, a + n * 6.5, 1.0)
    linea(b - n * 6.5, b + n * 6.5, 1.0)
    t = 0.0
    while t < _LARGO_BANDA:                                     # bloques de 20 px, cajitas de 20 px
        t1 = min(t + 20, _LARGO_BANDA)
        p, q = _P0 + u * t, _P0 + u * t1
        poli([p + n * 6.5, q + n * 6.5, q - n * 6.5, p - n * 6.5])
        t += 40
    if rejilla:                                                 # rejilla 24 × 24 de líneas de 1 px
        cx, cy = _P0 - u * 13
        for j in range(0, 25, 4):
            linea((cx - 12 + j, cy - 12), (cx - 12 + j, cy + 12), 1.0)
            linea((cx - 12, cy - 12 + j), (cx + 12, cy - 12 + j), 1.0)
    fr = cv2.resize(big, (ancho, alto), interpolation=cv2.INTER_AREA).astype(float) / 255
    img = 255 - fr[..., None] * (255 - np.array(AZUL, float))
    if trama:                                                   # trama de otro color pegada a la banda
        bt = np.zeros_like(big)
        c0 = _P0 + u * 150 + n * 7
        for j in range(0, 80, 8):
            linea(c0 + n * j - u * 40, c0 + n * j + u * 40, 1.0, bt)
        ft = cv2.resize(bt, (ancho, alto), interpolation=cv2.INTER_AREA).astype(float) / 255
        img = img * (1 - ft[..., None]) + ft[..., None] * np.array(TRAMA, float)
    return _cuantizar(np.clip(np.round(img), 0, 255).astype(np.uint8))


def _trazos_de_imagen(img):
    cols = IP.paleta([img], indexada=True)
    azul = [c for c in cols if c.rgb == AZUL][0]
    nucleo = IP.mascara(img, azul)
    return IT.trazos(nucleo, 4.0, familia=IP.familia(img, azul, cols)), nucleo


def _desvio_del_eje(pt):
    u = np.array([math.cos(_ANG), -math.sin(_ANG)])
    r = np.array(pt) - _P0
    return abs(r[0] * u[1] - r[1] * u[0])


def test_banda_inclinada_con_antialias_es_un_eje_continuo():
    p, _n = _trazos_de_imagen(_img_banda_inclinada())
    gruesas = [l for l, g in zip(p.lineas, p.grosores) if g > 2.0]
    assert len(gruesas) == 1, [len(l) for l in p.lineas]
    assert max(_desvio_del_eje(v) for v in gruesas[0]) <= 0.75
    assert _largo(gruesas[0]) > 0.9 * _LARGO_BANDA


def test_rejilla_con_antialias_en_la_punta_es_un_simbolo():
    p, _n = _trazos_de_imagen(_img_banda_inclinada(rejilla=True))
    u = np.array([math.cos(_ANG), -math.sin(_ANG)])
    cx, cy = _P0 - u * 13
    cerca = [s for s in p.simbolos if abs(s.cx - cx) <= 6 and abs(s.cy - cy) <= 6]
    assert len(cerca) == 1 and len(p.simbolos) == 1
    gruesas = [l for l, g in zip(p.lineas, p.grosores) if g > 2.0]
    assert len(gruesas) == 1


def test_trama_de_otro_color_no_entra_en_la_banda():
    img = _img_banda_inclinada(trama=True)
    p, nucleo = _trazos_de_imagen(img)
    assert not nucleo[np.abs(img.astype(int) - TRAMA).max(-1) <= 2].any()
    gruesas = [l for l, g in zip(p.lineas, p.grosores) if g > 2.0]
    assert len(gruesas) == 1 and max(_desvio_del_eje(v) for v in gruesas[0]) <= 0.75
    assert len(p.lineas) == 1, [round(g, 2) for g in p.grosores]


# ── puentes con evidencia y rejillas (relevo de la Tarea 3) ─────────────────────────────────

from hoja import imagen_puentes as IPU  # noqa: E402

_K_AA = 8


def _poli_aa(big, pts):
    cv2.fillConvexPoly(big, np.round(((np.array(pts, float) + 0.5) * _K_AA - 0.5) * 16).astype(np.int32),
                       255, cv2.LINE_AA, 4)


def _linea_aa(big, a, b, g):
    a, b = np.array(a, float), np.array(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    q = np.array([-d[1], d[0]]) * g / 2
    _poli_aa(big, [a + q, b + q, b - q, a - q])


def _borrar_aa(big, centro, u, largo, ancho):
    """Corte de BLANCO PURO de `largo` px a lo largo de u (en px de la imagen final)."""
    c, u = np.array(centro, float), np.array(u, float)
    n = np.array([-u[1], u[0]])
    pts = [c + u * largo / 2 + n * ancho / 2, c - u * largo / 2 + n * ancho / 2,
           c - u * largo / 2 - n * ancho / 2, c + u * largo / 2 - n * ancho / 2]
    cv2.fillConvexPoly(big, np.round(((np.array(pts) + 0.5) * _K_AA - 0.5) * 16).astype(np.int32),
                       0, cv2.LINE_8, 4)


def _a_imagen(big, alto=500, ancho=500):
    fr = cv2.resize(big, (ancho, alto), interpolation=cv2.INTER_AREA).astype(float) / 255
    img = 255 - fr[..., None] * (255 - np.array(AZUL, float))
    return _cuantizar(np.clip(np.round(img), 0, 255).astype(np.uint8))


def _banda_aa(big, p0, u, largo, cortes=0, semilla=0, contorno=True, bloque=20, caja=20, media=6.5):
    """Banda «en caja» desde p0 por u: bloques de `bloque` px y cajitas de `caja` px; contorno de
    1 px con `cortes` cortes de blanco puro de 1.5 px al azar en las cajitas (los dos lados)."""
    u = np.array(u, float) / np.linalg.norm(u)
    n = np.array([-u[1], u[0]])
    p0 = np.array(p0, float)
    b = p0 + u * largo
    if contorno:
        for s in (-(media - 0.5), media - 0.5):
            _linea_aa(big, p0 + n * s, b + n * s, 1.0)
        _linea_aa(big, p0 - n * media, p0 + n * media, 1.0)
        _linea_aa(big, b - n * media, b + n * media, 1.0)
    t = 0.0
    while t < largo:
        t1 = min(t + bloque, largo)
        p, q = p0 + u * t, p0 + u * t1
        _poli_aa(big, [p + n * media, q + n * media, q - n * media, p - n * media])
        t += bloque + caja
    rng = np.random.default_rng(semilla)
    n_cajas = int(largo // (bloque + caja))
    for _ in range(cortes):
        k = int(rng.integers(0, n_cajas))
        t = k * (bloque + caja) + bloque + float(rng.uniform(3, caja - 3))
        for s in (-(media - 0.5), media - 0.5):
            _borrar_aa(big, p0 + u * t + n * s, u, 1.5, 3.0)


def _piezas_aa(img):
    cols = IP.paleta([img], indexada=True)
    azul = [c for c in cols if c.rgb == AZUL][0]
    return IT.trazos(IP.mascara(img, azul), 4.0, familia=IP.familia(img, azul, cols))


def test_banda_inclinada_con_cortes_blancos_es_un_eje_continuo():
    big = np.zeros((500 * _K_AA, 500 * _K_AA), np.uint8)
    u = np.array([math.cos(_ANG), -math.sin(_ANG)])
    _banda_aa(big, _P0, u, _LARGO_BANDA, cortes=12, semilla=7)
    img = _a_imagen(big)
    p = _piezas_aa(img)
    gruesas = [l for l, g in zip(p.lineas, p.grosores) if g > 2.0]
    assert len(gruesas) == 1, [(len(l), round(g, 2)) for l, g in zip(p.lineas, p.grosores)]
    assert max(_desvio_del_eje(v) for v in gruesas[0]) <= 0.75
    assert _largo(gruesas[0]) > 0.9 * _LARGO_BANDA


def test_dos_bandas_paralelas_a_4_px_nunca_se_unen_entre_si():
    big = np.zeros((500 * _K_AA, 500 * _K_AA), np.uint8)
    _banda_aa(big, (40, 200), (1, 0), 400, cortes=10, semilla=3)
    _banda_aa(big, (60, 217), (1, 0), 380, cortes=10, semilla=4)        # bordes exteriores a 4 px
    img = _a_imagen(big)
    cols = IP.paleta([img], indexada=True)
    azul = [c for c in cols if c.rgb == AZUL][0]
    nucleo, fam = IP.mascara(img, azul), IP.familia(img, azul, cols)
    con = IPU.puentes(nucleo, fam, 4.0)
    assert (con & ~nucleo).any()                                       # sí hay puentes (en cada banda) …
    assert not (con & ~nucleo)[208:210, :].any()                     # … y nada entre las dos (filas 208–209)
    p = IT.trazos(nucleo, 4.0, familia=fam)
    gruesas = [l for l, g in zip(p.lineas, p.grosores) if g > 2.0]
    assert len(gruesas) == 2
    for l, y in zip(sorted(gruesas, key=lambda l: l[0][1]), (200, 217)):
        assert all(abs(v[1] - y) <= 1.5 for v in l)                  # cada eje en SU banda


def test_guiones_sin_contorno_tras_una_banda_quedan_sueltos():
    big = np.zeros((500 * _K_AA, 500 * _K_AA), np.uint8)
    _banda_aa(big, (40, 200), (1, 0), 140, cortes=6, semilla=5)       # banda de 40 a 180
    _banda_aa(big, (200, 200), (1, 0), 200, contorno=False)          # guiones de 20, huecos de 20
    img = _a_imagen(big)
    p = _piezas_aa(img)
    guiones = [l for l in p.lineas if min(v[0] for v in l) >= 195]
    assert len(guiones) == 5, [[(round(v[0]), round(v[1])) for v in l] for l in p.lineas]
    assert all(abs(_largo(l) - 20) <= 2 for l in guiones)
    banda = [l for l in p.lineas if min(v[0] for v in l) < 60]
    assert len(banda) == 1 and max(v[0] for v in banda[0]) <= 185


def test_rejilla_antialias_con_lineas_cortadas_es_un_simbolo():
    big = np.zeros((500 * _K_AA, 500 * _K_AA), np.uint8)
    _banda_aa(big, (140, 250), (1, 0), 260, cortes=6, semilla=9)
    x0, y0, x1, y1 = 104, 230, 140, 270                                # rejilla 36 × 40 pegada a la banda
    for x in range(x0, x1 + 1, 6):
        _linea_aa(big, (x, y0), (x, y1), 1.2)
    for y in range(y0, y1 + 1, 10):
        _linea_aa(big, (x0, y), (x1, y), 1.0)
    rng = np.random.default_rng(11)
    for _ in range(10):                                                 # cortes de blanco en las líneas
        x = x0 + 6 * int(rng.integers(0, 7))
        _borrar_aa(big, (x, float(rng.uniform(y0 + 3, y1 - 3))), (0, 1), 2.0, 3.0)
        y = y0 + 10 * int(rng.integers(0, 5))
        _borrar_aa(big, (float(rng.uniform(x0 + 3, x1 - 3)), y), (1, 0), 2.0, 3.0)
    img = _a_imagen(big)
    p = _piezas_aa(img)
    assert len(p.simbolos) == 1, p.simbolos
    s = p.simbolos[0]
    assert abs(s.cx - (x0 + x1) / 2) <= 3 and abs(s.cy - (y0 + y1) / 2) <= 3
    assert s.forma.startswith("cuadro")
    assert all(g > 2.0 for g in p.grosores), [round(g, 2) for g in p.grosores]
    assert len(p.lineas) == 1 and min(v[0] for v in p.lineas[0]) >= x1 - 2
