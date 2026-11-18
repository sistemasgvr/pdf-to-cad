"""lectura_retenida.py — la lectura cruda de UNA hoja que se QUEDA en el proceso entre trabajos (PURO, sin Qt;
plan 2026-11-16, «reconocimiento desde el editor»).

Antes, `recognition_trabajo.reconocer_hoja` abría el PDF, leía la hoja una vez para todas las utilidades
(`pdf_styles.lectura_unica`) y soltaba todo al terminar. Ahora cada ▶ del panel «Reconocer» es un trabajo aparte
(una utilidad, las válvulas, los diámetros, los rótulos) y la interpretación de la hoja es otro: los tres leerían la
hoja de nuevo. Aquí el documento abierto y su `lectura_unica` quedan vivos en el proceso trabajador «reconocer» bajo
una FIRMA (la de la hoja compuesta, la pone quien llama): otro trabajo con la misma firma los reusa.

  · `abrir(ruta, firma)` → el documento retenido de esa firma (lo abre la 1.ª vez; otra firma suelta la anterior:
    como mucho UNA hoja retenida — en 36 mapas su lectura es ~1 GB).
  · `reponer(doc)` → deja el documento como lo da un `fitz.open` recién hecho: capas encendidas/apagadas como
    venían en el PDF y sin estilos ocultos. La interpretación las enciende todas (`capas_trabajo.leer_doc`) y
    `reconocer_hoja` siempre reconoció sobre un documento recién abierto (las capas ocultas se filtran por NOMBRE):
    sin esto las cachés por estado de capas (`pdf_styles`, `page_letters`) darían otra cosa.
  · `soltar()` → cierra y suelta (trabajo `"reconocimiento.lectura_retenida:soltar"`; el trabajador vuelve a poder
    reciclarse, `ui.comun.proceso`).

Si el proceso muere (tope de memoria, cancelar), la lectura muere con él: el próximo trabajo vuelve a abrir y leer,
con el mismo resultado.

OJO: lo leído se COMPARTE entre trabajos (`pdf_styles.drawings`, `memo`): nadie debe modificar las listas que
devuelven (con proceso, ni sin él: `PDFCAD_PROCESO=0` retiene la lectura en el proceso de la ventana hasta `soltar`
o hasta que llega otra firma). Solo el trabajador «reconocer» deja de reciclarse mientras retiene
(`ui.comun.proceso.RETENEDOR`); estos trabajos en otro trabajador no cambian su reciclado.
"""
from __future__ import annotations

import gc
from typing import Optional

_ACTUAL: Optional[dict] = None      # {firma, ruta, doc, lectura (contexto abierto), capas (estado inicial)}


def abrir(ruta: str, firma: str):
    """El documento retenido para `firma` (dentro de su `pdf_styles.lectura_unica`)."""
    global _ACTUAL
    ruta = str(ruta)
    firma = str(firma)
    a = _ACTUAL
    if a is not None and a["firma"] == firma and a["ruta"] == ruta and not a["doc"].is_closed:
        return a["doc"]
    soltar()
    import pymupdf as fitz
    from hoja import pdf_layers, pdf_styles
    doc = fitz.open(ruta)
    capas = pdf_layers.encendidas(doc)
    lectura = pdf_styles.lectura_unica(doc)
    lectura.__enter__()
    _ACTUAL = {"firma": firma, "ruta": ruta, "doc": doc, "lectura": lectura, "capas": capas}
    return doc


def reponer(doc) -> None:
    """Capas y estilos ocultos como al abrir el PDF (ver el docstring del módulo)."""
    from hoja import pdf_layers
    a = _ACTUAL
    if a is None or a["doc"] is not doc:
        return
    pdf_layers.poner_encendidas(doc, a["capas"])
    doc.__dict__.pop("_pdf_style_hidden", None)


def retenida() -> Optional[str]:
    """La firma retenida en este proceso (None = ninguna)."""
    return _ACTUAL["firma"] if _ACTUAL is not None else None


def soltar(progreso=None) -> None:
    """Cierra el documento retenido y suelta su lectura (la memoria vuelve al asignador)."""
    global _ACTUAL
    a, _ACTUAL = _ACTUAL, None
    if a is None:
        return
    try:
        a["lectura"].__exit__(None, None, None)
    except Exception:                                  # noqa: BLE001 — soltar nunca falla
        pass
    try:
        a["doc"].close()
    except Exception:                                  # noqa: BLE001
        pass
    gc.collect()
