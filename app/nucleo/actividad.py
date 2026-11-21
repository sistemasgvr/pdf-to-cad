"""Registro de TRABAJO EN CURSO (2026-11-21, pedido del usuario: «cada botón, cada acción debe mostrar un loader»).

Cada cosa que tarda —la capa «Cargando…», un trabajo en otro proceso o hilo, un trabajo por pasos— anota aquí que
empezó y que terminó. La interfaz (`ui/comun/accion_cargando`) usa ese registro para dejar un aro girando en el
control que el usuario pulsó mientras algo de lo que éste lanzó siga en marcha. PURO (sin Qt), seguro entre hilos."""
from __future__ import annotations

import contextlib
import itertools
import threading
from typing import Callable, Dict, List

_lock = threading.Lock()
_vivas: Dict[int, str] = {}
_contador = itertools.count(1)
_oyentes: List[Callable[[str, int, str], None]] = []


def iniciar(nombre: str = "") -> int:
    """Anota que algo empezó → su ficha (para `terminar`)."""
    with _lock:
        ficha = next(_contador)
        _vivas[ficha] = nombre
        oyentes = list(_oyentes)
    for f in oyentes:
        _avisar(f, "inicia", ficha, nombre)
    return ficha


def terminar(ficha) -> None:
    """Anota que terminó (repetirlo, o una ficha desconocida/None, no hace nada)."""
    if ficha is None:
        return
    with _lock:
        nombre = _vivas.pop(ficha, None)
        oyentes = list(_oyentes)
    if nombre is None:
        return
    for f in oyentes:
        _avisar(f, "termina", ficha, nombre)


def _avisar(f, que, ficha, nombre):
    try:
        f(que, ficha, nombre)
    except Exception:                                  # noqa: BLE001 — un oyente roto no debe tumbar el trabajo
        pass


def hay() -> bool:
    return bool(_vivas)


def vivas() -> Dict[int, str]:
    with _lock:
        return dict(_vivas)


def escuchar(f: Callable[[str, int, str], None]) -> Callable[[], None]:
    """`f("inicia"|"termina", ficha, nombre)`; devuelve la función que deja de escuchar."""
    with _lock:
        _oyentes.append(f)

    def dejar():
        with _lock:
            if f in _oyentes:
                _oyentes.remove(f)
    return dejar


@contextlib.contextmanager
def en_curso(nombre: str = ""):
    ficha = iniciar(nombre)
    try:
        yield ficha
    finally:
        terminar(ficha)


def lanzar(objetivo, nombre: str):
    """Un hilo de usuario (IA, ayuda…) que cuenta como trabajo en curso mientras corre: lo lanza una acción
    (botón «Enviar», «Resolver»…) y su aro gira hasta que termina. La ficha se anota AQUÍ, en el hilo que lanza
    (el del clic), para que el aro sea del botón que lo pidió."""
    ficha = iniciar(nombre)

    def correr():
        try:
            objetivo()
        finally:
            terminar(ficha)
    h = threading.Thread(target=correr, name=nombre, daemon=True)
    h.start()
    return h
