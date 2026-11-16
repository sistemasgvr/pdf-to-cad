# Guía para quitar esperas (rendimiento) — método y tareas

Escrita el 2026-11-14 para que cualquier persona o modelo pueda seguir el trabajo paso a paso, sin
conocer el proyecto a fondo. Complementa `docs/arquitectura-rendimiento.md` (el porqué y las ideas de
fondo); aquí está el **cómo**: un ciclo fijo, tres medidores y una lista de tareas ya medidas.

Regla para quien ejecuta: **una tarea a la vez, de arriba abajo, sin saltarse pasos del ciclo.**
Si un paso no sale como dice aquí, se detiene y se informa; no se improvisa.

---

## 1. Qué se busca y qué no

«Que no demore nada» no existe: leer un PDF de 54 hojas cuesta trabajo real. Lo que sí se consigue:

| Tipo de acción | Meta | Si no se puede |
|---|---|---|
| Clic, tecla, elegir, Esc, encender o apagar algo ya cargado | La ventana responde en **≤ 0.1 s** (aceptable hasta 0.3 s) | El trabajo va a segundo plano y la ventana sigue atendiendo |
| Pintar un cuadro al desplazar o hacer zoom | **≤ 0.05 s** | Se pinta solo lo visible, y lo demás por partes |
| Trabajo largo (reconocer, componer, abrir, exportar) | Lo más corto posible, **nunca** con la ventana congelada más de 1 s seguido | Proceso aparte, avance visible y «Cancelar» |

Hay dos números distintos y hay que medir los dos:

- **Tiempo total** del trabajo (reconocer una hoja: 5 s).
- **Pausa de la ventana**: cuánto está congelada. Un trabajo de 60 s en otro proceso con la ventana
  viva molesta menos que uno de 3 s que la congela.

## 2. La regla que no se rompe: mismo resultado

Optimizar aquí es **hacer menos trabajo repetido**, nunca hacer un trabajo distinto.

Prohibido para ganar tiempo:

- cambiar tolerancias, umbrales o redondeos;
- saltarse utilidades, hojas, capas, vértices o avisos;
- cambiar el **orden** en que se prueban los candidatos (muchas reglas son «el primero gana»);
- devolver un resultado guardado sin comprobar que sus datos de entrada son los mismos;
- usar `float32` donde hoy hay `float`/`float64`.

Toda tarea termina con una **prueba de igualdad**: el resultado nuevo comparado con el viejo, campo por
campo. Los medidores de `scripts/rendimiento/` traen `--foto` y `--comparar` para eso. «0 diferencias» o
la tarea no está hecha.

## 3. Los medidores

Están en `scripts/rendimiento/`. Usan las MISMAS funciones que la app y ajustes aparte (no tocan los de
la app). Se corren desde la raíz del proyecto.

```bash
python scripts/rendimiento/editor.py proyecto.digproj
```

```bash
python scripts/rendimiento/reconocer.py plano.pdf 3
```

```bash
python scripts/rendimiento/componer.py plano.pdf
```

```bash
python scripts/rendimiento/capas.py hoja.pdf 0
```

```bash
python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --textos-de origen.pdf
```

Opciones comunes:

| Opción | Para qué |
|---|---|
| `--perfil` | Lista de funciones del proyecto ordenadas por tiempo acumulado: dice DÓNDE se va el tiempo |
| `--foto antes.json` | Guarda el resultado (reconocer, componer) |
| `--comparar antes.json` | Dice «IDÉNTICO» o lista las diferencias; sale con código 1 si hay alguna |
| `--filas N` | Cuántas filas del perfil |

Propias de cada uno:

- `editor.py --valvulas N --buzones N`: agrega carga simulada sobre las tuberías del proyecto.
  `--solo "texto"` corre solo las acciones cuyo nombre lo contiene; `--perfil "texto"` perfila esas.
- `reconocer.py -u ELECTRICO DRENAJE`: solo esas utilidades. `--sugerir` para hojas SIN capas (deduce la
  utilidad y sus estilos); con una hoja compuesta sin capas, además `--textos-de origen.pdf`.
- `componer.py --pdf-salida hoja.pdf`: deja la hoja compuesta para reconocerla después;
  `--paralelo 1` para perfilar (con varios procesos el perfil solo ve el proceso principal).
- `capas.py`: «Capas de la hoja» (`hoja/capas_trabajo.leer`): capas, las que tienen algo visible y los estilos
  sugeridos (`--foto`/`--comparar`).
- `importar.py`: la ventana real tras reconocer: vista previa (curvas de los quiebres), importar y editor quieto.
  Reconoce UNA vez y guarda el resultado junto al PDF (`--reconocer` lo rehace); la escala se lee una vez y se pone
  como la pone la app con una hoja compuesta (si no, `detect_scale` suma ~28 s que la app no paga). `--perfil
  importar quieto` perfila esos pasos. La vista previa incluye una copia profunda de lo reconocido (la hace el
  medidor, no la app). `--exportar anot|todo` = el botón «Exportar» después de importar (`--foto-dxf` /
  `--comparar-dxf`: cada entidad del DXF). `--pilas 20` anota cada 20 s la pila de cada hilo en `<pdf>.pilas.txt`:
  sirve cuando un paso tarda tanto que el perfil no termina (así se halló la exportación de 23 minutos).

