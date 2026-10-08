"""Panel derecho «Inventario» (pestañas y paneles de propiedades).

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class PanelDerechoMixin:
    def _build_right_dock(self):
        # ── DOCK DERECHO: inventario y selección ──
        rdock = _bind(QtWidgets.QDockWidget(self), "setWindowTitle", "Inventario"); rdock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self._rdock = rdock
        right = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(right)
        self.tabs = QtWidgets.QTabWidget()
        self.pipe_list = QtWidgets.QListWidget(); self.pipe_list.currentRowChanged.connect(self._sel_pipe)
        # Selección MASIVA: Ctrl+clic / Shift+clic / Ctrl+A. El panel de
        # propiedades sigue mostrando la fila actual; eliminar, cambiar tipo y
        # asignar bancoducto actúan sobre todas las seleccionadas.
        self.pipe_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.pipe_list.itemSelectionChanged.connect(self._pipe_selection_changed)
        self.sleader_list = QtWidgets.QListWidget(); self.sleader_list.currentRowChanged.connect(self._sel_sleader)
        self.txt_marks_list = QtWidgets.QListWidget(); self.txt_marks_list.currentRowChanged.connect(self._sel_text)
        self.region_list = QtWidgets.QListWidget(); self.region_list.currentRowChanged.connect(self._sel_region)
        self.region_list.itemChanged.connect(self._region_toggled)
        self.bz_list = QtWidgets.QListWidget(); self.bz_list.currentRowChanged.connect(self._sel_bz)
        self.curve_list = QtWidgets.QListWidget(); self.curve_list.currentRowChanged.connect(self._sel_curve)
        self.cl_list = QtWidgets.QListWidget(); self.cl_list.currentRowChanged.connect(self._sel_cl)
        # Bancoductos: pestaña con lista + mini-toolbar (nuevo/editar/duplicar).
        # Botones abajo — consistente con el resto de tabs del inventario.
        # No incluye "Eliminar" aquí: la barra inferior de la ventana ya tiene el
        # botón rojo de eliminar que actúa sobre el ítem seleccionado.
        self._db_tab_widget = QtWidgets.QWidget()
        _dbv = QtWidgets.QVBoxLayout(self._db_tab_widget)
        _dbv.setContentsMargins(0, 0, 0, 0); _dbv.setSpacing(4)
        self.db_list = QtWidgets.QListWidget()
        self.db_list.currentRowChanged.connect(self._sel_db)
        self.db_list.itemDoubleClicked.connect(lambda _it: self._db_edit())
        # Hover sobre una fila → miniatura de la sección del bancoducto.
        from ui.comun.thumbnails import HoverPreview
        self._db_hover = HoverPreview(self.db_list, self._db_preview)
        _dbv.addWidget(self.db_list, 1)
        _dbbar = GridAdaptable(max_cols=3, spacing=4)     # 3, 2 o 1 por fila según el ancho
        self.btn_db_new = _bind(WrapButton(), "setText", "+ Nuevo")
        _bind(self.btn_db_new, "setToolTip", "Crear un bancoducto nuevo desde cero.")
        self.btn_db_new.clicked.connect(self._db_new)
        self.btn_db_edit = _bind(WrapButton(), "setText", "Editar")
        _bind(self.btn_db_edit, "setToolTip", "Editar el bancoducto seleccionado.\n"
                                    "También doble-click sobre la fila.")
        self.btn_db_edit.clicked.connect(self._db_edit)
        self.btn_db_dup = _bind(WrapButton(), "setText", "Duplicar")
        _bind(self.btn_db_dup, "setToolTip", "Duplicar el bancoducto seleccionado.")
        self.btn_db_dup.clicked.connect(self._db_duplicate)
        for _b in (self.btn_db_new, self.btn_db_edit, self.btn_db_dup):
            _b.setMinimumHeight(30)
            _dbbar.addWidget(_b)
        _dbv.addLayout(_dbbar)
        _bind(self.tabs, "setTabText", "Utilidades", self.tabs.addTab(self.pipe_list, ""))
        _bind(self.tabs, "setTabText", "Leaders", self.tabs.addTab(self.sleader_list, ""))
        _bind(self.tabs, "setTabText", "Textos", self.tabs.addTab(self.txt_marks_list, "")); _bind(self.tabs, "setTabText", "Zonas", self.tabs.addTab(self.region_list, ""))
        _bind(self.tabs, "setTabText", "Buzones", self.tabs.addTab(self.bz_list, "")); _bind(self.tabs, "setTabText", "Curvas", self.tabs.addTab(self.curve_list, ""))
        _bind(self.tabs, "setTabText", "Centerlines", self.tabs.addTab(self.cl_list, ""))
        _bind(self.tabs, "setTabText", "Bancoductos", self.tabs.addTab(self._db_tab_widget, ""))
        # RESPONSIVO: los textos de los items son largos ("AGUA · 12" · 4
        # vértices · <nombre>"), así que por defecto QListWidget saca una barra
        # de desplazamiento HORIZONTAL y el usuario tiene que arrastrarla para
        # leer. Con elide a la derecha el texto se recorta con "…" y la barra
        # desaparece; el texto completo queda en el tooltip del item (ver
        # _refresh_lists). No afecta la selección ni los índices de fila.
        for _lw in (self.pipe_list, self.sleader_list,
                    self.txt_marks_list, self.region_list, self.bz_list,
                    self.curve_list, self.cl_list, self.db_list):
            _lw.setTextElideMode(QtCore.Qt.ElideRight)
            _lw.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            _lw.setWordWrap(False)
            _lw.setUniformItemSizes(True)          # más fluido con muchas filas
        # Menú contextual (clic derecho) en cada lista visible del inventario
        for listw, tab_idx in ((self.pipe_list, TAB_PIPE),
                               (self.sleader_list, TAB_LEADER), (self.txt_marks_list, TAB_TEXT),
                               (self.region_list, TAB_REGION),
                               (self.db_list, TAB_DB)):
            listw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            listw.customContextMenuRequested.connect(
                lambda pos, lw=listw, ti=tab_idx: self._list_context_menu(lw, ti, pos))
        # Selector de sección: desplegable en vez de pestañas clicables (con
        # varias secciones, la fila de tabs no entraba bien) — misma lógica de
        # siempre debajo, el combo solo refleja/mueve self.tabs.currentIndex.
        self.tab_combo = QtWidgets.QComboBox()
        self.tab_combo.setMaxVisibleItems(self.tabs.count() + 2)
        self.tab_combo.setStyleSheet("QComboBox { combobox-popup: 0; }")
        for key in (N_("Utilidades"), N_("Leaders"), N_("Textos"), N_("Zonas"), N_("Buzones"), N_("Curvas"),
                    N_("Centerlines"), N_("Bancoductos")):
            _bind_item(self.tab_combo, key)
        self.tab_combo.currentIndexChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.tab_combo.setCurrentIndex)
        self.tabs.tabBar().hide()
        rv.addWidget(self.tab_combo)
        self.tabs.currentChanged.connect(self._tab_changed); rv.addWidget(self.tabs, 1)
        # Propiedades de la utilidad seleccionada (nombre, diámetro, unidad) → XDATA en el DXF
        self.gprop = _bind(ResponsiveGroupBox(), "setTitle", "Propiedades de la utilidad"); fpr = QtWidgets.QFormLayout(self.gprop)
        self.prop_name = QtWidgets.QLineEdit(); self.prop_name.editingFinished.connect(self._prop_changed)
        # El diámetro va SIEMPRE en PULGADAS y SOLO de la lista estándar del
        # catálogo (12,15,18,…): un desplegable NO editable, sin valores libres,
        # para que coincida 1:1 con un tamaño real del catálogo de Civil 3D.
        # Es independiente de la unidad de trabajo (que rige coordenadas/cotas).
        # El diámetro ya no es un campo del UI: se deriva automáticamente del
        # "Tamaño (catálogo)" elegido. p["diam"] se calcula al guardar propiedades.
        fpr.addRow(_bind(QtWidgets.QLabel(), "setText", "Nombre:"), self.prop_name)
        # Campos de la utilidad usados por el JSON de red 3.0 y por el DXF:
        #   - material: texto libre (p.ej. "HDPE"); viaja al JSON como `material`.
        #   - part (pieza): nombre del tipo de pieza; viaja al JSON como `part`.
        #   - network_type: "auto" (=lo decide la capa) / "pipe" (con buzones)
        #     / "pressure" (línea a presión). Viaja al JSON como `network_type`.
        #   - invert inicio/fin (m): las COTAS de fondo de la tubería en cada
        #     extremo; imprescindibles para reconstruir la red 3D.
        # Material: desplegable con los valores exactos de Civil 3D (no texto libre).
        self.prop_material = QtWidgets.QComboBox()
        for m in PIPE_MATERIALS:
            _bind_item(self.prop_material, m, m)   # data = valor real (no traducido)
        self.prop_material.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.prop_part = QtWidgets.QLineEdit(); _bind(self.prop_part, "setPlaceholderText", "p.ej. 900 mm Corrugated HDPE Pipe")
        self.prop_part.editingFinished.connect(self._prop_changed)
        self.prop_nettype = QtWidgets.QComboBox()
        _bind_item(self.prop_nettype, "Automático (según la capa)", "")
        _bind_item(self.prop_nettype, "Con buzones (pipe)", "pipe")
        _bind_item(self.prop_nettype, "A presión (pressure)", "pressure")
        self.prop_nettype.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.prop_inv0 = QtWidgets.QDoubleSpinBox(); self.prop_inv1 = QtWidgets.QDoubleSpinBox()
        for sp in (self.prop_inv0, self.prop_inv1):
            sp.setRange(-100000, 100000); sp.setDecimals(3); sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sp.valueChanged.connect(lambda _: self._prop_changed())
        fpr.addRow(_bind(QtWidgets.QLabel(), "setText", "Tipo de red:"), self.prop_nettype)
        # Labels dinámicas: se recomponen al cambiar la unidad de trabajo.
        # Nombre igual a Civil 3D: "Elevación de rasante" (no "Invert").
        self.lbl_prop_inv0 = _bind(QtWidgets.QLabel(), "setText", "Elev. de rasante inicial (ft):"); fpr.addRow(self.lbl_prop_inv0, self.prop_inv0)
        self.lbl_prop_inv1 = _bind(QtWidgets.QLabel(), "setText", "Elev. de rasante final (ft):");   fpr.addRow(self.lbl_prop_inv1, self.prop_inv1)
        # Familia + tamaño del catálogo Civil 3D para esta pipe (solo gravedad).
        # Para presión y conduit no aplica: presión usa el sub-catálogo por material
        # y conduit se deja como polyline simple.
        self.prop_family = QtWidgets.QComboBox()
        self.prop_family.currentIndexChanged.connect(self._pipe_family_changed)
        self.prop_size = QtWidgets.QComboBox()
        self.prop_size.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.lbl_prop_family = _bind(QtWidgets.QLabel(), "setText", "Familia (catálogo):")
        self.lbl_prop_size = _bind(QtWidgets.QLabel(), "setText", "Tamaño (catálogo):")
        fpr.addRow(self.lbl_prop_family, self.prop_family)
        # Botón verde «+»: agrega un tamaño nuevo a la familia (catalogo_tamanos.py).
        self.btn_add_size = self._boton_mas(lambda: self._agregar_tamano("pipe"))
        self._prop_size_box = self._con_boton(self.prop_size, self.btn_add_size)
        fpr.addRow(self.lbl_prop_size, self._prop_size_box)

        rv.addWidget(self.gprop)
        # ── Cotas por tramo (edición de rasante por segmento) ──────────────────
        # inv_start/inv_end (arriba) siguen fijando los extremos de la utilidad
        # completa; esta tabla muestra cada TRAMO (par de vértices consecutivos)
        # con su Inicio/Fin/Longitud/Pendiente% — no solo la cota "pelada" del
        # vértice — para poder juzgar si la pendiente resultante tiene sentido.
        # "Fin" es editable (fija esa cota como override del vértice
        # compartido con el tramo siguiente); "Auto" la vuelve a la
        # interpolación lineal de siempre — ver _interp_vertex_z y su espejo en
        # ImportarRed.cs (InterpolateZ). Clic en la columna "Tramo" lo resalta
        # y encuadra en el lienzo.
        self.gprop_segs = _bind(ResponsiveGroupBox(), "setTitle", "Cotas por tramo")
        segv = QtWidgets.QVBoxLayout(self.gprop_segs)
        self.btn_seg_edit = _bind(WrapButton(), "setText", "Activar edición por tramo", pre='  ')
        self.btn_seg_edit.setIconSize(QtCore.QSize(18, 18))
        self.btn_seg_edit.setCheckable(True)
        _bind(self.btn_seg_edit, "setToolTip", "Activa la edición de cotas por tramo. Cuando está apagado se usan "
            "solo las rasantes de inicio/fin (interpolación lineal). Cuando "
            "se enciende, cada Inicio y Fin es totalmente independiente y "
            "editable, y en el lienzo aparecen etiquetas T1, T2… por tramo.")
        self.btn_seg_edit.toggled.connect(self._seg_edit_toggled)
        segv.addWidget(self.btn_seg_edit)
        self.tbl_seg_inv = QtWidgets.QTableWidget(0, 4)
        _bind(self.tbl_seg_inv, "setHorizontalHeaderLabels", ["Tramo", "Inicio (ft)", "Fin (ft)", "Long (ft)"])
        hdr = self.tbl_seg_inv.horizontalHeader()
        # RESPONSIVO: "Tramo" y "Long" al ancho de su contenido (son cortos) y
        # las dos columnas de cota se reparten el resto. Con las 4 en
        # ResizeToContents la suma se pasaba del ancho del dock y salía barra
        # horizontal, dejando "Long (ft)" cortada.
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setStretchLastSection(False)
        self.tbl_seg_inv.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tbl_seg_inv.verticalHeader().setVisible(False)
        self.tbl_seg_inv.verticalHeader().setDefaultSectionSize(38)   # fila alta: usuario mayor
        self.tbl_seg_inv.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_seg_inv.cellClicked.connect(self._seg_row_label_clicked)
        # Altura para ~4 tramos visibles: sin esto el grupo quedaba comprimido y
        # solo se veía UNA fila, obligando a desplazarse para cada tramo.
        self.tbl_seg_inv.setMinimumHeight(4 * 38 + 40)
        segv.addWidget(self.tbl_seg_inv)
        self.gprop_segs.setVisible(False)
        rv.addWidget(self.gprop_segs)
        # ── Propiedades del buzón seleccionado (tab Buzones) ───────────────────
        self.gprop_bz = _bind(ResponsiveGroupBox(), "setTitle", "Propiedades del buzón"); fbz = QtWidgets.QFormLayout(self.gprop_bz)
        self.bz_cod = QtWidgets.QLineEdit(); self.bz_cod.editingFinished.connect(self._bz_prop_changed)
        self.bz_rim = QtWidgets.QDoubleSpinBox(); self.bz_sump = QtWidgets.QDoubleSpinBox()
        for sp in (self.bz_rim, self.bz_sump):
            sp.setRange(-100000, 100000); sp.setDecimals(3); sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sp.valueChanged.connect(lambda _v: self._bz_prop_changed())
        self.bz_family = QtWidgets.QComboBox(); self.bz_family.currentIndexChanged.connect(self._bz_family_changed)
        self.bz_size = QtWidgets.QComboBox(); self.bz_size.currentIndexChanged.connect(self._bz_prop_changed)
        self.bz_height = QtWidgets.QDoubleSpinBox()
        self.bz_height.setRange(0, 1000); self.bz_height.setDecimals(2)
        self.bz_height.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        _bind(self.bz_height, "setSpecialValueText", "(automática)")
        _bind(self.bz_height, "setToolTip", "Altura deseada del buzón, en pies. Si se llena, al importar la red en Civil3D\n"
            "se ajusta la cota de tapa (Rim = Sump + esta altura) para que la propiedad\n"
            "'Altura de estructura' salga exacta. Vacío (0) = se calcula automático desde el terreno.")
        self.bz_height.valueChanged.connect(lambda _v: self._bz_prop_changed())
        self.bz_net_lbl = QtWidgets.QLabel("—")
        self.bz_origin_lbl = QtWidgets.QLabel("—")
        fbz.addRow(_bind(QtWidgets.QLabel(), "setText", "Código:"), self.bz_cod)
        fbz.addRow(_bind(QtWidgets.QLabel(), "setText", "Familia:"), self.bz_family)
        self.btn_add_bz_size = self._boton_mas(lambda: self._agregar_tamano("structure"))
        self._bz_size_box = self._con_boton(self.bz_size, self.btn_add_bz_size)
        fbz.addRow(_bind(QtWidgets.QLabel(), "setText", "Tamaño:"), self._bz_size_box)
        fbz.addRow(_bind(QtWidgets.QLabel(), "setText", "Altura (Pies):"), self.bz_height)
        # SÓLIDO (caja cuadrada reconocida del PDF): sin familia/tamaño de catálogo;
        # largo × ancho (precargados del plano, editables: cambian el dibujo) y
        # altura. En Civil 3D se dibuja como sólido 3D.
        self._fbz = fbz
        self.sld_len = QtWidgets.QDoubleSpinBox(); self.sld_wid = QtWidgets.QDoubleSpinBox()
        self.sld_h = QtWidgets.QDoubleSpinBox()
        for sp in (self.sld_len, self.sld_wid, self.sld_h):
            sp.setRange(0.01, 1000); sp.setDecimals(3)
            sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda _v: self._solid_prop_changed())
        self.sld_h.setDecimals(5)                   # 6.56168 ft = 2 m exactos
        _bind(self.sld_len, "setToolTip", "Largo del sólido (lado largo), en pies. Viene medido del plano; al cambiarlo se redibuja en el lienzo.")
        _bind(self.sld_wid, "setToolTip", "Ancho del sólido (lado corto), en pies. Viene medido del plano; al cambiarlo se redibuja en el lienzo.")
        _bind(self.sld_h, "setToolTip", "Altura del sólido 3D en Civil 3D, en pies (por defecto 6.56168 ft = 2 m).")
        self._lbl_sld_len = _bind(QtWidgets.QLabel(), "setText", "Largo (Pies):")
        self._lbl_sld_wid = _bind(QtWidgets.QLabel(), "setText", "Ancho (Pies):")
        self._lbl_sld_h = _bind(QtWidgets.QLabel(), "setText", "Altura del sólido (Pies):")
        fbz.addRow(self._lbl_sld_len, self.sld_len)
        fbz.addRow(self._lbl_sld_wid, self.sld_wid)
        fbz.addRow(self._lbl_sld_h, self.sld_h)
        # Cota SUPERIOR del sólido: manda la tapa (base = cota − altura). Por
        # defecto la de la utilidad a la que está unida; editable.
        self.sld_top = QtWidgets.QDoubleSpinBox()
        self.sld_top.setRange(-100000, 100000); self.sld_top.setDecimals(3)
        self.sld_top.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.sld_top.setKeyboardTracking(False)
        self.sld_top.valueChanged.connect(lambda _v: self._solid_top_changed())
        _bind(self.sld_top, "setToolTip", "Cota de la parte SUPERIOR del sólido, en pies (la base queda en cota − altura).\n"
            "Por defecto es la cota de la utilidad a la que está unido.")
        self.btn_sld_top_auto = QtWidgets.QToolButton()
        self.btn_sld_top_auto.setIcon(_icon("mdi:restore"))
        _bind(self.btn_sld_top_auto, "setToolTip", "Volver a la cota de la utilidad unida")
        self.btn_sld_top_auto.clicked.connect(self._solid_top_reset)
        self._sld_top_w = QtWidgets.QWidget(); _h = QtWidgets.QHBoxLayout(self._sld_top_w)
        _h.setContentsMargins(0, 0, 0, 0); _h.setSpacing(4)
        _h.addWidget(self.sld_top, 1); _h.addWidget(self.btn_sld_top_auto)
        self.lbl_sld_top_src = QtWidgets.QLabel("")
        self._lbl_sld_top = _bind(QtWidgets.QLabel(), "setText", "Cota superior (Pies):")
        fbz.addRow(self._lbl_sld_top, self._sld_top_w)
        fbz.addRow("", self.lbl_sld_top_src)
        fbz.addRow(_bind(QtWidgets.QLabel(), "setText", "Red:"), self.bz_net_lbl)
        fbz.addRow(_bind(QtWidgets.QLabel(), "setText", "Origen:"), self.bz_origin_lbl)
        self.bz_is_curve = _bind(WrapButton(), "setText", "Cambiar a elemento curvo")
        self.bz_is_curve.setCheckable(True)
        _bind(self.bz_is_curve, "setToolTip", "Marca este vértice como la esquina de un elemento curvo (p.ej. el codo de un\n"
            "bancoducto) en vez de un buzón/caja normal. Pasa a la pestaña 'Curvas' y no se\n"
            "exporta como buzón en el DXF (se marca con un punto PDFCAD_CURVE aparte).")
        self.bz_is_curve.toggled.connect(self._bz_curve_toggled)
        fbz.addRow("", self.bz_is_curve)
        self.chk_bz_hidden = _bind(WrapButton(), "setText", "Desactivar/activar buzón")
        self.chk_bz_hidden.setCheckable(True)
        _bind(self.chk_bz_hidden, "setToolTip", "Este vértice se detectó automáticamente pero no quieres un buzón real ahí.\n"
            "Se deja de dibujar en el lienzo y, al exportar/importar en Civil3D, se usa la\n"
            "familia 'Estructura nula' (invisible) en vez de un buzón visible — la red sigue\n"
            "conectada, solo no se ve el manhole.")
        self.chk_bz_hidden.toggled.connect(self._bz_hidden_toggled)
        fbz.addRow("", self.chk_bz_hidden)
        # Checkbox de etiquetas — entre la lista de buzones (tab) y el panel de propiedades.
        self.chk_bz_labels = _bind(WrapCheckBox(), "setText", "Ver etiquetas de buzón y en el DXF exportado")
        self.chk_bz_labels.setChecked(bool(self.show_bz_labels))
        def _toggle_bz_labels(v):
            self.show_bz_labels = bool(v); self._redraw()
        self.chk_bz_labels.toggled.connect(_toggle_bz_labels)
        rv.addWidget(self.chk_bz_labels)
        rv.addWidget(self.gprop_bz)
        # Mensaje guía cuando estás en la tab Buzones pero no seleccionaste nada.
        self.lbl_bz_hint = _bind(QtWidgets.QLabel(), "setText", "Haz clic en un buzón de la lista (o en su círculo en el lienzo) para ver y editar sus propiedades.")
        self.lbl_bz_hint.setWordWrap(True)
        # Estilo aplicado por _apply_theme_custom_styles (sigue el tema activo).
        rv.addWidget(self.lbl_bz_hint)
        self.gprop_bz.setVisible(False); self.lbl_bz_hint.setVisible(False)
        # ── Propiedades del elemento curvo seleccionado (tab Curvas) ───────────
        self.gprop_curve = _bind(ResponsiveGroupBox(), "setTitle", "Propiedades del elemento curvo"); fcv = QtWidgets.QFormLayout(self.gprop_curve)
        self.cv_cod = QtWidgets.QLineEdit(); self.cv_cod.editingFinished.connect(self._curve_prop_changed)
        # Familia/Tamaño NO se eligen aparte: siempre son los de la tubería recta que
        # pasa por este vértice (garantiza que la curva calce con los tramos rectos).
        self.cv_family_lbl = QtWidgets.QLabel("—")
        self.cv_size_lbl = QtWidgets.QLabel("—")
        self.cv_radius = QtWidgets.QDoubleSpinBox()
        self.cv_radius.setRange(0, 10000); self.cv_radius.setDecimals(2)
        self.cv_radius.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        _bind(self.cv_radius, "setSpecialValueText", "(automático)")
        _bind(self.cv_radius, "setToolTip", "Radio deseado de la tubería curva, en pies. Vacío (0) = automático:\n"
            "al importar en Civil3D se usa 6× el ancho/diámetro interior de la tubería.")
        self.cv_radius.valueChanged.connect(lambda _v: self._curve_prop_changed())
        # Aviso rojo debajo del radio con el máximo geométrico permitido y por qué.
        # Se muestra solo cuando el usuario intenta poner un valor por encima del
        # máximo (que el spinbox ya bloquea) o cuando el máximo es informativo.
        self.cv_radius_warn = QtWidgets.QLabel("")
        self.cv_radius_warn.setWordWrap(True)
        self.cv_radius_warn.setStyleSheet("color:#d33; font-size:14px;")
        self.cv_radius_warn.setVisible(False)
        self.cv_net_lbl = QtWidgets.QLabel("—")
        self.cv_origin_lbl = QtWidgets.QLabel("—")
        fcv.addRow(_bind(QtWidgets.QLabel(), "setText", "Código:"), self.cv_cod)
        fcv.addRow(_bind(QtWidgets.QLabel(), "setText", "Familia (tubería):"), self.cv_family_lbl)
        fcv.addRow(_bind(QtWidgets.QLabel(), "setText", "Tamaño:"), self.cv_size_lbl)
        fcv.addRow(_bind(QtWidgets.QLabel(), "setText", "Radio (Pies):"), self.cv_radius)
        fcv.addRow("", self.cv_radius_warn)
        fcv.addRow(_bind(QtWidgets.QLabel(), "setText", "Red:"), self.cv_net_lbl)
        fcv.addRow(_bind(QtWidgets.QLabel(), "setText", "Origen:"), self.cv_origin_lbl)
        self.curve_is_bz = _bind(WrapButton(), "setText", "Volver a tratar como buzón/caja")
        self.curve_is_bz.clicked.connect(self._curve_is_bz_toggled)
        fcv.addRow("", self.curve_is_bz)
        rv.addWidget(self.gprop_curve)
        self.lbl_curve_hint = _bind(QtWidgets.QLabel(), "setText", "Haz clic en un elemento curvo de la lista (o en su marcador violeta en el lienzo) "
            "para ver y editar sus propiedades.")
        self.lbl_curve_hint.setWordWrap(True)
        # Estilo aplicado por _apply_theme_custom_styles.
        rv.addWidget(self.lbl_curve_hint)
        self.gprop_curve.setVisible(False); self.lbl_curve_hint.setVisible(False)
        # ── Propiedades del centerline seleccionado (tab Centerlines) ──────────
        self.gprop_cl = _bind(ResponsiveGroupBox(), "setTitle", "Propiedades del centerline"); fcl = QtWidgets.QFormLayout(self.gprop_cl)
        self.cl_cod = QtWidgets.QLineEdit(); self.cl_cod.editingFinished.connect(self._cl_prop_changed)
        self.cl_len_lbl = QtWidgets.QLabel("—")
        fcl.addRow(_bind(QtWidgets.QLabel(), "setText", "Código:"), self.cl_cod)
        fcl.addRow(_bind(QtWidgets.QLabel(), "setText", "Longitud (ft):"), self.cl_len_lbl)
        rv.addWidget(self.gprop_cl)
        self.lbl_cl_hint = _bind(QtWidgets.QLabel(), "setText", "Haz clic en un centerline de la lista (o en su línea magenta punteada en el "
            "lienzo) para ver y editar sus propiedades. Referencia propia de una calle "
            "(distinta de las utilidades) para calzar contra la calle real al "
            "georreferenciar — no representa ninguna tubería.")
        self.lbl_cl_hint.setWordWrap(True)
        # Estilo aplicado por _apply_theme_custom_styles.
        rv.addWidget(self.lbl_cl_hint)
        self.gprop_cl.setVisible(False); self.lbl_cl_hint.setVisible(False)
        self._cl_prop_guard = False
        self._bz_prop_guard = False                 # evita reentradas al setear valores desde el modelo
        self._curve_prop_guard = False
        rr = GridAdaptable(max_cols=2)              # 2 columnas si caben; 1 si el panel es angosto
        self.btn_ct = _bind(WrapButton(), "setText", "Cambiar tipo"); self.btn_ct.clicked.connect(self.change_pipe_type)
        self.btn_mv = _bind(WrapButton(), "setText", "Editar/mover"); self.btn_mv.clicked.connect(self.enter_move)
        self.btn_edit = _bind(WrapButton(), "setText", "Editar texto"); self.btn_edit.clicked.connect(self.edit_selected_text)
        self.btn_del = _bind(WrapButton(), "setText", "Eliminar"); self.btn_del.setProperty("danger", True)
        self.btn_del.clicked.connect(self.delete_selected)
        # Datos extendidos (capa OCG de origen + campos del usuario), junto a Eliminar
        self.btn_xd = _bind(WrapButton(), "setText", "Ver datos extendidos")
        self.btn_xd.setProperty("success", True)
        _bind(self.btn_xd, "setToolTip", "Capa del PDF de la que salió (disciplina, sistema, ubicación, estado) "
                                         "y tus propios campos. Se guardan en el proyecto y van al DXF.")
        self.btn_xd.clicked.connect(self.show_xdata)
        # Mismo orden que la rejilla de antes: [Cambiar tipo, Editar/mover] [Editar texto o
        # Ver datos extendidos (nunca los dos a la vez), Eliminar]; los ocultos no ocupan celda.
        for _b in (self.btn_ct, self.btn_mv, self.btn_edit, self.btn_xd, self.btn_del):
            rr.addWidget(_b)
        rv.addLayout(rr)
        # RESPONSIVO: en un QFormLayout la etiqueta y el campo van en la MISMA
        # fila, así que etiquetas largas ("Material de la tubería:") imponen un
        # ancho mínimo grande y sacan barra horizontal. Con WrapLongRows la
        # etiqueta se pone ENCIMA del campo cuando no cabe al lado, y el
        # formulario se adapta al ancho del dock sin recortar nada.
        for _fl in (fpr, fbz, fcv, fcl):
            _fl.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            _fl.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            _fl.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        # RESPONSIVO: el panel derecho tiene MUCHO contenido (lista + varios
        # QGroupBox de propiedades + la tabla de cotas por tramo). Sin scroll
        # externo, cuando la altura de la ventana no basta el layout comprime
        # todos los widgets — la tabla de cotas terminaba mostrando solo 2
        # filas de 4 sin barra propia visible, como reportó el usuario. Con un
        # QScrollArea alrededor de TODO el contenido del dock, el panel entero
        # se puede desplazar y cada widget conserva su tamaño natural (misma
        # solución que ya usaba el dock izquierdo — el acordeón vive en un
        # QScrollArea). Es el patrón estándar para paneles de propiedades.
        # ── RESPONSIVO: pasada final sobre TODOS los descendientes del dock ──
        # Sin esto los QLineEdit/QDoubleSpinBox/QComboBox reservan su ancho
        # natural (a veces >200px por dígitos de precisión), y las QLabel largas
        # ("Elev. de rasante inicial (ft):") empujan la columna izquierda del
        # QFormLayout. La suma sacaba una barra HORIZONTAL en el dock que no
        # deja leer nada. Estas 3 políticas globales lo evitan sin tocar cada
        # widget individual:
        #   1) Labels: word-wrap para que quiebren en el ancho disponible.
        #   2) LineEdit/SpinBox/ComboBox: sizePolicy horizontal Ignored → el
        #      layout los encoge por debajo del hint. Un minimumWidth pequeño
        #      (60–80 px) garantiza que sigan usables.
        #   3) QFormLayout: FieldGrowthPolicy = AllNonFixedFieldsGrow (los
        #      campos se estiran) y RowWrapPolicy = WrapLongRows (la label
        #      salta a la línea superior si su texto no cabe).
        for _lbl in right.findChildren(QtWidgets.QLabel):
            _lbl.setWordWrap(True)
        for _w in right.findChildren(QtWidgets.QAbstractSpinBox):
            _w.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            _w.setMinimumWidth(70)
        for _w in right.findChildren(QtWidgets.QLineEdit):
            _w.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            _w.setMinimumWidth(70)
        for _w in right.findChildren(QtWidgets.QComboBox):
            _w.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            _w.setMinimumWidth(70)
            _w.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            _w.setMinimumContentsLength(6)
            try: _w.view().setTextElideMode(QtCore.Qt.ElideRight)
            except Exception: pass
        for _fl in right.findChildren(QtWidgets.QFormLayout):
            _fl.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            _fl.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            _fl.setHorizontalSpacing(6)

        rscroll = QtWidgets.QScrollArea()
        rscroll.setWidget(right)
        rscroll.setWidgetResizable(True)
        rscroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        rscroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        rdock.setWidget(rscroll)
        # 300 (antes 250): la fuente base subió a 14px por accesibilidad, y con
        # 250 los campos quedaban demasiado estrechos.
        rdock.setMinimumWidth(300)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, rdock)
