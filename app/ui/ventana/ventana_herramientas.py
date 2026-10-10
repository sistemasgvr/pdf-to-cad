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
        escala = self.canvas.fondo_escala           # hoja enorme a menos resolución (fondo_pdf)
        if regions:
            img = img.convertToFormat(QtGui.QImage.Format_RGB32)
            painter = QtGui.QPainter(img)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            if escala != 1.0:
                painter.scale(escala, escala)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
            for rg in regions:
                poly = QtGui.QPolygonF([QtCore.QPointF(px, py) for (px, py) in rg["pts"]])
                painter.drawPolygon(poly)
            painter.end()
        dlg = GeorefDialog(self, img, self.pipes, self.ref_centerlines, self.georef, img_escala=escala)
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
    def open_normativas(self):
        """Ventana flotante de normativas (normativas_dialog.py)."""
        from ui.dialogos import normativas_dialog
        normativas_dialog.abrir(self)

    def _on_toggle_show_acc(self, on):
        try:
            QtCore.QSettings("pdf-to-cad", "app").setValue("show_accesorios", bool(on))
        except Exception:
            pass
        self._redraw()

    def _draw_accesorios(self):
        """Evalúa las normativas activas y dibuja los accesorios de presión con
        su tipo y ángulo (accesorios_view.py). Deja `_accesorios`,
        `_normas_res` y `_normas_lista` para la ventana y la barra de estado."""
        self._accesorios = []; self._normas_res = {}; self._normas_lista = []
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        if ft_px and self.pipes:
            ctx = normativas.Contexto(self.pipes, self.structures, self._pipe_z_at, ft_px)
            self._normas_res = normativas.evaluar(self.normas, self.normas_estado, ctx)
            self._normas_lista = normativas.incumplimientos(self._normas_res, self.normas)
            act = getattr(self, "act_show_acc", None)
            if act is None or act.isChecked():
                self._accesorios = ctx.accesorios
                from ui.comun import accesorios_view
                tol = 0.5 / ft_px
                self._overlay += accesorios_view.dibujar(self.canvas.scene(), self._accesorios,
                                                         self._normas_lista, tol)
        n = len(self._normas_lista)
        if hasattr(self, "btn_normas"):
            self.btn_normas.setText("✗ " + _tr("{n} fuera de normativa").format(n=n) if n else "")
            self.btn_normas.setVisible(bool(n))
        if self._normas_dlg is not None:
            self._normas_dlg.refrescar()

    def _normas_ir_a(self, n):
        """Centra el lienzo en el incumplimiento n y lo marca un momento."""
        if not (0 <= n < len(self._normas_lista)):
            return
        inc = self._normas_lista[n][0]
        self.canvas.centerOn(inc.x, inc.y)
        sc = self.canvas.scene()
        pen = QtGui.QPen(QtGui.QColor(255, 60, 60), 3); pen.setCosmetic(True)
        r = 26.0
        it = sc.addEllipse(-r, -r, 2 * r, 2 * r, pen)
        it.setPos(inc.x, inc.y); it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        it.setZValue(Z_HANDLE + 9)

        def _quitar():
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        QtCore.QTimer.singleShot(1800, _quitar)
        self.raise_(); self.activateWindow()

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
