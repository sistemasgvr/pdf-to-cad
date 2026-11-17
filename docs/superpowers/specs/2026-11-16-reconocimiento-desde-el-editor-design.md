# Reconocimiento desde el editor — diseño

Fecha: 2026-11-16 · Pedido del usuario (rama `dev_santos_v2`).

## Intención y por qué

Abrir un PDF grande tarda demasiado. Una composición de 36 a 54 mapas, o agregar una segunda utilidad a una hoja de 36
mapas, deja al usuario esperando minutos antes de poder trabajar. La espera viene de reconocer todo de una sola vez:
todas las utilidades, válvulas, diámetros y perfiles.

El usuario quiere:

1. **Entrar rápido al editor.** Al abrir solo se compone la hoja y se **interpreta todo lo que el PDF trae**: capas o
   estilos, letras del linetype, leyenda, rótulos y símbolos. No se reconoce ninguna utilidad todavía.
2. **Reconocer por partes, cuando él quiera.** Desde el editor, un panel «Reconocer» lista todo lo que se puede
   reconocer, con un ▶ por fila. Cada ▶ reconoce solo esa cosa, en segundo plano, y el resultado entra al plano solo.
3. **Revisar si quiere.** La vista previa, el resumen y los «Para verificar» se abren desde la fila (👁). No son un paso
   obligatorio.

Éxito = con la compuesta de 36 mapas (Phoenix agua) el editor queda usable en una fracción del tiempo de hoy. Agregar
alcantarillado solo paga la lectura del PDF nuevo y el reconocimiento que se pida.

## Metas

- Flujo de apertura: **Componer hoja → interpretar → editor**. Se saca el paso «Capas de la hoja» y la vista previa
  obligatoria.
- Panel **Reconocer** en el riel (junto a Hoja y PDF, Revisión…), con estas filas:
  - **Utilidades:** una fila por utilidad soportada (Eléctrico, Telecom, Drenaje, Alcantarillado, Agua, Gas), con sus
    capas o estilos detectados. Si no hay nada de una utilidad, la fila lo dice y su ▶ queda apagado.
  - **Válvulas.**
  - **Diámetros:** grosor del plano, rótulos de diámetro y perfiles de laterales.
  - **Rótulos del plano:** multileaders y MText.
  - **▶ Todo**, en el orden correcto.
- Cada fila tiene su estado (pendiente / reconociendo % / reconocida N / con observaciones), ▶ y 👁.
- El ▶ corre en el proceso de fondo con «Cancelar» y no bloquea la ventana. Durante el trabajo se ven las líneas
  provisionales, como hoy. Al terminar, el resultado entra **encima** de lo dibujado sin repetir líneas (lo que ya hace
  «Reconocer más capas», `nucleo.reconocer_mas`) y con UN paso de deshacer.
- La lectura de la hoja **se hace una sola vez** por proyecto abierto y la reusan todos los ▶.
- «Agregar utilidad» desde otro PDF: calca y compone como hoy, interpreta **solo el PDF nuevo** y sus filas aparecen en
  el mismo panel, sin reconocer nada solo.

## No metas

- Bajar el tiempo de los algoritmos de reconocimiento en sí. Eso va por las tareas de `docs/rendimiento/GUIA.md`.
- Reconocer por pieza de origen y unir costuras (la opción C de la conversación). Queda para después, si la medición lo
  justifica.
- Cambiar el flujo de escaneos (`Composite.manual`): sigue igual.

## Anti-metas (fallaría aunque funcione)

- Que un ▶ dé un resultado **distinto** al reconocimiento de hoy para la misma hoja, utilidad, capas y roles. Las líneas,
  codos, bóvedas, válvulas y diámetros deben salir iguales (foto antes/después).
- Que algo que hoy se interpreta se pierda: leyenda, letras, roles por leyenda, escala calibrada, capas ocultas, etc.
- Que la ventana se congele más de 1 s seguido al abrir o al reconocer.
- Que reconocer una utilidad borre o mueva lo que el usuario ya dibujó o editó.
- Que el panel sea un muro de texto: estado con iconos y cifras (ver memoria «UI: menos texto»).

## Restricciones

