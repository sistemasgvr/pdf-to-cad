# Decisiones sobre conflictos de tuberías y accesorios

Este documento recoge **qué hace la app y qué hace Civil 3D** cuando dos o más
utilidades se tocan, se cruzan o quedan en una situación difícil, y **por qué** se
decidió así. Cada caso se validó dibujándolo en los proyectos de prueba y
revisando el resultado en la app y en Civil 3D.

Al final de cada caso hay una línea **«Dónde se valida»** con el archivo y la
función que implementan o comprueban esa decisión.

> **Proyectos de prueba** (se abren en la app y se exportan a Civil 3D; cada celda
> lleva escrito lo que debe pasar):
> - [tests/escenarios/escenarios_prueba.digproj](../tests/escenarios/escenarios_prueba.digproj) — casos **E01–E50**,
>   generados por [generar_escenarios.py](../tests/escenarios/generar_escenarios.py) (tabla `CASOS`).
> - [tests/escenarios/escenarios_complejos.digproj](../tests/escenarios/escenarios_complejos.digproj) — casos **C01–C26** y **F01–F10**,
>   generados por [generar_escenarios_complejos.py](../tests/escenarios/generar_escenarios_complejos.py).
>
> Pruebas automáticas de la parte de la app: `pytest tests/escenarios`.
> Lo que ocurre dentro de Civil 3D se revisa a mano con el texto de cada celda y
> los mensajes del plugin (`[COTAS]`, `[RETORNO]`, `[UNION-PENDIENTE]`…).

---

## Índice

