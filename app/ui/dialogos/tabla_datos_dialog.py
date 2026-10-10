"""Ventana «Tabla de datos» (Herramientas): toda la información de cada elemento en
pestañas (utilidades, buzones y cajas, curvas, bancoductos, avisos) y «Exportar a
Excel». Doble clic en una fila = ir a ese elemento en el plano. No modal: se puede
dejar abierta mientras se trabaja («Actualizar» relee el proyecto)."""
from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

from nucleo import tabla_datos
from traduccion.i18n import t as _tr
from ui.comun.ui_common import DOWNLOADS

_ROL = QtCore.Qt.UserRole
_FILTRO_XLSX = "Excel (*.xlsx)"              # filtro de archivo (igual en ambos idiomas)


class _Item(QtWidgets.QTableWidgetItem):
    """Ordena números como números."""

    def __lt__(self, otro):
        a, b = self.data(_ROL + 1), otro.data(_ROL + 1)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return self.text().lower() < otro.text().lower()


class TablaDatosDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Tabla de datos"))
        self.resize(1200, 640)
        self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, True)
        lay = QtWidgets.QVBoxLayout(self)
        fila = QtWidgets.QHBoxLayout()
        self.buscar = QtWidgets.QLineEdit()
        self.buscar.setPlaceholderText(_tr("Buscar en la tabla…"))
        self.buscar.setClearButtonEnabled(True)
        self.buscar.textChanged.connect(self._filtrar)
        fila.addWidget(self.buscar, 1)
        self.btn_act = QtWidgets.QPushButton(_tr("Actualizar"))
        self.btn_act.setProperty("secondary", True)
        self.btn_act.clicked.connect(self.refrescar)
        self.btn_xls = QtWidgets.QPushButton(_tr("Exportar a Excel…"))
        self.btn_xls.clicked.connect(self.exportar)
        fila.addWidget(self.btn_act)
        fila.addWidget(self.btn_xls)
        lay.addLayout(fila)
        ayuda = QtWidgets.QLabel(_tr("Doble clic en una fila para verla en el plano. Clic en un encabezado para ordenar."))
        ayuda.setProperty("muted", True)
        lay.addWidget(ayuda)
        self.pestanas = QtWidgets.QTabWidget()
        lay.addWidget(self.pestanas, 1)
        self.tablas = []
        self.refrescar()

    def refrescar(self):
        actual = self.pestanas.currentIndex()
        self.tablas = self.win._tablas_de_datos()
        self.pestanas.clear()
        for tb in self.tablas:
            w = QtWidgets.QTableWidget(len(tb.filas), len(tb.columnas))
            w.setHorizontalHeaderLabels([_tr(c) for c in tb.columnas])
            w.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            w.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            w.verticalHeader().setVisible(False)
            for r, fila in enumerate(tb.filas):
                for c, v in enumerate(fila):
                    it = _Item("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))
                    it.setData(_ROL, r)
                    it.setData(_ROL + 1, v)
                    if isinstance(v, (int, float)):
                        it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    w.setItem(r, c, it)
            w.setSortingEnabled(True)
            w.sortByColumn(0, QtCore.Qt.AscendingOrder)
            w.resizeColumnsToContents()
            w.cellDoubleClicked.connect(lambda row, _c, w=w, tb=tb: self._ir(w, tb, row))
            self.pestanas.addTab(w, f"{_tr(tb.titulo)} ({len(tb.filas)})")
        if 0 <= actual < self.pestanas.count():
            self.pestanas.setCurrentIndex(actual)
        self._filtrar(self.buscar.text())

    def _filtrar(self, texto):
        texto = (texto or "").strip().lower()
        for k in range(self.pestanas.count()):
            w = self.pestanas.widget(k)
            for r in range(w.rowCount()):
                ver = not texto or any(texto in (w.item(r, c).text().lower() if w.item(r, c) else "")
                                       for c in range(w.columnCount()))
                w.setRowHidden(r, not ver)

    def _ir(self, w, tb, row):
        it = w.item(row, 0)
        if it is None:
            return
        lugar = tb.lugares[it.data(_ROL)]
        if lugar:
            self.win._ir_a_elemento(*lugar)

    def exportar(self):
        base = os.path.splitext(os.path.basename(self.win.pdf_path or "proyecto"))[0]
        ruta, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, _tr("Exportar a Excel"), os.path.join(DOWNLOADS, base + "_datos.xlsx"), _FILTRO_XLSX)
        if not ruta:
            return
        try:
            tabla_datos.exportar_excel(self.tablas, ruta)
        except Exception as e:                      # archivo abierto en Excel, sin permiso…
            QtWidgets.QMessageBox.warning(self, _tr("Exportar a Excel"), _tr(
                "No se pudo guardar el Excel (¿está abierto?).\n\n{e}").format(e=e))
            return
        self.win._info(_tr("Tabla de datos exportada: {ruta}").format(ruta=ruta))


def abrir(win):
    dlg = getattr(win, "_tabla_dlg", None)
    if dlg is None:
        dlg = TablaDatosDialog(win)
        win._tabla_dlg = dlg
    else:
        dlg.refrescar()
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg
