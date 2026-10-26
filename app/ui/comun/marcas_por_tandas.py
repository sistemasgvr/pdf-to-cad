"""marcas_por_tandas.py — las marcas del lienzo se cargan POR TANDAS en planos gigantes.

Pedido del usuario 2026-10-26: «cuando el plano es gigante y se intentan cargar todos los avisos de
golpe, se lajea el programa». Medido con AGUA 2 (16 761 utilidades): al llegar los resultados del
cálculo de fondo, el redibujo final creaba de golpe ~54 mil marcas (16 812 cruces, 19 802 etiquetas de
accesorios, insignias de avisos y C-n) y la ventana quedaba ~3.7 s congelada.

Cada dibujante de marcas (`ventana_conflictos`, `accesorios_view`, `avisos_view`, `conflictos_view`)
es un GENERADOR con el mismo cuerpo de siempre: crea la marca, la pone en su capa (`capa_marcas`) y la
entrega. Con pocas marcas se recorre entero en el redibujo (como antes); con `UMBRAL` o más, la ventana
lo pasa a una `Tandas`, que avanza `TANDA_MS` por vuelta del bucle de eventos (la ventana atiende al
usuario entre tandas) con el % en la barra de estado. Las capas del grupo no se pintan mientras se
cargan (repintarlas a medias costaba ~0.3 s cada vez: 76 repintados, ~3 s) y aparecen todas juntas al
final, en un solo repintado. Los generadores se
recorren EN EL ORDEN en que se pidieron, así que al terminar cada capa tiene las mismas marcas en el
mismo orden que cargadas de golpe: mismo dibujo, mismos globos, mismo despeje de rótulos.

Si el modelo cambia a medias, el redibujo siguiente cancela la carga (el grupo a medias no queda para
deshacer: `firma` = None); con el mismo modelo (elegir, Esc) la carga sigue en el mismo grupo.
"""
from __future__ import annotations

import os
import time
from collections import deque

from PySide6 import QtCore

from traduccion.i18n import t as _tr

UMBRAL = int(os.environ.get("PDFCAD_MARCAS_TANDAS_MIN", "5000"))   # marcas de un dibujante para ir por tandas
TANDA_MS = 30                     # trabajo por vuelta del bucle de eventos
REFRESCO_S = 0.25                 # cada cuánto se actualiza el % en la barra de estado


class Tandas(QtCore.QObject):
    """La carga en curso de las marcas de UN grupo (`capa_marcas.GrupoMarcas`) de la ventana `win`."""

    def __init__(self, win, grupo):
        super().__init__(win)
        self.win = win
        self.grupo = grupo
        self.cola = deque()
        self.total = 0
        self.hechas = 0
        self.terminada = False
        self._mostrado = False                           # puso su avance en la barra de estado
        self._refresco = time.perf_counter()
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)
        grupo.cargar(True)                               # sus capas aparecen todas juntas al terminar

    def agregar(self, gen, n):
        """Un dibujante más (generador de marcas ya puestas en su capa) con ~`n` marcas."""
        self.cola.append(gen)
        self.total += max(0, int(n))
        if not self._timer.isActive():
            self._timer.start()

    def _viva(self):
        try:
            return self.grupo.vivo(self.win.canvas.scene())
        except RuntimeError:
            return False

    def _avanzar(self, hasta=None):
        """Saca marcas hasta vaciar la cola (o hasta el instante `hasta`). True = terminó."""
        overlay = self.win._overlay
        cola = self.cola
        reloj = time.perf_counter
        while cola:
            try:
                it = next(cola[0])
            except StopIteration:
                cola.popleft()
                continue
            overlay.append(it)
            self.hechas += 1
            if hasta is not None and not (self.hechas & 63) and reloj() > hasta:
                return False
        return True

    def _tick(self):
        if self.terminada:
            return
        if not self._viva():                             # la escena se vació (otra hoja, otro proyecto)
            self.cancelar()
            return
        if self._avanzar(time.perf_counter() + TANDA_MS / 1000.0):
            self._terminar()
            return
        ahora = time.perf_counter()
        if ahora - self._refresco >= REFRESCO_S:
            self._refresco = ahora
            self._mostrar()
        self._timer.start()

    def correr_todo(self):
        """Termina ya, sin ceder (quien necesita todas las marcas en la escena: capturas del informe)."""
        if self.terminada:
            return
        if self._viva():
            self._avanzar()
            self._terminar()
        else:
            self.cancelar()

    def cancelar(self):
        self._timer.stop()
        self.cola.clear()
        self.terminada = True
        self.grupo.firma = None                          # a medias: no se reusa ni se guarda para deshacer
        self._cerrar()

    def _terminar(self):
        self._timer.stop()
        self.terminada = True
        oc = getattr(self.win, "_ocultar_marcas_apagadas", None)
        if oc is not None:
            oc()                                         # «Capas»: ya con todas las marcas
        self.grupo.cargar(False)                         # aparecen todas (un solo repintado)
        self._cerrar()

    # ── avance en la barra de estado ──
    def _mostrar(self):
        p = int(100 * self.hechas / self.total) if self.total else 0
        self._mostrado = True
        bar = self._barra()
        if bar is not None:
            bar.setVisible(True)
            bar.setValue(min(1000, int(1000 * self.hechas / self.total)) if self.total else 0)
        if hasattr(self.win, "statusBar"):
            self.win.statusBar().showMessage(_tr("Cargando las marcas del plano… {p} %").format(p=min(p, 99)))

    def _barra(self):
        from ui.ventana.calculo_avance import AvanceCalculo
        return AvanceCalculo._widget(self.win)

    def _cerrar(self):
        if getattr(self.win, "_tandas", None) is self:
            self.win._tandas = None
        if not self._mostrado:
            return
        bar = self._barra()
        if bar is not None:
            bar.setVisible(False)
        if hasattr(self.win, "statusBar"):
            self.win.statusBar().clearMessage()
