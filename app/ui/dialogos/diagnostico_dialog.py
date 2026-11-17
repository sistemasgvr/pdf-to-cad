"""Ayuda → «Diagnóstico del equipo…» (2026-11-17): corre `diagnostico_equipo` en OTRO proceso (la prueba de OpenGL abre
sus propios contextos y no debe tocar los de la ventana) con la capa «Cargando…», y muestra el informe con «Copiar
informe» y «Abrir la carpeta del registro». El .txt queda guardado en la carpeta del registro."""
from __future__ import annotations

import os
import subprocess

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme


def _correr():
    import diagnostico_equipo as DE
    r = subprocess.run(DE.comando(), capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    salida = r.stdout.decode("utf-8", "replace").strip().splitlines()
    ruta = next((s.strip() for s in reversed(salida) if s.strip().lower().endswith(".txt")), "")
    return ruta, r.returncode


def abrir(win):
    from ui.comun import en_hilo
    import diagnostico_equipo as DE
    try:
        (ruta, _codigo), _err, _canc = en_hilo.ejecutar(win, _correr, _tr("Revisando el equipo…"),
                                                        _tr("Sistema, tarjeta de video y OpenGL"), relanzar=True)
    except Exception as e:                                   # noqa: BLE001
        QtWidgets.QMessageBox.warning(win, _tr("Diagnóstico del equipo"),
                                      _tr("No se pudo hacer el diagnóstico: {e}").format(e=e))
        return None
    if not ruta or not os.path.isfile(ruta):
        QtWidgets.QMessageBox.warning(win, _tr("Diagnóstico del equipo"), _tr("No se pudo hacer el diagnóstico."))
        return None
    texto = open(ruta, encoding="utf-8-sig", errors="replace").read()
    dlg = DialogoDiagnostico(win, texto, ruta, DE.carpeta())
    dlg.exec()
    return ruta


class DialogoDiagnostico(QtWidgets.QDialog):
    def __init__(self, padre, texto, ruta, carpeta):
        super().__init__(padre)
        self.setWindowTitle(_tr("Diagnóstico del equipo"))
        self.resize(860, 680)
        self.texto, self.ruta, self.carpeta = texto, ruta, carpeta
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(_tr("Si algo falla, envíanos este informe: dice qué tiene tu equipo y si la Vista 3D "
                                     "podrá funcionar. Se guardó en:") + f"<br><code>{ruta}</code>")
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lay.addWidget(intro)
        self.vista = QtWidgets.QPlainTextEdit(texto)
        self.vista.setReadOnly(True)
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.vista.setFont(f)
        t = _theme.tokens()
        self.vista.setStyleSheet(f"background:{t.surface};color:{t.text};")
        lay.addWidget(self.vista, 1)
        fila = QtWidgets.QHBoxLayout()
        self.btn_copiar = QtWidgets.QPushButton(_tr("Copiar informe"))
        self.btn_copiar.clicked.connect(self.copiar)
        self.btn_carpeta = QtWidgets.QPushButton(_tr("Abrir la carpeta del registro"))
        self.btn_carpeta.clicked.connect(self.abrir_carpeta)
        cerrar = QtWidgets.QPushButton(_tr("Cerrar"))
        cerrar.setDefault(True)
        cerrar.clicked.connect(self.accept)
        fila.addWidget(self.btn_copiar); fila.addWidget(self.btn_carpeta); fila.addStretch(1); fila.addWidget(cerrar)
        lay.addLayout(fila)

    def copiar(self):
        QtWidgets.QApplication.clipboard().setText(self.texto)
        self.btn_copiar.setText(_tr("Copiado"))

    def abrir_carpeta(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.carpeta))
