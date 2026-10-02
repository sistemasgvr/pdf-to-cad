**Referencia de la API de estilos, Civil 3D 2025 (AeccDbMgd / AeccPressurePipesMgd / acdbmgd)**

Cada firma de abajo sale de la herramienta de reflexión. Además, casi todo lo que aparece se compiló de verdad en `C:/Users/User/AppData/Local/Temp/claude/D--GVR-Proyectos-DEV-EEUU-pdf-to-cad/556754cb-8a11-4e39-b999-dbbf14d3d9b9/scratchpad/stylecheck/Check.cs`: 0 errores y ningún aviso de miembro obsoleto (CS0618). Quedan 3 avisos MSB3277 de conflicto de versiones, que no afectan. Lo que no he podido verificar está marcado **[NO VERIFICABLE]**.

La herramienta original no muestra los parámetros de los indexers ni los miembros heredados. Hice una propia: `.../scratchpad/apiref_estilos/out/apiref_estilos.exe "<regexTipo>" "<regexMiembro>" [--all]`. Muestra los parámetros de los indexers, los miembros heredados con `--all`, marca `[OBSOLETE]` e incluye acdbmgd. Ojo: la carpeta `scratchpad/apiref2` la sobrescribió otro agente, no la uséis.

## 1. Colecciones de estilos

`CivilDocument.Styles` → `StylesRoot` (solo `{get;}`). Propiedades de `StylesRoot`:
- `ProfileViewStyleCollection ProfileViewStyles {get;}`
- `ProfileStyleCollection ProfileStyles {get;}`
- `PipeStyleCollection PipeStyles {get;}`
- `StructureStyleCollection StructureStyles {get;}`
- `MarkerStyleCollection MarkerStyles {get;}`
- `BandStylesRoot BandStyles {get;}`
- `ProfileViewBandSetStyleCollection ProfileViewBandSetStyles {get;}`
- `LabelStylesRoot LabelStyles {get;}`
- `LabelSetStylesRoot LabelSetStyles {get;}`

Las colecciones de presión **no** son propiedades de `StylesRoot`. Salen de métodos de extensión estáticos (AeccPressurePipesMgd, espacio de nombres `...DatabaseServices.Styles`) en `StylesRootPressurePipesExtension`:
- `static PressurePipeStyleCollection GetPressurePipeStyles(StylesRoot)`
- `GetPressureFittingStyles(StylesRoot)`
- `GetPressureAppurtenanceStyles(StylesRoot)`
- `GetPressurePartLists(StylesRoot)`

Estilos de banda, en `BandStylesRoot` (todas son `BandStyleCollection {get;}`):
- `ProfileViewPipeNetworkBandStyles`
- `ProfileViewProfileDataBandStyles`
- `ProfileViewHorizontalGeometryBandStyles`
- `ProfileViewVerticalGeometryBandStyles`
- `ProfileViewSectionalDataBandStyles`
- `ProfileViewSuperElevationBandStyles`
- Banda de presión: `BandStylesRootPressurePipesExtension.GetProfileViewPressureNetworkBandStyles(BandStylesRoot)`.

Operaciones comunes. `StyleCollectionBase : TreeNodeCollectionBase`, y todas las colecciones de arriba heredan de ella:
- Agregar: `ObjectId Add(String name)`
- Comprobar si existe: `Boolean Contains(String name)` / `Contains(ObjectId)`
- Obtener: `prop ObjectId Item[String styleName] {get;}` / `Item[Int32 index] {get;}`
- También: `Int32 Count {get;}`, `GetEnumerator()` (de ObjectId), `ToObjectIds()`, `Remove(String)`, `Remove(Int32)`. `Remove(StyleBase)` está **[OBSOLETE]**.
- Copiar: `StyleBase.CopyAsSibling(String styleName) → ObjectId`. Además `StyleBase.Name {get;set;}`.
- Patrón que compila: `col.Contains(n) ? col[n] : col.Add(n)`. Está comprobado que el índice por nombre existe.

