"""
model.py — Estructuras de datos y constantes del marcado.

El modelo vivo se guarda como listas de dicts JSON-serializables (compatibles con
los .digproj ya guardados). Aquí se centralizan las CLAVES de esos dicts, los
valores por defecto (factories) y los mapeos derivados. No importa Qt.

Esquema de cada elemento (claves de los dicts):
  pipe   = {layer, pts:[(x,y)…], ab:bool, name:str, diam:float, unit:"pulg"|"pies"}
  leader = {text, orient:"h"|"v"|"d", simple:bool, arrow:(x,y), tp:(x,y),
            font:str, size_ft:float, bold:bool, landing:(x,y)|None}
  text   = {pos:(x,y), text:str, size_ft:float, font:str, bold:bool, rot:int, free:bool,
            box:(x,y,w,h)  # solo textos de corrección OCR}
  region = {pts:[(x,y)…], enabled:bool}
  pipe (red gravedad) añade: inv_start, inv_end (float|None), part(str), frm, to (cod buzón),
        net(str nombre de red), world(bool), wstart/wend((x,y) reales si world)
  struct = {cod, x, y, rim:float|None, sump:float|None, part:str, net:str, world:bool}
Coordenadas DIBUJADAS en PÍXELES (se convierten con geometry.to_cad al exportar);
coordenadas IMPORTADAS de Excel ya son reales de mundo (world=True → se usan tal cual).
"""

VERSION = "1.0.0"

# Capas de red por GRAVEDAD (tramos entre buzones, con invert inicio/fin).
GRAVITY_LAYERS = {"ALCANTARILLADO", "DRENAJE"}

# UNIDAD DE TRABAJO para la red 3D. Solo dos opciones — pies o pulgadas — porque
# es lo que consume el plugin C# aguas abajo. NUNCA usar metros en el flujo de
# red 3D (ni en la UI, ni en el JSON, ni al ingresar cotas/diámetros).
WORK_UNITS = ("ft", "in")
DEFAULT_WORK_UNIT = "ft"


def is_valid_work_unit(u):
    return u in WORK_UNITS


# DIÁMETROS de tubería: SIEMPRE en PULGADAS y SOLO de esta lista (los tamaños
# nominales del catálogo imperial de Civil 3D). No se permite un valor libre —
# así lo que se elige aquí coincide 1:1 con un tamaño real del catálogo y no cae
# al "más cercano" al importar. El diámetro es independiente de la unidad de
# trabajo (que rige coordenadas/cotas): el diámetro nunca va en pies.
PIPE_DIAMETERS_IN = [12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78,
                     84, 90, 96, 102, 108, 114, 120, 126, 132, 138, 144]

# MATERIALES de tubería permitidos en la UI. Son exactamente los valores del
# desplegable "Material" de Civil 3D, para que el plugin los setee 1:1 en la
# propiedad Material de cada tubería/estructura.
PIPE_MATERIALS = ["Material sin definir", "Hormigón armado", "Acero corrugado",
                  "Plástico ABS", "Fundición dúctil", "PVC"]
DEFAULT_PIPE_MATERIAL = "Material sin definir"


def nearest_pipe_diameter(value):
    """Devuelve el diámetro estándar (pulg) más cercano a `value` (para migrar
    proyectos viejos cuyo diámetro no esté en la lista)."""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    if v <= 0:
        return PIPE_DIAMETERS_IN[0]
    return min(PIPE_DIAMETERS_IN, key=lambda d: abs(d - v))

TIPOS = [
    ("Agua (W)", "AGUA"), ("Alcantarillado (SS)", "ALCANTARILLADO"),
    ("Drenaje (SD)", "DRENAJE"), ("Gas (G)", "GAS"),
    ("Eléctrico (E)", "ELECTRICO"),
    ("Telefonía (T)", "TELECOM"),
]
ACI_RGB = {1: (255, 60, 60), 2: (235, 215, 40), 3: (60, 210, 60), 4: (60, 210, 210),
           5: (90, 140, 255), 6: (230, 90, 230), 7: (235, 235, 235), 8: (150, 150, 150),
           30: (255, 150, 40)}
