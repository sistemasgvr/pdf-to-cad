"""Un trabajo largo POR PASOS que no bloquea la ventana (pedido del usuario 2026-10-23: el Informe automático no
dejaba seguir trabajando).

El trabajo es un GENERADOR; cada `yield` le devuelve el control a la ventana (el usuario sigue trabajando) y dice
qué esperar:
  - `yield`                            → seguir en la próxima vuelta del bucle de eventos;
  - `r = yield ("hilo", fn)`           → correr `fn()` en un hilo (lo que avise por `nucleo.avance` llega a
                                         `avance`); devuelve su resultado o LANZA su excepción en el generador;
  - `ok = yield ("esperar", cond, s)`  → hasta que `cond()` sea verdad (o pasen `s` segundos: ok = False).
`cancelar()` cierra el generador (sus `finally` corren); un hilo en curso termina solo y su resultado se descarta.
`esperar()` = bloquear hasta el final (pruebas). Al terminar llama `al_terminar(resultado, error)`.
"""
from __future__ import annotations

import threading
import time
import traceback

from PySide6 import QtCore

SONDEO_MS = 100


class _Aviso(QtCore.QObject):
    paso = QtCore.Signal(str, object, object)
    listo = QtCore.Signal(int, object, object)


class TrabajoPasos(QtCore.QObject):
    terminado = QtCore.Signal()

    def __init__(self, parent, gen, avance=None, al_terminar=None):
        super().__init__(parent)
        self.gen = gen
        self.avance = avance
        self.al_terminar = al_terminar
        self.activo = False
        self.cancelado = False
        self.resultado = None
        self.error = None
        self._hilo_n = 0
        self._aviso = _Aviso(self)
        if avance is not None:
            self._aviso.paso.connect(avance, QtCore.Qt.QueuedConnection)
        self._aviso.listo.connect(self._hilo_listo, QtCore.Qt.QueuedConnection)
        self._espera = None
        self._t = QtCore.QTimer(self, interval=SONDEO_MS, timeout=self._sondear)

    def empezar(self):
        self.activo = True
        QtCore.QTimer.singleShot(0, lambda: self._avanzar(None))
        return self

    def cancelar(self):
        if not self.activo:
            return
        self.cancelado = True
        self._hilo_n += 1                                  # el hilo en curso ya no cuenta
        self._t.stop()
        try:
            self.gen.close()
        except Exception:                                  # noqa: BLE001
            traceback.print_exc()
        self._fin(None, None)

    def esperar(self):
        if self.activo:
            lazo = QtCore.QEventLoop()
            self.terminado.connect(lazo.quit)
            if self.activo:
                lazo.exec()
        return self.resultado

    # ── motor ──
    def _avanzar(self, valor, exc=None):
        if not self.activo:
            return
        try:
            paso = self.gen.throw(exc) if exc is not None else self.gen.send(valor)
        except StopIteration as fin:
            self._fin(fin.value, None)
            return
        except Exception as e:                             # noqa: BLE001 (se informa a quien llamó)
            traceback.print_exc()
            self._fin(None, e)
            return
        if paso is None:
            QtCore.QTimer.singleShot(0, lambda: self._avanzar(None))
        elif paso[0] == "hilo":
            self._lanzar(paso[1])
        elif paso[0] == "esperar":
            cond, tope = paso[1], (paso[2] if len(paso) > 2 else None)
            self._espera = (cond, time.perf_counter() + tope if tope else None)
            self._sondear()
            if self._espera is not None:
                self._t.start()
        else:
            raise ValueError(paso)

    def _sondear(self):
        if self._espera is None:
            self._t.stop()
            return
        cond, fin = self._espera
        ok = bool(cond())
        if ok or (fin is not None and time.perf_counter() > fin):
            self._espera = None
            self._t.stop()
            QtCore.QTimer.singleShot(0, lambda: self._avanzar(ok))

    def _lanzar(self, fn):
        self._hilo_n += 1
        n = self._hilo_n
        aviso = self._aviso

        def correr():
            r, e = None, None
            try:
                if self.avance is not None:
                    from nucleo import avance as _avance
                    with _avance.escuchar(lambda t, i, k: aviso.paso.emit(t, i, k)):
                        r = fn()
                else:
                    r = fn()
            except BaseException as ex:                    # noqa: BLE001
                e = ex
            aviso.listo.emit(n, r, e)
        threading.Thread(target=correr, name="pdfcad-trabajo", daemon=True).start()

    def _hilo_listo(self, n, r, e):
        if n == self._hilo_n and self.activo:
            self._avanzar(r, e)

    def _fin(self, resultado, error):
        if not self.activo:
            return
        self.activo = False
        self.resultado, self.error = resultado, error
        if self.al_terminar is not None:
            try:
                self.al_terminar(resultado, error)
            except Exception:                              # noqa: BLE001
                traceback.print_exc()
        self.terminado.emit()
