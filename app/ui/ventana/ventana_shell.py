"""2.0.0 — Estructura de la ventana del rediseño, SIN cambiar ningún widget ni método de antes.

    barra superior · marca (menú Archivo) · proyecto · hoja ◀ ▶ · buscar o ejecutar (Ctrl+K) · deshacer ·
                     Capas · Asistente · tema · Exportar ▾ (versión e idioma de Civil 3D)
    riel           · Dibujar · Hoja y PDF · Inventario · Revisión | Normativas · Tabla · Vista 3D · Duct Bank |
                     Ayuda · Ajustes
    panel del riel · el dock izquierdo de siempre (`_ldock`, se oculta solo) con una página por botón
    centro         · el plano y, dentro de la ventana, Normativas, Tabla de datos y Duct Bank
    derecha        · el panel de propiedades de siempre (`_rdock`) o el Asistente (ventana_asistente.py)

La barra de menús clásica no se muestra: sus acciones (mismos métodos y atajos, `self._acc`) están en la
marca, el riel, los paneles y la paleta Ctrl+K. Una ventana se incrusta en la principal solo si ésta está a
la vista (`_incrustar_ok`); si no (p. ej. pruebas sin pantalla) se abre como antes, en su propia ventana.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from ui.comun import rediseno as R
from ui.ventana import ventana_shell_paneles as PN

# (icono, texto, página del panel | None, qué hace)
RIEL = [("vector-polyline", "Dibujar", 0, None), ("file-pdf-box", "Hoja y PDF", 1, None),
        ("format-list-bulleted", "Inventario", 2, None), ("alert-outline", "Revisión", 3, None),
        None,
        ("playlist-check", "Normativas de diseño", None, "open_normativas"),
        ("table-large", "Tabla de datos", None, "abrir_tabla_datos"),
        ("cube-outline", "Vista 3D", None, "abrir_vista3d"),
        ("chart-bell-curve-cumulative", "Perfil longitudinal", None, "abrir_perfil"),
        ("vector-square", "Diseñador de Duct Bank", None, "_open_duct_bank_designer")]
PAGINAS = ["Dibujar", "Hoja y PDF", "Inventario", "Revisión"]


# ───────────────────────── barra superior ─────────────────────────
def barra_superior_izquierda(win, tb):
    marca = QtWidgets.QToolButton()
    marca.setObjectName("marca")
    marca.setText("P")
    marca.setFixedSize(30, 30)
    _bind(marca, "setToolTip", "Archivo: nuevo, abrir, guardar, cerrar…")
    marca.setPopupMode(QtWidgets.QToolButton.InstantPopup)
    marca.setMenu(win._menu_archivo)
    marca.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
    win._btn_marca = marca
    tb.addWidget(_margen(10))
    tb.addWidget(marca)
    tb.addWidget(_margen(10))
    win.lbl_proyecto = QtWidgets.QLabel()
    win.lbl_proyecto.setProperty("rol", "h3")
    tb.addWidget(win.lbl_proyecto)
    win.lbl_sin_guardar = QtWidgets.QLabel("●")
    _bind(win.lbl_sin_guardar, "setToolTip", "Cambios sin guardar (Ctrl+S)")
    win._acc_sin_guardar = tb.addWidget(win.lbl_sin_guardar)   # en una QToolBar se oculta la ACCIÓN
    tb.addWidget(_margen(8))
    win.btn_hoja_ant = R.boton_icono("chevron-left", "Hoja anterior", lambda: win._prev_page(), px=16)
    win.lbl_hoja_barra = QtWidgets.QLabel()
    win.lbl_hoja_barra.setObjectName("insigniaHoja")
    win.btn_hoja_sig = R.boton_icono("chevron-right", "Hoja siguiente", lambda: win._next_page(), px=16)
    win._acc_hoja = [tb.addWidget(w) for w in (win.btn_hoja_ant, win.lbl_hoja_barra, win.btn_hoja_sig)]
    tb.addWidget(_estirable())
    buscar = R.CampoBuscar("Buscar o ejecutar un comando…", "Ctrl + K")
    buscar.setFixedWidth(360)
    buscar.setReadOnly(True)
    buscar.mousePressEvent = lambda _e: win.abrir_paleta()
    win.campo_buscar = buscar
    tb.addWidget(buscar)
    tb.addWidget(_estirable())


def barra_superior_derecha(win, tb):
    tb.addSeparator()
    win.btn_asistente = QtWidgets.QPushButton()
    _bind(win.btn_asistente, "setText", "Asistente", pre="  ")
    win.btn_asistente.setProperty("soft", True)
    win.btn_asistente.setCheckable(True)
    _bind(win.btn_asistente, "setToolTip", "Asistente IA: preguntas sobre el proyecto, resolver conflictos y "
                                           "«¿Cómo hago…?» (Ctrl+Shift+I)")
    win.btn_asistente.toggled.connect(win.mostrar_asistente)
    tb.addWidget(win.btn_asistente)
    win.btn_tema = R.boton_icono("weather-night", "Modo claro / oscuro", lambda: win._toggle_theme())
    tb.addWidget(win.btn_tema)
    tb.addWidget(_margen(6))
    tb.addWidget(win.btn_export)
    # Los combos de siempre (versión e idioma de Civil 3D) viven fuera de la barra: los muestran, reflejados,
    # «Exportar a Civil 3D» y Ajustes → Civil 3D.
    win._guarda_combos = QtWidgets.QWidget(win)
    guarda = QtWidgets.QFormLayout(win._guarda_combos)
    guarda.addRow(win.cmb_civil)
    guarda.addRow(win.cmb_lang)
    win._guarda_combos.hide()
    tb.addWidget(_margen(10))


def _margen(px):
    w = QtWidgets.QWidget()
    w.setFixedWidth(px)
    w.setStyleSheet("background: transparent;")
    return w


def _estirable():
    w = QtWidgets.QWidget()
    w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
    w.setStyleSheet("background: transparent;")
    return w


class _PilaDelPanel(QtWidgets.QStackedWidget):
    """El ancho preferido del panel izquierdo es el de siempre (el del acordeón, página 0), no el de la
    página más ancha: la ventana arranca con el mismo reparto de anchos que antes."""

    def sizeHint(self):                                # noqa: N802
        return self.widget(0).sizeHint() if self.count() else super().sizeHint()


class ShellMixin:
    # ───────────────────────── armado ─────────────────────────
    def _build_shell(self):
        """Después de los docks de siempre y ANTES de `_build_side_panels` (que toma su contenido)."""
        self._construir_riel()
        # panel izquierdo: el contenido de siempre (acordeón) es la página «Dibujar»
        self.paneles_riel = _PilaDelPanel()
        self.paneles_riel.setObjectName("panelesRiel")
        viejo = self._ldock.widget()
        from ui.ventana import ventana_dibujar
        ventana_dibujar.poner_herramientas(self, viejo)   # cuadrícula de herramientas sobre el acordeón
        self.paneles_riel.addWidget(viejo)
        self.paneles_riel.addWidget(PN.panel_hoja(self))
        from ui.ventana import ventana_inventario
        self.paneles_riel.addWidget(ventana_inventario.panel_inventario(self))
        self.paneles_riel.addWidget(PN.panel_revision(self))
        self._ldock.setWidget(self.paneles_riel)
        # derecha: propiedades de siempre o el Asistente
        from ui.ventana import ventana_asistente
        self.pila_derecha = QtWidgets.QStackedWidget()
        self.pila_derecha.addWidget(self._rdock.widget())
        self.asistente = ventana_asistente.PanelAsistente(self)
        self.pila_derecha.addWidget(self.asistente)
        self._rdock.setWidget(self.pila_derecha)
        from ui.ventana import ventana_inspector
        ventana_inspector.poner_cabecera(self)          # cabecera del inspector (color, nombre, acciones)
        # centro: el plano y las vistas que se abren dentro de la ventana
        self.centro = QtWidgets.QStackedWidget()
        self.centro.setObjectName("centro")
        self.takeCentralWidget()                       # sin esto, setCentralWidget BORRA el lienzo
        self.centro.addWidget(self.canvas)
        self.setCentralWidget(self.centro)
        # la barra de menús clásica se oculta; sus acciones siguen vivas con sus atajos
        mb = self.menuBar()
        for a in self._acciones_de_menu(mb):
            self.addAction(a)
        mb.setVisible(False)
        for k, fn in (("Ctrl+K", self.abrir_paleta), ("Ctrl+Shift+I", lambda: self.mostrar_asistente(True))):
            QtGui.QShortcut(QtGui.QKeySequence(k), self, activated=fn)
        _theme.THEME_BUS.changed.connect(lambda _n: self._estilo_shell())
        self._estilo_shell()
        self._ir_riel(0)
        self._actualizar_barra_superior()
        from ui.ventana import ventana_flotantes      # aviso de conflictos y barra del plano (2.0.0)
        ventana_flotantes.poner(self)

    def _acciones_de_menu(self, _barra=None):
        for menu in self._menus.values():
            yield from R.acciones_de(menu)

    def _construir_riel(self):
        riel = QtWidgets.QToolBar()
        _bind(riel, "setWindowTitle", "Riel")
        riel.setObjectName("riel")
        riel.setMovable(False)
        riel.setFloatable(False)
        riel.setOrientation(QtCore.Qt.Vertical)
        riel.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)
        riel.setIconSize(QtCore.QSize(20, 20))
        self.addToolBar(QtCore.Qt.LeftToolBarArea, riel)
        self._riel = riel
        self._riel_btn = []
        grupo = QtWidgets.QButtonGroup(riel)
        grupo.setExclusive(False)
        for i, item in enumerate(RIEL):
            if item is None:
                riel.addSeparator()
                continue
            ic, tip, pagina, fn = item
            b = R.boton_icono(ic, tip, checkable=pagina is not None, px=20)
            b.setProperty("kind", "rail")
            b.clicked.connect(lambda _=False, k=i: self._ir_riel(k))
            self._riel_btn.append((i, b))
            riel.addWidget(b)
        espacio = QtWidgets.QWidget()
        espacio.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        espacio.setStyleSheet("background: transparent;")
        riel.addWidget(espacio)
        ayuda = R.boton_icono("help-circle-outline", "Ayuda: manual, atajos de teclado, acerca de", px=20)
        ayuda.setProperty("kind", "rail")
        ayuda.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        ayuda.setMenu(self._menus.get("Ayuda") or QtWidgets.QMenu())
        ayuda.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        riel.addWidget(ayuda)
        ajustes = R.boton_icono("cog-outline", "Ajustes: idioma, tema, paneles, asistente IA, familias de Civil 3D",
                                lambda: self.abrir_ajustes(), px=20)
        ajustes.setProperty("kind", "rail")
        riel.addWidget(ajustes)

    def abrir_exportar(self):
        """«Exportar a Civil 3D» (2.0.0): qué incluir, versión e idioma; luego el `run_pipeline` de siempre."""
        from ui.dialogos import exportar_dialog
        exportar_dialog.exportar(self)

    def abrir_ajustes(self, seccion=0):
        """Ajustes (2.0.0): idioma, tema, paneles, Civil 3D, IA, familias, atajos y acerca de."""
        from ui.dialogos import ajustes_dialog
        ajustes_dialog.abrir(self, seccion)

    # ───────────────────────── navegación ─────────────────────────
    def _ir_riel(self, i):
        _ic, _tip, pagina, fn = RIEL[i]
        if pagina is None:
            getattr(self, fn)()
            return
        self.paneles_riel.setCurrentIndex(pagina)
        self._pagina_riel = pagina
        for k, b in self._riel_btn:
            b.setChecked(k == i)
        self._titulo_panel_izq()
        panel = getattr(self, "panel_izq", None)
        if panel is not None and panel.autohide and self.isVisible():
            panel.open()
        self.mostrar_plano()
        self._estilo_shell()

    def _titulo_panel_izq(self):
        panel = getattr(self, "panel_izq", None)
        if panel is None:
            return
        nombre = _tr(PAGINAS[getattr(self, "_pagina_riel", 0)])
        for cab in (panel.dock_header, panel.overlay_header):
            lbl = cab.findChild(QtWidgets.QLabel, "panelHeaderTitle")
            if lbl is not None:
                lbl.setText(nombre)
        panel.tab.setText(nombre)

    def _titulo_panel_der(self):
        panel = getattr(self, "panel_der", None)
        if panel is None or getattr(self, "pila_derecha", None) is None:
            return
        nombre = _tr("Asistente" if self.pila_derecha.currentIndex() == 1 else "Propiedades")
        for cab in (panel.dock_header, panel.overlay_header):
            lbl = cab.findChild(QtWidgets.QLabel, "panelHeaderTitle")
            if lbl is not None:
                lbl.setText(nombre)
        panel.tab.setText(nombre)

    def mostrar_plano(self):
        if getattr(self, "centro", None) is not None:
            self.centro.setCurrentWidget(self.canvas)
        self._paneles_laterales(True)

    def _paneles_laterales(self, ver):
        """Las vistas a pantalla completa (Normativas, Tabla, Duct Bank) ocultan los dos paneles, como el
        prototipo; al volver al plano se ven como estaban (los que se ocultan solos no se tocan)."""
        if ver:
            for dock in getattr(self, "_docks_ocultos", ()):
                dock.show()
            self._docks_ocultos = ()
            return
        ocultos = []
        for panel, dock in ((getattr(self, "panel_izq", None), self._ldock),
                            (getattr(self, "panel_der", None), self._rdock)):
            if panel is not None and panel.autohide:
                if panel.is_open():
                    panel.close()
            elif dock.isVisible():
                dock.hide()
                ocultos.append(dock)
        self._docks_ocultos = tuple(ocultos) + tuple(getattr(self, "_docks_ocultos", ()))

    def abrir_paleta(self):
        from ui.dialogos.paleta_comandos import PaletaComandos
        PaletaComandos(self).exec()

    # ───────────────────────── vistas dentro de la ventana ─────────────────────────
    def _incrustar_ok(self):
        return getattr(self, "centro", None) is not None and self.isVisible()

    def aviso_breve(self, titulo, detalle="", accion=None, tono="ok"):
        """2.0.0: un resultado que no pide decidir nada, como aviso breve abajo a la derecha (se va solo).
        `accion` = (texto, función), p. ej. «Deshacer». Sin la ventana en pantalla (pruebas): el
        mensaje de siempre."""
        if not self._incrustar_ok():
            QtWidgets.QMessageBox.information(self, titulo, "\n".join(x for x in (titulo, detalle) if x)
                                              if detalle else titulo)
            return None
        from ui.comun import aviso_breve
        return aviso_breve.mostrar(self, titulo, detalle, accion, tono)

    def informar(self, titulo, texto):
        """2.0.0: un mensaje informativo (no pregunta nada) como aviso breve; sin la ventana en pantalla
        (pruebas), el cuadro de siempre con los MISMOS argumentos."""
        if not self._incrustar_ok():
            QtWidgets.QMessageBox.information(self, titulo, texto)
            return None
        from ui.comun import aviso_breve
        return aviso_breve.mostrar(self, titulo, texto, None, "info")

    def _abrir_carpeta_de(self, ruta):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.dirname(os.path.abspath(ruta))))

    def incrustar_vista(self, dlg):
        """Una ventana (Normativas, Tabla) pasa a ser una vista del centro. Cerrarla = volver al plano."""
        if not self._incrustar_ok():
            return False
        dlg.setWindowFlags(QtCore.Qt.Widget)
        self.centro.addWidget(dlg)
        dlg.finished.connect(lambda _r: self.mostrar_plano())
        return True

    def mostrar_vista(self, dlg):
        if self.centro.indexOf(dlg) < 0:
            return False
        dlg.show()
        self.centro.setCurrentWidget(dlg)
        self._paneles_laterales(False)
        return True

    def _recoger_panel_izq(self):
        panel = getattr(self, "panel_izq", None)
        if panel is not None and panel.autohide and panel.is_open():
            panel.close()

    def ejecutar_incrustado(self, dlg):
        """Un diálogo MODAL (diseñador de Duct Bank) dentro de la ventana, con el mismo resultado que
        `exec()`: espera a que se acepte o cancele y devuelve el código."""
        if not self._incrustar_ok():
            return dlg.exec()
        dlg.setWindowFlags(QtCore.Qt.Widget)
        self.centro.addWidget(dlg)
        bucle = QtCore.QEventLoop()
        dlg.finished.connect(bucle.quit)
        dlg.show()
        self.centro.setCurrentWidget(dlg)
        self._paneles_laterales(False)
        self._riel.setEnabled(False)
        try:
            bucle.exec()
        finally:
            self._riel.setEnabled(True)
            self.centro.removeWidget(dlg)
            self.mostrar_plano()
        return dlg.result()

    # ───────────────────────── Asistente (derecha) ─────────────────────────
    def mostrar_asistente(self, si, pestana=None):
        si = bool(si)
        if hasattr(self, "btn_asistente"):
            self.btn_asistente.blockSignals(True)
            self.btn_asistente.setChecked(si)
            self.btn_asistente.blockSignals(False)
        if getattr(self, "pila_derecha", None) is None:
            return
        self.pila_derecha.setCurrentIndex(1 if si else 0)
        self._titulo_panel_der()
        if si:
            self.asistente.preparar(pestana)
            panel = getattr(self, "panel_der", None)
            if panel is not None and panel.autohide and self.isVisible():
                panel.open()
            if not self._rdock.isVisible() and not (panel is not None and panel.autohide):
                self._rdock.show()

    # ───────────────────────── estado de la barra superior ─────────────────────────
    def _actualizar_barra_superior(self):
        if not hasattr(self, "lbl_proyecto"):
            return
        if self.project_path:
            nombre = os.path.splitext(os.path.basename(self.project_path))[0]
        elif getattr(self, "pdf_path", None):
            nombre = os.path.basename(self.pdf_path)
        else:
            nombre = _tr("Proyecto sin nombre")
        self.lbl_proyecto.setText(nombre)
        self._acc_sin_guardar.setVisible(bool(getattr(self, "_dirty", False)))
        doc = getattr(self, "doc", None)
        hay = doc is not None and doc.page_count > 1
        for a in self._acc_hoja:
            a.setVisible(False)          # 2026-10-28: sin cambio de hoja en la barra (pedido del usuario)
        if hay:
            self.lbl_hoja_barra.setText(_tr("Hoja {n} de {m}").format(n=self.page_idx + 1, m=doc.page_count))
            self.btn_hoja_ant.setEnabled(self.page_idx > 0)
            self.btn_hoja_sig.setEnabled(self.page_idx < doc.page_count - 1)
        if getattr(self, "panel_hoja", None) is not None:
            self.panel_hoja.refrescar()

    def _estilo_shell(self):
        t = _theme.tokens()
        if hasattr(self, "_btn_marca"):
            self._btn_marca.setStyleSheet(
                f"QToolButton#marca {{ background:{t.accent}; color:{t.text_on_accent}; border-radius:8px;"
                f" font-weight:700; font-size:15px; }} QToolButton#marca:hover {{ background:{t.accent_hover}; }}"
                " QToolButton#marca::menu-indicator { image: none; width: 0; }")
        if hasattr(self, "lbl_sin_guardar"):
            self.lbl_sin_guardar.setStyleSheet(f"color:{t.warning}; font-size:11px;")
            self.lbl_hoja_barra.setStyleSheet(f"QLabel#insigniaHoja {{ background:{t.surface_alt}; color:{t.text_muted};"
                                              f" border-radius:9px; padding:1px 8px; font-size:12px; }}")
            self.btn_tema.setIcon(_icon("mdi:white-balance-sunny" if _theme.is_dark() else "mdi:weather-night"))
            self.btn_asistente.setIcon(_icon("mdi:creation", color=t.soft_text))
        for _k, b in getattr(self, "_riel_btn", []):
            b.setIcon(_icon("mdi:" + b._icono, color=t.accent if b.isChecked() else t.text_muted))
        if hasattr(self, "_tb"):
            self._tb.setStyleSheet(f"QToolBar#barraSuperior {{ background:{t.surface}; border:none;"
                                   f" border-bottom:1px solid {t.border_soft}; padding:9px 0; spacing:6px; }}")
        if hasattr(self, "_riel"):
            self._riel.setStyleSheet(f"QToolBar#riel {{ background:{t.surface}; border:none;"
                                     f" border-right:1px solid {t.border_soft}; padding:10px 8px; spacing:6px; }}")
