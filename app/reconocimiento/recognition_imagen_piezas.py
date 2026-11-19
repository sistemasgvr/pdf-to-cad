"""recognition_imagen_piezas.py — modo «trazo continuo» / núcleo POR PIEZA en las capas de IMAGEN de una hoja
compuesta (PURO; ronda de corrección 2 de la Tarea 5 de los ejes de imagen, plan 2026-11-18).

`recognize_page` decide por CAPA si sus trazos son continuos (la tinta es el eje, `recognition_ink_lines`) o un tipo
de línea a guiones (núcleo). En una hoja COMPUESTA de mapas con la red en imagen (Phoenix «QS SD»), cada pieza trae
los ejes de SU hoja de origen (`hoja/imagen_compuesta`): una hoja suelta puede ser continua y su vecina no (South h.4
sí, h.5 no: sus bandas «en caja» salen en trozos). Decidido en la hoja entera, la pieza h.4 iba al núcleo y daba 74
líneas contra 146 suelta. Aquí, solo para las capas de imagen (`PDF_STYLE:["img",…]`) y solo en una compuesta (trazos
de ≥ 2 piezas), cada pieza decide con lo suyo, como su hoja suelta; las capas vectoriales y las hojas sueltas no
pasan por aquí (mismo resultado que antes)."""
from __future__ import annotations

import bisect
from typing import Callable, List, Optional, Sequence, Tuple

from hoja import pdf_styles

_PREFIJO_IMAGEN = pdf_styles.PREFIX + '["img"'


def es_capa_imagen(ocg: str) -> bool:
    return (ocg or "").startswith(_PREFIJO_IMAGEN)


def pieza_de(path: dict, inicios: Sequence[int]) -> int:
    """Índice de la pieza del trazo (como `recognition_ink_lines`): −1 si no se sabe."""
    seq = path.get("seqno")
    return bisect.bisect_right(inicios, int(seq)) - 1 if inicios and seq is not None else -1


def grupos(ocg: str, paths: Sequence[dict], inicios: Optional[Sequence[int]],
           continua: Callable[[Sequence[dict]], bool]) -> Optional[List[Tuple[bool, List[dict]]]]:
    """[(¿continua?, trazos)] de una capa de imagen de una hoja compuesta: los trazos de las piezas que su propia
    tinta hace continuas y los de las demás (en el orden original; grupos vacíos fuera). None si la capa no es de
    imagen o sus trazos no son de ≥ 2 piezas (todo como antes)."""
    if not es_capa_imagen(ocg) or not inicios or not paths:
        return None
    por_pieza: dict = {}
    for p in paths:
        por_pieza.setdefault(pieza_de(p, inicios), []).append(p)
    if len(por_pieza) < 2:
        return None
    modo = {k: bool(continua(ps)) for k, ps in por_pieza.items()}
    out = []
    ps = [p for p in paths if modo[pieza_de(p, inicios)]]
    if ps:
        out.append((True, ps))
    # las del NÚCLEO, cada pieza por separado (2026-11-19: juntas, una compuesta de 36 mapas pasaba horas en
    # `recognition_geom.resolve_nodes`, que compara extremos y corridas todos con todos; sola, cada pieza da lo
    # mismo que su hoja suelta). Mismo orden de los trazos dentro de cada una.
    for k in sorted(k for k in por_pieza if not modo[k]):
        out.append((False, [p for p in paths if pieza_de(p, inicios) == k]))
    return out


def bovedas_cerca(ps: Sequence[dict], vault_paths: Sequence[dict], margen: float) -> List[dict]:
    """Los trazos de bóveda que tocan la caja de los trazos `ps` agrandada `margen` (en su orden): el núcleo de UNA
    pieza solo necesita las bóvedas de su zona."""
    cajas = [c for c in (_caja(p.get("rect")) for p in ps) if c is not None]
    if not cajas:
        return list(vault_paths)
    x0 = min(r[0] for r in cajas) - margen
    y0 = min(r[1] for r in cajas) - margen
    x1 = max(r[2] for r in cajas) + margen
    y1 = max(r[3] for r in cajas) + margen
    out = []
    for v in vault_paths:
        r = _caja(v.get("rect"))
        if r is None or (r[0] <= x1 and r[2] >= x0 and r[1] <= y1 and r[3] >= y0):
            out.append(v)
    return out


def _caja(r):
    """(x0, y0, x1, y1) de un `rect`: fitz.Rect, `recognition_geom._Rect` (trazo recortado, sin índices) o tupla."""
    if r is None:
        return None
    if hasattr(r, "x0"):
        return r.x0, r.y0, r.x1, r.y1
    return tuple(r[:4])


def con_contactos(ps: List[dict], contactos) -> List[dict]:
    """El grupo con los contactos de la capa en su primer trazo (el núcleo los lee de cualquier trazo; la capa los
    lleva en el primero de TODA la capa, que puede quedar en el otro grupo)."""
    if not contactos or not ps or ps[0].get("contact_pts"):
        return ps
    return [dict(ps[0], contact_pts=contactos)] + list(ps[1:])
