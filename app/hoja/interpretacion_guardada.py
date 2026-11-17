"""interpretacion_guardada.py — la interpretación de la hoja, LIVIANA, para el `.digproj` (PURO, sin Qt; plan
2026-11-16, «reconocimiento desde el editor», Tarea 10).

`hoja.interpretar_trabajo.interpretar` devuelve capas, leyenda del mapa (`LeyendaMapa`), estilos sugeridos
(`Sugerencia`), símbolos, rótulos, escala, firma… y las LETRAS de cada capa (`LayerLetters`, con sus trazos). Al
guardar va todo menos las letras (son lectura de la hoja: el ▶ las vuelve a leer en el trabajador). También van los
roles elegidos para la hoja (`Main._layer_roles_by_utility`): sin ellos el primer ▶ tras reabrir no daría lo mismo.

JSON no tiene tuplas, conjuntos, claves no texto ni clases: `codificar` las marca (`__t__`, `__s__`, `__d__`,
`__dc__`) y `decodificar` las rehace igual (`==` con lo original). Solo se reconstruyen las clases de `CLASES`: un
`.digproj` ajeno no puede pedir otra (ValueError).
"""
from __future__ import annotations

import dataclasses
import importlib
from typing import Optional, Tuple

VERSION = 1
SIN_GUARDAR = ("letras",)                       # lectura de la hoja: nunca al .digproj
CLASES = {"hoja.leyenda_mapa:LeyendaMapa", "hoja.leyenda_mapa:FilaMapa",
          "hoja.estilos_sugeridos:Sugerencia"}


def codificar(v):
    """`v` en datos que `json.dumps` acepta y `decodificar` rehace igual."""
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        nombre = f"{type(v).__module__}:{type(v).__qualname__}"
        if nombre not in CLASES:
            raise ValueError(f"clase no guardable: {nombre}")
        return {"__dc__": nombre, "campos": {f.name: codificar(getattr(v, f.name)) for f in dataclasses.fields(v)}}
    if isinstance(v, dict):
        if all(isinstance(k, str) and not k.startswith("__") for k in v):
            return {k: codificar(x) for k, x in v.items()}
        return {"__d__": [[codificar(k), codificar(x)] for k, x in v.items()]}
    if isinstance(v, tuple):
        return {"__t__": [codificar(x) for x in v]}
    if isinstance(v, (set, frozenset)):
        cod = [codificar(x) for x in v]
        import json
        cod.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))   # orden fijo (huella del proyecto)
        return {"__s__" if isinstance(v, set) else "__fs__": cod}
    if isinstance(v, list):
        return [codificar(x) for x in v]
    if v is None or isinstance(v, (str, bool, int, float)):
        return v
    if hasattr(v, "item"):                       # números de numpy
        return v.item()
    raise ValueError(f"dato no guardable: {type(v).__name__}")


def _clase(nombre):
    if nombre not in CLASES:
        raise ValueError(f"clase no permitida: {nombre}")
    mod, cls = nombre.split(":")
    return getattr(importlib.import_module(mod), cls)


def decodificar(v):
    if isinstance(v, list):
        return [decodificar(x) for x in v]
    if not isinstance(v, dict):
        return v
    if "__dc__" in v:
        cls = _clase(v["__dc__"])
        return cls(**{k: decodificar(x) for k, x in (v.get("campos") or {}).items()})
    if "__t__" in v:
        return tuple(decodificar(x) for x in v["__t__"])
    if "__s__" in v:
        return {decodificar(x) for x in v["__s__"]}
    if "__fs__" in v:
        return frozenset(decodificar(x) for x in v["__fs__"])
    if "__d__" in v:
        return {decodificar(k): decodificar(x) for k, x in v["__d__"]}
    return {k: decodificar(x) for k, x in v.items()}


def ligera(interp: Optional[dict], roles=None) -> dict:
    """{version, interpretacion (sin las letras), roles} — listo para `json.dumps`."""
    datos = None if interp is None else {k: v for k, v in interp.items() if k not in SIN_GUARDAR}
    return {"version": VERSION, "interpretacion": codificar(datos), "roles": codificar(roles)}


def de_ligera(d: Optional[dict]) -> Tuple[Optional[dict], Optional[dict]]:
    """(interpretación, roles) de lo que guardó `ligera`."""
    d = d or {}
    return decodificar(d.get("interpretacion")), decodificar(d.get("roles"))
