"""capas_previas.py — «Capas de la hoja» de una hoja compuesta: lo pesado, leído en el proceso trabajador.

Ver `hoja.capas_trabajo` (pedido del usuario 2026-10-24: agregar una utilidad de 36 mapas sobre
otra dejaba la ventana congelada al abrir este paso). `leer(doc, hoja, zoom)` corre en el proceso
la lista de capas, la leyenda del mapa y qué capas se ven, y dibuja ahí también la imagen de la hoja
(`fondo_trabajo`); la ventana espera sin trabarse bajo la capa «Cargando…» que pone quien llama.
La leyenda queda en la caché del documento (`leyenda_mapa.leer` la encuentra: mismo objeto que
habría leído aquí). Sin proceso, sin el PDF en disco o si algo falla → None: el diálogo lo lee en
la ventana, como siempre.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Previa:
    hoja: int
    layers: list                       # `pdf_layers.page_layers`
    visibles: frozenset                # capas con algo que se ve (todas encendidas)
    encendidas: tuple                  # estado de las capas con que se dibujó `imagen`
    imagen: Optional[tuple] = None     # (QImage, escala, ancho, alto) a `zoom`, o None


def leer(doc, hoja: int, zoom: float, al_avanzar=None) -> Optional[Previa]:
    from hoja import pdf_layers
    from ui.comun import fondo_trabajo, proceso
    ruta = fondo_trabajo.ruta_de(doc)
    if not proceso.activo() or not ruta:
        return None
    res, err = proceso.ejecutar("hoja.capas_trabajo:leer", ruta, int(hoja), pdf_layers.encendidas(doc),
                                sorted(getattr(doc, "_pdf_style_hidden", None) or ()), al_avanzar=al_avanzar)
    if err or not res:
        return None
    if res.get("leyenda") is not None:
        doc.__dict__.setdefault("_pdfcad_leyenda_mapa", {}).setdefault(int(hoja), res["leyenda"])
    img = fondo_trabajo.en_proceso(doc, hoja, zoom, grises=False, al_avanzar=al_avanzar)
    return Previa(int(hoja), res["layers"], frozenset(res["visibles"]), pdf_layers.encendidas(doc),
                  None if img is None else (img[0], img[2], img[3], img[4]))
