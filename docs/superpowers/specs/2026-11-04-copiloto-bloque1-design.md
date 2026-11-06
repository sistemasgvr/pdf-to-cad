# Copiloto del proyecto, Bloque 1 — diseño

Fecha: 2026-11-04. Rama: `dev_santos_v2`, sobre el commit `1aac4b4` (ya trae el perfil longitudinal, «No hay codo/T/Y/cruz», Resolver en la Vista 3D, la pantalla de inicio y la IA ↔ Civil 3D por MCP). Pedido del usuario: que el chat del Asistente actúe como agente y ahorre
tiempo, automatizando solo lo que tenga precisión; lo demás lo decide el usuario. Bloque 1 de 3 (2: análisis de todo el
proyecto en segundo plano y decisiones por patrón; 3: selección por consulta y recetas). Cada bloque tiene su
especificación y su plan.

## Objetivo

Llevar un proyecto recién importado hacia «listo para Civil 3D» desde el chat: saber qué falta, revisar los avisos sin
abrirlos uno por uno y resolver conflictos en tanda, con registro de todo lo que se hizo.

## Reglas fijas

1. Nada cambia el proyecto sin una confirmación del usuario en esa tarjeta, ni siquiera en tanda.
2. Las tandas solo contienen lo que MIDE la app. Lo que opina la IA va de uno en uno.
3. El Copiloto nunca mueve geometría ni borra.
4. Un aviso de normativa nunca se «arregla» cambiando datos para que cumpla: se aprueba con nota o se deja para
   que el usuario corrija el dato en el panel.
5. Los NÚMEROS los pone la app; la IA elige entre opciones ya validadas (regla de `docs/pendientes_ia.md`).
6. Sin servidor de IA funcionan igual el Estado, el nivel Seguro, Tu decisión y los conflictos en tanda. Solo el nivel
   Propuesta y las preguntas libres necesitan al modelo.

## Modelo

`qwen3.8:latest` en Ollama, con `think: false`. Medido el 2026-11-04 en el servidor del usuario, DU06 hojas 3, 4 y 10:
de 150 líneas con rótulos cerca, 143 las descarta la app en 0 s y 7 llegan al modelo; ~29 s por línea consultada,
0 propuestas equivocadas, 1 de 1 acierto con verdad conocida. Herramientas: llamada correcta en 7.4 s. Razonamiento
apagado: 49 s en una pregunta simple y falló la trampa. El diseño no depende del modelo: cualquiera con
`tools` sirve, y sin `tools` solo se pierde la pieza 5. La app ya usa `tools` de Ollama en la pestaña Civil 3D
(`ia/civil3d_agente.py`), con el mismo modelo.

## Entrada

En la pestaña **Chat** del Asistente, sobre la conversación, tres botones (la pestaña Civil 3D trabaja sobre el dibujo
abierto en Civil 3D y no cambia): **¿Cómo vamos?**, **Revisar avisos**, **Resolver conflictos**.

`ia/copiloto_intencion.py` (PURO) `intencion(texto)` → `estado | revision | conflictos | None`, por palabras, sin
modelo. «dime cuántos avisos tengo y empecemos a solucionarlos» → `revision`, que empieza mostrando el Estado.
«soluciona los conflictos» sin código C-n → `conflictos`; con código sigue siendo la orden `resolver_conflicto` de
siempre. `None` → el camino de siempre.

`PreguntaDialog.enviar` mira la intención ANTES de exigir proveedor: hoy corta si la IA no está configurada, y la regla
6 pide que el Copiloto funcione igual. Inyección y código (`ia/alcance`) se bloquean antes, como hoy.

## Piezas

### 1. Estado del proyecto

`nucleo/copiloto_estado.py` (PURO) `armar(pipes, conflictos, avisos, aprobados)` → `Estado` con grupos en orden de
prioridad: conflictos; diámetro del plano (`grosor`); sin tipo (`tipo`); demás avisos de normativa por clase. Cada
grupo: clave, título, cantidad pendiente, cantidad aprobada. `listo` = sin pendientes. Se excluyen `info`, `aprobado` y
la clase `angulo` (oculta por decisión del usuario).

La ventana llama `_resultados_al_dia()` antes de armar. La tarjeta se pinta en `ia_chat_html`; cada grupo es un enlace
`cop:revisar:<clave>` o `cop:conflictos`. Sin modelo: al instante.

### 2. Revisión guiada

`nucleo/copiloto_cola.py` (PURO) `clasificar(avisos, pipes, ...)` → `Cola` con `Item(clave, aviso, nivel, opciones)`:

| Nivel | Qué entra | Trabajo |
|---|---|---|
| `seguro` | `grosor` con una sola opción de continuidad de fuerza «alta» y permitida por la normativa; `tipo` cuando la utilidad tiene un único tipo posible en el catálogo | Una tarjeta con casillas y una confirmación; un paso de deshacer |
| `propuesta` | `grosor` con rótulos cerca que `ia/diametro_ia` no descarta | Una línea a la vez: aprobar, otro valor, saltar |
| `decision` | `grosor` sin evidencia; `tipo` con varios posibles; toda clase de normativa | Por grupos de (clase, mensaje sin cifras de lugar): aprobar con nota, o abrir cada caso |

