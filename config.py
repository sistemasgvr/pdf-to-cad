"""
config.py — Parámetros ajustables del pipeline PDF -> DXF.

Todo lo que cambia entre tipos de plano vive aquí. Edita este archivo
(no el código) para recalibrar detección de líneas, texto y mapeo de capas.

Hay dos perfiles:
  VECTOR_*  -> usados cuando el PDF es vectorizado (geometría exacta)
  RASTER_*  -> usados cuando el PDF es un escaneo (visión por computador)
"""

# ─────────────────────────────────────────────────────────────────────────────
# ESQUEMA DE CAPAS DE SALIDA (DXF)
# ─────────────────────────────────────────────────────────────────────────────
# Nombre de capa de destino -> color ACI de AutoCAD.
# Colores alineados con la convención pedida:
#   azul=agua, café=alcantarillado, amarillo=gas, negro=vía.
# Convención de color pedida por utilidad:
#   Agua = celeste (cian, ACI 4) · Desagüe/Alcantarillado = amarillo (ACI 2)
#   Drenaje/Storm = verde (ACI 3)
# Convención de color + linetype pedida por utilidad (ver LAYER_LINETYPE):
#   W  Agua            = Azul     · SS Alcantarillado = Verde
#   G  Gas             = Amarillo · E  Eléctrico       = Rojo
#   T  Telefonía       = Naranja  · T(OH) Tel. aérea   = Naranja (linetype distinto)
#   E(OH) Eléc. aérea  = Rojo (linetype distinto) · SD Drenaje = Verde (linetype distinto)
OUTPUT_LAYERS = {
    "AGUA":            5,    # W  azul
    "ALCANTARILLADO":  3,    # SS verde
    "DRENAJE":         3,    # SD verde (linetype DASHED)
    "GAS":             2,    # G  amarillo
    "ELECTRICO":       1,    # E  rojo
    "ELECTRICO_AEREO": 1,    # E(OH) rojo (linetype DASHED)
    "TELECOM":         30,   # T  naranja
    "TELECOM_AEREO":   30,   # T(OH) naranja (linetype DASHED)
    "AGUA_HIERRO":     4,    # (marca) agua hierro - celeste
    "CABLEADO":        6,    # (marca) cableado - magenta
    "EJE_VIA":         7,    # blanco/negro (base: calles, lotes, topografía)
    "METRO_RW":        140,  # azul claro (vía férrea / LRT / derecho de vía)
    "TOPO":            8,    # gris
    "ESTRUCTURAS":     7,    # blanco (pozos, postes, válvulas, hidrantes)
    "PREDIOS":         8,    # gris
    "LIMITE_MAPA":     250,  # gris oscuro
    "LEADER":          7,    # blanco (líneas guía + punta de flecha)
    "ANOTACION":       8,    # gris (texto + leaders: capa ocultable)
    "DIGITALIZADO":    7,    # blanco
    "TEXTO":           7,    # texto / labels
}

# ─────────────────────────────────────────────────────────────────────────────
# TIPO DE LÍNEA POR CAPA  (linetype ByLayer)
# ─────────────────────────────────────────────────────────────────────────────
# Reproduce la convención del plano para identificar cada línea por su trazo,
# no solo por color. Los tipos UTIL_* dibujan la letra de la utilidad (─W─W─).
# Los valores son nombres de linetype definidos en LINETYPE_DEFS (abajo) o
# linetypes estándar de AutoCAD (CONTINUOUS, CENTER2, DASHED, etc.).
#
# INTERRUPTOR: si es False, NINGÚN tipo de línea especial sale — ni los
# personalizados con letra (UTIL_W, UTIL_SS, UTIL_G, UTIL_E, UTIL_T) ni el
# punto-guión (CENTER2 de METRO_RW). TODAS las capas salen como CONTINUOUS.
# Ponlo en True para reactivar los marcadores y el punto-guión.
# Los tipos UTIL_* (letra ─W─) siguen desactivados. Para diferenciar las líneas
# AÉREAS (OH) y el DRENAJE de sus pares subterráneos se usan linetypes ESTÁNDAR
# (DASHED), que se aplican siempre (no dependen de USE_CUSTOM_LINETYPES).
# Linetypes personalizados CON la letra embebida (─W─W─): cada tubería se dibuja
# como UNA polilínea con su letra entre los guiones -> un solo elemento seleccionable.
USE_CUSTOM_LINETYPES = True
LAYER_LINETYPE = {
    "AGUA":            "UTIL_W",     # ─W─W─
    "ALCANTARILLADO":  "UTIL_SS",    # ─SS─SS─
    "DRENAJE":         "UTIL_SD",    # ─SD─SD─
    "GAS":             "UTIL_G",     # ─G─G─
    "ELECTRICO":       "UTIL_E",     # ─E─E─
    "ELECTRICO_AEREO": "UTIL_EOH",   # ─E(OH)─
    "TELECOM":         "UTIL_T",     # ─T─T─
    "TELECOM_AEREO":   "UTIL_TOH",   # ─T(OH)─
    "METRO_RW":        "CENTER2",    # punto-guión (eje / vía)
    # el resto -> CONTINUOUS (por defecto en ensure_layer)
}

