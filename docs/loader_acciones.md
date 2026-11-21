# Aro de «cargando» en cada acción

Generado por `scripts/inventario_acciones.py` desde la ventana real (2026-11-21).

**Regla:** todo botón de acción lleva, al pulsarlo, un aro que gira mientras lo que lanzó sigue en marcha (`ui/comun/accion_cargando`). Se ve si el manejador bloquea la ventana más de 0.25 s (el vigía lo pinta) o si lanza trabajo en otro proceso/hilo, la tarjeta «Cargando…» o un trabajo por pasos (`nucleo/actividad`). Las casillas, selectores y conmutadores no la llevan: alternan un ajuste al instante.

- Botones con aro: **123**
- Botones sin aro por ser ajustes o menús: **89**
- Acciones de menú/atajo sin botón (las cubre la tarjeta «Cargando…» y el vigía): **73**

## Main

**Con aro (4):** Avisos de normativa del proyecto. Clic para verlos · Escala — · Opacidad · Ver los conflictos y avisos en Revisión

*Sin aro — conmutador (alterna un modo) (2):* Modo ortogonal · Rastreo polar

*Sin aro — control del sistema (cerrar, flotar…) (5):* qt_dockwidget_closebutton · qt_dockwidget_floatbutton · qt_menubar_ext_button

## PanelAsistente

**Con aro (2):** Cerrar el asistente · Configurar IA…

## PilaActual

**Con aro (5):** Cambiar tipo · Editar texto · Editar/mover · Eliminar · Ver datos extendidos

*Sin aro — casilla (cambia un ajuste al instante) (1):* Ver etiquetas de buzón y en el DXF exportado

## ResponsiveGroupBox

