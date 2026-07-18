using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;   // Property Sets
using Exception = System.Exception;

// ============================================================================
//  HERRAMIENTAS de CORREDOR simplificadas:
//   · CREAR_CORREDOR_FACIL  → crea el corredor y, al final, detecta los TARGETS
//                             del assembly y te deja asignarlos (superficie/offset...).
//   · ASIGNAR_TARGETS_CORREDOR → hace lo mismo sobre un corredor que YA existe.
//  Archivo separado para no tocar Corredores.cs.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosCorredorHerramientas
    {
        // =====================================================================
        // CREAR_CORREDOR_FACIL — eje + perfil + assembly + nombre + frecuencia,
        //   y al terminar te pregunta y ASIGNA los targets del assembly.
        // =====================================================================
        [CommandMethod("CREAR_CORREDOR_FACIL")]
        public void CrearCorredorFacil()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            ObjectId alignId = PedirUno(ed, "Seleccione el EJE (alignment):", false, typeof(CivilDB.Alignment));
            if (alignId == ObjectId.Null) return;
            ObjectId profId = PedirUno(ed, "Seleccione el PERFIL (rasante) de ese eje:", false, typeof(CivilDB.Profile));
            if (profId == ObjectId.Null) return;
            ObjectId asmId = PedirUno(ed, "Seleccione el ASSEMBLY (sección tipo):", false, typeof(CivilDB.Assembly));
            if (asmId == ObjectId.Null) return;

            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            PromptDoubleOptions pfo = new PromptDoubleOptions("\nFrecuencia (intervalo entre secciones, m):")
            { AllowNegative = false, AllowZero = false, DefaultValue = 5.0, UseDefaultValue = true };
            PromptDoubleResult pfr = ed.GetDouble(pfo);
            if (pfr.Status != PromptStatus.OK) return;
            double freq = pfr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectId corridorId = civilDoc.CorridorCollection.Add(nombre, "BL-1", alignId, profId, "R-1", asmId);
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(corridorId, OpenMode.ForWrite);
                    ConfigurarFrecuencia(corridor.Baselines[0].BaselineRegions[0], freq);

                    // Detectar y asignar targets del assembly (superficie / offset / elevación)
                    PromptKeywordOptions pkT = new PromptKeywordOptions("\n¿Asignar ahora los objetivos (targets) del assembly? [Si/No] <Si>:", "Si No");
                    pkT.AllowNone = true;
                    PromptResult rkT = ed.GetKeywords(pkT);
                    if (!(rkT.Status == PromptStatus.OK && rkT.StringResult == "No"))
                        AsignarTargets(ed, corridor);

                    corridor.Rebuild();
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Corredor '{nombre}' creado (frecuencia {freq:F1} m).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n(Comprueba que el Profile pertenezca al Alignment seleccionado.)");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // ASIGNAR_TARGETS_CORREDOR — sobre un corredor existente: lista los targets
        //   que pide el assembly y te deja asignar el objeto a cada uno.
        // =====================================================================
        [CommandMethod("ASIGNAR_TARGETS_CORREDOR")]
        public void AsignarTargetsCorredor()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el CORREDOR:");
            peo.SetRejectMessage("\nDebe ser un corredor.");
            peo.AddAllowedClass(typeof(CivilDB.Corridor), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(per.ObjectId, OpenMode.ForWrite);
                    bool algo = AsignarTargets(ed, corridor);
                    if (algo) corridor.Rebuild();
                    tr.Commit();
                    ed.WriteMessage(algo ? "\n✓ Targets asignados y corredor reconstruido." : "\n(No se asignó ningún target.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // ---------- Núcleo: recorre los targets y deja asignar cada uno ----------
        private bool AsignarTargets(Editor ed, CivilDB.Corridor corridor)
        {
            CivilDB.SubassemblyTargetInfoCollection targets = corridor.GetTargets();
            if (targets == null || targets.Count == 0)
            {
                ed.WriteMessage("\nEste assembly no pide objetivos (targets): no hay nada que asignar.");
                return false;
            }

            ed.WriteMessage($"\nEl assembly expone {targets.Count} objetivo(s). En cada uno: selecciona un objeto o Enter para SALTAR.");
            int asignados = 0;
            for (int i = 0; i < targets.Count; i++)
            {
                CivilDB.SubassemblyTargetInfo ti = targets[i];
                ed.WriteMessage($"\n\n▸ Objetivo '{ti.DisplayName}'  [{ti.TargetType}]  (subassembly: {ti.SubassemblyName})");

                ObjectId sel = ObjectId.Null;
                switch (ti.TargetType)
                {
                    case CivilDB.SubassemblyLogicalNameType.Surface:
                        sel = PedirUno(ed, "  → SUPERFICIE para este objetivo (Enter = saltar):", true, typeof(CivilDB.TinSurface));
                        break;

                    case CivilDB.SubassemblyLogicalNameType.Offset:
                    case CivilDB.SubassemblyLogicalNameType.OffsetPipe:
                        sel = PedirUno(ed, "  → EJE / polilínea / feature line para el offset (Enter = saltar):", true,
                                       typeof(CivilDB.Alignment), typeof(CivilDB.FeatureLine), typeof(Polyline), typeof(Polyline3d));
                        break;

                    case CivilDB.SubassemblyLogicalNameType.Elevation:
                    case CivilDB.SubassemblyLogicalNameType.ElevationPipe:
                    case CivilDB.SubassemblyLogicalNameType.Profile:
                        sel = PedirUno(ed, "  → PERFIL / feature line para la elevación (Enter = saltar):", true,
                                       typeof(CivilDB.Profile), typeof(CivilDB.FeatureLine));
                        break;

                    case CivilDB.SubassemblyLogicalNameType.Alignment:
                        sel = PedirUno(ed, "  → EJE (alignment) (Enter = saltar):", true, typeof(CivilDB.Alignment));
                        break;

                    default:
                        ed.WriteMessage("\n  (Tipo no soportado por el asistente; saltado.)");
                        break;
                }

                if (sel != ObjectId.Null)
                {
                    ObjectIdCollection oc = new ObjectIdCollection();
                    oc.Add(sel);
                    ti.TargetIds = oc;
                    asignados++;
                    ed.WriteMessage("\n  ✓ Asignado.");
                }
                else ed.WriteMessage("\n  (saltado)");
            }

            corridor.SetTargets(targets);
            ed.WriteMessage($"\n\n{asignados} de {targets.Count} objetivo(s) asignado(s).");
            return asignados > 0;
        }

        // =====================================================================
        // CORREDOR — crea el corredor DIRECTO desde una polilínea (2D o 3D):
        //   crea el EJE automático, crea el PERFIL (3D: por cotas de vértices;
        //   2D: desde una superficie), pide el ASSEMBLY y arma el corredor.
        // =====================================================================
        [CommandMethod("CORREDOR")]
        public void Corredor()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la polilínea del trazado (2D o 3D):");
            peo.SetRejectMessage("\nDebe ser una polilínea 2D (LWPolyline) o 3D (Polyline3d).");
            peo.AddAllowedClass(typeof(Polyline), false);
            peo.AddAllowedClass(typeof(Polyline3d), false);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor:") { AllowSpaces = true };
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // Paso 1: eje + perfil (transacción propia; el corredor los usa ya confirmados)
            ObjectId alignId = ObjectId.Null, profId = ObjectId.Null;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    Entity ent = tr.GetObject(per.ObjectId, OpenMode.ForRead) as Entity;
                    var pts = new List<Point3d>();
                    bool tieneZ = false;
                    if (ent is Polyline3d p3d)
                    {
                        foreach (ObjectId vId in p3d)
                        { var v = tr.GetObject(vId, OpenMode.ForRead) as PolylineVertex3d; if (v != null) pts.Add(v.Position); }
                        tieneZ = true;
                    }
                    else if (ent is Polyline p2d)
                    {
                        for (int i = 0; i < p2d.NumberOfVertices; i++) pts.Add(p2d.GetPoint3dAt(i));
                    }
                    else { ed.WriteMessage("\nEntidad no válida."); tr.Abort(); return; }
                    if (pts.Count < 2) { ed.WriteMessage("\nLa polilínea no tiene suficientes vértices."); tr.Abort(); return; }

                    alignId = CrearAlineamientoCorredor(ed, db, civilDoc, tr, pts, nombre + "-eje");
                    if (alignId == ObjectId.Null) { ed.WriteMessage("\nNo se pudo crear el eje."); tr.Abort(); return; }

                    // Perfil automático desde las cotas (3D = cotas reales; 2D = plano a su elevación).
                    // NO se pide superficie aquí: solo se pedirá al asignar un target de superficie.
                    profId = CrearPerfilPorCotas(ed, db, civilDoc, tr, alignId, pts, nombre + "-rasante");
                    if (!tieneZ)
                        ed.WriteMessage("\n(Polilínea 2D: rasante PLANA a su elevación. Ajusta el perfil luego o usa un target de superficie.)");
                    if (profId == ObjectId.Null) { ed.WriteMessage("\nNo se pudo crear el perfil."); tr.Abort(); return; }

                    tr.Commit();
                }
                catch (Exception ex) { ed.WriteMessage($"\nError creando eje/perfil: {ex.Message}"); tr.Abort(); return; }
            }

            ArmarCorredor(ed, db, civilDoc, nombre, alignId, profId);
        }

        // =====================================================================
        // CORREDOR_COGO — igual que CORREDOR pero el trazado sale de CogoPoints
        //   (cada punto aporta X/Y y su cota para el perfil).
        // =====================================================================
        [CommandMethod("CORREDOR_COGO")]
        public void CorredorCogo()
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
                { MessageForAdding = "\nSeleccione CogoPoints:" });
                if (selRes.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }
                seleccion = selRes.Value.GetObjectIds();
            }

            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor:") { AllowSpaces = true };
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            ObjectId alignId = ObjectId.Null, profId = ObjectId.Null;
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
                    puntos.Sort((a, b) => a.PointNumber.CompareTo(b.PointNumber));

                    var pts = new List<Point3d>();
                    foreach (var cp in puntos) pts.Add(new Point3d(cp.Easting, cp.Northing, cp.Elevation));

                    alignId = CrearAlineamientoCorredor(ed, db, civilDoc, tr, pts, nombre + "-eje");
                    if (alignId == ObjectId.Null) { ed.WriteMessage("\nNo se pudo crear el eje."); tr.Abort(); return; }
                    profId = CrearPerfilPorCotas(ed, db, civilDoc, tr, alignId, pts, nombre + "-rasante");
                    if (profId == ObjectId.Null) { ed.WriteMessage("\nNo se pudo crear el perfil."); tr.Abort(); return; }

                    tr.Commit();
                }
                catch (Exception ex) { ed.WriteMessage($"\nError creando eje/perfil: {ex.Message}"); tr.Abort(); return; }
            }

            ArmarCorredor(ed, db, civilDoc, nombre, alignId, profId);
        }

        // Pide el assembly + frecuencia y arma el corredor con el eje y perfil dados; ofrece targets.
        private void ArmarCorredor(Editor ed, Database db, CivilDocument civilDoc, string nombre, ObjectId alignId, ObjectId profId)
        {
            ObjectId asmId = PedirUno(ed, "Seleccione el ASSEMBLY (sección tipo):", false, typeof(CivilDB.Assembly));
            if (asmId == ObjectId.Null) { ed.WriteMessage("\nSin assembly no se puede armar el corredor."); return; }

            PromptDoubleOptions pfo = new PromptDoubleOptions("\nFrecuencia (intervalo entre secciones, m):")
            { AllowNegative = false, AllowZero = false, DefaultValue = 5.0, UseDefaultValue = true };
            PromptDoubleResult pfr = ed.GetDouble(pfo);
            if (pfr.Status != PromptStatus.OK) return;
            double freq = pfr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectId corridorId = civilDoc.CorridorCollection.Add(nombre, "BL-1", alignId, profId, "R-1", asmId);
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(corridorId, OpenMode.ForWrite);
                    ConfigurarFrecuencia(corridor.Baselines[0].BaselineRegions[0], freq);

                    PromptKeywordOptions pkT = new PromptKeywordOptions("\n¿Asignar ahora los objetivos (targets) del assembly? [Si/No] <Si>:", "Si No");
                    pkT.AllowNone = true;
                    PromptResult rkT = ed.GetKeywords(pkT);
                    if (!(rkT.Status == PromptStatus.OK && rkT.StringResult == "No")) AsignarTargets(ed, corridor);

                    corridor.Rebuild();
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Corredor '{nombre}' creado (eje + perfil automáticos, frecuencia {freq:F1} m).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError armando el corredor: {ex.Message}");
                    ed.WriteMessage("\n(Verifica que el assembly sea válido y que el perfil pertenezca al eje.)");
                    tr.Abort();
                }
            }
        }

        // Crea el EJE a lo largo de la planta (X-Y) de una lista de puntos (polilínea temporal -> Alignment).
        private ObjectId CrearAlineamientoCorredor(Editor ed, Database db, CivilDocument civilDoc, Transaction tr, List<Point3d> pts, string nombre)
        {
            try
            {
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
            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo crear el eje: {ex.Message})"); return ObjectId.Null; }
        }

        // Crea una RASANTE (perfil) con un PVI por vértice: estación = distancia 2D acumulada, cota = Z del punto.
        private ObjectId CrearPerfilPorCotas(Editor ed, Database db, CivilDocument civilDoc, Transaction tr, ObjectId alignId, List<Point3d> pts, string nombre)
        {
            try
            {
                ObjectId pStyle = civilDoc.Styles.ProfileStyles[0];
                ObjectId pLabel = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];
                ObjectId profId = CivilDB.Profile.CreateByLayout(nombre, alignId, db.Clayer, pStyle, pLabel);
                CivilDB.Profile profile = (CivilDB.Profile)tr.GetObject(profId, OpenMode.ForWrite);
                double sta = 0;
                profile.PVIs.AddPVI(0, pts[0].Z);
                for (int i = 1; i < pts.Count; i++)
                {
                    double dx = pts[i].X - pts[i - 1].X, dy = pts[i].Y - pts[i - 1].Y;
                    sta += Math.Sqrt(dx * dx + dy * dy);
                    profile.PVIs.AddPVI(sta, pts[i].Z);
                }
                return profId;
            }
            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo crear la rasante: {ex.Message})"); return ObjectId.Null; }
        }

        // Pide UNA entidad de los tipos permitidos. allowNone=true permite Enter para saltar.
        private ObjectId PedirUno(Editor ed, string msg, bool allowNone, params Type[] clases)
        {
            PromptEntityOptions peo = new PromptEntityOptions("\n" + msg);
            peo.AllowNone = allowNone;
            peo.SetRejectMessage("\n  (Tipo no válido; intenta con otro objeto.)");   // DEBE ir antes de AddAllowedClass
            foreach (Type c in clases) peo.AddAllowedClass(c, false);
            PromptEntityResult per = ed.GetEntity(peo);
            return per.Status == PromptStatus.OK ? per.ObjectId : ObjectId.Null;
        }

        // =====================================================================
        // EXPORTAR_SOLIDOS_CSV — exporta a un CSV (Excel) la RELACIÓN de sólidos 3D
        //   seleccionados: capa, volumen, área, centroide y caja envolvente.
        //   Sirve para los sólidos de corredores, redes a presión o gravedad.
        // =====================================================================
        [CommandMethod("EXPORTAR_SOLIDOS_CSV")]
        public void ExportarSolidosCsv()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            // Seleccionar SÓLIDOS 3D (filtro a 3DSOLID)
            TypedValue[] filtro = { new TypedValue((int)DxfCode.Start, "3DSOLID") };
            PromptSelectionResult sel = ed.GetSelection(
                new PromptSelectionOptions { MessageForAdding = "\nSeleccione los sólidos 3D a exportar:" },
                new SelectionFilter(filtro));
            if (sel.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }
            ObjectId[] ids = sel.Value.GetObjectIds();

            PromptSaveFileOptions opt = new PromptSaveFileOptions("\nGuardar la relación de sólidos como CSV (Excel):");
            opt.Filter = "CSV para Excel (*.csv)|*.csv";
            opt.InitialFileName = "solidos";
            PromptFileNameResult rF = ed.GetFileNameForSave(opt);
            if (rF.Status != PromptStatus.OK) return;
            string ruta = rF.StringResult;
            if (!ruta.ToLowerInvariant().EndsWith(".csv")) ruta += ".csv";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CultureInfo ci = CultureInfo.CurrentCulture;
                    Func<double, string> N = v => v.ToString("0.###", ci);
                    Func<string, string> T = s => "\"" + (s ?? "").Replace("\"", "\"\"") + "\"";

                    // Columnas base (geometría)
                    var baseCols = new List<string> { "N", "Handle", "Capa", "Volumen", "Area", "Cx", "Cy", "Cz", "Xmin", "Ymin", "Zmin", "Xmax", "Ymax", "Zmax", "Largo", "Ancho", "Alto" };

                    // Paso 1: recolectar datos por sólido + descubrir todas las columnas de Property Set
                    var filas = new List<Dictionary<string, string>>();
                    var colProps = new List<string>();
                    var colSet = new HashSet<string>();
                    int i = 1; double volTotal = 0;
                    foreach (ObjectId id in ids)
                    {
                        Solid3d sol = tr.GetObject(id, OpenMode.ForRead) as Solid3d;
                        if (sol == null) continue;

                        double vol = 0, area = 0; Point3d c = Point3d.Origin;
                        try { Solid3dMassProperties mp = sol.MassProperties; vol = mp.Volume; c = mp.Centroid; } catch { }
                        try { area = sol.Area; } catch { }
                        Point3d mn = Point3d.Origin, mx = Point3d.Origin; double lx = 0, ly = 0, lz = 0;
                        try { Extents3d ext = sol.GeometricExtents; mn = ext.MinPoint; mx = ext.MaxPoint; lx = mx.X - mn.X; ly = mx.Y - mn.Y; lz = mx.Z - mn.Z; } catch { }

                        var fila = new Dictionary<string, string>
                        {
                            ["N"] = i.ToString(ci), ["Handle"] = sol.Handle.ToString(), ["Capa"] = sol.Layer,
                            ["Volumen"] = N(vol), ["Area"] = N(area), ["Cx"] = N(c.X), ["Cy"] = N(c.Y), ["Cz"] = N(c.Z),
                            ["Xmin"] = N(mn.X), ["Ymin"] = N(mn.Y), ["Zmin"] = N(mn.Z),
                            ["Xmax"] = N(mx.X), ["Ymax"] = N(mx.Y), ["Zmax"] = N(mx.Z),
                            ["Largo"] = N(lx), ["Ancho"] = N(ly), ["Alto"] = N(lz)
                        };

                        // Datos de los Property Sets adjuntos al sólido
                        try
                        {
                            ObjectIdCollection psets = AecPS.PropertyDataServices.GetPropertySets(sol);
                            if (psets != null)
                                foreach (ObjectId psId in psets)
                                {
                                    AecPS.PropertySet ps = tr.GetObject(psId, OpenMode.ForRead) as AecPS.PropertySet;
                                    if (ps == null) continue;
                                    string psName = ps.PropertySetDefinitionName;
                                    AecPS.PropertySetDataCollection datos = ps.PropertySetData;
                                    for (int k = 0; k < datos.Count; k++)
                                    {
                                        AecPS.PropertySetData d = datos[k];
                                        string pn = ps.PropertyIdToName(d.Id);
                                        string key = $"{psName}.{pn}";
                                        object val = null;
                                        try { val = d.GetData(); } catch { }
                                        fila[key] = val?.ToString() ?? "";
                                        if (colSet.Add(key)) colProps.Add(key);
                                    }
                                }
                        }
                        catch { }

                        filas.Add(fila);
                        volTotal += vol; i++;
                    }

                    // Paso 2: escribir con las columnas base + todas las de Property Set descubiertas
                    var todasCols = new List<string>(baseCols); todasCols.AddRange(colProps);
                    var sb = new StringBuilder();
                    sb.AppendLine("sep=;");
                    sb.AppendLine("SOLIDOS 3D");
                    sb.AppendLine(string.Join(";", todasCols.ConvertAll(x => T(x))));
                    foreach (var fila in filas)
                    {
                        var celdas = new List<string>();
                        foreach (string col in todasCols)
                            celdas.Add(fila.TryGetValue(col, out string v) ? T(v) : "");
                        sb.AppendLine(string.Join(";", celdas));
                    }
                    sb.AppendLine();
                    sb.AppendLine($"TOTAL;;;{N(volTotal)}");

                    File.WriteAllText(ruta, sb.ToString(), new UTF8Encoding(true));
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Relación de {filas.Count} sólido(s) exportada a:\n  {ruta}" +
                                    (colProps.Count > 0 ? $"\n  Incluye {colProps.Count} columna(s) de Property Set." : "\n  (Los sólidos no tenían Property Sets adjuntos.)") +
                                    $"\n  Volumen total: {N(volTotal)}. (Ábrelo con doble clic en Excel.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // Frecuencia para que el corredor siga bien el eje (igual que en Corredores.cs).
        private void ConfigurarFrecuencia(CivilDB.BaselineRegion region, double freq)
        {
            CivilDB.AppliedAssemblySetting fs = region.AppliedAssemblySetting;
            fs.FrequencyAlongTangents = freq;
            fs.FrequencyAlongCurves = freq;
            fs.FrequencyAlongSpirals = freq;
            fs.FrequencyAlongProfileCurves = freq;
            fs.AppliedAtHorizontalGeometryPoints = true;
            fs.AppliedAtProfileGeometryPoints = true;
            fs.AppliedAtProfileHighLowPoints = true;
        }
    }
}
