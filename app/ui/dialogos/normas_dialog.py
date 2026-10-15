"""Ventana «Normativas de diseño» (formato de tablas del usuario, 2026-10-09).

Las normativas son un Excel simple (`normas_excel`): aquí se ven sus tablas tal cual,
la lista de avisos del proyecto (clic = ir al lugar; se APRUEBAN con una nota y queda
el registro de quién y cuándo, `nucleo/normas_aprobacion`) y los botones para importar el
Excel, exportarlo (para editarlo en Excel) o volver a los valores iniciales. Los tipos
nuevos que el usuario agrega con el «+» del panel ya están en el catálogo y salen al
exportar. No modal: se refresca sola al redibujar el plano."""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import normas_catalogo as nc
from nucleo import normas_excel
from nucleo.normas_validar import CLASES
from traduccion.i18n import N_, t as _tr
from ui.comun.ui_common import DOWNLOADS

_ROL = QtCore.Qt.UserRole
_FILTRO_XLSX = "Excel (*.xlsx)"              # filtro de archivo (igual en ambos idiomas)

def _n(v):
    return "" if v is None else nc.texto_numero(v)


def _extremos(r):
    return ["", ""] if not r else [_n(r[0]), _n(r[1])]


# (título de la pestaña, encabezados, función que da las filas como texto)
_PESTANAS = [
    (N_("Tipos"), normas_excel.COL_TIPOS, lambda cat: [list(x) for x in cat["tipos"]]),
    (N_("Diámetros (presión)"), normas_excel.COL_DIAM,
     lambda cat: [[f["utilidad"], f["tipo"], nc.texto_lista(f["diametros"]), _n(f.get("diam_min")),
                   _n(f.get("diam_max")), f.get("nota") or ""] for f in cat["diametros"]]),
    (N_("Accesorios (presión)"), normas_excel.COL_ACC,
     lambda cat: [[f["utilidad"], f["accesorio"], f.get("solo_en") or "", nc.texto_lista(f.get("diam_principal")),
                   f.get("prohibido_en") or "", "" if f.get("ramal") is None else f"{int(f['ramal'])}",
                   nc.texto_lista(f.get("angulos"))] for f in cat["accesorios"]]),
    (N_("Eléctrico y telecom"), normas_excel.COL_ELEC,
     lambda cat: [[f["utilidad"], f.get("estructura") or "", f.get("tipo") or "", *_extremos(f.get("amperaje")),
                   *_extremos(f.get("longitud")), nc.texto_lista(f.get("diam_fijo")), _n(f.get("diam_min")),
                   _n(f.get("diam_max")), _n(f.get("radio_min")), _n(f.get("radio_max")),
                   nc.texto_lista(f.get("radio_fijo"))]
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
        pag = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(pag)
        barra = QtWidgets.QHBoxLayout()
        self.btn_aprobar = QtWidgets.QPushButton(_tr("Aprobar seleccionados…"))
        self.btn_aprobar.setToolTip(_tr("Revisaste el aviso y se acepta así: deja de marcarse en el plano y queda "
                                        "registrado como aprobado (quién, cuándo y por qué)."))
        self.btn_quitar = QtWidgets.QPushButton(_tr("Quitar aprobación"))
        self.btn_quitar.setProperty("secondary", True)
        self.chk_aprobados = QtWidgets.QCheckBox(_tr("Mostrar aprobados"))
        self.chk_aprobados.setChecked(True)
        self.btn_aprobar.clicked.connect(lambda: self.aprobar())
        self.btn_quitar.clicked.connect(self.quitar_aprobacion)
        self.chk_aprobados.toggled.connect(lambda _on: self.refrescar())
        for b in (self.btn_aprobar, self.btn_quitar):
            b.setMinimumHeight(32)
            barra.addWidget(b)
        barra.addWidget(self.chk_aprobados)
        barra.addStretch(1)
        pl.addLayout(barra)
        self.lst_avisos = QtWidgets.QTreeWidget()
        self.lst_avisos.setHeaderLabels([_tr("Utilidad"), _tr("Aviso"), _tr("Estado")])
        self.lst_avisos.setRootIsDecorated(False)
        self.lst_avisos.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.lst_avisos.itemClicked.connect(self._ir)
        self.lst_avisos.itemSelectionChanged.connect(self._botones)
        pl.addWidget(self.lst_avisos, 1)
        self.pestanas.addTab(pag, _tr("Avisos"))
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
        ver_ap = self.chk_aprobados.isChecked()
        orden = sorted(range(len(avisos)), key=lambda k: (bool(avisos[k].aprobado), avisos[k].info))
        for n in orden:                                  # primero los pendientes
            a = avisos[n]
            if a.aprobado and not ver_ap:
                continue
            quien = f"#{a.pipe + 1}" if a.pipe is not None and a.pipe >= 0 else ""
            r = a.aprobado or {}
            if a.aprobado:
                estado = " · ".join(x for x in ("✔ " + _tr("Aprobado"), r.get("fecha"), r.get("usuario"),
                                                 r.get("nota")) if x)
                marca = "✔ "
            else:
                estado, marca = (_tr("Información"), "ⓘ ") if a.info else (_tr("Pendiente"), "⚠ ")
            it = QtWidgets.QTreeWidgetItem([quien, marca + a.mensaje, estado])
            tip = _tr(CLASES.get(a.clase, a.clase)) + "\n" + a.mensaje
            if r.get("nota"):
                tip += "\n\n" + _tr("Nota: {nota}").format(nota=r["nota"])
            for c in range(3):
                it.setToolTip(c, tip)
            if a.aprobado:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor(60, 150, 80)))
            it.setData(0, _ROL, n)
            self.lst_avisos.addTopLevelItem(it)
        for r in (self._registros_viejos() if ver_ap else []):     # aprobados cuyo aviso ya no está
            u = r.get("utilidad")
            it = QtWidgets.QTreeWidgetItem([f"#{u + 1}" if isinstance(u, int) and u >= 0 else "",
                                            "✔ " + (r.get("mensaje") or ""),
                                            _tr("Ya no aplica (aprobado {fecha})").format(fecha=r.get("fecha", ""))])
            it.setForeground(1, QtGui.QBrush(QtGui.QColor(140, 140, 140)))
            it.setData(0, _ROL + 1, r.get("clave"))
            self.lst_avisos.addTopLevelItem(it)
        if not avisos:
            self.lst_avisos.addTopLevelItem(QtWidgets.QTreeWidgetItem(["", _tr("Todo cumple las normativas.")]))
        self.lst_avisos.resizeColumnToContents(0)
        self.lst_avisos.setColumnWidth(1, 520)
        self._botones()
        n = sum(1 for a in avisos if not a.info and not a.aprobado)
        self.pestanas.setTabText(0, _tr("Avisos ({n})").format(n=n) if n else _tr("Avisos"))
        cat = self.win.normas_cat
        for w, (_t, _c, filas_de) in zip(self.vistas, _PESTANAS):
            filas = filas_de(cat)
            w.setRowCount(len(filas))
            for r, fila in enumerate(filas):
                for c, v in enumerate(fila):
                    w.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))
            w.resizeColumnsToContents()

    def _registros_viejos(self):
        usadas = {a.aprobado.get("clave") for a in getattr(self.win, "_normas_avisos", None) or [] if a.aprobado}
        return [r for r in getattr(self.win, "normas_aprobados", None) or [] if r.get("clave") not in usadas]

    def _elegidos(self):
        avisos = getattr(self.win, "_normas_avisos", None) or []
        sel = self.lst_avisos.selectedItems()
        idx = [it.data(0, _ROL) for it in sel]
        viejos = [it.data(0, _ROL + 1) for it in sel if it.data(0, _ROL + 1)]
        return [avisos[int(n)] for n in idx if n is not None and 0 <= int(n) < len(avisos)], viejos

    def _botones(self):
        av, viejos = self._elegidos()
        self.btn_aprobar.setEnabled(any(not a.info and not a.aprobado for a in av))
        self.btn_quitar.setEnabled(any(a.aprobado for a in av) or bool(viejos))

    def aprobar(self, nota=None):
        """Aprueba los avisos seleccionados (pide un motivo opcional)."""
        av = [a for a in self._elegidos()[0] if not a.info and not a.aprobado]
        if not av:
            return 0
        if nota is None:
            nota, ok = QtWidgets.QInputDialog.getText(
                self, _tr("Aprobar avisos"), _tr("Se aprobarán {n} aviso(s). Queda registrado quién y cuándo.\n"
                                                 "Motivo o nota (opcional):").format(n=len(av)))
            if not ok:
                return 0
        return self.win.aprobar_avisos(av, nota)

    def quitar_aprobacion(self):
        av, viejos = self._elegidos()
        return self.win.quitar_aprobacion([a for a in av if a.aprobado], viejos)

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
            problemas = []
            cat, faltan = normas_excel.importar(ruta, problemas)
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
        if problemas:
            msg += "\n\n" + _tr("No se usó (corrígelo en el Excel):") + "\n• " + "\n• ".join(problemas[:12])
            if len(problemas) > 12:
                msg += "\n• " + _tr("… y {n} más").format(n=len(problemas) - 12)
            QtWidgets.QMessageBox.warning(self, _tr("Importar Excel de normativas"), msg)
            return
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