Cuidados al medir (cada uno costó tiempo descubrirlo):

1. **Redirigir a un archivo, no a una tubería**: `… > salida.log 2>&1` y luego leer el archivo.
   `editor.py | tail` se queda colgado: los procesos de trabajo heredan la tubería y `tail` nunca termina.
2. **Un medidor a la vez.** Dos a la vez se roban el procesador y los números no sirven.
3. **El perfil suma 30–60 %** al tiempo. Comparar perfil con perfil, o cronómetro con cronómetro.
4. **Correr dos veces** y quedarse con el menor: la primera paga cachés del disco.
5. En scripts propios que crean la ventana: `if __name__ == "__main__":` siempre. Sin eso, cada
   proceso de trabajo vuelve a ejecutar el script entero (se vio: 6 copias de 1 GB).
6. Nunca medir con los ajustes reales de la app: `comun.preparar(con_qt=True)` los aparta.

## 4. El ciclo (siempre los mismos 7 pasos)

**Paso 1 — Reproducir y anotar la línea base.** Correr el medidor del flujo, sin perfil, dos veces.
Anotar el número en la tabla de la tarea. Si el flujo va bien (cumple la meta de la sección 1), la
tarea se cierra como «no hace falta».

**Paso 2 — Guardar la foto del resultado** (`--foto antes.json`), con el código SIN tocar. Guardarla
en la carpeta temporal de trabajo, no en el repositorio.

**Paso 3 — Perfilar** (`--perfil`). Mirar las 10 primeras filas. Buscar una de estas dos formas:

- una función con **muchísimas llamadas** (decenas de miles o más) → trabajo repetido o búsqueda de
  todos contra todos;
- una función con **pocas llamadas y mucho tiempo propio** → un cálculo caro que quizá se repite con
  los mismos datos.

**Paso 4 — Escribir la causa en una frase** antes de tocar nada: «X se calcula N veces con los mismos
datos porque Y lo llama desde Z». Si no se puede escribir esa frase, falta investigar: volver al paso 3
con `--filas 60`, o leer quién llama a la función. **Sin causa escrita no se cambia código.**

**Paso 5 — Aplicar UN patrón de la sección 5.** El más simple que resuelva la causa. Un cambio por
vez; no «aprovechar» para ordenar otra cosa.

**Paso 6 — Comprobar igualdad y medir.**

1. `--comparar antes.json` → debe decir IDÉNTICO.
2. Medir otra vez sin perfil. Anotar el número nuevo.
3. Correr las pruebas del grupo afectado: `python scripts/pruebas.py <grupo>` (grupos en ese archivo).
4. Escribir una prueba nueva que **falle sin el cambio** (ver sección 6).

Si no es idéntico: se deshace el cambio y se vuelve al paso 4. No se «arregla la foto».

**Paso 7 — Dejar constancia.** Una línea en `CHANGELOG` (`app/nucleo/model.py`) con su traducción en
`app/traduccion/i18n_en_changelog.py`, y actualizar la tabla de la tarea en esta guía (antes, después,
qué se hizo). **No se hace commit**: los hace el usuario.

Si después de **dos** intentos una tarea no mejora, se detiene y se informa con el perfil: puede que
la causa sea de arquitectura y no de un arreglo puntual.

## 5. Causas típicas y su patrón de arreglo

Cada patrón ya existe en el proyecto: se copia la forma, no se inventa otra.

### A. Se recalcula lo mismo en cada redibujo → memo por firma

*Síntoma:* una función cara aparece en el perfil de «redibujo sin cambios» o de «elegir».
*Arreglo:* guardar el resultado con una clave que contenga **todo** lo que la función lee.

- Dentro de un redibujo: `self._memo(clave, fn, copiar=False)` (`ventana_dibujo.py`). La firma del
  modelo ya cubre utilidades, estructuras, normativas, escala, zoom e idioma (`_firma_modelo`).
- Si la función lee algo que NO está en `_firma_modelo` (válvulas, anotaciones, superficies, un ajuste),
  ese algo va en la clave. Ejemplo hecho: `_lugares_valvulas` en `ventana_valvulas.py`, clave =
  (firma del modelo, firma de las válvulas, pies por píxel, idioma).
- Devolver una **copia** si quien llama puede modificar el resultado (`list(...)` o `copiar=True`).

*Riesgo:* clave incompleta = resultado viejo. Antes de cerrar, listar cada dato que la función lee y
comprobar que está en la clave.

### B. Búsqueda de todos contra todos → índice por celdas, misma prueba, mismo orden

*Síntoma:* una función pequeña con cientos de miles de llamadas (`_dist_seg`, `_cerca`, `hypot`).
*Arreglo:* un índice que devuelve **candidatos** (un superconjunto, en el orden original) y después la
MISMA prueba exacta de siempre sobre ellos.

- Ya hechos: `nucleo/indice_plano.py` (`IndiceUtilidades`, `IndicePuntos`, `pares_tramos`),
  `reconocimiento/recognition_indice.py` (`IndiceTramos`, `IndiceCajas`), `valvulas.Ubicadas`.
