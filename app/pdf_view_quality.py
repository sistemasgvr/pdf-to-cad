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
