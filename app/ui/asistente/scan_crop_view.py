"""Área a tomar con ESQUINAS LIBRES (cuadrilátero) o rectángulo.

Pedido del usuario 2026-10-19: en todos los flujos (PDF con capas, aplanado y escaneo)
el área se puede ajustar esquina por esquina, como en el escaneo, con una casilla que lo
enciende y apaga. Apagado (`free=False`) la vista es el `_CropView` de siempre: rectángulo
con lados, imán a líneas y nada más cambia. Encendido, cada esquina se mueve sola, los
lados mueven sus dos esquinas a la vez (el lado sigue paralelo) y el centro lo traslada
todo; el imán a líneas lleva la esquina a la guía vertical/horizontal que tenga cerca."""
from PySide6 import QtCore, QtGui
from ui.asistente.sheet_crop_dialog import _CropView, _SNAP_TOL_MAX_PT, _SNAP_TOL_PX
from hoja import composite as C

CORNERS = ("tl", "tr", "br", "bl")
# lado → sus dos esquinas (índices en `polygon`, mismo orden que CORNERS)
SIDES = {"top": (0, 1), "right": (1, 2), "bottom": (2, 3), "left": (3, 0)}
RECT_TOL_PT = 0.05       # un cuadrilátero a ≤ esto de su caja ES un rectángulo (sin polígono)