# Definición de linetypes de utilidad (patrón en PIES, a escala del plano).
# Formato AutoCAD complejo: trazo, hueco (negativo) y texto embebido.
#   raya=4', luego hueco con la letra centrada, longitud total ~12'.
# Ajusta UTIL_LT_DASH / UTIL_LT_GAP / UTIL_LT_TEXT_H para cambiar el tamaño.
UTIL_LT_DASH = 4.0      # longitud de raya (pies)
UTIL_LT_GAP = 3.0       # hueco a cada lado de la letra (pies)
UTIL_LT_TEXT_H = 1.2    # altura de la letra (pies) — igual al marcador del PDF (~1.1 ft)

# Letra(s) de cada linetype de utilidad (se dibujan embebidas en la línea).
UTIL_LINETYPE_MARKERS = {
    "UTIL_W": "W", "UTIL_SS": "SS", "UTIL_G": "G", "UTIL_E": "E", "UTIL_T": "T",
    "UTIL_SD": "SD", "UTIL_EOH": "E(OH)", "UTIL_TOH": "T(OH)",
}

# Escala global de tipos de línea ($LTSCALE). Los patrones UTIL_* están en PIES
# reales (dash/gap/letra en ft), así que la escala es 1.0.
LINETYPE_SCALE = 1.0

