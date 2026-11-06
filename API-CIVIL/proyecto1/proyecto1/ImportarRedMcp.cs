using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  Puertas de IMPORTAR_RED para el MCP de la IA (2026-11-05): lo que el MCP hace
//  sobre un dibujo YA importado reutiliza el mismo código de la importación, sin
//  copiarlo: poner una válvula (`PonerValvula`), quitarla (unir de nuevo los dos
//  tubos) y crear una conexión vertical (`CrearConexionesCruzadas`). Las llama
//  `Mcp/Infraestructura/Civil3DEditor` dentro de su transacción (un paso de U).
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        /// <summary>Válvula en la tubería a presión que pasa por (x, y) con ese rumbo. Null si quedó; si no, el motivo.</summary>
        internal static string McpPonerValvula(Editor ed, Database db, Transaction tr, double x, double y, double dirX, double dirY,
                                               double diamIn, string union, string material)
        {
            var rec = ValvulaReceta.Receta(diamIn, union);
            var v = new ImportValvula
            {
                Centro = new Point2d(x, y), Dir = new Vector2d(dirX, dirY).GetNormal(), DiamIn = diamIn, LargoIn = rec.Largo,
                Union = union, Bloque = rec.Bloque, Material = material ?? "", Estimada = rec.Estimada,
            };
            return PonerValvula(ed, db, tr, RedesPresion(tr), v);
        }

        /// <summary>Todas las redes a presión (sin datos de la app: `PonerValvula` busca en todas).</summary>
        private static Dictionary<ObjectId, List<ImportPipe>> RedesPresion(Transaction tr)
        {
            var r = new Dictionary<ObjectId, List<ImportPipe>>();
            foreach (ObjectId n in CivilApplication.ActiveDocument.GetPressurePipeNetworkIds()) r[n] = new List<ImportPipe>();
            return r;
        }

        /// <summary>Borra la válvula (sus sólidos y los de su vástago junto al centro) y une de nuevo sus dos tubos en uno,
        /// reconectando las piezas de sus puntas lejanas.</summary>
        internal static string McpQuitarValvula(Editor ed, Database db, Transaction tr, Point2d c, IList<string> solidos, IList<string> tuberias)
        {
            var borrar = new HashSet<ObjectId>();
            foreach (string h in solidos) { ObjectId id = Id(db, h); if (!id.IsNull) borrar.Add(id); }
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            foreach (ObjectId id in ms)
            {
                if (!(tr.GetObject(id, OpenMode.ForRead) is Solid3d so)) continue;
                using (var rb = so.GetXDataForApplication("PDFCAD"))
                {
                    if (rb == null || !rb.AsArray().Any(tv => (tv.Value as string) == "PDFCAD_VALVULA_SOLIDO")) continue;
                }
                try
                {
                    Extents3d x = so.GeometricExtents;
                    var centro = new Point2d((x.MinPoint.X + x.MaxPoint.X) / 2, (x.MinPoint.Y + x.MaxPoint.Y) / 2);
                    if (centro.GetDistanceTo(c) <= 2.0) borrar.Add(id);
                }
                catch { }
            }
            foreach (ObjectId id in borrar) tr.GetObject(id, OpenMode.ForWrite).Erase();
            if (tuberias.Count != 2) return null;

            var t1 = tr.GetObject(Id(db, tuberias[0]), OpenMode.ForRead) as CivilDB.PressurePipe;
            var t2 = tr.GetObject(Id(db, tuberias[1]), OpenMode.ForRead) as CivilDB.PressurePipe;
            if (t1 == null || t2 == null || t1.NetworkId != t2.NetworkId) return "las dos tuberías no son de la misma red a presión: quedan separadas";
            Point3d Lejos(CivilDB.PressurePipe p) =>
                new Point2d(p.StartPoint.X, p.StartPoint.Y).GetDistanceTo(c) > new Point2d(p.EndPoint.X, p.EndPoint.Y).GetDistanceTo(c) ? p.StartPoint : p.EndPoint;
            Point3d A = Lejos(t1), B = Lejos(t2);
            var net = (CivilDB.PressurePipeNetwork)tr.GetObject(t1.NetworkId, OpenMode.ForWrite);
            var tubo = TuboDe(tr, net, t1);
            if (tubo == null) return "no se encontró la pieza del tubo: quedan separadas";
            var conA = ConexionesEnPuntas(tr, net, t1.ObjectId, A, A.IsEqualTo(t1.StartPoint) ? t1.EndPoint : t1.StartPoint).Where(k => k.Item3).ToList();
            var conB = ConexionesEnPuntas(tr, net, t2.ObjectId, B, B.IsEqualTo(t2.StartPoint) ? t2.EndPoint : t2.StartPoint).Where(k => k.Item3).ToList();
            ObjectId estilo = t1.StyleId;
            string desc = "", capa = t1.Layer;
            try { desc = t1.Description; } catch { }
            ObjectId nuevo = net.AddLinePipe(new LineSegment3d(A, B), tubo);
            t1.UpgradeOpen(); t1.Erase();
            t2.UpgradeOpen(); t2.Erase();
            var np = (CivilDB.PressurePipe)tr.GetObject(nuevo, OpenMode.ForWrite);
            try { np.StyleId = estilo; } catch { }
            try { if (!string.IsNullOrEmpty(desc)) np.Description = desc; } catch { }
            try { np.Layer = capa; } catch { }
            foreach (var (parte, puerto, _) in conA)
                try { ((CivilDB.PressurePart)tr.GetObject(parte, OpenMode.ForWrite)).ConnectToPipe(puerto, nuevo, 0); } catch { }
            foreach (var (parte, puerto, _) in conB)
                try { ((CivilDB.PressurePart)tr.GetObject(parte, OpenMode.ForWrite)).ConnectToPipe(puerto, nuevo, 1); } catch { }
            return null;
        }

        /// <summary>Conexión vertical entre las dos tuberías (handles) en (x, y), con las rasantes za/zb: el MISMO armado que
        /// las conexiones aprobadas en la app (`CrearConexionesCruzadas`).</summary>
        internal static void McpConexionVertical(Editor ed, Database db, Transaction tr, string a, string b, double x, double y,
                                                 double za, double zb)
        {
            var pipes = new List<ImportPipe> { ImportDe(tr, db, a, 0), ImportDe(tr, db, b, 1) };
            if (pipes.Any(p => p == null)) throw new Exception("una de las dos tuberías ya no existe");
            bool presion = pipes.All(p => p.NetKind == "pressure");
            var cc = new ImportCrossConnect { X = x, Y = y, PipeA = 0, PipeB = 1, ZA = za, ZB = zb, Valve = presion };
            new ComandosRedes().CrearConexionesCruzadas(ed, db, CivilApplication.ActiveDocument, tr, pipes, new List<ImportCrossConnect> { cc });
        }

        /// <summary>Lo que `CrearConexionesCruzadas` necesita de una tubería ya en el dibujo (dos vértices, diámetro, rasantes).</summary>
        private static ImportPipe ImportDe(Transaction tr, Database db, string h, int idx)
        {
            ObjectId id = Id(db, h);
            if (id.IsNull) return null;
            var e = tr.GetObject(id, OpenMode.ForRead) as Entity;
            Point3d s, f; double diamIn, r; string kind;
            if (e is CivilDB.Pipe p)
            {
                s = p.StartPoint; f = p.EndPoint; diamIn = p.InnerDiameterOrWidth * 12.0; r = p.InnerDiameterOrWidth / 2.0;
                try { if (p.InnerHeight > 1e-6) r = p.InnerHeight / 2.0; } catch { }
                kind = "gravity";
            }
            else if (e is CivilDB.PressurePipe pp)
            {
                s = pp.StartPoint; f = pp.EndPoint; diamIn = pp.NominalDiameter * 12.0; r = pp.NominalDiameter / 2.0; kind = "pressure";
            }
            else return null;
            return new ImportPipe
            {
                Layer = e.Layer, Vertices = new List<Point2d> { new Point2d(s.X, s.Y), new Point2d(f.X, f.Y) }, Diameter = diamIn,
                NetKind = kind, NetType = "pipe", InvStart = s.Z - r, InvEnd = f.Z - r, PipeIdx = idx, Unit = "ft", Material = "",
            };
        }

        private static ObjectId Id(Database db, string handle)
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
