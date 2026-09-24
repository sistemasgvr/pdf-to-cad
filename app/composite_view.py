"""composite_view.py — Lienzo del compositor: piezas arrastrables con imán.

`CompositeView` dibuja cada `composite.Piece` como un pixmap (el clip de su
hoja origen) colocado en coordenadas de la hoja compuesta (pt). Las piezas se
arrastran con el botón izquierdo; con el imán activo, mientras se arrastra la
pieza salta para que los extremos de sus líneas coincidan con los de la pieza
vecina (`magnet_delta`) o, si se deja un hueco, queden en línea con ellos
(`collinear_delta`). Los extremos (anclajes) y los puentes que los unirán se
dibujan encima como guía.

Al hacer zoom, la parte VISIBLE de cada pieza se re-renderiza nítida encima
de su imagen base (hijo del item, así se mueve con ella), con tope de píxeles
repartido entre las piezas a la vista. Las franjas blancas de `Piece.covers`
(tapan la línea de borde) y el contorno son también hijos del item.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

import composite as C
import composite_seam as S
from pdf_view_quality import MAX_RENDER_PIXELS, MAX_RENDER_SCALE, render_region
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
        self._sharp: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self._sharp_key = None
        self._covers: List[QtWidgets.QGraphicsItem] = []
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable
                      | QtWidgets.QGraphicsItem.ItemIsSelectable
                      | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setShapeMode(QtWidgets.QGraphicsPixmapItem.BoundingRectShape)
        self.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        # contorno como hijo con z alto: queda sobre el recorte nítido y las franjas
        self._outline = QtWidgets.QGraphicsRectItem(self)
        self._outline.setZValue(10)
        self._outline.setAcceptedMouseButtons(QtCore.Qt.NoButton)

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
        self._outline.setRect(QtCore.QRectF(0, 0, pm.width(), pm.height()))
        self._refresh_outline()
        self._refresh_covers()
        self.clear_sharp()

    def _refresh_outline(self):
        pen = QtGui.QPen(QtGui.QColor("#2b6fd1") if self.isSelected() else QtGui.QColor(255, 154, 0, 200), 0)
        pen.setCosmetic(True)
        pen.setWidth(3 if self.isSelected() else 1)
        self._outline.setPen(pen)
        self._outline.setBrush(QtCore.Qt.NoBrush)

    # ── coords: escena ↔ píxeles del pixmap base ─────────────────────────
    def scene_to_raw(self, x: float, y: float) -> QtCore.QPointF:
        t, _ = self.transform().inverted()
        return t.map(QtCore.QPointF(x - self.pos().x(), y - self.pos().y()))

    def _refresh_covers(self):
        for it in self._covers:
            it.setParentItem(None)
            if it.scene():
                it.scene().removeItem(it)
        self._covers = []
        p = self.piece
        for poly in C.cover_polygons(p, self.view.page_size(p), self.view.comp.target_scale()):
            qp = QtGui.QPolygonF([self.scene_to_raw(x, y) for x, y in poly])
            it = QtWidgets.QGraphicsPolygonItem(qp, self)
            it.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
            it.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            it.setZValue(6)                     # sobre el recorte nítido (5), bajo el contorno (10)
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            self._covers.append(it)

    # ── recorte nítido de la parte visible ───────────────────────────────
    def clear_sharp(self):
        if self._sharp is not None:
            self._sharp.setParentItem(None)
            if self._sharp.scene():
                self._sharp.scene().removeItem(self._sharp)
            self._sharp = None
            self._sharp_key = None

    def update_sharp(self, visible_scene: QtCore.QRectF, wanted: float, pixel_budget: float):
        """Pone (o actualiza) el recorte nítido de la parte de la pieza que se ve.
        `wanted`: px de pantalla por pt de la hoja compuesta; `pixel_budget`: px
        máximos para esta pieza."""
        p = self.piece
        region = visible_scene.intersected(self.sceneBoundingRect())
        if region.isEmpty():
            self.clear_sharp(); return
        pad = 0.2 * max(region.width(), region.height())
        region = region.adjusted(-pad, -pad, pad, pad).intersected(self.sceneBoundingRect())
        target = self.view.comp.target_scale()
        f = C.piece_factor(p, target)
        # la región de escena → rect en la hoja origen (visible), acotado al clip
        unmap = C.piece_unmap(p, self.view.page_size(p), target)
        pts = [unmap(region.left(), region.top()), unmap(region.right(), region.top()),
               unmap(region.right(), region.bottom()), unmap(region.left(), region.bottom())]
        cx0, cy0, cx1, cy1 = C.clip_rect_pt(self.view.page_size(p), p.clip)
        sx0 = max(cx0, min(q[0] for q in pts)); sx1 = min(cx1, max(q[0] for q in pts))
        sy0 = max(cy0, min(q[1] for q in pts)); sy1 = min(cy1, max(q[1] for q in pts))
        if sx1 - sx0 < 1e-3 or sy1 - sy0 < 1e-3:
            self.clear_sharp(); return
        scale = min(MAX_RENDER_SCALE, wanted * f, (pixel_budget / max(1.0, (sx1 - sx0) * (sy1 - sy0))) ** 0.5)
        if scale < self.ov * 1.4:
            self.clear_sharp(); return
        key = (round(sx0, 1), round(sy0, 1), round(sx1, 1), round(sy1, 1), round(scale, 2))
        if self._sharp is not None and key == self._sharp_key:
            return
        pm = render_region(self.view.page(p), (sx0, sy0, sx1, sy1), scale)
        if pm is None or pm.isNull():
            return
        if abs(p.rotation % 360.0) > 1e-9:
            pm = pm.transformed(QtGui.QTransform().rotate(-p.rotation), QtCore.Qt.SmoothTransformation)
        # caja del recorte en escena → en píxeles del pixmap base (coords del padre)
        fn = C.piece_map(p, self.view.page_size(p), target)
        sc = [fn(sx0, sy0), fn(sx1, sy0), fn(sx1, sy1), fn(sx0, sy1)]
        raw = [self.scene_to_raw(x, y) for x, y in sc]
        rx0 = min(q.x() for q in raw); rx1 = max(q.x() for q in raw)
        ry0 = min(q.y() for q in raw); ry1 = max(q.y() for q in raw)
        self.clear_sharp()
        it = QtWidgets.QGraphicsPixmapItem(pm, self)
        it.setTransformationMode(QtCore.Qt.SmoothTransformation)
        it.setZValue(5)
        it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        it.setPos(rx0, ry0)
        it.setTransform(QtGui.QTransform().scale((rx1 - rx0) / pm.width(), (ry1 - ry0) / pm.height()))
        self._sharp = it
        self._sharp_key = key

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
            self._refresh_outline()
            self.view.selectionChangedIdx.emit(cur)
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        option.state &= ~QtWidgets.QStyle.State_Selected      # sin el marco punteado de Qt
        super().paint(painter, option, widget)


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
        self._seam_cache: Dict[tuple, object] = {}          # (…, lado) → extremos de la match line
        self._segs_cache: Dict[tuple, object] = {}          # (pdf, hoja) → segmentos rectos de la hoja
        self._bridges: List[C.Bridge] = []
        self._overlay: List[QtWidgets.QGraphicsItem] = []
        self._bridge_timer = QtCore.QTimer(self)
        self._bridge_timer.setSingleShot(True)
        self._bridge_timer.setInterval(120)
        self._bridge_timer.timeout.connect(self.refresh_overlay)
        self.pieceMoved.connect(lambda _i: self._bridge_timer.start())
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._update_quality)
        self.viewChanged.connect(self._timer.start)
        self.pieceMoved.connect(lambda _i: self._timer.start())
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
        self._timer.start()
        # La match line de cada lado se calcula ya (tras pintar), no en el primer
        # arrastre que junta dos piezas: ahí la UI se trababa un momento.
        QtCore.QTimer.singleShot(0, self._warm_seams)

    def _warm_seams(self):
        if not self.pieces_ready() or any(getattr(d, "is_closed", False) for d in self.docs):
            return
        for i in range(len(self.comp.pieces)):
            for side in ("left", "right", "top", "bottom"):
                self._seam_line(i, side)
                self._rule(i, side)

    def refresh_piece(self, index: int, rerender: bool = False):
        it = self.items[index]
        if rerender:
            ov = self.overview_scale(it.piece)
            it.set_raw(self.render_piece(it.piece, ov), ov)
            self._edge_cache.pop(self._anchor_key(it.piece), None)
        else:
            it.refresh()
        self._update_scene_rect()
        self._bridge_timer.start()
        self._timer.start()

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
        return (p.source, p.page, tuple(round(v, 9) for v in p.clip),
                tuple(sorted((k, round(v, 3)) for k, v in p.covers.items())))

    def _anchors(self, index: int) -> List[C.Anchor]:
        p = self.comp.pieces[index]
        key = self._anchor_key(p)
        if key not in self._edge_cache:
            try:
                self._edge_cache[key] = C.edge_anchors(self.page(p), p.clip, insets=p.covers)
            except Exception:
                self._edge_cache[key] = []
        return self._edge_cache[key]

    def _piece_rect(self, index: int, at: Optional[C.Pt] = None):
        p = self.comp.pieces[index]
        if at is not None:
            p = C.Piece(**{**p.to_dict(), "x": at[0], "y": at[1]})
        return C.piece_rect(p, self.page_size(p), self.comp.target_scale())

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
        #    Los anclajes del borde interior de una franja NO cuentan: pegarlos
        #    solaparía las piezas (ese lado lo une el imán borde con borde).
        d = C.coincide_delta([m for m in moving if m.on_edge and not m.inset],
                             [s for s in static if s.on_edge and not s.inset], tol)
        if d is not None:
            # …pero la costura manda igual: dos extremos que coinciden pueden ser
            # el guión equivocado (la línea es discontinua), y la match line del
            # plano es evidencia exacta.
            return self._seam_align(index, (pos[0] + d[0], pos[1] + d[1]))
        # 2) borde con borde (los rectángulos de las piezas se tocan) + alineación
        #    lateral por los extremos enfrentados (que con franjas quedan por dentro).
        statics = [self._piece_rect(j) for j in range(len(self.comp.pieces)) if j != index]
        e = C.edge_snap_delta(self._piece_rect(index, pos), statics, tol)
        if e is not None:
            pos = (pos[0] + e[0], pos[1] + e[1])
            moving = self._mapped_anchors(index, pos)
        # 3) extremos enfrentados con hueco — solo alinea lateralmente. Tras un
        #    imán borde con borde, solo A LO LARGO de la costura (el otro eje ya
        #    está clavado; una línea algo inclinada no debe despegar los bordes).
        d = C.collinear_delta(moving, static, tol, self.comp.bridge_max_pt)
        if d is not None:
            if e is not None and e[0] != 0.0:
                d = (0.0, d[1])
            elif e is not None and e[1] != 0.0:
                d = (d[0], 0.0)
            pos = (pos[0] + d[0], pos[1] + d[1])
        elif e is None:
            return None
        # 4) ajuste fino por mínimos cuadrados con TODAS las parejas: las líneas
        #    inclinadas fijan también la normal de la costura (centésimas de pt).
        moving = self._mapped_anchors(index, pos)
        fx, fy = C.refine_delta(moving, static, 1.5, self.comp.bridge_max_pt)
        if fx is not None and abs(fx) <= 1.0:
            pos = (pos[0] + fx, pos[1])
        if fy is not None and abs(fy) <= 1.0:
            pos = (pos[0], pos[1] + fy)
        # 5) costura por TINTA: dos hojas de un plano comparten la match line, así
        #    que la franja de dibujo a cada lado es la misma. Si las piezas quedaron
        #    borde con borde, se corre la de arriba A LO LARGO de la costura hasta
        #    que las dos huellas de tinta coinciden. Esto arregla el caso en que
        #    cada hoja se recortó con un margen distinto (el imán de líneas del
        #    panel 2 engancha guías distintas) y no hay extremos enfrentados que
        #    guíen al imán: el desfase quedaba tal cual.
        pos = self._seam_align(index, pos)
        return pos

    def _seam_align(self, index: int, pos: C.Pt) -> C.Pt:
        """Alinea la pieza A LO LARGO de la costura con los extremos enfrentados.

        El imán normal solo llega a su radio (12 px de pantalla); si cada hoja se
        recortó con un margen distinto, al pegar los bordes queda un desfase de
        decenas de pt que hay que cerrar con la evidencia del dibujo: los
        extremos de línea que se miran de frente a un lado y otro de la costura.
        """
        rect = self._piece_rect(index, pos)
        for j in range(len(self.comp.pieces)):
            if j == index:
                continue
            other = self._piece_rect(j)
            right = abs(rect[0] - other[2]) <= 1.5       # la que se mueve va a la derecha
            left = abs(other[0] - rect[2]) <= 1.5
            below = abs(rect[1] - other[3]) <= 1.5
            above = abs(other[1] - rect[3]) <= 1.5
            vert = min(rect[3], other[3]) - max(rect[1], other[1])
            horz = min(rect[2], other[2]) - max(rect[0], other[0])
            if (right or left) and vert > 0.3 * (rect[3] - rect[1]):
                axis, side_m, side_o = 1, ("left" if right else "right"), ("right" if right else "left")
            elif (below or above) and horz > 0.3 * (rect[2] - rect[0]):
                axis, side_m, side_o = 0, ("top" if below else "bottom"), ("bottom" if below else "top")
            else:
                continue
            # 0º costura EXACTA por el dibujo (composite_seam): las dos match lines
            #    coinciden a través y los vectores que ambas hojas comparten fijan
            #    el desplazamiento a lo largo. Sin evidencia sigue como siempre.
            exact = self._seam_exact(index, j, pos, axis, side_m, side_o)
            if exact is not None:
                pos, done = exact
                if done:
                    return pos
            # 1º la MATCH LINE: las dos hojas dibujan la misma raya de la costura,
            #    así que sus extremos dan el desplazamiento exacto.
            d = C.seam_line_delta(self._seam_line(j, side_o), self._seam_line(index, side_m, pos))
            if d is None:
                # 2º los extremos de línea enfrentados (necesita ≥3 de acuerdo)
                d = C.seam_along_delta(self._mapped_anchors(index, pos), self._mapped_anchors(j), axis)
            if d is None or abs(d) > C.SEAM_ALONG_TOL_PT:
                if exact is not None:
                    return pos                  # al menos las match lines, a través
                continue
            pos = (pos[0], pos[1] + d) if axis == 1 else (pos[0] + d, pos[1])
            if exact is not None:
                # la match line va algo inclinada: el «a través» depende de dónde
                # quedó la pieza a lo largo → recalcularlo ya corrida
                again = self._seam_exact(index, j, pos, axis, side_m, side_o)
                if again is not None:
                    pos = again[0]
            return pos
        return pos

    def _lines(self, p: C.Piece):
        key = (p.source, p.page, "lines")
        if key not in self._segs_cache:
            self._segs_cache[key] = S.page_lines(self.page(p))
        return self._segs_cache[key]

    def _clip_pt(self, p: C.Piece):
        return C.clip_rect_pt(self.page_size(p), p.clip)

    def _rule(self, index: int, side: str) -> Optional[S.SeamRule]:
        """Match line (recta ajustada, la más gruesa) junto a ese lado de la pieza."""
        p = self.comp.pieces[index]
        key = self._anchor_key(p) + (side, "rule")
        if key not in self._seam_cache:
            try:
                self._seam_cache[key] = S.seam_rule(self._lines(p), self._clip_pt(p), side)
            except Exception:
                self._seam_cache[key] = None
        return self._seam_cache[key]

    def _votes(self, i_o: int, side_o: str, i_m: int, side_m: str):
        """Traslaciones de los vectores idénticos de las dos hojas junto a la costura."""
        po, pm = self.comp.pieces[i_o], self.comp.pieces[i_m]
        key = (self._anchor_key(po), side_o, self._anchor_key(pm), side_m, "votes")
        if key not in self._seam_cache:
            try:
                bo = S.band_segments(self._lines(po), self._clip_pt(po), side_o, rule=self._rule(i_o, side_o))
                bm = S.band_segments(self._lines(pm), self._clip_pt(pm), side_m, rule=self._rule(i_m, side_m))
                self._seam_cache[key] = S.seam_votes(bo, bm)
            except Exception:
                self._seam_cache[key] = []
        return self._seam_cache[key]

    def _crossing_votes(self, i_o: int, side_o: str, i_m: int, side_m: str):
        """Parejas de cruces de la match line (misma capa y rumbo) de las dos piezas."""
        po, pm = self.comp.pieces[i_o], self.comp.pieces[i_m]
        key = (self._anchor_key(po), side_o, self._anchor_key(pm), side_m, "cross")
        if key not in self._seam_cache:
            try:
                co = S.rule_crossings(self._lines(po), self._clip_pt(po), side_o, self._rule(i_o, side_o))
                cm = S.rule_crossings(self._lines(pm), self._clip_pt(pm), side_m, self._rule(i_m, side_m))
                self._seam_cache[key] = S.crossing_votes(co, cm)
            except Exception:
                self._seam_cache[key] = []
        return self._seam_cache[key]

    def _seam_exact(self, index: int, j: int, pos: C.Pt, axis: int, side_m: str, side_o: str):
        """Costura por el dibujo: (posición, completa) o None si no hay evidencia.
        `completa` = también quedó fijada a lo largo (si no, sigue el imán de
        siempre solo para ese eje)."""
        po, pm = self.comp.pieces[j], self.comp.pieces[index]
        target = self.comp.target_scale()
        if not S.comparable(po, pm, target):
            return None
        rule_o, rule_m = self._rule(j, side_o), self._rule(index, side_m)
        if not S.rules_match(rule_o, rule_m):
            return None
        pm_at = C.Piece(**{**pm.to_dict(), "x": pos[0], "y": pos[1]})
        size_o, size_m = self.page_size(po), self.page_size(pm)
        t_cur = S.current_translation(po, size_o, pm_at, size_m, target)
        x0, y0, x1, y1 = self._clip_pt(po)
        s_mid = (y0 + y1) / 2.0 if axis == 1 else (x0 + x1) / 2.0
        along = t_cur[axis]
        across = S.rule_across(rule_o, rule_m, s_mid, along)
        if abs(across - t_cur[1 - axis]) > S.SEAM_RULE_MAX_SHIFT_PT:
            return None
        found = S.translation_from_votes(self._votes(j, side_o, index, side_m), axis, across,
                                         along, C.SEAM_ALONG_TOL_PT)
        if found is not None:
            along, across = found
        else:
            # sin dibujo compartido: continuidad de las líneas que cruzan la costura
            cont = S.along_from_crossings(self._crossing_votes(j, side_o, index, side_m),
                                          along, C.SEAM_ALONG_TOL_PT)
            if cont is not None:
                along = cont
                across = S.rule_across(rule_o, rule_m, s_mid, along)
                found = (along, across)
        t = (across, along) if axis == 1 else (along, across)
        return S.pos_for_translation(po, size_o, pm_at, size_m, target, t), found is not None

    def _seam_line(self, index: int, side: str, at: Optional[C.Pt] = None):
        """Extremos de la match line de ese lado, en coords de la hoja compuesta.
        `seam_line_extent` los da relativos al origen de la pieza, así que la
        caché vale para cualquier posición."""
        p = self.comp.pieces[index]
        key = self._anchor_key(p) + (side, "seamline")
        if key not in self._seam_cache:
            try:
                skey = (p.source, p.page)
                if skey not in self._segs_cache:
                    self._segs_cache[skey] = C.page_segments(self.page(p))
                self._seam_cache[key] = C.seam_line_extent(
                    self.page(p), p, self.page_size(p), self.comp.target_scale(), side,
                    segments=self._segs_cache[skey])
            except Exception:
                self._seam_cache[key] = None
        ext = self._seam_cache[key]
        if ext is None:
            return None
        pos = at if at is not None else (p.x, p.y)
        base = pos[1] if side in ("left", "right") else pos[0]
        return (base + ext[0], base + ext[1])

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
            pts = b.polyline(self._piece_rect(b.piece_a), self._piece_rect(b.piece_b))
            path = QtGui.QPainterPath(QtCore.QPointF(*pts[0]))
            for q in pts[1:]:
                path.lineTo(QtCore.QPointF(*q))
            ln = self.scene().addPath(path, pen_b)
            ln.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            ln.setZValue(19)
            self._overlay.append(ln)
        self.bridgesChanged.emit(len(self._bridges))

    # ── nitidez al hacer zoom (todas las piezas a la vista) ─────────────
    def _update_quality(self):
        if not self.docs or any(getattr(d, "is_closed", False) for d in self.docs):
            return                                    # el diálogo ya cerró sus PDFs (temporizador pendiente)
        if not self.pieces_ready():
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        screen = abs(self.transform().m11()) * self.devicePixelRatioF()
        wanted = screen * 1.15                          # px de pantalla por pt de la hoja compuesta
        shown = [it for it in self.items if it.sceneBoundingRect().intersects(visible)]
        for it in self.items:
            if it not in shown:
                it.clear_sharp()
        if not shown:
            return
        budget = MAX_RENDER_PIXELS / len(shown)
        for it in shown:
            it.update_sharp(visible, wanted, budget)

    # ── ratón ───────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            it = self.itemAt(e.position().toPoint())
            if it is None:
                self.scene().clearSelection()
                self.selectionChangedIdx.emit(-1)
        super().mousePressEvent(e)
