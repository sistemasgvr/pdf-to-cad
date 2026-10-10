"""Ventana «Normativas de diseño» (formato de tablas del usuario, 2026-10-09).

Las normativas son un Excel simple (`normas_excel`): aquí se ven sus tablas tal cual,
la lista de avisos del proyecto (clic = ir al lugar) y los botones para importar el
Excel, exportarlo (para editarlo en Excel) o volver a los valores iniciales. Los tipos
nuevos que el usuario agrega con el «+» del panel ya están en el catálogo y salen al
exportar. No modal: se refresca sola al redibujar el plano."""
from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

from nucleo import normas_catalogo as nc
from nucleo import normas_excel
from nucleo.normas_validar import CLASES
from traduccion.i18n import N_, t as _tr
from ui.comun.ui_common import DOWNLOADS

_ROL = QtCore.Qt.UserRole
_FILTRO_XLSX = "Excel (*.xlsx)"              # filtro de archivo (igual en ambos idiomas)

# (título de la pestaña, encabezados, función que da las filas como texto)
_PESTANAS = [
    (N_("Tipos"), normas_excel.COL_TIPOS, lambda cat: [list(x) for x in cat["tipos"]]),
    (N_("Diámetros (presión)"), normas_excel.COL_DIAM,
     lambda cat: [[f["utilidad"], f["tipo"], nc.texto_lista(f["diametros"]), f.get("nota") or ""]
                  for f in cat["diametros"]]),
    (N_("Accesorios (presión)"), normas_excel.COL_ACC,
     lambda cat: [[f["utilidad"], f["accesorio"], f.get("solo_en") or "", nc.texto_lista(f.get("diam_principal")),
                   f.get("prohibido_en") or "", "" if f.get("ramal") is None else f"{int(f['ramal'])}",
                   nc.texto_lista(f.get("angulos"))] for f in cat["accesorios"]]),
    (N_("Eléctrico y telecom"), normas_excel.COL_ELEC,
     lambda cat: [[f["utilidad"], f.get("estructura") or "", f.get("tipo") or "", nc.texto_rango(f.get("amperaje")),
                   nc.texto_rango(f.get("longitud")), nc.texto_lista(f.get("diam_fijo")),
                   "" if f.get("diam_min") is None else nc.texto_numero(f["diam_min"]),
                   "" if f.get("diam_max") is None else nc.texto_numero(f["diam_max"]),
                   "" if f.get("radio_min") is None else nc.texto_numero(f["radio_min"])]
                  for f in cat["electricas"]]),
]


class NormasDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Normativas de diseño"))
        self.resize(980, 600)
        self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, True)
        lay = QtWidgets.QVBoxLayout(self)
        cab = QtWidgets.QLabel(_tr("Las normativas vienen de un Excel simple: expórtalo, edítalo en Excel e "
                                   "impórtalo. Valen para todos tus proyectos."))
        cab.setWordWrap(True)
        lay.addWidget(cab)
        fila = QtWidgets.QHBoxLayout()
        b_imp = QtWidgets.QPushButton(_tr("Importar Excel…"))
        b_exp = QtWidgets.QPushButton(_tr("Exportar Excel…"))
        b_base = QtWidgets.QPushButton(_tr("Volver a los valores iniciales"))
        b_base.setProperty("secondary", True)
        b_imp.clicked.connect(self.importar)
        b_exp.clicked.connect(self.exportar)
        b_base.clicked.connect(self.restaurar)
        for b in (b_imp, b_exp, b_base):
            b.setMinimumHeight(34)
            fila.addWidget(b)
        fila.addStretch(1)
        lay.addLayout(fila)
        self.pestanas = QtWidgets.QTabWidget()
        lay.addWidget(self.pestanas, 1)
        self.lst_avisos = QtWidgets.QTreeWidget()
        self.lst_avisos.setHeaderLabels([_tr("Utilidad"), _tr("Aviso")])
        self.lst_avisos.setRootIsDecorated(False)
        self.lst_avisos.itemClicked.connect(self._ir)
        self.pestanas.addTab(self.lst_avisos, _tr("Avisos"))
        self.vistas = []
        for titulo, columnas, _f in _PESTANAS:
            w = QtWidgets.QTableWidget(0, len(columnas))
            w.setHorizontalHeaderLabels(list(columnas))      # como en el Excel (es el formato de datos)
            w.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            w.verticalHeader().setVisible(False)
            self.vistas.append(w)
            self.pestanas.addTab(w, _tr(titulo))
        self.refrescar()

    def refrescar(self):
        avisos = getattr(self.win, "_normas_avisos", None) or []
        self.lst_avisos.clear()
        for n, a in enumerate(avisos):
            quien = f"#{a.pipe + 1}" if a.pipe is not None and a.pipe >= 0 else ""
            it = QtWidgets.QTreeWidgetItem([quien, ("ⓘ " if a.info else "⚠ ") + a.mensaje])
            it.setToolTip(1, _tr(CLASES.get(a.clase, a.clase)) + "\n" + a.mensaje)
            it.setData(0, _ROL, n)
            self.lst_avisos.addTopLevelItem(it)
        if not avisos:
            self.lst_avisos.addTopLevelItem(QtWidgets.QTreeWidgetItem(["", _tr("Todo cumple las normativas.")]))
        self.lst_avisos.resizeColumnToContents(0)
        n = sum(1 for a in avisos if not a.info)
        self.pestanas.setTabText(0, _tr("Avisos ({n})").format(n=n) if n else _tr("Avisos"))
        cat = self.win.normas_cat
        for w, (_t, _c, filas_de) in zip(self.vistas, _PESTANAS):
            filas = filas_de(cat)
            w.setRowCount(len(filas))
            for r, fila in enumerate(filas):
                for c, v in enumerate(fila):
                    w.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))
            w.resizeColumnsToContents()

    def _ir(self, item, _col):
        n = item.data(0, _ROL)
        if n is not None:
            self.win._normas_ir_a(int(n))

    def importar(self):
        ruta, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Importar Excel de normativas"), DOWNLOADS,
                                                        _FILTRO_XLSX)
        if not ruta:
            return
        try:
            cat, faltan = normas_excel.importar(ruta)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, _tr("Importar Excel de normativas"), _tr(
                "No se pudo leer el Excel.\n\n{e}").format(e=e))
            return
        self.win._usar_normas(cat)
        msg = _tr("Normativas importadas: {t} tipos, {d} filas de diámetros, {a} de accesorios y {e} de "
                  "eléctrico y telecom.").format(t=len(cat["tipos"]), d=len(cat["diametros"]),
                                                 a=len(cat["accesorios"]), e=len(cat["electricas"]))
        if faltan:
            msg += "\n\n" + _tr("No se encontraron estas hojas (quedan vacías): {h}.").format(h=", ".join(faltan))
        QtWidgets.QMessageBox.information(self, _tr("Importar Excel de normativas"), msg)

    def exportar(self):
        ruta, _ = QtWidgets.QFileDialog.getSaveFileName(self, _tr("Exportar Excel de normativas"),
                                                        os.path.join(DOWNLOADS, "Normativas.xlsx"), _FILTRO_XLSX)
        if not ruta:
            return
        try:
            normas_excel.exportar(self.win.normas_cat, ruta)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, _tr("Exportar Excel de normativas"), _tr(
                "No se pudo guardar el Excel (¿está abierto?).\n\n{e}").format(e=e))
            return
        self.win._info(_tr("Normativas exportadas: {ruta}").format(ruta=ruta))

    def restaurar(self):
        r = QtWidgets.QMessageBox.question(self, _tr("Volver a los valores iniciales"), _tr(
            "Se reemplazan las normativas por las iniciales (los tipos que agregaste también se quitan). "
            "¿Seguir?"), QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if r == QtWidgets.QMessageBox.Yes:
            self.win._usar_normas(nc.nuevo())


def abrir(win, en_avisos=False):
    dlg = getattr(win, "_normas_dlg", None)
    if dlg is None:
        dlg = NormasDialog(win)
        win._normas_dlg = dlg
    dlg.refrescar()
    if en_avisos:
        dlg.pestanas.setCurrentIndex(0)
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg
