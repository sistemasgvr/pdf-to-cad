API de etiquetas en vistas de perfil de Civil 3D 2025, verificada por reflexión contra AeccDbMgd.dll, AeccPressurePipesMgd.dll y acdbmgd.dll. Solo está comprobado que los miembros existen con esa firma. Su comportamiento en ejecución no se ha probado porque aquí no hay Civil 3D, y lo marco como **[sin probar]**.

**Herramienta usada.** `apiref.exe` no muestra tipos anidados, parámetros de indexer ni eventos, y el acceso a propiedades de estilo pasa justo por tipos anidados. Compilé una variante en `C:/Users/User/AppData/Local/Temp/claude/D--GVR-Proyectos-DEV-EEUU-pdf-to-cad/556754cb-8a11-4e39-b999-dbbf14d3d9b9/scratchpad/apiref3/out/apiref3.exe`. Usa los mismos argumentos más `--all` para ver miembros heredados, e imprime tipos anidados (`Tipo+Anidado`), indexers `Item[String name]`, eventos y el valor numérico de los enums. Todo lo de abajo sale de ahí.

---

## 1. Colecciones de estilos de etiqueta

`CivilDocument.Styles` (StylesRoot) → `.LabelStyles` (LabelStylesRoot):

| Qué | Ruta exacta | Tipo |
|---|---|---|
| Station/Elevation (vista de perfil) | `LabelStyles.ProfileViewLabelStyles.StationElevationLabelStyles` | LabelStyleCollection |
| Depth (vista de perfil) | `LabelStyles.ProfileViewLabelStyles.DepthLabelStyles` | LabelStyleCollection |
| Tubería de gravedad en planta **y** perfil (una sola colección) | `LabelStyles.PipeLabelStyles.PlanProfileLabelStyles` | LabelStyleCollection |
| Tubería de gravedad que cruza, en perfil | `LabelStyles.PipeLabelStyles.CrossProfileLabelStyles` | LabelStyleCollection |
| (tubería en sección) | `LabelStyles.PipeLabelStyles.CrossSectionLabelStyles` | |
| Estructura (planta y perfil, una sola colección) | `LabelStyles.StructureLabelStyles.LabelStyles` | LabelStyleCollection |
| Tubería a presión | `LabelStylesRootPressurePipesExtension.GetPressurePipeLabelStyles(civDoc.Styles.LabelStyles)` → `.PlanProfileLabelStyles` / `.CrossingProfileLabelStyles` / `.CrossingSectionLabelStyles` / `.LabelStyles` | LabelStylesPressurePipeRoot |
| Accesorio a presión (fitting) | `LabelStylesRootPressurePipesExtension.GetPressureFittingLabelStyles(root).LabelStyles` | |
| Appurtenance a presión | `LabelStylesRootPressurePipesExtension.GetPressureAppurtenanceLabelStyles(root).LabelStyles` | |

`LabelStylesRootPressurePipesExtension` está en el namespace `Autodesk.Civil.DatabaseServices.Styles`, en AeccPressurePipesMgd.dll. Es estática, así que se llama como `LabelStylesRootPressurePipesExtension.GetPressurePipeLabelStyles(LabelStylesRoot stylesRoot)`.

- `LabelStylesPressurePipeRoot` tiene a la vez `LabelStyles` y `PlanProfileLabelStyles`. No sé si son la misma colección **[sin probar]**. Usar `PlanProfileLabelStyles` y comparar `Count`/ids en ejecución.
- Colecciones útiles de otros objetos:
  - `LabelStylesProfileRoot`: CurveLabelStyles, LineLabelStyles, GradeBreakLabelStyles, MajorStationLabelStyles, MinorStationLabelStyles, HorizontalGeometryPointLabelStyles.
  - `LabelStylesRoot.GeneralNoteLabelStyles`, `LabelStylesRoot.ProjectionLabelStyles`.
- Estilo por defecto que usa la red al crear etiquetas (todos `{get;set;}`):
  - `Network`: `PipeProfileLabelStyleId`, `StructureProfileLabelStyleId`.
  - `PressurePipeNetwork`: `PipeProfileLabelStyleId`, `FittingProfileLabelStyleId`, `AppurtenanceProfileLabelStyleId`, `CrossingPressurePipeProfileLabelStyleId`.

