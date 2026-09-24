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

import math
from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from model import TIPOS
from ui_common import layer_qcolor, swatch_icon
from widgets import ZoomPanView, maximize_on_show, side_panel_width
import recognition as rec
import theme as _theme

# Etiqueta de cada utilidad tal como en el desplegable «Tipo de utilidad».
_UTILITY_LABEL = {key: label for label, key in TIPOS}
# Etiquetas de los kinds de reconocimiento (informativo en el preview).
_KIND_LABEL = {"elec_ungd": "Líneas", "drain_ungd": "Líneas",
               "structure": "Estructuras"}
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
    (rec.ROLE_LINEAS, "Líneas"),
    (rec.ROLE_BUZONES, "Buzones / estructuras"),
    (rec.ROLE_IGNORAR, "Ignorar"),
)


class LayerRolesDialog(QtWidgets.QDialog):
    """Ajuste OPCIONAL de qué capas son líneas y cuáles bóvedas (si el plot usa
    otros nombres). Se abre desde «Ajustar capas…» del preview."""

    def __init__(self, parent, layers: list[dict], utility="ELECTRICO"):
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
                0 if rec.suggest_layer_role(L["name"], utility) != rec.ROLE_IGNORAR else 1,
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
            sug = rec.suggest_layer_role(name, utility)
            idx = next((i for i, (r, _) in enumerate(_ROLE_LABELS) if r == sug), 2)
            combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, 2, combo)
            self._rows.append((name, combo))

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


def choose_layer_roles(parent, layers: list[dict], utility="ELECTRICO") -> dict | None:
    """Devuelve {lineas:[…], buzones:[…]} o None si cancela.

    `layers`: dicts de pdf_layers.page_layers (al menos name, short, path_count).
    """
    candidates = [L for L in layers if int(L.get("path_count") or 0) > 0]
    if not candidates:
        return {rec.ROLE_LINEAS: [], rec.ROLE_BUZONES: []}
    dlg = LayerRolesDialog(parent, candidates, utility)
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


def _display_runs(pl):
    """Tramos rectos para DIBUJAR: en un codo la recta llega hasta A (tangencia)
    y se reanuda en B; el arco entre A y B se pinta aparte (`_draw_fillet`)."""
    fillets = getattr(pl, "fillets", None) or {}
    if not fillets:
        return [pl.pts_pdf]
    runs, cur = [], []
    for i, p in enumerate(pl.pts_pdf):
        f = fillets.get(i)
        if f:
            cur.append(f["a"]); runs.append(cur); cur = [f["b"]]
        else:
            cur.append(p)
    runs.append(cur)
    return [r for r in runs if len(r) >= 2]


def _draw_fillet(scene, corner, f: dict, color, z=6):
    """Arco del codo (círculo ajustado al PDF) entre A y B, la esquina C punteada
    y el radio en la etiqueta."""
    cx, cy = f["center"]; r = f["r_px"]
    a0 = math.degrees(math.atan2(-(f["a"][1] - cy), f["a"][0] - cx))
    a1 = math.degrees(math.atan2(-(f["b"][1] - cy), f["b"][0] - cx))
    span = (a1 - a0 + 540.0) % 360.0 - 180.0          # el camino corto
    path = QtGui.QPainterPath()
    path.arcMoveTo(QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r), a0)
    path.arcTo(QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r), a0, span)
    pen = QtGui.QPen(color, 2.5); pen.setCosmetic(True)
    if f.get("loose"):
        # codo APROXIMADO: la curva del plano no es un arco tangente exacto (polilínea
        # «a mano»); el arco queda a ≤3 pt de ella. Se pinta a trazos para que se note.
        pen.setStyle(QtCore.Qt.DashLine)
    it = scene.addPath(path, pen); it.setZValue(z)
    dash = QtGui.QPen(color, 1); dash.setCosmetic(True); dash.setStyle(QtCore.Qt.DashLine)
    for q in (f["a"], f["b"]):
        ln = scene.addLine(q[0], q[1], corner[0], corner[1], dash); ln.setZValue(z)
    m = scene.addRect(corner[0] - 4, corner[1] - 4, 8, 8, QtGui.QPen(QtGui.QColor("#ffffff"), 1.5), QtGui.QBrush(color))
    m.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations); m.setZValue(z + 2)


