using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;

// ============================================================================
//  MODELO DE DATOS DEL PERFIL LONGITUDINAL (DISENO.md, sección B.1)
//   · Clases de datos con ObjectId, SIN lógica. Las comparten todos los
//     módulos Perfil*.cs (comando, grafo, eje, estilos, vista, etiquetas).
//   · Unidades: planta y cotas en PIES; diámetros de texto en PULGADAS;
//     ángulos en GRADOS; maquetación en PULGADAS DE PLOTEO.
//   · Los tipos puros que se usan aquí (V2Bulge, GNodo, GArista, FranjaTipo,
//     BloqueTexto, FilaTramo, ResultadoMaquetacion, Intervalos) viven en
//     PerfilRecorrido.cs y PerfilDiseno.cs (sin Autodesk).
//   · Los campos marcados «[contrato]» no están en B.1: se añadieron en el
//     esqueleto para que los módulos se pasen datos sin chocar.
// ============================================================================

namespace Civil3DBasico
{
    internal enum TipoRed { Gravedad, Conduit, Presion }
    internal enum TipoNodo { Estructura, EstructuraNula, Accesorio, Union, Extremo }
    internal enum TipoAccesorio { Ninguno, Codo, Tee, Wye, Cruz }

    /// <summary>Nodo del grafo de la red (estructura, accesorio sólido, unión o extremo libre). B.1.</summary>
    internal sealed class NodoPerfil
    {
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

    /// <summary>Una arista = UNA tubería NO degenerada (C.2 / C.3). B.1.</summary>
    internal sealed class TramoRed
    {
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

    /// <summary>Tubo degenerado (conexión vertical), excluido del grafo. B.1.</summary>
    internal sealed class VerticalConexion
    {
        public double X, Y, ZMin, ZMax; public string Red = ""; public ObjectId PipeId;
    }

    /// <summary>Red leída de Civil 3D: nodos, tramos, verticales y grafo puro. B.1.</summary>
    internal sealed class RedPerfil
    {
        public TipoRed Tipo; public ObjectId RedId; public string NombreRed = "";
        public ObjectId SuperficieId = ObjectId.Null;
        public List<NodoPerfil> Nodos = new List<NodoPerfil>();
        public List<TramoRed> Tramos = new List<TramoRed>();
        public List<VerticalConexion> Verticales = new List<VerticalConexion>();
        public List<GNodo> GNodos = new List<GNodo>();
        public List<GArista> GAristas = new List<GArista>();
    }

    /// <summary>Paso del recorrido: un tramo recorrido de NodoDesde a NodoHasta. B.1.</summary>
    internal sealed class PasoRecorrido
    {
        public TramoRed Tramo;
        public bool Invertido;                           // true = se recorre B→A
        public int NodoDesde, NodoHasta;
        public double EstDesde, EstHasta;                // estaciones de los NODOS
        public double EstPIni, EstPFin;                  // estaciones de los extremos reales del tubo (sentido de avance)
        public double ZIni, ZFin;                        // cota de eje en esos extremos (sentido de avance)
    }

    /// <summary>Arista que sale del recorrido en un nodo (C.4, ramales). B.1.</summary>
    internal sealed class Ramal
    {
        public int NodoId; public TramoRed Tramo; public double DiamIn;
        public string Lado = "";                         // "LT" | "RT"
        public double AnguloDeg; public bool EntraAlNodo;
    }

    /// <summary>Recorrido principal con estaciones, traza del eje y terreno muestreado. B.1.</summary>
    internal sealed class Recorrido
    {
        public RedPerfil Red;
        public List<int> Nodos = new List<int>();                     // orden de estación creciente
        public List<PasoRecorrido> Pasos = new List<PasoRecorrido>();  // Pasos[i]: Nodos[i] → Nodos[i+1]
        public Dictionary<int, double> EstNodo = new Dictionary<int, double>();
        public Dictionary<int, List<Ramal>> Ramales = new Dictionary<int, List<Ramal>>();
        public double EstIni, EstFin;                                 // EstIni = 100.00
        public List<V2Bulge> Traza = new List<V2Bulge>();
        public double DistN0;                                         // distancia sobre la traza hasta N0
        public double[] TerrenoEst = new double[0], TerrenoZ = new double[0]; // D.4 (NaN = sin superficie)
        // [contrato] rango del eje (D.3): preliminar en T0 (traza), definitivo en T1a (Starting/EndingStation)
        public double EstMinPermitida, EstMaxPermitida;
    }

