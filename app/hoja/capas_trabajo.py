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
    """{layers, leyenda (o None), visibles (nombres de capa con algo que se ve)[, sugeridos]}."""
    import fitz
    from hoja import pdf_styles
    with fitz.open(ruta) as doc:
        with pdf_styles.lectura_unica(doc):
            return leer_doc(doc, hoja, ons, estilos_ocultos, progreso)


def leer_doc(doc, hoja: int, ons: Sequence = (), estilos_ocultos: Sequence[str] = (),
             progreso=None) -> dict:
    """`leer` sobre un documento YA abierto, dentro de su `pdf_styles.lectura_unica` (la usa también
    `interpretar_trabajo`). Al volver, todas las capas quedan encendidas (como las deja `leer`)."""
    from hoja import leyenda_mapa, leyenda_trazos, pdf_layers
    pdf_layers.poner_encendidas(doc, ons)
    doc._pdf_style_hidden = set(estilos_ocultos or ())           # como `set_hidden` en la ventana
    page = doc[int(hoja)]
    layers = pdf_layers.page_layers(doc, int(hoja))
    ley = None
    if any(L.get("source") == "style" for L in layers) and leyenda_mapa.aplica(page):
        ley = leyenda_mapa.leer(doc, page)
    pdf_layers.set_hidden(doc, ())                               # todas encendidas: `_all_drawings`
    visibles = leyenda_trazos.capas_visibles(page)
    # sin capas ni leyenda: qué estilos son la red (`estilos_sugeridos`, 2026-11-14)
    sugeridos, con_sugeridos = None, False
    if any(L.get("source") == "style" for L in layers) and not (ley is not None and ley.filas):
        from hoja import estilos_sugeridos
        con_sugeridos = True
        try:
            sugeridos = estilos_sugeridos.sugerir(page, nombres=(doc.name,))
        except Exception:                                      # noqa: BLE001 — la ventana lo intenta
            con_sugeridos = False
    elif ley is not None and ley.filas and _con_lineas_de_imagen(layers):
        # red en IMAGEN con leyenda: solo la certeza de sus capas (`Sugerencia.capas`; plan 2026-11-18, Tarea 7)
        from hoja import estilos_sugeridos
        con_sugeridos = True
        try:
            sugeridos = estilos_sugeridos.sugerir(page, nombres=(doc.name,), leyenda=ley)
        except Exception:                                      # noqa: BLE001
            con_sugeridos = False
    out = {"layers": layers, "leyenda": ley, "visibles": sorted(visibles)}
    if con_sugeridos:
        out["sugeridos"] = sugeridos
    return out


def trazos(ruta: str, hoja: int, ons: Sequence = (), estilos_ocultos: Sequence[str] = (), para_reconocimiento=True,
           layers=None, progreso=None) -> list:
    """Las MISMAS listas que «Capas de la hoja» leía en la ventana para resaltar (reporte 2026-11-19: elegir una capa
    de una compuesta de 36 mapas con la red en imagen congelaba la ventana, sin aviso): con `para_reconocimiento`, la
    de `layer_dialog_info._all_drawings` (capas de `layers` y de utilidad); si no, la de `_pick_drawings` (todo
    vector visible; los trazos sin capa, con el nombre de su estilo). Todas las capas encendidas."""
    import fitz
    from hoja import leyenda_estandar as le, leyenda_trazos, pdf_layers, pdf_styles
    with fitz.open(ruta) as doc:
        with pdf_styles.lectura_unica(doc):
            pdf_layers.poner_encendidas(doc, ons)
            doc._pdf_style_hidden = set(estilos_ocultos or ())
            pdf_layers.set_hidden(doc, ())
            page = doc[int(hoja)]
            if para_reconocimiento:
                names = {L["name"] for L in layers or ()}
                quiere = le.capas_de_utilidad(layers or [])
                return leyenda_trazos.trazos_visibles(page, lambda n: n in names or quiere(n))
            out = []
            for original, shown in leyenda_trazos.trazos_visibles(page, para_reconocimiento=False):
                name = original.get("layer") or pdf_styles.style_name(original)
                if not original.get("layer"):
                    original = dict(original, layer=name)
                    shown = dict(shown, layer=name)
                out.append((original, shown))
            return out


def _con_lineas_de_imagen(layers) -> bool:
    """¿La hoja trae capas de LÍNEA de red en imagen (`imagen_ejes`)?"""
    from hoja import imagen_ejes
    return any(imagen_ejes.tipo_imagen(L.get("name") or "") == "line" for L in layers or ())
