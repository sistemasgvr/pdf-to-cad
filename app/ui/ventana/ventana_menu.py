"""Arma la interfaz: menús, barra de herramientas, paneles laterales, barra de estado y atajos.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class MenuMixin:
    # ─────────────────────────── UI ───────────────────────────
    def _build_ui(self):
        # La UI se arma por secciones, en este ORDEN (importante: los widgets
        # compartidos del acordeón se reubican al final, cuando ya existen los
        # del dock derecho). Cada _build_* deja sus widgets como self.* .
        self._build_menu()
        self._build_toolbar()
        self._build_left_dock()
        self._build_right_dock()
        self._build_side_panels()
        self._build_statusbar()
        # Todo listo: coloca los widgets compartidos del acordeón en la sección
        # inicial (esto necesita que self.tabs, self.gprop y self.lbl_mode existan).
        self._on_toolbox_change(self.toolbox.currentIndex())
        self._refresh_unit_labels()                # etiquetas de campo con la unidad activa

    def _build_menu(self):
        mb = self.menuBar()
        # Menús y acciones con _bind: se re-traducen solos al cambiar el idioma.
        def _menu(parent_bar, label_es):
            return _bind(parent_bar.addMenu(""), "setTitle", label_es)

        def _act(menu, label_es, fn, shortcut=None):
            return _bind(self._menu_act(menu, "", fn, shortcut), "setText", label_es)

        mfile = _menu(mb, "&Archivo")
        _act(mfile, "Nuevo lienzo…", self.new_blank_canvas, "Ctrl+N")
        _act(mfile, "Abrir PDF…", self.open_pdf)
        mfile.addSeparator()
        _act(mfile, "Abrir proyecto…", self.open_project)
        _act(mfile, "Guardar proyecto", self.save_project, "Ctrl+S")
        _act(mfile, "Guardar proyecto como…", self.save_project_as, "Ctrl+Shift+S")
        mfile.addSeparator()
        _act(mfile, "Opciones…", self.show_options)
        mfile.addSeparator()
        _act(mfile, "Cerrar proyecto", self.close_project, "Ctrl+W")
        medit = _menu(mb, "&Edición")
        _act(medit, "Deshacer", self.undo, "Ctrl+Z")
        _act(medit, "Rehacer", self.redo, "Ctrl+Shift+Z")
        medit.addSeparator()
        _act(medit, "Unir utilidades seleccionadas", self.unir_utilidades, "Ctrl+J")
        medit.addSeparator()
        _act(medit, "Editar utilidades seleccionadas en bloque…", self.editar_en_bloque, "Ctrl+E")
        _act(medit, "Copiar propiedades de la utilidad", self.copiar_propiedades, "Ctrl+Shift+C")
        _act(medit, "Pegar propiedades en las seleccionadas", self.pegar_propiedades, "Ctrl+Shift+V")
        mview = _menu(mb, "&Ver")
        self._mview = mview                        # _build_side_panels agrega sus opciones
        # «Organizar hojas…» / «Capas de hojas organizadas…» (flujo antiguo) ya no
        # van en el menú: la hoja compuesta los reemplaza. Los métodos siguen
        # (proyectos viejos con sheet_layout), pero no se ofrecen al usuario.
        # Acción dinámica: su texto muestra el tema al que se cambiaría.
        # Si estás en oscuro dice "Modo claro"; si estás en claro dice "Modo oscuro".
        self._act_theme = QtGui.QAction("", self)
        self._act_theme.triggered.connect(self._toggle_theme)
        mview.addAction(self._act_theme)
        self._refresh_theme_action_label()
        # Recomputa el texto cuando otro trigger cambie el tema (por si alguna vez
        # se agrega un atajo o un toggle desde otra parte).
        _theme.THEME_BUS.changed.connect(lambda _: self._refresh_theme_action_label())
        mview.addSeparator()
        # Toggle checkable: mostrar/ocultar las marcas de cruce y de conflicto
        # (círculos amarillos ⓘ = cruces sanos con distinta cota; círculos
        # rojos ⚠ = conflictos donde dos utilidades chocan). Encendido por
        # defecto — preferencia persistida en QSettings.
        self.chk_show_conflicts = _bind(QtGui.QAction(self), "setText", "Mostrar cruces/conflictos")
        self.chk_show_conflicts.setCheckable(True)
        try:
            _sc_pref = QtCore.QSettings("pdf-to-cad", "app").value("show_conflicts_v2", True, type=bool)
        except Exception:
            _sc_pref = True
        self.chk_show_conflicts.setChecked(bool(_sc_pref))
        _bind(self.chk_show_conflicts, "setToolTip", "Marca los puntos donde dos utilidades se cruzan geométricamente en el plano.\n"
            "  · Amarillo ⓘ: cruce sano (distinta cota, se pasan por encima/debajo).\n"
            "  · Rojo ⚠: conflicto (misma cota o sin cota → chocan).\n"
            "Apagarlo oculta las marcas y el contador de la barra de estado.")
        self.chk_show_conflicts.toggled.connect(self._on_toggle_show_conflicts)
        mview.addAction(self.chk_show_conflicts)
        mtools = _menu(mb, "&Herramientas")
        _act(mtools, "Componer hoja de trabajo…", self.compose_sheet)
        _act(mtools, "Componer PDF imagen/escaneo…", self.compose_scan_sheet)
        mtools.addSeparator()
        _act(mtools, "Insertar buzón en línea…", self.insert_manhole)
        _act(mtools, "Revisar y limpiar el dibujo…", self.revisar_dibujo)
        _act(mtools, "Instalar familia personalizada…", self.open_install_family_dialog)
        _act(mtools, "Desinstalar familia personalizada…", self.open_uninstall_family_dialog)
        mtools.addSeparator()
        _act(mtools, "Georreferenciar…", self.open_georef)
        _act(mtools, "Quitar georreferencia", self.clear_georef)
        # Normativas de diseño (normativas.py + ventana HTML normativas_dialog.py).
        mnorm = _menu(mb, "&Normativas")
        _act(mnorm, "Normativas de diseño…", self.open_normativas, "Ctrl+Shift+N")
        mnorm.addSeparator()
        # Etiquetas «Codo 45°», «Tee 90°»… de los accesorios de presión en el lienzo.
        self.act_show_acc = _bind(QtGui.QAction(self), "setText", "Mostrar accesorios (tipo y ángulo)")
        self.act_show_acc.setCheckable(True)
        try:
            _acc_pref = QtCore.QSettings("pdf-to-cad", "app").value("show_accesorios", True, type=bool)
        except Exception:
            _acc_pref = True
        self.act_show_acc.setChecked(bool(_acc_pref))
        _bind(self.act_show_acc, "setToolTip", "Muestra junto a cada codo, Tee, Wye o cruz de agua y gas el accesorio "
              "que se pondrá en Civil 3D y su ángulo; en rojo si incumple una normativa.")
        self.act_show_acc.toggled.connect(self._on_toggle_show_acc)
        mnorm.addAction(self.act_show_acc)
        mview.addAction(self.act_show_acc)
        mhelp = _menu(mb, "A&yuda")
        _act(mhelp, "Acerca de…", self.show_about)
        _act(mhelp, "Manual de usuario", self.show_manual)
        _act(mhelp, "Atajos de teclado", self.show_shortcuts)
        # Cuando el idioma cambie en vivo (desde Opciones…), retraducimos menús
        # y otros textos suscritos.
        _i18n.LANG_BUS.changed.connect(self._retranslate_ui)

    def _retranslate_ui(self, *_):
        """Re-genera el contenido CALCULADO de la UI al cambiar el idioma.

        Los textos fijos (menús, docks, botones, etiquetas, tooltips…) ya los
        re-traduce `i18n.retranslate_all` — se registraron con `_bind` al crear
        cada widget, y LANG_BUS los reaplica antes de llamar aquí. Solo queda lo
        que se arma con datos del proyecto: listas, panel de la selección, barra
        de estado y título."""
        for fn in (self._update_title, self._refresh_theme_action_label,
                   self._update_page_label, self._refresh_scale_label,
                   self._update_geo_status, self._refresh_unit_labels,
                   self._refresh_lists, self._refresh_counts, self._refresh_db_list,
                   self._refresh_catalog_panels, self._update_move_panel,
                   self._update_ui, self._redraw):
            try:
                fn()
            except Exception:   # un panel sin datos no debe cortar el resto
                pass

    def show_options(self):
        """Delegador al diálogo de opciones (dialogs.show_options)."""
        from ui.dialogos import dialogs as _dlg
        _dlg.show_options(self)

    def _build_toolbar(self):
        # ── Barra de acción superior: zoom · deshacer/rehacer · imán · exportar ──
        tb = _bind(self.addToolBar(""), "setWindowTitle", "Acciones"); tb.setMovable(False)
        # Los QAction llevan QIcon SVG; guardamos el mapa acción→nombre para
        # que _apply_theme_custom_styles pueda retintarlos al cambiar tema.
        self._action_icon_map = {}
        def tact(icon_name, tip, fn):
            a = QtGui.QAction("", self); _bind(a, "setToolTip", tip); a.triggered.connect(fn)
            tb.addAction(a); self._action_icon_map[a] = icon_name; return a
        self._act_zoom_in = tact("mdi:magnify-plus-outline", "Acercar", self._zoom_in)
        self._act_zoom_out = tact("mdi:magnify-minus-outline", "Alejar", self._zoom_out)
        tb.addSeparator()
        self._act_undo = tact("mdi:undo-variant", "Deshacer (Ctrl+Z)", self.undo)
        self._act_redo = tact("mdi:redo-variant", "Rehacer (Ctrl+Shift+Z)", self.redo)
        tb.addSeparator()
        spacer = QtWidgets.QWidget(); spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred); tb.addWidget(spacer)
        # Sin selector de unidad: TODO va en pies por campo (cotas/coordenadas),
        # salvo los diámetros que van siempre en pulgadas (lista fija del catálogo).
        tb.addSeparator()
        tb.addWidget(_bind(QtWidgets.QLabel(), "setText", "Civil 3D:"))
        self.cmb_civil = QtWidgets.QComboBox()
        from catalogo import civil_catalog as _cc
        _all_years = list(_cc.SUPPORTED_YEARS); _inst = set(_cc.installed_versions())
        for y in _all_years:
            self.cmb_civil.addItem(f"{y}{'' if y in _inst else '  ' + _tr('(no instalado)')}", y)
        if self.civil_year is not None:
            i = _all_years.index(self.civil_year); self.cmb_civil.setCurrentIndex(i)
        self.cmb_civil.currentIndexChanged.connect(self._on_civil_year_changed)
        _bind(self.cmb_civil, "setToolTip", "Versión de Civil 3D. El catálogo imperial se busca en\n"
                                  "C:\\ProgramData\\Autodesk\\C3D <año>\\<idioma>\\Pipes Catalog\\US Imperial Structures")
        tb.addWidget(self.cmb_civil)
        # Selector de idioma del catálogo — se puebla dinámicamente al elegir año.
        # Si el cliente tiene tanto 'esp' como 'enu' instalados, puede elegir
        # cuál usar para la instalación de familias custom y el listado.
        tb.addWidget(_bind(QtWidgets.QLabel(), "setText", "Idioma:"))
        self.cmb_lang = QtWidgets.QComboBox()
        _bind(self.cmb_lang, "setToolTip", "Idioma del catálogo Civil 3D a usar (subcarpeta esp/enu/etc.)")
        self.cmb_lang.currentIndexChanged.connect(self._on_civil_lang_changed)
        tb.addWidget(self.cmb_lang)
        # Poblamos el combo de idiomas por primera vez con la versión activa.
        self._refill_lang_combo()
        tb.addSeparator()
        self.btn_export = _bind(QtWidgets.QPushButton(), "setText", "Exportar DXF", pre='  ')
        self.btn_export.setIconSize(QtCore.QSize(18, 18))
        self.btn_export.clicked.connect(lambda: self.run_pipeline("todo"))
        tb.addWidget(self.btn_export)

    def _build_side_panels(self):
        # Los dos paneles se pueden ocultar solos como una pestaña en su borde, como
        # las paletas de Civil 3D (side_panels.py): chincheta en su cabecera y una
        # opción por panel en el menú Ver. Estado y ancho se recuerdan.
        self.panel_izq = side_panels.AutoHidePanel(self, self._ldock, "Herramientas",
                                                   "mdi:toolbox-outline", "left", "izq")
        self.panel_der = side_panels.AutoHidePanel(self, self._rdock, "Inventario",
                                                   "mdi:format-list-bulleted", "right", "der")
        self._mview.addSeparator()
        acciones = []
        for panel, texto in ((self.panel_izq, "Ocultar automáticamente el panel izquierdo"),
                             (self.panel_der, "Ocultar automáticamente el panel derecho")):
            act = _bind(QtGui.QAction(self), "setText", texto)
            act.setCheckable(True)
            act.toggled.connect(panel.set_autohide)

            def _sync(on, a=act):
                a.blockSignals(True); a.setChecked(on); a.blockSignals(False)
            panel.toggled.connect(_sync)
            self._mview.addAction(act)
            acciones.append(act)
            panel.restore()
        self.act_panel_izq, self.act_panel_der = acciones

    def _build_statusbar(self):
        # ── Barra de estado: modo · info · contadores en vivo · escala · georref ──
        self.status = self.statusBar(); self.status.setSizeGripEnabled(False)
        self.lbl_mode = _bind(QtWidgets.QLabel(), "setText", "Modo: inactivo")   # color por _apply_theme_custom_styles
        self.status.addWidget(self.lbl_mode)
        self.status.addWidget(QtWidgets.QLabel("│"))
        self.lbl_info = QtWidgets.QLabel("")   # color por _apply_theme_custom_styles
        self.status.addWidget(self.lbl_info, 1)
        # Aviso de snap activo mientras se dibuja. El marcador verde del lienzo
        # puede pasar desapercibido con zoom bajo; este texto confirma que el
        # click SÍ se va a pegar, y a qué.
        self.lbl_snap = QtWidgets.QLabel("")
        self.lbl_snap.setStyleSheet("color:#1ec83c; font-weight:bold;")
        self.status.addWidget(self.lbl_snap)
        # Incumplimientos de normativas: botón rojo que abre la ventana (oculto si todo cumple).
        self.btn_normas = QtWidgets.QPushButton("")
        self.btn_normas.setFlat(True); self.btn_normas.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_normas.setStyleSheet("QPushButton{color:#ff5a5a; font-weight:bold; border:0; padding:0 6px;}"
                                      "QPushButton:hover{text-decoration:underline;}")
        _bind(self.btn_normas, "setToolTip", "Accesorios que no cumplen las normativas activas. Clic para verlos.")
        self.btn_normas.clicked.connect(self.open_normativas)
        self.btn_normas.hide()
        self.status.addWidget(self.btn_normas)
        self.lbl_coords = QtWidgets.QLabel("X —  Y —  Z —")
        # Contadores en vivo: N utilidades · N leaders · N textos · dirty
        self.lbl_counts = QtWidgets.QLabel("—")
        self.lbl_dirty = QtWidgets.QLabel("")   # muestra "●" cuando hay cambios sin guardar
        # Escala como BOTÓN plano: el usuario reportó que "1"=20'" viene del
        # titleblock pero a veces necesita ajustarla. Un botón deja claro que
        # es interactivo y hace evidente el gesto (un QLabel se ve idéntico a
        # los otros textos de la barra de estado). Estilo consistente con la
        # barra: fondo transparente, sin borde salvo al pasar/pulsar.
        self.btn_scale = _bind(QtWidgets.QPushButton(), "setText", "Escala —")
        self.btn_scale.setFlat(True); self.btn_scale.setCursor(QtCore.Qt.PointingHandCursor)
        _bind(self.btn_scale, "setToolTip", "Clic para cambiar la escala del plano (1\"=X ft)")
        # Estilo por _apply_theme_custom_styles (btn plano de status bar).
        self.btn_scale.clicked.connect(self._prompt_scale)
        # Botón "Opacidad" al lado de la escala: abre un desplegable con un
        # deslizable (opacidad SOLO del PDF) y un botón para alternar el fondo
        # detrás del PDF entre blanco y negro.
        self.btn_opacity = _bind(QtWidgets.QPushButton(), "setText", "Opacidad", pre='  ')
        self.btn_opacity.setIconSize(QtCore.QSize(16, 16))
        self.btn_opacity.setFlat(True); self.btn_opacity.setCursor(QtCore.Qt.PointingHandCursor)
        _bind(self.btn_opacity, "setToolTip", "Opacidad del PDF y color de fondo (blanco/negro)")
        # Estilo por _apply_theme_custom_styles (idéntico a btn_scale).
        self.btn_opacity.clicked.connect(self._open_opacity_popup)
        self.lbl_geo = _bind(QtWidgets.QLabel(), "setText", "Georref: no")
        # Color por _apply_theme_custom_styles (usa text_info para contraste).
        for w in (self.lbl_coords, self.lbl_counts, self.lbl_dirty):
            self.status.addPermanentWidget(w)
        self.status.addPermanentWidget(self.btn_scale)
        self.status.addPermanentWidget(self.btn_opacity)
        self.status.addPermanentWidget(self.lbl_geo)   # color por _apply_theme_custom_styles
        self.canvas.moved.connect(self._update_coords)
        self._update_geo_status()
        self._info(_tr("Abre o arrastra un PDF/proyecto."))

    def _menu_act(self, menu, text, fn, sc=None):
        a = QtGui.QAction(text, self); a.triggered.connect(fn)
        if sc: a.setShortcut(sc)
        menu.addAction(a); return a

    def _apply_style(self):
        """Intencionalmente SIN stylesheet propio.

        Antes esta función definía un tema completo que DUPLICABA —y en varios
        puntos contradecía— el stylesheet global de main(). Al ser un
        stylesheet de ventana es MÁS específico, así que ganaba sobre el
        global y era imposible razonar sobre el resultado final.

        Sobre todo: su regla `QLabel,QCheckBox{...}` tocaba QCheckBox, y en
        Qt basta tocar CUALQUIER propiedad QSS de un QCheckBox/QRadioButton
        para que el estilo Fusion deje de dibujar su subcontrol ::indicator
        — el indicador desaparecía y las casillas se volvían invisibles sobre
        el fondo oscuro (reportado por el usuario). El tema completo vive
        ahora en un solo sitio: main().
        """
        self.setStyleSheet("")

    def _shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+T"), self, self.enter_move)
        for k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            QtGui.QShortcut(QtGui.QKeySequence(k), self, self._on_enter)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self._on_escape)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+C"), self, self._copy_sel)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+V"), self, self._paste_sel)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self, self._delete_shortcut)

    def _delete_shortcut(self):
        # Suprimir borra el elemento seleccionado, salvo mientras se escribe texto
        if self._editor is not None: return
        fw = QtWidgets.QApplication.focusWidget()
        if isinstance(fw, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QAbstractSpinBox)): return
        self.delete_selected()
