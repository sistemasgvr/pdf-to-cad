"""recognition_dialog.py — Asistente v1: tipo PDF, elegir hoja, preview, roles OCG.

El preview dibuja las pipes reconocidas como el trazo manual y, al Continuar,
se importan al editor (misma forma que finish_pipe). Las capas usadas como
líneas/bóvedas se asignan AUTOMÁTICAMENTE por nombre (`recognition.classify_ocg`)
y se muestran de forma informativa en el preview; «Ajustar capas…» abre el
diálogo de roles solo si hace falta (plot con otros nombres). Desde el preview
también se puede «Componer hoja…» (compositor → capas → nuevo preview).
Textos en español vía i18n.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr, N_
from nucleo.model import TIPOS
from ui.comun.ui_common import layer_qcolor, QA_UNCOVERED, QA_OFFPATTERN
from ui.comun.icons import icon
from ui.comun.widgets import (ZoomPanView, maximize_on_show, GripSplitter,
                     CollapsiblePanel, NaturalHeightScroll)
from ui.asistente.wizard_widgets import NoEscapeClose, StepBar, OpacityButton, wizard_header, wizard_footer
from ui.comun.busy import busy
from ui.comun import fondo_pdf
from reconocimiento import recognition as rec
from reconocimiento import recognition_cache
from ui.asistente.recognition_summary_view import SummaryPanel, separator, utility_swatch
from ui.asistente.recognition_review_view import ReviewPanel
from ui.asistente.recognition_layers_view import UsedLayersPanel
from ui.asistente.recognition_preview_draw import (DIM_OPACITY, _display_runs, _draw_fillet, _draw_orphan,
                                      _draw_poly, _draw_vault, _draw_vault_outline,
                                      draw_line_halo, draw_vault_halo, vault_points)
from ui.comun import theme as _theme

# Etiqueta de cada utilidad tal como en el desplegable «Tipo de utilidad».
_UTILITY_LABEL = {key: label for label, key in TIPOS}
# Acciones que devuelve el preview.
PREVIEW_IMPORT, PREVIEW_CANCEL = "import", "cancel"
PREVIEW_CHANGE_SHEET, PREVIEW_ADJUST_LAYERS = "change_sheet", "adjust_layers"
PREVIEW_SHEET_LAYERS = "sheet_layers"      # paso «2 Capas de la hoja» de la cabecera


# ─────────────────────────── Paso 1: tipo de PDF ───────────────────────────
def choose_pdf_type(parent) -> str | None:
    """Devuelve 'plotted', 'image' o None si cancela."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(_tr("Tipo de PDF"))
    dlg.resize(480, 220)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        _tr("¿Qué tipo de PDF estás abriendo?")))
    info = QtWidgets.QLabel(
        _tr("PDF bien ploteado: tiene capas vectoriales (OCG). "
            "PDF imagen: escaneo o raster sin capas útiles."))
    info.setWordWrap(True)
    lay.addWidget(info)

    btns = QtWidgets.QDialogButtonBox()
    btn_plot = btns.addButton(
        _tr("PDF bien ploteado (capas)"), QtWidgets.QDialogButtonBox.AcceptRole)
    btn_img = btns.addButton(
        _tr("PDF imagen / escaneo"), QtWidgets.QDialogButtonBox.ActionRole)
    btn_cancel = btns.addButton(QtWidgets.QDialogButtonBox.Cancel)
    btn_cancel.setText(_tr("Cancelar"))
    lay.addWidget(btns)

    result = {"choice": None}

    def _plotted():
        result["choice"] = "plotted"
        dlg.accept()

    def _image():
        result["choice"] = "image"
        dlg.accept()

    btn_plot.clicked.connect(_plotted)
    btn_img.clicked.connect(_image)
    btn_cancel.clicked.connect(dlg.reject)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return result["choice"]


