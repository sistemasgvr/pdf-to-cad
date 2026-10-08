"""Utilidades: bancoducto asignado, familias y tamaños del catálogo, leaders y textos de la lista.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class CatalogoMixin:
    def _duct_bank_for_pipe(self, pipe_idx):
        """Devuelve el DuctBank asignado a esta pipe, o None."""
        for db in getattr(self, "duct_banks", []):
            if pipe_idx in db.assigned():
                return db
        return None

    def _pipe_thumbnail(self, pipe_idx):
        """Miniatura de la utilidad sobre el plano (hover en el diseñador)."""
        from ui.comun.thumbnails import pipe_pixmap
        if not (0 <= pipe_idx < len(self.pipes)):
            return None
        p = self.pipes[pipe_idx]
        # La polilínea DE DIBUJO (con los arcos reales de sus curvas), igual que el lienzo.
        try:
            pts = self._pipe_display_pts(p)
        except Exception:
            pts = p.get("pts")
        return pipe_pixmap(self.canvas.scene(), pts,
                           color=layer_qcolor(p.get("layer", "")).name())

    def _db_pipes_label(self, db):
        """«#3 Eléctrico» (una) o «#3, #5, #7 +2» (varias)."""
        idxs = [i for i in db.assigned() if 0 <= i < len(self.pipes)]
        if not idxs:
            return _tr("(sin asignar)")
        if len(idxs) == 1:
            return f"#{idxs[0] + 1} {self._etq(self.pipes[idxs[0]])}"
        txt = ", ".join(f"#{i + 1}" for i in idxs[:3])
        return txt + (f" +{len(idxs) - 3}" if len(idxs) > 3 else "")

    def _db_preview(self, index):
        """Miniatura + resumen del bancoducto bajo el mouse en la lista."""
        from ui.comun.thumbnails import duct_bank_pixmap
        dbs = getattr(self, "duct_banks", []) or []
        r = index.row()
        if not (0 <= r < len(dbs)):
            return None
        db = dbs[r]
        nm = db.name or _tr("(sin nombre)")
        idxs = [i for i in db.assigned() if 0 <= i < len(self.pipes)]
        if len(idxs) > 1:
            tub = _tr("{n} utilidades").format(n=len(idxs)) + ": " + ", ".join(
                f"#{i + 1}" for i in idxs[:10]) + (" …" if len(idxs) > 10 else "")
        else:
            tub = self._db_pipes_label(db)
        cap = (f"<b>{nm}</b><br>{_tr('Envolvente')}: {db.width_in:g}\" × {db.height_in:g}\""
               f"<br>{_tr('Conductos')}: {len(db.conduits)}<br>{_tr('Tubería')}: {tub}"
               f"<br><i>{_tr('Doble-click para editar.')}</i>")
        return duct_bank_pixmap(db), cap

    def _db_new_for_pipes(self, rows):
        """Crear UN bancoducto asignado a varias utilidades."""
        from nucleo.duct_bank import DuctBank
        seed = DuctBank(name="")
        seed.assign(rows)
        self._open_duct_bank_designer(initial=seed)

    def _db_take_pipes(self, keep, idxs):
        """Quita estas utilidades de los OTROS bancoductos (una utilidad lleva un
        solo bancoducto). Un bancoducto que se queda sin utilidades porque todas
        pasaron a `keep` se elimina — mismo criterio que al rediseñar."""
        idxs = set(idxs)
        out = []
        for d in self.duct_banks:
            if d is not keep:
                prev = d.assigned()
                if prev and set(prev) & idxs:
                    d.assign([i for i in prev if i not in idxs])
                    if not d.assigned():
                        continue
            out.append(d)
        self.duct_banks = out

    def _db_assign_to_pipes(self, db_index, rows):
        """Suma estas utilidades a la asignación del bancoducto `db_index`."""
        dbs = getattr(self, "duct_banks", []) or []
        if not (0 <= db_index < len(dbs)) or not rows:
            return
        self._push()
        db = dbs[db_index]
        db.assign(db.assigned() + list(rows))
        self._db_take_pipes(db, rows)
        self._dirty = True
        try:
            self.sel_db = self.duct_banks.index(db)
        except ValueError:
            self.sel_db = -1
        self._refresh_lists(); self._reselect_pipes(rows)
        self._info(_tr("Bancoducto «{nombre}» asignado a {n} utilidad(es).").format(
            nombre=db.name or _tr("sin nombre"), n=len(rows)))

    def _db_unassign_pipes(self, rows):
        """Estas utilidades dejan de ser bancoducto (el diseño se conserva)."""
        rows = set(rows)
        hit = [d for d in getattr(self, "duct_banks", []) or [] if set(d.assigned()) & rows]
        if not hit:
            return
        self._push()
        for d in hit:
            d.assign([i for i in d.assigned() if i not in rows])
        self._dirty = True
        self._refresh_lists(); self._reselect_pipes(sorted(rows))
        self._info(_tr("Bancoducto quitado de {n} utilidad(es); el diseño queda en la lista.").format(n=len(rows)))

    def _reload_pipe_families(self, p):
        """Repuebla los combos prop_family y prop_size según la capa del pipe y el
        catálogo Civil 3D seleccionado. Si la pipe tiene un duct bank asignado,
        oculta familia/tamaño y muestra el nombre del duct bank."""
        from catalogo import civil_catalog as _cc
        self.prop_family.blockSignals(True); self.prop_family.clear()
        self.prop_size.blockSignals(True); self.prop_size.clear()
        # Duct bank asignado → ocultar familia/tamaño, mostrar label
        db = self._duct_bank_for_pipe(self.sel_pipe)
        if not hasattr(self, "lbl_ductbank_assigned"):
            self.lbl_ductbank_assigned = QtWidgets.QLabel()
            self.lbl_ductbank_assigned.setWordWrap(True)
            # Insertar en el form layout después de prop_size
            fpr = self.gprop.layout()
            fpr.addRow(self.lbl_ductbank_assigned)
        if db is not None:
            self.lbl_prop_family.setVisible(False); self.prop_family.setVisible(False)
            self.lbl_prop_size.setVisible(False); self._prop_size_box.setVisible(False)
            t = _theme.tokens()
            name = db.name or "(sin nombre)"
            nc = len(db.conduits)
            # No pintamos el título en `accent` puro: en dark, ese azul queda
            # ilegible sobre el fondo negro. Usamos negrita en color de texto
            # normal + un fondo tenue del accent (mismo patrón que la fila
            # resaltada en la pestaña Bancoductos).
            bg = QtGui.QColor(t.accent); bg.setAlpha(45)
            bg_css = f"rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()/255:.2f})"
            self.lbl_ductbank_assigned.setText(
                f"<div style='background:{bg_css}; padding:6px 8px; border-radius:4px;'>"
                f"<b style='color:{t.text}'>Duct Bank: {name}</b><br>"
                f"<span style='color:{t.text_muted}'>"
                + _tr("{ancho}\" x {alto}\" — {n} conducto(s)").format(
                    ancho=f"{db.width_in:g}", alto=f"{db.height_in:g}", n=nc)
                + "</span></div>")
            self.lbl_ductbank_assigned.setVisible(True)
            self.prop_family.blockSignals(False); self.prop_size.blockSignals(False)
            return
        self.lbl_ductbank_assigned.setVisible(False)
        kind = self._pipe_net_kind(p)
        show = kind in ("gravity", "pressure", "conduit") and bool(self.civil_year)
        self.lbl_prop_family.setVisible(show); self.prop_family.setVisible(show)
        self.lbl_prop_size.setVisible(show); self._prop_size_box.setVisible(show)
        if not show:
            self.prop_family.blockSignals(False); self.prop_size.blockSignals(False); return
        fams = (_cc.pressure_pipes(self.civil_year) if kind == "pressure"
                else _cc.imperial_pipes(self.civil_year))
        self.prop_family.addItem(_tr("(por defecto)"), "")
        for f in fams:
            idx = self.prop_family.count()
            self.prop_family.addItem(f"{f['pretty']}  [{f['subfolder']}]", f["id"])
            img = f.get("img_path")
            tip = f"<b>{f['pretty']}</b><br><i>{f['subfolder']}</i>"
            if img: tip += f"<br><img src='file:///{img.replace(chr(92), '/')}' width='220'>"
            self.prop_family.setItemData(idx, tip, QtCore.Qt.ToolTipRole)
        cur = p.get("pipe_family", "") or ""
        for i in range(self.prop_family.count()):
            if self.prop_family.itemData(i) == cur:
                self.prop_family.setCurrentIndex(i); break
        self._load_pipe_sizes(kind, cur, p.get("pipe_size", "") or "")
        self.prop_family.blockSignals(False); self.prop_size.blockSignals(False)

    def _diam_txt(self, p):
        """«24"» o «12" (Por defecto)» si la utilidad no tiene tamaño de catálogo."""
        d, defecto = model_ops.diametro(p)
        txt = f'{d:g}"'
        return _tr("{d} (Por defecto)").format(d=txt) if defecto else txt

    def _load_pipe_sizes(self, kind, fid, current):
        from catalogo import civil_catalog as _cc
        # Solo si la familia está en el catálogo de esta versión (la del desplegable).
        self.btn_add_size.setEnabled(bool(fid and self.civil_year and self.prop_family.currentData() == fid))
        self.prop_size.blockSignals(True); self.prop_size.clear()
        if not fid or not self.civil_year:
            self.prop_size.addItem(_tr("(sin familia)"), ""); self.prop_size.setEnabled(False)
            self.prop_size.blockSignals(False); return
        sizes = (_cc.pressure_pipe_sizes(self.civil_year, fid) if kind == "pressure"
                 else _cc.pipe_sizes(self.civil_year, fid))
        if not sizes:
            self.prop_size.addItem(_tr("(sin tamaños)"), ""); self.prop_size.setEnabled(False)
        else:
            self.prop_size.setEnabled(True)
            self.prop_size.addItem(_tr("{d} (Por defecto)").format(
                d=f'{model_ops.DIAM_DEFECTO_IN:g}"'), "")
            for sz in sizes: self.prop_size.addItem(sz, sz)
            if current:
                for i in range(self.prop_size.count()):
                    if self.prop_size.itemData(i) == current:
                        self.prop_size.setCurrentIndex(i); break
        self.prop_size.blockSignals(False)

    def _boton_mas(self, fn):
        """Botón verde «+» (agregar tamaño), grande y con nombre accesible."""
        b = QtWidgets.QToolButton()
        b.setIcon(_icon("mdi:plus", color="#ffffff")); b.setIconSize(QtCore.QSize(20, 20))
        b.setFixedSize(34, 34); b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setStyleSheet("QToolButton{background:#1f8f4a; border:1px solid #17703a; border-radius:6px;}"
                        "QToolButton:hover{background:#26a758;}"
                        "QToolButton:disabled{background:#7d8a82; border-color:#6a756e;}")
        _bind(b, "setToolTip", "Agregar un tamaño nuevo a esta familia (en Civil 3D 2025 en adelante, en español e inglés)")
        _bind(b, "setAccessibleName", "Agregar tamaño")
        b.setEnabled(False)
        b.clicked.connect(fn)
        return b

    @staticmethod
    def _con_boton(combo, boton):
        caja = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(caja); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        h.addWidget(combo, 1); h.addWidget(boton)
        return caja

    def _agregar_tamano(self, cual):
        """«+» junto al tamaño: agrega un tamaño a la familia elegida en el catálogo
        de Civil 3D (catalogo_tamanos_dialog) y lo deja seleccionado."""
        from catalogo import civil_catalog as _cc
        from ui.dialogos import catalogo_tamanos_dialog
        if not self.civil_year:
            return
        if cual == "pipe":
            if not (0 <= self.sel_pipe < len(self.pipes)):
                return
            red = self._pipe_net_kind(self.pipes[self.sel_pipe])
            kind = "pressure" if red == "pressure" else "pipe"
            fid, familia = self.prop_family.currentData() or "", self.prop_family.currentText()
        else:
            if not (0 <= self.sel_bz < len(self.structures)):
                return
            kind, red = "structure", None
            fid, familia = self.bz_family.currentData() or "", self.bz_family.currentText()
        if not fid:
            QtWidgets.QMessageBox.information(self, _tr("Agregar tamaño"), _tr("Elige primero una familia."))
            return
        texto = catalogo_tamanos_dialog.abrir(self, kind, fid, familia.split("  [")[0],
                                              self.civil_year, _cc._current_lang)
        if not texto:
            return
        if cual == "pipe":
            self._load_pipe_sizes(red, fid, texto)
            self._prop_changed()
        else:
            self._load_bz_sizes(fid, texto)
            self._bz_prop_changed()
        self._info(_tr("Tamaño {s} agregado a «{f}».").format(s=texto, f=familia.split("  [")[0]))

    def _pipe_family_changed(self, _idx):
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        fid = self.prop_family.currentData() or ""
        p["pipe_family"] = fid; p["pipe_size"] = ""
        self._load_pipe_sizes(self._pipe_net_kind(p), fid, "")
        self._dirty = True; self._redraw()

    def _leader_at_row(self, lst, r):
        """Índice real en self.leaders del item de la fila r (o -1)."""
        it = lst.item(r) if r is not None and r >= 0 else None
        return it.data(QtCore.Qt.UserRole) if it is not None else -1

    def _sel_sleader(self, r):
        i = self._leader_at_row(self.sleader_list, r); self.sel_leader = i
        if 0 <= i < len(self.leaders):
            ld = self.leaders[i]
            if not self._no_center and ld.get("tp"): self.canvas.centerOn(ld["tp"][0], ld["tp"][1])
        self._update_ui(); self._redraw()

    def _select_leader(self, i, center=False):
        if not (0 <= i < len(self.leaders)): return
        row = next((r for r in range(self.sleader_list.count()) if self.sleader_list.item(r).data(QtCore.Qt.UserRole) == i), -1)
        self._no_center = not center
        self._show_tab(TAB_LEADER); self.sleader_list.setCurrentRow(row)
        self._no_center = False

    def _sel_text(self, r):
        """Al seleccionar un texto libre, abrimos la sección Texto libre del
        acordeón para que el estilo (fuente/altura/negrita/rotación) sea editable."""
        self.sel_text = r
        if 0 <= r < len(self.text_marks):
            tm = self.text_marks[r]
            if not self._no_center: self.canvas.centerOn(tm["pos"][0], tm["pos"][1])
            self._open_section("text")
            self._style_guard = True
            self.font_combo.setCurrentFont(QtGui.QFont(tm.get("font", C.TEXT_FONT)))
            self.size_spin.setValue(tm.get("size_ft", 3.0)); self.chk_bold.setChecked(bool(tm.get("bold")))
            self.rot_spin.setValue(int(tm.get("rot", 0)) % 360); self._style_guard = False
        self._update_ui(); self._redraw()

    def _sel_region(self, r):
        self.sel_region = r
        if not self._no_center and 0 <= r < len(self.erase_regions):
            pts = self.erase_regions[r]["pts"]
            cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts); self.canvas.centerOn(cx, cy)
        self._update_ui(); self._redraw()

    def _region_toggled(self, item):
        r = self.region_list.row(item)
        if 0 <= r < len(self.erase_regions):
            self.erase_regions[r]["enabled"] = (item.checkState() == QtCore.Qt.Checked); self._dirty = True; self._redraw()