**Agregar, buscar y quitar estilos en una colección.** Cadena de herencia: `LabelStyleCollection : StyleCollectionBase : TreeNodeCollectionBase`.
```
ObjectId Add(String name)                   // LabelStyleCollection / StyleCollectionBase
Boolean  Contains(String name) / Contains(ObjectId item)   // TreeNodeCollectionBase
prop ObjectId Item[String styleName] {get;} / Item[Int32 index] {get;}  // col["x"]: lanza excepción si no existe (las muestras de Autodesk usan try/catch)
Void Remove(String styleName) / Remove(Int32 index) / Remove(StyleBase style)
prop Int32 Count; ObjectIdCollection ToObjectIds(); GetEnumerator()
prop LabelStyleDefault DefaultLabelStyle {get;}   // valores por defecto de la colección
prop ExpressionCollection Expressions {get;}      // Add(String name, String description, String expression)
```
Alternativa: `StyleBase.CopyAsSibling(String styleName)` devuelve un ObjectId con una copia de un estilo existente, por ejemplo el del template. Esa copia **hereda campos de texto que ya funcionan en el idioma instalado** (ver punto 4).

No existe `TryGet`: usar `Contains` y luego el indexer.

## 2. LabelStyle y sus componentes

**`Autodesk.Civil.DatabaseServices.Styles.LabelStyle : StyleBase`**
```
ObjectId AddComponent(String name, LabelStyleComponentType type)
ObjectId AddReferenceTextComponent(String name, ReferenceTextComponentSelectedType selectedType)
ObjectId AddTextForEachComponent(String name, TextForEachComponentSelectedType selectedType)
ObjectIdCollection GetComponents(LabelStyleComponentType type)
Int32 GetComponentsCount() / GetComponentsCount(LabelStyleComponentType type)
Boolean IsSupportedComponent(LabelStyleComponentType type)
Void RemoveComponent(String name)
ObjectId[] GetComponentsDrawOrder(); Void SetComponentsDrawOrder(ObjectId[] componentIds); Void SwitchComponentsDrawOrder(Int32 index1, Int32 index2)
prop LabelStyleBase Properties {get;}
ObjectId AddChild(String labelStyleName); prop Int32 ChildrenCount; prop ObjectId Item[Int32 index]/Item[String labelStyleName] (estilos hijos); ParentLabelStyleId; RemoveChild(..); RemoveAllDescendants()
```
`StyleBase` aporta: `String Name {get;set;}`, `CopyAsSibling(String)`, `ExportTo(...)`, `CreateBy`, `DateCreated`, `DateModified`, `ModifiedBy`. **No tiene `Description`.**

**Enums de componentes y del estilo:**
- `LabelStyleComponentType`: Text, Line, Block, Tick, ReferenceText, DirectionArrow, TextForEach.
- `TextForEachComponentSelectedType`: Curve, Spiral, CurveOrSpiral, **StructureAllPipes, StructureInFlowPipes, StructureOutFlowPipes**, IntersectionAllAlignment. Sirve para listar las cotas de cada tubería conectada en la etiqueta de estructura.
- `ReferenceTextComponentSelectedType`: Alignment, CogoPoint, Parcel, Profile, Surface.

**Propiedades generales del estilo** (`ls.Properties`, tipo `LabelStyleBase`). Cada propiedad es un wrapper con `.Value {get;set;}`, además de `Locked` y `Overridden {get;set;}` y `IsOverridable {get;}`.
- `Properties.Label` (`LabelStyleBase+BaseLabel`): `PropertyBoolean Visibility`, `PropertyLayer Layer`, `PropertyString TextStyle`, `PropertyEnum<LabelDisplayModeType> DisplayMode` (Label, Tag).
- `Properties.Behavior` (`+BaseBehavior`): `PropertyEnum<OrientationReferenceType> OrientationReference` (Object, View, WorldCoordinateSystem), `PropertyEnum<LabelInsertionType> InsertOption` (None, Top, Bottom), `PropertyEnum<LabelInsideCurveType> InsideCurveOption`.
- `Properties.PlanReadability` (`+BasePlanReadability`): `PropertyBoolean PlanReadable`, `PropertyDouble PlanReadableBias`, `PropertyBoolean FlipAnchorsWithText`.
- `Properties.Leader` (`+BaseLeader`): `PropertyBoolean Visibility`, `PropertyString ArrowheadStyle`, `PropertyDouble ArrowheadSize`, `PropertyColor Color`, `PropertyLinetype Linetype`, `PropertyEnum<LineWeight> Lineweight`, `PropertyEnum<LeaderShapeType> Shape` (Straight, Spline).
- `Properties.DraggedStateComponents` (`+BaseDraggedStateComponents`):
  - `PropertyEnum<LabelContentDisplayType> DisplayType` (Composed, StackedText)
  - `PropertyEnum<LeaderAttachmentType> LeaderAttachment` (LeaderTopOfTopLine, LeaderMiddleOfTopLine, LeaderMiddle, LeaderMiddleOfBottomLine, LeaderBottomOfBottomLine)
  - `PropertyBoolean LeaderJustification`, `PropertyBoolean BorderVisibility`, `PropertyEnum<TextBorderType> BorderType`, `PropertyDouble Gap`, `PropertyDouble MaxTextWidth`, `PropertyDouble TextHeight`, `PropertyBoolean UseBackgroundMask`, `PropertyColor Color`, `PropertyLinetype Linetype`, `PropertyEnum<LineWeight> Lineweight`