- El índice se arma **una vez** por tanda de consultas, no en cada consulta (ver C).
- Prueba obligatoria: el resultado con índice = el resultado recorriendo todo (se «apaga» el índice
  con `monkeypatch` y se compara; ejemplo en `tests/test_editor_sin_esperas.py`).

### C. Se valida o se arma algo en cada llamada → una vez por tanda

*Síntoma:* una función de «preparación» (`_firma`, `__init__` de un índice, `detect_scale`, abrir un
documento) con tantas llamadas como elementos.
*Arreglo:* sacarla del bucle; quien recorre la prepara una vez y pasa el resultado. Ejemplo hecho:
`_cerca_valv_al_dia` (valida el índice de utilidades una vez para todas las válvulas; antes, 10 ms por
válvula).

### D. Se borran y se crean los mismos objetos de la escena → se quedan

*Síntoma:* `removeItem`, `addItem` o constructores de ítems Qt con miles de llamadas en un redibujo
que no cambió el modelo.
*Arreglo:* si la clave (modelo + lo que decide el aspecto) no cambió y los ítems siguen en la escena,
se conservan. Ejemplo hecho: `_valvulas_que_siguen` / `_draw_valvulas`.

*Riesgo — el orden de apilado:* dos ítems con la misma Z se apilan por orden de llegada. Un ítem que
se queda es «más viejo» que los que se recrean y pasa a quedar debajo. Solución usada: darle una Z
apenas mayor (`Z_VALV = Z_MARK + 2.001`) **solo** después de comprobar qué más se dibuja en esa Z y en
qué orden (`grep "Z_MARK + 2"`).

### E. Varios redibujos por una sola acción → uno

*Síntoma:* `_redraw` aparece 2 o 3 veces en el perfil de una acción.
*Arreglo:* `with self._redibujo_diferido():` alrededor de las llamadas que redibujan, y un `_redraw()`
al final. Ejemplo hecho: `_pick` en `ventana_clics.py`.

### F. Un ítem de Python por elemento pintado → una capa que pinta lo visible

*Síntoma:* `paint` de un ítem con miles de llamadas por cuadro.
*Arreglo:* un solo ítem de la escena que guarda los datos en arreglos, descarta lo que no cae en la
zona a repintar (numpy) y pinta el resto. Modelos a copiar: `ui/comun/capa_lineas.py` (el más simple) y
`ui/comun/capa_marcas.py` (con sellos e imagen de la vista). Prueba obligatoria: mismos píxeles que
ítem por ítem (ver `tests/test_capa_lineas.py`).

### G. Trabajo pesado en la ventana → proceso aparte con avance

*Síntoma:* la ventana se congela más de 1 s.
*Arreglo:* `ui/comun/proceso.Tarea("modulo:funcion", args)` en un trabajador, con `avance` y
`terminado`. La función debe ser pura (sin Qt). **Todo módulo nuevo que corra así se suma a
`hiddenimports` de `PDF-a-CAD.spec` y a `autoprueba.MODULOS_POR_NOMBRE`**, o falla en el .exe.
Un hilo NO sirve para esto: PyMuPDF y el código Python no sueltan el GIL.

### H. Miles de elementos puestos de golpe → por tandas, primero lo visible

*Síntoma:* tras un cálculo, la ventana se congela mientras crea decenas de miles de marcas.
*Arreglo:* generador + `marcas_por_tandas.Tandas` (ya existe: 30 ms por vuelta). Lo que falta es el
orden (tarea E6).

### I. Se lee el PDF varias veces → una lectura compartida

*Síntoma:* `get_drawings`, `get_text`, `get_texttrace` o `drawings` con varias llamadas por hoja.
*Arreglo:* `pdf_styles.lectura_unica(doc)` y `pdf_styles.memo`. **Nadie modifica la lista que
devuelven.**

### J. Se dibuja (rasteriza) la misma zona varias veces → una vez y se guarda

*Síntoma:* `get_pixmap` o una función que dibuja una franja con cientos de llamadas.
*Arreglo:* guardar el resultado por (documento, hoja, zona, escala, capas visibles) mientras dure el
trabajo. Es la causa de la tarea C1.

## 6. Cómo se prueba cada arreglo

Tres pruebas, las tres obligatorias:

1. **Igualdad con datos reales**: `--comparar` del medidor, o una foto propia del flujo.
2. **Igualdad en pytest, con datos sintéticos**: el camino nuevo contra el viejo. Si el arreglo es un
   índice, se apaga y se compara. Si es un memo, se comprueba que cambia cuando cambia cada entrada.
3. **Que no se recalcula**: contar llamadas con `monkeypatch` (función `_contar` en
   `tests/test_editor_sin_esperas.py`) y exigir 0 en la acción que debía ser gratis.

Una prueba de tiempo («tarda menos de X s») solo como red de seguridad amplia (10× de margen): las
máquinas varían y una prueba que falla por ruido se termina ignorando.

Pruebas existentes que cualquier cambio del editor debe seguir pasando:

