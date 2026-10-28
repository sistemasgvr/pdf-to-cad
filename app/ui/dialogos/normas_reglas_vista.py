"""2.0.0 — Reglas de normativa como LISTA legible + EDITOR lateral (como el prototipo).

El dato sigue siendo la tabla de reglas de siempre (`EditorTablas.vistas["reglas"]`): la lista se arma con sus
filas (fila N de la lista = fila N de la tabla), el editor escribe en sus celdas (`setText` → la misma edición,
los mismos problemas en rojo, guardar y deshacer de siempre) y «Vista de tabla» muestra la tabla completa. Las
opciones de cada campo son las de la app (`normas_tablas.opciones`), igual que el desplegable de la tabla.
"""
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import normas_reglas as NR
from nucleo import normas_tablas as NT
from traduccion.i18n import t as _tr
from ui.comun import rediseno as R
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon
from ui.comun.ui_common import layer_qcolor

_K = {c: i for i, c in enumerate(NR.COLUMNAS)}
# campos del editor, agrupados como en el prototipo (cuándo aplica · qué revisa · si no se cumple)
GRUPOS = [("Cuándo aplica", ("ACTIVA", "UTILIDAD", "TIPO", "ELEMENTO", "SI DIAMETRO MIN (in)", "SI DIAMETRO MAX (in)",
                             "SI AMPERAJE MIN (A)", "SI AMPERAJE MAX (A)", "SI LARGO MIN (ft)", "SI LARGO MAX (ft)",
                             "SI MATERIAL")),
          ("Qué revisa", ("REVISAR", "MIN", "MAX", "VALORES", "CON UTILIDAD", "CON TIPO")),
          ("Si no se cumple", ("NIVEL", "FUENTE", "NOTA"))]


class _Delegado(QtWidgets.QStyledItemDelegate):
    """Fila de la lista: punto de la utilidad · la regla como frase / utilidad · tipo · elemento · nivel."""

    def __init__(self, vista):
        super().__init__(vista.lista)
        self.vista = vista

    def sizeHint(self, option, index):                 # noqa: N802
        return QtCore.QSize(option.rect.width(), 54)

    def paint(self, p, option, index):
        t = _theme.tokens()
        fila = self.vista.fila(index.row())
        r = option.rect.adjusted(2, 1, -2, -1)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if option.state & QtWidgets.QStyle.State_Selected:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(t.soft))
            p.drawRoundedRect(QtCore.QRectF(r), 8, 8)
        elif option.state & QtWidgets.QStyle.State_MouseOver:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(t.hover))
            p.drawRoundedRect(QtCore.QRectF(r), 8, 8)
        util = fila[_K["UTILIDAD"]]
        activa = fila[_K["ACTIVA"]] != NR.NO
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(layer_qcolor(util) if util else QtGui.QColor(t.text3))
        p.drawEllipse(QtCore.QPointF(r.left() + 14, r.center().y()), 5, 5)
        nivel = fila[_K["NIVEL"]] or ""
        color_n = {"ERROR": (t.danger_soft, t.danger), "AVISO": (t.warning_soft, t.warning)}.get(
            nivel.upper(), (t.soft, t.soft_text))
        f3 = QtGui.QFont(option.font)
        f3.setPixelSize(11)
        f3.setWeight(QtGui.QFont.DemiBold)
        ancho_n = QtGui.QFontMetrics(f3).horizontalAdvance(nivel) + 16 if nivel else 0
        x, derecha = r.left() + 30, r.right() - 10 - ancho_n
        if nivel:
            caja = QtCore.QRectF(r.right() - 8 - ancho_n, r.center().y() - 10, ancho_n, 20)
            p.setBrush(QtGui.QColor(color_n[0]))
            p.drawRoundedRect(caja, 9, 9)
            p.setFont(f3)
            p.setPen(QtGui.QColor(color_n[1]))
            p.drawText(caja, QtCore.Qt.AlignCenter, nivel)
        f = QtGui.QFont(option.font)
        f.setWeight(QtGui.QFont.DemiBold)
        p.setFont(f)
        p.setPen(QtGui.QColor(t.text if activa else t.text3))
        frase = NT.frase(fila) or _tr("(regla vacía)")
        if frase.startswith(_tr("En {donde}, {elemento}").split("{")[0]) and ": " in frase:      # «En AGUA · TIPO, Tubería: …» → lo que revisa
            frase = frase.split(": ", 1)[1]
        frase = " ".join(frase.split())                  # una nota con saltos de línea, en una sola línea
        arriba = QtCore.QRectF(x, r.top() + 6, derecha - x, r.height() / 2 - 4)
        p.drawText(arriba, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   QtGui.QFontMetrics(f).elidedText(frase, QtCore.Qt.ElideRight, int(arriba.width())))
        f2 = QtGui.QFont(option.font)
        f2.setPixelSize(12)
        p.setFont(f2)
        p.setPen(QtGui.QColor(t.text3))
        det = " · ".join(v for v in (util, fila[_K["TIPO"]], fila[_K["ELEMENTO"]],
                                     "" if activa else _tr("Desactivada")) if v)
        abajo = QtCore.QRectF(x, r.center().y() + 1, derecha - x, r.height() / 2 - 5)
        p.drawText(abajo, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   QtGui.QFontMetrics(f2).elidedText(det, QtCore.Qt.ElideRight, int(abajo.width())))
        p.restore()


