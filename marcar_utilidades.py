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
from ezdxf.enums import TextEntityAlignment
from PySide6 import QtCore, QtGui, QtWidgets

import config as C
import vector_pipeline as VP

VERSION = "0.3.1"

TIPOS = [
    ("Agua (W)", "AGUA"), ("Alcantarillado (SS)", "ALCANTARILLADO"),
    ("Drenaje (SD)", "DRENAJE"), ("Gas (G)", "GAS"),
    ("Eléctrico (E)", "ELECTRICO"), ("Eléctrico aéreo E(OH)", "ELECTRICO_AEREO"),
    ("Telefonía (T)", "TELECOM"), ("Telefonía aérea T(OH)", "TELECOM_AEREO"),
]
ACI_RGB = {1: (255, 60, 60), 2: (235, 215, 40), 3: (60, 210, 60), 4: (60, 210, 210),
           5: (90, 140, 255), 6: (230, 90, 230), 7: (235, 235, 235), 8: (150, 150, 150),
           30: (255, 150, 40)}
LEADER_TEXT_FT = 3.0
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
LEADER_ORIENT = [("h", "Horizontal (recto)"), ("v", "Vertical (recto)"), ("d", "Diagonal (con landing)")]
BTN_ON = "background:#2e9e4f;color:white;font-weight:bold;padding:8px;border-radius:4px;"
BTN_OFF = "background:#3c5a99;color:white;padding:8px;border-radius:4px;"
Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE = 0, 1, 5, 8

CHANGELOG = [
    ("0.3.1", [
        ("added", "En el cambiador de páginas se puede escribir un número de página y dar Enter."),
        ("fixed", "El editor de texto es una caja flotante: Enter aplica y clic fuera también dibuja el texto."),
        ("fixed", "El botón de aumentar la altura del texto ya funciona (se agregaron botones − / +)."),
        ("fixed", "Multileader vertical y horizontal ahora son perfectamente rectos y la punta de flecha sale recta."),
        ("fixed", "La landing del Multileader se adapta al largo del texto."),
        ("fixed", "En Diagonal el texto ya no se cruza con la landing (queda encima)."),
        ("fixed", "Editar Multileader: Ctrl+Shift+Enter hace salto de línea al otro lado de la landing."),
        ("fixed", "Al cambiar de hoja los textos y Multileaders ya no se dibujan gigantes (tamaño acotado)."),
        ("fixed", "Extender desde un vértice (forma de F) tolera el temblor del ratón al hacer clic."),
    ]),
    ("0.3.0", [
        ("fixed", "Navegación de páginas con botones ◀ ▶ (ya no hay que escribir el número primero)."),
        ("fixed", "El texto libre se agrega con Enter; ya no depende de hacer clic en el panel."),
        ("added", "Enter aplica el texto/Multileader; Ctrl+Shift+Enter (o Shift+Enter) hace salto de línea."),
        ("added", "Textos seleccionables, editables (doble clic) y movibles, con estilo modificable después de crearlos."),
        ("added", "Multileader editable (doble clic) con saltos de línea."),
        ("fixed", "Horizontal ahora es recto (sin quiebre); la opción con landing pasó a Diagonal."),
        ("added", "Vertical recto con texto vertical pegado a la línea."),
        ("added", "Extender desde un vértice: clic en un vértice y luego en el dibujo para ramificar (forma de F)."),
        ("added", "Los Multileader se digitalizan como entidad MULTILEADER de CAD (no como grupo)."),
        ("fixed", "Los polígonos de borrado quedan detrás de las tuberías (solo tapan el plano)."),
        ("added", "El área de listas se puede agrandar arrastrando el separador."),
        ("added", "Se renombró todo a 'Multileader'."),
    ]),
    ("0.2.0", [
        ("fixed", "Error al abrir un proyecto (objetos gráficos ya eliminados y zonas en formato antiguo)."),
        ("fixed", "Enter finaliza de forma fiable la utilidad que estás dibujando."),
        ("added", "Cerrar proyecto: pregunta si deseas guardar los cambios."),
        ("added", "Aviso de cambios sin guardar al cerrar la aplicación."),
        ("added", "Historial de versiones desplegable en 'Acerca de'."),
    ]),
    ("0.1.0", [
        ("added", "Utilidad abandonada con línea ──/── W ──."),
        ("added", "Multileader vertical; edición de texto; texto libre con estilos."),
        ("added", "Panel de zonas borradas; selección por clic; guardar en el mismo archivo."),
        ("added", "Menús Archivo / Edición / Ayuda con manual y atajos."),
        ("base", "Dibujar utilidades, Multileaders, texto, borrar zonas, OCR/ICR, proyectos y export a DXF."),
    ]),
    ("0.0.0", [
        ("base", "Primera versión interna: digitalización PDF→DXF y marcado básico de utilidades."),
    ]),
]


def aci_qcolor(a): return QtGui.QColor(*ACI_RGB.get(a, (235, 235, 235)))
def layer_qcolor(l): return aci_qcolor(C.OUTPUT_LAYERS.get(l, 7))


def swatch_icon(color, size=14):
    pm = QtGui.QPixmap(size, size); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setBrush(color); p.setPen(QtGui.QPen(QtGui.QColor(70, 70, 70)))
    p.drawRect(0, 0, size - 1, size - 1); p.end(); return QtGui.QIcon(pm)


def qimage_to_gray(qimg):
    qimg = qimg.convertToFormat(QtGui.QImage.Format_Grayscale8)
    w, h = qimg.width(), qimg.height(); ptr = qimg.constBits()
    arr = np.frombuffer(ptr, np.uint8).reshape(h, qimg.bytesPerLine())[:, :w]
    return arr.copy()


def point_in_poly(x, y, poly):
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


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


class OcrWorker(QtCore.QThread):
    done = QtCore.Signal(object, str)

    def __init__(self, gray): super().__init__(); self.gray = gray

    def run(self):
        try:
            import cv2, pytesseract
            from pytesseract import Output
            from collections import defaultdict
            g = self.gray; H, W = g.shape
            s = min(1.0, 2400.0 / max(H, W))
            gd = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else g
            Hd, Wd = gd.shape
            codes = {90: cv2.ROTATE_90_CLOCKWISE, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
            def back(o, ox, oy):
                if o == 0: return ox, oy
                if o == 90: return oy, Hd - 1 - ox
                return Wd - 1 - oy, ox
            out = []
            for o in (0, 90, 270):
                img = gd if o == 0 else cv2.rotate(gd, codes[o])
                data = pytesseract.image_to_data(img, output_type=Output.DICT, config="--psm 11")
                lines = defaultdict(list)
                for i in range(len(data["text"])):
                    t = (data["text"][i] or "").strip()
                    if not t: continue
                    try: conf = float(data["conf"][i])
                    except: conf = -1
                    if conf < 25: continue
                    k = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                    lines[k].append((data["left"][i], data["top"][i], data["width"][i], data["height"][i], t))
                for ws in lines.values():
                    ws.sort(key=lambda w: w[0]); txt = " ".join(w[4] for w in ws)
                    x = min(w[0] for w in ws); y = min(w[1] for w in ws)
                    x1 = max(w[0] + w[2] for w in ws); y1 = max(w[1] + w[3] for w in ws)
                    cs = [back(o, x, y), back(o, x1, y), back(o, x, y1), back(o, x1, y1)]
                    xs = [c[0] / s for c in cs]; ys = [c[1] / s for c in cs]
                    out.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), txt))
            self.done.emit(out, "")
        except Exception as e:
            self.done.emit([], str(e))


