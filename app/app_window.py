"""
marcar_utilidades.py — Digitalizar planos y marcar utilidades.

App de escritorio (PySide6) para ingeniería civil: abre el PDF de un plano,
marca utilidades, coloca Leaders (flechas), escribe texto libre,
borra zonas y exporta un único DXF (base digitalizada + tu marcado) en las
mismas coordenadas. Ver menú Ayuda → Manual de usuario.
"""
import sys, os, copy, math, json, zipfile
import fitz
import numpy as np
import ezdxf
from PySide6 import QtCore, QtGui, QtWidgets

import config as C
import vector_pipeline as VP
import geometry as G
import dxf_export
from geo import georef as georef_mod
from geometry import qimage_to_gray
# Clases de UI extraídas a módulos propios (mismo comportamiento, ver plan de
# arquitectura). El lienzo, los widgets reutilizables y el worker de fondo.
from canvas import Canvas
from widgets import InlineEdit, _SegInvSpinBox, _NoWheelFilter
from workers import PipelineWorker, RecognitionWorker, OrganizedRecognitionWorker
import dialogs
import recognition_dialog
import sheet_layout_dialog
import organized_layer_dialog
import organized_recognition_dialog
from organized_layers import selected_sheets
from sheet_layout import normalize as normalize_sheet_layout, normalize_rotations
from sheet_crops import normalize as normalize_sheet_crops
import layer_dialog
import composite as composite_mod
import composite_dialog
import project_io
import model_ops
from model import (VERSION, TIPOS, ACI_RGB, LEADER_TEXT_FT, LEADER_ORIENT,
                   Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE, GRAVITY_LAYERS,
                   TAB_PIPE, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ, TAB_CURVE, TAB_CL,
                   TAB_DB,
                   WORK_UNITS, DEFAULT_WORK_UNIT, CHANGELOG,
                   PIPE_DIAMETERS_IN, PIPE_MATERIALS, DEFAULT_PIPE_MATERIAL)

# Constantes y helpers de UI compartidos (antes definidos aquí) → ui_common.py.
from ui_common import (DOWNLOADS, btn_on_style, btn_off_style, aci_qcolor, layer_qcolor,
                       _extract_diam_from_size, swatch_icon)
import theme as _theme
import i18n as _i18n
from i18n import t as _tr
from icons import icon as _icon


