# pdf-to-cad — guía del proyecto

Pipeline **PDF de plano → DXF → Civil 3D** para redes de utilidad (agua,
alcantarillado, drenaje, gas, eléctrico, telecom). Todo en **unidades imperiales
(pies)**.

## Mapa del repo

- `app/` — **app de escritorio (PySide6)** donde el usuario digitaliza sobre el PDF.
  - `main.py` — punto de entrada (arma `sys.path`: `app/` + raíz).
  - `app_window.py` — ventana principal `Main`. La UI se arma en `_build_ui`, que
    llama a `_build_menu` / `_build_toolbar` / `_build_left_dock` / `_build_right_dock`
    / `_build_statusbar` (todos dejan sus widgets como `self.*`, en ese orden).
  - `canvas.py` — el lienzo (`Canvas`, QGraphicsView).
  - `widgets.py` — widgets reutilizables (`InlineEdit`, `_SegInvSpinBox`, `_NoWheelFilter`).
  - `ui_common.py` — constantes/helpers de UI compartidos (`DOWNLOADS`, estilos de
    botón, `layer_qcolor`, `swatch_icon`, …). Sin estado; los usa toda la app.
  - `workers.py` — hilos de fondo (`PipelineWorker`, `RecognitionWorker`).
  - `recognition.py` + `recognition_dialog.py` — asistente al abrir un PDF
    vectorial: componer hoja → capas → reconocer (v1: eléctricas `C-ELEC-UNGD`;
    roles líneas/bóvedas AUTOMÁTICOS por nombre, `classify_ocg`) → vista
    previa con QA e info de capas usadas → importar como pipes. El preview
    devuelve una acción (`PREVIEW_IMPORT | CANCEL | CHANGE_SHEET |
    ADJUST_LAYERS`): «Cambiar de hoja…» repite `Main._wizard_sheet_flow`
    (hojas → capas → reconocer); «Ajustar capas…» abre `LayerRolesDialog`
    (ya no es un paso obligatorio) y re-reconoce con `self._layer_roles`.
    `recognition.py` solo filtra paths por capa/rol y convierte PDF→px.
  - `recognition_geom.py` — **núcleo geométrico PURO** (sin Qt ni fitz): en el
    PDF la utilidad viene como linetype "explotado" (guiones + letras «e» +
    huecos), nunca como polilínea. Aprende el patrón del plano
    (`learn_pattern`), agrupa guiones colineales (±1°, ≤1.5 pt), arma corridas
    uniendo huecos solo con evidencia (patrón / letra encima / bóveda en medio),
    resuelve nodos (bóveda, esquina = intersección exacta, quiebre suave, T)
    con la regla de oro **un extremo solo se desliza por su propia recta**, y
    ensambla polilíneas con `kinds` por vértice (`end|corner|bend|junction|tee|
    vault|edge|stop|curve`). **Reglas de bóveda (apuntes del usuario, revisadas)**:
    toda línea llega por su recta y SIEMPRE deja `edge` (quiebre oculto) donde
    choca con el borde; el nodo interior `vault` (CAJA visible) existe solo si
    una línea de red ATRAVIESA la bóveda (corrida partida en Fase A, o dos
    llegadas colineales opuestas) y se calcula con las llegadas: sobre la que
    atraviesa (intersección si son dos), nunca con el círculo/cajita del símbolo
    (`Vault.reference` queda informativo). Las demás llegan al nodo por su eje +
    `bend` corto. Sin línea que atraviese, cada llegada termina en el borde con
    `stop` (CAJA visible ahí; el usuario completa a mano). `_split_by_fit`
    parte corridas donde los guiones se apartan >`RUN_FIT_TOL_PT` para que
    T/convergencias queden sobre la línea de la capa. **Clips**:
    `recognition.gather_paths` usa `get_drawings(extended=True)` y recorta cada
    path por el polígono de clip activo (`geom.clip_path`) — sin eso la
    geometría "supera" el marco de la vista de planta que sí recorta el render;
    los puntos de corte son nodos `cut` (no forman esquinas). Los arcos
    pequeños abiertos (giro ≤200°) son codos, no letras. **Abandonadas**
    (capa de estado `-A`, linetype «──/── e ──»): `recognition.is_abandoned_ocg`
    separa las capas activas de las abandonadas y `recognize_page` corre
    `reconstruct` por grupo (son pipes distintas; `RecognizedPolyline.abandoned`
    → pipe `ab=True`). En el núcleo, `strip_crossing_markers` convierte las
    barras «/» (trazo corto que cruza la línea con su punto medio sobre ella)
    en glifos, y `detect_loop_vaults` toma un lazo rectangular cerrado de 4
    corridas perpendiculares (lado 12–120 pt) de la propia capa como bóveda
    (el DU06 dibuja el contorno de la bóveda abandonada en `C-ELEC-UNGD-A`).
    Un trazo continuo que solo nace en el borde de una bóveda no forma
    «through virtual» con la línea del lado opuesto (sí si la cruza).
    **T-ends** (`resolve_nodes`, pre-pasada tras la Fase A): un extremo que
    muere a ≤`NODE_OFF_LINE_PT` de otra corrida recta, en su interior, sin
    continuación colineal enfrente ni otro extremo pegado, es una T con ESA
    corrida (no llega a bóvedas vecinas, no forma esquina con terceros:
    5c-bis). Un tick corto sobre el que muere otra corrida queda «capped»
    (sus puntas son extremos puros: ni esquina, ni T, ni prolongación). `slide_ok`: ninguna esquina/T desliza un
    extremo más de media corrida. `SOFT_SIMPLIFY_PT`=1.5 para bend/corner,
    `CURVE_SIMPLIFY_SOFT_PT`=1.0 en tramos con vértices de curva. Ojo: `git checkout --`
    sobre archivos *staged* descarta el trabajo no staged — no usarlo aquí.
    `edge`/`stop` nunca se simplifican. Devuelve cobertura de guiones,
    guiones sin cubrir y trazos off-pattern (leaders) para QA. Tests con PDFs
    sintéticos (`tests/test_recognition_geom.py::Sheet`) y umbrales sobre el
    DU06 (97–100 % por hoja). Si una hoja baja de eso, mirar primero
    `uncovered` con el overlay antes de tocar tolerancias.
  - `routes.py` — **rutas PURO** (sin Qt ni fitz), después de `reconstruct` y
    sin tocarlo. Une polilíneas de una sola capa en strokes por buena
    continuación (Thomson & Richardson, every-best-fit): en cada nodo se
    sigue de frente (`THETA_JUNCTION_DEG`=35° si grado ≥3, `THETA_DEG2_DEG`=100°
    si grado 2); si el segundo candidato está a < `AMBIGUOUS_DELTA_DEG` (10°)
    no se une nada. No inventa ni mueve puntos; no cruza capas ni activas con
    abandonadas (eso lo garantiza `recognize_page`, que llama `build_routes`
    una vez por OCG). `join_routes=False` deja las polilíneas cortadas.
  - `composite.py` + `composite_view.py` + `composite_dialog.py` — **hoja compuesta**
    (v1.2.0), primer paso del asistente para PDF vectorial (reemplaza a «Organizar
    hojas», que sigue en el menú Ver como legado). `composite.py` es PURO (solo
    fitz): `Piece` (PDF origen, hoja, `clip` normalizado sobre la hoja visible,
    `x,y` en pt de la hoja compuesta, `rotation` ANTIHORARIO como `show_pdf_page`,
    `src_scale` pies/pt) y `Composite` (piezas + `scale_ft_per_pt` única; cada
    pieza se escala por `src_scale/target`). `piece_map` reproduce exactamente el
    mapeo de `show_pdf_page` (centro a centro, giro antihorario, factor uniforme);
    `edge_anchors` da los anclajes (`Anchor`: cortes de trazos con el borde del
    clip + extremos sobre el borde ±0.75 pt, con dirección de salida y capa; se
    ignoran rellenos puros como logos y se fusionan los apiñados <0.5 pt);
    `magnet_delta` (extremos que coinciden) y `collinear_delta` (extremos
    enfrentados con hueco: solo alinea lateralmente) eligen el desplazamiento
    con más parejas MUTUAS coincidentes (mediana). `find_bridges` empareja
    extremos enfrentados de piezas distintas en la misma capa (nombre corto,
    desvío ≤1.5 pt, hueco ≤ `bridge_max_pt`) y `build_document(..., bridges)`
    los dibuja con `draw_line(oc=xref)` en esa capa, con el PATRÓN de guiones
    del extremo (`bridge_segments`; un trazo sólido largo alteraba `learn_pattern`).
    Anclajes: solo trazos de línea (≥3 pt, ≤6 items, sin rellenos); `on_edge`
    distingue extremos sobre el borde (imán de coincidencia) de los que mueren
    hasta 8 pt por dentro (solo alinean/puentean). `trim_border_lines` encoge el
    clip por dentro de la match line / marco: trazos paralelos ≤14 pt del lado
    agrupados por coordenada (±1.25 pt, `_collinear_lines`) que cubran ≥35 % del
    lado — también match lines a GUIONES gruesos (DU06 hojas 14/15: x=349/350,
    1609/1610, ancho 1.98); una serie de ≥3 paralelas = grilla, no se recorta. `recognition.
    gather_paths` descarta astillas <1.5 pt creadas por un clip (`CLIP_SLIVER_PT`):
    con eso DU06 hoja 4 partida en dos con hueco = 13 rutas, igual que entera.
    OJO: `theme.apply_theme` PERSISTE la preferencia en QSettings; en scripts de
    captura offscreen usar paleta+stylesheet a mano, nunca `apply_theme`. `build_document` materializa la hoja
    como PDF real de UNA página: `show_pdf_page` por pieza (vectores, textos y
    capas intactos; OJO: ignora el `/Rotate` de la hoja origen → clip des-rotado y
    `rotate=piece.rotation - page.rotation`) y reconstruye `/OCProperties` con los
    OCG que graftmap copió (hay que guardar y REABRIR el doc para que fitz vea el
    catálogo; por eso `Main._apply_composite` escribe un PDF temporal). El BBox de
    cada XObject actúa como clip en `gather_paths`, así el reconocimiento de la
    hoja compuesta es idéntico al de la original (verificado con el DU06). Con una
    sola pieza = hoja entera no se materializa: se usa el PDF origen (◀ ▶ sirven).
    `Main` guarda los PDFs de origen en memoria (`src_pdfs`, bytes) y en el
    `.digproj` (`sources/NNN.pdf`) junto a `composite`, `src_names`, `hidden_ocgs`
    y `scale_override`; `work_pdf_path` es el PDF que ven los workers.
    Tests: `tests/test_composite.py` (puro) y `tests/test_composite_dialog.py`
    (Qt offscreen, punta a punta: dos hojas → una ruta).
  - `pdf_layers.py` + `layer_dialog.py` — paso «Capas de la hoja» del asistente:
    lista las capas OCG con geometría y las apaga/enciende con
    `doc.set_layer_ui_config` (única API que afecta render **y** `get_drawings`;
    `doc.set_layer` no sirve en PDFs de Bluebeam). La visibilidad vive en el
    `fitz.Document` de `Main` (`self.hidden_ocgs` guarda los nombres); el worker
    abre su propio doc, por eso recibe `hidden_ocgs` y filtra por nombre.
    `pdf_layers.utility_of(name)` agrupa cada capa por tokens NCS en las
    utilidades de la app (`model.TIPOS` + `OTRAS`); el diálogo las lista
    agrupadas con su color, el panel «Utilidades» solo FILTRA la lista, y
    «◀ Hoja N / M ▶» cambia de hoja sin salir. Devuelve `(ocultas, hoja)`.
    En `Main`, `_start_recognition(idx)` lanza el worker con
    `self.hidden_ocgs` + `self._layer_roles` (None = automático); `_change_page`
    (◀ ▶ / nº de página del editor) lo reutiliza si `self._recog_ready`.
  - `dialogs.py` — diálogos fuera del flujo principal (Acerca/Manual/Atajos,
    instalar/desinstalar familias). Funciones que reciben `win`; en `Main` quedan
    métodos delgados que delegan (los menús siguen apuntando a `self.show_about`, etc.).
  - `project_io.py` — serialización del `.digproj`: `build_model_dict(win)` y
    `parse_model(model)`. Lógica PURA (sin Qt), testeable. `Main` conserva el zip,
    el PNG del lienzo y `set_image`; solo delega la parte de datos.
  - `icons.py` + `icons/mdi/*.svg` — iconos SVG bajados de
    [api.iconify.design](https://api.iconify.design) (familia Material Design
    Icons). `icon("mdi:pencil-outline", color=…)` devuelve un `QIcon` retintado
    en runtime — el color por defecto viene del tema activo. Los emojis
    (📄✏🔍🗑…) fueron reemplazados por estos iconos vectoriales, consistentes
    entre plataformas y con estilo moderno. Bajar nuevos: `curl -s -o
    app/icons/mdi/<nombre>.svg https://api.iconify.design/mdi/<nombre>.svg`.
  - `theme.py` — sistema de tema (claro/oscuro) global. Tokens de color en
    `Theme`, paleta Qt + stylesheet global aplicados por `apply_theme(app, name)`,
    señal `THEME_BUS.changed` para que widgets con QSS custom se restilen, y
    preferencia persistida en QSettings. Menú **Ver** en la ventana principal
    permite alternar en vivo.
  - `duct_bank.py` — modelo PURO del Duct Bank (sin Qt): `DuctBank` (envolvente
    rectangular en pulgadas + lista de `Conduit` + `pipe_idx` de la pipe asignada),
    `snap`, `validate`, `conduit_fits_envelope`, `conduits_overlap`. Testeado
    headless. La sección se asigna a una pipe específica y se exporta como
    `PDFCAD_DUCTBANK` en el DXF; el plugin C# la extruye como sólido 3D.
  - `duct_bank_dialog.py` — diálogo del **Diseñador de Duct Bank** (botón del
    toolbar, se guarda en `.digproj` como parte del proyecto). UI grande y
    accesible (usuario +60): grid en pulgadas, snap por defecto, solo una
    herramienta activa a la vez, undo/redo, zoom fit. Trae rectángulo,
    conductos, mover, medir, eliminar.
  - `model_ops.py` — operaciones PURAS sobre el modelo (sin Qt): auto-detección de
    buzones (`rebuild_structures`), ocultar cajas de quiebres reconocidos sin
    bóveda (`hide_soft_vertex_structures`, usa `pipe["vertex_kinds"]`), conteo de conexiones (`bz_segment_count`), cotas
    por tramo (`interp_vertex_z`, `migrate_vertex_inv`, `snapshot_seg_values`),
    búsqueda por vértice (`pipe_at_vertex`) y geometría de Multileader (`leader_geo`,
    recibe la conversión pies→px de la ventana). `Main` delega y solo asigna/dibuja.
  - `model.py` — constantes, `VERSION`, `CHANGELOG`, capas Z, tabs.
  - `dxf_export.py` — exporta el DXF con XDATA `PDFCAD`.
  - `civil_catalog.py` — lee el catálogo imperial de Civil 3D (familias/tamaños/GUID).
  - `geo/` — georreferenciación: `georef.py` (ajuste), `georef_dialog.py` (UI),
    `la_reference.py` (calles/parcelas de NavigateLA).
