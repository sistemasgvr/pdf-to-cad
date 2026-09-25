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
  - `widgets.py` — widgets reutilizables (`InlineEdit`, `_SegInvSpinBox`, `_NoWheelFilter`,
    `ZoomPanView`, `MiniMap`: minimapa con recuadro de lo visible sobre una ZoomPanView;
    `set_layout(items, scene_rect)` = esquema de hojas (cajas con etiqueta, lo que
    pidió el usuario: organización, no dibujo) o `set_thumbnail(pixmap, rect)`.
    «Capas de la hoja» recibe `layout` de `composite.piece_layout` vía
    `Main._composite_layout` (se calcula en `_apply_composite`); `maximize_on_show(dlg)`:
    la ÚNICA forma fiable de abrir un QDialog maximizado en Windows (setWindowState
    diferido tras el primer Show; `exec()` pisa un showMaximized previo);
    `side_panel_width`; `CollapsiblePanel` (cabecera + plegado a tira vertical, lo
    usa el compositor para pantallas pequeñas)).
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
    `recognition.py` solo filtra paths por capa/rol y convierte PDF→px… y hace
    dos post-procesos: `fit_fillets` (codo = EXACTAMENTE un trazo curvo del PDF:
    `_arc_spans` = ristra de vértices `curve` (interiores del trazo) + sus dos
    vecinos (extremos reales del trazo), encadenando `curve, nodo, curve`; NUNCA
    quiebres `corner`/`bend` sueltos — una cadena de guiones rectos es esquinas,
    el usuario lo exigió tras un falso codo). **Geometría (auditoría 2026-09-21,
    tras un codo con la esquina 3.7 pt fuera y la tangente 4.75° torcida en DU06
    h.4)**: el ajuste libre (Kåsa, RMS ≤1 pt·zoom) es solo semilla/filtro; un
    `bend`/`corner` vecino que cae SOBRE ese círculo se absorbe al arco (es el
    último guión curvo que la simplificación dejó recto o el empalme run↔curva),
    con fallback al tramo original si así no cierra (curva compuesta); las
    rectas son las de los GUIONES (`_leg_lines`: si el vecino es bend/corner
    pegado al arco, < `FILLET_TANGENT_SLIP_PX`, se prueba primero la recta del
    guión anterior — el salto hasta el trazo curvo suele ser hueco/letra, no
    tinta); el círculo final es el TANGENTE a esas dos rectas que mejor pasa por
    los vértices del trazo (`_fit_circle_tangent`, 1-D sobre la bisectriz, RMS
    ≤ tol) y A/B salen de C + rectas + r (T = r·tan(Δ/2)), a ≤ slip del extremo
    del trazo curvo O del último vértice recto (entre ambos puede haber un
    hueco). Así lo que dibuja el editor (`model_ops.fillet_geo`, arco REAL con
    puntos de tangencia; antes era un quadTo simbólico de 40 px que el usuario
    leyó como «curva mal aplicada») y lo que genera el plugin (mismo T; ojo:
    recorta a 0.9·pata y baja el radio si no entra → el editor lo pinta a
    trazos) es exactamente el arco del PDF → vértice `fillet` = esquina C,
    `RecognizedPolyline.fillets[idx] = {a, b, center, r_px}`. `pipes_from_recognition(zoom=)` pone
    `pipe["fillets"] = {idx: radio_ft}` y `model_ops.attach_fillets` marca la CAJA
    de ese vértice como CV (`curve=True, radius_ft`) → `PDFCAD_CURVE`, igual que el
    codo manual. DU06 h.4: 4 codos (10–15 ft), h.3: 4 (curva compuesta, 14–29 ft),
    h.10: 1. Auditoría «no inventar» en `tests/test_recognition.py::_audit_fillets`
    (tinta curva del sector sobre el círculo ≤1 pt, tangentes sobre la recta de
    un guión ≤0.5 pt/±1° en h.4, editor = reconocimiento) y escenarios sintéticos
    en `tests/test_composite_dialog.py` (`_elbow_doc`: huecos/letra antes del
    arco, giros 30/60/120, arco a guiones, curva compuesta de dos radios).
