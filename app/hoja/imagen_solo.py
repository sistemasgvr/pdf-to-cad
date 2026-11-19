"""Dibujar SOLO las imágenes de una hoja (sin los vectores ni las letras de encima).

Para leer una red que viene como IMAGEN dentro de un PDF por lo demás vectorial (mapas «QS SD» de
Phoenix: tiras indexadas de 52 px con la red en azul) hace falta ver la imagen SIN lo que el PDF
dibuja encima: una línea de lote o un rótulo negro que cruza el trazo azul lo cortaría en el render
normal. PURO (fitz + numpy, sin Qt).

Coordenadas: las de `page.get_drawings()` y `page.get_image_info()`, que en una hoja con `/Rotate`
son las de la hoja SIN girar (medido con PyMuPDF 1.28.2: una línea vertical de `get_drawings` sale
horizontal en `get_pixmap` de una hoja con /Rotate 90, y `get_pixmap(clip=)` va en las coordenadas
de la VISTA girada). `pintar` devuelve la imagen en ese mismo espacio sin girar: el píxel (fila i,
columna j) es el punto (clip.x0 + (j + 0.5)/escala, clip.y0 + (i + 0.5)/escala).

Técnica de `pintar` (la 1.ª de las dos del plan, la que se eligió): el filtro de contenido de MuPDF
(`pdf_filter_page_contents` con un `PdfSanitizeFilterOptions2` cuyo `culler` descarta los trazos
—relleno, contorno, sin pintar—, las letras y los degradados, `recurse=1` para entrar en las formas
de una hoja compuesta) sobre una COPIA de la hoja en un documento en memoria, con el giro quitado.
Las imágenes quedan con su transformación, sus máscaras y los recortes de las formas tal cual, y se
dibujan con el mismo motor que el resto de la app. La 2.ª opción (componer cada imagen decodificada
con `cv2.warpAffine`) habría que rehacerle a mano máscaras, recortes y espacios de color indexados.
La copia filtrada se guarda en el documento (`_pdfcad_imagen_solo`) para las teselas siguientes.
"""

from __future__ import annotations

from typing import Iterator

import fitz
import numpy as np
import pymupdf

AREA_MIN_PT2 = 400.0          # imágenes más chicas (viñetas, puntos) no cuentan
PX_POR_PT_MAX = 6.0           # tope de la resolución con que se dibuja (memoria)

_m = fitz.mupdf
# Lo que el filtro QUITA: todo lo que no es imagen (los recortes se conservan).
_QUITAR = {
    _m.FZ_CULL_PATH_DROP, _m.FZ_CULL_PATH_FILL, _m.FZ_CULL_PATH_STROKE,
    _m.FZ_CULL_PATH_FILL_STROKE, _m.FZ_CULL_GLYPH, _m.FZ_CULL_SHADING,
}
_CACHE = "_pdfcad_imagen_solo"


def _tiene_capas(doc) -> bool:
    try:
        return bool(doc.get_ocgs())
    except Exception:
        return False


def rect_sin_girar(page) -> fitz.Rect:
    """El rectángulo de la hoja en las coordenadas de `get_drawings` (sin el /Rotate)."""
    return fitz.Rect(page.rect * page.derotation_matrix)


def imagenes_utiles(page) -> list[dict]:
    """Imágenes de la hoja con caja ≥ `AREA_MIN_PT2` (`get_image_info()`, `bbox` en las
    coordenadas de `get_drawings`). [] si el PDF tiene capas (OCG): esas hojas no se tocan.
    Sin `xrefs=True` (el plan lo pedía): nadie usa el xref y con él tarda ~1.7 s por hoja de
    Phoenix SD (pasa por un filtro de contenido) contra ~0.05 s sin él."""
    if _tiene_capas(page.parent):
        return []
    utiles = []
    for info in page.get_image_info():
        caja = fitz.Rect(info["bbox"])
        if caja.is_empty or caja.width * caja.height < AREA_MIN_PT2:
            continue
        utiles.append(info)
    return utiles


def px_por_pt(imgs) -> float:
    """Resolución de las imágenes: mediana de ancho en px / largo en pt de su lado ancho (el vector
    (a, b) de la transformación, así vale para imágenes giradas). Con tope `PX_POR_PT_MAX`; 0 sin
    imágenes."""
    valores = []
    for info in imgs:
        a, b = info["transform"][0], info["transform"][1]
        lado = float(np.hypot(a, b))
        if lado > 0 and info.get("width"):
            valores.append(info["width"] / lado)
    if not valores:
        return 0.0
    return float(min(PX_POR_PT_MAX, np.median(valores)))


class _SoloImagenes(_m.PdfSanitizeFilterOptions2):
    """Opciones del filtro: el `culler` dice 1 (quitar) a todo lo que no es imagen ni recorte."""

    def __init__(self):
        super().__init__()
        self.use_virtual_culler()

    def culler(self, *args):          # (ctm, rect, tipo): la firma varía según la versión
        return 1 if args[-1] in _QUITAR else 0


