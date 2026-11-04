"""Registro local de excepciones y fallos nativos, también en los procesos hijos."""
import datetime
import faulthandler
import os
import sys
import threading

_archivo = None
_lock = threading.Lock()


def resumen(error):
    lineas = [s.strip() for s in str(error).splitlines() if s.strip()]
    if not lineas:
        return "Error sin detalle"
    return lineas[-1] if lineas[0].startswith("Traceback") else lineas[0]


def ruta(pid=None):
    base = os.environ.get("PDFCAD_DIAGNOSTICOS") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "pdf-to-cad", "diagnosticos")
    return os.path.join(base, f"sesion-{pid if pid is not None else os.getpid()}.log")


def registrar(detalle, contexto="Error"):
    """No propagar errores del propio registro (p. ej., disco lleno)."""
    path = ruta()
    try:
        with _lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n{datetime.datetime.now().astimezone().isoformat()} · {contexto}\n{detalle}\n")
    except (OSError, ValueError):
        return None
    return path


def activar():
    """Mantener el descriptor abierto: faulthandler lo usa incluso en un fallo de C/Qt."""
    global _archivo
    if _archivo is not None:
        return
    try:
        path = registrar(f"Python {sys.version}", "Inicio de sesión")
        if path:
            _archivo = open(path, "a", encoding="utf-8")
            faulthandler.enable(file=_archivo, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        pass
