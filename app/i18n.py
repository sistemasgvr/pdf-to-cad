"""i18n.py — Sistema de internacionalización simple y sin fricción.

Diseño:
  - Todos los textos originales de la app siguen escritos en **español** en el
    código (no rompemos nada). Cada texto que queramos traducir se envuelve con
    ``t("Texto en español")``.
  - Cuando el idioma activo es "es", ``t()`` devuelve el texto tal cual → cero
    overhead, cero cambio visible.
  - Cuando el idioma es "en", ``t()`` busca la traducción en el diccionario
    ``TRANSLATIONS["en"]``. Si no la encuentra, devuelve el original (así
    strings sin traducir siguen apareciendo en español en vez de romper la UI).
  - Preferencia persistida en ``QSettings``.
  - Bus de señales (``LANG_BUS.changed``) para que widgets con textos ya
    materializados se puedan re-traducir en vivo (menús, toolbars, docks). Los
    widgets creados después del cambio ya salen en el idioma nuevo sin más.

Uso típico:
    from i18n import t, set_lang, get_lang, LANG_BUS

    lbl = QtWidgets.QLabel(t("Buzones"))     # etiqueta traducible
    LANG_BUS.changed.connect(self._retranslate)   # para restilar cuando cambia

Términos de ingeniería civil (US imperial workflow) — traducidos con la
terminología que usa Civil 3D en inglés, no traducción literal:
    tubería/utilidad  → Pipe/Utility        buzón      → Manhole
    invert            → Invert              alineamiento → Alignment
    familia/tamaño    → Family/Size         parts list → Parts List
    bancoducto        → Duct Bank           conducto   → Conduit
    envolvente        → Envelope            rejilla    → Grid
    cota/elevación    → Elevation           georref.   → Georeference

Cuando falte una traducción concreta y la quieras añadir, solo edita el dict
``TRANSLATIONS`` de este archivo — no toques nada más.
"""
from __future__ import annotations
from typing import Optional
from PySide6 import QtCore


SUPPORTED_LANGS = ("es", "en")
DEFAULT_LANG = "es"


class _LangBus(QtCore.QObject):
    """Señal global emitida cuando el usuario cambia el idioma en vivo."""
    changed = QtCore.Signal(str)   # nuevo código de idioma ("es" | "en")


LANG_BUS = _LangBus()

_current_lang: str = DEFAULT_LANG
_settings_key = "app/language"


