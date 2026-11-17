"""Excepciones de callbacks Qt: registrar y avisar sin terminar QApplication.

Un MISMO error (tipo + lugar del código donde salta) se avisa una vez por sesión (reporte del cliente 2026-11-16:
un error al dibujar la Vista 3D se repetía en cada cuadro y el aviso volvía a salir al cerrarlo, en bucle, hasta
cerrar la app con el administrador de tareas). Las repeticiones solo se cuentan en el registro y en la barra de
estado de la ventana principal.
"""
import os
import sys
import threading
import traceback

from PySide6 import QtCore, QtGui, QtWidgets
from nucleo import diagnostico
from traduccion.i18n import t as _tr

REPETICIONES_REGISTRADAS = 3            # un error repetido se anota entero estas veces; después solo se cuenta


def firma(tipo, tb):
    """(tipo, archivo:línea del último lugar del código): lo que dice que dos errores son EL MISMO."""
    pila = traceback.extract_tb(tb) if tb is not None else []
    lugar = f"{os.path.basename(pila[-1].filename)}:{pila[-1].lineno}" if pila else "?"
    return tipo.__name__, lugar


def _donde(detalle):
    """En qué parte de la app pasó, según el código de la pila (para el mensaje)."""
    partes = (("visor3d", "la Vista 3D"), ("vista3d", "la Vista 3D"), ("perfil", "el perfil"),
              ("ia_", "el Asistente"), ("exportar", "la exportación"), ("informe", "el informe"),
              ("recognition", "el reconocimiento"), ("composite", "el compositor de hojas"),
              ("tabla_datos", "la Tabla de datos"), ("normas", "las normativas"))
    for linea in reversed(detalle.splitlines()):
        if 'File "' in linea:
            for clave, nombre in partes:
                if clave in linea:
                    return _tr(nombre)
    return ""


class GestorErrores(QtCore.QObject):
    fallo = QtCore.Signal(str, str)

    def __init__(self, app):
        super().__init__(app)
        self._mostrando = False
        self._vistos = {}                                # firma → veces
        self.fallo.connect(self._mostrar, QtCore.Qt.QueuedConnection)

    def capturar(self, tipo, valor, tb):
        clave = firma(tipo, tb)
        n = self._vistos[clave] = self._vistos.get(clave, 0) + 1
        detalle = "".join(traceback.format_exception(tipo, valor, tb))
        if n <= REPETICIONES_REGISTRADAS:
            path = diagnostico.registrar(detalle if n == 1 else f"(repetición {n}) {tipo.__name__}: {valor}",
                                         "Excepción no controlada")
        else:
            path = diagnostico.ruta()
        if n > 1:                                         # ya se avisó: sin otro diálogo
            self._en_barra(_tr("El mismo error se repitió ({n} veces); quedó en el registro.").format(n=n))
            return
        self.fallo.emit(f"{tipo.__name__}: {valor}", detalle + (f"\nRegistro: {path}" if path else ""))

    @staticmethod
    def _en_barra(texto):
        for w in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(w, QtWidgets.QMainWindow) and w.isVisible():
                try:
                    w.statusBar().showMessage(texto, 8000)
                except RuntimeError:
                    pass
                return

    @QtCore.Slot(str, str)
    def _mostrar(self, resumen, detalle):
        if self._mostrando:
            return  # otro error del mismo callback queda registrado, sin diálogos en cascada
        self._mostrando = True
        try:
            donde = _donde(detalle)
            box = QtWidgets.QMessageBox(QtWidgets.QApplication.activeWindow())
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle(_tr("Acción interrumpida"))
            box.setText(_tr("Algo falló en {d}.").format(d=donde) if donde else
                        _tr("Ocurrió un error al ejecutar la acción."))
            box.setInformativeText(
                _tr("Tu proyecto no se perdió: puedes seguir trabajando y guardar.") + "\n\n"
                + _tr("Si vuelve a pasar, envíanos el archivo de registro (botón «Abrir la carpeta del registro»).")
                + "\n\n" + _tr("Error: {e}").format(e=resumen))
            box.setDetailedText(detalle)
            box.setStandardButtons(QtWidgets.QMessageBox.Close)
            copiar = box.addButton(_tr("Copiar detalles"), QtWidgets.QMessageBox.ActionRole)
            carpeta = box.addButton(_tr("Abrir la carpeta del registro"), QtWidgets.QMessageBox.ActionRole)
            while True:                                   # copiar o abrir la carpeta no cierra el aviso
                box.exec()
                if box.clickedButton() is copiar:
                    QtWidgets.QApplication.clipboard().setText(detalle)
                elif box.clickedButton() is carpeta:
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.dirname(diagnostico.ruta())))
                else:
                    break
        finally:
            self._mostrando = False


def instalar(app):
    if hasattr(app, "_gestor_errores"):
        return app._gestor_errores
    gestor = app._gestor_errores = GestorErrores(app)
    anterior = sys.excepthook

    def capturar(tipo, valor, tb):
        if issubclass(tipo, (KeyboardInterrupt, SystemExit)):
            anterior(tipo, valor, tb)
        else:
            gestor.capturar(tipo, valor, tb)

    sys.excepthook = capturar
    threading.excepthook = lambda args: capturar(args.exc_type, args.exc_value, args.exc_traceback)
    return gestor
