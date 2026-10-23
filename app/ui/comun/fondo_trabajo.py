"""fondo_trabajo.py — la imagen de fondo de la hoja, dibujada en el proceso trabajador.

Reporte del usuario 2026-10-23 (36 + 36 mapas de Phoenix: «No responde»): dibujar la hoja
compuesta entera a zoom 3.5 (`fondo_pdf.render_pix`, 115 Mpx) y sus grises tomaba 6–12 s de
una sola llamada a MuPDF en la ventana; Windows la marcaba «No responde». Aquí la MISMA llamada
corre en el proceso trabajador (`ui.comun.proceso`) sobre el mismo PDF con las mismas capas
apagadas: MuPDF da los mismos píxeles. La imagen (cientos de MB) vuelve por un archivo temporal,
no por la cola. Sin proceso (pruebas, `PDFCAD_PROCESO=0`), sin PDF en disco o si algo falla, la
ventana la dibuja como siempre (`None`).
"""
from __future__ import annotations

import os
import tempfile


def dibujar(ruta, hoja, zoom, ocultas=(), limite=None, presupuesto=None, progreso=None) -> dict:
    """(En el proceso trabajador) la hoja `hoja` de `ruta` como `fondo_pdf.render_pix` + `gris`,
    a archivos temporales. Devuelve sus rutas y medidas."""
    import fitz
    from hoja import pdf_layers
    from ui.comun import fondo_pdf as F
    if limite:
        F.LIMITE_BYTES = int(limite)               # los de la ventana (las pruebas los bajan)
    if presupuesto:
        F.PRESUPUESTO_PX = int(presupuesto)
    with fitz.open(ruta) as doc:
        if ocultas:
            pdf_layers.set_hidden(doc, list(ocultas))
        fondo = F.render_pix(doc[int(hoja)], float(zoom))
        pix = fondo.pix
        buf = pix.samples
        gris = F.gris(buf, pix.width, pix.height, pix.stride)
        fd, img = tempfile.mkstemp(prefix="pdfcad_fondo", suffix=".rgb")
        with os.fdopen(fd, "wb") as fp:
            fp.write(buf)
        fd, gr = tempfile.mkstemp(prefix="pdfcad_fondo", suffix=".gris")
        with os.fdopen(fd, "wb") as fp:
            fp.write(gris.tobytes())
        return dict(img=img, gris=gr, w=pix.width, h=pix.height, stride=pix.stride,
                    escala=fondo.escala, ancho=fondo.ancho, alto=fondo.alto)


def en_proceso(doc, hoja, zoom, ocultas):
    """(En la ventana) (QImage, grises, escala, ancho, alto) de la hoja dibujada en el proceso
    trabajador, o None (dibujarla aquí, como siempre)."""
    import numpy as np
    from PySide6 import QtGui
    from ui.comun import fondo_pdf, proceso
    ruta = getattr(doc, "name", "") or ""
    if not proceso.activo() or not ruta or not os.path.isfile(ruta):
        return None
    res, err = proceso.ejecutar("ui.comun.fondo_trabajo:dibujar", ruta, int(hoja), float(zoom),
                                list(ocultas or ()), fondo_pdf.LIMITE_BYTES, fondo_pdf.PRESUPUESTO_PX)
    if err or not res:
        return None
    try:
        with open(res["img"], "rb") as fp:
            buf = fp.read()
        qimg = QtGui.QImage(buf, res["w"], res["h"], res["stride"], QtGui.QImage.Format_RGB888).copy()
        del buf
        gris = np.fromfile(res["gris"], dtype=np.uint8).reshape(res["h"], res["w"])
        return qimg, gris, res["escala"], res["ancho"], res["alto"]
    except (OSError, ValueError):
        return None
    finally:
        for k in ("img", "gris"):
            try:
                os.remove(res[k])
            except OSError:
                pass