- **Memoria.** La lectura cruda (`pdf_styles.drawings` de 36 mapas) pesa ~1 GB. No va a disco ni al `.digproj`. Vive en
  el trabajador «principal» (`ui.comun.proceso`) mientras el proyecto está abierto. Se suelta al cerrar o abrir otro
  proyecto, al cambiar la composición o si el trabajador se recicla. Ahí el próximo ▶ vuelve a leer, una sola vez.
- **Persistencia liviana.** La interpretación (lista de capas, leyenda leída, letras por capa, roles, escala, rótulos y
  símbolos con su ubicación) va al `.digproj` y a `respaldo_editor.CLAVES`, con la firma de la hoja (composición + sha1
  de los PDF + capas ocultas). Si la firma cambia, se interpreta de nuevo.
- **Dependencias entre filas:**
  - Válvulas: hoy `completar` y `ramales` necesitan las líneas, y `pegar` las une al importar. El ▶ de Válvulas se
    puede correr siempre. Sin líneas de su red, sus válvulas quedan «sin tubería» (rojo, como hoy) y se vuelven a pegar
    cuando se reconoce la utilidad.
  - Diámetros (`recognition_grosor_cruces.aplicar`) necesita TODAS las utilidades reconocidas a la vez. La fila se
    habilita con al menos una utilidad reconocida y avisa cuáles faltan.
  - El grosor/diámetro que hoy sale DENTRO de `recognize_page` sigue saliendo con su utilidad, para no cambiar
    resultados. La fila Diámetros solo hace lo que es entre utilidades (perfiles, cruces) y vuelve a aplicar lo dudoso.
- **La herramienta Reconocer es el ÚNICO lugar para todo lo de capas y estilos** (pedido del usuario). Ahí está todo lo
  que hoy hace «Capas de la hoja», para hojas con capas y sin capas:
  - Ver las capas o estilos de cada utilidad, en un árbol por utilidad y tipo (líneas, estructuras, válvulas), con su
    muestra de leyenda.
  - Resaltarlas en el plano del editor con un clic: halo del color de la utilidad y el resto atenuado, como hoy en
    «Capas».
  - Elegir qué capas o estilos entran en el reconocimiento de cada utilidad: casillas, mostrar/ocultar y «Ver solo
    esta».
  - **Hojas sin capas:** asignar a cada estilo de trazo su utilidad y su rol. Si la leyenda lo resuelve, queda asignado
    al interpretar y se puede corregir. Si no, la fila lo pide, y su ▶ se habilita cuando hay al menos un estilo
    asignado.
  - Roles a mano («Ajustar capas…»), letras del linetype activas o no (tarjetas «Por las letras de su línea»), leyenda
    del plano y del PDF, y escala (calibrar con dos clics o escribirla).
  - La vista previa de cada fila.

  Formato: el panel del riel muestra la lista con ▶ y 👁. Un «Capas y estilos…» por fila, o uno general, abre la vista
  completa en el centro de la ventana, a pantalla completa, como Normativas o Tabla de datos. Esa vista reusa los widgets
  de hoy (`layer_dialog`, `layer_assignments`, `layer_std_legend`, `layer_info_panel`, `layer_dialog_scale`) sobre el
  plano del editor. «Capas ▾» de la barra sigue siendo solo encender/apagar lo dibujado y los planos, sin cambio.
  Cambiar capas o estilos de una utilidad ya reconocida la marca «desactualizada»: su ▶ ofrece reconocer de nuevo.
- Archivos < 500 líneas; lógica pura en `app/nucleo` / `app/reconocimiento`; textos con `t()`; manual y CHANGELOG al día.

## Flujo nuevo, de punta a punta

1. **Abrir el PDF** → `detect` como hoy. Si es un escaneo, va al compositor de escaneos y al dibujo a mano, sin cambios.
   El panel dice «Hoja escaneada: no hay nada que reconocer».
2. **Componer hoja**, como hoy, con composición sugerida, área sugerida, esquinas libres y fundir. Al aceptar se arma la
   hoja y empieza la **interpretación** en el trabajador. Una tarjeta de avance muestra la etapa: capas, letras,
   leyenda, estilos sugeridos, rótulos, símbolos.
3. **Editor**, apenas la hoja está dibujada. La interpretación termina en segundo plano y el panel Reconocer se llena
   solo. Cada fila muestra cuántas capas, estilos o símbolos encontró, o un motivo si no puede: «sin capas de esta
   utilidad», «asigna un estilo», «todas sus capas apagadas».
