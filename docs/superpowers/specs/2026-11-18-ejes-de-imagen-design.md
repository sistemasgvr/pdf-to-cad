# Ejes de la red cuando viene como IMAGEN dentro de un PDF vectorial — diseño

Fecha: 2026-11-18. Pedido del usuario (con un script de prueba como referencia, `Downloads/extraer_ejes_azul.py`).

## 1. Intención y por qué

Los PDF «QS SD_Indian School_South/North» (drenaje de Phoenix, 18 hojas cada uno) traen los lotes, calles, cotas y
rótulos («18" HDPE», «24" RCP», «Unk») como VECTOR negro/gris, pero la RED de drenaje (trazos azules, sumideros,
círculos «B»/«DW»/«M», áreas rayadas) es una IMAGEN partida en ~600–1 750 tiras de 52 px por hoja (Indexed, 16
colores, ~4.17 px/pt ≈ 300 dpi). Por eso «Capas de la hoja» no ofrece nada azul: solo agrupa VECTORES por estilo.

Medido (hoja 4 de South): vectores = 6 866 trazos negros 0.24 pt + grises; ningún trazo de color. Paleta de las
imágenes: `#004DA8` (trazos de tubería y símbolos), `#80A6D4` (rayado de áreas de retención), blanco. Separar
`#004DA8` deja SOLO la red.

El usuario quiere: sacar de cada color de la imagen únicamente sus EJES (línea central), porque eso es lo que usa el
reconocimiento; que funcione con CUALQUIER color (no solo azul) y en cualquier escenario parecido; y decidir la
utilidad sola cuando hay certeza (nombre del PDF, leyenda, rótulos, trayectoria de la red) y PREGUNTARLE al usuario
cuando no la hay.

Corrección a CLAUDE.md (hay que arreglar la frase): dice que el drenaje de Phoenix «trae los LOTES COMO IMAGEN»; es al
revés: los lotes son vector y la red es imagen.

## 2. Objetivos

