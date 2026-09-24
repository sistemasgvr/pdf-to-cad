"""One layer selection and one preview for all arranged PDF sheets.

PDFs remain separate so each document keeps its own OCG configuration.
"""
from __future__ import annotations

import os

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

import pdf_layers
import recognition
from i18n import t as _tr
from layer_dialog import _UTILITY_RECOG_LABEL, utility_qcolor
from organized_layers import aggregate_layers, hidden_from_states, selected_sheets
from pdf_view_quality import FocusedPageQuality
from sheet_crops import normalize as normalize_crops, page_rect
from sheet_crop_dialog import choose_sheet_crop
from ui_common import swatch_icon
from widgets import ZoomPanView
import theme as _theme


_ROLE_GROUP = QtCore.Qt.UserRole
_ROLE_UTILITY = QtCore.Qt.UserRole + 1
_PREVIEW_SCALE = 0.65
_RERENDER_DELAY_MS = 150
_SLOT_LABELS = {"main": "Principal", "top": "Superior", "left": "Izquierda",
                "right": "Derecha", "bottom": "Inferior"}


class _SelectableSheetView(ZoomPanView):
    sheetClicked = QtCore.Signal(QtCore.QPointF)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.sheetClicked.emit(self.mapToScene(event.position().toPoint()))
        super().mousePressEvent(event)