```bash
python scripts/pruebas.py editor interfaz tests/test_editor_sin_esperas.py tests/test_valvulas.py tests/test_capa_lineas.py tests/test_capa_marcas.py tests/test_marcas_por_tandas.py tests/test_calculo_fondo.py tests/test_rendimiento_plano.py
```

`tests/test_capa_marcas.py::test_capas_se_ven_igual_y_dan_el_mismo_tooltip` **ya falla** sin ningún
cambio (anotado en `CLAUDE.md`): no cuenta.

## 7. Líneas base (medidas el 2026-11-14 en la máquina del proyecto)

### Editor — `PRUEBA AGUA 2 PDF SIN CAPAS.digproj` (16 761 utilidades, 53 843 marcas)

| Acción | Sin válvulas | + 2 000 válvulas y 1 500 buzones |
|---|---|---|
| Abrir (ventana lista) / avisos listos | 4.6 s / +12 s en segundo plano | — |
| Elegir en la lista | 0.3–0.4 s | 0.2–0.35 s (antes del arreglo: 86–190 s) |
| Clic en una línea | 0.4 s | — |
| Redibujo sin cambios | 0.07 s | 0.15 s (antes: 88 s) |
| Pintar la vista entera | 0.06 s | 0.3 s |
| Apagar / encender avisos | 0.2–0.4 s + ~1 s en segundo plano | igual |
| Apagar una capa / encenderla | 0.09 s / 0.06 s + 0.46 s de pintado | 0.16 s / 0.07 s + 0.85 s |
| Zoom ×4 (pintado) | 0.1 s | 0.2 s |

### Reconocer

| Caso | Tiempo |
|---|---|
| DU06, hoja 3, 6 utilidades (CAD con capas) | ~5.3 s |
| Southwest, hoja 36, gas (sin capas) | ~3.3 s + 1.4 s de deducir estilos |
| Southwest, compuesta de 54 hojas, gas | ~6 min (ver tarea R3) |

### Componer — Southwest, 54 hojas

| Etapa | Tiempo (4 procesos) |
|---|---|
| Leer las hojas (fichas) | 4.6 s |
| Uniones | 0.3 s |
| Armar | 9.4 s |
| Materializar el PDF de una hoja | 2.8 s |

## 8. Tareas, en orden

Cada tarea dice el síntoma, cómo medirla, la causa (medida, o hipótesis si dice «por confirmar»), el
patrón y cuándo está hecha. Se hacen en este orden: primero las de causa ya medida y arreglo local.

### Hechas (sirven de ejemplo)