1. En una hoja SIN capas OCG que trae imágenes, cada COLOR de red de esas imágenes aparece como una capa virtual más
   («Azul #004DA8 · imagen»), con sus ejes como trazos virtuales en el mismo sistema de coordenadas que
   `pdf_styles.drawings`. Desde ahí todo sigue igual: «Capas y estilos…», asignar utilidad/rol, panel «Reconocer»,
   hoja compuesta, reconocimiento, diámetros por rótulos, DXF.
2. Cualquier color: la paleta se descubre en cada hoja (indexada exacta o tonos agrupados), nunca un azul fijo.
3. Solo ejes de lo que es LÍNEA. Lo compacto (sumideros, círculos, letras) va a capas de SÍMBOLO de la imagen; el
   rayado de áreas a una capa de RELLENO que no se ofrece como red.
4. Certeza → se asigna solo (rol líneas de esa utilidad, y estructuras si corresponde). Duda → se le pregunta al
   usuario, con los ejes resaltados; sin respuesta, esa capa no se reconoce.
5. Hoja compuesta = mismas líneas que las hojas sueltas (los ejes se calculan por hoja de ORIGEN y se llevan con la
   pieza).

## 3. No-objetivos (por ahora)

- Planos ESCANEADOS enteros (todo imagen, sin texto ni vectores): siguen yendo al dibujo a mano (`detect.py`).
- Hojas CAD CON capas OCG que además traen imágenes (fotos aéreas, logos): no se tocan.
- Leer letras DENTRO de la imagen (OCR de «B», «DW», «M»): los símbolos se clasifican por forma, no por su letra.
- Cambiar el núcleo de reconocimiento (`recognition_geom`, `recognition_ink_lines`) más allá de lo indispensable.

## 4. Anti-objetivos (fracaso aunque «funcione»)

- **Inventar tramos.** Nada de cerrar huecos con morfología (el `MORPH_CLOSE` del script de referencia): pega
  paralelas cercanas, une la línea con el sumidero o el texto de al lado y borra la diferencia entre un hueco real y
  uno cerrado a la fuerza. La unión de trazos la hace el reconocimiento, con evidencia.
- **Una foto aérea o un logo convertido en miles de «ejes».** Una imagen fotográfica (tonos continuos) no genera capas.
- **Asignar mal en silencio.** Si la evidencia se contradice, se pregunta; nunca se elige «la más probable» sin decir.
- **Romper lo que ya funciona.** Hojas sin imágenes de red (Phoenix agua/alcantarillado, Southwest Gas, DU06/08/10,
  LABOE) dan EXACTAMENTE lo mismo que hoy (foto antes/después = 0 diferencias).
- **Congelar la ventana.** Todo el trabajo de imagen va en el proceso trabajador, con avance y cancelable.

## 5. Restricciones

- Lógica PURA en `app/hoja/` (sin Qt): extracción y certeza testeables sin ventana. numpy + opencv + scikit-image ya
  están en `requirements.txt`; si se usa algo de skimage/cv2 en un trabajo «mod:fn», va a `hiddenimports` de
  `PDF-a-CAD.spec` y a `autoprueba.MODULOS_POR_NOMBRE`.
- No modificar el PDF de origen. Nada a disco salvo temporales/cachés ya existentes.
- Coordenadas: las mismas de `get_drawings` de esa hoja (ojo `/Rotate 90` en estos PDF: probar que un eje cae encima
  del rótulo vectorial que lo acompaña).
- Archivos < 500 líneas; español en código y UI; textos visibles con `t()` y su traducción en `i18n_en.py`.
- Toda decisión automática se puede cambiar a mano (como lo que asigna una leyenda: `leyenda_mapa.CLAVE_LEYENDA`).

## 6. Enfoques considerados

- **A. Cerrar huecos + esqueleto de todo el color (script de referencia).** Simple y deja líneas continuas, pero el
  tamaño de cierre depende del plano e inventa uniones (paralelas, símbolo, texto). Descartado por el anti-objetivo 1.
- **B. Esqueleto por mancha, sin cerrar huecos; la app une con evidencia (ELEGIDO por el usuario: «la más completa»).**
  Cada mancha alargada de un color → su eje simplificado como trazo virtual de su capa; lo compacto → símbolo; los
  rayados → relleno. Los trazos se unen en el reconocimiento de siempre (patrón de guiones, letra en el hueco,
  bóveda; o «tinta = eje» si la capa es continua). Reutiliza todo y no inventa.
- **C. Pipeline ráster con Hough (`raster_pipeline.py`).** Solo rectas, sin curvas ni nodos, poco preciso. Descartado.

## 7. Diseño (enfoque B)

### 7.1 Dónde se engancha

`pdf_styles._drawings` (rama SIN capas) ya agrega trazos virtuales al final (símbolos de la leyenda,
`simbolos_fuente`). Se suma una tercera fuente, `hoja/imagen_ejes.capas(page)` memorizada con `pdf_styles.memo`
(una vez por hoja dentro de `lectura_unica`), que devuelve trazos con forma de `get_drawings`:

- `type "s"`, `color` = color representativo del grupo (0–1), `width` = grosor medido del trazo en pt (para que
  `recognition_ink_lines.simplify_tol` = medio grosor funcione), `items` = segmentos del eje, `rect`, `seqno` propio
  (que no choque con los nativos), y `layer` = capa virtual.
- Nombres de capa (nuevos, con `pdf_styles.PREFIX`): línea `PDF_STYLE:["img","line",[r,g,b]]`, símbolo
  `PDF_STYLE:["img","sym",[r,g,b],<forma>]`, relleno `PDF_STYLE:["img","fill",[r,g,b]]`. `style_label` los nombra
  «Azul #004DA8 · imagen», «Símbolo azul (cuadro 4×4 pt) · imagen», «Relleno azul claro · imagen». Helpers
  `es_imagen(name)`, `tipo_imagen(name)`.
- Los símbolos se emiten como círculos virtuales en su lugar (igual que `simbolos_fuente._circulo`), así el rol
  «Estructuras/Buzones» los toma como hoy.
- Los rellenos se listan (para que el usuario los vea) pero no se marcan como línea ni se reconocen salvo que el
  usuario los asigne.

Cuándo corre: hoja SIN OCG con al menos una imagen «gráfica» (§7.3) que cubra un área no trivial. En cualquier otra
hoja `capas` devuelve `[]` sin decodificar nada (rápido: solo `get_image_info`).

### 7.2 Leer la imagen de la hoja

Se arma, POR HOJA DE ORIGEN, una imagen de SOLO las imágenes (sin vectores ni texto) a la resolución nativa de las
imágenes (px/pt = ancho de la imagen / su lado en pt; tope de memoria con teselas). Debe respetar transformación,
giro, recortes (clip) y máscaras que el PDF aplica a cada imagen. Cómo dibujarla lo decide quien construye (p. ej.
copiar la hoja a un documento temporal y quitar vectores/texto con redacciones, o componer las imágenes decodificadas
con su matriz), con dos pruebas obligatorias: (a) donde hay un vector negro encima de un trazo azul, el azul sigue
entero; (b) el resultado coincide píxel a píxel (±1 px) con un render normal de la hoja en las zonas de color.

Trabajo pesado: dentro del proceso trabajador de la interpretación/reconocimiento (`proceso`), con `nucleo.avance`
(«Leyendo la imagen de la hoja… k de n»), cancelable. Caché por (sha1 del PDF, hoja) en memoria del trabajador, y si
conviene en la caché de lectura del documento.

Hoja compuesta: NO se lee la imagen materializada; se toman los ejes de cada hoja de ORIGEN (caché) y se llevan con
`composite.piece_map` de la pieza, recortados a su clip/polígono (como `recortes_de_piezas`). Así compuesta = sueltas.

### 7.3 Descubrir los colores (cualquier plano)

- Imagen indexada (como estas): la paleta exacta; cada color con píxeles suficientes es candidato.
- Imagen RGB/JPEG: agrupar tonos en Lab (k-means o mean-shift; el método lo elige quien construye) y asignar cada
  píxel al grupo más cercano dentro de un ΔE; el antialias (píxel entre fondo y tinta) no cuenta.
- Fuera siempre: el fondo (blanco/casi blanco, y el color dominante de la imagen si es papel). Negros/grises de la
  imagen SÍ se procesan (otro plano puede traer la red negra en imagen), pero su capa nunca se asigna sola por color
  (§7.5).
- Imagen fotográfica (muchos tonos sin grupos dominantes: p. ej. los N grupos principales cubren < X % de los píxeles
  no-fondo, o histograma de tonos continuo): se salta entera. Umbrales a medir.

### 7.4 De cada color: líneas, símbolos y rellenos

Por máscara de color, componentes conexas (8-vecinos). Para cada una: esqueleto (sin cerrar huecos), largo L del
esqueleto, grosor medio w = área / L, nº de ramas y nudos.

- **Línea**: alargada (L ≥ k·w; k a medir, p. ej. 3). Eje = esqueleto podado de espolones cortos (< ~1.5·w),
  recorrido en tramos entre puntas/nudos, simplificado (Douglas–Peucker ≈ ¼ de w, nunca más de 0.5 pt) y con cada
  punta ALARGADA medio grosor (w/2) en su rumbo: el esqueleto acorta el trazo y el núcleo aprende el patrón de
  guiones por su largo. Un trazo con ramas = varios trazos que comparten el punto del nudo.
- **Símbolo**: compacta (no alargada) o una zona densa en nudos (rejilla del sumidero). Si un símbolo toca una línea
  (sumidero sobre la tubería), se separa: la parte densa = símbolo, las ramas largas que salen = línea hasta el borde
  del símbolo. Los símbolos se agrupan por FORMA (tamaño ±15 %, relación de lados, momentos de Hu) → una capa por
  forma y color.
- **Relleno**: muchas líneas finas, cortas y PARALELAS dentro de una región (rayado) → capa de relleno de ese color;
  no se emite como línea. Un color cuyos componentes son casi todo rayado es «relleno» entero (el azul claro de aquí).
- Ruido: componentes de pocos píxeles fuera.

Validación del enfoque B (medir antes de seguir): en las 36 hojas de Phoenix SD los trazos que salen de un trazo
discontinuo deben dejar que `recognition_geom.learn_pattern` aprenda el patrón (largos de guión/hueco consistentes),
o que la capa se reconozca como continua por `recognition_ink_lines.continuous_layer`. Si el núcleo no los une bien,
el ajuste va en la EXTRACCIÓN (largos, grosor), no en el núcleo.

### 7.5 ¿De qué utilidad es? Certeza o pregunta

Se amplía `hoja/estilos_sugeridos` (ya decide la red en hojas sin capas ni leyenda por el texto y los rótulos) para
que incluya las capas de imagen y nuevas evidencias. Por cada capa de LÍNEA de imagen se juntan:

1. **Nombre del PDF** (`composicion_hermanos.utilidad`: «QS SD_…» → DRENAJE). En la hoja compuesta, el de las hojas
   de ORIGEN de esa pieza.
2. **Leyenda del PDF**: si `leyenda_mapa`/`pdf_legend` tienen una fila cuya MUESTRA es de ese color (muestras en
   imagen incluidas: el color de los píxeles de la muestra), su utilidad.
3. **Texto del plano** (`utilidad_de_texto`: «STORM DRAIN», «SEWER»…).
4. **Rótulos de tubería junto a los ejes** («18" HDPE», «24" RCP»): votan que ESA capa es una red; los que nombran
   una utilidad o código («WATER», «W», «SS») votan por esa utilidad; los materiales solo acotan (RCP/HDPE/CMP →
   drenaje o alcantarillado, nunca agua/gas eléctrico solos).
5. **Trayectoria**: símbolos de la imagen en las puntas/quiebres de los ejes (sumideros, buzones), ramales cortos
   que nacen de la principal hacia un símbolo, red que corre a lo largo de las calles. Solo suma o resta confianza;
   no decide sola.

**Seguro** (se aplica solo, viaja como lo que asigna una leyenda): hay UNA utilidad candidata con evidencia de 1, 2 o
3; esa capa es «la red» (la única capa de línea de color de la hoja con ejes, o la elegida por los rótulos de 4); y
ninguna evidencia la contradice. Entonces: capa de línea → rol líneas de esa utilidad; capas de SÍMBOLO de ese color
que caen en las puntas/vértices de sus ejes (≥ una fracción a medir) → rol estructuras de esa utilidad. Negro/gris de
imagen: nunca seguro por sí solo (necesita leyenda o rótulos que apunten a esa capa).

**Dudoso** (cualquier otro caso: varias capas de color y el nombre justifica una sola, evidencias contradictorias, o
ninguna): la capa queda «?» y se le pregunta al usuario (§7.6). Sin respuesta, no se reconoce.

Phoenix SD: nombre → DRENAJE, una sola capa de línea de color (`#004DA8`), rótulos HDPE/RCP junto a ella, sumideros en
sus puntas, nada en contra → **seguro**: drenaje sin preguntar. `#80A6D4` = relleno → no se ofrece como red.

`Sugerencia` gana un campo con el detalle por capa (utilidad, seguro/dudoso, evidencias a favor y en contra) para que
la interfaz lo muestre y `roles_iniciales` lo aplique igual que hoy aplica `lineas`.

### 7.6 Preguntarle al usuario

En el flujo actual (abrir PDF → editor → la hoja se interpreta → panel «Reconocer»):

- Panel «Reconocer»: una tarjeta por capa dudosa: muestra del color + «Hay líneas en la imagen de la hoja que no sé
  de qué red son», el porqué en una frase (p. ej. «el nombre del PDF dice drenaje pero hay dos colores de línea»),
  botones con las utilidades candidatas primero + «Otra…» + «No es una red», y ⌖ que resalta sus ejes en el plano.
  Elegir = asignar rol líneas (y sus símbolos, si caen en sus puntas) y la fila de esa utilidad queda lista para ▶.
- «Capas y estilos…»: la capa aparece con «?» y el mismo porqué en el globo; asignarla ahí también responde.
- Lo seguro también se ve (no es invisible): en el panel, la fila de la utilidad dice «asignada por: nombre del PDF,
  rótulos» y se puede cambiar.
- La respuesta vale para todas las hojas del MISMO PDF con ese color (clave: sha1 del PDF + capa) y se guarda en el
  `.digproj` junto a los roles; otro PDF vuelve a decidir.

### 7.7 Lo que no cambia

Reconocimiento, rutas, codos, ángulos a 0.25°, diámetros (`recognition_grosor_registros`/`_mapa` ya leen «18"
HDPE», RCP, RGRCP, CMP, PVC), DXF y Civil 3D reciben trazos como cualquier capa por estilo. Verificar en la práctica
que el diámetro se asigna con ejes de imagen (los rótulos son vector negro; las líneas, de imagen).

## 8. Pruebas y medición

- Sintéticas (PDF generado): imagen indexada y RGB con trazos de un color sobre vectores negros; trazo continuo,
  discontinuo, curva, «T», símbolo sobre la línea, rayado, foto (no genera nada), hoja girada 90°, hoja sin imágenes
  (= hoy). Ejes a ≤ ¼ px del centro del trazo dibujado.
- Phoenix SD South/North (36 hojas): nº de líneas, cobertura de la tinta del color por los ejes (≥ 97 %), 0 tramos
  sin tinta debajo (auditoría tipo `audit_sin_tinta` contra la máscara), diámetros leídos, asignación automática =
  DRENAJE sin preguntar; hoja compuesta de 2–4 hojas = mismas líneas que sueltas.
- Un caso dudoso sintético (dos colores de línea, nombre neutro) → pregunta; responder → se reconoce.
- Foto antes/después de las hojas SIN imágenes de red (Phoenix agua/alcantarillado, Southwest Gas, DU06, LABOE):
  0 diferencias.
- Tiempo por hoja medido (objetivo a fijar tras medir la primera versión; la ventana nunca se traba > ~0.5 s).

## 8b. Decisiones tras la revisión del diseño

1. **Camino de la leyenda.** Las hojas SD NO caen en el camino de la leyenda de mapa: `leyenda_mapa.aplica` da False
   (texto TrueType de verdad, no Type3). Por eso van por `estilos_sugeridos` / `roles_iniciales`, como Southwest Gas.
   Si algún día una hoja con leyenda de mapa trae la red en imagen, la evidencia 2 de §7.5 (muestra del color en la
   leyenda) entra por `leyenda_mapa.asignaciones`. Hoy no hay un PDF así: queda como caso sintético, no como requisito.
   Ojo: estas hojas también usan `ESRIDefaultMarker`, así que `simbolos_fuente` ya les agrega capas de glifos. Las capas
   de imagen se suman a esas sin reemplazarlas.
2. **Una utilidad POR CAPA (mi decisión).** Las capas de imagen compiten con los estilos de color vectoriales de la
   misma hoja: «la única capa de línea de color» cuenta las dos clases. `Sugerencia` pasa a tener un detalle por capa
   (capa → utilidad, seguro/dudoso, evidencias), y `utilidad`/`lineas` de hoy se conservan para lo vectorial. Así,
   gas vectorial + drenaje en imagen queda bien. Lo que `interpretacion_guardada` permita guardar se amplía con esa
   clase.
3. **El mismo color en todas partes (mi decisión).** Si la imagen es indexada, el nombre de la capa lleva el color
   EXACTO de la paleta. Si es RGB, lleva el centro del grupo redondeado a una rejilla de 1/32 por canal (8 niveles
   de 0–255). En la hoja compuesta, las capas de imagen de distintas piezas cuyo color difiere ≤ ΔE pequeño se juntan
   como gemelas, igual que `leyenda_piezas.equivalencias` / `pdf_styles.gemelos`. La respuesta del usuario se guarda
   con ese nombre normalizado.
4. **Herencia entre hojas (mi decisión).**
   - Lo automático «seguro» se recalcula en cada hoja y viaja como lo que asigna una leyenda (`CLAVE_LEYENDA`).
   - La respuesta del usuario es una asignación A MANO: con `SUMAR_LEYENDA` pasa a las otras hojas. Además se guarda
     en un mapa nuevo del proyecto, {sha1 del PDF: {capa: utilidad o «no es red»}], que se aplica a cualquier hoja de
     ese PDF. Va al `.digproj` y a `respaldo_editor.CLAVES`, para que «Cancelar» lo deje como estaba.
5. **Dónde se ven los ejes (mi decisión).** Van en `pdf_styles.drawings`, porque los necesitan «Capas», la
   interpretación y el reconocimiento. Pero la composición sugerida (`Ficha`), el encaje y el calcado de «Agregar
   utilidad», `trim_border` y los anclajes del compositor los FILTRAN (`es_imagen`), así el calcado de SD que ya
   funciona no cambia. Se suma la foto antes/después de componer y de agregar con SD.
6. **Símbolos de la imagen (mi decisión).** Igual que los buzones-símbolo de los mapas (`recognition_map_vaults`):
   un símbolo con rol estructuras que cae en una punta o vértice del eje (o que el eje atraviesa) se vuelve vértice
   «vault» de la línea. Un símbolo sin línea entra como caja suelta, como cualquier bóveda reconocida sin línea. No
   se crea nada más de lo que la red de gravedad ya crea en sus vértices.

## 9. Lo que queda a quien construye

Cómo dibujar «solo las imágenes» (§7.2); método de agrupación de colores para RGB y los umbrales (fondo, ΔE,
fotográfica); k de «alargada», poda de espolones, separación símbolo/línea y detección de rayado (§7.4); firma de
forma de los símbolos; la fracción de símbolos en puntas que cuenta como trayectoria; formato exacto del detalle de
evidencias; diseño visual de la tarjeta de pregunta dentro del estilo del panel (texto arriba, botones debajo);
nombres de módulos (`hoja/imagen_ejes.py` + uno de clasificación/esqueleto si pasa de 500 líneas).
