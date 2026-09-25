"""Combined utility recognition preview for an arranged set of PDF sheets.

The arrangement expresses adjacency only. Each result stays in its own sheet's
coordinates; no cross-sheet snapping or import is implied by this preview.
"""
from __future__ import annotations

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

import pdf_layers
import recognition
from i18n import t as _tr
from layer_dialog import utility_qcolor
from pdf_view_quality import FocusedPageQuality
from widgets import ZoomPanView
import theme as _theme


_LABELS = {"main": "Principal", "top": "Superior", "left": "Izquierda",
           "right": "Derecha", "bottom": "Inferior"}


def _row_results(row):
    return list(row.get("results") or [row["result"]])


def _rotated_point(x, y, width, height, angle):
    """Map an image point into its clockwise, rotated bounding rectangle."""
    angle = angle % 360
    if angle == 90:
        return height - y, x
    if angle == 180:
        return width - x, height - y
    if angle == 270:
        return y, width - x
    return x, y


class OrganizedRecognitionDialog(QtWidgets.QDialog):
    def __init__(self, parent, rows, rotations, join_routes=True):
        super().__init__(parent)
        self.rows = rows
        self.utilities = tuple(result.utility for result in _row_results(rows[0])) if rows else ("ELECTRICO",)
        utility_label = recognition.utilities_label(self.utilities)
        self.rotations = rotations or {}
        self._items = {}
        self.setWindowTitle(_tr("Vista previa del reconocimiento de {u} · hojas organizadas").format(
            u=utility_label))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinimizeButtonHint
                            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1400, 850)
        self.setWindowState(self.windowState() | QtCore.Qt.WindowMaximized)

        root = QtWidgets.QHBoxLayout(self)
        self.view = ZoomPanView()
        root.addWidget(self.view, 1)
        side = QtWidgets.QWidget()
        side.setFixedWidth(390)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(8)
        root.addWidget(side)

        title = QtWidgets.QLabel(_tr("{u} · hojas organizadas").format(u=utility_label))
        font = title.font(); font.setBold(True); font.setPointSize(font.pointSize() + 2)
        title.setFont(font)
        panel.addWidget(title)
        note = QtWidgets.QLabel(_tr(
            "Cada hoja se reconoce con las capas seleccionadas para su PDF. "
            "La posición entre hojas es aproximada; aún no se han alineado ni unido los trazos."))
        note.setWordWrap(True)
        panel.addWidget(note)
        self.chk_routes = QtWidgets.QCheckBox(_tr("Unir tramos en rutas"))
        self.chk_routes.setChecked(join_routes)
        self.chk_routes.toggled.connect(self._toggle_routes)
        panel.addWidget(self.chk_routes)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        panel.addWidget(self.summary)
        panel.addWidget(QtWidgets.QLabel(_tr("Hojas reconocidas")))
        self.list = QtWidgets.QListWidget()
        self.list.currentRowChanged.connect(self._select_row)
        panel.addWidget(self.list, 1)
        self.details = QtWidgets.QLabel()
        self.details.setWordWrap(True)
        panel.addWidget(self.details)
        panel.addWidget(QtWidgets.QLabel(_tr("Capas de {u} usadas en la hoja").format(
            u=utility_label)))
        self.layers = QtWidgets.QListWidget()
        panel.addWidget(self.layers, 1)
        hint = QtWidgets.QLabel(_tr("Rueda = zoom · botón central = desplazar"))
        hint.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        panel.addWidget(hint)
        buttons = QtWidgets.QDialogButtonBox()
        back = buttons.addButton(_tr("Volver a capas"), QtWidgets.QDialogButtonBox.ActionRole)
        back.clicked.connect(lambda: self.done(2))
        close = buttons.addButton(_tr("Cerrar vista previa"), QtWidgets.QDialogButtonBox.RejectRole)
        close.clicked.connect(self.reject)
        panel.addWidget(buttons)

        self._build_scene()
        self._refresh_summary()
        self.list.setCurrentRow(0)
        self._quality = None

    def enable_pdf_quality(self, docs, crops=None):
        self._quality = FocusedPageQuality(
            self.view, docs, [row["sheet"] for row in self.rows],
            self.rotations, self._items, 1.0, crops)

    def _build_scene(self):
        scene = self.view.scene()
        sizes = {}
        for row in self.rows:
            sheet = row["sheet"]
            slot = sheet["slot"]
            image = QtGui.QImage(row["samples"], row["width"], row["height"],
                                 row["stride"], QtGui.QImage.Format_RGB888).copy()
            pixmap = QtGui.QPixmap.fromImage(image)
            row.pop("samples", None)  # the pixmap owns the overview image now
            angle = int(self.rotations.get(slot, 0)) % 360
            if angle:
                pixmap = pixmap.transformed(QtGui.QTransform().rotate(angle),
                                            QtCore.Qt.SmoothTransformation)
            item = scene.addPixmap(pixmap)
            item.setTransformationMode(QtCore.Qt.SmoothTransformation)
            self._items[slot] = item
            sizes[slot] = (pixmap.width(), pixmap.height())
            name = f'{_tr(_LABELS[slot])} · {sheet["source_name"]} · '
            name += _tr("Hoja {i}").format(i=sheet["page"] + 1)
            self.list.addItem(name)

        main_w, main_h = sizes["main"]
        gap = 65
        for index, row in enumerate(self.rows):
            slot = row["sheet"]["slot"]
            w, h = sizes[slot]
            if slot == "left":
                x, y = -w - gap, (main_h - h) / 2
            elif slot == "right":
                x, y = main_w + gap, (main_h - h) / 2
            elif slot == "top":
                x, y = (main_w - w) / 2, -h - gap
            elif slot == "bottom":
                x, y = (main_w - w) / 2, main_h + gap
            else:
                x, y = 0, 0
            row["origin"] = (x, y)
            self._items[slot].setPos(x, y)
            label = scene.addSimpleText(self.list.item(index).text())
            label.setBrush(QtGui.QBrush(QtGui.QColor(_theme.tokens().text)))
            label.setPos(x, y - 28)
            frame = scene.addRect(x, y, w, h,
                                  QtGui.QPen(QtGui.QColor(_theme.tokens().focus), 2))
            frame.setZValue(1)
        self._redraw_overlays()
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-25, -25, 25, 25))

    def _point(self, row, point):
        slot = row["sheet"]["slot"]
        x, y = _rotated_point(point[0], point[1], row["width"], row["height"],
                              int(self.rotations.get(slot, 0)))
        ox, oy = row["origin"]
        return ox + x, oy + y

    def _redraw_overlays(self):
        scene = self.view.scene()
        for item in getattr(self, "_overlays", []):
            scene.removeItem(item)
        self._overlays = []
        for row in self.rows:
            for result in _row_results(row):
                color = utility_qcolor(result.utility)
                for pts in result.offpattern_px:
                    points = [self._point(row, p) for p in pts]
                    pen = QtGui.QPen(QtGui.QColor("#8a6cff"), 1.5); pen.setCosmetic(True)
                    for a, b in zip(points, points[1:]):
                        line = scene.addLine(a[0], a[1], b[0], b[1], pen)
                        line.setZValue(4); self._overlays.append(line)
                for pl in result.drawable:
                    pts = [self._point(row, p) for p in pl.pts_pdf]
                    pen = QtGui.QPen(color, 2); pen.setCosmetic(True)
                    for a, b in zip(pts, pts[1:]):
                        line = scene.addLine(a[0], a[1], b[0], b[1], pen)
                        line.setZValue(5); self._overlays.append(line)
                    for x, y in pts:
                        dot = scene.addEllipse(x - 3, y - 3, 6, 6, pen, QtGui.QBrush(color))
                        dot.setZValue(6); self._overlays.append(dot)
                for a, b in result.uncovered_px:
                    start, end = self._point(row, a), self._point(row, b)
                    pen = QtGui.QPen(QtGui.QColor("#ff8c00"), 4); pen.setCosmetic(True)
                    line = scene.addLine(start[0], start[1], end[0], end[1], pen)
                    line.setZValue(8); self._overlays.append(line)
                for point in result.vault_pts:
                    x, y = self._point(row, point)
                    dot = scene.addEllipse(x - 6, y - 6, 12, 12,
                                           QtGui.QPen(QtGui.QColor("#ffffff"), 1.5),
                                           QtGui.QBrush(color))
                    dot.setZValue(7); self._overlays.append(dot)
                for point in result.vault_orphans_px:
                    x, y = self._point(row, point)
                    dot = scene.addEllipse(x - 6, y - 6, 12, 12,
                                           QtGui.QPen(QtGui.QColor("#ffffff"), 1.5),
                                           QtGui.QBrush(QtGui.QColor("#ff8c00")))
                    dot.setZValue(7); self._overlays.append(dot)

    def _toggle_routes(self, checked):
        for row in self.rows:
            for result in _row_results(row):
                result.join_routes = bool(checked)
                result.polylines = list(result.polylines_joined if checked
                                        else result.polylines_raw)
        self._redraw_overlays()
        self._refresh_summary()
        self._select_row(self.list.currentRow())

    def _refresh_summary(self):
        results = [result for row in self.rows for result in _row_results(row)]
        n_lines = sum(len(result.drawable) for result in results)
        n_vaults = sum(len(result.vault_pts) for result in results)
        self.summary.setText(_tr("{s} hojas · {n} tramos · {v} estructuras").format(
            s=len(self.rows), n=n_lines, v=n_vaults))

    def _select_row(self, index):
        if not 0 <= index < len(self.rows):
            return
        row = self.rows[index]
        results = _row_results(row)
        details_rows = []
        for result in results:
            utility = recognition.utility_label(result.utility)
            details_rows.append(_tr("{u}: {n} tramos · {v} estructuras · cobertura {c:.1f}%").format(
                u=utility, n=len(result.drawable), v=len(result.vault_pts), c=result.coverage * 100))
        details = "\n".join(details_rows)
        details += "\n" + _tr("Sin cubrir: {n} (naranja) · Fuera de patrón: {m} (violeta)").format(
            n=sum(len(result.uncovered_px) for result in results),
            m=sum(len(result.offpattern_px) for result in results))
        self.details.setText(details)
        self.layers.clear()
        for result in results:
            utility = recognition.utility_label(result.utility)
            for layer in result.ocg_summary:
                if layer.get("kind") not in (recognition.utility_line_kind(result.utility), "structure"):
                    continue
                short = layer["ocg"].split("|")[-1]
                kind = (_tr("Líneas") if layer["kind"] == recognition.utility_line_kind(result.utility)
                        else _tr("Estructuras"))
                self.layers.addItem(f'{utility} · {kind} · {short} ({layer["path_count"]})')
        if not self.layers.count():
            self.layers.addItem(_tr("No se encontraron capas reconocibles de esta utilidad."))

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_view)

    def _fit_view(self):
        self.view.resetTransform()
        self.view.fitInView(self.view.scene().sceneRect(), QtCore.Qt.KeepAspectRatio)
        if self._quality is not None:
            self._quality.schedule()


def show_organized_recognition_preview(parent, rows, rotations, join_routes=True,
                                      base_path=None, external_pdfs=None,
                                      hidden_by_source=None, crops=None):
    docs = []
    try:
        if base_path:
            docs.append(fitz.open(base_path))
            for source in external_pdfs or ():
                docs.append(fitz.open(stream=source["data"], filetype="pdf"))
            for index, doc in enumerate(docs):
                pdf_layers.set_hidden(doc, (hidden_by_source or {}).get(str(index), ()))
        dialog = OrganizedRecognitionDialog(parent, rows, rotations, join_routes)
        if docs:
            dialog.enable_pdf_quality(docs, crops)
        action = dialog.exec()
        return action, dialog.chk_routes.isChecked()
    finally:
        for doc in docs:
            doc.close()
