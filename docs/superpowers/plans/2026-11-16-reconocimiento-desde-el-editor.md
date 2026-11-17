# Reconocimiento desde el editor — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Abrir un PDF = componer + interpretar y entrar al editor. Desde un panel «Reconocer» del riel, el usuario
reconoce cada cosa por separado (▶), en segundo plano, reutilizando una sola lectura de la hoja.

**Architecture:** La interpretación (capas, leyenda, letras, estilos sugeridos, símbolos, rótulos) corre en un trabajador
dedicado «reconocer» que RETIENE la lectura cruda de la hoja (`pdf_styles.lectura_unica`) por firma de hoja. Cada ▶ es una
`proceso.Tarea` sobre ese trabajador que reconoce una parte (`reconocer_parte`) con el MISMO código de hoy. El estado de las
filas es un modelo PURO (`nucleo/reconocer_estado.py`) que va al `.digproj`. La UI es un panel del riel + una vista central
«Capas y estilos» que reusa los widgets de «Capas de la hoja».

**Tech Stack:** Python 3, PySide6, PyMuPDF (fitz), pytest; trabajadores de `ui/comun/proceso.py`.

**Spec:** `docs/superpowers/specs/2026-11-16-reconocimiento-desde-el-editor-design.md`

## Global Constraints

- **Mismo resultado:** para la misma hoja, utilidad, capas ocultas, roles, letras y escala, un ▶ da EXACTAMENTE lo que da
  hoy `recognition_trabajo.reconocer_hoja` (líneas, codos, bóvedas, válvulas, diámetros). Se verifica con
  `scripts/rendimiento/reconocer.py --foto/--comparar` y con pruebas de igualdad.
- Ventana nunca congelada > 1 s seguido al abrir ni al reconocer (medir con el latido de `scripts/rendimiento`).
- Lectura cruda (~1 GB en 36 mapas) NUNCA a disco ni al `.digproj`; solo en el trabajador «reconocer».
- Nada de lo que el usuario dibujó o editó se borra ni se mueve al reconocer; cada importación = un `_push` (Ctrl+Z).
- Escaneos (`Composite.manual`): flujo sin cambios.
- Archivos < 500 líneas; lógica pura en `app/nucleo`, `app/hoja`, `app/reconocimiento`; textos visibles con `t()` y su
  traducción en `traduccion/i18n_en.py` (`tests/test_i18n.py`).
- Un trabajo nuevo `"mod:fn"` va a `hiddenimports` de `PDF-a-CAD.spec` y a `autoprueba.MODULOS_POR_NOMBRE`
  (`tests/test_empaquetado_trabajos.py`, `tests/test_instalador.py`).
- Atributo nuevo de la ventana que cambie el reconocimiento → `respaldo_editor.CLAVES` y `project_io`.
- **Commits los hace el usuario**: ningún paso hace `git commit`; cada tarea termina dejando los cambios para revisión.
- Pruebas por grupos: `python scripts/pruebas.py <grupo|archivo…>` (nunca la suite entera de una vez).

## Review Focus

1. **Cambiar capas/roles/estilos de una utilidad ya importada** → la fila queda «desactualizada»; el ▶ pregunta reemplazar o
   agregar; reemplazar quita SOLO las líneas de esa utilidad que vinieron del reconocimiento (marca `pipe["reconocida"]`), no
   las dibujadas a mano. Prueba en la Tarea 6.
2. **El trabajador «reconocer» muere o se recicla** (memoria, cancelar) → el próximo ▶ vuelve a leer la hoja y el resultado
   es el mismo. Prueba en la Tarea 3.
3. **Cancelar un ▶ a mitad** → editor intacto, fila vuelve a su estado anterior, la lectura retenida sigue sirviendo.
   Prueba en la Tarea 7.
4. **Abrir otro proyecto / recomponer mientras corre un ▶** → el resultado tardío se descarta (generación), no entra al
   proyecto nuevo. Prueba en la Tarea 7.
5. **Proyecto viejo sin interpretación** → abre sin interpretar, filas de lo ya importado «reconocida», «Interpretar la
   hoja» disponible. Prueba en la Tarea 10.

---

### Task 0: Línea base de tiempos

**Files:**
- Create: `scripts/rendimiento/flujo_reconocer.py`
- Create: `docs/rendimiento/2026-11-16-linea-base-reconocer.md`