# ─────────────────────────── Paso 1b: elegir hoja ───────────────────────────
def choose_page(parent, doc, current: int = 0) -> int | None:
    """Si hay más de una página, pide elegir (preselecciona `current`).
    Devuelve índice 0-based o None."""
    n = doc.page_count
    if n <= 1:
        return 0

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(_tr("Seleccionar hoja"))
    dlg.resize(640, 480)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        _tr("Este PDF tiene {n} hojas. Elige la hoja a reconocer:").format(n=n)))

    split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
    lst = QtWidgets.QListWidget()
    for i in range(n):
        lst.addItem(_tr("Hoja {i}").format(i=i + 1))
    lst.setCurrentRow(max(0, min(int(current or 0), n - 1)))
    split.addWidget(lst)

    thumb = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
    thumb.setMinimumSize(320, 240)
    thumb.setStyleSheet("background:#222;color:#aaa;")
    split.addWidget(thumb)
    split.setStretchFactor(1, 1)
    lay.addWidget(split, 1)

    def _update_thumb(row: int):
        if row < 0 or row >= n:
            return
        try:
            import fitz
            page = doc[row]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25), alpha=False)
            qimg = QtGui.QImage(
                bytes(pix.samples), pix.width, pix.height,
                pix.stride, QtGui.QImage.Format_RGB888).copy()
            pm = QtGui.QPixmap.fromImage(qimg)
            thumb.setPixmap(pm.scaled(
                thumb.size(), QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation))
        except Exception as e:
            thumb.setText(str(e))

    lst.currentRowChanged.connect(_update_thumb)
    _update_thumb(lst.currentRow())

    bb = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    bb.button(QtWidgets.QDialogButtonBox.Ok).setText(_tr("Usar esta hoja"))
    bb.button(QtWidgets.QDialogButtonBox.Cancel).setText(_tr("Cancelar"))
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)

    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return max(0, lst.currentRow())


# ───────────────── Paso: confirmar roles OCG (líneas / buzones) ─────────────
_ROLE_LABELS = (
    (rec.ROLE_LINEAS, N_("Líneas")),
    (rec.ROLE_BUZONES, N_("Buzones / estructuras")),
    (rec.ROLE_IGNORAR, N_("Ignorar")),
)


def _suggest_role(L: dict, utility: str) -> str:
    """Rol sugerido: por el nombre de la capa y, si sus líneas lo dicen con sus LETRAS
    (`pdf_layers.page_layers` → `letter_utilities`), por las letras: una capa que es
    TODA de esta utilidad por sus letras es «Líneas»; la que su nombre hacía de esta
    utilidad y sus letras dicen otra, «Ignorar»."""
    if list(L.get("letter_utilities") or ()) == [utility]:
        return rec.ROLE_LINEAS
    if L.get("name_utility") == utility:
        return rec.ROLE_IGNORAR
    return rec.suggest_layer_role(L["name"], utility)