4. **Reconocer** (panel del riel):
   - ▶ de una fila: la reconoce en segundo plano con avance y Cancelar. Se puede acercar y desplazar el plano. Al
     terminar entra al plano encima de lo que había, sin repetir líneas, en un paso de deshacer.
   - ▶ Todo: hace las filas en cola, en el orden utilidades → válvulas → diámetros → rótulos.
   - 👁: abre la vista previa de esa fila, con su resumen y sus «Para verificar». Si no estaba reconocida, primero la
     reconoce. «Importar» desde ahí = ▶.
   - «Capas y estilos…»: abre la vista completa en el centro de la ventana (ver arriba).
5. **Cambiar de hoja** (◀ ▶ del editor en un PDF de varias hojas): se interpreta la hoja nueva y el panel vuelve a
   «pendiente». Ya no se reconoce sola ni se abre la vista previa.
6. **Agregar utilidad desde otro PDF:** calcar y componer como hoy. Se interpreta solo el PDF nuevo y sus filas
   aparecen en el panel, marcadas con su PDF de origen.
7. **Guardar y reabrir:** la interpretación y el estado de cada fila viajan en el `.digproj`. La lectura cruda se rehace
   una vez, con el primer ▶.

## Funciones de hoy y a dónde van

| Función de hoy (dónde está) | En el flujo nuevo |
|---|---|
| Elegir utilidades a reconocer (tarjeta «Reconocer» de Capas) | Filas del panel, una por utilidad |
| Ver, resaltar, encender y apagar capas; buscador; «Ver solo esta» (árbol de Capas) | «Capas y estilos…» |
| Asignar estilos a utilidad y rol en hojas sin capas (`layer_assignments`) | «Capas y estilos…» |
| Estilos sugeridos sin capas ni leyenda (`estilos_sugeridos`, Southwest) | Interpretación; vienen asignados y la fila dice el motivo si no se pudo |
| Elegir un estilo con un clic en su tinta (`layer_style_pick`) | «Capas y estilos…», sobre el plano del editor |
| Símbolos de fuente ESRI como capas virtuales (`simbolos_fuente`) | «Capas y estilos…», rol Válvulas; fila Válvulas |
| Leyenda del mapa, del PDF y estándar BOE; tarjetas «por las letras» | «Capas y estilos…», panel Leyenda |
| Aviso «utilidad con todas sus capas ocultas» (`layer_dialog_recog`) | Motivo en la fila y ▶ apagado |
| Escala: calibrar o escribir (`layer_dialog_scale`) | «Capas y estilos…» y Hoja y PDF |
| «Ajustar capas…» (roles a mano) de la vista previa | En la fila de cada utilidad |
| «Unir tramos / tramos sueltos» (pie de la vista previa) | Opción en la fila de la utilidad (y en la vista previa) |
| Resumen, cobertura, «Para verificar» con ir al lugar y ✔ revisado | 👁 de la fila. Además, los «Para verificar» de cada fila se GUARDAN y se recorren desde el panel aunque ya esté importada (hoy se pierden al importar) |
| Curvas de los quiebres en la vista previa (`recognition_quiebres`) | Igual, en el 👁 |
| Caché del reconocimiento (`recognition_cache`) | Por utilidad: un ▶ sin cambios no reconoce de nuevo |
| Cancelar = editor como estaba (`respaldo_editor`) | Cancelar un ▶ no toca el editor; después de importar, Ctrl+Z |
| «Reconocer más capas de esta hoja…» | Absorbido por el panel; se quita del menú |
| ◀ ▶ del editor reconocía la hoja nueva y abría la vista previa | Interpreta la hoja nueva; el panel queda en pendiente |
| Perfiles de laterales de las hojas de origen (`perfiles_de`) | Fila Diámetros |
| Leer rótulos ilegibles con la IA (menú IA) | Acción en la fila Rótulos (sigue también en el menú IA) |
| Diámetro según la IA (tarjeta del inspector) | Sin cambio; la fila Diámetros muestra cuántas líneas quedan dudosas o sin dato |
| Bóvedas, buzones, sólidos, acometidas, codos y quiebres → curvas | Siguen saliendo con su utilidad, como al importar hoy |
| «Organizar hojas» (`organized_*`, ya fuera del menú) | Sin cambio; solo proyectos viejos |

