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

import re
from collections import Counter
from typing import Iterable, List, Set

from nucleo.model import TIPOS
from hoja import pdf_styles

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
    if name.startswith(pdf_styles.PREFIX):
        return pdf_styles.style_label(name)
    return name.split("|")[-1] if "|" in name else name


def _ui_configs(doc) -> list:
    try:
        return list(doc.layer_ui_configs() or [])
    except Exception:
        return []


def hidden_layers(doc) -> Set[str]:
    """Nombres (completos) de las capas apagadas ahora en el documento."""
    return {c["text"] for c in _ui_configs(doc) if not c.get("on", 1)} | set(
        getattr(doc, "_pdf_style_hidden", ()))


def set_hidden(doc, hidden: Iterable[str]) -> None:
    """Apaga exactamente las capas de `hidden` y enciende todas las demás."""
    hidden = set(hidden or ())
    doc._pdf_style_hidden = {name for name in hidden if name.startswith(pdf_styles.PREFIX)}
    for c in _ui_configs(doc):
        want_on = c["text"] not in hidden
        if bool(c.get("on", 1)) != want_on:
            doc.set_layer_ui_config(c["number"], action=_ACTION_ON if want_on else _ACTION_OFF)


def page_layers(doc, page_index: int, letters: bool = True) -> List[dict]:
    """Capas OCG y, en hojas aplanadas, capas virtuales por estilo.

    Devuelve dicts ``{name, short, number, path_count, on, utility, letters,
    letter_utilities, letter_codes, name_utility}`` para **cada** entrada de ``layer_ui_configs``
    (como Okular), aunque ``path_count`` sea 0 en esa hoja. Orden: primero las que
    tienen trazos (``path_count`` desc), luego las de 0 trazos por nombre corto.
    Para contar se encienden TODAS las capas un instante (los trazos de capas
    apagadas no salen en ``get_drawings``) y se restaura la visibilidad previa
    antes de devolver. En hojas con geometría OCG se omiten los trazos sin capa
    (marcos, bordes). En hojas sin geometría OCG se agrupan por estilo: sus
    casillas excluyen trazos del reconocimiento, sin modificar el render.

    Con `letters` se leen además las LETRAS del linetype de cada capa
    (`recognition.letter_uses`): una capa cuyo nombre no es de ninguna utilidad pero
    sus líneas dicen «—TE—» va al grupo de su utilidad (``letters`` = «TE»,
    ``letter_utilities`` = las que se reconocen por letras, ``letter_codes`` = el código
    de cada una; ``name_utility`` = la que decía su nombre si las letras la contradicen)."""
    cfgs = _ui_configs(doc)
    if not cfgs:
        return pdf_styles.layer_rows(pdf_styles.drawings(doc[page_index]), hidden_layers(doc))
    prev_hidden = hidden_layers(doc)
    set_hidden(doc, ())
    try:
        page = doc[page_index]
        drawings = pdf_styles.drawings(page)
        counts = Counter(d.get("layer") or "" for d in drawings)
        uses, read = {}, {}
        if letters:
            from reconocimiento import recognition                      # pesado: solo aquí (pdf_layers lo usa el compositor)
            read = recognition.page_letters(page, drawings)
            uses = recognition.letter_uses(read)
    finally:
        set_hidden(doc, prev_hidden)
    out = []
    for c in cfgs:
        name = c["text"]
        n = counts.get(name, 0)
        use = uses.get(name)
        lt = read.get(name)
        out.append({
            "name": name,
            "short": short_name(name),
            "number": c["number"],
            "path_count": n,
            "on": name not in prev_hidden,
            "utility": use.main if use is not None else utility_of(name),
            "name_group": utility_of(name),
            "letters": use.code if use is not None else "",
            "letter_utilities": list(use.utilities) if use is not None else [],
            "letter_codes": dict(use.codes) if use is not None else {},
            "letter_paths": dict(use.paths) if use is not None else {},
            "name_utility": use.name_utility if use is not None else "",
            # códigos de utilidad leídos en sus líneas (la leyenda marca los de esta hoja)
            "read_codes": [k for k, v in lt.codes.items() if v >= 2 and not k.endswith("(OH)")] if lt else [],
            "letter_raw": dict(lt.raw) if lt else {},       # código → letras con su caja («G», «e»)
            "read_counts": dict(lt.codes) if lt else {},    # código → sitios donde se leyó
        })
    out.extend(pdf_styles.layer_rows(drawings, prev_hidden))
    # Con trazos primero (más → menos); sin trazos al final, por short.
    out.sort(key=lambda d: (0 if d["path_count"] > 0 else 1,
                            -d["path_count"],
                            d["short"].upper()))
    return out


