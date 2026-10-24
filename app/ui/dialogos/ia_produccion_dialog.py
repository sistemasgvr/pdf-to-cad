"""IA → «Pasar a producción…» (pedido del usuario 2026-10-24): de lo que el equipo enseñó en desarrollo se marcan
las enseñanzas buenas y se copian al archivo de producción, el que viaja en el instalador (`ia/produccion`).

Una fila por enseñanza (la más nueva arriba): casilla, tipo, texto, proyecto, quién, fecha y si ya está en
producción. «Solo las que faltan» esconde las que ya pasaron. «Pasar a producción» copia las marcadas (y, si se
elige, los textos ya redactados de normativas y del manual); «Quitar de producción» saca las marcadas. Solo existe
ejecutando desde el repo: el programa instalado no tiene archivo de desarrollo.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ia import memoria as M
from ia import produccion as PR
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

TIPOS = {M.NOTA: N_("Nota"), M.CORRECCION: N_("Corrección"), M.VALORACION: N_("Valoración"),
         M.SOLUCION: N_("Solución aplicada")}
COLUMNAS = (N_("Tipo"), N_("Enseñanza"), N_("Proyecto"), N_("Quién"), N_("Fecha"), N_("En producción"))


def texto_de(reg):
    if reg.get("tipo") == M.VALORACION:
        bien = (reg.get("valor") or 0) > 0
        return (_tr("Útil") if bien else _tr("No útil")) + " · " + (reg.get("pregunta") or "")
    if reg.get("tipo") == M.CORRECCION and reg.get("pregunta"):
        return f"{reg.get('pregunta')} → {reg.get('texto') or ''}"
    return reg.get("texto") or ""


class ProduccionDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.setWindowTitle(_tr("Pasar a producción"))
        self.resize(1000, 600)
        self.dev, self.prod = PR.almacenes()
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr(
            "Marca las enseñanzas de desarrollo que deben ir al cliente y pulsa «Pasar a producción». Producción es "
            "el archivo que va en el instalador: el programa del cliente lo usa pero no lo cambia. Las conversaciones "
            "no pasan."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.lbl_rutas = QtWidgets.QLabel(_tr("Desarrollo: {d}\nProducción: {p}").format(d=self.dev.ruta,
                                                                                          p=self.prod.ruta))
        self.lbl_rutas.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.lbl_rutas.setStyleSheet("font-size: small;")
        lay.addWidget(self.lbl_rutas)
        fila = QtWidgets.QHBoxLayout()
        self.chk_faltan = QtWidgets.QCheckBox(_tr("Solo las que faltan"))
        self.chk_faltan.setChecked(True)
        self.chk_faltan.toggled.connect(self.refrescar)
        self.btn_todas = QtWidgets.QPushButton(_tr("Marcar todas"))
        self.btn_todas.clicked.connect(lambda: self._marcar_todas(True))
        self.btn_ninguna = QtWidgets.QPushButton(_tr("Desmarcar todas"))
        self.btn_ninguna.clicked.connect(lambda: self._marcar_todas(False))
        fila.addWidget(self.chk_faltan)
        fila.addStretch(1)
        fila.addWidget(self.btn_todas)
        fila.addWidget(self.btn_ninguna)
        lay.addLayout(fila)
        self.tabla = QtWidgets.QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels([_tr(c) for c in COLUMNAS])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tabla.setWordWrap(True)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.tabla.itemChanged.connect(lambda *_a: self._sincronizar())
        lay.addWidget(self.tabla, 1)
        self.chk_redaccion = QtWidgets.QCheckBox()
        self.chk_redaccion.toggled.connect(lambda *_a: self._sincronizar())
        lay.addWidget(self.chk_redaccion)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        botones = QtWidgets.QHBoxLayout()
        self.btn_quitar = QtWidgets.QPushButton(_tr("Quitar de producción"))
        self.btn_quitar.setProperty("soft", True)
        self.btn_quitar.clicked.connect(self.quitar)
        self.btn_pasar = QtWidgets.QPushButton(_tr("Pasar a producción"))
        self.btn_pasar.setDefault(True)
        self.btn_pasar.clicked.connect(self.pasar)
        cerrar = QtWidgets.QPushButton(_tr("Cerrar"))
        cerrar.clicked.connect(self.accept)
        botones.addWidget(self.btn_quitar)
        botones.addStretch(1)
        botones.addWidget(self.btn_pasar)
        botones.addWidget(cerrar)
        lay.addLayout(botones)
        self.refrescar()

    # ── datos ──
    def refrescar(self):
        filas = PR.lista(self.dev, self.prod)
        if self.chk_faltan.isChecked():
            filas = [(r, en) for r, en in filas if not en]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(filas))
        for i, (reg, en) in enumerate(filas):
            tipo = QtWidgets.QTableWidgetItem(_tr(TIPOS.get(reg.get("tipo"), reg.get("tipo") or "")))
            tipo.setFlags(tipo.flags() | QtCore.Qt.ItemIsUserCheckable)
            tipo.setCheckState(QtCore.Qt.Unchecked)
            tipo.setData(QtCore.Qt.UserRole, reg.get("id"))
            self.tabla.setItem(i, 0, tipo)
            valores = (texto_de(reg), reg.get("proyecto") or "", reg.get("autor") or "", reg.get("fecha") or "",
                       "✔" if en else "")
            for c, v in enumerate(valores, 1):
                self.tabla.setItem(i, c, QtWidgets.QTableWidgetItem(str(v)))
        self.tabla.blockSignals(False)
        self.tabla.resizeRowsToContents()
        n = len(PR.redaccion_general(self.dev, self.prod))
        self.chk_redaccion.setText(_tr("Pasar también los textos ya redactados de normativas y del manual ({n})")
                                   .format(n=n))
        self.chk_redaccion.setEnabled(n > 0)
        self.chk_redaccion.setChecked(n > 0 and self.chk_redaccion.isChecked())
        error = self.dev.error or self.prod.error
        self.lbl.setText(_tr("No se pudo leer: {e}").format(e=error) if error else "")
        self._sincronizar()

    def marcadas(self):
        return [self.tabla.item(i, 0).data(QtCore.Qt.UserRole) for i in range(self.tabla.rowCount())
                if self.tabla.item(i, 0).checkState() == QtCore.Qt.Checked]

    def _marcar_todas(self, si):
        self.tabla.blockSignals(True)
        for i in range(self.tabla.rowCount()):
            self.tabla.item(i, 0).setCheckState(QtCore.Qt.Checked if si else QtCore.Qt.Unchecked)
        self.tabla.blockSignals(False)
        self._sincronizar()

    def _sincronizar(self):
        n = len(self.marcadas())
        self.btn_pasar.setEnabled(n > 0 or (self.chk_redaccion.isEnabled() and self.chk_redaccion.isChecked()))
        self.btn_quitar.setEnabled(n > 0)

    # ── acciones ──
    def pasar(self):
        try:
            n, k = PR.pasar(self.dev, self.prod, self.marcadas(), self.chk_redaccion.isChecked())
        except (OSError, ValueError) as e:
            self.lbl.setText(_tr("No se pudo escribir producción: {e}").format(e=e))
            return
        self.refrescar()
        self.lbl.setText(_tr("Pasaron a producción: {n} enseñanzas y {k} textos. Súbelo con Git para que vaya en "
                             "el próximo instalador.").format(n=n, k=k))

    def quitar(self):
        try:
            n = PR.quitar(self.prod, self.marcadas())
        except (OSError, ValueError) as e:
            self.lbl.setText(_tr("No se pudo escribir producción: {e}").format(e=e))
            return
        self.refrescar()
        self.lbl.setText(_tr("Salieron de producción: {n} enseñanzas.").format(n=n))


def abrir(win):
    ProduccionDialog(win).exec()
