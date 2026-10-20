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
import json
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
    for r in glob.glob(os.path.join(carpeta(), "*.ext.json")):     # recuadros sin su DXF
        if not os.path.isfile(r[:-len(".ext.json")] + ".dxf"):
            try:
                os.remove(r)
            except OSError:
                pass


# ── Recuadro del plano base (2026-10-19): encuadrar la vista del DXF medía las ~600 mil entidades del
# plano en CADA exportación (~38 s con el mapa de 16 761 utilidades, sobre todo por los textos). Con el
# mismo DXF base el recuadro es el mismo: se guarda junto a él (números exactos: JSON escribe `repr`).

def _ruta_recuadro(c: str) -> str:
    return os.path.join(carpeta(), c + ".ext.json")


def guardar_recuadro(c: str | None, minimo, maximo) -> None:
    """Recuadro (mínimo, máximo; tuplas x, y, z) del DXF base guardado con la clave `c`; (None, None) =
    plano sin nada que medir."""
    if not c or not os.path.isfile(_ruta(c)):
        return
    datos = {"min": None if minimo is None else [float(v) for v in minimo],
             "max": None if maximo is None else [float(v) for v in maximo]}
    destino = _ruta_recuadro(c)
    tmp = destino + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    os.replace(tmp, destino)


def leer_recuadro(c: str | None):
    """(mínimo, máximo) guardado para la clave `c` (cada uno tupla o None), o None si no hay o no vale."""
    if not c or not os.path.isfile(_ruta(c)):
        return None
    try:
        with open(_ruta_recuadro(c), encoding="utf-8") as f:
            datos = json.load(f)
        mn, mx = datos["min"], datos["max"]
        if (mn is None) != (mx is None) or (mn is not None and (len(mn) != 3 or len(mx) != 3)):
            return None
        return (None, None) if mn is None else (tuple(float(v) for v in mn), tuple(float(v) for v in mx))
    except (OSError, ValueError, KeyError, TypeError):
        return None
