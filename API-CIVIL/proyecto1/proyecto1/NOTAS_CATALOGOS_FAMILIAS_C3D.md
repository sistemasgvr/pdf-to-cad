# Catálogos y familias de Civil 3D — cómo agregarlos por código

Notas de oro (auditadas contra runs reales en **C3D 2027 EN**, assembly
`AeccPressurePipesMgd v13.9.1.1308`). Cubren los **tres** flujos que resolvimos
para poblar familias/tamaños de piezas sin que el usuario toque los diálogos a
mano. Guardar y releer antes de tocar cualquier cosa de catálogos: cada uno tiene
una trampa distinta y la API pública **no** documenta la mitad.

---

## 0. El mapa mental: hay DOS mundos de catálogos + el binario

Civil 3D tiene **dos** sistemas de piezas completamente separados, con APIs
distintas. No mezclar conceptos entre ellos:

| | **Gravedad** (sanitario/pluvial) | **Presión** (agua/gas) |
|---|---|---|
| Lista del dibujo | `PartsList` (`Styles.PartsListSet`) | `PressurePartList` (`StylesRootPressurePipesExtension.GetPressurePartLists`) |
| Familia | `PartFamily` (tiene `GUID`) | familias del catálogo, sin objeto propio en la lista |
| Tamaño | `PartSize` / `SizeFilterRecord` | `PressurePartSize` (`FamilyGuid`, `PartSizeGuid`, `PartType`) |
| Agregar familia | `AddPartFamilyByGuid(domain, guid)` | `AddPart(PressurePartSize)` (copia desde el catálogo) |
| Agregar tamaños | `PartFamily.AddPartSize(SizeFilterRecord)` | vienen incluidos al copiar la pieza del catálogo |
| Catálogo activo | sysvar `AECCPIPECATALOG` + `PARTCATALOGREGEN` | `PressurePartCatalog.SetCatalog(path)` (estático) |

Y **debajo de ambos** está el **catálogo binario en SQLite**:
`C:\ProgramData\Autodesk\C3D <año>\<locale>\Pressure Pipes Catalog\<Imperial|Metric>\*.sqlite`
(gravedad usa `.apc`/content aparte; presión usa `.sqlite` directo). Cuando la
API **no** te deja hacer algo (p.ej. crear un tamaño que el catálogo no trae),
el último recurso es **editar el SQLite**.

Las tres soluciones de abajo son, cada una, un nivel distinto de este stack.

---

## 1. Agregar FAMILIAS + todos sus tamaños (GRAVEDAD)

**Archivo:** [`PrepararFamilias.cs`](PrepararFamilias.cs) — comando
`PREPARAR_FAMILIAS_STEP2` (botón "Preparar familias para dibujar").
**Equivale al flujo manual:** Parts List → Standard → clic derecho en la familia
→ "Añadir tamaño de pieza" → tildar "todos los tamaños".

### Claves

1. **Enumerar el catálogo activo:** `PartsList.GetAvailablePartFamilies(DomainType)`
   (Pipe / Structure). Devuelve las familias que hay en el catálogo que
   `PARTCATALOGREGEN` dejó activo. Por eso el flujo manual/alterno corre
   `_PARTCATALOGREGEN _P` y `_PARTCATALOGREGEN _S` primero (via
   `doc.SendStringToExecute(...)`, encadenando `PREPARAR_FAMILIAS_STEP2` después
   porque el diálogo de regen no siempre pasa tokens inline).

2. **Solo las familias que este dibujo usa y que son custom:** se lee el XDATA
   `PDFCAD` de las entidades (`PIPE_FAMILY=` / `PART=`) y se cruza contra
   `ComandosRedes.EsFamiliaCustomPipe/EsFamiliaCustomStruct`. Las de fábrica
   (`Aecc…`) ya traen tamaños de fábrica → no se tocan.

3. **Agregar la familia a "Standard":**
   ```csharp
   partsList.AddPartFamilyByGuid(domain, guid);          // = "Add Type"
   // localizarla de nuevo:
   partsList.GetPartFamilyIdsByDomain(domain) → buscar por GUID
   ```