| # | Qué | Antes → después | Dónde mirar |
|---|---|---|---|
| H1 | Válvulas ubicadas en cada redibujo | 88 s → 0.15 s | `ventana_valvulas._lugares_valvulas`, `valvulas.Ubicadas` (patrones A, B, C) |
| H2 | Ítems de válvulas recreados en cada clic | 0.25 s → 0 | `_valvulas_que_siguen` (patrón D) |
| H3 | Dos o tres redibujos por clic en una línea | 3 → 1 | `ventana_clics._pick` (patrón E) |
| H4 | Filtro del inventario, flujo y botón Capas recorrían todas las utilidades por clic | ~0.2 s → ~0 | `_filtrar_inventario_si_cambio`, `_flujo_en_plano_todas`, `_capas_utilidad` (patrón A) |
| C1 | Composición sugerida: la franja del marco se dibujaba 432 veces (Southwest, 54 hojas) | 15.3 s → 7.2 s (armar 9.4 → 0.8 s) | `borde_inclinado._hoja_leida` (una lista de dibujo por hoja, patrón J) y `marco_calculado` → `Ficha.marco_calc` que usa `armar` (patrón A) |
| R3.1 | Reconocer la compuesta: `join_emitted` probaba todas las rutas en cada nodo (91 millones) | 294 s → 11 s (con perfil) | `routes._Pasos` (patrón B) |
| R3.2 | Rótulos en piezas: `_vecinas` ordenaba y recorría todas las piezas por rótulo; `por_largo` medía cada rótulo contra cada línea | 240 s → 20 s (con perfil) | `recognition_grosor_registros._Orden`, pies ordenados + descarte por caja (patrones B y C) |
| R3.3 | `poner_cerca` medía líneas más allá del alcance del rótulo | 38 s → ~12 s (con perfil) | descarte por la caja de la línea (patrón B) |
| K1 | «Capas de la hoja» y reconocer: los símbolos de fuente se armaban dos veces por hoja | Capas ~20 s → 12 s | `pdf_styles._drawings` con `memo` (patrón I) |
| R3.4 | Válvulas de la leyenda en imagen: cada glifo se dibuja a 10× y cuesta ~20 ms (MuPDF traza enteras las calles que pasan por el recuadro) | 46 → 22 s | `recognition_valvulas_tinta.se_ven`: los MISMOS dibujos repartidos en procesos (patrón G). Dibujar un recuadro mayor y recortarlo NO da los mismos píxeles: probado, 701 de 1 575 recuadros distintos |
| R3.5 | `join_emitted` volvía a mirar los 28 mil extremos tras cada unión | 9 → 3 s | `routes._Pares`: tras unir, solo los nodos a ≤ 3·tol de la unión y de las puntas de la línea (patrón C) |
| R3.6 | `IndiceTramos` armado de a un tramo, ~30 veces por hoja | ~2× más rápido | `recognition_indice._repartir`: las mismas cuentas con numpy (patrón C) |
| R3.7 | `ajustar_quiebres`: cada punta recorría todos los bordes (recortes de las 54 piezas) | 22 → 14.5 s | `recognition_angulos_calc._bordes_cerca` (descarte por caja, patrón B) |
| R3.8 | Las válvulas (R3.4) esperaban al final aunque no dependen de las líneas | ~139 → ~124 s (con R3.9) | `recognition_valvulas.adelantar` + `recognition_trabajo._valvulas_adelantadas`: los dibujos salen al empezar y corren en otros procesos mientras se reconocen las líneas (las capas del documento no cambian en el reconocimiento: se filtran por nombre) |
| I1 | Importar (Southwest, 14 278 líneas, 1 570 válvulas): `_guardar_valvulas` pegaba cada válvula con `_utilidades_cerca`, que compara la geometría de TODAS las utilidades en cada llamada | 33 s → 3.6 s | `_cerca_valv_al_dia()` una vez (patrón C) y `valvulas.juntar` por celdas (patrón B) |
| I2 | Redibujo con los resultados del cálculo de fondo: `conflictos._sin_repetidos` todos contra todos (26 mil cruces) | 5 s → 1.5 s en la ventana | celdas de `MISMO_PX`; también `numerar_fijo` (tras cada edición) y `agrupar` (gana el grupo de menor índice) |
| X1 | Exportar solo lo dibujado (Southwest): `_export_valvulas` ubicaba las válvulas sin índice y `anotaciones.senala` buscaba la tubería de cada rótulo entre TODAS | 1 394 s → 23 s, DXF idéntico | `ubicar_todas(cerca=win._cerca_valv_al_dia())` y `senala(cerca=IndiceUtilidades(...).cerca)` (patrón B) |
| R3.10 | Revisión: dentro del trabajador de la app (proceso «daemon») ningún grupo de procesos arrancaba («daemonic processes are not allowed to have children»): R3.4/R3.8 y las fichas de la composición sugerida seguían de a uno, sin avisar. Los medidores corren FUERA del trabajador y no lo veían | la ganancia medida ahora también llega a la app | `proceso_hijo.con_hijos()` + `initializer=morir_con_el_padre` (patrón G). Medir también dentro de un proceso «daemon» lo que se reparta |
| R3.9 | `_cerca` medía cada rótulo de diámetro contra TODOS los tramos de cada ruta | (en R3.8) | `recognition_grosor_mapa._cerca(tramos=)`: solo los que da el índice a su alcance; el más cercano siempre está entre ellos (patrón B) |

**Total medido el 2026-11-15, compuesta de Southwest (54 hojas), todo IDÉNTICO con `--comparar`:**
composición sugerida 15.3 → 7.2 s · Capas ~20 → 12 s · reconocer ~6 min → ~104 s con el medidor (unos 85 s en
la app: el medidor no pasa la escala y `detect_scale` le suma ~18 s que la app no paga).

**2.ª vuelta (2026-11-15, R3.4–R3.7), también IDÉNTICO:** medido A/B en el mismo rato (el equipo con otras
aplicaciones abiertas, por eso los números absolutos son mayores que los de arriba): reconocer la compuesta
~184 s → ~143 s (dos corridas de cada versión, una tras otra; la «vieja» = las piezas cambiadas devueltas a su código anterior).
OJO al medir: con otras aplicaciones usando CPU el mismo código tarda 30–40 % más; comparar siempre A/B seguidos.

### C1 — Composición: la franja del marco inclinado se dibuja 432 veces  (HECHA el 2026-11-15, queda como ejemplo)

- **Síntoma:** componer Southwest tarda 15 s; con un proceso, 50 s.
- **Medir:** `python scripts/rendimiento/componer.py "<Southwest>.pdf" --paralelo 1 --perfil`
- **Causa (medida):** `borde_inclinado.cuadrilatero` → `_linea_y_grosor` → `tinta_de` → `franja` suma
  32.6 de 50.7 s (64 %). `cuadrilatero` se llama 108 veces = **2 por hoja**: una desde
  `composicion_ficha._marco` (12.7 s) y otra desde `composicion_sugerida.armar` (≈20 s), y cada una
  dibuja la franja de cada lado varias veces (432 llamadas a `franja`).
- **Patrón:** J y A. Dos pasos, cada uno con su comparación:
  1. dentro de `cuadrilatero`, dibujar la franja de cada lado **una vez** y reutilizarla para todas las
     rectas candidatas de ese lado;
  2. guardar el resultado de `cuadrilatero` de la ficha (por documento, hoja y rectángulo) y usarlo en
     `armar` cuando el rectángulo y los segmentos son los mismos. OJO: `armar` puede llamar con
     `rectos=True` o con otro rectángulo (`f.vista`); solo se reutiliza si TODOS los argumentos coinciden.
