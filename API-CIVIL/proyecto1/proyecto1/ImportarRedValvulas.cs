using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  IMPORTAR_RED paso 5f-bis — VÁLVULAS de compuerta de la app (2026-11-05)
//   · La app exporta un punto `PDFCAD_VALVULA` por válvula: el CENTRO exacto sobre el eje de su tubería
//     (PIPE_IDX, TRAMO, DIR_X/Y = dirección del tramo), el diámetro, la unión (FLG/RG), la pieza (BLOQUE), el
//     material y el largo. La app ya comprobó que va en un TRAMO RECTO y que cabe (con espacio para el codo/T de
//     cada lado): aquí solo se cumple, sin ventana ni preguntas.
//   · La tubería a presión que pasa por ahí se PARTE en las dos caras de la válvula (dos tubos con la misma pieza,
//     estilo, descripción y capa; las piezas conectadas a sus puntas se reconectan) y la válvula se dibuja como
//     SÓLIDOS (cuerpo en V-PRES-VALV-DIA, vástago y tuerca en V-PRES-VALV-INT) con `ValvulaReceta`, la MISMA
//     receta que la Vista 3D de la app: lo que se vio allá es lo que queda aquí.
//   · Colocación = `BaseBloque` del plugin de válvulas del equipo: X = eje de la tubería en 3D, Z = la vertical
//     hecha perpendicular a X, Y = Z × X; escala 1/12 (pulgadas → pies); centro en el eje de la tubería.
//   · Si una válvula no encuentra su tubería o no cabe, no se inventa nada: se avisa y se sigue.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        private const string CAPA_VALVULA_CUERPO = "V-PRES-VALV-DIA";    // ACI 5 (como el plugin de válvulas)
        private const string CAPA_VALVULA_INTERIOR = "V-PRES-VALV-INT";  // ACI 40
        private const double VALVULA_TOL_FT = 0.5;        // la tubería pasa a ≤ esto del centro
        private const double VALVULA_TUBO_MIN_FT = 0.02;  // el plugin no crea tubos más cortos

        private class ImportValvula
        {
            public Point2d Centro;
            public int PipeIdx = -1;
            public Vector2d Dir;
            public double DiamIn, LargoIn;
            public string Union = "FLG", Bloque = "", Material = "";
            public bool Estimada;
        }

        private static ImportValvula LeerValvula(DBPoint pt, Dictionary<string, string> xd)
        {
            var v = new ImportValvula
            {
                Centro = new Point2d(pt.Position.X, pt.Position.Y),
                PipeIdx = string.IsNullOrWhiteSpace(XdStr(xd, "PIPE_IDX", "")) ? -1 : (int)XdDouble(xd, "PIPE_IDX"),
                DiamIn = XdDouble(xd, "DIAMETER"),
                LargoIn = XdDouble(xd, "LARGO_IN"),
                Union = XdStr(xd, "UNION", "FLG"),
                Bloque = XdStr(xd, "BLOQUE", ""),
                Material = XdStr(xd, "MATERIAL", ""),
                Estimada = XdStr(xd, "ESTIMADA", "0") == "1",
            };
            var d = new Vector2d(XdDouble(xd, "DIR_X"), XdDouble(xd, "DIR_Y"));
            v.Dir = d.Length > 1e-9 ? d.GetNormal() : new Vector2d(1, 0);
            return v;
        }

        private static void CrearValvulas(Editor ed, Database db, Dictionary<ObjectId, List<ImportPipe>> redesConOrigen,
                                          List<ImportValvula> valvulas)
        {
            if (valvulas == null || valvulas.Count == 0) return;
            ed.WriteMessage($"\n\n── 5f-bis. Válvulas de la app: {valvulas.Count} ──");
            int puestas = 0;
            foreach (var v in valvulas)
            {
                string nombre = $"{v.Bloque} en ({v.Centro.X:F2},{v.Centro.Y:F2})";
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        string motivo = PonerValvula(ed, db, tr, redesConOrigen, v);
                        if (motivo == null) { tr.Commit(); puestas++; }
                        else { tr.Abort(); ed.WriteMessage($"\n  ⚠ Válvula {nombre}: {motivo} — no se puso."); }
                    }
                    catch (Exception ex)
                    {
                        tr.Abort();
                        ed.WriteMessage($"\n  ✗ Válvula {nombre}: {ex.Message}");
                    }
                }
            }
            ed.WriteMessage($"\n  · {puestas} de {valvulas.Count} válvula(s) puestas (tubería partida en sus caras).");
        }

        /// <summary>Parte la tubería y dibuja la válvula; null si quedó puesta, si no el motivo.</summary>
        private static string PonerValvula(Editor ed, Database db, Transaction tr,
                                           Dictionary<ObjectId, List<ImportPipe>> redesConOrigen, ImportValvula v)
        {
            // 1) La tubería a presión que pasa por el centro, en la red de su utilidad (o en cualquiera de presión).
            var redes = redesConOrigen.Where(kv => kv.Value.Any(p => p.PipeIdx == v.PipeIdx && v.PipeIdx >= 0))
                                      .Select(kv => kv.Key).ToList();
            if (redes.Count == 0) redes = redesConOrigen.Keys.ToList();
            CivilDB.PressurePipe mejor = null;
            ObjectId mejorRed = ObjectId.Null;
            double mejorD = VALVULA_TOL_FT, mejorT = 0;
            foreach (ObjectId nid in redes)
            {
                var net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                if (net == null) continue;
                foreach (ObjectId pid in net.GetPipeIds())
                {
                    var pp = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                    if (pp == null) continue;
                    var a = new Point2d(pp.StartPoint.X, pp.StartPoint.Y);
                    var b = new Point2d(pp.EndPoint.X, pp.EndPoint.Y);
                    Vector2d ab = b - a;
                    double L2 = ab.DotProduct(ab);
                    if (L2 < 1e-12) continue;
                    if (Math.Abs(ab.GetNormal().DotProduct(v.Dir)) < Math.Cos(2.0 * Math.PI / 180.0)) continue;  // otro rumbo
                    double t = (v.Centro - a).DotProduct(ab) / L2;
                    if (t <= 0 || t >= 1) continue;
                    double d = (a + ab * t).GetDistanceTo(v.Centro);
                    if (d < mejorD) { mejorD = d; mejor = pp; mejorRed = nid; mejorT = t; }
                }
            }
            if (mejor == null) return $"no hay una tubería a presión que pase por el centro (≤{VALVULA_TOL_FT} ft) con su rumbo";

            Point3d A = mejor.StartPoint, B = mejor.EndPoint;
            Vector3d u = (B - A).GetNormal();
            Point3d c = A + (B - A) * mejorT;
            double medio = v.LargoIn / 12.0 / 2.0;
            Point3d pA = c - u * medio, pB = c + u * medio;
            if (A.DistanceTo(pA) < VALVULA_TUBO_MIN_FT || B.DistanceTo(pB) < VALVULA_TUBO_MIN_FT
                || (pA - A).DotProduct(u) <= 0 || (B - pB).DotProduct(u) <= 0)
                return $"no cabe en el tubo de {A.DistanceTo(B):F2} ft (la válvula mide {2 * medio:F2} ft)";

            // 2) Partir: dos tubos nuevos (A→pA, pB→B) con la misma pieza y lo que llevaba; reconectar sus puntas.
            var net2 = (CivilDB.PressurePipeNetwork)tr.GetObject(mejorRed, OpenMode.ForWrite);
            PresStyles.PressurePartSize tubo = TuboDe(tr, net2, mejor);
            if (tubo == null) return "no se encontró la pieza del tubo en la lista de partes de su red";
            var conexiones = ConexionesEnPuntas(tr, net2, mejor.ObjectId, A, B);
            mejor.UpgradeOpen();
            ObjectId estilo = mejor.StyleId;
            string desc = "", capa = mejor.Layer;
            try { desc = mejor.Description; } catch { }
            ObjectId h1 = net2.AddLinePipe(new LineSegment3d(A, pA), tubo);
            ObjectId h2 = net2.AddLinePipe(new LineSegment3d(pB, B), tubo);
            mejor.Erase();
            foreach (ObjectId h in new[] { h1, h2 })
            {
                var np = (CivilDB.PressurePipe)tr.GetObject(h, OpenMode.ForWrite);
                try { np.StyleId = estilo; } catch { }
                try { if (!string.IsNullOrEmpty(desc)) np.Description = desc; } catch { }
                try { np.Layer = capa; } catch { }
            }
            foreach (var (parteId, puerto, enA) in conexiones)
            {
                try
                {
                    var parte = (CivilDB.PressurePart)tr.GetObject(parteId, OpenMode.ForWrite);
                    if (enA) parte.ConnectToPipe(puerto, h1, 0);
                    else parte.ConnectToPipe(puerto, h2, 1);
                }
                catch (Exception exC) { ed.WriteMessage($"\n  ⚠ Válvula {v.Bloque}: no se pudo reconectar una pieza ({exC.Message})."); }
            }

            // 3) La válvula: misma orientación que en la app (X = dirección del tramo de la app).
            Vector3d ex = u;
            if (new Vector2d(u.X, u.Y).DotProduct(v.Dir) < 0) ex = -u;
            Vector3d up = Vector3d.ZAxis;
            Vector3d ez = up - ex * up.DotProduct(ex);
            if (ez.Length < 1e-6) ez = Vector3d.YAxis - ex * Vector3d.YAxis.DotProduct(ex);
            ez = ez.GetNormal();
            Vector3d ey = ez.CrossProduct(ex).GetNormal();
            Matrix3d m = Matrix3d.AlignCoordinateSystem(Point3d.Origin, Vector3d.XAxis, Vector3d.YAxis, Vector3d.ZAxis,
                                                        c, ex, ey, ez)
                         * Matrix3d.Scaling(1.0 / 12.0, Point3d.Origin);
            var rec = ValvulaReceta.Receta(v.DiamIn, v.Union);
            AsegurarCapaValvula(tr, db, CAPA_VALVULA_CUERPO, 5);
            AsegurarCapaValvula(tr, db, CAPA_VALVULA_INTERIOR, 40);
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
            int idxPipe = v.PipeIdx;
            string nombreRed = "";
            try { nombreRed = net2.Name; } catch { }
            foreach (int capaPieza in new[] { 0, 1 })
            {
                Solid3d s = SolidoValvula(rec, capaPieza);
                if (s == null) continue;
                s.TransformBy(m);
                s.Layer = capaPieza == 0 ? CAPA_VALVULA_CUERPO : CAPA_VALVULA_INTERIOR;
                s.ColorIndex = 256;                                   // PorCapa
                ms.AppendEntity(s);
                tr.AddNewlyCreatedDBObject(s, true);
                s.XData = new ResultBuffer(
                    new TypedValue((int)DxfCode.ExtendedDataRegAppName, "PDFCAD"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "PDFCAD_VALVULA_SOLIDO"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "BLOQUE=" + rec.Bloque),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "DIAMETER=" + v.DiamIn.ToString("0.##", CultureInfo.InvariantCulture)),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "UNION=" + (rec.Tipo == "RG" ? "RG" : "FLG")),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "MATERIAL=" + v.Material),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "PARTE=" + (capaPieza == 0 ? "CUERPO" : "VASTAGO")),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "ESTIMADA=" + (rec.Estimada ? "1" : "0")),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "PIPE_IDX=" + idxPipe.ToString(CultureInfo.InvariantCulture)));
                if (capaPieza == 0)
                    MarcarComoAccesorio(tr, db, s, rec, v, c, 2 * medio, nombreRed);
            }
            Dl(ed, $"\n  [VALVULA] {rec.Bloque} en ({c.X:F2},{c.Y:F2},{c.Z:F3}) largo {2 * medio:F3} ft — tubo partido en {h1.Handle}/{h2.Handle}.");
            return null;
        }

        /// <summary>El cuerpo de la válvula lleva además el XDATA de accesorio sólido (`WyeSolido.APP_XDATA`, TIPO=VALVE):
        /// así CREAR_PERFIL_RED une los dos tubos a través de ella (como a través de un codo o una Tee, por COORD_X/Y,
        /// COTA_EJE_FT y LARGO_TOTAL_FT) y la rotula «{D}" FLG|MJ GATE VALVE».</summary>
        private static void MarcarComoAccesorio(Transaction tr, Database db, Solid3d cuerpo, RecetaValvula rec,
                                                ImportValvula v, Point3d c, double largoFt, string red)
        {
            var rat = (RegAppTable)tr.GetObject(db.RegAppTableId, OpenMode.ForRead);
            if (!rat.Has(WyeSolido.APP_XDATA))
            {
                rat.UpgradeOpen();
                var rar = new RegAppTableRecord { Name = WyeSolido.APP_XDATA };
                rat.Add(rar);
                tr.AddNewlyCreatedDBObject(rar, true);
            }
            string F(double x, string f) => x.ToString(f, CultureInfo.InvariantCulture);
            using (var rb = new ResultBuffer(
                new TypedValue((int)DxfCode.ExtendedDataRegAppName, WyeSolido.APP_XDATA),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "TIPO=VALVE"),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "ANGULO=0.0"),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "DIAM_PRINCIPAL_IN=" + F(v.DiamIn, "0.##")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "DIAM_RAMAL_IN=" + F(v.DiamIn, "0.##")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "N_PUERTOS=2"),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "LARGO_TOTAL_FT=" + F(largoFt, "F3")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "COORD_X=" + F(c.X, "F3")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "COORD_Y=" + F(c.Y, "F3")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "COTA_EJE_FT=" + F(c.Z, "F3")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "MATERIAL=" + v.Material),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "RED=" + red),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "UNION=" + (rec.Tipo == "RG" ? "RG" : "FLG")),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "BLOQUE=" + rec.Bloque),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, "ORIGEN=PDFCAD_VALVULA")))
            {
                cuerpo.XData = rb;                     // se suma al XDATA «PDFCAD» (otra app)
            }
        }

        /// <summary>La pieza (PressurePartSize) del tubo en la lista de partes de su red: misma descripción o, si no,
        /// el diámetro nominal más cercano.</summary>
        private static PresStyles.PressurePartSize TuboDe(Transaction tr, CivilDB.PressurePipeNetwork net, CivilDB.PressurePipe pp)
        {
            try
            {
                var pl = tr.GetObject(net.PartsListId, OpenMode.ForRead) as PresStyles.PressurePartList;
                var tubos = pl?.GetParts(CivilDB.PressurePartDomainType.Pipe);
                if (tubos == null || tubos.Count == 0) return null;
                string d = pp.PartDescription;
                var igual = tubos.FirstOrDefault(t => string.Equals(t.Description, d, StringComparison.OrdinalIgnoreCase));
                if (igual != null) return igual;
                double dn = pp.NominalDiameter;
                return tubos.OrderBy(t =>
                {
                    double x = ComandosPresion.ExtraerDiametroDeDescripcion(t.Description) / 12.0;
                    return x > 0 ? Math.Abs(x - dn) : double.MaxValue;
                }).First();
            }
            catch { return null; }
        }

        /// <summary>[(pieza, su puerto, en la punta A)] de los accesorios/apurtenencias conectados al tubo.</summary>
        private static List<(ObjectId, int, bool)> ConexionesEnPuntas(Transaction tr, CivilDB.PressurePipeNetwork net,
                                                                     ObjectId pipeId, Point3d A, Point3d B)
        {
            var out_ = new List<(ObjectId, int, bool)>();
            var ids = new List<ObjectId>();
            try { foreach (ObjectId id in net.GetFittingIds()) ids.Add(id); } catch { }
            try { foreach (ObjectId id in net.GetAppurtenanceIds()) ids.Add(id); } catch { }
            foreach (ObjectId id in ids)
            {
                try
                {
                    var parte = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressurePart;
                    if (parte == null) continue;
                    for (int i = 0; i < parte.ConnectionCount; i++)
                    {
                        var cx = parte.GetConnectionAt(i);
                        if (cx.ConnectedId != pipeId) continue;
                        out_.Add((id, i, cx.Position.DistanceTo(A) <= cx.Position.DistanceTo(B)));
                    }
                }
                catch { }
            }
            return out_;
        }

        private static void AsegurarCapaValvula(Transaction tr, Database db, string nombre, short aci)
        {
            var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (lt.Has(nombre)) return;
            lt.UpgradeOpen();
            var r = new LayerTableRecord { Name = nombre, Color = Color.FromColorIndex(ColorMethod.ByAci, aci) };
            lt.Add(r);
            tr.AddNewlyCreatedDBObject(r, true);
        }

        // ── Sólidos de la receta (pulgadas, sistema de la válvula) ──────────────────────────────────

        /// <summary>Todas las piezas de una capa unidas en un sólido; el cuerpo, con su paso interior y los agujeros
        /// de los pernos restados. null si la capa no tiene piezas.</summary>
        private static Solid3d SolidoValvula(RecetaValvula rec, int capa)
        {
            Solid3d todo = null;
            var restar = new List<Solid3d>();
            foreach (var p in rec.Piezas)
            {
                if (p.Capa != capa) continue;
                Solid3d s;
                switch (p.Tipo)
                {
                    case PiezaValvulaTipo.Tubo:
                    case PiezaValvulaTipo.Brida:
                        s = CilindroSol(p.R, p.X1 - p.X0, new Point3d(p.X0, 0, 0), 'x');
                        if (p.Tipo == PiezaValvulaTipo.Brida && p.NPernos > 0 && p.RAgujero > 0)
                            for (int i = 0; i < p.NPernos; i++)
                            {
                                double a = 2.0 * Math.PI * (i + 0.5) / p.NPernos;
                                restar.Add(CilindroSol(p.RAgujero, p.X1 - p.X0 + 0.2,
                                    new Point3d(p.X0 - 0.1, p.RPernos * Math.Cos(a), p.RPernos * Math.Sin(a)), 'x'));
                            }
                        break;
                    case PiezaValvulaTipo.Caja:
                        s = new Solid3d();
                        s.CreateBox(p.Max[0] - p.Min[0], p.Max[1] - p.Min[1], p.Max[2] - p.Min[2]);
                        s.TransformBy(Matrix3d.Displacement(new Vector3d((p.Min[0] + p.Max[0]) / 2, (p.Min[1] + p.Max[1]) / 2,
                                                                          (p.Min[2] + p.Max[2]) / 2)));
                        break;
                    case PiezaValvulaTipo.Cil:
                        s = CilindroSol(p.R, p.Largo, new Point3d(p.Inicio[0], p.Inicio[1], p.Inicio[2]), p.Eje);
                        break;
                    default:   // Toro: aro en el plano XZ (eje Y)
                        s = new Solid3d();
                        s.CreateTorus(p.R, p.Rt);
                        s.TransformBy(Matrix3d.Rotation(Math.PI / 2.0, Vector3d.XAxis, Point3d.Origin));
                        s.TransformBy(Matrix3d.Displacement(new Vector3d(p.Centro[0], p.Centro[1], p.Centro[2])));
                        break;
                }
                if (todo == null) todo = s;
                else { todo.BooleanOperation(BooleanOperationType.BoolUnite, s); s.Dispose(); }
            }
            if (todo == null) return null;
            if (capa == 0)
            {
                double h = rec.Largo / 2.0;
                restar.Add(CilindroSol(rec.N / 2.0, rec.Largo + 2.0, new Point3d(-h - 1.0, 0, 0), 'x'));   // paso interior
            }
            foreach (var r in restar)
            {
                try { todo.BooleanOperation(BooleanOperationType.BoolSubtract, r); }
                catch { }
                r.Dispose();
            }
            return todo;
        }

        /// <summary>Cilindro de radio r y largo L desde `inicio` a lo largo del eje ('x' | 'y' | 'z').</summary>
        private static Solid3d CilindroSol(double r, double L, Point3d inicio, char eje)
        {
            var s = new Solid3d();
            s.CreateFrustum(L, r, r, r);                         // a lo largo de Z, centrado en el origen
            s.TransformBy(Matrix3d.Displacement(new Vector3d(0, 0, L / 2.0)));   // de z = 0 a z = L
            if (eje == 'x') s.TransformBy(Matrix3d.Rotation(Math.PI / 2.0, Vector3d.YAxis, Point3d.Origin));
            else if (eje == 'y') s.TransformBy(Matrix3d.Rotation(-Math.PI / 2.0, Vector3d.XAxis, Point3d.Origin));
            s.TransformBy(Matrix3d.Displacement(inicio - Point3d.Origin));
            return s;
        }
    }
}
