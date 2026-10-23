"""IA → «Configurar IA…» (pedido del usuario 2026-10-23): quién responde (sin IA = plantillas, servidor propio con
Ollama; Claude después), la dirección del servidor, el modelo (se buscan los instalados) y cuántos pedidos a la vez
al redactar el informe. «Probar» pregunta algo corto y dice cuánto tardó. Se guarda en QSettings («ia/*»)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ia import proveedor as P
from traduccion.i18n import t as _tr


class IAConfigDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Configurar IA"))
        self.setMinimumWidth(520)
        c = P.Config.de(win._config_ia())
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr("La IA redacta el informe automático y responde «Pregúntale al proyecto». Los "
                                     "números siempre los pone la app; si la IA no responde, se usan plantillas."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QtWidgets.QFormLayout()
        self.cmb_prov = QtWidgets.QComboBox()
        self.cmb_prov.addItem(_tr("Sin IA (plantillas)"), P.PLANTILLA)
        self.cmb_prov.addItem(_tr("Servidor propio (Ollama)"), P.OLLAMA)
        self.cmb_prov.addItem(_tr("Claude (próximamente)"), P.ANTHROPIC)
        self.cmb_prov.model().item(2).setEnabled(False)
        self.cmb_prov.setCurrentIndex(max(0, self.cmb_prov.findData(c.proveedor)))
        self.ed_url = QtWidgets.QLineEdit(c.url)
        self.cmb_modelo = QtWidgets.QComboBox()
        self.cmb_modelo.setEditable(True)
        self.cmb_modelo.setEditText(c.modelo)
        btn_buscar = QtWidgets.QPushButton(_tr("Buscar modelos"))
        btn_buscar.setProperty("soft", True)
        btn_buscar.clicked.connect(self._buscar)
        fila = QtWidgets.QHBoxLayout()
        fila.addWidget(self.cmb_modelo, 1)
        fila.addWidget(btn_buscar)
        self.spn_par = QtWidgets.QSpinBox()
        self.spn_par.setRange(1, 8)
        self.spn_par.setValue(c.paralelo)
        self.spn_par.setToolTip(_tr("Pedidos a la vez al redactar el informe. Más es más rápido si el servidor "
                                    "lo permite (OLLAMA_NUM_PARALLEL)."))
        form.addRow(_tr("Quién responde"), self.cmb_prov)
        form.addRow(_tr("Servidor"), self.ed_url)
        form.addRow(_tr("Modelo"), fila)
        form.addRow(_tr("Pedidos a la vez"), self.spn_par)
        lay.addLayout(form)
        fila2 = QtWidgets.QHBoxLayout()
        btn_probar = QtWidgets.QPushButton(_tr("Probar"))
        btn_probar.clicked.connect(self._probar)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setWordWrap(True)
        fila2.addWidget(btn_probar)
        fila2.addWidget(self.lbl, 1)
        lay.addLayout(fila2)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setText(_tr("Guardar"))
        bb.button(QtWidgets.QDialogButtonBox.Cancel).setText(_tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.cmb_prov.currentIndexChanged.connect(self._sincronizar)
        self._sincronizar()

    def config(self):
        return {"proveedor": self.cmb_prov.currentData(), "url": self.ed_url.text().strip().rstrip("/"),
                "modelo": self.cmb_modelo.currentText().strip(), "paralelo": self.spn_par.value()}

    def _sincronizar(self):
        con = self.cmb_prov.currentData() == P.OLLAMA
        for w in (self.ed_url, self.cmb_modelo, self.spn_par):
            w.setEnabled(con)

    def _proveedor(self):
        return P.crear(self.config()) or P.Ollama(P.Config.de({**self.config(), "proveedor": P.OLLAMA}))

    def _en_hilo(self, fn, texto):
        from ui.comun import en_hilo
        return en_hilo.ejecutar(self, fn, texto, cancelable=True)

    def _buscar(self):
        r, err, cancel = self._en_hilo(self._proveedor().modelos, _tr("Buscando modelos…"))
        if cancel:
            return
        if err:
            self.lbl.setText(err.split("\n")[0])
            return
        actual = self.cmb_modelo.currentText()
        self.cmb_modelo.clear()
        self.cmb_modelo.addItems(r or [])
        self.cmb_modelo.setEditText(actual if actual in (r or []) or not r else r[0])
        self.lbl.setText(_tr("Modelos en el servidor: {n}.").format(n=len(r or [])))

    def _probar(self):
        r, err, cancel = self._en_hilo(self._proveedor().probar, _tr("Probando la IA…"))
        if not cancel:
            ok, msg = r if r else (False, err.split("\n")[0])
            self.lbl.setText(("✔ " if ok else "✖ ") + msg)

    def accept(self):
        s = QtCore.QSettings("pdf-to-cad", "app")
        for k, v in self.config().items():
            s.setValue("ia/" + k, v)
        super().accept()


def pedir(win):
    """True si se guardó."""
    return IAConfigDialog(win).exec() == QtWidgets.QDialog.Accepted
