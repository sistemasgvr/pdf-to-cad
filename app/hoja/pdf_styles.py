"""Virtual layers for flattened vectors. Never modifies the source PDF.

Names depend only on stroke/fill style, so roles survive reopening and page
navigation. Clips and native OCG paths keep their original identity.
"""
from __future__ import annotations

import json

PREFIX = "PDF_STYLE:"


def _color(value):
    return None if value is None else tuple(round(float(v), 3) for v in value)


def style_name(path):
    if path.get("type") in ("clip", "group") or not path.get("items"):
        return ""
    key = (path.get("type"), _color(path.get("color")),
           round(float(path.get("width") or 0), 2),
           " ".join((path.get("dashes") or "[] 0").split()),
           _color(path.get("fill")),
           _opacity(path.get("stroke_opacity")),
           _opacity(path.get("fill_opacity")))
    return PREFIX + json.dumps(key, separators=(",", ":"))


def _opacity(value):
    return None if value is None else round(float(value), 3)


def style_label(name):
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


def drawings(page, *, extended=False):
    """Native drawings plus deterministic identities for unlayered vectors."""
    paths = page.get_drawings(extended=extended)
    if any(p.get("layer") for p in paths if p.get("type") not in ("clip", "group")):
        return paths
    out = []
    for path in paths:
        if not path.get("layer"):
            name = style_name(path)
            if name:
                path = dict(path, layer=name)
        out.append(path)
    return out


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
