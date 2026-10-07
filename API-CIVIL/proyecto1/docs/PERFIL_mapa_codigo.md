# Mapa del código del plugin para el perfil longitudinal (CREAR_PERFIL_RED)

Base: `D:/GVR/Proyectos_DEV/EEUU/pdf-to-cad/API-CIVIL/proyecto1/proyecto1/`. Los números de línea corresponden al working tree actual (ImportarRed.cs tiene cambios staged y sin stage). Los archivos del perfil (`AlineamientosPerfiles.cs`, `PerfilUtil.cs`, `PerfilLongitudinalDatos.cs`) no tienen cambios locales.

## Hallazgos que condicionan el rediseño

1. **La mayoría de las redes no tienen eje asociado, y el comando actual aborta con ellas.**
   - `AgruparPipesPorComponente` (ImportarRed.cs:2205-2318) devuelve una entrada por **cadena**, no por componente conectado. Una cadena solo sigue en un "empalme simple": exactamente 2 extremos y ningún vértice interior (2270-2271).
   - `componentes.Count` (2155-2175) cuenta cadenas. `EsGravedad = !sinBuzones && componentes.Count == 1` (2173). En consecuencia:
     - Una red de gravedad con cualquier T o cruz, o con varias subredes, **no recibe** `Network.ReferenceAlignmentId`.
     - Una red conduit **nunca** lo recibe, porque `sinBuzones=true`.
   - En ambos casos CREAR_PERFIL_RED aborta en AlineamientosPerfiles.cs:117-121 aunque los ejes existan. El mensaje pide "reimportar", lo que no resuelve nada.
   - En presión (2743-2773) solo se escribe `PressurePipe.ReferenceAlignmentId` si hay una única cadena. `PressurePipeNetwork.ReferenceAlignmentId` y `ReferenceSurfaceId` existen en la API (verificado) pero nunca se asignan. El parámetro `surfId` llega a `CrearRedPresionCompleta` y no se usa.
   - Además `PartirTramosEnTes` (2447) parte la principal en cada T. Resultado: la línea principal queda como **dos** ejes distintos.

2. **Probable pérdida del primer y último buzón en el perfil.**
   - El eje de gravedad se recorta al **borde** del buzón extremo (`RecortarAlBordeBuzon`, 511-539 y 2382-2415).
   - Pipe.StartPoint/EndPoint quedan en el **centro** del buzón (comentario en CotarTuberias.cs:316-319).
   - Esos centros quedan antes de la estación inicial y después de la final. `Alignment.StationOffset` probablemente lanza para puntos fuera de rango, y entonces `TryStation` (PerfilLongitudinalDatos.cs:111-122) descarta el nodo y los tubos extremos. No se puede verificar sin Civil 3D.
   - Después, `nodos[0].Invert = tramos[0].InvIni` (AlineamientosPerfiles.cs:138-142) mezcla elementos que no se corresponden.

3. **Bancoductos: la red queda sin tuberías.**
   - Los tubos padre con `HasDuctBank` se **borran** de la red después de crearla (`pipesToErase`, 1446, 2032, 2058, 2177-2193). Quedan solo los buzones.
   - La envolvente es un Solid3d en la capa `PDFCAD_DUCT_BANK`, sin XDATA (5366-5640).
   - Los conductos interiores también son Solid3d cilíndricos en `PDFCAD_DUCT_BANK`, sin XDATA (880-971, `if (true) {...; continue;}`).
   - El código que crearía redes `DUCTBANK-{base}-{label}` (838, 974-1031) es **código muerto**: nunca se ejecuta.
   - El eje de esa red sí se crea, con las trazas calculadas antes del borrado.

4. **Las polilíneas DXF originales se borran al importar**, también las de conduit (`BorrarPolylinesConvertidas`, 3095-3129; el comentario de la línea 592 está desactualizado).
   - Después de IMPORTAR_RED ya no hay XDATA `PDFCAD_PIPE` que leer. El perfil tiene que salir solo de objetos de Civil 3D y de los sólidos con XDATA `PDFCAD_FITTING`.

5. **Presión con `FITTING_COMO_SOLIDO = true`** (RedesPresionJunturas.cs:30):
   - La red de presión **no tiene fittings** de Civil 3D, y los tubos no quedan conectados entre sí.
   - Los tubos se recortan al alcance de la campana (`WyeSolido.RecortarTubos`, llamado en WyeSolido.cs:256).
   - Los accesorios son Solid3d, que no admiten `AddToProfileView`. Para representarlos en el perfil hay que usar etiquetas u otro recurso nativo, posicionados con la XDATA.

## 1. Cómo ImportarRed.cs crea cada red

**Agrupación**
- `RedesUnidasPorContacto` (4123-4184): une tubos con la misma capa y el mismo NET_KIND si se tocan (extremo sobre el otro tubo o vértice compartido a ≤0.5 ft).
- Clave de grupo = NET_NAME del primer tubo con nombre (menor PIPE_IDX); si no hay, la capa.
- Reparto por NET_KIND: `pressure` / `conduit` / resto a gravedad (394-408).
- Nombre de red: `hasCustomName ? key : "RED-{key}"` (457-458, 481-482, 569-570).

**Superficie**
- Primera `TinSurface` del dibujo (410-427).
- Solo en gravedad y conduit: `net.ReferenceSurfaceId = surfId` (1399).

**Gravedad** (`CrearRedGravedadCompleta`, 1229-2199, con `sinBuzones:false`)
- `Network.Create(civilDoc, ref nm)` (1396); el nombre final puede cambiar vía `ref`.
- Estructuras:
  - Una por vértice no marcado en `NoManholeVerts` (1677-1836), con `AddStructure(... Point3d(v.X,v.Y,rim) ...)` (1778).
  - `st.Name = STRUCT_ID` del DXF (1830-1831), p. ej. "BZ-1".
  - Rim y sump explícitos, que se reponen al final: primero rim, luego control de sump por elevación, luego sump (2111-2145).
  - Vértices `Hidden`: no se crea **ninguna** estructura (1726-1736).
- Tubos:
  - `AddLinePipe(fam,size,LineSegment3d,ref pid, autoConexion)` por tramo (1907).
  - `pipe.Description = MATERIAL` (2034-2035).
  - Curvas con `AddCurvePipe` (2053), sin estructura en la unión: sus extremos tienen StartStructureId/EndStructureId nulos.
  - El Z de cada extremo se repone al final como `invert + OffsetEjeARasante` (InnerHeight/2 por reflexión; si no, InnerDiameterOrWidth/2) (2092-2108, 2361-2375).
- Tubos abandonados: estilo "Abandonado (PDFCAD)" (1995-2003, 1112-1159).
- Capas: no se asignan por código. Tubos y estructuras usan las capas por defecto de la red (`PipeProfileLayerName`, etc., que existen en la API).

**Conduit (eléctrico / telecom)**
- Es **la misma** `Network` de gravedad, vía `CrearRedGravedadCompleta(... sinBuzones:true)` (478-500).
- Estructura por defecto: la "Estructura nula" del catálogo (1260-1292), creada en cada nodo no oculto (1716-1721).
- `autoConexion=false` (1906), pero igual se llama `ConnectToStructure` si hay estructura (2019-2030). El comentario de la línea 2005 está desactualizado.
- Familias de tubo: las pedidas en el DXF (PIPE_FAMILY / PIPE_GUID).

**Presión** (`CrearRedPresionCompleta`, 2420-2901)
- `PressurePipeNetwork.Create(db, nombre)` (2439) y parts list elegida por `SeleccionarListaPresion`.
- Antes de crear tubos: `FusionarCodosSeguidos` y `PartirTramosEnTes` (2446-2447).
- `AddLinePipe` por tramo (2514); `Description = material` (2535-2543).
- Unificación de cotas en junturas, solo si la diferencia es ≤0.10 ft (2563-2667).
- Solera a eje: Z += NominalDiameter/2, con NominalDiameter **en pies** (2696-2724).
- Accesorios: `ProcesarJunturasPresion` (2736), que en modo sólido genera Solid3d (RedesPresionJunturas.cs:732-787).
- Red aparte "CROSS-CONNECTS" para conexiones verticales (4229), con Info.Red = "CROSS-CONNECTS" (5175).

**Eje (Alignment)**
- Helper `ComandosAlineamientos.CrearAlineamientoDesdePts` (AlineamientosPerfiles.cs:27-64):
  - Polyline con bulge → `Alignment.Create(civilDoc, PolylineOptions{AddCurvesBetweenTangents=false, EraseExistingEntities=true}, nombre, Null, db.Clayer, AlignmentStyles[0], AlignmentLabelSetStyles[0])`.
  - Si falla, devuelve Null y **deja la polilínea huérfana** en ModelSpace (se añade antes de llamar a Create y el `catch` no la borra).
- Gravedad y conduit:
  - Los datos se acumulan en `DatosAlignment` (1080-1088; 2155-2175).
  - El eje se crea **después del commit** en su propia transacción, con los extremos recortados al borde del buzón (502-563).
  - Solo si `EsGravedad`: `netW.ReferenceAlignmentId = alignId` (543-551).
- Nombres del eje:
  - Gravedad: `nm + "-eje"` si hay una sola cadena; `"{nm}-{k}-eje"` con k por cadena (2161, 541).
  - Presión: `"{nombre}-eje"` / `"{nombre}-{k}-eje"` (2750-2752). Se crea dentro de la misma transacción y sin recorte.
- Traza:
  - Por tubo DXF, con los puntos de tangencia de las curvas y su bulge (1647-1663).
  - Las cadenas **no recorren ramales**: se cortan en cualquier juntura que no sea un empalme simple, y cada ramal es otro eje.
  - El comentario de 2147-2150 ("en conduit NO se crea alineamiento") está desactualizado: sí se crea, pero no se asocia.
- `ElementosCurvos.RedondearEjeEnEsquina` (ElementosCurvos.cs:246-300) usa `net.ReferenceAlignmentId`.

## 2. Accesorios sólidos (WyeSolido.cs, AccesorioPropertySet.cs)

**Creación**
- `WyeSolido.Crear(db,tr,centro,brazos,info,ed)` (192-270). Capa `PDFCAD_WYE_SOLIDO` (42), creada con `AsegurarCapa` (927-941).
- Codo (2 brazos): barrido recto + arco + recto (`ConstruirCodo`, 223). Tee, Wye y Cruz: cilindros por brazo unidos con BoolUnite (225-243).
- Tee, Wye y Cruz son rígidos en Z (`Aplanar`, 288-313): brazos horizontales salvo ramales verticales (≥60°, 321-329). El codo conserva la pendiente.
- Registro solo en memoria: `WyeSolido.Creadas` (Registro con SolidId, Tipo, Centro, Brazos; 152-175). Se limpia en cada IMPORTAR_RED (ImportarRed.cs:66), así que no sirve después del import.

**XDATA** (app `PDFCAD_FITTING`, `GrabarXData` 517-603; regapp en 527-533). Todas son cadenas `ExtendedDataAsciiString` "CLAVE=valor", en este orden:
1. `TIPO=` WYE | TEE | ELBOW | CROSS
2. `ANGULO=` F1
3. `DIAM_PRINCIPAL_IN=` F1
4. `DIAM_RAMAL_IN=` F1
5. `N_PUERTOS=`
6. `LARGO_TOTAL_FT=` F2
7. `COORD_X=` F3
8. `COORD_Y=` F3
9. `COTA_EJE_FT=` F3
10. `RUMBOS_SALIDA=` azimuts separados por ";"
11. `PENDIENTES_PCT=` separados por ";"
12. `MATERIAL=`
13. `RED=`
14. `ORIGEN=PDFCAD_SOLIDO`

Detalles de los valores:
- Los números se formatean con la **cultura del equipo** (pueden salir con coma). El parser de AccesorioPropertySet.cs:176-178 hace `Replace(',', '.')`.
- MATERIAL = `PressurePipe.PartDescription` en junturas (RedesPresionJunturas.cs:59-62, 771); en CROSS es la descripción de la pieza de catálogo (ImportarRed.cs:5174).
- RED = nombre de la red; en CROSS vale "CROSS-CONNECTS" (5175) o la red del codo reemplazado (4888-4896).

**Lectura**
- `WyeSolido.LeerXData(Entity)` (910-925) devuelve `List<string>` "CLAVE=valor" o null.
- Ejemplo de parseo a diccionario: `AccesorioPropertySet.LeerCampos`.
- Filtro rápido de sólidos: `id.ObjectClass.DxfName == "3DSOLID"` (PerfilGrafoPresion.cs).

**Centro del accesorio**
- Sale directamente de la XDATA: COORD_X, COORD_Y, COTA_EJE_FT = `centroPlano` (Aplanar devuelve el centro sin cambiar, 312; se graba en 253 y 566-568). Es el punto de la juntura a cota de **eje**; no hace falta centroide ni GeometricExtents.
- Invert = COTA_EJE_FT − DIAM_PRINCIPAL_IN/24.

**Property Set** `PDFCAD_Accesorio` (AccesorioPropertySet.cs:35-44)
- Campos: Tipo_Accesorio, Angulo_Grados, Diametro_Pulg, Material, Cota_Eje_Pies.
- Aplicado desde la XDATA al crear cada pieza (`AplicarDesdeXData`).

**Conexiones verticales** (ImportarRed.cs:4200-4516)
- Tramo vertical PressurePipe en la red CROSS-CONNECTS.
- Piezas sólidas por `ColocarFittingSolido` (5129-5200): Tee o codo con ramal vertical.
- Caso Wye: `CrearCruceConWye` (4849-4999) con Wye + tubo auxiliar + 2 codos + vertical. `TUBO_AUX_CRUCE_FT` está definido en otro sitio.

## 3. Datos disponibles para etiquetas (verificado con apiref) y trampas

**Pipe** (gravedad y conduit)
- Heredados de `Part`: Name, PartSizeName, PartDescription, PartFamilyName, Material, NetworkId/NetworkName, Position, `AddToProfileView(ObjectId)`, `RemoveFromProfileView`, `GetProfileViewsDisplayingMe()`.
- Propios: StartPoint/EndPoint (**eje**), StartStructureId/EndStructureId, InnerDiameterOrWidth, InnerHeight, OuterDiameterOrWidth, OuterHeight, Slope (ratio), Length2D, Length2DCenterToCenter, Length3D, Length3DCenterToCenter, Length2DToInsideEdge, CoverOfStartPoint.
- `Description` guarda el MATERIAL del DXF (ImportarRed.cs:2035).

**Structure**
- Name (STRUCT_ID), Location, RimElevation, SumpElevation, Height, RimToSumpHeight, InnerDiameterOrWidth, PartSizeName (por Part), `AddToProfileView`.

**PressurePipe**
- Heredados de `PressurePart`: Name, PartDescription (get/set), PartFamilyName, PartType, PartData, ReferenceAlignmentId, ReferenceSurfaceId, ProfileViewPartId, `AddToProfileView`, `RemoveFromAllProfileViews`.
- Propios: StartPoint/EndPoint (**eje**), NominalDiameter, InnerDiameter, OuterDiameter, WallThickness (en **pies**), Slope, Length2DCenterToCenter, Length3DCenterToCenter, StartStation/EndStation/StartOffset/EndOffset (respecto al eje de referencia), MinimumCover/MaximumCover (requieren superficie), StartPartId/EndPartId, StyleId.
- **No tiene PartSizeName.**

**Estilos por red (strings)**
- Network: PipeProfileLabelStyleName, PipeProfileLayerName, StructureProfileLabelStyleName, StructureProfileLayerName.
- PressurePipeNetwork: PipeProfileLabelStyleName, PipeProfileLayerName, FittingProfile*, AppurtenanceProfile*, CrossingPressurePipeProfileLabelStyleName.

**Cómo lo leen CotarTuberias y CuadroBuzones**
- Invert por extremo: `ComandosCotarTuberias.InvertEnNodo` (CotarTuberias.cs:308-314, internal static) = centerline.Z − InnerHeight/2, con respaldo en InnerDiameterOrWidth/2. **Nunca** usa SumpElevation: esa dependencia causó desfases de −0.5/−0.833 ft (297-307).
- **Contradicción**: `PerfilLongitudinalDatos.InvertEnNodo` (PerfilLongitudinalDatos.cs:88-109) sigue usando `Structure.SumpElevation` y dice seguir a CotarTuberias, que hace lo contrario.
- Presión: invert = Z − NominalDiameter/2 (CotarTuberias.cs:235-237).
- Aguas arriba y abajo se deciden por cota, no por Start/End (CotarTuberias.cs:137-139, CuadroBuzones.cs:113-117).
- Estación: `EstacionTexto` con formato "0+81.45" (CotarTuberias.cs:358-370).
- Borde visual del buzón: `PuntoVisualExtremo` (internal static, 320-338).
- CuadroBuzones:
  - Filas de buzón: Name, Rim, Sump y Height (con `try` y respaldo a Rim − Sump) (89-104).
  - Longitud: `Length2DCenterToCenter`, con respaldo `Length2D` (130).
  - Diámetro: `FormatoDiametro` (276-290) usa InnerHeight si la sección no es circular.
  - Orden natural "BZ-2 < BZ-10": `ComparadorNatural` (317-336, privado).

**Otras trampas documentadas**
- "Retrieve attribute failed" en estructuras raras: cada lectura va en su propio try/catch (AlineamientosPerfiles.cs:98-100, PerfilLongitudinalDatos.cs:39-41).
- Un PVI con estación que no avanza deja el Profile inválido y todas sus lecturas lanzan (PerfilUtil.cs:70-84).
- En rectangulares, InnerDiameterOrWidth es el **ancho** (ImportarRed.cs:2350-2360).
- Mover la Position de un PressurePart conectado arrastra los tubos (2681-2684).

## 4. Comandos de perfil actuales y botón del panel

**CREAR_PERFIL_RED** (AlineamientosPerfiles.cs:76-189, clase `ComandosAlineamientos`, no partial). Flujo:
1. GetEntity de Pipe o Structure (solo `CivilDB.Pipe`/`Structure`, gravedad o conduit; no presión) (90-96).
2. Lee `NetworkId` y `net.ReferenceAlignmentId`; aborta si es nulo (114-121).
3. `PerfilLongitudinalDatos.Ordenar` (PerfilLongitudinalDatos.cs:36-86): proyecta con `StationOffset` y ordena buzones por estación, asumiendo una red lineal.
4. Perfil de terreno `"{red}-terreno"` con `Profile.CreateFromSurface(... ProfileStyles[0], ProfileLabelSetStyles[0])` desde `net.ReferenceSurfaceId` (148-161).
5. Rasante `"{red}-rasante"` con `CreateByLayout` y un PVI por buzón (cota = sump), estilo "Standard" por nombre o el primero de la lista (PerfilUtil.cs:52-110).
6. `ProfileView.Create(alignId, pt)`, sobrecarga de 2 argumentos: estilo y band set por defecto (174).
7. `AjustarRango` (PerfilUtil.cs:19-46):
   - Rango vertical = min/max de **todos** los Profile del eje, incluidos los de ejecuciones anteriores, ±5 ft (el comentario dice "m").
   - `LimpiarBandasYEstaciones` (112-136) **borra todas las bandas** y fija la estación al largo del eje.

Limitaciones:
- No añade tubos ni buzones a la vista: no hay `AddToProfileView` en todo el plugin.
- No crea etiquetas ni estilos.
- Las polilíneas no aparecen.
- Cada nueva ejecución duplica los perfiles "-terreno" y "-rasante"; puede fallar por nombre repetido (sin verificar).
- Los prompts ocurren dentro de la transacción.

**CREAR_PERFIL_PRESION** antiguo (estaba en RedesPresionRamales.cs, archivo ya eliminado; hoy
CREAR_PERFIL_PRESION es un alias de CREAR_PERFIL_RED en PerfilComando.cs):
- Elegía la red por número con `ElegirRedId` (eliminado).
- Busca el eje en `PipeRuns[i].AlignmentId` y luego en `pp.ReferenceAlignmentId`; ignora `PressurePipeNetwork.ReferenceAlignmentId`.
- Terreno opcional por prompt: "Terreno-Presion" con nombre fijo y `ProfileStyles[0]`.
- `ProfileView.Create` + `AjustarRango`. Mensaje "±5 m".
- No añade tubos a la vista y no está en el panel.
- Duplicado similar: `CrearRasanteInteractiva` en RedesPresion.cs:1073-1163 (Eje-Presion / Rasante-Presion, PVIs por clic con `FindStationAndElevationAtXY`).

**Botón del panel**
- PanelPipe.xaml:167-180: tarjeta "PERFIL LONGITUDINAL", subtítulo "Rasante, buzones y cotas máx/mín de una red de gravedad", `btnPerfilLongitudinal`.
- PanelPipe.xaml.cs:19 → `Ejecutar("CREAR_PERFIL_RED")` → `SendStringToExecute(cmd+" ", true, false, true)` (22-27).
- Paleta: comando PANEL_REDES (Panel.cs:13-24).

**Utilidades reutilizables**
- Log:
  - `ComandosRedes.Dl(ed, s)`: internal, controlado por `DEBUG_LOGS=false` (ImportarRed.cs:46-47).
  - `Dbg(tag, fields)`: privado de ComandosRedes, escribe el CSV (49-58).
- Capas: no hay helper compartido. Las copias privadas son:
  - CotarTuberias.cs:570 `AsegurarCapa(db,tr,nombre,aci)`
  - RedesPresion.cs:1425 `AsegurarCapa(tr,db,nombre)` y 1437 `PonerCapa`
  - CuadroBuzones.cs:374
  - WyeSolido.cs:927 (hace `using` sobre el LayerTableRecord recién añadido)
  - ImportarRed.cs:5370-5376 (capa con color)
- Estilos:
  - `PerfilUtil.BuscarEstiloPerfilPorNombre` (privado, 95-110).
  - Patrón para crear un estilo por código: `collection.Contains(name) ? collection[name] : base.CopyAsSibling(name) / collection.Add(name)` y luego `GetDisplayStyle*()` → Linetype/Visible (ImportarRed.cs:1112-1159; presión vía `StylesRootPressurePipesExtension.GetPressurePipeStyles`, 1176-1177).
  - Linetype: `AsegurarLinetypeDiscontinuo` (1219-1227).
- Unidades: `ComandosUnidades.ForzarImperial(db, ed, verbose)` (ConfiguracionUnidades.cs:30).
- Reutilizables internal static: `ComandosCotarTuberias.InvertEnNodo` y `PuntoVisualExtremo`.
- `ComandosRedes.TrazaPt` es un struct público (ImportarRed.cs:5736-5741).

**API verificada con apiref** (útil para el rediseño):
- `ProfileView.Create(alignId, pt, name, bandSetId, styleId)` y variantes con `SplitProfileViewCreationOptions`.
- `ProfileView`: StyleId, Bands (ProfileViewBandSet), `FindXYAtStationAndElevation`, ElevationRangeMode, StationRangeMode.
- `StylesRoot`: ProfileViewStyles, ProfileViewBandSetStyles, BandStyles, PipeStyles, StructureStyles, ProfileStyles.
- `LabelStylesRoot`: PipeLabelStyles, StructureLabelStyles, ProfileLabelStyles, ProfileViewLabelStyles.
- `Profile.CreateByLayout` y `CreateFromSurface` con ObjectIds.

## 5. Convenciones del código

- **Namespace**: `Civil3DBasico` (el RootNamespace del csproj es `proyecto1`).
  - Clases de comandos: `public class Comandos*` con `[CommandMethod("MAYUSCULAS")] public void X()`. No hay `CommandClass`: AutoCAD escanea el ensamblado. `ExtensionApp.cs` registra `IExtensionApplication` (assembly attribute, línea 10).
  - Clases partial: `ComandosRedes` (ImportarRed, RedesTuberia, ElementosCurvos) y `ComandosPresion` (RedesPresion, RedesPresionJunturas).
  - Helpers como `internal static class`: PerfilUtil, PerfilLongitudinalDatos, WyeSolido, AccesorioPropertySet.
- **Usings**: `using CivilDB = Autodesk.Civil.DatabaseServices; using PresStyles/PartsStyles = ...Styles; using Exception = System.Exception;`. ImplicitUsings y Nullable desactivados.
- **Transacciones**:
  - Patrón: `using (Transaction tr = db.TransactionManager.StartTransaction()) { try { ...; tr.Commit(); ed.WriteMessage("\n✓ ..."); } catch (Exception ex) { ed.WriteMessage($"\nError: {ex.Message}"); tr.Abort(); } }`.
  - Cada lectura frágil va en su propio try/catch.
  - `LockDocument`: no se usa; los comandos se lanzan desde la paleta con SendStringToExecute.
- **Mensajes**: en español, con prefijo `\n` y marcas `✓ / ⚠ / ✗ / ·`. Tags de depuración `[TAG]` solo a través de `Dl`.
- **Tamaño de archivos**: la guía del proyecto pide menos de 500 líneas. Los del perfil cumplen (191/138/124); ImportarRed tiene 6275, RedesPresion 314, RedesTuberia 1168.
- **Build**:
  - net8.0-windows x64, UseWPF.
  - Referencias con Private=false a `C:/Program Files/Autodesk/AutoCAD 2025/`: accoremgd, acdbmgd, acmgd, ACA/AecBaseMgd, C3D/AeccDbMgd, C3D/AeccPressurePipesMgd, ACA/AecPropDataMgd (proyecto1.csproj:28-57).
  - `dotnet build -c Release`; línea base según CLAUDE.md: 0 errores, 4 warnings.

**Comentarios desactualizados** (conviene corregirlos al tocar estos archivos):
- ImportarRed.cs:592 (conduit), 2005 (estructuras en conduit), 2147-2150 (eje en conduit).
- PerfilUtil.cs:11: dice "m" cuando las unidades son pies.