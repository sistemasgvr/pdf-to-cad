using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;              // Pressure* viven aquí (en el ensamblado AeccPressurePipesMgd)
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;    // PressurePartList, colecciones, extensión de estilos
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA — Redes a PRESIÓN (Pressure Network)  [ver README y memoria]
//  ARCHIVO SEPARADO de la red de gravedad (RedesTuberia.cs) para no mezclar.
//  Necesita la referencia a AeccPressurePipesMgd.dll (ya añadida en el .csproj).
//
//  Anatomía:  PressurePipeNetwork  →  Pipes (rectos/curvos)  +  Fittings (codos/tees/reductores)  +  Appurtenances (válvulas)
//  Catálogo:  "Pressure Part List" (aparte del de gravedad). Cada pieza = objeto PressurePartSize.
//
//  API clave (2026):
//    - PressurePipeNetwork.Create(db, nombre) -> ObjectId
//    - civilDoc.Styles.GetPressurePartLists()  (método de extensión) -> PressurePartListCollection
//    - PressurePartList.GetParts(PressurePartDomainType Pipe/Fitting/Appurtenance) -> List<PressurePartSize>
//    - PressurePartSize: .Description, .PartType, .Domain, .GetProperty(PressurePartContextType)
//
//  Este archivo: corrección automática de los fittings de una red a presión,
//  que IMPORTAR_RED aplica a cada red que crea (CorregirFittingsDeRed). Las
//  junturas (qué accesorio va en cada unión) viven en RedesPresionJunturas.cs.
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Redes a presión (Pressure Network) que crea IMPORTAR_RED. Separado de la red de gravedad.
    /// </summary>
    public partial class ComandosPresion
    {
        // Detecta fittings cuyo TIPO no corresponde a sus conexiones reales
        // (p.ej. un Codo donde debería haber un Reductor o una Tee, según
        // DecidirTipoFitting) y/o cuyo DIÁMETRO no coincide con el del tubo
        // conectado, y los reemplaza por el fitting correcto de la Parts List
        // de la red. No detecta junturas que hoy no tienen NINGÚN accesorio
        // (solo audita fittings existentes). Corrige directo, sin preguntar
        // (uso automático al importar desde DXF). Devuelve (detectados,
        // corregidos, fallidos); (0,0,0) si la red no tiene fittings, no hay
        // Parts List de fittings, o todos ya coinciden.
        internal static (int Detectados, int Corregidos, int Fallidos) CorregirFittingsDeRed(
            CivilDB.PressurePipeNetwork net, Transaction tr, Editor ed)
        {
            PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

            var fittingIds = new List<ObjectId>();
            foreach (ObjectId id in net.GetFittingIds()) fittingIds.Add(id);
            ComandosRedes.Dl(ed, $"\n  [CORREGIR_FITTINGS] Red '{net.Name}': {fittingIds.Count} fitting(s) encontrados.");
            if (fittingIds.Count == 0) return (0, 0, 0);

            var partsDisp = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);
            ComandosRedes.Dl(ed, $"\n  [CORREGIR_FITTINGS] Parts List '{pl.Name}': {partsDisp?.Count ?? 0} fitting(s) disponibles en catálogo.");
            if (partsDisp == null || partsDisp.Count == 0) return (0, 0, 0);

            // Fase 1: detectar desajustes
            var reemplazos = new List<_ReemplazoInfo>();

            foreach (ObjectId fid in fittingIds)
            {
                CivilDB.PressureFitting fit = tr.GetObject(fid, OpenMode.ForRead) as CivilDB.PressureFitting;
                if (fit == null) { ComandosRedes.Dl(ed, "\n  [CORREGIR_FITTINGS] · (no es PressureFitting, se salta)"); continue; }

                // Diámetro NOMINAL del fitting, en pulgadas, leído de su descripción
                // de catálogo ("elbow-4 in-45 degree-..." → 4.0). NO se usa
                // fit.GetConnectionAt(p).OutsideDiameter: ese valor resultó ser el
                // diámetro EXTERIOR del socket/campana del accesorio (más grande que
                // el tubo, por diseño — así encaja el tubo adentro), no el nominal, y
                // además viene en pulgadas fijas sin importar las unidades del dibujo
                // — comparado contra PressurePipe.OuterDiameter (en las unidades del
                // dibujo, pies) daba una "diferencia" enorme SIEMPRE, sin importar si
                // el tamaño era correcto o no.
                double fitDia = ExtraerDiametroDeDescripcion(fit.PartDescription);
                string descOriginal = "?"; try { descOriginal = fit.PartDescription; } catch { }
                if (fitDia <= 0)
                {
                    ComandosRedes.Dl(ed, $"\n  [CORREGIR_FITTINGS] · '{descOriginal}': no se pudo leer su diámetro de la descripción, se salta.");
                    continue;
                }

                var conexiones = new List<_ConexionInfo>();
                var pipesConectados = new List<CivilDB.PressurePipe>();
                // CONFIRMADO EMPÍRICAMENTE (log real de IMPORTAR_RED): un tubo cuya
                // propia descripción de catálogo dice "12 in" (descDia=12.0, parseado
                // de texto) tiene NominalDiameter=1.000 — es decir, PressurePipe.
                // NominalDiameter/OuterDiameter vienen en las UNIDADES DEL DIBUJO
                // (pies, ya que IMPORTAR_RED fuerza el dibujo a Feet), no en pulgadas.
                // El comentario en ImportarRed.cs junto a "(pp.NominalDiameter / 12.0)
                // / 2.0" decía lo contrario y estaba MAL — ver el fix de esa línea ahí.
                double pipeNomDiaMaxIn = 0;   // pulgadas (se convierte ×12 abajo)

                for (int p = 0; p < fit.ConnectionCount; p++)
                {
                    CivilDB.PressurePartConnection conn = fit.GetConnectionAt(p);
                    if (conn.ConnectedId == ObjectId.Null || !conn.ConnectedId.IsValid) continue;
                    try
                    {
                        CivilDB.PressurePipe pipe = tr.GetObject(conn.ConnectedId, OpenMode.ForRead) as CivilDB.PressurePipe;
                        if (pipe == null) continue;
                        int pipePort = (fit.Position.DistanceTo(pipe.StartPoint) <= fit.Position.DistanceTo(pipe.EndPoint)) ? 0 : 1;
                        conexiones.Add(new _ConexionInfo { PipeId = conn.ConnectedId, PipePort = pipePort, FitPort = p });
                        pipesConectados.Add(pipe);
                        string pipeDescOwn = "?"; try { pipeDescOwn = pipe.PartDescription; } catch { }
                        double pipeDescDia = ExtraerDiametroDeDescripcion(pipeDescOwn);
                        double nomIn = pipe.NominalDiameter * 12.0;
                        ComandosRedes.Dl(ed, $"\n  [CORREGIR_FITTINGS]     tubo conectado: '{pipeDescOwn}' — " +
                                        $"NominalDiameter={pipe.NominalDiameter:F3}ft ({nomIn:F1}in), descDia={pipeDescDia:F1}in");
                        if (nomIn > pipeNomDiaMaxIn) pipeNomDiaMaxIn = nomIn;
                    }
                    catch { }
                }

                // Tipo que DEBERÍA tener este accesorio según sus conexiones reales
                // (misma decisión que usa el import automático — ver
                // DecidirTipoFitting). d1/d2 en pies (unidades del dibujo) — la
                // comparación de DecidirTipoFitting es solo d1==d2, no le importa
                // la unidad mientras sea la MISMA en ambos lados. Para 2 tubos hace
                // falta la deflexión real, calculada desde el extremo LEJANO de cada
                // tubo respecto a la posición del accesorio (mismo cálculo que
                // ProcesarJunturasPresion).
                double deflex = 0;
                if (conexiones.Count == 2)
                {
                    Point3d far0 = conexiones[0].PipePort == 0 ? pipesConectados[0].EndPoint : pipesConectados[0].StartPoint;
                    Point3d far1 = conexiones[1].PipePort == 0 ? pipesConectados[1].EndPoint : pipesConectados[1].StartPoint;
                    Vector3d v1 = far0 - fit.Position, v2 = far1 - fit.Position;
                    deflex = 180.0 - v1.GetAngleTo(v2) * 180.0 / Math.PI;
                }
                // Para 3 tuberías, Tee vs Wye se decide por la MISMA geometría de
                // ángulos que usó la colocación (DecidirTeeOWye) — si no, esta
                // corrección degradaría a Tee cualquier Wye bien puesto (el bug que
                // reportó el usuario: 'Wye 75_ …' → 'tee-…'). DecidirTipoFitting
                // solo sabe devolver Tee para 3 miembros.
                CivilDB.PressurePartType? tipoCorrecto;
                if (conexiones.Count == 3 && pipesConectados.Count == 3)
                {
                    var vecs = new List<Vector3d>();
                    for (int i = 0; i < 3; i++)
                    {
                        Point3d far = conexiones[i].PipePort == 0
                            ? pipesConectados[i].EndPoint : pipesConectados[i].StartPoint;
                        vecs.Add(far - fit.Position);
                    }
                    tipoCorrecto = DecidirTeeOWye(vecs);
                }
                else
                {
                    tipoCorrecto = DecidirTipoFitting(conexiones.Count,
                        pipesConectados.Count > 0 ? pipesConectados[0].NominalDiameter : 0,
                        pipesConectados.Count > 1 ? pipesConectados[1].NominalDiameter : 0,
                        deflex);
                }

                ComandosRedes.Dl(ed, $"\n  [CORREGIR_FITTINGS] · '{descOriginal}' ({fit.PartType}): fitDiaNominal={fitDia:F2}in, conexiones={conexiones.Count}, " +
                                $"pipeNomDiaMax={pipeNomDiaMaxIn:F2}in, tipoCorrecto={tipoCorrecto}");

                if (pipeNomDiaMaxIn <= 0 || conexiones.Count == 0) continue;
                bool tipoDesajustado = tipoCorrecto.HasValue && tipoCorrecto.Value != fit.PartType;
                bool tamanoDesajustado = Math.Abs(fitDia - pipeNomDiaMaxIn) >= 0.5;
                if (!tipoDesajustado && !tamanoDesajustado) continue;

                double? angulo = ExtraerAnguloDeDescripcion(fit.PartDescription);

                reemplazos.Add(new _ReemplazoInfo
                {
                    FittingId = fid,
                    Posicion = fit.Position,
                    Tipo = tipoCorrecto ?? fit.PartType,
                    Angulo = angulo,
                    DiametroCorrecto = pipeNomDiaMaxIn,
                    Conexiones = conexiones,
                    DescVieja = fit.PartDescription
                });
            }

            if (reemplazos.Count == 0) return (0, 0, 0);

            // Fase 2: reemplazar
            int corregidos = 0, fallidos = 0;

            foreach (var r in reemplazos)
            {
                PresStyles.PressurePartSize nuevaPieza = _BuscarPiezaCorrecta(partsDisp, r.Tipo, r.DiametroCorrecto, r.Angulo);
                if (nuevaPieza == null)
                {
                    ed.WriteMessage($"\n  ✗ No hay {r.Tipo} Ø{r.DiametroCorrecto:F0}" +
                                    (r.Angulo != null ? $" {r.Angulo}°" : "") + " en la Parts List.");
                    fallidos++;
                    continue;
                }

                try
                {
                    // Desconectar tubos del fitting viejo
                    CivilDB.PressureFitting fitViejo = (CivilDB.PressureFitting)tr.GetObject(r.FittingId, OpenMode.ForWrite);
                    foreach (var c in r.Conexiones)
                    {
                        try
                        {
                            CivilDB.PressurePipe pipe = (CivilDB.PressurePipe)tr.GetObject(c.PipeId, OpenMode.ForWrite);
                            _DesconectarPipeDeFitting(pipe, r.FittingId);
                        }
                        catch { }
                    }

                    // Borrar fitting viejo
                    fitViejo.Erase();

                    // Colocar fitting nuevo (Wye necesita su catálogo Steel activo)
                    if (nuevaPieza.PartType == CivilDB.PressurePartType.Wye)
                        AsegurarPresionWye.ActivarCatalogo(ed);
                    ObjectId nuevoId = net.AddFitting(r.Posicion, nuevaPieza);
                    CivilDB.PressurePart parteNueva = (CivilDB.PressurePart)tr.GetObject(nuevoId, OpenMode.ForWrite);

                    // Reconectar tubos
                    int conectados = 0;
                    for (int i = 0; i < Math.Min(parteNueva.ConnectionCount, r.Conexiones.Count); i++)
                    {
                        var c = r.Conexiones[i];
                        try { parteNueva.ConnectToPipe(i, c.PipeId, c.PipePort); conectados++; }
                        catch { }
                    }

                    // Recortar tubos al puerto del nuevo fitting
                    try
                    {
                        for (int i = 0; i < parteNueva.ConnectionCount; i++)
                        {
                            CivilDB.PressurePartConnection conn = parteNueva.GetConnectionAt(i);
                            if (conn.ConnectedId == ObjectId.Null || !conn.ConnectedId.IsValid) continue;
                            CivilDB.PressurePipe pipe = tr.GetObject(conn.ConnectedId, OpenMode.ForWrite) as CivilDB.PressurePipe;
                            if (pipe == null) continue;
                            if (conn.Position.DistanceTo(pipe.StartPoint) < conn.Position.DistanceTo(pipe.EndPoint))
                                pipe.StartPoint = conn.Position;
                            else
                                pipe.EndPoint = conn.Position;
                        }
                    }
                    catch { }

                    // No hace falta reajustar la Z: la pieza nueva nace en r.Posicion,
                    // que es el Position del fitting VIEJO (ya a nivel de eje), y
                    // escribir Position sobre una pieza ya conectada arrastraría los
                    // tubos sin corregir el desfase relativo (ver nota en
                    // ProcesarJunturasPresion, RedesPresionJunturas.cs).
                    ed.WriteMessage($"\n  ✓ {r.Tipo}: '{r.DescVieja}' → '{nuevaPieza.Description}' ({conectados} conexión(es))");
                    corregidos++;
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n  ✗ Error reemplazando {r.Tipo}: {ex.Message}");
                    fallidos++;
                }
            }

            return (reemplazos.Count, corregidos, fallidos);
        }

        private static PresStyles.PressurePartSize _BuscarPiezaCorrecta(
            List<PresStyles.PressurePartSize> partes,
            CivilDB.PressurePartType tipo, double diametro, double? angulo)
        {
            PresStyles.PressurePartSize mejorConAngulo = null;
            PresStyles.PressurePartSize mejorSinAngulo = null;

            foreach (var p in partes)
            {
                if (p.PartType != tipo) continue;
                string desc = p.Description ?? "";

                // Verificar que el primer diámetro en la descripción coincida
                double primerDia = ExtraerDiametroDeDescripcion(desc);
                if (primerDia <= 0 || Math.Abs(primerDia - diametro) > 1.0) continue;

                double? candAng = ExtraerAnguloDeDescripcion(desc);
                if (angulo.HasValue && candAng.HasValue && Math.Abs(candAng.Value - angulo.Value) < 0.5)
                {
                    mejorConAngulo = p;
                    break;
                }
                if (mejorSinAngulo == null) mejorSinAngulo = p;
            }
            return mejorConAngulo ?? mejorSinAngulo;
        }

        private static void _DesconectarPipeDeFitting(CivilDB.PressurePipe pipe, ObjectId fittingId)
        {
            try
            {
                for (int port = 0; port < 2; port++)
                {
                    CivilDB.PressurePartConnection conn = pipe.GetConnectionAt(port);
                    if (conn.ConnectedId == fittingId) { pipe.DisconnectAt(port); return; }
                }
            }
            catch { }
        }

        private class _ConexionInfo { public ObjectId PipeId; public int PipePort; public int FitPort; }
        private class _ReemplazoInfo
        {
            public ObjectId FittingId;
            public Point3d Posicion;
            public CivilDB.PressurePartType Tipo;
            public double? Angulo;
            public double DiametroCorrecto;
            public List<_ConexionInfo> Conexiones;
            public string DescVieja;
        }
    }
}
