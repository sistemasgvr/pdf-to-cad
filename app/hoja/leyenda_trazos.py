"""leyenda_trazos.py — los trazos que SE VEN en la hoja, como los toma el reconocimiento.

`get_drawings` devuelve la geometría sin recortar: un xref recortado fuera de la vista
(DU06 h.3) o lo que cae en una vista de perfil sigue ahí aunque no se pinte. El
reconocimiento (`recognition.gather_paths`) lo recorta por los clips del PDF y lo
descarta; el resaltado y la leyenda de «Capas de la hoja» (`leyenda_estandar`) hacen lo
mismo con `trazos_visibles` (auditoría 2026-10-07: mismas capas que el reconocimiento en
las 141 hojas de los 4 PDFs de prueba). Sin Qt.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from hoja import pdf_layers
from hoja import pdf_styles
from hoja import recorte_lotes
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


def _recortar(path: dict, polys: list, rects: Optional[list] = None, bounds=None) -> Optional[dict]:
    """`geom.clip_path`, con atajo: un trazo que cae entero dentro de clips
    rectangulares (el caso común: el marco de la vista) queda tal cual. `rects` = el
    `_rect_poly` de cada polígono, si ya se calculó (una vez por recorte, no por trazo)."""
    if not polys:
        return path
    r = path.get("rect")
    if r is not None:
        if (bounds is not None and r.x0 <= r.x1 and r.y0 <= r.y1
                and all(math.isfinite(v) for v in (r.x0, r.y0, r.x1, r.y1))):
            x0, y0, x1, y1 = bounds
            tol = geom.CLIP_EDGE_TOL_PT
            if (r.x1 < x0 - tol or r.y1 < y0 - tol
                    or r.x0 > x1 + tol or r.y0 > y1 + tol):
                return None
        rects = rects if rects is not None else [_rect_poly(pg) for pg in polys]
        if all(b is not None and b[0] <= r.x0 and b[1] <= r.y0 and r.x1 <= b[2] and r.y1 <= b[3]
               for b in rects):
            return path
    return geom.clip_path(path, polys)


def _resolver_lote(pendientes, plan):
    vectorial = len(pendientes) >= recorte_lotes.MIN_VECTOR
    estados = (plan.estados([p for p, _mine, _prof in pendientes])
               if vectorial else [0] * len(pendientes))
    for (path, mine, is_prof), estado in zip(pendientes, estados):
        if estado == -1:
            continue
        shown = path if estado == 1 else _recortar(
            path, plan.polys, plan.rects, None if vectorial else plan.exterior)
        if shown is not None:
            yield path, shown, mine, is_prof


def _recortados(todos, page_rect, capas):
    """Sigue los recortes del PDF en orden; dentro de cada estado, resuelve los trazos por lotes acotados."""
    clip_stack: Dict[int, list] = {}
    planes = {}
    pendientes = []
    plan = None
    lote = recorte_lotes.tamano_lote() if len(todos) >= recorte_lotes.MIN_VECTOR else recorte_lotes.LOTE
    for k_av, path in enumerate(todos):
        if k_av % 4000 == 0:
            avance.avisar(_tr("Recortando lo que se ve de cada capa…"), k_av, len(todos))
        lvl = int(path.get("level", 0) or 0)
        tipo = path.get("type")
        if tipo in ("clip", "group"):
            if pendientes:
                yield from _resolver_lote(pendientes, plan)
                pendientes = []
            clip_stack = recognition._cerrar_recortes(clip_stack, lvl)
            if tipo == "clip":
                clip_stack[lvl] = recognition._clip_polygon(path, page_rect)
            planes.clear()
            continue
        if not path.get("items"):
            continue
        layer = path.get("layer") or ""
        is_prof = recognition.PROFILE_LAYER_TOKEN in pdf_layers.short_name(layer).upper()
        mine = capas is None or capas(layer)
        if not (mine or is_prof):
            continue
        niveles = tuple(lv for lv, pg in clip_stack.items() if lv < lvl and pg)
        if not niveles:
            if pendientes:
                yield from _resolver_lote(pendientes, plan)
                pendientes = []
            yield path, path, mine, is_prof
            continue
        nuevo = planes.get(niveles)
        if nuevo is None:
            polys = [clip_stack[lv] for lv in niveles]
            nuevo = planes[niveles] = recorte_lotes.Plan(
                polys, [_rect_poly(pg) for pg in polys], geom.CLIP_EDGE_TOL_PT)
        if pendientes and nuevo is not plan:
            yield from _resolver_lote(pendientes, plan)
            pendientes = []
        plan = nuevo
        pendientes.append((path, mine, is_prof))
        if len(pendientes) >= lote:
            yield from _resolver_lote(pendientes, plan)
            pendientes = []
    if pendientes:
        yield from _resolver_lote(pendientes, plan)
    avance.avisar(_tr("Recortando lo que se ve de cada capa…"), len(todos), len(todos))


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
    return _leer(page, capas, para_reconocimiento)


def capas_visibles(page) -> set:
    """Las capas con algo visible: las de `trazos_visibles(page, None)`, sin recortar más trazos de los necesarios.
    Primero los perfiles (dan las zonas que no cuentan); después, de cada capa, hasta el primer trazo que se ve.
    Recortarlos todos era lo más caro de abrir «Capas de la hoja» (4–5 s con 4 hojas)."""
    avance.avisar(_tr("Recortando lo que se ve de cada capa…"))
    todos = pdf_styles.drawings(page, extended=True)
    prof = []
    for _path, shown, _mine, _is_prof in _recortados(todos, page.rect, lambda _capa: False):
        bb = geom._path_bbox(shown)
        if bb is not None:
            prof.append(bb)
    regions = recognition._merge_close_boxes(prof, recognition.PROFILE_REGION_PAD_PT) if prof else []
    vistas: set = set()
    clip_stack: Dict[int, list] = {}
    planes: dict = {}
    for path in todos:
        lvl = int(path.get("level", 0) or 0)
        tipo = path.get("type")
        if tipo in ("clip", "group"):
            clip_stack = recognition._cerrar_recortes(clip_stack, lvl)
            if tipo == "clip":
                clip_stack[lvl] = recognition._clip_polygon(path, page.rect)
            planes.clear()
            continue
        layer = path.get("layer") or ""
        if layer in vistas or not path.get("items"):
            continue
        niveles = tuple(lv for lv, pg in clip_stack.items() if lv < lvl and pg)
        plan = planes.get(niveles)
        if plan is None:
            polys = [clip_stack[lv] for lv in niveles]
            plan = planes[niveles] = recorte_lotes.Plan(polys, [_rect_poly(pg) for pg in polys], geom.CLIP_EDGE_TOL_PT)
        shown = _recortar(path, plan.polys, plan.rects, plan.exterior)
        if shown is None or (shown.get("clipped") and recognition._path_length(shown) < recognition.CLIP_SLIVER_PT):
            continue
        if not (regions and recognition._region_hit(geom._path_bbox(shown), regions)):
            vistas.add(layer)
    avance.avisar(_tr("Recortando lo que se ve de cada capa…"), len(todos), len(todos))
    return vistas


def _leer(page, capas, para_reconocimiento):
    avance.avisar(_tr("Recortando lo que se ve de cada capa…"))
    cand: List[Tuple[dict, dict]] = []
    prof: list = []
    todos = pdf_styles.drawings(page, extended=True)
    for path, shown, mine, is_prof in _recortados(todos, page.rect, capas):
        if is_prof:
            bb = geom._path_bbox(shown)
            if bb is not None:
                prof.append(bb)
        if not mine or (para_reconocimiento and shown.get("clipped") and recognition._path_length(shown) < recognition.CLIP_SLIVER_PT):
            continue
        cand.append((path, shown))
    regions = recognition._merge_close_boxes(prof, recognition.PROFILE_REGION_PAD_PT) if prof and para_reconocimiento else []
    return [(p, s) for p, s in cand if not (regions and recognition._region_hit(geom._path_bbox(s), regions))]
