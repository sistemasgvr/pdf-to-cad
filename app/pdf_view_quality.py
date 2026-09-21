"""Re-render the focused PDF sheet as the user zooms into an arranged view.

The whole arrangement keeps inexpensive overview images. Only the sheet under
the viewport centre gets a sharper PDF render, bounded by a pixel budget.
Scene coordinates and recognition overlays stay at the overview scale.
"""
from __future__ import annotations

import math

import fitz
from PySide6 import QtCore, QtGui
from sheet_crops import page_rect


MAX_RENDER_PIXELS = 24_000_000
MAX_RENDER_SCALE = 4.0


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


def render_region(page, rect_pt, scale):
    """Pixmap del rectángulo `rect_pt` (x0, y0, x1, y1 en pt de la hoja VISIBLE,
    relativo a page.rect) a `scale` px/pt, o None si está vacío."""
    x0, y0, x1, y1 = rect_pt
    clip = fitz.Rect(page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
    if clip.is_empty or clip.width < 1e-3 or clip.height < 1e-3:
        return None
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, clip=clip)
    return QtGui.QPixmap.fromImage(QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                                                pix.stride, QtGui.QImage.Format_RGB888).copy())


class ViewportSharpener(QtCore.QObject):
    """Re-renderiza nítida SOLO la parte visible de una hoja mostrada a
    `base_scale` px/pt en una vista (escena = hoja × base_scale). Con el zoom
    la imagen base se ve borrosa; esto pone encima un pixmap del recorte
    visible a la escala de pantalla (con tope de píxeles) y lo quita al
    alejarse. `get_page()` devuelve la fitz.Page actual."""

    def __init__(self, view, get_page, base_scale=1.0, z=1, delay_ms=150):
        super().__init__(view)
        self.view = view
        self.get_page = get_page
        self.base_scale = base_scale
        self.z = z
        self._item = None
        self._key = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.update_quality)
        view.viewChanged.connect(self._timer.start)

    def invalidate(self):
        """La hoja cambió: quitar el recorte nítido y recalcular."""
        self._remove()
        self._key = None
        self._timer.start()

    def _remove(self):
        if self._item is not None:
            self.view.scene().removeItem(self._item)
            self._item = None

    def update_quality(self):
        try:
            page = self.get_page()
        except Exception:
            page = None
        if page is None:
            self._remove(); return
        screen = abs(self.view.transform().m11()) * self.view.devicePixelRatioF()
        wanted = screen * 1.15
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
        clip = fitz.Rect(*rect_pt)
        scale = render_scale(page, wanted, clip)
        key = (tuple(round(v, 1) for v in rect_pt), round(scale, 2))
        if self._item is not None and key == self._key:
            return
        pm = render_region(page, rect_pt, scale)
        if pm is None or pm.isNull():
            return
        self._remove()
        item = self.view.scene().addPixmap(pm)
        item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        item.setZValue(self.z)
        item.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        item.setPos(region.left(), region.top())
        item.setTransform(QtGui.QTransform().scale(region.width() / pm.width(), region.height() / pm.height()))
        self._item = item
        self._key = key