- Raíz — **pipeline de digitalización**: `config.py`, `vector_pipeline.py`,
  `raster_pipeline.py`, `digitize.py`, `detect.py`.
- `API-CIVIL/proyecto1/proyecto1/` — **plugin C# de Civil 3D** (.NET 8). Lee el DXF
  y crea las redes. Comando clave: `IMPORTAR_RED` ([ImportarRed.cs]).
- `installer/` — bundle del plugin + Inno Setup. `build_all.bat` (raíz) arma todo.
- `tests/` — pruebas de humo headless (pytest, 27): georref (`fit`), modelo Georef,
  catálogo (`family_guid`), serialización (`project_io`) y operaciones de modelo
  (`model_ops`: buzones, conteo, cotas por tramo). Corren sin abrir la UI.

## Invariantes (no romper)

- **Imperial / pies** siempre. El DXF necesita `$INSUNITS=2`, `$MEASUREMENT=0`.
- **Contrato XDATA del DXF** (appid `PDFCAD`), lo lee `ImportarRed.cs`:
  - `PDFCAD_PIPE` (polilínea): `DIAMETER, UNIT, MATERIAL, NET_KIND, NET_TYPE,
    INV_START, INV_END, MANNINGS_N, COVER_MIN, PIPE_FAMILY, PIPE_GUID, PIPE_SIZE,
    NO_MANHOLE_VERTS, SEG_OVERRIDES, VERTEX_INV, VERTEX_INV_IN, ABANDONED,
    PIPE_IDX, HAS_DUCT_BANK`.
    `HAS_DUCT_BANK=1` → el plugin excluye esta pipe del flujo de redes normales;
    el duct bank la reemplaza con un sólido 3D. `PIPE_IDX` es el índice Python
    de la pipe, usado para emparejar con el `PDFCAD_DUCTBANK` correspondiente.
    `ABANDONED=1` → el plugin le asigna un PipeStyle cuyo **display 3D (Model)**
    usa un linetype discontinuo (copia hermana del estilo base, así planta/perfil
    quedan idénticos). Solo afecta la vista 3D en Civil 3D.
  - `PDFCAD_STRUCT` (punto): `STRUCT_ID, RIM, SUMP, PART, PART_GUID, PART_SIZE,
    COVERED, NET_KIND, HEIGHT_FT, HIDDEN`.
  - `PDFCAD_CURVE` (punto): esquina de elemento curvo, con `RADIUS_FT`.
  - `PDFCAD_META` (punto): metadatos del proyecto, hoy `CS_CODE` (Huso).
  - `PDFCAD_DUCTBANK` (punto, capa `PDFCAD_DUCT_BANK`): sección transversal del
    duct bank asignado a una pipe. `PIPE_IDX, NAME, WIDTH_IN, HEIGHT_IN,
    MARGIN_TOP/RIGHT/BOTTOM/LEFT, CORNER_TL/TR/BR/BL,
    CONDUITS=cx,cy,diam,label|...`. El plugin extruye la envolvente como
    sólido 3D a lo largo de la polilínea de la pipe.