# ─────────────────────────────────────────────────────────────────────────────
# MAPEO OCG -> CAPA  (solo ruta VECTORIZADA)
# ─────────────────────────────────────────────────────────────────────────────
# El nombre OCG del PDF (ej. "AE36687_xUT|C-UTIL-W-EXIS") se compara contra
# estos tokens, sin distinguir mayúsculas, como SUBCADENA. Gana la primera
# coincidencia, así que pon los tokens más específicos arriba.
#   valor = nombre de capa de OUTPUT_LAYERS, o None para DESCARTAR (membretes, etc.)
LAYER_TOKENS = [
    # ═══ Familia LADWP Water Service Map (va primero para evitar colisiones) ═══
    ("WSM_BOUNDARY",          "LIMITE_MAPA"),   # borde de hoja (mayoría degenerado, se filtra)
    ("WSM_EDGE",              "LIMITE_MAPA"),
    ("WGS_LATERAL_PIPE",      "AGUA"),          # laterales de servicio
    ("WGS_PIPE",              "AGUA"),          # tubería de agua (red)
    ("PIPE_STRUCTURES",       "AGUA"),
    ("PIPE_",                 "AGUA"),          # PIPE_1000, PIPE_830, etc.
    ("WGS_HYDRANT",           "ESTRUCTURAS"),   # hidrantes
    ("WGS_APPURTENANCE",      "ESTRUCTURAS"),   # válvulas / accesorios
    ("WGS_LEADER",            "ANOTACION"),     # leaders de etiquetas
    ("WGS_DIMENSION",         "ANOTACION"),
    ("LOT_DIM",               "ANOTACION"),     # cotas de lote
    ("LOT_NUMBER",            "TEXTO"),         # números de lote (glifos)
    ("MB_NUMBER",             "TEXTO"),         # números de map book
    ("STNAMES",               "TEXTO"),         # nombres de calle
    ("TRACT_PM",              "PREDIOS"),       # tract / parcel map
    ("PROPERTY",              "PREDIOS"),       # líneas de propiedad
    ("LANDBASE",              "EJE_VIA"),       # base cartográfica / calles
    ("CENTERLINES",           "EJE_VIA"),       # ejes de calle (NO metro)

    # --- Líneas guía (leaders) de los callouts -> capa ANOTACION ---
    # Son las líneas que apuntan del texto del callout a la utilidad.
    ("C-UTIL-CALLOUT",        "ANOTACION"),
    ("C-ANNO-IDEN",           "ANOTACION"),

    # --- Descartes: membrete, título, cotas ---
    ("TITLEBLOCK",            None),
    ("G-ANNO-TTLB",           None),
    ("G-ANNO-TITL",           None),
    ("G-ANNO-FOR INFO",       None),
    ("G-ANNO-PROGRESS",       None),
    ("G-ANNO-NOTES",          None),
    ("G-ANNO-TEXT",           None),
    ("S-ANNO-TITL",           None),
    ("C-ANNO-TITL",           None),
    ("C-ANNO-DIMS",           None),     # cotas/dimensiones (cambiar a "ANOTACION" si las quieres)
    ("C-ANNO-PROJ",           None),
    ("C-ANNO-PROGRESS",       None),
    ("C-ROAD-TEXT",           None),
    ("ANNO-TTLB",             None),

    # --- Agua (W) ---
    ("C-UTIL-W-STRC",         "AGUA"),
    ("C-UTIL-W-EXIS",         "AGUA"),
    ("WATR-HYDT",             "AGUA"),
    ("DOMW-HYDR",             "AGUA"),
    ("DOMW-PITS-VALV",        "AGUA"),

    # --- Alcantarillado sanitario (SS) ---
    ("C-UTIL-SS",             "ALCANTARILLADO"),
    ("SSWR",                  "ALCANTARILLADO"),
    # --- Drenaje pluvial / storm drain (SD) ---
    ("C-UTIL-SD",             "DRENAJE"),
    ("STRM-MHOL",             "DRENAJE"),
    ("STRM-INLT",             "DRENAJE"),

    # --- Gas (G) ---
    ("C-UTIL-G-EXIS",         "GAS"),

    # --- Eléctrico: AÉREO (E-OHE) primero, porque 'C-UTIL-E-EXIS' es subcadena ---
    ("C-UTIL-E-EXIS-OHE",     "ELECTRICO_AEREO"),
    ("C-UTIL-E-EXIS",         "ELECTRICO"),
    ("POWR-POLE",             "ELECTRICO"),
    ("POWR-DEVC",             "ELECTRICO"),
    ("POWR-JBOX",             "ELECTRICO"),
    ("POWR-SWCH",             "ELECTRICO"),
    ("ELEC-STLT",             "ELECTRICO"),
    ("ELEC-VALT",             "ELECTRICO"),

    # --- Telecom: AÉREO (T-OH) primero, porque 'C-UTIL-T-EXIS' es subcadena ---
    ("C-UTIL-T-EXIS-OH",      "TELECOM_AEREO"),
    ("C-UTIL-T-STRC",         "TELECOM"),
    ("C-UTIL-T-EXIS",         "TELECOM"),
    ("COMM-JBOX",             "TELECOM"),

    # --- Metro / vía férrea / derecho de vía (ROW) ---
    ("C-TRACK-CL",            "METRO_RW"),
    ("FUTURE LRT",            "METRO_RW"),
    ("R-ROW",                 "METRO_RW"),
    ("CENTERLINE",            "METRO_RW"),

    # --- Eje de vía / calzada ---
    ("C-ROAD-CURB",           "EJE_VIA"),
    ("C-ROAD-EG",             "EJE_VIA"),
    ("C-ROAD-STAN",           "EJE_VIA"),
    ("C-SAWCUT",              "EJE_VIA"),
    ("C-ROAD-TRUNCATED",      "EJE_VIA"),
    ("C-FENC-WIRE",           "EJE_VIA"),
    ("ROAD-DRIV",            "EJE_VIA"),
    ("ROAD-SIGN",            "EJE_VIA"),
    ("C-ROAD",                "EJE_VIA"),

    # --- Topografía / superficie ---
    ("TOPO-BRKL",             "TOPO"),
    ("TOPO-CONC",             "TOPO"),
    ("TOPO-RTWL",             "TOPO"),
    ("FENC-LINE",             "TOPO"),
    ("SITE-STRC-WALL",        "TOPO"),

    # --- Estructuras / apéndices puntuales ---
    ("POTHOLE",               "ESTRUCTURAS"),
    ("GATE",                  "ESTRUCTURAS"),
    ("GID_ARM",               "ESTRUCTURAS"),
    ("GATE-ARM",              "ESTRUCTURAS"),
    ("SPCL-TRAF",             "ESTRUCTURAS"),
    ("LITE-EXTR",             "ESTRUCTURAS"),
    ("UTIL-VALV",             "ESTRUCTURAS"),
    ("UTIL-VENT",             "ESTRUCTURAS"),
    ("UTIL-EQPM",             "ESTRUCTURAS"),
    ("UTIL-POLE",             "ESTRUCTURAS"),
    ("SITE-VEGE",             "ESTRUCTURAS"),
    ("SITE-STRC",             "ESTRUCTURAS"),
    ("SGNL",                  "ESTRUCTURAS"),
    ("C-ANNO-SYMB",           "ESTRUCTURAS"),
]

