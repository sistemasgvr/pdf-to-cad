"""Utilidades: selección, cotas por tramo y versión/idioma de Civil 3D.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class UtilidadesMixin:
    # ─────────────────────────── utilidades ───────────────────────────
    def finish_pipe(self):
        if self._extending and self._ext_pipe is not None and 0 <= self._ext_pipe < len(self.pipes):
            extra = self.cur_pts[1:]                       # el 1er punto es el vértice existente
            if extra:
                self._push(); pep = self.pipes[self._ext_pipe]; pts = pep["pts"]
                if self._ext_at == "end": pts.extend(extra)
                else:
                    pep["pts"] = list(reversed(extra)) + pts
                    ov = pep.get("vertex_inv")             # todo lo existente se corre len(extra) a la derecha
                    if ov: pep["vertex_inv"] = {k + len(extra): v for k, v in ov.items()}
        elif len(self.cur_pts) >= 2:
            layer = self._ext_layer if self._extending else self.active_layer()
            ab = False if self._extending else self.chk_ab.isChecked()
            self._push(); self.pipes.append({"layer": layer, "pts": self.cur_pts[:], "ab": ab,
                                             "diam": float(PIPE_DIAMETERS_IN[0]), "diam_unit": "in",
                                             "material": DEFAULT_PIPE_MATERIAL})
        self.cur_pts = []; self._extending = False; self._ext_layer = None; self._ext_pipe = None; self._ext_at = None
        self._refresh_lists(); self._update_ui(); self._redraw()

    def _sel_pipe(self, r):
        """Se llama cuando el usuario selecciona una utilidad en el inventario
        (lista derecha). Actualiza el panel de Propiedades con SUS datos.

        `self._prop_guard` es un pequeño truco: bloquea temporalmente los
        callbacks de los campos mientras los rellenamos con valores. Sin él,
        `setValue`/`setText` dispararía `_prop_changed()` y guardaría los
        datos ANTES de terminar de cargarlos (círculo vicioso)."""
        self.sel_pipe = r
        if 0 <= r < len(self.pipes):
            p = self.pipes[r]; pts = p.get("pts")
            if not self._no_center and pts:                # los tramos importados (world) no tienen pts
                # Solo re-centrar si el pipe NO está ya visible en la vista
                # actual — evita saltos innecesarios que desorientan al usuario
                # cuando la utilidad ya se ve en pantalla.
                view_rect = self.canvas.mapToScene(self.canvas.viewport().rect()).boundingRect()
                xs = [x for (x, _) in pts]; ys = [y for (_, y) in pts]
                pipe_rect = QtCore.QRectF(QtCore.QPointF(min(xs), min(ys)),
                                          QtCore.QPointF(max(xs), max(ys)))
                if not view_rect.intersects(pipe_rect):
                    mid = pts[len(pts) // 2]; self.canvas.centerOn(mid[0], mid[1])
            self._prop_guard = True
            self.prop_name.setText(p.get("name", ""))
            # Vacío = nombre por defecto «TIPO-NÚMERO» (se renumera solo al borrar).
            self.prop_name.setPlaceholderText(model_ops.nombre_por_defecto(p, self.sel_pipe))
            # El diámetro se deriva del "Tamaño" del catálogo (elegido más abajo).
            self.prop_part.setText(p.get("part", ""))
            self.prop_inv0.setValue(p.get("inv_start") or 0.0); self.prop_inv1.setValue(p.get("inv_end") or 0.0)
            # findData por VALOR real (no por texto traducido) — así el mapeo
            # material↔selección es estable aunque el usuario cambie idioma.
            mi = self.prop_material.findData(p.get("material") or DEFAULT_PIPE_MATERIAL)
            if mi < 0:
                mi = self.prop_material.findText(p.get("material") or DEFAULT_PIPE_MATERIAL)
            self.prop_material.setCurrentIndex(mi if mi >= 0 else 0)
            # findData busca el índice del combo cuya "data" (dato oculto) coincide
            # con "" | "pipe" | "pressure"; si no encuentra devuelve -1 → índice 0.
            idx = self.prop_nettype.findData(p.get("net_type", "") or "")
            self.prop_nettype.setCurrentIndex(idx if idx >= 0 else 0)
            self._reload_pipe_families(p)
            self._prop_guard = False
            self._rebuild_seg_inv_table(p)
        else:
            self.gprop_segs.setVisible(False)
        # Repinta la lista de bancoductos para actualizar qué fila queda en
        # negrita/acento (la asignada a esta tubería).
        if hasattr(self, "_refresh_db_list"):
            self._refresh_db_list()
        self._update_ui(); self._redraw()

    def _interp_vertex_z(self, pts, z_start, z_end, overrides):
        # Interpolación de cota por vértice (pura) en model_ops.
        return model_ops.interp_vertex_z(pts, z_start, z_end, overrides)

    def _rebuild_seg_inv_table(self, p):
        """Reconstruye la tabla de tramos. Cada celda es independiente:
        'Inicio' de tramo N NO sincroniza con 'Fin' de tramo N-1 — el
        usuario puede poner cotas distintas a cada lado del vértice."""
        pts = p.get("pts") or []
        n = len(pts)
        tbl = self.tbl_seg_inv
        tbl.setRowCount(0)
        if p.get("world") or n < 3 or self._current_tab() != TAB_PIPE:
            self.gprop_segs.setVisible(False)
            self.sel_seg_idx = -1
            return
        self.gprop_segs.setVisible(True)
        if id(p) != getattr(self, "_seg_table_pipe_id", None):
            self.sel_seg_idx = -1
        self._seg_table_pipe_id = id(p)
        self._migrate_vertex_inv(p)
        # Estado por-pipe del check "Editar cotas por tramo". Por defecto OFF
        # para que la interfaz no muestre siempre editables las cotas cuando
        # ya tenemos los campos de rasante inicio/fin — el usuario lo activa
        # cuando de verdad quiere editar por tramo.
        seg_edit = bool(p.get("seg_edit_enabled", False))
        self._prop_guard = True
        self.btn_seg_edit.setChecked(seg_edit)
        _bind(self.btn_seg_edit, "setText",
              "Desactivar edición por tramo" if seg_edit else "Activar edición por tramo",
              pre="✕  " if seg_edit else "✎  ")
        self._prop_guard = False
        ov_out = p.get("vertex_inv_out") or {}
        ov_in  = p.get("vertex_inv_in") or {}
        z_start = p.get("inv_start") or 0.0; z_end = p.get("inv_end") or 0.0
        auto_z = self._interp_vertex_z(pts, z_start, z_end, ov_out)
        auto_z_in = self._interp_vertex_z(pts, z_start, z_end, ov_in)
        nseg = n - 1
        tbl.setRowCount(nseg)
        for si in range(nseg):
            v0, v1 = si, si + 1
            z0 = ov_out.get(v0, auto_z[v0]) if v0 != 0 else z_start
            z1 = ov_in.get(v1, auto_z_in[v1]) if v1 != n - 1 else z_end
            length = math.hypot(pts[v1][0] - pts[v0][0], pts[v1][1] - pts[v0][1])

            # Etiqueta corta "T1" — la MISMA que se dibuja sobre el tramo en el
            # lienzo, para que el usuario vea la correspondencia de un vistazo.
            # El detalle (vértices) va al tooltip: así la columna es estrecha y
            # la tabla entra sin barra horizontal en el dock.
            item = QtWidgets.QTableWidgetItem(f"T{si + 1}")
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            item.setData(QtCore.Qt.UserRole, si)
            item.setToolTip(_tr("Tramo {t}: vértice {v0} → vértice {v1}\nLongitud {largo} ft\n"
                                "Clic para resaltarlo en el lienzo.").format(
                                    t=si + 1, v0=v0, v1=v1, largo=f"{length:.2f}"))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            tbl.setItem(si, 0, item)

            if v0 == 0:
                # Inicio del primer tramo = rasante global (inv_start) — siempre
                # editable, no depende del check per-tramo.
                sp0 = _SegInvSpinBox()
                sp0.setRange(-100000, 100000); sp0.setDecimals(3)
                sp0.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp0.setValue(z0); sp0.setStyleSheet("font-weight: bold;")
                sp0.editingFinished.connect(lambda sp=sp0: self._seg_endpoint_changed("start", sp.value()))
                tbl.setCellWidget(si, 1, sp0)
            else:
                sp0 = _SegInvSpinBox()
                sp0.setRange(-100000, 100000); sp0.setDecimals(3)
                sp0.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp0.setValue(z0)
                if v0 in ov_out: sp0.setStyleSheet("font-weight: bold;")
                sp0.setEnabled(seg_edit)
                sp0.editingFinished.connect(lambda vi=v0, sp=sp0: self._seg_value_changed("out", vi, sp.value()))
                tbl.setCellWidget(si, 1, sp0)

            if v1 == n - 1:
                # Fin del último tramo = rasante global (inv_end) — siempre
                # editable, no depende del check per-tramo.
                sp1 = _SegInvSpinBox()
                sp1.setRange(-100000, 100000); sp1.setDecimals(3)
                sp1.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp1.setValue(z1); sp1.setStyleSheet("font-weight: bold;")
                sp1.editingFinished.connect(lambda sp=sp1: self._seg_endpoint_changed("end", sp.value()))
                tbl.setCellWidget(si, 2, sp1)
            else:
                sp = _SegInvSpinBox()
                sp.setRange(-100000, 100000); sp.setDecimals(3)
                sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp.setValue(z1)
                if v1 in ov_in: sp.setStyleSheet("font-weight: bold;")
                sp.setEnabled(seg_edit)
                sp.editingFinished.connect(lambda vi=v1, sp=sp: self._seg_value_changed("in", vi, sp.value()))
                tbl.setCellWidget(si, 2, sp)

            lbl_len = QtWidgets.QLabel(f"{length:.2f}"); lbl_len.setAlignment(QtCore.Qt.AlignCenter)
            tbl.setCellWidget(si, 3, lbl_len)
        if 0 <= self.sel_seg_idx < nseg:
            self._select_segment(self.sel_seg_idx, refocus=False)

    def _select_segment(self, si, refocus=True):
        """Marca el tramo `si` (entre pts[si] y pts[si+1]) como resaltado.
        Si `refocus`, solo salta la vista cuando el tramo NO está ya visible:
        entonces centra y hace un zoom SUAVE dejando bastante contexto (el
        tramo ocupa ~1/8 de la vista, no 1/3) para no desorientar al usuario.
        Si el tramo ya está en pantalla, no toca ni zoom ni encuadre."""
        self.sel_seg_idx = si
        if refocus and 0 <= self.sel_pipe < len(self.pipes):
            pts = self.pipes[self.sel_pipe].get("pts") or []
            if 0 <= si < len(pts) - 1:
                (x1, y1), (x2, y2) = pts[si], pts[si + 1]
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                length = math.hypot(x2 - x1, y2 - y1)
                view_rect = self.canvas.mapToScene(self.canvas.viewport().rect()).boundingRect()
                seg_rect = QtCore.QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                if not view_rect.contains(seg_rect):
                    if length > 1e-6:
                        visible_w = max(view_rect.width(), 1.0)
                        target_w = length * 8.0
                        if visible_w > target_w:
                            f = visible_w / target_w; self.canvas.scale(f, f)
                    self.canvas.centerOn(cx, cy)
        self._redraw()

    @staticmethod
    def _migrate_vertex_inv(p):
        # Migración de formato (pura) en model_ops.
        model_ops.migrate_vertex_inv(p)

    def _seg_value_changed(self, side, vi, value):
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        self._push()
        # Snapshot de TODOS los valores actualmente mostrados (auto + overrides)
        # antes de aplicar el cambio. Sin esto, editar el Fin del Tramo N
        # recalcularía por interpolación el Fin del Tramo N-1 (que no tiene
        # override) usando la Z recién editada como ancla — cascade que el
        # usuario ve como "me cambió el fin del anterior". Con el snapshot,
        # todos los intermedios pasan a ser overrides fijos e independientes.
        self._snapshot_seg_values(p)
        key = "vertex_inv_out" if side == "out" else "vertex_inv_in"
        ov = p.setdefault(key, {})
        ov[vi] = value
        self._rebuild_seg_inv_table(p)
        self._redraw()

    def _snapshot_seg_values(self, p):
        # Congelado de cotas por tramo como overrides (puro) en model_ops.
        model_ops.snapshot_seg_values(p)

    def _seg_edit_toggled(self, enabled):
        """Toggle del botón 'Editar cotas por tramo'. Al activar, congela los
        valores actuales de la tabla como overrides (así las ediciones
        posteriores no propagan), habilita los spinboxes y muestra las
        etiquetas T1, T2… en el lienzo. Al desactivar, conserva los valores
        guardados pero deshabilita la edición y oculta las etiquetas."""
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        self._push()
        p["seg_edit_enabled"] = bool(enabled)
        if enabled:
            self._snapshot_seg_values(p)
        self._rebuild_seg_inv_table(p)
        self._redraw()

    def _seg_endpoint_changed(self, which, value):
        """Editar 'Inicio' del primer tramo o 'Fin' del último tramo desde la
        tabla: son el mismo dato que inv_start/inv_end de la utilidad (arriba
        en 'Propiedades de la utilidad'), así que se escribe ahí directo — no
        en vertex_inv — y se sincroniza el spinbox de arriba con el guard para
        no re-disparar _prop_changed a mitad de la actualización."""
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        self._push()
        if which == "start": p["inv_start"] = value
        else: p["inv_end"] = value
        self._prop_guard = True
        self.prop_inv0.setValue(p.get("inv_start") or 0.0)
        self.prop_inv1.setValue(p.get("inv_end") or 0.0)
        self._prop_guard = False
        self._rebuild_seg_inv_table(p)
        # Reclasificar cruces: editar el extremo del primer/último tramo cambia
        # la cota interpolada y puede volver un conflicto en sugerencia (o
        # viceversa) — igual que hace _prop_changed al tocar la rasante arriba.
        self._redraw()

    def _seg_row_label_clicked(self, row, col):
        if col != 0: return
        item = self.tbl_seg_inv.item(row, 0)
        if item is None: return
        si = item.data(QtCore.Qt.UserRole)
        if si is None: return
        self._select_segment(int(si), refocus=True)

    def _pipe_net_kind(self, p):
        """Devuelve 'gravity' | 'pressure' | 'conduit' según la capa del pipe."""
        from nucleo.model import network_kind
        return network_kind(p.get("layer") or "")

    def _on_civil_year_changed(self, i):
        """Al cambiar la versión de Civil 3D en el toolbar, actualiza el combo
        de idiomas disponibles y refresca los combos de familias/tamaños del
        panel activo (pipes y buzones/cajas) contra el catálogo del año elegido."""
        self.civil_year = self.cmb_civil.itemData(i)
        self._refill_lang_combo()
        self._refresh_catalog_panels()

    def _on_civil_lang_changed(self, i):
        """Al cambiar el idioma del catálogo, propaga a civil_catalog y refresca
        los paneles inmediatamente."""
        from catalogo import civil_catalog as _cc
        lang = self.cmb_lang.itemData(i)
        _cc.set_current_lang(lang)
        self._refresh_catalog_panels()

    def _restore_civil_selection(self, year, lang):
        """Repone en el toolbar la versión/idioma de Civil 3D guardados en el
        proyecto (si esa versión está instalada). Se llama al abrir un proyecto.
        Se bloquean señales para no disparar refrescos intermedios; al final se
        refresca una sola vez."""
        from catalogo import civil_catalog as _cc
        if year is None:
            return                                   # proyecto viejo (sin este dato guardado)
        if year not in set(_cc.installed_versions()):
            # La versión guardada no está instalada/detectada en ESTA PC → no se
            # puede seleccionar. Se avisa (visible, no un mensaje de barra que se
            # pisa) para que el usuario entienda por qué quedó en otra versión.
            QtWidgets.QMessageBox.information(
                self, _tr("Civil 3D del proyecto no disponible"),
                _tr("El proyecto se guardó con Civil 3D {version}, pero esa versión no "
                    "está instalada/detectada en esta PC.\n\nSe mantiene la versión activa "
                    "({activa}). El catálogo de familias saldrá de esa versión.").format(
                    version=f"{year} ({lang})" if lang else year, activa=self.civil_year or "—"))
            return
        idx = self.cmb_civil.findData(year)
        if idx < 0:
            return
        self.cmb_civil.blockSignals(True)
        self.cmb_civil.setCurrentIndex(idx)
        self.cmb_civil.blockSignals(False)
        self.civil_year = year
        self._refill_lang_combo()                    # repuebla idiomas del año elegido
        if lang:
            li = self.cmb_lang.findData(lang)
            if li >= 0:
                self.cmb_lang.blockSignals(True)
                self.cmb_lang.setCurrentIndex(li)
                self.cmb_lang.blockSignals(False)
                _cc.set_current_lang(lang)
        self._refresh_catalog_panels()

    def _refill_lang_combo(self):
        """Repuebla el combo de idiomas con los realmente instalados para el año
        activo. Preserva la selección previa si sigue disponible."""
        from catalogo import civil_catalog as _cc
        prev = self.cmb_lang.currentData() if hasattr(self, "cmb_lang") else None
        self.cmb_lang.blockSignals(True); self.cmb_lang.clear()
        langs = _cc.installed_langs(self.civil_year) if self.civil_year else []
        if not langs:
            self.cmb_lang.addItem("—", None)
            _cc.set_current_lang(None)
        else:
            for lg in langs:
                # Etiqueta amigable
                pretty = {"esp": "esp (Español)", "enu": "enu (English)",
                          "fra": "fra (Français)", "deu": "deu (Deutsch)",
                          "ita": "ita (Italiano)", "ptb": "ptb (Português)"}.get(lg, lg)
                self.cmb_lang.addItem(pretty, lg)
            # Reponer la selección previa si sigue disponible; si no, primera
            target = prev if prev in langs else langs[0]
            idx = self.cmb_lang.findData(target)
            if idx >= 0: self.cmb_lang.setCurrentIndex(idx)
            _cc.set_current_lang(target)
        self.cmb_lang.blockSignals(False)

    def _refresh_catalog_panels(self):
        """Vuelve a leer el catálogo Civil 3D del año actual y repuebla los combos
        de familia/tamaño del panel activo (pipe y buzón/caja). Se llama tras
        cambiar la versión y también tras instalar/desinstalar familias."""
        try:
            if 0 <= getattr(self, "sel_pipe", -1) < len(self.pipes):
                self._reload_pipe_families(self.pipes[self.sel_pipe])
        except Exception: pass
        try:
            if 0 <= getattr(self, "sel_bz", -1) < len(self.structures):
                self._sync_bz_panel()
        except Exception: pass
        try:
            if 0 <= getattr(self, "sel_curve", -1) < len(self.structures):
                self._sync_curve_panel()
        except Exception: pass
