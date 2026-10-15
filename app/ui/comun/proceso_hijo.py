"""proceso_hijo.py — lo que corre DENTRO del proceso de trabajo (sin Qt: el hijo no carga la interfaz).

Ver `proceso.py`. El hijo:
  · baja su prioridad (`BELOW_NORMAL`: la PC y la ventana siguen respondiendo aunque el
    trabajo use un núcleo entero),
  · se pone un TOPE de memoria (Job Object de Windows, `tope_mb`): si un PDF enorme pide más,
    el hijo falla con «memoria» en vez de llevar todo el sistema a la memoria virtual,
  · atiende trabajos en orden (`bucle`): importa `objetivo` («paquete.modulo:funcion»), lo
    llama con `progreso=` (cada aviso va a la cola) y manda el resultado (o el error) y
    cuánta memoria le quedó (`memoria_mb`: el padre lo recicla si creció de más).
"""
from __future__ import annotations

import importlib
import os
import sys
import traceback

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def bajar_prioridad():
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except Exception:
        pass


def memoria_total_mb() -> int:
    """RAM física del equipo (MB); 0 si no se sabe."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return int(m.ullTotalPhys // 2**20)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 2**20)
    except Exception:
        return 0


def poner_tope(tope_mb: int) -> bool:
    """Tope de memoria comprometida del proceso (Windows; en otros sistemas, nada)."""
    if not tope_mb or os.name != "nt":
        return False
    try:
        import ctypes
        import ctypes.wintypes as W

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount",
                                                       "OtherOperationCount", "ReadTransferCount",
                                                       "WriteTransferCount", "OtherTransferCount")]

        class EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        k = ctypes.windll.kernel32
        k.CreateJobObjectW.restype = W.HANDLE
        job = k.CreateJobObjectW(None, None)
        if not job:
            return False
        info = EXT()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info.ProcessMemoryLimit = int(tope_mb) * 2**20
        ok = k.SetInformationJobObject(W.HANDLE(job), JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                       ctypes.byref(info), ctypes.sizeof(info))
        return bool(ok and k.AssignProcessToJobObject(W.HANDLE(job), k.GetCurrentProcess()))
    except Exception:
        return False


def memoria_mb() -> int:
    """Memoria comprometida (privada) de este proceso, en MB; 0 si no se sabe."""
    try:
        if os.name == "nt":
            import ctypes
            import ctypes.wintypes as W

            class PMC(ctypes.Structure):
                _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD)] + [
                    (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                                   "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                                   "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                                   "PagefileUsage", "PeakPagefileUsage")]
            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = W.HANDLE
            k.K32GetProcessMemoryInfo.argtypes = [W.HANDLE, ctypes.POINTER(PMC), W.DWORD]
            c = PMC(); c.cb = ctypes.sizeof(PMC)
            if k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return int(c.PagefileUsage // 2**20)
            return 0
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)
    except Exception:
        return 0


def bucle(entrada, salida, tope_mb: int):
    """Punto de entrada del trabajador (`multiprocessing`, «spawn»): atiende trabajos
    (id, «paquete.modulo:funcion», args, kwargs) hasta recibir None."""
    bajar_prioridad()
    poner_tope(tope_mb)
    while True:
        msg = entrada.get()
        if msg is None:
            return
        tid, objetivo, args, kwargs = msg
        try:
            nombre, fn = objetivo.split(":")
            f = getattr(importlib.import_module(nombre), fn)
            res = f(*args, progreso=lambda *a, tid=tid: salida.put(("avance", tid, a)), **kwargs)
            salida.put(("ok", tid, res, memoria_mb()))
        except MemoryError:
            salida.put(("memoria", tid))
            return
        except BaseException:
            salida.put(("error", tid, traceback.format_exc()))
        finally:
            sys.stdout.flush()


def eco(valor, pasos: int = 0, progreso=None):
    """Trabajo mínimo (pruebas y diagnóstico): avisa `pasos` veces y devuelve `valor`
    con el PID del proceso que lo corrió."""
    for i in range(pasos):
        if progreso is not None:
            progreso(i + 1, pasos)
    return valor, os.getpid()