Los valores por defecto de una colección están en `col.DefaultLabelStyle` (LabelStyleDefault), con `.Components.TextHeight`, `.Label.TextStyle`, `.Leader.*`, `.DraggedStateComponents.*`, etc.

**`LabelStyleTextComponent : LabelStyleComponent : StyleBase`**
- `.Text` (`LabelStyleTextComponent+StyleText`):
  - `PropertyString Contents`
  - `PropertyDouble Height`
  - `PropertyDouble Angle` (es PropertyDouble, no PropertyAngle; en la muestra de Autodesk los ángulos de línea van en radianes)
  - `PropertyEnum<LabelTextAttachmentType> Attachment` (TopLeft … BottomRight, 9 valores)
  - `PropertyDouble XOffset`, `PropertyDouble YOffset`, `PropertyDouble MaxWidth`
  - `PropertyColor Color`, `PropertyEnum<LineWeight> Lineweight`
- `.General` (`+StyleGeneral`):
  - `String Name {get;set;}`
  - `PropertyBoolean Visible`
  - `PropertyString AnchorComponent`: nombre de otro componente o el feature **[sin probar: probablemente la cadena "<Feature>", quizá traducida]**
  - `PropertyAnchorPoint AnchorLocation`: `.Value` es de tipo `AnchorPointType`
  - `PropertyEnum<AnchorLocationType> AnchorPoint`: el mismo concepto con un enum más corto
  - `PropertyBoolean SpanOutsideSegments`
  - `PropertyEnum<LayoutModeType> UsedIn` (Label, Tag, LabelTag)
- `.Border` (`+StyleBorder`): `PropertyBoolean Visible`, `PropertyEnum<TextBorderType> BorderType` (Rectangular, RoundedRectangular, Circular), `PropertyDouble Gap`, `PropertyBoolean BackgroundMask`, `PropertyColor Color`, `PropertyLinetype Linetype`, `PropertyEnum<LineWeight> Lineweight`

Valores de `AnchorPointType` relevantes para perfil: Start, Middle, End, TopLeft…BottomRight, InsertionPoint, Center, Station, LabelLocation, Insertion, **Dimension, PipeDimension, StructureDimension**, **Centerline, TopOuterDiameter, TopInnerDiameter, BottomOuterDiameter, BottomInnerDiameter**, StartExtension, MiddleExtension, EndExtension, BandTop, BandMiddle, BandBottom, …

**`LabelStyleLineComponent`** (líneas guía, verticales de cota):
- `.Line` (`+StyleLine`): `PropertyDouble Angle`, `PropertyDouble Length`, `PropertyEnum<LabelStyleLengthType> LengthType` (FixedLength, PercentLength), `PropertyDouble FixedLength`, `PropertyDouble PercentLength`, `PropertyDouble StartPointXOffset`, `StartPointYOffset`, `EndPointXOffset`, `EndPointYOffset`, `PropertyColor Color`, `PropertyLinetype Linetype`, `PropertyEnum<LineWeight> Lineweight`.
- `.General` (`+StyleGeneral`): `String Name`, `PropertyBoolean Visible`, `PropertyString StartPointAnchorComponent`, `PropertyAnchorPoint StartAnchorPoint`, `PropertyEnum<AnchorLocationType> StartPointAnchorPoint`, **`PropertyBoolean UseEndPointAnchor`**, `PropertyString EndPointAnchorComponent`, `PropertyAnchorPoint EndAnchorPoint`, `PropertyEnum<AnchorLocationType> EndPointAnchorPoint`, `PropertyEnum<LayoutModeType> UsedIn`.
- Con `UseEndPointAnchor` = true y `EndAnchorPoint` = Dimension/StructureDimension se dibuja una línea del objeto al ancla de cota **[sin probar]**.

