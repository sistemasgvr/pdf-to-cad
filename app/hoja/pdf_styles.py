"""Virtual layers for flattened vectors. Never modifies the source PDF.

Names depend only on stroke/fill style, so roles survive reopening and page
navigation. Clips and native OCG paths keep their original identity.
"""
from __future__ import annotations

import contextlib
import json
from nucleo import avance
from traduccion.i18n_core import t as _tr

PREFIX = "PDF_STYLE:"


def _color(value):
    return None if value is None else tuple(round(float(v), 3) for v in value)


_NOMBRES: dict = {}          # estilo crudo → nombre (un mapa trae 1.5 millones de trazos y decenas de estilos)


def style_name(path):
    if path.get("type") in ("clip", "group") or not path.get("items"):
        return ""
    crudo = (path.get("type"), path.get("color"), path.get("width"), path.get("dashes"),
             path.get("fill"), path.get("stroke_opacity"), path.get("fill_opacity"))
    try:
        hit = _NOMBRES.get(crudo)
    except TypeError:                     # un valor no «hasheable»: se calcula sin caché
        return _style_name(path)
    if hit is None:
        if len(_NOMBRES) > 50000:
            _NOMBRES.clear()
        hit = _NOMBRES[crudo] = _style_name(path)
    return hit


def _style_name(path):
    key = (path.get("type"), _color(path.get("color")),
           round(float(path.get("width") or 0), 2),
           " ".join((path.get("dashes") or "[] 0").split()),
           _color(path.get("fill")),
           _opacity(path.get("stroke_opacity")),
           _opacity(path.get("fill_opacity")))
    return PREFIX + json.dumps(key, separators=(",", ":"))


def _opacity(value):
    return None if value is None else round(float(value), 3)


def symbol_name(font, key):
    """Capa virtual de un SÍMBOLO de la fuente (válvula, hidrante, buzón de un mapa SIG):
    sus glifos superpuestos con su color (`texto_pdf.Simbolo.clave`). Ver `leyenda_mapa`."""
    return PREFIX + json.dumps(["sym", font, [[int(g), list(c)] for g, c in key]], separators=(",", ":"))


def is_symbol(name):
    return name.startswith(PREFIX + '["sym"')


def style_width(name):
    """Grosor (pt) del trazo de una capa por estilo —o de su capa de acometidas—; None si no es
    una (capa con nombre, símbolo). Un trazo recortado por el clip ya no trae su `width`."""
    if not (name or "").startswith(PREFIX) or is_symbol(name):
        return None
    from hoja import acometidas_mapa
    if acometidas_mapa.es_capa(name):
        name = acometidas_mapa.estilo_de(name)
    try:
        return float(json.loads(name[len(PREFIX):])[2])
    except (ValueError, IndexError, TypeError):
        return None


_ETIQUETAS: dict = {}


def style_label(name):
    """Nombre legible de la capa virtual (memorizado: se pide por cada trazo de la hoja)."""
    hit = _ETIQUETAS.get(name)
    if hit is None:
        if len(_ETIQUETAS) > 50000:
            _ETIQUETAS.clear()
        hit = _ETIQUETAS[name] = _style_label(name)
    return hit


def _style_label(name):
    if is_symbol(name):
        glyphs = json.loads(name[len(PREFIX):])[2]
        return "Símbolo " + "+".join(str(g) for g, _c in glyphs)
    from hoja import acometidas_mapa
    if acometidas_mapa.es_capa(name):
        return "Acometidas · " + style_label(acometidas_mapa.estilo_de(name))
    kind, color, width, dash, fill, *_ = json.loads(name[len(PREFIX):])
    rgb = color if color is not None else fill
    if rgb is None:
        label = "Sin color"
    elif max(rgb) < .02:
        label = "Negro"
    elif max(rgb) - min(rgb) < .02:
        label = "Gris" if min(rgb) < .98 else "Blanco"
    else:
        label = "#" + "".join(f"{round(v * 255):02X}" for v in rgb)
    return f"{label} {width:.2f} pt · {'continuo' if dash == '[] 0' else dash}" + (
        " · relleno" if kind == "f" else " · trazo y relleno" if kind == "fs" else "")


_LECTURA = "_pdfcad_lectura_unica"