def layer_groups(L: dict) -> List[str]:
    """Grupos de «Capas del plano» donde va la capa: el de su utilidad y, si las letras de
    sus líneas la hacen de VARIAS (capa mezclada: `G-XREF` de DU06 h.5 trae las líneas
    «—T—» de telecom y un tramo «—W—» de agua), también el de cada una de las otras. Es
    UNA capa del PDF: sale en los dos grupos y ocultarla oculta las líneas de ambas."""
    main = L.get("utility") or UTILITY_OTHER
    return [main] + [u for u in (L.get("letter_utilities") or ()) if u != main]


def without_letters(layers: List[dict], off: Iterable[str]) -> List[dict]:
    """`page_layers` con la decisión del usuario: las capas de `off` NO se toman por las
    letras de su línea (vuelven a su grupo por nombre y pierden la etiqueta)."""
    off = set(off or ())
    out = []
    for L in layers:
        if L["name"] in off and L.get("letter_utilities"):
            L = dict(L, utility=L.get("name_group") or utility_of(L["name"]), letters="",
                     letter_utilities=[], letter_codes={}, letter_paths={}, name_utility="")
        out.append(L)
    return out


_XREF_RE = re.compile(rb"(\d+) 0 R")


def page_uses_layers(doc, page_index: int) -> bool:
    """¿La hoja dibuja algo DENTRO de una capa OCG (apagar capas la cambia)?

    Hay PDFs que traen capas en el documento pero con hojas «aplanadas»: sus
    vectores no están marcados con ninguna capa (DU08 hojas 3–19, DU10 hojas
    30–37 de la carpeta de pruebas: 0 % de trazos con capa), así que apagar
    una capa no las cambia y el reconocimiento por capas no encuentra nada.

    Barato (sin `get_drawings`, ~10 ms por hoja): busca el operador de
    contenido opcional `/OC` en el contenido de la hoja y, recursivamente, en
    sus XObjects (su diccionario `/OC` o su propio contenido). Verificado
    contra el conteo real de trazos con capa en las 88 hojas de los PDFs de
    prueba: coincide en todas."""
    if not _ui_configs(doc):
        return False
    page = doc[page_index]
    try:
        if b"/OC" in page.read_contents():
            return True
        stack = [x[0] for x in page.get_xobjects()]
    except Exception:
        return True                     # ante la duda, no marcar la hoja
    seen = set()
    while stack:
        x = stack.pop()
        if x in seen or x <= 0:
            continue
        seen.add(x)
        try:
            if doc.xref_get_key(x, "OC")[0] != "null":
                return True
            if b"/OC" in (doc.xref_stream(x) or b""):
                return True
            kind, val = doc.xref_get_key(x, "Resources/XObject")
        except Exception:
            continue
        if kind == "dict":
            stack.extend(int(m) for m in _XREF_RE.findall(val.encode("latin-1", "ignore")))
        elif kind == "xref":            # diccionario de XObjects indirecto
            try:
                ref = int(val.split()[0])
                stack.extend(int(m) for m in _XREF_RE.findall(doc.xref_object(ref).encode("latin-1", "ignore")))
            except Exception:
                pass
    return False
