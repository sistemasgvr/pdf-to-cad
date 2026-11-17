# Línea base de tiempos — flujo actual «abrir PDF → asistente → editor» (2026-11-16)

Medido con `scripts/rendimiento/flujo_reconocer.py` (Tarea 0 del plan «reconocimiento desde el editor»; es la cifra
contra la que se mide la Tarea 12). Cada etapa corre como proceso aparte, una a la vez, con `OPENBLAS_NUM_THREADS=1`,
en una máquina de 12 hilos con otras aplicaciones abiertas (números orientativos, ±10 %).

```
python scripts/rendimiento/flujo_reconocer.py "QS Water_Indian School_South.pdf" "QS Water_Indian School_North.pdf" \
   --agregar "QS Sewer_Indian School_South.pdf" "QS Sewer_Indian School_North.pdf" --salida agua.json
```

## Phoenix Water South + North (36 mapas) — hasta tener el agua en el editor

| Etapa | Medidor | s |
|---|---|---:|
| Componer (sugerida 13.5 + materializar 3.6) | `componer.py` | 17.5 |
| «Capas de la hoja» (1 102 capas virtuales) | `capas.py` | 57.2 |
| Reconocer AGUA (17 196 líneas, zoom 3.5, en este proceso) | `RT.reconocer_hoja` | 143.5 |
| Importar: vista previa 4.1 + importar 8.9 + editor quieto 10.5 | `importar.py` | 23.4 (47.4 de pared con abrir la hoja ≈11 s y la escala) |
| **Total hasta el editor** | | **≈ 242 s (≈ 266 s de pared)** |

Resultado: 17 196 utilidades, 83 estructuras, 4 211 válvulas.

## «Agregar utilidad» hoy: Sewer South + North (36 mapas) sobre esa hoja

| Etapa | Medidor | s |
|---|---|---:|
| Calcar (`hoja_calcada.calcar_trabajo`; 36 ubicadas, 0 sin pareja) | en proceso | 11.9 |
| Componer los 36 mapas nuevos (14.5 + 6.4) | `componer.py` | 21.4 |
| «Capas de la hoja» | `capas.py` | 71.3 |
| Reconocer ALCANTARILLADO (11 877 líneas) | `RT.reconocer_hoja` | 156.6 (157.3 de pared) |
| Importar sola (5.1 + 11.5 + 5.8) | `importar.py` | 22.4 (46.0 de pared) |
| **Total** | | **≈ 284 s (≈ 308 s de pared)** |

## DU06 hoja índice 3 (suelta, CAD con capas)

| Etapa | s |
|---|---:|
| Capas (221 capas, 133 visibles) | 2.6 |
| Reconocer las 6 utilidades (95 líneas) | 6.4 |
| Importar (abrir 1.25, vista previa 0.07, importar 0.51, quieto 0.00) | 0.6 |

Comandos exactos (cada uno con `OPENBLAS_NUM_THREADS=1`, salida a un archivo; `DU06=".../docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"`):

```
python scripts/rendimiento/capas.py "$DU06" 3
python scripts/rendimiento/reconocer.py "$DU06" 3          # las 6 utilidades, zoom 1
python scripts/rendimiento/importar.py "$DU06" 3           # reconoce una vez (8.3 s) y mide importar
```
`flujo_reconocer.py` acepta `--hoja N` (se aplica a la cadena base y a la agregada; los Phoenix usan 0).

## Pausas de la ventana (latido, `flujo.py`)

* Phoenix Water South suelto (asistente real hasta el editor, 813 utilidades): **0 pausas > 1 s**, barra quieta
  como máximo 0.4 s; pasos Componer 1.3 s → Capas 5.8 s → Vista previa 10.0 s → importar 11.2 s.
* La línea base de pausas existe SOLO para un mapa Water South suelto. La Tarea 12 debe medir las pausas en la
  compuesta de 36 mapas con el mismo método (latido de `flujo.py`) antes y después del cambio.
* **No medido:** la pausa máxima en la compuesta de 36 mapas (`flujo.py` abre UN PDF; el flujo de dos PDF no es
  automatizable con él) ni con DU06 completo (`flujo.py` se quedó colgado dentro del diálogo modal del asistente y
  hubo que matarlo; el `--tope` no corta un bucle modal anidado). En el import de 17 196 utilidades el editor
  tarda ~10.5 s en quedar quieto (avisos/marcas), tiempo en que atiende eventos por tandas.

