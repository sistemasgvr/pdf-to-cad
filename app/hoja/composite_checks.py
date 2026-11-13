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

from traduccion.i18n_core import N_

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


# ── hojas encimadas (reporte 2026-11-13, cliente en fase beta) ──────────────────────────────
# Sin composición sugerida, el usuario tomó 10–15 hojas una por una y las dejó donde caían, unas
# ENCIMA de otras. Al reconocer, la tinta y las leyendas de una pieza tapaban a la de abajo: las
# líneas se asignaban a la utilidad equivocada (alcantarillado 0 líneas, agua 8 278) y el proceso
# podía no terminar. Las costuras normales (borde con borde, el solape de «Fundir bordes») son
# angostas; dos hojas puestas una sobre otra comparten una buena parte de su área.
ENCIMADA_FRAC = 0.25        # dos piezas que comparten ≥ esto del área de la MÁS CHICA = encimadas


def encimadas(rects, frac: float = ENCIMADA_FRAC):
    """[(i, j, fracción)] de las piezas (rectángulos x0, y0, x1, y1 en la hoja compuesta) que se
    tapan una a otra en ≥ `frac` del área de la más chica. i < j, de más a menos tapadas."""
    out = []
    for i in range(len(rects)):
        ax0, ay0, ax1, ay1 = rects[i]
        aa = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
        for j in range(i + 1, len(rects)):
            bx0, by0, bx1, by1 = rects[j]
            ab = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
            w = min(ax1, bx1) - max(ax0, bx0)
            h = min(ay1, by1) - max(ay0, by0)
            chica = min(aa, ab)
            if w <= 0 or h <= 0 or chica <= 0:
                continue
            f = w * h / chica
            if f >= frac:
                out.append((i, j, f))
    out.sort(key=lambda t: -t[2])
    return out
