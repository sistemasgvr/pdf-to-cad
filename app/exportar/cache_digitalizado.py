"""Caché del PDF DIGITALIZADO para «Exportar DXF» (pedido del usuario 2026-10-17: con un mapa grande,
digitalizar la hoja tarda minutos en cada exportación aunque el PDF no haya cambiado).

El DXF base que da `digitize.main(pdf, dxf, pages=…)` depende solo de los BYTES del PDF, de las hojas
pedidas y del código del pipeline de la raíz (`digitize`, `vector_pipeline`, `raster_pipeline`,
`config`, `detect`…). La clave es la huella de las tres cosas: si coincide, el DXF guardado es el MISMO
que saldría de digitalizar otra vez. Se guardan los `MAX_ARCHIVOS` más recientes (y no más de `MAX_MB`).

Carpeta: %LOCALAPPDATA%/pdf-to-cad/digitalizado (`PDFCAD_CACHE_DIGITALIZADO` la cambia; las pruebas la
mandan a una carpeta temporal). PURO: sin Qt.
"""
from __future__ import annotations

import glob
import hashlib
import os
import shutil
import sys
import tempfile

MAX_ARCHIVOS = 4
MAX_MB = 2048
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def carpeta() -> str:
    d = os.environ.get("PDFCAD_CACHE_DIGITALIZADO")
    if not d:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        d = os.path.join(base, "pdf-to-cad", "digitalizado")
    os.makedirs(d, exist_ok=True)
    return d


def version_codigo() -> str:
    """Huella del código que digitaliza: en el .exe, la versión y el propio ejecutable; desde el
    código fuente, los .py del pipeline (la raíz del repositorio)."""
    from nucleo.model import VERSION
    h = hashlib.sha1(VERSION.encode("utf-8"))
    if getattr(sys, "frozen", False):
        st = os.stat(sys.executable)
        h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        return h.hexdigest()
    for ruta in sorted(glob.glob(os.path.join(_RAIZ, "*.py"))):
        with open(ruta, "rb") as f:
            h.update(os.path.basename(ruta).encode("utf-8"))
            h.update(f.read())
    return h.hexdigest()


def clave(pdf_path: str, pages) -> str:
    """Huella de (bytes del PDF, hojas, código del pipeline)."""
    h = hashlib.sha1()
    with open(pdf_path, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    h.update(repr(None if pages is None else sorted(int(p) for p in pages)).encode())
    h.update(version_codigo().encode())
    return h.hexdigest()


def _ruta(c: str) -> str:
    return os.path.join(carpeta(), c + ".dxf")


def buscar(c: str | None) -> str | None:
    """Ruta del DXF guardado con esa clave, o None. Marca el uso (para quedarse con los recientes)."""
    if not c:
        return None
    r = _ruta(c)
    if not os.path.isfile(r):
        return None
    try:
        os.utime(r, None)
    except OSError:
        pass
    return r


def guardar(c: str | None, dxf_path: str) -> None:
    """Copia `dxf_path` a la caché con la clave `c` (escritura atómica) y deja solo los recientes."""
    if not c or not os.path.isfile(dxf_path):
        return
    destino = _ruta(c)
    tmp = destino + ".part"
    shutil.copyfile(dxf_path, tmp)
    os.replace(tmp, destino)
    _recortar()


def _recortar() -> None:
    archivos = sorted(glob.glob(os.path.join(carpeta(), "*.dxf")), key=os.path.getmtime, reverse=True)
    total = 0
    for i, r in enumerate(archivos):
        total += os.path.getsize(r)
        if i >= MAX_ARCHIVOS or total > MAX_MB * 1024 * 1024:
            try:
                os.remove(r)
            except OSError:
                pass