4. **Agregar TODOS los tamaños — el detalle que cuesta sangre**
   (`AddTamanosPorAnchoYAlto`): `AddPartSize` **NO** expande un producto
   cartesiano solo. Cada llamada agrega **exactamente** la combinación que
   tengan los campos `.Value` en ese momento. Entonces:
   - Se leen del SDK los valores reales de los 2 ejes objetivo con
     `SizeFilterField.ValueList` (Pipe: `PipeInnerWidth`×`PipeInnerHeight`;
     Structure: `StructInnerWidth`×`StructInnerLength`), identificados por
     `field.Context` (`PartContextType`).
   - Se hace **un `AddPartSize(SizeFilterRecord)` por cada combinación** (i,j).
   - **Trampa del ×2:** cualquier OTRO campo tipo lista (p.ej. `Material` con 8
     valores) con `IsMultipleSelect=true` hace que `AddPartSize` duplique. Fix:
     antes de cada `AddPartSize`, poner en **todos** los campos lista
     `IsMultipleSelect=false` y fijarlos a `ValueList[0]`.
   - `IsMultipleSelect=true` es, al revés, la técnica para que UN campo se
     expanda solo (visto en `RedesTuberia.cs`). O sea el flag SÍ influye en el
     SDK, pese a lo que sugiere la doc.

---

## 2. Agregar TAMAÑOS que el catálogo NO trae (editar el SQLite) — BANCODUCTOS

