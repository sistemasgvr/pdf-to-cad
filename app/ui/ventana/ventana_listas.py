"""Unir utilidades, borrar, copiar/pegar y refrescar las listas del inventario.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class ListasMixin:
    def unir_utilidades(self):
        """Une las utilidades seleccionadas en UNA (unir_utilidades.py): vista
        previa en el lienzo, confirmación y un solo paso de deshacer."""
        from nucleo import unir_utilidades as U
        filas = self._selected_pipe_rows()
        if len(filas) < 2:
            QtWidgets.QMessageBox.information(self, _tr("Unir utilidades"), _tr(
                "Selecciona dos o más utilidades: Ctrl+clic en la lista «Utilidades» o sobre ellas en el lienzo."))
            return
        # Base = la primera que se seleccionó (sus datos mandan).
        base = next((r for r in getattr(self, "_orden_sel", []) if r in filas), self.sel_pipe)
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        plan = U.planificar(self.pipes, filas, base, ft_px)
        if not plan.ok:
            QtWidgets.QMessageBox.warning(self, _tr("Unir utilidades"), plan.error)
            return
        vista = self._preview_union(plan)
        try:
            huecos = [e for e in plan.empalmes if e.hueco_ft > 0]
            texto = _tr("Se unirán {n} utilidades en la #{b} ({k} empalme(s), en verde en el plano).").format(
                n=len(filas), b=base + 1, k=len(plan.empalmes))
            if huecos:
                texto += "\n\n" + _tr("Huecos que se cierran con un tramo recto: {lista}.").format(
                    lista=", ".join(f"{e.hueco_ft:.2f} ft" for e in huecos))
            if plan.sobrantes:
                texto += "\n\n" + _tr("Quedan aparte {k} trozo(s) partido(s) en la T (en ámbar en el plano).").format(
                    k=len(plan.sobrantes))
            if plan.avisos:
                texto += "\n\n" + _tr("Se conservan los datos de la #{b}:").format(b=base + 1)
                texto += "\n" + "\n".join("• " + a for a in plan.avisos[:8])
            texto += "\n\n" + _tr("Se puede deshacer con Ctrl+Z.")
            resp = QtWidgets.QMessageBox.question(self, _tr("Unir utilidades"), texto,
                                                  QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                                  QtWidgets.QMessageBox.Yes)
        finally:
            sc = self.canvas.scene()
            for it in vista:
                try: sc.removeItem(it)
                except (RuntimeError, ValueError): pass
        if resp != QtWidgets.QMessageBox.Yes:
            return
        self._push()
        self.pipes[base] = plan.pipe
        # Conexiones verticales y bancoducto de las absorbidas pasan a la base.
        for c in list(getattr(self, "cross_connections", None) or []):
            for k in ("pipe_a", "pipe_b"):
                if int(c.get(k, -1)) in plan.unidas:
                    c[k] = base
            if c.get("pipe_a") == c.get("pipe_b"):
                self.cross_connections.remove(c)
        if self._duct_bank_for_pipe(base) is None:
            for j in plan.unidas:
                db = self._duct_bank_for_pipe(j)
                if db is not None:
                    db.assign(db.assigned() + [base]); break
        self._delete_pipes(plan.unidas)
        nueva = base - sum(1 for j in plan.unidas if j < base)
        if plan.sobrantes:
            # Trozos de una utilidad partida en la T: utilidades aparte (al final de la
            # lista) y buzones/cajas en el vértice nuevo de la T.
            self.pipes.extend(plan.sobrantes)
            self._rebuild_structures()
        self._refresh_lists()
        self._no_center = True
        try:
            self._show_tab(TAB_PIPE); self.pipe_list.clearSelection(); self.pipe_list.setCurrentRow(nueva)
        finally:
            self._no_center = False
        self._redraw()
        self._info(_tr("Se unieron {n} utilidades en la #{b}.").format(n=len(filas), b=nueva + 1))

    def _preview_union(self, plan):
        """Vista previa: la utilidad resultante en verde a trazos y un círculo en
        cada empalme (los tramos nuevos que cierran un hueco, más gruesos)."""
        sc = self.canvas.scene(); items = []
        verde = QtGui.QColor(30, 200, 60)
        pen = QtGui.QPen(verde, 5.0, QtCore.Qt.DashLine); pen.setCosmetic(True)
        path = QtGui.QPainterPath()
        # Con sus codos, igual que el lienzo (los vértices de la unida coinciden con
        # los de las originales: cada CV sigue siendo de su vértice).
        pts = self._pipe_display_pts(plan.pipe)
        path.moveTo(*pts[0])
        for q in pts[1:]:
            path.lineTo(*q)
        it = sc.addPath(path, pen); it.setZValue(Z_HANDLE + 5); items.append(it)
        # Trozos partidos en una T que quedan como utilidades aparte: en ámbar.
        pen_s = QtGui.QPen(QtGui.QColor(240, 170, 20), 4.0, QtCore.Qt.DashDotLine); pen_s.setCosmetic(True)
        for sob in plan.sobrantes:
            ps = self._pipe_display_pts(sob)
            ruta = QtGui.QPainterPath(); ruta.moveTo(*ps[0])
            for q in ps[1:]:
                ruta.lineTo(*q)
            it = sc.addPath(ruta, pen_s); it.setZValue(Z_HANDLE + 5); items.append(it)
        pen_c = QtGui.QPen(QtGui.QColor(20, 20, 20), 2.0); pen_c.setCosmetic(True)
        for e in plan.empalmes:
            r = 9.0
            c = sc.addEllipse(-r, -r, 2 * r, 2 * r, pen_c, QtGui.QBrush(verde))
            c.setPos(e.x, e.y); c.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            c.setZValue(Z_HANDLE + 6); items.append(c)
        self.canvas.viewport().update()
        QtWidgets.QApplication.processEvents()
        return items

    def _pipe_select_menu(self, menu, layer):
        """Entradas de selección masiva del menú de «Utilidades»."""
        menu.addSeparator()
        self._menu_act(menu, _tr("Seleccionar todas las utilidades (Ctrl+A)"), lambda: self._select_all_pipes())
        if layer:
            self._menu_act(menu, _tr("Seleccionar todas las de tipo «{tipo}»").format(tipo=self._tipo(layer)),
                           lambda: self._select_all_pipes(layer))

    def _pipe_assign_db_submenu(self, menu, rows):
        """Submenú «Asignar bancoducto existente» para estas utilidades."""
        dbs = getattr(self, "duct_banks", []) or []
        if not dbs:
            return
        sub = menu.addMenu(_tr("Asignar bancoducto existente"))
        for k, db in enumerate(dbs):
            nm = db.name or _tr("(sin nombre)")
            a = sub.addAction(_icon("mdi:grid"), _tr("{nombre}  ·  {n} conducto(s)").format(
                nombre=nm, n=len(db.conduits)))
            a.triggered.connect(lambda _=False, k=k: self._db_assign_to_pipes(k, rows))

    def _pipe_bulk_menu(self, menu):
        """Menú contextual con VARIAS utilidades seleccionadas."""
        rows = self._selected_pipe_rows()
        head = menu.addAction(_tr("{n} utilidades seleccionadas").format(n=len(rows)))
        head.setEnabled(False)
        menu.addSeparator()
        self._menu_act(menu, _tr("Unir en una utilidad (Ctrl+J)"), self.unir_utilidades)
        menu.addSeparator()
        self._menu_act(menu, _tr("Cambiar tipo ({n})").format(n=len(rows)), self.change_pipe_type)
        self._menu_act(menu, _tr("Editar en bloque: familia, diámetro… ({n})").format(n=len(rows)),
                       self.editar_en_bloque)
        base = next((r for r in getattr(self, "_orden_sel", []) if r in rows), rows[0])
        self._menu_act(menu, _tr("Copiar propiedades de la #{n} a las demás").format(n=base + 1),
                       self.copiar_de_la_primera)
        if getattr(self, "_props_copiadas", None):
            self._menu_act(menu, _tr("Pegar propiedades de la #{n}").format(n=self._props_copiadas[2]),
                           self.pegar_propiedades)
        menu.addSeparator()
        self._menu_act(menu, _tr("Crear un bancoducto para las {n} utilidades").format(n=len(rows)),
                       lambda: self._db_new_for_pipes(rows))
        self._pipe_assign_db_submenu(menu, rows)
        if any(self._duct_bank_for_pipe(r) is not None for r in rows):
            self._menu_act(menu, _tr("Quitar el bancoducto de las {n} utilidades").format(n=len(rows)),
                           lambda: self._db_unassign_pipes(rows))
        self._pipe_select_menu(menu, self.pipes[self.sel_pipe].get("layer"))
        menu.addSeparator()
        self._menu_act(menu, _tr("Eliminar {n} utilidades").format(n=len(rows)), self.delete_selected)

    def _delete_pipes(self, rows):
        """Borra estas utilidades (de mayor a menor índice) y corre los índices
        de las conexiones verticales y de los bancoductos asignados."""
        from nucleo.duct_bank import reindex_after_pipe_delete
        for r in sorted(set(rows), reverse=True):
            if not (0 <= r < len(self.pipes)):
                continue
            self.pipes.pop(r)
            self._reindex_cross_connections_on_pipe_delete(r)
            reindex_after_pipe_delete(getattr(self, "duct_banks", []) or [], r)
        self.sel_pipe = -1

    def _delete_duct_bank_warning(self, rows):
        """Aviso resaltado (HTML) si alguna de estas utilidades lleva bancoducto:
        cuáles, con qué diseño, y qué pasa con ese diseño. "" si ninguna lo lleva."""
        import html as _html
        t = _theme.tokens()
        filas = []
        for r in rows:
            db = self._duct_bank_for_pipe(r) if 0 <= r < len(self.pipes) else None
            if db is not None:
                filas.append(_tr("Utilidad #{n} → bancoducto «{nombre}» ({c} conducto(s))").format(
                    n=r + 1, nombre=db.name or _tr("sin nombre"), c=len(db.conduits)))
        if not filas:
            return ""
        lista = "".join(f"<li>{_html.escape(f)}</li>" for f in filas[:10])
        if len(filas) > 10:
            lista += "<li>…</li>"
        return (f"<p style='color:{t.danger}; font-weight:700;'>⚠ "
                + _html.escape(_tr("Tiene bancoducto asignado:") if len(filas) == 1
                               else _tr("{n} utilidades tienen bancoducto asignado:").format(n=len(filas)))
                + f"</p><ul style='margin-top:0;'>{lista}</ul>"
                f"<p style='color:{t.text_muted};'>"
                + _html.escape(_tr("Al eliminarla(s) se quita esa asignación. El diseño del bancoducto se "
                                   "conserva en la lista «Bancoductos» (sin asignar si no queda en ninguna "
                                   "otra utilidad). Se puede deshacer con Ctrl+Z."))
                + "</p>")

    def delete_selected(self):
        ti = self._current_tab()
        desc = None
        rows = self._selected_pipe_rows() if ti == TAB_PIPE else []
        if ti == TAB_PIPE and len(rows) > 1:
            desc = _tr("{n} utilidades ({lista})").format(
                n=len(rows), lista=", ".join(f"#{r + 1}" for r in rows[:12])
                + (" …" if len(rows) > 12 else ""))
        elif ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            p = self.pipes[self.sel_pipe]
            desc = _tr("Utilidad #{n} ({capa}, {v} vértices)").format(
                n=self.sel_pipe + 1, capa=self._etq(p), v=len(p.get("pts", [])))
        elif ti == TAB_LEADER and 0 <= self.sel_leader < len(self.leaders):
            desc = _tr("Leader #{n}").format(n=self.sel_leader + 1)
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            txt = self.text_marks[self.sel_text].get("text", "")[:30]
            desc = _tr("Texto #{n} «{txt}»").format(n=self.sel_text + 1, txt=txt)
        elif ti == TAB_REGION and 0 <= self.sel_region < len(self.erase_regions):
            desc = _tr("Zona de borrado #{n}").format(n=self.sel_region + 1)
        elif ti == TAB_CL and 0 <= self.sel_cl < len(self.ref_centerlines):
            desc = _tr("Centerline #{n}").format(n=self.sel_cl + 1)
        elif ti == TAB_DB and 0 <= self.sel_db < len(getattr(self, "duct_banks", [])):
            db = self.duct_banks[self.sel_db]
            desc = _tr("Bancoducto «{nombre}» ({n} conducto(s))").format(
                nombre=db.name or _tr("sin nombre"), n=len(db.conduits))
        if desc is None:
            return
        msg = _tr("¿Eliminar {que}?").format(que=desc)
        aviso = self._delete_duct_bank_warning(rows or [self.sel_pipe]) if ti == TAB_PIPE else ""
        if aviso:
            import html as _html
            msg = f"<p>{_html.escape(msg)}</p>{aviso}"
        r = QtWidgets.QMessageBox.question(
            self, _tr("Confirmar eliminación"), msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if r != QtWidgets.QMessageBox.Yes:
            return
        if ti == TAB_PIPE:
            self._push()
            self._delete_pipes(rows or [self.sel_pipe])
        elif ti == TAB_LEADER:
            self._push(); self.leaders.pop(self.sel_leader); self.sel_leader = -1
        elif ti == TAB_TEXT:
            self._push(); self.text_marks.pop(self.sel_text); self.sel_text = -1
        elif ti == TAB_REGION:
            self._push(); self.erase_regions.pop(self.sel_region); self.sel_region = -1
        elif ti == TAB_CL:
            self._push(); self.ref_centerlines.pop(self.sel_cl); self.sel_cl = -1
        elif ti == TAB_DB:
            self._push(); self.duct_banks.pop(self.sel_db); self.sel_db = -1
            if hasattr(self, "lbl_ductbank_count"):
                _bind(self.lbl_ductbank_count, "setText", "Duct banks guardados: {n}", fmt={"n": len(self.duct_banks)})
            self._dirty = True
        self._refresh_lists(); self._redraw()

    def _copy_sel(self):
        ti = self._current_tab()
        if ti == TAB_LEADER and 0 <= self.sel_leader < len(self.leaders): self._clip = ("leader", copy.deepcopy(self.leaders[self.sel_leader]))
        elif ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes): self._clip = ("pipe", copy.deepcopy(self.pipes[self.sel_pipe]))
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._clip = ("text", copy.deepcopy(self.text_marks[self.sel_text]))
        else: self._info(_tr("Selecciona algo para copiar.")); return
        self._info(_tr("Copiado. Ctrl+V para pegar una copia."))

    def _paste_sel(self):
        if not self._clip: return
        kind, obj = self._clip; o = copy.deepcopy(obj); d = 30; self._push()
        if kind == "leader":
            if o.get("arrow"): o["arrow"] = (o["arrow"][0] + d, o["arrow"][1] + d)
            if o.get("landing"): o["landing"] = (o["landing"][0] + d, o["landing"][1] + d)
            if o.get("tp"): o["tp"] = (o["tp"][0] + d, o["tp"][1] + d)
            self.leaders.append(o); self._refresh_lists(); self._select_leader(len(self.leaders) - 1)
        elif kind == "pipe":
            o["pts"] = [(x + d, y + d) for (x, y) in o["pts"]]; self.pipes.append(o)
            self._show_tab(TAB_PIPE); self._refresh_lists(); self.pipe_list.setCurrentRow(len(self.pipes) - 1)
        elif kind == "text":
            o["pos"] = (o["pos"][0] + d, o["pos"][1] + d); self.text_marks.append(o)
            self._show_tab(TAB_TEXT); self._refresh_lists(); self.txt_marks_list.setCurrentRow(len(self.text_marks) - 1)
        self._redraw(); self._info(_tr("Pegado (copia desplazada)."))

    def _refresh_lists(self):
        self._refresh_counts()
        self.pipe_list.blockSignals(True); self.pipe_list.clear()
        for i, p in enumerate(self.pipes, 1):
            tag = " (AB)" if p.get("ab") else ""
            nm = " · " + ((p.get("name") or "").strip() or model_ops.nombre_por_defecto(p, i - 1))
            n = len(p.get("pts") or [])
            info = (_tr("red: {red}").format(red=p.get("net", "")) if p.get("world")
                    else _tr("{n} vért.").format(n=n))
            it = QtWidgets.QListWidgetItem(swatch_icon(layer_qcolor(p["layer"])),
                                           f"{i}. {self._tipo(p['layer'])}{tag}{nm} ({info})")
            self.pipe_list.addItem(it)
        self.pipe_list.blockSignals(False)
        self.sleader_list.blockSignals(True); self.sleader_list.clear()
        ns = 0
        for i, ld in enumerate(self.leaders):
            ns += 1
            o = next((_tr(lbl) for oid, lbl in LEADER_ORIENT if oid == ld.get("orient", "d")), "")
            it = QtWidgets.QListWidgetItem(_tr("{n}. Leader {orientacion}").format(n=ns, orientacion=o.lower()).rstrip())
            it.setData(QtCore.Qt.UserRole, i); self.sleader_list.addItem(it)
        self.sleader_list.blockSignals(False)
        self.txt_marks_list.blockSignals(True); self.txt_marks_list.clear()
        for i, tm in enumerate(self.text_marks, 1): self.txt_marks_list.addItem(f"{i}. {tm['text'][:28].replace(chr(10), ' / ')}")
        self.txt_marks_list.blockSignals(False)
        self.region_list.blockSignals(True); self.region_list.clear()
        for i, rg in enumerate(self.erase_regions, 1):
            it = QtWidgets.QListWidgetItem(_tr("Zona {i} ({n} vértices)").format(i=i, n=len(rg['pts'])))
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if rg.get("enabled", True) else QtCore.Qt.Unchecked)
            self.region_list.addItem(it)
        self.region_list.blockSignals(False)
        # Refrescar tabs Buzones/Curvas (vistas filtradas de self.structures según
        # 'curve') + paneles de propiedades del elemento seleccionado en cada una.
        self._rebuild_structures()
        self.bz_list.blockSignals(True); self.bz_list.clear()
        self.curve_list.blockSignals(True); self.curve_list.clear()
        self._bz_rows = []; self._curve_rows = []
        for i, s in enumerate(self.structures):
            is_curve = bool(s.get("curve"))
            if is_curve:
                p = self._pipe_at_vertex(s.get("x"), s.get("y")) if s.get("x") is not None else None
                fam = (p.get("pipe_family") if p else "") or _tr("(sin familia)")
                sz = f"  {p['pipe_size']}" if p and p.get("pipe_size") else ""
                item_icon = _icon("mdi:vector-curve", color="#a855f7")   # curva = violeta
            else:
                fam = s.get("part") or _tr("(sin familia)")
                sz = f"  {s['part_size']}" if s.get("part_size") else ""
                if s.get("hidden"):
                    item_icon = _icon("mdi:eye-off-outline", color=_theme.tokens().text_muted)
                elif s.get("solid"):
                    item_icon = _icon("mdi:cube-outline", color="#f97316")    # sólido 3D = cubo
                elif s.get("net") == "conduit":
                    item_icon = _icon("mdi:circle-medium", color="#f97316")   # conducto = naranja
                else:
                    item_icon = _icon("mdi:circle-medium", color="#3b82f6")   # buzón = azul
            it = QtWidgets.QListWidgetItem(item_icon, self._solid_label(s) if s.get("solid") and not is_curve
                                           else f"{s.get('cod', '?')}  ·  {fam}{sz}")
            if not is_curve and s.get("hidden"):
                it.setForeground(QtGui.QColor(_theme.tokens().text_muted))
                it.setToolTip(_tr("Oculto — no se dibuja ni se crea en Civil3D como buzón real."))
            if is_curve: self.curve_list.addItem(it); self._curve_rows.append(i)
            else: self.bz_list.addItem(it); self._bz_rows.append(i)
        self.bz_list.blockSignals(False); self.curve_list.blockSignals(False)
        self._sync_bz_panel(); self._sync_curve_panel()
        self.cl_list.blockSignals(True); self.cl_list.clear()
        for c in self.ref_centerlines:
            _it_cl = QtWidgets.QListWidgetItem(
                _icon("mdi:vector-line", color="#22c55e"),
                _tr("{cod}  ·  {n} vértices").format(cod=c.get('cod', '?'), n=len(c.get('pts') or [])))
            self.cl_list.addItem(_it_cl)
        self.cl_list.blockSignals(False)
        self._sync_cl_panel()
        self._refresh_db_list()
        self._set_item_tooltips()

    def _set_item_tooltips(self):
        """Pone el texto completo de cada item como su tooltip. Las listas usan
        elide a la derecha para no sacar barra horizontal (ver el bloque
        RESPONSIVO en _build_ui), así que el texto recortado con "…" se puede
        leer completo al pasar el ratón."""
        for lw in (self.pipe_list, self.sleader_list,
                   self.txt_marks_list, self.region_list, self.bz_list,
                   self.curve_list, self.cl_list, self.db_list):
            for r in range(lw.count()):
                it = lw.item(r)
                if it is not None and not it.toolTip():
                    it.setToolTip(it.text())
