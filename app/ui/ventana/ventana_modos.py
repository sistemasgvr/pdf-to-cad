"""Estado de la ventana: modos de dibujo, pestañas, zoom, escala, coordenadas y avisos.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class ModosMixin:
    # ─────────────────────────── Estado / modos ───────────────────────────
    def _on_enter(self):
        if self.mode == "pipe": self.finish_pipe()
        elif self.mode == "erase": self.finish_erase()
        elif self.mode == "centerline": self.finish_centerline()
        elif self.mode in ("leader1", "leader2", "leader3"):
            self.set_mode("idle"); self._info(_tr("Comando Leader finalizado (Enter)"))
        elif self.mode == "move":
            self.set_mode("idle"); self._info(_tr("Edición terminada (Enter)"))

    def _on_escape(self):
        if self.mode == "pipe" and self.cur_pts:
            self._push(); self.cur_pts = []; self._extending = False; self._ext_pipe = None; self._ext_at = None
            self._update_ui(); self._redraw(); self._info(_tr("Puntos cancelados"))
        elif self.mode == "erase" and self._erase_pts:
            self._erase_pts = []; self._redraw(); self._info(_tr("Zona cancelada"))
        elif self.mode == "centerline" and self._cl_pts:
            self._push(); self._cl_pts = []; self._update_ui(); self._redraw(); self._info(_tr("Puntos cancelados"))
        elif self.mode == "insert_bz":
            self.set_mode("idle"); self._info(_tr("Inserción de buzón cancelada"))
        elif self.sel_pipe >= 0 or self.sel_leader >= 0 or self.sel_region >= 0 or self.sel_text >= 0 or self.sel_bz >= 0 or self.sel_curve >= 0 or self.sel_cl >= 0:
            self._deselect_all(); self._info(_tr("Selección quitada"))
        else:
            self.set_mode("idle"); self._info(_tr("Salió del modo"))

    def _deselect_all(self):
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = self.sel_bz = self.sel_curve = self.sel_cl = self.sel_db = -1
        for lst in (self.pipe_list, self.sleader_list, self.txt_marks_list, self.region_list,
                    getattr(self, "bz_list", None), getattr(self, "curve_list", None), getattr(self, "cl_list", None)):
            if lst is None: continue
            lst.blockSignals(True); lst.setCurrentRow(-1); lst.clearSelection(); lst.blockSignals(False)
        if self.mode == "move": self.set_mode("idle")
        self._update_ui(); self._redraw()

    def _info(self, m): self.lbl_info.setText(m)

    def _zoom_in(self): self.canvas.apply_zoom(1.25)
    def _zoom_out(self): self.canvas.apply_zoom(0.8)

    def _update_title(self):
        dirty = "* " if self._dirty else ""
        if self.project_path:
            name = os.path.splitext(os.path.basename(self.project_path))[0]
            self.setWindowTitle(f"{dirty}{self._base_title} — {name}")
        else:
            self.setWindowTitle(f"{dirty}{self._base_title}")

    def _refresh_scale_label(self):
        """Actualiza el botón de escala con el valor actual (1"=X ft).

        El icono de lápiz sirve para señalar que es EDITABLE — un botón flat
        sin hover se ve idéntico a un QLabel y no invita al clic. Es la misma
        señal visual que ya se usa en el botón de edición por tramo.
        """
        try:
            v = float(self.scale) * 72.0
        except Exception:
            v = 0.0
        # El icono de lápiz está seteado por _apply_theme_custom_styles (una sola
        # vez); aquí solo actualizamos el texto con el valor de escala actual.
        if v > 0:
            _bind(self.btn_scale, "setText", "Escala 1\"={v}'", fmt={"v": f"{v:.0f}"})
        else:
            _bind(self.btn_scale, "setText", "Escala —")

    def _prompt_scale(self):
        """Diálogo compacto para cambiar la escala del plano (1\"=X ft).

        La escala interna es en ft por punto PDF (72 pt = 1 in), así que un
        valor de 20 significa "1 pulgada = 20 pies" — la misma notación que
        usan los planos del titleblock. Se acepta un decimal por si acaso.
        """
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Escala"), _tr("Primero abre un PDF o proyecto.")); return
        cur = float(self.scale) * 72.0 if self.scale else 20.0
        val, ok = QtWidgets.QInputDialog.getDouble(
            self, _tr("Escala del plano"),
            _tr("1 pulgada del PDF equivale a X pies reales:"),
            cur, 0.01, 100000.0, 2)
        if not ok or val <= 0:
            return
        self._push()
        self.scale = val / 72.0
        self.leader_hpx = max(14.0, min(
            LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
        self._refresh_scale_label()
        self._update_geo_status()
        self._redraw()
        self._info(_tr("Escala cambiada a 1\"={v}'.").format(v=f"{val:g}"))

    def _open_opacity_popup(self):
        """Desplegable junto al botón de escala: deslizable de opacidad del PDF y
        botón para alternar el fondo detrás del PDF entre blanco y negro. El
        mismo desplegable lo usan «Capas de la hoja» y la vista previa
        (`wizard_widgets.show_opacity_popup`)."""
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Opacidad"), _tr("Primero abre un PDF o proyecto.")); return
        from ui.asistente.wizard_widgets import show_opacity_popup

        def _is_black():
            return self.canvas.pdf_bg_color.value() < 128

        def _toggle_bg():
            self.canvas.set_pdf_bg(QtGui.QColor(255, 255, 255) if _is_black()
                                   else QtGui.QColor(0, 0, 0))
            # Redibujar para que las zonas borradas adopten el color del fondo
            # (solo visual — nada cambia en el modelo).
            self._redraw()

        show_opacity_popup(self.btn_opacity, self.canvas.pdf_opacity, self.canvas.set_pdf_opacity,
                           _is_black, _toggle_bg, above=True,
                           # mantiene sincronizado el control del dock
                           on_value_text=lambda v: self.lbl_opacity.setText(f"{v}%"))

    def _update_coords(self, x, y):
        if self.canvas.pixmap_item is None: return
        cx, cy = self._to_cad(x, y)
        # Mostrar SIEMPRE X,Y,Z (X=Este, Y=Norte, Z=0 mientras el lienzo sea 2D).
        # Antes se mostraba N,E (Northing/Easting) al estar georreferenciado — se
        # cambió porque el usuario prefiere el orden X,Y,Z uniforme; el sistema de
        # referencia sigue siendo EPSG:2229 cuando la georref está activa.
        if self.georef.active():
            # Etiqueta del sistema: si el usuario fijó un código de Huso (CS-MAP,
            # ej. "CA83VF") se muestra ese; si no, el EPSG interno. Son el mismo
            # sistema (CA83VF = EPSG:2229): solo cambia el NOMBRE mostrado, no los
            # valores — la georreferenciación siempre produce coords en ese sistema.
            cs = (getattr(self.georef, "cs_code", "") or "").strip()
            etq = cs if cs else f"EPSG:{self.georef.epsg}"
            self.lbl_coords.setText(
                f"X {cx:,.4f}  Y {cy:,.4f}  Z 0.0000  ({etq})")
        else:
            self.lbl_coords.setText(f"X {cx:,.4f}  Y {cy:,.4f}  Z 0.0000")
        sc = self.canvas.scene(); r = sc.sceneRect()
        # `scene().clear()` (abrir proyecto, cambiar de hoja, re-render del plano)
        # destruye estas líneas pero la lista las sigue apuntando: sin tolerar el
        # puntero colgante, CADA movimiento del mouse fallaba aquí y ya no se
        # dibujaba el marcador verde del snap (el snap del clic sí funcionaba).
        for it in getattr(self, "_crosshair", []):
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._crosshair = []
        cp = QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 0); cp.setCosmetic(True)
        h = sc.addLine(r.left(), y, r.right(), y, cp); h.setZValue(Z_MARK + 10)
        v = sc.addLine(x, r.top(), x, r.bottom(), cp); v.setZValue(Z_MARK + 10)
        self._crosshair = [h, v]
        self._update_hover_tooltip(x, y)
        self._update_pipe_snap_hint(x, y)

    def _update_pipe_snap_hint(self, x, y):
        """Feedback visual del snap suave a utilidades: al mover el mouse en
        modo Dibujar, si el cursor está cerca de una utilidad existente del
        MISMO tipo (capa), marca en verde el punto exacto donde se pegaría el
        click. La forma del marcador dice a QUÉ se engancha:

          ○ círculo  = extremo de la utilidad (al hacer click ahí, la app
                       pregunta si quieres unirla o crear una nueva)
          □ cuadrado = vértice intermedio
          △ triángulo= punto cualquiera del tramo (proyección perpendicular)
          ◇ rombo    = contorno (borde o esquina) de un SÓLIDO

        También al arrastrar el extremo de una utilidad en modo Mover.

        Todo el cuerpo va en try/except: si algo falla aquí (un item de escena
        ya destruido, por ejemplo) NO puede tumbar el movimiento del mouse ni
        dejar al usuario sin saber si el snap está activo."""
        sc = self.canvas.scene()
        # Soltar el marcador anterior. `scene().clear()` (cambio de página,
        # abrir/cerrar proyecto) destruye el item de C++ pero deja este
        # atributo apuntando a él: hay que tolerar el puntero colgante.
        prev = getattr(self, "_pipe_snap_hint", None)
        if prev is not None:
            try: sc.removeItem(prev)
            except (RuntimeError, ValueError): pass
            self._pipe_snap_hint = None
        arrastre = self._endpoint_drag() if self.mode == "move" else None
        if self.mode != "pipe" and arrastre is None:
            self._set_snap_status(None)
            return
        try:
            hit = self._drag_snap(x, y)[2] if arrastre else self._pipe_soft_snap(x, y)
        except Exception:
            self._set_snap_status(None)
            return
        if hit is None:
            self._set_snap_status(None)
            return

        sx, sy = hit["pt"]
        kind = hit.get("kind")
        R = 7.0
        verde = QtGui.QColor(30, 200, 60)
        pen = QtGui.QPen(verde, 2.0); pen.setCosmetic(True)
        relleno = QtGui.QColor(30, 200, 60, 60)
        try:
            if kind == "endpoint":
                it = sc.addEllipse(-R, -R, R * 2, R * 2, pen, QtGui.QBrush(relleno))
            elif kind == "vertex":
                it = sc.addRect(-R, -R, R * 2, R * 2, pen, QtGui.QBrush(relleno))
            elif kind == "solid":                   # rombo: contorno de un sólido
                rombo = QtGui.QPolygonF([QtCore.QPointF(0, -R), QtCore.QPointF(R, 0),
                                         QtCore.QPointF(0, R), QtCore.QPointF(-R, 0)])
                it = sc.addPolygon(rombo, pen, QtGui.QBrush(relleno))
            else:                                   # segmento
                tri = QtGui.QPolygonF([QtCore.QPointF(0, -R),
                                       QtCore.QPointF(R, R * 0.7),
                                       QtCore.QPointF(-R, R * 0.7)])
                it = sc.addPolygon(tri, pen, QtGui.QBrush(relleno))
            it.setPos(sx, sy)
            it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            it.setZValue(Z_MARK + 20)
            self._pipe_snap_hint = it
        except Exception:
            self._pipe_snap_hint = None
        self._set_snap_status(hit)

    def _set_snap_status(self, hit):
        """Texto en la barra de estado sobre el snap. Sin esto el marcador
        verde es la única pista, y si el usuario no lo ve (zoom bajo, pantalla
        pequeña) no sabe si el click se va a pegar o no."""
        lbl = getattr(self, "lbl_snap", None)
        if lbl is None: return
        if not hit:
            lbl.setText("")
            return
        if hit.get("kind") == "solid":
            k = hit.get("port")
            st = self.structures[k] if isinstance(k, int) and 0 <= k < len(self.structures) else {}
            lbl.setText(_tr("⊙ Snap al sólido «{c}»").format(c=st.get("cod", "")))
            return
        ex = self._endpoint_drag() if self.mode == "move" else None
        capa = self.pipes[ex[0]].get("layer", "") if ex else self.active_layer()
        nombre = {"endpoint": _tr("extremo"),
                  "vertex": _tr("vértice"),
                  "segment": _tr("tramo")}.get(hit.get("kind"), "")
        lbl.setText(_tr("⊙ Snap a {q} de «{c}»").format(q=nombre, c=capa))

    def _update_hover_tooltip(self, x, y):
        thr = self.snap_r * 1.5
        for i, p in enumerate(self.pipes):
            pts = p.get("pts", [])
            for j in range(len(pts) - 1):
                ax, ay = pts[j]; bx, by = pts[j + 1]
                dx, dy = bx - ax, by - ay
                ln2 = dx * dx + dy * dy
                if ln2 == 0:
                    continue
                t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / ln2))
                px, py = ax + t * dx, ay + t * dy
                if (x - px) ** 2 + (y - py) ** 2 < thr ** 2:
                    d = self._diam_txt(p)
                    tag = " (AB)" if p.get("ab") else ""
                    tip = _tr("#{n} {capa}{tag} — {d} · {v} vértices").format(
                        n=i + 1, capa=self._etq(p), tag=tag, d=d, v=len(pts))
                    self.canvas.setToolTip(tip)
                    return
        self.canvas.setToolTip("")

    def _update_geo_status(self):
        if self.georef.active():
            unit = georef_mod.epsg_unit(self.georef.epsg)
            rms = f" · RMS {self.georef.rms:.2f} {unit}" if self.georef.rms is not None else ""
            cs = (getattr(self.georef, "cs_code", "") or "").strip()
            etq = cs if cs else f"EPSG:{self.georef.epsg}"
            _bind(self.lbl_geo, "setText", "Georref: {sistema}{rms}", fmt={"sistema": etq, "rms": rms})
            self.lbl_geo.setStyleSheet(f"color:{_theme.tokens().success};")
        else:
            _bind(self.lbl_geo, "setText", "Georref: no (escala titleblock)")
            self.lbl_geo.setStyleSheet(f"color:{_theme.tokens().danger};")

    def _update_ui(self):
        m = self.mode
        def st(btn, on): btn.setStyleSheet(btn_on_style() if on else btn_off_style())
        in_leader = m in ("leader1", "leader2", "leader3")
        st(self.btn_pipe, m == "pipe")
        st(self.btn_leader_simple, in_leader)
        st(self.btn_text, m == "text"); st(self.btn_erase, m == "erase")
        st(self.btn_centerline, m == "centerline")
        # Textos + iconos alternan según el estado (dibujando / detenido).
        # Icono "stop-circle" cuando la herramienta está activa (para invitar a
        # terminar), y el icono nativo de la utilidad cuando está inactiva.
        _white = _theme.tokens().text_on_accent
        def _toggle(btn, active, act_txt, idle_txt, idle_icon):
            btn.setText(act_txt if active else idle_txt)
            btn.setIcon(_icon("mdi:stop-circle-outline" if active else idle_icon, color=_white))
        _toggle(self.btn_pipe, m == "pipe",
                "  " + _tr("Salir de dibujar utilidad"), "  " + _tr("Dibujar utilidad"), "mdi:pencil-outline")
        _toggle(self.btn_leader_simple, in_leader,
                "  " + _tr("Coloque Leader…"), "  " + _tr("Colocar Leader"), "mdi:arrow-decision-outline")
        _toggle(self.btn_erase, m == "erase",
                "  " + _tr("Terminar zona (Enter)"), "  " + _tr("Borrar zona (polígono)"), "mdi:vector-rectangle")
        _toggle(self.btn_centerline, m == "centerline",
                "  " + _tr("Terminar centerline (Enter)"), "  " + _tr("Trazar centerline"), "mdi:ruler")
        ti = self._current_tab()
        _bind(self.gtxt, "setTitle", "Estilo de texto")
        self.gprop.setVisible(ti == TAB_PIPE and self.sel_pipe >= 0)
        # Panel de propiedades del buzón: visible en tab Buzones (aunque sin selección
        # se muestra el groupbox con campos deshabilitados para que el user vea que existe).
        if hasattr(self, "gprop_bz"):
            self.gprop_bz.setVisible(ti == TAB_BZ)
        if hasattr(self, "gprop_curve"):
            self.gprop_curve.setVisible(ti == TAB_CURVE)
        if hasattr(self, "gprop_cl"):
            self.gprop_cl.setVisible(ti == TAB_CL)
        if hasattr(self, "chk_bz_labels"):
            self.chk_bz_labels.setVisible(ti in (TAB_BZ, TAB_CURVE))
        # "En curso": solo mientras hay puntos en curso. gcur ya fue movido a la
        # sección correcta por set_mode; aquí solo habilitamos Finalizar y mostramos.
        active_draw = ((m == "pipe" and len(self.cur_pts) >= 1) or (m == "erase" and len(self._erase_pts) >= 1)
                       or (m == "centerline" and len(self._cl_pts) >= 1))
        self.gcur.setVisible(active_draw)
        self.btn_fin.setEnabled((m == "pipe" and len(self.cur_pts) >= 2) or (m == "erase" and len(self._erase_pts) >= 3)
                                or (m == "centerline" and len(self._cl_pts) >= 2))
        ti = self._current_tab()
        self.btn_ct.setVisible(ti == TAB_PIPE)
        self.btn_mv.setVisible(ti in (TAB_PIPE, TAB_LEADER, TAB_TEXT, TAB_REGION))
        _bind(self.btn_mv, "setText", "Mover" if ti == TAB_TEXT else "Editar/mover")
        self.btn_edit.setVisible(ti == TAB_TEXT)
        # "Eliminar" no aplica en la pestaña Buzones: los buzones se
        # auto-detectan de los vertices de las tuberias, borrarlos no tiene
        # efecto porque _rebuild_structures los repone. Se oculta el boton.
        self.btn_del.setVisible(ti != TAB_BZ)
        self.btn_xd.setVisible(ti in (TAB_PIPE, TAB_BZ))
        diag = self.orient_combo.currentData() == "d"
        lead_cuerpo = N_("Modo: Leader — clic en el final del cuerpo")
        clave_modo = {
            "idle": N_("Modo: inactivo  ·  clic en el dibujo para seleccionar"),
            "pipe": (N_("Modo: EXTENDIENDO desde el vértice — clic agrega puntos, Enter finaliza")
                     if self._extending else N_("Modo: dibujar utilidad  ·  Enter finaliza")),
            "leader1": N_("Modo: Leader — clic en la cabeza de flecha (dónde señala)"),
            "leader2": (N_("Modo: Leader — clic en el inicio del landing (bisagra)") if diag
                        else lead_cuerpo),
            "leader3": lead_cuerpo,
            "text": N_("Modo: texto libre — clic donde escribir · Enter aplica"),
            "erase": N_("Modo: borrar zona — clic para el polígono, Enter cierra"),
            "centerline": N_("Modo: trazar centerline — clic agrega puntos, Enter finaliza"),
            "move": N_("Modo: editar — arrastra vértice · clic en tramo inserta · clic-en-vértice extiende (F) · clic derecho elimina"),
        }.get(m)
        if clave_modo:
            _bind(self.lbl_mode, "setText", clave_modo)
        else:
            self.lbl_mode.setText("")
        # Actualiza el panel "Mover con precisión" (habilita/deshabilita según la selección).
        if hasattr(self, "_update_move_panel"):
            self._update_move_panel()

    def set_mode(self, m):
        """Cambia el "modo" del programa (qué está haciendo ahora el usuario):
        pipe (dibujando utilidad), leader1/2/3 (colocando Multileader/Leader),
        text (escribiendo texto libre), erase (borrando zona), move (editando),
        idle (sin nada activo).

        Además REPARENTA el grupo "En curso" (self.gcur) a la sección adecuada
        del acordeón según el modo, para que los botones Finalizar/Deshacer
        aparezcan DENTRO de la sección donde estás trabajando."""
        if m not in ("leader1", "leader2", "leader3"): self._pending = None
        if m != "erase": self._erase_pts = []
        if m != "centerline": self._cl_pts = []
        if m != "pipe": self._extending = False
        self.mode = m
        # Colocar el panel "En curso" en su sección correspondiente (si existe)
        if hasattr(self, "_slot_gcur_pipe"):
            if m == "pipe":
                self._place_widget(self.gcur, self._slot_gcur_pipe)
                self.gcur.show()
            elif m == "erase":
                self._place_widget(self.gcur, self._slot_gcur_erase)
                self.gcur.show()
            elif m == "centerline":
                self._place_widget(self.gcur, self._slot_gcur_cl)
                self.gcur.show()
            else:
                self.gcur.hide()
        self.canvas.set_mode_cursor(m)
        self._update_ui(); self._redraw()

    def _tab_map(self):
        m = {self.pipe_list: TAB_PIPE, self.sleader_list: TAB_LEADER,
             self.txt_marks_list: TAB_TEXT, self.region_list: TAB_REGION}
        if hasattr(self, "bz_list"): m[self.bz_list] = TAB_BZ
        if hasattr(self, "curve_list"): m[self.curve_list] = TAB_CURVE
        if hasattr(self, "cl_list"): m[self.cl_list] = TAB_CL
        if hasattr(self, "_db_tab_widget"): m[self._db_tab_widget] = TAB_DB
        return m

    def _current_tab(self):
        return self._tab_map().get(self.tabs.currentWidget(), TAB_PIPE)

    def _show_tab(self, logical):
        w = {v: k for k, v in self._tab_map().items()}.get(logical)
        idx = self.tabs.indexOf(w) if w is not None else -1
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def _tab_changed(self, _):
        ti = self._current_tab()
        if ti == TAB_LEADER: self.sel_leader = self._leader_at_row(self.sleader_list, self.sleader_list.currentRow())
        if self.mode == "move": self.set_mode("idle")   # no seguir editando al cambiar de pestaña
        # "Cotas por tramo" pertenece EXCLUSIVAMENTE a la pestaña Utilidades. El
        # panel vive en el dock derecho, que se comparte entre pestañas — sin
        # este toggle explicito la tabla quedaba visible al saltar de Utilidades
        # a Buzones/Curvas/Centerlines. Se oculta primero y solo Utilidades la
        # reactiva (a traves de _rebuild_seg_inv_table).
        if ti != TAB_PIPE:
            self.gprop_segs.setVisible(False)
        if ti == TAB_BZ: self._sync_bz_panel()
        elif ti == TAB_CURVE: self._sync_curve_panel()
        elif ti == TAB_CL: self._sync_cl_panel()
        elif ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            self._rebuild_seg_inv_table(self.pipes[self.sel_pipe])
        self._update_ui(); self._redraw()
    # Los "toggle_*" alternan entre "modo activo" e "idle" (sin nada activo).
    # Además abren su sección del acordeón para que las opciones sean visibles.
    def toggle_pipe(self):
        if self.mode == "pipe": self.set_mode("idle")
        else: self._open_section("pipe"); self.set_mode("pipe")
    def toggle_text_mode(self):
        if self.mode == "text": self.set_mode("idle")
        else: self._open_section("text"); self.set_mode("text")
    def toggle_erase(self):
        if self.mode == "erase": self.set_mode("idle")
        else: self._open_section("erase"); self.set_mode("erase")
    def toggle_centerline(self):
        if self.mode == "centerline": self.set_mode("idle")
        else: self._open_section("centerline"); self.set_mode("centerline")
    def active_layer(self):
        d = self.type_combo.currentData(); return d if d else "AGUA"
