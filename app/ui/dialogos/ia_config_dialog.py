"""IA → «Configurar IA…» (pedido del usuario 2026-10-23): quién responde (sin IA = plantillas, servidor propio con
Ollama, o Gemini de Google con su clave de API —2026-11-11—; Claude después), la dirección del servidor, el modelo (se buscan los instalados) y cuántos pedidos a la vez
al redactar el informe. «Probar» pregunta algo corto y dice cuánto tardó. Se guarda en QSettings («ia/*»)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ia import memoria as M
from ia import proveedor as P
from ia import proveedor_gemini as PG
from traduccion.i18n import t as _tr


class IAConfigDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Configurar IA"))
        self.setMinimumWidth(520)
        c = P.Config.de(win._config_ia())
        s = QtCore.QSettings("pdf-to-cad", "app")
        # cada proveedor recuerda su modelo: al cambiar de proveedor se pone el suyo en el campo
        self._modelos = {P.OLLAMA: s.value("ia/modelo", P.MODELO_OLLAMA) or P.MODELO_OLLAMA,
                         P.GEMINI: s.value("ia/modelo_gemini", "") or PG.MODELO_GEMINI}
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr("La IA redacta el informe automático y responde «Pregúntale al proyecto». Los "
                                     "números siempre los pone la app; si la IA no responde, se usan plantillas."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QtWidgets.QFormLayout()
        self.cmb_prov = QtWidgets.QComboBox()
        self.cmb_prov.addItem(_tr("Sin IA (plantillas)"), P.PLANTILLA)
        self.cmb_prov.addItem(_tr("Servidor propio (Ollama)"), P.OLLAMA)
        self.cmb_prov.addItem(_tr("Gemini de Google (clave de API)"), P.GEMINI)
        self.cmb_prov.addItem(_tr("Claude (próximamente)"), P.ANTHROPIC)
        self.cmb_prov.model().item(3).setEnabled(False)
        self.cmb_prov.setCurrentIndex(max(0, self.cmb_prov.findData(c.proveedor)))
        self.ed_url = QtWidgets.QLineEdit(s.value("ia/url", P.URL_OLLAMA) or P.URL_OLLAMA)
        self.ed_clave = QtWidgets.QLineEdit(c.clave)
        self.ed_clave.setEchoMode(QtWidgets.QLineEdit.Password)
        self.ed_clave.setPlaceholderText(_tr("Pega aquí la clave de Google AI Studio"))
        self.ed_clave.setToolTip(_tr("Se guarda solo en este equipo. No la compartas: quien la tenga puede usar "
                                     "tu cuenta de Gemini."))
        self.lbl_gemini = QtWidgets.QLabel(_tr("Con Gemini, las preguntas, los datos del proyecto y los recortes del "
                                               "plano se envían a Google."))
        self.lbl_gemini.setWordWrap(True)
        self.lbl_gemini.setProperty("rol", "t3")
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
        form.addRow(_tr("Clave de API"), self.ed_clave)
        form.addRow("", self.lbl_gemini)
        self._form = form
        form.addRow(_tr("Modelo"), fila)
        form.addRow(_tr("Pedidos a la vez"), self.spn_par)
        self.cmb_entorno = QtWidgets.QComboBox()
        self.cmb_entorno.addItem(_tr("Desarrollo (pruebas del equipo)"), M.DESARROLLO)
        self.cmb_entorno.addItem(_tr("Producción (lo que va al cliente)"), M.PRODUCCION)
        self.cmb_entorno.setCurrentIndex(max(0, self.cmb_entorno.findData(win._config_ia().get("entorno"))))
        self.lbl_entorno = QtWidgets.QLabel()
        self.lbl_entorno.setWordWrap(True)
        self.lbl_entorno.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.cmb_entorno.currentIndexChanged.connect(self._mostrar_entorno)
        form.addRow(_tr("Entorno de entrenamiento"), self.cmb_entorno)
        form.addRow("", self.lbl_entorno)
        self._mostrar_entorno()
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
        self._prov_previo = self.cmb_prov.currentData()
        self.cmb_prov.currentIndexChanged.connect(self._cambio_proveedor)
        self._sincronizar()

    def config(self):
        return {"proveedor": self.cmb_prov.currentData(), "url": self.ed_url.text().strip().rstrip("/"),
                "modelo": self.cmb_modelo.currentText().strip(), "paralelo": self.spn_par.value(),
                "entorno": self.cmb_entorno.currentData(), "clave": self.ed_clave.text().strip()}

    def _mostrar_entorno(self):
        escribir, leer = M.rutas(self.cmb_entorno.currentData())
        texto = _tr("Lo que aprende se guarda en: {r}").format(r=escribir)
        if leer:
            texto += "\n" + _tr("También usa (solo lectura): {r}").format(r=", ".join(leer))
        self.lbl_entorno.setText(texto)

    def _cambio_proveedor(self):
        if self._prov_previo in self._modelos:          # recordar lo escrito para el proveedor anterior
            self._modelos[self._prov_previo] = self.cmb_modelo.currentText().strip()
        nuevo = self.cmb_prov.currentData()
        if nuevo in self._modelos:
            self.cmb_modelo.clear()
            self.cmb_modelo.setEditText(self._modelos[nuevo])
        self._prov_previo = nuevo
        self._sincronizar()

    def _sincronizar(self):
        prov = self.cmb_prov.currentData()
        ollama, gemini = prov == P.OLLAMA, prov == P.GEMINI
        for w in (self.cmb_modelo, self.spn_par):
            w.setEnabled(ollama or gemini)
        for w, ver in ((self.ed_url, not gemini), (self.ed_clave, gemini), (self.lbl_gemini, gemini)):
            w.setEnabled(ollama if w is self.ed_url else ver)
            self._form.setRowVisible(w, ver)

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
        self.lbl.setText(_tr("Modelos disponibles: {n}.").format(n=len(r or [])))

    def _probar(self):
        r, err, cancel = self._en_hilo(self._proveedor().probar, _tr("Probando la IA…"))
        if not cancel:
            ok, msg = r if r else (False, err.split("\n")[0])
            self.lbl.setText(("✔ " if ok else "✖ ") + msg)

    def accept(self):
        s = QtCore.QSettings("pdf-to-cad", "app")
        cfg = self.config()
        if cfg["proveedor"] in self._modelos:
            self._modelos[cfg["proveedor"]] = cfg["modelo"]
        cfg["modelo"] = self._modelos[P.OLLAMA]          # «ia/modelo» = el de Ollama, como siempre
        cfg["modelo_gemini"] = self._modelos[P.GEMINI]
        cfg["clave_gemini"] = cfg.pop("clave")
        for k, v in cfg.items():
            s.setValue("ia/" + k, v)
        super().accept()


def pedir(win):
    """True si se guardó."""
    return IAConfigDialog(win).exec() == QtWidgets.QDialog.Accepted
