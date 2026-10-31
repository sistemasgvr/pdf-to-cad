"""Vista 3D: navegar con la RUEDA del ratón (pedido del usuario 2026-10-30).

- Un CLIC en la rueda (apretar y soltar sin arrastrar) entra en «navegar», como en el navegador: la vista avanza
  hacia donde está el cursor respecto del punto del clic (izquierda/derecha/arriba/abajo), más rápido cuanto más
  lejos. Otro clic (cualquier botón), Esc o salir de la ventana lo termina. Apretar la rueda y arrastrar sigue
  desplazando como siempre; doble clic en la rueda sigue encuadrando todo.
- Con la rueda APRETADA, sus giros desplazan en vez de acercar (algunos ratones convierten «rueda apretada + mover»
  en giros de rueda: arriba/abajo acercaba y alejaba, izquierda/derecha no hacía nada). Los giros horizontales
  (inclinar la rueda / panel táctil) desplazan a los lados.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui

ZONA_MUERTA_PX = 8          # cerca del punto del clic no se mueve
VELOCIDAD = 0.08            # px de la vista por cuadro, por px de distancia al punto del clic
CUADRO_MS = 16
PASO_RUEDA_PX = 60.0        # cuánto desplaza un «clic» de rueda (con la rueda apretada o de lado)


class AutoPanMixin:
    def _iniciar_autopan(self):
        self._autopan = None                                # punto del clic (None = apagado)
        self._t_autopan = QtCore.QTimer(self, interval=CUADRO_MS, timeout=self._autopan_paso)

    def _desplazar_px(self, dx, dy):
        """Mueve el objetivo como si el ratón se arrastrara (dx, dy) px (signo: lo que se ve va al revés)."""
        der, arriba = self.cam.ejes()
        k = self._pies_por_px(None)
        self.cam.objetivo = self.cam.objetivo - der * dx * k + arriba * dy * k
        self.update()

    def autopan_activo(self):
        return getattr(self, "_autopan", None) is not None

    def autopan_entrar(self, pos):
        self._autopan = QtCore.QPointF(pos)
        self._autopan_cursor = QtCore.QPointF(pos)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        self._t_autopan.start()

    def autopan_salir(self):
        if getattr(self, "_autopan", None) is None:
            return
        self._autopan = None
        self._t_autopan.stop()
        self.setCursor(QtCore.Qt.ArrowCursor)

    def _autopan_paso(self):
        if self._autopan is None:
            return
        off = self._autopan_cursor - self._autopan
        vx = _vel(off.x())
        vy = _vel(off.y())
        if vx or vy:                                        # se ve lo que está hacia el cursor
            self._desplazar_px(-vx, -vy)

    def _autopan_mover(self, pos):
        if self._autopan is not None:
            self._autopan_cursor = QtCore.QPointF(pos)
            return True
        return False

    def _rueda_desplaza(self, e):
        """Giros de rueda que desplazan (rueda apretada o de lado). True si ya se usó el evento."""
        d = e.angleDelta()
        apretada = bool(e.buttons() & QtCore.Qt.MiddleButton) or self.autopan_activo()
        dx = d.x() / 120.0 * PASO_RUEDA_PX
        dy = d.y() / 120.0 * PASO_RUEDA_PX if apretada else 0.0
        if not dx and not dy:
            return apretada                                  # rueda apretada sin giro: tampoco acerca
        self._desplazar_px(dx, dy)
        return True


def _vel(d):
    if abs(d) <= ZONA_MUERTA_PX:
        return 0.0
    return (abs(d) - ZONA_MUERTA_PX) * VELOCIDAD * (1 if d > 0 else -1)
