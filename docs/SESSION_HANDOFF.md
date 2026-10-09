# Handoff — cambios de las últimas 48h (georreferenciación, centerlines, buzones ocultos)

> Generado el 2026-08-24 para continuar el proyecto en otra sesión/cuenta de Claude Code.
> Todo lo de acá está **sin commitear** todavía (ver sección "Estado del repo" al final) — es
> el resultado de una sesión larga de trabajo sobre la rama `dev_deyvy`.

## Qué es este proyecto

Pipeline PDF → dibujo 2D → red 3D en Civil 3D, para el flujo de trabajo propio de un
ingeniero civil: `app/` (Python/PySide6) digitaliza planos PDF de utilidades (agua,
alcantarillado, drenaje, gas, eléctrico, telecom) y exporta un DXF con la red codificada
como XDATA; `API-CIVIL/proyecto1/proyecto1/` (C#, namespace `Civil3DBasico`) es el plugin
de Civil 3D que lee ese XDATA y arma la red real (tuberías, estructuras, familias/tamaños
imperiales). Todo el proyecto trabaja en pies (imperial) — nunca metros en el flujo de red 3D.

## Resumen ejecutivo (features nuevas de las últimas 48h)

1. **Auto-población de tamaños de familias personalizadas en Civil 3D** (`PrepararFamilias.cs`).
2. **Ocultar buzón**: un vértice puede no crear un manhole visible ni en Python ni en
   Civil3D, sin romper la topología de la red.
3. **Cotas por tramo editables**: toda la columna "Inicio" de la tabla es editable y
   sincronizada con "Elev. rasante inicial/final".
4. **Centerlines de referencia**: entidad nueva, distinta de las utilidades, con su propio
   modo de dibujo, tab, panel de propiedades, export a DXF y — lo más importante — se usan
   para mejorar la georreferenciación emparejando tu trazo contra la calle real.
5. **Diálogo de Georreferenciación reescrito y pulido en varias rondas**: mapa real de LA
   (NavigateLA) con calles + parcelas, snap a intersección exacta, PDF con opacidad
   ajustable y líneas vectoriales (no rasterizadas), Ctrl+Z, navegación uniforme con rueda/
   botón central, ventana redimensionable, guardado que cierra solo, recarga automática al
   reabrir, fetch en 2º plano (no congela la UI).
6. **Deploy del plugin sin NETLOAD manual**: `installer\build_plugin.bat` compila y copia
   solo al autoload de Civil 3D.
7. **Manual de usuario** (`Ayuda → Manual de usuario` en la app) actualizado con todo esto.

---

## 1. Familias personalizadas — auto-población de tamaños

**Archivo**: `API-CIVIL/proyecto1/proyecto1/PrepararFamilias.cs`.

El botón queda conectado directo al flujo automático (sin diálogo manual): detecta qué
familias personalizadas (excluyendo las de fábrica de Civil3D) están realmente en uso en
los datos importados del DXF actual, calcula todas las combinaciones Width×Height (tubería)
o Width×Length (estructura) presentes, y las agrega a la Parts List "Standard".

**Gotcha importante ya resuelto**: `PartSize.AddPartSize` **NO** expande un producto
cartesiano aunque los `SizeFilterField` tengan `IsMultipleSelect=true` — hay que loopear y
llamar `AddPartSize` una vez por cada combinación real, leyendo los valores reales vía
`SizeFilterField.ValueList` (confirmado con logs de debug reales dentro de Civil3D, no supuesto).

**Otro gotcha**: `PartContextType` vive en `Autodesk.Civil.DatabaseServices`, NO en
`Autodesk.Civil.DatabaseServices.Styles` (se verificó con reflection vía
`MetadataLoadContext` antes de asumir la firma correcta — ver sección de metodología abajo).

**Bug de matching corregido**: el código anterior comparaba tamaños parseando
`PartSize.Name` (que ya trae las dimensiones OUTER, calculadas por una fórmula propia de
cada familia). Se cambió a leer la dimensión INNER real vía
`PartSize.SizeDataRecord.GetDataFieldBy(PartContextType)`, que es lo que realmente hay que
comparar contra el valor del catálogo/XML. **Importante**: los valores INNER crudos del XML
(ej. "24x72") son los correctos a mostrar en el dropdown de Python — NO hay que convertirlos
a outer. Este fue un error que se cometió y se revirtió durante la sesión; quedó confirmado
con un XML real que pegó el usuario.

---

## 2. Ocultar buzón

**Por qué**: algunos vértices se auto-detectan como buzón (`_rebuild_structures()` en
`app_window.py`) pero en la realidad no son un acceso físico. Confirmado con el usuario que
"ocultar" debe llegar hasta Civil3D, no ser solo cosmético en Python.

**Cómo funciona (importante, no es solo "omitir el XDATA")**: si un buzón oculto
simplemente no se exportara, `ImportarRed.cs` cae al fallback `defStructFam/defStructSize`
(la primera familia real, un manhole visible) porque la red necesita SÍ o SÍ un Structure en
ese vértice para la topología. La solución correcta usa la familia
**"Estructura nula" / "Null Structure"** (invisible en 3D, mantiene la conexión) — antes solo
se usaba automático en redes conduit; ahora también aplica en gravedad cuando el vértice
viene marcado `hidden`.

- `app/model.py`: `struct["hidden"]` (bool, default False), documentado en el docstring del módulo.
- `app/app_window.py`: checkbox → **botón** `chk_bz_hidden` ("Ocultar buzón") en el panel de
  propiedades del buzón; handler `_bz_hidden_toggled`; `_draw_structures()` salta el dibujo
  si `hidden`; la lista de buzones NO filtra los ocultos (siguen siendo clickeables para
  des-ocultar), pero se muestran en gris con ícono distinto.
- `app/dxf_export.py`: `_export_structures()` sigue exportando el punto (la red necesita el
  nodo) pero agrega `HIDDEN=1` al XDATA; se omite el texto de código si está oculto.
- `API-CIVIL/proyecto1/proyecto1/ImportarRed.cs`: `ImportStruct.Hidden` parseado del XDATA;
  hay un local function `BuscarEstructuraNula(out fam, out size)` extraído y reusado tanto
  para el fallback de conduit como para el caso `match.Hidden` — esta condición gana ANTES
  de mirar `structType`/`NetKind`, así que aplica sin importar el tipo de red.

---

## 3. Cotas por tramo editables

**Archivo**: `app/app_window.py`, `_rebuild_seg_inv_table` y alrededores.

Toda la columna "Inicio" (incluyendo el primer tramo) y "Fin" (incluyendo el último) son
`_SegInvSpinBox` editables — antes el primero/último eran `QLabel` fijos. Editar la celda del
primer/último vértice escribe directo a `p["inv_start"]`/`p["inv_end"]` de la utilidad y
sincroniza (`setValue`, con guard anti-reentrancia) los campos "Elev. rasante
inicial/final" de arriba — y viceversa, `_prop_changed` ya llamaba a
`_rebuild_seg_inv_table` así que el camino inverso ya funcionaba solo.

Se eliminaron las columnas "Pendiente" y "Auto" (pedido explícito del usuario, quedó una
tabla más simple). La tabla solo es visible cuando la pestaña activa es Utilidades
(`gprop_segs.setVisible(self._current_tab() == TAB_PIPE)` en `_rebuild_seg_inv_table` y en
`_tab_changed`).

---

## 4. Centerlines de referencia (entidad nueva)

**Por qué**: distinto de trazar una utilidad — sirve para mejorar la precisión de la
georreferenciación emparejando el centerline que vos dibujás contra la calle real de
NavigateLA. Ver sección 5 para el uso en el diálogo de georref.

- `app/model.py`: `TAB_CL = 7` (después de `TAB_CURVE`); docstring documenta
  `ref_centerline = {cod, pts:[(x,y)…]}`.
- `app/app_window.py`:
  - Estado: `self.ref_centerlines`, `self._cl_pts` (scratch de dibujo), `self.sel_cl`.
  - Tab real `self.cl_list` (QListWidget) registrada en `_tab_map()`.
  - Acordeón nuevo "📐 Trazar centerline" (`btn_centerline`, `_slot_gcur_cl`); modo de
    dibujo mirror del modo pipe pero con su propio buffer (`_cl_pts`), igual patrón que el
    modo "erase" tiene el suyo (`_erase_pts`) — para no contaminar estado entre modos.
  - Panel de propiedades `gprop_cl` (código editable con chequeo de unicidad, longitud
    real de solo lectura vía `_to_cad`).
  - `finish_centerline()` auto-codifica "CL-N".
  - **Dibujo en `_redraw()`**: magenta punteado (`QColor(255,60,220)`), grosor
    `7.0 if sel else 2.0` (se subió de 3.0 a 7.0 — "mucho más grueso" fue pedido explícito).
  - **Selección desde el lienzo**: `_pick(x,y)` ahora también hit-testea
    `self.ref_centerlines` (antes solo pipes/leaders/textos/buzones eran clickeables) —
    bloque agregado justo antes del hit-test de pipes.
  - `_poly()` se extendió con parámetro `dash`.
- `app/dxf_export.py`: `_export_ref_centerlines()` — capa `REF_CENTERLINES` (color 6,
  magenta), `add_lwpolyline` + texto de código, **sin XDATA** (no participa en la red).
  Se llama desde `merge_into()` justo después de `_export_structures`.

---

## 5. Diálogo de Georreferenciación — reescritura + pulido iterativo

**Archivo**: `app/geo/georef_dialog.py` (el más tocado de toda la sesión, por lejos).

### Diseño general
Splitter horizontal: **izquierda** = el plano (PDF + utilidades + centerlines dibujados,
click con imán) — clase `_PdfPickView` (QGraphicsView). **Derecha** = mapa real de Los
Ángeles (NavigateLA, EPSG:2229 / State Plane CA Zona V, pies) — clase `_MapCanvas`
(matplotlib QtAgg embebido). Con ≥3 pares de puntos se ajusta una transformación afín
(`geo/georef.py::fit`, reusado sin cambios) y "💾 Guardar georreferenciación" deja el
resultado en `self._main.georef` y guarda el proyecto.

### Por qué el PDF pasó de "rasterizado" a "vectorial"
Versión vieja: `app_window.py::_render_plan_image()` horneaba TODO (PDF + utilidades +
leaders) en un solo `QImage` vía `scene().render(...)`. Esto causaba pixelado al hacer zoom
y hacía imposible bajarle la opacidad solo al PDF sin afectar las líneas. Se cambió a:
- `open_georef()` ahora pasa el PDF **crudo**: `self.canvas.pixmap_item.pixmap().toImage()`.
- `_PdfPickView.__init__(qimg, pipe_lines, cl_lines)` dibuja el PDF como un
  `QGraphicsPixmapItem` propio (`self._pm`, con `set_pdf_opacity(v)`) y las
  utilidades/centerlines como `QGraphicsLineItem` vectoriales con **cosmetic pen** encima —
  no pixelan nunca, y la opacidad del PDF no las afecta.
- `_render_plan_image()` se **eliminó** de `app_window.py` (quedó sin uso).
- El panel izquierdo ya no tiene texto de indicaciones: tiene una barra `QSlider`
  ("Opacidad PDF:", rango 10-100, conectada a `set_pdf_opacity(v/100)`).

### Mapa (NavigateLA)
- `contextily` para el mapa base (tiles) — **se llegó a borrar por error** en una ronda
  intermedia (se interpretó mal "borra esas opciones que agregaste al mapa" como "borra el
  basemap"), el usuario aclaró que se refería a la `NavigationToolbar2QT` de matplotlib
  (Home/Pan/Zoom/Save) — esa SÍ quedó borrada, el basemap se restauró.
- **Parcelas de NavigateLA**: `fetch_parcels_2229` (ya existía en `geo/la_reference.py`,
  antes solo usada para la capa de referencia opcional al exportar DXF) ahora también se
  descarga y dibuja (gris tenue) en el mapa del diálogo — útil como puntos de control extra
  (esquinas de parcela) cuando el plano solo tiene 1 intersección visible.
- **Optimización de velocidad — la más importante**: antes `_draw_map()` rehacía TODO el
  mapa (calles + parcelas + tiles de red) en cada clic que agregaba/borraba un punto. Se
  separó en `_draw_map_base()` (solo se llama al llegar datos nuevos de un fetch) y
  `_draw_map_markers()` (solo mueve los marcadores rojos, sin tocar el mapa base) — agregar
  un punto ahora es instantáneo.
- Geocode + descarga de calles/parcelas corre en un `QThread` (`_FetchWorker`, con `done`/
  `failed` signals) para no congelar la ventana — antes usaba `QApplication.processEvents()`
  a mano.
- Cache de tiles en disco (`cx.set_cache_dir(~/.pdf_to_cad_tile_cache)`) y se recuerda el
  último proveedor de tiles que funcionó (`self._basemap_provider_i`) para no reintentar los
  3 de `_TILE_PROVIDERS` desde cero cada vez.
- Navegación del mapa ahora **idéntica** al panel del PDF: rueda = zoom (ya existía),
  botón central + arrastrar = pan libre (agregado a `_MapCanvas` con
  `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent`, matemática de pan derivada a mano
  para mantener el punto bajo el cursor fijo mientras se arrastra).

### Snap
- `SNAP_PX = 10` (plano, px de escena), `SNAP_FT` bajado de **30.0 a 15.0** (pies) — el
  usuario reportó que jalaba "con mucha fuerza" desde lejos en el lado del mapa.
- **Nueva función `snap_to_intersection(pt, polylines, max_dist)`**: calcula el cruce
  geométrico EXACTO entre 2 polilíneas distintas cerca del clic (no solo el vértice más
  cercano) — usa `_seg_intersect` (intersección segmento-segmento con parámetros t,u y
  tolerancia 2% en los extremos). Se prueba PRIMERO en ambos paneles (PDF y mapa), y si no
  hay cruce cerca, cae al `snap_to_lines` de siempre (vértice o proyección sobre segmento).
- El flujo manual normal (no "Emparejar centerline") ahora también snapea contra los
  centerlines dibujados (`self._pipe_lines + self._ref_cl_lines`), no solo contra pipes.

### Ctrl+Z
`QShortcut(QKeySequence.Undo, self)` a nivel de todo el diálogo (funciona con foco en
cualquiera de los 2 paneles). `self._undo_stack` guarda LOTES (listas de dicts de pares) —
1 clic manual = lote de 1, "Emparejar centerline" = lote de ~10 — así deshacer un match
automático borra los ~10 puntos de una, no de a uno. `_undo()` primero cancela un punto
pendiente a medias si existe, si no, pop del último lote (comparando por identidad de objeto
para ser robusto si el usuario borró algo suelto con "Eliminar sel." antes).

### Ventana
`QDialog` no trae botón de maximizar por defecto — se agregó
`WindowMaximizeButtonHint | WindowMinimizeButtonHint` a `windowFlags()`, más
`setSizeGripEnabled(True)` y el tamaño inicial se clampea a
`availableGeometry()` de la pantalla (antes `resize(1400, 860)` fijo, se rompía en
monitores chicos).

### Guardar y reabrir
- `_save()`: envuelve `self._main.save_project()` en try/except (muestra error claro si
  falla en vez de dejar el diálogo en un estado raro), y hace `self.accept()` (cierra) apenas
  `project_path` queda confirmado. Si no había path y el usuario cancela el "Guardar como…"
  nativo, se avisa en el hint y el diálogo queda abierto para reintentar — no se pierde el
  resultado ya calculado en memoria.
- **Reabrir con georreferenciación existente**: antes solo se precargaban los pares sobre el
  PDF (puntos verdes), el mapa quedaba vacío hasta buscar de nuevo. Ahora, si hay
  `init_georef.points`, se calcula el centroide de esos puntos (en coordenadas reales) y un
  radio de buffer según qué tan dispersos están, y se dispara un fetch automático
  (`_FetchWorker(buffer_ft, center=(cx,cy))` — el worker ahora acepta `center` directo sin
  geocodificar) para que el mapa aparezca poblado y editable de una.

### Tooltips
`lbl_rms` y `b_fit` ("Ajustar afín + RMSE") tienen tooltip explicando qué es RMSE (error
promedio en pies entre cada punto y donde el ajuste lo ubica) — pedido explícito porque no
era obvio para el usuario.

---

## 6. Deploy sin NETLOAD manual

**Archivo**: `installer/build_plugin.bat` — **ya probado y verificado**, no es solo teoría.

Al final del script (que ya hacía `dotnet publish` + armaba `installer/AsistenteC3D.bundle/`)
se agregó un `robocopy /MIR` hacia
`%APPDATA%\Autodesk\ApplicationPlugins\AsistenteC3D.bundle`, con manejo de `RC GEQ 8` como
error (típicamente: Civil3D abierto con el DLL viejo cargado y bloqueado — el mensaje de
error se lo dice explícito al usuario: cerrar Civil3D y reintentar). Confirmado que los
archivos quedaron en disco en esa ruta tras correrlo.

---

## 7. Manual de usuario

`app/app_window.py::show_manual()` — HTML embebido en un `QTextBrowser`, sin red ni
servidor. Se actualizó con secciones nuevas/reescritas para: cotas por tramo, ocultar
buzón, centerlines de referencia (sección nueva), y georreferenciación (reescrita
completa). El usuario pidió explícitamente que esto se mantenga actualizado en cada
sesión futura — **no te olvides de tocarlo cuando cambies algo user-facing**.

---

## Metodología usada para no adivinar la API de Civil3D

Cuando hubo dudas sobre firmas/namespaces del API de Civil3D (`PartContextType`,
`SizeFilterField`, etc.) se verificó con un proyecto de consola C# de scratch usando
`MetadataLoadContext` + `PathAssemblyResolver` sobre los ensamblados reales de Civil3D, en
vez de asumir. Vale la pena repetir esa técnica si aparecen dudas similares — es más rápido
y confiable que buscar documentación desactualizada.

---

## Errores ya cometidos y corregidos (para no repetirlos)

- **`git commit -- <pathspec>` con `git rm --cached`**: pasar pathspecs explícitos a
  `git commit` re-agrega el contenido del working tree para esos paths, pisando lo que se
  había preparado con `git rm --cached`. Si vas a "des-trackear" algo, hacé el commit SIN
  pathspec una vez que no quede nada más staged.
- **Wheel/pan del diálogo de georref**: se corrigió 2 VECES en direcciones distintas hasta
  llegar al esquema correcto (rueda = zoom siempre, botón central + arrastrar = pan libre,
  igual que Civil3D y que el `Canvas` principal de la app). Si tocás la navegación de algún
  panel nuevo, replicá este esquema — ya está validado por el usuario.
- **`curve_is_bz` checkbox→botón**: al convertir un checkbox a botón, si el panel de
  propiedades SIEMPRE resetea el estado visual (no hay nada persistente que reflejar —
  es una acción de un solo disparo, no un toggle), tiene que ser un botón NO checkable con
  `.clicked` (no `.toggled`), y el handler no puede depender del parámetro `bool` del signal
  (siempre es `False` en botones no-checkable).
- **"Borra esas opciones del mapa"**: pedido ambiguo que se interpretó mal una vez (se
  borró el basemap por error en vez de solo la toolbar). Si un pedido de "borrar código
  basura" es ambiguo sobre alcance, mejor confirmar qué específicamente se ve/usa antes de
  borrar, o preguntar — no asumir el borrado más agresivo.
- **Tamaños INNER vs OUTER**: los valores crudos del XML/catálogo (inner) son los correctos
  para mostrar en Python. La forma "bonita" que calcula Civil3D internamente (outer, vía
  `PartSize.Name`) NO es lo que hay que mostrar ni comparar — ver sección 1.

---

## Estado del repo (a la fecha de este handoff)

Rama `dev_deyvy`. Todo lo de arriba está **sin commitear**, working tree modificado sobre
el último commit (`c44e3fc`, merge de `elvis_oficial`):

```
 M API-CIVIL/proyecto1/proyecto1/ImportarRed.cs   (+56/-…)
 M app/app_window.py                              (+406/-…)
 M app/dxf_export.py                              (+33/-…)
 M app/geo/georef_dialog.py                       (+586/-…, el más grande)
 M app/model.py                                   (+16/-…)
 M installer/build_plugin.bat                     (+25/-…)
```

No se hizo ningún `git commit` durante esta sesión — el usuario no lo pidió explícitamente.
Antes de seguir trabajando, decidí con el usuario si conviene commitear este estado como
punto de control (son cambios grandes y probados solo parcialmente — ver próxima sección).

---

## Lo que falta / sugerido para la próxima sesión

1. **No hubo testing visual real** — esta sesión no tuvo entorno gráfico disponible.
   Todo se validó con `python -m py_compile` (sintaxis) y lectura cuidadosa de código, NO
   ejecutando la app. Antes de dar por cerrado este bloque de trabajo, probar en Civil3D/la
   app real, en este orden:
   - Dibujar 1-2 centerlines, exportar DXF, confirmar la capa `REF_CENTERLINES`.
   - Flujo completo del diálogo de georreferenciar: opacidad del PDF, snap a intersección
     (clickear cerca de un cruce real de 2 calles), "Emparejar centerline dibujado", Ctrl+Z,
     pan con botón central en el mapa, guardar (debe cerrar solo), reabrir (el mapa debe
     poblarse solo).
   - Ocultar un buzón → exportar DXF → `IMPORTAR_RED` en Civil3D → confirmar que se crea una
     "Estructura nula" invisible ahí y que los tramos quedan conectados igual.
   - `installer\build_plugin.bat` con Civil3D cerrado → reabrir Civil3D → confirmar que
     `IMPORTAR_RED` y demás comandos ya están disponibles sin `NETLOAD`.
2. **Mejora ofrecida pero no construida**: cuando se empareja un centerline dibujado largo
   contra la calle real, NavigateLA devuelve el eje de calle segmentado por cuadra (una
   polilínea corta por tramo entre 2 intersecciones), lo que puede hacer tedioso el matching
   si el centerline dibujado cruza varias cuadras. Se le explicó la causa al usuario y se le
   ofreció una mejora futura: auto-extender la selección a los segmentos reales conectados y
   co-lineales (mismo rumbo, capaz mismo nombre de calle si el campo viene en la respuesta
   de NavigateLA — no verificado qué campo es) cuando se clickea uno para el match. No
   implementado — el usuario no lo pidió explícito, solo se dejó como opción.
3. El campo de **nombre de calle** en la respuesta de NavigateLA (capa 337, "ejes de calle")
   nunca se verificó — hoy `_fetch()` en `geo/la_reference.py` solo pide `outFields:
   "OBJECTID"`. Si se quiere la mejora del punto 2, hay que inspeccionar el schema real del
   servicio ArcGIS primero (no asumir el nombre del campo).
4. Revisar si conviene comitear el estado actual antes de seguir — son ~920 líneas
   modificadas sin ningún commit intermedio.
