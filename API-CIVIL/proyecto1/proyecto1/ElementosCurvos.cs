using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        [CommandMethod("AGREGAR_TUBO_CURVO")]
        public void AgregarTuboCurvo()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            ed.WriteMessage("\n═══ AGREGAR TUBERÍA CURVA ═══");
            ed.WriteMessage("\nSeleccione dos tuberías rectas que compartan un extremo (esquina).");

            var peo1 = new PromptEntityOptions("\nSeleccione la PRIMERA tubería:");
            peo1.SetRejectMessage("\nDebe ser una tubería de Civil 3D (Pipe).");
            peo1.AddAllowedClass(typeof(CivilDB.Pipe), false);
            PromptEntityResult r1 = ed.GetEntity(peo1);
            if (r1.Status != PromptStatus.OK) return;

            var peo2 = new PromptEntityOptions("\nSeleccione la SEGUNDA tubería:");
            peo2.SetRejectMessage("\nDebe ser una tubería de Civil 3D (Pipe).");
            peo2.AddAllowedClass(typeof(CivilDB.Pipe), false);
            PromptEntityResult r2 = ed.GetEntity(peo2);
            if (r2.Status != PromptStatus.OK) return;

            if (r1.ObjectId == r2.ObjectId)
            {
                ed.WriteMessage("\n✗ Ha seleccionado la misma tubería dos veces.");
                return;
            }

            var pdr = new PromptDoubleOptions("\nRadio de la curva en pies (0 = automático, 6× diámetro):");
            pdr.DefaultValue = 0.0;
            pdr.AllowNegative = false;
            pdr.AllowZero = true;
            pdr.UseDefaultValue = true;
            PromptDoubleResult rr = ed.GetDouble(pdr);
            if (rr.Status != PromptStatus.OK) return;
            double radioUsuario = rr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var pipe1 = (CivilDB.Pipe)tr.GetObject(r1.ObjectId, OpenMode.ForRead);
                    var pipe2 = (CivilDB.Pipe)tr.GetObject(r2.ObjectId, OpenMode.ForRead);

                    ObjectId netId1 = pipe1.NetworkId;
                    ObjectId netId2 = pipe2.NetworkId;
                    if (netId1 != netId2)
                    {
                        ed.WriteMessage("\n✗ Las dos tuberías deben pertenecer a la misma red.");
                        tr.Abort();
                        return;
                    }

                    var net = (CivilDB.Network)tr.GetObject(netId1, OpenMode.ForWrite);
                    var partsList = (PartsStyles.PartsList)tr.GetObject(
                        net.PartsListId, OpenMode.ForRead);

                    Point3d s1 = pipe1.StartPoint, e1 = pipe1.EndPoint;
                    Point3d s2 = pipe2.StartPoint, e2 = pipe2.EndPoint;

                    const double tol = 0.5;
                    Point3d corner;
                    Point3d farEnd1, farEnd2;
                    if (s1.DistanceTo(s2) < tol) { corner = Mid(s1, s2); farEnd1 = e1; farEnd2 = e2; }
                    else if (s1.DistanceTo(e2) < tol) { corner = Mid(s1, e2); farEnd1 = e1; farEnd2 = s2; }
                    else if (e1.DistanceTo(s2) < tol) { corner = Mid(e1, s2); farEnd1 = s1; farEnd2 = e2; }
                    else if (e1.DistanceTo(e2) < tol) { corner = Mid(e1, e2); farEnd1 = s1; farEnd2 = s2; }
                    else
                    {
                        ed.WriteMessage($"\n✗ Las dos tuberías no comparten un extremo (tolerancia {tol:F1}').");
                        ed.WriteMessage($"\n  Pipe1: ({s1.X:F2},{s1.Y:F2}) → ({e1.X:F2},{e1.Y:F2})");
                        ed.WriteMessage($"\n  Pipe2: ({s2.X:F2},{s2.Y:F2}) → ({e2.X:F2},{e2.Y:F2})");
                        tr.Abort();
                        return;
                    }

                    Vector3d dir1 = (farEnd1 - corner).GetNormal();
                    Vector3d dir2 = (farEnd2 - corner).GetNormal();

                    double dot = dir1.X * dir2.X + dir1.Y * dir2.Y;
                    double angleDeg = Math.Acos(Math.Max(-1, Math.Min(1, dot))) * 180.0 / Math.PI;
                    if (angleDeg < 1.0)
                    {
                        ed.WriteMessage($"\n✗ El ángulo entre las tuberías es ~{angleDeg:F1}° — son casi paralelas, no hay esquina.");
                        tr.Abort();
                        return;
                    }

                    double dist1 = corner.DistanceTo(farEnd1);
                    double dist2 = corner.DistanceTo(farEnd2);

                    double halfAngle = (Math.PI - Math.Acos(Math.Max(-1, Math.Min(1, dot)))) / 2.0;
                    double tanHalf = Math.Tan(halfAngle);
                    if (tanHalf < 1e-9)
                    {
                        ed.WriteMessage("\n✗ El ángulo de deflexión es demasiado pequeño para una curva.");
                        tr.Abort();
                        return;
                    }

                    double radio;
                    if (radioUsuario > 0.01)
                    {
                        radio = radioUsuario;
                    }
                    else
                    {
                        double diam = 0;
                        try
                        {
                            var pIH = pipe1.GetType().GetProperty("InnerHeight");
                            if (pIH != null) diam = (double)pIH.GetValue(pipe1);
                            var pIW = pipe1.GetType().GetProperty("InnerDiameterOrWidth");
                            if (pIW != null) diam = Math.Max(diam, (double)pIW.GetValue(pipe1));
                        }
                        catch { }
                        if (diam < 0.1) diam = 1.0;
                        radio = 6.0 * diam;
                    }

                    double t = radio * tanHalf;
                    double maxT = Math.Min(dist1, dist2) * 0.45;
                    if (t > maxT)
                    {
                        radio = maxT / tanHalf;
                        t = maxT;
                        ed.WriteMessage($"\n⚠ Radio ajustado a {radio:F2}' para caber entre las tuberías.");
                    }

                    Point3d p1 = new Point3d(
                        corner.X + t * dir1.X, corner.Y + t * dir1.Y,
                        corner.Z + (t / dist1) * (farEnd1.Z - corner.Z));
                    Point3d p2 = new Point3d(
                        corner.X + t * dir2.X, corner.Y + t * dir2.Y,
                        corner.Z + (t / dist2) * (farEnd2.Z - corner.Z));

                    double radioReal; bool horario;
                    CircularArc3d arco = ArcoTangente(p1, p2, corner, out radioReal, out horario);

                    string diamStr = $"{pipe1.InnerDiameterOrWidth:F2}";
                    string matDesc = pipe1.PartDescription ?? "";
                    ObjectId pipeFam, pipeSize; string pipeNom;
                    if (!BuscarTuberia(tr, partsList, matDesc, diamStr,
                                       out pipeFam, out pipeSize, out pipeNom))
                    {
                        if (!BuscarTuberia(tr, partsList, "", diamStr,
                                           out pipeFam, out pipeSize, out pipeNom))
                        {
                            ed.WriteMessage("\n✗ No se encontró la familia/tamaño de tubería en la Parts List.");
                            tr.Abort();
                            return;
                        }
                    }

                    ObjectId arcId = ObjectId.Null;
                    net.AddCurvePipe(pipeFam, pipeSize, arco, horario, ref arcId, false);
                    var arcoPipe = (CivilDB.Pipe)tr.GetObject(arcId, OpenMode.ForWrite);

                    try
                    {
                        var desc1 = pipe1.Description;
                        if (!string.IsNullOrWhiteSpace(desc1))
                            arcoPipe.Description = desc1;
                    }
                    catch { }

                    pipe1 = (CivilDB.Pipe)tr.GetObject(r1.ObjectId, OpenMode.ForWrite);
                    pipe2 = (CivilDB.Pipe)tr.GetObject(r2.ObjectId, OpenMode.ForWrite);

                    RecortarTuboEnEsquina(pipe1, corner, p1, tol);
                    RecortarTuboEnEsquina(pipe2, corner, p2, tol);

                    ed.WriteMessage($"\n✓ Tubería curva creada:");
                    ed.WriteMessage($"\n  Radio:     {radioReal:F2}'");
                    ed.WriteMessage($"\n  Ángulo:    {angleDeg:F1}°");
                    ed.WriteMessage($"\n  Tangencia: ({p1.X:F2},{p1.Y:F2}) → ({p2.X:F2},{p2.Y:F2})");

                    // El EJE de la red también debe seguir el arco, no cortarlo con la
                    // cuerda. Es un extra "best effort": si algo falla la tubería curva
                    // ya quedó bien, así que se avisa y se sigue (nunca se aborta).
                    RedondearEjeEnEsquina(tr, net, corner, PuntoMedioArco(arco, p1, p2), ed);

                    tr.Commit();
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n✗ Error: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        private static Point3d Mid(Point3d a, Point3d b)
        {
            return new Point3d((a.X + b.X) / 2, (a.Y + b.Y) / 2, (a.Z + b.Z) / 2);
        }

        private static void RecortarTuboEnEsquina(CivilDB.Pipe pipe, Point3d corner,
                                                    Point3d tangencia, double tol)
        {
            try
            {
                Point3d s = pipe.StartPoint, e = pipe.EndPoint;
                bool startEsEsquina = s.DistanceTo(corner) < tol + 0.1;
                if (startEsEsquina)
                    pipe.StartPoint = tangencia;
                else
                    pipe.EndPoint = tangencia;
            }
            catch { }
        }

        // Punto SOBRE el arco a media curva: se proyecta desde el centro hacia el
        // punto medio de la cuerda, a distancia radio. Es lo que pide AddFreeCurve
        // para fijar por dónde debe pasar el fillet.
        private static Point3d PuntoMedioArco(CircularArc3d arco, Point3d p1, Point3d p2)
        {
            Point3d c = arco.Center;
            double r = arco.Radius;
            double mx = (p1.X + p2.X) / 2.0, my = (p1.Y + p2.Y) / 2.0;
            double dx = mx - c.X, dy = my - c.Y;
            double len = Math.Sqrt(dx * dx + dy * dy);
            if (len < 1e-9) return new Point3d(mx, my, (p1.Z + p2.Z) / 2.0);
            return new Point3d(c.X + r * dx / len, c.Y + r * dy / len, (p1.Z + p2.Z) / 2.0);
        }

        // Aplica un "Free curve fillet" en el ALINEAMIENTO de la red, en la misma
        // esquina donde se acaba de crear la tubería curva: busca las dos tangentes
        // que se juntan en `corner` y mete un arco libre entre ellas que pase por
        // `pMedArco` — así el eje queda con el mismo radio que el tubo.
        private static void RedondearEjeEnEsquina(Transaction tr, CivilDB.Network net,
                                                   Point3d corner, Point3d pMedArco, Editor ed)
        {
            try
            {
                ObjectId alignId = net.ReferenceAlignmentId;
                if (alignId.IsNull)
                {
                    ed.WriteMessage("\n  ⓘ La red no tiene alineamiento asociado: no se redondeó ningún eje.");
                    return;
                }
                var align = (CivilDB.Alignment)tr.GetObject(alignId, OpenMode.ForWrite);

                // Tolerancia generosa: el eje pudo recortarse al borde de un buzón,
                // pero el vértice de la esquina (PI) sigue en su sitio.
                const double tolEje = 1.0;
                int idAntes = -1, idDespues = -1;
                foreach (CivilDB.AlignmentEntity ent in align.Entities)
                {
                    var line = ent as CivilDB.AlignmentLine;
                    if (line == null) continue;          // ya es un arco u otra cosa
                    Point2d s = line.StartPoint, e = line.EndPoint;
                    if (Math.Sqrt((e.X - corner.X) * (e.X - corner.X) +
                                  (e.Y - corner.Y) * (e.Y - corner.Y)) <= tolEje)
                        idAntes = line.EntityId;
                    if (Math.Sqrt((s.X - corner.X) * (s.X - corner.X) +
                                  (s.Y - corner.Y) * (s.Y - corner.Y)) <= tolEje)
                        idDespues = line.EntityId;
                }

                if (idAntes < 0 || idDespues < 0 || idAntes == idDespues)
                {
                    ed.WriteMessage("\n  ⓘ No se encontraron dos tangentes del eje en esa esquina: " +
                                    "el eje quedó sin redondear (la tubería curva sí se creó).");
                    return;
                }

                // Sobrecarga "pasa por un punto": fija el radio implícitamente por
                // geometría, sin depender de enums de parámetro de curva.
                var arc = align.Entities.AddFreeCurve(idAntes, idDespues, pMedArco);

                // Las tangentes son entidades FIJAS (el alignment nació de una
                // polilínea): meter el fillet NO las acorta, siguen dibujándose
                // hasta el vértice original y queda un "pico" residual encima del
                // eje curvo. Se recortan a los puntos de tangencia reales del arco.
                // PassThroughPoint1/2 son los dos puntos que definen una línea fija:
                // el 2 es su final y el 1 su inicio, así que a la de ANTES se le
                // mueve el final y a la de DESPUÉS el inicio.
                try
                {
                    Point2d tanIni = arc.StartPoint, tanFin = arc.EndPoint;
                    // Re-obtener por id: tras AddFreeCurve las referencias previas
                    // pueden haber quedado obsoletas.
                    var lnAntes = align.Entities.EntityAtId(idAntes) as CivilDB.AlignmentLine;
                    if (lnAntes != null) lnAntes.PassThroughPoint2 = tanIni;
                    var lnDespues = align.Entities.EntityAtId(idDespues) as CivilDB.AlignmentLine;
                    if (lnDespues != null) lnDespues.PassThroughPoint1 = tanFin;
                    ed.WriteMessage("\n  ✓ Eje redondeado con el mismo arco (Free curve fillet); " +
                                    "tangentes recortadas a los puntos de tangencia.");
                }
                catch (Exception exT)
                {
                    ed.WriteMessage($"\n  ⚠ Eje redondeado, pero quedó tangente sobrante sin recortar " +
                                     $"({exT.Message}). Bórrala a mano o recorta la entidad del eje.");
                }
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n  ⓘ No se pudo redondear el eje ({ex.Message}); " +
                                 "la tubería curva sí quedó creada.");
            }
        }
    }
}