# Capa para geometría sin token / sin capa OCG (as-builts planos, auditoría).
FALLBACK_LAYER = "DIGITALIZADO"

# ─────────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN POR COLOR  (vector APLANADO: sin capas OCG)
# ─────────────────────────────────────────────────────────────────────────────
# Algunos PDFs vectorizados vienen "aplanados": traen la geometría exacta pero
# SIN nombres de capa OCG y SIN texto vivo (las letras son trazos rellenos).
# En ese caso se clasifica por el COLOR del trazo. RGB en 0..1; se compara con
# tolerancia VECTOR_COLOR_TOL. Útil en as-builts donde la utilidad va resaltada
# (p.ej. LADWP resalta la línea de agua en amarillo).
# Gana la primera coincidencia.
# NOTA: el amarillo/rojo/azul/cian NO se mapean aquí (no se dibujan como línea
# propia); son MARCAS de resaltado que recolorean la línea negra de abajo
# (ver VECTOR_OVERLAY_LAYER_MAP). Aquí solo quedan colores que SÍ son geometría.
VECTOR_COLOR_LAYER_MAP = [
    ((0.0, 0.5, 0.0), "GAS"),             # verde oscuro (si el trazo es geometría real)
]
VECTOR_COLOR_DEFAULT = "EJE_VIA"   # trazo negro / base cartográfica
VECTOR_COLOR_TOL = 0.25            # distancia máx. por componente RGB

# ─────────────────────────────────────────────────────────────────────────────
# MARCAS DE COLOR (OVERLAYS) -> transferir a la LÍNEA NEGRA de abajo
# ─────────────────────────────────────────────────────────────────────────────
# El usuario resalta encima del dibujo las tuberías con colores. Se detecta la
# marca, se busca la línea negra real que queda DEBAJO y se asigna a esta capa
# (la marca de color en sí NO se dibuja). Color RGB (0..1) -> capa.
VECTOR_OVERLAY_LAYER_MAP = [
    ((0.90, 0.13, 0.22), "AGUA"),         # rojo    = agua
    ((1.00, 0.00, 0.00), "AGUA"),         # rojo puro = agua
    ((1.00, 1.00, 0.00), "AGUA"),         # amarillo (resaltado del autor) = agua
    ((0.00, 0.00, 1.00), "AGUA_HIERRO"),  # azul    = agua tubería de hierro
    ((0.22, 0.90, 1.00), "CABLEADO"),     # celeste = cableado subterráneo
    ((0.00, 1.00, 1.00), "TELECOM"),      # cian
]
VECTOR_OVERLAY_TOL = 0.16       # tolerancia de color de la marca
VECTOR_OVERLAY_SNAP_PT = 22.0   # distancia máx. marca <-> línea negra (pt, ~6 ft)
VECTOR_OVERLAY_ANGLE_TOL = 22.0 # la línea debe ser paralela a la marca (grados)

