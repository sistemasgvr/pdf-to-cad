"""recognition_cache.py — el reconocimiento de la hoja queda EN MEMORIA (PURO, sin Qt).

Pedido del usuario (2026-10-06): ya importado el reconocimiento al editor, volver
a Herramientas → «Componer hoja de trabajo…» y seguir sin cambiar nada volvía a
reconocer todas las utilidades (el paso más lento del asistente). Ahora cada
resultado se guarda con una CLAVE que reúne todo lo que lo decide:

  · el contenido de los PDF de origen (sha1; el mismo `bytes` no se vuelve a leer),
  · la composición (piezas, recortes, giros, escala, puentes; no `last_view`, que
    solo dice dónde quedó mirando el compositor),
  · la hoja, las capas ocultas, las utilidades a reconocer, los roles de
    «Ajustar capas…», las capas que no se toman por sus letras, la escala y el zoom.

Si la clave se repite, la vista previa se abre con ese resultado sin volver a leer
el PDF; cualquier cambio da otra clave y se reconoce de nuevo. «Unir tramos» no
entra en la clave: el resultado trae las dos variantes (`polylines_joined` /
`polylines_raw`) y `set_join_routes` deja la elegida. El import y la vista previa
no modifican los resultados (solo esa elección), así que se pueden reutilizar.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

# Hojas recordadas a la vez (◀ ▶ del editor también reconoce: volver a una hoja
# reciente es instantáneo). Cada entrada son los resultados de todas las utilidades.
MAX_ENTRIES = 4

# Campos de la composición que no cambian la hoja de trabajo.
_COMPOSITE_VIEW_ONLY = ("last_view", "alignment_ruler")


def freeze(value):
    """Valor → algo hashable y estable (dict/set sin orden, listas → tuplas)."""
    if isinstance(value, dict):
        return tuple(sorted(((str(k), freeze(v)) for k, v in value.items()), key=repr))
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((freeze(v) for v in value), key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, float):
        return float(value)
    return value


def composition_signature(comp) -> tuple | None:
    """La composición tal como la ve el reconocimiento (sin lo que es solo vista)."""
    if comp is None:
        return None
    d = comp.to_dict()
    for key in _COMPOSITE_VIEW_ONLY:
        d.pop(key, None)
    return freeze(d)


class SourceFingerprints:
    """Huella sha1 del contenido de cada PDF de origen. Recuerda la de cada objeto
    `bytes` mientras siga en la lista: volver a pedirla no relee el PDF."""

    def __init__(self):
        self._memo: dict = {}

    def __call__(self, sources) -> tuple:
        fresh, out = {}, []
        for entry in sources or ():
            data = entry.get("data") or b""
            hit = self._memo.get(id(data))
            digest = hit[1] if hit is not None and hit[0] is data else hashlib.sha1(data).hexdigest()
            fresh[id(data)] = (data, digest)
            out.append(digest)
        self._memo = fresh
        return tuple(out)


def recognition_key(document, composite, page_index, *, hidden_ocgs=(), utilities=(),
                    roles_by_utility=None, letters_off=(), scale_ft_per_pt=None,
                    zoom=1.0) -> tuple:
    """Todo lo que decide el resultado de `RecognitionWorker` sobre la hoja.
    `document` identifica el PDF de origen (huellas de `SourceFingerprints`)."""
    return (
        freeze(document),
        composition_signature(composite),
        int(page_index),
        freeze(set(hidden_ocgs or ())),
        tuple(utilities or ()),
        freeze({k: v for k, v in (roles_by_utility or {}).items() if v}),
        freeze(set(letters_off or ())),
        None if scale_ft_per_pt is None else float(scale_ft_per_pt),
        float(zoom),
    )


class RecognitionCache:
    """Los últimos `max_entries` reconocimientos, por clave (el más viejo sale)."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self.max_entries = max(1, int(max_entries))
        self._items: OrderedDict = OrderedDict()

    def get(self, key):
        """Resultados guardados con esa clave (lista nueva) o None."""
        if key is None or key not in self._items:
            return None
        self._items.move_to_end(key)
        return list(self._items[key])

    def put(self, key, results) -> None:
        results = [r for r in (results or ()) if r is not None]
        if key is None or not results:
            return
        self._items[key] = results
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def set_join_routes(results, on: bool) -> None:
    """«Unir tramos»: deja en cada resultado la variante elegida (unida o cortada)."""
    for result in results or ():
        joined = getattr(result, "polylines_joined", None)
        raw = getattr(result, "polylines_raw", None)
        if not joined or not raw:
            continue
        result.join_routes = bool(on)
        result.polylines = list(joined if on else raw)
