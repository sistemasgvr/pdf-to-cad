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
  struct = {cod, x, y, rim:float|None, sump:float|None, part:str, part_size:str, net:str,
            world:bool, covered:bool, height_ft:float, curve:bool, radius_ft:float|None,
            hidden:bool}
  hidden=True: el usuario no quiere un buzón real en este vértice (p.ej. un
  vértice auto-detectado que en realidad no es un acceso físico). No se dibuja
  en el lienzo ni en el DXF/Civil3D como manhole visible — se exporta igual el
  punto (la red necesita el nodo para conectar tramos) pero con HIDDEN=1 en el
  XDATA, y el importador de Civil3D (ImportarRed.cs) usa ahí la familia
  "Estructura nula" (invisible, mantiene la topología) en vez de un buzón real.
  Cuando curve=True el struct no es un buzón/caja: es la ESQUINA de un elemento curvo
  (p.ej. el codo de un bancoducto). rim/sump/height_ft/part/part_size no aplican — la
  familia/tamaño de la curva SIEMPRE es la misma de la tubería recta que pasa por ese
  vértice (se muestra de solo lectura en la UI, no se elige aparte). radius_ft es el
  radio deseado en pies; vacío/0 = automático (ImportarRed.cs usa 6× el ancho/diámetro
  interior de la tubería). Se exporta al DXF como PDFCAD_CURVE en vez de PDFCAD_STRUCT
  (sin buzón), y la tubería lleva además NO_MANHOLE_VERTS marcando ese índice.
  ref_centerline = {cod, pts:[(x,y)…]}  — trazo de referencia de una calle,
  DISTINTO de una utilidad (no representa ninguna tubería): se dibuja aparte
  (tab "Centerlines") para calzar contra la calle real al georreferenciar
  (ver geo/georef_dialog.py, botón "Emparejar centerline dibujado"). Se
  exporta al DXF en su propia capa REF_CENTERLINES, sin XDATA.
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


TIPOS = [
    ("Agua (W)", "AGUA"), ("Alcantarillado (SS)", "ALCANTARILLADO"),
    ("Drenaje (SD)", "DRENAJE"), ("Gas (G)", "GAS"),
    ("Eléctrico (E)", "ELECTRICO"),
    ("Telefonía (T)", "TELECOM"),
]
ACI_RGB = {1: (255, 60, 60), 2: (235, 215, 40), 3: (60, 210, 60), 4: (60, 210, 210),
           5: (90, 140, 255), 6: (230, 90, 230), 7: (235, 235, 235), 8: (150, 150, 150),
           30: (255, 150, 40)}
LEADER_TEXT_FT = 3.0
LEADER_ORIENT = [("h", "Horizontal"), ("v", "Vertical"), ("d", "Diagonal")]
Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE = 0, 1, 5, 8
# Índices de las pestañas del inventario (derecha)
TAB_PIPE, TAB_ML, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ, TAB_CURVE, TAB_CL = 0, 1, 2, 3, 4, 5, 6, 7

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


CHANGELOG = [
    ("1.0.0", [
        ("release", "Primera versión estable: digitalización PDF → DXF, importación a Civil 3D con familias imperiales de gravedad/presión/conduit, gestión de buzones y cajas, y adjunción automática de Property Sets a tuberías vía Excel."),
    ]),
]
