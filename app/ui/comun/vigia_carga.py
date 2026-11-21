"""Vigía de las cargas: la tarjeta «Cargando…» se sigue pintando aunque el trabajo no avise.

Pedido del usuario (2026-11-16): «evitar que el programa se quede en No responde… si no, el usuario cree que se
quedó bugeado». Un trabajo en el hilo de la ventana solo repinta la tarjeta cuando avisa (`nucleo.avance`); entre
un aviso y otro la barra quedaba quieta. Aquí un hilo mira las tarjetas activas y, si alguna lleva `QUIETA_S` sin
pintarse, pide al intérprete que la pinte EN el hilo de la ventana, en cuanto éste llegue a su próxima instrucción
de Python (`Py_AddPendingCall`). Solo PINTA la tarjeta: no atiende eventos (ni entrada, ni temporizadores), así
que nada de la aplicación corre a destiempo.

Lo que NO puede: un cálculo largo dentro de una biblioteca en C que no suelta el intérprete (PyMuPDF dibujando o
leyendo una hoja enorme) no deja correr nada hasta que vuelve; para eso el trabajo pesado va en otro proceso
(`ui/comun/proceso`). `sin_fantasma()` quita además el «(No responde)» de Windows: mientras trabaja, la ventana
conserva lo último pintado (la tarjeta con su barra) en vez de ponerse blanca.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import weakref

QUIETA_S = 0.25             # una tarjeta sin pintarse este tiempo → se pinta desde aquí
MIRAR_S = 0.1
# Con una de estas funciones de Python en la pila, la ventana está pintando o midiendo: no se pinta encima (se
# reintenta al rato).
_PINTANDO = frozenset((
    "paintEvent", "paint", "drawBackground", "drawForeground", "drawItems", "pump", "repaint", "grab", "render",
    "pixmap", "scaledPixmap", "actualSize", "boundingRect", "shape", "sizeHint", "minimumSizeHint", "resizeEvent",
    "showEvent", "hideEvent", "_pintar_marcas"))
# …y con una de éstas, depende del evento que reparte (un clic que lanzó la carga no estorba; un repintado sí)
_REPARTIENDO = frozenset(("event", "eventFilter", "viewportEvent"))
_EVENTOS_DE_PINTAR = None

_tarjetas = weakref.WeakSet()
_hay = threading.Event()
_hilo = None
_pendiente = False
_apagado = os.environ.get("PDFCAD_VIGIA", "1") == "0"


def _eventos_de_pintar():
    global _EVENTOS_DE_PINTAR
    if _EVENTOS_DE_PINTAR is None:
        from PySide6.QtCore import QEvent
        _EVENTOS_DE_PINTAR = frozenset((
            QEvent.Paint, QEvent.UpdateRequest, QEvent.Resize, QEvent.Move, QEvent.Show, QEvent.Hide,
            QEvent.LayoutRequest, QEvent.Polish, QEvent.PolishRequest, QEvent.WindowStateChange, QEvent.Expose,
            QEvent.GraphicsSceneResize, QEvent.StyleChange, QEvent.FontChange, QEvent.PaletteChange))
    return _EVENTOS_DE_PINTAR


def importando_en_la_pila() -> bool:
    """¿El hilo está EN MEDIO de un `import`? (2026-11-21: el programa se cerraba solo —access violation siempre en
    `python314.dll +0x2ad5ef`, con el hilo de la ventana dentro de `shibokensupport.feature.feature_import` y el vigía
    activo— porque el vigía corría Python (pintar la tarjeta) a mitad de un import: PySide envuelve `__import__`, y
    ese envoltorio no soporta que otro import / código de Qt corra en medio. Nada se pinta desde el vigía con un
    import a medias; se reintenta al rato.)"""
    f = sys._getframe(1)
    while f is not None:
        c = f.f_code
        if (c.co_name in ("feature_import", "__import__", "_find_and_load", "_handle_fromlist", "import_module")
                or c.co_filename.startswith("<frozen importlib") or "shibokensupport" in c.co_filename):
            return True
        f = f.f_back
    return False


def pintando_en_la_pila() -> bool:
    from PySide6.QtCore import QEvent
    if importando_en_la_pila():
        return True
    f = sys._getframe(1)
    while f is not None:
        nombre = f.f_code.co_name
        if nombre in _PINTANDO:
            return True
        if nombre in _REPARTIENDO:
            try:
                eventos = [v for v in f.f_locals.values() if isinstance(v, QEvent)]
                if not eventos or any(e.type() in _eventos_de_pintar() for e in eventos):
                    return True
            except Exception:                          # noqa: BLE001 — ante la duda, no pintar
                return True
        f = f.f_back
    return False


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
def _en_la_ventana(_arg):
    """Corre en el hilo de la ventana, entre dos instrucciones de Python."""
    global _pendiente
    _pendiente = False
    try:
        if importando_en_la_pila():                    # a mitad de un import: no se corre nada de Qt (se reintenta)
            return 0
        for tarjeta in list(_tarjetas):
            tarjeta.pintar_desde_el_vigia()
    except BaseException:                              # noqa: BLE001 — nunca tumba el trabajo en curso
        pass
    return 0


def _mirar():
    global _pendiente
    pedir = ctypes.pythonapi.Py_AddPendingCall
    pedir.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    pedir.restype = ctypes.c_int
    while True:
        _hay.wait()
        time.sleep(MIRAR_S)
        try:
            vivas = [t for t in list(_tarjetas) if t.vigilada()]
            if not vivas:
                _hay.clear()
                if any(t.vigilada() for t in list(_tarjetas)):      # (una empezó justo ahora)
                    _hay.set()
                continue
            ahora = time.perf_counter()
            if not _pendiente and any(ahora - t.latido > QUIETA_S for t in vivas):
                _pendiente = True
                if pedir(_en_la_ventana, None) != 0:
                    _pendiente = False
        except Exception:                              # noqa: BLE001
            _pendiente = False


def vigilar(tarjeta) -> None:
    """`tarjeta` tiene `vigilada()`, `latido` (cuándo se pintó) y `pintar_desde_el_vigia()`."""
    global _hilo
    if _apagado:
        return
    _tarjetas.add(tarjeta)
    if _hilo is None:
        _hilo = threading.Thread(target=_mirar, name="pdfcad-vigia-carga", daemon=True)
        _hilo.start()
    _hay.set()


def sin_fantasma() -> None:
    """Windows deja de cambiar la ventana por su copia blanca «(No responde)» cuando tarda en atender."""
    try:
        if os.name == "nt":
            ctypes.windll.user32.DisableProcessWindowsGhosting()
    except Exception:                                  # noqa: BLE001
        pass
