"""Pick the plan area within one PDF sheet without changing the PDF."""
from __future__ import annotations

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from sheet_crops import move_rect, resize_corner, resize_side
from widgets import ZoomPanView


class _CropView(ZoomPanView):
    selectionChanged = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self._page_rect = QtCore.QRectF()
        self._selection = None
        self._drag_start = None
        self._drag_mode = None
        self._drag_initial = None
        self._active_handle = "center"
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._shape = self.scene().addRect(QtCore.QRectF(),
            QtGui.QPen(QtGui.QColor("#ff9a00"), 2),
            QtGui.QBrush(QtGui.QColor(255, 154, 0, 45)))
        self._shape.setZValue(3)
        outline = self._shape.pen()
        outline.setCosmetic(True)
        self._shape.setPen(outline)
        self._handles = {}
        for name in ("tl", "tr", "bl", "br", "top", "right", "bottom", "left", "center"):
            pen = QtGui.QPen(QtGui.QColor("#ffffff"), 2)
            brush = QtGui.QBrush(QtGui.QColor("#ff9a00"))
            if name in ("top", "right", "bottom", "left"):
                marker = self.scene().addRect(-5, -5, 10, 10, pen, brush)
            else:
                marker = self.scene().addEllipse(-6, -6, 12, 12, pen, brush)
            marker.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            marker.setZValue(4)
            marker.setVisible(False)
            self._handles[name] = marker
        self._highlight_handle()

    def _highlight_handle(self):
        for name, marker in self._handles.items():
            color = "#2b6fd1" if name == self._active_handle else "#ff9a00"
            marker.setBrush(QtGui.QBrush(QtGui.QColor(color)))

    def set_page(self, rect):
        self._page_rect = QtCore.QRectF(rect)

    def set_selection(self, rect):
        self._selection = QtCore.QRectF(rect).normalized() if rect is not None else None
        self._shape.setRect(self._selection or QtCore.QRectF())
        self._shape.setVisible(self._selection is not None)
        if self._selection is not None and self._selection.width() >= 2 and self._selection.height() >= 2:
            r = self._selection
            points = {"tl": r.topLeft(), "tr": r.topRight(),
                      "bl": r.bottomLeft(), "br": r.bottomRight(),
                      "top": QtCore.QPointF(r.center().x(), r.top()),
                      "right": QtCore.QPointF(r.right(), r.center().y()),
                      "bottom": QtCore.QPointF(r.center().x(), r.bottom()),
                      "left": QtCore.QPointF(r.left(), r.center().y()),
                      "center": r.center()}
            for name, marker in self._handles.items():
                marker.setPos(points[name])
                marker.setVisible(True)
        else:
            for marker in self._handles.values():
                marker.setVisible(False)
        self.selectionChanged.emit(self._selection)

    def _clamped(self, event):
        point = self.mapToScene(event.position().toPoint())
        return QtCore.QPointF(
            max(self._page_rect.left(), min(self._page_rect.right(), point.x())),
            max(self._page_rect.top(), min(self._page_rect.bottom(), point.y())))

    def _bounds(self):
        r = self._page_rect
        return r.left(), r.top(), r.right(), r.bottom()

    def _handle_at(self, position):
        closest = None
        for name, marker in self._handles.items():
            if not marker.isVisible():
                continue
            centre = self.mapFromScene(marker.pos())
            distance = (position.x() - centre.x()) ** 2 + (position.y() - centre.y()) ** 2
            if distance <= 12 ** 2 and (closest is None or distance < closest[0]):
                closest = distance, name
        return closest[1] if closest else None

    def _apply_drag(self, point):
        if self._drag_mode == "create":
            self.set_selection(QtCore.QRectF(self._drag_start, point))
            return
        initial = self._drag_initial
        coords = (initial.left(), initial.top(), initial.right(), initial.bottom())
        if self._drag_mode == "center":
            dx = point.x() - self._drag_start.x()
            dy = point.y() - self._drag_start.y()
            result = move_rect(coords, dx, dy, self._bounds())
        elif self._drag_mode in ("top", "right", "bottom", "left"):
            coordinate = point.y() if self._drag_mode in ("top", "bottom") else point.x()
            result = resize_side(coords, self._drag_mode, coordinate, self._bounds())
        else:
            result = resize_corner(coords, self._drag_mode, point.x(), point.y(),
                                   self._bounds())
        x0, y0, x1, y1 = result
        self.set_selection(QtCore.QRectF(x0, y0, x1 - x0, y1 - y0))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setFocus()
            self._drag_start = self._clamped(event)
            handle = self._handle_at(event.position())
            self._drag_mode = handle or "create"
            self._active_handle = handle or "center"
            self._highlight_handle()
            self._drag_initial = QtCore.QRectF(self._selection) if handle else None
            if not handle:
                self.set_selection(QtCore.QRectF(self._drag_start, self._drag_start))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode is not None:
            self._apply_drag(self._clamped(event))
            event.accept()
            return
        handle = self._handle_at(event.position())
        cursor = {"tl": QtCore.Qt.SizeFDiagCursor, "br": QtCore.Qt.SizeFDiagCursor,
                  "tr": QtCore.Qt.SizeBDiagCursor, "bl": QtCore.Qt.SizeBDiagCursor,
                  "top": QtCore.Qt.SizeVerCursor, "bottom": QtCore.Qt.SizeVerCursor,
                  "left": QtCore.Qt.SizeHorCursor, "right": QtCore.Qt.SizeHorCursor,
                  "center": QtCore.Qt.SizeAllCursor}.get(handle, QtCore.Qt.CrossCursor)
        self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._drag_mode is not None:
            self._apply_drag(self._clamped(event))
            self._drag_start = None
            self._drag_mode = None
            self._drag_initial = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        direction = {QtCore.Qt.Key_Left: (-1, 0), QtCore.Qt.Key_Right: (1, 0),
                     QtCore.Qt.Key_Up: (0, -1), QtCore.Qt.Key_Down: (0, 1)}.get(event.key())
        if direction and self._selection is not None:
            modifiers = event.modifiers()
            step = (0.1 if modifiers & QtCore.Qt.ControlModifier else
                    10.0 if modifiers & QtCore.Qt.ShiftModifier else 1.0)
            dx, dy = direction[0] * step, direction[1] * step
            r = self._selection
            coords = (r.left(), r.top(), r.right(), r.bottom())
            if self._active_handle == "center":
                x0, y0, x1, y1 = move_rect(coords, dx, dy, self._bounds())
            elif self._active_handle in ("top", "right", "bottom", "left"):
                coordinate = {
                    "top": r.top() + dy, "bottom": r.bottom() + dy,
                    "left": r.left() + dx, "right": r.right() + dx,
                }[self._active_handle]
                x0, y0, x1, y1 = resize_side(
                    coords, self._active_handle, coordinate, self._bounds())
            else:
                point = {"tl": r.topLeft(), "tr": r.topRight(),
                         "bl": r.bottomLeft(), "br": r.bottomRight()}[self._active_handle]
                x0, y0, x1, y1 = resize_corner(
                    coords, self._active_handle, point.x() + dx, point.y() + dy,
                    self._bounds())
            self.set_selection(QtCore.QRectF(x0, y0, x1 - x0, y1 - y0))
            event.accept()
            return
        super().keyPressEvent(event)


