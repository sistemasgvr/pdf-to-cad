# IA ↔ Civil 3D (MCP)

La IA consulta el dibujo abierto en Civil 3D y **propone** cambios; el usuario los confirma. Funciona con dos
entradas que usan el mismo servidor:

1. **La app (Qwen local)** — `app/ia/civil3d_mcp.py` + `app/ia/civil3d_agente.py` (perfil `basico`).
2. **Claude Code / Claude Desktop** — se registra el servidor y listo (perfil `completo`).

## Arquitectura (limpia)

```
Claude (Code/Desktop) ─┐                           ┌───────────── plugin (dentro de Civil 3D) ─────────────┐
App Python + Qwen ─────┴─ MCP stdio ─► PdfCadMcp.exe ─ tubería ─► Infraestructura ─► Aplicación ─► Dominio
                                       (Presentación)  \\.\pipe\   (Civil 3D API)    (casos de uso) (reglas)
```

| Capa | Carpeta | Depende de |
|---|---|---|
| Contratos | `API-CIVIL/proyecto1/proyecto1/Mcp/Contratos` — protocolo de la tubería y **catálogo cerrado** de herramientas | nada |
| Dominio | `…/Mcp/Dominio` — foto del modelo (ft / in), resúmenes, filtros, reglas de cada cambio | nada |
| Aplicación | `…/Mcp/Aplicacion` — `Despachador` (perfil, validación, propuesta → confirmación, registro) y puertos | Dominio, Contratos |
| Infraestructura | `…/Mcp/Infraestructura` — lector/editor de Civil 3D, hilo de AutoCAD, registro `.jsonl`, servidor de la tubería | Aplicación + Autodesk |
| Presentación | `API-CIVIL/proyecto1/PdfCadMcp` — servidor MCP por stdio (JSON-RPC 2.0) | solo Contratos |

Ni Dominio ni Aplicación conocen Autodesk ni MCP: se prueban sin Civil 3D (`McpPruebas`). Un cliente nuevo
(Slack, chat dentro de C3D) es solo otro adaptador; las reglas no se tocan.

## Lineamientos

- Unidades imperiales: cotas y largos en pies, diámetros en pulgadas.
- Los números los calcula el plugin; la IA elige herramientas y redacta.
- **Ningún cambio sin confirmación**: `proponer_cambio` devuelve id + antes/después + consecuencias +
  advertencias; `confirmar_cambio` solo tras el sí del usuario (en la app, solo el botón: el modelo no lo ve).
  Si el elemento cambió desde la propuesta, se rechaza; las propuestas vencen a los 30 min.
