"""Select a destination first, then a page from this or another PDF."""
import os

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from icons import icon as _icon
from i18n import t as _tr
from sheet_layout import DIRECTIONS, normalize, normalize_rotations
import theme as _theme


_LABELS = {"top": "Superior", "left": "Izquierda", "right": "Derecha",
           "bottom": "Inferior", "main": "Principal"}
_POSITIONS = {"top": (0, 1), "left": (1, 0), "main": (1, 1),
              "right": (1, 2), "bottom": (2, 1)}


class _SheetCard(QtWidgets.QFrame):
    clicked = QtCore.Signal()
    resized = QtCore.Signal()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class SheetLayoutDialog(QtWidgets.QDialog):
    def __init__(self, parent, doc, layout=None, current=0, sources=None,
                 external_pdfs=None, rotations=None):
        super().__init__(parent)
        self.doc = doc
        self.existing = [(item["name"], fitz.open(stream=item["data"], filetype="pdf"))
                         for item in (external_pdfs or [])]
        total = doc.page_count + sum(other.page_count for _, other in self.existing)
        self.arrangement = normalize(layout, total, current)
        self.rotations = normalize_rotations(rotations, self.arrangement)
        self.sources = list(sources or [{"name": "PDF principal", "start": 0,
                                         "count": doc.page_count}])
        self.added = []  # (path, Document); incorporated only on accept
        self._thumbs = {}
        self.setWindowTitle(_tr("Organizar hojas del plano"))
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint)
        self.resize(1100, 760)
        self.setWindowState(self.windowState() | QtCore.Qt.WindowMaximized)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        intro = QtWidgets.QLabel(_tr(
            "Haz clic en la posición que quieres llenar. Luego elige una hoja "
            "del PDF abierto; para las posiciones contiguas puedes cargar otro PDF. "
            "Las posiciones indican "
            "continuidad; el ajuste geométrico se realizará después."))
        intro.setWordWrap(True)
        root.addWidget(intro)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)
        root.addLayout(grid, 1)
        self.cards = {}
        for key in ("top", "left", "main", "right", "bottom"):
            row, col = _POSITIONS[key]
            card = _SheetCard()
            card.clicked.connect(lambda slot=key: self._pick(slot))
            card.resized.connect(lambda: QtCore.QTimer.singleShot(0, self._refresh))
            card.setCursor(QtCore.Qt.PointingHandCursor)
            card.setObjectName("sheetCard")
            token = _theme.tokens()
            border = token.focus if key == "main" else token.border
            card.setStyleSheet(
                f"QFrame#sheetCard {{ background:{token.surface}; border:1px solid {border}; "
                "border-radius:8px; }"
                f"QToolButton {{ background:transparent; border:0; border-radius:4px; }}"
                f"QToolButton:hover {{ background:{token.hover}; }}")
            card.setMinimumSize(210, 145)
            box = QtWidgets.QVBoxLayout(card)
            box.setContentsMargins(8, 6, 8, 6)
            box.setSpacing(4)
            header = QtWidgets.QHBoxLayout()
            title = QtWidgets.QLabel(_tr(_LABELS[key]))
            title.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            title.setStyleSheet("font-weight:600;")
            header.addWidget(title)
            header.addStretch()
            choose = self._icon_button("file-plus-outline", _tr("Elegir o cambiar hoja"))
            choose.clicked.connect(lambda _=False, slot=key: self._pick(slot))
            header.addWidget(choose)
            left = self._icon_button("undo-variant", _tr("Rotar 90° a la izquierda"))
            left.clicked.connect(lambda _=False, slot=key: self._rotate(slot, -90))
            header.addWidget(left)
            right = self._icon_button("redo-variant", _tr("Rotar 90° a la derecha"))
            right.clicked.connect(lambda _=False, slot=key: self._rotate(slot, 90))
            header.addWidget(right)
            remove = None
            if key != "main":
                remove = self._icon_button("trash-can-outline", _tr("Quitar hoja"))
                remove.clicked.connect(lambda _=False, slot=key: self._remove(slot))
                header.addWidget(remove)
            box.addLayout(header)
            preview = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
            preview.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            preview.setMinimumHeight(55)
            preview.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            box.addWidget(preview, 1)
            name = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
            name.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            name.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            box.addWidget(name)
            self.cards[key] = (title, preview, name, choose, left, right, remove)
            grid.addWidget(card, row, col)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 2)
        grid.setRowStretch(2, 1)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        self._refresh()
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(_tr("Continuar con esta organización"))
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(_tr("Cancelar"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _icon_button(self, icon_name, tooltip):
        button = QtWidgets.QToolButton()
        button.setIcon(_icon(f"mdi:{icon_name}", color=_theme.tokens().text))
        button.setIconSize(QtCore.QSize(20, 20))
        button.setFixedSize(30, 30)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        return button

    @property
    def page_count(self):
        return (self.doc.page_count + sum(doc.page_count for _, doc in self.existing)
                + sum(doc.page_count for _, doc in self.added))

    def _page(self, index):
        if index < self.doc.page_count:
            return self.doc[index]
        index -= self.doc.page_count
        for _, doc in (*self.existing, *self.added):
            if index < doc.page_count:
                return doc[index]
            index -= doc.page_count
        raise IndexError(index)

    def _source_name(self, index):
        for source in self.sources:
            if source["start"] <= index < source["start"] + source["count"]:
                number = index - source["start"] + 1
                return f'{source["name"]} · {_tr("Hoja {i}").format(i=number)}'
        return _tr("Hoja {i}").format(i=index + 1)

    def _thumb(self, index):
        if index not in self._thumbs:
            page = self._page(index)
            scale = min(0.8, 900 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                                 pix.stride, QtGui.QImage.Format_RGB888).copy()
            self._thumbs[index] = QtGui.QPixmap.fromImage(image)
        return self._thumbs[index]

    def _refresh(self):
        for key, (title, preview, name, choose, left, right, remove) in self.cards.items():
            index = self.arrangement[key]
            angle = self.rotations[key]
            title.setText(_tr(_LABELS[key]) + (f" · {angle}°" if angle else ""))
            if index is None:
                preview.setPixmap(QtGui.QPixmap())
                preview.setText("+")
                preview.setStyleSheet("font-size:24px;")
                name.setText(_tr("Sin hoja"))
                name.setToolTip("")
            else:
                try:
                    preview.setText("")
                    preview.setStyleSheet("")
                    pixmap = self._thumb(index)
                    if angle:
                        pixmap = pixmap.transformed(
                            QtGui.QTransform().rotate(angle), QtCore.Qt.SmoothTransformation)
                    preview.setPixmap(pixmap.scaled(
                        max(80, preview.width() - 8), max(55, preview.height() - 8),
                        QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
                except Exception as exc:
                    preview.setText(str(exc))
                full_name = self._source_name(index)
                name.setToolTip(full_name)
                name.setText(name.fontMetrics().elidedText(
                    full_name, QtCore.Qt.ElideMiddle, max(100, name.width() - 12)))
            choose.setToolTip(_tr("Elegir hoja") if index is None else _tr("Cambiar hoja"))
            choose.setAccessibleName(choose.toolTip())
            choose.setIcon(_icon("mdi:file-plus-outline" if index is None
                                 else "mdi:pencil-outline", color=_theme.tokens().text))
            left.setEnabled(index is not None)
            right.setEnabled(index is not None)
            if remove is not None:
                remove.setEnabled(index is not None)

    def _remove(self, key):
        self.arrangement[key] = None
        self.rotations[key] = 0
        self._refresh()

    def _rotate(self, key, delta):
        if self.arrangement[key] is None:
            return
        self.rotations[key] = (self.rotations[key] + delta) % 360
        self._refresh()

    def _pick(self, key):
        added_before = len(self.added)
        sources_before = len(self.sources)
        picker = QtWidgets.QDialog(self)
        picker.setWindowTitle(_tr("Elegir hoja para {position}").format(
            position=_tr(_LABELS[key]).lower()))
        picker.resize(690, 570)
        root = QtWidgets.QVBoxLayout(picker)
        root.addWidget(QtWidgets.QLabel(_tr("Selecciona una hoja o carga otro PDF.")))
        body = QtWidgets.QHBoxLayout()
        root.addLayout(body, 1)
        pages = QtWidgets.QTreeWidget()
        pages.setHeaderHidden(True)
        body.addWidget(pages, 1)
        preview = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
        preview.setMinimumSize(320, 260)
        body.addWidget(preview, 1)

        def fill():
            pages.clear()
            for source in self.sources:
                group = QtWidgets.QTreeWidgetItem([source["name"]])
                pages.addTopLevelItem(group)
                for i in range(source["count"]):
                    item = QtWidgets.QTreeWidgetItem([_tr("Hoja {i}").format(i=i + 1)])
                    index = source["start"] + i
                    item.setData(0, QtCore.Qt.UserRole, index)
                    if key == "main" and index >= self.doc.page_count:
                        item.setDisabled(True)
                    group.addChild(item)
                group.setExpanded(True)
            wanted = self.arrangement[key]
            if wanted is not None:
                for i in range(pages.topLevelItemCount()):
                    group = pages.topLevelItem(i)
                    for j in range(group.childCount()):
                        item = group.child(j)
                        if item.data(0, QtCore.Qt.UserRole) == wanted:
                            pages.setCurrentItem(item)
                            return
            if pages.topLevelItemCount() and pages.topLevelItem(0).childCount():
                pages.setCurrentItem(pages.topLevelItem(0).child(0))

        def show_item(item, _previous=None):
            index = item.data(0, QtCore.Qt.UserRole) if item else None
            if index is None:
                preview.clear()
                return
            try:
                preview.setPixmap(self._thumb(index).scaled(
                    320, 260, QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation))
            except Exception as exc:
                preview.setText(str(exc))

        pages.currentItemChanged.connect(show_item)
        fill()
        add = QtWidgets.QPushButton(_tr("+ Cargar otro PDF…"))
        add.setVisible(key != "main")

        def add_pdf():
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                picker, _tr("Cargar PDF"), "", "PDF (*.pdf)")
            if not path:
                return
            try:
                loaded = fitz.open(path)
                if not loaded.page_count:
                    loaded.close()
                    raise ValueError(_tr("El PDF no contiene hojas."))
            except Exception as exc:
                QtWidgets.QMessageBox.warning(picker, _tr("Cargar PDF"), str(exc))
                return
            start = self.page_count
            self.added.append((path, loaded))
            self.sources.append({"name": os.path.basename(path),
                                 "start": start, "count": loaded.page_count})
            fill()
            group = pages.topLevelItem(pages.topLevelItemCount() - 1)
            if key != "main":
                pages.setCurrentItem(group.child(0))

        add.clicked.connect(add_pdf)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(_tr("Usar esta hoja"))
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(_tr("Cancelar"))
        def update_use_button(*_):
            item = pages.currentItem()
            index = item.data(0, QtCore.Qt.UserRole) if item else None
            buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(
                index is not None and (key != "main" or index < self.doc.page_count))
        pages.currentItemChanged.connect(update_use_button)
        update_use_button()
        buttons.accepted.connect(picker.accept)
        buttons.rejected.connect(picker.reject)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(add)
        actions.addStretch()
        actions.addWidget(buttons)
        root.addLayout(actions)
        pages.itemDoubleClicked.connect(
            lambda item, col: picker.accept()
            if item.data(0, QtCore.Qt.UserRole) is not None else None)
        if picker.exec() != QtWidgets.QDialog.Accepted:
            for _, doc in self.added[added_before:]:
                doc.close()
            del self.added[added_before:]
            del self.sources[sources_before:]
            self._thumbs = {i: pix for i, pix in self._thumbs.items()
                            if i < self.page_count}
            return
        item = pages.currentItem()
        index = item.data(0, QtCore.Qt.UserRole) if item else None
        if index is None or (key == "main" and index >= self.doc.page_count):
            return
        rotation = self.rotations[key] if self.arrangement[key] == index else 0
        for position in ("main", *DIRECTIONS):
            if position != key and self.arrangement[position] == index:
                rotation = self.rotations[position]
                self.arrangement[position] = None
                self.rotations[position] = 0
        self.arrangement[key] = index
        self.rotations[key] = rotation
        self._refresh()

    def close_added(self):
        for _, doc in (*self.existing, *self.added):
            doc.close()


def choose_sheet_layout(parent, doc, layout=None, current=0, sources=None,
                        external_pdfs=None, rotations=None):
    dlg = SheetLayoutDialog(parent, doc, layout, current, sources,
                            external_pdfs, rotations)
    try:
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return None
        return (dict(dlg.arrangement), [path for path, _ in dlg.added],
                list(dlg.sources), dict(dlg.rotations))
    finally:
        dlg.close_added()
