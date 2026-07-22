"""
marcar_utilidades.py — Digitalizar planos y marcar utilidades.

App de escritorio (PySide6) para ingeniería civil: abre el PDF de un plano,
marca utilidades, coloca Multileaders con nomenclatura, escribe texto libre,
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
import excel_import
from export.network_json import write_network_json
from geo import georef as georef_mod
from geometry import point_in_poly, qimage_to_gray
from ocr import OcrWorker, IcrWorker
from model import (VERSION, TIPOS, ACI_RGB, LEADER_TEXT_FT, LEADER_ORIENT,
                   Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE, GRAVITY_LAYERS,
                   TAB_PIPE, TAB_ML, TAB_LEADER, TAB_TEXT, TAB_REGION,
                   WORK_UNITS, DEFAULT_WORK_UNIT, is_valid_work_unit, CHANGELOG,
                   PIPE_DIAMETERS_IN, PIPE_MATERIALS, DEFAULT_PIPE_MATERIAL,
                   nearest_pipe_diameter)

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
BTN_ON = "background:#2e9e4f;color:white;font-weight:bold;padding:8px;border-radius:4px;"
BTN_OFF = "background:#3c5a99;color:white;padding:8px;border-radius:4px;"


def aci_qcolor(a): return QtGui.QColor(*ACI_RGB.get(a, (235, 235, 235)))
def layer_qcolor(l): return aci_qcolor(C.OUTPUT_LAYERS.get(l, 7))


def swatch_icon(color, size=14):
    pm = QtGui.QPixmap(size, size); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setBrush(color); p.setPen(QtGui.QPen(QtGui.QColor(70, 70, 70)))
    p.drawRect(0, 0, size - 1, size - 1); p.end(); return QtGui.QIcon(pm)


class InlineEdit(QtWidgets.QTextEdit):
    """Editor embebido. Enter = aplicar; Ctrl+Shift+Enter o Shift+Enter = salto de
    línea. El commit se difiere con un timer para no destruir el widget dentro de
    su propio evento (eso provocaba cierres inesperados)."""
    committed = QtCore.Signal(str)

    def __init__(self, text):
        super().__init__(); self.setPlainText(text); self._done = False
        self.setStyleSheet("background:#111;color:#7f7;border:1px solid #7f7;")

    def _commit(self):
        if not self._done:
            self._done = True; txt = self.toPlainText()
            QtCore.QTimer.singleShot(0, lambda: self.committed.emit(txt))

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            m = e.modifiers()
            if (m & QtCore.Qt.ShiftModifier):     # Shift(+Ctrl)+Enter → salto de línea
                self.insertPlainText("\n"); return
            self._commit(); return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e); self._commit()


class PipelineWorker(QtCore.QThread):
    done = QtCore.Signal(str, str)

    def __init__(self, pdf, tmp): super().__init__(); self.pdf, self.tmp = pdf, tmp

    def run(self):
        try:
            import digitize
            digitize.main(self.pdf, self.tmp, verbose=False); self.done.emit(self.tmp, "")
        except Exception as e:
            import traceback; self.done.emit("", f"{e}\n\n{traceback.format_exc()}")


class Canvas(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float, object)
    dbl = QtCore.Signal(float, float)
    moved = QtCore.Signal(float, float)

    def __init__(self, win):
        super().__init__(); self.win = win
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(13, 19, 33)); self.setAcceptDrops(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMouseTracking(True); self.viewport().setMouseTracking(True)
        self.pixmap_item = None; self._pan = False; self._pan0 = None; self._moving = False
        self.pdf_opacity = 1.0

    def set_image(self, qimg):
        self.scene().clear()
        self.pixmap_item = self.scene().addPixmap(QtGui.QPixmap.fromImage(qimg))
        self.pixmap_item.setZValue(Z_PDF)
        self.pixmap_item.setOpacity(self.pdf_opacity)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform(); self.fitInView(self.pixmap_item, QtCore.Qt.KeepAspectRatio)

    def set_pdf_opacity(self, val):
        self.pdf_opacity = max(0.1, min(1.0, val))
        if self.pixmap_item: self.pixmap_item.setOpacity(self.pdf_opacity)

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.win._on_enter(); e.accept(); return
        if e.key() == QtCore.Qt.Key_Escape:
            self.win._on_escape(); e.accept(); return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        if self.pixmap_item:
            f = 1.25 if e.angleDelta().y() > 0 else 0.8; self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = True; self._pan0 = e.position(); self.setCursor(QtCore.Qt.ClosedHandCursor); return
        if not self.pixmap_item: return super().mousePressEvent(e)
        self.setFocus(QtCore.Qt.MouseFocusReason)
        sp = self.mapToScene(e.position().toPoint())
        if self.win.mode == "move" and e.button() == QtCore.Qt.LeftButton:
            self._moving = True; self.win.begin_move(sp.x(), sp.y()); return
        if e.button() in (QtCore.Qt.LeftButton, QtCore.Qt.RightButton):
            self.clicked.emit(sp.x(), sp.y(), e.button()); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.pixmap_item:
            sp = self.mapToScene(e.position().toPoint()); self.moved.emit(sp.x(), sp.y())
        if self._pan:
            d = e.position() - self._pan0; self._pan0 = e.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y())); return
        if self._moving:
            sp = self.mapToScene(e.position().toPoint()); self.win.do_move(sp.x(), sp.y()); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = False; self.setCursor(QtCore.Qt.ArrowCursor); return
        if self._moving and e.button() == QtCore.Qt.LeftButton:
            self._moving = False; self.win.end_move(); return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.win.mode == "pipe": self.win.finish_pipe(); return
        sp = self.mapToScene(e.position().toPoint()); self.dbl.emit(sp.x(), sp.y())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            self.win.open_path(u.toLocalFile()); break


class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Digitalizador de planos — utilidades  (v{VERSION})"); self.resize(1480, 940)
        self.setAcceptDrops(True)
        self.canvas = Canvas(self); self.canvas.clicked.connect(self.on_click)
        self.canvas.dbl.connect(self.on_dblclick); self.setCentralWidget(self.canvas)
        self.zoom = 3.5; self.scale = 20 / 72.0; self.rot = 0; self.W = 0; self.H = 0
        self.derot = fitz.Matrix(1, 0, 0, 1, 0, 0); self.gray = None; self.page_idx = 0; self.pageH_px = 0
        self.pdf_path = None; self.doc = None; self.project_path = None; self.leader_hpx = 40
        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.mode = "idle"; self._pending = None
        self.snap = False; self.snap_r = 14
        self.show_text_boxes = False; self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
        self.sel_pipe = -1; self.sel_leader = -1; self.sel_region = -1; self.sel_text = -1; self._no_center = False
        self._move0 = None; self._drag_vertex = None; self._edit_pts = None; self._edit_closed = False; self._edit_leader = None
        self._move_kind = None; self._moved = False; self._press_xy = None; self._last_xy = None
        self._extending = False; self._ext_layer = None; self._ext_pipe = None; self._ext_at = None
        self._editor = None; self._undo, self._redo, self._overlay = [], [], []
        self._dirty = False; self._style_guard = False; self._prop_guard = False; self._clip = None
        self.georef = georef_mod.Georef()          # georreferenciación (píxel→UTM); inactiva por defecto
        self.work_unit = DEFAULT_WORK_UNIT          # unidad de trabajo del proyecto: 'ft' o 'in' (obligatoria)
        self._build_ui(); self._apply_style(); self._shortcuts(); self._update_ui()

    # ─────────────────────────── UI ───────────────────────────
    def _build_ui(self):
        mb = self.menuBar()
        mfile = mb.addMenu("&Archivo")
        self._menu_act(mfile, "Abrir PDF…", self.open_pdf)
        self._menu_act(mfile, "Abrir Excel…", self.open_excel)
        mfile.addSeparator()
        self._menu_act(mfile, "Abrir proyecto…", self.open_project)
        self._menu_act(mfile, "Guardar proyecto", self.save_project, "Ctrl+S")
        self._menu_act(mfile, "Guardar proyecto como…", self.save_project_as, "Ctrl+Shift+S")
        mfile.addSeparator()
        self._menu_act(mfile, "Cerrar proyecto", self.close_project, "Ctrl+W")
        medit = mb.addMenu("&Edición")
        self._menu_act(medit, "Deshacer", self.undo, "Ctrl+Z")
        self._menu_act(medit, "Rehacer", self.redo, "Ctrl+Shift+Z")
        mgeo = mb.addMenu("&Georreferencia")
        self._menu_act(mgeo, "Georreferenciar…", self.open_georef)
        self._menu_act(mgeo, "Quitar georreferencia", self.clear_georef)
        mhelp = mb.addMenu("A&yuda")
        self._menu_act(mhelp, "Acerca de…", self.show_about)
        self._menu_act(mhelp, "Manual de usuario", self.show_manual)
        self._menu_act(mhelp, "Atajos de teclado", self.show_shortcuts)

        # ── Barra de acción superior: zoom · deshacer/rehacer · imán · exportar ──
        tb = self.addToolBar("Acciones"); tb.setMovable(False)
        def tact(txt, tip, fn):
            a = QtGui.QAction(txt, self); a.setToolTip(tip); a.triggered.connect(fn); tb.addAction(a); return a
        tact("🔍＋", "Acercar", self._zoom_in); tact("🔍－", "Alejar", self._zoom_out)
        tb.addSeparator(); tact("↶", "Deshacer (Ctrl+Z)", self.undo); tact("↷", "Rehacer (Ctrl+Shift+Z)", self.redo)
        tb.addSeparator()
        self.chk_snap = QtWidgets.QCheckBox("Imán al trazo"); self.chk_snap.toggled.connect(self._toggle_snap); tb.addWidget(self.chk_snap)
        spacer = QtWidgets.QWidget(); spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred); tb.addWidget(spacer)
        # Selector de UNIDAD DE TRABAJO (obligatorio para la red 3D): pies o pulgadas.
        # QComboBox lista opciones ("addItem(texto, datoOculto)") y con currentData()
        # leemos el "dato oculto" — aquí lo usamos como código corto ("ft"/"in").
        tb.addWidget(QtWidgets.QLabel(" Unidad de red: "))
        self.unit_combo = QtWidgets.QComboBox()
        self.unit_combo.addItem("Pies (ft)", "ft"); self.unit_combo.addItem("Pulgadas (in)", "in")
        self.unit_combo.setToolTip("Unidad en la que se ingresan cotas y diámetros, y en la que se exporta la red 3D (JSON). NO se usan metros.")
        self.unit_combo.currentIndexChanged.connect(self._on_unit_change)
        tb.addWidget(self.unit_combo)
        tb.addSeparator()
        self.btn_export = QtWidgets.QToolButton()
        self.btn_export.setText("⭳  Exportar DXF  ▾")
        self.btn_export.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.btn_export.setStyleSheet("QToolButton{background:#4d8eff;color:#00285d;font-weight:bold;padding:5px 14px;border-radius:4px;}")
        exp_menu = QtWidgets.QMenu(self.btn_export)
        exp_menu.addAction("PDF + anotaciones (todo)", lambda: self.run_pipeline("todo"))
        exp_menu.addAction("Solo el PDF digitalizado", lambda: self.run_pipeline("pdf"))
        exp_menu.addAction("Solo las anotaciones", lambda: self.run_pipeline("anot"))
        exp_menu.addSeparator()
        exp_menu.addAction("Exportar red 3D (JSON)", self.export_network_json)
        self.btn_export.setMenu(exp_menu); tb.addWidget(self.btn_export)

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
        ldock = QtWidgets.QDockWidget("Herramientas", self)
        ldock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)     # no se puede sacar/flotar
        left = QtWidgets.QWidget(); lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QtWidgets.QToolBox()
        # Guardamos por NOMBRE el índice de cada sección para poder abrirla desde código.
        self._sec_idx = {}

        # ── Helper de creación: crea una página del toolbox con su layout vertical ──
        def _page(title, key):
            page = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(page); lay.setSpacing(6)
            self.toolbox.addItem(page, title)
            self._sec_idx[key] = self.toolbox.count() - 1
            return page, lay

        # ═══════════════════════════════════════════════════════════════════════
        # PRIMERO: creamos TODOS los widgets (una sola vez) — luego los repartimos
        # en las secciones. Los que se comparten entre secciones (orient_combo,
        # gtxt) los REPARENTAMOS al abrir cada sección (ver _on_toolbox_change).
        # ═══════════════════════════════════════════════════════════════════════

        # Fila de navegación de páginas del PDF
        self.gp = QtWidgets.QWidget(); lp = QtWidgets.QHBoxLayout(self.gp); lp.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QtWidgets.QPushButton("◀"); self.btn_prev.setFixedWidth(34); self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next = QtWidgets.QPushButton("▶"); self.btn_next.setFixedWidth(34); self.btn_next.clicked.connect(self._next_page)
        self.page_edit = QtWidgets.QLineEdit(); self.page_edit.setAlignment(QtCore.Qt.AlignCenter)
        self.page_edit.setToolTip("Escribe un número de página y pulsa Enter")
        # returnPressed = Enter en un QLineEdit; editingFinished = perdió el foco también
        self.page_edit.returnPressed.connect(self._goto_page_edit)
        self.page_edit.editingFinished.connect(self._goto_page_edit)
        self.lbl_page = QtWidgets.QLabel(" / — ")
        lp.addWidget(self.btn_prev); lp.addWidget(self.page_edit, 1); lp.addWidget(self.lbl_page); lp.addWidget(self.btn_next)

        # Fila de transparencia del PDF de fondo (para ver mejor el marcado encima)
        self.gtr = QtWidgets.QWidget(); ltr = QtWidgets.QHBoxLayout(self.gtr); ltr.setContentsMargins(0, 0, 0, 0)
        tb_l = QtWidgets.QPushButton("−"); tb_l.setFixedWidth(30); tb_l.setToolTip("Más translúcido"); tb_l.clicked.connect(lambda: self._bump_opacity(-10))
        self.lbl_opacity = QtWidgets.QLabel("100%"); self.lbl_opacity.setAlignment(QtCore.Qt.AlignCenter)
        tb_r = QtWidgets.QPushButton("+"); tb_r.setFixedWidth(30); tb_r.setToolTip("Más opaco"); tb_r.clicked.connect(lambda: self._bump_opacity(10))
        ltr.addWidget(tb_l); ltr.addWidget(self.lbl_opacity, 1); ltr.addWidget(tb_r)

        # Botones de acción (uno por sección; el color verde/azul lo pone _update_ui)
        self.btn_pipe = QtWidgets.QPushButton("✏  Dibujar utilidad"); self.btn_pipe.clicked.connect(self.toggle_pipe)
        self.btn_leader = QtWidgets.QPushButton("↳  Colocar Multileader"); self.btn_leader.clicked.connect(lambda: self.start_leader(False))
        self.btn_leader_simple = QtWidgets.QPushButton("↘  Colocar Leader"); self.btn_leader_simple.clicked.connect(lambda: self.start_leader(True))
        self.btn_text = QtWidgets.QPushButton("T  Texto libre"); self.btn_text.clicked.connect(self.toggle_text_mode)
        self.btn_erase = QtWidgets.QPushButton("▭  Borrar zona"); self.btn_erase.clicked.connect(self.toggle_erase)

        # Grupo "Tipo de utilidad" (usado al DIBUJAR una utilidad)
        # QComboBox es la lista desplegable clásica. addItem(icono, texto, dato) le
        # asocia a cada opción un "dato oculto" que recuperamos con currentData().
        self.gt = QtWidgets.QWidget(); lgt = QtWidgets.QVBoxLayout(self.gt); lgt.setContentsMargins(0, 0, 0, 0)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.type_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for label, layer in TIPOS:
            self.type_combo.addItem(swatch_icon(layer_qcolor(layer)), label, layer)
        self.type_combo.setCurrentIndex(0); self.type_combo.currentIndexChanged.connect(lambda _: self._redraw())
        self.chk_ab = QtWidgets.QCheckBox("Abandonado (línea ──/── W ──)")
        self.chk_ext_same = QtWidgets.QCheckBox("Al extender un extremo: continuar la misma utilidad")
        self.chk_ext_same.setChecked(True)
        lgt.addWidget(self.type_combo); lgt.addWidget(self.chk_ab); lgt.addWidget(self.chk_ext_same)

        # Combo de ORIENTACIÓN — COMPARTIDO por Multileader y Leader.
        # Cuando el usuario abre "Multileader" o "Leader" lo REPARENTAMOS al slot
        # de esa sección (una única instancia; su estado —H/V/D— se mantiene).
        self.orient_combo = QtWidgets.QComboBox()
        for oid, lbl in LEADER_ORIENT: self.orient_combo.addItem(lbl, oid)
        self.orient_combo.currentIndexChanged.connect(lambda _: self._update_ui())

        # Grupo "Contenido del Multileader" (checkbox + texto libre + lista Excel)
        self.ga = QtWidgets.QGroupBox("Contenido del texto"); lga = QtWidgets.QVBoxLayout(self.ga)
        self.chk_custom = QtWidgets.QCheckBox("Usar texto personalizado"); self.chk_custom.toggled.connect(self._toggle_custom)
        lga.addWidget(self.chk_custom)
        self.txt_edit = QtWidgets.QLineEdit(); self.txt_edit.setPlaceholderText("texto personalizado…"); self.txt_edit.setEnabled(False)
        lga.addWidget(self.txt_edit)
        self.lbl_textos = QtWidgets.QLabel("Textos (columna TEXTO del Excel):"); lga.addWidget(self.lbl_textos)
        # QListWidget es una lista simple de líneas de texto (una por fila).
        self.text_list = QtWidgets.QListWidget(); self.text_list.setMaximumHeight(140); lga.addWidget(self.text_list)
        self.lbl_lead_hint = QtWidgets.QLabel("<i>Colocas varios seguidos; Esc para salir.</i>"); lga.addWidget(self.lbl_lead_hint)

        # Grupo "Estilo de texto" (fuente, altura, negrita + rotación).
        # COMPARTIDO por Multileader y Texto libre. La rotación solo aplica a
        # textos libres; la mostramos/ocultamos según la sección abierta.
        self.gtxt = QtWidgets.QGroupBox("Estilo de texto"); lgx = QtWidgets.QVBoxLayout(self.gtxt)
        # QFontComboBox = combo que lista todas las fuentes instaladas en el sistema.
        self.font_combo = QtWidgets.QFontComboBox(); self.font_combo.setCurrentFont(QtGui.QFont(C.TEXT_FONT))
        self.font_combo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.font_combo.currentFontChanged.connect(lambda _: self._style_changed())
        r = QtWidgets.QHBoxLayout(); r.addWidget(QtWidgets.QLabel("Altura (pies):"))
        b_minus = QtWidgets.QPushButton("−"); b_minus.setFixedWidth(30); b_minus.clicked.connect(lambda: self._bump_size(-0.5))
        # QDoubleSpinBox = campo numérico decimal con incremento por flechas (aquí ocultas).
        self.size_spin = QtWidgets.QDoubleSpinBox(); self.size_spin.setRange(0.5, 200); self.size_spin.setValue(3.0)
        self.size_spin.setSingleStep(0.5); self.size_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.size_spin.valueChanged.connect(lambda _: self._style_changed())
        b_plus = QtWidgets.QPushButton("+"); b_plus.setFixedWidth(30); b_plus.clicked.connect(lambda: self._bump_size(0.5))
        r.addWidget(b_minus); r.addWidget(self.size_spin); r.addWidget(b_plus)
        self.chk_bold = QtWidgets.QCheckBox("Negrita"); self.chk_bold.toggled.connect(lambda _: self._style_changed())
        lgx.addWidget(self.font_combo); lgx.addLayout(r); lgx.addWidget(self.chk_bold)
        # Rotación (0-360°) — solo se usa para textos libres.
        self.rot_row = QtWidgets.QWidget(); rr2 = QtWidgets.QHBoxLayout(self.rot_row); rr2.setContentsMargins(0, 0, 0, 0)
        rr2.addWidget(QtWidgets.QLabel("Rotación (°):"))
        rb_l = QtWidgets.QPushButton("⟲"); rb_l.setFixedWidth(30); rb_l.clicked.connect(lambda: self._bump_rot(-1))
        self.rot_spin = QtWidgets.QSpinBox(); self.rot_spin.setRange(0, 360); self.rot_spin.setSingleStep(1); self.rot_spin.setWrapping(True)
        self.rot_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons); self.rot_spin.valueChanged.connect(lambda _: self._style_changed())
        rb_r = QtWidgets.QPushButton("⟳"); rb_r.setFixedWidth(30); rb_r.clicked.connect(lambda: self._bump_rot(1))
        rr2.addWidget(rb_l); rr2.addWidget(self.rot_spin); rr2.addWidget(rb_r)
        lgx.addWidget(self.rot_row)
        lgx.addWidget(QtWidgets.QLabel("<i>Enter aplica · Ctrl+Shift+Enter salta de línea</i>"))

        # Grupo "En curso" (aparece cuando estás dibujando una utilidad o zona)
        self.gcur = QtWidgets.QGroupBox("En curso"); lc = QtWidgets.QHBoxLayout(self.gcur)
        self.btn_fin = QtWidgets.QPushButton("Finalizar (Enter)"); self.btn_fin.clicked.connect(self._on_enter)
        b_up = QtWidgets.QPushButton("Deshacer punto"); b_up.clicked.connect(self.undo)
        lc.addWidget(self.btn_fin); lc.addWidget(b_up)

        # Botones de Cotas y red 3D
        b_bz = QtWidgets.QPushButton("Gestionar buzones…"); b_bz.clicked.connect(self.manage_structures)
        b_xls = QtWidgets.QPushButton("Importar Excel de red…"); b_xls.clicked.connect(self.import_network_excel)

        # Botones de Georreferenciación
        b_geo = QtWidgets.QPushButton("🌍  Georreferenciar…"); b_geo.clicked.connect(self.open_georef)
        b_geo_off = QtWidgets.QPushButton("Quitar georreferencia"); b_geo_off.clicked.connect(self.clear_georef)

        # Casillas de OCR/ICR
        self.chk_txt = QtWidgets.QCheckBox("Textos impresos (OCR)"); self.chk_txt.toggled.connect(self.toggle_text_boxes)
        self.chk_icr = QtWidgets.QCheckBox("Manuscrita (ICR, offline)"); self.chk_icr.toggled.connect(self.toggle_icr)

        # ═══════════════════════════════════════════════════════════════════════
        # AHORA: creamos las secciones del acordeón y colocamos los widgets.
        # Los "slots" (self._slot_*) son QVBoxLayouts vacíos que quedan reservados
        # dentro de cada página para recibir los widgets compartidos por reparent.
        # ═══════════════════════════════════════════════════════════════════════

        # ── Sección: Vista y páginas ──
        p, l = _page("📄  Vista y páginas", "view")
        l.addWidget(QtWidgets.QLabel("Página:")); l.addWidget(self.gp)
        l.addWidget(QtWidgets.QLabel("Transparencia del PDF:")); l.addWidget(self.gtr)
        l.addStretch(1)

        # ── Sección: Dibujar utilidad ──
        p, l = _page("✏  Dibujar utilidad", "pipe")
        l.addWidget(self.btn_pipe)
        l.addWidget(QtWidgets.QLabel("Tipo de utilidad:"))
        l.addWidget(self.gt)
        self._slot_gcur_pipe = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_pipe)   # slot: aquí va gcur al dibujar
        l.addStretch(1)

        # ── Sección: Multileader ──
        # p, l = _page("↳  Multileader", "ml")
        # l.addWidget(self.btn_leader)
        # l.addWidget(QtWidgets.QLabel("Orientación:"))
        # self._slot_orient_ml = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_orient_ml)   # slot: orient_combo
        # l.addWidget(self.ga)                                                                # contenido (texto)
        # self._slot_style_ml = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_style_ml)     # slot: gtxt (estilo)
        # l.addStretch(1)

        # ── Sección: Leader (flecha simple) ──
        p, l = _page("↘  Leader (flecha simple)", "leader")
        l.addWidget(self.btn_leader_simple)
        l.addWidget(QtWidgets.QLabel("Orientación:"))
        self._slot_orient_ld = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_orient_ld)   # slot: orient_combo
        l.addWidget(QtWidgets.QLabel("<i>El Leader es solo flecha, sin texto.</i>"))
        l.addStretch(1)

        # ── Sección: Texto libre ──
        p, l = _page("T  Texto libre", "text")
        l.addWidget(self.btn_text)
        self._slot_style_tx = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_style_tx)     # slot: gtxt (estilo)
        l.addStretch(1)

        # ── Sección: Borrar zona ──
        p, l = _page("▭  Borrar zona", "erase")
        l.addWidget(self.btn_erase)
        _lbl = QtWidgets.QLabel("<i>Clic para agregar vértices, Enter cierra. "
                                     "Al exportar borra el plano dentro del polígono.</i>")
        _lbl.setWordWrap(True); l.addWidget(_lbl)
        self._slot_gcur_erase = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_erase)  # slot: gcur al borrar
        l.addStretch(1)

        # ── Sección: Georreferenciación ──
        p, l = _page("🌍  Georreferenciación", "georef")
        l.addWidget(b_geo); l.addWidget(b_geo_off)
        _lbl = QtWidgets.QLabel(
            "<i>Calzar el plano sobre imagen satelital te da coordenadas UTM <b>aproximadas</b> "
            "(útiles para anteproyecto, NO grado construcción). El dato topográfico real "
            "viene del levantamiento/Excel.</i>")
        _lbl.setWordWrap(True); l.addWidget(_lbl)
        l.addStretch(1)

        # ── Sección: Cotas y red 3D ──
        p, l = _page("📐  Cotas y red 3D", "net")
        l.addWidget(b_bz); l.addWidget(b_xls)
        _lbl = QtWidgets.QLabel(
            "<i>Los buzones aparecen automáticamente al dibujar tuberías de gravedad "
            "(alcantarillado/drenaje) — cada vértice es un buzón. Aquí gestionas su "
            "Cod, rim (tapa) y sump (fondo). También puedes IMPORTAR un Excel con "
            "hojas BUZONES y TUBERIAS (encabezados en fila 5).</i>")
        _lbl.setWordWrap(True); l.addWidget(_lbl)
        l.addStretch(1)

        # ── Sección: Reconocimiento (OCR / ICR) ──
        p, l = _page("🔤  Reconocimiento de texto", "ocr")
        l.addWidget(self.chk_txt); l.addWidget(self.chk_icr)
        _lbl = QtWidgets.QLabel(
            "<i>OCR = texto impreso (Tesseract).  ICR = manuscrita (EasyOCR, offline). "
            "Aparecen recuadros amarillos sobre el plano; clic en uno para corregir "
            "el texto reconocido.</i>")
        _lbl.setWordWrap(True); l.addWidget(_lbl)
        l.addStretch(1)

        # Al abrir una sección del acordeón: reparenta los widgets compartidos y
        # regresa el modo a "idle" (así no quedan mezclados los estados).
        self.toolbox.currentChanged.connect(self._on_toolbox_change)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.toolbox)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        lv.addWidget(scroll, 1)
        ldock.setWidget(left); ldock.setMinimumWidth(260)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, ldock)

        # (La inicialización de los widgets compartidos ocurre al final de _build_ui,
        # cuando el dock derecho —self.tabs, etc.— ya existe.)

        # ── DOCK DERECHO: inventario y selección ──
        rdock = QtWidgets.QDockWidget("Inventario", self); rdock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        right = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(right)
        self.tabs = QtWidgets.QTabWidget()
        self.pipe_list = QtWidgets.QListWidget(); self.pipe_list.currentRowChanged.connect(self._sel_pipe)
        self.lead_list = QtWidgets.QListWidget(); self.lead_list.currentRowChanged.connect(self._sel_leader)
        self.sleader_list = QtWidgets.QListWidget(); self.sleader_list.currentRowChanged.connect(self._sel_sleader)
        self.txt_marks_list = QtWidgets.QListWidget(); self.txt_marks_list.currentRowChanged.connect(self._sel_text)
        self.region_list = QtWidgets.QListWidget(); self.region_list.currentRowChanged.connect(self._sel_region)
        self.region_list.itemChanged.connect(self._region_toggled)
        self.tabs.addTab(self.pipe_list, "Utilidades"); #self.tabs.addTab(self.lead_list, "Multileaders")
        self.tabs.addTab(self.sleader_list, "Leaders")
        self.tabs.addTab(self.txt_marks_list, "Textos"); self.tabs.addTab(self.region_list, "Zonas")
        # Menú contextual (clic derecho) en cada lista del inventario
        for listw, tab_idx in ((self.pipe_list, TAB_PIPE), (self.lead_list, TAB_ML),
                               (self.sleader_list, TAB_LEADER), (self.txt_marks_list, TAB_TEXT),
                               (self.region_list, TAB_REGION)):
            listw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            listw.customContextMenuRequested.connect(
                lambda pos, lw=listw, ti=tab_idx: self._list_context_menu(lw, ti, pos))
        self.tabs.currentChanged.connect(self._tab_changed); rv.addWidget(self.tabs, 1)
        # Propiedades de la utilidad seleccionada (nombre, diámetro, unidad) → XDATA en el DXF
        self.gprop = QtWidgets.QGroupBox("Propiedades de la utilidad"); fpr = QtWidgets.QFormLayout(self.gprop)
        self.prop_name = QtWidgets.QLineEdit(); self.prop_name.editingFinished.connect(self._prop_changed)
        # El diámetro va SIEMPRE en PULGADAS y SOLO de la lista estándar del
        # catálogo (12,15,18,…): un desplegable NO editable, sin valores libres,
        # para que coincida 1:1 con un tamaño real del catálogo de Civil 3D.
        # Es independiente de la unidad de trabajo (que rige coordenadas/cotas).
        self.prop_diam = QtWidgets.QComboBox()
        for d in PIPE_DIAMETERS_IN:
            self.prop_diam.addItem(f'{d}"', float(d))
        self.prop_diam.currentIndexChanged.connect(lambda _: self._prop_changed())
        fpr.addRow("Nombre:", self.prop_name)
        self.lbl_prop_diam = QtWidgets.QLabel("Diámetro (pulg):"); fpr.addRow(self.lbl_prop_diam, self.prop_diam)
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
            self.prop_material.addItem(m)
        self.prop_material.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.prop_part = QtWidgets.QLineEdit(); self.prop_part.setPlaceholderText("p.ej. 900 mm Corrugated HDPE Pipe")
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
        fpr.addRow("Material:", self.prop_material)
        fpr.addRow("Tipo de red:", self.prop_nettype)
        # Labels dinámicas: se recomponen al cambiar la unidad de trabajo.
        self.lbl_prop_inv0 = QtWidgets.QLabel("Invert inicio (ft):"); fpr.addRow(self.lbl_prop_inv0, self.prop_inv0)
        self.lbl_prop_inv1 = QtWidgets.QLabel("Invert fin (ft):");   fpr.addRow(self.lbl_prop_inv1, self.prop_inv1)
        fpr.addRow("Part (pieza):", self.prop_part)
        rv.addWidget(self.gprop)
        rr = QtWidgets.QGridLayout()
        self.btn_ct = QtWidgets.QPushButton("Cambiar tipo"); self.btn_ct.clicked.connect(self.change_pipe_type)
        self.btn_mv = QtWidgets.QPushButton("Editar/mover"); self.btn_mv.clicked.connect(self.enter_move)
        self.btn_edit = QtWidgets.QPushButton("Editar texto"); self.btn_edit.clicked.connect(self.edit_selected_text)
        self.btn_del = QtWidgets.QPushButton("Eliminar"); self.btn_del.clicked.connect(self.delete_selected)
        rr.addWidget(self.btn_ct, 0, 0); rr.addWidget(self.btn_mv, 0, 1)
        rr.addWidget(self.btn_edit, 1, 0); rr.addWidget(self.btn_del, 1, 1)
        rv.addLayout(rr)
        rdock.setWidget(right); rdock.setMinimumWidth(250)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, rdock)

        # ── Barra de estado: modo · coordenadas · escala · imán ──
        self.status = self.statusBar(); self.status.setSizeGripEnabled(False)
        self.lbl_mode = QtWidgets.QLabel("Modo: inactivo"); self.lbl_mode.setStyleSheet("color:#adc6ff;")
        self.status.addWidget(self.lbl_mode)
        self.status.addWidget(QtWidgets.QLabel("│"))
        self.lbl_info = QtWidgets.QLabel(""); self.lbl_info.setStyleSheet("color:#8c909f;"); self.status.addWidget(self.lbl_info, 1)
        self.lbl_snap = QtWidgets.QLabel("Imán: OFF"); self.lbl_coords = QtWidgets.QLabel("X —  Y —")
        self.lbl_scale = QtWidgets.QLabel("Escala —"); self.lbl_geo = QtWidgets.QLabel("Georref: no")
        self.lbl_unit = QtWidgets.QLabel(f"Unidad: {self.work_unit}")
        for w in (self.lbl_snap, self.lbl_coords, self.lbl_scale, self.lbl_geo, self.lbl_unit):
            w.setStyleSheet("color:#c2c6d6;"); self.status.addPermanentWidget(w)
        self.canvas.moved.connect(self._update_coords)
        self._update_geo_status()
        self._info("Abre o arrastra un PDF/proyecto.")

        # Todo listo: coloca los widgets compartidos del acordeón en la sección
        # inicial (esto necesita que self.tabs, self.gprop y self.lbl_mode existan).
        self._on_toolbox_change(self.toolbox.currentIndex())
        self._refresh_unit_labels()                # etiquetas de campo con la unidad activa

    def _menu_act(self, menu, text, fn, sc=None):
        a = QtGui.QAction(text, self); a.triggered.connect(fn)
        if sc: a.setShortcut(sc)
        menu.addAction(a); return a

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow,QDockWidget,QGroupBox,QScrollArea,QMenuBar,QMenu{background:#2b2b2b;color:#eee;}
            QMenuBar::item:selected,QMenu::item:selected{background:#3c5a99;}
            QGroupBox{border:1px solid #444;margin-top:8px;padding:6px;border-radius:4px;font-weight:bold;}
            QGroupBox::title{subcontrol-origin:margin;left:8px;color:#bbb;}
            QListWidget,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QFontComboBox,QTabWidget::pane{background:#333;color:#eee;border:1px solid #555;}
            QTabBar::tab{background:#333;color:#ccc;padding:5px;} QTabBar::tab:selected{background:#3c5a99;color:white;}
            QPushButton{background:#3c5a99;color:white;border:none;padding:6px;border-radius:4px;}
            QPushButton:hover{background:#4a6fbf;} QLabel,QCheckBox{color:#ddd;font-weight:normal;}
            QSplitter::handle{background:#555;height:6px;}""")
        self.chk_snap.setChecked(False)

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
            self.page_idx = n; self._load_page(n)
        else:
            self._update_page_label()

    def _prev_page(self):
        if self.doc and self.page_idx > 0:
            if not self._confirm_discard(): return
            self.page_idx -= 1; self._load_page(self.page_idx)

    def _next_page(self):
        if self.doc and self.page_idx < self.doc.page_count - 1:
            if not self._confirm_discard(): return
            self.page_idx += 1; self._load_page(self.page_idx)

    # ─────────────────────────── Estado / modos ───────────────────────────
    def _on_enter(self):
        if self.mode == "pipe": self.finish_pipe()
        elif self.mode == "erase": self.finish_erase()
        elif self.mode in ("leader1", "leader2", "leader3"):
            self.set_mode("idle"); self._info("Comando Leader finalizado (Enter)")
        elif self.mode == "move":
            self.set_mode("idle"); self._info("Edición terminada (Enter)")

    def _on_escape(self):
        if self.mode == "pipe" and self.cur_pts:
            self._push(); self.cur_pts = []; self._extending = False; self._ext_pipe = None; self._ext_at = None
            self._update_ui(); self._redraw(); self._info("Puntos cancelados")
        elif self.mode == "erase" and self._erase_pts:
            self._erase_pts = []; self._redraw(); self._info("Zona cancelada")
        elif self.sel_pipe >= 0 or self.sel_leader >= 0 or self.sel_region >= 0 or self.sel_text >= 0:
            self._deselect_all(); self._info("Selección quitada")
        else:
            self.set_mode("idle"); self._info("Salió del modo")

    def _deselect_all(self):
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        for lst in (self.pipe_list, self.lead_list, self.sleader_list, self.txt_marks_list, self.region_list):
            lst.blockSignals(True); lst.setCurrentRow(-1); lst.clearSelection(); lst.blockSignals(False)
        if self.mode == "move": self.set_mode("idle")
        self._update_ui(); self._redraw()

    def _info(self, m): self.lbl_info.setText(m)

    def _zoom_in(self): self.canvas.scale(1.25, 1.25)
    def _zoom_out(self): self.canvas.scale(0.8, 0.8)

    def _toggle_snap(self, v):
        self.snap = v; self.lbl_snap.setText(f"Imán: {'ON' if v else 'OFF'}")
        self.lbl_snap.setStyleSheet("color:%s;" % ("#5fd35f" if v else "#c2c6d6"))

    def _update_coords(self, x, y):
        if self.canvas.pixmap_item is None: return
        cx, cy = self._to_cad(x, y); self.lbl_coords.setText(f"X {cx:,.1f}  Y {cy:,.1f}")

    def _update_geo_status(self):
        if self.georef.active():
            rms = f" · RMS {self.georef.rms:.2f} m" if self.georef.rms is not None else ""
            self.lbl_geo.setText(f"Georref: EPSG:{self.georef.epsg}{rms}")
            self.lbl_geo.setStyleSheet("color:#5fd35f;")
        else:
            self.lbl_geo.setText("Georref: no (escala titleblock)")
            self.lbl_geo.setStyleSheet("color:#e0c060;")

    def _update_ui(self):
        m = self.mode
        def st(btn, on): btn.setStyleSheet(BTN_ON if on else BTN_OFF)
        in_leader = m in ("leader1", "leader2", "leader3"); simple = bool(self._pending and self._pending.get("simple"))
        st(self.btn_pipe, m == "pipe"); st(self.btn_leader, in_leader and not simple)
        st(self.btn_leader_simple, in_leader and simple)
        st(self.btn_text, m == "text"); st(self.btn_erase, m == "erase")
        self.btn_pipe.setText("■  Salir de dibujar utilidad" if m == "pipe" else "✏  Dibujar utilidad")
        self.btn_leader.setText("●  Coloque Multileader…" if (in_leader and not simple) else "↳  Colocar Multileader")
        self.btn_leader_simple.setText("●  Coloque Leader…" if (in_leader and simple) else "↘  Colocar Leader")
        self.btn_erase.setText("■  Terminar zona (Enter)" if m == "erase" else "▭  Borrar zona (polígono)")
        ti = self.tabs.currentIndex()
        # Con el acordeón (QToolBox) la visibilidad de las opciones la controla la
        # sección expandida — cada sección solo enseña lo suyo. Aquí ya no tenemos
        # que ocultar/mostrar `gt`/`ga`/`gtxt` según el modo; solo ajustamos el
        # título del grupo cuando el estilo es del Multileader vs Texto libre.
        self.gtxt.setTitle("Estilo del Multileader" if m in ("leader1", "leader2", "leader3") else "Estilo de texto")
        self.gprop.setVisible(ti == TAB_PIPE and self.sel_pipe >= 0)
        # "En curso": solo mientras hay puntos en curso. gcur ya fue movido a la
        # sección correcta por set_mode; aquí solo habilitamos Finalizar y mostramos.
        active_draw = (m == "pipe" and len(self.cur_pts) >= 1) or (m == "erase" and len(self._erase_pts) >= 1)
        self.gcur.setVisible(active_draw)
        self.btn_fin.setEnabled((m == "pipe" and len(self.cur_pts) >= 2) or (m == "erase" and len(self._erase_pts) >= 3))
        ti = self.tabs.currentIndex()
        self.btn_ct.setVisible(ti == TAB_PIPE)
        self.btn_mv.setVisible(ti in (TAB_PIPE, TAB_LEADER, TAB_TEXT, TAB_REGION))
        self.btn_mv.setText("Mover" if ti == TAB_TEXT else "Editar/mover")
        self.btn_edit.setVisible(ti in (TAB_ML, TAB_TEXT))
        if simple:                                       # Leader (solo flecha)
            diag = self.orient_combo.currentData() == "d"
            lead1 = "Modo: Leader — clic en la cabeza de flecha (dónde señala)"
            lead2 = ("Modo: Leader — clic en el inicio del landing (bisagra)" if diag
                     else "Modo: Leader — clic en el final del cuerpo")
            lead3 = "Modo: Leader — clic en el final del cuerpo"
        else:
            lead1 = "Modo: Multileader — clic en la PUNTA (a qué señala)"
            lead2 = "Modo: Multileader — clic dónde va el TEXTO"
            lead3 = ""
        self.lbl_mode.setText({"idle": "Modo: inactivo  ·  clic en el dibujo para seleccionar",
                               "pipe": ("Modo: EXTENDIENDO desde el vértice — clic agrega puntos, Enter finaliza"
                                        if self._extending else "Modo: dibujar utilidad  ·  Enter finaliza"),
                               "leader1": lead1,
                               "leader2": lead2,
                               "leader3": lead3,
                               "text": "Modo: texto libre — clic donde escribir · Enter aplica",
                               "erase": "Modo: borrar zona — clic para el polígono, Enter cierra",
                               "move": "Modo: editar — arrastra vértice · clic en tramo inserta · clic-en-vértice extiende (F) · clic derecho elimina"}.get(m, ""))

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
            else:
                self.gcur.hide()
        self._update_ui(); self._redraw()

    def _tab_changed(self, _):
        ti = self.tabs.currentIndex()               # sel_leader se comparte entre ML y Leaders: re-sincronizar
        if ti == TAB_ML: self.sel_leader = self._leader_at_row(self.lead_list, self.lead_list.currentRow())
        elif ti == TAB_LEADER: self.sel_leader = self._leader_at_row(self.sleader_list, self.sleader_list.currentRow())
        if self.mode == "move": self.set_mode("idle")   # no seguir editando al cambiar de pestaña
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
    def active_layer(self):
        d = self.type_combo.currentData(); return d if d else "AGUA"

    def _toggle_custom(self, on):
        self.txt_edit.setEnabled(on); self.text_list.setEnabled(not on)
        if on:
            self.text_list.blockSignals(True); self.text_list.setCurrentRow(-1); self.text_list.clearSelection(); self.text_list.blockSignals(False)
        else:
            self.txt_edit.clear()

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
        if self._undo: self._redo.append(self._snap_state()); self._restore(self._undo.pop()); self._info("Deshacer")

    def redo(self):
        if self._redo: self._undo.append(self._snap_state()); self._restore(self._redo.pop()); self._info("Rehacer")

    # ─────────────────────────── abrir ───────────────────────────
    def _busy(self, m="Procesando…"):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor); self._info(m); QtWidgets.QApplication.processEvents()
    def _unbusy(self): QtWidgets.QApplication.restoreOverrideCursor()

    def open_path(self, path):
        low = path.lower()
        if low.endswith(".pdf"): self._open_pdf_path(path)
        elif low.endswith(".digproj"): self._open_project_path(path)
        elif low.endswith((".xlsx", ".xlsm")): self._read_excel(path)

    def open_pdf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir PDF", DOWNLOADS, "PDF (*.pdf)")
        if path: self._open_pdf_path(path)

    def _open_pdf_path(self, path):
        if not self._confirm_discard(): return
        self._busy("Abriendo PDF…")
        try:
            self.pdf_path = path; self.project_path = None; self.doc = fitz.open(path)
            self.page_idx = 0; self._load_page(0)
        finally: self._unbusy()

    def _load_page(self, idx):
        self._close_editor()
        page = self.doc[idx]; self.page_idx = idx; self.scale = VP.detect_scale(page)
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
        self.lbl_scale.setText(f"Escala 1\"={self.scale*72:.0f}'")
        self._info(f"Página {idx + 1} cargada.")

    def _reset_model(self):
        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        self._overlay = []; self._close_editor(); self._dirty = False; self._extending = False
        self.georef = georef_mod.Georef()          # cada página/PDF nuevo empieza sin georreferencia
        self._undo.clear(); self._redo.clear(); self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
        self.set_mode("idle"); self._refresh_lists(); self._redraw(); self._update_geo_status()

    # ─────────────────────────── proyecto ───────────────────────────
    def _write_project(self, path):
        self._busy("Guardando proyecto…")
        try:
            model = dict(pipes=self.pipes, leaders=self.leaders, text_marks=self.text_marks,
                         erase_regions=self.erase_regions, structures=self.structures,
                         georef=self.georef.to_dict(),
                         work_unit=self.work_unit,                # unidad de trabajo del proyecto
                         tf=dict(scale=self.scale, zoom=self.zoom, rot=self.rot, W=self.W, H=self.H,
                                 derot=[self.derot.a, self.derot.b, self.derot.c, self.derot.d, self.derot.e, self.derot.f]),
                         pdf_name=os.path.basename(self.pdf_path or ""), version=VERSION)
            ba = QtCore.QByteArray(); buf = QtCore.QBuffer(ba); buf.open(QtCore.QIODevice.WriteOnly)
            self.canvas.pixmap_item.pixmap().save(buf, "PNG")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("model.json", json.dumps(model)); z.writestr("page.png", bytes(ba))
                pdf_bytes = self._get_pdf_bytes()
                if pdf_bytes:
                    z.writestr("source.pdf", pdf_bytes)
            self.project_path = path; self._dirty = False; self._info(f"Proyecto guardado: {os.path.basename(path)}")
        finally: self._unbusy()

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
        tmp = getattr(self, '_tmp_pdf', None)
        if tmp and os.path.isfile(tmp):
            try: os.remove(tmp)
            except Exception: pass
        self._tmp_pdf = None

    def save_project(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, "Nada que guardar", "Abre un PDF o proyecto primero."); return
        if self.project_path: self._write_project(self.project_path)
        else: self.save_project_as()

    def save_project_as(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, "Nada que guardar", "Abre un PDF o proyecto primero."); return
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
            self._cleanup_tmp_pdf()
            with zipfile.ZipFile(path) as z:
                model = json.loads(z.read("model.json")); png = z.read("page.png")
                if "source.pdf" in z.namelist():
                    tmp_pdf = path + ".src.pdf"
                    with open(tmp_pdf, "wb") as fp: fp.write(z.read("source.pdf"))
                    self._tmp_pdf = tmp_pdf
                else:
                    tmp_pdf = None
            qimg = QtGui.QImage.fromData(png, "PNG")
            self._overlay = []; self._close_editor()
            self.canvas.set_image(qimg); self.gray = qimage_to_gray(qimg)
            tf = model["tf"]; self.scale = tf["scale"]; self.zoom = tf["zoom"]; self.rot = tf["rot"]
            self.W, self.H = tf["W"], tf["H"]; self.derot = fitz.Matrix(*tf["derot"])
            self.pageH_px = qimg.height()
            self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
            if tmp_pdf:
                self.pdf_path = tmp_pdf; self.doc = fitz.open(tmp_pdf)
            else:
                self.pdf_path = None; self.doc = None
            self.project_path = path; self.page_idx = 0
            self.pipes = model.get("pipes", []); self.leaders = model.get("leaders", [])
            self.text_marks = model.get("text_marks", [])
            self.erase_regions = [r if isinstance(r, dict) else {"pts": r, "enabled": True}
                                  for r in model.get("erase_regions", [])]
            self.structures = model.get("structures", [])   # retrocompat: proyectos viejos sin buzones
            self.georef = georef_mod.Georef.from_dict(model.get("georef"))   # retrocompat: sin georref → escala
            # Retrocompat de unidad: proyectos anteriores a 0.12 no guardan work_unit.
            # Si alguna pipe tenía unit="pulg"/"pies", elegimos la unidad más común
            # para el proyecto (por defecto "ft"). No convertimos los valores.
            wu = model.get("work_unit")
            if not is_valid_work_unit(wu):
                # Heurística: si más de la mitad de las pipes están en pulgadas, "in"; si no, "ft".
                pulg = sum(1 for p in self.pipes if str(p.get("unit", "")).lower().startswith("pulg"))
                wu = "in" if (self.pipes and pulg > len(self.pipes) / 2) else "ft"
            self.work_unit = wu
            # Anotamos el work_unit en cada pipe (uniforme: no per-pipe unit).
            for p in self.pipes: p["unit"] = self.work_unit
            self.cur_pts = []; self._erase_pts = []; self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
            self._undo.clear(); self._redo.clear(); self._dirty = False
            self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
            self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._redraw()
            self.lbl_scale.setText(f"Escala 1\"={self.scale*72:.0f}'"); self._update_geo_status()
            self._refresh_unit_labels()
            self._info(f"Proyecto abierto ({len(self.pipes)} utilidades). Ctrl+S guarda en este mismo archivo.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
        finally: self._unbusy()

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
        self._cleanup_tmp_pdf()
        self.canvas.scene().clear(); self.canvas.pixmap_item = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.gray = None
        self.pipes = []; self.leaders = []; self.text_marks = []; self.erase_regions = []; self.structures = []
        self.cur_pts = []; self._erase_pts = []; self._overlay = []; self._close_editor()
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
        self._undo.clear(); self._redo.clear(); self._dirty = False; self.show_text_boxes = False
        self.georef = georef_mod.Georef()
        for chk in (self.chk_txt, self.chk_icr):
            chk.blockSignals(True); chk.setChecked(False); chk.blockSignals(False)
        self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._info("Proyecto cerrado.")

    def closeEvent(self, e):
        if self._confirm_discard():
            self._cleanup_tmp_pdf(); e.accept()
        else: e.ignore()

    # ─────────────────────────── clics ───────────────────────────
    def on_click(self, x, y, button):
        if self.canvas.pixmap_item is None: return
        if self.show_text_boxes and button == QtCore.Qt.LeftButton and self._click_box(x, y): return
        if button == QtCore.Qt.RightButton:
            if self.mode == "pipe": self.finish_pipe()
            elif self.mode == "erase": self.finish_erase()
            elif self.mode == "move": self._delete_vertex(x, y)
            return
        if self.mode == "pipe":
            self._push(); self.cur_pts.append(self._snap(x, y)); self._update_ui(); self._redraw()
        elif self.mode == "erase":
            self._erase_pts.append((x, y)); self._update_ui(); self._redraw()
        elif self.mode == "text":
            if self._editor is not None: return   # el clic confirma el texto abierto (no abre otro)
            self._new_free_text(x, y)
        elif self.mode == "leader1":
            self._pending["arrow"] = self._snap(x, y); self.mode = "leader2"; self._update_ui()
        elif self.mode == "leader2":
            simple = bool(self._pending.get("simple"))
            if simple:
                hx, hy = self._pending["arrow"]; o = self.orient_combo.currentData()
                if o == "d":                                 # diagonal: 2º clic = inicio del landing (bisagra)
                    self._pending["landing"] = self._snap(x, y); self.mode = "leader3"; self._update_ui(); return
                tail = (x, hy) if o == "h" else (hx, y)      # h/v: 2º clic = final del cuerpo, recto al eje
                self._add_simple_leader((hx, hy), tail, o); return
            txt = self._read_leader_text()
            if not txt:
                self._info("Selecciona un texto (o activa 'texto personalizado') antes de colocar.")
                self._pending = {"arrow": None, "simple": False}
                self.mode = "leader1"; self._update_ui(); return
            self._push()
            self.leaders.append({"text": txt, "orient": self.orient_combo.currentData(),
                                 "simple": False,
                                 "arrow": self._pending["arrow"], "tp": (x, y),
                                 "font": self.font_combo.currentFont().family(),
                                 "size_ft": self.size_spin.value(), "bold": self.chk_bold.isChecked()})
            self._pending = {"arrow": None, "simple": False}; self.mode = "leader1"
            self._refresh_lists(); self._update_ui(); self._redraw()      # se ve al instante
            self._info("Multileader colocado. Clic en la PUNTA del siguiente (Esc para salir).")
        elif self.mode == "leader3":                         # Leader diagonal: 3er clic = final del cuerpo
            self._add_simple_leader(self._pending["arrow"], (x, y), "d",
                                    landing=self._pending.get("landing")); return
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
        self._info("Leader colocado. Clic en la cabeza de flecha del siguiente (Esc para salir).")

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
        for i, tm in enumerate(self.text_marks):        # textos primero (blancos pequeños)
            if self._text_hit(tm, x, y):
                self._no_center = True; self.tabs.setCurrentIndex(TAB_TEXT); self.txt_marks_list.setCurrentRow(i)
                self._no_center = False; return
        for i, ld in enumerate(self.leaders):           # leaders/multileaders: por la línea o el texto
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
        best, bd = -1, thr
        for i, p in enumerate(self.pipes):
            if not p.get("pts"): continue               # tramos importados (world) no están en el lienzo
            for a, b in zip(p["pts"], p["pts"][1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < bd: bd, best = d, i
        if best >= 0:
            self._no_center = True; self.tabs.setCurrentIndex(TAB_PIPE); self.pipe_list.setCurrentRow(best)
            self._no_center = False

    def _snap(self, x, y):
        if not self.snap: return (x, y)
        return G.snap_point(self.gray, x, y, self.snap_r)

    # ─────────────────────────── editar / mover ───────────────────────────
    def _current_kind(self):
        ti = self.tabs.currentIndex()
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
            self.set_mode("move"); self._info("Editar Leader: arrastra un vértice (posición/longitud) o el trazo para mover. Enter/Esc termina.")
        elif kind:
            self.set_mode("move"); self._info("Arrastra para mover · clic en vértice extiende (F) · clic derecho elimina")
        else:
            self._info("Selecciona primero una utilidad, Leader, texto o zona")

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
            self._info("Continuando la MISMA utilidad: clic para agregar puntos, Enter finaliza.")
        else:
            self._ext_pipe = None; self._ext_at = None
            if self.chk_ext_same.isChecked() and not is_end:
                self._info("Solo desde un extremo se continúa; se creará una utilidad NUEVA. Clic para agregar, Enter finaliza.")
            else:
                self._info("Utilidad NUEVA (rama en F): clic para agregar puntos, Enter finaliza.")
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
            self._push(); pts.pop(vi); self._refresh_lists(); self._redraw(); self._info("Vértice eliminado")

    # ─────────────────────────── utilidades ───────────────────────────
    def finish_pipe(self):
        if self._extending and self._ext_pipe is not None and 0 <= self._ext_pipe < len(self.pipes):
            extra = self.cur_pts[1:]                       # el 1er punto es el vértice existente
            if extra:
                self._push(); pts = self.pipes[self._ext_pipe]["pts"]
                if self._ext_at == "end": pts.extend(extra)
                else: self.pipes[self._ext_pipe]["pts"] = list(reversed(extra)) + pts
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
                mid = pts[len(pts) // 2]; self.canvas.centerOn(mid[0], mid[1])
            self._prop_guard = True
            self.prop_name.setText(p.get("name", ""))
            # Diámetro (pulg): buscar el tamaño exacto; si el proyecto es viejo y trae
            # un valor no estándar, seleccionar el estándar más cercano.
            di = self.prop_diam.findData(float(p.get("diam") or 0))
            if di < 0: di = self.prop_diam.findData(float(nearest_pipe_diameter(p.get("diam"))))
            self.prop_diam.setCurrentIndex(di if di >= 0 else 0)
            self.prop_part.setText(p.get("part", ""))
            self.prop_inv0.setValue(p.get("inv_start") or 0.0); self.prop_inv1.setValue(p.get("inv_end") or 0.0)
            mi = self.prop_material.findText(p.get("material") or DEFAULT_PIPE_MATERIAL)
            self.prop_material.setCurrentIndex(mi if mi >= 0 else 0)
            # findData busca el índice del combo cuya "data" (dato oculto) coincide
            # con "" | "pipe" | "pressure"; si no encuentra devuelve -1 → índice 0.
            idx = self.prop_nettype.findData(p.get("net_type", "") or "")
            self.prop_nettype.setCurrentIndex(idx if idx >= 0 else 0)
            self._prop_guard = False
        self._update_ui(); self._redraw()

    def _leader_at_row(self, lst, r):
        """Índice real en self.leaders del item de la fila r (o -1)."""
        it = lst.item(r) if r is not None and r >= 0 else None
        return it.data(QtCore.Qt.UserRole) if it is not None else -1

    def _sel_leader(self, r):                              # pestaña Multileaders
        """Al seleccionar un Multileader en el inventario derecho, abrimos la
        sección Multileader del acordeón izquierdo — así el usuario ve el
        estilo/orientación y puede editarlos."""
        i = self._leader_at_row(self.lead_list, r); self.sel_leader = i
        if 0 <= i < len(self.leaders):
            ld = self.leaders[i]
            if not self._no_center and ld.get("tp"): self.canvas.centerOn(ld["tp"][0], ld["tp"][1])
            self._open_section("ml")
            self._style_guard = True
            self.font_combo.setCurrentFont(QtGui.QFont(ld.get("font", C.TEXT_FONT)))
            self.size_spin.setValue(ld.get("size_ft", LEADER_TEXT_FT)); self.chk_bold.setChecked(bool(ld.get("bold")))
            self._style_guard = False
        self._update_ui(); self._redraw()

    def _sel_sleader(self, r):                             # pestaña Leaders (solo flechas)
        i = self._leader_at_row(self.sleader_list, r); self.sel_leader = i
        if 0 <= i < len(self.leaders):
            ld = self.leaders[i]
            if not self._no_center and ld.get("tp"): self.canvas.centerOn(ld["tp"][0], ld["tp"][1])
        self._update_ui(); self._redraw()

    def _select_leader(self, i, center=False):
        """Selecciona el leader nº i en la pestaña que le corresponde (ML o Leaders)."""
        if not (0 <= i < len(self.leaders)): return
        simple = self.leaders[i].get("simple")
        lst = self.sleader_list if simple else self.lead_list
        row = next((r for r in range(lst.count()) if lst.item(r).data(QtCore.Qt.UserRole) == i), -1)
        self._no_center = not center
        self.tabs.setCurrentIndex(TAB_LEADER if simple else TAB_ML); lst.setCurrentRow(row)
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
             - orient_combo → Multileader o Leader (según sección)
             - gtxt (estilo) → Multileader o Texto libre
             - rot_row visible solo en Texto libre
          3) Refrescamos la UI (etiqueta del modo, botones activos, etc.)."""
        # Descubrimos qué sección ("key") corresponde al índice.
        key = next((k for k, i in self._sec_idx.items() if i == idx), None)
        if self.mode not in ("idle",):
            self.set_mode("idle")
        if key == "ml":
            self._place_widget(self.orient_combo, self._slot_orient_ml)
            self._place_widget(self.gtxt, self._slot_style_ml)
            self.rot_row.setVisible(False)
        elif key == "leader":
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
        ti = self.tabs.currentIndex()
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            tm = self.text_marks[self.sel_text]; self._push()
            tm["font"] = self.font_combo.currentFont().family(); tm["size_ft"] = self.size_spin.value()
            tm["bold"] = self.chk_bold.isChecked(); tm["rot"] = self.rot_spin.value() % 360
            self._redraw()
        elif ti == TAB_ML and 0 <= self.sel_leader < len(self.leaders):
            ld = self.leaders[self.sel_leader]; self._push()
            ld["font"] = self.font_combo.currentFont().family(); ld["size_ft"] = self.size_spin.value()
            ld["bold"] = self.chk_bold.isChecked()
            self._redraw()

    def _prop_changed(self):
        """Callback: cualquier cambio en el panel Propiedades escribe al modelo.
        `self._push()` guarda un snapshot para Ctrl+Z (deshacer).
        La UNIDAD de diámetro/invert es la del proyecto (self.work_unit), no per-pipe."""
        if self._prop_guard: return
        if self.tabs.currentIndex() == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            p = self.pipes[self.sel_pipe]; self._push()
            p["name"] = self.prop_name.text().strip()
            p["diam"] = float(self.prop_diam.currentData() or 0)         # SIEMPRE en pulgadas
            p["diam_unit"] = "in"                                        # el diámetro nunca va en pies
            p["unit"] = self.work_unit                                  # unidad de trabajo (coords/cotas)
            p["part"] = self.prop_part.text().strip()
            p["inv_start"] = self.prop_inv0.value(); p["inv_end"] = self.prop_inv1.value()
            p["material"] = self.prop_material.currentText()
            # currentData devuelve el "dato oculto" del ítem seleccionado del combo
            # (asignado con addItem(texto, dato)). "" = auto; "pipe"/"pressure" = override.
            p["net_type"] = self.prop_nettype.currentData() or ""
            self._refresh_lists()

    # ────────── Unidad de trabajo (ft/in) — obligatoria para la red 3D ──────────
    def _on_unit_change(self, _idx):
        """El usuario cambió la unidad de trabajo en el combo de la barra.
        Recomputamos las etiquetas ("(ft)"/"(in)") pero NO reescalamos datos
        (el usuario debe ingresar los nuevos valores en la unidad activa)."""
        new_u = self.unit_combo.currentData()
        if not is_valid_work_unit(new_u) or new_u == self.work_unit: return
        self.work_unit = new_u; self._dirty = True
        self._refresh_unit_labels()
        self._info(f"Unidad de trabajo cambiada a '{new_u}'. Ingresa cotas y diámetros en esta unidad.")

    def _refresh_unit_labels(self):
        """Vuelve a escribir las etiquetas de UI que dependen de la unidad activa."""
        u = self.work_unit
        # El diámetro NO depende de la unidad de trabajo: siempre en pulgadas.
        if hasattr(self, "lbl_prop_diam"): self.lbl_prop_diam.setText("Diámetro (pulg):")
        if hasattr(self, "lbl_prop_inv0"): self.lbl_prop_inv0.setText(f"Invert inicio ({u}):")
        if hasattr(self, "lbl_prop_inv1"): self.lbl_prop_inv1.setText(f"Invert fin ({u}):")
        if hasattr(self, "lbl_unit"): self.lbl_unit.setText(f"Unidad: {u}")
        # Sincronizar el combo por si se llamó desde carga de proyecto (no del combo).
        if hasattr(self, "unit_combo"):
            i = self.unit_combo.findData(u)
            if i >= 0 and self.unit_combo.currentIndex() != i:
                self.unit_combo.blockSignals(True); self.unit_combo.setCurrentIndex(i); self.unit_combo.blockSignals(False)

    def change_pipe_type(self):
        if 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes[self.sel_pipe]["layer"] = self.active_layer()
            self.pipes[self.sel_pipe]["ab"] = self.chk_ab.isChecked(); self._refresh_lists(); self._redraw()

    def edit_selected_text(self):
        ti = self.tabs.currentIndex()
        if ti == TAB_ML and 0 <= self.sel_leader < len(self.leaders): self._edit_leader_text(self.sel_leader)
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._edit_text_mark(self.sel_text)

    def _list_context_menu(self, listw, tab_idx, pos):
        item = listw.itemAt(pos)
        if item is None: return
        if self.tabs.currentIndex() != tab_idx: self.tabs.setCurrentIndex(tab_idx)
        listw.setCurrentRow(listw.row(item))          # selecciona la fila bajo el cursor
        menu = QtWidgets.QMenu(self)
        if tab_idx == TAB_PIPE:
            self._menu_act(menu, "Cambiar tipo", self.change_pipe_type)
            self._menu_act(menu, "Editar/mover", self.enter_move)
        elif tab_idx == TAB_ML:
            self._menu_act(menu, "Editar texto", self.edit_selected_text)
        elif tab_idx == TAB_LEADER:
            self._menu_act(menu, "Editar/mover", self.enter_move)
        elif tab_idx == TAB_TEXT:
            self._menu_act(menu, "Mover", self.enter_move)
            self._menu_act(menu, "Editar texto", self.edit_selected_text)
        elif tab_idx == TAB_REGION:
            self._menu_act(menu, "Editar/mover", self.enter_move)
        menu.addSeparator()
        self._menu_act(menu, "Eliminar", self.delete_selected)
        menu.exec(listw.viewport().mapToGlobal(pos))

    def delete_selected(self):
        ti = self.tabs.currentIndex()
        if ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes.pop(self.sel_pipe); self.sel_pipe = -1
        elif ti in (TAB_ML, TAB_LEADER) and 0 <= self.sel_leader < len(self.leaders):
            self._push(); self.leaders.pop(self.sel_leader); self.sel_leader = -1
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            self._push(); self.text_marks.pop(self.sel_text); self.sel_text = -1
        elif ti == TAB_REGION and 0 <= self.sel_region < len(self.erase_regions):
            self._push(); self.erase_regions.pop(self.sel_region); self.sel_region = -1
        self._refresh_lists(); self._redraw()

    def _copy_sel(self):
        ti = self.tabs.currentIndex()
        if ti in (TAB_ML, TAB_LEADER) and 0 <= self.sel_leader < len(self.leaders): self._clip = ("leader", copy.deepcopy(self.leaders[self.sel_leader]))
        elif ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes): self._clip = ("pipe", copy.deepcopy(self.pipes[self.sel_pipe]))
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._clip = ("text", copy.deepcopy(self.text_marks[self.sel_text]))
        else: self._info("Selecciona algo para copiar."); return
        self._info("Copiado. Ctrl+V para pegar una copia.")

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
            self.tabs.setCurrentIndex(TAB_PIPE); self._refresh_lists(); self.pipe_list.setCurrentRow(len(self.pipes) - 1)
        elif kind == "text":
            o["pos"] = (o["pos"][0] + d, o["pos"][1] + d); self.text_marks.append(o)
            self.tabs.setCurrentIndex(TAB_TEXT); self._refresh_lists(); self.txt_marks_list.setCurrentRow(len(self.text_marks) - 1)
        self._redraw(); self._info("Pegado (copia desplazada).")

    def _refresh_lists(self):
        self.pipe_list.blockSignals(True); self.pipe_list.clear()
        for i, p in enumerate(self.pipes, 1):
            tag = " (AB)" if p.get("ab") else ""
            nm = f" · {p['name']}" if p.get("name") else ""
            n = len(p.get("pts") or [])
            info = f"red:{p.get('net', '')}" if p.get("world") else str(n)
            it = QtWidgets.QListWidgetItem(swatch_icon(layer_qcolor(p["layer"])), f"{i}. {p['layer']}{tag}{nm} ({info})")
            it.setForeground(QtGui.QColor("white")); self.pipe_list.addItem(it)
        self.pipe_list.blockSignals(False)
        self.lead_list.blockSignals(True); self.lead_list.clear()
        self.sleader_list.blockSignals(True); self.sleader_list.clear()
        nml = ns = 0
        for i, ld in enumerate(self.leaders):
            if ld.get("simple"):
                ns += 1; o = {"h": "horizontal", "v": "vertical", "d": "diagonal"}.get(ld.get("orient", "d"), "")
                it = QtWidgets.QListWidgetItem(f"{ns}. Leader {o}".rstrip())
                it.setData(QtCore.Qt.UserRole, i); self.sleader_list.addItem(it)
            else:
                nml += 1; it = QtWidgets.QListWidgetItem(f"{nml}. {ld['text'][:24].replace(chr(10), ' / ')}")
                it.setData(QtCore.Qt.UserRole, i); self.lead_list.addItem(it)
        self.lead_list.blockSignals(False); self.sleader_list.blockSignals(False)
        self.txt_marks_list.blockSignals(True); self.txt_marks_list.clear()
        for i, tm in enumerate(self.text_marks, 1): self.txt_marks_list.addItem(f"{i}. {tm['text'][:28].replace(chr(10), ' / ')}")
        self.txt_marks_list.blockSignals(False)
        self.region_list.blockSignals(True); self.region_list.clear()
        for i, rg in enumerate(self.erase_regions, 1):
            it = QtWidgets.QListWidgetItem(f"Zona {i} ({len(rg['pts'])} vértices)")
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if rg.get("enabled", True) else QtCore.Qt.Unchecked)
            it.setForeground(QtGui.QColor("white")); self.region_list.addItem(it)
        self.region_list.blockSignals(False)

    # ─────────────────────────── borrar zona ───────────────────────────
    def finish_erase(self):
        if len(self._erase_pts) < 3: return
        self._push(); poly = self._erase_pts[:]; self.erase_regions.append({"pts": poly, "enabled": True})
        self.pipes = [p for p in self.pipes if not (p.get("pts") and all(point_in_poly(px, py, poly) for (px, py) in p["pts"]))]
        self.leaders = [l for l in self.leaders if not (l.get("tp") and point_in_poly(l["tp"][0], l["tp"][1], poly))]
        self.text_marks = [t for t in self.text_marks if not point_in_poly(t["pos"][0], t["pos"][1], poly)]
        self._erase_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info("Zona agregada: al exportar también se borra la geometría base del plano dentro de ella.")

    # ─────────────────────────── Multileader ───────────────────────────
    def _read_leader_text(self):
        if self.chk_custom.isChecked(): return self.txt_edit.text().strip()
        it = self.text_list.currentItem()
        return it.text() if it and self.text_list.currentRow() >= 0 else ""

    def start_leader(self, simple=False):
        """Entra al modo de colocación (Multileader o Leader). No se captura la
        orientación aquí: se lee de `orient_combo` AL MOMENTO del clic final,
        para que el usuario pueda cambiarla dentro del modo."""
        self._pending = {"arrow": None, "simple": bool(simple)}
        # Abrimos la sección correcta del acordeón según el tipo de leader
        self._open_section("leader" if simple else "ml")
        self.set_mode("leader1")
        if simple:
            if self.orient_combo.currentData() == "d":
                self._info("Leader diagonal: cabeza → inicio del landing (bisagra) → final del cuerpo. Enter/Esc para salir.")
            else:
                self._info("Leader: cabeza de flecha → final del cuerpo. Enter/Esc para salir.")
        else:
            self._info("Multileader: elige el texto; clic en la PUNTA y luego dónde va el TEXTO. Esc para salir.")

    def _edit_leader_text(self, idx):
        ld = self.leaders[idx]; tp = ld["tp"]
        if ld.get("simple"):                                 # el Leader simple no tiene texto que editar
            self._info("El Leader simple no lleva texto."); return
        def commit(val):
            self._close_editor()
            if val.strip(): self._push(); ld["text"] = val.rstrip("\n"); self._refresh_lists()
            self._redraw()
        self._open_editor(tp[0], tp[1] - self.leader_hpx, ld["text"], commit)

    def _leader_geo(self, ld):
        """Geometría del Multileader (px). La 'cola' (parte de la línea junto al texto)
        se adapta al largo del texto. La punta se orienta con segs[0][1]."""
        ax, ay = ld["arrow"]; tx, ty = ld["tp"]
        ftsize = ld.get("size_ft", LEADER_TEXT_FT)
        H = self._px_for_ft(ftsize)
        lines = ld["text"].split("\n"); maxlen = max((len(s) for s in lines), default=1); nlines = len(lines)
        tw = max(maxlen * H * 0.6, H * 2); th = nlines * H; gap = H * 0.5; near = H * 0.22
        if ld.get("simple"):                               # LEADER simple: solo flecha, sin texto
            lp = ld.get("landing")
            if lp:                                         # diagonal con landing: cabeza → bisagra → final
                segs = [[(ax, ay), (lp[0], lp[1]), (tx, ty)]]
            else:                                          # recto h/v: cabeza → final del cuerpo
                segs = [[(ax, ay), (tx, ty)]]
            end = segs[0][-1]
            return dict(segs=segs, label_pos=end, rot=0, side="right", verts_px=segs[0], insert_px=end,
                        dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=end, cad_rot=0)
        orient = ld.get("orient", "h")
        if orient == "v":                                  # recto vertical; texto vertical junto a la cola
            signY = -1 if ty < ay else 1
            L = max(abs(ty - ay), tw + gap); ey = ay + signY * L; my = (ay + ey) / 2
            side = "top" if signY < 0 else "bottom"
            lbl = (ax + H * 0.08, my + tw / 2)              # rot -90, centrado a lo largo, pegado a la línea
            segs = [[(ax, ay), (ax, ey)]]
            return dict(segs=segs, label_pos=lbl, rot=-90, side=side, verts_px=segs[0], insert_px=(ax, ey),
                        dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=(ax + th / 2 + H * 0.08, my), cad_rot=90)
        if orient == "h":                                  # recto horizontal; texto encima de la cola
            signX = 1 if tx >= ax else -1
            L = max(abs(tx - ax), tw + gap); ex = ax + signX * L
            lblx = ex - tw if signX > 0 else ex
            side = "right" if signX > 0 else "left"
            segs = [[(ax, ay), (ex, ay)]]
            return dict(segs=segs, label_pos=(lblx, ay - th - near), rot=0, side=side, verts_px=segs[0], insert_px=(ex, ay),
                        dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=(lblx + tw / 2, ay - near - th / 2), cad_rot=0)
        # diagonal: flecha → 2º clic → landing horizontal → texto encima del landing
        right = tx >= ax; sgn = 1 if right else -1
        lx = tx + sgn * (tw + gap); text_x = min(tx, lx) + gap
        side = "right" if right else "left"
        lbl = (text_x, ty - H - near)                      # 1ª línea encima; extras al otro lado
        segs = [[(ax, ay), (tx, ty), (lx, ty)]]
        return dict(segs=segs, label_pos=lbl, rot=0, side=side, verts_px=segs[0], insert_px=(lx, ty),
                    dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=(text_x + tw / 2, ty - H - near + th / 2), cad_rot=0)

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

    # ─────────────────────────── OCR / ICR ───────────────────────────
    def _sync_boxes(self):
        self.ocr_boxes = self._tess_boxes + self._icr_boxes
        self.show_text_boxes = self.chk_txt.isChecked() or self.chk_icr.isChecked()
        self._redraw()

    def toggle_text_boxes(self, on):
        if on and not self._tess_boxes and self.gray is not None:
            self._prog = QtWidgets.QProgressDialog("Detectando texto impreso (0/90/270°)…", None, 0, 0, self)
            self._prog.setWindowTitle("OCR"); self._prog.setWindowModality(QtCore.Qt.WindowModal)
            self._prog.setCancelButton(None); self._prog.show()
            self._ocr = OcrWorker(self.gray); self._ocr.done.connect(self._ocr_done); self._ocr.start()
        else: self._sync_boxes()

    def _ocr_done(self, boxes, err):
        if getattr(self, "_prog", None): self._prog.close()
        if err: self._info(f"OCR no disponible: {err}"); return
        self._tess_boxes = [(QtCore.QRectF(x, y, w, h), t) for (x, y, w, h, t) in boxes]
        self._info(f"{len(self._tess_boxes)} zonas de texto impreso. Clic en una para corregirla."); self._sync_boxes()

    def toggle_icr(self, on):
        if on and not self._icr_boxes and self.gray is not None:
            self._prog = QtWidgets.QProgressDialog("Reconociendo manuscrita (EasyOCR)…\n"
                                                   "La 1ª vez descarga el modelo, puede tardar.", None, 0, 0, self)
            self._prog.setWindowTitle("ICR"); self._prog.setWindowModality(QtCore.Qt.WindowModal)
            self._prog.setCancelButton(None); self._prog.show()
            self._icr = IcrWorker(self.gray); self._icr.done.connect(self._icr_done); self._icr.start()
        else: self._sync_boxes()

    def _icr_done(self, boxes, err):
        if getattr(self, "_prog", None): self._prog.close()
        if err == "missing":
            self.chk_icr.blockSignals(True); self.chk_icr.setChecked(False); self.chk_icr.blockSignals(False)
            QtWidgets.QMessageBox.information(self, "EasyOCR no instalado",
                "Para la ICR manuscrita (offline) instala EasyOCR con tu Python 3.12:\n\n"
                r'C:\Users\Deyvy\AppData\Local\Programs\Python\Python312\python.exe -m pip install easyocr'
                "\n\nLa primera vez descargará el modelo (~100 MB) automáticamente.")
            return
        if err:
            self.chk_icr.blockSignals(True); self.chk_icr.setChecked(False); self.chk_icr.blockSignals(False)
            self._info(f"ICR no disponible: {err}"); return
        self._icr_boxes = [(QtCore.QRectF(x, y, w, h), t) for (x, y, w, h, t) in boxes]
        self._info(f"{len(self._icr_boxes)} zonas manuscritas. Clic en una para corregirla."); self._sync_boxes()

    def _click_box(self, x, y):
        for rect, txt in self.ocr_boxes:
            if rect.contains(x, y):
                def commit(val):
                    self._close_editor()
                    if val.strip():
                        self._push()
                        self.text_marks.append({"pos": (rect.center().x(), rect.center().y()), "text": val.rstrip("\n"),
                                                "h": rect.height(), "box": (rect.x(), rect.y(), rect.width(), rect.height())})
                        self._refresh_lists()
                    self._redraw()
                self._open_editor(rect.x(), rect.y(), txt, commit, max(160, int(rect.width())))
                return True
        return False

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
        for i, rg in enumerate(self.erase_regions):
            qp = QtGui.QPolygonF([QtCore.QPointF(px, py) for (px, py) in rg["pts"]])
            enabled = rg.get("enabled", True); sel = (i == self.sel_region)
            if not enabled:
                pen = QtGui.QPen(QtGui.QColor(150, 150, 150), 1.2, QtCore.Qt.DashLine); brush = QtGui.QBrush(QtGui.QColor(200, 200, 200, 30))
            elif sel:
                pen = QtGui.QPen(QtGui.QColor(255, 40, 40), 2.0); brush = QtGui.QBrush(QtGui.QColor(255, 255, 255, 128))
            else:
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.6); brush = QtGui.QBrush(QtGui.QColor(255, 255, 255, 255))
            pen.setCosmetic(True); it = sc.addPolygon(qp, pen, brush); it.setZValue(Z_ERASE); self._overlay.append(it)
            if sel and self.mode == "move": self._handles(rg["pts"])
        # utilidades
        for i, p in enumerate(self.pipes):
            if not p.get("pts"): continue               # tramos importados (world): no se dibujan
            sel = (i == self.sel_pipe)
            self._poly(p["pts"], layer_qcolor(p["layer"]), 4.0 if sel else 2.0, z=Z_MARK)
            if sel and self.mode == "move": self._handles(p["pts"])
        self._poly(self.cur_pts, layer_qcolor(self._ext_layer or self.active_layer()), 2.0, dots=True, z=Z_MARK)
        # multileaders
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
        # cajas OCR/ICR
        if self.show_text_boxes:
            pen = QtGui.QPen(QtGui.QColor(255, 200, 0), 1); pen.setCosmetic(True)
            for rect, _ in self.ocr_boxes:
                it = sc.addRect(rect, pen); it.setZValue(Z_MARK); self._overlay.append(it)
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
            if i == self.sel_text and self.tabs.currentIndex() == TAB_TEXT:
                br = t.boundingRect(); pen = QtGui.QPen(QtGui.QColor(255, 180, 40)); pen.setCosmetic(True)
                rit = sc.addRect(tm["pos"][0], tm["pos"][1], br.width(), br.height(), pen); rit.setZValue(Z_MARK); self._overlay.append(rit)

    def _handles(self, pts):
        sc = self.canvas.scene(); pen = QtGui.QPen(QtGui.QColor(255, 255, 255)); pen.setCosmetic(True)
        for (vx, vy) in pts:
            it = sc.addRect(vx - 5, vy - 5, 10, 10, pen, QtGui.QBrush(QtGui.QColor(255, 180, 40)))
            it.setZValue(Z_HANDLE); self._overlay.append(it)

    def _poly(self, pts, color, width, dots=False, z=Z_MARK):
        sc = self.canvas.scene(); pen = QtGui.QPen(color, width); pen.setCosmetic(True)
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

    # ─────────────────────────── exportar ───────────────────────────
    def run_pipeline(self, mode="todo"):
        """mode: 'todo' = PDF digitalizado + anotaciones · 'pdf' = solo el PDF ·
        'anot' = solo las anotaciones dibujadas en el programa."""
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, "Nada", "Abre un PDF o proyecto."); return
        need_pdf = mode in ("todo", "pdf")
        if need_pdf and (not self.pdf_path or not os.path.isfile(self.pdf_path)):
            QtWidgets.QMessageBox.information(self, "Sin PDF",
                "No se encontró el PDF original. Se exportarán solo las anotaciones (utilidades, leaders, textos).")
            mode = "anot"; need_pdf = False
        base = os.path.splitext(os.path.basename(self.pdf_path))[0] if self.pdf_path else "proyecto"
        suffix = {"todo": "_completo", "pdf": "_plano", "anot": "_anotaciones"}[mode]
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar DXF", os.path.join(DOWNLOADS, base + suffix + ".dxf"), "DXF (*.dxf)")
        if not out: return
        self._out = out; self._mode = mode
        if not need_pdf:                                   # solo anotaciones: sin pipeline
            try:
                doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
                self._merge_into(doc, marks=True); doc.saveas(out)
                QtWidgets.QMessageBox.information(self, "Listo", f"Exportado (solo anotaciones):\n{out}")
                self._info("DXF de anotaciones exportado.")
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
            self._merge_into(doc, marks=marks); doc.saveas(self._out)
            if os.path.exists(tmp): os.remove(tmp)
            if marks:
                nreg = sum(1 for r in self.erase_regions if r.get("enabled", True))
                msg = (f"Exportado (PDF + anotaciones):\n{self._out}\n\n{len(self.pipes)} utilidades, "
                       f"{len(self.leaders)} leaders/multileaders, {len(self.text_marks)} textos, {nreg} zonas borradas.")
            else:
                msg = f"Exportado (solo el PDF digitalizado):\n{self._out}"
            QtWidgets.QMessageBox.information(self, "Listo", msg); self._info("DXF exportado.")
        except Exception as e:
            import traceback; QtWidgets.QMessageBox.critical(self, "Error al guardar", f"{e}\n{traceback.format_exc()}")

    def _merge_into(self, doc, marks=True):
        dxf_export.merge_into(self, doc, marks=marks)

    # ─────────────────────────── Red 3D: buzones / cotas ───────────────────────────
    def _rebuild_structures(self):
        """Detecta buzones por los EXTREMOS de las tuberías de gravedad dibujadas.
        Extremos compartidos (misma coord, con tolerancia) = un solo buzón. Preserva
        las ediciones (cod/rim/sump/part) por coincidencia de coordenada. Los buzones
        importados de Excel (world) se conservan aparte."""
        tol = 14.0
        def near(a, b): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
        old = [s for s in self.structures if not s.get("world")]
        world = [s for s in self.structures if s.get("world")]
        detected = []
        for p in self.pipes:
            if p.get("world") or p.get("layer") not in GRAVITY_LAYERS: continue
            pts = p.get("pts")
            if not pts or len(pts) < 2: continue
            for pt in pts:                              # todos los vértices (extremos + intermedios)
                if not any(near(pt, (s["x"], s["y"])) for s in detected):
                    detected.append({"cod": "", "x": pt[0], "y": pt[1], "rim": None,
                                     "sump": None, "part": "", "net": "", "world": False})
        for s in detected:                                 # reasigna ediciones previas por coordenada
            for o in old:
                if near((s["x"], s["y"]), (o.get("x", -1e9), o.get("y", -1e9))):
                    s.update(cod=o.get("cod", ""), rim=o.get("rim"), sump=o.get("sump"),
                             part=o.get("part", ""), net=o.get("net", "")); break
        n = 1
        for s in detected:
            if not s["cod"]: s["cod"] = f"BZ-{n}"; n += 1
        self.structures = world + detected; self._dirty = True

    def manage_structures(self):
        self._rebuild_structures()
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Buzones / nudos"); dlg.resize(580, 440)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(QtWidgets.QLabel("Buzones detectados por los extremos de las tuberías de gravedad "
                                       "(extremos compartidos = un mismo buzón). Edita Cod, rim (tapa), sump (fondo) y part."))
        tbl = QtWidgets.QTableWidget(len(self.structures), 5)
        tbl.setHorizontalHeaderLabels(["Cod", f"rim ({self.work_unit})", f"sump ({self.work_unit})", "part", "origen"])
        tbl.horizontalHeader().setStretchLastSection(True)
        def setc(r, c, text, editable=True):
            it = QtWidgets.QTableWidgetItem("" if text is None else str(text))
            if not editable: it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
            tbl.setItem(r, c, it)
        for r, s in enumerate(self.structures):
            setc(r, 0, s.get("cod", "")); setc(r, 1, s.get("rim")); setc(r, 2, s.get("sump"))
            setc(r, 3, s.get("part", "")); setc(r, 4, "Excel" if s.get("world") else "dibujo", editable=False)
        lay.addWidget(tbl)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted: return
        def fnum(t):
            try: return float(t)
            except (TypeError, ValueError): return None
        self._push()
        for r, s in enumerate(self.structures):
            if tbl.item(r, 0): s["cod"] = tbl.item(r, 0).text().strip()
            s["rim"] = fnum(tbl.item(r, 1).text() if tbl.item(r, 1) else None)
            s["sump"] = fnum(tbl.item(r, 2).text() if tbl.item(r, 2) else None)
            if tbl.item(r, 3): s["part"] = tbl.item(r, 3).text().strip()
        self._info(f"{len(self.structures)} buzones guardados.")

    def import_network_excel(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Importar Excel de red", DOWNLOADS, "Excel (*.xlsx *.xlsm)")
        if not path: return
        self._busy("Leyendo Excel de red…")
        try:
            nets, warns = excel_import.read_network_workbook(path)
        except Exception as e:
            self._unbusy(); QtWidgets.QMessageBox.critical(self, "Error al leer Excel", str(e)); return
        self._unbusy(); self._push()
        # reemplaza lo importado previamente (world); conserva lo dibujado
        self.structures = [s for s in self.structures if not s.get("world")]
        self.pipes = [p for p in self.pipes if not p.get("world")]
        n_s = n_p = 0
        # El Excel del cliente viene en METROS (estándar topográfico); pasamos
        # coordenadas, cotas y diámetros a la unidad de trabajo del proyecto
        # (ft o in) para que TODO en el modelo esté en la misma unidad que el JSON.
        u = self.work_unit
        def to_u(v): return G.convert_length(v, "m", u)
        for name, nd in nets.items():
            for s in nd["structures"]:
                self.structures.append({
                    "cod": s["cod"], "x": to_u(s["x"]), "y": to_u(s["y"]),
                    "rim": to_u(s["rim"]), "sump": to_u(s["sump"]),
                    "part": s["part"], "net": name, "world": True}); n_s += 1
            for pp in nd["pipes"]:
                self.pipes.append({
                    "layer": "ALCANTARILLADO", "pts": [], "world": True, "net": name,
                    "wstart": (to_u(pp["xi"]), to_u(pp["yi"])),
                    "wend":   (to_u(pp["xf"]), to_u(pp["yf"])),
                    "from": pp["from"], "to": pp["to"], "id": pp["id"], "name": pp["id"],
                    "inv_start": to_u(pp["zi"]), "inv_end": to_u(pp["zf"]),
                    "diam": to_u(pp["diam"]) or 0.0, "unit": u,
                    "part": pp["part"]}); n_p += 1
        self._refresh_lists(); self._redraw()
        msg = f"Importado: {len(nets)} red(es), {n_s} buzones, {n_p} tuberías."
        if warns: msg += "\n\nAvisos:\n- " + "\n- ".join(warns[:12])
        QtWidgets.QMessageBox.information(self, "Importación de red", msg); self._info(msg.split(chr(10))[0])

    def export_network_json(self):
        # Al menos alguna tubería con geometría (dibujada o importada)
        if not any(p.get("pts") or (p.get("world") and p.get("wstart") and p.get("wend"))
                   for p in self.pipes):
            QtWidgets.QMessageBox.information(self, "Nada que exportar",
                "No hay tuberías. Dibuja alguna o importa un Excel de red."); return
        # Antes de exportar, refrescar los buzones detectados desde los vértices dibujados
        self._rebuild_structures()
        base = os.path.splitext(os.path.basename(self.pdf_path))[0] if self.pdf_path else "red"
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar red 3D (JSON)",
                                                       os.path.join(DOWNLOADS, base + ".network.json"), "JSON (*.json)")
        if not out: return
        try:
            path, warns = write_network_json(self, out)
        except Exception as e:
            import traceback; QtWidgets.QMessageBox.critical(self, "Error", f"{e}\n{traceback.format_exc()}"); return
        if not path:
            QtWidgets.QMessageBox.information(self, "Nada que exportar", warns[0] if warns else "Sin redes."); return
        msg = f"Red exportada (utility-network/3.0):\n{path}"
        if not self.georef.active():
            msg += ("\n\nAviso: el plano NO está georreferenciado; las coordenadas x,y no coinciden "
                    "con datos UTM externos. Usa Georreferencia → Georreferenciar… para calzarlo.")
        if warns: msg += "\n\nAvisos (no bloqueantes):\n- " + "\n- ".join(warns[:15])
        QtWidgets.QMessageBox.information(self, "Exportar red 3D (JSON)", msg); self._info("JSON de red exportado.")

    # ─────────────────────────── Georreferenciación ───────────────────────────
    def clear_georef(self):
        if not self.georef.active():
            self._info("El plano no está georreferenciado."); return
        self._dirty = True; self.georef = georef_mod.Georef()
        self._update_geo_status(); self._info("Georreferencia quitada; se usa la escala del titleblock.")

    def open_georef(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, "Sin plano", "Abre un PDF o proyecto primero."); return
        try:
            from geo.georef_dialog import GeorefDialog
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Falta un componente",
                "La georreferenciación necesita PySide6-WebEngine, pyproj y scikit-image.\n\n"
                "Instálalos con tu Python 3.12:\n"
                r"  C:\Users\Deyvy\AppData\Local\Programs\Python\Python312\python.exe -m pip install "
                "PySide6-WebEngine pyproj scikit-image" f"\n\nDetalle: {e}")
            return
        img = self.canvas.pixmap_item.pixmap().toImage()
        dlg = GeorefDialog(self, img, self.georef)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_georef is not None:
            self.georef = dlg.result_georef; self._dirty = True
            self._update_geo_status(); self._redraw()
            rms = self.georef.rms if self.georef.rms is not None else 0.0
            self._info(f"Georreferenciado (EPSG:{self.georef.epsg}, RMS {rms:.2f} m). "
                       "Las coordenadas exportadas ahora son UTM reales (aproximadas).")

    # ─────────────────────────── Excel ───────────────────────────
    def open_excel(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir Excel", DOWNLOADS, "Excel (*.xlsx *.xlsm)")
        if path: self._read_excel(path)

    def _read_excel(self, path):
        self._busy("Leyendo Excel…")
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True); texts = []
            for ws in wb.worksheets:
                try:
                    hc = hr = None
                    for row in ws.iter_rows():
                        for cell in row:
                            if cell.value is not None and str(cell.value).strip().upper() in ("TEXTO", "TEXTOS"):
                                hc, hr = cell.column, cell.row; break
                        if hc: break
                    if hc is None: continue
                    for row in ws.iter_rows(min_row=hr + 1, min_col=hc, max_col=hc):
                        val = row[0].value
                        if val is not None and str(val).strip(): texts.append(str(val).strip())
                except Exception: continue
            self.text_list.clear(); self.text_list.addItems(texts)
            self._info(f"Excel: {len(texts)} textos de la columna TEXTO." if texts else "No hallé columna TEXTO/TEXTOS.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error al leer Excel", str(e))
        finally: self._unbusy()

    # ─────────────────────────── Ayuda ───────────────────────────
    def _show_html(self, title, html, w=780, h=660):
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle(title); dlg.resize(w, h)
        lay = QtWidgets.QVBoxLayout(dlg); tb = QtWidgets.QTextBrowser(); tb.setOpenExternalLinks(True)
        tb.setStyleSheet("background:#1e1e1e;color:#e8e8e8;font-size:14px;"); tb.setHtml(html)
        btn = QtWidgets.QPushButton("Cerrar"); btn.clicked.connect(dlg.accept)
        lay.addWidget(tb); lay.addWidget(btn); dlg.exec()

    def show_about(self):
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Acerca de"); dlg.resize(760, 680)
        lay = QtWidgets.QVBoxLayout(dlg)
        head = QtWidgets.QLabel(
            f"<h2>Digitalizador de planos — utilidades</h2>"
            f"<p><b>Versión {VERSION}</b> · para ingeniería civil (agua, alcantarillado, gas, "
            f"eléctrico, telefonía, drenaje).</p>"
            f"<p>Convierte un PDF de plano a DXF y te deja marcar utilidades, Multileaders y notas "
            f"sobre la imagen, exportando todo en las mismas coordenadas.</p>"
            f"<p style='color:#888;'>Historial de versiones (la más reciente arriba, la más antigua "
            f"abajo). Haz clic en cada versión para desplegarla.</p>")
        head.setWordWrap(True); head.setStyleSheet("color:#e8e8e8;"); lay.addWidget(head)
        box = QtWidgets.QToolBox()
        box.setStyleSheet("QToolBox::tab{background:#333;color:#ddd;border:1px solid #555;}"
                          "QToolBox::tab:selected{background:#3c5a99;color:white;font-weight:bold;}")
        icon = {"added": ("#5fd35f", "✚ nueva"), "removed": ("#e06060", "✖ quitada"),
                "fixed": ("#6cc5e0", "✎ corregida"), "changed": ("#e0c060", "↻ cambiada"),
                "base": ("#cfcfcf", "•")}
        default = ("#cfcfcf", "•")
        for ver, items in CHANGELOG:
            tb = QtWidgets.QTextBrowser(); tb.setStyleSheet("background:#1e1e1e;color:#e8e8e8;border:none;")
            lis = "".join(f'<li style="color:{icon.get(s, default)[0]};margin-bottom:4px;">'
                          f'<b>[{icon.get(s, default)[1]}]</b> {t}</li>' for s, t in items)
            tb.setHtml(f"<ul>{lis}</ul>"); box.addItem(tb, f"v{ver}")
        lay.addWidget(box, 1)
        btn = QtWidgets.QPushButton("Cerrar"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
        dlg.exec()

    def show_manual(self):
        """Ventana del manual de usuario. Es HTML sencillo dentro de un
        QTextBrowser (visor de texto enriquecido); nada de red ni servidor."""
        html = """
        <h2>Manual de usuario</h2>
        <p><i>Esta aplicación te permite marcar sobre un plano PDF (agua, alcantarillado,
        drenaje, gas, eléctrico, telefonía) y exportar el resultado a AutoCAD (DXF) y/o
        a un archivo JSON con la red 3D para Civil 3D. Está pensada para ingeniería civil.</i></p>

        <h3>0. Disposición de la ventana</h3>
        <ul>
          <li><b>Barra superior (menús):</b> Archivo · Edición · Georreferencia · Ayuda. Y una
              fila con Zoom, Deshacer/Rehacer, Imán al trazo, y el botón <b>Exportar DXF ▾</b>.</li>
          <li><b>Panel izquierdo (acordeón):</b> una sección por herramienta. Al abrir una
              sección solo se ven las opciones de ESA herramienta (evita confusión).</li>
          <li><b>Lienzo central:</b> el plano.</li>
          <li><b>Panel derecho (Inventario):</b> lo que has marcado (Utilidades, Multileaders,
              Leaders, Textos, Zonas). Debajo, <b>Propiedades</b> de la utilidad seleccionada.</li>
          <li><b>Barra de estado (inferior):</b> modo actual · coordenadas del cursor · escala ·
              estado de imán · estado de georreferenciación.</li>
        </ul>

        <h3>1. Abrir el plano y navegar</h3>
        <ol>
          <li><b>Archivo → Abrir PDF…</b> (o arrastra el PDF a la ventana).</li>
          <li>En la sección <b>Vista y páginas</b> del acordeón izquierdo:
              <ul>
                <li>Cambia de página con <b>◀ ▶</b> o escribe el número y pulsa Enter.</li>
                <li>Ajusta la <b>Transparencia del PDF</b> con − / + para ver mejor tu marcado
                    (útil sobre planos oscuros o muy densos).</li>
              </ul>
          </li>
          <li>Con la rueda haces <b>zoom</b>; con el botón central arrastras (pan).</li>
        </ol>

        <h3>2. Dibujar una utilidad (tubería / línea)</h3>
        <p>En el acordeón, abre la sección <b>✏ Dibujar utilidad</b>.</p>
        <ol>
          <li>Elige el <b>Tipo de utilidad</b> en el desplegable (cada tipo tiene su color).</li>
          <li>Marca <b>Abandonado</b> si la línea está fuera de servicio (linetype ──/── W ──).</li>
          <li>Pulsa <b>✏ Dibujar utilidad</b> (el botón se pone verde = modo activo).</li>
          <li>Haz clic en el plano punto por punto para definir la polilínea.</li>
          <li>Termina con <b>Enter</b>, clic derecho o doble clic.</li>
        </ol>
        <p><b>Extender un extremo:</b> con una utilidad seleccionada, pulsa <b>Editar/mover</b>
        (Ctrl+T) y haz un clic BREVE (sin arrastrar) sobre un vértice de extremo. Si la casilla
        <b>Al extender un extremo: continuar la misma utilidad</b> está marcada, la nueva línea
        prolonga la existente; si no, crea una rama nueva (forma de F).</p>

        <h3>3. Propiedades de la utilidad (para exportar a la red 3D)</h3>
        <p>Cuando seleccionas una utilidad en el inventario (panel derecho), aparecen sus
        <b>Propiedades</b>:</p>
        <ul>
          <li><b>Nombre:</b> identificador libre (ej. "SD-A-01").</li>
          <li><b>Diámetro y Unidad:</b> valor numérico y unidad (pulg / pies).</li>
          <li><b>Material:</b> texto libre (ej. "HDPE", "PVC", "Concreto").</li>
          <li><b>Tipo de red:</b>
              <ul>
                <li><i>Automático</i> — lo decide la capa (agua/gas → presión; el resto → con buzones).</li>
                <li><i>Con buzones (pipe)</i> — fuerza red por gravedad con buzones.</li>
                <li><i>A presión (pressure)</i> — fuerza línea a presión (sin buzones).</li>
              </ul>
          </li>
          <li><b>Invert inicio / Invert fin (m):</b> cotas del fondo de la tubería (para
              redes de gravedad). Se rellenan a mano o se importan del Excel.</li>
          <li><b>Part (pieza):</b> nombre del tipo de pieza que el plugin de Civil 3D
              emparejará por nombre (ej. "900 mm Corrugated HDPE Pipe").</li>
        </ul>
        <p>El <b>color</b> se hereda del tipo/capa y viaja en el JSON de red como
        <code>{aci, name}</code> (índice ACI de AutoCAD + nombre en inglés).</p>

        <h3>4. Multileader (flecha + texto)</h3>
        <p>En el acordeón, abre <b>↳ Multileader</b>.</p>
        <ol>
          <li>Elige la <b>Orientación</b>: Horizontal (recto), Vertical (texto vertical pegado
              a la línea) o Diagonal (con landing/quiebre).</li>
          <li>Elige el TEXTO: marca <b>Usar texto personalizado</b> y escríbelo, o desactívalo
              y selecciona uno de la lista (viene de la columna TEXTO/TEXTOS del Excel abierto).</li>
          <li>Ajusta <b>Estilo</b> (fuente, altura, negrita) — se puede cambiar antes o después.</li>
          <li>Pulsa <b>↳ Colocar Multileader</b>, clic en la <b>punta</b> (a qué señala) y luego
              clic dónde va el <b>texto</b>. Queda armado para colocar otro; pulsa <b>Esc</b> para salir.</li>
          <li>Para editar: <b>doble clic</b> sobre el texto. <b>Enter</b> aplica y
              <b>Ctrl+Shift+Enter</b> hace salto de línea.</li>
        </ol>
        <p>Al exportar, cada Multileader se digitaliza como <b>entidad MULTILEADER nativa</b>
        de CAD (flecha + directriz + texto).</p>

        <h3>5. Leader (solo flecha, sin texto)</h3>
        <p>En el acordeón, abre <b>↘ Leader (flecha simple)</b>.</p>
        <ol>
          <li>Elige la orientación (H/V/D).</li>
          <li>Pulsa <b>↘ Colocar Leader</b>. En H/V son dos clics (cabeza y final del cuerpo).
              En Diagonal son tres (cabeza → bisagra → final).</li>
        </ol>
        <p>Al exportar sale como entidad LEADER nativa de CAD.</p>

        <h3>6. Texto libre</h3>
        <p>En el acordeón, abre <b>T Texto libre</b>.</p>
        <ol>
          <li>Ajusta fuente, altura, negrita y <b>rotación</b> (giro libre 0–360°).</li>
          <li>Pulsa <b>T Texto libre</b>, haz clic donde escribir, teclea y pulsa <b>Enter</b>
              (Ctrl+Shift+Enter = salto de línea).</li>
          <li>Los textos son <b>seleccionables</b> (clic), <b>editables</b> (doble clic) y
              <b>movibles</b> (Editar/mover). Al seleccionar uno, la sección Texto libre se
              abre sola y puedes cambiarle el estilo.</li>
        </ol>

        <h3>7. Borrar zona (tapar el plano)</h3>
        <p>Abre <b>▭ Borrar zona</b>. Haz clics para marcar el polígono; <b>Enter</b> cierra la
        zona. El interior se rellena de blanco y queda detrás de las tuberías (solo tapa el plano).
        Al exportar se borra la geometría base dentro de esa zona. En la pestaña <b>Zonas</b> del
        inventario puedes activarla/desactivarla, editar sus vértices o eliminarla.</p>

        <h3>8. Reconocimiento de texto (OCR / ICR)</h3>
        <p>Abre <b>🔤 Reconocimiento de texto</b>.</p>
        <ul>
          <li><b>Textos impresos (OCR):</b> lee los textos impresos del plano con Tesseract.</li>
          <li><b>Manuscrita (ICR, offline):</b> lee anotaciones a mano con EasyOCR (offline; la
              primera vez descarga el modelo ~100 MB).</li>
        </ul>
        <p>Verás recuadros amarillos sobre el plano. Haz clic en uno, corrige el texto y confirma
        con Enter — el texto corregido queda anotado en tu plano.</p>

        <h3>9. Georreferenciación (coordenadas UTM reales)</h3>
        <p>Abre <b>🌍 Georreferenciación</b> (o menú <b>Georreferencia → Georreferenciar…</b>).</p>
        <ol>
          <li>Se abre una ventana con el <b>PDF a la izquierda</b> y un <b>mapa</b> a la derecha
              (satélite Esri o calles OSM, conmutable).</li>
          <li><b>Busca la dirección</b> en el mapa (escribe y pulsa Enter — usa Nominatim/OSM).</li>
          <li>Coloca <b>puntos de control</b>: clic en un punto identificable del PDF (una esquina,
              cruce de calles, vértice de manzana) y luego el <b>mismo</b> punto en el mapa.
              Mínimo 2 pares (ajuste "similarity"); 3–4 pares recomendados ("affine").</li>
          <li>Indica la zona <b>EPSG UTM</b> (o déjala en <i>auto</i>: se calcula desde la longitud
              del primer punto).</li>
          <li>Pulsa <b>Calcular ajuste</b>. Verás el <b>RMS</b> (error cuadrático medio) en metros.
              Si supera ~2 m, agrega puntos mejor repartidos o revisa los pares.</li>
          <li>Acepta. La barra de estado muestra <b>Georref: EPSG:xxxxx · RMS y m</b>.</li>
        </ol>
        <p>Con georreferencia activa, TODA la exportación (DXF y JSON) usa esas coordenadas
        <b>UTM reales</b>; sin ella se usa la escala detectada del titleblock y las X,Y NO
        coincidirán con datos externos.</p>
        <p><b>Aviso importante:</b> calzar sobre imagen satelital da coordenadas
        <b>aproximadas</b> (metros de error). Sirve para trazado/anteproyecto, NO para grado
        construcción. El dato topográfico real siempre viene del levantamiento/Excel.</p>

        <h3>10. Cotas y red 3D — buzones e importación de Excel</h3>
        <p>Abre <b>📐 Cotas y red 3D</b>.</p>
        <ul>
          <li><b>Gestionar buzones…</b> — abre una tabla con los buzones detectados
              automáticamente en los vértices de las tuberías de gravedad (alcantarillado,
              drenaje). Edita <b>Cod</b>, <b>rim</b> (cota de tapa), <b>sump</b> (cota de fondo)
              y <b>part</b> (pieza).</li>
          <li><b>Importar Excel de red…</b> — lee un libro con hojas <b>BUZONES</b> y
              <b>TUBERIAS</b> (encabezados en la fila 5). Las coordenadas del Excel son
              <b>reales</b> (metros UTM) y se cargan tal cual; las cotas y diámetros pasan a las
              utilidades correspondientes.</li>
        </ul>
        <p>Columnas esperadas:</p>
        <ul>
          <li><b>BUZONES:</b> X, Y, Z (=rim), C. SOLERA (=sump), Cod, Tipo Bz (=part).</li>
          <li><b>TUBERIAS:</b> Cod. Tub ("A - B"), Xi, Yi, Zi, Xf, Yf, Zf, Altura (=diámetro),
              Tipo Tub (=part).</li>
        </ul>

        <h3>11. Editar, mover, extender</h3>
        <ul>
          <li><b>Clic sobre el dibujo</b> selecciona el elemento más cercano (no mueve la vista).</li>
          <li>Seleccionar desde la lista del inventario <b>centra la vista</b> en el elemento
              y abre la sección del acordeón que corresponde para editarlo.</li>
          <li><b>Editar/mover</b> (Ctrl+T): arrastra vértices, inserta uno haciendo clic sobre un
              tramo, borra un vértice con clic derecho, o arrastra lejos de los vértices para
              mover todo el elemento.</li>
          <li><b>Escape</b> quita la selección; volver a pulsar sale del modo actual.</li>
          <li><b>Ctrl+C / Ctrl+V:</b> copia y pega el elemento seleccionado (con un desplazamiento).</li>
        </ul>

        <h3>12. Guardar y exportar</h3>
        <ul>
          <li><b>Archivo → Guardar proyecto</b> (Ctrl+S): guarda TODO en un <code>.digproj</code>
              (imagen del PDF + tu marcado + cotas + georreferencia). Se comparte y abre sin el PDF
              original.</li>
          <li><b>Exportar DXF ▾</b> (arriba a la derecha, en la barra de acción):
              <ul>
                <li><i>PDF + anotaciones</i> — el plano digitalizado + tu marcado (todo).</li>
                <li><i>Solo el PDF digitalizado</i> — sin tu marcado.</li>
                <li><i>Solo las anotaciones</i> — sin el plano base.</li>
                <li><i>Exportar red 3D (JSON)</i> — archivo <code>.network.json</code> con el
                    contrato <b>utility-network/3.0</b> (utilidades, buzones, cotas, diámetro,
                    material, color, tipo de red) para el plugin de Civil 3D.</li>
              </ul>
          </li>
          <li><b>Archivo → Cerrar proyecto</b> (Ctrl+W): pregunta si hay cambios sin guardar.</li>
        </ul>

        <h3>13. ¿Qué significa cada dato y de dónde sale?</h3>
        <table cellpadding="4">
          <tr><td><b>x, y (utilidades y buzones)</b></td>
              <td>Coordenadas de mundo del dibujo. Con georreferencia activa: UTM real
                  (en metros). Sin ella: escala del titleblock (NO son coordenadas UTM
                  reales; no coinciden con datos externos).</td></tr>
          <tr><td><b>rim, sump</b></td>
              <td>Cotas del buzón (tapa y fondo, en metros). SE INGRESAN A MANO o se importan
                  del Excel. La app NO las inventa; si no las das, van null.</td></tr>
          <tr><td><b>invert inicio / fin</b></td>
              <td>Cotas de fondo de la tubería en cada extremo (metros). Igual que rim/sump:
                  dato externo, null si no se rellena.</td></tr>
          <tr><td><b>diameter (value, unit)</b></td>
              <td>Diámetro que escribes en Propiedades, con la unidad tal cual la usas
                  (pulg / pies / m — importado desde Excel).</td></tr>
          <tr><td><b>material</b></td>
              <td>Texto libre en Propiedades (ej. "HDPE"). null si no lo rellenas.</td></tr>
          <tr><td><b>color</b></td>
              <td>Se deriva del tipo/capa: <code>{aci, name}</code>. Es el color de AutoCAD
                  con el que se dibuja la utilidad.</td></tr>
          <tr><td><b>network_type</b></td>
              <td>"pipe" (con buzones) o "pressure" (a presión). Por defecto lo decide la capa
                  (agua/gas → pressure, resto → pipe); puedes forzarlo en Propiedades.</td></tr>
          <tr><td><b>part</b></td>
              <td>Nombre del tipo de pieza que usa el plugin de Civil 3D para elegir el estilo
                  3D. Texto libre; null si no se rellena.</td></tr>
        </table>

        <h3>14. Historial de versiones</h3>
        <p><b>Ayuda → Acerca de…</b> muestra la versión actual y un historial desplegable por
        versión (verde = nueva · celeste = corregida · ámbar = cambiada · rojo = quitada).</p>
        """
        self._show_html("Manual de usuario", html, 880, 780)

    def show_shortcuts(self):
        rows = [("Ctrl+Z / Ctrl+Shift+Z", "Deshacer / Rehacer"),
                ("Enter", "Aplicar: finaliza utilidad/zona, o agrega texto/edición"),
                ("Ctrl+Shift+Enter", "Salto de línea dentro de un texto o Multileader"),
                ("Escape", "Quitar la selección; si no hay, salir del modo"),
                ("Ctrl+T", "Editar/mover lo seleccionado"),
                ("Ctrl+S / Ctrl+Shift+S", "Guardar proyecto / Guardar como…"),
                ("Ctrl+W", "Cerrar proyecto (pregunta si hay cambios)"),
                ("Doble clic", "Sobre un Multileader o texto: editarlo"),
                ("Clic derecho", "Finaliza línea/zona; en editar, elimina el vértice"),
                ("◀ ▶", "Página anterior / siguiente"),
                ("Rueda", "Zoom · Botón central + arrastrar: desplazar")]
        body = "".join(f'<tr><td style="padding:4px 14px;color:#8bd;"><b>{k}</b></td>'
                       f'<td style="padding:4px;">{d}</td></tr>' for k, d in rows)
        self._show_html("Atajos de teclado", f"<h2>Atajos de teclado</h2><table>{body}</table>", 640, 500)

    # ─────────────────────────── drag & drop ───────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls(): self.open_path(u.toLocalFile()); break


def main():
    # Necesario para QWebEngineView (mapa de georreferenciación); inofensivo si no se usa.
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication(sys.argv)
    win = Main(); win.show()
    if len(sys.argv) > 1:
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
