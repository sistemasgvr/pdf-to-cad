"""Ventana «Normativas de diseño» (formato de tablas del usuario, 2026-10-09).

Las normativas son UNA tabla de reglas + la de tipos (2026-10-21, `normas_reglas`; las mismas hojas del
Excel, `normas_excel`) que se EDITAN aquí mismo (`normas_tablas_view`: «la aplicación manda en todo»;
«Guardar cambios» las revisa y aplica), la lista de avisos del proyecto (clic = ir al lugar; se APRUEBAN con una nota y queda
el registro de quién y cuándo, `nucleo/normas_aprobacion`) y los botones para importar o
exportar el Excel (opcional: para compartirlas o editarlas en lote) y volver a los valores
iniciales. Los tipos nuevos que el usuario agrega con el «+» del panel ya están en el catálogo.
No modal: se refresca sola al redibujar el plano (las tablas, solo si no hay cambios sin guardar)."""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import normas_catalogo as nc
from nucleo import normas_excel
from nucleo import normas_tablas as NT
from nucleo.normas_validar import CLASES
from traduccion.i18n import t as _tr
from ui.comun.ui_common import DOWNLOADS
from ui.dialogos.normas_tablas_view import EditorTablas

_ROL = QtCore.Qt.UserRole
_FILTRO_XLSX = "Excel (*.xlsx)"              # filtro de archivo (igual en ambos idiomas)


class NormasDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Normativas de diseño"))
        self.resize(980, 600)
        self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 14)
        lay.setSpacing(12)
        # 2.0.0: cabecera (título + una línea) y las acciones del Excel arriba a la derecha (como el prototipo)
        fila = QtWidgets.QHBoxLayout()
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(2)
        titulo = QtWidgets.QLabel(_tr("Normativas de diseño"))
        titulo.setProperty("rol", "h1")
        tx.addWidget(titulo)
        cab = QtWidgets.QLabel(_tr("Edita las tablas aquí mismo (doble clic en una celda) y pulsa «Guardar "
                                   "cambios». Valen para todos tus proyectos. El Excel es opcional: para "
                                   "compartirlas o editarlas en lote."))
        cab.setWordWrap(True)
        cab.setProperty("rol", "t2")
        tx.addWidget(cab)
        fila.addLayout(tx, 1)
        self.btn_guardar = QtWidgets.QPushButton(_tr("Guardar cambios"))
        self.btn_guardar.setProperty("kind", "primary")
        self.btn_descartar = QtWidgets.QPushButton(_tr("Descartar cambios"))
        self.btn_descartar.setProperty("kind", "ghost")
        self.btn_guardar.clicked.connect(lambda: self.guardar())
        self.btn_descartar.clicked.connect(self.descartar)
        b_imp = QtWidgets.QPushButton(_tr("Importar Excel…"))
        b_exp = QtWidgets.QPushButton(_tr("Exportar Excel…"))
        b_base = QtWidgets.QPushButton(_tr("Volver a los valores iniciales"))
        b_base.setProperty("kind", "ghost")
        b_imp.clicked.connect(self.importar)
        b_exp.clicked.connect(self.exportar)
        b_base.clicked.connect(self.restaurar)
        for b in (b_imp, b_exp, b_base):
            b.setMinimumHeight(34)
            b.setAutoDefault(False)
            fila.addWidget(b, 0, QtCore.Qt.AlignTop)
        for b in (self.btn_guardar, self.btn_descartar):
            b.setMinimumHeight(34)
            b.setAutoDefault(False)
        lay.addLayout(fila)
        self._seg = QtWidgets.QFrame()
        self._seg.setObjectName("segmentado")
        self._seg.setMaximumWidth(520)
        sl = QtWidgets.QHBoxLayout(self._seg)
        sl.setContentsMargins(3, 3, 3, 3)
        self._grupo_seg = QtWidgets.QButtonGroup(self._seg)
        lay.addWidget(self._seg)
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
        self.tablas = EditorTablas(self)
        for pag, tabla in self.tablas.paginas:
            self.pestanas.addTab(pag, _tr(tabla.titulo))
        self.tablas.cambio.connect(self._botones_tablas)
        self.tablas.cargar(self.win.normas_cat)
        # «¿Qué significa esta regla?» con la IA (2026-10-23, `normas_ia_panel`): en el editor de la regla
        from ui.dialogos.normas_ia_panel import PanelExplicacion
        from ui.dialogos.normas_reglas_vista import VistaReglas
        for i, (pag, tabla) in enumerate(self.tablas.paginas, 1):
            if tabla.clave == "reglas":
                self.panel_ia = PanelExplicacion(self.win, self.tablas, pag)
                # 2.0.0: lista legible + editor lateral; la tabla de siempre es «Vista de tabla»
                self.pestanas.removeTab(i)
                self.vista_reglas = VistaReglas(self.tablas, pag, self.panel_ia)
                self.pestanas.insertTab(i, self.vista_reglas, _tr(tabla.titulo))
        # pestañas como control segmentado (Reglas · Tipos · Avisos); el QTabWidget sigue siendo el de siempre
        self.pestanas.tabBar().hide()
        for i in reversed(range(self.pestanas.count())):
            b = QtWidgets.QPushButton(self.pestanas.tabText(i))
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            self._grupo_seg.addButton(b, i)
            self._seg.layout().addWidget(b, 1)
        self._grupo_seg.idClicked.connect(self.pestanas.setCurrentIndex)
        self.pestanas.currentChanged.connect(lambda i: self._grupo_seg.button(i).setChecked(True))
        self._grupo_seg.button(self.pestanas.currentIndex()).setChecked(True)
        pie = QtWidgets.QHBoxLayout()
        self.lbl_pendientes = QtWidgets.QLabel()
        self.lbl_pendientes.setProperty("rol", "t3")
        pie.addWidget(self.lbl_pendientes, 1)
        pie.addWidget(self.btn_descartar)
        pie.addWidget(self.btn_guardar)
        lay.addLayout(pie)
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
                estado, marca = ((_tr("Información"), "ⓘ ") if a.info else
                                 (_tr("Error"), "⛔ ") if getattr(a, "nivel", "") == "ERROR" else (_tr("Pendiente"), "⚠ "))
            it = QtWidgets.QTreeWidgetItem([quien, marca + a.mensaje, estado])
            tip = _tr(CLASES.get(a.clase, a.clase)) + "\n" + a.mensaje
            if getattr(a, "fuente", ""):
                tip += "\n" + _tr("Fuente: {f}").format(f=a.fuente)
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
        if hasattr(self, "_grupo_seg") and self._grupo_seg.button(0) is not None:
            self._grupo_seg.button(0).setText(self.pestanas.tabText(0))
        cat = self.win.normas_cat
        if not self.tablas.sucio and any(NT.filas(cat, t.clave) != self.tablas.base().get(t.clave)
                                         for t in NT.TABLAS):
            self.tablas.cargar(cat)                      # cambió fuera (el «+» del panel): sin cambios propios
        self._botones_tablas()

    # ── edición de las tablas ──
    def _botones_tablas(self):
        sucio = self.tablas.sucio
        self.btn_guardar.setEnabled(sucio)
        self.btn_descartar.setEnabled(sucio)
        if hasattr(self, "lbl_pendientes"):
            self.lbl_pendientes.setText(_tr("Hay cambios sin guardar") if sucio else "")

    def guardar(self, avisar=True):
        """Revisa las tablas (las mismas reglas que el Excel) y, si todo se entiende, las aplica: se guardan
        para todos los proyectos y el plano se vuelve a revisar. Con problemas no aplica nada: los marca en
        rojo y los lista. Un tipo renombrado en «Tipos» se renombra también en las utilidades del proyecto."""
        cat, problemas = NT.catalogo(self.tablas.textos())
        if problemas:
            clave = self.tablas.marcar_problemas(problemas)
            for k, (_pag, tabla) in enumerate(self.tablas.paginas, 1):
                if tabla.clave == clave:
                    self.pestanas.setCurrentIndex(k)
            if clave == "reglas" and hasattr(self, "vista_reglas"):     # las celdas en rojo: en la tabla
                self.vista_reglas.btn_tabla.setChecked(True)
            if avisar:
                nombres = {t.clave: _tr(t.titulo) for t in NT.TABLAS}
                lineas = [_tr("{tabla}, fila {n}, {col}: {motivo}").format(
                    tabla=nombres.get(c, c), n=f + 1, col=col, motivo=m) for c, f, col, m in problemas]
                msg = _tr("No se guardó: corrige las celdas marcadas en rojo.") + "\n\n• " + "\n• ".join(lineas[:12])
                if len(lineas) > 12:
                    msg += "\n• " + _tr("… y {n} más").format(n=len(lineas) - 12)
                QtWidgets.QMessageBox.warning(self, _tr("Normativas de diseño"), msg)
            return False
        # tipos agregados con el «+» del panel mientras se editaba: se conservan
        viejos = {tuple(x) for x in self.tablas.base().get("tipos", [])}
        for u, tp in self.win.normas_cat.get("tipos", []):
            if (u, tp) not in viejos and (u, tp) not in {tuple(x) for x in cat["tipos"]}:
                cat["tipos"].append([u, tp])
        self._renombrar_en_proyecto(self.tablas.renombres)
        self.win._usar_normas(cat)
        self.tablas.cargar(self.win.normas_cat)
        if avisar:
            self.win._info(_tr("Normativas guardadas."))
        return True

    def _renombrar_en_proyecto(self, renombres):
        """Las utilidades del proyecto con un tipo renombrado pasan al nombre nuevo (se puede deshacer)."""
        pipes = getattr(self.win, "pipes", None) or []
        cambios = []
        for i, p in enumerate(pipes):
            tipo = nc.clave(p.get("tipo"))
            for u, viejo, nuevo in renombres:
                if tipo and nc.clave(p.get("layer")) == u and tipo == viejo:
                    tipo = nuevo
            if tipo != nc.clave(p.get("tipo")):
                cambios.append((i, tipo))
        if cambios:
            self.win._push()
            for i, tipo in cambios:
                pipes[i]["tipo"] = tipo
        return len(cambios)

    def descartar(self):
        self.tablas.cargar(self.win.normas_cat)

    def _sin_cambios_pendientes(self, titulo):
        """True si se puede seguir: sin cambios en las tablas, o el usuario los guardó o descartó."""
        if not self.tablas.sucio:
            return True
        r = QtWidgets.QMessageBox.question(
            self, titulo, _tr("Hay cambios sin guardar en las tablas de normativas. ¿Guardarlos?"),
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save)
        if r == QtWidgets.QMessageBox.Save:
            return self.guardar()
        if r == QtWidgets.QMessageBox.Discard:
            self.descartar()
            return True
        return False

    def closeEvent(self, e):
        if not self._sin_cambios_pendientes(_tr("Normativas de diseño")):
            e.ignore()
            return
        super().closeEvent(e)

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
        if not self._sin_cambios_pendientes(_tr("Importar Excel de normativas")):
            return
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
        msg = _tr("Normativas importadas: {t} tipos y {r} reglas.").format(t=len(cat["tipos"]), r=len(cat["reglas"]))
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
        if not self._sin_cambios_pendientes(_tr("Exportar Excel de normativas")):
            return
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
            self.tablas.cargar(self.win.normas_cat)


def abrir(win, en_avisos=False):
    dlg = getattr(win, "_normas_dlg", None)
    if dlg is None:
        dlg = NormasDialog(win)
        win._normas_dlg = dlg
        if hasattr(win, "incrustar_vista"):                  # 2.0.0: una vista dentro de la ventana
            win.incrustar_vista(dlg)
    dlg.refrescar()
    if en_avisos:
        dlg.pestanas.setCurrentIndex(0)
    if not (hasattr(win, "mostrar_vista") and win.mostrar_vista(dlg)):
        dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg
