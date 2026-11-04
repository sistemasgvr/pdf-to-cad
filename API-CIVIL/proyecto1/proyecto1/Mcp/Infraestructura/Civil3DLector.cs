using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Dominio;
using CivilDB = Autodesk.Civil.DatabaseServices;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;

// ============================================================================
//  ADAPTADOR de lectura (Civil 3D → Dominio). Foto de redes de gravedad/conduit y
//  de presión en pies; la rasante sale de la PROPIA tubería (eje − radio interior),
//  igual que COTAR_TUBERIAS. La foto se reusa hasta que el dibujo cambia
//  (eventos ObjectAppended/Modified/Erased de su base de datos).
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed class Civil3DLector : IModeloLector
    {
        private sealed class Cache { public long Version; public long Leida = -1; public Modelo Modelo; }
        private readonly ConditionalWeakTable<Database, Cache> _caches = new ConditionalWeakTable<Database, Cache>();

        public EstadoDibujo Estado() => HiloAutoCAD.Leer(d =>
        {
            var e = new EstadoDibujo { Dibujo = d.Name, Comando = HiloAutoCAD.ComandoEnCurso(d) };
            e.Ocupado = e.Comando.Length > 0;
            try
            {
                CivilDocument c = CivilApplication.ActiveDocument;
                var uz = c.Settings.DrawingSettings.UnitZoneSettings;
                e.Unidades = uz.DrawingUnits.ToString();
                e.SistemaCoordenadas = uz.CoordinateSystemCode;
                e.RedesGravedad = c.GetPipeNetworkIds().Count;
                e.RedesPresion = c.GetPressurePipeNetworkIds().Count;
            }
            catch { }
            return e;
        }, permitirOcupado: true);

        public Modelo Leer() => HiloAutoCAD.Leer(d =>
        {
            Cache c = CacheDe(d.Database);
            if (c.Modelo != null && c.Leida == c.Version) return c.Modelo;
            long v = c.Version;
            c.Modelo = LeerTodo(d.Database);
            c.Leida = v;
            return c.Modelo;
        });

        public bool CapaExiste(string capa) => HiloAutoCAD.Leer(d =>
        {
            using (Transaction tr = d.Database.TransactionManager.StartOpenCloseTransaction())
            {
                var lt = (LayerTable)tr.GetObject(d.Database.LayerTableId, OpenMode.ForRead);
                return lt.Has(capa);
            }
        });

        public Dictionary<string, object> Detalle(string handle) => HiloAutoCAD.Leer(d =>
        {
            ObjectId id = Ids.De(d.Database, handle);
            if (id.IsNull) return null;
            var r = new Dictionary<string, object>();
            using (Transaction tr = d.Database.TransactionManager.StartTransaction())
            {
                var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                if (ent == null) return null;
                r["clase"] = ent.GetType().Name;
                r["capa"] = ent.Layer;
                if (ent is CivilDB.Structure s)
                {
                    var tubos = new List<string>();
                    for (int i = 0; i < s.ConnectedPipesCount; i++)
                        try { tubos.Add(s.get_ConnectedPipe(i).Handle.ToString()); } catch { }
                    r["tuberias_conectadas"] = tubos;
                }
                r["property_sets"] = PropertySets(tr, ent);
                tr.Commit();
            }
            return r;
        });

        // ------------------------------------------------------------------ foto

        private Cache CacheDe(Database db)
        {
            if (_caches.TryGetValue(db, out Cache c)) return c;
            c = new Cache();
            _caches.Add(db, c);
            db.ObjectAppended += (s, e) => c.Version++;
            db.ObjectModified += (s, e) => c.Version++;
            db.ObjectErased += (s, e) => c.Version++;
            return c;
        }

        private static Modelo LeerTodo(Database db)
        {
            var m = new Modelo();
            CivilDocument civil = CivilApplication.ActiveDocument;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                foreach (ObjectId nid in civil.GetPipeNetworkIds())
                {
                    if (!(tr.GetObject(nid, OpenMode.ForRead) is CivilDB.Network net)) continue;
                    foreach (ObjectId pid in net.GetPipeIds())
                        try { if (tr.GetObject(pid, OpenMode.ForRead) is CivilDB.Pipe p) m.Tuberias.Add(Gravedad(p, net.Name)); } catch { }
                    foreach (ObjectId sid in net.GetStructureIds())
                        try { if (tr.GetObject(sid, OpenMode.ForRead) is CivilDB.Structure s) m.Estructuras.Add(Estr(s, net.Name)); } catch { }
                }
                foreach (ObjectId nid in civil.GetPressurePipeNetworkIds())
                {
                    if (!(tr.GetObject(nid, OpenMode.ForRead) is CivilDB.PressurePipeNetwork net)) continue;
                    foreach (ObjectId pid in net.GetPipeIds())
                        try { if (tr.GetObject(pid, OpenMode.ForRead) is CivilDB.PressurePipe p) m.Tuberias.Add(Presion(p, net.Name)); } catch { }
                }
                LeerTextos(tr, db, m);
                tr.Commit();
            }
            return m;
        }

        /// <summary>TEXT y MTEXT del espacio modelo, en texto plano (MText.Text ya quita los códigos de formato).</summary>
        private static void LeerTextos(Transaction tr, Database db, Modelo m)
        {
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            RXClass cTexto = RXObject.GetClass(typeof(DBText)), cMText = RXObject.GetClass(typeof(MText));
            foreach (ObjectId id in ms)
            {
                try
                {
                    if (id.ObjectClass.IsDerivedFrom(cTexto) && tr.GetObject(id, OpenMode.ForRead) is DBText t)
                        m.Textos.Add(new TextoDibujo
                        {
                            Handle = t.Handle.ToString(), Tipo = "TEXT", Contenido = t.TextString, Capa = t.Layer,
                            X = t.Position.X, Y = t.Position.Y, Altura = t.Height,
                        });
                    else if (id.ObjectClass.IsDerivedFrom(cMText) && tr.GetObject(id, OpenMode.ForRead) is MText mt)
                        m.Textos.Add(new TextoDibujo
                        {
                            Handle = mt.Handle.ToString(), Tipo = "MTEXT", Contenido = mt.Text, Capa = mt.Layer,
                            X = mt.Location.X, Y = mt.Location.Y, Altura = mt.TextHeight,
                        });
                }
                catch { }
            }
        }

        internal static double RadioInterior(CivilDB.Pipe p)
        {
            double r = 0.0;
            try { double h = p.InnerHeight; if (h > 1e-6) r = h / 2.0; } catch { }
            if (r <= 0.0) { try { r = p.InnerDiameterOrWidth / 2.0; } catch { } }
            return r;
        }

        private static Tuberia Gravedad(CivilDB.Pipe p, string red)
        {
            double r = RadioInterior(p);
            Point3d a = p.StartPoint, b = p.EndPoint;
            var t = Base(p, red, Dominio.TipoRed.Gravedad, a, b);
            try { t.Nombre = p.Name; } catch { t.Nombre = t.Handle; }
            try { t.DiametroIn = p.InnerDiameterOrWidth * 12.0; } catch { }
            try { t.Tamano = p.PartSizeName; } catch { }
            try { t.Descripcion = p.Description; } catch { }
            t.CotaIni = a.Z - r; t.CotaFin = b.Z - r;
            try { t.PendientePct = p.Slope * 100.0; } catch { }
            try { if (!p.StartStructureId.IsNull) t.EstructuraIni = p.StartStructureId.Handle.ToString(); } catch { }
            try { if (!p.EndStructureId.IsNull) t.EstructuraFin = p.EndStructureId.Handle.ToString(); } catch { }
            return t;
        }

        private static Tuberia Presion(CivilDB.PressurePipe p, string red)
        {
            Point3d a = p.StartPoint, b = p.EndPoint;
            var t = Base(p, red, Dominio.TipoRed.Presion, a, b);
            try { t.Nombre = p.Name; } catch { t.Nombre = t.Handle; }
            double r = 0.0;
            try { r = p.NominalDiameter / 2.0; t.DiametroIn = p.NominalDiameter * 12.0; } catch { }   // en pies
            try { t.Tamano = p.PartDescription; } catch { }
            try { t.Descripcion = p.Description; } catch { }
            t.CotaIni = a.Z - r; t.CotaFin = b.Z - r;
            try { t.PendientePct = p.Slope * 100.0; } catch { }
            return t;
        }

        private static Tuberia Base(Entity e, string red, Dominio.TipoRed tipo, Point3d a, Point3d b)
        {
            var t = new Tuberia
            {
                Handle = e.Handle.ToString(), Red = red, TipoRed = tipo, Capa = e.Layer,
                XIni = a.X, YIni = a.Y, XFin = b.X, YFin = b.Y,
                LargoFt = Math.Sqrt((b.X - a.X) * (b.X - a.X) + (b.Y - a.Y) * (b.Y - a.Y)),
            };
            return t;
        }

        private static Estructura Estr(CivilDB.Structure s, string red)
        {
            var e = new Estructura { Handle = s.Handle.ToString(), Red = red, Capa = s.Layer, X = s.Position.X, Y = s.Position.Y };
            try { e.Nombre = s.Name; } catch { e.Nombre = e.Handle; }
            try { e.Tamano = s.PartSizeName; } catch { }
            try { e.Rim = s.RimElevation; } catch { }
            try { e.Sump = s.SumpElevation; } catch { }
            try { e.Conexiones = s.ConnectedPipesCount; } catch { }
            return e;
        }

        private static Dictionary<string, Dictionary<string, string>> PropertySets(Transaction tr, Entity ent)
        {
            var r = new Dictionary<string, Dictionary<string, string>>();
            try
            {
                foreach (ObjectId psId in AecPS.PropertyDataServices.GetPropertySets(ent))
                {
                    var ps = tr.GetObject(psId, OpenMode.ForRead) as AecPS.PropertySet;
                    if (ps == null) continue;
                    var campos = new Dictionary<string, string>();
                    foreach (AecPS.PropertySetData dato in ps.PropertySetData)
                    {
                        try
                        {
                            string v = Convert.ToString(dato.GetData(), System.Globalization.CultureInfo.InvariantCulture);
                            if (!string.IsNullOrEmpty(v)) campos[ps.PropertyIdToName(dato.Id)] = v;
                        }
                        catch { }
                    }
                    r[ps.PropertySetDefinitionName] = campos;
                }
            }
            catch { }
            return r;
        }
    }

    internal static class Ids
    {
        public static ObjectId De(Database db, string handle)
        {
            try
            {
                long h = Convert.ToInt64((handle ?? "").Trim(), 16);
                return db.TryGetObjectId(new Handle(h), out ObjectId id) && !id.IsErased ? id : ObjectId.Null;
            }
            catch { return ObjectId.Null; }
        }
    }
}