**Interfaces:**
- Produces: `flujo_reconocer.py <pdf…> [--agregar <pdf…>] [--salida json]` = tiempos por etapa del flujo ACTUAL: componer
  (sugerida + armar), «Capas» (`capas_trabajo.leer`), reconocer (`reconocer_hoja` todas las utilidades), importar
  (`importar.py`), y la pausa máxima de la ventana. Reusa `scripts/rendimiento/comun.py`.

- [ ] **Step 1:** Escribir el script reutilizando `componer.py`, `capas.py`, `reconocer.py`, `importar.py` (llamar sus
  funciones, no copiar).
- [ ] **Step 2:** Correrlo (uno a la vez, salida a archivo) con Phoenix Water South+North (36 mapas) y luego `--agregar`
  Sewer (36). También DU06 h.3 suelta.
- [ ] **Step 3:** Anotar la tabla en `docs/rendimiento/2026-11-16-linea-base-reconocer.md` (etapa → segundos, pausa máx).
  Es la cifra contra la que se mide la Tarea 12.

### Task 1: Estado de las filas (PURO)

**Files:**
- Create: `app/nucleo/reconocer_estado.py`
- Test: `tests/test_reconocer_estado.py`

**Interfaces:**
- Produces:
  - `PARTES = ("ELECTRICO","TELECOM","DRENAJE","ALCANTARILLADO","AGUA","GAS","VALVULAS","DIAMETROS","ROTULOS")`
    (las utilidades en el orden de `recognition.SUPPORTED_UTILITIES`).
  - `@dataclass Fila(parte: str, estado: str = "sin_interpretar", fuentes: int = 0, motivo: str = "", hechos: int = 0,
    firma: str | None = None, verificar: list[dict] = [], unir_tramos: bool = True)`;
    `estado ∈ {"sin_interpretar","pendiente","bloqueada","reconociendo","reconocida","desactualizada","error"}`.
  - `@dataclass Estado(firma_hoja: str | None, filas: dict[str, Fila])`.
  - `nuevo() -> Estado`; `de_interpretacion(estado, interp: dict, firma_hoja: str) -> Estado` (fuentes/motivo por fila);
    `firma_parte(parte, hidden, roles, letters_off, escala, unir) -> str` (sha1 de un json ordenado);
    `marcar_cambios(estado, nuevas_firmas: dict[str, str]) -> Estado` (reconocida con otra firma → desactualizada);
    `puede(estado, parte) -> tuple[bool, str]` (VALVULAS siempre si fuentes>0; DIAMETROS exige ≥1 utilidad reconocida y
    su motivo nombra las que faltan); `orden_todo(estado) -> list[str]` (utilidades → VALVULAS → DIAMETROS → ROTULOS,
    solo las que `puede`); `a_dict(estado) -> dict` / `de_dict(d) -> Estado` (tolerante a claves faltantes).

- [ ] **Step 1: Tests**
  - `test_de_interpretacion_bloquea_utilidad_sin_capas`: interp sin capas de GAS → `filas["GAS"].estado == "bloqueada"` y
    motivo no vacío.
  - `test_estilos_sin_asignar_bloquea`: hoja sin capas, AGUA con 0 estilos asignados → bloqueada, motivo «asigna un estilo».
  - `test_capas_todas_ocultas_bloquea` (regla de `leyenda_estandar.sin_capas_visibles`).
  - `test_cambio_de_firma_desactualiza`: reconocida con firma A, `marcar_cambios` con B → `"desactualizada"`; con A → igual.
  - `test_diametros_necesita_una_utilidad` y `test_orden_todo`.
  - `test_ida_y_vuelta_dict` y `test_de_dict_viejo_sin_claves`.
- [ ] **Step 2:** `python scripts/pruebas.py tests/test_reconocer_estado.py` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Las pruebas pasan.

### Task 2: Interpretación de la hoja (trabajo PURO)

**Files:**
- Create: `app/hoja/interpretar_trabajo.py`
- Modify: `app/hoja/capas_trabajo.py` (sacar el cuerpo de `leer` a una función que reciba el `doc` abierto, sin cambiar
  `leer`)
- Modify: `PDF-a-CAD.spec`, `app/autoprueba.py`
- Test: `tests/test_interpretar_hoja.py`

**Interfaces:**
- Consumes: `capas_trabajo.leer`, `recognition.page_letters`, `estilos_sugeridos`, `simbolos_fuente`,
  `pdf_legend.document_legend`, conteo de rótulos (`recognition_anotaciones` memo por hoja), `vector_pipeline.detect_scale`.
