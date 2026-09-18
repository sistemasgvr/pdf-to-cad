"""composite_view.py — Lienzo del compositor: piezas arrastrables con imán.

`CompositeView` dibuja cada `composite.Piece` como un pixmap (el clip de su
hoja origen) colocado en coordenadas de la hoja compuesta (pt). Las piezas se
arrastran con el botón izquierdo; con el imán activo, mientras se arrastra la
pieza salta para que los extremos de sus líneas coincidan con los de la pieza
vecina (`magnet_delta`) o, si se deja un hueco, queden en línea con ellos
(`collinear_delta`). Los extremos (anclajes) y los puentes que los unirán se
dibujan encima como guía.

Al hacer zoom, la pieza bajo el centro de la vista se re-renderiza más nítida
(misma idea que pdf_view_quality, pero por pieza y sin slots).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

import composite as C
from pdf_view_quality import render_scale
from widgets import ZoomPanView


def _qpixmap(pix: fitz.Pixmap) -> QtGui.QPixmap:
    img = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                       pix.stride, QtGui.QImage.Format_RGB888).copy()
    return QtGui.QPixmap.fromImage(img)


class PieceItem(QtWidgets.QGraphicsPixmapItem):
    """Una pieza en el lienzo. `pixmap` es el clip SIN girar a `ov` px/pt; el
    giro y la escala van en la transformación del item."""

    def __init__(self, index: int, view: "CompositeView"):
        super().__init__()
        self.index = index
        self.view = view
        self.ov = 1.0
        self._raw: Optional[QtGui.QPixmap] = None
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable
                      | QtWidgets.QGraphicsItem.ItemIsSelectable
                      | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setShapeMode(QtWidgets.QGraphicsPixmapItem.BoundingRectShape)
        self.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.setCursor(QtCore.Qt.OpenHandCursor)

    @property
    def piece(self) -> C.Piece:
        return self.view.comp.pieces[self.index]

    def set_raw(self, pixmap: QtGui.QPixmap, ov: float):
        self._raw, self.ov = pixmap, ov
        self.refresh()

    def refresh(self):
        """Reaplica giro, escala y posición desde el modelo."""
        if self._raw is None:
            return
        p = self.piece
        pm = self._raw
        if abs(p.rotation % 360.0) > 1e-9:
            # Qt gira horario con ángulo positivo; el modelo es antihorario.
            pm = pm.transformed(QtGui.QTransform().rotate(-p.rotation),
                                QtCore.Qt.SmoothTransformation)
        super().setPixmap(pm)
        f = C.piece_factor(p, self.view.comp.target_scale())
        w, h = C.piece_size(p, self.view.page_size(p), self.view.comp.target_scale())
        # El pixmap girado puede diferir en ±1 px de la caja teórica: escalar por eje.
        sx = w / pm.width() if pm.width() else f / self.ov
        sy = h / pm.height() if pm.height() else f / self.ov
        self.setTransform(QtGui.QTransform().scale(sx, sy))
        self._syncing = True
        self.setPos(p.x, p.y)
        self._syncing = False

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and not getattr(self, "_syncing", False):
            pos = value
            if self.view.magnet_enabled and self.view.pieces_ready():
                snapped = self.view.snap_position(self.index, (pos.x(), pos.y()))
                if snapped is not None:
                    pos = QtCore.QPointF(*snapped)
            return pos
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged and not getattr(self, "_syncing", False):
            p = self.piece
            p.x, p.y = float(value.x()), float(value.y())
            self.view.pieceMoved.emit(self.index)
        if change == QtWidgets.QGraphicsItem.ItemSelectedHasChanged:
            # Índice seleccionado RESULTANTE (al cambiar de pieza, Qt deselecciona
            # la anterior después de seleccionar la nueva: no debe "borrar" la nueva).
            cur = self.index if value else self.view.selected_index(exclude=self.index)
            self.view.selectionChangedIdx.emit(cur)
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        pen = QtGui.QPen(QtGui.QColor("#2b6fd1") if self.isSelected() else QtGui.QColor(255, 154, 0, 200), 0)
        pen.setCosmetic(True)
        pen.setWidth(3 if self.isSelected() else 1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(self.boundingRect())


class CompositeView(ZoomPanView):
    pieceMoved = QtCore.Signal(int)
    selectionChangedIdx = QtCore.Signal(int)
    bridgesChanged = QtCore.Signal(int)

    def __init__(self, comp: C.Composite, docs: List[fitz.Document]):
        super().__init__()
        self.comp = comp
        self.docs = docs
        self.magnet_enabled = True
        self.show_anchors = True
        self.items: List[PieceItem] = []
        self._edge_cache: Dict[tuple, List[C.Anchor]] = {}  # (pdf, hoja, clip) → anclajes (coords hoja origen)
        self._bridges: List[C.Bridge] = []
        self._overlay: List[QtWidgets.QGraphicsItem] = []
        self._bridge_timer = QtCore.QTimer(self)
        self._bridge_timer.setSingleShot(True)
        self._bridge_timer.setInterval(120)
        self._bridge_timer.timeout.connect(self.refresh_overlay)
        self.pieceMoved.connect(lambda _i: self._bridge_timer.start())
        self._sharp_index: Optional[int] = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._update_quality)
        self.viewChanged.connect(self._timer.start)
        self.setBackgroundBrush(QtGui.QColor("#d8dbe0"))
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)

    # ── modelo ──────────────────────────────────────────────────────────
    def page(self, p: C.Piece) -> fitz.Page:
        return self.docs[p.source][p.page]

    def page_size(self, p: C.Piece):
        r = self.page(p).rect
        return r.width, r.height

    def pieces_ready(self) -> bool:
        return len(self.items) == len(self.comp.pieces)

    def overview_scale(self, p: C.Piece) -> float:
        x0, y0, x1, y1 = C.clip_rect_pt(self.page_size(p), p.clip)
        longest = max(x1 - x0, y1 - y0, 1.0)
        return min(1.0, 1400.0 / longest)

    def render_piece(self, p: C.Piece, scale: float) -> QtGui.QPixmap:
        page = self.page(p)
        x0, y0, x1, y1 = C.clip_rect_pt(self.page_size(p), p.clip)
        clip = fitz.Rect(page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, clip=clip)
        return _qpixmap(pix)

    def rebuild(self, keep_selection: int = -1):
        """Vuelve a crear todos los items desde `self.comp`."""
        self._sharp_index = None
        for it in self.items:
            self.scene().removeItem(it)
        self.items = []
        for i, p in enumerate(self.comp.pieces):
            it = PieceItem(i, self)
            self.scene().addItem(it)
            ov = self.overview_scale(p)
            it.set_raw(self.render_piece(p, ov), ov)
            self.items.append(it)
        self._update_scene_rect()
        if 0 <= keep_selection < len(self.items):
            self.items[keep_selection].setSelected(True)
        self.refresh_overlay()

    def refresh_piece(self, index: int, rerender: bool = False):
        it = self.items[index]
        if rerender:
            ov = self.overview_scale(it.piece)
            it.set_raw(self.render_piece(it.piece, ov), ov)
            self._edge_cache.pop(self._anchor_key(it.piece), None)
        else:
            it.refresh()
        if self._sharp_index == index:
            self._sharp_index = None
        self._update_scene_rect()
        self._bridge_timer.start()

    def refresh_all(self):
        for i in range(len(self.items)):
            self.refresh_piece(i)

    def rerender_source(self, source: int):
        """Tras cambiar capas de un PDF origen: nuevos pixmaps de sus piezas."""
        for i, p in enumerate(self.comp.pieces):
            if p.source == source:
                self.refresh_piece(i, rerender=True)
        self._bridge_timer.stop()
        self.refresh_overlay()

    def _update_scene_rect(self):
        bb = C.bounds(self.comp, self.page_size)
        if bb is None:
            self.setSceneRect(QtCore.QRectF(0, 0, 800, 600))
            return
        x0, y0, x1, y1 = bb
        pad = max(200.0, 0.5 * max(x1 - x0, y1 - y0))
        self.setSceneRect(QtCore.QRectF(x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad))

    def fit_all(self):
        bb = C.bounds(self.comp, self.page_size)
        if bb is None:
            return
        x0, y0, x1, y1 = bb
        m = 0.05 * max(x1 - x0, y1 - y0, 1.0)
        self.fitInView(QtCore.QRectF(x0 - m, y0 - m, (x1 - x0) + 2 * m, (y1 - y0) + 2 * m),
                       QtCore.Qt.KeepAspectRatio)
        self.viewChanged.emit()

    def selected_index(self, exclude: int = -1) -> int:
        for it in self.items:
            if it.isSelected() and it.index != exclude:
                return it.index
        return -1

    def select(self, index: int):
        for it in self.items:                 # primero soltar las demás, luego la pedida
            if it.index != index:
                it.setSelected(False)
        for it in self.items:
            if it.index == index:
                it.setSelected(True)

    # ── imán / anclajes / puentes ──────────────────────────────────────
    @staticmethod
    def _anchor_key(p: C.Piece) -> tuple:
        return (p.source, p.page, tuple(round(v, 9) for v in p.clip))

    def _anchors(self, index: int) -> List[C.Anchor]:
        p = self.comp.pieces[index]
        key = self._anchor_key(p)
        if key not in self._edge_cache:
            try:
                self._edge_cache[key] = C.edge_anchors(self.page(p), p.clip)
            except Exception:
                self._edge_cache[key] = []
        return self._edge_cache[key]

    def _edge_points(self, index: int) -> List[C.Pt]:
        return [a.xy for a in self._anchors(index)]

    def _mapped_anchors(self, index: int, at: Optional[C.Pt] = None) -> List[C.Anchor]:
        p = self.comp.pieces[index]
        return C.map_anchors(p, self.page_size(p), self.comp.target_scale(), self._anchors(index), at)

    def _mapped_points(self, index: int, at: Optional[C.Pt] = None) -> List[C.Pt]:
        return [a.xy for a in self._mapped_anchors(index, at)]

    def snap_position(self, index: int, pos: C.Pt) -> Optional[C.Pt]:
        moving = self._mapped_anchors(index, pos)
        if not moving:
            return None
        static: List[C.Anchor] = []
        for j in range(len(self.comp.pieces)):
            if j != index:
                static.extend(self._mapped_anchors(j))
        if not static:
            return None
        # tolerancia en pantalla (~12 px) convertida a pt de la hoja compuesta
        zoom = abs(self.transform().m11()) or 1.0
        tol = max(C.MAGNET_TOL_PT, 12.0 / zoom)
        # 1) extremos que coinciden (piezas que se tocan) — fija x e y. Solo los
        #    que están EN el borde: uno que muere por dentro no debe solapar piezas.
        d = C.magnet_delta([m.xy for m in moving if m.on_edge], [s.xy for s in static if s.on_edge], tol)
        # 2) extremos enfrentados con hueco — solo alinea lateralmente
        if d is None:
            d = C.collinear_delta(moving, static, tol, self.comp.bridge_max_pt)
        if d is None:
            return None
        return pos[0] + d[0], pos[1] + d[1]

    def bridges(self) -> List[C.Bridge]:
        return list(self._bridges)

    def refresh_overlay(self):
        """Recalcula puentes y redibuja anclajes/puentes sobre las piezas."""
        for it in self._overlay:
            self.scene().removeItem(it)
        self._overlay = []
        if not self.pieces_ready():
            self._bridges = []
            return
        by_piece = {i: self._mapped_anchors(i) for i in range(len(self.comp.pieces))}
        self._bridges = (C.find_bridges(by_piece, self.comp.bridge_max_pt)
                         if self.comp.bridges and len(self.comp.pieces) > 1 else [])
        bridged = {(b.piece_a, b.a) for b in self._bridges} | {(b.piece_b, b.b) for b in self._bridges}
        if self.show_anchors:
            pen_free = QtGui.QPen(QtGui.QColor("#d9480f"), 0); pen_free.setCosmetic(True)
            pen_ok = QtGui.QPen(QtGui.QColor("#0b7a3b"), 0); pen_ok.setCosmetic(True)
            for i, anchors in by_piece.items():
                for a in anchors:
                    joined = (i, a.xy) in bridged
                    dot = self.scene().addEllipse(-3, -3, 6, 6, pen_ok if joined else pen_free,
                                                  QtGui.QBrush(QtGui.QColor("#0b7a3b" if joined else "#d9480f")))
                    dot.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
                    dot.setAcceptedMouseButtons(QtCore.Qt.NoButton)   # no roba el clic a la pieza
                    dot.setPos(a.x, a.y); dot.setZValue(20)
                    self._overlay.append(dot)
        pen_b = QtGui.QPen(QtGui.QColor("#0b7a3b"), 2); pen_b.setCosmetic(True)
        for b in self._bridges:
            ln = self.scene().addLine(b.a[0], b.a[1], b.b[0], b.b[1], pen_b)
            ln.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            ln.setZValue(19)
            self._overlay.append(ln)
        self.bridgesChanged.emit(len(self._bridges))

    # ── nitidez al hacer zoom ───────────────────────────────────────────
    def _focused_index(self) -> Optional[int]:
        centre = self.mapToScene(self.viewport().rect().center())
        for it in self.items:
            if it.sceneBoundingRect().contains(centre):
                return it.index
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        for it in self.items:
            if it.sceneBoundingRect().intersects(visible):
                return it.index
        return None

    def _update_quality(self):
        idx = self._focused_index()
        if idx is None or not self.pieces_ready():
            return
        it = self.items[idx]
        p = it.piece
        f = C.piece_factor(p, self.comp.target_scale())
        screen = abs(self.transform().m11()) * self.devicePixelRatioF()
        wanted = screen * f * 1.15                      # px de pantalla por pt de la hoja origen
        page = self.page(p)
        x0, y0, x1, y1 = C.clip_rect_pt(self.page_size(p), p.clip)
        clip = fitz.Rect(page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
        scale = render_scale(page, wanted, clip)
        base = self.overview_scale(p)
        if scale < base * 1.4:
            if self._sharp_index == idx:
                it.set_raw(self.render_piece(p, base), base)
                self._sharp_index = None
            return
        if self._sharp_index == idx and scale < it.ov * 1.3:
            return
        if self._sharp_index is not None and self._sharp_index != idx:
            prev = self.items[self._sharp_index]
            b = self.overview_scale(prev.piece)
            prev.set_raw(self.render_piece(prev.piece, b), b)
        it.set_raw(self.render_piece(p, scale), scale)
        self._sharp_index = idx

    # ── ratón ───────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            it = self.itemAt(e.position().toPoint())
            if it is None:
                self.scene().clearSelection()
                self.selectionChangedIdx.emit(-1)
        super().mousePressEvent(e)