# Nombre "amable" para los códigos ACI de AutoCAD.  ACI = AutoCAD Color Index:
# es la paleta clásica numerada 1..255 con la que AutoCAD guarda los colores.
# Usamos el nombre en inglés porque así lo consumen la mayoría de plugins CAD.
ACI_NAME = {1: "red", 2: "yellow", 3: "green", 4: "cyan",
            5: "blue", 6: "magenta", 7: "white", 8: "gray",
            30: "orange"}
LEADER_TEXT_FT = 3.0
LEADER_ORIENT = [("h", "Horizontal"), ("v", "Vertical"), ("d", "Diagonal")]
Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE = 0, 1, 5, 8
# Índices de las pestañas del inventario (derecha)
TAB_PIPE, TAB_ML, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ = 0, 1, 2, 3, 4, 5

# Tipo de red derivado de la CAPA (agrupa las utilidades a nivel de red completa).
#   gravity  → red por gravedad con buzones (alcantarillado, drenaje)
#   pressure → red a presión (agua, gas)
#   conduit  → red de conductos (eléctrico/telefonía; aérea o subterránea)
NETWORK_KIND = {
    "AGUA": "pressure", "GAS": "pressure",
    "ALCANTARILLADO": "gravity", "DRENAJE": "gravity",
    "ELECTRICO": "conduit", "ELECTRICO_AEREO": "conduit",
    "TELECOM": "conduit", "TELECOM_AEREO": "conduit",
}
# Tipo por TUBERIA en el JSON de red 3.0:
#   "pipe"     → tramo dentro de una red con buzones (típico de gravedad)
#   "pressure" → línea a presión (sin buzones intermedios)
# Los eléctricos/telefonía por defecto se tratan como "pipe" (el plugin C# los usa así).
NETWORK_TYPE_DEFAULT = {
    "AGUA": "pressure", "GAS": "pressure",
    "ALCANTARILLADO": "pipe", "DRENAJE": "pipe",
    "ELECTRICO": "pipe", "ELECTRICO_AEREO": "pipe",
    "TELECOM": "pipe", "TELECOM_AEREO": "pipe",
}


MANNINGS_N = {
    "PVC": 0.009, "HDPE": 0.011, "PE": 0.011,
    "RCP": 0.013, "CONCRETO": 0.013, "CONCRETE": 0.013,
    "CLAY": 0.013, "ARCILLA": 0.013, "VCP": 0.013,
    "DIP": 0.011, "DUCTILE": 0.011, "HIERRO": 0.012,
    "CAST IRON": 0.012, "STEEL": 0.012, "ACERO": 0.012,
    "CMP": 0.024, "CORRUGATED": 0.024,
}
COVER_MIN_FT = {
    "AGUA": 3.0, "ALCANTARILLADO": 3.0, "DRENAJE": 2.5,
    "GAS": 2.0, "ELECTRICO": 2.0, "ELECTRICO_AEREO": 0.0,
    "TELECOM": 2.0, "TELECOM_AEREO": 0.0,
}


def mannings_n(material):
    """Coeficiente de Manning por material (fuzzy match).
    Cubre también los nombres de material en español de la UI/Civil 3D
    (Hormigón armado, Acero corrugado, Plástico ABS, Fundición dúctil, PVC)."""
    m = (material or "").upper().strip()
    # "corrugado/corrugated" (CMP) primero: su n es alto y no debe perder contra "acero".
    if "CORRUGAD" in m or "CMP" in m:
        return 0.024
    es = {
        "HORMIG": 0.013, "CONCRET": 0.013,        # hormigón / concreto
        "PVC": 0.009, "ABS": 0.011, "HDPE": 0.011,
        "FUNDIC": 0.011, "DUCTIL": 0.011, "DÚCTIL": 0.011,  # fundición dúctil
        "ACERO": 0.012, "STEEL": 0.012,
    }
    for k, v in es.items():
        if k in m:
            return v
    for k, v in MANNINGS_N.items():
        if k in m:
            return v
    return 0.013


