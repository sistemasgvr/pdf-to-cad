"""recorte_nitido.py — La parte visible de una hoja del PDF, nítida a CUALQUIER zoom.

Pedido del usuario (2026-10-13, «Componer hoja» sobre un mapa de Phoenix: al acercarse la
hoja se veía borrosa): el compositor re-dibujaba lo visible a 4 px/pt como mucho y «Capas de
la hoja», la vista previa y el editor nunca pasaban de la resolución de su imagen (3–3.5
px/pt). Ahora el recorte va a la resolución de la PANTALLA, con el mismo tope de píxeles de
siempre (`MAX_PX`). Es solo imagen: coordenadas, imán y composición no la usan.

Fuentes Type3 (mapas SIG aplanados): MuPDF dibuja cada letra en una imagen del tamaño de su
caja DECLARADA —en Phoenix ~20× la letra: 37 pt para una letra de 2 pt— aunque la letra caiga
fuera del recorte: a 24 px/pt un recorte tardaba 6 s y a 60 px/pt un minuto. En esas hojas
(`usa_type3`) el recorte pasa por el «culling device» de MuPDF, que no manda al dibujo las
letras de fuera (descarta una letra si más de la mitad de su caja cae en los rectángulos que
se le dan). Se le dan solo rectángulos que ninguna letra que toca el recorte alcanza
(`_rectangulos_fuera`, con las MISMAS cajas que calcula MuPDF: `Medidor`), así que el
resultado es IDÉNTICO byte a byte al render de siempre. Y si las letras que quedan costarían
más de `TOPE_LETRAS_MPX`, la escala baja (nunca por debajo de la que se usaba antes); con la
vista quieta `REFINO_MS`, la vista lo vuelve a dibujar con `TOPE_REFINO_MPX` (Phoenix, vista
a 16 px/pt: 9.3 px/pt en 0.3 s y luego 16 px/pt en ~0.9 s; antes 4 px/pt). Sin Type3 (CAD:
DU06, DU08, LABOE) no hay tope de letras: la resolución de la pantalla en 6–35 ms.

Sin Qt: lo usan `fondo_pdf.Nitidez`, `pdf_view_quality.ViewportSharpener` y las piezas del
compositor (`composite_view.PieceItem`).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from typing import Optional

import fitz
import numpy as np
import pymupdf
from pymupdf import mupdf as _mu

MAX_PX = 24_000_000            # píxeles de un recorte nítido (el tope de siempre)
MAX_ESCALA = 64.0              # px/pt (4608 dpi): por si una vista no limita su zoom
TOPE_LETRAS_MPX = 800.0        # Mpx de letras Type3 a dibujar al moverse (≈ 0.3 s en Phoenix)
TOPE_REFINO_MPX = 2400.0       # … y con la vista quieta `REFINO_MS` (≈ 0.9 s; 1:1 a 16 px/pt)
REFINO_MS = 700
PAD_LETRA_PT = 2.0             # holgura del recorte al buscar las letras que lo tocan


def usa_type3(page: fitz.Page) -> bool:
    """¿La hoja (o un XObject suyo) usa fuentes Type3? Solo ahí hace falta recortar letras."""
    try:
        return any(f[2] == "Type3" for f in page.get_fonts(full=True))
    except Exception:
        return False


class Medidor(_mu.FzDevice2):
    """Dispositivo que solo anota la caja de cada letra, calculada igual que el culling device
    de MuPDF (`fz_bound_glyph` con la matriz de la letra × ctm). En el trazo de texto se le
    suma el grosor de la línea (MuPDF no lo cuenta: así la caja nunca se queda corta)."""

    def __init__(self):
        super().__init__()
        self.use_virtual_fill_text()
        self.use_virtual_stroke_text()
        self.use_virtual_clip_text()
        self.use_virtual_clip_stroke_text()
        self.cajas = []

    def _texto(self, text, ctm, borde=0.0):
        c = _mu.FzMatrix(ctm)
        span = text.head
        while span:
            items = _mu.FzTextSpan(span)
            font = _mu.FzFont(_mu.ll_fz_keep_font(span.font))
            t = _mu.FzMatrix(span.trm)
            for i in range(span.len):
                it = items.items(i)
                if it.gid < 0:
                    continue
                r = _mu.fz_bound_glyph(font, it.gid, _mu.fz_concat(_mu.FzMatrix(t.a, t.b, t.c, t.d, it.x, it.y), c))
                self.cajas.append((r.x0 - borde, r.y0 - borde, r.x1 + borde, r.y1 + borde))
            span = span.next

    @staticmethod
    def _borde(stroke, ctm) -> float:
        try:
            return float(stroke.linewidth) * max(1.0, _mu.fz_matrix_expansion(_mu.FzMatrix(ctm)))
        except Exception:
            return 2.0

    def fill_text(self, ctx, text, ctm, *a):
        self._texto(text, ctm)

    def stroke_text(self, ctx, text, stroke, ctm, *a):
        self._texto(text, ctm, self._borde(stroke, ctm))

    def clip_text(self, ctx, text, ctm, scissor):
        self._texto(text, ctm)

    def clip_stroke_text(self, ctx, text, stroke, ctm, scissor):
        self._texto(text, ctm, self._borde(stroke, ctm))


def cajas_de_letras(dl: fitz.DisplayList) -> Optional[np.ndarray]:
    """(n, 4) cajas de las letras de la lista de dibujo en pt de la hoja; None si no se
    pudieron medir (entonces no se recorta ninguna letra)."""
    dev = Medidor()
    try:
        _mu.fz_run_display_list(dl.this, dev, _mu.FzMatrix(), _mu.FzRect(_mu.FzRect.Fixed_INFINITE),
                                _mu.FzCookie())
        _mu.fz_close_device(dev)
    except Exception:
        return None
    cajas = np.array(dev.cajas, float).reshape(-1, 4)
    if not np.isfinite(cajas).all() or (np.abs(cajas) > 1e6).any():
        return None                          # una caja infinita: no se puede razonar sobre ella
    return cajas


def _zona_a_conservar(cajas: np.ndarray, clip: fitz.Rect, escala: float):
    """Rectángulo que contiene el recorte (con holgura) y TODA letra que lo toca."""
    pad = PAD_LETRA_PT + 2.0 / escala
    x0, y0, x1, y1 = clip.x0 - pad, clip.y0 - pad, clip.x1 + pad, clip.y1 + pad
    if len(cajas):
        c = cajas
        toca = (c[:, 0] <= x1) & (c[:, 2] >= x0) & (c[:, 1] <= y1) & (c[:, 3] >= y0)
        if toca.any():
            t = c[toca]
            x0, y0 = min(x0, float(t[:, 0].min())), min(y0, float(t[:, 1].min()))
            x1, y1 = max(x1, float(t[:, 2].max())), max(y1, float(t[:, 3].max()))
    return x0, y0, x1, y1


def _area_dibujada(cajas: np.ndarray, zona) -> float:
    """pt² de las cajas de las letras que MuPDF NO descarta con `zona` (regla: descarta si
    más de la mitad de la caja cae fuera)."""
    if not len(cajas):
        return 0.0
    x0, y0, x1, y1 = zona
    c = cajas
    area = np.clip(c[:, 2] - c[:, 0], 0, None) * np.clip(c[:, 3] - c[:, 1], 0, None)
    dentro = (np.clip(np.minimum(c[:, 2], x1) - np.maximum(c[:, 0], x0), 0, None)
              * np.clip(np.minimum(c[:, 3], y1) - np.maximum(c[:, 1], y0), 0, None))
    return float(area[(area - dentro) <= 0.5 * area].sum())


def _rectangulos_fuera(zona):
    """Cuatro rectángulos que cubren todo lo de fuera de `zona`, sin solaparse (MuPDF suma
    las intersecciones: dos rectángulos solapados contarían doble)."""
    x0, y0, x1, y1 = zona
    big = 1e7
    v = _mu.vector_fz_rect()
    for r in ((-big, -big, x0, big), (x1, -big, big, big), (x0, -big, x1, y0), (x0, y1, x1, big)):
        fr = _mu.fz_rect()
        fr.x0, fr.y0, fr.x1, fr.y1 = r
        v.append(fr)
    return v


def render_sin_letras_fuera(dl: fitz.DisplayList, escala: float, clip: fitz.Rect,
                            cajas: np.ndarray) -> fitz.Pixmap:
    """`dl.get_pixmap(matrix=escala, clip=clip, alpha=False)` (el mismo código de PyMuPDF,
    `JM_pixmap_from_display_list`) con el culling device delante del dibujo."""
    matrix = pymupdf.JM_matrix_from_py(fitz.Matrix(escala, escala))
    rclip = pymupdf.JM_rect_from_py(clip)
    rect = _mu.fz_intersect_rect(_mu.fz_bound_display_list(dl.this), rclip)
    irect = _mu.fz_round_rect(_mu.fz_transform_rect(rect, matrix))
    pix = _mu.fz_new_pixmap_with_bbox(_mu.FzColorspace(_mu.FzColorspace.Fixed_RGB), irect,
                                      _mu.FzSeparations(), 0)
    _mu.fz_clear_pixmap_with_value(pix, 0xFF)
    dev = _mu.fz_new_draw_device_with_bbox(matrix, pix, irect)
    cull = _mu.fz_new_culling_device_with_rects2(dev, _rectangulos_fuera(_zona_a_conservar(cajas, clip, escala)))
    try:
        _mu.fz_run_display_list(dl.this, cull, _mu.FzMatrix(), rclip, _mu.FzCookie())
    finally:
        _mu.fz_close_device(cull)            # el culling device no cierra el de dibujo
        _mu.fz_close_device(dev)
    return pymupdf.Pixmap("raw", pix)


def escala_para(quiero: float, rect_pt) -> float:
    """px/pt del recorte `rect_pt`: la que pide la pantalla, con los topes de píxeles y de
    escala."""
    x0, y0, x1, y1 = rect_pt
    area = max(1.0, (x1 - x0) * (y1 - y0))
    return min(quiero, MAX_ESCALA, math.sqrt(MAX_PX / area))


class Hojas:
    """Lista de dibujo (y cajas de letras si usa Type3) de las últimas hojas re-dibujadas.
    Clave = (documento, hoja): `doc[i]` da un objeto nuevo en cada llamada. Quien cambie las
    capas del documento llama `soltar()` (la lista guarda lo que se veía al crearla)."""

    def __init__(self, max_hojas: int = 4):
        self.max_hojas = max_hojas
        self._d: "OrderedDict[tuple, dict]" = OrderedDict()

    def soltar(self) -> None:
        self._d.clear()

    def _entrada(self, page: fitz.Page) -> dict:
        key = (id(page.parent), page.number)
        e = self._d.get(key)
        if e is None or e["doc"] is not page.parent:
            e = {"doc": page.parent, "pagina": page, "lista": page.get_displaylist(), "cajas": False}
            self._d[key] = e
            while len(self._d) > self.max_hojas:
                self._d.popitem(last=False)
        self._d.move_to_end(key)
        return e

    def lista(self, page: fitz.Page) -> fitz.DisplayList:
        return self._entrada(page)["lista"]

    def cajas(self, page: fitz.Page) -> Optional[np.ndarray]:
        """Cajas de las letras (None = la hoja no usa Type3 o no se pudieron medir)."""
        e = self._entrada(page)
        if e["cajas"] is False:
            e["cajas"] = cajas_de_letras(e["lista"]) if usa_type3(page) else None
        return e["cajas"]

    def escala(self, page: fitz.Page, rect_pt, quiero: float, minimo: float,
               tope_mpx: float = TOPE_LETRAS_MPX) -> float:
        """Escala del recorte `rect_pt` (pt de la hoja visible): `quiero` con los topes de
        siempre (`escala_para`) y, en hojas con Type3, la que no pase de `tope_mpx` de letras;
        nunca menos que min(quiero, `minimo`) (lo que se dibujaba antes). Si queda por debajo
        de `escala_para`, la vista puede refinar con `TOPE_REFINO_MPX` al quedarse quieta."""
        escala = escala_para(quiero, rect_pt)
        cajas = self.cajas(page)
        if cajas is None or not len(cajas):
            return escala
        area = _area_dibujada(cajas, _zona_a_conservar(cajas, _clip(page, rect_pt), escala))
        if area <= 0:
            return escala
        return max(min(escala, minimo), min(escala, math.sqrt(tope_mpx * 1e6 / area)))

    def render(self, page: fitz.Page, rect_pt, escala: float) -> Optional[fitz.Pixmap]:
        """Pixmap del recorte `rect_pt` a `escala` px/pt (None si está vacío). Mismos píxeles
        que `page.get_pixmap(matrix=escala, clip=…)`; su (x, y) es el origen del recorte en
        px de la hoja a esa escala (MuPDF redondea hacia afuera)."""
        clip = _clip(page, rect_pt)
        if clip.is_empty or clip.width < 1e-3 or clip.height < 1e-3:
            return None
        e = self._entrada(page)
        cajas = self.cajas(page)
        if cajas is not None and len(cajas):
            try:
                return render_sin_letras_fuera(e["lista"], escala, clip, cajas)
            except Exception:
                pass                          # cualquier problema: el render de siempre
        return e["lista"].get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False, clip=clip)


def _clip(page: fitz.Page, rect_pt) -> fitz.Rect:
    x0, y0, x1, y1 = rect_pt
    r = page.rect
    return fitz.Rect(r.x0 + x0, r.y0 + y0, r.x0 + x1, r.y0 + y1)