- **Familias de piezas**: por defecto de Autodesk (nombre `Aecc…`) se emparejan
  por **GUID** (`Catalog_PartID` = `PartFamily.GUID`); las **custom** por
  **Descripción**. Nunca mezclar. `civil_catalog.family_guid` devuelve "" para no-Aecc.
- **Georreferenciación**: EPSG:2229 (State Plane CA V, ftUS). El ajuste es de
  **similaridad** (rota+escala, sin deformar); no volver al afín. El código de
  sistema de coordenadas (Huso, ej. `CA83VF`) viaja en `PDFCAD_META/CS_CODE` y el
  plugin lo aplica a `DrawingSettings.UnitZoneSettings.CoordinateSystemCode`.
- **Versión/idioma de Civil 3D** elegidos en el toolbar se guardan en el `.digproj`
  (`civil_year`/`civil_lang`) y se reponen al abrir.

## Cómo correr

- App: `python app/main.py`
- Pruebas: `pytest`  (desde la raíz)
- Compilar plugin + exe + instalador: `build_all.bat` (pregunta la versión)
- Quitar el plugin del autoload de C3D (testing): `uninstall_plugin.bat`
- Compilar solo el plugin C#: `dotnet build -c Release` en
  `API-CIVIL/proyecto1/proyecto1` (baseline: 0 errores, 4 warnings).