# Glifos de texto dibujados como relleno (vector aplanado sin texto vivo):
# un trazo SOLO-relleno (fill != None y color de borde None) cuyo bbox sea menor
# a esta área (pt²) se descarta como letra. Subir si queda texto; bajar si se
# comen símbolos rellenos legítimos (válvulas sólidas, flechas).
VECTOR_FILL_GLYPH_MAX_AREA_PT = 300.0

# OCR de CALLOUTS en PDFs vectoriales aplanados (sin texto vivo): se renderiza la
# página, se lee el texto por OCR, se coloca en la capa TEXTO con sus atributos
# (diámetro/material/dueño/distancia/estación) en XDATA, y se genera un reporte
# .txt junto al DXF. Requiere Tesseract.
VECTOR_OCR_CALLOUTS = True
VECTOR_OCR_ZOOM = 4.167      # ~300 DPI (mejor cobertura de lectura en este plano)
                              #  -> menos misreads. (vector: render nítido a cualquier DPI)
VECTOR_OCR_BINARIZE = False   # binarizar empeoraba algunas lecturas en este plano
# Separación TEXTO/GRÁFICOS antes del OCR (clave en PDFs aplanados donde el texto
# son trazos mezclados con tuberías/símbolos): se conservan SOLO los componentes
# conexos de tamaño de carácter; las líneas largas y símbolos grandes se quitan,
# así Tesseract no inventa texto a partir de ellos.
VECTOR_OCR_TEXT_CC = True
VECTOR_OCR_CHAR_MIN_PX = 8    # lado menor de un carácter (px @ zoom). Menor = motas
VECTOR_OCR_CHAR_MAX_PX = 75   # lado mayor de un carácter. Mayor = líneas/símbolos
VECTOR_OCR_CHAR_FILL_MIN = 0.06  # densidad mín. (área/bbox): descarta trazos finos
VECTOR_OCR_MIN_CONF = 20      # bajo: la cobertura la maximiza el filtro de contenido (is_garbage)
                              #  (más alto = menos texto inexistente/basura)
VECTOR_OCR_SUPPRESS_CONF = 8  # confianza mín. para SUPRIMIR el texto de fondo
                              # (más bajo = borra más rótulo original, aunque no se
                              #  pueda releer; evita que queden trazos de letra sueltos)
# Excluir texto que cae sobre un SÍMBOLO circular (burbujas de nota, válvulas):
# evita que esos símbolos se interpreten como texto. Radio máx. de símbolo (pt).
VECTOR_SYMBOL_CIRCLE_MAX_PT = 30.0
# OCR multi-orientación: lee la página también a 90° y 270° para capturar el
# texto rotado (rótulos verticales) — mejora cobertura y suprime más fondo.
VECTOR_OCR_ORIENTATIONS = (0, 90, 270)

# No dibujar las COTAS (dimensiones): se omiten como etiquetas los textos que son
# solo número/elevación/pie-pulgada. Las estaciones (149+10) y los callouts con
# texto de utilidad NO se consideran cota.
VECTOR_SKIP_DIMENSIONS = True

# Ruido: descarta geometría diminuta (motas) cuyo bbox mayor < esto (pt PDF).
VECTOR_NOISE_MIN_PT = 1.5

# ─────────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN DE UTILIDAD POR CALLOUT  (método flecha + texto)
# ─────────────────────────────────────────────────────────────────────────────
# Cada callout de utilidad apunta (vía una flecha/leader) a la línea que describe.
# Se detecta el leader que arranca en la caja del texto, se sigue hasta su punta,
# y la línea de tubería más cercana a esa punta se reclasifica a la capa indicada
# y recibe la nomenclatura (diámetro/material/dueño/…) en XDATA.
# Palabra clave del callout -> capa destino.
UTILITY_KEYWORDS = [
    ("SD",          "DRENAJE"),         # storm drain
    ("STORM",       "DRENAJE"),
    ("HDPE",        "DRENAJE"),         # en este plano el HDPE es el SD
    ("SEWER",       "ALCANTARILLADO"),
    ("SS",          "ALCANTARILLADO"),
    ("GAS",         "GAS"),
    ("SCG",         "GAS"),
    ("WATER",       "AGUA"),
    ("DWPWS",       "AGUA"),
    ("DWP",         "AGUA"),
    ("RW",          "AGUA"),            # recycled water
    ("R.W",         "AGUA"),
    ("D.I",         "AGUA"),
    ("DI",          "AGUA"),
    ("STL",         "AGUA"),
]
LEADER_BOX_MARGIN_PT = 6.0    # un leader arranca a <= esto de la caja del texto
LEADER_MIN_LEN_PT    = 8.0    # longitud mínima de un leader
CLASSIFY_RADIUS_PT   = 40.0   # radio para asociar la punta del leader a una tubería
ARROWHEAD_LEN_PT     = 7.0    # tamaño de la punta de flecha reconstruida
DRAW_ARROWHEADS      = True