    /// <summary>Tubería de otra red que cruza el recorrido (C.7). B.1.</summary>
    internal sealed class Cruce
    {
        public ObjectId PipeId; public bool EsPresion, EsGravedad; public string Red = "";
        public double Estacion, ZEje, DiamIn, AltoExtFt, RadioIntFt, AnguloDeg, ClaroFt;
        public string Material = ""; public bool Abandonado, Encima;
        public int Grupo = -1; public bool EtiquetaDelGrupo;          // F.11: solo uno por grupo lleva etiqueta
        public List<ObjectId> PvPartIds = new List<ObjectId>();       // uno por hoja en que aparece
        public List<ObjectId> EtiquetaIds = new List<ObjectId>();
        // [contrato] punto de corte en planta (ft), para la estación definitiva con StationOffset (T1a)
        public double X, Y;
        // [contrato] hojas en que aparece (paralelo a PvPartIds; -1 = sin parte resuelta)
        public List<int> Hojas = new List<int>();
    }

    /// <summary>Rótulo vertical (callout) de nodo, cruce, rasante o tramo desbordado. B.1.</summary>
    internal sealed class Callout
    {
        public string Id = "", Tipo = "";   // "INICIO","FIN","TEE","WYE","CRUZ","CODO","DEFLEXION","REDUCCION","ESTRUCTURA","CRUCE","TERRENO","TRAMO"
        public FranjaTipo Franja; public int Prioridad;
        public bool PuedeCambiarFranja, PuedeAlternar = true, PuedeRecortar;
        public double Estacion, EstAncla, ZAncla;        // Estacion = la del texto; EstAncla/ZAncla = punta de la flecha
        public List<string> Lineas = new List<string>(); // saneadas (H.8)
        public int Hoja;
        public ObjectId EtiquetaId = ObjectId.Null;
        public BloqueTexto Bloque;
        // [contrato] índice del cruce representante (solo Tipo "CRUCE"; -1 en el resto)
        public int CruceIdx = -1;
    }

    /// <summary>Rótulo horizontal de tramo en la fila superior (H.4 / F.7). B.1.</summary>
    internal sealed class RotuloTramo
    {
        public string Id = ""; public double EstIni, EstFin; public string L1 = "", L2 = "", L3 = "";
        public int Hoja; public bool Omitido;
        public ObjectId EtiquetaId = ObjectId.Null; public FilaTramo Fila;
    }

    /// <summary>[contrato] Medida de una etiqueta (G.6): caja relativa a su ancla, en PULGADAS de ploteo.</summary>
    internal sealed class MedidaEtiqueta
    {
        public string Id = "";                           // = Callout.Id / RotuloTramo.Id
        public ObjectId EtiquetaId = ObjectId.Null;
        public double EstAncla, ZAncla;                  // ancla usada al medir (ft)
        public double RelMinX, RelMinY, RelMaxX, RelMaxY; // (ext − ancla)/S, in
        public bool Valida;                              // false = se usó la predicción ([MEDIDA])
        public double Ancho { get { return RelMaxX - RelMinX; } }
        public double Alto { get { return RelMaxY - RelMinY; } }
    }

    /// <summary>Una ProfileView (F.11 hojas). B.1.</summary>
    internal sealed class HojaPerfil
    {
        public int Indice; public string Nombre = "";
        public double EstA, EstB;                        // rango de nodos que cubre
        public Point3d Insercion; public ObjectId PvId = ObjectId.Null;
        public ResultadoMaquetacion Prelim, Final;
        public List<Callout> Callouts = new List<Callout>();
        public List<RotuloTramo> Rotulos = new List<RotuloTramo>();
        public List<ObjectId> EtiquetasVista = new List<ObjectId>();  // título, STATION, extremos, profundidades, límites
        // [contrato] datos de fases posteriores
        public List<int> Cruces = new List<int>();                    // índices en ContextoPerfil.Cruces
        public EntradaMaquetacion EntradaFinal;                      // la usada en el Maquetar final (G.8)
        public Dictionary<string, MedidaEtiqueta> Medidas = new Dictionary<string, MedidaEtiqueta>();
        public List<ObjectId> AlFondo = new List<ObjectId>();         // límites, recubrimientos, separaciones (G.10-8)
        public ObjectId TituloId = ObjectId.Null, EjeTituloId = ObjectId.Null;
        public ObjectId EstStartId = ObjectId.Null, EstEndId = ObjectId.Null;
    }

