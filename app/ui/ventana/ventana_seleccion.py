"""Acordeón, propiedades y selección múltiple de utilidades (menús contextuales).

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class SeleccionMixin:
    # ─────────────────────── Acordeón: cambios de sección ────────────────────────
    def _place_widget(self, w, target_layout):
        """Mueve un widget al layout indicado (Qt reasigna su padre automáticamente).
        Es como "mover una caja" de un estante a otro. Si el widget ya estaba en un
        layout, primero lo quitamos de ese layout (removeWidget). Si no hacemos esto,
        Qt puede dejar celdas huérfanas o mostrar el widget en dos sitios."""
        if w.parent() is not None:
            pl = w.parent().layout()
            if pl is not None:
                pl.removeWidget(w)
        target_layout.addWidget(w)

    def _on_toolbox_change(self, idx):
        """Al abrir una sección distinta del acordeón:
          1) Salimos del modo activo (evita mezclar 'colocar Multileader' con
             el usuario abriendo la sección Texto por error).
          2) Reparentamos los widgets COMPARTIDOS a la sección correspondiente:
             - orient_combo → Leader
             - gtxt (estilo) → Texto libre
             - rot_row visible solo en Texto libre
          3) Refrescamos la UI (etiqueta del modo, botones activos, etc.)."""
        # Descubrimos qué sección ("key") corresponde al índice.
        key = next((k for k, i in self._sec_idx.items() if i == idx), None)
        if self.mode not in ("idle",):
            self.set_mode("idle")
        if key == "leader":
            self._place_widget(self.orient_combo, self._slot_orient_ld)
        elif key == "text":
            self._place_widget(self.gtxt, self._slot_style_tx)
            self.rot_row.setVisible(True)
        self._update_ui()

    def _open_section(self, key):
        """Abre programáticamente una sección del acordeón por su nombre lógico.
        La usamos p.ej. cuando el usuario selecciona un Multileader en el
        inventario: abrimos automáticamente la sección Multileader para que
        vea su estilo/orientación y pueda editarlos."""
        i = self._sec_idx.get(key)
        if i is not None and self.toolbox.currentIndex() != i:
            self.toolbox.setCurrentIndex(i)

    def _bump_size(self, delta):
        """Sube o baja la altura del texto en pasos de 0.5 pies."""
        self.size_spin.setValue(round(max(0.5, self.size_spin.value() + delta), 2))

    def _bump_rot(self, delta):
        self.rot_spin.setValue((self.rot_spin.value() + delta) % 360)

    def _bump_opacity(self, delta_pct):
        val = self.canvas.pdf_opacity + delta_pct / 100.0
        self.canvas.set_pdf_opacity(val)
        self.lbl_opacity.setText(f"{round(self.canvas.pdf_opacity * 100)}%")

    def _px_for_ft(self, ft):
        raw = ft / self.scale * self.zoom if self.scale else ft * self.zoom
        cap = self.pageH_px * 0.06 if self.pageH_px else 200
        return max(8.0, min(raw, cap))

    def _style_changed(self):
        if self._style_guard: return
        ti = self._current_tab()
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            tm = self.text_marks[self.sel_text]; self._push()
            tm["font"] = self.font_combo.currentFont().family(); tm["size_ft"] = self.size_spin.value()
            tm["bold"] = self.chk_bold.isChecked(); tm["rot"] = self.rot_spin.value() % 360
            self._redraw()
        # (Multileader eliminado — solo quedan Leaders simples sin texto editable.)

    def _prop_changed(self):
        """Callback: cualquier cambio en el panel Propiedades escribe al modelo.
        `self._push()` guarda un snapshot para Ctrl+Z (deshacer).
        La UNIDAD de diámetro/invert es la del proyecto (self.work_unit), no per-pipe."""
        if self._prop_guard: return
        if self._current_tab() == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            p = self.pipes[self.sel_pipe]; self._push()
            p["name"] = self.prop_name.text().strip()
            p["diam_unit"] = "in"                                        # el diámetro nunca va en pies
            p["unit"] = self.work_unit                                  # unidad de trabajo (coords/cotas)
            p["part"] = self.prop_part.text().strip()
            p["inv_start"] = self.prop_inv0.value(); p["inv_end"] = self.prop_inv1.value()
            # Guardamos el VALOR real (data), no el texto traducido en pantalla.
            p["material"] = self.prop_material.currentData() or self.prop_material.currentText()
            p["net_type"] = self.prop_nettype.currentData() or ""
            # Familia + tamaño del catálogo Civil 3D. El diámetro se deriva del tamaño.
            if self.prop_family.isVisibleTo(self.gprop):     # no depende de que el panel esté desplegado
                p["pipe_family"] = self.prop_family.currentData() or ""
                p["pipe_size"] = self.prop_size.currentData() or "" if self.prop_size.isEnabled() else ""
            # p["diam"] se calcula del pipe_size (p.ej. "24 in" → 24.0). Sin tamaño de
            # catálogo se CONSERVA el diámetro que ya tenía: antes quedaba en 0 al
            # editar cualquier campo (p. ej. el nombre) y cambiaban las alertas.
            # Sin tamaño de catálogo = diámetro PRECARGADO (model_ops.DIAM_DEFECTO_IN).
            d_size = _extract_diam_from_size(p.get("pipe_size", "")) or model_ops.DIAM_DEFECTO_IN
            if d_size or not p.get("diam"):
                p["diam"] = d_size
            self._refresh_lists()
            self._rebuild_seg_inv_table(p)
            # Repintamos el lienzo para que los marcadores de cruces se
            # reclasifiquen inmediatamente: al cambiar inv_start/inv_end,
            # una sugerencia (cotas distintas) puede volverse conflicto
            # (cotas iguales) o viceversa.
            self._redraw()

    def _refresh_unit_labels(self):
        """Etiquetas de campo fijas: cotas en PIES, diámetro en PULGADAS.
        (Ya no hay selector de unidad; todo va por campo.)"""
        # (Diámetro se muestra vía combo de tamaño del catálogo, no necesita etiqueta aquí)
        if hasattr(self, "lbl_prop_inv0"): _bind(self.lbl_prop_inv0, "setText", "Elev. de rasante inicial (ft):")
        if hasattr(self, "lbl_prop_inv1"): _bind(self.lbl_prop_inv1, "setText", "Elev. de rasante final (ft):")

    def _refresh_counts(self):
        """Contadores en vivo en la barra de estado: utilidades, leaders, textos, zonas."""
        if not hasattr(self, "lbl_counts"): return
        n_p = len(self.pipes); n_l = len(self.leaders); n_t = len(self.text_marks); n_z = len(self.erase_regions)
        _bind(self.lbl_counts, "setText", "{p} util · {l} lead · {t} txt · {z} zona",
              fmt={"p": n_p, "l": n_l, "t": n_t, "z": n_z})
        # marca de "sin guardar"
        if hasattr(self, "lbl_dirty"):
            if self._dirty:
                self.lbl_dirty.setText("●"); self.lbl_dirty.setStyleSheet(f"color:{_theme.tokens().danger};")
            else:
                self.lbl_dirty.setText("")
        self._update_title()

    def change_pipe_type(self):
        rows = self._selected_pipe_rows()
        if rows:
            self._push()
            for r in rows:
                self.pipes[r]["layer"] = self.active_layer()
                self.pipes[r]["ab"] = self.chk_ab.isChecked()
            self._refresh_lists(); self._reselect_pipes(rows); self._redraw()

    # ── selección múltiple de utilidades ──
    def _selected_pipe_rows(self):
        """Filas seleccionadas en «Utilidades». Solo cuenta como selección
        múltiple si incluye la utilidad actual (`sel_pipe`); si no, la actual
        sola (así nada actúa sobre una selección vieja de la lista)."""
        if not (0 <= self.sel_pipe < len(self.pipes)):
            return []
        rows = sorted({self.pipe_list.row(it) for it in self.pipe_list.selectedItems()})
        rows = [r for r in rows if 0 <= r < len(self.pipes)]
        if len(rows) > 1 and self.sel_pipe in rows:
            return rows
        return [self.sel_pipe]

    def _reselect_pipes(self, rows):
        """Vuelve a seleccionar estas filas tras rehacer la lista."""
        rows = [r for r in rows if 0 <= r < self.pipe_list.count()]
        if not rows:
            return
        cur = self.sel_pipe if self.sel_pipe in rows else rows[0]
        self._no_center = True
        try:
            self.pipe_list.setCurrentRow(cur)
            sm = self.pipe_list.selectionModel()
            for r in rows:
                sm.select(self.pipe_list.model().index(r, 0),
                          QtCore.QItemSelectionModel.Select)
        finally:
            self._no_center = False

    def _pipe_selection_changed(self):
        n = len(self.pipe_list.selectedItems())
        if n > 1:
            self._info(_tr("{n} utilidades seleccionadas — clic derecho para acciones en bloque.").format(n=n))
        # Orden en que se fueron seleccionando: la PRIMERA es la base al unir.
        actuales = {self.pipe_list.row(it) for it in self.pipe_list.selectedItems()}
        previo = [r for r in getattr(self, "_orden_sel", []) if r in actuales]
        self._orden_sel = previo + sorted(actuales - set(previo))
        filas = tuple(self._selected_pipe_rows())
        if filas != getattr(self, "_multi_dibujada", ()):      # resaltar en el lienzo
            self._multi_dibujada = filas
            self._redraw()

    def _select_all_pipes(self, layer=None):
        """Selecciona todas las utilidades (o solo las de esa capa/tipo)."""
        rows = [i for i, p in enumerate(self.pipes) if layer is None or p.get("layer") == layer]
        if not rows:
            return
        if self.sel_pipe not in rows:
            self._no_center = True
            try:
                self.pipe_list.setCurrentRow(rows[0])
            finally:
                self._no_center = False
        self._reselect_pipes(rows)

    def edit_selected_text(self):
        ti = self._current_tab()
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._edit_text_mark(self.sel_text)

    def _list_context_menu(self, listw, tab_idx, pos):
        item = listw.itemAt(pos)
        if item is None:
            # Sin item bajo el cursor: en Bancoductos permitimos "+ Nuevo" igualmente.
            if tab_idx == TAB_DB:
                menu = QtWidgets.QMenu(self)
                self._menu_act(menu, "+ Nuevo bancoducto", self._db_new)
                menu.exec(listw.viewport().mapToGlobal(pos))
            return
        if self._current_tab() != tab_idx: self._show_tab(tab_idx)
        # Clic derecho sobre una fila YA seleccionada de una selección múltiple
        # (utilidades) la conserva; si no, selecciona la fila bajo el cursor.
        if not (tab_idx == TAB_PIPE and item.isSelected()
                and len(listw.selectedItems()) > 1):
            listw.setCurrentRow(listw.row(item))
        menu = QtWidgets.QMenu(self)
        if tab_idx == TAB_PIPE and len(self._selected_pipe_rows()) > 1:
            self._pipe_bulk_menu(menu)
            menu.exec(listw.viewport().mapToGlobal(pos))
            return
        if tab_idx == TAB_PIPE:
            self._pipe_single_menu(menu)
        elif tab_idx == TAB_LEADER:
            self._menu_act(menu, "Editar/mover", self.enter_move)
        elif tab_idx == TAB_TEXT:
            self._menu_act(menu, "Mover", self.enter_move)
            self._menu_act(menu, "Editar texto", self.edit_selected_text)
        elif tab_idx == TAB_REGION:
            self._menu_act(menu, "Editar/mover", self.enter_move)
        elif tab_idx == TAB_DB:
            self._menu_act(menu, "Editar", self._db_edit)
            self._menu_act(menu, "Duplicar", self._db_duplicate)
        menu.addSeparator()
        self._menu_act(menu, "Eliminar", self.delete_selected)
        menu.exec(listw.viewport().mapToGlobal(pos))

    def _pipe_single_menu(self, menu):
        """Entradas del menú contextual de UNA utilidad (lista y lienzo)."""
        self._menu_act(menu, "Cambiar tipo", self.change_pipe_type)
        self._menu_act(menu, "Editar/mover", self.enter_move)
        # Bancoducto asignado a esta tubería: editar o crear.
        if 0 <= self.sel_pipe < len(self.pipes):
            db = self._duct_bank_for_pipe(self.sel_pipe)
            menu.addSeparator()
            if db is not None:
                self._menu_act(menu, f"Editar bancoducto «{db.name or 'sin nombre'}»",
                               lambda: self._db_edit_for_pipe(self.sel_pipe))
            else:
                self._menu_act(menu, "Crear bancoducto para esta tubería",
                               lambda: self._db_new_for_pipe(self.sel_pipe))
            self._pipe_assign_db_submenu(menu, [self.sel_pipe])
            self._pipe_select_menu(menu, self.pipes[self.sel_pipe].get("layer"))

    def _canvas_context_menu(self, x, y):
        """Clic derecho en el lienzo (sin herramienta activa) sobre una utilidad:
        el mismo menú que en la lista. Si era parte de la selección múltiple, la
        conserva; si no, la selecciona sola."""
        best = self._pipe_at(x, y)
        if best < 0:
            return
        if best not in self._selected_pipe_rows():
            self._no_center = True
            try:
                self._show_tab(TAB_PIPE); self.pipe_list.clearSelection(); self.pipe_list.setCurrentRow(best)
            finally:
                self._no_center = False
        elif best != self.sel_pipe:
            filas = self._selected_pipe_rows()
            self._no_center = True
            try:
                self.pipe_list.setCurrentRow(best)
            finally:
                self._no_center = False
            self._reselect_pipes(filas)
        menu = QtWidgets.QMenu(self)
        if len(self._selected_pipe_rows()) > 1:
            self._pipe_bulk_menu(menu)
        else:
            self._pipe_single_menu(menu)
            menu.addSeparator()
            self._menu_act(menu, "Eliminar", self.delete_selected)
        menu.exec(QtGui.QCursor.pos())

    def _pipe_at(self, x, y):
        """Índice de la utilidad más cercana al punto (a ≤ 10 px de pantalla) o -1."""
        thr = 10.0 / max(1e-6, self.canvas.transform().m11())
        best, bd = -1, thr
        for i, p in enumerate(self.pipes):
            if not p.get("pts"): continue               # tramos importados (world) no están en el lienzo
            for a, b in zip(p["pts"], p["pts"][1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < bd: bd, best = d, i
        return best

    def _toggle_pipe_selection(self, i):
        """Ctrl+clic en el lienzo: suma o quita la utilidad i de la selección
        (igual que Ctrl+clic en la lista)."""
        filas = set(self._selected_pipe_rows())
        orden = [r for r in getattr(self, "_orden_sel", []) if r in filas] or sorted(filas)
        if i in filas and len(filas) > 1:
            filas.discard(i)
            actual = self.sel_pipe if self.sel_pipe in filas else min(filas)
        else:
            filas.add(i); actual = i
        self._no_center = True
        try:
            self._show_tab(TAB_PIPE)
            self.pipe_list.setCurrentRow(actual)
        finally:
            self._no_center = False
        self.pipe_list.clearSelection()
        self._reselect_pipes(sorted(filas))
        # Rehacer la selección la reordena: se repone el orden real (la 1.ª = base al unir).
        self._orden_sel = [r for r in orden if r in filas] + [r for r in sorted(filas) if r not in orden]
        self._scroll_pipe_list_to(i)
        self._redraw()
