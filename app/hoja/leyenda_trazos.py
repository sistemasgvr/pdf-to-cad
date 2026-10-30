"""leyenda_trazos.py — los trazos que SE VEN en la hoja, como los toma el reconocimiento.

`get_drawings` devuelve la geometría sin recortar: un xref recortado fuera de la vista
(DU06 h.3) o lo que cae en una vista de perfil sigue ahí aunque no se pinte. El
reconocimiento (`recognition.gather_paths`) lo recorta por los clips del PDF y lo
descarta; el resaltado y la leyenda de «Capas de la hoja» (`leyenda_estandar`) hacen lo
mismo con `trazos_visibles` (auditoría 2026-10-07: mismas capas que el reconocimiento en
las 141 hojas de los 4 PDFs de prueba). Sin Qt.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from hoja import pdf_layers
from hoja import pdf_styles
from nucleo import avance
from traduccion.i18n_core import t as _tr
from reconocimiento import recognition
from reconocimiento import recognition_geom as geom


def _rect_poly(pg) -> Optional[Tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) si el polígono de clip es un rectángulo alineado a los ejes."""
    if len(pg) != 4:
        return None
    xs = sorted({round(q[0], 6) for q in pg})
    ys = sorted({round(q[1], 6) for q in pg})
    return (xs[0], ys[0], xs[1], ys[1]) if len(xs) == 2 and len(ys) == 2 else None


def _recortar(path: dict, polys: list, rects: Optional[list] = None) -> Optional[dict]:
    """`geom.clip_path`, con atajo: un trazo que cae entero dentro de clips
    rectangulares (el caso común: el marco de la vista) queda tal cual. `rects` = el
    `_rect_poly` de cada polígono, si ya se calculó (una vez por recorte, no por trazo)."""
    if not polys:
        return path
    r = path.get("rect")
    if r is not None:
        rects = rects if rects is not None else [_rect_poly(pg) for pg in polys]
        if all(b is not None and b[0] <= r.x0 and b[1] <= r.y0 and r.x1 <= b[2] and r.y1 <= b[3]
               for b in rects):
            return path
    return geom.clip_path(path, polys)


def trazos_visibles(page, capas: Optional[Callable[[str], bool]] = None, *, para_reconocimiento=True) -> List[Tuple[dict, dict]]:
    """(trazo de `get_drawings`, lo que se VE de él) de cada trazo de la hoja, como los
    toma `recognition.gather_paths`: recortado por los clips del PDF (marco de la vista,
    XCLIP de un xref, el BBox de cada pieza de la hoja compuesta), sin las astillas del
    recorte ni lo que cae en una vista de perfil (`recognition.profile_view_regions`,
    aquí en la MISMA pasada). El original sirve para decidir de qué utilidad es
    (`letter_paths` se leyó sobre él); el recortado, para dibujar. `capas(nombre)`: solo
    esas (recortar toda la hoja tarda 2–4 s; así, lo que tarda leer sus trazos, 0.5–1.3 s).
    Con todas las capas encendidas. `para_reconocimiento=False` conserva también
    perfiles y fragmentos cortos visibles para poder inspeccionar cualquier vector."""
    avance.avisar(_tr("Recortando lo que se ve de cada capa…"))
    page_rect = page.rect
    clip_stack: Dict[int, list] = {}
    rect_de: Dict[int, object] = {}       # nivel → `_rect_poly` de su recorte (una vez por recorte)
    cand: List[Tuple[dict, dict]] = []
    prof: list = []
    todos = pdf_styles.drawings(page, extended=True)
    n_todos = len(todos)
    for k_av, path in enumerate(todos):
        if k_av % 4000 == 0:
            avance.avisar(_tr("Recortando lo que se ve de cada capa…"), k_av, n_todos)
        lvl = int(path.get("level", 0) or 0)
        if path.get("type") == "clip":
            clip_stack = {lv: pg for lv, pg in clip_stack.items() if lv < lvl}
            clip_stack[lvl] = recognition._clip_polygon(path, page_rect)
            rect_de = {lv: rect_de[lv] for lv in clip_stack if lv in rect_de}
            rect_de[lvl] = _rect_poly(clip_stack[lvl]) if clip_stack[lvl] else None
            continue
        if path.get("type") == "group":
            clip_stack = recognition._cerrar_recortes(clip_stack, lvl)   # pieza fundida, etc.
            rect_de = {lv: rect_de[lv] for lv in clip_stack if lv in rect_de}
            continue
        if not path.get("items"):
            continue
        layer = path.get("layer") or ""
        is_prof = recognition.PROFILE_LAYER_TOKEN in pdf_layers.short_name(layer).upper()
        mine = capas is None or capas(layer)
        if not (mine or is_prof):
            continue
        niveles = [lv for lv, pg in clip_stack.items() if lv < lvl and pg]
        shown = _recortar(path, [clip_stack[lv] for lv in niveles], [rect_de[lv] for lv in niveles])
        if shown is None:
            continue
        if is_prof:
            bb = geom._path_bbox(shown)
            if bb is not None:
                prof.append(bb)
        if not mine or (para_reconocimiento and shown.get("clipped") and recognition._path_length(shown) < recognition.CLIP_SLIVER_PT):
            continue
        cand.append((path, shown))
    regions = recognition._merge_close_boxes(prof, recognition.PROFILE_REGION_PAD_PT) if prof and para_reconocimiento else []
    return [(p, s) for p, s in cand if not (regions and recognition._region_hit(geom._path_bbox(s), regions))]