class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._base_title = f"Asistente C3D  (v{VERSION})"
        self.setWindowTitle(self._base_title); self.resize(1480, 940)
        self.setAcceptDrops(True)
        self.canvas = Canvas(self); self.canvas.clicked.connect(self.on_click)
        self.canvas.dbl.connect(self.on_dblclick); self.setCentralWidget(self.canvas)
        self.zoom = 3.5; self.scale = 20 / 72.0; self.rot = 0; self.W = 0; self.H = 0
        self.derot = fitz.Matrix(1, 0, 0, 1, 0, 0); self.gray = None; self.page_idx = 0; self.pageH_px = 0
        self.hidden_ocgs = []   # capas OCG ocultas en el paso «Capas de la hoja» (por PDF abierto)
        self.hidden_ocgs_by_source = {}  # selección de capas por PDF de la organización
        self._layer_roles_by_utility = {}  # roles OCG manuales separados por utilidad
        self._recognition_utilities = ("ELECTRICO", "DRENAJE")
        self._join_routes = True   # unir tramos de la misma capa en rutas (desactivable en el preview)
        self._recog_ready = False  # True cuando el asistente ya reconoció una hoja de este PDF (◀ ▶ vuelven a reconocer)
        self.sheet_layout = None  # hoja principal y vecinas del PDF; índices 0-based
        self.sheet_rotations = {}  # giros de vista por posición, múltiplos de 90°
        self.sheet_crops = {}  # ventana no destructiva del plano por posición
        self.sheet_sources = []   # nombre y rango virtual de páginas de cada PDF
        self.sheet_external_pdfs = []  # PDF externos completos, con capas originales
        # Hoja compuesta (composite.py): PDFs de origen en memoria, piezas y la
        # escala única de la hoja. `work_pdf_path` es el PDF que ven los workers
        # (el compuesto temporal o el original); `pdf_path` sigue siendo el original.
        self.src_pdfs = []        # [{name, data(bytes), path?}, …]; 0 = PDF principal
        self.composite = None     # composite.Composite o None
        self.work_pdf_path = None
        self._scale_override = None  # escala de la hoja compuesta (pies/pt); None = detectar
        self._tmp_composite = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.leader_hpx = 40

        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.ref_centerlines = []; self._cl_pts = []
        self.duct_banks = []   # colección del proyecto — ver duct_bank.py
        self.cross_connections = []   # conexiones aprobadas en cruces físicos
        self.mode = "idle"; self._pending = None
        self.snap = False; self.snap_r = 14
        self.sel_pipe = -1; self.sel_leader = -1; self.sel_region = -1; self.sel_text = -1; self.sel_bz = -1
        self.sel_curve = -1; self.sel_cl = -1; self.sel_db = -1; self._bz_rows = []; self._curve_rows = []
        self.sel_seg_idx = -1            # tramo resaltado en la tabla "Cotas por tramo"
        self._no_center = False; self._crosshair = []
        self._move0 = None; self._drag_vertex = None; self._edit_pts = None; self._edit_closed = False; self._edit_leader = None
        self._move_kind = None; self._moved = False; self._press_xy = None; self._last_xy = None
        self._extending = False; self._ext_layer = None; self._ext_pipe = None; self._ext_at = None
        self._editor = None; self._undo, self._redo, self._overlay = [], [], []
        self._dirty = False; self._style_guard = False; self._prop_guard = False; self._clip = None
        self.georef = georef_mod.Georef()          # georreferenciación (píxel→UTM); inactiva por defecto
        self.work_unit = DEFAULT_WORK_UNIT          # unidad de trabajo del proyecto: 'ft' o 'in' (obligatoria)
        self.show_bz_labels = False                # ¿dibujar el código del buzón al lado del círculo?
        # Detectar versiones de Civil 3D instaladas para escanear su catálogo imperial.
        # civil_year = None si no hay ninguna (se usa igual sin dropdown de familias).
        import civil_catalog as _cc
        _vs = _cc.installed_versions()
        self.civil_year = _vs[-1] if _vs else None
        self._build_ui(); self._apply_style(); self._shortcuts(); self._update_ui()
        # Re-aplica estilos custom con los tokens del tema activo, y se reconecta
        # al bus para reaccionar cuando el usuario alterne claro↔oscuro.
        self._apply_theme_custom_styles()
        _theme.THEME_BUS.changed.connect(self._apply_theme_custom_styles)

    # ─────────────────────────── UI ───────────────────────────
    def _build_ui(self):
        # La UI se arma por secciones, en este ORDEN (importante: los widgets
        # compartidos del acordeón se reubican al final, cuando ya existen los
        # del dock derecho). Cada _build_* deja sus widgets como self.* .
        self._build_menu()
        self._build_toolbar()
        self._build_left_dock()
        self._build_right_dock()
        self._build_statusbar()
        # Todo listo: coloca los widgets compartidos del acordeón en la sección
        # inicial (esto necesita que self.tabs, self.gprop y self.lbl_mode existan).
        self._on_toolbox_change(self.toolbox.currentIndex())
        self._refresh_unit_labels()                # etiquetas de campo con la unidad activa

    def _build_menu(self):
        mb = self.menuBar()
        # Guardamos referencias a menús + acciones traducibles para poder
        # retranslatarlas en vivo cuando cambia el idioma (_retranslate_menu).
        self._i18n_menus = []   # lista de (menu, clave_es_original)
        self._i18n_actions = []  # lista de (action, clave_es_original)

        def _menu(parent_bar, label_es):
            m = parent_bar.addMenu(_tr(label_es))
            self._i18n_menus.append((m, label_es))
            return m

        def _act(menu, label_es, fn, shortcut=None):
            a = self._menu_act(menu, _tr(label_es), fn, shortcut)
            self._i18n_actions.append((a, label_es))
            return a

        mfile = _menu(mb, "&Archivo")
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
        mview = _menu(mb, "&Ver")
        _act(mview, "Componer hoja de trabajo…", self.compose_sheet)
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
        self.chk_show_conflicts = QtGui.QAction(_tr("Mostrar cruces/conflictos"), self)
        self.chk_show_conflicts.setCheckable(True)
        try:
            _sc_pref = QtCore.QSettings("pdf-to-cad", "app").value("show_conflicts_v2", False, type=bool)
        except Exception:
            _sc_pref = False
        self.chk_show_conflicts.setChecked(bool(_sc_pref))
        self.chk_show_conflicts.setToolTip(_tr(
            "Marca los puntos donde dos utilidades se cruzan geométricamente en el plano.\n"
            "  · Amarillo ⓘ: cruce sano (distinta cota, se pasan por encima/debajo).\n"
            "  · Rojo ⚠: conflicto (misma cota o sin cota → chocan).\n"
            "Apagarlo oculta las marcas y el contador de la barra de estado."))
        self.chk_show_conflicts.toggled.connect(self._on_toggle_show_conflicts)
        mview.addAction(self.chk_show_conflicts)
        self._i18n_actions.append((self.chk_show_conflicts, "Mostrar cruces/conflictos"))
        mtools = _menu(mb, "&Herramientas")
        _act(mtools, "Insertar buzón en línea…", self.insert_manhole)
        _act(mtools, "Instalar familia personalizada…", self.open_install_family_dialog)
        _act(mtools, "Desinstalar familia personalizada…", self.open_uninstall_family_dialog)
        mtools.addSeparator()
        _act(mtools, "Georreferenciar…", self.open_georef)
        _act(mtools, "Quitar georreferencia", self.clear_georef)
        mhelp = _menu(mb, "A&yuda")
        _act(mhelp, "Acerca de…", self.show_about)
        _act(mhelp, "Manual de usuario", self.show_manual)
        _act(mhelp, "Atajos de teclado", self.show_shortcuts)
        # Cuando el idioma cambie en vivo (desde Opciones…), retraducimos menús
        # y otros textos suscritos.
        _i18n.LANG_BUS.changed.connect(self._retranslate_ui)

    def _retranslate_ui(self, *_):
        """Actualiza los textos de la UI cuando cambia el idioma. Solo toca los
        widgets que registramos como traducibles — sin recrear la ventana.

        Nota: hay muchos textos hardcodeados repartidos por la UI (labels
        puntuales, tooltips, mensajes) que no viven en esta lista. Esos se
        aplicarán la próxima vez que se abra la ventana correspondiente."""
        for m, key in getattr(self, "_i18n_menus", []):
            try: m.setTitle(_tr(key))
            except Exception: pass
        for a, key in getattr(self, "_i18n_actions", []):
            try: a.setText(_tr(key))
            except Exception: pass
        # Título de la ventana (por si contiene texto traducible)
        try: self._update_title()
        except Exception: pass
        # Refrescar título del theme action
        try: self._refresh_theme_action_label()
        except Exception: pass
        # Docks: título del dock derecho ("Inventario")
        try:
            for dock in self.findChildren(QtWidgets.QDockWidget):
                # Guardamos la clave original en una propiedad dinámica al construir
                key = dock.property("i18n_key")
                if key: dock.setWindowTitle(_tr(key))
        except Exception: pass
        # Tabs del inventario
        try:
            if hasattr(self, "tabs"):
                labels_es = ["Utilidades", "Leaders", "Textos", "Zonas",
                              "Buzones", "Curvas", "Centerlines", "Bancoductos"]
                for i, es in enumerate(labels_es):
                    if i < self.tabs.count():
                        self.tabs.setTabText(i, _tr(es))
                # y el combo que refleja los tabs
                if hasattr(self, "tab_combo"):
                    self.tab_combo.blockSignals(True)
                    for i in range(min(self.tab_combo.count(), len(labels_es))):
                        self.tab_combo.setItemText(i, _tr(labels_es[i]))
                    self.tab_combo.blockSignals(False)
        except Exception: pass
        # Botones del panel de bancoductos
        try:
            if hasattr(self, "btn_db_new"): self.btn_db_new.setText(_tr("+ Nuevo"))
            if hasattr(self, "btn_db_edit"): self.btn_db_edit.setText(_tr("Editar"))
            if hasattr(self, "btn_db_dup"): self.btn_db_dup.setText(_tr("Duplicar"))
            # Toolbar principal
            if hasattr(self, "btn_export"): self.btn_export.setText(_tr("  Exportar DXF"))
            # Toolbox (dock izquierdo) — botones de las secciones
            if hasattr(self, "btn_pipe"): self.btn_pipe.setText("  " + _tr("Dibujar utilidad"))
            if hasattr(self, "btn_leader_simple"): self.btn_leader_simple.setText("  " + _tr("Colocar Leader"))
            if hasattr(self, "btn_text"): self.btn_text.setText("  " + _tr("Texto libre"))
            if hasattr(self, "btn_erase"): self.btn_erase.setText("  " + _tr("Borrar zona"))
            if hasattr(self, "btn_centerline"): self.btn_centerline.setText("  " + _tr("Trazar centerline"))
            if hasattr(self, "btn_ductbank"):
                self.btn_ductbank.setText("  " + _tr("Abrir diseñador de Duct Bank"))
            if hasattr(self, "lbl_ductbank_count"):
                self.lbl_ductbank_count.setText(_tr("Duct banks guardados: 0"))
            if hasattr(self, "chk_ab"): self.chk_ab.setText(_tr("Abandonado"))
            if hasattr(self, "chk_ext_same"): self.chk_ext_same.setText(_tr("Extender: continuar la misma"))
            # Panel de propiedades
            if hasattr(self, "lbl_prop_inv0"): self.lbl_prop_inv0.setText(_tr("Elev. de rasante inicial (ft):"))
            if hasattr(self, "lbl_prop_inv1"): self.lbl_prop_inv1.setText(_tr("Elev. de rasante final (ft):"))
            if hasattr(self, "lbl_prop_family"): self.lbl_prop_family.setText(_tr("Familia (catálogo):"))
            if hasattr(self, "lbl_prop_size"): self.lbl_prop_size.setText(_tr("Tamaño (catálogo):"))
            # Botones del panel derecho (bajo la lista)
            if hasattr(self, "btn_ct"): self.btn_ct.setText(_tr("Cambiar tipo"))
            if hasattr(self, "btn_mv"): self.btn_mv.setText(_tr("Editar/mover"))
            if hasattr(self, "btn_edit"): self.btn_edit.setText(_tr("Editar texto"))
            if hasattr(self, "btn_del"): self.btn_del.setText(_tr("Eliminar"))
            # Toolbox: títulos de las secciones (leyendo del combo lang porque el
            # acordeón guarda el label real). Los redraws de _page los reemplazan
            # solo si se reabre; por eso los actualizamos aquí:
            if hasattr(self, "toolbox"):
                sec_labels = [_tr("Vista y páginas"), _tr("Dibujar utilidad"),
                              _tr("Trazar centerline"), _tr("Leader (flecha simple)"),
                              _tr("Texto libre"), _tr("Borrar zona"), _tr("Duct Bank")]
                for i, lbl in enumerate(sec_labels):
                    if i < self.toolbox.count():
                        self.toolbox.setItemText(i, lbl)
            # Barra de estado
            if hasattr(self, "lbl_mode"): self.lbl_mode.setText(_tr("Modo: inactivo"))
            if hasattr(self, "btn_opacity"): self.btn_opacity.setText("  " + _tr("Opacidad"))
            self._update_geo_status()   # refresca "Georref: ..."
            if hasattr(self, "_refresh_scale_label"):
                self._refresh_scale_label()  # refresca "Escala ..."
        except Exception: pass
        # Refrescar la lista de bancoductos (incluye tooltips traducibles)
        try:
            if hasattr(self, "_refresh_db_list"):
                self._refresh_db_list()
        except Exception: pass

    def show_options(self):
        """Delegador al diálogo de opciones (dialogs.show_options)."""
        import dialogs as _dlg
        _dlg.show_options(self)

    def _build_toolbar(self):
        # ── Barra de acción superior: zoom · deshacer/rehacer · imán · exportar ──
        tb = self.addToolBar("Acciones"); tb.setMovable(False)
        # Los QAction llevan QIcon SVG; guardamos el mapa acción→nombre para
        # que _apply_theme_custom_styles pueda retintarlos al cambiar tema.
        self._action_icon_map = {}
        def tact(icon_name, tip, fn):
            a = QtGui.QAction("", self); a.setToolTip(tip); a.triggered.connect(fn)
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
        tb.addWidget(QtWidgets.QLabel("Civil 3D:"))
        self.cmb_civil = QtWidgets.QComboBox()
        import civil_catalog as _cc
        _all_years = list(_cc.SUPPORTED_YEARS); _inst = set(_cc.installed_versions())
        for y in _all_years:
            self.cmb_civil.addItem(f"{y}{'' if y in _inst else '  ' + _tr('(no instalado)')}", y)
        if self.civil_year is not None:
            i = _all_years.index(self.civil_year); self.cmb_civil.setCurrentIndex(i)
        self.cmb_civil.currentIndexChanged.connect(self._on_civil_year_changed)
        self.cmb_civil.setToolTip(_tr("Versión de Civil 3D. El catálogo imperial se busca en\n"
                                  "C:\\ProgramData\\Autodesk\\C3D <año>\\<idioma>\\Pipes Catalog\\US Imperial Structures"))
        tb.addWidget(self.cmb_civil)
        # Selector de idioma del catálogo — se puebla dinámicamente al elegir año.
        # Si el cliente tiene tanto 'esp' como 'enu' instalados, puede elegir
        # cuál usar para la instalación de familias custom y el listado.
        tb.addWidget(QtWidgets.QLabel(_tr("Idioma:")))
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.setToolTip(_tr("Idioma del catálogo Civil 3D a usar (subcarpeta esp/enu/etc.)"))
        self.cmb_lang.currentIndexChanged.connect(self._on_civil_lang_changed)
        tb.addWidget(self.cmb_lang)
        # Poblamos el combo de idiomas por primera vez con la versión activa.
        self._refill_lang_combo()
        tb.addSeparator()
        self.btn_export = QtWidgets.QPushButton(_tr("  Exportar DXF"))
        self.btn_export.setIconSize(QtCore.QSize(18, 18))
        self.btn_export.clicked.connect(lambda: self.run_pipeline("todo"))
        tb.addWidget(self.btn_export)

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
        ldock = QtWidgets.QDockWidget(_tr("Herramientas"), self)
        ldock.setProperty("i18n_key", "Herramientas")   # para _retranslate_ui
        ldock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)     # no se puede sacar/flotar
        left = QtWidgets.QWidget(); lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QtWidgets.QToolBox()
        # Guardamos por NOMBRE el índice de cada sección para poder abrirla desde código.
        self._sec_idx = {}
        # Mapa clave→nombre de icono para retintar los tabs en cambios de tema.
        self._toolbox_icons = {}

        # ── Helper de creación: crea una página del toolbox con su layout vertical ──
        def _page(title, key, icon_name=None):
            page = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(page); lay.setSpacing(6)
            self.toolbox.addItem(page, title)
            idx = self.toolbox.count() - 1
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
        self.page_edit.setToolTip(_tr("Escribe un número de página y pulsa Enter"))
        # returnPressed = Enter en un QLineEdit; editingFinished = perdió el foco también
        self.page_edit.returnPressed.connect(self._goto_page_edit)
        self.page_edit.editingFinished.connect(self._goto_page_edit)
        self.lbl_page = QtWidgets.QLabel(" / — ")
        lp.addWidget(self.btn_prev); lp.addWidget(self.page_edit, 1); lp.addWidget(self.lbl_page); lp.addWidget(self.btn_next)

        # Fila de transparencia del PDF de fondo (para ver mejor el marcado encima)
        self.gtr = QtWidgets.QWidget(); ltr = QtWidgets.QHBoxLayout(self.gtr); ltr.setContentsMargins(0, 0, 0, 0)
        tb_l = QtWidgets.QPushButton("−"); tb_l.setFixedSize(38, 34); tb_l.setProperty("iconOnly", True); tb_l.setToolTip(_tr("Más translúcido")); tb_l.clicked.connect(lambda: self._bump_opacity(-10))
        self.lbl_opacity = QtWidgets.QLabel("100%"); self.lbl_opacity.setAlignment(QtCore.Qt.AlignCenter)
        tb_r = QtWidgets.QPushButton("+"); tb_r.setFixedSize(38, 34); tb_r.setProperty("iconOnly", True); tb_r.setToolTip(_tr("Más opaco")); tb_r.clicked.connect(lambda: self._bump_opacity(10))
        ltr.addWidget(tb_l); ltr.addWidget(self.lbl_opacity, 1); ltr.addWidget(tb_r)

        # Botones de acción (uno por sección; el color verde/azul lo pone _update_ui)
        self.btn_pipe = QtWidgets.QPushButton("  " + _tr("Dibujar utilidad")); self.btn_pipe.clicked.connect(self.toggle_pipe)
        self.btn_leader_simple = QtWidgets.QPushButton("  " + _tr("Colocar Leader")); self.btn_leader_simple.clicked.connect(lambda: self.start_leader(True))
        self.btn_text = QtWidgets.QPushButton("  " + _tr("Texto libre")); self.btn_text.clicked.connect(self.toggle_text_mode)
        self.btn_erase = QtWidgets.QPushButton("  " + _tr("Borrar zona")); self.btn_erase.clicked.connect(self.toggle_erase)
        self.btn_centerline = QtWidgets.QPushButton("  " + _tr("Trazar centerline")); self.btn_centerline.clicked.connect(self.toggle_centerline)
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
            self.type_combo.addItem(swatch_icon(layer_qcolor(layer)), _tr(label), layer)
        self.type_combo.setCurrentIndex(0); self.type_combo.currentIndexChanged.connect(lambda _: self._redraw())
        # Etiquetas CORTAS a propósito: QCheckBox no hace word-wrap, así que un
        # texto largo impone un ancho mínimo que saca barra horizontal en el
        # dock. El detalle completo va al tooltip — y de paso se lee más fácil,
        # que es lo que necesita el usuario principal.
        self.chk_ab = QtWidgets.QCheckBox(_tr("Abandonado"))
        self.chk_ab.setToolTip(_tr("Marca la utilidad como abandonada: se dibuja con "
                               "línea discontinua ──/── W ── en el DXF."))
        self.chk_ext_same = QtWidgets.QCheckBox(_tr("Extender: continuar la misma"))
        self.chk_ext_same.setToolTip(_tr(
            "Al extender un extremo de una utilidad existente, los puntos nuevos "
            "se añaden a ESA misma utilidad en vez de crear una nueva."))
        self.chk_ext_same.setChecked(True)
        lgt.addWidget(self.type_combo); lgt.addWidget(self.chk_ab); lgt.addWidget(self.chk_ext_same)

        # Combo de ORIENTACIÓN del Leader.
        self.orient_combo = QtWidgets.QComboBox()
        for oid, lbl in LEADER_ORIENT: self.orient_combo.addItem(_tr(lbl), oid)
        self.orient_combo.currentIndexChanged.connect(lambda _: self._update_ui())

        # Grupo "Estilo de texto" (fuente, altura, negrita + rotación).
        # COMPARTIDO por Leader y Texto libre. La rotación solo aplica a
        # textos libres; la mostramos/ocultamos según la sección abierta.
        self.gtxt = QtWidgets.QGroupBox(_tr("Estilo de texto")); lgx = QtWidgets.QVBoxLayout(self.gtxt)
        # QFontComboBox = combo que lista todas las fuentes instaladas en el sistema.
        self.font_combo = QtWidgets.QFontComboBox(); self.font_combo.setCurrentFont(QtGui.QFont(C.TEXT_FONT))
        self.font_combo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.font_combo.currentFontChanged.connect(lambda _: self._style_changed())
        r = QtWidgets.QHBoxLayout(); r.addWidget(QtWidgets.QLabel("Altura (pies):"))
        b_minus = QtWidgets.QPushButton("−"); b_minus.setFixedSize(38, 34); b_minus.setProperty("iconOnly", True); b_minus.clicked.connect(lambda: self._bump_size(-0.5))
        # QDoubleSpinBox = campo numérico decimal con incremento por flechas (aquí ocultas).
        self.size_spin = QtWidgets.QDoubleSpinBox(); self.size_spin.setRange(0.5, 200); self.size_spin.setValue(3.0)
        self.size_spin.setSingleStep(0.5); self.size_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.size_spin.valueChanged.connect(lambda _: self._style_changed())
        b_plus = QtWidgets.QPushButton("+"); b_plus.setFixedSize(38, 34); b_plus.setProperty("iconOnly", True); b_plus.clicked.connect(lambda: self._bump_size(0.5))
        r.addWidget(b_minus); r.addWidget(self.size_spin); r.addWidget(b_plus)
        self.chk_bold = QtWidgets.QCheckBox("Negrita"); self.chk_bold.toggled.connect(lambda _: self._style_changed())
        lgx.addWidget(self.font_combo); lgx.addLayout(r); lgx.addWidget(self.chk_bold)
        # Rotación (0-360°) — solo se usa para textos libres.
        self.rot_row = QtWidgets.QWidget(); rr2 = QtWidgets.QHBoxLayout(self.rot_row); rr2.setContentsMargins(0, 0, 0, 0)
        rr2.addWidget(QtWidgets.QLabel("Rotación (°):"))
        rb_l = QtWidgets.QPushButton("⟲"); rb_l.setFixedSize(38, 34); rb_l.setProperty("iconOnly", True); rb_l.clicked.connect(lambda: self._bump_rot(-1))
        self.rot_spin = QtWidgets.QSpinBox(); self.rot_spin.setRange(0, 360); self.rot_spin.setSingleStep(1); self.rot_spin.setWrapping(True)
        self.rot_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons); self.rot_spin.valueChanged.connect(lambda _: self._style_changed())
        rb_r = QtWidgets.QPushButton("⟳"); rb_r.setFixedSize(38, 34); rb_r.setProperty("iconOnly", True); rb_r.clicked.connect(lambda: self._bump_rot(1))
        rr2.addWidget(rb_l); rr2.addWidget(self.rot_spin); rr2.addWidget(rb_r)
        lgx.addWidget(self.rot_row)
        lgx.addWidget(QtWidgets.QLabel("<i>Guarda pulsando enter </i>"))

        # Grupo "En curso" (aparece cuando estás dibujando una utilidad o zona)
        self.gcur = QtWidgets.QGroupBox("En curso"); lc = QtWidgets.QHBoxLayout(self.gcur)
        self.btn_fin = QtWidgets.QPushButton("Finalizar (Enter)"); self.btn_fin.clicked.connect(self._on_enter)
        b_up = QtWidgets.QPushButton("Deshacer punto"); b_up.clicked.connect(self.undo)
        lc.addWidget(self.btn_fin); lc.addWidget(b_up)

        # ═══════════════════════════════════════════════════════════════════════
        # AHORA: creamos las secciones del acordeón y colocamos los widgets.
        # Los "slots" (self._slot_*) son QVBoxLayouts vacíos que quedan reservados
        # dentro de cada página para recibir los widgets compartidos por reparent.
        # ═══════════════════════════════════════════════════════════════════════

        # ── Sección: Vista y páginas ──
        p, l = _page(_tr("Vista y páginas"), "view", "mdi:file-document-outline")
        l.addWidget(QtWidgets.QLabel(_tr("Página:"))); l.addWidget(self.gp)
        l.addWidget(QtWidgets.QLabel(_tr("Transparencia del PDF:"))); l.addWidget(self.gtr)
        l.addStretch(1)

        # ── Sección: Dibujar utilidad ──
        p, l = _page(_tr("Dibujar utilidad"), "pipe", "mdi:pencil-outline")
        l.addWidget(self.btn_pipe)
        l.addWidget(QtWidgets.QLabel(_tr("Tipo de utilidad:")))
        l.addWidget(self.gt)
        self._slot_gcur_pipe = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_pipe)   # slot: aquí va gcur al dibujar
        l.addStretch(1)

        # ── Sección: Trazar centerline ──
        # Va JUSTO DESPUES de "Dibujar utilidad": las dos son de trazado de
        # geometria, el usuario suele alternarlas y tenerlas contiguas ahorra
        # clics.
        p, l = _page(_tr("Trazar centerline"), "centerline", "mdi:ruler")
        l.addWidget(self.btn_centerline)
        _lbl_cl = QtWidgets.QLabel(_tr(
            "<i>Clic para agregar vértices, Enter "
            "cierra. Se exporta al DXF en su propia capa.</i>"))
        _lbl_cl.setWordWrap(True); l.addWidget(_lbl_cl)
        self._slot_gcur_cl = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_cl)   # slot: gcur al trazar
        l.addStretch(1)

        # ── Sección: Leader (flecha simple) ──
        p, l = _page(_tr("Leader (flecha simple)"), "leader", "mdi:arrow-decision-outline")
        l.addWidget(self.btn_leader_simple)
        l.addWidget(QtWidgets.QLabel(_tr("Orientación:")))
        self._slot_orient_ld = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_orient_ld)   # slot: orient_combo
        l.addWidget(QtWidgets.QLabel(_tr("<i>El Leader es solo flecha, sin texto.</i>")))
        l.addStretch(1)

        # ── Sección: Texto libre ──
        p, l = _page(_tr("Texto libre"), "text", "mdi:format-text")
        l.addWidget(self.btn_text)
        self._slot_style_tx = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_style_tx)     # slot: gtxt (estilo)
        l.addStretch(1)

        # ── Sección: Borrar zona ──
        p, l = _page(_tr("Borrar zona"), "erase", "mdi:vector-rectangle")
        l.addWidget(self.btn_erase)
        _lbl = QtWidgets.QLabel(_tr("<i>Clic para agregar vértices, Enter cierra. "
                                     "Al exportar borra el plano dentro del polígono.</i>"))
        _lbl.setWordWrap(True); l.addWidget(_lbl)
        self._slot_gcur_erase = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_erase)  # slot: gcur al borrar
        l.addStretch(1)

        # ── Sección: Mover con precisión ──
        # Panel para desplazar la selección actual (utilidad completa o un
        # vértice puntual) una distancia EXACTA en pies. Cuatro flechas con
        # "paso" en ft para movimientos rápidos, y campos ΔX/ΔY con botón
        # "Aplicar" para desplazamientos arbitrarios. Se habilita/deshabilita
        # en vivo según lo que esté seleccionado en el lienzo (ver _update_move_panel).
        p, l = _page(_tr("Mover con precisión"), "move_precise", "mdi:cursor-move")
        self._build_move_precise_panel(l)
        l.addStretch(1)

        # ── Sección: Duct Bank ──
        # Abre el diseñador de la sección (envolvente + conductos). El diseño se
        # guarda a nivel proyecto en self.duct_banks. La conexión con una utilidad
        # y el export en DXF/plugin es la fase 2 (pendiente).
        p, l = _page(_tr("Duct Bank"), "ductbank", "mdi:grid")
        self.btn_ductbank = QtWidgets.QPushButton(_tr("  Abrir diseñador de Duct Bank"))
        self.btn_ductbank.setIconSize(QtCore.QSize(20, 20))
        self.btn_ductbank.setToolTip(_tr("Diseña la sección transversal del Duct Bank\n"
                                     "(envolvente rectangular + conductos internos)."))
        # Siempre abrir un diseño nuevo desde este botón — no cargar el
        # último editado ni el asignado a la pipe seleccionada (para eso
        # está el panel "Bancoductos" con doble-click / botón Editar).
        self.btn_ductbank.clicked.connect(lambda: self._open_duct_bank_designer(initial=None))
        l.addWidget(self.btn_ductbank)
        _lbl_db = QtWidgets.QLabel(_tr(
            "<i>Dibuja la cara interior del duct bank en pulgadas: primero el "
            "rectángulo del contorno, luego cada conducto redondo dentro.</i>"))
        _lbl_db.setWordWrap(True); l.addWidget(_lbl_db)
        self.lbl_ductbank_count = QtWidgets.QLabel(_tr("Duct banks guardados: 0"))
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
                _bt.setFixedSize(38, 34)
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

    def _build_right_dock(self):
        # ── DOCK DERECHO: inventario y selección ──
        rdock = QtWidgets.QDockWidget(_tr("Inventario"), self); rdock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        rdock.setProperty("i18n_key", "Inventario")   # para _retranslate_ui
        right = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(right)
        self.tabs = QtWidgets.QTabWidget()
        self.pipe_list = QtWidgets.QListWidget(); self.pipe_list.currentRowChanged.connect(self._sel_pipe)
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
        _dbv.addWidget(self.db_list, 1)
        _dbbar = QtWidgets.QHBoxLayout(); _dbbar.setSpacing(4)
        self.btn_db_new = QtWidgets.QPushButton(_tr("+ Nuevo"))
        self.btn_db_new.setToolTip(_tr("Crear un bancoducto nuevo desde cero."))
        self.btn_db_new.clicked.connect(self._db_new)
        self.btn_db_edit = QtWidgets.QPushButton(_tr("Editar"))
        self.btn_db_edit.setToolTip(_tr("Editar el bancoducto seleccionado.\n"
                                    "También doble-click sobre la fila."))
        self.btn_db_edit.clicked.connect(self._db_edit)
        self.btn_db_dup = QtWidgets.QPushButton(_tr("Duplicar"))
        self.btn_db_dup.setToolTip(_tr("Duplicar el bancoducto seleccionado."))
        self.btn_db_dup.clicked.connect(self._db_duplicate)
        for _b in (self.btn_db_new, self.btn_db_edit, self.btn_db_dup):
            _b.setMinimumHeight(30)
            _dbbar.addWidget(_b)
        _dbv.addLayout(_dbbar)
        self.tabs.addTab(self.pipe_list, _tr("Utilidades"))
        self.tabs.addTab(self.sleader_list, _tr("Leaders"))
        self.tabs.addTab(self.txt_marks_list, _tr("Textos")); self.tabs.addTab(self.region_list, _tr("Zonas"))
        self.tabs.addTab(self.bz_list, _tr("Buzones")); self.tabs.addTab(self.curve_list, _tr("Curvas"))
        self.tabs.addTab(self.cl_list, _tr("Centerlines"))
        self.tabs.addTab(self._db_tab_widget, _tr("Bancoductos"))
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
        for i in range(self.tabs.count()):
            self.tab_combo.addItem(self.tabs.tabText(i))
        self.tab_combo.currentIndexChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.tab_combo.setCurrentIndex)
        self.tabs.tabBar().hide()
        rv.addWidget(self.tab_combo)
        self.tabs.currentChanged.connect(self._tab_changed); rv.addWidget(self.tabs, 1)
        # Propiedades de la utilidad seleccionada (nombre, diámetro, unidad) → XDATA en el DXF
        self.gprop = QtWidgets.QGroupBox("Propiedades de la utilidad"); fpr = QtWidgets.QFormLayout(self.gprop)
        self.prop_name = QtWidgets.QLineEdit(); self.prop_name.editingFinished.connect(self._prop_changed)
        # El diámetro va SIEMPRE en PULGADAS y SOLO de la lista estándar del
        # catálogo (12,15,18,…): un desplegable NO editable, sin valores libres,
        # para que coincida 1:1 con un tamaño real del catálogo de Civil 3D.
        # Es independiente de la unidad de trabajo (que rige coordenadas/cotas).
        # El diámetro ya no es un campo del UI: se deriva automáticamente del
        # "Tamaño (catálogo)" elegido. p["diam"] se calcula al guardar propiedades.
        fpr.addRow("Nombre:", self.prop_name)
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
            self.prop_material.addItem(_tr(m), m)   # data = valor real (no traducido)
        self.prop_material.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.prop_part = QtWidgets.QLineEdit(); self.prop_part.setPlaceholderText(_tr("p.ej. 900 mm Corrugated HDPE Pipe"))
        self.prop_part.editingFinished.connect(self._prop_changed)
        self.prop_nettype = QtWidgets.QComboBox()
        self.prop_nettype.addItem("Automático (según la capa)", "")
        self.prop_nettype.addItem("Con buzones (pipe)", "pipe")
        self.prop_nettype.addItem("A presión (pressure)", "pressure")
        self.prop_nettype.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.prop_inv0 = QtWidgets.QDoubleSpinBox(); self.prop_inv1 = QtWidgets.QDoubleSpinBox()
        for sp in (self.prop_inv0, self.prop_inv1):
            sp.setRange(-100000, 100000); sp.setDecimals(3); sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sp.valueChanged.connect(lambda _: self._prop_changed())
        fpr.addRow("Tipo de red:", self.prop_nettype)
        # Labels dinámicas: se recomponen al cambiar la unidad de trabajo.
        # Nombre igual a Civil 3D: "Elevación de rasante" (no "Invert").
        self.lbl_prop_inv0 = QtWidgets.QLabel(_tr("Elev. de rasante inicial (ft):")); fpr.addRow(self.lbl_prop_inv0, self.prop_inv0)
        self.lbl_prop_inv1 = QtWidgets.QLabel(_tr("Elev. de rasante final (ft):"));   fpr.addRow(self.lbl_prop_inv1, self.prop_inv1)
        # Familia + tamaño del catálogo Civil 3D para esta pipe (solo gravedad).
        # Para presión y conduit no aplica: presión usa el sub-catálogo por material
        # y conduit se deja como polyline simple.
        self.prop_family = QtWidgets.QComboBox()
        self.prop_family.currentIndexChanged.connect(self._pipe_family_changed)
        self.prop_size = QtWidgets.QComboBox()
        self.prop_size.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.lbl_prop_family = QtWidgets.QLabel(_tr("Familia (catálogo):"))
        self.lbl_prop_size = QtWidgets.QLabel(_tr("Tamaño (catálogo):"))
        fpr.addRow(self.lbl_prop_family, self.prop_family)
        fpr.addRow(self.lbl_prop_size, self.prop_size)

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
        self.gprop_segs = QtWidgets.QGroupBox("Cotas por tramo")
        segv = QtWidgets.QVBoxLayout(self.gprop_segs)
        self.btn_seg_edit = QtWidgets.QPushButton("  Activar edición por tramo")
        self.btn_seg_edit.setIconSize(QtCore.QSize(18, 18))
        self.btn_seg_edit.setCheckable(True)
        self.btn_seg_edit.setToolTip(
            "Activa la edición de cotas por tramo. Cuando está apagado se usan "
            "solo las rasantes de inicio/fin (interpolación lineal). Cuando "
            "se enciende, cada Inicio y Fin es totalmente independiente y "
            "editable, y en el lienzo aparecen etiquetas T1, T2… por tramo.")
        self.btn_seg_edit.toggled.connect(self._seg_edit_toggled)
        segv.addWidget(self.btn_seg_edit)
        self.tbl_seg_inv = QtWidgets.QTableWidget(0, 4)
        self.tbl_seg_inv.setHorizontalHeaderLabels(
            ["Tramo", "Inicio (ft)", "Fin (ft)", "Long (ft)"])
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
        self.gprop_bz = QtWidgets.QGroupBox("Propiedades del buzón"); fbz = QtWidgets.QFormLayout(self.gprop_bz)
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
        self.bz_height.setSpecialValueText("(automática)")
        self.bz_height.setToolTip(
            "Altura deseada del buzón, en pies. Si se llena, al importar la red en Civil3D\n"
            "se ajusta la cota de tapa (Rim = Sump + esta altura) para que la propiedad\n"
            "'Altura de estructura' salga exacta. Vacío (0) = se calcula automático desde el terreno.")
        self.bz_height.valueChanged.connect(lambda _v: self._bz_prop_changed())
        self.bz_net_lbl = QtWidgets.QLabel("—")
        self.bz_origin_lbl = QtWidgets.QLabel("—")
        fbz.addRow("Código:", self.bz_cod)
        fbz.addRow("Familia:", self.bz_family)
        fbz.addRow("Tamaño:", self.bz_size)
        fbz.addRow("Altura (Pies):", self.bz_height)
        fbz.addRow("Red:", self.bz_net_lbl)
        fbz.addRow("Origen:", self.bz_origin_lbl)
        self.bz_is_curve = QtWidgets.QPushButton("Cambiar a elemento curvo")
        self.bz_is_curve.setCheckable(True)
        self.bz_is_curve.setToolTip(
            "Marca este vértice como la esquina de un elemento curvo (p.ej. el codo de un\n"
            "bancoducto) en vez de un buzón/caja normal. Pasa a la pestaña 'Curvas' y no se\n"
            "exporta como buzón en el DXF (se marca con un punto PDFCAD_CURVE aparte).")
        self.bz_is_curve.toggled.connect(self._bz_curve_toggled)
        fbz.addRow("", self.bz_is_curve)
        self.chk_bz_hidden = QtWidgets.QPushButton("Desactivar/activar buzón")
        self.chk_bz_hidden.setCheckable(True)
        self.chk_bz_hidden.setToolTip(
            "Este vértice se detectó automáticamente pero no quieres un buzón real ahí.\n"
            "Se deja de dibujar en el lienzo y, al exportar/importar en Civil3D, se usa la\n"
            "familia 'Estructura nula' (invisible) en vez de un buzón visible — la red sigue\n"
            "conectada, solo no se ve el manhole.")
        self.chk_bz_hidden.toggled.connect(self._bz_hidden_toggled)
        fbz.addRow("", self.chk_bz_hidden)
        # Checkbox de etiquetas — entre la lista de buzones (tab) y el panel de propiedades.
        self.chk_bz_labels = QtWidgets.QCheckBox(
            "Ver etiquetas de buzón y en el DXF exportado")
        self.chk_bz_labels.setChecked(bool(self.show_bz_labels))
        def _toggle_bz_labels(v):
            self.show_bz_labels = bool(v); self._redraw()
        self.chk_bz_labels.toggled.connect(_toggle_bz_labels)
        rv.addWidget(self.chk_bz_labels)
        rv.addWidget(self.gprop_bz)
        # Mensaje guía cuando estás en la tab Buzones pero no seleccionaste nada.
        self.lbl_bz_hint = QtWidgets.QLabel(
            "Haz clic en un buzón de la lista (o en su círculo en el lienzo) para ver y editar sus propiedades.")
        self.lbl_bz_hint.setWordWrap(True)
        # Estilo aplicado por _apply_theme_custom_styles (sigue el tema activo).
        rv.addWidget(self.lbl_bz_hint)
        self.gprop_bz.setVisible(False); self.lbl_bz_hint.setVisible(False)
        # ── Propiedades del elemento curvo seleccionado (tab Curvas) ───────────
        self.gprop_curve = QtWidgets.QGroupBox("Propiedades del elemento curvo"); fcv = QtWidgets.QFormLayout(self.gprop_curve)
        self.cv_cod = QtWidgets.QLineEdit(); self.cv_cod.editingFinished.connect(self._curve_prop_changed)
        # Familia/Tamaño NO se eligen aparte: siempre son los de la tubería recta que
        # pasa por este vértice (garantiza que la curva calce con los tramos rectos).
        self.cv_family_lbl = QtWidgets.QLabel("—")
        self.cv_size_lbl = QtWidgets.QLabel("—")
        self.cv_radius = QtWidgets.QDoubleSpinBox()
        self.cv_radius.setRange(0, 10000); self.cv_radius.setDecimals(2)
        self.cv_radius.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.cv_radius.setSpecialValueText("(automático)")
        self.cv_radius.setToolTip(
            "Radio deseado de la tubería curva, en pies. Vacío (0) = automático:\n"
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
        fcv.addRow("Código:", self.cv_cod)
        fcv.addRow("Familia (tubería):", self.cv_family_lbl)
        fcv.addRow("Tamaño:", self.cv_size_lbl)
        fcv.addRow("Radio (Pies):", self.cv_radius)
        fcv.addRow("", self.cv_radius_warn)
        fcv.addRow("Red:", self.cv_net_lbl)
        fcv.addRow("Origen:", self.cv_origin_lbl)
        self.curve_is_bz = QtWidgets.QPushButton("Volver a tratar como buzón/caja")
        self.curve_is_bz.clicked.connect(self._curve_is_bz_toggled)
        fcv.addRow("", self.curve_is_bz)
        rv.addWidget(self.gprop_curve)
        self.lbl_curve_hint = QtWidgets.QLabel(
            "Haz clic en un elemento curvo de la lista (o en su marcador violeta en el lienzo) "
            "para ver y editar sus propiedades.")
        self.lbl_curve_hint.setWordWrap(True)
        # Estilo aplicado por _apply_theme_custom_styles.
        rv.addWidget(self.lbl_curve_hint)
        self.gprop_curve.setVisible(False); self.lbl_curve_hint.setVisible(False)
        # ── Propiedades del centerline seleccionado (tab Centerlines) ──────────
        self.gprop_cl = QtWidgets.QGroupBox("Propiedades del centerline"); fcl = QtWidgets.QFormLayout(self.gprop_cl)
        self.cl_cod = QtWidgets.QLineEdit(); self.cl_cod.editingFinished.connect(self._cl_prop_changed)
        self.cl_len_lbl = QtWidgets.QLabel("—")
        fcl.addRow("Código:", self.cl_cod)
        fcl.addRow("Longitud (ft):", self.cl_len_lbl)
        rv.addWidget(self.gprop_cl)
        self.lbl_cl_hint = QtWidgets.QLabel(
            "Haz clic en un centerline de la lista (o en su línea magenta punteada en el "
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
        rr = QtWidgets.QGridLayout()
        self.btn_ct = QtWidgets.QPushButton(_tr("Cambiar tipo")); self.btn_ct.clicked.connect(self.change_pipe_type)
        self.btn_mv = QtWidgets.QPushButton(_tr("Editar/mover")); self.btn_mv.clicked.connect(self.enter_move)
        self.btn_edit = QtWidgets.QPushButton(_tr("Editar texto")); self.btn_edit.clicked.connect(self.edit_selected_text)
        self.btn_del = QtWidgets.QPushButton(_tr("Eliminar")); self.btn_del.setProperty("danger", True)
        self.btn_del.clicked.connect(self.delete_selected)
        rr.addWidget(self.btn_ct, 0, 0); rr.addWidget(self.btn_mv, 0, 1)
        rr.addWidget(self.btn_edit, 1, 0); rr.addWidget(self.btn_del, 1, 1)
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

    def _build_statusbar(self):
        # ── Barra de estado: modo · info · contadores en vivo · escala · georref ──
        self.status = self.statusBar(); self.status.setSizeGripEnabled(False)
        self.lbl_mode = QtWidgets.QLabel(_tr("Modo: inactivo"))   # color por _apply_theme_custom_styles
        self.status.addWidget(self.lbl_mode)
        self.status.addWidget(QtWidgets.QLabel("│"))
        self.lbl_info = QtWidgets.QLabel("")   # color por _apply_theme_custom_styles
        self.status.addWidget(self.lbl_info, 1)
        self.lbl_coords = QtWidgets.QLabel("X —  Y —  Z —")
        # Contadores en vivo: N utilidades · N leaders · N textos · dirty
        self.lbl_counts = QtWidgets.QLabel("—")
        self.lbl_dirty = QtWidgets.QLabel("")   # muestra "●" cuando hay cambios sin guardar
        # Escala como BOTÓN plano: el usuario reportó que "1"=20'" viene del
        # titleblock pero a veces necesita ajustarla. Un botón deja claro que
        # es interactivo y hace evidente el gesto (un QLabel se ve idéntico a
        # los otros textos de la barra de estado). Estilo consistente con la
        # barra: fondo transparente, sin borde salvo al pasar/pulsar.
        self.btn_scale = QtWidgets.QPushButton(_tr("Escala —"))
        self.btn_scale.setFlat(True); self.btn_scale.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_scale.setToolTip(_tr("Clic para cambiar la escala del plano (1\"=X ft)"))
        # Estilo por _apply_theme_custom_styles (btn plano de status bar).
        self.btn_scale.clicked.connect(self._prompt_scale)
        # Botón "Opacidad" al lado de la escala: abre un desplegable con un
        # deslizable (opacidad SOLO del PDF) y un botón para alternar el fondo
        # detrás del PDF entre blanco y negro.
        self.btn_opacity = QtWidgets.QPushButton("  " + _tr("Opacidad"))
        self.btn_opacity.setIconSize(QtCore.QSize(16, 16))
        self.btn_opacity.setFlat(True); self.btn_opacity.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_opacity.setToolTip(_tr("Opacidad del PDF y color de fondo (blanco/negro)"))
        # Estilo por _apply_theme_custom_styles (idéntico a btn_scale).
        self.btn_opacity.clicked.connect(self._open_opacity_popup)
        self.lbl_geo = QtWidgets.QLabel(_tr("Georref: no"))
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

    # ─────────────────────────── páginas ───────────────────────────
    def _update_page_label(self):
        if self.doc:
            self.page_edit.setText(str(self.page_idx + 1)); self.lbl_page.setText(f" / {self.doc.page_count} ")
            self.page_edit.setEnabled(True)
            self.btn_prev.setEnabled(self.page_idx > 0)
            self.btn_next.setEnabled(self.page_idx < self.doc.page_count - 1)
        else:
            self.page_edit.setText(""); self.page_edit.setEnabled(False); self.lbl_page.setText(" / — ")
            self.btn_prev.setEnabled(False); self.btn_next.setEnabled(False)

    def _goto_page_edit(self):
        if not self.doc: return
        try: n = int(self.page_edit.text()) - 1
        except ValueError: self._update_page_label(); return
        n = max(0, min(n, self.doc.page_count - 1))
        if n != self.page_idx:
            if not self._confirm_discard(): self._update_page_label(); return
            self._change_page(n)
        else:
            self._update_page_label()

    def _prev_page(self):
        if self.doc and self.page_idx > 0:
            if not self._confirm_discard(): return
            self._change_page(self.page_idx - 1)

    def _next_page(self):
        if self.doc and self.page_idx < self.doc.page_count - 1:
            if not self._confirm_discard(): return
            self._change_page(self.page_idx + 1)

    def _change_page(self, idx):
        """Cambio de hoja desde el editor (◀ ▶ / nº de página). Si el asistente
        ya reconoció una hoja de este PDF, la nueva se reconoce con las mismas
        capas ocultas y roles (mismo PDF = mismas capas) y se muestra la vista
        previa para importar."""
        self.page_idx = idx; self._load_page(idx)
        if self.composite is not None and self.composite.is_single_full_page():
            self.composite.pieces[0].page = idx
        if self._recog_ready and self.pdf_path:
            self._start_recognition(idx)

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
        self.btn_scale.setText(f"{_tr('Escala')} 1\"={v:.0f}'" if v > 0 else _tr("Escala —"))

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
            self, "Escala del plano",
            "1 pulgada del PDF equivale a X pies reales:",
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
        self._info(f"Escala cambiada a 1\"={val:g}'.")

    def _open_opacity_popup(self):
        """Desplegable junto al botón de escala: deslizable de opacidad del PDF y
        botón para alternar el fondo detrás del PDF entre blanco y negro."""
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Opacidad"), _tr("Primero abre un PDF o proyecto.")); return
        menu = QtWidgets.QMenu(self)
        box = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(box); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(8)
        pct = round(self.canvas.pdf_opacity * 100)
        lbl = QtWidgets.QLabel(f"Opacidad del PDF: {pct}%")
        sl = QtWidgets.QSlider(QtCore.Qt.Horizontal); sl.setRange(10, 100)
        sl.setValue(pct); sl.setMinimumWidth(240)
        # Accesibilidad: más contraste (canal oscuro + parte activa azul brillante)
        # y un handle más ancho/visible, fácil de agarrar. Solo estético.
        sl.setStyleSheet(
            "QSlider::groove:horizontal { height: 10px; border-radius: 5px;"
            " background: #202020; border: 1px solid #6a6a6a; }"
            "QSlider::sub-page:horizontal { background: #4a90ff; border: 1px solid #8ec2ff;"
            " border-radius: 5px; }"
            "QSlider::add-page:horizontal { background: #2b2b2b; border: 1px solid #565656;"
            " border-radius: 5px; }"
            "QSlider::handle:horizontal { width: 26px; height: 22px; margin: -7px 0;"
            " border-radius: 6px; background: #ffffff; border: 2px solid #2f6ad9; }"
            "QSlider::handle:horizontal:hover { background: #eaf1ff; border: 2px solid #6ba3ff; }"
            "QSlider::handle:horizontal:pressed { background: #cfe0ff; border: 2px solid #8ec2ff; }")

        def _on_val(v):
            self.canvas.set_pdf_opacity(v / 100.0)
            lbl.setText(f"Opacidad del PDF: {v}%")
            self.lbl_opacity.setText(f"{v}%")     # mantiene sincronizado el control del dock
        sl.valueChanged.connect(_on_val)

        btn_bg = QtWidgets.QPushButton()

        def _is_black():
            return self.canvas.pdf_bg_color.value() < 128

        def _refresh_bg_btn():
            # El texto muestra la acción que hará el clic (viceversa del estado actual).
            btn_bg.setText("Fondo blanco" if _is_black() else "Fondo negro")

        def _toggle_bg():
            self.canvas.set_pdf_bg(QtGui.QColor(255, 255, 255) if _is_black()
                                   else QtGui.QColor(0, 0, 0))
            _refresh_bg_btn()
            # Redibujar para que las zonas borradas adopten el color del fondo
            # (solo visual — nada cambia en el modelo).
            self._redraw()
        btn_bg.clicked.connect(_toggle_bg)
        _refresh_bg_btn()

        lay.addWidget(lbl); lay.addWidget(sl); lay.addWidget(btn_bg)
        wa = QtWidgets.QWidgetAction(menu); wa.setDefaultWidget(box); menu.addAction(wa)
        # Se abre encima del botón; Qt reubica solo si no cabe (la barra está abajo).
        pos = self.btn_opacity.mapToGlobal(QtCore.QPoint(0, 0))
        menu.exec(QtCore.QPoint(pos.x(), pos.y() - menu.sizeHint().height()))

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
        for it in getattr(self, "_crosshair", []):
            sc.removeItem(it)
        cp = QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 0); cp.setCosmetic(True)
        h = sc.addLine(r.left(), y, r.right(), y, cp); h.setZValue(Z_MARK + 10)
        v = sc.addLine(x, r.top(), x, r.bottom(), cp); v.setZValue(Z_MARK + 10)
        self._crosshair = [h, v]
        self._update_hover_tooltip(x, y)
        self._update_pipe_snap_hint(x, y)

    def _update_pipe_snap_hint(self, x, y):
        """Feedback visual del snap suave a utilidades: al mover el mouse en
        modo Dibujar, si el cursor está cerca de una utilidad existente del
        mismo tipo, dibuja un círculo verde en el punto donde se pegaría.
        Sin costo cuando no hay hit (removeItem del previo y no dibuja nada)."""
        sc = self.canvas.scene()
        prev = getattr(self, "_pipe_snap_hint", None)
        if prev is not None:
            try: sc.removeItem(prev)
            except (RuntimeError, ValueError): pass
            self._pipe_snap_hint = None
        if self.mode != "pipe": return
        hit = self._pipe_soft_snap(x, y)
        if hit is None: return
        sx, sy = hit["pt"]
        R_PX = 6.0
        pen = QtGui.QPen(QtGui.QColor(30, 200, 60), 2.0); pen.setCosmetic(True)
        it = sc.addEllipse(-R_PX, -R_PX, R_PX * 2, R_PX * 2, pen,
                            QtGui.QBrush(QtCore.Qt.NoBrush))
        it.setPos(sx, sy)
        it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        it.setZValue(Z_MARK + 20)
        self._pipe_snap_hint = it

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
                    d = p.get("diam", "?")
                    tag = " (AB)" if p.get("ab") else ""
                    tip = f"#{i+1} {p['layer']}{tag} — {d}\" · {len(pts)} vértices"
                    self.canvas.setToolTip(tip)
                    return
        self.canvas.setToolTip("")

    def _update_geo_status(self):
        if self.georef.active():
            unit = georef_mod.epsg_unit(self.georef.epsg)
            rms = f" · RMS {self.georef.rms:.2f} {unit}" if self.georef.rms is not None else ""
            cs = (getattr(self.georef, "cs_code", "") or "").strip()
            etq = cs if cs else f"EPSG:{self.georef.epsg}"
            self.lbl_geo.setText(f"{_tr('Georref')}: {etq}{rms}")
            self.lbl_geo.setStyleSheet(f"color:{_theme.tokens().success};")
        else:
            self.lbl_geo.setText(_tr("Georref: no (escala titleblock)"))
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
        self.gtxt.setTitle(_tr("Estilo de texto"))
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
        self.btn_mv.setText(_tr("Mover") if ti == TAB_TEXT else _tr("Editar/mover"))
        self.btn_edit.setVisible(ti == TAB_TEXT)
        # "Eliminar" no aplica en la pestaña Buzones: los buzones se
        # auto-detectan de los vertices de las tuberias, borrarlos no tiene
        # efecto porque _rebuild_structures los repone. Se oculta el boton.
        self.btn_del.setVisible(ti != TAB_BZ)
        diag = self.orient_combo.currentData() == "d"
        lead1 = _tr("Modo: Leader — clic en la cabeza de flecha (dónde señala)")
        lead2 = (_tr("Modo: Leader — clic en el inicio del landing (bisagra)") if diag
                 else _tr("Modo: Leader — clic en el final del cuerpo"))
        lead3 = _tr("Modo: Leader — clic en el final del cuerpo")
        self.lbl_mode.setText({"idle": _tr("Modo: inactivo  ·  clic en el dibujo para seleccionar"),
                               "pipe": (_tr("Modo: EXTENDIENDO desde el vértice — clic agrega puntos, Enter finaliza")
                                        if self._extending else _tr("Modo: dibujar utilidad  ·  Enter finaliza")),
                               "leader1": lead1,
                               "leader2": lead2,
                               "leader3": lead3,
                               "text": _tr("Modo: texto libre — clic donde escribir · Enter aplica"),
                               "erase": _tr("Modo: borrar zona — clic para el polígono, Enter cierra"),
                               "centerline": _tr("Modo: trazar centerline — clic agrega puntos, Enter finaliza"),
                               "move": _tr("Modo: editar — arrastra vértice · clic en tramo inserta · clic-en-vértice extiende (F) · clic derecho elimina")}.get(m, ""))
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

    # ─────────────────────────── undo/redo ───────────────────────────
    def _snap_state(self):
        return copy.deepcopy(dict(cur_pts=self.cur_pts, pipes=self.pipes, leaders=self.leaders,
                                  text_marks=self.text_marks, erase_regions=self.erase_regions,
                                  structures=self.structures))

    def _push(self):
        self._undo.append(self._snap_state()); self._redo.clear(); self._dirty = True
        if len(self._undo) > 400: self._undo.pop(0)

    def _restore(self, s):
        self.cur_pts, self.pipes = s["cur_pts"], s["pipes"]
        self.leaders, self.text_marks = s["leaders"], s["text_marks"]
        self.erase_regions = s.get("erase_regions", [])
        self.structures = s.get("structures", [])
        self._refresh_lists(); self._update_ui(); self._redraw()

    def undo(self):
        if self._undo: self._redo.append(self._snap_state()); self._restore(self._undo.pop()); self._info(_tr("Deshacer"))
        self._update_undo_tooltips()

    def redo(self):
        if self._redo: self._undo.append(self._snap_state()); self._restore(self._redo.pop()); self._info(_tr("Rehacer"))
        self._update_undo_tooltips()

    def _update_undo_tooltips(self):
        u, r = len(self._undo), len(self._redo)
        self._act_undo.setToolTip(f"Deshacer (Ctrl+Z) — {u} paso{'s' if u != 1 else ''}")
        self._act_redo.setToolTip(f"Rehacer (Ctrl+Shift+Z) — {r} paso{'s' if r != 1 else ''}")

    # ─────────────────────────── abrir ───────────────────────────
    def _busy(self, m="Procesando…"):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor); self._info(m); QtWidgets.QApplication.processEvents()
    def _unbusy(self): QtWidgets.QApplication.restoreOverrideCursor()

    def open_path(self, path):
        low = path.lower()
        if low.endswith(".pdf"): self._open_pdf_path(path)
        elif low.endswith(".digproj"): self._open_project_path(path)

    def open_pdf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir PDF", DOWNLOADS, "PDF (*.pdf)")
        if path: self._open_pdf_path(path)

    def _open_pdf_path(self, path):
        if not self._confirm_discard(): return
        self._busy(_tr("Abriendo PDF…"))
        try:
            new_doc = fitz.open(path)
            if self.doc:
                self.doc.close()
            self._cleanup_tmp_pdf()
            self.pdf_path = path; self.project_path = None; self.doc = new_doc; self._update_title()
            self.work_pdf_path = path
            with open(path, "rb") as fp:
                self.src_pdfs = [{"name": os.path.basename(path), "data": fp.read(), "path": path}]
            self.composite = None
            self._scale_override = None
            self.hidden_ocgs = []   # capas OCG ocultas por el usuario (paso «Capas de la hoja»)
            self.hidden_ocgs_by_source = {}
            self._layer_roles_by_utility = {}
            self._recognition_utilities = ("ELECTRICO", "DRENAJE")
            self._recog_ready = False
            self.sheet_layout = None
            self.sheet_rotations = {}
            self.sheet_crops = {}
            self.sheet_sources = [{"name": os.path.basename(path), "start": 0,
                                   "count": self.doc.page_count}]
            self.sheet_external_pdfs = []
        finally:
            self._unbusy()
        # Asistente: tipo → hoja → capas/utilidad → reconocimiento → preview.
        self._run_recognition_wizard()

    def _run_recognition_wizard(self):
        """Elegir tipo/hoja, utilidad/capas, reconocer y mostrar preview. Sin importar pipes.

        Si detect.py clasifica claro (vector o raster con imagen dominante), se omite
        el diálogo de tipo; solo se pregunta en casos ambiguos.
        """
        if not self.doc or not self.pdf_path:
            return

        _load = self._load_sheet_busy

        def _go_manual(msg):
            _load(0)
            self._info(msg)

        def _go_plotted():
            if not self._wizard_sheet_flow(0):
                _load(0)

        # Clasificación automática (página 0) — misma heurística que digitize.
        import detect as _detect
        kind, info = _detect.classify_page(self.doc[0])
        n_paths = info.get("n_paths", 0)
        img_cover = float(info.get("max_image_cover") or 0.0)

        if kind == "vector":
            self._info(_tr("Detectado PDF vectorial ({n} trazos)…").format(n=n_paths))
            _go_plotted()
            return
        if kind == "raster" and info.get("traced"):
            _go_manual(_tr("Detectado plano escaneado y vectorizado ({n} trazos calcados, sin texto ni capas) "
                           "— continúa con el dibujo manual.").format(n=n_paths))
            return
        if kind == "raster" and img_cover >= 0.6:
            _go_manual(_tr("Detectado PDF imagen/escaneo — continúa con el dibujo manual."))
            return

        # Ambiguo: pedir confirmación al usuario.
        pdf_type = recognition_dialog.choose_pdf_type(self)
        if pdf_type is None:
            _load(0)
            return
        if pdf_type != "plotted":
            _go_manual(_tr("PDF imagen: continúa con el dibujo manual."))
            return
        _go_plotted()

    def _load_sheet_busy(self, idx):
        self._busy(_tr("Cargando hoja…"))
        try:
            self.page_idx = idx
            self._load_page(idx)
        finally:
            self._unbusy()

    def _wizard_sheet_flow(self, start_idx):
        """Componer la hoja de trabajo, elegir capas y reconocer.
        Lo usa el asistente al abrir el PDF y «Cambiar de hoja…» del preview.
        Devuelve False si se cancela el compositor. Al cancelar las capas, la
        hoja queda cargada sin reconocer."""
        res = composite_dialog.compose_sheet(
            self, self.src_pdfs, self.composite, self.hidden_ocgs_by_source, current_page=start_idx)
        if res is None:
            return False
        comp, sources, hidden_by_source = res
        self.src_pdfs = sources
        self.composite = comp
        self.hidden_ocgs_by_source = {k: list(v) for k, v in hidden_by_source.items()}
        self._recog_ready = False
        try:
            self._apply_composite()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, _tr("Componer hoja"),
                _tr("No se pudo armar la hoja compuesta:\n\n{e}").format(e=exc))
            return False
        page_idx = self.page_idx
        # Paso «Capas de la hoja»: el usuario decide qué capas OCG ver ANTES
        # de dibujar. Deja la visibilidad aplicada en self.doc, así _load_page
        # ya renderiza sin las ocultas.
        chosen = layer_dialog.choose_sheet_layers(self, self.doc, page_idx,
                                                  layout=getattr(self, "_composite_layout", None),
                                                  recognition_utilities=self._recognition_utilities)
        if chosen is None:
            self._load_sheet_busy(page_idx)
            self._dirty = True
            self._info(_tr("Reconocimiento cancelado — hoja cargada con las capas elegidas."))
            return True
        hidden, page_idx, self._recognition_utilities = chosen
        if self.composite is not None and self.composite.is_single_full_page():
            self.composite.pieces[0].page = page_idx
        self.hidden_ocgs = list(hidden)
        self._sync_hidden_to_sources(hidden)
        # Los roles (qué capas son líneas / bóvedas) se asignan solos por
        # nombre y se muestran en el preview; «Ajustar capas…» los cambia.
        self._layer_roles_by_utility = {}
        self._load_sheet_busy(page_idx)
        self._dirty = True
        self._recog_ready = True
        self._start_recognition(page_idx)
        return True

    def _apply_composite(self):
        """Deja en `self.doc` la hoja de trabajo según `self.composite`:
        una sola pieza = hoja entera → el PDF origen tal cual (◀ ▶ siguen
        sirviendo); si no, se materializa la hoja compuesta como PDF temporal
        (`composite.build_document`) con las capas de cada origen ya apagadas."""
        comp = self.composite
        import pdf_layers as _pdf_layers
        if self.doc:
            self.doc.close(); self.doc = None
        self._cleanup_tmp_composite()
        self._composite_layout = None      # esquema para el minimapa de «Capas de la hoja»
        if comp is None or comp.is_single_full_page():
            piece = comp.pieces[0] if comp else None
            src = piece.source if piece else 0
            entry = self.src_pdfs[src]
            if entry.get("path") and os.path.isfile(entry["path"]):
                path = entry["path"]
            else:
                path = self._write_tmp_composite(entry["data"], suffix=f"_src{src}")
            self.doc = fitz.open(path)
            self.work_pdf_path = path
            hidden = list(self.hidden_ocgs_by_source.get(str(src), []))
            _pdf_layers.set_hidden(self.doc, hidden)
            self.hidden_ocgs = hidden
            self._scale_override = None
            self.page_idx = piece.page if piece else 0
        else:
            docs = [fitz.open(stream=e["data"], filetype="pdf") for e in self.src_pdfs]
            try:
                for i, d in enumerate(docs):      # capas apagadas: sin trazos ni anclajes
                    _pdf_layers.set_hidden(d, self.hidden_ocgs_by_source.get(str(i), ()))
                bridges = composite_mod.compute_bridges(comp, docs)
                built = composite_mod.build_document(comp, docs, self.hidden_ocgs_by_source, bridges)
                data = built.tobytes(deflate=True); built.close()
                sizes = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)
                self._composite_layout = composite_mod.piece_layout(
                    comp, sizes, [e.get("name", "") for e in self.src_pdfs])
            finally:
                for d in docs: d.close()
            path = self._write_tmp_composite(data, suffix="_compuesta")
            self.doc = fitz.open(path)     # reabrir: así fitz lee el catálogo de capas nuevo
            self.work_pdf_path = path
            self.hidden_ocgs = sorted(_pdf_layers.hidden_layers(self.doc))
            self._scale_override = comp.target_scale()
            self.page_idx = 0
        self._load_sheet_busy(self.page_idx)

    def _write_tmp_composite(self, data, suffix=""):
        import tempfile
        fd, path = tempfile.mkstemp(prefix="pdfcad_hoja", suffix=f"{suffix}.pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        self._tmp_composite = path
        return path

    def _cleanup_tmp_composite(self):
        tmp = getattr(self, "_tmp_composite", None)
        if tmp and os.path.isfile(tmp):
            try: os.remove(tmp)
            except Exception: pass
        self._tmp_composite = None

    def _sync_hidden_to_sources(self, hidden):
        """Las capas apagadas en la hoja de trabajo se reflejan por nombre en
        cada PDF de origen, así al volver al compositor se conservan."""
        import pdf_layers as _pdf_layers
        hidden = set(hidden or ())
        for i, entry in enumerate(self.src_pdfs):
            try:
                with fitz.open(stream=entry["data"], filetype="pdf") as d:
                    names = [c["text"] for c in _pdf_layers._ui_configs(d)]
            except Exception:
                continue
            self.hidden_ocgs_by_source[str(i)] = [n for n in names if n in hidden]

    def compose_sheet(self):
        """Menú Ver → volver al compositor (piezas de varias hojas/PDF) y
        repetir capas + reconocimiento sobre la hoja compuesta nueva."""
        if not self.doc or not self.src_pdfs:
            QtWidgets.QMessageBox.information(self, _tr("Componer hoja de trabajo"),
                _tr("Abre un PDF para componer su hoja de trabajo."))
            return
        if not self._confirm_discard():
            return
        if not self._wizard_sheet_flow(self.page_idx):
            self._info(_tr("Composición cancelada — se mantiene la hoja actual."))

    def organize_sheets(self):
        """Reopen the arrangement without changing the current drawing or layers."""
        if not self.doc:
            QtWidgets.QMessageBox.information(self, _tr("Organizar hojas"),
                _tr("Abre un PDF para organizar sus hojas."))
            return
        selection = sheet_layout_dialog.choose_sheet_layout(
            self, self.doc, self.sheet_layout, current=self.page_idx,
            sources=self.sheet_sources, external_pdfs=self.sheet_external_pdfs,
            rotations=self.sheet_rotations)
        if selection is None:
            return
        layout, added_paths, sources, rotations = selection
        if layout["main"] != self.page_idx and not self._confirm_discard():
            return
        changed = (layout != self.sheet_layout or rotations != self.sheet_rotations
                   or bool(added_paths))
        if not self._apply_sheet_selection(layout, added_paths, sources, rotations):
            return
        if any(layout[key] is not None for key in ("top", "left", "right", "bottom")):
            self._recog_ready = False
        if layout["main"] != self.page_idx:
            self._change_page(layout["main"])
        self._dirty = self._dirty or changed
        self._info(_tr("Organización guardada. Hoja principal: {n}.").format(
            n=layout["main"] + 1))

    def open_organized_layers(self):
        """Review common layers and continue to the arranged recognition preview."""
        layout = self.sheet_layout
        if not self.doc or not layout or not any(
                layout[key] is not None for key in ("top", "left", "right", "bottom")):
            QtWidgets.QMessageBox.information(self, _tr("Capas de hojas organizadas"),
                _tr("Organiza al menos dos hojas para abrir esta vista."))
            return
        chosen = organized_layer_dialog.choose_organized_sheet_layers(
            self, self.doc, self.sheet_external_pdfs, self.sheet_sources,
            layout, self.sheet_rotations, self.hidden_ocgs_by_source,
            self.sheet_crops, self._recognition_utilities)
        if chosen is None:
            return
        self.hidden_ocgs_by_source, self.sheet_crops, self._recognition_utilities = chosen
        self.hidden_ocgs = list(self.hidden_ocgs_by_source.get("0", []))
        self._refresh_current_pdf_image()
        self._dirty = True
        self._recog_ready = False
        self._info(_tr("Capas de las hojas organizadas guardadas."))
        self._start_organized_recognition()

    def _start_organized_recognition(self):
        """Recognize all arranged sheets without changing the editor's drawing."""
        if not self.doc or not self.sheet_layout or not self.pdf_path:
            return
        sheets = selected_sheets(self.sheet_layout, self.sheet_sources)
        utility_text = ("Eléctrico y Drenaje" if len(self._recognition_utilities) > 1
                        else ("Drenaje" if self._recognition_utilities[0] == "DRENAJE" else "Eléctrico"))
        progress = QtWidgets.QProgressDialog(
            _tr("Reconociendo {u} en las hojas organizadas…").format(u=utility_text),
            None, 0, 0, self)
        progress.setWindowTitle(_tr("Reconocimiento"))
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self._organized_recog_progress = progress
        self._organized_recog_worker = OrganizedRecognitionWorker(
            self.pdf_path, self.sheet_external_pdfs, sheets,
            self.hidden_ocgs_by_source, zoom=1.0,
            join_routes=self._join_routes, crops=self.sheet_crops,
            utilities=self._recognition_utilities)
        self._organized_recog_worker.done.connect(self._organized_recognition_done)
        self._organized_recog_worker.start()

    def _organized_recognition_done(self, rows, error):
        progress = getattr(self, "_organized_recog_progress", None)
        if progress is not None:
            progress.close()
            self._organized_recog_progress = None
        if error:
            QtWidgets.QMessageBox.warning(self, _tr("Reconocimiento"),
                _tr("No se pudieron reconocer las hojas:\n\n{e}").format(e=error))
            return
        if not rows:
            return
        action, self._join_routes = organized_recognition_dialog.show_organized_recognition_preview(
            self, rows, self.sheet_rotations, self._join_routes,
            base_path=self.pdf_path, external_pdfs=self.sheet_external_pdfs,
            hidden_by_source=self.hidden_ocgs_by_source, crops=self.sheet_crops)
        if action == 2:
            self.open_organized_layers()

    def _refresh_current_pdf_image(self):
        """Update the PDF background after OCG changes without losing annotations."""
        if not self.doc or self.canvas.pixmap_item is None:
            return
        pix = self.doc[self.page_idx].get_pixmap(
            matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        qimg = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                            pix.stride, QtGui.QImage.Format_RGB888).copy()
        self.canvas.pixmap_item.setPixmap(QtGui.QPixmap.fromImage(qimg))
        self.gray = qimage_to_gray(qimg)
        self._redraw()

    def _apply_sheet_selection(self, layout, added_paths, sources, rotations):
        """Keep each PDF intact so OCG layers are available in later stages."""
        if not 0 <= layout["main"] < self.doc.page_count:
            QtWidgets.QMessageBox.warning(self, _tr("Organizar hojas"),
                _tr("La hoja principal debe pertenecer al PDF abierto."))
            return False
        additions = []
        try:
            expected = sources[1 + len(self.sheet_external_pdfs):]
            if len(expected) != len(added_paths):
                raise ValueError(_tr("La lista de PDF no coincide con las hojas elegidas."))
            for path, source in zip(added_paths, expected):
                with open(path, "rb") as stream:
                    data = stream.read()
                with fitz.open(stream=data, filetype="pdf") as check:
                    if check.page_count != source["count"]:
                        raise ValueError(_tr("El PDF cambió mientras se elegían sus hojas."))
                additions.append({"name": os.path.basename(path), "data": data})
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, _tr("Organizar hojas"),
                _tr("No se pudieron incorporar los PDF:\n\n{e}").format(e=exc))
            return False
        old_layout = self.sheet_layout or {}
        kept_crops = {slot: crop for slot, crop in self.sheet_crops.items()
                      if old_layout.get(slot) == layout.get(slot)}
        self.sheet_external_pdfs.extend(additions)
        total = self.doc.page_count + sum(s["count"] for s in sources[1:])
        self.sheet_layout = normalize_sheet_layout(layout, total)
        self.sheet_rotations = normalize_rotations(rotations, self.sheet_layout)
        self.sheet_crops = normalize_sheet_crops(kept_crops, self.sheet_layout)
        self.sheet_sources = sources
        return True

    def _adjust_layer_roles(self, page_idx):
        """«Ajustar capas…» del preview: elegir a mano qué capas visibles son
        líneas / bóvedas y volver a reconocer la hoja con esos roles."""
        import pdf_layers as _pdf_layers
        utilities = tuple(self._recognition_utilities)
        if len(utilities) > 1:
            labels = ["Eléctrico" if key == "ELECTRICO" else "Drenaje" for key in utilities]
            label, ok = QtWidgets.QInputDialog.getItem(
                self, _tr("Ajustar capas"),
                _tr("¿Qué utilidad quieres ajustar?"), labels, 0, False)
            if not ok:
                return
            utility = utilities[labels.index(label)]
        else:
            utility = utilities[0]
        all_layers = _pdf_layers.page_layers(self.doc, page_idx)
        visible = [L for L in all_layers if L["name"] not in set(self.hidden_ocgs)]
        roles = recognition_dialog.choose_layer_roles(
            self, visible, utility=utility)
        if roles is None:
            self._info(_tr("Reconocimiento cancelado — hoja cargada con las capas elegidas."))
            return
        self._layer_roles_by_utility[utility] = roles
        self._start_recognition(page_idx)

    def _start_recognition(self, page_idx):
        """Lanza el reconocimiento de la hoja `page_idx` en segundo plano con las
        capas ocultas (`self.hidden_ocgs`) y roles separados por utilidad
        (sin ajuste manual = automático por nombre). Al terminar, `_recognition_done` muestra
        la vista previa. Lo usan el asistente y el cambio de hoja del editor."""
        utility_text = ("Eléctrico y Drenaje" if len(self._recognition_utilities) > 1
                        else ("Drenaje" if self._recognition_utilities[0] == "DRENAJE" else "Eléctrico"))
        progress = QtWidgets.QProgressDialog(
            _tr("Reconociendo {u}…").format(u=utility_text),
            None, 0, 0, self)
        progress.setWindowTitle(_tr("Reconocimiento"))
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QtWidgets.QApplication.processEvents()
        self._recog_progress = progress
        self._recog_worker = RecognitionWorker(
            self.work_pdf_path or self.pdf_path, page_idx, zoom=self.zoom,
            utilities=self._recognition_utilities,
            hidden_ocgs=self.hidden_ocgs,
            roles_by_utility=self._layer_roles_by_utility,
            join_routes=self._join_routes, scale_ft_per_pt=self._scale_override)
        self._recog_worker.done.connect(self._recognition_done)
        self._recog_worker.start()

    def _recognition_done(self, results, error):
        prog = getattr(self, "_recog_progress", None)
        if prog is not None:
            prog.close()
            self._recog_progress = None
        if error:
            QtWidgets.QMessageBox.warning(
                self, _tr("Reconocimiento"),
                _tr("No se pudo reconocer la hoja:\n\n{e}").format(e=error))
            return
        if results is None:
            return
        if not isinstance(results, (list, tuple)):
            results = [results]
        results = [result for result in results if result is not None]
        if not results:
            return
        qimg = None
        if self.canvas.pixmap_item is not None:
            qimg = self.canvas.pixmap_item.pixmap().toImage()
        if qimg is None or qimg.isNull():
            QtWidgets.QMessageBox.information(
                self, _tr("Reconocimiento"),
                _tr("Reconocimiento listo, pero no hay imagen de la hoja para la vista previa."))
            return
        action = recognition_dialog.show_recognition_preview(
            self, qimg, results,
            page_count=self.doc.page_count if self.doc else None)
        self._join_routes = all(bool(getattr(result, "join_routes", True)) for result in results)
        page_index = results[0].page_index
        if action == recognition_dialog.PREVIEW_IMPORT:
            self._import_recognized_pipes(results)
        elif action == recognition_dialog.PREVIEW_CHANGE_SHEET:
            # Flujo pedido: lista de hojas → capas → preview de la hoja nueva.
            if not self._wizard_sheet_flow(page_index):
                self._info(_tr("Cambio de hoja cancelado — se mantiene la hoja {n}.").format(
                    n=page_index + 1))
        elif action == recognition_dialog.PREVIEW_ADJUST_LAYERS:
            self._adjust_layer_roles(page_index)
        else:
            self._info(_tr("Reconocimiento cancelado — editor vacío."))

    def _import_recognized_pipes(self, results):
        """Añade centerlines reconocidas e inserta sus estructuras como nodos."""
        import recognition as rec
        if not isinstance(results, (list, tuple)):
            results = [results]
        batches = []
        for result in results:
            utility = getattr(result, "utility", None) or "ELECTRICO"
            pipes = rec.pipes_from_recognition(result, layer=utility, zoom=self.zoom)
            vaults = list(getattr(result, "vault_pts", None) or [])
            snapped, skipped = rec.inject_vault_vertices(pipes, vaults)
            result.vaults_snapped = snapped
            result.vaults_skipped = skipped
            has_importable_structure = any(
                vault.get("importable", False)
                for vault in (getattr(result, "vaults_geo", None) or []))
            if pipes or has_importable_structure:
                batches.append((result, utility, pipes, snapped, skipped))
        if not batches:
            self._info(_tr("No hay tramos reconocidos para importar."))
            return
        self._push()
        for _result, _utility, pipes, _snapped, _skipped in batches:
            self.pipes.extend(pipes)
        self._dirty = True
        self._refresh_lists()                 # crea las CAJA en todos los vértices…
        # …y oculta las de quiebres/esquinas sin bóveda (siguen en el DXF como
        # "Estructura nula" para no romper la topología de la red).
        n_hidden = model_ops.hide_soft_vertex_structures(self.pipes, self.structures)
        # …y les pone a las CAJA de bóveda real su forma, medidas (pies) y contorno.
        n_geo = n_alone = 0
        for result, utility, _pipes, _snapped, _skipped in batches:
            added_geo, added_alone = model_ops.attach_vault_geometry(
                self.structures, getattr(result, "vaults_geo", None) or [],
                net="gravity" if utility == "DRENAJE" else "conduit", utility=utility)
            n_geo += added_geo; n_alone += added_alone
        # …y los codos reconocidos quedan como esquina «CV» con su radio (flujo manual).
        n_cv = model_ops.attach_fillets(self.pipes, self.structures)
        if n_hidden or n_geo or n_cv:
            self._refresh_lists()
        self._update_ui()
        self._redraw()
        parts = []
        for result, utility, pipes, _snapped, _skipped in batches:
            if not pipes:
                continue
            n_seg = sum(int(getattr(pl, "n_segments", 1) or 1) for pl in result.drawable)
            utility_name = "Drenaje" if utility == "DRENAJE" else "Eléctrico"
            parts.append(_tr("{n} rutas ({m} tramos) de {u}").format(
                n=len(pipes), m=n_seg, u=utility_name))
        msg = (_tr("Importadas: {items}.").format(items="; ".join(parts))
               if parts else _tr("Importadas estructuras reconocidas."))
        if n_geo:
            msg += " " + _tr("Estructuras con medidas: {g}.").format(g=n_geo)
            if n_alone:
                msg += " " + _tr("({a} sin línea, importadas como cajas sueltas.)").format(a=n_alone)
        if n_cv:
            msg += " " + _tr("Codos como esquina + radio (CV): {c}.").format(c=n_cv)
        n_ab = sum(1 for _r, _u, pipes, _s, _k in batches for p in pipes if p.get("ab"))
        if n_ab:
            msg += " " + _tr("Abandonadas (AB): {a}.").format(a=n_ab)
        snapped = sum(row[3] for row in batches); skipped = sum(row[4] for row in batches)
        if snapped or skipped:
            msg += " " + _tr("Estructuras: {s} en líneas, {k} sin pipe cercana.").format(
                s=snapped, k=skipped)
        if n_hidden:
            msg += " " + _tr("Quiebres sin bóveda: {h} (cajas ocultas).").format(h=n_hidden)
        self._info(msg)

    def _load_page(self, idx):
        self._close_editor()
        page = self.doc[idx]; self.page_idx = idx; self.scale = VP.detect_scale(page)
        if self._scale_override:        # hoja compuesta: escala única elegida en el compositor
            self.scale = float(self._scale_override)
        self.rot = page.rotation; mbx = page.mediabox; self.W, self.H = mbx.width, mbx.height
        self.derot = page.derotation_matrix
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        self.pageH_px = pix.height
        # tamaño de marca acotado: evita textos/Multileaders gigantes por escala mal detectada
        self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
        buf = bytes(pix.samples)
        qimg = QtGui.QImage(buf, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888).copy()
        arr = np.frombuffer(buf, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3].reshape(pix.height, pix.width, 3)
        self.gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)
        self._overlay = []
        self.canvas.set_image(qimg)
        self._reset_model(); self._update_page_label()
        self._refresh_scale_label()
        self._info(f"Página {idx + 1} cargada.")

    def _reset_model(self):
        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.ref_centerlines = []; self._cl_pts = []
        self.duct_banks = []
        self.cross_connections = []
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        self.sel_cl = -1
        self._overlay = []; self._close_editor(); self._dirty = False; self._extending = False
        self.georef = georef_mod.Georef()          # cada página/PDF nuevo empieza sin georreferencia
        self._undo.clear(); self._redo.clear()
        self.set_mode("idle"); self._refresh_lists(); self._redraw(); self._update_geo_status()

    # ─────────────────────────── proyecto ───────────────────────────
    def _write_project(self, path):
        self._busy("Guardando proyecto…")
        try:
            # La construcción del dict de datos vive en project_io (pura, testeable);
            # aquí queda solo lo de Qt/PDF (PNG del lienzo, zip, PDF fuente).
            model = project_io.build_model_dict(self)
            ba = QtCore.QByteArray(); buf = QtCore.QBuffer(ba); buf.open(QtCore.QIODevice.WriteOnly)
            self.canvas.pixmap_item.pixmap().save(buf, "PNG")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("model.json", json.dumps(model)); z.writestr("page.png", bytes(ba))
                pdf_bytes = self._get_pdf_bytes()
                if pdf_bytes:
                    z.writestr("source.pdf", pdf_bytes)
                for i, source in enumerate(self.sheet_external_pdfs):
                    z.writestr(f"external/{i:03d}.pdf", source["data"])
                # Hoja compuesta: los PDFs de origen completos, para poder
                # volver al compositor (source.pdf ya es la hoja materializada).
                if self.composite is not None and (
                        len(self.src_pdfs) > 1 or not self.composite.is_single_full_page()):
                    for i, entry in enumerate(self.src_pdfs):
                        z.writestr(f"sources/{i:03d}.pdf", entry["data"])
            self.project_path = path; self._dirty = False; self._update_title()
            self._info(f"Proyecto guardado: {os.path.basename(path)}")
            self._flash_save()
        finally: self._unbusy()

    def _flash_save(self):
        t = _theme.tokens()
        self.lbl_info.setStyleSheet(f"color:{t.success};font-weight:bold;")
        QtCore.QTimer.singleShot(2000, lambda: self.lbl_info.setStyleSheet(f"color:{t.text_info};"))

    def _get_pdf_bytes(self):
        if self.doc:
            try: return self.doc.tobytes(deflate=True)
            except Exception: pass
        if self.pdf_path and os.path.isfile(self.pdf_path):
            try:
                with open(self.pdf_path, "rb") as f: return f.read()
            except Exception: pass
        return None

    def _cleanup_tmp_pdf(self):
        self._cleanup_tmp_composite()
        tmp = getattr(self, '_tmp_pdf', None)
        if tmp and os.path.isfile(tmp):
            try: os.remove(tmp)
            except Exception: pass
        self._tmp_pdf = None

    def save_project(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Nada que guardar"), _tr("Abre un PDF o proyecto primero.")); return
        if self.project_path: self._write_project(self.project_path)
        else: self.save_project_as()

    def save_project_as(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Nada que guardar"), _tr("Abre un PDF o proyecto primero.")); return
        base = self.project_path or os.path.join(DOWNLOADS, "proyecto.digproj")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar proyecto como", base, "Proyecto (*.digproj)")
        if path: self._write_project(path)

    def open_project(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir proyecto", DOWNLOADS, "Proyecto (*.digproj)")
        if path: self._open_project_path(path)

    def _open_project_path(self, path):
        if not self._confirm_discard(): return
        self._busy("Abriendo proyecto…")
        try:
            if self.doc:
                self.doc.close()
                self.doc = None
            self._cleanup_tmp_pdf()
            with zipfile.ZipFile(path) as z:
                model = json.loads(z.read("model.json")); png = z.read("page.png")
                external_pdfs = [
                    {"name": entry.get("name", f"PDF {i + 2}"),
                     "data": z.read(f"external/{i:03d}.pdf")}
                    for i, entry in enumerate(model.get("sheet_sources", [])[1:])]
                src_bytes = z.read("source.pdf") if "source.pdf" in z.namelist() else None
                if src_bytes is not None:
                    tmp_pdf = path + ".src.pdf"
                    with open(tmp_pdf, "wb") as fp: fp.write(src_bytes)
                    self._tmp_pdf = tmp_pdf
                else:
                    tmp_pdf = None
                src_names = model.get("src_names") or []
                src_pdfs = [{"name": src_names[i] if i < len(src_names) else f"PDF {i + 1}",
                             "data": z.read(f"sources/{i:03d}.pdf")}
                            for i in range(len(src_names)) if f"sources/{i:03d}.pdf" in z.namelist()]
            qimg = QtGui.QImage.fromData(png, "PNG")
            self._overlay = []; self._close_editor()
            self.canvas.set_image(qimg); self.gray = qimage_to_gray(qimg)
            # Normalización de los datos (casteo de cotas por vértice, zonas de
            # borrado, reconstrucción de Georef) vive en project_io (pura, testeable);
            # aquí solo se ASIGNAN a self.* y se hace lo de Qt/PDF.
            data = project_io.parse_model(model)
            self.scale = data["scale"]; self.zoom = data["zoom"]; self.rot = data["rot"]
            self.W, self.H = data["W"], data["H"]; self.derot = fitz.Matrix(*data["derot"])
            self.pageH_px = qimg.height()
            self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
            if tmp_pdf:
                self.pdf_path = tmp_pdf; self.doc = fitz.open(tmp_pdf)
            else:
                self.pdf_path = None; self.doc = None
            self.work_pdf_path = tmp_pdf
            self.composite = data.get("composite")
            self._scale_override = data.get("scale_override")
            if src_pdfs:
                self.src_pdfs = src_pdfs
            elif src_bytes is not None:
                self.src_pdfs = [{"name": model.get("pdf_name") or "PDF principal", "data": src_bytes}]
            else:
                self.src_pdfs = []
            self.project_path = path
            self.sheet_external_pdfs = external_pdfs
            self.sheet_sources = data.get("sheet_sources") or (
                [{"name": model.get("pdf_name") or "PDF principal",
                  "start": 0, "count": self.doc.page_count}] if self.doc else [])
            total = sum(source["count"] for source in self.sheet_sources)
            self.sheet_layout = normalize_sheet_layout(
                data.get("sheet_layout"), total) if self.doc else None
            self.sheet_rotations = normalize_rotations(
                data.get("sheet_rotations"), self.sheet_layout) if self.sheet_layout else {}
            self.sheet_crops = normalize_sheet_crops(
                data.get("sheet_crops"), self.sheet_layout) if self.sheet_layout else {}
            self.hidden_ocgs_by_source = data.get("hidden_ocgs_by_source", {})
            self.hidden_ocgs = list(data.get("hidden_ocgs") or self.hidden_ocgs_by_source.get("0", []))
            if self.doc and (self.hidden_ocgs or "0" in self.hidden_ocgs_by_source):
                import pdf_layers as _pdf_layers
                _pdf_layers.set_hidden(self.doc, self.hidden_ocgs)
            self.page_idx = data.get("page_idx", 0)
            if self.doc and not 0 <= self.page_idx < self.doc.page_count:
                self.page_idx = 0
            self._update_title()
            self.pipes = data["pipes"]; self.leaders = data["leaders"]
            self.text_marks = data["text_marks"]
            self.erase_regions = data["erase_regions"]
            self.structures = data["structures"]
            self.ref_centerlines = data["ref_centerlines"]
            self.duct_banks = data.get("duct_banks", [])
            self.cross_connections = data.get("cross_connections", []) or []
            self.georef = data["georef"]
            self.work_unit = data["work_unit"]
            self.cur_pts = []; self._erase_pts = []; self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
            self._undo.clear(); self._redo.clear(); self._dirty = False
            self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._redraw()
            self._refresh_scale_label(); self._update_geo_status()
            self._refresh_unit_labels()
            # Reponer la versión/idioma de Civil 3D con que se guardó el proyecto
            # (si esa versión sigue instalada). Debe ir ANTES de _warn_missing_families.
            self._restore_civil_selection(model.get("civil_year"), model.get("civil_lang"))
            import civil_catalog as _cc
            _cv = f" · Civil 3D {self.civil_year}/{_cc._current_lang or '—'}" if self.civil_year else ""
            self._info(f"Proyecto abierto ({len(self.pipes)} utilidades){_cv}. Ctrl+S guarda en este mismo archivo.")
            # Aviso si el proyecto referencia familias del catálogo que no están
            # instaladas en el Civil 3D activo — ofrece abrir el instalador.
            self._warn_missing_families()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
        finally: self._unbusy()

    def _warn_missing_families(self):
        """Recorre pipes y structures del proyecto actual, junta los `pipe_family`
        y `part` que están seteados y compara contra las familias que existen en
        el catálogo Civil 3D del año/idioma actualmente seleccionados. Si alguno
        falta, muestra un aviso con opción de abrir el diálogo de instalación."""
        if not self.civil_year: return
        try:
            import civil_catalog as _cc
        except Exception:
            return
        # Set de fids conocidos por tipo. `id` es el mismo string que la app usó
        # al guardar el proyecto (basename del .xml para pipes/structures; y
        # "<subcat>|<PART_FAMILY_NAME>" para pressure).
        try:
            grav_ids = {f["id"] for f in _cc.imperial_pipes(self.civil_year)}
            struct_ids = {f["id"] for f in _cc.imperial_structures(self.civil_year)}
            pressure_ids = {f["id"] for f in _cc.pressure_pipes(self.civil_year)}
        except Exception:
            return

        missing_p, missing_s = [], []
        for p in self.pipes:
            fid = (p.get("pipe_family") or "").strip()
            if not fid: continue
            kind = self._pipe_net_kind(p) if hasattr(self, "_pipe_net_kind") else (p.get("net") or "gravity")
            pool = pressure_ids if kind == "pressure" else grav_ids
            if fid not in pool: missing_p.append(fid)
        for s in self.structures:
            fid = (s.get("part") or "").strip()
            if fid and fid not in struct_ids: missing_s.append(fid)

        missing = sorted(set(missing_p) | set(missing_s))
        if not missing: return

        lines = ["<b>Este proyecto usa familias del catálogo que no están instaladas "
                 f"en Civil 3D {self.civil_year} ({_cc._current_lang or '?'}):</b>", ""]
        for m in missing[:25]: lines.append(f"  • <code>{m}</code>")
        if len(missing) > 25: lines.append(f"  … y {len(missing)-25} más.")
        lines += ["", "¿Quieres abrir el instalador de familias ahora? "
                       "Puedes seguir trabajando con el proyecto igual — el aviso es "
                       "solo para evitar sorpresas al exportar a DXF."]

        mb = QtWidgets.QMessageBox(self)
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setWindowTitle("Familias no instaladas")
        mb.setTextFormat(QtCore.Qt.RichText)
        mb.setText("<br>".join(lines))
        btn_install = mb.addButton("Instalar familias…", QtWidgets.QMessageBox.AcceptRole)
        mb.addButton("Seguir sin instalar", QtWidgets.QMessageBox.RejectRole)
        mb.exec()
        if mb.clickedButton() is btn_install:
            self.open_install_family_dialog()

    def _confirm_discard(self):
        if not self._dirty or self.canvas.pixmap_item is None: return True
        r = QtWidgets.QMessageBox.question(
            self, "Cambios sin guardar", "Hay cambios sin guardar. ¿Deseas guardarlos?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if r == QtWidgets.QMessageBox.Cancel: return False
        if r == QtWidgets.QMessageBox.Save:
            self.save_project(); return not self._dirty
        return True

    def close_project(self):
        if self.canvas.pixmap_item is None: return
        if not self._confirm_discard(): return
        if self.doc:
            self.doc.close()
        self._cleanup_tmp_pdf()
        self.canvas.scene().clear(); self.canvas.pixmap_item = None; self.canvas.pdf_bg_item = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.gray = None; self._update_title()
        self.sheet_layout = None
        self.sheet_rotations = {}
        self.sheet_crops = {}
        self.sheet_sources = []
        self.sheet_external_pdfs = []
        self.hidden_ocgs_by_source = {}
        self.hidden_ocgs = []
        self.pipes = []; self.leaders = []; self.text_marks = []; self.erase_regions = []; self.structures = []
        self.duct_banks = []; self.cross_connections = []
        self.ref_centerlines = []; self._cl_pts = []
        self.cur_pts = []; self._erase_pts = []; self._overlay = []; self._close_editor()
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = self.sel_cl = self.sel_db = -1
        self._undo.clear(); self._redo.clear(); self._dirty = False
        self.georef = georef_mod.Georef()
        self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._info(_tr("Proyecto cerrado."))

    def closeEvent(self, e):
        if self._confirm_discard():
            if self.doc:
                self.doc.close()
            self._cleanup_tmp_pdf(); e.accept()
        else: e.ignore()

    # ─────────────────────────── clics ───────────────────────────
    def on_click(self, x, y, button):
        if self.canvas.pixmap_item is None: return
        if button == QtCore.Qt.RightButton:
            if self.mode == "pipe": self.finish_pipe()
            elif self.mode == "erase": self.finish_erase()
            elif self.mode == "centerline": self.finish_centerline()
            elif self.mode == "move": self._delete_vertex(x, y)
            return
        # Left-click sobre una marca de conflicto (círculo amarillo con !):
        # abre el diálogo de aprobación para conectar con válvula. Tiene
        # prioridad sobre cualquier otro modo — el usuario no debe estar
        # esperando resolver un conflicto y que el click empiece a dibujar.
        if button == QtCore.Qt.LeftButton and self.mode != "pipe":
            if self._try_click_conflict(x, y):
                return
        if self.mode == "pipe":
            self._push(); self.cur_pts.append(self._pipe_snap_and_ask(x, y)); self._update_ui(); self._redraw()
        elif self.mode == "erase":
            self._erase_pts.append((x, y)); self._update_ui(); self._redraw()
        elif self.mode == "centerline":
            self._push(); self._cl_pts.append(self._snap(x, y)); self._update_ui(); self._redraw()
        elif self.mode == "text":
            if self._editor is not None: return   # el clic confirma el texto abierto (no abre otro)
            self._new_free_text(x, y)
        elif self.mode == "leader1":
            self._pending["arrow"] = self._snap(x, y); self.mode = "leader2"; self._update_ui()
        elif self.mode == "leader2":
            hx, hy = self._pending["arrow"]; o = self.orient_combo.currentData()
            if o == "d":                                 # diagonal: 2º clic = inicio del landing (bisagra)
                self._pending["landing"] = self._snap(x, y); self.mode = "leader3"; self._update_ui(); return
            tail = (x, hy) if o == "h" else (hx, y)      # h/v: 2º clic = final del cuerpo, recto al eje
            self._add_simple_leader((hx, hy), tail, o); return
        elif self.mode == "leader3":                         # Leader diagonal: 3er clic = final del cuerpo
            self._add_simple_leader(self._pending["arrow"], (x, y), "d",
                                    landing=self._pending.get("landing")); return
        elif self.mode == "insert_bz":
            self._do_insert_manhole(x, y)
        elif self.mode == "idle":
            self._pick(x, y)

    def _add_simple_leader(self, head, tail, orient, landing=None):
        """Coloca un Leader simple (solo flecha, sin texto) y queda listo para el siguiente.
        orient 'h'/'v' → 2 clics (cabeza→final del cuerpo, recto al eje).
        orient 'd'     → 3 clics (cabeza → inicio del landing/bisagra → final del cuerpo)."""
        self._push()
        self.leaders.append({"text": "", "orient": orient, "simple": True,
                             "arrow": head, "tp": tail if tail else head, "landing": landing,
                             "font": self.font_combo.currentFont().family(),
                             "size_ft": self.size_spin.value(), "bold": self.chk_bold.isChecked()})
        self._pending = {"arrow": None, "simple": True}; self.mode = "leader1"
        self._refresh_lists(); self._update_ui(); self._redraw()
        self._info(_tr("Leader colocado. Clic en la cabeza de flecha del siguiente (Esc para salir)."))

    def on_dblclick(self, x, y):
        if self.mode not in ("idle", "move"): return
        thr = 14.0 / max(1e-6, self.canvas.transform().m11())
        for i, ld in enumerate(self.leaders):
            if not (ld.get("arrow") and ld.get("tp")): continue
            geo = self._leader_geo(ld); lx, ly = geo["label_pos"]; H = geo["H"]
            lines = ld["text"].split("\n"); tw = max((len(s) for s in lines), default=1) * H * 0.55; th = len(lines) * H
            hit_text = (lx - 8 <= x <= lx + tw + 8 and ly - 8 <= y <= ly + th + 8)
            if hit_text or math.hypot(ld["tp"][0] - x, ld["tp"][1] - y) < thr:
                self._edit_leader_text(i); return
        for i, tm in enumerate(self.text_marks):
            if self._text_hit(tm, x, y):
                self._edit_text_mark(i); return

    def _text_hit(self, tm, x, y):
        h = self._px_for_ft(tm["size_ft"]) if "size_ft" in tm else tm.get("h", 16)
        lines = tm["text"].split("\n")
        w = max((len(s) for s in lines), default=1) * h * 0.55; th = len(lines) * h
        px, py = tm["pos"]; return px - 6 <= x <= px + w + 6 and py - 6 <= y <= py + th + 6

    def _pick(self, x, y):
        thr = 10.0 / max(1e-6, self.canvas.transform().m11())
        bz_thr = 18.0 / max(1e-6, self.canvas.transform().m11())
        curve_thr = 22.0 / max(1e-6, self.canvas.transform().m11())
        best_bz, bd_bz = -1, bz_thr
        for i, s in enumerate(self.structures):
            if s.get("world") or s.get("hidden"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            d = math.hypot(x - sx, y - sy)
            local_thr = curve_thr if s.get("curve") else bz_thr
            if d < local_thr and d < bd_bz: bd_bz, best_bz = d, i
        # Hit-test extra sobre el ARCO REAL de cada elemento curvo. Sin esto
        # el usuario tiene que clickear justo en el vértice esquina (chico);
        # con esto puede hacer clic en cualquier parte del arco visible.
        arc_thr = thr * 1.5
        for i, s in enumerate(self.structures):
            if not s.get("curve") or s.get("world") or s.get("hidden"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            pipe = self._pipe_at_vertex(sx, sy)
            info = self._curve_arc_info(s, pipe) if pipe else None
            if info is None: continue
            arc_pts = self._arc_polyline(info, n_per_90=12)
            for a, b in zip(arc_pts, arc_pts[1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < arc_thr and d < bd_bz:
                    bd_bz, best_bz = d, i
        if best_bz >= 0:
            self._no_center = True
            if self.structures[best_bz].get("curve"):
                self._show_tab(TAB_CURVE); self.curve_list.setCurrentRow(self._curve_rows.index(best_bz))
            else:
                self._show_tab(TAB_BZ); self.bz_list.setCurrentRow(self._bz_rows.index(best_bz))
            self._no_center = False; return
        for i, tm in enumerate(self.text_marks):        # textos primero (blancos pequeños)
            if self._text_hit(tm, x, y):
                self._no_center = True; self._show_tab(TAB_TEXT); self.txt_marks_list.setCurrentRow(i)
                self._no_center = False; return
        for i, ld in enumerate(self.leaders):           # leaders: por la línea o el texto
            if not (ld.get("arrow") and ld.get("tp")): continue
            geo = self._leader_geo(ld); hit = False
            for s in geo["segs"]:
                for a, b in zip(s, s[1:]):
                    if G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1]) < thr: hit = True; break
                if hit: break
            lx, ly = geo["label_pos"]; H = geo["H"]
            tw = max((len(t) for t in ld["text"].split("\n")), default=1) * H * 0.6; tt = ld["text"].count("\n") + 1
            if not hit and lx - 8 <= x <= lx + tw + 8 and ly - 8 <= y <= ly + tt * H + 8: hit = True
            if hit:
                self._select_leader(i); return
        best_cl, bd_cl = -1, thr
        for i, c in enumerate(self.ref_centerlines):
            pts = c.get("pts") or []
            for a, b in zip(pts, pts[1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < bd_cl: bd_cl, best_cl = d, i
        if best_cl >= 0:
            self._no_center = True; self._show_tab(TAB_CL); self.cl_list.setCurrentRow(best_cl)
            self._no_center = False; return
        best, bd = -1, thr
        for i, p in enumerate(self.pipes):
            if not p.get("pts"): continue               # tramos importados (world) no están en el lienzo
            for a, b in zip(p["pts"], p["pts"][1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < bd: bd, best = d, i
        if best >= 0:
            self._no_center = True; self._show_tab(TAB_PIPE); self.pipe_list.setCurrentRow(best)
            self._no_center = False

    def _snap(self, x, y):
        if not self.snap: return (x, y)
        return G.snap_point(self.gray, x, y, self.snap_r)

    def _pipe_soft_snap(self, x, y, layer=None):
        """Snap suave a utilidades EXISTENTES del mismo tipo (capa) mientras se
        dibuja una nueva. Busca dentro de un radio en pixels de pantalla el
        candidato más cercano y devuelve un dict:
            {"pt": (x, y), "kind": "endpoint"|"vertex"|"segment",
             "pipe_idx": int, "port": int}
        `port` es 0 para start, len(pts)-1 para end (endpoints), o el índice
        del vértice interno (vertex), o el índice del segmento inicio (segment).
        Devuelve None si no hay nada cerca.

        Sólo compara contra pipes cuya capa == `layer` (o self.active_layer()
        si no se pasa). Radio de snap = 12 px de pantalla, convertidos a
        unidades de escena según el zoom actual."""
        lay = layer or self.active_layer()
        m11 = max(1e-6, self.canvas.transform().m11())
        tol = 12.0 / m11
        best = None; best_d2 = tol * tol
        for pi, p in enumerate(self.pipes):
            if p.get("layer") != lay: continue
            pts = p.get("pts") or []
            n = len(pts)
            if n < 2: continue
            # 1) Vértices (endpoints + intermedios).
            for vi, (vx, vy) in enumerate(pts):
                d2 = (vx - x) ** 2 + (vy - y) ** 2
                if d2 < best_d2:
                    kind = "endpoint" if (vi == 0 or vi == n - 1) else "vertex"
                    best = {"pt": (vx, vy), "kind": kind, "pipe_idx": pi, "port": vi}
                    best_d2 = d2
            # 2) Proyección perpendicular sobre cada segmento.
            for si in range(n - 1):
                ax, ay = pts[si]; bx, by = pts[si + 1]
                dx, dy = bx - ax, by - ay
                seg_len2 = dx * dx + dy * dy
                if seg_len2 < 1e-9: continue
                t = ((x - ax) * dx + (y - ay) * dy) / seg_len2
                if t <= 0 or t >= 1: continue      # los extremos ya se cubren arriba
                px = ax + t * dx; py = ay + t * dy
                d2 = (px - x) ** 2 + (py - y) ** 2
                if d2 < best_d2:
                    best = {"pt": (px, py), "kind": "segment", "pipe_idx": pi, "port": si}
                    best_d2 = d2
        return best

    def _pipe_snap_and_ask(self, x, y):
        """Aplica el snap suave para el modo Dibujar. Si el snap cae en el
        EXTREMO de una utilidad existente del mismo tipo y es el PRIMER click
        de la nueva utilidad, pregunta si el usuario quiere unirla como parte
        de esa utilidad (extenderla) o crear una nueva independiente.

        Devuelve (x, y) del punto a usar. Si el usuario eligió "unir", además
        deja `_extending`/`_ext_pipe`/`_ext_at` armados como si hubiera venido
        del comando F, para que `finish_pipe` haga el append correcto."""
        hit = self._pipe_soft_snap(x, y)
        if hit is None:
            return self._snap(x, y)
        sx, sy = hit["pt"]
        # Sólo pregunta si es el primer click (cur_pts vacío) y el snap es a
        # un EXTREMO (unir a mitad de segmento no tiene sentido en polilíneas).
        first_click = not self.cur_pts and not self._extending
        if first_click and hit["kind"] == "endpoint":
            resp = QtWidgets.QMessageBox.question(
                self, _tr("Unir a utilidad existente"),
                _tr("El punto donde estás dibujando coincide con el extremo de otra "
                    "utilidad del mismo tipo.\n\n"
                    "¿Quieres UNIRLA como parte de esa utilidad (misma polilínea, "
                    "una sola red)?\n\n"
                    "Sí = extiende la utilidad existente.\n"
                    "No = crea una utilidad nueva que la toca (juntura automática al importar)."),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if resp == QtWidgets.QMessageBox.Yes:
                pi = hit["pipe_idx"]; port = hit["port"]
                pep = self.pipes[pi]
                self._extending = True
                self._ext_pipe = pi
                self._ext_layer = pep.get("layer", "")
                self._ext_at = "start" if port == 0 else "end"
        return (sx, sy)

    # ─────────────────────────── editar / mover ───────────────────────────
    def _current_kind(self):
        ti = self._current_tab()
        if ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes): return "pipe"
        if ti == TAB_LEADER and 0 <= self.sel_leader < len(self.leaders) and self.leaders[self.sel_leader].get("simple"): return "leader"
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): return "text"
        if ti == TAB_REGION and 0 <= self.sel_region < len(self.erase_regions): return "region"
        return None

    def enter_move(self):
        kind = self._current_kind()
        # Ctrl+T con un Leader simple seleccionado: asegura la pestaña Leaders y entra a editar sus vértices
        if not kind and 0 <= self.sel_leader < len(self.leaders) and self.leaders[self.sel_leader].get("simple"):
            self._select_leader(self.sel_leader, center=True); kind = "leader"
        if kind == "leader":
            self.set_mode("move"); self._info(_tr("Editar Leader: arrastra un vértice (posición/longitud) o el trazo para mover. Enter/Esc termina."))
        elif kind:
            self.set_mode("move"); self._info(_tr("Arrastra para mover · clic en vértice extiende (F) · clic derecho elimina"))
        else:
            self._info(_tr("Selecciona primero una utilidad, Leader, texto o zona"))

    def _thr(self): return 12.0 / max(1e-6, self.canvas.transform().m11())

    def _segments(self, pts, closed):
        segs = list(zip(range(len(pts) - 1), pts, pts[1:]))
        if closed and len(pts) >= 3: segs.append((len(pts) - 1, pts[-1], pts[0]))
        return segs

    def begin_move(self, x, y):
        kind = self._current_kind()
        if not kind: return
        self._push(); self._moved = False; self._move_kind = kind
        self._press_xy = (x, y); self._last_xy = (x, y); thr = self._thr()
        if kind == "text":
            self._move0 = (x, y); self._drag_vertex = None; self._edit_pts = None; return
        if kind == "leader":
            ld = self.leaders[self.sel_leader]; self._edit_leader = ld
            pts = [tuple(ld["arrow"])]
            if ld.get("landing"): pts.append(tuple(ld["landing"]))
            pts.append(tuple(ld["tp"]))
            self._edit_pts = pts; self._edit_closed = False
            vi, vd = -1, thr
            for i, (px, py) in enumerate(pts):
                d = math.hypot(px - x, py - y)
                if d < vd: vd, vi = d, i
            self._drag_vertex = vi if vi >= 0 else None       # vértice cercano → arrastra; si no, mueve todo
            self._move0 = None if vi >= 0 else (x, y); return
        pts = self.pipes[self.sel_pipe]["pts"] if kind == "pipe" else self.erase_regions[self.sel_region]["pts"]
        if not pts: return                              # tramo importado (world): no editable en el lienzo
        self._edit_pts = pts; self._edit_closed = (kind == "region")
        vi, vd = -1, thr
        for i, (px, py) in enumerate(pts):
            d = math.hypot(px - x, py - y)
            if d < vd: vd, vi = d, i
        if vi >= 0:
            self._drag_vertex = vi; self._move0 = None; return
        si, sd = -1, thr
        for idx, a, b in self._segments(pts, self._edit_closed):
            d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
            if d < sd: sd, si = d, idx
        if si >= 0:
            pts.insert(si + 1, (x, y)); self._drag_vertex = si + 1; self._move0 = None; self._moved = True
            if kind == "pipe":
                p = self.pipes[self.sel_pipe]; ov = p.get("vertex_inv")
                if ov:                          # reindexar: todo lo que estaba después del corte sube uno
                    p["vertex_inv"] = {(k + 1 if k >= si + 1 else k): v for k, v in ov.items()}
                self._rebuild_seg_inv_table(p)
            self._refresh_lists(); return
        self._drag_vertex = None; self._move0 = (x, y)

    def do_move(self, x, y):
        self._moved = True; self._last_xy = (x, y)
        if self._move_kind == "text" and 0 <= self.sel_text < len(self.text_marks):
            if self._move0:
                dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
                px, py = self.text_marks[self.sel_text]["pos"]
                self.text_marks[self.sel_text]["pos"] = (px + dx, py + dy); self._redraw()
            return
        if self._move_kind == "leader":
            pts = self._edit_pts
            if pts is None: return
            if self._drag_vertex is not None:
                pts[self._drag_vertex] = (x, y)               # mueve un vértice (posición/longitud)
            elif self._move0 is not None:
                dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
                for i in range(len(pts)): pts[i] = (pts[i][0] + dx, pts[i][1] + dy)
            else:
                return
            self._sync_leader(); self._redraw(); return
        pts = self._edit_pts
        if pts is None: return
        if self._drag_vertex is not None:
            pts[self._drag_vertex] = (x, y); self._redraw(); return
        if self._move0 is not None:
            dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
            for i in range(len(pts)): pts[i] = (pts[i][0] + dx, pts[i][1] + dy)
            self._redraw()

    def end_move(self):
        # clic (casi sin arrastrar) sobre un vértice de una tubería → extender
        dist = math.hypot(self._last_xy[0] - self._press_xy[0], self._last_xy[1] - self._press_xy[1]) \
            if (self._last_xy and self._press_xy) else 0
        if (self._move_kind == "pipe" and self._drag_vertex is not None and dist < 6
                and 0 <= self.sel_pipe < len(self.pipes)):
            self._move0 = None; self._move_kind = None
            self._start_extension(self.sel_pipe, self._drag_vertex); self._drag_vertex = None; return
        self._move0 = None; self._drag_vertex = None; self._move_kind = None; self._edit_leader = None

    def _sync_leader(self):
        """Vuelca los vértices editados (self._edit_pts) al leader (arrow / landing / tp)."""
        ld = self._edit_leader; pts = self._edit_pts
        if not ld or not pts: return
        ld["arrow"] = pts[0]
        if ld.get("landing"): ld["landing"] = pts[1]; ld["tp"] = pts[2]
        else: ld["tp"] = pts[-1]

    def _start_extension(self, pi, vi):
        # Sin ventana emergente: la casilla 'continuar la misma utilidad' decide.
        pts = self.pipes[pi]["pts"]; vpos = tuple(pts[vi]); is_end = (vi == 0 or vi == len(pts) - 1)
        same = self.chk_ext_same.isChecked() and is_end
        self._extending = True; self._ext_layer = self.pipes[pi]["layer"]; self.cur_pts = [vpos]
        if same:
            self._ext_pipe = pi; self._ext_at = "start" if vi == 0 else "end"
            self._info(_tr("Continuando la MISMA utilidad: clic para agregar puntos, Enter finaliza."))
        else:
            self._ext_pipe = None; self._ext_at = None
            if self.chk_ext_same.isChecked() and not is_end:
                self._info(_tr("Solo desde un extremo se continúa; se creará una utilidad NUEVA. Clic para agregar, Enter finaliza."))
            else:
                self._info(_tr("Utilidad NUEVA (rama en F): clic para agregar puntos, Enter finaliza."))
        self.set_mode("pipe")

    def _delete_vertex(self, x, y):
        kind = self._current_kind()
        if kind not in ("pipe", "region"): return
        pts = self.pipes[self.sel_pipe]["pts"] if kind == "pipe" else self.erase_regions[self.sel_region]["pts"]
        floor = 3 if kind == "region" else 2
        if len(pts) <= floor: self._info(f"Necesita al menos {floor} puntos"); return
        thr = self._thr(); vi, vd = -1, thr
        for i, (px, py) in enumerate(pts):
            d = math.hypot(px - x, py - y)
            if d < vd: vd, vi = d, i
        if vi >= 0:
            self._push(); pts.pop(vi)
            if kind == "pipe":
                p = self.pipes[self.sel_pipe]; ov = p.get("vertex_inv")
                if ov:                          # reindexar: el vértice vi ya no existe, los de más allá bajan uno
                    p["vertex_inv"] = {(k - 1 if k > vi else k): v for k, v in ov.items() if k != vi}
                self._rebuild_seg_inv_table(p)
            self._refresh_lists(); self._redraw(); self._info(_tr("Vértice eliminado"))

    # ─────────────────────────── utilidades ───────────────────────────
    def finish_pipe(self):
        if self._extending and self._ext_pipe is not None and 0 <= self._ext_pipe < len(self.pipes):
            extra = self.cur_pts[1:]                       # el 1er punto es el vértice existente
            if extra:
                self._push(); pep = self.pipes[self._ext_pipe]; pts = pep["pts"]
                if self._ext_at == "end": pts.extend(extra)
                else:
                    pep["pts"] = list(reversed(extra)) + pts
                    ov = pep.get("vertex_inv")             # todo lo existente se corre len(extra) a la derecha
                    if ov: pep["vertex_inv"] = {k + len(extra): v for k, v in ov.items()}
        elif len(self.cur_pts) >= 2:
            layer = self._ext_layer if self._extending else self.active_layer()
            ab = False if self._extending else self.chk_ab.isChecked()
            self._push(); self.pipes.append({"layer": layer, "pts": self.cur_pts[:], "ab": ab,
                                             "diam": float(PIPE_DIAMETERS_IN[0]), "diam_unit": "in",
                                             "material": DEFAULT_PIPE_MATERIAL})
        self.cur_pts = []; self._extending = False; self._ext_layer = None; self._ext_pipe = None; self._ext_at = None
        self._refresh_lists(); self._update_ui(); self._redraw()

    def _sel_pipe(self, r):
        """Se llama cuando el usuario selecciona una utilidad en el inventario
        (lista derecha). Actualiza el panel de Propiedades con SUS datos.

        `self._prop_guard` es un pequeño truco: bloquea temporalmente los
        callbacks de los campos mientras los rellenamos con valores. Sin él,
        `setValue`/`setText` dispararía `_prop_changed()` y guardaría los
        datos ANTES de terminar de cargarlos (círculo vicioso)."""
        self.sel_pipe = r
        if 0 <= r < len(self.pipes):
            p = self.pipes[r]; pts = p.get("pts")
            if not self._no_center and pts:                # los tramos importados (world) no tienen pts
                # Solo re-centrar si el pipe NO está ya visible en la vista
                # actual — evita saltos innecesarios que desorientan al usuario
                # cuando la utilidad ya se ve en pantalla.
                view_rect = self.canvas.mapToScene(self.canvas.viewport().rect()).boundingRect()
                xs = [x for (x, _) in pts]; ys = [y for (_, y) in pts]
                pipe_rect = QtCore.QRectF(QtCore.QPointF(min(xs), min(ys)),
                                          QtCore.QPointF(max(xs), max(ys)))
                if not view_rect.intersects(pipe_rect):
                    mid = pts[len(pts) // 2]; self.canvas.centerOn(mid[0], mid[1])
            self._prop_guard = True
            self.prop_name.setText(p.get("name", ""))
            # El diámetro se deriva del "Tamaño" del catálogo (elegido más abajo).
            self.prop_part.setText(p.get("part", ""))
            self.prop_inv0.setValue(p.get("inv_start") or 0.0); self.prop_inv1.setValue(p.get("inv_end") or 0.0)
            # findData por VALOR real (no por texto traducido) — así el mapeo
            # material↔selección es estable aunque el usuario cambie idioma.
            mi = self.prop_material.findData(p.get("material") or DEFAULT_PIPE_MATERIAL)
            if mi < 0:
                mi = self.prop_material.findText(p.get("material") or DEFAULT_PIPE_MATERIAL)
            self.prop_material.setCurrentIndex(mi if mi >= 0 else 0)
            # findData busca el índice del combo cuya "data" (dato oculto) coincide
            # con "" | "pipe" | "pressure"; si no encuentra devuelve -1 → índice 0.
            idx = self.prop_nettype.findData(p.get("net_type", "") or "")
            self.prop_nettype.setCurrentIndex(idx if idx >= 0 else 0)
            self._reload_pipe_families(p)
            self._prop_guard = False
            self._rebuild_seg_inv_table(p)
        else:
            self.gprop_segs.setVisible(False)
        # Repinta la lista de bancoductos para actualizar qué fila queda en
        # negrita/acento (la asignada a esta tubería).
        if hasattr(self, "_refresh_db_list"):
            self._refresh_db_list()
        self._update_ui(); self._redraw()

    def _interp_vertex_z(self, pts, z_start, z_end, overrides):
        # Interpolación de cota por vértice (pura) en model_ops.
        return model_ops.interp_vertex_z(pts, z_start, z_end, overrides)

    def _rebuild_seg_inv_table(self, p):
        """Reconstruye la tabla de tramos. Cada celda es independiente:
        'Inicio' de tramo N NO sincroniza con 'Fin' de tramo N-1 — el
        usuario puede poner cotas distintas a cada lado del vértice."""
        pts = p.get("pts") or []
        n = len(pts)
        tbl = self.tbl_seg_inv
        tbl.setRowCount(0)
        if p.get("world") or n < 3 or self._current_tab() != TAB_PIPE:
            self.gprop_segs.setVisible(False)
            self.sel_seg_idx = -1
            return
        self.gprop_segs.setVisible(True)
        if id(p) != getattr(self, "_seg_table_pipe_id", None):
            self.sel_seg_idx = -1
        self._seg_table_pipe_id = id(p)
        self._migrate_vertex_inv(p)
        # Estado por-pipe del check "Editar cotas por tramo". Por defecto OFF
        # para que la interfaz no muestre siempre editables las cotas cuando
        # ya tenemos los campos de rasante inicio/fin — el usuario lo activa
        # cuando de verdad quiere editar por tramo.
        seg_edit = bool(p.get("seg_edit_enabled", False))
        self._prop_guard = True
        self.btn_seg_edit.setChecked(seg_edit)
        self.btn_seg_edit.setText(
            "✕  Desactivar edición por tramo" if seg_edit
            else "✎  Activar edición por tramo")
        self._prop_guard = False
        ov_out = p.get("vertex_inv_out") or {}
        ov_in  = p.get("vertex_inv_in") or {}
        z_start = p.get("inv_start") or 0.0; z_end = p.get("inv_end") or 0.0
        auto_z = self._interp_vertex_z(pts, z_start, z_end, ov_out)
        auto_z_in = self._interp_vertex_z(pts, z_start, z_end, ov_in)
        nseg = n - 1
        tbl.setRowCount(nseg)
        for si in range(nseg):
            v0, v1 = si, si + 1
            z0 = ov_out.get(v0, auto_z[v0]) if v0 != 0 else z_start
            z1 = ov_in.get(v1, auto_z_in[v1]) if v1 != n - 1 else z_end
            length = math.hypot(pts[v1][0] - pts[v0][0], pts[v1][1] - pts[v0][1])

            # Etiqueta corta "T1" — la MISMA que se dibuja sobre el tramo en el
            # lienzo, para que el usuario vea la correspondencia de un vistazo.
            # El detalle (vértices) va al tooltip: así la columna es estrecha y
            # la tabla entra sin barra horizontal en el dock.
            item = QtWidgets.QTableWidgetItem(f"T{si + 1}")
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            item.setData(QtCore.Qt.UserRole, si)
            item.setToolTip(f"Tramo {si + 1}: vértice {v0} → vértice {v1}\n"
                            f"Longitud {length:.2f} ft\n"
                            "Clic para resaltarlo en el lienzo.")
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            tbl.setItem(si, 0, item)

            if v0 == 0:
                # Inicio del primer tramo = rasante global (inv_start) — siempre
                # editable, no depende del check per-tramo.
                sp0 = _SegInvSpinBox()
                sp0.setRange(-100000, 100000); sp0.setDecimals(3)
                sp0.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp0.setValue(z0); sp0.setStyleSheet("font-weight: bold;")
                sp0.editingFinished.connect(lambda sp=sp0: self._seg_endpoint_changed("start", sp.value()))
                tbl.setCellWidget(si, 1, sp0)
            else:
                sp0 = _SegInvSpinBox()
                sp0.setRange(-100000, 100000); sp0.setDecimals(3)
                sp0.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp0.setValue(z0)
                if v0 in ov_out: sp0.setStyleSheet("font-weight: bold;")
                sp0.setEnabled(seg_edit)
                sp0.editingFinished.connect(lambda vi=v0, sp=sp0: self._seg_value_changed("out", vi, sp.value()))
                tbl.setCellWidget(si, 1, sp0)

            if v1 == n - 1:
                # Fin del último tramo = rasante global (inv_end) — siempre
                # editable, no depende del check per-tramo.
                sp1 = _SegInvSpinBox()
                sp1.setRange(-100000, 100000); sp1.setDecimals(3)
                sp1.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp1.setValue(z1); sp1.setStyleSheet("font-weight: bold;")
                sp1.editingFinished.connect(lambda sp=sp1: self._seg_endpoint_changed("end", sp.value()))
                tbl.setCellWidget(si, 2, sp1)
            else:
                sp = _SegInvSpinBox()
                sp.setRange(-100000, 100000); sp.setDecimals(3)
                sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp.setValue(z1)
                if v1 in ov_in: sp.setStyleSheet("font-weight: bold;")
                sp.setEnabled(seg_edit)
                sp.editingFinished.connect(lambda vi=v1, sp=sp: self._seg_value_changed("in", vi, sp.value()))
                tbl.setCellWidget(si, 2, sp)

            lbl_len = QtWidgets.QLabel(f"{length:.2f}"); lbl_len.setAlignment(QtCore.Qt.AlignCenter)
            tbl.setCellWidget(si, 3, lbl_len)
        if 0 <= self.sel_seg_idx < nseg:
            self._select_segment(self.sel_seg_idx, refocus=False)

    def _select_segment(self, si, refocus=True):
        """Marca el tramo `si` (entre pts[si] y pts[si+1]) como resaltado.
        Si `refocus`, solo salta la vista cuando el tramo NO está ya visible:
        entonces centra y hace un zoom SUAVE dejando bastante contexto (el
        tramo ocupa ~1/8 de la vista, no 1/3) para no desorientar al usuario.
        Si el tramo ya está en pantalla, no toca ni zoom ni encuadre."""
        self.sel_seg_idx = si
        if refocus and 0 <= self.sel_pipe < len(self.pipes):
            pts = self.pipes[self.sel_pipe].get("pts") or []
            if 0 <= si < len(pts) - 1:
                (x1, y1), (x2, y2) = pts[si], pts[si + 1]
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                length = math.hypot(x2 - x1, y2 - y1)
                view_rect = self.canvas.mapToScene(self.canvas.viewport().rect()).boundingRect()
                seg_rect = QtCore.QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                if not view_rect.contains(seg_rect):
                    if length > 1e-6:
                        visible_w = max(view_rect.width(), 1.0)
                        target_w = length * 8.0
                        if visible_w > target_w:
                            f = visible_w / target_w; self.canvas.scale(f, f)
                    self.canvas.centerOn(cx, cy)
        self._redraw()

    @staticmethod
    def _migrate_vertex_inv(p):
        # Migración de formato (pura) en model_ops.
        model_ops.migrate_vertex_inv(p)

    def _seg_value_changed(self, side, vi, value):
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        self._push()
        # Snapshot de TODOS los valores actualmente mostrados (auto + overrides)
        # antes de aplicar el cambio. Sin esto, editar el Fin del Tramo N
        # recalcularía por interpolación el Fin del Tramo N-1 (que no tiene
        # override) usando la Z recién editada como ancla — cascade que el
        # usuario ve como "me cambió el fin del anterior". Con el snapshot,
        # todos los intermedios pasan a ser overrides fijos e independientes.
        self._snapshot_seg_values(p)
        key = "vertex_inv_out" if side == "out" else "vertex_inv_in"
        ov = p.setdefault(key, {})
        ov[vi] = value
        self._rebuild_seg_inv_table(p)
        self._redraw()

    def _snapshot_seg_values(self, p):
        # Congelado de cotas por tramo como overrides (puro) en model_ops.
        model_ops.snapshot_seg_values(p)

    def _seg_edit_toggled(self, enabled):
        """Toggle del botón 'Editar cotas por tramo'. Al activar, congela los
        valores actuales de la tabla como overrides (así las ediciones
        posteriores no propagan), habilita los spinboxes y muestra las
        etiquetas T1, T2… en el lienzo. Al desactivar, conserva los valores
        guardados pero deshabilita la edición y oculta las etiquetas."""
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        self._push()
        p["seg_edit_enabled"] = bool(enabled)
        if enabled:
            self._snapshot_seg_values(p)
        self._rebuild_seg_inv_table(p)
        self._redraw()

    def _seg_endpoint_changed(self, which, value):
        """Editar 'Inicio' del primer tramo o 'Fin' del último tramo desde la
        tabla: son el mismo dato que inv_start/inv_end de la utilidad (arriba
        en 'Propiedades de la utilidad'), así que se escribe ahí directo — no
        en vertex_inv — y se sincroniza el spinbox de arriba con el guard para
        no re-disparar _prop_changed a mitad de la actualización."""
        if self._prop_guard: return
        if not (0 <= self.sel_pipe < len(self.pipes)): return
        p = self.pipes[self.sel_pipe]
        self._push()
        if which == "start": p["inv_start"] = value
        else: p["inv_end"] = value
        self._prop_guard = True
        self.prop_inv0.setValue(p.get("inv_start") or 0.0)
        self.prop_inv1.setValue(p.get("inv_end") or 0.0)
        self._prop_guard = False
        self._rebuild_seg_inv_table(p)

    def _seg_row_label_clicked(self, row, col):
        if col != 0: return
        item = self.tbl_seg_inv.item(row, 0)
        if item is None: return
        si = item.data(QtCore.Qt.UserRole)
        if si is None: return
        self._select_segment(int(si), refocus=True)

    def _pipe_net_kind(self, p):
        """Devuelve 'gravity' | 'pressure' | 'conduit' según la capa del pipe."""
        from model import network_kind
        return network_kind(p.get("layer") or "")

    def _on_civil_year_changed(self, i):
        """Al cambiar la versión de Civil 3D en el toolbar, actualiza el combo
        de idiomas disponibles y refresca los combos de familias/tamaños del
        panel activo (pipes y buzones/cajas) contra el catálogo del año elegido."""
        self.civil_year = self.cmb_civil.itemData(i)
        self._refill_lang_combo()
        self._refresh_catalog_panels()

    def _on_civil_lang_changed(self, i):
        """Al cambiar el idioma del catálogo, propaga a civil_catalog y refresca
        los paneles inmediatamente."""
        import civil_catalog as _cc
        lang = self.cmb_lang.itemData(i)
        _cc.set_current_lang(lang)
        self._refresh_catalog_panels()

    def _restore_civil_selection(self, year, lang):
        """Repone en el toolbar la versión/idioma de Civil 3D guardados en el
        proyecto (si esa versión está instalada). Se llama al abrir un proyecto.
        Se bloquean señales para no disparar refrescos intermedios; al final se
        refresca una sola vez."""
        import civil_catalog as _cc
        if year is None:
            return                                   # proyecto viejo (sin este dato guardado)
        if year not in set(_cc.installed_versions()):
            # La versión guardada no está instalada/detectada en ESTA PC → no se
            # puede seleccionar. Se avisa (visible, no un mensaje de barra que se
            # pisa) para que el usuario entienda por qué quedó en otra versión.
            QtWidgets.QMessageBox.information(
                self, "Civil 3D del proyecto no disponible",
                f"El proyecto se guardó con Civil 3D {year}"
                + (f" ({lang})" if lang else "") +
                f", pero esa versión no está instalada/detectada en esta PC.\n\n"
                f"Se mantiene la versión activa ({self.civil_year or '—'}). "
                "El catálogo de familias saldrá de esa versión.")
            return
        idx = self.cmb_civil.findData(year)
        if idx < 0:
            return
        self.cmb_civil.blockSignals(True)
        self.cmb_civil.setCurrentIndex(idx)
        self.cmb_civil.blockSignals(False)
        self.civil_year = year
        self._refill_lang_combo()                    # repuebla idiomas del año elegido
        if lang:
            li = self.cmb_lang.findData(lang)
            if li >= 0:
                self.cmb_lang.blockSignals(True)
                self.cmb_lang.setCurrentIndex(li)
                self.cmb_lang.blockSignals(False)
                _cc.set_current_lang(lang)
        self._refresh_catalog_panels()

    def _refill_lang_combo(self):
        """Repuebla el combo de idiomas con los realmente instalados para el año
        activo. Preserva la selección previa si sigue disponible."""
        import civil_catalog as _cc
        prev = self.cmb_lang.currentData() if hasattr(self, "cmb_lang") else None
        self.cmb_lang.blockSignals(True); self.cmb_lang.clear()
        langs = _cc.installed_langs(self.civil_year) if self.civil_year else []
        if not langs:
            self.cmb_lang.addItem("—", None)
            _cc.set_current_lang(None)
        else:
            for lg in langs:
                # Etiqueta amigable
                pretty = {"esp": "esp (Español)", "enu": "enu (English)",
                          "fra": "fra (Français)", "deu": "deu (Deutsch)",
                          "ita": "ita (Italiano)", "ptb": "ptb (Português)"}.get(lg, lg)
                self.cmb_lang.addItem(pretty, lg)
            # Reponer la selección previa si sigue disponible; si no, primera
            target = prev if prev in langs else langs[0]
            idx = self.cmb_lang.findData(target)
            if idx >= 0: self.cmb_lang.setCurrentIndex(idx)
            _cc.set_current_lang(target)
        self.cmb_lang.blockSignals(False)

    def _refresh_catalog_panels(self):
        """Vuelve a leer el catálogo Civil 3D del año actual y repuebla los combos
        de familia/tamaño del panel activo (pipe y buzón/caja). Se llama tras
        cambiar la versión y también tras instalar/desinstalar familias."""
        try:
            if 0 <= getattr(self, "sel_pipe", -1) < len(self.pipes):
                self._reload_pipe_families(self.pipes[self.sel_pipe])
        except Exception: pass
        try:
            if 0 <= getattr(self, "sel_bz", -1) < len(self.structures):
                self._sync_bz_panel()
        except Exception: pass
        try:
            if 0 <= getattr(self, "sel_curve", -1) < len(self.structures):
                self._sync_curve_panel()
        except Exception: pass

    def _duct_bank_for_pipe(self, pipe_idx):
        """Devuelve el DuctBank asignado a esta pipe, o None."""
        for db in getattr(self, "duct_banks", []):
            if getattr(db, "pipe_idx", -1) == pipe_idx:
                return db
        return None

    def _reload_pipe_families(self, p):
        """Repuebla los combos prop_family y prop_size según la capa del pipe y el
        catálogo Civil 3D seleccionado. Si la pipe tiene un duct bank asignado,
        oculta familia/tamaño y muestra el nombre del duct bank."""
        import civil_catalog as _cc
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
            self.lbl_prop_size.setVisible(False); self.prop_size.setVisible(False)
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
                f"{db.width_in:g}\" x {db.height_in:g}\" — {nc} conducto(s)</span>"
                f"</div>")
            self.lbl_ductbank_assigned.setVisible(True)
            self.prop_family.blockSignals(False); self.prop_size.blockSignals(False)
            return
        self.lbl_ductbank_assigned.setVisible(False)
        kind = self._pipe_net_kind(p)
        show = kind in ("gravity", "pressure", "conduit") and bool(self.civil_year)
        self.lbl_prop_family.setVisible(show); self.prop_family.setVisible(show)
        self.lbl_prop_size.setVisible(show); self.prop_size.setVisible(show)
        if not show:
            self.prop_family.blockSignals(False); self.prop_size.blockSignals(False); return
        fams = (_cc.pressure_pipes(self.civil_year) if kind == "pressure"
                else _cc.imperial_pipes(self.civil_year))
        self.prop_family.addItem("(por defecto)", "")
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

    def _load_pipe_sizes(self, kind, fid, current):
        import civil_catalog as _cc
        self.prop_size.blockSignals(True); self.prop_size.clear()
        if not fid or not self.civil_year:
            self.prop_size.addItem("(sin familia)", ""); self.prop_size.setEnabled(False)
            self.prop_size.blockSignals(False); return
        sizes = (_cc.pressure_pipe_sizes(self.civil_year, fid) if kind == "pressure"
                 else _cc.pipe_sizes(self.civil_year, fid))
        if not sizes:
            self.prop_size.addItem("(sin tamaños)", ""); self.prop_size.setEnabled(False)
        else:
            self.prop_size.setEnabled(True); self.prop_size.addItem("(por defecto)", "")
            for sz in sizes: self.prop_size.addItem(sz, sz)
            if current:
                for i in range(self.prop_size.count()):
                    if self.prop_size.itemData(i) == current:
                        self.prop_size.setCurrentIndex(i); break
        self.prop_size.blockSignals(False)

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

    # ─────────────────────── Acordeón: cambios de sección ────────────────────────
    def _place_widget(self, w, target_layout):
        """Mueve un widget al layout indicado (Qt reasigna su padre automáticamente).
        Es como "mover una caja" de un estante a otro. Si el widget ya estaba en un
        layout, primero lo quitamos de ese layout (removeWidget). Si no hacemos esto,
        Qt puede dejar celdas huérfanas o mostrar el widget en dos sitios."""
        if w.parent() is not None:
            pl = w.parent().layout()
            if pl is not None:
                pl.removeWidget(w)
        target_layout.addWidget(w)

    def _on_toolbox_change(self, idx):
        """Al abrir una sección distinta del acordeón:
          1) Salimos del modo activo (evita mezclar 'colocar Multileader' con
             el usuario abriendo la sección Texto por error).
          2) Reparentamos los widgets COMPARTIDOS a la sección correspondiente:
             - orient_combo → Leader
             - gtxt (estilo) → Texto libre
             - rot_row visible solo en Texto libre
          3) Refrescamos la UI (etiqueta del modo, botones activos, etc.)."""
        # Descubrimos qué sección ("key") corresponde al índice.
        key = next((k for k, i in self._sec_idx.items() if i == idx), None)
        if self.mode not in ("idle",):
            self.set_mode("idle")
        if key == "leader":
            self._place_widget(self.orient_combo, self._slot_orient_ld)
        elif key == "text":
            self._place_widget(self.gtxt, self._slot_style_tx)
            self.rot_row.setVisible(True)
        self._update_ui()

    def _open_section(self, key):
        """Abre programáticamente una sección del acordeón por su nombre lógico.
        La usamos p.ej. cuando el usuario selecciona un Multileader en el
        inventario: abrimos automáticamente la sección Multileader para que
        vea su estilo/orientación y pueda editarlos."""
        i = self._sec_idx.get(key)
        if i is not None and self.toolbox.currentIndex() != i:
            self.toolbox.setCurrentIndex(i)

    def _bump_size(self, delta):
        """Sube o baja la altura del texto en pasos de 0.5 pies."""
        self.size_spin.setValue(round(max(0.5, self.size_spin.value() + delta), 2))

    def _bump_rot(self, delta):
        self.rot_spin.setValue((self.rot_spin.value() + delta) % 360)

    def _bump_opacity(self, delta_pct):
        val = self.canvas.pdf_opacity + delta_pct / 100.0
        self.canvas.set_pdf_opacity(val)
        self.lbl_opacity.setText(f"{round(self.canvas.pdf_opacity * 100)}%")

    def _px_for_ft(self, ft):
        raw = ft / self.scale * self.zoom if self.scale else ft * self.zoom
        cap = self.pageH_px * 0.06 if self.pageH_px else 200
        return max(8.0, min(raw, cap))

    def _style_changed(self):
        if self._style_guard: return
        ti = self._current_tab()
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            tm = self.text_marks[self.sel_text]; self._push()
            tm["font"] = self.font_combo.currentFont().family(); tm["size_ft"] = self.size_spin.value()
            tm["bold"] = self.chk_bold.isChecked(); tm["rot"] = self.rot_spin.value() % 360
            self._redraw()
        # (Multileader eliminado — solo quedan Leaders simples sin texto editable.)

    def _prop_changed(self):
        """Callback: cualquier cambio en el panel Propiedades escribe al modelo.
        `self._push()` guarda un snapshot para Ctrl+Z (deshacer).
        La UNIDAD de diámetro/invert es la del proyecto (self.work_unit), no per-pipe."""
        if self._prop_guard: return
        if self._current_tab() == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            p = self.pipes[self.sel_pipe]; self._push()
            p["name"] = self.prop_name.text().strip()
            p["diam_unit"] = "in"                                        # el diámetro nunca va en pies
            p["unit"] = self.work_unit                                  # unidad de trabajo (coords/cotas)
            p["part"] = self.prop_part.text().strip()
            p["inv_start"] = self.prop_inv0.value(); p["inv_end"] = self.prop_inv1.value()
            # Guardamos el VALOR real (data), no el texto traducido en pantalla.
            p["material"] = self.prop_material.currentData() or self.prop_material.currentText()
            p["net_type"] = self.prop_nettype.currentData() or ""
            # Familia + tamaño del catálogo Civil 3D. El diámetro se deriva del tamaño.
            if self.prop_family.isVisible():
                p["pipe_family"] = self.prop_family.currentData() or ""
                p["pipe_size"] = self.prop_size.currentData() or "" if self.prop_size.isEnabled() else ""
            # p["diam"] se calcula del pipe_size (p.ej. "24 in" → 24.0). Sin tamaño → 0.
            p["diam"] = _extract_diam_from_size(p.get("pipe_size", ""))
            self._refresh_lists()
            self._rebuild_seg_inv_table(p)
            # Repintamos el lienzo para que los marcadores de cruces se
            # reclasifiquen inmediatamente: al cambiar inv_start/inv_end,
            # una sugerencia (cotas distintas) puede volverse conflicto
            # (cotas iguales) o viceversa.
            self._redraw()

    def _refresh_unit_labels(self):
        """Etiquetas de campo fijas: cotas en PIES, diámetro en PULGADAS.
        (Ya no hay selector de unidad; todo va por campo.)"""
        # (Diámetro se muestra vía combo de tamaño del catálogo, no necesita etiqueta aquí)
        if hasattr(self, "lbl_prop_inv0"): self.lbl_prop_inv0.setText("Elev. de rasante inicial (ft):")
        if hasattr(self, "lbl_prop_inv1"): self.lbl_prop_inv1.setText("Elev. de rasante final (ft):")

    def _refresh_counts(self):
        """Contadores en vivo en la barra de estado: utilidades, leaders, textos, zonas."""
        if not hasattr(self, "lbl_counts"): return
        n_p = len(self.pipes); n_l = len(self.leaders); n_t = len(self.text_marks); n_z = len(self.erase_regions)
        self.lbl_counts.setText(f"{n_p} util · {n_l} lead · {n_t} txt · {n_z} zona")
        # marca de "sin guardar"
        if hasattr(self, "lbl_dirty"):
            if self._dirty:
                self.lbl_dirty.setText("●"); self.lbl_dirty.setStyleSheet(f"color:{_theme.tokens().danger};")
            else:
                self.lbl_dirty.setText("")
        self._update_title()

    def change_pipe_type(self):
        if 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes[self.sel_pipe]["layer"] = self.active_layer()
            self.pipes[self.sel_pipe]["ab"] = self.chk_ab.isChecked(); self._refresh_lists(); self._redraw()

    def edit_selected_text(self):
        ti = self._current_tab()
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._edit_text_mark(self.sel_text)

    def _list_context_menu(self, listw, tab_idx, pos):
        item = listw.itemAt(pos)
        if item is None:
            # Sin item bajo el cursor: en Bancoductos permitimos "+ Nuevo" igualmente.
            if tab_idx == TAB_DB:
                menu = QtWidgets.QMenu(self)
                self._menu_act(menu, "+ Nuevo bancoducto", self._db_new)
                menu.exec(listw.viewport().mapToGlobal(pos))
            return
        if self._current_tab() != tab_idx: self._show_tab(tab_idx)
        listw.setCurrentRow(listw.row(item))          # selecciona la fila bajo el cursor
        menu = QtWidgets.QMenu(self)
        if tab_idx == TAB_PIPE:
            self._menu_act(menu, "Cambiar tipo", self.change_pipe_type)
            self._menu_act(menu, "Editar/mover", self.enter_move)
            # Bancoducto asignado a esta tubería: editar o crear.
            if 0 <= self.sel_pipe < len(self.pipes):
                db = self._duct_bank_for_pipe(self.sel_pipe)
                menu.addSeparator()
                if db is not None:
                    self._menu_act(menu, f"Editar bancoducto «{db.name or 'sin nombre'}»",
                                   lambda: self._db_edit_for_pipe(self.sel_pipe))
                else:
                    self._menu_act(menu, "Crear bancoducto para esta tubería",
                                   lambda: self._db_new_for_pipe(self.sel_pipe))
        elif tab_idx == TAB_LEADER:
            self._menu_act(menu, "Editar/mover", self.enter_move)
        elif tab_idx == TAB_TEXT:
            self._menu_act(menu, "Mover", self.enter_move)
            self._menu_act(menu, "Editar texto", self.edit_selected_text)
        elif tab_idx == TAB_REGION:
            self._menu_act(menu, "Editar/mover", self.enter_move)
        elif tab_idx == TAB_DB:
            self._menu_act(menu, "Editar", self._db_edit)
            self._menu_act(menu, "Duplicar", self._db_duplicate)
        menu.addSeparator()
        self._menu_act(menu, "Eliminar", self.delete_selected)
        menu.exec(listw.viewport().mapToGlobal(pos))

    def delete_selected(self):
        ti = self._current_tab()
        desc = None
        if ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            p = self.pipes[self.sel_pipe]
            desc = f"Utilidad #{self.sel_pipe+1} ({p['layer']}, {len(p.get('pts',[]))} vértices)"
        elif ti == TAB_LEADER and 0 <= self.sel_leader < len(self.leaders):
            desc = f"Leader #{self.sel_leader+1}"
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            txt = self.text_marks[self.sel_text].get("text", "")[:30]
            desc = f"Texto #{self.sel_text+1} «{txt}»"
        elif ti == TAB_REGION and 0 <= self.sel_region < len(self.erase_regions):
            desc = f"Zona de borrado #{self.sel_region+1}"
        elif ti == TAB_CL and 0 <= self.sel_cl < len(self.ref_centerlines):
            desc = f"Centerline #{self.sel_cl+1}"
        elif ti == TAB_DB and 0 <= self.sel_db < len(getattr(self, "duct_banks", [])):
            db = self.duct_banks[self.sel_db]
            desc = f"Bancoducto «{db.name or 'sin nombre'}» ({len(db.conduits)} conducto(s))"
        if desc is None:
            return
        r = QtWidgets.QMessageBox.question(
            self, "Confirmar eliminación", f"¿Eliminar {desc}?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if r != QtWidgets.QMessageBox.Yes:
            return
        if ti == TAB_PIPE:
            self._push()
            deleted_idx = self.sel_pipe
            self.pipes.pop(self.sel_pipe); self.sel_pipe = -1
            self._reindex_cross_connections_on_pipe_delete(deleted_idx)
        elif ti == TAB_LEADER:
            self._push(); self.leaders.pop(self.sel_leader); self.sel_leader = -1
        elif ti == TAB_TEXT:
            self._push(); self.text_marks.pop(self.sel_text); self.sel_text = -1
        elif ti == TAB_REGION:
            self._push(); self.erase_regions.pop(self.sel_region); self.sel_region = -1
        elif ti == TAB_CL:
            self._push(); self.ref_centerlines.pop(self.sel_cl); self.sel_cl = -1
        elif ti == TAB_DB:
            self._push(); self.duct_banks.pop(self.sel_db); self.sel_db = -1
            if hasattr(self, "lbl_ductbank_count"):
                self.lbl_ductbank_count.setText(f"Duct banks guardados: {len(self.duct_banks)}")
            self._dirty = True
        self._refresh_lists(); self._redraw()

    def _copy_sel(self):
        ti = self._current_tab()
        if ti == TAB_LEADER and 0 <= self.sel_leader < len(self.leaders): self._clip = ("leader", copy.deepcopy(self.leaders[self.sel_leader]))
        elif ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes): self._clip = ("pipe", copy.deepcopy(self.pipes[self.sel_pipe]))
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._clip = ("text", copy.deepcopy(self.text_marks[self.sel_text]))
        else: self._info(_tr("Selecciona algo para copiar.")); return
        self._info(_tr("Copiado. Ctrl+V para pegar una copia."))

    def _paste_sel(self):
        if not self._clip: return
        kind, obj = self._clip; o = copy.deepcopy(obj); d = 30; self._push()
        if kind == "leader":
            if o.get("arrow"): o["arrow"] = (o["arrow"][0] + d, o["arrow"][1] + d)
            if o.get("landing"): o["landing"] = (o["landing"][0] + d, o["landing"][1] + d)
            if o.get("tp"): o["tp"] = (o["tp"][0] + d, o["tp"][1] + d)
            self.leaders.append(o); self._refresh_lists(); self._select_leader(len(self.leaders) - 1)
        elif kind == "pipe":
            o["pts"] = [(x + d, y + d) for (x, y) in o["pts"]]; self.pipes.append(o)
            self._show_tab(TAB_PIPE); self._refresh_lists(); self.pipe_list.setCurrentRow(len(self.pipes) - 1)
        elif kind == "text":
            o["pos"] = (o["pos"][0] + d, o["pos"][1] + d); self.text_marks.append(o)
            self._show_tab(TAB_TEXT); self._refresh_lists(); self.txt_marks_list.setCurrentRow(len(self.text_marks) - 1)
        self._redraw(); self._info(_tr("Pegado (copia desplazada)."))

    def _refresh_lists(self):
        self._refresh_counts()
        self.pipe_list.blockSignals(True); self.pipe_list.clear()
        for i, p in enumerate(self.pipes, 1):
            tag = " (AB)" if p.get("ab") else ""
            nm = f" · {p['name']}" if p.get("name") else ""
            n = len(p.get("pts") or [])
            info = f"red:{p.get('net', '')}" if p.get("world") else str(n)
            it = QtWidgets.QListWidgetItem(swatch_icon(layer_qcolor(p["layer"])), f"{i}. {p['layer']}{tag}{nm} ({info})")
            self.pipe_list.addItem(it)
        self.pipe_list.blockSignals(False)
        self.sleader_list.blockSignals(True); self.sleader_list.clear()
        ns = 0
        for i, ld in enumerate(self.leaders):
            ns += 1; o = {"h": "horizontal", "v": "vertical", "d": "diagonal"}.get(ld.get("orient", "d"), "")
            it = QtWidgets.QListWidgetItem(f"{ns}. Leader {o}".rstrip())
            it.setData(QtCore.Qt.UserRole, i); self.sleader_list.addItem(it)
        self.sleader_list.blockSignals(False)
        self.txt_marks_list.blockSignals(True); self.txt_marks_list.clear()
        for i, tm in enumerate(self.text_marks, 1): self.txt_marks_list.addItem(f"{i}. {tm['text'][:28].replace(chr(10), ' / ')}")
        self.txt_marks_list.blockSignals(False)
        self.region_list.blockSignals(True); self.region_list.clear()
        for i, rg in enumerate(self.erase_regions, 1):
            it = QtWidgets.QListWidgetItem(f"Zona {i} ({len(rg['pts'])} vértices)")
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if rg.get("enabled", True) else QtCore.Qt.Unchecked)
            self.region_list.addItem(it)
        self.region_list.blockSignals(False)
        # Refrescar tabs Buzones/Curvas (vistas filtradas de self.structures según
        # 'curve') + paneles de propiedades del elemento seleccionado en cada una.
        self._rebuild_structures()
        self.bz_list.blockSignals(True); self.bz_list.clear()
        self.curve_list.blockSignals(True); self.curve_list.clear()
        self._bz_rows = []; self._curve_rows = []
        for i, s in enumerate(self.structures):
            is_curve = bool(s.get("curve"))
            if is_curve:
                p = self._pipe_at_vertex(s.get("x"), s.get("y")) if s.get("x") is not None else None
                fam = (p.get("pipe_family") if p else "") or "(sin familia)"
                sz = f"  {p['pipe_size']}" if p and p.get("pipe_size") else ""
                item_icon = _icon("mdi:vector-curve", color="#a855f7")   # curva = violeta
            else:
                fam = s.get("part") or "(sin familia)"
                sz = f"  {s['part_size']}" if s.get("part_size") else ""
                if s.get("hidden"):
                    item_icon = _icon("mdi:eye-off-outline", color=_theme.tokens().text_muted)
                elif s.get("net") == "conduit":
                    item_icon = _icon("mdi:circle-medium", color="#f97316")   # conducto = naranja
                else:
                    item_icon = _icon("mdi:circle-medium", color="#3b82f6")   # buzón = azul
            it = QtWidgets.QListWidgetItem(item_icon, f"{s.get('cod', '?')}  ·  {fam}{sz}")
            if not is_curve and s.get("hidden"):
                it.setForeground(QtGui.QColor(_theme.tokens().text_muted))
                it.setToolTip("Oculto — no se dibuja ni se crea en Civil3D como buzón real.")
            if is_curve: self.curve_list.addItem(it); self._curve_rows.append(i)
            else: self.bz_list.addItem(it); self._bz_rows.append(i)
        self.bz_list.blockSignals(False); self.curve_list.blockSignals(False)
        self._sync_bz_panel(); self._sync_curve_panel()
        self.cl_list.blockSignals(True); self.cl_list.clear()
        for c in self.ref_centerlines:
            _it_cl = QtWidgets.QListWidgetItem(
                _icon("mdi:vector-line", color="#22c55e"),
                f"{c.get('cod', '?')}  ·  {len(c.get('pts') or [])} vértices")
            self.cl_list.addItem(_it_cl)
        self.cl_list.blockSignals(False)
        self._sync_cl_panel()
        self._refresh_db_list()
        self._set_item_tooltips()

    def _set_item_tooltips(self):
        """Pone el texto completo de cada item como su tooltip. Las listas usan
        elide a la derecha para no sacar barra horizontal (ver el bloque
        RESPONSIVO en _build_ui), así que el texto recortado con "…" se puede
        leer completo al pasar el ratón."""
        for lw in (self.pipe_list, self.sleader_list,
                   self.txt_marks_list, self.region_list, self.bz_list,
                   self.curve_list, self.cl_list, self.db_list):
            for r in range(lw.count()):
                it = lw.item(r)
                if it is not None and not it.toolTip():
                    it.setToolTip(it.text())

    # ─────────────────────────── borrar zona ───────────────────────────
    def finish_erase(self):
        if len(self._erase_pts) < 3: return
        self._push(); poly = self._erase_pts[:]; self.erase_regions.append({"pts": poly, "enabled": True})
        # Las zonas de borrado SOLO tapan la geometría del PDF base al exportar
        # (ver dxf_export.apply_erase, que corre antes de agregar utilidades).
        # NO eliminan pipes/leaders/textos del usuario que caigan dentro — eso
        # se hace explícito con el borrado individual del panel.
        self._erase_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info(_tr("Zona agregada: al exportar tapa la geometría base del plano dentro de ella (no toca tus utilidades)."))

    def finish_centerline(self):
        if len(self._cl_pts) < 2: return
        self._push()
        used = {c.get("cod", "") for c in self.ref_centerlines if c.get("cod")}
        n = 1
        while f"CL-{n}" in used: n += 1
        self.ref_centerlines.append({"cod": f"CL-{n}", "pts": self._cl_pts[:]})
        self._cl_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info(_tr("Centerline agregado — solo referencia para calzar la georreferenciación, no es una utilidad."))

    def start_leader(self, simple=True):
        """Entra al modo de colocación de Leader (solo flecha, sin texto). La
        orientación se lee de `orient_combo` AL MOMENTO del clic final para que
        el usuario pueda cambiarla dentro del modo. `simple` se mantiene solo
        por retrocompat de callers antiguos; siempre es True ahora."""
        self._pending = {"arrow": None, "simple": True}
        self._open_section("leader")
        self.set_mode("leader1")
        if self.orient_combo.currentData() == "d":
            self._info(_tr("Leader diagonal: cabeza → inicio del landing (bisagra) → final del cuerpo. Enter/Esc para salir."))
        else:
            self._info(_tr("Leader: cabeza de flecha → final del cuerpo. Enter/Esc para salir."))

    def _edit_leader_text(self, idx):
        ld = self.leaders[idx]; tp = ld["tp"]
        if ld.get("simple"):                                 # el Leader simple no tiene texto que editar
            self._info(_tr("El Leader simple no lleva texto.")); return
        def commit(val):
            self._close_editor()
            if val.strip(): self._push(); ld["text"] = val.rstrip("\n"); self._refresh_lists()
            self._redraw()
        self._open_editor(tp[0], tp[1] - self.leader_hpx, ld["text"], commit)

    def _leader_geo(self, ld):
        # Geometría del Multileader (pura) en model_ops; se le pasa la conversión
        # pies→px de la ventana (depende de escala/zoom).
        return model_ops.leader_geo(ld, self._px_for_ft)

    # ─────────────────────────── texto libre ───────────────────────────
    def _new_free_text(self, x, y):
        def commit(val):
            self._close_editor()
            if val.strip():
                self._push()
                self.text_marks.append({"pos": (x, y), "text": val.rstrip("\n"),
                                        "size_ft": self.size_spin.value(), "font": self.font_combo.currentFont().family(),
                                        "bold": self.chk_bold.isChecked(), "rot": self.rot_spin.value() % 360, "free": True})
                self._refresh_lists()
            self._redraw()
        self._open_editor(x, y, "", commit)

    def _edit_text_mark(self, idx):
        tm = self.text_marks[idx]
        def commit(val):
            self._close_editor()
            if val.strip(): self._push(); tm["text"] = val.rstrip("\n"); self._refresh_lists()
            self._redraw()
        self._open_editor(tm["pos"][0], tm["pos"][1], tm["text"], commit)

    def _open_editor(self, x, y, initial, on_commit, w=220):
        # Caja flotante hija del viewport (no escala con el zoom y recibe el teclado
        # de forma fiable: Enter aplica, Ctrl+Shift+Enter salta de línea, clic fuera aplica).
        self._close_editor()
        ed = InlineEdit(initial); ed.setParent(self.canvas.viewport())
        ed.setFixedWidth(w); ed.setFixedHeight(64)
        vp = self.canvas.mapFromScene(QtCore.QPointF(x, y))
        ed.move(vp); ed.show(); ed.raise_()
        ed.committed.connect(on_commit); self._editor = ed
        ed.setFocus(QtCore.Qt.OtherFocusReason); ed.selectAll()

    def _close_editor(self):
        if self._editor:
            ed = self._editor; self._editor = None
            try: ed.hide(); ed.deleteLater()
            except Exception: pass

    # ─────────────────────────── dibujo ───────────────────────────
    def _redraw(self):
        sc = self.canvas.scene()
        for it in self._overlay:
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._overlay = []
        if self.canvas.pixmap_item is None: return
        # zonas de borrado — DETRÁS de todo (solo tapan el PDF)
        if self._erase_pts:
            self._poly(self._erase_pts, QtGui.QColor(255, 220, 0), 1.8, dots=True, z=Z_MARK)
        # Fondo detrás del PDF (blanco/negro) — solo cambia el ASPECTO VISUAL de
        # las zonas borradas en el lienzo principal. Al exportar/importar la zona
        # sigue tratándose exactamente igual (nada de esto toca los datos).
        bg = self.canvas.pdf_bg_color
        bg_dark = bg.value() < 128
        fill_full = QtGui.QColor(bg)                       # opaco (misma tinta que el fondo)
        fill_sel = QtGui.QColor(bg); fill_sel.setAlpha(128)   # semitransparente al seleccionar
        for i, rg in enumerate(self.erase_regions):
            qp = QtGui.QPolygonF([QtCore.QPointF(px, py) for (px, py) in rg["pts"]])
            enabled = rg.get("enabled", True); sel = (i == self.sel_region)
            if not enabled:
                pen = QtGui.QPen(QtGui.QColor(150, 150, 150), 1.2, QtCore.Qt.DashLine); brush = QtGui.QBrush(QtGui.QColor(200, 200, 200, 30))
            elif sel:
                # Solo al seleccionar se dibuja borde (rojo) para verla; el resto sin borde.
                pen = QtGui.QPen(QtGui.QColor(255, 40, 40), 2.0); brush = QtGui.QBrush(fill_sel)
            else:
                pen = QtGui.QPen(QtCore.Qt.NoPen); brush = QtGui.QBrush(fill_full)
            pen.setCosmetic(True); it = sc.addPolygon(qp, pen, brush); it.setZValue(Z_ERASE); self._overlay.append(it)
            if sel and self.mode == "move": self._handles(rg["pts"])
        # utilidades
        for i, p in enumerate(self.pipes):
            if not p.get("pts"): continue               # tramos importados (world): no se dibujan
            sel = (i == self.sel_pipe)
            # Dibujo la polilínea del pipe con arcos REALES sustituyendo cada
            # esquina que tenga un elemento curvo — mismo radio y tangencia
            # que el plugin usará en Civil 3D.
            self._poly(self._pipe_display_pts(p), layer_qcolor(p["layer"]),
                       4.0 if sel else 2.0, z=Z_MARK)
            if sel and self.mode == "move": self._handles(p["pts"])
            if sel and 0 <= self.sel_seg_idx < len(p["pts"]) - 1:
                a, b = p["pts"][self.sel_seg_idx], p["pts"][self.sel_seg_idx + 1]
                pen_hi = QtGui.QPen(QtGui.QColor(255, 50, 220), 6.0); pen_hi.setCosmetic(True)
                it = sc.addLine(a[0], a[1], b[0], b[1], pen_hi)
                it.setZValue(Z_HANDLE + 1); self._overlay.append(it)
                dot_pen = QtGui.QPen(QtGui.QColor(20, 20, 20), 1.4); dot_pen.setCosmetic(True)
                for (vx, vy) in (a, b):
                    it2 = sc.addEllipse(vx - 7, vy - 7, 14, 14, dot_pen, QtGui.QBrush(QtGui.QColor(255, 50, 220)))
                    it2.setZValue(Z_HANDLE + 1); self._overlay.append(it2)
            # Etiquetas T1, T2… encima de cada tramo cuando el pipe tiene
            # activada la edición por tramo. Se dibujan aunque el pipe no
            # esté seleccionado, así el usuario ve la numeración en todo
            # momento. Solo visual — NO se exportan al DXF (dxf_export lee
            # self.pipes, no la escena Qt).
            if p.get("seg_edit_enabled") and len(p["pts"]) >= 3:
                for si in range(len(p["pts"]) - 1):
                    (x1, y1), (x2, y2) = p["pts"][si], p["pts"][si + 1]
                    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    self._seg_label(sc, f"T{si + 1}", mx, my,
                                    layer_qcolor(p["layer"]))
        self._poly(self.cur_pts, layer_qcolor(self._ext_layer or self.active_layer()), 2.0, dots=True, z=Z_MARK)
        # centerlines de referencia (para georreferenciar) — magenta punteado,
        # bien distinto de las utilidades para no confundirlos a simple vista.
        cl_color = QtGui.QColor(255, 60, 220)
        for i, c in enumerate(self.ref_centerlines):
            sel = (i == self.sel_cl)
            self._poly(c.get("pts") or [], cl_color, 7.0 if sel else 2.0, z=Z_MARK, dash=True)
        self._poly(self._cl_pts, cl_color, 2.0, dots=True, z=Z_MARK, dash=True)
        # leaders
        anno = aci_qcolor(8)
        for i, ld in enumerate(self.leaders):
            if not (ld.get("arrow") and ld.get("tp")): continue
            col = QtGui.QColor(120, 220, 120) if i == self.sel_leader else anno
            geo = self._leader_geo(ld)
            for s in geo["segs"]: self._poly(s, col, 1.6, z=Z_MARK)
            self._arrow(ld["arrow"], geo["segs"][0][1], col)   # punta orientada a lo largo de la línea
            if i == self.sel_leader and self.mode == "move" and ld.get("simple"):
                self._handles(geo["segs"][0])                  # vértices editables (cabeza / bisagra / final)
            if ld["text"]:                                     # Leader simple no lleva texto
                t = sc.addText(ld["text"]); t.setDefaultTextColor(col); t.document().setDocumentMargin(0)
                f = t.font(); f.setPixelSize(int(geo["H"])); t.setFont(f)
                if geo["rot"]: t.setRotation(geo["rot"])
                t.setPos(geo["label_pos"][0], geo["label_pos"][1]); t.setZValue(Z_MARK); self._overlay.append(t)
        # buzones — círculo relleno con el color del pipe al que pertenecen.
        # Se dibuja por encima de las utilidades (mismo z que MARK). Si show_bz_labels
        # está activo, el código se dibuja al lado con una fuente pequeña blanca.
        self._draw_structures()
        # Marcas de conflicto: pares de segmentos que se cruzan geométricamente
        # (dos utilidades pasando una por encima de la otra sin ser juntura).
        self._draw_pipe_conflicts()
        # textos
        for i, tm in enumerate(self.text_marks):
            t = sc.addText(tm["text"]); t.setDefaultTextColor(QtGui.QColor(120, 220, 120)); t.document().setDocumentMargin(0)
            hpx = self._px_for_ft(tm["size_ft"]) if "size_ft" in tm else tm.get("h", 16)
            f = t.font(); f.setPixelSize(max(6, int(hpx)))
            if tm.get("font"): f.setFamily(tm["font"])
            f.setBold(bool(tm.get("bold"))); t.setFont(f)
            t.setPos(tm["pos"][0], tm["pos"][1])
            if tm.get("rot"): t.setRotation(-tm["rot"])       # rot en grados CCW; Qt gira en sentido horario
            t.setZValue(Z_MARK); self._overlay.append(t)
            if i == self.sel_text and self._current_tab() == TAB_TEXT:
                br = t.boundingRect(); pen = QtGui.QPen(QtGui.QColor(255, 180, 40)); pen.setCosmetic(True)
                rit = sc.addRect(tm["pos"][0], tm["pos"][1], br.width(), br.height(), pen); rit.setZValue(Z_MARK); self._overlay.append(rit)

    def _reindex_cross_connections_on_pipe_delete(self, deleted_idx):
        """Al borrar una utilidad se corren TODOS los índices posteriores:
        pipe #k con k > deleted_idx pasa a ser k-1. Actualizamos las
        conexiones aprobadas (`cross_connections`) para reflejar eso:
          - Se DESCARTA la que referencia a la pipe borrada (queda huérfana).
          - En las demás, si pipe_a > deleted_idx se le resta 1 (idem pipe_b)."""
        if not getattr(self, "cross_connections", None): return
        nuevas = []
        for c in self.cross_connections:
            a, b = int(c.get("pipe_a", -1)), int(c.get("pipe_b", -1))
            if a == deleted_idx or b == deleted_idx: continue
            if a > deleted_idx: a -= 1
            if b > deleted_idx: b -= 1
            c["pipe_a"] = a; c["pipe_b"] = b
            nuevas.append(c)
        self.cross_connections = nuevas

    def _prune_stale_cross_connections(self):
        """Filtro defensivo: quita conexiones aprobadas que ya no tienen
        sentido geométrico (la pipe referenciada ya no existe o los segmentos
        de las dos tuberías ya no se cruzan cerca del punto guardado). Se
        corre antes de exportar y antes de dibujar, para que nunca se cuele
        al DXF un cruce fantasma que quedó del historial. Devuelve cuántas
        conexiones se descartaron."""
        conns = getattr(self, "cross_connections", None) or []
        if not conns: return 0
        # Tolerancia en pixeles del lienzo (mismo criterio que _draw).
        # Como aquí no dependemos del zoom, usamos una tolerancia fija amplia
        # (~5 unidades del lienzo, suficiente porque el punto se guardó en
        # las mismas coords).
        TOL = 6.0
        keep = []
        for c in conns:
            try:
                a = int(c["pipe_a"]); b = int(c["pipe_b"])
                cx = float(c["x"]); cy = float(c["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= a < len(self.pipes) and 0 <= b < len(self.pipes)):
                continue
            if a == b:
                continue
            pa = self.pipes[a].get("pts") or []
            pb = self.pipes[b].get("pts") or []
            if len(pa) < 2 or len(pb) < 2:
                continue
            # ¿Existe algún par de segmentos (uno de A, otro de B) que se
            # crucen en el interior cerca de (cx, cy)?
            hallado = False
            for i in range(len(pa) - 1):
                a1, a2 = pa[i], pa[i + 1]
                for j in range(len(pb) - 1):
                    b1, b2 = pb[j], pb[j + 1]
                    cp = self._seg_inter_pts(a1, a2, b1, b2)
                    if cp is None: continue
                    if (cp[0] - cx) ** 2 + (cp[1] - cy) ** 2 <= TOL * TOL:
                        hallado = True
                        break
                if hallado: break
            if hallado:
                keep.append(c)
        removed = len(conns) - len(keep)
        if removed > 0:
            self.cross_connections = keep
        return removed

    @staticmethod
    def _seg_inter_pts(p1, p2, p3, p4):
        """Intersección de dos segmentos (incluyendo extremos), o None.
        Acepta t/u en [0, 1] con pequeña tolerancia, para que también cuenten
        cruces donde un extremo de un segmento cae sobre el otro o donde los
        extremos coinciden — el usuario ve ese contacto físico como cruce
        aunque no sea intersección estrictamente interior."""
        x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-9: return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
        eps = 1e-6
        if not (-eps <= t <= 1 + eps and -eps <= u <= 1 + eps): return None
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    def _pipe_z_at(self, pipe_idx, seg_idx, x, y):
        """Devuelve la cota Z interpolada de la tubería `pipe_idx` en el punto
        (x, y) que se sabe que cae en el segmento `seg_idx` (entre pts[seg_idx]
        y pts[seg_idx+1]). Usa las cotas por vértice (VertexInv/VertexInvIn)
        con el mismo criterio que `interp_vertex_z`. Cuando la pipe no tiene
        `inv_start`/`inv_end` (típico de tuberías recién dibujadas), asume Z=0
        — mismo valor que muestra el spinbox de la UI por defecto."""
        if not (0 <= pipe_idx < len(self.pipes)): return None
        p = self.pipes[pipe_idx]
        pts = p.get("pts") or []
        if seg_idx < 0 or seg_idx >= len(pts) - 1: return None
        zs = p.get("inv_start"); ze = p.get("inv_end")
        # None → 0.0 (coincide con el valor por defecto que ve el usuario).
        if zs is None: zs = 0.0 if ze is None else ze
        if ze is None: ze = zs
        ov = p.get("vertex_inv") or {}
        # Normaliza claves a int (json las guarda como str).
        ov = {int(k): float(v) for k, v in ov.items()}
        z_verts = model_ops.interp_vertex_z(pts, float(zs), float(ze), ov)
        # Interpolación lineal a lo largo del segmento.
        a = pts[seg_idx]; b = pts[seg_idx + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-9: return z_verts[seg_idx]
        t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / seg_len2))
        return z_verts[seg_idx] + (z_verts[seg_idx + 1] - z_verts[seg_idx]) * t

    def _on_toggle_show_conflicts(self, on):
        """Toggle del checkbox de la barra inferior 'Mostrar cruces/conflictos':
        redibuja el lienzo para que las marcas aparezcan/desaparezcan de inmediato.
        Preferencia persistida en QSettings (Configuración → app), reconstruida
        al iniciar la app."""
        try:
            s = QtCore.QSettings("pdf-to-cad", "app")
            s.setValue("show_conflicts_v2", bool(on))
        except Exception: pass
        self._redraw()

    def _draw_pipe_conflicts(self):
        """Detecta y dibuja marcas en los cruces geométricos entre segmentos
        de tuberías. Se distinguen tres estados (colores distintos):

        - ROJO «!»  = CONFLICTO físico real (dos tuberías con la MISMA cota
          en el punto de cruce → chocan). Requiere corregir la geometría o
          alguna cota. NO se ofrece conexión.
        - AZUL «↕»  = SUGERENCIA de conexión: cotas distintas (una pasa por
          encima/debajo de la otra sin chocar). Se puede aprobar con click
          para que el plugin dibuje una vertical + válvula uniéndolas.
        - VERDE «✓» = Sugerencia ya APROBADA por el usuario.

        Tolerancia de "misma cota": 0.10 ft (~1.2 pulgadas). Si a alguna de
        las dos le falta la cota, se trata como conflicto (no se puede
        confirmar que estén a alturas distintas)."""
        # Saneamos antes de dibujar por si el usuario borró/movió una pipe
        # y quedaron cruces fantasma en cross_connections.
        self._prune_stale_cross_connections()
        # Toggle del usuario en la barra inferior: si está apagado, no dibujar
        # nada, limpiar hits (para que un click no active nada) y quitar el
        # contador de la barra de estado. El resto de la app sigue igual —
        # los cross_connections aprobados se conservan (afectan el DXF).
        if hasattr(self, "chk_show_conflicts") and not self.chk_show_conflicts.isChecked():
            self._conflict_hits = []
            if hasattr(self, "lbl_info"):
                # Deja el texto de info normal (sin el contador de cruces)
                pass
            return
        sc = self.canvas.scene()

        def _seg_inter(p1, p2, p3, p4):
            # Acepta intersecciones en los extremos también: si dos utilidades
            # se TOCAN (un extremo cae sobre el otro segmento o los extremos
            # coinciden) también cuenta como cruce físico.
            x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-9: return None
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
            u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
            eps = 1e-6
            if not (-eps <= t <= 1 + eps and -eps <= u <= 1 + eps): return None
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        segs = []
        for i, p in enumerate(self.pipes):
            pts = p.get("pts") or []
            lay = p.get("layer", "")
            for k in range(len(pts) - 1):
                segs.append((i, k, pts[k], pts[k + 1], lay))

        # Cada hit lleva su "estado" ya clasificado.
        self._conflict_hits = []
        approvals = {(int(c["pipe_a"]), int(c["pipe_b"]), round(float(c["x"]), 3), round(float(c["y"]), 3))
                      for c in (getattr(self, "cross_connections", None) or [])}
        Z_TOL = 0.10        # ft — misma cota si |za - zb| <= Z_TOL
        R_PX = 7.0
        red_col   = QtGui.QColor(180, 20, 20)
        blue_col  = QtGui.QColor(30, 90, 220)
        green_col = QtGui.QColor(30, 160, 60)
        yellow_br = QtGui.QBrush(QtGui.QColor(255, 235, 60))
        cyan_br   = QtGui.QBrush(QtGui.QColor(180, 220, 255))
        greenbr   = QtGui.QBrush(QtGui.QColor(180, 240, 200))
        ign = QtWidgets.QGraphicsItem.ItemIgnoresTransformations
        n_conf = n_sug = n_ap = 0
        for a in range(len(segs)):
            ia, ka, a1, a2, la = segs[a]
            for b in range(a + 1, len(segs)):
                ib, kb, b1, b2, lb = segs[b]
                if ia == ib: continue
                cp = _seg_inter(a1, a2, b1, b2)
                if cp is None: continue
                cx, cy = cp
                za = self._pipe_z_at(ia, ka, cx, cy)
                zb = self._pipe_z_at(ib, kb, cx, cy)
                aprobado = ((min(ia, ib), max(ia, ib), round(cx, 3), round(cy, 3)) in approvals)
                # Clasificación del cruce.
                if za is None or zb is None:
                    estado = "conflicto"       # sin cotas → tratar como conflicto
                elif abs(za - zb) <= Z_TOL:
                    estado = "conflicto"       # misma cota → chocan
                else:
                    estado = "aprobado" if aprobado else "sugerencia"
                self._conflict_hits.append((cx, cy, ia, ib, ka, kb, za, zb, estado))
                if estado == "conflicto":  n_conf += 1
                elif estado == "aprobado": n_ap += 1
                else:                       n_sug += 1
                # Dibujo según estado.
                if estado == "conflicto":
                    pen = QtGui.QPen(red_col, 2.0); pen.setCosmetic(True)
                    brush = yellow_br; text = "!"; text_col = red_col
                elif estado == "aprobado":
                    pen = QtGui.QPen(green_col, 2.0); pen.setCosmetic(True)
                    brush = greenbr; text = "✓"; text_col = green_col
                else:  # sugerencia
                    pen = QtGui.QPen(blue_col, 2.0); pen.setCosmetic(True)
                    brush = cyan_br; text = "↕"; text_col = blue_col
                circ = sc.addEllipse(-R_PX, -R_PX, R_PX * 2, R_PX * 2, pen, brush)
                circ.setPos(cx, cy); circ.setFlag(ign)
                circ.setZValue(Z_HANDLE + 5); self._overlay.append(circ)
                t = sc.addText(text); t.setDefaultTextColor(text_col)
                f = t.font(); f.setPixelSize(11); f.setBold(True); t.setFont(f)
                t.document().setDocumentMargin(0)
                br = t.boundingRect()
                t.setPos(cx, cy); t.setFlag(ign)
                t.setTransform(QtGui.QTransform().translate(-br.width() / 2, -br.height() / 2))
                t.setZValue(Z_HANDLE + 6); self._overlay.append(t)
                # Tooltip por estado.
                z_desc = ""
                if za is not None and zb is not None:
                    z_desc = f"\nZ «{la}» = {za:.2f} ft   |   Z «{lb}» = {zb:.2f} ft (Δ = {abs(za - zb):.2f} ft)"
                elif za is not None or zb is not None:
                    z_desc = "\n(a una de las dos le falta la cota — no se puede confirmar Δ)"
                else:
                    z_desc = "\n(sin cotas en ninguna — no se puede confirmar Δ)"
                if estado == "conflicto":
                    tip = "⚠ CONFLICTO — cruce con la misma cota (las tuberías chocan). Revisa la geometría o las cotas."
                elif estado == "aprobado":
                    tip = "✓ Conexión vertical aprobada — al importar se dibuja una tubería vertical uniendo las dos cotas."
                else:
                    tip = "↕ Sugerencia — cotas distintas, pasan una por encima de la otra. Click para conectarlas con una tubería vertical."
                pair = f"Dos tramos de «{la}»" if la == lb else f"«{la}» × «{lb}»"
                circ.setToolTip(f"{tip}\n{pair}{z_desc}")

        if hasattr(self, "lbl_info"):
            partes = []
            if n_conf > 0: partes.append(f"⚠ {n_conf} conflicto(s)")
            if n_sug > 0:  partes.append(f"↕ {n_sug} sugerencia(s)")
            if n_ap > 0:   partes.append(f"✓ {n_ap} aprobada(s)")
            if partes: self.lbl_info.setText(" · ".join(partes))

    def _try_click_conflict(self, x, y):
        """Si el click está sobre una marca de cruce, abre el diálogo
        correspondiente. Devuelve True si consumió el click."""
        hits = getattr(self, "_conflict_hits", None) or []
        if not hits: return False
        m11 = max(1e-6, self.canvas.transform().m11())
        tol = 10.0 / m11
        tol2 = tol * tol
        for h in hits:
            cx, cy = h[0], h[1]
            if (cx - x) ** 2 + (cy - y) ** 2 <= tol2:
                self._open_conflict_dialog(h)
                return True
        return False

    def _open_conflict_dialog(self, hit):
        """Según el estado del cruce:
          - "conflicto"  → sólo muestra info, no ofrece conectar.
          - "sugerencia" → pregunta si aprobar conexión vertical + válvula.
          - "aprobado"   → pregunta si retirar la aprobación."""
        cx, cy, ia, ib, ka, kb, za, zb, estado = hit
        la = self.pipes[ia].get("layer", "?")
        lb = self.pipes[ib].get("layer", "?")
        if not hasattr(self, "cross_connections") or self.cross_connections is None:
            self.cross_connections = []
        z_info = ""
        if za is not None and zb is not None:
            z_info = f"\n\nCotas en el punto de cruce:\n  • «{la}»: {za:.2f} ft\n  • «{lb}»: {zb:.2f} ft\n  • Diferencia: {abs(za - zb):.2f} ft"
        else:
            z_info = "\n\n(⚠ falta cota en al menos una de las dos utilidades — pon cotas para poder decidir si es conflicto o sugerencia de unión)"

        if estado == "conflicto":
            QtWidgets.QMessageBox.warning(
                self, _tr("Conflicto físico"),
                _tr(f"⚠ CONFLICTO entre «{la}» y «{lb}» — están a la MISMA cota en el cruce y chocan geométricamente.{z_info}\n\n"
                    "No se ofrece conexión automática aquí: hay que corregir la geometría del plano o ajustar la cota de alguna de las dos tuberías."))
            return

        if estado == "aprobado":
            # Retirar aprobación.
            idx = next((i for i, c in enumerate(self.cross_connections)
                        if min(int(c["pipe_a"]), int(c["pipe_b"])) == min(ia, ib)
                        and max(int(c["pipe_a"]), int(c["pipe_b"])) == max(ia, ib)
                        and round(float(c["x"]), 3) == round(cx, 3)
                        and round(float(c["y"]), 3) == round(cy, 3)), None)
            resp = QtWidgets.QMessageBox.question(
                self, _tr("Conexión vertical ya aprobada"),
                _tr(f"Este cruce entre «{la}» y «{lb}» ya está marcado para conectarse con una tubería vertical al importar.{z_info}\n\n"
                    "¿Deseas RETIRAR la aprobación?"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if resp == QtWidgets.QMessageBox.Yes and idx is not None:
                self.cross_connections.pop(idx)
                self._push(); self._redraw()
            return

        # sugerencia → ofrecer conectar.
        resp = QtWidgets.QMessageBox.question(
            self, _tr("Sugerencia de conexión vertical"),
            _tr(f"Las utilidades «{la}» y «{lb}» se cruzan pero están a cotas distintas — no chocan, una pasa por encima de la otra.{z_info}\n\n"
                "¿Quieres conectarlas con una tubería vertical al importar en Civil 3D?\n\n"
                "Sí = se dibuja un tramo vertical uniendo ambas cotas.\n"
                "No = se dejan como están (no se conectan)."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if resp == QtWidgets.QMessageBox.Yes:
            self.cross_connections.append({
                "x": float(cx), "y": float(cy),
                "pipe_a": int(ia), "pipe_b": int(ib),
                "z_a": (None if za is None else float(za)),
                "z_b": (None if zb is None else float(zb)),
                "valve": True,
            })
            self._push(); self._redraw()

    def _draw_structures(self):
        """Dibuja cada buzón como un círculo relleno con el color del pipe al que
        pertenece (mismo vértice). Si show_bz_labels está activo, escribe el código
        del buzón al lado del círculo."""
        if not self.structures: return
        sc = self.canvas.scene(); tol2 = 14.0 ** 2
        # Precomputa color por buzón: mira los pipes NO importados y toma el layer
        # del primero cuyo vértice coincida (dist² ≤ tol²).
        def _color_for(s):
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: return QtGui.QColor(200, 200, 200)
            if s.get("world") or s.get("net") == "pressure":
                # Para presión (sin vértice de pipe dibujado) o buzones importados,
                # gris claro (no hay línea de referencia visible).
                pass
            for p in self.pipes:
                if p.get("world") or not p.get("pts"): continue
                for (vx, vy) in p["pts"]:
                    if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol2:
                        return layer_qcolor(p["layer"])
            if s.get("standalone"):
                return layer_qcolor(s.get("utility") or "ELECTRICO")
            return QtGui.QColor(180, 180, 180)     # buzón sin pipe cercano (raro)
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.2); pen.setCosmetic(True)
        pen_sel = QtGui.QPen(QtGui.QColor(255, 220, 40), 2.5); pen_sel.setCosmetic(True)
        R = 6.0                                     # radio en px (independiente del zoom por _cosmetic pen)
        for i, s in enumerate(self.structures):
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if s.get("world"): continue             # los importados (Excel) están en coord mundo, no lienzo
            if s.get("hidden"): continue             # ocultado por el usuario — sigue en la lista, no en el lienzo
            is_curve = bool(s.get("curve"))
            col = QtGui.QColor(190, 90, 220) if is_curve else _color_for(s); brush = QtGui.QBrush(col)
            selected = i == getattr(self, "sel_curve" if is_curve else "sel_bz", -1)
            use_pen = pen_sel if selected else pen
            r_use = R + 1.5 if selected else R
            # El arco real ya se dibuja como parte de la polilínea del pipe
            # (ver _pipe_display_pts). Para el marcador de la curva, lo
            # colocamos EN el arco (punto medio) — así queda visualmente
            # pegado a la geometría y no "volando" en la esquina teórica,
            # que puede estar lejos del arco cuando el radio es grande.
            # Si la curva está seleccionada, además repintamos el arco encima
            # en amarillo grueso para que sea inequívoco cuál está activa.
            mx, my = sx, sy   # fallback si no hay pipe / geometría inválida
            if is_curve:
                pipe = self._pipe_at_vertex(sx, sy)
                # Arco REAL con el radio explícito (o el auto = 6 × diámetro). La
                # matemática (tangencias, centro, discretización, cap por doble
                # curva) vive en _curve_arc_info + _arc_polyline: envuelve al
                # model_ops.fillet_geo (base pura) añadiéndole el cap 0.48 si el
                # vecino también es curva y el auto-radio. El pipe (ver
                # _pipe_display_pts) ya dibuja este mismo arco integrado en su
                # polilínea; aquí sólo pintamos:
                #   · el marcador (pegado al arco, no volando en la esquina),
                #   · el resalte amarillo cuando la curva está seleccionada,
                #   · los puntos de tangencia (con línea discontinua si el
                #     radio pedido no entró y el plugin lo va a recortar).
                info = self._curve_arc_info(s, pipe) if pipe else None
                if info is not None:
                    arc_pts = self._arc_polyline(info, n_per_90=24)
                    if arc_pts:
                        mx, my = arc_pts[len(arc_pts) // 2]
                    clamped = bool(info.get("clamped"))
                    if selected:
                        hi_col = QtGui.QColor(255, 220, 40)
                        hi_pen = QtGui.QPen(hi_col, 6.0); hi_pen.setCosmetic(True)
                        hi_pen.setCapStyle(QtCore.Qt.RoundCap)
                        if clamped: hi_pen.setStyle(QtCore.Qt.DashLine)
                        path = QtGui.QPainterPath()
                        path.moveTo(*arc_pts[0])
                        for (ax, ay) in arc_pts[1:]:
                            path.lineTo(ax, ay)
                        it = sc.addPath(path, hi_pen)
                        it.setZValue(Z_MARK + 1); self._overlay.append(it)
                        arc_col = hi_col
                    else:
                        arc_col = col
                    # Puntos de tangencia — muestran dónde arranca/termina el arco
                    # sobre cada recta vecina (útil para saber si el radio "cabe").
                    for q in (info["p1"], info["p2"]):
                        it = sc.addEllipse(q[0] - 3, q[1] - 3, 6, 6, use_pen, QtGui.QBrush(arc_col))
                        it.setZValue(Z_MARK + 1); self._overlay.append(it)
            it = sc.addEllipse(mx - r_use, my - r_use, 2 * r_use, 2 * r_use, use_pen, brush)
            it.setZValue(Z_MARK + 1); self._overlay.append(it)
            # Bóveda reconocida (feature de reconocimiento del PDF, dev_santos_v2):
            # su contorno real a escala, con el color de la línea y la medida al
            # seleccionarla.
            outline = s.get("outline")
            if outline and len(outline) >= 3:
                poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in outline])
                open_pen = QtGui.QPen(QtGui.QColor(255, 220, 40) if selected else col, 2 if selected else 1.5)
                open_pen.setCosmetic(True)
                fill = QtGui.QColor(col); fill.setAlpha(45)
                it = sc.addPolygon(poly, open_pen, QtGui.QBrush(fill)); it.setZValue(Z_MARK); self._overlay.append(it)
                if selected and s.get("width_ft") and s.get("length_ft"):
                    t = sc.addText(f"{s['width_ft']:.1f} × {s['length_ft']:.1f} ft")
                    t.setDefaultTextColor(QtGui.QColor(255, 220, 40))
                    t.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
                    t.setPos(max(x for x, _ in outline) + 4, min(y for _, y in outline))
                    t.setZValue(Z_MARK + 2); self._overlay.append(t)
            if self.show_bz_labels and s.get("cod"):
                t = sc.addText(s["cod"]); t.setDefaultTextColor(QtGui.QColor(180, 180, 180))
                t.document().setDocumentMargin(0)
                f = t.font(); f.setPixelSize(11); f.setBold(True); t.setFont(f)
                # Etiqueta también sigue el marcador (mx, my) — así queda
                # junto a la curva y no en la esquina teórica.
                t.setPos(mx + R + 2, my - R - 2); t.setZValue(Z_MARK + 1); self._overlay.append(t)

    def _handles(self, pts):
        sc = self.canvas.scene(); pen = QtGui.QPen(QtGui.QColor(255, 255, 255)); pen.setCosmetic(True)
        for (vx, vy) in pts:
            it = sc.addRect(vx - 5, vy - 5, 10, 10, pen, QtGui.QBrush(QtGui.QColor(255, 180, 40)))
            it.setZValue(Z_HANDLE); self._overlay.append(it)

    def _seg_label(self, sc, text, cx, cy, color, px=24, halo=5.0):
        """Etiqueta de tramo ("T1", "T2"…) centrada sobre el punto (cx, cy):
        relleno del COLOR DE LA LÍNEA con CONTORNO NEGRO GRUESO, al doble del
        tamaño que tenía antes (24px vs 12px).

        Se dibuja en DOS CAPAS porque un QGraphicsTextItem no admite contorno,
        y un solo QGraphicsPathItem con pen+brush tampoco sirve: Qt traza el
        pen DESPUÉS de rellenar y centrado sobre el borde del glifo, así que un
        pen grueso se come el relleno y la etiqueta sale casi negra (verificado
        renderizando las variantes). Con dos capas —silueta negra engordada
        detrás, relleno de color encima— el contorno es grueso de verdad y el
        color queda limpio.

        Escala con el zoom, igual que las etiquetas de buzón de
        _draw_structures — misma convención en todo el lienzo.
        """
        font = QtGui.QFont(); font.setPixelSize(px); font.setBold(True)
        path = QtGui.QPainterPath()
        path.addText(0.0, 0.0, font, text)            # baseline en (0,0)
        w = QtGui.QFontMetricsF(font).horizontalAdvance(text)
        x, y = cx - w / 2.0, cy - 8.0                 # centrado y por encima
        halo_pen = QtGui.QPen(QtGui.QColor(0, 0, 0), halo)
        halo_pen.setJoinStyle(QtCore.Qt.RoundJoin); halo_pen.setCapStyle(QtCore.Qt.RoundCap)
        for pen, brush in ((halo_pen, QtGui.QBrush(QtGui.QColor(0, 0, 0))),
                           (QtGui.QPen(QtCore.Qt.NoPen), QtGui.QBrush(color))):
            it = sc.addPath(path, pen, brush)
            it.setPos(x, y); it.setZValue(Z_MARK + 2); self._overlay.append(it)

    def _poly(self, pts, color, width, dots=False, z=Z_MARK, dash=False):
        sc = self.canvas.scene(); pen = QtGui.QPen(color, width); pen.setCosmetic(True)
        if dash: pen.setStyle(QtCore.Qt.DashLine)
        for a, b in zip(pts, pts[1:]):
            it = sc.addLine(a[0], a[1], b[0], b[1], pen); it.setZValue(z); self._overlay.append(it)
        if dots:
            for (x, y) in pts:
                it = sc.addEllipse(x - 3, y - 3, 6, 6, pen, QtGui.QBrush(color)); it.setZValue(z); self._overlay.append(it)

    def _arrow(self, a, b, color):
        ang = math.atan2(a[1] - b[1], a[0] - b[0]); L = self.leader_hpx * 0.8
        p1 = (a[0] - L * math.cos(ang - 0.4), a[1] - L * math.sin(ang - 0.4))
        p2 = (a[0] - L * math.cos(ang + 0.4), a[1] - L * math.sin(ang + 0.4))
        poly = QtGui.QPolygonF([QtCore.QPointF(*a), QtCore.QPointF(*p1), QtCore.QPointF(*p2)])
        it = self.canvas.scene().addPolygon(poly, QtGui.QPen(color), QtGui.QBrush(color)); it.setZValue(Z_MARK); self._overlay.append(it)

    # ─────────────────────────── coords ───────────────────────────
    def _to_cad(self, x, y):
        # Compuerta única: si hay georreferencia activa, píxel→UTM real; si no, escala del titleblock.
        if self.georef.active():
            return self.georef.to_world(x, y)
        return G.to_cad(x, y, self.scale, self.rot, self.W, self.H, self.derot, self.zoom)

    def _georef_base_doc(self, doc):
        """Con georreferencia activa, transforma TODO el plano base al mismo sistema
        REAL que las anotaciones. El plano base viene en coordenadas de titleblock
        (G.to_cad sin georref); ajustamos una afín base→real muestreando 3 puntos
        (base = G.to_cad(px), real = georef.to_world(px)) y la aplicamos a todas
        las entidades del modelspace. Así base + anotaciones quedan alineados."""
        from ezdxf.math import Matrix44
        pm = self.canvas.pixmap_item.pixmap()
        w, h = pm.width(), pm.height()
        samples = [(0.1 * w, 0.1 * h), (0.9 * w, 0.15 * h), (0.15 * w, 0.9 * h)]
        src = [G.to_cad(x, y, self.scale, self.rot, self.W, self.H, self.derot, self.zoom) for (x, y) in samples]
        dst = [self.georef.to_world(x, y) for (x, y) in samples]
        M, _, _ = georef_mod.fit(src, dst, "affine")
        a, b, c = M[0]; d, e, f = M[1]
        mat = Matrix44((a, d, 0, 0), (b, e, 0, 0), (0, 0, 1, 0), (c, f, 0, 1))
        msp = doc.modelspace()
        for ent in list(msp):
            try:
                ent.transform(mat)
            except Exception:
                pass                                     # entidad que no soporta transform: se deja

    def _set_geodata(self, doc):
        """Incrusta el sistema de coordenadas (EPSG del georef) como GeoData, para
        que el CAD reconozca el plano geolocalizado.
        Best-effort: si algo falla, no rompe la exportación."""
        if not self.georef.active():
            return
        try:
            epsg = int(self.georef.epsg)
            gd = doc.modelspace().new_geodata()
            gd.coordinate_system_definition = f"EPSG:{epsg}"
        except Exception:
            pass

    def _set_plan_view(self, doc):
        """Hace que el DXF se abra en vista de PLANTA (top) y encuadrado al dibujo,
        para que no aparezca como una hoja inclinada ni diminuta al abrirlo."""
        try:
            from ezdxf import bbox
            ext = bbox.extents(doc.modelspace())
            if not ext.has_data:
                return
            cx = (ext.extmin.x + ext.extmax.x) / 2.0
            cy = (ext.extmin.y + ext.extmax.y) / 2.0
            h = (ext.extmax.y - ext.extmin.y) or (ext.extmax.x - ext.extmin.x) or 100.0
            doc.set_modelspace_vport(h * 1.15, center=(cx, cy))   # vista top, centrada
        except Exception:
            pass

    def _maybe_export_dwg(self, doc, out):
        """Si el usuario lo activó, genera también un .dwg junto al .dxf usando el
        ODA File Converter (ezdxf.addons.odafc). Si ODA no está, avisa y deja el DXF."""
        if not (getattr(self, "act_dwg", None) and self.act_dwg.isChecked()):
            return
        dwg = os.path.splitext(out)[0] + ".dwg"
        try:
            from ezdxf.addons import odafc
            if not odafc.is_installed():
                QtWidgets.QMessageBox.information(self, "DWG",
                    "Para generar DWG necesitas instalar el ODA File Converter (gratuito).\n"
                    "Se guardó solo el DXF; ábrelo en tu CAD y «Guardar como DWG» si lo necesitas ahora.")
                return
            odafc.export_dwg(doc, dwg, replace=True)
            self._info(f"DWG generado: {os.path.basename(dwg)}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "DWG", f"No se pudo generar el DWG (se conserva el DXF).\n\n{e}")

    def _plan_bbox_real(self):
        """Recuadro del plano en coordenadas reales (del georef), desde las esquinas
        de la página. Devuelve (xmin, ymin, xmax, ymax)."""
        pm = self.canvas.pixmap_item.pixmap()
        w, h = pm.width(), pm.height()
        cs = [self.georef.to_world(x, y) for (x, y) in ((0, 0), (w, 0), (w, h), (0, h))]
        xs = [c[0] for c in cs]; ys = [c[1] for c in cs]
        return (min(xs), min(ys), max(xs), max(ys))

    def _maybe_add_la_reference(self, doc):
        """Si el usuario lo activó y el plano está georreferenciado a EPSG:2229,
        descarga de NavigateLA las calles (y opcional parcelas) del área y las
        añade como capas de referencia. Falla en silencio con aviso."""
        want_streets = getattr(self, "act_la_ref", None) and self.act_la_ref.isChecked()
        want_parcels = getattr(self, "act_la_parcels", None) and self.act_la_parcels.isChecked()
        if not (want_streets or want_parcels):
            return
        if not self.georef.active() or int(self.georef.epsg) != 2229:
            QtWidgets.QMessageBox.information(self, "Capas de LA",
                "Las capas reales de LA solo se pueden agregar si el plano está "
                "georreferenciado a EPSG:2229 (State Plane de LA)."); return
        try:
            from geo.la_reference import add_reference_layers
            nc, npa = add_reference_layers(doc, self._plan_bbox_real(),
                                           streets=bool(want_streets), parcels=bool(want_parcels))
            self._info(f"Capas de LA agregadas: {nc} tramos de calle, {npa} parcelas.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Capas de LA",
                f"No se pudieron descargar las capas de LA (¿internet?).\n\n{e}")

    # ─────────────────────────── exportar ───────────────────────────
    def run_pipeline(self, mode="todo"):
        """mode: 'todo' = PDF digitalizado + anotaciones · 'pdf' = solo el PDF ·
        'anot' = solo las anotaciones dibujadas en el programa."""
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Nada"), _tr("Abre un PDF o proyecto.")); return
        need_pdf = mode in ("todo", "pdf")
        if need_pdf and (not self.pdf_path or not os.path.isfile(self.pdf_path)):
            QtWidgets.QMessageBox.information(self, _tr("Sin PDF"), _tr("No se encontró el PDF original. Se exportarán solo las anotaciones (utilidades, leaders, textos)."))
            mode = "anot"; need_pdf = False
        base = os.path.splitext(os.path.basename(self.pdf_path))[0] if self.pdf_path else "proyecto"
        suffix = {"todo": "_completo", "pdf": "_plano", "anot": "_anotaciones"}[mode]
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar DXF", os.path.join(DOWNLOADS, base + suffix + ".dxf"), "DXF (*.dxf)")
        if not out: return
        self._out = out; self._mode = mode
        if not need_pdf:                                   # solo anotaciones: sin pipeline
            try:
                doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
                self._merge_into(doc, marks=True)
                self._maybe_add_la_reference(doc)        # capas reales de LA (si se activó)
                self._set_geodata(doc)                   # geolocaliza el DXF en EPSG:2229
                self._set_plan_view(doc)                 # abrir en vista 2D/planta, encuadrado
                doc.saveas(out)
                self._maybe_export_dwg(doc, out)         # además .dwg si se activó (ODA)
                geo_active = self.georef.active()
                geo_msg = " [georef]" if geo_active else ""
                if self.georef.matrix and not geo_active:
                    m = self.georef.matrix
                    det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
                    geo_msg = (f"\n\n⚠ Georef: matriz presente pero active()=False."
                               f"\n  matrix[0]={m[0]}\n  matrix[1]={m[1]}"
                               f"\n  det={det:.6f}, epsg={self.georef.epsg}"
                               f"\n  → Exportado en coordenadas de escala.")
                elif not self.georef.matrix:
                    geo_msg += "\n\n(Sin georreferenciación configurada.)"
                QtWidgets.QMessageBox.information(self, "Listo", f"Exportado (solo anotaciones):\n{out}{geo_msg}")
                self._info("DXF de anotaciones exportado." + (" (georef)" if geo_active else ""))
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
            return
        self._tmp = out + ".base.tmp.dxf"
        self._prog = QtWidgets.QProgressDialog("Digitalizando el plano…", None, 0, 0, self)
        self._prog.setWindowTitle("Procesando"); self._prog.setWindowModality(QtCore.Qt.WindowModal)
        self._prog.setCancelButton(None); self._prog.show()
        self._worker = PipelineWorker(self.pdf_path, self._tmp); self._worker.done.connect(self._pipeline_done); self._worker.start()

    def _pipeline_done(self, tmp, err):
        if getattr(self, "_prog", None): self._prog.close()
        if err: QtWidgets.QMessageBox.critical(self, "Error al digitalizar", err); return
        try:
            marks = (self._mode == "todo")               # 'pdf' = solo el plano, sin anotaciones
            doc = ezdxf.readfile(tmp); C.apply_imperial_header(doc)   # reafirma imperial ($MEASUREMENT=0) tras leer el plano base
            if self.georef.active():                     # lleva el plano base al mismo sistema REAL que las anotaciones
                self._georef_base_doc(doc)
            self._merge_into(doc, marks=marks)
            self._maybe_add_la_reference(doc)            # capas reales de LA (si se activó)
            self._set_geodata(doc)                       # geolocaliza el DXF en EPSG:2229
            self._set_plan_view(doc)                     # abrir en vista 2D/planta, encuadrado
            doc.saveas(self._out)
            self._maybe_export_dwg(doc, self._out)       # además .dwg si se activó (ODA)
            if os.path.exists(tmp): os.remove(tmp)
            geo_active = self.georef.active()
            geo_warn = ""
            if self.georef.matrix and not geo_active:
                m = self.georef.matrix
                det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
                geo_warn = (f"\n\n⚠ Georreferenciación: matriz presente pero active()=False."
                            f"\n  matrix[0]={m[0]}\n  matrix[1]={m[1]}"
                            f"\n  det={det:.6f}, epsg={self.georef.epsg}"
                            f"\n  → Se exportó en coordenadas de escala (sin georef).")
            elif not self.georef.matrix:
                geo_warn = "\n\n(Sin georreferenciación configurada.)"
            geo_tag = " [georef]" if geo_active else ""
            if marks:
                nreg = sum(1 for r in self.erase_regions if r.get("enabled", True))
                msg = (f"Exportado (PDF + anotaciones){geo_tag}:\n{self._out}\n\n{len(self.pipes)} utilidades, "
                       f"{len(self.leaders)} leaders, {len(self.text_marks)} textos, {nreg} zonas borradas.{geo_warn}")
            else:
                msg = f"Exportado (solo el PDF digitalizado){geo_tag}:\n{self._out}{geo_warn}"
            QtWidgets.QMessageBox.information(self, "Listo", msg); self._info("DXF exportado." + (" (georef)" if geo_active else ""))
        except Exception as e:
            import traceback; QtWidgets.QMessageBox.critical(self, "Error al guardar", f"{e}\n{traceback.format_exc()}")

    def _merge_into(self, doc, marks=True):
        dxf_export.merge_into(self, doc, marks=marks)

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
        from model import network_kind
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
        import civil_catalog as _cc
        self._bz_prop_guard = True
        try:
            in_tab = self._current_tab() == TAB_BZ
            self.gprop_bz.setVisible(in_tab)
            has_sel = 0 <= self.sel_bz < len(self.structures)
            # Habilitar/deshabilitar todos los controles del groupbox según haya selección
            for w in (self.bz_cod, self.bz_rim, self.bz_sump, self.bz_family, self.bz_size,
                      self.bz_height, self.bz_is_curve, self.chk_bz_hidden):
                w.setEnabled(has_sel)
            if not has_sel:
                self.gprop_bz.setTitle("Propiedades del buzón — selecciona uno de la lista")
                self.bz_is_curve.setVisible(True)
                self.bz_is_curve.setChecked(False)
                self.chk_bz_hidden.setChecked(False)
                return
            s = self.structures[self.sel_bz]
            net = s.get("net") or "gravity"
            self.gprop_bz.setTitle("Propiedades de la caja" if net == "conduit"
                                    else "Propiedades del buzón")
            self.bz_cod.setText(s.get("cod", ""))
            self.bz_rim.setValue(float(s.get("rim") or 0.0))
            self.bz_sump.setValue(float(s.get("sump") or 0.0))
            self.bz_height.setValue(float(s.get("height_ft") or 0.0))
            self.bz_net_lbl.setText("conduit (eléctrico/telecom)" if net == "conduit" else "gravedad")
            self.bz_origin_lbl.setText("Excel" if s.get("world") else "dibujo")
            # "Cambiar a elemento curvo" solo tiene sentido en una ESQUINA: un
            # vértice donde se juntan dos tramos (dos tangentes). Un buzón al final
            # de una línea conecta a una sola → no puede ser un codo/curva, así que
            # ahí se oculta la opción.
            self.bz_is_curve.setVisible(self._bz_segment_count(s) >= 2)
            self.bz_is_curve.setChecked(bool(s.get("curve")))
            self.chk_bz_hidden.setChecked(bool(s.get("hidden")))
            # Familias del catálogo imperial de estructuras (gravedad).
            self.bz_family.blockSignals(True); self.bz_family.clear()
            fams = _cc.imperial_structures(self.civil_year) if self.civil_year else []
            self.bz_family.addItem("(por defecto)", "")
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
        import civil_catalog as _cc
        self.bz_size.blockSignals(True); self.bz_size.clear()
        if not fid or not self.civil_year:
            self.bz_size.addItem("(sin familia)", ""); self.bz_size.setEnabled(False)
            self.bz_size.blockSignals(False); return
        sizes = _cc.structure_sizes(self.civil_year, fid)
        if not sizes:
            self.bz_size.addItem("(sin tamaños detectados)", ""); self.bz_size.setEnabled(False)
        else:
            self.bz_size.setEnabled(True); self.bz_size.addItem("(por defecto)", "")
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
                QtWidgets.QMessageBox.warning(self, "Código repetido",
                    f"Ya existe un buzón con código '{cod_new}'. Elige otro.")
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

    def _refresh_bz_list_item(self, idx):
        """idx es un índice de self.structures (no una fila de bz_list): se
        resuelve la fila visible vía self._bz_rows."""
        if not (0 <= idx < len(self.structures)) or idx not in self._bz_rows: return
        s = self.structures[idx]
        fam = s.get("part") or "(sin familia)"
        sz = f"  {s['part_size']}" if s.get("part_size") else ""
        emoji = "🚫" if s.get("hidden") else ("🟠" if s.get("net") == "conduit" else "🔵")
        item = self.bz_list.item(self._bz_rows.index(idx))
        if item:
            item.setText(f"{emoji} {s.get('cod', '?')}  ·  {fam}{sz}")
            if s.get("hidden"):
                item.setForeground(QtGui.QColor(_theme.tokens().text_muted))
            else:
                item.setData(QtCore.Qt.ForegroundRole, None)
            item.setToolTip("Oculto — no se dibuja ni se crea en Civil3D como buzón real." if s.get("hidden") else "")

    def _bz_curve_toggled(self, v):
        """Checkbox 'No colocar buzón — es un elemento curvo' en la tab Buzones."""
        if self._bz_prop_guard: return
        if not (0 <= self.sel_bz < len(self.structures)): return
        s = self.structures[self.sel_bz]
        if bool(s.get("curve")) == bool(v): return
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
        self._refresh_lists(); self._redraw()

    # ─────────────────────────── Tab Curvas: selección, panel, edición ─────
    def _pipe_at_vertex(self, x, y, tol=14.0):
        # Búsqueda de tubería por vértice cercano (pura) en model_ops.
        return model_ops.pipe_at_vertex(self.pipes, x, y, tol)

    # ─────────────────── Mover con precisión (panel izquierdo) ─────────────
    def _build_move_precise_panel(self, lay):
        """Panel para desplazar la selección actual una distancia EXACTA en
        pies. Se compone de:
          · Etiqueta con lo seleccionado (color + descripción). Fondo gris si
            no hay nada seleccionado.
          · Radio: toda la utilidad / solo un vértice (con QSpinBox del índice).
          · Botones flecha ↑↓←→ + "paso" en ft para nudge rápidos.
          · Campos ΔX / ΔY con botón "Aplicar" para vector arbitrario.
        Todo entra en el mismo contenedor `lay` (QVBoxLayout de la sección)."""
        # Encabezado: qué está seleccionado.
        self.mv_lbl_sel = QtWidgets.QLabel(_tr("(nada seleccionado)"))
        self.mv_lbl_sel.setWordWrap(True)
        self.mv_lbl_sel.setStyleSheet(
            "padding:6px 8px; border-radius:4px; background:#333; color:#ccc;")
        lay.addWidget(self.mv_lbl_sel)

        # Alcance del movimiento (radios apilados vertical → no fuerzan ancho).
        self.mv_grp_scope = QtWidgets.QWidget()
        sc_l = QtWidgets.QVBoxLayout(self.mv_grp_scope); sc_l.setContentsMargins(0, 0, 0, 0)
        sc_l.setSpacing(2)
        self.mv_rb_all = QtWidgets.QRadioButton(_tr("Toda la utilidad"))
        self.mv_rb_vert = QtWidgets.QRadioButton(_tr("Un vértice"))
        self.mv_rb_all.setChecked(True)
        sc_grp = QtWidgets.QButtonGroup(self.mv_grp_scope)
        sc_grp.addButton(self.mv_rb_all); sc_grp.addButton(self.mv_rb_vert)
        # Fila del índice de vértice: label + spin al lado.
        vert_row = QtWidgets.QHBoxLayout(); vert_row.setContentsMargins(20, 0, 0, 0)
        vert_row.addWidget(QtWidgets.QLabel(_tr("Vértice #:")))
        self.mv_vert_idx = QtWidgets.QSpinBox()
        self.mv_vert_idx.setRange(0, 999); self.mv_vert_idx.setPrefix("V")
        self.mv_vert_idx.setMinimumWidth(60)
        self.mv_vert_idx.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.mv_vert_idx.setToolTip(_tr("Índice del vértice a mover (0 = primero)."))
        self.mv_vert_idx.setEnabled(False)
        self.mv_rb_vert.toggled.connect(self.mv_vert_idx.setEnabled)
        vert_row.addWidget(self.mv_vert_idx, 1)
        sc_l.addWidget(self.mv_rb_all); sc_l.addWidget(self.mv_rb_vert); sc_l.addLayout(vert_row)
        lay.addWidget(self.mv_grp_scope)

        # Paso rápido con flechas
        step_row = QtWidgets.QHBoxLayout(); step_row.setContentsMargins(0, 0, 0, 0)
        step_row.addWidget(QtWidgets.QLabel(_tr("Paso (ft):")))
        self.mv_step_ft = QtWidgets.QDoubleSpinBox()
        self.mv_step_ft.setDecimals(2); self.mv_step_ft.setRange(0.01, 10000.0)
        self.mv_step_ft.setSingleStep(0.5); self.mv_step_ft.setValue(1.0)
        self.mv_step_ft.setMinimumWidth(70)
        self.mv_step_ft.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        step_row.addWidget(self.mv_step_ft, 1)
        lay.addLayout(step_row)

        # Flechas en cruz (grid). Los botones NO tienen ancho fijo — con
        # setSizePolicy Preferred el layout los encoge cuando el dock se
        # angosta, así el panel deja de forzar scroll horizontal. Se usan
        # setMinimumSize para no perderlos completamente en anchos mínimos.
        arrows = QtWidgets.QGridLayout(); arrows.setSpacing(4)
        arrows.setContentsMargins(0, 0, 0, 0)
        self.mv_btn_up = QtWidgets.QPushButton(); self.mv_btn_up.setIcon(_icon("mdi:arrow-up-bold"))
        self.mv_btn_dn = QtWidgets.QPushButton(); self.mv_btn_dn.setIcon(_icon("mdi:arrow-down-bold"))
        self.mv_btn_lf = QtWidgets.QPushButton(); self.mv_btn_lf.setIcon(_icon("mdi:arrow-left-bold"))
        self.mv_btn_rt = QtWidgets.QPushButton(); self.mv_btn_rt.setIcon(_icon("mdi:arrow-right-bold"))
        for b in (self.mv_btn_up, self.mv_btn_dn, self.mv_btn_lf, self.mv_btn_rt):
            b.setIconSize(QtCore.QSize(20, 20))
            b.setMinimumSize(32, 34)
            b.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.mv_btn_up.setToolTip(_tr("Arriba (Y+) por Paso"))
        self.mv_btn_dn.setToolTip(_tr("Abajo (Y−) por Paso"))
        self.mv_btn_lf.setToolTip(_tr("Izquierda (X−) por Paso"))
        self.mv_btn_rt.setToolTip(_tr("Derecha (X+) por Paso"))
        arrows.addWidget(self.mv_btn_up, 0, 1)
        arrows.addWidget(self.mv_btn_lf, 1, 0)
        arrows.addWidget(self.mv_btn_rt, 1, 2)
        arrows.addWidget(self.mv_btn_dn, 2, 1)
        arrows.setColumnStretch(0, 1); arrows.setColumnStretch(1, 1); arrows.setColumnStretch(2, 1)
        self.mv_btn_up.clicked.connect(lambda: self._apply_move_by_ft(0.0, +self.mv_step_ft.value()))
        self.mv_btn_dn.clicked.connect(lambda: self._apply_move_by_ft(0.0, -self.mv_step_ft.value()))
        self.mv_btn_lf.clicked.connect(lambda: self._apply_move_by_ft(-self.mv_step_ft.value(), 0.0))
        self.mv_btn_rt.clicked.connect(lambda: self._apply_move_by_ft(+self.mv_step_ft.value(), 0.0))
        lay.addLayout(arrows)

        # Vector arbitrario ΔX, ΔY.
        # Los spinboxes se construyen con un helper local que, si el usuario
        # borra el texto y deja el campo vacío, lo colapsa a 0.00 en vez de
        # dejar el valor anterior "pegado" (comportamiento raro de QDoubleSpinBox
        # por defecto — la primera versión de este panel lo tenía).
        vec_lbl = QtWidgets.QLabel(_tr("O escribe un desplazamiento exacto:"))
        vec_lbl.setStyleSheet("margin-top:6px; color:#aaa;")
        vec_lbl.setWordWrap(True)
        lay.addWidget(vec_lbl)
        vec = QtWidgets.QGridLayout(); vec.setSpacing(4); vec.setContentsMargins(0, 0, 0, 0)
        def _dsb_delta():
            b = QtWidgets.QDoubleSpinBox()
            b.setDecimals(2); b.setRange(-1e6, 1e6); b.setSingleStep(0.5)
            b.setMinimumWidth(70)
            b.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            le = b.lineEdit()
            # Al perder el foco: si el texto quedó vacío o sin dígitos, set 0.
            def _coerce_empty():
                txt = (le.text() or "").strip()
                # Quitar cualquier prefijo/sufijo para chequear si hay número.
                # Los DoubleSpinBox nuestros no usan prefix/suffix, así que txt
                # es directamente el número (o vacío/signo suelto).
                if not txt or txt in ("-", "+", ",", "."):
                    b.setValue(0.0)
            le.editingFinished.connect(_coerce_empty)
            return b
        vec.addWidget(QtWidgets.QLabel("ΔX (ft):"), 0, 0)
        self.mv_dx = _dsb_delta()
        vec.addWidget(self.mv_dx, 0, 1)
        vec.addWidget(QtWidgets.QLabel("ΔY (ft):"), 1, 0)
        self.mv_dy = _dsb_delta()
        vec.addWidget(self.mv_dy, 1, 1)
        vec.setColumnStretch(1, 1)
        self.mv_btn_apply = QtWidgets.QPushButton("  " + _tr("Aplicar"))
        self.mv_btn_apply.setIcon(_icon("mdi:check"))
        self.mv_btn_apply.setIconSize(QtCore.QSize(18, 18))
        self.mv_btn_apply.clicked.connect(
            lambda: self._apply_move_by_ft(self.mv_dx.value(), self.mv_dy.value()))
        vec.addWidget(self.mv_btn_apply, 2, 0, 1, 2)
        lay.addLayout(vec)

        # Nota UX
        note = QtWidgets.QLabel(_tr(
            "<i>ΔY+ = norte del plano. Cada movimiento respeta Deshacer (Ctrl+Z).</i>"))
        note.setWordWrap(True); note.setStyleSheet("color:#888; margin-top:4px;")
        lay.addWidget(note)

        # Estado inicial: deshabilitado hasta que haya selección.
        self._update_move_panel()

    def _update_move_panel(self):
        """Habilita/deshabilita el panel según lo que esté seleccionado y
        actualiza el label con qué se va a mover. Se llama desde _update_ui()."""
        if not hasattr(self, "mv_lbl_sel"): return
        info = self._selected_move_target()
        widgets = (self.mv_grp_scope, self.mv_step_ft, self.mv_btn_up, self.mv_btn_dn,
                   self.mv_btn_lf, self.mv_btn_rt, self.mv_dx, self.mv_dy, self.mv_btn_apply)
        if info is None:
            for w in widgets: w.setEnabled(False)
            self.mv_lbl_sel.setText(_tr("(nada seleccionado)"))
            self.mv_lbl_sel.setStyleSheet(
                "padding:6px 8px; border-radius:4px; background:#333; color:#ccc;")
            return
        for w in widgets: w.setEnabled(True)
        kind, obj = info
        if kind == "pipe":
            layer = obj.get("layer", ""); diam = obj.get("diam") or "?"
            n = len(obj.get("pts") or [])
            col = layer_qcolor(layer).name()
            self.mv_lbl_sel.setText(_tr("Utilidad {layer} · Ø{diam}\" · {n} vértices").format(
                layer=layer, diam=diam, n=n))
            self.mv_lbl_sel.setStyleSheet(
                f"padding:6px 8px; border-radius:4px; background:{col}; color:white; font-weight:bold;")
            # Ajustar rango del spinbox de vértice
            self.mv_vert_idx.setRange(0, max(0, n - 1))
        elif kind == "struct":
            cod = obj.get("cod") or "(sin código)"
            es_curva = bool(obj.get("curve"))
            tag = _tr("Curva") if es_curva else _tr("Buzón")
            self.mv_lbl_sel.setText(f"{tag} · {cod}")
            self.mv_lbl_sel.setStyleSheet(
                "padding:6px 8px; border-radius:4px; background:#8a3ab9; color:white; font-weight:bold;")
            # Un buzón/curva es un punto — solo aplica "un vértice" implícito.
            self.mv_rb_all.setChecked(True)
            self.mv_rb_vert.setEnabled(False)
            return
        # Radio botones habilitados solo para pipe con >1 vértice.
        self.mv_rb_vert.setEnabled(kind == "pipe" and len(obj.get("pts") or []) > 0)

    def _selected_move_target(self):
        """Determina qué está seleccionado y va a mover el panel. Devuelve
        (kind, obj) o None. Prioridad: pipe → structure (buzón/curva). Otros
        tipos de selección (leader/text/región/centerline) no aplican."""
        if 0 <= getattr(self, "sel_pipe", -1) < len(self.pipes):
            return ("pipe", self.pipes[self.sel_pipe])
        idx = -1
        if 0 <= getattr(self, "sel_bz", -1) < len(self.structures):
            idx = self.sel_bz
        elif 0 <= getattr(self, "sel_curve", -1) < len(self.structures):
            idx = self.sel_curve
        if idx >= 0:
            return ("struct", self.structures[idx])
        return None

    def _apply_move_by_ft(self, dx_ft, dy_ft):
        """Motor de mover: convierte pies a scene pixels usando la escala y
        el zoom actuales, y desplaza el objeto seleccionado en consecuencia.
        Empuja al undo stack antes de mutar. Redibuja al final."""
        if abs(dx_ft) < 1e-9 and abs(dy_ft) < 1e-9: return
        info = self._selected_move_target()
        if info is None:
            self._info(_tr("No hay nada seleccionado para mover.")); return
        if not self.scale or self.scale <= 1e-6:
            QtWidgets.QMessageBox.warning(self, _tr("Sin escala"),
                _tr("La escala del plano no está definida — establece '1\" = X ft' antes de mover.")); return
        # ft → scene px. La conversión inversa a _px_for_ft (que además tiene un
        # cap para textos que aquí NO queremos aplicar).
        px_per_ft = float(self.zoom) / self.scale
        dx_px = dx_ft * px_per_ft
        # Y del plano crece hacia arriba en la vida real, pero en Qt/canvas Y
        # crece hacia ABAJO. Se invierte para que "ΔY+ = norte del plano".
        dy_px = -dy_ft * px_per_ft
        self._push()
        kind, obj = info
        if kind == "pipe":
            pts = obj.get("pts") or []
            if self.mv_rb_vert.isChecked():
                vi = self.mv_vert_idx.value()
                if not (0 <= vi < len(pts)):
                    self._info(_tr("Índice de vértice fuera de rango.")); return
                pts[vi] = (pts[vi][0] + dx_px, pts[vi][1] + dy_px)
                # Si algún buzón/curva coincidía con ese vértice, moverlo
                # también para mantener la coherencia (mismo criterio que
                # _no_manhole_vertex_indices: tol 14 px).
                self._drag_structures_at((pts[vi][0] - dx_px, pts[vi][1] - dy_px), dx_px, dy_px)
                self._info(_tr("Vértice V{vi} movido ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.").format(
                    vi=vi, dx=dx_ft, dy=dy_ft))
            else:
                # Utilidad completa: desplazar TODOS los vértices y arrastrar
                # los buzones/curvas asociados a esos vértices también.
                new_pts = []
                for (px, py) in pts:
                    new_pts.append((px + dx_px, py + dy_px))
                    self._drag_structures_at((px, py), dx_px, dy_px)
                obj["pts"] = new_pts
                self._info(_tr("Utilidad movida ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft ({n} vértices).").format(
                    dx=dx_ft, dy=dy_ft, n=len(new_pts)))
        elif kind == "struct":
            sx, sy = obj.get("x"), obj.get("y")
            if sx is None or sy is None:
                self._info(_tr("El elemento seleccionado no tiene posición en el lienzo.")); return
            obj["x"] = sx + dx_px; obj["y"] = sy + dy_px
            # Además: si algún vértice de pipe coincidía con la vieja posición,
            # arrástralo también para no "despegar" un buzón de su tubería.
            self._drag_pipe_vertices_at((sx, sy), dx_px, dy_px)
            self._info(_tr("Elemento movido ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.").format(
                dx=dx_ft, dy=dy_ft))
        self._dirty = True; self._redraw()

    def _drag_structures_at(self, pos, dx_px, dy_px, tol_px=14.0):
        """Mueve todas las structures cuyo (x,y) coincide con `pos` dentro de
        `tol_px`. Se usa cuando un vértice de pipe se desplaza, para mantener
        pegado el buzón/curva que estaba en ese vértice."""
        tol2 = tol_px * tol_px
        px, py = pos
        for s in self.structures:
            if s.get("world"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if (sx - px) ** 2 + (sy - py) ** 2 <= tol2:
                s["x"] = sx + dx_px; s["y"] = sy + dy_px

    def _drag_pipe_vertices_at(self, pos, dx_px, dy_px, tol_px=14.0):
        """Mueve todos los vértices de todas las pipes cuya posición coincide
        con `pos` dentro de `tol_px`. Complemento simétrico de _drag_structures_at."""
        tol2 = tol_px * tol_px
        px, py = pos
        for p in self.pipes:
            if p.get("world") or not p.get("pts"): continue
            new_pts = list(p["pts"])
            changed = False
            for i, (vx, vy) in enumerate(new_pts):
                if (vx - px) ** 2 + (vy - py) ** 2 <= tol2:
                    new_pts[i] = (vx + dx_px, vy + dy_px); changed = True
            if changed: p["pts"] = new_pts

    def _curve_max_radius_ft(self, curve_idx):
        """Radio máximo (en pies) que ImportarRed.cs aceptará para esta curva sin
        recortar. Replica la fórmula del plugin:
          t_max = min(distPrev·capPrev, distNext·capNext)
          r_max = t_max · tan(Δ/2)
        donde Δ es el ángulo interno entre los dos tramos rectos (dot product de
        las direcciones que salen del vértice curvo), y cap es 0.48 si el vértice
        vecino también es curva o 0.9 si es recto. Devuelve None si no aplica
        (curva sin tubería asociada, tramo casi recto, etc.)."""
        import math
        if not (0 <= curve_idx < len(self.structures)): return None
        s = self.structures[curve_idx]
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None: return None
        p = self._pipe_at_vertex(sx, sy)
        if p is None or not p.get("pts") or len(p["pts"]) < 3: return None
        # Índice del vértice de la tubería que corresponde a esta curva
        tol2 = 14.0 ** 2
        vi = None
        for i, (vx, vy) in enumerate(p["pts"]):
            if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol2:
                vi = i; break
        if vi is None or vi <= 0 or vi >= len(p["pts"]) - 1:
            return None
        # Detectar si los vecinos vi-1 y vi+1 también son vértices curvos
        # (misma tubería). Usa la misma tolerancia que _no_manhole_vertex_indices.
        def es_curva_en(idx_v):
            vx, vy = p["pts"][idx_v]
            for o in self.structures:
                if not o.get("curve") or o.get("world"): continue
                ox, oy = o.get("x"), o.get("y")
                if ox is None or oy is None: continue
                if (ox - vx) ** 2 + (oy - vy) ** 2 <= tol2: return True
            return False
        cap_prev = 0.48 if es_curva_en(vi - 1) else 0.9
        cap_next = 0.48 if es_curva_en(vi + 1) else 0.9
        # Distancias en pies (usar _to_cad para convertir de píxeles a CAD ft).
        try:
            cx_ft, cy_ft = self._to_cad(*p["pts"][vi])
            px_ft, py_ft = self._to_cad(*p["pts"][vi - 1])
            nx_ft, ny_ft = self._to_cad(*p["pts"][vi + 1])
        except Exception:
            return None
        vpx, vpy = px_ft - cx_ft, py_ft - cy_ft
        vnx, vny = nx_ft - cx_ft, ny_ft - cy_ft
        dist_prev = math.hypot(vpx, vpy)
        dist_next = math.hypot(vnx, vny)
        if dist_prev < 1e-6 or dist_next < 1e-6: return None
        # Ángulo interno (mismo criterio que el plugin: Acos del dot product
        # de los vectores UNITARIOS que salen del vértice curvo).
        cos_d = (vpx * vnx + vpy * vny) / (dist_prev * dist_next)
        cos_d = max(-1.0, min(1.0, cos_d))
        delta_rad = math.acos(cos_d)
        # Casi recta: no aplica límite (el plugin salta la curva)
        if math.degrees(delta_rad) > 178.0: return None
        t_max = min(dist_prev * cap_prev, dist_next * cap_next)
        r_max = t_max * math.tan(delta_rad / 2.0)
        return r_max if r_max > 0 else None

    # ───────────────────── arcos reales por vértice curvo ─────────────────────
    def _structure_curve_at(self, x, y, tol_px=14.0):
        """Devuelve la estructura con curve=True cuyo (x,y) coincide con el punto
        dado dentro de tolerancia (misma que usa el exportador DXF). Sirve para
        el hit-test en el lienzo y para dibujar el arco real del pipe."""
        tol2 = tol_px * tol_px
        for s in self.structures:
            if not s.get("curve") or s.get("world"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if (sx - x) ** 2 + (sy - y) ** 2 <= tol2:
                return s
        return None

    def _curve_arc_info(self, s, pipe):
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
        tol2 = 14.0 ** 2
        vi = None
        for j, (vx, vy) in enumerate(pts):
            if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol2:
                vi = j; break
        if vi is None or vi <= 0 or vi >= len(pts) - 1:
            return None
        if not self.scale or self.scale <= 1e-6: return None
        # Radio en pies: explícito o auto = 6 × diámetro interior.
        r_ft = float(s.get("radius_ft") or 0.0)
        if r_ft <= 0.01:
            diam_in = float(pipe.get("diam") or 12.0)
            r_ft = 6.0 * (diam_in / 12.0)
        # Conversión ft → scene px: los pts se renderizan a self.zoom × puntos
        # PDF, y self.scale es ft por punto PDF. → scene_px = ft × zoom / scale.
        r_px = r_ft * float(self.zoom) / self.scale
        if r_px <= 0: return None
        # Cap por vecino curvo — mismo criterio del plugin.
        px_prev, py_prev = pts[vi - 1]
        px_next, py_next = pts[vi + 1]
        cap_prev = 0.48 if self._structure_curve_at(px_prev, py_prev) else 0.9
        cap_next = 0.48 if self._structure_curve_at(px_next, py_next) else 0.9
        # fillet_geo usa un solo max_frac (mínimo de ambos lados es conservador).
        geo = model_ops.fillet_geo((px_prev, py_prev), (sx, sy), (px_next, py_next),
                                    r_px, max_frac=min(cap_prev, cap_next))
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
        out = [pts[0]]
        for j in range(1, n):
            if 0 < j < n - 1:
                s = self._structure_curve_at(*pts[j])
                info = self._curve_arc_info(s, pipe) if s is not None else None
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
                self.gprop_curve.setTitle("Propiedades del elemento curvo — selecciona uno de la lista")
                self.cv_family_lbl.setText("—"); self.cv_size_lbl.setText("—")
                return
            s = self.structures[self.sel_curve]
            net = s.get("net") or "gravity"
            self.gprop_curve.setTitle("Propiedades del elemento curvo")
            self.cv_cod.setText(s.get("cod", ""))
            # Calcular y aplicar el radio máximo geométrico ANTES de setValue.
            # Si no lo aplicamos, el usuario puede escribir p.ej. 100ft y el
            # plugin lo recortará silenciosamente (con warning en consola,
            # pero fuera de vista). Con el límite en la UI, se ve al instante.
            r_max = self._curve_max_radius_ft(self.sel_curve)
            self._cv_radius_max_ft = r_max
            valor_guardado = float(s.get("radius_ft") or 0.0)
            if r_max is not None and r_max > 0.01:
                self.cv_radius.setMaximum(round(r_max, 2))
                self.cv_radius.setToolTip(
                    f"Radio deseado de la tubería curva, en pies. Vacío (0) = automático.\n"
                    f"Máximo permitido por la geometría (tramos rectos adyacentes): "
                    f"{r_max:.2f} ft.")
                # Si el valor guardado excedía el nuevo máximo, sale aviso rojo
                # (además del clamp automático que el spinbox aplica al setValue).
                if valor_guardado > r_max + 1e-3:
                    self.cv_radius_warn.setText(
                        f"⚠ Máximo permitido: {r_max:.2f} ft (limitado por los tramos "
                        f"rectos adyacentes). El valor guardado ({valor_guardado:.2f} ft) "
                        f"se ajustó.")
                    self.cv_radius_warn.setVisible(True)
                else:
                    self.cv_radius_warn.setText(
                        f"Máximo permitido: {r_max:.2f} ft.")
                    self.cv_radius_warn.setVisible(True)
            else:
                self.cv_radius.setMaximum(10000.0)
                self.cv_radius.setToolTip(
                    "Radio deseado de la tubería curva, en pies. Vacío (0) = automático:\n"
                    "al importar en Civil3D se usa 6× el ancho/diámetro interior de la tubería.")
                self.cv_radius_warn.setVisible(False)
                self.cv_radius_warn.setText("")
            self.cv_radius.setValue(valor_guardado)
            self.cv_net_lbl.setText("conduit (eléctrico/telecom)" if net == "conduit" else "gravedad")
            self.cv_origin_lbl.setText("Excel" if s.get("world") else "dibujo")
            # Familia/tamaño heredados de la tubería recta que pasa por este vértice
            # (solo lectura: garantiza que la curva calce con los tramos rectos).
            x, y = s.get("x"), s.get("y")
            p = self._pipe_at_vertex(x, y) if x is not None and y is not None else None
            if p is not None and p.get("pipe_family"):
                import civil_catalog as _cc
                fid = p["pipe_family"]
                pretty = fid
                try:
                    if self.civil_year:
                        pretty = _cc.family_description(self.civil_year, fid, "pipe") or fid
                except Exception: pass
                self.cv_family_lbl.setText(pretty)
                self.cv_size_lbl.setText(p.get("pipe_size") or "(por defecto)")
            else:
                self.cv_family_lbl.setText("(sin tubería detectada)")
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
                QtWidgets.QMessageBox.warning(self, "Código repetido",
                    f"Ya existe un elemento con código '{cod_new}'. Elige otro.")
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
                self.cv_radius_warn.setText(
                    f"⚠ Alcanzaste el máximo permitido: {r_max:.2f} ft. "
                    f"No se puede subir más porque los tramos rectos adyacentes "
                    f"no dan espacio para una tangente mayor.")
                self.cv_radius_warn.setStyleSheet("color:#d33; font-weight:bold; font-size:14px;")
            else:
                self.cv_radius_warn.setText(f"Máximo permitido: {r_max:.2f} ft.")
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
                self.gprop_cl.setTitle("Propiedades del centerline — selecciona uno de la lista")
                self.cl_len_lbl.setText("—")
                return
            c = self.ref_centerlines[self.sel_cl]
            self.gprop_cl.setTitle("Propiedades del centerline")
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
                QtWidgets.QMessageBox.warning(self, "Código repetido",
                    f"Ya existe un centerline con código '{cod_new}'. Elige otro.")
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
            item.setText(f"{c.get('cod', '?')}  ·  {len(c.get('pts') or [])} vértices")
            item.setIcon(_icon("mdi:vector-line", color="#22c55e"))

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
            QtWidgets.QMessageBox.warning(self, "Falta un componente",
                "La georreferenciación necesita matplotlib, pyproj y scikit-image.\n\n"
                "Instálalos con tu Python 3.12:\n"
                r"  C:\Users\Deyvy\AppData\Local\Programs\Python\Python312\python.exe -m pip install "
                "matplotlib pyproj scikit-image" f"\n\nDetalle: {e}")
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

    # ── Bancoductos: lista/CRUD desde la pestaña "Bancoductos" del inventario ──
    def _refresh_db_list(self):
        """Refresca la pestaña "Bancoductos" con `Tubería · Nombre · Nº conductos`.
        La fila cuya `pipe_idx` coincide con la tubería seleccionada en el canvas
        se resalta en negrita (ancla visual: "el bancoducto de la tubería que
        estoy viendo")."""
        if not hasattr(self, "db_list"):
            return
        self.db_list.blockSignals(True)
        self.db_list.clear()
        dbs = getattr(self, "duct_banks", []) or []
        cur_pipe = getattr(self, "sel_pipe", -1)
        for db in dbs:
            # Tubería asignada
            pi = getattr(db, "pipe_idx", -1)
            if 0 <= pi < len(self.pipes):
                p = self.pipes[pi]
                pipe_lbl = f"#{pi+1} {p.get('layer', '?')}"
            else:
                pipe_lbl = _tr("(sin asignar)")
            nm = db.name or _tr("(sin nombre)")
            nc = len(db.conduits)
            unit_c = _tr("conducto(s)")
            txt = f"{pipe_lbl}  ·  {nm}  ·  {nc} {unit_c}"
            it = QtWidgets.QListWidgetItem(_icon("mdi:grid"), txt)
            it.setToolTip(f"{_tr('Bancoducto')} «{nm}»\n"
                          f"{_tr('Envolvente')}: {db.width_in:g}\" × {db.height_in:g}\"\n"
                          f"{_tr('Conductos')}: {nc}\n"
                          f"{_tr('Tubería')}: {pipe_lbl}\n\n"
                          f"{_tr('Doble-click para editar.')}")
            if pi == cur_pipe and cur_pipe >= 0:
                # Resaltar la fila del bancoducto asignado a la tubería
                # actualmente seleccionada. No cambiamos el color del texto (en
                # dark, un accent azul sobre fondo negro queda ilegible), sino
                # que aplicamos negrita + un fondo tinte del accent — se lee en
                # ambos temas y no depende de contraste marginal.
                f = it.font(); f.setBold(True); it.setFont(f)
                t = _theme.tokens()
                # Fondo tenue del accent (~15% alpha) — legible sobre bg claro y
                # oscuro sin cambiar el color del texto.
                bg = QtGui.QColor(t.accent); bg.setAlpha(45)
                it.setBackground(bg)
            self.db_list.addItem(it)
        # Estado vacío: mensaje placeholder cuando no hay filas.
        if not dbs:
            hint = QtWidgets.QListWidgetItem(
                _tr("Aún no hay bancoductos.\n"
                    "Crea uno con «+ Nuevo» arriba, o click derecho en una tubería."))
            hint.setFlags(QtCore.Qt.NoItemFlags)   # no seleccionable
            hint.setForeground(QtGui.QColor(_theme.tokens().text_muted))
            self.db_list.addItem(hint)
        # Restaurar selección si sigue siendo válida.
        if 0 <= self.sel_db < len(dbs):
            self.db_list.setCurrentRow(self.sel_db)
        self.db_list.blockSignals(False)

    def _sel_db(self, row):
        if 0 <= row < len(getattr(self, "duct_banks", [])):
            self.sel_db = row
        else:
            self.sel_db = -1

    def _db_new(self):
        """Crear un bancoducto nuevo desde cero (sin tubería preasignada)."""
        self._open_duct_bank_designer(initial=None)

    def _db_new_for_pipe(self, pipe_idx):
        """Crear un bancoducto ya asignado a esta tubería."""
        from duct_bank import DuctBank
        seed = DuctBank(name="", pipe_idx=pipe_idx)
        self._open_duct_bank_designer(initial=seed)

    def _db_edit(self):
        """Editar el bancoducto seleccionado en la lista."""
        dbs = getattr(self, "duct_banks", []) or []
        if not (0 <= self.sel_db < len(dbs)):
            self._info(_tr("Selecciona un bancoducto primero."))
            return
        self._open_duct_bank_designer(initial=dbs[self.sel_db])

    def _db_edit_for_pipe(self, pipe_idx):
        """Editar el bancoducto asignado a esta tubería (desde menú contextual)."""
        db = self._duct_bank_for_pipe(pipe_idx)
        if db is None:
            return
        self._open_duct_bank_designer(initial=db)

    def _db_duplicate(self):
        """Duplica el bancoducto seleccionado (sin tubería asignada — el usuario
        decide a cuál asignarlo al editar)."""
        dbs = getattr(self, "duct_banks", []) or []
        if not (0 <= self.sel_db < len(dbs)):
            self._info(_tr("Selecciona un bancoducto para duplicar."))
            return
        src = dbs[self.sel_db]
        dup = src.copy()
        dup.name = f"{src.name or 'sin nombre'} (copia)"
        dup.pipe_idx = -1   # no heredamos asignación para evitar superposición
        self._push()
        self.duct_banks.append(dup)
        self.sel_db = len(self.duct_banks) - 1
        self._dirty = True
        if hasattr(self, "lbl_ductbank_count"):
            self.lbl_ductbank_count.setText(f"Duct banks guardados: {len(self.duct_banks)}")
        self._refresh_lists()
        self._info(f"Bancoducto duplicado como «{dup.name}».")

    # Sentinel para distinguir "sin argumento" (comportamiento heredado del
    # botón viejo del toolbar) de "explícitamente None" (nuevo desde cero).
    # Sin esto, `_open_duct_bank_designer(initial=None)` caía al fallback que
    # cargaba el último bancoducto — el usuario pedía Nuevo y se le abría uno ya
    # creado.
    _DB_DEFAULT = object()

    def _open_duct_bank_designer(self, initial=_DB_DEFAULT):
        # Delegador delgado: la UI del diseñador vive en duct_bank_dialog.py.
        # Al aceptar, guarda el diseño en self.duct_banks (colección del proyecto)
        # sobreescribiendo por identidad de objeto O por pipe_idx (para evitar
        # sólidos superpuestos cuando se rediseña el bancoducto de una tubería).
        #
        # `initial` explícito manda:
        #   - Un DuctBank existente → editarlo en-place
        #   - Un DuctBank nuevo con pipe_idx puesto → crear preasignado
        #   - None → crear desde cero (BOTÓN "Nuevo")
        # Sin `initial` (sentinel _DB_DEFAULT), cae al comportamiento heredado:
        # bancoducto de la pipe seleccionada, o el último — para no romper el
        # botón del toolbar antiguo.
        from duct_bank_dialog import open_designer
        if initial is Main._DB_DEFAULT:
            current = None
            if hasattr(self, "sel_pipe") and self.sel_pipe >= 0:
                current = self._duct_bank_for_pipe(self.sel_pipe)
            if current is None and getattr(self, "duct_banks", None):
                current = self.duct_banks[-1]
        else:
            current = initial   # None aquí SÍ significa "crear desde cero"
        result = open_designer(self, initial=current)
        if result is None:
            return
        if not getattr(self, "duct_banks", None):
            self.duct_banks = []
        # Reemplazo:
        #   - Si `current` es un DuctBank ya guardado, sustituimos ESE objeto
        #     (identidad) — así "Editar" nunca crea duplicados aunque el usuario
        #     cambie el nombre.
        #   - Sino, cae al match por nombre (nombres únicos como convención).
        replaced = False
        if current is not None:
            for i, d in enumerate(self.duct_banks):
                if d is current:
                    self.duct_banks[i] = result
                    replaced = True
                    break
        if not replaced:
            existing = next((i for i, d in enumerate(self.duct_banks)
                             if d.name and d.name == result.name), None)
            if existing is not None:
                self.duct_banks[existing] = result
            else:
                self.duct_banks.append(result)
        # Eliminar otros duct banks que apunten a la misma pipe (evita superposición).
        if result.pipe_idx >= 0:
            self.duct_banks = [
                d for d in self.duct_banks
                if d is result or getattr(d, "pipe_idx", -1) != result.pipe_idx
            ]
        self._dirty = True   # marca proyecto para pedir guardar
        pipe_info = ""
        if result.pipe_idx >= 0 and result.pipe_idx < len(self.pipes):
            p = self.pipes[result.pipe_idx]
            pipe_info = f" → asignado a #{result.pipe_idx+1} {p.get('layer','?')}"
        if hasattr(self, "lbl_ductbank_count"):
            self.lbl_ductbank_count.setText(
                f"Duct banks: {len(self.duct_banks)}{pipe_info}")
        # Deja seleccionado el bancoducto que se acaba de editar/crear en la lista.
        try:
            self.sel_db = self.duct_banks.index(result)
        except ValueError:
            self.sel_db = -1
        self._refresh_lists()
        self._info(f"Duct bank '{result.name or 'sin nombre'}' guardado{pipe_info}.")

    # ─────────────────────────── drag & drop ───────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls(): self.open_path(u.toLocalFile()); break


def main():
    app = QtWidgets.QApplication(sys.argv)
    app._no_wheel_filter = _NoWheelFilter(app)
    app.installEventFilter(app._no_wheel_filter)
    # Idioma preferido del usuario. Debe cargarse ANTES de construir Main() para
    # que los textos ya salgan traducidos desde el primer render.
    import i18n as _i18n
    _i18n.load_lang()
    # Tema visual global (claro/oscuro). La preferencia se persiste en QSettings
    # y se puede alternar desde el menú "Ver" en tiempo real. Todo el CSS antes
    # hardcodeado ahora vive en app/theme.py, parametrizado por tokens de color.
    _theme.apply_theme(app, _theme.load_preference("dark"))
    win = Main(); win.show()
    if len(sys.argv) > 1:
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
