"""proceso.py — trabajo pesado en un PROCESO aparte, controlado (pedido del usuario 2026-10-14).

Reconocer o armar una hoja compuesta de decenas de hojas (mapas de Phoenix: 36) usaba
varios GB de RAM DENTRO de la ventana y la dejaba trabada: el hilo de fondo compartía el GIL
con la interfaz (cada llamada larga de MuPDF lo retiene entera) y la memoria no volvía al
sistema al terminar (el asignador de Python la conserva). Aquí el trabajo va a un proceso
TRABAJADOR (`multiprocessing`, «spawn», el mismo en el .exe con `freeze_support`):

  · la ventana nunca espera al trabajo: sondea la cola cada `SONDEO_MS` y repinta;
  · prioridad baja y TOPE de memoria (`proceso_hijo`): el resto del equipo sigue andando y
    un trabajo que no cabe falla con un aviso en vez de llevar todo a la memoria virtual;
  · el avance llega por la misma cola (`Tarea.avance`), también resultados parciales;
  · cancelar = terminar el proceso (al instante); se vuelve a crear al pedir otro trabajo;
  · el trabajador se REUSA (no paga otra vez ~1–2 s de arranque e importaciones) y se
    recicla si tras un trabajo quedó con más de `RECICLAR_MB` (vuelve la RAM al sistema).

`PDFCAD_PROCESO=0` lo apaga (las pruebas: `tests/conftest.py`); entonces cada `Tarea` corre en
un hilo como antes. Las funciones de trabajo son PURAS y reciben `progreso=`.
"""
from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import queue
import threading
from typing import Dict, Optional

from PySide6 import QtCore

from ui.comun import proceso_hijo

SONDEO_MS = 60
RECICLAR_MB = 1200           # memoria del trabajador tras un trabajo: más que esto → otro proceso
TOPE_FRACCION = 0.7          # tope de memoria del trabajador = esta parte de la RAM del equipo
TOPE_MIN_MB = 2048


def activo() -> bool:
    return os.environ.get("PDFCAD_PROCESO", "1") != "0"


def tope_mb() -> int:
    total = proceso_hijo.memoria_total_mb()
    return max(TOPE_MIN_MB, int(total * TOPE_FRACCION)) if total else 0


class Tarea(QtCore.QObject):
    """Un trabajo. `avance(tupla)` = lo que la función pasó a `progreso(...)`;
    `terminado(resultado, error)`: error "" = bien, «memoria», «cancelado» o el traceback."""
    avance = QtCore.Signal(object)
    terminado = QtCore.Signal(object, str)

    def __init__(self, objetivo: str, args=(), kwargs=None, parent=None):
        super().__init__(parent)
        self.objetivo, self.args, self.kwargs = objetivo, tuple(args), dict(kwargs or {})
        self.id = None
        self.hecha = False
        self._dueno: Optional["Trabajador"] = None

    def cancelar(self):
        if not self.hecha and self._dueno is not None:
            self._dueno.cancelar(self)

    def _fin(self, res, err):
        if not self.hecha:
            self.hecha = True
            self.terminado.emit(res, err)