def _draw_vault_outline(scene, vg: dict, color, z=5):
    """Rectángulo (o círculo) del símbolo de bóveda tal como está en el PDF, con
    el MISMO color de la utilidad que usan las cajas en el editor (una sola
    regla de color en toda la app), y «ancho × largo ft» al lado. Solo informa:
    el vértice de la línea sigue siendo el punto de referencia."""
    color = QtGui.QColor(color)
    pen = QtGui.QPen(color, 2)
    pen.setCosmetic(True)
    fill = QtGui.QColor(color); fill.setAlpha(40)
    if vg.get("corners"):
        poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in vg["corners"]])
        it = scene.addPolygon(poly, pen, QtGui.QBrush(fill))
    else:
        cx, cy = vg["center"]
        r = max(4.0, 0.5 * vg.get("width_ft", 0.0) / max(1e-9, 1.0))   # radio aprox. en px lo pone el llamador
        it = scene.addEllipse(cx - r, cy - r, 2 * r, 2 * r, pen)
    it.setZValue(z)
    if vg.get("width_ft") and vg.get("length_ft"):
        label = f"{vg['width_ft']:.1f} × {vg['length_ft']:.1f} ft" + (" (AB)" if vg.get("abandoned") else "")
        txt = scene.addSimpleText(label)
        txt.setBrush(QtGui.QBrush(color))
        txt.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        xs = [x for x, _ in vg["corners"]] if vg.get("corners") else [vg["center"][0]]
        ys = [y for _, y in vg["corners"]] if vg.get("corners") else [vg["center"][1]]
        txt.setPos(max(xs) + 3, min(ys))
        txt.setZValue(z + 1)


def _draw_vault(scene, x, y, color, z=6, r=None):
    """Punto de bóveda ≈ caja del lienzo (elipse rellena)."""
    pen = QtGui.QPen(QtGui.QColor("#ffffff"), 1.5)
    pen.setCosmetic(True)
    brush = QtGui.QBrush(color)
    r = 6.0 if r is None else float(r)
    it = scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, brush)
    it.setZValue(z)


