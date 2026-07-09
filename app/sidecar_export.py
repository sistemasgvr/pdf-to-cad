"""
sidecar_export.py — Salida "sidecar" JSON para reconstruir la red 3D en Civil 3D.

write_sidecar(win, path) escribe, junto al DXF, un archivo que sigue el contrato
"utility-network/1.0". Todas las coordenadas van en COORDENADAS DE MUNDO CAD (las
mismas del DXF), 2D — se obtienen con win._to_cad sobre cada punto en píxeles.
La Z la resuelve Civil 3D con las cotas de las etiquetas (otra herramienta).
"""
import json
import os
import re

from model import VERSION, network_kind, diameter_unit

_DECIMAL = re.compile(r"\d+\.\d+")


def label_hint(text):
    """Pista opcional del tipo de cota. Ante la duda, 'generic'."""
    u = (text or "").upper()
    if "INV" in u:
        return "invert"
    if "RIM" in u:
        return "rim"
    return "generic"


def build_model(win):
    """Construye el dict del sidecar (coordenadas ya en mundo CAD)."""
    utilities = []
    for i, p in enumerate(win.pipes, 1):
        verts = []
        for (x, y) in p["pts"]:
            cx, cy = win._to_cad(x, y)
            verts.append({"x": round(cx, 4), "y": round(cy, 4)})
        utilities.append({
            "id": f"U{i}",
            "type": p["layer"],
            "network_kind": network_kind(p["layer"]),
            "name": p.get("name") or f"{p['layer']}-{i}",
            "diameter": {"value": p.get("diam", 0), "unit": diameter_unit(p.get("unit", "pulg"))},
            "abandoned": bool(p.get("ab")),
            "vertices": verts,
            "elevation_source": "labels",
        })

    labels = []
    n = 1
    for tm in win.text_marks:                     # todos los textos libres / correcciones
        cx, cy = win._to_cad(*tm["pos"])
        labels.append({"id": f"T{n}", "text": tm.get("text", ""),
                       "x": round(cx, 4), "y": round(cy, 4), "hint": label_hint(tm.get("text", ""))})
        n += 1
    for ld in win.leaders:                        # texto de los Multileaders (leaders con texto)
        if not ld.get("text"):
            continue
        cx, cy = win._to_cad(*ld["tp"])
        labels.append({"id": f"T{n}", "text": ld["text"],
                       "x": round(cx, 4), "y": round(cy, 4), "hint": label_hint(ld["text"])})
        n += 1

    return {
        "schema": "utility-network/1.0",
        "source": {
            "pdf": os.path.basename(win.pdf_path) if win.pdf_path else "",
            "page": int(win.page_idx) + 1,
            "app_version": VERSION,
            "units": "ft",
        },
        "notes": ("Todas las coordenadas ya están en coordenadas de mundo CAD "
                  "(mismas del DXF), 2D. Z se resuelve en Civil 3D."),
        "utilities": utilities,
        "labels": labels,
    }


def write_sidecar(win, path):
    """Escribe el JSON en `path`. Devuelve (n_utilities, n_labels)."""
    data = build_model(win)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return len(data["utilities"]), len(data["labels"])
