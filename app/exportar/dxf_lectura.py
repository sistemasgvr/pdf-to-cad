"""Leer el DXF base avisando cuánto va (pedido del usuario 2026-10-20: la barra de la exportación).

`leer(ruta)` = `ezdxf.readfile(ruta)`: el MISMO documento (abre el archivo igual —codificación de
`dxf_file_info`, `errors="surrogateescape"`— y lo lee con `Drawing.read`, como `readfile`). Si alguien
escucha el avance (`nucleo.avance`) avisa «leer» (bytes ya leídos del archivo, mirados desde otro hilo
cada 0.1 s) y luego «armar» (entidades ya armadas, contando `factory.bind` mientras dura la lectura).
Sin nadie escuchando, o con un DXF binario, es `ezdxf.readfile` tal cual.
"""
from __future__ import annotations

import contextlib
import os
import threading

from nucleo import avance

MUESTREO_S = 0.1


@contextlib.contextmanager
def _contando_entidades(al_armar=None):
    from ezdxf.entities import factory
    from ezdxf.lldxf import loader
    original_cargar, original_bind = loader.load_and_bind_dxf_content, factory.bind
    estado = {"total": 1, "k": 0}

    def cargar(sections, doc):
        if al_armar is not None:
            al_armar()
        estado["total"] = max(1, sum(len(sections[n]) for n in ("TABLES", "CLASSES", "ENTITIES", "BLOCKS",
                                                                 "OBJECTS") if n in sections))
        avance.avisar("armar", 0, estado["total"])
        return original_cargar(sections, doc)

    def bind(entity, doc):
        estado["k"] += 1
        if not estado["k"] & 511:                         # cada 512 (avisar en cada una costaba ~5 %)
            avance.avisar("armar", min(estado["k"], estado["total"]), estado["total"])
        return original_bind(entity, doc)
    loader.load_and_bind_dxf_content, factory.bind = cargar, bind
    try:
        yield
    finally:
        loader.load_and_bind_dxf_content, factory.bind = original_cargar, original_bind


def leer(ruta):
    import ezdxf
    from ezdxf.document import Drawing
    from ezdxf.filemanagement import dxf_file_info
    from ezdxf.lldxf.validator import is_binary_dxf_file, is_dxf_file
    ruta = str(ruta)
    oyente = avance.oyente()
    if oyente is None or is_binary_dxf_file(ruta) or not is_dxf_file(ruta):
        return ezdxf.readfile(ruta)
    info = dxf_file_info(ruta)
    total = max(1, os.path.getsize(ruta))
    with open(ruta, mode="rt", encoding=info.encoding, errors="surrogateescape") as fp:
        fd, listo = fp.fileno(), threading.Event()

        def mirar():                                      # cuánto se leyó (el offset del archivo)
            while not listo.wait(MUESTREO_S):
                try:
                    oyente("leer", min(os.lseek(fd, 0, os.SEEK_CUR), total), total)
                except Exception:                         # noqa: BLE001 (un aviso nunca corta la lectura)
                    return
        hilo = threading.Thread(target=mirar, name="pdfcad-leer-avance", daemon=True)
        hilo.start()
        try:
            with _contando_entidades(al_armar=listo.set):
                doc = Drawing.read(fp)
        finally:
            listo.set()
            hilo.join()
    doc.filename = ruta
    return doc
