"""Editor de las normativas dentro de la aplicación (pedidos del usuario 2026-10-20: «que todo sea editable
desde la aplicación… la aplicación manda en todo», y 2026-10-21: una sola tabla de reglas).

Dos pestañas, las hojas del Excel: Tipos (ahí se crean, con texto libre) y Reglas (`normas_reglas`), cada una con
«Agregar fila» / «Quitar filas»; Reglas además con un filtro por utilidad. Donde la app decide los valores hay
un DESPLEGABLE que depende del resto de la fila (`normas_tablas.opciones`): TIPO = los de su utilidad, ELEMENTO =
los que existen en esa utilidad, REVISAR = lo que se mide de ese elemento, VALORES = SI/NO, tipos o materiales
según REVISAR (admite varios con «;»)… El globo de cada fila es la regla leída como frase. Renombrar un tipo en
Tipos lo renombra en las reglas (`renombrar_tipo`). Nada se aplica hasta «Guardar cambios» de la ventana
(`NormasDialog`), que revisa todo con las reglas del Excel y marca en rojo las celdas con problemas.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import model
from nucleo import normas_catalogo as nc
from nucleo import normas_excel_ayuda as ayuda
from nucleo import normas_reglas as NR
from nucleo import normas_tablas as NT
from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon

_ROL_ANTES = QtCore.Qt.UserRole + 7          # valor de la celda al cargar/editar (renombrar tipos)
_NOMBRE_UTIL = dict((c, n) for n, c in model.TIPOS)
_ROJO = QtGui.QColor(220, 60, 60, 90)
_LIBRES = ("VALORES", "SI MATERIAL")         # desplegable que también deja escribir varios con «;»


class _Delegado(QtWidgets.QStyledItemDelegate):
    """Desplegable en las columnas cuyo valor decide la app; texto en las demás."""

    def __init__(self, editor, tabla):
        super().__init__(editor)
        self.editor, self.tabla = editor, tabla

    def _opciones(self, index):
        col = self.tabla.columnas[index.column()]
        if self.tabla.clave == "tipos":
            return [(c, _NOMBRE_UTIL.get(c, c)) for c in nc.UTILIDADES] if col == "UTILIDAD" else None
        fila = self.editor.fila_de("reglas", index.row())
        ops = NT.opciones(col, fila, self.editor.textos_de("tipos"))
        if ops and col == "UTILIDAD":
            ops = [(c, _NOMBRE_UTIL.get(c, c)) for c, _a in ops]
        return ops

    def createEditor(self, parent, option, index):
        ops = self._opciones(index)
        if ops is None:
            return super().createEditor(parent, option, index)
        cb = QtWidgets.QComboBox(parent)
        cb.setEditable(self.tabla.columnas[index.column()] in _LIBRES)
        for valor, ayuda_txt in ops:
            cb.addItem(valor, valor)
            if ayuda_txt and ayuda_txt != valor:
                cb.setItemData(cb.count() - 1, ayuda_txt, QtCore.Qt.ToolTipRole)
        return cb

    def setEditorData(self, ed, index):
        if isinstance(ed, QtWidgets.QComboBox):
            v = nc.clave(index.data() or "")
            k = next((i for i in range(ed.count()) if nc.clave(ed.itemData(i)) == v), -1)
            if k < 0 and index.data():
                if ed.isEditable():
                    ed.setEditText(index.data())
                    return
                ed.addItem(index.data(), index.data())          # valor que ya no existe: se ve igual
                k = ed.count() - 1
            ed.setCurrentIndex(max(k, 0))
            return
        super().setEditorData(ed, index)

    def setModelData(self, ed, model_, index):
        if isinstance(ed, QtWidgets.QComboBox):
            valor = ed.currentText().strip() if ed.isEditable() else ed.currentData()
            model_.setData(index, valor or "")
            return
        super().setModelData(ed, model_, index)


class EditorTablas(QtCore.QObject):
    """Las tablas editables (páginas para el QTabWidget de la ventana)."""
    cambio = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sucio = False
        self.renombres = []                  # [(utilidad, viejo, nuevo)] hechos en la pestaña Tipos
        self.vistas, self.paginas = {}, []
        self._base = None
        self._cargando = False
        self.filtro = None
        for tabla in NT.TABLAS:
            pag = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(pag)
            barra = QtWidgets.QHBoxLayout()
            b_mas = QtWidgets.QPushButton(_icon("mdi:plus"), _tr("Agregar fila"))
            b_menos = QtWidgets.QPushButton(_icon("mdi:trash-can-outline"), _tr("Quitar filas"))
            b_menos.setProperty("secondary", True)
            for b in (b_mas, b_menos):
                b.setMinimumHeight(30); b.setAutoDefault(False)
                barra.addWidget(b)
            if tabla.clave == "reglas":
                self.filtro = QtWidgets.QComboBox()
                self.filtro.addItem(_tr("Todas las utilidades"), "")
                for c in nc.UTILIDADES:
                    self.filtro.addItem(_NOMBRE_UTIL.get(c, c), c)
                self.filtro.currentIndexChanged.connect(lambda _i: self._filtrar())
                barra.addWidget(self.filtro)
            pista = QtWidgets.QLabel(_tr("Doble clic en una celda para cambiarla. Pasa el mouse por el título de "
                                         "cada columna para ver qué va ahí, y por una fila para leerla como frase."))
            pista.setObjectName("hint"); pista.setWordWrap(True)
            barra.addWidget(pista, 1)
            lay.addLayout(barra)
            w = QtWidgets.QTableWidget(0, len(tabla.columnas))
            w.setHorizontalHeaderLabels(list(tabla.columnas))      # como en el Excel (es el formato de datos)
            for k, col in enumerate(tabla.columnas):
                tip = ayuda.comentario(tabla.hoja, col)
                if tip:
                    w.horizontalHeaderItem(k).setToolTip(tip)
            w.verticalHeader().setVisible(False)
            w.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            w.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed
                              | QtWidgets.QAbstractItemView.AnyKeyPressed)
            w.setItemDelegate(_Delegado(self, tabla))
            w.itemChanged.connect(lambda it, t=tabla: self._editado(t, it))
            lay.addWidget(w, 1)
            b_mas.clicked.connect(lambda _c=False, t=tabla: self.agregar_fila(t.clave))
            b_menos.clicked.connect(lambda _c=False, t=tabla: self.quitar_filas(t.clave))
            self.vistas[tabla.clave] = w
            self.paginas.append((pag, tabla))

    # ── datos ──
    def cargar(self, cat):
        """Pone el catálogo en las tablas y queda «sin cambios»."""
        self._cargando = True
        try:
            for tabla in NT.TABLAS:
                self._poner(tabla.clave, NT.filas(cat, tabla.clave))
        finally:
            self._cargando = False
        self._base = {t.clave: NT.filas(cat, t.clave) for t in NT.TABLAS}
        self.renombres = []
        self._marcar_sucio(False)

    def base(self):
        return self._base or {}

    def _poner(self, clave, filas):
        w = self.vistas[clave]
        w.blockSignals(True)
        w.setRowCount(len(filas))
        for r, fila in enumerate(filas):
            for c, v in enumerate(fila):
                it = QtWidgets.QTableWidgetItem(str(v))
                it.setData(_ROL_ANTES, str(v))
                w.setItem(r, c, it)
        w.blockSignals(False)
        for r in range(len(filas)):
            self._frase(clave, r)
        w.resizeColumnsToContents()
        for c in range(w.columnCount()):
            w.setColumnWidth(c, min(w.columnWidth(c), 320))
        self._filtrar()

    def fila_de(self, clave, r):
        w = self.vistas[clave]
        return [(w.item(r, c).text() if w.item(r, c) else "") for c in range(w.columnCount())]

    def textos_de(self, clave):
        return [self.fila_de(clave, r) for r in range(self.vistas[clave].rowCount())]

    def textos(self):
        return {t.clave: self.textos_de(t.clave) for t in NT.TABLAS}

    def _frase(self, clave, r):
        if clave != "reglas":
            return
        w = self.vistas[clave]
        txt = NT.frase(self.fila_de(clave, r))
        w.blockSignals(True)
        for c in range(w.columnCount()):
            it = w.item(r, c)
            if it is not None and not it.data(QtCore.Qt.UserRole + 8):      # (las celdas en rojo dicen su motivo)
                it.setToolTip(txt)
        w.blockSignals(False)

    def _filtrar(self):
        if self.filtro is None or "reglas" not in self.vistas:
            return
        u = self.filtro.currentData() or ""
        w = self.vistas["reglas"]
        k = NR.COLUMNAS.index("UTILIDAD")
        for r in range(w.rowCount()):
            it = w.item(r, k)
            w.setRowHidden(r, bool(u) and (it.text() if it else "") != u)

    # ── edición ──
    def _marcar_sucio(self, on=True):
        self.sucio = bool(on)
        self.cambio.emit()

    def _editado(self, tabla, it):
        if self._cargando:
            return
        antes, ahora = it.data(_ROL_ANTES), it.text()
        if tabla.clave == "tipos" and it.column() == 1 and antes and nc.clave(antes) != nc.clave(ahora):
            util = self.vistas["tipos"].item(it.row(), 0)
            util = util.text() if util else ""
            textos = self.textos()
            if nc.clave(ahora) and NT.renombrar_tipo(textos, util, antes, ahora):
                self._cargando = True
                try:
                    self._poner("reglas", textos["reglas"])
                finally:
                    self._cargando = False
            if nc.clave(ahora):
                self.renombres.append((nc.clave(util), nc.clave(antes), nc.clave(ahora)))
        w = self.vistas[tabla.clave]
        w.blockSignals(True)
        it.setData(_ROL_ANTES, ahora)
        it.setData(QtCore.Qt.UserRole + 8, None)
        it.setBackground(QtGui.QBrush())
        it.setToolTip("")
        w.blockSignals(False)
        self._frase(tabla.clave, it.row())
        self._marcar_sucio()

    def agregar_fila(self, clave):
        """Fila nueva con la utilidad de la fila elegida (o la del filtro, o la primera de la app)."""
        w = self.vistas[clave]
        sel = w.currentRow()
        k_u = 0 if clave == "tipos" else NR.COLUMNAS.index("UTILIDAD")
        util = ((w.item(sel, k_u).text() if sel >= 0 and w.item(sel, k_u) else "")
                or (self.filtro.currentData() if clave == "reglas" and self.filtro else "") or nc.UTILIDADES[0])
        r = sel + 1 if sel >= 0 else w.rowCount()
        if clave == "tipos":
            valores = [util, ""]
        else:
            valores = NR.fila_de(NR.regla_vacia(utilidad=util))
        w.blockSignals(True)
        w.insertRow(r)
        for c, v in enumerate(valores):
            it = QtWidgets.QTableWidgetItem(v)
            it.setData(_ROL_ANTES, v)
            w.setItem(r, c, it)
        w.blockSignals(False)
        col = 1 if clave == "tipos" else NR.COLUMNAS.index("TIPO")
        w.setCurrentCell(r, col)
        w.editItem(w.item(r, col))
        self._marcar_sucio()
        return r

    def quitar_filas(self, clave):
        w = self.vistas[clave]
        filas = sorted({i.row() for i in w.selectedIndexes()} or ({w.currentRow()} - {-1}), reverse=True)
        for r in filas:
            w.removeRow(r)
        if filas:
            self._marcar_sucio()
        return len(filas)

    def marcar_problemas(self, problemas):
        """Celdas con problema en rojo, con el motivo en su globo. Devuelve la pestaña del primero."""
        primera = None
        for clave, fila, col, motivo in problemas:
            tabla = next((t for t in NT.TABLAS if t.clave == clave), None)
            if tabla is None or fila < 0:
                continue
            w = self.vistas[clave]
            c = tabla.columnas.index(col) if col in tabla.columnas else 0
            it = w.item(fila, c)
            if it is None:
                continue
            w.blockSignals(True)
            it.setBackground(QtGui.QBrush(_ROJO))
            it.setToolTip(motivo)
            it.setData(QtCore.Qt.UserRole + 8, True)
            w.blockSignals(False)
            if primera is None:
                primera = clave
                if self.filtro is not None and clave == "reglas" and w.isRowHidden(fila):
                    self.filtro.setCurrentIndex(0)
                w.clearSelection()                   # seleccionada, el rojo no se vería
                w.scrollToItem(it)
        return primera
