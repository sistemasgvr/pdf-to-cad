# DISEÑO TÉCNICO — CREAR_PERFIL_RED (perfil longitudinal 100 % nativo de Civil 3D)

**Revisión 2.** Esta revisión incorpora la crítica de API/ejecución y la de composición/dibujo. El documento es **autocontenido**: el informe de exploración `diseno.md` se perdió porque en Windows `diseno.md` y `DISENO.md` son el mismo archivo. Lo normativo de las imágenes de referencia está en la sección 0. La revisión 1 queda en `DISENO_rev1_backup.md`.

> **Nota de implementación (2026-09-30).** C.5 dice que el punto medio de un arco con bulge positivo cae «a la izquierda» de la cuerda: es un error. Con la convención de AutoCAD (bulge > 0 = antihorario) cae a la DERECHA, como confirman las tangentes del caso R5. `PerfilRecorrido.PuntoMedioArco` implementa la geometría correcta y el arnés lo comprueba. R4 se prueba con un lazo de 12 lados (un cuadrado de 90° no pasa el tope de 45° de la continuación).

**Datos del plugin**
- Ruta: `D:/GVR/Proyectos_DEV/EEUU/pdf-to-cad/API-CIVIL/proyecto1/proyecto1`.
- Namespace `Civil3DBasico`, net8.0-windows x64, Civil 3D 2025 en ESPAÑOL.

**Fuentes**
- `apiEstilos.md`, `apiEtiquetas.md` y `codigo.md`, en esta misma carpeta.
- Las imágenes `images/50.png` y `images/51.png`.
- El arnés de compilación `scratchpad/critica/Check.cs`.

**Verificación de firmas.** Todas las firmas citadas se comprobaron por reflexión con:
- `apiref3.exe` y `apiref_estilos.exe`.
- `scratchpad/apiref4/out/apiref4.exe`: creado en esta revisión. Es igual a apiref3 pero añade `accoremgd.dll`.

Lo que solo se puede comprobar dentro de Civil 3D va marcado **[EJECUCIÓN]**. Su mitigación está en la sección I, y la prueba de humo de la sección J lo valida.

**Convenciones**
- `S` = `CivilDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingScale`. Son pies de modelo por pulgada de ploteo, así que 10 significa 1"=10'. Se considera válido si `0 < S ≤ 1000`.
- «in» = pulgadas de PLOTEO. Una distancia de ploteo `d` in mide `d·S` ft en el modelo, tanto en X como en Y. La vista aplica la exageración vertical a la Y de las cotas; los textos no se deforman.
- `Pl(d)` = valor que se escribe en una propiedad de estilo de ploteo = `d · FactorPl`.
  - `FactorPl` inicial = 1/12 en pies y 0.0254 en metros (I-1).
  - Se recalibra midiendo las etiquetas reales (F.10, G.7).
- `V` = pies de cota por pulgada de ploteo vertical. Se elige de la lista estándar (F.3). `VE = S / V`.
- Coordenadas dentro del marco de una vista:
  - `X(e) = (e − StationStart)/S`
  - `Y(z) = (z − ElevationMin)/V`
- Todo el código C# nuevo usa:
  - `using Autodesk.Civil;` para `LabelTextAttachmentType`, `LeaderShapeType`, `LeaderVisibilityType`, `LeaderTailVisibilityType`, `OrientationReferenceType`, `LabelContentDisplayType` y `TextJustificationType`.
  - `using Autodesk.Civil.Settings;` para `DrawingUnitType`.
  - `using CivilDB = Autodesk.Civil.DatabaseServices;` y `using Exception = System.Exception;`, como el resto del plugin.

---

## 0. Referencias visuales (50.png, 51.png): reglas que el diseño reproduce

1. **Marco y rejilla**
   - Líneas horizontales: las mayores en negro cada `CotaMayor` y las menores en gris cada `CotaMenor`.
   - Líneas verticales: solo las mayores, cada 100 ft de estación.
   - Las cotas (730, 740…) van en los ejes izquierdo y derecho. Las estaciones mayores van en el eje inferior, y además la de cada extremo del marco (0+85, 1+85).
   - Títulos: «ELEVATION (FT)» en vertical a ambos lados y «STATION (FT)» centrado bajo los números. Los títulos de eje tienen la misma altura que los números.
2. **Tubería del recorrido**
   - Se dibujan las paredes exteriores y las líneas de extremo.
   - La tubería empieza en 1+00, a unas 1.5" del borde izquierdo.
   - El terreno existente (EX. GRADE) va en trazo discontinuo gris.
3. **Fila de tramos**, pegada al borde superior del marco:
   - Contenido: «INSTALL 50 LF OF NEW 8" WELD STL PIPE» en una línea, o «INSTALL 5 LF OF / NEW 8" DI PIPE» en dos.
   - El texto va centrado sobre su «celda», es decir, el tramo entre dos verticales de límite. Esas verticales bajan desde la base de la fila hasta la corona del tubo.
   - Si el texto no cabe, sube a una fila más alta y lleva un leader que apunta a su celda.
4. **Callouts**
   - Texto vertical que se lee de abajo arriba. La 1.ª línea («PIPE STA 1+00.00») queda subrayada por la cola del leader.
   - Las líneas se justifican a la izquierda desde una base común.
   - Franja superior: apoyada sobre el dibujo. Franja inferior: colgada bajo el dibujo.
   - Leader recto con flecha que nace en el extremo de la cola más cercano al tubo. Inclinación máxima de unos 60°.
   - En general, accesorios y tees arriba; codos y deflexiones abajo.
   - Ningún texto cruza una vertical de límite ni otro texto.
5. **Cruces**
   - La tubería cruzada se dibuja como elipse o círculo, con su callout («EX. 18" VCP SEWER, COLA»).
   - Varios conductos de la misma red se rotulan en un solo callout.
   - Separaciones y recubrimientos van como cotas verticales que muestran SOLO el valor («1.22'», «5.83'»).
6. **Título**: bajo la vista y alineado a la izquierda, con el formato `PROFILE 10 - 8 INCH MAIN - …`.
7. **Fuera de alcance** (no hay datos para dibujarlos):
   - casing
   - PROP GRADE
   - ejes de vía («EAST TRACK»)
   - las cotas horizontales con flechas de la fila de tramos. Ningún objeto nativo de la vista de perfil dibuja una cota horizontal de largo variable; la celda se marca con sus verticales de límite (ver K).

---

## A. Archivos

### A.1 Nuevos (en `proyecto1/proyecto1/`, namespace `Civil3DBasico`, todos < 500 líneas)

| Archivo | Tipo | Responsabilidad | Líneas est. |
|---|---|---|---|
| `PerfilComando.cs` | `public class ComandosPerfil` | `[CommandMethod("CREAR_PERFIL_RED")]` y el alias `CREAR_PERFIL_PRESION`. Orquesta prompts → T0…T6 (sección G) y el resumen. No dibuja nada por sí mismo. | 380 |
| `PerfilPruebaHumo.cs` | `public class ComandosPerfilPrueba` | `[CommandMethod("PDFCAD_PERFIL_PRUEBA")]`: prueba de humo de la sección J. | 200 |
| `PerfilModelo.cs` | `internal` clases de datos | Modelo con `ObjectId` (B.1). Sin lógica. | 220 |
| `PerfilRecorrido.cs` | **PURO** | Grafo (V2, GNodo, GArista), `TryUnit`, tangentes, deflexiones, continuación, recorrido, elección de accesorio 3D, traza (fusión colineal, prolongaciones, distancia sobre la traza), `CortarTraza`. | 460 |
| `PerfilGrafoCivil.cs` | `internal static partial class PerfilGrafoCivil` | Parte común y gravedad/conduit (C.1, C.2): lectura de `Network`, tubos degenerados, bulge verificado. | 330 |
| `PerfilGrafoPresion.cs` | `partial class PerfilGrafoCivil` | Presión (C.3): sólidos `PDFCAD_FITTING`, asignación 3D, verticales de conexión. | 360 |
| `PerfilCruces.cs` | `internal static class PerfilCruces` | Candidatos a cruce (C.7), agrupación, `AddToProfileView` y etiqueta de cruce. | 360 |
| `PerfilEje.cs` | `internal static class PerfilEje` | Nombre único (con sitios), capa, eje propio, `ReferencePointStation`, estaciones y muestreo del terreno en T0 (D). | 260 |
| `PerfilEstilos.cs` | `internal static class PerfilEstilos` | Capas, linetype, TextStyle, ProfileViewStyle, band set, estilo de terreno, estilos de tubo/estructura, marcador, eje y juegos de etiquetas vacíos (E.1–E.7). | 480 |
| `PerfilEstilosEtiquetas.cs` | `internal static class PerfilEstilosEtiquetas` | Estilos de etiqueta (E.8, E.9), purga de componentes y diagnóstico de fábrica (E.10). | 470 |
| `PerfilVista.cs` | `internal static class PerfilVista` | Perfil de terreno, vistas (una por hoja), rango, apilado, `AddToProfileView` con captura de `ProfileViewPart` y overrides por vista. | 420 |
| `PerfilEtiquetas.cs` | `internal static class PerfilEtiquetas` | Arma `Callout` y `RotuloTramo`; crea, recrea y reescribe las etiquetas nativas con `SetTextComponentOverride`. | 440 |
| `PerfilEtiquetasVista.cs` | `internal static class PerfilEtiquetasVista` | Etiquetas que dependen del rango final (T4/T5): «STATION (FT)», estaciones de extremo, título, recubrimientos, separaciones, límites y orden de dibujo. | 380 |
| `PerfilMaquetacion.cs` | `internal static class PerfilMaquetacion` | Medición (extents → cajas en in), calibración, entrada/salida de `PerfilDiseno`, movimiento, corrección iterativa y verificación. | 460 |
| `PerfilDiseno.cs` | **PURO**, `internal static partial class PerfilDiseno` | Constantes, V/VE, intervalos, métrica, `Maquetar` (bucle F.4), verificaciones (F.9) y calibración (F.10). | 470 |
| `PerfilDisenoFranjas.cs` | **PURO**, `partial class PerfilDiseno` | `Empaquetar1D` ponderado, segmentos por paredes, holgura y reglas «si no cabe» (F.5, F.6, F.8). | 420 |
| `PerfilDisenoFila.cs` | **PURO**, `partial class PerfilDiseno` | Fila de tramos (F.7), recubrimientos, estaciones de extremo, hojas, agrupación de cruces y cota de separación (F.11). | 400 |
| `PerfilTextos.cs` | **PURO** | Formatos, materiales, plantillas en inglés, saneado MText y parser tolerante de XDATA (H). | 360 |
| `PerfilLog.cs` | `internal static class PerfilLog` | Log en `%TEMP%\PDFCAD_Perfil.log` (se sobrescribe en cada ejecución) y lista de avisos. Solo `System.IO`. | 90 |

Los cinco archivos PUROS son `PerfilRecorrido.cs`, `PerfilDiseno*.cs` (3) y `PerfilTextos.cs`. Reglas comunes:
- Solo usan `System`, `System.Collections.Generic`, `System.Globalization` y `System.Linq`.
- Todo es `internal` dentro de `namespace Civil3DBasico`.
- Ninguno lleva un `using Autodesk`.

La decisión 7 («módulo PerfilDiseno») se cumple con una sola clase `PerfilDiseno` repartida en tres archivos parciales.

### A.2 Arnés de pruebas (FUERA de la carpeta del proyecto)

Va fuera para que el glob SDK de `proyecto1.csproj` no lo compile. Ruta: `D:/GVR/Proyectos_DEV/EEUU/pdf-to-cad/API-CIVIL/proyecto1/PerfilPruebas/`.

- `PerfilPruebas.csproj`
  - `Microsoft.NET.Sdk`, `OutputType=Exe`, `TargetFramework=net8.0`, `ImplicitUsings=disable`, `Nullable=disable`.
  - Un `<Compile Include="..\proyecto1\X.cs" />` por cada uno de los cinco archivos puros.
  - Sin referencias Autodesk. No se añade a `proyecto1.sln`.
- `Program.cs`
  - Un método por caso de F.12.
  - `Chequear(bool, string)` acumula los fallos.
  - `return fallos == 0 ? 0 : 1`.
- Ejecución: `dotnet run --project D:/GVR/Proyectos_DEV/EEUU/pdf-to-cad/API-CIVIL/proyecto1/PerfilPruebas -c Release`.

### A.3 Modificados

| Archivo | Cambio |
|---|---|
| `AlineamientosPerfiles.cs` | Se ELIMINA `CrearPerfilRed()` con su `[CommandMethod]`. Se conservan las dos sobrecargas de `CrearAlineamientoDesdePts`, que usa ImportarRed.cs:540 y 2753, y se añade la sobrecarga con capa/estilo/juego (D.2). Arreglo de la polilínea huérfana con el código exacto de D.2. Se corrigen los comentarios de cabecera. |
| `RedesPresionRamales.cs` | Se ELIMINA `CrearPerfilPresion()` (líneas 262-334, `[CommandMethod("CREAR_PERFIL_PRESION")]`), porque dos `CommandMethod` con el mismo nombre rompen la carga. `ElegirRedId` se queda: lo usa RedesPresion.cs. |
| `PanelPipe.xaml` (~174) | `Text="Eje, terreno, tuberías, cruces y rótulos nativos (gravedad, conduit y presión)"`. El botón sigue lanzando `CREAR_PERFIL_RED`. |

Build: `dotnet build -c Release`. La línea base es 0 errores, y no se admite ningún CS0618 nuevo: el setter de `Label.DraggedOffset` está obsoleto y el diseño no lo usa.

### A.4 Eliminados

`PerfilUtil.cs` y `PerfilLongitudinalDatos.cs`. Antes de borrarlos, grep `PerfilUtil|PerfilLongitudinalDatos` debe dar 0 resultados fuera de ellos mismos.

---

## B. Modelo de datos

Unidades:
- Planta y cotas en PIES.
- Diámetros de texto en PULGADAS.
- Ángulos en GRADOS, salvo que se indique radianes.
- Maquetación en PULGADAS DE PLOTEO.

### B.1 `PerfilModelo.cs` (con ObjectId)

```csharp
internal enum TipoRed { Gravedad, Conduit, Presion }
internal enum TipoNodo { Estructura, EstructuraNula, Accesorio, Union, Extremo }
internal enum TipoAccesorio { Ninguno, Codo, Tee, Wye, Cruz }

internal sealed class NodoPerfil {
    public int Id;                                   // = índice en RedPerfil.Nodos = GNodo.Id
    public TipoNodo Tipo;
    public double X, Y;                              // ft planta
    public double ZEje = double.NaN;                 // accesorio: COTA_EJE_FT; resto NaN
    public ObjectId EstructuraId = ObjectId.Null, SolidoId = ObjectId.Null;
    public string Nombre = "";
    public double Rim = double.NaN, Sump = double.NaN;
    public TipoAccesorio Accesorio = TipoAccesorio.Ninguno;
    public double AnguloXData = double.NaN, DiamPrincipalIn = double.NaN, DiamRamalIn = double.NaN;
    public double LargoTotalFt = double.NaN;
    public string MaterialXData = "", RedXData = "";
    public bool RamalVertical; public string SentidoVertical = "";   // "UP" | "DOWN" | "" (H.3)
    public List<int> Tramos = new List<int>();
}

internal sealed class TramoRed {                     // una arista = UNA tubería NO degenerada
    public int Id;
    public ObjectId PipeId; public bool EsPresion;
    public int NodoA, NodoB;                         // A = StartPoint, B = EndPoint
    public Point3d PIni, PFin;                       // eje real (Z = cota de eje)
    public double DiamIn, AltoExtFt, RadioIntFt;     // ver C.2 / C.3
    public string MaterialOriginal = "", Material = "";
    public bool Abandonado;
    public bool Curva; public double Bulge;          // bulge VERIFICADO (C.2-3), sentido Start→End
    public double Longitud2D;
    public string NombreRed = "";
}

internal sealed class VerticalConexion {            // tubo degenerado (conexión vertical), excluido del grafo
    public double X, Y, ZMin, ZMax; public string Red = ""; public ObjectId PipeId;
}

internal sealed class RedPerfil {
    public TipoRed Tipo; public ObjectId RedId; public string NombreRed = "";
    public ObjectId SuperficieId = ObjectId.Null;
    public List<NodoPerfil> Nodos = new List<NodoPerfil>();
    public List<TramoRed> Tramos = new List<TramoRed>();
    public List<VerticalConexion> Verticales = new List<VerticalConexion>();
    public List<GNodo> GNodos = new List<GNodo>();
    public List<GArista> GAristas = new List<GArista>();
}

internal sealed class PasoRecorrido {
    public TramoRed Tramo;
    public bool Invertido;                           // true = se recorre B→A
    public int NodoDesde, NodoHasta;
    public double EstDesde, EstHasta;                // estaciones de los NODOS
    public double EstPIni, EstPFin;                  // estaciones de los extremos reales del tubo (sentido de avance)
    public double ZIni, ZFin;                        // cota de eje en esos extremos (sentido de avance)
}

internal sealed class Ramal {
    public int NodoId; public TramoRed Tramo; public double DiamIn;
    public string Lado = "";                         // "LT" | "RT"
    public double AnguloDeg; public bool EntraAlNodo;
}

internal sealed class Recorrido {
    public RedPerfil Red;
    public List<int> Nodos = new List<int>();                     // orden de estación creciente
    public List<PasoRecorrido> Pasos = new List<PasoRecorrido>();  // Pasos[i]: Nodos[i] → Nodos[i+1]
    public Dictionary<int, double> EstNodo = new Dictionary<int, double>();
    public Dictionary<int, List<Ramal>> Ramales = new Dictionary<int, List<Ramal>>();
    public double EstIni, EstFin;                                 // EstIni = 100.00
    public List<V2Bulge> Traza = new List<V2Bulge>();
    public double DistN0;                                         // distancia sobre la traza hasta N0
    public double[] TerrenoEst = new double[0], TerrenoZ = new double[0]; // D.4 (NaN = sin superficie)
}

internal sealed class Cruce {
    public ObjectId PipeId; public bool EsPresion, EsGravedad; public string Red = "";
    public double Estacion, ZEje, DiamIn, AltoExtFt, RadioIntFt, AnguloDeg, ClaroFt;
    public string Material = ""; public bool Abandonado, Encima;
    public int Grupo = -1; public bool EtiquetaDelGrupo;          // F.11: solo uno por grupo lleva etiqueta
    public List<ObjectId> PvPartIds = new List<ObjectId>();       // uno por hoja en que aparece
    public List<ObjectId> EtiquetaIds = new List<ObjectId>();
}

internal sealed class Callout {
    public string Id = "", Tipo = "";   // "INICIO","FIN","TEE","WYE","CRUZ","CODO","DEFLEXION","REDUCCION","ESTRUCTURA","CRUCE","TERRENO","TRAMO"
    public FranjaTipo Franja; public int Prioridad;
    public bool PuedeCambiarFranja, PuedeAlternar = true, PuedeRecortar;
    public double Estacion, EstAncla, ZAncla;        // Estacion = la del texto; EstAncla/ZAncla = punta de la flecha
    public List<string> Lineas = new List<string>(); // saneadas (H.8)
    public int Hoja;
    public ObjectId EtiquetaId = ObjectId.Null;
    public BloqueTexto Bloque;
}

internal sealed class RotuloTramo {
    public string Id = ""; public double EstIni, EstFin; public string L1 = "", L2 = "", L3 = "";
    public int Hoja; public bool Omitido;
    public ObjectId EtiquetaId = ObjectId.Null; public FilaTramo Fila;
}

internal sealed class HojaPerfil {                   // una ProfileView (F.11 hojas)
    public int Indice; public string Nombre = "";
    public double EstA, EstB;                        // rango de nodos que cubre
    public Point3d Insercion; public ObjectId PvId = ObjectId.Null;
    public ResultadoMaquetacion Prelim, Final;
    public List<Callout> Callouts = new List<Callout>();
    public List<RotuloTramo> Rotulos = new List<RotuloTramo>();
    public List<ObjectId> EtiquetasVista = new List<ObjectId>();  // título, STATION, extremos, profundidades, límites
}

internal sealed class EstilosPerfil {                // ObjectId.Null = no disponible → se omite con aviso
    public ObjectId CapaId, CapaEjeId, VistaStyle, BandSetVacio, TerrenoStyle, LabelSetPerfilVacio, EjeStyle, LabelSetEjeVacio,
        TuboGrav, TuboGravAband, CruceGrav, TuboPres, TuboPresAband, CrucePres, Estructura, SinMarcador,
        CalloutSup, CalloutInf, Tramo, Rasante, Titulo, EstExtremo, EjeTitulo, CruceGravLbl, CrucePresLbl, Profundidad, Limite;
    public string Linetype = "Continuous"; public double LinetypeEscala = 1.0;
    public double FactorPl; public string SufijoPl = "";
}

internal sealed class ResumenPerfil { public int Tubos, Estructuras, Cruces, GruposCruce, Callouts, Rotulos, Profundidades, Hojas; }
```

### B.2 Tipos PUROS del recorrido (`PerfilRecorrido.cs`)

```csharp
internal struct V2 {
    public double X, Y;
    public V2(double x, double y) { X = x; Y = y; }
    public static V2 operator +(V2 a, V2 b) { return new V2(a.X + b.X, a.Y + b.Y); }
    public static V2 operator -(V2 a, V2 b) { return new V2(a.X - b.X, a.Y - b.Y); }
    public static V2 operator *(V2 a, double k) { return new V2(a.X * k, a.Y * k); }
    public double Largo { get { return Math.Sqrt(X * X + Y * Y); } }
    public double Dot(V2 o) { return X * o.X + Y * o.Y; }
    public double Cross(V2 o) { return X * o.Y - Y * o.X; }
    public bool TryUnit(out V2 u) {                 // NUNCA devuelve NaN
        double l = Largo;
        if (l < 1e-9 || double.IsNaN(l)) { u = new V2(0, 0); return false; }
        u = new V2(X / l, Y / l); return true;
    }
}
internal struct V2Bulge { public double X, Y, Bulge; }          // bulge del segmento que EMPIEZA aquí
internal sealed class GNodo { public int Id; public double X, Y; public List<int> Aristas = new List<int>(); }
internal sealed class GArista {
    public int Id, A, B; public double Bulge, Largo;
    public V2 DirSalidaA, DirSalidaB;                            // tangentes unitarias que SALEN de A y de B
    public bool Valida;                                          // false si Largo < 1e-9 o TryUnit falla (C.4)
}
internal sealed class PasoG { public int Arista; public bool Invertida; }
internal sealed class CorteTraza { public double Estacion, AnguloDeg, T; public V2 P; }
internal sealed class CandidatoAccesorio { public int Id; public double X, Y, Z, DiamPrincipalFt, LargoTotalFt; public string Red = ""; }
```

### B.3 Tipos PUROS de maquetación (`PerfilDiseno.cs`)

```csharp
internal enum FranjaTipo { Superior, Inferior }
internal sealed class BloqueTexto {
    public string Id = ""; public FranjaTipo Franja; public int Prioridad = 50;   // también es el PESO del empaquetado
    public bool PuedeCambiarFranja, PuedeAlternar = true, PuedeRecortar;
    public double EstAncla, ZAncla;                  // ft
    public string[] Lineas = new string[0]; public bool Vertical = true;
    public double Ancho, Alto; public bool Medido;   // in: extensión X / Y del bloque de texto (sin leader)
    public double DxEnganche = PerfilDiseno.H_TEXTO; // in: de X0 al punto de enganche del leader (cola de la línea 1)
    // salida
    public FranjaTipo FranjaFinal; public int Nivel = 1; public double X0, Y0;
    public bool Recortado, Descartado;
}
internal sealed class FilaTramo {
    public string Id = ""; public double EstIni, EstFin; public string L1 = "", L2 = "", L3 = "";
    public double KMedida = 1.0;                     // medido/predicho de la variante creada en T1
    // salida
    public bool Omitido, ConLeader, AVertical; public int Fila = 1, NumLineas = 2;
    public double Ancho, Alto, X0, Y0, Cx;
}
internal sealed class CajaDibujo { public string Id = ""; public double EstIni, EstFin, ZMin, ZMax; } // elipses de cruce, en ft
internal sealed class Caja { public string Id = ""; public double X0, Y0, X1, Y1; }
internal sealed class Leader { public string Id = ""; public double X0, Y0, X1, Y1; }  // enganche → ancla (in)
internal sealed class Intervalos { public double EstMayor, EstMenor, CotaMayor, CotaMenor; }
internal sealed class EntradaMaquetacion {
    public double S; public double EstIni, EstFin;           // primer y último nodo de la HOJA
    public double EstMinPermitida, EstMaxPermitida;          // rango del eje (con prolongaciones)
    public double ZMinDibujo, ZMaxDibujo;                    // tubos, cruces, estructuras (SIN terreno)
    public double[] TerrenoEst = new double[0], TerrenoZ = new double[0];  // muestras (NaN admitido)
    public List<BloqueTexto> Bloques = new List<BloqueTexto>();
    public List<FilaTramo> Tramos = new List<FilaTramo>();
    public List<CajaDibujo> CajasDibujo = new List<CajaDibujo>();
    public double? VForzada; public Intervalos IntForzados;  // null = automático
}
internal sealed class ResultadoMaquetacion {
    public double V, VE; public Intervalos Int; public double VRecomendada;
    public double StationStart, StationEnd, ElevationMin, ElevationMax, AnchoMarco, AltoMarco;
    public double HolguraSup, HolguraInf, YBaseSup, YTopeInf, YFila1Base, YFila2Base = double.NaN;
    public List<double> Paredes = new List<double>();        // estaciones de las verticales de límite (fusionadas)
    public List<string> Avisos = new List<string>(), Recortados = new List<string>();
    public List<string> Solapes = new List<string>(), FueraDeMarco = new List<string>();
    public List<string> CrucesLeaders = new List<string>(), CortesLeaderCaja = new List<string>(), PendientesExcedidas = new List<string>();
    public bool SinSolapes;                                  // Solapes, FueraDeMarco y CrucesLeaders vacíos
}
```

---

## C. Algoritmo del recorrido

Constantes: `TOL_COINCIDE = 0.5` ft; `LARGO_MIN_TUBO = 2·TOL_COINCIDE = 1.0` ft (en planta).

### C.1 Identificación de la red (T0)

**De la entidad a la red**
- `Pipe` y `Structure`: `NetworkId` → `Network`.
- `PressurePipe`: `NetworkId`, que hereda de `PressurePart`, → `PressurePipeNetwork`.

**Tubería vertical elegida**
- Condición: `Pipe` o `PressurePipe` con distancia 2D entre `StartPoint` y `EndPoint` menor que `LARGO_MIN_TUBO`.
- Mensaje: «⚠ La tubería seleccionada es vertical (conexión cruzada); seleccione una tubería horizontal.» y return. No se crea nada.

**`TipoRed`**
- Presión si es una `PressurePipeNetwork`.
- En una `Network`: `Conduit` si TODAS sus estructuras son nulas o si no tiene ninguna; si no, `Gravedad`.
- Estructura nula ⇔ `Structure.PartFamilyName.ToLowerInvariant()` contiene `"null"` o `"nula"`. Cada lectura va en su try; si falla, se considera no nula.

**Superficie**
- Se usa `ReferenceSurfaceId` de la red si es válida y es `TinSurface`.
- Si no, la primera `TinSurface` de `civilDoc.GetSurfaceIds()`.
- Si no hay ninguna, `Null`: sin terreno ni recubrimientos, con aviso.

### C.2 Grafo de gravedad y conduit (`PerfilGrafoCivil.ConstruirGravedad`)

1. Por cada id de `net.GetPipeIds()`, abrir la `Pipe` en su try: si falla, aviso y se salta el tubo.
   - Si `dist2D(StartPoint, EndPoint) < LARGO_MIN_TUBO`, se EXCLUYE: log `[GRAFO] tubo degenerado excluido {handle}` y se añade a `Verticales`.
   - Datos:
     - `PIni/PFin`
     - `DiamIn = InnerDiameterOrWidth·12`
     - `AltoExtFt = OuterHeight` si es > 0; si no, `OuterDiameterOrWidth`; como respaldo `DiamIn/12`
     - `RadioIntFt = InnerHeight/2` si es > 0; si no, `InnerDiameterOrWidth/2`
     - `MaterialOriginal = Description`, con respaldo `PartDescription`
     - `Abandonado` ⇔ el nombre del estilo es `"Abandonado (PDFCAD)"`
     - `Longitud2D = Length2DCenterToCenter`, con respaldo `Length2D`
2. Nodos de los extremos:
   - Si `StartStructureId`/`EndStructureId` es válido: un nodo por estructura, con clave `"S:" + handle`. Se toman `Location`, `Name`, `RimElevation` y `SumpElevation`, cada uno en try.
   - Si no hay estructura: agrupar a ≤ `TOL_COINCIDE` en planta. Se crea `Extremo`, y los nodos con ≥ 2 tramos pasan a `Union`.
3. **Bulge verificado** (`SubEntityType`):
   - `Straight` → 0.
   - `Segmented` o `Flex` → cuerda, con log `[GRAFO] tubo {tipo}: se usa la cuerda`.
   - `Curved`:
     - Con `CircularArc2d a = Curve2d; Interval iv = a.GetInterval();`:
       - `Pm = a.EvaluatePoint((iv.LowerBound + iv.UpperBound)/2)`
       - `barrido = a.GetLength(iv.LowerBound, iv.UpperBound) / a.Radius`
       - `|b| = tan(barrido/4)`
       - `signo(b) = signo(Cross(Pm − P0, P1 − Pm))`, con `P0 = PIni`, `P1 = PFin` en 2D. Positivo = giro antihorario.
     - Comprobación pura: `PerfilRecorrido.PuntoMedioArco(P0, P1, b)` debe caer a ≤ 0.1 ft de `Pm`. Si no, cuerda y aviso `[GRAFO] curva no verificada`.
     - Todo va en try; ante una excepción, cuerda.
4. `GArista` = nodo(A) → nodo(B).
   - Lleva el bulge del tubo solo si los dos extremos del tubo están a ≤ 0.5 ft de su nodo; si no, cuerda.
   - `Largo` = distancia 2D (o largo del arco). Si `Largo < 1e-9` o `TryUnit` falla, `Valida = false` y la arista no participa en el recorrido.

### C.3 Grafo de presión (`PerfilGrafoCivil.ConstruirPresion`)

1. **Accesorios.**
   - Recorrer `ModelSpace` con el filtro `id.ObjectClass.DxfName == "3DSOLID"` y leer `WyeSolido.LeerXData(ent)` (app `"PDFCAD_FITTING"`). Se parsea con `PerfilTextos.ParsearXData` (H.6).
   - Se aceptan TODOS los que tengan `COORD_X` y `COORD_Y`. **No se filtra por `RED`**: la TEE de una conexión cruzada lleva `RED=CROSS-CONNECTS` aunque esté sobre la principal (ImportarRed.cs:5175), y el usuario puede haber renombrado la red.
   - Para no recorrer de más, solo se guardan los que caen dentro de la caja envolvente de los tubos de la red, ampliada 10 ft.
   - `CandidatoAccesorio`:
     - `Z = COTA_EJE_FT`; si falta, NaN y log.
     - `DiamPrincipalFt = DIAM_PRINCIPAL_IN/12`
     - `LargoTotalFt = LARGO_TOTAL_FT`, o NaN
     - `Red = RED`
2. **Tubos** (`net.GetPipeIds()` → `PressurePipe`).
   - Se EXCLUYEN los degenerados (`dist2D < LARGO_MIN_TUBO`). Van a `Verticales` con `ZMin/ZMax` de sus extremos: son las conexiones verticales de «CROSS-CONNECTS».
   - Datos:
     - `DiamIn = NominalDiameter·12`
     - `AltoExtFt = OuterDiameter` si es > 0; si no, `NominalDiameter`
     - `RadioIntFt = NominalDiameter/2`
     - `MaterialOriginal = Description`; si viene vacío, `PartDescription`
     - `Abandonado`
     - `Longitud2D = Length2DCenterToCenter`
   - Curva: si `IsCurve`, se parte de `b = Bulge` y se toma `Pm = GetPointAtParameter((StartParam + EndParam)/2)` en try.
     - Si `PuntoMedioArco(P0, P1, b)` está a ≤ 0.1 ft de `Pm`, se usa `b`.
     - Si lo está `−b`, se usa `−b` con log `[GRAFO] bulge de presión invertido`.
     - En cualquier otro caso, cuerda con aviso.
3. **Asignación extremo→accesorio EN 3D** (pura: `PerfilRecorrido.ElegirAccesorio(E, u, dTuboFt, candidatos, nombreRed)` → id o −1).
   - Entradas: `E` = extremo `(x, y, z eje)` y `u` = dirección de salida en planta.
     - Tubo recto: `E − OtroExtremo`.
     - Tubo curvo: la tangente de C.5 invertida.
   - Para cada candidato C:
     - `Dm = max(dTuboFt, C.DiamPrincipalFt)`
     - `Ralc = max(1.5·Dm + 0.75, LargoTotalFt/2 + 0.5)`; si `LargoTotalFt` es NaN, el segundo término no cuenta
     - `d2 = |C.xy − E.xy|`
     - `dz = |C.Z − E.z|`; si `C.Z` es NaN, `dz = 0`
   - C es candidato si se cumple todo esto:
     - `d2 ≤ Ralc`
     - `dz ≤ Dm/2 + 0.5`
     - `d2 ≤ 0.25` **o** el ángulo entre `(C − E).xy` y `u` es ≤ 25°.
   - Elección:
     - Gana el de menor `d3 = √(d2² + dz²)`.
     - Si dos quedan a menos de 0.05 ft en `d3`, se desempata por este orden: `Red` igual al nombre de la red (sin distinguir mayúsculas y con trim), luego `"CROSS-CONNECTS"`, luego el resto.
   - Si el elegido tiene `Red` distinta del nombre de la red: log `[PRESION] accesorio de otra red: {handle} RED={red}`.
   - Los dos extremos de un mismo tubo no pueden ir al mismo accesorio. Si ocurre, el de mayor `d3` se desasigna.
4. **Extremos sin accesorio**: se agrupan si están a ≤ 0.5 ft en planta y `|Δz| ≤ 0.5` → `Union` si hay ≥ 2, `Extremo` si hay 1.
5. **Nodos y aristas**
   - Los accesorios sin ningún tubo asignado se descartan.
   - Nodo `Accesorio` con los datos de la XDATA: `TIPO` (`ELBOW`→Codo, `TEE`→Tee, `WYE`→Wye, `CROSS`→Cruz), `ANGULO`, `DIAM_PRINCIPAL_IN`, `DIAM_RAMAL_IN`, `MATERIAL`, `RED` y `LARGO_TOTAL_FT`.
   - `GArista` va de nodo a nodo. Lleva el bulge del tubo solo si ambos extremos del tubo están a ≤ 0.5 ft de su nodo; si el tubo está recortado a la campana, cuerda. El tubo recortado es colineal con los centros.
   - `Valida` se calcula como en C.2.
6. **Ramal vertical**:
   - Para cada nodo accesorio, se busca una `VerticalConexion` de CUALQUIER red de presión con `dist2D(V, C) ≤ Ralc`. Las verticales de las otras redes se reúnen en T0 durante la pasada de cruces (C.7).
   - Si existe: `RamalVertical = true`.
   - `SentidoVertical`:
     - `"UP"` si `V.ZMax > ZEje + 0.5`
     - si no, `"DOWN"` si `V.ZMin < ZEje − 0.5`
     - si no, `""`

### C.4 Continuación y recorrido (PURO)

Constantes: `DEFLEXION_MAX_DEG = 45`, `EMPATE_DEG = 10`.

```csharp
internal static double Deflexion(V2 dirLlegada, V2 dirSalida);        // 0..180 ; NaN si alguno no es unitario válido
internal static double AnguloFirmado(V2 dirLlegada, V2 dirSalida);    // (−180,180], + = izquierda
internal static int? Continuacion(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int nodo, int aristaLlegada, V2 dirLlegada, ISet<int> usadas);
internal static List<PasoG> Recorrer(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int aristaInicial);   // vacío si !a[aristaInicial].Valida
internal static List<PasoG> RecorrerDesdeNodo(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int nodo);
```

**Continuación**
- `dirLlegada` = `−DirSalida(n, e)`.
- `Continuacion`:
  - Candidatos: aristas `Valida` de `n`, distintas de la de llegada y no usadas.
  - Para cada una, `δ = Deflexion(...)`. Se descarta si `double.IsNaN(δ)`, nunca se ordena un NaN.
  - Se ordena con un comparador explícito: δ ascendente y, a igualdad, `Id`.
  - Devuelve null si no hay candidatos, si `δmin > 45` o si `δ2 − δmin < 10`. Si no, la de δmin.

**Recorrido**
- `Recorrer(e0)` avanza desde `e0.B` y retrocede desde `e0.A`. Se para al volver a un nodo ya visitado (lazo).
- `RecorrerDesdeNodo(n)`:
  - Con ≥ 2 aristas: el par con menor deflexión. Si esa δ > 45°, solo la arista más larga.
  - Con 1 arista: esa arista.
  - Con 0: vacío, con el mensaje «La estructura no tiene tuberías».

**Sentido de las estaciones** (1+00 al inicio):
- Gravedad: empieza en el extremo de MENOR invert (`z eje − RadioIntFt`).
- Conduit y presión: empieza en el extremo más al OESTE. Si `|ΔX| < 0.3·|ΔY|`, en el más al SUR.

**Ramales**
- En cada nodo interior, las aristas `Valida` que quedan fuera del recorrido:
  - `Lado`: `AnguloFirmado > 0` → `"LT"`; si no, `"RT"`.
  - `AnguloDeg` = la deflexión.
  - `EntraAlNodo` (solo gravedad): el invert del extremo lejano es mayor que el del nodo.
- En los nodos extremos, todas las aristas sin usar.

### C.5 Tangentes y traza (PURO)

**Tangentes**
- Segmento P0→P1 con bulge `b`:
  - `c = unit(P1 − P0)`, `θ = 4·atan(b)`.
  - Tangente de salida en P0 = `rot(c, −θ/2)`; de llegada en P1 = `rot(c, +θ/2)`.
  - Ejemplo: (0,0)→(10,10) con `b = tan 22.5°` da `t0 = (1,0)` y `t1 = (0,1)`.
- `DirSalidaA = t0`, `DirSalidaB = −t1`. Recorrido invertido → `−b`.
- `PuntoMedioArco(P0, P1, b)` = punto medio de la cuerda desplazado `s = b·|P1−P0|/2` hacia la izquierda de `c` (b > 0: antihorario).

**Traza.** `internal static List<V2Bulge> Traza(List<V2> nodos, List<double> bulges, double ext)`:
- Vértices `[N0 − t0·ext, N0, …, Nk, Nk + tk·ext]` y bulges `[0, b0, …, b(k−1), 0]`.
- Limpieza, en este orden:
  1. Se fusionan los vértices consecutivos a menos de 0.01 ft; se conserva el bulge no nulo. Log `[GRAFO] conexión vertical` si los fusionados eran dos nodos distintos.
  2. Se elimina todo vértice interior con deflexión < 1e-6 rad cuyos segmentos adyacentes tengan ambos bulge 0 (colineal). Las estaciones de los nodos salen de `StationOffset`, así que no se pierden.
  3. Si quedan menos de 2 vértices, error «✗ No se pudo formar la traza del eje».
- `ext = EXT_EJE = max(25, PAD_MAX·S + 10)` ft. `ReferencePointStation` puede quedar negativa (se admite; el eje va en su propia capa, D.2).

**Utilidades puras**
- `LargoTraza(traza)`.
- `PuntoEnTraza(traza, dist) → V2`.
- `DistanciaEnTraza(traza, V2 p) → double`: proyección sobre el segmento más cercano; en arcos, 16 cuerdas.

### C.6 Deflexiones y clasificación de los nodos interiores

- `δh = Deflexion` en planta.
- `δv = |atan(sOut) − atan(sIn)|`, con `s = (ZFin − ZIni)/max(Longitud2D, 0.01)`.
- Vertical dominante ⇔ `δv > δh`.
- Un nodo va sin callout si `max(δh, δv) < UMBRAL` (1.0° en presión, 2.0° en conduit) y además mantiene el diámetro y no tiene ramal vertical.

### C.7 Cruces (`PerfilCruces` + PURO `CortarTraza`)

```csharp
internal static List<CorteTraza> CortarTraza(List<V2Bulge> traza, double estPrimerVertice, V2 a, V2 b);
// arcos de la traza discretizados en 16 cuerdas; si |b − a| < 1e-9 devuelve lista vacía (sin división por cero)
```

**Candidatos**
- Todas las tuberías de `civilDoc.GetPipeNetworkIds()` y de `CivilDocumentPressurePipesExtension.GetPressurePipeNetworkIds(civilDoc)`. Se excluyen:
  - las del recorrido;
  - las degeneradas (`dist2D < LARGO_MIN_TUBO`). De paso, estas alimentan las `VerticalConexion` de C.3-6;
  - las que tienen un extremo a ≤ 0.5 ft en planta de un nodo del recorrido (tocan, no cruzan).
- Un tubo curvo se trata como 8 cuerdas.

**Cortes**
- Filtro: `AnguloDeg ≥ 15°` y `EstIni + 0.5 ≤ Estacion ≤ EstFin − 0.5`.
- Un solo corte por tubo.
- `ZEje` se interpola por largo 2D.
- `Encima` = `ZEje > ZEjeRecorrido(Estacion)`.
- Claro:
  - si el cruce va debajo: `ClaroFt = (ZEjeRec − AltoExtRec/2) − (ZEje + AltoExt/2)`;
  - si va encima: `ClaroFt = (ZEje − AltoExt/2) − (ZEjeRec + AltoExtRec/2)`.
- Estación preliminar en T0 (distancia sobre la traza, D.3). En T1 se toma la definitiva con `StationOffset`; si `|off| > 0.1` ft, log.
- Agrupación: F.11 (`AgruparCruces`).

---

## D. Eje propio

### D.1 Nombre único (`PerfilEje.NombreUnico`)

1. `red = Sanear(NombreRed)`: cada carácter de ``<>/\":;?*|,=` `` se sustituye por `-` y se hace trim.
2. Se reúnen los nombres usados, cada lectura en su try:
   - `Name` de todos los ejes de:
     - `civilDoc.GetAlignmentIds()`
     - `civilDoc.GetSitelessAlignmentIds()`
     - `GetAlignmentIds()` de cada `Site` de `civilDoc.GetSiteIds()`
   - Más el `Name` de las `ProfileView` de cada uno (`alignment.GetProfileViewIds()`).
3. Se prueba `n = 1, 2, …` hasta que `"PERFIL " + red + " (" + n + ")"` no esté usado Y ningún nombre usado empiece por ese nombre seguido de `" - H"`.
4. Nombres:
   - Eje y vista de la hoja 1: `nombre`.
   - Hojas siguientes: `nombre + " - H" + (k+1)`.
   - Terreno: `nombre + " - EX. GRADE"`.
   - `n` numera el título (`PROFILE {n}`).

### D.2 Creación del eje

Nueva sobrecarga en `ComandosAlineamientos` (AlineamientosPerfiles.cs):

```csharp
public static ObjectId CrearAlineamientoDesdePts(Database db, CivilDocument civilDoc, Transaction tr,
    List<ComandosRedes.TrazaPt> pts, string nombre, ObjectId layerId, ObjectId styleId, ObjectId labelSetId)
{
    Polyline pl = null;                                   // declarada FUERA del try (arreglo del huérfano)
    try {
        var btr = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
        pl = new Polyline();
        for (int i = 0; i < pts.Count; i++) pl.AddVertexAt(i, new Point2d(pts[i].P.X, pts[i].P.Y), pts[i].Bulge, 0, 0);
        btr.AppendEntity(pl); tr.AddNewlyCreatedDBObject(pl, true);
        var opt = new PolylineOptions { PlineId = pl.ObjectId, AddCurvesBetweenTangents = false, EraseExistingEntities = true };
        return CivilDB.Alignment.Create(civilDoc, opt, nombre, ObjectId.Null, layerId, styleId, labelSetId);
    } catch (Exception ex) {
        try { if (pl != null && !pl.IsErased) { if (!pl.IsWriteEnabled) pl.UpgradeOpen(); pl.Erase(); } } catch { }
        // (log / mensaje igual que la versión existente)
        return ObjectId.Null;
    }
}
```

- Los nombres de campo de `TrazaPt` se ajustan a los del struct real (ImportarRed.cs:5736).
- La sobrecarga existente de 5 argumentos llama a esta con `db.Clayer`, `AlignmentStyles[0]` y `AlignmentLabelSetStyles[0]`. El comportamiento de ImportarRed queda igual.
- Firma verificada: `static ObjectId Alignment.Create(CivilDocument, PolylineOptions, String, ObjectId siteId, ObjectId layerId, ObjectId styleId, ObjectId labelSetId)`.

`PerfilEje.Crear` (T1a):
1. Capa **`PDFCAD_PERFIL_EJE`** (ACI 6), separada de `PDFCAD_PERFIL`: así congelar la capa de la vista no oculta el eje, y al revés.
2. `id = CrearAlineamientoDesdePts(..., CapaEjeId, EjeStyle, LabelSetEjeVacio)`.
   - Si devuelve Null: reintento con `AlignmentStyles[0]` y `AlignmentLabelSetStyles[0]`.
   - Si vuelve a dar Null: error fatal «✗ No se pudo crear el eje del perfil». Se aborta T1a.
3. `Alignment` ForWrite:
   - `s0` = estación de N0 con `StationOffset(N0.X, N0.Y, ref s, ref o)`, leída antes del cambio.
   - `ReferencePointStation = 100.0 − (s0 − StartingStation)`.
4. Comprobación: `StationOffset(N0)` debe dar 100.00 ± 0.01. Si no, log `[EJE]`.

Firmas:
- `prop Double ReferencePointStation {get;set;}`
- `Void StationOffset(Double, Double, Double&, Double&)`
- `Void StationOffsetAcceptOutOfRange(Double, Double, Double&, Double&, Boolean&)`
- `StartingStation`/`EndingStation {get;}`

### D.3 Estaciones

**T0 (preliminar, pura)**
- `est(P) = 100 + DistanciaEnTraza(traza, P) − DistN0`.
- Se calcula para nodos, extremos de tubo y cortes.
- Con estas estaciones se hace la maquetación preliminar.

**T1a (definitiva)**
- Se usa `StationOffset` sobre el eje nuevo para los mismos puntos. Si lanza, `StationOffsetAcceptOutOfRange` con aviso.
- Si difiere de la preliminar en más de 0.05 ft: log `[EJE] estación {id}: {pre} → {def}`.
- A partir de aquí, TODO usa las definitivas.

**Otras reglas**
- Monotonía: `EstNodo` debe crecer estrictamente. Si no crece (problema numérico), se usa la distancia acumulada sobre la traza + 100, con aviso.
- `EstMinPermitida = StartingStation`, `EstMaxPermitida = EndingStation`.
- `ZEjeRecorrido(e)`:
  - Dentro de un tubo: interpolación lineal entre `(EstPIni, ZIni)` y `(EstPFin, ZFin)`.
  - En el hueco hasta el centro de un accesorio: lineal hasta `(EstNodo, ZEje del nodo)`; si es NaN, se prolonga la cota del extremo.
- Corona = `ZEje + AltoExtFt/2`. Fondo exterior = `ZEje − AltoExtFt/2`.

### D.4 Terreno muestreado en T0 (sin `Profile.ElevationAt`)

- Si hay superficie: `Surface.FindElevationAtXY(x, y)` (firma verificada: `Double FindElevationAtXY(Double x, Double y)` en `CivilDB.Surface`).
- Se muestrea cada `PASO_TERRENO = 2` ft de distancia sobre la traza, en `[EstMinPermitida, EstMaxPermitida]`, usando `PuntoEnTraza`.
- Cada llamada va en su try: si lanza (hueco de la superficie), la muestra queda en NaN.
- Si todas salen NaN: se trata como «sin superficie» (aviso) y no se crea el perfil de terreno.
- Las muestras (`TerrenoEst/TerrenoZ`) alimentan:
  - la maquetación, que solo usa las que caen en `[StationStart, StationEnd]` (F.4-4);
  - el ancla de EX. GRADE;
  - los recubrimientos.

---

## E. Estilos

**Helper `Asegurar(StyleCollectionBase col, string nombre, Transaction tr, out bool nuevo)`**
- Si `col.Contains(nombre)`, devuelve `col[nombre]`.
- Si no, busca la BASE: el primer estilo de `col` cuyo `Name` NO empiece por `"PDFCAD"`. Hace `((StyleBase)tr.GetObject(base, ForRead)).CopyAsSibling(nombre)`.
- Si no hay base, `col.Add(nombre)`.

**Reglas comunes**
- El estilo se abre **ForWrite** antes de cualquier `Set`.
- Idempotencia: si ya existe, no se recrea pero se REAPLICAN todas las propiedades.
- Cada set va dentro de `Set("prop", () => …)`, que captura la excepción y registra `[ESTILO] <estilo>.<prop>: <msg>`.
- **Nunca se modifica un estilo cuyos parámetros de nombre no coinciden.** Los que dependen de algo lo llevan en el nombre: VE e intervalos (vista), `S` (linetype) y `SufijoPl` (alturas).
- `SufijoPl` = `""` si `FactorPl` es el inicial; si no, `" P" + FactorPl.ToString("G4", CultureInfo.InvariantCulture)`.

**Colores y grosores**
- Colores: `Color.FromColorIndex(ColorMethod.ByAci, n)`: 7 negro/blanco, 8 gris, 253 gris claro, 6 magenta (eje).
- Grosores: `LineWeight.LineWeight050/035/025/018/013`.

### E.1 Recursos base

**Capas `PDFCAD_PERFIL` (ACI 7) y `PDFCAD_PERFIL_EJE` (ACI 6)**
- `LayerTable` se abre ForWrite para el `Add`.
- Si ya existen: `IsFrozen=false` e `IsLocked=false`.

**TextStyle `PDFCAD_PERFIL`**
- `romans.shx`, `TextSize=0`, `XScale=1.0`.
- Si ya existe, se deja como está.

**Linetype discontinuo**
- Orden de búsqueda: `DASHED` → `TRAZOS` → `HIDDEN` → `"L\u00CDNEAS_OCULTAS"` → `ACAD_ISO02W100`.
- Para cada nombre: si `Has` lo encuentra, se usa. Si no, `try LoadLineTypeFile(n, "acad.lin")`, luego `"acadiso.lin"`, y se vuelve a comprobar con `Has`.
- Si ninguno está disponible: `"Continuous"` con aviso.
- Largo de trazo del patrón `g`:

  | Linetype | `g` |
  |---|---|
  | DASHED | 0.5 |
  | TRAZOS | 0.5 |
  | HIDDEN | 0.25 |
  | LÍNEAS_OCULTAS | 0.25 |
  | ACAD_ISO02W100 | 12 |

- `LinetypeEscala = 0.25·S/(g·db.Ltscale)`.

### E.2 `ProfileViewStyle` (`Styles.ProfileViewStyles`)

Nombre: `"PDFCAD Perfil VE{VE} E{CotaMayor}-{CotaMenor} S{EstMayor}{SufijoPl}"`, con números en `G` invariante.

**Creación**
- `Asegurar` (CopyAsSibling de la base de fábrica): así hereda el `LabelText` de las estaciones.
- Se registra el `LabelText` de fábrica de los tres ejes. Si contiene letras fuera de un token `<[…]>` (regex `<\[[^\]]*\]>`), se reescribe con solo los tokens concatenados y se registra `[ESTILO] LabelText saneado`.

**GraphStyle, GridStyle y ejes**
- `GraphStyle`:
  - `VerticalExaggeration = VE`, `Direction = LeftToRight`
  - `TitleStyle.Text = ""`
- `GridStyle`:
  - `GridPadding*` = 0 y `AxisOffset*` = 0
  - en `HorizontalGridOptions` y `VerticalGridOptions`: `UseClipGrid = false`, `ClipToHighestProfile = false`, `OmitGridInPaddingAreas = true`
- `BottomAxis`:
  - `ShowTickAndLabel = true`
  - `MajorTickStyle`: `Interval = EstMayor`, `TextHeight = Pl(0.10)`, `Size = Pl(0.05)`, `TextStyle = "PDFCAD_PERFIL"`. No se tocan `OffsetX/OffsetY/Rotation/Justification`: solo se registran.
  - `MinorTickStyle.Interval = EstMenor`
  - `TitleStyle.Text = ""`: «STATION (FT)» lo pone una etiqueta propia (E.8) para poder medir los números del eje (G.11).
- `LeftAxis` y `RightAxis`:
  - `ShowTickAndLabel = true`
  - `MajorTickStyle`: `Interval = CotaMayor`, `TextHeight = Pl(0.10)`, `Size = Pl(0.05)`, `TextStyle`
  - `MinorTickStyle.Interval = CotaMenor`
  - `TitleStyle`: `Text = "ELEVATION (FT)"`, **`TextHeight = Pl(0.10)`** (igual que los números), `TextStyle`, `Location = AxisTitleLocationType.Center`
- `TopAxis`:
  - `ShowTickAndLabel = false`, `TitleStyle.Text = ""`
  - `Interval`s como en `BottomAxis`

**Visibilidad** (`GetDisplayStylePlan(ProfileViewDisplayStyleType.X)`)

| Encendido | Color | Grosor | Linetype |
|---|---|---|---|
| `LeftAxis`, `RightAxis`, `BottomAxis`, `TopAxis` | 7 | 050 | Continuous |
| `LeftAxisTitle`, `RightAxisTitle` | 7 | 018 | — |
| `LeftAxisAnnotationMajor`, `RightAxisAnnotationMajor`, `BottomAxisAnnotationMajor` | 7 | 018 | — |
| `LeftAxisTicksMajor`, `RightAxisTicksMajor`, `BottomAxisTicksMajor` | 7 | 025 | Continuous |
| `GridHorizontalMajor` | 7 | 035 | Continuous |
| `GridHorizontalMinor` | 253 | 013 | Continuous |
| `GridVerticalMajor` | 7 | 025 | Continuous |

Apagados:
- `GraphTitle`, **`BottomAxisTitle`**, `TopAxisTitle`
- `TopAxisAnnotationMajor/Minor`, `TopAxisTicksMajor/Minor`
- los `…AnnotationMinor` y `…TicksMinor` de los ejes izquierdo, derecho e inferior
- `GridVerticalMinor`, `GridAtHGP`
- `Top/BottomAxisAnnotationHGP`, `Top/BottomAxisTicksHGP`
- `GridAtSampleLineStations`, `ProfileHatch`

### E.3 Band set vacío (`Styles.ProfileViewBandSetStyles`)

- `"PDFCAD Perfil Sin bandas"`, con `Contains ? [n] : Add(n)`.
- Tras crear la vista, con `pv` ForWrite: `GetTopBandItems()`/`GetBottomBandItems()`, `RemoveAt` de atrás hacia delante y `SetTopBandItems`/`SetBottomBandItems`.

### E.4 Terreno (`Styles.ProfileStyles`)

- Nombre `"PDFCAD Perfil Terreno S{S}"`, con `Asegurar`.
- `GetDisplayStyleProfile(ProfileDisplayStyleProfileType.X)`:
  - `Line`, `Curve`, `SymmetricalParabola` y `AsymmetricalParabola`: visibles, color 8, grosor 025, `Linetype` y `LinetypeScale`.
  - `Arrow`, `LineExtension`, `ParabolicCurveExtension` y `WarningSymbol`: ocultos.
- Todos los `*MarkerStyle` = `SinMarcador`.
- Juego de etiquetas: `LabelSetStyles.ProfileLabelSetStyles`, `"PDFCAD Perfil Sin etiquetas"` (`Contains ? [n] : Add(n)`). Se abre ForWrite y se vacía con `while (s.Count > 0) s.RemoveAt(s.Count - 1);`. `BaseLabelSetStyle.Count` y `RemoveAt(Int32)` están verificados.

### E.5 Eje (`Styles.AlignmentStyles`)

- `"PDFCAD Perfil Eje"`, con `Asegurar`.
- `GetDisplayStylePlan(AlignmentDisplayStyleType.Line/Curve/Spiral)`: visibles, color 6, grosor 018.
- `Arrow`, `LineExtensions`, `CurveExtensions`, `TangentExtensions` y `WarningSymbol`: ocultos.
- Juego de etiquetas: `AlignmentLabelSetStyles`, `"PDFCAD Perfil Sin etiquetas"`, vaciado igual que en E.4.

### E.6 Estilos de tubo y estructura (override por vista)

Colecciones: gravedad en `Styles.PipeStyles`; presión en `StylesRootPressurePipesExtension.GetPressurePipeStyles(civDoc.Styles)`.

| Nombre | Profile encendidos (color/grosor/linetype) | Apagados |
|---|---|---|
| `"PDFCAD Perfil Tubo"` | `OutsideWalls` 7/050/Continuous; `EndLine` 7/025; `CrossingPipeOutsideWall` 7/035 | `Centerline`, `InsideWalls`, `Hatch`, `CrossingPipeInsideWall`, `CrossingPipeHatch`; en gravedad también `HydraulicGradeLine` y `EnergyGradeLine` |
| `"PDFCAD Perfil Tubo Abandonado S{S}"` | `OutsideWalls` 7/025/discontinuo (con escala); `EndLine` 7/018; `CrossingPipeOutsideWall` 7/025/discontinuo | ídem |
| `"PDFCAD Perfil Cruce"` | `CrossingPipeOutsideWall` 7/035; `OutsideWalls` 8/025; `EndLine` 8/018 | ídem |

- `ProfileOption`: `WallSizeType = UsePartDimensions`, `EndSizeType = DrawToOuterWall`.
- `"PDFCAD Perfil Estructura"` (`Styles.StructureStyles`):
  - `Structure` 7/035, visible.
  - `StructureHatch` y `StructurePipeOutlines`: ocultos.
  - `ViewOptions = DisplayAsBoundary`, `MaskConnectedObjects = false`.
- Los overrides se aplican en T1b (G.5). El `StyleId` del modelo NO se toca.

### E.7 Marcador invisible (`Styles.MarkerStyles`, `"PDFCAD Perfil Sin marcador"`)

- `MarkerType = UseCustomMarker`, `CustomMarkerStyle = CustomMarkerBlank`, `CustomMarkerSuperimposeStyle = None`.
- `SizeType = DrawingScale`, `MarkerSize = Pl(0.01)`.
- `GetMarkerDisplayStylePlan()`, `…Model()`, `…Profile()` y `…Section()` con `Visible = false`.

### E.8 Estilos de etiqueta (helper `AsegurarEstiloTexto`)

```csharp
static ObjectId AsegurarEstiloTexto(LabelStyleCollection col, string nombre, Transaction tr, ConfigTexto cfg, EstilosPerfil est);
sealed class ConfigTexto {
    public bool Vertical; public LabelTextAttachmentType Attachment; public double AltoIn = 0.12;
    public bool Leader = true; public bool JustificarLeader = true;
}
```

1. **Id**: `Asegurar` (base ≠ PDFCAD). Estilo ForWrite.
2. **Purga SIEMPRE** (sea nuevo o no): para cada `LabelStyleComponentType` con `IsSupportedComponent`, se leen los nombres de `GetComponents(t)` y se ejecuta `RemoveComponent(name)` en todo componente cuyo `Name` no sea `"PDFCAD_TEXTO"`. Así un estilo que quedó a medias en una ejecución anterior converge.
3. **Componente `"PDFCAD_TEXTO"`**. Si no existe, `AddComponent("PDFCAD_TEXTO", LabelStyleComponentType.Text)` y se vuelve a buscar por `Name`. Se abre ForWrite:
   - `General.Visible = true`
   - `Text.Contents = "X"` (texto de relleno)
   - `Text.Height = Pl(cfg.AltoIn)`
   - `Text.Angle = cfg.Vertical ? Math.PI/2 : 0`
   - `Text.Attachment = cfg.Attachment`
   - `Text.XOffset = 0`, `Text.YOffset = 0`, `Text.MaxWidth = 0`
   - `Text.Color = 7`
   - `Border.Visible = false`, `Border.BackgroundMask = true`, `Border.Gap = Pl(0.02)`
4. **`ls.Properties`**:
   - `Label.TextStyle = "PDFCAD_PERFIL"`, `Label.Layer = "PDFCAD_PERFIL"`, `Label.Visibility = true`
   - `Behavior.OrientationReference = View`
   - `PlanReadability.PlanReadable = false`
   - `Leader`:
     - `Visibility = cfg.Leader`. Debe ser true para poder mostrarlo: por etiqueta solo existen `FromLabelStyle` y `AlwaysHide`, lo verifiqué.
     - `ArrowheadSize = Pl(0.08)`, `Shape = Straight`, `Lineweight = 018`, `Color = 7`
     - `ArrowheadStyle`: se conserva el heredado. Si el estilo salió de `Add`, se copia el de la base.
   - `DraggedStateComponents`:
     - `DisplayType = Composed`, `BorderVisibility = false`, `UseBackgroundMask = true`
     - `Gap = Pl(0.02)`, `TextHeight = Pl(cfg.AltoIn)`, **`MaxTextWidth = 0`**
     - `LeaderAttachment = LeaderMiddleOfTopLine`
     - **`LeaderJustification = cfg.JustificarLeader`**. Es true en los verticales y false en los horizontales (I-19).

**Estilos** (`LabelStyles = civDoc.Styles.LabelStyles`; todos con `+ SufijoPl` en el nombre):

| Nombre | Colección | Vertical | Attachment | Alto | Leader | Justif. |
|---|---|---|---|---|---|---|
| `PDFCAD Perfil Callout Sup` | `ProfileViewLabelStyles.StationElevationLabelStyles` | sí | `MiddleLeft` | 0.12 | sí | true |
| `PDFCAD Perfil Callout Inf` | ídem | sí | **`MiddleLeft`** (izquierda, base común abajo: 51.png) | 0.12 | sí | true |
| `PDFCAD Perfil Rasante` | ídem | sí | `MiddleLeft` | 0.12 | sí (recto) | true |
| `PDFCAD Perfil Tramo` | ídem | no | `BottomCenter` | 0.12 | sí (oculto por etiqueta salvo fila 2) | false |
| `PDFCAD Perfil Titulo` | ídem | no | `TopLeft` | 0.20 | no | false |
| `PDFCAD Perfil Estacion Extremo` | ídem | no | `BottomCenter` | 0.10 | no | false |
| `PDFCAD Perfil Eje Titulo` («STATION (FT)») | ídem | no | `TopCenter` | 0.10 | no | false |
| `PDFCAD Perfil Cruce` | `PipeLabelStyles.CrossProfileLabelStyles` | sí | `MiddleLeft` | 0.12 | sí | true |
| `PDFCAD Perfil Cruce` | `LabelStylesRootPressurePipesExtension.GetPressurePipeLabelStyles(LabelStyles).CrossingProfileLabelStyles` | sí | `MiddleLeft` | 0.12 | sí | true |

Todos llevan offsets 0: la posición final siempre sale del arrastre medido (G.10–G.11).

### E.9 Estilos de profundidad (`ProfileViewLabelStyles.DepthLabelStyles`)

**`"PDFCAD Perfil Profundidad{SufijoPl}"`**
- `Asegurar` (CopyAsSibling de la base ≠ PDFCAD). Si la colección está vacía, no hay recubrimientos ni separaciones, y se avisa.
- No se purgan los componentes.
- En cada componente de texto:
  - se registra `Contents`;
  - se extraen los tokens `<\[[^\]]*\]>` y se escribe `Contents.Value` = tokens concatenados, sin literales en español ni prefijo; en las referencias solo aparece el valor («5.83'»). Si no hay ningún token, se deja como está y se avisa `[ESTILO] Contents sin token`;
  - `Height = Pl(0.12)`, `Border.BackgroundMask = true`, `Border.Gap = Pl(0.02)`.
- En cada componente de línea: grosor 018.
- `Label.TextStyle` y `Label.Layer` = `PDFCAD_PERFIL`.

**`"PDFCAD Perfil Limite{SufijoPl}"`**
- Misma base.
- Todos los textos con `General.Visible = false`.
- Líneas con grosor 018 y color 7.
- Se usa para las verticales de límite de tramo.

### E.10 Diagnóstico (log, T1a)

Todo se lee de la PRIMERA base ≠ PDFCAD de cada colección:
- Configuración:
  - `DrawingScale`, `DrawingUnits`
  - `db.Cannoscale.Name/Scale/PaperUnits/DrawingUnits`, `db.Ltscale`
- `ProfileViewStyle` de fábrica:
  - `GraphStyle.CurrentHorizontalScale` y `VerticalExaggeration`
  - `BottomAxis.MajorTickStyle.{TextHeight, Size, OffsetX, OffsetY, Rotation, Justification, LabelText}`
  - `LeftAxis.TitleStyle.{TextHeight, Rotation, OffsetX, OffsetY}`
- `StationElevationLabelStyles[base]`, primer texto: `{Contents, Height, Angle, Attachment, AnchorComponent, AnchorLocation}`.
- Leader: `{ArrowheadStyle, ArrowheadSize, Shape}`.
- `DraggedStateComponents.{DisplayType, LeaderAttachment, LeaderJustification}`.
- `DepthLabelStyles[base]`: `Contents`.
- `FactorPl` inicial y su origen (I-1).

---

## F. Maquetación — `PerfilDiseno` (PURO)

### F.1 Constantes (pulgadas de ploteo salvo indicación)

```csharp
internal static partial class PerfilDiseno {
    public const double H_TEXTO = 0.12, H_NUM = 0.10, H_TITULO = 0.20;
    public const double PASO_LINEA = 0.20, ANCHO_CAR = 0.79;
    public const double GAP = 0.15, MARGEN_MARCO = 0.10, MARGEN_PARED = 0.05;
    public const double HOLGURA_DIBUJO = 0.20, HOLGURA_MAX = 1.50, PENDIENTE_LEADER_MAX = 1.7; // |dx|/dy ≈ 60°
    public const double SEP_FILA = 0.10, SEP_FILAS = 0.10, BASE_TEXTO_FILA = 0.05, MARGEN_CELDA = 0.10;
    public const double FRANJA_INF_MIN = 0.50, SEP_NIVEL = 0.10, HUECO_LEADER_MIN = 0.30;
    public const double PAD_MIN = 1.5, PAD_MAX = 4.0, SOBRANTE_MAX_ELEVMIN = 0.75;
    public const double ALTO_MAX_DIBUJO = 8.0, ALTO_MAX_MARCO = 12.0, ANCHO_MAX_MARCO = 30.0;
    public const double FUSION_PAREDES = 0.15, TRAMO_MIN_IN = 0.25, TRAMO_MIN_FT = 2.0;
    public const double TOL_SOLAPE = 0.02, TOL_CORRECCION = 0.02;
    public const double REDONDEO_EST = 5.0;                        // ft
    public static readonly double[] V_ESTANDAR = { 1, 2, 2.5, 4, 5, 10, 20, 25, 40, 50, 100 };
}
```

### F.2 API pública exacta

```csharp
// PerfilDiseno.cs
public static double ElegirV(double s);                                    // F.3
public static double SiguienteV(double v, double s);                       // F.3
public static Intervalos ElegirIntervalos(double s, double v);             // F.3
public static double AnchoBloqueVertical(int lineas, double h = H_TEXTO); // h + (n−1)·PASO_LINEA
public static double LargoLinea(string texto, double h = H_TEXTO);        // LongitudVisible·ANCHO_CAR·h
public static int LongitudVisible(string texto);                           // "%%d" cuenta 1; "\\P", "\\{", "\\}", "\\\\" cuentan 0/1/1/1
public static void PredecirBloque(BloqueTexto b);                          // vertical: Ancho = AnchoBloqueVertical(n), Alto = max LargoLinea
public static void PredecirTramo(FilaTramo t, int numLineas);              // horizontal: Ancho = max LargoLinea, Alto = h+(n−1)·PASO_LINEA (×KMedida)
public static double RedondearAbajo(double v, double paso);                // floor(v/paso + 1e-9)·paso
public static double RedondearArriba(double v, double paso);               // ceil(v/paso − 1e-9)·paso
public static ResultadoMaquetacion Maquetar(EntradaMaquetacion e);          // F.4
public static List<Caja> CajasFinales(EntradaMaquetacion e, ResultadoMaquetacion r);    // bloques + tramos (no descartados/omitidos)
public static List<Leader> LeadersFinales(EntradaMaquetacion e, ResultadoMaquetacion r);// F.9
public static List<Caja> CajasDeDibujo(EntradaMaquetacion e, ResultadoMaquetacion r);   // elipses de cruce en in
public static List<string> Solapes(IReadOnlyList<Caja> c, double tol = TOL_SOLAPE);    // "idA|idB"
public static bool Solapan(Caja a, Caja b, double tol);
public static List<string> FueraDeMarco(IReadOnlyList<Caja> c, double ancho, double alto, double margen = MARGEN_MARCO, double tol = TOL_SOLAPE);
public static List<string> CrucesLeaders(IReadOnlyList<Leader> l);                     // "idA|idB"
public static List<string> CortesLeaderCaja(IReadOnlyList<Leader> l, IReadOnlyList<Caja> c); // "leader|caja" (excluye la propia)
public static List<string> PendientesExcedidas(IReadOnlyList<Leader> l, double max = PENDIENTE_LEADER_MAX);
public static double Calibrar(IReadOnlyList<double> medidos, IReadOnlyList<double> predichos, out double dispersion); // F.10
// PerfilDisenoFranjas.cs
public static List<double> Empaquetar1D(IReadOnlyList<double> ideal, IReadOnlyList<double> anchos, IReadOnlyList<double> pesos,
                                        double gap, double min, double max, out double desborde);   // F.5 (pesos null = 1)
// PerfilDisenoFila.cs
public static List<double> ElegirEstacionesRecubrimiento(double estIni, double estFin, double s,
        IReadOnlyList<double[]> ocupadosLeader, IReadOnlyList<double[]> ocupadosCruce, double estCoberturaMin); // F.11
public static void AjustarEstacionesExtremo(ref double start, ref double end, double s, double estMayor, double estMin, double estMax);
public static List<double[]> PartirEnHojas(IReadOnlyList<double> estNodos, double s, double anchoMax = ANCHO_MAX_MARCO);
public static List<List<int>> AgruparCruces(IReadOnlyList<double> est, IReadOnlyList<string> red, double s);
public static bool CotaSeparacionCabe(double claroFt, double v, double hTexto = H_TEXTO);
public static List<double> FusionarParedes(IReadOnlyList<double> xIn, double tol = FUSION_PAREDES);
```

### F.3 V, VE e intervalos

**`ElegirV(s)`**
1. `VEobj = s ≤ 10 ? 2.5 : (s ≤ 20 ? s/5 : min(10, s/4))`.
2. `Vobj = s/VEobj`.
3. `V` = el menor de `V_ESTANDAR` que sea `≥ Vobj − 1e-9`. Si ninguno lo es, `Vobj` redondeado hacia arriba a un múltiplo de 100.
4. `VE = s/V`.
5. Si `e.VForzada` tiene valor, se usa esa.

**`SiguienteV(v, s)`**
- El siguiente estándar mayor que `v`.
- Si ese valor supera `s`, devuelve `s` (VE = 1).
- Si `v ≥ s`, devuelve `v`.

**Criterio de altura** (F.4-5): si `(ZMaxDib − ZMinDib)/V > ALTO_MAX_DIBUJO` o `AltoMarco > ALTO_MAX_MARCO`, entonces `V = SiguienteV(V, s)`, se recalculan los intervalos y se repite. Máximo 8 veces, con el aviso `"VE reducida a {VE}"`.
- Con `VForzada` no se cambia `V`: se deja `VRecomendada` (lo que se habría elegido) y un aviso.

**`ElegirIntervalos(s, V)`**
- `CotaMayor` = el menor de `{1, 2, 5, 10, 20, 50, 100}` que cumpla `CotaMayor/V ≥ 2.0`.
- `CotaMenor`:

  | CotaMayor | 1 | 2 | 5 | 10 | 20 | 50 | 100 |
  |---|---|---|---|---|---|---|---|
  | CotaMenor | 0.5 | 0.5 | 1 | 2 | 5 | 10 | 20 |

- `EstMayor` = 100 si `100/s ≥ 0.75`; si no, 500 si `500/s ≥ 0.75`; si no, 1000. `EstMenor = EstMayor/10`.

| S | V | VE | CotaMayor/Menor | EstMayor/Menor |
|---|---|---|---|---|
| 5 | 2 | 2.5 | 5 / 1 | 100 / 10 |
| 10 | 4 | 2.5 | 10 / 2 | 100 / 10 |
| 20 | 5 | 4 | 10 / 2 | 100 / 10 |
| 25 | 4 | 6.25 | 10 / 2 | 100 / 10 |
| 30 | 4 | 7.5 | 10 / 2 | 100 / 10 |
| 40 | 4 | 10 | 10 / 2 | 100 / 10 |
| 50 | 5 | 10 | 10 / 2 | 100 / 10 |
| 60 | 10 | 6 | 20 / 5 | 100 / 10 |
| 100 | 10 | 10 | 20 / 5 | 100 / 10 |
| 200 | 20 | 10 | 50 / 10 | 500 / 50 |

### F.4 `Maquetar` (algoritmo completo, por hoja)

Coordenadas:
- Relativas: `x' = (e − EstIni)/S` in.
- Marco final: `X = x' + (EstIni − StationStart)/S`.

**1. V e intervalos**
- `V`, `VE` e `Int` salen de F.3, salvo que vengan forzados.

**2. Predicción**
- Bloques sin `Medido`: `PredecirBloque`.
- Tramos: las variantes de F.7 escaladas por `KMedida`.
- Paredes (F.6.a).

**3. Bucle horizontal.** Hasta `MAX_ITER = nBloques + nTramos + 3` pasadas; cada pasada aplica como mucho UN paso de regla.
- a. **Empaquetado sin límites**: por franja y nivel, con segmentos por paredes (F.6.b). Límites exteriores ±∞; los interiores son las paredes activas. Fila de tramos (F.7) en `x'` sin límites. Se obtienen `Lmin` y `Rmax`: la izquierda mínima y la derecha máxima de todas las cajas.
- b. **Relleno y rango horizontal**:
  - Relleno:
    - `padL = clamp(max(PAD_MIN, −Lmin + MARGEN_MARCO), PAD_MIN, PAD_MAX)`
    - `padR = clamp(max(PAD_MIN, Rmax − Lr + MARGEN_MARCO), PAD_MIN, PAD_MAX)`, con `Lr = (EstFin − EstIni)/S`.
  - `StationStart = RedondearAbajo(EstIni − padL·S, REDONDEO_EST)`:
    - Si `StationStart < 0` y `EstIni − (max(0, −Lmin) + MARGEN_MARCO)·S ≥ 0`, los bloques caben sin estaciones negativas: `StationStart = 0` (se sacrifica relleno para evitar «-0+xx»). Si no, se admite negativa con aviso.
    - Si queda por debajo de `EstMinPermitida`: `RedondearArriba(EstMinPermitida, 5)`.
  - `StationEnd = RedondearArriba(EstFin + padR·S, 5)`, acotado con `RedondearAbajo(EstMaxPermitida, 5)`.
  - `AjustarEstacionesExtremo` (F.11).
  - `AnchoMarco = (StationEnd − StationStart)/S`.
- c. **Empaquetado con límites**, en `[MARGEN_MARCO, AnchoMarco − MARGEN_MARCO]`, con segmentos (F.6.b) y fila (F.7). Paso a paso de desactivación de paredes (F.6.b) si un segmento desborda.
- d. **Holgura** por franja (F.6.c).
- e. **Evaluación**. Una franja o nivel está «desbordada» si su `desborde > 0` o si `maxDx/PENDIENTE_LEADER_MAX > HOLGURA_MAX`. La fila está desbordada si la fila 2 tiene `desborde > 0`.
- f. Si hay algo desbordado y alguna regla de F.8 cambia algo → se aplica ese paso y se vuelve a (a). Si no → se sale con aviso si sigue desbordado.

**4. Vertical**
- Terreno: solo muestras no NaN con `StationStart ≤ est ≤ StationEnd`.
  - `ZMaxDib = max(ZMaxDibujo, maxTerreno)`
  - `ZMinDib = min(ZMinDibujo, minTerreno)`
- Alturas de franja:
  - `Ht1` = máx `Alto` de los bloques superiores de nivel 1. `Ht = Ht1 (+ SEP_NIVEL + Ht2 si hay nivel 2)`.
  - `Hb` se calcula igual para la inferior. Sin bloques inferiores, `Hb = FRANJA_INF_MIN − HOLGURA_DIBUJO − MARGEN_MARCO` (= 0.20).
- Fila:
  - `H1`, `H2` = máx `Alto` de los textos de fila 1 y fila 2 (0 si no hay).
  - Si hay tramos rotulados: `AltoFila = MARGEN_MARCO + (H2 > 0 ? H2 + BASE_TEXTO_FILA + SEP_FILAS : 0) + H1 + BASE_TEXTO_FILA`. Si no, `AltoFila = 0`.
- **ElevationMin**:
  - `zNec = ZMinDib − (HolguraInf + Hb + MARGEN_MARCO)·V`
  - `ElevationMin = RedondearAbajo(zNec, CotaMayor)`
  - Si `(zNec − ElevationMin)/V > SOBRANTE_MAX_ELEVMIN`: `ElevationMin = RedondearAbajo(zNec, CotaMenor)`.
- `Y(z) = (z − ElevationMin)/V`.
- Franja inferior (izquierda, **base común**):
  - `YTopeInf = Y(ZMinDib) − HolguraInf`
  - nivel 1: `Y0 = YTopeInf − Hb1`, igual para todos
  - nivel 2: `Y0 = YTopeInf − Hb1 − SEP_NIVEL − Hb2`
- Franja superior:
  - `YBaseSup = Y(ZMaxDib) + HolguraSup`
  - nivel 1: `Y0 = YBaseSup`
  - nivel 2: `Y0 = YBaseSup + Ht1 + SEP_NIVEL`
- Tope y marco:
  - `Tope = YBaseSup + Ht + (AltoFila > 0 ? SEP_FILA + AltoFila : MARGEN_MARCO)`
  - `ElevationMax = RedondearArriba(ElevationMin + Tope·V, CotaMenor)`
  - `AltoMarco = (ElevationMax − ElevationMin)/V`
- Bases de fila:
  - `YFila2Base = AltoMarco − MARGEN_MARCO − H2 − BASE_TEXTO_FILA` (si `H2 > 0`)
  - `YFila1Base = (H2 > 0 ? YFila2Base − SEP_FILAS : AltoMarco − MARGEN_MARCO) − H1 − BASE_TEXTO_FILA`
  - Texto de fila: `Y0 = base + BASE_TEXTO_FILA`.
  - El sobrante del redondeo queda entre la franja superior y la fila.

**5. Criterio de altura** (F.3): si no se cumple, se sube `V` y se vuelve a 3. Sin forzado: máximo 8 veces.

**6. Posiciones**
- `X0 = centro − Ancho/2` en el marco final.
- `FranjaFinal`, `Nivel` e `Y0` según el paso 4.

**7. Leaders**
- Con `LeadersFinales` se calcula `CrucesLeaders`.
- Si hay cruce entre dos bloques de la misma franja y nivel, se intercambia su orden de empaquetado (la lista de orden es explícita, no se reordena por estación). Se repite desde 3 hasta 3 veces.

**8. Verificación**
- Se rellenan `Solapes`, `FueraDeMarco`, `CrucesLeaders`, `CortesLeaderCaja` (contra cajas de texto ajenas y `CajasDeDibujo`) y `PendientesExcedidas`.
- `SinSolapes = Solapes.Count == 0 && FueraDeMarco.Count == 0 && CrucesLeaders.Count == 0`.
- Los cortes y las pendientes se avisan (`"Leader corta {caja}"`, `"Leader inclinado {id}"`), pero no invalidan.

### F.5 `Empaquetar1D` (ponderado, exacto)

Requiere `ideal` en el orden de empaquetado del llamador (normalmente estación ascendente con desempate por `Id`). Devuelve los CENTROS en ese mismo orden.

```
n == 0 → lista vacía, desborde = 0
grupos = [ {items=[i]} para cada i ]
repetir:
   para cada grupo g (k items):
      ancho(g) = Σw + (k−1)·gap
      off_j = Σ_{m<j}(w_m + gap) + w_j/2
      inicio(g) = Σ p_j·(ideal_j − off_j) / Σ p_j          // media ponderada (p = pesos; null → 1)
      si ancho(g) > max − min:  inicio(g) = min ; desborde_g = ancho(g) − (max − min)
      si no:                    inicio(g) = clamp(inicio(g), min, max − ancho(g))
   si existe g, g+1 con inicio(g) + ancho(g) + gap > inicio(g+1) + 1e-9: fusionar g y g+1 y repetir
   si no: salir
desborde = Σ desborde_g ;  centro_j = inicio(g) + off_j
```

Con `min = −∞` y `max = +∞` no hay clamp.

### F.6 Franjas

**a. Paredes**
- Son las estaciones de las verticales de límite: EstIni, EstFin y las fronteras entre tramos rotulados. Los tramos omitidos no generan pared propia (F.7).
- `FusionarParedes`: las que quedan a menos de `FUSION_PAREDES` = 0.15" se sustituyen por su media.
- Se guardan en `r.Paredes`.
- Sin tramos rotulados no hay paredes.

**b. Segmentos** (en las referencias, ningún texto cruza una vertical de límite).
- Un bloque está «junto a pared» si la pared más cercana a su ancla cumple `|x'a − x'w| < Ancho`.
- Lado del bloque:
  - pared = EstIni → izquierda;
  - pared = EstFin → derecha;
  - pared interior → el lado cuya celda contigua (hasta la pared siguiente o el borde) es más ancha; en caso de empate, izquierda.
- Paredes ACTIVAS de una franja: las que tienen al menos un bloque junto a ellas. Dividen la franja en segmentos:
  - límite izquierdo = `pared_anterior + MARGEN_PARED` (o `MARGEN_MARCO` / −∞);
  - límite derecho = `pared_siguiente − MARGEN_PARED` (o `AnchoMarco − MARGEN_MARCO` / +∞).
- Cada bloque va al segmento de su lado; los que no están junto a pared, al segmento que contiene su ancla.
- Cada segmento se empaqueta por separado con `Empaquetar1D`:
  - `ideal = x'(EstAncla) + Ancho/2 − DxEnganche`, para que el enganche quede sobre el ancla;
  - pesos = `Prioridad`.
- Si un segmento desborda (`desborde > 0` o `maxDx > HOLGURA_MAX·PENDIENTE_LEADER_MAX`): se desactiva la pared de ese segmento cuyo segmento vecino tiene más holgura libre, y se reempaqueta. Cuenta como un paso del bucle F.4-3.
- Si al final un bloque queda sobre una pared: aviso `[PARED] {id}`. La vertical sigue completa y la máscara del texto la tapa, gracias al orden de dibujo de G.10.

**c. Holgura**
- `dx_i = |X0_i + DxEnganche − X(EstAncla_i)|`.
- `Holgura_f = clamp(max_i dx_i / PENDIENTE_LEADER_MAX, HOLGURA_DIBUJO, HOLGURA_MAX)`. Así ningún leader del ancla más alta pasa de unos 60° respecto a la vertical.
- Llegar al tope cuenta como desborde local (F.4-3e).

### F.7 Fila de tramos

Por tramo, en orden de estación:
- Celda `[Xa, Xb]` y `cx = (Xa + Xb)/2`.
- Variantes:
  - `v1` = una línea: `L1 + " " + L2 (+ " " + L3)`;
  - `v2` = dos líneas: `L1` / `L2 (+ " " + L3)`;
  - `v3` = tres líneas: `L1` / `L2` / `L3`, solo si hay `L3`.

1. **Omitido** si `EstFin − EstIni < max(TRAMO_MIN_FT, TRAMO_MIN_IN·S)`. No lleva rótulo; su dato se añade como una línea `INSTALL {L} LF {D}" {MAT}` al callout de su nodo inicial si existe, y si no se avisa. Sus fronteras se fusionan en una sola pared.
2. **Cabe**: la primera variante con `Ancho + MARGEN_CELDA ≤ Xb − Xa` → fila 1, centrada en `cx`.
3. **Fila 1 compartida**, para los que no caben, en orden de estación y con la variante más estrecha. Va a fila 1, centrado en `cx`, si se cumplen las tres condiciones:
   - su caja, con `GAP`, no solapa ninguna caja de fila 1 ya colocada;
   - su caja no cubre el `cx ± 0.10` de ningún OTRO tramo, para que el leader de un tramo de fila 2 nunca atraviese este texto;
   - en la fase con límites, queda dentro de `[MARGEN_MARCO, AnchoMarco − MARGEN_MARCO]`.
4. **Fila 2**, el resto:
   - `Empaquetar1D(ideal = cx, pesos = 1, GAP, límites)`.
   - **Siempre lleva leader** (`ConLeader`), con ancla en `(cx, YFila1Base)` y enganche en `(centro, Y0)`.
   - Si desborda, el tramo de fila 2 más corto pasa a callout vertical en la franja superior (`AVertical`, Tipo `"TRAMO"`, prioridad 40, movible, ancla `(cx, corona)`, líneas de la variante `v3`/`v2`). Un paso de regla por vez.
5. `Y0` = base de su fila + `BASE_TEXTO_FILA`. `NumLineas` = la variante elegida.

### F.8 Reglas «si no cabe» (un paso por pasada del bucle F.4-3; orden estricto)

Se aplican a la franja o nivel desbordado, sobre el **grupo empaquetado que desborda**.

1. **Cambiar de franja**: el bloque con `PuedeCambiarFranja` de MENOR prioridad del grupo que desborda pasa a la otra franja, siempre que esa otra franja no desborde después. Se repite en pasadas sucesivas mientras haya candidatos.
2. **Alternar franjas**: los bloques de índice impar del grupo (en orden de estación) con `PuedeAlternar` (false en INICIO/FIN) pasan a la otra franja, aunque tengan `PuedeCambiarFranja = false`. Una sola vez por franja.
3. **Recortar**: todos los bloques de la franja desbordada con `PuedeRecortar` y `Lineas.Length ≥ 3` pierden la ÚLTIMA línea («TOP ELEV …» / «INV ELEV …»).
   - `Ancho −= PASO_LINEA`.
   - `Alto = max LargoLinea(restantes)·(Alto/AltoPredichoOriginal)` si estaba medido. Si la línea quitada no era la más larga, `Alto` no cambia.
   - Se marca `Recortado = true` y se añade a `Recortados`. Una sola vez.
4. **Escalonar** (último recurso, CONDICIONADO): los índices impares pasan al nivel 2.
   - El nivel 1 se empaqueta normalmente.
   - En el nivel 2, `ideal` = centro del hueco de nivel 1 más cercano a su ancla `+ Ancho/2 − DxEnganche`.
   - Se acepta solo si todos los huecos usados miden `≥ HUECO_LEADER_MIN` y `CortesLeaderCaja` de los leaders de nivel 2 contra las cajas de nivel 1 queda vacío. Si no, se deshace.
5. **Aviso**: `"Rótulos apretados en franja {sup|inf}"`. El bloque `TERRENO` (EX. GRADE) de la franja desbordada se marca `Descartado`, y su etiqueta se borra en T3.

Durante las reglas el rango horizontal SÍ se recalcula: cada pasada vuelve a F.4-3a. La VE no forma parte de estas reglas: el desborde es horizontal (ver K).

### F.9 Leaders y verificaciones

**`LeadersFinales`** (en pulgadas del marco final; ancla = `(X(EstAncla), Y(ZAncla))`):
- Bloque superior: enganche `(X0 + DxEnganche, Y0)`.
- Bloque inferior: enganche `(X0 + DxEnganche, Y0 + Alto)`, es decir, el extremo superior de la cola de la línea 1.
- Tramo con leader: enganche `(centro, Y0)` y ancla `(cx, YFila1Base)`.

**Verificaciones**
- `CrucesLeaders`: intersección propia de segmentos por parejas, con tolerancia 1e-9 y excluyendo los extremos compartidos.
- `CortesLeaderCaja`: el segmento corta una caja (reducida en `TOL_SOLAPE`) que no es la suya. Las cajas de `CajasDeDibujo` son las elipses de los cruces:
  - `[X(EstIni_c), X(EstFin_c)] × [Y(ZMin_c), Y(ZMax_c)]`
  - ancho en estación = `AltoExt/sin(max(ángulo, 15°))`
- `PendientesExcedidas`: `|dx|/max(dy, 1e-6) > PENDIENTE_LEADER_MAX`.
- `FueraDeMarco`: caja con `X0 < MARGEN − tol`, `X1 > W − MARGEN + tol`, `Y0 < MARGEN − tol` o `Y1 > H − MARGEN + tol`.

### F.10 Calibración de medidas (`Calibrar`)

**Qué se compara.** Para cada etiqueta medida se toma la dimensión TRANSVERSAL a sus líneas, que depende solo de `h` y del interlineado:
- vertical → `Ancho`;
- horizontal → `Alto`.

**Cálculo**
- `r_i = medido_i/predicho_i`, con `predicho = h + (n−1)·PASO_LINEA`.
- `r = mediana(r_i)`.
- `dispersion = mediana(|r_i − r|)/r`.
- Con menos de 3 muestras, `r = 1` y dispersión 0.

**Uso** (G.6–G.7):
- Si `dispersion < 0.15` y `|r − 1| > 0.05`: problema de UNIDADES o de ESCALA, sea `FactorPl` o que CANNOSCALE no coincida con DrawingScale.
  - Se corrige `FactorPl /= r`: los textos pasan a medir lo previsto a la escala `S`.
  - Estilos con `SufijoPl`, etiquetas recreadas y nueva medición.
  - Log `[UNIDADES] r=… S=… Cannoscale=…`.
- Solo se descartan los atípicos respecto a `r`, no respecto a la predicción: `|r_i/r − 1| > 0.5` → se usa `predicho·r`, con log `[MEDIDA]`.
- La razón a lo largo de las líneas (`r_L`, que depende de `ANCHO_CAR`) solo se registra: se usan los tamaños medidos.

### F.11 Complementos (`PerfilDisenoFila.cs`)

**`ElegirEstacionesRecubrimiento`**
- `m = max(3, 0.3·S)`.
- Recorrido corto: si `estFin − estIni < 2·m + 0.75·S`, una sola estación, en el punto medio.
- Si no, los objetivos son:
  - `s1 = estIni + m`;
  - `s2 = estFin − m`;
  - `s3 = estCoberturaMin` (si no es NaN y está a ≥ 0.75"·S de s1 y de s2).
- Cada objetivo se desplaza a la estación libre más cercana:
  - en pasos de `0.05·S` ft;
  - dentro de `±0.75·S`;
  - a ≥ `0.10·S` de todo intervalo ocupado por leaders y a ≥ `0.30·S` de los ocupados por cruces;
  - en caso de empate, hacia el centro del tubo.
- Si no queda ninguna estación libre, ese objetivo se omite.
- Resultado ordenado y sin duplicados a menos de `0.75·S`.

**`AjustarEstacionesExtremo`**
- `lim(etq) = (LargoLinea(etq, H_NUM) + 0.15)·S`.
- Fin: si `0 < end − mayorAnterior < lim(FormatoEstacion(end, 0))`, `end = RedondearArriba(mayorAnterior + 0.6·S, 5)`, sin pasar de `estMax`.
- Inicio: si `0 < mayorSiguiente − start < lim(...)`, `start = RedondearAbajo(mayorSiguiente − 0.6·S, 5)`, sin bajar de `estMin`.

**`PartirEnHojas`**
- `L = estFin − estIni`, `Lmax = (anchoMax − 2·PAD_MIN)·S`, `k = ceil(L/Lmax)`.
- Corte `j` en el nodo más cercano a `estIni + j·L/k`. En caso de empate, el de menor estación.
- Si alguna hoja supera `Lmax`, `k++` y se repite, hasta `k = número de nodos − 1`.
- Devuelve los rangos `[EstA, EstB]`. El nodo de corte pertenece a ambas hojas, y su callout aparece en las dos.

**`AgruparCruces`**
- Se ordenan por estación.
- Un cruce entra en el grupo anterior si es de la misma `red` y está a `≤ max(2, 0.3·S)` ft del último del grupo.

**`CotaSeparacionCabe`**: `claroFt/V ≥ LargoLinea("0.00'", hTexto) + 0.10`.

### F.12 Casos del arnés

Tolerancia 1e-6 salvo que se indique otra.

**Formatos (`PerfilTextos`)**
- `FormatoEstacion`:
  - `(105.144, 2)` = `"1+05.14"`
  - `(100, 2)` = `"1+00.00"`
  - `(99.996, 2)` = `"1+00.00"`
  - `(1234.5, 2)` = `"12+34.50"`
  - `(85, 0)` = `"0+85"`
  - `(-15, 0)` = `"-0+15"`
  - `(160.584, 2)` = `"1+60.58"`
  - **`(-0.004, 2)` = `"0+00.00"`** (sin «-0»)
- `FormatoCota`:
  - `(745.434)` = `"745.43'"`
  - `(745.436)` = `"745.44'"`
  - `(-3.2)` = `"-3.20'"`
- `FormatoDiametro`:
  - `(8.0)` = `"8\""`
  - `(7.97)` = `"8\""`
  - `(0.75)` = `"1\""`
- `FormatoAngulo`:
  - `(44.6)` = `"45%%d"`
  - `(22.3)` = `"22.5%%d"`
  - `(11.0)` = `"11.25%%d"`
  - `(2.46)` = `"2.5%%d"`
  - `(30.0)` = `"30%%d"`
- `FormatoLongitud`:
  - `(0.3)` = `"1"`
  - `(49.6)` = `"50"`
- `AbreviarMaterial`:
  - `("Fundición dúctil")` = `"DI"`
  - `("PVC")` = `"PVC"`
  - `("Hormigón armado")` = `"RCP"`
  - `("Acero corrugado")` = `"CSP"`
  - `("Plástico ABS")` = `"ABS"`
  - `("Acero")` = `"STL"`
  - `("Material sin definir")` = `""`
  - `("")` = `""`
  - `("HDPE")` = `"HDPE"`
  - `("Cobre")` = `"COBRE"`
- `NumeroTolerante`:
  - `("745,431")` = 745.431
  - `("1.234,5")` = 1234.5
  - `("1,234.5")` = 1234.5
  - `(" 12 ")` = 12
  - `("")` y `("abc")` → false
- `ParsearXData(["TIPO=TEE","ANGULO=90,0","COORD_X=6512345,123","RED=RED-AGUA","TIPO=WYE"])`:
  - claves en MAYÚSCULAS
  - la clave repetida gana la ÚLTIMA (`Txt("TIPO") = "WYE"`, sin excepción)
  - `Num("ANGULO") = 90`, `Num("COORD_X") = 6512345.123`, `Num("FALTA")` = NaN
- `Sanear`:
  - `("Fundición {x}\\y")` = `"FUNDICION \\{X\\}\\\\Y"` (en notación C#: MAYÚSCULAS, sin tildes, `{`→`\{`, `}`→`\}`, `\`→`\\`)
  - `("45%%d bend")` = `"45%%d BEND"`: `%%d` se conserva en minúscula (H.8).

**Métrica**
- `AnchoBloqueVertical`:
  - `(3)` = 0.52
  - `(4)` = 0.72
  - `(1)` = 0.12
- `LargoLinea("PIPE STA 1+00.00")` = 1.5168.
- `LongitudVisible`:
  - `("45%%d BEND")` = 8
  - `("A\\{B")` = 3

**V/VE e intervalos**
- La tabla F.3 completa (10 filas).
- `SiguienteV`:
  - `(4, 10)` = 5
  - `(5, 10)` = 10
  - `(10, 10)` = 10
  - `(4, 30)` = 5

**Empaquetado** (gap 0.15, anchos 0.52, pesos null salvo que se indique):

| Caso | Ideal | Límites / pesos | Centros esperados | Desborde |
|---|---|---|---|---|
| E1 | [1.0, 1.19] | ±∞ | [0.76, 1.43] | — |
| E2 | [1.0, 1.19] | [0.6, 10] | [0.86, 1.53] | — |
| E3 | [1.0, 1.19, 5.0] | ±∞ | [0.76, 1.43, 5.0] | — |
| E4 | [1.0, 1.5, 2.0] | ±∞ | [0.83, 1.50, 2.17] | — |
| E5 | [1.0, 1.19] | [0, 1.0] | [0.26, 0.93] | 0.19 |
| E6 | [0, 3] | ±∞ | [0, 3] | 0 |
| E7 | [1.0, 1.19] | ±∞, pesos [100, 50] | [0.84, 1.51] | — |
| E8 (fusión por clamp en max) | [9.2, 9.9] | [0, 10] | [9.07, 9.74] | 0 |
| E9 | n = 0 | — | lista vacía | 0 |
| E10 | [5], ancho 12 | [0, 10] | [6] | 2 |

**Recorrido (`PerfilRecorrido`)**
- R1: nodos 0(0,0) 1(10,0) 2(20,0) 3(30,0) 4(20,10); aristas e0 0-1, e1 1-2, e2 2-3, e3 2-4 → `Recorrer(e0)` = [e0, e1, e2]. e3 es un ramal LT en el nodo 2.
- R2: continuaciones a 30° y a −35° → empate (5° < 10°) → [e0].
- R3: única continuación, con 50° → se para.
- R4: cuadrado cerrado → 4 aristas, sin repetir.
- R5: tangentes (0,0)-(10,10) con `b = tan 22.5°` → `t0 = (1,0)`, `t1 = (0,1)` (±1e-9). `PuntoMedioArco` a distancia `5√2·tan(22.5°)` del punto medio de la cuerda, a la izquierda.
- R6: `CortarTraza` sobre [(−50,0),(0,0),(100,0),(150,0)], estación del primer vértice 50:
  - (50,−10)-(50,10) → estación 150, 90°.
  - (20,−1)-(30,1) → 11.31°.
  - **(60,5)-(60,5)** (degenerado) → lista vacía, sin NaN.
- R7: `RecorrerDesdeNodo` en un nodo con aristas a 0°, 180° y 90° → par 0°/180°.
- **R8** (arista degenerada): nodos 0(0,0), 1(10,0), 2(10,0), 3(20,0); e0 0-1, e1 1-2 (`Valida = false`), e2 1-3 → `Recorrer(e0)` = [e0, e2]. Ningún δ es NaN.
- **R9** (vertical elegida): `Recorrer(e1)` con e1 no válida → lista vacía.
- **R10** (asignación 3D): extremo E=(0,0,100), u=(1,0), D=0.667 ft. Candidatos A(1.5,0,100,"CROSS-CONNECTS") y B(1.5,0,106,"RED-AGUA") → A (B no pasa el filtro dz).
- **R11** (desempate por red): A(1.5,0,100,"OTRA") y B(1.5,0,100,"RED-AGUA") con nombreRed "red-agua" → B.
- **R12** (detrás): C(−1.5,0.2,100) → −1 (ángulo > 25° y d2 > 0.25).
- **R13** (`Ralc` por LARGO_TOTAL_FT): C(3.0,0,100) con LargoTotalFt 5.6 y D=0.667 → aceptado (`Ralc = max(1.75, 3.3)`).
- **R14** (traza colineal): nodos (0,0),(10,0),(20,0) con bulges 0 y ext 25 → traza con 2 vértices: (−25,0) y (45,0).

**Maquetar**

M1 (réplica de 50.png)
- Entrada:
  - `S=10`, `EstIni=100`, `EstFin=160.58`, `EstMinPermitida=50`, `EstMaxPermitida=210.58`, `ZMinDibujo=743.60`, `ZMaxDibujo=750.60`, sin terreno.
  - Bloques `Medido`, Ancho 0.52:
    - superiores (ZAncla 745.0): U1(100.00, Alto 1.52, prio 100, INICIO, `PuedeAlternar=false`), U2(101.87, 1.42, 90), U3(158.92, 1.30, 90), U4(160.58, 1.52, 100, FIN, `PuedeAlternar=false`)
    - inferior (ZAncla 744.20): L1(154.86, 1.60, 60)
  - Tramos sin medir:
    - T1 100→105 ("INSTALL 5 LF OF" / "NEW 8\" DI PIPE")
    - T2 105→155 ("INSTALL 50 LF OF" / "NEW 8\" DI PIPE")
    - T3 155→160.58 ("INSTALL 6 LF OF" / "NEW 8\" DI PIPE")
- Esperado:
  - `V = 4`, `VE = 2.5`, `Int = {100, 10, 10, 2}`.
  - `StationStart = 85`, `StationEnd = 180`, `AnchoMarco = 9.5`.
  - `ElevationMin = 734`, `ElevationMax = 762`, `AltoMarco = 7.0`.
  - `HolguraSup = 0.658824`, `HolguraInf = 0.256471`, `YBaseSup = 4.808824`, `YTopeInf = 2.143529`.
  - Paredes activas: EstIni (U1 y U2 a la izquierda), EstFin (U3 y U4 a la derecha) y 155 (L1 a la izquierda).
  - Centros X: U1 0.52, U2 1.19, U3 7.868, U4 8.538. Todos los superiores con `Y0 = 4.808824`.
  - L1: centro 6.69, `Y0 = 0.543529`.
  - Tramos, todos en fila 1:
    - T1 en 2 líneas, centro 1.75
    - T2 `NumLineas = 1`, centro 4.5, ancho 2.9388
    - T3 en 2 líneas, centro 7.279
  - `YFila1Base = 6.53`, `YFila2Base = NaN`.
  - `SinSolapes = true`, `CortesLeaderCaja` y `PendientesExcedidas` vacíos.

M2 (apiñados → alternar)
- Entrada: S=10, EstIni=100, EstFin=109; 10 bloques superiores en 100, 101, …, 109 (Ancho 0.52, Alto 1.0, `Medido`, prio 90, ZAncla 745, no movibles, alternables); ZMin 740, ZMax 745; EstMin 50, EstMax 159.
- 1.ª pasada: holgura 2.565/1.7 = 1.508824 > 1.50, así que desborda y se aplica la regla 2.
- Esperado:
  - 5 bloques superiores (índices pares) y 5 inferiores (impares).
  - `StationStart = 85`, `StationEnd = 125`.
  - `HolguraSup = HolguraInf = 0.552941`, `ElevationMin = 732`, `ElevationMax = 752`.
  - Todos los niveles = 1. `SinSolapes`.

M2b (holgura sin regla)
- Entrada: igual que M2 pero con 4 bloques en 100…103 y EstFin 103.
- Esperado:
  - `StationStart = 85`, `StationEnd = 120`.
  - `HolguraSup = 0.502941`, `ElevationMin = 738`, `YBaseSup = 2.252941`, `ElevationMax = 752`.
  - Todos arriba. `SinSolapes`, `PendientesExcedidas` vacío.

M3 (recorte, sin posibilidad de alternar)
- Entrada: S=10, EstIni=100, EstFin=119; 20 bloques superiores en 100…119 con `Lineas` = ["PIPE STA 1+00.00", "8\" X 45%%d BEND", "TOP ELEV 745.43'"], Ancho 0.52, Alto 1.0, `Medido`, `PuedeRecortar`, `PuedeAlternar=false`, no movibles; ZMin 740, ZMax 745; EstMin 50, EstMax 169.
- Esperado:
  - `Recortados.Count = 20`, cada uno con Ancho 0.32 y Alto 1.0 (la línea quitada no era la más larga).
  - `StationStart = 60`, `StationEnd = 160`.
  - `HolguraSup = 1.50`. El escalonado no es viable (huecos de 0.15 < 0.30).
  - Todos en nivel 1.
  - `Avisos` contiene "Rótulos apretados en franja sup".
  - `SinSolapes = true`, `PendientesExcedidas` no vacío.

M4 (escalonado viable)
- Entrada: S=10; 25 bloques superiores en `100 + 4.5j` (j = 0..24), Ancho 0.52, Alto 1.0, `Medido`, ZAncla 745, no movibles, ni recortables ni alternables; EstIni 100, EstFin 208; ZMin 740, ZMax 745; EstMin 50, EstMax 258.
- Esperado:
  - `Nivel = 1` si j es par y 2 si es impar.
  - Centros X: nivel 1 = `1.64 + 0.9k`, nivel 2 = `2.23 + 0.9k`.
  - `StationStart = 85`, `StationEnd = 225`.
  - `Ht = 2.1`, `HolguraSup = 0.20`.
  - `SinSolapes`, `CortesLeaderCaja` vacío.

M5 (VE)
- Entrada: S=10, ZMin 700, ZMax 740, sin bloques.
- Esperado: `V = 5`, `VE = 2`, con aviso "VE reducida a 2".

M6 (cruce de leaders)
- Entrada: S=10, ZMinDibujo 743, ZMaxDibujo 750.6; un tramo 100→130, que da paredes en 100 y 130. Dos bloques superiores `Medido` de ancho 0.52 y Alto 1.0, ambos junto a la pared EstIni, así que van a la izquierda:
  - A: ancla 100.0, ZAncla 750.4 (somera)
  - B: ancla 100.3, ZAncla 744.0 (profunda)
- En orden de estación los leaders se cruzan: A va de (−1.12, Yb) a (0, somera) y B de (−0.45, Yb) a (0.03, profunda), en x' de enganche.
- Esperado:
  - `CrucesLeaders` vacío tras la corrección de F.4-7;
  - orden final B a la izquierda de A (`B.X0 < A.X0`);
  - `SinSolapes`.
- Prueba directa de la función: `CrucesLeaders([L1 (5.0,3)→(1.0,0), L2 (5.7,3)→(1.1,2.7)])` = `["L1|L2"]`.

M7 (fila de tramos saturada)
- Entrada: 30 tramos de gravedad de 20 ft a S=50 con L1/L2/L3 = "INSTALL 20 LF OF" / "NEW 8\" PVC PIPE" / "@ 0.52%".
- Esperado:
  - ningún texto fuera del marco;
  - todo tramo de fila 2 con `ConLeader`;
  - los que desbordan, con `AVertical`;
  - `FueraDeMarco` vacío.

M8 (tramo minúsculo)
- Entrada: tramo de 0.3 ft a S=10.
- Esperado: `Omitido = true`, sin pared propia y con las paredes vecinas fusionadas.

M9 (tubo corto)
- Entrada: un tubo de 20 ft (EstIni 100, EstFin 120) a S=10 y a S=50.
- Esperado: `FueraDeMarco` vacío en los dos. Recubrimientos: S=10 → [103, 117]; S=50 → [110].

M10 (terreno)
- Entrada: muestras de terreno con una loma de 800 ft FUERA de `[StationStart, StationEnd]` y una vaguada bajo el tubo dentro del rango.
- Esperado: `ZMaxDib` no incluye la loma y `ElevationMin` baja por la vaguada. Las muestras NaN se ignoran.

M11 (altura total)
- Entrada: S=20, ZMin 700, ZMax 760, sin tramos.
- Esperado: `V` pasa de 5 a 10 (VE 2), porque 60/5 = 12" > 8" y con V=10 queda en 6". `AltoMarco ≤ 12`.

**Complementos**
- Recubrimiento con un leader que ocupa el intervalo [102.5, 103.5] (S=10, tubo 100–120) → [104.5, 117].
- `AjustarEstacionesExtremo`:
  - `(start 85, end 1205, S 40, EstMayor 100, estMax 2000)` → end = 1225.
  - `(start 95, …, S 40)` → start = 75.
  - `(85, 180, S 10)` → sin cambios.
- `PartirEnHojas([100,150,230,380,560,610,790,950,1100], S 20)` → [[100, 610], [610, 1100]]. Con S 40 → una sola hoja.
- `AgruparCruces`:
  - estaciones [120, 121, 122, 123, 124] de la red "ELEC" + [122] de la red "AGUA", S=10 → 2 grupos (5 + 1).
  - [120, 126] de "ELEC" → 2 grupos.
- `CotaSeparacionCabe`:
  - `(1.0, 4)` → false (0.25" < 0.574").
  - `(3.0, 4)` → true.
- `Solapes`: (0,0,1,1) contra (0.99,0,2,1) con tol 0.02 → sin solape; (0.9,0,2,1) → solape.
- `FueraDeMarco`: caja (1, 7.85, 2, 8.02) en un marco de 8" de alto → fuera.
- `Calibrar`:
  - medidos = 12 × predichos (5 muestras) → r = 12, dispersión 0.
  - [1.0, 1.02, 0.98, 2.5] → r ≈ 1.01, y el 2.5 es atípico.

---

## G. Secuencia del comando (`ComandosPerfil.CrearPerfilRed`)

```csharp
[CommandMethod("CREAR_PERFIL_RED")]     public void CrearPerfilRed() { ... }
[CommandMethod("CREAR_PERFIL_PRESION")] public void CrearPerfilPresion() { CrearPerfilRed(); }
```

**Regla transversal.** Tras el `Commit` de cada transacción que crea, mueve o redimensiona etiquetas o vistas se hace `doc.TransactionManager.QueueForGraphicsFlush(); doc.TransactionManager.FlushGraphics();`.
- `doc.TransactionManager` es `Autodesk.AutoCAD.ApplicationServices.TransactionManager` (accoremgd). Tiene `FlushGraphics()` y hereda `QueueForGraphicsFlush()`; ambos están verificados.
- La llamada va en try.

### G.0 Preparación
- Se obtienen `doc`, `ed`, `db` y `civDoc`, y se ejecuta `PerfilLog.Iniciar()`.
- `S = DrawingScale`. Si no es válido (`S ≤ 0` o `S > 1000`), se registra `Cannoscale` y se usa `S = 20` con aviso `[UNIDADES]`.
- Si `DrawingUnits == Meters`, aviso y `FactorPl = 0.0254`.

### G.1 Prompt 1 (antes de cualquier transacción)
- `PromptEntityOptions("\nSeleccione una tubería o estructura de la red para el perfil:")`.
- `SetRejectMessage("\nDebe ser una tubería (gravedad/presión) o una estructura.")` va ANTES de los `AddAllowedClass`.
- `AddAllowedClass(typeof(CivilDB.Pipe), true)`, lo mismo con `Structure` y con `PressurePipe`.
- Si el usuario cancela → return.

### G.2 T0 (lectura, sin cambios)
1. C.1, con la comprobación de la tubería vertical, que sale con su mensaje.
2. Grafo (C.2/C.3) y recorrido (C.4). Si el recorrido tiene 0 tubos: «✗ No se pudo formar un recorrido desde esa entidad.» y return.
3. Traza (C.5), estaciones preliminares (D.3) y terreno (D.4).
4. Ramales, callouts (H.3), tramos (H.4), candidatos a cruce (C.7) con su agrupación, y callouts de cruce (H.5) y de EX. GRADE.
5. `FactorPl` inicial (I-1) y tamaños predichos.
6. `PartirEnHojas`: reparte callouts, tramos y cruces por hoja.
7. Maquetar preliminar por hoja. `V` global = el MAYOR V de todas las hojas (la VE más baja), y con él los `Int`.
8. Nombre único (D.1).
9. `Commit` y mensaje `"\n· Recorrido: {tubos} tubos, {nodos} nodos, {largo:0.00} ft, {ramales} ramales, {cruces} cruces ({grupos} grupos), {hojas} hoja(s)."`.

### G.3 Prompt 2
- `ed.GetPoint("\nPunto de inserción de la vista de perfil (esquina inferior izquierda):")`.
- Si se cancela → return (no se ha creado nada).

### G.4 T1a (creación)
Si el eje o la vista de la hoja 1 fallan: `Abort` y return. Pasos:
1. Capas, TextStyle y linetype. Estilos (E) con `V`, `Int` y `FactorPl` → `EstilosPerfil`. Diagnóstico E.10.
2. Eje (D.2, fatal si falla). Estaciones definitivas (D.3) de nodos, extremos y cruces.
3. Perfil de terreno: `Profile.CreateFromSurface(nombre + " - EX. GRADE", alignId, surfId, CapaId, TerrenoStyle, LabelSetPerfilVacio)`. Si falla, aviso.
4. Por cada hoja k:
   - `Insercion_k = pt + (0, −Σ_{j<k}(AltoMarco_j^prelim + 2.5)·S, 0)`.
   - `ProfileView.Create(alignId, Insercion_k, nombreHoja, BandSetVacio, VistaStyle)`. Si falla una hoja k > 0, aviso y se omite su contenido.
   - `pv` ForWrite:
     - `Layer = "PDFCAD_PERFIL"`;
     - vaciar las bandas;
     - `StationRangeMode` y `ElevationRangeMode` = `UserSpecified`;
     - rango = el del Maquetar preliminar de la hoja, en orden seguro: si la nueva Min > Max actual, primero Max. Cada set va en su try.
5. **Captura** (`AddToProfileView`): lista `nuevos` y manejador `db.ObjectAppended` que añade los ids cuya `ObjectClass` deriva de `ProfileViewPart` o de `ProfileViewPressurePart`.
   - El manejador se SUSCRIBE aquí y se DESUSCRIBE después del `Commit` de T1a, en un `finally` exterior.
   - Por cada hoja y cada parte:
     - partes del recorrido cuya estación cae en la hoja;
     - estructuras de sus nodos (gravedad y conduit);
     - cruces de la hoja.
   - Para cada una: se abre la parte (`Part`/`PressurePart`) **ForWrite**, se guarda `i0 = nuevos.Count`, se llama a `part.AddToProfileView(pvId)` y se asocia `nuevos[i0..]` a (parte, hoja). Cada parte en su try.
6. `Commit`. Desuscribir. Flush.

### G.5 T1b (overrides y etiquetas)
1. **Resolución de `ProfileViewPart`**:
   - Los ids atribuidos por ventana se abren ForRead para confirmar `ModelPartId`.
   - Los que llegaron durante el `Commit` (sin ventana) se emparejan por `ModelPartId` y por hoja, con `GeometricExtents` dentro de `pv.GeometricExtents`, en try.
   - Respaldo 1: recorrer el `BlockTableRecord` de `pv.OwnerId`.
   - Respaldo 2: `part.ProfileViewPartId` solo si `GetProfileViewsDisplayingMe().Count == 1`. Al volver a ejecutar, los cruces ya dibujados en otra vista quedan con Count ≥ 2 y no usan este respaldo.
   - Sin id: el cruce queda sin etiqueta y se avisa.
2. **Overrides por vista** (`pv` ForWrite):
   - Se recorren `pv.PipeOverrides` (`PipeId`), `pv.StructureOverrides` (`StructId`) y `ProfileViewPressurePipesExtension.GetPressurePipeOverrides(pv)` (`PressurePartId`).
   - En cada uno: `Draw = true`, `OverrideStyleId = estilo`, `UseOverrideStyle = true`.
   - Asignación: recorrido → Tubo o Tubo Abandonado; cruce → Cruce; estructura → Estructura.
   - Si un id esperado no aparece: log `[VISTA] override no encontrado {handle}`.
3. **Etiquetas**, cada una en su try.
   - Callouts (H.3) y EX. GRADE (H.5): `StationElevationLabel.Create(pvId, estilo, SinMarcador, Estacion, ZAncla)`. Si lanza, reintento con `ObjectId.Null`; si vuelve a fallar, se omite con aviso.
     - Ancla de presión: `EstAncla` (H.3); si el ancla difiere de la estación del texto, se crea en `(EstAncla, ZAncla)`.
   - Tramos: ancla `(estMedia, corona(estMedia))`, texto en la variante `v2`.
   - Cruces, solo el representante del grupo:
     - gravedad: `CrossingPipeProfileLabel.Create(pvPartId, pvId, CruceGravLbl)`;
     - presión: `CrossingPressurePipeProfileLabel.Create(pvPartId, pvId, 0.5, CrucePresLbl)`;
     - si la colección viene vacía → aviso;
     - si trae más de una → se queda la de estación más cercana, calculada con `pv.FindStationAndElevationAtXY(AnchorInfo.Location.X, …)`, y las demás se abren ForWrite y se ejecuta `Erase()`.
   - Texto de cada etiqueta (ForWrite):
     - `GetTextComponentIds()`, se abre cada uno como `LabelStyleTextComponent` y se toma el de `Name == "PDFCAD_TEXTO"`;
     - `SetTextComponentOverride(compId, string.Join("\\P", lineasSaneadas))`;
     - nunca una cadena vacía (mínimo `" "`).
   - Tras crear cada etiqueta: `LeaderVisibility = AlwaysHide`, para que la medición de T2 no incluya el leader.
4. `Commit`. Flush.

### G.6 T2 (medición, solo lectura)
Por cada etiqueta:
1. Ancla:
   - `ok = pv.FindXYAtStationAndElevation(est, z, ref x, ref y)`.
   - Si `!ok`, respaldo `x = pv.Location.X + (est − StationStart)`, `y = pv.Location.Y + (z − ElevationMin)·VE`, con log `[VISTA]`.
2. Extensión:
   - `ext = label.GeometricExtents`, en try.
   - Si lanza o si su ancho o alto es ≤ 1e-6 → tamaño predicho, con aviso `[MEDIDA]`.
3. Cajas:
   - `Rel = (ext.Min − ancla)/S`, `(ext.Max − ancla)/S`, en pulgadas.
   - `Ancho` y `Alto` a partir de `Rel`.
   - Se registra `AnchorInfo.Location` frente al ancla calculada.
4. Tramos: `KMedida = medido/predicho(v2)`.
5. `Calibrar` (F.10) → `r` y dispersión. `Commit`.

### G.7 T2b (solo si F.10 detecta un problema de unidades; como mucho una vez)
- `FactorPl /= r` y `SufijoPl` nuevo.
- En la transacción:
  - `Asegurar` todos los estilos dependientes con el nuevo nombre;
  - `pv.StyleId = nuevaVista` en cada hoja (ForWrite);
  - borrar las etiquetas de G.5-3 y recrearlas con los estilos nuevos.
- `Commit`, flush y repetir G.6. Si `|r − 1| > 0.05` otra vez, aviso `[UNIDADES]` y se siguen usando las medidas.

### G.8 Maquetar final (puro, por hoja)
- Parámetros: `VForzada = V`, `IntForzados = Int`, tamaños medidos, estaciones definitivas y `CajasDibujo` de los cruces.
- Si `VRecomendada ≠ V` en alguna hoja (por ejemplo, altura excedida con las medidas reales):
  - `V = max(VRecomendada)`;
  - se repite el Maquetar de TODAS las hojas con el nuevo `V`;
  - en T3 se aplica un estilo de vista con el nombre nuevo (nunca se modifica el que está en uso).
- Los avisos del resultado van al log.

### G.9 T3 (rango final)
Por hoja, con `pv` ForWrite:
1. Si `V/Int` cambiaron: `Asegurar` el nuevo `ProfileViewStyle` y `pv.StyleId = …` ANTES del rango.
2. Rango final, en orden seguro.
3. Reapilado: para k ≥ 1, `pv.Location = pt + (0, −Σ_{j<k}(AltoMarco_j^final + 2.5)·S, 0)`. Todavía no hay etiquetas arrastradas, así que siguen a su ancla **[EJECUCIÓN]**: se registra un `FindXY` de control antes y después.
4. Etiquetas (ForWrite):
   - `Recortados` → override sin la última línea;
   - tramos cuya variante elegida ≠ `v2` → override con la variante elegida;
   - `Descartado` → `Erase()`;
   - `AVertical` → `Erase()` del tramo y creación de un callout con el estilo Callout Sup.
5. `Commit`. Flush.

### G.10 T4 (colocación y etiquetas que dependen del rango)
1. Origen del marco `O` = `FindXY(StationStart, ElevationMin)`, con el respaldo de G.6.
2. Por cada bloque o tramo (etiqueta ForWrite):
   - `ancla' = FindXY(EstAncla, ZAncla)`
   - `minActual = ancla' + RelMin·S`
   - `destino = O + (X0, Y0)·S`
   - `LabelLocation = LabelLocation + (destino − minActual)`
   - No se usa `DraggedOffset`: su setter está obsoleto.
3. Visibilidad de leaders:
   - Callouts, cruces y rasante: `LeaderVisibility = FromLabelStyle`, `LeaderTailVisibility = FromLabelStyle` (la cola subraya la línea 1).
   - Tramos de fila 1: `AlwaysHide` en ambos.
   - Tramos de fila 2: se BORRAN y se recrean en `(cx, z(YFila1Base))`, donde `z(Y) = ElevationMin + Y·V`, con el mismo texto; se mueven igual; `LeaderVisibility = FromLabelStyle` y `LeaderTailVisibility = AlwaysHide`.
4. Etiquetas nuevas (`StationElevationLabel` con override), creadas en su ancla. Se colocan en T5 porque dependen de `pv.GeometricExtents`:
   - «STATION (FT)» (`EjeTitulo`) en `(estCentroVista, ElevationMin)`;
   - estaciones de extremo en `StationStart` y `StationEnd` si no son múltiplo de `EstMayor` (`|resto| > 0.01`), con el texto `FormatoEstacion(est, 0)`;
   - título (H.7), en `(StationStart, ElevationMin)`.
   - En las tres: `LeaderVisibility = AlwaysHide` y `LeaderTailVisibility = AlwaysHide`.
5. Recubrimientos, si hay terreno y estilo de profundidad:
   - estaciones con `ElegirEstacionesRecubrimiento`, pasándole los intervalos de X ocupados por leaders y cruces (en estación) y `s3` = mínimo de `terreno − corona`;
   - para cada una con `terreno − corona > 0.10` ft: `ProfileViewDepthLabel.Create(pvId, Profundidad, P(s, corona), P(s, terreno))`, con `P` = `Point2d` de `FindXY`.
6. Separaciones con cruces:
   - si `|ClaroFt| ≤ 10` y `CotaSeparacionCabe(ClaroFt, V)`: `ProfileViewDepthLabel` entre las dos paredes;
   - si no cabe: el callout del cruce ya lleva la línea `{clr} CLR` (H.5).
7. Límites, en cada pared de `r.Paredes`: `ProfileViewDepthLabel.Create(pvId, Limite, P(e, cota(YFila1Base)), P(e, corona(e)) + 0.05"·S en Y)`. La vertical es SIEMPRE completa.
8. Orden de dibujo: el `DrawOrderTable` del `BlockTableRecord` dueño de la vista (`btr.DrawOrderTableId`, ForWrite) hace `MoveToBottom` de los ids de límites, recubrimientos y separaciones. Así la máscara de los textos los tapa (I-20).
9. `Commit`. Flush.

### G.11 T5 (corrección iterativa; hasta 3 iteraciones, cada una en su transacción con commit y flush)
1. Se mide cada etiqueta movida (extents en try).
2. Bordes fiables:
   - franja superior: `MaxY` (el leader baja);
   - franja inferior: `MinY` (base común);
   - en X: si `ancla.X < centro destino`, `MaxX` frente a `X1`; si no, `MinX` frente a `X0`;
   - tramos de fila 1 y etiquetas sin leader: los cuatro bordes.
3. `d = destino − medido`. Si `|d| > TOL_CORRECCION·S`, `LabelLocation += d`.
4. Posición relativa a la vista: se mide `pv.GeometricExtents` (el título del eje inferior está apagado, así que `MinY` es el pie de los números de estación) y `frameMinY = Y de O`.
   - Estaciones de extremo: borde inferior = `pv.MinY`, centradas en `X(est)`.
   - «STATION (FT)»: borde superior = `pv.MinY − 0.10"·S`, centrado en el marco.
   - Título: borde superior = `MinY(STATION) − 0.25"·S`, borde izquierdo = `pv.MinX`.
   - Si `frameMinY − pv.MinY < 0.10"·S` (no hay números mayores en el rango): las estaciones de extremo se alinean con la parte superior en `frameMinY − 0.08"·S`, con aviso.
5. Seguridad: si una etiqueta vertical medida tiene la proporción invertida (Ancho > 2× lo esperado y Alto < 0.5× lo esperado), se hace `ResetLocation()` y se avisa «rótulo sin reubicar: {id}» (I-2).
6. Las etiquetas que no convergen en 3 iteraciones: log `[CORRECCION] {id} d={d}`.

### G.12 T6 (verificación final, lectura)
- Por hoja se calcula todo con cajas y leaders MEDIDOS:
  - `Solapes`;
  - `FueraDeMarco` (con `MARGEN_MARCO`);
  - `CrucesLeaders` y `CortesLeaderCaja`, con enganche en el extremo del leader más cercano al bloque y ancla medida.
- Todo va al log; cada problema cuenta como aviso.

### G.13 Resumen (línea de comandos, en español)

```
\n✓ Perfil '{nombre}' creado: {Hojas} vista(s), {Tubos} tubos, {Estructuras} estructuras, {Cruces} cruces ({GruposCruce} rótulos), {Callouts} rótulos, {Rotulos} tramos, {Profundidades} cotas de recubrimiento.
\n⚠ {n} aviso(s): {primeros 3 separados por '; '}          (si hay avisos)
\n⚠ Sin superficie: no se dibuja terreno ni recubrimientos.  (si procede)
\n· Si cambia el rango de la vista, vuelva a ejecutar el comando (los rótulos quedan arrastrados).
\n· Detalle en {PerfilLog.Ruta}
```

### G.14 Objetos que se abren ForWrite (siempre con `tr.GetObject(id, OpenMode.ForWrite)`)

| Objeto | Para qué | Fase |
|---|---|---|
| `LayerTable`, `TextStyleTable`, `LinetypeTable` | `Add` | T1a |
| `BlockTableRecord` de ModelSpace | `AppendEntity` (polilínea del eje) | T1a |
| Cada estilo (`StyleBase`, `LabelStyle`, componentes) | cualquier `Set`; `RemoveComponent`/`AddComponent` | T1a, T2b, T3 |
| `ProfileLabelSetStyle` / `AlignmentLabelSetStyle` | vaciado (`RemoveAt`) | T1a |
| `Alignment` | `ReferencePointStation` | T1a |
| `ProfileView` | `Layer`, bandas, rango, `StyleId`, `Location`, overrides | T1a, T1b, T2b, T3 |
| `Part` / `PressurePart` | `AddToProfileView` | T1a |
| `Label` (todas) | override, `LabelLocation`, `LeaderVisibility`, `LeaderTailVisibility`, `ResetLocation`, `Erase` | T1b–T5 |
| `DrawOrderTable` | `MoveToBottom` | T4 |

`CopyAsSibling` puede ejecutarse sobre la base abierta ForRead; ya se usa así en ImportarRed.cs:1128/1184.

### G.15 Robustez
- Todo acceso frágil a Civil va en su propio try.
- Un fallo en T2…T6 no deshace T1: el perfil queda creado, se hace commit de lo logrado y se informa.
- Todo es un único comando, así que un UNDO lo revierte entero.
- Los prompts se hacen fuera de las transacciones.
- El manejador de `ObjectAppended` se desuscribe siempre, en un `finally`.

---

## H. Contenido de las etiquetas (inglés) y formatos

### H.1 Formatos (`PerfilTextos`, cultura invariante)

```csharp
internal const string GRADO = "%%d";                               // única constante (I-5)
internal static string FormatoEstacion(double est, int decimales);  // redondeo AwayFromZero; si |e| < 0.5·10^-dec → 0 (sin "-0")
internal static string FormatoCota(double z);                       // "0.00" + "'"
internal static string FormatoDiametro(double pulg);                // max(1, round(pulg)) + "\""
internal static string FormatoAngulo(double grados);                // estándar {11.25, 22.5, 45, 90} si |Δ| ≤ 1.0; si no F1 sin ".0"; + GRADO
internal static string FormatoPendiente(double ratio);              // (|ratio|·100).ToString("0.00") + "%"
internal static string FormatoLongitud(double ft);                  // max(1, round(ft, AwayFromZero))
internal static string AbreviarMaterial(string m);                  // H.2
internal static bool NumeroTolerante(string s, out double v);       // H.6
internal static Dictionary<string, string> ParsearXData(IEnumerable<string> lineas);  // dic[clave] = valor (la última gana)
internal static string Sanear(string texto);                        // H.8
```

### H.2 Materiales

La comparación se hace sin tildes y sin mayúsculas, en este orden:

| Si el texto… | Resultado |
|---|---|
| es `""`, null o «material sin definir» | `""` |
| contiene «ductil» | `DI` |
| contiene «corrugado» | `CSP` |
| contiene «hormigon» o «concreto» | `RCP` |
| contiene «pvc» | `PVC` |
| contiene «abs» | `ABS` |
| contiene «hdpe» o «polietileno» | `HDPE` |
| contiene «acero» | `STL` |
| cualquier otro | MAYÚSCULAS sin tildes, primeros 10 caracteres |

Composición con `Unir(params string[])`, que descarta los vacíos: `"{D}\" {MAT} PIPE"`.

### H.3 Callouts de nodo

Formato: `StationElevationLabel` con `\P` entre líneas. Cada línea se sanea (H.8).

**Ancla**
- Franja superior → corona. Franja inferior → fondo exterior. Estructura de gravedad → `Rim`.
- **Presión**: si el centro del accesorio cae en el hueco entre tubos recortados, `EstAncla` = la estación del extremo de tubo más cercano (corona allí). El texto conserva la estación del nodo.
- `TOP = FormatoCota(corona)`. `D` y `MAT` son los del tubo que llega (o el que sale, en el primer nodo).

| Caso | Franja / prio / movible / alternable / recortable | Líneas |
|---|---|---|
| Inicio/fin en extremo libre (presión, conduit) | Sup / 100 / no / **no** / sí | `PIPE STA {sta}` · `END OF {D}" {MAT} PIPE` · `TOP ELEV {top}` |
| Inicio/fin en extremo libre (gravedad) | Sup / 100 / no / **no** / no | `PIPE STA {sta}` · `END OF {D}" {MAT} PIPE` · `INV ELEV {inv}` |
| Tee (ramal en planta) | Sup / 90 / no / sí / sí | `PIPE STA {sta}` · `{Dm}" X {Dr}" TEE` · `{Dr}" BRANCH {LT\|RT}` · `TOP ELEV {top}` |
| **Tee con ramal vertical** (sin arista de ramal en planta, `DiamRamalIn > 0`) | Sup / 90 / no / sí / sí | `PIPE STA {sta}` · `{Dm}" X {Dr}" TEE` · `{Dr}" VERT BRANCH {UP\|DOWN}` (sin sentido si `SentidoVertical == ""`) · `TOP ELEV {top}` |
| Tee terminal | Sup / 90 / no / sí / sí | `PIPE STA {sta}` · `{Dm}" X {Dr}" TEE` · `TOP ELEV {top}` |
| Wye | Sup / 90 / no / sí / sí | `PIPE STA {sta}` · `{Dm}" X {Dr}" WYE` · `{Dr}" BRANCH {LT\|RT} {ang}` · `TOP ELEV {top}` |
| Cruz | Sup / 90 / no / sí / sí | `PIPE STA {sta}` · `{Dm}" X {Dr}" CROSS` · `{Dr}" BRANCHES LT & RT` · `TOP ELEV {top}` |
| Codo interior | Inf / 70 / sí / sí / sí | `PIPE STA {sta}` · `{D}" X {ang} {HORIZ\|VERT} {MAT} BEND` · `TOP ELEV {top}` |
| **Codo en extremo del recorrido** sin otra arista en planta | Inf / 70 / sí / sí / sí | `PIPE STA {sta}` · `{D}" X {ang} VERT {MAT} BEND` · `TOP ELEV {top}` |
| Reducción | Inf / 65 / sí / sí / sí | `PIPE STA {sta}` · `{D1}" X {D2}" REDUCER` · `TOP ELEV {top}` |
| Deflexión (unión de presión ≥ 1°) | Inf / 60 / sí / sí / sí | `PIPE STA {sta}` · `{defl} DEFLECTION` · `TOP ELEV {top}` |
| Quiebre de conduit (≥ 2°) | Inf / 60 / sí / sí / sí | `PIPE STA {sta}` · `{defl} {HORIZ\|VERT} BEND` · `TOP ELEV {top}` |
| Estructura (gravedad) | Sup / 80 / no / sí / no | `STA {sta}` · `{NOMBRE}` · `RIM ELEV {rim}` · `INV IN {inv}` (… ramal: `INV IN {inv} ({Dr}" {LT\|RT})`) · `INV OUT {inv}` |

- `{ang}` = `AnguloXData` si no es NaN; si no, `max(δh, δv)`. Siempre con `FormatoAngulo`.
- `HORIZ`/`VERT` según la vertical dominante (C.6).
- `Dm` = `DiamPrincipalIn`, con el del recorrido como respaldo. `Dr` = `DiamRamalIn`, con el del ramal como respaldo.
- Inverts de gravedad: `ComandosCotarTuberias.InvertEnNodo(ObjectId.Null, extremo, pipe, tr)`. Máximo 6 líneas; si hay más, `INV IN {min} ({n} BRANCHES)`.
- Si un nodo es a la vez inicio/fin y accesorio, prevalece el callout del accesorio sin la línea `END OF …`.
- Línea adicional del tramo omitido (F.7-1): se añade antes de `TOP ELEV`.

### H.4 Rótulo de tramo (StationElevationLabel «Tramo»)

Un tramo es una racha de pasos con el mismo `DiamIn` redondeado, `Material` y `Abandonado`, y en gravedad además la misma pendiente (`|Δs| < 0.0001`). `L = FormatoLongitud(EstFin_t − EstIni_t)`.

| Tipo | L1 | L2 | L3 |
|---|---|---|---|
| Presión | `INSTALL {L} LF OF` | `NEW {D}" {MAT} PIPE` | — |
| Conduit | `INSTALL {L} LF OF` | `NEW {D}" {MAT} CONDUIT` | — |
| Gravedad | `INSTALL {L} LF OF` | `NEW {D}" {MAT} PIPE` | `@ {S}` |
| Abandonado | `{L} LF OF EXIST` | `{D}" {MAT} PIPE (ABANDONED)` | — |

### H.5 Rasante y cruces

**EX. GRADE**
- 1 línea, franja superior, prioridad 50, no movible, alternable, leader recto.
- Estación: de entre `EstIni + k·(EstFin − EstIni)/6` (k = 1..5), con terreno no NaN, la de mayor distancia mínima en X a las anclas de los demás bloques superiores, a los cruces y a los recubrimientos previstos.
- `ZAncla = terreno(e)`.

**Cruce** (uno por GRUPO, en el representante = el primero del grupo)
- Franja superior si `Encima`; si no, inferior. Prioridad 55, no movible, alternable, recortable.
- Líneas:
  - Un solo tubo:
    - `{D}" {MAT} PIPE` (+ ` (ABAND.)`)
    - `{RED}`, en mayúsculas y con 24 caracteres como máximo
    - gravedad: `INV ELEV {ZEje − RadioInt}`; presión: `TOP ELEV {ZEje + AltoExt/2}`
  - Grupo de n: `({n}) {D}" {MAT} {PIPES|CONDUITS}` (si los diámetros son distintos, `{D1}"/{D2}"`), `{RED}` y `TOP ELEV {min}-{max}`.
  - Si la cota de separación no cabe (F.11) y `|ClaroFt| ≤ 10`: línea extra `{FormatoCota(clr)} CLR`.
- `ZAncla = ZEje` del representante.
- Los demás cruces del grupo se dibujan (`AddToProfileView`) sin etiqueta.

### H.6 Parser tolerante de XDATA
- `ParsearXData`:
  - cada línea `CLAVE=valor` se parte por el primer `=`;
  - clave = `Trim().ToUpperInvariant()`;
  - **`dic[clave] = valor`** (nunca `Add`: una clave repetida no lanza excepción);
  - las líneas sin `=` se ignoran.
- `NumeroTolerante`:
  - con trim; si queda vacío → false;
  - si hay `,` y `.`, el último que aparece es el separador decimal y el otro se elimina;
  - si solo hay `,`, pasa a `.`;
  - `double.TryParse(…, NumberStyles.Float, CultureInfo.InvariantCulture, out v)`.
- `Num` → NaN si falta la clave. `Txt` → `""` si falta.

### H.7 Título y estaciones de extremo
- Título en 2 líneas:
  - `PROFILE {n} - {Dpred} INCH {MAIN|PIPE|CONDUIT} - {RED}`, con ` ({k}/{K})` tras `{n}` si hay más de una hoja;
  - `HORIZ 1"={S}'  VERT 1"={V}'`.
- `Dpred` = el diámetro con más longitud en el recorrido. `MAIN` en presión, `PIPE` en gravedad, `CONDUIT` en conduit.
- Estaciones de extremo: `FormatoEstacion(est, 0)`.

### H.8 Saneado para MText (`Sanear`)
1. `ToUpperInvariant()` y quitar tildes (normalización FormD, eliminando las `NonSpacingMark`).
2. Escapar: `\` → `\\`, `{` → `\{`, `}` → `\}`.
3. Conservar la constante `GRADO` (`%%d`) en minúscula: se sustituye por un marcador antes de pasar a mayúsculas y se repone después.
4. Se aplica a cada línea ANTES de unirlas con `\P`: el `\P` separador no se escapa.
- Se aplica a callouts, tramos, cruces, título y nombres de red o estructura. romans.shx no tiene glifos con tilde.

---

## I. Riesgos de ejecución y mitigación en el código

| # | Riesgo | Mitigación |
|---|---|---|
| I-1 | Unidades de las distancias de ploteo, y CANNOSCALE ≠ DrawingScale. | `FactorPl` inicial: 1/12, o 0.0254 en metros. Autodetección con `hf` = `BottomAxis.MajorTickStyle.TextHeight` de la base de fábrica: `0.004 ≤ hf ≤ 0.03` confirma 1/12; `0.05 ≤ hf ≤ 0.5` → `FactorPl = 1`. Después, calibración por medida (F.10, G.6–G.7): una razón uniforme corrige `FactorPl` y recrea estilos y etiquetas. Se registran `DrawingScale`, `Cannoscale.*` y `CurrentHorizontalScale`. |
| I-2 | Composed + rotación al arrastrar: el texto podría perder los 90° o engancharse la flecha en un punto raro. | `DisplayType = Composed`. La prueba de humo (J) lo mide antes de usarlo. T5 corrige con bordes fiables. Con la proporción invertida → `ResetLocation()` y aviso. |
| I-3 | Semántica de `DimensionAnchor`. | No se usa. |
| I-4 | Marcador Null en `StationElevationLabel.Create`. | Siempre se pasa el marcador invisible; reintento con Null; si falla, se omite. |
| I-5 | `\P` y `%%d` dentro del override. | T2 detecta un bloque de n líneas medido como si fuera 1 línea → se reescribe con `"  "` entre líneas y se avisa `[FORMATO]`. `%%d`: si sale literal, se cambia la constante `GRADO` a `"\u00B0"`. J lo verifica. |
| I-6 | `StationStart` fuera del eje. | Prolongaciones `EXT_EJE`; rango acotado a `[StartingStation, EndingStation]`. |
| I-7 | `GeometricExtents` sin regenerar. | Transacciones separadas, `QueueForGraphicsFlush` + `FlushGraphics` tras cada commit y lecturas en try. Extensión nula → predicción con aviso. |
| I-8 | Captura del `ProfileViewPart`. | T1a/T1b separados, manejador activo hasta después del commit, ventanas por llamada y respaldos. Sin id → cruce sin etiqueta y aviso. |
| I-9 | Nombre de la flecha. | Se hereda de la base; nunca se escribe un literal. |
| I-10 | `AnchorComponent/AnchorLocation` del componente nuevo. | No se tocan; se registran. |
| I-11 | Componentes de fábrica en estilos propios, en español. | Purga SIEMPRE de todo lo que no sea `PDFCAD_TEXTO`. Profundidad: tokens sin literales. |
| I-12 | Linetype con tilde. | `"L\u00CDNEAS_OCULTAS"` y cadena de alternativas. |
| I-13 | Offsets de fábrica de los números y títulos de eje. | No se tocan. «STATION (FT)», extremos y título se colocan midiendo `pv.GeometricExtents` (G.11). |
| I-14 | Signo del bulge. | Comprobación con el punto medio del arco real (C.2-3, C.3-2): si falla, cuerda con aviso. |
| I-15 | Reapilar vistas con `pv.Location`. | Solo en T3, antes de arrastrar etiquetas. Se registra un `FindXY` de control; si no siguen, las etiquetas se colocan igual en T4 con el `FindXY` nuevo, porque el cálculo es relativo al ancla actual. |
| I-16 | Huecos visuales del tubo de presión en los accesorios. | Es la geometría real. El callout identifica el accesorio y ancla en el extremo de tubo más cercano (H.3). Log `[PRESION] huecos: n`. |
| I-17 | Override vacío o componente no encontrado. | Mínimo `" "`. Sin `PDFCAD_TEXTO` → se usa el primer id y se avisa. |
| I-18 | `ElevationMin > ElevationMax` transitorio. | Orden seguro y set en try. Se registra el rango leído. |
| I-19 | Lado de enganche del leader. | En texto vertical, el lado depende de la posición VERTICAL del ancla respecto al bloque, que es fija en cada franja. Con `LeaderJustification = true` la franja superior engancha abajo y la inferior arriba, como en las referencias. En horizontales, `false` (lado fijo). J lo verifica. Si no se cumple, cambiar la constante `JUSTIFICAR_LEADER_VERTICAL`. |
| I-20 | Máscaras frente a líneas de límite y cotas. | `DrawOrderTable.MoveToBottom` de límites y profundidades. |
| I-21 | Más de una etiqueta devuelta por la etiqueta de cruce. | Se queda la de estación más cercana; el resto se borra. |

---

## J. Prueba de humo `PDFCAD_PERFIL_PRUEBA` (`PerfilPruebaHumo.cs`)

Objetivo: validar I-1, I-2, I-5 e I-19 en Civil 3D en 1 minuto.

**Flujo**
1. Se pide una `ProfileView` existente.
2. En una transacción: estilos (E.8) y dos etiquetas `StationElevationLabel`, en `(StationStart + 30%, zMedia)` con Callout Sup y en `(… + 60%, zMedia)` con Callout Inf. El texto es `"PIPE STA 1+00.00\\P8\" X 45%%d BEND\\PTOP ELEV 745.43'"`.
3. Commit y flush.
4. Registro de cada etiqueta:
   - `GeometricExtents`, `AnchorInfo.Location`, `LabelLocation`, `Dragged`, `RotationAngle`;
   - razón ancho/alto frente a la predicha, y `r` de F.10.
5. Arrastre de cada etiqueta con `LabelLocation += (0, ±1.5"·S)` y `LeaderVisibility = FromLabelStyle`. Commit y flush.
6. Se registran de nuevo los extents, y además:
   - el punto de enganche aproximado: la esquina de los extents más cercana al ancla;
   - si el texto sigue vertical (Alto > Ancho);
   - si `%%d` se ve como «°»: comprobación visual indicada en el mensaje.

**Mensaje final.** En español, con los valores clave:
- `FactorPl` sugerido;
- vertical OK / NO;
- enganche superior / inferior;
- ruta del log.

---

## K. Críticas descartadas

- **API-5 (parte)**, usar `M_ef` en todas las conversiones: se corrige `FactorPl` (los textos) y se mantiene `S` para la escala del marco, porque el título declara `HORIZ 1"=S'` y la rejilla depende de `S`.
- **API-10 / P0-8 (parte)**, `LeaderJustification = false` en los callouts verticales: en texto vertical el lado depende de la posición vertical del ancla, que nunca cambia en una franja; `true` pone el leader en el extremo cercano al tubo en ambas franjas (referencias). `false` sí se usa en los horizontales, y J lo verifica.
- **API-12 (parte)**, prefijo `"COVER "` en los recubrimientos: las referencias muestran solo el valor («5.83'»); se deja únicamente el token.
- **P0-1 (parte)**, renombrar el archivo a `DISENO_TECNICO.md`: el orquestador y los revisores apuntan a `DISENO.md`; la pérdida se resuelve con la sección 0 (documento autocontenido) y sin citas a `diseno.md`.
- **P0-5 (paso 3)**, bajar la VE como regla «si no cabe»: el desborde es horizontal y la VE no crea espacio horizontal; la VE solo se baja por altura (F.3).
- **P1-3 (c)**, crear todos los tramos en T4 midiéndolos por predicción: se crean en T1 para medirlos (`KMedida`) y solo los de fila 2 se recrean en T4 con el ancla definitiva.
- **Arnés-12 (valores)**, centros 9.07/9.74 para el ideal [8.9, 9.9]: con el algoritmo exacto F.5 esa pareja no se fusiona (8.90/9.74); el caso de fusión en cascada por clamp usa [9.2, 9.9] → 9.07/9.74 (E8).
- **P1-2 (parte)**, desplazar el GRUPO completo que cae sobre una pared: se sustituye por segmentos entre paredes activas (F.6.b), que es determinista y comprobable; lo que aún quede sobre una pared se avisa y la máscara tapa la vertical.
- **Cota horizontal con flechas en la fila (50.png)**: ninguna etiqueta nativa de vista de perfil dibuja una cota horizontal de largo variable; `ProfileViewDepthLabel` mide diferencias de cota. Queda fuera (API-17) y la celda se marca con las verticales de límite.

---

## L. Lista de verificación de implementación

**Compilación y estructura**
- [ ] `dotnet build -c Release` en `proyecto1`: 0 errores y ningún CS0618 nuevo (sin `DraggedOffset =`).
- [ ] Todos los archivos nuevos tienen < 500 líneas, namespace `Civil3DBasico`, comentarios en español y una responsabilidad cada uno (A.1).
- [ ] Los 5 archivos puros no tienen ningún `using Autodesk*`. El arnés `PerfilPruebas` compila solo con ellos y `dotnet run` devuelve 0.
- [ ] Un único `[CommandMethod("CREAR_PERFIL_PRESION")]` en todo el ensamblado, el alias. Borrado el de `RedesPresionRamales.cs`.
- [ ] `CrearPerfilRed` eliminado de `AlineamientosPerfiles.cs`. Las dos sobrecargas existentes funcionan igual para ImportarRed.
- [ ] Arreglo del huérfano exactamente como en D.2 (`pl` fuera del try; `IsWriteEnabled` antes de `UpgradeOpen`).
- [ ] `PerfilUtil.cs` y `PerfilLongitudinalDatos.cs` borrados, después de comprobar con grep que no hay referencias.
- [ ] Subtítulo de `PanelPipe.xaml` actualizado.

**Recorrido y grafo**
- [ ] Los tubos degenerados (`dist2D < 1 ft`) se excluyen del grafo y de los cruces, y quedan registrados en `Verticales`.
- [ ] Al pinchar una tubería vertical sale el mensaje de C.1 y no se crea nada.
- [ ] `TryUnit` nunca devuelve NaN. `Continuacion` descarta δ NaN y ordena con un comparador explícito.
- [ ] Presión: accesorios aceptados sin filtrar por `RED`, asignación 3D (`dz`), `Ralc` con `LARGO_TOTAL_FT` y desempate por red, con log.
- [ ] Bulge verificado con el punto medio real (gravedad: `Curve2d`; presión: `GetPointAtParameter`). `Segmented/Flex` → cuerda.
- [ ] Traza sin vértices colineales ni duplicados. Error claro si quedan menos de 2 vértices.
- [ ] Ramal vertical detectado (`VERT BRANCH UP/DOWN`) y codo terminal `VERT`.

**Eje, vista y partes**
- [ ] Nombre único que incluye los ejes siteless y de sitios, y los nombres de las hojas `- H{k}`.
- [ ] Eje en la capa `PDFCAD_PERFIL_EJE`; `StationOffset(N0)` = 100.00 ± 0.01 (log).
- [ ] Terreno muestreado en T0 con `FindElevationAtXY`, cada muestra en su try. Sin superficie → sin terreno, con aviso.
- [ ] Una `ProfileView` por hoja (`PartirEnHojas`), apiladas y reapiladas en T3.
- [ ] Rango en `UserSpecified` en orden seguro, bandas vacías y vista en `PDFCAD_PERFIL`.
- [ ] `AddToProfileView` con la parte ForWrite. `ObjectAppended` suscrito hasta DESPUÉS del commit de T1a y desuscrito en un `finally`.
- [ ] Overrides aplicados en T1b; los ids que falten van al log.
- [ ] Cruces agrupados: una etiqueta por grupo. Colección vacía → aviso; varias → se queda la más cercana.

**Estilos**
- [ ] Idempotentes: re-ejecutar no duplica. Los nombres llevan VE, intervalos, `S` y `SufijoPl` donde corresponde.
- [ ] Base de `CopyAsSibling` y del diagnóstico = primer estilo que no empieza por «PDFCAD».
- [ ] Purga de todo componente que no se llame `PDFCAD_TEXTO` en los estilos propios, SIEMPRE.
- [ ] Juegos de etiquetas vaciados con `RemoveAt` hasta `Count == 0`.
- [ ] `BottomAxisTitle` apagado y «STATION (FT)» puesto como etiqueta. Títulos de eje a 0.10".
- [ ] `LabelText` de ejes y `Contents` de profundidad sin literales en español (solo tokens).
- [ ] `DraggedStateComponents`: `MaxTextWidth = 0`, `LeaderJustification` según E.8, `Composed`.

**Etiquetas y textos**
- [ ] Textos del plano en inglés, en MAYÚSCULAS, sin tildes y escapados (H.8). `%%d` conservado.
- [ ] Mensajes de la línea de comandos en español con `✓ / ⚠ / ✗ / ·`.
- [ ] Nunca polilíneas, MText ni líneas sueltas: solo objetos Civil (Alignment, Profile, ProfileView, partes en la vista, etiquetas).
- [ ] Todas las etiquetas se crean con `LeaderVisibility = AlwaysHide` y se restauran en T4 según G.10.
- [ ] Tramos de fila 2 recreados en `(cx, cota de YFila1Base)` con leader.
- [ ] Límites siempre completos y enviados al fondo del orden de dibujo junto con las cotas de profundidad.
- [ ] Cota de separación solo si `CotaSeparacionCabe`; si no, línea `CLR` en el callout del cruce.

**Maquetación y transacciones**
- [ ] `Maquetar` preliminar en T0 con predicción, que fija `V` e `Int`. El final usa `VForzada`, y si cambia `V` se aplica un estilo nuevo, nunca se modifica el que está en uso.
- [ ] Calibración F.10; T2b solo con una razón uniforme; como mucho una corrección.
- [ ] `FindXYAtStationAndElevation`: se comprueba el `bool` y se usa el respaldo con log.
- [ ] `GeometricExtents` en try; flush tras cada commit.
- [ ] T5: hasta 3 iteraciones, cada una con commit y flush. Las que no convergen van al log.
- [ ] T6: solapes, fuera de marco, cruces de leaders y cortes con medidas reales → log y avisos.
- [ ] Prompts fuera de las transacciones. Un fallo parcial conserva lo logrado. El resumen trae los conteos de G.13.

**Pruebas en Civil 3D (manuales)**
- [ ] `PDFCAD_PERFIL_PRUEBA`: texto vertical conservado tras el arrastre, enganche superior abajo / inferior arriba, `%%d` → «°» y `FactorPl` sugerido coherente.
- [ ] Gravedad con buzones y un ramal: perfil con estructuras, inverts IN/OUT y ramal LT/RT.
- [ ] Conduit (estructuras nulas) y presión con TEE de conexión cruzada: el recorrido NO se corta en la conexión y el callout dice `VERT BRANCH`.
- [ ] Recorrido de más de 30" de marco: varias vistas apiladas y numeradas en el título.
- [ ] Red sin superficie: sin terreno ni recubrimientos, con aviso.
- [ ] Re-ejecución sobre la misma red: `PERFIL … (2)`, sin estilos duplicados y cruces con su etiqueta.
- [ ] Revisión visual contra 50.png y 51.png: ningún texto solapado, fuera del marco ni sobre una vertical de límite; leaders ≤ ~60° y sin cruzarse.
