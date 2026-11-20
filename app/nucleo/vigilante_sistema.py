"""vigilante_sistema.py — memoria y CPU de este proceso y de TODOS sus descendientes (sin psutil: ctypes de Windows).

Lo usa `nucleo/vigilante.py` (la guardia de la ventana, cada `SISTEMA_S`, y cada trabajo al empezar y terminar).
En otros sistemas devuelve lo mínimo (sin descendientes).
"""
from __future__ import annotations

import os
import time
from typing import Dict, List

_NT = os.name == "nt"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _mb(b) -> float:
    return round(b / 2**20, 1)


if _NT:
    import ctypes
    import ctypes.wintypes as W

    class _PE(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD),
                    ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", W.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                           "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                           "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                           "PagefileUsage", "PeakPagefileUsage")]

    class _MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    _k = ctypes.windll.kernel32
    _k.CreateToolhelp32Snapshot.restype = W.HANDLE
    _k.OpenProcess.restype = W.HANDLE
    _k.GetCurrentProcess.restype = W.HANDLE
    _k.K32GetProcessMemoryInfo.argtypes = [W.HANDLE, ctypes.POINTER(_PMC), W.DWORD]
    _k.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    _k.CloseHandle.argtypes = [W.HANDLE]

    def _memoria(h):
        c = _PMC(); c.cb = ctypes.sizeof(_PMC)
        if _k.K32GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return c
        return None

    def _cpu_s(h) -> float:
        a, b, kern, user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
        if not _k.GetProcessTimes(h, ctypes.byref(a), ctypes.byref(b), ctypes.byref(kern), ctypes.byref(user)):
            return 0.0
        t = lambda f: (f.dwHighDateTime << 32 | f.dwLowDateTime) / 1e7
        return t(kern) + t(user)

    def _arbol():
        """{pid: (ppid, exe, hilos)} de todos los procesos del equipo."""
        snap = _k.CreateToolhelp32Snapshot(0x2, 0)
        out = {}
        if not snap or snap == W.HANDLE(-1).value:
            return out
        e = _PE(); e.dwSize = ctypes.sizeof(_PE)
        ok = _k.Process32First(snap, ctypes.byref(e))
        while ok:
            out[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile.decode("mbcs", "replace"), e.cntThreads)
            ok = _k.Process32Next(snap, ctypes.byref(e))
        _k.CloseHandle(snap)
        return out


def memoria_propia_mb() -> float:
    """Memoria privada (comprometida) de este proceso, MB."""
    try:
        if _NT:
            c = _memoria(_k.GetCurrentProcess())
            return _mb(c.PagefileUsage) if c else 0.0
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:
        return 0.0


def memoria_pico_mb() -> float:
    try:
        if _NT:
            c = _memoria(_k.GetCurrentProcess())
            return _mb(c.PeakPagefileUsage) if c else 0.0
    except Exception:
        pass
    return 0.0


def ram_equipo() -> Dict[str, float]:
    try:
        if _NT:
            m = _MS(); m.dwLength = ctypes.sizeof(_MS)
            _k.GlobalMemoryStatusEx(ctypes.byref(m))
            return {"ram_total_mb": _mb(m.ullTotalPhys), "ram_libre_mb": _mb(m.ullAvailPhys),
                    "ram_uso_pct": int(m.dwMemoryLoad)}
    except Exception:
        pass
    return {}


def descendientes(arbol, raiz: int) -> List[int]:
    hijos: Dict[int, list] = {}
    for pid, (ppid, _exe, _h) in arbol.items():
        hijos.setdefault(ppid, []).append(pid)
    out, pila = [], [raiz]
    while pila:
        for c in hijos.get(pila.pop(), []):
            if c != raiz and c not in out:
                out.append(c)
                pila.append(c)
    return out


class Medidor:
    """`medir()` → memoria y CPU de este proceso y de sus descendientes; el CPU % es desde la medición anterior
    (100 % = un núcleo entero)."""

    def __init__(self, raiz: int | None = None):
        self.raiz = raiz or os.getpid()
        self._antes: Dict[int, tuple] = {}

    def medir(self) -> dict:
        out = ram_equipo()
        if not _NT:
            out["procesos"] = [{"pid": self.raiz, "priv_mb": memoria_propia_mb()}]
            return out
        try:
            arbol = _arbol()
        except Exception:
            arbol = {}
        pids = [self.raiz] + descendientes(arbol, self.raiz)
        ahora = time.perf_counter()
        procesos, vistos = [], {}
        for pid in pids:
            h = _k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                continue
            try:
                c = _memoria(h)
                cpu = _cpu_s(h)
            finally:
                _k.CloseHandle(h)
            ant = self._antes.get(pid)
            pct = round(100.0 * (cpu - ant[1]) / (ahora - ant[0]), 1) if ant and ahora > ant[0] else None
            vistos[pid] = (ahora, cpu)
            ppid, exe, hilos = arbol.get(pid, (0, "", 0))
            procesos.append({"pid": pid, "ppid": ppid, "exe": exe, "hilos": hilos,
                             "ws_mb": _mb(c.WorkingSetSize) if c else None,
                             "priv_mb": _mb(c.PagefileUsage) if c else None,
                             "pico_mb": _mb(c.PeakPagefileUsage) if c else None,
                             "cpu_s": round(cpu, 2), "cpu_pct": pct})
        self._antes = vistos
        out["procesos"] = procesos
        return out