**Otros componentes:**
- `LabelStyleBlockComponent`:
  - `.Block`: `PropertyString BlockName`, `PropertyDouble BlockHeight`, `PropertyDouble RotationAngle`, `PropertyEnum<BlockAttachmentType> Attachment`, `XOffset`, `YOffset`, `Color`, `Linetype`, `Lineweight`
  - `.General`: `Name`, `Visible`, `AnchorComponent`, `AnchorLocation`, `AnchorPoint`, `UsedIn`
- `LabelStyleTickComponent`:
  - `.Tick`: `AlignWithObject`, `BlockName`, `BlockHeight`, `RotationAngle`, `Color`, `Linetype`, `Lineweight`
  - `.General`: `Name`, `Visible`
- `LabelStyleTextForEachComponent` y `LabelStyleReferenceTextComponent` tienen `Border`, `General` y `Text` heredados de los de texto:
  - TextForEach añade `General.TextForEach {get;}` (string) y `Text.CurveContents` / `Text.SpiralContents`.
  - ReferenceText añade `General.ReferenceTextObjectType {get;}`.

**Wrappers de valor** (namespace `Autodesk.Civil.*`): `PropertyDouble.Value : Double`, `PropertyBoolean.Value : Boolean`, `PropertyString.Value : String` (PropertyLayer y PropertyLinetype heredan de él), `PropertyColor.Value : Autodesk.AutoCAD.Colors.Color`, `PropertyEnum<T>.Value : T`, `PropertyAnchorPoint.Value : AnchorPointType`. Todos tienen `{get;set;}`.

**Unidades de alto y offset: [sin probar].** La muestra oficial de Autodesk usa `Text.Height.Value = 0.0125` y `Line.Length.Value = 0.015`, "in whatever units are used in the drawing". Lo habitual es que sea el tamaño impreso expresado en unidades de dibujo; en imperial, 0.1" ≈ 0.00833 ft. Hay que calibrarlo en C3D leyendo el valor de un estilo cuyo diálogo muestre 0.10".

## 3. Borrar los componentes que trae un estilo recién creado

No hay método `Clear`. Se hace así (todo verificado):
```csharp
foreach (LabelStyleComponentType t in Enum.GetValues(typeof(LabelStyleComponentType))) {
    if (!ls.IsSupportedComponent(t)) continue;
    var names = new List<string>();
    foreach (ObjectId id in ls.GetComponents(t))
        names.Add(((LabelStyleComponent)tr.GetObject(id, OpenMode.ForRead)).Name);
    foreach (var n in names) ls.RemoveComponent(n);
}
```
No sé si `Add(name)` trae componentes por defecto; depende del tipo de etiqueta **[sin probar]**. El bucle es inocuo si no trae ninguno. La muestra de Autodesk hace `try { ls.RemoveComponent("X"); } catch {}` antes de `AddComponent("X", …)` para poder repetir el comando sin duplicados. `AddComponent` devuelve el ObjectId del componente; la muestra lo busca otra vez por nombre con `GetComponents(type)` y `comp.Name`, y conviene hacer lo mismo como respaldo.

## 4. Campos de texto (`<[...]>`)

- **No hay en las DLL ningún enum ni tabla de códigos de campo.** Las cadenas "Station Value" o "Pipe Slope" no aparecen en ningún binario de C3D.
- En los DWG y DWT (el template Imperial NCS y los dibujos de tutoriales) el contenido se **guarda con ids numéricos neutros de idioma**, por ejemplo `<[33607712(2097|2474|2387|2433|2593|2609|2657|…)]>`: id de propiedad más ids de los modificadores. La forma legible por nombre es la que usa la API y la interfaz para mostrar y analizar.
- El único formato con nombres que he podido comprobar es el de las muestras oficiales instaladas (`C3D/Sample/Civil 3D API/DotNet/VB.NET/AlignmentSample/Alignment.vb:629`):
  - `"<[Station Value(Uft|FS|P2|RN|AP|Sn|TP|B2|EN|W0|OF)]>"`
  - `"<[Design Speed(P0|RN|AP|Sn|OF)]>"`
  - Los modificadores se separan con `|` y la «n» de `Sn` va en minúscula en la muestra.
- **Riesgo:** en un Civil 3D en español es probable que el analizador espere los nombres traducidos, así que un nombre en inglés podría salir como texto literal o `???` **[sin probar]**.

Tres formas de reducir el riesgo, de más a menos segura:
1. **Texto literal y override por etiqueta.** El componente del estilo lleva un texto fijo de relleno y cada etiqueta recibe su texto calculado en C# con `SetTextComponentOverride` (punto 5). No depende del idioma. Contrapartida: la etiqueta no se actualiza sola si cambian los datos.
2. **Tomar el código del propio dibujo en ejecución.** Leer `LabelStyleTextComponent.Text.Contents.Value` de un estilo existente (por ejemplo `Network.PipeProfileLabelStyleId`, o el primero de `PlanProfileLabelStyles` o `StationElevationLabelStyles`), extraer los tokens `<[...]>` con una expresión regular y reutilizarlos. También se puede partir de `CopyAsSibling` sobre un estilo del template.
3. Escribir nombres en inglés solo como último recurso, comprobando después con `Contents.Value` que el texto no quedó literal.

## 5. Etiquetas individuales (`Label : LabelBase : Entity`)

`FeatureLabel` no declara miembros propios. Todo está en `Label` y `LabelBase`.

**Estilo:** `prop ObjectId StyleId {get;set;}`, `prop String StyleName {get;set;}`.

**Texto por instancia:**
```
ObjectIdCollection GetTextComponentIds()          // ids de LabelStyleTextComponent del estilo (la muestra los abre como LabelStyleTextComponent y filtra por .Name)
Void SetTextComponentOverride(ObjectId labelStyleComponentId, String textOverride)
Void SetTextComponentOverride(ObjectId labelStyleComponentId, String textOverride, TextJustificationType textJustificationType)  // Left, Center, Right
String GetTextComponentOverride(ObjectId labelStyleComponentId)
Boolean IsTextComponentOverriden(ObjectId labelStyleComponentId)   // (sic, "Overriden")
Void SetTextComponentJustificationOverride(ObjectId, TextJustificationType) / GetTextComponentJustificationOverride(ObjectId)
Void ClearAllTextComponentOverrides()
```

**Posición:**
- `prop Vector3d DraggedOffset {get;set;}`: la muestra oficial DraggedLabel hace `DraggedOffset = destino - AnchorInfo.Location`.
- `prop Point3d LabelLocation {get;set;}`.
- `prop Boolean Dragged {get;}`: no se puede escribir; **no existe `IsDragged`**.
- `prop AnchorInfo AnchorInfo {get;}`, con campos `Point3d Location`, `Vector3d DirectionAtLocation`, `Boolean IsOnCurve`, `Point2d CenterOfCurve`.
- `Void ResetLocation()`, `Void Reset()`, `Void ResetProperties()`.
- `prop Double RotationAngle {get;set;}`, `prop Boolean CanRotate {get;}`, `prop Boolean Flipped {get;set;}`, `prop Boolean Reversed {get;set;}`, `prop Boolean Pinned {get;set;}`.

**Ancla de cota** (para dejar todas las etiquetas alineadas a una misma altura):
- `prop DimensionAnchorOptionType DimensionAnchorOption {get;set;}`, con valores Elevation, Above, Below, Default, **ViewTop, ViewBottom**.
- `prop Double DimensionAnchorValue {get;set;}`, `prop AnchorInfo DimensionAnchorInfo {get;}`.
- En `LabelBase`: `DefaultDimensionAnchorOption {get;set;}` y `DefaultDimensionAnchorValue {get;set;}`.

**Guía y marcador:**
- `LeaderVisibilityType LeaderVisibility {get;set;}` y `LeaderTailVisibilityType LeaderTailVisibility {get;set;}` (FromLabelStyle, AlwaysHide).
- `LeaderAttachmentBehaviorType LeaderAttachment {get;set;}` (ToPoint, ToMarkerExtents, FromMarkerStyle).
- `ObjectId AnchorMarkerStyleId {get;set;}`, `Double AnchorMarkerRotationAngle {get;set;}`.

**En `LabelBase`:**
- Capacidades: `AllowsDragging`, `AllowsDimensionAnchors`, `AllowsFlipping`, `AllowsReversing`, `AllowsPinning`, `AllowsAnchorMarker`, `AllowsLeaderAttachment`.
- `StaggerLabelType AutoStagger {get;set;}` (None, Left, Right, Both).
- `LabelMaskType Mask {get;set;}` (FromLabelStyle, ObjectOnly).
- `ObjectId FeatureId {get;}`, `ObjectId ViewId {get;}`, `LabelType LabelType {get;}`, `LabelRotationType RotationType {get;}`.

## 6. Crear etiquetas: firmas exactas

