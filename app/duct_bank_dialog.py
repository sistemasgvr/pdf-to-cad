"""duct_bank_dialog.py — Diseñador de la sección del Duct Bank.

Diálogo grande (QDialog), diseñado para usuarios de +60 años:
  - Botones grandes con ícono + texto (no icon-only).
  - Grid visible cada 1", subgrid cada 0.25". Snap on por defecto.
  - Solo UNA herramienta activa a la vez (Seleccionar / Conducto / Rectángulo /
    Medir / Mover / Eliminar). El cursor y el estado del panel dicen qué modo.
  - Undo/Redo, Guardar/Abrir/Nuevo, Zoom con slider y botones ±, "Ajustar" para
    centrar la escena.
  - Toda la lógica de datos vive en `duct_bank.py` (testeada headless). Aquí solo
    va la UI.

Uso desde la ventana principal:
    from duct_bank_dialog import DuctBankDialog
    dlg = DuctBankDialog(win, initial=win.duct_bank_current)
    if dlg.exec() == QtWidgets.QDialog.Accepted:
        win.duct_bank_current = dlg.result()
"""
from __future__ import annotations
import copy
import json
import math
import os
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from duct_bank import (DuctBank, Conduit, DEFAULT_SNAP_IN,
                       snap, validate, conduit_fits_envelope)
import theme as _theme
from icons import icon as _icon


# ── Constantes visuales ─────────────────────────────────────────────────────
_INITIAL_PX_PER_IN = 60.0     # zoom inicial: 60 px = 1 pulgada
_MIN_ZOOM = 0.30
_MAX_ZOOM = 4.00
_GRID_MAJOR_IN = 1.0          # rejilla mayor cada 1"
_GRID_MINOR_IN = 0.25         # subrejilla cada 0.25"


# ── Colores derivados del tema ────────────────────────────────────────────
# Antes eran QColor constantes; ahora se resuelven contra `_theme.tokens()`
# cada vez que se pinta, así el diseñador sigue el modo claro/oscuro global.
def _envelope_border_color(): return QtGui.QColor(_theme.tokens().envelope_border)
def _envelope_fill_color(): return QtGui.QColor(_theme.tokens().envelope_fill)
def _conduit_border_color(): return QtGui.QColor(_theme.tokens().conduit_border)
def _conduit_fill_color(): return QtGui.QColor(_theme.tokens().conduit_fill)
def _conduit_text_color(): return QtGui.QColor(_theme.tokens().conduit_text)
def _selection_color(): return QtGui.QColor(_theme.tokens().selection)
def _invalid_color(): return QtGui.QColor(_theme.tokens().invalid)
def _grid_bg_color(): return QtGui.QColor(_theme.tokens().grid_bg)
def _grid_minor_color(): return QtGui.QColor(_theme.tokens().grid_line_minor)
def _grid_major_color(): return QtGui.QColor(_theme.tokens().grid_line_major)


# ── Rectángulo con esquinas redondeadas por-esquina ───────────────────────
def _rounded_rect_path(rect: QtCore.QRectF,
                        tl: float, tr: float, br: float, bl: float) -> QtGui.QPainterPath:
    """Devuelve un QPainterPath que traza un rectángulo con radios independientes
    en cada esquina (superior-izq, superior-der, inferior-der, inferior-izq).

    Cada radio se recorta a la mitad del lado más corto: evita que un valor muy
    grande "coma" la geometría cuando el rectángulo es pequeño.

    Se dibuja con arcos de 90°; los radios en cero producen una esquina en
    escuadra viva, así que el mismo código sirve para envolventes rectas y
    redondeadas."""
    x, y = rect.x(), rect.y()
    w, h = rect.width(), rect.height()
    lim = max(0.0, min(w, h) / 2.0)
    tl = max(0.0, min(tl, lim))
    tr = max(0.0, min(tr, lim))
    br = max(0.0, min(br, lim))
    bl = max(0.0, min(bl, lim))
    path = QtGui.QPainterPath()
    # Empezamos en la parte superior, justo después del arco TL.
    path.moveTo(x + tl, y)
    path.lineTo(x + w - tr, y)
    if tr > 0:
        path.arcTo(x + w - 2 * tr, y, 2 * tr, 2 * tr, 90, -90)
    path.lineTo(x + w, y + h - br)
    if br > 0:
        path.arcTo(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br, 0, -90)
    path.lineTo(x + bl, y + h)
    if bl > 0:
        path.arcTo(x, y + h - 2 * bl, 2 * bl, 2 * bl, -90, -90)
    path.lineTo(x, y + tl)
    if tl > 0:
        path.arcTo(x, y, 2 * tl, 2 * tl, 180, -90)
    path.closeSubpath()
    return path


def _build_btn_style() -> str:
    t = _theme.tokens()
    return (f"QToolButton{{background:{t.surface};border:1px solid {t.border};border-radius:6px;"
            f"padding:8px 4px;min-width:66px;min-height:66px;font-size:12px;color:{t.text};}}"
            f"QToolButton:hover{{background:{t.hover};}}"
            f"QToolButton:checked{{background:{t.accent};color:{t.text_on_accent};border-color:{t.accent_pressed};}}"
            f"QToolButton[danger='true']{{color:{t.danger};}}"
            f"QToolButton[danger='true']:checked{{background:{t.danger};color:{t.text_on_accent};border-color:{t.danger_hover};}}")


def _build_header_style() -> str:
    t = _theme.tokens()
    return (f"QPushButton{{background:{t.accent};color:{t.text_on_accent};border:none;border-radius:6px;"
            f"padding:10px 14px;font-size:13px;min-width:88px;font-weight:600;}}"
            f"QPushButton:hover{{background:{t.accent_hover};}}"
            f"QPushButton:disabled{{background:{t.border};color:{t.text_disabled};}}")


# ── Widget: editor de 4 valores estilo Photoshop ────────────────────────────
class _FourSideEditor(QtWidgets.QFrame):
    """Editor visual con 4 spinboxes dispuestos en un diseño espacial (compass
    o corners) más un botón de vincular ↔ desvincular al centro.

    - `layout_mode="compass"`: superior, derecho, inferior, izquierdo.
    - `layout_mode="corners"`: superior-izq, superior-der, inferior-der, inferior-izq.

    Cuando el botón de vincular está activo (link ON), cambiar cualquiera
    propaga a los cuatro. Emite `changed(top,right,bottom,left)` para compass o
    `changed(tl,tr,br,bl)` para corners cada vez que hay un cambio.
    """
    changed = QtCore.Signal(float, float, float, float)   # (top,right,bottom,left) o (tl,tr,br,bl)

    def __init__(self, parent=None, layout_mode="compass", maximum=100.0,
                 step=0.25, decimals=2, initial=0.0):
        super().__init__(parent)
        self._mode = layout_mode
        self._propagating = False
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        # Cuatro spinboxes idénticos: mismo rango, mismo step, sufijo pulgadas.
        def _sp():
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(0.0, maximum); s.setDecimals(decimals); s.setSingleStep(step)
            s.setSuffix('"'); s.setValue(initial)
            s.setMinimumWidth(62); s.setAlignment(QtCore.Qt.AlignCenter)
            return s
        # Los orden A/B/C/D representa la SEÑAL en el orden documentado del modo.
        # compass: A=top, B=right, C=bottom, D=left
        # corners: A=tl,  B=tr,   C=br,     D=bl
        self.sp_a = _sp(); self.sp_b = _sp(); self.sp_c = _sp(); self.sp_d = _sp()

        # Botón central de vincular. Empieza VINCULADO por defecto (uniforme).
        self.btn_link = QtWidgets.QToolButton()
        self.btn_link.setCheckable(True); self.btn_link.setChecked(True)
        self.btn_link.setToolTip("Vincular los cuatro valores.\n"
                                  "Cuando está activado, cambiar uno los actualiza a los cuatro.")
        self.btn_link.setFixedSize(44, 44)
        self.btn_link.setIconSize(QtCore.QSize(22, 22))
        self.btn_link.toggled.connect(self._refresh_link_icon)
        self._refresh_link_icon()

        # Etiquetas cortas alrededor de cada spinbox
        if layout_mode == "corners":
            lbls = ("Sup. Izq.", "Sup. Der.", "Inf. Der.", "Inf. Izq.")
        else:
            lbls = ("Superior", "Derecho", "Inferior", "Izquierdo")
        def _labeled(sp, txt):
            box = QtWidgets.QVBoxLayout(); box.setSpacing(2); box.setContentsMargins(0, 0, 0, 0)
            lbl = QtWidgets.QLabel(txt); lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet(f"color:{_theme.tokens().text_muted};font-size:11px;")
            box.addWidget(lbl); box.addWidget(sp); return box

        # Layout espacial: 3x3 grid, spinboxes en cruz o esquinas.
        g = QtWidgets.QGridLayout(self); g.setContentsMargins(4, 4, 4, 4); g.setSpacing(6)
        if layout_mode == "corners":
            # [sp_a][   ][sp_b]
            # [   ][ 🔗 ][   ]
            # [sp_d][   ][sp_c]
            g.addLayout(_labeled(self.sp_a, lbls[0]), 0, 0)
            g.addLayout(_labeled(self.sp_b, lbls[1]), 0, 2)
            g.addWidget(self.btn_link, 1, 1, QtCore.Qt.AlignCenter)
            g.addLayout(_labeled(self.sp_c, lbls[2]), 2, 2)
            g.addLayout(_labeled(self.sp_d, lbls[3]), 2, 0)
        else:
            # [   ][sp_a][   ]
            # [sp_d][🔗 ][sp_b]
            # [   ][sp_c][   ]
            g.addLayout(_labeled(self.sp_a, lbls[0]), 0, 1)
            g.addLayout(_labeled(self.sp_b, lbls[1]), 1, 2)
            g.addWidget(self.btn_link, 1, 1, QtCore.Qt.AlignCenter)
            g.addLayout(_labeled(self.sp_c, lbls[2]), 2, 1)
            g.addLayout(_labeled(self.sp_d, lbls[3]), 1, 0)
        g.setColumnStretch(0, 1); g.setColumnStretch(2, 1)

        for s in (self.sp_a, self.sp_b, self.sp_c, self.sp_d):
            s.valueChanged.connect(self._on_any_changed)

        # Retinta el icono del link al cambiar tema.
        _theme.THEME_BUS.changed.connect(lambda *_: self._refresh_link_icon())

    def _refresh_link_icon(self, *_):
        t = _theme.tokens()
        if self.btn_link.isChecked():
            name, tip = "mdi:link-variant", "Vinculados (cambiar uno cambia los 4). Click para desvincular."
            bg = t.accent
            fg = t.text_on_accent
        else:
            name, tip = "mdi:link-variant-off", "Independientes. Click para vincularlos."
            bg = t.surface_alt
            fg = t.text
        self.btn_link.setIcon(_icon(name, color=fg))
        self.btn_link.setToolTip(tip)
        self.btn_link.setStyleSheet(
            f"QToolButton{{background:{bg};border:1px solid {t.border};border-radius:6px;}}"
            f"QToolButton:hover{{background:{t.accent_hover};border:1px solid {t.focus};}}")

    def _on_any_changed(self, v):
        if self._propagating:
            return
        if self.btn_link.isChecked():
            # Propagamos a los otros tres sin re-disparar el ciclo
            self._propagating = True
            try:
                for s in (self.sp_a, self.sp_b, self.sp_c, self.sp_d):
                    if s.value() != v: s.setValue(v)
            finally:
                self._propagating = False
        self.changed.emit(self.sp_a.value(), self.sp_b.value(),
                           self.sp_c.value(), self.sp_d.value())

    def set_values(self, a, b, c, d):
        """Fija los 4 valores sin emitir señales. Útil al cargar un proyecto."""
        self._propagating = True
        try:
            self.sp_a.setValue(float(a)); self.sp_b.setValue(float(b))
            self.sp_c.setValue(float(c)); self.sp_d.setValue(float(d))
            # Si los 4 son iguales, mantenemos link ON; si difieren, lo apagamos.
            uniform = (a == b == c == d)
            self.btn_link.setChecked(uniform)
            self._refresh_link_icon()
        finally:
            self._propagating = False