- Produces: `interpretar(ruta: str, hoja: int, ons=(), estilos_ocultos=(), firma: str = "", progreso=None) -> dict` con
  claves `firma, layers, leyenda, visibles, sugeridos, letras, simbolos, rotulos_n, escala`. Corre dentro del retenedor de
  la Tarea 3 (deja la lectura abierta para los ▶). Objetivo de trabajo: `"hoja.interpretar_trabajo:interpretar"`.

- [ ] **Step 1: Tests**
  - `test_igual_que_capas_de_la_hoja`: en DU06 h.3 y Phoenix Water South h.4, `layers/leyenda/visibles/sugeridos` ==
    `capas_trabajo.leer(...)`.
  - `test_letras_iguales`: `letras` == `recognition.page_letters(doc[h])`.
  - `test_hoja_sin_capas_ni_leyenda_trae_sugeridos` (Southwest 37 si está en fixtures; si no, el sintético de
    `tests/test_estilos_sugeridos.py`).
  - `test_trabajo_en_el_spec` (nombre en `hiddenimports`).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS, más `python scripts/pruebas.py capas`.

### Task 3: Lectura retenida en el trabajador «reconocer»

**Files:**
- Create: `app/reconocimiento/lectura_retenida.py`
- Modify: `app/ui/comun/proceso.py` (`Trabajador(nombre, reciclar=True)`; «reconocer» con `reciclar=False` mientras
  retiene; `soltar_lectura()` lo vuelve a permitir)
- Modify: `app/reconocimiento/recognition_trabajo.py`
- Test: `tests/test_lectura_retenida.py`

**Interfaces:**
- Produces:
  - `abrir(ruta: str, firma: str) -> fitz.Document`: en el proceso, devuelve el doc retenido para `firma` (abre y entra en
    `lectura_unica` la primera vez; una firma distinta suelta la anterior). Máx. UNA firma retenida.
  - `soltar() -> None` (objetivo `"reconocimiento.lectura_retenida:soltar"`).
  - `recognition_trabajo.reconocer_parte(ruta, hoja, parte, firma, *, zoom, hidden_ocgs, roles_by_utility, letters_off,
    join_routes, scale_ft_per_pt, perfiles_de=(), resultados_previos=None, progreso=None) -> list[RecognitionResult] | dict`
    — utilidad → `[res]` con el mismo cuerpo del bucle de `reconocer_hoja` (letras de la interpretación retenida);
    `"VALVULAS"` → `{"valvulas": [...], "avisos": [...]}` (`_leer_valvulas` sobre `resultados_previos` o `[]`);
    `"DIAMETROS"` → aplica perfiles + `recognition_grosor_cruces.aplicar` sobre `resultados_previos` y los devuelve;
    `"ROTULOS"` → `{"anotaciones": [...]}`.
  - `reconocer_hoja` queda igual (lo siguen usando pruebas y «Agregar utilidad» hasta la Tarea 9).
- [ ] **Step 1: Tests**
  - `test_parte_igual_que_hoja_entera`: por utilidad en DU06 h.3/h.4/h.5 y DU08 h.22/h.26 y Phoenix South h.4, el resultado de
    `reconocer_parte` (comparado con el serializador de `scripts/rendimiento/reconocer.py --foto`) == el de
    `reconocer_hoja` para esa utilidad.
  - `test_valvulas_y_diametros_como_hoy`: utilidades + VALVULAS + DIAMETROS por partes == `reconocer_hoja` con todas.
  - `test_segundo_parte_no_relee`: contar llamadas a `page.get_drawings` (monkeypatch) → la 2.ª parte con la misma firma
    no lee.
  - `test_trabajador_muerto_relee_igual` (Review Focus 2): `proceso.trabajador("reconocer")._matar()` entre partes →
    resultado idéntico. Con `PDFCAD_PROCESO=1`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS + `python scripts/pruebas.py reconocimiento`.

### Task 4: Importar una parte encima de lo dibujado

**Files:**
- Create: `app/ui/ventana/ventana_importar_parte.py` (`ImportarParteMixin`)
- Modify: `app/ui/ventana/app_window.py` (heredar la mezcla), `app/reconocimiento/recognition.py`
  (`pipes_from_recognition` marca `pipe["reconocida"] = parte`)
- Test: `tests/test_importar_parte.py`

