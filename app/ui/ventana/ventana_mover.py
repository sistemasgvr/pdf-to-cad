"""Panel «Mover con precisión» y arrastre de vértices/estructuras.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class MoverPrecisoMixin:
    # ─────────────────── Mover con precisión (panel izquierdo) ─────────────
    def _build_move_precise_panel(self, lay):
        """Panel para desplazar la selección actual una distancia EXACTA en
        pies. Se compone de:
          · Etiqueta con lo seleccionado (color + descripción). Fondo gris si
            no hay nada seleccionado.
          · Radio: toda la utilidad / solo un vértice (con QSpinBox del índice).
          · Botones flecha ↑↓←→ + "paso" en ft para nudge rápidos.
          · Campos ΔX / ΔY con botón "Aplicar" para vector arbitrario.
        Todo entra en el mismo contenedor `lay` (QVBoxLayout de la sección)."""
        # Encabezado: qué está seleccionado.
        self.mv_lbl_sel = _bind(QtWidgets.QLabel(), "setText", "(nada seleccionado)")
        self.mv_lbl_sel.setWordWrap(True)
        self.mv_lbl_sel.setStyleSheet(
            "padding:6px 8px; border-radius:4px; background:#333; color:#ccc;")
        lay.addWidget(self.mv_lbl_sel)

        # Alcance del movimiento (radios apilados vertical → no fuerzan ancho).
        self.mv_grp_scope = QtWidgets.QWidget()
        sc_l = QtWidgets.QVBoxLayout(self.mv_grp_scope); sc_l.setContentsMargins(0, 0, 0, 0)
        sc_l.setSpacing(2)
        self.mv_rb_all = _bind(QtWidgets.QRadioButton(), "setText", "Toda la utilidad")
        self.mv_rb_vert = _bind(QtWidgets.QRadioButton(), "setText", "Un vértice")
        self.mv_rb_all.setChecked(True)
        sc_grp = QtWidgets.QButtonGroup(self.mv_grp_scope)
        sc_grp.addButton(self.mv_rb_all); sc_grp.addButton(self.mv_rb_vert)
        # Fila del índice de vértice: label + spin al lado.
        vert_row = QtWidgets.QHBoxLayout(); vert_row.setContentsMargins(20, 0, 0, 0)
        vert_row.addWidget(_bind(QtWidgets.QLabel(), "setText", "Vértice #:"))
        self.mv_vert_idx = QtWidgets.QSpinBox()
        self.mv_vert_idx.setRange(0, 999); self.mv_vert_idx.setPrefix("V")
        self.mv_vert_idx.setMinimumWidth(60)
        self.mv_vert_idx.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        _bind(self.mv_vert_idx, "setToolTip", "Índice del vértice a mover (0 = primero).")
        self.mv_vert_idx.setEnabled(False)
        self.mv_rb_vert.toggled.connect(self.mv_vert_idx.setEnabled)
        vert_row.addWidget(self.mv_vert_idx, 1)
        sc_l.addWidget(self.mv_rb_all); sc_l.addWidget(self.mv_rb_vert); sc_l.addLayout(vert_row)
        lay.addWidget(self.mv_grp_scope)

        # Paso rápido con flechas
        step_row = QtWidgets.QHBoxLayout(); step_row.setContentsMargins(0, 0, 0, 0)
        step_row.addWidget(_bind(QtWidgets.QLabel(), "setText", "Paso (ft):"))
        self.mv_step_ft = QtWidgets.QDoubleSpinBox()
        self.mv_step_ft.setDecimals(2); self.mv_step_ft.setRange(0.01, 10000.0)
        self.mv_step_ft.setSingleStep(0.5); self.mv_step_ft.setValue(1.0)
        self.mv_step_ft.setMinimumWidth(70)
        self.mv_step_ft.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        step_row.addWidget(self.mv_step_ft, 1)
        lay.addLayout(step_row)

        # Flechas en cruz (grid). Los botones NO tienen ancho fijo — con
        # setSizePolicy Preferred el layout los encoge cuando el dock se
        # angosta, así el panel deja de forzar scroll horizontal. Se usan
        # setMinimumSize para no perderlos completamente en anchos mínimos.
        arrows = QtWidgets.QGridLayout(); arrows.setSpacing(4)
        arrows.setContentsMargins(0, 0, 0, 0)
        self.mv_btn_up = QtWidgets.QPushButton(); self.mv_btn_up.setIcon(_icon("mdi:arrow-up-bold"))
        self.mv_btn_dn = QtWidgets.QPushButton(); self.mv_btn_dn.setIcon(_icon("mdi:arrow-down-bold"))
        self.mv_btn_lf = QtWidgets.QPushButton(); self.mv_btn_lf.setIcon(_icon("mdi:arrow-left-bold"))
        self.mv_btn_rt = QtWidgets.QPushButton(); self.mv_btn_rt.setIcon(_icon("mdi:arrow-right-bold"))
        for b in (self.mv_btn_up, self.mv_btn_dn, self.mv_btn_lf, self.mv_btn_rt):
            b.setIconSize(QtCore.QSize(20, 20))
            b.setMinimumSize(32, 34)
            b.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        _bind(self.mv_btn_up, "setToolTip", "Arriba (Y+) por Paso")
        _bind(self.mv_btn_dn, "setToolTip", "Abajo (Y−) por Paso")
        _bind(self.mv_btn_lf, "setToolTip", "Izquierda (X−) por Paso")
        _bind(self.mv_btn_rt, "setToolTip", "Derecha (X+) por Paso")
        arrows.addWidget(self.mv_btn_up, 0, 1)
        arrows.addWidget(self.mv_btn_lf, 1, 0)
        arrows.addWidget(self.mv_btn_rt, 1, 2)
        arrows.addWidget(self.mv_btn_dn, 2, 1)
        arrows.setColumnStretch(0, 1); arrows.setColumnStretch(1, 1); arrows.setColumnStretch(2, 1)
        self.mv_btn_up.clicked.connect(lambda: self._apply_move_by_ft(0.0, +self.mv_step_ft.value()))
        self.mv_btn_dn.clicked.connect(lambda: self._apply_move_by_ft(0.0, -self.mv_step_ft.value()))
        self.mv_btn_lf.clicked.connect(lambda: self._apply_move_by_ft(-self.mv_step_ft.value(), 0.0))
        self.mv_btn_rt.clicked.connect(lambda: self._apply_move_by_ft(+self.mv_step_ft.value(), 0.0))
        lay.addLayout(arrows)

        # Vector arbitrario ΔX, ΔY.
        # Los spinboxes se construyen con un helper local que, si el usuario
        # borra el texto y deja el campo vacío, lo colapsa a 0.00 en vez de
        # dejar el valor anterior "pegado" (comportamiento raro de QDoubleSpinBox
        # por defecto — la primera versión de este panel lo tenía).
        vec_lbl = _bind(QtWidgets.QLabel(), "setText", "O escribe un desplazamiento exacto:")
        vec_lbl.setStyleSheet("margin-top:6px; color:#aaa;")
        vec_lbl.setWordWrap(True)
        lay.addWidget(vec_lbl)
        vec = QtWidgets.QGridLayout(); vec.setSpacing(4); vec.setContentsMargins(0, 0, 0, 0)
        def _dsb_delta():
            b = QtWidgets.QDoubleSpinBox()
            b.setDecimals(2); b.setRange(-1e6, 1e6); b.setSingleStep(0.5)
            b.setMinimumWidth(70)
            b.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            le = b.lineEdit()
            # Al perder el foco: si el texto quedó vacío o sin dígitos, set 0.
            def _coerce_empty():
                txt = (le.text() or "").strip()
                # Quitar cualquier prefijo/sufijo para chequear si hay número.
                # Los DoubleSpinBox nuestros no usan prefix/suffix, así que txt
                # es directamente el número (o vacío/signo suelto).
                if not txt or txt in ("-", "+", ",", "."):
                    b.setValue(0.0)
            le.editingFinished.connect(_coerce_empty)
            return b
        vec.addWidget(_bind(QtWidgets.QLabel(), "setText", "ΔX (ft):"), 0, 0)
        self.mv_dx = _dsb_delta()
        vec.addWidget(self.mv_dx, 0, 1)
        vec.addWidget(_bind(QtWidgets.QLabel(), "setText", "ΔY (ft):"), 1, 0)
        self.mv_dy = _dsb_delta()
        vec.addWidget(self.mv_dy, 1, 1)
        vec.setColumnStretch(1, 1)
        self.mv_btn_apply = _bind(WrapButton(), "setText", "Aplicar", pre='  ')
        self.mv_btn_apply.setIcon(_icon("mdi:check"))
        self.mv_btn_apply.setIconSize(QtCore.QSize(18, 18))
        self.mv_btn_apply.clicked.connect(
            lambda: self._apply_move_by_ft(self.mv_dx.value(), self.mv_dy.value()))
        vec.addWidget(self.mv_btn_apply, 2, 0, 1, 2)
        lay.addLayout(vec)

        # Nota UX
        note = _bind(QtWidgets.QLabel(), "setText", "<i>ΔY+ = norte del plano. Cada movimiento respeta Deshacer (Ctrl+Z).</i>")
        note.setWordWrap(True); note.setStyleSheet("color:#888; margin-top:4px;")
        lay.addWidget(note)

        # Estado inicial: deshabilitado hasta que haya selección.
        self._update_move_panel()

    def _update_move_panel(self):
        """Habilita/deshabilita el panel según lo que esté seleccionado y
        actualiza el label con qué se va a mover. Se llama desde _update_ui()."""
        if not hasattr(self, "mv_lbl_sel"): return
        info = self._selected_move_target()
        widgets = (self.mv_grp_scope, self.mv_step_ft, self.mv_btn_up, self.mv_btn_dn,
                   self.mv_btn_lf, self.mv_btn_rt, self.mv_dx, self.mv_dy, self.mv_btn_apply)
        if info is None:
            for w in widgets: w.setEnabled(False)
            _bind(self.mv_lbl_sel, "setText", "(nada seleccionado)")
            self.mv_lbl_sel.setStyleSheet(
                "padding:6px 8px; border-radius:4px; background:#333; color:#ccc;")
            return
        for w in widgets: w.setEnabled(True)
        kind, obj = info
        if kind == "pipe":
            layer = obj.get("layer", ""); diam = self._diam_txt(obj)
            n = len(obj.get("pts") or [])
            col = layer_qcolor(layer).name()
            _bind(self.mv_lbl_sel, "setText", "Utilidad {layer} · Ø{diam} · {n} vértices",
                  fmt={"layer": self._etq(obj), "diam": diam, "n": n})
            self.mv_lbl_sel.setStyleSheet(
                f"padding:6px 8px; border-radius:4px; background:{col}; color:white; font-weight:bold;")
            # Ajustar rango del spinbox de vértice
            self.mv_vert_idx.setRange(0, max(0, n - 1))
        elif kind == "struct":
            cod = obj.get("cod") or _tr("(sin código)")
            es_curva = bool(obj.get("curve"))
            _bind(self.mv_lbl_sel, "setText", "Curva · {cod}" if es_curva else "Buzón · {cod}",
                  fmt={"cod": cod})
            self.mv_lbl_sel.setStyleSheet(
                "padding:6px 8px; border-radius:4px; background:#8a3ab9; color:white; font-weight:bold;")
            # Un buzón/curva es un punto — solo aplica "un vértice" implícito.
            self.mv_rb_all.setChecked(True)
            self.mv_rb_vert.setEnabled(False)
            return
        # Radio botones habilitados solo para pipe con >1 vértice.
        self.mv_rb_vert.setEnabled(kind == "pipe" and len(obj.get("pts") or []) > 0)

    def _selected_move_target(self):
        """Determina qué está seleccionado y va a mover el panel. Devuelve
        (kind, obj) o None. Prioridad: pipe → structure (buzón/curva). Otros
        tipos de selección (leader/text/región/centerline) no aplican."""
        if 0 <= getattr(self, "sel_pipe", -1) < len(self.pipes):
            return ("pipe", self.pipes[self.sel_pipe])
        idx = -1
        if 0 <= getattr(self, "sel_bz", -1) < len(self.structures):
            idx = self.sel_bz
        elif 0 <= getattr(self, "sel_curve", -1) < len(self.structures):
            idx = self.sel_curve
        if idx >= 0:
            return ("struct", self.structures[idx])
        return None

    def _apply_move_by_ft(self, dx_ft, dy_ft):
        """Motor de mover: convierte pies a scene pixels usando la escala y
        el zoom actuales, y desplaza el objeto seleccionado en consecuencia.
        Empuja al undo stack antes de mutar. Redibuja al final."""
        if abs(dx_ft) < 1e-9 and abs(dy_ft) < 1e-9: return
        info = self._selected_move_target()
        if info is None:
            self._info(_tr("No hay nada seleccionado para mover.")); return
        if not self.scale or self.scale <= 1e-6:
            QtWidgets.QMessageBox.warning(self, _tr("Sin escala"),
                _tr("La escala del plano no está definida — establece '1\" = X ft' antes de mover.")); return
        # ft → scene px. La conversión inversa a _px_for_ft (que además tiene un
        # cap para textos que aquí NO queremos aplicar).
        px_per_ft = float(self.zoom) / self.scale
        dx_px = dx_ft * px_per_ft
        # Y del plano crece hacia arriba en la vida real, pero en Qt/canvas Y
        # crece hacia ABAJO. Se invierte para que "ΔY+ = norte del plano".
        dy_px = -dy_ft * px_per_ft
        self._push()
        kind, obj = info
        if kind == "pipe":
            pts = obj.get("pts") or []
            if self.mv_rb_vert.isChecked():
                vi = self.mv_vert_idx.value()
                if not (0 <= vi < len(pts)):
                    self._info(_tr("Índice de vértice fuera de rango.")); return
                pts[vi] = (pts[vi][0] + dx_px, pts[vi][1] + dy_px)
                # Si algún buzón/curva coincidía con ese vértice, moverlo
                # también para mantener la coherencia (mismo criterio que
                # _no_manhole_vertex_indices: tol 14 px).
                self._drag_structures_at((pts[vi][0] - dx_px, pts[vi][1] - dy_px), dx_px, dy_px)
                self._info(_tr("Vértice V{vi} movido ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.").format(
                    vi=vi, dx=dx_ft, dy=dy_ft))
            else:
                # Utilidad completa: desplazar TODOS los vértices y arrastrar
                # los buzones/curvas asociados a esos vértices también.
                new_pts = []
                for (px, py) in pts:
                    new_pts.append((px + dx_px, py + dy_px))
                    self._drag_structures_at((px, py), dx_px, dy_px)
                obj["pts"] = new_pts
                self._info(_tr("Utilidad movida ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft ({n} vértices).").format(
                    dx=dx_ft, dy=dy_ft, n=len(new_pts)))
        elif kind == "struct":
            sx, sy = obj.get("x"), obj.get("y")
            if sx is None or sy is None:
                self._info(_tr("El elemento seleccionado no tiene posición en el lienzo.")); return
            obj["x"] = sx + dx_px; obj["y"] = sy + dy_px
            # Además: si algún vértice de pipe coincidía con la vieja posición,
            # arrástralo también para no "despegar" un buzón de su tubería.
            self._drag_pipe_vertices_at((sx, sy), dx_px, dy_px)
            self._info(_tr("Elemento movido ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.").format(
                dx=dx_ft, dy=dy_ft))
        self._dirty = True; self._redraw()

    def _drag_structures_at(self, pos, dx_px, dy_px, tol_px=14.0):
        """Mueve todas las structures cuyo (x,y) coincide con `pos` dentro de
        `tol_px`. Se usa cuando un vértice de pipe se desplaza, para mantener
        pegado el buzón/curva que estaba en ese vértice."""
        tol2 = tol_px * tol_px
        px, py = pos
        for s in self.structures:
            if s.get("world"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if (sx - px) ** 2 + (sy - py) ** 2 <= tol2:
                s["x"] = sx + dx_px; s["y"] = sy + dy_px

    def _drag_pipe_vertices_at(self, pos, dx_px, dy_px, tol_px=14.0):
        """Mueve todos los vértices de todas las pipes cuya posición coincide
        con `pos` dentro de `tol_px`. Complemento simétrico de _drag_structures_at."""
        tol2 = tol_px * tol_px
        px, py = pos
        for p in self.pipes:
            if p.get("world") or not p.get("pts"): continue
            new_pts = list(p["pts"])
            changed = False
            for i, (vx, vy) in enumerate(new_pts):
                if (vx - px) ** 2 + (vy - py) ** 2 <= tol2:
                    new_pts[i] = (vx + dx_px, vy + dy_px); changed = True
            if changed: p["pts"] = new_pts

    def _curve_max_radius_ft(self, curve_idx):
        """Radio máximo (en pies) que ImportarRed.cs aceptará para esta curva sin
        recortar. Replica la fórmula del plugin:
          t_max = min(distPrev·capPrev, distNext·capNext)
          r_max = t_max · tan(Δ/2)
        donde Δ es el ángulo interno entre los dos tramos rectos (dot product de
        las direcciones que salen del vértice curvo), y cap es 0.48 si el vértice
        vecino también es curva o 1.0 si es recto (model_ops.FILLET_CAP_*: la
        tangencia puede llegar hasta el vértice vecino). Devuelve None si no aplica
        (curva sin tubería asociada, tramo casi recto, etc.)."""
        import math
        if not (0 <= curve_idx < len(self.structures)): return None
        s = self.structures[curve_idx]
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None: return None
        p = self._pipe_at_vertex(sx, sy)
        if p is None or not p.get("pts") or len(p["pts"]) < 3: return None
        # Índice del vértice de la tubería que corresponde a esta curva (el más cercano)
        vi = model_ops.nearest_vertex(p["pts"], sx, sy, 14.0)
        if vi is None or vi <= 0 or vi >= len(p["pts"]) - 1:
            return None
        # Detectar si los vecinos vi-1 y vi+1 también son vértices curvos
        # (misma tubería). Mismo criterio que _no_manhole_vertex_indices: cada
        # estructura curva es de UN vértice (el más cercano).
        cv = model_ops.curve_vertex_indices(p, self.structures, self.pipes)

        def es_curva_en(idx_v):
            return idx_v in cv
        cap_prev = model_ops.FILLET_CAP_CURVA if es_curva_en(vi - 1) else model_ops.FILLET_CAP_RECTA
        cap_next = model_ops.FILLET_CAP_CURVA if es_curva_en(vi + 1) else model_ops.FILLET_CAP_RECTA
        # Distancias en pies (usar _to_cad para convertir de píxeles a CAD ft).
        try:
            cx_ft, cy_ft = self._to_cad(*p["pts"][vi])
            px_ft, py_ft = self._to_cad(*p["pts"][vi - 1])
            nx_ft, ny_ft = self._to_cad(*p["pts"][vi + 1])
        except Exception:
            return None
        vpx, vpy = px_ft - cx_ft, py_ft - cy_ft
        vnx, vny = nx_ft - cx_ft, ny_ft - cy_ft
        dist_prev = math.hypot(vpx, vpy)
        dist_next = math.hypot(vnx, vny)
        if dist_prev < 1e-6 or dist_next < 1e-6: return None
        # Ángulo interno (mismo criterio que el plugin: Acos del dot product
        # de los vectores UNITARIOS que salen del vértice curvo).
        cos_d = (vpx * vnx + vpy * vny) / (dist_prev * dist_next)
        cos_d = max(-1.0, min(1.0, cos_d))
        delta_rad = math.acos(cos_d)
        # Casi recta: no aplica límite (el plugin salta la curva)
        if math.degrees(delta_rad) > 178.0: return None
        t_max = min(dist_prev * cap_prev, dist_next * cap_next)
        r_max = t_max * math.tan(delta_rad / 2.0)
        return r_max if r_max > 0 else None