- **Igualdad:** `componer.py … --foto antes.json` y luego `--comparar antes.json`; además
  `python scripts/pruebas.py tests/test_borde_inclinado.py tests/test_atlas_bordes.py tests/test_composicion_sugerida.py tests/test_area_sugerida.py`.
- **Hecha cuando:** `franja` baja de 432 a ≤ 216 llamadas (paso 1) y a ≤ 108 (paso 2), composición
  idéntica, y el total con `--paralelo 1` baja de ~50 s a menos de 25 s con perfil.

### C2 — Composición: leer el texto de cada hoja

- **Medir:** el mismo comando de C1.
- **Causa (medida):** `composicion_ficha._textos` 6.4 s para 54 hojas (0.12 s por hoja).
- **Por confirmar:** si `_textos` y `texto_plano`/`estilos_sugeridos.textos_de_documento` leen el mismo
  texto de la misma hoja por separado. Si es así, patrón I (una lectura por hoja guardada en el documento).
- **Hecha cuando:** cada hoja lee su texto una sola vez en todo el flujo de «Componer hoja».

### C3 — Materializar: `_show_pdf_page`

- **Causa (medida):** 5.2 de 6.8 s (con perfil) son `show_pdf_page` de PyMuPDF, 54 llamadas: trabajo
  real de la librería. `_ocg_xrefs` 0.9 s en 55 llamadas.
- **Patrón:** C para `_ocg_xrefs` (calcularlo una vez por documento de origen, no por pieza).
- **No tocar** `_show_pdf_page`: corrige un defecto de PyMuPDF con las hojas giradas.
- **Hecha cuando:** `_ocg_xrefs` se llama una vez por documento y el PDF resultante es el mismo
  (comparar con `gather_paths` de la hoja compuesta: mismos trazos; el sha1 del PDF cambia en cada
  corrida por la fecha, no sirve).

### R1 — Reconocer CAD: `unir_codos` prueba ajustes punto por punto

- **Medir:** `python scripts/rendimiento/reconocer.py "<DU06>.pdf" 3 --perfil`
- **Causa (medida):** `recognition_unir_codos._probar` → `_ajustar` → `ajuste` 1 344 llamadas con un
  `genexpr` de 792 064 pasos (≈2.1 de 13.5 s con perfil). Es una suma de distancias en Python puro.
- **Patrón:** vectorizar con numpy **la misma fórmula**, o guardar por (tinta, recta) lo que no cambia
  entre los 1 344 intentos. OJO: una suma con numpy puede diferir en el último bit de una suma en
  Python; si un `min` o una comparación con tolerancia cae en el filo, cambia un codo. Por eso la
  comparación se hace sobre DU06 hojas 3, 4, 5 y DU08 hoja 22 y 26 (las que `CLAUDE.md` nombra como
  sensibles), no sobre una sola.
- **Igualdad:** `--foto`/`--comparar` en esas hojas + `python scripts/pruebas.py reconocimiento`.
- **Hecha cuando:** idéntico en las cinco hojas y `ajuste` deja de estar en las 10 primeras filas.

### R2 — Reconocer CAD: `_arc_distance` 750 450 llamadas

- **Causa (medida):** `recognition_trace.fit_continuous` → `_arc_distance` 1.4 s. Mismo tipo que R1.
- **Patrón y cuidados:** los de R1. Hacer R1 primero: enseña el método con una función más simple.

### R3 — Reconocer la hoja compuesta de mapas (Southwest, 54 hojas: ~6 min)

- **Medir:** primero dejar la hoja: `componer.py "<Southwest>.pdf" --pdf-salida comp.pdf`; luego
  `reconocer.py comp.pdf 0 --sugerir --textos-de "<Southwest>.pdf" --perfil --filas 45 > rec.log 2>&1`
- **Causa en UNA hoja (medida, hoja 36, 4.8 s con perfil):**
  - `recognition_grosor_mapa._cerca` 128 098 llamadas, 1.1 s → patrón B (rótulos × líneas);
  - `recognition_indice.__init__` 27 veces, 0.56 s → patrón C (¿el mismo índice armado varias veces
    sobre las mismas líneas?);
  - `vector_pipeline.detect_scale` 0.4 s → patrón A (una vez por hoja).
- **Estado 2026-11-15:** hechos los puntos 1, 2 y 3 de abajo (767 → 187 s con perfil, idéntico). Quedan, por
  tiempo con perfil: válvulas `_se_dibuja` 1 575 dibujos de 14 ms = 22 s (cada uno recorre la lista de dibujo
  ENTERA de la hoja; no se pudo abaratar sin cambiar píxeles: ver el punto 4), `recognition_indice.__init__` 31
  veces = 20 s (punto 5), `ajustar_quiebres` 16 s, las dos formas de la lectura de la hoja 15 s,
  `_best_emitted_pair` 10 s (arma su rejilla de puntas en cada una de las 56 vueltas: patrón C).