def network_kind(layer):
    """Devuelve gravity/pressure/conduit según la CAPA de la utilidad."""
    return NETWORK_KIND.get(layer, "unknown")


def default_network_type(layer):
    """Valor por defecto de 'network_type' para una utilidad (pipe|pressure)."""
    return NETWORK_TYPE_DEFAULT.get(layer, "pipe")


def layer_color_info(layer):
    """Devuelve {'aci': <int>, 'name': '<en>'} para la capa. `aci` es el índice
    de color en la paleta clásica de AutoCAD; `name` es una palabra en inglés
    ('red', 'blue', ...) para que sea fácil de leer y consumir por el plugin C#.

    Nota: importamos `config` aquí (dentro de la función) para evitar un
    import circular a nivel de módulo. Es una técnica común en Python cuando
    dos módulos necesitan valores el uno del otro pero no de golpe al importar.
    """
    import config as _c
    aci = _c.OUTPUT_LAYERS.get(layer, 7)         # 7 = blanco (fallback neutro)
    return {"aci": int(aci), "name": ACI_NAME.get(aci, "gray")}


def diameter_unit(unit):
    """'pulg' → 'in', 'pies' → 'ft'."""
    return "in" if str(unit or "").lower().startswith("pulg") else "ft"


def normalize_regions(regs):
    """Compatibilidad: zonas antiguas eran una lista de puntos; ahora {pts, enabled}."""
    return [r if isinstance(r, dict) else {"pts": r, "enabled": True} for r in regs]


# ── Factories: crean dicts con TODAS las claves (documentan el esquema) ──
# En Python un "dict" es un mapa {clave: valor}; aquí lo usamos como si fuera
# una "ficha" de la utilidad. Estas funciones son plantillas para que todos los
# dicts nazcan con las mismas claves; los usamos como referencia rápida del
# esquema (qué campos existen y su tipo). No es obligatorio pasar por ellas.
def new_pipe(layer, pts, ab=False, name="", diam=0.0, unit="pulg",
             material="", net_type=""):
    """Crea el dict de una utilidad (tubería/línea).
      layer     → capa del CAD (AGUA, DRENAJE, ...)
      pts       → lista de vértices en píxeles [(x,y), (x,y), ...]
      ab        → True si está abandonada (linetype con barra)
      name/diam/unit → nombre, diámetro y unidad ("pulg" o "pies")
      material  → texto libre (p.ej. "HDPE Corrugado")
      net_type  → "" (=auto según capa) | "pipe" | "pressure"
    """
    return {"layer": layer, "pts": list(pts), "ab": bool(ab),
            "name": name, "diam": float(diam), "unit": unit,
            "material": material, "net_type": net_type}


def new_text(pos, text, size_ft, font, bold=False, rot=0, free=True):
    return {"pos": pos, "text": text, "size_ft": float(size_ft), "font": font,
            "bold": bool(bold), "rot": int(rot), "free": free}


def new_region(pts, enabled=True):
    return {"pts": list(pts), "enabled": bool(enabled)}


def new_structure(cod, x, y, rim=None, sump=None, part="", net="", world=False):
    return {"cod": cod, "x": x, "y": y, "rim": rim, "sump": sump,
            "part": part, "net": net, "world": bool(world)}


CHANGELOG = [
    ("1.0.0", [
        ("release", "Primera versión estable: digitalización PDF → DXF, importación a Civil 3D con familias imperiales de gravedad/presión/conduit, gestión de buzones y cajas, y adjunción automática de Property Sets a tuberías vía Excel."),
    ]),
]