class CornerCropView(_CropView):
    def __init__(self, free: bool = True):
        super().__init__()
        self.free = bool(free)
        self.polygon = []
        pen = QtGui.QPen(QtGui.QColor("#ff9a00"), 2)
        pen.setCosmetic(True)
        self._poly_item = self.scene().addPolygon(QtGui.QPolygonF(), pen,
            QtGui.QBrush(QtGui.QColor(255, 154, 0, 45)))
        self._poly_item.setZValue(3)
        self._initial_polygon = []

    # ── modo ────────────────────────────────────────────────────────────
    def set_free(self, on: bool):
        """Enciende/apaga las esquinas libres sin perder el área: al encender, el
        rectángulo pasa a ser el cuadrilátero; al apagar, el área es la caja del
        cuadrilátero (lo inclinado se pierde)."""
        on = bool(on)
        if on == self.free:
            return
        sel = QtCore.QRectF(self._selection) if self._selection is not None else None
        self.free = on
        if not on:
            self.polygon = []
            self._poly_item.setPolygon(QtGui.QPolygonF())
            self._poly_item.hide()
        self.set_selection(sel)

    # ── área ────────────────────────────────────────────────────────────
    def set_selection(self, rect):
        if not self.free:
            self.polygon = []
            self._poly_item.setPolygon(QtGui.QPolygonF())
            self._poly_item.hide()
            super().set_selection(rect)
            return
        if rect is None:
            super().set_selection(None)
            self.polygon = []
            self._poly_item.setPolygon(QtGui.QPolygonF())
            return
        r = QtCore.QRectF(rect).normalized()
        self.set_polygon([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()])

    def set_polygon(self, points):
        if not self.free:
            self.set_free(True)
        self.polygon = [QtCore.QPointF(p) for p in points]
        poly = QtGui.QPolygonF(self.polygon)
        self._selection = poly.boundingRect()
        self._shape.hide()
        self._poly_item.show()
        self._poly_item.setPolygon(poly)
        whole = len(self.polygon) == 4 and self.is_whole_page(self._selection) and all(
            any(abs(q.x() - c.x()) < 0.5 and abs(q.y() - c.y()) < 0.5 for q in self.polygon)
            for c in (self._page_rect.topLeft(), self._page_rect.topRight(),
                      self._page_rect.bottomRight(), self._page_rect.bottomLeft()))
        self._poly_item.setBrush(self._fill_for(self._selection) if whole
                                 else QtGui.QBrush(QtGui.QColor(255, 154, 0, 45)))
        for marker in self._handles.values():
            marker.hide()
        big = self._selection.width() >= 2 and self._selection.height() >= 2
        if big:
            for name, point in zip(CORNERS, self.polygon):
                self._handles[name].setPos(point)
                self._handles[name].show()
            for name, (i, j) in SIDES.items():
                a, b = self.polygon[i], self.polygon[j]
                self._handles[name].setPos((a + b) / 2.0)
                self._handles[name].show()
            self._handles["center"].setPos(self._selection.center())
            self._handles["center"].show()
        self.selectionChanged.emit(self._selection)

    def is_rectangle(self) -> bool:
        """¿El cuadrilátero coincide con su caja? (entonces es un rectángulo normal)"""
        if not self.polygon or self._selection is None:
            return True
        r = self._selection
        corners = (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())
        return all(abs(p.x() - c.x()) <= RECT_TOL_PT and abs(p.y() - c.y()) <= RECT_TOL_PT
                   for p, c in zip(self.polygon, corners))

    def normalized_polygon(self):
        """Cuadrilátero normalizado sobre la hoja visible, o [] si es un rectángulo
        (el área es entonces solo el clip, como siempre) o las esquinas están apagadas."""
        if not self.free or not self.polygon or self.is_rectangle():
            return []
        return self._normalized(self.polygon)

    def _normalized(self, pts):
        r = self._page_rect
        return C.normalize_polygon([((p.x()-r.left())/r.width(), (p.y()-r.top())/r.height())
                                    for p in pts])

    # ── arrastre ────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        self._initial_polygon = list(self.polygon)
        super().mousePressEvent(event)

    def _snap_point(self, point):
        """Imán de la esquina: x a la guía vertical, y a la horizontal que pase cerca
        (las líneas generales de la hoja); resalta las usadas."""
        from hoja.composite import snap_edge
        if not self.snap_enabled:
            return point, []
        tol = min(_SNAP_TOL_MAX_PT, _SNAP_TOL_PX / max(abs(self.transform().m11()), 1e-6))
        x, y, used = point.x(), point.y(), []
        g = snap_edge(self._guides["x"], x, y - tol, y + tol, tol)
        if g:
            x = g[0]; used.append(("x", g))
        g = snap_edge(self._guides["y"], y, x - tol, x + tol, tol)
        if g:
            y = g[0]; used.append(("y", g))
        return QtCore.QPointF(x, y), used

    def _move_corner(self, name, point):
        pts = list(self.polygon)
        pts[CORNERS.index(name)] = point
        if self._normalized(pts):        # convexo y dentro de la hoja; si no, no se mueve
            self.set_polygon(pts)

    def _move_side(self, name, delta, base=None):
        """Mueve las dos esquinas del lado `name` por `delta` (el lado sigue paralelo)."""
        pts = list(base if base is not None else self.polygon)
        r = self._page_rect
        for k in SIDES[name]:
            q = pts[k] + delta
            pts[k] = QtCore.QPointF(max(r.left(), min(r.right(), q.x())), max(r.top(), min(r.bottom(), q.y())))
        if self._normalized(pts):
            self.set_polygon(pts)

    def _apply_drag(self, point):
        if not self.free or self._drag_mode == "create":
            super()._apply_drag(point)
            return
        if self._drag_mode in CORNERS:
            point, used = self._snap_point(point)
            self._show_guides(used)
            self._move_corner(self._drag_mode, point)
        elif self._drag_mode in SIDES:
            self._move_side(self._drag_mode, point - self._drag_start, base=self._initial_polygon)
        elif self._drag_mode == "center":
            r = self._drag_initial
            moved = C.move_rect((r.left(), r.top(), r.right(), r.bottom()),
                point.x()-self._drag_start.x(), point.y()-self._drag_start.y(), self._bounds())
            delta = QtCore.QPointF(moved[0]-r.left(), moved[1]-r.top())
            self.set_polygon([p + delta for p in self._initial_polygon])

    def keyPressEvent(self, event):
        directions = {QtCore.Qt.Key_Left: (-1, 0), QtCore.Qt.Key_Right: (1, 0),
                      QtCore.Qt.Key_Up: (0, -1), QtCore.Qt.Key_Down: (0, 1)}
        if self.free and self.polygon and event.key() in directions:
            dx, dy = directions[event.key()]
            step = 0.1 if event.modifiers() & QtCore.Qt.ControlModifier else 10 if event.modifiers() & QtCore.Qt.ShiftModifier else 1
            if self._active_handle in CORNERS:
                p = self._handles[self._active_handle].pos() + QtCore.QPointF(dx*step, dy*step)
                r = self._page_rect
                p = QtCore.QPointF(max(r.left(), min(r.right(), p.x())), max(r.top(), min(r.bottom(), p.y())))
                self._move_corner(self._active_handle, p)
            elif self._active_handle in SIDES:
                self._move_side(self._active_handle, QtCore.QPointF(dx*step, dy*step))
            else:
                r = self._selection
                moved = C.move_rect((r.left(), r.top(), r.right(), r.bottom()), dx*step, dy*step, self._bounds())
                self.set_polygon([p + QtCore.QPointF(moved[0]-r.left(), moved[1]-r.top()) for p in self.polygon])
            event.accept()
            return
        super().keyPressEvent(event)


class ScanCropView(CornerCropView):
    """Escaneos: esquinas libres encendidas de entrada (como siempre)."""
    def __init__(self):
        super().__init__(free=True)
