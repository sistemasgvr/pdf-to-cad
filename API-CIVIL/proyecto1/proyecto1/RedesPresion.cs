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
using CivilDB = Autodesk.Civil.DatabaseServices;              // Pressure* viven aquí (en el ensamblado AeccPressurePipesMgd)
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;    // PressurePartList, colecciones, extensión de estilos
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;     // Property Sets (AecPropDataMgd)
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA — Redes a PRESIÓN (Pressure Network)  [ver README y memoria]
//  ARCHIVO SEPARADO de la red de gravedad (RedesTuberia.cs) para no mezclar.
//  Necesita la referencia a AeccPressurePipesMgd.dll (ya añadida en el .csproj).
//
//  Anatomía:  PressurePipeNetwork  →  Pipes (rectos/curvos)  +  Fittings (codos/tees/reductores)  +  Appurtenances (válvulas)
//  Catálogo:  "Pressure Part List" (aparte del de gravedad). Cada pieza = objeto PressurePartSize.
//
//  API clave (2026):
//    - PressurePipeNetwork.Create(db, nombre) -> ObjectId
//    - civilDoc.Styles.GetPressurePartLists()  (método de extensión) -> PressurePartListCollection
//    - PressurePartList.GetParts(PressurePartDomainType Pipe/Fitting/Appurtenance) -> List<PressurePartSize>
//    - PressurePartSize: .Description, .PartType, .Domain, .GetProperty(PressurePartContextType)
//
//  FASE 1 (este archivo): CREAR_RED_PRESION + LISTAR_PIEZAS_PRESION.
//  (Fase 2: agregar tubo/fitting/válvula; Fase 3: crear la red desde una polilínea.)
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Comandos de redes a presión (Pressure Network). Separado de la red de gravedad.
    /// </summary>
    public partial class ComandosPresion
    {
        // =====================================================================
        // CREAR_RED_PRESION — crea una red a presión vacía y le asigna la
        //   Parts List de presión (+ superficie de referencia opcional).
        // =====================================================================
        [CommandMethod("CREAR_RED_PRESION")]
        public void CrearRedPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Nombre de la red
            PromptStringOptions pso = new PromptStringOptions("\nNombre de la red a presión:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // Superficie de referencia opcional (para cotas/profundidad)
            ObjectId surfId = ObjectId.Null;
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Superficie de referencia? [Si/No] <No>:", "Si No");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status == PromptStatus.OK && rk.StringResult == "Si")
            {
                PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la superficie (TIN):");
                peo.SetRejectMessage("\nDebe ser una superficie TIN.");
                peo.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                PromptEntityResult per = ed.GetEntity(peo);
                if (per.Status == PromptStatus.OK) surfId = per.ObjectId;
            }

            // ----- Paso 1: crear la red + parts list (transacción propia) -----
            ObjectId netId = ObjectId.Null;
            string plName = "";
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Elegir la Parts List de presión entre las DISPONIBLES
                    PresStyles.PressurePartListCollection plc =
                        PresStyles.StylesRootPressurePipesExtension.GetPressurePartLists(civilDoc.Styles);
                    ObjectId partsListId;
                    if (plc.Count == 0)
                    {
                        partsListId = plc.Add("Standard");
                        plName = "Standard";
                        ed.WriteMessage("\nNo había Parts Lists de presión; creé una llamada 'Standard'.");
                    }
                    else
                    {
                        var nombres = new List<string>();
                        var ids = new List<ObjectId>();
                        for (int i = 0; i < plc.Count; i++)
                        {
                            PresStyles.PressurePartList p = tr.GetObject(plc[i], OpenMode.ForRead) as PresStyles.PressurePartList;
                            nombres.Add(p.Name);
                            ids.Add(plc[i]);
                        }
                        // Lista NUMERADA -> se elige por número (más claro que teclear el nombre)
                        ed.WriteMessage("\nParts Lists de presión disponibles:");
                        for (int i = 0; i < nombres.Count; i++) ed.WriteMessage($"\n  {i + 1}. {nombres[i]}");
                        PromptIntegerOptions pio = new PromptIntegerOptions("\nNúmero de la Parts List a usar:")
                        { LowerLimit = 1, UpperLimit = nombres.Count, DefaultValue = 1, UseDefaultValue = true };
                        PromptIntegerResult pir = ed.GetInteger(pio);
                        if (pir.Status != PromptStatus.OK) { tr.Abort(); return; }
                        partsListId = ids[pir.Value - 1];
                        plName = nombres[pir.Value - 1];
                    }

                    // Crear la red a presión
                    netId = CivilDB.PressurePipeNetwork.Create(db, nombre);
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netId, OpenMode.ForWrite);
                    net.PartsListId = partsListId;

                    tr.Commit();
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError creando la red: {ex.Message}");
                    tr.Abort();
                    return;
                }
            }

            // ----- Paso 2: asignar la superficie de referencia EN SU PROPIA transacción -----
            // (La red a presión es un "objeto de referencia": asignar la superficie en la misma
            //  transacción de creación provoca un fallo. Aislado y ya confirmada la red, es seguro.)
            bool supOk = false;
            if (surfId != ObjectId.Null)
            {
                try
                {
                    using (Transaction tr2 = db.TransactionManager.StartTransaction())
                    {
                        CivilDB.PressurePipeNetwork net2 = (CivilDB.PressurePipeNetwork)tr2.GetObject(netId, OpenMode.ForWrite);
                        net2.ReferenceSurfaceId = surfId;
                        tr2.Commit();
                    }
                    supOk = true;
                }
                catch (Exception exS)
                {
                    ed.WriteMessage($"\n(No se pudo asignar la superficie de referencia: {exS.Message}. La red se creó SIN ella.)");
                }
            }

            ed.WriteMessage($"\n✓ Red a presión '{nombre}' creada. Parts List: '{plName}'." +
                            (supOk ? " Superficie de referencia asignada." : ""));
            ed.WriteMessage("\n  Usa LISTAR_PIEZAS_PRESION para ver tubos/fittings/válvulas disponibles.");
        }

        // =====================================================================
        // LISTAR_PIEZAS_PRESION — lista las piezas de la Parts List de presión,
        //   agrupadas por dominio (tubos / fittings / válvulas), con su tipo y
        //   diámetro nominal. Valida cómo se obtiene un PressurePartSize.
        // =====================================================================
        [CommandMethod("LISTAR_PIEZAS_PRESION")]
        public void ListarPiezasPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    PresStyles.PressurePartListCollection col =
                        PresStyles.StylesRootPressurePipesExtension.GetPressurePartLists(civilDoc.Styles);
                    if (col.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists de presión. Crea la red con CREAR_RED_PRESION."); tr.Abort(); return; }

                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(col[0], OpenMode.ForRead);
                    ed.WriteMessage("\n=== Piezas de la Parts List de presión ===");

                    var dominios = new[]
                    {
                        CivilDB.PressurePartDomainType.Pipe,
                        CivilDB.PressurePartDomainType.Fitting,
                        CivilDB.PressurePartDomainType.Appurtenance
                    };
                    foreach (var dom in dominios)
                    {
                        ed.WriteMessage($"\n--- {dom} ---");
                        var partes = pl.GetParts(dom);   // List<PressurePartSize>
                        if (partes == null || partes.Count == 0) { ed.WriteMessage("\n  (ninguna)"); continue; }

                        foreach (var ps in partes)
                        {
                            string dia = "";
                            try { object v = ps.GetProperty(CivilDB.PressurePartContextType.DiameterNominal); dia = v?.ToString(); }
                            catch { }
                            ed.WriteMessage($"\n  [{ps.PartType}] {ps.Description}" + (string.IsNullOrEmpty(dia) ? "" : $"  Ø{dia}"));
                        }
                    }
                    ed.WriteMessage("\n==========================================");
                    tr.Commit();
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // AGREGAR_TUBO_PRESION — coloca UN tubo a presión entre 2 puntos, eligiendo
        //   material+diámetro del catálogo. Sirve para validar la mecánica base
        //   (resolver PressurePartSize + AddLinePipe) antes de automatizar todo.
        // =====================================================================
        [CommandMethod("AGREGAR_TUBO_PRESION")]
        public void AgregarTuboPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Tomar la primera red a presión del dibujo
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();   // método de extensión (AeccPressurePipesMgd)
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión. Crea una con CREAR_RED_PRESION."); tr.Abort(); return; }

                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);
                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

                    // Elegir el TUBO de la lista de disponibles
                    PresStyles.PressurePartSize tubo = ElegirPiezaPresion(ed, pl.GetParts(CivilDB.PressurePartDomainType.Pipe), "Tubos disponibles");
                    if (tubo == null) { ed.WriteMessage("\nNo se eligió tubo (o no hay tubos en la parts list)."); tr.Abort(); return; }

                    // Punto y COTA (elevación) del inicio y del fin
                    PromptPointResult pr1 = ed.GetPoint("\nPunto inicial del tubo:");
                    if (pr1.Status != PromptStatus.OK) { tr.Abort(); return; }
                    PromptDoubleResult c1 = ed.GetDouble(new PromptDoubleOptions("\nCota (elevación) del inicio:") { AllowNegative = true, DefaultValue = pr1.Value.Z, UseDefaultValue = true });
                    if (c1.Status != PromptStatus.OK) { tr.Abort(); return; }

                    PromptPointResult pr2 = ed.GetPoint("\nPunto final del tubo:");
                    if (pr2.Status != PromptStatus.OK) { tr.Abort(); return; }
                    PromptDoubleResult c2 = ed.GetDouble(new PromptDoubleOptions("\nCota (elevación) del fin:") { AllowNegative = true, DefaultValue = pr2.Value.Z, UseDefaultValue = true });
                    if (c2.Status != PromptStatus.OK) { tr.Abort(); return; }

                    string capa = PreguntarCapa(ed);
                    Point3d p1 = new Point3d(pr1.Value.X, pr1.Value.Y, c1.Value);
                    Point3d p2 = new Point3d(pr2.Value.X, pr2.Value.Y, c2.Value);
                    ObjectId tuboId = net.AddLinePipe(new LineSegment3d(p1, p2), tubo);
                    AsegurarCapa(tr, db, capa);
                    PonerCapa(tr, tuboId, capa);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Tubo a presión creado: {tubo.Description}  (Id: {tuboId})" +
                                    (string.IsNullOrWhiteSpace(capa) ? "." : $", capa '{capa}'."));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_RUN_PRESION — crea una LÍNEA de red a presión a partir de una
        //   POLILÍNEA del dibujo: coloca tubos por cada segmento y, con
        //   autoAddBends=true, inserta los CODOS automáticamente en los vértices.
        //   Es la base de "convertir polilíneas en redes" (tu objetivo).
        // =====================================================================
        [CommandMethod("CREAR_RUN_PRESION")]
        public void CrearRunPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Polilínea que define el trazado: acepta LWPolyline (2D) o Polyline3d (3D con cotas)
            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la polilínea de la red a presión (2D o 3D):");
            peo.SetRejectMessage("\nDebe ser una polilínea 2D (LWPolyline) o 3D (Polyline3d).");
            peo.AddAllowedClass(typeof(Polyline), false);
            peo.AddAllowedClass(typeof(Polyline3d), false);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            // Profundidad de enterramiento (cover)
            PromptDoubleOptions pCov = new PromptDoubleOptions("\nProfundidad de enterramiento (m):");
            pCov.AllowNegative = false; pCov.DefaultValue = 1.0; pCov.UseDefaultValue = true;
            PromptDoubleResult rCov = ed.GetDouble(pCov);
            if (rCov.Status != PromptStatus.OK) return;
            double cover = rCov.Value;

            // Nombre del run
            PromptStringOptions pNom = new PromptStringOptions("\nNombre de la línea/run (Enter = automático):");
            pNom.AllowSpaces = true;
            PromptResult rNom = ed.GetString(pNom);
            string nombreRun = (rNom.Status == PromptStatus.OK && !string.IsNullOrWhiteSpace(rNom.StringResult))
                                   ? rNom.StringResult.Trim() : "Run-1";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión. Crea una con CREAR_RED_PRESION."); tr.Abort(); return; }

                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);
                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

                    // Elegir el TUBO de la lista de disponibles
                    PresStyles.PressurePartSize tubo = ElegirPiezaPresion(ed, pl.GetParts(CivilDB.PressurePartDomainType.Pipe), "Tubos disponibles");
                    if (tubo == null) { ed.WriteMessage("\nNo se eligió tubo (o no hay tubos en la parts list)."); tr.Abort(); return; }

                    string capa = PreguntarCapa(ed);
                    AsegurarCapa(tr, db, capa);

                    Entity ent = tr.GetObject(per.ObjectId, OpenMode.ForRead) as Entity;

                    if (ent is Polyline poly)
                    {
                        // ---- Camino 2D: createPipeRun con codos automáticos en los vértices ----

                        // AVISO: ¿la superficie de referencia cubre TODA la traza? (si no, el cover no se respeta ahí)
                        if (net.ReferenceSurfaceId != ObjectId.Null)
                        {
                            int fuera, total;
                            SuperficieCubreTraza(tr, net.ReferenceSurfaceId, poly, out fuera, out total);
                            if (fuera > 0)
                            {
                                double pct = 100.0 * fuera / Math.Max(1, total);
                                ed.WriteMessage($"\n⚠ AVISO: la superficie de referencia NO cubre toda la traza: {fuera}/{total} puntos ({pct:F0}%) quedan FUERA.");
                                ed.WriteMessage("\n  En esas zonas el enterramiento (cover) NO se respetará (la red salta a una cota de referencia).");
                                PromptKeywordOptions pkS = new PromptKeywordOptions("\n¿Continuar igual? [Si/No] <No>:", "Si No");
                                pkS.AllowNone = true;
                                PromptResult rkS = ed.GetKeywords(pkS);
                                if (!(rkS.Status == PromptStatus.OK && rkS.StringResult == "Si"))
                                { ed.WriteMessage("\nCancelado. Amplía la superficie, o usa el modo 3D (polilínea 3D / CogoPoints)."); tr.Abort(); return; }
                            }
                            else ed.WriteMessage("\n✓ La superficie de referencia cubre toda la traza.");
                        }
                        else
                        {
                            ed.WriteMessage("\n(Sin superficie de referencia: la tubería quedará PLANA a la elevación de la polilínea menos el cover.)");
                        }

                        var tubosAntes = new HashSet<ObjectId>();
                        foreach (ObjectId id in net.GetPipeIds()) tubosAntes.Add(id);
                        var codosAntes = new HashSet<ObjectId>();
                        foreach (ObjectId id in net.GetFittingIds()) codosAntes.Add(id);

                        try
                        {
                            net.PipeRuns.createPipeRun(nombreRun, poly, tubo, cover, true);
                        }
                        catch (Exception exRun)
                        {
                            ed.WriteMessage($"\n✗ No se pudo crear la línea: {exRun.Message}");
                            ed.WriteMessage("\n  Causa más común: esa POLILÍNEA ya se usó para OTRA red/línea. Cada línea (run) necesita su");
                            ed.WriteMessage("\n  PROPIA polilínea. Dibuja una polilínea nueva para esta red y reintenta.");
                            ed.WriteMessage("\n  (Alternativa: usa el modo 3D — polilínea 3D o CogoPoints — que arma la red tubo a tubo.)");
                            tr.Abort();
                            return;
                        }

                        int tubosNuevos = 0, codosNuevos = 0;
                        double odTubo = 0;   // Ø exterior del tubo, como referencia visual
                        foreach (ObjectId id in net.GetPipeIds())
                            if (!tubosAntes.Contains(id))
                            {
                                tubosNuevos++; PonerCapa(tr, id, capa);
                                if (odTubo <= 0) { var pp = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressurePipe; if (pp != null) odTubo = pp.OuterDiameter; }
                            }
                        int desajuste = 0; double odCodo = 0;
                        foreach (ObjectId id in net.GetFittingIds())
                            if (!codosAntes.Contains(id))
                            {
                                codosNuevos++; PonerCapa(tr, id, capa);
                                // Comparar el Ø exterior del codo (leído de su puerto) con el del tubo
                                try
                                {
                                    var f = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressureFitting;
                                    if (f != null && f.ConnectionCount > 0)
                                    {
                                        double od = f.GetConnectionAt(0).OutsideDiameter;
                                        if (odTubo > 0 && Math.Abs(od - odTubo) > 0.5) { desajuste++; odCodo = od; }
                                    }
                                }
                                catch { }
                            }

                        // Reportar el EJE (alignment) que createPipeRun genera para el run
                        string ejeMsg = "";
                        try
                        {
                            if (net.PipeRuns.Count > 0)
                            {
                                CivilDB.PressurePipeRun runNuevo = net.PipeRuns[net.PipeRuns.Count - 1];
                                if (runNuevo.AlignmentId.IsValid && !runNuevo.AlignmentId.IsNull)
                                {
                                    CivilDB.Alignment al = tr.GetObject(runNuevo.AlignmentId, OpenMode.ForRead) as CivilDB.Alignment;
                                    ejeMsg = al != null ? $" Eje generado: '{al.Name}'." : " Eje generado.";
                                }
                            }
                        }
                        catch { }

                        tr.Commit();
                        ed.WriteMessage($"\n✓ Línea '{nombreRun}' creada desde polilínea 2D con {tubo.Description}: " +
                                        $"{tubosNuevos} tubo(s) y {codosNuevos} codo(s), enterrada {cover:F2} m" +
                                        (string.IsNullOrWhiteSpace(capa) ? "." : $", capa '{capa}'.") + ejeMsg);
                        if (desajuste > 0)
                            ed.WriteMessage($"\n⚠ AVISO: {desajuste} codo(s) tienen Ø exterior ≈ {odCodo:F0} pero el tubo es ≈ {odTubo:F0}. " +
                                            "\n  Por eso se ven más pequeños. La parts list NO tiene un codo del mismo diámetro/familia que el tubo:" +
                                            "\n  añade el CODO del diámetro correcto (mismo material/estándar) y vuelve a crear la línea.");
                    }
                    else if (ent is Polyline3d p3d)
                    {
                        // ---- Camino 3D: un tubo por cada segmento, con la cota (Z) REAL de cada vértice ----
                        var pts = new List<Point3d>();
                        foreach (ObjectId vId in p3d)
                        {
                            PolylineVertex3d v = tr.GetObject(vId, OpenMode.ForRead) as PolylineVertex3d;
                            if (v != null) pts.Add(v.Position);
                        }
                        if (pts.Count < 2) { ed.WriteMessage("\nLa polilínea 3D no tiene suficientes vértices."); tr.Abort(); return; }

                        int nTubos = CrearTuberiasPorPuntos(ed, db, civilDoc, tr, net, pts, tubo, capa, nombreRun + "-eje");
                        tr.Commit();
                        ed.WriteMessage($"\n✓ Línea '{nombreRun}' creada desde polilínea 3D con {tubo.Description}: " +
                                        $"{nTubos} tubo(s) siguiendo las cotas de los vértices" +
                                        (string.IsNullOrWhiteSpace(capa) ? "." : $", capa '{capa}'.") +
                                        "\n  (Nota: en 3D los codos NO se insertan solos; usa UNIR_TUBERIAS_PRESION o AGREGAR_ELEMENTO_PRESION en los quiebres.)");
                    }
                    else
                    {
                        ed.WriteMessage("\nLa entidad no es una polilínea válida.");
                        tr.Abort();
                    }
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_RUN_PRESION_COGO — crea la red a presión a partir de una secuencia
        //   de CogoPoints (usa X/Y/Z reales de cada punto). Un tubo por cada par
        //   consecutivo. Ordena por número de punto (o por descripción).
        // =====================================================================
        [CommandMethod("CREAR_RUN_PRESION_COGO")]
        public void CrearRunPresionCogo()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // ¿Todos los CogoPoints o una selección?
            PromptKeywordOptions optSel = new PromptKeywordOptions("\n¿Usar todos los CogoPoints o seleccionar? [Seleccionar/UsarTodos] <Seleccionar>:");
            optSel.Keywords.Add("Seleccionar");
            optSel.Keywords.Add("UsarTodos");
            optSel.AllowNone = true;
            PromptResult optRes = ed.GetKeywords(optSel);
            if (optRes.Status != PromptStatus.OK && optRes.Status != PromptStatus.None) return;
            bool usarTodos = (optRes.Status == PromptStatus.OK && optRes.StringResult == "UsarTodos");

            // Si es selección manual, se pide FUERA de la transacción
            ObjectId[] seleccion = null;
            if (!usarTodos)
            {
                PromptSelectionOptions selOpts = new PromptSelectionOptions();
                selOpts.MessageForAdding = "\nSeleccione CogoPoints (otras entidades se ignoran):";
                PromptSelectionResult selRes = ed.GetSelection(selOpts);
                if (selRes.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }
                seleccion = selRes.Value.GetObjectIds();
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión. Crea una con CREAR_RED_PRESION."); tr.Abort(); return; }
                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);
                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

                    // Reunir los CogoPoints elegidos
                    var setCogoIds = new HashSet<ObjectId>();
                    CivilDB.CogoPointCollection allCogo = civilDoc.CogoPoints;
                    foreach (ObjectId cid in allCogo) setCogoIds.Add(cid);

                    var lista = new List<CivilDB.CogoPoint>();
                    if (usarTodos)
                    {
                        foreach (ObjectId cid in allCogo)
                        {
                            var cp = tr.GetObject(cid, OpenMode.ForRead) as CivilDB.CogoPoint;
                            if (cp != null) lista.Add(cp);
                        }
                    }
                    else
                    {
                        foreach (ObjectId soId in seleccion)
                        {
                            if (!setCogoIds.Contains(soId)) continue;
                            var cp = tr.GetObject(soId, OpenMode.ForRead) as CivilDB.CogoPoint;
                            if (cp != null) lista.Add(cp);
                        }
                    }
                    if (lista.Count < 2) { ed.WriteMessage("\nSe necesitan al menos 2 CogoPoints."); tr.Abort(); return; }

                    // Orden de conexión
                    PromptKeywordOptions ordOpts = new PromptKeywordOptions("\nOrdenar por: [Numero/Descripcion] <Numero>:");
                    ordOpts.Keywords.Add("Numero"); ordOpts.Keywords.Add("Descripcion"); ordOpts.AllowNone = true;
                    PromptResult ordRes = ed.GetKeywords(ordOpts);
                    if (ordRes.Status == PromptStatus.OK && ordRes.StringResult == "Descripcion")
                        lista.Sort((a, b) => string.Compare(a.RawDescription ?? "", b.RawDescription ?? "", StringComparison.OrdinalIgnoreCase));
                    else
                        lista.Sort((a, b) => a.PointNumber.CompareTo(b.PointNumber));

                    // Elegir el tubo
                    PresStyles.PressurePartSize tubo = ElegirPiezaPresion(ed, pl.GetParts(CivilDB.PressurePartDomainType.Pipe), "Tubos disponibles");
                    if (tubo == null) { ed.WriteMessage("\nNo se eligió tubo."); tr.Abort(); return; }

                    string capa = PreguntarCapa(ed);
                    AsegurarCapa(tr, db, capa);

                    // Puntos 3D reales (X=Easting, Y=Northing, Z=Elevation)
                    var pts = new List<Point3d>();
                    foreach (var cp in lista) pts.Add(new Point3d(cp.Easting, cp.Northing, cp.Elevation));

                    int nTubos = CrearTuberiasPorPuntos(ed, db, civilDoc, tr, net, pts, tubo, capa, "Eje-Presion-Cogo");
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Red a presión creada desde {lista.Count} CogoPoints con {tubo.Description}: " +
                                    $"{nTubos} tubo(s)" + (string.IsNullOrWhiteSpace(capa) ? "." : $", capa '{capa}'.") +
                                    "\n  (Nota: los codos NO se insertan solos; usa UNIR_TUBERIAS_PRESION o AGREGAR_ELEMENTO_PRESION en los quiebres.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // AGREGAR_ELEMENTO_PRESION — coloca UN elemento (codo, tee, cruz, reductor,
        //   válvula, hidrante...) en un punto (clic o coordenada tecleada).
        //   Elige el tipo, opcionalmente el diámetro, y lo coloca:
        //     - Fittings (Elbow/Tee/Cross/Reducer/...) -> net.AddFitting
        //     - Appurtenances (Valve/Hydrant/...)       -> net.AddAppurtenance
        // =====================================================================
        [CommandMethod("AGREGAR_ELEMENTO_PRESION")]
        public void AgregarElementoPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Tipo de elemento
            PromptKeywordOptions pk = new PromptKeywordOptions(
                "\nElemento a colocar [Codo/Tee/Cruz/Reductor/Tapon/Union/Wye/Valvula/Hidrante]:",
                "Codo Tee Cruz Reductor Tapon Union Wye Valvula Hidrante");
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status != PromptStatus.OK) return;

            CivilDB.PressurePartType tipo;
            switch (rk.StringResult)
            {
                case "Codo": tipo = CivilDB.PressurePartType.Elbow; break;
                case "Tee": tipo = CivilDB.PressurePartType.Tee; break;
                case "Cruz": tipo = CivilDB.PressurePartType.Cross; break;
                case "Reductor": tipo = CivilDB.PressurePartType.Reducer; break;
                case "Tapon": tipo = CivilDB.PressurePartType.Cap; break;
                case "Union": tipo = CivilDB.PressurePartType.Coupling; break;
                case "Wye": tipo = CivilDB.PressurePartType.Wye; break;
                case "Valvula": tipo = CivilDB.PressurePartType.Valve; break;
                case "Hidrante": tipo = CivilDB.PressurePartType.Hydrant; break;
                default: tipo = CivilDB.PressurePartType.Elbow; break;
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión. Crea una con CREAR_RED_PRESION."); tr.Abort(); return; }

                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);
                    PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

                    // Elegir la pieza concreta de ese tipo, de una lista
                    PresStyles.PressurePartSize pieza = ElegirPiezaPresion(ed, pl.GetParts(tipo), $"{rk.StringResult} disponibles");
                    if (pieza == null)
                    {
                        ed.WriteMessage($"\nNo se eligió pieza (o no hay de tipo '{rk.StringResult}'). Revisa LISTAR_PIEZAS_PRESION.");
                        tr.Abort(); return;
                    }

                    // Punto: clic o coordenada tecleada (GetPoint admite ambos)
                    PromptPointResult pr = ed.GetPoint("\nUbicación (clic o escribe  X,Y ):");
                    if (pr.Status != PromptStatus.OK) { tr.Abort(); return; }

                    string capa = PreguntarCapa(ed);

                    // Colocar según el dominio de la pieza
                    ObjectId nuevoId;
                    if (pieza.Domain == CivilDB.PressurePartDomainType.Appurtenance)
                        nuevoId = net.AddAppurtenance(pr.Value, pieza);
                    else
                        nuevoId = net.AddFitting(pr.Value, pieza);
                    AsegurarCapa(tr, db, capa);
                    PonerCapa(tr, nuevoId, capa);

                    // Conectar el elemento a tuberías (un puerto a la vez)
                    CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(nuevoId, OpenMode.ForWrite);
                    int puertos = parte.ConnectionCount;
                    ed.WriteMessage($"\nEste elemento tiene {puertos} puerto(s). Elige la tubería de cada uno (Enter = omitir).");
                    int conectados = 0;
                    for (int port = 0; port < puertos; port++)
                    {
                        PromptEntityOptions peoP = new PromptEntityOptions($"\n  Tubería para el puerto {port + 1} (Enter = omitir):");
                        peoP.SetRejectMessage("\nDebe ser una tubería a presión.");
                        peoP.AddAllowedClass(typeof(CivilDB.PressurePipe), true);
                        peoP.AllowNone = true;
                        PromptEntityResult perP = ed.GetEntity(peoP);
                        if (perP.Status != PromptStatus.OK) continue;   // omitir este puerto

                        CivilDB.PressurePipe tuboSel = (CivilDB.PressurePipe)tr.GetObject(perP.ObjectId, OpenMode.ForWrite);
                        // extremo de la tubería más cercano al elemento (0=inicio, 1=fin)
                        int pipePort = (pr.Value.DistanceTo(tuboSel.StartPoint) <= pr.Value.DistanceTo(tuboSel.EndPoint)) ? 0 : 1;
                        try
                        {
                            parte.ConnectToPipe(port, perP.ObjectId, pipePort);
                            conectados++;
                            ed.WriteMessage($"\n    Puerto {port + 1} conectado a '{tuboSel.Name}' (extremo {(pipePort == 0 ? "inicio" : "fin")}).");
                        }
                        catch (Exception exC) { ed.WriteMessage($"\n    No se pudo conectar el puerto {port + 1}: {exC.Message}"); }
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ {rk.StringResult} colocado: {pieza.Description}  (Id: {nuevoId}); {conectados} conexión(es)" +
                                    (string.IsNullOrWhiteSpace(capa) ? "." : $", capa '{capa}'."));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // EXTRAER_SOLIDOS_PRESION — extrae el cuerpo 3D (Solid3d) de cada pieza de
        //   la red (tubos, codos, válvulas) con PressurePart.Get3dBody() y los
        //   dibuja como sólidos de AutoCAD (opcionalmente en una capa).
        // =====================================================================
        [CommandMethod("EXTRAER_SOLIDOS_PRESION")]
        public void ExtraerSolidosPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            string capa = PreguntarCapa(ed);

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión."); tr.Abort(); return; }

                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForRead);

                    BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                    BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                    AsegurarCapa(tr, db, capa);

                    // ¿Adjuntar un Property Set a cada sólido?
                    bool conPS = ElegirPropertySet(ed, tr, db, out ObjectId psdId);

                    // Todas las piezas: tubos + fittings + appurtenances
                    var todas = new List<ObjectId>();
                    foreach (ObjectId id in net.GetPipeIds()) todas.Add(id);
                    foreach (ObjectId id in net.GetFittingIds()) todas.Add(id);
                    foreach (ObjectId id in net.GetAppurtenanceIds()) todas.Add(id);

                    int n = 0, nPS = 0;
                    foreach (ObjectId id in todas)
                    {
                        CivilDB.PressurePart parte = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressurePart;
                        if (parte == null) continue;
                        Solid3d sol = null;
                        try { sol = parte.Get3dBody(); } catch { }
                        if (sol == null) continue;

                        if (!string.IsNullOrWhiteSpace(capa)) sol.Layer = capa;
                        ms.AppendEntity(sol);
                        tr.AddNewlyCreatedDBObject(sol, true);

                        if (conPS)
                        {
                            try { AecPS.PropertyDataServices.AddPropertySet(sol, psdId); nPS++; }
                            catch { }
                        }
                        n++;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Sólidos 3D extraídos de la red a presión: {n}" +
                                    (string.IsNullOrWhiteSpace(capa) ? "." : $" (capa '{capa}').") +
                                    (conPS ? $" Property Set adjuntado a {nPS}." : ""));
                    if (n == 0) ed.WriteMessage("\n(La red no tiene piezas, o no pudieron generar cuerpo 3D.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // UNIR_TUBERIAS_PRESION — selecciona DOS tuberías, analiza su diámetro y
        //   el ángulo entre ellas, te deja elegir el accesorio y lo COLOCA y
        //   CONECTA en el punto de encuentro. Si no calza, explica por qué y
        //   sugiere accesorios del diámetro correcto.
        // =====================================================================
        [CommandMethod("UNIR_TUBERIAS_PRESION")]
        public void UnirTuberiasPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptEntityOptions peo1 = new PromptEntityOptions("\nSeleccione la PRIMERA tubería:");
            peo1.SetRejectMessage("\nDebe ser una tubería a presión.");
            peo1.AddAllowedClass(typeof(CivilDB.PressurePipe), true);
            PromptEntityResult per1 = ed.GetEntity(peo1);
            if (per1.Status != PromptStatus.OK) return;

            PromptEntityOptions peo2 = new PromptEntityOptions("\nSeleccione la SEGUNDA tubería:");
            peo2.SetRejectMessage("\nDebe ser una tubería a presión.");
            peo2.AddAllowedClass(typeof(CivilDB.PressurePipe), true);
            PromptEntityResult per2 = ed.GetEntity(peo2);
            if (per2.Status != PromptStatus.OK) return;
            if (per1.ObjectId == per2.ObjectId) { ed.WriteMessage("\nDeben ser dos tuberías distintas."); return; }

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

                    CivilDB.PressurePipe t1 = tr.GetObject(per1.ObjectId, OpenMode.ForWrite) as CivilDB.PressurePipe;
                    CivilDB.PressurePipe t2 = tr.GetObject(per2.ObjectId, OpenMode.ForWrite) as CivilDB.PressurePipe;
                    if (t1 == null || t2 == null) { ed.WriteMessage("\nSelección inválida."); tr.Abort(); return; }

                    double d1 = t1.NominalDiameter, d2 = t2.NominalDiameter;

                    // Punto de encuentro = extremos más cercanos entre las dos tuberías
                    Point3d[] e1 = { t1.StartPoint, t1.EndPoint };
                    Point3d[] e2 = { t2.StartPoint, t2.EndPoint };
                    int port1 = 0, port2 = 0; double best = double.MaxValue;
                    for (int i = 0; i < 2; i++)
                        for (int j = 0; j < 2; j++)
                        {
                            double dd = e1[i].DistanceTo(e2[j]);
                            if (dd < best) { best = dd; port1 = i; port2 = j; }
                        }
                    Point3d junta = new Point3d((e1[port1].X + e2[port2].X) / 2, (e1[port1].Y + e2[port2].Y) / 2, (e1[port1].Z + e2[port2].Z) / 2);

                    // ¿Esos extremos ya están conectados a algo? (evita crear un accesorio DUPLICADO)
                    ObjectId occ1 = ConexionEnPuerto(t1, port1);   // a qué está unido el extremo de t1
                    ObjectId occ2 = ConexionEnPuerto(t2, port2);   // a qué está unido el extremo de t2
                    bool otro1 = occ1 != ObjectId.Null && occ1 != per2.ObjectId; // ya hay OTRA pieza en t1
                    bool otro2 = occ2 != ObjectId.Null && occ2 != per1.ObjectId; // ya hay OTRA pieza en t2
                    bool unidasDirecto = (occ1 == per2.ObjectId) || (occ2 == per1.ObjectId); // ya unidas tubo-a-tubo

                    if (otro1 || otro2)
                    {
                        ObjectId ya = otro1 ? occ1 : occ2;
                        ed.WriteMessage($"\n✗ Ese extremo YA tiene un accesorio conectado (id {ya}).");
                        ed.WriteMessage("\n  No agrego otro para evitar duplicados. Si quieres cambiarlo, borra ese accesorio y vuelve a unir.");
                        tr.Abort();
                        return;
                    }

                    // Ángulo entre las tuberías (informativo)
                    Vector3d v1 = (port1 == 0 ? e1[1] - e1[0] : e1[0] - e1[1]);
                    Vector3d v2 = (port2 == 0 ? e2[1] - e2[0] : e2[0] - e2[1]);
                    double ang = v1.GetAngleTo(v2) * 180.0 / Math.PI;
                    double deflex = 180.0 - ang;

                    ed.WriteMessage($"\nTuberías: Ø{d1:F0} y Ø{d2:F0}.  Deflexión ≈ {deflex:F1}°.  Separación de extremos: {best:F3}.");
                    if (Math.Abs(d1 - d2) > 1e-6) ed.WriteMessage("\n→ Diámetros distintos: normalmente va un REDUCTOR.");
                    else if (deflex > 1.0) ed.WriteMessage($"\n→ Cambio de dirección: normalmente va un CODO de ~{deflex:F0}°.");
                    else ed.WriteMessage("\n→ Mismo diámetro y alineadas: una UNIÓN (coupling).");
                    if (best > 0.5) ed.WriteMessage($"\n(Aviso: los extremos están a {best:F2} de distancia; puede que no queden bien unidos.)");

                    // Accesorios disponibles + RECOMENDACIÓN automática
                    var fittings = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);
                    if (fittings == null || fittings.Count == 0) { ed.WriteMessage("\nLa parts list no tiene accesorios (fittings)."); tr.Abort(); return; }

                    // Tipo de accesorio que suele corresponder
                    CivilDB.PressurePartType objetivo =
                        (Math.Abs(d1 - d2) > 1e-6) ? CivilDB.PressurePartType.Reducer :
                        (deflex > 1.0) ? CivilDB.PressurePartType.Elbow : CivilDB.PressurePartType.Coupling;

                    string dTxt = ((int)Math.Round(d1)).ToString();
                    string aTxt = ((int)Math.Round(deflex)).ToString();

                    // Buscar el índice recomendado (tipo + diámetro [+ ángulo si es codo])
                    int rec = -1;
                    for (int k = 0; k < fittings.Count && rec < 0; k++)
                    {
                        if (fittings[k].PartType != objetivo) continue;
                        string de = (fittings[k].Description ?? "").Replace(" ", "").Replace(",", "").ToLowerInvariant();
                        if (de.Contains(dTxt) && (objetivo != CivilDB.PressurePartType.Elbow || de.Contains(aTxt))) rec = k;
                    }
                    if (rec < 0)   // relajar: solo por tipo + diámetro
                        for (int k = 0; k < fittings.Count && rec < 0; k++)
                        {
                            if (fittings[k].PartType != objetivo) continue;
                            string de = (fittings[k].Description ?? "").Replace(" ", "").Replace(",", "").ToLowerInvariant();
                            if (de.Contains(dTxt)) rec = k;
                        }

                    PresStyles.PressurePartSize pieza;
                    if (rec >= 0)
                    {
                        ed.WriteMessage($"\nRecomendado (#{rec + 1}): {fittings[rec].Description}");
                        PromptKeywordOptions pkR = new PromptKeywordOptions("\n¿Colocar el recomendado? [Aceptar/Elegir/Cancelar] <Aceptar>:", "Aceptar Elegir Cancelar");
                        pkR.AllowNone = true;
                        PromptResult rR = ed.GetKeywords(pkR);
                        if (rR.Status == PromptStatus.OK && rR.StringResult == "Cancelar") { tr.Abort(); return; }
                        if (rR.Status == PromptStatus.OK && rR.StringResult == "Elegir")
                            pieza = ElegirPiezaPresion(ed, fittings, "Accesorios (fittings) disponibles");
                        else
                            pieza = fittings[rec];   // Aceptar (o Enter) -> usa el recomendado
                    }
                    else
                    {
                        ed.WriteMessage("\nNo hallé un accesorio que calce automáticamente. Elige de la lista:");
                        pieza = ElegirPiezaPresion(ed, fittings, "Accesorios (fittings) disponibles");
                    }
                    if (pieza == null) { ed.WriteMessage("\nNo se eligió accesorio."); tr.Abort(); return; }

                    // Si ya estaban unidas directamente (tubo-a-tubo), separarlas para meter el accesorio EN MEDIO
                    if (unidasDirecto)
                    {
                        ed.WriteMessage("\nLas tuberías estaban unidas directamente; inserto el accesorio en su lugar.");
                        DesconectarDe(t1, per2.ObjectId);
                        DesconectarDe(t2, per1.ObjectId);
                    }

                    // Colocar el accesorio y conectar ambas tuberías
                    ObjectId fid = net.AddFitting(junta, pieza);
                    CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(fid, OpenMode.ForWrite);

                    bool ok1 = false, ok2 = false;
                    try { parte.ConnectToPipe(0, per1.ObjectId, port1); ok1 = true; }
                    catch (Exception ex) { ed.WriteMessage($"\n✗ No se pudo unir a la 1ª tubería: {ex.Message}"); }
                    try { parte.ConnectToPipe(1, per2.ObjectId, port2); ok2 = true; }
                    catch (Exception ex) { ed.WriteMessage($"\n✗ No se pudo unir a la 2ª tubería: {ex.Message}"); }

                    // RECORTAR cada tubería hasta el PUERTO real del accesorio, para que no se
                    // solapen con él (clave en esquinas de 90°). El puerto ya viene orientado por ConnectToPipe.
                    if (ok1 || ok2)
                    {
                        try
                        {
                            for (int i = 0; i < parte.ConnectionCount; i++)
                            {
                                CivilDB.PressurePartConnection c = parte.GetConnectionAt(i);
                                if (c.ConnectedId == per1.ObjectId) { if (port1 == 0) t1.StartPoint = c.Position; else t1.EndPoint = c.Position; }
                                else if (c.ConnectedId == per2.ObjectId) { if (port2 == 0) t2.StartPoint = c.Position; else t2.EndPoint = c.Position; }
                            }
                        }
                        catch (Exception ex) { ed.WriteMessage($"\n(No se pudo recortar los tubos al puerto del accesorio: {ex.Message})"); }
                    }

                    if (!ok1 || !ok2)
                    {
                        // Sugerir accesorios del diámetro de las tuberías (por si el elegido no calza)
                        ed.WriteMessage($"\nSugerencia: el accesorio suele fallar si su diámetro no coincide (tuberías Ø{d1:F0}).");
                        ed.WriteMessage($"\nAccesorios que mencionan Ø{dTxt} (con su #):");
                        int sug = 0;
                        for (int k = 0; k < fittings.Count; k++)
                        {
                            string de = (fittings[k].Description ?? "").Replace(",", "");
                            if (de.Contains(dTxt)) { ed.WriteMessage($"\n  #{k + 1}  {fittings[k].Description}"); sug++; }
                        }
                        if (sug == 0) ed.WriteMessage("\n  (ninguno de ese diámetro en la parts list; añade uno con LISTAR/UI del catálogo).");
                    }

                    tr.Commit();
                    ed.WriteMessage((ok1 && ok2)
                        ? $"\n✓ Unión completa con '{pieza.Description}'."
                        : $"\n⚠ Unión PARCIAL con '{pieza.Description}'. Revisa la sugerencia de arriba.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // EXPORTAR_RED_PRESION_EXCEL — vuelca los datos de la red a un CSV que
        //   Excel abre directamente (tubos, accesorios y válvulas con sus datos).
        //   Sin librerías externas: se genera un .csv con separador ';' y decimales
        //   en la cultura del equipo, precedido de "sep=;" para que Excel lo respete.
        // =====================================================================
        [CommandMethod("EXPORTAR_RED_PRESION_EXCEL")]
        public void ExportarRedPresionExcel()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Pedir dónde guardar (diálogo nativo de Guardar)
            PromptSaveFileOptions opt = new PromptSaveFileOptions("\nGuardar datos de la red como CSV (Excel):");
            opt.Filter = "CSV para Excel (*.csv)|*.csv";
            opt.InitialFileName = "red_presion";
            PromptFileNameResult rF = ed.GetFileNameForSave(opt);
            if (rF.Status != PromptStatus.OK) return;
            string ruta = rF.StringResult;
            if (!ruta.ToLowerInvariant().EndsWith(".csv")) ruta += ".csv";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPressurePipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes a presión."); tr.Abort(); return; }
                    ObjectId netSel = ElegirRedId(ed, tr, nets);
                    if (netSel == ObjectId.Null) { tr.Abort(); return; }
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForRead);

                    CultureInfo ci = CultureInfo.CurrentCulture;   // decimales como los espera el Excel del equipo
                    // Helpers locales para formatear
                    Func<double, string> N = v => v.ToString("0.###", ci);
                    Func<string, string> T = s => "\"" + (s ?? "").Replace("\"", "\"\"") + "\"";  // texto entre comillas

                    var sb = new StringBuilder();
                    sb.AppendLine("sep=;");   // pista para que Excel use ';' como separador

                    // ---------- TUBERÍAS ----------
                    sb.AppendLine("TUBERIAS");
                    sb.AppendLine("Nombre;Descripcion;Diametro_nominal;X_ini;Y_ini;Z_ini;X_fin;Y_fin;Z_fin;Longitud;Capa");
                    int nTubos = 0;
                    foreach (ObjectId id in net.GetPipeIds())
                    {
                        var p = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressurePipe;
                        if (p == null) continue;
                        Point3d a = p.StartPoint, b = p.EndPoint;
                        sb.AppendLine(string.Join(";",
                            T(p.Name), T(p.PartDescription), N(p.NominalDiameter),
                            N(a.X), N(a.Y), N(a.Z), N(b.X), N(b.Y), N(b.Z),
                            N(a.DistanceTo(b)), T(p.Layer)));
                        nTubos++;
                    }

                    // ---------- ACCESORIOS (fittings) ----------
                    sb.AppendLine();
                    sb.AppendLine("ACCESORIOS");
                    sb.AppendLine("Nombre;Tipo;Descripcion;X;Y;Z;Conexiones;Capa");
                    int nFit = 0;
                    foreach (ObjectId id in net.GetFittingIds())
                    {
                        var f = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressureFitting;
                        if (f == null) continue;
                        Point3d q = f.Position;
                        sb.AppendLine(string.Join(";",
                            T(f.Name), T(f.PartType.ToString()), T(f.PartDescription),
                            N(q.X), N(q.Y), N(q.Z), f.ConnectionCount.ToString(ci), T(f.Layer)));
                        nFit++;
                    }

                    // ---------- VÁLVULAS / HIDRANTES (appurtenances) ----------
                    sb.AppendLine();
                    sb.AppendLine("VALVULAS_HIDRANTES");
                    sb.AppendLine("Nombre;Tipo;Descripcion;X;Y;Z;Conexiones;Capa");
                    int nApp = 0;
                    foreach (ObjectId id in net.GetAppurtenanceIds())
                    {
                        var ap = tr.GetObject(id, OpenMode.ForRead) as CivilDB.PressureAppurtenance;
                        if (ap == null) continue;
                        Point3d q = ap.Position;
                        sb.AppendLine(string.Join(";",
                            T(ap.Name), T(ap.PartType.ToString()), T(ap.PartDescription),
                            N(q.X), N(q.Y), N(q.Z), ap.ConnectionCount.ToString(ci), T(ap.Layer)));
                        nApp++;
                    }

                    // Guardar (UTF-8 CON BOM para que Excel muestre bien las tildes)
                    File.WriteAllText(ruta, sb.ToString(), new UTF8Encoding(true));

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Datos exportados a:\n  {ruta}\n  {nTubos} tubería(s), {nFit} accesorio(s), {nApp} válvula(s)/hidrante(s)." +
                                    "\n  Ábrelo con doble clic (se abre en Excel).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // SEGUIR_RASANTE_PRESION — hace que una línea (run) siga una RASANTE (perfil)
        //   que tú diseñes, a un desfase (profundidad) por debajo. Alternativa al
        //   "seguir el terreno" cuando hay desniveles fuertes.
        // =====================================================================
        [CommandMethod("SEGUIR_RASANTE_PRESION")]
        public void SeguirRasantePresion()
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
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);

                    if (net.PipeRuns.Count == 0)
                    { ed.WriteMessage("\nLa red no tiene líneas (runs). Crea una con CREAR_RUN_PRESION desde una polilínea 2D."); tr.Abort(); return; }

                    // Elegir la línea (run) por número
                    ed.WriteMessage("\nLíneas (runs) de la red:");
                    for (int i = 0; i < net.PipeRuns.Count; i++)
                        ed.WriteMessage($"\n  {i + 1}. {net.PipeRuns[i].Name}");
                    PromptIntegerOptions pio = new PromptIntegerOptions("\nNúmero de la línea a la que aplicar la rasante:")
                    { LowerLimit = 1, UpperLimit = net.PipeRuns.Count, DefaultValue = 1, UseDefaultValue = true };
                    PromptIntegerResult pir = ed.GetInteger(pio);
                    if (pir.Status != PromptStatus.OK) { tr.Abort(); return; }
                    CivilDB.PressurePipeRun run = net.PipeRuns[pir.Value - 1];

                    // ¿Usar una rasante que YA existe, o CREARLA ahora?
                    PromptKeywordOptions pkO = new PromptKeywordOptions("\n¿La rasante a seguir? [Existente/Crear] <Crear>:", "Existente Crear");
                    pkO.AllowNone = true;
                    PromptResult rO = ed.GetKeywords(pkO);
                    bool crear = !(rO.Status == PromptStatus.OK && rO.StringResult == "Existente");

                    ObjectId profId;
                    ObjectId alignId = ObjectId.Null;
                    if (crear)
                    {
                        profId = CrearRasanteInteractiva(ed, db, civilDoc, tr, out alignId);
                        if (profId == ObjectId.Null) { ed.WriteMessage("\nNo se creó la rasante."); tr.Abort(); return; }
                    }
                    else
                    {
                        PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el PERFIL (rasante) existente:");
                        peo.SetRejectMessage("\nDebe ser un perfil (Profile).");
                        peo.AddAllowedClass(typeof(CivilDB.Profile), true);
                        PromptEntityResult per = ed.GetEntity(peo);
                        if (per.Status != PromptStatus.OK) { tr.Abort(); return; }
                        profId = per.ObjectId;
                        CivilDB.Profile pr = tr.GetObject(profId, OpenMode.ForRead) as CivilDB.Profile;
                        if (pr != null) alignId = pr.AlignmentId;
                    }

                    // Desfase vertical (profundidad por debajo de la rasante)
                    PromptDoubleOptions pOff = new PromptDoubleOptions("\nDesfase vertical bajo la rasante (m):")
                    { DefaultValue = 1.0, UseDefaultValue = true };
                    PromptDoubleResult rOff = ed.GetDouble(pOff);
                    if (rOff.Status != PromptStatus.OK) { tr.Abort(); return; }
                    double offset = rOff.Value;

                    // ¿Seguimiento dinámico? (si luego editas la rasante, la red se actualiza)
                    PromptKeywordOptions pkF = new PromptKeywordOptions("\n¿Mantener seguimiento dinámico si cambia la rasante? [Si/No] <Si>:", "Si No");
                    pkF.AllowNone = true;
                    PromptResult rkF = ed.GetKeywords(pkF);
                    bool keep = !(rkF.Status == PromptStatus.OK && rkF.StringResult == "No");

                    // Best-effort: asociar los tubos del run al eje de la rasante (necesario para el seguimiento)
                    if (alignId != ObjectId.Null)
                    {
                        foreach (ObjectId id in run.GetPartIds())
                        {
                            try
                            {
                                var pp = tr.GetObject(id, OpenMode.ForWrite) as CivilDB.PressurePipe;
                                if (pp != null) pp.ReferenceAlignmentId = alignId;
                            }
                            catch { }
                        }
                    }

                    // Aplicar el seguimiento de la rasante
                    run.FollowProfile(profId, offset, keep);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ La línea '{run.Name}' ahora sigue la rasante, {offset:F2} m por debajo" +
                                    (keep ? " (seguimiento dinámico)." : "."));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n  Nota: la rasante debe ir por la MISMA traza del run. Si el run se creó desde una" +
                                    "\n  polilínea suelta, la asociación con el eje puede fallar (usa la opción 'Crear' con la misma traza).");
                    tr.Abort();
                }
            }
        }

        // Crea, de forma interactiva, un EJE (desde una polilínea) + perfil de terreno opcional
        // + vista de perfil, y una RASANTE por DATOS (estación/cota) o por CLIC en la vista.
        // Devuelve el ObjectId de la rasante creada (o Null si se cancela); 'alignId' = eje creado.
        private ObjectId CrearRasanteInteractiva(Editor ed, Database db, CivilDocument civilDoc, Transaction tr, out ObjectId alignId)
        {
            alignId = ObjectId.Null;

            // 1) Traza (polilínea 2D) que define el eje y por tanto la rasante
            PromptEntityOptions peoP = new PromptEntityOptions("\nSeleccione la polilínea de la TRAZA (la misma de la red):");
            peoP.SetRejectMessage("\nDebe ser una polilínea (LWPolyline).");
            peoP.AddAllowedClass(typeof(Polyline), false);
            PromptEntityResult perP = ed.GetEntity(peoP);
            if (perP.Status != PromptStatus.OK) return ObjectId.Null;

            // 2) Crear el EJE (alignment) desde esa polilínea
            ObjectId aStyle = civilDoc.Styles.AlignmentStyles[0];
            ObjectId aLabel = civilDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0];
            CivilDB.PolylineOptions plo = new CivilDB.PolylineOptions
            { PlineId = perP.ObjectId, AddCurvesBetweenTangents = false, EraseExistingEntities = false };
            alignId = CivilDB.Alignment.Create(civilDoc, plo, "Eje-Presion", ObjectId.Null, db.Clayer, aStyle, aLabel);

            ObjectId pStyle = civilDoc.Styles.ProfileStyles[0];
            ObjectId pLabel = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

            // 3) Perfil del TERRENO (opcional) para ver el suelo en la vista
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
                {
                    try { CivilDB.Profile.CreateFromSurface("Terreno-Presion", alignId, perS.ObjectId, db.Clayer, pStyle, pLabel); }
                    catch (Exception ex) { ed.WriteMessage($"\n(No se pudo crear el perfil de terreno: {ex.Message})"); }
                }
            }

            // 4) Vista de perfil (el "lienzo" para ver y/o pinchar la rasante)
            PromptPointResult pIns = ed.GetPoint("\nPunto de inserción de la vista de perfil:");
            if (pIns.Status != PromptStatus.OK) return ObjectId.Null;
            ObjectId pvId = CivilDB.ProfileView.Create(alignId, pIns.Value);

            // 5) Crear la RASANTE (vacía) y añadirle los PVIs
            ObjectId profId = CivilDB.Profile.CreateByLayout("Rasante-Presion", alignId, db.Clayer, pStyle, pLabel);
            CivilDB.Profile prof = (CivilDB.Profile)tr.GetObject(profId, OpenMode.ForWrite);

            PromptKeywordOptions pkM = new PromptKeywordOptions("\n¿Cómo defines la rasante? [Datos/Clic] <Clic>:", "Datos Clic");
            pkM.AllowNone = true;
            PromptResult rM = ed.GetKeywords(pkM);
            bool porDatos = (rM.Status == PromptStatus.OK && rM.StringResult == "Datos");

            int nPvi = 0;
            if (porDatos)
            {
                ed.WriteMessage("\nIntroduce cada PVI (estación y cota). Enter en la estación para terminar.");
                while (true)
                {
                    PromptDoubleOptions pE = new PromptDoubleOptions($"\nPVI {nPvi + 1} - estación (Enter = terminar):");
                    pE.AllowNone = true;
                    PromptDoubleResult rE = ed.GetDouble(pE);
                    if (rE.Status != PromptStatus.OK) break;
                    PromptDoubleResult rC = ed.GetDouble($"\nPVI {nPvi + 1} - cota:");
                    if (rC.Status != PromptStatus.OK) break;
                    prof.PVIs.AddPVI(rE.Value, rC.Value);
                    nPvi++;
                }
            }
            else
            {
                CivilDB.ProfileView pv = (CivilDB.ProfileView)tr.GetObject(pvId, OpenMode.ForRead);
                ed.WriteMessage("\nPincha los PVIs dentro de la vista (de izquierda a derecha). Enter para terminar.");
                while (true)
                {
                    PromptPointOptions ppo = new PromptPointOptions($"\nPVI {nPvi + 1} (clic en la vista): ");
                    ppo.AllowNone = true;
                    PromptPointResult ppr = ed.GetPoint(ppo);
                    if (ppr.Status != PromptStatus.OK) break;
                    double est = 0, cota = 0;
                    if (!pv.FindStationAndElevationAtXY(ppr.Value.X, ppr.Value.Y, ref est, ref cota))
                    { ed.WriteMessage("\n  (Ese punto cae fuera de la vista; ignorado.)"); continue; }
                    prof.PVIs.AddPVI(est, cota);
                    nPvi++;
                    ed.WriteMessage($"\n  PVI {nPvi}: estación {est:F2}, cota {cota:F2}");
                }
            }

            if (nPvi < 2) { ed.WriteMessage("\nLa rasante necesita al menos 2 PVIs."); return ObjectId.Null; }
            ed.WriteMessage($"\n✓ Rasante creada con {nPvi} PVIs.");
            return profId;
        }

        // ¿La superficie cubre toda la traza de la polilínea? Muestrea ~50 puntos a lo largo
        // y cuenta cuántos quedan FUERA (FindElevationAtXY lanza excepción fuera del contorno).
        private static void SuperficieCubreTraza(Transaction tr, ObjectId surfId, Polyline poly, out int fuera, out int total)
        {
            fuera = 0; total = 0;
            CivilDB.Surface sup = tr.GetObject(surfId, OpenMode.ForRead) as CivilDB.Surface;
            if (sup == null) return;
            double len = poly.Length;
            if (len <= 0) return;
            const int n = 50;
            for (int i = 0; i <= n; i++)
            {
                Point3d p;
                try { p = poly.GetPointAtDist(len * i / n); } catch { continue; }
                total++;
                try { sup.FindElevationAtXY(p.X, p.Y); } catch { fuera++; }
            }
        }

        // Devuelve el ObjectId de lo que está conectado a un extremo del tubo (0=inicio,1=fin),
        // o ObjectId.Null si ese extremo está libre. (Sirve para no duplicar accesorios.)
        private static ObjectId ConexionEnPuerto(CivilDB.PressurePipe p, int port)
        {
            try
            {
                CivilDB.PressurePartConnection c = (port == 0) ? p.StartConnection : p.EndConnection;
                if (c == null) return ObjectId.Null;
                ObjectId id = c.ConnectedId;
                return (id.IsValid && !id.IsNull) ? id : ObjectId.Null;
            }
            catch { return ObjectId.Null; }
        }

        // Desconecta un tubo de otra pieza concreta (recorre sus conexiones de atrás hacia
        // delante porque DisconnectAt reindexa). Se usa para reemplazar una unión tubo-a-tubo.
        private static void DesconectarDe(CivilDB.PressurePipe p, ObjectId otroId)
        {
            for (int i = p.ConnectionCount - 1; i >= 0; i--)
            {
                try { if (p.GetConnectionAt(i).ConnectedId == otroId) p.DisconnectAt(i); }
                catch { }
            }
        }

        // Construye una línea de tubos a presión punto a punto (un tubo por segmento) usando
        // la cota Z REAL de cada punto, conecta tubos consecutivos y (opcional) crea un EJE
        // (alignment) a lo largo de la traza y lo asocia a los tubos. Devuelve cuántos tubos creó.
        // Se usa para polilíneas 3D y para secuencias de CogoPoints.
        private int CrearTuberiasPorPuntos(Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
                                           CivilDB.PressurePipeNetwork net, List<Point3d> pts,
                                           PresStyles.PressurePartSize tubo, string capa, string nombreEje)
        {
            var pipeIds = new List<ObjectId>();
            for (int i = 0; i < pts.Count - 1; i++)
            {
                // Saltar segmentos de longitud casi nula (puntos repetidos)
                if (pts[i].DistanceTo(pts[i + 1]) < 1e-6) continue;
                ObjectId pid = net.AddLinePipe(new LineSegment3d(pts[i], pts[i + 1]), tubo);
                if (!string.IsNullOrWhiteSpace(capa)) PonerCapa(tr, pid, capa);
                pipeIds.Add(pid);
            }

            // Conectar el FIN de cada tubo (puerto 1) con el INICIO del siguiente (puerto 0)
            int conectados = 0;
            for (int i = 0; i < pipeIds.Count - 1; i++)
            {
                try
                {
                    CivilDB.PressurePipe a = tr.GetObject(pipeIds[i], OpenMode.ForWrite) as CivilDB.PressurePipe;
                    if (a != null) { a.ConnectToPipe(1, pipeIds[i + 1], 0); conectados++; }
                }
                catch { /* si el quiebre es muy pronunciado puede requerir un codo; se ignora */ }
            }
            if (pipeIds.Count > 1)
                ed.WriteMessage($"\n  ({conectados} de {pipeIds.Count - 1} uniones tubo-a-tubo realizadas.)");

            // Crear el EJE (alignment) a lo largo de la traza y asociarlo a los tubos.
            ObjectId alignId = CrearAlineamientoDesdePuntos(ed, db, civilDoc, tr, pts, nombreEje);
            if (alignId != ObjectId.Null)
            {
                foreach (ObjectId pid in pipeIds)
                {
                    try
                    {
                        CivilDB.PressurePipe pp = tr.GetObject(pid, OpenMode.ForWrite) as CivilDB.PressurePipe;
                        if (pp != null) pp.ReferenceAlignmentId = alignId;
                    }
                    catch { }
                }
                ed.WriteMessage($"\n  ✓ Alineamiento '{nombreEje}' creado y asociado (útil para perfiles/rasante).");
            }
            return pipeIds.Count;
        }

        // Crea un alineamiento (Civil) a lo largo de la planta (X-Y) de una lista de puntos.
        // Arma una polilínea temporal y la convierte en Alignment (que la borra al terminar).
        private ObjectId CrearAlineamientoDesdePuntos(Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
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
            catch (Exception ex)
            {
                ed.WriteMessage($"\n  (No se pudo crear el alineamiento: {ex.Message})");
                return ObjectId.Null;
            }
        }

        // =====================================================================
        // DESCRIBIR_PIEZA_PRESION — pone una DESCRIPCIÓN (nombre visible) a un tubo,
        //   codo o válvula. Nota: el "Name" interno lo asigna Civil y es de solo
        //   lectura; lo editable es la Descripción (se ve en Propiedades/Prospector).
        // =====================================================================
        [CommandMethod("DESCRIBIR_PIEZA_PRESION")]
        public void DescribirPiezaPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la pieza a la que poner nombre/descripción:");
            peo.SetRejectMessage("\nDebe ser un tubo, accesorio o válvula a presión.");
            peo.AddAllowedClass(typeof(CivilDB.PressurePipe), false);
            peo.AddAllowedClass(typeof(CivilDB.PressureFitting), false);
            peo.AddAllowedClass(typeof(CivilDB.PressureAppurtenance), false);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            PromptStringOptions pso = new PromptStringOptions("\nNombre/descripción para la pieza:") { AllowSpaces = true };
            PromptResult pr = ed.GetString(pso);
            if (pr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pr.StringResult)) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(per.ObjectId, OpenMode.ForWrite);
                    string txt = pr.StringResult.Trim();
                    parte.Description = txt;
                    bool nombreOk = false;
                    try { parte.Name = txt; nombreOk = true; } catch { }
                    tr.Commit();
                    ed.WriteMessage(nombreOk
                        ? $"\n✓ Nombre y descripción asignados: '{txt}'."
                        : $"\n✓ Descripción asignada: '{txt}'. (El 'Name' interno lo fija Civil y no aceptó el cambio.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // ADJUNTAR_PROPERTY_SET — selecciona objetos (p. ej. sólidos) y adjunta un
        //   Property Set elegido en una VENTANA con botones.
        // =====================================================================
        [CommandMethod("ADJUNTAR_PROPERTY_SET")]
        public void AdjuntarPropertySet()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            // 1) Seleccionar los objetos (sólidos u otros)
            PromptSelectionResult sel = ed.GetSelection(new PromptSelectionOptions
            { MessageForAdding = "\nSeleccione los objetos a los que adjuntar el Property Set:" });
            if (sel.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }
            ObjectId[] ids = sel.Value.GetObjectIds();

            // 2) Leer los Property Sets disponibles (nombre + id)
            var nombres = new List<string>();
            var psdIds = new List<ObjectId>();
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    AecPS.DictionaryPropertySetDefinitions dict = new AecPS.DictionaryPropertySetDefinitions(db);
                    ObjectIdCollection recs = dict.Records;
                    if (recs != null)
                        foreach (ObjectId id in recs)
                        {
                            AecPS.PropertySetDefinition d = tr.GetObject(id, OpenMode.ForRead) as AecPS.PropertySetDefinition;
                            if (d != null) { nombres.Add(d.Name); psdIds.Add(id); }
                        }
                    tr.Commit();
                }
                catch (Exception ex) { ed.WriteMessage($"\nError leyendo Property Sets: {ex.Message}"); tr.Abort(); return; }
            }
            if (nombres.Count == 0)
            { ed.WriteMessage("\nNo hay definiciones de Property Set en el dibujo. Créalas en el Administrador de estilos y reintenta."); return; }

            // 3) Ventana con BOTONES para elegir
            VentanaPropertySet win = new VentanaPropertySet(nombres);
            Application.ShowModalWindow(win);
            if (win.SelectedIndex < 0) { ed.WriteMessage("\nCancelado."); return; }
            ObjectId psdId = psdIds[win.SelectedIndex];

            // 4) Adjuntar a cada objeto seleccionado
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    int n = 0;
                    foreach (ObjectId id in ids)
                    {
                        try
                        {
                            Entity ent = tr.GetObject(id, OpenMode.ForWrite) as Entity;
                            if (ent == null) continue;
                            AecPS.PropertyDataServices.AddPropertySet(ent, psdId);
                            n++;
                        }
                        catch { }
                    }
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Property Set '{nombres[win.SelectedIndex]}' adjuntado a {n} objeto(s).");
                }
                catch (Exception ex) { ed.WriteMessage($"\nError: {ex.Message}"); tr.Abort(); }
            }
        }

        // Pregunta y elige una definición de Property Set del dibujo. Devuelve true + psdId si se elige.
        private bool ElegirPropertySet(Editor ed, Transaction tr, Database db, out ObjectId psdId)
        {
            psdId = ObjectId.Null;
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Adjuntar un Property Set a los sólidos? [Si/No] <No>:", "Si No");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (!(rk.Status == PromptStatus.OK && rk.StringResult == "Si")) return false;

            AecPS.DictionaryPropertySetDefinitions dict = new AecPS.DictionaryPropertySetDefinitions(db);
            ObjectIdCollection recs = dict.Records;
            if (recs == null || recs.Count == 0)
            {
                ed.WriteMessage("\nNo hay definiciones de Property Set en el dibujo. Créalas primero (Administrador de estilos) y reintenta.");
                return false;
            }
            var nombres = new List<string>(); var ids = new List<ObjectId>();
            foreach (ObjectId id in recs)
            {
                AecPS.PropertySetDefinition d = tr.GetObject(id, OpenMode.ForRead) as AecPS.PropertySetDefinition;
                if (d != null) { nombres.Add(d.Name); ids.Add(id); }
            }
            if (ids.Count == 0) return false;
            ed.WriteMessage("\nProperty Sets disponibles:");
            for (int i = 0; i < nombres.Count; i++) ed.WriteMessage($"\n  {i + 1}. {nombres[i]}");
            PromptIntegerOptions pio = new PromptIntegerOptions("\nNúmero del Property Set:")
            { LowerLimit = 1, UpperLimit = ids.Count, DefaultValue = 1, UseDefaultValue = true };
            PromptIntegerResult pir = ed.GetInteger(pio);
            if (pir.Status != PromptStatus.OK) return false;
            psdId = ids[pir.Value - 1];
            return true;
        }

        // Deja ELEGIR la red a presión de destino cuando hay más de una (arregla el bug de
        // que todo se agregaba siempre a la primera red). Devuelve el ObjectId elegido, o Null
        // si se cancela. Asume nets.Count >= 1 (el llamador ya validó que hay al menos una).
        private ObjectId ElegirRedId(Editor ed, Transaction tr, ObjectIdCollection nets)
        {
            if (nets.Count == 1) return nets[0];
            var nombres = new List<string>();
            for (int i = 0; i < nets.Count; i++)
            {
                var n = tr.GetObject(nets[i], OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                nombres.Add(n != null ? n.Name : $"(red {i + 1})");
            }
            ed.WriteMessage("\nRedes a presión disponibles:");
            for (int i = 0; i < nombres.Count; i++) ed.WriteMessage($"\n  {i + 1}. {nombres[i]}");
            PromptIntegerOptions pio = new PromptIntegerOptions("\n¿En qué red trabajar? Número (Enter = la última):")
            { LowerLimit = 1, UpperLimit = nets.Count, DefaultValue = nets.Count, UseDefaultValue = true };
            PromptIntegerResult pir = ed.GetInteger(pio);
            if (pir.Status != PromptStatus.OK) return ObjectId.Null;
            return nets[pir.Value - 1];
        }

        // Muestra una lista NUMERADA de piezas y deja elegir una (o null si cancela/vacía).
        private PresStyles.PressurePartSize ElegirPiezaPresion(Editor ed, List<PresStyles.PressurePartSize> lista, string titulo)
        {
            if (lista == null || lista.Count == 0) { ed.WriteMessage($"\n(No hay piezas disponibles: {titulo}.)"); return null; }
            ed.WriteMessage($"\n{titulo}:");
            for (int i = 0; i < lista.Count; i++)
                ed.WriteMessage($"\n  {i + 1}. {lista[i].Description}");
            PromptIntegerOptions pio = new PromptIntegerOptions("\nNúmero de la pieza:");
            pio.LowerLimit = 1; pio.UpperLimit = lista.Count;
            PromptIntegerResult pir = ed.GetInteger(pio);
            if (pir.Status != PromptStatus.OK) return null;
            return lista[pir.Value - 1];
        }

        // Se asegura de que exista una capa con ese nombre (la crea si falta). Vacío = no hace nada.
        private static void AsegurarCapa(Transaction tr, Database db, string nombre)
        {
            if (string.IsNullOrWhiteSpace(nombre)) return;
            LayerTable lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (lt.Has(nombre)) return;
            lt.UpgradeOpen();
            LayerTableRecord ltr = new LayerTableRecord { Name = nombre };
            lt.Add(ltr);
            tr.AddNewlyCreatedDBObject(ltr, true);
        }

        // Pone una entidad (por su ObjectId) en la capa indicada. Vacío = la deja como está.
        private static void PonerCapa(Transaction tr, ObjectId id, string capa)
        {
            if (string.IsNullOrWhiteSpace(capa) || id == ObjectId.Null) return;
            Entity e = tr.GetObject(id, OpenMode.ForWrite) as Entity;
            if (e != null) e.Layer = capa;
        }

        // Pregunta una capa (Enter = la capa actual, sin cambiar).
        private static string PreguntarCapa(Editor ed)
        {
            PromptStringOptions p = new PromptStringOptions("\nCapa de destino (Enter = capa actual):");
            p.AllowSpaces = true;
            PromptResult r = ed.GetString(p);
            return (r.Status == PromptStatus.OK) ? r.StringResult.Trim() : "";
        }

        // =====================================================================
        // CORREGIR_FITTINGS_PRESION — comando manual: elige una red y corrige
        //   sus fittings de diámetro incorrecto (con confirmación). La lógica
        //   real vive en CorregirFittingsDeRed, reutilizada también por
        //   IMPORTAR_RED para corregir automáticamente al importar (sin
        //   preguntar) — ver CrearRedPresionCompleta en ImportarRed.cs.
        // =====================================================================
        [CommandMethod("CORREGIR_FITTINGS_PRESION", CommandFlags.Modal | CommandFlags.Session)]
        public void CorregirFittingsPresion()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
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
                    CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netSel, OpenMode.ForWrite);

                    var (detectados, corregidos, fallidos) = CorregirFittingsDeRed(net, tr, ed, preguntar: true);

                    tr.Commit();
                    if (detectados == 0)
                        ed.WriteMessage("\n✓ Todos los fittings coinciden con el diámetro de sus tuberías.");
                    else
                        ed.WriteMessage($"\n\n✓ Resultado: {corregidos} corregido(s), {fallidos} fallido(s) de {detectados} detectado(s).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // Detecta fittings cuyo diámetro no coincide con el del tubo conectado
        // y los reemplaza por el fitting correcto de la Parts List de la red.
        // `preguntar` = true: lista los desajustes y pide confirmación [Si/No]
        // antes de tocar nada (uso interactivo, CORREGIR_FITTINGS_PRESION).
        // `preguntar` = false: corrige directo, sin preguntar (uso automático
        // al importar desde DXF). Devuelve (detectados, corregidos, fallidos);
        // (0,0,0) si la red no tiene fittings, no hay Parts List de fittings,
        // o todos ya coinciden.
        internal static (int Detectados, int Corregidos, int Fallidos) CorregirFittingsDeRed(
            CivilDB.PressurePipeNetwork net, Transaction tr, Editor ed, bool preguntar)
        {
            PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(net.PartsListId, OpenMode.ForRead);

            var fittingIds = new List<ObjectId>();
            foreach (ObjectId id in net.GetFittingIds()) fittingIds.Add(id);
            ed.WriteMessage($"\n  [CORREGIR_FITTINGS] Red '{net.Name}': {fittingIds.Count} fitting(s) encontrados.");
            if (fittingIds.Count == 0) return (0, 0, 0);

            var partsDisp = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);
            ed.WriteMessage($"\n  [CORREGIR_FITTINGS] Parts List '{pl.Name}': {partsDisp?.Count ?? 0} fitting(s) disponibles en catálogo.");
            if (partsDisp == null || partsDisp.Count == 0) return (0, 0, 0);

            // Fase 1: detectar desajustes
            var reemplazos = new List<_ReemplazoInfo>();

            foreach (ObjectId fid in fittingIds)
            {
                CivilDB.PressureFitting fit = tr.GetObject(fid, OpenMode.ForRead) as CivilDB.PressureFitting;
                if (fit == null) { ed.WriteMessage("\n  [CORREGIR_FITTINGS] · (no es PressureFitting, se salta)"); continue; }

                double fitDia = _ObtenerDiametroFitting(fit);
                string descOriginal = "?"; try { descOriginal = fit.PartDescription; } catch { }
                if (fitDia <= 0)
                {
                    ed.WriteMessage($"\n  [CORREGIR_FITTINGS] · '{descOriginal}': no se pudo leer su diámetro (fitDia<=0), se salta.");
                    continue;
                }

                var conexiones = new List<_ConexionInfo>();
                double pipeDiaMax = 0, pipeNomDiaMax = 0;

                for (int p = 0; p < fit.ConnectionCount; p++)
                {
                    CivilDB.PressurePartConnection conn = fit.GetConnectionAt(p);
                    if (conn.ConnectedId == ObjectId.Null || !conn.ConnectedId.IsValid) continue;
                    try
                    {
                        CivilDB.PressurePipe pipe = tr.GetObject(conn.ConnectedId, OpenMode.ForRead) as CivilDB.PressurePipe;
                        if (pipe == null) continue;
                        int pipePort = (fit.Position.DistanceTo(pipe.StartPoint) <= fit.Position.DistanceTo(pipe.EndPoint)) ? 0 : 1;
                        conexiones.Add(new _ConexionInfo { PipeId = conn.ConnectedId, PipePort = pipePort, FitPort = p });
                        if (pipe.OuterDiameter > pipeDiaMax) pipeDiaMax = pipe.OuterDiameter;
                        if (pipe.NominalDiameter > pipeNomDiaMax) pipeNomDiaMax = pipe.NominalDiameter;
                    }
                    catch { }
                }

                ed.WriteMessage($"\n  [CORREGIR_FITTINGS] · '{descOriginal}': fitDia(OD)={fitDia:F2}, conexiones={conexiones.Count}, " +
                                $"pipeDiaMax(OD)={pipeDiaMax:F2}, pipeNomDiaMax={pipeNomDiaMax:F2}");

                if (pipeDiaMax <= 0 || conexiones.Count == 0) continue;
                // Comparación de MISMATCH: OD del fitting vs OD del tubo (mismo tipo de
                // medida en ambos lados). Para BUSCAR el reemplazo en el catálogo se usa
                // el diámetro NOMINAL (pipeNomDiaMax) más abajo — las descripciones del
                // catálogo ("12 in x 12 in...") están en nominal, no en OD real (que para
                // tubería de hierro dúctil/PVC suele ser mayor que el nominal, p.ej. 12"
                // nominal ≈ 13.2" de OD real — comparar OD contra nominal ahí habría
                // fallado el match aunque el fitting correcto SÍ estuviera en la Parts List).
                if (Math.Abs(fitDia - pipeDiaMax) < 0.5) continue;

                string angulo = _ExtraerAngulo(fit.PartDescription);

                reemplazos.Add(new _ReemplazoInfo
                {
                    FittingId = fid,
                    Posicion = fit.Position,
                    Tipo = fit.PartType,
                    Angulo = angulo,
                    DiametroActual = fitDia,
                    DiametroCorrecto = pipeNomDiaMax > 0 ? pipeNomDiaMax : pipeDiaMax,
                    Conexiones = conexiones,
                    DescVieja = fit.PartDescription
                });
            }

            if (reemplazos.Count == 0) return (0, 0, 0);

            if (preguntar)
            {
                ed.WriteMessage($"\n{reemplazos.Count} fitting(s) con diámetro incorrecto:");
                foreach (var r in reemplazos)
                    ed.WriteMessage($"\n  · {r.Tipo} '{r.DescVieja}' (Ø{r.DiametroActual:F0}) → necesita Ø{r.DiametroCorrecto:F0}");

                PromptKeywordOptions pkC = new PromptKeywordOptions(
                    $"\n¿Corregir {reemplazos.Count} fitting(s)? [Si/No] <Si>:", "Si No");
                pkC.AllowNone = true;
                PromptResult rkC = ed.GetKeywords(pkC);
                if (rkC.Status == PromptStatus.OK && rkC.StringResult == "No") return (reemplazos.Count, 0, 0);
            }

            // Fase 2: reemplazar
            int corregidos = 0, fallidos = 0;

            foreach (var r in reemplazos)
            {
                PresStyles.PressurePartSize nuevaPieza = _BuscarPiezaCorrecta(partsDisp, r.Tipo, r.DiametroCorrecto, r.Angulo);
                if (nuevaPieza == null)
                {
                    ed.WriteMessage($"\n  ✗ No hay {r.Tipo} Ø{r.DiametroCorrecto:F0}" +
                                    (r.Angulo != null ? $" {r.Angulo}°" : "") + " en la Parts List.");
                    fallidos++;
                    continue;
                }

                try
                {
                    // Desconectar tubos del fitting viejo
                    CivilDB.PressureFitting fitViejo = (CivilDB.PressureFitting)tr.GetObject(r.FittingId, OpenMode.ForWrite);
                    foreach (var c in r.Conexiones)
                    {
                        try
                        {
                            CivilDB.PressurePipe pipe = (CivilDB.PressurePipe)tr.GetObject(c.PipeId, OpenMode.ForWrite);
                            _DesconectarPipeDeFitting(pipe, r.FittingId);
                        }
                        catch { }
                    }

                    // Borrar fitting viejo
                    fitViejo.Erase();

                    // Colocar fitting nuevo
                    ObjectId nuevoId = net.AddFitting(r.Posicion, nuevaPieza);
                    CivilDB.PressurePart parteNueva = (CivilDB.PressurePart)tr.GetObject(nuevoId, OpenMode.ForWrite);

                    // Reconectar tubos
                    int conectados = 0;
                    for (int i = 0; i < Math.Min(parteNueva.ConnectionCount, r.Conexiones.Count); i++)
                    {
                        var c = r.Conexiones[i];
                        try { parteNueva.ConnectToPipe(i, c.PipeId, c.PipePort); conectados++; }
                        catch { }
                    }

                    // Recortar tubos al puerto del nuevo fitting
                    try
                    {
                        for (int i = 0; i < parteNueva.ConnectionCount; i++)
                        {
                            CivilDB.PressurePartConnection conn = parteNueva.GetConnectionAt(i);
                            if (conn.ConnectedId == ObjectId.Null || !conn.ConnectedId.IsValid) continue;
                            CivilDB.PressurePipe pipe = tr.GetObject(conn.ConnectedId, OpenMode.ForWrite) as CivilDB.PressurePipe;
                            if (pipe == null) continue;
                            if (conn.Position.DistanceTo(pipe.StartPoint) < conn.Position.DistanceTo(pipe.EndPoint))
                                pipe.StartPoint = conn.Position;
                            else
                                pipe.EndPoint = conn.Position;
                        }
                    }
                    catch { }

                    ed.WriteMessage($"\n  ✓ {r.Tipo}: '{r.DescVieja}' → '{nuevaPieza.Description}' ({conectados} conexión(es))");
                    corregidos++;
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n  ✗ Error reemplazando {r.Tipo}: {ex.Message}");
                    fallidos++;
                }
            }

            return (reemplazos.Count, corregidos, fallidos);
        }

        private static double _ObtenerDiametroFitting(CivilDB.PressureFitting fit)
        {
            try { if (fit.ConnectionCount > 0) return fit.GetConnectionAt(0).OutsideDiameter; }
            catch { }
            var m = System.Text.RegularExpressions.Regex.Match(fit.PartDescription ?? "", @"(\d+)\s*in");
            if (m.Success && double.TryParse(m.Groups[1].Value, out double d)) return d;
            return 0;
        }

        private static string _ExtraerAngulo(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return null;
            var m = System.Text.RegularExpressions.Regex.Match(desc, @"([\d.]+)\s*degree");
            return m.Success ? m.Groups[1].Value : null;
        }

        private static PresStyles.PressurePartSize _BuscarPiezaCorrecta(
            List<PresStyles.PressurePartSize> partes,
            CivilDB.PressurePartType tipo, double diametro, string angulo)
        {
            string diaStr = ((int)Math.Round(diametro)).ToString();
            PresStyles.PressurePartSize mejorConAngulo = null;
            PresStyles.PressurePartSize mejorSinAngulo = null;

            foreach (var p in partes)
            {
                if (p.PartType != tipo) continue;
                string desc = (p.Description ?? "").ToLowerInvariant();

                // Verificar que el primer diámetro en la descripción coincida
                var mDia = System.Text.RegularExpressions.Regex.Match(desc, @"(\d+)\s*in");
                if (!mDia.Success) continue;
                int primerDia = int.Parse(mDia.Groups[1].Value);
                if (Math.Abs(primerDia - diametro) > 1.0) continue;

                if (angulo != null && desc.Contains(angulo + " degree"))
                {
                    mejorConAngulo = p;
                    break;
                }
                if (mejorSinAngulo == null) mejorSinAngulo = p;
            }
            return mejorConAngulo ?? mejorSinAngulo;
        }

        private static void _DesconectarPipeDeFitting(CivilDB.PressurePipe pipe, ObjectId fittingId)
        {
            try
            {
                for (int port = 0; port < 2; port++)
                {
                    CivilDB.PressurePartConnection conn = pipe.GetConnectionAt(port);
                    if (conn.ConnectedId == fittingId) { pipe.DisconnectAt(port); return; }
                }
            }
            catch { }
        }

        private class _ConexionInfo { public ObjectId PipeId; public int PipePort; public int FitPort; }
        private class _ReemplazoInfo
        {
            public ObjectId FittingId;
            public Point3d Posicion;
            public CivilDB.PressurePartType Tipo;
            public string Angulo;
            public double DiametroActual, DiametroCorrecto;
            public List<_ConexionInfo> Conexiones;
            public string DescVieja;
        }
    }
}