# ─────────────────────────────────────────────────────────────────────────────
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
TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # ── Menús principales ──────────────────────────────────────────────
        "Archivo": "File",
        "Editar": "Edit",
        "Ver": "View",
        "Herramientas": "Tools",
        "Georreferencia": "Georeferencing",
        "Ayuda": "Help",
        "Nuevo": "New",
        "Abrir": "Open",
        "Guardar": "Save",
        "Guardar como…": "Save As…",
        "Exportar DXF": "Export DXF",
        "Exportar a DXF": "Export to DXF",
        "Cerrar proyecto": "Close project",
        "Salir": "Exit",
        "Opciones…": "Options…",
        "Opciones": "Options",
        "Idioma": "Language",
        "Español": "Spanish",
        "Inglés": "English",
        "Cambiar tema (claro/oscuro)": "Toggle theme (light/dark)",
        "Tema claro": "Light theme",
        "Tema oscuro": "Dark theme",
        "Acerca de…": "About…",
        "Manual…": "Manual…",
        "Atajos de teclado…": "Keyboard shortcuts…",
        "Deshacer": "Undo",
        "Rehacer": "Redo",
        "Copiar": "Copy",
        "Pegar": "Paste",
        "Eliminar": "Delete",
        "Cortar": "Cut",
        "Duplicar": "Duplicate",
        "Editar": "Edit",

        # ── Toolbar y acciones principales ─────────────────────────────────
        "Acercar": "Zoom in",
        "Alejar": "Zoom out",
        "Ajustar": "Fit view",
        "Ajustar a página": "Fit to page",
        "Página anterior": "Previous page",
        "Página siguiente": "Next page",
        "Selección": "Select",
        "Seleccionar": "Select",
        "Puntero": "Pointer",
        "Dibujar tubería": "Draw pipe",
        "Marcar buzón": "Mark manhole",
        "Marcar curva": "Mark curve",
        "Leader": "Leader",
        "Texto": "Text",
        "Borrar zona": "Erase zone",
        "Centerline": "Centerline",

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
        "Selecciona un bancoducto para eliminar.": "Select a duct bank to delete.",
        "Bancoducto duplicado como «{name}».": "Duct bank duplicated as «{name}».",
        "(copia)": "(copy)",

        # ── Bancoductos: diseñador ─────────────────────────────────────────
        "Diseñador de Duct Bank": "Duct Bank Designer",
        "Cara Interior (Corte Longitudinal)": "Interior Face (Cross Section)",
        "Conducto\n(Círculo)": "Conduit\n(Circle)",
        "Medir": "Measure",
        "Zoom +": "Zoom +",
        "Zoom −": "Zoom −",
        "Acercar": "Zoom in",
        "Alejar": "Zoom out",
        "Centrar la vista sobre la envolvente": "Center the view on the envelope",
        "Identificación": "Identification",
        "Nombre:": "Name:",
        "Ej. Duct Bank A – Telecom": "Ex. Duct Bank A – Telecom",
        "Asignar a:": "Assign to:",
        "Utilidad:": "Utility:",
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
        "  Eliminar conducto": "  Delete conduit",
        "Envolvente (pulgadas)": "Envelope (inches)",
        "Ancho:": "Width:",
        "Alto:": "Height:",
        "Margen interior (pulgadas)": "Interior margin (inches)",
        "Rejilla de distribución": "Distribution grid",
        "Mostrar rejilla": "Show grid",
        "Columnas:": "Columns:",
        "Filas:": "Rows:",
        "Redondeo de esquinas (pulgadas)": "Corner rounding (inches)",
        "Visualización en Civil 3D": "Civil 3D visualization",
        "Dibujar contenedor 3D": "Draw 3D container",
        "Conductos: 0": "Conduits: 0",
        "Cancelar": "Cancel",
        "  Guardar y cerrar": "  Save and close",
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
        "Material:": "Material:",
        "Pieza (part):": "Part:",
        "Tipo de red:": "Network type:",
        "Automático (según la capa)": "Automatic (per layer)",
        "Con buzones (pipe)": "With manholes (pipe)",
        "A presión (pressure)": "Pressure",
        "Familia:": "Family:",
        "Tamaño (catálogo):": "Size (catalog):",
        "Diámetro (pulg):": "Diameter (in):",
        "Invert inicio (m):": "Start invert (m):",
        "Invert fin (m):": "End invert (m):",
        "Invert inicio (ft):": "Start invert (ft):",
        "Invert fin (ft):": "End invert (ft):",
        "Coef. Manning:": "Manning's coef.:",
        "Cobertura mínima:": "Minimum cover:",
        "Marcar como abandonada": "Mark as abandoned",

        # ── Estado / mensajes comunes ──────────────────────────────────────
        "Listo.": "Ready.",
        "Cargando…": "Loading…",
        "Guardado.": "Saved.",
        "Sin cambios que guardar.": "No changes to save.",
        "Proyecto cerrado.": "Project closed.",
        "Confirmar eliminación": "Confirm deletion",
        "¿Eliminar {desc}?": "Delete {desc}?",
        "Sí": "Yes",
        "No": "No",
        "Aceptar": "OK",
        "Cancelar": "Cancel",
        "Advertencia": "Warning",
        "Error": "Error",
        "Duct banks guardados: 0": "Duct banks saved: 0",
        "Duct banks: {n}{pipe}": "Duct banks: {n}{pipe}",

        # ── Términos aislados frecuentes (para listas / tooltips) ──────────
        "Bancoducto": "Duct Bank",
        "Envolvente": "Envelope",
        "Conductos": "Conduits",
        "Conductos:": "Conduits:",
        "Tubería": "Pipe",
        "Tubería:": "Pipe:",
        "conducto(s)": "conduit(s)",
        "(sin asignar)": "(not assigned)",
        "(sin nombre)": "(no name)",
        "Doble-click para editar.": "Double-click to edit.",

        # ── Asistente: capas de la hoja (layer_dialog) ────────────────────
        "Capas de la hoja {n}": "Sheet {n} layers",
        "Marca las capas que quieres ver. Las capas ocultas no se dibujan "
        "en el lienzo ni se usan en el reconocimiento.":
            "Check the layers you want to see. Hidden layers are neither drawn "
            "on the canvas nor used for recognition.",
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
        "Reconocimiento cancelado — hoja cargada con todas las capas.":
            "Recognition cancelled — sheet loaded with all layers.",
        "Reconocimiento cancelado — hoja cargada con las capas elegidas.":
            "Recognition cancelled — sheet loaded with the chosen layers.",
        "No hay capas de líneas eléctricas — hoja cargada sin reconocer.":
            "No electrical line layers — sheet loaded without recognition.",
        "Hoja {n} cargada. Capas aplicadas; reconocimiento en pausa.":
            "Sheet {n} loaded. Layers applied; recognition paused.",
        "Ajustar capas eléctricas": "Adjust electrical layers",
        "Indica qué capas son líneas eléctricas y cuáles bóvedas. Las "
        "líneas se importan como utilidades Eléctrico; las bóvedas como "
        "cajas en esas líneas. Al aceptar se vuelve a reconocer la hoja.":
            "Choose which layers are electrical lines and which are vaults. "
            "Lines import as Electric utilities; vaults as boxes on those "
            "lines. On accept the sheet is recognized again.",
        "Capa": "Layer",
        "Trazos": "Paths",
        "Rol": "Role",
        "Líneas eléctricas": "Electrical lines",
        "Buzones / bóvedas": "Manholes / vaults",
        "Ignorar": "Ignore",
        "Debe haber al menos una capa en «Líneas eléctricas» para continuar.":
            "Assign at least one layer as «Electrical lines» to continue.",
        "Asigna al menos una capa como «Líneas eléctricas».":
            "Assign at least one layer as «Electrical lines».",
        "Tramos listos: {n}  ·  Bóvedas: {v}  ·  Escala: {s:.6f} pie/pt":
            "Ready runs: {n}  ·  Vaults: {v}  ·  Scale: {s:.6f} ft/pt",
        "Capas usadas (asignadas automáticamente por su nombre):":
            "Layers used (assigned automatically by name):",
        "Líneas": "Lines",
        "Bóvedas": "Vaults",
        "Hoja {n}": "Sheet {n}",
        "No se encontraron capas de líneas eléctricas en esta hoja. "
        "Usa «Ajustar capas…» para indicar cuáles son las líneas y las bóvedas.":
            "No electrical line layers were found on this sheet. "
            "Use «Adjust layers…» to say which layers are lines and vaults.",
        "Cambiar de hoja…": "Change sheet…",
        "Elegir otra hoja del PDF, revisar sus capas y reconocerla.":
            "Pick another sheet of the PDF, review its layers and recognize it.",
        "Ajustar capas…": "Adjust layers…",
        "Solo si el plot usa otros nombres: indicar qué capas son líneas y bóvedas.":
            "Only if the plot uses other names: say which layers are lines and vaults.",
        "Cambio de hoja cancelado — se mantiene la hoja {n}.":
            "Sheet change cancelled — sheet {n} is kept.",
        "Abandonadas (AB): {a} — mismo color; se distinguen por (AB).":
            "Abandoned (AB): {a} — same color; marked (AB).",
        "(abandonada)": "(abandoned)",
        "Abandonadas (AB): {a}.": "Abandoned (AB): {a}.",
        "Unir tramos en rutas": "Join segments into routes",
        "En cada cruce sigue de frente; el ramal empieza otra ruta. "
        "Si no hay trayectoria clara, no une nada. No mueve puntos.":
            "At each crossing it continues straight; the branch starts another route. "
            "If the path is not clear, nothing is joined. No points are moved.",
        "Rutas: {n} (unen {m} tramos)": "Routes: {n} (join {m} segments)",
        "Importadas {n} rutas ({m} tramos) de Eléctrico.":
            "Imported {n} routes ({m} segments) of Electric.",
        "Al continuar, estas líneas se importan al editor como "
        "utilidades Eléctrico (igual que el dibujo manual, con sus "
        "puntos de quiebre). Las bóvedas se insertan como cajas.":
            "On continue, these lines import into the editor as Electric "
            "utilities (same as manual drawing, with break points). "
            "Vaults are inserted as boxes.",
        "Bóvedas: {s} en líneas, {k} sin pipe cercana.":
            "Vaults: {s} on lines, {k} with no nearby pipe.",
        "Capas ocultas por ti: {n} (no se dibujan ni se reconocen)":
            "Layers you hid: {n} (neither drawn nor recognized)",
        "Cobertura: {c:.1f}%  ·  sin cubrir: {m} (naranja)  ·  fuera de patrón: {o} (violeta)":
            "Coverage: {c:.1f}%  ·  uncovered: {m} (orange)  ·  off-pattern: {o} (violet)",
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
        "  Exportar DXF": "  Export DXF",

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
        "Georref": "Georef",
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
        "Telefonía (T)": "Telecom (T)",

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

        # ── Entradas del CHANGELOG v1.1.0 (rendered in Acerca de…) ────────
        "Nuevo diseñador de Bancoductos (Duct Bank): dibuja la sección con envolvente, márgenes, redondeo de esquinas, rejilla de distribución, reglas de separación y de resguardo al borde. Cada bancoducto se asigna a una utilidad del plano y al importar en Civil 3D se crea el sólido 3D del contenedor + los conductos internos como tuberías reales.":
            "New Duct Bank designer: draw the cross-section with envelope, margins, corner rounding, distribution grid, spacing and edge-clearance rules. Each duct bank is assigned to a utility of the plan and, when imported into Civil 3D, creates the 3D container solid + internal conduits as real pipes.",
        "Panel «Bancoductos» en el inventario derecho: lista todos los bancoductos del proyecto con botones Nuevo / Editar / Duplicar. Doble-click en una fila abre el diseñador ya cargado con ese bancoducto. Click derecho sobre una tubería del plano ofrece «Crear/Editar bancoducto».":
            "«Duct Banks» panel in the right inventory: lists all project duct banks with New / Edit / Duplicate buttons. Double-click on a row opens the designer already loaded with that duct bank. Right-click on a pipe offers «Create/Edit duct bank».",
        "Opción para elegir si se dibuja el contenedor 3D del bancoducto o solo los conductos internos (útil cuando el contenedor de concreto ya existe en el DWG).":
            "Option to choose whether the duct bank's 3D container is drawn or only the internal conduits (useful when the concrete container already exists in the DWG).",
        "Selector de idioma en Archivo → Opciones… La app se puede alternar entre Español e Inglés; la elección se recuerda al reabrir.":
            "Language selector under File → Options… The app can switch between Spanish and English; the choice is remembered on reopen.",
        "Diálogo de Opciones en el menú Archivo (pensado para crecer con más preferencias en el futuro).":
            "Options dialog in the File menu (designed to grow with more preferences in the future).",
        "Documento «Cómo funciona el proyecto» en formato interactivo (docs/arquitectura.html): explicación por carpetas y archivos en lenguaje sencillo, con diagramas.":
            "«How the project works» interactive document (docs/arquitectura.html): folder-by-folder and file-by-file explanation in plain language, with diagrams.",
        "Menú contextual (click derecho) en las tuberías del inventario: crear o editar el bancoducto asignado sin salir del contexto.":
            "Context menu (right-click) on inventory pipes: create or edit the assigned duct bank without leaving context.",
        "La cota invert del bancoducto ahora manda el FONDO del contenedor (parte inferior externa), como en las tuberías normales. Los conductos internos se distribuyen correctamente hacia arriba desde ese fondo.":
            "The duct bank invert elevation now drives the BOTTOM of the container (outer lower face), like normal pipes. Internal conduits distribute correctly upward from that bottom.",
        "Las cotas por tramo (VertexInv) del pipe padre ahora se aplican también al sólido del contenedor y a los conductos internos — antes solo se usaban en tuberías normales.":
            "Per-segment elevations (VertexInv) on the parent pipe now also apply to the container solid and internal conduits — previously used only on normal pipes.",
        "Zoom del lienzo principal: acercar hasta 4000% y alejar hasta 30% con la rueda o los botones (antes 1000% / 10% y el botón se saltaba el límite).":
            "Main canvas zoom: zoom in up to 4000% and out to 30% with the wheel or buttons (was 1000% / 10% and the button skipped the limit).",
        "El botón «+ Nuevo» del panel de bancoductos ahora sí crea uno desde cero (antes cargaba el último diseño).":
            "The «+ New» button in the duct banks panel now really creates one from scratch (previously loaded the latest design).",
        "Rediseño del diseñador de bancoductos: acciones «Cancelar / Guardar y cerrar» debajo del canvas, «Puntero» unificado (click selecciona, arrastra mueve), banner rojo sobre el canvas cuando hay problemas, panel «Identificación» al inicio, panel «Conducto» contextual (cambia entre modo nuevo/editar).":
            "Duct bank designer redesign: «Cancel / Save and close» actions below the canvas, unified «Pointer» (click selects, drag moves), red banner over the canvas when there are issues, «Identification» panel at the top, contextual «Conduit» panel (switches between new/edit mode).",
        "Modo oscuro mejorado: el bancoducto asignado a la tubería seleccionada ya se lee sin problemas, y el título en «Duct Bank: ...» dejó de salir con azul ilegible sobre fondo negro.":
            "Improved dark mode: the duct bank assigned to the selected pipe is now readable, and the «Duct Bank: ...» title no longer shows in an illegible blue on black background.",
        "Los tamaños de tubería que faltan en el catálogo se instalan automáticamente al importar (evita el fallback silencioso a un diámetro distinto).":
            "Pipe sizes missing in the catalog are automatically installed on import (prevents silent fallback to a different diameter).",
        "Los conductos del bancoducto ya no sobresalen del contenedor en el render 3D (Civil 3D dibuja al diámetro exterior; ahora se fuerza pared 0 en las medidas custom que la app inyecta al catálogo).":
            "Duct bank conduits no longer poke out of the container in the 3D render (Civil 3D draws to outer diameter; now forces wall 0 for custom sizes the app injects into the catalog).",
        "Rediseñar el bancoducto de una utilidad ya no crea dos sólidos superpuestos: se sobreescribe por identidad, no por nombre.":
            "Redesigning a utility's duct bank no longer creates two overlapping solids: it overwrites by identity, not by name.",
        "El sólido del bancoducto sigue las cotas de la tubería padre (antes quedaba a Z=0 mientras los conductos usaban las cotas correctas).":
            "The duct bank solid now follows the parent pipe's elevations (previously stayed at Z=0 while conduits used the correct elevations).",
        "Al abrir el diseñador desde una tubería, ahora carga el bancoducto asignado a ESA tubería (antes cargaba el último editado).":
            "When opening the designer from a pipe, it now loads the duct bank assigned to THAT pipe (previously loaded the last edited one).",

        # ── Ventanas de la app (títulos) ──────────────────────────────────
        "Asistente C3D": "C3D Assistant",
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
        "Divide el área interior en celdas iguales para colocar\n"
        "conductos simétricamente. Solo es una guía visual;\n"
        "no obliga a nada.":
            "Divides the interior area into equal cells to place\n"
            "conduits symmetrically. Just a visual guide;\n"
            "does not enforce anything.",
        "Cuántas columnas verticales dividen el área interior.":
            "How many vertical columns divide the interior area.",
        "Cuántas filas horizontales dividen el área interior.":
            "How many horizontal rows divide the interior area.",
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
        "Click en dos puntos para medir la distancia entre ellos en pulgadas.":
            "Click on two points to measure the distance between them in inches.",
        "Click en un conducto para eliminarlo.":
            "Click on a conduit to delete it.",
        "Click en un conducto para seleccionarlo. Arrástralo para moverlo.":
            "Click on a conduit to select it. Drag it to move it.",
        'Click dentro de la envolvente para colocar un conducto de {d}".':
            'Click inside the envelope to place a {d}" conduit.',
        "Click en 2 puntos para medir la distancia entre ellos.":
            "Click on 2 points to measure the distance between them.",
        "Centrar la vista sobre la envolvente":
            "Center the view on the envelope",
        "Celda": "Cell",
        "col": "col",
        "fil": "row",
        "Celda: —": "Cell: —",
        "Celda: —  (envolvente o margen inválido)":
            "Cell: —  (invalid envelope or margin)",

        # ── Toolbox / secciones (dock izquierdo) ───────────────────────────
        "Duct Bank": "Duct Bank",
        "  Abrir diseñador de Duct Bank": "  Open Duct Bank Designer",
        "Diseña la sección transversal del Duct Bank\n"
        "(envolvente rectangular + conductos internos).":
            "Design the cross-section of the Duct Bank\n"
            "(rectangular envelope + internal conduits).",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