**Archivo:** [`PressureCatalogFiller.cs`](PressureCatalogFiller.cs) — se llama al
final de `PREPARAR_FAMILIAS_STEP2` (`FillAllGapsAllVersions`).
**Problema que resuelve:** hay diámetros de tubería (p.ej. Ø1") que **no tienen
accesorios** (elbow/tee/wye) en el catálogo → Civil 3D no deja dibujar la red.
La API pública **no** permite crear un tamaño nuevo en el catálogo. Solución:
**escribir directamente el SQLite** clonando el tamaño más cercano y escalando.

### Claves

1. **Detectar el gap:** diámetros en `WA_PIPE_MODEL` que no aparecen en ninguna
   tabla de fittings (`WA_ELBOW_MODEL`, `WA_BRANCH_FITTING_MODEL`,
   `WA_FITTING_MODEL`). `pipeDiams.Except(fittingDiams)`.

2. **Clonar + escalar por proporción:** para cada familia de fitting, se busca
   el registro del diámetro **más cercano** (`FindClosestSize`), se copia su fila
   y sus `WA_CONNECTION_POINT`, y se escalan las dimensiones geométricas por
   `ratio = targetDiam / templateDiam` (OUTER_DIAMETER, WALL_THICKNESS,
   POSITION_3D_X/Y/Z, ENGAGEMENT_LENGTH). Si el diámetro existe en
   `WA_CONNECTION_POINT` de una tubería real, se usan esas dimensiones exactas en
   vez del escalado.

3. **IDs nuevos deterministas:** `PID` = UUID v5 (MD5 sobre
   `familia|diámetro|tabla`) → idempotente: re-correr no duplica. `FID` =
   `MAX(FID)+100` incremental. Antes de insertar, `SELECT COUNT(*)` por
   `(PART_FAMILY_NAME, DIAMETER_NOMINAL)`.

4. **Idempotente y transaccional:** si no hay gaps, no toca nada
   (`transaction.Rollback()` cuando `totalCreated == 0`). Corre sobre **todas**
   las versiones/unidades instaladas (`FindAllCatalogRoots`).

5. **Formato de `DIAMETER_NOMINAL`:** unos catálogos usan `"12"`, otros
   `"12 in"`, y los reductores `"12 x 8"`. `ExtractNomDiams` parsea con regex y
   `MakeDnString` respeta el sufijo detectado (`DetectInSuffix`).

> Nota: el lado Python tiene el equivalente en
> [`scripts/fill_pressure_catalog_gaps.py`](../../../scripts/fill_pressure_catalog_gaps.py)
> y `fill_pressure_catalog_gaps_multi.py` (mismo algoritmo, para correr fuera de
> C3D).

---

## 3. Agregar FAMILIAS Wye de PRESIÓN a la PressurePartList

**Archivo:** [`AsegurarPresionWye.cs`](AsegurarPresionWye.cs) — comando de prueba
`CARGAR_WYE`; en producción lo llama `PREPARAR_FAMILIAS_STEP2` (paso 6) y el
pre-scan de junturas en [`RedesPresionJunturas.cs`](RedesPresionJunturas.cs).
**Equivale al flujo manual:** Parts List Standard → Information → **"Load new
catalog"** → `Imperial_AWWA_Steel.sqlite` → Fittings → **"Add Type"** → elegir
"Imperial_AWWA_Steel" → tildar Wye → **"Add all sizes"**.

Este fue **el más difícil de todo el proyecto** (varios días, muchas iteraciones).
La API de presión **no está documentada** (en la doc pública ≤2022
`PressurePartList` era `internal`; en 2027 ya es público y **expone más de lo que
dice la doc**). Lo resolvimos **descubriendo la API real por reflexión** (§4) y,
al final, apoyándonos en un **comando oficial** para el paso que la API NO permite.

> **TL;DR de la solución que FUNCIONÓ (2026-09-23):**
> 1. La red de agua usa una PressurePartList del catálogo **Steel** creada con el
>    comando oficial **`CREATEPRESSUREPARTLISTFULL`** (no por `plc.Add`).
> 2. El import **prueba** cada lista colocando una Wye de verdad y solo usa la que
>    construye; si ninguna, cae a "Standard" (tubos siempre salen).
> 3. Costo aceptado por el usuario: los tubos de agua quedan en acero AWWA.

### La API REAL de listado (confirmada por dump del assembly)

```csharp
PressurePartCatalog.SetCatalog(string fullPath)          // ESTÁTICO = "Load new catalog"
<partsList>.Catalog                    → PressurePartCatalog   // catálogo de ESA lista
PressurePartCatalog.GetParts(PressurePartDomainType)  → List<PressurePartSize>  // piezas DEL CATÁLOGO
PressurePartList.AddPart(PressurePartSize)               // copia la entrada a la lista
```

### El viaje completo — 4 bugs/paredes en orden

1. **`pl.GetPart(guid)` NO lee del catálogo.** Busca una pieza **ya presente en
   la lista** → devolvía `null` para los 116 GUIDs. Es un lookup, no un importador.
   → Correcto: `catalog.GetParts(domain)` enumera el **catálogo**.

2. **`pl.Catalog` NO refleja `SetCatalog`.** `SetCatalog` cambia el catálogo activo
   **global**, pero `pl.Catalog` devuelve el catálogo **propio** de la lista
   (PushOn → Cross/Elbow/Tee, sin Wye). Síntoma: `175 pieza(s); 0 son Wye`.
   → Para LEER las Wye del catálogo Steel: `SetCatalog(steel)` + crear una lista
   **temporal**; su `.Catalog` sí queda ligado a Steel. (Confirmado comparando
   `tmp.CatalogGuid` ≠ `pl.CatalogGuid`.)

3. **⛔ LA PARED REAL — `AddPart` copia la ENTRADA, no REGISTRA el catálogo.**
   Copiar las Wye a "Standard" con `AddPart` hace que **aparezcan** en la pestaña
   Fittings… pero `net.AddFitting(wye)` lanza **`"Fail to add a new fitting."`**.
   Motivo: para **construir** la geometría, el catálogo Steel tiene que estar
   **registrado en la parts list de la red** — eso es el botón manual **"Load new
   catalog"**, y **ese registro NO tiene API** (`PressurePartList` no expone
   `AddCatalog`; `SetCatalog` activo no basta; una lista Steel aparte tampoco).
   Por eso la 1ª vez sí funcionó: en ESE dibujo el usuario había hecho "Load new
   catalog" a mano sobre Standard.

