# proyecto1 — Add‑in de AutoCAD Civil 3D 2026

Add‑in (complemento) escrito en **C#** que automatiza tareas de **AutoCAD Civil 3D 2026**:
crear puntos, CogoPoints, superficies, alineamientos, perfiles, **corredores** y **redes de tubería (Pipe Networks)**.

Este documento explica **cómo está armado el proyecto**, **cómo se carga en Civil 3D** y, sobre todo,
**cómo leer el código** aunque no sepas programar ni conozcas la API de Civil 3D.

---

## 1. Requisitos

- **AutoCAD Civil 3D 2026** (corre sobre **.NET 8**; por eso el proyecto es `net8.0-windows`, x64).
- **Visual Studio 2022** (para compilar).
- El proyecto referencia las DLL de Autodesk desde `C:\Program Files\Autodesk\AutoCAD 2026\...`
  (ver `proyecto1\proyecto1.csproj`). Si instalaste Civil 3D en otra ruta, ajusta esos `HintPath`.

---

## 2. Compilar y cargar

1. Abre `proyecto1.sln` en Visual Studio → **Compilar** (Ctrl+Shift+B).
   - Sale el DLL en `proyecto1\bin\x64\Debug\proyecto1.dll`.
2. Abre Civil 3D 2026 y escribe el comando **`NETLOAD`** → selecciona ese `proyecto1.dll`.
3. Ya puedes escribir cualquiera de los comandos (ver sección 6).

> ⚠️ **Importante:** una vez cargado con `NETLOAD`, Civil 3D **bloquea el DLL** hasta que cierras el programa.
> Si al recompilar te sale un error `MSB3021 / archivo en uso`, **cierra Civil 3D**, recompila y vuelve a `NETLOAD`.

---

## 3. Arquitectura del proyecto

```
proyecto1/                     ← carpeta de la solución
├── proyecto1.sln              ← se abre en Visual Studio
├── README.md                  ← este archivo
├── *.csv                      ← archivos de ejemplo para probar
└── proyecto1/                 ← carpeta del proyecto (código)
    ├── proyecto1.csproj        ← configuración (.NET 8, x64, referencias a Civil 3D)
    ├── Puntos.cs               ← clase ComandosPuntos      (unir CogoPoints)
    ├── Comandos_Civil.cs       ← clase ComandosCivilReal   (puntos, cogopoints, alineamiento, superficie, curvas)
    ├── Corredores.cs           ← clase ComandosCorredores  (corredores, perfiles, vistas, sólidos 3D)
    └── RedesTuberia.cs         ← clase ComandosRedes       (redes de tubería / pipe networks)
```

- Cada archivo `.cs` contiene **una clase** con varios **comandos**.
- Un **comando** es un método marcado con `[CommandMethod("NOMBRE")]`: ese `NOMBRE` es lo que
  escribes en la línea de comandos de Civil 3D.
- Todas las clases están en el mismo *namespace* `Civil3DBasico`, así que da igual en qué archivo esté
  cada comando: todos se registran juntos al cargar el DLL.

---

## 4. Curso exprés de la API de Civil 3D (para principiantes)

Casi todos los comandos siguen **el mismo patrón**. Si entiendes estos conceptos, entiendes todo el código.

### 4.1 Los tres objetos base
```csharp
Document doc = Application.DocumentManager.MdiActiveDocument; // el dibujo abierto
Editor   ed  = doc.Editor;                                    // la "línea de comandos": pregunta y escribe mensajes
Database db  = doc.Database;                                  // la base de datos del dibujo (donde viven las entidades)
CivilDocument civilDoc = CivilApplication.ActiveDocument;     // la parte "Civil 3D" del dibujo (superficies, redes, estilos…)
```

### 4.2 La Transacción (Transaction) — obligatoria para tocar el dibujo
Todo lo que **lea o modifique** objetos del dibujo va dentro de una *transacción*. Es como “abrir una sesión”:
si todo sale bien haces **`Commit()`** (guardar); si algo falla, **`Abort()`** (deshacer todo).

