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
  (tab "Centerlines") y sirve de referencia visual (e imán de puntos de
  control) al georreferenciar. Se exporta al DXF en su propia capa
  REF_CENTERLINES, sin XDATA.
Coordenadas DIBUJADAS en PÍXELES (se convierten con geometry.to_cad al exportar);
coordenadas IMPORTADAS de Excel ya son reales de mundo (world=True → se usan tal cual).
"""

VERSION = "1.1.8"

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
TAB_PIPE, TAB_ML, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ, TAB_CURVE, TAB_CL, TAB_DB = 0, 1, 2, 3, 4, 5, 6, 7, 8

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
    ("1.1.8", [
        ("changed", "Las utilidades eléctricas abandonadas se dibujan del mismo color que la activa. Solo se distinguen por (AB) en la lista; ya no van a trazos ni con otro matiz."),
    ]),
    ("1.1.7", [
        ("fixed", "Un ramal de la misma capa eléctrica (guiones del linetype, aunque uno sea un poco más largo, más el codo) se une a la centerline: nace en la línea principal, quiebra en el codo y el otro extremo queda libre. Ya no se pinta violeta como leader. Un trazo continuo solo, sin contacto con esa red, sigue fuera."),
    ]),
    ("1.1.6", [
        ("fixed", "El reconocimiento reconstruye cada capa OCG de líneas por separado: una capa eléctrica que no es la utilidad (p.ej. U-PROP-ESFV-ELEC-STRUCT) ya no se cose ni se imana con C-ELEC-UNGD-E. Las bóvedas solo cuentan si son un símbolo compacto con caja/círculo; un linetype disfrazado de estructura no atrae extremos. Los ramales de la misma capa que quedaban sin dibujar se cubren si son guiones del patrón."),
    ]),
    ("1.1.5", [
        ("added", "Utilidades eléctricas ABANDONADAS: la capa de estado «-A» (C-ELEC-UNGD-A, linetype «──/── e ──») se reconoce igual que la activa pero se importa marcada como abandonada (AB), como la casilla «Abandonado» del dibujo manual (en el DXF sale con el linetype discontinuo). Las barras «/» del linetype se tratan como marcadores (no quedan «sin cubrir»); el contorno de bóveda que el plot dibuja en esa misma capa se detecta como bóveda (la línea para en su borde y el contorno no se dibuja); activas y abandonadas se reconstruyen por separado (son pipes distintas). En la vista previa van a trazos y la lista de capas las señala «(abandonada)»."),
        ("changed", "Bóvedas: un trazo continuo (sin patrón) que solo nace en el borde y sale hacia afuera ya no se toma como continuación de la línea que llega por el lado opuesto (ambos paran en el borde); sí cuenta si el trazo entra y cruza la bóveda."),
        ("fixed", "Un ramal abandonado que nace sobre su propia línea junto a una bóveda activa ya no se «engancha» a esa bóveda con un tramo inventado: un extremo que muere sobre otra línea es una T con esa línea (nos basamos en las capas)."),
        ("changed", "Precisión de los puntos de quiebre: un extremo que muere sobre otra corrida es una T sobre ella (antes podía formar una esquina fuera de la línea con un tercer extremo cercano); los ticks «┤» de fin de tramo quedan como extremo–T–extremo y sus puntas nunca se unen a otra línea (ni a la que muere a 4 pt de ellas); una esquina nunca se traga más de media corrida; un cruce en X con hueco sigue siendo una sola línea; la línea que atraviesa una bóveda y sigue un trozo corto conserva borde, nodo, borde y su extremo; y las transiciones suaves se simplifican a 1.5 pt (las curvas siguen a 1 pt). Hoja 9 del DU06: 98.4 % → 100 %."),
        ("changed", "Ya no se pide confirmar las capas eléctricas: las capas de líneas y bóvedas se asignan solas por su nombre y la vista previa del reconocimiento las muestra de forma informativa (cabecera con la utilidad y su color, «Capas usadas: Líneas / Bóvedas»). Si el plot usa otros nombres, «Ajustar capas…» permite indicarlas a mano y vuelve a reconocer; si no se encontró ninguna, la vista previa lo avisa y no deja importar."),
        ("added", "«Cambiar de hoja…» en la vista previa del reconocimiento: lista de hojas → capas de la hoja → vista previa de la hoja nueva ya reconocida, sin pasar por el editor."),
    ]),
    ("1.1.4", [
        ("changed", "Paso «Capas de la hoja» reorganizado: las capas se agrupan por utilidad (Agua, Alcantarillado, Drenaje, Gas, Eléctrico, Telefonía y Otras — las mismas del desplegable «Tipo de utilidad», cada una con su color) a partir del nombre de la capa; el panel «Utilidades» filtra la lista (o «Todas») y combina con el buscador."),
        ("added", "Cambio de hoja sin salir del paso de capas (◀ Hoja N / M ▶): la vista previa y los conteos se actualizan y las capas marcadas se conservan. Después, al cambiar de hoja en el editor (◀ ▶ o nº de página) la nueva hoja se reconoce con las mismas capas y roles ya confirmados y se muestra la vista previa para importar."),
    ]),
    ("1.1.3", [
        ("fixed", "Reconocimiento eléctrico: centerlines más continuas y precisas (snap de extremos, colapso de trazos paralelos, cosido colineal por grafo y Douglas–Peucker). Menos cortes artificiales y menos dobles desfasados en el preview."),
    ]),
    ("1.1.2", [
        ("added", "Tras elegir capas, se confirman roles OCG (líneas / bóvedas / ignorar) por si el plot usa otros nombres."),
        ("added", "El reconocimiento eléctrico vuelve a correr: preview con líneas listas (inicio, quiebres, fin) como dibujo manual y bóvedas VALT como puntos; Continuar las importa al editor (pipes ELECTRICO + cajas)."),
    ]),
    ("1.1.1", [
        ("added", "Vista previa de reconocimiento al abrir un PDF bien ploteado: eliges la hoja, se reconocen utilidades eléctricas subterráneas (capas C-ELEC-UNGD) y se muestran dibujadas como el trazo manual. Solo preview — aún no se importan al inventario."),
        ("added", "Reconocimiento eléctrico reconstruido desde cero (núcleo geométrico nuevo): aprende el patrón del linetype del propio plano (guiones, letras «e», huecos), reconstruye cada corrida de inicio a fin con sus quiebres, resuelve esquinas por intersección exacta, T, quiebres suaves, arcos discontinuos y bóvedas como vértices compartidos. Un extremo nunca se mueve fuera de su propia recta, así ninguna línea se inclina. Cobertura medida en el DU06: 97–100 % por hoja (antes 75–89 %)."),
        ("added", "La vista previa muestra control de calidad: porcentaje de cobertura, guiones que ninguna línea cubrió (naranja), trazos continuos fuera de patrón como leaders/flechas (violeta, no se importan) y bóvedas sin línea cercana."),
        ("added", "Al importar, los quiebres sin bóveda (esquinas suaves, arcos) quedan como cajas OCULTAS (Estructura nula en Civil 3D): solo las bóvedas reales salen como CAJA visible. Las pipes reconocidas guardan el tipo de cada vértice en el proyecto."),
        ("fixed", "Las líneas reconocidas ya no superan el marco de la vista de planta: la geometría se recorta por los clips reales del PDF (marco de la vista, XCLIP de referencias) y un extremo creado por el recorte no forma esquinas ni se prolonga. Los codos «⌒» que conectan un conduit con el borde de la bóveda se reconocen como curvas (antes se descartaban como letras)."),
        ("changed", "Bóvedas, ajustes finos: la llegada al nodo interior es un solo tramo recto borde→nodo (sin quiebre intermedio); un stub corto colineal con una línea al otro lado de la bóveda cuenta como continuidad de esa línea; las curvas/continuas que salen de una bóveda nunca se cosen entre sí en sus puntas (conduits cortados por el límite de la vista); los trozos cortos que tocan una bóveda se conservan y se conectan al nodo de llegada más cercano."),
        ("added", "Reglas de bóveda según los apuntes (revisadas): toda línea llega al buzón por su propia recta y SIEMPRE deja un punto de quiebre donde choca con el borde (entrada y salida). Dentro del buzón no se inventa nada a partir del símbolo: si una línea de red lo atraviesa (o dos llegan colineales por lados opuestos), el nodo interior se calcula con las llegadas —sobre la línea que atraviesa, en la intersección si son dos— y las demás llegan a él siguiendo su eje con un quiebre corto. Si ninguna línea lo atraviesa (bóveda grande, stubs, curvas), cada una termina en el borde y ahí queda su caja: el usuario completa a mano. Dos conduits que convergen en ángulo rasante nacen en un vértice compartido sobre la línea principal; las corridas se parten donde los guiones se apartan >0.75 pt para que todo vértice quede sobre la línea de la capa."),
        ("fixed", "Una línea CAD con deriva de 1–2 pt (dibujo casi recto) ya no sale como dos líneas superpuestas terminando en la misma bóveda: cada guión se asigna a la recta que mejor ajusta y las corridas superpuestas se funden. La línea que atraviesa una bóveda se importa como UNA sola polilínea con la bóveda de vértice (antes se partía en dos en el nodo)."),
        ("added", "Paso «Capas de la hoja» antes de la vista previa: lista todas las capas del plano (con su cantidad de trazos) y permite mostrarlas u ocultarlas con casillas, viendo el resultado en vivo. Las capas ocultas no se dibujan en el lienzo ni se usan en el reconocimiento. Incluye buscador y botones Mostrar/Ocultar todas."),
    ]),
    ("1.1.0", [
        ("added", "Nuevo diseñador de Bancoductos (Duct Bank): dibuja la sección con envolvente, márgenes, redondeo de esquinas, rejilla de distribución, reglas de separación y de resguardo al borde. Cada bancoducto se asigna a una utilidad del plano y al importar en Civil 3D se crea el sólido 3D del contenedor + los conductos internos como tuberías reales."),
        ("added", "Panel «Bancoductos» en el inventario derecho: lista todos los bancoductos del proyecto con botones Nuevo / Editar / Duplicar. Doble-click en una fila abre el diseñador ya cargado con ese bancoducto. Click derecho sobre una tubería del plano ofrece «Crear/Editar bancoducto»."),
        ("added", "Opción para elegir si se dibuja el contenedor 3D del bancoducto o solo los conductos internos (útil cuando el contenedor de concreto ya existe en el DWG)."),
        ("added", "Selector de idioma en Archivo → Opciones… La app se puede alternar entre Español e Inglés; la elección se recuerda al reabrir."),
        ("added", "Diálogo de Opciones en el menú Archivo (pensado para crecer con más preferencias en el futuro)."),
        ("added", "Documento «Cómo funciona el proyecto» en formato interactivo (docs/arquitectura.html): explicación por carpetas y archivos en lenguaje sencillo, con diagramas."),
        ("added", "Menú contextual (click derecho) en las tuberías del inventario: crear o editar el bancoducto asignado sin salir del contexto."),
        ("changed", "La cota invert del bancoducto ahora manda el FONDO del contenedor (parte inferior externa), como en las tuberías normales. Los conductos internos se distribuyen correctamente hacia arriba desde ese fondo."),
        ("changed", "Las cotas por tramo (VertexInv) del pipe padre ahora se aplican también al sólido del contenedor y a los conductos internos — antes solo se usaban en tuberías normales."),
        ("changed", "Zoom del lienzo principal: acercar hasta 4000% y alejar hasta 30% con la rueda o los botones (antes 1000% / 10% y el botón se saltaba el límite)."),
        ("changed", "El botón «+ Nuevo» del panel de bancoductos ahora sí crea uno desde cero (antes cargaba el último diseño)."),
        ("changed", "Rediseño del diseñador de bancoductos: acciones «Cancelar / Guardar y cerrar» debajo del canvas, «Puntero» unificado (click selecciona, arrastra mueve), banner rojo sobre el canvas cuando hay problemas, panel «Identificación» al inicio, panel «Conducto» contextual (cambia entre modo nuevo/editar)."),
        ("changed", "Modo oscuro mejorado: el bancoducto asignado a la tubería seleccionada ya se lee sin problemas, y el título en «Duct Bank: ...» dejó de salir con azul ilegible sobre fondo negro."),
        ("changed", "Los tamaños de tubería que faltan en el catálogo se instalan automáticamente al importar (evita el fallback silencioso a un diámetro distinto)."),
        ("fixed", "Los conductos del bancoducto ya no sobresalen del contenedor en el render 3D (Civil 3D dibuja al diámetro exterior; ahora se fuerza pared 0 en las medidas custom que la app inyecta al catálogo)."),
        ("fixed", "Rediseñar el bancoducto de una utilidad ya no crea dos sólidos superpuestos: se sobreescribe por identidad, no por nombre."),
        ("fixed", "El sólido del bancoducto sigue las cotas de la tubería padre (antes quedaba a Z=0 mientras los conductos usaban las cotas correctas)."),
        ("fixed", "Al abrir el diseñador desde una tubería, ahora carga el bancoducto asignado a ESA tubería (antes cargaba el último editado)."),
    ]),
    ("1.0.1", [
        ("added", "Alineamientos curvos: el eje de la red sigue el mismo arco (mismo radio) que la tubería curva, en vez de cortar la esquina en recta."),
        ("added", "Botón «Agregar tubería curva»: seleccionas dos tuberías y un radio opcional, y crea la curva tangente y redondea también el eje."),
        ("added", "Selector de versión e idioma de Civil 3D en el toolbar; se guarda en el proyecto y se repone solo al reabrirlo."),
        ("added", "Código de sistema de coordenadas (Huso) en la georreferenciación: el dibujo queda seteado con ese sistema al importar la red en Civil 3D."),
        ("added", "Botón «Opacidad» con deslizable para atenuar solo el PDF, y fondo blanco/negro detrás del PDF."),
        ("added", "Georreferenciación: indicador de carga al buscar/descargar el mapa, e imanes a las esquinas redondeadas de las parcelas."),
        ("fixed", "Familias por defecto: ahora se coloca la familia elegida (se emparejan por su GUID, no por el nombre traducido) — antes salía una familia distinta."),
        ("fixed", "Buzones ocultos ya no aparecen como una estructura visible al importar la red."),
        ("fixed", "Redes de presión: los codos salen a la elevación correcta (sobre el eje del tubo)."),
        ("fixed", "Cotas por tramo: ya no se pierden al cerrar y reabrir el proyecto, y la tabla ya no aparece en la pestaña Buzones."),
        ("fixed", "Georreferenciación: el ajuste ya no deforma el plano (transformación de similaridad) y el RMSE es real aunque uses 3 puntos."),
        ("fixed", "Las zonas borradas ya no aparecen en la ventana de georreferenciación."),
        ("changed", "Coordenadas mostradas como X, Y, Z (antes N, E), con 4 decimales; muestran el código de Huso si lo fijaste."),
        ("changed", "Los nombres de familias se muestran en el idioma del Civil 3D seleccionado."),
        ("changed", "«Trazar centerline» va justo después de «Dibujar utilidad»; ejes X/Y de la georreferenciación en morado; ventana de georreferenciación maximizada al abrir."),
        ("changed", "Tema oscuro y accesibilidad; botones de eliminar en rojo; el membrete ya no se separa a una capa aparte."),
        ("removed", "Función «Emparejar centerline dibujado» de la georreferenciación."),
    ]),
    ("1.0.0", [
        ("release", "Primera versión estable: digitalización PDF → DXF, importación a Civil 3D con familias imperiales de gravedad/presión/conduit, gestión de buzones y cajas, y adjunción automática de Property Sets a tuberías vía Excel."),
    ]),
]