class IcrWorker(QtCore.QThread):
    done = QtCore.Signal(object, str)

    def __init__(self, gray): super().__init__(); self.gray = gray

    def run(self):
        try:
            import easyocr, cv2
            g = self.gray; H, W = g.shape
            s = min(1.0, 2000.0 / max(H, W))
            gd = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else g
            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            out = []
            for bbox, txt, conf in reader.readtext(gd, detail=1, paragraph=False):
                if not txt.strip() or conf < 0.15: continue
                xs = [p[0] / s for p in bbox]; ys = [p[1] / s for p in bbox]
                out.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), txt.strip()))
            self.done.emit(out, "")
        except ModuleNotFoundError:
            self.done.emit(None, "missing")
        except Exception as e:
            self.done.emit([], str(e))


class Canvas(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float, object)
    dbl = QtCore.Signal(float, float)

    def __init__(self, win):
        super().__init__(); self.win = win
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(28, 28, 28)); self.setAcceptDrops(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.pixmap_item = None; self._pan = False; self._pan0 = None; self._moving = False

    def set_image(self, qimg):
        self.scene().clear()
        self.pixmap_item = self.scene().addPixmap(QtGui.QPixmap.fromImage(qimg))
        self.pixmap_item.setZValue(Z_PDF)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform(); self.fitInView(self.pixmap_item, QtCore.Qt.KeepAspectRatio)

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
        self.erase_regions = []; self._erase_pts = []
        self.mode = "idle"; self._pending = None
        self.snap = False; self.snap_r = 14
        self.show_text_boxes = False; self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
        self.sel_pipe = -1; self.sel_leader = -1; self.sel_region = -1; self.sel_text = -1; self._no_center = False
        self._move0 = None; self._drag_vertex = None; self._edit_pts = None; self._edit_closed = False
        self._move_kind = None; self._moved = False; self._press_xy = None; self._last_xy = None
        self._extending = False; self._ext_layer = None
        self._editor = None; self._undo, self._redo, self._overlay = [], [], []
        self._dirty = False; self._style_guard = False
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
        mhelp = mb.addMenu("A&yuda")
        self._menu_act(mhelp, "Acerca de…", self.show_about)
        self._menu_act(mhelp, "Manual de usuario", self.show_manual)
        self._menu_act(mhelp, "Atajos de teclado", self.show_shortcuts)

        tb = self.addToolBar("Vista")
        self.btn_prev = QtWidgets.QPushButton("◀"); self.btn_prev.setFixedWidth(36); self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next = QtWidgets.QPushButton("▶"); self.btn_next.setFixedWidth(36); self.btn_next.clicked.connect(self._next_page)
        tb.addWidget(QtWidgets.QLabel(" Página ")); tb.addWidget(self.btn_prev)
        self.page_edit = QtWidgets.QLineEdit(); self.page_edit.setFixedWidth(48); self.page_edit.setAlignment(QtCore.Qt.AlignCenter)
        self.page_edit.setToolTip("Escribe un número de página y pulsa Enter")
        self.page_edit.returnPressed.connect(self._goto_page_edit); tb.addWidget(self.page_edit)
        self.lbl_page = QtWidgets.QLabel(" / — "); tb.addWidget(self.lbl_page); tb.addWidget(self.btn_next)
        tb.addSeparator()
        self.chk_snap = QtWidgets.QCheckBox("Imán al trazo"); self.chk_snap.toggled.connect(lambda v: setattr(self, "snap", v))
        tb.addWidget(self.chk_snap)

        dock = QtWidgets.QDockWidget("Herramientas", self); dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        container = QtWidgets.QWidget(); cv = QtWidgets.QVBoxLayout(container)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True)
        top = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(top)

        gm = QtWidgets.QGroupBox("¿Qué quieres hacer?"); lm = QtWidgets.QVBoxLayout(gm)
        self.btn_pipe = QtWidgets.QPushButton("✏  Dibujar utilidad"); self.btn_pipe.clicked.connect(self.toggle_pipe)
        self.btn_leader = QtWidgets.QPushButton("↳  Colocar Multileader"); self.btn_leader.clicked.connect(self.start_leader)
        self.btn_text = QtWidgets.QPushButton("T  Texto libre"); self.btn_text.clicked.connect(self.toggle_text_mode)
        self.btn_erase = QtWidgets.QPushButton("▭  Borrar zona (polígono)"); self.btn_erase.clicked.connect(self.toggle_erase)
        self.chk_txt = QtWidgets.QCheckBox("Ayudar con textos impresos (OCR)"); self.chk_txt.toggled.connect(self.toggle_text_boxes)
        self.chk_icr = QtWidgets.QCheckBox("ICR manuscrita (EasyOCR, offline)"); self.chk_icr.toggled.connect(self.toggle_icr)
        self.lbl_mode = QtWidgets.QLabel("Modo: inactivo"); self.lbl_mode.setStyleSheet("color:#9cf;"); self.lbl_mode.setWordWrap(True)
        for w in (self.btn_pipe, self.btn_leader, self.btn_text, self.btn_erase, self.chk_txt, self.chk_icr, self.lbl_mode): lm.addWidget(w)
        v.addWidget(gm)

        self.gt = QtWidgets.QGroupBox("Tipo de utilidad"); lgt = QtWidgets.QVBoxLayout(self.gt)
        self.type_list = QtWidgets.QListWidget()
        for label, layer in TIPOS:
            it = QtWidgets.QListWidgetItem(swatch_icon(layer_qcolor(layer)), label)
            it.setData(QtCore.Qt.UserRole, layer); it.setForeground(QtGui.QColor("white")); self.type_list.addItem(it)
        self.type_list.setCurrentRow(0); self.type_list.currentRowChanged.connect(lambda _: self._redraw())
        lgt.addWidget(self.type_list)
        self.chk_ab = QtWidgets.QCheckBox("Abandonado (línea ──/── W ──)")
        lgt.addWidget(self.chk_ab); v.addWidget(self.gt)

        self.gtxt = QtWidgets.QGroupBox("Estilo de texto"); lgx = QtWidgets.QVBoxLayout(self.gtxt)
        self.font_combo = QtWidgets.QFontComboBox(); self.font_combo.setCurrentFont(QtGui.QFont(C.TEXT_FONT))
        self.font_combo.currentFontChanged.connect(lambda _: self._style_changed())
        r = QtWidgets.QHBoxLayout(); r.addWidget(QtWidgets.QLabel("Altura (pies):"))
        b_minus = QtWidgets.QPushButton("−"); b_minus.setFixedWidth(30); b_minus.clicked.connect(lambda: self._bump_size(-0.5))
        self.size_spin = QtWidgets.QDoubleSpinBox(); self.size_spin.setRange(0.5, 200); self.size_spin.setValue(3.0)
        self.size_spin.setSingleStep(0.5); self.size_spin.setMinimumHeight(28)
        self.size_spin.valueChanged.connect(lambda _: self._style_changed())
        b_plus = QtWidgets.QPushButton("+"); b_plus.setFixedWidth(30); b_plus.clicked.connect(lambda: self._bump_size(0.5))
        r.addWidget(b_minus); r.addWidget(self.size_spin); r.addWidget(b_plus)
        self.chk_bold = QtWidgets.QCheckBox("Negrita"); self.chk_bold.toggled.connect(lambda _: self._style_changed())
        lgx.addWidget(self.font_combo); lgx.addLayout(r); lgx.addWidget(self.chk_bold)
        lgx.addWidget(QtWidgets.QLabel("<i>Enter aplica · Ctrl+Shift+Enter salta de línea</i>"))
        v.addWidget(self.gtxt)

        self.gcur = QtWidgets.QGroupBox("En curso"); lc = QtWidgets.QHBoxLayout(self.gcur)
        self.btn_fin = QtWidgets.QPushButton("Finalizar (Enter)"); self.btn_fin.clicked.connect(self._on_enter)
        b_up = QtWidgets.QPushButton("Deshacer punto"); b_up.clicked.connect(self.undo)
        lc.addWidget(self.btn_fin); lc.addWidget(b_up); v.addWidget(self.gcur)

        self.ga = QtWidgets.QGroupBox("Multileader"); lga = QtWidgets.QVBoxLayout(self.ga)
        self.orient_combo = QtWidgets.QComboBox()
        for oid, lbl in LEADER_ORIENT: self.orient_combo.addItem(lbl, oid)
        lga.addWidget(QtWidgets.QLabel("Orientación:")); lga.addWidget(self.orient_combo)
        self.chk_custom = QtWidgets.QCheckBox("Usar texto personalizado"); self.chk_custom.toggled.connect(self._toggle_custom)
        lga.addWidget(self.chk_custom)
        self.txt_edit = QtWidgets.QLineEdit(); self.txt_edit.setPlaceholderText("texto personalizado…"); self.txt_edit.setEnabled(False)
        lga.addWidget(self.txt_edit)
        lga.addWidget(QtWidgets.QLabel("Textos (columna TEXTO del Excel):"))
        self.text_list = QtWidgets.QListWidget(); lga.addWidget(self.text_list); v.addWidget(self.ga, 1)

        scroll.setWidget(top); splitter.addWidget(scroll)

        ge = QtWidgets.QGroupBox("Marcado (arrastra el separador para agrandar)"); lge = QtWidgets.QVBoxLayout(ge)
        self.tabs = QtWidgets.QTabWidget()
        self.pipe_list = QtWidgets.QListWidget(); self.pipe_list.currentRowChanged.connect(self._sel_pipe)
        self.lead_list = QtWidgets.QListWidget(); self.lead_list.currentRowChanged.connect(self._sel_leader)
        self.txt_marks_list = QtWidgets.QListWidget(); self.txt_marks_list.currentRowChanged.connect(self._sel_text)
        self.region_list = QtWidgets.QListWidget(); self.region_list.currentRowChanged.connect(self._sel_region)
        self.region_list.itemChanged.connect(self._region_toggled)
        self.tabs.addTab(self.pipe_list, "Utilidades"); self.tabs.addTab(self.lead_list, "Multileaders")
        self.tabs.addTab(self.txt_marks_list, "Textos"); self.tabs.addTab(self.region_list, "Zonas borradas")
        self.tabs.currentChanged.connect(self._tab_changed); lge.addWidget(self.tabs)
        rr = QtWidgets.QHBoxLayout()
        self.btn_ct = QtWidgets.QPushButton("Cambiar tipo"); self.btn_ct.clicked.connect(self.change_pipe_type)
        self.btn_mv = QtWidgets.QPushButton("Editar/mover (Ctrl+T)"); self.btn_mv.clicked.connect(self.enter_move)
        self.btn_edit = QtWidgets.QPushButton("Editar texto"); self.btn_edit.clicked.connect(self.edit_selected_text)
        self.btn_del = QtWidgets.QPushButton("Eliminar"); self.btn_del.clicked.connect(self.delete_selected)
        for b in (self.btn_ct, self.btn_mv, self.btn_edit, self.btn_del): rr.addWidget(b)
        lge.addLayout(rr); splitter.addWidget(ge)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2); splitter.setSizes([560, 320])
        cv.addWidget(splitter, 1)

        gs = QtWidgets.QGroupBox("Salida"); lgs = QtWidgets.QVBoxLayout(gs)
        b = QtWidgets.QPushButton("Digitalizar plano + exportar DXF"); b.setStyleSheet("font-weight:bold;padding:10px;")
        b.clicked.connect(self.run_pipeline); lgs.addWidget(b); cv.addWidget(gs)

        dock.setWidget(container); dock.setMinimumWidth(350)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        self.status = self.statusBar(); self._info("Abre o arrastra un PDF/proyecto.")

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

    def _on_escape(self):
        if self.mode == "pipe" and self.cur_pts:
            self._push(); self.cur_pts = []; self._extending = False; self._update_ui(); self._redraw(); self._info("Puntos cancelados")
        elif self.mode == "erase" and self._erase_pts:
            self._erase_pts = []; self._redraw(); self._info("Zona cancelada")
        elif self.sel_pipe >= 0 or self.sel_leader >= 0 or self.sel_region >= 0 or self.sel_text >= 0:
            self._deselect_all(); self._info("Selección quitada")
        else:
            self.set_mode("idle"); self._info("Salió del modo")

    def _deselect_all(self):
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        for lst in (self.pipe_list, self.lead_list, self.txt_marks_list, self.region_list):
            lst.blockSignals(True); lst.setCurrentRow(-1); lst.clearSelection(); lst.blockSignals(False)
        if self.mode == "move": self.set_mode("idle")
        self._update_ui(); self._redraw()

    def _info(self, m): self.status.showMessage(m)

    def _update_ui(self):
        m = self.mode
        def st(btn, on): btn.setStyleSheet(BTN_ON if on else BTN_OFF)
        st(self.btn_pipe, m == "pipe"); st(self.btn_leader, m in ("leader1", "leader2"))
        st(self.btn_text, m == "text"); st(self.btn_erase, m == "erase")
        self.btn_pipe.setText("■  Salir de dibujar utilidad" if m == "pipe" else "✏  Dibujar utilidad")
        self.btn_leader.setText("●  Coloque Multileader…" if m in ("leader1", "leader2") else "↳  Colocar Multileader")
        self.btn_erase.setText("■  Terminar zona (Enter)" if m == "erase" else "▭  Borrar zona (polígono)")
        self.gt.setVisible(m in ("pipe", "move"))
        self.gtxt.setVisible(m == "text" or (self.tabs.currentIndex() == 2 and self.sel_text >= 0))
        self.gcur.setVisible((m == "pipe" and len(self.cur_pts) >= 1) or (m == "erase" and len(self._erase_pts) >= 1))
        self.btn_fin.setEnabled((m == "pipe" and len(self.cur_pts) >= 2) or (m == "erase" and len(self._erase_pts) >= 3))
        ti = self.tabs.currentIndex()
        self.btn_ct.setVisible(ti == 0); self.btn_mv.setVisible(ti in (0, 2, 3)); self.btn_edit.setVisible(ti in (1, 2))
        self.lbl_mode.setText({"idle": "Modo: inactivo  ·  clic en el dibujo para seleccionar",
                               "pipe": ("Modo: EXTENDIENDO desde el vértice — clic agrega puntos, Enter finaliza"
                                        if self._extending else "Modo: dibujar utilidad  ·  Enter finaliza"),
                               "leader1": "Modo: Multileader — clic en la PUNTA (a qué señala)",
                               "leader2": "Modo: Multileader — clic dónde va el TEXTO",
                               "text": "Modo: texto libre — clic donde escribir · Enter aplica",
                               "erase": "Modo: borrar zona — clic para el polígono, Enter cierra",
                               "move": "Modo: editar — arrastra vértice · clic en tramo inserta · clic-en-vértice extiende (F) · clic derecho elimina"}.get(m, ""))

    def set_mode(self, m):
        if m not in ("leader1", "leader2"): self._pending = None
        if m != "erase": self._erase_pts = []
        if m != "pipe": self._extending = False
        self.mode = m; self._update_ui(); self._redraw()

    def _tab_changed(self, _): self._update_ui(); self._redraw()
    def toggle_pipe(self): self.set_mode("idle" if self.mode == "pipe" else "pipe")
    def toggle_text_mode(self): self.set_mode("idle" if self.mode == "text" else "text")
    def toggle_erase(self): self.set_mode("idle" if self.mode == "erase" else "erase")
    def active_layer(self):
        it = self.type_list.currentItem(); return it.data(QtCore.Qt.UserRole) if it else "AGUA"

    def _toggle_custom(self, on):
        self.txt_edit.setEnabled(on); self.text_list.setEnabled(not on)
        if on:
            self.text_list.blockSignals(True); self.text_list.setCurrentRow(-1); self.text_list.clearSelection(); self.text_list.blockSignals(False)
        else:
            self.txt_edit.clear()

    # ─────────────────────────── undo/redo ───────────────────────────
    def _snap_state(self):
        return copy.deepcopy(dict(cur_pts=self.cur_pts, pipes=self.pipes, leaders=self.leaders,
                                  text_marks=self.text_marks, erase_regions=self.erase_regions))

    def _push(self):
        self._undo.append(self._snap_state()); self._redo.clear(); self._dirty = True
        if len(self._undo) > 400: self._undo.pop(0)

    def _restore(self, s):
        self.cur_pts, self.pipes = s["cur_pts"], s["pipes"]
        self.leaders, self.text_marks = s["leaders"], s["text_marks"]
        self.erase_regions = s.get("erase_regions", [])
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
        self._reset_model(); self._update_page_label(); self._info(f"Página {idx + 1} · escala 1\"={self.scale*72:.0f}'")

    def _reset_model(self):
        self.cur_pts = []; self.pipes = []; self.leaders = []; self.text_marks = []
        self.erase_regions = []; self._erase_pts = []
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        self._overlay = []; self._close_editor(); self._dirty = False; self._extending = False
        self._undo.clear(); self._redo.clear(); self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
        self.set_mode("idle"); self._refresh_lists(); self._redraw()

    # ─────────────────────────── proyecto ───────────────────────────
    def _write_project(self, path):
        self._busy("Guardando proyecto…")
        try:
            model = dict(pipes=self.pipes, leaders=self.leaders, text_marks=self.text_marks,
                         erase_regions=self.erase_regions,
                         tf=dict(scale=self.scale, zoom=self.zoom, rot=self.rot, W=self.W, H=self.H,
                                 derot=[self.derot.a, self.derot.b, self.derot.c, self.derot.d, self.derot.e, self.derot.f]),
                         pdf_name=os.path.basename(self.pdf_path or ""), version=VERSION)
            ba = QtCore.QByteArray(); buf = QtCore.QBuffer(ba); buf.open(QtCore.QIODevice.WriteOnly)
            self.canvas.pixmap_item.pixmap().save(buf, "PNG")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("model.json", json.dumps(model)); z.writestr("page.png", bytes(ba))
            self.project_path = path; self._dirty = False; self._info(f"Proyecto guardado: {os.path.basename(path)}")
        finally: self._unbusy()

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
            with zipfile.ZipFile(path) as z:
                model = json.loads(z.read("model.json")); png = z.read("page.png")
            qimg = QtGui.QImage.fromData(png, "PNG")
            self._overlay = []; self._close_editor()
            self.canvas.set_image(qimg); self.gray = qimage_to_gray(qimg)
            tf = model["tf"]; self.scale = tf["scale"]; self.zoom = tf["zoom"]; self.rot = tf["rot"]
            self.W, self.H = tf["W"], tf["H"]; self.derot = fitz.Matrix(*tf["derot"])
            self.pageH_px = qimg.height()
            self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
            self.pdf_path = None; self.doc = None; self.project_path = path; self.page_idx = 0
            self.pipes = model.get("pipes", []); self.leaders = model.get("leaders", [])
            self.text_marks = model.get("text_marks", [])
            self.erase_regions = [r if isinstance(r, dict) else {"pts": r, "enabled": True}
                                  for r in model.get("erase_regions", [])]
            self.cur_pts = []; self._erase_pts = []; self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
            self._undo.clear(); self._redo.clear(); self._dirty = False
            self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
            self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._redraw()
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
        self.canvas.scene().clear(); self.canvas.pixmap_item = None
        self.pdf_path = None; self.doc = None; self.project_path = None; self.gray = None
        self.pipes = []; self.leaders = []; self.text_marks = []; self.erase_regions = []
        self.cur_pts = []; self._erase_pts = []; self._overlay = []; self._close_editor()
        self.sel_pipe = self.sel_leader = self.sel_region = self.sel_text = -1
        self.ocr_boxes = []; self._tess_boxes = []; self._icr_boxes = []
        self._undo.clear(); self._redo.clear(); self._dirty = False; self.show_text_boxes = False
        for chk in (self.chk_txt, self.chk_icr):
            chk.blockSignals(True); chk.setChecked(False); chk.blockSignals(False)
        self.set_mode("idle"); self._refresh_lists(); self._update_page_label(); self._info("Proyecto cerrado.")

    def closeEvent(self, e):
        if self._confirm_discard(): e.accept()
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
            self._push(); self._pending["tp"] = (x, y); self.leaders.append(self._pending)
            self._pending = None; self.set_mode("idle"); self._refresh_lists(); self._info("Multileader colocado")
        elif self.mode == "idle":
            self._pick(x, y)

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
        for i, tm in enumerate(self.text_marks):        # textos primero (blancos pequeños)
            if self._text_hit(tm, x, y):
                self._no_center = True; self.tabs.setCurrentIndex(2); self.txt_marks_list.setCurrentRow(i)
                self._no_center = False; return
        thr = 10.0 / max(1e-6, self.canvas.transform().m11()); best, bd = -1, thr
        for i, p in enumerate(self.pipes):
            for a, b in zip(p["pts"], p["pts"][1:]):
                d = VP._pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < bd: bd, best = d, i
        if best >= 0:
            self._no_center = True; self.tabs.setCurrentIndex(0); self.pipe_list.setCurrentRow(best)
            self._no_center = False

    def _snap(self, x, y):
        if not self.snap or self.gray is None: return (x, y)
        h, w = self.gray.shape; xi, yi, r = int(x), int(y), self.snap_r
        win = self.gray[max(0, yi - r):min(h, yi + r + 1), max(0, xi - r):min(w, xi + r + 1)] < 128
        if not win.any(): return (x, y)
        ys, xs = np.nonzero(win); return (max(0, xi - r) + xs.mean(), max(0, yi - r) + ys.mean())

    # ─────────────────────────── editar / mover ───────────────────────────
    def _current_kind(self):
        ti = self.tabs.currentIndex()
        if ti == 0 and 0 <= self.sel_pipe < len(self.pipes): return "pipe"
        if ti == 2 and 0 <= self.sel_text < len(self.text_marks): return "text"
        if ti == 3 and 0 <= self.sel_region < len(self.erase_regions): return "region"
        return None

    def enter_move(self):
        if self._current_kind(): self.set_mode("move"); self._info("Arrastra para mover · clic en vértice extiende (F) · clic derecho elimina")
        else: self._info("Selecciona primero una utilidad, texto o zona")

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
        pts = self.pipes[self.sel_pipe]["pts"] if kind == "pipe" else self.erase_regions[self.sel_region]["pts"]
        self._edit_pts = pts; self._edit_closed = (kind == "region")
        vi, vd = -1, thr
        for i, (px, py) in enumerate(pts):
            d = math.hypot(px - x, py - y)
            if d < vd: vd, vi = d, i
        if vi >= 0:
            self._drag_vertex = vi; self._move0 = None; return
        si, sd = -1, thr
        for idx, a, b in self._segments(pts, self._edit_closed):
            d = VP._pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
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
        pts = self._edit_pts
        if pts is None: return
        if self._drag_vertex is not None:
            pts[self._drag_vertex] = (x, y); self._redraw(); return
        if self._move0 is not None:
            dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
            for i in range(len(pts)): pts[i] = (pts[i][0] + dx, pts[i][1] + dy)
            self._redraw()

    def end_move(self):
        # clic (casi sin arrastrar) sobre un vértice de una tubería → extender en forma de F
        dist = math.hypot(self._last_xy[0] - self._press_xy[0], self._last_xy[1] - self._press_xy[1]) \
            if (self._last_xy and self._press_xy) else 0
        if (self._move_kind == "pipe" and self._drag_vertex is not None and dist < 6
                and 0 <= self.sel_pipe < len(self.pipes)):
            vpos = self.pipes[self.sel_pipe]["pts"][self._drag_vertex]
            self._ext_layer = self.pipes[self.sel_pipe]["layer"]; self._extending = True
            self.cur_pts = [tuple(vpos)]; self.set_mode("pipe")
            self._info("Extendiendo desde el vértice: clic para agregar puntos, Enter finaliza")
        self._move0 = None; self._drag_vertex = None; self._move_kind = None

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
        if len(self.cur_pts) >= 2:
            layer = self._ext_layer if self._extending else self.active_layer()
            ab = False if self._extending else self.chk_ab.isChecked()
            self._push(); self.pipes.append({"layer": layer, "pts": self.cur_pts[:], "ab": ab})
        self.cur_pts = []; self._extending = False; self._ext_layer = None
        self._refresh_lists(); self._update_ui(); self._redraw()

    def _sel_pipe(self, r):
        self.sel_pipe = r
        if not self._no_center and 0 <= r < len(self.pipes):
            pts = self.pipes[r]["pts"]; mid = pts[len(pts) // 2]; self.canvas.centerOn(mid[0], mid[1])
        self._update_ui(); self._redraw()

    def _sel_leader(self, r):
        self.sel_leader = r
        if not self._no_center and 0 <= r < len(self.leaders) and self.leaders[r].get("tp"):
            tp = self.leaders[r]["tp"]; self.canvas.centerOn(tp[0], tp[1])
        self._update_ui(); self._redraw()

    def _sel_text(self, r):
        self.sel_text = r
        if 0 <= r < len(self.text_marks):
            tm = self.text_marks[r]
            if not self._no_center: self.canvas.centerOn(tm["pos"][0], tm["pos"][1])
            self._style_guard = True
            self.font_combo.setCurrentFont(QtGui.QFont(tm.get("font", C.TEXT_FONT)))
            self.size_spin.setValue(tm.get("size_ft", 3.0)); self.chk_bold.setChecked(bool(tm.get("bold")))
            self._style_guard = False
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

    def _bump_size(self, delta):
        self.size_spin.setValue(round(max(0.5, self.size_spin.value() + delta), 2))

    def _px_for_ft(self, ft):
        raw = ft / self.scale * self.zoom if self.scale else ft * self.zoom
        cap = self.pageH_px * 0.06 if self.pageH_px else 200
        return max(8.0, min(raw, cap))

    def _style_changed(self):
        if self._style_guard: return
        if self.tabs.currentIndex() == 2 and 0 <= self.sel_text < len(self.text_marks):
            tm = self.text_marks[self.sel_text]; self._push()
            tm["font"] = self.font_combo.currentFont().family(); tm["size_ft"] = self.size_spin.value()
            tm["bold"] = self.chk_bold.isChecked(); tm["h"] = tm["size_ft"] / self.scale * self.zoom
            self._redraw()

    def change_pipe_type(self):
        if 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes[self.sel_pipe]["layer"] = self.active_layer()
            self.pipes[self.sel_pipe]["ab"] = self.chk_ab.isChecked(); self._refresh_lists(); self._redraw()

    def edit_selected_text(self):
        ti = self.tabs.currentIndex()
        if ti == 1 and 0 <= self.sel_leader < len(self.leaders): self._edit_leader_text(self.sel_leader)
        elif ti == 2 and 0 <= self.sel_text < len(self.text_marks): self._edit_text_mark(self.sel_text)

    def delete_selected(self):
        ti = self.tabs.currentIndex()
        if ti == 0 and 0 <= self.sel_pipe < len(self.pipes):
            self._push(); self.pipes.pop(self.sel_pipe); self.sel_pipe = -1
        elif ti == 1 and 0 <= self.sel_leader < len(self.leaders):
            self._push(); self.leaders.pop(self.sel_leader); self.sel_leader = -1
        elif ti == 2 and 0 <= self.sel_text < len(self.text_marks):
            self._push(); self.text_marks.pop(self.sel_text); self.sel_text = -1
        elif ti == 3 and 0 <= self.sel_region < len(self.erase_regions):
            self._push(); self.erase_regions.pop(self.sel_region); self.sel_region = -1
        self._refresh_lists(); self._redraw()

    def _refresh_lists(self):
        self.pipe_list.blockSignals(True); self.pipe_list.clear()
        for i, p in enumerate(self.pipes, 1):
            tag = " (AB)" if p.get("ab") else ""
            it = QtWidgets.QListWidgetItem(swatch_icon(layer_qcolor(p["layer"])), f"{i}. {p['layer']}{tag} ({len(p['pts'])})")
            it.setForeground(QtGui.QColor("white")); self.pipe_list.addItem(it)
        self.pipe_list.blockSignals(False)
        self.lead_list.blockSignals(True); self.lead_list.clear()
        for i, ld in enumerate(self.leaders, 1): self.lead_list.addItem(f"{i}. {ld['text'][:28].replace(chr(10), ' / ')}")
        self.lead_list.blockSignals(False)
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
        self.pipes = [p for p in self.pipes if not all(point_in_poly(px, py, poly) for (px, py) in p["pts"])]
        self.leaders = [l for l in self.leaders if not (l.get("tp") and point_in_poly(l["tp"][0], l["tp"][1], poly))]
        self.text_marks = [t for t in self.text_marks if not point_in_poly(t["pos"][0], t["pos"][1], poly)]
        self._erase_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info("Zona agregada: al exportar también se borra la geometría base del plano dentro de ella.")

    # ─────────────────────────── Multileader ───────────────────────────
    def start_leader(self):
        if self.chk_custom.isChecked():
            txt = self.txt_edit.text().strip()
        else:
            it = self.text_list.currentItem(); txt = it.text() if it and self.text_list.currentRow() >= 0 else ""
        if not txt:
            QtWidgets.QMessageBox.information(self, "Sin texto",
                "Activa 'texto personalizado' y escribe, o desactívalo y selecciona un texto del Excel."); return
        self._pending = {"text": txt, "orient": self.orient_combo.currentData(), "arrow": None, "tp": None}
        self.set_mode("leader1"); self._info("Clic en la PUNTA (a qué señala)")

    def _edit_leader_text(self, idx):
        ld = self.leaders[idx]; tp = ld["tp"]
        def commit(val):
            self._close_editor()
            if val.strip(): self._push(); ld["text"] = val.rstrip("\n"); self._refresh_lists()
            self._redraw()
        self._open_editor(tp[0], tp[1] - self.leader_hpx, ld["text"], commit)

    def _leader_geo(self, ld):
        """Geometría del Multileader (px). Devuelve: segs (preview), label_pos, rot,
        side (conexión CAD), verts_px (línea de la flecha), insert_px, dogleg (pies), H.
        La punta de flecha se orienta con segs[0][1] (el punto contiguo a la flecha)."""
        ax, ay = ld["arrow"]; tx, ty = ld["tp"]; H = self.leader_hpx
        lines = ld["text"].split("\n"); maxlen = max((len(s) for s in lines), default=1); nlines = len(lines)
        tw = max(maxlen * H * 0.55, H); th = nlines * H; gap = H * 0.45; orient = ld.get("orient", "h")
        if orient == "v":                                  # recto vertical, texto vertical pegado
            signY = -1 if ty < ay else 1
            length = max(abs(ty - ay), tw + gap)           # la landing se adapta al texto
            ey = ay + signY * length
            side = "top" if signY < 0 else "bottom"
            lbl = (ax + gap, ey + (tw if signY < 0 else 0))
            return dict(segs=[[(ax, ay), (ax, ey)]], label_pos=lbl, rot=-90, side=side,
                        verts_px=[(ax, ay)], insert_px=(ax, ey), dogleg=0.0, H=H)
        if orient == "h":                                  # recto horizontal
            signX = 1 if tx >= ax else -1
            length = max(abs(tx - ax), tw + gap)
            ex = ax + signX * length; side = "right" if signX > 0 else "left"
            lbl = (ex + gap, ay - th / 2) if signX > 0 else (ex - gap - tw, ay - th / 2)
            return dict(segs=[[(ax, ay), (ex, ay)]], label_pos=lbl, rot=0, side=side,
                        verts_px=[(ax, ay)], insert_px=(ex + signX * gap, ay), dogleg=0.0, H=H)
        # diagonal: flecha → 2º clic → landing horizontal → texto ENCIMA del landing
        right = tx >= ax; sgn = 1 if right else -1
        lx = tx + sgn * (tw + gap); text_x = min(tx, lx) + gap
        side = "right" if right else "left"
        # la 1ª línea queda ENCIMA del landing; las líneas extra caen al otro lado
        lbl = (text_x, ty - H - gap * 0.7)
        return dict(segs=[[(ax, ay), (tx, ty), (lx, ty)]], label_pos=lbl, rot=0, side=side,
                    verts_px=[(ax, ay), (tx, ty)], insert_px=(tx + sgn * gap, ty), dogleg=LEADER_TEXT_FT * 1.5, H=H)

    # ─────────────────────────── texto libre ───────────────────────────
    def _new_free_text(self, x, y):
        def commit(val):
            self._close_editor()
            if val.strip():
                self._push()
                self.text_marks.append({"pos": (x, y), "text": val.rstrip("\n"),
                                        "h": self.size_spin.value() / self.scale * self.zoom,
                                        "size_ft": self.size_spin.value(), "font": self.font_combo.currentFont().family(),
                                        "bold": self.chk_bold.isChecked(), "free": True})
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
            t = sc.addText(ld["text"]); t.setDefaultTextColor(col)
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
            t = sc.addText(tm["text"]); t.setDefaultTextColor(QtGui.QColor(120, 220, 120))
            hpx = self._px_for_ft(tm["size_ft"]) if "size_ft" in tm else tm.get("h", 16)
            f = t.font(); f.setPixelSize(max(6, int(hpx)))
            if tm.get("font"): f.setFamily(tm["font"])
            f.setBold(bool(tm.get("bold"))); t.setFont(f)
            t.setPos(tm["pos"][0], tm["pos"][1]); t.setZValue(Z_MARK); self._overlay.append(t)
            if i == self.sel_text and self.tabs.currentIndex() == 2:
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
        mp = fitz.Point(x / self.zoom, y / self.zoom) * self.derot
        px, py = mp.x, mp.y; s, r, W, H = self.scale, self.rot, self.W, self.H
        if r == 0: return (px * s, (H - py) * s)
        if r == 90: return (py * s, px * s)
        if r == 180: return ((W - px) * s, py * s)
        return (py * s, px * s)

    # ─────────────────────────── exportar ───────────────────────────
    def run_pipeline(self):
        if self.canvas.pixmap_item is None:
            QtWidgets.QMessageBox.information(self, "Nada", "Abre un PDF o proyecto."); return
        name = os.path.splitext(os.path.basename(self.pdf_path))[0] if self.pdf_path else "proyecto"
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar DXF", os.path.join(DOWNLOADS, name + "_completo.dxf"), "DXF (*.dxf)")
        if not out: return
        self._out = out
        if not self.pdf_path:
            try:
                doc = ezdxf.new("R2010", setup=True); doc.header["$INSUNITS"] = C.INSUNITS
                self._merge_into(doc); doc.saveas(out)
                QtWidgets.QMessageBox.information(self, "Listo", f"Exportado (sin plano base):\n{out}")
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
            doc = ezdxf.readfile(tmp); self._merge_into(doc); doc.saveas(self._out)
            if os.path.exists(tmp): os.remove(tmp)
            nreg = sum(1 for r in self.erase_regions if r.get("enabled", True))
            QtWidgets.QMessageBox.information(self, "Listo",
                f"Exportado:\n{self._out}\n\n{len(self.pipes)} utilidades, {len(self.leaders)} Multileaders, "
                f"{len(self.text_marks)} textos, {nreg} zonas borradas.")
            self._info("DXF completo exportado.")
        except Exception as e:
            import traceback; QtWidgets.QMessageBox.critical(self, "Error al guardar", f"{e}\n{traceback.format_exc()}")

    def _merge_into(self, doc):
        VP.setup_linetypes(doc); msp = doc.modelspace()
        self._apply_erase(msp)
        for p in self.pipes:
            VP.ensure_layer(doc, p["layer"]); att = {"layer": p["layer"]}
            if p.get("ab"):
                lt = C.LAYER_LINETYPE_AB.get(p["layer"])
                if lt and lt in doc.linetypes: att["linetype"] = lt
            msp.add_lwpolyline([self._to_cad(x, y) for (x, y) in p["pts"]], dxfattribs=att)
        VP.ensure_layer(doc, "ANOTACION")
        if "CAD_TEXT" not in doc.styles: doc.styles.add("CAD_TEXT", font=C.TEXT_FONT)
        for ld in self.leaders:
            if ld.get("arrow") and ld.get("tp"): self._add_leader(doc, msp, ld)
        for tm in self.text_marks:
            if tm.get("free"): self._add_free_text(doc, msp, tm)
            else: self._replace_text(doc, msp, tm)

    def _apply_erase(self, msp):
        regions = [r for r in self.erase_regions if r.get("enabled", True)]
        if not regions: return
        polys = [[self._to_cad(px, py) for (px, py) in r["pts"]] for r in regions]
        def inside(pt): return any(point_in_poly(pt[0], pt[1], poly) for poly in polys)
        for e in list(msp):
            t = e.dxftype()
            try:
                if t == "LWPOLYLINE":
                    pts = [(p[0], p[1]) for p in e.get_points()]
                    hit = inside((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
                elif t == "LINE":
                    a, b = e.dxf.start, e.dxf.end; hit = inside(((a.x + b.x) / 2, (a.y + b.y) / 2))
                elif t in ("TEXT", "MTEXT"):
                    ins = e.dxf.insert; hit = inside((ins.x, ins.y))
                elif t in ("CIRCLE", "ARC"):
                    c = e.dxf.center; hit = inside((c.x, c.y))
                else: hit = False
                if hit: msp.delete_entity(e)
            except Exception: continue

    def _add_leader(self, doc, msp, ld):
        """Exporta como entidad MULTILEADER de CAD. Si falla, cae al grupo."""
        try:
            from ezdxf.math import Vec2
            from ezdxf.render.mleader import ConnectionSide
            geo = self._leader_geo(ld)
            verts = [Vec2(*self._to_cad(*p)) for p in geo["verts_px"]]
            insert = Vec2(*self._to_cad(*geo["insert_px"]))
            smap = {"right": ConnectionSide.right, "left": ConnectionSide.left,
                    "top": ConnectionSide.top, "bottom": ConnectionSide.bottom}
            content = ld["text"].replace("\n", "\\P")
            for side in (smap[geo["side"]], ConnectionSide.right, ConnectionSide.left):
                try:
                    b = msp.add_multileader_mtext("Standard")
                    b.set_content(content, char_height=LEADER_TEXT_FT)
                    b.set_connection_properties(dogleg_length=geo["dogleg"])
                    b.add_leader_line(side, verts)
                    b.build(insert=insert)
                    return
                except Exception:
                    continue
        except Exception:
            pass
        self._add_leader_group(doc, msp, ld)

    def _add_leader_group(self, doc, msp, ld):
        geo = self._leader_geo(ld); ents = []
        for s in geo["segs"]:
            ents.append(msp.add_lwpolyline([self._to_cad(x, y) for (x, y) in s], dxfattribs={"layer": "ANOTACION"}))
        a = self._to_cad(*ld["arrow"]); b = self._to_cad(*geo["segs"][0][1])
        ang = math.atan2(a[1] - b[1], a[0] - b[0]); L = LEADER_TEXT_FT * 0.8
        p1 = (a[0] - L * math.cos(ang - 0.4), a[1] - L * math.sin(ang - 0.4))
        p2 = (a[0] - L * math.cos(ang + 0.4), a[1] - L * math.sin(ang + 0.4))
        ents.append(msp.add_solid([a, p1, p2, a], dxfattribs={"layer": "ANOTACION"}))
        m = msp.add_mtext(ld["text"].replace("\n", "\\P"),
                          dxfattribs={"layer": "ANOTACION", "style": "CAD_TEXT", "char_height": LEADER_TEXT_FT})
        m.set_location(self._to_cad(*ld["tp"]), attachment_point=4); ents.append(m)
        try:
            g = doc.groups.new()
            with g.edit_data() as data: data.extend(ents)
        except Exception: pass

    def _add_free_text(self, doc, msp, tm):
        font = tm.get("font", C.TEXT_FONT); bold = bool(tm.get("bold")); h = tm.get("size_ft", LEADER_TEXT_FT)
        style = f"TXT_{font}_{'B' if bold else 'N'}".replace(" ", "_")[:60]
        if style not in doc.styles:
            try: doc.styles.add(style, font=font)
            except Exception: style = "CAD_TEXT"
        body = tm["text"].replace("\n", "\\P")
        if bold: body = f"{{\\f{font}|b1;{body}}}"
        m = msp.add_mtext(body, dxfattribs={"layer": "ANOTACION", "style": style, "char_height": h})
        m.set_location(self._to_cad(*tm["pos"]), attachment_point=1)

    def _replace_text(self, doc, msp, tm):
        bx, by, bw, bh = tm.get("box", (tm["pos"][0] - 30, tm["pos"][1] - 10, 60, 20))
        cs = [self._to_cad(bx, by), self._to_cad(bx + bw, by), self._to_cad(bx, by + bh), self._to_cad(bx + bw, by + bh)]
        xs = [c[0] for c in cs]; ys = [c[1] for c in cs]; pad = LEADER_TEXT_FT * 2
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        for e in list(msp.query("TEXT MTEXT")):
            if e.dxf.layer in ("ANOTACION", "TEXTO"):
                ins = e.dxf.insert
                if x0 <= ins.x <= x1 and y0 <= ins.y <= y1: msp.delete_entity(e)
        t = msp.add_text(tm["text"], height=LEADER_TEXT_FT, dxfattribs={"layer": "ANOTACION", "style": "CAD_TEXT"})
        t.set_placement(self._to_cad(tm["pos"][0], tm["pos"][1]), align=TextEntityAlignment.MIDDLE_CENTER)

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
                "fixed": ("#6cc5e0", "✎ corregida"), "base": ("#cfcfcf", "•")}
        for ver, items in CHANGELOG:
            tb = QtWidgets.QTextBrowser(); tb.setStyleSheet("background:#1e1e1e;color:#e8e8e8;border:none;")
            lis = "".join(f'<li style="color:{icon[s][0]};margin-bottom:4px;"><b>[{icon[s][1]}]</b> {t}</li>' for s, t in items)
            tb.setHtml(f"<ul>{lis}</ul>"); box.addItem(tb, f"v{ver}")
        lay.addWidget(box, 1)
        btn = QtWidgets.QPushButton("Cerrar"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
        dlg.exec()

    def show_manual(self):
        html = """
        <h2>Manual de usuario</h2>
        <h3>1. Abrir el plano</h3>
        <p><b>Archivo → Abrir PDF…</b> (o arrastra el PDF). Navega entre páginas con los botones
        <b>◀ ▶</b> de la barra superior. Puedes arrastrar un <b>Excel</b> para cargar sus textos.</p>
        <h3>2. Dibujar una utilidad</h3>
        <ol>
          <li>Elige el <b>Tipo de utilidad</b> (color por servicio).</li>
          <li>Pulsa <b>✏ Dibujar utilidad</b> (se pone verde) y haz clic punto por punto.</li>
          <li>Pulsa <b>Enter</b> (o clic derecho / doble clic) para finalizar.</li>
          <li>Marca <b>Abandonado</b> para la línea ──/── W ──.</li>
        </ol>
        <h3>3. Colocar un Multileader</h3>
        <ol>
          <li>Elige la orientación: <b>Horizontal</b> (recto), <b>Vertical</b> (recto, texto vertical
              pegado a la línea) o <b>Diagonal</b> (con landing/quiebre).</li>
          <li>Marca <b>Usar texto personalizado</b> y escríbelo, o selecciona un texto del Excel.</li>
          <li>Pulsa <b>↳ Colocar Multileader</b>, clic en la <b>punta</b> y luego dónde va el <b>texto</b>.
              El lado (izq/der o arriba/abajo) lo decide el segundo clic.</li>
          <li>Para editarlo: <b>doble clic</b> sobre el texto. <b>Enter</b> aplica, <b>Ctrl+Shift+Enter</b>
              hace salto de línea.</li>
        </ol>
        <p>Al exportar, cada Multileader se digitaliza como una <b>entidad MULTILEADER</b> de CAD.</p>
        <h3>4. Texto libre</h3>
        <ol>
          <li>Pulsa <b>T Texto libre</b>, ajusta fuente, altura y negrita (puedes cambiarlos también
              mientras escribes o después, con el texto seleccionado).</li>
          <li>Haz clic donde escribir, teclea y pulsa <b>Enter</b> para agregarlo
              (<b>Ctrl+Shift+Enter</b> = salto de línea).</li>
          <li>Los textos son <b>seleccionables</b> (clic), <b>editables</b> (doble clic) y
              <b>movibles</b> (Editar/mover). Su estilo se cambia al seleccionarlos.</li>
        </ol>
        <h3>5. OCR e ICR</h3>
        <p>Marca <b>Ayudar con textos impresos (OCR)</b> o <b>ICR manuscrita</b>. Aparecen recuadros:
        clic en uno, corrige y confirma con Enter.</p>
        <h3>6. Borrar una zona</h3>
        <p>Pulsa <b>▭ Borrar zona</b>, marca el polígono y pulsa <b>Enter</b>. Se rellena de blanco y
        queda <b>detrás de las tuberías</b> (solo tapa el plano). Al exportar borra la geometría base
        dentro. En la pestaña <b>Zonas borradas</b> puedes activarla/desactivarla, editarla o eliminarla.</p>
        <h3>7. Editar, mover y extender</h3>
        <ul>
          <li>Clic en el dibujo selecciona (sin mover la vista); desde las listas la vista se centra.</li>
          <li><b>Editar/mover</b> (Ctrl+T): arrastra un vértice, clic en un tramo inserta un vértice,
              clic derecho sobre un vértice lo elimina, y arrastrar lejos mueve todo.</li>
          <li><b>Extender en forma de F</b>: en editar, haz un clic sobre un vértice (sin arrastrar) y
              luego clic en el dibujo para dibujar una nueva rama desde ese vértice.</li>
          <li><b>Escape</b> quita la selección; de nuevo sale del modo.</li>
        </ul>
        <h3>8. Guardar y exportar</h3>
        <ul>
          <li><b>Guardar proyecto</b> (Ctrl+S): guarda todo en un <b>.digproj</b> (se comparte y abre
              sin el PDF). Si abriste un proyecto, actualiza ese mismo archivo.</li>
          <li><b>Digitalizar plano + exportar DXF</b>: genera el DXF final (plano base + tu marcado).</li>
          <li><b>Cerrar proyecto</b> (Ctrl+W): pregunta si hay cambios sin guardar.</li>
        </ul>
        <h3>9. Historial de versiones</h3>
        <p><b>Ayuda → Acerca de</b>: versión actual e historial desplegable por versión (verde=nueva,
        celeste=corregida, rojo=quitada).</p>
        """
        self._show_html("Manual de usuario", html, 840, 740)

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
    app = QtWidgets.QApplication(sys.argv)
    win = Main(); win.show()
    if len(sys.argv) > 1:
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
