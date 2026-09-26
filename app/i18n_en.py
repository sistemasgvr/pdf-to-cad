"""Traducciones ES → EN de la interfaz.

La clave es SIEMPRE el texto en español exactamente como se escribe en el
código (el argumento de ``t()``); el valor, su traducción. Este módulo solo
contiene datos: el motor (``t``, ``bind``, cambio de idioma) vive en i18n.py.
"""

# Diccionario maestro de traducciones ES → EN.
#
# Convenciones:
#   - La clave es SIEMPRE el texto EN ESPAÑOL exactamente como aparece en la UI.
#   - Solo agregamos claves para strings que aparecen en la UI (no logs internos,
#     no nombres de variables). Los debug prints no necesitan traducción.
#   - Los HTML pequeños (bold, spans) se traducen en la parte de texto plano y
#     dejamos el marcado. Si el HTML es complejo, se traduce el string entero.
#   - Placeholders tipo ``f"Utilidad #{i}"`` NO se pueden pasar como clave —
#     usamos ``t("Utilidad #{n}").format(n=i)`` o ``t()`` sobre la parte fija.
# ─────────────────────────────────────────────────────────────────────────────
EN: dict[str, str] = {
    # ── Menús principales ──────────────────────────────────────────────
    "Editar": "Edit",
    "Herramientas": "Tools",
    "Ayuda": "Help",
    "Nuevo": "New",
    "Exportar DXF": "Export DXF",
    "Cerrar proyecto": "Close project",
    "Opciones…": "Options…",
    "Opciones": "Options",
    "Idioma": "Language",
    "Español": "Spanish",
    "Inglés": "English",
    "Acerca de…": "About…",
    "Deshacer": "Undo",
    "Rehacer": "Redo",
    "Eliminar": "Delete",
    "Duplicar": "Duplicate",
    "Editar": "Edit",

    # ── Toolbar y acciones principales ─────────────────────────────────
    "Acercar": "Zoom in",
    "Alejar": "Zoom out",
    "Ajustar": "Fit view",
    "Puntero": "Pointer",
    "Borrar zona": "Erase zone",

    # ── Docks / paneles ────────────────────────────────────────────────
    "Herramientas": "Tools",
    "Inventario": "Inventory",
    "Propiedades de la utilidad": "Utility properties",
    "Utilidades": "Utilities",
    "Leaders": "Leaders",
    "Textos": "Texts",
    "Zonas": "Zones",
    "Buzones": "Manholes",
    "Curvas": "Curves",
    "Centerlines": "Centerlines",
    "Bancoductos": "Duct Banks",

    # ── Bancoductos: pestaña de inventario ─────────────────────────────
    "+ Nuevo": "+ New",
    "Editar": "Edit",
    "Duplicar": "Duplicate",
    "Crear un bancoducto nuevo desde cero.": "Create a new duct bank from scratch.",
    "Editar el bancoducto seleccionado.\nTambién doble-click sobre la fila.":
        "Edit the selected duct bank.\nAlso double-click on the row.",
    "Duplicar el bancoducto seleccionado.": "Duplicate the selected duct bank.",
    "Aún no hay bancoductos.\nCrea uno con «+ Nuevo» arriba, o click derecho en una tubería.":
        "No duct banks yet.\nCreate one with «+ New» above, or right-click a pipe.",
    "+ Nuevo bancoducto": "+ New duct bank",
    "Crear bancoducto para esta tubería": "Create duct bank for this pipe",
    "Editar/mover": "Edit/move",
    "Mover": "Move",
    "Cambiar tipo": "Change type",
    "Editar texto": "Edit text",
    "Selecciona un bancoducto primero.": "Select a duct bank first.",
    "Selecciona un bancoducto para duplicar.": "Select a duct bank to duplicate.",

    # ── Bancoductos: diseñador ─────────────────────────────────────────
    "Diseñador de Duct Bank": "Duct Bank Designer",
    "Cara Interior (Corte Longitudinal)": "Interior Face (Cross Section)",
    "Conducto\n(Círculo)": "Conduit\n(Circle)",
    "Zoom +": "Zoom +",
    "Zoom −": "Zoom −",
    "Acercar": "Zoom in",
    "Alejar": "Zoom out",
    "Centrar la vista sobre la envolvente": "Center the view on the envelope",
    "Identificación": "Identification",
    "Nombre:": "Name:",
    "Ej. Duct Bank A – Telecom": "Ex. Duct Bank A – Telecom",
    "Asignar a:": "Assign to:",
    "(Sin asignar)": "(Not assigned)",
    "Reglas de diseño": "Design rules",
    "Aplicar reglas": "Apply rules",
    "Sep. entre conductos:": "Conduit spacing:",
    "Dist. al borde:": "Edge clearance:",
    "Conducto": "Conduit",
    "Nuevo conducto": "New conduit",
    "Conducto seleccionado": "Selected conduit",
    "Diámetro:": "Diameter:",
    "Diám. real:": "Actual dia.:",
    "X:": "X:",
    "Y:": "Y:",
    "Etiqueta:": "Label:",
    "Etiqueta (opcional)": "Label (optional)",
    "Envolvente (pulgadas)": "Envelope (inches)",
    "Ancho:": "Width:",
    "Alto:": "Height:",
    "Margen interior (pulgadas)": "Interior margin (inches)",
    "Redondeo de esquinas (pulgadas)": "Corner rounding (inches)",
    "Visualización en Civil 3D": "Civil 3D visualization",
    "Dibujar contenedor 3D": "Draw 3D container",
    "Conductos: 0": "Conduits: 0",
    "Cancelar": "Cancel",
    "Cerrar sin guardar cambios.": "Close without saving changes.",
    "Guardar el bancoducto en el proyecto y cerrar el diseñador.":
        "Save the duct bank in the project and close the designer.",
    "Rejilla activada · 1 punto = 1 pulgada":
        "Grid on · 1 dot = 1 inch",
    "Ajuste a rejilla (0.25\")": "Snap to grid (0.25\")",
    "Nivel de zoom actual.\n"
    "Usa los botones Zoom +/- de la toolbar\n"
    "o la rueda del ratón.":
        "Current zoom level.\n"
        "Use the Zoom +/- buttons on the toolbar\n"
        "or the mouse wheel.",
    "Se dibujará el sólido 3D del contenedor + los conductos internos.":
        "The 3D container solid + internal conduits will be drawn.",
    "Solo se dibujarán los conductos internos. El sólido 3D del contenedor NO se creará.":
        "Only internal conduits will be drawn. The 3D container solid will NOT be created.",
    "Reglas custom desactivadas. Los chequeos geométricos básicos "
    "(dentro de envolvente, sin colisión) siguen activos.":
        "Custom rules disabled. Basic geometric checks "
        "(inside envelope, no collision) still apply.",
    "Sin valores puestos — configura arriba para que apliquen.":
        "No values set — configure above so they apply.",
    "Regla activa: {rules}": "Active rule: {rules}",
    "Reglas activas: {rules}": "Active rules: {rules}",

    # ── Propiedades de utilidad ────────────────────────────────────────
    "Nombre:": "Name:",
    "Tipo de red:": "Network type:",
    "Automático (según la capa)": "Automatic (per layer)",
    "Con buzones (pipe)": "With manholes (pipe)",
    "A presión (pressure)": "Pressure",
    "Familia:": "Family:",
    "Tamaño (catálogo):": "Size (catalog):",

    # ── Estado / mensajes comunes ──────────────────────────────────────
    "Cargando…": "Loading…",
    "Proyecto cerrado.": "Project closed.",
    "Confirmar eliminación": "Confirm deletion",
    "Aceptar": "OK",
    "Cancelar": "Cancel",
    "Error": "Error",
    "Duct banks guardados: 0": "Duct banks saved: 0",

    # ── Términos aislados frecuentes (para listas / tooltips) ──────────
    "Bancoducto": "Duct Bank",
    "Envolvente": "Envelope",
    "Conductos": "Conduits",
    "Tubería": "Pipe",
    "conducto(s)": "conduit(s)",
    "(sin asignar)": "(not assigned)",
    "(sin nombre)": "(no name)",
    "Doble-click para editar.": "Double-click to edit.",

    # ── Asistente: capas de la hoja (layer_dialog) ────────────────────
    "Capas de la hoja {n}": "Sheet {n} layers",
    "Buscar capa…": "Search layer…",
    "Mostrar todas": "Show all",
    "Ocultar todas": "Hide all",
    "Visibles: {v} de {t} capas": "Visible: {v} of {t} layers",
    "Rueda = zoom · botón central = desplazar": "Wheel = zoom · middle button = pan",
    "Continuar": "Continue",
    "Hoja anterior": "Previous sheet",
    "Hoja siguiente": "Next sheet",
    "Hoja {n} / {total}": "Sheet {n} / {total}",
    "Todas": "All",
    "Otras": "Other",
    "Reconocimiento cancelado — hoja cargada con las capas elegidas.":
        "Recognition cancelled — sheet loaded with the chosen layers.",
    "Capa": "Layer",
    "Trazos": "Paths",
    "Rol": "Role",
    "Ignorar": "Ignore",
    "Capas usadas (asignadas automáticamente por su nombre):":
        "Layers used (assigned automatically by name):",
    "Líneas": "Lines",
    "Bóvedas": "Vaults",
    "Hoja {n}": "Sheet {n}",
    "Componer hoja…": "Compose sheet…",
    "Componer hoja de trabajo": "Compose working sheet",
    "Componer hoja de trabajo…": "Compose working sheet…",
    "Tomar área": "Take area",
    "Tomar hoja completa": "Take whole sheet",
    "Hojas": "Sheets",
    "Escala de la hoja": "Sheet scale",
    "Escala pieza": "Piece scale",
    "Imán": "Magnet",
    "Ángulo": "Angle",
    "Elegir otra hoja del PDF, revisar sus capas y reconocerla.":
        "Pick another sheet of the PDF, review its layers and recognize it.",
    "Ajustar capas…": "Adjust layers…",
    "Solo si el plot usa otros nombres: indicar qué capas son líneas y bóvedas.":
        "Only if the plot uses other names: say which layers are lines and vaults.",
    "Cambio de hoja cancelado — se mantiene la hoja {n}.":
        "Sheet change cancelled — sheet {n} is kept.",
    "Abandonadas (AB): {a}.": "Abandoned (AB): {a}.",
    "Unir tramos en rutas": "Join segments into routes",
    "En cada cruce sigue de frente; el ramal empieza otra ruta. "
    "Si no hay trayectoria clara, no une nada. No mueve puntos.":
        "At each crossing it continues straight; the branch starts another route. "
        "If the path is not clear, nothing is joined. No points are moved.",
    "Capas ocultas por ti: {n} (no se dibujan ni se reconocen)":
        "Layers you hid: {n} (neither drawn nor recognized)",
    "Quiebres sin bóveda: {h} (cajas ocultas).": "Bends without vault: {h} (hidden boxes).",
    # ── Diálogo de Opciones ────────────────────────────────────────────
    "El cambio se aplica al instante en menús y paneles principales. "
    "Algunas ventanas ya abiertas pueden requerir cerrarse y volver "
    "a abrirse para verse completamente en el nuevo idioma.":
        "The change is applied instantly to menus and main panels. "
        "Some already-open windows may need to be closed and reopened "
        "to appear fully in the new language.",

    # ── Menú Archivo (extras) ──────────────────────────────────────────
    "Abrir PDF…": "Open PDF…",
    "Abrir proyecto…": "Open project…",
    "Guardar proyecto": "Save project",
    "Guardar proyecto como…": "Save project as…",

    # ── Menú Edición ───────────────────────────────────────────────────
    "&Archivo": "&File",
    "&Edición": "&Edit",
    "&Ver": "&View",
    "&Herramientas": "&Tools",
    "A&yuda": "&Help",

    # ── Menú Herramientas ──────────────────────────────────────────────
    "Insertar buzón en línea…": "Insert manhole in-line…",
    "Instalar familia personalizada…": "Install custom family…",
    "Desinstalar familia personalizada…": "Uninstall custom family…",
    "Georreferenciar…": "Georeference…",
    "Quitar georreferencia": "Remove georeferencing",

    # ── Menú Ayuda ─────────────────────────────────────────────────────
    "Manual de usuario": "User manual",
    "Atajos de teclado": "Keyboard shortcuts",

    # ── Toolbar principal ──────────────────────────────────────────────
    "(no instalado)": "(not installed)",
    "Versión de Civil 3D. El catálogo imperial se busca en\n"
    "C:\\ProgramData\\Autodesk\\C3D <año>\\<idioma>\\Pipes Catalog\\US Imperial Structures":
        "Civil 3D version. The imperial catalog is looked up under\n"
        "C:\\ProgramData\\Autodesk\\C3D <year>\\<lang>\\Pipes Catalog\\US Imperial Structures",
    "Idioma del catálogo Civil 3D a usar (subcarpeta esp/enu/etc.)":
        "Civil 3D catalog language to use (esp/enu subfolder etc.)",

    # ── Toolbox (dock izquierdo, secciones) ────────────────────────────
    "Vista y páginas": "View and pages",
    "Página:": "Page:",
    "Transparencia del PDF:": "PDF transparency:",
    "Dibujar utilidad": "Draw utility",
    "Tipo de utilidad:": "Utility type:",
    "Trazar centerline": "Draw centerline",
    "<i>Clic para agregar vértices, Enter cierra. "
    "Se exporta al DXF en su propia capa.</i>":
        "<i>Click to add vertices, Enter closes. "
        "Exported to DXF on its own layer.</i>",
    "Leader (flecha simple)": "Leader (simple arrow)",
    "Orientación:": "Orientation:",
    "<i>El Leader es solo flecha, sin texto.</i>":
        "<i>The Leader is just an arrow, no text.</i>",
    "Texto libre": "Free text",
    "Borrar zona": "Erase zone",
    "<i>Clic para agregar vértices, Enter cierra. "
    "Al exportar borra el plano dentro del polígono.</i>":
        "<i>Click to add vertices, Enter closes. "
        "On export, erases the plan inside the polygon.</i>",
    "<i>Dibuja la cara interior del duct bank en pulgadas: primero el "
    "rectángulo del contorno, luego cada conducto redondo dentro.</i>":
        "<i>Draw the interior face of the duct bank in inches: first the "
        "outline rectangle, then each round conduit inside.</i>",

    # ── Panel propiedades ──────────────────────────────────────────────
    "Elev. de rasante inicial (ft):": "Start grade elev. (ft):",
    "Elev. de rasante final (ft):":   "End grade elev. (ft):",
    "Familia (catálogo):": "Family (catalog):",
    "Tamaño (catálogo):":  "Size (catalog):",

    # ── Barra de estado ────────────────────────────────────────────────
    "Modo: inactivo": "Mode: idle",
    "Georref: no": "Georef: no",
    "Georref: no (escala titleblock)": "Georef: no (titleblock scale)",
    "Modo claro": "Light mode",
    "Modo oscuro": "Dark mode",
    "Fondo blanco": "White background",
    "Fondo negro": "Black background",
    "Más translúcido": "More translucent",
    "Más opaco": "More opaque",
    "Escribe un número de página y pulsa Enter": "Type a page number and press Enter",
    "Clic para cambiar la escala del plano (1\"=X ft)":
        "Click to change the plan scale (1\"=X ft)",
    "Opacidad del PDF y color de fondo (blanco/negro)":
        "PDF opacity and background color (white/black)",
    "Altura (pies):": "Height (feet):",
    "Rotación (°):": "Rotation (°):",
    "Excel": "Excel",
    "dibujo": "drawing",

    # ── Menú contextual / acciones sobre selección ────────────────────
    "Oculto — no se dibuja ni se crea en Civil3D como buzón real.":
        "Hidden — not drawn or created in Civil3D as a real manhole.",

    # ── Toolbox: botones de acción de cada sección ────────────────────
    "Dibujar utilidad": "Draw utility",
    "Colocar Leader": "Place Leader",
    "Texto libre": "Free text",
    "Borrar zona": "Erase zone",
    "Trazar centerline": "Draw centerline",
    "Abrir diseñador de Duct Bank": "Open Duct Bank Designer",
    "Abandonado": "Abandoned",
    "Marca la utilidad como abandonada: se dibuja con "
    "línea discontinua ──/── W ── en el DXF.":
        "Mark the utility as abandoned: drawn with a dashed line "
        "──/── W ── in the DXF.",
    "Extender: continuar la misma": "Extend: continue same",
    "Salir de dibujar utilidad": "Exit draw utility",
    "Coloque Leader…": "Place Leader…",
    "Terminar zona (Enter)": "Finish zone (Enter)",
    "Borrar zona (polígono)": "Erase zone (polygon)",
    "Terminar centerline (Enter)": "Finish centerline (Enter)",
    "Estilo de texto": "Text style",

    # ── Tipos de utilidad (mostrados en el combo Tipo de utilidad) ────
    "Agua (W)": "Water (W)",
    "Alcantarillado (SS)": "Sanitary Sewer (SS)",
    "Drenaje (SD)": "Storm Drain (SD)",
    "Gas (G)": "Gas (G)",
    "Eléctrico (E)": "Electric (E)",
    "Telecomunicaciones (T)": "Telecommunications (T)",

    # ── Materiales de tubería ─────────────────────────────────────────
    "Material sin definir": "Undefined material",
    "Hormigón armado": "Reinforced concrete",
    "Acero corrugado": "Corrugated steel",
    "Plástico ABS": "ABS plastic",
    "Fundición dúctil": "Ductile iron",
    "PVC": "PVC",

    # ── Orientaciones (Leader) ────────────────────────────────────────
    "Horizontal": "Horizontal",
    "Vertical": "Vertical",
    "Diagonal": "Diagonal",

    # ── Placeholders comunes ──────────────────────────────────────────
    "p.ej. 900 mm Corrugated HDPE Pipe": "e.g. 900 mm Corrugated HDPE Pipe",

    # ── Mensajes de estado (self._info) ────────────────────────────────
    "Abre un PDF o proyecto primero.": "Open a PDF or project first.",
    "Abre un PDF o proyecto.": "Open a PDF or project.",
    "Buzón insertado. Edítalo en la tab Buzones.": "Manhole inserted. Edit it on the Manholes tab.",
    "Centerline agregado — solo referencia para calzar la georreferenciación, no es una utilidad.":
        "Centerline added — reference only for georeferencing alignment, it's not a utility.",
    "Clic sobre una línea para insertar un buzón (Esc para salir).":
        "Click on a line to insert a manhole (Esc to exit).",
    "Comando Leader finalizado (Enter)": "Leader command finished (Enter)",
    "Continuando la MISMA utilidad: clic para agregar puntos, Enter finaliza.":
        "Continuing the SAME utility: click to add points, Enter finishes.",
    "Copiado. Ctrl+V para pegar una copia.": "Copied. Ctrl+V to paste a copy.",
    "Edición terminada (Enter)": "Edit finished (Enter)",
    "Editar Leader: arrastra un vértice (posición/longitud) o el trazo para mover. Enter/Esc termina.":
        "Edit Leader: drag a vertex (position/length) or the stroke to move. Enter/Esc finishes.",
    "El Leader simple no lleva texto.": "The simple Leader has no text.",
    "El plano no está georreferenciado.": "The plan is not georeferenced.",
    "Georreferencia quitada; se usa la escala del titleblock.":
        "Georeferencing removed; the titleblock scale is used.",
    "Inserción de buzón cancelada": "Manhole insertion canceled",
    "Leader colocado. Clic en la cabeza de flecha del siguiente (Esc para salir).":
        "Leader placed. Click on the arrowhead of the next one (Esc to exit).",
    "Leader diagonal: cabeza → inicio del landing (bisagra) → final del cuerpo. Enter/Esc para salir.":
        "Diagonal Leader: arrowhead → landing start (elbow) → body end. Enter/Esc to exit.",
    "Leader: cabeza de flecha → final del cuerpo. Enter/Esc para salir.":
        "Leader: arrowhead → body end. Enter/Esc to exit.",
    "Los buzones/cajas solo se insertan en redes de gravedad o conduit (no en presión).":
        "Manholes/boxes are only inserted in gravity or conduit networks (not pressure).",
    "No hay líneas dibujadas para insertar un buzón.":
        "No drawn lines to insert a manhole.",
    "No se encontró el PDF original. Se exportarán solo las anotaciones (utilidades, leaders, textos).":
        "Original PDF not found. Only the annotations (utilities, leaders, texts) will be exported.",
    "Pegado (copia desplazada).": "Pasted (displaced copy).",
    "Puntos cancelados": "Points canceled",
    "Salió del modo": "Exited mode",
    "Selecciona algo para copiar.": "Select something to copy.",
    "Selecciona primero una utilidad, Leader, texto o zona":
        "First select a utility, Leader, text or zone",
    "Selección quitada": "Selection cleared",
    "Solo desde un extremo se continúa; se creará una utilidad NUEVA. Clic para agregar, Enter finaliza.":
        "Only from an endpoint can it continue; a NEW utility will be created. Click to add, Enter finishes.",
    "Utilidad NUEVA (rama en F): clic para agregar puntos, Enter finaliza.":
        "NEW utility (F branch): click to add points, Enter finishes.",
    "Vértice eliminado": "Vertex deleted",
    "Zona agregada: al exportar tapa la geometría base del plano dentro de ella (no toca tus utilidades).":
        "Zone added: on export it covers the base plan geometry inside it (does not touch your utilities).",
    "Zona cancelada": "Zone canceled",
    "Arrastra para mover · clic en vértice extiende (F) · clic derecho elimina":
        "Drag to move · click on vertex extends (F) · right-click deletes",
    "Deshacer": "Undo",
    "Rehacer": "Redo",

    # ── Diálogos QMessageBox comunes ───────────────────────────────────
    "Nada": "Nothing",
    "Nada que guardar": "Nothing to save",
    "Sin PDF": "No PDF",
    "Sin plano": "No plan",
    "Escala": "Scale",
    "Eliminar conducto": "Delete conduit",
    "Guardar y cerrar": "Save and close",

    # ── Diálogo Opciones extra ─────────────────────────────────────────
    "Idioma:": "Language:",

    # ── Toggle "Mostrar medidas" del diseñador de bancoductos ─────────
    "Mostrar\nmedidas": "Show\ndimensions",
    "Ocultar\nmedidas": "Hide\ndimensions",
    "Muestra las cotas de separación entre conductos y "
    "resguardo al borde/margen (en rojo).":
        "Shows the spacing dimensions between conduits and "
        "the clearance to the edge/margin (in red).",
    "Oculta las cotas del diseño.":
        "Hides the design dimensions.",

    # ── Mensajes de reglas obligatorias del diseñador ─────────────────
    "Diámetro debe ser > 0.": "Diameter must be > 0.",
    "El conducto queda fuera de la envolvente.":
        "The conduit is outside the envelope.",
    'El conducto viola el resguardo mínimo al borde ({v:g}").':
        'The conduit violates the minimum edge clearance ({v:g}").',
    'Separación entre conductos < {v:g}".':
        'Spacing between conduits < {v:g}".',
    "Los conductos se solapan.": "The conduits overlap.",

    # ── Diálogos: Acerca de / Manual / Atajos ─────────────────────────
    "Cerrar": "Close",
    "Acerca de": "About",
    "Versión": "Version",
    "para ingeniería civil (agua, alcantarillado, gas, "
    "eléctrico, telefonía, drenaje).":
        "for civil engineering (water, sewer, gas, "
        "electric, telecom, drainage).",
    "Convierte un PDF de plano a DXF y te deja marcar utilidades, Multileaders y notas "
    "sobre la imagen, exportando todo en las mismas coordenadas para abrirlo en Civil 3D.":
        "Converts a plan PDF to DXF and lets you mark utilities, Multileaders and "
        "notes on the image, exporting everything in the same coordinates to open in Civil 3D.",
    "nueva": "new",
    "quitada": "removed",
    "corregida": "fixed",
    "cambiada": "changed",
    "Manual de usuario": "User manual",
    "Aplicar: finaliza utilidad/zona, o agrega texto/edición":
        "Apply: finish utility/zone, or add text/edit",
    "Quitar la selección; si no hay, salir del modo":
        "Clear selection; if none, exit mode",
    "Doble clic": "Double click",
    "Sobre un texto: editarlo": "On a text: edit it",
    "Clic derecho": "Right click",
    "Finaliza línea/zona; en editar, elimina el vértice":
        "Finish line/zone; in edit mode, delete the vertex",
    "Rueda": "Wheel",
    "Zoom · Botón central + arrastrar: desplazar":
        "Zoom · Middle button + drag: pan",
    "Atajos de teclado": "Keyboard shortcuts",

    # ── Ventanas de la app (títulos) ──────────────────────────────────
    "Al extender un extremo de una utilidad existente, los puntos nuevos "
    "se añaden a ESA misma utilidad en vez de crear una nueva.":
        "When extending an existing utility's endpoint, new points are "
        "added to THAT same utility instead of creating a new one.",

    # ── Escala / status bar / textos comunes ───────────────────────────
    "Escala": "Scale",
    "Escala —": "Scale —",
    "Opacidad": "Opacity",
    "Abre o arrastra un PDF/proyecto.": "Open or drag a PDF/project.",
    "Primero abre un PDF o proyecto.": "First, open a PDF or project.",

    # ── Modos del canvas (barra de estado) ─────────────────────────────
    "Modo: inactivo  ·  clic en el dibujo para seleccionar":
        "Mode: idle  ·  click on the drawing to select",
    "Modo: EXTENDIENDO desde el vértice — clic agrega puntos, Enter finaliza":
        "Mode: EXTENDING from vertex — click to add points, Enter finishes",
    "Modo: dibujar utilidad  ·  Enter finaliza":
        "Mode: draw utility  ·  Enter finishes",
    "Modo: Leader — clic en la cabeza de flecha (dónde señala)":
        "Mode: Leader — click on the arrowhead (target)",
    "Modo: Leader — clic en el inicio del landing (bisagra)":
        "Mode: Leader — click on the landing start (elbow)",
    "Modo: Leader — clic en el final del cuerpo":
        "Mode: Leader — click on the body's end point",
    "Modo: texto libre — clic donde escribir · Enter aplica":
        "Mode: free text — click where to write · Enter applies",
    "Modo: borrar zona — clic para el polígono, Enter cierra":
        "Mode: erase zone — click to add polygon points, Enter closes",
    "Modo: trazar centerline — clic agrega puntos, Enter finaliza":
        "Mode: draw centerline — click to add points, Enter finishes",
    "Modo: editar — arrastra vértice · clic en tramo inserta · clic-en-vértice extiende (F) · clic derecho elimina":
        "Mode: edit — drag vertex · click on segment inserts · click-on-vertex extends (F) · right-click deletes",

    # ── Diálogo del diseñador (dinámicos + editor de 4 lados) ─────────
    "Vincular los cuatro valores.\n"
    "Cuando está activado, cambiar uno los actualiza a los cuatro.":
        "Link the four values.\n"
        "When active, changing one updates all four.",
    "Superior": "Top",
    "Inferior": "Bottom",
    "Izquierdo": "Left",
    "Derecho": "Right",
    "Sup. Izq.": "Top Left",
    "Sup. Der.": "Top Right",
    "Inf. Izq.": "Bottom Left",
    "Inf. Der.": "Bottom Right",
    "vértices": "vertices",
    "Conductos": "Conduits",
    "Conductos: 0": "Conduits: 0",
    "Nuevo": "New",
    "¿Descartar el diseño actual y empezar uno nuevo?":
        "Discard current design and start a new one?",
    "Error al abrir": "Error opening",
    "Error al guardar": "Error saving",
    "Ayuda — Duct Bank": "Help — Duct Bank",
    "1) En el panel derecho, ponle <b>Nombre</b> y <b>Asigna la utilidad</b> "
    "que este bancoducto reemplazará al importar en Civil 3D.<br>"
    "2) Ajusta el <b>Ancho</b> y <b>Alto</b> de la envolvente (pulgadas).<br>"
    "3) Elige un diámetro y usa la herramienta <b>Conducto</b>: cada clic "
    "dentro de la envolvente coloca un conducto.<br>"
    "4) Con el <b>Puntero</b>: click selecciona un conducto y arrástralo "
    "para moverlo. Los datos del seleccionado (X/Y/diámetro/etiqueta) "
    "aparecen en el panel derecho.<br>"
    "5) <b>Eliminar</b> quita el conducto que hagas clic.<br>"
    "6) La rueda del ratón acerca/aleja; el botón central mueve la vista.<br>"
    "7) Si hay un problema con el diseño (conducto fuera, solape…) aparece "
    "un banner rojo en el tope del canvas con el mensaje.<br>"
    "8) Presiona <b>Guardar y cerrar</b> — el diseño se guarda en el proyecto.":
        "1) In the right panel, set the <b>Name</b> and <b>Assign the utility</b> "
        "this duct bank will replace when imported into Civil 3D.<br>"
        "2) Adjust the <b>Width</b> and <b>Height</b> of the envelope (inches).<br>"
        "3) Pick a diameter and use the <b>Conduit</b> tool: each click "
        "inside the envelope places a conduit.<br>"
        "4) With the <b>Pointer</b>: click selects a conduit and drag "
        "moves it. The selected conduit's data (X/Y/diameter/label) "
        "appears in the right panel.<br>"
        "5) <b>Delete</b> removes the conduit you click on.<br>"
        "6) Mouse wheel zooms in/out; middle button pans the view.<br>"
        "7) If there is a design problem (conduit outside, overlap…) a "
        "red banner appears at the top of the canvas with the message.<br>"
        "8) Press <b>Save and close</b> — the design is saved in the project.",
    "Al exportar, esta utilidad será un duct bank (no una tubería normal).":
        "On export, this utility will be a duct bank (not a normal pipe).",
    "Sin asignar — el duct bank no se exportará.":
        "Not assigned — the duct bank will not be exported.",

    # ── Hints, tooltips y strings dinámicos del diseñador ─────────────
    "Ej. Duct Bank A – Telecom": "Ex. Duct Bank A – Telecom",
    "Etiqueta (opcional)": "Label (optional)",
    "Nivel de zoom actual.\n"
    "Usa los botones Zoom +/- de la toolbar\n"
    "o la rueda del ratón.":
        "Current zoom level.\n"
        "Use the Zoom +/- buttons on the toolbar\n"
        "or the mouse wheel.",
    "Cerrar sin guardar cambios.": "Close without saving changes.",
    "Guardar el bancoducto en el proyecto y cerrar el diseñador.":
        "Save the duct bank in the project and close the designer.",
    "Activa las reglas de diseño personalizables abajo.\n\n"
    "Cuando está DESACTIVADO, el diseño puede colocar conductos sin\n"
    "respetar ninguna separación ni resguardo (los chequeos geométricos\n"
    "básicos — dentro de envolvente, sin colisión gruesa — siguen).":
        "Enable the customizable design rules below.\n\n"
        "When DISABLED, the design may place conduits without\n"
        "respecting any spacing or clearance (basic geometric checks —\n"
        "inside envelope, no gross collision — still apply).",
    "Hueco mínimo entre bordes de conductos.\n0\" = sin regla.":
        "Minimum gap between conduit edges.\n0\" = no rule.",
    "Distancia mínima entre borde del conducto\ny borde de la envolvente. 0\" = sin regla.":
        "Minimum distance between conduit edge\nand envelope edge. 0\" = no rule.",
    "Elige un diámetro y usa la herramienta <b>Conducto</b> "
    "para colocarlo dentro de la envolvente.":
        "Pick a diameter and use the <b>Conduit</b> tool "
        "to place it inside the envelope.",
    "Al importar en Civil 3D, crea el sólido 3D del contenedor\n"
    "(prisma de concreto) además de los conductos internos.\n\n"
    "Desactívalo si el contenedor ya existe en el DWG o si solo\n"
    "necesitas los conductos como pipes.":
        "On import into Civil 3D, creates the 3D solid of the container\n"
        "(concrete prism) in addition to the internal conduits.\n\n"
        "Disable if the container already exists in the DWG or if you\n"
        "only need the conduits as pipes.",
    "Se dibujará el sólido 3D del contenedor + los conductos internos.":
        "The 3D container solid + internal conduits will be drawn.",
    "Solo se dibujarán los conductos internos. El sólido 3D del contenedor NO se creará.":
        "Only internal conduits will be drawn. The 3D container solid will NOT be created.",
    "Solo se dibujarán los conductos internos. El sólido 3D del "
    "contenedor NO se creará.":
        "Only internal conduits will be drawn. The 3D container "
        "solid will NOT be created.",
    "Reglas custom desactivadas. Los chequeos geométricos básicos "
    "(dentro de envolvente, sin colisión) siguen activos.":
        "Custom rules disabled. Basic geometric checks "
        "(inside envelope, no collision) still apply.",
    "sep.": "sep.",
    "borde": "edge",
    "Sin valores puestos — configura arriba para que apliquen.":
        "No values set — configure above so they apply.",
    "Regla activa: {rules}": "Active rule: {rules}",
    "Reglas activas: {rules}": "Active rules: {rules}",
    "Cuando está activado, los clics del ratón se pegan (imán) al retículo\n"
    "de 0.25 pulgadas del fondo del lienzo. Sirve para colocar conductos\n"
    "y medir con precisión ⅟₄ pulgada.\n\n"
    "Desactívalo si necesitas posicionar algo en un valor libre no múltiplo\n"
    "de 0.25\".":
        "When enabled, mouse clicks snap (magnet) to the 0.25-inch\n"
        "background grid of the canvas. Useful for placing conduits\n"
        "and measuring with ¼-inch precision.\n\n"
        "Disable it if you need to position something at a free value\n"
        "not a multiple of 0.25\".",
    "Click para seleccionar un conducto.\n"
    "Arrastra un conducto para moverlo.":
        "Click to select a conduit.\n"
        "Drag a conduit to move it.",
    "Click dentro de la envolvente para colocar un conducto del diámetro elegido.":
        "Click inside the envelope to place a conduit of the chosen diameter.",
    "Click en un conducto para eliminarlo.":
        "Click on a conduit to delete it.",
    "Click en un conducto para seleccionarlo. Arrástralo para moverlo.":
        "Click on a conduit to select it. Drag it to move it.",
    'Click dentro de la envolvente para colocar un conducto de {d}".':
        'Click inside the envelope to place a {d}" conduit.',
    "Centrar la vista sobre la envolvente":
        "Center the view on the envelope",

    # ── Toolbox / secciones (dock izquierdo) ───────────────────────────
    "Duct Bank": "Duct Bank",
    "Diseña la sección transversal del Duct Bank\n"
    "(envolvente rectangular + conductos internos).":
        "Design the cross-section of the Duct Bank\n"
        "(rectangular envelope + internal conduits).",

    # ── app_window.py ──
    "Nuevo lienzo…":
        "New canvas…",
    "Mostrar cruces/conflictos":
        "Show crossings/conflicts",
    "Marca los puntos donde dos utilidades se cruzan geométricamente en el plano.\n  · Amarillo ⓘ: cruce sano (distinta cota, se pasan por encima/debajo).\n  · Rojo ⚠: conflicto (misma cota o sin cota → chocan).\nApagarlo oculta las marcas y el contador de la barra de estado.":
        "Marks the points where two utilities cross geometrically on the plan.\n  · Yellow ⓘ: safe crossing (different elevation, one passes over/under the other).\n  · Red ⚠: conflict (same elevation or no elevation → they clash).\nTurning it off hides the marks and the status bar counter.",
    "Acciones":
        "Actions",
    "Deshacer (Ctrl+Z)":
        "Undo (Ctrl+Z)",
    "Rehacer (Ctrl+Shift+Z)":
        "Redo (Ctrl+Shift+Z)",
    "Civil 3D:":
        "Civil 3D:",
    "Negrita":
        "Bold",
    "<i>Guarda pulsando enter </i>":
        "<i>Press Enter to save </i>",
    "En curso":
        "In progress",
    "Finalizar (Enter)":
        "Finish (Enter)",
    "Deshacer punto":
        "Undo point",
    "Mover con precisión":
        "Precise move",
    "Cotas por tramo":
        "Elevations per segment",
    "Activar edición por tramo":
        "Enable per-segment editing",
    "Activa la edición de cotas por tramo. Cuando está apagado se usan solo las rasantes de inicio/fin (interpolación lineal). Cuando se enciende, cada Inicio y Fin es totalmente independiente y editable, y en el lienzo aparecen etiquetas T1, T2… por tramo.":
        "Enables per-segment elevation editing. When off, only the start/end inverts are used (linear interpolation). When on, each Start and End is fully independent and editable, and T1, T2… labels appear on the canvas for each segment.",
    "Tramo":
        "Segment",
    "Inicio (ft)":
        "Start (ft)",
    "Fin (ft)":
        "End (ft)",
    "Long (ft)":
        "Length (ft)",
    "Propiedades del buzón":
        "Manhole properties",
    "(automática)":
        "(automatic)",
    "Altura deseada del buzón, en pies. Si se llena, al importar la red en Civil3D\nse ajusta la cota de tapa (Rim = Sump + esta altura) para que la propiedad\n'Altura de estructura' salga exacta. Vacío (0) = se calcula automático desde el terreno.":
        "Desired manhole height, in feet. If set, when the network is imported into Civil 3D\nthe rim elevation is adjusted (Rim = Sump + this height) so the\n'Structure height' property comes out exact. Empty (0) = computed automatically from the surface.",
    "Código:":
        "Code:",
    "Tamaño:":
        "Size:",
    "Altura (Pies):":
        "Height (ft):",
    "Red:":
        "Network:",
    "Origen:":
        "Source:",
    "Cambiar a elemento curvo":
        "Change to curved element",
    "Marca este vértice como la esquina de un elemento curvo (p.ej. el codo de un\nbancoducto) en vez de un buzón/caja normal. Pasa a la pestaña 'Curvas' y no se\nexporta como buzón en el DXF (se marca con un punto PDFCAD_CURVE aparte).":
        "Marks this vertex as the corner of a curved element (e.g. the bend of a\nduct bank) instead of a regular manhole/box. It moves to the 'Curves' tab and is not\nexported as a manhole in the DXF (it is marked with a separate PDFCAD_CURVE point).",
    "Desactivar/activar buzón":
        "Disable/enable manhole",
    "Este vértice se detectó automáticamente pero no quieres un buzón real ahí.\nSe deja de dibujar en el lienzo y, al exportar/importar en Civil3D, se usa la\nfamilia 'Estructura nula' (invisible) en vez de un buzón visible — la red sigue\nconectada, solo no se ve el manhole.":
        "This vertex was detected automatically but you don't want a real manhole there.\nIt is no longer drawn on the canvas and, when exporting/importing into Civil 3D, the\n'Null structure' family (invisible) is used instead of a visible manhole — the network stays\nconnected, the manhole just isn't shown.",
    "Ver etiquetas de buzón y en el DXF exportado":
        "Show manhole labels, also in the exported DXF",
    "Haz clic en un buzón de la lista (o en su círculo en el lienzo) para ver y editar sus propiedades.":
        "Click a manhole in the list (or its circle on the canvas) to view and edit its properties.",
    "Propiedades del elemento curvo":
        "Curved element properties",
    "(automático)":
        "(automatic)",
    "Radio deseado de la tubería curva, en pies. Vacío (0) = automático:\nal importar en Civil3D se usa 6× el ancho/diámetro interior de la tubería.":
        "Desired radius of the curved pipe, in feet. Empty (0) = automatic:\nwhen importing into Civil 3D, 6× the pipe's inner width/diameter is used.",
    "Familia (tubería):":
        "Family (pipe):",
    "Radio (Pies):":
        "Radius (ft):",
    "Volver a tratar como buzón/caja":
        "Treat as manhole/box again",
    "Haz clic en un elemento curvo de la lista (o en su marcador violeta en el lienzo) para ver y editar sus propiedades.":
        "Click a curved element in the list (or its purple marker on the canvas) to view and edit its properties.",
    "Propiedades del centerline":
        "Centerline properties",
    "Longitud (ft):":
        "Length (ft):",
    "Haz clic en un centerline de la lista (o en su línea magenta punteada en el lienzo) para ver y editar sus propiedades. Referencia propia de una calle (distinta de las utilidades) para calzar contra la calle real al georreferenciar — no representa ninguna tubería.":
        "Click a centerline in the list (or its dotted magenta line on the canvas) to view and edit its properties. A street reference of its own (different from utilities) used to match against the real street when georeferencing — it does not represent any pipe.",
    "Escala 1\"={v}'":
        "Scale 1\"={v}'",
    "Escala del plano":
        "Plan scale",
    "1 pulgada del PDF equivale a X pies reales:":
        "1 inch of the PDF equals X real feet:",
    "Escala cambiada a 1\"={v}'.":
        "Scale changed to 1\"={v}'.",
    "Opacidad del PDF: {pct}%":
        "PDF opacity: {pct}%",
    "extremo":
        "end",
    "vértice":
        "vertex",
    "tramo":
        "segment",
    "⊙ Snap a {q} de «{c}»":
        "⊙ Snap to {q} of «{c}»",
    "Georref: {sistema}{rms}":
        "Georef: {sistema}{rms}",
    "Deshacer (Ctrl+Z) — {n} paso":
        "Undo (Ctrl+Z) — {n} step",
    "Deshacer (Ctrl+Z) — {n} pasos":
        "Undo (Ctrl+Z) — {n} steps",
    "Rehacer (Ctrl+Shift+Z) — {n} paso":
        "Redo (Ctrl+Shift+Z) — {n} step",
    "Rehacer (Ctrl+Shift+Z) — {n} pasos":
        "Redo (Ctrl+Shift+Z) — {n} steps",
    "Abrir PDF":
        "Open PDF",
    "Abriendo PDF…":
        "Opening PDF…",
    "Creando lienzo…":
        "Creating canvas…",
    "Lienzo {n} · 1\"={e:g}'":
        "Canvas {n} · 1\"={e:g}'",
    "Detectado PDF vectorial ({n} trazos)…":
        "Vector PDF detected ({n} strokes)…",
    "Detectado PDF imagen/escaneo — continúa con el dibujo manual.":
        "Image/scanned PDF detected — continue with manual drawing.",
    "PDF imagen: continúa con el dibujo manual.":
        "Image PDF: continue with manual drawing.",
    "Cargando hoja…":
        "Loading sheet…",
    "Componer hoja":
        "Compose sheet",
    "No se pudo armar la hoja compuesta:\n\n{e}":
        "The composite sheet could not be built:\n\n{e}",
    "Abre un PDF para componer su hoja de trabajo.":
        "Open a PDF to compose its work sheet.",
    "Composición cancelada — se mantiene la hoja actual.":
        "Composition cancelled — the current sheet is kept.",
    "Organizar hojas":
        "Arrange sheets",
    "Abre un PDF para organizar sus hojas.":
        "Open a PDF to arrange its sheets.",
    "Organización guardada. Hoja principal: {n}.":
        "Arrangement saved. Main sheet: {n}.",
    "Capas de hojas organizadas":
        "Arranged sheets layers",
    "Organiza al menos dos hojas para abrir esta vista.":
        "Arrange at least two sheets to open this view.",
    "Capas de las hojas organizadas guardadas.":
        "Arranged sheets layers saved.",
    "Reconocimiento":
        "Recognition",
    "No se pudieron reconocer las hojas:\n\n{e}":
        "The sheets could not be recognized:\n\n{e}",
    "La hoja principal debe pertenecer al PDF abierto.":
        "The main sheet must belong to the open PDF.",
    "La lista de PDF no coincide con las hojas elegidas.":
        "The PDF list does not match the chosen sheets.",
    "El PDF cambió mientras se elegían sus hojas.":
        "The PDF changed while its sheets were being chosen.",
    "No se pudieron incorporar los PDF:\n\n{e}":
        "The PDFs could not be added:\n\n{e}",
    "No se pudo reconocer la hoja:\n\n{e}":
        "The sheet could not be recognized:\n\n{e}",
    "Reconocimiento listo, pero no hay imagen de la hoja para la vista previa.":
        "Recognition finished, but there is no sheet image for the preview.",
    "Reconocimiento cancelado — editor vacío.":
        "Recognition cancelled — empty editor.",
    "Codos como esquina + radio (CV): {c}.":
        "Bends as corner + radius (CV): {c}.",
    "Página {n} cargada.":
        "Page {n} loaded.",
    "Guardando proyecto…":
        "Saving project…",
    "Proyecto guardado: {archivo}":
        "Project saved: {archivo}",
    "Guardar proyecto como":
        "Save project as",
    "Proyecto (*.digproj)":
        "Project (*.digproj)",
    "Abrir proyecto":
        "Open project",
    "Abriendo proyecto…":
        "Opening project…",
    "Proyecto abierto ({n} utilidades){civil}. Ctrl+S guarda en este mismo archivo.":
        "Project opened ({n} utilities){civil}. Ctrl+S saves to this same file.",
    "Familias no instaladas":
        "Families not installed",
    "Instalar familias…":
        "Install families…",
    "Seguir sin instalar":
        "Continue without installing",
    "Cambios sin guardar":
        "Unsaved changes",
    "Hay cambios sin guardar. ¿Deseas guardarlos?":
        "There are unsaved changes. Do you want to save them?",
    "Unir a utilidad existente":
        "Join existing utility",
    "El punto donde estás dibujando coincide con el extremo de otra utilidad del mismo tipo.\n\n¿Quieres UNIRLA como parte de esa utilidad (misma polilínea, una sola red)?\n\nSí = extiende la utilidad existente.\nNo = crea una utilidad nueva que la toca (juntura automática al importar).":
        "The point where you are drawing matches the end of another utility of the same type.\n\nDo you want to JOIN it as part of that utility (same polyline, a single network)?\n\nYes = extends the existing utility.\nNo = creates a new utility that touches it (automatic junction on import).",
    "Necesita al menos {n} puntos":
        "Needs at least {n} points",
    "Desactivar edición por tramo":
        "Disable per-segment editing",
    "Tramo {t}: vértice {v0} → vértice {v1}\nLongitud {largo} ft\nClic para resaltarlo en el lienzo.":
        "Segment {t}: vertex {v0} → vertex {v1}\nLength {largo} ft\nClick to highlight it on the canvas.",
    "Civil 3D del proyecto no disponible":
        "Project's Civil 3D not available",
    "El proyecto se guardó con Civil 3D {version}, pero esa versión no está instalada/detectada en esta PC.\n\nSe mantiene la versión activa ({activa}). El catálogo de familias saldrá de esa versión.":
        "The project was saved with Civil 3D {version}, but that version is not installed/detected on this PC.\n\nThe active version ({activa}) is kept. The family catalog will come from that version.",
    "{ancho}\" x {alto}\" — {n} conducto(s)":
        "{ancho}\" x {alto}\" — {n} conduit(s)",
    "(por defecto)":
        "(default)",
    "(sin familia)":
        "(no family)",
    "(sin tamaños)":
        "(no sizes)",
    "{p} util · {l} lead · {t} txt · {z} zona":
        "{p} util · {l} lead · {t} txt · {z} area",
    "¿Eliminar {que}?":
        "Delete {que}?",
    "Duct banks guardados: {n}":
        "Saved duct banks: {n}",
    "Zona {i} ({n} vértices)":
        "Area {i} ({n} vertices)",
    "{cod}  ·  {n} vértices":
        "{cod}  ·  {n} vertices",
    "Hay {n} tuberías en el mismo punto, no se dibujará ningún accesorio en Civil 3D, por favor corrija el dibujo.":
        "There are {n} pipes at the same point; no fitting will be drawn in Civil 3D, please fix the drawing.",
    "«{a}» y «{b}» se cruzan a la misma cota, pero son redes distintas.\n\nEn Civil 3D no se conectarán: las tuberías quedarán chocando.":
        "«{a}» and «{b}» cross at the same elevation, but they are different networks.\n\nIn Civil 3D they will not be connected: the pipes will clash.",
    "En este vértice hay un escalón: el tramo T{a} llega a {za:.2f} ft y el T{b} sale a {zb:.2f} ft.\n\nEn Civil 3D los dos se unirán a {zc:.2f} ft (el promedio).":
        "There is a step at this vertex: segment T{a} arrives at {za:.2f} ft and T{b} leaves at {zb:.2f} ft.\n\nIn Civil 3D both will be joined at {zc:.2f} ft (the average).",
    "Demasiadas tuberías en un punto":
        "Too many pipes at one point",
    "Escalón de cota":
        "Elevation step",
    "Redes distintas a la misma cota":
        "Different networks at the same elevation",
    "Cotas en el punto de cruce:\n  • «{la}»: {za} ft\n  • «{lb}»: {zb} ft\n  • Diferencia: {dz} ft":
        "Elevations at the crossing point:\n  • «{la}»: {za} ft\n  • «{lb}»: {zb} ft\n  • Difference: {dz} ft",
    "(⚠ falta cota en al menos una de las dos utilidades — pon cotas para poder decidir si es conflicto o sugerencia de unión)":
        "(⚠ at least one of the two utilities has no elevation — set elevations to decide whether it is a conflict or a joining suggestion)",
    "Conflicto físico":
        "Physical conflict",
    "⚠ CONFLICTO entre «{la}» y «{lb}» — están a la MISMA cota en el cruce y chocan geométricamente.{cotas}\n\nNo se ofrece conexión automática aquí: hay que corregir la geometría del plano o ajustar la cota de alguna de las dos tuberías.":
        "⚠ CONFLICT between «{la}» and «{lb}» — they are at the SAME elevation at the crossing and clash geometrically.{cotas}\n\nNo automatic connection is offered here: the plan geometry must be fixed or the elevation of one of the two pipes adjusted.",
    "Conexión vertical ya aprobada":
        "Vertical connection already approved",
    "Este cruce entre «{la}» y «{lb}» ya está marcado para conectarse con una tubería vertical al importar.{cotas}\n\n¿Deseas RETIRAR la aprobación?":
        "This crossing between «{la}» and «{lb}» is already marked to be connected with a vertical pipe on import.{cotas}\n\nDo you want to WITHDRAW the approval?",
    "Sugerencia de conexión vertical":
        "Vertical connection suggestion",
    "Las utilidades «{la}» y «{lb}» se cruzan pero están a cotas distintas — no chocan, una pasa por encima de la otra.{cotas}\n\n¿Quieres conectarlas con una tubería vertical al importar en Civil 3D?\n\nSí = se dibuja un tramo vertical uniendo ambas cotas.\nNo = se dejan como están (no se conectan).":
        "Utilities «{la}» and «{lb}» cross but are at different elevations — they do not clash, one passes over the other.{cotas}\n\nDo you want to connect them with a vertical pipe when importing into Civil 3D?\n\nYes = a vertical segment is drawn joining both elevations.\nNo = they are left as they are (not connected).",
    "Para generar DWG necesitas instalar el ODA File Converter (gratuito).\nSe guardó solo el DXF; ábrelo en tu CAD y «Guardar como DWG» si lo necesitas ahora.":
        "To generate DWG you need to install the ODA File Converter (free).\nOnly the DXF was saved; open it in your CAD and «Save as DWG» if you need it now.",
    "DWG generado: {archivo}":
        "DWG generated: {archivo}",
    "No se pudo generar el DWG (se conserva el DXF).\n\n{e}":
        "The DWG could not be generated (the DXF is kept).\n\n{e}",
    "Capas de LA":
        "LA layers",
    "Las capas reales de LA solo se pueden agregar si el plano está georreferenciado a EPSG:2229 (State Plane de LA).":
        "The real LA layers can only be added if the plan is georeferenced to EPSG:2229 (LA State Plane).",
    "Capas de LA agregadas: {calles} tramos de calle, {parcelas} parcelas.":
        "LA layers added: {calles} street segments, {parcelas} parcels.",
    "No se pudieron descargar las capas de LA (¿internet?).\n\n{e}":
        "The LA layers could not be downloaded (internet?).\n\n{e}",
    "Guardar DXF":
        "Save DXF",
    "⚠ Georef: matriz presente pero active()=False.\n  matrix[0]={m0}\n  matrix[1]={m1}\n  det={det}, epsg={epsg}\n  → Exportado en coordenadas de escala.":
        "⚠ Georef: matrix present but active()=False.\n  matrix[0]={m0}\n  matrix[1]={m1}\n  det={det}, epsg={epsg}\n  → Exported in scale coordinates.",
    "(Sin georreferenciación configurada.)":
        "(No georeferencing configured.)",
    "Listo":
        "Done",
    "Exportado (solo anotaciones):\n{archivo}{georef}":
        "Exported (annotations only):\n{archivo}{georef}",
    "DXF de anotaciones exportado (georef).":
        "Annotations DXF exported (georef).",
    "DXF de anotaciones exportado.":
        "Annotations DXF exported.",
    "Digitalizando el plano…":
        "Digitizing the plan…",
    "Procesando":
        "Processing",
    "Error al digitalizar":
        "Digitizing error",
    "DXF exportado (georef).":
        "DXF exported (georef).",
    "DXF exportado.":
        "DXF exported.",
    "Propiedades del buzón — selecciona uno de la lista":
        "Manhole properties — select one from the list",
    "Propiedades de la caja":
        "Box properties",
    "conduit (eléctrico/telecom)":
        "conduit (electrical/telecom)",
    "gravedad":
        "gravity",
    "(sin tamaños detectados)":
        "(no sizes detected)",
    "Código repetido":
        "Duplicate code",
    "Ya existe un buzón con código «{cod}». Elige otro.":
        "A manhole with code «{cod}» already exists. Choose another one.",
    "(nada seleccionado)":
        "(nothing selected)",
    "Toda la utilidad":
        "Whole utility",
    "Un vértice":
        "One vertex",
    "Vértice #:":
        "Vertex #:",
    "Índice del vértice a mover (0 = primero).":
        "Index of the vertex to move (0 = first).",
    "Paso (ft):":
        "Step (ft):",
    "Arriba (Y+) por Paso":
        "Up (Y+) by Step",
    "Abajo (Y−) por Paso":
        "Down (Y−) by Step",
    "Izquierda (X−) por Paso":
        "Left (X−) by Step",
    "Derecha (X+) por Paso":
        "Right (X+) by Step",
    "O escribe un desplazamiento exacto:":
        "Or type an exact offset:",
    "ΔX (ft):":
        "ΔX (ft):",
    "ΔY (ft):":
        "ΔY (ft):",
    "Aplicar":
        "Apply",
    "<i>ΔY+ = norte del plano. Cada movimiento respeta Deshacer (Ctrl+Z).</i>":
        "<i>ΔY+ = plan north. Every move supports Undo (Ctrl+Z).</i>",
    "Utilidad {layer} · Ø{diam}\" · {n} vértices":
        "Utility {layer} · Ø{diam}\" · {n} vertices",
    "(sin código)":
        "(no code)",
    "Curva · {cod}":
        "Curve · {cod}",
    "Buzón · {cod}":
        "Manhole · {cod}",
    "No hay nada seleccionado para mover.":
        "Nothing is selected to move.",
    "Sin escala":
        "No scale",
    "La escala del plano no está definida — establece '1\" = X ft' antes de mover.":
        "The plan scale is not defined — set '1\" = X ft' before moving.",
    "Índice de vértice fuera de rango.":
        "Vertex index out of range.",
    "Vértice V{vi} movido ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.":
        "Vertex V{vi} moved ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.",
    "Utilidad movida ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft ({n} vértices).":
        "Utility moved ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft ({n} vertices).",
    "El elemento seleccionado no tiene posición en el lienzo.":
        "The selected element has no position on the canvas.",
    "Elemento movido ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.":
        "Element moved ΔX={dx:+.2f}ft, ΔY={dy:+.2f}ft.",
    "Propiedades del elemento curvo — selecciona uno de la lista":
        "Curved element properties — select one from the list",
    "Radio deseado de la tubería curva, en pies. Vacío (0) = automático.\nMáximo permitido por la geometría (tramos rectos adyacentes): {r} ft.":
        "Desired radius of the curved pipe, in feet. Empty (0) = automatic.\nMaximum allowed by the geometry (adjacent straight segments): {r} ft.",
    "⚠ Máximo permitido: {r} ft (limitado por los tramos rectos adyacentes). El valor guardado ({v} ft) se ajustó.":
        "⚠ Maximum allowed: {r} ft (limited by the adjacent straight segments). The saved value ({v} ft) was adjusted.",
    "Máximo permitido: {r} ft.":
        "Maximum allowed: {r} ft.",
    "(sin tubería detectada)":
        "(no pipe detected)",
    "Ya existe un elemento con código «{cod}». Elige otro.":
        "An element with code «{cod}» already exists. Choose another one.",
    "⚠ Alcanzaste el máximo permitido: {r} ft. No se puede subir más porque los tramos rectos adyacentes no dan espacio para una tangente mayor.":
        "⚠ You reached the maximum allowed: {r} ft. It cannot go higher because the adjacent straight segments leave no room for a longer tangent.",
    "Propiedades del centerline — selecciona uno de la lista":
        "Centerline properties — select one from the list",
    "Ya existe un centerline con código «{cod}». Elige otro.":
        "A centerline with code «{cod}» already exists. Choose another one.",
    "Falta un componente":
        "Missing component",
    "La georreferenciación necesita matplotlib, pyproj y scikit-image.\n\nInstálalos con:\n  {cmd}\n\nDetalle: {e}":
        "Georeferencing needs matplotlib, pyproj and scikit-image.\n\nInstall them with:\n  {cmd}\n\nDetails: {e}",
    "Bancoducto duplicado como «{nombre}».":
        "Duct bank duplicated as «{nombre}».",
    "sin nombre":
        "unnamed",
    "Duct banks: {n} → asignado a #{num} {capa}":
        "Duct banks: {n} → assigned to #{num} {capa}",
    "Duct banks: {n}":
        "Duct banks: {n}",
    "Duct bank «{nombre}» guardado → asignado a #{num} {capa}.":
        "Duct bank «{nombre}» saved → assigned to #{num} {capa}.",
    "Duct bank «{nombre}» guardado.":
        "Duct bank «{nombre}» saved.",

    # ── dialogs.py ──
    "Sin versión de Civil 3D":
        "No Civil 3D version",
    "Elige una versión de Civil 3D en el toolbar antes de instalar familias.":
        "Choose a Civil 3D version in the toolbar before installing families.",
    "Sin idioma seleccionado":
        "No language selected",
    "Elige un idioma en el toolbar antes de instalar familias.":
        "Choose a language in the toolbar before installing families.",
    "Instalar familia personalizada — Civil 3D {anio} / {idioma}":
        "Install custom family — Civil 3D {anio} / {idioma}",
    "<b>Elige la carpeta de UNA familia</b> — debe contener el <code>.xml</code>, el <code>.dwg</code> del Part Builder y el <code>.bmp</code> (miniatura).<br><br>Se instalará en el catálogo de <b>Civil 3D {anio} ({idioma})</b>. El script detecta automáticamente si es tubería o estructura, sus unidades y la forma, copia los archivos y registra la familia en el <code>.apc</code> (con backup).<br><br>Al terminar, ejecuta <b>PREPARAR_FAMILIAS</b> en Civil 3D — regenera el catálogo y te deja elegir qué familias añadir a la lista de piezas del dibujo.":
        "<b>Choose the folder of ONE family</b> — it must contain the <code>.xml</code>, the Part Builder <code>.dwg</code> and the <code>.bmp</code> (thumbnail).<br><br>It will be installed in the <b>Civil 3D {anio} ({idioma})</b> catalog. The script automatically detects whether it is a pipe or a structure, its units and shape, copies the files and registers the family in the <code>.apc</code> (with backup).<br><br>When done, run <b>PREPARAR_FAMILIAS</b> in Civil 3D — it regenerates the catalog and lets you choose which families to add to the drawing's parts list.",
    "Carpeta de la familia:":
        "Family folder:",
    "Elegir…":
        "Choose…",
    "<i>Elige una carpeta para ver qué se detecta.</i>":
        "<i>Choose a folder to see what is detected.</i>",
    "Instalar familia":
        "Install family",
    "<span style='color:#e06060;'>❌ No encontré ningún .xml con .dwg hermano en esta carpeta.</span>":
        "<span style='color:#e06060;'>❌ I found no .xml with a sibling .dwg in this folder.</span>",
    "Carpeta de familias (.xml + .dwg + .bmp por familia)":
        "Families folder (.xml + .dwg + .bmp per family)",
    "Error al instalar":
        "Installation error",
    "Familias instaladas":
        "Families installed",
    "Sin versión":
        "No version",
    "Elige una versión de Civil 3D en el toolbar antes de desinstalar familias.":
        "Choose a Civil 3D version in the toolbar before uninstalling families.",
    "Sin idioma":
        "No language",
    "Elige un idioma en el toolbar antes de desinstalar familias.":
        "Choose a language in the toolbar before uninstalling families.",
    "Sin familias personalizadas":
        "No custom families",
    "No se encontraron familias personalizadas instaladas en Civil 3D {anio}.":
        "No custom families installed in Civil 3D {anio} were found.",
    "Desinstalar familias — Civil 3D {anio} / {idioma}":
        "Uninstall families — Civil 3D {anio} / {idioma}",
    "<b>Familias personalizadas en Civil 3D {anio}</b><br>Marca las que deseas desinstalar:":
        "<b>Custom families in Civil 3D {anio}</b><br>Check the ones you want to uninstall:",
    "Desinstalar seleccionadas":
        "Uninstall selected",
    "Sin selección":
        "No selection",
    "Selecciona al menos una familia.":
        "Select at least one family.",
    "Confirmar desinstalación":
        "Confirm uninstall",
    "¿Desinstalar {n} familia(s)?\n\n{nombres}\n\nSe quitarán del catálogo de Civil 3D. Esta acción se puede revertir reinstalando las familias desde su carpeta original.":
        "Uninstall {n} family(ies)?\n\n{nombres}\n\nThey will be removed from the Civil 3D catalog. This can be reverted by reinstalling the families from their original folder.",
    "Errores":
        "Errors",
    "Se desinstalaron {ok} de {n} familias.\n\nErrores:\n{errores}":
        "{ok} of {n} families were uninstalled.\n\nErrors:\n{errores}",
    "Familias desinstaladas":
        "Families uninstalled",
    "Se desinstalaron {ok} familia(s) correctamente.\n\nEn Civil 3D ejecuta PREPARAR_FAMILIAS para actualizar la Parts List.":
        "{ok} family(ies) uninstalled successfully.\n\nIn Civil 3D run PREPARAR_FAMILIAS to update the Parts List.",
    "es":
        "es",
    "en":
        "en",

    # ── blank_canvas_dialog.py ──
    "Carta (Letter)":
        "Letter",
    "Oficio (Legal)":
        "Legal",
    "Tabloide (Ledger)":
        "Tabloid (Ledger)",
    "Nuevo lienzo":
        "New canvas",
    "Tamaño de hoja":
        "Sheet size",
    "Personalizado…":
        "Custom…",
    "Formato:":
        "Format:",
    "milímetros (mm)":
        "millimeters (mm)",
    "mm":
        "mm",
    "pulgadas (in)":
        "inches (in)",
    "in":
        "in",
    "Unidad:":
        "Unit:",
    "Personalizada…":
        "Custom…",
    "Escala:":
        "Scale:",
    "pies por pulgada":
        "feet per inch",
    "Valor:":
        "Value:",
    "Cubre:":
        "Covers:",
    "{w:,.0f} × {h:,.0f} pies reales":
        "{w:,.0f} × {h:,.0f} real feet",
    "Crear":
        "Create",

    # ── geo/georef_dialog.py ──
    "Clic izquierdo: punto de control (imán a la utilidad/centerline más cercana)\nRueda: zoom · Rueda presionada + arrastrar: desplazar (como en Civil3D)":
        "Left click: control point (snaps to the nearest utility/centerline)\nWheel: zoom · Wheel pressed + drag: pan (as in Civil 3D)",
    "zona ya georreferenciada":
        "area already georeferenced",
    "Georreferenciar plano":
        "Georeference plan",
    "✓ Este plano YA está georreferenciado (EPSG:{epsg}{rms}). Puedes recalcular con nuevos puntos o cerrar sin cambios.":
        "✓ This plan is ALREADY georeferenced (EPSG:{epsg}{rms}). You can recompute with new points or close without changes.",
    "Opacidad PDF:":
        "PDF opacity:",
    "Dirección o intersección… ej: Colfax Ave & Chandler Blvd":
        "Address or intersection… e.g.: Colfax Ave & Chandler Blvd",
    "Radio (ft):":
        "Radius (ft):",
    "Buscar y descargar":
        "Search and download",
    "Calles de LA (NavigateLA)  —  clic: punto de control (imán a la intersección)  |  rueda: zoom":
        "LA streets (NavigateLA)  —  click: control point (snaps to the intersection)  |  wheel: zoom",
    "1) Busca y descarga las calles de la zona · 2) clic en el plano (izquierda) · 3) clic en la calle correspondiente (derecha). Mínimo 3 pares — puedes marcar puntos A LO LARGO de toda la calle, no solo en las esquinas: más puntos bien repartidos mejoran el ajuste (RMSE).":
        "1) Search and download the area's streets · 2) click on the plan (left) · 3) click on the matching street (right). At least 3 pairs — you can mark points ALONG the whole street, not only at corners: more well-distributed points improve the fit (RMSE).",
    "RMSE (Root Mean Square Error / error cuadrático medio): el error PROMEDIO, en pies, entre cada punto de control y donde el ajuste calculado lo ubica.\n\nNo es el error de un punto — es el error de TODOS a la vez: si un punto quedó mal clickeado, el RMSE sube aunque los demás estén perfectos. Mientras más bajo, mejor (verde <3 ft, amarillo <8 ft, rojo ≥8 ft).":
        "RMSE (Root Mean Square Error): the AVERAGE error, in feet, between each control point and where the computed fit places it.\n\nIt is not the error of one point — it is the error of ALL of them at once: if one point was clicked badly, the RMSE goes up even if the others are perfect. The lower, the better (green <3 ft, yellow <8 ft, red ≥8 ft).",
    "Ajustar + RMSE":
        "Fit + RMSE",
    "Calcula la transformación (rotación + escala uniforme + traslación) que mejor hace coincidir todos los pares plano↔calle real, y muestra el RMSE. No deforma el plano: solo lo gira y escala parejo.":
        "Computes the transformation (rotation + uniform scale + translation) that best matches all the plan↔real street pairs, and shows the RMSE. It does not distort the plan: it only rotates and scales it uniformly.",
    "RMSE: —":
        "RMSE: —",
    "Eliminar sel.":
        "Delete sel.",
    "Limpiar todos":
        "Clear all",
    "Sistema de coordenadas (Huso) — código:":
        "Coordinate system (Zone) — code:",
    "ej: CA83VF  (código CS-MAP; vacío = no setear Huso)":
        "e.g.: CA83VF  (CS-MAP code; empty = do not set the Zone)",
    "Código nativo CS-MAP del sistema de coordenadas que quedará seteado en el\ndibujo de Civil 3D al importar la red. Debe corresponder al EPSG con que\ngeorreferenciaste (para EPSG:2229 → 'CA83VF'). Cópialo del diálogo nativo\nde Civil 3D (Configuración de dibujo → Unidades y huso) si no lo sabes.\nVacío = el dibujo no se setea (lo puedes poner luego a mano).":
        "Native CS-MAP code of the coordinate system that will be set in the\nCivil 3D drawing when the network is imported. It must match the EPSG you\ngeoreferenced with (for EPSG:2229 → 'CA83VF'). Copy it from Civil 3D's native\ndialog (Drawing Settings → Units and Zone) if you don't know it.\nEmpty = the drawing is not set (you can set it later by hand).",
    "Guardar georreferenciación":
        "Save georeference",
    "Cerrar sin guardar":
        "Close without saving",
    "Hiciste cambios en la georreferenciación que no se han guardado.\n\n¿Cerrar de todas formas y descartarlos?":
        "You made georeferencing changes that have not been saved.\n\nClose anyway and discard them?",
    "Falta dirección":
        "Missing address",
    "Escribe una dirección o intersección.":
        "Type an address or intersection.",
    "No se encontraron calles en esa zona. Prueba un radio mayor.":
        "No streets were found in that area. Try a larger radius.",
    "{tramos} tramos, {parcelas} parcelas, {esquinas} esquinas redondeadas — {zona}. Marca puntos de control — clic cerca de un cruce imanta al cruce exacto":
        "{tramos} street segments, {parcelas} parcels, {esquinas} rounded corners — {zona}. Mark control points — clicking near a crossing snaps to the exact crossing",
    "Punto del plano fijado. Ahora clic en la calle correspondiente (derecha).":
        "Plan point set. Now click on the matching street (right).",
    "Primero clic en el plano (izquierda).":
        "Click on the plan first (left).",
    "Primero descarga las calles de la zona.":
        "Download the area's streets first.",
    "Punto {n} agregado. Repite (mínimo 3) y pulsa «Ajustar».":
        "Point {n} added. Repeat (at least 3) and press «Fit».",
    "Punto pendiente cancelado (Ctrl+Z).":
        "Pending point cancelled (Ctrl+Z).",
    "Último punto/lote deshecho (Ctrl+Z).":
        "Last point/batch undone (Ctrl+Z).",
    "Faltan puntos":
        "Missing points",
    "Se necesitan al menos 3 puntos de control.":
        "At least 3 control points are needed.",
    "Ajuste":
        "Fit",
    "No se pudo ajustar la transformación.\n\n{e}":
        "The transformation could not be fitted.\n\n{e}",
    "⚠ Ajuste ESPEJADO":
        "⚠ MIRRORED fit",
    "Ajuste espejado":
        "Mirrored fit",
    "El ajuste salió espejado: el plano se guardaría volteado.\n\nCausa típica: los puntos de control están casi en línea recta. Usa 3–4 puntos que formen un triángulo amplio (en calles distintas o a ambos lados) y recalcula.":
        "The fit came out mirrored: the plan would be saved flipped.\n\nTypical cause: the control points are almost in a straight line. Use 3–4 points that form a wide triangle (on different streets or on both sides) and recompute.",
    "RMSE: {rms} ft  ({tipo}, {n} pts)":
        "RMSE: {rms} ft  ({tipo}, {n} pts)",
    "✓ Ajuste OK (RMSE {rms} ft). Pulsa «Guardar georreferenciación».":
        "✓ Fit OK (RMSE {rms} ft). Press «Save georeference».",
    "Falta ajustar":
        "Fit missing",
    "Primero pulsa «Ajustar + RMSE» para calcular la georreferenciación.":
        "First press «Fit + RMSE» to compute the georeference.",
    "La georreferenciación se aplicó, pero no se pudo guardar el proyecto.\n\n{e}":
        "The georeference was applied, but the project could not be saved.\n\n{e}",
    "Georreferenciación calculada, pero falta guardarla en disco (cancelaste «Guardar como…»). Pulsa «Guardar georreferenciación» de nuevo.":
        "Georeference computed, but it still has to be saved to disk (you cancelled «Save as…»). Press «Save georeference» again.",
    "Georreferenciación guardada":
        "Georeference saved",
    "✓ Guardado en el proyecto:\n{archivo}\n\nEPSG: {epsg}\nRMSE: {rms} ft":
        "✓ Saved in the project:\n{archivo}\n\nEPSG: {epsg}\nRMSE: {rms} ft",
    "{i}   plano({x},{y})  →  calle({X},{Y}) ft{etiqueta}":
        "{i}   plan({x},{y})  →  street({X},{Y}) ft{etiqueta}",

    # ── composite_dialog.py ──
    "Elige el PDF y la hoja, marca el área del plano que necesitas y tómala a la hoja compuesta. Acomoda las piezas arrastrándolas: el imán alinea los extremos de las líneas y los puentes (verde) los unen. Cada pieza conserva sus vectores, capas, textos y medidas.":
        "Choose the PDF and the sheet, mark the area of the plan you need and take it to the composite sheet. Arrange the pieces by dragging them: the magnet aligns the line ends and the bridges (green) join them. Each piece keeps its vectors, layers, texts and measurements.",
    "Rueda = zoom · botón central = desplazar · Supr quita la pieza seleccionada":
        "Wheel = zoom · middle button = pan · Del removes the selected piece",
    "1 · Origen":
        "1 · Source",
    "PDF":
        "PDF",
    "Agregar PDF…":
        "Add PDF…",
    "Agregar otro PDF":
        "Add another PDF",
    "Escala leída del texto de la hoja; corrígela si no es la del plano.":
        "Scale read from the sheet text; correct it if it is not the plan's scale.",
    "2 · Área a tomar":
        "2 · Area to take",
    "Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan.":
        "Drag a rectangle over the plan; corners and sides can be adjusted.",
    "Nueva pieza":
        "New piece",
    "Dejar de editar la pieza seleccionada y marcar un área nueva":
        "Stop editing the selected piece and mark a new area",
    "Imán a líneas":
        "Snap to lines",
    "Al arrastrar el rectángulo, sus lados saltan a las líneas generales de la hoja (match lines, marcos, bordes largos), que se resaltan en celeste":
        "When dragging the rectangle, its sides jump to the sheet's general lines (match lines, frames, long edges), highlighted in light blue",
    "Sin línea de borde":
        "No border line",
    "Recortar el área por dentro de la línea larga que corra pegada a cada lado (match line, marco de la vista), sea de la capa que sea, para que no aparezca en la hoja compuesta":
        "Crop the area inside the long line running next to each side (match line, view frame), whatever its layer, so it does not appear in the composite sheet",
    "3 · Hoja compuesta":
        "3 · Composite sheet",
    "Girar 90° antihorario":
        "Rotate 90° counterclockwise",
    "Girar 90° horario":
        "Rotate 90° clockwise",
    "Ángulo fino de la pieza (antihorario)":
        "Fine angle of the piece (counterclockwise)",
    "Escala de la hoja de origen de esta pieza":
        "Scale of this piece's source sheet",
    "Quitar la pieza seleccionada (Supr)":
        "Remove the selected piece (Del)",
    "Ajustar la vista a todas las piezas":
        "Fit the view to all pieces",
    "Al arrastrar, los extremos de las líneas se pegan (o se alinean) con los de la pieza vecina":
        "When dragging, line ends snap to (or align with) those of the neighboring piece",
    "Extremos":
        "Ends",
    "Mostrar los extremos de línea en el borde de cada pieza":
        "Show line ends on the edge of each piece",
    "Puentes":
        "Bridges",
    "Unir con un trazo vectorial (misma capa) cada extremo con el que tiene enfrente en la pieza vecina":
        "Join each end with the one facing it on the neighboring piece using a vector stroke (same layer)",
    "hueco máx.":
        "max. gap",
    "Separación máxima entre dos extremos para unirlos con un puente":
        "Maximum distance between two ends to join them with a bridge",
    "Escala única de la hoja compuesta; cada pieza se ajusta a ella":
        "Single scale of the composite sheet; each piece is adjusted to it",
    "{name}  ({n} hojas)":
        "{name}  ({n} sheets)",
    "{w:.0f} × {h:.0f} pt":
        "{w:.0f} × {h:.0f} pt",
    "Editando el área de la pieza {n} ({name}). Ajusta el rectángulo; la pieza se actualiza sola.":
        "Editing the area of piece {n} ({name}). Adjust the rectangle; the piece updates by itself.",
    "Agregar PDF":
        "Add PDF",
    "El PDF no tiene hojas.":
        "The PDF has no sheets.",
    "No se pudo abrir el PDF:\n\n{e}":
        "The PDF could not be opened:\n\n{e}",
    "{n} puentes":
        "{n} bridges",
    "{n} pieza(s) · hoja compuesta {w:.0f} × {h:.0f} pt · {s}":
        "{n} piece(s) · composite sheet {w:.0f} × {h:.0f} pt · {s}",

    # ── duct_bank_dialog.py ──
    "Abrir Duct Bank":
        "Open Duct Bank",
    "Duct Bank (*.dbjson);;JSON (*.json)":
        "Duct Bank (*.dbjson);;JSON (*.json)",
    "Guardar Duct Bank":
        "Save Duct Bank",
    "Duct Bank (*.dbjson)":
        "Duct Bank (*.dbjson)",

    # ── layer_dialog.py ──
    "Marca las capas que quieres ver. Las capas ocultas no se dibujan en el lienzo ni se usan en el reconocimiento. Una utilidad desmarcada apaga todas sus capas en la hoja.":
        "Check the layers you want to see. Hidden layers are not drawn on the canvas nor used in recognition. An unchecked utility turns off all its layers on the sheet.",

    # ── organized_layer_dialog.py ──
    "Principal":
        "Main",
    "Izquierda":
        "Left",
    "Derecha":
        "Right",
    "Capas de las hojas organizadas":
        "Arranged sheets layers",
    "Las hojas aparecen según la organización elegida. Marca las capas que quieres ver: una opción controla sus equivalentes en todos los PDF. La posición es aproximada hasta ajustar la unión de las hojas.":
        "Sheets appear according to the chosen arrangement. Check the layers you want to see: one option controls its equivalents in all PDFs. The position is approximate until the sheet join is adjusted.",
    "Delimitar plano…":
        "Delimit plan…",
    "Guardar selección de capas":
        "Save layer selection",
    "Hoja {i}":
        "Sheet {i}",
    "Haz clic en una hoja para delimitar su plano.":
        "Click a sheet to delimit its plan.",
    "Área delimitada":
        "Delimited area",
    "Hoja completa":
        "Full sheet",

    # ── organized_recognition_dialog.py ──
    "Cada hoja se reconoce con las capas seleccionadas para su PDF. La posición entre hojas es aproximada; aún no se han alineado ni unido los trazos.":
        "Each sheet is recognized with the layers selected for its PDF. The position between sheets is approximate; the strokes have not been aligned or joined yet.",
    "Hojas reconocidas":
        "Recognized sheets",
    "Volver a capas":
        "Back to layers",
    "Cerrar vista previa":
        "Close preview",
    "Sin cubrir: {n} (naranja) · Fuera de patrón: {m} (violeta)":
        "Uncovered: {n} (orange) · Off-pattern: {m} (purple)",

    # ── recognition_dialog.py ──
    "Tipo de PDF":
        "PDF type",
    "¿Qué tipo de PDF estás abriendo?":
        "What type of PDF are you opening?",
    "PDF bien ploteado: tiene capas vectoriales (OCG). PDF imagen: escaneo o raster sin capas útiles.":
        "Properly plotted PDF: it has vector layers (OCG). Image PDF: scan or raster without useful layers.",
    "PDF bien ploteado (capas)":
        "Properly plotted PDF (layers)",
    "PDF imagen / escaneo":
        "Image PDF / scan",
    "Seleccionar hoja":
        "Select sheet",
    "Este PDF tiene {n} hojas. Elige la hoja a reconocer:":
        "This PDF has {n} sheets. Choose the sheet to recognize:",
    "Usar esta hoja":
        "Use this sheet",
    "Vista previa del reconocimiento":
        "Recognition preview",
    "Continuar e importar al editor":
        "Continue and import into the editor",

    # ── sheet_crop_dialog.py ──
    "Delimitar plano · {name}":
        "Delimit plan · {name}",
    "Arrastra un rectángulo alrededor del plano. Ajusta sus esquinas o cada lado; el punto central mueve el área sin cambiar su forma. Flechas = 1 punto del PDF, Ctrl+flechas = 0,1 y Mayús+flechas = 10. Rueda = zoom; botón central = desplazar.":
        "Drag a rectangle around the plan. Adjust its corners or each side; the center point moves the area without changing its shape. Arrows = 1 PDF point, Ctrl+arrows = 0.1 and Shift+arrows = 10. Wheel = zoom; middle button = pan.",
    "Usar esta área":
        "Use this area",
    "Usar hoja completa":
        "Use full sheet",
    "Área marcada":
        "Marked area",
    "Marca el área del plano arrastrando sobre la hoja.":
        "Mark the plan area by dragging over the sheet.",

    # ── sheet_layout_dialog.py ──
    "Organizar hojas del plano":
        "Arrange plan sheets",
    "Haz clic en la posición que quieres llenar. Luego elige una hoja del PDF abierto; para las posiciones contiguas puedes cargar otro PDF. Las posiciones indican continuidad; el ajuste geométrico se realizará después.":
        "Click the position you want to fill. Then choose a sheet of the open PDF; for adjacent positions you can load another PDF. Positions indicate continuity; the geometric adjustment is done later.",
    "Elegir o cambiar hoja":
        "Choose or change sheet",
    "Rotar 90° a la izquierda":
        "Rotate 90° left",
    "Rotar 90° a la derecha":
        "Rotate 90° right",
    "Quitar hoja":
        "Remove sheet",
    "Continuar con esta organización":
        "Continue with this arrangement",
    "Sin hoja":
        "No sheet",
    "Elegir hoja":
        "Choose sheet",
    "Cambiar hoja":
        "Change sheet",
    "Elegir hoja para {position}":
        "Choose sheet for {position}",
    "Selecciona una hoja o carga otro PDF.":
        "Select a sheet or load another PDF.",
    "+ Cargar otro PDF…":
        "+ Load another PDF…",
    "Cargar PDF":
        "Load PDF",
    "El PDF no contiene hojas.":
        "The PDF contains no sheets.",

    # ── widgets.py ──
    "Plegar este panel para dar más sitio a los demás":
        "Collapse this panel to give the others more room",
    "Desplegar":
        "Expand",

    # ── app_window.py (mensajes armados en variables) ──
    "#{n} {capa}{tag} — {d}\" · {v} vértices":
        "#{n} {capa}{tag} — {d}\" · {v} vertices",
    "(a una de las dos le falta la cota — no se puede confirmar Δ)":
        "(one of the two is missing its elevation — Δ cannot be confirmed)",
    "(sin cotas en ninguna — no se puede confirmar Δ)":
        "(neither has elevations — Δ cannot be confirmed)",
    "Bancoducto «{nombre}» ({n} conducto(s))":
        "Duct bank «{nombre}» ({n} conduit(s))",
    "CONFLICTO — cruce con la misma cota (las tuberías chocan). Revisa la geometría o las cotas.":
        "CONFLICT — crossing at the same elevation (the pipes clash). Check the geometry or the elevations.",
    "Centerline #{n}":
        "Centerline #{n}",
    "Conexión vertical aprobada — al importar se dibuja una tubería vertical uniendo las dos cotas.":
        "Vertical connection approved — on import a vertical pipe is drawn joining both elevations.",
    "Dos tramos de «{capa}»":
        "Two segments of «{capa}»",
    "Este proyecto usa familias del catálogo que no están instaladas en Civil 3D {anio} ({idioma}):":
        "This project uses catalog families that are not installed in Civil 3D {anio} ({idioma}):",
    "Exportado (PDF + anotaciones){georef}:\n{archivo}\n\n{np} utilidades, {nl} leaders, {nt} textos, {nz} zonas borradas.":
        "Exported (PDF + annotations){georef}:\n{archivo}\n\n{np} utilities, {nl} leaders, {nt} texts, {nz} erased areas.",
    "Exportado (solo el PDF digitalizado){georef}:\n{archivo}":
        "Exported (digitized PDF only){georef}:\n{archivo}",
    "Leader #{n}":
        "Leader #{n}",
    "Sugerencia — cotas distintas, pasan una por encima de la otra. Click para conectarlas con una tubería vertical.":
        "Suggestion — different elevations, one passes over the other. Click to connect them with a vertical pipe.",
    "Texto #{n} «{txt}»":
        "Text #{n} «{txt}»",
    "Utilidad #{n} ({capa}, {v} vértices)":
        "Utility #{n} ({capa}, {v} vertices)",
    "Zona de borrado #{n}":
        "Erase area #{n}",
    "{n} aprobada(s)":
        "{n} approved",
    "{n} choque(s) entre redes distintas":
        "{n} clash(es) between different networks",
    "{n} conflicto(s)":
        "{n} conflict(s)",
    "{n} escalón(es) de cota":
        "{n} elevation step(s)",
    "{n} punto(s) con 5+ tuberías":
        "{n} point(s) with 5+ pipes",
    "{n} sugerencia(s)":
        "{n} suggestion(s)",
    "¿Quieres abrir el instalador de familias ahora? Puedes seguir trabajando con el proyecto igual — el aviso es solo para evitar sorpresas al exportar a DXF.":
        "Do you want to open the family installer now? You can keep working on the project anyway — this notice is only to avoid surprises when exporting to DXF.",
    "… y {n} más.":
        "… and {n} more.",

    # ── civil_catalog.py (mensajes armados en variables) ──
    "'{v}' no tiene 'US Imperial Pipes.apc' — Civil 3D no verá familias hasta que se regenere el .apc.":
        "'{v}' has no 'US Imperial Pipes.apc' — Civil 3D will not see families until the .apc is regenerated.",
    "'{v}' no tiene 'US Imperial Structures.apc' — idem structures.":
        "'{v}' has no 'US Imperial Structures.apc' — same for structures.",
    ".xml copiado pero no pude copiar el .dwg: {e}. La familia NO funcionará sin él.":
        ".xml copied but I could not copy the .dwg: {e}. The family will NOT work without it.",
    "Archivos borrados: {archivos}":
        "Deleted files: {archivos}",
    "Archivos copiados: {total_files}  ·  Tamaño: {mb:.1f} MB":
        "Files copied: {total_files}  ·  Size: {mb:.1f} MB",
    "Avisos:":
        "Warnings:",
    "Backup: {archivo}":
        "Backup: {archivo}",
    "Backups .apc:":
        ".apc backups:",
    "Carpeta '{subfolder}' conservada ({n} familia(s) restante(s))":
        "Folder '{subfolder}' kept ({n} family(ies) remaining)",
    "Carpeta '{subfolder}' eliminada (vacía)":
        "Folder '{subfolder}' deleted (empty)",
    "Combinación no soportada: kind={kind}, units={units}.":
        "Unsupported combination: kind={kind}, units={units}.",
    "El XML no declara ningún tamaño (no hay ColumnConstList con Items ni Column con Rows). Civil 3D no compilará ningún PartSize.":
        "The XML declares no size (no ColumnConstList with Items nor Column with Rows). Civil 3D will not compile any PartSize.",
    "El XML no parece una familia de Civil 3D válida (la etiqueta raíz no es 'LandPart').":
        "The XML does not look like a valid Civil 3D family (the root tag is not 'LandPart').",
    "El archivo XML de la familia no se puede abrir o está corrupto ({e}).":
        "The family XML file cannot be opened or is corrupt ({e}).",
    "El parámetro '{name}' no tiene ningún valor cargado. Sin valores, Civil 3D no generará ningún tamaño.":
        "Parameter '{name}' has no values loaded. Without values, Civil 3D will not generate any size.",
    "El parámetro '{name}' tiene el valor '{txt}' que no es un número.":
        "Parameter '{name}' has the value '{txt}', which is not a number.",
    "El parámetro '{name}' tiene un valor en blanco entre sus opciones.":
        "Parameter '{name}' has a blank value among its options.",
    "El rango '{name}' no tiene mínimo o máximo definido.":
        "Range '{name}' has no minimum or maximum defined.",
    "En '{source_folder}' no encontré ninguna subcarpeta 'US Imperial Pipes' ni 'US Imperial Structures'. El source debe ser la raíz del catálogo custom del modelador (con .apc adentro).":
        "In '{source_folder}' I found no 'US Imperial Pipes' or 'US Imperial Structures' subfolder. The source must be the root of the modeler's custom catalog (with the .apc inside).",
    "Estructura: {ruta}":
        "Structure: {ruta}",
    "Falta ColumnConst 'Catalog_PartDesc' — el plugin C# usará el nombre del archivo como Description.":
        "ColumnConst 'Catalog_PartDesc' is missing — the C# plugin will use the file name as Description.",
    "Falta el archivo .dwg de Part Builder ('{name}.dwg') al lado del .xml — la familia NO funcionará en Civil 3D sin él.":
        "The Part Builder .dwg file ('{name}.dwg') is missing next to the .xml — the family will NOT work in Civil 3D without it.",
    "Familias instaladas: {ok} / {total}":
        "Families installed: {ok} / {total}",
    "La carpeta origen no existe: {source_folder}":
        "The source folder does not exist: {source_folder}",
    "La familia no define el 'Nombre del tamaño' — Civil 3D no sabrá cómo llamar a cada tamaño y el plugin no podrá encontrar esta familia al importar.":
        "The family does not define the 'Size Name' — Civil 3D will not know how to name each size and the plugin will not be able to find this family on import.",
    "La fórmula '{fname}' usa la variable '${var}' que no está definida en la familia. Civil 3D no podrá calcular ese valor.":
        "Formula '{fname}' uses the variable '${var}', which is not defined in the family. Civil 3D will not be able to compute that value.",
    "La referencia al archivo .dwg lleva un prefijo de carpeta ('{val}'). El instalador lo corregirá al copiar.":
        "The reference to the .dwg file has a folder prefix ('{val}'). The installer will fix it when copying.",
    "Ninguna familia se instaló.":
        "No family was installed.",
    "No encontré el .apc: {apc}":
        "I could not find the .apc: {apc}",
    "No encontré la carpeta del idioma '{v}' para Civil 3D {year}.":
        "I could not find the language folder '{v}' for Civil 3D {year}.",
    "No encontré ningún .xml de familia (con .dwg hermano) en '{source_folder}'.":
        "I found no family .xml (with a sibling .dwg) in '{source_folder}'.",
    "No existe '{pipes_catalog_root}'. ¿Está instalado Civil 3D {year}?":
        "'{pipes_catalog_root}' does not exist. Is Civil 3D {year} installed?",
    "No existe el subcatálogo: {catalog_dir}":
        "The subcatalog does not exist: {catalog_dir}",
    "No hay versión de Civil 3D seleccionada en la UI.":
        "No Civil 3D version is selected in the UI.",
    "No pude copiar el .xml: {e}":
        "I could not copy the .xml: {e}",
    "No pude copiar la carpeta '{folder_name}' al subcatálogo '{catalog_dir_name}': {e}. Ejecuta la app como Administrador.":
        "I could not copy the folder '{folder_name}' to the subcatalog '{catalog_dir_name}': {e}. Run the app as Administrator.",
    "No pude crear el destino '{dest_folder}': {e}":
        "I could not create the destination '{dest_folder}': {e}",
    "No pude crear la carpeta destino: {e}":
        "I could not create the destination folder: {e}",
    "No pude detectar si es tubería o estructura (revisa que el XML tenga ColumnConstList con SID/PID/etc).":
        "I could not detect whether it is a pipe or a structure (check that the XML has ColumnConstList with SID/PID/etc).",
    "No pude detectar tipo/unidades/shape (kind={kind}, units={units}, shape={shape}).":
        "I could not detect type/units/shape (kind={kind}, units={units}, shape={shape}).",
    "No pude hacer backup del .apc: {e}":
        "I could not back up the .apc: {e}",
    "No pude hacer backup del .xml existente: {e}":
        "I could not back up the existing .xml: {e}",
    "No pude registrar en el .apc: {e}":
        "I could not register it in the .apc: {e}",
    "No pude resolver la carpeta destino del catálogo Civil 3D.":
        "I could not resolve the Civil 3D catalog destination folder.",
    "No se encontró Civil 3D {year}.":
        "Civil 3D {year} was not found.",
    "No se encontró catálogo {kind} para {year}.":
        "No {kind} catalog was found for {year}.",
    "No se pudo guardar: {e}":
        "Could not save: {e}",
    "No se pudo hacer backup: {e}":
        "Could not make a backup: {e}",
    "Otro archivo XML en esta carpeta usa el mismo nombre interno '{pn}'. Civil 3D solo cargará uno de ellos y descartará el otro. Cambia el nombre interno para diferenciarlos.":
        "Another XML file in this folder uses the same internal name '{pn}'. Civil 3D will load only one of them and discard the other. Change the internal name to tell them apart.",
    "Quitado de {apc_name}":
        "Removed from {apc_name}",
    "Sin miniatura .bmp — el usuario no verá thumbnail al elegir la familia.":
        "No .bmp thumbnail — the user will not see a thumbnail when choosing the family.",
    "Sin permiso de escritura en {path}. Ejecuta la app como administrador y reintenta.":
        "No write permission on {path}. Run the app as administrator and try again.",
    "Tubería:    {ruta}":
        "Pipe:       {ruta}",
    "XML corrupto: {e}":
        "Corrupt XML: {e}",
    "XML no encontrado":
        "XML not found",
    "fórmula":
        "formula",
    "parámetro":
        "parameter",
    "reemplazada en el .apc":
        "replaced in the .apc",
    "registrada en el .apc":
        "registered in the .apc",
    "valor inválido":
        "invalid value",
    "ya existía":
        "already existed",
    "✓ Catálogo copiado a: {dest_folder}":
        "✓ Catalog copied to: {dest_folder}",

    # ── dialogs.py (mensajes armados en variables) ──
    "(sin .bmp)":
        "(no .bmp)",
    "AHORA en Civil 3D:\n  · Ejecuta el comando  PREPARAR_FAMILIAS\n    (regenera el catálogo y te deja elegir qué familias\n    añadir a la Parts List del dibujo actual).":
        "NOW in Civil 3D:\n  · Run the command  PREPARAR_FAMILIAS\n    (it regenerates the catalog and lets you choose which families\n    to add to the Parts List of the current drawing).",
    "Destinos:":
        "Destinations:",
    "Se copiará la carpeta al subcatálogo correspondiente y cada .xml se registrará como familia independiente en el .apc.":
        "The folder will be copied to the matching subcatalog and each .xml will be registered as an independent family in the .apc.",
    "tipo {tipo} · unidades {unidades} · shape {shape}":
        "type {tipo} · units {unidades} · shape {shape}",
    "{n} familia(s) detectadas en la carpeta:":
        "{n} family(ies) detected in the folder:",
    "{n} familia(s) → {destino}":
        "{n} family(ies) → {destino}",

    # ── duct_bank.py (mensajes armados en variables) ──
    "Conducto {i}: diámetro debe ser > 0.":
        "Conduit {i}: diameter must be > 0.",
    "Conducto {i}: sale de la envolvente.":
        "Conduit {i}: goes outside the envelope.",
    "Conducto {i}: viola distancia mínima al borde ({d:g}\").":
        "Conduit {i}: violates the minimum edge clearance ({d:g}\").",
    "Conductos {i} y {j} se solapan.":
        "Conduits {i} and {j} overlap.",
    "Conductos {i} y {j}: separación menor a {d:g}\" entre bordes.":
        "Conduits {i} and {j}: spacing less than {d:g}\" between edges.",
    "Demasiados conductos ({n} > {max}).":
        "Too many conduits ({n} > {max}).",
    "La envolvente debe tener ancho y alto positivos.":
        "The envelope must have a positive width and height.",

    # ── duct_bank_dialog.py (mensajes armados en variables) ──
    "(+{n} más)":
        "(+{n} more)",
    "Independientes. Click para vincularlos.":
        "Independent. Click to link them.",
    "Vinculados (cambiar uno cambia los 4). Click para desvincular.":
        "Linked (changing one changes all 4). Click to unlink.",

    # ── geo/georef_dialog.py (mensajes armados en variables) ──
    "Buscando dirección y descargando calles/parcelas…":
        "Searching address and downloading streets/parcels…",
    "Cargando la zona de la georreferenciación existente…":
        "Loading the area of the existing georeference…",

    # ── recognition.py (mensajes armados en variables) ──
    "Bóvedas detectadas: {n} (ya son vértices de las líneas).":
        "Vaults detected: {n} (they are already line vertices).",
    "Bóvedas sin línea cercana: {n}.":
        "Vaults with no nearby line: {n}.",
    "Capa «-A» sin el patrón de marcadores «/» a lo largo de la línea: {n} — NO se marcan como abandonadas.":
        "«-A» layer without the «/» marker pattern along the line: {n} — NOT marked as abandoned.",
    "Cobertura de guiones: {pct:.1f}% ({n} sin cubrir, en naranja).":
        "Dash coverage: {pct:.1f}% ({n} uncovered, in orange).",
    "Cobertura de guiones: {pct:.1f}%.":
        "Dash coverage: {pct:.1f}%.",
    "Ninguna capa OCG coincidió con los roles / tokens de reconocimiento.":
        "No OCG layer matched the recognition roles / tokens.",
    "No se encontraron líneas eléctricas subterráneas en esta hoja.":
        "No underground electrical lines were found on this sheet.",
    "Patrón de marcadores «/» en una capa ACTIVA: {n} línea(s) — se importan activas (manda la capa); revisar.":
        "«/» marker pattern on an ACTIVE layer: {n} line(s) — imported as active (the layer rules); review.",
    "Rutas: {n} (unen {tramos} tramos de la misma capa).":
        "Routes: {n} (joining {tramos} segments of the same layer).",
    "Se omitieron {n} trazos de marcador/linetype (letras, barras); solo se dibuja la centerline.":
        "{n} marker/linetype strokes (letters, bars) were skipped; only the centerline is drawn.",
    "Trazos continuos fuera de patrón (leaders/flechas): {n} — no se importan.":
        "Off-pattern continuous strokes (leaders/arrows): {n} — not imported.",

    # ── app_window.py (unión de la misma utilidad en Civil 3D) ──
    "un codo sólido":
        "a solid elbow",
    "una Tee sólida":
        "a solid Tee",
    "una Wye sólida":
        "a solid Wye",
    "una cruz sólida":
        "a solid cross",
    "Unión en Civil 3D":
        "Joint in Civil 3D",
    "Se unen aquí a {z:.2f} ft.\n\nEn Civil 3D: {accesorio} en la red «{red}».":
        "They join here at {z:.2f} ft.\n\nIn Civil 3D: {accesorio} in network «{red}».",
    "Tienen nombres de red distintos («{a}» / «{b}»): las dos quedan en «{red}».":
        "They have different network names («{a}» / «{b}»): both go into «{red}».",

    # ── app_window.py (tramo corto entre codos) ──
    "{n} tramo(s) muy corto(s) entre codos":
        "{n} segment(s) too short between elbows",
    "Tramo muy corto entre codos":
        "Segment too short between elbows",
    "El tramo T{t} mide {largo:.2f} ft: es muy corto para dos codos (mínimo {minimo:.2f} ft).\n\nEn Civil 3D se reemplazará por un solo codo.":
        "Segment T{t} is {largo:.2f} ft long: too short for two elbows (minimum {minimo:.2f} ft).\n\nIn Civil 3D it will be replaced by a single elbow.",

    # ── app_window.py (conexión vertical con pendiente) ──
    "{n} conexión(es) vertical(es) con pendiente":
        "{n} sloped vertical connection(s)",
    "Conexión vertical con pendiente":
        "Sloped vertical connection",
    "Desnivel de {dz:.2f} ft: es muy poco para bajar con dos codos (mínimo {minimo:.2f} ft).\n\nEn Civil 3D se pondrá una Wye con el ramal inclinado y la tubería «{capa}» se modificará para que llegue con pendiente.":
        "Elevation difference of {dz:.2f} ft: too little to drop with two elbows (minimum {minimo:.2f} ft).\n\nIn Civil 3D a Wye with a sloped branch will be placed and pipe «{capa}» will be modified so it arrives with a slope.",

    # ── manual_dialog.py ──
    "Anterior":
        "Previous",
    "Siguiente":
        "Next",
    "Letra más pequeña":
        "Smaller text",
    "Letra más grande":
        "Larger text",
    "Tamaño de letra:":
        "Text size:",
    "Capítulo {n} de {total}":
        "Chapter {n} of {total}",

    # ── app_window.py (listas del panel derecho) ──
    "red: {red}":
        "network: {red}",
    "{n} vért.":
        "{n} vert.",
    "{n}. Leader {orientacion}":
        "{n}. {orientacion} leader",

    # ── Datos extendidos (xdata_dialog, rama dev_santos_v2) ──
    "Ver datos extendidos":
        "View extended data",
    "Datos extendidos":
        "Extended data",
    "Campo":
        "Field",
    "Valor":
        "Value",
    "Agregar campo":
        "Add field",
    "Quitar campo":
        "Remove field",
    "Copiar todo":
        "Copy all",
    "Información de referencia que no forma parte de las propiedades de la red. Los campos con 🔒 vienen del PDF y no se editan; los tuyos sí.":
        "Reference information that is not part of the network properties. Fields marked 🔒 come from the PDF and are read-only; yours can be edited.",
    "Este elemento no viene del reconocimiento del PDF: no tiene datos automáticos.":
        "This item was not recognized from the PDF: it has no automatic data.",
    "Selecciona una utilidad o una estructura para ver sus datos extendidos.":
        "Select a utility or a structure to view its extended data.",
    "Hoja compuesta":
        "Composed sheet",

    # ── app_window.py (rama dev_santos_v2) ──
    "({a} sin línea, importadas como cajas sueltas.)":
        "({a} with no line, imported as standalone boxes.)",
    "Ajustar capas":
        "Adjust layers",
    "Capa del PDF de la que salió (disciplina, sistema, ubicación, estado) y tus propios campos. Se guardan en el proyecto y van al DXF.":
        "PDF layer it came from (discipline, system, location, status) and your own fields. They are saved in the project and go into the DXF.",
    "Detectado plano escaneado y vectorizado ({n} trazos calcados, sin texto ni capas) — continúa con el dibujo manual.":
        "Scanned and vectorized plan detected ({n} traced strokes, no text or layers) — continue with manual drawing.",
    "Estructura #{n}":
        "Structure #{n}",
    "Estructuras con medidas: {g}.":
        "Structures with measurements: {g}.",
    "Estructuras: {s} en líneas, {k} sin pipe cercana.":
        "Structures: {s} on lines, {k} with no nearby pipe.",
    "Importadas estructuras reconocidas.":
        "Recognized structures imported.",
    "Importadas: {items}.":
        "Imported: {items}.",
    "No hay tramos reconocidos para importar.":
        "There are no recognized segments to import.",
    "Reconociendo {u} en las hojas organizadas…":
        "Recognizing {u} on the organized sheets…",
    "Reconociendo {u}…":
        "Recognizing {u}…",
    "Utilidad #{n}":
        "Utility #{n}",
    "{n} rutas ({m} tramos) de {u}":
        "{n} routes ({m} segments) of {u}",
    "¿Qué utilidad quieres ajustar?":
        "Which utility do you want to adjust?",

    # ── composite_dialog.py (rama dev_santos_v2) ──
    "Esta hoja no interactúa con las capas: sus vectores no están en ninguna capa del PDF (hoja aplanada). Apagar capas no la cambia y el reconocimiento por capas no encontrará utilidades en ella.":
        "This sheet does not interact with layers: its vectors are not on any PDF layer (flattened sheet). Turning layers off does not change it and layer-based recognition will not find utilities on it.",
    "Hoja {n} sin capas: sus vectores no están en ninguna capa del PDF. Apagar capas no la cambia y el reconocimiento de utilidades por capa no encontrará nada aquí.":
        "Sheet {n} has no layers: its vectors are not on any PDF layer. Turning layers off does not change it and layer-based utility recognition will not find anything here.",
    "Hoja {n} · sin capas":
        "Sheet {n} · no layers",
    "✔ Área tomada como pieza {n} ({label}). Ya está en la hoja compuesta ({total} pieza(s)).":
        "✔ Area taken as piece {n} ({label}). It is already on the composite sheet ({total} piece(s)).",

    # ── layer_dialog.py (rama dev_santos_v2) ──
    "Utilidades a reconocer:":
        "Utilities to recognize:",

    # ── organized_recognition_dialog.py (rama dev_santos_v2) ──
    "Capas de {u} usadas en la hoja":
        "{u} layers used on the sheet",
    "Estructuras":
        "Structures",
    "No se encontraron capas reconocibles de esta utilidad.":
        "No recognizable layers were found for this utility.",
    "Vista previa del reconocimiento de {u} · hojas organizadas":
        "{u} recognition preview · organized sheets",
    "{s} hojas · {n} tramos · {v} estructuras":
        "{s} sheets · {n} segments · {v} structures",
    "{u} · hojas organizadas":
        "{u} · organized sheets",
    "{u}: {n} tramos · {v} estructuras · cobertura {c:.1f}%":
        "{u}: {n} segments · {v} structures · coverage {c:.1f}%",

    # ── recognition.py (rama dev_santos_v2) ──
    "({n} aproximado(s), a trazos: la curva del plano no es un arco tangente exacto; desvío máx. {dev:.1f} pt)":
        "({n} approximate, dashed: the plan's curve is not an exact tangent arc; max. deviation {dev:.1f} pt)",
    "Codos como esquina + radio: {n}":
        "Bends as corner + radius: {n}",
    "Curvas que quedan como polilínea: {n} tramo(s) — curva compuesta (radio variable) o sin recta tangente a un lado; no se inventa un arco que no está en el plano.":
        "Curves left as polylines: {n} segment(s) — compound curve (variable radius) or no tangent line on one side; no arc that is not on the plan is made up.",
    "Esta hoja no tiene capas: sus vectores no están en ninguna capa del PDF (hoja aplanada), así que el reconocimiento por capas no puede encontrar utilidades en ella.":
        "This sheet has no layers: its vectors are not on any PDF layer (flattened sheet), so layer-based recognition cannot find utilities on it.",
    "Existentes A ABANDONAR (capa «-D», marcadores «//» de la leyenda): {n} línea(s) — hoy se importan activas; revisar.":
        "Existing TO BE ABANDONED («-D» layer, «//» markers from the legend): {n} line(s) — imported as active for now; review.",
    "No se encontraron líneas de agua en esta hoja.":
        "No water lines were found on this sheet.",
    "No se encontraron líneas de alcantarillado en esta hoja.":
        "No sewer lines were found on this sheet.",
    "No se encontraron líneas de gas en esta hoja.":
        "No gas lines were found on this sheet.",
    "No se encontraron líneas de telecomunicaciones en esta hoja.":
        "No telecom lines were found on this sheet.",
    "No se encontraron líneas de drenaje en esta hoja.":
        "No storm drain lines were found on this sheet.",
    "No se encontraron líneas de {u} en esta hoja.":
        "No {u} lines were found on this sheet.",
    "Patrón «//» en una capa que no es «-A»: {n} línea(s) — se importan ABANDONADAS (el «//» manda).":
        "«//» pattern on a layer that is not «-A»: {n} line(s) — imported as ABANDONED (the «//» rules).",
    "Se excluyeron {n} trazo(s) dentro de una vista de PERFIL (grilla de estación/elevación): esa vista no es planta y no se reconoce.":
        "{n} stroke(s) inside a PROFILE view (station/elevation grid) were excluded: that view is not a plan and is not recognized.",
    "Utilidades abandonadas (capa «-A» + patrón «/», o patrón «//»): {n} — se importan marcadas (AB).":
        "Abandoned utilities («-A» layer + «/» pattern, or «//» pattern): {n} — imported marked (AB).",

    # ── recognition_dialog.py (rama dev_santos_v2) ──
    "Ajustar capas de {u}":
        "Adjust {u} layers",
    "Al continuar, estas líneas se importan al editor como {u} (igual que el dibujo manual, con sus puntos de quiebre). Las estructuras se insertan como nodos de la red.":
        "On continue, these lines are imported into the editor as {u} (just like manual drawing, with their break points). Structures are inserted as network nodes.",
    "Asigna al menos una capa como «Líneas».":
        "Assign at least one layer as «Lines».",
    "Buzones / estructuras":
        "Manholes / structures",
    "Cobertura":
        "Coverage",
    "Arrastra para cambiar el ancho":
        "Drag to resize",
    "{n} sin cubrir":
        "{n} uncovered",
    "{n} fuera de patrón":
        "{n} off-pattern",
    "Debe haber al menos una capa en «Líneas» para continuar.":
        "There must be at least one layer in «Lines» to continue.",
    "Escala {s:.6f} pie/pt":
        "Scale {s:.6f} ft/pt",
    "Guiones del plano cubiertos por las líneas reconocidas. En el dibujo: naranja = sin cubrir, violeta = trazos fuera de patrón (leaders/flechas).":
        "Plan dashes covered by the recognized lines. In the drawing: orange = uncovered, purple = off-pattern strokes (leaders/arrows).",

    # ── recognition_summary_view.py (rama dev_santos_v2) ──
    "Clic: ir al lugar en la hoja (cada clic, el siguiente).":
        "Click: go to the spot on the sheet (each click, the next one).",
    "Detalles ({n})":
        "Details ({n})",
    "Nada que revisar":
        "Nothing to review",
    "Revisar ({n})":
        "Review ({n})",
    "{u}: {n} tramos — {a} activos, {b} abandonados (AB)\n{c} codos · {v} estructuras · cobertura {k:.1f} %":
        "{u}: {n} segments — {a} active, {b} abandoned (AB)\n{c} bends · {v} structures · coverage {k:.1f} %",

    # ── app_window.py (codo de retorno) ──
    "{n} codo(s) de retorno":
        "{n} return bend(s)",
    "Codo de retorno":
        "Return bend",
    "Giro de {giro:.0f}° muy cerrado: el codo necesita {necesita:.2f} ft de tubería y el tramo T{t} solo tiene {largo:.2f} ft.\n\nEn Civil 3D se pondrá un codo de retorno (curva en U) en el vértice y el tramo T{t} se correrá {lateral:.2f} ft hacia el costado para no montarse sobre el otro tubo.":
        "Turn of {giro:.0f}° too tight: the elbow needs {necesita:.2f} ft of pipe and segment T{t} only has {largo:.2f} ft.\n\nIn Civil 3D a return bend (U curve) will be placed at the vertex and segment T{t} will be shifted {lateral:.2f} ft to the side so it does not ride on top of the other pipe.",

    # ── app_window.py (codo con reducción) ──
    "un codo sólido de {d1:g}\" con reducción {d1:g}×{d2:g}\"":
        "a solid {d1:g}\" elbow with a {d1:g}×{d2:g}\" reducer",

    # ── app_window.py (unión con pendiente, sin espacio para vertical) ──
    "No hay espacio para una tubería vertical: la diferencia de altura es de {dz:.2f} ft y hacen falta al menos {minimo:.2f} ft.":
        "There is no room for a vertical pipe: the height difference is {dz:.2f} ft and at least {minimo:.2f} ft are needed.",
    "se unirán con un codo":
        "they will be joined with an elbow",
    "se unirán en línea recta":
        "they will be joined in a straight line",
    "En Civil 3D: las dos tuberías miden lo mismo, así que las dos tendrán una pendiente hasta un punto medio ({z:.2f} ft) y {union}.":
        "In Civil 3D: both pipes are the same length, so both will get a slope to a midpoint ({z:.2f} ft) and {union}.",
    "En Civil 3D: la tubería más larga («{nombre}», tramo T{t}) tendrá una pendiente para llegar a la más corta y {union}.":
        "In Civil 3D: the longer pipe («{nombre}», segment T{t}) will get a slope to reach the shorter one and {union}.",
    "Sin espacio para tubería vertical":
        "No room for a vertical pipe",
    "{n} unión(es) con pendiente":
        "{n} sloped joint(s)",

    # ── app_window.py (unión recta extremo con extremo) ──
    "una reducción {d1:g}×{d2:g}\"":
        "a {d1:g}×{d2:g}\" reducer",
}
