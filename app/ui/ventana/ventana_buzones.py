"""Buzones, cajas y sólidos: inserción y panel de propiedades.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class BuzonesMixin:
    # ─────────────────────────── Red 3D: buzones / cotas ───────────────────────────
    def insert_manhole(self):
        """Activa el modo 'clic sobre una línea existente' para insertar un buzón en
        ese punto. El buzón se materializa como un vértice extra en la polilínea (y
        _rebuild_structures lo recoge como buzón nuevo)."""
        if not self.pipes:
            self._info(_tr("No hay líneas dibujadas para insertar un buzón."))
            return
        self.set_mode("insert_bz")
        self._info(_tr("Clic sobre una línea para insertar un buzón (Esc para salir)."))

    def _do_insert_manhole(self, x, y):
        from nucleo.model import network_kind
        thr = 14.0 / max(1e-6, self.canvas.transform().m11())
        best = (None, -1, thr)                      # (pipe_index, seg_index, dist)
        for pi, p in enumerate(self.pipes):
            pts = p.get("pts")
            if not pts or len(pts) < 2: continue    # tramos importados de Excel (world) no editables
            if network_kind(p.get("layer") or "") == "pressure": continue   # presión no lleva buzones
            for idx, a, b in self._segments(pts, False):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < best[2]: best = (pi, idx, d)
        if best[0] is None:
            self._info(_tr("Los buzones/cajas solo se insertan en redes de gravedad o conduit (no en presión)."))
            self.set_mode("idle"); return
        self._push()
        pi, si, _ = best
        self.pipes[pi]["pts"].insert(si + 1, (x, y))
        self._rebuild_structures()
        self._refresh_lists(); self._redraw()
        self._info(_tr("Buzón insertado. Edítalo en la tab Buzones."))
        self.set_mode("idle")

    def _rebuild_structures(self):
        # Detección/reconciliación de buzones (pura) en model_ops; aquí solo se
        # asigna el resultado y se marca el proyecto como modificado.
        self.structures = model_ops.rebuild_structures(self.pipes, self.structures)
        self._dirty = True

    # ── Tab Buzones: selección, panel de propiedades y edición ──────────────
    def _sel_bz(self, row):
        """La selección en la lista de buzones cambió: sincroniza panel + canvas.
        'row' es la fila en bz_list (vista filtrada, curve=False); se traduce al
        índice real en self.structures vía self._bz_rows."""
        if row < 0 or row >= len(self._bz_rows):
            self.sel_bz = -1
        else:
            self.sel_bz = idx = self._bz_rows[row]
            s = self.structures[idx]
            if not s.get("world") and not self._no_center:
                x, y = s.get("x"), s.get("y")
                if x is not None and y is not None:
                    self.canvas.centerOn(float(x), float(y))
        self._sync_bz_panel(); self._update_ui(); self._redraw()

    def _sel_curve(self, row):
        """Igual que _sel_bz pero para curve_list (vista filtrada, curve=True)."""
        if row < 0 or row >= len(self._curve_rows):
            self.sel_curve = -1
        else:
            self.sel_curve = idx = self._curve_rows[row]
            s = self.structures[idx]
            if not s.get("world") and not self._no_center:
                x, y = s.get("x"), s.get("y")
                if x is not None and y is not None:
                    self.canvas.centerOn(float(x), float(y))
        self._sync_curve_panel(); self._update_ui(); self._redraw()

    def _bz_segment_count(self, s):
        # Conteo de extremos de tramo que tocan el buzón (puro) en model_ops.
        return model_ops.bz_segment_count(self.pipes, s)

    def _sync_bz_panel(self):
        """Carga los valores del buzón self.sel_bz en el panel de propiedades."""
        if not hasattr(self, "gprop_bz"): return
        from catalogo import civil_catalog as _cc
        self._bz_prop_guard = True
        try:
            in_tab = self._current_tab() == TAB_BZ
            self.gprop_bz.setVisible(in_tab)
            has_sel = 0 <= self.sel_bz < len(self.structures)
            # Habilitar/deshabilitar todos los controles del groupbox según haya selección
            for w in (self.bz_cod, self.bz_rim, self.bz_sump, self.bz_family, self.bz_size,
                      self.bz_height, self.bz_is_curve, self.chk_bz_hidden,
                      self.sld_len, self.sld_wid, self.sld_h, self.sld_top):
                w.setEnabled(has_sel)
            if not has_sel:
                _bind(self.gprop_bz, "setTitle", "Propiedades del buzón — selecciona uno de la lista")
                self.bz_is_curve.setVisible(True)
                self.bz_is_curve.setChecked(False)
                self.chk_bz_hidden.setChecked(False)
                return
            s = self.structures[self.sel_bz]
            net = s.get("net") or "gravity"
            solid = bool(s.get("solid"))
            _bind(self.gprop_bz, "setTitle", "Propiedades del sólido" if solid
                  else ("Propiedades de la caja" if net == "conduit" else "Propiedades del buzón"))
            for w in (self.bz_family, self._bz_size_box, self.bz_height):
                self._fbz.setRowVisible(w, not solid)
            for w in (self.sld_len, self.sld_wid, self.sld_h, self._sld_top_w, self.lbl_sld_top_src):
                self._fbz.setRowVisible(w, solid)
            if solid:
                self.sld_len.setValue(float(s.get("length_ft") or 0.01))
                self.sld_wid.setValue(float(s.get("width_ft") or 0.01))
                self.sld_h.setValue(float(s.get("solid_height_ft") or 6.56168))
                self._sync_solid_top(s)
            self.bz_cod.setText(s.get("cod", ""))
            self.bz_rim.setValue(float(s.get("rim") or 0.0))
            self.bz_sump.setValue(float(s.get("sump") or 0.0))
            self.bz_height.setValue(float(s.get("height_ft") or 0.0))
            self.bz_net_lbl.setText(_tr("conduit (eléctrico/telecom)") if net == "conduit"
                                    else _tr("presión (agua/gas)") if net == "pressure" else _tr("gravedad"))
            self.bz_origin_lbl.setText("Excel" if s.get("world") else _tr("dibujo"))
            # "Cambiar a elemento curvo" solo tiene sentido en una ESQUINA: un
            # vértice donde se juntan dos tramos (dos tangentes). Un buzón al final
            # de una línea conecta a una sola → no puede ser un codo/curva, así que
            # ahí se oculta la opción.
            self.bz_is_curve.setVisible(self._bz_segment_count(s) >= 2)
            self.bz_is_curve.setChecked(bool(s.get("curve")))
            # Un sólido no puede pasar a elemento curvo, ni un buzón DESACTIVADO (pedido
            # del usuario 2026-10-07: primero hay que activarlo).
            self.bz_is_curve.setEnabled(not solid and not s.get("hidden"))
            self.chk_bz_hidden.setChecked(bool(s.get("hidden")))
            # Familias del catálogo imperial de estructuras (gravedad).
            self.bz_family.blockSignals(True); self.bz_family.clear()
            fams = _cc.imperial_structures(self.civil_year) if self.civil_year else []
            self.bz_family.addItem(_tr("(por defecto)"), "")
            for f in fams:
                idx = self.bz_family.count()
                self.bz_family.addItem(f"{f['pretty']}  [{f['subfolder']}]", f["id"])
                img = f.get("img_path")
                tip = f"<b>{f['pretty']}</b><br><i>{f['subfolder']}</i>"
                if img:
                    tip += f"<br><img src='file:///{img.replace(chr(92), '/')}' width='220'>"
                self.bz_family.setItemData(idx, tip, QtCore.Qt.ToolTipRole)
            cur_fid = s.get("part", "") or ""
            for i in range(self.bz_family.count()):
                if self.bz_family.itemData(i) == cur_fid:
                    self.bz_family.setCurrentIndex(i); break
            self.bz_family.blockSignals(False)
            self._load_bz_sizes(cur_fid, s.get("part_size", "") or "")
        finally:
            self._bz_prop_guard = False

    def _load_bz_sizes(self, fid, current):
        """Repuebla self.bz_size según la familia (siempre catálogo de gravedad)."""
        from catalogo import civil_catalog as _cc
        self.btn_add_bz_size.setEnabled(bool(fid and self.civil_year and self.bz_family.currentData() == fid))
        self.bz_size.blockSignals(True); self.bz_size.clear()
        if not fid or not self.civil_year:
            self.bz_size.addItem(_tr("(sin familia)"), ""); self.bz_size.setEnabled(False)
            self.bz_size.blockSignals(False); return
        sizes = _cc.structure_sizes(self.civil_year, fid)
        if not sizes:
            self.bz_size.addItem(_tr("(sin tamaños detectados)"), ""); self.bz_size.setEnabled(False)
        else:
            self.bz_size.setEnabled(True); self.bz_size.addItem(_tr("(por defecto)"), "")
            for sz in sizes: self.bz_size.addItem(sz, sz)
            if current:
                for i in range(self.bz_size.count()):
                    if self.bz_size.itemData(i) == current:
                        self.bz_size.setCurrentIndex(i); break
        self.bz_size.blockSignals(False)

    def _bz_family_changed(self, _idx):
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        fid = self.bz_family.currentData() or ""
        s["part"] = fid; s["part_size"] = ""      # al cambiar familia se resetea el tamaño
        self._load_bz_sizes(fid, "")
        self._dirty = True
        self._refresh_bz_list_item(self.sel_bz)
        self._redraw()

    def _bz_prop_changed(self):
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        cod_new = self.bz_cod.text().strip()
        if cod_new and cod_new != s.get("cod", ""):
            # Validar unicidad
            if any(o.get("cod") == cod_new for i, o in enumerate(self.structures) if i != self.sel_bz):
                QtWidgets.QMessageBox.warning(self, _tr("Código repetido"),
                    _tr("Ya existe un buzón con código «{cod}». Elige otro.").format(cod=cod_new))
                self._bz_prop_guard = True; self.bz_cod.setText(s.get("cod", "")); self._bz_prop_guard = False
                return
            s["cod"] = cod_new
        s["rim"] = float(self.bz_rim.value()) if self.bz_rim.value() != 0.0 else s.get("rim")
        s["sump"] = float(self.bz_sump.value()) if self.bz_sump.value() != 0.0 else s.get("sump")
        # Si el usuario dejó los spins en 0.0 pero el valor original era 0 o None, respetar 0.
        s["rim"] = float(self.bz_rim.value()); s["sump"] = float(self.bz_sump.value())
        # 0.0 = "(automática)" (sin override) — no se manda al DXF como altura explícita.
        s["height_ft"] = float(self.bz_height.value())
        if self.bz_size.isEnabled():
            s["part_size"] = self.bz_size.currentData() or ""
        self._dirty = True
        self._refresh_bz_list_item(self.sel_bz)
        self._redraw()

    def _solid_prop_changed(self):
        """Largo/ancho/altura del SÓLIDO: rehace su contorno a escala y redibuja."""
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        if not s.get("solid"): return
        from nucleo import model_ops
        px_per_ft = (self.zoom / self.scale) if self.scale else self.zoom
        if (abs(float(s.get("length_ft") or 0) - self.sld_len.value()) > 1e-6
                or abs(float(s.get("width_ft") or 0) - self.sld_wid.value()) > 1e-6):
            self._push()
            model_ops.resize_solid(s, self.sld_len.value(), self.sld_wid.value(), px_per_ft)
        s["solid_height_ft"] = float(self.sld_h.value())
        self._dirty = True
        if s.get("solid_top_z") is None:                  # automática: sigue centrada en la utilidad
            self._bz_prop_guard = True
            try: self._sync_solid_top(s)
            finally: self._bz_prop_guard = False
        self._refresh_bz_list_item(self.sel_bz)
        self._redraw()

    def _solid_default_top(self, s):
        """Cota superior automática: la que deja el EJE de la utilidad unida en su
        vértice justo a media altura del sólido (la mayor si llegan varias), o None
        si es un sólido suelto. La cota de la utilidad es su solera; el plugin sube
        el eje medio alto interior (model_ops.solid_top_centrado)."""
        from nucleo import model_ops
        x, y = s.get("x"), s.get("y")
        if x is None:
            return None
        h = float(s.get("solid_height_ft") or model_ops.SOLID_DEFAULT_H_FT)
        zs = []
        for pi, p in enumerate(self.pipes):
            pts = p.get("pts") or []
            for vi, (vx, vy) in enumerate(pts):
                if abs(vx - x) <= 1.0 and abs(vy - y) <= 1.0 and len(pts) >= 2:
                    seg = vi if vi < len(pts) - 1 else vi - 1
                    z = self._pipe_z_at(pi, seg, vx, vy)
                    if z is not None:
                        zs.append(model_ops.solid_top_centrado(z, model_ops.alto_interior_ft(p), h))
                    break
        return max(zs) if zs else None

    def _solid_top_value(self, s):
        """(cota, es_automática): la del usuario si la fijó; si no, la de la utilidad."""
        if s.get("solid_top_z") is not None:
            return float(s["solid_top_z"]), False
        return self._solid_default_top(s), True

    def _sync_solid_top(self, s):
        z, auto = self._solid_top_value(s)
        self.sld_top.setValue(float(z or 0.0))
        self.btn_sld_top_auto.setEnabled(not auto)
        if auto and z is None:
            self.lbl_sld_top_src.setText(_tr("Sin utilidad unida: se usa la cota de fondo o 0."))
        elif auto:
            self.lbl_sld_top_src.setText(_tr("Automática: la utilidad unida llega al centro del sólido."))
        else:
            self.lbl_sld_top_src.setText(_tr("Fijada por el usuario."))

    def _solid_top_changed(self):
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        if not s.get("solid"): return
        auto = self._solid_default_top(s)
        v = float(self.sld_top.value())
        if s.get("solid_top_z") is None and auto is not None and abs(v - auto) < 1e-6:
            return
        self._push()
        s["solid_top_z"] = v
        self._dirty = True
        self._bz_prop_guard = True
        try: self._sync_solid_top(s)
        finally: self._bz_prop_guard = False

    def _solid_top_reset(self):
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        if s.get("solid_top_z") is None: return
        self._push()
        s["solid_top_z"] = None
        self._dirty = True
        self._bz_prop_guard = True
        try: self._sync_solid_top(s)
        finally: self._bz_prop_guard = False

    def _solid_label(self, s):
        return _tr("{cod}  ·  Sólido {l:g} × {a:g} × {h:g} ft").format(
            cod=s.get("cod", "?"), l=round(float(s.get("length_ft") or 0), 2),
            a=round(float(s.get("width_ft") or 0), 2), h=round(float(s.get("solid_height_ft") or 0), 2))

    def _refresh_bz_list_item(self, idx):
        """idx es un índice de self.structures (no una fila de bz_list): se
        resuelve la fila visible vía self._bz_rows."""
        if not (0 <= idx < len(self.structures)) or idx not in self._bz_rows: return
        s = self.structures[idx]
        fam = s.get("part") or "(sin familia)"
        sz = f"  {s['part_size']}" if s.get("part_size") else ""
        emoji = "🚫" if s.get("hidden") else ("🟠" if s.get("net") == "conduit" else "🔵")
        item = self.bz_list.item(self._bz_rows.index(idx))
        if item and s.get("solid"):
            item.setText(self._solid_label(s))
        elif item:
            item.setText(f"{emoji} {s.get('cod', '?')}  ·  {fam}{sz}")
            if s.get("hidden"):
                item.setForeground(QtGui.QColor(_theme.tokens().text_muted))
            else:
                item.setData(QtCore.Qt.ForegroundRole, None)
            item.setToolTip(_tr("Oculto — no se dibuja ni se crea en Civil3D como buzón real.") if s.get("hidden") else "")

    def _bz_curve_toggled(self, v):
        """Checkbox 'No colocar buzón — es un elemento curvo' en la tab Buzones."""
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        if bool(s.get("curve")) == bool(v): return
        if s.get("solid") and v:
            self._bz_prop_guard = True; self.bz_is_curve.setChecked(False); self._bz_prop_guard = False
            self._info(_tr("Un sólido no se puede cambiar a elemento curvo."))
            return
        if s.get("hidden") and v:
            self._bz_prop_guard = True; self.bz_is_curve.setChecked(False); self._bz_prop_guard = False
            self._info(_tr("El buzón está desactivado: actívalo para cambiarlo a elemento curvo."))
            return
        s["curve"] = bool(v)
        if v: s["part"] = ""; s["part_size"] = ""   # cambia de catálogo (estructura → tubería)
        s["cod"] = ""                               # fuerza a _rebuild_structures a asignar
                                                     # el prefijo correcto (BZ-/CAJA- vs CV-)
        x0, y0 = s.get("x"), s.get("y")
        self._dirty = True
        self._refresh_lists()
        if v:
            # Saltar a la pestaña Curvas y seleccionar el elemento que se acaba de mover
            # (_rebuild_structures reconstruye los dicts; se ubica por coordenada, estable
            # a través del rebuild aunque el código haya cambiado).
            new_idx = next((i for i, x in enumerate(self.structures)
                             if x.get("x") == x0 and x.get("y") == y0), -1)
            if new_idx in self._curve_rows:
                self._no_center = True; self._show_tab(TAB_CURVE)
                self.curve_list.setCurrentRow(self._curve_rows.index(new_idx))
                self._no_center = False
        self._redraw()

    def _bz_hidden_toggled(self, v):
        """Checkbox 'Ocultar buzón' en la tab Buzones: deja de dibujarse en el
        lienzo y de listarse como visible, pero sigue existiendo como dato
        (con hidden=True) para que el DXF exportado marque HIDDEN=1 en ese
        punto — Civil3D lo importa como 'Estructura nula' en vez de omitirlo,
        para no romper la topología de la red."""
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        if bool(s.get("hidden")) == bool(v): return
        s["hidden"] = bool(v); self._dirty = True
        self.bz_is_curve.setEnabled(not s.get("solid") and not s["hidden"])
        self._refresh_lists(); self._redraw()

    # ─────────────────────────── Tab Curvas: selección, panel, edición ─────
    def _pipe_at_vertex(self, x, y, tol=14.0):
        # Búsqueda de tubería por vértice cercano (pura) en model_ops.
        return model_ops.pipe_at_vertex(self.pipes, x, y, tol)
