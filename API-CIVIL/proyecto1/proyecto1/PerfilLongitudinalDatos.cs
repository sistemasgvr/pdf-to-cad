using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;

// ============================================================================
//  PERFIL LONGITUDINAL — topología de la red a lo largo de su eje.
//   Como cada red de gravedad tiene UN único eje/alineamiento (creado por
//   IMPORTAR_RED a partir de la traza de la red), la cadena de buzones y
//   tramos es lineal: basta proyectar cada punto sobre el eje con
//   Alignment.StationOffset y ordenar por estación ascendente.
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilLongitudinalDatos
    {
        internal class NodoBuzon
        {
            public CivilDB.Structure St;
            public double Station;
            public double Invert;   // SumpElevation (fondo del buzón)
        }

        internal class TramoPipe
        {
            public CivilDB.Pipe P;
            public double StaIni, StaFin;
            public double InvIni, InvFin;
        }

        // Devuelve los buzones y tramos de la red, ordenados por estación
        // ascendente a lo largo del eje. Los buzones sin estación proyectable
        // (fuera del rango del eje) se descartan.
        internal static (List<NodoBuzon> Nodos, List<TramoPipe> Tramos) Ordenar(
            CivilDB.Network net, CivilDB.Alignment align, Transaction tr)
        {
            // Cada estructura/tubería se procesa en su propio try/catch: una que falle
            // al leer (p.ej. "Retrieve attribute failed" por un estado interno raro de
            // Civil3D en un buzón puntual) se salta en vez de tumbar todo el comando.
            var nodos = new List<NodoBuzon>();
            foreach (ObjectId sid in net.GetStructureIds())
            {
                try
                {
                    CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                    if (st == null) continue;
                    if (!TryStation(align, st.Location, out double sta)) continue;
                    nodos.Add(new NodoBuzon { St = st, Station = sta, Invert = st.SumpElevation });
                }
                catch { }
            }
            nodos.Sort((a, b) => a.Station.CompareTo(b.Station));

            var tramos = new List<TramoPipe>();
            foreach (ObjectId pid in net.GetPipeIds())
            {
                try
                {
                    CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                    if (p == null) continue;
                    if (!TryStation(align, p.StartPoint, out double staI)) continue;
                    if (!TryStation(align, p.EndPoint, out double staF)) continue;
                    var tramo = new TramoPipe
                    {
                        P = p,
                        StaIni = staI,
                        StaFin = staF,
                        InvIni = InvertEnNodo(p.StartStructureId, p.StartPoint, p, tr),
                        InvFin = InvertEnNodo(p.EndStructureId, p.EndPoint, p, tr)
                    };
                    // Normalizar para que StaIni sea siempre la estación menor (sentido de recorrido del eje)
                    if (tramo.StaIni > tramo.StaFin)
                    {
                        (tramo.StaIni, tramo.StaFin) = (tramo.StaFin, tramo.StaIni);
                        (tramo.InvIni, tramo.InvFin) = (tramo.InvFin, tramo.InvIni);
                    }
                    tramos.Add(tramo);
                }
                catch { }
            }
            tramos.Sort((a, b) => a.StaIni.CompareTo(b.StaIni));

            return (nodos, tramos);
        }

        // Rasante en un extremo de tubería: SIEMPRE Structure.SumpElevation cuando hay
        // estructura conectada — es el valor AUTORITATIVO que IMPORTAR_RED ya fijó
        // explícitamente desde el DXF, no una regla interna de Civil3D. (Antes se
        // probaba primero "rim − structure.get_PipeInvertDepth(idx)", pero esa regla de
        // Civil3D no aplica igual a tuberías conduit/eléctricas y desfasaba la cota —
        // ver CotarTuberias.cs.InvertEnNodo para el detalle del bug.)
        // Sin estructura conectada: cálculo geométrico eje − radio_interior.
        private static double InvertEnNodo(ObjectId structId, Point3d centerline, CivilDB.Pipe p, Transaction tr)
        {
            if (!structId.IsNull && structId.IsValid)
            {
                try
                {
                    var st = tr.GetObject(structId, OpenMode.ForRead) as CivilDB.Structure;
                    if (st != null) return st.SumpElevation;
                }
                catch { }
            }
            double r = 0.0;
            try { r = p.InnerDiameterOrWidth / 2.0; } catch { }
            return centerline.Z - r;
        }

        private static bool TryStation(CivilDB.Alignment align, Point3d pt, out double station)
        {
            station = 0.0;
            try
            {
                double sta = 0.0, offset = 0.0;
                align.StationOffset(pt.X, pt.Y, ref sta, ref offset);
                station = sta;
                return true;
            }
            catch { return false; }
        }
    }
}
