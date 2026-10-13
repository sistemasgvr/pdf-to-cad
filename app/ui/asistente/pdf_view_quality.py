"""Re-render the focused PDF sheet as the user zooms into an arranged view.

The whole arrangement keeps inexpensive overview images. Only the sheet under
the viewport centre gets a sharper PDF render, bounded by a pixel budget.
Scene coordinates and recognition overlays stay at the overview scale.
"""
from __future__ import annotations

import math

import fitz
from PySide6 import QtCore, QtGui
from hoja.sheet_crops import page_rect
from ui.comun.recorte_nitido import REFINO_MS, TOPE_LETRAS_MPX, TOPE_REFINO_MPX, Hojas, escala_para


MAX_RENDER_PIXELS = 24_000_000
MAX_RENDER_SCALE = 4.0          # hoja ENTERA (FocusedPageQuality); el recorte visible no tiene tope


def render_scale(page, wanted, clip=None):
    """Limit a full-page bitmap while allowing detailed PDF rendering."""
    bounds = clip or page.rect
    area = max(1.0, float(bounds.width * bounds.height))
    return min(MAX_RENDER_SCALE, wanted, math.sqrt(MAX_RENDER_PIXELS / area))


class FocusedPageQuality(QtCore.QObject):
    def __init__(self, view, docs, sheets, rotations, items, overview_scale,
                 crops=None):
        super().__init__(view)
        self.view = view
        self.docs = docs
        self.sheets = sheets
        self.rotations = rotations or {}
        self.items = items
        self.overview_scale = overview_scale
        self.crops = crops or {}
        self._base = {slot: (item.pixmap(), item.pos()) for slot, item in items.items()}
        self._sharp_slot = None
        self._sharp_scale = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self.update_quality)
        view.viewChanged.connect(self.schedule)

    def schedule(self):
        self._timer.start()

    def invalidate(self, sources=None):
        """Call before a layer change replaces overview pixmaps."""
        slots = {sheet["slot"] for sheet in self.sheets
                 if sources is None or sheet["source"] in sources}
        if self._sharp_slot in slots:
            self._clear_sharp()
        for slot in slots:
            item = self.items[slot]
            self._base[slot] = (item.pixmap(), item.pos())

    def _clear_sharp(self):
        if self._sharp_slot is None:
            return
        item = self.items[self._sharp_slot]
        pixmap, pos = self._base[self._sharp_slot]
        item.setTransform(QtGui.QTransform())
        item.setPixmap(pixmap)
        item.setPos(pos)
        self._sharp_slot = None
        self._sharp_scale = 0.0

    def _focused_sheet(self):
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        for sheet in self.sheets:
            if self.items[sheet["slot"]].sceneBoundingRect().contains(centre):
                return sheet
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        candidates = [sheet for sheet in self.sheets
                      if self.items[sheet["slot"]].sceneBoundingRect().intersects(visible)]
        return candidates[0] if candidates else None

    def update_quality(self):
        sheet = self._focused_sheet()
        if sheet is None:
            self._clear_sharp()
            return
        slot = sheet["slot"]
        page = self.docs[sheet["source"]][sheet["page"]]
        clip = page_rect(page, self.crops.get(slot))
        screen_scale = abs(self.view.transform().m11()) * self.view.devicePixelRatioF()
        wanted = self.overview_scale * screen_scale * 1.15
        scale = render_scale(page, wanted, clip)
        if scale < self.overview_scale * 1.4:
            self._clear_sharp()
            return
        # Refresh only when another zoom level would visibly add detail.
        if slot == self._sharp_slot and scale < self._sharp_scale * 1.3:
            return
        self._clear_sharp()
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False,
                              clip=clip)
        image = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                             pix.stride, QtGui.QImage.Format_RGB888).copy()
        pixmap = QtGui.QPixmap.fromImage(image)
        angle = int(self.rotations.get(slot, 0)) % 360
        if angle:
            pixmap = pixmap.transformed(QtGui.QTransform().rotate(angle),
                                        QtCore.Qt.SmoothTransformation)
        base_pixmap, base_pos = self._base[slot]
        item = self.items[slot]
        item.setPixmap(pixmap)
        item.setTransform(QtGui.QTransform().scale(
            base_pixmap.width() / pixmap.width(),
            base_pixmap.height() / pixmap.height()))
        item.setPos(base_pos)
        self._sharp_slot = slot
        self._sharp_scale = scale


