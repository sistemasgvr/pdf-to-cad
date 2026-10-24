"""fondo_trabajo.py — la imagen de fondo de la hoja, dibujada en el proceso trabajador.

Reporte del usuario 2026-10-23 (36 + 36 mapas de Phoenix: «No responde»): dibujar la hoja
compuesta entera a zoom 3.5 (`fondo_pdf.render_pix`, 115 Mpx) y sus grises tomaba 6–12 s de
una sola llamada a MuPDF en la ventana; Windows la marcaba «No responde». Aquí la MISMA llamada
corre en el proceso trabajador (`ui.comun.proceso`) sobre el mismo PDF con las mismas capas
encendidas (el estado de cada una, por su número: como las teselas): MuPDF da los mismos
píxeles. La imagen (cientos de MB) vuelve por un archivo temporal, no por la cola. Sin proceso
(pruebas, `PDFCAD_PROCESO=0`), sin PDF en disco o si algo falla, la ventana la dibuja como
siempre (`aqui`).

Se usa con las hojas COMPUESTAS de varias piezas (`conviene`): el fondo del editor
(`Main._load_page`, la hoja con la utilidad agregada) y la vista de «Capas de la hoja»
(2026-10-24: el código existía pero nadie lo llamaba).
"""
from __future__ import annotations

import os
import tempfile


def dibujar(ruta, hoja, zoom, ons=(), limite=None, presupuesto=None, grises=True, progreso=None) -> dict:
    """(En el proceso trabajador) la hoja `hoja` de `ruta` como `fondo_pdf.render_pix` (+ `gris`
    si `grises`), a archivos temporales. Devuelve sus rutas y medidas."""
    import fitz
    from hoja import pdf_layers
    from ui.comun import fondo_pdf as F
    if limite:
        F.LIMITE_BYTES = int(limite)               # los de la ventana (las pruebas los bajan)
    if presupuesto:
        F.PRESUPUESTO_PX = int(presupuesto)
    with fitz.open(ruta) as doc:
        pdf_layers.poner_encendidas(doc, ons)
        fondo = F.render_pix(doc[int(hoja)], float(zoom))
        pix = fondo.pix
        buf = pix.samples
        fd, img = tempfile.mkstemp(prefix="pdfcad_fondo", suffix=".rgb")
        with os.fdopen(fd, "wb") as fp:
            fp.write(buf)
        gr = None
        if grises:
            gris = F.gris(buf, pix.width, pix.height, pix.stride)
            fd, gr = tempfile.mkstemp(prefix="pdfcad_fondo", suffix=".gris")
            with os.fdopen(fd, "wb") as fp:
                fp.write(gris.tobytes())
        return dict(img=img, gris=gr, w=pix.width, h=pix.height, stride=pix.stride,
                    escala=fondo.escala, ancho=fondo.ancho, alto=fondo.alto)


def conviene(composite) -> bool:
    """¿Dibujar el fondo en el proceso? Solo hojas compuestas de varias piezas (las que crecen
    sin tope: 36, 72 mapas); una hoja suelta sigue por el camino de siempre."""
    from ui.comun import proceso
    return bool(proceso.activo() and composite is not None and len(composite.pieces) > 1)


def ruta_de(doc) -> str:
    """El PDF de `doc` en disco, sin cambios (lo que abre el proceso), o "" si no lo hay."""
    ruta = getattr(doc, "name", "") or ""
    if not ruta or not os.path.isfile(ruta) or getattr(doc, "is_dirty", False):
        return ""
    return ruta


def en_proceso(doc, hoja, zoom, grises=True, al_avanzar=None):
    """(En la ventana) (QImage, grises o None, escala, ancho, alto) de la hoja dibujada en el
    proceso trabajador, o None (dibujarla aquí, como siempre). Espera sin trabar la ventana
    (`proceso.ejecutar`): quien llama tapa la ventana con la capa «Cargando…»."""
    import numpy as np
    from PySide6 import QtGui
    from hoja import pdf_layers
    from ui.comun import fondo_pdf, proceso
    ruta = ruta_de(doc)
    if not proceso.activo() or not ruta:
        return None
    res, err = proceso.ejecutar("ui.comun.fondo_trabajo:dibujar", ruta, int(hoja), float(zoom),
                                pdf_layers.encendidas(doc), fondo_pdf.LIMITE_BYTES, fondo_pdf.PRESUPUESTO_PX,
                                bool(grises), al_avanzar=al_avanzar)
    if err or not res:
        return None
    try:
        with open(res["img"], "rb") as fp:
            buf = fp.read()
        qimg = QtGui.QImage(buf, res["w"], res["h"], res["stride"], QtGui.QImage.Format_RGB888).copy()
        del buf
        gris = (np.fromfile(res["gris"], dtype=np.uint8).reshape(res["h"], res["w"])
                if res.get("gris") else None)
        return qimg, gris, res["escala"], res["ancho"], res["alto"]
    except (OSError, ValueError):
        return None
    finally:
        for k in ("img", "gris"):
            try:
                if res.get(k):
                    os.remove(res[k])
            except OSError:
                pass


def aqui(page, zoom, grises=True):
    """(QImage, grises o None, escala, ancho, alto) dibujada en la ventana, como siempre."""
    from PySide6 import QtGui
    from ui.comun import fondo_pdf
    fondo = fondo_pdf.render_pix(page, zoom)
    pix = fondo.pix
    buf = bytes(pix.samples)
    qimg = QtGui.QImage(buf, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888).copy()
    gris = fondo_pdf.gris(buf, pix.width, pix.height, pix.stride) if grises else None
    return qimg, gris, fondo.escala, fondo.ancho, fondo.alto