class LayerRolesDialog(QtWidgets.QDialog):
    """Ajuste OPCIONAL de qué capas son líneas y cuáles bóvedas (si el plot usa
    otros nombres). Se abre desde «Ajustar capas…» del preview."""

    def __init__(self, parent, layers: list[dict], utility="ELECTRICO", current_roles=None):
        super().__init__(parent)
        self.utility = utility
        utility_name = _tr(_UTILITY_LABEL.get(utility, utility))
        self.setWindowTitle(_tr("Ajustar capas de {u}").format(u=utility_name))
        self.resize(560, 520)
        self._rows = []  # (name, combo)

        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr(
            "Indica qué capas son líneas y cuáles estructuras de {u}. "
            "Al aceptar se vuelve a reconocer la hoja.".format(u=utility_name)))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(_tr("Buscar capa…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            _tr("Capa"), _tr("Trazos"), _tr("Rol")])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        lay.addWidget(self.table, 1)

        ordered = sorted(
            layers,
            key=lambda L: (
                0 if _suggest_role(L, utility) != rec.ROLE_IGNORAR else 1,
                -int(L.get("path_count") or 0),
                (L.get("short") or L["name"]).upper(),
            ),
        )
        self.table.setRowCount(len(ordered))
        for row, L in enumerate(ordered):
            name = L["name"]
            short = L.get("short") or name
            it0 = QtWidgets.QTableWidgetItem(short)
            it0.setFlags(it0.flags() & ~QtCore.Qt.ItemIsEditable)
            it0.setToolTip(name)
            it0.setData(QtCore.Qt.UserRole, name)
            self.table.setItem(row, 0, it0)
            it1 = QtWidgets.QTableWidgetItem(str(L.get("path_count", 0)))
            it1.setFlags(it1.flags() & ~QtCore.Qt.ItemIsEditable)
            it1.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, 1, it1)
            combo = QtWidgets.QComboBox()
            for role, label in _ROLE_LABELS:
                combo.addItem(_tr(label), role)
            sug = (_suggest_role(L, utility) if current_roles is None else
                   next((role for role in (rec.ROLE_LINEAS, rec.ROLE_BUZONES)
                         if name in current_roles.get(role, ())), rec.ROLE_IGNORAR))
            idx = next((i for i, (r, _) in enumerate(_ROLE_LABELS) if r == sug), 2)
            combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, 2, combo)
            self._rows.append((name, combo))

        # A themed combo is taller than Qt's default table row. Give every
        # row room for the full control, including its border and padding.
        row_height = max((combo.sizeHint().height() + 6 for _, combo in self._rows),
                         default=self.table.fontMetrics().height() + 12)
        self.table.verticalHeader().setMinimumSectionSize(row_height)
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        hint = QtWidgets.QLabel(_tr(
            "Debe haber al menos una capa en «Líneas» para continuar."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{_theme.tokens().text_muted};")
        lay.addWidget(hint)

        bb = QtWidgets.QDialogButtonBox()
        self.btn_ok = bb.addButton(_tr("Continuar"), QtWidgets.QDialogButtonBox.AcceptRole)
        btn_cancel = bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
        btn_cancel.setText(_tr("Cancelar"))
        bb.accepted.connect(self._try_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _filter(self, text: str):
        q = (text or "").strip().upper()
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            tip = (it.toolTip() or "") if it else ""
            txt = (it.text() or "") if it else ""
            hide = bool(q) and q not in txt.upper() and q not in tip.upper()
            self.table.setRowHidden(row, hide)

    def roles(self) -> dict:
        lineas, buzones = [], []
        for name, combo in self._rows:
            role = combo.currentData()
            if role == rec.ROLE_LINEAS:
                lineas.append(name)
            elif role == rec.ROLE_BUZONES:
                buzones.append(name)
        return {rec.ROLE_LINEAS: lineas, rec.ROLE_BUZONES: buzones}

    def _try_accept(self):
        if not self.roles().get(rec.ROLE_LINEAS):
            QtWidgets.QMessageBox.warning(
                self, _tr("Ajustar capas"),
                _tr("Asigna al menos una capa como «Líneas»."))
            return
        self.accept()


def choose_layer_roles(parent, layers: list[dict], utility="ELECTRICO", current_roles=None) -> dict | None:
    """Devuelve {lineas:[…], buzones:[…]} o None si cancela.

    `layers`: dicts de pdf_layers.page_layers (al menos name, short, path_count).
    """
    candidates = [L for L in layers if int(L.get("path_count") or 0) > 0]
    if not candidates:
        return {rec.ROLE_LINEAS: [], rec.ROLE_BUZONES: []}
    dlg = LayerRolesDialog(parent, candidates, utility, current_roles=current_roles)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return dlg.roles()


_PreviewView = ZoomPanView


GOTO_MIN_SIDE_PX = 420.0   # clic en un aviso: lado mínimo de la zona mostrada (px de la imagen)


# El dibujo sobre la hoja vive en recognition_preview_draw; «Capas usadas», en
# recognition_layers_view (clic = resaltar la capa en la hoja).


class RecognitionPreviewDialog(NoEscapeClose, QtWidgets.QDialog):
    """Muestra el PDF + overlay de líneas (listas para el editor) y bóvedas.

    `action` al cerrar: PREVIEW_IMPORT (Continuar), PREVIEW_CANCEL,
    PREVIEW_CHANGE_SHEET (paso 1 «Componer hoja» de la barra de pasos),
    PREVIEW_SHEET_LAYERS (paso 2 «Capas de la hoja») o PREVIEW_ADJUST_LAYERS
    («Ajustar capas…»). Quien lo abre (Main) ejecuta el flujo correspondiente.
    Esc no la cierra (`NoEscapeClose`): quita el resaltado de «Capas usadas».
    """

    def __init__(self, parent, qimg: QtGui.QImage, result, utility_layer="ELECTRICO",
                 page_count: int | None = None, fondo: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(_tr("Vista previa del reconocimiento"))
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1200, 760)
        maximize_on_show(self)
        self._results = list(result) if isinstance(result, (list, tuple)) else [result]
        self._results = [item for item in self._results if item is not None]
        if not self._results:
            raise ValueError("La vista previa necesita al menos un resultado")
        self._result = self._results[0]  # compatibilidad con consumidores antiguos
        utilities = tuple(item.utility for item in self._results)
        utility_title = (rec.utilities_label(utilities) if len(utilities) > 1 else
                         _UTILITY_LABEL.get(utilities[0], utilities[0]))
        self.action = PREVIEW_CANCEL

        # Cabecera (pasos, a todo el ancho) · Para verificar | vista | resumen · pie
        # (pedido del usuario 2026-10-03: «Revisar» y «Detalles» a la IZQUIERDA; el
        # panel derecho juntaba resumen, avisos y capas y la izquierda quedaba vacía).
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)   # margen uniforme alrededor de vista y paneles
        root.setSpacing(10)
        # pasos del asistente: 1 y 2 son clicables (volver atrás); es la única navegación
        self.steps = StepBar(2)
        self.steps.stepClicked.connect(
            lambda i: self._finish(PREVIEW_CHANGE_SHEET if i == 0 else PREVIEW_SHEET_LAYERS))
        self.btn_sheet = self.steps.buttons[0]       # «1 Componer hoja»
        root.addWidget(wizard_header(self.steps))
        t = _theme.tokens()
        panel_qss = (f"QFrame#previewPanel {{ background:{t.surface}; border:1px solid {t.border};"
                     f" border-radius:8px; }}")
        self.split = GripSplitter(QtCore.Qt.Horizontal)   # tiradores visibles y arrastrables

        # ── izquierda: «Para verificar» + «Detalles» (plegable: en pantallas chicas deja
        # la hoja más ancha; plegado muestra «Para verificar (N)» en vertical) ──
        self.review_panel = ReviewPanel(self._results)
        self.review_panel.locate.connect(self._go_to)
        n_review = len(self.review_panel.review_rows)
        # «Para verificar», no «Revisar»: lo encontrado que conviene mirar, no errores
        self.review_box = CollapsiblePanel(_tr("Para verificar ({n})").format(n=n_review) if n_review
                                           else _tr("Para verificar"))
        self.review_box.setObjectName("previewPanel")
        self.review_box.setStyleSheet(panel_qss)
        self.review_scroll = NaturalHeightScroll(self.review_panel)
        self.review_box.body_layout.addWidget(self.review_scroll, 1)
        self.review_box.setMinimumWidth(240)
        self.review_box.toggled.connect(self._on_review_toggled)
        self.split.addWidget(self.review_box)

        self.view = _PreviewView()
        self.split.addWidget(self.view)

        # ── derecha: hoja + resumen + capas usadas; «Ajustar capas…» fuera del scroll ──
        side = QtWidgets.QFrame()
        side.setObjectName("previewPanel")
        side.setStyleSheet(panel_qss)
        side.setMinimumWidth(300)
        self.side_panel = side
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(12, 10, 12, 10)
        side_layout.setSpacing(8)
        body = QtWidgets.QWidget()
        panel = QtWidgets.QVBoxLayout(body)
        panel.setContentsMargins(0, 0, 4, 0)    # aire para la barra de scroll
        panel.setSpacing(10)
        self.panel_scroll = NaturalHeightScroll(body)
        side_layout.addWidget(self.panel_scroll, 1)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 0); self.split.setStretchFactor(1, 1); self.split.setStretchFactor(2, 0)
        self._sizes_auto = True            # False en cuanto el usuario mueve un divisor
        self.split.splitterMoved.connect(lambda *_: setattr(self, "_sizes_auto", False))
        self._sizes_timer = QtCore.QTimer(self)
        self._sizes_timer.setSingleShot(True)
        self._sizes_timer.timeout.connect(lambda: self._sizes_auto and self._apply_side_width())
        root.addWidget(self.split, 1)

        color = layer_qcolor(utilities[0])

        # ── cabecera: hoja (lo que se está viendo) + escala; debajo, las utilidades ──
        head = QtWidgets.QHBoxLayout(); head.setSpacing(8)
        sheet = (_tr("Hoja {n} / {total}").format(n=self._result.page_index + 1, total=page_count)
                 if page_count else _tr("Hoja {n}").format(n=self._result.page_index + 1))
        self.lbl_sheet = QtWidgets.QLabel(sheet)
        sf = self.lbl_sheet.font(); sf.setBold(True); sf.setPointSize(sf.pointSize() + 3)
        self.lbl_sheet.setFont(sf)
        head.addWidget(self.lbl_sheet, 1)
        scale = float(getattr(self._result, "scale_ft_per_pt", 0.0) or 0.0)
        self.lbl_scale = QtWidgets.QLabel(_tr("Escala 1\"={v}'").format(v=f"{round(scale * 72.0, 3):g}"))
        self.lbl_scale.setStyleSheet(f"color:{t.text_muted};")
        self.lbl_scale.setToolTip(_tr("Escala {s:.6f} pie/pt").format(s=scale))
        head.addWidget(self.lbl_scale, 0, QtCore.Qt.AlignVCenter)
        panel.addLayout(head)
        sub = QtWidgets.QHBoxLayout(); sub.setSpacing(6)
        if len(utilities) == 1:            # con varias, el color de cada una está en sus barras
            sw = QtWidgets.QLabel()
            sw.setPixmap(utility_swatch(color, 12))
            sub.addWidget(sw, 0, QtCore.Qt.AlignTop)
        title = QtWidgets.QLabel(_tr(utility_title))
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        title.setStyleSheet(f"color:{t.text_muted};")
        sub.addWidget(title, 1)
        panel.addLayout(sub)

        self._colors = {item.utility: layer_qcolor(item.utility) for item in self._results}
        # Resumen visual: tarjetas + barra por utilidad + cobertura (los avisos van
        # en el panel izquierdo).
        self.summary = SummaryPanel(self._results)
        self._marker = None
        self._reviewed: list = []          # lugares ya vistos desde «Para verificar» (recuadro verde)
        panel.addWidget(self.summary)
        # «Unir tramos en rutas» va en el pie, junto a «Opacidad» (en el panel,
        # entre los avisos y la cobertura, descuadraba el resumen).
        self.chk_routes = QtWidgets.QToolButton()
        self.chk_routes.setText(_tr("Unir tramos"))
        self.chk_routes.setCheckable(True)
        self.chk_routes.setProperty("toggleTool", True)      # activo = verde (theme.py)
        self.chk_routes.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.chk_routes.setIconSize(QtCore.QSize(18, 18))
        self.chk_routes.setMinimumHeight(38)
        self.chk_routes.setToolTip(_tr("Unir tramos en rutas") + "\n" + _tr(
            "En cada cruce sigue de frente; el ramal empieza otra ruta. "
            "Si no hay trayectoria clara, no une nada. No mueve puntos."))
        self.chk_routes.setChecked(all(bool(getattr(item, "join_routes", True))
                                      for item in self._results))
        self._sync_routes_icon(self.chk_routes.isChecked())
        self.chk_routes.toggled.connect(self._sync_routes_icon)
        self.chk_routes.toggled.connect(self._toggle_routes)
        self._update_summary()

        # ── capas usadas: clic en una = resaltarla en la hoja (pedido del usuario 2026-10-03) ──
        panel.addWidget(separator())
        self.layers_panel = UsedLayersPanel(self._results, self._colors)
        self.layers_panel.focusChanged.connect(self._on_layer_focus)
        self.used_layers = self.layers_panel.list
        self._focus = None
        panel.addWidget(self.layers_panel, 1)

        n_draw = self._n_draw()
        if n_draw == 0:
            warn = QtWidgets.QLabel(_tr(
                "No se encontraron capas de líneas de {u} en esta hoja. "
                "Usa «Ajustar capas…» para indicar cuáles son las líneas y las estructuras."
                .format(u=utility_title)))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{t.danger}; font-weight:bold;")
            panel.addWidget(warn)

        # «Ajustar capas…» es sobre la lista de arriba: va en el panel, fuera del
        # scroll. Volver atrás = la cabecera; opacidad y la decisión final = el pie.
        self.btn_roles = QtWidgets.QPushButton(icon("mdi:tune-vertical", color=t.soft_text),
                                               _tr("Ajustar capas…"))
        self.btn_roles.setToolTip(_tr("Solo si el plot usa otros nombres: indicar qué capas son líneas y bóvedas."))
        self.btn_roles.clicked.connect(lambda: self._finish(PREVIEW_ADJUST_LAYERS))
        self.btn_roles.setProperty("soft", True)
        self.btn_roles.setAutoDefault(False)
        self.btn_roles.setMinimumHeight(38)
        side_layout.addWidget(self.btn_roles)
        # Opacidad del PDF (el mismo desplegable del editor): bajarla deja ver
        # mejor QUÉ y CUÁNTO se reconoció sobre el plano.
        self.opacity = OpacityButton(lambda: getattr(self, "_pixmap_item", None))
        self.btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancel.setProperty("secondary", True)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton(_tr("Continuar e importar al editor"))
        self.btn_ok.clicked.connect(lambda: self._finish(PREVIEW_IMPORT))
        self.btn_ok.setToolTip(
            _tr("Al continuar, estas líneas se importan al editor como {u} "
                "(igual que el dibujo manual, con sus puntos de quiebre). "
                "Las estructuras se insertan como nodos de la red.").format(u=utility_title))
        root.addWidget(wizard_footer([self.opacity, self.chk_routes],
                                     _tr("Rueda = zoom · botón central = desplazar"),
                                     [self.btn_cancel, self.btn_ok]))
        self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(n_draw > 0)

        sc = self.view.scene()
        pm = QtGui.QPixmap.fromImage(qimg)
        # Hoja enorme (fondo_pdf): `qimg` es la imagen reducida del editor; se agranda
        # a su tamaño (`fondo["tam"]`) y se re-dibuja nítida la parte visible.
        escala = float(fondo["escala"]) if fondo else 1.0
        self._pixmap_item = fondo_pdf.nuevo_item(pm, escala)
        sc.addItem(self._pixmap_item)
        self._nitidez = None
        if escala < 1.0:
            zoom = float(fondo["zoom"])
            self._nitidez = fondo_pdf.Nitidez(self.view, lambda: zoom, fondo["pagina"])
            self._nitidez.fijar(self._pixmap_item)
        self.opacity.sync()
        self._redraw_overlay()
        self.view.setSceneRect(QtCore.QRectF(pm.rect()) if escala >= 1.0
                               else QtCore.QRectF(0, 0, *fondo["tam"]))
        self._fit_pending = True
        self._fit_view()

    def _drawable(self):
        return [polyline for result in self._results for polyline in result.drawable]

    def _n_draw(self):
        return len(self._drawable())

    def _sync_routes_icon(self, on: bool):
        t = _theme.tokens()
        self.chk_routes.setIcon(icon("mdi:link-variant", color=t.text_on_accent) if on
                                else icon("mdi:link-variant-off", color=t.text))

    def _update_summary(self):
        drawable = self._drawable()
        self.summary.refresh()
        if hasattr(self, "btn_ok"):
            self.btn_ok.setEnabled(len(drawable) > 0)

    def _toggle_routes(self, checked):
        recognition_cache.set_join_routes(self._results, checked)
        self._update_summary()
        self._redraw_overlay()

    def _hit(self, utility, kind, ocg=None):
        """¿Esto es de lo elegido en «Capas usadas»? None = no hay nada elegido.
        Lo que no lleva capa (puntos de bóveda sobre las líneas, marcas del control
        de calidad) solo cuenta cuando se eligió la utilidad entera."""
        f = self._focus
        if f is None:
            return None
        if f["utility"] != utility:
            return False
        if f["kind"] is None:
            return True
        return kind == f["kind"] and (f["ocg"] is None or ocg == f["ocg"])

    def _redraw_overlay(self):
        sc = self.view.scene()
        keep = (self._pixmap_item, self.opacity.backdrop)     # el PDF y su fondo (Opacidad)
        for it in list(sc.items()):
            # el recorte nítido de una hoja enorme es hijo del PDF: se queda con él
            if it not in keep and it.topLevelItem() is not self._pixmap_item:
                sc.removeItem(it)
        dim = []                           # lo que no es de la capa elegida: atenuado

        def put(items, hit):
            if hit is False:
                dim.extend(items if isinstance(items, list) else [items])

        for result in self._results:
            color = self._colors[result.utility]
            u = result.utility
            for pts in (getattr(result, "offpattern_px", None) or []):
                put(_draw_poly(sc, pts, QtGui.QColor(QA_OFFPATTERN), width=2.0, dots=False, z=4, dotted=True),
                    self._hit(u, "qa"))
            for pl in result.drawable:
                hit = self._hit(u, "line", getattr(pl, "layer_ocg", None))
                items = []
                for run in _display_runs(pl):
                    items += _draw_poly(sc, run, color, width=2.0, dots=True, z=5)
                for idx, f in (getattr(pl, "fillets", None) or {}).items():
                    items += _draw_fillet(sc, pl.pts_pdf[idx], f, color)
                x, y = pl.pts_pdf[0]
                start = sc.addEllipse(
                    x - 5, y - 5, 10, 10, QtGui.QPen(QtGui.QColor("#ffffff"), 1.5),
                    QtGui.QBrush(color))
                start.setZValue(8)
                items.append(start)
                put(items, hit)
                if hit:
                    draw_line_halo(sc, pl, color)
            for a, b in (getattr(result, "uncovered_px", None) or []):
                put(_draw_poly(sc, [a, b], QtGui.QColor(QA_UNCOVERED), width=4.0, dots=False, z=7),
                    self._hit(u, "qa"))
            for (vx, vy) in (getattr(result, "vault_pts", None) or []):
                put(_draw_vault(sc, vx, vy, color, z=6), self._hit(u, "node"))
            for vg in (getattr(result, "vaults_geo", None) or []):
                if not vg.get("orphan") or vg.get("importable", False):
                    hit = self._hit(u, "structure", vg.get("layer"))
                    put(_draw_vault_outline(sc, vg, color), hit)
                    if hit:
                        draw_vault_halo(sc, vg, color)
            for (vx, vy) in (getattr(result, "vault_orphans_px", None) or []):
                put(_draw_orphan(sc, vx, vy, z=6), self._hit(u, "qa"))
        for it in dim:
            it.setOpacity(DIM_OPACITY)
        for rect in getattr(self, "_reviewed", []):
            self._draw_reviewed(rect)

    def _focus_points(self):
        """Lo elegido en «Capas usadas»: (puntos que ocupa, nº de líneas, nº de bóvedas)."""
        pts, n_lines, n_vaults = [], 0, 0
        for result in self._results:
            u = result.utility
            for pl in result.drawable:
                if self._hit(u, "line", getattr(pl, "layer_ocg", None)):
                    n_lines += 1
                    pts += list(pl.pts_pdf)
            for vg in (getattr(result, "vaults_geo", None) or []):
                if (not vg.get("orphan") or vg.get("importable", False)) and \
                        self._hit(u, "structure", vg.get("layer")):
                    n_vaults += 1
                    pts += vault_points(vg)
        return pts, n_lines, n_vaults

    def _on_layer_focus(self, focus):
        """Clic en «Capas usadas»: resalta lo de esa capa (halo del color de la
        utilidad, lo demás atenuado) y encuadra la zona; sin elección, toda la hoja."""
        self._focus = focus
        self._redraw_overlay()
        if focus is None:
            self._fit_view()
            return
        pts, n_lines, n_vaults = self._focus_points()
        if not pts:
            self.layers_panel.set_status(
                _tr("{what}: no hay nada reconocido de esta capa en la hoja.").format(what=focus["label"]))
            return
        parts = []
        if n_lines:
            parts.append(_tr("1 línea") if n_lines == 1 else _tr("{n} líneas").format(n=n_lines))
        if n_vaults:
            parts.append(_tr("1 bóveda") if n_vaults == 1 else _tr("{n} bóvedas").format(n=n_vaults))
        self.layers_panel.set_status(_tr("Resaltado: {what} · {parts}").format(
            what=focus["label"], parts=", ".join(parts)))
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        rect = QtCore.QRectF(QtCore.QPointF(min(xs), min(ys)), QtCore.QPointF(max(xs), max(ys)))
        self._show_rect(rect, margin=0.08)

    def _escape(self) -> bool:
        """Esc (la ventana no se cierra: `NoEscapeClose`) = «Ver todo» si hay algo resaltado."""
        if self._focus is None:
            return False
        self.layers_panel.clear_focus()          # emite focusChanged(None) → _on_layer_focus
        return True

    def _draw_reviewed(self, rect: QtCore.QRectF):
        """Recuadro verde a trazos: este lugar ya se vio desde «Para verificar»."""
        pen = QtGui.QPen(QtGui.QColor(_theme.tokens().success), 2, QtCore.Qt.DashLine)
        pen.setCosmetic(True)
        it = self.view.scene().addRect(rect.adjusted(-6, -6, 6, 6), pen)
        it.setZValue(49)
        it.setToolTip(_tr("Visto"))

    def _show_rect(self, rect: QtCore.QRectF, margin: float = 0.0):
        """Lleva la vista a `rect` con contexto alrededor (nunca menos de
        GOTO_MIN_SIDE_PX de lado: un punto suelto no queda a zoom máximo)."""
        ctx = max(rect.width(), rect.height()) * (1.0 + 2 * margin if margin else 1.6) + 60
        side = max(ctx, GOTO_MIN_SIDE_PX)
        c = rect.center()
        view_rect = QtCore.QRectF(c.x() - side / 2, c.y() - side / 2, side, side).united(
            rect.adjusted(-20, -20, 20, 20))
        self.view.resetTransform()
        self.view.fitInView(view_rect, QtCore.Qt.KeepAspectRatio)
        self.view.centerOn(c)

    def _go_to(self, rect: QtCore.QRectF):
        """Clic en un punto de «Para verificar»: la vista va a ese lugar (con
        contexto alrededor) y lo marca con un recuadro que parpadea y se desvanece;
        debajo queda un recuadro verde a trazos (ya visto) hasta cerrar la vista previa."""
        if not any(r == rect for r in self._reviewed):
            self._reviewed.append(QtCore.QRectF(rect))
            self._draw_reviewed(rect)
        self._show_rect(rect)
        sc = self.view.scene()
        if self._marker is not None and self._marker.scene() is sc:
            sc.removeItem(self._marker)
        # Recuadro blanco + trazos negros encima: se ve sobre papel blanco y sobre
        # fondo negro, y no tiene el tono de ninguna utilidad (el ámbar de antes se
        # confundía con gas/telecom).
        box = rect.adjusted(-6, -6, 6, 6)
        halo = QtGui.QPen(QtGui.QColor("#ffffff"), 6)
        halo.setCosmetic(True)
        self._marker = sc.addRect(box, halo)
        ants = QtGui.QPen(QtGui.QColor("#111111"), 2.5, QtCore.Qt.DashLine)
        ants.setCosmetic(True)
        QtWidgets.QGraphicsRectItem(box, self._marker).setPen(ants)
        self._marker.setZValue(50)
        marker = self._marker
        anim = QtCore.QVariantAnimation(self)
        anim.setDuration(2600)
        anim.setStartValue(0.0); anim.setEndValue(1.0)

        def _step(v, m=marker):
            if m.scene() is None:
                return
            # 3 destellos y luego se apaga (queda un contorno tenue hasta el próximo clic)
            m.setOpacity(1.0 - 0.75 * v if v > 0.6 else (0.35 if int(v * 10) % 2 else 1.0))
        anim.valueChanged.connect(_step)
        anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

    def _fit_view(self):
        self.view.resetTransform()
        self.view.fitInView(self.view.scene().itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        # El fitInView del constructor ocurre antes de tener el tamaño real.
        if self._fit_pending:
            self._fit_pending = False
            QtCore.QTimer.singleShot(0, self._apply_side_width)
            QtCore.QTimer.singleShot(0, self._fit_view)

    @staticmethod
    def _review_width(total: int) -> int:
        return max(240, min(300, int(total * 0.20)))

    def _apply_side_width(self):
        """Para verificar (240–300 px, ~20 %) | hoja | resumen (300–400 px, ~28 %): con
        1280 px la hoja conserva ~600 px."""
        w = self.split.width() or self.width()
        right = max(300, min(400, int(w * 0.28)))
        left = CollapsiblePanel.STRIP_W if self.review_box.collapsed else self._review_width(w)
        self.split.setSizes([left, max(200, w - left - right), right])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # hasta que el usuario mueva un divisor, los anchos siguen a la ventana
        # (maximize_on_show maximiza DESPUÉS del primer show). Un ciclo después:
        # aquí el divisor todavía tiene el ancho anterior.
        if getattr(self, "_sizes_auto", False) and not getattr(self, "_fit_pending", True):
            self._sizes_timer.start(0)

    def _on_review_toggled(self, collapsed: bool):
        """Plegar «Para verificar» le da su ancho a la hoja; desplegar lo recupera."""
        sizes = self.split.sizes()
        if collapsed:
            self._review_w = sizes[0]
            sizes[1] += max(0, sizes[0] - CollapsiblePanel.STRIP_W)
            sizes[0] = CollapsiblePanel.STRIP_W
        else:
            # CollapsiblePanel deja el mínimo en 0 al desplegar: sin el de 240 px, los
            # textos que se parten (explicaciones) ensanchaban el panel
            self.review_box.setMinimumWidth(240)
            want = getattr(self, "_review_w", 0) or self._review_width(sum(sizes))
            sizes[1] = max(200, sizes[1] - (want - sizes[0]))
            sizes[0] = want
        self.split.setSizes(sizes)

    def _finish(self, action: str):
        self.action = action
        self.accept()


def show_recognition_preview(parent, qimg, result, utility_layer="ELECTRICO",
                             page_count: int | None = None, fondo: dict | None = None) -> str:
    """Muestra el preview. Devuelve la acción elegida: PREVIEW_IMPORT,
    PREVIEW_CANCEL, PREVIEW_CHANGE_SHEET o PREVIEW_ADJUST_LAYERS."""
    with busy(parent, _tr("Preparando la vista previa…"),
              _tr("Dibujando lo reconocido sobre la hoja")):
        dlg = RecognitionPreviewDialog(parent, qimg, result, utility_layer, page_count=page_count, fondo=fondo)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return PREVIEW_CANCEL
    return dlg.action
