# Investigación y primera implementación de aceleración adaptable

Fecha: 2 de noviembre de 2026. Equipo del usuario: Windows, RTX 3050 Laptop 6 GB.

## Conclusión

Sí se puede aprovechar la GPU, pero el proceso debe repartir el trabajo según su
naturaleza. La mejora más grande encontrada aquí consiste en evitar recortar
geometría que está claramente fuera de la vista. La GPU puede apoyar el filtro
numérico; el recorte geométrico exacto y la interpretación del PDF siguen en CPU.
Esta implementación es una primera etapa, no una conversión completa del programa
a GPU ni un motor que use todos los núcleos para todas las operaciones.

## Qué estaba pasando en la captura

El texto «Recortando lo que se ve de cada capa… (72000 de 511438)» corresponde a
`hoja.leyenda_trazos.trazos_visibles`. El total incluye elementos de la lectura
extendida del PDF: trazos, recortes y grupos. No representa 511 438 páginas ni
necesariamente ese número de líneas simples. El trabajo puede variar mucho entre
elementos, así que 14 % de elementos no permite predecir 14 % del tiempo.

El código mantiene una pila de recortes por nivel. Para los casos que necesitan
cálculo exacto, `recognition_geom.clip_path` descompone curvas, busca cruces de
segmentos con lados de polígonos, decide qué fragmentos quedan dentro y conserva
los puntos de corte. Buena parte de esas operaciones son bucles de Python.

El coste depende de la cantidad de segmentos, lados de polígonos y clips activos,
no solo del tamaño del archivo. Una curva puede generar varios segmentos.
Componer hojas también puede conservar vectores de referencias que después hay
que excluir porque quedaron fuera de la vista.

La captura muestra CPU global al 19 %, RAM al 82 %, disco al 5 % y GPU 3D al 26 %.
Eso no identifica el consumo de un proceso ni demuestra paginación, saturación
de un núcleo o cómputo CUDA. El sistema informa 12 procesadores lógicos: un hilo
saturado puede representar aproximadamente 8,3 % del total. Para atribuir consumo
hay que medir el proceso trabajador y observar los núcleos por separado.

Microsoft explica que el porcentaje global de GPU corresponde al motor más
ocupado; no es una media de toda la tarjeta. Debe revisarse el motor y el proceso,
además de los tiempos del programa. [Documentación de Microsoft](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/).

## Hardware comprobado

`nvidia-smi` reconoció NVIDIA GeForce RTX 3050 6GB Laptop GPU, 6144 MiB de VRAM,
capacidad de cómputo 8.6 y controlador 591.80. El entorno informó 12 procesadores
lógicos y unos 31,2 GiB de RAM física utilizable. La RAM libre cambia durante el uso.

La indicación «CUDA 13.1» de `nvidia-smi` describe la compatibilidad del controlador;
no prueba que un programa tenga instaladas las bibliotecas necesarias ni las use.
[Referencia NVIDIA](https://docs.nvidia.com/deploy/nvidia-smi/index.html).

Se preparó un entorno aislado en `.venv/hardware`, con CuPy 14.2.0 y componentes
CUDA dentro del proyecto, y se ejecutó realmente el kernel en la RTX. No se
modificó el controlador ni la instalación global de Python.

## Cambios implementados

1. **Filtro conservador por cajas.** Rechaza geometría claramente fuera de los
   recortes antes de convertirla y calcular intersecciones. Mantiene el margen de
   visibilidad existente de 0,25 pt. Estar dentro de la caja de un polígono inclinado
   no se acepta como prueba de estar dentro del polígono.
2. **Procesamiento por lotes.** NumPy ejecuta los predicados en código nativo de
   CPU. OpenCL y el backend opcional CUDA reúnen los predicados en un solo
   lanzamiento. Los casos ambiguos conservan el algoritmo exacto anterior.
3. **Selección automática.** Para lotes de al menos 32 768 elementos se compara
   CPU con las GPU detectadas y se exige una ventaja mínima del 20 %, incluidas las copias de
   ida y vuelta. La calibración verifica igualdad de resultados.
4. **Preparación en segundo plano.** La CPU sigue procesando mientras otro hilo
   prepara CUDA. No se espera a crear el contexto o compilar el kernel en la ruta
   normal del PDF. Este hilo recibe únicamente números, nunca objetos MuPDF.
5. **Memoria acotada.** Los lotes llegan hasta 65 536 elementos y se reducen según
   la RAM disponible. Se comprueba memoria GPU libre al cargar CUDA. Los errores
   de instalación, controlador, compilación o memoria activan la ruta CPU.
6. **Resumen de visibilidad.** Cuando el trabajador solo necesita nombres de
   capas visibles, conserva nombres y cajas en lugar de toda la geometría
   recortada. Sigue aplicando las exclusiones de perfiles.

PyOpenCL es opcional (no está en `requirements.txt` ni en el `.exe`): permite usar distintas
marcas cuando el controlador ofrece OpenCL y doble precisión. Se comprobó este filtro en la AMD
integrada (`gfx1103`) y en la RTX 3050 del equipo, con resultados iguales a CPU.
Intel está contemplado por detección de capacidades, pero no se dispuso de una GPU
Intel para verificarla físicamente. Dispositivos sin soporte suficiente usan CPU.
La ruta CuPy/CUDA se mantiene para instalaciones que ya la tengan. El selector
compara las rutas detectadas y utiliza la más rápida que cumpla el margen exigido;
no reparte el mismo lote simultáneamente entre varias GPU. La calibración queda
en el proceso trabajador y se repite al reemplazarlo.

## Mediciones y límites de interpretación

Mediciones locales, sin promesa de rendimiento para otros archivos:

| Caso | Anterior / CPU | Nuevo / CUDA | Qué se midió |
| --- | ---: | ---: | --- |
| 100 000 trazos sintéticos mayormente fuera del área | 0,823 s | 0,203 s, nueva CPU | Etapa de visibilidad; unos 4,1×; mismo resultado |
| 65 535 cajas, GPU preparada | CPU 0,985 ms | CUDA 0,612 ms | Solo filtro numérico, incluidas transferencias; alrededor de 1,6× |
| DU06 hoja 3, 18 287 elementos | 0,648 s | 0,614 s, nueva CPU | Mediana de cuatro pasadas de recorte sobre geometría ya leída |
| DU06 hoja 5, 19 215 elementos | 0,637 s | 0,603 s, nueva CPU | Misma metodología; mejora de aproximadamente 5 % |

En las hojas DU06 comparadas se verificó la misma geometría, marcas de recorte,
puntos de corte y capas visibles. El resumen de capas tardó aproximadamente
0,594 s y 0,588 s en las hojas 3 y 5, respectivamente. Las cifras son sensibles
a la carga del equipo; diferencias pequeñas deben confirmarse con más muestras.

En otro ensayo controlado de 20 000 trazos que cruzaban el borde, el pico de
asignaciones Python de esta etapa bajó de 20,29 MiB al producir todas las
geometrías a 5,74 MiB al solicitar solo capas visibles. Se midió con `tracemalloc`,
después de preparar los trazos: no representa el uso total de RAM del programa.

El arranque y calibración de CUDA tardaron alrededor de 0,82 s en una prueba
diagnóstica, contando carga de bibliotecas. Esa espera se midió explícitamente
en el diagnóstico; el procesamiento normal continúa por CPU mientras se prepara.
Una operación breve puede terminar antes de que se use CUDA. Por eso un kernel
rápido no demuestra una importación completa más rápida.

El PDF `QS Water_Indian School_South.pdf` de la captura no apareció entre los
archivos del proyecto examinados. No se ha medido ese caso exacto ni el tiempo
total de su importación. Las mediciones de DU06 excluyen la lectura inicial del
PDF y no equivalen a la duración completa del asistente.

## Qué conviene optimizar después

- **Recorte exacto en código nativo.** Los cruces y distancias de los casos
  ambiguos siguen en Python. Una ruta compilada o por lotes puede aportar más
  que mover únicamente el filtro de cajas. Debe conservar tolerancias, perfiles,
  puntos de corte y precisión de curvas; cambiar todo a `float32` exige validación.
- **Lectura más compacta.** Evaluar `get_cdrawings(extended=True)`: devuelve tuplas
  y evita objetos Point/Rect/Quad. No es un reemplazo directo, porque el código
  actual usa atributos de esos objetos. La documentación lo propone como opción
  más rápida. [API PyMuPDF](https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_cdrawings).
- **Varios núcleos con tareas independientes.** PyMuPDF indica utilizar procesos
  separados en vez de varios hilos sobre sus documentos. En este proyecto el
  trabajador actual es `daemon=True`: no puede crear un pool de procesos hijos
  directamente. Hay que planificarlo desde el proceso coordinador, abrir cada
  documento por separado y limitar concurrencia por RAM. No repartir arbitrariamente
  una lista ignorando la pila de recortes. [PyMuPDF y multiprocesamiento](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html).
- **Geometría nativa paralela.** Shapely ofrece operaciones sobre arrays y libera
  el GIL en sus operaciones GEOS. Es una alternativa CPU para evaluar con datos
  reales, no una garantía de que sustituya exactamente el recorte actual.
  [Documentación Shapely](https://shapely.readthedocs.io/en/stable/).
- **Escaneos y OCR.** Son una ruta distinta. El paquete `opencv-python` estándar
  se distribuye para CPU; instalarlo no activa CUDA. Un backend de imagen/OCR en
  GPU requiere operaciones y dependencias específicas, además de comparar la
  calidad de reconocimiento. [OpenCV on Wheels](https://pypi.org/project/opencv-python/).

NVIDIA recomienda agrupar transferencias y conservar datos en GPU cuando resulte
rentable. En esta arquitectura la GPU recibe números compactos; el parseo del PDF
y los objetos Python permanecen en CPU. [Buenas prácticas CUDA](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html).
CuPy advierte sobre los costes iniciales de contexto y compilación y sobre la
necesidad de sincronizar las mediciones. [Rendimiento CuPy](https://docs.cupy.dev/en/stable/user_guide/performance.html).

## Uso, diagnóstico y distribución

La instalación normal usa solo CPU. Para probar la ruta GPU portable:

```powershell
python -m pip install -r requirements.txt
python -m pip install "pyopencl>=2026.1,<2027"
python scripts/diagnostico_hardware.py --modo auto
python scripts/diagnostico_hardware.py --pdf "plano.pdf" --hoja 1 --modo auto
```

Por defecto, `PDFCAD_ACELERACION=cpu`: en 65 535 cajas la GPU ahorra ~0,4 ms de los ~200 ms de
la etapa, y no compensa la dependencia, el hilo de medición ni cargar controladores en el trabajador
(la mejora de ~4× viene de NumPy por lotes). Para usarla o comparar se puede fijar `auto`, `opencl`
o `cuda`; los modos GPU también vuelven a CPU ante errores. Los lotes pequeños
permanecen en CPU. El diagnóstico devuelve JSON y registra los tiempos de calibración.
En este equipo también puede ejecutarse con `.venv/hardware/Scripts/python.exe`.

Se eliminó `requirements-cuda.txt`: CUDA no es un requisito común de NVIDIA,
AMD e Intel. PyOpenCL se instala aparte y el controlador OpenCL corresponde al
fabricante del dispositivo; si falta o no ofrece FP64, se conserva CPU sin
reducir la precisión. [PyOpenCL](https://documen.tician.de/pyopencl/).
CuPy puede instalarse opcionalmente, escogiendo una variante compatible con el
controlador NVIDIA. [Instalación oficial CuPy](https://docs.cupy.dev/en/stable/install.html).

Los cambios se hicieron en el código fuente. El ejecutable/instalador abierto en
la captura no se recompiló ni se sustituyó. Para distribuir CUDA hay que incluir
y verificar sus bibliotecas y cabeceras en el empaquetado; añadir una dependencia
al entorno de desarrollo no la incorpora por sí sola al `.exe` existente.