```csharp
using (Transaction tr = db.TransactionManager.StartTransaction())
{
    // ... aquí leo/creo/modifico objetos ...
    tr.Commit();   // confirmar los cambios
}
```
El `using(...)` garantiza que la transacción se cierra sola aunque haya un error.

### 4.3 ObjectId y "abrir" objetos (ForRead / ForWrite)
En Civil 3D **no manejas los objetos directamente**, sino su **identificador**: `ObjectId`.
Para usar el objeto real, lo "abres" dentro de la transacción con `GetObject`, indicando si es para
**leer** (`ForRead`) o para **modificar** (`ForWrite`):

```csharp
CogoPoint cp = tr.GetObject(id, OpenMode.ForRead)  as CogoPoint;   // solo leer
Structure st = tr.GetObject(id, OpenMode.ForWrite) as Structure;   // modificar (aquí sí puedo cambiarle cotas)
```
`as Tipo` intenta convertir; si el objeto no es de ese tipo, devuelve `null` (por eso a veces se comprueba `!= null`).

### 4.4 Pedir datos al usuario (los `Prompt...`)
El `Editor` (`ed`) hace las preguntas en la línea de comandos. Los tipos más usados:

| Método | Para qué | Devuelve |
|---|---|---|
| `ed.GetPoint(...)` | pedir un punto (clic) | `PromptPointResult` (`.Value` = Point3d) |
| `ed.GetString(...)` | pedir un texto | `PromptResult` (`.StringResult`) |
| `ed.GetDouble(...)` | pedir un número | `PromptDoubleResult` (`.Value`) |
| `ed.GetInteger(...)` | pedir un entero | `PromptIntegerResult` (`.Value`) |
| `ed.GetKeywords(...)` | elegir opción `[A/B/C]` | `PromptResult` (`.StringResult`) |
| `ed.GetEntity(...)` | seleccionar UNA entidad | `PromptEntityResult` (`.ObjectId`) |
| `ed.GetSelection(...)` | seleccionar VARIAS | `PromptSelectionResult` (`.Value`) |

**Siempre** se revisa `.Status`: si no es `PromptStatus.OK`, el usuario canceló (ESC) y se sale del comando.

```csharp
PromptPointResult r = ed.GetPoint("\nIndique un punto: ");
if (r.Status != PromptStatus.OK) return;   // el usuario canceló
Point3d p = r.Value;
```

### 4.5 Crear una entidad y meterla en el dibujo (ModelSpace)
Las entidades "normales" de AutoCAD (puntos, líneas, polilíneas) se guardan en el **ModelSpace**:

```csharp
BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);

DBPoint punto = new DBPoint(new Point3d(10, 20, 0));
ms.AppendEntity(punto);              // lo añade al dibujo
tr.AddNewlyCreatedDBObject(punto, true);
```
Los objetos **de Civil 3D** (superficies, alineamientos, redes…) NO van al ModelSpace: se crean con
métodos propios (`TinSurface.Create`, `Alignment.Create`, `Network.Create`, …).

### 4.6 Glosario rápido de objetos Civil 3D usados
- **CogoPoint**: punto topográfico de Civil 3D (con nº, cota, descripción). Colección: `civilDoc.CogoPoints`.
- **TinSurface**: superficie triangulada (terreno).
- **Alignment**: eje / trazado en planta.
- **Profile**: perfil vertical de un eje (terreno o **rasante** de diseño). Se ve en una **ProfileView** (vista de perfil).
- **Corridor**: corredor. Estructura: `Corridor → Baseline (eje+rasante) → BaselineRegion (assembly)`.
- **Assembly**: sección transversal tipo (se arma a mano en Civil 3D; el código solo la *selecciona*).
- **Network** (Pipe Network): red de tubería = **Structures** (buzones) + **Pipes** (tuberías) + una **Parts List** (catálogo de tamaños).

---

## 5. Cómo leer un comando (ejemplo comentado)

Todos los comandos tienen la misma forma. Ejemplo simplificado:

```csharp
[CommandMethod("CREAR_PUNTOS")]          // 1) el nombre que escribes en Civil 3D
public void CrearPuntos()
{
    Document doc = Application.DocumentManager.MdiActiveDocument;   // 2) el dibujo
    Editor ed = doc.Editor;
    Database db = doc.Database;

    using (Transaction tr = db.TransactionManager.StartTransaction())  // 3) abrir transacción
    {
        // 4) preguntar/crear...
        PromptPointResult r = ed.GetPoint("\nIndique punto: ");
        if (r.Status != PromptStatus.OK) return;   // usuario canceló

        // 5) confirmar
        tr.Commit();
    }
}
```
Con este molde en la cabeza, cualquiera de los 26 comandos se lee igual: *pedir datos → hacer algo dentro de la transacción → Commit*.

---

## 6. Referencia de comandos

### Puntos (`Puntos.cs`)
| Comando | Qué hace |
|---|---|
| `UNIR_PUNTOS` | Une CogoPoints existentes con una polilínea 3D (ordenados por número o descripción) |

### Puntos / Eje / Superficie / Curvas (`Comandos_Civil.cs`)
| Comando | Qué hace |
|---|---|
| `CREAR_PUNTOS` | Crea puntos de AutoCAD (DBPoint) marcando en pantalla |
| `CREAR_COGOPOINTS` | Crea CogoPoints desde pantalla o desde un CSV `X,Y,Z,Desc` |
| `CREAR_ALIG_REAL` | Crea un Alignment a partir de una polilínea (pregunta si invertir el sentido) |
| `CREAR_SUPERFICIE` | Crea una superficie TIN desde CogoPoints o polilíneas (Contornos / Breaklines / Vértices) |
| `DIAG_ENTIDADES` | Diagnóstico: cuenta entidades, capas y el **rango de Z** (dice si las polilíneas están planas) |
| `UNIR_CURVAS` | Reconecta curvas de nivel partidas por su número (une extremos colineales) |
| `ELEVAR_CURVAS_POR_TEXTO` | Asigna a cada curva su cota leyéndola del texto más cercano |

### Corredores y perfiles (`Corredores.cs`)
| Comando | Qué hace |
|---|---|
| `CREAR_CORREDOR` | Corredor simple: 1 eje + 1 rasante + 1 assembly |
| `CREAR_CORREDOR_TRAMOS` | Un baseline por tramo (**ejes divididos** → esquinas de 90°, canales) |
| `CREAR_CORREDOR_REGIONES` | 1 eje + 1 rasante con **varias regiones por estación** (cambia la sección por tramos) |
| `CREAR_PROFILE_TERRENO` | Perfil del terreno proyectando una superficie sobre el eje (+ dibuja la vista) |
| `CREAR_PROFILE_DISENO` | Rasante de diseño tecleando los PVIs (estación, cota) |
| `CREAR_RASANTE_EN_VISTA` | Rasante dibujada **pinchando puntos** dentro de una vista de perfil |
| `CREAR_VISTA_PERFIL` | Dibuja una vista de perfil vacía (útil sin superficie) |
| `AJUSTAR_RANGO_VISTA` | Fija el rango vertical de una vista de perfil (cota mín−margen … máx+margen) |
| `CREAR_SUPERFICIE_CORREDOR` | Genera la superficie del corredor (código `Top` o `Datum`) |
| `EXTRAER_SOLIDOS_CORREDOR` | Extrae los sólidos 3D del corredor (respeta huecos, p. ej. canal cerrado) |