# ── Escena / vista ──────────────────────────────────────────────────────────
class _DuctBankScene(QtWidgets.QGraphicsScene):
    """Escena en coordenadas de PULGADAS. El eje Y va HACIA ABAJO (como en el
    lienzo principal): esto acepta un rectángulo con height positivo dibujado
    hacia abajo, coincidente con las reglas del mockup (0" arriba, 8" abajo).

    Emite señales cuando el modelo cambia para que el diálogo actualice el panel
    lateral y el botón Guardar."""
    changed_model = QtCore.Signal()
    selection_changed = QtCore.Signal()
    tool_hint = QtCore.Signal(str)
    conduit_double_clicked = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = DuctBank()
        self.tool = "select"                  # select | conduit | move | delete | measure
        self.snap_on = True
        self.snap_step = DEFAULT_SNAP_IN
        self.new_conduit_diam = 4.0
        self.selected_idx: Optional[int] = None    # índice del conducto seleccionado
        self.envelope_selected = False
        self._dragging_idx: Optional[int] = None   # para "Mover"
        self._drag_offset = QtCore.QPointF(0, 0)
        self._measure_pts: List[QtCore.QPointF] = []
        # Escena generosa: 50" × 30", centrada en (0,0).
        self.setSceneRect(-10, -10, 50, 30)

    # ── snapping ──────────────────────────────────────────────────────────
    def _snap_pt(self, p: QtCore.QPointF) -> QtCore.QPointF:
        if not self.snap_on:
            return p
        return QtCore.QPointF(snap(p.x(), self.snap_step), snap(p.y(), self.snap_step))

    def _magnetic_snap(self, p: QtCore.QPointF, radius: float = 0.5) -> QtCore.QPointF:
        """Además del snap a la rejilla, imanta el punto a candidatos "notables"
        cercanos: centros de conductos, líneas de guía y esquinas de la
        envolvente/margen. Usado por la herramienta MEDIR — así el usuario
        puede medir "de conducto a conducto" con precisión total, no ⅟₄ pulgada.
        Cae al snap normal si nada está dentro del radio (en pulgadas)."""
        best = None
        best_d2 = radius * radius
        d = self.model
        cx, cy = p.x(), p.y()
        # Centros de conductos
        for c in d.conduits:
            dd = (c.cx - cx) ** 2 + (c.cy - cy) ** 2
            if dd < best_d2:
                best_d2 = dd; best = (c.cx, c.cy)
        # Esquinas y aristas de la envolvente
        for ex in (0.0, d.width_in):
            for ey in (0.0, d.height_in):
                dd = (ex - cx) ** 2 + (ey - cy) ** 2
                if dd < best_d2:
                    best_d2 = dd; best = (ex, ey)
        # Líneas de la guía (proyecciones)
        if d.guide_show:
            gx, gy, gw, gh = d.inner_rect()
            if gw > 0 and gh > 0:
                cols = max(1, int(d.guide_cols)); rows = max(1, int(d.guide_rows))
                for i in range(cols + 1):
                    lx = gx + i * (gw / cols)
                    dd = (lx - cx) ** 2
                    if dd < best_d2:
                        best_d2 = dd; best = (lx, cy)
                for j in range(rows + 1):
                    ly = gy + j * (gh / rows)
                    dd = (ly - cy) ** 2
                    if dd < best_d2:
                        best_d2 = dd; best = (cx, ly)
        if best is not None:
            return QtCore.QPointF(best[0], best[1])
        # Fallback: snap normal a rejilla (o crudo si snap_on es False)
        return self._snap_pt(p)

    # ── búsqueda: qué hay bajo el puntero ─────────────────────────────────
    def _hit_conduit(self, p: QtCore.QPointF) -> Optional[int]:
        for i in range(len(self.model.conduits) - 1, -1, -1):   # top-most primero
            c = self.model.conduits[i]
            r = c.diam / 2.0
            if (p.x() - c.cx) ** 2 + (p.y() - c.cy) ** 2 <= r * r:
                return i
        return None

    def _hit_envelope_border(self, p: QtCore.QPointF, tol=0.15) -> bool:
        d = self.model
        if d.width_in <= 0 or d.height_in <= 0:
            return False
        # dentro pero cerca del borde
        near_l = abs(p.x()) < tol
        near_r = abs(p.x() - d.width_in) < tol
        near_t = abs(p.y()) < tol
        near_b = abs(p.y() - d.height_in) < tol
        inside_x = -tol <= p.x() <= d.width_in + tol
        inside_y = -tol <= p.y() <= d.height_in + tol
        return ((near_l or near_r) and inside_y) or ((near_t or near_b) and inside_x)

    # ── mouse ─────────────────────────────────────────────────────────────
    def mousePressEvent(self, e: QtWidgets.QGraphicsSceneMouseEvent):
        if e.button() != QtCore.Qt.LeftButton:
            return super().mousePressEvent(e)
        p = self._snap_pt(e.scenePos())

        if self.tool == "select":
            idx = self._hit_conduit(e.scenePos())
            if idx is not None:
                self.selected_idx = idx
                self.envelope_selected = False
            elif self._hit_envelope_border(e.scenePos()):
                self.selected_idx = None
                self.envelope_selected = True
            else:
                self.selected_idx = None
                self.envelope_selected = False
            self.selection_changed.emit()
            self.update()

        elif self.tool == "conduit":
            c = Conduit(cx=float(p.x()), cy=float(p.y()), diam=float(self.new_conduit_diam))
            if not conduit_fits_envelope(self.model, c):
                self.tool_hint.emit("El conducto queda fuera de la envolvente.")
                return
            self.model.conduits.append(c)
            self.selected_idx = len(self.model.conduits) - 1
            self.envelope_selected = False
            self.changed_model.emit(); self.selection_changed.emit(); self.update()

        elif self.tool == "move":
            idx = self._hit_conduit(e.scenePos())
            if idx is not None:
                self._dragging_idx = idx
                c = self.model.conduits[idx]
                self._drag_offset = QtCore.QPointF(e.scenePos().x() - c.cx, e.scenePos().y() - c.cy)

        elif self.tool == "delete":
            idx = self._hit_conduit(e.scenePos())
            if idx is not None:
                del self.model.conduits[idx]
                if self.selected_idx == idx:
                    self.selected_idx = None
                self.changed_model.emit(); self.selection_changed.emit(); self.update()

        elif self.tool == "measure":
            # La regla usa SNAP MAGNÉTICO: primero intenta pegarse a centros de
            # conductos / esquinas de envolvente / líneas de guía. Si nada está
            # cerca, cae al snap de rejilla normal — así "medir del conducto A
            # al B" da exactamente la distancia real, sin redondeo a 0.25".
            mp = self._magnetic_snap(e.scenePos())
            self._measure_pts.append(mp)
            if len(self._measure_pts) >= 2:
                a, b = self._measure_pts[-2], self._measure_pts[-1]
                dist = math.hypot(a.x() - b.x(), a.y() - b.y())
                self.tool_hint.emit(f"Distancia: {dist:.3f} pulgadas")
                if len(self._measure_pts) > 2:
                    self._measure_pts = self._measure_pts[-2:]
            self.update()

    def mouseMoveEvent(self, e: QtWidgets.QGraphicsSceneMouseEvent):
        if self.tool == "move" and self._dragging_idx is not None:
            p = self._snap_pt(e.scenePos() - self._drag_offset)
            c = self.model.conduits[self._dragging_idx]
            # No dejamos que el conducto salga de la envolvente
            r = c.diam / 2.0
            nx = max(r, min(self.model.width_in - r, p.x()))
            ny = max(r, min(self.model.height_in - r, p.y()))
            c.cx, c.cy = nx, ny
            self.update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.tool == "move" and self._dragging_idx is not None:
            self._dragging_idx = None
            self.changed_model.emit()
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QtWidgets.QGraphicsSceneMouseEvent):
        if e.button() == QtCore.Qt.LeftButton:
            idx = self._hit_conduit(e.scenePos())
            if idx is not None:
                self.selected_idx = idx
                self.envelope_selected = False
                self.selection_changed.emit()
                self.conduit_double_clicked.emit(idx)
                return
        super().mouseDoubleClickEvent(e)

    # ── dibujo ────────────────────────────────────────────────────────────
    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        painter.fillRect(rect, _grid_bg_color())
        # Subgrid punteada cada 0.25"
        pen_min = QtGui.QPen(_grid_minor_color(), 0, QtCore.Qt.DotLine)
        pen_maj = QtGui.QPen(_grid_major_color(), 0)
        painter.setPen(pen_min)
        x0 = math.floor(rect.left() / _GRID_MINOR_IN) * _GRID_MINOR_IN
        y0 = math.floor(rect.top() / _GRID_MINOR_IN) * _GRID_MINOR_IN
        x = x0
        while x < rect.right():
            painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            x += _GRID_MINOR_IN
        y = y0
        while y < rect.bottom():
            painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))
            y += _GRID_MINOR_IN
        # Rejilla mayor sólida cada 1"
        painter.setPen(pen_maj)
        x = math.floor(rect.left()) - 1
        while x < rect.right() + 1:
            painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            x += _GRID_MAJOR_IN
        y = math.floor(rect.top()) - 1
        while y < rect.bottom() + 1:
            painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))
            y += _GRID_MAJOR_IN
        # Ejes 0-0 más marcados
        painter.setPen(QtGui.QPen(QtGui.QColor(_theme.tokens().text_muted), 0))
        painter.drawLine(QtCore.QPointF(0, rect.top()), QtCore.QPointF(0, rect.bottom()))
        painter.drawLine(QtCore.QPointF(rect.left(), 0), QtCore.QPointF(rect.right(), 0))

    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        d = self.model
        # Envolvente (posiblemente con esquinas redondeadas)
        if d.width_in > 0 and d.height_in > 0:
            env_rect = QtCore.QRectF(0, 0, d.width_in, d.height_in)
            painter.setBrush(_envelope_fill_color())
            pen = QtGui.QPen(_selection_color() if self.envelope_selected else _envelope_border_color(),
                             0.06 if self.envelope_selected else 0.04)
            painter.setPen(pen)
            if d.has_rounded_corners():
                path = _rounded_rect_path(env_rect,
                                           d.corner_tl, d.corner_tr,
                                           d.corner_br, d.corner_bl)
                painter.drawPath(path)
            else:
                painter.drawRect(env_rect)
            # Margen interior: línea GRIS OSCURA punteada, similar al margen de
            # página en un procesador de texto. Solo se pinta si al menos uno
            # de los cuatro márgenes es > 0 (evita ruido cuando no aplica).
            if d.has_margin():
                mx, my, mw, mh = d.inner_rect()
                if mw > 0 and mh > 0:
                    inner = QtCore.QRectF(mx, my, mw, mh)
                    margin_pen = QtGui.QPen(QtGui.QColor(_theme.tokens().text_muted),
                                             0.035, QtCore.Qt.DashLine)
                    painter.setPen(margin_pen)
                    painter.setBrush(QtCore.Qt.NoBrush)
                    painter.drawRect(inner)
            # ── Guía interior (rejilla estilo Photoshop) ────────────────
            # Solo se pinta si el usuario la activó. Línea continua fina en
            # color de acento; NO usa la subrejilla del fondo (que sigue en
            # pulgadas) ni interfiere con el snap del lienzo.
            if d.guide_show:
                gx, gy, gw, gh = d.inner_rect()
                if gw > 0 and gh > 0:
                    cols = max(1, int(d.guide_cols))
                    rows = max(1, int(d.guide_rows))
                    guide_pen = QtGui.QPen(QtGui.QColor(_theme.tokens().accent),
                                             0.02)
                    painter.setPen(guide_pen)
                    # Verticales interiores (cols-1 divisorias)
                    cw = gw / cols
                    for i in range(1, cols):
                        x = gx + i * cw
                        painter.drawLine(QtCore.QPointF(x, gy),
                                          QtCore.QPointF(x, gy + gh))
                    # Horizontales interiores (rows-1 divisorias)
                    ch = gh / rows
                    for j in range(1, rows):
                        y = gy + j * ch
                        painter.drawLine(QtCore.QPointF(gx, y),
                                          QtCore.QPointF(gx + gw, y))
                    # Etiqueta arriba con el tamaño de celda en pulgadas —
                    # así el usuario ve la SEPARACIÓN entre líneas guía.
                    txt = f'{cw:.2f}" × {ch:.2f}"'
                    painter.setPen(QtGui.QPen(QtGui.QColor(_theme.tokens().accent), 0))
                    f = painter.font(); f.setPointSizeF(0.30); painter.setFont(f)
                    painter.drawText(QtCore.QRectF(gx, gy - 0.55, gw, 0.45),
                                      QtCore.Qt.AlignCenter, txt)
        # Conductos
        for i, c in enumerate(d.conduits):
            r = c.diam / 2.0
            fits = conduit_fits_envelope(d, c) if d.width_in > 0 else True
            painter.setBrush(_conduit_fill_color())
            col = _invalid_color() if not fits else (_selection_color() if i == self.selected_idx else _conduit_border_color())
            painter.setPen(QtGui.QPen(col, 0.05 if i == self.selected_idx else 0.03))
            painter.drawEllipse(QtCore.QPointF(c.cx, c.cy), r, r)
            # Etiqueta grande y legible
            painter.setPen(QtGui.QPen(_conduit_text_color(), 0))
            f = painter.font(); f.setPointSizeF(0.28 * (r * 2))
            painter.setFont(f)
            txt = c.label or f'{c.diam:g}"'
            painter.drawText(QtCore.QRectF(c.cx - r, c.cy - r, r * 2, r * 2),
                             QtCore.Qt.AlignCenter, txt)
        # Medida — línea con marcadores en los endpoints imantados + valor
        if self.tool == "measure" and len(self._measure_pts) >= 2:
            a, b = self._measure_pts[-2], self._measure_pts[-1]
            mpen = QtGui.QPen(QtGui.QColor(180, 40, 100), 0.04, QtCore.Qt.DashDotLine)
            painter.setPen(mpen); painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(a, b)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(180, 40, 100)))
            painter.drawEllipse(a, 0.08, 0.08)
            painter.drawEllipse(b, 0.08, 0.08)
            # Valor de distancia flotando al centro
            mid = QtCore.QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            painter.setPen(QtGui.QPen(QtGui.QColor(180, 40, 100), 0))
            fm = painter.font(); fm.setPointSizeF(0.32); painter.setFont(fm)
            painter.drawText(QtCore.QRectF(mid.x() - 1.5, mid.y() - 0.9, 3.0, 0.5),
                              QtCore.Qt.AlignCenter,
                              f'{math.hypot(a.x() - b.x(), a.y() - b.y()):.2f}"')

        # ── Cotas exteriores (4 lados) ──────────────────────────────────
        # Notación tipo ingeniería: |———— 18.00" ————|, uno por lado, por fuera
        # de la envolvente. Se dibujan una sola vez con el ancho/alto real —
        # no dependen del margen ni de la guía, siempre marcan el contenedor.
        if d.width_in > 0 and d.height_in > 0:
            self._draw_dimensions(painter, d)

        # ── Cotas AUTOMÁTICAS del conducto seleccionado a sus vecinos ─────
        # Mientras haya un conducto seleccionado, se pintan 4 cotas cortitas
        # desde su borde hasta el obstáculo más cercano en cada dirección:
        # otro conducto, línea de la rejilla guía, o pared interior de la
        # envolvente. Así el usuario ve al instante la SEPARACIÓN real.
        if (self.selected_idx is not None
                and 0 <= self.selected_idx < len(d.conduits)
                and d.width_in > 0 and d.height_in > 0):
            self._draw_neighbor_dims(painter, d, self.selected_idx)

    def _draw_dimensions(self, painter, d):
        """Cotas exteriores estilo plano: línea corta perpendicular en cada
        extremo (tick), línea larga entre ticks y valor en pulgadas al centro.
        Se pintan en las 4 direcciones (arriba, abajo, izquierda, derecha) para
        que se vea la SEPARACIÓN por lado, como pidió el usuario."""
        offset = 1.0           # distancia entre el borde de la envolvente y la cota
        tick = 0.18            # medio-alto del tick perpendicular
        color = QtGui.QColor(_theme.tokens().text)
        pen_line = QtGui.QPen(color, 0.03)
        font = painter.font(); font.setPointSizeF(0.34); painter.setFont(font)
        text_flags = QtCore.Qt.AlignCenter

        w, h = d.width_in, d.height_in

        # ── Cota SUPERIOR (mide ancho) ──
        y = -offset
        painter.setPen(pen_line)
        painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(w, y))
        painter.drawLine(QtCore.QPointF(0, y - tick), QtCore.QPointF(0, y + tick))
        painter.drawLine(QtCore.QPointF(w, y - tick), QtCore.QPointF(w, y + tick))
        painter.drawText(QtCore.QRectF(0, y - 0.75, w, 0.55), text_flags, f'{w:.2f}"')

        # ── Cota INFERIOR (mide ancho) ──
        y = h + offset
        painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(w, y))
        painter.drawLine(QtCore.QPointF(0, y - tick), QtCore.QPointF(0, y + tick))
        painter.drawLine(QtCore.QPointF(w, y - tick), QtCore.QPointF(w, y + tick))
        painter.drawText(QtCore.QRectF(0, y + 0.15, w, 0.55), text_flags, f'{w:.2f}"')

        # ── Cota IZQUIERDA (mide alto) ──
        x = -offset
        painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, h))
        painter.drawLine(QtCore.QPointF(x - tick, 0), QtCore.QPointF(x + tick, 0))
        painter.drawLine(QtCore.QPointF(x - tick, h), QtCore.QPointF(x + tick, h))
        painter.save()
        painter.translate(x - 0.4, h / 2.0)
        painter.rotate(-90)
        painter.drawText(QtCore.QRectF(-h / 2.0, -0.28, h, 0.55), text_flags, f'{h:.2f}"')
        painter.restore()

        # ── Cota DERECHA (mide alto) ──
        x = w + offset
        painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, h))
        painter.drawLine(QtCore.QPointF(x - tick, 0), QtCore.QPointF(x + tick, 0))
        painter.drawLine(QtCore.QPointF(x - tick, h), QtCore.QPointF(x + tick, h))
        painter.save()
        painter.translate(x + 0.9, h / 2.0)
        painter.rotate(-90)
        painter.drawText(QtCore.QRectF(-h / 2.0, -0.28, h, 0.55), text_flags, f'{h:.2f}"')
        painter.restore()

    def _draw_neighbor_dims(self, painter, d, idx):
        """Dibuja 4 cotas del conducto seleccionado a lo más cercano en cada
        dirección: otro conducto, línea de la rejilla guía, o pared interior de
        la envolvente (considerando margen si lo hay).

        Formato tipo cota chica:  |———— 4.00" ————|  del borde del conducto al
        borde del vecino más próximo. Solo se pintan cuando hay algo a menos de
        una distancia razonable (evita cotas kilométricas si un conducto está
        solo en la esquina)."""
        c = d.conduits[idx]
        r = c.diam / 2.0
        # Punto medio de cada borde del conducto
        left_x, right_x = c.cx - r, c.cx + r
        top_y, bot_y = c.cy - r, c.cy + r

        # ── Candidatos por dirección ─────────────────────────────────
        # Para IZQUIERDA / DERECHA (búsqueda horizontal en y = c.cy):
        # (a) borde interior de la envolvente en X = 0 / width
        # (b) borde interior del margen (si has_margin)
        # (c) líneas verticales de la guía (si guide_show)
        # (d) borde derecho de otros conductos a la izquierda / borde izq a la derecha,
        #     que estén EN EL MISMO RANGO Y (solapan verticalmente con la selección)
        left_cands = [(0.0, "envolvente")]
        right_cands = [(d.width_in, "envolvente")]
        top_cands = [(0.0, "envolvente")]
        bot_cands = [(d.height_in, "envolvente")]

        if d.has_margin():
            mx, my, mw, mh = d.inner_rect()
            if mw > 0 and mh > 0:
                left_cands.append((mx, "margen"))
                right_cands.append((mx + mw, "margen"))
                top_cands.append((my, "margen"))
                bot_cands.append((my + mh, "margen"))

        if d.guide_show:
            gx, gy, gw, gh = d.inner_rect()
            if gw > 0 and gh > 0:
                cols = max(1, int(d.guide_cols)); rows = max(1, int(d.guide_rows))
                cw = gw / cols; ch = gh / rows
                for i in range(1, cols):
                    left_cands.append((gx + i * cw, "guía"))
                    right_cands.append((gx + i * cw, "guía"))
                for j in range(1, rows):
                    top_cands.append((gy + j * ch, "guía"))
                    bot_cands.append((gy + j * ch, "guía"))

        # Otros conductos que se solapan verticalmente (H) u horizontalmente (V)
        for j, o in enumerate(d.conduits):
            if j == idx: continue
            ro = o.diam / 2.0
            # Vecino horizontal: solapa en Y con el seleccionado
            if abs(o.cy - c.cy) <= (r + ro):
                if o.cx + ro <= left_x:      # está a la izquierda
                    left_cands.append((o.cx + ro, "conducto"))
                elif o.cx - ro >= right_x:   # está a la derecha
                    right_cands.append((o.cx - ro, "conducto"))
            # Vecino vertical: solapa en X con el seleccionado
            if abs(o.cx - c.cx) <= (r + ro):
                if o.cy + ro <= top_y:
                    top_cands.append((o.cy + ro, "conducto"))
                elif o.cy - ro >= bot_y:
                    bot_cands.append((o.cy - ro, "conducto"))

        # ── Elegir el más cercano en cada dirección (mayor X <= left_x, etc.) ──
        left_hit  = max((v for v, _ in left_cands  if v <= left_x  + 1e-6), default=None)
        right_hit = min((v for v, _ in right_cands if v >= right_x - 1e-6), default=None)
        top_hit   = max((v for v, _ in top_cands   if v <= top_y   + 1e-6), default=None)
        bot_hit   = min((v for v, _ in bot_cands   if v >= bot_y   - 1e-6), default=None)

        # ── Dibujo de cotas cortas (dentro/junto al conducto) ──────
        acc = QtGui.QColor(_theme.tokens().accent)
        pen = QtGui.QPen(acc, 0.025)
        painter.setPen(pen)
        f = painter.font(); f.setPointSizeF(0.35); painter.setFont(f)
        tick = 0.12
        flags = QtCore.Qt.AlignCenter

        def _draw_h(x0, x1, y, txt):
            span = abs(x1 - x0)
            if span < 0.05: return
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(x0, y), QtCore.QPointF(x1, y))
            painter.drawLine(QtCore.QPointF(x0, y - tick), QtCore.QPointF(x0, y + tick))
            painter.drawLine(QtCore.QPointF(x1, y - tick), QtCore.QPointF(x1, y + tick))
            tw = max(span, 1.2)
            painter.setPen(QtGui.QPen(acc, 0))
            painter.drawText(QtCore.QRectF(min(x0, x1) - (tw - span) / 2, y - 0.55,
                                            tw, 0.50), flags, txt)

        def _draw_v(y0, y1, x, txt):
            span = abs(y1 - y0)
            if span < 0.05: return
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(x, y0), QtCore.QPointF(x, y1))
            painter.drawLine(QtCore.QPointF(x - tick, y0), QtCore.QPointF(x + tick, y0))
            painter.drawLine(QtCore.QPointF(x - tick, y1), QtCore.QPointF(x + tick, y1))
            painter.save()
            painter.translate(x + 0.45, (y0 + y1) / 2.0)
            painter.rotate(-90)
            th = max(span, 1.2)
            painter.setPen(QtGui.QPen(acc, 0))
            painter.drawText(QtCore.QRectF(-th / 2, -0.28, th, 0.50),
                              flags, txt)
            painter.restore()

        if left_hit  is not None:
            _draw_h(left_hit,  left_x,  c.cy, f'{left_x  - left_hit :.2f}"')
        if right_hit is not None:
            _draw_h(right_x,   right_hit, c.cy, f'{right_hit - right_x:.2f}"')
        if top_hit   is not None:
            _draw_v(top_hit,   top_y,   c.cx, f'{top_y   - top_hit  :.2f}"')
        if bot_hit   is not None:
            _draw_v(bot_y,     bot_hit, c.cx, f'{bot_hit - bot_y   :.2f}"')


