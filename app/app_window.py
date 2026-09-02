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
from model import (VERSION, TIPOS, ACI_RGB, LEADER_TEXT_FT, LEADER_ORIENT,
                   Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE, GRAVITY_LAYERS,
                   TAB_PIPE, TAB_ML, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ, TAB_CURVE, TAB_CL,
                   WORK_UNITS, DEFAULT_WORK_UNIT, CHANGELOG,
                   PIPE_DIAMETERS_IN, PIPE_MATERIALS, DEFAULT_PIPE_MATERIAL)

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
BTN_ON = "background:#2e9e4f;color:white;font-weight:bold;padding:8px;border-radius:4px;"
BTN_OFF = "background:#3c5a99;color:white;padding:8px;border-radius:4px;"


def aci_qcolor(a): return QtGui.QColor(*ACI_RGB.get(a, (235, 235, 235)))
def layer_qcolor(l): return aci_qcolor(C.OUTPUT_LAYERS.get(l, 7))


def _extract_diam_from_size(size_str):
    """Extrae el primer número de un tamaño del catálogo, p.ej. '24 in' → 24.0,
    '12 in x 8 in' → 12.0. Retorna 0.0 si no encuentra número."""
    import re as _re
    if not size_str: return 0.0
    m = _re.match(r"\s*(\d+(?:\.\d+)?)", str(size_str))
    return float(m.group(1)) if m else 0.0


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
        # Fondo DETRÁS del PDF (mismo tamaño que el PDF): blanco por defecto. Al
        # bajar la opacidad del PDF se ve este fondo en vez del azul del lienzo.
        # Se puede alternar a negro (ver set_pdf_bg / botón "Opacidad").
        self.pdf_bg_item = None
        self.pdf_bg_color = QtGui.QColor(255, 255, 255)

    def set_image(self, qimg):
        self.scene().clear()
        # Rectángulo de fondo (blanco/negro) por debajo del PDF, de su mismo tamaño.
        pm = QtGui.QPixmap.fromImage(qimg)
        self.pdf_bg_item = self.scene().addRect(
            QtCore.QRectF(pm.rect()), QtGui.QPen(QtCore.Qt.NoPen),
            QtGui.QBrush(self.pdf_bg_color))
        self.pdf_bg_item.setZValue(Z_PDF - 1)
        self.pixmap_item = self.scene().addPixmap(pm)
        self.pixmap_item.setZValue(Z_PDF)
        self.pixmap_item.setOpacity(self.pdf_opacity)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform(); self.fitInView(self.pixmap_item, QtCore.Qt.KeepAspectRatio)

    def set_pdf_opacity(self, val):
        self.pdf_opacity = max(0.1, min(1.0, val))
        if self.pixmap_item: self.pixmap_item.setOpacity(self.pdf_opacity)

    def set_pdf_bg(self, color):
        """Color del fondo detrás del PDF (blanco o negro)."""
        self.pdf_bg_color = QtGui.QColor(color)
        if self.pdf_bg_item:
            self.pdf_bg_item.setBrush(QtGui.QBrush(self.pdf_bg_color))

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