class OrganizedLayersDialog(QtWidgets.QDialog):
    def __init__(self, parent, docs, sources, layout, rotations, saved_hidden=None,
                 saved_crops=None, recognition_utilities=None):
        super().__init__(parent)
        self.docs = docs
        self.sheets = selected_sheets(layout, sources)
        self.rotations = rotations or {}
        self.crops = normalize_crops(saved_crops, layout)
        self._before = {i: pdf_layers.hidden_layers(doc) for i, doc in enumerate(docs)}
        saved_hidden = saved_hidden or {}
        for index, doc in enumerate(docs):
            if str(index) in saved_hidden:
                pdf_layers.set_hidden(doc, saved_hidden[str(index)])
        self._initial = {i: pdf_layers.hidden_layers(doc) for i, doc in enumerate(docs)}

        self.setWindowTitle(_tr("Capas de las hojas organizadas"))
        self.setWindowFlags(self.windowFlags()
                            | QtCore.Qt.WindowMinimizeButtonHint
                            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1400, 850)
        self.setWindowState(self.windowState() | QtCore.Qt.WindowMaximized)
        root = QtWidgets.QHBoxLayout(self)
        self.view = _SelectableSheetView()
        self.view.sheetClicked.connect(self._select_sheet_at)
        root.addWidget(self.view, 1)
        self._pix_items = {}
        self._frame_items = {}
        self._quality = None
        self._selected_slot = None

        side = QtWidgets.QWidget()
        side.setFixedWidth(430)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(8)
        root.addWidget(side)
        intro = QtWidgets.QLabel(_tr(
            "Las hojas aparecen según la organización elegida. Marca las capas "
            "que quieres ver: una opción controla sus equivalentes en todos los PDF. "
            "La posición es aproximada hasta ajustar la unión de las hojas."))
        intro.setWordWrap(True)
        panel.addWidget(intro)
        crop_row = QtWidgets.QHBoxLayout()
        self.crop_status = QtWidgets.QLabel()
        self.crop_status.setWordWrap(True)
        self.btn_crop = QtWidgets.QPushButton(_tr("Delimitar plano…"))
        self.btn_crop.clicked.connect(self._choose_crop)
        crop_row.addWidget(self.crop_status, 1)
        crop_row.addWidget(self.btn_crop)
        panel.addLayout(crop_row)
        self._refresh_selected_sheet()

        group = QtWidgets.QGroupBox(_tr("Utilidades"))
        group_layout = QtWidgets.QGridLayout(group)
        self._utility_checks = {}
        self.chk_all = QtWidgets.QCheckBox(_tr("Todas"))
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self._on_all_toggled)
        group_layout.addWidget(self.chk_all, 0, 0, 1, 2)
        for n, (key, label) in enumerate(pdf_layers.UTILITIES):
            cb = QtWidgets.QCheckBox(_tr(label))
            cb.setIcon(swatch_icon(utility_qcolor(key)))
            cb.setChecked(True)
            cb.toggled.connect(self._on_utility_toggled)
            self._utility_checks[key] = cb
            group_layout.addWidget(cb, 1 + n // 2, n % 2)
        panel.addWidget(group)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(_tr("Buscar capa…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        panel.addWidget(self.search)
        self.lst = QtWidgets.QListWidget()
        self.lst.setAlternatingRowColors(True)
        self.lst.itemChanged.connect(self._on_item_changed)
        panel.addWidget(self.lst, 1)
        row = QtWidgets.QHBoxLayout()
        self.btn_all = QtWidgets.QPushButton(_tr("Mostrar todas"))
        self.btn_none = QtWidgets.QPushButton(_tr("Ocultar todas"))
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_none)
        panel.addLayout(row)
        self.lbl_count = QtWidgets.QLabel()
        panel.addWidget(self.lbl_count)
        hint = QtWidgets.QLabel(_tr("Rueda = zoom · botón central = desplazar"))
        hint.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        panel.addWidget(hint)
        buttons = QtWidgets.QDialogButtonBox()
        btn_ok = buttons.addButton(_tr("Guardar selección de capas"),
                                   QtWidgets.QDialogButtonBox.AcceptRole)
        btn_cancel = buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        btn_cancel.setText(_tr("Cancelar"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        panel.addWidget(buttons)
        btn_ok.setDefault(True)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_RERENDER_DELAY_MS)
        self._timer.timeout.connect(self._apply_and_render)

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            rows = [(sheet, pdf_layers.page_layers(docs[sheet["source"]], sheet["page"]))
                    for sheet in self.sheets]
            self.groups = aggregate_layers(rows)
            target = QtWidgets.QVBoxLayout()
            target.setSpacing(4)
            target.addWidget(QtWidgets.QLabel(_tr("Utilidades a reconocer:")))
            row_recog = QtWidgets.QHBoxLayout()
            self._recog_checks: dict[str, QtWidgets.QCheckBox] = {}
            available = {group["utility"] for group in self.groups if group["path_count"]}
            selected = recognition.normalize_utilities(recognition_utilities)
            for key in recognition.SUPPORTED_UTILITIES:
                cb = QtWidgets.QCheckBox(_tr(_UTILITY_RECOG_LABEL.get(key, key)))
                cb.setIcon(swatch_icon(utility_qcolor(key)))
                cb.setChecked(key in selected)
                cb.setEnabled(key in available)
                cb.toggled.connect(self._on_recog_utility_toggled)
                self._recog_checks[key] = cb
                row_recog.addWidget(cb)
            row_recog.addStretch(1)
            target.addLayout(row_recog)
            panel.insertLayout(2, target)
            self._fill_list()
            self._render_sheets(first=True)
            self._quality = FocusedPageQuality(
                self.view, self.docs, self.sheets, self.rotations,
                self._pix_items, _PREVIEW_SCALE, self.crops)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.result_hidden = None
        self.result_utilities = recognition.normalize_utilities(recognition_utilities)

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_view)

    def _fit_view(self):
        bounds = self.view.scene().itemsBoundingRect()
        if not bounds.isEmpty():
            self.view.resetTransform()
            self.view.fitInView(bounds.adjusted(-25, -25, 25, 25),
                                QtCore.Qt.KeepAspectRatio)
            if self._quality is not None:
                self._quality.schedule()

    def _fill_list(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        by_utility = {}
        for index, layer in enumerate(self.groups):
            by_utility.setdefault(layer["utility"], []).append((index, layer))
        n_sheets = len(self.sheets)
        for utility, label in pdf_layers.UTILITIES:
            entries = by_utility.get(utility, [])
            cb = self._utility_checks[utility]
            cb.setText(f"{_tr(label)}  ({len(entries)})")
            cb.setEnabled(bool(entries))
            if not entries:
                continue
            color = utility_qcolor(utility)
            header = QtWidgets.QListWidgetItem(
                swatch_icon(color, 12), f"{_tr(label)} — {len(entries)}")
            header.setFlags(QtCore.Qt.ItemIsEnabled)
            header.setForeground(color)
            font = header.font(); font.setBold(True); header.setFont(font)
            header.setData(_ROLE_GROUP, None)
            header.setData(_ROLE_UTILITY, utility)
            self.lst.addItem(header)
            for index, layer in entries:
                text = (f'{layer["short"]}  ({layer["path_count"]} · '
                        f'{len(layer["sheets_with_paths"])}/{n_sheets} hojas)')
                item = QtWidgets.QListWidgetItem(text)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                values = set(layer["bindings"].values())
                state = (QtCore.Qt.Checked if values == {True} else
                         QtCore.Qt.Unchecked if values == {False} else
                         QtCore.Qt.PartiallyChecked)
                item.setCheckState(state)
                item.setData(_ROLE_GROUP, index)
                item.setData(_ROLE_UTILITY, utility)
                bindings = sorted(layer["bindings"])
                item.setToolTip("\n".join(
                    f'PDF {source + 1}: {name}' for source, name in bindings))
                self.lst.addItem(item)
        self.lst.blockSignals(False)
        self._apply_filter()
        self._update_count()

    def _layer_items(self):
        for index in range(self.lst.count()):
            item = self.lst.item(index)
            if item.data(_ROLE_GROUP) is not None:
                yield item

    def _states(self):
        states = [None] * len(self.groups)
        for item in self._layer_items():
            state = item.checkState()
            states[item.data(_ROLE_GROUP)] = (
                True if state == QtCore.Qt.Checked else
                False if state == QtCore.Qt.Unchecked else None)
        return states

    def _selected_hidden(self):
        return hidden_from_states(self.groups, self._states(), self._initial)

    def _update_count(self):
        total = sum(1 for _ in self._layer_items())
        visible = sum(1 for item in self._layer_items()
                      if item.checkState() != QtCore.Qt.Unchecked)
        self.lbl_count.setText(_tr("Visibles: {v} de {t} capas").format(
            v=visible, t=total))

    def _on_item_changed(self, _item):
        self._update_count()
        self._timer.start()

    def _set_all(self, on):
        self.lst.blockSignals(True)
        for item in self._layer_items():
            if not item.isHidden():
                item.setCheckState(QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        self.lst.blockSignals(False)
        self._update_count()
        self._timer.start()

    def _on_all_toggled(self, on):
        for cb in self._utility_checks.values():
            cb.blockSignals(True); cb.setChecked(on); cb.blockSignals(False)
        self._apply_filter()

    def _on_utility_toggled(self, _on):
        enabled = [cb for cb in self._utility_checks.values() if cb.isEnabled()]
        self.chk_all.blockSignals(True)
        self.chk_all.setChecked(all(cb.isChecked() for cb in enabled))
        self.chk_all.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self, _text=None):
        query = (self.search.text() or "").strip().upper()
        selected = {key for key, cb in self._utility_checks.items() if cb.isChecked()}
        shown = {}
        for item in self._layer_items():
            utility = item.data(_ROLE_UTILITY)
            hidden = utility not in selected or (
                bool(query) and query not in item.text().upper()
                and query not in item.toolTip().upper())
            item.setHidden(hidden)
            if not hidden:
                shown[utility] = shown.get(utility, 0) + 1
        for index in range(self.lst.count()):
            item = self.lst.item(index)
            if item.data(_ROLE_GROUP) is None:
                item.setHidden(shown.get(item.data(_ROLE_UTILITY), 0) == 0)

    def _apply_and_render(self):
        selected = self._selected_hidden()
        changed = set()
        for index, doc in enumerate(self.docs):
            before = pdf_layers.hidden_layers(doc)
            after = selected.get(index, set())
            if before != after:
                pdf_layers.set_hidden(doc, after)
                changed.add(index)
        if changed:
            self._render_sheets(changed)

    def _render_sheets(self, changed_sources=None, first=False):
        if self._quality is not None:
            self._quality._clear_sharp()
        scene = self.view.scene()
        for sheet in self.sheets:
            slot = sheet["slot"]
            source = sheet["source"]
            if changed_sources is not None and source not in changed_sources:
                continue
            page = self.docs[source][sheet["page"]]
            pix = page.get_pixmap(matrix=fitz.Matrix(_PREVIEW_SCALE,
                                                      _PREVIEW_SCALE), alpha=False,
                                  clip=page_rect(page, self.crops.get(slot)))
            image = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                                 pix.stride, QtGui.QImage.Format_RGB888).copy()
            pixmap = QtGui.QPixmap.fromImage(image)
            rotation = int(self.rotations.get(slot, 0)) % 360
            if rotation:
                pixmap = pixmap.transformed(QtGui.QTransform().rotate(rotation),
                                            QtCore.Qt.SmoothTransformation)
            if slot in self._pix_items:
                self._pix_items[slot].setPixmap(pixmap)
            else:
                item = scene.addPixmap(pixmap)
                item.setTransformationMode(QtCore.Qt.SmoothTransformation)
                self._pix_items[slot] = item
        if first:
            self._position_sheets()
        elif self._quality is not None:
            self._quality.invalidate(changed_sources)
            self._quality.schedule()

    def _position_sheets(self):
        scene = self.view.scene()
        main = self._pix_items["main"].boundingRect()
        gap = 65
        for sheet in self.sheets:
            slot = sheet["slot"]
            item = self._pix_items[slot]
            size = item.boundingRect()
            if slot == "left":
                x, y = -size.width() - gap, (main.height() - size.height()) / 2
            elif slot == "right":
                x, y = main.width() + gap, (main.height() - size.height()) / 2
            elif slot == "top":
                x, y = (main.width() - size.width()) / 2, -size.height() - gap
            elif slot == "bottom":
                x, y = (main.width() - size.width()) / 2, main.height() + gap
            else:
                x, y = 0, 0
            item.setPos(x, y)
            label = scene.addSimpleText(self._sheet_title(sheet))
            label.setBrush(QtGui.QBrush(QtGui.QColor(_theme.tokens().text)))
            label.setPos(x, y - 28)
            outline = scene.addRect(QtCore.QRectF(x, y, size.width(), size.height()),
                                    QtGui.QPen(QtGui.QColor(_theme.tokens().focus), 2),
                                    QtGui.QBrush(QtCore.Qt.NoBrush))
            outline.setZValue(1)
            self._frame_items[slot] = outline
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self._refresh_selected_sheet()

    def _sheet_title(self, sheet):
        return (f'{_tr(_SLOT_LABELS[sheet["slot"]])} · {sheet["source_name"]} · '
                f'{_tr("Hoja {i}").format(i=sheet["page"] + 1)}')

    def _select_sheet_at(self, point):
        self._selected_slot = next((sheet["slot"] for sheet in self.sheets
            if self._pix_items[sheet["slot"]].sceneBoundingRect().contains(point)), None)
        self._refresh_selected_sheet()

    def _refresh_selected_sheet(self):
        slot = self._selected_slot
        self.btn_crop.setEnabled(slot is not None)
        if slot is None:
            self.crop_status.setText(_tr("Haz clic en una hoja para delimitar su plano."))
        else:
            sheet = next(s for s in self.sheets if s["slot"] == slot)
            state = (_tr("Área delimitada") if slot in self.crops
                     else _tr("Hoja completa"))
            self.crop_status.setText(f"{self._sheet_title(sheet)} · {state}")
        for key, frame in self._frame_items.items():
            color = QtGui.QColor("#ff9a00" if key == slot else _theme.tokens().focus)
            pen = QtGui.QPen(color, 3 if key == slot else 2)
            pen.setCosmetic(True)
            frame.setPen(pen)

    def _choose_crop(self):
        slot = self._selected_slot
        if slot is None:
            return
        self._timer.stop()
        self._apply_and_render()
        sheet = next(s for s in self.sheets if s["slot"] == slot)
        crop = choose_sheet_crop(self, self.docs[sheet["source"]][sheet["page"]],
                                 self._sheet_title(sheet), self.crops.get(slot))
        if crop is None:
            return
        self.crops = normalize_crops({**self.crops, slot: crop})
        self._refresh_selected_sheet()
        if self._quality is not None:
            self.view.viewChanged.disconnect(self._quality.schedule)
            self._quality._timer.stop()
            self._quality.deleteLater()
            self._quality = None
        self.view.scene().clear()
        self._pix_items.clear()
        self._frame_items.clear()
        self._render_sheets(first=True)
        self._quality = FocusedPageQuality(
            self.view, self.docs, self.sheets, self.rotations,
            self._pix_items, _PREVIEW_SCALE, self.crops)
        self._fit_view()

    def _on_recog_utility_toggled(self, _on: bool):
        # Al menos una tiene que quedar marcada (si no, ¿qué se reconoce?).
        if not any(cb.isChecked() for cb in self._recog_checks.values()):
            sender = self.sender()
            if sender is not None:
                sender.blockSignals(True); sender.setChecked(True); sender.blockSignals(False)

    def accept(self):
        self._timer.stop()
        self._apply_and_render()
        self.result_hidden = {str(index): sorted(pdf_layers.hidden_layers(doc))
                              for index, doc in enumerate(self.docs)}
        self.result_crops = dict(self.crops)
        chosen = tuple(key for key in recognition.SUPPORTED_UTILITIES
                       if self._recog_checks[key].isChecked())
        self.result_utilities = recognition.normalize_utilities(chosen)
        super().accept()

    def reject(self):
        self._timer.stop()
        for index, doc in enumerate(self.docs):
            pdf_layers.set_hidden(doc, self._before[index])
        super().reject()


def choose_organized_sheet_layers(parent, base_doc, external_pdfs, sources,
                                   layout, rotations, hidden_by_source=None,
                                   sheet_crops=None, recognition_utilities=None):
    docs = [base_doc]
    before_base = pdf_layers.hidden_layers(base_doc)
    try:
        for source in external_pdfs:
            docs.append(fitz.open(stream=source["data"], filetype="pdf"))
        dialog = OrganizedLayersDialog(parent, docs, sources, layout, rotations,
                                       hidden_by_source, sheet_crops, recognition_utilities)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return None
        return dialog.result_hidden, dialog.result_crops, dialog.result_utilities
    except Exception:
        pdf_layers.set_hidden(base_doc, before_base)
        raise
    finally:
        for doc in docs[1:]:
            doc.close()
