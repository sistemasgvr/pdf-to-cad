"""Dónde se guardan los perfiles de las cargas (`nucleo/avance_aprendido`): cuánto duró cada etapa la última vez.

En los ajustes de la app (QSettings «pdf-to-cad»/«app», clave `tiempos_carga`, un JSON chico): así la barra de
0 a 100 % ya sabe repartirse desde la segunda vez que se hace algo, también tras cerrar el programa. En memoria
mientras dura la sesión; se escribe al terminar cada carga que duró lo bastante.
"""
from __future__ import annotations

import json

from PySide6 import QtCore

from nucleo import avance_aprendido as AA

CLAVE = "tiempos_carga"
MAX_CARGAS = 120            # cargas distintas que se recuerdan (las más recientes)

_perfiles = None            # {clave de la carga: perfil}, en orden de uso


def _ajustes():
    return QtCore.QSettings("pdf-to-cad", "app")


def _cargar() -> dict:
    global _perfiles
    if _perfiles is None:
        _perfiles = {}
        try:
            datos = json.loads(_ajustes().value(CLAVE, "") or "{}")
            if isinstance(datos, dict):
                _perfiles = {str(k): v for k, v in datos.items() if AA.perfil_valido(v)}
        except (TypeError, ValueError):
            pass
    return _perfiles


def seguidor(texto: str) -> AA.Seguidor:
    """El seguidor de una carga que empieza (`texto` = su título), con lo aprendido de la vez anterior."""
    s = AA.Seguidor(_cargar().get(AA.clave_de(texto)))
    s.carga = AA.clave_de(texto)
    return s


def guardar(s) -> None:
    """Al terminar la carga: su perfil queda para la próxima vez."""
    try:
        perfil = s.cerrar()
        clave = getattr(s, "carga", "")
        if not perfil or not clave:
            return
        perfiles = _cargar()
        perfiles.pop(clave, None)
        perfiles[clave] = perfil
        while len(perfiles) > MAX_CARGAS:
            perfiles.pop(next(iter(perfiles)))
        _ajustes().setValue(CLAVE, json.dumps(perfiles, ensure_ascii=False, separators=(",", ":")))
    except Exception:                                  # noqa: BLE001 — recordar tiempos nunca tumba una carga
        pass


def olvidar() -> None:
    """(pruebas) vuelve a leer de los ajustes."""
    global _perfiles
    _perfiles = None