# ─────────────────────────────────────────────────────────────────────────────
# ESCALA
# ─────────────────────────────────────────────────────────────────────────────
# Si la detección automática de escala falla, se usa este valor (pies / punto PDF).
# 1" = 20'  ->  20 / 72.
DEFAULT_SCALE_FT_PER_PT = 20.0 / 72.0
INSUNITS = 2  # 2 = pies (feet) en el encabezado DXF $INSUNITS

# Override manual de escala (pies/punto). Si es None, se auto-detecta.
# Ej. para forzar 1"=100':  100/72.0
SCALE_FT_PER_PT_OVERRIDE = None
# Rango de escalas de trabajo válidas (pies por pulgada). Descarta escalas de
# mapas índice/locator (p.ej. 1"=1500') al elegir la escala del dibujo.
SCALE_WORKING_MIN = 5.0
SCALE_WORKING_MAX = 500.0

# ─────────────────────────────────────────────────────────────────────────────
# CARPETA DE SALIDA
# ─────────────────────────────────────────────────────────────────────────────
# Donde se guardan los DXF cuando no se da una ruta con carpeta explícita.
OUTPUT_DIR = "output"

# ─────────────────────────────────────────────────────────────────────────────
# TEXTO  (ruta vectorizada)
# ─────────────────────────────────────────────────────────────────────────────
# Normaliza la altura de fuente del PDF a la práctica estándar (0.1" = 2' @ 1"=20').
TEXT_SCALE_FACTOR = 0.57
TEXT_MIN_HEIGHT_FT = 0.25
TEXT_FONT = "Arial"

# Exclusión del MEMBRETE / cuadro de rótulo:
# El texto del membrete (signaturas, "FOR INFORMATION ONLY", "DRAWING NO",
# escala, etc.) vive FUERA del área del dibujo. Se calcula la caja del dibujo
# a partir de la geometría real (utilidades/vías/topo) y se descarta todo el
# texto que cae fuera de esa caja + margen.
TEXT_PLAN_BBOX_MARGIN_PT = 90.0   # margen alrededor del dibujo (puntos PDF)
TEXT_PLAN_BBOX_PCT_LO = 0.005     # percentil inferior (ignora outliers/marco)
TEXT_PLAN_BBOX_PCT_HI = 0.995     # percentil superior
TEXT_TITLE_OY_FRAC = 0.78         # fallback si no hay geometría suficiente

# ─────────────────────────────────────────────────────────────────────────────
# SUPRESIÓN DE GLIFOS SHX  (marcadores de letra W/G/SS/T sobre las líneas)
# ─────────────────────────────────────────────────────────────────────────────
# Ventana de área (pt²) en la que viven los glifos de letra de linetype CAD.
SHX_AREA_MIN = 5.0
SHX_AREA_MAX = 80.0

# Marcadores de letra en las líneas de utilidad (W, SS, G, E, T, "(OH)"): son
# glifos pequeños de VARIOS segmentos que ensucian y fragmentan la tubería. Se
# suprimen por tamaño de bbox: un path de >2 segmentos (o con curvas) cuyo lado
# mayor sea menor a esto se descarta EN LAS CAPAS DE TUBERÍA (los guiones reales
# de la tubería son de 1 segmento y no se tocan; las curvas son grandes).
MARKER_GLYPH_MAX_DIM_PT = 17.0
UTILITY_LINE_LAYERS = {
    "AGUA", "ALCANTARILLADO", "DRENAJE", "GAS",
    "ELECTRICO", "ELECTRICO_AEREO", "TELECOM", "TELECOM_AEREO",
}