class _SegInvSpinBox(QtWidgets.QDoubleSpinBox):
    """QDoubleSpinBox de la tabla "Cotas por tramo": Enter/Return confirma el
    valor tecleado ahí mismo. Embebido en una celda de QTableWidget (vía
    setCellWidget), el widget contenedor puede quedarse con la tecla Enter
    antes de que dispare editingFinished normalmente — se maneja acá a mano
    para no depender de esa cadena de eventos."""
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.interpretText()
            event.accept()
            # Diferido: el slot conectado reconstruye la tabla (destruye este
            # mismo spinbox) — no hacerlo en medio de este keyPressEvent.
            QtCore.QTimer.singleShot(0, self.editingFinished.emit)
            return
        super().keyPressEvent(event)


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
        self.pdf_path = None; self.doc = None; self.project_path = None; self.leader_hpx = 40
        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.ref_centerlines = []; self._cl_pts = []
        self.mode = "idle"; self._pending = None
        self.snap = False; self.snap_r = 14
        self.sel_pipe = -1; self.sel_leader = -1; self.sel_region = -1; self.sel_text = -1; self.sel_bz = -1
        self.sel_curve = -1; self.sel_cl = -1; self._bz_rows = []; self._curve_rows = []
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

    # ─────────────────────────── UI ───────────────────────────
    def _build_ui(self):
        mb = self.menuBar()
        mfile = mb.addMenu("&Archivo")
        self._menu_act(mfile, "Abrir PDF…", self.open_pdf)
        mfile.addSeparator()
        self._menu_act(mfile, "Abrir proyecto…", self.open_project)
        self._menu_act(mfile, "Guardar proyecto", self.save_project, "Ctrl+S")
        self._menu_act(mfile, "Guardar proyecto como…", self.save_project_as, "Ctrl+Shift+S")
        mfile.addSeparator()
        self._menu_act(mfile, "Cerrar proyecto", self.close_project, "Ctrl+W")
        medit = mb.addMenu("&Edición")
        self._menu_act(medit, "Deshacer", self.undo, "Ctrl+Z")
        self._menu_act(medit, "Rehacer", self.redo, "Ctrl+Shift+Z")
        mtools = mb.addMenu("&Herramientas")
        self._menu_act(mtools, "Insertar buzón en línea…", self.insert_manhole)
        self._menu_act(mtools, "Instalar familia personalizada…", self.open_install_family_dialog)
        self._menu_act(mtools, "Desinstalar familia personalizada…", self.open_uninstall_family_dialog)
        mtools.addSeparator()
        self._menu_act(mtools, "Georreferenciar…", self.open_georef)
        self._menu_act(mtools, "Quitar georreferencia", self.clear_georef)
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
        spacer = QtWidgets.QWidget(); spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred); tb.addWidget(spacer)
        # Sin selector de unidad: TODO va en pies por campo (cotas/coordenadas),
        # salvo los diámetros que van siempre en pulgadas (lista fija del catálogo).
        tb.addSeparator()
        tb.addWidget(QtWidgets.QLabel("Civil 3D:"))
        self.cmb_civil = QtWidgets.QComboBox()
        import civil_catalog as _cc
        _all_years = list(_cc.SUPPORTED_YEARS); _inst = set(_cc.installed_versions())
        for y in _all_years:
            self.cmb_civil.addItem(f"{y}{'' if y in _inst else '  (no instalado)'}", y)
        if self.civil_year is not None:
            i = _all_years.index(self.civil_year); self.cmb_civil.setCurrentIndex(i)
        self.cmb_civil.currentIndexChanged.connect(self._on_civil_year_changed)
        self.cmb_civil.setToolTip("Versión de Civil 3D. El catálogo imperial se busca en\n"
                                  "C:\\ProgramData\\Autodesk\\C3D <año>\\<idioma>\\Pipes Catalog\\US Imperial Structures")
        tb.addWidget(self.cmb_civil)
        # Selector de idioma del catálogo — se puebla dinámicamente al elegir año.
        # Si el cliente tiene tanto 'esp' como 'enu' instalados, puede elegir
        # cuál usar para la instalación de familias custom y el listado.
        tb.addWidget(QtWidgets.QLabel("Idioma:"))
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.setToolTip("Idioma del catálogo Civil 3D a usar (subcarpeta esp/enu/etc.)")
        self.cmb_lang.currentIndexChanged.connect(self._on_civil_lang_changed)
        tb.addWidget(self.cmb_lang)
        # Poblamos el combo de idiomas por primera vez con la versión activa.
        self._refill_lang_combo()
        tb.addSeparator()
        self.btn_export = QtWidgets.QPushButton("⭳  Exportar DXF")
        self.btn_export.setStyleSheet("QPushButton{background:#4d8eff;color:#00285d;font-weight:bold;padding:5px 14px;border-radius:4px;} QPushButton:hover{background:#66a3ff;}")
        self.btn_export.clicked.connect(lambda: self.run_pipeline("todo"))
        tb.addWidget(self.btn_export)
        # Capas de referencia reales de LA (checkables ocultas: se activan por menú Herramientas si hace falta).
        self.act_la_ref = QtGui.QAction("Incluir calles reales de LA", self); self.act_la_ref.setCheckable(True)
        self.act_la_parcels = QtGui.QAction("Incluir parcelas de LA", self); self.act_la_parcels.setCheckable(True)

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
        tb_l = QtWidgets.QPushButton("−"); tb_l.setFixedSize(38, 34); tb_l.setProperty("iconOnly", True); tb_l.setToolTip("Más translúcido"); tb_l.clicked.connect(lambda: self._bump_opacity(-10))
        self.lbl_opacity = QtWidgets.QLabel("100%"); self.lbl_opacity.setAlignment(QtCore.Qt.AlignCenter)
        tb_r = QtWidgets.QPushButton("+"); tb_r.setFixedSize(38, 34); tb_r.setProperty("iconOnly", True); tb_r.setToolTip("Más opaco"); tb_r.clicked.connect(lambda: self._bump_opacity(10))
        ltr.addWidget(tb_l); ltr.addWidget(self.lbl_opacity, 1); ltr.addWidget(tb_r)

        # Botones de acción (uno por sección; el color verde/azul lo pone _update_ui)
        self.btn_pipe = QtWidgets.QPushButton("✏  Dibujar utilidad"); self.btn_pipe.clicked.connect(self.toggle_pipe)
        self.btn_leader_simple = QtWidgets.QPushButton("↘  Colocar Leader"); self.btn_leader_simple.clicked.connect(lambda: self.start_leader(True))
        self.btn_text = QtWidgets.QPushButton("T  Texto libre"); self.btn_text.clicked.connect(self.toggle_text_mode)
        self.btn_erase = QtWidgets.QPushButton("▭  Borrar zona"); self.btn_erase.clicked.connect(self.toggle_erase)
        self.btn_centerline = QtWidgets.QPushButton("📐  Trazar centerline"); self.btn_centerline.clicked.connect(self.toggle_centerline)

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
        # Etiquetas CORTAS a propósito: QCheckBox no hace word-wrap, así que un
        # texto largo impone un ancho mínimo que saca barra horizontal en el
        # dock. El detalle completo va al tooltip — y de paso se lee más fácil,
        # que es lo que necesita el usuario principal.
        self.chk_ab = QtWidgets.QCheckBox("Abandonado")
        self.chk_ab.setToolTip("Marca la utilidad como abandonada: se dibuja con "
                               "línea discontinua ──/── W ── en el DXF.")
        self.chk_ext_same = QtWidgets.QCheckBox("Extender: continuar la misma")
        self.chk_ext_same.setToolTip(
            "Al extender un extremo de una utilidad existente, los puntos nuevos "
            "se añaden a ESA misma utilidad en vez de crear una nueva.")
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

        # ── Sección: Trazar centerline ──
        # Va JUSTO DESPUES de "Dibujar utilidad": las dos son de trazado de
        # geometria, el usuario suele alternarlas y tenerlas contiguas ahorra
        # clics.
        p, l = _page("📐  Trazar centerline", "centerline")
        l.addWidget(self.btn_centerline)
        _lbl_cl = QtWidgets.QLabel(
            "<i>Clic para agregar vértices, Enter "
            "cierra. Se exporta al DXF en su propia capa.</i>")
        _lbl_cl.setWordWrap(True); l.addWidget(_lbl_cl)
        self._slot_gcur_cl = QtWidgets.QVBoxLayout(); l.addLayout(self._slot_gcur_cl)   # slot: gcur al trazar
        l.addStretch(1)

        # (La sección "Multileader" del acordeón está deshabilitada; su tab del
        # inventario también. La infraestructura de Multileader se conserva por si
        # se reactiva, pero NO se muestra al usuario.)

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
        self.bz_list = QtWidgets.QListWidget(); self.bz_list.currentRowChanged.connect(self._sel_bz)
        self.curve_list = QtWidgets.QListWidget(); self.curve_list.currentRowChanged.connect(self._sel_curve)
        self.cl_list = QtWidgets.QListWidget(); self.cl_list.currentRowChanged.connect(self._sel_cl)
        self.tabs.addTab(self.pipe_list, "Utilidades"); #self.tabs.addTab(self.lead_list, "Multileaders")
        self.tabs.addTab(self.sleader_list, "Leaders")
        self.tabs.addTab(self.txt_marks_list, "Textos"); self.tabs.addTab(self.region_list, "Zonas")
        self.tabs.addTab(self.bz_list, "Buzones"); self.tabs.addTab(self.curve_list, "Curvas")
        self.tabs.addTab(self.cl_list, "Centerlines")
        # RESPONSIVO: los textos de los items son largos ("AGUA · 12" · 4
        # vértices · <nombre>"), así que por defecto QListWidget saca una barra
        # de desplazamiento HORIZONTAL y el usuario tiene que arrastrarla para
        # leer. Con elide a la derecha el texto se recorta con "…" y la barra
        # desaparece; el texto completo queda en el tooltip del item (ver
        # _refresh_lists). No afecta la selección ni los índices de fila.
        for _lw in (self.pipe_list, self.lead_list, self.sleader_list,
                    self.txt_marks_list, self.region_list, self.bz_list,
                    self.curve_list, self.cl_list):
            _lw.setTextElideMode(QtCore.Qt.ElideRight)
            _lw.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            _lw.setWordWrap(False)
            _lw.setUniformItemSizes(True)          # más fluido con muchas filas
        # Menú contextual (clic derecho) en cada lista visible del inventario
        # (la lista de Multileaders no se registra porque su pestaña está oculta)
        for listw, tab_idx in ((self.pipe_list, TAB_PIPE),
                               (self.sleader_list, TAB_LEADER), (self.txt_marks_list, TAB_TEXT),
                               (self.region_list, TAB_REGION)):
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
        fpr.addRow("Tipo de red:", self.prop_nettype)
        # Labels dinámicas: se recomponen al cambiar la unidad de trabajo.
        # Nombre igual a Civil 3D: "Elevación de rasante" (no "Invert").
        self.lbl_prop_inv0 = QtWidgets.QLabel("Elev. de rasante inicial (ft):"); fpr.addRow(self.lbl_prop_inv0, self.prop_inv0)
        self.lbl_prop_inv1 = QtWidgets.QLabel("Elev. de rasante final (ft):");   fpr.addRow(self.lbl_prop_inv1, self.prop_inv1)
        # Familia + tamaño del catálogo Civil 3D para esta pipe (solo gravedad).
        # Para presión y conduit no aplica: presión usa el sub-catálogo por material
        # y conduit se deja como polyline simple.
        self.prop_family = QtWidgets.QComboBox()
        self.prop_family.currentIndexChanged.connect(self._pipe_family_changed)
        self.prop_size = QtWidgets.QComboBox()
        self.prop_size.currentIndexChanged.connect(lambda _: self._prop_changed())
        self.lbl_prop_family = QtWidgets.QLabel("Familia (catálogo):")
        self.lbl_prop_size = QtWidgets.QLabel("Tamaño (catálogo):")
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
        self.btn_seg_edit = QtWidgets.QPushButton("✎  Activar edición por tramo")
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
        self.lbl_bz_hint.setStyleSheet("color:#f0d060; padding:8px; background:#333a4a; border-radius:4px;")
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
        self.cv_net_lbl = QtWidgets.QLabel("—")
        self.cv_origin_lbl = QtWidgets.QLabel("—")
        fcv.addRow("Código:", self.cv_cod)
        fcv.addRow("Familia (tubería):", self.cv_family_lbl)
        fcv.addRow("Tamaño:", self.cv_size_lbl)
        fcv.addRow("Radio (Pies):", self.cv_radius)
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
        self.lbl_curve_hint.setStyleSheet("color:#f0d060; padding:8px; background:#333a4a; border-radius:4px;")
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
        self.lbl_cl_hint.setStyleSheet("color:#f0d060; padding:8px; background:#333a4a; border-radius:4px;")
        rv.addWidget(self.lbl_cl_hint)
        self.gprop_cl.setVisible(False); self.lbl_cl_hint.setVisible(False)
        self._cl_prop_guard = False
        self._bz_prop_guard = False                 # evita reentradas al setear valores desde el modelo
        self._curve_prop_guard = False
        rr = QtWidgets.QGridLayout()
        self.btn_ct = QtWidgets.QPushButton("Cambiar tipo"); self.btn_ct.clicked.connect(self.change_pipe_type)
        self.btn_mv = QtWidgets.QPushButton("Editar/mover"); self.btn_mv.clicked.connect(self.enter_move)
        self.btn_edit = QtWidgets.QPushButton("Editar texto"); self.btn_edit.clicked.connect(self.edit_selected_text)
        self.btn_del = QtWidgets.QPushButton("Eliminar"); self.btn_del.setProperty("danger", True)
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

        # ── Barra de estado: modo · info · contadores en vivo · escala · georref ──
        self.status = self.statusBar(); self.status.setSizeGripEnabled(False)
        self.lbl_mode = QtWidgets.QLabel("Modo: inactivo"); self.lbl_mode.setStyleSheet("color:#adc6ff;")
        self.status.addWidget(self.lbl_mode)
        self.status.addWidget(QtWidgets.QLabel("│"))
        self.lbl_info = QtWidgets.QLabel(""); self.lbl_info.setStyleSheet("color:#8c909f;"); self.status.addWidget(self.lbl_info, 1)
        self.lbl_coords = QtWidgets.QLabel("X —  Y —  Z —")
        # Contadores en vivo: N utilidades · N leaders · N textos · dirty
        self.lbl_counts = QtWidgets.QLabel("—")
        self.lbl_dirty = QtWidgets.QLabel("")   # muestra "●" cuando hay cambios sin guardar
        # Escala como BOTÓN plano: el usuario reportó que "1"=20'" viene del
        # titleblock pero a veces necesita ajustarla. Un botón deja claro que
        # es interactivo y hace evidente el gesto (un QLabel se ve idéntico a
        # los otros textos de la barra de estado). Estilo consistente con la
        # barra: fondo transparente, sin borde salvo al pasar/pulsar.
        self.btn_scale = QtWidgets.QPushButton("Escala —")
        self.btn_scale.setFlat(True); self.btn_scale.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_scale.setToolTip("Clic para cambiar la escala del plano (1\"=X ft)")
        self.btn_scale.setStyleSheet(
            "QPushButton{background:transparent;color:#c2c6d6;border:1px solid transparent;"
            " padding:2px 8px;border-radius:3px;font-weight:normal;}"
            "QPushButton:hover{background:#3a3a3a;border:1px solid #565656;color:#ffffff;}"
            "QPushButton:pressed{background:#2f6ad9;color:#ffffff;}")
        self.btn_scale.clicked.connect(self._prompt_scale)
        # Botón "Opacidad" al lado de la escala: abre un desplegable con un
        # deslizable (opacidad SOLO del PDF) y un botón para alternar el fondo
        # detrás del PDF entre blanco y negro.
        self.btn_opacity = QtWidgets.QPushButton("◑ Opacidad")
        self.btn_opacity.setFlat(True); self.btn_opacity.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_opacity.setToolTip("Opacidad del PDF y color de fondo (blanco/negro)")
        self.btn_opacity.setStyleSheet(self.btn_scale.styleSheet())
        self.btn_opacity.clicked.connect(self._open_opacity_popup)
        self.lbl_geo = QtWidgets.QLabel("Georref: no")
        for w in (self.lbl_coords, self.lbl_counts, self.lbl_dirty):
            w.setStyleSheet("color:#c2c6d6;"); self.status.addPermanentWidget(w)
        self.status.addPermanentWidget(self.btn_scale)
        self.status.addPermanentWidget(self.btn_opacity)
        self.lbl_geo.setStyleSheet("color:#c2c6d6;"); self.status.addPermanentWidget(self.lbl_geo)
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
        elif self.mode == "centerline": self.finish_centerline()
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
        elif self.mode == "centerline" and self._cl_pts:
            self._push(); self._cl_pts = []; self._update_ui(); self._redraw(); self._info("Puntos cancelados")
        elif self.mode == "insert_bz":
            self.set_mode("idle"); self._info("Inserción de buzón cancelada")
        elif self.sel_pipe >= 0 or self.sel_leader >= 0 or self.sel_region >= 0 or self.sel_text >= 0 or self.sel_bz >= 0 or self.sel_curve >= 0 or self.sel_cl >= 0:
            self._deselect_all(); self._info("Selección quitada")
        else:
            self.set_mode("idle"); self._info("Salió del modo")

    def _deselect_all(self):
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = self.sel_bz = self.sel_curve = self.sel_cl = -1
        for lst in (self.pipe_list, self.lead_list, self.sleader_list, self.txt_marks_list, self.region_list,
                    getattr(self, "bz_list", None), getattr(self, "curve_list", None), getattr(self, "cl_list", None)):
            if lst is None: continue
            lst.blockSignals(True); lst.setCurrentRow(-1); lst.clearSelection(); lst.blockSignals(False)
        if self.mode == "move": self.set_mode("idle")
        self._update_ui(); self._redraw()

    def _info(self, m): self.lbl_info.setText(m)

    def _zoom_in(self): self.canvas.scale(1.25, 1.25)
    def _zoom_out(self): self.canvas.scale(0.8, 0.8)

    def _update_title(self):
        if self.project_path:
            name = os.path.splitext(os.path.basename(self.project_path))[0]
            self.setWindowTitle(f"{self._base_title} — {name}")
        else:
            self.setWindowTitle(self._base_title)

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
        self.btn_scale.setText(f"✎ Escala 1\"={v:.0f}'" if v > 0 else "✎ Escala —")

    def _prompt_scale(self):
        """Diálogo compacto para cambiar la escala del plano (1\"=X ft).

        La escala interna es en ft por punto PDF (72 pt = 1 in), así que un
        valor de 20 significa "1 pulgada = 20 pies" — la misma notación que
        usan los planos del titleblock. Se acepta un decimal por si acaso.
        """
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, "Escala",
                "Primero abre un PDF o proyecto."); return
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
            QtWidgets.QMessageBox.information(self, "Opacidad",
                "Primero abre un PDF o proyecto."); return
        menu = QtWidgets.QMenu(self)
        box = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(box); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(8)
        pct = round(self.canvas.pdf_opacity * 100)
        lbl = QtWidgets.QLabel(f"Opacidad del PDF: {pct}%")
        sl = QtWidgets.QSlider(QtCore.Qt.Horizontal); sl.setRange(10, 100)
        sl.setValue(pct); sl.setMinimumWidth(220)

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

    def _update_geo_status(self):
        if self.georef.active():
            unit = georef_mod.epsg_unit(self.georef.epsg)
            rms = f" · RMS {self.georef.rms:.2f} {unit}" if self.georef.rms is not None else ""
            cs = (getattr(self.georef, "cs_code", "") or "").strip()
            etq = cs if cs else f"EPSG:{self.georef.epsg}"
            self.lbl_geo.setText(f"Georref: {etq}{rms}")
            self.lbl_geo.setStyleSheet("color:#5fd35f;")
        else:
            self.lbl_geo.setText("Georref: no (escala titleblock)")
            self.lbl_geo.setStyleSheet("color:#e0c060;")

    def _update_ui(self):
        m = self.mode
        def st(btn, on): btn.setStyleSheet(BTN_ON if on else BTN_OFF)
        in_leader = m in ("leader1", "leader2", "leader3")
        st(self.btn_pipe, m == "pipe")
        st(self.btn_leader_simple, in_leader)
        st(self.btn_text, m == "text"); st(self.btn_erase, m == "erase")
        st(self.btn_centerline, m == "centerline")
        self.btn_pipe.setText("■  Salir de dibujar utilidad" if m == "pipe" else "✏  Dibujar utilidad")
        self.btn_leader_simple.setText("●  Coloque Leader…" if in_leader else "↘  Colocar Leader")
        self.btn_erase.setText("■  Terminar zona (Enter)" if m == "erase" else "▭  Borrar zona (polígono)")
        self.btn_centerline.setText("■  Terminar centerline (Enter)" if m == "centerline" else "📐  Trazar centerline")
        ti = self._current_tab()
        self.gtxt.setTitle("Estilo de texto")
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
        self.btn_mv.setText("Mover" if ti == TAB_TEXT else "Editar/mover")
        self.btn_edit.setVisible(ti in (TAB_ML, TAB_TEXT))
        # "Eliminar" no aplica en la pestaña Buzones: los buzones se
        # auto-detectan de los vertices de las tuberias, borrarlos no tiene
        # efecto porque _rebuild_structures los repone. Se oculta el boton.
        self.btn_del.setVisible(ti != TAB_BZ)
        diag = self.orient_combo.currentData() == "d"
        lead1 = "Modo: Leader — clic en la cabeza de flecha (dónde señala)"
        lead2 = ("Modo: Leader — clic en el inicio del landing (bisagra)" if diag
                 else "Modo: Leader — clic en el final del cuerpo")
        lead3 = "Modo: Leader — clic en el final del cuerpo"
        self.lbl_mode.setText({"idle": "Modo: inactivo  ·  clic en el dibujo para seleccionar",
                               "pipe": ("Modo: EXTENDIENDO desde el vértice — clic agrega puntos, Enter finaliza"
                                        if self._extending else "Modo: dibujar utilidad  ·  Enter finaliza"),
                               "leader1": lead1,
                               "leader2": lead2,
                               "leader3": lead3,
                               "text": "Modo: texto libre — clic donde escribir · Enter aplica",
                               "erase": "Modo: borrar zona — clic para el polígono, Enter cierra",
                               "centerline": "Modo: trazar centerline — clic agrega puntos, Enter finaliza",
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
        self._update_ui(); self._redraw()

    # El inventario usa IDs lógicos (TAB_PIPE, TAB_ML, …) que NO coinciden con la
    # posición visible de la pestaña cuando alguna está oculta (p. ej. Multileaders).
    # Estos helpers traducen widget↔constante, así el código es robusto ante
    # pestañas ocultas o reordenadas.
    def _tab_map(self):
        m = {self.pipe_list: TAB_PIPE, self.lead_list: TAB_ML, self.sleader_list: TAB_LEADER,
             self.txt_marks_list: TAB_TEXT, self.region_list: TAB_REGION}
        if hasattr(self, "bz_list"): m[self.bz_list] = TAB_BZ
        if hasattr(self, "curve_list"): m[self.curve_list] = TAB_CURVE
        if hasattr(self, "cl_list"): m[self.cl_list] = TAB_CL
        return m

    def _current_tab(self):
        return self._tab_map().get(self.tabs.currentWidget(), TAB_PIPE)

    def _show_tab(self, logical):
        w = {v: k for k, v in self._tab_map().items()}.get(logical)
        idx = self.tabs.indexOf(w) if w is not None else -1
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def _tab_changed(self, _):
        ti = self._current_tab()                    # sel_leader se comparte entre ML y Leaders: re-sincronizar
        if ti == TAB_ML: self.sel_leader = self._leader_at_row(self.lead_list, self.lead_list.currentRow())
        elif ti == TAB_LEADER: self.sel_leader = self._leader_at_row(self.sleader_list, self.sleader_list.currentRow())
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

    def open_pdf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir PDF", DOWNLOADS, "PDF (*.pdf)")
        if path: self._open_pdf_path(path)

    def _open_pdf_path(self, path):
        if not self._confirm_discard(): return
        self._busy("Abriendo PDF…")
        try:
            self.pdf_path = path; self.project_path = None; self.doc = fitz.open(path); self._update_title()
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
        self._refresh_scale_label()
        self._info(f"Página {idx + 1} cargada.")

    def _reset_model(self):
        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []; self.structures = []
        self.ref_centerlines = []; self._cl_pts = []
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
            import civil_catalog as _cc
            model = dict(pipes=self.pipes, leaders=self.leaders, text_marks=self.text_marks,
                         erase_regions=self.erase_regions, structures=self.structures,
                         ref_centerlines=self.ref_centerlines,
                         georef=self.georef.to_dict(),
                         work_unit=self.work_unit,                # unidad de trabajo del proyecto
                         # Versión/idioma de Civil 3D elegidos en el toolbar: se
                         # guardan para reabrir el proyecto con la MISMA selección.
                         civil_year=self.civil_year,
                         civil_lang=_cc._current_lang,
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
            self.project_path = path; self._dirty = False; self._update_title(); self._info(f"Proyecto guardado: {os.path.basename(path)}")
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
            self.project_path = path; self.page_idx = 0; self._update_title()
            self.pipes = model.get("pipes", []); self.leaders = model.get("leaders", [])
            for p in self.pipes:                            # JSON vuelve las keys de vertex_inv a str
                # Tres diccionarios distintos guardan cotas por vertice:
                #   vertex_inv     — legado, cota unica por vertice
                #   vertex_inv_out — cota de SALIDA del vertice (start del segmento siguiente)
                #   vertex_inv_in  — cota de ENTRADA al vertice (end del segmento anterior)
                # Los tres se persisten con json.dumps, que convierte SIEMPRE las
                # llaves a str. Si no se re-castean a int aca, los lookups por
                # indice (que son int) fallan silenciosamente y la edicion por
                # tramo aparece vacia al reabrir el proyecto.
                for k in ("vertex_inv", "vertex_inv_out", "vertex_inv_in"):
                    d = p.get(k)
                    if isinstance(d, dict) and d:
                        p[k] = {int(kk): float(vv) for kk, vv in d.items()}
            self.text_marks = model.get("text_marks", [])
            self.erase_regions = [r if isinstance(r, dict) else {"pts": r, "enabled": True}
                                  for r in model.get("erase_regions", [])]
            self.structures = model.get("structures", [])   # retrocompat: proyectos viejos sin buzones
            self.ref_centerlines = model.get("ref_centerlines", [])   # retrocompat: proyectos viejos sin centerlines
            self.georef = georef_mod.Georef.from_dict(model.get("georef"))   # retrocompat: sin georref → escala
            # Unidad de trabajo SIEMPRE pies (los diámetros van en pulgadas, por campo).
            # Ya no hay selector; ignoramos el work_unit guardado en proyectos viejos.
            self.work_unit = "ft"
            for p in self.pipes: p["unit"] = "ft"
            self.cur_pts = []; self._erase_pts = []; self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
            self._undo.clear(); self._redo.clear(); self._dirty = False
            self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._redraw()
            self._refresh_scale_label(); self._update_geo_status()
            self._refresh_unit_labels()
            # Reponer la versión/idioma de Civil 3D con que se guardó el proyecto
            # (si esa versión sigue instalada). Debe ir ANTES de _warn_missing_families.
            self._restore_civil_selection(model.get("civil_year"), model.get("civil_lang"))
            self._info(f"Proyecto abierto ({len(self.pipes)} utilidades). Ctrl+S guarda en este mismo archivo.")
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
        self._cleanup_tmp_pdf()
        self.canvas.scene().clear(); self.canvas.pixmap_item = None; self.canvas.pdf_bg_item = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.gray = None; self._update_title()
        self.pipes = []; self.leaders = []; self.text_marks = []; self.erase_regions = []; self.structures = []
        self.ref_centerlines = []; self._cl_pts = []
        self.cur_pts = []; self._erase_pts = []; self._overlay = []; self._close_editor()
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = self.sel_cl = -1
        self._undo.clear(); self._redo.clear(); self._dirty = False
        self.georef = georef_mod.Georef()
        self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._info("Proyecto cerrado.")

    def closeEvent(self, e):
        if self._confirm_discard():
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
        if self.mode == "pipe":
            self._push(); self.cur_pts.append(self._snap(x, y)); self._update_ui(); self._redraw()
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
            self._push(); pts.pop(vi)
            if kind == "pipe":
                p = self.pipes[self.sel_pipe]; ov = p.get("vertex_inv")
                if ov:                          # reindexar: el vértice vi ya no existe, los de más allá bajan uno
                    p["vertex_inv"] = {(k - 1 if k > vi else k): v for k, v in ov.items() if k != vi}
                self._rebuild_seg_inv_table(p)
            self._refresh_lists(); self._redraw(); self._info("Vértice eliminado")

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
        self._update_ui(); self._redraw()

    def _interp_vertex_z(self, pts, z_start, z_end, overrides):
        """Cota por vértice interpolada por distancia acumulada 2D, entre anclas
        (extremos + overrides fijados). Espejo exacto de InterpolateZ/ZalongByDistance
        en ImportarRed.cs — usado aquí solo para mostrar el valor 'automático' en la
        tabla de vértices intermedios."""
        n = len(pts)
        z = [0.0] * n
        if n == 0: return z
        if n == 1: z[0] = z_start; return z
        anchors = {0: z_start, n - 1: z_end}
        for k, v in (overrides or {}).items():
            if 0 < k < n - 1: anchors[k] = v
        keys = sorted(anchors.keys())
        for a, b in zip(keys, keys[1:]):
            sub = pts[a:b + 1]
            d = [0.0] * len(sub)
            for i in range(1, len(sub)):
                d[i] = d[i - 1] + math.hypot(sub[i][0] - sub[i - 1][0], sub[i][1] - sub[i - 1][1])
            total = d[-1]
            za, zb = anchors[a], anchors[b]
            for i in range(len(sub)):
                z[a + i] = za + (zb - za) * (d[i] / total) if total > 1e-9 else za
        return z

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
        """Migra el formato viejo (vertex_inv compartido) al nuevo
        (vertex_inv_out + vertex_inv_in independientes)."""
        old = p.pop("vertex_inv", None)
        if old and "vertex_inv_out" not in p:
            p["vertex_inv_out"] = dict(old)
            p["vertex_inv_in"] = dict(old)

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
        """Congela como overrides explícitos todos los valores actualmente
        mostrados en la tabla (excepto v0 del primer tramo y v_n del último,
        que se editan vía inv_start/inv_end). Idempotente."""
        pts = p.get("pts") or []
        n = len(pts)
        if n < 3: return
        ov_out = p.setdefault("vertex_inv_out", {})
        ov_in  = p.setdefault("vertex_inv_in",  {})
        z_start = p.get("inv_start") or 0.0; z_end = p.get("inv_end") or 0.0
        auto_out = self._interp_vertex_z(pts, z_start, z_end, ov_out)
        auto_in  = self._interp_vertex_z(pts, z_start, z_end, ov_in)
        for vi in range(1, n - 1):
            ov_out.setdefault(vi, auto_out[vi])
            ov_in.setdefault(vi, auto_in[vi])

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
            return
        if year not in set(_cc.installed_versions()):
            return                                   # esa versión ya no está en esta PC
        idx = self.cmb_civil.findData(year)
        if idx < 0:
            return
        self.cmb_civil.blockSignals(True)
        self.cmb_civil.setCurrentIndex(idx)
        self.cmb_civil.blockSignals(False)
        self.civil_year = year
        self._refill_lang_combo()                    # repuebla idiomas del año elegido
        lang_ok = ""
        if lang:
            li = self.cmb_lang.findData(lang)
            if li >= 0:
                self.cmb_lang.blockSignals(True)
                self.cmb_lang.setCurrentIndex(li)
                self.cmb_lang.blockSignals(False)
                _cc.set_current_lang(lang)
                lang_ok = f"/{lang}"
        self._refresh_catalog_panels()
        self._info(f"Civil 3D restaurado del proyecto: {year}{lang_ok}.")

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

    def _reload_pipe_families(self, p):
        """Repuebla los combos prop_family y prop_size según la capa del pipe y el
        catálogo Civil 3D seleccionado. Aplica para todos los tipos:
          - gravity y conduit → catálogo imperial de pipes (PVC/HDPE/DI/concreto/CMP…)
          - pressure → catálogo AWWA sub-material (Flanged/PushOn/PVC/HDPE/…)"""
        import civil_catalog as _cc
        self.prop_family.blockSignals(True); self.prop_family.clear()
        self.prop_size.blockSignals(True); self.prop_size.clear()
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
        self._show_tab(TAB_LEADER if simple else TAB_ML); lst.setCurrentRow(row)
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
        if self._current_tab() == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            p = self.pipes[self.sel_pipe]; self._push()
            p["name"] = self.prop_name.text().strip()
            p["diam_unit"] = "in"                                        # el diámetro nunca va en pies
            p["unit"] = self.work_unit                                  # unidad de trabajo (coords/cotas)
            p["part"] = self.prop_part.text().strip()
            p["inv_start"] = self.prop_inv0.value(); p["inv_end"] = self.prop_inv1.value()
            p["material"] = self.prop_material.currentText()
            p["net_type"] = self.prop_nettype.currentData() or ""
            # Familia + tamaño del catálogo Civil 3D. El diámetro se deriva del tamaño.
            if self.prop_family.isVisible():
                p["pipe_family"] = self.prop_family.currentData() or ""
                p["pipe_size"] = self.prop_size.currentData() or "" if self.prop_size.isEnabled() else ""
            # p["diam"] se calcula del pipe_size (p.ej. "24 in" → 24.0). Sin tamaño → 0.
            p["diam"] = _extract_diam_from_size(p.get("pipe_size", ""))
            self._refresh_lists()
            self._rebuild_seg_inv_table(p)

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
                self.lbl_dirty.setText("●"); self.lbl_dirty.setStyleSheet("color:#e0c060;")
            else:
                self.lbl_dirty.setText("")

    def change_pipe_type(self):
        if 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes[self.sel_pipe]["layer"] = self.active_layer()
            self.pipes[self.sel_pipe]["ab"] = self.chk_ab.isChecked(); self._refresh_lists(); self._redraw()

    def edit_selected_text(self):
        ti = self._current_tab()
        if ti == TAB_ML and 0 <= self.sel_leader < len(self.leaders): self._edit_leader_text(self.sel_leader)
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): self._edit_text_mark(self.sel_text)

    def _list_context_menu(self, listw, tab_idx, pos):
        item = listw.itemAt(pos)
        if item is None: return
        if self._current_tab() != tab_idx: self._show_tab(tab_idx)
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
        ti = self._current_tab()
        if ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes.pop(self.sel_pipe); self.sel_pipe = -1
        elif ti in (TAB_ML, TAB_LEADER) and 0 <= self.sel_leader < len(self.leaders):
            self._push(); self.leaders.pop(self.sel_leader); self.sel_leader = -1
        elif ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks):
            self._push(); self.text_marks.pop(self.sel_text); self.sel_text = -1
        elif ti == TAB_REGION and 0 <= self.sel_region < len(self.erase_regions):
            self._push(); self.erase_regions.pop(self.sel_region); self.sel_region = -1
        elif ti == TAB_CL and 0 <= self.sel_cl < len(self.ref_centerlines):
            self._push(); self.ref_centerlines.pop(self.sel_cl); self.sel_cl = -1
        self._refresh_lists(); self._redraw()

    def _copy_sel(self):
        ti = self._current_tab()
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
            self._show_tab(TAB_PIPE); self._refresh_lists(); self.pipe_list.setCurrentRow(len(self.pipes) - 1)
        elif kind == "text":
            o["pos"] = (o["pos"][0] + d, o["pos"][1] + d); self.text_marks.append(o)
            self._show_tab(TAB_TEXT); self._refresh_lists(); self.txt_marks_list.setCurrentRow(len(self.text_marks) - 1)
        self._redraw(); self._info("Pegado (copia desplazada).")

    def _refresh_lists(self):
        self._refresh_counts()
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
                emoji = "🟣"
            else:
                fam = s.get("part") or "(sin familia)"
                sz = f"  {s['part_size']}" if s.get("part_size") else ""
                emoji = "🚫" if s.get("hidden") else ("🟠" if s.get("net") == "conduit" else "🔵")
            it = QtWidgets.QListWidgetItem(f"{emoji} {s.get('cod', '?')}  ·  {fam}{sz}")
            if not is_curve and s.get("hidden"):
                it.setForeground(QtGui.QColor(130, 130, 130))
                it.setToolTip("Oculto — no se dibuja ni se crea en Civil3D como buzón real.")
            if is_curve: self.curve_list.addItem(it); self._curve_rows.append(i)
            else: self.bz_list.addItem(it); self._bz_rows.append(i)
        self.bz_list.blockSignals(False); self.curve_list.blockSignals(False)
        self._sync_bz_panel(); self._sync_curve_panel()
        self.cl_list.blockSignals(True); self.cl_list.clear()
        for c in self.ref_centerlines:
            self.cl_list.addItem(f"📐 {c.get('cod', '?')}  ·  {len(c.get('pts') or [])} vértices")
        self.cl_list.blockSignals(False)
        self._sync_cl_panel()
        self._set_item_tooltips()

    def _set_item_tooltips(self):
        """Pone el texto completo de cada item como su tooltip. Las listas usan
        elide a la derecha para no sacar barra horizontal (ver el bloque
        RESPONSIVO en _build_ui), así que el texto recortado con "…" se puede
        leer completo al pasar el ratón."""
        for lw in (self.pipe_list, self.lead_list, self.sleader_list,
                   self.txt_marks_list, self.region_list, self.bz_list,
                   self.curve_list, self.cl_list):
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
        self._info("Zona agregada: al exportar tapa la geometría base del plano dentro de ella (no toca tus utilidades).")

    def finish_centerline(self):
        if len(self._cl_pts) < 2: return
        self._push()
        used = {c.get("cod", "") for c in self.ref_centerlines if c.get("cod")}
        n = 1
        while f"CL-{n}" in used: n += 1
        self.ref_centerlines.append({"cod": f"CL-{n}", "pts": self._cl_pts[:]})
        self._cl_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info("Centerline agregado — solo referencia para calzar la georreferenciación, no es una utilidad.")

    # ─────────────────────────── Multileader ───────────────────────────
    def _read_leader_text(self):
        if self.chk_custom.isChecked(): return self.txt_edit.text().strip()
        it = self.text_list.currentItem()
        return it.text() if it and self.text_list.currentRow() >= 0 else ""

    def start_leader(self, simple=True):
        """Entra al modo de colocación de Leader (solo flecha, sin texto). La
        orientación se lee de `orient_combo` AL MOMENTO del clic final para que
        el usuario pueda cambiarla dentro del modo. `simple` se mantiene solo
        por retrocompat de callers antiguos; siempre es True ahora."""
        self._pending = {"arrow": None, "simple": True}
        self._open_section("leader")
        self.set_mode("leader1")
        if self.orient_combo.currentData() == "d":
            self._info("Leader diagonal: cabeza → inicio del landing (bisagra) → final del cuerpo. Enter/Esc para salir.")
        else:
            self._info("Leader: cabeza de flecha → final del cuerpo. Enter/Esc para salir.")

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
            self._poly(p["pts"], layer_qcolor(p["layer"]), 4.0 if sel else 2.0, z=Z_MARK)
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
            drew_arc = False
            if is_curve:
                pipe = self._pipe_at_vertex(sx, sy)
                if pipe and len(pipe.get("pts", [])) >= 3:
                    pts = pipe["pts"]
                    vi = None
                    for j, (vx, vy) in enumerate(pts):
                        if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol2:
                            vi = j; break
                    if vi is not None and 0 < vi < len(pts) - 1:
                        px, py = pts[vi - 1]; nx, ny = pts[vi + 1]
                        dx1, dy1 = px - sx, py - sy; dx2, dy2 = nx - sx, ny - sy
                        L1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
                        L2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
                        if L1 > 1e-3 and L2 > 1e-3:
                            t_len = min(60.0, L1 * 0.45, L2 * 0.45)
                            t1x, t1y = sx + dx1 / L1 * t_len, sy + dy1 / L1 * t_len
                            t2x, t2y = sx + dx2 / L2 * t_len, sy + dy2 / L2 * t_len
                            path = QtGui.QPainterPath()
                            path.moveTo(t1x, t1y); path.quadTo(sx, sy, t2x, t2y)
                            arc_col = QtGui.QColor(255, 220, 40) if selected else col
                            arc_pen = QtGui.QPen(arc_col, 14.0 if selected else 11.0)
                            arc_pen.setCosmetic(True); arc_pen.setCapStyle(QtCore.Qt.RoundCap)
                            it = sc.addPath(path, arc_pen); it.setZValue(Z_MARK + 1); self._overlay.append(it)
                            drew_arc = True
            if not drew_arc:
                it = sc.addEllipse(sx - r_use, sy - r_use, 2 * r_use, 2 * r_use, use_pen, brush)
                it.setZValue(Z_MARK + 1); self._overlay.append(it)
            if self.show_bz_labels and s.get("cod"):
                t = sc.addText(s["cod"]); t.setDefaultTextColor(QtGui.QColor(180, 180, 180))
                t.document().setDocumentMargin(0)
                f = t.font(); f.setPixelSize(11); f.setBold(True); t.setFont(f)
                t.setPos(sx + R + 2, sy - R - 2); t.setZValue(Z_MARK + 1); self._overlay.append(t)

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
            self._info("No hay líneas dibujadas para insertar un buzón.")
            return
        self.set_mode("insert_bz")
        self._info("Clic sobre una línea para insertar un buzón (Esc para salir).")

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
            self._info("Los buzones/cajas solo se insertan en redes de gravedad o conduit (no en presión).")
            self.set_mode("idle"); return
        self._push()
        pi, si, _ = best
        self.pipes[pi]["pts"].insert(si + 1, (x, y))
        self._rebuild_structures()
        self._refresh_lists(); self._redraw()
        self._info("Buzón insertado. Edítalo en la tab Buzones.")
        self.set_mode("idle")

    def _rebuild_structures(self):
        """Detecta buzones por los VÉRTICES (extremos + intermedios) de las tuberías
        dibujadas:
          - Gravedad (SS/SD) → prefijo BZ- (buzones cilíndricos con tapa).
          - Conduit (eléctrico/telecom) → prefijo CAJA- (cajas de registro/vaults).
          - Presión (agua/gas) → sin nodos automáticos.
        Preserva ediciones (cod/rim/sump/part/part_size/covered) por coincidencia
        de coordenada. Los buzones importados de Excel (world) se conservan aparte."""
        from model import network_kind
        tol = 14.0
        def near(a, b): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
        # Descarta buzones espurios de versiones previas con net inválida (p.ej. "pressure").
        old = [s for s in self.structures
               if not s.get("world") and (s.get("net") or "gravity") in ("gravity", "conduit")]
        world = [s for s in self.structures if s.get("world")]
        detected = []
        for p in self.pipes:
            if p.get("world"): continue
            kind = network_kind(p.get("layer") or "")
            if kind not in ("gravity", "conduit"): continue    # presión no lleva nodos automáticos
            pts = p.get("pts")
            if not pts or len(pts) < 2: continue
            for pt in pts:                              # todos los vértices (extremos + intermedios)
                if not any(near(pt, (s["x"], s["y"])) for s in detected):
                    detected.append({"cod": "", "x": pt[0], "y": pt[1], "rim": None,
                                     "sump": None, "part": "", "part_size": "",
                                     "net": kind, "covered": True, "world": False,
                                     "hidden": False})
        for s in detected:                                 # reasigna ediciones previas por coordenada
            for o in old:
                if near((s["x"], s["y"]), (o.get("x", -1e9), o.get("y", -1e9))):
                    s.update(cod=o.get("cod", ""), rim=o.get("rim"), sump=o.get("sump"),
                             part=o.get("part", ""), part_size=o.get("part_size", ""),
                             covered=bool(o.get("covered", True)),
                             height_ft=o.get("height_ft", 0.0),
                             curve=bool(o.get("curve", False)),
                             radius_ft=o.get("radius_ft", 0.0),
                             hidden=bool(o.get("hidden", False))); break
        # Códigos únicos: BZ-N gravedad, CAJA-N conduit, CV-N esquina de elemento curvo
        # (curve=True manda sobre el prefijo por red: no es un buzón/caja real).
        used = {s.get("cod", "") for s in world + detected if s.get("cod")}
        cnt_bz = cnt_caja = cnt_cv = 1
        for s in detected:
            if s.get("cod"): continue
            if s.get("curve"):
                while f"CV-{cnt_cv}" in used: cnt_cv += 1
                s["cod"] = f"CV-{cnt_cv}"; used.add(s["cod"]); cnt_cv += 1
                continue
            prefix = "CAJA-" if s.get("net") == "conduit" else "BZ-"
            if prefix == "BZ-":
                while f"BZ-{cnt_bz}" in used: cnt_bz += 1
                s["cod"] = f"BZ-{cnt_bz}"; used.add(s["cod"]); cnt_bz += 1
            else:
                while f"CAJA-{cnt_caja}" in used: cnt_caja += 1
                s["cod"] = f"CAJA-{cnt_caja}"; used.add(s["cod"]); cnt_caja += 1
        self.structures = world + detected; self._dirty = True

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
        """Cuántos EXTREMOS de segmento de tubería coinciden con la posición del
        buzón `s`. Un buzón al final de una línea suma 1 (un solo tramo llega); un
        vértice intermedio suma 2 (tramo que entra + tramo que sale); un cruce de
        dos utilidades, 2 o más. Solo con >=2 hay una esquina con dos tangentes,
        que es lo único que puede convertirse en un elemento curvo."""
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None:
            return 0
        tol = 14.0                              # misma tolerancia que _rebuild_structures
        n = 0
        for p in self.pipes:
            if p.get("world"):
                continue
            pts = p.get("pts")
            if not pts or len(pts) < 2:
                continue
            last = len(pts) - 1
            for i, pt in enumerate(pts):
                if math.hypot(pt[0] - sx, pt[1] - sy) <= tol:
                    n += 1 if (i == 0 or i == last) else 2
        return n

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
            item.setForeground(QtGui.QColor(130, 130, 130) if s.get("hidden") else QtGui.QColor("white"))
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
        """Tubería (dict, no 'world') cuyo pts tiene un vértice a distancia <= tol
        de (x,y), o None. La familia/tamaño de un elemento curvo se hereda de esta
        tubería — nunca se elige aparte, para que la curva calce con los tramos rectos."""
        tol2 = tol * tol
        for p in self.pipes:
            if p.get("world") or not p.get("pts"): continue
            for (vx, vy) in p["pts"]:
                if (vx - x) ** 2 + (vy - y) ** 2 <= tol2:
                    return p
        return None

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
            self.cv_radius.setValue(float(s.get("radius_ft") or 0.0))
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
        s["radius_ft"] = float(self.cv_radius.value())
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
        if item: item.setText(f"🟣 {s.get('cod', '?')}  ·  {fam}{sz}")

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
        if item: item.setText(f"📐 {c.get('cod', '?')}  ·  {len(c.get('pts') or [])} vértices")

    # ─────────────────────────── Instalador familias personalizadas ───────────
    def open_install_family_dialog(self):
        """Instala UNA familia personalizada en el catálogo Civil 3D del año e
        idioma seleccionados en la UI. Adaptación del script `install_c3d_family.py`
        que ya está validado.

        Flujo:
          1. Usuario elige la carpeta de la familia (con .xml, .dwg, .bmp adentro).
          2. Se detecta kind/units/shape leyendo el XML y el nombre.
          3. Se copia la carpeta al subcatálogo correcto del año/idioma activos.
          4. Se registra la familia en el .apc (backup automático con timestamp).
          5. Se le dice al usuario que corra PREPARAR_FAMILIAS en Civil 3D (que
             regenera el catálogo y añade las familias a una PartsList)."""
        import civil_catalog as _cc

        if not self.civil_year:
            QtWidgets.QMessageBox.warning(
                self, "Sin versión de Civil 3D",
                "Elige una versión de Civil 3D en el toolbar antes de instalar familias.")
            return
        cur_lang = _cc._current_lang
        if not cur_lang:
            QtWidgets.QMessageBox.warning(
                self, "Sin idioma seleccionado",
                "Elige un idioma en el toolbar antes de instalar familias.")
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Instalar familia personalizada — Civil 3D {self.civil_year} / {cur_lang}")
        dlg.resize(760, 480)
        lay = QtWidgets.QVBoxLayout(dlg)

        header = QtWidgets.QLabel(
            f"<b>Elige la carpeta de UNA familia</b> — debe contener el "
            f"<code>.xml</code>, el <code>.dwg</code> del Part Builder y el "
            f"<code>.bmp</code> (miniatura).<br><br>"
            f"Se instalará en el catálogo de <b>Civil 3D {self.civil_year} ({cur_lang})</b>. "
            f"El script detecta automáticamente si es tubería o estructura, sus unidades "
            f"y la forma, copia los archivos y registra la familia en el <code>.apc</code> "
            f"(con backup).<br><br>"
            f"Al terminar, ejecuta <b>PREPARAR_FAMILIAS</b> en Civil 3D — regenera el "
            f"catálogo y te deja elegir qué familias añadir a la lista de piezas del dibujo.")
        header.setWordWrap(True); lay.addWidget(header)

        # Selector carpeta origen
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Carpeta de la familia:"))
        self._if_src = QtWidgets.QLineEdit(); self._if_src.setReadOnly(True)
        prev = getattr(self, "_last_family_folder", None)
        if prev and os.path.isdir(prev): self._if_src.setText(prev)
        btn_browse = QtWidgets.QPushButton("Elegir…")
        row.addWidget(self._if_src, 1); row.addWidget(btn_browse)
        lay.addLayout(row)

        # Preview de lo que se detectó
        preview_lbl = QtWidgets.QLabel("<i>Elige una carpeta para ver qué se detecta.</i>")
        preview_lbl.setWordWrap(True); preview_lbl.setTextFormat(QtCore.Qt.RichText)
        preview_lbl.setStyleSheet("color:#b8c6df; background:#333a4a; padding:8px; border-radius:4px;")
        lay.addWidget(preview_lbl, 1)

        bb = QtWidgets.QDialogButtonBox()
        btn_install = bb.addButton("Instalar familia", QtWidgets.QDialogButtonBox.AcceptRole)
        btn_close = bb.addButton("Cerrar", QtWidgets.QDialogButtonBox.RejectRole)
        btn_install.setEnabled(False)
        lay.addWidget(bb)

        def _refresh_preview(path):
            btn_install.setEnabled(False)
            if not path or not os.path.isdir(path):
                preview_lbl.setText("<i>Elige una carpeta para ver qué se detecta.</i>")
                return
            fams = _cc.scan_family_folder_preview(path)
            if not fams:
                preview_lbl.setText(
                    "<span style='color:#e06060;'>❌ No encontré ningún .xml con "
                    ".dwg hermano en esta carpeta.</span>")
                return

            def _dot(v):
                if v: return f"<span style='color:#3fbf3f;'>{v}</span>"
                return "<span style='color:#e06060;'>⚠</span>"

            lines = [f"<b>{len(fams)} familia(s) detectadas en la carpeta:</b>",
                     "<span style='color:#8fa6bf;'>Se copiará la carpeta al subcatálogo "
                     "correspondiente y cada .xml se registrará como familia independiente "
                     "en el .apc.</span>", ""]
            for f in fams:
                lines.append(
                    f"• <code>{f['name']}</code> — tipo {_dot(f['kind'])} · "
                    f"unidades {_dot(f['units'])} · shape {_dot(f['shape'])}"
                    + ("" if f['bmp_ok'] else "  &nbsp;<span style='color:#e0a020;'>(sin .bmp)</span>"))
            # Destinos por (kind,units)
            grupos = {}
            for f in fams:
                if f['kind'] and f['units']:
                    grupos.setdefault((f['kind'], f['units']),  []).append(f['name'])
            if grupos:
                lang_root = _cc._lang_root(self.civil_year, cur_lang)
                lines.append("")
                lines.append("<b>Destinos:</b>")
                for (k, u), names in grupos.items():
                    cat = _cc._CATALOG_DIRS.get((k, u), "?")
                    dest = os.path.join(lang_root or "?", "Pipes Catalog", cat)
                    lines.append(f"  {len(names)} familia(s) → <code>{dest}</code>")
            preview_lbl.setText("<br>".join(lines))
            btn_install.setEnabled(any(f['kind'] and f['units'] and f['shape'] for f in fams))

        def _pick():
            start = getattr(self, "_last_family_folder", None) or DOWNLOADS
            path = QtWidgets.QFileDialog.getExistingDirectory(
                dlg, "Carpeta de familias (.xml + .dwg + .bmp por familia)", start)
            if not path: return
            self._last_family_folder = path
            self._if_src.setText(path); _refresh_preview(path)

        def _do_install():
            src = self._if_src.text().strip()
            if not src or not os.path.isdir(src): return
            res = _cc.install_family_folder(src, self.civil_year, cur_lang)
            if not res["ok"]:
                QtWidgets.QMessageBox.critical(dlg, "Error al instalar", res["error"] or res["summary"])
                return
            msg = res["summary"] + (
                "\n\nAHORA en Civil 3D:\n"
                "  · Ejecuta el comando  PREPARAR_FAMILIAS\n"
                "    (regenera el catálogo y te deja elegir qué familias\n"
                "    añadir a la Parts List del dibujo actual).")
            # Refrescar inmediatamente el combo de familias del panel activo
            # para que el usuario vea las familias recién instaladas sin
            # tener que deseleccionar/re-seleccionar la utilidad.
            try: self._refresh_catalog_panels()
            except Exception: pass
            QtWidgets.QMessageBox.information(dlg, "Familias instaladas", msg)

        btn_browse.clicked.connect(_pick)
        btn_install.clicked.connect(_do_install)
        btn_close.clicked.connect(dlg.reject)
        if self._if_src.text(): _refresh_preview(self._if_src.text())
        dlg.exec()

    def open_uninstall_family_dialog(self):
        import civil_catalog as _cc
        if not self.civil_year:
            QtWidgets.QMessageBox.warning(self, "Sin versión",
                "Elige una versión de Civil 3D en el toolbar antes de desinstalar familias.")
            return
        cur_lang = getattr(self, "civil_lang", None) or (
            self.cmb_lang.currentData() if hasattr(self, "cmb_lang") else None)
        if not cur_lang:
            QtWidgets.QMessageBox.warning(self, "Sin idioma",
                "Elige un idioma en el toolbar antes de desinstalar familias.")
            return

        fams = _cc.installed_custom_families(self.civil_year)
        if not fams:
            QtWidgets.QMessageBox.information(self, "Sin familias personalizadas",
                f"No se encontraron familias personalizadas instaladas en Civil 3D {self.civil_year}.")
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Desinstalar familias — Civil 3D {self.civil_year} / {cur_lang}")
        dlg.setMinimumSize(500, 400)
        lay = QtWidgets.QVBoxLayout(dlg)

        lay.addWidget(QtWidgets.QLabel(
            f"<b>Familias personalizadas en Civil 3D {self.civil_year}</b><br>"
            "Marca las que deseas desinstalar:"))

        lw = QtWidgets.QListWidget()
        lw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for f in fams:
            tipo = "Estructura" if f["kind"] == "structure" else "Tubería"
            text = f"{f['display_name']}  ({tipo} — {f['subfolder']})"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(256, f)
            lw.addItem(item)
        lay.addWidget(lw)

        bb = QtWidgets.QDialogButtonBox()
        btn_del = bb.addButton("Desinstalar seleccionadas", QtWidgets.QDialogButtonBox.AcceptRole)
        btn_del.setProperty("danger", True)
        btn_close = bb.addButton("Cerrar", QtWidgets.QDialogButtonBox.RejectRole)
        lay.addWidget(bb)

        def _do_uninstall():
            sel = [lw.item(i).data(256) for i in range(lw.count()) if lw.item(i).isSelected()]
            if not sel:
                QtWidgets.QMessageBox.warning(dlg, "Sin selección", "Selecciona al menos una familia.")
                return
            names = "\n".join(f"  · {s['display_name']}" for s in sel)
            r = QtWidgets.QMessageBox.question(
                dlg, "Confirmar desinstalación",
                f"¿Desinstalar {len(sel)} familia(s)?\n\n{names}\n\n"
                "Se quitarán del catálogo de Civil 3D. Esta acción se puede revertir "
                "reinstalando las familias desde su carpeta original.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if r != QtWidgets.QMessageBox.Yes:
                return
            ok_count = 0
            errors = []
            for s in sel:
                res = _cc.uninstall_family(
                    self.civil_year, s["name"], s["kind"], s["subfolder"], cur_lang)
                if res["ok"]:
                    ok_count += 1
                else:
                    errors.append(f"{s['display_name']}: {res['error']}")
            try:
                self._refresh_catalog_panels()
            except Exception:
                pass
            if errors:
                QtWidgets.QMessageBox.warning(dlg, "Errores",
                    f"Se desinstalaron {ok_count} de {len(sel)} familias.\n\nErrores:\n" +
                    "\n".join(errors))
            else:
                QtWidgets.QMessageBox.information(dlg, "Familias desinstaladas",
                    f"Se desinstalaron {ok_count} familia(s) correctamente.\n\n"
                    "En Civil 3D ejecuta PREPARAR_FAMILIAS para actualizar la Parts List.")
            dlg.accept()

        btn_del.clicked.connect(_do_uninstall)
        btn_close.clicked.connect(dlg.reject)
        dlg.exec()

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
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle(title); dlg.resize(w, h)
        lay = QtWidgets.QVBoxLayout(dlg); tb = QtWidgets.QTextBrowser(); tb.setOpenExternalLinks(True)
        tb.setStyleSheet("background:#1e1e1e;color:#e8e8e8;font-size:14px;"); tb.setHtml(html)
        btn = QtWidgets.QPushButton("Cerrar"); btn.clicked.connect(dlg.accept)
        lay.addWidget(tb); lay.addWidget(btn); dlg.exec()

    def show_about(self):
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Acerca de"); dlg.resize(760, 680)
        lay = QtWidgets.QVBoxLayout(dlg)
        head = QtWidgets.QLabel(
            f"<h2>Asistente C3D</h2>"
            f"<p><b>Versión {VERSION}</b> · para ingeniería civil (agua, alcantarillado, gas, "
            f"eléctrico, telefonía, drenaje).</p>"
            f"<p>Convierte un PDF de plano a DXF y te deja marcar utilidades, Multileaders y notas "
            f"sobre la imagen, exportando todo en las mismas coordenadas para abrirlo en Civil 3D.</p>"
            f"<p style='color:#888;'>GVR Engineering · sistemas.gvrpe@gmail.com</p>")
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
        <h2>Manual de usuario — v1.0.0</h2>
        <p><i>Pipeline PDF → CAD → Civil 3D para redes de utilidad (agua, alcantarillado,
        drenaje, gas, electricidad, telecomunicaciones). Trabaja en unidades imperiales (pies).</i></p>

        <h3>1. Abrir el plano</h3>
        <p><b>Archivo → Abrir PDF…</b> (o arrastralo). Cambia de página y ajusta la
        transparencia en la sección <b>Vista y páginas</b>. Rueda = zoom, botón central = pan.</p>

        <h3>2. Dibujar una utilidad</h3>
        <p>Acordeón <b>Dibujar utilidad</b> → elige el tipo (agua, alcantarillado, drenaje,
        gas, eléctrico, telecom) → clic en cada vértice, <b>Enter</b> finaliza.</p>

        <h3>3. Propiedades de la tubería</h3>
        <p>Selecciona la tubería en el inventario. En <b>Propiedades</b>:</p>
        <ul>
          <li><b>Familia de tubería</b> y <b>Tamaño</b>: se leen del catálogo Civil 3D
              instalado (selecciónalo en la barra superior).</li>
          <li><b>Elev. rasante inicial/final</b> en pies (opcional; el plugin puede autoderivar).</li>
          <li><b>Material</b> (lista fija que se mapea al catálogo).</li>
          <li><b>Cotas por tramo</b> (pestaña Utilidades, tubería de gravedad): tabla con la
              cota de cada vértice del tramo, incluido el primero y el último — cualquier
              celda es editable, y queda sincronizada con <b>Elev. rasante inicial/final</b>
              de arriba (editar en cualquiera de los 2 lugares actualiza el otro).</li>
        </ul>

        <h3>4. Buzones y cajas</h3>
        <p>Los buzones (gravedad, prefijo <code>BZ-</code>) y las cajas (conduit eléctrico/telecom,
        prefijo <code>CAJA-</code>) se detectan automáticamente en cada vértice. Cambia
        familia, tamaño y cotas en la pestaña <b>Buzones</b>. También puedes insertar uno
        en medio de una línea con <b>Herramientas → Insertar buzón en línea…</b> El botón
        <b>Ocultar buzón</b> saca un vértice de la vista y del DXF/Civil 3D como manhole
        visible (se exporta igual como "Estructura nula", invisible, para no romper la
        topología de la red) — útil para vértices auto-detectados que en realidad no son
        un acceso físico.</p>

        <h3>5. Leaders, texto, borrar zona</h3>
        <p><b>Leader</b>: orientación H/V/D, clic cabeza y final. <b>Texto libre</b>: clic +
        <b>Enter</b> para aplicar (<b>Ctrl+Shift+Enter</b> salto de línea). <b>Borrar zona</b>:
        polilínea cerrada; al exportar se elimina el plano dentro. El cajetín del PDF se
        detecta y va a la capa <b>MEMBRETE</b>.</p>

        <h3>6. Selección de versión Civil 3D</h3>
        <p>El selector <b>Civil 3D</b> de la barra superior fija la versión
        (2025/2026/2027) contra la que se listan las familias y tamaños del catálogo.</p>

        <h3>7. Centerlines de referencia (opcional)</h3>
        <p>Distintos de las utilidades — no representan ninguna tubería, sirven para mejorar
        la georreferenciación. Acordeón <b>Trazar centerline</b> → clic en cada vértice
        sobre el eje de una calle → <b>Enter</b> finaliza. Se gestionan en la pestaña
        <b>Centerlines</b> (código, longitud); seleccioná uno desde la lista o directo
        clickeándolo en el lienzo (se resalta bien grueso). Se exportan al DXF en su
        propia capa <code>REF_CENTERLINES</code>.</p>

        <h3>8. Georreferenciación (opcional)</h3>
        <p><b>Herramientas → Georreferenciar…</b> — ventana redimensionable/maximizable,
        2 paneles:</p>
        <ul>
          <li><b>Izquierda (plano)</b>: el PDF con una barra de <b>opacidad</b> (solo
              atenúa el PDF, nunca las líneas dibujadas encima — utilidades y centerlines
              se ven siempre nítidas, no pixelan al hacer zoom). Clic = punto de control,
              con imán a la línea/centerline más cercana, o al <b>cruce exacto</b> si hay
              2 líneas que se cortan cerca del clic.</li>
          <li><b>Derecha (mapa)</b>: buscá una dirección/intersección → descarga calles y
              parcelas reales de Los Ángeles (NavigateLA) sobre mapa base. Misma
              navegación que el plano (rueda = zoom, botón central + arrastrar = mover
              libremente) y el mismo imán a vértice/cruce exacto.</li>
        </ul>
        <p><b>Ctrl+Z</b> deshace el último punto agregado, en cualquiera de los 2
        paneles.</p>
        <p>Con 3+ pares (idealmente en 2 cruces distintos, o combinando el cruce que
        tengas + esquinas de parcela), pulsá
        <b>«Ajustar + RMSE»</b>: el <b>RMSE</b> es el error PROMEDIO en pies entre
        cada punto marcado y donde el ajuste calculado lo ubica — mide qué tan bien calzan
        TODOS los puntos a la vez (pasá el mouse sobre "RMSE:" para el detalle). Mientras
        más bajo, mejor. Luego <b>«💾 Guardar georreferenciación»</b> guarda el proyecto y
        cierra la ventana sola si el guardado funcionó. Al reabrir un plano ya
        georreferenciado, el mapa se recarga solo (calles/parcelas + tus puntos existentes)
        listo para seguir editando, sin tener que rebuscar la dirección. Solo para
        anteproyecto — el dato topográfico de precisión viene del levantamiento.</p>

        <h3>9. Exportar a DXF y abrir en Civil 3D</h3>
        <ul>
          <li><b>Ctrl+S</b> guarda el proyecto como <code>.digproj</code>.</li>
          <li><b>Exportar DXF</b> genera el DXF completo (dibujado + red 3D como XDATA).</li>
          <li>En Civil 3D: <code>NETLOAD</code> del plugin → <code>PANEL_REDES</code> →
              <b>Importar red desde DXF</b>. Se crean automáticamente las redes de
              gravedad, presión y conduit con sus familias y tamaños.</li>
        </ul>

        <h3>10. Property Sets a tuberías (flujo con Excel)</h3>
        <p>En el panel de Civil 3D, tras importar la red:</p>
        <ol>
          <li><b>Exportar tuberías a Excel</b> genera un <code>.xlsx</code> con columnas
              <b>Nombre</b> y <b>Tipo</b> (una fila por tubería, gravedad y presión).</li>
          <li>Agrega en Excel las columnas que quieras (una por Property Set); por ejemplo
              <code>Material_Especificacion</code>, <code>Fecha_Instalacion</code>. Rellena
              los valores por tubería (deja vacío para omitir).</li>
          <li><b>Importar Property Sets desde Excel</b>: se crean las definiciones que
              falten (una propiedad <code>Valor</code> por PS) y se adjuntan a cada tubería
              por nombre. Es idempotente — puedes reimportar el mismo archivo sin duplicar.</li>
          <li>Verifica en Civil 3D: selecciona una pipe → Properties → <b>Extended Data</b>.</li>
        </ol>
        """
        self._show_html("Manual de usuario", html, 880, 780)

    def show_shortcuts(self):
        rows = [("Ctrl+Z / Ctrl+Shift+Z", "Deshacer / Rehacer"),
                ("Enter", "Aplicar: finaliza utilidad/zona, o agrega texto/edición"),
                ("Ctrl+Shift+Enter", "Salto de línea dentro de un texto"),
                ("Escape", "Quitar la selección; si no hay, salir del modo"),
                ("Ctrl+T", "Editar/mover lo seleccionado"),
                ("Ctrl+S / Ctrl+Shift+S", "Guardar proyecto / Guardar como…"),
                ("Ctrl+W", "Cerrar proyecto (pregunta si hay cambios)"),
                ("Doble clic", "Sobre un texto: editarlo"),
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


class _NoWheelFilter(QtCore.QObject):
    """Bloquea la rueda del ratón sobre QSpinBox / QDoubleSpinBox / QComboBox
    (y sus derivados). Motivo: al desplazarse por un panel con la rueda,
    quedar el puntero sobre uno de esos campos incrementa/decrementa el valor
    o cambia el item del combo sin querer — el usuario perdía datos ya
    introducidos por un gesto que solo pretendía mover la vista.

    Se instala una sola vez sobre la QApplication y cubre TODOS los widgets
    existentes y futuros, sin tener que subclasificarlos uno por uno. El
    evento wheel se ignora en esos widgets (así lo hereda el padre y sigue
    desplazando el panel); en el resto de widgets pasa tal cual.
    """
    _WHEEL_BLOCKED = (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox)

    def eventFilter(self, obj, ev):
        if (ev.type() == QtCore.QEvent.Wheel
                and isinstance(obj, self._WHEEL_BLOCKED)):
            ev.ignore()
            return True
        return False


def main():
    app = QtWidgets.QApplication(sys.argv)
    app._no_wheel_filter = _NoWheelFilter(app)
    app.installEventFilter(app._no_wheel_filter)
    # Forzar estilo Fusion + paleta oscura SIEMPRE, independiente del tema de
    # Windows. Sin esto, cuando el usuario tiene Windows en modo claro, los
    # menús, combos, campos y bordes salen blancos sobre nuestros fondos
    # oscuros y no se ven los textos.
    app.setStyle("Fusion")
    # Paleta con GRISES NEUTROS (no azul en Button — antes contaminaba los fondos
    # de QToolBox/QGroupBox). El acento azul se limita a Highlight para selección.
    _p = QtGui.QPalette()
    _p.setColor(QtGui.QPalette.Window,          QtGui.QColor(43, 43, 43))
    _p.setColor(QtGui.QPalette.WindowText,      QtGui.QColor(232, 232, 232))
    _p.setColor(QtGui.QPalette.Base,            QtGui.QColor(51, 51, 51))
    _p.setColor(QtGui.QPalette.AlternateBase,   QtGui.QColor(60, 60, 60))
    _p.setColor(QtGui.QPalette.ToolTipBase,     QtGui.QColor(30, 30, 30))
    _p.setColor(QtGui.QPalette.ToolTipText,     QtGui.QColor(232, 232, 232))
    _p.setColor(QtGui.QPalette.Text,            QtGui.QColor(232, 232, 232))
    _p.setColor(QtGui.QPalette.Button,          QtGui.QColor(60, 60, 60))
    _p.setColor(QtGui.QPalette.ButtonText,      QtGui.QColor(232, 232, 232))
    _p.setColor(QtGui.QPalette.BrightText,      QtGui.QColor(255, 80, 80))
    _p.setColor(QtGui.QPalette.Highlight,       QtGui.QColor(60, 90, 153))
    _p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    _p.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(160, 160, 160))
    _p.setColor(QtGui.QPalette.Light,           QtGui.QColor(85, 85, 85))
    _p.setColor(QtGui.QPalette.Midlight,        QtGui.QColor(70, 70, 70))
    _p.setColor(QtGui.QPalette.Dark,            QtGui.QColor(30, 30, 30))
    _p.setColor(QtGui.QPalette.Mid,             QtGui.QColor(45, 45, 45))
    _p.setColor(QtGui.QPalette.Shadow,          QtGui.QColor(20, 20, 20))
    _p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text,       QtGui.QColor(130, 130, 130))
    _p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(130, 130, 130))
    _p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(130, 130, 130))
    app.setPalette(_p)
    # Stylesheet global de refuerzo: fija los widgets que Fusion sigue pintando
    # con acento del sistema (QToolBox tabs, QScrollArea backgrounds, tooltips).
    app.setStyleSheet("""
        /* ═══════════════════════════════════════════════════════════════════════
           Tema oscuro — referencia Photoshop dark UI.
           Usuario objetivo: persona mayor → texto 14px, targets ≥32px,
           indicadores de selección 20x20 con borde claro muy visible.

           REGLA DE ORO (bug que causaba checkboxes invisibles):
           tocar CUALQUIER propiedad QSS de QCheckBox/QRadioButton desactiva el
           render nativo de su ::indicator en Fusion y el indicador DESAPARECE.
           Por eso, si se estilan, hay que estilar el ::indicator COMPLETO.
           ═══════════════════════════════════════════════════════════════════════ */

        /* ── Base ── */
        QWidget { background-color: #2f2f2f; color: #ececec; font-size: 14px; }
        QToolTip { background-color: #1c1c1c; color: #f2f2f2; border: 1px solid #6a6a6a;
                   padding: 6px; font-size: 14px; }

        /* ── Contenedores ── */
        QScrollArea, QAbstractScrollArea { background: #2f2f2f; border: none; }
        QGroupBox { background: #2f2f2f; border: 1px solid #4d4d4d; border-radius: 5px;
                    margin-top: 14px; padding-top: 10px; font-weight: bold; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
                           left: 10px; padding: 0 6px; color: #9fc0ff; font-size: 14px; }

        /* ── Acordeón de Herramientas: cabeceras grandes y legibles ── */
        QToolBox::tab { background: #3a3a3a; color: #dcdcdc; border: 1px solid #555;
                        border-radius: 4px; padding-left: 10px; min-height: 34px;
                        font-weight: bold; }
        QToolBox::tab:hover { background: #454545; color: #ffffff; }
        QToolBox::tab:selected { background: #2f6ad9; color: #ffffff; border: 1px solid #6ba3ff; }

        /* ── Menús ── */
        QMenu { background: #333; color: #ececec; border: 1px solid #5a5a5a; padding: 4px; }
        QMenu::item { padding: 8px 26px 8px 22px; }
        QMenu::item:selected { background: #2f6ad9; color: #fff; }
        QMenu::separator { height: 1px; background: #4d4d4d; margin: 4px 8px; }
        QMenuBar { background: #2b2b2b; color: #ececec; }
        QMenuBar::item { padding: 6px 11px; }
        QMenuBar::item:selected { background: #2f6ad9; color: #fff; }
        QStatusBar { background: #2b2b2b; color: #c8ccd6; }

        /* ── Campos de entrada: hundidos, estilo Photoshop ── */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
        QListWidget, QTreeWidget, QTableWidget, QFontComboBox, QAbstractItemView {
            background: #242424; color: #f0f0f0; border: 1px solid #565656;
            border-radius: 4px; selection-background-color: #2f6ad9;
            selection-color: #ffffff;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {
            padding: 6px 8px; min-height: 22px;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus {
            border: 1px solid #6ba3ff;
        }
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
            background: #2b2b2b; color: #7d7d7d; border: 1px solid #414141;
        }

        /* Combo: NO estilar ::drop-down ni ::down-arrow - en QSS el truco de
           bordes-triangulo da un rectangulo gris. Fusion dibuja su flecha nativa. */
        QComboBox QAbstractItemView { background: #2b2b2b; color: #f0f0f0;
                                      border: 1px solid #6a6a6a;
                                      selection-background-color: #2f6ad9;
                                      selection-color: #ffffff; outline: none; }
        /* Altura de fila del popup: dedo/ratón poco preciso */
        QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 8px; }

        /* ── Botones: target ≥32px ── */
        QPushButton { background: #2f6ad9; color: #fff; border: 1px solid #4a7fe0;
                      padding: 8px 14px; border-radius: 4px; font-weight: bold;
                      min-height: 20px; }
        QPushButton:hover { background: #4a83e8; border: 1px solid #6ba3ff; }
        QPushButton:pressed { background: #2657ad; }
        QPushButton:disabled { background: #3a3a3a; color: #808080; border: 1px solid #464646; }
        /* Estado ACTIVADO de un botón toggle — antes era indistinguible del apagado */
        QPushButton:checked { background: #1f8f4a; border: 2px solid #5fe08d; color: #ffffff; }
        QPushButton:checked:hover { background: #26a758; }
        /* Botones de un solo glifo (+ - flechas de pagina, rotacion). Sin esto
           el padding generoso de arriba no deja ancho para el simbolo y el
           boton sale VACIO. Se marcan con setProperty("iconOnly", True). */
        QPushButton[iconOnly="true"] { padding: 0; font-size: 17px; font-weight: bold; }

        /* Acciones DESTRUCTIVAS — Eliminar / Borrar / Desinstalar. Rojo por
           convencion de UX (accion irreversible). Se marcan con
           setProperty("danger", True). Overrides el fondo default por especificidad. */
        QPushButton[danger="true"] { background: #d1352d; color: #ffffff; border: 1px solid #a8241c;
                                     font-weight: bold; }
        QPushButton[danger="true"]:hover  { background: #e0453c; border: 1px solid #ff5a4e; }
        QPushButton[danger="true"]:pressed{ background: #a8241c; border: 1px solid #d1352d; }
        QPushButton[danger="true"]:disabled{ background: #4a2825; color: #a08380; border: 1px solid #4a2825; }

        /* ═══ CONTROLES DE SELECCIÓN — el fix principal ═══════════════════════
           20x20 px, borde claro de 2px siempre visible sobre el fondo oscuro.
           Marcado = relleno azul brillante (inequívoco, no depende de un ✓ fino). */
        QCheckBox, QRadioButton { background: transparent; color: #ececec;
                                  spacing: 10px; padding: 4px 0; }
        QCheckBox:disabled, QRadioButton:disabled { color: #8a8a8a; }

        QCheckBox::indicator, QRadioButton::indicator { width: 20px; height: 20px; }

        QCheckBox::indicator { border: 2px solid #8c8c8c; border-radius: 4px; background: #232323; }
        QCheckBox::indicator:hover { border: 2px solid #6ba3ff; background: #2b2b2b; }
        QCheckBox::indicator:checked { background: #2f6ad9; border: 2px solid #8ec2ff; }
        QCheckBox::indicator:checked:hover { background: #4a83e8; border: 2px solid #bcdcff; }
        QCheckBox::indicator:indeterminate { background: #7a7a7a; border: 2px solid #b4b4b4; }
        QCheckBox::indicator:disabled { border: 2px solid #565656; background: #2b2b2b; }
        QCheckBox::indicator:checked:disabled { background: #3f5480; border: 2px solid #5c6f95; }

        QRadioButton::indicator { border: 2px solid #8c8c8c; border-radius: 11px; background: #232323; }
        QRadioButton::indicator:hover { border: 2px solid #6ba3ff; }
        QRadioButton::indicator:checked { background: #2f6ad9; border: 5px solid #232323; }
        QRadioButton::indicator:disabled { border: 2px solid #565656; }

        /* Indicador de los items checkables de las listas (Zonas activadas/desactivadas) */
        QListWidget::indicator, QTreeWidget::indicator, QTableWidget::indicator {
            width: 20px; height: 20px; border: 2px solid #8c8c8c;
            border-radius: 4px; background: #232323;
        }
        QListWidget::indicator:checked, QTreeWidget::indicator:checked,
        QTableWidget::indicator:checked { background: #2f6ad9; border: 2px solid #8ec2ff; }

        /* ── Listas / tablas: filas altas y legibles ── */
        QListWidget::item, QTreeWidget::item { padding: 7px 6px; border-radius: 3px; }
        QListWidget::item:hover, QTreeWidget::item:hover { background: #3a3a3a; }
        QListWidget::item:selected, QTreeWidget::item:selected { background: #2f6ad9; color: #fff; }
        QTableWidget { gridline-color: #464646; }
        QTableWidget::item { padding: 5px; }
        QTableWidget::item:selected { background: #2f6ad9; color: #fff; }
        QHeaderView::section { background: #3a3a3a; color: #e4e4e4; border: none;
                               border-right: 1px solid #4d4d4d;
                               border-bottom: 1px solid #4d4d4d;
                               padding: 7px 6px; font-weight: bold; }

        /* ── Pestañas ── */
        QTabWidget::pane { background: #2f2f2f; border: 1px solid #4d4d4d; border-radius: 4px; }
        QTabBar::tab { background: #383838; color: #d4d4d4; padding: 8px 14px;
                       border: 1px solid #4d4d4d; border-bottom: none;
                       border-top-left-radius: 4px; border-top-right-radius: 4px; }
        QTabBar::tab:hover { background: #434343; color: #fff; }
        QTabBar::tab:selected { background: #2f6ad9; color: #fff; }

        /* ── Barras de desplazamiento: anchas, fáciles de agarrar ── */
        QScrollBar:vertical { background: #2b2b2b; width: 15px; margin: 0; border: none; }
        QScrollBar::handle:vertical { background: #5a5a5a; min-height: 34px;
                                      border-radius: 7px; margin: 2px; }
        QScrollBar::handle:vertical:hover { background: #757575; }
        QScrollBar:horizontal { background: #2b2b2b; height: 15px; margin: 0; border: none; }
        QScrollBar::handle:horizontal { background: #5a5a5a; min-width: 34px;
                                        border-radius: 7px; margin: 2px; }
        QScrollBar::handle:horizontal:hover { background: #757575; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; border: none; background: none; }
        QScrollBar::add-page, QScrollBar::sub-page { background: none; }

        /* ── Spinbox dentro de la tabla de cotas: sin el padding global, o desborda
              la altura de la fila y se solapa con la de al lado ── */
        QTableWidget QDoubleSpinBox, QTableWidget QSpinBox {
            padding: 2px 6px; min-height: 0; border-radius: 3px;
        }
        QTableWidget QLabel { padding: 2px 6px; }

        /* ── Docks ── */
        QDockWidget { color: #ececec; font-weight: bold; }
        QDockWidget::title { background: #262626; padding: 8px 10px; border-bottom: 1px solid #4d4d4d; }
        QSplitter::handle { background: #4d4d4d; }
        QSplitter::handle:horizontal { width: 5px; }
        QSplitter::handle:vertical { height: 5px; }
    """)
    win = Main(); win.show()
    if len(sys.argv) > 1:
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
