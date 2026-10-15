"""avance.py — «qué se está cargando», dicho desde el código PURO (pedido del usuario 2026-10-14).

Abrir «Capas de la hoja» sobre una hoja compuesta de 36 mapas tardaba ~2 min con un «Cargando…»
mudo. Los pasos largos (leer los vectores, la leyenda, las letras, cada pieza…) avisan aquí su
etapa con `avisar(texto, i, n)`; quien espera la muestra: `escuchar(fn)` (la capa «Cargando…»
de la ventana, o el proceso trabajador, que la manda por su cola). Sin nadie escuchando, no
hace nada. Por hilo: el trabajo de fondo no pisa los avisos de la ventana.

Los avisos se espacian (`CADA_S`): repintar la tarjeta en cada vuelta de un bucle costaría más
que el trabajo. Un texto NUEVO pasa siempre; el mismo texto con otro i/n, cada `CADA_S`.
"""
from __future__ import annotations

import contextlib
import threading
import time
from typing import Callable, Optional

CADA_S = 0.12

_local = threading.local()


@contextlib.contextmanager
def escuchar(fn: Callable[[str, Optional[int], Optional[int]], None]):
    """Mientras dura el bloque, `fn(texto, i, n)` recibe los avisos de este hilo."""
    prev = getattr(_local, "fn", None), getattr(_local, "ultimo", None)
    _local.fn, _local.ultimo = fn, (None, 0.0)
    try:
        yield
    finally:
        _local.fn, _local.ultimo = prev


def avisar(texto: str, i: Optional[int] = None, n: Optional[int] = None) -> None:
    fn = getattr(_local, "fn", None)
    if fn is None:
        return
    previo, cuando = _local.ultimo
    ahora = time.perf_counter()
    if texto == previo and ahora - cuando < CADA_S:
        return
    _local.ultimo = (texto, ahora)
    try:
        fn(texto, i, n)
    except Exception:
        pass                              # un aviso nunca tumba el trabajo


def activo() -> bool:
    return getattr(_local, "fn", None) is not None
