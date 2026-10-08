"""Curvas (arcos reales por vértice) y centerlines.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class CurvasMixin:
    # ───────────────────── arcos reales por vértice curvo ─────────────────────
    def _structure_curve_at(self, x, y, tol_px=14.0):
        """Devuelve la estructura con curve=True MÁS CERCANA al punto dado dentro de
        tolerancia (misma que usa el exportador DXF). Sirve para el hit-test en el
        lienzo y para dibujar el arco real del pipe. La más cercana, no la primera:
        dos codos reconocidos pueden quedar a menos de la tolerancia (DU08 h.26) y
        una curva se dibujaba con el radio y la esquina de la otra."""
        best, bd = None, tol_px * tol_px
        for s in self.structures:
            if not s.get("curve") or s.get("world"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            d = (sx - x) ** 2 + (sy - y) ** 2
            if d <= bd:
                best, bd = s, d
        return best

    def _curve_arc_info(self, s, pipe, cv=None):
        """Geometría del arco real de una curva sobre su pipe. Delega el cálculo
        base (tangencias, centro, discretización, radio efectivo) al helper
        puro `model_ops.fillet_geo` — mismo criterio que el plugin C#. Encima
        añade dos cosas específicas del editor:
          · Resolución del radio: en pies (explícito) o AUTO = 6 × diámetro
            interior de la tubería, y conversión ft → scene px (multiplicar
            por zoom porque los pts están en la escena renderizada).
          · Cap por vecino curvo: 0.48 en cada lado si el vértice vecino
            también es una curva (evita que dos filletes contiguos se
            traguen el tramo intermedio).
        Devuelve un dict con las claves que necesita el dibujo/hit-test del
        lienzo (`p1`, `p2`, `center`, `r_px`, `clamped`, `arc`, `corner`, `vi`).
        None si la curva no aplica (sin pipe, en un extremo, tramo casi
        recto, sin escala, etc.)."""
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None: return None
        pts = (pipe or {}).get("pts") or []
        if len(pts) < 3: return None
        # Vértice DUEÑO de esta estructura curva (el más cercano entre todas las
        # tuberías): así una CV vecina (a < 14 px) no se toma por la de este vértice.
        if cv is None:
            cv = model_ops.curve_vertex_indices(pipe, self.structures, self.pipes)
        vi = next((i for i, o in cv.items() if o is s), None)
        if vi is None or vi <= 0 or vi >= len(pts) - 1:
            return None
        # La esquina es el VÉRTICE de la tubería (la estructura CV está sobre él; si
        # quedó un poco corrida, el arco igual sale de la polilínea real).
        sx, sy = pts[vi]
        if not self.scale or self.scale <= 1e-6: return None
        # Radio en pies: explícito o auto = 6 × diámetro interior.
        r_ft = float(s.get("radius_ft") or 0.0)
        if r_ft <= 0.01:
            r_ft = model_ops.radio_auto_ft(pipe)
        # Conversión ft → scene px: los pts se renderizan a self.zoom × puntos
        # PDF, y self.scale es ft por punto PDF. → scene_px = ft × zoom / scale.
        r_px = r_ft * float(self.zoom) / self.scale
        if r_px <= 0: return None
        # Cap por vecino curvo — mismo criterio del plugin.
        px_prev, py_prev = pts[vi - 1]
        px_next, py_next = pts[vi + 1]
        cap_prev = model_ops.FILLET_CAP_CURVA if (vi - 1) in cv else model_ops.FILLET_CAP_RECTA
        cap_next = model_ops.FILLET_CAP_CURVA if (vi + 1) in cv else model_ops.FILLET_CAP_RECTA
        # Tope POR LADO, igual que el plugin y que _curve_max_radius_ft.
        geo = model_ops.fillet_geo((px_prev, py_prev), (sx, sy), (px_next, py_next),
                                    r_px, max_frac=cap_prev, max_frac_next=cap_next,
                                    tol_r=model_ops.FILLET_TOL_RADIO_FT * float(self.zoom) / self.scale)
        if geo is None: return None
        # Enriquecemos el dict con las claves que usa el resto del editor
        # (p1/p2 = t1/t2 de fillet_geo; corner y vi para el marcador y el pipe).
        geo["p1"] = geo["t1"]; geo["p2"] = geo["t2"]
        geo["r_px"] = geo["r"]
        geo["corner"] = (sx, sy)
        geo["vi"] = vi
        return geo

    def _arc_polyline(self, info, n_per_90=24):
        """Puntos del arco (scene px) para dibujarlo y hacer hit-test. Reutiliza
        directamente el `arc` que devolvió model_ops.fillet_geo — así el visual
        y el pick del click son idénticos y coherentes con el pipe."""
        return list(info.get("arc") or [])

    def _pipe_display_pts(self, pipe):
        """Devuelve la polilínea DE DIBUJO del pipe: los tramos rectos entre
        vértices normales quedan igual; cada vértice con curva se REEMPLAZA por
        la polilínea del arco real (misma geometría que el plugin dibuja en C3D).
        Así el usuario ve el radio real sobre el lienzo."""
        pts = (pipe or {}).get("pts") or []
        n = len(pts)
        if n < 2: return list(pts)
        cv = model_ops.curve_vertex_indices(pipe, self.structures, self.pipes) if n >= 3 else {}
        out = [pts[0]]
        for j in range(1, n):
            if 0 < j < n - 1:
                s = cv.get(j)
                info = self._curve_arc_info(s, pipe, cv) if s is not None else None
                if info is not None:
                    out.extend(self._arc_polyline(info, n_per_90=24))
                    continue
            out.append(pts[j])
        return out

    def _sync_curve_panel(self):
        """Carga los valores del elemento curvo self.sel_curve en el panel de propiedades."""
        if not hasattr(self, "gprop_curve"): return
        self._curve_prop_guard = True
        try:
            in_tab = self._current_tab() == TAB_CURVE
            self.gprop_curve.setVisible(in_tab)
            has_sel = 0 <= self.sel_curve < len(self.structures)
            for w in (self.cv_cod, self.cv_radius, self.curve_is_bz):
                w.setEnabled(has_sel)
            if not has_sel:
                _bind(self.gprop_curve, "setTitle", "Propiedades del elemento curvo — selecciona uno de la lista")
                self.cv_family_lbl.setText("—"); self.cv_size_lbl.setText("—")
                return
            s = self.structures[self.sel_curve]
            net = s.get("net") or "gravity"
            _bind(self.gprop_curve, "setTitle", "Propiedades del elemento curvo")
            self.cv_cod.setText(s.get("cod", ""))
            # Calcular y aplicar el radio máximo geométrico ANTES de setValue.
            # Si no lo aplicamos, el usuario puede escribir p.ej. 100ft y el
            # plugin lo recortará silenciosamente (con warning en consola,
            # pero fuera de vista). Con el límite en la UI, se ve al instante.
            r_max = self._curve_max_radius_ft(self.sel_curve)
            self._cv_radius_max_ft = r_max
            valor_guardado = float(s.get("radius_ft") or 0.0)
            if r_max is not None and r_max > 0.01:
                # Redondeo HACIA ARRIBA a los 2 decimales del campo: con round() un
                # radio que calza justo en el tramo (tangencia sobre el vértice
                # vecino, típico del reconocimiento) se recortaba 0.01 ft. El exceso
                # (< 0.01 ft) lo absorben el plugin y el dibujo (FILLET_TOL_RADIO_FT).
                import math as _m
                r_max = _m.ceil(r_max * 100.0 - 1e-6) / 100.0
                self._cv_radius_max_ft = r_max
                self.cv_radius.setMaximum(r_max)
                _bind(self.cv_radius, "setToolTip",
                      "Radio deseado de la tubería curva, en pies. Vacío (0) = automático.\n"
                      "Máximo permitido por la geometría (tramos rectos adyacentes): {r} ft.",
                      fmt={"r": f"{r_max:.2f}"})
                # Si el valor guardado excedía el nuevo máximo, sale aviso rojo
                # (además del clamp automático que el spinbox aplica al setValue).
                if valor_guardado > r_max + 1e-3:
                    self.cv_radius_warn.setText(_tr(
                        "⚠ Máximo permitido: {r} ft (limitado por los tramos rectos "
                        "adyacentes). El valor guardado ({v} ft) se ajustó.").format(
                            r=f"{r_max:.2f}", v=f"{valor_guardado:.2f}"))
                    self.cv_radius_warn.setVisible(True)
                else:
                    self.cv_radius_warn.setText(
                        _tr("Máximo permitido: {r} ft.").format(r=f"{r_max:.2f}"))
                    self.cv_radius_warn.setVisible(True)
            else:
                self.cv_radius.setMaximum(10000.0)
                _bind(self.cv_radius, "setToolTip",
                      "Radio deseado de la tubería curva, en pies. Vacío (0) = automático:\n"
                      "al importar en Civil3D se usa 6× el ancho/diámetro interior de la tubería.")
                self.cv_radius_warn.setVisible(False)
                self.cv_radius_warn.setText("")
            self.cv_radius.setValue(valor_guardado)
            self.cv_net_lbl.setText(_tr("conduit (eléctrico/telecom)") if net == "conduit" else _tr("gravedad"))
            self.cv_origin_lbl.setText("Excel" if s.get("world") else
                                       _tr("quiebre del plano (radio mínimo)") if s.get("quiebre")
                                       else _tr("dibujo"))
            # Familia/tamaño heredados de la tubería recta que pasa por este vértice
            # (solo lectura: garantiza que la curva calce con los tramos rectos).
            x, y = s.get("x"), s.get("y")
            p = self._pipe_at_vertex(x, y) if x is not None and y is not None else None
            if p is not None and p.get("pipe_family"):
                from catalogo import civil_catalog as _cc
                fid = p["pipe_family"]
                pretty = fid
                try:
                    if self.civil_year:
                        pretty = _cc.family_description(self.civil_year, fid, "pipe") or fid
                except Exception: pass
                self.cv_family_lbl.setText(pretty)
                self.cv_size_lbl.setText(p.get("pipe_size") or self._diam_txt(p))
            else:
                self.cv_family_lbl.setText(_tr("(sin tubería detectada)"))
                self.cv_size_lbl.setText("—")
        finally:
            self._curve_prop_guard = False

    def _curve_prop_changed(self):
        if self._curve_prop_guard: return
        if not (0 <= self.sel_curve < len(self.structures)): return
        s = self.structures[self.sel_curve]
        cod_new = self.cv_cod.text().strip()
        if cod_new and cod_new != s.get("cod", ""):
            if any(o.get("cod") == cod_new for i, o in enumerate(self.structures) if i != self.sel_curve):
                QtWidgets.QMessageBox.warning(self, _tr("Código repetido"),
                    _tr("Ya existe un elemento con código «{cod}». Elige otro.").format(cod=cod_new))
                self._curve_prop_guard = True; self.cv_cod.setText(s.get("cod", "")); self._curve_prop_guard = False
                return
            s["cod"] = cod_new
        val_actual = float(self.cv_radius.value())
        s["radius_ft"] = val_actual
        # Si el usuario está topando contra el máximo geométrico, resalta el
        # aviso en rojo intenso para que sepa que el spinbox no lo dejó subir más.
        r_max = getattr(self, "_cv_radius_max_ft", None)
        if r_max is not None and r_max > 0.01:
            if val_actual >= r_max - 1e-3 and val_actual > 0:
                self.cv_radius_warn.setText(_tr(
                    "⚠ Alcanzaste el máximo permitido: {r} ft. No se puede subir más porque "
                    "los tramos rectos adyacentes no dan espacio para una tangente mayor.").format(
                        r=f"{r_max:.2f}"))
                self.cv_radius_warn.setStyleSheet("color:#d33; font-weight:bold; font-size:14px;")
            else:
                self.cv_radius_warn.setText(_tr("Máximo permitido: {r} ft.").format(r=f"{r_max:.2f}"))
                self.cv_radius_warn.setStyleSheet("color:#d33; font-size:14px;")
            self.cv_radius_warn.setVisible(True)
        self._dirty = True
        self._refresh_curve_list_item(self.sel_curve)
        self._redraw()

    def _refresh_curve_list_item(self, idx):
        if not (0 <= idx < len(self.structures)) or idx not in self._curve_rows: return
        s = self.structures[idx]
        x, y = s.get("x"), s.get("y")
        p = self._pipe_at_vertex(x, y) if x is not None and y is not None else None
        fam = (p.get("pipe_family") if p else "") or "(sin familia)"
        sz = f"  {p['pipe_size']}" if p and p.get("pipe_size") else ""
        item = self.curve_list.item(self._curve_rows.index(idx))
        if item:
            item.setText(f"{s.get('cod', '?')}  ·  {fam}{sz}")
            item.setIcon(_icon("mdi:vector-curve", color="#a855f7"))

    def _curve_is_bz_toggled(self, _checked=False):
        """Botón 'Volver a tratar como buzón/caja' en la tab Curvas — acción de
        un solo clic (no un estado persistente: el elemento sale de esta lista
        en cuanto se convierte, así que no tiene sentido que quede 'marcado')."""
        if self._curve_prop_guard: return
        if not (0 <= self.sel_curve < len(self.structures)): return
        s = self.structures[self.sel_curve]
        s["curve"] = False; s["part"] = ""; s["part_size"] = ""
        s.pop("quiebre", None)                      # ya no es la curva de un quiebre del plano
        s["cod"] = ""                               # fuerza a asignar prefijo BZ-/CAJA-
        x0, y0 = s.get("x"), s.get("y")
        self._dirty = True
        self._refresh_lists()
        new_idx = next((i for i, x in enumerate(self.structures)
                         if x.get("x") == x0 and x.get("y") == y0), -1)
        if new_idx in self._bz_rows:
            self._no_center = True; self._show_tab(TAB_BZ)
            self.bz_list.setCurrentRow(self._bz_rows.index(new_idx))
            self._no_center = False
        self._redraw()

    # ─────────────────────────── Tab Centerlines: selección, panel, edición ─
    def _sel_cl(self, row):
        """self.ref_centerlines no se filtra (a diferencia de bz_list/curve_list,
        que muestran una vista filtrada de self.structures): cl_list es 1:1 con
        la lista, no hace falta traducir fila↔índice."""
        self.sel_cl = row
        if 0 <= row < len(self.ref_centerlines) and not self._no_center:
            pts = self.ref_centerlines[row].get("pts") or []
            if pts:
                mid = pts[len(pts) // 2]; self.canvas.centerOn(mid[0], mid[1])
        self._sync_cl_panel(); self._update_ui(); self._redraw()

    def _sync_cl_panel(self):
        """Carga los valores del centerline self.sel_cl en el panel de propiedades."""
        if not hasattr(self, "gprop_cl"): return
        self._cl_prop_guard = True
        try:
            in_tab = self._current_tab() == TAB_CL
            self.gprop_cl.setVisible(in_tab)
            has_sel = 0 <= self.sel_cl < len(self.ref_centerlines)
            self.cl_cod.setEnabled(has_sel)
            if not has_sel:
                _bind(self.gprop_cl, "setTitle", "Propiedades del centerline — selecciona uno de la lista")
                self.cl_len_lbl.setText("—")
                return
            c = self.ref_centerlines[self.sel_cl]
            _bind(self.gprop_cl, "setTitle", "Propiedades del centerline")
            self.cl_cod.setText(c.get("cod", ""))
            # Longitud real (respeta georreferencia activa vía _to_cad, igual que
            # el resto de la app — no una escala fija).
            real = [self._to_cad(x, y) for (x, y) in (c.get("pts") or [])]
            length_ft = sum(math.hypot(real[i + 1][0] - real[i][0], real[i + 1][1] - real[i][1])
                            for i in range(len(real) - 1))
            self.cl_len_lbl.setText(f"{length_ft:.1f}")
        finally:
            self._cl_prop_guard = False

    def _cl_prop_changed(self):
        if self._cl_prop_guard: return
        if not (0 <= self.sel_cl < len(self.ref_centerlines)): return
        c = self.ref_centerlines[self.sel_cl]
        cod_new = self.cl_cod.text().strip()
        if cod_new and cod_new != c.get("cod", ""):
            if any(o.get("cod") == cod_new for i, o in enumerate(self.ref_centerlines) if i != self.sel_cl):
                QtWidgets.QMessageBox.warning(self, _tr("Código repetido"),
                    _tr("Ya existe un centerline con código «{cod}». Elige otro.").format(cod=cod_new))
                self._cl_prop_guard = True; self.cl_cod.setText(c.get("cod", "")); self._cl_prop_guard = False
                return
            c["cod"] = cod_new
        self._dirty = True
        self._refresh_cl_list_item(self.sel_cl)

    def _refresh_cl_list_item(self, idx):
        if not (0 <= idx < len(self.ref_centerlines)): return
        c = self.ref_centerlines[idx]
        item = self.cl_list.item(idx)
        if item:
            item.setText(_tr("{cod}  ·  {n} vértices").format(cod=c.get('cod', '?'), n=len(c.get('pts') or [])))
            item.setIcon(_icon("mdi:vector-line", color="#22c55e"))