**Interfaces:**
- Consumes: `_import_recognized_pipes`, `nucleo.reconocer_mas.quitar_repetidas`, `ventana_valvulas._guardar_valvulas`.
- Produces: `Main.importar_parte(parte: str, resultado, reemplazar: bool = False) -> int` (nº de cosas agregadas; un solo
  `_push` antes; sin `respaldo_editor`). `reemplazar=True` quita antes las `pipes` con `reconocida == parte` (y sus
  estructuras ocultas), nunca las dibujadas a mano. VALVULAS → `_guardar_valvulas`; al importar una utilidad se vuelven a
  pegar las válvulas sin tubería (`valvulas.pegar`). DIAMETROS → actualiza `grosor`/`diam_plano` de las pipes ya importadas
  de esas utilidades (por `PIPE_IDX` de origen guardado en `pipe["reconocida_idx"]`).
- [ ] **Step 1: Tests** (ventana real offscreen, DU06 h.3):
  - `test_importar_agua_igual_que_el_flujo_viejo`: `importar_parte("AGUA", r)` en editor vacío → mismas pipes/estructuras
    que `_import_recognized_pipes([r])`.
  - `test_no_repite_lo_dibujado` y `test_un_paso_de_deshacer`.
  - `test_reemplazar_no_toca_lo_dibujado_a_mano` (Review Focus 1).
  - `test_valvulas_antes_que_su_red_se_pegan_despues`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS + `python scripts/pruebas.py editor`.

### Task 5: Panel «Reconocer» del riel

**Files:**
- Create: `app/ui/comun/panel_reconocer.py` (widget, sin lógica de ventana)
- Create: `app/ui/ventana/ventana_reconocer.py` (`ReconocerMixin`: conecta panel ↔ estado ↔ trabajos)
- Modify: `app/ui/ventana/ventana_shell.py` (`RIEL`: `("auto-fix", "Reconocer", 4, None)` tras «Revisión»; `PAGINAS` +
  «Reconocer»), `app/ui/ventana/ventana_shell_paneles.py`, `app/traduccion/i18n_en.py`
- Test: `tests/test_panel_reconocer.py`

**Interfaces:**
- Consumes: `nucleo.reconocer_estado` (Tarea 1).
- Produces:
  - `PanelReconocer(QWidget)` con `mostrar(estado: Estado)`, señales `reproducir(str)`, `ver(str)`, `capas(str | None)`,
    `todo()`, `cancelar()`, `interpretar()`. Una fila por parte: icono de estado, nombre, «N capas/estilos/símbolos» o motivo,
    ▶ (`setEnabled` NO: botón con aspecto apagado y el clic explica el motivo, como `ventana_dibujar._bloqueado`), 👁, ⋯
    (Capas y estilos…, Ajustar capas…, Unir tramos, Leer rótulos con IA en ROTULOS). Pie: «Último: …» y «k por verificar».
  - `Main.reconocer_estado: Estado` y `Main._refrescar_panel_reconocer()`.
- [ ] **Step 1: Tests**: filas y motivos según un `Estado` armado a mano; clic en ▶ bloqueado no emite `reproducir` y
  muestra el motivo; `test_nada_se_corta_al_ancho_minimo` (sumar la página a `tests/test_paneles.py`); claro/oscuro sin
  colores de utilidad para estados (memoria «colores sin choque»).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS + `python scripts/pruebas.py interfaz`.

### Task 6: ▶ en segundo plano (una parte y «Todo»)

**Files:**
- Modify: `app/ui/ventana/ventana_reconocer.py`, `app/ui/ventana/app_window.py` (sacar de `_start_recognition` lo de tarjeta
  de avance y `TrazadoProgresivo` a `_avance_reconocer(texto)` reutilizable)
- Modify: `app/reconocimiento/recognition_cache.py` (clave por parte = `firma_parte` + firma de hoja)
- Test: `tests/test_reconocer_fila.py`

**Interfaces:**
- Consumes: Tareas 1, 3, 4, 5.
- Produces: `Main.reconocer_parte(parte: str) -> None` (encola `proceso.Tarea("reconocimiento.recognition_trabajo:
  reconocer_parte", …)` en «reconocer»; avance y trazado provisional como hoy; al terminar `importar_parte` y fila
  «reconocida» con su firma; `verificar` = avisos con lugar de `recognition_summary.classify_warning` + `targets_for`);
  `Main.reconocer_todo()` (cola `orden_todo`); `Main.cancelar_reconocer()`. Fila «desactualizada» → pregunta «Reemplazar lo
  reconocido / Agregar lo que falta / Cancelar». Generación `_recog_generation` descarta lo tardío.
