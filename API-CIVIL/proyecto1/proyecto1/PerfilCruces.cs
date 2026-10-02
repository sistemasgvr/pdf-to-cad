using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  CRUCES CON OTRAS TUBERÍAS (DISENO.md C.7, F.11 AgruparCruces, G.4-5, G.5-3)
//   · Candidatos: todas las tuberías (gravedad y presión) que cortan la traza
//     del eje, salvo las del recorrido, las degeneradas (que además alimentan
//     VerticalesTodas, C.3-6) y las que tocan un nodo del recorrido.
//   · Agrupación por red y proximidad (una etiqueta por grupo).
//   · Añadido a las vistas (vía PerfilVista.AgregarParte) y etiqueta nativa de
//     cruce (CrossingPipeProfileLabel / CrossingPressurePipeProfileLabel).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilCruces
    {
        private const double ANGULO_MIN_DEG = 15.0;
        private const int CUERDAS_CURVA = 8;

        /// <summary>
        /// C.7 (T0): cortes de las tuberías de todas las redes con la traza (≥15°, dentro de [EstIni+0.5, EstFin−0.5]),
        /// un corte por tubo, ZEje interpolado, Encima, ClaroFt y estación PRELIMINAR. <paramref name="verticales"/> = tubos
        /// degenerados de todas las redes de PRESIÓN (para MarcarRamalesVerticales).
        /// </summary>
        internal static List<Cruce> BuscarCandidatos(Transaction tr, CivilDocument civDoc, Recorrido rec, out List<VerticalConexion> verticales)
        {
            var verts = new List<VerticalConexion>();
            verticales = verts;
            var r = new List<Cruce>();
            var propios = new HashSet<ObjectId>(rec.Pasos.Select(p => p.Tramo.PipeId));
            var nodos = rec.Nodos.Select(i => rec.Red.Nodos[i]).ToList();
            double estPrimer = PerfilRecorrido.EST_INICIAL - rec.DistN0;
            bool TocaNodo(Point3d p) { return nodos.Any(n => Math.Sqrt((n.X - p.X) * (n.X - p.X) + (n.Y - p.Y) * (n.Y - p.Y)) <= PerfilRecorrido.TOL_COINCIDE); }

            void Procesar(ObjectId pid, bool presion, bool gravedad, string red)
            {
                if (propios.Contains(pid)) return;
                Curve cv; Point3d a, b;
                try { cv = (Curve)tr.GetObject(pid, OpenMode.ForRead); a = cv.StartPoint; b = cv.EndPoint; } catch { return; }
                double d2 = Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));
                if (d2 < PerfilRecorrido.LARGO_MIN_TUBO)
                {
                    if (presion) verts.Add(new VerticalConexion { X = a.X, Y = a.Y, ZMin = Math.Min(a.Z, b.Z), ZMax = Math.Max(a.Z, b.Z), Red = red, PipeId = pid });
                    return;
                }
                if (TocaNodo(a) || TocaNodo(b)) return;
                var pts = new List<Point3d>();
                bool curva = false;
                try { curva = presion ? ((CivilDB.PressurePipe)cv).IsCurve : ((CivilDB.Pipe)cv).SubEntityType == CivilDB.PipeSubEntityType.Curved; } catch { }
                if (curva)
                {
                    try
                    {
                        double p0 = cv.StartParam, p1 = cv.EndParam;
                        for (int k = 0; k <= CUERDAS_CURVA; k++) pts.Add(cv.GetPointAtParameter(p0 + (p1 - p0) * k / CUERDAS_CURVA));
                    }
                    catch { pts.Clear(); }
                }
                if (pts.Count < 2) { pts.Add(a); pts.Add(b); }
                for (int k = 0; k + 1 < pts.Count; k++)
                {
                    var cortes = PerfilRecorrido.CortarTraza(rec.Traza, estPrimer, new V2(pts[k].X, pts[k].Y), new V2(pts[k + 1].X, pts[k + 1].Y))
                        .Where(c => c.AnguloDeg >= ANGULO_MIN_DEG && c.Estacion >= rec.EstIni + 0.5 && c.Estacion <= rec.EstFin - 0.5).ToList();
                    if (cortes.Count == 0) continue;
                    var ct = cortes[0];
                    double z = pts[k].Z + (pts[k + 1].Z - pts[k].Z) * ct.T;
                    var c = new Cruce { PipeId = pid, EsPresion = presion, EsGravedad = gravedad, Red = red, Estacion = ct.Estacion, ZEje = z, AnguloDeg = ct.AnguloDeg, X = ct.P.X, Y = ct.P.Y };
                    LeerDimensiones(tr, c, cv, presion);
                    double zr = PerfilEje.ZEjeRecorrido(rec, c.Estacion), ar = PerfilEje.AltoExtEn(rec, c.Estacion);
                    c.Encima = c.ZEje > zr;
                    c.ClaroFt = c.Encima ? (c.ZEje - c.AltoExtFt / 2.0) - (zr + ar / 2.0) : (zr - ar / 2.0) - (c.ZEje + c.AltoExtFt / 2.0);
                    r.Add(c);
                    return;                                                   // un solo corte por tubo
                }
            }

            try
            {
                foreach (ObjectId nid in civDoc.GetPipeNetworkIds())
                {
                    CivilDB.Network net;
                    try { net = (CivilDB.Network)tr.GetObject(nid, OpenMode.ForRead); } catch { continue; }
                    string nombre = ""; try { nombre = net.Name; } catch { }
                    bool conduit = true;
                    try
                    {
                        var sids = net.GetStructureIds();
                        foreach (ObjectId sid in sids)
                            try { if (!PerfilGrafoCivil.EsEstructuraNula((CivilDB.Structure)tr.GetObject(sid, OpenMode.ForRead))) { conduit = false; break; } } catch { }
                    }
                    catch { }
                    try { foreach (ObjectId pid in net.GetPipeIds()) Procesar(pid, false, !conduit, nombre); } catch { }
                }
            }
            catch (Exception ex) { PerfilLog.Error("CRUCE", "redes de gravedad", ex); }
            try
            {
                foreach (ObjectId nid in CivilDocumentPressurePipesExtension.GetPressurePipeNetworkIds(civDoc))
                {
                    CivilDB.PressurePipeNetwork net;
                    try { net = (CivilDB.PressurePipeNetwork)tr.GetObject(nid, OpenMode.ForRead); } catch { continue; }
                    string nombre = ""; try { nombre = net.Name; } catch { }
                    try { foreach (ObjectId pid in net.GetPipeIds()) Procesar(pid, true, false, nombre); } catch { }
                }
            }
            catch (Exception ex) { PerfilLog.Error("CRUCE", "redes de presión", ex); }
            r.Sort((x, y) => x.Estacion.CompareTo(y.Estacion));
            PerfilLog.Log("CRUCE", $"{r.Count} cruces, {verticales.Count} conexiones verticales de presión");
            return r;
        }

        private static void LeerDimensiones(Transaction tr, Cruce c, Curve cv, bool presion)
        {
            try
            {
                if (presion)
                {
                    var pp = (CivilDB.PressurePipe)cv;
                    double nom = 0, outer = 0;
                    try { nom = pp.NominalDiameter; } catch { }
                    try { outer = pp.OuterDiameter; } catch { }
                    c.DiamIn = nom * 12.0; c.AltoExtFt = outer > 0 ? outer : nom; c.RadioIntFt = nom / 2.0;
                    try { c.Material = pp.Description; } catch { }
                    if (string.IsNullOrWhiteSpace(c.Material)) try { c.Material = pp.PartDescription; } catch { }
                    try { c.Abandonado = string.Equals(pp.StyleName, "Abandonado (PDFCAD)", StringComparison.OrdinalIgnoreCase); } catch { }
                }
                else
                {
                    var p = (CivilDB.Pipe)cv;
                    double inner = 0, innerH = 0, outerH = 0, outerD = 0;
                    try { inner = p.InnerDiameterOrWidth; } catch { }
                    try { innerH = p.InnerHeight; } catch { }
                    try { outerH = p.OuterHeight; } catch { }
                    try { outerD = p.OuterDiameterOrWidth; } catch { }
                    c.DiamIn = inner * 12.0;
                    c.AltoExtFt = outerH > 0 ? outerH : (outerD > 0 ? outerD : inner);
                    c.RadioIntFt = innerH > 0 ? innerH / 2.0 : inner / 2.0;
                    try { c.Material = p.Description; } catch { }
                    if (string.IsNullOrWhiteSpace(c.Material)) try { c.Material = p.PartDescription; } catch { }
                    try { c.Abandonado = string.Equals(p.StyleName, "Abandonado (PDFCAD)", StringComparison.OrdinalIgnoreCase); } catch { }
                }
            }
            catch (Exception ex) { PerfilLog.Log("CRUCE", "dimensiones de " + c.PipeId.Handle + ": " + ex.Message); }
        }

        /// <summary>F.11: asigna Grupo y EtiquetaDelGrupo (representante = primero del grupo por estación). Devuelve el número de grupos.</summary>
        internal static int Agrupar(List<Cruce> cruces, double s)
        {
            if (cruces == null || cruces.Count == 0) return 0;
            var grupos = PerfilDiseno.AgruparCruces(cruces.Select(c => c.Estacion).ToList(), cruces.Select(c => c.Red).ToList(), s);
            for (int g = 0; g < grupos.Count; g++)
            {
                var orden = grupos[g].OrderBy(i => cruces[i].Estacion).ToList();
                foreach (int i in orden) { cruces[i].Grupo = g; cruces[i].EtiquetaDelGrupo = false; }
                cruces[orden[0]].EtiquetaDelGrupo = true;
            }
            return grupos.Count;
        }

        /// <summary>
        /// G.4-5 (T1a, dentro de la captura): añade a su hoja cada cruce de hoja.Cruces con PerfilVista.AgregarParte
        /// (Rol = Cruce, CruceIdx). Cada parte en su try; los fallos van al log.
        /// </summary>
        internal static void AgregarAVista(Transaction tr, ContextoPerfil ctx, CapturaPartes cap)
        {
            foreach (var h in ctx.Hojas)
            {
                if (h.PvId.IsNull) continue;
                foreach (int ci in h.Cruces)
                {
                    try
                    {
                        var c = ctx.Cruces[ci];
                        var parte = PerfilVista.AgregarParte(tr, ctx, cap, c.PipeId, c.EsPresion, h.Indice, RolParte.Cruce, ci);
                        if (parte == null) PerfilLog.Aviso("CRUCE", "No se pudo añadir el cruce " + c.PipeId.Handle + " a la hoja " + (h.Indice + 1));
                    }
                    catch (Exception ex) { PerfilLog.Error("CRUCE", "AgregarAVista", ex); }
                }
            }
        }

        /// <summary>
        /// G.5-3 (T1b): etiqueta nativa del representante de cada grupo de la hoja (gravedad: CrossingPipeProfileLabel;
        /// presión: CrossingPressurePipeProfileLabel ratio 0.5), se queda la de estación más cercana y borra el resto,
        /// escribe el texto del Callout "CRUCE" (PerfilEtiquetas.EscribirTexto) y oculta el leader. Devuelve cuántas creó.
        /// </summary>
        internal static int CrearEtiquetas(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            int n = 0;
            if (hoja.PvId.IsNull) return 0;
            CivilDB.ProfileView pv;
            try { pv = (CivilDB.ProfileView)tr.GetObject(hoja.PvId, OpenMode.ForRead); } catch { return 0; }
            foreach (var co in hoja.Callouts.Where(c => c.Tipo == "CRUCE" && c.CruceIdx >= 0))
            {
                var cr = ctx.Cruces[co.CruceIdx];
                int k = cr.Hojas.IndexOf(hoja.Indice);
                ObjectId part = k >= 0 && k < cr.PvPartIds.Count ? cr.PvPartIds[k] : ObjectId.Null;
                if (part.IsNull) { PerfilLog.Aviso("CRUCE", "Cruce sin parte en la vista: sin etiqueta (" + cr.PipeId.Handle + ")"); continue; }
                try
                {
                    ObjectIdCollection ids = cr.EsPresion
                        ? CivilDB.CrossingPressurePipeProfileLabel.Create(part, hoja.PvId, 0.5, ctx.Estilos.CrucePresLbl)
                        : CivilDB.CrossingPipeProfileLabel.Create(part, hoja.PvId, ctx.Estilos.CruceGravLbl);
                    if (ids == null || ids.Count == 0) { PerfilLog.Aviso("CRUCE", "La etiqueta de cruce no se creó (" + cr.PipeId.Handle + ")"); continue; }
                    ObjectId elegida = ids[0];
                    if (ids.Count > 1)
                    {
                        double mejor = double.MaxValue;
                        foreach (ObjectId id in ids)
                        {
                            try
                            {
                                var lb = (CivilDB.Label)tr.GetObject(id, OpenMode.ForRead);
                                double st = 0, el = 0;
                                pv.FindStationAndElevationAtXY(lb.AnchorInfo.Location.X, lb.AnchorInfo.Location.Y, ref st, ref el);
                                if (Math.Abs(st - cr.Estacion) < mejor) { mejor = Math.Abs(st - cr.Estacion); elegida = id; }
                            }
                            catch { }
                        }
                        foreach (ObjectId id in ids) if (id != elegida) PerfilEtiquetas.Borrar(tr, id);
                    }
                    var lbl = (CivilDB.Label)tr.GetObject(elegida, OpenMode.ForWrite);
                    PerfilEtiquetas.EscribirTexto(tr, lbl, co.Lineas);
                    PerfilEtiquetas.Leaders(lbl, false, false);
                    co.EtiquetaId = elegida; cr.EtiquetaIds.Add(elegida);
                    n++;
                }
                catch (Exception ex) { PerfilLog.Error("CRUCE", "etiqueta de cruce " + cr.PipeId.Handle, ex); PerfilLog.Aviso("Etiqueta de cruce omitida (" + cr.PipeId.Handle + ")"); }
            }
            return n;
        }
    }
}
