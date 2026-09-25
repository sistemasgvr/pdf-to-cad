"""xdata_dialog.py — Modal «Datos extendidos» de una utilidad o estructura.

Tabla Campo | Valor: arriba los campos automáticos que vinieron del PDF
(capa OCG, disciplina, sistema, ubicación, estado, origen), bloqueados porque
son la referencia fiel del plano; debajo los del usuario, que se agregan,
editan y quitan libremente (como un Property Set de Civil 3D).
"""
from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

import xdata
from i18n import t as _tr


class XDataDialog(QtWidgets.QDialog):
    def __init__(self, parent, title: str, xd: dict):
        super().__init__(parent)
        self.setWindowTitle(_tr("Datos extendidos") + " — " + title)
        self.resize(700, 600)                  # las ~10 filas del PDF a la vista sin scroll
        self._auto: Dict[str, str] = dict(xd.get(xdata.AUTO) or {})
        lay = QtWidgets.QVBoxLayout(self)

        head = QtWidgets.QLabel(
            _tr("Información de referencia que no forma parte de las propiedades de la red. "
                "Los campos con 🔒 vienen del PDF y no se editan; los tuyos sí."))
        head.setWordWrap(True)
        lay.addWidget(head)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([_tr("Campo"), _tr("Valor")])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        lay.addWidget(self.table, 1)

        muted = self.palette().color(QtGui.QPalette.Disabled, QtGui.QPalette.Text)
        for name, value in self._auto.items():
            self._add_row("🔒 " + name, value, locked=True, color=muted)
        for name, value in (xd.get(xdata.USER) or {}).items():
            self._add_row(name, value)
        if not self._auto:
            self.lbl_empty = QtWidgets.QLabel(
                _tr("Este elemento no viene del reconocimiento del PDF: no tiene datos automáticos."))
            self.lbl_empty.setWordWrap(True)
            lay.addWidget(self.lbl_empty)

        row = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton(_tr("Agregar campo"))
        self.btn_add.clicked.connect(self._add_user_row)
        self.btn_remove = QtWidgets.QPushButton(_tr("Quitar campo"))
        self.btn_remove.clicked.connect(self._remove_row)
        self.btn_copy = QtWidgets.QPushButton(_tr("Copiar todo"))
        self.btn_copy.clicked.connect(self._copy_all)
        row.addWidget(self.btn_add); row.addWidget(self.btn_remove); row.addStretch(1); row.addWidget(self.btn_copy)
        lay.addLayout(row)

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self._sync_buttons()
        self.table.resizeRowsToContents()

    # ── filas ────────────────────────────────────────────────────────────
    def _add_row(self, name: str, value: str, locked: bool = False, color=None) -> int:
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, text in enumerate((name, value)):
            it = QtWidgets.QTableWidgetItem(str(text))
            if locked:
                it.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                it.setData(QtCore.Qt.UserRole, "auto")
                if color is not None and c == 0:
                    it.setForeground(QtGui.QBrush(color))
            self.table.setItem(r, c, it)
        return r

    def _is_locked(self, r: int) -> bool:
        it = self.table.item(r, 0)
        return it is not None and it.data(QtCore.Qt.UserRole) == "auto"

    def _add_user_row(self):
        r = self._add_row("", "")
        self.table.setCurrentCell(r, 0)
        self.table.editItem(self.table.item(r, 0))

    def _remove_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if not self._is_locked(r):
                self.table.removeRow(r)
        self._sync_buttons()

    def _sync_buttons(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        self.btn_remove.setEnabled(bool(rows) and any(not self._is_locked(r) for r in rows))

    def _copy_all(self):
        lines = []
        for r in range(self.table.rowCount()):
            a = self.table.item(r, 0); b = self.table.item(r, 1)
            name = (a.text() if a else "").replace("🔒 ", "")
            lines.append(f"{name}\t{b.text() if b else ''}")
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))

    # ── resultado ────────────────────────────────────────────────────────
    def user_rows(self):
        out = []
        for r in range(self.table.rowCount()):
            if self._is_locked(r):
                continue
            a = self.table.item(r, 0); b = self.table.item(r, 1)
            out.append(((a.text() if a else "").strip(), b.text() if b else ""))
        return out

    def user_fields(self) -> Dict[str, str]:
        return {name: value for name, value in self.user_rows() if name}

    def _accept(self):
        err = xdata.validate_user(self.user_rows(), self._auto)
        if err:
            QtWidgets.QMessageBox.warning(self, _tr("Datos extendidos"), _tr(err))
            return
        self.accept()


def edit_xdata(parent, title: str, obj: dict) -> Optional[Dict[str, str]]:
    """Abre el modal; devuelve los campos del usuario (dict) o None si se cancela."""
    dlg = XDataDialog(parent, title, xdata.get(obj))
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return dlg.user_fields()
