"""Un paso pesado en OTRO hilo sin trabar la ventana (pedido del usuario 2026-10-17: al exportar un
proyecto grande la ventana quedaba «No responde» minutos leyendo y guardando el DXF).

`ejecutar(host, fn, texto)` corre `fn()` en un hilo y espera con un bucle de eventos local mientras
la capa «Cargando…» (`busy`) tapa `host` (come la entrada, así nadie cambia el modelo a medias).
Con `cancelable=True` la capa muestra «Cancelar»: se deja de esperar y el resultado se descarta (el
hilo termina solo; Python no puede cortarlo a la mitad). Devuelve (resultado, error, cancelado).

Solo para trabajo que no toca la interfaz (ezdxf: leer/guardar un documento, copiar archivos).
"""
from __future__ import annotations

import threading
import traceback

from PySide6 import QtCore

from ui.comun import busy


class _Aviso(QtCore.QObject):
    listo = QtCore.Signal()


def ejecutar(host, fn, texto: str, detalle: str = "", cancelable: bool = False):
    out = {}
    lazo = QtCore.QEventLoop()
    aviso = _Aviso()
    aviso.listo.connect(lazo.quit, QtCore.Qt.QueuedConnection)
    estado = {"cancelado": False, "listo": False}

    def correr():
        try:
            out["r"] = fn()
        except BaseException as e:                       # noqa: BLE001 (se informa a quien llama)
            out["e"] = f"{e}\n\n{traceback.format_exc()}"
        finally:
            estado["listo"] = True
            aviso.listo.emit()

    def cancelar():
        estado["cancelado"] = True
        lazo.quit()

    ov = busy.overlay_for(host) if host is not None else None
    if ov is not None:
        ov.begin(texto, detalle, cancel=cancelar if cancelable else None)
    try:
        hilo = threading.Thread(target=correr, name="pdfcad-en-hilo", daemon=True)
        hilo.start()
        if not estado["listo"]:
            lazo.exec()
        if not estado["cancelado"]:
            hilo.join()
    finally:
        if ov is not None:
            ov.end()
    if estado["cancelado"]:
        return None, "", True
    return out.get("r"), out.get("e", ""), False