```
StationElevationLabel.Create(ObjectId profileViewId, ObjectId labelStyleId, ObjectId markerStyleId, Double station, Double elevation) : ObjectId
   props: Double Station {get;}  Double Elevation {get;}  ObjectId Profile1Id {get;set;}  ObjectId Profile2Id {get;set;}
PipeProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId) : ObjectId
PipeProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId, Double ratio, ObjectId labelStyleId) : ObjectId
   prop Double Ratio {get;set;};  static GetAvailableLabelIds(ObjectId profileViewId)
SpanningPipeProfileLabel.Create(ObjectIdCollection profileViewPartIds, ObjectId anchorProfileViewPartId, ObjectId profileViewId) : ObjectId
SpanningPipeProfileLabel.Create(ObjectIdCollection profileViewPartIds, ObjectId anchorProfileViewPartId, ObjectId profileViewId, Double ratio, ObjectId labelStyleId) : ObjectId
   props: Ratio, ReferenceAlignmentId, ShowSpannedProfileViewPipes {get;set;}, AnchorProfileViewPartId {get;set;}, ProfileViewPipeIds/ProfileViewStructureIds {get;}, Length2D/3D CenterToCenter/EdgeToEdge {get;}
CrossingPipeProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId) : ObjectIdCollection
CrossingPipeProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId, ObjectId labelStyleId) : ObjectIdCollection
StructureProfileLabel.Create(ObjectId profileViewId, ObjectId profileViewPartId) : ObjectId                 // ¡ORDEN INVERTIDO!
StructureProfileLabel.Create(ObjectId profileViewId, ObjectId profileViewPartId, ObjectId labelStyleId) : ObjectId
PressurePipeProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId, Double ratio, ObjectId labelStyleId) : ObjectId   // única sobrecarga
PressureFittingProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId, Double ratio, Vector3d direction, ObjectId labelStyleId) : ObjectId  // única
PressureAppurtenanceProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId, Double ratio, Vector3d direction, ObjectId labelStyleId) : ObjectId  // única
CrossingPressurePipeProfileLabel.Create(ObjectId profileViewPartId, ObjectId profileViewId, Double ratio, ObjectId labelStyleId) : ObjectIdCollection  // única
ProfileViewDepthLabel.Create(ObjectId profileViewId, ObjectId labelStyleId, Point2d startPoint, Point2d endPoint) : ObjectId
   props: Point2d StartPoint/EndPoint {get;set;}
```
- **Orden de argumentos:** `StructureProfileLabel.Create` recibe **(profileViewId, profileViewPartId)**. Todas las demás reciben **(profileViewPartId, profileViewId)**.
- `PartProfileLabel` y `PressurePartProfileLabel` tienen `ObjectId ReferenceAlignmentId {get;set;}`.
- Station y Elevation de `StationElevationLabel` son de solo lectura; para mover la etiqueta hay que recrearla o arrastrarla.
- Para fittings y appurtenances no sé qué valor de `direction` es el correcto **[sin probar]**; se puede empezar con `Vector3d.XAxis`.
- No existe una etiqueta spanning para redes a presión.
- `ProfileView` también tiene `GetAvailablePipeProfileLabelIds()`, `GetAvailableStructureProfileLabelIds()`, `GetAvailableSpanningPipeProfileLabelIds()`, `GetLabelIds()` y `GetProfileViewLabelIds()`.

**MarkerStyle** (necesario para `StationElevationLabel`):
- Se crea con `civDoc.Styles.MarkerStyles.Add(String name)` (MarkerStyleCollection), que devuelve un ObjectId.
- `MarkerStyle : MarkerStyleBase`:
  - `MarkerDisplayType MarkerType {get;set;}`: UsePointForMarker, UseCustomMarker, UseSymbolForMarker, UseVerticalLineForMarker.
  - `CustomMarkerType CustomMarkerStyle {get;set;}`: CustomMarkerDot, **CustomMarkerBlank**, CustomMarkerPlus, CustomMarkerX, CustomMarkerVLine.
  - `CustomMarkerSuperimposeType CustomMarkerSuperimposeStyle {get;set;}`: None, Square, Circle, SquareCircle.
  - `Double MarkerSize`, `MarkerSizeType SizeType` (DrawingScale, RelativeToScreen, AbsoluteUnits, FixedScale), `String MarkerSymbolName`, `Double MarkerRotationAngle`, `MarkerOrientationType Orientation`, `Point3d MarkerFixedScale`.
  - Estilos de visualización: `GetMarkerDisplayStylePlan()`, `GetMarkerDisplayStyleModel()`, `GetMarkerDisplayStyleProfile()`, `GetMarkerDisplayStyleSection()`. Cada uno devuelve un `DisplayStyle` con `Visible`, `Color`, `Layer`, `Linetype`, `LinetypeScale`, `Lineweight` y `PlotStyle`, todos `{get;set;}`.
