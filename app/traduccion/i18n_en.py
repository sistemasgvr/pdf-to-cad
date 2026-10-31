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
    "Zoom sincronizado con la vista · clic o arrastre: navegar · doble clic: ver todas las hojas": "Zoom synchronized with view · click or drag: navigate · double click: show all sheets",
    "Largo": "Length",
    "Ancho": "Width",
    "Bloquear regla": "Lock ruler",
    "Dejar la regla fija y permitir mover las hojas por debajo": "Keep the ruler fixed and allow sheets to move underneath",
    "Transportador": "Protractor",
    "Indica la escala real del plano escaneado; las medidas de la regla y del editor dependen de ella.": "Enter the scanned plan's actual scale; ruler and editor measurements depend on it.",
    "Componer PDF imagen/escaneo…": "Compose image/scanned PDF…",
    "Importar hoja al editor": "Import sheet into editor",
    "Arrastra un área y mueve cada esquina para seguir el borde inclinado del plano.": "Drag an area and move each corner to follow the slanted plan border.",
    "Regla": "Ruler",
    "Enderezar": "Straighten",
    "Ajusta las cuatro esquinas; la pieza seleccionada se actualiza sola.": "Adjust the four corners; the selected piece updates automatically.",
    "Esquinas libres": "Free corners",
    "Mover cada esquina del área por separado para seguir un borde inclinado o un área que no es rectangular (los lados se mueven paralelos). Apagada: rectángulo; «Sin línea de borde» solo recorta áreas rectangulares.":
        "Move each corner of the area separately to follow a slanted border or a non-rectangular area (sides move parallel). Off: rectangle; “No border line” only trims rectangular areas.",
    "Hoja compuesta importada al editor. Dibuja las utilidades a mano.": "Composed sheet imported into the editor. Draw utilities manually.",
    "Girar a 0°": "Rotate to 0°",
    "{d:.2f} ft · {a:.2f}°": "{d:.2f} ft · {a:.2f}°",
    "Regla graduada en pies sobre la hoja. Su borde inferior es la guía para alinear; el punto verde del extremo la gira (imán a 0° y 90°).": "Ruler graduated in feet over the sheet. Its bottom edge is the alignment guide; the green dot at its end rotates it (snaps to 0° and 90°).",
    "Girar 90°": "Rotate 90°",
    "Traer a la vista": "Bring into view",
    "Grados sobre la pieza elegida. Arrastra el punto verde para girarla: se imanta a 0°/90°; Ctrl = ajuste fino; Shift = pasos de 15°; doble clic = volver a 0°.": "Degrees over the selected piece. Drag the green dot to rotate it: snaps to 0°/90°; Ctrl = fine adjustment; Shift = 15° steps; double-click = back to 0°.",
    "Medir": "Measure",
    "Clic en dos puntos: distancia en pies y rumbo. Shift = horizontal/vertical. Con los dos puntos en una pieza puedes calibrar la escala de su hoja.": "Click two points: distance in feet and bearing. Shift = horizontal/vertical. With both points on one piece you can calibrate its sheet's scale.",
    "Clic en dos puntos de una línea que debería ir horizontal o vertical: la pieza gira hasta dejarla derecha.": "Click two points on a line that should be horizontal or vertical: the piece rotates to straighten it.",
    "Fundir bordes": "Blend edges",
    "Donde dos piezas se superponen se ve la tinta de ambas: el papel de una no tapa las líneas de la otra. Superpón un poco las piezas y la unión no deja corte ni franja blanca. También se aplica al PDF que pasa al editor.": "Where two pieces overlap, the ink of both shows: one piece's paper does not hide the other's lines. Overlap the pieces slightly and the join leaves no cut or white strip. Also applied to the PDF sent to the editor.",
    "Calibrar escala…": "Calibrate scale…",
    "Escribe cuánto mide en realidad lo que mediste: la escala de esa hoja se corrige con esa distancia.": "Type the real length of what you measured: that sheet's scale is corrected from that distance.",
    "Medida: {m}": "Measured: {m}",
    "Medir: clic en dos puntos · Shift = horizontal/vertical · Esc = salir": "Measure: click two points · Shift = horizontal/vertical · Esc = exit",
    "Enderezar: clic en dos puntos de una línea que debe quedar horizontal o vertical": "Straighten: click two points on a line that should be horizontal or vertical",
    "Transportador: arrastra el punto verde · imán a 0°/90° · Ctrl = fino · Shift = 15° · doble clic = 0°": "Protractor: drag the green dot · snaps to 0°/90° · Ctrl = fine · Shift = 15° · double-click = 0°",
    "Transportador: elige una pieza para ver sus grados": "Protractor: select a piece to see its degrees",
    "Flechas = mover · + / − = girar 0.1° · Ctrl = ajuste fino · Shift = paso grande": "Arrows = move · + / − = rotate 0.1° · Ctrl = fine adjustment · Shift = big step",
    "Regla: arrástrala hasta una línea; su borde inferior es la guía · ▾ Bloquear para mover las hojas por debajo": "Ruler: drag it onto a line; its bottom edge is the guide · ▾ Lock to move sheets underneath",
    "✔ Pieza {n} enderezada: {a:+.2f}°": "✔ Piece {n} straightened: {a:+.2f}°",
    "Calibrar escala": "Calibrate scale",
    "Medida en el plano: {m:.2f} ft. ¿Cuánto mide en realidad (pies)?": "Measured on the plan: {m:.2f} ft. What is the real length (feet)?",
    "✔ Escala de la hoja corregida: {s}": "✔ Sheet scale corrected: {s}",
    "Fundir bordes activado: superpón un poco las piezas en la unión.": "Blend edges on: overlap the pieces slightly at the join.",
    "Fundir bordes desactivado: cada pieza tapa a la de abajo.": "Blend edges off: each piece covers the one below.",
    "Fundir bordes activado: donde dos piezas se superponen se ve la tinta de las dos.": "Blend edges on: where two pieces overlap, the ink of both shows.",
    "Donde dos piezas se superponen se ve la tinta de ambas: lo blanco de una no tapa las líneas de la otra. Dentro de cada hoja no cambia nada y, borde con borde, el PDF queda igual. También se aplica al PDF que pasa al editor.": "Where two pieces overlap, the ink of both shows: the white of one does not hide the other's lines. Nothing changes inside each sheet and, edge to edge, the PDF stays the same. Also applied to the PDF sent to the editor.",
    # ── Menús principales ──────────────────────────────────────────────
    "Editar": "Edit",
    "Herramientas": "Tools",
    "Ayuda": "Help",
    "Nuevo": "New",
    "Cerrar proyecto": "Close project",
    "Opciones…": "Options…",
    "Opciones": "Options",
    "Reconocer":
        "Recognize",
    "Marcar o desmarcar todas las utilidades que tiene la hoja":
        "Check or uncheck all the utilities on this sheet",
    "Marca al menos una utilidad para reconocer.":
        "Check at least one utility to recognize.",
    "Sus capas están ocultas en «Capas del plano»: no se reconocería nada.":
        "Its layers are hidden in «Plan layers»: nothing would be recognized.",
    "{u}: sus capas están ocultas, no se reconocería nada.":
        "{u}: its layers are hidden, nothing would be recognized.",
    "{u}: sus capas están ocultas, no se reconocería nada de ellas.":
        "{u}: their layers are hidden, nothing would be recognized from them.",
    "Mostrar sus capas":
        "Show its layers",
    "No reconocerla":
        "Don't recognize it",
    "No reconocerlas":
        "Don't recognize them",
    "Es UNA sola capa del PDF: también está en {u}. Ocultarla oculta sus líneas de todas las utilidades; "
    "para ver solo las de una, márcala en la «Leyenda».":
        "It is ONE single PDF layer: it is also in {u}. Hiding it hides its lines of every utility; "
        "to see only one utility's lines, check it in the «Legend».",
    "Muestra en la leyenda del PDF:":
        "Sample in the PDF legend:",
    "Capas del plano":
        "Plan layers",
    "Esta hoja no tiene capas de {u}":
        "This sheet has no {u} layers",
    "Su nombre dice {n}, pero las letras de su línea («{c}») dicen {u}: se reconoce como {u}.":
        "Its name says {n}, but the letters on its line («{c}») say {u}: it is recognized as {u}.",
    "Capa con líneas de varias utilidades ({u}). Cada línea se reconoce por sus letras.":
        "Layer with lines of several utilities ({u}). Each line is recognized by its letters.",
    "Su nombre no es de ninguna utilidad, pero las letras de su línea («{c}») dicen {u}: se reconoce como {u}.":
        "Its name is not a utility's, but the letters on its line («{c}») say {u}: it is recognized as {u}.",
    # ── layer_info_panel.py / layer_dialog_info.py (panel «Leyenda» de «Capas de la hoja») ──
    "Leyenda":
        "Legend",
    "Por las letras de su línea ({n})":
        "By the letters on their line ({n})",
    "Su nombre no dice la utilidad; las letras de su línea sí. Desmarca las que no quieras usar.":
        "Their name does not say the utility; the letters on their line do. Uncheck the ones you do not want to use.",
    "Usar: reconocer esta capa por las letras de su línea":
        "Use: recognize this layer by the letters on its line",
    "Clic: ver sus líneas en la hoja (otro clic, ver todo).":
        "Click: see its lines on the sheet (click again to see everything).",
    "su nombre dice {u}":
        "its name says {u}",
    "línea por línea":
        "line by line",
    "su nombre no dice la utilidad":
        "its name does not say the utility",
    "Leyenda: {d}":
        "Legend: {d}",
    "Buscando la leyenda en el PDF…":
        "Looking for the legend in the PDF…",
    "Leyenda de esta hoja":
        "This sheet's legend",
    "Cada utilidad con los tipos de línea que hay en esta hoja. Marca una o varias (casilla o clic) para verlas juntas en la hoja: lo marcado se ve con halo y aquí con el color de su utilidad.":
        "Each utility with the kinds of line on this sheet. Check one or more (box or click) to see them together on the sheet: what is checked shows with a halo, and here with its utility's color.",
    "Ver en la hoja todas sus líneas y estructuras":
        "See all its lines and structures on the sheet",
    "Ver estas líneas en la hoja":
        "See these lines on the sheet",
    "Esta hoja no tiene líneas de utilidades.":
        "This sheet has no utility lines.",
    "Según el estándar BOE (buscando la leyenda en el PDF…).":
        "Per the BOE standard (looking for the legend in the PDF…).",
    "Según la leyenda del PDF ({donde}).":
        "Per the PDF's legend ({donde}).",
    "Según el estándar BOE: el PDF no trae leyenda.":
        "Per the BOE standard: the PDF has no legend.",
    "Leyenda completa del PDF ({n})":
        "Full PDF legend ({n})",
    "Aérea · {estado}":
        "Overhead · {estado}",
    "Leyenda del PDF: {d}":
        "PDF legend: {d}",
    "Línea AÉREA: se ve con su utilidad en «Capas del plano», pero no se reconoce (la app reconoce las subterráneas).":
        "OVERHEAD line: it shows with its utility in «Plan layers», but it is not recognized (the app recognizes underground lines).",
    "Estado según la leyenda del PDF para esas letras.":
        "Status according to the PDF's legend for those letters.",
    "{estado} · {capas}":
        "{estado} · {capas}",
    "No se reconoce":
        "Not recognized",
    "Resaltado: {what}":
        "Highlighted: {what}",
    "Leyendo las líneas de la hoja…":
        "Reading the sheet's lines…",
    "{capa} con halo; en línea fina, el resto de {u}":
        "{capa} with a halo; thin line, the rest of {u}",
    "{what} · {n} capas":
        "{what} · {n} layers",
    "{capa} (por sus letras)":
        "{capa} (by its letters)",
    "{capas} y {n} más":
        "{capas} and {n} more",
    "Capas: {capas}":
        "Layers: {capas}",
    "Estado «{c}» del nombre de la capa (BOE §8.1.6).":
        "Status «{c}» from the layer name (BOE §8.1.6).",
    "Estado tomado del nombre del xref de la capa.":
        "Status taken from the name of the layer's xref.",
    "El nombre no dice el estado: letras en MAYÚSCULA = propuesta, en minúscula = existente (leyendas de los planos).":
        "The name has no status: UPPERCASE letters = proposed, lowercase = existing (plan legends).",
    "«{m}» sobre la línea = a abandonar / abandonada.":
        "«{m}» on the line = to be abandoned / abandoned.",
    "Propuesta: línea continua (BOE fig. 3.1.7.1-2).":
        "Proposed: continuous line (BOE fig. 3.1.7.1-2).",
    "Letras leídas: {l}":
        "Letters read: {l}",
    "Estándar BOE: {a} — {en} ({es}).":
        "BOE standard: {a} — {en} ({es}).",
    "Clic: ver estas líneas en la hoja (otro clic, ver todo).":
        "Click: see these lines on the sheet (click again to see everything).",
    "Clic: ver en la hoja todas sus líneas y estructuras (otro clic, ver todo).":
        "Click: see all its lines and structures on the sheet (click again to see everything).",
    "Eléctrico de alta tensión (4160 V o más)":
        "High voltage electrical (4160 V and up)",
    "Eléctrico de baja tensión":
        "Low voltage electrical",
    "Gas natural":
        "Natural gas",
    "Agua contra incendios":
        "Fire protection water",
    "Riego":
        "Irrigation",
    "Agua potable":
        "Potable water",
    "Alcantarillado sanitario":
        "Sanitary sewer",
    "Drenaje pluvial":
        "Storm drain",
    "Fibra óptica":
        "Fiber optic",
    "Teléfono / comunicaciones":
        "Telephone / communications",
    "Bóvedas eléctricas":
        "Electrical vaults",
    "Buzones de alcantarillado":
        "Sanitary sewer manholes",
    "Buzones de drenaje":
        "Storm drain manholes",
    "Estructuras (bóvedas, buzones)":
        "Structures (vaults, manholes)",
    "Existente":
        "Existing",
    "Existente a demoler":
        "Existing to demolish",
    "Abandonada":
        "Abandoned",
    "A retirar":
        "To be removed",
    "Nueva (propuesta)":
        "New (proposed)",
    "Temporal":
        "Temporary",
    "Futura":
        "Future",
    "Fuera de contrato":
        "Not in contract",
    "Fase {n}":
        "Phase {n}",
    "Sin estado en el nombre":
        "No status in the name",
    "hoja {n}":
        "sheet {n}",
    "hojas {n}":
        "sheets {n}",
    "Capas de la hoja":
        "Sheet layers",
    "Vista previa":
        "Preview",
    "Volver a «{paso}»":
        "Back to «{paso}»",
    "Opacidad {pct}%":
        "Opacity {pct}%",
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
    "Capas usadas":
        "Layers used",
    "Líneas": "Lines",
    "Bóvedas": "Vaults",
    "Hoja {n}": "Sheet {n}",
    "Componer hoja de trabajo": "Compose working sheet",
    "Componer hoja de trabajo…": "Compose working sheet…",
    "Tomar área": "Take area",
    "Agregar el rectángulo marcado como una pieza nueva de la hoja compuesta":
        "Add the marked rectangle as a new piece of the composite sheet",
    "Agregar la hoja entera como una pieza":
        "Add the whole sheet as a piece",
    "Cómo se ajusta el rectángulo al plano":
        "How the rectangle snaps to the plan",
    "Ajustes":
        "Adjust",
    "Ángulo fino y escala de la pieza seleccionada":
        "Fine angle and scale of the selected piece",
    "Haz clic en una pieza para girarla, ajustarla o quitarla.":
        "Click a piece to rotate, adjust or remove it.",
    "Uniones":
        "Joins",
    "Cómo se unen las piezas vecinas":
        "How neighbouring pieces are joined",
    "Siempre queda al menos un panel abierto":
        "At least one panel always stays open",
    "Escala de la hoja": "Sheet scale",
    "Escala pieza": "Piece scale",
    "Imán": "Magnet",
    "Ángulo": "Angle",
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
    "quiebre del plano (radio mínimo)": "kink in the plan (minimum radius)",

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

    # ── Diálogo Opciones extra ─────────────────────────────────────────

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
    "Quitar la selección; si no hay, salir del modo":
        "Clear selection; if none, exit mode",
    "Doble clic": "Double click",
    "Sobre un texto: editarlo": "On a text: edit it",
    "Clic derecho": "Right click",
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
    "8) Presiona <b>Guardar diseño</b> — el diseño se guarda en el proyecto.":
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
        "8) Press <b>Save design</b> — the design is saved in the project.",
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
    "⊙ Snap al sólido «{c}»":
        "⊙ Snap to solid «{c}»",
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
    "No se pudo leer la imagen de la hoja del proyecto.":
        "The sheet image of the project could not be read.",
    "Abre un PDF para componer su hoja de trabajo.":
        "Open a PDF to compose its work sheet.",
    "Composición cancelada — se mantiene la hoja actual.":
        "Composition cancelled — the current sheet is kept.",
    "Apertura cancelada — no se cargó nada en el editor.":
        "Opening cancelled — nothing was loaded into the editor.",
    "Composición cancelada — el editor queda como estaba.":
        "Composition cancelled — the editor is left as it was.",
    "Reconocimiento cancelado — el editor queda como estaba.":
        "Recognition cancelled — the editor is left as it was.",
    "La hoja compuesta no cambió — el editor queda como estaba.":
        "The composite sheet did not change — the editor is left as it was.",
    "No hay tramos reconocidos para importar — el editor queda como estaba.":
        "There are no recognized segments to import — the editor is left as it was.",
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
    "Sin cambios en la hoja ni en sus capas: se usa el reconocimiento anterior.":
        "No changes to the sheet or its layers: the previous recognition is reused.",
    "Codos como esquina + radio (CV): {c}.":
        "Bends as corner + radius (CV): {c}.",
    "Quiebres como curva de radio mínimo: {q}.":
        "Kinks as curves with the minimum radius: {q}.",
    "Quiebres sin lugar para la curva mínima (tramos cortos), quedan como quiebre: {s}.":
        "Kinks with no room for the minimum curve (short segments), left as kinks: {s}.",
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
    "Tuberías que chocan":
        "Clashing pipes",
    "«{a}» y «{b}» se cruzan a la misma cota ({za:.2f} / {zb:.2f} ft) y no se conectan: en Civil 3D quedarán chocando.\n\nCorrige el dibujo o cambia la cota de una de las dos.":
        "«{a}» and «{b}» cross at the same elevation ({za:.2f} / {zb:.2f} ft) and are not connected: in Civil 3D they will clash.\n\nFix the drawing or change the elevation of one of them.",
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
    "presión (agua/gas)":
        "pressure (water/gas)",
    # ── composite_choice.py / composite_dialog.py: la hoja elegida (2026-10-05) ──
    "Para continuar, elige una hoja del plano.":
        "To continue, choose a sheet of the plan.",
    "La hoja {n} entera está en la hoja compuesta. Si solo necesitas una parte, arrastra un área sobre el plano o mueve las esquinas: la hoja compuesta se actualiza sola.":
        "The whole sheet {n} is in the composite sheet. If you only need part of it, drag an area over the plan or move the corners: the composite sheet updates by itself.",
    "La hoja compuesta usa el área marcada de la hoja {n}. Ajústala, o pulsa «Hoja completa» para volver a usar toda la hoja.":
        "The composite sheet uses the marked area of sheet {n}. Adjust it, or press «Full sheet» to use the whole sheet again.",
    "Volver a usar la hoja entera en esta pieza":
        "Use the whole sheet in this piece again",
    "✔ Lista para continuar: hoja {n} completa":
        "✔ Ready to continue: full sheet {n}",
    "✔ Lista para continuar: área de la hoja {n}":
        "✔ Ready to continue: area of sheet {n}",
    "Usar la hoja {n}":
        "Use sheet {n}",
    "Usar solo esta hoja":
        "Use only this sheet",
    "Quitar lo tomado y usar solo la hoja que estás viendo":
        "Drop what was taken and use only the sheet you are viewing",
    "La hoja {n} aún no está en la hoja compuesta (que usa: {donde}). Para sumarla, marca un área y pulsa «Tomar área», o pulsa «Hoja completa».":
        "Sheet {n} is not in the composite sheet yet (it uses: {donde}). To add it, mark an area and press «Take area», or press «Full sheet».",
    "Marca la casilla de cada hoja que vas a usar: las marcadas forman la hoja compuesta. La hoja {n} ya viene marcada (es la que estaba abierta); desmárcala si no la necesitas.":
        "Tick the box of each sheet you will use: the ticked sheets make up the composite sheet. Sheet {n} comes ticked (it was the open one); untick it if you do not need it.",
    "Marca la casilla de cada hoja que vas a usar: las marcadas forman la hoja compuesta. Clic en una hoja = verla; doble clic = tomar solo una parte en «Área a tomar».":
        "Tick the box of each sheet you will use: the ticked sheets make up the composite sheet. Click a sheet = view it; double click = take only part of it in «Area to take».",
    "Hojas marcadas: {n}":
        "Ticked sheets: {n}",
    "Desmarcar: quitarla de la hoja compuesta":
        "Untick: remove it from the composite sheet",
    "Marcar: usar esta hoja en la hoja compuesta":
        "Tick: use this sheet in the composite sheet",
    "Desmarcar la hoja":
        "Untick the sheet",
    "La hoja {n} tiene un área tomada.":
        "Sheet {n} has a taken area.",
    "Si la desmarcas, sale de la hoja compuesta y se pierde esa área.":
        "If you untick it, it leaves the composite sheet and that area is lost.",
    "Desmarcarla":
        "Untick it",
    "{n} piezas":
        "{n} pieces",
    "Área tomada":
        "Area taken",
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
    "Utilidad {layer} · Ø{diam} · {n} vértices":
        "Utility {layer} · Ø{diam} · {n} vertices",
    "{d} (Por defecto)":
        "{d} (Default)",
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
    "Dirección o intersección… ej: Colfax Ave & Chandler Blvd":
        "Address or intersection… e.g.: Colfax Ave & Chandler Blvd",
    "Buscar y descargar":
        "Search and download",
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
    "Hay un área marcada en la hoja {n} sin tomar.":
        "There is a marked area on sheet {n} that was not taken.",
    "La hoja {n} que estás viendo no está en la hoja compuesta.":
        "Sheet {n}, which you are viewing, is not in the composite sheet.",
    "Origen":
        "Source",
    "Área a tomar":
        "Area to take",
    "Elegir el PDF y la hoja":
        "Choose the PDF and the sheet",
    "Marcar el área de la hoja y tomarla":
        "Mark the sheet area and take it",
    "Acomodar las piezas tomadas":
        "Arrange the pieces taken",
    "Atrás":
        "Back",
    "Siguiente: Área a tomar":
        "Next: Area to take",
    "Siguiente: Hoja compuesta":
        "Next: Composite sheet",
    "✔ Lista para continuar: {n} pieza(s)":
        "✔ Ready to continue: {n} piece(s)",
    "Tomarla":
        "Take it",
    "Tomar la hoja {n}":
        "Take sheet {n}",
    "Ir":
        "Go",
    "Ver todas las hojas":
        "See all sheets",
    "Volver a «Origen» para elegir otra hoja":
        "Back to «Source» to choose another sheet",
    "Ver hoja compuesta":
        "See composite sheet",
    "Hoja {n} de {total}":
        "Sheet {n} of {total}",
    "✔ ya está en la hoja compuesta":
        "✔ already in the composite sheet",
    "Acomoda las piezas arrastrándolas: el imán alinea los extremos de las líneas y los puentes (verde) los unen. Cada pieza conserva sus vectores, capas, textos y medidas.":
        "Arrange the pieces by dragging them: the magnet aligns the line ends and the bridges (green) join them. Each piece keeps its vectors, layers, texts and measurements.",
    "Usa la regla para enderezar cada pieza y pásala al editor para dibujar las utilidades a mano.":
        "Use the ruler to straighten each piece and send it to the editor to draw the utilities by hand.",
    "Editar área":
        "Edit area",
    "Ajustar en «Área a tomar» el recorte de la pieza seleccionada":
        "Adjust the selected piece's crop in «Area to take»",
    "Aún no hay piezas: toma un área en «Área a tomar».":
        "No pieces yet: take an area in «Area to take».",
    "Área sin tomar":
        "Area not taken",
    "Marcaste un área en la hoja {n} pero no la tomaste.":
        "You marked an area on sheet {n} but did not take it.",
    "Si no la tomas, no estará en la hoja compuesta.":
        "If you do not take it, it will not be in the composite sheet.",
    "Tomar el área":
        "Take the area",
    "Seguir sin tomarla":
        "Continue without it",
    "Tomar área de esta hoja":
        "Take area of this sheet",
    "Ir a «Área a tomar» con la hoja elegida":
        "Go to «Area to take» with the chosen sheet",
    "A la vista: hoja {n} de {total}":
        "Viewing: sheet {n} of {total}",
    "PDF":
        "PDF",
    "Agregar PDF…":
        "Add PDF…",
    "Quitar PDF":
        "Remove PDF",
    "Composición sugerida {k} de {n}:":
        "Suggested composition {k} of {n}:",
    "Quitar este PDF del compositor (sus hojas salen de la hoja compuesta)":
        "Remove this PDF from the composer (its sheets leave the composite sheet)",
    "¿Quitar «{pdf}» del compositor?":
        "Remove “{pdf}” from the composer?",
    "Sus {n} pieza(s) salen de la hoja compuesta.":
        "Its {n} piece(s) leave the composite sheet.",
    "Agregar otro PDF":
        "Add another PDF",
    "Escala leída del texto de la hoja; corrígela si no es la del plano.":
        "Scale read from the sheet text; correct it if it is not the plan's scale.",
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
    "Sin cubrir: {n} (magenta) · Fuera de patrón: {m} (turquesa)":
        "Uncovered: {n} (magenta) · Off-pattern: {m} (turquoise)",

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
    "#{n} {capa}{tag} — {d} · {v} vértices":
        "#{n} {capa}{tag} — {d} · {v} vertices",
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
    "{n} cruce(s) a la misma cota sin conexión":
        "{n} crossing(s) at the same elevation without connection",
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
    "Tuberías dibujadas con sus dos paredes: {n} — se toma la línea del medio (una sola utilidad).":
        "Pipes drawn with their two walls: {n} — the middle line is used (a single utility).",
    "Tuberías dibujadas con paredes y eje: {n} — se usa el eje y se omiten las paredes.":
        "Pipes drawn with walls and centerline: {n} — the centerline is used and the walls are skipped.",
    "Puntas unidas a su bóveda (imán): {n} — quedaban a menos de {d} pt de su contorno y se llevaron hasta él por su propia recta.":
        "Line ends joined to their vault (magnet): {n} — they were less than {d} pt from its outline and were moved onto it along their own line.",
    "Llevando los ángulos de los quiebres a pasos de {p}°…":
        "Snapping bend angles to {p}° steps…",
    "Ángulos de los quiebres a pasos de {p}°: {n} — cada vértice se movió lo mínimo (máx. {d:.2f} pt); los codos conservan su radio.":
        "Bend angles in steps of {p}°: {n} — each vertex moved as little as possible (max. {d:.2f} pt); elbows keep their radius.",
    "Líneas con el ángulo del plano en sus quiebres: {n} — llevarlas a pasos de {p}° las apartaba de la tinta o de una línea que tocan.":
        "Lines that keep the plan's angle at their bends: {n} — snapping them to {p}° steps pulled them off the ink or away from a line they touch.",
    "Sus quiebres quedan con el ángulo exacto del plano: llevarlos a pasos de 0.25° las apartaba de la tinta o las separaba de una línea que tocan. Revisa el ángulo de sus codos en el editor.":
        "Their bends keep the plan's exact angle: snapping them to 0.25° steps pulled them off the ink or away from a line they touch. Check their elbow angles in the editor.",
    "Reconocidas por las letras de su línea (no por el nombre de la capa): {n} — {capas}.":
        "Recognized by the letters on their line (not by the layer name): {n} — {capas}.",
    "(su nombre decía {u})":
        "(its name said {u})",
    "Capa «-A» sin el patrón de marcadores «/» a lo largo de la línea: {n} — NO se marcan como abandonadas.":
        "«-A» layer without the «/» marker pattern along the line: {n} — NOT marked as abandoned.",
    "Cobertura de guiones: {pct:.1f}% ({n} sin cubrir, en magenta).":
        "Dash coverage: {pct:.1f}% ({n} uncovered, in magenta).",
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
    "({a} como cajas sueltas, sin unir a una línea.)":
        "({a} as standalone boxes, not joined to a line.)",
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
    # ── capa «Cargando…» del asistente (busy.py) ──
    "Analizando el PDF…":
        "Analyzing the PDF…",
    "Armando la hoja compuesta…":
        "Building the composite sheet…",
    "{n} piezas · vectores, capas y textos intactos":
        "{n} pieces · vectors, layers and text kept intact",
    "Hoja {n} · leyendo las líneas y estructuras de cada capa":
        "Sheet {n} · reading the lines and structures of each layer",
    "Hoja {p} · {u} ({i} de {n})":
        "Sheet {p} · {u} ({i} of {n})",
    "Importando al editor…":
        "Importing into the editor…",
    "Preparando la vista previa…":
        "Preparing the preview…",
    "Dibujando lo reconocido sobre la hoja":
        "Drawing the recognized items over the sheet",
    "Cargando hoja {n}…":
        "Loading sheet {n}…",
    "Leyendo sus capas":
        "Reading its layers",
    "Actualizando la vista…":
        "Updating the view…",
    "Leyendo las capas de la hoja…":
        "Reading the sheet layers…",
    "Contando los trazos de cada capa":
        "Counting the strokes in each layer",
    "Líneas generales y escala de la hoja":
        "Sheet guide lines and scale",
    "Agregando la pieza…":
        "Adding the piece…",
    "Bordes, extremos de línea y uniones con las vecinas":
        "Edges, line ends and joins with neighboring pieces",
    "Abriendo «Componer hoja»…":
        "Opening «Compose sheet»…",
    "Preparando las hojas del PDF":
        "Preparing the PDF sheets",
    "Utilidad #{n}":
        "Utility #{n}",
    "{n} rutas ({m} tramos) de {u}":
        "{n} routes ({m} segments) of {u}",
    "¿Qué utilidad quieres ajustar?":
        "Which utility do you want to adjust?",

    # ── composite_dialog.py (rama dev_santos_v2) ──
    "Hoja {n} · sin capas":
        "Sheet {n} · no layers",
    "✔ Área tomada como pieza {n} ({label}). Ya está en la hoja compuesta ({total} pieza(s)).":
        "✔ Area taken as piece {n} ({label}). It is already on the composite sheet ({total} piece(s)).",
    "Esta hoja ya está en la hoja compuesta.": "This sheet is already on the composite sheet.",
    "La hoja {n} aún no está en la hoja compuesta: marca un área y pulsa «Tomar área», o pulsa «Hoja completa».":
        "Sheet {n} is not on the composite sheet yet: draw an area and press «Take area», or press «Full sheet».",
    "Hoja sin tomar": "Sheet not taken",
    "La hoja {n} que estás viendo aún no está en la hoja compuesta.":
        "Sheet {n}, the one you are viewing, is not on the composite sheet yet.",
    "Si continúas así, solo se usará lo que ya tomaste: {taken}.":
        "If you continue now, only what you already took will be used: {taken}.",
    "{pdf} · hoja {n}": "{pdf} · sheet {n}",
    "Agregar el área marcada": "Add the marked area",
    "Agregar la hoja {n} completa": "Add full sheet {n}",
    "Usar solo el área marcada": "Use only the marked area",
    "Usar solo la hoja {n}": "Use only sheet {n}",
    "Continuar sin ella": "Continue without it",
    "Volver": "Go back",
    # ── vista previa del reconocimiento: resumen (2026-09-30) ──
    "Tramos": "Segments",
    "Abandonadas": "Abandoned",
    "Codos": "Bends",
    "Polilíneas que se importan al editor.": "Polylines imported into the editor.",
    "Tramos marcados (AB): capa «-A» + patrón «/», o patrón «//».":
        "Marked segments (AB): «-A» layer + «/» pattern, or «//» pattern.",
    "Esquinas con radio (curvas reales del plano).": "Corners with a radius (real curves of the plan).",
    "Bóvedas que quedan como nodos de las líneas.": "Vaults that become nodes of the lines.",
    "activas": "active",
    "abandonadas (AB)": "abandoned (AB)",
    "Unir tramos": "Join segments",
    "Marcar como pendiente": "Mark as pending",

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
    "Guiones del plano cubiertos por las líneas reconocidas. En el dibujo: magenta = sin cubrir, turquesa a puntos = trazos fuera de patrón (leaders/flechas).":
        "Plan dashes covered by the recognized lines. In the drawing: magenta = uncovered, dotted turquoise = off-pattern strokes (leaders/arrows).",
    "1 bóveda sin línea":
        "1 vault without a line",
    "{n} bóvedas sin línea":
        "{n} vaults without a line",

    # ── recognition_review_view.py / recognition_dialog.py (paneles 2026-10-03) ──
    "Para verificar ({n})":
        "To check ({n})",
    "Para verificar":
        "To check",
    "Nada que verificar":
        "Nothing to check",
    "{what}: no hay nada reconocido de esta capa en la hoja.":
        "{what}: nothing from this layer was recognized on the sheet.",
    "1 línea":
        "1 line",
    "{n} líneas":
        "{n} lines",
    "1 bóveda":
        "1 vault",
    "{n} bóvedas":
        "{n} vaults",
    "Resaltado: {what} · {parts}":
        "Highlighted: {what} · {parts}",
    "Visto":
        "Seen",
    "Ver todo":
        "Show all",
    "Quitar el resaltado y ver toda la hoja.":
        "Remove the highlight and show the whole sheet.",
    "Clic: verla resaltada en la hoja (otro clic la quita).":
        "Click: see it highlighted on the sheet (click again to remove).",
    "Clic en una capa para verla en la hoja.":
        "Click a layer to see it on the sheet.",
    "Al ver todos los casos queda marcado como visto.":
        "Once all cases have been seen it is marked as seen.",
    "Clic: marcar como visto.":
        "Click: mark as seen.",
    "Marcar como visto":
        "Mark as seen",
    "Todo se reconoció sin dudas: no hay nada que mirar antes de importar.":
        "Everything was recognized without doubts: nothing to look at before importing.",
    "En rojo, lo que no se pudo reconocer. Lo demás se reconoció y conviene mirarlo en la hoja antes de importar.":
        "In red, what could not be recognized. The rest was recognized and is worth a look on the sheet before importing.",
    "Todo se reconoció. Estos puntos conviene mirarlos en la hoja antes de importar; no son errores. Clic en uno para verlo.":
        "Everything was recognized. These points are worth a look on the sheet before importing; they are not errors. Click one to see it.",
    "Puntos ya vistos. Clic derecho en uno: marcarlo como pendiente.":
        "Points already seen. Right-click one: mark it as pending.",
    "✔ Todos vistos":
        "✔ All seen",
    "{k} de {n} vistos":
        "{k} of {n} seen",
    "No hay líneas de esta utilidad en la hoja. Si el plano usa otros nombres de capa, indícalos con «Ajustar capas…».":
        "There are no lines of this utility on the sheet. If the plan uses other layer names, set them with «Adjust layers…».",
    "Ningún nombre de capa es conocido. Indica cuáles son las líneas con «Ajustar capas…».":
        "No layer name is known. Tell which ones are the lines with «Adjust layers…».",
    "Su capa dice «abandonada» (-A), pero la línea no lleva las marcas «/». Se importan como activas: confirma si lo son.":
        "Their layer says «abandoned» (-A), but the line has no «/» marks. They are imported as active: confirm whether they are.",
    "Su capa es «existente a abandonar» (-D). Se importan como activas hasta que tú decidas.":
        "Their layer is «existing to be abandoned» (-D). They are imported as active until you decide.",
    "Llevan las marcas «/» de abandonada, pero su capa es activa. Se importan como activas.":
        "They carry the abandoned «/» marks, but their layer is active. They are imported as active.",
    "El plano no las dibuja como un arco exacto (radio que cambia o esquina cortada). Se importan como tramos rectos que siguen la curva.":
        "The plan does not draw them as an exact arc (changing radius or cut corner). They are imported as straight segments that follow the curve.",
    "Están en el plano, pero ninguna línea llega a ellas (anillo magenta). Se importan igual, como cajas sueltas; mira si les falta una línea.":
        "They are on the plan, but no line reaches them (magenta ring). They are imported anyway, as standalone boxes; check whether a line is missing.",
    "La curva del plano no es un arco perfecto. Se importó el arco que mejor la sigue (a trazos en la hoja).":
        "The plan's curve is not a perfect arc. The arc that best follows it was imported (dashed on the sheet).",
    "Trozos de línea del plano que no quedaron dentro de ninguna línea reconocida (en magenta). Suelen ser restos sueltos del dibujo.":
        "Pieces of plan line that did not end up inside any recognized line (in magenta). They are usually loose leftovers of the drawing.",
    "El nombre de su capa no dice esta utilidad, pero las letras de la línea sí (por ejemplo «—TE—»). Confirma que es así; si no, cámbialo con «Ajustar capas…».":
        "Their layer name does not say this utility, but the letters on the line do (for example «—TE—»). Confirm it; if not, change it with «Adjust layers…».",
    "{n} ocultas por ti":
        "{n} hidden by you",

    # ── recognition_summary_view.py (rama dev_santos_v2) ──
    "Clic: ir al lugar en la hoja (cada clic, el siguiente).":
        "Click: go to the spot on the sheet (each click, the next one).",
    "Detalles ({n})":
        "Details ({n})",
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

    # ── Bancoductos: varias utilidades por diseño + selección masiva ──
    "{n} utilidades": "{n} utilities",
    "Bancoducto «{nombre}» asignado a {n} utilidad(es).":
        "Duct bank «{nombre}» assigned to {n} utility(ies).",
    "Bancoducto quitado de {n} utilidad(es); el diseño queda en la lista.":
        "Duct bank removed from {n} utility(ies); the design stays in the list.",
    "{n} utilidades seleccionadas — clic derecho para acciones en bloque.":
        "{n} utilities selected — right-click for bulk actions.",
    "Seleccionar todas las utilidades (Ctrl+A)": "Select all utilities (Ctrl+A)",
    "Seleccionar todas las de tipo «{tipo}»": "Select all of type «{tipo}»",
    "Asignar bancoducto existente": "Assign existing duct bank",
    "{nombre}  ·  {n} conducto(s)": "{nombre}  ·  {n} conduit(s)",
    "{n} utilidades seleccionadas": "{n} utilities selected",
    "Cambiar tipo ({n})": "Change type ({n})",
    "Crear un bancoducto para las {n} utilidades": "Create one duct bank for the {n} utilities",
    "Quitar el bancoducto de las {n} utilidades": "Remove the duct bank from the {n} utilities",
    "Eliminar {n} utilidades": "Delete {n} utilities",
    "{n} utilidades ({lista})": "{n} utilities ({lista})",
    "Duct banks: {n} → asignado a {k} utilidades": "Duct banks: {n} → assigned to {k} utilities",
    "Duct bank «{nombre}» guardado → asignado a {k} utilidades.":
        "Duct bank «{nombre}» saved → assigned to {k} utilities.",
    "Ya tiene el bancoducto «{nombre}»: se reemplazará.":
        "Already has the duct bank «{nombre}»: it will be replaced.",
    "Filtrar utilidades…": "Filter utilities…",
    "Ninguna": "None",
    "Marcar todas las utilidades de la lista (respeta el filtro).":
        "Check every utility in the list (respects the filter).",
    "Desmarcar todas las utilidades de la lista (respeta el filtro).":
        "Uncheck every utility in the list (respects the filter).",
    "{n} ya tenía(n) otro bancoducto: se reemplazará.":
        "{n} already had another duct bank: it will be replaced.",
    "Al exportar, estas {n} utilidades serán un duct bank con este mismo diseño.":
        "On export, these {n} utilities will be a duct bank with this same design.",
    "Proyecto guardado": "Project saved",
    "Guardando el DXF…": "Saving the DXF…",
    "Lista de utilidades · selección masiva": "Utilities list · bulk selection",
    "Ctrl + clic": "Ctrl + click",
    "Agregar o quitar una utilidad de la selección": "Add or remove a utility from the selection",
    "Shift + clic": "Shift + click",
    "Seleccionar un rango de utilidades": "Select a range of utilities",
    "Seleccionar todas las utilidades (con la lista activa)": "Select all utilities (with the list focused)",
    "Seleccionar todas las de un mismo tipo": "Select all of the same type",
    "Eliminar las utilidades seleccionadas (pide confirmación)": "Delete the selected utilities (asks for confirmation)",
    "Diseñador de bancoducto": "Duct bank designer",
    "Pasar el mouse": "Hover",
    "En «Asignar a:», miniatura de la utilidad sobre el plano": "In «Assign to:», thumbnail of the utility on the plan",
    "Soltar la herramienta activa sin cerrar la ventana": "Drop the active tool without closing the window",
    "Lienzo y ratón": "Canvas and mouse",
    "En la lista «Bancoductos», miniatura de la sección": "In the «Duct banks» list, thumbnail of the section",
    "General": "General",
    "Ningún atajo coincide con la búsqueda.": "No shortcut matches the search.",
    "Teclas y gestos de la app, agrupados por menú. Escribe para filtrar.": "App keys and gestures, grouped by menu. Type to filter.",
    "Buscar atajo o acción…": "Search shortcut or action…",
    "Largo (Pies):": "Length (Feet):",
    "Ancho (Pies):": "Width (Feet):",
    "Altura del sólido (Pies):": "Solid height (Feet):",
    "Largo del sólido (lado largo), en pies. Viene medido del plano; al cambiarlo se redibuja en el lienzo.": "Length of the solid (long side), in feet. Measured from the plan; changing it redraws it on the canvas.",
    "Ancho del sólido (lado corto), en pies. Viene medido del plano; al cambiarlo se redibuja en el lienzo.": "Width of the solid (short side), in feet. Measured from the plan; changing it redraws it on the canvas.",
    "Altura del sólido 3D en Civil 3D, en pies (por defecto 6.56168 ft = 2 m).": "Height of the 3D solid in Civil 3D, in feet (default 6.56168 ft = 2 m).",
    "Propiedades del sólido": "Solid properties",
    "El buzón está desactivado: actívalo para cambiarlo a elemento curvo.":
        "The manhole is deactivated: activate it to change it to a curved element.",
    "Un sólido no se puede cambiar a elemento curvo.": "A solid cannot be changed to a curved element.",
    "{cod}  ·  Sólido {l:g} × {a:g} × {h:g} ft": "{cod}  ·  Solid {l:g} × {a:g} × {h:g} ft",
    "Cota superior (Pies):": "Top elevation (Feet):",
    "Cota de la parte SUPERIOR del sólido, en pies (la base queda en cota − altura).\n"
    "Por defecto es la cota de la utilidad a la que está unido.":
        "Elevation of the TOP of the solid, in feet (the base is elevation − height).\n"
        "By default it is the elevation of the utility it is attached to.",
    "Volver a la cota de la utilidad unida": "Back to the attached utility's elevation",
    "Sin utilidad unida: se usa la cota de fondo o 0.": "No attached utility: the bottom elevation or 0 is used.",
    "Automática: la utilidad unida llega al centro del sólido.":
        "Automatic: the attached utility reaches the middle of the solid.",
    "Fijada por el usuario.": "Set by the user.",
    "Utilidad #{n} → bancoducto «{nombre}» ({c} conducto(s))":
        "Utility #{n} → duct bank «{nombre}» ({c} conduit(s))",
    "Tiene bancoducto asignado:":
        "It has a duct bank assigned:",
    "{n} utilidades tienen bancoducto asignado:":
        "{n} utilities have a duct bank assigned:",
    "Al eliminarla(s) se quita esa asignación. El diseño del bancoducto se conserva en la lista «Bancoductos» (sin asignar si no queda en ninguna otra utilidad). Se puede deshacer con Ctrl+Z.":
        "Deleting it (them) removes that assignment. The duct bank design is kept in the «Duct banks» list (unassigned if no other utility uses it). You can undo with Ctrl+Z.",
    # ── Normativas de diseño (normativas.py, normativas_dialog.py, accesorios_view.py) ──
    "En Civil 3D: {acc} de {ang} (accesorio sólido) en la red «{red}».":
        "In Civil 3D: {acc} of {ang} (solid fitting) in network «{red}».",
    "Reúne dos quiebres muy juntos: Civil 3D pone un solo codo.":
        "It merges two very close bends: Civil 3D places a single bend.",
    "&Normativas":
        "&Standards",
    "Normativas de diseño…":
        "Design standards…",
    "Mostrar accesorios (tipo y ángulo)":
        "Show fittings (type and angle)",
    "Codo":
        "Bend",
    "Tee":
        "Tee",
    "Wye":
        "Wye",
    "Cruz":
        "Cross",
    "Medido sobre el eje: desvío de {g} respecto del lado recto prolongado.":
        "Angle between the two pipes (the pipe turns {g}).",
    "Normativas de diseño":
        "Design standards",
    # ── Unir utilidades (unir_utilidades.py) ──
    "Unir utilidades seleccionadas":
        "Join selected utilities",
    "Unir utilidades":
        "Join utilities",
    "Selecciona dos o más utilidades: Ctrl+clic en la lista «Utilidades» o sobre ellas en el lienzo.":
        "Select two or more utilities: Ctrl+click in the «Utilities» list or on them on the canvas.",
    "Se unirán {n} utilidades en la #{b} ({k} empalme(s), en verde en el plano).":
        "{n} utilities will be joined into #{b} ({k} joint(s), in green on the plan).",
    "Huecos que se cierran con un tramo recto: {lista}.":
        "Gaps closed with a straight run: {lista}.",
    "Se conservan los datos de la #{b}:":
        "The data of #{b} is kept:",
    "Se puede deshacer con Ctrl+Z.":
        "You can undo it with Ctrl+Z.",
    "Se unieron {n} utilidades en la #{b}.":
        "{n} utilities were joined into #{b}.",
    "Unir en una utilidad (Ctrl+J)":
        "Join into one utility (Ctrl+J)",
    "El plano no tiene escala: fija la escala antes de unir utilidades.":
        "The plan has no scale: set the scale before joining utilities.",
    "Selecciona al menos dos utilidades para unirlas.":
        "Select at least two utilities to join them.",
    "La utilidad #{n} no se puede unir (no está dibujada en el lienzo).":
        "Utility #{n} cannot be joined (it is not drawn on the canvas).",
    "La utilidad #{n} es de otro tipo («{a}» y «{b}»): solo se unen utilidades del mismo tipo.":
        "Utility #{n} is of another type («{a}» and «{b}»): only utilities of the same type are joined.",
    "La utilidad #{n} termina a mitad de otra: es un ramal (una T), no una continuación. Solo se unen utilidades punta con punta.":
        "Utility #{n} ends in the middle of another: it is a branch (a tee), not a continuation. Utilities are only joined end to end.",
    "La utilidad #{n} no toca a las demás: su punta más cercana está a {d:.2f} ft (se cierran huecos de hasta {m:g} ft).":
        "Utility #{n} does not touch the others: its closest end is {d:.2f} ft away (gaps of up to {m:g} ft are closed).",
    "#{n}: {campo} «{v}» → «{w}» (como la #{b}).":
        "#{n}: {campo} «{v}» → «{w}» (like #{b}).",
    "sí":
        "yes",
    "no":
        "no",
    "diámetro":
        "diameter",
    "material":
        "material",
    "abandonada":
        "abandoned",
    "familia":
        "family",
    "tamaño":
        "size",
    "Ctrl + clic (lienzo)":
        "Ctrl + click (canvas)",
    "Sobre una utilidad: sumarla o quitarla de la selección":
        "On a utility: add it to or remove it from the selection",
    "Clic derecho (lienzo)":
        "Right click (canvas)",
    "Sobre una utilidad: su menú (con varias seleccionadas, «Unir en una utilidad»)":
        "On a utility: its menu (with several selected, «Join into one utility»)",
    # ── Normativas: Excel (normativas_excel.py, normativas_clearance.py) ──
    "Agua":
        "Water",
    "Alcantarillado":
        "Sewer",
    "Drenaje":
        "Storm drain",
    "Gas":
        "Gas",
    "Eléctrico":
        "Electrical",
    "Telecomunicaciones":
        "Telecommunications",
    "Buzón":
        "Manhole",
    "Excel (*.xlsx)":
        "Excel (*.xlsx)",
    # ── Agregar tamaño a una familia (catalogo_tamanos) ──
    'Agregar un tamaño nuevo a esta familia (en Civil 3D 2025 en adelante, en español e inglés)':
        'Add a new size to this family (in Civil 3D 2025 and later, in Spanish and English)',
    'Agregar tamaño':
        'Add size',
    'Elige primero una familia.':
        'Choose a family first.',
    'Tamaño {s} agregado a «{f}».':
        'Size {s} added to “{f}”.',
    'Diámetro interior':
        'Inside diameter',
    'Ancho interior':
        'Inside width',
    'Alto interior':
        'Inside height',
    'Largo interior':
        'Inside length',
    'español':
        'Spanish',
    'inglés':
        'English',
    'Civil 3D {a} · {i}':
        'Civil 3D {a} · {i}',
    'Diámetro nominal':
        'Nominal diameter',
    'Diámetro exterior':
        'Outside diameter',
    'Grosor de pared':
        'Wall thickness',
    'La familia no está en esta instalación.':
        'This installation does not have the family.',
    'Sin permiso para escribir el catálogo: ejecuta la app como administrador.':
        'No permission to write the catalog: run the app as administrator.',
    'El catálogo está en uso: cierra Civil 3D y vuelve a intentarlo.':
        'The catalog is in use: close Civil 3D and try again.',
    'Agregar un tamaño a «{f}»':
        'Add a size to “{f}”',
    'Tamaños actuales: {lista}':
        'Current sizes: {lista}',
    'Medidas del tamaño nuevo':
        'New size dimensions',
    'En esta familia las dos medidas se combinan con las que ya existen: el valor nuevo de cada una se podrá usar con todas las de la otra.':
        'In this family the two dimensions combine with the existing ones: the new value of each can be used with every value of the other.',
    'Otros datos (calculados de los tamaños vecinos; puedes corregirlos)':
        'Other data (calculated from the neighboring sizes; you can correct them)',
    'Agregar en':
        'Add to',
    '(no tiene esta familia)':
        '(does not have this family)',
    'Si Civil 3D está abierto y el catálogo de presión no se puede escribir, ciérralo y vuelve a intentarlo.':
        'If Civil 3D is open and the pressure catalog cannot be written, close it and try again.',
    'Civil 3D regenera su catálogo solo la próxima vez que importes la red (o con el comando PREPARAR_FAMILIAS).':
        'Civil 3D regenerates its catalog by itself the next time you import the network (or with the PREPARAR_FAMILIAS command).',
    'Marca al menos una instalación de Civil 3D.':
        'Check at least one Civil 3D installation.',
    'agregado':
        'added',
    'no tiene esta familia':
        'does not have this family',
    'error':
        'error',
    'No se pudo agregar el tamaño:':
        'The size could not be added:',
    'Tamaño {s}:':
        'Size {s}:',
    'Esta familia no tiene una tabla de tamaños que la app pueda ampliar.':
        'This family has no size table the app can extend.',
    # ── Unir utilidades con ramales (unir_ramales) ──
    'Quedan aparte {k} trozo(s) partido(s) en la T (en ámbar en el plano).':
        '{k} piece(s) cut at the tee stay separate (in amber on the plan).',
    'La #{n} se cruza en una T justo sobre un codo: no se puede partir ahí.':
        '#{n} meets a tee right on a bend: it cannot be cut there.',
    'Las utilidades seleccionadas se ramifican y no caben en una sola línea: quedaría fuera la #{n}. Únelas por partes.':
        'The selected utilities branch out and do not fit in a single line: #{n} would be left out. Join them in parts.',
    'La #{n} se parte en la T: el trozo que no entra queda como utilidad aparte.':
        '#{n} is cut at the tee: the piece that does not fit stays as a separate utility.',
    # ── Paneles laterales que se ocultan solos (side_panels) ──
    'Ocultar automáticamente: el panel queda como una pestaña en el borde y se abre al pasar el ratón':
        'Auto-hide: the panel becomes a tab on the edge and opens when you hover over it',
    'Ocultar automáticamente':
        'Auto-hide',
    'Fijar el panel (que no se oculte)':
        'Pin the panel (keep it open)',
    'Fijar el panel':
        'Pin the panel',
    'Ocultar automáticamente el panel izquierdo':
        'Auto-hide the left panel',
    'Ocultar automáticamente el panel derecho':
        'Auto-hide the right panel',
    # ── Autoguardado y recuperación (autoguardado) ──
    'Recuperar trabajo sin guardar':
        'Recover unsaved work',
    'Trabajo recuperado. Guárdalo (Ctrl+S) para conservarlo.':
        'Work recovered. Save it (Ctrl+S) to keep it.',
    'No se pudo guardar la copia automática: {error}':
        'The automatic backup could not be saved: {error}',
    'Proyecto sin nombre':
        'Untitled project',
    'La aplicación se cerró sin guardar los últimos cambios, pero hay una copia automática:':
        'The application closed without saving the latest changes, but there is an automatic backup:',
    '«{nombre}» · {n} utilidades · copia del {fecha}':
        '“{nombre}” · {n} utilities · backup from {fecha}',
    'Hay {k} copia(s) más antiguas: se ofrecerán la próxima vez.':
        'There are {k} older backup(s): they will be offered next time.',
    'Recuperar':
        'Recover',
    'Descartar':
        'Discard',
    'Más tarde':
        'Later',
    # ── Edición en bloque y copiar/pegar propiedades (edicion_bloque) ──
    'Solo cambia lo que elijas; lo que quede en «(sin cambios)» se respeta en cada utilidad. Se puede deshacer con Ctrl+Z.':
        'Only what you choose changes; anything left as “(no change)” is kept on each utility. Can be undone with Ctrl+Z.',
    'Propiedades':
        'Properties',
    'Familia':
        'Family',
    '(sin cambios)':
        '(no change)',
    'Tamaño (diámetro)':
        'Size (diameter)',
    'Tamaño (diámetro):':
        'Size (diameter):',
    'Tipo de tubería':
        'Pipe type',
    'Tipo de tubería:':
        'Pipe type:',
    'Material':
        'Material',
    'Material:':
        'Material:',
    'Estado':
        'Status',
    'Activa':
        'Active',
    'Abandonada (AB)':
        'Abandoned (AB)',
    'Estado:':
        'Status:',
    'Sin catálogo de Civil 3D: elige la versión en la barra superior.':
        'No Civil 3D catalog: choose the version in the top bar.',
    '{n} utilidades de tipo «{tipo}»':
        '{n} utilities of type “{tipo}”',
    'Aplicar a {n} utilidades':
        'Apply to {n} utilities',
    'Tienen familias distintas: elige una familia para cambiar el tamaño.':
        'They have different families: choose a family to change the size.',
    'Pegar también los datos extendidos del usuario ({n})':
        'Also paste the user extended data ({n})',
    'Con bancoducto ({k}): su familia y tamaño no cambian (los define el bancoducto).':
        'With a duct bank ({k}): their family and size do not change (the duct bank defines them).',
    'Las de otro tipo ({k}) no se tocan.':
        'Those of another type ({k}) are left untouched.',
    'Editar en bloque':
        'Bulk edit',
    'Pegar propiedades':
        'Paste properties',
    'Copiar propiedades':
        'Copy properties',
    'Selecciona dos o más utilidades del mismo tipo: Ctrl+clic en la lista «Utilidades» o sobre ellas en el lienzo, o clic derecho → «Seleccionar todas las de tipo …».':
        'Select two or more utilities of the same type: Ctrl+click in the “Utilities” list or on them in the canvas, or right-click → “Select all of type …”.',
    'Selecciona la utilidad de la que quieres copiar las propiedades.':
        'Select the utility whose properties you want to copy.',
    'Primero copia las propiedades de una utilidad: clic derecho sobre ella → «Copiar propiedades».':
        'First copy the properties of a utility: right-click on it → “Copy properties”.',
    'Las utilidades seleccionadas son de tipos distintos ({tipos}). Esto se hace solo con utilidades del mismo tipo: clic derecho → «Seleccionar todas las de tipo …».':
        'The selected utilities are of different types ({tipos}). This only works with utilities of the same type: right-click → “Select all of type …”.',
    'Propiedades de la utilidad #{n} copiadas: selecciona otras de tipo «{tipo}» y elige «Pegar propiedades».':
        'Properties of utility #{n} copied: select others of type “{tipo}” and choose “Paste properties”.',
    'Pegar propiedades de la utilidad #{n}':
        'Paste properties of utility #{n}',
    'Copiar propiedades de la utilidad #{n}':
        'Copy properties of utility #{n}',
    'Se actualizaron {n} de {total} utilidades.':
        '{n} of {total} utilities were updated.',
    'Las propiedades copiadas son de una utilidad de tipo «{tipo}»: solo se pegan en utilidades de ese tipo.':
        'The copied properties belong to a utility of type “{tipo}”: they can only be pasted on utilities of that type.',
    'Editar en bloque: familia, diámetro… ({n})':
        'Bulk edit: family, diameter… ({n})',
    'Copiar propiedades de la #{n} a las demás':
        'Copy properties of #{n} to the others',
    'Pegar propiedades de la #{n}':
        'Paste properties of #{n}',
    'Editar utilidades seleccionadas en bloque…':
        'Bulk edit selected utilities…',
    'Copiar propiedades de la utilidad':
        'Copy utility properties',
    'Pegar propiedades en las seleccionadas':
        'Paste properties on the selected',
    'Con varias seleccionadas: editar en bloque (familia, diámetro…), copiar propiedades, eliminar, cambiar tipo, crear o asignar bancoducto, quitarlo':
        'With several selected: bulk edit (family, diameter…), copy properties, delete, change type, create or assign a duct bank, remove it',
    # ── Revisar y limpiar el dibujo (limpieza) ──
    'Revisar y limpiar el dibujo':
        'Review and clean up the drawing',
    'Revisar y limpiar el dibujo…':
        'Review and clean up the drawing…',
    'Tramos rectos diminutos (menos de {min} ft): en Civil 3D salen como tuberías diminutas':
        'Tiny straight runs (under {min} ft): they come out as tiny pipes in Civil 3D',
    'Puntas casi unidas (hasta {max} ft): se unen exacto a la otra utilidad':
        'Ends that almost touch (up to {max} ft): they are joined exactly to the other utility',
    'Utilidades más cortas que {corta} ft: se eliminan':
        'Utilities shorter than {corta} ft: they are deleted',
    'Utilidades repetidas (la misma línea dos veces): se elimina la copia':
        'Repeated utilities (the same line twice): the copy is deleted',
    'se quita un vértice que sobra':
        'an extra vertex is removed',
    'la curva se estira hasta el vértice':
        'the curve is stretched to the vertex',
    'la curva arranca justo en el vértice':
        'the curve starts exactly at the vertex',
    'Clic para verlo en el plano.':
        'Click to see it on the plan.',
    'Arreglar y exportar':
        'Fix and export',
    'Arreglar lo marcado':
        'Fix what is checked',
    'Para revisar a mano (no se cambian)':
        'To review by hand (not changed)',
    '{u} · tramo de {l} ft: {como}':
        '{u} · {l} ft run: {como}',
    '{u} · tramo de {l} ft: no se arregla solo (junto a un buzón, una unión u otra curva)':
        '{u} · {l} ft run: not fixed automatically (next to a manhole, a junction or another curve)',
    '{u} · punta a {l} ft de otra de su tipo: se une':
        '{u} · end {l} ft from another of its type: joined',
    '{u} · punta a {l} ft de otra de su tipo: no se une sola (el tramo quedaría muy corto)':
        '{u} · end {l} ft from another of its type: not joined automatically (the run would be too short)',
    '{u} · mide {l} ft':
        '{u} · {l} ft long',
    '{u} · repetida ({l} ft)':
        '{u} · repeated ({l} ft)',
    '{u} · mide {l} ft y no toca ninguna otra de su tipo':
        '{u} · {l} ft long and touches no other of its type',
    'No hay utilidades dibujadas (o falta la escala de la hoja).':
        'There are no utilities drawn (or the sheet scale is missing).',
    'Todo en orden: no hay nada que limpiar.':
        'All good: there is nothing to clean up.',
    'Dibujo limpio: {n} arreglo(s).':
        'Drawing cleaned: {n} fix(es).',
    # ── Normativas en tablas, tabla de datos y avisos (normas_*.py, tabla_datos*, avisos_view) ──
    'Tipo de utilidad':
        'Utility type',
    'Diámetro':
        'Diameter',
    'Diámetro según amperaje y largo':
        'Diameter by amperage and length',
    'Accesorio':
        'Fitting',
    'Condición de uso':
        'Condition of use',
    'T domiciliaria':
        'Service tee',
    'Sin tipo: elige su tipo para revisar sus normativas.':
        'No type: choose its type to check its standards.',
    'El tipo «{tipo}» ya no está en la lista de tipos.':
        'The type “{tipo}” is no longer in the list of types.',
    'Diámetro {d}: solo se permite en {nota}.':
        'Diameter {d}: only allowed in {nota}.',
    'Falta el amperaje: escríbelo para revisar su diámetro.':
        'Amperage missing: enter it to check its diameter.',
    'debe ser {lista}':
        'must be {lista}',
    '{r} ft de largo':
        '{r} ft long',
    'Diámetro {d}: {req}':
        'Diameter {d}: {req}',
    '{acc} no permitida en «{tipo}».':
        '{acc} not allowed in “{tipo}”.',
    '{acc}: no hay un tamaño menor que {d} en {lista} para el ramal.':
        '{acc}: there is no size smaller than {d} in {lista} for the branch.',
    '{acc}: el ramal debe ser {r} (un tamaño menor que {d}); es {dr}.':
        '{acc}: the branch must be {r} (one size smaller than {d}); it is {dr}.',
    'Codo de {ang}: fuera de norma. Permitidos: {lista}.':
        '{ang} bend: out of standard. Allowed: {lista}.',
    'Gravedad':
        'Gravity',
    'Presión':
        'Pressure',
    'Nombre':
        'Name',
    'Utilidad':
        'Utility',
    'Tipo':
        'Type',
    'Tamaño':
        'Size',
    'Diámetro (in)':
        'Diameter (in)',
    'Largo (ft)':
        'Length (ft)',
    'Vértices':
        'Vertices',
    'Rasante inicial (ft)':
        'Start invert (ft)',
    'Rasante final (ft)':
        'End invert (ft)',
    'Amperaje (A)':
        'Amperage (A)',
    'Inicio X':
        'Start X',
    'Inicio Y':
        'Start Y',
    'Fin X':
        'End X',
    'Fin Y':
        'End Y',
    'Avisos':
        'Warnings',
    'Por defecto':
        'Default',
    'Buzones y cajas':
        'Manholes and boxes',
    'Código':
        'Code',
    'Clase':
        'Class',
    'Red':
        'Network',
    'Tapa (ft)':
        'Rim (ft)',
    'Fondo (ft)':
        'Sump (ft)',
    'Visible':
        'Visible',
    'Forma':
        'Shape',
    'Ancho (ft)':
        'Width (ft)',
    'Alto (ft)':
        'Height (ft)',
    'Vértice':
        'Vertex',
    'Radio (ft)':
        'Radius (ft)',
    'Automático ({r} ft)':
        'Automatic ({r} ft)',
    'Automático':
        'Automatic',
    'Quiebre del plano':
        'Bend from the plan',
    'Curva':
        'Curve',
    'Sólido':
        'Solid',
    'Caja':
        'Box',
    'No':
        'No',
    'Sí':
        'Yes',
    'Ancho (in)':
        'Width (in)',
    'Alto (in)':
        'Height (in)',
    'Avisos de normativa':
        'Standards warnings',
    'Tipo de aviso':
        'Warning type',
    'Mensaje':
        'Message',
    'Información':
        'Information',
    'Cumple las normativas.':
        'Meets the standards.',
    'Menú Normativas → Normativas de diseño… para ver las tablas.':
        'Standards menu → Design standards… to see the tables.',
    'Utilidad {n}':
        'Utility {n}',
    '(sin tipo)':
        '(no type)',
    'Tipo:':
        'Type:',
    '0 = sin dato.':
        '0 = no data.',
    'Amperaje:':
        'Amperage:',
    '{n} línea(s) que casi tocan a otra: se unirán':
        '{n} line(s) that almost touch another: they will be joined',
    '{n} línea(s) muy cortas (menos de {corta} ft): se borrarán':
        '{n} very short line(s) (under {corta} ft): they will be deleted',
    '{n} línea(s) repetidas: se borrará la copia':
        '{n} repeated line(s): the copy will be deleted',
    '{n} tramo(s) rectos diminutos: se corrigen':
        '{n} tiny straight run(s): they are fixed',
    'Antes de exportar':
        'Before exporting',
    'Encontramos algunas cosas que conviene arreglar antes de exportar:':
        'We found a few things worth fixing before exporting:',
    'Esto saldría mal en Civil 3D o habría que corregirlo a mano:':
        'This would come out wrong in Civil 3D or would have to be fixed by hand:',
    '{n} caso(s) para revisar a mano':
        '{n} case(s) to review by hand',
    'Ver detalles (elegir qué arreglar, ir a cada caso)':
        'See details (choose what to fix, go to each case)',
    'Exportar sin arreglar':
        'Export without fixing',
    'Tipos':
        'Types',
    'Edita las tablas aquí mismo (doble clic en una celda) y pulsa «Guardar cambios». Valen para todos tus proyectos. El Excel es opcional: para compartirlas o editarlas en lote.':
        'Edit the tables right here (double-click a cell) and press «Save changes». They apply to all your projects. The Excel file is optional: to share them or edit them in bulk.',
    'Guardar cambios': 'Save changes',
    'Reglas': 'Rules',
    'En {donde}, {elemento}': 'In {donde}, {elemento}',
    'si': 'if',
    'solo referencia (no se revisa).': 'reference only (not checked).',
    'con {u}': 'with {u}',
    '(desactivada)': '(disabled)',
    'Fuente: {f}': 'Source: {f}',
    'Separación con otra utilidad': 'Clearance from another utility',
    'no puede ser {lista}': 'cannot be {lista}',
    'entre {a} y {b}': 'between {a} and {b}',
    'mínimo {v}': 'minimum {v}',
    'máximo {v}': 'maximum {v}',
    '{r} in de diámetro': '{r} in diameter',
    'Diámetro {d}: es de «{otro}» y esta utilidad es «{tipo}». Para su tipo: {req}.': 'Diameter {d}: it belongs to «{otro}» and this utility is «{tipo}». For its type: {req}.',
    'Diámetro {d} no permitido para «{tipo}»: {req}.': 'Diameter {d} not allowed for «{tipo}»: {req}.',
    '{etq} T{n} {v}: {req}': '{etq} S{n} {v}: {req}',
    '(y 1 tramo más)': '(and 1 more segment)',
    '(y {n} tramos más)': '(and {n} more segments)',
    '{etq} {v}: {req}': '{etq} {v}: {req}',
    'Amperaje': 'Amperage',
    'Quiebre de {g} sin buzón: {req}': 'Bend of {g} without a manhole: {req}',
    'Caída en el buzón {v}: {req}': 'Drop in the manhole {v}: {req}',
    'Abrir el manual de usuario': 'Open the user manual',
    'Según el manual de usuario': 'According to the user manual',
    'CONFLICTOS DETECTADOS': 'DETECTED CONFLICTS',
    'Choque en Civil 3D': 'Clash in Civil 3D',
    'Propuestas calculadas por la app': 'Proposals calculated by the app',
    'Probadas en una copia del proyecto': 'Tested on a copy of the project',
    'Aplicar propuesta elegida': 'Apply chosen proposal',
    '{n} totales': '{n} total',
    '{n} resueltos': '{n} resolved',
    'Red: {a} vs {b}': 'Network: {a} vs {b}',
    'Utilidad: {a}': 'Utility: {a}',
    'Cotas: {v}': 'Inverts: {v}',
    'Separación actual: {v} ft': 'Current clearance: {v} ft',
    '(Req: ≥ {v} ft)': '(Req: ≥ {v} ft)',
    'Recomendada por la IA': 'Recommended by the AI',
    'Recomendada': 'Recommended',
    '{n} opciones': '{n} options',
    '1 opción': '1 option',
    'Δ Cota: {v} ft': 'Δ Invert: {v} ft',
    'Cota: {v} ft': 'Invert: {v} ft',
    'Separación libre: {v} ft': 'Clearance: {v} ft',
    'Motivo de recomendación:': 'Why it is recommended:',
    'Ctrl+↵': 'Ctrl+↵',
    'No entendí qué cambio quieres. Puedo mover utilidades, subir o bajar sus cotas, cambiar diámetro, material, tipo o estado, borrar utilidades, resolver un conflicto, llevarte a un elemento o abrir una ventana.': 'I did not understand what change you want. I can move utilities, raise or lower their inverts, change diameter, material, type or status, delete utilities, resolve a conflict, take you to an element or open a window.',
    'No encuentro la utilidad «{c}» en el proyecto.': 'I cannot find utility «{c}» in the project.',
    '¿A qué utilidad? Dime su código (por ejemplo AGUA-5).': 'Which utility? Tell me its code (for example AGUA-5).',
    '¿Cuántos pies y hacia dónde la muevo?': 'How many feet and in which direction should I move it?',
    '¿Cuántos pies subo o bajo sus cotas?': 'How many feet should I raise or lower its inverts?',
    '¿Qué cota de inicio o de fin le pongo?': 'What start or end invert should I set?',
    '¿Qué diámetro, en pulgadas?': 'What diameter, in inches?',
    '¿Qué material? Puede ser: {m}.': 'Which material? It can be: {m}.',
    '¿Qué tipo? Para esa utilidad puede ser: {m}.': 'Which type? For that utility it can be: {m}.',
    '(no hay tipos definidos en Normativas)': '(no types defined in Design standards)',
    'No encuentro el conflicto «{c}».': 'I cannot find conflict «{c}».',
    'No encuentro «{c}» en el proyecto.': 'I cannot find «{c}» in the project.',
    '¿Qué ventana abro? Puede ser: Vista 3D, Tabla de datos, Normativas, Exportar, Georreferenciar o Informe.': 'Which window should I open? It can be: 3D View, Data table, Design standards, Export, Georeference or Report.',
    '{v} ft al {d}': '{v} ft to the {d}',
    'este': 'east',
    'oeste': 'west',
    'norte': 'north',
    'sur': 'south',
    'Mover {u} {d} (todos sus vértices y sus buzones).': 'Move {u} {d} (all its vertices and its manholes).',
    'Subir': 'Raise',
    'Bajar': 'Lower',
    '{v} todas las cotas de {u} {d} ft (la pendiente no cambia).': '{v} all inverts of {u} by {d} ft (the slope does not change).',
    'inicio {v} ft': 'start {v} ft',
    'fin {v} ft': 'end {v} ft',
    'Poner a {u} la cota de {d}.': 'Set the {d} invert of {u}.',
    'Cambiar el diámetro de {u} a {d}".': 'Change the diameter of {u} to {d}".',
    'Cambiar el material de {u} a {m}.': 'Change the material of {u} to {m}.',
    'Cambiar el tipo de {u} a «{m}».': 'Change the type of {u} to «{m}».',
    'Marcar {u} como abandonada(s).': 'Mark {u} as abandoned.',
    'Quitar la marca de abandonada a {u}.': 'Remove the abandoned mark from {u}.',
    'Borrar {u} del proyecto.': 'Delete {u} from the project.',
    'Resolver {c} con la propuesta {p}.': 'Resolve {c} with proposal {p}.',
    'Resolver {c} con la mejor solución que la app pruebe.': 'Resolve {c} with the best solution the app tests.',
    'Llevar el plano a {c}.': 'Take the plan to {c}.',
    'Abrir {v}.': 'Open {v}.',
    'Entendí que quieres:': 'I understood you want:',
    'Consecuencias:': 'Consequences:',
    '¿Lo hago?': 'Shall I do it?',
    'Sí, hazlo': 'Yes, do it',
    'No se pudo hacer: {e}': 'It could not be done: {e}',
    'No hice nada. ¿Qué entendí mal? Dime qué cambio (por ejemplo otra utilidad u otra cantidad) y te lo vuelvo a proponer.': 'I did nothing. What did I get wrong? Tell me what to change (for example another utility or another amount) and I will propose it again.',
    'No pude calcular las consecuencias ({e}).': 'I could not calculate the consequences ({e}).',
    'No cambia nada del proyecto.': 'It does not change anything in the project.',
    'La escala del plano no está definida: no puedo mover en pies.': 'The plan scale is not defined: I cannot move in feet.',
    'Se van {n} conflicto(s) o aviso(s): {l}': '{n} conflict(s) or warning(s) go away: {l}',
    '⚠ Aparecerían {n} conflicto(s) o aviso(s) nuevos: {l}': '⚠ {n} new conflict(s) or warning(s) would appear: {l}',
    'No cambian los conflictos ni los avisos de normativa de la zona.': 'The conflicts and design-standard warnings of the area do not change.',
    'Sus puntas quedarían separadas de: {u}.': 'Its ends would be separated from: {u}.',
    '{n} lleva(n) bancoducto: se le quita.': '{n} carry a duct bank: it is removed.',
    'Se quitan {n} conexión(es) vertical(es) aprobada(s).': '{n} approved vertical connection(s) are removed.',
    '{n} lleva(n) bancoducto: su diámetro no cambia.': '{n} carry a duct bank: their diameter does not change.',
    'Ese conflicto ya no está en el dibujo.': 'That conflict is no longer in the drawing.',
    'Para {c} no hay una solución automática que lo resuelva sin crear otros problemas.': 'For {c} there is no automatic solution that resolves it without creating other problems.',
    '{c} no tiene la propuesta {p}.': '{c} has no proposal {p}.',
    'Se hará: {p}': 'It will do: {p}',
    'La app la probó: resuelve {c} sin crear otros problemas.': 'The app tested it: it resolves {c} without creating other problems.',
    'Además resuelve {n} problema(s) más.': 'It also resolves {n} more problem(s).',
    '⚠ La app la probó y no queda limpia: {r}': '⚠ The app tested it and it is not clean: {r}',
    'no resuelve el conflicto': 'it does not resolve the conflict',
    'y {n} más': 'and {n} more',
    'No encontré «{c}».': 'I did not find «{c}».',
    'Listo: el plano muestra {c}.': 'Done: the plan shows {c}.',
    'Abrí {v}.': 'I opened {v}.',
    'No se pudo aplicar la propuesta.': 'The proposal could not be applied.',
    'Hecho: {p} (Ctrl+Z para deshacer).': 'Done: {p} (Ctrl+Z to undo).',
    'Hecho: {q} (Ctrl+Z para deshacer).': 'Done: {q} (Ctrl+Z to undo).',
    'Minimizar el panel': 'Minimize the panel',
    'Mostrar el panel': 'Show the panel',
    'Opciones de la vista': 'View options',
    '{n} pendientes': '{n} pending',
    'Revisar uno por uno': 'Review one by one',
    'Recorre los conflictos con sus soluciones (N: siguiente)': 'Goes through the conflicts with their solutions (N: next)',
    'Aplicar la propuesta elegida (Ctrl+Enter); Ctrl+Z la deshace': 'Apply the chosen proposal (Ctrl+Enter); Ctrl+Z undoes it',
    '{k} de {n}': '{k} of {n}',
    'Sin conflictos': 'No conflicts',
    'Calculando soluciones…': 'Calculating solutions…',
    'Sin solución automática.': 'No automatic solution.',
    'Ajusta las cotas en «Editar»': 'Adjust the inverts in «Edit»',
    '{c} resuelto': '{c} resolved',
    'Siguiente conflicto ▶': 'Next conflict ▶',
    'Sugerida por la IA': 'Suggested by the AI',
    'La IA está eligiendo una alternativa…': 'The AI is choosing an alternative…',
    'Aplicado: {p} (Ctrl+Z para deshacer).': 'Applied: {p} (Ctrl+Z to undo).',
    'Conflicto anterior (Mayús+N)': 'Previous conflict (Shift+N)',
    'Siguiente conflicto (N)': 'Next conflict (N)',
    'Resolver': 'Resolve',
    'Aplicar': 'Apply',
    'En ese punto no va accesorio: deja de marcarse y Civil 3D no lo dibuja': 'No fitting goes at that point: it is no longer flagged and Civil 3D does not draw it',
    '{c}: sin accesorio en ese punto (Ctrl+Z para deshacer).': '{c}: no fitting at that point (Ctrl+Z to undo).',
    'Sin accesorio en ese punto (Ctrl+Z para deshacer).': 'No fitting at that point (Ctrl+Z to undo).',
    'No hay codo': 'No bend',
    'No hay T': 'No tee',
    'No hay Y': 'No wye',
    'No hay cruz': 'No cross',
    'No hay accesorio': 'No fitting',
    'Volver a poner el codo': 'Put the bend back',
    'Volver a poner la T': 'Put the tee back',
    'Volver a poner la Y': 'Put the wye back',
    'Volver a poner la cruz': 'Put the cross back',
    'Volver a poner el accesorio': 'Put the fitting back',
    'Ahí no se pondrá accesorio (ni en Civil 3D). Ctrl+Z para deshacer.': 'No fitting will go there (not in Civil 3D either). Ctrl+Z to undo.',
    'Buzón de {v}: {req}': 'Manhole of {v}: {req}',
    '¿No quedó claro? Pregúntale algo sobre esta regla…': 'Not clear? Ask it something about this rule…',
    'Preguntar': 'Ask',
    'La IA responde la duda sobre esta regla, siguiendo su explicación.': 'The AI answers your question about this rule, following its explanation.',
    'La IA no respondió ({e}).': 'The AI did not respond ({e}).',
    'Tú:': 'You:',
    'IA:': 'AI:',
    '{c} · {t} (resuelto)': '{c} · {t} (resolved)',
    '{c} · resuelto': '{c} · resolved',
    'Este conflicto ya no está en el dibujo. Conserva su número; Ctrl+Z lo deshace.': 'This conflict is no longer in the drawing. It keeps its number; Ctrl+Z undoes it.',
    'Diámetro del buzón (in)': 'Manhole diameter (in)',
    'Distancia entre buzones {v}: {req}': 'Distance between manholes {v}: {req}',
    '{acc} solo se permite en {tipos}.': '{acc} is only allowed in {tipos}.',
    '{acc}: la principal debe ser {req}; es {d}.': '{acc}: the main must be {req}; it is {d}.',
    '{acc}: el ramal debe ser {req}; es {d}.': '{acc}: the branch must be {req}; it is {d}.',
    '{acc}: el ramal ({dr}) va {v} menos que la principal ({d}): {req}.': '{acc}: the branch ({dr}) is {v} smaller than the main ({d}): {req}.',
    '{acc}: ramal a {ang}, fuera de norma. Permitidos: {lista}.': '{acc}: branch at {ang}, not compliant. Allowed: {lista}.',
    'entre bordes': 'edge to edge',
    'entre ejes': 'center to center',
    'A {v} de «{otra}» en paralelo ({como}): {req}': '{v} from «{otra}» running parallel ({como}): {req}',
    'Cruce con «{otra}»: {v} libres en vertical: {req}': 'Crossing with «{otra}»: {v} vertical clearance: {req}',
    'Cruce con «{otra}»: pasa {v} por encima: {req}': 'Crossing with «{otra}»: passes {v} above: {req}',
    'Cruce con «{otra}»: pasa {v} por debajo: {req}': 'Crossing with «{otra}»: passes {v} below: {req}',
    'Llega a «{otra}» de {d}: es {v} menor: {req}': 'Reaches «{otra}» of {d}: it is {v} smaller: {req}',
    'Normativas importadas: {t} tipos y {r} reglas.': 'Standards imported: {t} types and {r} rules.',
    'Todas las utilidades': 'All utilities',
    'Doble clic en una celda para cambiarla. Pasa el mouse por el título de cada columna para ver qué va ahí, y por una fila para leerla como frase.': 'Double-click a cell to change it. Hover over each column title to see what goes there, and over a row to read it as a sentence.',
    'Largo': 'Length',
    'Buzones': 'Manholes',
    'Error': 'Error',
    'o': 'or',
    'Armando la Tabla de datos…': 'Building the Data table…',
    'Exportando a Excel…': 'Exporting to Excel…',
    'Leyendo el archivo: {i} de {n} bytes': 'Reading the file: {i} of {n} bytes',
    'Preparando la imagen de la hoja…': 'Preparing the sheet image…',
    'Preparando la hoja para el imán…': 'Preparing the sheet for snapping…',
    'Leyendo las utilidades…': 'Reading the utilities…',
    'Armando las listas…': 'Building the lists…',
    'Dibujando el plano…': 'Drawing the plan…',
    'Juntando los datos del proyecto…': 'Gathering the project data…',
    'Guardando la imagen de la hoja…': 'Saving the sheet image…',
    'Guardando el PDF…': 'Saving the PDF…',
    'Comprimiendo el proyecto: {i} de {n} bytes': 'Compressing the project: {i} of {n} bytes',
    'Preparando la revisión…': 'Preparing the review…',
    'Buscando utilidades repetidas: {i} de {n}': 'Looking for repeated utilities: {i} of {n}',
    'Buscando utilidades muy cortas…': 'Looking for very short utilities…',
    'Revisando las puntas: {i} de {n}': 'Checking the ends: {i} of {n}',
    'Revisando tramos diminutos: {i} de {n}': 'Checking tiny segments: {i} of {n}',
    'Buscando utilidades sueltas: {i} de {n}': 'Looking for loose utilities: {i} of {n}',
    'Juntando los datos: {i} de {n} utilidades': 'Gathering the data: {i} of {n} utilities',
    'Juntando las cotas por vértice: {i} de {n} utilidades': 'Gathering the inverts per vertex: {i} of {n} utilities',
    'Armando la tabla: {i} de {n} filas': 'Building the table: {i} of {n} rows',
    'Ordenando la tabla: {i} de {n} filas': 'Sorting the table: {i} of {n} rows',
    'Ajustando las columnas: {i} de {n} filas': 'Fitting the columns: {i} of {n} rows',
    'Escribiendo el Excel: {i} de {n} filas': 'Writing the Excel file: {i} of {n} rows',
    'Marcando las columnas editables: {i} de {n} celdas': 'Marking the editable columns: {i} of {n} cells',
    'Guardando el Excel: {i} de {n} filas': 'Saving the Excel file: {i} of {n} rows',
    'cruces y conflictos': 'crossings and conflicts',
    'accesorios y avisos': 'fittings and warnings',
    'dibujando las marcas': 'drawing the marks',
    'Actualizando conflictos y avisos… {p} %': 'Updating conflicts and warnings… {p} %',
    'Escribe la cota o usa ↑ ↓ del teclado (±0.10 ft). Se aplica al instante en el plano y en 3D (Ctrl+Z lo deshace).':
        'Type the invert or use the ↑ ↓ keys (±0.10 ft). Applied right away on the plan and in 3D (Ctrl+Z undoes it).',
    'Tramo {t}: {largo} ft en planta': 'Segment {t}: {largo} ft in plan',
    'Rasante inicial': 'Start invert',
    'Rasante final': 'End invert',
    'El diámetro de esta utilidad no se cambia aquí (lo define su bancoducto o su familia de catálogo).':
        "This utility's diameter is not changed here (its duct bank or its catalog family sets it).",
    'Descartar cambios': 'Discard changes',
    '{tabla}, fila {n}, {col}: {motivo}': '{tabla}, row {n}, {col}: {motivo}',
    'No se guardó: corrige las celdas marcadas en rojo.': 'Not saved: fix the cells marked in red.',
    'Normativas guardadas.': 'Standards saved.',
    'Hay cambios sin guardar en las tablas de normativas. ¿Guardarlos?':
        'There are unsaved changes in the standards tables. Save them?',
    'Agregar fila': 'Add row',
    'Quitar filas': 'Remove rows',
    'Importar Excel…':
        'Import Excel…',
    'Exportar Excel…':
        'Export Excel…',
    'Volver a los valores iniciales':
        'Restore the initial values',
    'Aviso':
        'Warning',
    'Todo cumple las normativas.':
        'Everything meets the standards.',
    'Avisos ({n})':
        'Warnings ({n})',
    'Importar Excel de normativas':
        'Import standards Excel',
    'No se pudo leer el Excel.\n\n{e}':
        'The Excel file could not be read.\n\n{e}',
    'No se encontraron estas hojas (quedan vacías): {h}.':
        'These sheets were not found (left empty): {h}.',
    'Exportar Excel de normativas':
        'Export standards Excel',
    'No se pudo guardar el Excel (¿está abierto?).\n\n{e}':
        'The Excel file could not be saved (is it open?).\n\n{e}',
    'Normativas exportadas: {ruta}':
        'Standards exported: {ruta}',
    'Se reemplazan las normativas por las iniciales (los tipos que agregaste también se quitan). ¿Seguir?':
        'The standards are replaced by the initial ones (the types you added are removed too). Continue?',
    'Tabla de datos':
        'Data table',
    'Buscar en la tabla…':
        'Search in the table…',
    'Actualizar':
        'Refresh',
    'Exportar a Excel…':
        'Export to Excel…',
    'Doble clic en una fila para verla en el plano. Clic en un encabezado para ordenar.':
        'Double-click a row to see it on the plan. Click a header to sort.',
    'Exportar a Excel':
        'Export to Excel',
    'Tabla de datos exportada: {ruta}':
        'Data table exported: {ruta}',
    'No se pudieron guardar las normativas: {e}':
        'The standards could not be saved: {e}',
    '{n} avisos de normativa':
        '{n} standards warnings',
    'Agregar tipo':
        'Add type',
    'Tipo nuevo para {utilidad} (por ejemplo «Distribución secundaria»):':
        'New type for {utilidad} (for example “Secondary distribution”):',
    'Tipo «{tipo}» agregado.':
        'Type “{tipo}” added.',
    'Tabla de datos…':
        'Data table…',
    'Muestra junto a cada codo, Tee, Wye o cruz de agua y gas el accesorio que se pondrá en Civil 3D y su ángulo; en ámbar si tiene un aviso de normativa.':
        'Shows next to each water and gas bend, tee, wye or cross the fitting that Civil 3D will place and its angle; in amber if it has a standards warning.',
    'Mostrar avisos de normativa':
        'Show standards warnings',
    'Un circulito pequeño donde una utilidad o un accesorio no cumple las normativas (tipo, diámetro, amperaje…). Pasa el ratón para leerlo.':
        'A small circle where a utility or a fitting does not meet the standards (type, diameter, amperage…). Hover over it to read it.',
    'Mostrar avisos de reconocimiento':
        'Show recognition warnings',
    'Un circulito donde el reconocimiento del PDF no encontró el diámetro de una utilidad o no está seguro de él (queda el de por defecto). Pasa el ratón para leerlo.':
        'A small circle where the PDF recognition did not find a utility\'s diameter or is not sure of it (the default one stays). Hover over it to read it.',
    '{n} avisos de reconocimiento':
        '{n} recognition warnings',
    '{n} de reconocimiento':
        '{n} recognition',
    'Mostrar todos':
        'Show all',
    'Ocultar todos':
        'Hide all',
    'Tabla de datos: utilidades, buzones, curvas… (Ctrl+Shift+T)':
        'Data table: utilities, manholes, curves… (Ctrl+Shift+T)',
    'Avisos de normativa del proyecto. Clic para verlos.':
        'Project standards warnings. Click to see them.',
    'Agregar un tipo nuevo a esta utilidad: se guarda en las normativas y sale en su Excel al exportarlo':
        'Add a new type to this utility: it is saved in the standards and goes into its Excel when exporting it',
    'Amperaje de la línea (dato informativo): con él se revisa su diámetro según las normativas. Vacío (—) = sin dato.':
        'Line amperage (informative): it is used to check its diameter against the standards. Empty (—) = no data.',
    # ── Vista 3D (1.3.0) ──
    'Vista 3D':
        '3D view',
    'Vista 3D: lo que Civil 3D va a construir (F3)':
        '3D view: what Civil 3D will build (F3)',
    'Ver en 3D':
        'Show in 3D',
    'Dibuja o importa utilidades para verlas en 3D.':
        'Draw or import utilities to see them in 3D.',
    'Encuadrar todo':
        'Zoom to all',
    'Ver todo el modelo (Inicio)':
        'Show the whole model (Home)',
    'Arriba':
        'Top',
    'Frente':
        'Front',
    'Lateral':
        'Side',
    'Isométrica':
        'Isometric',
    'Seguir la selección':
        'Follow the selection',
    'Al elegir una utilidad o un buzón en el plano, la vista 3D lo encuadra':
        'When you pick a utility or a manhole on the plan, the 3D view zooms to it',
    'Mostrar':
        'Show',
    'Buzones, cajas y sólidos':
        'Manholes, boxes and solids',
    'Accesorios (codos, Tee, Wye…)':
        'Fittings (bends, tees, wyes…)',
    'Suelo':
        'Ground',
    'Mostrar el suelo':
        'Show the ground',
    'Cota':
        'Elevation',
    'Automática':
        'Automatic',
    'Automática: la tapa más alta de los buzones o, sin buzones, 3 ft sobre la tubería más alta':
        'Automatic: the highest manhole rim or, without manholes, 3 ft above the highest pipe',
    'Rueda: zoom · Botón central: desplazar · Shift + botón central o arrastrar: girar · Clic: elegir · Doble clic: encuadrar':
        'Wheel: zoom · Middle button: pan · Shift + middle button or drag: orbit · Click: pick · Double-click: zoom to it',
    'Actualizando la vista 3D…':
        'Updating the 3D view…',
    'Buscando los accesorios: {i} de {n} utilidades':
        'Finding the fittings: {i} of {n} utilities',
    'Armando los accesorios: {i} de {n}':
        'Building the fittings: {i} of {n}',
    'Armando las utilidades: {i} de {n}':
        'Building the utilities: {i} of {n}',
    'Armando los buzones y cajas: {i} de {n}':
        'Building the manholes and boxes: {i} of {n}',
    'Terminando la escena…':
        'Finishing the scene…',
    'Armando la vista 3D…':
        'Building the 3D view…',
    'Preparando los datos…':
        'Preparing the data…',
    '{etapa} · {p} %':
        '{etapa} · {p} %',
    'Actualizando la vista 3D… {p} %':
        'Updating the 3D view… {p} %',
    'Mostrando la escena…':
        'Showing the scene…',
    'Leyendo los trazos del PDF…':
        'Reading the PDF strokes…',
    'Digitalizando la imagen del plano…':
        'Digitizing the plan image…',
    'Leyendo la escala del plano…':
        'Reading the plan scale…',
    'Buscando el cajetín y las leyendas…':
        'Finding the title block and legends…',
    'Clasificando los trazos: {i} de {n}':
        'Classifying the strokes: {i} of {n}',
    'Uniendo las líneas…':
        'Joining the lines…',
    'Pasando los textos…':
        'Copying the texts…',
    'Terminando el plano…':
        'Finishing the plan…',
    'Guardando el plano digitalizado: {i} de {n} entidades':
        'Saving the digitized plan: {i} of {n} entities',
    'Revisando el plano digitalizado…':
        'Checking the digitized plan…',
    'Armando el plano: {i} de {n} entidades':
        'Building the plan: {i} of {n} entities',
    'Midiendo el plano para encuadrarlo: {i} de {n} entidades':
        'Measuring the plan to frame it: {i} of {n} entities',
    'Agregando las utilidades: {i} de {n}':
        'Adding the utilities: {i} of {n}',
    'Guardando el DXF: {i} de {n} entidades':
        'Saving the DXF: {i} of {n} entities',
    'Exportando a DXF…':
        'Exporting to DXF…',
    'No se pudo iniciar la vista 3D (OpenGL 2.1): {e}':
        'The 3D view could not start (OpenGL 2.1): {e}',
    'solera {a} → {b} ft':
        'invert {a} → {b} ft',
    'Bancoducto «{n}»':
        'Duct bank «{n}»',
    '{cod} · fondo {a} ft · tapa {b} ft':
        '{cod} · sump {a} ft · rim {b} ft',
    'Restablecer':
        'Reset',
    'Volver a los valores por defecto del suelo: visible, opacidad 18 % y cota automática':
        'Back to the default ground values: visible, 18 % opacity and automatic elevation',
    # ── Cubo de vistas (Vista 3D) ──
    'SUPERIOR':
        'TOP',
    'INFERIOR':
        'BOTTOM',
    'FRONTAL':
        'FRONT',
    'POSTERIOR':
        'BACK',
    'DERECHA':
        'RIGHT',
    'IZQUIERDA':
        'LEFT',
    'N':
        'N',
    'E':
        'E',
    'S':
        'S',
    'O':
        'W',
    'El proyecto aún no tiene archivo: se hizo una copia de recuperación. Guárdalo con Ctrl+S.':
        'The project has no file yet: a recovery copy was made. Save it with Ctrl+S.',
    # ── Ficha de la Vista 3D ──
    'Copia la ficha (para pegarla en Excel o en un correo)':
        'Copies the sheet (to paste it in Excel or an email)',
    'Copiar':
        'Copy',
    'Cota del eje (ft)':
        'Axis elevation (ft)',
    'Diámetros':
        'Diameters',
    'Fondo en 3D (ft)':
        'Sump in 3D (ft)',
    'Haz clic en una tubería, un accesorio o un buzón para ver sus datos.':
        'Click a pipe, a fitting or a manhole to see its data.',
    'Pendiente (%)':
        'Slope (%)',
    'Selección':
        'Selection',
    'Tapa en 3D (ft)':
        'Rim in 3D (ft)',
    'Une las utilidades':
        'Joins the utilities',
    'Ver en el plano':
        'Show on the plan',
    # ── Conflictos numerados y Excel de ida y vuelta ──
    '(vacío)':
        '(empty)',
    '2. Las columnas grises son de consulta: no se importan.':
        '2. Grey columns are for reference: they are not imported.',
    '3. En la app: Herramientas → Tabla de datos → «Importar Excel…». Verás los cambios antes de aplicarlos y se pueden deshacer con Ctrl+Z.':
        '3. In the app: Tools → Data table → «Import Excel…». You will see the changes before applying them and they can be undone with Ctrl+Z.',
    '4. En «Cotas por vértice», una celda vacía = cota automática (interpolada).':
        '4. In «Elevations per vertex», an empty cell = automatic elevation (interpolated).',
    '5 o más tuberías en un punto':
        '5 or more pipes at one point',
    'Automática (ft)':
        'Automatic (ft)',
    'Choque entre redes distintas':
        'Clash between different networks',
    'Conflicto':
        'Conflict',
    'Conflictos':
        'Conflicts',
    'Cota A (ft)':
        'Elevation A (ft)',
    'Cota B (ft)':
        'Elevation B (ft)',
    'Cota de llegada (ft)':
        'Incoming elevation (ft)',
    'Cota de salida (ft)':
        'Outgoing elevation (ft)',
    'Cotas por vértice':
        'Elevations per vertex',
    'Cruce a la misma cota':
        'Crossing at the same elevation',
    'Cruce sin conexión':
        'Crossing without connection',
    'Cómo editar este Excel y volver a cargarlo':
        'How to edit this Excel and load it back',
    'Detalle':
        'Detail',
    'Diferencia (ft)':
        'Difference (ft)',
    'El Excel no trae cambios respecto del proyecto.':
        'The Excel has no changes compared with the project.',
    'Excel importado: {n} cambio(s). Conflictos: {a} → {b}.':
        'Excel imported: {n} change(s). Conflicts: {a} → {b}.',
    'ID':
        'ID',
    'Importar Excel':
        'Import Excel',
    'Las columnas verdes se pueden editar en Excel y volver a cargar':
        'Green columns can be edited in Excel and loaded back',
    'Léeme':
        'Read me',
    'No se aplicaron:':
        'Not applied:',
    'Se aplicarán {n} cambio(s):':
        '{n} change(s) will be applied:',
    'Tipo de conflicto':
        'Conflict type',
    'Unión con pendiente':
        'Sloped joint',
    'Utilidad #{n} · vértice {v} · {campo}':
        'Utility #{n} · vertex {v} · {campo}',
    'Utilidad #{n} · {campo}':
        'Utility #{n} · {campo}',
    'Utilidad #{n}, vértice {v}: no existe.':
        'Utility #{n}, vertex {v}: does not exist.',
    'Utilidad #{n}: no existe en el proyecto.':
        'Utility #{n}: does not exist in the project.',
    'Utilidad N°':
        'Utility No.',
    '{donde}: «{v}» no es un número.':
        '{donde}: «{v}» is not a number.',
    '{u} utilidades · {e} buzones/cajas · {a} accesorios · {k} conflictos · suelo a {z} ft':
        '{u} utilities · {e} manholes/boxes · {a} fittings · {k} conflicts · ground at {z} ft',
    '«{a}» y «{b}» se cruzan a la misma cota ({za:.2f} / {zb:.2f} ft) y no se unen: las tuberías chocan. Cambia la cota de una de las dos o corrige el dibujo.':
        '«{a}» and «{b}» cross at the same elevation ({za:.2f} / {zb:.2f} ft) and are not joined: the pipes clash. Change the elevation of one of them or fix the drawing.',
    '«{a}» y «{b}» se cruzan y a una de las dos le falta la cota: no se puede confirmar que pasen a distinta altura.':
        '«{a}» and «{b}» cross and one of them has no elevation: it cannot be confirmed that they pass at different heights.',
    '«{cod}»: no existe en el proyecto.':
        '«{cod}»: does not exist in the project.',
    '… y {n} más':
        '… and {n} more',
    'Avisos y conflictos':
        'Warnings and conflicts',
    # ── hojas sin capas: capas por estilo, escala (2026-10-10) ──
    'Asigna un estilo a {u} en «Capas del plano» para reconocerla.':
        'Assign a style to {u} in «Plan layers» to recognize it.',
    'Automática':
        'Automatic',
    'Buzones donde terminan las tuberías del mapa (capa por estilo): {n} — cada tubería va de buzón a buzón.':
        "Manholes where the map's pipes end (style layer): {n} — each pipe runs from manhole to manhole.",
    'Calibra la escala con una distancia conocida: un PDF reducido puede no coincidir con la escala del rótulo.':
        'Calibrate the scale with a known distance: a reduced PDF may not match the title block scale.',
    'Calibrar con una distancia conocida…':
        'Calibrate with a known distance…',
    'Calibrar escala: clic en dos puntos de una distancia conocida · Esc = salir':
        'Calibrate scale: click two points of a known distance · Esc = exit',
    'Capa virtual por estilo. La casilla excluye sus trazos del reconocimiento; no cambia la imagen del PDF. Selecciónala para asignar utilidad y rol.':
        'Virtual style layer. The checkbox excludes its strokes from recognition; it does not change the PDF image. Select it to assign utility and role.',
    'Capas por estilo asignadas manualmente: revisa líneas y símbolos antes de importar. El estilo no determina si una red está abandonada.':
        'Style layers assigned by hand: review lines and symbols before importing. The style does not tell whether a network is abandoned.',
    'Capas por estilo de trazo continuo: {n} — cada trazo del plano es el eje de la tubería, sin unir ni mover nada.':
        'Continuous-stroke style layers: {n} — each stroke of the plan is the pipe centerline, nothing joined or moved.',
    'Clic en una capa para resaltarla y asignar su utilidad y rol abajo. Las casillas excluyen estilos del reconocimiento; el PDF conserva su imagen. Calibra la escala antes de importar.':
        'Click a layer to highlight it and assign its utility and role below. The checkboxes exclude styles from recognition; the PDF keeps its image. Calibrate the scale before importing.',
    'Codos en el extremo de una tubería del mapa: {n} — revisa si ahí hay un buzón.':
        'Bends at the end of a map pipe: {n} — check whether there is a manhole there.',
    'Distancia real entre los dos puntos (pies):':
        'Real distance between the two points (feet):',
    'El PDF no trae capas: sus líneas se agrupan por estilo (color y grosor). Asigna el estilo de la red a esta utilidad en «Capas de la hoja» o con «Ajustar capas…». Si la red es una imagen, dibújala a mano en el editor.':
        "The PDF has no layers: its lines are grouped by style (color and weight). Assign the network's style to this utility in «Sheet layers» or with «Adjust layers…». If the network is an image, draw it by hand in the editor.",
    'En el mapa, las tuberías van de buzón a buzón; aquí un codo cae donde termina una. Mira si es una curva o un buzón.':
        'On the map, pipes run from manhole to manhole; here a bend falls where one ends. Check whether it is a curve or a manhole.',
    'Escala del plano (pies por pulgada del PDF). Los radios y largos se calculan con ella al reconocer: si el PDF está impreso reducido, calíbrala aquí.':
        'Plan scale (feet per PDF inch). Radii and lengths are computed with it when recognizing: if the PDF is printed reduced, calibrate it here.',
    'Escribir la escala…':
        'Type the scale…',
    'Esta hoja no tiene capas originales: asigna el estilo de la red a esta utilidad en «Capas de la hoja» o con «Ajustar capas…». Si la red está en una imagen, requiere dibujo manual.':
        "This sheet has no original layers: assign the network's style to this utility in «Sheet layers» or with «Adjust layers…». If the network is in an image, it needs manual drawing.",
    'Hoja sin capas originales: sus líneas se agrupan por estilo (color y grosor) y en «Capas de la hoja» se asigna el de la red a su utilidad. Si la red está en una imagen, requiere dibujo manual.':
        "Sheet without original layers: its lines are grouped by style (color and weight) and in «Sheet layers» the network's style is assigned to its utility. If the network is in an image, it needs manual drawing.",
    'Hoja sin capas: elige abajo el estilo de la red y asígnale su utilidad (o Cancelar para dibujar a mano).':
        "Sheet without layers: pick the network's style below and assign its utility (or Cancel to draw by hand).",
    'Hoja {n} sin capas originales: sus líneas se agrupan por estilo (color y grosor). En «Capas de la hoja» asigna el estilo de la red a su utilidad. Si la red está en una imagen, requiere dibujo manual.':
        "Sheet {n} without original layers: its lines are grouped by style (color and weight). In «Sheet layers» assign the network's style to its utility. If the network is in an image, it needs manual drawing.",
    'La escala no se leyó del plano o puede no ser la real (un PDF impreso reducido). Calíbrala en «Capas de la hoja» con una distancia conocida: los radios y largos dependen de ella.':
        'The scale was not read from the plan or may not be the real one (a PDF printed reduced). Calibrate it in «Sheet layers» with a known distance: radii and lengths depend on it.',
    'Se asignan por su nombre o por tus decisiones en «Capas de la hoja». «Ajustar capas…» permite modificarlas.':
        'Assigned by their name or by your choices in «Sheet layers». «Adjust layers…» lets you change them.',
    'Selecciona una capa para asignar su utilidad.':
        'Select a layer to assign its utility.',
    'Utilidad':
        'Utility',
    'Aprobado:':
        'Approved:',
    'Aprobado':
        'Approved',
    'Pendiente':
        'Pending',
    'Aprobado por':
        'Approved by',
    'Fecha de aprobación':
        'Approval date',
    'Nota':
        'Note',
    '1. Cambia solo las columnas VERDES (cotas, tapas y fondos, radios, nombre, tipo, estado, familia, tamaño o diámetro, material, amperaje).':
        '1. Change only the GREEN columns (elevations, rims and sumps, radii, name, type, status, family, size or diameter, material, amperage).',
    'Familia y tamaño se escriben como en el catálogo de Civil 3D; un diámetro nuevo elige el tamaño de esa medida en la familia de la utilidad. «Por defecto» = sin familia o tamaño.':
        "Family and size are written as in the Civil 3D catalog; a new diameter picks the size of that measure in the utility's family. «Default» = no family or size.",
    '{donde}: «{v}» no es «Activa» ni «Abandonada».':
        '{donde}: «{v}» is neither «Active» nor «Abandoned».',
    '{donde}: «{v}» no está en el catálogo de Civil 3D de esta utilidad.':
        '{donde}: «{v}» is not in the Civil 3D catalog for this utility.',
    '{donde}: «{v}» no es un tamaño de su familia.':
        '{donde}: «{v}» is not a size of its family.',
    '{donde}: no hay un tamaño de {d} in en su familia.':
        '{donde}: there is no {d} in size in its family.',
    'Utilidad #{n}: lleva bancoducto; su sección la define el bancoducto.':
        'Utility #{n}: it has a duct bank; its section is defined by the duct bank.',
    'Aprobar seleccionados…':
        'Approve selected…',
    'Revisaste el aviso y se acepta así: deja de marcarse en el plano y queda registrado como aprobado (quién, cuándo y por qué).':
        'You reviewed the warning and accept it as is: it is no longer marked on the plan and is recorded as approved (who, when and why).',
    'Quitar aprobación':
        'Remove approval',
    'Mostrar aprobados':
        'Show approved',
    'Nota: {nota}':
        'Note: {nota}',
    'Ya no aplica (aprobado {fecha})':
        'No longer applies (approved {fecha})',
    'Aprobar avisos':
        'Approve warnings',
    'Se aprobarán {n} aviso(s). Queda registrado quién y cuándo.\nMotivo o nota (opcional):':
        '{n} warning(s) will be approved. Who and when is recorded.\nReason or note (optional):',
    'Carga un Excel exportado y editado: cotas, tapas y fondos, radios, nombre, tipo, estado, familia, tamaño o diámetro, material y amperaje. Verás los cambios antes de aplicarlos.':
        'Loads an exported and edited Excel: elevations, rims and sumps, radii, name, type, status, family, size or diameter, material and amperage. You will see the changes before applying them.',
    '{n} avisos aprobados':
        '{n} approved warnings',
    '{n} aviso(s) de normativa aprobado(s).':
        '{n} standards warning(s) approved.',
    'Aprobación quitada: {n} aviso(s).':
        'Approval removed: {n} warning(s).',
    'Pegar también las cotas (rasante inicial {a} ft, final {b} ft)':
        'Also paste the elevations (start invert {a} ft, end {b} ft)',
    'Las cotas por vértice (llegada y salida) se pegan solo en las utilidades con la misma cantidad de vértices; en las demás quedan interpoladas.':
        'Per-vertex elevations (incoming and outgoing) are pasted only in utilities with the same number of vertices; in the others they stay interpolated.',
    'Radio de curva':
        'Curve radius',
    'Curva de radio {r} ft: {req}':
        'Curve radius {r} ft: {req}',
    'No se usó (corrígelo en el Excel):':
        'Not used (fix it in the Excel):',
    'Pendiente por tramo (%)':
        'Slope per segment (%)',
    '5. Pendiente (%) = (rasante final − rasante inicial) / largo × 100. Si la cambias, cambia también la rasante inicial o la final para que coincidan: si no coinciden, el Excel NO se importa.':
        '5. Slope (%) = (end invert − start invert) / length × 100. If you change it, also change the start or end invert so they match: if they do not match, the Excel is NOT imported.',
    '6. Los conflictos (hoja «Conflictos», C-1, C-2…) se recalculan al importar.':
        '6. Conflicts («Conflicts» sheet, C-1, C-2…) are recalculated when importing.',
    'Utilidad #{n}: la pendiente «{v}» no es un número.':
        'Utility #{n}: the slope «{v}» is not a number.',
    'Utilidad #{n}: pendiente {p} %, pero sus rasantes ({zs} → {ze} ft en {L} ft) dan {dan} %. Para {p} % la rasante final sería {sug} ft (o la inicial {sug0} ft).':
        'Utility #{n}: slope {p} %, but its inverts ({zs} → {ze} ft over {L} ft) give {dan} %. For {p} % the end invert would be {sug} ft (or the start one {sug0} ft).',
    'No se importó nada: estas pendientes no coinciden con las cotas de su utilidad. La pendiente se calcula con la rasante inicial, la final y el largo: si la cambias, cambia también una rasante (o deja la pendiente como estaba). Corrige el Excel y vuelve a importarlo.':
        'Nothing was imported: these slopes do not match the elevations of their utility. The slope is calculated from the start invert, the end invert and the length: if you change it, also change an invert (or leave the slope as it was). Fix the Excel and import it again.',
    # ── mapas sin capas: leyenda del plano, acometidas, buzones y diámetros (2026-10-13/14) ──
    'Capas por estilo asignadas por la leyenda del plano: revisa líneas y símbolos antes de importar.':
        "Style layers assigned from the plan's legend: review lines and symbols before importing.",
    'Leyenda del plano: {n} trazo(s) de sus muestras no se reconocen como tuberías.':
        "Plan legend: {n} stroke(s) of its samples are not recognized as pipes.",
    'Leyenda del plano leída, pero ningún estilo es solo de una red: asígnalos abajo.':
        "Plan legend read, but no style belongs to a single network only: assign them below.",
    'Leyenda del plano: {u} — {l} estilo(s) de líneas y {e} de estructuras ya asignados. Revísalos y cambia lo que haga falta.':
        "Plan legend: {u} — {l} line style(s) and {e} structure style(s) already assigned. Review them and change what is needed.",
    'Leyenda del plano: {u} — {l} estilo(s) de líneas, {a} de acometidas y {e} de estructuras ya asignados. Revísalos y cambia lo que haga falta.':
        "Plan legend: {u} — {l} line style(s), {a} service-line style(s) and {e} structure style(s) already assigned. Review them and change what is needed.",
    'Sin asignar (la leyenda también los usa para lotes, anotaciones u otra red):':
        "Not assigned (the legend also uses them for lots, annotations or another network):",
    'Buzones de la leyenda unidos a su línea (su punta o un vértice cae en el símbolo, o lo atraviesa): {n}.':
        "Legend manholes joined to their line (its end or a vertex falls on the symbol, or it crosses it): {n}.",
    'Acometidas (servicios a los predios, leyenda «Tap»): {n}, {t} unidas a su tubería con una T — diámetro {d}" (nota de la leyenda).':
        'Service lines (taps to the lots, legend «Tap»): {n}, {t} joined to their pipe with a tee — diameter {d}" (legend note).',
    'Acometidas (servicios a los predios, leyenda «Tap»): {n}, {t} unidas a su tubería con una T.':
        "Service lines (taps to the lots, legend «Tap»): {n}, {t} joined to their pipe with a tee.",
    # Grosor de los mapas sin capas (recognition_grosor_mapa.py, 2026-10-23)
    'Diámetros del plano (rótulos junto a la tubería): {n} tubería(s) los toman; {m} dudosa(s) quedan con el diámetro por defecto y un aviso en el editor.':
        'Diameters from the plan (labels next to the pipe): {n} pipe(s) take them; {m} doubtful one(s) keep the default diameter and get a notice in the editor.',
    'Tuberías sin diámetro en el plano: {n} — ningún rótulo de diámetro va junto a ellas; quedan con el diámetro por defecto y un aviso en el editor.':
        'Pipes without a diameter on the plan: {n} — no diameter label goes next to them; they keep the default diameter and get a notice in the editor.',
    'El mapa escribe el diámetro junto a cada tramo, pero el de estas tuberías no es seguro: rótulos distintos en el mismo tramo, un rótulo que está entre dos tuberías, o un tramo sin rótulo con otro diámetro a cada lado (no se sabe dónde cambia). No se pone: quedan con el diámetro por defecto y el editor les pone un aviso con lo que dice el plano para que elijas el suyo.':
        'The map writes the diameter next to each run, but for these pipes it is not certain: different labels on the same run, a label lying between two pipes, or an unlabeled run with a different diameter on each side (where it changes is unknown). It is not set: they keep the default diameter and the editor gives them a notice with what the plan says so you can pick theirs.',
    'un rótulo junto a ella que no se sabe si es suyo (está entre dos tuberías o pasada su punta) dice {lista}':
        'a label next to it that may not be its own (it lies between two pipes or past its end) says {lista}',
    'no tiene rótulo y a cada lado el plano dice otro diámetro ({lista}): no se sabe dónde cambia':
        'it has no label and the plan gives a different diameter on each side ({lista}): where it changes is unknown',
    # Grosor del plano CAD (recognition_grosor.py, 2026-10-21)
    'Diámetros del plano (rótulos con flecha y paredes dibujadas): {n} tubería(s) los toman; {m} dudosa(s) quedan con el diámetro por defecto y un aviso en el editor.':
        'Diameters from the plan (labels with leaders and drawn walls): {n} pipe(s) take them; {m} doubtful one(s) keep the default diameter and get a notice in the editor.',
    'Tuberías sin diámetro en el plano: {n} — ningún rótulo con flecha llega a ellas ni tienen paredes dibujadas; quedan con el diámetro por defecto y un aviso en el editor.':
        'Pipes without a diameter on the plan: {n} — no label with a leader reaches them and they have no drawn walls; they keep the default diameter and get a notice in the editor.',
    'El plano dice algo del diámetro de estas tuberías, pero no con certeza: rótulos distintos que no se pudieron separar en un pozo, unión o esquina, un rótulo que no coincide con el ancho de sus paredes, o paredes dibujadas sin un rótulo en la hoja que diga si son las de adentro o las de afuera del tubo. No se pone: quedan con el diámetro por defecto y el editor les pone un aviso con lo que dice el plano para que elijas el suyo.':
        'The plan says something about the diameter of these pipes, but not with certainty: different labels that could not be separated at a manhole, junction or corner, a label that does not match the width of their walls, or drawn walls with no label on the sheet telling whether they are the inside or the outside of the pipe. It is not set: they keep the default diameter and the editor gives them a notice with what the plan says so you can pick theirs.',
    'El plano no dice el diámetro de estas tuberías: ningún rótulo de diámetro es suyo (en un plano CAD, ninguno con flecha llega a ellas y no tienen paredes dibujadas). Quedan con el diámetro por defecto y el editor les pone un aviso para que elijas el suyo.':
        'The plan does not give the diameter of these pipes: no diameter label is theirs (on a CAD plan, no label with a leader reaches them and they have no drawn walls). They keep the default diameter and the editor gives them a notice so you can pick theirs.',
    'Tuberías partidas donde el plano cambia de diámetro: {n} — sus rótulos dicen un diámetro hasta un nodo (pozo, unión o esquina) y otro después.':
        'Pipes split where the plan changes diameter: {n} — their labels give one diameter up to a node (manhole, junction or corner) and another after it.',
    # Composición sugerida (composite_suggest.py, 2026-10-14)
    '{n} hojas ({desde} → {hasta})':
        '{n} sheets ({desde} → {hasta})',
    'STA {a} → {b}':
        'STA {a} → {b}',
    '{n} PDF':
        '{n} PDFs',
    'Usar sugerencia':
        'Use suggestion',
    'Reemplaza la hoja compuesta por la sugerida (se puede deshacer)':
        'Replaces the composed sheet with the suggested one (can be undone)',
    'Volver a la hoja compuesta de antes de usar la sugerencia':
        'Go back to the composed sheet you had before using the suggestion',
    'Ocultar la sugerencia':
        'Hide the suggestion',
    'Buscando cómo se unen las hojas…':
        'Finding how the sheets join…',
    'Buscando cómo se unen las hojas… (hoja {i} de {n})':
        'Finding how the sheets join… (sheet {i} of {n})',
    'Confirmando las uniones con el dibujo…':
        'Confirming the joins against the drawing…',
    'Armando la composición sugerida…':
        'Building the suggested composition…',
    'Buscando en la carpeta el PDF con las hojas vecinas…':
        'Looking in the folder for the PDF with the neighboring sheets…',
    'Elegir el juego de hojas…':
        'Choose the set of sheets…',
    '✔ Composición sugerida en la hoja compuesta: {txt}.':
        '✔ Suggested composition in the composed sheet: {txt}.',
    'Encontré {n} juegos de hojas que se unen. ¿Cuál quieres usar?':
        'I found {n} sets of sheets that join. Which one do you want to use?',
    'No encontré hojas que se unan solas: compón la hoja a mano.':
        'No sheets join automatically: compose the sheet by hand.',
    'Composición sugerida:':
        'Suggested composition:',
    'Las hojas vecinas {celdas} ({n}) están en «{pdf}». ¿Agregarlo a la composición?':
        'The neighboring sheets {celdas} ({n}) are in «{pdf}». Add it to the composition?',
    '{n} hojas · vectores, capas y textos intactos':
        '{n} sheets · vectors, layers and text intact',
    'Volviendo a la hoja compuesta anterior…':
        'Going back to the previous composed sheet…',
    'Cancelando…': 'Cancelling…',
    'Hoja {p} · {u} ({i} de {n}) · capa {k} de {m}': 'Sheet {p} · {u} ({i} of {n}) · layer {k} of {m}',
    'La hoja necesita más memoria de la que hay libre en el equipo. Prueba con menos hojas en la composición, menos utilidades a la vez o cerrando otros programas.':
        'The sheet needs more memory than this computer has free. Try fewer sheets in the composition, '
        'fewer utilities at a time, or closing other programs.',
    'La hoja compuesta necesita más memoria de la que hay libre en el equipo.':
        'The composed sheet needs more memory than this computer has free.',
    'No se pudo armar la hoja compuesta.': 'The composed sheet could not be built.',
    'Leyendo los vectores de la hoja…': 'Reading the vectors of the sheet…',
    'Agrupando {n} trazos por su estilo (color, grosor, guiones)…': 'Grouping {n} strokes by style (color, width, dashes)…',
    'Buscando las acometidas (servicios a los predios)…': 'Looking for service taps (connections to lots)…',
    'Ubicando los símbolos de la leyenda (buzones, válvulas…)…': 'Locating the legend symbols (manholes, valves…)…',
    'Leyendo las letras del mapa (por la forma de cada letra)…': 'Reading the map text (by the shape of each letter)…',
    'Leyendo la leyenda del plano…': 'Reading the plan legend…',
    'Leyendo la leyenda de cada hoja…': 'Reading the legend of each sheet…',
    'Leyendo las letras de las líneas («—E—», «TE», «W»…)…': 'Reading the letters on the lines («—E—», «TE», «W»…)…',
    'Recortando lo que se ve de cada capa…': 'Clipping what is visible on each layer…',
    'Copiando cada hoja con sus vectores, capas y textos…': 'Copying each sheet with its vectors, layers and text…',
    'Buscando las líneas que cruzan cada costura…': 'Looking for the lines that cross each seam…',
    'Guardando la hoja compuesta…': 'Saving the composed sheet…',
    'Dibujando la hoja en pantalla ({w} × {h} px)…': 'Drawing the sheet on screen ({w} × {h} px)…',
    'Dibujando la hoja en pantalla…': 'Drawing the sheet on screen…',
    # agregar utilidad (por «Componer hoja»); «Capas»: utilidades y planos de fondo (ventana_capas/planos)
    '{n} de {t} hojas de la hoja del editor tienen su hoja en «{pdf}»: elige cuáles agregar.':
        '{n} of {t} sheets of the editor sheet have their sheet in «{pdf}»: choose which ones to add.',
    'Plano {n}': 'Plan {n}',
    'Todos': 'All',
    'Mostrando el plano: {p}…': 'Showing the plan: {p}…',
    'Plano': 'Plan',
    'No se pudo armar el plano de {p}.': 'The plan of {p} could not be built.',
    'El plano de {p} no mide lo mismo que la hoja.': 'The plan of {p} is not the same size as the sheet.',
    'Planos de fondo apagados: solo lo dibujado.': 'Background plans off: only what is drawn.',
    'Planos a la vista: {p}.': 'Plans on screen: {p}.',
    'Apagar': 'Turn off',
    'Encender': 'Turn on',
    'encendida': 'on',
    'apagada': 'off',
    'Capas': 'Layers',
    'Encender todas': 'Turn all on',
    'Todavía no hay utilidades dibujadas.': 'There are no drawn utilities yet.',
    'UTILIDADES (lo dibujado)': 'UTILITIES (what is drawn)',
    'PLANOS DEL PDF (fondo)': 'PDF PLANS (background)',
    'Ver solo esta': 'Show only this one',
    'Capas · {n} apagada(s)': 'Layers · {n} off',
    'Capas: encender y apagar las utilidades dibujadas y los planos de fondo de cada PDF, como en AutoCAD. Solo cambia lo que se ve: el DXF sale completo.':
        'Layers: turn the drawn utilities and the background plans of each PDF on and off, as in AutoCAD. Only what is shown changes: the DXF is exported complete.',
    '{n} utilidades de {t} dibujadas': '{n} {t} utilities drawn',
    '{n} hoja(s)': '{n} sheet(s)',
    'Plano original del PDF: {pdf}': 'Original plan of the PDF: {pdf}',
    'Capa encendida: {c}.': 'Layer on: {c}.',
    'Capa apagada: {c}.': 'Layer off: {c}.',
    'Solo a la vista: {c}.': 'Only on screen: {c}.',
    'Todas las capas encendidas.': 'All layers on.',
    'Cargando las marcas del plano… {p} %': 'Loading the plan marks… {p} %',
    'Leyendo los trazos de las capas de {u}…': 'Reading the strokes of the {u} layers…',
    'Reconstruyendo las líneas de la capa {c}…': 'Rebuilding the lines of layer {c}…',
    'Midiendo las bóvedas y buzones y uniendo sus líneas…': 'Measuring vaults and manholes and joining their lines…',
    '{texto} ({i} de {n})': '{texto} ({i} of {n})',
    'Dibujando cada hoja en la hoja compuesta…': 'Drawing each sheet in the composed sheet…',
    'Minimapa de las hojas': 'Sheet minimap',
    'Mostrar el minimapa': 'Show the minimap',
    'Buzón: hace falta una línea de gravedad o conduit (agua y gas van a presión y no llevan buzones).': 'Manhole: it needs a gravity or conduit line (water and gas are pressure networks and have no manholes).',
    'Minimizar el minimapa': 'Minimize the minimap',
    'En una hoja compuesta, el esquema de sus hojas abajo a la izquierda: clic = ir a esa hoja.': 'On a composed sheet, the layout of its sheets at the bottom left: click = go to that sheet.',
    'Marcas de las hojas': 'Sheet marks',
    'En una hoja compuesta, el borde y el código de cada hoja, tenues, sobre el plano. No se exportan ni tapan nada.': 'On a composed sheet, the outline and code of each sheet, faint, over the plan. They are not exported and cover nothing.',
    'Quitar la curva (vuelve a ser un vértice)':
        'Remove the curve (back to a vertex)',
    'Convertir este vértice en curva':
        'Convert this vertex into a curve',
    'Vértice convertido en curva {cod} (radio automático: cámbialo en el panel).':
        'Vertex converted into curve {cod} (automatic radius: change it in the panel).',
    'Curva quitada: vuelve a ser un vértice simple.':
        'Curve removed: it is a plain vertex again.',
    '{a}° · {l} ft':
        '{a}° · {l} ft',
    'Unión con la utilidad #{n} a {a}: no sigue el paso de 0.25° (el más cercano: {c}).':
        'Joint with utility #{n} at {a}: does not follow the 0.25° step (nearest: {c}).',
    'Quiebre de {a}: no sigue el paso de 0.25° (el más cercano: {c}).':
        'Bend of {a}: does not follow the 0.25° step (nearest: {c}).',
    'Ángulo fuera del paso de 0.25°':
        'Angle off the 0.25° step',
    # Diámetro según la IA (ia/diametro_ia.py, ui/ventana/ventana_diametro_ia.py, 2026-10-29)
    'su guía llega a ESTA línea':
        'its leader reaches THIS line',
    'su guía llega a esta línea y a otra casi igual de cerca':
        'its leader reaches this line and another one almost as close',
    'su guía llega a OTRA línea (capa {c})':
        'its leader reaches ANOTHER line (layer {c})',
    'su guía llega a la tinta de otra utilidad ({u})':
        'its leader reaches the ink of another utility ({u})',
    'su guía no llega a ninguna línea':
        'its leader reaches no line',
    'su guía no toca ninguna línea: termina a {d} pt de esta línea':
        'its leader touches no line: it ends {d} pt from this line',
    'sin guía':
        'no leader',
    'diámetro {d}':
        'diameter {d}',
    'material {m}':
        'material {m}',
    'el texto nombra: {u}':
        'the text names: {u}',
    'el texto no nombra utilidad':
        'the text names no utility',
    'a {d} pt de la línea':
        '{d} pt from the line',
    'rótulo de unión o estación':
        'join or station label',
    '{n} conductos':
        '{n} conduits',
    'la normativa lo permite':
        'the standards allow it',
    'la normativa NO lo permite':
        'the standards do NOT allow it',
    'Línea a revisar (en la imagen, en MAGENTA):':
        'Line to check (in MAGENTA in the image):',
    'utilidad: {u}':
        'utility: {u}',
    'capa: {c}':
        'layer: {c}',
    'estado según la capa: {e}':
        'status from the layer: {e}',
    'largo: {l} ft':
        'length: {l} ft',
    'sus paredes dibujadas miden {w}':
        'its drawn walls measure {w}',
    'los perfiles de los laterales que cruza dicen {v}':
        'the profiles of the laterals it crosses say {v}',
    'Rótulos con diámetro junto a esta línea:':
        'Labels with a diameter next to this line:',
    'Correcciones del equipo en casos parecidos (tenlas en cuenta):':
        'Team corrections in similar cases (take them into account):',
    'La IA no dio una respuesta que se pueda leer.':
        'The AI did not give a readable answer.',
    'La IA eligió un rótulo que no existe ({id}).':
        'The AI chose a label that does not exist ({id}).',
    'El rótulo {id} es de varios conductos, no el diámetro de una tubería.':
        'Label {id} is for several conduits, not the diameter of one pipe.',
    'El rótulo {id} es de otra utilidad.':
        'Label {id} belongs to another utility.',
    'La guía del rótulo {id} llega a otra línea.':
        'The leader of label {id} reaches another line.',
    'La normativa no permite {d} en esta utilidad.':
        'The standards do not allow {d} for this utility.',
    'La guía del rótulo {id} llega a esta línea y a otra: no se sabe de cuál es.':
        'The leader of label {id} reaches this line and another one: it is not known which it belongs to.',
    'La IA no está segura.':
        'The AI is not sure.',
    'No hay rótulos con diámetro junto a esta línea en la hoja.':
        'There are no labels with a diameter next to this line on the sheet.',
    'Ningún rótulo junto a esta línea puede ser suyo: son de otra utilidad, van a otra línea o son de varios conductos.':
        'No label next to this line can be its own: they belong to another utility, go to another line or are for several conduits.',
    'Pedido detenido.':
        'Request stopped.',
    'Las dos revisiones de la IA no eligieron el mismo rótulo.':
        "The AI's two checks did not choose the same label.",
    'En una línea de {u} (capa {c}) la IA eligió «{r}» y el equipo dijo que NO era su diámetro.':
        'On a {u} line (layer {c}) the AI chose “{r}” and the team said it was NOT its diameter.',
    'Vuelve a reconocer la hoja para que la IA pueda revisar esta línea.':
        'Recognize the sheet again so the AI can check this line.',
    'La IA puede revisar los rótulos junto a esta línea y sugerir su diámetro.':
        'The AI can check the labels next to this line and suggest its diameter.',
    'La IA sugiere {d}':
        'The AI suggests {d}',
    'confianza {c}':
        'confidence {c}',
    'Rótulo {id}: «{texto}»':
        'Label {id}: “{texto}”',
    'Usar {d}':
        'Use {d}',
    'La IA no encontró el diámetro de esta línea con certeza.':
        "The AI could not find this line's diameter with certainty.",
    'Pista: {p}':
        'Hint: {p}',
    'Revisando con la IA… {s} s':
        'Checking with the AI… {s} s',
    'La IA no respondió: {e}':
        'The AI did not respond: {e}',
    'Diámetro según la IA':
        'Diameter according to the AI',
    'La familia de esta utilidad no tiene un tamaño de {d}: elige el tamaño en el panel.':
        "This utility's family has no {d} size: choose the size in the panel.",
    'Marcado como incorrecto: el equipo dijo que ese rótulo no es su diámetro.':
        'Marked as incorrect: the team said that label is not its diameter.',
    'No es correcto':
        'Not correct',
    # Diámetro del plano en el editor (nucleo/diametro_plano.py, 2026-10-22)
    'Diámetro del plano':
        'Diameter from the plan',
    'Diámetro no encontrado en el plano: queda {d} por defecto. Elige el suyo, o aprueba el aviso para dejarlo.':
        'Diameter not found on the plan: it keeps the default {d}. Pick its own, or approve the notice to keep it.',
    'sus rótulos dicen {lista}':
        'its labels say {lista}',
    'los perfiles de los laterales que cruza dicen {lista}':
        'the profiles of the laterals it crosses say {lista}',
    'la planta dice {a} y el perfil de un lateral que cruza dice {b}':
        'the plan says {a} and the profile of a lateral it crosses says {b}',
    'el rótulo dice {r} y sus paredes miden {w}':
        'the label says {r} and its walls measure {w}',
    'sus paredes miden {w}, pero ningún rótulo de la hoja dice si son las de adentro o las de afuera del tubo':
        'its walls measure {w}, but no label on the sheet tells whether they are the inside or the outside of the pipe',
    'Diámetro dudoso en el plano: {motivo}. Queda {d} por defecto hasta que elijas el suyo.':
        'Doubtful diameter on the plan: {motivo}. It keeps the default {d} until you pick its own.',
    'Rótulos: {textos}.':
        'Labels: {textos}.',
    'Perfiles de las hojas de origen':
        'Profiles of the source sheets',
    'Salió del modo (Enter)':
        'Left the mode (Enter)',
    'Modo: dibujar utilidad (ángulos en pasos de 0.25°)  ·  Enter finaliza; otro Enter sale':
        'Mode: draw utility (angles in 0.25° steps)  ·  Enter finishes; another Enter exits',
    'Aplicar: finaliza utilidad/zona (otro Enter sale del modo), o agrega texto/edición':
        'Apply: finish utility/zone (another Enter exits the mode), or add text/edit',
    'Finaliza línea/zona; en editar, elimina el vértice':
        'Finish line/zone; in edit mode, delete the vertex',
    '{a}° · giro {g}° {v} · {l} ft':
        '{a}° · turn {g}° {v} · {l} ft',
    'giro {g}° {v} · {l1} / {l2} ft':
        'turn {g}° {v} · {l1} / {l2} ft',
    'giro {g}° {v} · {l} ft':
        'turn {g}° {v} · {l} ft',
    'Vértice {k} elegido: «Cambiar a curva» en el panel (o clic derecho sobre él).':
        'Vertex {k} selected: «Change to curve» in the panel (or right-click it).',
    'Vértice {k} de esta utilidad':
        'Vertex {k} of this utility',
    'Cambiar a curva':
        'Change to curve',
    'Convierte el vértice elegido en una curva (radio automático: se cambia en el panel de Curvas).':
        'Turns the selected vertex into a curve (automatic radius: change it in the Curves panel).',
    'Reducción':
        'Reducer',
    'Ángulos y pendientes por tramo':
        'Angles and slopes per segment',
    'Rótulos sobre cada utilidad: la pendiente de cada tramo y el ángulo de cada quiebre':
        'Labels on each utility: the slope of each segment and the angle of each bend',
    'Pendiente: {p} %':
        'Slope: {p} %',
    'Pendiente por tramo: {tramos}':
        'Slope per segment: {tramos}',
    'Preparando el DXF…':
        'Preparing the DXF…',
    'Actualizando conflictos y avisos…':
        'Updating conflicts and warnings…',
    'Reusando el plano ya digitalizado…':
        'Reusing the already digitized plan…',
    'Leyendo el plano digitalizado…':
        'Reading the digitized plan…',
    'Exportación cancelada.':
        'Export cancelled.',
    'Agregar un diámetro personalizado (pulgadas) para esta utilidad':
        'Add a custom diameter (inches) for this utility',
    'Diámetro personalizado':
        'Custom diameter',
    'Diámetro (pulgadas):':
        'Diameter (inches):',
    'Diámetro {d} elegido para esta utilidad.':
        'Diameter {d} chosen for this utility.',
    'Hoja compuesta: {n} estilo(s) de las piezas se reconocen junto con el mismo tipo de tubería de las demás (la leyenda de cada hoja dice que es la misma línea).': 'Composed sheet: {n} style(s) of the pieces are recognized together with the same pipe type of the others (the legend of each sheet says it is the same line).',
    'Costuras de la hoja compuesta: {n} — la tubería sigue de una hoja a la otra (sus puntas quedaban a menos de {d} pt).': 'Seams of the composed sheet: {n} — the pipe continues from one sheet to the next (its ends were less than {d} pt apart).',
    # Informe automático (2026-10-23)
    'y': 'and',
    'Abrir el informe': 'Open the report',
    'Ajusta las cotas del tramo para llegar a la pendiente pedida.': 'Adjust the elevations of the segment to reach the required slope.',
    'Alarga el tramo entre los dos codos o junta los codos en uno.': 'Lengthen the segment between the two bends or merge the bends into one.',
    'Aleja las dos utilidades o cambia sus cotas para cumplir la separación.': 'Move the two utilities apart or change their elevations to meet the separation.',
    'Anexo: todos los conflictos y avisos': 'Appendix: all conflicts and warnings',
    'Aprobado por {u} el {fecha}.': 'Approved by {u} on {fecha}.',
    'Arma un informe en Word con las fichas de cada zona del plano, sus capturas y la explicación de cada conflicto y aviso.': 'Builds a Word report with the sheets of each zone of the plan, their captures and the explanation of each conflict and warning.',
    'Armando el anexo: {i} de {n} filas': 'Building the appendix: {i} of {n} rows',
    'Armando el informe…': 'Building the report…',
    'Avisos aprobados': 'Approved warnings',
    'Avisos de normativa pendientes': 'Pending design-standard warnings',
    'Avisos de normativa: {n} (pendientes: {p}, aprobados: {a}, informativos: {i}).': 'Design-standard warnings: {n} (pending: {p}, approved: {a}, informational: {i}).',
    'Avisos informativos': 'Informational warnings',
    'Cambia el diámetro a uno de los permitidos o revisa el tipo de la utilidad.': 'Change the diameter to an allowed one or check the utility type.',
    'Cambia el material al permitido por la norma.': 'Change the material to the one allowed by the standard.',
    'Cambia el radio de la curva al permitido.': 'Change the curve radius to the allowed one.',
    'Cambia la cota de una de las dos tuberías para que pasen a distinta altura, o únelas si debían conectarse.': 'Change the elevation of one of the two pipes so they pass at different heights, or join them if they should connect.',
    'Cantidad': 'Count',
    'Capturando el plano: zona {i} de {n}': 'Capturing the plan: zone {i} of {n}',
    'Capturando la vista 3D: zona {i} de {n}': 'Capturing the 3D view: zone {i} of {n}',
    'Capturas de cada zona': 'Captures of each zone',
    'Concepto': 'Item',
    'Confirma que se cumple la condición de uso indicada.': 'Confirm that the stated condition of use is met.',
    'Conflictos ({n})': 'Conflicts ({n})',
    'Conflictos en el dibujo: {n}.': 'Conflicts in the drawing: {n}.',
    'Conflictos y avisos': 'Conflicts and warnings',
    'Contenido: {c}.': 'Content: {c}.',
    'Da espacio a la unión o ajusta las cotas para que la pieza entre.': 'Give the joint room or adjust the elevations so the fitting fits.',
    'Dibujando el mapa general…': 'Drawing the overview map…',
    'El informe no lleva capturas 3D: {m}.': 'The report has no 3D captures: {m}.',
    'Fecha: {f}': 'Date: {f}',
    'Fichas por zona': 'Sheets by zone',
    'Fuente: {f}.': 'Source: {f}.',
    'Generar informe…': 'Generate report…',
    'Guardando el Word…': 'Saving the Word file…',
    'Guardar informe': 'Save report',
    'Iguala la cota de llegada y la de salida en ese vértice, o pon un buzón si el escalón es intencional.': 'Match the incoming and outgoing elevations at that vertex, or add a manhole if the step is intentional.',
    'Informe automático': 'Automatic report',
    'Informe automático…': 'Automatic report…',
    'Informe de conflictos y normativas': 'Conflicts and design-standards report',
    'Informe guardado: {n} conflictos y avisos en {z} zonas.\n{ruta}': 'Report saved: {n} conflicts and warnings in {z} zones.\n{ruta}',
    'Juntando conflictos y avisos…': 'Gathering conflicts and warnings…',
    'La conexión vertical debe ser vertical: iguala la ubicación en planta de sus dos puntas.': 'The vertical connection must be vertical: match the plan location of its two ends.',
    'La redacción con IA («{p}») aún no está disponible: se usaron plantillas.': 'AI writing («{p}») is not available yet: templates were used.',
    'La vista 3D se arma si no está abierta: con proyectos grandes tarda más.': 'The 3D view is built if it is not open: with large projects it takes longer.',
    'Las tuberías se tocan sin conexión: sepáralas en altura o en planta.': 'The pipes touch without a connection: separate them in height or in plan.',
    'Mapa general': 'Overview map',
    'Nivel': 'Level',
    'No hay conflictos en el dibujo.': 'There are no conflicts in the drawing.',
    'No hay utilidades: no hay nada que informar.': 'There are no utilities: nothing to report.',
    'No se pudo guardar el informe: ¿está abierto en Word? Ciérralo y vuelve a intentar.': 'The report could not be saved: is it open in Word? Close it and try again.',
    'Normativas ({n} avisos)': 'Design standards ({n} warnings)',
    'Plano (2D)': 'Plan (2D)',
    'Plano y vista 3D': 'Plan and 3D view',
    'Proyecto: {p}': 'Project: {p}',
    'Qué': 'What',
    'Qué hacer: {c}': 'What to do: {c}',
    'Qué incluir': 'What to include',
    'Redactando las fichas: zona {i} de {n}': 'Writing the sheets: zone {i} of {n}',
    'Reparte las conexiones: en un mismo punto Civil 3D no arma más de cuatro tuberías.': 'Spread the connections: Civil 3D does not join more than four pipes at one point.',
    'Resumen': 'Summary',
    'Revisa el accesorio, el tipo de la línea principal y los diámetros de principal y ramal.': 'Check the fitting, the type of the main line and the diameters of main and branch.',
    'Revisa el amperaje y el largo de la línea y elige el diámetro que pide la tabla.': 'Check the amperage and the length of the line and choose the diameter the table asks for.',
    'Revisa el largo de la tubería o pártela con un buzón.': 'Check the pipe length or split it with a manhole.',
    'Revisa el trazo: la tubería vuelve casi sobre sí misma.': 'Check the route: the pipe almost doubles back on itself.',
    'Revisa la ubicación de los buzones y las cotas en ellos.': 'Check the location of the manholes and the elevations at them.',
    'Se muestran {n} de {total}. El detalle completo está en la Tabla de datos (Herramientas → Tabla de datos → Exportar a Excel).': 'Showing {n} of {total}. The full detail is in the Data table (Tools → Data table → Export to Excel).',
    'Separa las dos redes o confirma que deben unirse.': 'Separate the two networks or confirm they should be joined.',
    'Todo el dibujo con las zonas numeradas.': 'The whole drawing with the numbered zones.',
    'Utilidades involucradas: {u}.': 'Utilities involved: {u}.',
    'Utilidades revisadas': 'Utilities checked',
    'Utilidades revisadas: {n}.': 'Utilities checked: {n}.',
    'Utilidades sin tipo': 'Utilities without type',
    'Utilidades sin tipo asignado: {n} (sin tipo no se revisan las reglas propias de cada tipo).': 'Utilities without an assigned type: {n} (without a type, the rules specific to each type are not checked).',
    'Zona': 'Zone',
    'Zona {z}': 'Zone {z}',
    'Zona {z} en el plano.': 'Zone {z} in the plan.',
    'Zona {z} en la vista 3D.': 'Zone {z} in the 3D view.',
    'Zona {z} · conflictos: {c} · avisos: {a}.': 'Zone {z} · conflicts: {c} · warnings: {a}.',
    'Zonas del plano con algo que revisar: {n}; cada una tiene su ficha más abajo.': 'Zones of the plan with something to check: {n}; each one has its sheet below.',
    'aprobado': 'approved',
    'conflictos': 'conflicts',
    'la escena 3D está vacía': 'the 3D scene is empty',
    'la vista 3D tardó demasiado en armarse': 'the 3D view took too long to build',
    'no se pudo iniciar OpenGL: {e}': 'OpenGL could not be started: {e}',
    'normativas': 'design standards',
    'sin pantalla no hay vista 3D': 'without a screen there is no 3D view',
    '{u}: {m}': '{u}: {m}',
    # IA: Pregúntale al proyecto e informe con IA (2026-10-23)
    '&IA': '&AI',
    'Abrir carpeta de aprendizaje': 'Open learning folder',
    'Además, en «zona», 1 o 2 frases que resuman lo que hay en la zona {z} ({n} conflictos y avisos en total).': 'Also, in «zona», 1 or 2 sentences summarizing what is in zone {z} ({n} conflicts and warnings in total).',
    'Anotado para este proyecto: {n}': 'Noted for this project: {n}',
    'Ante «{p}», esta respuesta fue útil: {t}': 'For «{p}», this answer was useful: {t}',
    'Ante «{p}», la respuesta correcta es: {t}': 'For «{p}», the correct answer is: {t}',
    "Aprende en <a href='#'>{c}</a> · {n} enseñanzas": "Learns in <a href='#'>{c}</a> · {n} lessons",
    'Avisos de normativa (N-n): {n} (pendientes {p}, aprobados {a}, informativos {i}).': 'Design-standard warnings (N-n): {n} (pending {p}, approved {a}, informational {i}).',
    'Buscando modelos…': 'Looking for models…',
    'Buscar modelos': 'Find models',
    'Claude (próximamente)': 'Claude (coming soon)',
    'Configurar IA': 'Configure AI',
    'Configurar IA…': 'Configure AI…',
    'Conflictos (C-n): {n}.': 'Conflicts (C-n): {n}.',
    'Conflictos y avisos que vienen al caso ({n} de {total})': 'Relevant conflicts and warnings ({n} of {total})',
    'Contenido de la zona: {c}': 'Zone content: {c}',
    'Corregida: la IA lo tendrá en cuenta': 'Corrected: the AI will take it into account',
    'Corregir la respuesta': 'Correct the answer',
    'Datos del proyecto': 'Project data',
    'Detener': 'Stop',
    'El servidor de IA respondió {c}: {d}': 'The AI server answered {c}: {d}',
    'Enseñanzas del equipo para este proyecto': "Team's lessons for this project",
    'Enseñarle algo a la IA': 'Teach the AI something',
    'Enseñarle algo…': 'Teach it something…',
    'Enviar': 'Send',
    'Escribe tu pregunta… (Enter envía; Mayús+Enter, otra línea)': 'Type your question… (Enter sends; Shift+Enter, new line)',
    'Fichas:': 'Sheets:',
    'Formato de respuesta: {f}': 'Answer format: {f}',
    'Guardar': 'Save',
    'IA: {m} · {u}': 'AI: {m} · {u}',
    'Indicaciones del equipo para este proyecto:': "Team's instructions for this project:",
    'La IA no está configurada.': 'The AI is not configured.',
    'La IA no está disponible ({e}): se usó lo ya redactado y plantillas.': 'The AI is not available ({e}): what was already written and templates were used.',
    'La IA no respondió en parte: {e}': 'The AI partly did not answer: {e}',
    'La IA redacta el informe automático y responde «Pregúntale al proyecto». Los números siempre los pone la app; si la IA no responde, se usan plantillas.': 'The AI writes the automatic report and answers «Ask the project». The numbers always come from the app; if the AI does not answer, templates are used.',
    'La IA redacta el informe: parte {i} de {n}': 'The AI writes the report: part {i} of {n}',
    'Marcada como no útil': 'Marked as not useful',
    'Marcada como útil': 'Marked as useful',
    'Modelo': 'Model',
    'Modelos en el servidor: {n}.': 'Models on the server: {n}.',
    'No se pudo conectar con el servidor de IA ({u}): {e}': 'Could not connect to the AI server ({u}): {e}',
    'Nota del equipo: {t}': 'Team note: {t}',
    'Pedidos a la vez': 'Requests at once',
    'Pedidos a la vez al redactar el informe. Más es más rápido si el servidor lo permite (OLLAMA_NUM_PARALLEL).': 'Requests at once when writing the report. More is faster if the server allows it (OLLAMA_NUM_PARALLEL).',
    'Por clase: {c}.': 'By kind: {c}.',
    'Pregunta': 'Question',
    'Pregunta lo que quieras sobre este proyecto: conflictos, normativas, utilidades, zonas. La IA responde solo con los datos del proyecto y cada código (C-12, AGUA-5) lleva al plano. También responde cómo usar la app («¿Cómo exporto a Civil 3D?») con el manual de usuario.': 'Ask anything about this project: conflicts, design standards, utilities, zones. The AI answers only with the project data and each code (C-12, AGUA-5) takes you to the plan. It also answers how to use the app («How do I export to Civil 3D?») with the user manual.',
    'Pregúntale al proyecto': 'Ask the project',
    'Pregúntale al proyecto: la IA responde con los datos del proyecto (Ctrl+Shift+I)': 'Ask the project: the AI answers with the project data (Ctrl+Shift+I)',
    'Pregúntale al proyecto…': 'Ask the project…',
    'Probando la IA…': 'Testing the AI…',
    'Probar': 'Test',
    'Quién responde': 'Who answers',
    'Redacta el resumen ejecutivo del informe (3 a 5 frases) con estos conteos.': 'Write the executive summary of the report (3 to 5 sentences) with these counts.',
    'Redacta las fichas de la zona {z}.': 'Write the sheets of zone {z}.',
    'Redactado con IA ({m}): {n} fichas; con plantilla: {p}.': 'Written with AI ({m}): {n} sheets; with template: {p}.',
    'Responde en {s} s con «{m}».': 'Answers in {s} s with «{m}».',
    'Resume lo que hay en la zona 1.': 'Summarize what is in zone 1.',
    'Revisa estas cifras: no salen de los datos del proyecto: {c}': 'Check these figures: they are not in the project data: {c}',
    'Servidor': 'Server',
    'Servidor propio (Ollama)': 'Own server (Ollama)',
    'Sin IA (plantillas)': 'No AI (templates)',
    'Tú': 'You',
    'Una regla o un dato de este proyecto que la IA debe tener en cuenta (por ejemplo: «los cruces con drenaje se resuelven bajando el agua»).': 'A rule or fact of this project the AI must take into account (for example: «crossings with storm drain are solved by lowering the water line»).',
    'Una regla o un dato de este proyecto que la IA debe tener en cuenta.': 'A rule or fact of this project the AI must take into account.',
    'Unidades: pies (ft); diámetros en pulgadas (in).': 'Units: feet (ft); diameters in inches (in).',
    'Utilidades que vienen al caso ({n} de {total})': 'Relevant utilities ({n} of {total})',
    'Utilidades: {n}.': 'Utilities: {n}.',
    'Zonas: {z}.': 'Zones: {z}.',
    'abandonadas {a}': 'abandoned {a}',
    'cota {z} ft': 'elevation {z} ft',
    'cotas {a} → {b} ft': 'elevations {a} → {b} ft',
    'diferencia {v} ft': 'difference {v} ft',
    'diámetros (in) {d}': 'diameters (in) {d}',
    'el modelo «{m}» no está en el servidor': 'the model «{m}» is not on the server',
    'fuente: {f}': 'source: {f}',
    'informativo': 'informational',
    'largo total {l} ft': 'total length {l} ft',
    'largo {l} ft': 'length {l} ft',
    'materiales {m}': 'materials {m}',
    'nombre «{n}»': 'name «{n}»',
    'pendiente': 'pending',
    'pendiente {s} %': 'slope {s} %',
    'sin tipo': 'no type',
    'tipos {t}': 'types {t}',
    'usó {n} enseñanzas': 'used {n} lessons',
    'zona {z}': 'zone {z}',
    'zona {z} ({n})': 'zone {z} ({n})',
    '{m} · {s} s': '{m} · {s} s',
    '{n} textos de la IA no pasaron la revisión de cifras y salieron con plantilla.': '{n} AI texts did not pass the figures check and used the template.',
    '{u} ({c}): {n} utilidades': '{u} ({c}): {n} utilities',
    '¿Cuál es la respuesta correcta? La IA la usará en las próximas preguntas de este proyecto.': 'What is the correct answer? The AI will use it in the next questions of this project.',
    '¿Cuántos conflictos hay y dónde están?': 'How many conflicts are there and where are they?',
    '¿Qué conflicto conviene resolver primero y por qué?': 'Which conflict should be solved first and why?',
    '¿Qué utilidades no cumplen la normativa?': 'Which utilities do not meet the design standards?',
    'Ø {d} in': 'Ø {d} in',
    # IA: resolver conflictos y explicar normativas (2026-10-23)
    '(ninguna)': '(none)',
    '(y resuelve {n} más)': '(and solves {n} more)',
    'Aplicado en {c}: {p} (Ctrl+Z para deshacer).': 'Applied to {c}: {p} (Ctrl+Z to undo).',
    'Bajar {u} {d} ft (todas sus cotas: la pendiente no cambia) para pasar por debajo de {o}': 'Lower {u} {d} ft (all its elevations: the slope does not change) to pass under {o}',
    'Conflicto:': 'Conflict:',
    'Crearía: {p}': 'Would create: {p}',
    'Elige una regla de la tabla.': 'Choose a rule in the table.',
    'En {u}, poner la cota de llegada del vértice igual a la de salida: {z} ft.': 'On {u}, set the incoming elevation of the vertex equal to the outgoing one: {z} ft.',
    'En {u}, poner la cota de salida del vértice igual a la de llegada: {z} ft.': 'On {u}, set the outgoing elevation of the vertex equal to the incoming one: {z} ft.',
    'En «{tit}» ({c}) se aplicó: {txt}': 'For «{tit}» ({c}) this was applied: {txt}',
    'Este conflicto se arregla cambiando el dibujo; la app no tiene una propuesta automática.': 'This conflict is fixed by changing the drawing; the app has no automatic proposal.',
    'Explica esta regla de la tabla de normativas:': 'Explain this rule of the design-standards table:',
    'Explicar con IA': 'Explain with AI',
    'Guardada: no se volvió a preguntar a la IA.': 'Saved: the AI was not asked again.',
    'La IA escribió cifras que no están en los datos: recomendación de la app.': 'The AI wrote figures that are not in the data: recommendation of the app.',
    'La IA está pensando…': 'The AI is thinking…',
    'La IA explica la regla elegida en palabras sencillas. La respuesta se guarda: la misma regla no se vuelve a pedir.': 'The AI explains the chosen rule in plain words. The answer is saved: the same rule is not asked again.',
    'La IA no respondió ({e}): recomendación de la app.': 'The AI did not answer ({e}): recommendation of the app.',
    'La app recomienda {id}: {txt} Resuelve el conflicto sin crear otros problemas.': 'The app recommends {id}: {txt} It solves the conflict without creating other problems.',
    'La regla tiene celdas sin completar o que no se entienden.': 'The rule has empty or unreadable cells.',
    'La regla tiene celdas sin completar o que no se entienden: guárdala primero.': 'The rule has empty or unreadable cells: save it first.',
    'Lo que el equipo decidió antes en este proyecto:': 'What the team decided before in this project:',
    'Ninguna propuesta automática resuelve el conflicto sin crear otros problemas.': 'No automatic proposal solves the conflict without creating other problems.',
    'No resuelve el conflicto': 'Does not solve the conflict',
    'Propuestas de la app (ya probadas en una copia del proyecto):': "App's proposals (already tested on a copy of the project):",
    'Pulsa «Explicar con IA» para leerla en palabras sencillas.': 'Press «Explain with AI» to read it in plain words.',
    'Recomendación': 'Recommendation',
    'Redactada por la IA y guardada.': 'Written by the AI and saved.',
    'Redactada por la IA.': 'Written by the AI.',
    'Resolver conflictos': 'Solve conflicts',
    'Resolver conflictos…': 'Solve conflicts…',
    'Resolver {c}: ver soluciones…': 'Solve {c}: see solutions…',
    'Resuelve el conflicto sin crear otros problemas': 'Solves the conflict without creating other problems',
    'Revisa estas cifras: no están en la regla: {c}': 'Check these figures: they are not in the rule: {c}',
    'Sin IA configurada (IA → Configurar IA…): la regla leída por la app.': 'No AI configured (AI → Configure AI…): the rule as read by the app.',
    'Sin IA configurada: la regla leída por la app.': 'No AI configured: the rule as read by the app.',
    'Sin IA: recomendación de la app.': 'No AI: recommendation of the app.',
    'Solo los que tienen solución automática': 'Only those with an automatic solution',
    'Solución aplicada antes: {t}': 'Solution applied before: {t}',
    'Subir {u} {d} ft (todas sus cotas: la pendiente no cambia) para pasar por encima de {o}': 'Raise {u} {d} ft (all its elevations: the slope does not change) to pass over {o}',
    'dejando {s} ft libres (normativa)': 'leaving {s} ft of clearance (design standard)',
    'revisa el dibujo y las cotas en ese punto.': 'check the drawing and the elevations at that point.',
    'separa la unión entre {a} y {b}': 'separates the joint between {a} and {b}',
    '¿Qué significa esta regla?': 'What does this rule mean?',
    # IA: chat con pautas UX/UI (2026-10-23)
    'Letra más chica (Ctrl+-)': 'Smaller text (Ctrl+-)',
    'Letra más grande (Ctrl++)': 'Larger text (Ctrl++)',
    'Conversación': 'Conversation',
    'Tu pregunta': 'Your question',
    'IA sin configurar': 'AI not configured',
    'Primero configura la IA para poder preguntar.': 'Configure the AI first to be able to ask.',
    'La IA no está configurada: elige el servidor y el modelo para poder preguntar.': 'The AI is not configured: choose the server and the model to be able to ask.',
    'Detener la respuesta (Esc)': 'Stop the answer (Esc)',
    'Enviar la pregunta (Enter)': 'Send the question (Enter)',
    'Copiada': 'Copied',
    'Útil: la IA lo tendrá en cuenta': 'Useful: the AI will take it into account',
    'No útil: la IA no volverá a usarla': 'Not useful: the AI will not use it again',
    'Corregir la respuesta…': 'Correct the answer…',
    'Copiar la respuesta': 'Copy the answer',
    'Volver a preguntar': 'Ask again',
    'Preguntar esto': 'Ask this',
    '¿Por qué ocurre {c} y cómo se resuelve?': 'Why does {c} happen and how is it solved?',
    'Más detalle sobre {c}': 'More detail about {c}',
    'Pensando… {s} s': 'Thinking… {s} s',
    'IA': 'AI',
    'escribiendo…': 'writing…',
    'Según los datos del proyecto': 'According to the project data',
    # IA en el manual e informe en segundo plano (2026-10-23)
    'El manual no habla de eso. Prueba con otras palabras o mira el índice.': 'The manual does not cover that. Try other words or look at the contents.',
    'Fragmentos del manual:': 'Manual excerpts:',
    'Pregunta del usuario:': 'User question:',
    '¿Cómo hago…?': 'How do I…?',
    'Escribe qué quieres hacer, por ejemplo: ¿cómo exporto a Civil 3D?': 'Type what you want to do, for example: how do I export to Civil 3D?',
    'Preguntar a la IA': 'Ask the AI',
    'Detenida.': 'Stopped.',
    'Respuesta guardada: no se volvió a preguntar a la IA.': 'Saved answer: the AI was not asked again.',
    'Sin IA configurada (IA → Configurar IA…): estos capítulos hablan de eso.': 'No AI configured (AI → Configure AI…): these chapters cover it.',
    'La IA no respondió ({e}): estos capítulos hablan de eso.': 'The AI did not answer ({e}): these chapters cover it.',
    'Según el manual de usuario.': 'According to the user manual.',
    'En el manual:': 'In the manual:',
    'Ya se está armando un informe: espera a que termine o cancélalo.': 'A report is already being built: wait for it to finish or cancel it.',
    'No se pudo armar el informe: {e}': 'The report could not be built: {e}',
    'Se canceló el informe.': 'The report was canceled.',
    'No se pudo leer o escribir: {e}': 'Could not read or write: {e}',
    'Desarrollo (pruebas del equipo)': 'Development (team testing)',
    'Producción (lo que va al cliente)': 'Production (what goes to the client)',
    'Entorno de entrenamiento': 'Training environment',
    'Lo que aprende se guarda en: {r}': 'What it learns is saved in: {r}',
    'También usa (solo lectura): {r}': 'It also uses (read-only): {r}',
    # IA: pasar a producción (2026-10-24)
    'Corrección': 'Correction',
    'Valoración': 'Rating',
    'Solución aplicada': 'Applied solution',
    'Enseñanza': 'Teaching',
    'Proyecto': 'Project',
    'Quién': 'Who',
    'Fecha': 'Date',
    'En producción': 'In production',
    'Útil': 'Useful',
    'No útil': 'Not useful',
    'Pasar a producción': 'Move to production',
    'Pasar a producción…': 'Move to production…',
    'Marca las enseñanzas de desarrollo que deben ir al cliente y pulsa «Pasar a producción». Producción es el archivo que va en el instalador: el programa del cliente lo usa pero no lo cambia. Las conversaciones no pasan.': "Check the development teachings that must go to the client and press «Move to production». Production is the file that ships in the installer: the client's program uses it but does not change it. Conversations are not moved.",
    'Desarrollo: {d}\nProducción: {p}': 'Development: {d}\nProduction: {p}',
    'Solo las que faltan': 'Only the missing ones',
    'Marcar todas': 'Check all',
    'Desmarcar todas': 'Uncheck all',
    'Quitar de producción': 'Remove from production',
    'Pasar también los textos ya redactados de normativas y del manual ({n})': 'Also move the already written texts of standards and the manual ({n})',
    'No se pudo leer: {e}': 'Could not read: {e}',
    'No se pudo escribir producción: {e}': 'Could not write production: {e}',
    'Pasaron a producción: {n} enseñanzas y {k} textos. Súbelo con Git para que vaya en el próximo instalador.': 'Moved to production: {n} teachings and {k} texts. Push it with Git so it goes in the next installer.',
    'Salieron de producción: {n} enseñanzas.': 'Removed from production: {n} teachings.',
    'Usar área sugerida': 'Use suggested area',
    'Marca el área sugerida en la hoja; ajusta sus lados si hace falta y pulsa «Tomar área»': 'Marks the suggested area on the sheet; adjust its sides if needed and press «Take area»',
    'Otra vista': 'Another view',
    'La hoja tiene otra vista con líneas de utilidades: sugerir esa': 'The sheet has another view with utility lines: suggest that one',
    'No sugerir áreas': 'Do not suggest areas',
    'Buscando el área de la hoja que conviene tomar…': 'Looking for the area of the sheet worth taking…',
    'la vista de planta entre las match lines STA {a} y STA {b}': 'the plan view between match lines STA {a} and STA {b}',
    'la vista de planta hasta la match line STA {a}': 'the plan view up to match line STA {a}',
    'la vista de planta del plano': 'the plan view of the drawing',
    'el marco del mapa {celda}, sin leyenda ni cajetín': 'the frame of map {celda}, without legend or title block',
    'el marco del mapa, sin leyenda ni cajetín': 'the map frame, without legend or title block',
    'la vista del plano con el {p} % de las líneas de utilidades de la hoja': "the drawing view with {p} % of the sheet's utility lines",
    'la vista del plano con las líneas de utilidades': 'the drawing view with the utility lines',
    'Área sugerida marcada: {txt}. Ajusta sus lados si hace falta y pulsa «Tomar área».': 'Suggested area marked: {txt}. Adjust its sides if needed and press «Take area».',
    'Área sugerida:': 'Suggested area:',
    'Otra vista ({i}/{n})': 'Another view ({i}/{n})',
    'Sigue su borde inclinado (esquinas libres).': 'It follows its slanted border (free corners).',
    # «Agregar utilidad desde otro PDF…» (ventana_agregar, hoja_calcada)
    'Leyendo el mapa base de las hojas nuevas…': 'Reading the base map of the new sheets…',
    'Buscando dónde cae cada hoja sobre la hoja del editor…': 'Finding where each sheet falls on the editor sheet…',
    'Agregar utilidad': 'Add utility',
    'Agregar utilidad desde otro PDF…': 'Add utility from another PDF…',
    'Agregar utilidad desde otro PDF: se ubica sola sobre esta hoja por el mapa base y se reconoce como siempre':
        'Add a utility from another PDF: it places itself on this sheet by the base map and is recognized as usual',
    'Abre primero el PDF de una utilidad e impórtala: la nueva se agrega sobre esa hoja.':
        'First open the PDF of one utility and import it: the new one is added on top of that sheet.',
    'La hoja del editor es un PDF imagen/escaneo: no tiene un mapa base vectorial con el que ubicar otra utilidad.':
        'The editor sheet is an image/scanned PDF: it has no vector base map to place another utility with.',
    'No se pudo leer el PDF:\n\n{e}': 'The PDF could not be read:\n\n{e}',
    'Ninguna hoja de «{pdf}» dibuja el mismo lugar que la hoja del editor (su mapa base de lotes y calles no '
    'coincide con el de la hoja), así que no se puede ubicar sobre ella.':
        'No sheet of «{pdf}» draws the same place as the editor sheet (its base map of lots and streets does not '
        'match the sheet\'s), so it cannot be placed on it.',
    'Agregar utilidad: elige su PDF': 'Add utility: choose its PDF',
    'La hoja del editor viene de {n} PDF. ¿Agregar también estos de la misma utilidad?\n\n{lista}':
        'The editor sheet comes from {n} PDFs. Also add these of the same utility?\n\n{lista}',
    'Ubicando «{pdf}» sobre la hoja del editor…': 'Placing «{pdf}» on the editor sheet…',
    'Buscando en cada hoja el mismo mapa base (lotes, calles)': 'Looking for the same base map in each sheet (lots, streets)',
    'Agregar utilidad cancelado — el editor queda como estaba.': 'Add utility cancelled — the editor stays as it was.',
    'No se pudo ubicar el PDF sobre la hoja del editor:\n\n{e}': 'The PDF could not be placed on the editor sheet:\n\n{e}',
    'La hoja necesita más memoria de la que hay libre en el equipo.': 'The sheet needs more memory than is free on this computer.',
    '{n} de {t} hojas de la hoja del editor ubicadas en «{pdf}» por su mapa base.':
        '{n} of {t} sheets of the editor sheet found in «{pdf}» by their base map.',
    '{n} hoja(s) no coinciden con ninguna hoja del editor (su mapa base no está en la hoja) y no se usan: {lista}.':
        '{n} sheet(s) do not match any sheet of the editor (their base map is not on the sheet) and are not used: {lista}.',
    'Ninguna de las hojas elegidas coincide con la hoja del editor.': 'None of the chosen sheets matches the editor sheet.',
    'No se pudo armar la hoja con las dos utilidades:\n\n{e}': 'The sheet with both utilities could not be built:\n\n{e}',
    'Utilidad agregada a la hoja del editor': 'Utility added to the editor sheet',
    'Armando la hoja con las dos utilidades…': 'Building the sheet with both utilities…',
    'La hoja combinada no mide lo mismo que la del editor.': 'The combined sheet does not have the same size as the editor sheet.',
    # avance de la importación y de la vista previa (sin trabar la ventana con hojas grandes)
    'Poniendo cada bóveda en su línea…': 'Placing each vault on its line…',
    'Uniendo cada acometida a su tubería…': 'Joining each service tap to its pipe…',
    'Asociando cada bóveda a su estructura…': 'Matching each vault to its structure…',
    'Buscando los quiebres que entran como curva…': 'Finding the bends that become curves…',
    'Agregando las tuberías al editor…': 'Adding the pipes to the editor…',
    'Creando los buzones de sus vértices…': 'Creating the manholes at their vertices…',
    # Informe: avisos de reconocimiento aparte (2026-10-24)
    'avisos de reconocimiento': 'recognition warnings',
    'Avisos de reconocimiento (diámetro del plano)': 'Recognition warnings (plan diameter)',
    'Avisos de reconocimiento': 'Recognition warnings',
    'Lo que el reconocimiento del PDF no pudo leer con certeza (por ejemplo, el diámetro que dice el plano). No son incumplimientos de normativa: revísalos en el plano.': 'What the PDF recognition could not read with certainty (for example, the diameter the plan gives). They are not design-standard violations: check them on the plan.',
    'Avisos de reconocimiento, aparte ({n})': 'Recognition warnings, separately ({n})',
    'Lo que el reconocimiento del PDF no leyó con certeza (diámetro del plano). Va en su propia sección, no como normativa.': 'What the PDF recognition did not read with certainty (plan diameter). It goes in its own section, not as a standard.',
    # IA: UX/UI (2026-10-26)
    '¿En qué te ayudo?': 'How can I help?',
    'No hay una solución automática para este tipo de conflicto: hay que cambiar el dibujo.': 'There is no automatic solution for this type of conflict: the drawing must be changed.',
    # Rediseño 2.0.0: barra superior, riel, paneles, Asistente, paleta Ctrl+K
    'Vista': 'View',
    'Ir a': 'Go to',
    'Archivo: nuevo, abrir, guardar, cerrar…': 'File: new, open, save, close…',
    'Cambios sin guardar (Ctrl+S)': 'Unsaved changes (Ctrl+S)',
    'Asistente': 'Assistant',
    'Asistente IA: preguntas sobre el proyecto, resolver conflictos y «¿Cómo hago…?» (Ctrl+Shift+I)': 'AI assistant: questions about the project, solve conflicts and «How do I…?» (Ctrl+Shift+I)',
    'Riel': 'Rail',
    'Hoja {n} de {m}': 'Sheet {n} of {m}',
    'Dibujar': 'Draw',
    'Hoja y PDF': 'Sheet and PDF',
    'Revisión': 'Review',
    'Ayuda: manual, atajos de teclado, acerca de': 'Help: manual, keyboard shortcuts, about',
    'Ajustes: idioma, tema, paneles, asistente IA, familias de Civil 3D': 'Settings: language, theme, panels, AI assistant, Civil 3D families',
    'Regla, transportador y enderezar': 'Ruler, protractor and straighten',
    'Se ubica sola por el mapa base': 'Placed automatically by the base map',
    'Georreferencia': 'Georeference',
    'Varias utilidades': 'Several utilities',
    'Normativa': 'Standards',
    'El asistente propone y prueba soluciones': 'The assistant proposes and tests solutions',
    'Puntas sueltas, repetidas y tramos diminutos': 'Loose ends, duplicates and tiny segments',
    'Word con zonas, capturas y explicación': 'Word with zones, screenshots and explanation',
    'Reglas y aprobación de avisos': 'Rules and warning approval',
    'Mostrar en el plano': 'Show on the drawing',
    'Chat': 'Chat',
    'Cerrar el asistente': 'Close the assistant',
    'Buscar o ejecutar un comando…': 'Search or run a command…',
    'Buscar una acción, una utilidad o un conflicto…': 'Search an action, a utility or a conflict…',
    'Modo claro / oscuro': 'Light / dark mode',
    # Rediseño 2.0.0 (2.ª vuelta): Ajustes, Exportar, Dibujar, Hoja, Inventario, inspector, Revisión
    'Historial completo': 'Full history',
    'Exportar a Civil 3D': 'Export to Civil 3D',
    'Exportar': 'Export',
    '{n} avisos': '{n} warnings',
    '1 aviso': '1 warning',
    'Cambiar…': 'Change…',
    'Quitar': 'Remove',
    'Sin PDF abierto': 'No PDF open',
    'Hoja compuesta · {n} hojas': 'Composite sheet · {n} sheets',
    'Clic: ir al lugar · doble clic: resolver con el asistente': 'Click: go to the place · double click: solve with the assistant',
    'Leader': 'Leader',
    'Texto': 'Text',
    'Borrar': 'Erase',
    'Centerline': 'Centerline',
    'Cotas': 'Elevations',
    'Datos': 'Data',
    'Centrar en el plano': 'Center on the drawing',
    'Más acciones': 'More actions',
    'Con avisos': 'With warnings',
    'Filtrar por nombre, tipo, diámetro…': 'Filter by name, type, diameter…',
    'Asistente IA': 'AI assistant',
    'Familias personalizadas': 'Custom families',
    'Idioma, tema y comportamiento de los paneles.': 'Language, theme and panel behavior.',
    'Tema': 'Theme',
    'Claro': 'Light',
    'Oscuro': 'Dark',
    'Paneles': 'Panels',
    'Queda una pestaña en el borde; se abre al pasar el ratón': 'A tab stays on the edge; it opens when you hover over it',
    'Versión e idioma del catálogo imperial que usa la exportación.': 'Version and language of the imperial catalog used by the export.',
    'Idioma del catálogo': 'Catalog language',
    'También se elige al exportar («Exportar a Civil 3D»).': 'Also chosen when exporting («Export to Civil 3D»).',
    'Quién responde y dónde se guarda lo que aprende.': 'Who answers and where what it learns is saved.',
    'Aprendizaje': 'Learning',
    'Piezas propias en el catálogo de Civil 3D (todas las versiones e idiomas instalados).': 'Your own parts in the Civil 3D catalog (all installed versions and languages).',
    'Asistente C3D': 'Asistente C3D',
    'Novedades': "What's new",
    'Incluir': 'Include',
    'Plano + utilidades': 'Drawing + utilities',
    'Solo utilidades': 'Utilities only',
    'Solo el plano': 'Drawing only',
    'Catálogo': 'Catalog',
    'Civil 3D': 'Civil 3D',
    'Un DXF con las utilidades, buzones y datos para IMPORTAR_RED.': 'A DXF with the utilities, manholes and data for IMPORTAR_RED.',
    'Antes de exportar se revisa el dibujo (puntas sueltas, tramos diminutos…): si hay algo que arreglar, te lo pregunta. Después eliges dónde guardar el DXF.': 'Before exporting, the drawing is reviewed (loose ends, tiny segments…): if there is something to fix, it asks you. Then you choose where to save the DXF.',
    'Opacidad del PDF': 'PDF opacity',
    'Fondo': 'Background',
    'Blanco': 'White',
    'Negro': 'Black',
    'Planos de fondo': 'Background drawings',
    # ── Rediseño 2.0.0: 3.ª vuelta (Normativas, Tabla de datos, Duct Bank, Vista 3D, chat, avisos breves) ──
    'Guardar diseño': 'Save design',
    'Nuevo bancoducto': 'New duct bank',
    'Duplica este bancoducto (sin utilidad asignada).': 'Duplicates this duct bank (with no utility assigned).',
    'Eliminar este bancoducto del proyecto': 'Delete this duct bank from the project',
    '{w} × {h}" · {n} conductos': '{w} × {h}" · {n} conduits',
    '¿Guardar los cambios de este bancoducto?': 'Save the changes to this duct bank?',
    '¿Eliminar el bancoducto «{nombre}» del proyecto?': 'Delete the duct bank “{nombre}” from the project?',
    'Hay cambios sin guardar': 'There are unsaved changes',
    '(regla vacía)': '(empty rule)',
    'Desactivada': 'Disabled',
    'Vista de tabla': 'Table view',
    'Nueva regla': 'New rule',
    'Densidad': 'Density',
    '{n} filas · doble clic en una fila: ir al plano · clic en un encabezado: ordenar':
        '{n} rows · double-click a row: go to the drawing · click a header: sort',
    'DXF exportado': 'DXF exported',
    'Abrir carpeta': 'Open folder',
    'Cumple las normativas': 'Meets the standards',
    'Aprobar…': 'Approve…',
    'Ver opciones': 'See options',
    '{id}: {titulo}. El asistente propone soluciones y prueba cada una en una copia del proyecto.':
        '{id}: {titulo}. The assistant proposes solutions and tests each one on a copy of the project.',
    'Nota (opcional): por qué se aprueba': 'Note (optional): why it is approved',
    'Marca puntos del plano y sus puntos en las calles reales: se ajusta girando y escalando, sin deformar.':
        'Mark points on the drawing and their points on the real streets: it fits by rotating and scaling, '
        'without distorting.',
    'Hojas': 'Sheets',
    '{z} ft': '{z} ft',
    'Esquema de las dos utilidades y la tubería vertical': 'Diagram of the two utilities and the vertical pipe',
    'Conexión vertical': 'Vertical connection',
    'Ya se conectan con una tubería vertical al importar.': 'They are already joined by a vertical pipe on import.',
    'Se cruzan a distinta cota: una pasa por encima de la otra.':
        'They cross at different elevations: one passes over the other.',
    'Diferencia: {dz} ft': 'Difference: {dz} ft',
    'Falta la cota de al menos una de las dos: ponla para decidir si se conectan.':
        'At least one of them has no elevation: set it to decide whether to connect them.',
    'En Civil 3D se dibuja un tramo vertical con su válvula entre las dos cotas.':
        'In Civil 3D a vertical segment with its valve is drawn between the two elevations.',
    'Quitarla deja las dos utilidades sin conectar.': 'Removing it leaves the two utilities unconnected.',
    'Mantener': 'Keep',
    'No conectar': 'Do not connect',
    'Quitar la conexión': 'Remove the connection',
    'Conectar en Civil 3D': 'Connect in Civil 3D',
    'Ver los conflictos y avisos en Revisión': 'See the conflicts and warnings in Review',
    '{n} conflictos': '{n} conflicts',
    '1 conflicto': '1 conflict',
    'Esta hoja': 'This sheet',
    '{n} capas': '{n} layers',
    '1 capa': '1 layer',
    'Una hoja en blanco para dibujar sin PDF: elige su tamaño y la escala.': 'A blank sheet to draw without a PDF: choose its size and scale.',
    'Solo aviso: no se cambian': 'Notice only: not changed',
    'clic: punto del plano': 'click: point on the plan',
    'Calles · NavigateLA': 'Streets · NavigateLA',
    'clic: imán a la intersección · rueda: zoom': 'click: snaps to the intersection · wheel: zoom',
    'Buscar': 'Search',
    'Radio': 'Radius',
    'Zona cargada': 'Area loaded',
    'ft': 'ft',
    'Buscar la zona': 'Find the area',
    'Marcar pares': 'Mark pairs',
    'Ajustar y guardar': 'Fit and save',
    'Escribe una dirección y descarga las calles': 'Type an address and download the streets',
    '{n} pares · mínimo 3': '{n} pairs · minimum 3',
    '{n} de 3 pares como mínimo': '{n} of at least 3 pairs',
    'Error medio {e} ft': 'Mean error {e} ft',
    'Pulsa «Ajustar» con 3 pares o más': 'Press “Fit” with 3 pairs or more',
    'Giro {g}° · Escala {e}': 'Rotation {g}° · Scale {e}',
    'Par con más error: {n} · {e} ft': 'Pair with the largest error: {n} · {e} ft',
    'Sistema de coordenadas (Huso)': 'Coordinate system (zone)',
    'Código CS-MAP (EPSG:2229 = CA83VF). Se aplica al dibujo de Civil 3D al importar.': 'CS-MAP code (EPSG:2229 = CA83VF). Applied to the Civil 3D drawing on import.',
    'Pares de puntos': 'Point pairs',
    'Casilla = mostrar en la hoja · interruptor = reconocer · ▸ = capa por capa': 'Checkbox = show on the sheet · switch = recognize · ▸ = layer by layer',
    'Reconocer {u}': 'Recognize {u}',
    'Tramos unidos': 'Joined runs',
    'Tramos sueltos': 'Separate runs',
    'Hace {n} min': '{n} min ago',
    'Hace {n} h': '{n} h ago',
    'Ayer': 'Yesterday',
    'Hace {n} días': '{n} days ago',
    'Recientes': 'Recent',
    'Sin proyectos recientes': 'No recent projects',
    'Otro diámetro…': 'Other diameter…',
    'Ver análisis': 'View analysis',
    '1 hoja original': '1 original sheet',
    '{n} hojas originales': '{n} original sheets',
    'Original {n}': 'Original {n}',
    'Texto completo de origen': 'Complete source text',
    'Analizando hojas originales y recorrido': 'Analyzing original sheets and route',
    'Datos considerados': 'Data considered',
    'Interpretación: {motivo}': 'Interpretation: {motivo}',
    'El recorrido mide {l} ft y tiene {n} cambios de dirección de al menos 10°.': 'The route is {l} ft long and has {n} direction changes of at least 10°.',
    'Una línea de la misma utilidad toca un extremo y tiene {d}" confirmado; el contacto geométrico no confirma continuidad hidráulica.': 'A line of the same utility touches an endpoint and has a confirmed {d}" diameter; geometric contact does not confirm hydraulic continuity.',
    'Hay {n} estructuras junto a los extremos; su conexión debe comprobarse en el recorte.': 'There are {n} structures near the endpoints; their connection must be checked in the crop.',
    'Análisis del diámetro': 'Diameter analysis',
    'Imagen analizada': 'Image analyzed',
    'Datos enviados': 'Data sent',
    'Detalle de la decisión': 'Decision details',
    'Este análisis no usó imagen, o su captura original ya no está disponible.': 'This analysis did not use an image, or its original crop is no longer available.',
    'Las observaciones y la explicación del modelo son interpretaciones pendientes de revisión.': 'The model’s observations and explanation are interpretations awaiting review.',
    'Propuesta: {d}': 'Proposal: {d}',
    'Por qué:': 'Why:',
    'Criterio:': 'Criterion:',
    'Fuente:': 'Source:',
    'Referencia:': 'Reference:',
    'Por confirmar:': 'To confirm:',
    'Rótulo asociado a esta línea': 'Label associated with this line',
    'Plano PDF': 'PDF drawing',
    '{l} ft de recorrido': '{l} ft route',
    '{n} giros': '{n} turns',
    '{n} contactos geométricos': '{n} geometric contacts',
    'Revisando con la IA': 'Reviewing with AI',
    '{etapa}… {s} s': '{etapa}… {s} s',
    'Contexto y captura preparados': 'Context and crop prepared',
    'Contexto preparado': 'Context prepared',
    'Revisando rótulos y recorrido': 'Reviewing labels and route',
    'Contrastando contexto y normativa': 'Comparing context and standards',
    'Analizando captura y recorrido': 'Analyzing crop and route',
    'Analizando datos del plano': 'Analyzing drawing data',
    'Comprobando la propuesta': 'Checking the proposal',
    'Propuesta para este recorrido de {l} ft, compatible con las reglas aplicables.': 'Proposal for this {l} ft route, compatible with applicable rules.',
    'Propuesta compatible con la utilidad y las reglas aplicables.': 'Proposal compatible with the utility and applicable rules.',
    'Tipo supuesto: {tipo}.': 'Assumed type: {tipo}.',
    'Coincide con los {d}" confirmados de una línea de la misma utilidad en contacto; la conexión debe verificarse.': 'Matches the confirmed {d}" of a touching line of the same utility; the connection must be verified.',
    'Aprobar {d}': 'Approve {d}',
    'El modelo no devolvió una propuesta normativa válida. Reintenta o elige un modelo instruct.': 'The model did not return a valid standards proposal. Retry or choose an instruct model.',
    'Referencia: {u}; capa {c}.': 'Reference: {u}; layer {c}.',
    'La IA revisará los rótulos y, si no hay una lectura segura, propondrá un diámetro según tu normativa.': 'The AI will review labels and, if there is no reliable reading, propose a diameter based on your standards.',
    'No hay rótulos utilizables ni una regla de diámetro aplicable con los datos disponibles. Elige el tipo y completa los datos de la normativa.': 'There are no usable labels or diameter rules applicable to the available data. Choose the type and complete the standards data.',
    'Elige el tipo de la utilidad para concretar la propuesta normativa.': 'Choose the utility type to determine a standards proposal.',
    'Propuesta normativa; no es un diámetro leído del plano. Fuente: {f}. Criterio: {c}': 'Standards proposal; this diameter was not read from the plan. Source: {f}. Criterion: {c}',
    'Tipo supuesto: {tipo}; confírmalo antes de aprobar.': 'Assumed type: {tipo}; confirm it before approving.',
    'Se propone el menor diámetro que cumple estas reglas; requiere aprobación.': 'The smallest diameter satisfying these rules is proposed; approval is required.',
    'En una línea de {u} (capa {c}) el equipo rechazó la propuesta normativa de {d}.': 'For a {u} line (layer {c}), the team rejected the standards proposal of {d}.',
    'Ese proyecto ya no está en su carpeta:\n{p}': 'That project is no longer in its folder:\n{p}',
    'No puedo cambiar mis reglas: solo respondo sobre este proyecto y el uso de PDF-a-CAD. Pregúntame, por ejemplo, por los conflictos, las utilidades o cómo hacer algo en la app.':
        "I can't change my rules: I only answer about this project and how to use PDF-a-CAD. Ask me, for example, about the conflicts, the utilities or how to do something in the app.",
    'No escribo código: solo respondo sobre este proyecto y el uso de PDF-a-CAD. Puedo decirte dónde está algo en la app o qué dicen los datos del proyecto.':
        "I don't write code: I only answer about this project and how to use PDF-a-CAD. I can tell you where something is in the app or what the project data says.",
    '¡Hola! Soy el asistente de PDF-a-CAD. Puedo responderte sobre este proyecto (utilidades, conflictos, avisos, normativas, cotas…) y explicarte cómo hacer algo en la app, por ejemplo georreferenciar la hoja, exportar a Civil 3D o usar la Vista 3D. ¿En qué te ayudo?':
        "Hi! I'm the PDF-a-CAD assistant. I can answer questions about this project (utilities, conflicts, warnings, standards, elevations…) and explain how to do things in the app, for example georeferencing the sheet, exporting to Civil 3D or using the 3D View. How can I help?",
    '{u} es una red a presión (agua o gas): no lleva buzones ni cajas.':
        '{u} is a pressure network (water or gas): it has no manholes or boxes.',
    'Acércate a una línea de gravedad o conduit: el buzón se pone sobre ella.':
        'Move closer to a gravity or conduit line: the manhole is placed on it.',
    'Clic para poner el buzón aquí, sobre {u} (Esc para salir).':
        'Click to place the manhole here, on {u} (Esc to exit).',
    'Solo puedo ayudarte con este proyecto y con el uso de PDF-a-CAD (utilidades, conflictos, avisos, normativas, cotas, cómo hacer algo en la app…).':
        'I can only help you with this project and with using PDF-a-CAD (utilities, conflicts, warnings, standards, elevations, how to do something in the app…).',
    'Perfil longitudinal': 'Longitudinal profile',
    'Exageración vertical': 'Vertical exaggeration',
    '{n} · {a} → {b} ({l} ft)': '{n} · {a} → {b} ({l} ft)',
    'Perfiles guardados ({n})': 'Saved profiles ({n})',
    'Perfil {n}': 'Profile {n}',
    'Guardar perfil': 'Save profile',
    'Nombre del perfil:': 'Profile name:',
    'Ese perfil ya no existe en el plano: sus utilidades cambiaron.': 'That profile no longer exists on the plan: its utilities changed.',
    'VE ×{v}': 'VE ×{v}',
    'Inicio': 'Start',
    'Fin': 'End',
    'Acortar un tramo': 'Shorten by one segment',
    'Extender un tramo': 'Extend by one segment',
    'Limitar hasta…: el siguiente clic en el plano fija el final del perfil': 'Limit to…: the next click on the plan sets the end of the profile',
    'Encuadrar el perfil': 'Fit the profile',
    'Cerrar el perfil': 'Close the profile',
    'Haz clic en una utilidad del plano': 'Click a utility on the plan',
    'Se arma solo el perfil de su tramo, siguiendo la red de frente en cada unión.': 'The profile of its run is built automatically, following the network straight ahead at each junction.',
    'Arrastra un punto (o ↑ ↓) para cambiar su cota · ← → Inicio Fin = nodos · rueda = acercar · botón derecho = desplazar · doble clic = encuadrar': 'Drag a point (or ↑ ↓) to change its elevation · ← → Home End = nodes · wheel = zoom · right button = pan · double click = fit',
    'Guardar este perfil…': 'Save this profile…',
    'Quitar «{n}» de los guardados': 'Remove «{n}» from saved',
    'Quitar de los guardados': 'Remove from saved',
    'el inicio y el final': 'the start and the end',
    'el inicio': 'the start',
    'el final': 'the end',
    'El recorrido se detiene en {l}: en esa unión hay dos caminos casi igual de rectos. Usa «+» para seguir por el más recto o «Limitar hasta…» para elegir.': 'The run stops at {l}: at that junction there are two almost equally straight ways. Use «+» to follow the straightest one or «Limit to…» to choose.',
    '{n} tramos · {c} cruces · elige un punto (clic o ← →) para ver sus datos': '{n} segments · {c} crossings · pick a point (click or ← →) to see its data',
    'solera {z}': 'invert {z}',
    'corona {z}': 'crown {z}',
    'tapa {z}': 'rim {z}',
    'llega {p}': 'in {p}',
    'sale {p}': 'out {p}',
    '(cota no editable aquí: es una T a mitad de tramo)': '(elevation not editable here: it is a tee mid-segment)',
    'Básico': 'Basic',
    'Completo': 'Full',
    'Rótulos cortos: solo qué es cada punto': 'Short labels: only what each point is',
    'Rótulos completos, como en Civil 3D': 'Full labels, as in Civil 3D',
    'Perfiles guardados, guardar y encuadrar': 'Saved profiles, save and fit',
    'Auto': 'Auto',
    'Rótulos completos si caben; si no, básicos': 'Full labels if they fit; otherwise basic',
    'Recubrimiento {c} ft, menor que el mínimo de {m} ft': 'Cover {c} ft, less than the minimum of {m} ft',
    'Contrapendiente {p}: este tramo baja en el sentido del perfil y el agua no corre hacia el inicio': 'Adverse slope {p}: this segment goes down along the profile and water does not flow toward the start',
    'Pendiente nula: el agua no corre': 'Zero slope: water does not flow',
    'Cota del punto': 'Point elevation',
    'Solera (invert) en {e}, ft:': 'Invert at {e}, ft:',
    'Pendiente del tramo': 'Segment slope',
    'Pendiente de {a} a {b}, en % (se mueve la cota del final):': 'Slope from {a} to {b}, in % (the end elevation moves):',
    'Escribir la cota…': 'Type the elevation…',
    'Fijar la pendiente de este tramo…': 'Set the slope of this segment…',
    'Ir a la siguiente alerta del perfil': 'Go to the next profile alert',
    '{n} alertas': '{n} alerts',
    '1 alerta': '1 alert',
    'Alerta {i} de {n} · {e} · {m}': 'Alert {i} of {n} · {e} · {m}',
    'Clic: ver el perfil de este ramal': 'Click: see the profile of this branch',
    'Ramal {n}': 'Branch {n}',
    'Volver a {n}': 'Back to {n}',
    'Ramal de {n}': 'Branch of {n}',
    'Perfil': 'Profile',
}
