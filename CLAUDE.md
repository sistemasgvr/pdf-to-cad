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
    usa «Para verificar» de la vista previa; el compositor ya no: va en pestañas); `NaturalHeightScroll` (scroll de
    un panel lateral que respeta el alto natural de su contenido)).
  - `ui_common.py` — constantes/helpers de UI compartidos (`DOWNLOADS`, estilos de
    botón, `layer_qcolor`, `swatch_icon`, …). Sin estado; los usa toda la app.
  - `side_panels.py` — los dos docks de la ventana (`Main._ldock` «Herramientas», `_rdock`
    «Inventario») se ocultan solos como las paletas de Civil 3D (pedido del usuario 2026-10-05):
    `AutoHidePanel` (`Main.panel_izq/panel_der`) pone una cabecera con chincheta; «ocultar
    automáticamente» mueve el contenido (los MISMOS widgets) a un `QFrame#panelOverlay` hijo de la
    ventana, encima del `centralWidget`, y deja una tira con `SideTab` (pestaña vertical) en su
    borde. Hover 250 ms o clic → se abre; se recoge con el ratón fuera 500 ms (sondeo cada 100 ms) o
    al hacer clic fuera (filtro de eventos de la app SOLO mientras está abierto), no con
    desplegable/menú/modal abiertos, botón del ratón apretado ni escribiendo en un campo del panel.
    Borde interior arrastrable (`_Grip`). Estado y ancho en QSettings («pdf-to-cad»/«app»,
    `panel_izq_auto`/`_ancho`…; las pruebas lo cambian por memoria en `tests/conftest.py`). Menú Ver
    `act_panel_izq/der`. OJO: con el panel recogido sus widgets NO están «visibles» → no usar
    `isVisible()` para lógica (`_prop_changed` usa `isVisibleTo(self.gprop)`).
  - `autoguardado.py` — copias automáticas y recuperación (pedido del usuario 2026-10-05).
    `Main.autoguardado` (`Autoguardado`) arranca SOLO desde `main()` con `Main.iniciar_autoguardado()`
    (las pruebas que crean la ventana no escriben nada): cada 2 min, si `_has_real_changes()` y la huella
    del modelo cambió, escribe en `%LOCALAPPDATA%/pdf-to-cad/recuperacion/<sesión>/` las partes del
    .digproj — `model.json` siempre; `page.png` (clave = `pixmap().cacheKey()`) y los PDF (copia del
    archivo `pdf_path`, o `doc.tobytes` si no hay archivo; `external/`, `sources/`) solo si cambiaron, en
    un HILO (`QImage.save` y `shutil.copyfile`, sin tocar fitz ni widgets); `meta.json` al final. Un
    `QLockFile` por sesión (`setStaleLockTime(0)`): si su proceso murió, `recuperables()` la ofrece
    (`dialogs.preguntar_recuperacion`: Recuperar/Descartar/Más tarde). Recuperar = `armar_digproj` →
    `_open_project_path` → `project_path` original y `_forzar_cambios` (sigue «sin guardar»). El setter de
    `_dirty` (False = guardado/abierto/descartado) llama `limpiar()`; `closeEvent` → `cerrar()`. Pruebas:
    `tests/test_autoguardado.py`; `tests/conftest.py` manda `PDFCAD_RECUPERACION` a una carpeta temporal.
  - `responsive.py` — controles para que los paneles NUNCA corten ni pidan scroll horizontal:
    `WrapButton`/`WrapCheckBox` (parten el texto en líneas; mínimo = palabra más larga; `text()` =
    texto completo), `ResponsiveGroupBox` (título con «…», no impone ancho) y `GridAdaptable`
    (filas de botones de 1 a N columnas según quepan). En los paneles: botones con texto → `WrapButton`,
    casillas → `WrapCheckBox`, grupos → `ResponsiveGroupBox`, filas de botones → `GridAdaptable`.
    `tests/test_paneles.py::test_nada_se_corta_al_ancho_minimo` recorre cada sección y pestaña a 300 px
    en español e inglés: un control nuevo que no quepa lo hace fallar.
  - `busy.py` — capa «Cargando…» (pedido del usuario 2026-09-29: que un paso lento no
    parezca congelado). `BusyOverlay` = hijo que tapa una ventana o una vista (atenúa,
    come ratón/teclado/atajos y el cierre, tarjeta con indicador giratorio + texto +
    detalle + barra i/n); `with busy(widget, texto):` para trabajo en el hilo de la UI
    (se pinta ANTES de empezar; `step()` repinta entre pasos: fitz no suelta el hilo) y
    `overlay_for(w).begin/end` para trabajo en otro hilo (reconocimiento, con
    `RecognitionWorker.progress` por utilidad; ahí `step(pump=False)`). Anidable (pila de
    mensajes). `Main._busy/_unbusy` la usan (abrir PDF/proyecto, guardar, cargar hoja).
    En el asistente: abrir el compositor (sus miniaturas ya se cargan de a una con un
    QTimer), cambiar de hoja/tomar área/agregar PDF, armar la hoja compuesta, leer capas,
    ◀ ▶ de «Capas» (y el re-render al marcar capas, solo si el anterior tardó >0.25 s),
    reconocer, preparar la vista previa e importar. Paso nuevo lento → envolverlo igual.
  - `workers.py` — hilos de fondo (`PipelineWorker`, `RecognitionWorker`).
  - `recognition_cache.py` (PURO) — el reconocimiento queda EN MEMORIA (pedido del usuario
    2026-10-06: con lo reconocido ya importado, Herramientas → «Componer hoja…» y seguir sin
    cambios reconocía todo otra vez). `Main._start_recognition` arma la clave
    (`_recognition_key`: sha1 de los PDF de origen, composición sin `last_view`, hoja, capas
    ocultas, utilidades, roles de «Ajustar capas…», `letters_off`, escala, zoom); si está en
    `_recog_cache` (las 4 últimas; se vacía al cerrar el proyecto) abre la vista previa con ese
    resultado (QTimer, como el hilo) sin `RecognitionWorker`. «Unir tramos» no va en la clave
    (`set_join_routes`). OJO: un parámetro NUEVO que cambie el reconocimiento se suma a
    `recognition_key`, o el caché devolvería un resultado viejo. Tests:
    `tests/test_recognition_cache.py`.
  - `respaldo_editor.py` — **Cancelar no borra el editor** (pedido del usuario 2026-10-07: con lo
    importado, Herramientas → «Componer hoja…» y Cancelar dejaba la hoja sin líneas: aceptar el
    compositor recarga la hoja —`_apply_composite` → `_load_page` → `_reset_model`— ANTES de Capas y
    de la vista previa). Si el editor tiene trabajo (`hay_trabajo`: líneas, estructuras, marcas,
    georref…; sin él todo sigue como antes), `compose_sheet`/`compose_scan_sheet` toman `Main._respaldo` (`tomar`: PDF de
    trabajo ABIERTO + su temporal, composición/capas, QPixmap y vista del lienzo, modelo, deshacer,
    `_dirty_flag`/`_clean_sig`); toda salida SIN importar (compositor tras volver de Capas, Capas,
    vista previa, error, nada que importar) → `_cancelar_asistente` → `reponer` (sin releer el PDF; la
    huella de guardado se repone tras el `_take_clean_sig` pendiente); importar → `_soltar_respaldo`
    (cierra el PDF viejo). Mientras hay respaldo, `_apply_composite`/`_cleanup_tmp_composite` no
    cierran ese PDF ni borran su temporal (`lo_guarda`). OJO: un atributo NUEVO de la ventana que el
    asistente cambie va en `respaldo_editor.CLAVES`, o «Cancelar» lo dejaría cambiado. «Ajustar
    capas…» cancelado vuelve a la misma vista previa (caché); escaneo con la misma composición
    (`_misma_composicion`) no recarga. Tests: `tests/test_respaldo_editor.py`.
  - `recognition.py` + `recognition_dialog.py` — asistente al abrir un PDF
    vectorial: componer hoja → capas → reconocer (perfiles Eléctrico, Drenaje, Agua y
    Alcantarillado; v1 fue eléctricas `C-ELEC-UNGD`;
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
    un guión: ahí no hay recta después). **Bifurcación de curvas** (DU08 h.26,
    2026-09-28): en el EXTREMO de la polilínea un `tee`/`junction` SIN línea pasante
    (`FILLET_NODE_PASS_KINDS`) también admite el arco — antes la guarda «sin recta
    tangente» lo tiraba y una «Y» de curvas partida en el nodo quedaba en cuerdas —; y
    el lado −1 de ese respaldo ya no invierte la recta (ya viene orientada hacia el
    arco; daba RMS 180 px). Foto DU06+DU08: +12 codos, 0 perdidos, todos sobre tinta
    curva. **Rectas «libres»**: la línea que PASA
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
    cajas de paso/postes no cuentan): TODA bóveda de `vaults_geo` es `importable` (pedido del
    usuario 2026-10-05: «se reconoció el buzón sin líneas y al importar no está»; antes las de
    capas U-PROP/POLE/PBOX/JUNCTION —`NON_VAULT_TOKENS`, hoy solo clasifica— y todas las de
    agua/gas quedaban fuera: 129 en los 4 PDFs). Una bóveda SIN línea se importa como CAJA
    suelta `standalone=True` — `attach_vault_geometry` la crea, `rebuild_structures` la
    conserva como a las `world`, el lienzo la pinta con el color de la utilidad. En agua/gas
    (red a PRESIÓN) toda bóveda es suelta y, rectangular, SÓLIDO (`model_ops.SOLID_NETS`); el
    DXF exporta los sólidos de presión y el plugin los dibuja (no cuentan como «nodos de
    presión descartados»). Foto antes/después (4 PDFs × 6 utilidades): 129 → 0 sin importar,
    ninguna estructura previa movida ni quitada, líneas idénticas.)
  - `recognition_arcs.py` (lee la tinta) + `recognition_arc_plan.py` (`ink_fillet_plan`:
    rectas, nodos, ajuste y anclas), PUROS — **2.ª pasada de codos desde la TINTA** (2026-09-28,
    pedido del usuario: «toda curva, mínima o muy abierta, en todas las utilidades»; caso
    DU08 h.26: ramal de telecom que sale TANGENTE a la vertical y termina libre, quedaba
    `end, curve, corner, curve, end`). AutoCAD exporta cada arco APLANADO con flecha
    constante ~0.025 pt (cuerda ≈ √(8·r·0.025): 1.3 pt en r=7, 5.5 en r=150, ~14 en
    r=1000) y cada recta como UN segmento: `arc_pieces` saca de los trazos de la capa los
    trozos de arco (ristras de cuerdas parecidas, ±1.6×, que giran 0.15–20° al mismo lado;
    vértices sobre el círculo ≤0.12 pt) y las rectas de tinta; descarta la tinta dentro de
    las cajas de letras/marcas que reconoció el núcleo (`GeomResult.glyphs`, campo NUEVO
    solo de salida; sin esto la panza de una «S» de «SS» se tomaba por arco);
    `assign_to_polylines` reparte por polilínea; `group_arcs` junta los trozos del MISMO
    círculo (RMS ≤0.1 pt, huecos/letras ≤60 pt) si corren sobre la polilínea y con su
    rumbo. `ink_fillet_plan`: por arco, rectas = RECTAS DE TINTA exactas (alineadas con la
    tangente del arco), la línea que PASA por un extremo (`through_ink`: también extremos
    `end` apoyados en otra línea) o el NODO donde muere la tinta (extremo, corte, tee,
    bóveda) si entre el fin del arco y el nodo no hay tinta recta; círculo tangente
    (`fit_circle_line_node` sembrado con la tinta: en curvas abiertas la tangencia cae
    lejos del nodo), tangencias ENTRE el fin de la tinta curva y la punta de la recta
    (desvío d²/2r ≤0.75 pt si caen dentro), tinta sobre el arco ≥45 %, sin tinta recta
    de la propia polilínea dentro del arco que se aparte >0.75 pt (línea POLIGONAL). RMS
    ≤0.5 pt exacto; ≤1 pt (desvío ≤1.5) = `loose` (a trazos + aviso). Anclas: último
    vértice antes de A / primero después de B; si es blando se lleva SOBRE la recta de
    tinta (a la tangencia si caía dentro); dos codos con la recta del medio comparten
    ancla, puesto entre B1 y A2 (la «U»). Los vértices quitados/movidos quedan ≤1.5 pt de
    la forma recta–arco–recta. Al final cada codo se RECALCULA como lo dibuja el editor
    (`_editor_geo` ≡ `model_ops.fillet_geo` con los anclas definitivos; si la tangencia se
    pasa ≤1 pt del ancla —arco que muere en un nodo— se ajusta el radio) y se revalida
    contra la tinta: editor = plugin = reconocimiento, sin recortes. Las rectas de
    tinta se AJUSTAN con todos los guiones colineales (`_refine_line`, ≤0.3 pt, ±1°: el
    rumbo de un guión corto trae ±0.25° de cuantización). Curva en «S» junto a un codo
    de la 1.ª pasada con la MISMA recta (DU08 h.26, 2.º reporte): su ancla se comparte
    deslizándolo sobre la recta del codo viejo (`_anchor_shared_p1`; un vértice
    INTERIOR de un codo viejo nunca es ancla). `fit_to_editor` (en `recognition_arcs`,
    usa `model_ops.fillet_geo` con topes 1.0/0.48): si el editor recortaría un codo
    (también de la 1.ª pasada) por ≤1.5 pt de tangencia, se ajusta el radio al máximo.
    **Editor/DXF (mismo reporte)**: una estructura CV pertenece a UN vértice, el más
    cercano entre todas las tuberías (`model_ops.curve_vertex_indices`, `nearest_vertex`,
    `pipe_at_vertex` = el más cercano). Antes cualquier vértice a ≤14 px de una CV era
    «curvo»: con dos esquinas a 13 px el lienzo dibujaba una curva con la esquina y el
    radio de la otra, y un ancla recta a 13.6 px de su esquina recortaba el radio (tope
    0.48) y salía en NO_MANHOLE_VERTS (el plugin le ponía una curva de radio automático).
    `tests/test_curvas_editor.py` comprueba, en la ventana real, que cada codo de DU08 h.26
    se dibuja con sus tangencias reconocidas (≤0.1 pt) y sin recorte. La 1.ª pasada NO cambia (sus vértices quedan bloqueados;
    `fit_fillets(arcs=None)` = comportamiento anterior) y `relabel_false_curves` marca
    `corner`/`bend` los `curve` sin tinta curva cerca (esquinas de agua/gas: el aviso
    «curvas que quedan como polilínea» solo cuenta curvas reales). Auditoría:
    `scripts/audit_curvas.py salida.json [--sin-tinta]` + `--diff` (6 utilidades × 4
    PDFs, ~5 min): codos, precisión p90 de la tinta curva sobre cada arco, curvas que
    quedan como polilínea con su motivo y tinta curva sin arco. Foto 2026-09-28 vs 1.ª
    pasada sola: eléctrico 429 → 986 codos, telecom 86 → 501, drenaje 2 → 6,
    alcantarillado 0 → 8, gas 0 → 1 (p90 mediana 0.04 pt); 0 codos previos quitados;
    «curvas que quedan como polilínea» 876 → 242. Se prueban TODOS los candidatos en
    orden (loose, RMS) hasta uno con anclas válidas (si un nodo cae dentro del arco, el
    arco que pasa por el nodo). Dos codos nuevos consecutivos pueden compartir un NODO
    como ancla si ya está entre sus tangencias (no se mueve; DU08 h.39). Tests:
    `tests/test_recognition_arcs.py`, `tests/test_curvas_editor.py`.
    **Codo casi en «U»** (2026-09-30, DU06 h.5 telecom 178.7°: esquina a 2514 px, fuera de la
    hoja): `fit_fillets` termina con `recognition_trace.split_wide_fillets` — giro ≥
    `WIDE_FILLET_DEG`=150° → DOS codos de Δ/2 del MISMO círculo, unidos en el punto medio M
    del arco por un vértice `bend` (formato de `_encode`); `split_b`/`split_a` marcan ese lado
    (tangente del arco, sin guión recto: la auditoría no la exige). Solo si `fillet_geo` dibuja
    las dos mitades EXACTAS (A, M, B, centro, sin recorte) y ningún vecino es otro codo. Foto
    1799 codos (4 PDFs × 6 utilidades): 0 entre 120° y 170°, 1 ≥170° (ese). Tests:
    `tests/test_codos_abiertos.py`.
    **DU10 h.3 (2026-09-30, «curvas que quedan como polilínea»)**: (1) `fit_continuous.gap`
    solo fija los extremos que son EMPALME con un trazo validado; el extremo propio de la
    polilínea puede moverse como sin parche (un tee a la tangencia de su línea): antes se
    descartaba el reajuste entero y se perdía un codo r=126 pt. (2) `recognition_arcs.
    dash_arc_ends`: un «trozo» de DOS cuerdas muy distintas (3 puntos siempre caben en un
    círculo) = arco que nace/muere DENTRO de un guión recto → (cuerda corta = arco, cuerda
    larga = recta). En `ink_fillet_plan(arc_ends=)`: la corta suma cobertura si va sobre el
    círculo (≤`ON_ARC_TOL_PT`=0.25) y la recta del guión se APARTA ≥`END_DASH_LEAVE_PT`=1
    (en arcos muy abiertos un guión recto no se distingue del arco: LABOE h.29 empeoraba);
    la larga es recta del codo SOLO en un lado sin otra recta de tinta y si llega al FIN de
    la línea (en una «S» la recta del medio le quitaba las anclas al otro codo: DU08 h.22).
    No entra en la lista global de rectas (`_refine_line` movía radios en 50 hojas). Foto
    846 hoja×utilidad: cambian 4, todas a mejor (DU10 h.3/4, DU08 h.40, DU08 h.35).
  - `recognition_ends.py` (PURO) — **dónde TERMINA cada línea** (pedido del usuario
    2026-09-28, DU08 h.26), sobre la salida del núcleo sin tocarlo:
    `trim_inkless_tails` (coords PDF, antes de `build_routes`): un extremo tee/junction
    cuyo tramo final no tiene tinta PROPIA (≤2.5 pt y paralela ±25°: la línea a la que
    llega no cuenta) más larga que el hueco simple + 1 pt y sin letra suya (una letra
    centrada sobre OTRA línea de la capa no vale: la «t» de la línea de abajo) se recorta
    donde termina el trazo (su punta proyectada) → `end`. `extend_to_cut` (px, en `_emit`
    DESPUÉS de `fit_fillets`: prolonga la recta del codo; antes, la cuerda de la curva, y
    se perdían 7 codos): un extremo `end` sigue su recta hasta el borde del polígono de
    recorte de su capa (`path["clip_polys"]` de `gather_paths`: clip de la vista y, en la
    hoja compuesta, el BBox de cada pieza) si cada tramo sin tinta propia ni letra suya
    centrada encima (±1 pt) mide ≤ hueco simple + 1 pt (≤40 pt en total); otra línea de
    la capa sobre la prolongación la bloquea → `cut`. Hueco simple (`_plain_gap`) =
    max(gap_max − letter, gap_max/2), o gap_max si la capa no tiene letras (su `letter`
    es el 5 pt por defecto). Foto 4 PDFs × 6 utilidades: ~700 extremos al corte (mediana
    4.6 pt, todos letra/hueco junto al borde), 27 colas recortadas (14 casos, revisados:
    tramos sin tinta de su capa, a veces cubiertos por OTRA capa —-A→-E, -E→-D—), codos
    sin cambios salvo los ramales recortados. En la hoja compuesta DU06 13+14 alineada no
    queda ningún corte en la costura (las líneas se unen antes, en el núcleo). Tests:
    `tests/test_recognition_ends.py`.
  - `recognition_vault_snap.py` (PURO) — **imán de puntas a bóvedas** (pedido del usuario
    2026-10-01, captura de un SÓLIDO eléctrico de DU06 h.5: «las líneas quedan separadas del
    buzón… que se una solito, sin alterar el reconocimiento, solo bien cerca»). Paso APARTE al
    final de `recognize_page` (tras `_vaults_geometry`, sobre `polylines_joined` y `_raw`): el
    núcleo corta la llegada en el recuadro del CLÚSTER +1 pt (`v.bbox(1.0)`, o el círculo +1),
    así que la punta «stop» quedaba ~1 pt FUERA del contorno; a zoom 3.5 (editor) son 3.5 px y
    `attach_vault_geometry` (±2 px) no veía la llegada → caja SUELTA en el centro (235 de 604
    bóvedas con línea). `snap_ends_to_vaults`: punta «stop» (≤`SNAP_STOP_PT`=3 pt, adelante o
    atrás si la línea pasó por encima) o «end» (≤`SNAP_END_PT`=1.5, solo adelante) → el cruce
    MÁS CERCANO de SU recta con el contorno (`corners`, girado, o `circle` = anillo dibujado:
    `Vault.circle`, campo NUEVO solo de salida del núcleo) y queda «stop». No se mueve: punta
    dentro de un contorno, recta que no lo corta (de costado/esquina), rumbo poco fiable
    (`end_direction`), recorte que pase el vértice anterior o entre en el arco de un codo
    vecino, ni punta que coincide con otra línea salvo que todas vayan al MISMO punto (grupo).
    Bóveda «sin línea» a la que llega una punta pasa a `orphan=False` (y su punto sale de
    `vault_orphans_px`); aviso «Puntas unidas a su bóveda (imán): N» (info, clic → cada punta,
    `vault_snaps_px`). `model_ops._dentro_de_boveda`: el import reconoce también el ANILLO de
    un buzón redondo (la BZ de la punta se lleva el buzón; antes quedaba otra BZ suelta al
    centro). Foto 6 utilidades × 4 PDFs (846 hoja×utilidad): 626 puntas (eléctrico 225,
    drenaje 156, alcantarillado 119, telecom 114, agua 12), mediana 1.0 pt, máx 3.0; ningún
    vértice interior ni codo distinto. Import (zoom 3.5): caja unida a la línea 366 → 581,
    suelta 235 → 18 (nodos de varias líneas fuera del contorno y bóvedas anidadas: no se
    tocan), estructuras 3993 → 3838. Tests: `tests/test_recognition_vault_snap.py`.
  - **Reporte DU06 h.4 (2026-09-29, cuatro casos, TODAS las utilidades)**:
    `recognition_dupink.py` (PURO) — la MISMA línea dibujada dos veces en la misma capa
    con el linetype desfasado (banco de ductos `N-COMM-DUCT-BANK-PL`: dos entidades
    superpuestas; salían dos polilíneas encimadas con T y empalmes inventados, «la línea
    está doble»). `trim_repeated_ink` (en `recognize_page`, tras `dedup_paths`): de los
    trazos más cortos se recorta lo que corre SOBRE un trazo más largo de la capa (≤0.25
    pt, ≥2 pt de solape; recto con recto ±1.5°; cuerda de arco con cuerda de arco ±10° y
    SOLO si giran al mismo lado —dos curvas de una «Y» nacen tangentes y van ~3 pt a
    <0.25 pt: DU10 h.5—; una cuerda de arco sobre un guión recto es una curva que llega
    TANGENTE, DU08 h.26: no se toca); lo que queda es lo que la otra copia pone en los
    huecos. En un linetype normal dos trazos de la capa nunca se solapan. Auditoría de
    solapes (4 PDFs): DU06 h.4/5/11, LABOE h.5, borde del cajetín de DU10 en capas de
    utilidad y solapes chicos. Núcleo (`resolve_nodes`): la unión DE FRENTE con una letra
    del linetype en el hueco (`letter_in_gap`) vale en todas las utilidades (antes solo
    `precise_junctions`), también entre dos corridas «continuas» (guiones de 144 pt en
    una capa de 50 pt) si hay letra en medio o se TOCAN de frente: la «TE» bajo el texto
    «105+00» cortaba la línea. Fuera de `precise_junctions`, si el hueco supera
    `join_gap` esa unión («bend_letter») se resuelve DESPUÉS de las esquinas: la línea de
    gas que rodea un símbolo tiene su «g» en el hueco y la recta de frente la cruzaba sin
    tinta (LABOE h.26). `recognition_arc_chain.py` (PURO): curva en «S» sin recta entre
    medio (`common_tangent`: tangente INTERIOR a dos arcos seguidos que giran al revés,
    cada uno con ≥3 pt de arco, opción de recta de `ink_fillet_plan`; los dos codos
    comparten el ancla en la inflexión, `_place` tolera ≤1 pt de cruce; NO para arcos del
    mismo giro: el aplanado mezcla la punta de una recta con la primera cuerda del arco y
    daba curvas compuestas falsas, `-D` de h.4 r=45→77); `merge_same_circle` (en
    `group_arcs`): grupos seguidos del mismo giro a ≤60 pt que un círculo ajusta (RMS
    ≤0.08, máx ≤0.5) con radio coherente con el de cada uno (÷/×1.5) son un arco (con RMS
    0.2 y sin la coherencia juntaba dos codos r=14.5 a 63 pt en uno de r=126 —DU10 h.9— o
    dos arcos r 313/286 que ya no eran tangentes a sus rectas —DU08 h.25—); `explains`
    (`fit_fillets._run_ink`): un codo explica un grupo solo si la tinta cae DENTRO de su
    arco A→B (antes bastaba el círculo); `is_short`/`overshoot`: un codo de la 1.ª pasada
    cuya tinta curva sigue sobre su círculo pasada una tangencia (se aparta >0.75 pt de la
    recta: tomó por recta una cuerda de la curva, drenaje r≈145 pt de h.4 a medias) se
    rehace con la 2.ª pasada; si ésta no lo reemplaza, se conserva; `straight_off_arc`
    (1.ª pasada, `_accept`): un arco que pasa por encima de un guión RECTO (≥8 pt: no el
    brazo de una letra) de ESTA línea (≤1 pt de la polilínea, ±10°) se rechaza como en la
    2.ª pasada (DU10 h.10: «Y» de curvas que baja a una vertical, el arco se comía 13 pt
    de vertical y salía de 103°). `_through_dirs`: si un lado del vértice de paso es la
    primera cuerda de una curva, la línea que pasa es la del lado recto (el promedio la
    torcía 3.5°). Auditoría final (4 PDFs, 6 utilidades): eléctrico 986→1019 codos
    (imprecisos p90>0.5: 70→55), telecom 501→529, alcantarillado 8→16, drenaje 6→7;
    «sin tinta» y «V» iguales en las 6; los codos que desaparecen están revisados (el
    mismo arco rehecho mejor, o arcos sin tinta curva). Pendiente conocido:
    un ramal cuya entidad CAD arranca ENCIMA de la línea principal (DU06 h.4 «554+00»,
    24 pt) sale con el tee en ese punto y no en su tangencia (coincide exacto, no se ve
    doble). Tests: `tests/test_curvas_encadenadas.py`, `tests/test_curvas_editor.py`
    (DU06 h.4 telecom/drenaje).
  - `recognition_walls.py` + `recognition_wall_runs.py` (PUROS) — **tubería dibujada con
    sus PAREDES** (reporte del usuario 2026-10-02, `C-SSWR-PIPE` a 1.3 pt: salían dos
    utilidades pegadas). Regla del usuario: «si las líneas van juntas de inicio a fin, es una
    sola utilidad» → la línea del MEDIO. `merge_walls` (en `recognize_page` tras el
    contorno/anillo, TODAS las utilidades, por capa con las demás capas de la utilidad como
    `others`): trazos abiertos de solo rectas ≥20 pt (encadenados punta con punta, salvo un
    trazo corto que gira fuerte = TAPÓN), gemelos a separación CONSTANTE 0.5–30 pt (menos: la misma línea dibujada dos veces algo corrida, LABOE h.32 a 0.42 pt) (±max(0.2,
    8 %)) en ≥90 % de cada uno, puntas juntas (≤ sep + max(2, 2·sep); una punta cortada por el
    clip no cuenta) y largo ≥8·sep. Formas halladas (ET-004 drenaje): paredes; paredes + eje
    (tinta ≥50 % sobre el medio, de cualquier capa de la utilidad, o 3 gemelas con la del medio
    centrada → se quita solo lo de afuera); paredes + CUERPO relleno (relleno >8 pt entero en la
    banda sale); paredes A TRAZOS (`dash_runs`: guiones colineales, huecos ≤12 pt, solapes ≤2 pt
    de dos copias, partidos en tramos rectos; el eje sale a trazos con la unión de los guiones;
    `joint_leftovers`: el guión que dobla en un quiebre 2°–100° sale y va el conector
    fin→vértice→inicio). NO se toca: grupos de ≥3 paralelas (marco del cajetín de DU10, 4
    líneas de telecom DU10 h.27, 3 de agua «—W—» DU10 h.25), figuras cerradas (DU06 h.4), y
    líneas con LETRAS (tinta ≤8 pt que cruza la recta en algún hueco de sus guiones, hasta
    300 pt; la pared de otra tubería que cruza junto al buzón no es letra). Aviso «Tuberías
    dibujadas con sus dos paredes / con paredes y eje: N» solo si el cambio quedó como línea
    reconocida (`_recognized_walls`; clave `walls`, `RecognitionResult.walls_px`). Foto: los 4
    PDFs de prueba × 6 utilidades sin cambios; reporte 6 → 3 líneas (eje ≤0.08 pt del centro),
    ET-004 h.1 73 → 19, h.2 35 → 20 (una por tubería). El CONTORNO cerrado delgado
    (`outline_axis_paths`, paredes + tapones en un trazo) pasó de solo alcantarillado a TODAS
    (`OUTLINE_AXIS_UTILITIES` = `SUPPORTED_UTILITIES`) con trazo y largo ≥`OUTLINE_MIN_LEN_PT`=20
    (las barras RELLENAS de 0.9×9 pt de la leyenda de capas `-D` de gas/agua no son tubería).
    Tests: `tests/test_recognition_walls.py` (paredes, paredes + eje, a trazos y contorno en
    las 6 utilidades).
  - `recognition_letters.py` + `recognition_letter_lines.py` + `recognition_letter_shapes.py`
    (PUROS, numpy) — **utilidad por las LETRAS del linetype** (pedido del usuario 2026-10-05,
    DU08 h.26: `U-TRPW-DBNK-P` «—TE—» caía en «Otras» y no se reconocía). Las letras son
    vectores SHX: `recognition_letter_shapes.read_letter` las compara con plantillas de trazos
    (A–Z, a–z, «(», «)», «/»; chaflán simétrico, estirada al ancho de la letra, puntaje ≤0.08 =
    confiable; caché por forma REDONDEADA —letra 0.005 del alto, rótulo 0.01 pt— y se lee esa
    forma redondeada: antes se leía la primera que llegaba con la clave y el resultado de una hoja
    dependía de las hojas leídas antes en el mismo proceso, LABOE h.5 drenaje 14 o 17 líneas).
    `recognition_letter_lines`: huecos entre guiones COLINEALES
    enfrentados (≤40 pt; sentido de lectura = cola del guión) y sus trazos; `read_text` lee el
    rótulo en los dos sentidos (empate → el que da un código conocido, luego el del guión),
    solo con trazos CENTRADOS en el eje (tres líneas de agua juntas metían sus «w»). Votos por
    SITIO (lecturas a ≤10 pt = uno). `LETTER_CODES` según la LEYENDA del propio PDF (DU08
    h.3/h.33): e/E, SE (Station Electrification), TE (Traction Electrification) = ELECTRICO; t/T,
    SC (Signal & Communication) = TELECOM; w/W AGUA; g/G GAS; ss/SS/S ALCANTARILLADO; sd/SD
    DRENAJE; «(oh)» aérea y «unk», «o» = nada. `recognition.page_letters(page)` (~0.5–1.3 s por
    hoja, sin capas ANNO/TEXT/TTLB/LOGO/OVHD: la leyenda de h.33 va en `G-ANNO-TEXT`) +
    `letter_uses` deciden: (1) capa que el NOMBRE no hace línea/estructura de ninguna utilidad →
    LÍNEA POR LÍNEA (`split_by_line`: une guiones del hueco, puntas que se tocan, esquinas,
    guiones de una curva, letras y barras «/»; cada línea a la utilidad de SUS letras), o la capa
    ENTERA si es dedicada (`dedicated`: ≥90 % un código y el reparto cubre ≥75 % de su tinta;
    `U-TRPW-DBNK-P` 96–98 %); las genéricas (`_Xref` «G»+«W», `G-XREF`, la capa «0» de LABOE con
    comentarios, perfil y UNA línea «—S—»: 1–22 %) solo aportan sus líneas con letras;
    (2) capa de LÍNEA cuyo nombre contradicen letras UNÁNIMES (≥5 sitios, ≥95 %) → manda la
    letra (`N-COMM-DUCT-BANK-PL-SE` → ELECTRICO; antes TELECOM por nombre). Ruido: trazos
    rellenos fuera (logo de Metro), códigos con <2 sitios, y capa cuyas «letras» no son ≥50 %
    códigos (`W-Plantry`) no clasifica. `recognize_page(letters=)`: `_kind_for` + filtro por
    trazo `gather_paths(keep=)` (clave `path_key` = rect + nº de items: el `seqno` cambia al
    apagar capas), `stroke_letters=True` para esas capas, `RecognizedPolyline.letters` y aviso
    «Reconocidas por las letras de su línea…» (REVIEW, clave `letters`). `RecognitionWorker`
    lee las letras UNA vez por hoja; una capa que el usuario asignó a mano a otra utilidad
    («Ajustar capas…») no se toma por letras. «Capas de la hoja»: `pdf_layers.page_layers` trae
    `letters`/`letter_utilities`/`letter_codes`/`name_utility`; la capa va al grupo de su
    utilidad con «TE» al lado y tooltip. Foto 4 PDFs (141 hojas): 190 líneas en 51 hojas, 0 sin
    tinta, 0 «V», 138 codos; ajenas: solo un vértice de unión donde una línea nueva toca otra.
    Tests: `tests/test_recognition_letters.py`.
    **Reparto por línea sin uniones falsas (2026-10-06, DU06 h.5: una línea «—W—» de agua en
    `G-XREF` salía como telecom)**: `_link_corners` no une una punta con una línea que PASA de
    largo por la «esquina» si la punta no llega a tocarla (`_passes_beyond`: tinta de guión sobre
    su eje pasado ese punto), ni una punta que ya SIGUE de frente en otro trazo
    (`_continuations`); los trazos de una letra de varios trazos («T»: dos rectas, `_letter_pairs`)
    van juntos, no «continúan» ninguna línea y, si caen en el hueco de una continuación, van con
    esa línea (`_link_gap_letters`). Foto de letras (141 hojas): 50 trazos cambian — letras que
    pasan a su línea, y tres líneas que dejan de tomar la utilidad de otra (agua de `G-XREF` que
    era telecom en DU08 h.36/37, una línea de referencia con flecha de `_Xref` que era agua en
    DU10 h.8). **Letra en el hueco = la línea SIGUE** (núcleo, `resolve_nodes`, todas las
    utilidades, mayúscula o minúscula): dos puntas libres que se miran (±30°, giro ≤35°) con una
    letra del linetype en medio se unen al final de la pasada de esquinas — en el cruce de sus
    rectas si cae delante de las dos; recta + curva: sobre la recta frente a la punta de la curva;
    dos curvas: el centro del hueco (≤3 pt de la otra recta). Antes quedaban cortadas: dos tramos
    «continuos» no forman esquina (DU06 h.9 «E», h.10 «SE») y la esquina de una curva caía detrás
    de su punta (DU06 h.5 «—T—»). El quiebre suave no cose una CURVA con una recta paralela
    desplazada (desfase que el giro no explica > `NODE_OFF_LINE_PT`; DU08 h.39, DU06 h.3).
    Auditoría de continuidad: huecos 3 → 0. Tests: `tests/test_letra_en_el_hueco.py`.
  - `recognition_summary.py` (PURO) + `recognition_summary_view.py` +
    `recognition_review_view.py` + `recognition_layers_view.py` +
    `recognition_preview_draw.py` — resumen VISUAL de la vista previa (lo pidió el
    usuario: «evitar mucho texto»): `classify_warning` pasa cada aviso de
    `recognize_page` a `Notice` (nivel problema/revisar/info + etiqueta corta + `hint` =
    explicación llana de `_HINTS`; el texto completo va al tooltip; un aviso SIN regla cae
    en «revisar» — al agregar un `warnings.append` nuevo en `recognition.py`, sumar su
    regla en `_RULES` y, si se muestra en «Para verificar», su `_HINTS`). **Tres
    columnas** (pedido del usuario 2026-10-03): `RecognitionPreviewDialog` = `review_box`
    (`CollapsiblePanel` «Para verificar (N)», plegable: la hoja gana su ancho) | hoja |
    `side_panel` (hoja + escala `lbl_scale`, `SummaryPanel`, `layers_panel` «Capas usadas»
    que crece con el panel, «Ajustar capas…» fuera del scroll); anchos ~20 %/~28 % (240–300 /
    300–400 px) que siguen a la ventana hasta que el usuario mueve un divisor; cada panel con
    su `widgets.NaturalHeightScroll`. `SummaryPanel` (derecha) = 4 tarjetas + barra por
    utilidad (activas sólidas / AB rayadas, misma escala) con su leyenda + «Cobertura»
    (cifra, barra fina NEUTRA, el estado lo da el icono: ✔ / ojo / rojo <90 %) y las marcas
    del control de calidad que haya (`qa_kinds`). **«Para verificar» NO son errores**
    (2.º pedido, mismo día): `ReviewPanel` (izquierda) = frase arriba (`lbl_intro`: «Todo
    se reconoció… no son errores»; otra si hay un PROBLEM), avance «k de N vistos» + barra,
    puntos AGRUPADOS por utilidad (cuadrito + nombre una vez; primero el grupo con un
    problema) como tarjetas `_NoticeRow` con icono de ojo neutro (solo PROBLEM: octágono y
    borde rojos) y la explicación debajo (`row.hint`); Tab + Enter/Espacio = clic;
    «Detalles» plegado, agrupado igual. **«Capas usadas» → ver en la hoja**
    (`UsedLayersPanel.focusChanged`): clic en una capa, en «Líneas»/«Bóvedas» o en la
    utilidad → `_on_layer_focus`: `_hit(utility, kind, ocg)` decide qué es de lo elegido
    (líneas por `pl.layer_ocg`, bóvedas por `vaults_geo[i]["layer"]`; puntos de bóveda y
    marcas de calidad solo con la utilidad entera), halo del color de la utilidad
    (`draw_line_halo`/`draw_vault_halo`), lo demás a `DIM_OPACITY`, encuadre con
    `_show_rect` y «Resaltado: … · N líneas, M bóvedas»; otro clic o «Ver todo» lo quita.
    Las funciones `_draw_*` (en `recognition_preview_draw`) devuelven sus ítems para eso. **Colores del control de calidad** (`ui_common.QA_*`): ninguno
    es de utilidad y cada uno con su forma — guion sin cubrir = línea magenta, bóveda sin
    línea = anillo magenta, fuera de patrón = turquesa a puntos (antes naranja = telecom y
    violeta ≈ agua; `test_colores_de_calidad_no_son_de_ninguna_utilidad` exige ≥30° de tono).
    «Unir tramos» (`chk_routes`, QToolButton `toggleTool`) va en el PIE junto a
    «Opacidad». **Clic en un aviso → ir al lugar** (pedido del usuario): cada regla
    de `_RULES` lleva una CLAVE y `targets_for(clave, result)` da los recuadros (px de la
    vista) — codos `loose`, ristras `curve` (uno por tramo), `uncovered_px`,
    `vault_orphans_px`, y `RecognizedPolyline.review` (lo marca `recognize_page` en las
    rutas que generan los avisos «-A» sin patrón / «//» / «-D» / «/» activa); la fila
    emite `ReviewPanel.locate(QRectF)` y `RecognitionPreviewDialog._go_to` hace zoom
    y marca con un recuadro blanco + trazos negros (1/N por clic). **Revisado** (2026-09-30): vistos todos
    sus casos (`_NoticeRow._seen`) —o un clic si no tiene lugar— la fila queda ✔
    (`reviewedChanged`; clic derecho = pendiente), «k de N vistos» arriba, y
    cada lugar visitado queda con un recuadro verde a trazos (`_reviewed`, se redibuja en
    `_redraw_overlay`). Aviso nuevo con ubicación → clave +
    rama en `targets_for`. Ojo: un ítem con `ItemIgnoresTransformations` (esquina C del
    codo) se dibuja centrado en (0,0) y con `setPos` — en coordenadas de la hoja sale
    corrido con zoom ≠ 1. Tests: `tests/test_recognition_summary.py`.
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
    = un marcador) y juzga cada polilínea con `_covers` (ver más abajo): True,
    False, None (más corta que el
    paso → hereda el veredicto de la capa). `recognize_page` lo calcula sobre
    las RUTAS (joined y raw) por OCG; DU06 h.9: paso 67.7 pt, línea de 282 pt
    True + 3 stubs None → 4 (AB). Capa `-A` sin patrón → se importa activa con
    aviso; patrón en capa activa → solo aviso.
    **«//» = abandonada en CUALQUIER utilidad y capa** (regla del usuario
    2026-09-25; DU08 h.21 agua `-D`): `MarkerPattern.doubles` (mayoría de
    marcadores de 2 barras) y `double_verdict` (solo los dobles, o todos los
    marcadores si así cubren la línea; sin «//» propio y corta → None = hereda la
    capa). La «/» simple sigue exigiendo capa `-A`.
    **Cobertura (`_covers`, auditoría 2026-09-28, DU08 h.26 alcantarillado `-D`
    «—//—ss—» con «//» a 90/75/75 pt que salía activa)**: AutoCAD dibuja el linetype
    POR SEGMENTO y lo reinicia en cada vértice, así que el paso que cruza un vértice
    cae entre ~0 y 2 periodos y el último marcador queda a <2 periodos de la punta.
    Una línea sigue el patrón si ≥`MARKER_STEPS_OK`=75 % de sus pasos miden entre
    `MARKER_SHORT_MIN_PT`=12 (con «/» simple solo si hay ≥3 marcas; si no, periodo −
    tol) y 2×(periodo + tol), y cada punta queda a ≤2 periodos + tol. Los arcos cortos
    (`_curve_spans`: cuerdas ≤30 pt junto a un vértice `curve`) no cuentan como tramo
    sin marcador: cada arco es su propio segmento del linetype (LABOE h.27). Paso
    definido por la propia línea (`local`, 2 marcas): puntas a ≤1.5 periodos y sin
    descontar arcos (DU06 h.12: dos «℄» sobre un banco de ductos). «//» suelto sin paso
    en la capa → `MARKER_DEFAULT_PERIOD_PT`=67.7 (acometidas `-D` de un solo «//»). Foto
    6 utilidades × 4 PDFs (`scripts/audit_abandonadas.py` + `--diff`, 5235 rutas): 64
    líneas pasan a AB (23 `-A` con
    «/», 41 `-D` con «//»), 0 al revés, 0 avisos nuevos, geometría idéntica. Queda 1
    sin AB: DU08 h.35 eléctrica `-D` con 190 pt sin marcador al cruzar una bóveda.
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
    extremo más de media corrida. **Cruces con tinta** (2026-09-30, DU10 h.11 alcantarillado):
    `slide_ok(keep_ink=True)` además no deja retroceder sobre más de `RETRACT_INK_MAX_PT`=3 pt
    de guiones PROPIOS (`_ink_beyond`). En esquinas (5b) solo se rechaza si las DOS corridas
    siguen pasado el cruce (una «X» = dos rectas enteras; exigirlo a cada una por separado
    cambiaba codos del eléctrico en ~20 hojas); en T (5d) la T se forma como siempre y la tinta
    del otro lado queda como corrida-cola que nace en el mismo nodo (lateral «ss» que cruza la
    principal; una cola < `floor` se va como ruido: el guión que se pasa unos pt no cambia).
    Foto 6 utilidades × 4 PDFs: 16 hojas, todas ganan tinta, 0 codos distintos. Tests:
    `tests/test_cruces_con_tinta.py`. `SOFT_SIMPLIFY_PT`=0.5 para bend/corner (era 1.5: dejaba la centerline hasta 1.5 pt fuera de los guiones en quiebres suaves),
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
    **Continuidad tras los codos** (`join_emitted`, pedido del usuario 2026-09-30, DU06
    h.5 telecom: la «U» salía partida donde `recognition_text_gaps.connect_text_gaps`
    cierra el hueco de sus letras «TE»): en `recognize_page`, después de `_emit` y de los
    huecos de texto, solo en las rutas UNIDAS, dos rutas de la misma capa/estado que
    comparten un extremo (grado 2, nada más pasa por ahí) se concatenan si siguen de frente
    con el rumbo LOCAL (≤100°, ≤35° con «tee»; nunca «cut» ni si cierra un lazo). No toca
    vértices ni codos (índices corridos, a/b invertidos si hace falta); junction/tee/end de
    la unión → «bend». Las «Y» (3 extremos, bancos de ductos que se abren) NO se tocan.
    `connect_text_gaps` suma un 3.er caso: dos puntas libres junto a un codo cuyas rectas
    miran al hueco (±6°) con letras de la capa encima se unen en RECTA, sin puntos nuevos
    (tramo recto del medio de una «S» bajo «SC», DU10 h.10).
    Auditoría `scripts/audit_continuidad.py salida.json` + `--diff` (6 utilidades × 4 PDFs,
    ~5 min): cortes de grado 2, pares sin unir en nodos, huecos entre puntas enfrentadas y
    codos por hoja. Foto 2026-09-30: cortes 3 → 0 (DU06 h.5, DU10 h.3 telecom; DU08 h.37
    eléctrico), huecos 1 → 0 (DU10 h.10), 0 codos distintos. Tests: `tests/test_routes.py`
    (`join_emitted`), `tests/test_recognition_text_gaps.py` (la «S»).
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
    secundaria neutra, la usa el preview en su cuadrícula 2×2). **PESTAÑAS (2026-10-03, pedido
    del usuario: en tres columnas a cada vista le quedaba poco sitio)**: `WorkTabs`
    (`composite_tabs.py`, pintadas a mano con insignia: nº de piezas / «!» pendiente) + un
    `QStackedWidget` (`self.stack`, `self.pages`): «Origen» (`composite_source_page.
    SourcePageMixin`: galería IconMode `lst_pages` con miniaturas de `THUMB_W`=220 — sigue
    siendo la hoja actual: `setCurrentRow` dispara `_on_page_changed`; doble clic o
    `btn_go_area` → Área), «Área a tomar» (‹ › `_step_page`, `lbl_page` «Hoja N de M»,
    `btn_all_pages`; `spn_src_scale` junto a «Tomar»; `taken_box` verde con «Ver hoja
    compuesta ›») y «Hoja compuesta» (`btn_edit_area` en `piece_tools` → Área). `_go_tab(i)`
    centraliza todo (Atrás/Siguiente del pie, Ctrl+RePág/AvPág, encuadre la 1.ª vez que se ve
    cada vista —y otra vez al maximizarse, `changeEvent`—). `_start_tab`: sin piezas → Origen;
    una hoja entera (la del editor) → Área; si no → Hoja compuesta. Ojo en pruebas: la vista de
    una pestaña oculta no está visible (`isVisibleTo` falso, `centerOn` sin efecto) →
    `dlg._go_tab(TAB_SHEET)` antes. **La hoja ELEGIDA es la hoja compuesta**
    (`composite_choice.ChosenSheetMixin`, pedido del usuario 2026-10-05: elegía la hoja, pulsaba
    «Siguiente» y quedaba vacía): mientras la hoja compuesta sea vacía o UNA hoja entera
    (`_simple`), elegir hoja la reemplaza (`_choose_page`: al abrir, clic/flechas en la galería
    —`composite_source_page.PageGallery.picked`, solo gestos del USUARIO; `setCurrentRow` por
    código no elige—, ‹ ›, «Tomar área de esta hoja») y la deja EN EDICIÓN: un área marcada (o
    sus esquinas movidas) la recorta al momento con el `_apply_crop_edit` de siempre y «Hoja
    completa» la devuelve (`_set_piece_area`; `_take`/`_take_area` sobre la pieza en edición de
    la hoja a la vista = actualizarla, no agregar). La hoja entera se ve SIN tinte (borde +
    asas: `_CropView.is_whole_page`/`_fill_for`). Con trabajo de verdad (un área, ≥2 piezas)
    elegir otra hoja solo la muestra (aviso `pending_box` con «Usar solo esta hoja» si hay una
    pieza: `_use_only_this_sheet`); Ctrl+clic en la galería (`PageGallery.added`) agrega la
    hoja entera. Esc no cierra el diálogo (`wizard_widgets.NoEscapeClose`). Tests:
    `tests/test_composite_dialog.py::test_la_hoja_elegida_es_la_hoja_compuesta` y siguientes.
    **Validaciones** (`composite_checks.py`, PURO): sin piezas
    ni área marcada → `btn_ok` apagado (enlace «Usar la hoja N» = `pick`); área marcada sin tomar (`_sel_dirty`: la marcó el
    usuario, no la de una pieza en edición) o hoja a la vista sin tomar → aviso ámbar en el pie
    (`lbl_check`, enlace `take`/`tab:N`) + «!» en la pestaña; «Siguiente» desde Área y `accept`
    preguntan (`_ask_untaken_area`: tomar / seguir sin ella / volver); con solo un área
    marcada, `accept` la toma. «Para continuar…» va en tono neutro: no es un error.
    **UX (2026-09-26, pedido del usuario: «que no haya muchos
    botones»)**: Área = «Tomar área» (principal) + «Hoja completa» + menú «Opciones»
    (`btn_area_snap`/`btn_trim` son QAction checables, mismo nombre que antes); Hoja compuesta =
    herramientas de pieza (`piece_tools`: editar área, girar, menú «Ajustes» con `spn_angle`/
    `spn_piece_scale`, quitar) SOLO con una pieza seleccionada, y menú «Uniones»
    (`btn_magnet`/`btn_anchors`/`btn_bridges` + `spn_gap`); `cmb_scale` solo visible con >1
    escala. Botones: «Hoja
    completa» = `QPushButton[soft="true"]`, «Opciones»/«Uniones»/«Ajustes» =
    `QPushButton[options="true"]` con menú, todos `_BTN_H`=38. Hoja a la vista que NO está en
    la hoja compuesta: la lista marca las que sí («✔ Hoja completa» / «✔ Área tomada»),
    `pending_box` avisa y `accept` pregunta (`_ask_pending_page`: agregar / usar solo esa hoja
    si hay UNA pieza / seguir sin ella / volver). Abre en `Composite.last_view` ([pdf, hoja] al aceptar; va al
    .digproj) — con una sola hoja entera, en su PDF + la hoja del editor; sin nada, la de la
    última pieza (`_start_position`). `piece_map` reproduce exactamente el
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
  - **Compositor de escaneos** (`Composite.manual`, PDF imagen/escaneo → editor sin capas ni
    reconocimiento): `scan_crop_view.py` (área con 4 esquinas → `Piece.polygon`),
    `alignment_tools.py` (regla con asa de giro, transportador de tamaño FIJO en pantalla con
    imán a 0/90/180/270°, Ctrl ×0.1, Shift 15°, doble clic = eje), `composite_measure.py`
    (Medir / Enderezar: dos clics con línea elástica, Esc), `composite_scan.py` (PURO:
    `snap_angle`, `rotate_piece`/`scale_piece` con punto fijo, `calibrated_scale`) y
    `composite_scan_ui.py` (`ScanToolsMixin` de `CompositeDialog`: barra y acciones). UI
    (pedido del usuario 2026-10-02): UNA barra (`tool_strip.ToolStrip`, pasa a solo icono si no
    cabe) — guías a la izquierda, acciones de la pieza a la derecha — y la indicación de la
    herramienta en `lbl_status` bajo la hoja, nunca filas de texto encima. «Enderezar» elige el
    eje solo (`ruler_correction(vertical=None)`). **Fundir bordes** (`Composite.seam_blend`,
    `blends()`): modo OSCURECER en la vista (`PieceItem.paint` + papel blanco en
    `CompositeView.drawBackground`; bajo el recorte nítido no se pinta la base) y en el PDF
    (`build_document`: `/PdfcadDarken gs` por pieza, ExtGState `/BM /Darken`): el papel de una
    pieza no tapa la tinta de otra y la superposición no oscurece el papel. Solo escaneos: en el
    vectorial las franjas `covers` DEBEN tapar. Tests: `tests/test_scan_composition.py`,
    `tests/test_scan_tools.py`.
  - `wizard_widgets.py` — UI compartida por los pasos del asistente: `StepBar` («1 Componer
    hoja › 2 Capas de la hoja › 3 Vista previa»; pasos anteriores clicables = volver),
    `show_opacity_popup` (el desplegable de opacidad del editor, movido aquí: lo usan
    `Main._open_opacity_popup`, Capas y el preview) y `OpacityButton` (opacidad del
    pixmap del PDF + rectángulo de fondo blanco/negro debajo; `sync()` tras cada render;
    quien limpie la escena debe conservar `backdrop`) y `NoEscapeClose` (pedido del usuario
    2026-10-05: Esc cerraba los pasos y se perdía el trabajo; mezcla de `CompositeDialog`,
    `SheetLayersDialog` y `RecognitionPreviewDialog`: Esc no cierra, solo `_escape()` —quitar el
    resaltado—; los cuadros chicos y preguntas siguen cerrando con Esc). Navegación (pedido del usuario
    2026-09-26): `Main._wizard_sheet_flow(start_idx, start_step)` es un bucle —
    Capas devuelve `layer_dialog.LAYERS_BACK` (paso 1 de la cabecera) → vuelve al
    compositor; el preview devuelve `PREVIEW_SHEET_LAYERS` (paso 2) → `start_step=1`, o
    `PREVIEW_CHANGE_SHEET` (paso 1; `btn_sheet` = ese botón de la barra). Diseño (el
    usuario, 2026-09-26: «repetitivo… que ocupe todo el ancho»): los tres pasos usan
    `wizard_header` (la barra de pasos a TODO el ancho = única navegación hacia atrás, sin
    botones «◀» repetidos) y `wizard_footer` (a todo el ancho: opciones de vista como
    Opacidad · ayuda · Cancelar | Continuar); el panel lateral queda solo con el contenido.
  - `pdf_layers.py` + `layer_dialog.py` — paso «Capas de la hoja» del asistente:
    lista las capas OCG con geometría y las apaga/enciende con
    `doc.set_layer_ui_config` (única API que afecta render **y** `get_drawings`;
    `doc.set_layer` no sirve en PDFs de Bluebeam). La visibilidad vive en el
    `fitz.Document` de `Main` (`self.hidden_ocgs` guarda los nombres); el worker
    abre su propio doc, por eso recibe `hidden_ocgs` y filtra por nombre.
    `pdf_layers.utility_of(name)` agrupa cada capa por tokens NCS en las
    utilidades de la app (`model.TIPOS` + `OTRAS`); el diálogo (rediseño 2026-09-26)
    tiene la tarjeta «Reconocer» (`chk_recog_all` «Todas» + `_recog_checks`; sin ninguna
    marcada `btn_ok` se apaga y avisa) y «Capas del plano» = `QTreeWidget` con un grupo por
    utilidad (plegado; su casilla APAGA/enciende todas sus capas —`set_utility_visible`,
    `_set_utility_visible` recuerda el estado por capa en `_util_memory` para reponerlo— y
    muestra «on/total» si es parcial), buscador que filtra y despliega, ojo mostrar/ocultar
    sobre lo filtrado, «Opacidad», y
    «◀ Hoja N / M ▶» cambia de hoja sin salir. Devuelve `(ocultas, hoja, utilidades, letras_no)`.
    **Panel izquierdo «Leyenda»** (pedido del usuario 2026-10-05; `layer_dialog_info.LayerInfoMixin` +
    `layer_info_panel.LayerInfoPanel`, `CollapsiblePanel` como «Para verificar»): (1) «Por las letras de
    su línea (N)» = tarjetas de las capas con `letter_utilities` (utilidad + letras, capa, por qué, y
    `legend_texts`: lo que dice la leyenda del PDF de ese código —misma caja «g»/«G» si alguna fila la
    tiene, primera hoja de leyenda, sin las variantes «ABANDONED»—) con casilla «Usar» →
    `self._letters_off` y el árbol se rearma con `pdf_layers.without_letters` (vuelve a su grupo por
    nombre: `name_group`). La decisión vuelve a `Main._letters_off`, va al `.digproj` (`letters_off`),
    a `RecognitionWorker(letters_off=)` (quita esas capas de `letters`) y a «Ajustar capas…». (2) «Leyenda
    del plano» = `pdf_legend.document_legend` de los PDF de ORIGEN (`Main._legend_sources`: en una hoja
    compuesta la de trabajo es un temporal sin leyenda), leída en otro hilo (`LegendWorker`, ~4 s; caché
    `Main._legend_cache` por PDF), primero las filas de las letras de esta hoja (`read_codes` +
    `letter_raw` de `page_layers`), «Ver toda». Clic en tarjeta o fila = resaltar (velo blanco sobre la
    hoja + trazos de esas capas con el color de su utilidad; en una capa mezclada solo los suyos, por
    `letter_paths`) y encuadrar; otro clic o «Ver todo» (`focus_bar` arriba del panel, «Resaltado: …»)
    lo quita. La TARJETA resalta su capa con halo y, en línea fina, el RESTO de las líneas de su utilidad
    que se reconocerán (2.º reporte 2026-10-07, DU06 h.5: junto a las «T» de G-XREF iban sin resaltar las
    «t» de C-TELE-UNGD-E/-D, telecom al importar). **Sin leyenda en el PDF** (DU06) → leyenda del
    ESTÁNDAR BOE (mismo pedido): `leyenda_estandar.py` (PURO) arma, con las capas de la hoja ya con
    `without_letters`, un `Grupo` por utilidad y una `Fila` por (estado, abreviatura BOE) de sus líneas +
    una de sus estructuras. Datos del manual (`Documentos/docs prueba/BOE_CADD_Manual_210610.pdf`):
    fig. 3.1.7.1-1/-2 «Utility Linetypes» (`LINETYPES`: ELEC, HV ELEC, NGAS, PW, FPW, IRR, SSWR, SD,
    TEL, FO; `STRUCTURES`: ELECTRICAL VAULTS, SSMH, SDMH; propuesta ≤12" = línea continua) y §8.1.6
    estados (`estado_capa`: letra de estado del nombre NCS sin la disciplina ni el paquete «__UA4»; si no,
    PROP/EXIST/ABND en el nombre o en el xref; si no, la caja de sus letras: MAYÚSCULA = propuesta).
    `rol_capa`/`es_trazo_de` deciden qué capa —y en una capa mezclada qué trazo— es línea/estructura de
    cada utilidad IGUAL que `recognition.line_selectors`, y solo lo VISIBLE: `trazos_visibles` (una
    pasada de `get_drawings(extended=True)`: mismos recortes y vistas de perfil que `gather_paths`,
    solo las capas de utilidad, atajo para clips rectangulares; 0.5–1.3 s) da (original, recortado):
    se decide con el original (`letter_paths` se leyó sobre él) y se dibuja lo recortado; la leyenda
    lista solo capas con algo visible (`LayerInfoPanel.visible_layers`). Capas con trazos que NO están
    en la lista del PDF (`layer_ui_configs`; DU06 h.2 `…(A2_TRIM)|V-ELEC-MANH`): por su nombre
    (`capa_sin_lista`), como el reconocimiento. Auditado: mismas capas en las 141 hojas × 6 utilidades. UI `layer_std_legend.py` (`StandardLegend`: cabecera = toda la utilidad, fila = esas
    capas; `LineSample` dibuja la muestra: a trazos/continua, letras leídas, «//» a demoler). Sin
    utilidades, capas por letras ni leyenda, el panel se pliega solo. Tests: `tests/test_leyenda_estandar.py`.
    `pdf_legend` (sin Qt): hojas con LEGEND/LEYENDA ordenadas por filas «EXISTING/PROPOSED…» (máx. 3);
    fila = texto con una muestra HORIZONTAL (≤12 pt de alto, ≥60 pt de largo) contigua a su izquierda;
    solo columnas de ≥3 filas a PASO REGULAR (tolera filas sin leer: paso ×2/×3) con letras en ≥30 %:
    las etiquetas con flecha de LABOE h.8/h.9 y el cajetín no entran. DU08/DU10/LABOE: 34–37 filas;
    DU06: sin leyenda. Tests: `tests/test_layer_legend.py`.
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
  - `i18n.py` + `i18n_core.py` + `i18n_en.py` + `i18n_en_changelog.py` — traducción
    ES → EN. La clave es el texto en español tal cual está en el código. UI:
    `from i18n import t` (y `bind(widget, "setText", "Clave")` en widgets de vida
    larga: se re-traducen solos con `LANG_BUS`; `bind_item` para ítems de combo);
    lógica PURA (`duct_bank`, `recognition`, `civil_catalog`, `composite`):
    `from i18n_core import t` (sin Qt). Reglas: plantillas `t("… {n}").format(n=…)`,
    nunca f-string ni concatenación dentro de `t()`; el sangrado va fuera de la clave
    (`"  " + t("Guardar")`); tablas de datos con `N_("…")` y `t()` al mostrar;
    documentos largos en `app/docs/<nombre>.<idioma>.html` vía `load_doc`.
    `tests/test_i18n.py` falla si un texto visible queda sin envolver/traducir, si
    una traducción pierde `{marcadores}` o si quedan claves muertas.
  - `duct_bank.py` — modelo PURO del Duct Bank (sin Qt): `DuctBank` (envolvente
    rectangular en pulgadas + lista de `Conduit` + `pipe_idx` de la pipe asignada),
    `snap`, `validate`, `conduit_fits_envelope`, `conduits_overlap`. Testeado
    headless. La sección se asigna a una pipe específica y se exporta como
    `PDFCAD_DUCTBANK` en el DXF; el plugin C# la extruye como sólido 3D.
    **Un diseño en VARIAS pipes** (2026-09-29): `pipe_idxs` + `assigned()`/`assign()`
    (`pipe_idx` = la primera, compat); leer SIEMPRE con `assigned()`. El DXF emite un
    `PDFCAD_DUCTBANK` por pipe (NAME `<nombre>-P<n>` si se comparte: el plugin nombra las
    redes de conductos con NAME). Al borrar pipes `reindex_after_pipe_delete`; el estado
    de deshacer (`_snap_state`) incluye `duct_banks`. Una pipe lleva UN bancoducto
    (`Main._db_take_pipes`). Lista «Utilidades» con selección múltiple
    (`_selected_pipe_rows`: solo cuenta si incluye `sel_pipe`) y menú en bloque.
    `thumbnails.py`: `HoverPreview` (globo con miniatura en vez del tooltip),
    `duct_bank_pixmap`, `pipe_pixmap` (recorte de la escena del lienzo).
  - `duct_bank_dialog.py` — diálogo del **Diseñador de Duct Bank** (botón del
    toolbar, se guarda en `.digproj` como parte del proyecto). UI grande y
    accesible (usuario +60): grid en pulgadas, snap por defecto, solo una
    herramienta activa a la vez, undo/redo, zoom fit. Trae rectángulo,
    conductos, mover, medir, eliminar.
  - `model_ops.py` — operaciones PURAS sobre el modelo (sin Qt): auto-detección de
    buzones (`rebuild_structures`: gravedad = BZ en TODOS los vértices; eléctrico/
    telecom (conduit) = CAJA solo en los vértices de bóveda REAL del reconocimiento,
    `VAULT_VERTEX_KINDS` = vault/stop — regla de dev_deyvy «muy pocas cajas»; las
    demás las pone el usuario; presión nunca. `attach_fillets` crea la marca CV del
    codo reconocido si en conduit no hay estructura), ocultar cajas de quiebres reconocidos sin
    bóveda (`hide_soft_vertex_structures`, usa `pipe["vertex_kinds"]`), conteo de conexiones (`bz_segment_count`), cotas
    por tramo (`interp_vertex_z`, `migrate_vertex_inv`, `snapshot_seg_values`),
    búsqueda por vértice (`pipe_at_vertex`), geometría de Multileader (`leader_geo`,
    recibe la conversión pies→px de la ventana) y `attach_vault_geometry`: copia a la
    CAJA más cercana (≤12 px) la geometría real de la bóveda reconocida
    (`VAULT_GEO_KEYS`: shape, width_ft, length_ft, rot_deg, outline en px; las
    huérfanas no inventan buzón; `rebuild_structures` los conserva por coordenada).
    El lienzo dibuja `outline` como polígono a escala y la medida al seleccionar.
    **SÓLIDOS** (2026-09-30): caja CONDUIT —o bóveda de PRESIÓN, 2026-10-05— con
    `shape="rect"` + `outline` (`is_solid`, `SOLID_NETS`) →
    `normalize_solids` (al final de `rebuild_structures` y `attach_vault_geometry`):
    `solid=True`, sin `part`/`part_size`, `solid_height_ft` (defecto `SOLID_DEFAULT_H_FT`
    = 6.56168), código CAJA-N → SÓLIDO-N. Panel: Largo/Ancho/Altura (`resize_solid` rehace
    el contorno con el mismo centro/giro, px/ft = zoom/scale); no puede ser CV. DXF:
    `PDFCAD_STRUCT` + `SOLID=1, SOLID_CX/CY, SOLID_ROT_DEG, SOLID_H_FT` (+ LENGTH/WIDTH_FT);
    el plugin NO crea estructura en ese vértice (tramos por extremo libre) y `CrearSolidos`
    dibuja un Solid3d en `PDFCAD_SOLIDOS` con base en el sump (o SUMP, RIM−h, 0).
    Cota SUPERIOR (2026-09-30): `solid_top_z` (None = automática: desde 2026-10-02 el EJE de la
    utilidad unida queda a media altura — `model_ops.solid_top_centrado(solera, alto_interior_ft, h)`,
    alto = 2.º número de «W x H» o el diámetro, como `OffsetEjeARasante` del plugin —;
    `Main._solid_default_top` vía `_pipe_z_at`, la mayor si llegan varias) → `SOLID_TOP_Z`; si viene, manda: base = top − h. Property Set
    `PDFCAD_Solido` (`SolidoPropertySet.cs`): Codigo, Largo/Ancho/Altura, Cota_Superior/
    Base + cada `XD_*` (sin prefijo) y `XDU_*` («Usuario_…») de la estructura; la
    definición se amplía sola con los campos que falten.
    `Main` delega y solo asigna/dibuja.
  - `quiebres_curvas.py` (PURO) — **los quiebres del plano son curvas** (regla de los ingenieros,
    pedido del usuario 2026-10-06 con una línea eléctrica de dos quiebres): en gravedad y conduit (agua y
    gas NO: en presión el quiebre es un codo) `Main._import_recognized_pipes` llama
    `curvas_en_quiebres(indices=las tuberías nuevas)` después de `attach_fillets`. Cada vértice
    `bend`/`corner` —y `curve` que quedó SIN codo (2.º reporte 2026-10-07, DU06 h.5 eléctrico: una línea
    dibujada como UN trazo de tres rectas, el núcleo la marcó «curve»; o curva que quedó como polilínea)—
    con giro > `GIRO_MIN_DEG`=2° pasa a CV con radio AUTOMÁTICO (`radius_ft`=0 →
    `model_ops.radio_auto_ft` = 6 × diam, el mismo del editor y del plugin: el mínimo de la regla, la curva
    más chica; sigue al diámetro) y la marca `quiebre` (panel «Origen: quiebre del plano»;
    `rebuild_structures` la conserva, «Volver a tratar como buzón/caja» la quita). Solo si entra tal cual la
    dibujan editor y plugin: sin recorte con los topes 1.0/0.48, sin cambiar ninguna curva vecina (con una
    curva al lado el tope de un codo de la tinta baja a 0.48: se compara su `fillet_geo` antes/después) y con
    el tramo recto mínimo del plugin entre dos curvas seguidas (1 × ancho, ×`HOLGURA_RECTO`=1.1); primero los
    que más giran. No en un vértice compartido (otro vértice a ≤14 px; en gravedad tampoco de la misma
    tubería, su buzón se reconcilia por coordenada), junto a una estructura visible ni dentro de una bóveda.
    Lo que no entra queda como quiebre y lo cuenta el mensaje de la importación. Foto (simulación de la
    importación a zoom 3.5, 4 PDFs × 4 utilidades): 531 curvas (eléctrico 265, telecom 208, drenaje 32,
    alcantarillado 26; con los `curve` sin codo 613: eléctrico 316, telecom 238, drenaje 33, alcantarillado
    26, 0 recortadas), 0 curvas existentes cambian, 0 pares sin recto mínimo; sin lugar 300 (310): 205 en la
    punta de un codo de la tinta cuyo arco llega justo al quiebre (la curva del plano sigue y el
    reconocimiento no la cubrió entera: es otro problema), tramos < 3 pt y esquinas de 90° con tramos más
    cortos que T. Tests: `tests/test_quiebres_curvas.py`,
    `tests/test_curvas_editor.py::test_quiebre_del_plano_entra_como_curva_minima` (ventana real → DXF).
  - **Normativas de diseño** (2026-09-30): `normativas.py` (PURO) = motor escalable: `TIPOS` (tipo de
    regla: categoría, `Campo`s que la ventana dibuja sola —`grados_lista|grados|pies|utilidades`— y
    `verificar(regla, Contexto) -> Resultado`), `REGLAS_BASE` (valores iniciales AWWA: codos
    11.25/22.5/45/90° = 168.75/157.5/135/90° ENTRE tuberías, Tee 90°, Wye 45°, cruz 90°, ±1°;
    el CODO se mide entre las dos tuberías —«lado B», pedido del usuario 2026-10-01— y su giro va en
    `a["giro"]`; el catálogo v1 guardaba giros y `cargar_catalogo` los convierte), catálogo GLOBAL (`ruta_global`, %APPDATA%/
    pdf-to-cad/normativas.json, solo las diferencias con la base; env `PDFCAD_NORMATIVAS` en tests) y
    activación POR PROYECTO (`Main.normas_estado` → `.digproj` `normativas_activas`). Regla nueva =
    un `TipoRegla` + (opcional) su entrada en `REGLAS_BASE`; la UI no cambia. `accesorios.py` (PURO):
    tipo + ángulo de cada accesorio de presión con las reglas del plugin (extremos de tramo de la
    misma red a ≤0.5 ft y ≤0.10 ft de cota, T a mitad de tramo, `FusionarCodosSeguidos` ANTES de
    agrupar; rejilla espacial: 300 utilidades ≈ 90 ms). `accesorios_view.py`: etiqueta «Codo 45°»
    (roja = obligatoria incumplida, ámbar = recomendada) en `Main._draw_accesorios` (cada `_redraw`);
    `btn_normas` en la barra de estado; toggle `act_show_acc` (Ver y Normativas). Ventana
    `normativas_dialog.py` = QWebEngineView + QWebChannel (`PuenteNormas`) sobre
    `docs/normativas_ui.html` (SIN textos propios: llegan en `_TEXTOS` traducidos; tema por tokens);
    `main()` fija `AA_ShareOpenGLContexts` antes de la QApplication. Solo avisa: no mueve geometría
    ni cambia el plugin. Tests: `tests/test_normativas.py`.
    **Excel** (2026-10-02): `normativas_excel.py` = plantilla UNIVERSAL (`COLUMNAS`: una fila por regla,
    encabezados/listas en español fijo = formato de datos, columnas grises de TRAZABILIDAD; hojas
    Instrucciones/Reglas/Referencias/Notas/Documento/Listas; `exportar`/`importar` → reglas, anexos,
    errores por fila). `normativas_clearance.py` convierte el Excel de «clearance tables» de los
    ingenieros (tablas por hoja, «5' MIN.¹», superíndices = referencias por hoja → `REF-nn` únicas,
    asteriscos → notas): NADA se pierde (`celdas_no_usadas` = [] y test de textos sobre el Excel
    real); lo dudoso = estado «Revisar». Tipos nuevos `separacion_horizontal|vertical`, `recubrimiento`,
    `requisito` (`_sin_revision`: se guardan/editan, aún no se verifican; `Resultado.pendiente`).
    `normativas.json` guarda además `referencias`/`notas`/`documento` (`cargar_anexos`,
    `Main.normas_anexos`); `fusionar` (importar) y `quitar` (reglas importadas). Ventana simplificada
    (fila: interruptor · título · valor · estado · Detalles; buscador). Tests:
    `tests/test_normativas_excel.py`.
    **Formato SIMPLE** (2026-10-06, contrapropuesta de los ingenieros = formato OFICIAL): `normativas_simple.py`
    (PURO) — «All (Flat)» una fila por regla en inglés (Utility A/B, Orientation, Case, Min/Max + unidad ft|in,
    Measured From, Notes, Reference(s) «HOJA:n», Source Sheet; grises opcionales Rule ID/Active/Mandatory/Status/
    Note IDs para el ida y vuelta), «References», pestaña por utilidad (solo lectura), «Fitting Angles» y «App
    Notes» (lo que el formato no cubre). `normativas_excel.importar` lo detecta por la hoja «All (Flat)»;
    «Exportar Excel» usa `normativas_simple.exportar` (la plantilla vieja sigue importándose). Tests:
    `tests/test_normativas_simple.py`.
  - **Unir utilidades** (2026-10-02): `unir_utilidades.py` (PURO) `planificar(pipes, filas, base,
    ft_per_px)` → `Plan` (pipe unida, empalmes, absorbidas, avisos): encadena punta con punta desde la
    BASE (la 1.ª seleccionada, `Main._orden_sel`; sus datos mandan), `invertir` las que van al revés,
    ≤0.5 ft = mismo vértice, hueco ≤10 ft = tramo recto; otro tipo o lejos → error con motivo. RAMAL (2026-10-02, `unir_ramales.py`): si una seleccionada nace a
    mitad de otra seleccionada, ésta se PARTE en la T (`partir_en_tes`: vértice nuevo con cota del tramo,
    corre cotas/kinds/fillets; T sobre un codo = error) y `mejor_recorrido` (DFS) elige el recorrido punta
    con punta que cubre todas (de una partida basta un trozo; menos hueco > más trozos > menos giro; un
    hueco solo entre puntas LIBRES y nunca entre trozos de la misma); los trozos sobrantes →
    `Plan.sobrantes` (utilidades aparte, `_rebuild_structures`, ámbar en la vista previa, que dibuja los
    codos con `_pipe_display_pts` igual que el lienzo). Las no seleccionadas nunca se tocan.
    Cotas: en el empalme quedan explícitas la de llegada/salida y, si no coinciden, antes se congelan
    (`snapshot_seg_values`) las interpoladas; corre `vertex_kinds`/`fillets`. `Main.unir_utilidades`
    (Ctrl+J, Edición, menú en bloque, clic derecho en el lienzo `_canvas_context_menu`): vista previa
    verde, confirma, pasa bancoducto y `cross_connections` a la base y `_delete_pipes`. Ctrl+clic en el
    lienzo = `_toggle_pipe_selection`; todas las seleccionadas se resaltan. `_snap_state` ahora guarda
    `cross_connections`. Tests: `tests/test_unir_utilidades.py`.
  - `model.py` — constantes, `VERSION`, `CHANGELOG`, capas Z, tabs.
  - `dxf_export.py` — exporta el DXF con XDATA `PDFCAD`.
  - `civil_catalog.py` — lee el catálogo imperial de Civil 3D (familias/tamaños/GUID).
  - **Agregar tamaño** (2026-10-02, botón verde «+» junto a `prop_size`/`bz_size`:
    `Main._boton_mas`/`_agregar_tamano`): `catalogo_tamanos.py` (PURO) + `_presion.py` +
    `_dialog.py`. Escribe en TODAS las instalaciones ≥2025 × idioma (`instalaciones()`); la
    familia se identifica por lo que NO se traduce: nombre del ARCHIVO .xml (gravedad,
    conductos, buzones) o `subcat|PART_FAMILY_NAME` (presión; PART_FAMILY_ID se repite).
    Formatos: FILAS (`<Column>/<Row>` + `RowUnique` UUID v5 determinista; extras como WTh
    interpolados), LISTAS (`<ColumnConstList>/<Item>`), PRESIÓN (clona la fila
    `WA_PIPE_MODEL` más cercana + `WA_CONNECTION_POINT` y crea los accesorios que falten).
    XML editado como TEXTO (BOM, CRLF y xlink intactos), respaldo `.pdfcad.bak`, repetir =
    `ya_existia`. Gravedad deja `Pipes Catalog/pdfcad_regenerar.txt`: el plugin
    (`CatalogoTamanos.cs`) lo ve al empezar IMPORTAR_RED → encola `PARTCATALOGREGEN` P y S +
    IMPORTAR_RED (PREPARAR_FAMILIAS borra la marca); `AgregarTamanoExacto` mete la medida
    exacta en la lista del dibujo (estructuras W×L/diámetro y tuberías W×H; el diámetro
    circular ya lo hacía `AgregarTamañoPipe`); presión: `AsegurarTuboPresion` copia el tubo
    del `pl.Catalog` (reflexión) con `AddPart`, y `MatchPresionTubo` ahora sí filtra por
    familia (`DescripcionDeFamilia`: la Description lleva «N in-» dentro del nombre).
    Tests: `tests/test_catalogo_tamanos.py` (ProgramData sintético) y `_ventana.py`.
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
  **Perfil longitudinal** (`CREAR_PERFIL_RED`, alias `CREAR_PERFIL_PRESION`; prueba de humo
  `PDFCAD_PERFIL_PRUEBA`): 19 archivos `Perfil*.cs` según `API-CIVIL/proyecto1/docs/PERFIL_DISENO.md`
  (fases T0–T6, todo nativo: eje propio `PDFCAD_PERFIL_EJE`, terreno, ProfileView por hoja,
  AddToProfileView + overrides, StationElevationLabel con override de texto). Cinco módulos PUROS
  (`PerfilRecorrido`, `PerfilDiseno*` ×3, `PerfilTextos`, sin `using Autodesk`) con arnés
  `API-CIVIL/proyecto1/PerfilPruebas` (`dotnet run -c Release`, 173 casos de F.12). Ojo: el diseño
  C.5 decía que un arco con bulge > 0 cae «a la izquierda»: cae a la DERECHA (corregido en código).
  Log de cada ejecución: `%TEMP%\PDFCAD_Perfil.log`.
  **Quiebres mínimos** (2026-09-30): `EnderezarQuiebres` (`ImportarRedEnderezar.cs`, antes de agrupar redes)
  quita en gravedad/conduit los vértices con giro ≤2° y ≤0.25 ft de la recta sin nada encima (buzón visible,
  caja, sólido, curva, ANCLA de un codo —vecino de un vértice curvo: mide el tubo del codo—, otra tubería a ≤1 ft,
  pieza distinta, caída o cambio de pendiente) → un tubo recto (dos en ángulo se montan/abren en planta y 3D; no
  hay limpieza de uniones en la API de estilos). Núcleo PURO `EnderezarNucleo.cs`, casos en el arnés `PerfilPruebas`.
  **Capa de la utilidad** (2026-10-05, `ImportarRedCapas.cs`, paso 5g de IMPORTAR_RED, tras las
  conexiones verticales): cada pieza de cada red creada (tuberías, estructuras, accesorios/apurtenencias de
  presión) pasa a la capa de su polilínea de origen (`redesConOrigen`: red → ImportPipe; red de capas
  mezcladas → la polilínea más cercana). Antes quedaban en la capa por defecto de Civil 3D. Conductos de
  bancoducto → `PDFCAD_DUCT_BANK` (su ImportPipe ya trae esa capa); sólidos sin cambio.
  **PREPARAR_FAMILIAS paso 5** (`PressureCatalogFiller`, completar tamaños de los SQLite de presión):
  DESACTIVADO desde 2026-10-05 con `ComandosPrepararFamilias.RELLENAR_CATALOGOS_PRESION = false`
  (código intacto; `true` lo reactiva). Los tamaños nuevos van por el «+» de la app.
  **Ángulo del codo** (2026-10-01): el XDATA `ANGULO` de la pieza sigue siendo el GIRO (lo usa el rótulo del
  perfil «45° BEND»); el Property Set `PDFCAD_Accesorio.Angulo_Grados` y `LISTAR_ACCESORIOS` muestran el
  ángulo ENTRE tuberías (`AccesorioPropertySet.AnguloVisible`: codo = 180° − giro), igual que la app.
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
    PIPE_IDX, HAS_DUCT_BANK, NET_NAME, NET_NAME_DEFAULT`.
    `NET_NAME_DEFAULT` (2026-10-02) = «TIPO-NÚMERO» (`model_ops.nombre_por_defecto`: capa +
    índice+1, no se guarda: se renumera al borrar); `RedesUnidasPorContacto` lo usa solo si el
    grupo de contacto no trae NET_NAME propio (nombre escrito > defecto; DXF viejo → «RED-<capa>»).
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
    `XDU_<NOMBRE>` (ASCII, ≤250 car.). En Civil 3D (2026-10-06, `ImportarRedDatos.cs`, paso 5h de
    IMPORTAR_RED, con `PropertySetPdfcad.cs` genérico): Property Set «PDFCAD_Utilidad» en cada tubería/
    accesorio/apurtenencia de presión (Utilidad, Numero_App = PIPE_IDX+1, Red + XD_* sin prefijo y
    XDU_* como «Usuario_…» de su polilínea de origen; red de varias capas → la más cercana; conductos
    de bancoducto → los de su tubería) y «PDFCAD_Estructura» en cada estructura (Codigo, Red + los de la
    `ImportStruct` a ≤0.5 ft; las estructuras nulas de extremos libres no llevan). Clases por
    `RXObject.GetClass` (nunca nombres a mano). Paleta Propiedades → «Datos extendidos».
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
    AGUA; `DEFAULT_UTILITIES` (selección al abrir) = TODAS (`SUPPORTED_UTILITIES`, pedido 2026-09-25); se
    desmarcan en «Capas de la hoja». Etiquetas: `UTILITY_LABELS`/`utility_label`/
    `utilities_label` (no volver a escribir «Eléctrico y Drenaje» a mano en la UI).
    `_classify_water`: línea `water_ungd` = `C-WATE?R[-_](paquete-)?(UNGD|UGND|PIPE)` sin
    ANNO/TEXT/CASE/FITT/APPT/VALV/METR/HYDR/-FH/-GV/WALL/…; estructura = V-WATR-VALT/MANH/
    STRU, V-FIRE-STRU, C-WATR-VALT/MANH/MHOL/STRC (válvulas, medidores, hidrantes =
    accesorios, no). Red a PRESIÓN (`NETWORK_KIND`): como en el dibujo manual,
    `rebuild_structures` no crea nodos en sus vértices; desde 2026-10-05 sus bóvedas
    reconocidas sí entran (`attach_vault_geometry(net="pressure")`: caja suelta, SÓLIDO si es
    rectangular). Reglas del perfil
    (`GeomOptions`, SOLO agua): `join_touching_ends` (puntas a ≤1 pt se cosen primero;
    punta JUSTO sobre una línea = T aunque esté cerca de su extremo — el join_gap del agua
    llega a 70 pt), `gap_turn_blocks` (`build_runs` no cruza un hueco si en su borde nace
    otro trazo no colineal), `markers_on_curves` (`strip_crossing_markers(curve_chains=)`).
    Auditoría: `tests/test_water_profile.py`; 68 hojas sin tramos sin tinta ni «V»; foto
    eléctrico/drenaje de los 4 PDFs = 0 diferencias.
  - **Perfil ALCANTARILLADO (2026-09-25)**: `SUPPORTED_UTILITIES` suma ALCANTARILLADO
    (kind `sewer_ungd`). `_classify_sewer`: línea =
    `C-(SSWR|SEWR|SEWER|SANI)[-_](paquete-)?(UNGD|UGND|UNDG|PIPE)` sin ANNO/TEXT/CASE/PATT/
    WALL/PROF/STRC/MANH/SCRN/COUT…; estructura = V-SSWR-MANH/STRU, C-SSWR-STRC/MANH/MHOL y
    `C-SSWR-(UNGD|UGND)-STRC(-N-301…)` (LABOE, propuestos). `V-SSWR-COUT` (cleanout) =
    accesorio; `C-SSWR-UNDG-SCRN-N` (DU08 h.36–38) = símbolo tramado del buzón, no línea.
    Red por GRAVEDAD (`attach_vault_geometry(net=NETWORK_KIND[utility])`). Reglas del
    perfil: TODAS las `GeomOptions` de drenaje y de agua + `polygon_circles`, y
    `RING_VAULT_UTILITIES`: el xref existente dibuja el ANILLO del buzón (polígono de 39
    lados, r≈9–11 pt) en la capa de la LÍNEA → `ring_symbol_paths` lo pasa a
    `vault_paths` (sin esto: 156 polilíneas circulares y saltos sin tinta al anillo).
    `polygon_circles`: ese polígono es círculo (`_polygon_circle`) y la bóveda queda
    `round_entry` → `_vault_entry` corta la recta contra el CÍRCULO, no contra la caja
    (DU10 h.5 (981,710): la diagonal de una «X» vecina rozaba la esquina de la caja).
    Auditoría (4 PDFs, 71 hojas): sin reglas 22 tramos sin tinta; drenaje 19; agua 11;
    ambas 8; + anillo 0 (y 0 «V», cobertura ≥99.77 %). Buzones: círculo, mediana 5 ft.
    Tests: `tests/test_sewer_profile.py` (capas) y `tests/test_sewer_integration.py`
    (ventana real offscreen: PDF → importar → DXF con NET_KIND=gravity, SHAPE=circle).
    Foto eléctrico/drenaje/agua de los 4 PDFs antes/después = 0 vértices distintos.
    `_cluster_vaults_layer`: en empate de capas manda la del contorno más grande (antes
    el orden de un `set` → `importable` cambiaba entre ejecuciones, DU10 h.2).
    **Precisión (2.ª revisión, mismo día; el usuario: «no inventamos nada, reconocer bien
    las líneas»)**: `precise_junctions` — un ramal que muere en el HUECO del linetype de
    una línea que sigue de frente (nodo «bend» en el centro del hueco) lleva el nodo al
    CRUCE de las rectas si cae en el hueco ±`JUNCTION_GAP_SLACK_PT`=2 (DU06 h.13: laterales
    2 pt inclinados). Desde 2026-10-06 (reporte del usuario, DU08 h.26: la diagonal «TE» iba
    hasta 2.4 pt fuera de su tinta hasta el centro del hueco de la «TE» de abajo) el cruce vale
    en TODAS las utilidades, pero solo para un ramal RECTO que ya se unía a ese nodo y cuya
    recta pasa a >`JUNCTION_TILT_MIN_PT`=0.25 pt del punto medio (mismas uniones; un ramal casi
    paralelo ya está sobre su recta y correrlo cambió una ruta en el filo de 35° en DU08 h.25;
    la tangente de una CURVA no sirve: DU10 h.19 perdía dos codos). Foto 6 utilidades × 4
    PDFs (`scripts/audit_perfil.py`): solo se mueven esos nodos (0.5–5.5 pt), en eléctrico,
    telecom, agua y gas; imprecisos 64 → 57 (eléctrico 33 → 29, agua 7 → 5, gas 1 → 0), sin
    tinta y «V» iguales, codos 1250 → 1254 (DU08 h.25/26: el arquito donde la diagonal nace de
    la horizontal); dibujado→tinta p90 igual o mejor (telecom DU08 h.40 neutro). Tests:
    `test_ramal_que_muere_en_el_hueco_llega_por_su_recta`, `test_du08_h26_diagonal_te_…`; `continuation_before_vault` — una punta cuya continuación de
    frente está más cerca que el borde de la bóveda no salta a la bóveda (DU08 h.36: el
    guión del medio de una curva se estiraba ENCIMA del siguiente → dos tramos
    superpuestos); `OUTLINE_AXIS_UTILITIES` + `outline_axis_paths`: rectángulo delgado
    (≤8 pt, largo ≥6×) en la capa de la línea = tubería en contorno → su EJE (DU06 h.4
    `PROP_SEWER_PIPE_ALGN|C-SSWR-UNGD-N`; desde 2026-10-02 en TODAS las utilidades, ver
    `recognition_walls`). GLOBAL (núcleo): el filtro de ruido compara
    `pl.length >= dash_long - 0.5` (dash_long sale de largos redondeados: un trazo de 209.8
    con dash_long=210 se tiraba) — cambia drenaje (DU10 h.17/18: lateral propuesto de 120
    pt recuperado) y agua (18 trazos sueltos recuperados, todos con tinta); eléctrico 0.
    **Continuidad (3.ª revisión, mismo día; hoja compuesta DU06 13+14, «debería ser
    continua»)**, todo bajo `precise_junctions`: `join_touching_ends` NO cose por contacto
    una punta con continuación de frente al otro lado del hueco (`continues_ahead`; el
    lateral tocaba la punta del guión y quedaba esquina + principal cortada — solo pasaba
    cuando `_split_by_fit` partía la corrida, p.ej. por el recorte de la pieza); el ramal
    se une al «bend» por el cruce dentro del hueco (`_gap_crossing`) aunque el punto
    medio de un hueco ANCHO no quede sobre su eje; 5d-ter: punta que tocaba y quedó libre
    = T justo donde toca (DU08 h.40, junto al buzón); quiebre suave con letra en el hueco
    hasta `glyph_bridge` (`letter_in_gap`, curvas con «ss»); `classify_paths(
    keep_line_strokes=)`: un trozo que nace en la punta de un guión con su rumbo no es
    asta de letra aunque se repita (DU08 h.37 «—//—ss—»). Auditoría de huecos: puntas
    enfrentadas y colineales a <40 pt entre polilíneas distintas = 0 en los 4 PDFs.
    `scripts/audit_alcantarillado.py`: auditoría con métrica de PRECISIÓN (p90 de la
    distancia perpendicular a guiones paralelos ≥3 pt de su propia capa; ojo: sin esos
    filtros, las letras «ss» y los huecos dan cientos de falsos positivos). Referencia:
    859 tramos, 0 sin tinta, 0 «V», 3 «imprecisos» = ejes de tuberías con doble línea.
    **Buzón en un quiebre (2026-09-26, pregunta del usuario en DU08 h.25)**: `manhole_bend`
    (solo alcantarillado): dos puntas de la MISMA capa que se tocan (≤`ENDS_TOUCH_PT`) dentro
    del mismo buzón REDONDO (`round_entry`) se cosen ahí con nodo `vault` (con su `vi`), si cada
    pieza mide ≥`MANHOLE_BEND_MIN_RUN_PT`=6 (una astilla del símbolo no cuenta: DU08 h.45). La
    costura por contacto excluía el interior de las bóvedas y el nodo de bóveda solo existe si
    una línea la ATRAVIESA de frente: la tubería que gira en el buzón quedaba en dos piezas
    (horizontal cortada en el borde + pieza interior). Auditoría: 6 hojas cambian, todas a una
    pieza menos (≈8 pt de hueco cerrado); 0 sin tinta, 0 «V», 3 imprecisos = 3.
  - **Perfil GAS (2026-09-25)**: `SUPPORTED_UTILITIES` suma GAS (kind `gas_ungd`; red a
    PRESIÓN como el agua: sin cajas automáticas). `_classify_gas`: línea = capas de SOLO
    estado de la red existente (`…REF-EXIST_NGAS|C-NGAS-A/-D/-E`, sin «UNGD»),
    `C-N?GAS-(paquete-)?(UNGD|UGND|UNDG|PIPE)` y `PROP-GAS-ALGN` (alineamiento C3D del
    LABOE), sin ANNO/TEXT/CASE/VALV/METR/RISR/…; estructura = V-NGAS-VALT (+ MANH/STRU,
    C-NGAS-VALT/STRC); medidores, válvulas y risers = accesorios. Única regla de perfil:
    `glyph_hooks` (`classify_paths` → `_glyph_hooks`): el gancho de la «G»/«g» del linetype
    «—G—» es un path aparte que pasaba por CODO; un arco que cabe en una letra, la toca y se
    repite ≥3 veces con el mismo largo es letra. Sin ella: 38 tramos sin tinta (la línea
    entraba al gancho y saltaba a la vecina, DU10 h.7) y un rodeo de ~24 pt por cada «G».
    Auditoría `scripts/audit_perfil.py GAS [config]` (genérica: cualquier utilidad; config
    none/drain/water/sewer/profile/`profile+regla`): 68 hojas, 636 tramos, 0 sin tinta,
    0 «V», cobertura ≥99.76 %, 1 impreciso (DU10 h.15, ramal 1 pt inclinado hacia el hueco
    de la línea). Las reglas de drenaje/agua/alcantarillado no mejoran o empeoran (sewer: 41
    sin tinta); `precise_junctions` quita ese impreciso pero traza cuerdas de 32 pt sin tinta
    sobre los rodeos del gas alrededor de símbolos (LABOE h.26/30): NO usarla. Tests:
    `tests/test_gas_profile.py` y `tests/test_gas_integration.py` (DU10 h.7 → DXF
    NET_KIND=pressure, ABANDONED=1 en `C-NGAS-D` con «//»).
    Duplicados: GAS está en `DEDUP_OCG_UTILITIES` y en `DEDUP_ADD_SUFFIX_UTILITIES`
    (`duplicate_ocgs(ignore_add_suffix=True)`: «-E-ADD» ≡ «-E»; en empate se conserva la
    capa sin «-ADD»): DU10/DU08 traen la existente en `REF-EXIST_NGAS|C-NGAS-UGND-E` y
    otra vez en `REF-EXIST_SSWR|…-E-ADD` y `SERVICE_MAPS_CALLOUT|…-E-ADD` → la misma
    tubería salía 3 veces (19 líneas de más en los 4 PDFs; foto de las 5 utilidades: solo
    cambia gas). Ojo al revisar: en DU08 h.22 la etiqueta «10+00» tiene fondo BLANCO
    dibujado DESPUÉS de la línea propuesta (`_Xref` con fill blanco) y tapa su final: la
    línea SÍ llega a x=1255 (inicio del alineamiento sobre la existente); no es inventada.
    Ojo también: `Shape.finish` de fitz cierra la polilínea por defecto (`closePath=True`)
    — al dibujar overlays de revisión pasar `closePath=False` o se ven diagonales falsas.
  - **Perfil TELECOM (2026-09-25)**: `SUPPORTED_UTILITIES` suma TELECOM (kind `tele_ungd`;
    red de CONDUCTOS como el eléctrico: CAJA solo en vértices de bóveda real). `_classify_telecom`:
    línea = `C-(TELE|COMM|CATV|FIBR|FO)-(paquete-)?(UNGD|UGND|UNDG|PIPE)`, la propuesta
    `T-PROP-COMM(_ATT)` y el banco de ductos de Metro `N-COMM-DUCT-BANK-PL(-SC/-SE)` («—SC—»,
    una línea con letras); fuera `C-TELE-OVHD` (aérea, como `C-ELEC-OVHD`), ANNO/TEXT/TEXL.
    Estructuras: C-TELE-VALT/MANH/MHOL/STRC, V-COMM-MANH/VALT/STRU, V-COMM-PBOX, V-CATV-PBOX,
    `N-Comm-Junction Box*`; «JUNCTION» está en `NON_VAULT_TOKENS` (como PBOX; sin línea
    también se importa, como caja suelta, desde 2026-10-05). CABT/RISR = accesorios.
    Única regla de perfil: `stroke_letters` — las letras del linetype son TRAZOS SUELTOS:
    (1) la «t» de «—t—» = asta perpendicular con gancho (pasa por codo) + travesaño de 2.4 pt
    (pasa por guión) → `_stroke_letters` (curva ≤12 pt + trazo ≤`LETTER_TICK_MAX_PT`=4 que se
    tocan, pareja repetida ≥3); (2) «TE»/«SE» de Metro, solo trazos rectos: el travesaño de la
    «T» toca la «E» y se funde en `classify_paths`, pero el asta solo toca ese travesaño →
    pasadas extra `_swallow_letter_strokes` en `reconstruct` DESPUÉS de `strip_crossing_markers`
    (antes se comían las barras del «//» y la línea dejaba de ser AB), solo trazos
    ≤`LETTER_STROKE_MAX_PT`=8 (un guión de 11.5 pt de una curva a guiones es línea, LABOE h.26),
    que NO continúen un guión largo (rumbo ±35°, desvío ≤1 pt + 10 % de lo que se aleja: en un
    arco a guiones los cortos junto a la «t» giran con la curva) y con ≥2 repeticiones
    (`LETTER_STROKE_MIN_REPEAT`: un tramo «—SE—» lleva solo dos «E», DU08 h.38).
    Auditoría `scripts/audit_perfil.py TELECOM` (ahora NO cuenta como «sin tinta» el tramo hasta
    la esquina C de un codo `fillet`: se dibuja con su arco; gas/alcantarillado tenían 0 codos):
    sin reglas 110 sin tinta / 117 imprecisos; con el perfil 0 / 15, 0 «V», cobertura ≥99.51 %,
    AB 99, 59 codos. Reglas de agua/alcantarillado/gas: no mejoran. Tests:
    `tests/test_telecom_profile.py`, `tests/test_telecom_integration.py` (DU10 h.5 → CAJA con
    medidas, DXF NET_KIND=conduit). Foto de las otras 5 utilidades antes/después: sin cambios.
    2.ª regla (2026-09-26, reporte del usuario en DU08 h.26): `corner_before_vault` — en la
    Fase B una punta que forma ESQUINA con otra punta libre (ambas avanzan ≤ join_gap, giro
    ≥`CORNER_MIN_TURN_DEG`=20° —las casi-de-frente no, su intersección es inestable— e
    interior ≥73°, esquina fuera de la caja) antes que el borde de la bóveda NO salta a la
    bóveda; la une la pasada de esquinas. Caso: la diagonal «—SC—» gira 45° en el hueco de la
    «SC» hacia el tramo que sale de la caja; se estiraba 30 pt sin tinta hasta la esquina de la
    caja. El audit no lo veía (el tramo inventado pasaba sobre las letras, que son tinta de la
    capa, y moría en el margen de la caja). Auditoría: 12 hojas cambian, todas a menos tramos;
    0 sin tinta, 0 «V», imprecisos 15 = 15. Las líneas «TE» de esas hojas son
    `U-TRPW-DBNK-P` (Traction Electrification ductbank de Metro, leyenda de DU08 h.33 =
    energía, NO telecom): desde 2026-10-05 entran a ELECTRICO por sus letras
    (`recognition_letters`), igual que `N-COMM-DUCT-BANK-PL-SE` («SE»).
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
  versión en `app/model.py` (y el manual: `app/docs/manual.es.html` + `manual.en.html`, un
  `<section data-title>` por capítulo, colores `{{token}}` del tema; lo muestra `manual_dialog.py`).
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