4. **⛔ Una PressurePartList creada por código NO construye NADA.** Intentamos
   crear una lista Steel completa con `plc.Add` + `AddPart` de todos los tubos y
   fittings. Resultado: **ni los tubos** se dibujaban (`"Fail to add line pipe."`).
   → **Solo construyen** las listas creadas por la **plantilla/UI** de Civil 3D
   (como "Standard" original) **o por el comando oficial** (ver solución).

### ✅ LA SOLUCIÓN (la que quedó en el código)

**a) Crear la lista Steel con el comando OFICIAL, no por API.**
En `PREPARAR_FAMILIAS_STEP2`, al final: `AsegurarPresionWye.ActivarCatalogo()`
(= `SetCatalog(steel)`) y luego **encolar**
`doc.SendStringToExecute("_CREATEPRESSUREPARTLISTFULL ", true, false, false)`.
El comando corre DESPUÉS (cola de AutoCAD) y crea una lista **bien registrada**
con el catálogo activo (Steel) → **sí construye** sus piezas, incluida la Y.
(Si pide nombre en la línea de comandos, el usuario lo escribe; el import la
encuentra sin importar el nombre, ver (b).)

**b) Elegir la lista por PRUEBA REAL, con fallback seguro.**
`ImportarRed.SeleccionarListaPresion` / `ProbarListaWye`: antes de crear cada red
de presión, se crea una **red de prueba** y se intenta `AddFitting` de una Wye;
si no lanza, esa lista construye la Y y se usa; si ninguna, cae a "Standard"
(que sí construye tubos/tees) → **el dibujo nunca se rompe**. La red de prueba se
borra (`Erase`).

**c) Bug lateral corregido: la corrección degradaba Wye→Tee.**
`RedesPresion.cs` (CorregirFittings) usaba `DecidirTipoFitting`, que devuelve
**Tee para 3 miembros siempre** → reemplazaba cualquier Wye bien puesta. Fix: para
3 tuberías usar `DecidirTeeOWye` (ángulos entre salidas: sin par colineal ⇒ Wye).

### Alternativa sin cambiar material (NO automatizable)
Registrar el catálogo Steel **una sola vez** en la lista "Standard" de la
**plantilla .dwt** (Toolspace → Pressure Networks → Parts Lists → Standard →
Edit → Information → **Load new catalog** → `Imperial_AWWA_Steel.sqlite`) y guardar
la plantilla. Desde ahí la Y sale automática **conservando los tubos PushOn**. Es
la única forma de mantener el material; se descartó porque el usuario quería 0
pasos manuales.

---

## 4. Claves TRANSVERSALES (aplican a los tres)

### 4.1 Cómo descubrir una API version-specific: DUMP por reflexión
Cuando la doc miente o el tipo es `internal`, la técnica que nos salvó fue
**volcar el assembly por reflexión a un `.txt`** y leerlo: todos los tipos del
assembly, y método por método / propiedad por propiedad de `PressurePartList`,
`PressurePartSize` y todo tipo con `Catalog`/`Content` en el nombre. **Así
descubrimos `SetCatalog` y `pl.Catalog`** (el API 2027 va por delante de la doc
pública 2022). Los comandos de dump que se usaron para esto ya se retiraron del
plugin una vez cumplido su propósito; si hace falta de nuevo, se reimplementa un
`[CommandMethod]` que recorra `asm.GetTypes()` por reflexión y escriba a disco.

### 4.2 Tipo público en runtime pero inaccesible al compilar
`PressurePartCatalog` sale como `IsPublic==true` por reflexión pero el compilador
lo rechaza (`CS0122`). → Tocarlo **solo por reflexión** (`asm.GetType(fullName)` +
`GetMethod`/`GetProperty`/`Invoke`). `PressurePartList` y `PressurePartSize` sí
son accesibles directo.

