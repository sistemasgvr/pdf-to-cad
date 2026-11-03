"""Núcleos y RAM del equipo, sin dependencias, para acotar lotes y cachés (también en Windows)."""
from __future__ import annotations

import os


def recursos() -> dict:
    cpu = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    total = disponible = 0
    try:
        if os.name == "nt":
            import ctypes

            class Memory(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            *[(name, ctypes.c_ulonglong) for name in (
                                "total", "available", "page_total", "page_available",
                                "virtual_total", "virtual_available", "extended")]]

            mem = Memory()
            mem.length = ctypes.sizeof(mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                total, disponible = mem.total, mem.available
        else:
            size = os.sysconf("SC_PAGE_SIZE")
            total = size * os.sysconf("SC_PHYS_PAGES")
            disponible = size * os.sysconf("SC_AVPHYS_PAGES")
    except (OSError, ValueError, AttributeError):
        pass
    return {"cpu_logicos": cpu, "ram_total": total, "ram_disponible": disponible}