# ─────────────────────────────────────────────────────────────────────────────
# CAPAS A ELIMINAR POR COMPLETO  (ruta vectorizada)
# ─────────────────────────────────────────────────────────────────────────────
# Capas cuya geometría se DESCARTA por completo del DXF: no queda ni el trazo
# ni el hueco. Pensado para quitar las líneas de utilidad con linetype de letra
# (--W--, --SS--, --G--, --E(OH)--, --T--) cuando NO se quieren en el dibujo.
# Vacíalo ({}) para conservar todas las capas.
DROP_LAYERS = set()

# ─────────────────────────────────────────────────────────────────────────────
# UNIÓN DE SEGMENTOS COLINEALES -> POLILÍNEAS  (ruta vectorizada)
# ─────────────────────────────────────────────────────────────────────────────
MERGE_MAX_BRIDGE_PT = 20.0   # puentea huecos (dejados por marcadores SHX) hasta 20pt
# Cosido de piezas en UNA polilínea por tubería (capas de utilidad): une extremos
# que estén a <= esta distancia (pt PDF) -> un solo elemento seleccionable.
STITCH_TOL_PT = 14.0
# Escala por-entidad para los linetypes ESTÁNDAR (DASHED/CENTER/DASHDOT) que se
# detectan en las líneas NO personalizadas (base). En un plano de ~720 ft hace
# visibles sus guiones (los UTIL_* van en pies con $LTSCALE=1).
LINETYPE_STD_SCALE = 30.0
MERGE_ANGLE_TOL_DEG = 3.0    # mismo rumbo si difieren < 3°
MERGE_PERP_TOL_PT   = 2.0    # colineales si distancia perpendicular < 2pt

# Aplanado de curvas Bézier: nº de tramos por curva (más = más suave).
BEZIER_STEPS = 16

# Segmentos/puntos degenerados: se descartan los segmentos cuya longitud sea
# menor a este epsilon (puntos de longitud cero que solo inflan el archivo).
DEGENERATE_EPS_PT = 0.1

# ─────────────────────────────────────────────────────────────────────────────
# LIMPIEZA DE MARCADORES DE LÍNEA (ticks/slashes de los linetypes de utilidad)
# ─────────────────────────────────────────────────────────────────────────────
# Las líneas de utilidad del PDF llevan, además de la letra (W/G/SS, ya filtrada
# como glifo), pequeños trazos diagonales (ticks) que NO son parte de la tubería.
# Método general (independiente de la orientación del plano): tras fusionar los
# guiones en corridas largas de tubería, los ticks quedan como trazos CORTOS y
# AISLADOS (no se fusionan con nada). Se eliminan por longitud + aislamiento.
CLEAN_UTILITY_MARKERS = True
UTILITY_CLEAN_LAYERS = {"AGUA", "GAS", "ALCANTARILLADO", "DRENAJE", "ELECTRICO",
                        "ELECTRICO_AEREO", "TELECOM", "TELECOM_AEREO"}
MARKER_MAX_SEGMENTS = 1     # se descarta si lo forman <= N segmentos (aislado)
MARKER_MAX_LEN_PT = 50.0    # ...y su longitud total es menor a esto (corto)

# Capas (tokens OCG) cuyos segmentos NO deben fusionarse: patrones de relleno,
# tramas y símbolos compuestos por muchos segmentos cortos. Fusionarlos crea
# líneas largas cruzadas (maraña). Se dibujan tal cual.
NO_MERGE_TOKENS = [
    "TRUNCATED DOME",   # domo truncado / pavimento podotáctil (trama)
    "C-ANNO-SYMB",      # símbolos de anotación
    "GID_GATE",         # detalles de compuerta (trama)
    "GATE DETAIL",
]

# ═════════════════════════════════════════════════════════════════════════════
#                       PARÁMETROS RUTA RASTERIZADA (OpenCV)
# ═════════════════════════════════════════════════════════════════════════════
RASTER_DPI = 300