### 4.3 `e_sqlite3.dll` bajo NETLOAD
`Microsoft.Data.Sqlite` lanza `TypeInitializationException` bajo NETLOAD porque
no resuelve la DLL nativa. Fix (`EnsureSqliteNativeLoaded`): cargar a mano con
`NativeLibrary.Load()` desde `<dir del DLL>\runtimes\win-x64\native\e_sqlite3.dll`
(o junto al ensamblado) **antes** de tocar `SqliteConnection`.

### 4.4 Localizar el catálogo por versión × idioma
`LocalizarSqlite()`: iterar años (2027→2024) y **subcarpetas de idioma reales**
del FS (enu/esp/deu/…), prefiriendo el locale de la sesión (`InstalledUICulture`
→ carpeta). El binario y sus GUIDs son idénticos entre idiomas, así que cualquier
locale instalado sirve.

### 4.5 `SendStringToExecute` para comandos que abren diálogo
`PARTCATALOGREGEN` (y otros) abren TaskDialog y no siempre aceptan tokens inline.
Patrón: encolar los comandos con `doc.SendStringToExecute(...)` y encadenar el
paso siguiente como **otro** `SendStringToExecute` (corre después, en su propio
contexto de comando), no dentro de la misma transacción.

### 4.6 Idempotencia SIEMPRE
Los tres flujos se pueden re-ejecutar sin duplicar: gravedad salta familias/tamaños
ya presentes; el filler usa PID determinista + COUNT previo; Wye salta por
`Description` los `PartType==Wye` ya cargados.

---

## 5. Comandos de diagnóstico (dejar en el plugin)

| Comando | Qué hace |
|---|---|
| `PREPARAR_FAMILIAS_STEP2` | Flujo completo: gravedad (AddPartFamily+AddPartSize) + filler SQLite de gaps + carga de entradas Wye en "Standard" + **encola `CREATEPRESSUREPARTLISTFULL`** con catálogo Steel activo. Ya **no** retorna temprano si faltan familias de gravedad (sigue hasta el paso de presión). |
| `_CREATEPRESSUREPARTLISTFULL` | Comando **oficial de Autodesk** (lo encola STEP2). Crea una PressurePartList completa y **bien registrada** del catálogo activo → sus piezas SÍ se construyen. Es la pieza que faltaba para dibujar la Y automáticamente. |

> Comandos retirados: `CARGAR_WYE` y `DUMP_API_PRESION` (fueron para diagnóstico;
> el dump ya cumplió su propósito — reimplementar por reflexión si hace falta).
> El intento de lista Steel por `plc.Add` (`ConstruirListaSteelCompleta` /
> nombres `AWWA_Steel`, `GVR_AWWA_Steel`) quedó como **código muerto/aprendizaje**:
> NO se usa porque una lista creada por API no construye piezas (bug #4).

El log de `PREPARAR_FAMILIAS_STEP2` se guarda en
`Escritorio\AsistenteC3D_PREPARAR_FAMILIAS.txt` (incluye líneas `D()` que no
salen en consola: valores crudos de los ejes leídos del SDK, para diffear contra
`app/civil_catalog.py`).

---

## 6. Tablas SQLite del catálogo de presión (referencia rápida)

- `WA_PIPE_MODEL` — tuberías. `DIAMETER_NOMINAL`, `PID`.
- `WA_BRANCH_FITTING_MODEL` — wyes/tees. `ID_TYPE=4` = **wye**. `PART_FAMILY_ID`
  (GUID de familia), `PID` (GUID de tamaño), `PART_FAMILY_NAME`, `DESCRIPTION`,
  `DIAMETER_NOMINAL`.
- `WA_ELBOW_MODEL`, `WA_FITTING_MODEL` — otros fittings.
- `WA_CONNECTION_POINT` — puertos de cada pieza (`PID`, `NOMINAL_DIAMETER`,
  `OUTER_DIAMETER`, `WALL_THICKNESS`, `POSITION_3D_X/Y/Z`, `ENGAGEMENT_LENGTH`).

> El `PID` de un **tamaño** es lo que consume la API por GUID; `PART_FAMILY_ID`
> es el GUID de la **familia**. No confundirlos (nos costó un ciclo entero).