## Enfoques considerados

- **A. Lectura guardada + reconocer desde el editor** — ELEGIDO. El cambio de flujo es grande, pero entra rápido al
  editor, no reconoce lo que no se usa y no lee el PDF dos veces.
- **B. El mismo flujo, en segundo plano.** Entrar al editor después de «Capas» y que las utilidades aparezcan solas.
  Cambia poco, pero el tiempo total no baja y se sigue reconociendo todo. Su parte buena (no esperar) queda dentro de A.
- **C. Reconocer cada hoja de origen y unir costuras.** Es lo que más ahorra al recomponer. También es lo más riesgoso:
  cambia los resultados en las uniones. Se deja para después.

## Decidido con el usuario

- Enfoque A, con el reconocimiento en segundo plano.
- Se quita el paso «Capas de la hoja» del flujo de apertura. Todo su contenido (ver, resaltar y elegir capas, asignar
  estilos en hojas sin capas, roles, letras, leyenda, escala) se maneja desde la herramienta Reconocer.
- Botón «Reconocer» en el riel con la lista, ▶ por fila y vista previa opcional desde la fila.
- El resultado se actualiza solo en el editor.

## Decisiones del diseñador (corregibles)

- Primer trabajo del plan: **medir por etapas** el caso real (Phoenix agua 36 mapas → agregar alcantarillado) con
  `scripts/rendimiento/` (componer, capas, reconocer, importar), antes y después, en el mismo rato.
- La «interpretación» = lo que hoy calculan `pdf_layers.page_layers`, `page_letters`, `leyenda_mapa`/`pdf_legend`,
  `trazos_visibles`, rótulos (`recognition_grosor_texto`/anotaciones, memo por hoja) y símbolos de válvulas. Corre en
  `hoja/capas_trabajo.leer` ampliado, en el trabajador, con `lectura_unica` abierta y retenida.
- Retener la lectura: el trabajador guarda (documento abierto + caché de `lectura_unica`) por firma de hoja; la llamada
  `recognition_trabajo.reconocer_hoja` acepta reutilizarla. Esto exige que nada modifique las listas de `drawings` (ya es
  regla) y que el estado de capas del documento no cambie entre ▶ (se filtra por nombre, como hoy).
- Un ▶ a la vez; ▶ Todo = cola en el orden utilidades → válvulas → diámetros → rótulos. Mientras corre se puede navegar,
  pero no editar (lo de hoy: `_recognition_readonly`).
- La caché de reconocimiento (`recognition_cache`) pasa a guardar por utilidad: un ▶ repetido sin cambios no reconoce de
  nuevo.
- Importar = `_importar_mas` (reponer nada, solo agregar sin repetidas). Una utilidad ya reconocida que se vuelve a
  reconocer pregunta: reemplazar lo de esa utilidad o agregar solo lo que falta.
- La vista previa (👁) reusa `RecognitionPreviewDialog` con el resultado de esa fila. «Importar» desde ahí es igual que el
  ▶. Si se abre antes de reconocer, primero reconoce.
- Proyectos viejos (`.digproj` sin interpretación): al abrir no se interpreta nada. El panel muestra «Interpretar la
  hoja» y lo ya importado queda como «reconocida».
- `Main._wizard_sheet_flow` termina después del paso 0. «Reconocer más capas» queda absorbido por el panel (se quita del
  menú y el código se reutiliza).

## Lo que queda al constructor

- Nombres de clases y módulos (sugerencia: `ui/ventana/ventana_reconocer.py`, `nucleo/reconocer_estado.py`,
  `hoja/interpretar_trabajo.py`).
- Cómo partir `recognize_page` para Válvulas/Rótulos sin cambiar resultados (hoy salen dentro del trabajo por hoja).
- Diseño visual del panel siguiendo `ventana_shell_paneles` y las memorias de UI.
- Pruebas: foto antes/después (`--foto/--comparar`) en DU06 h.3/4/5, DU08 h.22/26, Phoenix agua h.4 y una compuesta.
  Prueba de ventana: abrir PDF → editor sin reconocer → ▶ Agua → mismas líneas que el flujo viejo.
