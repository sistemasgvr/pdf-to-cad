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

VERSION = "0.9.0"

# Capas de red por GRAVEDAD (tramos entre buzones, con invert inicio/fin).
GRAVITY_LAYERS = {"ALCANTARILLADO", "DRENAJE"}

TIPOS = [
    ("Agua (W)", "AGUA"), ("Alcantarillado (SS)", "ALCANTARILLADO"),
    ("Drenaje (SD)", "DRENAJE"), ("Gas (G)", "GAS"),
    ("Eléctrico (E)", "ELECTRICO"), ("Eléctrico aéreo E(OH)", "ELECTRICO_AEREO"),
    ("Telefonía (T)", "TELECOM"), ("Telefonía aérea T(OH)", "TELECOM_AEREO"),
]
ACI_RGB = {1: (255, 60, 60), 2: (235, 215, 40), 3: (60, 210, 60), 4: (60, 210, 210),
           5: (90, 140, 255), 6: (230, 90, 230), 7: (235, 235, 235), 8: (150, 150, 150),
           30: (255, 150, 40)}
LEADER_TEXT_FT = 3.0
LEADER_ORIENT = [("h", "Horizontal"), ("v", "Vertical"), ("d", "Diagonal")]
Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE = 0, 1, 5, 8
# Índices de las pestañas del inventario (derecha)
TAB_PIPE, TAB_ML, TAB_LEADER, TAB_TEXT, TAB_REGION = 0, 1, 2, 3, 4

# Tipo de red derivado de la capa de la utilidad (para el sidecar 3D).
NETWORK_KIND = {
    "AGUA": "pressure", "GAS": "pressure",
    "ALCANTARILLADO": "gravity", "DRENAJE": "gravity",
    "ELECTRICO": "conduit", "ELECTRICO_AEREO": "conduit",
    "TELECOM": "conduit", "TELECOM_AEREO": "conduit",
}


def network_kind(layer):
    return NETWORK_KIND.get(layer, "unknown")


def diameter_unit(unit):
    """'pulg' → 'in', 'pies' → 'ft'."""
    return "in" if str(unit or "").lower().startswith("pulg") else "ft"


def normalize_regions(regs):
    """Compatibilidad: zonas antiguas eran una lista de puntos; ahora {pts, enabled}."""
    return [r if isinstance(r, dict) else {"pts": r, "enabled": True} for r in regs]


# ── Factories: crean dicts con TODAS las claves (documentan el esquema) ──
def new_pipe(layer, pts, ab=False, name="", diam=0.0, unit="pulg"):
    return {"layer": layer, "pts": list(pts), "ab": bool(ab),
            "name": name, "diam": float(diam), "unit": unit}


def new_text(pos, text, size_ft, font, bold=False, rot=0, free=True):
    return {"pos": pos, "text": text, "size_ft": float(size_ft), "font": font,
            "bold": bool(bold), "rot": int(rot), "free": free}


def new_region(pts, enabled=True):
    return {"pts": list(pts), "enabled": bool(enabled)}


def new_structure(cod, x, y, rim=None, sump=None, part="", net="", world=False):
    return {"cod": cod, "x": x, "y": y, "rim": rim, "sump": sump,
            "part": part, "net": net, "world": bool(world)}


CHANGELOG = [
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
