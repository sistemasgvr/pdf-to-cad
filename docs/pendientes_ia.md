# IA en PDF-a-CAD: qué hay y qué falta

- Pruebas: Ollama + `qwen3-vl:8b` en la PC de la oficina («localollama», RTX 4060), por Tailscale
  (`http://100.64.200.58:11434`). Conviene la variante sin razonamiento (`qwen3-vl:8b-instruct`): la que piensa
  tarda ~45 s por respuesta.
- Producción: Claude Sonnet 5.5 (`claude-sonnet-5-5`).

**Regla de oro: los NÚMEROS los pone la app; la IA solo redacta.** Lo que escribe se revisa contra los datos y,
si falla o no responde, sale la plantilla.

## Hecho (MVP, 2026-10-23: puntos 1, 2 y 3 + explicar normativas)

Todo en `app/ia/` (PURO, sin Qt) y la ventana en `ui/ventana/ventana_ia.py` + `ui/dialogos/ia_*.py`.

| Módulo | Qué hace |
|---|---|
| `ia/proveedor.py` | `Config` (QSettings `ia/proveedor`, `ia/url`, `ia/modelo`, `ia/paralelo`), interfaz `Proveedor` (`chat`, `modelos`, `probar`) y `Ollama` (HTTP con la biblioteca estándar, respuesta en trozos). |
| `ia/memoria.py` | Lo que la IA aprende del proyecto, en TEXTO PLANO junto al .digproj (ver abajo). |
| `ia/contexto.py` | Los datos reales del proyecto en texto compacto + `seleccionar(pregunta)` (códigos, zona, utilidad, palabras). |
| `ia/consulta.py` | «Pregúntale al proyecto»: pedido = enseñanzas + resumen + lo que viene al caso; respuesta con referencias al plano y cifras sin respaldo marcadas. |
| `ia/redactor_ia.py` | El Informe automático redactado por la IA, por lotes por zona, en paralelo, con revisión de cifras y lo ya redactado guardado. |
| `ia/texto.py` | Números de un texto, normalizar, JSON. |

### 1. Informe automático redactado por la IA

- Herramientas → «Informe automático…»: si en IA → «Configurar IA…» hay un servidor, la IA redacta el resumen, el
  párrafo de cada zona y cada ficha.
- Recibe cada ficha como JSON (`informe_redaccion.datos_para_ia` + «sugerencia» de la plantilla) y devuelve
  `{"zona": …, "fichas": {ID: texto}}`.
- Cada texto se revisa: no vacío, no muy largo, y sin cifras que no estén en su ficha. Si no pasa, esa ficha sale
  con la plantilla.
- La fuente y la aprobación las agrega la app siempre.
- Lo redactado queda en `redaccion.jsonl`: repetir el informe no vuelve a preguntar. Sin servidor, se usa lo ya
  redactado y la plantilla para lo demás.
- La barra tiene la etapa «La IA redacta el informe: parte i de n», con «Cancelar».

### 2. «Pregúntale al proyecto» (menú IA, Ctrl+Shift+I, botón de la barra)

- Es un chat. La respuesta aparece mientras se escribe y cada código (C-12, N-3, AGUA-5) lleva al plano.
- Si la respuesta trae cifras que no están en los datos, se avisa debajo.
- Debajo de cada respuesta: «Útil», «No útil», «Corregir…». Aparte, «Enseñarle algo…» deja una regla del proyecto.

### 3. Resolver conflictos (menú IA → «Resolver conflictos…», o clic derecho junto a una marca C-n)

- La APP propone (`nucleo/soluciones.py`):
  - **Cruce/choque a la misma cota:** bajar o subir UNA de las dos utilidades entera, lo justo para que no se toquen.
    Si las normativas piden una separación vertical entre esas utilidades, también se propone con esa separación.
  - **Escalón:** igualar la salida a la llegada o al revés.
- La app PRUEBA cada propuesta en una copia de la zona (`ui/ventana/ventana_soluciones.py`), con el mismo cálculo
  del plano. Vale si el conflicto desaparece y no aparece ningún conflicto, aviso de normativa ni unión de la red
  rota.
