# Válvulas como capa del plano

Fecha: 2026-11-05. Pedido del usuario: reconocer las válvulas del PDF vectorial como se reconocen utilidades y
diámetros, y que sean una capa más. Alcance: hasta el DXF, en PDF con capas, sin capas con leyenda y sin capas ni leyenda.
Referencias: `Design Standards and Installation Requirements 2025` (LADWP, PC9431-1 pág. 161) y DU06.

## Hechos medidos

- DU06 h.3–16: 91 válvulas en `V-WATR/NGAS/UTIL/IRRG-VALV`, casi todas un moño de 3×4 pt, siempre en la misma
  orientación (bloque de topografía sin girar). 48 de 70 de agua y 8 de 14 de gas a ≤1.5 pt de su línea.
- El símbolo de DU06 no es el de LADWP (punto negro): en DU06 la forma no da el tipo.
- Phoenix: la leyenda nombra tipo y estado («Standard Vlv - Open», «Blow-Off», «Sgl Check», «PRV»).
- DU08 h.4–19 (aplanado): el mismo moño, sin capa. La forma sola también toma árboles: exige una línea cerca.
- Southwest Gas: símbolos de fuentes ESRI sin significado escrito: nada automático.

## Diseño

- `reconocimiento/recognition_valvulas.py` (PURO): lee una vez por hoja al final de `reconocer_hoja`. Fuentes: `capa`,
  `leyenda`, `forma` (solo hoja sin capas ni leyenda, «por confirmar», a ≤1.5 pt de una línea reconocida) y `manual`
  (rol «Válvulas» en «Capas de la hoja»). `RecognitionResult.valvulas` = la misma lista en cada utilidad.
- `hoja/simbolos_fuente.py`: en una hoja sin capas ni leyenda, los glifos de fuentes de símbolos son capas virtuales
  asignables.
- `nucleo/valvulas.py` (PURO): datos, juntar sin repetir, relación con la tubería (de su utilidad a ≤5 pt; sin utilidad
  conocida, solo encima, ≤1.5 pt). Tubería, giro y diámetro se calculan
  al pedirlos: no se guarda un índice que borrar utilidades dejaría viejo. No parte tuberías ni agrega vértices.
- `Main.valvulas`: lista aparte de las estructuras; .digproj, deshacer, respaldo del asistente.
- Interfaz: interruptor «Válvulas» en «Reconocer», vista previa, fila en «Capas ▾», `ui/comun/capa_valvulas.py`, globo,
  clic derecho (confirmar/borrar), pestaña en la Tabla de datos.
- DXF: punto `PDFCAD_VALVULA` en la capa `PDFCAD_VALVULAS` con XDATA `TIPO, UTILIDAD, ESTADO, DIAMETER, ROT_DEG, ORIGEN,
  CERTEZA, PIPE_IDX`. El plugin lo ignora.

## Fuera de alcance

Reglas LADWP (espaciado 600–1,200 ft), piezas en Civil 3D, hidrantes y medidores.

## Criterios

DU06: válvulas revisadas hoja por hoja y líneas idénticas. Water South h.4: símbolos según su leyenda. DU08: aciertos y
falsos positivos medidos. Southwest: cero automáticas y asignación a mano. DXF real exportado desde la ventana.
