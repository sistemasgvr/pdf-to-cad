# Bloqueo al activar y desactivar capas

Corrección del 2 de noviembre de 2026 para el flujo de visibilidad del editor.
La captura muestra una hoja compuesta de 72 piezas y unas 29 000 utilidades; el
proyecto exacto de esa captura no está entre los casos reproducidos aquí.

## Causas encontradas

- `_aplicar_capas` llamaba al redibujo general. Aunque se reutilizaban líneas y
  marcas, se recorrían los overlays y se creaban otra vez buzones, curvas y textos.
- Cambiar planos de fondo también llamaba al redibujo general para actualizar
  únicamente el minimapa y las marcas de las hojas.
- Una combinación de fondos sin imagen guardada entraba en un flujo de preparación
  con espera y posible rasterización síncrona de la hoja entera. Solo se guardaba
  una imagen anterior.

## Comportamiento corregido

Las utilidades conservan sus objetos gráficos. Sus máscaras cambian la visibilidad;
buzones y curvas conservan geometría, contornos y etiquetas y se muestran u ocultan
según sus utilidades asociadas. Se mantiene la excepción de estructuras seleccionadas.
La asociación se renueva al reconstruir el dibujo por cambios del modelo.

Las etiquetas de edición de tramos se actualizan por separado, manteniendo el
mismo algoritmo de colocación. Su distribución puede depender de otras etiquetas
visibles; actualizarla no requiere reconstruir la red ni los buzones.

Los fondos ya preparados se reutilizan. Una combinación nueva se materializa y
rasteriza en un proceso separado. La ventana conserva su imagen anterior y atiende
eventos mientras espera. Hay una preparación activa y una petición de presentación
vigente: los clics rápidos sustituyen el destino pendiente, sin acumular una
rasterización por cada clic.

Al llegar un resultado se comprueba la generación de la hoja, la firma del estado
y el destino vigente. No puede restaurar un plano apagado ni sustituir una hoja
nueva por una imagen antigua. Los archivos RGB/gris descartados se eliminan. Un
error conserva la vista anterior y permite volver a solicitar el fondo.

Se retienen hasta cuatro estados recientes cuando caben en el presupuesto de
caché, adaptado a RAM libre entre 64 y 256 MiB. Una imagen anterior grande puede
superar ese presupuesto: se conserva sola para permitir volver sin rasterizar.
La política no reduce la resolución de las imágenes guardadas.

Cambiar fondos actualiza su imagen, sus teselas y sus ayudas de ubicación. Las
utilidades, cálculos, estructuras, historial, coordenadas y exportación permanecen
en el modelo original. La primera presentación de una combinación no preparada
puede tardar; lo corregido es la espera bloqueante y la reconstrucción innecesaria.

## Validación

39 pruebas de capas, líneas y marcas pasaron. Incluyen:

- identidad de objetos conservada al apagar/encender, sin entrar al redibujo general;
- visibilidad de líneas y estructuras, selección, tooltips y dibujo de marcas;
- etiquetas de edición por tramo y sus reglas de colocación;
- mismos píxeles del fondo y datos geométricos/historial sin cambios;
- volver a estados guardados sin materializar ni rasterizar de nuevo;
- clics rápidos, apagar todos y cambiar de hoja mientras llega un resultado;
- fallos del trabajador sin ejecutar una rasterización síncrona como respaldo;
- un proceso trabajador real, con un temporizador Qt que sigue atendiendo eventos.

Se añadieron los casos de regresión en `tests/test_capas_incrementales.py` y se
ejecutaron junto con `test_planos_fondo.py`, `test_capa_marcas.py` y
`test_capa_lineas.py`. El ejecutable abierto en la captura no se sustituyó.
