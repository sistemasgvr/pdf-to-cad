"""Indicador de «trabajando» de la barra superior (2026-11-21, pedido del usuario: cada acción debe mostrar que carga).

El aro de `accion_cargando` va sobre el BOTÓN pulsado; las acciones que se lanzan por menú, atajo o paleta (Ctrl+K)
no tienen botón, así que este aro, junto al buscador de la barra superior, gira mientras haya CUALQUIER trabajo en
marcha (`nucleo.actividad`). Aparece tras `RETRASO_MS` (lo instantáneo no parpadea) y se queda `GRACIA_MS` por si el
trabajo que termina lanza otro. Reserva su sitio siempre: la barra no se corre al aparecer."""
from __future__ import annotations

import threading

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import actividad
from traduccion.i18n import t as _tr
from ui.comun import theme as _theme

RETRASO_MS = 250
GRACIA_MS = 450
LADO = 22


def _seguro(f):
    """Qt pudo borrar la barra: un adorno no rompe nada (2026-11-21)."""
    def envoltura(*a, **k):
        try:
            return f(*a, **k)
        except RuntimeError:
            return None
    envoltura.__name__ = f.__name__
    return envoltura


class IndicadorActividad(QtWidgets.QWidget):
    _desde_otro_hilo = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(LADO + 8, LADO + 8)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self._girando = False
        self._angulo = 0.0
        self._giro = QtCore.QTimer(self, interval=16, timeout=self._girar)
        self._espera = QtCore.QTimer(self, singleShot=True, timeout=self._revisar)
        self._desde_otro_hilo.connect(self._cambio, QtCore.Qt.QueuedConnection)
        self._dejar = actividad.escuchar(self._oir)
        self.destroyed.connect(lambda *_: self._dejar())
        self.setAccessibleName(_tr("Trabajando"))

    def _oir(self, *_):
        if threading.current_thread() is threading.main_thread():
            self._cambio()
        else:
            self._desde_otro_hilo.emit()

    def activo(self) -> bool:
        return self._girando

    @_seguro
    def _cambio(self):
        if self._girando:
            self._poner_globo()
        if actividad.hay():
            if not self._girando and not self._espera.isActive():
                self._espera.start(RETRASO_MS)                 # solo si dura: lo instantáneo no se ve
        elif self._girando:
            self._espera.start(GRACIA_MS)                      # por si el que termina lanza otro

    @_seguro
    def _revisar(self):
        if actividad.hay():
            if not self._girando:
                self._girando = True
                self._giro.start()
                self._poner_globo()
                self.update()
        elif self._girando:
            self._girando = False
            self._giro.stop()
            self.setToolTip("")
            self.update()

    @_seguro
    def _girar(self):
        self._angulo = (self._angulo + 14.0) % 360.0
        self.update()

    def _poner_globo(self):
        nombres = sorted(set(actividad.vivas().values()))
        self.setToolTip(_tr("Trabajando…") + ("\n" + "\n".join(nombres[:6]) if nombres else ""))

    @_seguro
    def paintEvent(self, _ev):
        if not self._girando:
            return
        t = _theme.tokens()
        r = QtCore.QRectF(self.rect()).adjusted(5, 5, -5, -5)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        pista = QtGui.QColor(t.accent)
        pista.setAlpha(60)
        p.setPen(QtGui.QPen(pista, 2.4))
        p.drawEllipse(r)
        p.setPen(QtGui.QPen(QtGui.QColor(t.accent), 2.4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        p.drawArc(r, int(-self._angulo * 16), 100 * 16)
        p.end()