- La IA (`ia/soluciones_ia.py`) solo elige entre las válidas y explica por qué. Responde
  «RECOMENDADA: Pn» + explicación; si nombra una que no vale, se toma la mejor de la app; si escribe cifras que no
  están en los datos, sale la recomendación de la app.
- La respuesta queda en `redaccion.jsonl` del proyecto: el mismo caso no se vuelve a preguntar.
- «Aplicar» = un paso de deshacer. Lo aplicado queda como enseñanza «solucion» para los casos siguientes.
- Otros conflictos (5+ tuberías, tramos cortos entre codos…) se arreglan cambiando el dibujo: sin propuesta
  automática, solo la explicación.

### Normativas: «¿Qué significa esta regla?»

- En Normativas → Reglas, elige una fila y pulsa «Explicar con IA» (`ia/explicar_norma.py`,
  `ui/dialogos/normas_ia_panel.py`).
- La respuesta se guarda en `%APPDATA%/pdf-to-cad/ia/redaccion.jsonl`, junto al catálogo, porque las reglas valen
  para todos los proyectos. La clave son las celdas de la regla + el idioma:
  - la misma regla no se vuelve a pedir (aparece al elegirla);
  - si cambia cualquier celda, se puede pedir de nuevo.
- Las cifras que no estén en la regla se marcan.

### Memoria («aprendizaje») del proyecto

```
Mi proyecto.digproj
Mi proyecto - IA/
    LEEME.txt
    ensenanzas.jsonl       notas, correcciones y respuestas valoradas
    conversaciones.jsonl   historial de preguntas
    redaccion.jsonl        textos del informe ya redactados
```

- JSONL = una línea JSON por registro (se lee con el Bloc de notas).
- Sin proyecto guardado, queda en memoria y se escribe al guardar. «Guardar como…» copia la carpeta.
- La IA NO se reentrena: antes de cada consulta, `Memoria.buscar` trae las enseñanzas parecidas y van en el pedido.

## Pasar a Claude (producción)

1. Escribir `class Anthropic(Proveedor)` en `ia/proveedor.py`, con la misma interfaz:
   - `chat(mensajes, sistema, json, al_texto, maximo, cancelado)` → `Respuesta`, usando la Messages API con
     streaming;
   - `modelos()` y `probar()`.
2. Sumarla a `PROVEEDORES` y activar «Claude» en `ui/dialogos/ia_config_dialog.py` (hoy deshabilitado).
3. Guardar la API key fuera del proyecto (por ejemplo, el almacén de credenciales de Windows; nunca en QSettings
   en texto plano ni en la memoria del proyecto).
4. Con más contexto disponible, subir `contexto.MAX_FICHAS` / `MAX_UTILIDADES` y `redactor_ia.LOTE`.

Nada más cambia: consulta, informe y memoria hablan solo con `Proveedor`.

## Siguientes pasos

- **Herramientas (tool use):** con Claude, las funciones de `contexto.DatosProyecto` (buscar utilidades,
  conflictos, zonas) pueden ser herramientas que la IA llama sola, en vez de elegir de antemano qué datos van.
- **Memoria central:** juntar las carpetas «- IA» de los proyectos en una base del servidor, con búsqueda por
  parecido (embeddings). El formato JSONL no cambia.
- **Reentrenar (fine-tuning)** con las correcciones acumuladas, cuando haya miles.
- **Más soluciones automáticas:** tramos cortos entre codos (quitar o juntar vértices), uniones con pendiente,
  5+ tuberías en un punto. También mover solo el tramo del cruce en vez de la utilidad entera.
- **4. Leer el plano con el modelo visual** (leyenda, diámetros, válvulas en escaneos), siempre como sugerencia
  que el usuario confirma.
- **5. Normativas desde PDF/Word:** la IA propone filas de la tabla de reglas, validadas con la lista cerrada de
  lo que la app sabe medir.
- **Reubicación de utilidades existentes:** sugerir trazos que cumplan las normativas, validados por la app.
