"""Panel «Editar» de la Vista 3D: diámetro y cotas por tramo de la utilidad elegida (pedido del usuario
2026-10-20: «que sea más interactivo y dinámico… y que se actualice en la vista 2D también»).

Una fila por tramo (T1, T2… como en el plano) con la cota de inicio y de fin y su pendiente. Se escribe la
cota o ↑ ↓ del teclado la cambian 0.10 ft. Cada cambio se VE al instante en la 3D (`parche_local` de la
ventana: solo esa utilidad, sus vecinas y sus accesorios, ~0.2 s con 16 761 utilidades) y la pendiente en la
tabla; el cambio REAL (un paso de deshacer, el plano y el armado completo de la 3D en otro proceso) se aplica
al dejar de tocar (`ESPERA_MS`) o con Enter. Clic en una fila = ese tramo resaltado en el plano. Los datos y las reglas son los del panel
del plano (`ui/ventana/ventana_edicion3d.py`)."""
from __future__ import annotations

import copy

from PySide6 import QtCore, QtWidgets

from nucleo import edicion3d
from traduccion.i18n import t as _tr

ESPERA_MS = 800
PASO_FT = 0.1


class _Cota(QtWidgets.QDoubleSpinBox):
    def __init__(self, tramo, lado):
        super().__init__()
        self.tramo, self.lado = tramo, lado
        self.setRange(-100000.0, 100000.0)
        self.setDecimals(3)
        self.setSingleStep(PASO_FT)
        self.setKeyboardTracking(False)           # al escribir, se aplica con Enter o al salir
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)   # sin + / − (pedido 2026-10-20): ↑ ↓ del teclado
        self.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        # Se encoge con el panel (el rango ±100 000 le daría el ancho de «-100000.000» y cortaba la tabla).
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)