Recomendación:
- Hacer `CopyAsSibling` de un estilo de fábrica (`col[0]`) para heredar códigos de campo válidos. Usar `Add` como alternativa.
- Las plantillas instaladas son ESPAÑOLAS (`C3D 2025\esp`), así que los estilos de fábrica pueden no llamarse "Standard". No buscarlos por nombre en inglés.

## 2. ProfileViewStyle y tipos relacionados (espacio de nombres `Autodesk.Civil.DatabaseServices.Styles`)

**`ProfileViewStyle : StyleBase`**
- `AxisStyle LeftAxis`, `RightAxis`, `TopAxis`, `BottomAxis {get;}`
- `GridStyle GridStyle {get;}`
- `GraphStyle GraphStyle {get;}`
- `DisplayStyle GetDisplayStylePlan(ProfileViewDisplayStyleType)`. **Solo existe la versión Plan**: no hay Profile ni Model.
- Valores de `ProfileViewDisplayStyleType`:
  - `GraphTitle`
  - `Left/Right/Top/BottomAxis`
  - `…AxisTitle`
  - `…AxisAnnotationMajor/Minor`
  - `…AxisTicksMajor/Minor`
  - `GridHorizontalMajor/Minor`, `GridVerticalMajor/Minor`
  - `GridAtHGP`
  - `Top/BottomAxisAnnotationHGP`, `Top/BottomAxisTicksHGP`
  - `GridAtSampleLineStations`
  - `ProfileHatch`

**`AxisStyle`**
- `AxisTickStyle MajorTickStyle`, `MinorTickStyle`, `HorizontalGeometryTickStyle {get;}`
- `AxisTitleStyle TitleStyle {get;}`
- `Boolean ShowTickAndLabel {get;set;}`. Sustituye a `AxisTickStyle.TickAndLabelStartElevation`, que está [OBSOLETE].

**`AxisTickStyle`** (todo `{get;set;}`):
- `Double Interval`, `Size`, `TextHeight`, `OffsetX`, `OffsetY`, `Rotation`
- `String LabelText`, `TextStyle`
- `AxisTickJustificationType Justification` {TopOrLeft, Center, BottomOrRight}

**`AxisTitleStyle`** (todo `{get;set;}`):
- `String Text`, `TextStyle`
- `Double TextHeight`, `Rotation`, `OffsetX`, `OffsetY`
- `AxisTitleLocationType Location` {BottomOrRight, Center, TopOrLeft}

**`GridStyle`**
- `Double GridPaddingAbove/Bottom/Left/Right`, `AxisOffsetAbove/Bottom/Left/Right {get;set;}`
- `GridOptions HorizontalGridOptions`, `VerticalGridOptions {get;}`
- `GridOptions`: `Boolean UseClipGrid`, `ClipToHighestProfile`, `OmitGridInPaddingAreas {get;set;}`
- **No existen intervalos de rejilla en `GridStyle`.** Las líneas de rejilla siguen `AxisTickStyle.Interval` de los ejes:
  - Rejilla vertical = `Bottom/TopAxis.Major/MinorTickStyle.Interval` (pies de estación).
  - Rejilla horizontal = `Left/RightAxis…Interval` (pies de cota).
  - Visibilidad y color de la rejilla: `GetDisplayStylePlan(GridVerticalMajor…)`.
- Recorte por vista: `ProfileView.GraphOverrides.ClipGridAt` (`String {get;set;}`, es el nombre del perfil; semántica inferida).

**`GraphStyle`**
- `Double VerticalExaggeration {get;set;}`, `VerticalScale {get;set;}`, `CurrentHorizontalScale {get;}`
- `GraphDirectionType Direction {get;set;}` {LeftToRight, RightToLeft}
- `GraphTitleStyle TitleStyle {get;}`

**`GraphTitleStyle`** (todo `{get;set;}`):
- `String Text`, `TextStyle`
- `Double TextHeight`, `OffsetX`, `OffsetY`, `BorderGap`
- `Boolean Border`
- `GraphTitleLocationType Location` {Top, Bottom, Left, Right}
- `GraphTitleJustificationType Justification` {TopOrLeft, MiddleOrCenter, BottomOrRight}

**`DisplayStyle`** (común a todos los estilos, todo `{get;set;}`):
- `Boolean Visible`
- `Color Color`
- `String Layer`
- `String Linetype`
- `Double LinetypeScale`
- `LineWeight Lineweight`
- `String PlotStyle`

**`HatchDisplayStyle`**:
- `String Pattern`
- `HatchType HatchType` {UserDefined, PreDefined, CustomDefined, SolidFill}
- `Double Angle`, `ScaleFactor`, `Spacing`, `UOffset`, `VOffset`
- `Boolean IsDoubleHatch`, `UseAngleOfObject`

**Formato de estación tipo 0+85 [NO VERIFICABLE].** Se escribe en `BottomAxis.MajorTickStyle.LabelText` con códigos de campo. El patrón habitual es `<[Station Value(Uft|FS|P0|RN|AP|Sn|TP|B2|EN|W0|OF)]>`. No lo encontré en las DLL ni en los recursos, así que conviene leer y registrar en el log `LabelText` del estilo de fábrica en tiempo de ejecución y reutilizarlo (con `CopyAsSibling` ya viene heredado). Los títulos de texto plano ("STATION", "ELEVATION (FT)") son seguros.

**Rotación [NO VERIFICABLE]:** probablemente en radianes, según la convención de la API. El título del eje izquierdo sería π/2. Confirmarlo leyendo el estilo de fábrica.

## 3. ProfileStyle

- `DisplayStyle GetDisplayStyleProfile(ProfileDisplayStyleProfileType)`. **Solo existe la versión Profile.**
- Enum: `Line`, `Curve`, `Arrow`, `LineExtension`, `SymmetricalParabola`, `AsymmetricalParabola`, `ParabolicCurveExtension`, `WarningSymbol`.
- Terreno existente discontinuo: `Linetype`, `LinetypeScale` y `Color` en `Line` y `Curve`, y `Visible=false` en `Arrow`/`WarningSymbol`. Compila.
- Marcadores, todos `ObjectId {get;set;}`: `BeginPointMarkerStyle`, `EndPointMarkerStyle`, `HighPointMarkerStyle`, `LowPointMarkerStyle`, `VIntersectionPointMarkerStyle`, …
- Obsoletos: `Chain3DDisplayStyleModel` → usar `GetChain3DDisplayStyleModel()`; `ProfileMarkerDisplayStyleSection` → usar `GetProfileMarkerDisplayStyleSection()`.
- Se asigna con `Profile.StyleId {get;set;}`. Por vista: `ProfileView.GraphOverrides` (`ProfileOverride`).
- Creación del perfil: `Profile.CreateFromSurface(String, ObjectId alignmentId, ObjectId surfaceId, ObjectId layerId, ObjectId styleId, ObjectId labelSetId[, Double offset, Double sampleStart, Double sampleEnd])` y `Profile.CreateByLayout(String, ObjectId alignmentId, ObjectId layerId, ObjectId styleId, ObjectId labelSetId)`.

## 4. PipeStyle, PressurePipeStyle y StructureStyle

**`PipeStyle : StyleBase`**
- `GetDisplayStyleProfile(PipeDisplayStyleProfileType)`. Enum: `Centerline`, `InsideWalls`, `OutsideWalls`, `EndLine`, `Hatch`, `CrossingPipeInsideWall`, `CrossingPipeOutsideWall`, `CrossingPipeHatch`, `HydraulicGradeLine`, `EnergyGradeLine`.
- `GetHatchStyleProfile(PipeHatchStyleProfileType {Hatch, CrossingPipeHatch})`
- También `GetDisplayStylePlan`, `GetDisplayStyleModel()`, `GetDisplayStyleSection`.
- `PipeStyleProfileOption ProfileOption {get;}`. Hereda de `PipeStyleOptionBase`; todo `{get;set;}`:
  - `PipeHatchType HatchOptions` {HatchToInnerWalls, HatchToOuterWalls, HatchWallsOnly}
  - `PipeHatchType CrossingHatch`
  - `PipeWallSizeType WallSizeType` {UsePartDimensions, UserDefinedWallSize}
  - `PipeEndSizeType EndSizeType` {DrawToInnerWall, DrawToOuterWall, UserDefinedEndSize}
  - `InnerDiameter`, `OuterDiameter`, `EndLineSize` (+ `…Percent`)
  - `PipeUserDefinedType WallSizeOptions`, `EndSizeOptions`
  - `Boolean AlignHatchToPipe`, `PipeToPipeEndCleanup`

**`PressurePipeStyle`** (AeccPressurePipesMgd)
- `GetDisplayStyleProfile(PressurePipeDisplayStyleProfileType)`. Enum: `Centerline`, `InsideWalls`, `OutsideWalls`, `EndLine`, `Hatch`, `CrossingPipeInsideWall`, `CrossingPipeOutsideWall`, `CrossingPipeHatch`.
- `GetHatchStyleProfile(PressurePipeHatchStyleProfileType {Hatch, CrossingPipeHatch})`
- `PressurePipeStyleProfileOption ProfileOption {get;}`:
  - `PressurePipeHatchType HatchOptions`, `CrossingHatch`
  - `PressurePipeWallSizeType WallSizeType`
  - `PressurePipeEndSizeType EndSizeType`
  - `InnerDiameter`, `OuterDiameter`, `EndLineSize`
  - `AlignHatchToPipe`

**`StructureStyle`**
- `GetDisplayStyleProfile(StructureDisplayStyleProfileType {Structure, StructureHatch, StructurePipeOutlines})`
- `GetHatchStyleProfile()`
- `ProfileOption` (`StructureStyleOptionBase`):
  - `StructureViewType ViewOptions` {DisplayAsSolid, DisplayAsBoundary, DisplayAsBlock}
  - `Boolean MaskConnectedObjects`
  - `StructureSizeOptionsType SizeType`
  - `XSize`, `YSize`, `SymbolBlockName`
  - `StructureInsertionLocation BlockInsertLocation` {Rim, Sump}

**Asignación.** El estilo del modelo vale para planta y perfil a la vez: `Pipe.StyleId`, `Structure.StyleId`, `PressurePipe.StyleId`/`StyleName`, `PressureFitting.StyleId` (todos `{get;set;}`).

Añadir a la vista: `Part.AddToProfileView(ObjectId)` y `PressurePart.AddToProfileView(ObjectId)`. Además: `RemoveFromProfileView`, `GetProfileViewsDisplayingMe()`, `ProfileViewPartId {get;}`.

**Override por vista (camino recomendado):**
- `ProfileView.PipeOverrides` (`PipeOverrideCollection`), `StructureOverrides`, `GraphOverrides` (perfiles).
- Presión: `ProfileViewPressurePipesExtension.GetPressurePipeOverrides(ProfileView)`, `GetPressureFittingOverrides`, `GetPressureAppurtenanceOverrides`.
- Cada elemento (`GraphOverride`) tiene `ObjectId OverrideStyleId {get;set;}`, `Boolean UseOverrideStyle {get;set;}` y `Boolean Draw {get;set;}`. Identificadores de solo lectura: `PipeId`, `StructId`, `PressurePartId`, `ProfileId`.
- Las colecciones tienen `ClipGridAt` y `SplitAt` (`String {get;set;}`).

`ProfileViewPart` sí existe y hereda `StyleId {get;set;}` de la `Entity` de Civil, pero **no está documentado qué hace asignarlo**: usar los overrides.

## 5. ProfileView

Propiedades escribibles:
- Heredadas: `Name`, `Description`, `StyleId`, `StyleName` (de la `Entity` de Civil) y `Point3d Location {get;set;}` (de `Graph`).
- `ElevationRangeMode` (`ElevationRangeType` {Automatic, UserSpecified}), `ElevationMin`, `ElevationMax`.
- `StationRangeMode` (`StationRangeType` {Automatic, UserSpecified}), `StationStart`, `StationEnd`.
- `SplitProfileView`, `SplitHeight`, `SplitDatumRounding`, `SplitStationMode`, `SplitStationRounding`.

