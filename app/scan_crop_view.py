"""Four independently movable crop corners for scanned plans."""
from PySide6 import QtCore, QtGui
from sheet_crop_dialog import _CropView
import composite as C


class ScanCropView(_CropView):
    def __init__(self):
        super().__init__()
        self.polygon = []
        pen = QtGui.QPen(QtGui.QColor("#ff9a00"), 2)
        pen.setCosmetic(True)
        self._poly_item = self.scene().addPolygon(QtGui.QPolygonF(), pen,
            QtGui.QBrush(QtGui.QColor(255, 154, 0, 45)))
        self._poly_item.setZValue(3)

    def set_selection(self, rect):
        super().set_selection(rect)
        if rect is None:
            self.polygon = []
            self._poly_item.setPolygon(QtGui.QPolygonF())
        else:
            r = self._selection
            self.set_polygon([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()])

    def set_polygon(self, points):
        self.polygon = [QtCore.QPointF(p) for p in points]
        poly = QtGui.QPolygonF(self.polygon)
        self._selection = poly.boundingRect()
        self._shape.hide()
        self._poly_item.setPolygon(poly)
        for marker in self._handles.values():
            marker.hide()
        for name, point in zip(("tl", "tr", "br", "bl"), self.polygon):
            self._handles[name].setPos(point)
            self._handles[name].show()
        self._handles["center"].setPos(self._selection.center())
        self._handles["center"].show()
        self.selectionChanged.emit(self._selection)

    def normalized_polygon(self):
        r = self._page_rect
        return C.normalize_polygon([((p.x()-r.left())/r.width(), (p.y()-r.top())/r.height())
                                    for p in self.polygon]) if self.polygon else []

    def mousePressEvent(self, event):
        self._initial_polygon = list(self.polygon)
        super().mousePressEvent(event)

    def _move_corner(self, name, point):
        pts = list(self.polygon)
        pts[("tl", "tr", "br", "bl").index(name)] = point
        r = self._page_rect
        valid = C.normalize_polygon([((p.x()-r.left())/r.width(), (p.y()-r.top())/r.height()) for p in pts])
        if valid:
            self.set_polygon(pts)

    def _apply_drag(self, point):
        if self._drag_mode in ("tl", "tr", "br", "bl"):
            self._move_corner(self._drag_mode, point)
        elif self._drag_mode == "center":
            r = self._drag_initial
            moved = C.move_rect((r.left(), r.top(), r.right(), r.bottom()),
                point.x()-self._drag_start.x(), point.y()-self._drag_start.y(), self._bounds())
            delta = QtCore.QPointF(moved[0]-r.left(), moved[1]-r.top())
            self.set_polygon([p + delta for p in self._initial_polygon])
        else:
            super()._apply_drag(point)

    def keyPressEvent(self, event):
        directions = {QtCore.Qt.Key_Left: (-1, 0), QtCore.Qt.Key_Right: (1, 0),
                      QtCore.Qt.Key_Up: (0, -1), QtCore.Qt.Key_Down: (0, 1)}
        if self.polygon and event.key() in directions:
            dx, dy = directions[event.key()]
            step = 0.1 if event.modifiers() & QtCore.Qt.ControlModifier else 10 if event.modifiers() & QtCore.Qt.ShiftModifier else 1
            if self._active_handle in ("tl", "tr", "br", "bl"):
                p = self._handles[self._active_handle].pos() + QtCore.QPointF(dx*step, dy*step)
                r = self._page_rect
                p = QtCore.QPointF(max(r.left(), min(r.right(), p.x())), max(r.top(), min(r.bottom(), p.y())))
                self._move_corner(self._active_handle, p)
            else:
                r = self._selection
                moved = C.move_rect((r.left(), r.top(), r.right(), r.bottom()), dx*step, dy*step, self._bounds())
                self.set_polygon([p + QtCore.QPointF(moved[0]-r.left(), moved[1]-r.top()) for p in self.polygon])
            event.accept()
            return
        super().keyPressEvent(event)
