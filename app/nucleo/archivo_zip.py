"""Leer y escribir el .digproj (un zip) POR BLOQUES, avisando cuánto va (PURO: sin Qt).

Pedido del usuario 2026-10-20 (barra de carga precisa al abrir y guardar un proyecto grande: AGUA 2 lleva
~64 MB entre la imagen de la hoja y los PDF). `zipfile` lee y escribe cada archivo de una vez; aquí se hace
en bloques de `BLOQUE` y cada bloque avisa por `nucleo.avance` («i de n» bytes). El contenido es EL MISMO que
con `ZipFile.read` / `writestr` (mismo ZipInfo, mismo compresor: deflate no cambia por partir la entrada;
lo comprueba `tests/test_barras_de_carga.py`).
"""
from __future__ import annotations

import time
import zipfile

from nucleo import avance

BLOQUE = 1 << 20


def escribir(ruta, entradas, clave="comprimir"):
    """Escribe el zip `ruta` con `entradas` = [(nombre, bytes | str)] (en ese orden), como `writestr` con
    ZIP_DEFLATED."""
    datos = [(n, d.encode("utf-8") if isinstance(d, str) else d) for n, d in entradas]
    total = sum(len(d) for _n, d in datos) or 1
    hecho = 0
    avance.avisar(clave, 0, total)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, d in datos:
            zinfo = zipfile.ZipInfo(filename=nombre, date_time=time.localtime(time.time())[:6])
            zinfo.compress_type = z.compression
            zinfo._compresslevel = z.compresslevel
            zinfo.external_attr = 0o600 << 16           # como `writestr` con un nombre
            zinfo.file_size = len(d)
            with z.open(zinfo, mode="w") as dest:
                vista = memoryview(d)
                for k in range(0, len(d), BLOQUE):
                    dest.write(vista[k:k + BLOQUE])
                    hecho += min(BLOQUE, len(d) - k)
                    avance.avisar(clave, hecho, total)
    return total


def leer(ruta, nombres=None, clave="leer"):
    """{nombre: bytes} de los archivos del zip (`nombres` = cuáles; None = todos)."""
    out = {}
    with zipfile.ZipFile(ruta) as z:
        infos = [i for i in z.infolist() if nombres is None or i.filename in nombres]
        total = sum(i.file_size for i in infos) or 1
        hecho = 0
        avance.avisar(clave, 0, total)
        for info in infos:
            partes = []
            with z.open(info) as f:
                while True:
                    b = f.read(BLOQUE)
                    if not b:
                        break
                    partes.append(b)
                    hecho += len(b)
                    avance.avisar(clave, hecho, total)
            out[info.filename] = b"".join(partes)
    return out