- **Estado tras la 2.ª vuelta (R3.4–R3.7):** quedan `ajustar_quiebres` ~14 s sin perfil (`_ajustar_linea`,
  `contactos`, `resolver`: álgebra por línea), `pdf_styles._drawings` (dos lecturas de la hoja) y `gather_paths`
  ~10 s, el grosor de los mapas (`poner_cerca`, `por_largo`) ~15 s y las válvulas ~22 s (ya en paralelo: lo que
  queda es el dibujo de MuPDF, que no se puede abaratar sin cambiar píxeles).
- **Después de reconocer (medido con `importar.py`, Southwest):** cargar la hoja ~5.5 s (dibujo de MuPDF), vista
  previa ~2 s, importar 3.6 s (antes 33), editor quieto ~8 s en tandas sin trabar la ventana. «Capas de la hoja»
  ~12 s: casi todo es la lectura de la hoja y de su texto en PyMuPDF (lo nuestro, ~1 s). Exportar: solo lo
  dibujado 23 s; completo (PDF digitalizado + lo dibujado, 76 MB) 130 s, casi todo digitalizar en su hilo.
- **3.ª vuelta (R3.8–R3.9), IDÉNTICO:** A/B ~139 → ~124 s. Revisado y descartado: las «dos lecturas» de
  `pdf_styles._drawings` (la lectura real, ~10 s, ya es una; lo repetido es ~1 s de agrupar por estilo y cambiarlo
  arriesga la clave `_pdfcad_dibujos`) y el resto de `ajustar_quiebres` (~6 s por variante repartidos en miles de
  cuentas chicas por línea; vectorizarlo entre líneas cambiaría el último bit de las sumas).
- **En la compuesta (medida, 767 s con perfil, 14 278 líneas):** casi todo es todos contra todos.
  Hacerlas en este orden, una por una, cada una con su `--comparar`:
  1. `routes.join_emitted` → `_best_emitted_pair` (56 llamadas) → `_passes` **91 millones** de
     llamadas: 294 s (38 %). Cada vuelta busca el mejor par recorriendo todas las rutas contra todas.
     Patrón B: índice de puntas (`IndicePuntos`) para dar solo las rutas que pasan por ese punto, en
     el mismo orden; y no rehacer la búsqueda entera tras cada unión.
  2. `recognition_grosor_registros.por_largo` 125 s y `rotulos` → `_vecinas` (35 568 llamadas, 146
     millones de pasos de su `lambda`) 113 s; `_pies` 39 millones. Patrón B (celdas de piezas de texto).
  3. `recognition_grosor_mapa._cerca` 3.8 millones de llamadas, 38 s. Patrón B.
  4. `vector_pipeline.detect_scale` 33 s **dentro de** `recognition_valvulas._de_imagen`: lee el texto
     de toda la hoja compuesta para la escala. Patrón A (una vez por hoja, o recibir la escala ya conocida).
     `_se_dibuja` 1 575 llamadas, 29 s: patrón C/J.
  5. `recognition_indice.__init__` 31 veces, 25 s: patrón C (el mismo índice armado varias veces).
  6. `pdf_styles._drawings` 2 lecturas de la hoja, 23.6 s: patrón I (¿por qué dos?).
- **Hecha cuando:** la compuesta baja de 6 min a menos de 2 con resultado idéntico. Es la tarea más
  larga: hacerla después de C1, R1 y E1–E3.

### E1 — Editor: pintar las válvulas (0.25 s por cuadro con 2 000 a la vista)

- **Medir:** `editor.py <proyecto> --valvulas 2000 --solo "pintar" --perfil "pintar"`
- **Causa (medida):** `ValvulaItem.paint` 8 000 llamadas por cuadro (dos ítems por válvula; uno pinta
  y el otro solo decide que no le toca) + `boundingRect`.
- **Patrón:** F. Una `CapaValvulas` copiada de `CapaLineas`: arreglos con x, y, rumbo, largo, alto,
  color, estado; en `paint` descarta por la zona a repintar y dibuja con `_pintar_partes`. La regla
  «moño real o moño mínimo de 14 px» se decide por válvula con la escala del pintor.
- **No perder:** el globo (tooltip) de cada válvula, `_sync_capa_valvulas` (apagar por utilidad) y
  `_valvula_en` (el clic). El globo se resuelve como en `capa_marcas.GrupoMarcas.tooltip_en`.
- **Igualdad:** mismos píxeles que con `ValvulaItem` a 100 % y 125 %, con zoom lejano y cercano.
- **Hecha cuando:** pintar la vista entera con 2 000 válvulas ≤ 0.1 s.

### E2 — Editor: los buzones se recrean en cada redibujo (~40 µs cada uno)

- **Medir:** `editor.py <proyecto> --buzones 5000 --solo "redibujo" --perfil "redibujo"`
- **Causa (medida):** `_draw_structures` crea de nuevo cada círculo, contorno y rótulo.
- **Patrón:** D, con clave = (firma del modelo, `sel_bz`, `sel_curve`, `show_bz_labels`, colores).
- **Riesgo:** el orden de apilado. Los contornos van en `Z_MARK`, igual que las líneas de leaders,
  centerlines y textos que se dibujan antes y después. Antes de tocar: listar con `grep "Z_MARK"` qué
  se dibuja en cada Z y en qué orden, y decidir Z por Z. Si no se puede garantizar el mismo apilado,
  **no se hace** y se pasa a F (una capa para los buzones).
