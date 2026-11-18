# Georreferencia automática por lo que dice la hoja — diseño

2026-11-18. Primera fuente: cuartos de sección (QS) de la ciudad de Phoenix.

## Para qué

Que al componer una hoja de mapas el proyecto quede georreferenciado solo, sin clics, para que cada
utilidad, venga del PDF que venga, caiga en su lugar del mapa real y sin armar composiciones a mano. El
usuario lo pidió así. También recordó que cada empresa de utilidad dibuja distinto: la solución no puede
ser solo para Phoenix. Phoenix es el primer caso, no el único.

## Objetivos, no-objetivos y lo que no puede pasar

- Objetivo: una hoja (o una hoja compuesta) cuyas piezas dicen en qué lugar del mundo están queda con
  `Georef` activo, en el sistema real, con su error medido a la vista.
- Objetivo: agregar otra fuente (otra ciudad, otro índice, GeoPDF, PLSS…) sin tocar el flujo, solo con
  datos o con una fuente nueva.
- No-objetivo (ahora): corregir la composición con las coordenadas. Water South compone con 80 ft de
  error y la georreferencia lo detecta, pero no lo arregla. Queda como paso siguiente.
- No-objetivo: consultar internet al usar la app. Los datos van con la app.
- No puede pasar: que un plano sin datos de ubicación cambie (CAD como DU06), que se pise una
  georreferencia hecha a mano, que se aplique una ubicación dudosa en silencio, ni que un «17-10» de
  otra ciudad se tome por el de Phoenix.

## Lo que se midió (datos en las notas `georef-qs/`)

- La capa pública es `maps.phoenix.gov/pub/rest/services/Public/STR_QSMapIndex/MapServer/0`, con
  4 359 polígonos (3 708 con número). El sistema es EPSG 2868 = NAD83(HARN) / Arizona Central en pie
  internacional; en Civil 3D es `AZHP-CIF` (`sistemas_cs.codigo_civil3d`). La fila crece hacia el norte
  y la columna hacia el este. Los cuadros no son cuadrados exactos: miden 2 630–2 700 ft y algunos lados
  van inclinados hasta 0.4°, por eso se guarda el polígono. Cada cuadro trae su sección PLSS
  (T, R, SEC, 1/4).
- Cada hoja de Phoenix tiene un recuadro de ~2 800 ft centrado en su cuadro, con el norte arriba.
  Centro del recuadro (`composicion_encaje.caja`) contra el centroide del cuadro, sobre la composición
  sugerida: Sewer North 18 hojas RMS 4.2 ft (máximo 10.6), Water North 16 hojas 4.1 ft, giro 0.000°.
  Water South 80 ft, por el error encadenado de su composición. A la vista (Sewer North 17-12), el
  contorno real cae sobre los ejes de las calles, con las esquinas a 0–18 ft.
- El cajetín dice además «NE 1/4 SEC.26, T.2N, R.1E», y coincide con el PLSS del cuadro 16-10.

## Enfoques

1. **Elegido — fuentes enchufables + centro de la pieza ↔ lugar conocido.** Cada fuente mira una
   pieza y, si la reconoce, da pares hoja ↔ mundo. Phoenix QS da el centro del recuadro ↔ el centroide
   del cuadro. Un solo ajuste por similaridad (`georef.fit`) sobre todas las piezas. Es general, se mide
   y es simple.
2. Esquinas del cuadro buscadas en el dibujo (cruces de calles). Sería más exacto en teoría, pero es
   frágil según cómo dibuje cada empresa, y la ganancia es poca frente a 4 ft.
3. Consultar la capa en línea. Descartado: nada de red al usar la app.

## Cómo es

### Fuentes (`app/geo/auto/`, PURO, sin Qt)

- `fuentes.py`: `Ancla(hoja_pt, mundo, peso, motivo)` y `Ubicacion(epsg, cs_code, anclas, fuente,
  etiqueta)`. Cada fuente es una función `ubicar(page, ficha) -> Optional[Ubicacion]`, registrada en
  una lista ordenada. La primera que responde gana para esa pieza.
- `indice_mapas.py`: fuente genérica de **índice de mapas en cuadrícula**, que lee un archivo de datos
  por jurisdicción: `app/geo/indices/<id>.json.gz` con `{id, nombre, epsg, unidad, patron_etiqueta,
  confirmar: {palabras, plss}, fecha, fuente_url, celdas: {"17-10": {poligono, plss}}}`. Para otra ciudad
  basta otro archivo, sin código nuevo. Phoenix = `phoenix_qs.json.gz` (~300 KB comprimido).
- **Confirmación de jurisdicción** (para que un «17-10» de otra ciudad no se tome por el de Phoenix):
  la celda vale solo si el texto de la hoja (`get_text` o `texto_pdf.corridas` para Type3) trae el PLSS
  de esa celda («NE 1/4 SEC.26, T.2N, R.1E»), o en su defecto las palabras de la jurisdicción («City of
  Phoenix»). Sin confirmación no hay ancla.
