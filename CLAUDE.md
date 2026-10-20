# pdf-to-cad — guía del proyecto

Pipeline **PDF de plano → DXF → Civil 3D** para redes de utilidad (agua,
alcantarillado, drenaje, gas, eléctrico, telecom). Todo en **unidades imperiales
(pies)**.

## Mapa del repo

- `app/` — **app de escritorio (PySide6)** donde el usuario digitaliza sobre el PDF.
  - `main.py` — punto de entrada (arma `sys.path`: `app/` + raíz).
  - **Carpetas por capa (2026-10-08, en curso)**: `app/nucleo/` = lógica PURA del dominio (sin Qt ni fitz):
    `model`, `model_ops`, `xdata`, `duct_bank`, `unir_utilidades`, `unir_ramales`, `quiebres_curvas`,
    `accesorios`, `normas_catalogo`, `normas_excel`, `normas_excel_ayuda`, `normas_validar`, `normas_aprobacion`, `tabla_datos`, `tabla_excel`, `conflictos`, `modelo3d`, `mallas3d`, `accesorios3d`, `verticales3d`, `marcas3d`, `ficha3d`, `edicion_bloque`,
    `limpieza`, `limpieza_tramos`, `vertice_curva`, `conexiones_verticales`, `trazo_asistido`, `angulos`, `indice_plano`, `memo_modelo`, `deshacer`, `reducciones3d`, `rotulos3d`. Se importan
    como `from nucleo import model_ops` / `from nucleo.model import …` (nunca `import model_ops`: ese nombre
    ya no existe). Regla: la interfaz usa `nucleo`, `nucleo` NUNCA importa la interfaz (PySide6, `i18n`,
    ventana…; sí `i18n_core`). Más abajo los módulos se nombran sin la carpeta: `model_ops.py` = `app/nucleo/
    model_ops.py`. `app/reconocimiento/` (mismo día) = lectura PURA del PDF vectorial: `recognition`,
    `recognition_geom`, `routes` y los demás `recognition_*` sin Qt (`from reconocimiento import recognition`;
    `recognition.py` sube TRES carpetas para poner la raíz del repo en `sys.path`). Las vistas Qt del asistente
    (`recognition_dialog`, `_summary_view`, `_review_view`, `_layers_view`, `_preview_draw`) siguen en `app/`.
    `app/hoja/` (mismo día) = hoja de trabajo PURA: `composite`, `composite_checks`, `composite_scan`,
    `composite_seam`, `pdf_layers`, `pdf_legend`, `sheet_crops`, `sheet_layout`, `organized_layers`,
    `leyenda_cruce`, `leyenda_estandar`, `leyenda_trazos`, y los de mapas sin capas `pdf_styles`, `texto_pdf`,
    `leyenda_mapa`, `leyenda_mapa_lectura`, `acometidas_mapa` (`from hoja import composite`). Los diálogos y vistas
    del compositor/capas (y `composite_choice`, que usa `i18n`) siguen en `app/`.
    `app/catalogo/` = `civil_catalog`, `catalogo_tamanos`, `catalogo_tamanos_presion` (PUROS) y `app/exportar/` =
    `dxf_export` (NO puro: recibe la ventana `win` y usa `geometry.point_in_poly`; `geometry` importa QtGui).
    `app/ui/` (mismo día) = TODA la interfaz Qt, en cuatro subpaquetes: `ui/ventana/` (`app_window`, `ventana_*`,
    `ventana_comun`, `respaldo_editor`, `autoguardado`), `ui/asistente/` (compositor, capas de la hoja, leyenda,
    vista previa del reconocimiento y sus vistas: `composite_dialog`/`_view`/`_choice`…, `layer_dialog*` (incl. `layer_dialog_recog`, de dev_santos_v2),
    `layer_info_panel`, `layer_std_legend`, `recognition_dialog` y `recognition_*_view`/`_preview_draw`,
    `wizard_widgets`, `pdf_view_quality`, `alignment_tools`, `tool_strip`…), `ui/dialogos/` (`dialogs`,
    `normas_dialog`, `tabla_datos_dialog`, `vista3d_dialog`, `edicion_bloque_dialog`, `limpieza_dialog`, `duct_bank_dialog`, `xdata_dialog`, `catalogo_tamanos_dialog`, `manual_dialog`,
    `shortcuts_dialog`, `blank_canvas_dialog`) y `ui/comun/` (`canvas`, `widgets`, `ui_common`, `theme`, `icons`,
    `busy`, `responsive`, `side_panels`, `thumbnails`, `workers`, `accesorios_view`, `avisos_view`, `capa_marcas`, `visor3d`, `cubo_vistas`, `fondo_pdf`, `recorte_nitido`, `teselas`, `teselas_hijo`, `teselas_servidor`,
    `teselas_vista`). Se importan como
    `from ui.ventana import app_window`, `from ui.comun import widgets`… OJO rutas de recursos: `icons.py` sube
    TRES carpetas para llegar a `app/icons` (en el .exe usan
    `sys._MEIPASS`, donde PDF-a-CAD.spec deja `icons/` y `docs/`). `app/traduccion/` (mismo día) = `i18n`,
    `i18n_core`, `i18n_en`, `i18n_en_changelog` (NO se llama `i18n/`: chocaría con el módulo `i18n.py` y el motor
    puro arrastraría Qt); `i18n.py` sube DOS carpetas para `app/docs` (en el .exe, `_MEIPASS/docs`). En `app/`
    quedan solo `main.py`, `geometry` y `project_io`. Cada traslado se verificó con la suite completa
    antes/después y fotos con el código viejo vs. el nuevo (reconocimiento de un PDF real, capas/leyenda/
    composición, DXF exportado y catálogo): idénticas. Para mover más: el mismo método (script que mueve y
    reescribe imports, `git add -A` para que Git vea renombres).
  - `app_window.py` — ventana principal `Main`. La UI se arma en `_build_ui`, que
    llama a `_build_menu` / `_build_toolbar` / `_build_left_dock` / `_build_right_dock`
    / `_build_statusbar` (todos dejan sus widgets como `self.*`, en ese orden).
    **Partida en clases mezcla (2026-10-08)**: los métodos de `Main` se movieron TAL CUAL, por tema,
    a `ventana_*.py` (`MenuMixin`, `PanelIzquierdoMixin`, `PanelDerechoMixin`, `ModosMixin`, `ClicsMixin`,
    `UtilidadesMixin`, `CatalogoMixin`, `SeleccionMixin`, `ListasMixin`, `MarcasMixin`, `DibujoMixin`,
    `ConflictosMixin`, `CoordsMixin`, `BuzonesMixin`, `MoverPrecisoMixin`, `CurvasMixin`, `HerramientasMixin`,
    `BancoductosMixin`, y desde 2026-10-08 `EdicionBloqueMixin` de `ventana_bloque`, desde 2026-10-10 `Vista3DMixin` de `ventana_vista3d`) y `Main` las hereda: `win.<método>` sigue igual (313 métodos, mismo código).
    `ventana_comun.py` = las MISMAS importaciones de app_window (`from ventana_comun import *`).
    En app_window quedan `__init__`, páginas, deshacer, abrir/asistente, proyecto (con `_dirty`: usa
    `self.__…`, que no puede ir a una mezcla), exportar y arrastrar-soltar. OJO: los métodos que crean
    `RecognitionWorker`/`PipelineWorker` se quedan en app_window (las pruebas los cambian con
    `monkeypatch.setattr(app_window, …)`); en una mezcla no se usa `Main.` (usar `self.` o la clase mezcla).
  - `canvas.py` — el lienzo (`Canvas`, QGraphicsView).
  - `fondo_pdf.py` — **hoja enorme** (reporte del usuario 2026-10-09: 18 piezas → «code=5: Overly large
    image»: MuPDF no crea pixmaps de más de 1 GiB, ancho × alto × 3 ≤ 2³⁰; 18 hojas del DU06 a zoom 3.5 =
    1006 Mpx). `render_pix(page, zoom)`: si cabe, EL MISMO `get_pixmap` de siempre (`escala`=1); si no, a
    ≈`PRESUPUESTO_PX`=100 Mpx con `escala` < 1 = px de la imagen por px de la vista. Las coordenadas NO
    cambian (pt × zoom): `Canvas.set_image(qimg, escala, tam)` agranda la imagen 1/escala (`FondoItem`) y la
    escena mide `tam`; usar `canvas.tam_hoja()` (no `pixmap().width()`) para el tamaño de la hoja en px.
    `Nitidez` (en el lienzo, «Capas de la hoja» y la vista previa): al acercarse pide las TESELAS nítidas
    de lo visible (`FondoItem.superficie`, ver «Teselas» abajo; la imagen no se pinta debajo de una tesela
    si la opacidad del PDF < 100 %, si no la tinta se oscurecía); el imán a la tinta mira la ventana
    del clic a resolución completa (`snap_nitido`: mismo punto que con la hoja normal). El .digproj guarda
    `fondo_escala`/`fondo_tam` SOLO si la hoja va reducida; `leer_png` quita el tope de 256 MB de
    `QImageReader` (antes un proyecto con hoja compuesta de ~2 hojas no se reabría). `gris`: grises por
    bloques (idéntico byte a byte). Si `_apply_composite` falla, `_volver_a_la_hoja` recarga la hoja anterior
    (sin respaldo el editor quedaba sin PDF). Tests: `tests/test_hoja_enorme.py` (bajan el límite con
    `chica`). **Nítida a CUALQUIER zoom** (pedido del usuario 2026-10-13, compositor sobre el «QS Water» de
    Phoenix borroso): `recorte_nitido.py` (sin Qt) lo usan las teselas de `Nitidez` (editor, Capas, vista
    previa: también con la hoja NORMAL —`nuevo_item` da siempre `FondoItem`; con escala 1 se pinta igual que
    un QGraphicsPixmapItem: misma imagen, sin `setScale` ni modo suave— y sin el tope «la resolución de la
    imagen»), `ViewportSharpener` («Área a tomar», `TeselasItem` a z=1) y `PieceItem` (`superficie`; el
    `update_sharp` de antes queda como atajo). `Hojas` = caché de listas
    de dibujo por (documento, hoja) —`soltar()` al cambiar capas— y `escala` (pantalla × 1.15, `MAX_PX`
    24 Mpx, `MAX_ESCALA` 64 px/pt; nunca menos que el tope de antes: `minimo`). **Fuentes Type3** (mapas SIG
    de Phoenix): MuPDF rasteriza cada letra en su caja DECLARADA (FontBBox ~20× la letra) aunque caiga
    fuera del recorte —a 24 px/pt 6 s, a 60 px/pt 1 min—; si la hoja usa Type3 (`usa_type3`), el recorte
    pasa por `fz_new_culling_device_with_rects2` (descarta una letra si >50 % de su caja cae en los
    rectángulos) con rectángulos fuera de la zona que contiene TODA caja de letra que toca el recorte (cajas
    medidas igual que MuPDF con un `FzDevice2` Python, `Medidor`): mismos píxeles byte a byte (verificado en
    recortes al azar, también hoja girada; OJO: MuPDF suaviza los bordes distinto según el RECORTE pedido
    —hasta 20/255 en ~1 % de los píxeles de una línea—, así que «mismos píxeles» es siempre contra el mismo
    recorte). `Hojas.escala`/`TOPE_LETRAS_MPX`/`REFINO_MS` (recorte con tope de letras y refino con la vista
    quieta) ya no los usa ninguna vista: las teselas acotan solas el costo. Sin Type3 (DU06/DU08/LABOE,
    Type0) el camino de siempre (`dl.get_pixmap`). El imán, las coordenadas y la imagen base no cambian.
    Tests: `tests/test_nitidez_zoom.py`. Pendiente: con 18 hojas, armar tarda ~28 s (`compute_bridges` relee
    los vectores de cada hoja) y «Capas de la hoja» ~49 s (`page_layers`, letras, `trazos_visibles` sobre toda
    la hoja compuesta); el compositor tarda ~20 s en dibujar las vistas generales de 36 piezas (`rebuild`).
  - **Teselas** (reporte del usuario 2026-10-15: con la hoja compuesta de 36 mapas o su reconocimiento,
    cada parada del zoom trababa la ventana 0.3–1.3 s —la primera ~7 s: lista de dibujo + 494 mil cajas de
    letras Type3— porque el recorte nítido se dibujaba en el hilo de la interfaz; PyMuPDF NO suelta el GIL
    al dibujar, un hilo no sirve). Como los visores de mapas/planos: `ui/comun/teselas.py` (puro) — nivel L
    = 2^(L/2) px/pt (pasos de √2: la tesela queda entre 1 y 1.41× la pantalla; con pasos de 2 dibujaba hasta
    4× los píxeles a la vista), `TAM`=1024 px, rejilla de píxeles de la hoja a esa escala (vecinas exactas,
    origen real en `pix.x/pix.y`), `teselas_en` = centro primero + anillo de 1 para el desplazamiento,
    `hace_falta` = la pantalla pide ≥ 1.1× la imagen base (antes 1.4: el primer paso de rueda se veía borroso), `dibujar` = `Hojas.render` (culling Type3).
    `teselas_hijo.py` (sin Qt) = el proceso dibujante (lee el PDF a MEMORIA: no deja abierto el temporal
    que la ventana borra; capas por `layer_ui_configs` → `firma` en la clave; «pedir» REEMPLAZA la lista;
    «calentar» prepara lista de dibujo + cajas antes del primer zoom; `PDFCAD_TESELAS_LOG=1` = tiempos
    por tesela en stderr). `teselas_servidor.py` (`servidor()`): `cuantos()` procesos (≤`MAX_PROCESOS`=3
    según núcleos y RAM, `proceso_hijo.paralelos`), dos `Pipe` de un sentido por proceso + hilo de envío
    (un PDF de 30 MB no traba), lectura con QTimer `SONDEO_MS`=15, reparto con la tesela pegada a su
    proceso, caché LRU `MAX_MB`=384 que nunca suelta lo que se mira, 3 muertes → dibuja aquí mismo;
    `PDFCAD_PROCESO=0` (pruebas) = aquí mismo y al instante. `teselas_vista.py`: `Superficie(item)` (coords
    del item = pt × k + d: `FondoItem` k = zoom·escala; `PieceItem` k = ov, d = −origen, `limite` = clip
    de la pieza; `TeselasItem` para el «Área a tomar») — `actualizar(vista)` pide; `pintar` dibuja la base
    y encima las teselas listas o, mientras faltan, las del nivel anterior (o siguiente) recortadas a su
    cuadro, sin suavizado de bordes (sin rayas entre vecinas); `exclusivo` (opacidad < 1 o «Fundir bordes»)
    = la base no se pinta bajo una tesela. Nunca usar el nombre `tx` para la tubería en el hijo (fue un
    error: la columna de la tesela la pisaba). Medido con 36 mapas de agua (editor, 1600×900): la ventana
    nunca se detiene > ~45 ms; vista entera nítida en 0.6–1.1 s por zoom (1 proceso y niveles ×2: 2.6–4 s);
    compositor de 36 piezas 0.2–1 s. Tests: `tests/test_teselas.py` (mismos píxeles, colocación exacta a
    1:1, otro nivel mientras falta, opacidad, capas, proceso real por ruta y por bytes).
  - `widgets.py` — widgets reutilizables (`InlineEdit`, `_SegInvSpinBox`, `_NoWheelFilter`,
    `ZoomPanView`, `MiniMap`: minimapa con recuadro de lo visible sobre una ZoomPanView;
    `set_layout(items, scene_rect)` = esquema de hojas (cajas con etiqueta, lo que
    pidió el usuario: organización, no dibujo; a la medida del número de hojas —la hoja típica a
    `HOJA_PX`=64, mínimo `LAYOUT_MIN_PX`, máximo el `LAYOUT_*` de siempre—: con 1–2 hojas se hacía
    gigante, pedido 2026-10-15) o `set_thumbnail(pixmap, rect)`.
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
    **Varias curvitas → UNA curva** (reporte del usuario 2026-10-19, DU06 UD-205 «—SC—» junto a
    «CB-216 LAT», h.7 (índice 6) ~(785, 1059)): el codo de la 1.ª/2.ª pasada era el arco del PDF
    (r 14.4 pt), pero la punta de la diagonal se apartaba 0.17 pt de su recta y `fit_continuous`
    (umbral `FIT_PT`=0.12) lo cambió por `circular_trace`, que ajusta recta + arco + recta como
    círculos → tres codos (r 67.6/18/13.5). `recognition_unir_codos.unir_codos` (PURO, al final de
    `fit_fillets`, antes de `split_wide_fillets`, TODAS las utilidades): ristra de codos seguidos del
    mismo giro, con solo vértices blandos entre ellos → UN codo tangente a la recta que llega y a la
    que sale (primero las rectas de los tramos vecinos ≥`RECTA_MIN_PT`, luego las tangentes de los
    codos de punta; el vértice blando sobre la recta se quita). LA TINTA MANDA (con 0.5 pt contra el
    dibujo se juntaban curvas de radio VARIABLE que `fit_continuous` sigue a ≤0.13 pt: DU06 h.5 telecom/
    eléctrico y DU08 h.22, `test_curve_precision`/`test_curve_structure_contacts`): radio por mínimos
    cuadrados sobre la tinta (`strokes` de `fit_fillets`) que el dibujo de ahora sigue (≤`SIGUE_PT`=0.25),
    aceptado si en CADA uno de esos puntos queda a ≤ max(lo de ahora, `PRECISION_PT`=0.12)+0.01, en los
    huecos sin tinta a ≤`UNIR_TOL_PT`=0.5 del dibujo de antes, `fillet_geo` sin recorte y los codos
    vecinos idénticos; sin tinta (<6 puntos), solo si ya era el mismo círculo (≤0.12). Arco que muere en
    un nodo sigue muriendo en él (`node_a/b`). Si la ristra entera no cabe, sus tramos más largos.
    Curva compuesta de verdad (60/120), radio variable y «S» no cambian. UD-205: r = 14.7 pt.
    Marca `unidos` = nº de codos. Tests: `tests/test_curvitas_una_curva.py` (sintéticos + recorte de la
    zona de DU06, ~2 s).
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
  - `recognition_angulos.py` + `recognition_angulos_calc.py` (PUROS, numpy) — **quiebres a pasos
    de 0.25°** (pedido del usuario 2026-10-17: «no hay codos de 45.648°; sí de 11.25°, 22.5°,
    45°…»). ÚLTIMO paso de `recognize_page` (tras el imán a bóvedas), en las dos variantes (rutas
    unidas y tramos), con capas y sin capas: cada deflexión (codo incluido) queda múltiplo EXACTO
    de `PASO_DEG`; nada más cambia (vértices, tipos, codos, radios). Rejilla: todos los tramos de
    una línea con rumbo φ + k·0.25° (φ por mínimos cuadrados, peso largo²; las líneas que se tocan
    PUNTA CON PUNTA comparten φ: el ángulo entre ellas también es un codo; las T no). Vértices
    nuevos = mínimos cuadrados con los rumbos como filas DURAS y los contactos (vértice compartido,
    punta sobre otra línea, con el MISMO desfase de antes) como filas BLANDAS de peso 1e6; un
    vértice compartido queda bit a bit el mismo punto (`_MISMO_PUNTO_PT`; pesa `_PESO_COMPARTIDO`
    =1e3 veces más, así un desacuerdo lo absorben las puntas sobre una línea), una punta sobre otra
    línea a ≤`CONTACTO_MAX_PT`=0.05 pt. Dos contactos casi paralelos (<10°) en un vértice se
    promedian por lo que MUEVEN (no por su término b: dependía del origen de la hoja, se iba
    72 px). Orden (`_orden`): la ANFITRIONA de una T (punta sobre su tramo) antes que sus ramas
    (una recta no puede seguir a dos ramas ya movidas), luego la que toca a una ya ajustada, la más
    larga. (T en un VÉRTICE de la anfitriona como rama: −20 líneas sin ajustar, pero curvas de DU08
    h.22 a 0.18 pt de la tinta: descartado.) Punta «stop»/«cut» = sigue SOBRE el contorno de su bóveda / el corte (`bordes`: `vault_snap.boundary`
    + `clip_polys`); fijarla del todo dejaba mal puesto un vértice casi recto entre dos puntas
    fijas. Micro-tramo (<`MICRO_PT`=0.25 pt: dos vértices de buzón de Phoenix a 0.02–0.1 pt) = un
    punto rígido; el ángulo es el de los tramos a cada lado (`deflexiones_deg(pts, minimo)`).
    Codos (`_rehacer_codos`): mismo radio, A/B/centro de `fillet_geo` SIN topes y luego
    `recognition_arcs.fit_to_editor` (como el reconocimiento: con los topes, un codo que el editor
    recorta bajaba de r 211 a 163 y salía de la tinta, DU06 h.3); si la tangencia caía en el
    vértice vecino (nodo, ancla en la tangencia, mitades del codo en «U») el tramo se fuerza a
    r·tan(Δ/2) (`_piernas_de_codos`, fila dura) y sigue ahí exacto (las mitades comparten centro y
    radio). Intentos: radio exacto + contactos 1e6; si algún vértice se corre >`MOVER_POCO_PT`=0.5
    pt (casi tangente/paralelo: DU08 h.47, h.49 se deslizaban 1–10 pt) se prueban sin las
    piernas y con contactos 1e3 y gana el que menos mueve. Línea que se apartaría >`DESVIO_MAX_PT`=2
    pt (de lado, `lateral`: deslizar por su recta no cuenta), daría vuelta un tramo o separaría un
    contacto → queda como estaba (solo sigue a sus contactos), aviso «Líneas con el ángulo del
    plano…» (REVIEW, `angles_off_px`). `reubicar` lleva `vault_pts`/`vault_snaps_px` a su vértice.
    Medido (DU06/DU10/DU08/LABOE × 6 utilidades + Phoenix agua/alcantarillado, 445 hoja×utilidad):
    15 380 quiebres a 0.25°, 94 líneas de ~5 400 sin ajustar, desvío lateral p90 por hoja ~0.07 pt
    (máx 1 pt), contactos ≤0.05 pt, ~30 ms por hoja×utilidad (≤1 s en mapas de Phoenix);
    `audit_perfil`: mismos tramos, codos, cobertura, «sin tinta» y «V»; «imprecisos» 85 → ~100
    (las nuevas a 0.76–0.84 pt, una a 1.1). Pruebas que buscaban coordenadas EXACTAS del PDF las
    buscan ahora a 0.1–0.25 pt. Ojo: `limpieza_tramos` (al exportar) y `limpieza` pueden mover un
    vértice en sus arreglos de tramos diminutos (no conocen la rejilla). Tests:
    `tests/test_angulos_quiebres.py`.
  - **Fase B sin inventos** (reporte del usuario 2026-10-09, DU06 h.10/h.12, «—SC—» de telecom: «hay que
    interpretar lo que da el PDF, no dibujar cosas que no existen», en TODAS las utilidades). En
    `recognition_geom.resolve_nodes` (llegadas a bóvedas): (A) `_vault_entry(run=)`: una CURVA que ya
    atravesó la bóveda no se recorta hacia atrás sobre más de `RETRACT_INK_MAX_PT` de su tinta
    (`_curve_ink_beyond`; antes: vuelta en U de 28 pt hasta el borde y el arco perdido); (B)
    `letter_continuation`: una punta no se estira HACIA ADELANTE hasta la bóveda si antes tiene su
    continuación de frente con una letra del linetype en el hueco (la une «letra en el hueco»), o si esa
    continuación, casi igual de cerca (≤ entrada + `NODE_OFF_LINE_PT`), es la punta de un trazo TODO dentro de
    la caja (DU08 h.21, DU10 h.11: la diagonal se prolongaba hasta la esquina de la caja). Ojo: con la bóveda
    DETRÁS `move` es un retroceso (la regla volteaba llegadas buenas, DU08 h.26) y la punta de una línea que
    ATRAVIESA la caja no es «continuación»: es la llegada opuesta que da el nodo (DU06 h.4); (C) una llegada
    no puede pasar el OTRO extremo de su recta: ≤`RETRACT_INK_MAX_PT` se queda en ese extremo (el último guión
    que entra en el margen de la caja), más no es llegada (la corrida quedaba al revés y un paso posterior la
    pegaba hacia atrás al nodo: zigzags hasta las esquinas de la caja, DU10 h.3/4, DU08 h.35–39); (D) recta
    TODA dentro de la caja, que CABE en ella (largo ≤ lado menor) y sin llegada por un borde →
    `Run.absorbed` al final de la Fase B (no sale: `assemble` la salta), aunque a su capa no le llegue nada:
    el núcleo corre POR CAPA y la línea que atraviesa puede ser de otra (LABOE h.26 alcantarillado), y las
    bóvedas solapadas se procesan una a una; si toca la línea que atraviesa, su tinta marca el NODO (la «T» de
    LABOE h.26/29/30 drenaje). Paso aparte `recognition_vault_through.py` (PURO): línea que ATRAVIESA su
    bóveda sin nodo (trazo curvo que la cruza recto: Fase A solo parte rectas) → vértice «vault» en el pie
    del centro sobre su parte recta dibujada, sin mover nada; no en bóvedas solapadas con otra que ya tiene
    nodo (DU08 h.36). Auditoría nueva `scripts/audit_sin_tinta.py salida.json` + `--diff` (6 utilidades × 4
    PDFs, ~10 min): hueco CONTINUO sin tinta de lo que se dibuja (rectas entre tangencias + arcos de los
    codos; `audit_perfil` salta los tramos hasta un codo y mira la mitad: no veía estos casos) y
    «retrocesos» (dos rutas que salen del mismo vértice suelto una encima de la otra = vuelta en U). Para
    revisar cada hoja que cambia: reconocer con el código viejo y el nuevo y dibujar ambos sobre el PDF con
    la tinta de la utilidad encima (no basta con los contadores). Foto 6 utilidades × 4 PDFs: huecos sin tinta
    eléctrico 32 → 24 y telecom 24 → 22 (0 nuevos en ninguna utilidad), vueltas en U eléctrico 9 → 1 y telecom
    3 → 2; `audit_perfil` «sin tinta» eléctrico 16 → 8, drenaje 1 → 0, imprecisos telecom 15 → 13; rutas 5451 →
    5384 (cortes en nodo 88 → 85, 0 cortes); codos distintos en 13 hojas (el mismo arco rehecho sobre la tinta
    o curvas que ya no terminan en un tramo inventado). 45 hoja×utilidad cambian, todas revisadas a la vista.
    Pendiente conocido: curva que se funde TANGENTE con otra línea junto a una bóveda y vuelve ~6 pt sobre ella
    (DU08 h.37 (1116, 991), h.38 (765, 1179) telecom; ya estaba).
    Tests: `tests/test_bovedas_no_inventar.py`.
  - **Curva con el RÓTULO dentro** (reporte del usuario 2026-10-19, hoja compuesta DU06 UD-201, «—SC—»):
    la línea gira con un arco y las letras del linetype van DENTRO de él; AutoCAD dibuja el guión recto hasta
    el inicio del arco + 2–3 cuerdas del aplanado (~2 pt) y el resto es el rótulo. `recognition_arc_letters.py`
    (PURO): `arc_tips` (punta curva = guión ≥8 pt + cuerdas cortas que giran al mismo lado), `arc_between`
    (dos puntas que curvan hacia el mismo arco, rectas que llegan a la esquina con el mismo largo ±20 %+1 pt,
    círculo TANGENTE a las dos rectas por las cuerdas curvas —RMS ≤0.15 pt—, tangencias donde termina cada
    recta ≤1 pt y letras centradas sobre el arco que, con la tinta curva, tapan ≥85 % de él). Lo usan (1)
    `recognition_letter_lines._link_arc_letters` (reparto por letras: une los dos guiones y las letras del arco;
    sin esto el guión de después quedaba sin utilidad en `G-XREF`) y (2) `letter_arcs`, en `_emit` después de
    `fit_fillets` (cajas = `GeomResult.glyphs`): pone el codo (`fillets[i]["letters"]=True`) donde no hay ya
    uno, quitando solo vértices blandos dentro del triángulo A–C–B. En la misma caja: una punta que SALE de la
    caja (la otra punta de su recta está DENTRO, bóveda detrás) y sigue por su letra no es la llegada (Fase B,
    `recognition_geom`): llega la punta de dentro (antes la línea quedaba cortada en su «SC» junto a la caja); y
    la 2.ª pasada de codos, sin ninguna opción de un lado, usa la recta de la polilínea hasta su «stop»
    (`arc_plan._vault_leg`: su tinta es el trazo hasta el centro de la caja, que no se le reparte). Foto 4 PDFs ×
    6 utilidades (846 hoja×utilidad): cambian 9, todas telecom y revisadas a la vista — DU06 h.3 (el reporte),
    la «—SC—» que quedaba en dos trozos junto a una caja (DU08 h.23/24/47, DU10 h.13/14/23/24) y DU08 h.40 (curva
    muy abierta junto a una caja: quiebre de 2° → arco r = 1130 pt, tinta→dibujo máx 0.30 → 0.24 pt). LABOE 0.
    Tests: `tests/test_arco_con_letras.py`.
  - **Vista previa = importación en los quiebres** (mismo reporte, DU06 UD-202): `recognition_quiebres.
    curvas_de_quiebres(results, zoom)` repite sobre COPIAS los pasos de datos de `Main._import_recognized_pipes`
    (tuberías, vértices de bóveda, acometidas, estructuras, cajas, codos, `quiebres_curvas.curvas_en_quiebres`) y
    la vista previa (`_curvas_quiebres`, zoom = `fondo["zoom"]`; se recalcula al unir/separar tramos) dibuja esos
    quiebres como la curva de radio mínimo que entrará (no presión). OJO: un paso NUEVO de la importación que
    cambie qué quiebres son curva va también ahí. Tests: `tests/test_recognition_quiebres.py`.
  - **Hojas SIN capas (PDF aplanado / mapa SIG; 2026-10-10, Quarter Section de Phoenix, una utilidad
    por PDF, `docs/flattened-pdf-recognition.md`)**: `hoja/pdf_styles.py` da a cada trazo sin OCG de una hoja
    sin geometría OCG una capa VIRTUAL `PDF_STYLE:[json]` (color, grosor, guiones, relleno, opacidad;
    `style_label` = «Negro 0.73 pt · continuo»); `pdf_styles.drawings(page)` reemplaza a `get_drawings` en
    `gather_paths`, `page_layers`, `trazos_visibles`… (en hojas CON OCG devuelve lo mismo). «Capas de la hoja»:
    `layer_assignments.LayerAssignmentsMixin` (utilidad + rol por capa → `roles_by_utility`, 5.º valor de
    `choose_sheet_layers(include_roles=True)`); en hoja sin capas solo se reconocen las utilidades con estilo
    asignado (`RecogCardMixin._flat_sheet`; sin ninguno, «Continuar» apagado). Escala: `layer_dialog_scale`
    (botón «Escala» del pie, calibrar con dos clics o escribir; 6.º valor → `Main._calibrated_scale` →
    `_scale_override` + `src_scale` de la pieza) y `_apply_composite` usa la escala del compositor de UNA
    hoja si el usuario la corrigió. Reconocimiento (solo capas por estilo): `recognition_ink_lines` — capa
    de trazos CONTINUOS (`continuous_layer`: casi ninguna punta con otra enfrente a un hueco de guion y ≥60 %
    de tinta en trazos ≥25 pt) → la tinta es el eje (`ink_reconstruct`, Douglas–Peucker 0.5 pt contra el
    zigzag SIG); a guiones (CAD aplanado, DU08 h.4–19) → núcleo; `recognition_style_nodes` (solo GRAVEDAD):
    extremo compartido por ≥2 trazos ≥10 pt = buzón → vértice «vault» (insertado si la línea pasa de largo).
    Sin regla «//» en capas por estilo; `xdata.parse_layer` guarda «Estilo …». Rendimiento: `px()` de
    `recognize_page` con la matriz de giro guardada + caché y `_through_dirs` con cajas (mismo resultado;
    Phoenix 13 s → 1–4 s). Foto 15 hojas × 6 utilidades (DU06/DU08/DU10/LABOE) = 0 diferencias. Tests:
    `tests/test_pdf_styles.py`, `tests/test_mapas_sin_capas.py` (Phoenix 17-10 ventana → DXF: 69 líneas, 102
    buzones). OJO al dibujar revisiones sobre estas hojas: tienen `/Rotate 90` → `pts_pdf` (px de la vista) por
    `page.derotation_matrix` antes de dibujar en la página.
    **Leyenda del plano y todo lo que dice el mapa (2026-10-13/14, SOLO hojas sin OCG con texto Type3 sin
    ToUnicode: `leyenda_mapa.aplica`)**: `hoja/texto_pdf.py` lee el texto por la FORMA de cada glifo (charprocs
    dibujados y comparados con Arial, coseno ≥0.9; cada glifo RECORTADO a su celda: una flecha grande se metía en
    la celda del «4»/«6»); los glifos sin letra son SÍMBOLOS (`simbolos`). La fuente fina de trazos de Phoenix
    alcantarillado (calles, subdivisiones) no se lee: es mapa base. `hoja/leyenda_mapa_lectura.py` arma el cuadro
    (columnas a paso regular partidas donde salta el paso, muestra entre el texto de la columna de la izquierda
    QUE ESTÁ A SU ALTURA y la descripción, símbolo centrado en su fila ±0.35 paso, notas «taps are .75"» /
    «main material is ACP») y `hoja/leyenda_mapa.py` da el significado (sección/utilidad, rol LINEA/ESTRUCTURA/
    ACCESORIO/ANOTACION/BASE/ACOMETIDA) y `asignaciones` (voto por estilo/símbolo; lo que la leyenda usa también
    para lotes queda ambiguo). `hoja/acometidas_mapa.py`: acometidas = trazos del estilo de una fila «Tap» que
    NACEN sobre la tinta de la red (≤0.35 pt) en un BLOQUE del orden de dibujo (`seqno`, huecos ≤20 trazos) donde
    ≥50 % nace sobre ella (el SIG dibuja cada capa seguida: los linderos del mismo estilo quedan en otros bloques);
    `pdf_styles.drawings` las pone en la capa virtual `["tap", utilidad, estilo]` («Acometidas · Negro 0.19 pt»),
    asignada como líneas en TODAS las utilidades (2026-10-14; antes solo presión): en gravedad/conductos el import
    (`nucleo/acometidas.unir_a_principal`) pone la punta «tee» como vértice `acometida` de su tubería (no si cae a
    ≤ `_TOL` de otro vértice: movería el buzón) y `hide_soft_vertex_structures` deja NULOS los nodos de la
    acometida (`pipe["acometida"]`); `recognition_style_nodes` no mira las capas de acometidas. QS Sewer South h.4:
    40 tuberías + 390 acometidas, buzones visibles iguales. Tests: `tests/test_acometidas_gravedad.py`. Reconocimiento:
    `recognition_ink_lines.simplify_tol` = medio grosor del trazo (0.15–0.5; el grosor sale del NOMBRE de la capa
    —`pdf_styles.style_width`—: `geom.clip_path` no conserva `width`), así el eje no sale de la línea;
    `recognition_map_vaults` (buzón-símbolo con punta/vértice dentro o atravesado → vértice «vault», deja de ser
    huérfano), `recognition_taps` (punta de la acometida al pie sobre la tubería, «tee»; las acometidas no se unen
    en rutas), `recognition_diametros` («8"», «12" DIP», «278' 2"» paralelos y pegados → `diam_in` por mayoría
    ≥60 %; mezcla → `review="diam_mix"`). `RecognizedPolyline.diam_in` → `pipe["diam"]`. Foto 16 hojas Phoenix
    (HEAD → nuevo): agua mismas tuberías + acometidas (South h.4: 151 + 404, 0 a >1 pt de la tinta al importar);
    Water North h.1/4/10 de 0 líneas a 145/143/106 (la leyenda ya se lee); alcantarillado mismas líneas, buzones
    sin línea 33→4, 37→4. Tests: `tests/test_mapas_leyenda.py`.
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
    Tests: `tests/test_recognition_letters.py`. **Capa de DOS utilidades** (reporte 2026-10-07, DU06 h.5:
    `G-XREF` con las «—T—» de telecom y un tramo «—W—» de agua con UNA «W» que no se leía —la línea
    gira 1.4 pt después de la letra— y el agua no lo reconocía): `dash_ends` acepta una punta de guión
    corta (≥`DASH_STUB_MIN_PT`=1) si el tramo siguiente del trazo ya es guión; un código en un solo
    sitio (ruido, `MIN_SITES_CODE`) vale si la MISMA hoja lo usa en ≥2 sitios de otra capa
    (`confirm_across`, al final de `page_letters`; `LayerLetters.noisy`/`confirm`); `dedicated` nunca
    con dos utilidades (todo línea por línea). Foto de letras 141 hojas: solo 7 capas cambian, todas
    tramos de agua de capas genéricas que ahora son agua (DU06 h.4 `PROP_WATER_PIPE_ALGN|P-INST`, h.5,
    h.12, h.14 y DU08 h.36/37 `G-XREF`; `U-Rearr-Tel` de h.4 pasa a capa entera con los mismos 23
    trazos). El árbol pone la capa en el grupo de CADA utilidad (`pdf_layers.layer_groups`, con su
    código y un icono de enlace; `_items_by_name` + `_sync_twins`: las dos filas van juntas, la capa
    cuenta una vez en `hidden_names`/«Visibles»).
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
    «Siguiente» y quedaba vacía): al abrir sin piezas, la hoja a la vista entra sola, MARCADA
    (`_choose_provisional`; `_provisional` = `to_dict()` de esa pieza, solo para el texto «ya
    viene marcada»: `_provisional_now()`; nada la reemplaza sola). **Una CASILLA por hoja**
    (`page_gallery.PageGallery`, pedido 2026-10-19: «así nos evitamos problemas y confusiones»):
    marcadas = la hoja compuesta (`USED_ROLE`, la pone `_label_page_item`; `_CheckDelegate` la
    dibuja abajo a la derecha, 22 px, colores del tema). Casilla / Espacio / Enter / Ctrl+clic →
    `toggled` → `_toggle_page`: marcar = `_use_page` (la deja a la vista y `_pick_page`: entera,
    en edición, SUMADA —nunca reemplaza, pedido 2026-10-16: «selecciono la 1, luego la 2, y la 2
    sustituye a la 1»—; vacía → `_choose_page`); desmarcar = `_remove_page(fila)` (pregunta si
    tenía un área tomada: `_confirm_remove_page`). El doble clic en la casilla cuenta una vez.
    Clic en la miniatura (`picked` → `_view_page`), flechas y ‹ › (`gesture`) solo MUESTRAN; si
    la hoja ya está, su pieza queda en edición (`_select_page_piece`, desde `_on_page_changed`);
    si no, aviso `pending_box` («Usar solo esta hoja» con una pieza: `_use_only_this_sheet`).
    «Tomar área de esta hoja» y el enlace «Usar la hoja N» = `_pick_page`. La pieza de la hoja a la vista queda
    EN EDICIÓN: un área marcada (o sus esquinas movidas) la recorta al momento con el
    `_apply_crop_edit` de siempre y «Hoja completa» la devuelve (`_set_piece_area`;
    `_take`/`_take_area` sobre la pieza en edición de la hoja a la vista = actualizarla, no
    agregar). La hoja entera se ve SIN tinte (borde + asas: `_CropView.is_whole_page`/
    `_fill_for`). Esc no cierra el diálogo (`wizard_widgets.NoEscapeClose`). Tests:
    `tests/test_composite_dialog.py::test_la_hoja_elegida_es_la_hoja_compuesta`,
    `test_casillas_de_las_hojas` y siguientes.
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
    arrastrar y las resalta. Nitidez (teselas, ver arriba): `pdf_view_quality.ViewportSharpener` (panel 2)
    y `PieceItem.superficie` (todas las piezas a la vista; antes presupuesto de píxeles
    repartido) re-renderizan solo la región visible como overlay, a la resolución de la
    pantalla (`recorte_nitido`, ver `fondo_pdf`). **Colocación EXACTA** (reporte
    2026-10-09, escaneos: «al hacer zoom como que se mueve»): MuPDF redondea el recorte hacia afuera
    (el pixmap empieza en `floor(x0·escala)` = `pix.x`), así que la imagen base NO se estira a la caja: va
    sin girar y `PieceItem._raw_transform` (≡ `piece_map`, con el origen `pix.x/pix.y`) pone giro, escala y
    desfase; el recorte nítido es hijo con solo escala + origen, y ambos se recortan al clip exacto en
    `paint`. Antes la base quedaba corrida hasta 1 px de la vista general (1–2 pt) y la pieza saltaba al
    aparecer el recorte. `scene_box()` = caja de la pieza (contorno, clic y nitidez; `sceneBoundingRect`
    es mayor con giro). Tests: `tests/test_piezas_exactas.py`. `recognition.
    gather_paths` descarta astillas <1.5 pt creadas por un clip (`CLIP_SLIVER_PT`):
    con eso DU06 hoja 4 partida en dos con hueco = 13 rutas, igual que entera.
    OJO: `theme.apply_theme` PERSISTE la preferencia en QSettings; en scripts de
    captura offscreen usar paleta+stylesheet a mano, nunca `apply_theme`. `build_document` materializa la hoja
    como PDF real de UNA página: `show_pdf_page` por pieza (vectores, textos y
    capas intactos; OJO: ignora el `/Rotate` de la hoja origen → clip des-rotado y
    `rotate=piece.rotation - page.rotation`; y PyMuPDF 1.28 recorta ese clip SIN rotar con el
    rect de la hoja GIRADA —en /Rotate 90/270, ancho y alto cambiados: la pieza salía cortada y
    centrada en su lugar, franja blanca en la unión (reporte 2026-10-15, drenaje de Phoenix; las 36
    piezas de alcantarillado perdían 3–6 % y se corrían ~50 pt)—, por eso va por `_show_pdf_page`, que
    quita el /Rotate de la hoja de origen durante la llamada; test
    `test_hoja_girada_cada_trazo_donde_lo_pone_el_compositor`) y reconstruye `/OCProperties` con los
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
  - **Composición sugerida** (pedido del usuario 2026-10-14: «revisar TODAS las hojas y sugerir cómo se unen»;
    escaneos excluidos, `comp.manual` no la lanza). Núcleo PURO en `app/hoja/`: `composicion_ficha.py` (por hoja:
    rótulos «MATCH LINE STA … SEE DWG …» con su lado de la VISTA = clip del viewport, número de hoja + serie
    «UR-#A», celda de cuadrícula «17-10»/«Q17-10» + mapa índice 3×3 — una celda solo vale con mapa índice o
    prefijo Q: un «380-4» de portada no—, trazos de las franjas de los bordes; el dibujo solo se lee si el texto
    dice algo; Type3 por `texto_pdf`), `composicion_encaje.py` (B = escala·A + t, hoja VISIBLE: `costura_cad` =
    match lines que coinciden + vectores idénticos o continuidad, la MISMA costura exacta de `composite_seam`,
    con ventanas 30→600 pt alrededor de la pista de los rótulos y el hallazgo tiene que ser además el pico
    GLOBAL de votos crudos — con ventana amplia cada voto se reparte y LABOE sin capas perdía uniones—;
    `encaje_mapa` = trazos idénticos en la franja de solape, escala si los PDF difieren, pico dominante, ≥2
    rumbos, vecina del lado del mapa índice; plantilla = trazos en la misma posición en ≥50 % de las hojas),
    `composicion_sugerida.py` (parejas por el texto ±60 ft de estación —erratas reales de 50 ft— o celdas
    vecinas en la dirección del mapa índice / convención aprendida; primero dentro de la serie; mapas sin pico
    claro → GUIADAS por la traslación mediana de las ya confirmadas, con dominio 1.5 y RMS ≤0.3; grupos con
    control de CICLOS (≤1 pt, si no se parten); `armar` → `Composite` normal: CAD recortada EN su match line +
    `trim_border` (franjas) y puentes; mapa sin puentes, costuras (`composicion_costuras.py`) por el solape de TINTA (`tinta`: la vista de
    alcantarillado es ~25 pt más ancha que el mapa) en la posición que menos tinta de una sola hoja pierde y
    menos tramos rasantes toca (`_costo_corte`: cada hoja dibuja su red entera y solo parte de la vecina),
    recta común por fila/columna si cabe) y `composicion_hermanos.py` (PDF de la carpeta con la misma utilidad
    en el nombre y las celdas que faltan). UI `ui/asistente/composite_suggest.py` (`SuggestionMixin` + `Servicio`
    en un QThread de baja prioridad, caché por sha1 de cada PDF): tarjeta bajo las pestañas (progreso → «Composición
    sugerida: 14 hojas (UD-201 → UD-214) · STA …» → «Usar sugerencia» / «Deshacer»; la hoja abierta o elegida en
    Origen decide el grupo y la serie, si no está en ninguno y hay varios, combo; PDF hermano → «Agregar PDF» y
    se vuelve a analizar). `PDFCAD_SUGERENCIA=0` la apaga (conftest). Reconocimiento: en `recognition_ink_lines`
    la punta «cut» donde llega la de OTRA pieza (otro `clip_polys`) es «junction» (una tubería de un mapa
    compuesto sigue en la costura; hojas sueltas: 0 diferencias en 8 hojas de Phoenix). Auditoría
    `scripts/audit_composicion.py [--fotos] [--reconocer] [du06 du10 du08 laboe agua cloaca sd]`: CAD contra la
    verdad independiente de `audit_costuras` (DU06 13/13, DU10 24/24, DU08, LABOE: todas ≤0.19 pt), mapas RMS +
    ciclos (agua 0.26 pt, alcantarillado 0.65 pt, 36 hojas en 2 PDF cada uno; SD queda en tramos: líneas a
    guiones repetidas). Tests: `tests/test_composicion_sugerida.py`.
  - **Trabajo pesado CONTROLADO** (pedido del usuario 2026-10-14: «no detener todo el sistema», RAM, avance «como
    un lápiz»). `ui/comun/proceso.py` + `proceso_hijo.py` (sin Qt): `Trabajador` = proceso hijo «spawn» reusado
    («principal»: reconocer/armar; «fondo»: composición sugerida), prioridad BELOW_NORMAL, tope de memoria por Job
    Object (`TOPE_FRACCION` 0.7 de la RAM; si no cabe → error «memoria» con aviso), reciclado si tras un trabajo
    queda > `RECICLAR_MB`; `Tarea(objetivo «mod:fn», args, kwargs)` con `avance`/`terminado`, `cancelar()` = matar.
    `ejecutar(...)` espera con un QEventLoop local (la capa «Cargando…» come la entrada). Trabajos PUROS:
    `reconocimiento/recognition_trabajo.reconocer_hoja` (lo de `RecognitionWorker.run`, que sigue igual para las
    pruebas; `start()` va al proceso; señales nuevas `layer` «capa k de m» —`recognize_page(avance=)`— y `partial`
    con los trazos de cada utilidad terminada, que `Main._recognition_partial` dibuja bajo un velo más claro),
    `hoja/composite_trabajo.materializar` (`_build_composite_doc`) y `hoja/composicion_trabajo.analizar` (caché de
    fichas EN el trabajador; vuelve sin `Ficha.lineas`). `BusyOverlay.begin(cancel=)` pinta «Cancelar»;
    `set_veil`. `main.py`: `freeze_support()` y la interfaz se importa solo bajo `__main__` (el hijo importa main
    como `__mp_main__`); `OPENBLAS_NUM_THREADS=1` antes de numpy (+361 → +8 MB por proceso; letras igual de
    rápidas). `PDFCAD_PROCESO=0` = todo aquí mismo (conftest; `tests/test_proceso.py` lo enciende).
    Velocidad sin cambiar resultados (`reconocimiento/recognition_indice.py`: `IndiceTramos` por corredor y
    `IndicePuntos`, candidatos en el ORDEN original → mismo desempate): `strokes_by_polyline`, `_through_dirs`,
    `ink_reconstruct` (puntas), `recognition_diametros.asignar`, `snap_taps`, `acometidas_mapa` (celdas) y
    `leyenda_mapa_lectura` (una leyenda POR HOJA en una compuesta: `_grupos` de encabezados a ≤ `GRUPO_HS`=100×
    su tamaño, `_Pagina` con filtros exactos, filas de todas sin repetir y una zona por leyenda; `_rotulos` por
    celdas). Antes las leyendas de una compuesta se juntaban en UNA caja que tapaba parte del mapa (4 hojas de agua:
    282 → 389 tuberías + acometidas). Phoenix agua 36 hojas con estilos asignados: 668 s → 79 s. Foto antes/después
    (7 casos: agua S/N, alcantarillado, DU06 eléctrico/drenaje/telecom): idénticos salvo las acometidas nuevas.
    **2.ª vuelta (mismo día)**: `nucleo/avance.py` = avisos de ETAPA desde el código puro (`avisar(texto, i, n)`,
    por hilo, espaciados `CADA_S`); los escuchan `busy()` (todo `with busy(...)` muestra la etapa en el detalle,
    `busy.escuchar_en(ov)`, `detalle_de`), el trabajador (`proceso_hijo.bucle` → («detalle», t, i, n) por la cola) y
    `RecognitionWorker.stage` (2.ª línea del detalle). Avisan: `pdf_styles.drawings`, `texto_pdf.glifos`,
    `leyenda_mapa_lectura._leer` (leyenda k de n), `pdf_layers.page_layers`, `leyenda_trazos.trazos_visibles`,
    `composite.build_document`/`compute_bridges`, `composite_trabajo`, `fondo_pdf.render_pix`, `recognize_page`
    (trazos, capa con su nombre, bóvedas) y `CompositeView.rebuild`. PARALELO (mismo resultado, verificado):
    `proceso_hijo.paralelos(n, mb)` (mitad de los núcleos, RAM libre, ≤ `MAX_PARALELOS`=4) → `RecognitionWorker.start`
    reparte una utilidad por trabajador («principal», «principal-1»…; DU06 h.4 6 utilidades 17 → 10 s) y
    `composicion_trabajo._fichas_en_paralelo` (ProcessPoolExecutor dentro del trabajador «fondo», encargos de 3
    hojas; 36 mapas 33 → 12 s). Exactos: `pdf_styles.style_name`/`style_label` memorizados (1.5 M `json.dumps`),
    `_Pagina.dibujos` con numpy, `IndiceTramos` por caja en tramos cortos, `trazos_visibles` con el `_rect_poly` de
    cada recorte una vez, y `pdf_styles.drawings` deja a `_dibujos` los trazos ya leídos (`_pdfcad_dibujos`). Una
    lectura `get_drawings` de 36 mapas = 1 GB que no vuelve al soltarla. «Capas de la hoja» 36 mapas: 62+55 s →
    31+37 s. UI: `StepBar` paso hecho = botón `soft` con ✓ (subrayado no se leía en oscuro); `MiniMap` esquema
    crece con la vista (`LAYOUT_*_FRAC`), `set_layout(items (rect, etiqueta[, detalle]), sync_zoom=)`, etiquetas en
    2.ª pasada en lo VISIBLE de cada caja con letra que cabe, hoja del centro resaltada, tooltip;
    `widgets.etiquetas_cortas` («17-10», «North 3»); «Capas de la hoja» con `sync_zoom` y `Main._layout_minimapa`
    (la etiqueta de la pieza, solo para mostrar: `_composite_layout` sigue siendo el dato de xdata).
    **3.ª vuelta (mismo día, reporte: 36 mapas de alcantarillado → 0 tuberías, 2042 «bóvedas sin línea»)**: la
    leyenda de una compuesta se lee POR PIEZA — `leyenda_mapa_lectura.inicios_de_piezas` (contenido `/fzFrm…` ≥2:
    `get_cdrawings(extended=True)`, el `seqno` del primer trazo tras cada recorte de nivel 0) y `Glifo.seqno`
    (`texto_pdf`, del `get_texttrace`): cada grupo de encabezados usa solo textos/símbolos/trazos de SU pieza (la
    vecina dibuja el mapa encima de la leyenda tapada) — y `LeyendaMapa.por_hoja` → `leyenda_mapa.asignaciones`
    decide cada hoja como suelta (`_asignaciones`) y gana la MAYORÍA de las hojas que nombran el estilo
    (`MAYORIA_HOJAS`; juntando filas sin repetir, «Standard Main» votaba una vez y dos muestras sueltas lo dejaban
    ambiguo). Alcantarillado 12/36 hojas: «Negro 0.73» asignado (North 0.73, South 0.39 × 1.89); agua igual.
    Hojas sueltas: mismas filas/zonas/acometidas. Bóvedas × líneas con índices (`IndiceCajas`, `IndicePuntos.
    en_caja`, `lineas_cerca`): `recognition_map_vaults.mark_symbol_vaults`, `recognition_vault_through.
    mark_through_vaults`, `recognition_vault_snap.snap_ends_to_vaults` (insertar un vértice no cambia el dibujo:
    el índice inicial vale; candidatos en orden) — alcantarillado 12 hojas 335 → 47 s, idéntico. UI:
    `ui/ventana/ventana_hojas.py` (`HojasEditorMixin`): minimapa del editor (más chico) y marcas de agua
    (`marcas_de_agua`, Z = `Z_PDF`+0.5, sin ratón, en `_overlay` desde `_redraw` → `_dibujar_hojas`; Ver →
    `act_minimapa_hojas`/`act_marcas_hojas`, QSettings), `_layout_minimapa` (se movió aquí; reabierto: lo calcula
    de los PDF de origen) y `_hojas_px`; la vista previa recibe `hojas=` y pone su `MiniMap`. Avance con cifras en
    `trazos_visibles` y en el nombrado de estilos.
    **4.ª vuelta (2026-10-19, Water North + South, 10 mapas: «hoja por hoja funciona, compuesta no»; continuidad
    y precisión)**: (1) ROLES POR HOJA: `Main._layer_roles_by_utility` sobrevivía de una hoja suelta a la compuesta
    y `_apply_map_legend` NO aplicaba la leyenda si había roles → solo las piezas con los mismos grosores quedaban
    como agua. Ahora `roles_by_utility()` lleva `leyenda_mapa.CLAVE_LEYENDA` (lo que asignó la leyenda de ESA
    hoja); `Main._layer_roles_hoja` = `_clave_hoja` (PDF de origen + composición + nº de hoja) donde se eligieron;
    en otra hoja `_roles_de_la_hoja` → `roles_de_otra_hoja` (quita lo de la leyenda, deja lo puesto a mano con
    `SUMAR_LEYENDA`) y el diálogo / `recognize_page` suman la leyenda de esta hoja (`roles_con_leyenda`). Misma
    hoja (volver de la vista previa) = roles tal cual. ◀ ▶ en «Capas» → `_legend_for_new_sheet`. CAD (capas con
    nombre, sin `CLAVE_LEYENDA`): igual que siempre. (2) `leyenda_mapa_lectura._divisores`: una línea del MAPA
    dibujada antes del fondo opaco del cuadro y tapada por él no es divisoria (`_tapado`): Water South h.15/North
    h.13/15/18/South h.11 tenían «Standard Main» en «GENERAL» sin utilidad → 0 tuberías en la hoja suelta (foto
    108 hojas: solo esas 5 cambian). (3) `hoja/leyenda_piezas.py` (PURO): `equivalencias(ley)` (unión de
    conjuntos sobre (pieza, estilo) de filas de LÍNEA con utilidad, `LeyendaMapa.piezas` = pieza de cada
    `por_hoja`) → `recognize_page` agrupa en `by_ocg` el estilo de una pieza con el común si los dos son líneas de
    la utilidad (17-24/25 dibujan a 0.57 pt lo que las demás a 0.71; con la escala de cada pieza: 0.30/0.37/0.38
    en tres capas que se cortaban en cada costura). `gather_paths` conserva `seqno` en el recorte (pieza por
    `inicios_de_piezas`). (4) `recognition_ink_lines` en hoja compuesta (más de un recorte; hoja suelta igual):
    `_sin_dobles` (trocito todo a ≤0.3 pt de la línea de otra pieza), `_soldar_costuras` (punta «cut» y la de
    la misma tubería en la pieza vecina a ≤`COSTURA_HUECO_PT`=2.5 que se miran: adelante → la cortada se
    alarga hasta ella; las dos cortadas una al lado de la otra → punto medio; si no, el rayo de la cortada
    hasta la LÍNEA de la otra pieza cruzándola ≥30° → T), una punta «cut» donde termina otra línea de la misma
    capa = «junction» (tubería pegada a la costura: cada vértice sale como corte) y una «cut» sobre la línea de la
    otra pieza = «tee». Aviso «Costuras de la hoja compuesta: N». (5) `merge_walls` no corre en capas por estilo
    de trazo CONTINUO (mapa SIG: dos paralelas son dos tuberías; en North h.15 dos laterales a 2.7 pt quedaban en
    una línea al medio sin tinta; en la compuesta, 125 pt inventados). (6) `recognition_ends.trim_inkless_tails`:
    el índice de la punta final se toma después de recortar la inicial (IndexError latente). Medido en la
    compuesta de 10 mapas: capas de la red 3 → 1, puntas «cut» 203 → 99 (las 95 restantes: la otra hoja no
    dibuja esa tubería), muestras a >1 pt de la tinta 0.65 % → 0.02 %. Tests: `tests/test_mapas_compuestos.py`.
    Pruebas por grupos en paralelo: `python scripts/pruebas.py <grupo…>` (mapas, compositor, capas,
    reconocimiento, utilidades, editor, interfaz, otros, todo; sin pytest-xdist).
  - **Esquinas libres en TODOS los flujos** (pedido del usuario 2026-10-19): casilla
    `chk_corners` «Esquinas libres» en «Área a tomar» (encendida en escaneos, apagada en vectorial;
    se enciende sola al editar una pieza con `polygon`). `scan_crop_view.CornerCropView(free=)` —
    apagada es el `_CropView` de siempre; encendida: esquinas, lados paralelos, centro, flechas e imán
    de esquina a las guías—. `normalized_polygon()` = [] si el cuadrilátero es un rectángulo (todo como
    antes: `clip`, «Sin línea de borde»); si no, `Piece.polygon` con `clip` = su caja y sin `covers`.
    Hoja compuesta: `build_document` ya recortaba por el polígono (`W n`, el reconocimiento lo ve como
    un clip más); anclajes por el lado inclinado (`hoja/composite_esquinas.edge_anchors_poly`, vía
    `edge_anchors(polygon=)`), puentes hasta el cuadrilátero (`piece_bounds_shape`, `_ray_exit` con
    polígono) y el imán borde con borde / costura por match line se saltan las piezas con polígono.
    Tests: `tests/test_esquinas_libres.py`.
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
    pieza no tapa la tinta de otra y la superposición no oscurece el papel. Tests:
    `tests/test_scan_composition.py`, `tests/test_scan_tools.py`. **También en el VECTORIAL** (con
    y sin capas, pedido del usuario 2026-10-19; `hoja/composite_fundir.py`, PURO): mismo botón
    (`ScanToolsMixin.build_blend_tool`, solo a la izquierda de la barra) y `Composite.blends()` =
    `seam_blend` en todos los flujos. En el PDF, `blended_pieces`: escaneo = todas (como siempre);
    vectorial = solo las que se SUPERPONEN a una anterior > `SOLAPE_MIN_PT`=1 pt (borde con borde
    el PDF sale idéntico: mismos bytes de contenido) y van como GRUPO de transparencia AISLADO
    (`/Group <</S/Transparency/I true>>` en su «fzFrm», `aislar_ultima_pieza`): con el oscurecer
    directo cada trazo se oscurecía dentro de SU hoja (el fondo blanco de un rótulo dejaba ver la
    línea) y MuPDF abría un grupo por objeto. Las franjas `covers` van fuera del modo y siguen
    tapando. OJO lectores: el grupo queda en el NIVEL 0 de `get_drawings(extended=True)` y el
    recorte de la pieza en el 1; `recognition._cerrar_recortes` (gather_paths, profile_view_regions,
    `leyenda_trazos.trazos_visibles`: un grupo cierra los recortes de su nivel, si no el de la pieza
    anterior recortaba a la fundida: −3 200 trazos en DU06 h.13) y `inicios_de_piezas` (grupo o
    recorte de nivel 0 = pieza nueva). Los PDF de prueba que ya traen grupos (DU06 h.5/10, DU10,
    LABOE) no cambian. Píxeles: dentro del grupo MuPDF suaviza bordes hasta 18/255 distinto (no se
    ve); dibujo ~2× en la pieza fundida. Tests: `tests/test_fundir_vectorial.py`.
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
    «t» de C-TELE-UNGD-E/-D, telecom al importar). **«Leyenda de esta hoja» POR UTILIDAD** (pedidos
    2026-10-07: DU06 sin leyenda; DU08 h.26 «ubicarlas e interpretarlas… para cada una de las
    utilidades»: con la leyenda del PDF aparte, «EXISTING ELECTRICAL» marcaba solo las «e» y las «E», «TE»,
    «SE» no se marcaban con nada), SIEMPRE (con o sin leyenda en el PDF): `leyenda_estandar.leyenda(layers,
    pdf_rows=)` (PURO) arma, con las capas de la hoja ya con `without_letters`, un `Grupo` por utilidad y
    una `Fila` por (rol, estado, código de letras, abreviatura) —«E», «TE», «SE» filas distintas—; roles
    LINE, STRUCTURE y OVERHEAD (aérea: token OVHD + `utility_of`; está en el filtro, NO se reconoce: fila
    «No se reconoce», el clic en la utilidad no la incluye). `codigos_capa`: códigos de la utilidad leídos,
    el más leído primero (`page_layers` → `read_counts`; si ninguno ≥2, los de `letter_raw`). Estado
    (`estado_capa`): letra de estado del nombre NCS sin la disciplina ni el paquete «__UA4»; si no,
    PROP/EXIST/ABND en el nombre o en el xref; si no, con leyenda del PDF lo que ésta dice de esas letras
    (`leyenda_cruce.estado_por_leyenda`: misma caja, todas las filas de acuerdo; «W» queda sin estado:
    DU08 usa «W» para existente y propuesta) y sin leyenda la caja (MAYÚSCULA = propuesta).
    `leyenda_cruce.py` (PURO) cruza cada fila con la leyenda del PDF: `estado_de_texto` (EXISTING E,
    PROPOSED/NEW N, «… ABANDONED» A, «TO BE ABAN…» D —errata «ABANONDED»—), `utilidad_de_fila` (código o
    palabras: «PROPOSED STORM DRAIN» no tiene letras), `emparejar` (utilidad, aérea, estado, mismo código o
    si no otro de la utilidad —«S» leída / «SS»—, misma caja si alguna); dos filas con la misma
    descripción se juntan (`_juntar_por_leyenda`). DU08 h.26: todas las líneas de las 6 utilidades con su
    descripción. Datos BOE (`Documentos/docs prueba/BOE_CADD_Manual_210610.pdf`): fig. 3.1.7.1-1/-2
    «Utility Linetypes» (`LINETYPES`: ELEC, HV ELEC, NGAS, PW, FPW, IRR, SSWR, SD, TEL, FO; `STRUCTURES`:
    ELECTRICAL VAULTS, SSMH, SDMH; propuesta ≤12" = línea continua) y §8.1.6 estados. `rol_capa`/
    `es_trazo_de` deciden qué capa —y en una capa mezclada qué trazo— es línea/estructura de cada
    utilidad IGUAL que `recognition.line_selectors`, y solo lo VISIBLE: `leyenda_trazos.trazos_visibles`
    (una pasada de `get_drawings(extended=True)`: mismos recortes y vistas de perfil que `gather_paths`,
    solo las capas de utilidad, atajo para clips rectangulares; 0.5–1.3 s) da (original, recortado): se
    decide con el original (`letter_paths` se leyó sobre él) y se dibuja lo recortado; la leyenda lista
    solo capas con algo visible (`LayerInfoPanel.visible_layers`). Capas con trazos que NO están en la
    lista del PDF (`layer_ui_configs`; DU06 h.2 `…(A2_TRIM)|V-ELEC-MANH`): por su nombre
    (`capa_sin_lista`), como el reconocimiento. Auditado: mismas capas en las 141 hojas × 6 utilidades.
    UI `layer_std_legend.py` (`StandardLegend` con CASILLAS —3.er pedido 2026-10-07: «activar más de una
    utilidad… ahorita no sé cuál está activa»—: la de la cabecera (`toggle_utility`) marca todo lo que se
    reconocerá —líneas y estructuras, no las aéreas— y queda a medias si solo hay algunas filas; la de cada
    fila, esas capas; clic = casilla. Lo marcado se SUMA a las tarjetas por letras y filas del PDF activas
    (`LayerInfoPanel._extra`, otro clic las quita) y va junto al diálogo (`focusRequested({"specs": …,
    "label": summary})` → `_union_sets`: cada trazo una vez, lo fuerte manda sobre lo fino, «Resaltado: A ·
    B · N capas»); en el panel lo activo lleva borde y fondo OPACO del color de su utilidad (`active_qss`:
    la tarjeta mezclada al 22 %, se lee en claro y oscuro; drenaje en gris en tema claro: `accent`); `LineSample` dibuja la muestra: a trazos/continua, letras leídas, «//» a demoler; la
    muestra del PDF reducida no deja leer las letras). Debajo, plegada, «Leyenda completa del PDF (N)»
    (`btn_all`): filas de esta hoja (`StandardLegend.matched`) en negrita y clicables → las capas de las
    filas que describen (`filas_de_pdf`). Sin utilidades, capas por letras ni leyenda, el panel se pliega
    solo. Tests: `tests/test_leyenda_estandar.py`, `tests/test_leyenda_cruce.py` (DU08 h.26).
    `pdf_legend` (sin Qt): hojas con LEGEND/LEYENDA ordenadas por filas «EXISTING/PROPOSED…» (máx. 3);
    fila = texto con una muestra HORIZONTAL (≤12 pt de alto, ≥60 pt de largo) contigua a su izquierda;
    solo columnas de ≥3 filas a PASO REGULAR (tolera filas sin leer: paso ×2/×3) con letras en ≥30 %:
    las etiquetas con flecha de LABOE h.8/h.9 y el cajetín no entran. DU08/DU10/LABOE: 34–37 filas;
    DU06: sin leyenda. Tests: `tests/test_layer_legend.py`.
    **«Reconocer» con sus capas ocultas no puede ser** (pedido 2026-10-07): tarjeta en
    `layer_dialog_recog.RecogCardMixin` (también `card`, `utility_qcolor`; `layer_dialog` los
    re-exporta): `leyenda_estandar.sin_capas_visibles` (utilidad marcada con TODAS sus capas de línea
    —o, sin líneas, de estructura; `capas_que_reconoce` = mismos roles que el reconocimiento—
    ocultas) → icono de aviso en su casilla, frase con «Mostrar sus capas» / «No reconocerla» y
    `btn_ok` apagado; se revisa en `_sync_recog_all` (tras cada cambio del árbol). Tooltip de cada
    fila de la leyenda con la muestra en GRANDE (`layer_std_legend.sample_pixmap`/`paint_sample`, 3×)
    y la del PDF (`pdf_sample`), como `<img>` data URI (`img_html`/`tooltip_html`; el tooltip de Qt 6
    los muestra); igual en las filas de la leyenda completa del PDF.
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
  - `traduccion/` = `i18n.py` + `i18n_core.py` + `i18n_en.py` + `i18n_en_changelog.py` — traducción
    ES → EN. La clave es el texto en español tal cual está en el código. UI:
    `from traduccion.i18n import t` (y `bind(widget, "setText", "Clave")` en widgets de vida
    larga: se re-traducen solos con `LANG_BUS`; `bind_item` para ítems de combo);
    lógica PURA (`duct_bank`, `recognition`, `civil_catalog`, `composite`):
    `from traduccion.i18n_core import t` (sin Qt). Reglas: plantillas `t("… {n}").format(n=…)`,
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
  - **Reporte 2026-10-15 (cuatro puntos)**: (1) `nucleo/vertice_curva.py` + `ui/ventana/ventana_vertices.py`
    (`VerticesMixin`): en CONDUCTOS (sin caja por vértice) la utilidad seleccionada muestra sus vértices interiores
    libres y el clic derecho del lienzo (`_menu_vertice` en `_canvas_context_menu`) ofrece «Convertir este vértice en
    curva» → marca CV `vertice=True`, radio automático (la misma de `attach_fillets`, que ahora también lleva
    `vertice`); `se_quita` (conductos con `vertice` o `quiebre`) → «Quitar la curva» la BORRA (antes «Volver a
    buzón/caja» dejaba una CAJA inventada). (2) `ui/comun/marcas_lienzo.Marca`: buzones, curvas, tangencias, asas y
    vértices miden R en px del plano pero no pasan de `TOPE_PX` de pantalla (de cerca tapaban los tramos cortos).
    (3) `model_ops.diametro` = el `diam` de la utilidad (el del DXF) con o sin familia; «por defecto» solo si no hay
    tamaño ni `diam_elegido` (lo ponen el panel y el reconocimiento que leyó el diámetro) y vale el precargado. Sin
    familia el panel lista `model.DIAMETROS_SIN_FAMILIA_IN` (dato `edicion_bloque.dato_diam` «diam:N»), también sin
    Civil 3D; `_prop_changed` ya no pisa el diámetro al editar otro campo; copiar/pegar, bloque y Excel llevan
    «diam:N»; sin familia el «+» (`btn_add_size`, también sin Civil 3D) pide un diámetro personalizado
    (`_agregar_diametro_sin_familia`: «diam:N» en su lugar de la lista, pedido 2026-10-17). (4)
    `nucleo/conexiones_verticales.actualizar_cotas`: `z_a/z_b` de cada conexión aprobada se releen de
    las tuberías (tramo más cercano, menor índice en un vértice) en `_draw_pipe_conflicts`, el DXF y la Vista 3D.
    Tests: `tests/test_vertices_diametros.py`.
  - **Ángulos en pasos de 0.25°** (pedidos del usuario 2026-10-15/16: a mano los quiebres chicos del pulso se
    volvían vértices con accesorios; «no puedo encontrar ángulos de 45.684°» en NINGUNA utilidad, uniones ni
    accesorios): `ui/ventana/ventana_trazo.py` (`TrazoMixin`; el anillo «Asistir/Libre/Finalizar/Cancelar» del
    2026-10-15 se QUITÓ el 16: siempre en el paso; Enter / doble clic / clic derecho terminan y otro Enter sale
    del modo, `_on_enter`). Rumbos (`nucleo/trazo_asistido.py`): cada tramo `cuantizar(rumbo, base)` a 0.25°
    desde `base` = rumbo del tramo anterior (el quiebre queda múltiplo) o, en el primero, el del tramo donde
    empieza (`_base_de_hit`: la unión) o 0°; múltiplos de 45° con vectores EXACTOS (`unitario`); `imanes`
    (seguir recto, ±45°/90° del anterior y, si la base está en la red de 0°, los ejes de la hoja) a ≤ `IMAN_PX`
    de pantalla; sin imán, hacia el imán a la tinta (`_snap`). Llegada EXACTA a un extremo/vértice de otra
    utilidad: `deslizar_inicio` corre el punto anterior por su recta (si no está unido a nada: `_trazo_fijos`; ≤
    `DESLIZ_PX`); sobre un tramo, `cruce_rayo`. Editar/mover: `arrastre_en_paso` (cruce de los rayos en el paso
    desde los dos vecinos; `_drag_snap` manda) + `_etiqueta_arrastre` (giro ✓/⚠ y largos). Línea elástica a
    trazos + «rumbo · giro ✓/⚠ · largo» (`_trazo_actualizar`, desde `_update_pipe_snap_hint`); `_redraw` →
    `_trazo_al_redibujar` la borra. VALIDACIÓN `nucleo/angulos.py` (ángulos RELATIVOS, no dependen del giro de la
    hoja ni de la georref): `quiebres` (deflexión en cada vértice interior) + `uniones` (punta sobre otra
    utilidad de la misma capa a ≤ `UNION_FT`, ángulo entre las dos; rejilla) fuera de múltiplo de 0.25° ±
    `TOL_DEG`=0.01 → `avisos` clase «angulo» que `_draw_accesorios` guarda en `_angulos_fuera` SIN mostrarlos
    (pedido del usuario 2026-10-16: «validarse pero no mostrarse»; no van a `_normas_avisos`: ni insignia, ni
    contador, ni Tabla de datos, ni 3D). `avisos_view.dibujar` agrupa con rejilla (mismo
    resultado; 5000 avisos ≈ 0.1 s). El reconocimiento del PDF NO se toca (lo hace un compañero). Presentación
    1.3.1: X03 con el tramo del medio a 45°, X14 (quiebre 45.684°) y X15 (unión 80.3°). **Mismo día**: clic en
    un vértice libre de eléctrico/telecom (`_pick` → `_vertice_bajo_clic`/`_elegir_vertice`, `_vertice_sel`) →
    `box_vertice` «Cambiar a curva» en el panel de la utilidad (`_sync_vertice_panel` desde `_update_ui`);
    etiquetas T1/T2 (`ui/comun/etiquetas_tramo.py`: alto = 0.45 × largo del tramo, al costado —arriba; en
    verticales, a la izquierda—, sin solaparse ni tapar vértices, `ubicar`; `EtiquetaTramo` no pasa de
    `TOPE_PX` en pantalla); `canvas._ZOOM_MAX` 80 → 400; Vista 3D SIN padre Qt (`Vista3DDialog(None)` +
    `_duenio`: transient parent = la principal): un QOpenGLWidget en una HIJA hacía que Qt recreara la ventana
    nativa de la principal (Hide → otra → Show; medido con `winId`), la principal la cierra en `closeEvent`.
    Tests: `tests/test_trazo_asistido.py`.
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
    **Vértices prácticamente rectos que estorban** (mismo reporte 2026-10-19, UD-205: el quiebre junto a
    la «SC» de abajo tenía dos `bend` de 0.75° a 1.3 ft): `_enderezar` quita los MENOS posibles
    (`RECTOS_MAX`=4 por lado) vértices blandos con giro ≤ `GIRO_MIN_DEG`, a ≤0.25 ft de la recta nueva,
    sin otra utilidad (`limpieza_tramos.compartido`), sin estructura visible ni curva, si con eso la curva
    entra y ninguna otra curva cambia de radio, se recorta o corre su arco >0.25 ft (`_curvas_quietas`)
    —es lo que hace `EnderezarQuiebres` del plugin—; usa `limpieza_tramos.quitar_vertice` y borra el
    buzón oculto del vértice quitado (gravedad). En gravedad un vértice propio a ≤ tol px del quiebre
    (antes: se saltaba sin aviso) ahora se intenta quitar igual. Los candidatos se siguen por coordenada
    (los índices se corren). Vista previa: `recognition_quiebres.curvas_de_quiebres` marca esos vértices
    `{QUITADO: True}` y `dibujo_de(pl, curvas)` da la polilínea sin ellos + sus codos (la usa
    `recognition_dialog`).
  - **Normativas de diseño EN TABLAS** (2026-10-09; reemplazan al motor de reglas `normativas*.py` y su ventana
    QtWebEngine, borrados: el .exe ya no lleva QtWebEngine). Formato = el Excel que hizo el ingeniero a mano:
    `normas_catalogo.py` (PURO) — `BASE` = su contenido (tipos por utilidad, `diametros` de agua/gas por tipo con
    nota, `accesorios` Y/T/Cruz/Codo/T-Domiciliaria —permitido/prohibido/solo_en, diámetro principal, ramal
    «-1» = un tamaño menor en la lista del tipo, ángulos del codo solo en DISTRIBUCION PRINCIPAL—, `electricas`
    por tipo/amperaje/largo); celda vacía = sin restricción o no aplica. Catálogo GLOBAL `ruta()` =
    %APPDATA%/pdf-to-cad/normativas_tablas.json (env `PDFCAD_NORMAS_TABLAS`; `tests/conftest.py` lo manda a
    tmp); `normalizar` suma a TIPOS los tipos usados en las tablas; `agregar_tipo` (botón «+»). `normas_excel.py`
    — `importar` (encabezados por nombre) / `exportar`: hojas TIPOS, PRESION-DIAMETROS, PRESION-ACCESORIOS,
    ELECT-TELECOM como tablas; desplegables: UTILIDAD = `TIPOS!$K$1:$P$1`, TIPO = `OFFSET(TIPOS!$K$2,…)` sobre un
    bloque auxiliar OCULTO K:P (ArrayFormula `_xlfn._xlws.FILTER`, una columna por utilidad) que se rellena solo
    con las filas nuevas de TIPOS. Fórmulas de validación en INGLÉS con openpyxl (por COM Excel las espera
    localizadas). `normas_validar.py` (PURO) — `validar(cat, pipes, accesorios, ft_per_px, con_bancoducto)` →
    `Aviso(x, y, clase, mensaje, pipe, info)`: sin tipo / tipo que ya no existe, diámetro según el tipo (nombra el
    otro tipo si el diámetro es de él; la nota va como `info`), eléctricas (sin amperaje = aviso; con bancoducto
    no se revisa), accesorios sobre el tipo de la PRINCIPAL (`accesorios.tronco_y_ramal`: nodos T/Y traen
    `tronco`/`ramal`), T con ramal domiciliario = SOLO la fila «T - Domiciliaria», codo ±1° (`a["angulo"]` =
    deflexión sobre el eje). Solo avisa: nunca mueve geometría. UI (pedido: «avisos NO invasivos»):
    `ui/comun/avisos_view.py` (`InsigniaAviso`: circulito ámbar «!», celeste «i» = info; agrupa por punto; «sin
    tipo» NO se dibuja —52 insignias en un proyecto recién importado—), etiqueta del accesorio en ámbar con «⚠»
    (`accesorios_view`), `btn_normas` «⚠ N avisos de normativa» (fondo transparente, clic →
    `open_normativas(en_avisos=True)`), `lbl_normas_pipe` en el panel. `Main._draw_accesorios` calcula todo en
    cada `_redraw` (`self._normas_avisos`). Panel: `prop_tipo` + «+» verde (`_boton_mas(self._agregar_tipo)`) y
    `prop_amp` (solo ELECTRICO) → `p["tipo"]`/`p["amperaje"]`; también en `edicion_bloque` y copiar/pegar. DXF:
    `XD_TIPO`, `XD_AMPERAJE` en `PDFCAD_PIPE` (Property Set de Civil 3D sin tocar el plugin). Ver → submenú
    `menu_avisos` («Avisos»: conflictos, `act_show_acc`, `act_show_normas` —QSettings `show_normas`—, mostrar/
    ocultar todos). `ui/dialogos/normas_dialog.py`: pestaña Avisos (clic → `_normas_ir_a`) + las tablas de solo
    lectura; Importar/Exportar Excel, «Volver a los valores iniciales» (se edita en Excel). **Aprobar avisos**
    (2026-10-12): `nucleo/normas_aprobacion.py` (PURO) — registro `Main.normas_aprobados` (.digproj, deshacer,
    `respaldo_editor`) con clave = clase + utilidad + lugar (2 px) + `huella` (capa, tipo, familia, tamaño, amperaje,
    ab): si cambia, vuelve a pendiente y el registro queda «Ya no aplica»; `marcar` (en `_draw_accesorios`) pone
    `Aviso.aprobado`; `en_punto`, `avisos_view`, `marcas3d` y el contador lo saltan; Tabla de datos con Estado/
    Aprobado por/Fecha/Nota; `reindexar` al borrar una utilidad. Pestaña Avisos: «Aprobar seleccionados…»,
    «Quitar aprobación», «Mostrar aprobados»; `Main.aprobar_avisos`/`quitar_aprobacion`. Tests:
    `tests/test_normas_aprobacion.py` (también el Excel con estado/familia/tamaño/diámetro/material:
    `tabla_excel._cambios_seccion`, `catalogo=Main._catalogo_excel()`, aplica por `edicion_bloque.aplicar`). `.digproj`: ya no
    escribe `normativas_activas` (la lee y la ignora). **Rangos MIN/MAX** (2026-10-14, Excel v2 del ingeniero con
    «0.5-2», «>4», «>=400» en una celda que se perdían callados): PRESION-DIAMETROS `DIAMETRO MIN/MAX (in)` (fila con
    lista O rango, `_permite`), ELECT-TELECOM `AMPERAJE MIN/MAX (A)`, `LONGITUD MIN/MAX (pies)`, `RADIO CURVA MAX`;
    en memoria [mín, máx] con None = abierto (`nc.rango_min_max`, `en_rango`, `texto_rango` «≥ 400»); se sigue
    leyendo «AMPERAJE (A)»/«LONGITUD RANGO» «0-320». `importar(ruta, problemas=[])` anota cada celda que no entiende
    (hoja, fila, columna; el diálogo la muestra y no aplica en silencio). Radio de curva: `validar(structures=)` →
    aviso «radio» en la curva (`radius_ft` o `radio_auto_ft`). Al exportar: comentario por encabezado, validación
    numérica en MIN/MAX y hoja INSTRUCCIONES primera (`nucleo/normas_excel_ayuda.py`); solo se leen las 4 tablas
    (INSTRUCCIONES y «auxiliar» = notas del ingeniero, nunca). Columna DESCONOCIDA (p. ej. «DIAMETRO PRINCIPAL (in)»
    antes del `ALIAS`) → problema «HOJA: columna «X» desconocida» (antes se perdía callada). **v4** (2026-10-14):
    `BASE` = «Normativas v4» del ingeniero (copia en `tests/escenarios/normativas_1_3_1.xlsx`) y columna
    `RADIO CURVA FIJO (pies)` (lista, `radio_fijo`: la curva debe ser uno de esos radios ±0.005 ft; con MIN/MAX
    además el rango). Tests: `tests/test_normas.py`.
  - **Tabla de datos** (2026-10-09, Herramientas, Ctrl+Shift+T, botón `_act_tabla` `mdi:table-large`):
    `nucleo/tabla_datos.py` (PURO: `armar(...)` → `Tabla` utilidades/buzones/curvas/bancoductos/avisos, con
    `lugares` para ir al plano; `exportar_excel` una hoja por tabla) + `ui/dialogos/tabla_datos_dialog.py` (no
    modal, buscar, ordenar —`_Item` compara números como números—, doble clic → `Main._ir_a_elemento`).
  - **Vista 3D** (2026-10-10, Ver → «Vista 3D», F3, botón `_act_3d` `mdi:cube-outline`, clic derecho → «Ver en
    3D»): lo que Civil 3D va a construir, sin exportar. `nucleo/modelo3d.py` (PURO) `construir(pipes, structures,
    ft, colores, duct_banks, cruces, avisos, choques, ocultas, ver, suelo_z)` → `Escena` (mallas numpy de
    triángulos, 15 floats por vértice: pos, normal, color, **id** del objeto, eje + radio de la sección en las
    TUBERÍAS —`barrido_camino(minimo=True)`: el shader las engrosa desde su eje hasta `RADIO_MIN_PX`=1 px de radio
    si de lejos quedarían más finas (pedido 2026-10-10: en la vista encuadrada desaparecían); accesorios,
    buzones y sólidos a tamaño real (radio 0)—; `picks` = cápsulas para elegir;
    **INSTANCING** (2026-10-16, «mismos resultados con menos recursos»): dentro de `construir`
    (`M.instanciar(I3.Instancias())`, por hilo) `mallas3d.barrido_camino` con perfil circular CENTRADO
    (`_es_circulo`: tubos, brazos/campanas/codos de `accesorios3d`, verticales, buzones redondos) y `esfera`
    (avisos/conflictos) NO hacen triángulos: anotan filas en `nucleo/instancias3d.py` (34 floats por tramo:
    los dos anillos P/lado/arriba/inglete b·f, color, id, r, radio mínimo; TAPA y ESFERA con la misma fila)
    y devuelven `VACIA`. `Escena.base` = el resto (prismas, bancoducto, suelo aparte), `Escena.instancias` =
    {(tipo, lados): filas float32 centradas}; `Escena.opacos` (propiedad, cacheada) = base + `expandir_todo`
    = los triángulos de antes (respaldo y pruebas). `expandir` repite las operaciones de `barrido_camino`
    → BIT A BIT iguales (prueba con 200 recorridos al azar); `extremos` da la caja exacta sin armarlas. GPU:
    `ui/comun/visor3d_instancias.py` (`Instanciador`, malla unidad por (tipo, lados) + filas con divisor 1,
    `glDrawArraysInstanced` de `extraFunctions`, shader `visor3d_shaders.VERT_INST` = la misma cuenta;
    `soportado`: GL ≥ 3.3 o `GL_ARB_instanced_arrays`; si falla o `PDFCAD_SIN_INSTANCING=1`, `Visor3D` sube
    `escena.opacos` como antes). Además, mismos resultados: `model_ops.memo_cotas()` (las cotas por vértice de
    cada utilidad una vez por `construir`; `cotas_tramo` las rehacía por tramo) y `_IndiceVertices` para
    `_soleras_en`. Medido (300 utilidades, 1.3 M triángulos): RAM de la vista +520 → +60 MB, escena 234 → 5 MB,
    armado 59 → 18 s; imágenes con y sin instancing iguales (≤ 0.003 % de píxeles de borde); geometría igual
    a ≤ 6e-5 ft (redondeo float32). Tests: `tests/test_instancias3d.py`.
    `objetos` id → datos; centrada y con el suelo en z = 0). Reglas = las del plugin: eje = solera + medio alto
    interior; cotas por tramo con `model_ops.cotas_tramo`/`z_en_tramo` (sacadas VERBATIM de `Main._pipe_z_at`,
    que ahora delega); curvas con `limpieza_tramos.curvas` (= `fillet_geo`); bancoducto reemplaza a su utilidad,
    FONDO en la cota (CrearDuctBanks); buzón = fondo en la solera más baja (o SUMP), tapa = RIM o fondo +
    COVER_MIN (5 ft), «Altura» manda, mínimo 1 ft (ImportarRed); sólidos con `solid_top_centrado`; accesorios de
    `accesorios.accesorios` con la forma de `WyeSolido.cs` en `nucleo/accesorios3d.py` (PURO; espejo de
    sus constantes, `test_espejo_de_wyesolido`): Tee/Wye/cruz = brazo por tubo (cuerpo 0.75·D/1.25·D, tronco de la
    Wye +0.03 ft) + campana; `aplanar`, `sacar_campanas`, `separar` como el plugin; codo = cuerpo CURVO
    (`curva_codo`) + 2 campanas; cada tubo se RECORTA hasta su `alcance` (`cortar`). Sin bolas: el usuario las
    rechazó (2026-10-10, «no refleja la realidad»), tampoco en los quiebres de las tuberías: `barrido_camino`
    comparte los anillos en INGLETE (bisectriz, 1/cos(giro/2)) y la curva queda lisa. Dos líneas casi encimadas
    (Wye a 0.4°) daban brazos de cientos/miles de ft y con 0.01° el tubo se recortaba ENTERO (santos_proyecto_prueba,
    #8 de agua: solo se veían sus codos): `separar` y `SepararBrazos` (WyeSolido.cs) ya NO separan brazos a <
    `ANG_EJES_MIN_DEG` (superpuestos; el plugin lo avisa), y `RECORTE_MAX`=0.45: una campana nunca recorta más
    del 45 % de una tubería (ninguna puede desaparecer). **Codo por cambio de PENDIENTE** (2026-10-16, «00.proyecto»
    utilidades 2-3-4: casi rectas en planta, la del medio sube 6 ft en 3.4 ft): `accesorios.clasificar(salidas,
    pendientes)` mide el giro de DOS tramos en 3D (extremo `ext[8]` = subida por pie en planta hacia el otro
    extremo), como `ProcesarJunturasPresion` (vectores 3D al extremo lejano); Tee/Wye/cruz siguen en planta; a
    nivel da lo mismo que antes. `_accesorios` recorta cada tubo `alcance × componente en planta` del brazo
    (`A3.cortar` mide en planta; con brazos empinados dejaba hueco). **Conexiones verticales** (2026-10-14, `nucleo/verticales3d.py`,
    espejo de `CrearConexionesCruzadas`/`ColocarFittingSolido`/`CrearCruceConWye` con `FITTING_COMO_SOLIDO`; antes solo
    un cilindro): `planear` (antes de los accesorios) + `dibujar` (después). Vertical Ø = el menor; en cada horizontal
    (eje = solera + r) CODO 90° si TERMINA a ≤0.5 ft (`alejandose`, como `DireccionAlejandoseDelCruce`) o TEE si pasa
    (tangente); recortes en las campanas. Caso Wye: la que pasa tiene un codo del plano ahí y la otra termina →
    `_accesorios` convierte ESE codo en Wye (`_plan_wye`, tronco con `ENGROSE_TRONCO_Y_FT`, ramal `ramal_de`) y
    `_wye` pone tubo aux `TUBO_AUX_CRUCE_FT` + codo + vertical + codo (en `d_e3`, la otra se recorta); desnivel < 2 bocas
    de codo 90° + 0.05 → `inclinada`: ramal hacia el vértice siguiente de la que termina y su punta sube/baja a la Wye
    (`_utilidad(ajustes=)`). Piezas registradas como «accesorio» (`vertical=True`) con ficha. Desde 2026-10-16 el
    brazo hacia la utilidad sigue su PENDIENTE (`_Dibujo.brazo_3d` con `z_eje`; recorte `corte_brazo` en planta):
    una utilidad que sube 17° desde el cruce entraba torcida a un codo armado a nivel. OJO: el plugin
    (`ColocarFittingYOrientar` con `DireccionAlejandoseDelCruce`, z = 0) aún lo arma a nivel. Sin «Accesorios» a la
    vista: solo la vertical. Test: `test_conexiones_verticales_con_codos_tee_y_wye_como_el_plugin`. Largos y diámetros 3D = DXF (verificado: diferencia 0); «sin tipo» no se marca (como
    en el plano). Ids: utilidad i+1, estructura `ID_ESTRUCTURA`+j+1, accesorio, aviso (`objeto_de`). Suelo
    automático = tapa más alta o 3 ft sobre el tope de la tubería más alta. `nucleo/mallas3d.py`: primitivas
    (`barrido_camino` VECTORIZADO —un tramo por llamada tardaba 1.4 s con 66 utilidades, ahora ~0.3 s—, `prisma`, `esfera`, `elegir` = rayo contra cápsulas con
    radio mínimo). `ui/comun/visor3d.py`: `QOpenGLWidget` + shaders GLSL 120 de Qt (SIN dependencias nuevas;
    pyqtgraph no está instalado y sumaría PyOpenGL al .exe), resaltado por UNIFORMES (`uSel`/`uHov` contra el id
    del vértice: elegir no reconstruye); los ACCESORIOS no llevan tamaño mínimo (el usuario lo pidió quitar), solo las tuberías; `glBlendFuncSeparate(..., ZERO, ONE)`: con
    el alfa del framebuffer < 1 Qt componía el widget con el fondo y lo semitransparente salía azul. Navegación
    Civil 3D (rueda = zoom hacia el punto EXACTO bajo el cursor —superficie de la tubería, `mallas3d.choque`, o el
    plano del objetivo—: la cámara se mueve por el rayo sin girar, el objetivo queda a la profundidad de ese punto
    y se detiene a `DIST_MIN_FT`=1 ft de la superficie, nunca la atraviesa (antes, en el zoom máximo, cada clic
    empujaba ~1 % del modelo y saltaba); desplazar = 60 % del ratón (`DESPLAZAR`) a la PROFUNDIDAD de lo agarrado
    al apretar (`_prof_agarre`; antes un piso del 0.5 % del modelo lo disparaba de cerca); doble clic central = encuadrar todo; central =
    desplazar, Shift + central = girar; izquierdo = girar, derecho/Ctrl = desplazar). La cámara NO se recuerda:
    `abrir` → `visor.reiniciar()` si la ventana estaba cerrada. Zoom 5 % por clic (`ZOOM_PASO`=0.95; 15 % y 8 % eran muy
    sensibles); giro 0.22°/0.16° por píxel (`GIRO_DEG_PX`). **Cubo de vistas** (`ui/comun/cubo_vistas.py`, pedido 2026-10-10, como el ViewCube de Civil 3D):
    QPainter ENCIMA del GL (proyección ortográfica con la orientación de la cámara), caras con su nombre deformado
    con `QTransform.quadToQuad`, anillo N/E/S/O (+X este, +Y norte); clic en cara/letra → `Visor3D.animar` (giro
    suave por el camino corto), arrastrar → orbitar; letras detrás del cubo tapadas y sin clic. OJO OpenGL: el VAO
    se enlaza SOLO mientras se dibuja el modelo y se apagan los atributos y el test de profundidad antes de
    QPainter (si no, sus rellenos no salían); `paintGL` repone depth/blend al empezar.
    **Ficha** (pedido 2026-10-10): `nucleo/ficha3d.py` (PURO, de las MISMAS tablas que «Tabla de datos» sin
    coordenadas + pendiente + avisos; accesorio: tipo, ángulo, une, diámetros, cota del eje —`modelo3d` registra
    `pipes/eje_z/x/y`—) + `ui/dialogos/vista3d_ficha.FichaPanel` (Campo | Valor arriba del panel, «Ver en el
    plano», «Copiar»); sigue la selección del plano; un accesorio elegido en 3D = `_sel_local`. Esc NO cierra
    (`keyPressEvent`): `deseleccionar` (3D, ficha y plano) o nada; clic en el vacío también deselecciona.
    Abandonadas A TRAZOS (`mallas3d.trozos`, trazo ≥3 ft o 4·D, hueco 60 %; antes semitransparentes). Cámara
    por defecto en PLANTA (`VISTAS["arriba"]`) y encuadrada.
    `ui/dialogos/vista3d_dialog.py`: ventana no modal (barra Encuadrar/Arriba/Frente/Lateral/Isométrica/«Seguir
    la selección», panel = utilidades con su color = leyenda, mostrar, suelo con «Restablecer»; sin exagerar la altura: el
    usuario la pidió quitar), línea de estado con
    lo que hay bajo el cursor); `construir` corre en `QThreadPool` sobre COPIAS, con pausa de 350 ms y firma
    (json de los datos: si no cambió, no recalcula). `ui/ventana/ventana_vista3d.py` (`Vista3DMixin`):
    `abrir_vista3d`, `ver_en_3d`, `_vista3d_al_dia` (al final de `_draw_accesorios`, o sea de cada `_redraw`).
    Al abrir, `_guardar_antes_de_3d` (pedido 2026-10-10, «por si acaso»): con archivo y `_has_real_changes` →
    `_write_project`; sin archivo → `autoguardado.guardar_ahora()` (copia de recuperación), NUNCA «Guardar como».
    Ajustes en QSettings «pdf-to-cad»/«vista3d». Sin OpenGL 2.1 la ventana lo dice (no se cae; offscreen arma la
    escena sin dibujar). Tests: `tests/test_vista3d.py`.
  - **Cruz en X, reducciones y pendientes** (pedidos del usuario 2026-10-16): `accesorios.accesorios` parte los
    DOS tramos de un cruce en X a mitad de tramo (ninguno con vértice a ≤ tol) de la misma red y cota → cruz (con
    diámetros distintos también); `_union_civil` (plano) ya no lo llama choque. OJO: el plugin aún no la arma.
    `accesorios(rectos=[])` devuelve además las uniones RECTAS de dos tramos; `nucleo/reducciones3d.py` (PURO,
    espejo de `ReduccionSolida.cs`): en 3D `rectas` = reducción (campana del grande + cono `mallas3d.tronco`
    1.25·D mayor + campana del chico, tubo chico recortado) donde cambia el diámetro; codo REDUCTOR
    (`modelo3d._accesorios`): codo uniforme del diámetro MAYOR (`chico.d` = mayor) + `codo_reductor` (cono desde
    donde moriría un tubo mayor en la campana del codo hasta el eje del chico); si el tubo chico no alcanza, codo
    solo. Ficha «Reducción» (`NOMBRE_ACC`). Pendiente: `lbl_pendiente` en el panel de la utilidad
    (`_mostrar_pendiente`: una si un tramo o todas iguales, si no «T1 … · T2 …»); la ficha 3D igual (la de cada
    tramo REEMPLAZA a la de punta a punta). Vista 3D «Ángulos y pendientes por tramo» (`ver["rotulos"]`, apagada):
    `nucleo/rotulos3d.py` → `Escena.rotulos` (pendiente en el medio de cada tramo, giro en cada vértice interior,
    id de su utilidad), pintados por `etiquetas3d.dibujar(rotulo=True)`. Tests: `tests/test_reduccion_cruz_pendiente.py`.
  - **Conflictos NUMERADOS + Excel de ida y vuelta** (2026-10-10, pedido del usuario): `nucleo/conflictos.py` (PURO)
    `numerar(items)` → `Conflicto` C-1, C-2… en orden de LECTURA (filas de `FILA_PX`, luego x) y sin repetidos (el
    mismo cruce visto por varios pares de tramos en un vértice = uno; antes C-10…C-13 en el mismo punto);
    `agrupar` (etiqueta «C-10 · C-13» si coinciden). `ui/ventana/ventana_conflictos_lista.ConflictosListaMixin.
    _numerar_conflictos` (al final de `_draw_pipe_conflicts`) junta los cruces «conflicto» que el plugin NO une
    (`_union_civil` vacío) y TODAS las alertas rojas (`_exceso/_escalon/_codos/_retorno/_pendiente/_inclinada/_redes/
    _choque_hits`, con sus `_msg_*`) → `Main._conflictos` y `ui/comun/conflictos_view.dibujar` (etiqueta roja ARRIBA
    A LA IZQUIERDA de la marca: a la derecha va la del accesorio). Tabla de datos: pestaña «Conflictos»
    (`tabla_datos.armar(conflictos=)`) y «Cotas por vértice» (`tabla_excel.tabla_vertices`). `nucleo/tabla_excel.py`
    (PURO): `exportar` (columnas `EDITABLES` en verde, «Léeme»), `importar` (hojas y encabezados en ES o EN vía
    `TRANSLATIONS`), `cambios` (tolerancia del redondeo del Excel: lo no tocado no cambia; coma decimal; errores por
    fila), `aplicar`; el diálogo confirma, `_push` (Ctrl+Z) y recalcula. 3D: `nucleo/marcas3d.py` (avisos y
    conflictos; `ID_CONFLICTO`, `Escena.etiquetas`, `ui/comun/etiquetas3d.dibujar` con QPainter), ficha
    `ficha3d.de_conflicto`; sin el tooltip de instrucciones en el visor (tapaba el de los conflictos). Tests:
    `tests/test_conflictos_excel.py`. **Pendiente (%)** (2026-10-14): `model_ops.pendientes_tramos` (por tramo =
    por tubería de Civil 3D, Slope: Δcota/largo en planta, con `cotas_tramo`) y `pendiente_total` (rasantes de punta a
    punta / largo en planta): columna en la Tabla de datos (verde en el Excel) y ficha 3D («Pendiente por tramo» si
    cambia). Al importar, `tabla_excel.incoherencias`: una pendiente CAMBIADA (≠ la del proyecto ±0.0015) que no
    coincide con las rasantes de su fila → el diálogo NO importa nada y sugiere la rasante; `cambios` nunca la
    aplica (se recalcula). Tests: `tests/test_pendiente.py`.
  - **Redibujo rápido, mismo resultado** (2026-10-16, «sobre todo cuando se hace de forma masiva»; 400
    utilidades: ~20 s por redibujo). `nucleo/indice_plano.py` (PURO): `pares_tramos(segs)` = pares (a < b,
    ORDENADOS) cuyos recuadros —agrandados por la tolerancia t, u ∈ [−1e-6, 1+1e-6] y `MARGEN_PX`— se tocan
    (ningún cruce queda fuera); `IndicePuntos(puntos, celda).en_caja/en_radio` = índices ORDENADOS. Quien llama
    hace la MISMA prueba en el MISMO orden («el primero gana» igual): `model_ops.choques_sin_conexion`,
    `junturas_excedidas` (grupo por centro móvil: candidatos a ≤ R del primero y, si el centro se alejó más de
    R − tol, otra vez con R mayor), el bucle de pares de `_draw_pipe_conflicts`, `_color_for` de los buzones y
    las insignias de `accesorios_view`. `nucleo/memo_modelo.py` (PURO): `Main._redraw` calcula
    `_firma_modelo()` (pickle + blake2b de pipes, structures, cross_connections, normas_aprobados, normas_cat,
    duct_banks, scale, zoom, idioma) y `self._memo(clave, fn, copiar)` reusa lo que depende SOLO de eso (cruces
    de presión, juntas, escalones, codos, retornos, choques, accesorios, normativas, ángulos y la polilínea de
    cada utilidad `("dibujo", i)`); devuelve COPIAS (`memo_modelo.copia`: `marcar` escribe en los avisos).
    OJO: un cálculo NUEVO memorizado que lea otro estado de la ventana suma ese estado a `_firma_modelo`, o el
    redibujo mostraría un resultado viejo; fuera de `_redraw`, `_memo` siempre calcula. Todo el redibujo va
    dentro de `model_ops.memo_cotas()`. Foto de lo que calcula el redibujo (hits, C-n, avisos, accesorios e ítems
    del lienzo con posición y tooltip; 8 casos: sintéticos densos, uniones en estrella, escenarios, presentación,
    proyecto del usuario) = idéntica al código viejo; 400 utilidades: 19.9 s → ~1.3 s con el modelo cambiado,
    ~0.75 s sin cambios (lo que queda es crear los ítems Qt). Tests: `tests/test_rendimiento_plano.py`
    (índices = todo con todo, en el núcleo y en la ventana; memo reusa y se invalida).
    **Ratón y deshacer** (mismo día, puntos 3 y 4): `indice_plano.IndiceUtilidades` + `utilidades_cerca(cache,
    pipes, x, y, r)` = utilidades con un tramo a ≤ r, en orden; lo usan `_update_hover_tooltip`, `_pipe_soft_snap`,
    `_pipe_at` y `_vertice_bajo_clic` (vía `Main._utilidades_cerca`, caché `_cache_raton`). El índice se valida
    comparando la geometría (`_firma`, ~0.3 ms con 400 utilidades) y solo se arma si la misma geometría se ve dos
    veces seguidas (arrastrando un vértice cambia en cada evento: se recorren todas, como antes). Clic en vértice
    802 → 14 ms, `_pipe_at` 4.4 → 0.7 ms. OJO al medir el ratón sin bucle de eventos: `scene.sceneRect()` (cruz del
    cursor) recalcula el recuadro de TODOS los ítems si no corrió `processEvents` (30 ms falsos). `nucleo/
    deshacer.py` (PURO): `_snap_state` → `deshacer.paso(estado, anterior)` = cada elemento de cada lista en bytes de
    pickle y lo igual al paso anterior REUSA los mismos bytes; `_restore` → `deshacer.abrir`. Si dos partes del
    estado comparten un objeto mutable (`_comparte`), el estado entero va en un bloque (= deepcopy). 100 pasos con
    400 utilidades: +111 → +3 MB. `model_ops.rebuild_structures` (lo llama `_refresh_lists`: cada deshacer) con
    celdas de `_TOL` (dedupe de vértices e `IndicePuntos` para reasignar ediciones, mismo orden): 0.7 → 0.04 s en 11
    casos idénticos al código viejo (deshacer con 400 utilidades tardaba ~18 s, 12 s ahí).
    **Proyecto que no abría** (2026-10-16, «PRUEBA AGUA 2 PDF SIN CAPAS»: 16 761 utilidades de agua = mapa con
    acometidas): `_union_civil` llamaba `accesorio_en_punto` con TODAS las polilíneas de la capa en cada cruce
    (~33 mil) → nunca terminaba. Ahora solo las de `_indice_union()` (un `IndiceUtilidades` por redibujo,
    `_indice_redibujo`, soltado en `_redraw`; fuera de un redibujo, todas), mismo orden: abre en ~46 s (lo demás
    es dibujar ~33 mil marcas de cruce y ~38 mil etiquetas de accesorios).
    **Capas de marcas** (mismo proyecto, «se lagea mucho»): `ui/comun/capa_marcas.py` — las marcas de tamaño
    fijo en pantalla (círculo + texto de cruce y alerta roja de `ventana_conflictos`, `EtiquetaAccesorio`,
    `InsigniaAviso`, C-n de `conflictos_view`) son los MISMOS ítems de siempre pero NO entran a la escena:
    `Main._marca(it)` → `GrupoMarcas.agregar` (uno por redibujo, `self._marcas`) las pone en la `_Capa` de su Z
    (un ítem de la escena por Z), que las pinta con su propio `paint` como Qt pinta un ítem que ignora el zoom
    (punto → pantalla + su transformación, mismo orden), solo las de los rectángulos a repintar
    (`paintEngine().systemClip()`: la cruz del cursor = dos franjas; Qt no lo deja como recorte del pintor) y
    por celdas. Tooltip: `hoverMoveEvent` → `tooltip_en` (la marca de más arriba cuya forma contiene el
    cursor, como `QGraphicsScene.helpEvent`). Siguen en `_overlay` (las pruebas y listas los leen); el borrado
    del redibujo solo saca de la escena lo que está en ella. Reuso: `_reusar_marca(clave)`/`_guardar_marca` —
    clave = todo lo que define el aspecto (tipo, punto, estado, texto) → el MISMO objeto del redibujo anterior
    con su tooltip renovado. Además: `_union_civil` memorizado (`_memo`), plumas/fuente/medida del texto de
    cruce una vez, `memo_modelo.copia` con pickle, y al abrir un solo redibujo (`_redibujo_diferido`). Igualdad
    verificada: píxeles y tooltips de 15 vistas con y sin capas / con y sin reuso = 0 diferencias. «PRUEBA
    AGUA 2»: abrir 30 → 20 s, redibujo 22 → 10 s, mover el ratón 1.3 → 0.6 s; zoom ~igual (pinta todo lo
    visible). Probado y descartado: `DeviceCoordinateCache` en las capas (ratón 0.12 s pero cada zoom 4 s).
    Tests: `tests/test_capa_marcas.py`.
    **2.º reporte (2026-10-17)**: (1) la cruz «borraba» etiquetas: el recorte del sistema va en px FÍSICOS de
    la VENTANA (desplazamiento de la vista + escala de pantalla 125 %) → se lleva con `deviceTransform`, no con
    `worldTransform` (en las pruebas offscreen la escala es 1 y el desplazamiento 0: no se veía; la prueba
    `test_repintado_parcial_no_borra_marcas` repinta solo la franja con `vp.render(img, desplazamiento,
    región)` a 1.25). Descarte exacto por la CAJA de cada marca (numpy), no solo por el margen de la mayor.
    (2) SELLOS: `capa_marcas.sello(item, clave)` o `sello(item, partes=[(clave, fases, rect, pintar)])` = el
    aspecto se dibuja UNA vez por (clave, escala de pantalla, fase de subpíxel en pasos de 1/`FASES`=2) y se
    copia con `drawPixmap` alineado al píxel físico; la escala es la REAL del pintor (`deviceTransform` con el
    mundo identidad: al renderizar a una imagen `device()` puede ser la vista con otra escala). La etiqueta del
    accesorio va por PARTES (`EtiquetaAccesorio.partes_sello`: fondo con 2 fases, texto con 1): en AGUA 2 hay
    ~3 600 textos distintos («Codo 12.34°»). Memoria tope `MAX_MB`=192 (se vacía). Las marcas sin clave se
    pintan como antes. Diferencia con lo que dibuja Qt: bordes de ≤¼ px y letras que el ajuste de fuente
    corre 1 px. OJO: `QTransform.type()` es un enum NO ordenable (`.value`); una excepción dentro de un
    `paint` con `painter.save()` sin `restore()` tumba el proceso: `_pintar_marcas` va en try/finally.
    (3) Redibujo: `_poly(reuso=("pipe", i))` reusa los segmentos de la utilidad si el objeto de puntos
    memorizado es el MISMO y el aspecto igual (`_lineas`/`_lineas_previas`; lo no reusado se quita en
    `_soltar_lineas_previas`; un segmento rehecho —el seleccionado— queda encima de los demás de su Z); la
    clasificación de los cruces (`_clasificar`), los textos/globos de las etiquetas (`accesorios_view.preparar`)
    y el índice de vértices de los buzones van por `_memo`; `_Capa.agregar` avisa a la escena solo si la caja
    crece y guarda punto/caja/ids en la marca. AGUA 2: zoom ~8 s → 0.2–0.5 s, redibujo ~4 s → ~1 s, ratón de
    cerca ~30 ms (vista entera ~180 ms: la cruz cruza ~16 mil marcas), desplazar ~8 ms. `nucleo/limpieza.py`
    (`_duplicadas`, `_unir_puntas`, `_sueltas`) con `IndicePuntos`/`IndiceUtilidades`, mismo orden: «Exportar»
    con 16 761 utilidades no terminaba (> 5 min) → 1.6–5 s (`test_limpieza_con_indices_igual_que_todo_con_todo`).
    Queda en «PDF + anotaciones»: digitalizar el PDF (`PipelineWorker`, 198 s, DXF base de 132 MB) + releerlo
    (30 s) + guardar (~32 s).
    **Nivel de detalle y redibujo (3.er pedido, mismo día)**: `capa_marcas` partido en `capa_marcas_sellos.py`
    (`sello`, cajas, `_hacer_sello`) y `capa_marcas_vista.py` (`CacheVistaMixin`, `DespejeMixin`). RÓTULOS:
    `sello(it, clave, rotulo=True)` o el 5.º valor de cada parte (`EtiquetaAccesorio.partes_sello`: rombo = punto;
    guía+pastilla y texto = rótulo; C-n = rótulo entero); `despeje_rotulos.despejar` (PURO, voraz por prioridad:
    Z más alta y orden de llegada, rejilla de 64 px) una vez por escala y región de la vista ±50 %
    (`GrupoMarcas.rotulos_visibles`; desplazar dentro de la región no lo rehace); los rótulos se pintan DESPUÉS
    de los puntos de su capa; un rótulo oculto no da tooltip (sí su punto). `DESPEJAR` (en `capa_marcas_vista`)
    lo apaga (pruebas de «se ve igual»). IMAGEN DE LA VISTA (`_con_cache`, capas ≥ `CACHE_MIN`=300 marcas): con
    la vista quieta la capa se pinta UNA vez en una imagen alineada al píxel físico y repintar (la cruz) es
    copiarla; se arma al pintar la vista entera o al repetirse la vista; la fase de subpíxel sale SIEMPRE de la
    transformación del pintor tal cual (`inv_w·D` traía 382.5000000000018 y cambiaba empates de redondeo).
    REUSO DE CAPAS: `_firma_marcas()` (firma del modelo + `chk_show_conflicts`/`act_show_acc`/`act_show_normas`);
    si no cambió, las MISMAS capas siguen en la escena (`_marcas_vigentes`: cruces, alertas, C-n, etiquetas e
    insignias no se rehacen; los hits sí se calculan). OJO: una marca nueva que dependa de otro estado suma ese
    estado a `_firma_marcas`. AGUA 2: ratón a vista entera ~85 ms, zoom 0.17–0.38 s, elegir ~0.7 s.
    EXPORTAR: `exportar/cache_digitalizado.py` (PURO; clave = sha1 del PDF + hojas + código del pipeline —los
    .py de la raíz, o versión + ejecutable en el .exe—; `MAX_ARCHIVOS`=4, `MAX_MB`; `PDFCAD_CACHE_DIGITALIZADO`,
    las pruebas a tmp) → `run_pipeline` reusa el DXF base; `ui/comun/en_hilo.ejecutar` (hilo + bucle local +
    capa «Cargando…», `cancelable`) para leer (con «Cancelar») y guardar el DXF (`_guardar_dxf_en_hilo`);
    digitalizar con «Cancelar» (`_export_tok`: el resultado de una cancelada se descarta). `limpieza_tramos.
    cajas_de(pipes)` + `al_dia`: `compartido` solo prueba las utilidades cuya caja contiene el punto (mismo
    resultado; `_sin_tramos_diminutos` y `limpieza` lo usan) y copias con `memo_modelo.copia`: fusión 14 → 3.2 s.
    Tests: `tests/test_capa_marcas.py`, `tests/test_exportar_rapido.py`, `tests/test_limpieza.py`.
    **Utilidades en UNA capa (2026-10-18)**: `ui/comun/capa_lineas.CapaLineas` (un ítem a `Z_MARK`, en el lugar
    del orden donde iban los segmentos) pinta cada utilidad con `drawLines` y su pluma cosmética
    (`Main._pluma_utilidad`), en orden; solo las que tocan lo que hay que repintar (cajas en numpy, recorte del
    sistema en px físicos como `capa_marcas`); `cerrar()` fija la caja tras agregar todo. Segmentos por
    utilidad en `Main._lineas_cache` mientras la polilínea memorizada sea el MISMO objeto. Reemplaza al reuso
    por segmento (`_poly(reuso=)`, quitado). Igual píxel a píxel que un `QGraphicsLineItem` por segmento
    (`tests/test_capa_lineas.py`, 100 % y 125 %, cruz incluida). AGUA 2: ratón a vista entera 85 → 23 ms, zoom
    0.14–0.30 s, abrir ~16 s. Medido (sin tocar): editar un vértice ~8 s (redibujo con el modelo cambiado
    6.7 s), deshacer/rehacer ~9 s, guardar .digproj 7.6 s, autoguardado 0.13 s en la ventana, Vista 3D: armar
    la escena ~94 s en otro hilo (19 908 accesorios; el ~390 s de antes era con `tracemalloc`).
    **Editar, deshacer y 3D (2026-10-18, «sin romper nada»)**, todo EXACTO: `memo_modelo.Memo` recuerda los
    `PREVIOS`=2 modelos anteriores (firma → resultados): deshacer/rehacer VUELVE a una firma ya vista y retoma lo
    suyo; la firma es por VALOR (`pickle` en modo `fast`, sin memoria de referencias: tras deshacer los objetos se
    comparten de otra manera y con el pickle normal la firma cambiaba). `model_ops.memo_cotas` guarda además las
    cotas de TODOS los tramos de cada utilidad (`_cota_de_tramo`); `junturas_excedidas` con celdas de 2.5·tol y la
    cota de un extremo solo en los grupos de más de `maximo`; `accesorio_en_punto` salta los tramos cuya caja queda
    a más de tol (con holgura de redondeo); `normas_validar.validar` calcula los tipos de cada capa una vez;
    `_refresh_lists` un muestrario por capa; `normas_catalogo.clave` memorizada. 3D: `mallas3d._cruz`/`_norma`
    (mismos bits que `np.cross`/`np.linalg.norm` sin su costo fijo) y `_circulo_unidad`, `accesorios3d.cortar` en
    floats de Python, `accesorios` con `redes` precalculadas, índice de los codos fundidos y vecinos 5×5 por celda.
    Verificado: foto del redibujo (9 casos con AGUA 2) y foto 3D bit a bit (7 casos) = idénticas; prueba
    `test_deshacer_reusa_el_redibujo_anterior_y_da_lo_mismo`. AGUA 2: deshacer ~9 → ~3 s, editar ~9 → ~8 s (queda
    recalcular accesorios y cruces de todas las utilidades: haría falta un cálculo por zonas), 3D ~94 → ~28 s.
    OJO pruebas: cada prueba de ventana deja su `Main` viva (ya pasaba antes) y `test_theme.py` aplica el tema a
    TODAS (80 ventanas ≈ 160 s, crece más que lineal): en la batería completa se queda «colgado» ahí; correrlo
    aparte. `test_paneles.py` (3) y `escenarios/test_presentacion_131.py` (avisos de ángulo ya ocultos) fallan
    también en `d0cd77f`.
    **Sin trabas con proyectos enormes (2026-10-19, «dibujar, leader, deshacer, Esc… demora bastante»)**. (1) Con
    el MISMO modelo (firma) el redibujo reusa: la capa de líneas (`CapaLineas.cambiar_pluma` solo para las que
    se eligen/sueltan, `Main._capa_lineas` = (firma + colores, capa, elegidas, con T1/T2); el bucle solo recorre
    elegidas + las de etiquetas de tramo), los resultados de accesorios/avisos (`_resultados_acc`) y de cruces/
    conflictos (`_resultado_conflictos`, clave = firma + firma de `cross_connections` tras podar, solo con
    `_marcas_vigentes`): Esc/elegir/modo 1.1–1.6 → ~0.2 s. Ojo: el orden de apilado con las capas de marcas de
    igual Z es el del redibujo COMPLETO (líneas debajo). `_lineas_de_utilidad` reusa por VALOR de los puntos.
    (2) CÁLCULO vs DIBUJO: `ui/ventana/ventana_calculo.CalculoPlanoMixin` (`_calcular_cruces`,
    `_calcular_accesorios`, `_preparar_etiquetas`, `_calcular_vertices_buzones`) = lo de antes, movido tal
    cual, mismas claves de `_memo`. (3) `ui/ventana/calculo_fondo.py`: modelo ≥ `UMBRAL`=3000 utilidades
    (`PDFCAD_CALCULO_FONDO_MIN`) y firma nueva sin resultados → redibujo PROVISIONAL (`_provisional`: líneas,
    buzones… al instante; marcas de antes a la vista, sus listas vacías = sin acciones; el grupo provisional
    va SIN firma, si no el redibujo final lo tomaba por vigente y no dibujaba nada) y `Calculo` (copia del
    modelo + los mismos métodos prestados de las mezclas) corre en el trabajador `proceso` «plano» (+ «plano-2»
    si `proceso_hijo.paralelos` deja: «cruces» y «accesorios» a la vez; un HILO no sirve: el GIL hacía que
    pintar 16 761 utilidades tardara 7 s); al volver, sus claves entran al memo de esa firma y se redibuja.
    `_resultados_al_dia()` espera (Tabla de datos, normativas, Vista 3D, aprobar). Mensaje «Actualizando
    conflictos y avisos…». AGUA 2: editar → ventana libre ~1.7–2.4 s (antes ~8 s), avisos ~8 s; deshacer/
    rehacer ~3 s (memo previo). Recálculo por ZONAS: no hecho (el orden global de cada resultado lo hace
    delicado). Tests: `tests/test_calculo_fondo.py`, `tests/test_capa_lineas.py`.
    **Guardar el DXF** (mismo día): `exportar/dxf_rapido.guardar` (lo usa `Main._guardar_dxf_en_hilo`) cambia,
    solo mientras guarda, `DXFNamespace.export_dxf_attribs` / `_export_dxf_attribute_optional` de ezdxf por la
    MISMA lógica sin objetos intermedios (definiciones por lista de nombres una vez, texto `"%3d
%s
"`,
    vértices `float` ≤3 componentes como `DXFVertex`; solo con `TagWriter`, otro escritor = el de ezdxf). AGUA 2
    (597 mil entidades): 32 → 17 s, archivo idéntico salvo hora/GUID/marca de ezdxf (cambian en todo guardado).
    OJO al actualizar ezdxf (hoy 1.4.4): correr `tests/test_dxf_rapido.py`. Medido: leer el DXF base 30 s y
    fusionar 42 s (zonas borradas/georref sobre las 600 mil entidades).
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
  - **Editar en bloque y copiar/pegar propiedades** (2026-10-08, cliente ferroviario: mapea lo existente, no
    diseña; automatizar el modelado): `nucleo/edicion_bloque.py` (PURO: `aplicar(pipes, filas, cambios,
    sin_familia)`, `cambios` = solo lo que cambia —familia/tamano/net_type/material/ab/datos—; cambiar la
    familia sin tamaño = diámetro por defecto, como el panel; con bancoducto no cambia familia/tamaño) +
    `ui/dialogos/edicion_bloque_dialog.py` (todo arranca en «(sin cambios)»; al pegar, con los valores
    copiados) + `ui/ventana/ventana_bloque.py` (`EdicionBloqueMixin`: `editar_en_bloque` Ctrl+E,
    `copiar_propiedades` Ctrl+Shift+C, `pegar_propiedades` Ctrl+Shift+V, `copiar_de_la_primera`; SOLO entre
    utilidades de la MISMA capa). Tests: `tests/test_edicion_bloque.py`.
  - **Revisar y limpiar el dibujo** (2026-10-08, Herramientas y antes de exportar —`run_pipeline` llama
    `revisar_dibujo(exportando=True)`, que solo pregunta si hay algo que arreglar—): `nucleo/limpieza.py`
    (PURO, en sitio; la vista previa corre sobre copias y la ventana borra con `_delete_pipes`): puntas a
    ≤1 ft de otra de la misma capa y estado → exacto al vértice/línea (nunca de costado contra una paralela:
    `_destino_valido`), utilidades <1 ft y repetidas (borrar; las de bancoducto/conexión vertical nunca),
    aviso de cortas <5 ft sin contacto. `nucleo/limpieza_tramos.py`: tramo RECTO del plugin (tangencia a
    tangencia, `fillet_geo` con sus topes) de 0.02–1 ft = tubería diminuta en Civil 3D («ELECTRICO-47
    (19)»: curva cuyo ancla quedó a 0.07 ft de la T; «(20)», 0.31 ft rectos entre dos curvas seguidas de una
    curva compuesta: con el umbral de 0.25 ft se escapaba). Arreglos en orden, cada uno solo si BAJA la
    cantidad de diminutos y no cambia/recorta otra curva: quitar vértice (sin otra utilidad a ≤0.01 ft —más
    tolerancia tomaba por unión el ancla a 0.07 ft—, sin buzón/caja visible, desvío <`DESVIO_MAX_FT`=0.25),
    estirar la curva hasta el vértice (radio redondeado HACIA ARRIBA a 0.01: T = tramo entero), correr la
    esquina ≤0.5 ft por la recta del otro lado con esa tangencia fija (la esquina es virtual: sobre otra
    utilidad solo si sigue sobre ella), o quitar el ancla + correr la esquina. Foto del proyecto de prueba
    (2.ª versión): 9 tramos arreglados, 0 sin arreglar; lo DIBUJADO (rectas + arcos) se aparta <0.05 ft.
    Tests: `tests/test_limpieza.py` (incluye la geometría real de la #52 y que el dibujo no cambia). **El DXF
    SIEMPRE sin tramos diminutos** (2026-10-09, «resuélvelo de una vez»: el usuario exportaba sin pulsar
    «Arreglar» / con un .exe viejo): `dxf_export.merge_into` cambia por un rato `win.pipes/structures` por
    COPIAS pasadas por `limpieza_tramos.arreglar` (`_sin_tramos_diminutos`) y escribe con `_merge_into`;
    el proyecto no se toca. Test `test_el_dxf_sale_sin_tramos_diminutos_aunque_no_se_limpie`.
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
  Escala: `ctx.S` = DrawingScale, salvo escala de DETALLE (< `PerfilDiseno.S_MIN_PERFIL`=10, p. ej.
  1"=1'): entonces `EscalaAuto(largo)` (menor de 10/20/30/40/50/60/100… con el recorrido ≤ 24 in) y
  `FactorPlInicial ×= S/SDibujo` (las etiquetas nativas escalan con el dibujo). Con S=1 la VE era 1: perfil
  aplanado (2026-10-06).
  **Quiebres mínimos** (2026-09-30): `EnderezarQuiebres` (`ImportarRedEnderezar.cs`, antes de agrupar redes)
  quita en gravedad/conduit los vértices con giro ≤2° y ≤0.25 ft de la recta sin nada encima (buzón visible,
  caja, sólido, curva, ANCLA de un codo —vecino de un vértice curvo: mide el tubo del codo—, otra tubería a ≤1 ft,
  pieza distinta, caída o cambio de pendiente) → un tubo recto (dos en ángulo se montan/abren en planta y 3D; no
  hay limpieza de uniones en la API de estilos). Núcleo PURO `EnderezarNucleo.cs`, casos en el arnés `PerfilPruebas`.
  **Capa de la utilidad** (2026-10-05, `ImportarRedCapas.cs`, paso 5g de IMPORTAR_RED, tras las
  conexiones verticales): cada pieza de cada red creada (tuberías, estructuras, accesorios/apurtenencias de
  presión) pasa a la capa de su polilínea de origen (`redesConOrigen`: red → ImportPipe; red de capas
  mezcladas → la polilínea más cercana). Antes quedaban en la capa por defecto de Civil 3D. Conductos de
  bancoducto → `PDFCAD_DUCT_BANK` (su ImportPipe ya trae esa capa). SÓLIDOS (2026-10-06,
  `AsignarCapasDeSolidos`): los Solid3d de ESTE import (handle ≥ `db.Handseed` al empezar) en
  `PDFCAD_WYE_SOLIDO` (accesorios de presión: codo/Tee/Wye/cruz/reducción) y `PDFCAD_SOLIDOS` (buzones/cajas)
  → capa de la polilínea de utilidad más cercana, dentro de su red si el XDATA trae `RED=`; bancoducto no.
  **Nombres y consola** (2026-10-06): paso 5i `NombrarTuberiasPorRed` → «RED - (n)»; el diagnóstico de
  pendiente ≈ 0 omite redes conduit (estructuras nulas) y agrupa por red; los mensajes por accesorio
  ([CODO-DBG], [XDATA], [WYE-PRESCAN], [JUNTURA-WYE-SCAN], [FITTING-SOLIDO] sin ⚠) van por `ComandosRedes.Dl`
  (solo con `DEBUG_LOGS`).
  **PREPARAR_FAMILIAS paso 5** (`PressureCatalogFiller`, completar tamaños de los SQLite de presión):
  DESACTIVADO desde 2026-10-05 con `ComandosPrepararFamilias.RELLENAR_CATALOGOS_PRESION = false`
  (código intacto; `true` lo reactiva). Los tamaños nuevos van por el «+» de la app.
  **Ángulo del codo** (2026-10-01): el XDATA `ANGULO` de la pieza sigue siendo el GIRO (lo usa el rótulo del
  perfil «45° BEND»); el Property Set `PDFCAD_Accesorio.Angulo_Grados` muestra la
  deflexión sobre el eje (= ANGULO; 2026-10-07, antes 180° − giro), igual que la app.
  **Comandos quitados** (2026-10-07, pedido del usuario): CREAR_RED, CREAR_RED_COMPLETA,
  CREAR_RED_POLILINEA, CREAR_RED_COGO, UNIR_TUBERIAS_RED, AGREGAR_FAMILIA, AGREGAR_TAMANOS,
  AGREGAR_BANCOS_Y_BUZONES/BB, todos los manuales de presión (CREAR_RED_PRESION, CREAR_RUN_PRESION[_COGO],
  AGREGAR_TUBO/ELEMENTO_PRESION, UNIR_TUBERIAS/VARIAS_PRESION, RAMIFICAR_PRESION, CORREGIR_FITTINGS_PRESION,
  SEGUIR_RASANTE_PRESION, LISTAR_PIEZAS_PRESION, EXPORTAR_RED_PRESION_EXCEL, INVERTIR_ALINEAMIENTO),
  LISTAR_ACCESORIOS, DATOS_ACCESORIO, PS_ACCESORIOS y ADJUNTAR_PROPERTY_SET. Se fueron sus archivos
  (`RedesTuberiaEntrada`, `RedesPresionRamales`, `ListarAccesoriosSolidos`, `CatalogoBancos`, `VentanaPropertySet`);
  `RedesPresion.cs` quedó solo con `CorregirFittingsDeRed` (lo usa IMPORTAR_RED, sin preguntar) y
  `RedesTuberia.cs` con la elección de familias/tamaños de IMPORTAR_RED. No volver a crearlos sin que el
  usuario lo pida.
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
- Pruebas: `pytest`  (desde la raíz). Por grupos y en paralelo (cada archivo en su proceso):
  `python scripts/pruebas.py mapas capas` (sin argumentos lista los grupos; `todo` = todas)
- Compilar plugin + exe + instalador: `build_all.bat` (pregunta la versión)
- Quitar el plugin del autoload de C3D (testing): `uninstall_plugin.bat`
- Compilar solo el plugin C#: `dotnet build -c Release` en
  `API-CIVIL/proyecto1/proyecto1` (baseline: 0 errores, 4 warnings).
  El `.csproj` toma las DLL de la PRIMERA AutoCAD instalada (`AcadDir`: 2025 → 2026 → 2027;
  forzar con `-p:AcadDir="…"`) y su .NET (`AcadTfm`: net8 para 2025/2026, net10 para 2027,
  14 warnings). El DLL solo sirve para la versión con la que se compiló.

## Convenciones

- Apuntar a archivos **< 500 líneas**; una responsabilidad por módulo.
- Dónde va cada cosa: lógica pura del dominio → `app/nucleo/`; lienzo → `canvas.py`; widgets reutilizables → `widgets.py`;
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
