# Lista de humo (antes de cada entrega, ~40 min)

Se hace con el **INSTALADOR** recién generado (no desde el código), en una PC con Civil 3D, usando los archivos de
la **carpeta dorada** (`gestion/casos_dorados.toml`). Copiarla para la entrega con
`python scripts/gestion humo <versión>` y marcar `[x]` / anotar lo que falle. Todo lo que falle → issue con captura.

Antes: `python scripts/regresion.py` (debe decir 0 diferencias) y `build_all.bat` sin errores de verificación.

## 1. Instalación (5 min)
- [ ] El instalador termina sin errores; la app abre maximizada con la pantalla de inicio.
- [ ] Civil 3D muestra el panel «Redes de Tuberías» con todos sus botones.
- [ ] Ayuda → Acerca de muestra la versión que se entrega.

## 2. PDF vectorial con capas (10 min) — caso dorado DU06
- [ ] Abrir el PDF → Componer hoja: elegir una hoja, «Usar área sugerida», Siguiente.
- [ ] Capas de la hoja: se ven las utilidades agrupadas; Continuar.
- [ ] Vista previa: líneas sobre la tinta, «Para verificar» se recorre con clic; Importar.
- [ ] En el editor: líneas, buzones/cajas y curvas donde el plano los tiene.
- [ ] Componer dos hojas contiguas: la costura une las líneas sin escalón.

## 3. Mapa sin capas y escaneo (5 min) — casos dorados Phoenix y escaneo
- [ ] Mapa de agua: se lee la leyenda y se reconocen tuberías y acometidas.
- [ ] Escaneo: recortar con 4 esquinas, calibrar escala y dibujar una línea a mano.

## 4. Edición (5 min)
- [ ] Dibujar una utilidad, insertar un buzón, convertir un vértice en curva.
- [ ] Deshacer / rehacer varias veces; editar en bloque dos utilidades.
- [ ] Guardar el proyecto, cerrarlo y volver a abrirlo: todo igual.

## 5. Revisión (5 min)
- [ ] Conflictos numerados C-n; abrir «Resolver» en uno y aplicar una propuesta.
- [ ] Normativas: avisos sobre el plano; aprobar uno.
- [ ] Vista 3D abre, se navega y la ficha muestra los datos de lo elegido.
- [ ] Perfil longitudinal de un tramo con A y B.
- [ ] Tabla de datos → Exportar a Excel abre bien.

## 6. Exportar a Civil 3D (8 min)
- [ ] Exportar DXF «Todo»: termina con aviso breve.
- [ ] En Civil 3D: IMPORTAR_RED crea las redes, buzones, accesorios y sólidos sin errores en la consola.
- [ ] Las tuberías llevan su capa y sus Property Sets; el perfil guardado se crea.
- [ ] Piezas 3D y laminado (si la versión los trae): crear una pieza de cada tipo nuevo.

## 7. IA (3 min, si hay IA configurada)
- [ ] Chat: «¿cuántas utilidades hay?» responde con datos del proyecto.
- [ ] Pestaña Civil 3D: con PDFCAD_IA encendido, «¿qué redes hay?» responde.

## 8. Lo nuevo de esta versión
- [ ] Cada novedad de `gestion/versiones/<versión>.toml` probada una vez como lo haría el cliente.
- [ ] Cada observación del cliente atendida: probada con SU archivo/captura.

Resultado: ☐ Se entrega  ☐ Se entrega con observaciones (listar)  ☐ No se entrega