### Redes de tubería (`RedesTuberia.cs`)
| Comando | Qué hace |
|---|---|
| `CREAR_RED` | Crea una red vacía + le asigna una Parts List + superficie de referencia opcional |
| `LISTAR_PARTSLISTS` | Lista las Parts Lists (catálogos) del dibujo |
| `LISTAR_PIEZAS` | Lista las familias (tipos) y tamaños de estructuras y tuberías de la Parts List |
| `AGREGAR_FAMILIA` | Añade una familia del catálogo a la Parts List, con todos sus tamaños |
| `AGREGAR_TAMANOS` | Añade diámetros específicos a una familia (útil en tuberías paramétricas) |
| `CREAR_RED_DESDE_CSV` | Red simple en cadena: buzones consecutivos unidos por tubería (auto-elige pieza) |
| `CREAR_RED_AVANZADA` | Buzón con tipo/radio por fila del CSV + tuberías **por tramo** (material+diámetro) |
| `CREAR_RED_COMPLETA` | Red 100% desde datos: **dos CSV** (buzones + tuberías) |

---

## 7. Formatos de CSV

**Buzones** (`CREAR_RED_AVANZADA`, `CREAR_RED_COMPLETA`):
```
Name,X,Y,CotaSup,CotaInf,Type,Radius
B1,1000,5000,101.0,98.5,Cylindrical,1200
```
- `CotaSup` = cota de tapa (rim). `CotaInf` = cota de fondo (invert/sump).
- `Type` = familia de estructura (busca por texto contenido). `Radius` = tamaño.

**Tuberías** (`CREAR_RED_COMPLETA`):
```
Desde,Hasta,Material,Diametro
B1,B2,PVC Pipe,110
```
- `Desde/Hasta` = nombres de buzones. `Material` = familia de tubería. `Diametro` = diámetro.

**CogoPoints** (`CREAR_COGOPOINTS` opción CSV):
```
X,Y,Z,Descripcion
1000,5000,100.5,EJE
```

> El lector de CSV es **tolerante**: acepta separador `,` o `;` y decimales con `.` o `,`.
> El emparejamiento de `Type/Material` es por *texto contenido*, y `Radius/Diametro` por número
> (ignora comas/espacios: `1300` encuentra `1,300`).

Archivos de ejemplo incluidos: `puntos_ejemplo.csv`, `red_ejemplo.csv`, `red_avanzada_ejemplo.csv`,
`red_buzones.csv`, `red_tuberias.csv`.

---

## 8. Flujos de trabajo típicos

**Topografía → superficie**
```
CREAR_COGOPOINTS (o curvas)  →  [si están planas] UNIR_CURVAS + ELEVAR_CURVAS_POR_TEXTO  →  CREAR_SUPERFICIE
```

**Corredor (p. ej. un canal)**
```
CREAR_ALIG_REAL  →  CREAR_PROFILE_DISENO (rasante)  →  [assembly a mano en Civil 3D]  →
CREAR_CORREDOR (o _TRAMOS / _REGIONES)  →  CREAR_SUPERFICIE_CORREDOR / EXTRAER_SOLIDOS_CORREDOR
```

**Red de tubería**
```
(una vez) Set Pipe Network Catalog en la UI  →  AGREGAR_FAMILIA (buzón y tubería)  →
LISTAR_PIEZAS (ver qué hay)  →  preparar CSV  →  CREAR_RED_COMPLETA
```

---

## 9. Cosas que conviene saber (gotchas)

- **Curvas de nivel planas (Z=0):** muchos planos traen la cota solo como *texto*. Antes de hacer
  superficie, revisa con `DIAG_ENTIDADES` y, si están planas, usa `UNIR_CURVAS` + `ELEVAR_CURVAS_POR_TEXTO`.
- **Un perfil es invisible** hasta que se dibuja una **vista de perfil** (por eso los comandos de perfil
  también crean la vista).
- **Esquinas de 90° en corredores:** un corredor de un solo eje no las hace cuadradas → usa
  `CREAR_CORREDOR_TRAMOS` (un eje por tramo).
- **Assembly:** no se puede fabricar por código; se arma a mano en Civil 3D y el add‑in solo lo selecciona.
- **Parts List = selección del catálogo:** solo puede contener tamaños que el catálogo defina. Para tener
  más diámetros necesitas un catálogo que los incluya (o una familia paramétrica).
- **El DLL se bloquea** mientras Civil 3D está abierto (ver sección 2).
```
