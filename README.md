# PDF → CAD — Digitalización de planos de utilidades

Pipeline modular que convierte un PDF de plano (agua, alcantarillado, gas, vías,
metro) en un **DXF por capas** listo para AutoCAD / Civil 3D.

Detecta automáticamente si el PDF es **vectorizado** (extrae geometría exacta con
PyMuPDF) o **rasterizado/escaneo** (vectoriza con OpenCV + OCR).

## Georreferenciación (coordenadas de mundo reales)

La app de marcado (`app/`) permite **georreferenciar** el plano por puntos de
control (menú **Herramientas → Georreferenciar…**): a la izquierda el plano ya
cargado (PDF + utilidades dibujadas, con imán a la línea más cercana), a la
derecha las calles reales de Los Ángeles (NavigateLA) tras buscar una
dirección/intersección, con imán a la intersección más cercana. Con 3+ pares se
ajusta una transformación afín y el botón **«💾 Guardar georreferenciación»**
la deja guardada en el proyecto (`.digproj`) y activa para la próxima
exportación — tanto el **DXF** como el **JSON de red** salen en coordenadas
reales, **State Plane CA Zona V (EPSG:2229, pies)**.

> ⚠️ **Advertencia:** calzar contra las centerlines da coordenadas de
> **trazado/anteproyecto**, **NO grado construcción**. El dato topográfico real
> sigue viniendo del **levantamiento / Excel**.

Requiere las dependencias opcionales `pyproj` y `scikit-image` (ver
`requirements.txt`); `contextily` es opcional (imagen base satelital/calles
detrás de las centerlines — sin ella el mapa sigue funcionando solo con las
líneas). Si no están instaladas, la app abre igual y usa la escala del
titleblock como hasta ahora.

## Instalación

```bash
pip install -r requirements.txt
```

Para procesar escaneos también necesitas el binario **Tesseract-OCR** instalado
en el sistema (para el OCR de labels). La ruta vectorizada no lo requiere.

## Uso

```bash
# Auto-detecta vector vs raster
python digitize.py entrada.pdf salida.dxf

# Forzar una ruta concreta
python digitize.py entrada.pdf salida.dxf --force-raster
python digitize.py entrada.pdf salida.dxf --force-vector
```

Programático:

```python
from digitize import main
warnings = main("plan.pdf", "plan.dxf")   # devuelve lista de warnings de QA
```

## Arquitectura (modular)

| Archivo | Responsabilidad |
|---|---|
| `config.py` | **Todos los parámetros ajustables**: mapeo de capas, escala, texto, color HSV, HoughLinesP, tolerancias de unión. Edita aquí para recalibrar por tipo de plano. |
| `detect.py` | Clasifica cada página: `vector` o `raster`. |
| `vector_pipeline.py` | Extracción de PDFs vectorizados (geometría por capa OCG + texto). |
| `raster_pipeline.py` | Vectorización de escaneos (color → Hough → polilíneas + OCR). |
| `digitize.py` | Router + validación QA + CLI. |

## Capas de salida (DXF)

`AGUA` · `ALCANTARILLADO` · `GAS` · `ELECTRICO` · `TELECOM` · `EJE_VIA` ·
`METRO_RW` · `TOPO` · `ESTRUCTURAS` · `PREDIOS` · `LIMITE_MAPA` ·
`ANOTACION` · `TEXTO`

> El mapeo soporta varias familias de plano (MTA/BOE `C-UTIL-*` y LADWP Water
> Service Map `WGS_*`/`WSM_*`/`PROPERTY`/`CENTERLINES`…). Para un plano nuevo con
> otro esquema, añade sus tokens OCG a `LAYER_TOKENS` en `config.py`.
> `PREDIOS` = lotes/parcelas; `LIMITE_MAPA` = borde de hoja de mapa de servicio.

> `ANOTACION` contiene las **líneas guía (leaders)** que conectan cada texto de
> callout con la utilidad a la que se refiere (capas `C-UTIL-CALLOUT`,
> `C-ANNO-IDEN`). Las cotas/dimensiones (`C-ANNO-DIMS`) se descartan por defecto;
> cámbialas a `"ANOTACION"` en `config.py` si las quieres.

> Se conservan `ELECTRICO` y `TELECOM` porque el plano sí los contiene; si solo
> quieres las 6 capas básicas, reasigna esos tokens en `config.py`.

Colores alineados a la convención: azul=agua, café=alcantarillado, amarillo=gas,
negro=vía.

## Cómo ajustar la detección

### PDF vectorizado
- **Mapeo de capas** → `LAYER_TOKENS` en `config.py`. Cada token se compara como
  subcadena contra el nombre OCG del PDF; gana la primera coincidencia. Pon `None`
  para descartar (membrete, cotas, callouts).
