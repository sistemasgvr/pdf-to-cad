using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices; // alias: objetos de Civil 3D (CogoPoint, Alignment, TinSurface...)
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA PARA LEER ESTE ARCHIVO  (detalle completo en README.md, sección 4)
//  - Cada método con [CommandMethod("X")] es un COMANDO: escribes X en Civil 3D.
//  - Patrón de casi todos:
//        1) obtener doc / ed / db          (dibujo, línea de comandos, base de datos)
//        2) abrir una Transaction          (using (Transaction tr = ...))
//        3) pedir datos con ed.Get...      (GetPoint, GetString, GetKeywords, GetEntity...)
//        4) crear / leer / modificar objetos
//        5) tr.Commit()                    (confirmar) — o tr.Abort() si algo falla
//  - 'ed' pregunta y escribe mensajes en la línea de comandos.
//  - 'tr.GetObject(id, OpenMode.ForRead|ForWrite)' = "abrir" un objeto por su ObjectId
//     (ForRead = solo leer, ForWrite = poder modificar).
//  - Siempre se revisa '.Status == PromptStatus.OK'; si no, el usuario canceló (ESC).
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Comandos base de Civil 3D 2026 (API real, sin reflexión):
    /// puntos, CogoPoints, alineamiento, superficie y utilidades de curvas de nivel.
    /// Todo objeto de Civil 3D se crea/lee dentro de una Transaction (ver guía arriba).
    /// </summary>
    public class ComandosCivilReal
    {
        // =====================================================================
        // 1) PUNTOS AUTOCAD  (DBPoint) — el "hola mundo" de la API de AutoCAD
        // =====================================================================
        [CommandMethod("CREAR_PUNTOS")]
        public void CrearPuntos()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Abrimos el ModelSpace para escribir en él
                    BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                    BlockTableRecord ms = (BlockTableRecord)tr.GetObject(
                        bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);

                    // El usuario va marcando puntos hasta pulsar ESC/Enter
                    int count = 0;
                    while (true)
                    {
                        PromptPointOptions ppo = new PromptPointOptions(
                            "\nIndique punto (ESC/Enter para terminar): ");
                        ppo.AllowNone = true;
                        PromptPointResult ppr = ed.GetPoint(ppo);
                        if (ppr.Status != PromptStatus.OK) break;

                        DBPoint p = new DBPoint(ppr.Value);
                        ms.AppendEntity(p);
                        tr.AddNewlyCreatedDBObject(p, true);
                        count++;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ {count} punto(s) AutoCAD creados.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // 2) COGOPOINTS de Civil 3D  (API real: CogoPointCollection)
        //    Modos: marcar en pantalla, o leer un CSV (X,Y,Z[,Descripcion])
        // =====================================================================
        [CommandMethod("CREAR_COGOPOINTS")]
        public void CrearCogoPoints()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Origen de los puntos
            PromptKeywordOptions pko = new PromptKeywordOptions(
                "\nOrigen de los CogoPoints: [Pantalla/CSV] <Pantalla>:", "Pantalla CSV");
            pko.AllowNone = true;
            PromptResult rko = ed.GetKeywords(pko);
            if (rko.Status != PromptStatus.OK && rko.Status != PromptStatus.None) return;
            string origen = (rko.Status == PromptStatus.OK) ? rko.StringResult : "Pantalla";

            // Recolectamos (ubicacion, descripcion) antes de crear
            var entradas = new List<(Point3d loc, string desc)>();

            if (origen.Equals("CSV", StringComparison.OrdinalIgnoreCase))
            {
                PromptOpenFileOptions pfo = new PromptOpenFileOptions(
                    "\nSeleccione CSV (X,Y,Z[,Descripcion]):");
                pfo.Filter = "CSV (*.csv)|*.csv|Todos (*.*)|*.*";
                PromptFileNameResult pfr = ed.GetFileNameForOpen(pfo);
                if (pfr.Status != PromptStatus.OK) return;

                foreach (string ln in System.IO.File.ReadAllLines(pfr.StringResult))
                {
                    if (string.IsNullOrWhiteSpace(ln)) continue;
                    string[] c = ln.Split(',');
                    if (c.Length < 3) continue;
                    if (double.TryParse(c[0].Trim(), out double x) &&
                        double.TryParse(c[1].Trim(), out double y) &&
                        double.TryParse(c[2].Trim(), out double z))
                    {
                        string desc = c.Length > 3 ? c[3].Trim() : "";
                        entradas.Add((new Point3d(x, y, z), desc));
                    }
                }
            }
            else // Pantalla
            {
                while (true)
                {
                    PromptPointOptions ppo = new PromptPointOptions(
                        "\nUbicación del CogoPoint (ESC/Enter para terminar): ");
                    ppo.AllowNone = true;
                    PromptPointResult ppr = ed.GetPoint(ppo);
                    if (ppr.Status != PromptStatus.OK) break;

                    PromptStringOptions pso = new PromptStringOptions("\nDescripción (Enter = vacío): ");
                    pso.AllowSpaces = true;
                    PromptResult pdr = ed.GetString(pso);
                    string desc = (pdr.Status == PromptStatus.OK) ? pdr.StringResult : "";

                    entradas.Add((ppr.Value, desc));
                }
            }

            if (entradas.Count == 0)
            {
                ed.WriteMessage("\nNo se ingresaron puntos.");
                return;
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // >>> API REAL de Civil 3D: la colección de CogoPoints del documento
                    CivilDB.CogoPointCollection cogoPoints = civilDoc.CogoPoints;

                    int creados = 0;
                    foreach (var e in entradas)
                    {
                        // Firma real (Civil 3D 2024): Add(ubicacion, descripcion, usarNumeracionAutomatica)
                        // Fija la descripción en la misma llamada; devuelve el ObjectId del CogoPoint.
                        cogoPoints.Add(e.loc, e.desc ?? string.Empty, true);
                        creados++;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ {creados} CogoPoint(s) creados.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // 3) ALINEAMIENTO real desde una polilínea  (Alignment.CreateFromPolyline)
        //    Reemplaza al stub CREAR_ALIG que solo escribía mensajes.
        // =====================================================================
        [CommandMethod("CREAR_ALIG_REAL")]
        public void CrearAlineamientoReal()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Seleccionar una polilínea (2D o 3D) como base
            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione una polilínea para el Alignment:");
            peo.SetRejectMessage("\nDebe ser una polilínea.");
            peo.AddAllowedClass(typeof(Polyline), false);
            peo.AddAllowedClass(typeof(Polyline2d), false);
            peo.AddAllowedClass(typeof(Polyline3d), false);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            // Nombre del alineamiento
            PromptStringOptions pso = new PromptStringOptions("\nNombre del Alignment:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Estilos: tomamos el primero disponible del documento.
                    // (Si no hay estilos, esto lanza excepción -> crea al menos uno en la plantilla.)
                    ObjectId styleId = civilDoc.Styles.AlignmentStyles[0];
                    ObjectId labelSetId = civilDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0];

                    // >>> API REAL (Civil 3D 2024): la creación desde polilínea se hace
                    // con Alignment.Create(...) pasando una struct PolylineOptions.
                    CivilDB.PolylineOptions plineOpts = new CivilDB.PolylineOptions
                    {
                        PlineId = per.ObjectId,          // la polilínea seleccionada
                        AddCurvesBetweenTangents = false, // no insertar curvas entre tangentes
                        EraseExistingEntities = false     // no borrar la polilínea original
                    };

                    // Create(document, plineOptions, nombre, siteId, layerId, styleId, labelSetId)
                    ObjectId alignId = CivilDB.Alignment.Create(
                        civilDoc,
                        plineOpts,
                        nombre,
                        ObjectId.Null,        // sin Site (alignment "siteless")
                        db.Clayer,            // capa actual
                        styleId,
                        labelSetId);

                    // Elegir el sentido del flujo del eje (el eje nace en el sentido de la polilínea)
                    PromptKeywordOptions pkDir = new PromptKeywordOptions(
                        "\nSentido del eje: [Mantener/Invertir] <Mantener>:", "Mantener Invertir");
                    pkDir.AllowNone = true;
                    PromptResult rDir = ed.GetKeywords(pkDir);
                    if (rDir.Status == PromptStatus.OK && rDir.StringResult == "Invertir")
                    {
                        CivilDB.Alignment al = (CivilDB.Alignment)tr.GetObject(alignId, OpenMode.ForWrite);
                        al.Reverse();
                        ed.WriteMessage("\n  Sentido del eje invertido.");
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Alignment '{nombre}' creado (Id: {alignId}).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // 4) SUPERFICIE TIN  (TinSurface)
        //    Origen: CogoPoints  ó  Polilíneas (2D / 2D-poly / 3D).
        //    Las polilíneas se pueden usar como VÉRTICES o como BREAKLINES.
        //    Nota: las polilíneas 3D son la mejor fuente (cada vértice lleva Z).
        // =====================================================================
        [CommandMethod("CREAR_SUPERFICIE")]
        public void CrearSuperficie()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Nombre de la superficie
            PromptStringOptions pso = new PromptStringOptions("\nNombre de la superficie:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // Origen de los datos
            PromptKeywordOptions pko = new PromptKeywordOptions(
                "\nOrigen de datos: [CogoPoints/Polilineas] <CogoPoints>:", "CogoPoints Polilineas");
            pko.AllowNone = true;
            PromptResult rko = ed.GetKeywords(pko);
            if (rko.Status != PromptStatus.OK && rko.Status != PromptStatus.None) return;
            string origen = (rko.Status == PromptStatus.OK) ? rko.StringResult : "CogoPoints";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Crear la superficie TIN (usa el estilo de superficie por defecto)
                    ObjectId surfaceId = CivilDB.TinSurface.Create(db, nombre);
                    CivilDB.TinSurface surface = (CivilDB.TinSurface)tr.GetObject(surfaceId, OpenMode.ForWrite);

                    if (origen.Equals("CogoPoints", StringComparison.OrdinalIgnoreCase))
                    {
                        // Todos los CogoPoints -> vértices de la superficie
                        Point3dCollection pts = new Point3dCollection();
                        foreach (ObjectId cid in civilDoc.CogoPoints)
                        {
                            CivilDB.CogoPoint cp = tr.GetObject(cid, OpenMode.ForRead) as CivilDB.CogoPoint;
                            if (cp != null) pts.Add(new Point3d(cp.Easting, cp.Northing, cp.Elevation));
                        }
                        if (pts.Count < 3) { ed.WriteMessage("\nSe necesitan al menos 3 CogoPoints."); tr.Abort(); return; }

                        surface.AddVertices(pts);
                        ed.WriteMessage($"\n✓ Superficie '{nombre}' creada con {pts.Count} CogoPoints.");
                    }
                    else // Polilíneas
                    {
                        // Seleccionar polilíneas (LWPOLYLINE = 2D ligera, POLYLINE = 2D-poly y 3D)
                        PromptSelectionOptions selOpts = new PromptSelectionOptions();
                        selOpts.MessageForAdding = "\nSeleccione polilíneas (2D/3D) y pulse Enter:";
                        TypedValue[] filtro = { new TypedValue((int)DxfCode.Start, "LWPOLYLINE,POLYLINE") };
                        PromptSelectionResult selRes = ed.GetSelection(selOpts, new SelectionFilter(filtro));
                        if (selRes.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); tr.Abort(); return; }
                        ObjectId[] ids = selRes.Value.GetObjectIds();

                        // ¿Cómo interpretar las polilíneas?
                        //   Contornos  = curvas de nivel (lo correcto para topografía)
                        //   Breaklines = líneas de quiebre (bordillos, cunetas...)
                        //   Vertices   = usar sus vértices como puntos sueltos
                        PromptKeywordOptions pmk = new PromptKeywordOptions(
                            "\nUsar polilíneas como: [Contornos/Breaklines/Vertices] <Contornos>:", "Contornos Breaklines Vertices");
                        pmk.AllowNone = true;
                        PromptResult rmk = ed.GetKeywords(pmk);
                        string modo = (rmk.Status == PromptStatus.OK) ? rmk.StringResult : "Contornos";

                        if (modo.Equals("Contornos", StringComparison.OrdinalIgnoreCase))
                        {
                            // Método correcto para curvas de nivel. Requiere que las curvas tengan Z real.
                            // Parámetros: midOrdinate, maxDistance, weedingDistance, weedingAngle (0 = sin filtrar)
                            ObjectIdCollection col = new ObjectIdCollection(ids);
                            surface.ContoursDefinition.AddContours(col, 1.0, 0.0, 0.0, 0.0);
                            ed.WriteMessage($"\n✓ Superficie '{nombre}' creada con {col.Count} curva(s) de nivel.");
                        }
                        else if (modo.Equals("Breaklines", StringComparison.OrdinalIgnoreCase))
                        {
                            // Civil 3D extrae la geometría de las polilíneas él mismo.
                            // Parámetros: midOrdinate, maxDistance, weedingDistance, weedingAngle (0 = sin filtrar)
                            ObjectIdCollection col = new ObjectIdCollection(ids);
                            surface.BreaklinesDefinition.AddStandardBreaklines(col, 1.0, 0.0, 0.0, 0.0);
                            ed.WriteMessage($"\n✓ Superficie '{nombre}' creada con {col.Count} polilínea(s) como breaklines.");
                        }
                        else // Vértices
                        {
                            Point3dCollection pts = new Point3dCollection();
                            foreach (ObjectId id in ids)
                            {
                                DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                                if (obj is Polyline lw)                 // polilínea 2D ligera (Z = elevación única)
                                {
                                    for (int i = 0; i < lw.NumberOfVertices; i++)
                                        pts.Add(lw.GetPoint3dAt(i));
                                }
                                else if (obj is Polyline3d p3)          // polilínea 3D (Z real por vértice)
                                {
                                    foreach (ObjectId vId in p3)
                                    {
                                        PolylineVertex3d v = tr.GetObject(vId, OpenMode.ForRead) as PolylineVertex3d;
                                        if (v != null) pts.Add(v.Position);
                                    }
                                }
                                else if (obj is Polyline2d p2)          // polilínea 2D "pesada"
                                {
                                    foreach (ObjectId vId in p2)
                                    {
                                        Vertex2d v = tr.GetObject(vId, OpenMode.ForRead) as Vertex2d;
                                        if (v != null) pts.Add(v.Position);
                                    }
                                }
                            }
                            if (pts.Count < 3) { ed.WriteMessage("\nNo se extrajeron suficientes vértices (mínimo 3)."); tr.Abort(); return; }

                            surface.AddVertices(pts);
                            ed.WriteMessage($"\n✓ Superficie '{nombre}' creada con {pts.Count} vértices de polilíneas.");
                        }
                    }

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
        // DIAGNÓSTICO: qué hay en el dibujo y si sirve para crear superficie.
        // Reporta tipos de entidad, capas y — lo más importante — el RANGO DE Z
        // de los vértices de las polilíneas. Si Zmin ≈ Zmax ≈ 0, las curvas son
        // planas (cota solo como texto) y NO sirven directamente.
        // =====================================================================
        [CommandMethod("DIAG_ENTIDADES")]
        public void DiagnosticoEntidades()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            int nLw = 0, nP2 = 0, nP3 = 0, nLine = 0, nPoint = 0, nOtros = 0;
            double zMin = double.MaxValue, zMax = double.MinValue;
            int vertsConZ = 0, vertsTotal = 0;
            var capas = new HashSet<string>();

            void Track(double z) { vertsTotal++; if (Math.Abs(z) > 1e-6) vertsConZ++; if (z < zMin) zMin = z; if (z > zMax) zMax = z; }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                foreach (ObjectId id in ms)
                {
                    DBObject obj = tr.GetObject(id, OpenMode.ForRead);
                    if (obj is Polyline lw)
                    {
                        nLw++; capas.Add(lw.Layer);
                        for (int i = 0; i < lw.NumberOfVertices; i++) Track(lw.GetPoint3dAt(i).Z);
                    }
                    else if (obj is Polyline3d p3)
                    {
                        nP3++; capas.Add(p3.Layer);
                        foreach (ObjectId vId in p3)
                        {
                            PolylineVertex3d v = tr.GetObject(vId, OpenMode.ForRead) as PolylineVertex3d;
                            if (v != null) Track(v.Position.Z);
                        }
                    }
                    else if (obj is Polyline2d p2)
                    {
                        nP2++; capas.Add(p2.Layer);
                        foreach (ObjectId vId in p2)
                        {
                            Vertex2d v = tr.GetObject(vId, OpenMode.ForRead) as Vertex2d;
                            if (v != null) Track(v.Position.Z);
                        }
                    }
                    else if (obj is Line) nLine++;
                    else if (obj is DBPoint) nPoint++;
                    else nOtros++;
                }
                tr.Commit();
            }

            int nCogo = 0;
            try { nCogo = (int)civilDoc.CogoPoints.Count; } catch { }

            ed.WriteMessage("\n================ DIAGNÓSTICO DEL DIBUJO ================");
            ed.WriteMessage($"\n  CogoPoints (Civil 3D): {nCogo}");
            ed.WriteMessage($"\n  Polilíneas 2D ligeras (LWPOLYLINE): {nLw}");
            ed.WriteMessage($"\n  Polilíneas 2D pesadas (POLYLINE 2D): {nP2}");
            ed.WriteMessage($"\n  Polilíneas 3D (POLYLINE 3D): {nP3}");
            ed.WriteMessage($"\n  Líneas / Puntos AutoCAD / Otros: {nLine} / {nPoint} / {nOtros}");
            ed.WriteMessage($"\n  Capas de polilíneas: {(capas.Count > 0 ? string.Join(", ", capas) : "(ninguna)")}");
            if (vertsTotal > 0)
            {
                ed.WriteMessage($"\n  Vértices de polilíneas: {vertsTotal}  (con Z≠0: {vertsConZ})");
                ed.WriteMessage($"\n  Rango de elevación Z: {zMin:F3}  a  {zMax:F3}");
                bool planas = (zMax - zMin) < 0.001;
                ed.WriteMessage(planas
                    ? "\n  >>> ⚠ Las polilíneas son PLANAS (sin Z). NO sirven directas para superficie; hay que asignarles elevación primero."
                    : "\n  >>> ✓ Las polilíneas TIENEN elevación 3D. Sirven para CREAR_SUPERFICIE (usa modo Contornos).");
            }
            else ed.WriteMessage("\n  No se encontraron polilíneas en ModelSpace.");
            ed.WriteMessage("\n========================================================");
        }

        // =====================================================================
        // UNIR_CURVAS — reconecta tramos de una misma curva de nivel partida por
        // el número (el hueco de la etiqueta). Solo une extremos que son COLINEALES
        // (se apuntan entre sí a través del hueco), para no fusionar por error dos
        // curvas distintas que pasen cerca. v1: ajustar 'gap' y 'ángulo' si hace falta.
        // =====================================================================
        private class Seg { public ObjectId Id; public List<Point3d> Pts; public string Layer; }

        [CommandMethod("UNIR_CURVAS")]
        public void UnirCurvas()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            // Selección de polilíneas (LWPOLYLINE)
            PromptSelectionOptions selOpts = new PromptSelectionOptions();
            selOpts.MessageForAdding = "\nSeleccione las curvas a unir (polilíneas 2D) y pulse Enter:";
            TypedValue[] filtro = { new TypedValue((int)DxfCode.Start, "LWPOLYLINE") };
            PromptSelectionResult selRes = ed.GetSelection(selOpts, new SelectionFilter(filtro));
            if (selRes.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección cancelada."); return; }

            // Distancia máxima del hueco a puentear
            PromptDoubleOptions pgo = new PromptDoubleOptions("\nDistancia máxima del hueco del número a puentear (m):");
            pgo.AllowNegative = false; pgo.AllowZero = false; pgo.DefaultValue = 5.0; pgo.UseDefaultValue = true;
            PromptDoubleResult pgr = ed.GetDouble(pgo);
            if (pgr.Status != PromptStatus.OK) return;
            double maxGap = pgr.Value;

            // Tolerancia angular de colinealidad
            PromptDoubleOptions pao = new PromptDoubleOptions("\nTolerancia angular de colinealidad (grados):");
            pao.AllowNegative = false; pao.AllowZero = false; pao.DefaultValue = 20.0; pao.UseDefaultValue = true;
            PromptDoubleResult par = ed.GetDouble(pao);
            if (par.Status != PromptStatus.OK) return;
            double cosTol = Math.Cos(par.Value * Math.PI / 180.0);

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Cargar segmentos abiertos
                    var segs = new List<Seg>();
                    foreach (ObjectId id in selRes.Value.GetObjectIds())
                    {
                        Polyline pl = tr.GetObject(id, OpenMode.ForRead) as Polyline;
                        if (pl == null || pl.Closed || pl.NumberOfVertices < 2) continue;
                        var pts = new List<Point3d>();
                        for (int i = 0; i < pl.NumberOfVertices; i++) pts.Add(pl.GetPoint3dAt(i));
                        segs.Add(new Seg { Id = id, Pts = pts, Layer = pl.Layer });
                    }
                    int nEntrada = segs.Count;
                    if (nEntrada < 2) { ed.WriteMessage("\nNada que unir (menos de 2 polilíneas abiertas)."); tr.Abort(); return; }

                    // Dirección saliente 2D en un extremo (side: 0=inicio, 1=fin)
                    double[] Dir(Seg s, int side)
                    {
                        Point3d a, b;
                        if (side == 0) { a = s.Pts[0]; b = s.Pts[1]; }
                        else { a = s.Pts[s.Pts.Count - 1]; b = s.Pts[s.Pts.Count - 2]; }
                        double dx = a.X - b.X, dy = a.Y - b.Y;
                        double L = Math.Sqrt(dx * dx + dy * dy);
                        return L < 1e-9 ? new[] { 0.0, 0.0 } : new[] { dx / L, dy / L };
                    }
                    Point3d Pt(Seg s, int side) => side == 0 ? s.Pts[0] : s.Pts[s.Pts.Count - 1];

                    // Emparejar extremos: end index = seg*2 + side
                    int E = segs.Count * 2;
                    int[] partner = new int[E];
                    for (int i = 0; i < E; i++) partner[i] = -1;

                    // Candidatos (dist, e1, e2) ordenados por distancia
                    var cand = new List<(double d, int e1, int e2)>();
                    for (int i = 0; i < E; i++)
                    {
                        int si = i / 2, sd = i % 2;
                        var pi = Pt(segs[si], sd); var di = Dir(segs[si], sd);
                        for (int j = i + 1; j < E; j++)
                        {
                            int sj = j / 2, sdj = j % 2;
                            if (sj == si) continue; // no unir un tramo consigo mismo
                            var pj = Pt(segs[sj], sdj); var dj = Dir(segs[sj], sdj);
                            double vx = pj.X - pi.X, vy = pj.Y - pi.Y;
                            double dist = Math.Sqrt(vx * vx + vy * vy);
                            if (dist < 1e-9 || dist > maxGap) continue;
                            double nvx = vx / dist, nvy = vy / dist;
                            // di apunta hacia j (v) y dj apunta hacia i (-v)
                            double dotI = di[0] * nvx + di[1] * nvy;
                            double dotJ = dj[0] * (-nvx) + dj[1] * (-nvy);
                            if (dotI >= cosTol && dotJ >= cosTol) cand.Add((dist, i, j));
                        }
                    }
                    cand.Sort((x, y) => x.d.CompareTo(y.d));
                    foreach (var c in cand)
                        if (partner[c.e1] == -1 && partner[c.e2] == -1) { partner[c.e1] = c.e2; partner[c.e2] = c.e1; }

                    // Construir cadenas y crear polilíneas unidas
                    BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                    BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);

                    bool[] used = new bool[segs.Count];
                    int cadenas = 0, unidas = 0;

                    for (int start = 0; start < segs.Count; start++)
                    {
                        if (used[start]) continue;
                        // empezar por un extremo terminal (sin pareja) del segmento
                        int startSide = partner[start * 2] == -1 ? 0 : (partner[start * 2 + 1] == -1 ? 1 : 0);

                        var chain = new List<Point3d>();      // puntos ordenados de la cadena
                        var chainSegs = new List<int>();       // segmentos que la forman
                        int curSeg = start, entrySide = startSide;
                        while (true)
                        {
                            used[curSeg] = true; chainSegs.Add(curSeg);
                            var pts = segs[curSeg].Pts;
                            if (entrySide == 0) chain.AddRange(pts);                          // inicio->fin
                            else { var r = new List<Point3d>(pts); r.Reverse(); chain.AddRange(r); } // fin->inicio
                            int exitSide = entrySide == 0 ? 1 : 0;
                            int p = partner[curSeg * 2 + exitSide];
                            if (p == -1) break;
                            int nextSeg = p / 2, nextEntry = p % 2;
                            if (used[nextSeg]) break;
                            curSeg = nextSeg; entrySide = nextEntry;
                        }

                        if (chainSegs.Count < 2) continue; // segmento aislado: se deja tal cual

                        // crear polilínea unida (plana, Z=0) en la misma capa
                        Polyline np = new Polyline();
                        for (int i = 0; i < chain.Count; i++)
                            np.AddVertexAt(i, new Point2d(chain[i].X, chain[i].Y), 0, 0, 0);
                        np.Layer = segs[start].Layer;
                        ms.AppendEntity(np);
                        tr.AddNewlyCreatedDBObject(np, true);
                        cadenas++; unidas += chainSegs.Count;

                        // borrar los tramos originales que se fusionaron
                        foreach (int s in chainSegs)
                        {
                            Entity e = tr.GetObject(segs[s].Id, OpenMode.ForWrite) as Entity;
                            e?.Erase();
                        }
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ UNIR_CURVAS: {nEntrada} polilíneas de entrada -> {cadenas} curva(s) unida(s) a partir de {unidas} tramos. Sin pareja: {nEntrada - unidas}.");
                    ed.WriteMessage("\n  (Si unió de más o de menos, reejecuta ajustando la distancia de hueco / tolerancia angular.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // ELEVAR_CURVAS_POR_TEXTO — asigna a cada curva la cota de su texto más
        // cercano (Paso 2 del pipeline de curvas). Setea Elevation en la LWPolyline.
        // Selección: primero las curvas, luego los textos de cota.
        // =====================================================================
        [CommandMethod("ELEVAR_CURVAS_POR_TEXTO")]
        public void ElevarCurvasPorTexto()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            // 1) Curvas a elevar
            PromptSelectionOptions so1 = new PromptSelectionOptions();
            so1.MessageForAdding = "\nSeleccione las CURVAS (polilíneas) a elevar y pulse Enter:";
            SelectionFilter f1 = new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "LWPOLYLINE") });
            PromptSelectionResult r1 = ed.GetSelection(so1, f1);
            if (r1.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección de curvas cancelada."); return; }

            // 2) Textos de cota
            PromptSelectionOptions so2 = new PromptSelectionOptions();
            so2.MessageForAdding = "\nSeleccione los TEXTOS de cota y pulse Enter:";
            SelectionFilter f2 = new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "TEXT,MTEXT") });
            PromptSelectionResult r2 = ed.GetSelection(so2, f2);
            if (r2.Status != PromptStatus.OK) { ed.WriteMessage("\nSelección de textos cancelada."); return; }

            // 3) Distancia máxima texto-curva (evita asignar un texto lejano a una curva equivocada)
            PromptDoubleOptions pdo = new PromptDoubleOptions("\nDistancia máxima texto-curva (m):");
            pdo.AllowNegative = false; pdo.AllowZero = false; pdo.DefaultValue = 10.0; pdo.UseDefaultValue = true;
            PromptDoubleResult pdr = ed.GetDouble(pdo);
            if (pdr.Status != PromptStatus.OK) return;
            double maxDist = pdr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Cargar curvas candidatas
                    var curvas = new List<(ObjectId id, Polyline pl)>();
                    foreach (ObjectId id in r1.Value.GetObjectIds())
                    {
                        Polyline pl = tr.GetObject(id, OpenMode.ForRead) as Polyline;
                        if (pl != null) curvas.Add((id, pl));
                    }
                    if (curvas.Count == 0) { ed.WriteMessage("\nNo hay curvas válidas."); tr.Abort(); return; }

                    var asignado = new Dictionary<ObjectId, double>();
                    int textosOk = 0, sinCurva = 0, noNumero = 0, conflictos = 0;

                    foreach (ObjectId id in r2.Value.GetObjectIds())
                    {
                        DBObject o = tr.GetObject(id, OpenMode.ForRead);

                        // Valor de cota del texto
                        string s = (o is DBText t) ? t.TextString : (o is MText m) ? m.Text : null;
                        if (s == null) continue;
                        if (!TryParseCota(s, out double cota)) { noNumero++; continue; }

                        // Punto del texto = centro de su bounding box (robusto ante justificación)
                        Point3d tp;
                        try { Extents3d ex = ((Entity)o).GeometricExtents; tp = new Point3d((ex.MinPoint.X + ex.MaxPoint.X) / 2, (ex.MinPoint.Y + ex.MaxPoint.Y) / 2, 0); }
                        catch { continue; }

                        // Curva más cercana (distancia 2D del punto a la polilínea)
                        double best = double.MaxValue; ObjectId bestId = ObjectId.Null;
                        foreach (var c in curvas)
                        {
                            Point3d cp;
                            try { cp = c.pl.GetClosestPointTo(tp, false); }
                            catch { continue; }
                            double dx = cp.X - tp.X, dy = cp.Y - tp.Y;
                            double d = Math.Sqrt(dx * dx + dy * dy);
                            if (d < best) { best = d; bestId = c.id; }
                        }

                        if (bestId == ObjectId.Null || best > maxDist) { sinCurva++; continue; }
                        if (asignado.TryGetValue(bestId, out double prev) && Math.Abs(prev - cota) > 1e-6) conflictos++;
                        asignado[bestId] = cota;
                        textosOk++;
                    }

                    // Aplicar elevación
                    double zmin = double.MaxValue, zmax = double.MinValue;
                    foreach (var kv in asignado)
                    {
                        Polyline pl = tr.GetObject(kv.Key, OpenMode.ForWrite) as Polyline;
                        if (pl == null) continue;
                        pl.Elevation = kv.Value;
                        if (kv.Value < zmin) zmin = kv.Value;
                        if (kv.Value > zmax) zmax = kv.Value;
                    }

                    tr.Commit();

                    ed.WriteMessage("\n============== ELEVAR CURVAS POR TEXTO ==============");
                    ed.WriteMessage($"\n  Curvas seleccionadas: {curvas.Count}");
                    ed.WriteMessage($"\n  Curvas elevadas: {asignado.Count}");
                    if (asignado.Count > 0) ed.WriteMessage($"\n  Rango de cotas asignadas: {zmin:F3} a {zmax:F3}");
                    ed.WriteMessage($"\n  Textos aplicados: {textosOk}  |  sin curva cercana: {sinCurva}  |  no numéricos: {noNumero}  |  conflictos: {conflictos}");
                    ed.WriteMessage($"\n  Curvas sin cota (quedan en 0): {curvas.Count - asignado.Count}");
                    ed.WriteMessage("\n====================================================");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // Extrae el primer número de un texto de cota (admite coma o punto decimal).
        private static bool TryParseCota(string s, out double value)
        {
            value = 0;
            if (string.IsNullOrWhiteSpace(s)) return false;
            Match mm = Regex.Match(s, @"-?\d+(?:[.,]\d+)?");
            if (!mm.Success) return false;
            string num = mm.Value.Replace(',', '.');
            return double.TryParse(num, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }
    }
}