Solo lectura:
- `Bands` (`ProfileViewBandSet`), `PipeOverrides`, `StructureOverrides`, `GraphOverrides`, `HatchAreas`, `AlignmentId`.

Métodos:
- `FindXYAtStationAndElevation(Double, Double, ref Double x, ref Double y)` y `FindStationAndElevationAtXY(...)`.
- `GetProfileViewLabelIds()` (`GetLabelIds()` está [OBSOLETE]).
- `GetAvailablePipeProfileLabelIds()`, `GetAvailableStructureProfileLabelIds()`, `GetAvailableSpanningPipeProfileLabelIds()`, `GetPressureNetworkPartsInGraph()`.

Sobrecarga de `Create` con estilo y juego de bandas (compila): `static ObjectId Create(ObjectId alignmentId, Point3d insertPosition, String profileViewName, ObjectId profileViewBandSetId, ObjectId profileViewStyleId[, SplitProfileViewCreationOptions])`. Otras: `Create(alignId, pt)`, variantes apiladas y `CreateMultiple(...)` con `profileViewStyleId`. Las dos sobrecargas que toman `CivilDocument` como primer argumento están [OBSOLETE].

Bandas:
- `ProfileViewBandSetStyle.GetBottomBandSetItems()` / `SetBottomBandSetItems(ProfileViewBandSetItemCollection)` (también Top).
- Colección nueva: `new ProfileViewBandSetItemCollection(BandLocationType, ObjectId profileViewBandSetStyleId)`. El constructor de un solo argumento es [OBSOLETE] **y da error de compilación CS0619**.
- `Add(Database, BandType, String)` está [OBSOLETE]. Usar `BandSetItemCollection.Add(ObjectId)` con `BandStyle.GetBandStyleId(Database, BandType, String)`, o directamente el id de la colección de estilos.
- En la vista: `pv.Bands.GetBottomBandItems()`, modificar cada `ProfileViewBandItem` y luego `SetBottomBandItems(...)`. Campos: `Profile1Id`, `Profile2Id`, `DataSourceId`, `Alignment2Id` (del ítem), `Gap`, `ShowLabels`, `MajorInterval`, `MinorInterval`, `LabelAtStartStation`/`EndStation`, `BandStyleId`.
- `GraphBandSet.ImportBandSetStyle(ObjectId)`, `MatchIncrementToGridIntervals {get;set;}`.
- `ProfileViewBandItemCollection(ObjectId pvId, BandLocationType)` sirve con `.Add(ObjectId)`; su `Add(BandType, String)` está [OBSOLETE].
- `BandType`: `ProfileData`, `PipeNetwork`, `PressureNetwork`, …

`BandStyle` (todo `{get;set;}`):
- `BandHeight`, `TextHeight`, `Text`, `TextStyle`, `TextBoxWidth`, `OffsetFromBand`, `WeedingFactor`
- `BandTitleBoxPosition TextBoxPosition` {LeftOfBand, RightOfBand}
- `BandTitleTextLocation TextLocation`

Subclases:
- `PipeNetworkBandStyle`: `GetDisplayStylePlan(PipeNetworkDisplayStyleType)`; `PipeLabelStyleId`/`StructureLabelStyleId` son `{get;}`; `PipeTickStyle`, `StructureTickStyle`.
- `ProfileDataBandStyle`: `MajorIncrementLabelStyleId {get;}`, …
- `PressureNetworkBandStyle`: `PressurePipeLabelStyleId {get;}`, …
- Los ids de estilo de etiqueta de las bandas son de solo lectura: se editan abriendo ese `LabelStyle`.

## 6. Alturas de texto y escala

Propiedades: `AxisTickStyle.TextHeight`, `.Size`, `.OffsetX/Y`; `AxisTitleStyle.TextHeight`; `GraphTitleStyle.TextHeight`, `.BorderGap`; `GridStyle.AxisOffset*`; `BandStyle.BandHeight`, `.TextHeight`, `.TextBoxWidth`. En etiquetas: `LabelStyleTextComponent.Text.Height` (`PropertyDouble`, se escribe con `.Value {get;set;}`), accesible vía `LabelStyle.GetComponents(LabelStyleComponentType.Text)`. **Ningún nombre indica la unidad.**

