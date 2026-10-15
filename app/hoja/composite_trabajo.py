"""composite_trabajo.py — materializar la hoja compuesta como trabajo de fondo (PURO).

Lo que hacía `Main._build_composite_doc` con los PDF de origen (movido tal cual): capas
apagadas en cada origen, puentes, `build_document` y el esquema de piezas del minimapa.
Corre en el proceso trabajador (`ui.comun.proceso`, pedido del usuario 2026-10-14): con 18–36
piezas tardaba 7–28 s con la ventana trabada y dejaba la memoria ocupada.
"""
from __future__ import annotations

from typing import Dict, List, Sequence
from nucleo import avance
from traduccion.i18n_core import t as _tr


def materializar(comp_dict: dict, fuentes: Sequence[bytes], ocultas: Dict[str, list],
                 nombres: Sequence[str], progreso=None):
    """(bytes del PDF de UNA hoja, esquema `piece_layout`)."""
    import fitz
    from hoja import composite as composite_mod
    from hoja import pdf_layers as _pdf_layers
    avisar = progreso or (lambda *a: None)
    comp = composite_mod.Composite.from_dict(comp_dict)
    docs = [fitz.open(stream=data, filetype="pdf") for data in fuentes]
    try:
        for i, d in enumerate(docs):      # capas apagadas: sin trazos ni anclajes
            _pdf_layers.set_hidden(d, ocultas.get(str(i), ()))
        avisar("puentes")
        bridges = composite_mod.compute_bridges(comp, docs)
        avisar("armar")
        built = composite_mod.build_document(comp, docs, ocultas, bridges)
        avance.avisar(_tr("Guardando la hoja compuesta…"))
        data = built.tobytes(deflate=True); built.close()
        sizes = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)  # noqa: E731
        layout: List = composite_mod.piece_layout(comp, sizes, list(nombres))
    finally:
        for d in docs: d.close()
    return data, layout
