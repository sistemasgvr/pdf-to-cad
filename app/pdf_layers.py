"""pdf_layers.py — Capas OCG de una hoja PDF: listado y visibilidad (puro, sin Qt).

Un PDF "bien ploteado" desde AutoCAD/Civil 3D conserva las capas del DWG como
grupos de contenido opcional (OCG). PyMuPDF permite apagarlas por documento con
``doc.set_layer_ui_config(numero, action)``; una capa apagada NO se pinta en
``page.get_pixmap()`` y sus trazos tampoco salen en ``page.get_drawings()``.
(``doc.set_layer(...)`` NO sirve en estos PDFs de Bluebeam: el render no cambia.)

Uso típico:
    layers = page_layers(doc, page_index)       # todas las OCG [{name, short, …}]
    set_hidden(doc, {"PS…|G-LOGO-SFTC"})        # apaga esas, enciende el resto
    hidden = hidden_layers(doc)                 # nombres apagados ahora mismo

La visibilidad vive en el ``fitz.Document``: afecta a todas las hojas y a todo
render posterior con ese mismo objeto (no a otro ``fitz.open`` del mismo archivo).
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, List, Set

from model import TIPOS

# Códigos de `Document.set_layer_ui_config(number, action)`.
_ACTION_ON, _ACTION_TOGGLE, _ACTION_OFF = 0, 1, 2


# ── Utilidad a la que pertenece una capa (por tokens NCS del nombre) ──────────
# Mismas utilidades (clave y etiqueta) que el desplegable «Tipo de utilidad» de
# la app (`model.TIPOS`), más «Otras» para el resto (calles, topo, membrete…).
# Las claves son capas de config.OUTPUT_LAYERS: así comparten color con la app.
# El reconocimiento hoy solo trata ELECTRICO; las demás agrupan la lista.
UTILITY_OTHER = "OTRAS"
UTILITIES = [(key, label) for label, key in TIPOS] + [(UTILITY_OTHER, "Otras")]
# Tokens (subcadena, sin distinguir mayúsculas). TELECOM va ANTES que
# ELECTRICO porque "TELE" contiene "ELE".
_UTILITY_TOKENS = [
    ("TELECOM", ("TELE", "COMM", "CATV", "FIBER", "FIBR", "-FO-")),
    ("ELECTRICO", ("ELEC", "POWR", "PWR", "STLT", "OC-SYSTEM", "OCS-")),
    ("AGUA", ("WATR", "WATER", "FIRE", "IRRG", "DOMW", "HYDR")),
    ("GAS", ("NGAS", "-GAS", "GAS-")),
    ("ALCANTARILLADO", ("SSWR", "SEWER", "SANI")),
    ("DRENAJE", ("STRM", "STORM", "DRAN", "DRAIN")),
]


def utility_of(name: str) -> str:
    """Clave de utilidad de una capa por su nombre (o ``UTILITY_OTHER``)."""
    up = short_name(name or "").upper()
    for key, toks in _UTILITY_TOKENS:
        if any(t in up for t in toks):
            return key
    return UTILITY_OTHER


def short_name(name: str) -> str:
    """'PS89616000-A1-UE-REF-EXIST_ELEC|C-ELEC-UNGD-E' → 'C-ELEC-UNGD-E'.
    Los prefijos son el XREF de origen; el usuario reconoce la capa por el sufijo."""
    return name.split("|")[-1] if "|" in name else name


def _ui_configs(doc) -> list:
    try:
        return list(doc.layer_ui_configs() or [])
    except Exception:
        return []


def hidden_layers(doc) -> Set[str]:
    """Nombres (completos) de las capas apagadas ahora en el documento."""
    return {c["text"] for c in _ui_configs(doc) if not c.get("on", 1)}


def set_hidden(doc, hidden: Iterable[str]) -> None:
    """Apaga exactamente las capas de `hidden` y enciende todas las demás."""
    hidden = set(hidden or ())
    for c in _ui_configs(doc):
        want_on = c["text"] not in hidden
        if bool(c.get("on", 1)) != want_on:
            doc.set_layer_ui_config(c["number"], action=_ACTION_ON if want_on else _ACTION_OFF)


def page_layers(doc, page_index: int) -> List[dict]:
    """Todas las capas OCG del documento, con conteo de trazos en la hoja.

    Devuelve dicts ``{name, short, number, path_count, on, utility}`` para **cada**
    entrada de ``layer_ui_configs`` (como Okular), aunque ``path_count`` sea 0
    en esa hoja. Orden: primero las que tienen trazos (``path_count`` desc),
    luego las de 0 trazos por nombre corto. Para contar se encienden TODAS las
    capas un instante (los trazos de capas apagadas no salen en
    ``get_drawings``) y se restaura la visibilidad previa antes de devolver.
    Los trazos sin capa (marcos, bordes de Bluebeam) no se listan: no se pueden
    apagar."""
    cfgs = _ui_configs(doc)
    if not cfgs:
        return []
    prev_hidden = hidden_layers(doc)
    set_hidden(doc, ())
    try:
        counts = Counter(d.get("layer") or "" for d in doc[page_index].get_drawings())
    finally:
        set_hidden(doc, prev_hidden)
    out = []
    for c in cfgs:
        name = c["text"]
        n = counts.get(name, 0)
        out.append({
            "name": name,
            "short": short_name(name),
            "number": c["number"],
            "path_count": n,
            "on": name not in prev_hidden,
            "utility": utility_of(name),
        })
    # Con trazos primero (más → menos); sin trazos al final, por short.
    out.sort(key=lambda d: (0 if d["path_count"] > 0 else 1,
                            -d["path_count"],
                            d["short"].upper()))
    return out