**La TINTA manda (auditoría 2026-09-22)**: el círculo se
    ajusta a los vectores del PDF, no a la centerline simplificada —
    `ink_samples(paths, px)` muestrea los trazos de la capa cada 1.5 pt,
    `ink_by_polyline` reparte cada punto a la polilínea MÁS cercana (≤
    `FILLET_INK_CORRIDOR_PT`=2.5; sin esto una paralela cercana tuerce el arco) y
    `_span_members` toma solo la tinta del corredor de los vértices `curve` (si
    entra la de las rectas vecinas, el ajuste se va a 1.4 pt y el codo se pierde).
    Un codo además necesita tinta CURVA sobre el arco: `_arc_ink_cover` solo
    cuenta los puntos cuyo trazo está curvado como pide el radio
    (`_stroke_curvature_kind`: flecha propia ≥ `FILLET_SAG_RATIO`=0.5 de
    r − √(r²−(L/2)²); trazos < `FILLET_STROKE_MIN_PT`=12 pt o con flecha
    esperada < `FILLET_SAG_MIN_PT`=0.5 son «neutral» y tampoco suman) y exige
    ≥ `FILLET_INK_COVER`=0.45. Así un **chaflán** —el plano gira con dos
    guiones RECTOS y el quiebre en el hueco, DU06 h.4 en (571,1262), lo reportó
    el usuario— no se toma por codo, ni tampoco un quiebre con una astilla del
    plot. Ojo: una curva tan suave que ningún guión llegue a 0.5 pt de flecha
    (r ≳ 250 pt ≈ 70 ft a 1"=20') queda como polilínea a propósito. Con tinta, el control de calidad es el
    RMS del ajuste (`dev_px`), no la distancia a la centerline. **Curva que MUERE
    en un nodo** (`NODE_KINDS_END`: tee, junction, vault, stop, edge, end, cut):
    sin segunda recta, `_fit_circle_through` busca el círculo tangente a la recta
    que llega y que PASA por el nodo (1-D sobre la tangencia, mejor ajuste a la
    tinta) y `_close_at_node` cierra la esquina con la tangente en el nodo →
    `fillets[idx]["node_a"/"node_b"]` (la auditoría no les exige tangente sobre
    un guión: ahí no hay recta después). **Rectas «libres»**: la línea que PASA
    por un tee se extiende a los dos lados, así que no se le aplica el orden
    P…A…C…B…N y, si la tangencia cae más allá del nodo, el vértice se escribe en
    la tangencia (`_leg_vertex`) — si no, el tramo recto queda más corto que T y
    el plugin recortaría el radio. `_try_span` prueba todas las combinaciones de
    recta y se queda con la de menor error; `_accept` centraliza las
    comprobaciones. Cadenas `curve, nodo, curve` (o dos nodos a ≤40 pt) que no caben en un
    círculo se parten en sub-ristras (`_sub_spans`, cola de intentos); un vecino
    a ≥`FILLET_CHORD_LEG_MIN_PT`=40 del trazo curvo es fin de recta (ancla), no
    miembro del arco; una cuerda que termina en un vértice `curve` solo sirve de
    recta si mide ≥40; una «recta» <`FILLET_LEG_MIN_PT`=18 sin guión anterior
    colineal ni línea pasante que la confirme no es recta; dos tramos cortos que
    siguen girando tampoco; el arco entero debe ir a ≤`FILLET_ARC_DEV_PT`=1.5 de
    la polilínea. `through_dirs` = dirección de la línea que PASA (por el
    interior de un tramo o por un vértice colineal de otra polilínea; un ramal
    que muere ahí no cuenta) por un tee/junction: si es el extremo de la
    polilínea, tangencia FIJA en el tee (r = T/tan(Δ/2)); si no, confirma la
    dirección de la recta. **2.º intento `FILLET_LOOSE_TOL_PT`=3** (curvas «a
    mano»: polilínea de cuerdas / espiral): `fillets[idx]["loose"]=True`, preview
    a trazos y aviso con el desvío; con el ajuste a la tinta ya no hace falta en
    el DU06 (0 aproximados). Codos consecutivos: C2 debe estar sobre la recta de
    salida de C1. DU06 hoy: 17 codos en todo el PDF (h.3 = 6, h.4 = 9, h.15 = 2),
    ninguno aproximado ni recortado por el editor/plugin (tras el filtro de
    chaflanes: 15, h.3 = 6, h.4 = 8, h.15 = 1); lo que queda como
    polilínea son chaflanes y curvas compuestas (aviso «Curvas que quedan como polilínea»)) y `_vaults_geometry` (geometría real de bóvedas, `VAULT_MIN_FT`=2:
    cajas de paso/postes no cuentan; `Vault.layer` + `is_vault_ocg` → `importable`:
    una bóveda SIN línea de capa VALT/MANH (o lazo en la capa de la línea) se
    importa como CAJA suelta `standalone=True` — `attach_vault_geometry` la crea,
    `rebuild_structures` la conserva como a las `world`, el lienzo la pinta con
    el color de la utilidad; las U-PROP/POLE/PBOX (`NON_VAULT_TOKENS`) no).
  - `recognition_summary.py` (PURO) + `recognition_summary_view.py` — resumen
    VISUAL de la vista previa (lo pidió el usuario: «evitar mucho texto»):
    `classify_warning` pasa cada aviso de `recognize_page` a `Notice` (nivel
    problema/revisar/info + etiqueta corta; el texto completo va al tooltip; un
    aviso SIN regla cae en «revisar» — al agregar un `warnings.append` nuevo en
    `recognition.py`, sumar su regla en `_RULES`); `SummaryPanel` = 4 tarjetas +
    barra por utilidad (activas sólidas / AB rayadas, misma escala) + «Revisar» +
    «Detalles» plegado. Tests: `tests/test_recognition_summary.py`.
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
    una línea de red ATRAVIESA la bóveda (corrida partida en Fase A **por ESA
    bóveda** —`Run.split_vi`; una pieza partida por otra bóveda no cuenta, si no
    el nodo caía en una esquina de la segunda y las llegadas daban un rodeo por
    el borde: DU06 h.3—, o dos llegadas colineales opuestas) y se calcula con las llegadas: sobre la que
    atraviesa (intersección si son dos), nunca con el círculo/cajita del símbolo
    (`Vault.reference` queda informativo). Las demás llegan al nodo por su eje +
    `bend` corto. Sin línea que atraviese, cada llegada termina en el borde con
    `stop` (CAJA visible ahí; el usuario completa a mano). **Nada inventado
    alrededor de la bóveda (auditoría 2026-09-22, abanico de la hoja 3)**: una
    llegada solo se une al nodo si éste queda sobre su eje con un quiebre corto
    (`_perp_line(r.line(s), P) ≤ VAULT_BEND_OFF_FRAC`=0.5 × lado menor; medido en
    el DU06: llegadas buenas ≤0.46, el abanico iba de 0.56 a 1.6), si no para en
    el borde; el nodo se clampa DENTRO del recuadro (sobre la línea que atraviesa)
    — antes `bb_reach` lo dejaba salir un hueco del linetype y las llegadas
    formaban un triángulo fuera de la caja; y `entry_point` no prolonga un extremo
    más de `pat.join_gap` hacia la bóveda (29 pt sin tinta en la h.3).
    `tests/test_recognition.py::test_du06_ningun_tramo_sin_tinta_debajo` audita las
    19 hojas: todo segmento >6 pt fuera de una bóveda tiene tinta debajo.
    **Perfil drenaje (auditoría 2026-09-23, DU06 h.4)**: `recognition.
    UTILITY_GEOM_OPTIONS["DRENAJE"]` = `geom.GeomOptions` con tres reglas que el
    eléctrico NO usa (con ellas cambiaba en 7 hojas; sin ellas, 0 diferencias
    vértice por vértice en las 19): `separate_vaults` (dos contornos ≥8 pt con
    hueco ≥1.5 pt no se funden), `nearest_vault` (un extremo va a la bóveda que
    lo CONTIENE o donde entra más cerca, solo entre bóvedas que no se solapan —
    los contornos anidados alrededor del manhole siguen el orden de siempre) y
    `absorb_inside_runs` (un guión corto dentro de otra corrida y sobre su recta,
    ±3°, se funde: si no, el tramo salía doble). Además `duplicate_ocgs` (solo
    `DEDUP_OCG_UTILITIES`): la misma capa corta repetida por otro xref (≥90 % de
    trazos a ≤0.5 pt) se reconoce una vez y sus trazos propios se suman a la
    conservada. `C-STRM-UNGD-*-NPLT` SÍ es centerline (está impresa); `-CASE`
    (camisa) y `-WALL` no. Eléctrico de otros paquetes (DU08/DU10): `C-ELEC-
    (<paquete>-)?UGND…` = línea PROPUESTA «—E—» (leyenda: existente = letra
    minúscula a trazos, propuesta = MAYÚSCULA continua, «/» abandonada, «//» a
    abandonar = capas `-D`); `C-ELEC-UNGD-WALL-N` fuera. Hojas «aplanadas» (0 %
    de vectores con capa): `pdf_layers.page_uses_layers` (busca `/OC` en el
    contenido y XObjects, ~10 ms/hoja) → el compositor las marca «sin capas».
    **DU08 h.39 (2026-09-23)**: sin paso aprendido en la capa (<3 marcadores),
    una línea con ≥2 «/» a ≥`MARKER_LOCAL_MIN_PT`=30 define su paso
    (`marker_pattern`, `local`); `split_offpattern` → `_continues_line`: un
    trazo largo que sigue DE FRENTE (±35°, ≤ `join_gap`) el guión anterior no es
    leader (en una curva a guiones cada guión es su corrida y ninguno es «ancla»).
    Capas `-D` → aviso propio (`is_to_abandon_ocg`), siguen activas hasta que el
    usuario decida. Antes de
    tocar el núcleo compartido: foto del eléctrico en las 19 hojas y diff.
    `_split_by_fit`
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
    (el DU06 dibuja el contorno de la bóveda abandonada en `C-ELEC-UNGD-A`);
    `_rect_geometry` le da contorno/medidas/giro como a las activas y
    `recognition._vaults_geometry` la marca `abandoned=True` (lazo ≥4 paths,
    con contorno, sin `ref`); `model_ops.attach_vault_geometry` cae al CAJA
    más cercano DENTRO del contorno si no hay ninguno a ≤12 px del centro (la
    línea abandonada muere en el borde con `stop`). Marcadores: barras hasta
    `MARKER_MAX_LEN_PT`=18 (las > `GLYPH_MAX_DIM_PT` solo si cruzan la corrida
    por el interior o hay guiones colineales a ambos lados: el tick «|» de fin
    de tramo se conserva); un «//» en un solo path zigzag no es codo porque
    `classify_paths` exige giros ≤ `CODO_MAX_VERTEX_TURN_DEG`=60. **Veredicto
    abandonada (regla del usuario)** = capa `-A` **Y** patrón: `GeomResult.markers`
    guarda las barras y `marker_pattern(polylines, markers)` aprende el paso
    (≥`MARKER_MIN_AGREE`=2 espaciados iguales ±15 %+3 pt; «//» a ≤`MARKER_PAIR_PT`
    = un marcador) y juzga cada polilínea: True (marcadores a paso 1× o 2× desde
    ≤1.5 pasos del inicio hasta ≤1.5 del final), False, None (más corta que el
    paso → hereda el veredicto de la capa). `recognize_page` lo calcula sobre
    las RUTAS (joined y raw) por OCG; DU06 h.9: paso 67.7 pt, línea de 282 pt
    True + 3 stubs None → 4 (AB). Capa `-A` sin patrón → se importa activa con
    aviso; patrón en capa activa → solo aviso.
    **«//» = abandonada en CUALQUIER utilidad y capa** (regla del usuario
    2026-09-25; DU08 h.21 agua `-D`): `MarkerPattern.doubles` (mayoría de
    marcadores de 2 barras) y `double_verdict` (solo los dobles, ≥75 % de pasos
    a 1×/2× el periodo — `MARKER_DOUBLE_STEPS_OK` —, dobles a ≤2 pasos de cada
    punta; sin «//» propio y corta → None = hereda la capa). La «/» simple sigue
    exigiendo capa `-A`.
    `Vault` trae además la geometría REAL del símbolo (`_fill_vault_geometry`: el
    path cerrado más grande del clúster → `outline` 4 esquinas con giro, `width`/
    `length` pt, `angle_deg` rumbo del lado largo, o `shape="circle"`); `recognition`
    la pasa a px + pies en `RecognitionResult.vaults_geo` y el preview la pinta.
    **Auditoría de líneas cercanas (2026-09-19)**: paralelas a ≥2 pt quedan
    separadas; el defecto era 5d-bis (convergencia rasante) que enganchaba como
    T una paralela que solo TERMINA al lado → ahora exige que la corrida se
    acerque ≥`GRAZE_MIN_APPROACH_PT`=2 pt (tests `test_paralela_que_termina…`).
    Un trazo continuo que solo nace en el borde de una bóveda no forma
    «through virtual» con la línea del lado opuesto (sí si la cruza).
    **T-ends** (`resolve_nodes`, pre-pasada tras la Fase A): un extremo que
    muere a ≤`NODE_OFF_LINE_PT` de otra corrida recta, en su interior, sin
    continuación colineal enfrente ni otro extremo pegado, es una T con ESA
    corrida (no llega a bóvedas vecinas, no forma esquina con terceros:
    5c-bis). Un tick corto sobre el que muere otra corrida queda «capped»
    (sus puntas son extremos puros: ni esquina, ni T, ni prolongación). `slide_ok`: ninguna esquina/T desliza un
    extremo más de media corrida. `SOFT_SIMPLIFY_PT`=0.5 para bend/corner (era 1.5: dejaba la centerline hasta 1.5 pt fuera de los guiones en quiebres suaves),
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
    hojas»; sus entradas ya no están en el menú Ver, los métodos siguen para
    proyectos viejos). `composite.py` es PURO (solo
    fitz): `Piece` (PDF origen, hoja, `clip` normalizado sobre la hoja visible,
    `x,y` en pt de la hoja compuesta, `rotation` ANTIHORARIO como `show_pdf_page`,
    `src_scale` pies/pt) y `Composite` (piezas + `scale_ft_per_pt` única; cada
    pieza se escala por `src_scale/target`). Botones conmutables del compositor:
    `_tool(checkable=True)` pone la propiedad `toggleTool` (QSS en `theme.py`:
    activo = verde + icono claro; `QPushButton[secondary="true"]` = acción
    secundaria neutra, la usa el preview en su cuadrícula 2×2) y `_notify_taken` muestra 5 s «✔ Área tomada
    como pieza N» en el panel 2. `piece_map` reproduce exactamente el
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
    hasta 8 pt por dentro (solo alinean/puentean). `trim_border` lleva cada lado
    del clip al CENTRO de la match line / marco pegado a él (trazos paralelos
    ≤14 pt del lado agrupados por coordenada ±1.25 pt, `_collinear_lines`, que
    cubran ≥35 % del lado; también a GUIONES gruesos: DU06 hoja 14 x=349/350 y
    1609/1610, ancho 1.98; ≥3 paralelas = grilla, no se recorta) y devuelve
    `covers` {lado: ancho}: franja BLANCA que tapa la tinta (ancho/2 + deriva +
    0.3). Cortar por el centro no pierde vectores (los de debajo de la tinta
    siguen en el XObject); `build_document` dibuja las franjas sin capa tras cada
    pieza (el reconocimiento no las ve) y `PieceItem` las pinta como hijos. Con
    esto DU06 hojas 13→14 unen borde con borde: traslación pura (−5.55 pt en y,
    giro 0.01°). OJO: 14→15 NO son contiguas así. Costura milimétrica: la franja
    sale `COVER_OUT_PT`=0.5 por FUERA del borde (si no, el píxel de la costura
    queda gris por el antialiasing de ambas piezas: medido 152/255 → 255); los
    anclajes de un lado con franja se toman en su borde INTERIOR (`insets`,
    `Anchor.inset`) y los puentes completan encima de la franja las líneas que
    cruzan; el imán: `coincide_delta` (extremos enfrentados que coinciden, sin
    los `inset`) → `edge_snap_delta` (rectángulos borde con borde) + colineal
    solo a lo largo de la costura → `refine_delta` (mínimos cuadrados 2D sobre
    parejas mutuas; None en el eje que las líneas no determinan) → **costura por
    MATCH LINE** (`_seam_align`, auditoría 2026-09-22): las dos hojas contiguas
    dibujan LA MISMA raya de la costura, así que `seam_line_extent` (la línea
    larga paralela al borde, ≤`SEAM_LINE_TOL_PT`=10 pt de él, recortada a la
    franja de la pieza y ≥25 % de su alto) + `seam_line_delta` (mismos largos
    ±2 pt) dan el desplazamiento EXACTO a lo largo de la costura; si no hay,
    `seam_along_delta` usa los extremos enfrentados con ≥`SEAM_MIN_PAIRS`=3 de
    acuerdo y hasta `SEAM_ALONG_TOL_PT`=90 pt. Esta etapa corre SIEMPRE, también
    tras el imán de coincidencia (etapa 1), porque dos extremos que coinciden
    pueden ser el guión equivocado. Sin ella, si cada hoja se recortaba a distinta
    altura (el imán de líneas engancha una guía distinta en cada una) el desfase
    quedaba tal cual: DU06 h.13→14 daba −25.5/−43.5/+18.2 según dónde se soltara
    la pieza, cuando la match line 519+00 (378 pt en las dos hojas) dice −34.51.
    **Costura EXACTA (`composite_seam.py`, auditoría 2026-09-24, «grada» en las
    diagonales de DU06 13→14)**: `_seam_align` prueba primero `_seam_exact`:
    A TRAVÉS, las dos match lines coinciden (`seam_rule`: la línea MÁS GRUESA a
    ≤30 pt del lado, por dentro o fuera, ajustada como recta — va inclinada
    0.23° en el DU06—; las cotas de papel de 0.72 pt a 20/40/60 pt de ella, en
    espejo en cada hoja, no cuentan; `rules_match` = mismo grosor); A LO LARGO,
    `seam_votes` sobre segmentos IDÉNTICOS (capa, largo, rumbo) de la franja
    ±45 pt de cada costura, restringidos a esa traslación a través ±1.5 pt
    (`translation_from_votes`: ≥5 votos de ≥2 capas y pico 1.5× el segundo; su
    «a través» manda: las match lines pueden ir 0.4–0.7 pt corridas). Sin la
    restricción ganaban picos falsos (cotas espejadas, parquímetros
    `V-PKNG-METR`). La franja de votos va centrada en la MATCH LINE, no en el
    corte. Un segmento con varios gemelos a tiro reparte su voto (1/n: LABOE
    h.9→10 repite cada 108 pt); hoja sin capas (DU08) → 2× votos en vez de ≥2
    capas. Sin dibujo compartido (LABOE h.8→9, 10→11; DU06 3→4…): CONTINUIDAD
    (`rule_crossings`/`crossing_votes`: cada línea que llega a la match line o
    la cruza, prolongada hasta ella; pareja = misma capa y rumbo ±0.3°). Si
    tampoco: match lines a través + el imán de siempre a lo largo, y se
    recalcula el «a través» (inclinación). `trim_border` ahora mira
    también ±band por FUERA y elige la línea más gruesa (clusters por grosor);
    antes un lado 4 pt corto de la match line dejaba 8 pt de plano fuera; una
    línea ≥`TRIM_HEAVY_MIN_W`=1.2 pt se alcanza hasta 2× la banda, y la MATCH
    LINE (`_match_line_among`: gruesa, A GUIONES, fuera de capas de utilidad
    —`is_utility_layer`—, la más gruesa del lado y 1.5× cualquier otra a guiones)
    hasta 6.5× (91 pt) y aunque las cotas parezcan grilla: el área puede quedar
    sobre la cota de 60 pt o sobre el marco de la hoja (1.68 pt continuo, 71 pt
    afuera en DU06 h.6). `guide_lines` lleva el grosor (5.º campo) y
    `snap_edge` pesa cobertura × grosor: en el DU10 la cota fina cubre MÁS que la
    match line (349 vs 301 pt) y el área saltaba a la cota. `seam_rule` exige
    ≥`SEAM_RULE_MIN_WIDTH`=1.2 (dos cotas finas en espejo coinciden entre sí y
    dan una costura falsa), sin capas de utilidad, ≤30 pt del lado o ≤90 si va a
    guiones.
    Auditoría: `scripts/audit_costuras.py` (pares contiguos por estación «MATCH
    LINE STA», verdad independiente: vectores idénticos o continuidad; 54
    uniones por par; hoy 78/78 pares sin error en DU06/DU10/DU08/LABOE, ~40 min)
    — correrlo antes de tocar el imán; tests `tests/test_composite_seam.py`.
    `page_segments` cachea el escaneo de la hoja (`_segs_cache`) para que el imán
    siga siendo instantáneo al arrastrar (1-5 ms). Todo escaneo de vectores pasa
    por `composite.page_drawings(page)` (caché de `get_drawings` en el propio
    documento, clave con el estado de capas): antes cada función lo releía
    (~0.6 s/hoja) y la primera unión congelaba la UI ~5 s; `CompositeView.
    _warm_seams` prepara las match lines al agregar la pieza (unión: 27 ms). Puente =
    `Bridge.polyline(rect_a, rect_b)`: cada extremo sigue RECTO por su dirección
    hasta el borde de su pieza (`_ray_exit`) y ahí cierra; `bridge_segments_poly`
    mantiene el patrón de guiones por la polilínea (ojo: guardas 1e-6 contra
    pasos nulos de coma flotante — colgaba). Medir con render 8× por columnas;
    DU06 13→14: desvío lateral por línea mediana 0.03 pt, máx 0.09 pt.
    `guide_lines` lista las líneas generales de la hoja (h/v, ≥40 pt de cobertura,
    con guiones) y `snap_edge` elige a cuál salta un lado del área (≤ tol y
    solape; gana la de más cobertura); `_CropView` (sheet_crop_dialog) las usa al
    arrastrar y las resalta. Nitidez: `pdf_view_quality.ViewportSharpener` (panel 2)
    y `PieceItem.update_sharp` (todas las piezas a la vista, presupuesto de píxeles
    repartido) re-renderizan solo la región visible como overlay. `recognition.
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
    agrupadas con su color, cada casilla del panel «Utilidades» APAGA/enciende
    todas las capas de esa utilidad en la hoja y filtra la lista (`_set_utility_visible`
    recuerda el estado por capa en `_util_memory` para reponerlo; el buscador solo
    filtra), y
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
    búsqueda por vértice (`pipe_at_vertex`), geometría de Multileader (`leader_geo`,
    recibe la conversión pies→px de la ventana) y `attach_vault_geometry`: copia a la
    CAJA más cercana (≤12 px) la geometría real de la bóveda reconocida
    (`VAULT_GEO_KEYS`: shape, width_ft, length_ft, rot_deg, outline en px; las
    huérfanas no inventan buzón; `rebuild_structures` los conserva por coordenada).
    El lienzo dibuja `outline` como polígono a escala y la medida al seleccionar.
    `Main` delega y solo asigna/dibuja.
  - `model.py` — constantes, `VERSION`, `CHANGELOG`, capas Z, tabs.
  - `dxf_export.py` — exporta el DXF con XDATA `PDFCAD`.
  - `civil_catalog.py` — lee el catálogo imperial de Civil 3D (familias/tamaños/GUID).
  - `geo/` — georreferenciación: `georef.py` (ajuste), `georef_dialog.py` (UI),
    `la_reference.py` (calles/parcelas de NavigateLA).
- Raíz — **pipeline de digitalización**: `config.py`, `vector_pipeline.py`,
  `raster_pipeline.py`, `digitize.py`, `detect.py` (`classify_page`: «vector»
  solo con ≥80 trazos Y evidencia CAD — texto ≥20 chars, fuentes u OCGs; un
  escaneo vectorizado (12k trazos calcados, 0 texto/fuentes/capas, fixture
  `tests/fixtures/escaneado_vectorizado.pdf`) es «raster» con `info["traced"]`
  y `Main._run_recognition_wizard` lo manda al dibujo manual; imagen ≥60 % de
  la página sin OCG = escaneo aunque lleve anotaciones vectoriales con texto).
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
    COVERED, NET_KIND, HEIGHT_FT, HIDDEN, SHAPE, WIDTH_FT, LENGTH_FT, ROT_DEG`.
    Los cuatro últimos (v1.2.0) llegan solo en bóvedas RECONOCIDAS del PDF
    vectorial: forma (`rect|circle`), ancho × largo en pies medidos del símbolo
    (pt × pies/pt) y rumbo del lado largo; vacíos en buzones manuales. El plugin
    aún no los usa (`XdStr` ignora claves extra) — candidato: elegir PART_SIZE por
    medidas y girar la estructura.
  - **Datos extendidos** (`app/xdata.py` puro + `app/xdata_dialog.py`, botón verde
    «Ver datos extendidos» junto a Eliminar, pestañas Utilidades y Buzones): cada
    pipe/estructura puede llevar `xdata = {"auto": {…}, "user": {…}}`. `auto` lo pone
    el reconocimiento (`pipes_from_recognition(origin=)`, `attach_vault_geometry(origin=)`):
    capa OCG de origen + lo que dice su nombre NCS (`parse_layer`: disciplina, sistema,
    ubicación UNGD/OVHD, estado N/E/A/D…, modificadores) + «PDF · Hoja N» (pieza de la
    hoja compuesta bajo el objeto, `Main._xdata_origin`; texto fijo en español: es dato).
    Es SOLO referencia: no cambia la utilidad (la línea sigue siendo DRENAJE/ELECTRICO)
    ni el reconocimiento. `user` = campos libres del usuario (no pueden llamarse como un
    campo auto). `rebuild_structures` copia `xdata` por coordenada; re-importar
    (`set_auto`) no borra lo del usuario. Van al .digproj tal cual y al DXF como claves
    extra de `PDFCAD_PIPE`/`PDFCAD_STRUCT`: `XD_CAPA_OCG, XD_XREF, XD_CAPA,
    XD_DISCIPLINA, XD_SISTEMA, XD_UBICACION, XD_ESTADO, XD_MODIFICADORES, XD_ORIGEN` y
    `XDU_<NOMBRE>` (ASCII, ≤250 car.). El plugin aún no las usa (candidato: Property Sets).
  - **Estándar de capas BOE/NCS** (manual en `Documentos/docs prueba/BOE_CADD_Manual_210610.pdf`,
    §8.1): DISC(1 letra + opcional subconjunto nivel 2)-MAYOR(4, relleno «~»)-menor(es)-ESTADO
    (A D E F M N T X, 1–9 fases). `recognition.standard_short_name` normaliza (quita «~» y la
    2.ª letra de disciplina: `CU-STRM-…` → `C-STRM-…`) antes de `classify_ocg`, que SUMA las
    formas del estándar (drenaje `C-STRM-UGND`, `C-STRM-PIPE…`; estructuras `-MHOL`, `-HWAL`)
    a las de los APDU sin cambiar ninguna: foto de las 1182 capas de los 5 PDFs de prueba
    antes/después = 0 diferencias (hacer lo mismo antes de tocar `classify_ocg`).
    Tests: `tests/test_layer_standard.py`. La lista completa de capas por disciplina es un
    anexo aparte que NO viene en ese PDF.
  - **«No inventar» con líneas juntas (auditoría 2026-09-24, DU08 h.21)**:
    `recognition.dedup_paths` quita trazos IDÉNTICOS (≤0.05 pt, también al revés)
    dentro de cada capa antes de reconstruir — DU08/DU10 traen capas enteras
    duplicadas (xref insertado dos veces): daban líneas de ida y vuelta y ticks
    de «dos guiones» que ya no eran `capped` y se prolongaban sin tinta. Núcleo:
    esquina solo si el ángulo INTERIOR ≥ `CORNER_MIN_INTERIOR_DEG`=73° (falsas
    ≤69.5°, reales ≥77° medido en DU06/08/10/LABOE; DU06 ninguna <75°); una curva
    no retrocede > `CURVE_BACKSLIDE_PT`=1 hasta su esquina (`slide_ok`);
    `learn_pattern` ignora «guiones» > `DASH_LONG_MAX_RATIO`=15× el largo más común
    (rayas de 731 pt del cajetín ganaban al deduplicar). `routes`: en un nodo T
    (extremo `tee`, la línea que pasa no crea extremo) solo se sigue de frente
    (35°). Red final: `_split_sharp` parte toda polilínea en un vértice < 73° (no
    `fillet`) antes de marcadores/tinta/codos. Verificación: foto de TODAS las
    hojas de los 4 PDFs antes/después (vértices en «V» 863 → 0, largos iguales
    donde solo se parte) + `test_recognition_no_inventar.py`.
    2.ª revisión (mismo día): un extremo que TOCA (≤`ENDS_TOUCH_PT`=1) el de otra
    corrida que sigue de frente (giro ≤35°) no va a la bóveda vecina (Fase B) si el
    toque queda FUERA de la caja (dentro es la línea que la atraviesa: DU06 h.9/h.12);
    y en T-ends el «trozo colineal enfrente» no cuenta si otro extremo lo mira mejor
    (suma de desvíos a ambas rectas): la curva que muere sobre la vertical no se
    apropia de la continuación de la diagonal que pasa por la «e».
    3.ª revisión (DU08 h.49): `stretch_ok` — en una esquina (5b) una corrida de UN
    guión (tick, patita de símbolo) no se prolonga más que max(su largo, ½ join_gap)
    salvo que haya un glifo de la capa en el hueco (`resolve_nodes(glyphs=)`; con el
    umbral de un join_gap entero volvía la vertical inventada de DU10 h.21, con ½ sin
    glifo se cortaban las líneas «e» de LABOE); un tick con T interior no es ruido
    aunque mida < `floor` (dos xrefs con su tick pegado: se veía una sola T);
    `strip_crossing_markers(attached=)` no toma por «/» un trazo que NACE en la punta
    de una curva (`MARKER_ATTACH_PT`=0.5). Foto: DU06 y LABOE 0 cambios.
    4.ª revisión (DU08 h.49, borde de la vista): la referencia viene RECORTADA justo
    en el clip (x=661.14). `_clip_chain` conserva un trozo que corre SOBRE el borde
    (sus dos puntas a ≤`CLIP_EDGE_TOL_PT`=0.25 y largo ≥0.5; una colita que cruza
    sigue fuera — con solo el punto medio se movían cortes 0.3–0.9 pt); `clip_path`
    marca como `cut_pts` los extremos que ya están sobre el borde, y un extremo
    cortado no es T-end (queda en su punta). `_cut_letter_strokes` (en
    `classify_paths`): grupo de ≥2 trazos cortos que se tocan con ángulo ≥60° y caben
    en una letra, repetido ≥`CUT_GLYPH_MIN_REPEAT`=3 veces con los mismos largos =
    letra partida → glifo. Foto: DU06 0 puntos movidos (solo «end»→«cut» en extremos
    del borde); cambios de geometría solo en DU08 h.36/37/49 y LABOE h.26 (revisados).
  - **Perfil AGUA (2026-09-24)**: `recognition.SUPPORTED_UTILITIES` = ELECTRICO, DRENAJE,
    AGUA; `DEFAULT_UTILITIES` (selección al abrir) sigue siendo Eléctrico+Drenaje — Agua se
    marca en «Capas de la hoja». Etiquetas: `UTILITY_LABELS`/`utility_label`/
    `utilities_label` (no volver a escribir «Eléctrico y Drenaje» a mano en la UI).
    `_classify_water`: línea `water_ungd` = `C-WATE?R[-_](paquete-)?(UNGD|UGND|PIPE)` sin
    ANNO/TEXT/CASE/FITT/APPT/VALV/METR/HYDR/-FH/-GV/WALL/…; estructura = V-WATR-VALT/MANH/
    STRU, V-FIRE-STRU, C-WATR-VALT/MANH/MHOL/STRC (válvulas, medidores, hidrantes =
    accesorios, no). Red a PRESIÓN (`NETWORK_KIND`): `Main._import_recognized_pipes` no
    llama `attach_vault_geometry` ni cuenta bóvedas importables para presión (como el
    dibujo manual: `rebuild_structures` no crea nodos en presión). Reglas del perfil
    (`GeomOptions`, SOLO agua): `join_touching_ends` (puntas a ≤1 pt se cosen primero;
    punta JUSTO sobre una línea = T aunque esté cerca de su extremo — el join_gap del agua
    llega a 70 pt), `gap_turn_blocks` (`build_runs` no cruza un hueco si en su borde nace
    otro trazo no colineal), `markers_on_curves` (`strip_crossing_markers(curve_chains=)`).
    Auditoría: `tests/test_water_profile.py`; 68 hojas sin tramos sin tinta ni «V»; foto
    eléctrico/drenaje de los 4 PDFs = 0 diferencias.
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