Quedan en `decision`, nunca en `seguro`: utilidades con bancoducto y utilidades cuya familia no tiene ese tamaño (la
misma comprobación de `_diam_ia_aplicar`).

Línea por línea:
- `_ir_a_elemento(x, y, "pipe", i, activar=False)`: el Asistente sigue abierto.
- La tarjeta muestra propuesta, motivo, criterio y fuente, igual que la del inspector.
- Mientras el usuario decide, se pide en un hilo la sugerencia del SIGUIENTE ítem `propuesta` (solo uno adelantado). Se
  usa `DI.sugerir` y su caché, sin depender de la selección actual; el recorte y `fitz` se preparan en la ventana,
  como hace `_diam_ia_imagen`.
- Antes de mostrar un ítem se comprueba que su aviso sigue pendiente; si no, se salta sin decir nada.
- Aprobar y «otro valor» aprenden igual que hoy (`DR.aprender`, `DI.aprender_error`).

Estado de la revisión: `Main.revision` = `{"saltados": [claves]}`, con `normas_aprobacion.clave`. Va al .digproj y a
`respaldo_editor.CLAVES`; se vacía en `_reset_model`. Una clave vieja que ya no coincide se ignora. Retomar = volver a
clasificar y saltar `saltados`; «Volver a ver los saltados» los vacía.

Costo en proyectos grandes: `diametro_continuidad.analizar` recorre todas las utilidades en cada llamada; con 16 761
sería todo contra todo. `analizar` recibe un índice por (capa, ab) armado una vez, con el mismo resultado, y `clasificar`
corre por pasos en `TrabajoPasos` con la tarjeta de avance y «Cancelar».

### 3. Conflictos en tanda

`ui/ventana/ventana_copiloto_conflictos.py`:
1. Para cada conflicto, `soluciones_de(cid)`; conserva el que tiene propuesta válida. Por pasos, con avance y Cancelar.
2. Tarjeta en el chat: una fila por conflicto con casilla DESMARCADA, código con enlace, qué cambia («Bajar AGUA-5
   0.50 ft») y lo que además resuelve. Botón **Marcar todas las limpias**, **Aplicar las marcadas (N)**.
   Los conflictos sin propuesta válida se cuentan aparte, con enlace a «Resolver conflictos».
3. Aplicar: un solo `_push`. En orden, antes de cada propuesta se repite `_validar_propuesta(c, p)` con `_sol_antes`
   vacío, sobre `self.pipes` ya modificado: solo recalcula la zona y no necesita redibujar. Si dejó de ser válida o
   ya no resuelve, se salta y se reporta. Un solo redibujo al final. El conflicto `c` y su número C-n son los de la
   lista inicial.

Conflicto causado por un accesorio (`accesorio_de_conflicto(c.id)` no es None): solo el usuario sabe si ese codo, T, Y o
cruz existe, así que nunca lleva casilla. Va en la lista aparte, con enlace a «Resolver conflictos», donde está «No hay…».

Las casillas empiezan desmarcadas porque cambiar la cota de una red existente es una decisión de ingeniería: la app
prueba que queda limpio, no que la tubería esté a esa cota.

Las casillas de la tarjeta son enlaces (`cop:marca:<i>`) con icono, porque el chat es un `QTextBrowser` sin controles.

### 4. Bitácora

`nucleo/bitacora.py` (PURO): `agregar(lista, tipo, resumen, detalle, usuario, fecha)`. Cada entrada: id, tipo (`tanda`,
`decision`, `aprobacion`, `conflictos`), resumen, detalle por elemento (código, antes, después, por qué, evidencia),
usuario, fecha, `deshecha` (bool).

`Main.bitacora`: lista en el .digproj (`project_io`) y en `respaldo_editor.CLAVES`, como `Main.perfiles`. El registro
sobrevive a Ctrl+Z: la lista NO se restaura al deshacer. `_snap_state` guarda solo `bitacora_vigentes`, la tupla de ids
de entradas vigentes en ese paso; `_restore` pone `deshecha = id no está en vigentes`. Así deshacer y rehacer la marcan
y desmarcan sin ambigüedad, también si después hubo otra tanda. Se ve en una tarjeta «Bitácora» del chat (enlace
`cop:bitacora`) con las últimas entradas. «Deshacer» solo aparece en la entrada que es el último paso de deshacer:
revertir una tanda vieja dejando lo posterior podría romper lo que vino después.

Es el registro del proyecto en la app. Los cambios hechos en Civil 3D siguen en su propio `<dwg>.pdfcad-ia.jsonl`. Se
usan los mismos conceptos: quién, origen, cuándo, antes/después y motivo.