class RecognitionPreviewDialog(QtWidgets.QDialog):
    """Muestra el PDF + overlay de líneas (listas para el editor) y bóvedas.

    `action` al cerrar: PREVIEW_IMPORT (Continuar), PREVIEW_CANCEL,
    PREVIEW_CHANGE_SHEET («Componer hoja…») o PREVIEW_ADJUST_LAYERS
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
        maximize_on_show(self)
        self._results = list(result) if isinstance(result, (list, tuple)) else [result]
        self._results = [item for item in self._results if item is not None]
        if not self._results:
            raise ValueError("La vista previa necesita al menos un resultado")
        self._result = self._results[0]  # compatibilidad con consumidores antiguos
        utilities = tuple(item.utility for item in self._results)
        utility_title = ("Eléctrico y Drenaje" if len(utilities) > 1 else
                         _UTILITY_LABEL.get(utilities[0], utilities[0]))
        self.action = PREVIEW_CANCEL

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)   # margen uniforme alrededor de vista y panel
        self.view = _PreviewView()
        # Vista | panel derecho con divisor arrastrable (ancho según la ventana).
        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(10)
        # tirador fino y transparente: solo separación (sigue siendo arrastrable)
        self.split.setStyleSheet("QSplitter::handle { background: transparent; border: none; }")
        self.split.addWidget(self.view)
        side = QtWidgets.QWidget()
        side.setMinimumWidth(300)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(10, 0, 0, 0)   # aire entre el divisor y los controles
        panel.setSpacing(8)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 1); self.split.setStretchFactor(1, 0)
        root.addWidget(self.split, 1)

        color = layer_qcolor(utilities[0])
        t = _theme.tokens()

        # ── cabecera: utilidad (con su color) y hoja ──
        head = QtWidgets.QHBoxLayout()
        sw = QtWidgets.QLabel()
        sw.setPixmap(swatch_icon(color, 16).pixmap(16, 16))
        head.addWidget(sw)
        title = QtWidgets.QLabel(_tr(utility_title))
        tf = title.font(); tf.setBold(True); tf.setPointSize(tf.pointSize() + 3); title.setFont(tf)
        head.addWidget(title, 1)
        sheet = (_tr("Hoja {n} / {total}").format(n=self._result.page_index + 1, total=page_count)
                 if page_count else _tr("Hoja {n}").format(n=self._result.page_index + 1))
        self.lbl_sheet = QtWidgets.QLabel(sheet)
        sf = self.lbl_sheet.font(); sf.setBold(True); self.lbl_sheet.setFont(sf)
        head.addWidget(self.lbl_sheet, 0)
        panel.addLayout(head)

        self._colors = {item.utility: layer_qcolor(item.utility) for item in self._results}
        self.lbl_summary = QtWidgets.QLabel()
        self.lbl_summary.setWordWrap(True)
        panel.addWidget(self.lbl_summary)
        self.chk_routes = QtWidgets.QCheckBox(_tr("Unir tramos en rutas"))
        self.chk_routes.setToolTip(_tr(
            "En cada cruce sigue de frente; el ramal empieza otra ruta. "
            "Si no hay trayectoria clara, no une nada. No mueve puntos."))
        self.chk_routes.setChecked(all(bool(getattr(item, "join_routes", True))
                                      for item in self._results))
        self.chk_routes.toggled.connect(self._toggle_routes)
        panel.addWidget(self.chk_routes)
        self._update_summary()
        # QA de un vistazo: cuánto del plano quedó cubierto y qué se dejó fuera.
        cov = min(float(getattr(item, "coverage", 1.0) or 0.0) for item in self._results)
        n_unc = sum(len(getattr(item, "uncovered_px", None) or []) for item in self._results)
        n_off = sum(len(getattr(item, "offpattern_px", None) or []) for item in self._results)
        qa = QtWidgets.QLabel(
            _tr("Cobertura: {c:.1f}%  ·  sin cubrir: {m} (naranja)  ·  fuera de patrón: {o} (violeta)").format(
                c=cov * 100, m=n_unc, o=n_off))
        qa.setWordWrap(True)
        qa.setStyleSheet("color:%s;" % (t.success if cov >= 0.98 and n_unc == 0 else "#e08a00"))
        panel.addWidget(qa)
        hidden = sorted({name for item in self._results
                         for name in (getattr(item, "hidden_ocgs", None) or [])})
        if hidden:
            hid = QtWidgets.QLabel(_tr("Capas ocultas por ti: {n} (no se dibujan ni se reconocen)").format(
                n=len(hidden)))
            hid.setWordWrap(True)
            hid.setToolTip("\n".join(hidden))
            panel.addWidget(hid)

        # ── capas usadas (informativo: asignación automática por nombre) ──
        lbl_used = QtWidgets.QLabel(_tr("Capas usadas (asignadas automáticamente por su nombre):"))
        lbl_used.setWordWrap(True)
        panel.addWidget(lbl_used)
        lst = QtWidgets.QListWidget()
        for item in self._results:
            item_color = self._colors[item.utility]
            if len(self._results) > 1:
                utility_header = QtWidgets.QListWidgetItem(
                    swatch_icon(item_color, 12), _tr(_UTILITY_LABEL.get(item.utility, item.utility)))
                utility_header.setFlags(QtCore.Qt.ItemIsEnabled)
                uf = utility_header.font(); uf.setBold(True); utility_header.setFont(uf)
                utility_header.setForeground(item_color); lst.addItem(utility_header)
            for kind in (rec.utility_line_kind(item.utility), "structure"):
                rows = [x for x in item.ocg_summary if x.get("kind") == kind]
                if not rows:
                    continue
                kind_label = ("Bóvedas" if kind == "structure" and item.utility == "ELECTRICO"
                              else _KIND_LABEL[kind])
                hdr = QtWidgets.QListWidgetItem(_tr(kind_label))
                hdr.setFlags(QtCore.Qt.ItemIsEnabled)
                hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
                hdr.setForeground(item_color); lst.addItem(hdr)
                for x in rows:
                    short = x["ocg"].split("|")[-1] if "|" in x["ocg"] else x["ocg"]
                    tag = "  (AB)" if x.get("abandoned") else ""
                    layer_item = QtWidgets.QListWidgetItem(
                        f"    {short}  ({x.get('path_count', 0)}){tag}")
                    layer_item.setToolTip(x["ocg"]); lst.addItem(layer_item)
        panel.addWidget(lst, 1)

        n_draw = self._n_draw()
        if n_draw == 0:
            warn = QtWidgets.QLabel(_tr(
                "No se encontraron capas de líneas de {u} en esta hoja. "
                "Usa «Ajustar capas…» para indicar cuáles son las líneas y las estructuras."
                .format(u=utility_title)))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{t.danger}; font-weight:bold;")
            panel.addWidget(warn)
        else:
            warnings = []
            for item in self._results:
                prefix = (_UTILITY_LABEL.get(item.utility, item.utility) + ": "
                          if len(self._results) > 1 else "")
                warnings.extend(prefix + text for text in item.warnings)
            warn = QtWidgets.QLabel("\n".join(warnings))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{t.text_muted};")
            if warnings:
                panel.addWidget(warn)

        note = QtWidgets.QLabel(
            _tr("Al continuar, estas líneas se importan al editor como {u} "
                "(igual que el dibujo manual, con sus puntos de quiebre). "
                "Las estructuras se insertan como nodos de la red.").format(
                    u=utility_title))
        note.setWordWrap(True)
        panel.addWidget(note)

        # ── botones: dos filas alineadas en cuadrícula (mismo ancho por columna).
        #    Fila 1, secundarias: Componer hoja… | Ajustar capas…
        #    Fila 2, decisión:    Cancelar       | Continuar e importar (primaria, por defecto)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
        self.btn_sheet = QtWidgets.QPushButton(_tr("Componer hoja…"))
        self.btn_sheet.setToolTip(_tr("Elegir otra hoja del PDF, revisar sus capas y reconocerla."))
        self.btn_sheet.clicked.connect(lambda: self._finish(PREVIEW_CHANGE_SHEET))
        self.btn_roles = QtWidgets.QPushButton(_tr("Ajustar capas…"))
        self.btn_roles.setToolTip(_tr("Solo si el plot usa otros nombres: indicar qué capas son líneas y bóvedas."))
        self.btn_roles.clicked.connect(lambda: self._finish(PREVIEW_ADJUST_LAYERS))
        self.btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton(_tr("Continuar e importar al editor"))
        self.btn_ok.clicked.connect(lambda: self._finish(PREVIEW_IMPORT))
        for b in (self.btn_sheet, self.btn_roles, self.btn_cancel):
            b.setProperty("secondary", True)
        for b in (self.btn_sheet, self.btn_roles, self.btn_cancel, self.btn_ok):
            b.setMinimumHeight(36)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        grid.addWidget(self.btn_sheet, 0, 0); grid.addWidget(self.btn_roles, 0, 1)
        grid.addWidget(self.btn_cancel, 1, 0); grid.addWidget(self.btn_ok, 1, 1)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        panel.addLayout(grid)
        self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(n_draw > 0)

        sc = self.view.scene()
        pm = QtGui.QPixmap.fromImage(qimg)
        self._pixmap_item = sc.addPixmap(pm)
        self._redraw_overlay()
        self.view.setSceneRect(pm.rect())
        self._fit_pending = True
        self._fit_view()

    def _drawable(self):
        return [polyline for result in self._results for polyline in result.drawable]

    def _n_draw(self):
        return len(self._drawable())

    def _update_summary(self):
        drawable = self._drawable()
        n_ab = sum(1 for p in drawable if getattr(p, "abandoned", False))
        n_vault = sum(len(getattr(result, "vault_pts", None) or []) for result in self._results)
        txt = _tr("Tramos listos: {n}  ·  Estructuras: {v}  ·  Escala: {s:.6f} pie/pt").format(
            n=len(drawable), v=n_vault, s=self._result.scale_ft_per_pt)
        n_routes = sum(int(getattr(result, "n_routes", 0) or 0) for result in self._results)
        n_seg = sum(int(getattr(result, "n_segments_total", 0) or 0) for result in self._results)
        if self.chk_routes.isChecked() and n_seg:
            txt += "\n" + _tr("Rutas: {n} (unen {m} tramos)").format(n=n_routes or len(drawable), m=n_seg)
        if n_ab:
            txt += "\n" + _tr("Abandonadas (AB): {a} — mismo color; se distinguen por (AB).").format(a=n_ab)
        self.lbl_summary.setText(txt)
        if hasattr(self, "btn_ok"):
            self.btn_ok.setEnabled(len(drawable) > 0)

    def _toggle_routes(self, checked):
        for result in self._results:
            joined = getattr(result, "polylines_joined", None)
            raw = getattr(result, "polylines_raw", None)
            if not joined or not raw:
                continue
            result.join_routes = bool(checked)
            result.polylines = list(joined if checked else raw)
        self._update_summary()
        self._redraw_overlay()

    def _redraw_overlay(self):
        sc = self.view.scene()
        for it in list(sc.items()):
            if it is not self._pixmap_item:
                sc.removeItem(it)
        for result in self._results:
            color = self._colors[result.utility]
            for pts in (getattr(result, "offpattern_px", None) or []):
                _draw_poly(sc, pts, QtGui.QColor("#8a6cff"), width=1.5, dots=False, z=4)
            for pl in result.drawable:
                for run in _display_runs(pl):
                    _draw_poly(sc, run, color, width=2.0, dots=True, z=5)
                for idx, f in (getattr(pl, "fillets", None) or {}).items():
                    _draw_fillet(sc, pl.pts_pdf[idx], f, color)
                x, y = pl.pts_pdf[0]
                start = sc.addEllipse(
                    x - 5, y - 5, 10, 10, QtGui.QPen(QtGui.QColor("#ffffff"), 1.5),
                    QtGui.QBrush(color))
                start.setZValue(8)
            for a, b in (getattr(result, "uncovered_px", None) or []):
                _draw_poly(sc, [a, b], QtGui.QColor("#ff8c00"), width=4.0, dots=False, z=7)
            for (vx, vy) in (getattr(result, "vault_pts", None) or []):
                _draw_vault(sc, vx, vy, color, z=6)
            for vg in (getattr(result, "vaults_geo", None) or []):
                if not vg.get("orphan") or vg.get("importable", False):
                    _draw_vault_outline(sc, vg, color)
            for (vx, vy) in (getattr(result, "vault_orphans_px", None) or []):
                _draw_vault(sc, vx, vy, QtGui.QColor("#ff8c00"), z=6, r=4.0)

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

    def _apply_side_width(self):
        w = self.width()
        side_w = side_panel_width(w, 400)
        self.split.setSizes([max(200, w - side_w), side_w])

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
