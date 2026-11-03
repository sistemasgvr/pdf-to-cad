"""Prepara una combinación de planos de fondo (su PDF y su imagen exacta) fuera de la ventana."""
from __future__ import annotations

import os
import tempfile


def preparar(ruta, datos, hoja, zoom, composicion=None, limites=(), ons=(), progreso=None):
    from ui.comun import fondo_trabajo
    nuevo = not ruta
    if nuevo:
        if composicion is not None:
            from hoja.composite_trabajo import materializar
            datos, _layout = materializar(*composicion, progreso=progreso)
        fd, ruta = tempfile.mkstemp(prefix="pdfcad_plano", suffix=".pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(datos)
    try:
        limite, presupuesto = limites or (None, None)
        res = fondo_trabajo.dibujar(ruta, hoja, zoom, ons, limite, presupuesto, progreso=progreso)
        res.update(pdf=ruta, nuevo_pdf=nuevo)
        return res
    except BaseException:
        if nuevo:
            try:
                os.remove(ruta)
            except OSError:
                pass
        raise
