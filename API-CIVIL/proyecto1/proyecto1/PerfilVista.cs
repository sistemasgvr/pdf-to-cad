using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  VISTAS DE PERFIL (DISENO.md G.4, G.5-1/2, G.6-1, G.7, G.9-1…3)
//   · Perfil de terreno (Profile.CreateFromSurface) y una ProfileView por hoja,
//     apiladas, en la capa PDFCAD_PERFIL, sin bandas y con rango UserSpecified
//     fijado en orden seguro (I-18).
//   · AddToProfileView con captura de los ProfileViewPart nuevos
//     (Database.ObjectAppended), resolución en T1b y overrides por vista.
//   · FindXY con respaldo, cambio de estilo de vista, rango final y reapilado.
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// G.4-5: captura de los ProfileViewPart / ProfileViewPressurePart que se añaden a la base de datos.
    /// Se suscribe en T1a y se desuscribe DESPUÉS del Commit de T1a, en un finally (Dispose).
    /// </summary>
    internal sealed class CapturaPartes : IDisposable
    {
        /// <summary>Ids capturados, en orden de llegada.</summary>
        public List<ObjectId> Nuevos = new List<ObjectId>();
        private Database _db;
        private RXClass _cGrav, _cPres;

        private void Manejador(object sender, ObjectEventArgs e)
        {
            try
            {
                var id = e.DBObject.ObjectId;
                var c = id.ObjectClass;
                if ((_cGrav != null && c.IsDerivedFrom(_cGrav)) || (_cPres != null && c.IsDerivedFrom(_cPres))) Nuevos.Add(id);
            }
            catch { }
        }

        /// <summary>Suscribe el manejador a db.ObjectAppended (filtra por clase derivada de ProfileViewPart/ProfileViewPressurePart).</summary>
        public void Suscribir(Database db)
        {
            if (_db != null) return;
            try { _cGrav = RXObject.GetClass(typeof(CivilDB.ProfileViewPart)); } catch { }
            try { _cPres = RXObject.GetClass(typeof(CivilDB.ProfileViewPressurePart)); } catch { }
            _db = db;
            db.ObjectAppended += Manejador;
        }

        /// <summary>Desuscribe el manejador (idempotente; nunca lanza).</summary>
        public void Desuscribir()
        {
            try { if (_db != null) _db.ObjectAppended -= Manejador; } catch { }
            _db = null;
        }

        /// <summary>Desuscribe (para usar en using/finally).</summary>
        public void Dispose() { Desuscribir(); }
    }

    internal static class PerfilVista
    {
        public const double SEPARACION_HOJAS_IN = 2.5;   // G.4-4: hueco vertical entre vistas apiladas (in de ploteo)

        /// <summary>G.4-3: perfil de terreno "{nombre} - EX. GRADE" desde ctx.Red.SuperficieId; Null con aviso si falla o no hay superficie.</summary>
        internal static ObjectId CrearTerreno(Transaction tr, ContextoPerfil ctx)
        {
            if (ctx.SinSuperficie || ctx.Red.SuperficieId.IsNull) return ObjectId.Null;
            try
            {
                var e = ctx.Estilos;
                return CivilDB.Profile.CreateFromSurface(PerfilEje.NombreTerreno(ctx.Nombre), ctx.AlignId, ctx.Red.SuperficieId, e.CapaId, e.TerrenoStyle, e.LabelSetPerfilVacio);
            }
            catch (Exception ex) { PerfilLog.Error("VISTA", "perfil de terreno", ex); PerfilLog.Aviso("No se pudo crear el perfil del terreno"); return ObjectId.Null; }
        }

        /// <summary>
        /// G.4-4: crea la ProfileView de cada hoja (nombre D.1, BandSetVacio, VistaStyle) en su inserción apilada, capa, sin bandas
        /// y rango preliminar. Rellena hoja.PvId/Insercion. false si falla la hoja 1 (fatal); las demás se omiten con aviso.
        /// </summary>
        internal static bool CrearVistas(Transaction tr, ContextoPerfil ctx)
        {
            var altos = ctx.Hojas.Select(h => h.Prelim != null ? h.Prelim.AltoMarco : 8.0).ToList();
            foreach (var h in ctx.Hojas)
            {
                try
                {
                    h.Nombre = PerfilEje.NombreHoja(ctx.Nombre, h.Indice);
                    h.Insercion = InsercionHoja(ctx.PuntoInsercion, altos, h.Indice, ctx.S);
                    h.PvId = CivilDB.ProfileView.Create(ctx.AlignId, h.Insercion, h.Nombre, ctx.Estilos.BandSetVacio, ctx.Estilos.VistaStyle);
                    var pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForWrite);
                    try { pv.Layer = PerfilEstilos.CAPA; } catch (Exception ex) { PerfilLog.Log("VISTA", "capa: " + ex.Message); }
                    VaciarBandas(pv);
                    if (h.Prelim != null) FijarRango(pv, h.Prelim.StationStart, h.Prelim.StationEnd, h.Prelim.ElevationMin, h.Prelim.ElevationMax);
                    ctx.Resumen.Hojas++;
                }
                catch (Exception ex)
                {
                    PerfilLog.Error("VISTA", "hoja " + (h.Indice + 1), ex);
                    h.PvId = ObjectId.Null;
                    if (h.Indice == 0) return false;
                    PerfilLog.Aviso("No se pudo crear la vista de la hoja " + (h.Indice + 1));
                }
            }
            return true;
        }

        /// <summary>G.4-4 / G.9-3: inserción de la hoja k: pt + (0, −Σ_{j&lt;k}(altoMarco_j + 2.5)·s, 0).</summary>
        internal static Point3d InsercionHoja(Point3d pt, IReadOnlyList<double> altosMarco, int k, double s)
        {
            double dy = 0;
            for (int j = 0; j < k && j < altosMarco.Count; j++) dy += (altosMarco[j] + SEPARACION_HOJAS_IN) * s;
            return new Point3d(pt.X, pt.Y - dy, pt.Z);
        }

        /// <summary>G.4-4 / G.9-2: modos UserSpecified y rango en orden seguro (si la nueva Min &gt; Max actual, primero Max); cada set en try.</summary>
        internal static void FijarRango(CivilDB.ProfileView pv, double stationStart, double stationEnd, double elevMin, double elevMax)
        {
            try { pv.StationRangeMode = CivilDB.StationRangeType.UserSpecified; } catch (Exception ex) { PerfilLog.Log("VISTA", "StationRangeMode: " + ex.Message); }
            try { pv.ElevationRangeMode = CivilDB.ElevationRangeType.UserSpecified; } catch (Exception ex) { PerfilLog.Log("VISTA", "ElevationRangeMode: " + ex.Message); }
            void Par(Func<double> maxActual, Action<double> setMin, Action<double> setMax, double nMin, double nMax, string que)
            {
                bool primeroMax = false;
                try { primeroMax = nMin > maxActual(); } catch { }
                try
                {
                    if (primeroMax) { setMax(nMax); setMin(nMin); } else { setMin(nMin); setMax(nMax); }
                }
                catch (Exception ex)
                {
                    PerfilLog.Log("VISTA", que + ": " + ex.Message + " (reintento en el otro orden)");
                    try { setMax(nMax); } catch { }
                    try { setMin(nMin); } catch { }
                }
            }
            Par(() => pv.StationEnd, v => pv.StationStart = v, v => pv.StationEnd = v, stationStart, stationEnd, "estaciones");
            Par(() => pv.ElevationMax, v => pv.ElevationMin = v, v => pv.ElevationMax = v, elevMin, elevMax, "cotas");
            try { PerfilLog.Log("VISTA", $"rango leído: {pv.StationStart:0.##}–{pv.StationEnd:0.##} / {pv.ElevationMin:0.##}–{pv.ElevationMax:0.##}"); } catch { }
        }

        /// <summary>E.3: vacía las bandas superiores e inferiores de la vista (pv ForWrite; RemoveAt de atrás hacia delante).</summary>
        internal static void VaciarBandas(CivilDB.ProfileView pv)
        {
            try
            {
                var top = pv.Bands.GetTopBandItems();
                for (int i = top.Count - 1; i >= 0; i--) top.RemoveAt(i);
                pv.Bands.SetTopBandItems(top);
            }
            catch (Exception ex) { PerfilLog.Log("VISTA", "bandas superiores: " + ex.Message); }
            try
            {
                var bot = pv.Bands.GetBottomBandItems();
                for (int i = bot.Count - 1; i >= 0; i--) bot.RemoveAt(i);
                pv.Bands.SetBottomBandItems(bot);
            }
            catch (Exception ex) { PerfilLog.Log("VISTA", "bandas inferiores: " + ex.Message); }
        }

        /// <summary>
        /// G.4-5: abre la parte ForWrite, llama a AddToProfileView(pvId) y guarda en ctx.Partes los ids capturados en su ventana.
        /// Devuelve la ParteEnVista creada (null si lanzó; el error va al log).
        /// </summary>
        internal static ParteEnVista AgregarParte(Transaction tr, ContextoPerfil ctx, CapturaPartes cap, ObjectId parteId, bool esPresion,
                                                  int hoja, RolParte rol, int cruceIdx)
        {
            var h = ctx.Hojas[hoja];
            if (h.PvId.IsNull) return null;
            if (ctx.Partes.Any(p => p.ModeloId == parteId && p.Hoja == hoja)) return ctx.Partes.First(p => p.ModeloId == parteId && p.Hoja == hoja);
            try
            {
                int i0 = cap.Nuevos.Count;
                var obj = tr.GetObject(parteId, OpenMode.ForWrite);
                if (obj is CivilDB.Part part) part.AddToProfileView(h.PvId);
                else if (obj is CivilDB.PressurePart pp) pp.AddToProfileView(h.PvId);
                else return null;
                var r = new ParteEnVista { ModeloId = parteId, EsPresion = esPresion, Hoja = hoja, Rol = rol, CruceIdx = cruceIdx };
                for (int i = i0; i < cap.Nuevos.Count; i++) r.Capturados.Add(cap.Nuevos[i]);
                ctx.Partes.Add(r);
                return r;
            }
            catch (Exception ex) { PerfilLog.Error("VISTA", "AddToProfileView " + parteId.Handle, ex); return null; }
        }

        /// <summary>G.4-5: añade a cada hoja los tubos del recorrido que caen en ella y las estructuras de sus nodos (gravedad/conduit), y luego PerfilCruces.AgregarAVista.</summary>
        internal static void AgregarPartes(Transaction tr, ContextoPerfil ctx, CapturaPartes cap)
        {
            var rec = ctx.Rec;
            foreach (var h in ctx.Hojas)
            {
                if (h.PvId.IsNull) continue;
                foreach (var p in rec.Pasos.Where(p => p.EstHasta > h.EstA + 1e-6 && p.EstDesde < h.EstB - 1e-6))
                {
                    var r = AgregarParte(tr, ctx, cap, p.Tramo.PipeId, p.Tramo.EsPresion, h.Indice,
                                         p.Tramo.Abandonado ? RolParte.RecorridoAbandonado : RolParte.Recorrido, -1);
                    if (r != null) ctx.Resumen.Tubos++;
                }
                if (ctx.Red.Tipo != TipoRed.Presion)
                    foreach (int nd in rec.Nodos.Distinct())
                    {
                        var n = ctx.Red.Nodos[nd];
                        double e = rec.EstNodo[nd];
                        if (n.EstructuraId.IsNull || e < h.EstA - 1e-6 || e > h.EstB + 1e-6) continue;
                        if (AgregarParte(tr, ctx, cap, n.EstructuraId, false, h.Indice, RolParte.Estructura, -1) != null) ctx.Resumen.Estructuras++;
                    }
            }
            PerfilCruces.AgregarAVista(tr, ctx, cap);
        }

        private static ObjectId ModeloDe(Transaction tr, ObjectId pvPartId)
        {
            try
            {
                var o = tr.GetObject(pvPartId, OpenMode.ForRead);
                if (o is CivilDB.ProfileViewPart g) return g.ModelPartId;
                if (o is CivilDB.ProfileViewPressurePart p) return p.ModelPartId;
            }
            catch { }
            return ObjectId.Null;
        }

        private static bool Dentro(Transaction tr, ObjectId id, Extents3d ev)
        {
            try
            {
                var e = ((Entity)tr.GetObject(id, OpenMode.ForRead)).GeometricExtents;
                double tol = 1.0;
                return e.MinPoint.X >= ev.MinPoint.X - tol && e.MaxPoint.X <= ev.MaxPoint.X + tol
                    && e.MinPoint.Y >= ev.MinPoint.Y - tol && e.MaxPoint.Y <= ev.MaxPoint.Y + tol;
            }
            catch { return true; }
        }

        /// <summary>
        /// G.5-1 (T1b): resuelve el ProfileViewPart de cada ParteEnVista (ventana → ModelPartId; llegados sin ventana → por ModelPartId
        /// y extents; respaldo BTR de pv.OwnerId; respaldo ProfileViewPartId si la parte está en una sola vista). Rellena Cruce.PvPartIds/Hojas.
        /// </summary>
        internal static void ResolverPartes(Transaction tr, ContextoPerfil ctx, CapturaPartes cap)
        {
            var usados = new HashSet<ObjectId>();
            foreach (var p in ctx.Partes)
            {
                var h = ctx.Hojas[p.Hoja];
                ObjectId r = p.Capturados.FirstOrDefault(id => !usados.Contains(id) && ModeloDe(tr, id) == p.ModeloId);
                ExtentsVista(tr, h.PvId, out Extents3d ev);
                if (r.IsNull)
                    r = cap.Nuevos.FirstOrDefault(id => !usados.Contains(id) && ModeloDe(tr, id) == p.ModeloId && Dentro(tr, id, ev));
                if (r.IsNull)
                {
                    try
                    {
                        var pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForRead);
                        var btr = (BlockTableRecord)tr.GetObject(pv.OwnerId, OpenMode.ForRead);
                        foreach (ObjectId id in btr)
                        {
                            if (usados.Contains(id)) continue;
                            string dxf = ""; try { dxf = id.ObjectClass.Name; } catch { }
                            if (dxf.IndexOf("ProfileView", StringComparison.OrdinalIgnoreCase) < 0) continue;
                            if (ModeloDe(tr, id) == p.ModeloId && Dentro(tr, id, ev)) { r = id; break; }
                        }
                    }
                    catch (Exception ex) { PerfilLog.Log("VISTA", "respaldo BTR: " + ex.Message); }
                }
                if (r.IsNull)
                {
                    try
                    {
                        var o = tr.GetObject(p.ModeloId, OpenMode.ForRead);
                        if (o is CivilDB.Part g && g.GetProfileViewsDisplayingMe().Count == 1) r = g.ProfileViewPartId;
                        else if (o is CivilDB.PressurePart pp && pp.GetProfileViewsDisplayingMe().Count == 1) r = pp.ProfileViewPartId;
                    }
                    catch { }
                }
                p.PvPartId = r;
                if (!r.IsNull) usados.Add(r);
                else PerfilLog.Log("VISTA", "parte sin ProfileViewPart " + p.ModeloId.Handle + " hoja " + (p.Hoja + 1));
                if (p.Rol == RolParte.Cruce && p.CruceIdx >= 0)
                {
                    var c = ctx.Cruces[p.CruceIdx];
                    c.PvPartIds.Add(r); c.Hojas.Add(p.Hoja);
                }
            }
        }

        private static ObjectId EstiloDe(EstilosPerfil e, ParteEnVista p)
        {
            switch (p.Rol)
            {
                case RolParte.Recorrido: return p.EsPresion ? e.TuboPres : e.TuboGrav;
                case RolParte.RecorridoAbandonado: return p.EsPresion ? e.TuboPresAband : e.TuboGravAband;
                case RolParte.Cruce: return p.EsPresion ? e.CrucePres : e.CruceGrav;
                default: return e.Estructura;
            }
        }

        /// <summary>G.5-2 (T1b): overrides por vista (PipeOverrides, StructureOverrides, overrides de presión) con el estilo de su RolParte; log si falta alguno.</summary>
        internal static void AplicarOverrides(Transaction tr, ContextoPerfil ctx)
        {
            foreach (var h in ctx.Hojas)
            {
                if (h.PvId.IsNull) continue;
                CivilDB.ProfileView pv;
                try { pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForWrite); } catch { continue; }
                var partes = ctx.Partes.Where(p => p.Hoja == h.Indice).ToList();
                var vistos = new HashSet<ObjectId>();
                void Aplicar(CivilDB.GraphOverride o, ObjectId modelo)
                {
                    var p = partes.FirstOrDefault(k => k.ModeloId == modelo);
                    if (p == null) return;
                    ObjectId st = EstiloDe(ctx.Estilos, p);
                    try { o.Draw = true; if (!st.IsNull) { o.OverrideStyleId = st; o.UseOverrideStyle = true; } vistos.Add(modelo); }
                    catch (Exception ex) { PerfilLog.Log("VISTA", "override " + modelo.Handle + ": " + ex.Message); }
                }
                try { foreach (var o in pv.PipeOverrides) Aplicar(o, o.PipeId); } catch (Exception ex) { PerfilLog.Log("VISTA", "PipeOverrides: " + ex.Message); }
                try { foreach (var o in pv.StructureOverrides) Aplicar(o, o.StructId); } catch (Exception ex) { PerfilLog.Log("VISTA", "StructureOverrides: " + ex.Message); }
                try { foreach (var o in CivilDB.ProfileViewPressurePipesExtension.GetPressurePipeOverrides(pv)) Aplicar(o, o.PressurePartId); }
                catch (Exception ex) { PerfilLog.Log("VISTA", "PressurePipeOverrides: " + ex.Message); }
                foreach (var p in partes.Where(k => !vistos.Contains(k.ModeloId)))
                    PerfilLog.Log("VISTA", "override no encontrado " + p.ModeloId.Handle);
            }
        }

        /// <summary>
        /// G.6-1: XY de (est, z) con pv.FindXYAtStationAndElevation; si devuelve false o lanza, respaldo
        /// x = Location.X + (est − StationStart), y = Location.Y + (z − ElevationMin)·VE con log [VISTA]. Devuelve false si usó el respaldo.
        /// </summary>
        internal static bool FindXY(CivilDB.ProfileView pv, double ve, double est, double z, out double x, out double y)
        {
            x = 0; y = 0;
            try { if (pv.FindXYAtStationAndElevation(est, z, ref x, ref y)) return true; } catch { }
            try
            {
                x = pv.Location.X + (est - pv.StationStart);
                y = pv.Location.Y + (z - pv.ElevationMin) * ve;
            }
            catch { }
            PerfilLog.Log("VISTA", $"FindXY con respaldo en ({est:0.##}, {z:0.##})");
            return false;
        }

        /// <summary>G.7 / G.9-1: asigna un nuevo ProfileViewStyle a todas las vistas (pv ForWrite).</summary>
        internal static void CambiarEstilo(Transaction tr, ContextoPerfil ctx, ObjectId nuevoEstilo)
        {
            if (nuevoEstilo.IsNull) return;
            foreach (var h in ctx.Hojas.Where(h => !h.PvId.IsNull))
                try { ((CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForWrite)).StyleId = nuevoEstilo; }
                catch (Exception ex) { PerfilLog.Error("VISTA", "StyleId hoja " + (h.Indice + 1), ex); }
        }

        /// <summary>G.9-2/3 (T3): rango final de cada hoja (hoja.Final) en orden seguro y reapilado con los altos finales; FindXY de control al log.</summary>
        internal static void AplicarRangoFinal(Transaction tr, ContextoPerfil ctx)
        {
            var altos = ctx.Hojas.Select(h => (h.Final ?? h.Prelim)?.AltoMarco ?? 8.0).ToList();
            double ve = ctx.S / ctx.V;
            foreach (var h in ctx.Hojas)
            {
                if (h.PvId.IsNull || h.Final == null) continue;
                try
                {
                    var pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForWrite);
                    FijarRango(pv, h.Final.StationStart, h.Final.StationEnd, h.Final.ElevationMin, h.Final.ElevationMax);
                    if (h.Indice > 0)
                    {
                        FindXY(pv, ve, h.Final.StationStart, h.Final.ElevationMin, out double xa, out double ya);
                        h.Insercion = InsercionHoja(ctx.PuntoInsercion, altos, h.Indice, ctx.S);
                        pv.Location = h.Insercion;
                        FindXY(pv, ve, h.Final.StationStart, h.Final.ElevationMin, out double xb, out double yb);
                        PerfilLog.Log("VISTA", $"reapilado hoja {h.Indice + 1}: origen ({xa:0.##},{ya:0.##}) → ({xb:0.##},{yb:0.##})");
                    }
                }
                catch (Exception ex) { PerfilLog.Error("VISTA", "rango final hoja " + (h.Indice + 1), ex); }
            }
        }

        /// <summary>Extents de la vista (pv.GeometricExtents en try); false si no se pudieron leer. G.11-4.</summary>
        internal static bool ExtentsVista(Transaction tr, ObjectId pvId, out Extents3d ext)
        {
            ext = new Extents3d();
            try { ext = ((Entity)tr.GetObject(pvId, OpenMode.ForRead)).GeometricExtents; return true; }
            catch { return false; }
        }
    }
}