class Trabajador(QtCore.QObject):
    """Un proceso hijo y su cola de trabajos (uno a la vez, en orden)."""
    _ids = itertools.count(1)

    def __init__(self, nombre: str):
        super().__init__()
        self.nombre = nombre
        self._proc = None
        self._entrada = self._salida = None
        self._cola: list = []
        self._actual: Optional[Tarea] = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(SONDEO_MS)
        self._timer.timeout.connect(self._sondear)
        self._hilo: Optional[threading.Thread] = None       # sin proceso (PDFCAD_PROCESO=0)
        self._hilo_res: "queue.Queue" = queue.Queue()

    # ── API ───────────────────────────────────────────────────────────
    def enviar(self, tarea: Tarea) -> Tarea:
        tarea._dueno = self
        tarea.id = next(self._ids)
        self._cola.append(tarea)
        self._siguiente()
        return tarea

    def cancelar(self, tarea: Tarea):
        if tarea in self._cola:
            self._cola.remove(tarea)
            tarea._fin(None, "cancelado")
            return
        if tarea is self._actual:
            self._actual = None
            if self._hilo is None:
                self._matar()             # el hilo no se puede matar: su resultado se descarta
            tarea._fin(None, "cancelado")
            self._siguiente()

    def parar(self):
        for t in list(self._cola):
            self.cancelar(t)
        if self._actual is not None:
            self.cancelar(self._actual)
        self._matar()

    # ── proceso ───────────────────────────────────────────────────────
    def _arrancar(self):
        ctx = mp.get_context("spawn")
        self._entrada, self._salida = ctx.Queue(), ctx.Queue()
        self._proc = ctx.Process(target=proceso_hijo.bucle, name=f"pdfcad-{self.nombre}",
                                 args=(self._entrada, self._salida, tope_mb()), daemon=True)
        self._proc.start()

    def _matar(self):
        p, self._proc = self._proc, None
        if p is not None:
            try:
                p.terminate()
                p.join(2)
            except Exception:
                pass
        for q in (self._entrada, self._salida):
            try:
                if q is not None:
                    q.cancel_join_thread()
                    q.close()
            except Exception:
                pass
        self._entrada = self._salida = None

    def _siguiente(self):
        if self._actual is not None or not self._cola:
            if self._actual is None and self._hilo is None:
                self._timer.stop()
            return
        t = self._actual = self._cola.pop(0)
        try:
            if not activo():
                self._en_hilo(t)
            else:
                if self._proc is None or not self._proc.is_alive():
                    self._matar()
                    self._arrancar()
                self._entrada.put((t.id, t.objetivo, t.args, t.kwargs))
        except Exception:
            import traceback
            detalle = traceback.format_exc()
            self._actual = None
            self._matar()
            t._fin(None, detalle)
            self._siguiente()
            return
        self._timer.start()

    def _en_hilo(self, t: Tarea):
        def correr(tid=t.id):
            import importlib
            import traceback
            from nucleo import avance
            try:
                nombre, fn = t.objetivo.split(":")
                f = getattr(importlib.import_module(nombre), fn)
                with avance.escuchar(lambda tx, i, n: self._hilo_res.put(("avance", tid, ("detalle", tx, i, n)))):
                    res = f(*t.args, progreso=lambda *a: self._hilo_res.put(("avance", tid, a)), **t.kwargs)
                self._hilo_res.put(("ok", tid, res, 0))
            except MemoryError:
                self._hilo_res.put(("memoria", tid))
            except BaseException:
                self._hilo_res.put(("error", tid, traceback.format_exc()))
        self._hilo = threading.Thread(target=correr, daemon=True)
        self._hilo.start()

    def _mensajes(self):
        fuente = self._hilo_res if self._hilo is not None or not activo() else self._salida
        while fuente is not None:
            try:
                yield fuente.get_nowait()
            except (queue.Empty, OSError, ValueError, EOFError):
                return

    def _sondear(self):
        for msg in self._mensajes():
            tipo, tid = msg[0], msg[1]
            t = self._actual
            if t is None or tid != t.id:
                if tipo != "avance" and self._hilo is not None:
                    self._hilo = None
                continue                          # de un trabajo cancelado
            if tipo == "avance":
                t.avance.emit(msg[2])
                continue
            self._actual = None
            self._hilo = None
            if tipo == "ok":
                t._fin(msg[2], "")
                if msg[3] and msg[3] > RECICLAR_MB:
                    self._matar()                 # devuelve la memoria al sistema
            elif tipo == "memoria":
                self._matar()
                t._fin(None, "memoria")
            else:
                t._fin(None, msg[2] or "error")
            self._siguiente()
            return
        if (self._actual is not None and activo() and self._hilo is None
                and (self._proc is None or not self._proc.is_alive())):
            t, self._actual = self._actual, None
            # Un fallo nativo no es necesariamente falta de RAM. Conservar el
            # código de salida para distinguir una violación de acceso de memoria.
            code = self._proc.exitcode if self._proc is not None else None
            pid = self._proc.pid if self._proc is not None else None
            codigo = f"0x{code & 0xffffffff:08X}" if code is not None else "desconocido"
            detalle = (f"El proceso de trabajo se detuvo inesperadamente.\n"
                       f"Tarea: {t.objetivo}\nPID: {pid}\nCódigo de salida: {codigo}")
            if pid is not None:
                from nucleo import diagnostico
                detalle += f"\nDiagnóstico del proceso: {diagnostico.ruta(pid)}"
            self._matar()
            t._fin(None, detalle)
            self._siguiente()


_TRABAJADORES: Dict[str, Trabajador] = {}


def trabajador(nombre: str = "principal") -> Trabajador:
    """«principal» (reconocer, armar la hoja) y «fondo» (composición sugerida): dos procesos,
    así el análisis de fondo no hace esperar al reconocimiento."""
    if nombre not in _TRABAJADORES:
        _TRABAJADORES[nombre] = Trabajador(nombre)
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_TRABAJADORES[nombre].parar)
    return _TRABAJADORES[nombre]


def ejecutar(objetivo: str, *args, nombre: str = "principal", al_avanzar=None, **kwargs):
    """Corre el trabajo y ESPERA sin trabar la ventana (bucle de eventos local; la capa
    «Cargando…» de quien llama come la entrada). Devuelve (resultado, error)."""
    if not activo():                      # sin proceso: aquí mismo, como siempre
        import importlib
        nombre_mod, fn = objetivo.split(":")
        f = getattr(importlib.import_module(nombre_mod), fn)
        try:
            return f(*args, progreso=(lambda *a: al_avanzar(a)) if al_avanzar else None, **kwargs), ""
        except MemoryError:
            return None, "memoria"
    t = Tarea(objetivo, args, kwargs)
    out = {}
    lazo = QtCore.QEventLoop()
    if al_avanzar is not None:
        t.avance.connect(al_avanzar)
    t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
    trabajador(nombre).enviar(t)
    if not t.hecha:
        lazo.exec()
    return out.get("r"), out.get("e", "")