## Qué no se midió y por qué

* La etapa «combinar la hoja calcada + importar» de Agregar (`_importar_agregando`, `_poner_hoja_combinada`) solo
  existe dentro de la ventana con el editor ya cargado; aquí se midió la importación de sewer sola.
* Reconocimiento hecho en este proceso (como los medidores existentes), no en el trabajador de la app.
* La utilidad se fija con `--utilidad`; los Phoenix traen leyenda, así que no se usa `--sugerir` (con la hoja
  compuesta de agua `estilos_sugeridos` no deduce utilidad: «sin_utilidad», 86 s perdidos).

---

# Después (Tarea 12) — DU06 con el flujo nuevo «reconocimiento desde el editor» (2026-11-16)

Medido con OTRAS pruebas corriendo en la máquina (números orientativos, más altos que con la máquina libre).
`DU06=".../docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"`, zoom 3.5, las 6 utilidades, roles automáticos.

## Mismo resultado (por partes = de una vez)

`scripts/rendimiento/partes.py` — modo `viejo` (`reconocer_hoja` de una vez) y `nuevo` (interpretar + ▶ por utilidad →
válvulas → diámetros → rótulos sobre la lectura retenida), cada uno en su proceso; `--diff` compara líneas (vértices,
tipos, codos, capa, abandonada), bóvedas, avisos, válvulas completas, grosor completo y rótulos.

| Hoja (índice) | Líneas | Válvulas | Rótulos | Diferencias | De una vez (s) | Interpretar (s) | Interpretar + todos los ▶ (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 77 | 72 | 47 | **0** | 3.00 | 1.86 | 4.49 |
| 3 | 97 | 66 | 67 | **0** | 5.27 | 2.32 | 5.01 |
| 4 | 55 | 24 | 56 | **0** | 3.61 | 1.54 | 4.41 |
| 5 | 34 | 30 | 37 | **0** | 1.93 | 1.24 | 2.08 |
| 9 | 62 | 18 | 53 | **0** | 2.65 | 1.85 | 3.93 |
| 11 | 52 | 30 | 42 | **0** | 2.52 | 1.29 | 2.55 |
| 12 | 66 | 42 | 49 | **0** | 2.83 | 1.67 | 3.47 |
| Compuesta sugerida (14 hojas, `componer.py --pdf-salida`) | 671 | 534 | 608 | **0** | 84.6 | 18.2 | 85.3 |

Compuesta, ▶ por parte: Eléctrico 9.7 · Drenaje 5.1 · Agua 3.3 · Alcantarillado 3.7 · Gas 3.4 · Telecom 41.0 ·
Válvulas 0.8 · Diámetros 0.0 · Rótulos 0.0 s. Lo que el usuario espera antes de trabajar baja de ~85 s (asistente
entero) a 18 s de interpretación EN SEGUNDO PLANO con el editor ya usable; cada utilidad tarda lo suyo.

## En la ventana (`scripts/rendimiento/flujo_editor.py`, trabajadores reales) — DU06 hoja 3

| Paso | s |
|---|---:|
| Abrir → editor usable (hoja a la vista) | 1.37 |
| Interpretación en segundo plano | 3.10 |
| ▶ Todo (6 utilidades + válvulas + diámetros + rótulos; 96 utilidades, 11 válvulas, 67 rótulos) | 10.5 |

Pausas de la ventana > 0.2 s: 8; máxima **1.02 s** al abrir (`fondo_pdf.gris` en `ventana_hojas._fondo_de`: la
imagen en grises de la hoja suelta, el mismo paso del flujo de antes); durante la interpretación y los ▶ ninguna
pasa de 0.3 s.

## El editor = el de antes (`scripts/rendimiento/editor_igual.py`)

Hojas 3 y 4: tras «▶ Todo», utilidades, válvulas y rótulos IDÉNTICOS al flujo de antes (`reconocer_hoja` →
`_import_recognized_pipes`); estructuras iguales por lugar y contenido. Solo cambian el ORDEN de la lista de
estructuras y sus códigos BZ-n/CV-n (se numeran a medida que entra cada utilidad).