def _copia_filtrada(page):
    """Documento en memoria con la hoja sin giro y solo sus imágenes (memorizado en el documento)."""
    doc = page.parent
    cache = getattr(doc, _CACHE, None)
    if cache is None:
        cache = {}
        try:
            setattr(doc, _CACHE, cache)
        except Exception:
            pass
    tmp = cache.get(page.number)
    if tmp is not None:
        return tmp
    tmp = fitz.open()
    tmp.insert_pdf(doc, from_page=page.number, to_page=page.number)
    hoja = tmp[0]
    hoja.set_rotation(0)
    opciones = _SoloImagenes()
    filtro = pymupdf._make_PdfFilterOptions(recurse=1, sanitize=1, sopts=opciones)
    pp = pymupdf._as_pdf_page(hoja.this)
    _m.pdf_filter_page_contents(pp.doc(), pp, filtro)
    cache[page.number] = tmp
    return tmp


def soltar(doc) -> None:
    """Cierra las copias filtradas memorizadas en `doc`."""
    cache = getattr(doc, _CACHE, None) or {}
    for tmp in cache.values():
        try:
            tmp.close()
        except Exception:
            pass
    cache.clear()


def pintar(page, clip: fitz.Rect, escala: float) -> np.ndarray:
    """Imagen RGB uint8 (alto, ancho, 3) de SOLO las imágenes de `clip` (coordenadas de
    `get_drawings`) a `escala` px/pt, fondo blanco. Fuera de la hoja queda blanco."""
    clip = fitz.Rect(clip)
    ancho = max(1, int(np.ceil(clip.width * escala - 1e-6)))
    alto = max(1, int(np.ceil(clip.height * escala - 1e-6)))
    salida = np.full((alto, ancho, 3), 255, np.uint8)
    hoja_rect = rect_sin_girar(page)
    dentro = clip & hoja_rect
    if dentro.is_empty:
        return salida
    hoja = _copia_filtrada(page)[0]
    # Matriz con el origen en la esquina del clip: el píxel 0 empieza exacto en clip.x0/y0.
    mat = fitz.Matrix(escala, 0, 0, escala, -clip.x0 * escala, -clip.y0 * escala)
    pix = hoja.get_pixmap(matrix=mat, clip=dentro, alpha=False, colorspace=fitz.csRGB)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    # El pixmap empieza en (pix.x, pix.y) del espacio de la matriz (= px de la salida).
    y0, x0 = pix.y, pix.x
    ys, xs = max(0, y0), max(0, x0)
    ye, xe = min(alto, y0 + pix.h), min(ancho, x0 + pix.w)
    if ye > ys and xe > xs:
        salida[ys:ye, xs:xe] = arr[ys - y0:ye - y0, xs - x0:xe - x0]
    # Lo que cae fuera de la hoja, blanco (el contenido puede salirse del cuadro de la hoja).
    fx0 = int(np.floor((hoja_rect.x0 - clip.x0) * escala))
    fy0 = int(np.floor((hoja_rect.y0 - clip.y0) * escala))
    fx1 = int(np.ceil((hoja_rect.x1 - clip.x0) * escala))
    fy1 = int(np.ceil((hoja_rect.y1 - clip.y0) * escala))
    if fy0 > 0:
        salida[:min(alto, fy0)] = 255
    if fy1 < alto:
        salida[max(0, fy1):] = 255
    if fx0 > 0:
        salida[:, :min(ancho, fx0)] = 255
    if fx1 < ancho:
        salida[:, max(0, fx1):] = 255
    return salida


def teselas(page, escala: float, lado_px: int = 4096,
            solape_px: int = 64) -> Iterator[tuple[fitz.Rect, np.ndarray]]:
    """Recorre la unión de las cajas de `imagenes_utiles` en teselas de `lado_px` (con `solape_px`
    de solape con la vecina) y da (rect en coordenadas de `get_drawings`, imagen de `pintar`).
    Las teselas que no tocan ninguna imagen se saltan."""
    cajas = [fitz.Rect(i["bbox"]) & rect_sin_girar(page) for i in imagenes_utiles(page)]
    cajas = [c for c in cajas if not c.is_empty]
    if not cajas or escala <= 0:
        return
    union = fitz.Rect(cajas[0])
    for c in cajas[1:]:
        union |= c
    lado = lado_px / escala
    paso = max(1e-3, (lado_px - solape_px) / escala)
    y = union.y0
    while y < union.y1:
        x = union.x0
        while x < union.x1:
            r = fitz.Rect(x, y, min(x + lado, union.x1), min(y + lado, union.y1))
            if any(r.intersects(c) for c in cajas):
                yield r, pintar(page, r, escala)
            if r.x1 >= union.x1:
                break
            x += paso
        if min(y + lado, union.y1) >= union.y1:
            break
        y += paso