- Ancla Phoenix: el centro de `composicion_encaje.caja(ficha)` → el centroide del polígono. Sin
  recuadro hallado (hoy, las hojas SD), no hay ancla.
- `ajuste.py`: piezas de la hoja compuesta → `piece_map` lleva cada ancla a pt de la hoja de trabajo y
  luego a px del lienzo (× zoom). Con ≥2 anclas, `georef.fit(kind="similarity")`. Con 1 ancla, la escala
  de la hoja (la del compositor) y giro 0, igual que `superficies.matriz_sobre_superficie`. Devuelve
  matriz, RMS en pies, residuo por pieza y escala ajustada contra la escala de la hoja.
- Se acepta si RMS ≤ `RMS_MAX_FT`=25, ninguna pieza > `PIEZA_MAX_FT`=60 y la escala difiere
  ≤ `ESCALA_TOL`=2 % de la del compositor. Si no, queda **dudosa**.
- Más adelante, sin cambiar lo demás: GeoPDF (`/VP /Measure`), coordenadas o marcas de cuadrícula
  escritas en la hoja, y PLSS genérico de la BLM (el texto «SEC/T/R» existe en muchos planos del oeste
  de EE. UU.).

### Datos (sin red al usar la app)

`scripts/datos/indice_phoenix_qs.py` descarga la capa (paginada, `outSR=2868`) y escribe el
`.json.gz` con la fecha y la URL. Se corre a mano cuando la ciudad cambie la capa. El archivo va al
repo y al instalador (`PDF-a-CAD.spec` → datos, y `autoprueba` lo comprueba).

### En la ventana (`ui/ventana/ventana_georef_auto.py`, `GeorefAutoMixin`)

- Se llama al final de `_apply_composite` y al abrir una hoja suelta, solo si `self.georef` NO está
  activo (lo hecho a mano manda siempre). Una pieza sin `ficha.celda` no lleva a ninguna fuente: DU06 y
  los CAD no pasan por aquí y nada cambia.
- Aceptada: `Georef(matrix, epsg=2868, kind="similarity", rms, points, cs_code="AZHP-CIF")` con un
  `_push` (Ctrl+Z la quita). `points` lleva cada ancla (`px`, `utm` = mundo, `fuente`, `celda`) para que
  «Georreferenciar…» las muestre como pares de siempre y se puedan ajustar a mano. Aviso breve:
  «Georreferenciada sola por cuarto de sección (16-10…16-27) · error 4 ft» con «Deshacer».
- Dudosa: no se aplica. Aviso con la cifra («las hojas no coinciden con sus cuadros: 80 ft; revisa la
  composición») y botones «Aplicar igual» / «Georreferenciar a mano…».
- Panel «Hoja y PDF», tarjeta de georreferencia: «Automática · cuarto de sección · error N ft».
- Agregar utilidad desde otro PDF: la georreferencia es de la hoja del editor, y las piezas agregadas
  se calcan sobre ella, así que no cambia nada. Si el editor no tenía georreferencia y las piezas nuevas
  traen celda, se intenta al combinar.

## Pruebas (`tests/test_georef_auto.py`)

- PURAS: tabla → centroide y PLSS de 16-10. Confirmación: con «NE 1/4 SEC.26, T.2N, R.1E» sí; con solo
  «17-10» y sin texto de Phoenix, no. Ajuste sintético de 1 y de 3 anclas.
- Indian School: Sewer North y Water North compuestos → la georreferencia se aplica; RMS ≤ 10 ft y cada
  pieza ≤ 15 ft de su cuadro. Además, 4 esquinas de cuadro contra la intersección de ejes de calle,
  tomada de la capa pública de calles de Phoenix y guardada como dato fijo en la prueba: ≤ 25 ft (el
  error se imprime).
- Water South compuesto → dudosa, no se aplica; muestra el error.
- DU06 (y una hoja CAD cualquiera) → `georef` sigue inactivo y el DXF queda idéntico.
- Una georreferencia a mano no se pisa.
- Las pruebas que necesitan los PDF de Indian School se saltan si no están.

## Decisiones tomadas por mí (el usuario dijo «lo que tú consideres mejor»)

- Enfoque 1, los umbrales (25 ft, 60 ft, 2 %), la confirmación por PLSS o por el nombre de la ciudad y
  no aplicar nada dudoso en silencio.
- EPSG 2868 (HARN), tal como lo publica la ciudad, no 2223. La diferencia es de menos de 1 m y se
  conserva el dato de origen.
- La georreferencia automática solo actúa si no hay ninguna. Para cambiar una existente: «Quitar» y
  volver a componer, o el diálogo de siempre.

## Lo que queda al constructor

Nombres internos, dónde exactamente se muestra la tarjeta del panel y el texto final de los avisos
(con `t()` y su traducción).
