"""lanzar.py — abre el monitor de rendimiento en OTRO proceso (desde la ventana de la app).

Corre aparte para seguir al día aunque la ventana esté en «No responde» (un diálogo de la misma app se trabaría con
ella). «spawn», como los trabajadores: en el .exe arranca el mismo programa y `freeze_support` lo desvía. Uno a la
vez: si ya está abierto, no se abre otro.
"""
from __future__ import annotations

import multiprocessing as mp

from nucleo import vigilante as V

_proc = {"p": None}


def abierto() -> bool:
    p = _proc["p"]
    return p is not None and p.is_alive()


def abrir(carpeta: str | None = None) -> bool:
    """Abre el monitor sobre la sesión `carpeta` (la de esta app si hay). False si ya estaba abierto."""
    if abierto():
        return False
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=_correr, args=(carpeta or V.carpeta(),), name="pdfcad-monitor", daemon=False)
    p.start()
    _proc["p"] = p
    V.evento("monitor", pid_monitor=p.pid)
    return True


def _correr(carpeta):
    from ui.monitor import monitor_ventana
    monitor_ventana.main(carpeta)
