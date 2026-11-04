# Reconocimiento con vista progresiva

El reconocimiento vectorial del editor muestra el progreso en una tarjeta en la
esquina inferior derecha del lienzo. No utiliza el velo central del resto de
operaciones. La tarjeta se adapta al ancho del lienzo y evita la barra flotante
de navegación. Mantiene el detalle de la etapa, la barra y Cancelar.

Mientras trabaja se permite acercar, alejar y desplazar el plano. Las acciones
que editan el proyecto quedan pausadas y recuperan su estado previo al terminar,
cancelar o fallar. Escape desde el lienzo permite cancelar. La aplicación que ya
está abierta no recibe estos cambios hasta ejecutar el código actualizado.

## Entrega de líneas

`recognition_geom.reconstruct` e `ink_reconstruct` notifican las polilíneas
provisionales conforme las producen. `FlujoTrazos` copia sus coordenadas y las
envía por el canal de progreso existente, tanto en proceso como en hilo. Cada
mensaje contiene como máximo 64 líneas y 4096 puntos; las líneas largas se
dividen compartiendo el extremo para conservar todos sus segmentos.

El lienzo consume esa cola mediante un temporizador, con un presupuesto objetivo
de 4 ms y un máximo de 4096 segmentos por turno. Los objetos gráficos agrupan
hasta 2048 segmentos. No hay una pausa artificial por línea ni se espera a vaciar
la animación después de finalizar el cálculo.

Al completar una utilidad se sustituye únicamente su vista provisional por las
líneas ajustadas de esa utilidad. Al terminar todo el reconocimiento se retiran
los trazos temporales y se abre la vista previa original. Un identificador de
sesión descarta mensajes tardíos de trabajos anteriores.

## Precisión y alcance

Los trazos temporales no se incorporan al modelo, historial ni exportación.
Continúan ejecutándose los mismos cálculos de cobertura, uniones, extremos,
estructuras, perfiles y diámetros. Las pruebas comparan todos los campos del
resultado con y sin entrega progresiva y exigen igualdad exacta.

Las fases previas (lectura del PDF, clasificación y preparación de la geometría)
pueden tardar antes de producir la primera línea; durante ellas se muestra su
etapa. Mostrar avances mejora la respuesta visual, pero no elimina ese trabajo
ni garantiza una reducción del tiempo total. Este cambio corresponde al
reconocimiento vectorial del editor mostrado en la captura, no a cada diálogo
de importación o reconocimiento organizado del programa.

## Verificación

`tests/test_reconocimiento_progresivo.py` verifica ubicación sin velo, navegación,
cancelación, restauración de controles, entrega en el hilo de interfaz, límites
de dibujo y mensajes, continuidad de líneas largas, sustitución por utilidad y
descarte de sesiones anteriores. Incluye reconocimiento real de un PDF sintético
con igualdad completa de resultados y entrega por un proceso separado mientras
el bucle de eventos de Qt sigue atendiendo un temporizador.
