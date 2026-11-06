using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Civil3DBasico.Mcp.Dominio;
using CivilDB = Autodesk.Civil.DatabaseServices;

// ============================================================================
//  ADAPTADOR: choques 3D DE VERDAD. `Cuerpos` = todo lo dibujado con su caja
//  (tuberías con su radio exterior, estructuras, piezas de presión y TODOS los
//  sólidos del espacio modelo: accesorios, válvulas, buzones sólidos,
//  bancoductos). `Interferencias` arma un sólido por cuerpo (cilindro en las
//  tuberías, el cuerpo 3D de la pieza si Civil 3D lo da, si no su caja; el
//  sólido tal cual) y usa Solid3d.CheckInterference. Nada se agrega al dibujo.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed partial class Civil3DLector
    {
        public const int PARES_MAX = 4000;

        public List<Cuerpo> Cuerpos() => HiloAutoCAD.Leer(d =>
        {
            Modelo m = LeerTodo(d.Database);
            var por = m.Tuberias.ToDictionary(t => t.Handle, StringComparer.OrdinalIgnoreCase);
            var r = new List<Cuerpo>();
            Database db = d.Database;
            CivilDocument civil = CivilApplication.ActiveDocument;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                var redes = new List<(ObjectId id, bool presion)>();
                foreach (ObjectId n in civil.GetPipeNetworkIds()) redes.Add((n, false));
                foreach (ObjectId n in civil.GetPressurePipeNetworkIds()) redes.Add((n, true));
                foreach (var (nid, presion) in redes)
                {
                    var ids = new List<ObjectId>();
                    string red = "";
                    try
                    {
                        if (tr.GetObject(nid, OpenMode.ForRead) is CivilDB.Network net)
                        { red = net.Name; foreach (ObjectId x in net.GetPipeIds()) ids.Add(x); foreach (ObjectId x in net.GetStructureIds()) ids.Add(x); }
                        else if (tr.GetObject(nid, OpenMode.ForRead) is CivilDB.PressurePipeNetwork pn)
                        {
                            red = pn.Name;
                            foreach (ObjectId x in pn.GetPipeIds()) ids.Add(x);
                            try { foreach (ObjectId x in pn.GetFittingIds()) ids.Add(x); } catch { }
                            try { foreach (ObjectId x in pn.GetAppurtenanceIds()) ids.Add(x); } catch { }
                        }
                    }
                    catch { continue; }
                    foreach (ObjectId id in ids)
                        try { var c = CuerpoDe(tr.GetObject(id, OpenMode.ForRead) as Entity, red, por, m); if (c != null) r.Add(c); } catch { }
                }
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                RXClass cSol = RXObject.GetClass(typeof(Solid3d));
                foreach (ObjectId id in ms)
                    try
                    {
                        if (!id.ObjectClass.IsDerivedFrom(cSol) || !(tr.GetObject(id, OpenMode.ForRead) is Solid3d so)) continue;
                        Accesorio acc = Solido(so);
                        r.Add(Caja(so, "solido", acc != null ? $"{(string.IsNullOrEmpty(acc.Tipo) ? "accesorio" : acc.Tipo)} ({so.Layer})" : $"sólido ({so.Layer})",
                                   acc?.Red ?? "", "", so.Layer));
                    }
                    catch { }
                tr.Commit();
            }
            return r;
        });

        private static Cuerpo CuerpoDe(Entity e, string red, Dictionary<string, Tuberia> por, Modelo m)
        {
            if (e == null) return null;
            string h = e.Handle.ToString();
            if (por.TryGetValue(h, out Tuberia t))
            {
                double r = RadioExterior(e);
                Point3d a = ((Curve)e).StartPoint, b = ((Curve)e).EndPoint;
                var c = new Cuerpo
                {
                    Handle = h, Tipo = "tuberia", Nombre = t.Nombre, Red = red, Utilidad = string.IsNullOrEmpty(t.UtilidadNumero) ? "" : t.Utilidad(),
                    Capa = e.Layer, EstructuraIni = t.EstructuraIni, EstructuraFin = t.EstructuraFin,
                    Min = new[] { Math.Min(a.X, b.X) - r, Math.Min(a.Y, b.Y) - r, Math.Min(a.Z, b.Z) - r },
                    Max = new[] { Math.Max(a.X, b.X) + r, Math.Max(a.Y, b.Y) + r, Math.Max(a.Z, b.Z) + r },
                };
                c.Puntas.Add((a.X, a.Y)); c.Puntas.Add((b.X, b.Y));
                return c;
            }
            if (e is CivilDB.Structure s)
            {
                Estructura es = m.Estructuras.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                if (es != null && es.Nula) return null;
                return Caja(e, "estructura", es?.Nombre ?? h, red, "", e.Layer);
            }
            if (e is CivilDB.PressurePart) return Caja(e, "accesorio", $"{SafeDesc(e)} ({red})", red, "", e.Layer);
            return null;
        }

        private static string SafeDesc(Entity e) { try { return ((CivilDB.PressurePart)e).PartDescription; } catch { return "accesorio"; } }

        private static Cuerpo Caja(Entity e, string tipo, string nombre, string red, string utilidad, string capa)
        {
            Extents3d x = e.GeometricExtents;
            return new Cuerpo
            {
                Handle = e.Handle.ToString(), Tipo = tipo, Nombre = nombre, Red = red, Utilidad = utilidad, Capa = capa,
                Min = new[] { x.MinPoint.X, x.MinPoint.Y, x.MinPoint.Z }, Max = new[] { x.MaxPoint.X, x.MaxPoint.Y, x.MaxPoint.Z },
            };
        }

        private static double RadioExterior(Entity e)
        {
            double r = 0.0;
            if (e is CivilDB.Pipe p) { try { r = p.OuterDiameterOrWidth / 2.0; } catch { } if (r <= 0) r = RadioInterior(p); }
            else if (e is CivilDB.PressurePipe pp) { try { r = pp.OuterDiameter / 2.0; } catch { } if (r <= 0) try { r = pp.NominalDiameter / 2.0; } catch { } }
            return Math.Max(r, 0.01);
        }

        public List<Interferencia> Interferencias(IList<(string a, string b)> pares) => HiloAutoCAD.Leer(d =>
        {
            var r = new List<Interferencia>();
            Database db = d.Database;
            var solidos = new Dictionary<string, Solid3d>(StringComparer.OrdinalIgnoreCase);
            try
            {
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    Solid3d De(string h)
                    {
                        if (solidos.TryGetValue(h, out Solid3d s)) return s;
                        ObjectId id = Ids.De(db, h);
                        s = id.IsNull ? null : SolidoDe(tr.GetObject(id, OpenMode.ForRead) as Entity);
                        solidos[h] = s;
                        return s;
                    }
                    foreach (var (a, b) in pares.Take(PARES_MAX))
                    {
                        Solid3d sa = De(a), sb = De(b);
                        if (sa == null || sb == null) continue;
                        try
                        {
                            if (!sa.CheckInterference(sb)) continue;
                            var i = new Interferencia { A = a, B = b };
                            try
                            {
                                // lo común: intersección de COPIAS (los sólidos de prueba se reusan con otros pares)
                                using (var comun = (Solid3d)sa.Clone())
                                using (var otro = (Solid3d)sb.Clone())
                                {
                                    comun.BooleanOperation(BooleanOperationType.BoolIntersect, otro);
                                    Extents3d x = comun.GeometricExtents;
                                    i.X = (x.MinPoint.X + x.MaxPoint.X) / 2; i.Y = (x.MinPoint.Y + x.MaxPoint.Y) / 2; i.Z = (x.MinPoint.Z + x.MaxPoint.Z) / 2;
                                    i.VolumenFt3 = comun.MassProperties.Volume;
                                }
                            }
                            catch
                            {
                                Extents3d ea = sa.GeometricExtents, eb = sb.GeometricExtents;
                                i.X = (Math.Max(ea.MinPoint.X, eb.MinPoint.X) + Math.Min(ea.MaxPoint.X, eb.MaxPoint.X)) / 2;
                                i.Y = (Math.Max(ea.MinPoint.Y, eb.MinPoint.Y) + Math.Min(ea.MaxPoint.Y, eb.MaxPoint.Y)) / 2;
                                i.Z = (Math.Max(ea.MinPoint.Z, eb.MinPoint.Z) + Math.Min(ea.MaxPoint.Z, eb.MaxPoint.Z)) / 2;
                            }
                            r.Add(i);
                        }
                        catch { }
                    }
                    tr.Commit();
                }
            }
            finally { foreach (var s in solidos.Values) s?.Dispose(); }
            return r;
        });

        /// <summary>Un sólido NUEVO (fuera del dibujo) con la forma del objeto.</summary>
        private static Solid3d SolidoDe(Entity e)
        {
            if (e == null) return null;
            if (e is Solid3d so) return (Solid3d)so.Clone();
            if (e is CivilDB.Pipe || e is CivilDB.PressurePipe)
            {
                Point3d a = ((Curve)e).StartPoint, b = ((Curve)e).EndPoint;
                double L = a.DistanceTo(b), r = RadioExterior(e);
                if (L < 1e-6) return null;
                var s = new Solid3d();
                s.CreateFrustum(L, r, r, r);
                Vector3d z = (b - a).GetNormal();
                Vector3d x = z.GetPerpendicularVector().GetNormal(), y = z.CrossProduct(x).GetNormal();
                s.TransformBy(Matrix3d.AlignCoordinateSystem(Point3d.Origin, Vector3d.XAxis, Vector3d.YAxis, Vector3d.ZAxis,
                                                             a + (b - a) / 2.0, x, y, z));
                return s;
            }
            // pieza de Civil 3D: su cuerpo 3D si la API lo da (según la versión), si no su caja
            try
            {
                if (e.GetType().GetProperty("Solid3dBody")?.GetValue(e) is Solid3d cuerpo) return cuerpo;
            }
            catch { }
            try
            {
                Extents3d x = e.GeometricExtents;
                Vector3d t = x.MaxPoint - x.MinPoint;
                if (t.X < 1e-6 || t.Y < 1e-6 || t.Z < 1e-6) return null;
                var s = new Solid3d();
                s.CreateBox(t.X, t.Y, t.Z);
                s.TransformBy(Matrix3d.Displacement(x.MinPoint + t / 2.0 - Point3d.Origin));
                return s;
            }
            catch { return null; }
        }
    }
}