Lo que sí está verificado para convertir:
- `CivilDocument.Settings.DrawingSettings.UnitZoneSettings` → `Double DrawingScale {get;set;}`, `DrawingUnitType DrawingUnits` {Feet, Meters}.
- `Database.Cannoscale` → `AnnotationScale`: `Scale`, `PaperUnits`, `DrawingUnits`.

**[NO VERIFICABLE]** Según el comportamiento conocido de las etiquetas, el valor está en unidades de dibujo de papel: 0.1" se guarda como 0.1/12 = 0.008333 en un dibujo en pies. Civil lo multiplica luego por la escala de anotación. Seguramente vale lo mismo para `GraphStyle` y `BandStyle`.

Hay que calibrarlo en tiempo de ejecución: registrar `TextHeight` del eje inferior de un estilo de fábrica (se espera ≈0.00833) y usar `Pl(in) = in/12`. `GridPadding*` son número de intervalos mayores de rejilla (según la interfaz) y no son medidas de ploteo. Los `Interval` de los ejes van en pies de modelo. La exageración vertical no deforma los textos.

## 7. Tipos de línea

Firmas (acdbmgd):
- `Database.LoadLineTypeFile(String lineTypeName, String filename)` (lanza excepción si ya existe, así que comprobar antes).
- `Database.LinetypeTableId {get;}`
- `SymbolTable.Has(String)`
- `HostApplicationServices.Current.FindFile(String, Database, FindFileHint)`
- `Database.Ltscale`, `Psltscale`, `Celtscale {get;set;}`

Se asignan con `DisplayStyle.Linetype = nombre` y `.LinetypeScale`.

**Hallazgo importante:** el C3D 2025 instalado es la versión española. `%APPDATA%\Autodesk\C3D 2025\esp\Support\acad.lin` **no contiene DASHED ni HIDDEN**. Sus equivalentes son:
- `TRAZOS` = patrón `.5,-.25`; también `TRAZOS2` y `TRAZOSX2`.
- `LÍNEAS_OCULTAS` = patrón `.25,-.125`. El nombre lleva una Í en Latin-1.
- `CENTRO`, `TRAZO_Y_PUNTO`, `PUNTOS`.
- `ACAD_ISO02W100` está en ambos idiomas, pero su patrón es `12,-3` (pensado en mm): en pies necesita un `LinetypeScale` pequeño.

Por eso `AsegurarLinetypeDiscontinuo` (ImportarRed.cs:1219) cae a "Continuous" en esta instalación. Orden recomendado: `DASHED` → `TRAZOS` → `HIDDEN` → `LÍNEAS_OCULTAS` → `ACAD_ISO02W100`. Para cada uno: si `lt.Has` lo tiene, usarlo; si no, `try LoadLineTypeFile(n, "acad.lin")` y volver a comprobar con `Has`.

## Otros obsoletos que evitar

- `MarkerStyle.MarkerDisplayStyleProfile/Section/Model/Plan` → usar los métodos `Get…()`.
- `LabelStylesPressurePipeRoot.LabelStyles` → usar `PlanProfileLabelStyles`.
- `LabelStylesProfileRoot.GradeBreadLabelStyles` → usar `GradeBreakLabelStyles`.

Raíces de estilos de etiqueta (verificadas):
- `LabelStyles.PipeLabelStyles.PlanProfileLabelStyles`, `.CrossProfileLabelStyles`
- `StructureLabelStyles.LabelStyles`
- `ProfileViewLabelStyles.StationElevationLabelStyles`, `.DepthLabelStyles`
- Presión: `LabelStylesRootPressurePipesExtension.GetPressurePipeLabelStyles(LabelStylesRoot)` → `.PlanProfileLabelStyles` / `.CrossingProfileLabelStyles`
- Todas son `LabelStyleCollection.Add(String)`.