- [ ] **Step 1: Tests**: `test_play_agua_agrega_al_editor_sin_vista_previa`; `test_todo_respeta_el_orden`;
  `test_repetir_sin_cambios_usa_la_cache`; `test_cancelar_deja_el_editor_igual` (Review Focus 3);
  `test_resultado_tardio_tras_abrir_otro_proyecto_se_descarta` (Review Focus 4); `test_desactualizada_pregunta`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.

### Task 7: 👁 vista previa por fila y «Para verificar» guardados

**Files:**
- Modify: `app/ui/ventana/ventana_reconocer.py`, `app/ui/asistente/recognition_dialog.py` (modo `editor=True`: sin barra de
  pasos ni «Atrás»; botón principal «Importar»; «Ajustar capas…» y «Tramos unidos/sueltos» siguen)
- Modify: `app/ui/comun/panel_reconocer.py` (lista «Por verificar» con ir al lugar y ✔ revisado)
- Test: `tests/test_vista_previa_fila.py`

**Interfaces:**
- Produces: `Main.ver_parte(parte)`: si no hay resultado en caché, primero `reconocer_parte` sin importar; abre
  `show_recognition_preview(..., editor=True)`; Importar = `importar_parte`; «Ajustar capas…» = `_adjust_layer_roles`
  limitado a esa utilidad. Los «Para verificar» de `Fila.verificar` se recorren desde el panel con `_marcar_lugar`; ✔ se
  guarda en la fila.
- [ ] **Step 1: Tests**: la vista previa muestra lo mismo que hoy para ese resultado (`_curvas_quiebres` incluido); importar
  desde 👁 == ▶; los «Para verificar» siguen tras importar y tras guardar/abrir.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.

### Task 8: «Capas y estilos…» como vista central

**Files:**
- Create: `app/ui/ventana/ventana_capas_estilos.py` (`CapasEstilosMixin`)
- Modify: `app/ui/asistente/layer_dialog.py` (`SheetLayersDialog(..., editor=True)`: sin pasos, sin ◀ ▶ si la hoja es la
  del editor, botón «Aplicar» en vez de «Continuar»; el árbol, `layer_assignments`, `layer_sugeridos`, `layer_style_pick`,
  `layer_info_panel`, `layer_std_legend`, `layer_dialog_scale` y `layer_dialog_recog` sin cambio de lógica)
- Test: `tests/test_capas_estilos_editor.py`

**Interfaces:**
- Consumes: `incrustar_vista`/`mostrar_vista` (`ventana_shell`), la interpretación retenida (no relee la hoja si la firma
  coincide: le pasa `layers/leyenda/visibles/sugeridos` como hoy hace `capas_previas`).
- Produces: `Main.abrir_capas_estilos(parte: str | None = None)`; al aplicar actualiza `hidden_ocgs`,
  `_layer_roles_by_utility`, `_letters_off`, escala (`_calibrated_scale`) y llama `marcar_cambios` (filas desactualizadas o
  desbloqueadas). Abre filtrada en la utilidad de `parte`.
- [ ] **Step 1: Tests**: asignar un estilo en hoja sin capas desbloquea la fila; ocultar todas las capas de AGUA la bloquea;
  cambiar roles de una utilidad reconocida la deja «desactualizada»; el diálogo no llama `get_drawings` en la ventana con la
  interpretación retenida (como `test_agregar_sin_trabas`); `tests/test_asistente_sin_amontonar.py` incluye la vista.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS + `python scripts/pruebas.py capas`.

### Task 9: Flujo de apertura nuevo (sin «Capas» ni vista previa)

**Files:**
- Modify: `app/ui/ventana/app_window.py` (`_wizard_sheet_flow`: tras el paso 0 → `_interpretar_hoja()` y salir; `_change_page`
  → interpretar en vez de `_start_recognition`), `app/ui/ventana/ventana_agregar.py` (tras calcar/componer: interpretar solo
  el grupo nuevo; filas marcadas con su PDF), `app/ui/ventana/ventana_menu.py` y `ventana_panel_hoja.py` (quitar «Reconocer
  más capas de esta hoja…»; dejar el mixin hasta borrarlo en esta misma tarea si ninguna prueba lo usa)
