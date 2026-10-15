# Reconocimiento de PDF aplanado

Las hojas vectoriales sin capas originales entran al mismo flujo de reconocimiento
mediante capas virtuales por estilo (`app/hoja/pdf_styles.py`). Se agrupan por color,
grosor en puntos PDF, patrón de guiones, relleno y opacidad. Los nombres internos
son estables entre aperturas y hojas que comparten el mismo estilo.

1. Abrir o componer la hoja. Si el mapa trae recuadros de detalle (por ejemplo
   S-16-10-1 en Phoenix), tomar en **Componer hoja** solo el área del mapa principal:
   las líneas de los recuadros también se reconocerían.
2. En **Capas de la hoja**, los estilos aparecen inicialmente en **Otras**. Clic en un
   estilo resalta sus trazos.
3. Con el estilo seleccionado, elegir **Utilidad** y **Rol** debajo de la lista. La capa
   se mueve al grupo elegido y el reconocimiento recibe su asignación. **Otras** la
   excluye del reconocimiento; **Automática** restablece la clasificación original.
   Solo se reconocen las utilidades con un estilo asignado: hasta asignar uno,
   **Continuar** queda apagado (**Cancelar** deja la hoja cargada para dibujar a mano).
   También se puede ajustar en la vista previa con **Ajustar capas…**.
4. Corregir la **Escala** (botón del pie) antes de continuar: **Calibrar con una
   distancia conocida…** (dos clics + distancia real en pies) o **Escribir la escala…**.
   Los radios y largos se calculan al reconocer; corregirla después en el editor ya no
   los arregla. La escala escrita en **Componer hoja** para una sola hoja también se usa.
5. Revisar la vista previa e importar al editor; exportar.

Las casillas de estilos excluyen geometría del reconocimiento. No apagan tinta en el
render del PDF: son capas virtuales, no grupos OCG. Los PDF originales no se modifican.
Las hojas con geometría en OCG conservan el flujo existente (foto antes/después de 15
hojas × 6 utilidades de DU06/DU08/DU10/LABOE: 0 diferencias). Los trazos sin OCG de una
hoja que también tiene trazos OCG conservan el comportamiento anterior; aún no se agrupan
como estilos.

## Qué hace el reconocimiento con una capa por estilo

- **Trazo continuo** (mapa SIG: cada tubería un trazo, las curvas en cuerdas cortas;
  `recognition_ink_lines.continuous_layer`): la tinta es el eje tal cual
  (`ink_reconstruct`), simplificada a la MITAD del grosor del trazo (`simplify_tol`,
  entre 0.15 y 0.5 pt; el grosor sale del nombre de la capa por estilo) para quitar el
  zigzag del trazo sin que el eje salga de la línea dibujada (con 0.5 fijo la tubería de
  agua de 0.38 pt cortaba las curvas por cuerdas a 0.45 pt de su tinta). El núcleo de
  guiones partía las curvas en rectas y ponía esquinas hasta 5 pt fuera de la tinta.
- **Tipo de línea a guiones** (plano CAD aplanado, por ejemplo DU08 h.4–19): sigue por el
  núcleo de siempre (`recognition_geom.reconstruct`).
- **Buzones en los cortes** (`recognition_style_nodes`, solo redes por gravedad:
  alcantarillado y drenaje): donde terminan dos o más tuberías del mapa hay un buzón (en
  Phoenix 17-10 los 104 cortes caen todos en el círculo de un buzón, que es un glifo de la
  fuente Type3, no un vector). El vértice pasa a «vault»; así ese quiebre no se convierte
  en curva al importar.
- El estilo no dice si una red está abandonada: en estas capas no se aplica la regla «//».
- El dato extendido de la línea guarda el estilo legible («Estilo Negro 0.73 pt ·
  continuo»), no el nombre interno.

## Lo que dice la leyenda y el mapa (2026-10-13/14)

Solo en hojas sin capas cuyo texto viene en una fuente Type3 sin mapa de caracteres
(`leyenda_mapa.aplica`):

- **Texto** (`hoja/texto_pdf.py`): cada glifo se dibuja y se compara con Arial (coseno
  ≥ 0.9); en Phoenix las letras son exactamente las de Arial. Los glifos sin letra son
  símbolos (válvulas, hidrantes, buzones). La fuente fina de trazos del alcantarillado
  (nombres de calles y subdivisiones, anchos de vía) no se lee: es mapa base, no red.
- **Leyenda** (`leyenda_mapa_lectura` + `leyenda_mapa`): filas = muestra + descripción,
  por sección; utilidad del plano, escala del rótulo, notas («taps are .75" in diameter»,
  «main material is ACP»). `asignaciones` deja la red como líneas y el buzón como
  estructura en «Capas de la hoja»; lo que la leyenda usa también para lotes o
  anotaciones queda para el usuario.
- **Acometidas** (`acometidas_mapa`, `recognition_taps`): mismo estilo que los linderos,
  pero NACEN sobre la red y el SIG las dibuja en un bloque seguido del orden de dibujo.
  Van a la capa «Acometidas · …»; en agua y gas se reconocen unidas a la tubería con una
  T y el diámetro de la nota (o el escrito, «278' 2"»); en gravedad quedan sin asignar.
- **Buzones** (`recognition_map_vaults`): el buzón-símbolo con la punta o un vértice de su
  línea dentro, o atravesado por ella, queda en la línea (antes: «sin línea» e importado
  dos veces).
- **Diámetros** (`recognition_diametros`): «6"», «8" DIP», «12"» paralelos y pegados a una
  tubería → su diámetro (mayoría ≥ 60 %; con rótulos distintos queda el de siempre y se
  avisa).

## Corpus Phoenix

`scripts/verify_flattened_pdfs.py <carpeta>` inspecciona los seis PDF externos de
Indian School (108 hojas) y prueba el reconocimiento de la primera hoja de
cada archivo Sewer/Water con estilos elegidos para esa prueba. Los grosores
del script no son reglas del producto ni una clasificación automática.
El reporte queda en `output/flattened-pdf-validation.json`.
`tests/test_mapas_sin_capas.py` recorre el flujo completo con la hoja 17-10 de
alcantarillado (ventana real → DXF) y casos sintéticos.

Resultados (hoja 1, escala calibrada a 1"=160'): alcantarillado Norte 69 líneas y 102
buzones; agua Norte 151 líneas (red a presión: sin buzones); alcantarillado Sur 48 líneas
y 113 buzones. Tiempo de reconocimiento 1–4 s por hoja.

Pendiente: leer las letras del tipo de línea en las capas por
estilo de los planos CAD aplanados (un estilo mezcla varias utilidades: «—W—», «—G—»…),
vectorizar las imágenes de drenaje por color, asignar a cada buzón su fila de las tablas
«Quadrant … Manholes» (Rim/Inv, ya legibles), importar válvulas e hidrantes como accesorios,
partir una ruta donde cambia el diámetro escrito (reducción) y permitir elegir el sistema de coordenadas del
proyecto (Phoenix: Arizona Central, no EPSG:2229). Este cambio no habilita una
exportación georreferenciada específica para Phoenix.
