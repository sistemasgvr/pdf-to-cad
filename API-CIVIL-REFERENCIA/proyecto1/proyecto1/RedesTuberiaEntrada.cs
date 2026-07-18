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

            // Elegir el BUZÓN (estructura) y la TUBERÍA de la parts list (como en presión)
            if (!ElegirParteGravedad(ed, tr, partsList, CivilDB.DomainType.Structure, "Buzones (estructuras) disponibles", out ObjectId sFam, out ObjectId sSize, out string sNom))
            { ed.WriteMessage("\nNo se eligió buzón (o la Parts List no tiene estructuras)."); return false; }
            if (!ElegirParteGravedad(ed, tr, partsList, CivilDB.DomainType.Pipe, "Tuberías disponibles", out ObjectId pFam, out ObjectId pSize, out string pNom))
            { ed.WriteMessage("\nNo se eligió tubería (o la Parts List no tiene tuberías)."); return false; }
            ed.WriteMessage($"\nBuzón: '{sNom}' | tubería: '{pNom}'.");

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

            // Crear el EJE (alignment) a lo largo de la traza y asociarlo a la red
            var ptsEje = new List<Point3d>();
            foreach (var x in nodos) ptsEje.Add(x.pt);
            ObjectId alignId = CrearAlineamientoGravedad(ed, db, civilDoc, tr, ptsEje, nm + "-eje");
            if (alignId != ObjectId.Null)
            {
                try { net.ReferenceAlignmentId = alignId; } catch { }
                ed.WriteMessage($"\n  ✓ Alineamiento '{nm}-eje' creado y asociado a la red (útil para perfiles).");
            }

            ed.WriteMessage($"\n✓ Red '{nm}' creada: {structIds.Count} buzones y {nPipes} tuberías (conectadas).");
            return true;
        }

        // Selector de pieza de gravedad EN DOS PASOS: primero el MATERIAL/TIPO (familia),
        // luego el DIÁMETRO/TAMAÑO (size) dentro de esa familia. Así la lista no es enorme.
        private bool ElegirParteGravedad(Editor ed, Transaction tr, PartsStyles.PartsList pl, CivilDB.DomainType dom,
                                         string titulo, out ObjectId famId, out ObjectId sizeId, out string nombre)
        {
            famId = ObjectId.Null; sizeId = ObjectId.Null; nombre = "";

            // --- Paso 1: elegir la FAMILIA (material/tipo) ---
            var fIds = new List<ObjectId>(); var fNames = new List<string>();
            foreach (ObjectId fid in pl.GetPartFamilyIdsByDomain(dom))
            {
                PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                string desc = fam.Description ?? "";
                if (desc.IndexOf("Null", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                fIds.Add(fid); fNames.Add(desc);
            }
            if (fIds.Count == 0) { ed.WriteMessage($"\n(No hay piezas: {titulo}.)"); return false; }

            int fi = 0;
            if (fIds.Count > 1)
            {
                ed.WriteMessage($"\n{titulo} — material/tipo:");
                for (int i = 0; i < fNames.Count; i++) ed.WriteMessage($"\n  {i + 1}. {fNames[i]}");
                PromptIntegerOptions pioF = new PromptIntegerOptions("\nNúmero del material/tipo:")
                { LowerLimit = 1, UpperLimit = fNames.Count, DefaultValue = 1, UseDefaultValue = true };
                PromptIntegerResult rF = ed.GetInteger(pioF);
                if (rF.Status != PromptStatus.OK) return false;
                fi = rF.Value - 1;
            }
            famId = fIds[fi];

            // --- Paso 2: elegir el TAMAÑO/DIÁMETRO dentro de esa familia ---
            PartsStyles.PartFamily famSel = tr.GetObject(famId, OpenMode.ForRead) as PartsStyles.PartFamily;
            var sIds = new List<ObjectId>(); var sNames = new List<string>();
            for (int i = 0; i < famSel.PartSizeCount; i++)
            {
                ObjectId sid = famSel[i];
                PartsStyles.PartSize sz = tr.GetObject(sid, OpenMode.ForRead) as PartsStyles.PartSize;
                sIds.Add(sid); sNames.Add(sz != null ? sz.Name : "?");
            }
            int si = 0;
            if (sIds.Count > 1)
            {
                ed.WriteMessage($"\n{fNames[fi]} — diámetro/tamaño:");
                for (int i = 0; i < sNames.Count; i++) ed.WriteMessage($"\n  {i + 1}. {sNames[i]}");
                PromptIntegerOptions pioS = new PromptIntegerOptions("\nNúmero del diámetro/tamaño:")
                { LowerLimit = 1, UpperLimit = sNames.Count, DefaultValue = 1, UseDefaultValue = true };
                PromptIntegerResult rS = ed.GetInteger(pioS);
                if (rS.Status != PromptStatus.OK) return false;
                si = rS.Value - 1;
            }
            sizeId = sIds[si];
            nombre = $"{fNames[fi]} — {sNames[si]}";
            return true;
        }

        // Crea un alineamiento a lo largo de la planta (X-Y) de una lista de puntos (polilínea temporal -> Alignment).
        private ObjectId CrearAlineamientoGravedad(Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
                                                   List<Point3d> pts, string nombre)
        {
            try
            {
                if (pts == null || pts.Count < 2) return ObjectId.Null;
                BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                Polyline pl = new Polyline();
                for (int i = 0; i < pts.Count; i++) pl.AddVertexAt(i, new Point2d(pts[i].X, pts[i].Y), 0, 0, 0);
                ms.AppendEntity(pl);
                tr.AddNewlyCreatedDBObject(pl, true);
                ObjectId aStyle = civilDoc.Styles.AlignmentStyles[0];
                ObjectId aLabel = civilDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0];
                CivilDB.PolylineOptions plo = new CivilDB.PolylineOptions
                { PlineId = pl.ObjectId, AddCurvesBetweenTangents = false, EraseExistingEntities = true };
                return CivilDB.Alignment.Create(civilDoc, plo, nombre, ObjectId.Null, db.Clayer, aStyle, aLabel);
            }
            catch (Exception ex) { ed.WriteMessage($"\n  (No se pudo crear el alineamiento: {ex.Message})"); return ObjectId.Null; }
        }

        // =====================================================================
        // CREAR_PERFIL_RED — crea la vista de perfil del EJE de una red de gravedad
        //   (+ perfil de terreno opcional desde una superficie).
        // =====================================================================
        [CommandMethod("CREAR_PERFIL_RED")]
        public void CrearPerfilRed()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes de tubería."); tr.Abort(); return; }

                    // Elegir red (si hay más de una)
                    ObjectId netId = nets[0];
                    if (nets.Count > 1)
                    {
                        var nombres = new List<string>();
                        for (int i = 0; i < nets.Count; i++)
                        { var n = tr.GetObject(nets[i], OpenMode.ForRead) as CivilDB.Network; nombres.Add(n != null ? n.Name : $"(red {i + 1})"); }
                        ed.WriteMessage("\nRedes de tubería disponibles:");
                        for (int i = 0; i < nombres.Count; i++) ed.WriteMessage($"\n  {i + 1}. {nombres[i]}");
                        PromptIntegerOptions pio = new PromptIntegerOptions("\n¿Qué red? Número:")
                        { LowerLimit = 1, UpperLimit = nets.Count, DefaultValue = nets.Count, UseDefaultValue = true };
                        PromptIntegerResult pir = ed.GetInteger(pio);
                        if (pir.Status != PromptStatus.OK) { tr.Abort(); return; }
                        netId = nets[pir.Value - 1];
                    }

                    CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForRead);
                    ObjectId alignId = net.ReferenceAlignmentId;
                    if (!alignId.IsValid || alignId.IsNull)
                    { ed.WriteMessage("\nEsta red no tiene EJE asociado. Créala con POLILÍNEA/COGOPOINTS (ahora generan el eje) y reintenta."); tr.Abort(); return; }

                    ObjectId pStyle = civilDoc.Styles.ProfileStyles[0];
                    ObjectId pLabel = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

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
                            try { CivilDB.Profile.CreateFromSurface("Terreno-Red", alignId, perS.ObjectId, db.Clayer, pStyle, pLabel); }
                            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo crear el perfil de terreno: {ex.Message})"); }
                    }

                    PromptPointResult pIns = ed.GetPoint("\nPunto de inserción de la vista de perfil:");
                    if (pIns.Status != PromptStatus.OK) { tr.Abort(); return; }
                    ObjectId pvId = CivilDB.ProfileView.Create(alignId, pIns.Value);

                    // Rango vertical: +5 sobre la cota máxima y -5 bajo la mínima
                    CivilDB.ProfileView pvW = tr.GetObject(pvId, OpenMode.ForWrite) as CivilDB.ProfileView;
                    bool rango = PerfilUtil.AjustarRango(pvW, alignId, tr);

                    tr.Commit();
                    ed.WriteMessage("\n✓ Vista de perfil creada para el eje de la red de gravedad." +
                                    (rango ? " Rango vertical ajustado (±5 m)." : ""));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
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