- Create: `app/ui/ventana/ventana_interpretar.py` (`InterpretarMixin`)
- Test: `tests/test_flujo_abrir_interpretar.py`; actualizar las pruebas que esperan el paso «Capas»/vista previa al abrir
  (`test_composite_dialog`, `test_respaldo_editor`, `test_recognition_cache`, `test_agregar_utilidad`,
  `test_sewer_integration`, `test_gas_integration`, `test_telecom_integration`, `test_mapas_sin_capas`…) para que pasen
  por `reconocer_parte` en vez de la vista previa, con las MISMAS aserciones de resultado.

**Interfaces:**
- Produces: `Main._interpretar_hoja()` (Tarea `"hoja.interpretar_trabajo:interpretar"` en «reconocer», tarjeta de avance
  sin velo, al terminar `reconocer_estado = de_interpretacion(...)` y abre la página «Reconocer» del riel).
- [ ] **Step 1: Tests**: abrir PDF vectorial → editor con hoja, 0 pipes, panel con filas «pendiente»; escaneo → igual que hoy;
  ◀ ▶ → filas «pendiente» de la hoja nueva y sin vista previa; agregar utilidad → filas nuevas, el agua de antes intacta.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar y adaptar las pruebas listadas. **Step 4:** `python scripts/pruebas.py
  compositor capas reconocimiento utilidades mapas`.

### Task 10: Guardar, reabrir y proyectos viejos

**Files:**
- Modify: `app/project_io.py` (`reconocer_estado` = `a_dict` + interpretación liviana: `layers`, `leyenda` serializada,
  `sugeridos`, `escala`; sin lectura cruda), `app/ui/ventana/respaldo_editor.py` (`CLAVES` + `reconocer_estado`,
  `_interpretacion`), `app/ui/ventana/autoguardado.py` si copia campos a mano
- Test: `tests/test_reconocer_guardar.py`

**Interfaces:**
- Produces: al abrir un `.digproj` con estado → panel igual; sin estado → `Estado` con filas «sin_interpretar» salvo las
  utilidades presentes en `pipes` («reconocida», firma None) y botón «Interpretar la hoja».
- [ ] **Step 1: Tests**: ida y vuelta del estado; proyecto viejo (fixture de un .digproj existente en `tests/`) (Review
  Focus 5); primer ▶ tras reabrir relee una vez y da lo mismo.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.

### Task 11: Filas Diámetros y Rótulos completas

**Files:**
- Modify: `app/ui/ventana/ventana_reconocer.py`, `app/ui/comun/panel_reconocer.py`
- Test: `tests/test_reconocer_diametros_rotulos.py`

**Interfaces:**
- Produces: DIAMETROS muestra «N dudosas · M sin dato» (`diametro_plano.avisos`) y su motivo nombra utilidades sin
  reconocer; ROTULOS importa `anotaciones` (`_guardar_anotaciones`) y su ⋯ ofrece «Leer rótulos ilegibles con la IA…»
  (`anotaciones_ia`, la acción del menú IA).
- [ ] **Step 1: Tests**: perfiles de las hojas de origen en una compuesta (DU06 compuesta sugerida) dan los mismos
  diámetros que hoy; rótulos = los de `reconocer_hoja`. **Step 2–4** como siempre.

### Task 12: Medición final, manual y versión

**Files:**
- Modify: `docs/rendimiento/2026-11-16-linea-base-reconocer.md` (columna «después»), `app/nucleo/model.py` (`VERSION`,
  `CHANGELOG`), `app/docs/manual.es.html` + `manual.en.html` (capítulo «Reconocer desde el editor»; quitar «Reconocer más
  capas»), `CLAUDE.md` (sección del flujo), `gestion/funciones.toml` (función nueva, estado `propuesto`)
- [ ] **Step 1:** `flujo_reconocer.py` con los mismos PDF de la Tarea 0, A/B seguidos: tiempo hasta editor usable, tiempo
  de cada ▶, pausa máxima ≤ 1 s.
- [ ] **Step 2:** Fotos de igualdad: `reconocer.py --foto` (código anterior) vs `--comparar` (por partes) en DU06 h.3/4/5,
  DU08 h.22/26, Phoenix South h.4 y la compuesta de 36 → 0 diferencias.
- [ ] **Step 3:** Manual, CHANGELOG, versión, i18n (`python scripts/pruebas.py tests/test_i18n.py`).
- [ ] **Step 4:** `python scripts/verificar_instalador.py --estatico`.