def _settings():
    return QtCore.QSettings("pdfcad", "app")


def get_lang() -> str:
    """Devuelve el código de idioma activo ("es" o "en")."""
    return _current_lang


def load_lang() -> str:
    """Lee la preferencia guardada (o el default) y la activa. Se llama una vez
    al arrancar la app, ANTES de construir la UI."""
    global _current_lang
    saved = _settings().value(_settings_key, DEFAULT_LANG)
    if saved in SUPPORTED_LANGS:
        _current_lang = saved
    else:
        _current_lang = DEFAULT_LANG
    return _current_lang


def set_lang(lang: str) -> None:
    """Cambia el idioma activo, lo guarda en preferencias y emite la señal
    ``LANG_BUS.changed`` para que la UI se re-traduzca en vivo."""
    global _current_lang
    if lang not in SUPPORTED_LANGS:
        return
    if lang == _current_lang:
        return
    _current_lang = lang
    _settings().setValue(_settings_key, lang)
    LANG_BUS.changed.emit(lang)


def t(text_es: str, en: Optional[str] = None) -> str:
    """Traduce ``text_es`` al idioma activo.

    Contrato:
      - Si idioma = "es" → devuelve ``text_es`` sin tocar. Rendimiento cero.
      - Si idioma = "en":
          * si se pasó ``en`` explícito, lo usa (útil para strings puntuales
            que no queremos meter al dict maestro).
          * si el string existe en ``TRANSLATIONS["en"]``, devuelve esa
            traducción.
          * si no, devuelve el original en español (así una UI sin traducir
            sigue visible; no se rompe nada).
    """
    if _current_lang == "es":
        return text_es
    if en is not None:
        return en
    return TRANSLATIONS.get(_current_lang, {}).get(text_es, text_es)


def display_lang(code: str) -> str:
    """Nombre humano del idioma en el idioma activo (para desplegables)."""
    if code == "es":
        return t("Español")
    if code == "en":
        return t("Inglés")
    return code
