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


def _versiones():
    """Versiones de las bibliotecas que más importan (2026-11-13: el .exe del cliente se compiló con
    otras y en el registro no se veía). Sin importarlas: lee los metadatos instalados."""
    import importlib
    from importlib import metadata
    # (paquete, módulo, atributo): en el .exe PyInstaller no siempre copia los metadatos
    cuales = (("pymupdf", "fitz", "VersionBind"), ("numpy", "numpy", "__version__"),
              ("PySide6", "PySide6", "__version__"), ("shapely", "shapely", "__version__"),
              ("ezdxf", "ezdxf", "__version__"), ("opencv-python", "cv2", "__version__"))
    out = []
    for nombre, modulo, attr in cuales:
        try:
            v = metadata.version(nombre)
        except Exception:
            try:
                v = str(getattr(importlib.import_module(modulo), attr))
            except Exception:
                v = "?"
        out.append(f"{nombre} {v}")
    return ", ".join(out)


def activar():
    """Mantener el descriptor abierto: faulthandler lo usa incluso en un fallo de C/Qt."""
    global _archivo
    if _archivo is not None:
        return
    try:
        path = registrar(f"Python {sys.version}\n{_versiones()}", "Inicio de sesión")
        if path:
            _archivo = open(path, "a", encoding="utf-8")
            faulthandler.enable(file=_archivo, all_threads=True)
            _volcado_completo()
    except (OSError, RuntimeError, ValueError):
        pass


_filtro = None          # (el callback debe seguir vivo mientras viva el proceso)


def _volcado_completo(carpeta=None):
    """Windows: ante un fallo nativo (access violation…) el propio proceso escribe `sesion-<pid>.dmp` con TODA la
    memoria (2026-11-21: el mini-volcado de WER solo trae ~8 KB de pila y no deja ver quién dañó la memoria; reporte:
    el programa se cerró solo importando lo reconocido). Devuelve la ruta del .dmp que escribirá, o None.
    Se queda con los 3 últimos (cada uno pesa lo que pesaba el proceso)."""
    global _filtro
    if sys.platform != "win32" or _filtro is not None:
        return None
    import ctypes
    from ctypes import wintypes
    destino = os.path.join(carpeta or os.path.dirname(ruta()), f"sesion-{os.getpid()}.dmp")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dbg = ctypes.WinDLL("dbghelp")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                wintypes.DWORD, wintypes.HANDLE]
    dbg.MiniDumpWriteDump.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID]
    FILTRO = ctypes.WINFUNCTYPE(wintypes.LONG, wintypes.LPVOID)

    class _Info(ctypes.Structure):
        _pack_ = 4                                   # MINIDUMP_EXCEPTION_INFORMATION va empaquetada a 4
        _fields_ = [("hilo", wintypes.DWORD), ("excepcion", wintypes.LPVOID), ("cliente", wintypes.BOOL)]

    def al_fallar(punteros):
        try:
            h = k32.CreateFileW(destino, 0x40000000, 0, None, 2, 0x80, None)
            if h and h != wintypes.HANDLE(-1).value:
                info = _Info(k32.GetCurrentThreadId(), punteros, False)
                # 0x2 = MiniDumpWithFullMemory | 0x4 = WithHandleData | 0x1000 = WithThreadInfo
                dbg.MiniDumpWriteDump(k32.GetCurrentProcess(), os.getpid(), h, 0x2 | 0x4 | 0x1000,
                                      ctypes.byref(info), None, None)
                k32.CloseHandle(h)
        except Exception:
            pass
        return 0                                     # EXCEPTION_CONTINUE_SEARCH: lo demás sigue (WER, faulthandler)

    _filtro = FILTRO(al_fallar)
    k32.SetUnhandledExceptionFilter(_filtro)
    try:                                             # solo los 3 más nuevos
        base = os.path.dirname(destino)
        viejos = sorted((f for f in os.listdir(base) if f.endswith(".dmp")),
                        key=lambda f: os.path.getmtime(os.path.join(base, f)))[:-2]
        for f in viejos:
            os.remove(os.path.join(base, f))
    except OSError:
        pass
    return destino
