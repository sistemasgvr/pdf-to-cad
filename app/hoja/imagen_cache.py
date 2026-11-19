"""Caché EN DISCO de los ejes de una hoja con la red en imagen (PURO: sin Qt).

Pedido del usuario (2026-11-19, «revisar los tiempos de carga»): leer la imagen de una hoja de Phoenix «QS SD» y sacar
sus ejes tarda ~30 s (esqueleto, paleta, rejillas…); una compuesta de 36 mapas, minutos aunque vaya en procesos, y se
repetía en CADA apertura del proyecto o reinicio de la app (la memoria de `imagen_compuesta.memo` es del proceso).

Lo calculado depende SOLO de la hoja (su huella: contenido, caja y bytes de sus imágenes, `imagen_compuesta._huella`)
y del código que lee la imagen (`hoja/imagen_*.py`, `version_codigo`). Con las dos iguales, lo guardado es lo MISMO que
saldría de calcularlo otra vez. Se guardan los más recientes hasta `MAX_MB`.

Carpeta: %LOCALAPPDATA%/pdf-to-cad/ejes_imagen (`PDFCAD_CACHE_EJES_IMAGEN` la cambia; las pruebas la mandan a una
carpeta temporal; vacía = sin caché). Un archivo roto o ilegible = como si no estuviera.
"""
from __future__ import annotations

import glob
import hashlib
import os
import pickle
import sys
import tempfile

MAX_MB = 1024
_AQUI = os.path.dirname(os.path.abspath(__file__))
_VERSION: str | None = None


def carpeta() -> str | None:
    d = os.environ.get("PDFCAD_CACHE_EJES_IMAGEN")
    if d is None:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        d = os.path.join(base, "pdf-to-cad", "ejes_imagen")
    if not d:
        return None
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


def version_codigo() -> str:
    """Huella del código que lee la imagen: en el .exe, la versión y el propio ejecutable; desde el código fuente,
    los `hoja/imagen_*.py` y `hoja/pdf_styles.py`."""
    global _VERSION
    if _VERSION is None:
        from nucleo.model import VERSION
        h = hashlib.sha1(VERSION.encode("utf-8"))
        if getattr(sys, "frozen", False):
            st = os.stat(sys.executable)
            h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        else:
            for ruta in sorted(glob.glob(os.path.join(_AQUI, "imagen_*.py")) + [os.path.join(_AQUI, "pdf_styles.py")]):
                with open(ruta, "rb") as f:
                    h.update(os.path.basename(ruta).encode("utf-8"))
                    h.update(f.read())
        _VERSION = h.hexdigest()
    return _VERSION


def _ruta(clave: str) -> str | None:
    d = carpeta()
    if d is None:
        return None
    h = hashlib.sha1((clave + "|" + version_codigo()).encode("utf-8")).hexdigest()
    return os.path.join(d, h + ".pkl")


def leer(clave: str):
    """Lo guardado con esa clave (o None)."""
    r = _ruta(clave)
    if r is None or not os.path.isfile(r):
        return None
    try:
        with open(r, "rb") as f:
            v = pickle.load(f)
        os.utime(r, None)
        return v
    except Exception:
        return None


def guardar(clave: str, valor) -> None:
    r = _ruta(clave)
    if r is None:
        return
    tmp = r + ".%d.tmp" % os.getpid()
    try:
        with open(tmp, "wb") as f:
            pickle.dump(valor, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, r)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return
    _recortar(os.path.dirname(r))


def _recortar(d: str) -> None:
    """Deja los más recientes que entran en `MAX_MB`."""
    try:
        archivos = sorted((os.stat(p).st_mtime, os.path.getsize(p), p) for p in glob.glob(os.path.join(d, "*.pkl")))
    except OSError:
        return
    total = sum(s for _t, s, _p in archivos)
    for _t, s, p in archivos:
        if total <= MAX_MB * 1024 * 1024:
            break
        try:
            os.remove(p)
            total -= s
        except OSError:
            pass