- **Hecha cuando:** un redibujo sin cambios con 5 000 buzones no llama a `ML.agregar`.

### E3 — Editor: elegir en la LISTA redibuja dos veces

- **Causa (medida):** Qt avisa primero «cambió la selección» (`_pipe_selection_changed` redibuja con
  la utilidad anterior) y después «cambió la fila» (`_sel_pipe` redibuja bien). El primero sobra.
- **Patrón:** E, pero aquí no hay un punto único que envolver. Opción segura: que
  `_pipe_selection_changed` deje el redibujo para la siguiente vuelta del bucle de eventos
  (`QTimer.singleShot(0, self, …)`, **con contexto**) y lo cancele si `_redraw_todo` ya dibujó esa
  selección (`_multi_dibujada`).
- **Riesgo:** pruebas que eligen varias filas y miran el lienzo sin dar una vuelta de eventos. Correr
  `tests/test_unir_utilidades.py`, `test_edicion_bloque.py` y el grupo `editor`. Si alguna depende del
  redibujo inmediato, se descarta la tarea (gana 0.15 s, no vale romper nada).

### E4 — Editor: encender o apagar avisos rearma las marcas

- **Causa (medida):** los tres interruptores están en `_firma_marcas`; al cambiar uno, el grupo de
  marcas se rehace (0.3–0.5 s en la ventana + ~1 s por tandas). Volver a una combinación ya vista es
  inmediato (`ventana_estados`, las 2 últimas).
- **Patrón:** como «Capas»: una máscara por TIPO de marca en `_Capa` (igual que `fijar_ocultas`) en
  vez de rehacer. Las marcas se crean todas una vez y el interruptor solo cambia qué se pinta.
- **Cuidado:** hoy, con un tipo apagado, sus marcas ni se crean; con la máscara se crean siempre (más
  memoria y más carga inicial). Medir las dos cosas antes de decidir.
- **Hecha cuando:** apagar o encender un tipo de aviso ≤ 0.1 s y sin trabajo en segundo plano.

### E5 — Editor: al encender una capa, el repintado tarda 0.5–0.85 s

- **Causa (por confirmar):** `fijar_ocultas` borra la imagen de la vista y el despeje de rótulos de
  TODAS las capas de marcas, aunque solo cambie una parte.
- **Medir:** `editor.py <proyecto> --solo "capa" --perfil "encender"`.

### E6 — Carga focal: las marcas, primero donde mira el usuario

- **Hoy:** las marcas se PINTAN solo en lo visible, pero se CREAN todas, por tandas, en el orden del
  modelo, y las capas quedan ocultas hasta terminar (~3 s con 54 mil).
- **Idea:** repartir cada dibujante en dos pasadas —lo que cae en la vista (más un margen) y el
  resto— y mostrar las capas al terminar la primera.
- **Riesgo alto:** dentro de cada capa el ORDEN de llegada decide qué marca queda encima, qué rótulo
  gana el despeje y qué globo sale. Dos pasadas cambian ese orden. Solo vale si cada marca guarda su
  número de orden original y la capa pinta y despeja por ese número, no por orden de llegada.
- **No empezar** sin que el usuario lo apruebe: es un cambio de diseño de `capa_marcas`, no un arreglo.

### E7 — `_firma_modelo`: 45 ms en cada redibujo

- **Causa (medida):** serializa TODO el modelo (16 mil utilidades) para saber si cambió.
- **No tocar por ahora.** Es el detector que hace seguros todos los memos. Cambiarlo por un contador
  de versión exige encontrar cada lugar que modifica `pipes` o `structures` (cientos); uno que falte
  = resultados viejos en pantalla. Solo con aprobación y con un plan aparte.

### M1 — Medidores de «Capas de la hoja», «Importar» y «Exportar»  (HECHA el 2026-11-16)

- `capas.py` e `importar.py` (con `--exportar`), sección 3.

## 9. Informe al terminar cada tarea

Copiar y llenar. Va al final de la tarea en esta guía y, resumido, al usuario.

```
Tarea: C1
Causa: (la frase del paso 4)
Cambio: (archivos y funciones)
Antes → después: 50.7 s → __ s (con perfil, --paralelo 1); 15.3 s → __ s (normal)
Igualdad: IDÉNTICO en (qué casos)
Pruebas: (grupos corridos y resultado); prueba nueva: tests/__.py::__
Riesgos o dudas: __
Sin hacer: __
```

## 10. Reglas del proyecto que aplican aquí

- No hacer `git commit` ni `git push`: el usuario revisa y hace los commits.
- Archivos con finales de línea de Windows (CRLF): al editar con un script, abrir y escribir con
  `newline=""` para no cambiarlos.
- Archivos de menos de 500 líneas; lógica pura en `app/nucleo`, `app/hoja`, `app/reconocimiento`.
- Textos visibles nuevos: `t("…")` y su traducción (`tests/test_i18n.py` lo exige).
- No correr toda la batería: `python scripts/pruebas.py <grupo>`.
- Si algo que la app no puede resolver queda sin resolver, se le avisa al usuario en la interfaz.
