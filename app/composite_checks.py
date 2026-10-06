"""composite_checks.py — qué falta para seguir en «Componer hoja» (PURO, sin Qt).

El compositor va en PESTAÑAS (Origen · Área a tomar · Hoja compuesta; pedido del
usuario 2026-10-03: en tres columnas a cada vista le quedaba poco sitio) y antes de
«Continuar» revisa lo que el usuario podría haber dejado a medias:

  - ERROR  no hay ninguna pieza ni área marcada: «Continuar» queda apagado (con
           solo un área marcada, «Continuar» la toma: es lo único útil). Desde
           2026-10-05 la hoja elegida entra sola, así que solo pasa si el usuario
           quitó todas las piezas;
  - AVISO  hay un área marcada sin tomar (marcó el rectángulo y no pulsó «Tomar»);
  - AVISO  la hoja a la vista no está en la hoja compuesta (eligió otra hoja y no
           la tomó: reporte del usuario 2026-09-30).
Los avisos no bloquean; al pulsar «Continuar» se pregunta qué hacer con ellos.
Cada aviso dice en qué pestaña se arregla (`tab`). La vista los traduce con `t()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from i18n_core import N_

TAB_SOURCE, TAB_AREA, TAB_SHEET = 0, 1, 2
ERROR, WARN = "error", "warn"


@dataclass
class Check:
    level: str            # ERROR | WARN
    code: str             # no_pieces | untaken_area | pending_page
    text: str             # clave i18n (con {n} = nº de hoja, si lo lleva)
    page: int = 0         # nº de hoja (1…) para el texto
    tab: int = TAB_AREA   # pestaña donde se arregla


def checks(n_pieces: int, untaken_area_page: Optional[int] = None,
           pending_page: Optional[int] = None) -> List[Check]:
    """Lo que falta, lo más grave primero. Páginas en base 1 (None = nada)."""
    out: List[Check] = []
    # sin piezas pero con un área marcada no se bloquea: «Continuar» la toma
    if n_pieces <= 0 and untaken_area_page is None:
        out.append(Check(ERROR, "no_pieces",
                         N_("Para continuar, elige una hoja del plano."), tab=TAB_SOURCE))
    if untaken_area_page is not None:
        out.append(Check(WARN, "untaken_area", N_("Hay un área marcada en la hoja {n} sin tomar."),
                         untaken_area_page, TAB_AREA))
    # la hoja sin tomar solo importa si ya hay piezas (si no, manda el error) y si no
    # la explica ya el área marcada en esa misma hoja
    if pending_page is not None and n_pieces > 0 and pending_page != untaken_area_page:
        out.append(Check(WARN, "pending_page", N_("La hoja {n} que estás viendo no está en la hoja compuesta."),
                         pending_page, TAB_AREA))
    return out


def ready(found: List[Check]) -> bool:
    """¿Se puede continuar? Solo los errores bloquean."""
    return not any(c.level == ERROR for c in found)