class EditorUtilidad(QtWidgets.QGroupBox):
    def __init__(self, win, parent=None, vista=None):
        super().__init__(_tr("Editar"), parent)
        self.win = win
        self.vista = vista                        # la ventana 3D (vista previa con `parche_local`)
        self.i = -1
        self._pend = {}                           # (tramo, lado) → valor por aplicar
        self._largos = []
        self._cargando = False
        v = QtWidgets.QVBoxLayout(self)
        f = QtWidgets.QFormLayout()
        self.cmb_diam = QtWidgets.QComboBox()
        self.cmb_diam.currentIndexChanged.connect(self._diametro)
        self.cmb_diam.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_diam.setMinimumContentsLength(6)          # no ensancha el panel con el texto más largo
        f.addRow(_tr("Diámetro:"), self.cmb_diam)
        v.addLayout(f)
        self.tabla = QtWidgets.QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels([_tr("Tramo"), _tr("Inicio (ft)"), _tr("Fin (ft)"), _tr("Pendiente")])
        self.tabla.verticalHeader().setVisible(False)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        for c in (1, 2):
            h.setSectionResizeMode(c, QtWidgets.QHeaderView.Stretch)
        h.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.tabla.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabla.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tabla.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.tabla.currentCellChanged.connect(lambda r, _c, _r0, _c0: self._resaltar(r))
        v.addWidget(self.tabla)
        self.lbl_pista = QtWidgets.QLabel(_tr("Escribe la cota o usa ↑ ↓ del teclado (±0.10 ft). Se aplica al "
                                              "instante en el plano y en 3D (Ctrl+Z lo deshace)."))
        self.lbl_pista.setWordWrap(True)
        self.lbl_pista.setObjectName("hint")
        v.addWidget(self.lbl_pista)
        self._t = QtCore.QTimer(self, singleShot=True, interval=ESPERA_MS, timeout=self.aplicar)
        self._t_previa = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self._previa)
        self.setVisible(False)

    # ── cargar ──
    def cargar(self, i):
        """Muestra la utilidad `i` (-1 = ninguna). Con la misma utilidad y un campo en uso, solo pone al día
        los demás (no se pisa lo que se está escribiendo)."""
        w = self.win
        if not (0 <= i < len(w.pipes)) or len(w.pipes[i].get("pts") or []) < 2:
            self.aplicar()                        # lo que quedó a medio aplicar no se pierde
            self.i = -1
            self.setVisible(False)
            return
        misma = i == self.i
        if not misma:
            self.aplicar()
        self.i = i
        cotas = w.cotas_para_3d(i)
        self._largos = [L for _a, _b, L in cotas]
        self._cargando = True
        try:
            if not misma or self.tabla.rowCount() != len(cotas):
                self._armar_tabla(cotas)
            else:
                enfoco = QtWidgets.QApplication.focusWidget()
                for r, (z0, z1, _L) in enumerate(cotas):
                    for c, z in ((1, z0), (2, z1)):
                        sp = self.tabla.cellWidget(r, c)
                        en_uso = enfoco is not None and (enfoco is sp or sp.isAncestorOf(enfoco))
                        if not en_uso and (r, sp.lado) not in self._pend:
                            sp.setValue(z)
                    self._pendiente_de(r)
            self._cargar_diametro(i)
        finally:
            self._cargando = False
        self.setVisible(True)

    def _armar_tabla(self, cotas):
        n = len(cotas)
        self.tabla.setRowCount(n)
        for r, (z0, z1, L) in enumerate(cotas):
            it = QtWidgets.QTableWidgetItem(f"T{r + 1}")
            it.setTextAlignment(QtCore.Qt.AlignCenter)
            it.setToolTip(_tr("Tramo {t}: {largo} ft en planta").format(t=r + 1, largo=f"{L:.2f}"))
            self.tabla.setItem(r, 0, it)
            for c, lado, z in ((1, "inicio", z0), (2, "fin", z1)):
                sp = _Cota(r, lado)
                sp.setValue(z)
                if (r == 0 and lado == "inicio") or (r == n - 1 and lado == "fin"):
                    f = sp.font(); f.setBold(True); sp.setFont(f)
                    sp.setToolTip(_tr("Rasante inicial") if lado == "inicio" else _tr("Rasante final"))
                sp.valueChanged.connect(lambda val, s=sp: self._cambio(s, val))
                sp.editingFinished.connect(self.aplicar)
                self.tabla.setCellWidget(r, c, sp)
            pe = QtWidgets.QTableWidgetItem()
            pe.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.tabla.setItem(r, 3, pe)
            self._pendiente_de(r)
        self.tabla.resizeRowsToContents()
        alto = self.tabla.horizontalHeader().height() + sum(self.tabla.rowHeight(r) for r in range(n)) + 4
        self.tabla.setFixedHeight(min(max(alto, 60), 320))

    def _cargar_diametro(self, i):
        ops, actual, usable = self.win.opciones_diametro_3d(i)
        cb = self.cmb_diam
        cb.blockSignals(True)
        cb.clear()
        for texto, dato in ops:
            cb.addItem(texto, dato)
        cb.setCurrentIndex(actual)
        cb.setEnabled(usable and cb.count() > 1)
        cb.setToolTip("" if cb.isEnabled() else _tr("El diámetro de esta utilidad no se cambia aquí "
                                                   "(lo define su bancoducto o su familia de catálogo)."))
        cb.blockSignals(False)

    # ── editar ──
    def _pendiente_de(self, r):
        it = self.tabla.item(r, 3)
        if it is None or r >= len(self._largos):
            return
        z0 = self.tabla.cellWidget(r, 1).value()
        z1 = self.tabla.cellWidget(r, 2).value()
        L = self._largos[r]
        it.setText(f"{(z1 - z0) / L * 100.0:.2f} %" if L > 1e-9 else "—")

    def _cambio(self, sp, valor):
        if self._cargando:
            return
        self._pend[(sp.tramo, sp.lado)] = float(valor)
        self._pendiente_de(sp.tramo)
        self._t_previa.start()                     # se junta con otros cambios del mismo instante
        self._t.start()

    def _previa(self, diametro=None):
        """La 3D con lo que se está editando, YA (una copia de la utilidad; el proyecto aún no cambia)."""
        if self.vista is None or not (0 <= self.i < len(self.win.pipes)):
            return False
        p = copy.deepcopy(self.win.pipes[self.i])
        for (tramo, lado), valor in self._pend.items():
            edicion3d.aplicar_cota(p, tramo, lado, valor)
        if diametro is not None:
            edicion3d.aplicar_diametro(p, diametro)
        return self.vista.parche_local({self.i: p})

    def aplicar(self):
        """Lleva al modelo lo que se cambió (UN paso de deshacer). Devuelve cuántas cotas había."""
        self._t.stop()
        pend, self._pend = self._pend, {}
        if not pend or not (0 <= self.i < len(self.win.pipes)):
            return 0
        if self._t_previa.isActive():               # Enter enseguida: que la 3D muestre lo mismo que se aplica
            self._t_previa.stop()
            self._pend = pend
            self._previa()
            self._pend = {}
        self.win.editar_cotas_3d(self.i, [(t, lado, v) for (t, lado), v in pend.items()])
        return len(pend)

    def _diametro(self, k):
        if self._cargando or not (0 <= self.i < len(self.win.pipes)):
            return
        self.aplicar()
        dato = self.cmb_diam.itemData(k)
        self._previa(diametro=dato)                 # la 3D al instante; el cambio real, tras pintarla
        i = self.i
        QtCore.QTimer.singleShot(30, lambda: self._aplicar_diametro(i, dato))

    def _aplicar_diametro(self, i, dato):
        if i != self.i or not (0 <= i < len(self.win.pipes)):
            return
        self.win.editar_diametro_3d(i, dato)
        self._cargar_diametro(i)

    def _resaltar(self, r):
        w = self.win
        if r >= 0 and w.sel_pipe == self.i and 0 <= self.i < len(w.pipes):
            w._select_segment(r, refocus=False)