class SheetCropDialog(QtWidgets.QDialog):
    def __init__(self, parent, page, title, current=None):
        super().__init__(parent)
        self.setWindowTitle(_tr("Delimitar plano · {name}").format(name=title))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinimizeButtonHint
                            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1150, 800)
        self.result_crop = None
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(_tr(
            "Arrastra un rectángulo alrededor del plano. Ajusta sus esquinas o cada lado; "
            "el punto central mueve el área sin cambiar su forma. Flechas = 1 punto del PDF, "
            "Ctrl+flechas = 0,1 y Mayús+flechas = 10. Rueda = zoom; botón central = desplazar."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.view = _CropView()
        layout.addWidget(self.view, 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
        image = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                             pix.stride, QtGui.QImage.Format_RGB888).copy()
        self.view.scene().addPixmap(QtGui.QPixmap.fromImage(image))
        self.view.set_page(QtCore.QRectF(0, 0, pix.width, pix.height))
        self.view.setSceneRect(QtCore.QRectF(0, 0, pix.width, pix.height))
        if current:
            x0, y0, x1, y1 = current
            self.view.set_selection(QtCore.QRectF(
                x0 * pix.width, y0 * pix.height,
                (x1 - x0) * pix.width, (y1 - y0) * pix.height))
        self.status = QtWidgets.QLabel()
        layout.addWidget(self.status)
        buttons = QtWidgets.QDialogButtonBox()
        self.use = buttons.addButton(_tr("Usar esta área"), QtWidgets.QDialogButtonBox.AcceptRole)
        full = buttons.addButton(_tr("Usar hoja completa"), QtWidgets.QDialogButtonBox.ActionRole)
        cancel = buttons.addButton(_tr("Cancelar"), QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._accept_selection)
        full.clicked.connect(self._accept_full)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)
        self.view.selectionChanged.connect(self._update_status)
        self._update_status(self.view._selection)

    def _update_status(self, rect):
        valid = self._valid(rect)
        self.use.setEnabled(valid)
        self.status.setText(_tr("Área marcada") if valid else
                            _tr("Marca el área del plano arrastrando sobre la hoja."))

    def _accept_selection(self):
        rect = self.view._selection
        if not self._valid(rect):
            return
        full = self.view._page_rect
        self.result_crop = [rect.left() / full.width(), rect.top() / full.height(),
                            rect.right() / full.width(), rect.bottom() / full.height()]
        self.accept()

    def _valid(self, rect):
        full = self.view._page_rect
        return (rect is not None
                and rect.width() >= 2
                and rect.height() >= 2)

    def _accept_full(self):
        self.result_crop = [0.0, 0.0, 1.0, 1.0]
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, lambda: self.view.fitInView(
            self.view.sceneRect(), QtCore.Qt.KeepAspectRatio))


def choose_sheet_crop(parent, page, title, current=None):
    dialog = SheetCropDialog(parent, page, title, current)
    return dialog.result_crop if dialog.exec() == QtWidgets.QDialog.Accepted else None