## Convenciones

- Apuntar a archivos **< 500 líneas**; una responsabilidad por módulo.
- Dónde va cada cosa: lienzo → `canvas.py`; widgets reutilizables → `widgets.py`;
  hilos → `workers.py`; diálogos secundarios → `dialogs.py` (el de georref vive en
  `geo/georef_dialog.py`); lógica de catálogo → `civil_catalog.py`; export →
  `dxf_export.py`.
- Al mover código a un módulo nuevo: hacerlo **verbatim** y dejar en `Main` un
  método delgado que delega, para no romper menús/atajos ni la navegación.
- Al cambiar comportamiento visible al usuario, actualizar `CHANGELOG` y la
  versión en `app/model.py` (y el manual en `app_window.py` `show_manual`).
- Español en comentarios y textos de UI (el usuario y su equipo trabajan en español).

## Roadmap de arquitectura (incremental)

1. ✅ Extraer `Canvas`, widgets y worker a módulos propios + tests + este archivo.
2. ✅ Extraer los **diálogos** (ayuda + familias) a `dialogs.py` (con delegadores).
   ✅ Partir `_build_ui` en submétodos (`_build_menu/_toolbar/_left_dock/_right_dock/
   _statusbar`), misma clase, mismo orden — cero cambio de comportamiento.
3. ✅ Separar lógica de datos PURA de `Main` a módulos testeables:
   `project_io.py` (serialización del `.digproj`) y `model_ops.py` (auto-detección
   de buzones + conteo de conexiones). Patrón: mover verbatim → `Main` delega y
   asigna → test unitario + round-trip real headless.
   Ya movidas también las cotas por tramo (`interp_vertex_z`/`migrate_vertex_inv`/
   `snapshot_seg_values`). Pendiente: seguir con lo que quede de datos en `Main`.
