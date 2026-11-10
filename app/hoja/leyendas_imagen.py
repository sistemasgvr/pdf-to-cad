"""leyendas_imagen.py — leyendas que el PDF trae como IMAGEN (PURO; pedido del usuario 2026-11-07).

Southwest Gas pega su leyenda como una imagen: `get_text` no la lee y la hoja parece no tener leyenda, aunque dice qué
es cada símbolo. La misma imagen va en todas sus hojas (mismos bytes), así que aquí se reconoce por su huella y una
tabla, leída una vez a mano de esa imagen, da el significado de cada glifo. Una imagen que no está en la tabla no da
nada: los símbolos se siguen asignando a mano con el rol «Válvulas» (`simbolos_fuente`).

Los glifos se nombran por su fuente y su carácter: el número interno cambia con cada subconjunto de la fuente.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

EXCESO_FLUJO = "Exceso de flujo"


@dataclass(frozen=True)
class Simbolo:
    texto: str                     # lo que dice la fila de la leyenda
    tipo: str = ""                 # tipo de válvula ("" = compuerta)
    por_rumbo: bool = False        # abierta o cerrada según cómo va el símbolo respecto a la tubería


@dataclass(frozen=True)
class Leyenda:
    empresa: str
    utilidad: str
    simbolos: Dict[Tuple[str, int], Simbolo]


CONOCIDAS = {
    # «VALVE - OPEN»: el medio círculo con el borde a lo largo de la tubería; «VALVE - CLOSED»: atravesado
    "6df8a828855445f4a8e1a5d6cc1559d793e11dfa": Leyenda("Southwest Gas", "GAS", {
        ("ESRIDefaultMarker", 60): Simbolo("VALVE", por_rumbo=True),
        ("ESRIDefaultMarker", 83): Simbolo("EXCESS FLOW VALVE", EXCESO_FLUJO),
    }),
}


def conocida(page) -> Optional[Leyenda]:
    """La leyenda conocida que trae la hoja como imagen, o None."""
    doc = page.parent
    memo = doc.__dict__.setdefault("_pdfcad_leyenda_imagen", {})
    if page.number not in memo:
        memo[page.number] = None
        for im in page.get_images(full=True):
            try:
                ley = CONOCIDAS.get(hashlib.sha1(doc.extract_image(im[0])["image"]).hexdigest())
            except (RuntimeError, ValueError, KeyError, TypeError):
                continue
            if ley is not None:
                memo[page.number] = ley
                break
    return memo[page.number]
