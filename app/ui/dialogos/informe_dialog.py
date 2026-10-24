"""Opciones del INFORME AUTOMÁTICO (pedido del usuario 2026-10-23): qué entra (conflictos y/o normativas)
y qué capturas lleva cada zona (2D, 3D o ambas). Recuerda la última elección (QSettings)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from nucleo.informe_datos import Opciones
from traduccion.i18n import t as _tr

_CLAVE = "informe"


def _ajustes():
    return QtCore.QSettings("pdf-to-cad", "app")


class InformeDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, n_conflictos=0, n_avisos=0, n_reconocimiento=0):
        super().__init__(parent)
        self.setWindowTitle(_tr("Informe automático"))
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr("Arma un informe en Word con las fichas de cada zona del plano, sus capturas "
                                     "y la explicación de cada conflicto y aviso."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        g1 = QtWidgets.QGroupBox(_tr("Qué incluir"))
        l1 = QtWidgets.QVBoxLayout(g1)
        self.chk_conf = QtWidgets.QCheckBox(_tr("Conflictos ({n})").format(n=n_conflictos))
        self.chk_norm = QtWidgets.QCheckBox(_tr("Normativas ({n} avisos)").format(n=n_avisos))
        self.chk_rec = QtWidgets.QCheckBox(_tr("Avisos de reconocimiento, aparte ({n})").format(n=n_reconocimiento))
        self.chk_rec.setToolTip(_tr("Lo que el reconocimiento del PDF no leyó con certeza (diámetro del plano). Va "
                                    "en su propia sección, no como normativa."))
        for c in (self.chk_conf, self.chk_norm, self.chk_rec):
            l1.addWidget(c)
            c.toggled.connect(self._botones)
        lay.addWidget(g1)
        g2 = QtWidgets.QGroupBox(_tr("Capturas de cada zona"))
        l2 = QtWidgets.QVBoxLayout(g2)
        self.rb_2d = QtWidgets.QRadioButton(_tr("Plano (2D)"))
        self.rb_3d = QtWidgets.QRadioButton(_tr("Vista 3D"))
        self.rb_ambas = QtWidgets.QRadioButton(_tr("Plano y vista 3D"))
        for r in (self.rb_2d, self.rb_3d, self.rb_ambas):
            l2.addWidget(r)
        nota = QtWidgets.QLabel(_tr("La vista 3D se arma si no está abierta: con proyectos grandes tarda más."))
        nota.setObjectName("hint"); nota.setWordWrap(True)
        l2.addWidget(nota)
        lay.addWidget(g2)
        self.botones = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.botones.button(QtWidgets.QDialogButtonBox.Ok).setText(_tr("Generar informe…"))
        self.botones.button(QtWidgets.QDialogButtonBox.Cancel).setText(_tr("Cancelar"))
        self.botones.accepted.connect(self.accept)
        self.botones.rejected.connect(self.reject)
        lay.addWidget(self.botones)
        s = _ajustes()
        self.chk_conf.setChecked(s.value(_CLAVE + "/conflictos", True, type=bool))
        self.chk_norm.setChecked(s.value(_CLAVE + "/normativas", True, type=bool))
        self.chk_rec.setChecked(s.value(_CLAVE + "/reconocimiento", True, type=bool))
        {"2d": self.rb_2d, "3d": self.rb_3d, "ambas": self.rb_ambas}.get(
            s.value(_CLAVE + "/capturas", "2d"), self.rb_2d).setChecked(True)
        self._botones()

    def _botones(self):
        self.botones.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(
            self.chk_conf.isChecked() or self.chk_norm.isChecked() or self.chk_rec.isChecked())

    def opciones(self):
        return Opciones(conflictos=self.chk_conf.isChecked(), normativas=self.chk_norm.isChecked(),
                        capturas_2d=self.rb_2d.isChecked() or self.rb_ambas.isChecked(),
                        capturas_3d=self.rb_3d.isChecked() or self.rb_ambas.isChecked(),
                        reconocimiento=self.chk_rec.isChecked())

    def accept(self):
        s = _ajustes()
        s.setValue(_CLAVE + "/conflictos", self.chk_conf.isChecked())
        s.setValue(_CLAVE + "/normativas", self.chk_norm.isChecked())
        s.setValue(_CLAVE + "/reconocimiento", self.chk_rec.isChecked())
        s.setValue(_CLAVE + "/capturas", "ambas" if self.rb_ambas.isChecked() else "3d" if self.rb_3d.isChecked()
                   else "2d")
        super().accept()


def pedir(win, n_conflictos=0, n_avisos=0, n_reconocimiento=0):
    """Opciones elegidas, o None si se canceló."""
    dlg = InformeDialog(win, n_conflictos, n_avisos, n_reconocimiento)
    return dlg.opciones() if dlg.exec() == QtWidgets.QDialog.Accepted else None
