"""recognition_dialog.py — Asistente v1: tipo PDF, elegir hoja, preview, roles OCG.

El preview dibuja las pipes reconocidas como el trazo manual y, al Continuar,
se importan al editor (misma forma que finish_pipe). Las capas usadas como
líneas/bóvedas se asignan AUTOMÁTICAMENTE por nombre (`recognition.classify_ocg`)
y se muestran de forma informativa en el preview; «Ajustar capas…» abre el
diálogo de roles solo si hace falta (plot con otros nombres). Desde el preview
también se puede «Cambiar de hoja…» (lista de hojas → capas → nuevo preview).
Textos en español vía i18n.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from model import TIPOS
from ui_common import layer_qcolor, swatch_icon
from widgets import ZoomPanView
import recognition as rec
import theme as _theme

# Etiqueta de cada utilidad tal como en el desplegable «Tipo de utilidad».
_UTILITY_LABEL = {key: label for label, key in TIPOS}
# Etiquetas de los kinds de reconocimiento (informativo en el preview).
_KIND_LABEL = {"elec_ungd": "Líneas", "structure": "Bóvedas"}
# Acciones que devuelve el preview.
PREVIEW_IMPORT, PREVIEW_CANCEL = "import", "cancel"
PREVIEW_CHANGE_SHEET, PREVIEW_ADJUST_LAYERS = "change_sheet", "adjust_layers"


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
    (rec.ROLE_LINEAS, "Líneas eléctricas"),
    (rec.ROLE_BUZONES, "Buzones / bóvedas"),
    (rec.ROLE_IGNORAR, "Ignorar"),
)


class LayerRolesDialog(QtWidgets.QDialog):
    """Ajuste OPCIONAL de qué capas son líneas y cuáles bóvedas (si el plot usa
    otros nombres). Se abre desde «Ajustar capas…» del preview."""

    def __init__(self, parent, layers: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(_tr("Ajustar capas eléctricas"))
        self.resize(560, 520)
        self._rows = []  # (name, combo)

        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr(
            "Indica qué capas son líneas eléctricas y cuáles bóvedas. Las "
            "líneas se importan como utilidades Eléctrico; las bóvedas como "
            "cajas en esas líneas. Al aceptar se vuelve a reconocer la hoja."))
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
                0 if rec.suggest_layer_role(L["name"]) != rec.ROLE_IGNORAR else 1,
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
            sug = rec.suggest_layer_role(name)
            idx = next((i for i, (r, _) in enumerate(_ROLE_LABELS) if r == sug), 2)
            combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, 2, combo)
            self._rows.append((name, combo))

        hint = QtWidgets.QLabel(_tr(
            "Debe haber al menos una capa en «Líneas eléctricas» para continuar."))
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
                self, _tr("Ajustar capas eléctricas"),
                _tr("Asigna al menos una capa como «Líneas eléctricas»."))
            return
        self.accept()


def choose_layer_roles(parent, layers: list[dict]) -> dict | None:
    """Devuelve {lineas:[…], buzones:[…]} o None si cancela.

    `layers`: dicts de pdf_layers.page_layers (al menos name, short, path_count).
    """
    candidates = [L for L in layers if int(L.get("path_count") or 0) > 0]
    if not candidates:
        return {rec.ROLE_LINEAS: [], rec.ROLE_BUZONES: []}
    dlg = LayerRolesDialog(parent, candidates)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return dlg.roles()


_PreviewView = ZoomPanView


def _draw_poly(scene, pts, color, width=2.0, dots=False, z=5, dashed=False):
    """Misma convención visual que Main._poly para pipes finalizados."""
    pen = QtGui.QPen(color, width)
    pen.setCosmetic(True)
    if dashed:
        pen.setDashPattern([6.0, 4.0])
    for a, b in zip(pts, pts[1:]):
        it = scene.addLine(a[0], a[1], b[0], b[1], pen)
        it.setZValue(z)
    if dots:
        for (x, y) in pts:
            it = scene.addEllipse(
                x - 3, y - 3, 6, 6, pen, QtGui.QBrush(color))
            it.setZValue(z)


def _draw_vault(scene, x, y, color, z=6):
    """Punto de bóveda ≈ caja del lienzo (elipse rellena)."""
    pen = QtGui.QPen(QtGui.QColor("#ffffff"), 1.5)
    pen.setCosmetic(True)
    brush = QtGui.QBrush(color)
    r = 6.0
    it = scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, brush)
    it.setZValue(z)


class RecognitionPreviewDialog(QtWidgets.QDialog):
    """Muestra el PDF + overlay de líneas (listas para el editor) y bóvedas.

    `action` al cerrar: PREVIEW_IMPORT (Continuar), PREVIEW_CANCEL,
    PREVIEW_CHANGE_SHEET («Cambiar de hoja…») o PREVIEW_ADJUST_LAYERS
    («Ajustar capas…»). Quien lo abre (Main) ejecuta el flujo correspondiente.
    """

    def __init__(self, parent, qimg: QtGui.QImage, result, utility_layer="ELECTRICO",
                 page_count: int | None = None):
        super().__init__(parent)
        self.setWindowTitle(_tr("Vista previa del reconocimiento"))
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1200, 760)
        self._result = result
        self.action = PREVIEW_CANCEL

        root = QtWidgets.QHBoxLayout(self)
        self.view = _PreviewView()
        root.addWidget(self.view, 1)

        side = QtWidgets.QWidget()
        side.setFixedWidth(400)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(8)
        root.addWidget(side, 0)

        color = layer_qcolor(utility_layer)
        t = _theme.tokens()

        # ── cabecera: utilidad (con su color) y hoja ──
        head = QtWidgets.QHBoxLayout()
        sw = QtWidgets.QLabel()
        sw.setPixmap(swatch_icon(color, 16).pixmap(16, 16))
        head.addWidget(sw)
        title = QtWidgets.QLabel(_tr(_UTILITY_LABEL.get(utility_layer, utility_layer)))
        tf = title.font(); tf.setBold(True); tf.setPointSize(tf.pointSize() + 3); title.setFont(tf)
        head.addWidget(title, 1)
        sheet = (_tr("Hoja {n} / {total}").format(n=result.page_index + 1, total=page_count)
                 if page_count else _tr("Hoja {n}").format(n=result.page_index + 1))
        self.lbl_sheet = QtWidgets.QLabel(sheet)
        sf = self.lbl_sheet.font(); sf.setBold(True); self.lbl_sheet.setFont(sf)
        head.addWidget(self.lbl_sheet, 0)
        panel.addLayout(head)

        drawable = [p for p in result.polylines if p.kind == "elec_ungd" and p.pts_pdf]
        n_draw = len(drawable)
        n_ab = sum(1 for p in drawable if getattr(p, "abandoned", False))
        n_vault = len(getattr(result, "vault_pts", None) or [])
        txt = _tr("Tramos listos: {n}  ·  Bóvedas: {v}  ·  Escala: {s:.6f} pie/pt").format(
            n=n_draw, v=n_vault, s=result.scale_ft_per_pt)
        if n_ab:
            txt += "\n" + _tr("Abandonadas (AB): {a} — mismo color; se distinguen por (AB).").format(a=n_ab)
        summary = QtWidgets.QLabel(txt)
        summary.setWordWrap(True)
        panel.addWidget(summary)
        # QA de un vistazo: cuánto del plano quedó cubierto y qué se dejó fuera.
        cov = float(getattr(result, "coverage", 1.0) or 0.0)
        n_unc = len(getattr(result, "uncovered_px", None) or [])
        n_off = len(getattr(result, "offpattern_px", None) or [])
        qa = QtWidgets.QLabel(
            _tr("Cobertura: {c:.1f}%  ·  sin cubrir: {m} (naranja)  ·  fuera de patrón: {o} (violeta)").format(
                c=cov * 100, m=n_unc, o=n_off))
        qa.setWordWrap(True)
        qa.setStyleSheet("color:%s;" % (t.success if cov >= 0.98 and n_unc == 0 else "#e08a00"))
        panel.addWidget(qa)
        if getattr(result, "hidden_ocgs", None):
            hid = QtWidgets.QLabel(_tr("Capas ocultas por ti: {n} (no se dibujan ni se reconocen)").format(
                n=len(result.hidden_ocgs)))
            hid.setWordWrap(True)
            hid.setToolTip("\n".join(result.hidden_ocgs))
            panel.addWidget(hid)

        # ── capas usadas (informativo: asignación automática por nombre) ──
        lbl_used = QtWidgets.QLabel(_tr("Capas usadas (asignadas automáticamente por su nombre):"))
        lbl_used.setWordWrap(True)
        panel.addWidget(lbl_used)
        lst = QtWidgets.QListWidget()
        for kind in ("elec_ungd", "structure"):
            rows = [x for x in result.ocg_summary if x.get("kind") == kind]
            if not rows:
                continue
            hdr = QtWidgets.QListWidgetItem(swatch_icon(color, 12), _tr(_KIND_LABEL[kind]))
            hdr.setFlags(QtCore.Qt.ItemIsEnabled)       # ni marcable ni seleccionable; icono a color
            hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
            hdr.setForeground(color)
            lst.addItem(hdr)
            for x in rows:
                short = x["ocg"].split("|")[-1] if "|" in x["ocg"] else x["ocg"]
                tag = "  (AB)" if x.get("abandoned") else ""
                it = QtWidgets.QListWidgetItem(f"    {short}  ({x.get('path_count', 0)}){tag}")
                it.setToolTip(x["ocg"])
                lst.addItem(it)
        panel.addWidget(lst, 1)

        if n_draw == 0:
            warn = QtWidgets.QLabel(_tr(
                "No se encontraron capas de líneas eléctricas en esta hoja. "
                "Usa «Ajustar capas…» para indicar cuáles son las líneas y las bóvedas."))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{t.danger}; font-weight:bold;")
            panel.addWidget(warn)
        elif result.warnings:
            warn = QtWidgets.QLabel("\n".join(result.warnings))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{t.text_muted};")
            panel.addWidget(warn)

        note = QtWidgets.QLabel(
            _tr("Al continuar, estas líneas se importan al editor como "
                "utilidades Eléctrico (igual que el dibujo manual, con sus "
                "puntos de quiebre). Las bóvedas se insertan como cajas."))
        note.setWordWrap(True)
        panel.addWidget(note)

        # ── acciones secundarias: cambiar de hoja / ajustar capas ──
        row = QtWidgets.QHBoxLayout()
        self.btn_sheet = QtWidgets.QPushButton(_tr("Cambiar de hoja…"))
        self.btn_sheet.setToolTip(_tr("Elegir otra hoja del PDF, revisar sus capas y reconocerla."))
        self.btn_sheet.clicked.connect(lambda: self._finish(PREVIEW_CHANGE_SHEET))
        self.btn_roles = QtWidgets.QPushButton(_tr("Ajustar capas…"))
        self.btn_roles.setToolTip(_tr("Solo si el plot usa otros nombres: indicar qué capas son líneas y bóvedas."))
        self.btn_roles.clicked.connect(lambda: self._finish(PREVIEW_ADJUST_LAYERS))
        row.addWidget(self.btn_sheet); row.addWidget(self.btn_roles)
        panel.addLayout(row)

        bb = QtWidgets.QDialogButtonBox()
        self.btn_ok = bb.addButton(
            _tr("Continuar e importar al editor"), QtWidgets.QDialogButtonBox.AcceptRole)
        btn_cancel = bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
        btn_cancel.setText(_tr("Cancelar"))
        bb.accepted.connect(lambda: self._finish(PREVIEW_IMPORT))
        bb.rejected.connect(self.reject)
        panel.addWidget(bb)
        self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(n_draw > 0)

        sc = self.view.scene()
        pm = QtGui.QPixmap.fromImage(qimg)
        sc.addPixmap(pm)
        # Fuera de patrón (leaders, flechas): violeta fino, debajo de las líneas.
        for pts in (getattr(result, "offpattern_px", None) or []):
            _draw_poly(sc, pts, QtGui.QColor("#8a6cff"), width=1.5, dots=False, z=4)
        for pl in drawable:
            # Activas y abandonadas son la misma utilidad (mismo color). El (AB)
            # de la lista es lo que las distingue; no se dibujan a trazos.
            _draw_poly(sc, pl.pts_pdf, color, width=2.0, dots=True, z=5)
        # Guiones que ninguna línea cubrió: naranja grueso (para revisar a mano).
        for a, b in (getattr(result, "uncovered_px", None) or []):
            _draw_poly(sc, [a, b], QtGui.QColor("#ff8c00"), width=4.0, dots=False, z=7)
        for (vx, vy) in (getattr(result, "vault_pts", None) or []):
            _draw_vault(sc, vx, vy, color, z=6)
        for (vx, vy) in (getattr(result, "vault_orphans_px", None) or []):
            _draw_vault(sc, vx, vy, QtGui.QColor("#ff8c00"), z=6)
        self.view.setSceneRect(pm.rect())
        self._fit_pending = True
        self._fit_view()

    def _fit_view(self):
        self.view.resetTransform()
        self.view.fitInView(self.view.scene().itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        # El fitInView del constructor ocurre antes de tener el tamaño real.
        if self._fit_pending:
            self._fit_pending = False
            QtCore.QTimer.singleShot(0, self._fit_view)

    def _finish(self, action: str):
        self.action = action
        self.accept()


def show_recognition_preview(parent, qimg, result, utility_layer="ELECTRICO",
                             page_count: int | None = None) -> str:
    """Muestra el preview. Devuelve la acción elegida: PREVIEW_IMPORT,
    PREVIEW_CANCEL, PREVIEW_CHANGE_SHEET o PREVIEW_ADJUST_LAYERS."""
    dlg = RecognitionPreviewDialog(parent, qimg, result, utility_layer, page_count=page_count)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return PREVIEW_CANCEL
    return dlg.action