- Marcador invisible: `MarkerType = UseCustomMarker`, `CustomMarkerStyle = CustomMarkerBlank`, `CustomMarkerSuperimposeStyle = None`. Opcionalmente además `GetMarkerDisplayStyleProfile().Visible = false`.
- No sé si `Create` acepta `ObjectId.Null` como marcador **[sin probar]**; mejor pasar el estilo invisible.

## 7. ProfileViewPart por vista: no hay forma directa

- Gravedad: `ProfileViewPart : Entity`. Solo tiene `ObjectId ModelPartId {get;}`, `ObjectIdCollection GetLabelIds()` y `ObjectIdCollection GetPartProfileLabelIds()`. **No tiene `ProfileViewId`.**
- Presión: la clase es distinta, `ProfileViewPressurePart : Entity` (AeccPressurePipesMgd). Solo tiene `ObjectId ModelPartId {get;}`; ni siquiera `GetLabelIds`.
- `Part` y `PressurePart` tienen:
  - `void AddToProfileView(ObjectId profileViewId)`
  - `ObjectIdCollection GetProfileViewsDisplayingMe()`
  - `prop ObjectId ProfileViewPartId {get;}`: un único id. Con varias vistas **no está documentado cuál devuelve**. Solo es fiable si `GetProfileViewsDisplayingMe().Count == 1`.
  - `RemoveFromProfileView(ObjectId)`, `RemoveFromAllProfileViews()`.
  - Solo en `Part`: `AddToSectionView`, `SectionViewPartId`.
- `ProfileView` **no tiene** un método del tipo parte de modelo → parte de vista. Tiene `GetPressureNetworkPartsInGraph()`, pero no sé si devuelve ids de modelo o de vista **[sin probar]**. Hay overrides por vista para estilo y dibujo:
  - Gravedad: `pv.PipeOverrides` / `pv.StructureOverrides`, con elementos `PipeOverride { PipeId, Draw, OverrideStyleId, UseOverrideStyle }` y `StructureOverride { StructId, … }`.
  - Presión: `ProfileViewPressurePipesExtension.GetPressurePipeOverrides(pv)`, `GetPressureFittingOverrides(pv)` y `GetPressureAppurtenanceOverrides(pv)`, con `PressurePartId`, `Draw` y `OverrideStyleId`.

Estrategia recomendada, en capas. Todos los miembros existen; el comportamiento está **[sin probar]**:
```csharp
var nuevos = new List<ObjectId>();
var cGrav = RXObject.GetClass(typeof(ProfileViewPart));
var cPres = RXObject.GetClass(typeof(ProfileViewPressurePart));
ObjectEventHandler h = (s, e) => { var c = e.DBObject.ObjectId.ObjectClass;
    if (c.IsDerivedFrom(cGrav) || c.IsDerivedFrom(cPres)) nuevos.Add(e.DBObject.ObjectId); };
db.ObjectAppended += h;                        // Database.ObjectAppended verificado (event ObjectEventHandler)
try { part.AddToProfileView(pvId); } finally { db.ObjectAppended -= h; }
// luego: abrir cada id nuevo y quedarse con el de ModelPartId == part.ObjectId
```
- **Respaldo 1:** recorrer el BlockTableRecord dueño de la vista (`pv.OwnerId`), filtrar por `ObjectClass` y `ModelPartId`, y desempatar quedándose con la parte cuyo `GeometricExtents` cae dentro de `pv.GeometricExtents`.
- **Respaldo 2:** `part.ProfileViewPartId` cuando la parte esté en una sola vista.
- **Respaldo 3** (solo en try/catch): algunos informan que `Create` acepta el id de la parte de modelo **[sin probar]**.

## 8. Bandas

- `ProfileView.Bands` es un `ProfileViewBandSet : GraphBandSet`, con:
  - `ProfileViewBandItemCollection GetBottomBandItems()` / `GetTopBandItems()`
  - `Void SetBottomBandItems(ProfileViewBandItemCollection bandItems)` / `SetTopBandItems(...)`
  - `Void ImportBandSetStyle(ObjectId bandSetId)`, `ObjectId SaveAsBandSetStyle(String name)`, `Boolean MatchIncrementToGridIntervals {get;set;}`
- `ProfileViewBandItemCollection`:
  - `ctor(ObjectId profileViewId, BandLocationType location)`
  - `Void Add(BandType bandType, String profileBandStyleName)`
  - `prop ProfileViewBandItem Item[Int32 index]`
  - Heredados de `BandSetItemCollection`: `Count`, `RemoveAt`, `RemoveAll`, `Swap(Int32, Int32)`
- `ProfileViewBandItem` (hereda de `ProfileViewBandSetItem : BandSetItem`):
  - Propios: `ObjectId DataSourceId {get;set;}` (para PipeNetwork y PressureNetwork, el id de la red **[sin probar]**), `Profile1Id` / `Profile2Id {get;set;}` (ProfileData), `Alignment2Id`, `MaterialName`, `Nullable<Double> MaxOffsetDistance`
  - Heredados: `BandStyleId {get;set;}`, `BandType {get;}`, `Gap`, `MajorInterval`, `MinorInterval`, `ShowLabels`, `StaggerLabel`, `StaggerLineHeight`, `Weeding`, `LabelAtStartStation`, `LabelAtEndStation`, `Location {get;}`
- `BandType`: ProfileData, HorizontalGeometry, VerticalGeometry, SuperelevationData, SectionData, SectionSegment, **PipeNetwork, PressureNetwork**, SectionalData, CantData. `BandLocationType`: Top, Bottom.
- **Estilos de banda:** `civDoc.Styles.BandStyles` (BandStylesRoot) tiene `.ProfileViewProfileDataBandStyles`, `.ProfileViewPipeNetworkBandStyles`, `.ProfileViewVerticalGeometryBandStyles`, `.ProfileViewHorizontalGeometryBandStyles`, `.ProfileViewSectionalDataBandStyles` y `.ProfileViewSuperElevationBandStyles`. La de presión **no está en BandStylesRoot**; se obtiene con `BandStylesRootPressurePipesExtension.GetProfileViewPressureNetworkBandStyles(BandStylesRoot)`. En todas, `Add(String name)` devuelve un ObjectId.
- **`BandStyle`:** `BandHeight`, `OffsetFromBand`, `Text`, `TextHeight`, `TextStyle`, `TextBoxWidth`, `TextBoxPosition` (LeftOfBand, RightOfBand), `TextLocation` (Right, Center, Left), `WeedingFactor`, `TitleTextLabelStyleId {get;}`, y `static ObjectId GetBandStyleId(Database, BandType, String)`.
- **`PipeNetworkBandStyle`:**
  - `ObjectId PipeLabelStyleId {get;}`, `ObjectId StructureLabelStyleId {get;}`, `BandTickStyle PipeTickStyle`, `BandTickStyle StructureTickStyle`
  - `DisplayStyle GetDisplayStylePlan(PipeNetworkDisplayStyleType)`: Border, TitleBox, TitleBoxText, TicksAtStructureLocation, TicksAtPipeEnds, LabelsAtStructureLocation, LabelsForPipe, LinePipeSchematic
- **`PressureNetworkBandStyle`:**
  - `PressurePipeLabelStyleId`, `FittingLabelStyleId`, `AppurtenanceLabelStyleId` (todos de solo lectura) y sus TickStyle
  - `GetDisplayStylePlan(PressureNetworkDisplayStyleType)`
- Los estilos de etiqueta de banda **no tienen colección propia** en LabelStylesRoot. Se editan abriendo como `LabelStyle` el id devuelto por `*LabelStyleId`, y después con `GetComponents` y `Text.Contents`, como en la muestra `ProfileSample/Profile.vb` de Autodesk.
- Estilos de conjunto de bandas: `civDoc.Styles.ProfileViewBandSetStyles.Add(name)` → `ProfileViewBandSetStyle` → `GetBottomBandSetItems()` → `ProfileViewBandSetItemCollection.Add(Database database, BandType bandType, String profileBandStyleName)` → `SetBottomBandSetItems(...)`.

## 9. Lo que NO existe

- Una forma de obtener el ProfileViewPart de una vista concreta; `ProfileViewPart.ProfileViewId`; `GetLabelIds` en `ProfileViewPressurePart`.
- Enums o constantes con los códigos de campo `<[...]>` en las DLL.
- `Label.IsDragged` (lo que hay es `Dragged {get;}`); setters de `StationElevationLabel.Station` y `.Elevation`.
- Sobrecargas simples de `PressurePipeProfileLabel`, `PressureFittingProfileLabel`, `PressureAppurtenanceProfileLabel` y `CrossingPressurePipeProfileLabel`: solo existe la versión con ratio y estilo.
- Una etiqueta spanning para redes a presión.
- La colección de estilos de banda de presión en `BandStylesRoot` (hay que usar la extensión estática).
- Colecciones de estilos de etiqueta de banda.
- `StyleBase.Description`; `TryGet` en las colecciones.
- Una colección de estilos separada para estructuras en perfil: planta y perfil comparten `StructureLabelStyles.LabelStyles`, y lo mismo pasa con las tuberías en `PipeLabelStyles.PlanProfileLabelStyles`.