# Rangos de color HSV (OpenCV: H 0-179, S 0-255, V 0-255) por tipo de utilidad.
# Cada entrada: capa -> lista de (low_hsv, high_hsv). Varias franjas para colores
# que cruzan el wrap del matiz (ej. rojo) o tonos amplios.
RASTER_COLOR_RANGES = {
    "AGUA":           [((90, 60, 40),  (130, 255, 255))],   # azul
    "ALCANTARILLADO": [((8, 60, 30),   (25, 200, 200))],    # café / marrón
    "GAS":            [((22, 80, 80),  (35, 255, 255))],    # amarillo
    "EJE_VIA":        [((0, 0, 0),     (179, 60, 90))],     # negro (baja S, baja V)
}

# Parámetros HoughLinesP por capa. Ajusta 'thickness' (grosor) según el plano.
# threshold = votos mínimos; minLineLength / maxLineGap en píxeles @ RASTER_DPI.
RASTER_HOUGH = {
    "default":        dict(threshold=50, minLineLength=40, maxLineGap=8,  thickness=1),
    "AGUA":           dict(threshold=50, minLineLength=40, maxLineGap=12, thickness=2),
    "ALCANTARILLADO": dict(threshold=50, minLineLength=40, maxLineGap=12, thickness=2),
    "GAS":            dict(threshold=45, minLineLength=35, maxLineGap=15, thickness=2),
    "EJE_VIA":        dict(threshold=60, minLineLength=60, maxLineGap=6,  thickness=1),
}

# Unión de segmentos en la ruta raster (en píxeles).
RASTER_MERGE_ANGLE_TOL_DEG = 2.5
RASTER_MERGE_PERP_TOL_PX   = 5.0    # con esqueleto los ejes son finos
RASTER_MERGE_MAX_BRIDGE_PX = 26.0   # puentea huecos de guiones/letras
# Esqueletonizar antes del LSD: desactivado (fragmentaba más de lo que unificaba).
RASTER_SKELETONIZE = False
# Colapsar líneas dobles del LSD: si dos líneas son casi paralelas, se solapan y
# están a <= esta distancia perpendicular, son los DOS bordes de un mismo trazo
# -> se deja una. Las dobles reales (bordillos) van más separadas y se conservan.
RASTER_DOUBLE_MAX_GAP_PX = 6.0

# ── Vectorización por LSD (escaneos monocromos: planos B&N sin color) ─────────
# Cuando el escaneo NO tiene color (saturación ~0), separar por color es inútil.
# En ese caso se usa una tubería basada en FORMA, que clasifica antes de dibujar:
#   binarizar -> OCR borra texto -> quitar blobs de texto (CC) -> LSD -> unir.
RASTER_BW_SAT_THRESH   = 12      # si la saturación media < esto => tratar como B&N
RASTER_MIN_LINE_LEN_PX = 42      # descarta segmentos más cortos que esto (px @ DPI)
RASTER_LSD_SCALE       = 0.8     # escala de trabajo del LSD (0.5–1.0; menor = más rápido)

# Borrado de texto/símbolos antes de vectorizar (OCR Tesseract).
RASTER_TEXT_ERASE_CONF = 25      # confianza mín. para BORRAR una caja de texto
RASTER_TEXT_ERASE_PAD_PX = 4     # margen alrededor de la caja borrada (px)

# Eliminación de texto por componentes conexos (independiente de la orientación):
# un componente cuyo bbox cabe en CHAR_MAX x CHAR_MAX px (ambos lados) se trata
# como glifo/marca "X" y se descarta. Las líneas (bbox alargado) se conservan.
# Subir si queda texto; bajar si se comen segmentos cortos de dibujo.
RASTER_TEXT_CC_MAX_PX = 64

# Identificación de TUBERÍAS por callout: si una etiqueta OCR contiene estos
# tokens (p.ej. 10"Pipe), las líneas cercanas se asignan a la capa AGUA.
RASTER_PIPE_TOKENS = ("PIPE", "WATER", "W.M.", "WM", "MAIN")
RASTER_PIPE_NEAR_PX = 60         # radio de asociación callout->línea (px)

# OCR (pytesseract). Si no está instalado, se omite el texto en la ruta raster.
RASTER_OCR_ENABLED = True
RASTER_OCR_MIN_CONF = 40      # confianza mínima (0-100) para conservar un label