1. [Marcadores de la app: qué significa cada uno](#1-marcadores-de-la-app-qué-significa-cada-uno)
2. [Reglas generales](#2-reglas-generales)
3. [Codos (quiebres de una misma tubería)](#3-codos-quiebres-de-una-misma-tubería)
4. [Reducciones (cambio de diámetro)](#4-reducciones-cambio-de-diámetro)
5. [Tee, Wye y Cruz (3 o 4 tuberías en un punto)](#5-tee-wye-y-cruz-3-o-4-tuberías-en-un-punto)
6. [Extremo con extremo y cotas distintas](#6-extremo-con-extremo-y-cotas-distintas)
7. [Cruces entre utilidades](#7-cruces-entre-utilidades)
8. [Conexiones verticales aprobadas](#8-conexiones-verticales-aprobadas)
9. [Nombres de red](#9-nombres-de-red)
10. [Otros casos de control (y cajas en eléctrico/telecom)](#10-otros-casos-de-control)
11. [Datos que viajan con cada accesorio (Property Set)](#11-datos-que-viajan-con-cada-accesorio-property-set)
12. [Casos límite documentados (C01–C26, F01–F10)](#12-casos-límite-documentados-c01c26-f01f10)
13. [Mapa rápido: dónde está cada regla](#13-mapa-rápido-dónde-está-cada-regla)

---

## 1. Marcadores de la app: qué significa cada uno

| Marcador en el lienzo | Significa | Qué hace el usuario |
|---|---|---|
| **Conflicto** (misma cota) | Dos o más tuberías de la **misma red** se tocan a la misma cota (±0.10 ft). El mensaje dice qué accesorio pondrá Civil 3D (codo, tee, wye, cruz, reducción) y a qué cota. | Nada: Civil 3D las une solo. |
| **Sugerencia ↕** | Se tocan en planta pero a **distinta cota**. | Puede **aprobar** una conexión vertical. |
| **Aprobado ✓** | El usuario aprobó la conexión vertical. | — |
| **▲ Alerta roja** | Algo que Civil 3D **no puede resolver como está dibujado**, o que resolverá cambiando el dibujo (p. ej. dando pendiente). El texto explica qué pasará. | Revisar; corregir el dibujo si no le sirve la solución automática. |

> **Solo redes a presión (agua y gas).** Ninguna de estas señales aparece en drenaje,
> alcantarillado, eléctrico ni telecomunicaciones (ver §2, «Señales solo en redes a presión»).

Decisiones sobre los mensajes:

- **Mensajes simples y con el nombre de la tubería**: cada tubería se nombra como
  «Tipo - nombre» (p. ej. «Agua - Linea Norte»); si no tiene nombre, solo el tipo.
- El texto largo de las alertas rojas se muestra en un **bloque cuadrado de ancho
  fijo** (340 px) para que se lea bien.
- Todos los textos se traducen al cambiar de idioma.

**Dónde se valida:** mensajes en [app_window.py](../app/app_window.py) —
`_union_civil` ([L4295](../app/app_window.py#L4295)), `_tipo` / `_etq`
([L4342](../app/app_window.py#L4342)), `_msg_*` ([L4290–4398](../app/app_window.py#L4290));
bloque del tooltip: `tooltip_bloque` en [ui_common.py:65](../app/ui_common.py#L65);
lista de alertas esperadas por caso: `ALERTAS` en
[generar_escenarios.py](../tests/escenarios/generar_escenarios.py).

---

## 2. Reglas generales

| Regla | Decisión |
|---|---|
| **Tolerancia de cota** | Dos puntos están «a la misma cota» si difieren **≤ 0.10 ft**. Entre 0.01 y 0.10 ft Civil 3D las une igual y las deja al **promedio** (mensaje `[COTAS] cotas unificadas`). |
| **Tolerancia en planta** | El plugin considera que dos extremos se tocan a **≤ 0.5 ft**. |
| **Solo se unen utilidades de la misma red** | Agua con agua, gas con gas… Nunca agua con drenaje ni gas con agua (ver §7). |
| **Accesorios siempre conectados** | Prioridad absoluta: toda boca de un accesorio debe quedar alineada con su tubo (en planta y en altura). Por eso en las piezas reductoras cada brazo va a la altura del eje de **su** tubo. |
| **Máximo 4 tuberías por accesorio** | La pieza más grande es la **Cruz** (4 salidas). Con 5 o más, alerta roja y no se pone pieza. |
| **Solo redes a presión** llevan accesorios sólidos (agua, gas). En **gravedad** (drenaje, alcantarillado) las uniones las resuelve el **buzón**. En **conduit** (eléctrico, telecom) no hay accesorios. |
| **Señales solo en redes a presión** | Conflictos, sugerencias y aprobaciones de vertical, «redes distintas» y todas las alertas rojas se calculan **solo con tuberías de agua y gas**. Una tubería de drenaje, alcantarillado, eléctrico o telecom no genera ninguna señal, ni sola ni cruzándose con una de presión. Una conexión vertical aprobada en un proyecto viejo entre tuberías que no son a presión se descarta y no llega al DXF. *(Decisión del usuario, 2026-09-28.)* |
| **El nombre de la tubería no cambia su geometría ni su diámetro** | Renombrar una tubería solo cambia cómo se llama. (Se corrigió un error en el que renombrar ponía el diámetro en 0.) |

**Dónde se valida:** `Z_TOL_JUNTA = 0.10` en
[ImportarRed.cs:2565](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L2565);
`MAX_TRAMOS_POR_ACCESORIO = 4` y `junturas_excedidas` en
[model_ops.py:794](../app/model_ops.py#L794); aviso del plugin «máximo de 4» en
[RedesPresionJunturas.cs:613](../API-CIVIL/proyecto1/proyecto1/RedesPresionJunturas.cs#L613);
diámetro al renombrar: `_prop_changed` en [app_window.py:3422](../app/app_window.py#L3422).
Señales solo en redes a presión: filtro de tuberías en `_draw_pipe_conflicts`
([app_window.py:4075](../app/app_window.py#L4075)) y descarte de aprobaciones viejas en
`_prune_stale_cross_connections` ([app_window.py:3888](../app/app_window.py#L3888)); las alertas
de `model_ops` ya filtraban `network_kind(...) == "pressure"`. Escenarios E24–E26 y E46
(sin señales) en [generar_escenarios.py](../tests/escenarios/generar_escenarios.py) y F09 en
[generar_escenarios_complejos.py](../tests/escenarios/generar_escenarios_complejos.py).

---

## 3. Codos (quiebres de una misma tubería)

### E01–E03 · Codos normales (11°, 45°, 90°)
- **App:** sin marcadores.
- **Civil 3D:** codo sólido del ángulo exacto, con curva de radio = 1 diámetro.
- **Decisión:** se pone codo desde **1° de giro**. Por debajo de 1° es una unión
  recta (sin pieza).

**Dónde se valida:** `accesorio_en_punto` en [model_ops.py:518](../app/model_ops.py#L518)
(«codo» si el giro > 1°); `DecidirTipoFitting` en
[RedesPresionJunturas.cs:177](../API-CIVIL/proyecto1/proyecto1/RedesPresionJunturas.cs#L177);
curva del sólido: `CurvaCodo` en [WyeSolido.cs:658](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L658).

### E04–E06 · Codos cerrados (130°, 140°, 160°, 176°)
- **App:** sin marcadores.
- **Civil 3D:** hasta 135° de giro, curva normal. **Más de 135°** = «codo cerrado»:
  se usa el **radio mínimo viable** y los tubos se recortan más.
- **Decisión:** el límite es `GIRO_CERRADO_DEG = 135°`.

**Dónde se valida:** `CurvaCodo` / `ConstruirCodo` en
[WyeSolido.cs:658](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L658) y
[WyeSolido.cs:714](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L714); espejo de las
constantes en Python comprobado por `test_espejo_de_wyesolido`
([test_escenarios_complejos.py:79](../tests/escenarios/test_escenarios_complejos.py#L79)).

### E07 · Codo cerrado (170°) con un tramo muy corto (2 ft)
- **Situación:** la curva del codo cerrado no cabe en el tramo de 2 ft.
- **App:** **▲ alerta roja** «codo de retorno».
- **Civil 3D:** **codo de retorno (forma de U) en el vértice**; el tramo corto se
  corre de lado (~1.2 ft) para que la U quepa.
- **Decisión del usuario:** «Codo de retorno en el vértice» (en vez de dejar un
  codo que no cabe o mover el vértice).

**Dónde se valida:** `codos_de_retorno` en [model_ops.py:624](../app/model_ops.py#L624)
(test `test_codos_de_retorno_solo_con_tramo_corto`,
[test_model_ops.py:426](../tests/test_model_ops.py#L426)); plugin: `CodosDeRetorno` en
[ImportarRed.cs:3717](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L3717) (mensaje `[RETORNO]`).

### E08 · Codo con pendiente (-2 → -10)
- **App:** sin marcadores.
- **Civil 3D:** el codo **sigue la pendiente** de los tubos (no se queda plano).

**Dónde se valida:** celda E08 de [generar_escenarios.py](../tests/escenarios/generar_escenarios.py);
orientación 3D del codo en `ConstruirCodo`
([WyeSolido.cs:714](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L714)).

### E39 · Dos codos separados por un tramo muy corto (0.6 ft)
- **Situación:** entre dos codos de 60° hay 0.6 ft; no entran dos codos sólidos
  (cada uno recorta el tubo) y quedarían montados.
- **App:** **▲ alerta roja** «tramo muy corto entre codos».
- **Civil 3D:** **un solo codo** de 120° en la intersección de las dos rectas; el
  tramo corto desaparece.
- **Regla:** largo mínimo entre codos = **3 diámetros, mínimo 1 ft** (solo redes a presión).

**Dónde se valida:** `largo_min_entre_codos_ft` y `tramos_cortos_entre_codos` en
[model_ops.py:570](../app/model_ops.py#L570) y [model_ops.py:580](../app/model_ops.py#L580);
plugin: `LargoMinEntreCodosFt` y `FusionarCodosSeguidos` en
[ImportarRed.cs:3639](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L3639) y
[ImportarRed.cs:3650](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L3650).

---

## 4. Reducciones (cambio de diámetro)

### E09, E41, E42, E43 · Codo reductor (Ø24→Ø12 a 45° y 90°, Ø12→Ø24, cerrado Ø18→Ø12)
- **App:** conflicto (misma cota); el mensaje dice «codo + reducción».
- **Civil 3D:** **codo del diámetro MAYOR** (mantiene su forma uniforme) +
  **reducción excéntrica** hacia el tubo delgado. La reducción respeta las cotas:
  fondo plano, cada boca a ras del eje de su tubo.
- **Decisiones del usuario:** codo del diámetro mayor; la excéntrica respeta las cotas.
- E42 (entra el delgado): el codo va del lado del tubo grueso y la reducción hacia el que entra.

**Dónde se valida:** `CrearCodoConReduccion` en
[ReduccionSolida.cs:44](../API-CIVIL/proyecto1/proyecto1/ReduccionSolida.cs#L44)
(largo de la reducción = 1.25·D); lo llama la juntura con codo reductor en
[RedesPresionJunturas.cs](../API-CIVIL/proyecto1/proyecto1/RedesPresionJunturas.cs);
celdas E09/E41–E43 de [generar_escenarios.py](../tests/escenarios/generar_escenarios.py).

### E11, E14, E44 · Wye y Tee reductoras (tronco Ø24, ramal Ø12)
- **App:** conflicto (misma cota).
- **Civil 3D:** la pieza se centra en el **eje del tubo grueso**; el ramal delgado va
  a la altura de **su propio eje** (fondo plano). Todas las bocas quedan
  **coaxiales** con sus tubos.
- **Decisión del usuario (E11):** «siempre se debe priorizar que los accesorios
  conecten» — antes el ramal quedaba desconectado.
- E44 (ramal a 30°): el brazo del ramal sale muy alargado (~3.2 ft) para que su
  campana no choque con el tronco.

**Dónde se valida:** ajuste de altura de cada brazo (`EjeZ` / `OffsetZFt`) en
`Aplanar` y `RecortarTubos` de
[WyeSolido.cs:300](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L300) y
[WyeSolido.cs:499](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L499); separación de
campanas: `SepararBrazos` ([WyeSolido.cs:444](../API-CIVIL/proyecto1/proyecto1/WyeSolido.cs#L444)).

---

## 5. Tee, Wye y Cruz (3 o 4 tuberías en un punto)

| Caso | Situación | Civil 3D |
|---|---|---|
| **E10** | Y simétrica (3 tubos a 120°) | WYE sólida |
| **E12** | Ramal muy cerrado (20°) | WYE con brazos alargados (sin hundirse en el tronco) |
| **E13** | Tee 90° Ø18 | TEE sólida |
| **E15** | Ramal a 72° | **TEE** (ramal y brazo vecino no chocan) |
| **E16** | Ramal a 66° | **WYE** (ramal < 70°) |
| **E17** | 4 tubos en un punto | **CRUZ** sólida, 4 brazos iguales |
| **E18** | 5 tubos en un punto | **▲ alerta roja** «Hay 5 tuberías…»; sin pieza |
| **E45** | 6 tramos en un punto | **▲ alerta roja** «Hay 6 tuberías…»; sin pieza |
| **E46** | 5 tramos de **drenaje** | Sin alerta: en gravedad lo resuelve el **buzón** |
| **E47** | 5 tramos, uno 2 ft más abajo | Sin alerta: el de abajo **no cuenta** (otra cota); CRUZ + tubo aparte |
| **E23** | Extremo que muere a mitad de otro tramo | **TEE**: el tramo que pasa se parte (`[JUNTURA-T]`) |
| **E38** | Y en **gas** | WYE sólida en la red de gas |

**Regla Tee / Wye:** es **Tee** solo si dos salidas son colineales (≥ 160°) **y**
el ramal va a 90° ± 20° (es decir, ≥ 70°). Si no, **Wye**.

**Dónde se valida:** `accesorio_en_punto` en [model_ops.py:518](../app/model_ops.py#L518)
(misma regla que el plugin); `DecidirTipoFitting` en
[RedesPresionJunturas.cs:177](../API-CIVIL/proyecto1/proyecto1/RedesPresionJunturas.cs#L177)
(umbral 70° en la [L215](../API-CIVIL/proyecto1/proyecto1/RedesPresionJunturas.cs#L215));
exceso de tuberías: `junturas_excedidas` ([model_ops.py:797](../app/model_ops.py#L797)) y
tests `test_cinco_tramos_en_un_punto_se_avisan`, `test_seis_tramos_informa_seis`,
`test_cruz_de_cuatro_no_se_avisa`, `test_gravedad_no_se_avisa`,
`test_utilidad_a_otra_cota_no_cuenta`
([test_model_ops.py:345–368](../tests/test_model_ops.py#L345)).

---

## 6. Extremo con extremo y cotas distintas

### E19 · Extremo con extremo, misma cota
- **App:** conflicto (misma cota). El mensaje dice que **se unen con un codo** (o con
  una reducción si cambia el diámetro) y a qué cota.
- **Civil 3D:** se unen con un codo de 60°.
- **Decisión del usuario:** el mensaje no debe decir «sin accesorio»; debe decir que
  se unen **con un codo**. Si siguen casi en línea recta (≤ 1°) es una unión recta,
  pero el texto igualmente habla de «un codo sólido».

**Dónde se valida:** `_union_civil` en [app_window.py:4295](../app/app_window.py#L4295)
(textos por tipo de accesorio, incluido `"recto"`).

### E20 · Extremo con extremo, diferencia de 0.08 ft
- **App:** conflicto (≤ 0.10 ft cuenta como misma cota).
- **Civil 3D:** se unen y quedan al **promedio** (`[COTAS] cotas unificadas`).

**Dónde se valida:** paso de cotas de juntura en
[ImportarRed.cs:2652](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L2652).

### E21 y E49 · Extremo con extremo sin altura para una vertical
- **Situación:** las dos tuberías terminan en el mismo punto a distinta cota
  (0.15 ft en E21, 0.5 ft en E49), pero el desnivel es **menor** que el necesario
  para bajar con dos codos de 90° (**2 × 1.57·D + 0.05 ft**).
- **App:** **▲ alerta roja** (no una sugerencia) «no hay espacio para una vertical».
- **Civil 3D (`[UNION-PENDIENTE]`):**
  - Si tienen **largos distintos** (E49: 38 / 10 ft): la **más larga toma pendiente**
    hasta la cota de la otra y se unen con un codo.
  - Si tienen **el mismo largo** (±2 %, E21): **las dos** van a la cota del punto medio.
- **Decisiones del usuario:** la más larga toma la pendiente; si miden lo mismo, las
  dos; es alerta roja, no recomendación.

**Dónde se valida:** `desnivel_min_dos_codos_ft` y `union_con_pendiente` en
[model_ops.py:665](../app/model_ops.py#L665) y [model_ops.py:672](../app/model_ops.py#L672)
(test `test_union_con_pendiente_extremo_con_extremo`,
[test_model_ops.py:444](../tests/test_model_ops.py#L444)); plugin: `UnionConPendiente` en
[ImportarRed.cs:3767](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L3767), llamada en
[ImportarRed.cs:2614](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L2614).

### E22 · Escalón en el propio vértice (-4.0 / -5.0)
- **Situación:** la cota con la que llega un tramo y la con que sale el siguiente
  son distintas en el mismo vértice.
- **App:** **▲ alerta roja** «escalón… se unirán a -4.50».
- **Civil 3D:** `[COTAS] cotas unificadas a -4.50` (promedio).
- En **gravedad** no se avisa (el buzón absorbe el escalón).

**Dónde se valida:** `escalones_en_vertices` en [model_ops.py:766](../app/model_ops.py#L766)
(tests `test_escalon_en_agua_se_avisa_con_el_promedio`,
`test_escalon_en_gravedad_no_se_avisa`, `test_diferencia_minima_no_es_escalon`,
[test_model_ops.py:398–415](../tests/test_model_ops.py#L398)).

---

## 7. Cruces entre utilidades

| Caso | Situación | App | Civil 3D |
|---|---|---|---|
| **E24** | Agua × drenaje a distinta cota | sin marcador | sin conexión |
| **E25** | Agua × drenaje a la **misma** cota | sin marcador (el drenaje no es red a presión) | sin conexión |
| **E28** | Gas × agua a la misma cota | **▲ «redes distintas»** | sin conexión |
| **E26** | Eléctrico × eléctrico a distinta cota | sin marcador (no es red a presión) | sin conexión |
| **E27** | Agua × agua a distinta cota, sin aprobar | **sugerencia ↕** | sin vertical |
| **E48** | Agua × agua cruzándose **en X** a la misma cota | conflicto | **sin conexión** |

**Decisiones:**
- Utilidades de **distinto tipo** nunca se unen. Si son **dos redes a presión** (agua ×
  gas) y chocan a la misma cota, alerta roja «redes distintas» para que el usuario mueva
  una. Si una de las dos no es a presión (p. ej. agua × drenaje, E25), no hay señal
  (ver §2, «Señales solo en redes a presión»).
- Un **cruce en X a mitad de tramo** (dos tubos que siguen de largo) **no se une**:
  solo se unen tuberías que **terminan** en el punto o comparten un vértice.

**Dónde se valida:** mensaje `_msg_redes` en [app_window.py:4290](../app/app_window.py#L4290)
y regla del cruce en X en [app_window.py:4307](../app/app_window.py#L4307); plugin:
[ImportarRed.cs:4274](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L4274).

---

## 8. Conexiones verticales aprobadas

Cuando dos tuberías de la misma red se tocan a distinta cota, el usuario puede
**aprobar** una conexión vertical. Lo que construye Civil 3D según el caso:

| Caso | Situación | Civil 3D |
|---|---|---|
| **E29** | Cruce recto × recto | TEE + TEE + tubo vertical |
| **E30** | Extremo sobre tramo recto | CODO abajo + TEE arriba + vertical |
| **E31** | Extremo sobre un **quiebre** | WYE + tubo auxiliar de 1 ft + codos + vertical |
| **E32** | Extremo con extremo | CODO + CODO + vertical |
| **E34** | Quiebre + extremo; termina la de **arriba** | WYE abajo, la vertical **sube** |
| **E35** | Cruce Ø24 × Ø12 | Vertical del diámetro **menor** (Ø12); TEE de arriba reductora |

### E33 · Quiebre + extremo aprobado, pero sin altura para los codos (Δz 2 ft)
- **App:** aprobado ✓ **+ ▲ alerta roja** «conexión con pendiente».
- **Civil 3D:** **WYE con el ramal inclinado** (sin codos ni vertical) y la tubería
  que termina recibe **pendiente** hasta la Wye.
- **Decisión del usuario:** Wye + accesorio con pendiente + tubería con un poco de
  pendiente, con alerta roja.

**Dónde se valida:** `conexion_vertical_inclinada` en [model_ops.py:725](../app/model_ops.py#L725);
plugin: `CrearCruceConWye` (caso inclinado) en
[ImportarRed.cs:5028](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L5028).

### E50 · Extremo con extremo en línea (misma dirección), aprobado
- **Situación reportada:** una tubería termina donde empieza la otra, en la misma
  dirección; el codo salía **girado** hacia otro lado.
- **Causa:** (1) el plugin tomaba la tubería por su posición en la lista y no por su
  número; (2) una tubería empezaba con un tramito de pocas pulgadas (doble clic) y el
  codo se orientaba con ese tramito.
- **Decisión:** cada codo mira **hacia su propia tubería**, usando el primer vértice
  que esté realmente lejos del punto de unión.

**Dónde se valida:** `ResolverTuboCruce` (busca por `PIPE_IDX` y comprueba que pase por
el cruce) y `DireccionAlejandoseDelCruce` en
[ImportarRed.cs:4929](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L4929) y
[ImportarRed.cs:4977](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L4977); las 8
conexiones aprobadas de la tanda E se cuentan en `test_guarda_sin_pdf_y_reabre_igual`
y `test_exporta_dxf` ([test_escenarios.py](../tests/escenarios/test_escenarios.py)).

---

## 9. Nombres de red

### E36 · Dos tramos con el mismo nombre («Linea Norte»)
- **Civil 3D:** se crea la red «Linea Norte» (no «RED-AGUA»).

### E38 (renombradas) · Misma utilidad, nombres distintos
- **Situación:** dos tuberías de agua que se tocan pero se llaman distinto.
- **Decisión del usuario:** **el nombre no debe influir**: se unen igual. Civil 3D
  las pone en **la misma red** (toma el nombre de la de menor número que tenga
  nombre; si ninguna tiene, «RED-<tipo>»). El nombre se usa solo en los mensajes.

**Dónde se valida:** `red_de` y `red_civil_de_union` en
[model_ops.py:499](../app/model_ops.py#L499) y [model_ops.py:506](../app/model_ops.py#L506)
(test `test_red_de_usa_nombre_y_si_no_la_capa`,
[test_model_ops.py:419](../tests/test_model_ops.py#L419)); plugin: `RedesUnidasPorContacto` en
[ImportarRed.cs:4243](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L4243); en el DXF,
`test_exporta_dxf` comprueba `NET_NAME=Linea Norte`.

---

## 10. Otros casos de control

| Caso | Situación | Resultado |
|---|---|---|
| **E37** | Utilidad abandonada | Sin marcadores; en Civil 3D, estilo 3D **discontinuo** |
| **E40** | Drenaje (gravedad) con quiebres | Buzones automáticos en cada vértice, sin cambios |

**Dónde se valida:** celdas E37 y E40 de
[generar_escenarios.py](../tests/escenarios/generar_escenarios.py).

### Eléctrico y telecomunicaciones: los vértices nunca son cajas

- **Situación:** en las líneas eléctricas y de telecom, los vértices (quiebres,
  esquinas, extremos, llegadas a una bóveda) se convertían en cajas (CAJA-). En líneas
  reconocidas del PDF, cualquier vértice que el reconocimiento marcaba como «llega a una
  bóveda» recibía una caja aunque ahí no hubiera ninguna bóveda reconocida. Por ejemplo,
  en el DU06, 36 de las 73 cajas del eléctrico estaban en vértices sin bóveda.
- **Decisión del usuario (2026-09-28):** en los dos flujos (dibujo a mano y
  digitalización del PDF), **un vértice de la utilidad nunca se reconoce ni se agrega
  automáticamente como buzón o caja**. Lo que **sí** está bien es la caja que sale de una
  **bóveda reconocida en sus capas** (manhole, vault, pull box… del reconocimiento).
- **Cómo queda:**
  - Dibujo a mano: ninguna caja automática. Si hace falta una, el usuario la inserta
    (Herramientas → «Insertar buzón en línea…»).
  - Reconocimiento: **una caja por cada bóveda reconocida**, con su forma y sus
    medidas. Si una línea llega a esa bóveda, la caja se coloca en el vértice por donde
    llega, para que en Civil 3D la línea quede **conectada** a ella (el plugin solo usa
    una caja si está a ≤ 1 ft de un vértice; en los demás vértices pone una «Estructura
    nula» invisible). Una bóveda sin línea entra como caja suelta, igual que antes.
  - Los codos reconocidos siguen como marca **CV** con su radio: son la esquina de la
    curva, no una caja.
  - Proyectos ya guardados: sus cajas existentes se conservan tal cual (pueden ser del
    usuario). Al volver a importar el PDF ya salen con la regla nueva.
- Gravedad (drenaje, alcantarillado) no cambia: buzón en cada vértice.

**Dónde se valida:** `rebuild_structures` (conduit nunca crea en vértices) en
[model_ops.py:81](../app/model_ops.py#L81); `attach_vault_geometry` (la caja nace de la
bóveda reconocida) y `_vertice_de_boveda` (vértice de llegada) en
[model_ops.py:292](../app/model_ops.py#L292) y [model_ops.py:376](../app/model_ops.py#L376);
la importación le pasa las líneas de esa utilidad en `Main._import_recognized_pipes`
([app_window.py:2126](../app/app_window.py#L2126)). Tests
`test_conduit_nunca_pone_cajas_en_sus_vertices` y
`test_conduit_caja_solo_de_boveda_reconocida`
([test_model_ops.py:260](../tests/test_model_ops.py#L260) y
[L276](../tests/test_model_ops.py#L276)). En el plugin, la «Estructura nula» de conduit:
`CrearRedGravedadCompleta` ([ImportarRed.cs:1230](../API-CIVIL/proyecto1/proyecto1/ImportarRed.cs#L1230)).

---

## 11. Datos que viajan con cada accesorio (Property Set)

Cada sólido de accesorio (codo, tee, wye, cruz, reducción) lleva en Civil 3D un
Property Set **`PDFCAD_Accesorio`** con el **tipo** («Codo», «Tee», «Wye», «Cruz»,
«Reducción»), el **ángulo** y tres campos más, para poder consultarlo y filtrarlo.

**Dónde se valida:** `AccesorioPropertySet.AplicarDesdeXData` en
[AccesorioPropertySet.cs:48](../API-CIVIL/proyecto1/proyecto1/AccesorioPropertySet.cs#L48).

---

## 12. Casos límite documentados (C01–C26, F01–F10)

La segunda tanda ([generar_escenarios_complejos.py](../tests/escenarios/generar_escenarios_complejos.py))
**documenta el comportamiento actual** en situaciones difíciles, incluidas las que
aún no tienen una solución definitiva («NO CONTEMPLADO»). Sirve de referencia al
decidir mejoras futuras. Las cifras de cada celda salen de las mismas fórmulas que
el plugin (el test `test_espejo_de_wyesolido` falla si el plugin cambia sus constantes).

### Accesorios sólidos en situaciones difíciles (C01–C26)

| Caso | Situación | Comportamiento | Pendiente / nota |
|---|---|---|---|
| C01 | Serpentín de codos con tramos cada vez más cortos | Aviso «Tubo demasiado corto» desde 2.7 ft | Codos vecinos se solapan en tramos < 3.14 ft (E39 ya lo resuelve en presión con un solo codo) |
| C02 | Codo 3D (giro en planta + punto bajo) | Codo medido en 3D, en plano inclinado | — |
| C03 | Recto en planta con punto bajo (sifón) | Codo en plano vertical | — |
| C04 | Quiebres de 0.5° y 1.5° | ≤1°: sin pieza; 1–2°: manguito recto | El manguito de 1–2° no existe en obra |
| C05 | Retorno de 179° | Aviso «casi superpuestos» + manguito | Casi seguro un error de trazado |
| C06 | Codo 90° Ø48 con tramos de 4 ft | «Tubo demasiado corto» ×2 | — |
| C07 | Escalón de 6 ft en el vértice de un codo | Cotas unificadas al promedio | Una caída debería ser vertical con 2 codos |
| C08 | Y rasante (ramal a 8°) | Brazos alargados a ~9 ft | Falta ángulo mínimo o aviso |
| C09 | Y con 3 diámetros (Ø18/12/8) | Pieza excéntrica, bocas coaxiales | — |
| C10 | Tronco quebrado 30° + ramal 90° | WYE (no TEE) | En obra sería Tee + codo |
| C11 | Ramal 1 ft más alto que el tronco | Sugerencia; no se unen | — |
| C12 | Dos Y a 3 ft | 2 WYE; la 2.ª avisa tubo corto | Se solapan 0.63 ft sin aviso |
| C13 | Y sobre tronco con 10 % de pendiente | Brazos del tronco horizontales | La pieza debería inclinarse entera |
| C14 | Tronco quebrado 19° / 21° | 19° → TEE, 21° → WYE (corte en 160°) | — |
| C15 | Tee Ø36 / ramal Ø4 | Ramal a la altura de su eje, campana fuera del tronco | — |
| C16 | Ramal de 1 ft | «Tubo demasiado corto» | — |
| C17 | Tee en punto bajo del tronco | Desalineación de 0.07 ft por boca | Igual que C13 |
| C18 | Ramal a 60.3° / 59.5° de inclinación | Por encima de 60° el brazo sigue al tubo; por debajo, horizontal | Salto brusco en el umbral |
| C19 | Cruz oblicua (0°/70°/180°/250°) | Cae a la cruz de catálogo | Cruz sólida oblicua no implementada |
| C20 | Tee entre «Linea Este» y «Ramal Sur» | *(texto de la celda anterior a la decisión E38)* | **Superado:** con `RedesUnidasPorContacto` la misma utilidad se une aunque el nombre sea distinto (§9) |
| C21 | Cruce aprobado sobre un quiebre de la superior | Codo + 2 TEE + vertical | Quiebre + tubería que pasa no tiene tratamiento propio |
| C22 | Cruce aprobado con quiebre en las dos | 4 sólidos en el punto | Igual que C21 |
| C23 | Tres utilidades apiladas | Dos verticales, 2 TEE en la del medio | Falta pieza de 3 niveles |
| C24 | Dos cruces aprobados a 2 ft | Recortes que se pisan | El recorte no comprueba si alarga el tubo |
| C25 | Solo 1.5 ft entre soleras (Ø14) | Las TEE no caben | Debería rechazarse al aprobar |
| C26 | Cruce Ø6 × Ø24 | Vertical Ø6 en campana de Ø24 | El cruce usa un solo diámetro por TEE |

### Casos no contemplados (F01–F10)

| Caso | Situación | Hoy |
|---|---|---|
| F01 | Extremos a 0.6 / 0.4 ft | La app no marca ninguno; el plugin une el de 0.4 (tolerancia 0.5 ft) |
| F02 | Utilidad que se cruza a sí misma | Sin aviso |
| F03 | Dos utilidades superpuestas 30 ft | Sin aviso |
| F04 | Utilidad duplicada exacta | Manguitos «casi superpuestos» |
| F05 | Y entre activa y abandonada | Se une sin distinguir |
| F06 | Cruce a distinta cota con vértices en el punto | 4 sugerencias apiladas |
| F07 | Vértice repetido (tramo de 0 ft) | Se omite; codo normal |
| F08 | Curva suave dibujada con 30 tramos | 29 codos de 3° (falta criterio de deflexión admisible en junta) |
| F09 | Eléctrico: derivación + quiebre | Sin sólidos (conduit) y, en la app, sin señales (solo redes a presión) |
| F10 | Lista de lo no dibujable | Bajantes propias, bloques de anclaje, válvulas en extremos, reimportar en el mismo dibujo… |

**Dónde se valida:** funciones `c01`…`c26`, `f01`…`f09` y `NO_DIBUJABLES` en
[generar_escenarios_complejos.py](../tests/escenarios/generar_escenarios_complejos.py);
pruebas en [test_escenarios_complejos.py](../tests/escenarios/test_escenarios_complejos.py)
(`test_marcadores_de_la_app`, `test_marcadores_apilados`, `test_espejo_de_wyesolido`).

---

## 13. Mapa rápido: dónde está cada regla

| Decisión | App (Python) | Plugin (C#) | Prueba |
|---|---|---|---|
| Señales solo en redes a presión (agua, gas) | `Main._draw_pipe_conflicts` / `_prune_stale_cross_connections` | — | escenarios E24–E26, F09 |
| Qué accesorio va en un punto | `model_ops.accesorio_en_punto` | `RedesPresionJunturas.DecidirTipoFitting` | escenarios E01–E17 |
| Máximo 4 tuberías | `model_ops.junturas_excedidas` | `RedesPresionJunturas` (aviso «máximo de 4») | `test_cinco_tramos_…` |
| Codo cerrado / curva | — | `WyeSolido.CurvaCodo` | `test_espejo_de_wyesolido` |
| Codo de retorno | `model_ops.codos_de_retorno` | `ImportarRed.CodosDeRetorno` | `test_codos_de_retorno_…` |
| Tramo corto entre codos | `model_ops.tramos_cortos_entre_codos` | `ImportarRed.FusionarCodosSeguidos` | escenario E39 |
| Codo reductor | mensaje en `Main._union_civil` | `ReduccionSolida.CrearCodoConReduccion` | escenarios E09, E41–E43 |
| Tee/Wye reductora conectada | — | `WyeSolido.Aplanar` / `RecortarTubos` | escenarios E11, E14, E44 |
| Unión con pendiente | `model_ops.union_con_pendiente` | `ImportarRed.UnionConPendiente` | `test_union_con_pendiente_…` |
| Escalón en vértice | `model_ops.escalones_en_vertices` | paso `[COTAS]` de `ImportarRed` | `test_escalon_…` |
| Vertical inclinada (Wye) | `model_ops.conexion_vertical_inclinada` | `ImportarRed.CrearCruceConWye` | escenario E33 |
| Codo orientado en vertical | — | `ImportarRed.ResolverTuboCruce` / `DireccionAlejandoseDelCruce` | escenario E50 |
| Misma red aunque cambie el nombre | `model_ops.red_civil_de_union` | `ImportarRed.RedesUnidasPorContacto` | `test_red_de_usa_nombre_…` |
| Vértices de eléctrico/telecom nunca son caja; caja solo de bóveda reconocida | `model_ops.rebuild_structures` / `attach_vault_geometry` | «Estructura nula» en `CrearRedGravedadCompleta` | `test_conduit_nunca_pone_cajas_…`, `test_conduit_caja_solo_de_boveda_…` |
| Property Set del accesorio | — | `AccesorioPropertySet.AplicarDesdeXData` | revisión en Civil 3D |
| Todas las alertas de un escenario | `ALERTAS` / `validar` | — | `tests/escenarios/test_escenarios.py` |
