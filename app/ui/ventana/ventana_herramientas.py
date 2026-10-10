"""Familias personalizadas, georreferencia, ayuda, normativas y tema.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class HerramientasMixin:
    # ─────────────────────────── Instalador familias personalizadas ───────────
    def open_install_family_dialog(self):
        dialogs.open_install_family_dialog(self)

    def open_uninstall_family_dialog(self):
        dialogs.open_uninstall_family_dialog(self)

    def clear_georef(self):
        if not self.georef.active():
            self._info(_tr("El plano no está georreferenciado.")); return
        self._dirty = True; self.georef = georef_mod.Georef()
        self._update_geo_status(); self._info(_tr("Georreferencia quitada; se usa la escala del titleblock."))

    def open_georef(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Sin plano"), _tr("Abre un PDF o proyecto primero.")); return
        try:
            from geo.georef_dialog import GeorefDialog
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, _tr("Falta un componente"),
                _tr("La georreferenciación necesita matplotlib, pyproj y scikit-image.\n\n"
                    "Instálalos con:\n  {cmd}\n\nDetalle: {e}").format(
                    cmd=f'"{sys.executable}" -m pip install matplotlib pyproj scikit-image', e=e))
            return
        # Solo el PDF crudo (sin utilidades/leaders horneados encima): el
        # diálogo dibuja las utilidades y centerlines como líneas vectoriales
        # propias sobre este pixmap, así no se pixelan al hacer zoom y su
        # opacidad no se ve afectada por la barra de opacidad del PDF.
        img = self.canvas.pixmap_item.pixmap().toImage()
        # Aplicar las zonas de borrado ACTIVAS sobre la imagen que ve el diálogo:
        # se tapan con blanco opaco, igual que en el lienzo principal. Si no, la
        # georreferenciación seguía mostrando el contenido que el usuario ya borró.
        # Las coordenadas de las zonas están en el mismo espacio de píxeles del
        # pixmap, así que se dibujan directamente sobre la imagen.
        regions = [r for r in self.erase_regions if r.get("enabled", True)]
        if regions:
            img = img.convertToFormat(QtGui.QImage.Format_RGB32)
            painter = QtGui.QPainter(img)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
            for rg in regions:
                poly = QtGui.QPolygonF([QtCore.QPointF(px, py) for (px, py) in rg["pts"]])
                painter.drawPolygon(poly)
            painter.end()
        dlg = GeorefDialog(self, img, self.pipes, self.ref_centerlines, self.georef)
        dlg.exec()
        # El propio diálogo guarda self.georef y el proyecto (botón "Guardar
        # georreferenciación"); no hace falta repetir ese trabajo acá.

    # ─────────────────────────── Ayuda ───────────────────────────
    def _show_html(self, title, html, w=780, h=660):
        dialogs.show_html(self, title, html, w, h)

    def show_about(self):
        dialogs.show_about(self)

    def show_manual(self):
        dialogs.show_manual(self)

    def show_shortcuts(self):
        dialogs.show_shortcuts(self)

    # ─────────────────────────── normativas ───────────────────────────
    def open_normativas(self, en_avisos=False):
        """Ventana de normativas en tablas (normas_dialog.py)."""
        from ui.dialogos import normas_dialog
        normas_dialog.abrir(self, en_avisos=en_avisos)

    def _usar_normas(self, cat):
        """Reemplaza el catálogo de normativas (global), lo guarda y redibuja."""
        self.normas_cat = normas_catalogo.normalizar(cat)
        try:
            normas_catalogo.guardar(self.normas_cat)
        except OSError as e:
            self._info(_tr("No se pudieron guardar las normativas: {e}").format(e=e))
        if 0 <= getattr(self, "sel_pipe", -1) < len(self.pipes):
            self._cargar_tipos_panel(self.pipes[self.sel_pipe])
        self._redraw()

    def _on_toggle_show_acc(self, on):
        try:
            QtCore.QSettings("pdf-to-cad", "app").setValue("show_accesorios", bool(on))
        except Exception:
            pass
        self._redraw()

    def _on_toggle_show_normas(self, on):
        try:
            QtCore.QSettings("pdf-to-cad", "app").setValue("show_normas", bool(on))
        except Exception:
            pass
        self._redraw()

    def _mostrar_avisos(self, on):
        """Ver → Avisos → Mostrar todos / Ocultar todos."""
        for a in (self.chk_show_conflicts, self.act_show_acc, self.act_show_normas):
            a.setChecked(bool(on))

    def _draw_accesorios(self):
        """Revisa las normativas en tablas (normas_validar) y dibuja los accesorios de
        presión con su tipo y ángulo (accesorios_view) y los avisos (avisos_view).
        Deja `_accesorios` y `_normas_avisos` para la ventana y la barra de estado."""
        self._accesorios = []; self._normas_avisos = []
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        if ft_px and self.pipes:
            from nucleo import accesorios as _acc
            accs = _acc.accesorios(self.pipes, self._pipe_z_at, ft_px)
            con_db = {i for db in getattr(self, "duct_banks", []) or [] for i in db.assigned()}
            self._normas_avisos = normas_validar.validar(self.normas_cat, self.pipes, accs, ft_px, con_db)
            tol = 0.5 / ft_px
            ver_acc = getattr(self, "act_show_acc", None) is None or self.act_show_acc.isChecked()
            if ver_acc:
                self._accesorios = accs
                from ui.comun import accesorios_view
                self._overlay += accesorios_view.dibujar(self.canvas.scene(), accs, self._normas_avisos, tol)
            if getattr(self, "act_show_normas", None) is None or self.act_show_normas.isChecked():
                from ui.comun import avisos_view
                self._overlay += avisos_view.dibujar(self.canvas.scene(), self._normas_avisos, tol * 2, ver_acc)
        n = sum(1 for a in self._normas_avisos if not a.info)
        if hasattr(self, "btn_normas"):
            self.btn_normas.setText("⚠ " + _tr("{n} avisos de normativa").format(n=n) if n else "")
            self.btn_normas.setVisible(bool(n))
        if self._normas_dlg is not None:
            self._normas_dlg.refrescar()
        if getattr(self, "lbl_normas_pipe", None) is not None:
            self._mostrar_avisos_de_la_utilidad()
        self._vista3d_al_dia()

    def _normas_ir_a(self, n):
        """Centra el lienzo en el aviso n y lo marca un momento."""
        if not (0 <= n < len(self._normas_avisos)):
            return
        a = self._normas_avisos[n]
        self._ir_a_elemento(a.x, a.y, "pipe", a.pipe)

    def _ir_a_elemento(self, x, y, objeto=None, indice=-1):
        """Lleva el lienzo a (x, y), selecciona el elemento y lo marca un momento."""
        self._no_center = True
        try:
            if objeto == "pipe" and indice is not None and 0 <= indice < len(self.pipes):
                self._show_tab(TAB_PIPE); self.pipe_list.clearSelection(); self.pipe_list.setCurrentRow(indice)
            elif objeto == "struct" and indice in getattr(self, "_bz_rows", []):
                self._show_tab(TAB_BZ); self.bz_list.setCurrentRow(self._bz_rows.index(indice))
            elif objeto == "curve" and indice in getattr(self, "_curve_rows", []):
                self._show_tab(TAB_CURVE); self.curve_list.setCurrentRow(self._curve_rows.index(indice))
        finally:
            self._no_center = False
        self.canvas.centerOn(x, y)
        sc = self.canvas.scene()
        pen = QtGui.QPen(QtGui.QColor(240, 170, 20), 3); pen.setCosmetic(True)
        r = 26.0
        it = sc.addEllipse(-r, -r, 2 * r, 2 * r, pen)
        it.setPos(x, y); it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        it.setZValue(Z_HANDLE + 9)

        def _quitar():
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        QtCore.QTimer.singleShot(1800, _quitar)
        self.raise_(); self.activateWindow()

    # ─────────────────────── tipo y amperaje de la utilidad ───────────────────────
    def _cargar_tipos_panel(self, p):
        """Llena «Tipo» con los tipos de la utilidad (normativas) y muestra el amperaje
        solo en eléctrico. Sin disparar `_prop_changed`."""
        if not hasattr(self, "prop_tipo"):
            return
        cb = self.prop_tipo
        cb.blockSignals(True)
        cb.clear()
        cb.addItem(_tr("(sin tipo)"), "")
        for tp in normas_catalogo.tipos_de(self.normas_cat, p.get("layer")):
            cb.addItem(tp, tp)
        actual = (p.get("tipo") or "").strip()
        if actual and cb.findData(actual) < 0:
            cb.addItem(actual, actual)             # tipo que ya no está en las normativas
        cb.setCurrentIndex(max(0, cb.findData(actual)))
        cb.blockSignals(False)
        es_elec = (p.get("layer") or "") == "ELECTRICO"
        self.lbl_prop_amp.setVisible(es_elec)
        self.prop_amp.setVisible(es_elec)
        self.prop_amp.blockSignals(True)
        self.prop_amp.setValue(float(normas_catalogo.numero(p.get("amperaje")) or 0.0))
        self.prop_amp.blockSignals(False)
        self._mostrar_avisos_de_la_utilidad()

    def _mostrar_avisos_de_la_utilidad(self):
        lbl = getattr(self, "lbl_normas_pipe", None)
        if lbl is None:
            return
        suyos = [a for a in getattr(self, "_normas_avisos", []) or [] if a.pipe == self.sel_pipe]
        lbl.setText("\n".join(("ⓘ " if a.info else "⚠ ") + a.mensaje for a in suyos[:4]))
        lbl.setVisible(bool(suyos))

    def _agregar_tipo(self):
        """«+» junto a «Tipo»: un tipo nuevo para esta utilidad (queda en las
        normativas, para todos los proyectos, y sale al exportar su Excel)."""
        if not (0 <= self.sel_pipe < len(self.pipes)):
            return
        p = self.pipes[self.sel_pipe]
        texto, ok = QtWidgets.QInputDialog.getText(
            self, _tr("Agregar tipo"), _tr("Tipo nuevo para {utilidad} (por ejemplo «Distribución secundaria»):")
            .format(utilidad=self._tipo(p.get("layer"))))
        if not ok or not texto.strip():
            return
        nombre = normas_catalogo.agregar_tipo(self.normas_cat, p.get("layer"), texto)
        try:
            normas_catalogo.guardar(self.normas_cat)
        except OSError as e:
            self._info(_tr("No se pudieron guardar las normativas: {e}").format(e=e))
        self._push()
        p["tipo"] = nombre
        self._cargar_tipos_panel(p)
        self._refresh_lists(); self._reselect_pipes([self.sel_pipe]); self._redraw()
        self._info(_tr("Tipo «{tipo}» agregado.").format(tipo=nombre))

    # ─────────────────────────── tabla de datos ───────────────────────────
    def abrir_tabla_datos(self):
        """Herramientas → «Tabla de datos…»: todo el proyecto en tablas (y a Excel)."""
        from ui.dialogos import tabla_datos_dialog
        tabla_datos_dialog.abrir(self)

    def _tablas_de_datos(self):
        from nucleo import tabla_datos
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0

        def familia(fid):
            nombre = dxf_export._resolve_family(self, fid, "pipe")
            return nombre.split("|")[-1] if nombre else fid
        return tabla_datos.armar(self.pipes, self.structures, getattr(self, "duct_banks", []),
                                 getattr(self, "_normas_avisos", []), self._to_cad, ft_px,
                                 nombre_utilidad=self._tipo, nombre_familia=familia)

    def _toggle_theme(self):
        # Alterna claro↔oscuro globalmente. El módulo `theme` se encarga de
        # aplicar paleta + stylesheet + persistir la preferencia. Los widgets
        # con QSS propio (btn_export, hints, opacidad, etc.) se recomponen en
        # `_apply_theme_custom_styles` — está conectado al bus del tema.
        _theme.toggle(QtWidgets.QApplication.instance())

    def _refresh_theme_action_label(self):
        # El item del menú muestra el tema al que se cambiaría (el opuesto al actual).
        # Si estás en oscuro → "Modo claro"; si estás en claro → "Modo oscuro".
        if not hasattr(self, "_act_theme"):
            return
        if _theme.is_dark():
            self._act_theme.setText(_tr("Modo claro"))
        else:
            self._act_theme.setText(_tr("Modo oscuro"))

    def _apply_theme_custom_styles(self, *_):
        """Re-aplica todos los estilos QSS custom del Main con los tokens del tema
        activo. Se llama al construir la UI y cada vez que el bus emite cambio.
        Los widgets se identifican por `hasattr` — así funciona aunque algunos
        se creen bajo condiciones."""
        t = _theme.tokens()
        # Duct Bank + Exportar DXF (toolbar principal)
        if hasattr(self, "btn_ductbank"):
            self.btn_ductbank.setStyleSheet(
                f"QPushButton{{background:{t.accent};color:{t.text_on_accent};"
                f"font-weight:bold;padding:5px 14px;border-radius:4px;}}"
                f"QPushButton:hover{{background:{t.accent_hover};}}")
        if hasattr(self, "btn_export"):
            self.btn_export.setStyleSheet(
                f"QPushButton{{background:{t.accent};color:{t.text_on_accent};"
                f"font-weight:bold;padding:5px 14px;border-radius:4px;}}"
                f"QPushButton:hover{{background:{t.accent_hover};}}")
        # Hints amarillos de "modo activo" — mantener contraste al invertir el fondo
        hint_style = (f"color:{t.text_on_accent if _theme.is_dark() else '#7a5b00'};"
                      f"padding:8px;background:{t.accent_pressed if _theme.is_dark() else '#fff3cc'};border-radius:4px;")
        for name in ("lbl_bz_hint", "lbl_curve_hint", "lbl_cl_hint"):
            w = getattr(self, name, None)
            if w is not None: w.setStyleSheet(hint_style)
        # Barra de estado — textos con CONTRASTE (text_info) para que se lean bien
        # tanto en modo claro (dark navy sobre gris claro) como oscuro (celeste
        # suave sobre gris). Los "muted" quedan solo para leyendas secundarias.
        for name in ("lbl_mode",):
            w = getattr(self, name, None)
            if w is not None: w.setStyleSheet(f"color:{t.accent};font-weight:600;")
        for name in ("lbl_info", "lbl_geo"):
            w = getattr(self, name, None)
            if w is not None: w.setStyleSheet(f"color:{t.text_info};")
        # Coordenadas / contador / dirty: mismo criterio de contraste
        for name in ("lbl_coords", "lbl_counts"):
            w = getattr(self, name, None)
            if w is not None: w.setStyleSheet(f"color:{t.text_info};font-weight:600;")
        # Botones planos "Escala…" y "Opacidad" del status bar: transparentes con
        # texto de contraste (text_info) y hover neutral.
        for name in ("btn_scale", "btn_opacity"):
            b = getattr(self, name, None)
            if b is None: continue
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{t.text_info};"
                f"border:1px solid transparent;padding:2px 8px;border-radius:3px;font-weight:600;}}"
                f"QPushButton:hover{{background:{t.hover};border:1px solid {t.border};color:{t.text};}}"
                f"QPushButton:pressed{{background:{t.accent};color:{t.text_on_accent};}}")
        # ── Iconos SVG: retintar según el tema activo ─────────────────────
        # QIcon guarda pixmaps ya rasterizados, así que hay que reasignarlos.
        # Acciones del toolbar principal.
        for a, name in getattr(self, "_action_icon_map", {}).items():
            a.setIcon(_icon(name, color=t.text))
        # Botón "Exportar DXF" (fondo azul acento → texto/icono blancos).
        if hasattr(self, "btn_export"):
            self.btn_export.setIcon(_icon("mdi:tray-arrow-down", color=t.text_on_accent))
        # Botones del dock izquierdo (fondo azul on/off → siempre blancos).
        _dock_icons = [
            (getattr(self, "btn_pipe", None), "mdi:pencil-outline"),
            (getattr(self, "btn_leader_simple", None), "mdi:arrow-decision-outline"),
            (getattr(self, "btn_text", None), "mdi:format-text"),
            (getattr(self, "btn_erase", None), "mdi:vector-rectangle"),
            (getattr(self, "btn_centerline", None), "mdi:ruler"),
            (getattr(self, "btn_ductbank", None), "mdi:grid"),
        ]
        for b, name in _dock_icons:
            if b is not None:
                b.setIcon(_icon(name, color=t.text_on_accent))
        # Chevrons de navegación de páginas del PDF (botones planos: color texto).
        if hasattr(self, "btn_prev"):
            self.btn_prev.setIcon(_icon("mdi:chevron-left", color=t.text))
        if hasattr(self, "btn_next"):
            self.btn_next.setIcon(_icon("mdi:chevron-right", color=t.text))
        # Botones planos del status bar (Escala / Opacidad): color text_info.
        if hasattr(self, "btn_scale"):
            self.btn_scale.setIcon(_icon("mdi:pencil-outline", color=t.text_info))
        if hasattr(self, "btn_opacity"):
            self.btn_opacity.setIcon(_icon("mdi:circle-half-full", color=t.text_info))
        # Botón "Activar edición por tramo" (fondo azul → icono blanco).
        if hasattr(self, "btn_seg_edit"):
            self.btn_seg_edit.setIcon(_icon("mdi:pencil-outline", color=t.text_on_accent))
        # Tabs del acordeón: los iconos van sobre la cabecera con fondo surface_alt.
        for key, name in getattr(self, "_toolbox_icons", {}).items():
            idx = self._sec_idx.get(key)
            if idx is not None:
                self.toolbox.setItemIcon(idx, _icon(name, color=t.text))
        # Refresca dirty indicator + los botones on/off (repintado siguiente)
        self._update_ui()
        # Refrescar listas del inventario (items ocultos usan foreground custom).
        if hasattr(self, "pipe_list"):
            self._refresh_lists()
