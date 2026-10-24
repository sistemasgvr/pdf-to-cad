"""capas_trabajo.py — lo pesado de «Capas de la hoja», en el proceso trabajador (sin Qt).

Reporte del usuario 2026-10-24 (agregar el alcantarillado de 36 mapas sobre el agua de 36): al
abrir «Capas de la hoja» la ventana leía todos los vectores de la hoja compuesta DOS veces (para
contar las capas y para saber cuáles se ven), su leyenda y sus acometidas; quedaba congelada
tramos de varios segundos (con 12 + 12 mapas: 18 s, en tramos de hasta 4 s). `leer` hace aquí lo
mismo, sobre el mismo PDF con el mismo estado de capas, y devuelve solo lo que el diálogo usa al
abrirse: la lista de capas (`pdf_layers.page_layers`), la leyenda del mapa
(`leyenda_mapa.leer`, si la hoja la tiene) y las capas con algo VISIBLE (`leyenda_trazos.
trazos_visibles` con todas las capas encendidas, como `_all_drawings` del diálogo). Mismos
resultados que leerlo en la ventana (`tests/test_capas_en_proceso.py`); una sola lectura de la
hoja (`pdf_styles.lectura_unica`), y la memoria vuelve al sistema con el proceso.
"""
from __future__ import annotations

from typing import Sequence


def leer(ruta: str, hoja: int, ons: Sequence = (), estilos_ocultos: Sequence[str] = (),
         progreso=None) -> dict:
    """{layers, leyenda (o None), visibles (nombres de capa con algo que se ve)}."""
    import fitz
    from hoja import leyenda_mapa, leyenda_trazos, pdf_layers, pdf_styles
    with fitz.open(ruta) as doc:
        pdf_layers.poner_encendidas(doc, ons)
        doc._pdf_style_hidden = set(estilos_ocultos or ())       # como `set_hidden` en la ventana
        page = doc[int(hoja)]
        with pdf_styles.lectura_unica(doc):
            layers = pdf_layers.page_layers(doc, int(hoja))
            ley = None
            if any(L.get("source") == "style" for L in layers) and leyenda_mapa.aplica(page):
                ley = leyenda_mapa.leer(doc, page)
            pdf_layers.set_hidden(doc, ())                       # todas encendidas: `_all_drawings`
            visibles = {d.get("layer") or "" for d, _s in leyenda_trazos.trazos_visibles(page, None)}
    return {"layers": layers, "leyenda": ley, "visibles": sorted(visibles)}
