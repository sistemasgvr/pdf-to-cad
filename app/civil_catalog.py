"""
civil_catalog.py — Detección de instalaciones de Civil 3D y listado de familias
del catálogo imperial de estructuras (buzones).

Uso típico:
    versions = installed_versions()       # ['2025', '2027']
    families = imperial_structures(2025)  # [('AeccStructConcentric…', 'Concentric Cylinder Rect Frame', 'Junction Structures with Frames'), …]
"""
import os
import re

# Rango soportado: Civil 3D 2024 → 2027 (fácil de extender).
SUPPORTED_YEARS = (2024, 2025, 2026, 2027)

# Sufijos de idioma que Autodesk mete en la ruta. 'esp' (español), 'enu' (inglés
# EE.UU.), etc. Se buscan en ese orden.
LANG_PREFERENCES = ("esp", "enu", "fra", "deu", "ita", "ptb")

# Subcarpetas dentro de "US Imperial Structures" que contienen los .xml.
STRUCTURE_SUBFOLDERS = (
    "Junction Structures with Frames",
    "Junction Structures without Frames",
    "Inlet-Outlets",
    "Simple Shapes",
)


def _programdata_root():
    """Raíz de C:\\ProgramData (respeta la variable de entorno)."""
    return os.environ.get("ProgramData", r"C:\ProgramData")


def catalog_root(year):
    """Devuelve la carpeta 'US Imperial Structures' de la versión indicada, o
    None si no está instalada."""
    base = os.path.join(_programdata_root(), "Autodesk", f"C3D {year}")
    if not os.path.isdir(base):
        return None
    for lang in LANG_PREFERENCES:
        p = os.path.join(base, lang, "Pipes Catalog", "US Imperial Structures")
        if os.path.isdir(p):
            return p
    return None


def installed_versions():
    """Lista años de Civil 3D instalados (2024–2027) que tienen el catálogo
    imperial disponible."""
    return [y for y in SUPPORTED_YEARS if catalog_root(y) is not None]


def _pretty_from_filename(fname):
    """AeccStructConcentricCylinderRectFrame_Imperial.xml → Concentric Cylinder Rect Frame"""
    base = os.path.splitext(fname)[0]
    for prefix in ("AeccStruct", "Aecc"):
        if base.startswith(prefix):
            base = base[len(prefix):]
            break
    if base.endswith("_Imperial"):
        base = base[:-len("_Imperial")]
    # CamelCase → palabras con espacio
    base = re.sub(r"(?<!^)(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", base)
    return base.strip()


def imperial_structures(year):
    """Devuelve la lista de familias del catálogo imperial de la versión indicada.
    Cada elemento es un tuple (id, pretty_name, subfolder). id = basename sin
    extensión (identificador único que se guarda en el proyecto y se lee del
    XDATA del DXF)."""
    root = catalog_root(year)
    if root is None:
        return []
    out = []
    for sub in STRUCTURE_SUBFOLDERS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".xml"):
                continue
            fid = os.path.splitext(fn)[0]
            out.append((fid, _pretty_from_filename(fn), sub))
    return out
