"""Textos cortos del monitor (duraciones, memoria, horas) y la tabla genérica que usan sus pestañas."""
from __future__ import annotations

import datetime
from typing import List, Optional, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr

ORDEN = QtCore.Qt.UserRole + 1          # valor para ordenar (número o texto)
DATO = QtCore.Qt.UserRole + 2           # lo que la fila representa (un suceso)


def dur(s: Optional[float]) -> str:
    if s is None:
        return "—"
    if s < 1:
        return _tr("{n} ms").format(n=int(round(s * 1000)))
    if s < 60:
        return _tr("{n} s").format(n=f"{s:.1f}")
    return _tr("{m} min {s} s").format(m=int(s // 60), s=int(s % 60))


def mb(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return _tr("{n} GB").format(n=f"{v / 1024:.2f}") if v >= 1024 else _tr("{n} MB").format(n=int(round(v)))


def hora(t: Optional[float]) -> str:
    return datetime.datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "—"


def funcion_legible(nombre: str) -> str:
    """«reconocimiento.recognition_arcs:_seg_dist» → «_seg_dist · reconocimiento.recognition_arcs»."""
    mod, _, fn = nombre.rpartition(":")
    return f"{fn}  ·  {mod}" if mod else nombre


class Tabla(QtWidgets.QTableView):
    """Tabla de solo lectura, ordenable por clic en el encabezado. Cada celda = (texto, valor para ordenar); cada
    fila puede llevar un dato (`elegida` lo emite al elegirla)."""
    elegida = QtCore.Signal(object)

    def __init__(self, columnas: Sequence[str], parent=None, estirar: int = 0):
        super().__init__(parent)
        self._modelo = QtGui.QStandardItemModel(0, len(columnas), self)
        self._modelo.setHorizontalHeaderLabels(list(columnas))
        self._modelo.setSortRole(ORDEN)
        self.setModel(self._modelo)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(26)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        h.setStretchLastSection(False)
        self._estirar = estirar
        h.setSectionResizeMode(estirar, QtWidgets.QHeaderView.Stretch)
        self._orden = None
        self.selectionModel().currentRowChanged.connect(self._fila)

    def poner(self, filas: List[tuple], datos: Optional[list] = None, alinear_der=()) -> None:
        """`filas` = [(celda, …)], celda = texto o (texto, orden). Conserva el orden elegido y la fila elegida."""
        elegido = self.dato_actual()
        h = self.horizontalHeader()
        col, sentido = h.sortIndicatorSection(), h.sortIndicatorOrder()
        self.setSortingEnabled(False)
        self._modelo.setRowCount(0)
        for i, fila in enumerate(filas):
            items = []
            for j, c in enumerate(fila):
                texto, orden = c if isinstance(c, tuple) else (c, c)
                it = QtGui.QStandardItem("" if texto is None else str(texto))
                it.setData(orden if orden is not None else -1, ORDEN)
                if j in alinear_der:
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                if datos is not None and j == 0:
                    it.setData(datos[i], DATO)
                items.append(it)
            self._modelo.appendRow(items)
        self.setSortingEnabled(True)
        if col >= 0 and self._orden is not None:
            self.sortByColumn(col, sentido)
        if elegido is not None:
            for r in range(self._modelo.rowCount()):
                if self._modelo.item(r, 0).data(DATO) is elegido:
                    self.selectRow(r)
                    break

    def ordenar(self, col: int, descendente: bool = True) -> None:
        """Orden INICIAL; luego manda el que elija el usuario con el encabezado."""
        if self._orden is not None:
            return
        self._orden = (col, descendente)
        self.sortByColumn(col, QtCore.Qt.DescendingOrder if descendente else QtCore.Qt.AscendingOrder)

    def anchos(self, *px) -> None:
        for i, w in enumerate(px):
            if i != self._estirar and w:
                self.setColumnWidth(i, w)

    def dato_actual(self):
        i = self.currentIndex()
        if not i.isValid():
            return None
        return self._modelo.item(i.row(), 0).data(DATO)

    def _fila(self, actual, _anterior):
        if actual.isValid():
            self.elegida.emit(self._modelo.item(actual.row(), 0).data(DATO))


def tarjeta(titulo: str = "") -> tuple:
    """QFrame#tarjeta con un título opcional; devuelve (frame, layout)."""
    f = QtWidgets.QFrame()
    f.setObjectName("tarjeta")
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    if titulo:
        lb = QtWidgets.QLabel(titulo)
        lb.setProperty("rol", "h3")
        lay.addWidget(lb)
    return f, lay