    /// <summary>Ids de capas y estilos creados en E (ObjectId.Null = no disponible → se omite con aviso). B.1.</summary>
    internal sealed class EstilosPerfil
    {
        public ObjectId CapaId, CapaEjeId, VistaStyle, BandSetVacio, TerrenoStyle, LabelSetPerfilVacio, EjeStyle, LabelSetEjeVacio,
            TuboGrav, TuboGravAband, CruceGrav, TuboPres, TuboPresAband, CrucePres, Estructura, SinMarcador,
            CalloutSup, CalloutInf, Tramo, Rasante, Titulo, EstExtremo, EjeTitulo, CruceGravLbl, CrucePresLbl, Profundidad, Limite;
        public string Linetype = "Continuous"; public double LinetypeEscala = 1.0;
        public double FactorPl; public string SufijoPl = "";
    }

    /// <summary>Conteos del resumen final (G.13). B.1.</summary>
    internal sealed class ResumenPerfil { public int Tubos, Estructuras, Cruces, GruposCruce, Callouts, Rotulos, Profundidades, Hojas; }

    /// <summary>[contrato] Rol de una parte añadida a una vista: decide el override de estilo (G.5-2).</summary>
    internal enum RolParte { Recorrido, RecorridoAbandonado, Cruce, Estructura }

    /// <summary>[contrato] Parte de modelo añadida a una hoja y su ProfileViewPart resuelto (G.4-5 / G.5-1).</summary>
    internal sealed class ParteEnVista
    {
        public ObjectId ModeloId = ObjectId.Null;        // Pipe / Structure / PressurePipe
        public bool EsPresion;
        public int Hoja;
        public RolParte Rol;
        public int CruceIdx = -1;                        // si Rol == Cruce: índice en ContextoPerfil.Cruces
        public List<ObjectId> Capturados = new List<ObjectId>();   // ids llegados por ObjectAppended en su ventana
        public ObjectId PvPartId = ObjectId.Null;        // resuelto en T1b
    }

    /// <summary>
    /// [contrato] Estado compartido del comando entre fases T0…T6 (G). Lo crea y lo
    /// posee ComandosPerfil; los módulos lo leen y rellenan sus partes.
    /// </summary>
    internal sealed class ContextoPerfil
    {
        public Document Doc; public Editor Ed; public Database Db; public CivilDocument CivDoc;
        public double S = 20.0;                          // DrawingScale (ft por in de ploteo)
        public bool Metros;                              // DrawingUnits == Meters (G.0)
        public double FactorPl, FactorPlInicial;         // I-1 / F.10
        public string OrigenFactorPl = "";
        public ObjectId EntidadId = ObjectId.Null;       // entidad elegida en el prompt 1
        public Point3d PuntoInsercion;                   // prompt 2
        public RedPerfil Red; public Recorrido Rec;
        public List<Cruce> Cruces = new List<Cruce>();
        public List<VerticalConexion> VerticalesTodas = new List<VerticalConexion>(); // de todas las redes de presión (C.3-6)
        public List<Callout> Callouts = new List<Callout>();          // globales (antes de repartir por hoja)
        public List<RotuloTramo> Rotulos = new List<RotuloTramo>();
        public List<HojaPerfil> Hojas = new List<HojaPerfil>();
        public double V; public Intervalos Int;          // V global (el mayor de todas las hojas) e intervalos
        public string Nombre = ""; public int Numero;    // D.1: "PERFIL {red} ({n})"
        public ObjectId AlignId = ObjectId.Null, TerrenoId = ObjectId.Null;
        public bool SinSuperficie;
        public EstilosPerfil Estilos;
        public List<ParteEnVista> Partes = new List<ParteEnVista>();
        public ResumenPerfil Resumen = new ResumenPerfil();
    }
}
