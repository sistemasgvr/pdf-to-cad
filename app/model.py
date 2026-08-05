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

VERSION = "0.12.0"

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
    ("0.12.0", [
        ("added", "Unidad de trabajo obligatoria para la red 3D: PIES (ft) o PULGADAS (in). Selector visible arriba y en la barra de estado. La misma unidad se usa para ingresar cotas/diámetros y aparece en el JSON como 'units'."),
        ("changed", "El JSON de red exporta TODAS las coordenadas, cotas y diámetros en la unidad de trabajo del proyecto. Se retiró el uso de metros del flujo de red 3D."),
        ("changed", "Etiquetas de campo dinámicas: Diámetro (ft/in), Invert inicio/fin (ft/in), y en el diálogo de Buzones rim/sump también muestran la unidad activa."),
        ("changed", "Se quitó el combo per-pipe de unidad ('pulg'/'pies') en Propiedades: la unidad la fija el proyecto."),
        ("changed", "Importar Excel de red: los metros del archivo se convierten a la unidad de trabajo del proyecto al importar (X, Y, Z, C.SOLERA, Zi, Zf, Altura)."),
        ("fixed", "Cotas de recorrido, no por segmento: cuando una polilínea tiene N vértices, el invert de inicio se pone SOLO en el 1er vértice y el de fin SOLO en el último; los intermedios van null (el plugin C# los interpola)."),
        ("added", "Validaciones no bloqueantes: aviso si un recorrido tiene invert de inicio sin fin (o viceversa) y si una utilidad de capa a presión (agua/gas) fue marcada como red con buzones."),
        ("changed", "El .digproj guarda la unidad de trabajo (retrocompat: proyectos viejos se cargan detectando la unidad más común entre sus pipes)."),
    ]),
    ("0.11.0", [
        ("added", "El JSON de red 3.0 lleva ahora en cada tubería: material (texto libre del usuario), color (índice ACI + nombre de la capa) y network_type (pipe/pressure)."),
        ("added", "Panel de Propiedades: se agregaron campos Material y Tipo de red (Automático / Con buzones / A presión). El diámetro ya viajaba desde 0.10; ahora también material y tipo."),
        ("changed", "Panel de herramientas reorganizado como ACORDEÓN: cada acción (Dibujar utilidad, Multileader, Leader, Texto libre, Borrar zona, Georreferenciación, Cotas/red, OCR/ICR) tiene su propia sección. Al abrir una sección solo se ven sus opciones."),
        ("changed", "Al seleccionar un Multileader o Texto en el inventario, se abre automáticamente su sección del acordeón para editarlo."),
        ("changed", "Manual de usuario reescrito (Ayuda → Manual de usuario): cubre todas las funciones — georreferenciación, cotas, materiales/colores/tipo de red, importación Excel, exportación de red 3D — con una sección '¿Qué significa cada dato y de dónde sale?'."),
        ("changed", "Comentarios pedagógicos añadidos al código nuevo y tocado (Qt, pyproj, scikit-image, ezdxf, openpyxl) para que sea fácil de mantener por alguien principiante."),
    ]),
    ("0.10.0", [
        ("fixed", "Se eliminó la entrada de menú duplicada que decía 'Exportar red 3D (JSON)' pero exportaba un DXF; ahora hay UNA sola opción 'Exportar red 3D (JSON)' que emite el JSON."),
        ("fixed", "El diámetro de la utilidad ya viaja siempre en cada tubería del JSON (antes se perdía)."),
        ("changed", "Contrato único de red: schema utility-network/3.0. Un solo archivo con array 'networks[]' agrupado por (capa, red); nunca mezcla capas (agua con drenaje, etc.)."),
        ("changed", "Cada polilínea con N vértices produce N−1 tramos consecutivos (antes se colapsaba a un solo tramo, con pérdida de datos)."),
        ("added", "En redes por gravedad, cada vértice compartido entre tramos es una estructura (buzón); el panel Buzones ahora detecta también los vértices intermedios de las polilíneas."),
        ("removed", "Se retiró la salida antigua schema 1.0 (sidecar '.utilities.json' junto al DXF)."),
    ]),
    ("0.9.0", [
        ("added", "Georreferenciación por puntos de control (menú Georreferencia → Georreferenciar…): calza el plano sobre imagen satelital (Esri) / calles (OSM) con un mapa embebido y obtiene coordenadas de mundo reales en UTM."),
        ("added", "Con georreferencia activa, TODA la exportación (DXF y JSON de red) usa las coordenadas UTM reales en vez de la escala del titleblock; el esquema del JSON no cambia (solo cambian las X,Y)."),
        ("added", "Búsqueda de direcciones (Nominatim/OSM) y reproyección lon/lat↔UTM (pyproj); ajuste afín/similar con RMS (scikit-image)."),
        ("added", "La barra de estado indica si el plano está georreferenciado y con qué EPSG; el .digproj guarda la georreferencia (los proyectos sin ella siguen abriendo con la escala de siempre)."),
        ("changed", "AVISO: calzar sobre satélite da coordenadas APROXIMADAS (metros), útiles para trazado/anteproyecto, NO grado construcción; el dato topográfico real viene del levantamiento/Excel."),
    ]),
    ("0.8.0", [
        ("added", "Cotas de red: en Propiedades de una utilidad de gravedad (alcantarillado/drenaje) puedes ingresar 'Invert inicio', 'Invert fin' y 'Part' (tipo de pieza)."),
        ("added", "Gestión de buzones/nudos: detecta los buzones por los extremos de las tuberías (extremos compartidos = mismo buzón) y edita su Cod, rim, sump y part."),
        ("added", "Importar Excel de red (hojas BUZONES/TUBERIAS, encabezados en la fila 5): vuelca cotas, diámetros y nombres al mismo modelo."),
        ("added", "Exportar 'red 3D (JSON resuelto)' con el contrato utility-network/2.0 (una red por hoja/red), lista para el plugin C#."),
        ("changed", "El .digproj ahora guarda también los buzones y las cotas (los proyectos antiguos siguen abriendo)."),
    ]),
    ("0.7.0", [
        ("changed", "Refactor interno: el programa se dividió en módulos (app_window, model, geometry, ocr, dxf_export, sidecar_export). Mismo comportamiento y mismos proyectos .digproj."),
        ("added", "Nueva salida 'Exportar red 3D (JSON)': junto al DXF se escribe un archivo .utilities.json con la red (tipo, red a presión/gravedad/conducto, diámetro, vértices en coordenadas CAD y etiquetas) para reconstruir el 3D en Civil 3D."),
    ]),
    ("0.6.7", [
        ("changed", "Al exportar a DXF, cada Multileader se escribe como entidad MULTILEADER nativa (flecha + directriz + texto); si el visor no lo soporta, se dibuja explícito como respaldo."),
        ("fixed", "Ayuda → 'Acerca de…' ya no aparecía en blanco (fallaba al mostrar entradas de tipo 'changed' del historial)."),
    ]),
    ("0.6.6", [
        ("added", "Con un Leader seleccionado, Ctrl+T entra directo a editar sus vértices (posición/longitud)."),
        ("changed", "Al exportar a DXF, los Leaders simples se escriben como entidad LEADER nativa (con punta de flecha) siguiendo sus vértices; si el visor no lo soporta, se dibujan explícitos como respaldo."),
    ]),
    ("0.6.5", [
        ("added", "Pestaña de inventario 'Leaders' independiente de 'Multileaders'."),
        ("added", "Editar Leaders (horizontal/vertical/diagonal): selecciona el Leader, pulsa 'Editar/mover' y arrastra sus vértices (posición y longitud) o el trazo completo. Enter/Esc termina la edición."),
    ]),
    ("0.6.4", [
        ("added", "Leader diagonal con landing (3 clics): cabeza de flecha → inicio del landing (bisagra) → final del cuerpo."),
        ("added", "En modo Leader, Enter finaliza el comando (además de Esc)."),
    ]),
    ("0.6.3", [
        ("added", "'Colocar Leader' tiene orientación (Horizontal/Vertical/Diagonal): 1er clic = cabeza de flecha, 2º clic = final del cuerpo. En Horizontal/Vertical el cuerpo se mantiene recto al eje."),
        ("changed", "En modo Leader el panel se titula 'Leader' y muestra solo la Orientación; se oculta el estilo de texto (el Leader no lleva texto)."),
    ]),
    ("0.6.2", [
        ("changed", "'Colocar Leader' ahora coloca solo la flecha, sin texto: 1er clic = cabeza de flecha, 2º clic = final del cuerpo."),
        ("fixed", "El Leader simple ya no se mezclaba con el Multileader al encadenar colocaciones (se perdía el modo)."),
    ]),
    ("0.6.1", [
        ("added", "El botón Exportar DXF es un desplegable: PDF + anotaciones, solo el PDF, o solo las anotaciones."),
        ("added", "Nueva herramienta 'Colocar Leader': una directriz recta simple (punta → texto), aparte del Multileader."),
    ]),
    ("0.6.0", [
        ("fixed", "El plano base ya NO se restilea: el linetype con letra (─ W ─) se aplica solo a la utilidad que dibujas (por entidad), no a la capa."),
        ("fixed", "El resaltador/anotaciones del PDF (rellenos semitransparentes) ya no se digitalizan."),
        ("fixed", "El Multileader se digitaliza como geometría exacta (línea + punta + texto) agrupada, igual que en la vista previa: el texto y la cola ya salen bien."),
    ]),
    ("0.5.2", [
        ("fixed", "El texto del Multileader vertical ahora queda pegado a la línea (antes salía muy separado)."),
        ("fixed", "Al digitalizar, la entidad MULTILEADER sigue exactamente la línea dibujada (no reencamina las diagonales/verticales)."),
    ]),
    ("0.5.1", [
        ("added", "El tipo de utilidad ahora es un menú desplegable (con su color), más compacto."),
    ]),
    ("0.5.0", [
        ("added", "El Multileader tiene estilo de texto propio (fuente, altura, negrita) editable, y se exporta a CAD con ese estilo."),
        ("added", "Extender vértice sin ventana emergente: casilla 'continuar la misma utilidad' (si es un extremo) o rama nueva."),
        ("added", "Cada utilidad tiene propiedades: nombre, diámetro y unidad (pies/pulgadas), que se exportan como dato (XDATA) al DXF."),
        ("fixed", "Multileader horizontal/vertical: la cola se adapta al largo del texto y el texto queda bien ubicado respecto a la línea y la flecha."),
        ("fixed", "El Multileader se ve al instante al colocarlo (ya no hace falta pulsar Escape)."),
        ("fixed", "En modo Multileader puedes cambiar orientación y texto y se aplican al siguiente que coloques."),
        ("added", "Al editar un texto puedes rotarlo con imán a 0/45/90/135/180/225/270/315°."),
        ("fixed", "El cambio de página con Enter funciona."),
        ("added", "Seleccionar Multileader con clic en el dibujo."),
        ("added", "Ctrl+C / Ctrl+V para duplicar el elemento seleccionado (Multileader, utilidad o texto)."),
    ]),
    ("0.4.1", [
        ("fixed", "Se recuperaron los tipos de línea con letra al exportar: ─ W ─, ─ SS ─, ─ G ─, y la variante abandonada ─/─ W ─. El modo fiel del plano base ya no borra el estilo de las utilidades marcadas."),
    ]),
    ("0.4.0", [
        ("added", "Interfaz reorganizada: herramientas a la izquierda, inventario a la derecha, barra de acción arriba y barra de estado con coordenadas y escala."),
        ("fixed", "Multileader horizontal: el texto sale al lado del extremo de la línea."),
        ("fixed", "Multileader vertical: el texto se pega más a la línea sin tocarla."),
        ("fixed", "Al editar un Multileader, el salto de línea queda más cerca de la línea."),
        ("added", "Colocar Multileader en cadena: tras poner uno queda listo para el siguiente (Esc para salir)."),
        ("fixed", "El cambio de página al escribir un número y dar Enter (o salir del campo) ya funciona."),
        ("added", "Al extender un vértice puedes elegir: misma utilidad o utilidad nueva."),
        ("removed", "Se quitaron las flechas ▲▼ del campo de altura de texto (quedan los botones − / +)."),
    ]),
    ("0.3.1", [
        ("added", "En el cambiador de páginas se puede escribir un número de página y dar Enter."),
        ("fixed", "El editor de texto es una caja flotante: Enter aplica y clic fuera también dibuja el texto."),
        ("fixed", "El botón de aumentar la altura del texto ya funciona (se agregaron botones − / +)."),
        ("fixed", "Multileader vertical y horizontal ahora son perfectamente rectos y la punta de flecha sale recta."),
        ("fixed", "La landing del Multileader se adapta al largo del texto."),
        ("fixed", "En Diagonal el texto ya no se cruza con la landing (queda encima)."),
        ("fixed", "Editar Multileader: Ctrl+Shift+Enter hace salto de línea al otro lado de la landing."),
        ("fixed", "Al cambiar de hoja los textos y Multileaders ya no se dibujan gigantes (tamaño acotado)."),
        ("fixed", "Extender desde un vértice (forma de F) tolera el temblor del ratón al hacer clic."),
    ]),
    ("0.3.0", [
        ("fixed", "Navegación de páginas con botones ◀ ▶ (ya no hay que escribir el número primero)."),
        ("fixed", "El texto libre se agrega con Enter; ya no depende de hacer clic en el panel."),
        ("added", "Enter aplica el texto/Multileader; Ctrl+Shift+Enter (o Shift+Enter) hace salto de línea."),
        ("added", "Textos seleccionables, editables (doble clic) y movibles, con estilo modificable después de crearlos."),
        ("added", "Multileader editable (doble clic) con saltos de línea."),
        ("fixed", "Horizontal ahora es recto (sin quiebre); la opción con landing pasó a Diagonal."),
        ("added", "Vertical recto con texto vertical pegado a la línea."),
        ("added", "Extender desde un vértice: clic en un vértice y luego en el dibujo para ramificar (forma de F)."),
        ("added", "Los Multileader se digitalizan como entidad MULTILEADER de CAD (no como grupo)."),
        ("fixed", "Los polígonos de borrado quedan detrás de las tuberías (solo tapan el plano)."),
        ("added", "El área de listas se puede agrandar arrastrando el separador."),
        ("added", "Se renombró todo a 'Multileader'."),
    ]),
    ("0.2.0", [
        ("fixed", "Error al abrir un proyecto (objetos gráficos ya eliminados y zonas en formato antiguo)."),
        ("fixed", "Enter finaliza de forma fiable la utilidad que estás dibujando."),
        ("added", "Cerrar proyecto: pregunta si deseas guardar los cambios."),
        ("added", "Aviso de cambios sin guardar al cerrar la aplicación."),
        ("added", "Historial de versiones desplegable en 'Acerca de'."),
    ]),
    ("0.1.0", [
        ("added", "Utilidad abandonada con línea ──/── W ──."),
        ("added", "Multileader vertical; edición de texto; texto libre con estilos."),
        ("added", "Panel de zonas borradas; selección por clic; guardar en el mismo archivo."),
        ("added", "Menús Archivo / Edición / Ayuda con manual y atajos."),
        ("base", "Dibujar utilidades, Multileaders, texto, borrar zonas, OCR/ICR, proyectos y export a DXF."),
    ]),
    ("0.0.0", [
        ("base", "Primera versión interna: digitalización PDF→DXF y marcado básico de utilidades."),
    ]),
]
