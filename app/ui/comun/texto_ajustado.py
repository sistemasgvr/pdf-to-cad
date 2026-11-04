"""texto_ajustado.py — un QLabel con salto de línea que nunca queda cortado dentro de un QFormLayout.

QFormLayout reparte mal el alto de una fila cuyo alto depende de su ancho (texto con salto de línea): le daba
12–20 px de menos y la última línea quedaba tapada por la fila de abajo (reporte 2026-11-03: los avisos de
normativa del inspector se cortaban). Su mínimo es siempre el alto que pide su texto a su ancho actual.
"""
from PySide6 import QtCore, QtWidgets


class TextoAjustado(QtWidgets.QLabel):
    def _ajustar_alto(self):
        if self.wordWrap() and self.width() > 0 and not getattr(self, "_midiendo", False):
            self._midiendo = True
            try:
                # QLabel incluye el mínimo anterior en heightForWidth: quitarlo al medir permite encoger
                self.setMinimumHeight(0)
                self.setMinimumHeight(max(0, self.heightForWidth(self.width())))
            finally:
                self._midiendo = False

    def setText(self, texto):  # noqa: N802 (API Qt)
        super().setText(texto)
        self._ajustar_alto()

    def resizeEvent(self, evento):  # noqa: N802
        super().resizeEvent(evento)
        self._ajustar_alto()

    def changeEvent(self, evento):  # noqa: N802
        super().changeEvent(evento)
        if evento.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._ajustar_alto()