Cada tanda es un `_push`. Usuario = `normas_aprobacion._usuario()` (se hace pública como `usuario()`).

### 5. Investigación con herramientas

No se agrega nada a `Proveedor`: se reutiliza `ia/civil3d_agente.Agente`, que ya tiene el bucle de herramientas, el tope
de pasos y `pedir_ollama`. `Agente` solo pide un `cliente` con `herramientas()` y `llamar(nombre, args)`, y gana un
argumento opcional `sistema` (por defecto su `SISTEMA` de siempre: Civil 3D no cambia).

`ia/herramientas.py` (PURO): `ClienteProyecto(datos)` es ese `cliente` para el proyecto de la app, de solo lectura sobre
`DatosProyecto`: `buscar_lineas(utilidad, sin_diametro, sin_tipo)`, `ver_ficha(codigo)`, `listar_avisos(clase)`,
`listar_conflictos()`. Cada una devuelve texto compacto con tope de 40 filas; un argumento desconocido devuelve
`(False, texto)`, nunca excepción. No hay herramientas de cambio: la `Agente` del proyecto no puede modificar nada.

`ia/consulta.preguntar` usa el agente si el modelo tiene la capacidad `tools` (`Proveedor.herramientas()`, como
`vision()`), con `max_pasos=4`. Si no, va por el camino de siempre. El texto final pasa por `alcance.salida_valida` y
`no_respaldados`, con las salidas de las herramientas sumadas a los datos. `pedir_ollama` suma `keep_alive` «30m»,
como el resto de la app: hoy el modelo se descargaría antes. La respuesta llega completa, sin escribirse en vivo; la
tarjeta muestra «Consultando…» con `al_paso`.

## Cambios en lo existente

| Archivo | Cambio |
|---|---|
| `app/ia/proveedor.py` | `herramientas()` como `vision()` |
| `app/ia/civil3d_agente.py` | `sistema` opcional en `Agente`, `keep_alive` en `pedir_ollama` |
| `app/ia/consulta.py` | usa `Agente` con `ClienteProyecto` |
| `app/ui/dialogos/ia_chat.py` | botones rápidos, intención antes de exigir proveedor, enlaces `cop:` |
| `app/ui/dialogos/ia_chat_html.py` | tarjetas del Copiloto (en un módulo nuevo si pasa de 500 líneas) |
| `app/nucleo/diametro_continuidad.py` | índice opcional, mismo resultado |
| `app/nucleo/normas_aprobacion.py` | `usuario()` pública |
| `app/project_io.py`, `app/ui/ventana/app_window.py`, `respaldo_editor.py` | `bitacora`, `bitacora_vigentes`, `revision` |
| `app/nucleo/model.py`, `i18n_en*.py`, `app/docs/manual.*.html` | historial, traducción y manual |

Nuevos: `ia/copiloto_intencion.py`, `ia/herramientas.py`, `nucleo/copiloto_estado.py`, `nucleo/copiloto_cola.py`,
`nucleo/bitacora.py`, `ui/ventana/ventana_copiloto.py` (`CopilotoMixin`), `ui/ventana/ventana_copiloto_conflictos.py`,
`ui/dialogos/ia_chat_copiloto.py` (mezcla de `PreguntaDialog`, como `OrdenesMixin`).

Regla de capas: `nucleo` e `ia` no importan Qt. Un proyecto viejo sin `bitacora` ni `revision` abre igual.

## Errores

- Servidor caído en mitad de una revisión: el ítem pasa a `decision` con «la IA no respondió» y la revisión sigue.
- Respuesta de la IA que no pasa `comprobar`: se trata como sin certeza.
- Fallo al aplicar una tanda: `_restore` del paso recién creado; no quedan cambios a medias, se dice en el chat y no
  se anota como hecha.
- Cancelar durante clasificar o probar: no cambió nada.

## Pruebas

- Puras: intención, Estado, clasificación por nivel (bancoducto, familia sin tamaño, normativa nunca en `seguro`),
  bitácora, herramientas, `analizar` con índice igual a sin índice en un proyecto real.
- Ventana (`tests/test_copiloto*.py`, Ollama simulado): nada cambia sin confirmar; una tanda = un Ctrl+Z; la bitácora
  sobrevive y marca `deshecha`, también tras otra tanda; retomar respeta los saltados; conflictos en tanda con revalidación y sin casilla si los causa un accesorio; sin servidor
  funcionan Estado, seguro y conflictos; el Asistente sigue abierto al recorrer líneas.
- Medición al terminar: `audit_diametro_ia` con qwen3.8 (0 equivocadas), y pausas de la ventana con AGUA 2 (ninguna
  mayor a ~1 s por el Copiloto).

## Fuera de este bloque

Análisis de todo el proyecto en segundo plano, decisiones por patrón, selección por consulta, recetas, bitácora en el
Informe, conexión con Claude. Sin cambios en el reconocimiento, el DXF, el plugin ni la pestaña Civil 3D. El Copiloto no consulta Civil 3D.
