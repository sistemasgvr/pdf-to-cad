"""PilaActual: un QStackedWidget cuyo tamaño (preferido y mínimo) es el de la página A LA VISTA.

Reporte del usuario 2026-11-13: tras abrir Asistente → Conflictos (lista y ficha lado a lado, ~856 px de mínimo) el
panel derecho ya no se podía achicar, ni siquiera al volver a Chat o a Propiedades, y en pantallas chicas se salía de
la ventana. Un QStackedWidget pide el MAYOR mínimo de todas sus páginas, también de las ocultas; esta pide el de la
que se ve y avisa al cambiar de página.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets


MINIMO_BASE = "pdfcad_minimo_base"      # propiedad del panel lateral: su ancho mínimo propio (p. ej. 300)


def soltar_minimo(w):
    """Un QDockWidget se queda con el MAYOR mínimo que llegó a tener su contenido (Qt lo agranda con
    `expandedTo(minimumSize)` y nunca lo achica): devolverlo a su mínimo propio para que vuelva a seguir al
    contenido. Solo los paneles marcados con `MINIMO_BASE`."""
    if isinstance(w, QtWidgets.QDockWidget):
        base = w.property(MINIMO_BASE)
        if base is not None and w.minimumWidth() != int(base):
            w.setMinimumWidth(int(base))


def avisar_arriba(w):
    """El mínimo de `w` cambió (otra página, o la ficha pasó a una columna): soltar el mínimo guardado de los
    paneles de arriba y que se recalculen."""
    while w is not None and not w.isWindow():
        soltar_minimo(w)
        w.updateGeometry()
        w = w.parentWidget()


class PilaActual(QtWidgets.QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _i: self._avisar())

    def _avisar(self):
        """Otra página a la vista: que lo sepan todos los de arriba hasta la ventana."""
        w = self
        while w is not None and not w.isWindow():
            soltar_minimo(w)
            w.updateGeometry()
            if w.layout() is not None:
                w.layout().invalidate()
            w = w.parentWidget()

    def event(self, ev):                                   # la página de adentro cambió su mínimo: avisar arriba
        if ev.type() == QtCore.QEvent.LayoutRequest:
            avisar_arriba(self)
        return super().event(ev)

    def sizeHint(self):                                    # noqa: N802
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):                             # noqa: N802
        w = self.currentWidget()
        if w is None:
            return super().minimumSizeHint()
        m = w.minimumSizeHint()
        # un mínimo puesto a mano en la página (setMinimumWidth/Height) también cuenta
        return QtCore.QSize(max(m.width(), w.minimumWidth()), max(m.height(), w.minimumHeight()))
