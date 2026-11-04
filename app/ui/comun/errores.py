"""Excepciones de callbacks Qt: registrar y avisar sin terminar QApplication."""
import sys
import threading
import traceback

from PySide6 import QtCore, QtWidgets
from nucleo import diagnostico
from traduccion.i18n import t as _tr


class GestorErrores(QtCore.QObject):
    fallo = QtCore.Signal(str, str)

    def __init__(self, app):
        super().__init__(app)
        self._mostrando = False
        self.fallo.connect(self._mostrar, QtCore.Qt.QueuedConnection)

    def capturar(self, tipo, valor, tb):
        detalle = "".join(traceback.format_exception(tipo, valor, tb))
        path = diagnostico.registrar(detalle, "Excepción no controlada")
        self.fallo.emit(f"{tipo.__name__}: {valor}", detalle + (
            f"\nRegistro: {path}" if path else ""))

    @QtCore.Slot(str, str)
    def _mostrar(self, resumen, detalle):
        if self._mostrando:
            return  # otro error del mismo callback queda registrado, sin diálogos en cascada
        self._mostrando = True
        try:
            box = QtWidgets.QMessageBox(QtWidgets.QApplication.activeWindow())
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle(_tr("Acción interrumpida"))
            box.setText(_tr("Ocurrió un error al ejecutar la acción."))
            box.setInformativeText(resumen + "\n\n" + _tr(
                "Cierra este aviso y vuelve a intentar la acción. Si se repite, comparte los detalles del error."))
            box.setDetailedText(detalle)
            box.setStandardButtons(QtWidgets.QMessageBox.Close)
            box.exec()
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