- **Texto del membrete (cuadro de rótulo)** → se descarta automáticamente: se
  calcula la caja del dibujo desde la geometría real y se excluye todo el texto
  fuera de ella. Si se cuela o se pierde algo, ajusta `TEXT_PLAN_BBOX_MARGIN_PT`
  (subir = conserva más labels de borde; bajar = recorta más cerca del dibujo).
- **Texto demasiado grande/pequeño** → `TEXT_SCALE_FACTOR`.
- **Líneas discontinuas que deberían ser continuas** → sube `MERGE_MAX_BRIDGE_PT`.
- **Tramas/patrones que salen como maraña de líneas cruzadas** (domo truncado,
  símbolos, hatch) → añade su token OCG a `NO_MERGE_TOKENS`: sus segmentos se
  dibujan tal cual, sin fusionar.
- **Marcas/ticks diagonales sobre las líneas de utilidad** (restos de los
  marcadores de linetype ─W─ ─G─ que no son letra) → se eliminan solas con
  `CLEAN_UTILITY_MARKERS = True`. Método **general** (sirve para cualquier plano,
  sin depender de la orientación): tras fusionar los guiones en corridas largas
  de tubería, los ticks quedan como trazos cortos y aislados y se descartan.
  Ajustes: `MARKER_MAX_LEN_PT` (longitud máx. de un tick) y `MARKER_MAX_SEGMENTS`
  (cuántos segmentos puede tener); `UTILITY_CLEAN_LAYERS` (capas a limpiar).
- **Marcadores de letra (W/G/SS) que aparecen como ruido** → ajusta la ventana
  `SHX_AREA_MIN` / `SHX_AREA_MAX`.

### PDF rasterizado (escaneo)
- **Colores** → `RASTER_COLOR_RANGES` (rangos HSV por utilidad).
- **Sensibilidad / grosor de línea** → `RASTER_HOUGH` (`threshold`,
  `minLineLength`, `maxLineGap`, `thickness`) por capa.
- **DPI de rasterizado** → `RASTER_DPI` (300 por defecto).
- **OCR** → `RASTER_OCR_ENABLED`, `RASTER_OCR_MIN_CONF`.

## Tipos de línea (identificación precisa)

> **Estado actual:** los tipos de línea personalizados con letra están
> **DESACTIVADOS** (`USE_CUSTOM_LINETYPES = False` en `config.py`). Todas las
> utilidades salen como líneas simples `CONTINUOUS`. Para reactivar los
> marcadores ─W─ ─SS─ ─G─ ─E─ ─T─, pon `USE_CUSTOM_LINETYPES = True`.

El PDF dibuja todas las líneas con trazo sólido; el aspecto discontinuo del plano
se logra con segmentos cortos + marcadores de letra. El pipeline puede reconstruir
la **convención CAD por capa** (linetype ByLayer) para que cada línea se identifique
por su trazo además del color:

| Capa | Linetype | Aspecto |
|---|---|---|
| AGUA | `UTIL_W` | ──W──W── |
| ALCANTARILLADO | `UTIL_SS` | ──SS──SS── |
| GAS | `UTIL_G` | ──G──G── |
| ELECTRICO | `UTIL_E` | ──E──E── |
| TELECOM | `UTIL_T` | ──T──T── |
| METRO_RW | `CENTER2` | punto-guión |
| EJE_VIA / TOPO / ESTRUCTURAS | `CONTINUOUS` | continua |

Ajustes en `config.py`:
- **Asignación capa → linetype** → `LAYER_LINETYPE`.
- **Tamaño de raya/hueco/letra** → `UTIL_LT_DASH`, `UTIL_LT_GAP`, `UTIL_LT_TEXT_H` (en pies).
- **Escala global** → `LINETYPE_SCALE` ($LTSCALE).

> Si en Civil 3D las letras (W, G, SS…) no se ven, haz `REGEN` o ajusta `LTSCALE`.
> Los marcadores de letra usan linetypes complejos con fuente Arial (`LTSTD`).

## Atributos capturados

Los labels se analizan para extraer **diámetro**, **material** (VCP, RCP, PVC,
DIP, HDPE, …) y **estación** (`123+00`). Se guardan como **XDATA** (`appid=PDFCAD`)
sobre la entidad TEXT correspondiente.

## Validación QA

Al final, `digitize.py` reporta entidades por capa y verifica:
capas de utilidad pobladas, conteo total razonable, y que la capa de respaldo no
domine (señal de huecos en `LAYER_TOKENS`).