class VistaReglas(QtWidgets.QWidget):
    """Lista + editor; `pag_tabla` (la página de siempre) es la «Vista de tabla»."""

    def __init__(self, editor, pag_tabla, panel_ia=None):
        super().__init__()
        self.editor = editor
        self.tabla = editor.vistas["reglas"]
        self.pag_tabla = pag_tabla
        R.transparente(self)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        arriba = QtWidgets.QHBoxLayout()
        self.buscar = R.CampoBuscar("Buscar una regla…")
        self.buscar.textChanged.connect(lambda _t: self._filtrar())
        arriba.addWidget(self.buscar, 1)
        if editor.filtro is not None:
            arriba.addWidget(editor.filtro)            # el filtro por utilidad de siempre
            editor.filtro.currentIndexChanged.connect(lambda _i: self._filtrar())
        self.btn_tabla = QtWidgets.QPushButton(_tr("Vista de tabla"))
        self.btn_tabla.setIcon(_icon("mdi:table-large"))
        self.btn_tabla.setProperty("kind", "ghost")
        self.btn_tabla.setCheckable(True)
        self.btn_tabla.toggled.connect(self._vista_tabla)
        arriba.addWidget(self.btn_tabla)
        nueva = QtWidgets.QPushButton(_tr("Nueva regla"))
        nueva.setIcon(_icon("mdi:plus"))
        nueva.setProperty("soft", True)
        nueva.clicked.connect(self._nueva)
        arriba.addWidget(nueva)
        lay.addLayout(arriba)
        self.pila = QtWidgets.QStackedWidget()
        cuerpo = R.transparente(QtWidgets.QWidget())
        cl = QtWidgets.QHBoxLayout(cuerpo)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(16)
        self.lista = QtWidgets.QListWidget()
        self.lista.setObjectName("listaReglas")
        self.lista.setMouseTracking(True)
        self.lista.setUniformItemSizes(True)
        self.lista.setItemDelegate(_Delegado(self))
        self.lista.currentRowChanged.connect(self._elegir)
        cl.addWidget(self.lista, 3)
        self.tarjeta = QtWidgets.QFrame()
        self.tarjeta.setObjectName("tarjeta")
        tl = QtWidgets.QVBoxLayout(self.tarjeta)
        tl.setContentsMargins(16, 14, 16, 12)
        cab = QtWidgets.QHBoxLayout()
        cab.addWidget(R.texto("Editar regla", "h2"), 1)
        quitar = R.boton_icono("trash-can-outline", "Quitar filas", self._quitar)
        cab.addWidget(quitar)
        tl.addLayout(cab)
        form_w = R.transparente(QtWidgets.QWidget())
        self.form = QtWidgets.QVBoxLayout(form_w)
        self.form.setContentsMargins(0, 0, 4, 0)
        self.form.setSpacing(6)
        self.campos = {}
        for titulo, cols in GRUPOS:
            self.form.addWidget(R.seccion(titulo))
            for col in cols:
                self.campos[col] = self._campo(col)
        self.form.addStretch(1)
        tl.addWidget(R.AreaVertical(form_w), 1)
        if panel_ia is not None:
            tl.addWidget(panel_ia)
        cl.addWidget(self.tarjeta, 2)
        self.pila.addWidget(cuerpo)
        self.pila.addWidget(pag_tabla)
        lay.addWidget(self.pila, 1)
        self._poniendo = False
        editor.cambio.connect(self.recargar)
        self.recargar()

    # ── datos (siempre de la tabla) ──
    def fila(self, r):
        return self.editor.fila_de("reglas", r) if 0 <= r < self.tabla.rowCount() else [""] * len(NR.COLUMNAS)

    def recargar(self):
        """Rearma la lista con las filas de la tabla (mismo orden) y el editor de la regla elegida."""
        actual = self.tabla.currentRow()
        self.lista.blockSignals(True)
        if self.lista.count() != self.tabla.rowCount():
            self.lista.clear()
            for _r in range(self.tabla.rowCount()):
                self.lista.addItem(QtWidgets.QListWidgetItem())
        for r in range(self.lista.count()):
            self.lista.item(r).setToolTip(NT.frase(self.fila(r)))
        if actual < 0 and self.lista.count():
            actual = 0
        self.lista.setCurrentRow(actual)
        self.lista.blockSignals(False)
        self._filtrar()
        self.lista.viewport().update()
        self._poner_editor(actual)

    def _filtrar(self):
        q = self.buscar.text().strip().lower()
        for r in range(self.lista.count()):
            oculto = self.tabla.isRowHidden(r) or (bool(q) and q not in " ".join(self.fila(r)).lower()
                                                     and q not in NT.frase(self.fila(r)).lower())
            self.lista.item(r).setHidden(oculto)

    def _elegir(self, r):
        if r >= 0:
            self.tabla.setCurrentCell(r, max(0, self.tabla.currentColumn()))
        self._poner_editor(r)

    # ── editor ──
    def _campo(self, col):
        w = R.transparente(QtWidgets.QWidget())
        f = QtWidgets.QHBoxLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        lbl = QtWidgets.QLabel(col.capitalize())
        lbl.setProperty("rol", "t2")
        lbl.setFixedWidth(150)
        lbl.setWordWrap(True)
        f.addWidget(lbl)
        combo = QtWidgets.QComboBox()
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        texto = QtWidgets.QLineEdit()
        combo.currentTextChanged.connect(lambda v, c=col: self._escribir(c, v))
        texto.editingFinished.connect(lambda c=col, e=texto: self._escribir(c, e.text()))
        f.addWidget(combo, 1)
        f.addWidget(texto, 1)
        self.form.addWidget(w)
        return combo, texto

    def _poner_editor(self, r):
        self.tarjeta.setEnabled(0 <= r < self.tabla.rowCount())
        fila = self.fila(r)
        tipos = self.editor.textos_de("tipos")
        self._poniendo = True
        try:
            for col, (combo, texto) in self.campos.items():
                valor = fila[_K[col]]
                ops = NT.opciones(col, fila, tipos)
                combo.setVisible(ops is not None)
                texto.setVisible(ops is None)
                if ops is None:
                    texto.setText(valor)
                    continue
                combo.blockSignals(True)
                combo.clear()
                vals = [v for v, _a in ops]
                if valor and valor not in vals:
                    vals.append(valor)                 # lo que haya escrito (p. ej. «a;b»), tal cual
                combo.addItems(vals)
                combo.setCurrentIndex(max(0, vals.index(valor)) if valor in vals else 0)
                combo.blockSignals(False)
        finally:
            self._poniendo = False

    def _escribir(self, col, valor):
        r = self.tabla.currentRow()
        if self._poniendo or not (0 <= r < self.tabla.rowCount()):
            return
        it = self.tabla.item(r, _K[col])
        if it is None or it.text() == valor:
            return
        it.setText(valor)                              # la edición de siempre (sucio, frase, rojo…)
        self.lista.viewport().update()
        self._poner_editor(r)                          # las opciones dependen del resto de la fila

    def _nueva(self):
        if self.btn_tabla.isChecked():
            self.btn_tabla.setChecked(False)
        r = self.editor.agregar_fila("reglas")
        self.recargar()
        self.lista.setCurrentRow(r)

    def _quitar(self):
        self.editor.quitar_filas("reglas")
        self.recargar()

    def _vista_tabla(self, on):
        self.pila.setCurrentIndex(1 if on else 0)
        if not on:
            self.recargar()