**Con aro (8):** Abrir la carpeta del archivo · Agregar un tamaño nuevo a esta familia (en Civil 3 · Agregar un tipo nuevo a esta utilidad: se guarda e · Cambiar a curva · Quitar la válvula · Volver a la cota de la utilidad unida · Volver a tratar como buzón/caja

*Sin aro — casilla (cambia un ajuste al instante) (1):* Poner este accesorio (también en Civil 3D)

*Sin aro — conmutador (alterna un modo) (3):* Activar edición por tramo · Cambiar a elemento curvo · Desactivar/activar buzón

*Sin aro — control del sistema (cerrar, flotar…) (1):* qt_tableview_cornerbutton

## _CajaFlujo

**Con aro (2):** Auto · Ocultar el sentido del flujo en el plano

*Sin aro — conmutador (alterna un modo) (2):* Elegir en el plano · Por tramos

## barraSuperior

**Con aro (7):** Capas  ▾ · Deshacer (Ctrl+Z) · Exportar a Civil 3D · Hoja anterior · Hoja siguiente · Modo claro / oscuro · Rehacer (Ctrl+Shift+Z)

*Sin aro — abre un menú (la acción es la del menú) (1):* P

*Sin aro — conmutador (alterna un modo) (1):* Asistente

*Sin aro — control del sistema (cerrar, flotar…) (1):* qt_toolbar_ext_button

## cabeceraInspector

**Con aro (2):** Centrar en el plano · Ver en 3D

*Sin aro — abre un menú (la acción es la del menú) (1):* Más acciones

## filaReconocer

**Con aro (18):** Interpreta la hoja antes de reconocer. · Vista previa

*Sin aro — abre un menú (la acción es la del menú) (9):* Más opciones

## flotante

**Con aro (3):** Acercar · Alejar · Encuadrar todo

*Sin aro — conmutador (alterna un modo) (2):* Editar / mover vértices · Seleccionar (Esc)

## inicioColumna

**Con aro (7):** C:\Users\bernu\AppData\Local\Temp\pytest-of-bernu\ · C:\Users\bernu\Downloads\FINA.digproj · C:\Users\bernu\Downloads\Preuba lineas imagen.digp · C:\Users\bernu\Downloads\QS Water Indian School So · Hoja en blanco para dibujar sin PDF · Plano vectorial o escaneado · Un proyecto .digproj guardado

## panelHeader

**Con aro (4):** Fijar el panel (que no se oculte) · Ocultar automáticamente: el panel queda como una p

## panelTab_der

*Sin aro — conmutador (alterna un modo) (1):* Propiedades

*Sin aro — control del sistema (cerrar, flotar…) (2):* qt_dockwidget_closebutton · qt_dockwidget_floatbutton

## panelTab_izq

*Sin aro — conmutador (alterna un modo) (1):* Dibujar

*Sin aro — control del sistema (cerrar, flotar…) (2):* qt_dockwidget_closebutton · qt_dockwidget_floatbutton

## panelesRiel

**Con aro (15):** + · Abajo (Y−) por Paso · Abrir diseñador de Duct Bank · Aplicar · Arriba (Y+) por Paso · Borrar zona (polígono) · Colocar Leader · Derecha (X+) por Paso · Dibujar utilidad · Izquierda (X−) por Paso · QPushButton · Texto libre · Trazar centerline · −

*Sin aro — casilla (cambia un ajuste al instante) (2):* Abandonado · Extender: continuar la misma

*Sin aro — control del sistema (cerrar, flotar…) (8):* Borrar zona · Dibujar utilidad · Duct Bank · Leader (flecha simple) · Mover con precisión · Texto libre · Trazar centerline · Vista y páginas

*Sin aro — selector (cambia un ajuste al instante) (2):* Toda la utilidad · Un vértice

## riel

**Con aro (7):** Ajustes: idioma, tema, paneles, asistente IA, fami · Diseñador de Duct Bank · Monitor de rendimiento: memoria, procesos, pausas  · Normativas de diseño · Perfil longitudinal · Tabla de datos · Vista 3D

*Sin aro — abre un menú (la acción es la del menú) (1):* Ayuda: manual, atajos de teclado, acerca de

*Sin aro — conmutador (alterna un modo) (5):* Dibujar · Hoja y PDF · Inventario · Reconocer · Revisión

*Sin aro — control del sistema (cerrar, flotar…) (1):* qt_toolbar_ext_button

## segmentado

*Sin aro — conmutador (alterna un modo) (9):* Asistente · Blanco · Chat · Civil 3D · Conflictos · Negro · Propiedades

## sinFondo

**Con aro (37):** + Nuevo · 0 por verificar · Agregar utilidad desde otro PDF · Aprobar… · Cambiar… · Cancelar · Capas y estilos… · Componer hoja de trabajo… · Copiar propiedades de la utilidad (Ctrl + Mayúsc + · Detener · Duplicar · Editar · Editar utilidades seleccionadas en bloque… (Ctrl + · Enviar · Georreferenciar… · Hoja anterior · Hoja siguiente · Importar superficies · Informe automático · Interpretar la hoja · Mostrar todos · Normativas de diseño · Ocultar todos · Otro diámetro… · Pegar propiedades en las seleccionadas (Ctrl + May · QPushButton · Quitar · Reconocer todo · Resolver conflictos · Revisa las líneas vecinas · Revisar con la IA · Revisar y limpiar el dibujo · ScrollLeftButton · ScrollRightButton · Unir utilidades seleccionadas (Ctrl + J) · ¿Por qué?

*Sin aro — conmutador (alterna un modo) (25):* Abandonada · Abandonadas · Accesorios · Borrar · Buzón · Centerline · Codos · Con avisos · Cruces · Duct Bank · Leader · Marcas de las hojas · Minimapa de las hojas · Mostrar accesorios (tipo y ángulo) · Mostrar avisos de normativa · Mostrar avisos de reconocimiento · Mostrar cruces/conflictos · Mover · Tees · Texto · Todas · Todos · Utilidad · Válvulas · Wyes

## tarjetaSuave

**Con aro (2):** Ver análisis · Ver opciones

## Acciones sin botón (menús, atajos, paleta Ctrl+K)

Abrir PDF… · Abrir carpeta de aprendizaje · Abrir proyecto… · Acciones · Acerca de… · Agregar utilidad desde otro PDF… · Atajos de teclado · Capas y estilos… · Cerrar proyecto · Componer PDF imagen/escaneo… · Componer hoja de trabajo… · Configurar IA… · Copiar propiedades de la utilidad · Deshacer · Desinstalar familia personalizada… · Diagnóstico del equipo… · Editar utilidades seleccionadas en bloque… · FINA.digproj  ·  Hace 16 min · Georreferenciar… · Guardar proyecto · Guardar proyecto como… · Herramientas · Importar superficies… · Informe automático… · Insertar buzón en línea… · Instalar familia personalizada… · Inventario · Leer rótulos ilegibles con la IA… · Manual de usuario · Marcas de las hojas · Minimapa de las hojas · Modo claro · Mostrar accesorios (tipo y ángulo) · Mostrar avisos de normativa · Mostrar avisos de reconocimiento · Mostrar cruces/conflictos · Mostrar todos · Normativas de diseño… · Nuevo lienzo… · Ocultar automáticamente el panel derecho · Ocultar automáticamente el panel izquierdo · Ocultar todos · Opciones… · Pasar a producción… · Pegar propiedades en las seleccionadas · Perfil longitudinal · Pregúntale al proyecto… · Preuba lineas imagen.digproj  ·  Ayer · QS Water Indian School South - recuperado 1023.digproj  ·  Hace 1 h · Quitar georreferencia · Rehacer · Resolver conflictos… · Revisar y limpiar el dibujo… · Riel · Tabla de datos… · Unir tramos · Unir utilidades seleccionadas · Vista 3D · agregada.digproj  ·  Hace 2 días