class _DuctBankView(QtWidgets.QGraphicsView):
    """Vista con zoom-a-cursor y arrastre con botón central."""
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
        # Estilo se aplica desde DuctBankDialog._restyle().
        self._panning = False
        self._pan_last = QtCore.QPoint()
        self.scale(_INITIAL_PX_PER_IN, _INITIAL_PX_PER_IN)   # pulgadas → px

    def wheelEvent(self, e: QtGui.QWheelEvent):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        cur = self.transform().m11()
        new = cur * f
        if _INITIAL_PX_PER_IN * _MIN_ZOOM <= new <= _INITIAL_PX_PER_IN * _MAX_ZOOM:
            self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._panning = True
            self._pan_last = e.position().toPoint()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning:
            delta = e.position().toPoint() - self._pan_last
            self._pan_last = e.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._panning = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            return
        super().mouseReleaseEvent(e)


# ── El diálogo completo ─────────────────────────────────────────────────────
class DuctBankDialog(QtWidgets.QDialog):
    """Diseñador de sección del Duct Bank. Ver docstring del módulo."""

    def __init__(self, parent=None, initial: Optional[DuctBank] = None,
                 pipes: Optional[list] = None):
        super().__init__(parent)
        self.setWindowTitle("Diseñador de Duct Bank")
        # Ventana top-level normal — como la ventana principal y georreferenciar.
        # Sin `setModal(True)`: `exec()` la sigue haciendo modal (bloquea la
        # ventana padre) pero el WM la trata como ventana común: se arrastra por
        # los bordes, minimiza, maximiza y restaura sin restricciones raras.
        # Los flags Min/Max/Close hint son necesarios porque QDialog los omite
        # por defecto en Windows.
        self.setWindowFlags(QtCore.Qt.Window
                             | QtCore.Qt.WindowMinimizeButtonHint
                             | QtCore.Qt.WindowMaximizeButtonHint
                             | QtCore.Qt.WindowCloseButtonHint
                             | QtCore.Qt.WindowSystemMenuHint)
        self.setSizeGripEnabled(True)
        # Se abre MAXIMIZADA (petición del usuario) usando la pantalla del padre.
        # `showMaximized` va en showEvent — llamarlo en __init__ no siempre pega
        # antes de que el WM registre la ventana. Guardamos un tamaño razonable
        # como fallback por si el usuario sale del maximizado y luego cierra.
        scr = (parent.screen() if parent else None) or self.screen() \
            or QtWidgets.QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else QtCore.QRect(0, 0, 1400, 860)
        w = min(1400, max(720, avail.width() - 80))
        h = min(880, max(540, avail.height() - 120))
        self.resize(w, h)
        # Mínimo lo bajo posible para que el usuario pueda arrastrar la ventana
        # a cualquier tamaño; el panel derecho tiene scroll si no cabe todo.
        self.setMinimumSize(680, 480)
        self._start_maximized = True
        # Historial simple para Deshacer/Rehacer
        self._history: List[DuctBank] = []
        self._future: List[DuctBank] = []

        self._pipes = pipes or []
        self.scene = _DuctBankScene(self)
        if initial is not None:
            self.scene.model = initial.copy()
        self._push_history()   # estado inicial en el historial

        self.view = _DuctBankView(self.scene)
        self._build_ui()
        self._wire()
        self._refresh_panel()
        # Herramienta activa al abrir
        self._set_tool("select")
        # Estilos custom: aplicar ahora + reaccionar a cambios de tema mientras el
        # diálogo está abierto. La conexión se limpia sola al destruir el diálogo.
        self._restyle()
        _theme.THEME_BUS.changed.connect(self._restyle)

    # ── result API ─────────────────────────────────────────────────────────
    def result_model(self) -> DuctBank:
        m = self.scene.model.copy()
        m.pipe_idx = self.cmb_pipe.currentData()
        return m

    # ── construcción de la UI ─────────────────────────────────────────────
    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # Header
        header = QtWidgets.QFrame(); self._header = header   # estilo por _restyle
        h = QtWidgets.QHBoxLayout(header); h.setContentsMargins(14, 10, 14, 10); h.setSpacing(10)
        lbl_title = QtWidgets.QLabel("<span style='color:white;font-size:18px;font-weight:700;'>"
                                     "Diseñador de Duct Bank</span><br>"
                                     "<span style='color:#d7e5ff;font-size:12px;'>"
                                     "Cara Interior (Corte Longitudinal)</span>")
        h.addWidget(lbl_title); h.addStretch(1)
        self.btn_new = QtWidgets.QPushButton("  Nuevo")
        self.btn_open = QtWidgets.QPushButton("  Abrir")
        self.btn_save = QtWidgets.QPushButton("  Guardar")
        self.btn_undo = QtWidgets.QPushButton("  Deshacer")
        self.btn_redo = QtWidgets.QPushButton("  Rehacer")
        self.btn_help = QtWidgets.QPushButton("  Ayuda")
        self.btn_close = QtWidgets.QPushButton("  Guardar y cerrar")
        self._header_buttons = [self.btn_new, self.btn_open, self.btn_save,
                                 self.btn_undo, self.btn_redo, self.btn_help, self.btn_close]
        # Mapa botón → nombre de icono (para _restyle: reasignar al cambiar tema).
        self._header_icon_map = {
            self.btn_new: "mdi:file-plus-outline",
            self.btn_open: "mdi:folder-open-outline",
            self.btn_save: "mdi:content-save-outline",
            self.btn_undo: "mdi:undo-variant",
            self.btn_redo: "mdi:redo-variant",
            self.btn_help: "mdi:help-circle-outline",
            self.btn_close: "mdi:close",
        }
        for b in self._header_buttons:
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setIconSize(QtCore.QSize(18, 18))
            h.addWidget(b)
        root.addWidget(header)

        # Cuerpo: [ toolbar | canvas | props ]
        body = QtWidgets.QWidget(); body_l = QtWidgets.QHBoxLayout(body)
        body_l.setContentsMargins(8, 8, 8, 8); body_l.setSpacing(8)

        # Toolbar izquierda
        tools_wrap = QtWidgets.QFrame()
        self._tools_wrap = tools_wrap
        tv = QtWidgets.QVBoxLayout(tools_wrap); tv.setContentsMargins(8, 8, 8, 8); tv.setSpacing(6)
        self._tool_group = QtWidgets.QButtonGroup(self); self._tool_group.setExclusive(True)
        self._tool_buttons = []
        # Mapa botón → nombre de icono, para retintar en _restyle.
        self._tool_icon_map = {}
        def _tool_btn(icon_name, label, tool_key, tip, danger=False):
            b = QtWidgets.QToolButton()
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            b.setText(label)
            b.setIconSize(QtCore.QSize(28, 28))
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setProperty("danger", "true" if danger else "false")
            b.clicked.connect(lambda: self._set_tool(tool_key))
            self._tool_group.addButton(b)
            self._tool_buttons.append(b)
            self._tool_icon_map[b] = icon_name
            tv.addWidget(b)
            return b
        self.tb_sel = _tool_btn("mdi:cursor-default-outline", "Seleccionar", "select",
                                "Click en un conducto o en la envolvente para seleccionarlo.")
        self.tb_conduit = _tool_btn("mdi:circle-outline", "Conducto\n(Círculo)", "conduit",
                                    "Click dentro de la envolvente para colocar un conducto del diámetro elegido.")
        # (La herramienta "Rectángulo" se retiró: el contenedor siempre existe con
        #  medidas por defecto y el usuario ajusta Ancho/Alto en el panel derecho.)
        self.tb_measure = _tool_btn("mdi:tape-measure", "Medir", "measure",
                                    "Click en dos puntos para medir la distancia entre ellos en pulgadas.")
        self.tb_move = _tool_btn("mdi:cursor-move", "Mover", "move",
                                 "Arrastra un conducto para reposicionarlo.")
        self.tb_delete = _tool_btn("mdi:trash-can-outline", "Eliminar", "delete",
                                   "Click en un conducto para eliminarlo.", danger=True)
        tv.addSpacing(10)
        # Zoom + ajustar
        def _plain_btn(icon_name, label, tip, fn):
            b = QtWidgets.QToolButton()
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            b.setText(label); b.setToolTip(tip)
            b.setIconSize(QtCore.QSize(28, 28))
            b.clicked.connect(fn); self._tool_buttons.append(b); self._tool_icon_map[b] = icon_name
            tv.addWidget(b); return b
        self.btn_zin = _plain_btn("mdi:magnify-plus-outline", "Zoom +", "Acercar", lambda: self._zoom(1.15))
        self.btn_zout = _plain_btn("mdi:magnify-minus-outline", "Zoom −", "Alejar", lambda: self._zoom(1 / 1.15))
        self.btn_fit = _plain_btn("mdi:image-filter-center-focus", "Ajustar",
                                    "Centrar la vista sobre la envolvente", self._fit)
        tv.addStretch(1)
        body_l.addWidget(tools_wrap, 0)

        # Zona central: canvas
        center = QtWidgets.QVBoxLayout(); center.setSpacing(4)
        center.addWidget(self.view, 1)

        # Barra inferior
        footer = QtWidgets.QFrame(); self._footer = footer   # estilo por _restyle
        fh = QtWidgets.QHBoxLayout(footer); fh.setContentsMargins(12, 6, 12, 6); fh.setSpacing(14)
        self.lbl_status = QtWidgets.QLabel("Rejilla activada · 1 punto = 1 pulgada")
        # color por _restyle
        fh.addWidget(self.lbl_status)
        fh.addStretch(1)
        # "Imán" al retículo de 0.25 pulgadas del lienzo (subrejilla punteada
        # de fondo). Con esto ON, cada clic para poner/mover un conducto o
        # medir queda ajustado al múltiplo de 0.25". Con OFF, precisión libre.
        self.chk_snap = QtWidgets.QCheckBox("Ajuste a rejilla (0.25\")")
        self.chk_snap.setChecked(True)
        self.chk_snap.setToolTip(
            "Cuando está activado, los clics del ratón se pegan (imán) al retículo\n"
            "de 0.25 pulgadas del fondo del lienzo. Sirve para colocar conductos\n"
            "y medir con precisión ⅟₄ pulgada.\n\n"
            "Desactívalo si necesitas posicionar algo en un valor libre no múltiplo\n"
            "de 0.25\".")
        fh.addWidget(self.chk_snap)
        self.sl_zoom = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_zoom.setRange(int(_MIN_ZOOM * 100), int(_MAX_ZOOM * 100))
        self.sl_zoom.setValue(100); self.sl_zoom.setFixedWidth(180)
        fh.addWidget(QtWidgets.QLabel("🔍")); fh.addWidget(self.sl_zoom)
        self.lbl_zoom = QtWidgets.QLabel("100%"); self.lbl_zoom.setFixedWidth(48)
        fh.addWidget(self.lbl_zoom)
        center.addWidget(footer, 0)

        body_l.addLayout(center, 1)

        # Panel derecho: propiedades
        # El panel derecho es alto (varios groupboxes) y con widgets espaciales
        # (compass/corners). Antes tenía ancho fijo 260 → contenido cortado en
        # pantallas chicas. Ahora el frame vive dentro de un QScrollArea:
        # ancho preferente ~340, scroll vertical automático si no cabe.
        side = QtWidgets.QFrame(); self._side = side   # estilo por _restyle
        sv = QtWidgets.QVBoxLayout(side); sv.setContentsMargins(10, 10, 10, 10); sv.setSpacing(10)

        # Nombre del duct bank
        gname = QtWidgets.QGroupBox("Nombre")
        gnl = QtWidgets.QVBoxLayout(gname)
        self.ed_name = QtWidgets.QLineEdit()
        self.ed_name.setPlaceholderText("Ej. Duct Bank A – Telecom")
        gnl.addWidget(self.ed_name)
        sv.addWidget(gname)

        # Envolvente
        genv = QtWidgets.QGroupBox("Envolvente (pulgadas)")
        gel = QtWidgets.QFormLayout(genv)
        self.sp_w = QtWidgets.QDoubleSpinBox(); self.sp_w.setRange(0.25, 200); self.sp_w.setDecimals(2); self.sp_w.setSuffix('"')
        self.sp_h = QtWidgets.QDoubleSpinBox(); self.sp_h.setRange(0.25, 200); self.sp_h.setDecimals(2); self.sp_h.setSuffix('"')
        gel.addRow("Ancho:", self.sp_w); gel.addRow("Alto:", self.sp_h)
        sv.addWidget(genv)

        # Margen interior (guía) — editor estilo Photoshop en disposición compás.
        gmarg = QtWidgets.QGroupBox("Margen interior (pulgadas)")
        gml = QtWidgets.QVBoxLayout(gmarg); gml.setContentsMargins(4, 4, 4, 4)
        self.ed_margin = _FourSideEditor(self, layout_mode="compass",
                                          maximum=50.0, step=0.25, decimals=2)
        gml.addWidget(self.ed_margin)
        sv.addWidget(gmarg)

        # Guía interior (rejilla estilo Photoshop) — se dibuja SOLO dentro del
        # margen. Sirve para posicionar conductos simétricamente. Un checkbox
        # muestra/oculta la vista, y muestra al lado el tamaño de cada celda.
        gguide = QtWidgets.QGroupBox("Guía interior (rejilla)")
        ggl = QtWidgets.QVBoxLayout(gguide); ggl.setContentsMargins(4, 4, 4, 4); ggl.setSpacing(6)
        self.chk_guide = QtWidgets.QCheckBox("Mostrar guía")
        self.chk_guide.setToolTip("Activa una rejilla fina de líneas guía dentro del "
                                    "margen, similar a las guías de Photoshop. "
                                    "Ayuda a colocar los conductos simétricamente.")
        ggl.addWidget(self.chk_guide)
        _grow = QtWidgets.QHBoxLayout(); _grow.setSpacing(8)
        _grow.addWidget(QtWidgets.QLabel("Columnas:"))
        self.sp_gcols = QtWidgets.QSpinBox(); self.sp_gcols.setRange(1, 40); self.sp_gcols.setValue(1)
        self.sp_gcols.setToolTip("Cuántas columnas verticales dividen el área interior.")
        _grow.addWidget(self.sp_gcols)
        _grow.addSpacing(10)
        _grow.addWidget(QtWidgets.QLabel("Filas:"))
        self.sp_grows = QtWidgets.QSpinBox(); self.sp_grows.setRange(1, 40); self.sp_grows.setValue(1)
        self.sp_grows.setToolTip("Cuántas filas horizontales dividen el área interior.")
        _grow.addWidget(self.sp_grows); _grow.addStretch(1)
        ggl.addLayout(_grow)
        # Etiqueta con la dimensión actual de cada celda (útil para saber la
        # separación en pulgadas — se actualiza en tiempo real).
        self.lbl_cell = QtWidgets.QLabel("Celda: —")
        ggl.addWidget(self.lbl_cell)
        sv.addWidget(gguide)

        # Redondeo de esquinas — editor estilo Photoshop en disposición esquinas.
        gcor = QtWidgets.QGroupBox("Redondeo de esquinas (pulgadas)")
        gcl = QtWidgets.QVBoxLayout(gcor); gcl.setContentsMargins(4, 4, 4, 4)
        self.ed_corners = _FourSideEditor(self, layout_mode="corners",
                                           maximum=20.0, step=0.25, decimals=2)
        gcl.addWidget(self.ed_corners)
        sv.addWidget(gcor)

        # Nuevo conducto
        gnc = QtWidgets.QGroupBox("Nuevo conducto")
        gnl2 = QtWidgets.QFormLayout(gnc)
        self.sp_new_diam = QtWidgets.QDoubleSpinBox()
        self.sp_new_diam.setRange(0.25, 50)
        self.sp_new_diam.setDecimals(2)
        self.sp_new_diam.setSingleStep(0.25)
        self.sp_new_diam.setSuffix('"')
        self.sp_new_diam.setValue(4.0)
        gnl2.addRow("Diámetro:", self.sp_new_diam)
        sv.addWidget(gnc)

        # Conducto seleccionado
        gsel = QtWidgets.QGroupBox("Conducto seleccionado")
        gsl = QtWidgets.QFormLayout(gsel)
        self.sel_x = QtWidgets.QDoubleSpinBox(); self.sel_x.setRange(0, 200); self.sel_x.setDecimals(2); self.sel_x.setSuffix('"')
        self.sel_y = QtWidgets.QDoubleSpinBox(); self.sel_y.setRange(0, 200); self.sel_y.setDecimals(2); self.sel_y.setSuffix('"')
        self.sel_d = QtWidgets.QDoubleSpinBox(); self.sel_d.setRange(0.25, 50); self.sel_d.setDecimals(2); self.sel_d.setSuffix('"')
        self.sel_lbl = QtWidgets.QLineEdit(); self.sel_lbl.setPlaceholderText("Etiqueta (opcional)")
        gsl.addRow("X:", self.sel_x); gsl.addRow("Y:", self.sel_y)
        gsl.addRow("Diám.:", self.sel_d); gsl.addRow("Etiqueta:", self.sel_lbl)
        self.btn_del_sel = QtWidgets.QPushButton("  Eliminar conducto")
        self.btn_del_sel.setIconSize(QtCore.QSize(18, 18))
        self.btn_del_sel.setProperty("danger", "true")   # el QSS global tiñe rojo
        gsl.addRow(self.btn_del_sel)
        sv.addWidget(gsel)

        # ── Asignación a utilidad (pipe) ──────────────────────────────────
        gassign = QtWidgets.QGroupBox("Asignar a utilidad")
        gal = QtWidgets.QFormLayout(gassign)
        self.cmb_pipe = QtWidgets.QComboBox()
        self.cmb_pipe.addItem("(Sin asignar)", -1)
        for i, p in enumerate(self._pipes):
            if not p.get("pts"): continue
            layer = p.get("layer", "?")
            n_pts = len(p.get("pts", []))
            diam = p.get("diam") or "?"
            label = f"#{i+1}  {layer}  —  {diam}\"  ({n_pts} vértices)"
            self.cmb_pipe.addItem(label, i)
        cur_idx = self.scene.model.pipe_idx
        if cur_idx >= 0:
            for ci in range(self.cmb_pipe.count()):
                if self.cmb_pipe.itemData(ci) == cur_idx:
                    self.cmb_pipe.setCurrentIndex(ci)
                    break
        self.lbl_pipe_status = QtWidgets.QLabel("")
        self.lbl_pipe_status.setWordWrap(True)
        gal.addRow("Utilidad:", self.cmb_pipe)
        gal.addRow(self.lbl_pipe_status)
        self._update_pipe_status()
        sv.addWidget(gassign)

        # Contador + validación
        self.lbl_count = QtWidgets.QLabel("Conductos: 0")
        # color por _restyle
        sv.addWidget(self.lbl_count)
        self.lbl_valid = QtWidgets.QLabel("")
        self.lbl_valid.setWordWrap(True)
        # color por _restyle
        sv.addWidget(self.lbl_valid)

        sv.addStretch(1)
        # Envolvemos el panel en un scroll: si el usuario achica la ventana, en
        # vez de recortar los editores compass/corners aparece un scroll vertical.
        side_scroll = QtWidgets.QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        side_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        side_scroll.setWidget(side)
        # Ancho preferente que da aire a los editores 3×3 sin lucir enorme.
        side_scroll.setMinimumWidth(340); side_scroll.setMaximumWidth(420)
        body_l.addWidget(side_scroll, 0)

        root.addWidget(body, 1)

    def _restyle(self, *_):
        """Aplica todos los estilos QSS custom con los tokens del tema activo.
        Se llama al construir la UI y cada vez que el bus emita cambio de tema."""
        t = _theme.tokens()
        # Header (barra azul superior)
        if hasattr(self, "_header"):
            self._header.setStyleSheet(f"QFrame{{background:{t.header};}}")
        # Panel derecho + toolbar izquierda (tarjetas)
        card_qss = (f"QFrame{{background:{t.surface};border:1px solid {t.border};"
                    f"border-radius:8px;}}")
        for f in ("_tools_wrap", "_side"):
            w = getattr(self, f, None)
            if w is not None: w.setStyleSheet(card_qss)
        # Footer (barra de estado)
        if hasattr(self, "_footer"):
            self._footer.setStyleSheet(
                f"QFrame{{background:{t.surface_alt};border:1px solid {t.border};border-radius:6px;}}")
        # Vista del canvas
        if hasattr(self, "view"):
            self.view.setStyleSheet(f"QGraphicsView{{border:1px solid {t.border};background:{t.grid_bg};}}")
        # Botones del header + herramientas de la izquierda
        for b in getattr(self, "_header_buttons", []):
            b.setStyleSheet(_build_header_style())
        for b in getattr(self, "_tool_buttons", []):
            b.setStyleSheet(_build_btn_style())
        # Iconos (SVG re-tintados con el tema): retintar con text_on_accent en el
        # header (fondo azul acento) y text en la barra de herramientas.
        for b, name in getattr(self, "_header_icon_map", {}).items():
            b.setIcon(_icon(name, color=t.text_on_accent))
        for b, name in getattr(self, "_tool_icon_map", {}).items():
            # Los checked/danger sobreescriben color vía QSS; con este tint base
            # se leen bien en estado normal.
            c = t.danger if b.property("danger") == "true" else t.text
            b.setIcon(_icon(name, color=c))
        if hasattr(self, "btn_del_sel"):
            self.btn_del_sel.setIcon(_icon("mdi:trash-can-outline",
                                            color=t.text_on_accent))
        # Labels de status/count/validez
        for name, style in (
            ("lbl_status", f"QLabel{{color:{t.text_muted};font-size:12px;}}"),
            ("lbl_count", f"QLabel{{color:{t.text_muted};font-size:12px;}}"),
            ("lbl_valid", f"QLabel{{color:{t.danger};font-size:12px;}}"),
        ):
            w = getattr(self, name, None)
            if w is not None: w.setStyleSheet(style)
        # Fuerza repintado de la escena (colores de envolvente/conductos)
        if hasattr(self, "scene"):
            self.scene.update()

    def _wire(self):
        # Header
        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_redo.clicked.connect(self._on_redo)
        QtGui.QShortcut(QtGui.QKeySequence.Undo, self, self._on_undo)
        QtGui.QShortcut(QtGui.QKeySequence.Redo, self, self._on_redo)
        self.btn_help.clicked.connect(self._on_help)
        self.btn_close.clicked.connect(self._on_close)

        # Escena
        self.scene.changed_model.connect(self._on_model_changed)
        self.scene.selection_changed.connect(self._refresh_panel)
        self.scene.tool_hint.connect(self.lbl_status.setText)

        # Panel
        self.ed_name.textChanged.connect(lambda s: self._set_name(s))
        self.sp_w.valueChanged.connect(lambda v: self._set_env(w=v))
        self.sp_h.valueChanged.connect(lambda v: self._set_env(h=v))
        # Margen (compass): a=top, b=right, c=bottom, d=left
        self.ed_margin.changed.connect(self._on_margin_changed)
        # Redondeo (corners): a=tl, b=tr, c=br, d=bl
        self.ed_corners.changed.connect(self._on_corners_changed)
        # Guía interior (rejilla)
        self.chk_guide.toggled.connect(lambda on: self._on_guide_changed(show=on))
        self.sp_gcols.valueChanged.connect(lambda v: self._on_guide_changed(cols=v))
        self.sp_grows.valueChanged.connect(lambda v: self._on_guide_changed(rows=v))
        self.sp_new_diam.valueChanged.connect(self._on_new_diam_changed)
        self.sel_x.valueChanged.connect(lambda v: self._edit_sel(x=v))
        self.sel_y.valueChanged.connect(lambda v: self._edit_sel(y=v))
        self.sel_d.valueChanged.connect(lambda v: self._edit_sel(d=v))
        self.sel_lbl.textChanged.connect(lambda s: self._edit_sel(lbl=s))
        self.btn_del_sel.clicked.connect(self._del_selected)
        self.cmb_pipe.currentIndexChanged.connect(lambda _: self._update_pipe_status())

        self.scene.conduit_double_clicked.connect(self._on_conduit_dblclick)

        # Footer
        self.chk_snap.toggled.connect(lambda on: setattr(self.scene, "snap_on", bool(on)))
        self.sl_zoom.valueChanged.connect(self._on_zoom_slider)

    # ── helpers de estado ────────────────────────────────────────────────
    def _push_history(self):
        self._history.append(self.scene.model.copy())
        self._future.clear()
        if len(self._history) > 200:
            self._history = self._history[-200:]

    def _refresh_panel(self):
        m = self.scene.model
        # Bloquear señales para no re-entrar
        blockers = [(w, w.blockSignals(True)) for w in
                    (self.ed_name, self.sp_w, self.sp_h,
                     self.sel_x, self.sel_y, self.sel_d, self.sel_lbl)]
        try:
            self.ed_name.setText(m.name)
            self.sp_w.setValue(m.width_in)
            self.sp_h.setValue(m.height_in)
            has_sel = (self.scene.selected_idx is not None and
                       0 <= self.scene.selected_idx < len(m.conduits))
            if has_sel:
                c = m.conduits[self.scene.selected_idx]
                self.sel_x.setEnabled(True); self.sel_y.setEnabled(True)
                self.sel_d.setEnabled(True); self.sel_lbl.setEnabled(True)
                self.btn_del_sel.setEnabled(True)
                self.sel_x.setValue(c.cx); self.sel_y.setValue(c.cy)
                self.sel_d.setValue(c.diam); self.sel_lbl.setText(c.label)
            else:
                for w in (self.sel_x, self.sel_y, self.sel_d, self.sel_lbl, self.btn_del_sel):
                    w.setEnabled(False)
                self.sel_x.setValue(0); self.sel_y.setValue(0); self.sel_d.setValue(4); self.sel_lbl.setText("")
        finally:
            for w, prev in blockers:
                w.blockSignals(prev)
        # Sincroniza los editores compass/corners con el modelo (usan set_values
        # que no re-emiten señal → no arma un ciclo con _push_history).
        if hasattr(self, "ed_margin"):
            self.ed_margin.set_values(m.margin_top, m.margin_right,
                                       m.margin_bottom, m.margin_left)
        if hasattr(self, "ed_corners"):
            self.ed_corners.set_values(m.corner_tl, m.corner_tr,
                                        m.corner_br, m.corner_bl)
        # Sincroniza controles de guía interior (sin disparar handlers).
        if hasattr(self, "chk_guide"):
            for w in (self.chk_guide, self.sp_gcols, self.sp_grows):
                w.blockSignals(True)
            try:
                self.chk_guide.setChecked(bool(m.guide_show))
                self.sp_gcols.setValue(int(m.guide_cols))
                self.sp_grows.setValue(int(m.guide_rows))
            finally:
                for w in (self.chk_guide, self.sp_gcols, self.sp_grows):
                    w.blockSignals(False)
            self._refresh_guide_label()
        self.lbl_count.setText(f"Conductos: {len(m.conduits)}")
        errs = validate(m)
        self.lbl_valid.setText("\n".join("• " + e for e in errs))

    def _on_model_changed(self):
        self._push_history()
        self._refresh_panel()
        self.scene.update()

    def _set_name(self, s):
        self.scene.model.name = str(s)
        # no historial por cada tecla; solo persistimos al Guardar / Cerrar

    def _set_env(self, w=None, h=None):
        m = self.scene.model
        if w is not None: m.width_in = float(w)
        if h is not None: m.height_in = float(h)
        self.scene.update()
        self._push_history()
        self.lbl_count.setText(f"Conductos: {len(m.conduits)}")
        self.lbl_valid.setText("\n".join("• " + e for e in validate(m)))

    def _on_margin_changed(self, top, right, bottom, left):
        m = self.scene.model
        m.margin_top = float(top); m.margin_right = float(right)
        m.margin_bottom = float(bottom); m.margin_left = float(left)
        self.scene.update()
        self._push_history()

    def _on_corners_changed(self, tl, tr, br, bl):
        m = self.scene.model
        m.corner_tl = float(tl); m.corner_tr = float(tr)
        m.corner_br = float(br); m.corner_bl = float(bl)
        self.scene.update()
        self._push_history()

    def _on_guide_changed(self, show=None, rows=None, cols=None):
        m = self.scene.model
        if show is not None: m.guide_show = bool(show)
        if rows is not None: m.guide_rows = int(rows)
        if cols is not None: m.guide_cols = int(cols)
        # Actualiza la etiqueta de dimensión de la celda al instante.
        self._refresh_guide_label()
        self.scene.update()
        self._push_history()

    def _refresh_guide_label(self):
        m = self.scene.model
        cw, ch = m.guide_cell_size()
        if cw > 0 and ch > 0:
            self.lbl_cell.setText(f'Celda: {cw:.2f}" × {ch:.2f}"'
                                    f'   ({m.guide_cols} col × {m.guide_rows} fil)')
        else:
            self.lbl_cell.setText("Celda: —  (envolvente o margen inválido)")

    def _on_new_diam_changed(self, val):
        self.scene.new_conduit_diam = float(val)

    def _edit_sel(self, x=None, y=None, d=None, lbl=None):
        idx = self.scene.selected_idx
        m = self.scene.model
        if idx is None or not (0 <= idx < len(m.conduits)):
            return
        c = m.conduits[idx]
        if x is not None: c.cx = float(x)
        if y is not None: c.cy = float(y)
        if d is not None: c.diam = float(d)
        if lbl is not None: c.label = str(lbl)
        self.scene.update()
        self.lbl_valid.setText("\n".join("• " + e for e in validate(m)))

    def _del_selected(self):
        idx = self.scene.selected_idx
        m = self.scene.model
        if idx is None or not (0 <= idx < len(m.conduits)):
            return
        del m.conduits[idx]
        self.scene.selected_idx = None
        self._on_model_changed()

    def _on_conduit_dblclick(self, idx: int):
        m = self.scene.model
        if not (0 <= idx < len(m.conduits)):
            return
        c = m.conduits[idx]
        center = self.view.mapFromScene(QtCore.QPointF(c.cx, c.cy))
        global_pos = self.view.mapToGlobal(center)
        sp = QtWidgets.QDoubleSpinBox()
        sp.setRange(0.25, 50); sp.setDecimals(2); sp.setSingleStep(0.25)
        sp.setSuffix('"'); sp.setValue(c.diam)
        sp.setAlignment(QtCore.Qt.AlignCenter)
        sp.setFixedWidth(100)
        popup = QtWidgets.QFrame(self, QtCore.Qt.Popup)
        lay = QtWidgets.QHBoxLayout(popup); lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(sp)
        popup.adjustSize()
        popup.move(global_pos.x() - popup.width() // 2,
                   global_pos.y() - popup.height() // 2)
        def _apply():
            new_d = sp.value()
            if abs(new_d - c.diam) > 0.001:
                c.diam = new_d
                self._on_model_changed()
            popup.close()
        sp.editingFinished.connect(_apply)
        popup.show()
        sp.setFocus()
        sp.selectAll()

    # ── herramientas ──────────────────────────────────────────────────────
    def _set_tool(self, key: str):
        self.scene.tool = key
        self.scene._measure_pts = []
        # Marca el botón correspondiente
        mapping = {"select": self.tb_sel, "conduit": self.tb_conduit,
                   "measure": self.tb_measure, "move": self.tb_move, "delete": self.tb_delete}
        for k, b in mapping.items():
            b.setChecked(k == key)
        hints = {"select": "Selecciona un elemento para verlo o editarlo.",
                 "conduit": f'Click dentro de la envolvente para colocar un conducto de {self.scene.new_conduit_diam:g}".',
                 "measure": "Click en 2 puntos para medir la distancia entre ellos.",
                 "move": "Arrastra un conducto para moverlo.",
                 "delete": "Click en un conducto para eliminarlo."}
        self.lbl_status.setText(hints.get(key, ""))
        # Cursor
        cursors = {"select": QtCore.Qt.ArrowCursor, "delete": QtCore.Qt.PointingHandCursor,
                   "conduit": QtCore.Qt.CrossCursor,
                   "measure": QtCore.Qt.CrossCursor, "move": QtCore.Qt.OpenHandCursor}
        self.view.setCursor(cursors.get(key, QtCore.Qt.ArrowCursor))

    def _zoom(self, f: float):
        cur = self.view.transform().m11()
        new = cur * f
        if _INITIAL_PX_PER_IN * _MIN_ZOOM <= new <= _INITIAL_PX_PER_IN * _MAX_ZOOM:
            self.view.scale(f, f)
            self.sl_zoom.blockSignals(True)
            self.sl_zoom.setValue(int((new / _INITIAL_PX_PER_IN) * 100))
            self.sl_zoom.blockSignals(False)
            self.lbl_zoom.setText(f"{int((new / _INITIAL_PX_PER_IN) * 100)}%")

    def _on_zoom_slider(self, v: int):
        target = (v / 100.0) * _INITIAL_PX_PER_IN
        cur = self.view.transform().m11()
        if cur <= 0: return
        f = target / cur
        self.view.scale(f, f)
        self.lbl_zoom.setText(f"{v}%")

    def _fit(self):
        m = self.scene.model
        if m.width_in > 0 and m.height_in > 0:
            self.view.fitInView(QtCore.QRectF(-1, -1, m.width_in + 2, m.height_in + 2),
                                QtCore.Qt.KeepAspectRatio)
        else:
            self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
        self.lbl_zoom.setText(f"{int((self.view.transform().m11() / _INITIAL_PX_PER_IN) * 100)}%")

    # ── deshacer / rehacer / archivo ──────────────────────────────────────
    def _on_undo(self):
        if len(self._history) < 2: return
        self._future.append(self._history.pop())
        self.scene.model = self._history[-1].copy()
        self.scene.selected_idx = None
        self.scene.update(); self._refresh_panel()

    def _on_redo(self):
        if not self._future: return
        m = self._future.pop()
        self._history.append(m.copy())
        self.scene.model = m.copy()
        self.scene.selected_idx = None
        self.scene.update(); self._refresh_panel()

    def _on_new(self):
        if QtWidgets.QMessageBox.question(self, "Nuevo", "¿Descartar el diseño actual y empezar uno nuevo?") \
                != QtWidgets.QMessageBox.Yes:
            return
        self.scene.model = DuctBank()
        self.scene.selected_idx = None
        self._history.clear(); self._future.clear()
        self._push_history(); self._refresh_panel(); self.scene.update()

    def _on_open(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir Duct Bank",
                                                      "", "Duct Bank (*.dbjson);;JSON (*.json)")
        if not fn: return
        try:
            with open(fn, "r", encoding="utf-8") as f:
                self.scene.model = DuctBank.from_dict(json.load(f))
            self.scene.selected_idx = None
            self._history.clear(); self._future.clear()
            self._push_history(); self._refresh_panel(); self.scene.update()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error al abrir", str(e))

    def _on_save(self):
        default = (self.scene.model.name or "duct_bank").replace("/", "_") + ".dbjson"
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar Duct Bank",
                                                      default, "Duct Bank (*.dbjson)")
        if not fn: return
        try:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self.scene.model.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error al guardar", str(e))

    def _on_help(self):
        QtWidgets.QMessageBox.information(self, "Ayuda — Duct Bank",
            "1) Empieza con <b>Rectángulo</b>: dos clics para dibujar la envolvente.<br>"
            "2) Elige un diámetro y usa <b>Conducto</b>: cada clic dentro de la "
            "envolvente coloca un conducto.<br>"
            "3) <b>Seleccionar</b> te muestra los datos del conducto en el panel; "
            "puedes cambiar X, Y, diámetro o etiqueta.<br>"
            "4) <b>Mover</b> arrastra un conducto; <b>Eliminar</b> quita el que "
            "hagas clic.<br>"
            "5) La rueda del ratón acerca/aleja; el botón central del ratón mueve la vista.<br>"
            "6) <b>Asigna una utilidad</b> en el combo de abajo para que el duct bank "
            "reemplace esa tubería al importar en Civil 3D.<br>"
            "7) Presiona <b>Guardar y cerrar</b> — el diseño se guarda en el proyecto "
            "y la utilidad asignada usará el duct bank en vez de una tubería normal.")

    def _update_pipe_status(self):
        idx = self.cmb_pipe.currentData()
        if idx is not None and idx >= 0:
            self.lbl_pipe_status.setText(
                "<span style='color:#2e7d32;font-weight:600;'>"
                "Al exportar, esta utilidad será un duct bank (no una tubería normal).</span>")
        else:
            self.lbl_pipe_status.setText(
                "<span style='color:#888;'>Sin asignar — el duct bank no se exportará.</span>")

    def _on_close(self):
        self.accept()

    def showEvent(self, e):
        # Maximizar en el primer show: hay que llamarlo cuando el WM ya tiene la
        # ventana registrada — hacerlo en __init__ no siempre pega. La bandera
        # `_start_maximized` se apaga tras la primera vez, para que si el usuario
        # sale del maximizado y hace algo que reabra el diálogo, se respete su
        # último tamaño en lugar de forzar maximizado otra vez.
        super().showEvent(e)
        if getattr(self, "_start_maximized", False):
            self._start_maximized = False
            self.showMaximized()


def open_designer(win, initial: Optional[DuctBank] = None) -> Optional[DuctBank]:
    """Abre el diálogo y devuelve el DuctBank final si el usuario aceptó, o None."""
    pipes = getattr(win, "pipes", None) or []
    dlg = DuctBankDialog(win, initial=initial, pipes=pipes)
    if dlg.exec() == QtWidgets.QDialog.Accepted:
        return dlg.result_model()
    return None
