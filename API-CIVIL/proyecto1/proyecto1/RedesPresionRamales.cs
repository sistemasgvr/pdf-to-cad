using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  UNIONES MÚLTIPLES y RAMIFICACIONES de la red a presión (partial de ComandosPresion):
//   · UNIR_VARIAS_PRESION  → une 3 tubos con una Tee (o 4 con una Cruz).
//   · RAMIFICAR_PRESION    → inserta una Tee en la principal (partiéndola) + tubo de
//                            ramal + hidrante/válvula al final, todo conectado.
//  Reutiliza helpers privados: ElegirRedId, ElegirPiezaPresion, ConexionEnPuerto, capas.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosPresion
    {
        // =====================================================================
        // UNIR_VARIAS_PRESION — selecciona 3 (Tee) o 4 (Cruz) tuberías que llegan a
        //   un mismo punto, coloca el accesorio y conecta cada tubo a un puerto.
        // =====================================================================
        [CommandMethod("UNIR_VARIAS_PRESION")]
        public void UnirVariasPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptSelectionResult sel = ed.GetSelection(new PromptSelectionOptions
            { MessageForAdding = "\nSeleccione 3 tuberías (Tee) o 4 (Cruz) que se encuentran en un punto:" });
            if (sel.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }
            ObjectId[] ids = sel.Value.GetObjectIds();

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión."); tr.Abort(); return; }
                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);
                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

                    // Reunir sólo las tuberías a presión seleccionadas
                    var pipeIds = new List<ObjectId>();
                    var pipes = new List<CivilDB.PressurePipe>();
                    foreach (ObjectId id in ids)
                    {
                        var p = tr.GetObject(id, OpenMode.ForWrite) as CivilDB.PressurePipe;
                        if (p != null) { pipeIds.Add(id); pipes.Add(p); }
                    }
                    int nP = pipes.Count;
                    if (nP < 3 || nP > 4) { ed.WriteMessage($"\nSelecciona 3 tuberías (Tee) o 4 (Cruz). Recibí {nP}."); tr.Abort(); return; }

                    // Punto de encuentro (junta) y, por tubo, cuál extremo está en la junta
                    Point3d[][] e = pipes.Select(p => new[] { p.StartPoint, p.EndPoint }).ToArray();
                    var todos = new List<Point3d>(); foreach (var pr in e) { todos.Add(pr[0]); todos.Add(pr[1]); }
                    Point3d guia = todos[0]; double best = double.MaxValue;
                    foreach (Point3d c in todos)
                    {
                        double s = 0; for (int i = 0; i < nP; i++) s += Math.Min(c.DistanceTo(e[i][0]), c.DistanceTo(e[i][1]));
                        if (s < best) { best = s; guia = c; }
                    }
                    int[] nearPort = new int[nP];
                    Point3d[] nearPt = new Point3d[nP];
                    for (int i = 0; i < nP; i++)
                    {
                        nearPort[i] = e[i][0].DistanceTo(guia) <= e[i][1].DistanceTo(guia) ? 0 : 1;
                        nearPt[i] = e[i][nearPort[i]];
                    }
                    Point3d junta = new Point3d(nearPt.Average(p => p.X), nearPt.Average(p => p.Y), nearPt.Average(p => p.Z));

                    // Direcciones (desde la junta hacia el otro extremo de cada tubo)
                    Vector3d[] dir = new Vector3d[nP];
                    for (int i = 0; i < nP; i++)
                    {
                        Vector3d v = e[i][1 - nearPort[i]] - junta;
                        dir[i] = v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis;
                    }
                    // Par más "opuesto" (colineales) -> puertos de PASO (0,1); resto -> RAMAL (2,3)
                    int ra = 0, rb = 1; double mejor = double.MaxValue;
                    for (int i = 0; i < nP; i++)
                        for (int j = i + 1; j < nP; j++)
                        { double dot = dir[i].DotProduct(dir[j]); if (dot < mejor) { mejor = dot; ra = i; rb = j; } }
                    var orden = new List<int> { ra, rb };
                    for (int i = 0; i < nP; i++) if (i != ra && i != rb) orden.Add(i);

                    // Elegir el accesorio del tipo correcto
                    CivilDB.PressurePartType tipo = nP == 3 ? CivilDB.PressurePartType.Tee : CivilDB.PressurePartType.Cross;
                    var fittings = pl.GetParts(CivilDB.PressurePartDomainType.Fitting).Where(f => f.PartType == tipo).ToList();
                    if (fittings.Count == 0) { ed.WriteMessage($"\nLa parts list no tiene un accesorio tipo {tipo}. Añádelo al catálogo."); tr.Abort(); return; }
                    PresStyles.PressurePartSize pieza = ElegirPiezaPresion(ed, fittings, $"{tipo} disponibles");
                    if (pieza == null) { tr.Abort(); return; }

                    // Colocar y conectar cada tubo a su puerto
                    ObjectId fid = net.AddFitting(junta, pieza);
                    CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(fid, OpenMode.ForWrite);
                    int okCon = 0;
                    for (int port = 0; port < orden.Count; port++)
                    {
                        int k = orden[port];
                        try { parte.ConnectToPipe(port, pipeIds[k], nearPort[k]); okCon++; }
                        catch (Exception ex) { ed.WriteMessage($"\n  ✗ Puerto {port}: {ex.Message}"); }
                    }

                    // Recortar cada tubo al puerto real del accesorio (para que calce)
                    try
                    {
                        for (int i = 0; i < parte.ConnectionCount; i++)
                        {
                            CivilDB.PressurePartConnection c = parte.GetConnectionAt(i);
                            int k = pipeIds.IndexOf(c.ConnectedId);
                            if (k < 0) continue;
                            if (nearPort[k] == 0) pipes[k].StartPoint = c.Position; else pipes[k].EndPoint = c.Position;
                        }
                    }
                    catch { }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ {tipo} '{pieza.Description}' colocada; {okCon} de {nP} tuberías conectadas.");
                    if (okCon < nP) ed.WriteMessage("\n  (Alguna no conectó: revisa que los diámetros coincidan con el accesorio.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // RAMIFICAR_PRESION — inserta una Tee en un punto de la tubería principal
        //   (partiéndola en dos), crea un tubo de ramal y coloca un hidrante/válvula
        //   al final del ramal, conectando todo.
        // =====================================================================
        [CommandMethod("RAMIFICAR_PRESION")]
        public void RamificarPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Tubería principal
            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la tubería PRINCIPAL a ramificar:");
            peo.SetRejectMessage("\nDebe ser una tubería a presión.");
            peo.AddAllowedClass(typeof(CivilDB.PressurePipe), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            // Punto del ramal (sobre la principal) y extremo del ramal
            PromptPointResult pCorte = ed.GetPoint("\nPunto del ramal SOBRE la principal:");
            if (pCorte.Status != PromptStatus.OK) return;
            PromptPointResult pFin = ed.GetPoint("\nExtremo del ramal (donde irá el hidrante/válvula):");
            if (pFin.Status != PromptStatus.OK) return;

            // Elemento al final del ramal
            PromptKeywordOptions pk = new PromptKeywordOptions("\nElemento al final del ramal: [Hidrante/Valvula/Ninguno] <Hidrante>:", "Hidrante Valvula Ninguno");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            string elem = (rk.Status == PromptStatus.OK) ? rk.StringResult : "Hidrante";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Red que contiene la principal
                    CivilDB.PressurePipeNetwork net = null;
                    foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
                    {
                        var n = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (n == null) continue;
                        foreach (ObjectId pid in n.GetPipeIds())
                            if (pid == per.ObjectId) { net = (CivilDB.PressurePipeNetwork)tr.GetObject(nid, OpenMode.ForWrite); break; }
                        if (net != null) break;
                    }
                    if (net == null) { ed.WriteMessage("\nNo se halló la red de esa tubería."); tr.Abort(); return; }
                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

                    // Piezas: tubo (para mitades + ramal), Tee, y el appurtenance del final
                    PresStyles.PressurePartSize tubo = ElegirPiezaPresion(ed, pl.GetParts(CivilDB.PressurePartDomainType.Pipe), "Tubo (para mitades y ramal)");
                    if (tubo == null) { tr.Abort(); return; }
                    var tees = pl.GetParts(CivilDB.PressurePartDomainType.Fitting).Where(f => f.PartType == CivilDB.PressurePartType.Tee).ToList();
                    if (tees.Count == 0) { ed.WriteMessage("\nLa parts list no tiene Tee. Añádela al catálogo."); tr.Abort(); return; }
                    PresStyles.PressurePartSize teeSize = ElegirPiezaPresion(ed, tees, "Tee disponibles");
                    if (teeSize == null) { tr.Abort(); return; }

                    PresStyles.PressurePartSize appSize = null;
                    if (elem != "Ninguno")
                    {
                        CivilDB.PressurePartType tApp = (elem == "Valvula") ? CivilDB.PressurePartType.Valve : CivilDB.PressurePartType.Hydrant;
                        var apps = pl.GetParts(CivilDB.PressurePartDomainType.Appurtenance).Where(a => a.PartType == tApp).ToList();
                        if (apps.Count == 0) { ed.WriteMessage($"\nLa parts list no tiene {tApp}; el ramal quedará sin elemento al final."); }
                        else { appSize = ElegirPiezaPresion(ed, apps, $"{tApp} disponibles"); }
                    }

                    // Proyectar el punto del ramal sobre la principal (segmento recto)
                    CivilDB.PressurePipe main = (CivilDB.PressurePipe)tr.GetObject(per.ObjectId, OpenMode.ForWrite);
                    Point3d A = main.StartPoint, B = main.EndPoint;
                    Vector3d ab = B - A;
                    double t = ab.LengthSqrd > 1e-12 ? ((pCorte.Value - A).DotProduct(ab)) / ab.DotProduct(ab) : 0.0;
                    t = Math.Max(0.0, Math.Min(1.0, t));
                    Point3d ptCorte = A + ab * t;

                    // Anotar a qué estaban conectados los extremos de la principal (para avisar)
                    ObjectId origStart = ConexionEnPuerto(main, 0);
                    ObjectId origEnd = ConexionEnPuerto(main, 1);

                    // Partir la principal: crear dos mitades y borrar la original
                    ObjectId h1 = net.AddLinePipe(new LineSegment3d(A, ptCorte), tubo);   // A -> corte
                    ObjectId h2 = net.AddLinePipe(new LineSegment3d(ptCorte, B), tubo);   // corte -> B
                    main.Erase();

                    // Tee en el corte: puertos 0,1 = las dos mitades
                    ObjectId fid = net.AddFitting(ptCorte, teeSize);
                    CivilDB.PressurePart tee = (CivilDB.PressurePart)tr.GetObject(fid, OpenMode.ForWrite);
                    try { tee.ConnectToPipe(0, h1, 1); } catch (Exception ex) { ed.WriteMessage($"\n  ✗ mitad 1: {ex.Message}"); }
                    try { tee.ConnectToPipe(1, h2, 0); } catch (Exception ex) { ed.WriteMessage($"\n  ✗ mitad 2: {ex.Message}"); }

                    // Tubo de ramal: corte -> extremo; conectar al puerto 2 (ramal) de la Tee
                    ObjectId bp = net.AddLinePipe(new LineSegment3d(ptCorte, pFin.Value), tubo);
                    try { tee.ConnectToPipe(2, bp, 0); } catch (Exception ex) { ed.WriteMessage($"\n  ✗ ramal: {ex.Message}"); }

                    // Recortar mitades y ramal a los puertos de la Tee
                    try
                    {
                        for (int i = 0; i < tee.ConnectionCount; i++)
                        {
                            CivilDB.PressurePartConnection c = tee.GetConnectionAt(i);
                            if (c.ConnectedId == h1) { var p = tr.GetObject(h1, OpenMode.ForWrite) as CivilDB.PressurePipe; if (p != null) p.EndPoint = c.Position; }
                            else if (c.ConnectedId == h2) { var p = tr.GetObject(h2, OpenMode.ForWrite) as CivilDB.PressurePipe; if (p != null) p.StartPoint = c.Position; }
                            else if (c.ConnectedId == bp) { var p = tr.GetObject(bp, OpenMode.ForWrite) as CivilDB.PressurePipe; if (p != null) p.StartPoint = c.Position; }
                        }
                    }
                    catch { }

                    // Elemento al final del ramal
                    bool conElem = false;
                    if (appSize != null)
                    {
                        ObjectId aid = net.AddAppurtenance(pFin.Value, appSize);
                        CivilDB.PressurePart app = (CivilDB.PressurePart)tr.GetObject(aid, OpenMode.ForWrite);
                        try { app.ConnectToPipe(0, bp, 1); conElem = true; } catch (Exception ex) { ed.WriteMessage($"\n  ✗ elemento final: {ex.Message}"); }
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Ramal creado: Tee '{teeSize.Description}' en la principal + tubo de ramal" +
                                    (conElem ? $" + {elem}." : "."));
                    if (origStart != ObjectId.Null || origEnd != ObjectId.Null)
                        ed.WriteMessage("\n  ⚠ La principal se partió en dos: revisa/reconecta sus EXTREMOS a los vecinos" +
                                        " (la API no reconecta automáticamente los extremos exteriores tras partir).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_PERFIL_PRESION — crea el perfil (vista de perfil) del EJE de la red
        //   a presión, y opcionalmente el perfil del TERRENO desde una superficie.
        // =====================================================================
        [CommandMethod("CREAR_PERFIL_PRESION")]
        public void CrearPerfilPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión."); tr.Abort(); return; }
                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForRead);

                    // Buscar el EJE de la red (en los runs o en los tubos)
                    ObjectId alignId = ObjectId.Null;
                    for (int i = 0; i < net.PipeRuns.Count && alignId == ObjectId.Null; i++)
                        if (net.PipeRuns[i].AlignmentId.IsValid && !net.PipeRuns[i].AlignmentId.IsNull) alignId = net.PipeRuns[i].AlignmentId;
                    if (alignId == ObjectId.Null)
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            var pp = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (pp != null && pp.ReferenceAlignmentId.IsValid && !pp.ReferenceAlignmentId.IsNull) { alignId = pp.ReferenceAlignmentId; break; }
                        }
                    if (alignId == ObjectId.Null)
                    { ed.WriteMessage("\nEsta red no tiene EJE. Créala con polilínea/CogoPoints (ahora generan el eje) y reintenta."); tr.Abort(); return; }

                    ObjectId pStyle = civilDoc.Styles.ProfileStyles[0];
                    ObjectId pLabel = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

                    // Perfil de terreno opcional
                    PromptKeywordOptions pkT = new PromptKeywordOptions("\n¿Dibujar el perfil del TERRENO desde una superficie? [Si/No] <No>:", "Si No");
                    pkT.AllowNone = true;
                    PromptResult rT = ed.GetKeywords(pkT);
                    if (rT.Status == PromptStatus.OK && rT.StringResult == "Si")
                    {
                        PromptEntityOptions peoS = new PromptEntityOptions("\nSeleccione la Superficie (TIN):");
                        peoS.SetRejectMessage("\nDebe ser una superficie TIN.");
                        peoS.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                        PromptEntityResult perS = ed.GetEntity(peoS);
                        if (perS.Status == PromptStatus.OK)
                            try { CivilDB.Profile.CreateFromSurface("Terreno-Presion", alignId, perS.ObjectId, db.Clayer, pStyle, pLabel); }
                            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo crear el perfil de terreno: {ex.Message})"); }
                    }

                    // Vista de perfil
                    PromptPointResult pIns = ed.GetPoint("\nPunto de inserción de la vista de perfil:");
                    if (pIns.Status != PromptStatus.OK) { tr.Abort(); return; }
                    ObjectId pvId = CivilDB.ProfileView.Create(alignId, pIns.Value);

                    // Rango vertical: +5 sobre la cota máxima y -5 bajo la mínima (perfil no aplastado)
                    CivilDB.ProfileView pvW = tr.GetObject(pvId, OpenMode.ForWrite) as CivilDB.ProfileView;
                    bool rango = PerfilUtil.AjustarRango(pvW, alignId, tr);

                    tr.Commit();
                    ed.WriteMessage("\n✓ Vista de perfil creada para el eje de la red a presión." +
                                    (rango ? " Rango vertical ajustado (±5 m)." : ""));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // INVERTIR_ALINEAMIENTO — invierte la DIRECCIÓN (sentido de estaciones) de
        //   un alineamiento seleccionado (p. ej. el eje de la red a presión).
        // =====================================================================
        [CommandMethod("INVERTIR_ALINEAMIENTO")]
        public void InvertirAlineamiento()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el ALINEAMIENTO (eje) a invertir:");
            peo.SetRejectMessage("\nDebe ser un alineamiento (Alignment).");
            peo.AddAllowedClass(typeof(CivilDB.Alignment), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.Alignment al = (CivilDB.Alignment)tr.GetObject(per.ObjectId, OpenMode.ForWrite);
                    al.Reverse();
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Dirección del alineamiento '{al.Name}' invertida.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }
    }
}
