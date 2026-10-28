"""Ventana «Tabla de datos» (Herramientas): toda la información de cada elemento en
pestañas (utilidades, buzones y cajas, curvas, bancoductos, avisos, conflictos C-n, cotas
por vértice) y el Excel de IDA Y VUELTA (`nucleo/tabla_excel.py`): «Exportar a Excel» con
las columnas editables en verde e «Importar Excel…», que muestra los cambios antes de
aplicarlos (se deshacen con Ctrl+Z). Doble clic en una fila = ir a ese elemento en el
plano. No modal: se puede dejar abierta mientras se trabaja."""
from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

from nucleo import tabla_excel
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
        lay.setContentsMargins(24, 18, 24, 12)
        lay.setSpacing(12)
        # 2.0.0 (como el prototipo): cabecera con las acciones a la derecha, pestañas segmentadas, buscador,
        # filtro por utilidad en fichas y densidad. Mismos datos, mismos botones, misma lógica.
        cab = QtWidgets.QHBoxLayout()
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(2)
        titulo = QtWidgets.QLabel(_tr("Tabla de datos"))
        titulo.setProperty("rol", "h1")
        tx.addWidget(titulo)
        ayuda = QtWidgets.QLabel(_tr("Doble clic en una fila para verla en el plano. Clic en un encabezado para ordenar."))
        ayuda.setProperty("rol", "t2")
        ayuda.setWordWrap(True)
        tx.addWidget(ayuda)
        cab.addLayout(tx, 1)
        self.btn_act = QtWidgets.QPushButton(_tr("Actualizar"))
        self.btn_act.setProperty("kind", "ghost")
        self.btn_act.clicked.connect(self.refrescar)
        self.btn_xls = QtWidgets.QPushButton(_tr("Exportar a Excel…"))
        self.btn_xls.setProperty("kind", "primary")
        self.btn_xls.setToolTip(_tr("Las columnas verdes se pueden editar en Excel y volver a cargar"))
        self.btn_xls.clicked.connect(self.exportar)
        self.btn_imp = QtWidgets.QPushButton(_tr("Importar Excel…"))
        self.btn_imp.setToolTip(_tr("Carga un Excel exportado y editado: cotas, tapas y fondos, radios, nombre, "
                                    "tipo, estado, familia, tamaño o diámetro, material y amperaje. Verás los cambios "
                                    "antes de aplicarlos."))
        self.btn_imp.clicked.connect(self.importar)
        for b in (self.btn_act, self.btn_imp, self.btn_xls):
            b.setAutoDefault(False)
            cab.addWidget(b, 0, QtCore.Qt.AlignTop)
        lay.addLayout(cab)
        self._seg = QtWidgets.QFrame()
        self._seg.setObjectName("segmentado")
        QtWidgets.QHBoxLayout(self._seg).setContentsMargins(3, 3, 3, 3)
        self._grupo_seg = QtWidgets.QButtonGroup(self._seg)
        self._grupo_seg.idClicked.connect(lambda i: self.pestanas.setCurrentIndex(i))
        lay.addWidget(self._seg)
        fila = QtWidgets.QHBoxLayout()
        from ui.comun import rediseno as R
        self.buscar = R.CampoBuscar("Buscar en la tabla…")
        self.buscar.setClearButtonEnabled(True)
        self.buscar.textChanged.connect(self._filtrar)
        fila.addWidget(self.buscar, 2)
        self._chips = QtWidgets.QHBoxLayout()
        self._chips.setSpacing(6)
        fila.addLayout(self._chips)
        self._grupo_chips = QtWidgets.QButtonGroup(self)
        self._grupo_chips.idClicked.connect(lambda _i: self._filtrar(self.buscar.text()))
        fila.addStretch(1)
        densidad = QtWidgets.QLabel(_tr("Densidad"))
        densidad.setProperty("rol", "t3")
        fila.addWidget(densidad)
        dens = QtWidgets.QFrame()
        dens.setObjectName("segmentado")
        dl = QtWidgets.QHBoxLayout(dens)
        dl.setContentsMargins(3, 3, 3, 3)
        self._grupo_dens = QtWidgets.QButtonGroup(dens)
        for i, clave in enumerate(("Compacta", "Cómoda")):
            b = QtWidgets.QPushButton(_tr(clave))
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setChecked(i == 1)
            self._grupo_dens.addButton(b, i)
            dl.addWidget(b)
        self._grupo_dens.idClicked.connect(lambda _i: self._densidad())
        fila.addWidget(dens)
        lay.addLayout(fila)
        self.pestanas = QtWidgets.QTabWidget()
        self.pestanas.tabBar().hide()
        self.pestanas.currentChanged.connect(self._pestana_cambiada)
        lay.addWidget(self.pestanas, 1)
        self.lbl_filas = QtWidgets.QLabel()
        self.lbl_filas.setProperty("rol", "t3")
        lay.addWidget(self.lbl_filas)
        self.tablas = []
        self.refrescar()

    def refrescar(self):
        """Arma las tablas. Con miles de filas tarda (AGUA 2: ~44 mil filas): barra de carga precisa
        (2026-10-20, `barras_carga`): los datos y la ventana avisan por bloques; mismo resultado."""
        from ui.ventana import barras_carga as BC
        w0 = self.win
        actual = self.pestanas.currentIndex()
        host = self if self.isVisible() else w0
        titulo = _tr("Armando la Tabla de datos…")
        w0._resultados_al_dia()                     # (calculo_fondo)
        with BC.tabla(host, len(w0.pipes)).abrir(titulo) as av:
            with av.escuchar():
                self.tablas = w0._tablas_de_datos() + [tabla_excel.tabla_vertices(w0.pipes, w0._to_cad)]
            av.costos_nuevos(BC.celdas_tabla(self.tablas))
            self.pestanas.clear()
            total = sum(len(tb.filas) for tb in self.tablas)
            hechas, vistas = 0, []
            av.recibir("celdas", 0, total, pump=True)
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
                    hechas += 1
                    if not hechas & 255:
                        av.recibir("celdas", hechas, total, pump=True)
                vistas.append((w, tb))
            pasos = (("ordenar", lambda w: (w.setSortingEnabled(True), w.sortByColumn(0, QtCore.Qt.AscendingOrder))),
                     ("columnas", lambda w: w.resizeColumnsToContents()))
            for paso, accion in pasos:
                hechas = 0
                for w, tb in vistas:
                    av.recibir(paso, hechas, total, pump=True)
                    accion(w)
                    hechas += len(tb.filas)
                av.recibir(paso, total, total, pump=True)
            for w, tb in vistas:
                w.cellDoubleClicked.connect(lambda row, _c, w=w, tb=tb: self._ir(w, tb, row))
                self.pestanas.addTab(w, f"{_tr(tb.titulo)} ({len(tb.filas)})")
        if 0 <= actual < self.pestanas.count():
            self.pestanas.setCurrentIndex(actual)
        self._armar_segmentado()
        self._marcar_editables()
        self._densidad()
        self._pestana_cambiada(self.pestanas.currentIndex())

    def _filtrar(self, texto):
        texto = (texto or "").strip().lower()
        chip = self._grupo_chips.checkedButton() if hasattr(self, "_grupo_chips") else None
        util = chip.property("valor") if chip is not None else ""
        for k in range(self.pestanas.count()):
            w = self.pestanas.widget(k)
            col_u = self._col_utilidad(k) if (util and k == self.pestanas.currentIndex()) else -1
            for r in range(w.rowCount()):
                ver = not texto or any(texto in (w.item(r, c).text().lower() if w.item(r, c) else "")
                                       for c in range(w.columnCount()))
                if ver and col_u >= 0:
                    it = w.item(r, col_u)
                    ver = (it.text() if it else "") == util
                w.setRowHidden(r, not ver)
        self._contar()

    # ── 2.0.0: pestañas segmentadas, filtro por utilidad, densidad y columnas editables ──
    def _armar_segmentado(self):
        lay = self._seg.layout()
        for b in list(self._grupo_seg.buttons()):
            self._grupo_seg.removeButton(b)
            b.hide()
            b.deleteLater()
        for i in range(self.pestanas.count()):
            b = QtWidgets.QPushButton(self.pestanas.tabText(i))
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setChecked(i == self.pestanas.currentIndex())
            self._grupo_seg.addButton(b, i)
            lay.addWidget(b, 1)

    def _col_utilidad(self, k):
        if not (0 <= k < len(self.tablas)):
            return -1
        cols = list(self.tablas[k].columnas)
        return cols.index("Utilidad") if "Utilidad" in cols else -1

    def _pestana_cambiada(self, k):
        if hasattr(self, "_grupo_seg") and self._grupo_seg.button(k) is not None:
            self._grupo_seg.button(k).setChecked(True)
        if not hasattr(self, "_grupo_chips"):
            return
        while self._chips.count():                          # fichas: las utilidades de ESTA tabla
            it = self._chips.takeAt(0)
            if it.widget() is not None:
                self._grupo_chips.removeButton(it.widget())
                it.widget().hide()
                it.widget().deleteLater()
        col = self._col_utilidad(k)
        if col >= 0:
            w = self.pestanas.widget(k)
            valores = sorted({w.item(r, col).text() for r in range(w.rowCount()) if w.item(r, col)} - {""})
            if 1 < len(valores) <= 8:
                for i, v in enumerate([""] + valores):
                    b = QtWidgets.QPushButton(v or _tr("Todas"))
                    b.setProperty("kind", "chip")
                    b.setProperty("valor", v)
                    b.setCheckable(True)
                    b.setChecked(i == 0)
                    self._grupo_chips.addButton(b, i)
                    self._chips.addWidget(b)
        self._filtrar(self.buscar.text())

    def _densidad(self):
        alto = 26 if self._grupo_dens.checkedId() == 0 else 34
        for k in range(self.pestanas.count()):
            self.pestanas.widget(k).verticalHeader().setDefaultSectionSize(alto)

    def _marcar_editables(self):
        """Columnas que se editan en el Excel: un punto verde en su encabezado (como el prototipo)."""
        from ui.comun import theme as _theme
        from ui.comun.icons import icon as _icon
        punto = _icon("mdi:circle-medium", color=_theme.tokens().success)
        for k, tb in enumerate(self.tablas[:self.pestanas.count()]):
            editables = tabla_excel.EDITABLES.get(tb.clave, {})
            w = self.pestanas.widget(k)
            w.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            for c, col in enumerate(tb.columnas):
                h = w.horizontalHeaderItem(c)
                if h is not None and col in editables:
                    h.setIcon(punto)
                    h.setToolTip(_tr("Las columnas verdes se pueden editar en Excel y volver a cargar"))

    def _contar(self):
        if not hasattr(self, "lbl_filas"):
            return
        w = self.pestanas.currentWidget()
        if w is None:
            self.lbl_filas.setText("")
            return
        n = sum(1 for r in range(w.rowCount()) if not w.isRowHidden(r))
        self.lbl_filas.setText(_tr("{n} filas · doble clic en una fila: ir al plano · clic en un encabezado: "
                                   "ordenar").format(n=n))

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
        from ui.ventana import barras_carga as BC
        try:
            titulo = _tr("Exportando a Excel…")
            # aquí mismo, avisando por bloques (en un hilo, openpyxl —Python puro— competía con los
            # repintados: 44 s en vez de 20 con AGUA 2)
            with BC.excel(self, self.tablas, tabla_excel.EDITABLES).abrir(titulo) as av, av.escuchar():
                tabla_excel.exportar(self.tablas, ruta)
        except Exception as e:                      # archivo abierto en Excel, sin permiso…
            QtWidgets.QMessageBox.warning(self, _tr("Exportar a Excel"), _tr(
                "No se pudo guardar el Excel (¿está abierto?).\n\n{e}").format(e=e))
            return
        self.win._info(_tr("Tabla de datos exportada: {ruta}").format(ruta=ruta))

    def importar(self, ruta=None, confirmar=True):
        """Carga un Excel editado: muestra los cambios, los aplica (con deshacer) y recalcula."""
        w = self.win
        if not ruta:
            ruta, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Importar Excel"), DOWNLOADS, _FILTRO_XLSX)
        if not ruta:
            return []
        try:
            con_db = {i for db in getattr(w, "duct_banks", []) or [] for i in db.assigned()}
            leido = tabla_excel.importar(ruta)
            ft = w.scale / w.zoom if w.scale and w.zoom else 0.0
            malas = tabla_excel.incoherencias(w.pipes, leido, ft)
            cambios, errores = tabla_excel.cambios(w.pipes, w.structures, leido,
                                                   catalogo=w._catalogo_excel(), con_bancoducto=con_db)
        except Exception as e:                      # no es un Excel de la app, está abierto…
            QtWidgets.QMessageBox.warning(self, _tr("Importar Excel"), _tr(
                "No se pudo leer el Excel.\n\n{e}").format(e=e))
            return []
        if malas:                                    # pendiente que no coincide con las cotas: no se importa
            lineas = malas[:10] + ([_tr("… y {n} más").format(n=len(malas) - 10)] if len(malas) > 10 else [])
            QtWidgets.QMessageBox.warning(self, _tr("Importar Excel"), _tr(
                "No se importó nada: estas pendientes no coinciden con las cotas de su utilidad. La pendiente se "
                "calcula con la rasante inicial, la final y el largo: si la cambias, cambia también una rasante "
                "(o deja la pendiente como estaba). Corrige el Excel y vuelve a importarlo.") + "\n\n• "
                + "\n• ".join(lineas))
            return []
        avisos = ("\n\n" + _tr("No se aplicaron:") + "\n• " + "\n• ".join(errores[:8])) if errores else ""
        if not cambios:
            QtWidgets.QMessageBox.information(self, _tr("Importar Excel"),
                                              _tr("El Excel no trae cambios respecto del proyecto.") + avisos)
            return []
        lineas = [tabla_excel.texto(c) for c in cambios[:15]]
        if len(cambios) > 15:
            lineas.append(_tr("… y {n} más").format(n=len(cambios) - 15))
        msg = (_tr("Se aplicarán {n} cambio(s):").format(n=len(cambios)) + "\n• " + "\n• ".join(lineas) + avisos
               + "\n\n" + _tr("Se puede deshacer con Ctrl+Z."))
        if confirmar and QtWidgets.QMessageBox.question(
                self, _tr("Importar Excel"), msg, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Yes) != QtWidgets.QMessageBox.Yes:
            return []
        antes = len(getattr(w, "_conflictos", []) or [])
        w._push()
        tabla_excel.aplicar(w.pipes, w.structures, cambios)
        w._refresh_lists(); w._update_ui(); w._redraw()
        self.refrescar()
        w._info(_tr("Excel importado: {n} cambio(s). Conflictos: {a} → {b}.").format(
            n=len(cambios), a=antes, b=len(getattr(w, "_conflictos", []) or [])))
        return cambios


def abrir(win):
    dlg = getattr(win, "_tabla_dlg", None)
    if dlg is None:
        dlg = TablaDatosDialog(win)
        win._tabla_dlg = dlg
        if hasattr(win, "incrustar_vista"):                  # 2.0.0: una vista dentro de la ventana
            win.incrustar_vista(dlg)
    else:
        dlg.refrescar()
    if not (hasattr(win, "mostrar_vista") and win.mostrar_vista(dlg)):
        dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg
