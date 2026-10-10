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
from exportar import dxf_export
from geo import georef as georef_mod
from geometry import qimage_to_gray
from nucleo import model_ops
# Clases de UI extraídas a módulos propios (mismo comportamiento, ver plan de
# arquitectura). El lienzo, los widgets reutilizables y el worker de fondo.
from ui.comun.canvas import Canvas
from ui.comun.widgets import InlineEdit, _SegInvSpinBox, _NoWheelFilter
from ui.comun import busy as _busy_mod
from ui.comun import fondo_pdf
from ui.comun.workers import PipelineWorker, RecognitionWorker, OrganizedRecognitionWorker
from ui.dialogos import dialogs
from ui.asistente import recognition_dialog
from ui.asistente import sheet_layout_dialog
from ui.asistente import organized_layer_dialog
from ui.asistente import organized_recognition_dialog
from hoja.organized_layers import selected_sheets
from hoja.sheet_layout import normalize as normalize_sheet_layout, normalize_rotations
from hoja.sheet_crops import normalize as normalize_sheet_crops
from ui.asistente import layer_dialog
from reconocimiento import recognition as _recognition
from reconocimiento import recognition_cache
from ui.ventana import respaldo_editor
from hoja import composite as composite_mod
from ui.asistente import composite_dialog
import project_io
from nucleo import model_ops
from nucleo import quiebres_curvas
from ui.comun.responsive import WrapButton, WrapCheckBox, ResponsiveGroupBox, GridAdaptable  # noqa: E402
from ui.comun import side_panels  # noqa: E402
from ui.ventana import autoguardado  # noqa: E402
from nucleo import normas_catalogo, normas_validar
from nucleo.model import (VERSION, TIPOS, ACI_RGB, LEADER_TEXT_FT, LEADER_ORIENT,
                   Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE, GRAVITY_LAYERS,
                   TAB_PIPE, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ, TAB_CURVE, TAB_CL,
                   TAB_DB,
                   WORK_UNITS, DEFAULT_WORK_UNIT, CHANGELOG,
                   PIPE_DIAMETERS_IN, PIPE_MATERIALS, DEFAULT_PIPE_MATERIAL, NETWORK_KIND)

# Constantes y helpers de UI compartidos (antes definidos aquí) → ui_common.py.
from ui.comun.ui_common import (DOWNLOADS, btn_on_style, btn_off_style, aci_qcolor, layer_qcolor,
                       _extract_diam_from_size, swatch_icon, tooltip_bloque)
from ui.comun import theme as _theme
from traduccion import i18n as _i18n
from traduccion.i18n import t as _tr, bind as _bind, bind_item as _bind_item, N_
from ui.comun.icons import icon as _icon

# Cuánto más cerca tiene que estar el tramo que un vértice para ganarle en el
# snap suave (ver `_pipe_soft_snap`). Junto a un vértice, la perpendicular a un
# segmento oblicuo cae un pelo más cerca; sin este margen el punto se deslizaba
# sobre el tramo y las utilidades no empalmaban en el vértice.
PRIORIDAD_VERTICE = 0.55


# Métodos de Main repartidos por tema en clases mezcla (movidos tal cual).
from ui.ventana.ventana_menu import MenuMixin
from ui.ventana.ventana_panel_izq import PanelIzquierdoMixin
from ui.ventana.ventana_panel_der import PanelDerechoMixin
from ui.ventana.ventana_modos import ModosMixin
from ui.ventana.ventana_clics import ClicsMixin
from ui.ventana.ventana_utilidades import UtilidadesMixin
from ui.ventana.ventana_catalogo import CatalogoMixin
from ui.ventana.ventana_seleccion import SeleccionMixin
from ui.ventana.ventana_listas import ListasMixin
from ui.ventana.ventana_marcas import MarcasMixin
from ui.ventana.ventana_dibujo import DibujoMixin
from ui.ventana.ventana_conflictos import ConflictosMixin
from ui.ventana.ventana_coords import CoordsMixin
from ui.ventana.ventana_buzones import BuzonesMixin
from ui.ventana.ventana_mover import MoverPrecisoMixin
from ui.ventana.ventana_curvas import CurvasMixin
from ui.ventana.ventana_herramientas import HerramientasMixin
from ui.ventana.ventana_bancoductos import BancoductosMixin
from ui.ventana.ventana_bloque import EdicionBloqueMixin
from ui.ventana.ventana_vista3d import Vista3DMixin


class Main(MenuMixin, PanelIzquierdoMixin, PanelDerechoMixin, ModosMixin, ClicsMixin, UtilidadesMixin, CatalogoMixin, SeleccionMixin, ListasMixin, MarcasMixin, DibujoMixin, ConflictosMixin, CoordsMixin, BuzonesMixin, MoverPrecisoMixin, CurvasMixin, HerramientasMixin, BancoductosMixin, EdicionBloqueMixin, Vista3DMixin,
           QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._base_title = f"Asistente C3D  (v{VERSION})"
        self.setWindowTitle(self._base_title); self.resize(1480, 940)
        self.setAcceptDrops(True)
        self.canvas = Canvas(self); self.canvas.clicked.connect(self.on_click)
        self.canvas.dbl.connect(self.on_dblclick); self.setCentralWidget(self.canvas)
        # Hoja enorme (fondo_pdf): recorte nítido de la parte visible al acercarse.
        self.canvas.nitidez = fondo_pdf.Nitidez(self.canvas, lambda: self.zoom, self._pagina_fondo)
        self.zoom = 3.5; self.scale = 20 / 72.0; self.rot = 0; self.W = 0; self.H = 0
        self.derot = fitz.Matrix(1, 0, 0, 1, 0, 0); self.gray = None; self.page_idx = 0; self.pageH_px = 0
        self.hidden_ocgs = []   # capas OCG ocultas en el paso «Capas de la hoja» (por PDF abierto)
        self.hidden_ocgs_by_source = {}  # selección de capas por PDF de la organización
        self._layer_roles_by_utility = {}  # roles OCG manuales separados por utilidad
        self._letters_off = set()  # capas que NO se reconocen por las letras de su línea (paso «Capas»)
        self._legend_cache = {}    # leyenda del PDF ya leída (paso «Capas»), por PDF de origen
        self._recognition_utilities = _recognition.DEFAULT_UTILITIES
        self._join_routes = True   # unir tramos de la misma capa en rutas (desactivable en el preview)
        self._recog_ready = False  # True cuando el asistente ya reconoció una hoja de este PDF (◀ ▶ vuelven a reconocer)
        # Reconocimientos ya hechos, por todo lo que los decide (`recognition_cache`):
        # volver a componer/capas sin cambios abre la vista previa sin reconocer otra vez.
        self._recog_cache = recognition_cache.RecognitionCache()
        self._src_fingerprints = recognition_cache.SourceFingerprints()
        self._recog_pending_key = None   # clave del reconocimiento que corre en el hilo
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
        # Editor tal como estaba al abrir el asistente desde Herramientas (respaldo_editor):
        # «Cancelar» en cualquier paso lo repone; importar lo suelta.
        self._respaldo = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.leader_hpx = 40
        # Proyecto sobre hoja en blanco (sin PDF de fondo). `paper` guarda el
        # formato elegido para reponerlo al abrir el .digproj.
        self.blank_canvas = False
        self.paper = None

        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.ref_centerlines = []; self._cl_pts = []
        self.duct_banks = []   # colección del proyecto — ver duct_bank.py
        self.cross_connections = []   # conexiones aprobadas en cruces físicos
        # Normativas de diseño en tablas: catálogo GLOBAL (el Excel del usuario, ver
        # normas_catalogo.py) y los avisos del proyecto (normas_validar, en cada redibujo).
        self.normas_cat = normas_catalogo.cargar()
        self._normas_avisos = []; self._normas_dlg = None; self._tabla_dlg = None
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
        from catalogo import civil_catalog as _cc
        _vs = _cc.installed_versions()
        self.civil_year = _vs[-1] if _vs else None
        self._build_ui(); self._apply_style(); self._shortcuts(); self._update_ui()
        # Re-aplica estilos custom con los tokens del tema activo, y se reconecta
        # al bus para reaccionar cuando el usuario alterne claro↔oscuro.
        self._apply_theme_custom_styles()
        _theme.THEME_BUS.changed.connect(self._apply_theme_custom_styles)
        # Copias automáticas del proyecto (autoguardado.py). Arrancan solo desde main()
        # con iniciar_autoguardado(): las pruebas que crean la ventana no escriben nada.
        self.autoguardado = autoguardado.Autoguardado(self)

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
        self._load_sheet_busy(idx)
        if self.composite is not None and self.composite.is_single_full_page():
            self.composite.pieces[0].page = idx
        if self._recog_ready and self.pdf_path:
            self._start_recognition(idx)

    # ─────────────────────────── undo/redo ───────────────────────────
    def _snap_state(self):
        return copy.deepcopy(dict(cur_pts=self.cur_pts, pipes=self.pipes, leaders=self.leaders,
                                  text_marks=self.text_marks, erase_regions=self.erase_regions,
                                  structures=self.structures,
                                  duct_banks=getattr(self, "duct_banks", []) or [],
                                  # apuntan a utilidades por índice: borrar/unir los corre
                                  cross_connections=getattr(self, "cross_connections", []) or []))

    def _push(self):
        self._undo.append(self._snap_state()); self._redo.clear(); self._dirty = True
        if len(self._undo) > 400: self._undo.pop(0)

    def _restore(self, s):
        self.cur_pts, self.pipes = s["cur_pts"], s["pipes"]
        self.leaders, self.text_marks = s["leaders"], s["text_marks"]
        self.erase_regions = s.get("erase_regions", [])
        self.structures = s.get("structures", [])
        if "cross_connections" in s:
            self.cross_connections = s["cross_connections"]
        if "duct_banks" in s:
            self.duct_banks = s["duct_banks"]
            if not (0 <= getattr(self, "sel_db", -1) < len(self.duct_banks)):
                self.sel_db = -1
        self._refresh_lists(); self._update_ui(); self._redraw()

    def undo(self):
        if self._undo: self._redo.append(self._snap_state()); self._restore(self._undo.pop()); self._info(_tr("Deshacer"))
        self._update_undo_tooltips()

    def redo(self):
        if self._redo: self._undo.append(self._snap_state()); self._restore(self._redo.pop()); self._info(_tr("Rehacer"))
        self._update_undo_tooltips()

    def _update_undo_tooltips(self):
        u, r = len(self._undo), len(self._redo)
        _bind(self._act_undo, "setToolTip", "Deshacer (Ctrl+Z) — {n} paso" if u == 1
              else "Deshacer (Ctrl+Z) — {n} pasos", fmt={"n": u})
        _bind(self._act_redo, "setToolTip", "Rehacer (Ctrl+Shift+Z) — {n} paso" if r == 1
              else "Rehacer (Ctrl+Shift+Z) — {n} pasos", fmt={"n": r})

    # ─────────────────────────── abrir ───────────────────────────
    def _busy(self, m="Procesando…", detail=""):
        """Capa «Cargando…» sobre la ventana (busy.py): se ve que la app trabaja."""
        self._info(m); _busy_mod.overlay_for(self).begin(m, detail)
    def _unbusy(self): _busy_mod.overlay_for(self).end()

    def open_path(self, path):
        low = path.lower()
        if low.endswith(".pdf"): self._open_pdf_path(path)
        elif low.endswith(".digproj"): self._open_project_path(path)

    def open_pdf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Abrir PDF"), DOWNLOADS, "PDF (*.pdf)")
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
            self._letters_off = set()
            self._recognition_utilities = _recognition.DEFAULT_UTILITIES
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

    def new_blank_canvas(self):
        """Crea un proyecto nuevo sobre una hoja EN BLANCO, sin PDF de fondo.

        Todo el resto de la app (dibujo, cotas, exportación a DXF) funciona
        igual: lo que necesita no es el PDF en sí, sino la imagen de fondo del
        lienzo y la tupla de transformación (scale, zoom, rot, W, H, derot).
        Aquí se construyen a mano a partir de la hoja y la escala que elige el
        usuario, en vez de leerlas de una página de fitz.
        """
        if not self._confirm_discard(): return
        from ui.dialogos import blank_canvas_dialog
        cfg = blank_canvas_dialog.choose_canvas(
            self, escala_actual=float(self.scale) * 72.0 if self.scale else 20.0)
        if not cfg: return

        self._busy(_tr("Creando lienzo…"))
        try:
            if self.doc:
                self.doc.close()
            self._cleanup_tmp_pdf()
            # Sin PDF: doc/pdf_path quedan en None. `_open_project_path` ya
            # contempla ese estado, así que el .digproj funciona igual.
            self.doc = None
            self.pdf_path = None
            self.project_path = None
            self.work_pdf_path = None
            self.src_pdfs = []
            self.composite = None
            self._scale_override = None
            self.hidden_ocgs = []
            self.hidden_ocgs_by_source = {}
            self._letters_off = set()
            self._layer_roles = None
            self._recog_ready = False
            self.sheet_layout = None
            self.sheet_rotations = {}
            self.sheet_crops = {}
            self.sheet_sources = []
            self.sheet_external_pdfs = []
            self.blank_canvas = True
            self.paper = dict(cfg)
            self._load_blank_page(cfg)
            self._update_title()
        finally:
            self._unbusy()
        self._info(_tr("Lienzo {n} · 1\"={e:g}'").format(
            n=_tr(cfg["name"]), e=cfg["ft_per_inch"]))

    def _load_blank_page(self, cfg):
        """Monta el lienzo en blanco: equivalente a `_load_page` pero sin fitz.

        Con rot=0 y derot identidad, `geometry.to_cad` se reduce a
            X_cad = (x_px / zoom) * scale
            Y_cad = (H - y_px / zoom) * scale
        así que basta con dar W/H en PUNTOS de hoja y la escala en pies/punto
        para que el DXF salga con las dimensiones correctas.
        """
        self.page_idx = 0
        self.scale = float(cfg["scale_ft_per_pt"])
        self.rot = 0
        self.W = float(cfg["w_pt"])
        self.H = float(cfg["h_pt"])
        self.derot = fitz.Matrix(1, 0, 0, 1, 0, 0)

        w_px = max(1, int(round(self.W * self.zoom)))
        h_px = max(1, int(round(self.H * self.zoom)))
        self.pageH_px = h_px
        self.leader_hpx = max(14.0, min(
            LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))

        qimg = QtGui.QImage(w_px, h_px, QtGui.QImage.Format_RGB888)
        qimg.fill(QtGui.QColor(255, 255, 255))
        # `gray` lo usa el snap a tinta del plano; en blanco no hay nada a que
        # engancharse, y `geometry.snap_point` ya tolera None devolviendo el
        # punto tal cual.
        self.gray = None

        self._overlay = []
        self.canvas.set_image(qimg)
        self._reset_model()
        self._update_page_label()
        self._refresh_scale_label()

    def _run_recognition_wizard(self):
        """Elegir tipo/hoja, utilidad/capas, reconocer y mostrar preview. Sin importar pipes.

        Si detect.py clasifica claro (vector o raster con imagen dominante), se omite
        el diálogo de tipo; solo se pregunta en casos ambiguos.
        """
        if not self.doc or not self.pdf_path:
            return

        _load = self._load_sheet_busy

        def _go_manual(msg):
            self._info(msg)
            if not self._wizard_sheet_flow(0, manual=True):
                _load(0)

        def _go_plotted():
            if not self._wizard_sheet_flow(0):
                _load(0)

        # Clasificación automática (página 0) — misma heurística que digitize.
        import detect as _detect
        with _busy_mod.busy(self, _tr("Analizando el PDF…")):
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

    def _wizard_sheet_flow(self, start_idx, start_step=0, manual=False):
        """Asistente de PDF vectorial: 1 Componer hoja → 2 Capas de la hoja →
        3 reconocer (vista previa). Lo usan la apertura del PDF, Ver → Componer
        hoja y la barra de pasos del preview. `start_step`=1 empieza en «Capas»
        con la hoja ya compuesta. «◀ Componer hoja» en Capas vuelve al paso 1
        (pedido del usuario: poder volver atrás en cada paso).
        Devuelve False si se cancela el compositor. Al cancelar las capas, la
        hoja queda cargada sin reconocer — o, si se entró desde el editor (hay
        `_respaldo`), el editor vuelve a como estaba."""
        step = start_step
        page_idx = start_idx
        while True:
            if step == 0:
                res = composite_dialog.compose_sheet(
                    self, self.src_pdfs, self.composite, self.hidden_ocgs_by_source, current_page=page_idx,
                    manual=manual)
                if res is None:
                    return False
                comp, sources, hidden_by_source = res
                if (comp.manual and getattr(self, "_respaldo", None) is not None
                        and self._misma_composicion(comp, sources, hidden_by_source)):
                    # Escaneo: «Continuar» sin cambiar la hoja no borra lo dibujado.
                    self._reponer_respaldo(_tr("La hoja compuesta no cambió — el editor queda como estaba."))
                    return True
                antes = (self.src_pdfs, self.composite, self.hidden_ocgs_by_source)
                self.src_pdfs = sources
                self.composite = comp
                self.hidden_ocgs_by_source = {k: list(v) for k, v in hidden_by_source.items()}
                self._recog_ready = False
                try:
                    self._apply_composite()
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(self, _tr("Componer hoja"),
                        _tr("No se pudo armar la hoja compuesta:\n\n{e}").format(e=exc))
                    self._volver_a_la_hoja(antes)
                    return False
                page_idx = self.page_idx
                if comp.manual:
                    if getattr(self, "_respaldo", None) is not None:
                        self._soltar_respaldo()      # hoja nueva en el editor: la anterior ya no vuelve
                    self._dirty = True
                    self._info(_tr("Hoja compuesta importada al editor. Dibuja las utilidades a mano."))
                    return True
            # Paso «Capas de la hoja»: el usuario decide qué capas OCG ver ANTES
            # de dibujar. Deja la visibilidad aplicada en self.doc, así _load_page
            # ya renderiza sin las ocultas.
            chosen = layer_dialog.choose_sheet_layers(self, self.doc, page_idx,
                                                      layout=getattr(self, "_composite_layout", None),
                                                      recognition_utilities=self._recognition_utilities,
                                                      can_go_back=bool(self.src_pdfs),
                                                      letters_off=self._letters_off,
                                                      legend_sources=self._legend_sources(),
                                                      legend_cache=self._legend_cache)
            if chosen == layer_dialog.LAYERS_BACK:
                step = 0
                continue
            break
        if chosen is None:
            if self._reponer_respaldo(_tr("Reconocimiento cancelado — el editor queda como estaba.")):
                return True
            self._load_sheet_busy(page_idx)
            self._dirty = True
            self._info(_tr("Reconocimiento cancelado — hoja cargada con las capas elegidas."))
            return True
        hidden, page_idx, self._recognition_utilities, letters_off = chosen
        self._letters_off = set(letters_off)
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

    def _volver_a_la_hoja(self, antes):
        """No se pudo armar la hoja compuesta: `_apply_composite` ya cerró el PDF de la
        hoja anterior. Con respaldo (editor con trabajo) lo repone quien llamó
        (`_cancelar_asistente`); sin él se vuelve a cargar la hoja anterior para que el
        editor no quede sin PDF (antes quedaba vacío, «Página: /—»)."""
        if getattr(self, "_respaldo", None) is not None:
            return
        self.src_pdfs, self.composite, self.hidden_ocgs_by_source = antes
        if not self.src_pdfs:
            return
        try:
            self._apply_composite()
        except Exception:
            pass

    def _apply_composite(self):
        """Deja en `self.doc` la hoja de trabajo según `self.composite`:
        una sola pieza = hoja entera → el PDF origen tal cual (◀ ▶ siguen
        sirviendo); si no, se materializa la hoja compuesta como PDF temporal
        (`composite.build_document`) con las capas de cada origen ya apagadas."""
        comp = self.composite
        from hoja import pdf_layers as _pdf_layers
        if self.doc:
            if not respaldo_editor.lo_guarda(self._respaldo, doc=self.doc):   # «Cancelar» lo repone
                self.doc.close()
            self.doc = None
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
            self._scale_override = comp.target_scale() if comp and comp.manual else None
            self.page_idx = piece.page if piece else 0
        else:
            with _busy_mod.busy(self, _tr("Armando la hoja compuesta…"),
                                _tr("{n} piezas · vectores, capas y textos intactos").format(
                                    n=len(comp.pieces))):
                self._build_composite_doc(comp, _pdf_layers)
        self._load_sheet_busy(self.page_idx)

    def _build_composite_doc(self, comp, _pdf_layers):
        """Materializa la hoja compuesta como PDF temporal y la deja en `self.doc`."""
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

    def _write_tmp_composite(self, data, suffix=""):
        import tempfile
        fd, path = tempfile.mkstemp(prefix="pdfcad_hoja", suffix=f"{suffix}.pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        self._tmp_composite = path
        return path

    def _cleanup_tmp_composite(self):
        tmp = getattr(self, "_tmp_composite", None)
        if tmp and os.path.isfile(tmp) and not respaldo_editor.lo_guarda(
                getattr(self, "_respaldo", None), tmp=tmp):
            try: os.remove(tmp)
            except Exception: pass
        self._tmp_composite = None

    def _sync_hidden_to_sources(self, hidden):
        """Las capas apagadas en la hoja de trabajo se reflejan por nombre en
        cada PDF de origen, así al volver al compositor se conservan."""
        from hoja import pdf_layers as _pdf_layers
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
        self._tomar_respaldo()
        if not self._wizard_sheet_flow(self.page_idx,
                manual=bool(self.composite and self.composite.manual)):
            self._cancelar_asistente(_tr("Composición cancelada — el editor queda como estaba."),
                                     _tr("Composición cancelada — se mantiene la hoja actual."))

    def compose_scan_sheet(self):
        """Explicit manual composition for mixed PDFs or ambiguous detection."""
        if not self.doc or not self.src_pdfs:
            QtWidgets.QMessageBox.information(self, _tr("Componer hoja de trabajo"),
                _tr("Abre un PDF para componer su hoja de trabajo."))
            return
        if not self._confirm_discard():
            return
        self._tomar_respaldo()
        if not self._wizard_sheet_flow(self.page_idx, manual=True):
            self._cancelar_asistente(_tr("Composición cancelada — el editor queda como estaba."),
                                     _tr("Composición cancelada — se mantiene la hoja actual."))

    # ── «Cancelar» en el asistente abierto desde el editor (respaldo_editor) ──
    def _tomar_respaldo(self):
        """Guarda el editor tal como está: si el asistente termina sin importar, vuelve así.
        Sin trabajo que perder no hace falta (cancelar deja la hoja nueva, como siempre)."""
        self._soltar_respaldo()
        if self.canvas.pixmap_item is not None and respaldo_editor.hay_trabajo(self):
            self._respaldo = respaldo_editor.tomar(self)

    def _soltar_respaldo(self):
        """Hoja nueva en el editor (importar): el respaldo ya no vuelve."""
        r, self._respaldo = self._respaldo, None
        respaldo_editor.soltar(self, r)

    def _reponer_respaldo(self, msg):
        """Editor a como estaba al abrir el asistente. False si no había respaldo."""
        r, self._respaldo = self._respaldo, None
        if r is None:
            return False
        respaldo_editor.reponer(self, r)
        self._info(msg)
        return True

    def _cancelar_asistente(self, msg, msg_sin_respaldo=None):
        """Fin del asistente SIN importar: con respaldo el editor vuelve a como estaba
        (`msg`); sin él (asistente al abrir el PDF) queda lo que hay (`msg_sin_respaldo`)."""
        if not self._reponer_respaldo(msg) and msg_sin_respaldo:
            self._info(msg_sin_respaldo)

    def _misma_composicion(self, comp, sources, hidden_by_source):
        """¿El compositor devolvió la misma hoja de trabajo que hay en el editor?"""
        sig = recognition_cache.composition_signature
        hidden = lambda h: {str(k): set(v) for k, v in (h or {}).items() if v}
        return (sig(comp) == sig(self.composite)
                and self._src_fingerprints(sources) == self._src_fingerprints(self.src_pdfs)
                and hidden(hidden_by_source) == hidden(self.hidden_ocgs_by_source))

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
        utility_text = _recognition.utilities_label(self._recognition_utilities)
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
        fondo = fondo_pdf.render_pix(self.doc[self.page_idx], self.zoom)
        pix = fondo.pix
        qimg = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                            pix.stride, QtGui.QImage.Format_RGB888).copy()
        self.canvas.cambiar_imagen(qimg, fondo.escala)
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

    def _legend_sources(self):
        """PDFs cuya LEYENDA muestra el paso «Capas de la hoja»: los de origen de la hoja
        (también los de una hoja compuesta: la de trabajo es un PDF temporal sin leyenda)."""
        if self.src_pdfs:
            return [{"name": e.get("name", ""), "data": e.get("data"), "path": e.get("path")}
                    for e in self.src_pdfs]
        if self.pdf_path:
            return [{"name": os.path.basename(self.pdf_path), "path": self.pdf_path}]
        return []

    def _adjust_layer_roles(self, page_idx):
        """«Ajustar capas…» del preview: elegir a mano qué capas visibles son
        líneas / bóvedas y volver a reconocer la hoja con esos roles. Cancelar
        vuelve a la MISMA vista previa (sin cambios, sale de `recognition_cache`)."""
        from hoja import pdf_layers as _pdf_layers
        utilities = tuple(self._recognition_utilities)
        if len(utilities) > 1:
            labels = [_recognition.utility_label(key) for key in utilities]
            label, ok = QtWidgets.QInputDialog.getItem(
                self, _tr("Ajustar capas"),
                _tr("¿Qué utilidad quieres ajustar?"), labels, 0, False)
            if not ok:
                self._start_recognition(page_idx)
                return
            utility = utilities[labels.index(label)]
        else:
            utility = utilities[0]
        all_layers = _pdf_layers.without_letters(_pdf_layers.page_layers(self.doc, page_idx), self._letters_off)
        visible = [L for L in all_layers if L["name"] not in set(self.hidden_ocgs)]
        roles = recognition_dialog.choose_layer_roles(
            self, visible, utility=utility)
        if roles is not None:
            self._layer_roles_by_utility[utility] = roles
        self._start_recognition(page_idx)

    def _start_recognition(self, page_idx):
        """Lanza el reconocimiento de la hoja `page_idx` en segundo plano con las
        capas ocultas (`self.hidden_ocgs`) y roles separados por utilidad
        (sin ajuste manual = automático por nombre). Al terminar, `_recognition_done` muestra
        la vista previa. Lo usan el asistente y el cambio de hoja del editor.
        Si nada cambió desde un reconocimiento anterior (misma composición, hoja,
        capas, utilidades…), reutiliza ese resultado: no vuelve a leer el PDF."""
        key = self._recognition_key(page_idx)
        cached = self._recog_cache.get(key)
        if cached is not None:
            self._end_recognition_busy()
            self._recog_pending_key = None
            recognition_cache.set_join_routes(cached, self._join_routes)
            self._info(_tr("Sin cambios en la hoja ni en sus capas: se usa el reconocimiento anterior."))
            # como el hilo: la vista previa se abre al volver al bucle de eventos
            QtCore.QTimer.singleShot(0, lambda: self._recognition_done(cached, ""))
            return
        self._recog_pending_key = key
        utility_text = _recognition.utilities_label(self._recognition_utilities)
        # Capa «Cargando…» sobre la ventana (la misma de todo el asistente): el
        # trabajo va en otro hilo, así que el indicador gira mientras tanto.
        self._end_recognition_busy()
        self._recog_busy = _busy_mod.overlay_for(self)
        self._recog_busy.begin(_tr("Reconociendo {u}…").format(u=utility_text),
                               _tr("Hoja {n} · leyendo las líneas y estructuras de cada capa").format(
                                   n=page_idx + 1))
        self._recog_worker = RecognitionWorker(
            self.work_pdf_path or self.pdf_path, page_idx, zoom=self.zoom,
            utilities=self._recognition_utilities,
            hidden_ocgs=self.hidden_ocgs,
            roles_by_utility=self._layer_roles_by_utility,
            letters_off=self._letters_off,
            join_routes=self._join_routes, scale_ft_per_pt=self._scale_override)
        self._recog_worker.done.connect(self._recognition_done)
        self._recog_worker.progress.connect(self._recognition_progress)
        self._recog_worker.start()

    def _recognition_key(self, page_idx):
        """Clave de `recognition_cache` con el estado actual del asistente."""
        document = (self._src_fingerprints(self.src_pdfs) if self.src_pdfs
                    else ("path", self.work_pdf_path or self.pdf_path))
        return recognition_cache.recognition_key(
            document, self.composite, page_idx, hidden_ocgs=self.hidden_ocgs,
            utilities=self._recognition_utilities, roles_by_utility=self._layer_roles_by_utility,
            letters_off=self._letters_off, scale_ft_per_pt=self._scale_override, zoom=self.zoom)

    def _recognition_progress(self, i, n, utility):
        ov = getattr(self, "_recog_busy", None)
        if ov is not None and n > 1:
            ov.step(detail=_tr("Hoja {p} · {u} ({i} de {n})").format(
                p=self._recog_worker.page_index + 1, u=_tr(_recognition.utility_label(utility)),
                i=i + 1, n=n),
                done=i, total=n, pump=False)

    def _end_recognition_busy(self):
        ov = getattr(self, "_recog_busy", None)
        self._recog_busy = None
        if ov is not None:
            ov.end()

    def _recognition_done(self, results, error):
        self._end_recognition_busy()
        key, self._recog_pending_key = self._recog_pending_key, None
        # Cualquier salida sin importar devuelve el editor a como estaba si el
        # asistente se abrió desde él (Herramientas → Componer hoja; respaldo_editor).
        cancelled = _tr("Reconocimiento cancelado — el editor queda como estaba.")
        if error:
            QtWidgets.QMessageBox.warning(
                self, _tr("Reconocimiento"),
                _tr("No se pudo reconocer la hoja:\n\n{e}").format(e=error))
            self._cancelar_asistente(cancelled)
            return
        if results is None:
            self._cancelar_asistente(cancelled)
            return
        if not isinstance(results, (list, tuple)):
            results = [results]
        results = [result for result in results if result is not None]
        if not results:
            self._cancelar_asistente(cancelled)
            return
        self._recog_cache.put(key, results)      # None (resultado reutilizado) no guarda nada
        qimg = None
        if self.canvas.pixmap_item is not None:
            qimg = self.canvas.pixmap_item.pixmap().toImage()
        if qimg is None or qimg.isNull():
            QtWidgets.QMessageBox.information(
                self, _tr("Reconocimiento"),
                _tr("Reconocimiento listo, pero no hay imagen de la hoja para la vista previa."))
            self._cancelar_asistente(cancelled)
            return
        extra = {}
        if self.canvas.fondo_escala < 1.0:       # hoja enorme a menos resolución (fondo_pdf)
            extra["fondo"] = {"escala": self.canvas.fondo_escala, "tam": self.canvas.tam_hoja(),
                              "zoom": self.zoom, "pagina": self._pagina_fondo}
        action = recognition_dialog.show_recognition_preview(
            self, qimg, results,
            page_count=self.doc.page_count if self.doc else None, **extra)
        del qimg                                 # copia de la hoja: no retenerla mientras se sigue
        self._join_routes = all(bool(getattr(result, "join_routes", True)) for result in results)
        page_index = results[0].page_index
        if action == recognition_dialog.PREVIEW_IMPORT:
            with _busy_mod.busy(self, _tr("Importando al editor…")):
                imported = self._import_recognized_pipes(results)
            if imported:
                self._soltar_respaldo()
            else:
                self._cancelar_asistente(
                    _tr("No hay tramos reconocidos para importar — el editor queda como estaba."))
        elif action == recognition_dialog.PREVIEW_CHANGE_SHEET:
            # Flujo pedido: lista de hojas → capas → preview de la hoja nueva.
            if not self._wizard_sheet_flow(page_index):
                self._cancelar_asistente(
                    _tr("Composición cancelada — el editor queda como estaba."),
                    _tr("Cambio de hoja cancelado — se mantiene la hoja {n}.").format(n=page_index + 1))
        elif action == recognition_dialog.PREVIEW_SHEET_LAYERS:
            # Paso «2 Capas de la hoja» de la cabecera: volver (y desde ahí, si quiere, al 1).
            if not self._wizard_sheet_flow(page_index, start_step=1):
                self._cancelar_asistente(
                    _tr("Composición cancelada — el editor queda como estaba."),
                    _tr("Cambio de hoja cancelado — se mantiene la hoja {n}.").format(n=page_index + 1))
        elif action == recognition_dialog.PREVIEW_ADJUST_LAYERS:
            self._adjust_layer_roles(page_index)
        else:
            self._cancelar_asistente(cancelled, _tr("Reconocimiento cancelado — editor vacío."))

    def _xdata_origin(self, page_index: int):
        """Función (puntos del lienzo) → «PDF · Hoja N» de donde salió el objeto,
        para los datos extendidos. En una hoja compuesta, la pieza bajo su
        punto medio (`_composite_layout`, en pt de la hoja compuesta)."""
        from nucleo import xdata
        names = [e.get("name", "") for e in (self.src_pdfs or [])]
        comp = self.composite
        if comp is not None and comp.pieces and getattr(self, "_composite_layout", None):
            single = len({p.source for p in comp.pieces}) == 1
            name0 = names[comp.pieces[0].source] if comp.pieces[0].source < len(names) else ""
            pieces = [(rect, f"{name0} · {label}" if single and name0 else label)
                      for rect, label in self._composite_layout]
            z = self.zoom or 1.0
            return lambda pts: xdata.origin_label([(x / z, y / z) for x, y in pts], pieces,
                                                  "Hoja compuesta")
        src = comp.pieces[0].source if comp is not None and comp.pieces else 0
        name = names[src] if src < len(names) and names[src] else (
            os.path.basename(self.pdf_path) if self.pdf_path else "")
        # es un DATO del proyecto (va al DXF): fijo en español, no depende del idioma de la UI
        label = f"{name} · Hoja {page_index + 1}" if name else f"Hoja {page_index + 1}"
        return lambda pts: label

    def show_xdata(self):
        """«Ver datos extendidos» de la utilidad o estructura seleccionada."""
        from nucleo import xdata
        from ui.dialogos import xdata_dialog
        ti = self._current_tab()
        obj = title = None
        if ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            obj = self.pipes[self.sel_pipe]
            title = _tr("Utilidad #{n}").format(n=self.sel_pipe + 1)
        elif ti == TAB_BZ and 0 <= self.sel_bz < len(self.structures):
            obj = self.structures[self.sel_bz]
            title = obj.get("cod") or _tr("Estructura #{n}").format(n=self.sel_bz + 1)
        if obj is None:
            self._info(_tr("Selecciona una utilidad o una estructura para ver sus datos extendidos."))
            return
        user = xdata_dialog.edit_xdata(self, title, obj)
        if user is None or user == xdata.get(obj)[xdata.USER]:
            return
        self._push()
        xdata.set_user(obj, user)
        self._dirty = True

    def _import_recognized_pipes(self, results):
        """Añade centerlines reconocidas e inserta sus estructuras como nodos.
        Devuelve False si no había nada que importar."""
        from reconocimiento import recognition as rec
        if not isinstance(results, (list, tuple)):
            results = [results]
        batches = []
        for result in results:
            utility = getattr(result, "utility", None) or "ELECTRICO"
            pipes = rec.pipes_from_recognition(result, layer=utility, zoom=self.zoom,
                                               origin=self._xdata_origin(result.page_index))
            vaults = list(getattr(result, "vault_pts", None) or [])
            snapped, skipped = rec.inject_vault_vertices(pipes, vaults)
            result.vaults_snapped = snapped
            result.vaults_skipped = skipped
            # Toda bóveda que la vista previa muestra se importa (pedido del usuario
            # 2026-10-05), también sin línea y en las redes a PRESIÓN (agua/gas): sus
            # vértices siguen sin nodos, como en el dibujo manual; la bóveda entra como
            # caja suelta (en Civil 3D, un sólido aislado). Las líneas no cambian.
            has_importable_structure = any(
                vault.get("importable", False)
                for vault in (getattr(result, "vaults_geo", None) or []))
            if pipes or has_importable_structure:
                batches.append((result, utility, pipes, snapped, skipped))
        if not batches:
            self._info(_tr("No hay tramos reconocidos para importar."))
            return False
        self._push()
        n_prev = len(self.pipes)
        for _result, _utility, pipes, _snapped, _skipped in batches:
            self.pipes.extend(pipes)
        self._dirty = True
        self._refresh_lists()                 # crea BZ en los vértices de gravedad (conduit: ninguna)…
        # …y oculta las de quiebres/esquinas sin bóveda (siguen en el DXF como
        # "Estructura nula" para no romper la topología de la red).
        n_hidden = model_ops.hide_soft_vertex_structures(self.pipes, self.structures)
        # …y crea/asocia la CAJA de cada bóveda reconocida con su forma, medidas (pies) y contorno.
        n_geo = n_alone = 0
        for result, utility, _pipes, _snapped, _skipped in batches:
            where = self._xdata_origin(result.page_index)
            # En eléctrico/telecom la caja nace de la bóveda reconocida y va en el
            # vértice por donde llega SU línea (los vértices solos nunca son caja).
            # Presión: sin estructuras en la red, cada bóveda es una caja suelta.
            added_geo, added_alone = model_ops.attach_vault_geometry(
                self.structures, getattr(result, "vaults_geo", None) or [],
                net=NETWORK_KIND.get(utility, "conduit"), utility=utility,
                origin=lambda c, where=where: where([c]),
                pipes=[p for p in self.pipes if p.get("layer") == utility])
            n_geo += added_geo; n_alone += added_alone
        # …y los codos reconocidos quedan como esquina «CV» con su radio (flujo manual).
        n_cv = model_ops.attach_fillets(self.pipes, self.structures)
        # …y cada QUIEBRE del plano de gravedad/conduit es una curva mal dibujada
        # (regla de los ingenieros): CV con el radio mínimo de la regla (automático),
        # solo donde entra sin tocar otra curva. Agua y gas no.
        fpp = self.scale / self.zoom if self.scale and self.zoom else 0.0
        curvas_q, sin_lugar = quiebres_curvas.curvas_en_quiebres(
            self.pipes, self.structures, fpp, indices=range(n_prev, len(self.pipes)))
        n_hidden -= sum(1 for s in curvas_q if s.get("net") == "gravity")   # el buzón oculto ahora es la curva
        if n_hidden or n_geo or n_cv or curvas_q:
            self._refresh_lists()
        self._update_ui()
        self._redraw()
        parts = []
        for result, utility, pipes, _snapped, _skipped in batches:
            if not pipes:
                continue
            n_seg = sum(int(getattr(pl, "n_segments", 1) or 1) for pl in result.drawable)
            utility_name = _recognition.utility_label(utility)
            parts.append(_tr("{n} rutas ({m} tramos) de {u}").format(
                n=len(pipes), m=n_seg, u=utility_name))
        msg = (_tr("Importadas: {items}.").format(items="; ".join(parts))
               if parts else _tr("Importadas estructuras reconocidas."))
        if n_geo:
            msg += " " + _tr("Estructuras con medidas: {g}.").format(g=n_geo)
            if n_alone:
                msg += " " + _tr("({a} como cajas sueltas, sin unir a una línea.)").format(a=n_alone)
        if n_cv:
            msg += " " + _tr("Codos como esquina + radio (CV): {c}.").format(c=n_cv)
        if curvas_q:
            msg += " " + _tr("Quiebres como curva de radio mínimo: {q}.").format(q=len(curvas_q))
        if sin_lugar:
            msg += " " + _tr("Quiebres sin lugar para la curva mínima (tramos cortos), quedan como quiebre: {s}.").format(
                s=len(sin_lugar))
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
        return True

    def _pagina_fondo(self):
        """La hoja del PDF que muestra el lienzo, para el recorte nítido de una hoja
        enorme (fondo_pdf), o None si el fondo no es esa hoja (proyecto sin el PDF)."""
        tam = self.canvas.tam_hoja()
        if not self.doc or tam is None or not 0 <= self.page_idx < self.doc.page_count:
            return None
        page = self.doc[self.page_idx]
        if (abs(page.rect.width * self.zoom - tam[0]) > 2
                or abs(page.rect.height * self.zoom - tam[1]) > 2):
            return None
        return page

    def _load_page(self, idx):
        self._close_editor()
        page = self.doc[idx]; self.page_idx = idx; self.scale = VP.detect_scale(page)
        if self._scale_override:        # hoja compuesta: escala única elegida en el compositor
            self.scale = float(self._scale_override)
        self.rot = page.rotation; mbx = page.mediabox; self.W, self.H = mbx.width, mbx.height
        self.derot = page.derotation_matrix
        # La hoja entera a zoom 3.5; si es enorme (hoja compuesta de muchas piezas),
        # a menos resolución con las MISMAS coordenadas (fondo_pdf).
        fondo = fondo_pdf.render_pix(page, self.zoom)
        pix = fondo.pix
        self.pageH_px = fondo.alto
        # tamaño de marca acotado: evita textos/Multileaders gigantes por escala mal detectada
        self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
        buf = bytes(pix.samples)
        qimg = QtGui.QImage(buf, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888).copy()
        self.gray = fondo_pdf.gris(buf, pix.width, pix.height, pix.stride)
        escala, tam = fondo.escala, (fondo.ancho, fondo.alto)
        del buf, pix, fondo                   # la hoja ya está en `qimg`: no duplicarla en memoria
        self._overlay = []
        self.canvas.set_image(qimg, escala, tam)
        self._reset_model(); self._update_page_label()
        self._refresh_scale_label()
        self._info(_tr("Página {n} cargada.").format(n=idx + 1))

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
        self._busy(_tr("Guardando proyecto…"))
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
            self._info(_tr("Proyecto guardado: {archivo}").format(archivo=os.path.basename(path)))
            self._flash_save()
        finally: self._unbusy()
        # Confirmación visible 2 s, DESPUÉS de quitar el «Guardando…».
        if not self._dirty and self.project_path == path:
            _busy_mod.toast(self, "✔ " + _tr("Proyecto guardado"))

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
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, _tr("Guardar proyecto como"), base, _tr("Proyecto (*.digproj)"))
        if path: self._write_project(path)

    def open_project(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Abrir proyecto"), DOWNLOADS, _tr("Proyecto (*.digproj)"))
        if path: self._open_project_path(path)

    def _open_project_path(self, path):
        if not self._confirm_discard(): return
        self._busy(_tr("Abriendo proyecto…"))
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
            # sin el tope de 256 MB de Qt: la hoja de una hoja compuesta lo pasa fácil
            qimg = fondo_pdf.leer_png(png)
            if qimg.isNull():
                raise ValueError(_tr("No se pudo leer la imagen de la hoja del proyecto."))
            # Normalización de los datos (casteo de cotas por vértice, zonas de
            # borrado, reconstrucción de Georef) vive en project_io (pura, testeable);
            # aquí solo se ASIGNAN a self.* y se hace lo de Qt/PDF.
            data = project_io.parse_model(model)
            # hoja enorme guardada a menos resolución (fondo_pdf): mismas coordenadas
            escala, tam = data["fondo_escala"], data["fondo_tam"]
            self._overlay = []; self._close_editor()
            self.canvas.set_image(qimg, escala, tam); self.gray = qimage_to_gray(qimg)
            self.scale = data["scale"]; self.zoom = data["zoom"]; self.rot = data["rot"]
            self.W, self.H = data["W"], data["H"]; self.derot = fitz.Matrix(*data["derot"])
            self.pageH_px = self.canvas.tam_hoja()[1] if escala < 1.0 else qimg.height()
            self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
            if tmp_pdf:
                self.pdf_path = tmp_pdf; self.doc = fitz.open(tmp_pdf)
            else:
                self.pdf_path = None; self.doc = None
            self.work_pdf_path = tmp_pdf
            self.composite = data.get("composite")
            self._scale_override = data.get("scale_override")
            self.blank_canvas = bool(data.get("blank_canvas"))
            self.paper = data.get("paper")
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
            self._letters_off = set(data.get("letters_off") or [])
            if self.doc and (self.hidden_ocgs or "0" in self.hidden_ocgs_by_source):
                from hoja import pdf_layers as _pdf_layers
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
            self.canvas.nitidez.programar()          # ya está el PDF: recorte nítido si hace falta
            # Reponer la versión/idioma de Civil 3D con que se guardó el proyecto
            # (si esa versión sigue instalada). Debe ir ANTES de _warn_missing_families.
            self._restore_civil_selection(model.get("civil_year"), model.get("civil_lang"))
            from catalogo import civil_catalog as _cc
            _cv = f" · Civil 3D {self.civil_year}/{_cc._current_lang or '—'}" if self.civil_year else ""
            self._info(_tr("Proyecto abierto ({n} utilidades){civil}. Ctrl+S guarda en este mismo "
                           "archivo.").format(n=len(self.pipes), civil=_cv))
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
            from catalogo import civil_catalog as _cc
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

        lines = ["<b>" + _tr("Este proyecto usa familias del catálogo que no están instaladas "
                             "en Civil 3D {anio} ({idioma}):").format(
                     anio=self.civil_year, idioma=_cc._current_lang or "?") + "</b>", ""]
        for m in missing[:25]: lines.append(f"  • <code>{m}</code>")
        if len(missing) > 25: lines.append("  " + _tr("… y {n} más.").format(n=len(missing) - 25))
        lines += ["", _tr("¿Quieres abrir el instalador de familias ahora? "
                          "Puedes seguir trabajando con el proyecto igual — el aviso es "
                          "solo para evitar sorpresas al exportar a DXF.")]

        mb = QtWidgets.QMessageBox(self)
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setWindowTitle(_tr("Familias no instaladas"))
        mb.setTextFormat(QtCore.Qt.RichText)
        mb.setText("<br>".join(lines))
        btn_install = mb.addButton(_tr("Instalar familias…"), QtWidgets.QMessageBox.AcceptRole)
        mb.addButton(_tr("Seguir sin instalar"), QtWidgets.QMessageBox.RejectRole)
        mb.exec()
        if mb.clickedButton() is btn_install:
            self.open_install_family_dialog()

    # ── «¿hay cambios sin guardar?» por CONTENIDO ──
    # `_dirty` lo encienden muchas rutas (refrescos, re-armado de buzones, cambio
    # de hoja…) aunque el proyecto no cambie. Al quedar limpio (guardar/abrir) se
    # toma la huella del modelo que se guarda en el .digproj y antes de preguntar
    # se compara: si es la misma, no hay nada que guardar.
    @property
    def _dirty(self):
        return self.__dict__.get("_dirty_flag", False)

    @_dirty.setter
    def _dirty(self, value):
        self._dirty_flag = bool(value)
        if not value:
            self._clean_sig = None
            self._forzar_cambios = False
            # Guardado, recién abierto o descartado: la copia automática ya no sirve.
            ag = self.__dict__.get("autoguardado")
            if ag is not None:
                ag.limpiar()
            # Diferida: incluye lo que se normaliza justo después de abrir.
            QtCore.QTimer.singleShot(0, self._take_clean_sig)

    def _take_clean_sig(self):
        # Aunque la marca ya se haya vuelto a encender (lo hacen rutas de la misma
        # carga/guardado), el contenido en este instante es el guardado.
        self._clean_sig = self._content_sig()

    def _content_sig(self):
        try:
            m = project_io.build_model_dict(self)
            for k in ("page_idx", "version", "pdf_name"):
                m.pop(k, None)
            return hash(json.dumps(m, sort_keys=True, default=str))
        except Exception:
            return None

    def _has_real_changes(self):
        if not self._dirty:
            return False
        if self.__dict__.get("_forzar_cambios"):     # trabajo recuperado: aún no se guardó
            return True
        sig = getattr(self, "_clean_sig", None)
        if sig is not None and sig == self._content_sig():
            self._dirty_flag = False
            try: self._update_title()
            except Exception: pass
            return False
        return True

    def _confirm_discard(self):
        if self.canvas.pixmap_item is None or not self._has_real_changes(): return True
        r = QtWidgets.QMessageBox.question(
            self, _tr("Cambios sin guardar"), _tr("Hay cambios sin guardar. ¿Deseas guardarlos?"),
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if r == QtWidgets.QMessageBox.Cancel: return False
        if r == QtWidgets.QMessageBox.Save:
            self.save_project(); return not self._dirty
        return True

    def close_project(self):
        if self.canvas.pixmap_item is None: return
        if not self._confirm_discard(): return
        self._soltar_respaldo()
        if self.doc:
            self.doc.close()
        self._cleanup_tmp_pdf()
        self.canvas.scene().clear(); self.canvas.pixmap_item = None; self.canvas.pdf_bg_item = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.gray = None; self._update_title()
        self.blank_canvas = False; self.paper = None
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
        self._recog_cache.clear()
        self.cur_pts = []; self._erase_pts = []; self._overlay = []; self._close_editor()
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = self.sel_cl = self.sel_db = -1
        self._undo.clear(); self._redo.clear(); self._dirty = False
        self.georef = georef_mod.Georef()
        self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._info(_tr("Proyecto cerrado."))

    def closeEvent(self, e):
        if self._confirm_discard():
            ag = self.__dict__.get("autoguardado")
            if ag is not None:
                ag.cerrar()                         # cierre normal: no queda nada por recuperar
            if self.doc:
                self.doc.close()
            self._cleanup_tmp_pdf(); e.accept()
        else: e.ignore()

    # ── autoguardado y recuperación (autoguardado.py) ──
    def iniciar_autoguardado(self):
        """Arranca las copias automáticas y, si una sesión anterior se cerró sin
        guardar, ofrece recuperarla. True si se recuperó un proyecto."""
        from ui.dialogos import dialogs as _dlg
        self.autoguardado.iniciar()
        try:
            copias = autoguardado.recuperables(self.autoguardado.base)
        except Exception:
            copias = []
        if not copias:
            return False
        resp = _dlg.preguntar_recuperacion(self, copias[0], len(copias) - 1)
        if resp == "recuperar":
            return self._recuperar_copia(copias[0])
        if resp == "descartar":
            autoguardado.descartar(copias[0])
        return False

    def _recuperar_copia(self, meta):
        """Abre la copia automática `meta` como proyecto SIN guardar (Ctrl+S la guarda
        en el archivo original, si lo tenía)."""
        tmp = os.path.join(self.autoguardado.base, f"recuperado-{meta.get('sesion', 'copia')}.digproj")
        try:
            autoguardado.armar_digproj(meta["dir"], tmp)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, _tr("Recuperar trabajo sin guardar"), str(e))
            return False
        self._open_project_path(tmp)
        try:
            os.remove(tmp)                          # ya está en memoria (el PDF de trabajo va aparte)
        except OSError:
            pass
        if self.project_path != tmp:                # no se pudo abrir: la copia se conserva
            return False
        original = meta.get("proyecto") or None
        self.project_path = original if original and os.path.isdir(os.path.dirname(original)) else None
        self._forzar_cambios = True                 # sigue «sin guardar» hasta que se guarde
        self._dirty_flag = True
        self._update_title()
        autoguardado.descartar(meta)
        self._info(_tr("Trabajo recuperado. Guárdalo (Ctrl+S) para conservarlo."))
        return True

    # ─────────────────────────── exportar ───────────────────────────
    def run_pipeline(self, mode="todo"):
        """mode: 'todo' = PDF digitalizado + anotaciones · 'pdf' = solo el PDF ·
        'anot' = solo las anotaciones dibujadas en el programa."""
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, _tr("Nada"), _tr("Abre un PDF o proyecto.")); return
        need_pdf = mode in ("todo", "pdf")
        if need_pdf and getattr(self, "blank_canvas", False):
            # Lienzo en blanco: no hay PDF que fusionar y nunca lo hubo, así
            # que se exportan las anotaciones sin avisar de nada (el aviso de
            # abajo daría a entender que se perdió un PDF que sí existía).
            mode = "anot"; need_pdf = False
        # PDF de TRABAJO: el de la hoja que está en el editor. Tras «Componer hoja»
        # con otro PDF, `pdf_path` sigue siendo el primero que se abrió y el DXF
        # salía con esa hoja, desfasada de las utilidades (reporte 2026-09-30).
        src_pdf = self._export_pdf_path()
        if need_pdf and not src_pdf:
            QtWidgets.QMessageBox.information(self, _tr("Sin PDF"), _tr("No se encontró el PDF original. Se exportarán solo las anotaciones (utilidades, leaders, textos)."))
            mode = "anot"; need_pdf = False
        # Limpieza antes de exportar (2026-10-08): solo pregunta si hay algo que arreglar.
        if mode in ("todo", "anot") and not self.revisar_dibujo(exportando=True):
            return
        base = os.path.splitext(os.path.basename(self.pdf_path))[0] if self.pdf_path else "proyecto"
        suffix = {"todo": "_completo", "pdf": "_plano", "anot": "_anotaciones"}[mode]
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, _tr("Guardar DXF"), os.path.join(DOWNLOADS, base + suffix + ".dxf"), "DXF (*.dxf)")
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
                    geo_msg = "\n\n" + _tr("⚠ Georef: matriz presente pero active()=False."
                                  "\n  matrix[0]={m0}\n  matrix[1]={m1}"
                                  "\n  det={det}, epsg={epsg}"
                                  "\n  → Exportado en coordenadas de escala.").format(
                        m0=m[0], m1=m[1], det=f"{det:.6f}", epsg=self.georef.epsg)
                elif not self.georef.matrix:
                    geo_msg += "\n\n" + _tr("(Sin georreferenciación configurada.)")
                QtWidgets.QMessageBox.information(self, _tr("Listo"), _tr("Exportado (solo anotaciones):\n{archivo}{georef}").format(
                    archivo=out, georef=geo_msg))
                self._info(_tr("DXF de anotaciones exportado (georef).") if geo_active else _tr("DXF de anotaciones exportado."))
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
            return
        self._tmp = out + ".base.tmp.dxf"
        self._prog = QtWidgets.QProgressDialog(_tr("Digitalizando el plano…"), None, 0, 0, self)
        self._prog.setWindowTitle(_tr("Procesando")); self._prog.setWindowModality(QtCore.Qt.WindowModal)
        self._prog.setCancelButton(None); self._prog.show()
        # Solo la hoja que se ve en el editor (la de las anotaciones).
        pages = [self.page_idx] if self.doc and 0 <= self.page_idx < self.doc.page_count else None
        self._worker = PipelineWorker(src_pdf, self._tmp, pages=pages); self._worker.done.connect(self._pipeline_done); self._worker.start()

    def _export_pdf_path(self):
        """PDF que digitaliza «Exportar DXF»: el de trabajo (hoja del editor, también
        la hoja compuesta) y, si no hay, el abierto. None si no existe en disco."""
        for path in (self.work_pdf_path, self.pdf_path):
            if path and os.path.isfile(path):
                return path
        return None

    def _pipeline_done(self, tmp, err):
        if getattr(self, "_prog", None): self._prog.close()
        if err: QtWidgets.QMessageBox.critical(self, _tr("Error al digitalizar"), err); return
        self._busy(_tr("Guardando el DXF…"))
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
            self._unbusy()
            geo_active = self.georef.active()
            geo_warn = ""
            if self.georef.matrix and not geo_active:
                m = self.georef.matrix
                det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
                # Mismo aviso que la exportación de solo anotaciones (misma clave).
                geo_warn = "\n\n" + _tr("⚠ Georef: matriz presente pero active()=False."
                                        "\n  matrix[0]={m0}\n  matrix[1]={m1}"
                                        "\n  det={det}, epsg={epsg}"
                                        "\n  → Exportado en coordenadas de escala.").format(
                    m0=m[0], m1=m[1], det=f"{det:.6f}", epsg=self.georef.epsg)
            elif not self.georef.matrix:
                geo_warn = "\n\n" + _tr("(Sin georreferenciación configurada.)")
            geo_tag = " [georef]" if geo_active else ""
            if marks:
                nreg = sum(1 for r in self.erase_regions if r.get("enabled", True))
                msg = _tr("Exportado (PDF + anotaciones){georef}:\n{archivo}\n\n{np} utilidades, "
                          "{nl} leaders, {nt} textos, {nz} zonas borradas.").format(
                    georef=geo_tag, archivo=self._out, np=len(self.pipes), nl=len(self.leaders),
                    nt=len(self.text_marks), nz=nreg) + geo_warn
            else:
                msg = _tr("Exportado (solo el PDF digitalizado){georef}:\n{archivo}").format(
                    georef=geo_tag, archivo=self._out) + geo_warn
            QtWidgets.QMessageBox.information(self, _tr("Listo"), msg); self._info(_tr("DXF exportado (georef).") if geo_active else _tr("DXF exportado."))
        except Exception as e:
            _busy_mod.overlay_for(self).end() if _busy_mod.overlay_for(self).active else None
            import traceback; QtWidgets.QMessageBox.critical(self, _tr("Error al guardar"), f"{e}\n{traceback.format_exc()}")

    def _merge_into(self, doc, marks=True):
        dxf_export.merge_into(self, doc, marks=marks)

    # ─────────────────────────── drag & drop ───────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls(): self.open_path(u.toLocalFile()); break


def main():
    # La Vista 3D usa QOpenGLWidget: Qt pide esto ANTES de crear la app.
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication(sys.argv)
    app._no_wheel_filter = _NoWheelFilter(app)
    app.installEventFilter(app._no_wheel_filter)
    # Idioma preferido del usuario. Debe cargarse ANTES de construir Main() para
    # que los textos ya salgan traducidos desde el primer render.
    from traduccion import i18n as _i18n
    _i18n.load_lang()
    # Tema visual global (claro/oscuro). La preferencia se persiste en QSettings
    # y se puede alternar desde el menú "Ver" en tiempo real. Todo el CSS antes
    # hardcodeado ahora vive en app/theme.py, parametrizado por tokens de color.
    _theme.apply_theme(app, _theme.load_preference("dark"))
    win = Main(); win.show()
    recuperado = win.iniciar_autoguardado()      # copias automáticas + ofrecer recuperar
    if len(sys.argv) > 1 and not recuperado:
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