- Cada cambio = un paso de deshacer (**U**) y una línea en `<dibujo>.pdfcad-ia.jsonl` junto al DWG
  (quién, origen claude/qwen, cuándo, antes/después, motivo). Dibujo sin guardar → `%APPDATA%\pdf-to-cad\civil3d-ia\`.
- Los elementos se piden por su NOMBRE como lo dice el usuario (`elemento`: «electrico 4 (1)» = «ELECTRICO-4 - (1)»,
  `Dominio/Referencias.cs`); el handle sigue valiendo. Ambiguo o inexistente → el error lista los parecidos.
- Lista cerrada de herramientas; nada de código libre en AutoCAD. La tubería solo acepta al usuario actual.
- Pocos tokens: salidas en tabla (`columnas` + `filas`), topes (`limite`, máx. 200) con «hay N más»,
  descripciones cortas, foto del modelo cacheada hasta que el dibujo cambia.

## Herramientas

| Nombre | Tipo | Perfil básico |
|---|---|---|
| `estado` | lectura | sí |
| `resumen_modelo` | lectura | sí |
| `buscar_tuberias` (red, capa, diámetro, pendiente, texto) | lectura | sí |
| `buscar_estructuras` (red, texto, profundidad) | lectura | no |
| `detalle_elemento` (por nombre → geometría, conexiones, Property Sets) | lectura | sí |
| `ir_a` (encuadra y selecciona) | lectura | sí |
| `proponer_cambio` (`cota_inicio`, `cota_fin`, `capa`, `descripcion`; `valor` o `sumar` ft) | cambio | sí |
| `buscar_conflictos` (cruces con choque, sin la separación de la normativa o en el orden contrario; K1…) | lectura | sí |
| `proponer_solucion` (`conflicto`; opcional `mover`, `accion`, `opcion`) — sube/baja una utilidad entera | cambio | sí |
| `datos_red` (todas las tuberías y estructuras: utilidad, tipo, material, diámetro, puntas, cotas) | lectura | sí (la app no se la ofrece al modelo) |
| `proponer_pendiente` (`elemento`/`elementos`/`red`; opcional `pendiente_pct`, `mantener` inicio\|fin) — rasantes nuevas | cambio | sí |
| `proponer_tamano` (`elemento`/`elementos`/`red`; `diametro_in` y/o `material`) — otro tubo de la lista de piezas | cambio | sí |
| `crear_perfil` (`desde`, opcional `hasta`, `nombre`) — CREAR_PERFIL_RED sin preguntar | cambio | sí |
| `confirmar_cambio` / `cancelar_cambio` | cambio | sí (en la app, solo el usuario) |
| `historial` | lectura | no |

Agregar una herramienta: catálogo (`McpHerramientas.cs`) + caso en `Despachador.cs` (+ puerto/adaptador si
hace falta leer o escribir algo nuevo) + prueba en `McpPruebas`. Un cambio nuevo: `TiposCambio` y
`ReglasCambio.Preparar` (Dominio) + `Civil3DEditor.Aplicar`. Contratos: solo se AGREGAN campos.

## Conflictos entre tuberías (2026-11-05)

`Dominio/ConflictosRed.cs` + `Dominio/SolucionesRed.cs` (PUROS), mismo criterio que «Resolver conflictos» de la app:

- **Buscar**: dos tuberías que se cruzan en planta (no las de la misma red unidas punta con tramo, ni las de la
  misma utilidad de la app). En el cruce: eje = rasante + D/2, pared a D/2 del eje (sin espesor). Conflicto =
  `choque` (paredes que se meten), `separacion` (libre < lo que pide la normativa) u `orden` (la normativa dice
  quién va encima y está al revés). Numerados K1… de arriba abajo y de izquierda a derecha.
- **Separaciones**: llegan en `reglas` = `[{a, b, sep_v_ft, encima|debajo, fuente}]` (b `*` = con cualquiera). La
  app las saca de su catálogo de normativas (`app/ia/civil3d_reglas.py`) y el agente las pone en cada llamada (el
  modelo no las ve). Sin reglas (p. ej. Claude sin pasarlas) solo se buscan choques.
- **Soluciones**: subir o bajar UNA utilidad entera (`Tuberia.UtilidadNumero/UtilidadCapa` = Property Set
  `PDFCAD_Utilidad`: todas sus tuberías de esa red), lo justo para dejar la separación (redondeado hacia arriba a
  0.01 ft), respetando quién va encima. Cada opción se prueba: resuelve, no crea conflictos nuevos, no separa uniones
  (accesorio que une con una tubería que no se mueve; punta con punta a la misma cota sin accesorio ni buzón real).
  Orden: válidas, no gravedad (alcantarillado/drenaje), menos movimiento, bajar antes que subir. `P1` = la propuesta.
- **Aplicar** (`TiposCambio.DESPLAZAR`, `Civil3DEditor.Desplazar`, un paso de U): piezas de presión de Civil 3D
  (`Position`: arrastran las puntas conectadas), cada tubería a su punto FINAL (original + Δz), sólidos del plugin
  (`TransformBy` + `COTA_EJE_FT` del XDATA); comprueba y avisa en la consola si algo quedó corrido. Confirmar
  rechaza si las cotas cambiaron desde la propuesta (`Huella`).
- Accesorios leídos: piezas de las redes a presión (con sus tuberías conectadas) y sólidos con XDATA
  `PDFCAD_FITTING` (codos, Tees, Wyes, cruces, válvulas; RED = la red, alcance = LARGO_TOTAL_FT/2 + 0.5 ft).
- Sin probar dentro de Civil 3D: el movimiento de redes a presión es lo que hay que revisar primero.

## Normativas, pendientes, tamaños y perfiles (2026-11-05)

- **`revisar_normativas`** es de la APP, no del plugin (`app/ia/civil3d_normativas.py`): pide `datos_red`, encadena
  las tuberías de cada utilidad de la app (Property Set `PDFCAD_Utilidad`: capa + número; campo `TIPO` = su tipo;
  material = la Descripción) en una polilínea con sus rasantes, la parte donde cambia el diámetro o el material o
  hay una bifurcación, y corre el MISMO validador de la app (`normas_validar` + `accesorios`): diámetro, pendiente,
  largo, material, quiebres, buzones, accesorios y separaciones. Coordenadas en px de `FT_PX`=0.08 ft (las
  tolerancias de la app están en px). Avisos N1… (los más graves primero, máx. 40); «sin tipo» y las tuberías que
  no vienen de la app se cuentan aparte.
- **Pendiente** (`Dominio/CambiosRed.Pendiente`, `TiposCambio.PENDIENTE`): por tubería de gravedad, la pendiente
  que pide la normativa (`normas` = `civil3d_reglas.reglas_tuberia`: reglas activas de pendiente/diámetro/material
  de TUBERIA, sin las de amperaje; mismo «alcance» = basta una, alcances distintos = todos) o la que dijo el
  usuario. Mueve el fin (o el inicio con `mantener=fin`); con varias tuberías solo las que no cumplen. Avisa:
  bajo el fondo / sobre la tapa de un buzón y una tubería que llega más abajo que la que sale de ahí.
- **Tamaño** (`CambiosRed.Tamano`, `TiposCambio.TAMANO`): elige de la lista de piezas de la red (`IModeloLector.
  Tamanos` → `Infraestructura/Civil3DTamanos.cs`): gravedad = familias y tamaños de la PartsList
  (`SwapPartFamilyAndSize`, la rasante no cambia), presión = tubos de la PressurePartList (`SwapPartSize`, el eje no
  cambia). Material con sinónimos ES↔EN (`NormasRed.MismoMaterial`: concreto = concrete…); sin material, la misma
  familia. Avisa si la normativa no lo permite, si queda más grande que la tubería de aguas abajo o si hay
  accesorios de presión conectados del diámetro anterior.
- **Perfil** (`CambiosRed.Perfil`, `TiposCambio.PERFIL`): semilla y fin = el medio de la tubería de inicio y de
  fin; al confirmar, `ComandosPerfil.CrearAutomatico` (como los perfiles de IMPORTAR_RED) debajo del dibujo.
- Confirmar rechaza si las cotas (pendiente) o el tamaño cambiaron desde la propuesta (huella).
- Sin probar dentro de Civil 3D: el cambio de tamaño (sobre todo presión) y el perfil desde el MCP.

## Orden del MCP (2026-11-05)

- **Catálogo por tema**: `Mcp/Contratos/Herramientas/` — `Catalogo.cs` (perfiles + `E`, que escribe los JSON Schema),
  `HerramientasLectura.cs`, `HerramientasCambios.cs`, `HerramientasConflictos.cs`.
- **Repartidor con registro**: `Despachador.cs` (política común: perfil, propuesta → confirmación, registro) y cada tema
  registra sus casos (`RegistrarLecturas/Conflictos/Red/Obra` en `Despachador*.cs`). `Descuadres()` = herramientas sin
  caso o casos sin herramienta (lo revisa `McpPruebas`).
- **Un cambio = una clase** (`Dominio/Cambios.cs`): `CambioSimple`, `CambioMover` (vertical y en planta), `CambioPendiente`,
  `CambioTamano`, `CambioPerfil`, `CambioBuzon`, `CambioValvula`, `CambioQuitarAccesorio`, `CambioConexionVertical`. Cada
  una sabe si sigue valiendo al confirmar (`Vigente`, por su huella) y qué hace en datos (`Efecto`). El editor
  (`Civil3DEditor*.cs`) aplica cada clase con un `switch` por tipo.
- Herramienta nueva: entrada en el archivo del tema + caso registrado (+ clase de cambio y su `case` en el editor si cambia
  algo) + prueba.

## Normativas: siempre las de la app

El plugin NO tiene reglas de normativa (se quitó `NormasRed`; queda `Materiales` = sinónimos ES↔EN). La app
(`app/ia/civil3d_locales.py`) pone en cada llamada lo que es suyo: las separaciones (`reglas`, de `civil3d_reglas`) y la
pendiente objetivo de cada tubería (`objetivos` = `civil3d_normativas_cambios.objetivos_pendiente`, con
`normas_validar.aplica/agrupar`). Cada propuesta trae su `efecto`; la app lo aplica a una copia de `datos_red` y la revisa
con su validador (`con_normativa`): avisos nuevos → advertencias «Normativa: …», resueltos → consecuencia.

## Herramientas nuevas (2026-11-05)

| Nombre | Tipo | Notas |
|---|---|---|
| `buscar_accesorios` | lectura | accesorios agrupados (los sólidos de uno = uno), ids A1… |
| `revisar_buzones` | lectura | tubería bajo el fondo, corona sobre la tapa, tapa bajo el fondo |
| `metrados` | lectura | largo por utilidad/diámetro/material, accesorios por tipo, estructuras por tamaño |
| `buscar_choques_3d` | lectura | `Cuerpos()` + `Choques3D.Pares` (cajas, sin lo unido a propósito) + `Interferencias` (`Solid3d.CheckInterference`: cilindro por tubería, `Solid3dBody` o caja de la pieza, sólidos tal cual) |
| `proponer_buzon` | cambio | tapa/fondo/altura (`Structure.RimElevation/SumpElevation`) |
| `proponer_valvula` | cambio | poner (`ComandosRedes.McpPonerValvula` = `PonerValvula` de IMPORTAR_RED) o quitar (une los dos tubos) |
| `proponer_quitar_accesorio` | cambio | borra la pieza/sólidos; sus tuberías se alargan a su centro sin unirse |
| `proponer_conexion_vertical` | cambio | `ComandosRedes.McpConexionVertical` = `CrearConexionesCruzadas` de IMPORTAR_RED |
| `proponer_mover_planta` | cambio | `dx`/`dy` o `lado`+`distancia`; accesorios y estructuras propias se mueven; conflictos antes/después |
| `revisar_normativas`, `exportar_cuadro`, `comparar_con_app`, `traer_a_la_app` | de la APP | `civil3d_normativas`, `civil3d_cuadro` (Excel/Word junto al DWG), `civil3d_comparar` (la tarjeta «Aplicar en la app» la aplica la ventana, Ctrl+Z) |

Sin probar dentro de Civil 3D: choques 3D (piezas sin `Solid3dBody` usan su caja), válvulas, quitar accesorio, conexión
vertical y mover en planta.

## Revisión del plano (2026-11-05)

`Dominio/Textos.cs` (anotaciones: `TextoDibujo` con su `Caja`, `Guia`, `Cota`, `Trama`), `Dominio/RevisionPlano.cs`,
`Dominio/CambiosTexto.cs` (`CambioTexto`, `CambioBorrar`, `CambioCota`), `Infraestructura/Civil3DAnotaciones.cs` (lee TEXT,
MTEXT, MLEADER con su texto y guías, LEADER, cotas alineadas/giradas y tramas) y `Civil3DEditorTexto.cs`.

| Nombre | Tipo | Notas |
|---|---|---|
| `revisar_plano` | lectura | Q1…: `guia_cruza_texto`, `guia_cruza_cota`, `flecha_suelta`, `texto_sobre_texto`, `cota_sobre_texto`, `texto_en_trama` (cajas en planta; trama ≤ 400× el texto) |
| `buscar_cotas` | lectura | texto, medida real, estilo, decimales, flecha, altura |
| `proponer_arreglo_revision` | cambio | Q# → mover lo justo (perpendicular a la guía o separando cajas), borrar la flecha suelta o máscara (MTEXT/MLEADER) |
| `proponer_texto` | cambio | `elemento` o `buscar`; `reemplazar`/`por` (vacío = quitar), `dx`/`dy`, `altura`, `mascara` |
| `proponer_cota` | cambio | crear alineada o cambiar estilo/decimales/flecha/altura/texto («» = medida real) |
| `comparar_con_pdf` | de la APP | `app/ia/civil3d_pdf.py`: tinta del PDF (imagen en grises de la app) bajo cada tubería/buzón (la inversa de la transformación del DXF) y lo de la app sin tubería en Civil 3D |

Sin probar dentro de Civil 3D. Cajas aproximadas: la de un TEXT girado es su caja en ejes; la del texto de una cota y la
del MLEADER se estiman con su altura y largo.

## Uso

1. En Civil 3D: `PANEL_REDES` → **«Encender conexión de la IA»** (o el comando `PDFCAD_IA`; otra vez = apagar).
2. Comprobar (opcional):
   ```powershell
   & "API-CIVIL\proyecto1\PdfCadMcp\bin\Release\net8.0\PdfCadMcp.exe" --probar
   ```
3. **Claude Code**:
   ```powershell
   claude mcp add pdfcad-civil3d -- "D:\…\PdfCadMcp\bin\Release\net8.0\PdfCadMcp.exe" --origen claude
   ```
   **Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
   ```json
   { "mcpServers": { "pdfcad-civil3d": {
       "command": "D:\\…\\PdfCadMcp.exe", "args": ["--origen", "claude"] } } }
   ```
4. **App (Qwen)**: Asistente → pestaña **Civil 3D** (`ui/dialogos/ia_civil3d.py` + `ia_civil3d_html.py`, mismo aspecto que el Chat; tarjeta de propuesta con «Aplicar en Civil 3D» / «Descartar»). Por código: `ClienteMCP(perfil="basico", origen="qwen")` + `Agente(cliente, pedir_ollama(config))`;
   `preguntar(texto)` → `Resultado(texto, propuestas)` y la ventana confirma con `agente.confirmar(id)`.
   El modelo debe soportar *tools* en Ollama.

## Compilar y probar

```powershell
dotnet build -c Release API-CIVIL\proyecto1\proyecto1      # plugin (incluye el MCP)
dotnet build -c Release API-CIVIL\proyecto1\PdfCadMcp      # host MCP
cd API-CIVIL\proyecto1\McpPruebas; dotnet run -c Release   # 79 pruebas, incluida la de punta a punta
python -m pytest tests/test_civil3d_mcp.py                 # entrada 1 (app)
```

## Pendiente

- `PdfCadMcp.exe` en el instalador (`build_all.bat` / Inno Setup).
- Más cambios: diámetro/tamaño (por catálogo de familias), mover, perfiles.
- Probado sin Civil 3D (dobles + host real + tubería real); falta la prueba en Civil 3D con un dibujo real.
