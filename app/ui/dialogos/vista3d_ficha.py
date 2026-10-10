"""Ficha de atributos de la Vista 3D: lo elegido (utilidad, accesorio, buzón) en una
tabla de dos columnas Campo | Valor, arriba del panel. Sigue la selección (también la
del plano). Se puede copiar (Ctrl+C o «Copiar») y llevar al plano («Ver en el plano»).
Los datos los arma `nucleo/ficha3d.py`."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme
from ui.comun.icons import icon as _icon


class FichaPanel(QtWidgets.QGroupBox):
    ir_al_plano = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(_tr("Selección"), parent)
        v = QtWidgets.QVBoxLayout(self)
        self.lbl_titulo = QtWidgets.QLabel()
        self.lbl_titulo.setWordWrap(True)
        f = self.lbl_titulo.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() + 1.5)
        self.lbl_titulo.setFont(f)
        v.addWidget(self.lbl_titulo)
        self.tabla = QtWidgets.QTableWidget(0, 2)
        self.tabla.horizontalHeader().setVisible(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(True)
        self.tabla.setShowGrid(False)
        self.tabla.setFocusPolicy(QtCore.Qt.ClickFocus)
        v.addWidget(self.tabla)
        fila = QtWidgets.QHBoxLayout()
        self.btn_plano = QtWidgets.QPushButton(_icon("mdi:crosshairs-gps"), _tr("Ver en el plano"))
        self.btn_plano.setAutoDefault(False)
        self.btn_plano.clicked.connect(self.ir_al_plano)
        self.btn_copiar = QtWidgets.QPushButton(_icon("mdi:content-copy"), _tr("Copiar"))
        self.btn_copiar.setAutoDefault(False)
        self.btn_copiar.setToolTip(_tr("Copia la ficha (para pegarla en Excel o en un correo)"))
        self.btn_copiar.clicked.connect(self.copiar)
        for b in (self.btn_plano, self.btn_copiar):
            b.setProperty("secondary", True)
            fila.addWidget(b)
        v.addLayout(fila)
        self.lbl_vacio = QtWidgets.QLabel(_tr("Haz clic en una tubería, un accesorio o un buzón para ver sus datos."))
        self.lbl_vacio.setWordWrap(True)
        self.lbl_vacio.setObjectName("hint")
        v.addWidget(self.lbl_vacio)
        QtGui.QShortcut(QtGui.QKeySequence.Copy, self.tabla, self.copiar)
        self.limpiar()

    def mostrar(self, titulo, filas, con_plano=True):
        """Muestra la ficha. `filas` = [(campo en español, valor)]."""
        self.lbl_titulo.setText(titulo)
        self.tabla.setRowCount(len(filas))
        apagado = QtGui.QColor(theme.tokens().text_muted)
        for r, (campo, valor) in enumerate(filas):
            a = QtWidgets.QTableWidgetItem(_tr(campo))
            a.setForeground(apagado)
            b = QtWidgets.QTableWidgetItem(str(valor))
            b.setToolTip(str(valor))
            self.tabla.setItem(r, 0, a)
            self.tabla.setItem(r, 1, b)
        self.tabla.resizeRowsToContents()
        alto = sum(self.tabla.rowHeight(r) for r in range(len(filas))) + 6
        self.tabla.setFixedHeight(min(max(alto, 40), 360))
        for w in (self.lbl_titulo, self.tabla, self.btn_copiar):
            w.setVisible(True)
        self.btn_plano.setVisible(con_plano)
        self.lbl_vacio.setVisible(False)

    def limpiar(self):
        self.tabla.setRowCount(0)
        for w in (self.lbl_titulo, self.tabla, self.btn_plano, self.btn_copiar):
            w.setVisible(False)
        self.lbl_vacio.setVisible(True)

    def filas(self):
        return [(self.tabla.item(r, 0).text(), self.tabla.item(r, 1).text()) for r in range(self.tabla.rowCount())]

    def copiar(self):
        texto = "\n".join([self.lbl_titulo.text()] + [f"{c}\t{v}" for c, v in self.filas()])
        QtWidgets.QApplication.clipboard().setText(texto)
