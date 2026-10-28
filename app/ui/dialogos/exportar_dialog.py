"""2.0.0 — «Exportar a Civil 3D» (como el prototipo): qué incluir, versión e idioma de Civil 3D, y Exportar.

Exportar llama a `win.run_pipeline(modo)` de siempre: «Plano + utilidades» = 'todo' (lo que hacía el botón
antes), «Solo utilidades» = 'anot', «Solo el plano» = 'pdf'. Después siguen igual la revisión del dibujo (solo
pregunta si hay algo que arreglar) y el «Guardar DXF» para elegir dónde.
"""
from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import rediseno as R
from ui.comun.icons import icon as _icon
from ui.dialogos.ajustes_dialog import AjustesDialog

MODOS = [("todo", "Plano + utilidades"), ("anot", "Solo utilidades"), ("pdf", "Solo el plano")]


class ExportarDialog(QtWidgets.QDialog):
    _copiar_combos = AjustesDialog._copiar_combos     # mismos combos reflejados que Ajustes → Civil 3D
    _a_la_ventana = AjustesDialog._a_la_ventana

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Exportar a Civil 3D"))
        self.setMinimumWidth(620)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(R.texto("Exportar a Civil 3D", "h1"))
        lay.addWidget(R.texto("Un DXF con las utilidades, buzones y datos para IMPORTAR_RED.", "t2", True))
        seg = QtWidgets.QFrame()
        seg.setObjectName("segmentado")
        sl = QtWidgets.QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        self.grupo = QtWidgets.QButtonGroup(seg)
        for i, (_m, clave) in enumerate(MODOS):
            b = QtWidgets.QPushButton(_tr(clave))
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.grupo.addButton(b, i)
            sl.addWidget(b, 1)
        if getattr(win, "blank_canvas", False):            # lienzo en blanco: no hay plano que exportar
            for i in (0, 2):
                self.grupo.button(i).setEnabled(False)
            self.grupo.button(1).setChecked(True)
        lay.addWidget(self._fila("Incluir", seg))
        self.cmb_anio = QtWidgets.QComboBox()
        self.cmb_cat = QtWidgets.QComboBox()
        self._copiar_combos()
        self.cmb_anio.currentIndexChanged.connect(lambda i: self._a_la_ventana(win.cmb_civil, i))
        self.cmb_cat.currentIndexChanged.connect(lambda i: self._a_la_ventana(win.cmb_lang, i))
        lay.addWidget(self._fila("Civil 3D", self.cmb_anio))
        lay.addWidget(self._fila("Catálogo", self.cmb_cat))
        nota = QtWidgets.QFrame()
        nota.setObjectName("tarjetaSuave")
        nl = QtWidgets.QVBoxLayout(nota)
        nl.setContentsMargins(12, 10, 12, 10)
        nl.addWidget(R.texto("Antes de exportar se revisa el dibujo (puntas sueltas, tramos diminutos…): si hay "
                             "algo que arreglar, te lo pregunta. Después eliges dónde guardar el DXF.", "t2", True))
        lay.addWidget(nota)
        bt = QtWidgets.QHBoxLayout()
        bt.addStretch(1)
        cancelar = QtWidgets.QPushButton(_tr("Cancelar"))
        cancelar.setProperty("kind", "ghost")
        cancelar.setAutoDefault(False)
        cancelar.clicked.connect(self.reject)
        bt.addWidget(cancelar)
        ok = QtWidgets.QPushButton(_tr("Exportar"))
        ok.setProperty("kind", "primary")
        ok.setIcon(_icon("mdi:export-variant", color="#ffffff"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bt.addWidget(ok)
        lay.addLayout(bt)

    @staticmethod
    def _fila(etiqueta_es, control):
        w = R.transparente(QtWidgets.QWidget())
        f = QtWidgets.QHBoxLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        lbl = R.texto(etiqueta_es, "t2")
        lbl.setFixedWidth(110)
        f.addWidget(lbl)
        f.addWidget(control, 1)
        return w

    def modo(self):
        return MODOS[self.grupo.checkedId()][0]


def exportar(win):
    dlg = ExportarDialog(win)
    if dlg.exec() == QtWidgets.QDialog.Accepted:
        QtCore.QTimer.singleShot(0, lambda m=dlg.modo(): win.run_pipeline(m))