@contextlib.contextmanager
def lectura_unica(doc):
    """Mientras dura el bloque, `drawings` lee cada hoja de `doc` UNA vez (pedido del usuario
    2026-10-20: reconocer DU06 h.4 con 6 utilidades leía la hoja 13 veces, 10.6 de 18.6 s; un
    mapa compuesto, 4 lecturas de ~3.7 s). Mismo resultado: la lista guardada es la que daría
    otra lectura (la clave lleva hoja, giro y estado de las capas; nadie modifica la lista) y la
    lectura sin `extended` es la extendida sin recortes/grupos ni la clave `level` (verificado:
    `get_drawings()` da exactamente eso). Al salir se suelta (en un mapa compuesto son cientos
    de MB). Anidable: el bloque de afuera manda."""
    if doc is None or _LECTURA in doc.__dict__:
        yield
        return
    doc.__dict__[_LECTURA] = {}
    try:
        yield
    finally:
        doc.__dict__.pop(_LECTURA, None)


def _clave_lectura(page, extended):
    try:
        capas = tuple(bool(c.get("on")) for c in page.parent.layer_ui_configs())
    except Exception:
        capas = ()
    return (page.number, page.rotation, capas, bool(extended))


def _nativos(page, extended, cache):
    """`page.get_drawings(extended=)`, con `cache` (dict de `lectura_unica`) o sin él."""
    if cache is None:
        return page.get_drawings(extended=extended)
    clave = ("nativos",) + _clave_lectura(page, True)
    if clave not in cache:
        cache[clave] = page.get_drawings(extended=True)
    if extended:
        return cache[clave]
    return [{k: v for k, v in p.items() if k != "level"}
            for p in cache[clave] if p.get("type") not in ("clip", "group")]


def drawings(page, *, extended=False):
    """Native drawings plus deterministic identities for unlayered vectors.

    En un mapa sin capas cuya fuente es Type3 sin mapa de caracteres (mapas SIG de
    Phoenix), también los SÍMBOLOS que describe su leyenda (válvulas, hidrantes,
    buzones: glifos de la fuente, no vectores) como círculos virtuales en su propia capa
    (`leyenda_mapa.simbolos_capas`), al final y sin recorte; y las ACOMETIDAS (servicios
    que nacen sobre la red, `acometidas_mapa`) en su capa aparte, no en la de su estilo.
    Dentro de `lectura_unica(doc)`, una sola lectura por hoja."""
    cache = page.parent.__dict__.get(_LECTURA)
    if cache is None:
        return _drawings(page, extended, None)
    clave = _clave_lectura(page, extended)
    if clave not in cache:
        cache[clave] = _drawings(page, extended, cache)
    return cache[clave]


def _drawings(page, extended, cache):
    avance.avisar(_tr("Leyendo los vectores de la hoja…"))
    paths = _nativos(page, extended, cache)
    if any(p.get("layer") for p in paths if p.get("type") not in ("clip", "group")):
        return paths
    out = []
    texto = _tr("Agrupando {n} trazos por su estilo (color, grosor, guiones)…").format(n=_miles(len(paths)))
    for k_av, path in enumerate(paths):
        if k_av % 20000 == 0:
            avance.avisar(texto, k_av, len(paths))
        if not path.get("layer"):
            name = style_name(path)
            if name:
                path = dict(path, layer=name)
        out.append(path)
    from hoja import acometidas_mapa, leyenda_mapa     # usan este módulo: importarlos aquí
    if leyenda_mapa.aplica(page):
        # la leyenda y las acometidas leen los MISMOS trazos por estilo (`leyenda_mapa_lectura.
        # _dibujos`): se los deja listos en vez de releer la hoja (en una compuesta de 36 mapas,
        # 500 000 trazos y ~1 GB por lectura). Mismos trazos, misma capa, mismo orden.
        page.parent.__dict__["_pdfcad_dibujos"] = (page.number, [
            p for p in out if p.get("type") not in ("clip", "group") and (p.get("layer") or "").startswith(PREFIX)])
        avance.avisar(_tr("Buscando las acometidas (servicios a los predios)…"))
        taps = acometidas_mapa.trazos(page)
        if taps:
            out = [dict(p, layer=acometidas_mapa.capa(p["layer"], taps[p["seqno"]]))
                   if p.get("seqno") in taps and (p.get("layer") or "").startswith(PREFIX) and not is_symbol(p["layer"])
                   else p for p in out]
        avance.avisar(_tr("Ubicando los símbolos de la leyenda (buzones, válvulas…)…"))
        out.extend(dict(p) for p in leyenda_mapa.simbolos_capas(page))
    return out


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def layer_rows(paths, hidden=()):
    counts = {}
    for path in paths:
        name = path.get("layer") or ""
        if name.startswith(PREFIX):
            counts[name] = counts.get(name, 0) + 1
    return [dict(name=name, short=style_label(name), number=None,
                 path_count=count, on=name not in hidden, utility="OTRAS",
                 name_group="OTRAS", source="style", letters="",
                 letter_utilities=[], letter_codes={}, letter_paths={},
                 name_utility="", read_codes=[], letter_raw={}, read_counts={})
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
