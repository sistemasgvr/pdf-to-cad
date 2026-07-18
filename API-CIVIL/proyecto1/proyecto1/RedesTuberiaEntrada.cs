using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  ENTRADAS de la red de GRAVEDAD análogas a las de presión:
//   · CREAR_RED_POLILINEA  → red desde una polilínea (2D o 3D): cada vértice = buzón, cada tramo = tubo.
//   · CREAR_RED_COGO       → red desde CogoPoints: cada punto = buzón.
//   · UNIR_TUBERIAS_RED    → une DOS tuberías colocando un BUZÓN en el encuentro (en gravedad los tubos NO se unen directo: van a una estructura).
//  Clase PARCIAL de ComandosRedes -> reutiliza los helpers privados (PrimeraPieza).
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        // =====================================================================
        // CREAR_RED_POLILINEA — cada VÉRTICE es un buzón (con su cota Z como fondo/
        //   invert) y cada TRAMO un tubo que conecta dos buzones. Acepta 2D y 3D.
        // =====================================================================
        [CommandMethod("CREAR_RED_POLILINEA")]
        public void CrearRedPolilinea()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la polilínea (2D o 3D):");
            peo.SetRejectMessage("\nDebe ser una polilínea 2D (LWPolyline) o 3D (Polyline3d).");
            peo.AddAllowedClass(typeof(Polyline), false);
            peo.AddAllowedClass(typeof(Polyline3d), false);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            string nombre = PedirNombre(ed, "\nNombre de la Pipe Network:");
            if (nombre == null) return;
            ObjectId surfId = PedirSuperficie(ed);
            double prof = PedirProfundidad(ed, surfId != ObjectId.Null);
            if (double.IsNaN(prof)) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var nodos = new List<(string name, Point3d pt)>();
                    Entity ent = tr.GetObject(per.ObjectId, OpenMode.ForRead) as Entity;

                    if (ent is Polyline3d p3d)
                    {
                        int k = 1;
                        foreach (ObjectId vId in p3d)
                        {
                            PolylineVertex3d v = tr.GetObject(vId, OpenMode.ForRead) as PolylineVertex3d;
                            if (v != null) nodos.Add(($"B{k++}", v.Position));
                        }
                    }
                    else if (ent is Polyline p2d)
                    {
                        ed.WriteMessage("\n(Aviso: es una polilínea 2D; todos los buzones quedarán a la misma cota (su elevación).)");
                        for (int i = 0; i < p2d.NumberOfVertices; i++)
                            nodos.Add(($"B{i + 1}", p2d.GetPoint3dAt(i)));
                    }

                    if (nodos.Count < 2) { ed.WriteMessage("\nSe necesitan al menos 2 vértices."); tr.Abort(); return; }

                    if (CrearRedEncadenada(ed, db, civilDoc, tr, nombre, surfId, prof, nodos))
                        tr.Commit();
                    else
                        tr.Abort();
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_RED_COGO — cada CogoPoint es un buzón (X/Y/Z = Este/Norte/Cota).
        //   Ordena por número (o descripción) y encadena los tubos.
        // =====================================================================
        [CommandMethod("CREAR_RED_COGO")]
        public void CrearRedCogo()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptKeywordOptions optSel = new PromptKeywordOptions("\n¿Usar todos los CogoPoints o seleccionar? [Seleccionar/UsarTodos] <Seleccionar>:");
            optSel.Keywords.Add("Seleccionar"); optSel.Keywords.Add("UsarTodos"); optSel.AllowNone = true;
            PromptResult optRes = ed.GetKeywords(optSel);
            if (optRes.Status != PromptStatus.OK && optRes.Status != PromptStatus.None) return;
            bool usarTodos = (optRes.Status == PromptStatus.OK && optRes.StringResult == "UsarTodos");

            ObjectId[] seleccion = null;
            if (!usarTodos)
            {
                PromptSelectionResult selRes = ed.GetSelection(new PromptSelectionOptions
                { MessageForAdding = "\nSeleccione CogoPoints (otras entidades se ignoran):" });
                if (selRes.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }
                seleccion = selRes.Value.GetObjectIds();
            }

            string nombre = PedirNombre(ed, "\nNombre de la Pipe Network:");
            if (nombre == null) return;
            ObjectId surfId = PedirSuperficie(ed);
            double prof = PedirProfundidad(ed, surfId != ObjectId.Null);
            if (double.IsNaN(prof)) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var setCogo = new HashSet<ObjectId>();
                    CivilDB.CogoPointCollection allCogo = civilDoc.CogoPoints;
                    foreach (ObjectId cid in allCogo) setCogo.Add(cid);

                    var puntos = new List<CivilDB.CogoPoint>();
                    if (usarTodos)
                        foreach (ObjectId cid in allCogo)
                        { var cp = tr.GetObject(cid, OpenMode.ForRead) as CivilDB.CogoPoint; if (cp != null) puntos.Add(cp); }
                    else
                        foreach (ObjectId soId in seleccion)
                        { if (!setCogo.Contains(soId)) continue; var cp = tr.GetObject(soId, OpenMode.ForRead) as CivilDB.CogoPoint; if (cp != null) puntos.Add(cp); }

                    if (puntos.Count < 2) { ed.WriteMessage("\nSe necesitan al menos 2 CogoPoints."); tr.Abort(); return; }

                    PromptKeywordOptions ordOpts = new PromptKeywordOptions("\nOrdenar por: [Numero/Descripcion] <Numero>:");
                    ordOpts.Keywords.Add("Numero"); ordOpts.Keywords.Add("Descripcion"); ordOpts.AllowNone = true;
                    PromptResult ordRes = ed.GetKeywords(ordOpts);
                    if (ordRes.Status == PromptStatus.OK && ordRes.StringResult == "Descripcion")
                        puntos.Sort((a, b) => string.Compare(a.RawDescription ?? "", b.RawDescription ?? "", StringComparison.OrdinalIgnoreCase));
                    else
                        puntos.Sort((a, b) => a.PointNumber.CompareTo(b.PointNumber));

                    var nodos = new List<(string name, Point3d pt)>();
                    foreach (var cp in puntos)
                        nodos.Add(($"P{cp.PointNumber}", new Point3d(cp.Easting, cp.Northing, cp.Elevation)));

                    if (CrearRedEncadenada(ed, db, civilDoc, tr, nombre, surfId, prof, nodos))
                        tr.Commit();
                    else
                        tr.Abort();
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // UNIR_TUBERIAS_RED — coloca un BUZÓN en el encuentro de dos tuberías y las
        //   conecta a él. (En gravedad los tubos NO se unen entre sí: van a una estructura.)
        // =====================================================================
        [CommandMethod("UNIR_TUBERIAS_RED")]
        public void UnirTuberiasRed()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptEntityOptions peo1 = new PromptEntityOptions("\nSeleccione la PRIMERA tubería:");
            peo1.SetRejectMessage("\nDebe ser una tubería (Pipe) de gravedad.");
            peo1.AddAllowedClass(typeof(CivilDB.Pipe), true);
            PromptEntityResult per1 = ed.GetEntity(peo1);
            if (per1.Status != PromptStatus.OK) return;

            PromptEntityOptions peo2 = new PromptEntityOptions("\nSeleccione la SEGUNDA tubería:");
            peo2.SetRejectMessage("\nDebe ser una tubería (Pipe) de gravedad.");
            peo2.AddAllowedClass(typeof(CivilDB.Pipe), true);
            PromptEntityResult per2 = ed.GetEntity(peo2);
            if (per2.Status != PromptStatus.OK) return;
            if (per1.ObjectId == per2.ObjectId) { ed.WriteMessage("\nDeben ser dos tuberías distintas."); return; }

            double prof = PedirProfundidad(ed, false);
            if (double.IsNaN(prof)) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Encontrar la red que contiene la 1ª tubería
                    CivilDB.Network net = null;
                    foreach (ObjectId nid in civilDoc.GetPipeNetworkIds())
                    {
                        CivilDB.Network n = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (n == null) continue;
                        foreach (ObjectId pid in n.GetPipeIds())
                            if (pid == per1.ObjectId) { net = (CivilDB.Network)tr.GetObject(nid, OpenMode.ForWrite); break; }
                        if (net != null) break;
                    }
                    if (net == null) { ed.WriteMessage("\nNo se halló la red de la 1ª tubería."); tr.Abort(); return; }

                    CivilDB.Pipe t1 = (CivilDB.Pipe)tr.GetObject(per1.ObjectId, OpenMode.ForWrite);
                    CivilDB.Pipe t2 = (CivilDB.Pipe)tr.GetObject(per2.ObjectId, OpenMode.ForWrite);

                    // Extremos más cercanos = punto de encuentro
                    Point3d[] e1 = { t1.StartPoint, t1.EndPoint };
                    Point3d[] e2 = { t2.StartPoint, t2.EndPoint };
                    int i1 = 0, i2 = 0; double best = double.MaxValue;
                    for (int i = 0; i < 2; i++)
                        for (int j = 0; j < 2; j++)
                        { double d = e1[i].DistanceTo(e2[j]); if (d < best) { best = d; i1 = i; i2 = j; } }
                    Point3d junta = new Point3d((e1[i1].X + e2[i2].X) / 2, (e1[i1].Y + e2[i2].Y) / 2, (e1[i1].Z + e2[i2].Z) / 2);
                    if (best > 1.0) ed.WriteMessage($"\n(Aviso: los extremos están a {best:F2} m; el buzón se coloca en el punto medio.)");

                    // Familia/tamaño de estructura de la parts list de ESTA red
                    PartsStyles.PartsList pl = (PartsStyles.PartsList)tr.GetObject(net.PartsListId, OpenMode.ForRead);
                    if (!PrimeraPieza(tr, pl, CivilDB.DomainType.Structure, out ObjectId sFam, out ObjectId sSize, out string sNom))
                    { ed.WriteMessage("\nLa Parts List no tiene familias de ESTRUCTURA."); tr.Abort(); return; }

                    // Colocar el buzón (rim = fondo + profundidad)
                    ObjectId sid = ObjectId.Null;
                    net.AddStructure(sFam, sSize, new Point3d(junta.X, junta.Y, junta.Z + prof), 0.0, ref sid, true);
                    CivilDB.Structure st = (CivilDB.Structure)tr.GetObject(sid, OpenMode.ForWrite);
                    st.SumpElevation = junta.Z;
                    st.RimElevation = junta.Z + prof;

                    // Conectar el extremo más cercano de cada tubo al buzón
                    t1.ConnectToStructure(i1 == 0 ? CivilDB.ConnectorPositionType.Start : CivilDB.ConnectorPositionType.End, sid, true);
                    t2.ConnectToStructure(i2 == 0 ? CivilDB.ConnectorPositionType.Start : CivilDB.ConnectorPositionType.End, sid, true);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Buzón '{st.Name}' colocado en el encuentro y ambas tuberías conectadas.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // ---------------------------------------------------------------------
        // Helper: construye una red ENCADENADA a partir de una lista de nodos
        // (nombre + punto con Z = FONDO/invert). Un buzón por nodo, un tubo por tramo.
        // ---------------------------------------------------------------------
        private bool CrearRedEncadenada(Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
                                        string nombre, ObjectId surfId, double prof, List<(string name, Point3d pt)> nodos)
        {
            PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
            if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists en el dibujo."); return false; }
            ObjectId partsListId = plSet[0];
            for (int i = 0; i < plSet.Count; i++)
            {
                PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase)) { partsListId = plSet[i]; break; }
            }
            PartsStyles.PartsList partsList = (PartsStyles.PartsList)tr.GetObject(partsListId, OpenMode.ForRead);

            if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Structure, out ObjectId sFam, out ObjectId sSize, out string sNom))
            { ed.WriteMessage("\nLa Parts List no tiene familias de ESTRUCTURA."); return false; }
            if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Pipe, out ObjectId pFam, out ObjectId pSize, out string pNom))
            { ed.WriteMessage("\nLa Parts List no tiene familias de TUBERÍA."); return false; }
            ed.WriteMessage($"\nUsando estructura: '{sNom}' | tubería: '{pNom}'.");

            string nm = nombre;
            ObjectId netId = CivilDB.Network.Create(civilDoc, ref nm);
            CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForWrite);
            net.PartsListId = partsListId;
            if (surfId != ObjectId.Null) net.ReferenceSurfaceId = surfId;

            var structIds = new List<ObjectId>();
            foreach (var n in nodos)
            {
                ObjectId sid = ObjectId.Null;
                net.AddStructure(sFam, sSize, new Point3d(n.pt.X, n.pt.Y, n.pt.Z + prof), 0.0, ref sid, true);
                CivilDB.Structure st = (CivilDB.Structure)tr.GetObject(sid, OpenMode.ForWrite);
                if (surfId != ObjectId.Null) st.AutomaticRimSurfaceAdjustment = true;
                else st.RimElevation = n.pt.Z + prof;
                st.SumpElevation = n.pt.Z;
                structIds.Add(sid);
            }

            int nPipes = 0;
            for (int i = 0; i < nodos.Count - 1; i++)
            {
                Point3d p1 = nodos[i].pt, p2 = nodos[i + 1].pt;
                if (p1.DistanceTo(p2) < 1e-6) continue;
                ObjectId pid = ObjectId.Null;
                net.AddLinePipe(pFam, pSize, new LineSegment3d(p1, p2), ref pid, true);
                CivilDB.Pipe pipe = (CivilDB.Pipe)tr.GetObject(pid, OpenMode.ForWrite);
                pipe.ConnectToStructure(CivilDB.ConnectorPositionType.Start, structIds[i], true);
                pipe.ConnectToStructure(CivilDB.ConnectorPositionType.End, structIds[i + 1], true);
                nPipes++;
            }

            ed.WriteMessage($"\n✓ Red '{nm}' creada: {structIds.Count} buzones y {nPipes} tuberías (conectadas).");
            return true;
        }

        // ---- Preguntas comunes ----
        private static string PedirNombre(Editor ed, string msg)
        {
            PromptStringOptions pso = new PromptStringOptions(msg) { AllowSpaces = true };
            PromptResult r = ed.GetString(pso);
            return (r.Status == PromptStatus.OK && !string.IsNullOrWhiteSpace(r.StringResult)) ? r.StringResult.Trim() : null;
        }

        private static ObjectId PedirSuperficie(Editor ed)
        {
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Superficie de referencia (tapas a ras)? [Si/No] <No>:", "Si No");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status == PromptStatus.OK && rk.StringResult == "Si")
            {
                PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la superficie (TIN):");
                peo.SetRejectMessage("\nDebe ser una superficie TIN.");
                peo.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                PromptEntityResult per = ed.GetEntity(peo);
                if (per.Status == PromptStatus.OK) return per.ObjectId;
            }
            return ObjectId.Null;
        }

        // Profundidad del buzón: rim = fondo(invert) + esta profundidad. Si hay superficie, la tapa va a ras (se ignora).
        private static double PedirProfundidad(Editor ed, bool haySuperficie)
        {
            PromptDoubleOptions pdo = new PromptDoubleOptions(
                haySuperficie ? "\nProfundidad del buzón (m) [la tapa irá a ras de la superficie]:" : "\nProfundidad del buzón (rim = fondo + esta profundidad, m):")
            { AllowNegative = false, DefaultValue = 1.5, UseDefaultValue = true };
            PromptDoubleResult r = ed.GetDouble(pdo);
            return r.Status == PromptStatus.OK ? r.Value : double.NaN;
        }
    }
}
