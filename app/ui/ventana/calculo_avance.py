"""Barra PRECISA del recálculo de conflictos y avisos en segundo plano (`calculo_fondo`; pedido del usuario
2026-10-20: «hoy solo hay un texto en la barra de estado»). No tapa nada: una barra chica en la barra de
estado con el %, y el texto con la etapa.

Tres partes, pesadas por lo medido con AGUA 2 (16 762 utilidades): CRUCES y ACCESORIOS (cada una en su
proceso, ~6.5 y ~8 s contando enviar y recibir los datos; si van a la vez, cada una pesa la mitad del más
largo) y DIBUJO (el redibujo final con todas las marcas, ~4 s). Mientras una parte calcula avanza sola según
lo que se estima que tarda (hasta `TOPE_SOLA`), y lo que avisa su proceso (`Calculo._memo`: qué cálculo
terminó) la adelanta si va más rápido; al llegar su resultado queda completa. Nunca retrocede.
"""
from __future__ import annotations

import time

from PySide6 import QtCore, QtWidgets

from nucleo.avance_pesado import Barra
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

MS_POR_UTIL = {"cruces": 0.39, "accesorios": 0.48, "dibujo": 0.25}
TOPE_SOLA = 0.95
TICK_MS = 200
TEXTOS = {"cruces": N_("cruces y conflictos"), "accesorios": N_("accesorios y avisos"),
          "dibujo": N_("dibujando las marcas")}


class AvanceCalculo(QtCore.QObject):
    """La barra de UN cálculo de fondo (`win` = la ventana principal)."""

    def __init__(self, win, n_utilidades, grupos):
        super().__init__(win)
        self.win = win
        est = {k: n_utilidades * ms for k, ms in MS_POR_UTIL.items()}
        self.estimado = dict(est)                      # ms de pared de cada parte
        if len(grupos) > 1:                            # a la vez: el total es el más largo de los dos
            mitad = max(est["cruces"], est["accesorios"]) / 2.0
            est["cruces"] = est["accesorios"] = mitad
        self.barra = Barra(est)
        self.desde = {k: time.perf_counter() for g in grupos for k in g}
        self.listas = set()
        self.etapa = None
        self._t = QtCore.QTimer(self, interval=TICK_MS, timeout=self._tick)
        self._t.start()
        self._mostrar()

    @staticmethod
    def _widget(win):
        bar = getattr(win, "_barra_calculo", None)
        if bar is None and hasattr(win, "status"):
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            bar.setFixedWidth(120)
            bar.setMaximumHeight(14)
            bar.setVisible(False)
            win.status.insertPermanentWidget(0, bar)
            win._barra_calculo = bar
        return bar

    def aviso(self, parte, msg):
        """Lo que avisa el proceso de `parte`: («detalle», parte, hecho, total)."""
        if isinstance(msg, tuple) and len(msg) >= 4 and msg[0] == "detalle" and msg[3]:
            # lo calculado es ~60 % de la parte (lo demás: mandar y recibir los datos)
            self.barra.parte(parte, 0.6 * float(msg[2]) / float(msg[3]))
            self._mostrar()

    def lista(self, parte):
        self.listas.add(parte)
        self.barra.lista(parte)
        self._mostrar()

    def dibujando(self):
        """Empieza el redibujo final (bloquea la ventana): se muestra antes de empezar."""
        for p in ("cruces", "accesorios"):
            self.barra.lista(p)
        self.etapa = "dibujo"
        self._mostrar(repintar=True)

    def cerrar(self):
        self._t.stop()
        bar = self._widget(self.win)
        if bar is not None:
            bar.setVisible(False)
        if hasattr(self.win, "statusBar"):
            self.win.statusBar().clearMessage()

    def _tick(self):
        ahora = time.perf_counter()
        for parte, t0 in self.desde.items():
            if parte not in self.listas:
                est = max(0.5, self.estimado[parte] / 1000.0)
                self.barra.parte(parte, min(TOPE_SOLA, (ahora - t0) / est))
        self._mostrar()

    def _mostrar(self, repintar=False):
        mil = self.barra.milesimas
        bar = self._widget(self.win)
        if bar is not None:
            bar.setVisible(True)
            bar.setValue(mil)
        faltan = [p for p in ("cruces", "accesorios") if p in self.desde and p not in self.listas]
        etapa = self.etapa or (faltan[0] if len(faltan) == 1 else None)
        texto = _tr("Actualizando conflictos y avisos… {p} %").format(p=mil // 10)
        if etapa:
            texto += " · " + _tr(TEXTOS[etapa])
        if hasattr(self.win, "statusBar"):
            self.win.statusBar().showMessage(texto)
        if repintar and bar is not None:
            bar.repaint()
            self.win.statusBar().repaint()
