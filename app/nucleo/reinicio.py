"""Reiniciar la app cuando no responde, sin perder el avance (2026-11-21, pedido del usuario: «cuando la app no
responda debe haber modo de reiniciar el proceso o que se reinicie solo sin perder el avance»).

Lo hace el MONITOR (otro proceso: sigue vivo aunque la ventana esté trabada):
  1. cierra a la fuerza la ventana trabada y los procesos de trabajo de su sesión (`cerrar`);
  2. abre la app otra vez con `--recuperar <pid>` (`comando`): al arrancar recupera SOLA la última copia
     automática de esa ventana (`ui/ventana/autoguardado`, cada 2 min), sin preguntar.
El avance que se recupera es el del último autoguardado; lo posterior a él no se puede salvar de un proceso trabado.
PURO (sin Qt): `subprocess` y la carpeta de copias."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Iterable, List, Optional

ARGUMENTO = "--recuperar"
ESPERA_CIERRE_S = 10.0


def comando(pid_ventana: Optional[int] = None) -> List[str]:
    """Cómo se abre la app: el .exe, o `python app/main.py` en desarrollo (+ `--recuperar <pid>`)."""
    extra = [ARGUMENTO] + ([str(pid_ventana)] if pid_ventana else [])
    if getattr(sys, "frozen", False):
        return [sys.executable] + extra
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return [sys.executable, main] + extra


def _vivo(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            k.GetExitCodeProcess(h, ctypes.byref(codigo))
            return codigo.value == 259                       # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


vivo = _vivo


def cerrar(pids: Iterable[int], excepto: Iterable[int] = ()) -> List[int]:
    """Cierra a la fuerza esos procesos (y espera a que mueran). → los que siguen vivos."""
    libres = {int(x) for x in excepto} | {os.getpid()}
    pids = [int(p) for p in pids if p and int(p) not in libres]
    for p in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True, timeout=20)
            else:
                os.kill(p, 9)
        except Exception:                                    # noqa: BLE001 — ya no existía
            pass
    fin = time.time() + ESPERA_CIERRE_S
    while time.time() < fin and any(_vivo(p) for p in pids):
        time.sleep(0.2)
    return [p for p in pids if _vivo(p)]


def reiniciar(pid_ventana: int, otros_pids: Iterable[int] = (), excepto: Iterable[int] = (),
              lanzar=None) -> bool:
    """Cierra la ventana `pid_ventana` y sus procesos de trabajo y abre la app recuperando su copia. `lanzar` (para
    pruebas) sustituye a `subprocess.Popen`. True si la app nueva arrancó."""
    vivos = cerrar([pid_ventana, *otros_pids], excepto)
    if pid_ventana in vivos:                                 # la ventana no murió: no se abre otra encima
        return False
    try:
        (lanzar or _abrir)(comando(pid_ventana))
    except Exception:                                        # noqa: BLE001
        return False
    return True


def _abrir(cmd):
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0     # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=flags, close_fds=True)


# ── la copia que se recupera ─────────────────────────────────────────────────────────────────────────────
def ultima_copia(base: str, pid: Optional[int] = None) -> Optional[dict]:
    """La copia automática más reciente de la ventana `pid` (o la más reciente de todas si `pid` es None o no
    tiene). Lee `meta.json` directamente: el candado de la sesión puede seguir tomado si el proceso acaba de morir."""
    mejores = []
    if not os.path.isdir(base):
        return None
    for nombre in os.listdir(base):
        d = os.path.join(base, nombre)
        meta_p = os.path.join(d, "meta.json")
        if not (os.path.isdir(d) and os.path.isfile(meta_p)):
            continue
        if not all(os.path.isfile(os.path.join(d, p)) for p in ("model.json", "page.png")):
            continue
        try:
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        meta["dir"] = d
        mejores.append(meta)
    mejores.sort(key=lambda m: m.get("fecha", 0), reverse=True)
    if pid:
        propias = [m for m in mejores if m.get("pid") == int(pid)]
        if propias:
            return propias[0]
    return mejores[0] if mejores else None
