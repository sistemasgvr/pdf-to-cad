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
                       snap, validate, conduit_fits_envelope, conduits_overlap)
import theme as _theme
from icons import icon as _icon
from i18n import t as _tr, N_


# ── Constantes visuales ─────────────────────────────────────────────────────
_INITIAL_PX_PER_IN = 60.0     # zoom inicial: 60 px = 1 pulgada
_MIN_ZOOM = 0.10
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


def _add_form_row(form: QtWidgets.QFormLayout, label_text: str,
                   field: QtWidgets.QWidget) -> QtWidgets.QLabel:
    """Añade una fila al QFormLayout y devuelve el QLabel creado, para poder
    mostrar/ocultar la fila entera después (label + campo). Sin esto, sólo
    podríamos ocultar el campo y el label quedaría huérfano."""
    lbl = QtWidgets.QLabel(label_text)
    form.addRow(lbl, field)
    return lbl


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
        self.btn_link.setToolTip(_tr("Vincular los cuatro valores.\n"
                                  "Cuando está activado, cambiar uno los actualiza a los cuatro."))
        self.btn_link.setFixedSize(44, 44)
        self.btn_link.setIconSize(QtCore.QSize(22, 22))
        self.btn_link.toggled.connect(self._refresh_link_icon)
        self._refresh_link_icon()

        # Etiquetas cortas alrededor de cada spinbox
        if layout_mode == "corners":
            lbls = (_tr("Sup. Izq."), _tr("Sup. Der."), _tr("Inf. Der."), _tr("Inf. Izq."))
        else:
            lbls = (_tr("Superior"), _tr("Derecho"), _tr("Inferior"), _tr("Izquierdo"))
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
            name, tip = "mdi:link-variant", N_("Vinculados (cambiar uno cambia los 4). Click para desvincular.")
            bg = t.accent
            fg = t.text_on_accent
        else:
            name, tip = "mdi:link-variant-off", N_("Independientes. Click para vincularlos.")
            bg = t.surface_alt
            fg = t.text
        self.btn_link.setIcon(_icon(name, color=fg))
        self.btn_link.setToolTip(_tr(tip))
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
    # Se emite cuando el usuario intenta colocar/mover un conducto y viola una
    # REGLA OBLIGATORIA (envolvente, separación mínima, resguardo al borde).
    # El diálogo lo conecta para mostrar el banner rojo con el mensaje.
    rule_violation = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = DuctBank()
        self.tool = "select"                  # select | conduit | move | delete
        self.snap_on = True
        # Toggle "Mostrar medidas" — dibuja cotas automáticas (rojo) entre
        # conductos adyacentes y desde cada conducto al borde de la envolvente
        # o al margen interior (lo más cercano). No es una herramienta del
        # canvas: es un overlay siempre-encima que no cambia self.tool.
        self.show_dimensions = False
        self.snap_step = DEFAULT_SNAP_IN
        self.new_conduit_diam = 4.0
        self.selected_idx: Optional[int] = None    # índice del conducto seleccionado
        self.envelope_selected = False
        self._dragging_idx: Optional[int] = None   # para "Mover"
        self._drag_offset = QtCore.QPointF(0, 0)
        # Posición ORIGINAL del conducto antes de arrastrar. Se usa para
        # revertir el movimiento si la posición final viola una regla
        # obligatoria (separación mínima entre conductos, resguardo al borde).
        self._drag_original_pos: Optional[tuple] = None
        self._measure_pts: List[QtCore.QPointF] = []
        # Ghost del conducto que se dibujaría al hacer click (herramienta
        # "conduit"): silueta translúcida verde si las reglas permiten, roja
        # si no. Se actualiza en mouseMoveEvent y se limpia al cambiar de
        # herramienta o al salir del canvas.
        self._ghost_pos: Optional[QtCore.QPointF] = None
        self._ghost_ok: bool = False
        # sceneRect dinámico — se recalcula en _update_scene_rect cada vez que
        # cambia el modelo, para que al hacer zoom + pan se pueda alcanzar
        # cualquier borde del contenedor. Inicial generoso por si el modelo
        # todavía no tiene dimensiones.
        self._update_scene_rect()

    def _update_scene_rect(self):
        """Ajusta el sceneRect al tamaño del bancoducto + márgenes generosos
        para poder pan/zoom sobre las cotas exteriores y aún un poco más allá.
        Se llama al arranque y cada vez que el modelo cambia."""
        w = max(1.0, float(self.model.width_in))
        h = max(1.0, float(self.model.height_in))
        # Padding proporcional al tamaño (mínimo 10", máximo 40") para que
        # bancoductos pequeños o grandes tengan espacio equivalente al mover.
        pad = max(10.0, min(40.0, max(w, h) * 1.5))
        self.setSceneRect(-pad, -pad, w + 2 * pad, h + 2 * pad)

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

    def _check_rules(self, cand: "Conduit", exclude_idx: Optional[int] = None):
        """Verifica si el conducto `cand` cumple todas las reglas obligatorias
        del bancoducto (envolvente, separación mínima entre conductos,
        resguardo al borde/margen). Devuelve None si OK, o un mensaje corto
        si viola alguna regla — pensado para mostrarse en el hint del canvas.

        Las reglas custom (rule_min_conduit_sep_in y rule_min_edge_clearance_in)
        se aplican SOLO si `rules_enabled` está ON y el valor > 0. Los chequeos
        básicos (dentro de envolvente, sin colisión gruesa) SIEMPRE aplican.
        """
        m = self.model
        if cand.diam <= 0:
            return _tr("Diámetro debe ser > 0.")
        # Con reglas activas, el "resguardo al borde" es la distancia mínima
        # entre el borde del conducto y el borde de la envolvente. Usamos
        # conduit_fits_envelope con margen=rule_min_edge_clearance_in.
        edge = float(m.rule_min_edge_clearance_in) if m.rules_enabled else 0.0
        if not conduit_fits_envelope(m, cand, margin=edge):
            if edge > 0:
                return _tr('El conducto viola el resguardo mínimo al borde '
                           '({v:g}").').format(v=edge)
            return _tr("El conducto queda fuera de la envolvente.")
        # Separación entre conductos (SIEMPRE hay que evitar solape físico —
        # incluso sin regla custom activa; y si hay regla, exigir sep. mínima).
        sep = float(m.rule_min_conduit_sep_in) if m.rules_enabled else 0.0
        for j, o in enumerate(m.conduits):
            if exclude_idx is not None and j == exclude_idx:
                continue
            if conduits_overlap(cand, o, tol=sep):
                if sep > 0:
                    return _tr('Separación entre conductos < {v:g}".').format(v=sep)
                return _tr("Los conductos se solapan.")
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
            # "Puntero" unificado: click selecciona, arrastrar mueve. Si el usuario
            # inicia el drag sobre un conducto seleccionado, empezamos a moverlo
            # (offset guardado para no saltar bajo el cursor).
            idx = self._hit_conduit(e.scenePos())
            if idx is not None:
                self.selected_idx = idx
                self.envelope_selected = False
                self._dragging_idx = idx
                c = self.model.conduits[idx]
                # Guardamos la posición original para poder REVERTIR el drag si
                # al soltar la nueva posición viola alguna regla obligatoria.
                self._drag_original_pos = (c.cx, c.cy)
                self._drag_offset = QtCore.QPointF(e.scenePos().x() - c.cx,
                                                    e.scenePos().y() - c.cy)
            elif self._hit_envelope_border(e.scenePos()):
                self.selected_idx = None
                self.envelope_selected = True
            else:
                self.selected_idx = None
                self.envelope_selected = False
            self.selection_changed.emit()
            self.update()

        elif self.tool == "conduit":
            cand = Conduit(cx=float(p.x()), cy=float(p.y()), diam=float(self.new_conduit_diam))
            # Reglas obligatorias: si viola cualquiera (envolvente, resguardo
            # al borde, separación mínima con vecinos), no se coloca.
            err = self._check_rules(cand)
            if err is not None:
                self.tool_hint.emit(err)
                self.rule_violation.emit(err)   # banner rojo visible
                return
            self.model.conduits.append(cand)
            self.selected_idx = len(self.model.conduits) - 1
            self.envelope_selected = False
            self.changed_model.emit(); self.selection_changed.emit(); self.update()

        elif self.tool == "move":
            idx = self._hit_conduit(e.scenePos())
            if idx is not None:
                self._dragging_idx = idx
                c = self.model.conduits[idx]
                self._drag_original_pos = (c.cx, c.cy)
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
        # Ghost del conducto en modo "dibujar": sigue al mouse (snapped) y
        # se pinta verde/rojo según si las reglas permiten dibujar ahí.
        if self.tool == "conduit":
            p = self._snap_pt(e.scenePos())
            cand = Conduit(cx=float(p.x()), cy=float(p.y()),
                            diam=float(self.new_conduit_diam))
            fits = conduit_fits_envelope(self.model, cand) if self.model.width_in > 0 else False
            err = self._check_rules(cand) if fits else "fuera"
            self._ghost_pos = p
            self._ghost_ok = (err is None and fits)
            self.update()
        # El drag funciona tanto en "select" (Puntero unificado) como en "move"
        # (legacy — mantenemos el modo por compatibilidad).
        if self.tool in ("select", "move") and self._dragging_idx is not None:
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
        if self.tool in ("select", "move") and self._dragging_idx is not None:
            idx = self._dragging_idx
            self._dragging_idx = None
            # Validación estricta al SOLTAR: si la posición final viola una
            # regla obligatoria, revertimos al lugar original y avisamos.
            # (Se evalúa después de dropear el _dragging_idx para que si el
            # usuario vuelve a arrastrar el mismo conducto, no se confunda.)
            if 0 <= idx < len(self.model.conduits) and self._drag_original_pos is not None:
                c = self.model.conduits[idx]
                err = self._check_rules(c, exclude_idx=idx)
                if err is not None:
                    ox, oy = self._drag_original_pos
                    c.cx, c.cy = ox, oy
                    self.tool_hint.emit(err)
                    self.rule_violation.emit(err)
                    self.update()
            self._drag_original_pos = None
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
        # (Los ejes X/Y 0-0 antes se dibujaban más marcados; se removieron por
        # petición del usuario — molestaban al ver la cuadrícula regular.)

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
            # Cuadrícula 1"×1" DENTRO del contenedor. La rejilla del fondo
            # (drawBackground) queda tapada por el fill azul de la envolvente;
            # aquí la re-pintamos por encima, recortada al rectángulo del
            # contenedor. Usamos el color del BORDE de la envolvente (que ya
            # está diseñado para contrastar con el fill en ambos temas) con
            # alpha alto — así se ve claramente en oscuro y en claro.
            painter.save()
            painter.setClipRect(env_rect)
            grid_col = QtGui.QColor(_theme.tokens().envelope_border)
            grid_col.setAlpha(180)
            painter.setPen(QtGui.QPen(grid_col, 0))
            xx = math.floor(env_rect.left()) + 1
            while xx < env_rect.right():
                painter.drawLine(QtCore.QPointF(xx, env_rect.top()),
                                  QtCore.QPointF(xx, env_rect.bottom()))
                xx += _GRID_MAJOR_IN
            yy = math.floor(env_rect.top()) + 1
            while yy < env_rect.bottom():
                painter.drawLine(QtCore.QPointF(env_rect.left(), yy),
                                  QtCore.QPointF(env_rect.right(), yy))
                yy += _GRID_MAJOR_IN
            painter.restore()
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
            # Conductos de 1" son muy pequeños: usamos una fracción mayor
            # del diámetro para que el número quepa; el resto mantiene 0.28.
            factor = 0.55 if c.diam <= 1.0 else 0.28
            f = painter.font(); f.setPointSizeF(factor * (r * 2))
            painter.setFont(f)
            txt = c.label or f'{c.diam:g}"'
            painter.drawText(QtCore.QRectF(c.cx - r, c.cy - r, r * 2, r * 2),
                             QtCore.Qt.AlignCenter, txt)
        # Ghost del conducto a colocar (herramienta "conduit"): silueta
        # translúcida verde=OK, roja=violaría regla. Se dibuja después de los
        # conductos reales para quedar encima.
        if self.tool == "conduit" and self._ghost_pos is not None:
            gr = float(self.new_conduit_diam) / 2.0
            if self._ghost_ok:
                border = QtGui.QColor(30, 170, 60)
                fill = QtGui.QColor(30, 170, 60, 90)
            else:
                border = QtGui.QColor(210, 40, 40)
                fill = QtGui.QColor(210, 40, 40, 90)
            painter.setBrush(QtGui.QBrush(fill))
            painter.setPen(QtGui.QPen(border, 0.06))
            painter.drawEllipse(self._ghost_pos, gr, gr)

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
        # Se suprime si el toggle "Mostrar medidas" está ON — evita duplicar
        # cotas (las mismas aparecen en rojo para todos los conductos).
        if (self.selected_idx is not None
                and 0 <= self.selected_idx < len(d.conduits)
                and d.width_in > 0 and d.height_in > 0
                and not self.show_dimensions):
            self._draw_neighbor_dims(painter, d, self.selected_idx)

        # ── Cotas GLOBALES (toggle "Mostrar medidas") ───────────────────
        # En ROJO, muestra: (a) hueco borde-a-borde entre cada par de
        # conductos adyacentes horizontal/verticalmente y (b) resguardo de
        # cada conducto hasta la envolvente o el margen interior (lo más
        # cercano) en las 4 direcciones donde no haya otro conducto.
        if self.show_dimensions and d.width_in > 0 and d.height_in > 0:
            self._draw_all_dimensions(painter, d)

    def _draw_dimensions(self, painter, d):
        """Cotas exteriores estilo plano: tick perpendicular en cada extremo,
        línea larga entre ticks y valor en pulgadas EN EL MEDIO de la línea
        (con un rectángulo de fondo del color del canvas para que el texto se
        vea sin chocar con la línea).

        Las 4 direcciones (arriba/abajo/izquierda/derecha) muestran ancho/alto
        de la envolvente."""
        offset = 1.0           # distancia entre el borde de la envolvente y la cota
        tick = 0.18            # medio-alto del tick perpendicular
        color = QtGui.QColor(_theme.tokens().text)
        pen_line = QtGui.QPen(color, 0.03)
        font = painter.font(); font.setPointSizeF(0.34); painter.setFont(font)

        w, h = d.width_in, d.height_in
        bg = _grid_bg_color()   # fondo detrás del texto (mismo del lienzo)

        # ── Cota SUPERIOR (mide ancho) ──
        y = -offset
        painter.setPen(pen_line)
        painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(w, y))
        painter.drawLine(QtCore.QPointF(0, y - tick), QtCore.QPointF(0, y + tick))
        painter.drawLine(QtCore.QPointF(w, y - tick), QtCore.QPointF(w, y + tick))
        self._draw_centered_label(painter, QtCore.QPointF(w / 2.0, y),
                                   f'{w:.2f}"', color, bg, horizontal=True)

        # ── Cota INFERIOR (mide ancho) ──
        y = h + offset
        painter.setPen(pen_line)
        painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(w, y))
        painter.drawLine(QtCore.QPointF(0, y - tick), QtCore.QPointF(0, y + tick))
        painter.drawLine(QtCore.QPointF(w, y - tick), QtCore.QPointF(w, y + tick))
        self._draw_centered_label(painter, QtCore.QPointF(w / 2.0, y),
                                   f'{w:.2f}"', color, bg, horizontal=True)

        # ── Cota IZQUIERDA (mide alto) ──
        x = -offset
        painter.setPen(pen_line)
        painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, h))
        painter.drawLine(QtCore.QPointF(x - tick, 0), QtCore.QPointF(x + tick, 0))
        painter.drawLine(QtCore.QPointF(x - tick, h), QtCore.QPointF(x + tick, h))
        self._draw_centered_label(painter, QtCore.QPointF(x, h / 2.0),
                                   f'{h:.2f}"', color, bg, horizontal=False)

        # ── Cota DERECHA (mide alto) ──
        x = w + offset
        painter.setPen(pen_line)
        painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, h))
        painter.drawLine(QtCore.QPointF(x - tick, 0), QtCore.QPointF(x + tick, 0))
        painter.drawLine(QtCore.QPointF(x - tick, h), QtCore.QPointF(x + tick, h))
        self._draw_centered_label(painter, QtCore.QPointF(x, h / 2.0),
                                   f'{h:.2f}"', color, bg, horizontal=False)

    def _draw_centered_label(self, painter, center: QtCore.QPointF, txt: str,
                              color: QtGui.QColor, bg: QtGui.QColor,
                              horizontal: bool = True):
        """Dibuja el valor de una cota (ej. `2.00"`) EN MEDIO de la línea.

        El texto SIEMPRE mide 8 device pixels en pantalla, independiente del
        zoom del canvas. Esto se logra reseteando la escala del painter antes
        de dibujar el font — así 8 pixel size = 8 pixels reales en pantalla.
        Ventaja: el número NO crece descontroladamente al hacer zoom in
        (que era el reclamo del usuario cuando el texto era scene-proporcional).

        - horizontal=True → texto horizontal centrado en (x, y).
        - horizontal=False → texto rotado -90° (cotas verticales).
        """
        painter.save()
        try:
            # Leer m11 ANTES de rotar (tras rotate(-90), m11 = cos(-90°) ≈ 0
            # y romperíamos el cálculo del pixelSize).
            m11 = abs(painter.transform().m11()) or 1.0
            painter.translate(center)
            if not horizontal:
                painter.rotate(-90)
            # Contenedor de altura fija = 1 pulgada de escena (igual que la
            # rejilla). Reseteamos el scale del painter a device coords y
            # dimensionamos todo en pixels: box_h_px = 1" × (px por pulgada).
            painter.scale(1.0 / m11, 1.0 / m11)
            box_h_px = 1.0 * m11
            f = painter.font()
            # Texto ocupa ~70% del alto (deja 15% de padding arriba/abajo).
            target_px = max(4, int(round(box_h_px * 0.70)))
            f.setPixelSize(target_px); painter.setFont(f)
            fm = QtGui.QFontMetricsF(f)
            tw = fm.horizontalAdvance(txt)
            pad_x = box_h_px * 0.15
            box = QtCore.QRectF(-tw / 2 - pad_x, -box_h_px / 2,
                                tw + 2 * pad_x, box_h_px)
            # Fondo del color del lienzo (bg) para "cortar" la línea de cota.
            painter.setBrush(QtGui.QBrush(bg))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(box)
            # Texto encima.
            painter.setPen(QtGui.QPen(color))
            painter.drawText(box, QtCore.Qt.AlignCenter, txt)
        finally:
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

    def _draw_all_dimensions(self, painter, d):
        """Toggle "Mostrar medidas": dibuja en ROJO todas las cotas útiles del
        diseño — separación borde-a-borde entre pares de conductos alineados
        (horizontal y vertical) y resguardo desde cada conducto al obstáculo
        más cercano (envolvente o margen interior) en las direcciones donde
        no lo tape otro conducto.

        Deduplica los pares conducto↔conducto: la cota entre A y B se pinta
        una sola vez, no dos.
        """
        red = QtGui.QColor(_theme.tokens().danger)
        pen = QtGui.QPen(red, 0.028)
        painter.setPen(pen)
        f = painter.font(); f.setPointSizeF(0.32); painter.setFont(f)
        tick = 0.12
        bg = _grid_bg_color()

        def _draw_h(x0, x1, y, txt):
            span = abs(x1 - x0)
            if span < 0.05: return
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(x0, y), QtCore.QPointF(x1, y))
            painter.drawLine(QtCore.QPointF(x0, y - tick), QtCore.QPointF(x0, y + tick))
            painter.drawLine(QtCore.QPointF(x1, y - tick), QtCore.QPointF(x1, y + tick))
            # Etiqueta en el MEDIO de la línea, con fondo del lienzo para que
            # el texto no se pise con la línea de cota.
            self._draw_centered_label(painter,
                                       QtCore.QPointF((x0 + x1) / 2.0, y),
                                       txt, red, bg, horizontal=True)

        def _draw_v(y0, y1, x, txt):
            span = abs(y1 - y0)
            if span < 0.05: return
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(x, y0), QtCore.QPointF(x, y1))
            painter.drawLine(QtCore.QPointF(x - tick, y0), QtCore.QPointF(x + tick, y0))
            painter.drawLine(QtCore.QPointF(x - tick, y1), QtCore.QPointF(x + tick, y1))
            self._draw_centered_label(painter,
                                       QtCore.QPointF(x, (y0 + y1) / 2.0),
                                       txt, red, bg, horizontal=False)

        # Cache de límites: la cota "al borde" del toggle "Mostrar medidas"
        # SIEMPRE apunta al borde de la ENVOLVENTE (no al margen interior).
        # El margen interior es solo una guía visual — no un obstáculo físico —
        # y la regla `rule_min_edge_clearance_in` se mide contra la envolvente.
        env_left, env_right = 0.0, d.width_in
        env_top, env_bot = 0.0, d.height_in

        # Set para deduplicar pares (i, j) — clave ordenada.
        pairs_h_drawn = set()   # pares dibujados como cota HORIZONTAL
        pairs_v_drawn = set()   # pares dibujados como cota VERTICAL

        for idx, c in enumerate(d.conduits):
            if c.diam <= 0: continue
            r = c.diam / 2.0
            left_x, right_x = c.cx - r, c.cx + r
            top_y, bot_y = c.cy - r, c.cy + r

            # Buscar el conducto vecino más cercano en cada dirección
            # (mismo criterio que _draw_neighbor_dims: solapa perpendicular).
            left_hit_v = None; left_hit_j = None
            right_hit_v = None; right_hit_j = None
            top_hit_v = None; top_hit_j = None
            bot_hit_v = None; bot_hit_j = None
            for j, o in enumerate(d.conduits):
                if j == idx or o.diam <= 0: continue
                ro = o.diam / 2.0
                # Horizontal (solapa en Y)
                if abs(o.cy - c.cy) <= (r + ro):
                    if o.cx + ro <= left_x + 1e-6:
                        if left_hit_v is None or o.cx + ro > left_hit_v:
                            left_hit_v = o.cx + ro; left_hit_j = j
                    elif o.cx - ro >= right_x - 1e-6:
                        if right_hit_v is None or o.cx - ro < right_hit_v:
                            right_hit_v = o.cx - ro; right_hit_j = j
                # Vertical (solapa en X)
                if abs(o.cx - c.cx) <= (r + ro):
                    if o.cy + ro <= top_y + 1e-6:
                        if top_hit_v is None or o.cy + ro > top_hit_v:
                            top_hit_v = o.cy + ro; top_hit_j = j
                    elif o.cy - ro >= bot_y - 1e-6:
                        if bot_hit_v is None or o.cy - ro < bot_hit_v:
                            bot_hit_v = o.cy - ro; bot_hit_j = j

            # ─ Cota IZQUIERDA
            if left_hit_j is not None:
                key = tuple(sorted((idx, left_hit_j)))
                if key not in pairs_h_drawn:
                    pairs_h_drawn.add(key)
                    _draw_h(left_hit_v, left_x, c.cy, f'{left_x - left_hit_v:.2f}"')
            else:
                # Al borde/margen izquierdo
                _draw_h(env_left, left_x, c.cy, f'{left_x - env_left:.2f}"')

            # ─ Cota DERECHA
            if right_hit_j is not None:
                key = tuple(sorted((idx, right_hit_j)))
                if key not in pairs_h_drawn:
                    pairs_h_drawn.add(key)
                    _draw_h(right_x, right_hit_v, c.cy, f'{right_hit_v - right_x:.2f}"')
            else:
                _draw_h(right_x, env_right, c.cy, f'{env_right - right_x:.2f}"')

            # ─ Cota ARRIBA
            if top_hit_j is not None:
                key = tuple(sorted((idx, top_hit_j)))
                if key not in pairs_v_drawn:
                    pairs_v_drawn.add(key)
                    _draw_v(top_hit_v, top_y, c.cx, f'{top_y - top_hit_v:.2f}"')
            else:
                _draw_v(env_top, top_y, c.cx, f'{top_y - env_top:.2f}"')

            # ─ Cota ABAJO
            if bot_hit_j is not None:
                key = tuple(sorted((idx, bot_hit_j)))
                if key not in pairs_v_drawn:
                    pairs_v_drawn.add(key)
                    _draw_v(bot_y, bot_hit_v, c.cx, f'{bot_hit_v - bot_y:.2f}"')
            else:
                _draw_v(bot_y, env_bot, c.cx, f'{env_bot - bot_y:.2f}"')


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

    def leaveEvent(self, e):
        # Al salir del canvas, ocultamos el ghost del conducto.
        sc = self.scene()
        if sc is not None and getattr(sc, "_ghost_pos", None) is not None:
            sc._ghost_pos = None
            sc.update()
        super().leaveEvent(e)

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
        self.setWindowTitle(_tr("Diseñador de Duct Bank"))
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
            # Al cargar un modelo con dimensiones ya definidas, ajustamos el
            # sceneRect antes de que la vista se conecte — así el usuario
            # puede pan/zoom hasta los bordes desde el primer momento.
            self.scene._update_scene_rect()
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
        # Reaccionar a cambio de idioma en vivo. Se reconstruye buena parte de
        # los textos + se llama a _refresh_panel para regenerar hints dinámicos.
        import i18n as _i18n_bus
        _i18n_bus.LANG_BUS.changed.connect(self._retranslate)

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
                                     f"{_tr('Diseñador de Duct Bank')}</span><br>"
                                     "<span style='color:#d7e5ff;font-size:12px;'>"
                                     f"{_tr('Cara Interior (Corte Longitudinal)')}</span>")
        h.addWidget(lbl_title); h.addStretch(1)
        # Header simplificado: SOLO acciones que se usan durante el diseño
        # (Deshacer/Rehacer/Ayuda). Nuevo/Abrir/Guardar del proyecto se manejan
        # desde la ventana principal (pestaña "Bancoductos"); no tiene sentido
        # duplicarlos aquí. Las acciones primarias (Cancelar / Guardar y cerrar)
        # van abajo, alineadas a la derecha del canvas para ser lo último que ve
        # el usuario tras diseñar.
        self.btn_undo = QtWidgets.QPushButton("  " + _tr("Deshacer"))
        self.btn_redo = QtWidgets.QPushButton("  " + _tr("Rehacer"))
        self.btn_help = QtWidgets.QPushButton("  " + _tr("Ayuda"))
        self._header_buttons = [self.btn_undo, self.btn_redo, self.btn_help]
        # Mapa botón → nombre de icono (para _restyle: reasignar al cambiar tema).
        self._header_icon_map = {
            self.btn_undo: "mdi:undo-variant",
            self.btn_redo: "mdi:redo-variant",
            self.btn_help: "mdi:help-circle-outline",
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
        # "Puntero" fusiona Seleccionar + Mover: click selecciona, arrastrar mueve
        # (patrón moderno de Figma/Illustrator/etc). Reduce el número de
        # herramientas y elimina la fricción de tener que cambiar entre las dos.
        self.tb_sel = _tool_btn("mdi:cursor-default-outline", _tr("Puntero"), "select",
                                _tr("Click para seleccionar un conducto.\n"
                                    "Arrastra un conducto para moverlo."))
        self.tb_conduit = _tool_btn("mdi:circle-outline", _tr("Conducto\n(Círculo)"), "conduit",
                                    _tr("Click dentro de la envolvente para colocar un conducto del diámetro elegido."))
        # (La herramienta "Rectángulo" se retiró: el contenedor siempre existe con
        #  medidas por defecto y el usuario ajusta Ancho/Alto en el panel derecho.)
        # ── Toggle "Mostrar medidas" ─────────────────────────────────────
        # NO es una herramienta del canvas (no cambia self.tool ni entra en
        # el ButtonGroup exclusivo). Es un overlay: al activarlo, el canvas
        # dibuja todas las cotas en rojo — hueco entre conductos alineados y
        # resguardo de cada conducto a la envolvente/margen. Al desactivarlo,
        # las cotas desaparecen. Cambia texto e icono según el estado.
        self.tb_dimensions = QtWidgets.QToolButton()
        self.tb_dimensions.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.tb_dimensions.setCheckable(True)
        self.tb_dimensions.setIconSize(QtCore.QSize(28, 28))
        self.tb_dimensions.setProperty("danger", "false")
        self.tb_dimensions.clicked.connect(self._toggle_dimensions)
        self._tool_buttons.append(self.tb_dimensions)
        # El icono se re-tinta en _restyle; guardamos el nombre "current" allí.
        self._tool_icon_map[self.tb_dimensions] = "mdi:ruler"
        tv.addWidget(self.tb_dimensions)
        self._refresh_dimensions_button()   # etiqueta y tooltip iniciales
        self.tb_delete = _tool_btn("mdi:trash-can-outline", _tr("Eliminar"), "delete",
                                   _tr("Click en un conducto para eliminarlo."), danger=True)
        tv.addSpacing(10)
        # Zoom + ajustar
        def _plain_btn(icon_name, label, tip, fn):
            b = QtWidgets.QToolButton()
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            b.setText(label); b.setToolTip(tip)
            b.setIconSize(QtCore.QSize(28, 28))
            b.clicked.connect(fn); self._tool_buttons.append(b); self._tool_icon_map[b] = icon_name
            tv.addWidget(b); return b
        self.btn_zin = _plain_btn("mdi:magnify-plus-outline", _tr("Zoom +"), _tr("Acercar"), lambda: self._zoom(1.15))
        self.btn_zout = _plain_btn("mdi:magnify-minus-outline", _tr("Zoom −"), _tr("Alejar"), lambda: self._zoom(1 / 1.15))
        self.btn_fit = _plain_btn("mdi:image-filter-center-focus", _tr("Ajustar"),
                                    _tr("Centrar la vista sobre la envolvente"), self._fit)
        tv.addStretch(1)
        body_l.addWidget(tools_wrap, 0)

        # Zona central: canvas + banner de errores (overlay) + footer + acciones
        center = QtWidgets.QVBoxLayout(); center.setSpacing(4)

        # Contenedor del canvas para permitir un banner de error overlay
        # posicionado ABSOLUTAMENTE encima del canvas (mejora #3).
        canvas_wrap = QtWidgets.QWidget()
        cwl = QtWidgets.QVBoxLayout(canvas_wrap)
        cwl.setContentsMargins(0, 0, 0, 0); cwl.setSpacing(0)
        cwl.addWidget(self.view, 1)
        # Banner de error persistente — hijo del canvas_wrap, se posiciona en el
        # tope centrado en cada resize (ver eventFilter). Oculto cuando no hay
        # errores de validate().
        self.lbl_error_banner = QtWidgets.QLabel(canvas_wrap)
        self.lbl_error_banner.setWordWrap(True)
        self.lbl_error_banner.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_error_banner.setVisible(False)
        self.lbl_error_banner.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        canvas_wrap.installEventFilter(self)
        self._canvas_wrap = canvas_wrap
        center.addWidget(canvas_wrap, 1)

        # Barra inferior — snap + estado. El slider de zoom se quitó (mejora #6):
        # ya hay botones +/-/Ajustar en la toolbar izquierda y la rueda del
        # ratón. Se mantiene el % como indicador de solo lectura.
        footer = QtWidgets.QFrame(); self._footer = footer   # estilo por _restyle
        fh = QtWidgets.QHBoxLayout(footer); fh.setContentsMargins(12, 6, 12, 6); fh.setSpacing(14)
        self.lbl_status = QtWidgets.QLabel(_tr("Rejilla activada · 1 punto = 1 pulgada"))
        # color por _restyle
        fh.addWidget(self.lbl_status)
        fh.addStretch(1)
        # "Imán" al retículo de 0.25 pulgadas del lienzo (subrejilla punteada
        # de fondo). Con esto ON, cada clic para poner/mover un conducto o
        # medir queda ajustado al múltiplo de 0.25". Con OFF, precisión libre.
        self.chk_snap = QtWidgets.QCheckBox(_tr("Ajuste a rejilla (0.25\")"))
        self.chk_snap.setChecked(True)
        self.chk_snap.setToolTip(_tr(
            "Cuando está activado, los clics del ratón se pegan (imán) al retículo\n"
            "de 0.25 pulgadas del fondo del lienzo. Sirve para colocar conductos\n"
            "y medir con precisión ⅟₄ pulgada.\n\n"
            "Desactívalo si necesitas posicionar algo en un valor libre no múltiplo\n"
            "de 0.25\"."))
        fh.addWidget(self.chk_snap)
        self.lbl_zoom = QtWidgets.QLabel("100%"); self.lbl_zoom.setFixedWidth(58)
        self.lbl_zoom.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_zoom.setToolTip(_tr("Nivel de zoom actual.\n"
                                    "Usa los botones Zoom +/- de la toolbar\n"
                                    "o la rueda del ratón."))
        fh.addWidget(self.lbl_zoom)
        center.addWidget(footer, 0)

        # ── Acciones primarias abajo del canvas (mejora #1) ───────────────────
        # Cancelar (secundario) + Guardar y cerrar (primario). Alineadas a la
        # derecha del canvas para ser lo último que ve el usuario tras diseñar.
        actions = QtWidgets.QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0); actions.setSpacing(8)
        actions.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancel.setMinimumHeight(38); self.btn_cancel.setMinimumWidth(120)
        self.btn_cancel.setToolTip(_tr("Cerrar sin guardar cambios."))
        self.btn_close = QtWidgets.QPushButton("  " + _tr("Guardar y cerrar"))
        self.btn_close.setIcon(_icon("mdi:check", color="#ffffff"))
        self.btn_close.setIconSize(QtCore.QSize(20, 20))
        self.btn_close.setMinimumHeight(38); self.btn_close.setMinimumWidth(180)
        self.btn_close.setToolTip(_tr("Guardar el bancoducto en el proyecto y cerrar el diseñador."))
        self.btn_close.setDefault(True)
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.btn_close)
        center.addLayout(actions, 0)

        body_l.addLayout(center, 1)

        # Panel derecho: propiedades
        # El panel derecho es alto (varios groupboxes) y con widgets espaciales
        # (compass/corners). Antes tenía ancho fijo 260 → contenido cortado en
        # pantallas chicas. Ahora el frame vive dentro de un QScrollArea:
        # ancho preferente ~340, scroll vertical automático si no cabe.
        side = QtWidgets.QFrame(); self._side = side   # estilo por _restyle
        sv = QtWidgets.QVBoxLayout(side); sv.setContentsMargins(10, 10, 10, 10); sv.setSpacing(10)

        # ── 1) IDENTIFICACIÓN — al tope, es lo primero que el usuario piensa ──
        # Nombre + Asignar a utilidad. Un bancoducto sin asignar a una tubería
        # no se exporta; que sea lo primero visible reduce el olvido más común.
        gid = QtWidgets.QGroupBox(_tr("Identificación")); gid.setProperty("_orig_title", "Identificación")
        gidl = QtWidgets.QFormLayout(gid)
        self.ed_name = QtWidgets.QLineEdit()
        self.ed_name.setPlaceholderText(_tr("Ej. Duct Bank A – Telecom"))
        gidl.addRow(_tr("Nombre:"), self.ed_name)
        self.cmb_pipe = QtWidgets.QComboBox()
        self.cmb_pipe.addItem(_tr("(Sin asignar)"), -1)
        _vertices_word = _tr("vértices")
        for i, p in enumerate(self._pipes):
            if not p.get("pts"): continue
            layer = p.get("layer", "?")
            n_pts = len(p.get("pts", []))
            diam = p.get("diam") or "?"
            label = f"#{i+1}  {layer}  —  {diam}\"  ({n_pts} {_vertices_word})"
            self.cmb_pipe.addItem(label, i)
        cur_idx = self.scene.model.pipe_idx
        if cur_idx >= 0:
            for ci in range(self.cmb_pipe.count()):
                if self.cmb_pipe.itemData(ci) == cur_idx:
                    self.cmb_pipe.setCurrentIndex(ci)
                    break
        gidl.addRow(_tr("Asignar a:"), self.cmb_pipe)
        self.lbl_pipe_status = QtWidgets.QLabel("")
        self.lbl_pipe_status.setWordWrap(True)
        gidl.addRow(self.lbl_pipe_status)
        self._update_pipe_status()
        sv.addWidget(gid)

        # ── 1b) REGLAS DE DISEÑO — separación entre conductos y al borde ─────
        # Toggle maestro + sub-controles con progressive disclosure (grayed
        # cuando el toggle está OFF). Los valores en 0" significan "sin regla"
        # para ese campo aunque el toggle esté ON — permite tener solo una
        # regla activa sin desactivarlas todas.
        grules = QtWidgets.QGroupBox(_tr("Reglas de diseño")); grules.setProperty("_orig_title", "Reglas de diseño")
        grl = QtWidgets.QVBoxLayout(grules)
        grl.setContentsMargins(8, 8, 8, 6); grl.setSpacing(6)
        self.chk_rules = QtWidgets.QCheckBox(_tr("Aplicar reglas"))
        self.chk_rules.setChecked(True)
        self.chk_rules.setToolTip(_tr(
            "Activa las reglas de diseño personalizables abajo.\n\n"
            "Cuando está DESACTIVADO, el diseño puede colocar conductos sin\n"
            "respetar ninguna separación ni resguardo (los chequeos geométricos\n"
            "básicos — dentro de envolvente, sin colisión gruesa — siguen)."))
        grl.addWidget(self.chk_rules)
        # Sub-form con los dos valores
        _rf = QtWidgets.QFormLayout(); _rf.setContentsMargins(0, 0, 0, 0)
        _rf.setSpacing(4); _rf.setHorizontalSpacing(6)
        self.sp_rule_sep = QtWidgets.QDoubleSpinBox()
        self.sp_rule_sep.setRange(0.0, 50.0); self.sp_rule_sep.setDecimals(2)
        self.sp_rule_sep.setSingleStep(0.25); self.sp_rule_sep.setSuffix('"')
        self.sp_rule_sep.setValue(0.0)
        self.sp_rule_sep.setToolTip(_tr("Hueco mínimo entre bordes de conductos.\n"
                                     "0\" = sin regla."))
        _rf.addRow(_tr("Sep. entre conductos:"), self.sp_rule_sep)
        self.sp_rule_edge = QtWidgets.QDoubleSpinBox()
        self.sp_rule_edge.setRange(0.0, 50.0); self.sp_rule_edge.setDecimals(2)
        self.sp_rule_edge.setSingleStep(0.25); self.sp_rule_edge.setSuffix('"')
        self.sp_rule_edge.setValue(0.0)
        self.sp_rule_edge.setToolTip(_tr("Distancia mínima entre borde del conducto\n"
                                      "y borde de la envolvente. 0\" = sin regla."))
        _rf.addRow(_tr("Dist. al borde:"), self.sp_rule_edge)
        grl.addLayout(_rf)
        self.lbl_rules_hint = QtWidgets.QLabel("")
        self.lbl_rules_hint.setWordWrap(True)
        grl.addWidget(self.lbl_rules_hint)
        sv.addWidget(grules)

        # ── 2) CONDUCTO — panel contextual (mejora #7) ───────────────────────
        # Un solo groupbox reemplaza los antiguos "Nuevo conducto" + "Conducto
        # seleccionado" — el título y los campos cambian según haya selección.
        self.grp_conduit = QtWidgets.QGroupBox(_tr("Conducto")); self.grp_conduit.setProperty("_orig_title", "Conducto")
        gcv = QtWidgets.QVBoxLayout(self.grp_conduit)
        gcv.setContentsMargins(8, 8, 8, 6); gcv.setSpacing(6)
        # Sub-form para los campos (X/Y/Diám/Etiqueta o solo Diám según modo)
        gcf = QtWidgets.QFormLayout()
        # Diámetro para colocar el próximo conducto (visible SIN selección).
        self.sp_new_diam = QtWidgets.QDoubleSpinBox()
        self.sp_new_diam.setRange(0.25, 50); self.sp_new_diam.setDecimals(2)
        self.sp_new_diam.setSingleStep(0.25); self.sp_new_diam.setSuffix('"')
        self.sp_new_diam.setValue(4.0)
        self._row_new_diam = _add_form_row(gcf, _tr("Diámetro:"), self.sp_new_diam)
        # Campos de edición (visibles solo con selección)
        self.sel_x = QtWidgets.QDoubleSpinBox(); self.sel_x.setRange(0, 200); self.sel_x.setDecimals(2); self.sel_x.setSuffix('"')
        self.sel_y = QtWidgets.QDoubleSpinBox(); self.sel_y.setRange(0, 200); self.sel_y.setDecimals(2); self.sel_y.setSuffix('"')
        self.sel_d = QtWidgets.QDoubleSpinBox(); self.sel_d.setRange(0.25, 50); self.sel_d.setDecimals(2); self.sel_d.setSuffix('"')
        self.sel_lbl = QtWidgets.QLineEdit(); self.sel_lbl.setPlaceholderText(_tr("Etiqueta (opcional)"))
        self._row_sel_x = _add_form_row(gcf, _tr("X:"), self.sel_x)
        self._row_sel_y = _add_form_row(gcf, _tr("Y:"), self.sel_y)
        self._row_sel_d = _add_form_row(gcf, _tr("Diám. real:"), self.sel_d)
        self._row_sel_lbl = _add_form_row(gcf, _tr("Etiqueta:"), self.sel_lbl)
        gcv.addLayout(gcf)
        # Hint contextual (cambia según modo)
        self.lbl_conduit_hint = QtWidgets.QLabel("")
        self.lbl_conduit_hint.setWordWrap(True)
        gcv.addWidget(self.lbl_conduit_hint)
        self.btn_del_sel = QtWidgets.QPushButton("  " + _tr("Eliminar conducto"))
        self.btn_del_sel.setIconSize(QtCore.QSize(18, 18))
        self.btn_del_sel.setProperty("danger", "true")   # el QSS global tiñe rojo
        gcv.addWidget(self.btn_del_sel)
        sv.addWidget(self.grp_conduit)

        # ── 3) ENVOLVENTE — dimensiones exteriores del contenedor ─────────────
        genv = QtWidgets.QGroupBox(_tr("Envolvente (pulgadas)")); genv.setProperty("_orig_title", "Envolvente (pulgadas)")
        gel = QtWidgets.QFormLayout(genv)
        self.sp_w = QtWidgets.QDoubleSpinBox(); self.sp_w.setRange(0.25, 200); self.sp_w.setDecimals(2); self.sp_w.setSuffix('"')
        self.sp_h = QtWidgets.QDoubleSpinBox(); self.sp_h.setRange(0.25, 200); self.sp_h.setDecimals(2); self.sp_h.setSuffix('"')
        gel.addRow(_tr("Ancho:"), self.sp_w); gel.addRow(_tr("Alto:"), self.sp_h)
        sv.addWidget(genv)

        # Margen interior (guía) — editor estilo Photoshop en disposición compás.
        gmarg = QtWidgets.QGroupBox(_tr("Margen interior (pulgadas)")); gmarg.setProperty("_orig_title", "Margen interior (pulgadas)")
        gml = QtWidgets.QVBoxLayout(gmarg); gml.setContentsMargins(4, 4, 4, 4)
        self.ed_margin = _FourSideEditor(self, layout_mode="compass",
                                          maximum=50.0, step=0.25, decimals=2)
        gml.addWidget(self.ed_margin)
        sv.addWidget(gmarg)

        # Redondeo de esquinas — editor estilo Photoshop en disposición esquinas.
        gcor = QtWidgets.QGroupBox(_tr("Redondeo de esquinas (pulgadas)")); gcor.setProperty("_orig_title", "Redondeo de esquinas (pulgadas)")
        gcl = QtWidgets.QVBoxLayout(gcor); gcl.setContentsMargins(4, 4, 4, 4)
        self.ed_corners = _FourSideEditor(self, layout_mode="corners",
                                           maximum=20.0, step=0.25, decimals=2)
        gcl.addWidget(self.ed_corners)
        sv.addWidget(gcor)

        # ── Visualización (qué se dibuja en Civil 3D al importar) ─────────────
        gviz = QtWidgets.QGroupBox(_tr("Visualización en Civil 3D")); gviz.setProperty("_orig_title", "Visualización en Civil 3D")
        gvl = QtWidgets.QVBoxLayout(gviz)
        gvl.setContentsMargins(8, 8, 8, 6); gvl.setSpacing(4)
        self.chk_render_envelope = QtWidgets.QCheckBox(_tr("Dibujar contenedor 3D"))
        self.chk_render_envelope.setChecked(True)
        self.chk_render_envelope.setToolTip(_tr(
            "Al importar en Civil 3D, crea el sólido 3D del contenedor\n"
            "(prisma de concreto) además de los conductos internos.\n\n"
            "Desactívalo si el contenedor ya existe en el DWG o si solo\n"
            "necesitas los conductos como pipes."))
        gvl.addWidget(self.chk_render_envelope)
        self.lbl_render_hint = QtWidgets.QLabel("")
        self.lbl_render_hint.setWordWrap(True)
        gvl.addWidget(self.lbl_render_hint)
        sv.addWidget(gviz)

        # Contador + validación
        self.lbl_count = QtWidgets.QLabel(_tr("Conductos: 0"))
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

    def _retranslate(self, *_):
        """Re-aplica todos los textos traducibles al cambiar el idioma en vivo.
        No recrea widgets — solo actualiza sus setText/setTitle/setToolTip."""
        try:
            self.setWindowTitle(_tr("Diseñador de Duct Bank"))
            # Header
            for hdr in getattr(self, "_header", []) if False else []: pass  # no-op guard
            if hasattr(self, "btn_undo"): self.btn_undo.setText("  " + _tr("Deshacer"))
            if hasattr(self, "btn_redo"): self.btn_redo.setText("  " + _tr("Rehacer"))
            if hasattr(self, "btn_help"): self.btn_help.setText("  " + _tr("Ayuda"))
            # Título del header (HTML rico)
            try:
                for lbl in self._header.findChildren(QtWidgets.QLabel):
                    lbl.setText("<span style='color:white;font-size:18px;font-weight:700;'>"
                                f"{_tr('Diseñador de Duct Bank')}</span><br>"
                                "<span style='color:#d7e5ff;font-size:12px;'>"
                                f"{_tr('Cara Interior (Corte Longitudinal)')}</span>")
                    break
            except Exception: pass
            # Toolbar izquierda (herramientas)
            if hasattr(self, "tb_sel"):
                self.tb_sel.setText(_tr("Puntero"))
                self.tb_sel.setToolTip(_tr("Click para seleccionar un conducto.\n"
                                           "Arrastra un conducto para moverlo."))
            if hasattr(self, "tb_conduit"):
                self.tb_conduit.setText(_tr("Conducto\n(Círculo)"))
                self.tb_conduit.setToolTip(_tr("Click dentro de la envolvente para colocar un conducto del diámetro elegido."))
            if hasattr(self, "tb_dimensions"):
                self._refresh_dimensions_button()
            if hasattr(self, "tb_delete"):
                self.tb_delete.setText(_tr("Eliminar"))
                self.tb_delete.setToolTip(_tr("Click en un conducto para eliminarlo."))
            if hasattr(self, "btn_zin"):
                self.btn_zin.setText(_tr("Zoom +")); self.btn_zin.setToolTip(_tr("Acercar"))
            if hasattr(self, "btn_zout"):
                self.btn_zout.setText(_tr("Zoom −")); self.btn_zout.setToolTip(_tr("Alejar"))
            if hasattr(self, "btn_fit"):
                self.btn_fit.setText(_tr("Ajustar"))
                self.btn_fit.setToolTip(_tr("Centrar la vista sobre la envolvente"))
            # Footer + acciones primarias
            if hasattr(self, "lbl_status"):
                self.lbl_status.setText(_tr("Rejilla activada · 1 punto = 1 pulgada"))
            if hasattr(self, "chk_snap"):
                self.chk_snap.setText(_tr("Ajuste a rejilla (0.25\")"))
            if hasattr(self, "btn_cancel"): self.btn_cancel.setText(_tr("Cancelar"))
            if hasattr(self, "btn_close"): self.btn_close.setText("  " + _tr("Guardar y cerrar"))
            # Panel derecho — títulos de groupbox y labels de forms
            for w, key in [
                (getattr(self, "grp_conduit", None),
                    "Conducto seleccionado" if (self.scene.selected_idx is not None) else "Nuevo conducto"),
            ]:
                if w is not None: w.setTitle(_tr(key))
            # Los QGroupBox se re-buscan por su título original almacenado en propiedad
            # dinámica NO existe — simple: recorremos todos y traducimos los conocidos.
            # (los títulos de otros groupboxes fijos los re-hacemos por posición)
            for gb in self.findChildren(QtWidgets.QGroupBox):
                orig = gb.property("_orig_title")
                if orig:
                    gb.setTitle(_tr(orig))
            # Checkboxes
            if hasattr(self, "chk_rules"): self.chk_rules.setText(_tr("Aplicar reglas"))
            if hasattr(self, "chk_render_envelope"):
                self.chk_render_envelope.setText(_tr("Dibujar contenedor 3D"))
            # Placeholder del nombre
            if hasattr(self, "ed_name"):
                self.ed_name.setPlaceholderText(_tr("Ej. Duct Bank A – Telecom"))
            if hasattr(self, "sel_lbl"):
                self.sel_lbl.setPlaceholderText(_tr("Etiqueta (opcional)"))
            # Combo pipe: primer item "(Sin asignar)"
            if hasattr(self, "cmb_pipe") and self.cmb_pipe.count() > 0:
                self.cmb_pipe.setItemText(0, _tr("(Sin asignar)"))
            # Labels de filas del sub-form del conducto
            for lbl_attr, key in (
                ("_row_new_diam", "Diámetro:"),
                ("_row_sel_x", "X:"),
                ("_row_sel_y", "Y:"),
                ("_row_sel_d", "Diám. real:"),
                ("_row_sel_lbl", "Etiqueta:"),
            ):
                lbl = getattr(self, lbl_attr, None)
                if lbl is not None: lbl.setText(_tr(key))
            # Botón "Eliminar conducto"
            if hasattr(self, "btn_del_sel"):
                self.btn_del_sel.setText("  " + _tr("Eliminar conducto"))
            # Refresca panel entero: labels dinámicos (hint reglas, hint render,
            # celda de rejilla, contador, pipe status, banner de errores) se
            # recomponen con el idioma nuevo.
            self._refresh_panel()
            self._update_pipe_status()
        except Exception:
            pass

    def _wire(self):
        # Header — solo Deshacer/Rehacer/Ayuda (Nuevo/Abrir/Guardar del proyecto
        # ahora se manejan desde la pestaña "Bancoductos" de la ventana principal).
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_redo.clicked.connect(self._on_redo)
        QtGui.QShortcut(QtGui.QKeySequence.Undo, self, self._on_undo)
        QtGui.QShortcut(QtGui.QKeySequence.Redo, self, self._on_redo)
        self.btn_help.clicked.connect(self._on_help)
        # Acciones primarias (abajo del canvas)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_close.clicked.connect(self._on_close)

        # Escena
        self.scene.changed_model.connect(self._on_model_changed)
        self.scene.selection_changed.connect(self._refresh_panel)
        self.scene.tool_hint.connect(self.lbl_status.setText)
        # Banner rojo cuando una acción viola una regla obligatoria.
        self.scene.rule_violation.connect(self._on_rule_violation)

        # Panel
        self.ed_name.textChanged.connect(lambda s: self._set_name(s))
        self.sp_w.valueChanged.connect(lambda v: self._set_env(w=v))
        self.sp_h.valueChanged.connect(lambda v: self._set_env(h=v))
        # Reglas de diseño
        self.chk_rules.toggled.connect(lambda on: self._on_rules_changed(enabled=on))
        self.sp_rule_sep.valueChanged.connect(lambda v: self._on_rules_changed(sep=v))
        self.sp_rule_edge.valueChanged.connect(lambda v: self._on_rules_changed(edge=v))
        # Visualización
        self.chk_render_envelope.toggled.connect(
            lambda on: self._on_render_env_changed(on))
        # Margen (compass): a=top, b=right, c=bottom, d=left
        self.ed_margin.changed.connect(self._on_margin_changed)
        # Redondeo (corners): a=tl, b=tr, c=br, d=bl
        self.ed_corners.changed.connect(self._on_corners_changed)
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
            # Panel "Conducto" contextual (mejora #7): mismo groupbox, título y
            # campos cambian según haya selección.
            #   sin selección → título "Nuevo conducto", solo Diámetro visible.
            #   con selección → título "Conducto seleccionado", X/Y/Diám/Etiqueta.
            if hasattr(self, "grp_conduit"):
                self.grp_conduit.setTitle(_tr("Conducto seleccionado") if has_sel
                                            else _tr("Nuevo conducto"))
            # Fila "Diámetro" para colocación: visible SOLO sin selección
            # (con selección se usa "Diám. real" que edita el conducto actual).
            if hasattr(self, "sp_new_diam"):
                self.sp_new_diam.setVisible(not has_sel)
                if getattr(self, "_row_new_diam", None) is not None:
                    self._row_new_diam.setVisible(not has_sel)
            # Campos de edición (X/Y/Diám real/Etiqueta): visibles solo con selección
            for w, lbl_attr in (
                (self.sel_x, "_row_sel_x"),
                (self.sel_y, "_row_sel_y"),
                (self.sel_d, "_row_sel_d"),
                (self.sel_lbl, "_row_sel_lbl"),
            ):
                w.setVisible(has_sel); w.setEnabled(has_sel)
                lbl = getattr(self, lbl_attr, None)
                if lbl is not None: lbl.setVisible(has_sel)
            self.btn_del_sel.setVisible(has_sel); self.btn_del_sel.setEnabled(has_sel)
            if has_sel:
                c = m.conduits[self.scene.selected_idx]
                self.sel_x.setValue(c.cx); self.sel_y.setValue(c.cy)
                self.sel_d.setValue(c.diam); self.sel_lbl.setText(c.label)
                if hasattr(self, "lbl_conduit_hint"):
                    self.lbl_conduit_hint.setText("")
            else:
                self.sel_x.setValue(0); self.sel_y.setValue(0); self.sel_d.setValue(4); self.sel_lbl.setText("")
                if hasattr(self, "lbl_conduit_hint"):
                    self.lbl_conduit_hint.setText(
                        f'<span style="color:{_theme.tokens().text_muted};font-size:11px;">'
                        + _tr("Elige un diámetro y usa la herramienta <b>Conducto</b> "
                              "para colocarlo dentro de la envolvente.")
                        + "</span>")
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
        # Sincroniza controles de reglas de diseño (sin disparar handlers)
        if hasattr(self, "chk_rules"):
            for w in (self.chk_rules, self.sp_rule_sep, self.sp_rule_edge):
                w.blockSignals(True)
            try:
                self.chk_rules.setChecked(bool(m.rules_enabled))
                self.sp_rule_sep.setValue(float(m.rule_min_conduit_sep_in))
                self.sp_rule_edge.setValue(float(m.rule_min_edge_clearance_in))
            finally:
                for w in (self.chk_rules, self.sp_rule_sep, self.sp_rule_edge):
                    w.blockSignals(False)
            # Refresca el estado grisado + hint sin re-empujar historial
            self._on_rules_changed()  # sin argumentos: solo repinta estado
        # Sincroniza el checkbox de visualización
        if hasattr(self, "chk_render_envelope"):
            self.chk_render_envelope.blockSignals(True)
            try:
                self.chk_render_envelope.setChecked(bool(m.render_envelope))
            finally:
                self.chk_render_envelope.blockSignals(False)
            # Repinta hint
            t = _theme.tokens()
            self.lbl_render_hint.setText(
                f'<span style="color:{t.text_muted};font-size:11px;">' +
                (_tr("Se dibujará el sólido 3D del contenedor + los conductos internos.")
                 if m.render_envelope
                 else _tr("Solo se dibujarán los conductos internos. El sólido 3D del "
                          "contenedor NO se creará.")) +
                "</span>")
        self.lbl_count.setText(f"{_tr('Conductos')}: {len(m.conduits)}")
        errs = validate(m)
        self.lbl_valid.setText("\n".join("• " + e for e in errs))
        self._update_error_banner(errs)

    def _update_error_banner(self, errs):
        """Muestra u oculta el banner rojo overlay del canvas (mejora #3).
        El primer error va en negrita; el resto va en el tooltip para no
        saturar la pantalla."""
        if not hasattr(self, "lbl_error_banner"):
            return
        if not errs:
            self.lbl_error_banner.setVisible(False)
            return
        t = _theme.tokens()
        head = errs[0]
        more = "  " + _tr("(+{n} más)").format(n=len(errs) - 1) if len(errs) > 1 else ""
        # Fondo rojo tenue con borde rojo — legible en dark y light.
        bg = QtGui.QColor(t.danger); bg.setAlpha(70)
        bg_css = f"rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()/255:.2f})"
        self.lbl_error_banner.setStyleSheet(
            f"QLabel{{background:{bg_css}; color:{t.text}; "
            f"border:1px solid {t.danger}; border-radius:6px; "
            f"padding:6px 12px; font-size:12px;}}")
        self.lbl_error_banner.setText(f"⚠ {head}{more}")
        self.lbl_error_banner.setToolTip("\n".join("• " + e for e in errs))
        self.lbl_error_banner.adjustSize()
        self._position_error_banner()
        self.lbl_error_banner.setVisible(True)
        self.lbl_error_banner.raise_()

    def _on_rule_violation(self, msg: str):
        """Recibe la señal de la escena cuando el usuario intenta una acción
        que viola una regla obligatoria (colocar/mover un conducto en posición
        no permitida). Muestra el banner rojo con el mensaje y programa que se
        oculte solo tras unos segundos — así el usuario ve la advertencia
        aunque no esté mirando la barra de estado inferior.

        Si el modelo ya tenía errores de validación acumulados, el banner con
        esos errores vuelve al ocultarse este mensaje temporal."""
        if not hasattr(self, "lbl_error_banner"):
            return
        self._update_error_banner([msg])
        # Programar borrado tras 3.5s: si el usuario no ha corregido, el
        # banner vuelve a mostrar los errores acumulados del modelo (validate).
        if not hasattr(self, "_rule_violation_timer"):
            self._rule_violation_timer = QtCore.QTimer(self)
            self._rule_violation_timer.setSingleShot(True)
            self._rule_violation_timer.timeout.connect(self._restore_error_banner)
        self._rule_violation_timer.start(3500)

    def _restore_error_banner(self):
        """Repone el banner con los errores actuales del modelo (o lo oculta
        si el modelo está limpio) al vencer el timer del aviso de regla."""
        try:
            errs = validate(self.scene.model)
            self._update_error_banner(errs)
        except Exception:
            pass

    def _position_error_banner(self):
        """Centra el banner en el tope del canvas, con margen 10px."""
        if not hasattr(self, "_canvas_wrap") or not hasattr(self, "lbl_error_banner"):
            return
        wrap = self._canvas_wrap
        banner = self.lbl_error_banner
        # Ancho máximo del banner: 90% del wrap
        max_w = int(wrap.width() * 0.9)
        banner.setMaximumWidth(max_w)
        banner.adjustSize()
        x = (wrap.width() - banner.width()) // 2
        banner.move(max(0, x), 10)

    def eventFilter(self, obj, ev):
        """Reposiciona el banner de errores cuando el canvas cambia de tamaño."""
        if hasattr(self, "_canvas_wrap") and obj is self._canvas_wrap \
                and ev.type() == QtCore.QEvent.Resize:
            self._position_error_banner()
        return super().eventFilter(obj, ev)

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
        # Al cambiar dimensiones de la envolvente, expandimos el sceneRect
        # para que se pueda pan/zoom a todos los bordes.
        self.scene._update_scene_rect()
        self.scene.update()
        self._push_history()
        self.lbl_count.setText(f"{_tr('Conductos')}: {len(m.conduits)}")
        errs = validate(m)
        self.lbl_valid.setText("\n".join("• " + e for e in errs))
        self._update_error_banner(errs)

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

    def _on_rules_changed(self, enabled=None, sep=None, edge=None):
        """Actualiza las reglas de diseño en el modelo. Solo `enabled` va al
        historial (los valores de sep/edge cambian con cada tecla — como Nombre)."""
        m = self.scene.model
        if enabled is not None:
            m.rules_enabled = bool(enabled)
            self._push_history()
        if sep is not None:
            m.rule_min_conduit_sep_in = float(sep)
        if edge is not None:
            m.rule_min_edge_clearance_in = float(edge)
        # Grisa/activa los sub-controles según el toggle maestro.
        active = m.rules_enabled
        for w in (self.sp_rule_sep, self.sp_rule_edge):
            w.setEnabled(active)
        # Hint del pie del grupo
        t = _theme.tokens()
        if active:
            active_rules = []
            if m.rule_min_conduit_sep_in > 0:
                active_rules.append(f'{_tr("sep.")} {m.rule_min_conduit_sep_in:g}"')
            if m.rule_min_edge_clearance_in > 0:
                active_rules.append(f'{_tr("borde")} {m.rule_min_edge_clearance_in:g}"')
            if active_rules:
                body = (_tr("Reglas activas: {rules}") if len(active_rules) > 1
                        else _tr("Regla activa: {rules}")).format(rules=", ".join(active_rules))
            else:
                body = _tr("Sin valores puestos — configura arriba para que apliquen.")
            self.lbl_rules_hint.setText(
                f'<span style="color:{t.text_muted};font-size:11px;">{body}</span>')
        else:
            self.lbl_rules_hint.setText(
                f'<span style="color:{t.text_muted};font-size:11px;">'
                + _tr("Reglas custom desactivadas. Los chequeos geométricos básicos "
                      "(dentro de envolvente, sin colisión) siguen activos.")
                + "</span>")
        # Re-valida y refresca banner.
        self.scene.update()
        errs = validate(m)
        self.lbl_valid.setText("\n".join("• " + e for e in errs))
        self._update_error_banner(errs)

    def _on_render_env_changed(self, on: bool):
        m = self.scene.model
        m.render_envelope = bool(on)
        self._push_history()
        t = _theme.tokens()
        if on:
            self.lbl_render_hint.setText(
                f'<span style="color:{t.text_muted};font-size:11px;">'
                + _tr("Se dibujará el sólido 3D del contenedor + los conductos internos.")
                + "</span>")
        else:
            self.lbl_render_hint.setText(
                f'<span style="color:{t.text_muted};font-size:11px;">'
                + _tr("Solo se dibujarán los conductos internos. El sólido 3D del "
                      "contenedor NO se creará.")
                + "</span>")
        self.scene.update()

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
        errs = validate(m)
        self.lbl_valid.setText("\n".join("• " + e for e in errs))
        self._update_error_banner(errs)

    def keyPressEvent(self, ev):
        # Escape (no cierra el diálogo — el default de QDialog es reject()):
        #   1. Si el toggle "Mostrar medidas" está activo → apagarlo.
        #   2. Si la herramienta activa NO es Puntero → volver a Puntero.
        #   3. Si hay un conducto seleccionado → deseleccionarlo.
        #   4. Nada: ignorar (evita cierre accidental).
        if ev.key() == QtCore.Qt.Key_Escape:
            if getattr(self, "tb_dimensions", None) is not None \
                    and self.tb_dimensions.isChecked():
                self.tb_dimensions.setChecked(False)
                self._toggle_dimensions()
                ev.accept()
                return
            if self.scene.tool != "select":
                self._set_tool("select")
                self.scene._ghost_pos = None
                self.scene.update()
                ev.accept()
                return
            if self.scene.selected_idx is not None:
                self.scene.selected_idx = None
                self._on_model_changed()
                ev.accept()
                return
            ev.accept()
            return
        super().keyPressEvent(ev)

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
        # Marca el botón correspondiente (mostrar medidas NO va aquí: es toggle
        # independiente, no una herramienta del canvas).
        mapping = {"select": self.tb_sel, "conduit": self.tb_conduit,
                   "delete": self.tb_delete}
        for k, b in mapping.items():
            b.setChecked(k == key)
        hints = {"select": _tr("Click en un conducto para seleccionarlo. Arrástralo para moverlo."),
                 "conduit": _tr('Click dentro de la envolvente para colocar un conducto de {d}\".').format(d=f"{self.scene.new_conduit_diam:g}"),
                 "delete": _tr("Click en un conducto para eliminarlo.")}
        self.lbl_status.setText(hints.get(key, ""))
        # Cursor
        cursors = {"select": QtCore.Qt.ArrowCursor, "delete": QtCore.Qt.PointingHandCursor,
                   "conduit": QtCore.Qt.CrossCursor}
        self.view.setCursor(cursors.get(key, QtCore.Qt.ArrowCursor))

    def _toggle_dimensions(self, *_):
        """Alterna el overlay de cotas. Sincroniza el estado del toggle en
        ambas direcciones (por si se llama desde código) y repinta."""
        on = self.tb_dimensions.isChecked()
        self.scene.show_dimensions = bool(on)
        self._refresh_dimensions_button()
        self.scene.update()

    def _refresh_dimensions_button(self):
        """Texto e icono del toggle según su estado. Activo → texto en rojo
        (mismo color con el que se dibujan las cotas) para hacer obvio que
        está encendido; inactivo → estilo normal.

        El icono lo pinta _restyle. Aquí solo cambiamos texto/tooltip/
        propiedad 'danger' (el QSS del ToolButton usa esa propiedad para
        colorear texto en rojo)."""
        if not hasattr(self, "tb_dimensions"):
            return
        b = self.tb_dimensions
        if b.isChecked():
            b.setText(_tr("Ocultar\nmedidas"))
            b.setToolTip(_tr("Oculta las cotas del diseño."))
            b.setProperty("danger", "true")
        else:
            b.setText(_tr("Mostrar\nmedidas"))
            b.setToolTip(_tr("Muestra las cotas de separación entre conductos y "
                             "resguardo al borde/margen (en rojo)."))
            b.setProperty("danger", "false")
        # Forzar re-estilo del QSS (para que el color/estilo se aplique)
        b.style().unpolish(b); b.style().polish(b)

    def _zoom(self, f: float):
        cur = self.view.transform().m11()
        new = cur * f
        if _INITIAL_PX_PER_IN * _MIN_ZOOM <= new <= _INITIAL_PX_PER_IN * _MAX_ZOOM:
            self.view.scale(f, f)
            self.lbl_zoom.setText(f"{int((new / _INITIAL_PX_PER_IN) * 100)}%")

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
        self.scene._update_scene_rect()
        self.scene.update(); self._refresh_panel()

    def _on_redo(self):
        if not self._future: return
        m = self._future.pop()
        self._history.append(m.copy())
        self.scene.model = m.copy()
        self.scene.selected_idx = None
        self.scene._update_scene_rect()
        self.scene.update(); self._refresh_panel()

    def _on_new(self):
        if QtWidgets.QMessageBox.question(self, _tr("Nuevo"), _tr("¿Descartar el diseño actual y empezar uno nuevo?")) \
                != QtWidgets.QMessageBox.Yes:
            return
        self.scene.model = DuctBank()
        self.scene.selected_idx = None
        self.scene._update_scene_rect()
        self._history.clear(); self._future.clear()
        self._push_history(); self._refresh_panel(); self.scene.update()

    def _on_open(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Abrir Duct Bank"),
                                                      "", _tr("Duct Bank (*.dbjson);;JSON (*.json)"))
        if not fn: return
        try:
            with open(fn, "r", encoding="utf-8") as f:
                self.scene.model = DuctBank.from_dict(json.load(f))
            self.scene.selected_idx = None
            self.scene._update_scene_rect()
            self._history.clear(); self._future.clear()
            self._push_history(); self._refresh_panel(); self.scene.update()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, _tr("Error al abrir"), str(e))

    def _on_save(self):
        default = (self.scene.model.name or "duct_bank").replace("/", "_") + ".dbjson"
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self, _tr("Guardar Duct Bank"),
                                                      default, _tr("Duct Bank (*.dbjson)"))
        if not fn: return
        try:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self.scene.model.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, _tr("Error al guardar"), str(e))

    def _on_help(self):
        QtWidgets.QMessageBox.information(self, _tr("Ayuda — Duct Bank"),
            _tr("1) En el panel derecho, ponle <b>Nombre</b> y <b>Asigna la utilidad</b> "
                "que este bancoducto reemplazará al importar en Civil 3D.<br>"
                "2) Ajusta el <b>Ancho</b> y <b>Alto</b> de la envolvente (pulgadas).<br>"
                "3) Elige un diámetro y usa la herramienta <b>Conducto</b>: cada clic "
                "dentro de la envolvente coloca un conducto.<br>"
                "4) Con el <b>Puntero</b>: click selecciona un conducto y arrástralo "
                "para moverlo. Los datos del seleccionado (X/Y/diámetro/etiqueta) "
                "aparecen en el panel derecho.<br>"
                "5) <b>Eliminar</b> quita el conducto que hagas clic.<br>"
                "6) La rueda del ratón acerca/aleja; el botón central mueve la vista.<br>"
                "7) Si hay un problema con el diseño (conducto fuera, solape…) aparece "
                "un banner rojo en el tope del canvas con el mensaje.<br>"
                "8) Presiona <b>Guardar y cerrar</b> — el diseño se guarda en el proyecto."))

    def _update_pipe_status(self):
        # Usa tokens del tema activo para legibilidad en dark y light.
        t = _theme.tokens()
        idx = self.cmb_pipe.currentData()
        if idx is not None and idx >= 0:
            self.lbl_pipe_status.setText(
                f"<span style='color:{t.success};font-weight:600;font-size:11px;'>"
                f"✓ {_tr('Al exportar, esta utilidad será un duct bank (no una tubería normal).')}"
                "</span>")
        else:
            self.lbl_pipe_status.setText(
                f"<span style='color:{t.text_muted};font-size:11px;'>"
                f"⚠ {_tr('Sin asignar — el duct bank no se exportará.')}</span>")

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
