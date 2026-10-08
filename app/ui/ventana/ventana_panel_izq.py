"""Panel izquierdo «Herramientas» (secciones del acordeón).

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class PanelIzquierdoMixin:
    def _build_left_dock(self):
        # ─────────────────────────── DOCK IZQUIERDO ───────────────────────────
        # Aquí construimos el panel lateral izquierdo como un ACORDEÓN de secciones
        # (QToolBox). Cada acción del usuario (Dibujar utilidad, Multileader, Leader,
        # Texto libre, Borrar zona, Georreferenciar, Cotas/red 3D, OCR/ICR) es su
        # propia sección. Solo UNA sección está abierta a la vez, así el usuario
        # ve ÚNICAMENTE las opciones relevantes al paso en el que está.
        #
        # QToolBox = "acordeón" en Qt: contenedor con un botón-cabecera por página.
        # Al hacer clic en una cabecera, esa página se despliega y las demás se
        # colapsan. Es el mismo widget que usamos para el historial de "Acerca de".
        ldock = _bind(QtWidgets.QDockWidget(self), "setWindowTitle", "Herramientas")
        self._ldock = ldock
        ldock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)     # no se puede sacar/flotar
        left = QtWidgets.QWidget(); lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QtWidgets.QToolBox()
        # Guardamos por NOMBRE el índice de cada sección para poder abrirla desde código.
        self._sec_idx = {}
        # Mapa clave→nombre de icono para retintar los tabs en cambios de tema.
        self._toolbox_icons = {}

        # ── Helper de creación: crea una página del toolbox con su layout vertical ──
        def _page(title_es, key, icon_name=None):
            page = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(page); lay.setSpacing(6)
            self.toolbox.addItem(page, "")
            idx = self.toolbox.count() - 1
            _bind(self.toolbox, "setItemText", title_es, idx)
            self._sec_idx[key] = idx
            if icon_name:
                self._toolbox_icons[key] = icon_name
                self.toolbox.setItemIcon(idx, _icon(icon_name))
            return page, lay

        # ═══════════════════════════════════════════════════════════════════════
        # PRIMERO: creamos TODOS los widgets (una sola vez) — luego los repartimos
        # en las secciones. Los que se comparten entre secciones (orient_combo,
        # gtxt) los REPARENTAMOS al abrir cada sección (ver _on_toolbox_change).
        # ═══════════════════════════════════════════════════════════════════════

        # Fila de navegación de páginas del PDF
        self.gp = QtWidgets.QWidget(); lp = QtWidgets.QHBoxLayout(self.gp); lp.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QtWidgets.QPushButton(""); self.btn_prev.setFixedWidth(34); self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next = QtWidgets.QPushButton(""); self.btn_next.setFixedWidth(34); self.btn_next.clicked.connect(self._next_page)
        self.btn_prev.setIconSize(QtCore.QSize(18, 18)); self.btn_next.setIconSize(QtCore.QSize(18, 18))
        self.page_edit = QtWidgets.QLineEdit(); self.page_edit.setAlignment(QtCore.Qt.AlignCenter)
        _bind(self.page_edit, "setToolTip", "Escribe un número de página y pulsa Enter")
        # returnPressed = Enter en un QLineEdit; editingFinished = perdió el foco también
        self.page_edit.returnPressed.connect(self._goto_page_edit)
        self.page_edit.editingFinished.connect(self._goto_page_edit)
        self.lbl_page = QtWidgets.QLabel(" / — ")
        lp.addWidget(self.btn_prev); lp.addWidget(self.page_edit, 1); lp.addWidget(self.lbl_page); lp.addWidget(self.btn_next)

        # Fila de transparencia del PDF de fondo (para ver mejor el marcado encima)
        self.gtr = QtWidgets.QWidget(); ltr = QtWidgets.QHBoxLayout(self.gtr); ltr.setContentsMargins(0, 0, 0, 0)
        tb_l = QtWidgets.QPushButton("−"); tb_l.setFixedSize(38, 34); tb_l.setProperty("iconOnly", True); _bind(tb_l, "setToolTip", "Más translúcido"); tb_l.clicked.connect(lambda: self._bump_opacity(-10))
        self.lbl_opacity = QtWidgets.QLabel("100%"); self.lbl_opacity.setAlignment(QtCore.Qt.AlignCenter)
        tb_r = QtWidgets.QPushButton("+"); tb_r.setFixedSize(38, 34); tb_r.setProperty("iconOnly", True); _bind(tb_r, "setToolTip", "Más opaco"); tb_r.clicked.connect(lambda: self._bump_opacity(10))
        ltr.addWidget(tb_l); ltr.addWidget(self.lbl_opacity, 1); ltr.addWidget(tb_r)

        # Botones de acción (uno por sección; el color verde/azul lo pone _update_ui)
        self.btn_pipe = _bind(WrapButton(), "setText", "Dibujar utilidad", pre='  '); self.btn_pipe.clicked.connect(self.toggle_pipe)
        self.btn_leader_simple = _bind(WrapButton(), "setText", "Colocar Leader", pre='  '); self.btn_leader_simple.clicked.connect(lambda: self.start_leader(True))
        self.btn_text = _bind(WrapButton(), "setText", "Texto libre", pre='  '); self.btn_text.clicked.connect(self.toggle_text_mode)
        self.btn_erase = _bind(WrapButton(), "setText", "Borrar zona", pre='  '); self.btn_erase.clicked.connect(self.toggle_erase)
        self.btn_centerline = _bind(WrapButton(), "setText", "Trazar centerline", pre='  '); self.btn_centerline.clicked.connect(self.toggle_centerline)
        for _b in (self.btn_pipe, self.btn_leader_simple, self.btn_text, self.btn_erase, self.btn_centerline):
            _b.setIconSize(QtCore.QSize(20, 20))

        # Grupo "Tipo de utilidad" (usado al DIBUJAR una utilidad)
        # QComboBox es la lista desplegable clásica. addItem(icono, texto, dato) le
        # asocia a cada opción un "dato oculto" que recuperamos con currentData().
        self.gt = QtWidgets.QWidget(); lgt = QtWidgets.QVBoxLayout(self.gt); lgt.setContentsMargins(0, 0, 0, 0)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.type_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, layer in TIPOS:
            _bind_item(self.type_combo, label, layer, icon=swatch_icon(layer_qcolor(layer)))
        self.type_combo.setCurrentIndex(0); self.type_combo.currentIndexChanged.connect(lambda _: self._redraw())
        # Etiquetas CORTAS a propósito: QCheckBox no hace word-wrap, así que un
        # texto largo impone un ancho mínimo que saca barra horizontal en el
        # dock. El detalle completo va al tooltip — y de paso se lee más fácil,
        # que es lo que necesita el usuario principal.
        self.chk_ab = _bind(WrapCheckBox(), "setText", "Abandonado")
        _bind(self.chk_ab, "setToolTip", "Marca la utilidad como abandonada: se dibuja con "
                               "línea discontinua ──/── W ── en el DXF.")
        self.chk_ext_same = _bind(WrapCheckBox(), "setText", "Extender: continuar la misma")
        _bind(self.chk_ext_same, "setToolTip", "Al extender un extremo de una utilidad existente, los puntos nuevos "
            "se añaden a ESA misma utilidad en vez de crear una nueva.")
        self.chk_ext_same.setChecked(True)
        lgt.addWidget(self.type_combo); lgt.addWidget(self.chk_ab); lgt.addWidget(self.chk_ext_same)

        # Combo de ORIENTACIÓN del Leader.
        self.orient_combo = QtWidgets.QComboBox()
        for oid, lbl in LEADER_ORIENT: _bind_item(self.orient_combo, lbl, oid)
        self.orient_combo.currentIndexChanged.connect(lambda _: self._update_ui())

        # Grupo "Estilo de texto" (fuente, altura, negrita + rotación).
        # COMPARTIDO por Leader y Texto libre. La rotación solo aplica a
        # textos libres; la mostramos/ocultamos según la sección abierta.
        self.gtxt = _bind(ResponsiveGroupBox(), "setTitle", "Estilo de texto"); lgx = QtWidgets.QVBoxLayout(self.gtxt)
        # QFontComboBox = combo que lista todas las fuentes instaladas en el sistema.
        self.font_combo = QtWidgets.QFontComboBox(); self.font_combo.setCurrentFont(QtGui.QFont(C.TEXT_FONT))
        self.font_combo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.font_combo.currentFontChanged.connect(lambda _: self._style_changed())
        r = QtWidgets.QHBoxLayout(); r.addWidget(_bind(QtWidgets.QLabel(), "setText", "Altura (pies):"))
        b_minus = QtWidgets.QPushButton("−"); b_minus.setFixedSize(38, 34); b_minus.setProperty("iconOnly", True); b_minus.clicked.connect(lambda: self._bump_size(-0.5))
        # QDoubleSpinBox = campo numérico decimal con incremento por flechas (aquí ocultas).
        self.size_spin = QtWidgets.QDoubleSpinBox(); self.size_spin.setRange(0.5, 200); self.size_spin.setValue(3.0)
        self.size_spin.setSingleStep(0.5); self.size_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.size_spin.valueChanged.connect(lambda _: self._style_changed())
        b_plus = QtWidgets.QPushButton("+"); b_plus.setFixedSize(38, 34); b_plus.setProperty("iconOnly", True); b_plus.clicked.connect(lambda: self._bump_size(0.5))
        r.addWidget(b_minus); r.addWidget(self.size_spin); r.addWidget(b_plus)
        self.chk_bold = _bind(WrapCheckBox(), "setText", "Negrita"); self.chk_bold.toggled.connect(lambda _: self._style_changed())
        lgx.addWidget(self.font_combo); lgx.addLayout(r); lgx.addWidget(self.chk_bold)
        # Rotación (0-360°) — solo se usa para textos libres.
        self.rot_row = QtWidgets.QWidget(); rr2 = QtWidgets.QHBoxLayout(self.rot_row); rr2.setContentsMargins(0, 0, 0, 0)
        rr2.addWidget(_bind(QtWidgets.QLabel(), "setText", "Rotación (°):"))
        rb_l = QtWidgets.QPushButton("⟲"); rb_l.setFixedSize(40, 34); rb_l.setProperty("iconOnly", True); rb_l.clicked.connect(lambda: self._bump_rot(-1))
        self.rot_spin = QtWidgets.QSpinBox(); self.rot_spin.setRange(0, 360); self.rot_spin.setSingleStep(1); self.rot_spin.setWrapping(True)
        self.rot_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons); self.rot_spin.valueChanged.connect(lambda _: self._style_changed())
        rb_r = QtWidgets.QPushButton("⟳"); rb_r.setFixedSize(40, 34); rb_r.setProperty("iconOnly", True); rb_r.clicked.connect(lambda: self._bump_rot(1))
        rr2.addWidget(rb_l); rr2.addWidget(self.rot_spin); rr2.addWidget(rb_r)
        lgx.addWidget(self.rot_row)
        lgx.addWidget(_bind(QtWidgets.QLabel(), "setText", "<i>Guarda pulsando enter </i>"))

        # Grupo "En curso" (aparece cuando estás dibujando una utilidad o zona)
        self.gcur = _bind(ResponsiveGroupBox(), "setTitle", "En curso"); lc = GridAdaptable(self.gcur, max_cols=2)
        self.btn_fin = _bind(WrapButton(), "setText", "Finalizar (Enter)"); self.btn_fin.clicked.connect(self._on_enter)
        b_up = _bind(WrapButton(), "setText", "Deshacer punto"); b_up.clicked.connect(self.undo)
        lc.addWidget(self.btn_fin); lc.addWidget(b_up)

        # ═══════════════════════════════════════════════════════════════════════
        # AHORA: creamos las secciones del acordeón y colocamos los widgets.
        # Los "slots" (self._slot_*) son QVBoxLayouts vacíos que quedan reservados
        # dentro de cada página para recibir los widgets compartidos por reparent.
        # ═══════════════════════════════════════════════════════════════════════

        # ── Sección: Vista y páginas ──
        p, l = _page("Vista y páginas", "view", "mdi:file-document-outline")
        l.addWidget(_bind(QtWidgets.QLabel(), "setText", "Página:")); l.addWidget(self.gp)
        l.addWidget(_bind(QtWidgets.QLabel(), "setText", "Transparencia del PDF:")); l.addWidget(self.gtr)
        l.addStretch(1)

        # ── Sección: Dibujar utilidad ──
        p, l = _page("Dibujar utilidad", "pipe", "mdi:pencil-outline")
        l.addWidget(self.btn_pipe)
        l.addWidget(_bind(QtWidgets.QLabel(), "setText", "Tipo de utilidad:"))
        l.addWidget(self.gt)
        self._slot_gcur_pipe = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_pipe)   # slot: aquí va gcur al dibujar
        l.addStretch(1)

        # ── Sección: Trazar centerline ──
        # Va JUSTO DESPUES de "Dibujar utilidad": las dos son de trazado de
        # geometria, el usuario suele alternarlas y tenerlas contiguas ahorra
        # clics.
        p, l = _page("Trazar centerline", "centerline", "mdi:ruler")
        l.addWidget(self.btn_centerline)
        _lbl_cl = _bind(QtWidgets.QLabel(), "setText", "<i>Clic para agregar vértices, Enter "
            "cierra. Se exporta al DXF en su propia capa.</i>")
        _lbl_cl.setWordWrap(True); l.addWidget(_lbl_cl)
        self._slot_gcur_cl = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_cl)   # slot: gcur al trazar
        l.addStretch(1)

        # ── Sección: Leader (flecha simple) ──
        p, l = _page("Leader (flecha simple)", "leader", "mdi:arrow-decision-outline")
        l.addWidget(self.btn_leader_simple)
        l.addWidget(_bind(QtWidgets.QLabel(), "setText", "Orientación:"))
        self._slot_orient_ld = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_orient_ld)   # slot: orient_combo
        l.addWidget(_bind(QtWidgets.QLabel(), "setText", "<i>El Leader es solo flecha, sin texto.</i>"))
        l.addStretch(1)

        # ── Sección: Texto libre ──
        p, l = _page("Texto libre", "text", "mdi:format-text")
        l.addWidget(self.btn_text)
        self._slot_style_tx = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_style_tx)     # slot: gtxt (estilo)
        l.addStretch(1)

        # ── Sección: Borrar zona ──
        p, l = _page("Borrar zona", "erase", "mdi:vector-rectangle")
        l.addWidget(self.btn_erase)
        _lbl = _bind(QtWidgets.QLabel(), "setText", "<i>Clic para agregar vértices, Enter cierra. "
                                     "Al exportar borra el plano dentro del polígono.</i>")
        _lbl.setWordWrap(True); l.addWidget(_lbl)
        self._slot_gcur_erase = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_erase)  # slot: gcur al borrar
        l.addStretch(1)

        # ── Sección: Mover con precisión ──
        # Panel para desplazar la selección actual (utilidad completa o un
        # vértice puntual) una distancia EXACTA en pies. Cuatro flechas con
        # "paso" en ft para movimientos rápidos, y campos ΔX/ΔY con botón
        # "Aplicar" para desplazamientos arbitrarios. Se habilita/deshabilita
        # en vivo según lo que esté seleccionado en el lienzo (ver _update_move_panel).
        p, l = _page("Mover con precisión", "move_precise", "mdi:cursor-move")
        self._build_move_precise_panel(l)
        l.addStretch(1)

        # ── Sección: Duct Bank ──
        # Abre el diseñador de la sección (envolvente + conductos). El diseño se
        # guarda a nivel proyecto en self.duct_banks. La conexión con una utilidad
        # y el export en DXF/plugin es la fase 2 (pendiente).
        p, l = _page("Duct Bank", "ductbank", "mdi:grid")
        self.btn_ductbank = _bind(WrapButton(), "setText", "Abrir diseñador de Duct Bank", pre='  ')
        self.btn_ductbank.setIconSize(QtCore.QSize(20, 20))
        _bind(self.btn_ductbank, "setToolTip", "Diseña la sección transversal del Duct Bank\n"
                                     "(envolvente rectangular + conductos internos).")
        # Siempre abrir un diseño nuevo desde este botón — no cargar el
        # último editado ni el asignado a la pipe seleccionada (para eso
        # está el panel "Bancoductos" con doble-click / botón Editar).
        self.btn_ductbank.clicked.connect(lambda: self._open_duct_bank_designer(initial=None))
        l.addWidget(self.btn_ductbank)
        _lbl_db = _bind(QtWidgets.QLabel(), "setText", "<i>Dibuja la cara interior del duct bank en pulgadas: primero el "
            "rectángulo del contorno, luego cada conducto redondo dentro.</i>")
        _lbl_db.setWordWrap(True); l.addWidget(_lbl_db)
        self.lbl_ductbank_count = _bind(QtWidgets.QLabel(), "setText", "Duct banks guardados: 0")
        l.addWidget(self.lbl_ductbank_count)
        l.addStretch(1)

        # (Georreferenciación y Cotas/red 3D se hacen una vez por proyecto — se
        #  mueven al menú "Herramientas" y menú "Georreferencia".)

        # Al abrir una sección del acordeón: reparenta los widgets compartidos y
        # regresa el modo a "idle" (así no quedan mezclados los estados).
        self.toolbox.currentChanged.connect(self._on_toolbox_change)

        # RESPONSIVO del dock izquierdo. El ScrollBarAlwaysOff de abajo oculta
        # la barra, pero por sí solo NO evita el desbordamiento: el ancho mínimo
        # del contenido seguía empujando y el texto se recortaba. Las dos causas
        # reales son (a) QLabel sin word-wrap, que reserva todo su ancho en una
        # línea, y (b) QComboBox que pide el ancho de su item más largo.
        # Se recorren TODOS los descendientes del acordeón para no depender de
        # acordarse de cada widget al añadir secciones nuevas.
        for _lb in self.toolbox.findChildren(QtWidgets.QLabel):
            _lb.setWordWrap(True)
        for _cb in self.toolbox.findChildren(QtWidgets.QComboBox):
            # Que el combo pueda encogerse por debajo de su item más largo (el
            # texto completo sigue visible al desplegarlo y en el tooltip).
            _cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            _cb.setMinimumContentsLength(10)
            _cb.view().setTextElideMode(QtCore.Qt.ElideRight)
        # Accesibilidad: los botoncitos de ±/rotación estaban a 30px, por debajo
        # del mínimo cómodo para el usuario principal. Se marcan con la
        # propiedad dinámica `iconOnly` para que el QSS les quite el padding
        # generoso de los botones normales: con `padding: 8px 14px` en un botón
        # de 34px no queda ancho para el glifo y el símbolo se recorta a NADA
        # (los botones salían azules y vacíos).
        for _bt in self.toolbox.findChildren(QtWidgets.QPushButton):
            if 0 < _bt.maximumWidth() <= 40:
                _bt.setProperty("iconOnly", True)
                _bt.setFixedSize(40, 34)            # 40: el glifo ⟲/⟳ pedía 2 px más que 38
            else:
                _bt.setMinimumHeight(32)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.toolbox)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        lv.addWidget(scroll, 1)
        ldock.setWidget(left)
        # 300 (antes 260): la fuente base subió a 14px por accesibilidad.
        ldock.setMinimumWidth(300)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, ldock)