class ViewportSharpener(QtCore.QObject):
    """Re-renderiza nítida SOLO la parte visible de una hoja mostrada a
    `base_scale` px/pt en una vista (escena = hoja × base_scale). Con el zoom
    la imagen base se ve borrosa; esto pone encima un pixmap del recorte
    visible a la escala de pantalla y lo quita al alejarse. `get_page()`
    devuelve la fitz.Page actual. Desde 2026-10-13 sin el tope de 4 px/pt
    (`recorte_nitido`: a cualquier zoom) y el recorte cae EXACTO: su píxel
    (u, v) es el punto ((x + u)/escala, (y + v)/escala) de la hoja, con (x, y)
    el origen que da MuPDF (antes se estiraba al rectángulo pedido)."""

    def __init__(self, view, get_page, base_scale=1.0, z=1, delay_ms=150):
        super().__init__(view)
        self.view = view
        self.get_page = get_page
        self.base_scale = base_scale
        self.z = z
        self._item = None
        self._key = None
        self._hojas = Hojas(max_hojas=2)       # lista de dibujo de las últimas hojas vistas
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.update_quality)
        # hoja con letras Type3 caras: con la vista quieta, otra vez con más resolución
        self._refine = QtCore.QTimer(self)
        self._refine.setSingleShot(True)
        self._refine.setInterval(REFINO_MS)
        self._refine.timeout.connect(lambda: self.update_quality(refine=True))
        view.viewChanged.connect(self._schedule)

    def _schedule(self):
        self._refine.stop()
        self._timer.start()

    def invalidate(self):
        """La hoja cambió: quitar el recorte nítido y recalcular."""
        self._remove()
        self._key = None
        self._schedule()

    def _remove(self):
        if self._item is not None:
            self.view.scene().removeItem(self._item)
            self._item = None

    def update_quality(self, refine=False):
        self._refine.stop()                               # se decide otra vez abajo
        try:
            page = self.get_page()
        except Exception:
            page = None
        if page is None:
            self._remove(); return
        screen = abs(self.view.transform().m11()) * self.view.devicePixelRatioF()
        wanted = screen * self.base_scale * 1.15          # px de pantalla por pt de la hoja
        if wanted < self.base_scale * 1.4:
            self._remove(); self._key = None
            return
        vis = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        pw, ph = page.rect.width * self.base_scale, page.rect.height * self.base_scale
        region = vis.intersected(QtCore.QRectF(0, 0, pw, ph))
        if region.isEmpty():
            self._remove(); return
        # margen para no re-renderizar a cada pequeño desplazamiento
        pad = 0.25 * max(region.width(), region.height())
        region = region.adjusted(-pad, -pad, pad, pad).intersected(QtCore.QRectF(0, 0, pw, ph))
        rect_pt = (region.left() / self.base_scale, region.top() / self.base_scale,
                   region.right() / self.base_scale, region.bottom() / self.base_scale)
        # antes el tope era MAX_RENDER_SCALE: nunca menos que eso
        scale = self._hojas.escala(page, rect_pt, wanted, minimo=MAX_RENDER_SCALE,
                                   tope_mpx=TOPE_REFINO_MPX if refine else TOPE_LETRAS_MPX)
        if scale < self.base_scale * 1.4:
            self._remove(); self._key = None
            return
        zone = (id(page.parent), page.number, tuple(round(v, 1) for v in rect_pt))
        if self._item is not None and self._key is not None and self._key[0] == zone \
                and self._key[1] >= round(scale, 2):
            return                                        # el recorte que hay ya basta
        pix = self._hojas.render(page, rect_pt, scale)
        if pix is None:
            return
        pm = QtGui.QPixmap.fromImage(QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                                                  pix.stride, QtGui.QImage.Format_RGB888).copy())
        if pm.isNull():
            return
        self._remove()
        item = self.view.scene().addPixmap(pm)
        item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        item.setZValue(self.z)
        item.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        # px del recorte → escena: MuPDF empieza el recorte en (pix.x, pix.y) px de la
        # hoja a `scale` (redondeo hacia afuera); exacto, sin estirar.
        k = self.base_scale / scale
        item.setPos(pix.x * k, pix.y * k)
        item.setTransform(QtGui.QTransform.fromScale(k, k))
        self._item = item
        self._key = (zone, round(scale, 2))
        if not refine and scale < 0.98 * escala_para(wanted, rect_pt):
            self._refine.start()                          # letras Type3: quedó corto
