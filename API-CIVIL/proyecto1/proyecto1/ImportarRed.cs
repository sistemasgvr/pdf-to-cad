using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  IMPORTAR_RED — crea redes COMPLETAS de Civil 3D desde un DXF exportado
//  por la app Python (pdf-to-cad). Un solo click produce:
//    1. Escanear XDATA del DXF
//    2. Auto-detectar superficie de referencia
//    3. Auto-poblar Parts List con familias/tamaños del catálogo si faltan
//    4. Crear redes de gravedad (buzones + tuberías conectadas)
//    5. Crear redes de presión (tuberías + fittings en cambios de dirección)
//    6. Conectar tuberías a presión en vértices compartidos
//    7. Diagnosticar la red creada (pendiente, rim/sump, diámetros)
//    8. Reporte completo
//
//  XDATA esperado (AppName "PDFCAD"):
//    Polilínea (tubería):
//      PDFCAD_PIPE, DIAMETER, UNIT, MATERIAL, NET_KIND, NET_TYPE,
//      INV_START, INV_END, MANNINGS_N, COVER_MIN
//    Punto (buzón, capa PDFCAD_BZ):
//      PDFCAD_STRUCT, STRUCT_ID, RIM, SUMP, PART
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        // Log de depuración exhaustivo del flujo de asignación de familias/tamaños
        // a los buzones. Se vuelca a un CSV en Descargas al final de IMPORTAR_RED.
        private static readonly List<string> _dbg = new List<string>();
        private static void Dbg(string tag, params (string k, object v)[] fields)
        {
            var sb = new System.Text.StringBuilder(tag);
            foreach (var (k, v) in fields)
            {
                var s = (v ?? "").ToString().Replace(",", ";").Replace("\r", " ").Replace("\n", " ");
                sb.Append(",").Append(k).Append("=").Append(s);
            }
            _dbg.Add(sb.ToString());
        }

        [CommandMethod("IMPORTAR_RED")]
        public void ImportarRed()
        {
            _dbg.Clear();
            Dbg("IMPORTAR_RED_INICIO", ("timestamp", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")));
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // ── 0. Forzar unidades imperiales (pies) antes de leer cotas ────
            ComandosUnidades.ForzarImperial(db, ed, true);

            // ── 1. Escanear modelspace ──────────────────────────────────────
            var pipes = new List<ImportPipe>();
            var structs = new List<ImportStruct>();

            using (Transaction trScan = db.TransactionManager.StartTransaction())
            {
                BlockTableRecord ms = (BlockTableRecord)trScan.GetObject(
                    SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);

                foreach (ObjectId eid in ms)
                {
                    Entity ent = trScan.GetObject(eid, OpenMode.ForRead) as Entity;
                    if (ent == null) continue;
                    var xd = LeerXdataPdfcad(ent);
                    if (xd == null) continue;

                    string marker;
                    xd.TryGetValue("_MARKER", out marker);

                    if (marker == "PDFCAD_PIPE" && ent is Polyline poly)
                    {
                        var verts = new List<Point2d>();
                        for (int i = 0; i < poly.NumberOfVertices; i++)
                            verts.Add(poly.GetPoint2dAt(i));
                        if (verts.Count < 2) continue;

                        string srcUnit = XdStr(xd, "UNIT", "ft");
                        double k = FactorConversion(srcUnit, db);

                        pipes.Add(new ImportPipe
                        {
                            Layer = poly.Layer,
                            Vertices = verts,
                            Diameter = XdDouble(xd, "DIAMETER"),
                            Unit = srcUnit,
                            Material = XdStr(xd, "MATERIAL", ""),
                            NetKind = XdStr(xd, "NET_KIND", "gravity"),
                            NetType = XdStr(xd, "NET_TYPE", "pipe"),
                            InvStart = MulNull(XdNullDouble(xd, "INV_START"), k),
                            InvEnd = MulNull(XdNullDouble(xd, "INV_END"), k),
                            ManningsN = XdDouble(xd, "MANNINGS_N"),
                            CoverMin = XdDouble(xd, "COVER_MIN") * k,
                            PipeFamily = XdStr(xd, "PIPE_FAMILY", ""),
                            PipeSize = XdStr(xd, "PIPE_SIZE", ""),
                        });
                    }
                    else if (marker == "PDFCAD_STRUCT" && ent is DBPoint pt)
                    {
                        // Los STRUCT no traen UNIT en el XDATA; asumo la misma que las tuberías
                        double k = pipes.Count > 0 ? FactorConversion(pipes[0].Unit, db) : 1.0;
                        var newSt = new ImportStruct
                        {
                            Location = new Point2d(pt.Position.X, pt.Position.Y),
                            Id = XdStr(xd, "STRUCT_ID", ""),
                            Rim = MulNull(XdNullDouble(xd, "RIM"), k),
                            Sump = MulNull(XdNullDouble(xd, "SUMP"), k),
                            Part = XdStr(xd, "PART", ""),
                            PartSize = XdStr(xd, "PART_SIZE", ""),
                            Covered = XdStr(xd, "COVERED", "1") != "0",
                            NetKind = XdStr(xd, "NET_KIND", "gravity"),
                        };
                        structs.Add(newSt);
                        Dbg("XDATA_STRUCT", ("id", newSt.Id), ("x", pt.Position.X.ToString("F3")),
                            ("y", pt.Position.Y.ToString("F3")), ("net", newSt.NetKind),
                            ("part", newSt.Part), ("part_size", newSt.PartSize),
                            ("covered", newSt.Covered ? "1" : "0"),
                            ("rim", newSt.Rim?.ToString("F3") ?? ""),
                            ("sump", newSt.Sump?.ToString("F3") ?? ""));
                    }
                }
                trScan.Commit();
            }

            if (pipes.Count == 0)
            {
                ed.WriteMessage("\nNo se encontraron polilíneas con XDATA 'PDFCAD'. " +
                                "¿Es un DXF exportado desde la app de marcado (pdf-to-cad)?");
                return;
            }

            string unit = pipes[0].Unit;
            double factor = FactorConversion(unit, db);
            ed.WriteMessage($"\n═══ IMPORTAR RED ═══");
            ed.WriteMessage($"\nDetectadas: {pipes.Count} tubería(s), {structs.Count} buzón(es). Unidad XDATA: {unit} · dibujo: {db.Insunits}.");
            if (Math.Abs(factor - 1.0) > 1e-9)
                ed.WriteMessage($"\n  → Conversión de elevaciones {unit} → {db.Insunits}: ×{factor:F4}");

            // ── 2. Agrupar por capa ─────────────────────────────────────────
            var gravedad = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);
            var presion = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);

            var conduit = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);
            foreach (var p in pipes)
            {
                if (p.NetKind.Equals("pressure", StringComparison.OrdinalIgnoreCase))
                    DictAdd(presion, p.Layer, p);
                else if (p.NetKind.Equals("conduit", StringComparison.OrdinalIgnoreCase))
                    DictAdd(conduit, p.Layer, p);        // eléctrico/telecom → red sin buzones
                else
                    DictAdd(gravedad, p.Layer, p);
            }

            // ── 3. Auto-detectar superficie (sin prompt) ────────────────────
            ObjectId surfId = ObjectId.Null;
            using (Transaction trSurf = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection surfIds = civilDoc.GetSurfaceIds();
                    foreach (ObjectId sid in surfIds)
                    {
                        if (trSurf.GetObject(sid, OpenMode.ForRead) is CivilDB.TinSurface)
                        { surfId = sid; break; }
                    }
                }
                catch { }
                trSurf.Commit();
            }
            if (surfId != ObjectId.Null)
                ed.WriteMessage("\nSuperficie de referencia detectada automáticamente.");

            // ── 3b. Verificar catálogo imperial ─────────────────────────────
            VerificarCatalogoImperial(ed);

            // Profundidad por defecto: del COVER_MIN del XDATA o 5.0
            double defaultDepth = 5.0;
            if (pipes.Count > 0 && pipes[0].CoverMin > 0)
                defaultDepth = pipes[0].CoverMin;

            // Separar structures por red: gravedad (BZ-) y conduit (CAJA-).
            // Las de presión se descartan (agua/gas no llevan nodos automáticos).
            var structsGravedad = new List<ImportStruct>();
            var structsConduit = new List<ImportStruct>();
            int nDescartadas = 0;
            foreach (var s in structs)
            {
                string nk = (s.NetKind ?? "").ToLowerInvariant();
                if (nk == "" || nk == "gravity") structsGravedad.Add(s);
                else if (nk == "conduit") structsConduit.Add(s);
                else nDescartadas++;
            }
            if (nDescartadas > 0)
                ed.WriteMessage($"\n(Se descartaron {nDescartadas} nodo(s) de presión — solo gravedad y conduit llevan nodos.)");

            // ── 4. Redes de GRAVEDAD ────────────────────────────────────────
            var createdNetIds = new List<ObjectId>();
            foreach (var kv in gravedad)
            {
                string netName = $"RED-{kv.Key}";
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        ObjectId netId = CrearRedGravedadCompleta(ed, db, civilDoc, tr,
                            netName, surfId, defaultDepth, kv.Value, structsGravedad);
                        if (netId != ObjectId.Null) createdNetIds.Add(netId);
                        tr.Commit();
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n✗ Error red gravedad '{netName}': {ex.Message}");
                        tr.Abort();
                    }
                }
            }

            // ── 4b. Redes de CONDUIT (eléctrico/telecom) — pipe network sin buzones ──
            foreach (var kv in conduit)
            {
                string netName = $"RED-{kv.Key}";
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        ObjectId netId = CrearRedGravedadCompleta(ed, db, civilDoc, tr,
                            netName, surfId, defaultDepth, kv.Value,
                            structsConduit, sinBuzones: true);
                        if (netId != ObjectId.Null) createdNetIds.Add(netId);
                        tr.Commit();
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n✗ Error red conduit '{netName}': {ex.Message}");
                        tr.Abort();
                    }
                }
            }

            // ── 5. Redes de PRESIÓN ─────────────────────────────────────────
            var createdPresIds = new List<ObjectId>();
            foreach (var kv in presion)
            {
                string netName = $"RED-{kv.Key}";
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        ObjectId pnId = CrearRedPresionCompleta(ed, db, civilDoc, tr, netName, surfId,
                            defaultDepth, kv.Value);
                        if (pnId != ObjectId.Null) createdPresIds.Add(pnId);
                        tr.Commit();
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n✗ Error red presión '{netName}': {ex.Message}");
                        tr.Abort();
                    }
                }
            }

            // ── 5b. Borrar polylines DXF que ya se convirtieron a Networks ──
            // Las polylines de gravedad y presión se transformaron en Pipe Networks
            // y en Pressure Networks; sus polylines XDATA=PDFCAD_PIPE originales
            // ya no aportan nada y solo generan ruido visual encima de las redes.
            // Conduit (eléctrico/telecom) SÍ se conservan porque no se convirtió a red.
            BorrarPolylinesConvertidas(ed, db);

            // ── 6. Diagnóstico inline ───────────────────────────────────────
            if (createdNetIds.Count > 0)
            {
                using (Transaction trDiag = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        DiagnosticarInline(ed, trDiag, createdNetIds);
                        trDiag.Commit();
                    }
                    catch { trDiag.Abort(); }
                }
            }

            // ── 7. Reporte CSV (para revisar cada elemento fuera de Civil) ───
            using (Transaction trRep = db.TransactionManager.StartTransaction())
            {
                try { EscribirReporteRed(ed, trRep, createdNetIds, createdPresIds); trRep.Commit(); }
                catch (Exception ex) { ed.WriteMessage($"\n(No se pudo escribir el reporte: {ex.Message})"); trRep.Abort(); }
            }

            // ── 8. Volcar log de depuración a CSV ───────────────────────────
            try
            {
                string dbgDir = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
                if (!System.IO.Directory.Exists(dbgDir))
                    dbgDir = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                string dbgPath = System.IO.Path.Combine(dbgDir, "IMPORTAR_RED_debug.csv");
                System.IO.File.WriteAllLines(dbgPath, _dbg, System.Text.Encoding.UTF8);
                ed.WriteMessage($"\n📋 Log de depuración: {dbgPath}  ({_dbg.Count} eventos)");
            }
            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo escribir log de depuración: {ex.Message})"); }

            ed.WriteMessage("\n═══ IMPORTAR RED — fin ═══");
        }

        // =================================================================
        //  RED DE GRAVEDAD COMPLETA (auto-populate + create + diagnostics)
        // =================================================================
        private ObjectId CrearRedGravedadCompleta(
            Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
            string nombre, ObjectId surfId, double defaultDepth,
            List<ImportPipe> pipes, List<ImportStruct> structs, bool sinBuzones = false)
        {
            PartsStyles.PartsList partsList = ObtenerPartsList(civilDoc, tr);
            if (partsList == null) { ed.WriteMessage("\nNo hay Parts Lists en el dibujo."); return ObjectId.Null; }

            // Si la Parts List no tiene un BUZÓN REAL (solo tiene la "Null Structure"),
            // se agrega uno cilíndrico con tapa concéntrica del catálogo imperial.
            // Sin esto, Civil crea una "Estructura nula" (Ø0) que en 3D se ve como esfera.
            // Para conduits (sinBuzones=true) NO agregamos buzón real — usaremos Null.
            if (!sinBuzones) AsegurarBuzonReal(ed, tr, partsList);

            // Log del estado del PartsList tras AsegurarBuzonReal
            foreach (ObjectId fidLog in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure))
            {
                var famLog = tr.GetObject(fidLog, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (famLog == null) continue;
                Dbg("PARTSLIST_STRUCT_FAM", ("red", nombre), ("descripcion", famLog.Description ?? ""),
                    ("sizes", famLog.PartSizeCount));
            }

            ObjectId defStructFam, defStructSize; string defStructNom;
            if (sinBuzones)
            {
                // Para conduit: usar la "Estructura nula" del template como default.
                // Es una estructura invisible tamaño 0 que sirve para "cerrar" las
                // pipes sin dibujar buzón real.
                defStructFam = ObjectId.Null; defStructSize = ObjectId.Null; defStructNom = "";
                foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure))
                {
                    var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                    if (fam == null || fam.PartSizeCount == 0) continue;
                    string d = fam.Description ?? "";
                    if (d.IndexOf("Null", StringComparison.OrdinalIgnoreCase) < 0 &&
                        d.IndexOf("nula", StringComparison.OrdinalIgnoreCase) < 0) continue;
                    defStructFam = fid; defStructSize = fam[0]; defStructNom = d;
                    break;
                }
                if (defStructFam == ObjectId.Null)
                {
                    // Sin Null Structure disponible: fallback a la primera real.
                    if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Structure,
                                      out defStructFam, out defStructSize, out defStructNom))
                    { ed.WriteMessage($"\n'{nombre}': sin familias de ESTRUCTURA."); return ObjectId.Null; }
                }
                ed.WriteMessage($"\n  · Red sin buzones (conduit) usando: {defStructNom}");
                Dbg("DEFAULT_STRUCT_CONDUIT", ("red", nombre), ("nom", defStructNom));
            }
            else
            {
                if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Structure,
                                  out defStructFam, out defStructSize, out defStructNom))
                { ed.WriteMessage($"\n'{nombre}': sin familias de ESTRUCTURA."); return ObjectId.Null; }
                ed.WriteMessage($"\n  · Buzón por defecto: {defStructNom}");
                Dbg("DEFAULT_STRUCT", ("red", nombre), ("nom", defStructNom));
            }

            // Familia para buzones "sin tapa" (Covered=0). Solo aplica en gravedad.
            bool haySinTapa = false;
            ObjectId defStructFamNoLid = ObjectId.Null, defStructSizeNoLid = ObjectId.Null;
            string defStructNomNoLid = "";
            if (!sinBuzones)
            {
                haySinTapa = BuscarFamiliaSinTapa(tr, partsList,
                    out defStructFamNoLid, out defStructSizeNoLid, out defStructNomNoLid);
                if (haySinTapa)
                    ed.WriteMessage($"\n  · Buzón sin tapa: {defStructNomNoLid}");
            }

            // Pre-scan: recolectar materiales/diámetros únicos y auto-poblar el catálogo
            var needed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var ip in pipes)
            {
                string key = $"{ip.Material}|{ip.Diameter:F0}";
                if (needed.Contains(key)) continue;
                needed.Add(key);
                string diamStr = ip.Diameter.ToString("F0");
                if (!BuscarTuberia(tr, partsList, ip.Material, diamStr,
                                   out _, out _, out _))
                {
                    AutoAgregarFamiliaCatalogo(ed, tr, partsList,
                        CivilDB.DomainType.Pipe, ip.Material);
                }
            }

            if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Pipe,
                              out ObjectId defPipeFam, out ObjectId defPipeSize, out string defPipeNom))
            { ed.WriteMessage($"\n'{nombre}': sin familias de TUBERÍA."); return ObjectId.Null; }

            // Crear la red
            string nm = nombre;
            ObjectId netId = CivilDB.Network.Create(civilDoc, ref nm);
            CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForWrite);
            net.PartsListId = partsList.ObjectId;
            if (surfId != ObjectId.Null) net.ReferenceSurfaceId = surfId;

            // Pre-scan: para cada Part único que llega del DXF (basename del .xml del catálogo
            // o nombre custom del modelador), agregarlo al PartsList si aún no está.
            var partsPedidos = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var st in structs)
            {
                if (!string.IsNullOrWhiteSpace(st.Part)) partsPedidos.Add(st.Part);
            }
            foreach (var pid in partsPedidos)
                AsegurarFamiliaPorId(ed, tr, partsList, pid);

            // Pre-scan de familias de TUBERÍA elegidas en Python (dominio Pipe).
            var pipesPedidas = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var ip2 in pipes)
            {
                if (!string.IsNullOrWhiteSpace(ip2.PipeFamily)) pipesPedidas.Add(ip2.PipeFamily);
            }
            foreach (var pid in pipesPedidas)
                AsegurarFamiliaPorId(ed, tr, partsList, pid, CivilDB.DomainType.Pipe);

            var createdStructs = new Dictionary<string, ObjectId>();
            int nPipes = 0;
            var trazaEje = new List<Point3d>();
            // Cotas EXPLÍCITAS a reponer al final. Civil 3D, al conectar tuberías
            // (ConnectToStructure), re-aplica reglas por defecto (pendiente ~1% +
            // tapada) y, si la estructura tiene el ajuste automático de superficie
            // activo, ignora el rim manual. Guardamos lo que el DXF trae y lo
            // volvemos a fijar DESPUÉS de crear/conectar todo.
            var explicitRimSump = new Dictionary<ObjectId, (double rim, double sump)>();
            var explicitPipeInv = new List<(ObjectId id, double zStart, double zEnd)>();

            foreach (var ip in pipes)
            {
                int nVerts = ip.Vertices.Count;
                double[] zVerts = InterpolateZ(ip, nVerts);
                for (int i = 0; i < nVerts; i++)
                    trazaEje.Add(new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zVerts[i]));

                // Prioridad para elegir familia+tamaño de esta pipe:
                //   1) PIPE_FAMILY del XDATA (elegida en Python del catálogo Civil 3D)
                //   2) BuscarTuberia por material + diámetro
                //   3) default
                string diamStr = !string.IsNullOrWhiteSpace(ip.PipeSize)
                    ? ip.PipeSize : ip.Diameter.ToString("F0");
                ObjectId pipeFam = ObjectId.Null, pipeSize = ObjectId.Null; string pipeNom = "";
                if (!string.IsNullOrWhiteSpace(ip.PipeFamily))
                {
                    // Se llama a BuscarTuberia con el catalogId como 'tipo' — el matcher
                    // ya sabe interpretar 'AeccCircular...' vía MatchCatalogId.
                    BuscarTuberia(tr, partsList, ip.PipeFamily, diamStr,
                                  out pipeFam, out pipeSize, out pipeNom);
                    Dbg("PIPE_FAMILY_MATCH", ("pedido", ip.PipeFamily), ("size", diamStr),
                        ("encontrada", pipeFam != ObjectId.Null ? "true" : "false"),
                        ("nombre", pipeNom));
                }
                if (pipeFam == ObjectId.Null)
                {
                    if (!BuscarTuberia(tr, partsList, ip.Material, diamStr,
                                       out pipeFam, out pipeSize, out pipeNom))
                    { pipeFam = defPipeFam; pipeSize = defPipeSize; pipeNom = defPipeNom; }
                }

                var vertStructIds = new List<ObjectId>();
                for (int i = 0; i < nVerts; i++)
                {
                    Point2d v = ip.Vertices[i];
                    double zInv = zVerts[i];
                    double depth = ip.CoverMin > 0 ? ip.CoverMin : defaultDepth;

                    ImportStruct match = FindNearestStruct(structs, v, 1.0);

                    double rim, sump;
                    string structType = match != null ? (match.Part ?? "") : "";  // ← siempre respeta la familia elegida
                    if (match != null && match.Rim.HasValue && match.Sump.HasValue)
                    { rim = match.Rim.Value; sump = match.Sump.Value; }
                    else
                    { sump = zInv - 0.5; rim = zInv + depth; }   // sump 0.5' bajo la solera; rim = invert + tapada
                    // Garantía: rim ARRIBA (mín. 1' sobre sump) y sump por debajo del invert.
                    if (rim - sump < 1.0) rim = sump + Math.Max(depth, 3.0);

                    string key = $"{Math.Round(v.X, 2)}_{Math.Round(v.Y, 2)}";
                    if (sinBuzones)
                    {
                        // Conduit: si el usuario asignó familia (match.Part != ""), se
                        // crea una CAJA real con esa familia (comportamiento cuasi-gravedad).
                        // Si NO hay familia asignada, no se crea structure alguna y la
                        // pipe se agrega con bAddDefaultConnections=false más adelante.
                        bool tienePart = match != null && !string.IsNullOrWhiteSpace(match.Part);
                        if (!tienePart)
                        {
                            if (!createdStructs.ContainsKey(key)) createdStructs[key] = ObjectId.Null;
                            vertStructIds.Add(ObjectId.Null);
                            continue;
                        }
                        // Cuando hay familia asignada, caemos al flujo normal de crear
                        // structure más abajo — se desactiva sinBuzones para este vértice.
                    }
                    if (!createdStructs.ContainsKey(key))
                    {
                        ObjectId sFam, sSize;
                        string ruta;
                        if (match != null && !match.Covered && haySinTapa)
                        { sFam = defStructFamNoLid; sSize = defStructSizeNoLid; ruta = "sin_tapa"; }
                        else
                        {
                            string sizeHint = match != null ? (match.PartSize ?? "") : "";
                            BuscarEstructura(tr, partsList, structType, sizeHint,
                                             out sFam, out sSize, out _);
                            if (sFam == ObjectId.Null)
                            { sFam = defStructFam; sSize = defStructSize; ruta = "fallback_default"; }
                            else ruta = "buscar_estructura_match";
                        }
                        // Nombres reales para diagnóstico
                        string realFamName = "?", realSizeName = "?";
                        try
                        {
                            var famDbg = tr.GetObject(sFam, OpenMode.ForRead) as PartsStyles.PartFamily;
                            realFamName = famDbg?.Description ?? "?";
                            var szDbg = tr.GetObject(sSize, OpenMode.ForRead) as PartsStyles.PartSize;
                            realSizeName = szDbg?.Name ?? "?";
                        }
                        catch { }
                        Dbg("STRUCT_CREATE", ("id", match?.Id ?? ""),
                            ("x", v.X.ToString("F3")), ("y", v.Y.ToString("F3")),
                            ("pedido_part", structType), ("pedido_size", match?.PartSize ?? ""),
                            ("ruta", ruta),
                            ("usada_familia", realFamName), ("usada_size", realSizeName));

                        ObjectId sid = ObjectId.Null;
                        try
                        {
                            net.AddStructure(sFam, sSize, new Point3d(v.X, v.Y, rim), 0.0, ref sid, true);
                        }
                        catch (Exception exAdd)
                        {
                            Dbg("STRUCT_ADD_FAIL", ("id", match?.Id ?? ""),
                                ("familia_pedida", realFamName), ("tamano_pedido", realSizeName),
                                ("error", exAdd.Message));
                            // Fallback al buzón por defecto (que sí sabemos que funciona
                            // porque PrimeraPieza lo eligió y AsegurarBuzonReal lo validó).
                            try
                            {
                                net.AddStructure(defStructFam, defStructSize,
                                                 new Point3d(v.X, v.Y, rim), 0.0, ref sid, true);
                                Dbg("STRUCT_ADD_FALLBACK_OK", ("id", match?.Id ?? ""),
                                    ("familia_usada", defStructNom));
                            }
                            catch (Exception exAdd2)
                            {
                                Dbg("STRUCT_ADD_FALLBACK_FAIL", ("id", match?.Id ?? ""),
                                    ("error", exAdd2.Message));
                                ed.WriteMessage($"\n⚠ No se pudo crear la estructura {match?.Id ?? "?"} en ({v.X:F2},{v.Y:F2}); se salta y sigue.");
                                // Marcar el vértice como "sin structure" y seguir con el
                                // siguiente vértice para no cortar la red entera.
                                createdStructs[key] = ObjectId.Null;
                                vertStructIds.Add(ObjectId.Null);
                                continue;
                            }
                        }
                        CivilDB.Structure st = (CivilDB.Structure)tr.GetObject(sid, OpenMode.ForWrite);
                        // Sump por ELEVACIÓN (si queda por profundidad, sump=rim−sumpDepth pisa lo nuestro).
                        SetSumpControlByElevation(st);
                        // ¿Tenemos rim explícito? (siempre que no dependamos de una superficie).
                        bool holdRim = surfId == ObjectId.Null || (match != null && match.Rim.HasValue);
                        if (holdRim)
                        {
                            st.AutomaticRimSurfaceAdjustment = false;   // clave: si queda true, ignora el rim manual
                            st.RimElevation = rim;
                            explicitRimSump[sid] = (rim, sump);         // reponer al final (la conexión lo pisa)
                        }
                        else st.AutomaticRimSurfaceAdjustment = true;   // rim tomado de la superficie
                        st.SumpElevation = sump;

                        if (match != null && !string.IsNullOrWhiteSpace(match.Id))
                        { try { st.Name = match.Id; } catch { } }

                        createdStructs[key] = sid;
                    }
                    vertStructIds.Add(createdStructs[key]);
                }

                for (int i = 0; i < nVerts - 1; i++)
                {
                    Point3d p1 = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zVerts[i]);
                    Point3d p2 = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, zVerts[i + 1]);
                    if (p1.DistanceTo(p2) < 1e-6) continue;

                    ObjectId pid = ObjectId.Null;
                    // Conduit (sinBuzones): sin auto-conexión ni structures. Solo la pipe pura.
                    bool autoConexion = !sinBuzones;
                    net.AddLinePipe(pipeFam, pipeSize, new LineSegment3d(p1, p2), ref pid, autoConexion);
                    CivilDB.Pipe pipe = (CivilDB.Pipe)tr.GetObject(pid, OpenMode.ForWrite);
                    // Solo conectar si la estructura correspondiente se creó bien.
                    // En modo conduit, vertStructIds[i] siempre es Null, así que no conecta.
                    // Envuelto en try/catch: si la structure asignada no admite la
                    // conexión (p.ej. una end-section que se elige por error), se
                    // registra pero no aborta la red entera.
                    if (vertStructIds[i] != ObjectId.Null)
                    {
                        try { pipe.ConnectToStructure(CivilDB.ConnectorPositionType.Start, vertStructIds[i], true); }
                        catch (Exception exC) { Dbg("PIPE_CONNECT_FAIL", ("extremo", "start"), ("error", exC.Message)); }
                    }
                    if (vertStructIds[i + 1] != ObjectId.Null)
                    {
                        try { pipe.ConnectToStructure(CivilDB.ConnectorPositionType.End, vertStructIds[i + 1], true); }
                        catch (Exception exC) { Dbg("PIPE_CONNECT_FAIL", ("extremo", "end"), ("error", exC.Message)); }
                    }
                    explicitPipeInv.Add((pid, zVerts[i], zVerts[i + 1]));   // reponer invert al final

                    if (!string.IsNullOrWhiteSpace(ip.Material))
                    { try { pipe.Description = ip.Material; } catch { } }

                    nPipes++;
                }
            }

            // ── Reponer cotas EXPLÍCITAS (Civil 3D las recalcula al conectar) ──
            // Se hace AL FINAL, cuando ya no hay conexiones que las pisen. Primero las
            // tuberías (fija la Z de cada extremo = invert capturado), luego rim/sump.
            // Tuberías: fijar Z de cada extremo y LEER DE VUELTA para saber si pegó.
            int pipeOk = 0, pipeErr = 0; string pipeMsg = "";
            foreach (var pv in explicitPipeInv)
            {
                try
                {
                    var pp = (CivilDB.Pipe)tr.GetObject(pv.id, OpenMode.ForWrite);
                    Point3d s = pp.StartPoint, e = pp.EndPoint;
                    // StartPoint.Z es el EJE del tubo; el invert (rasante) capturado
                    // es la SOLERA. Eje = invert + radio interior, así la solera
                    // mostrada = el invert capturado (sin el desfase de medio diámetro).
                    double r = 0.0; try { r = pp.InnerDiameterOrWidth / 2.0; } catch { }
                    double czS = pv.zStart + r, czE = pv.zEnd + r;
                    pp.StartPoint = new Point3d(s.X, s.Y, czS);
                    pp.EndPoint = new Point3d(e.X, e.Y, czE);
                    double back = pp.StartPoint.Z;
                    if (Math.Abs(back - czS) < 0.05) pipeOk++;
                    else { pipeErr++; if (pipeMsg == "") pipeMsg = $"pedí {czS:F2}, quedó {back:F2}"; }
                }
                catch (Exception ex) { pipeErr++; if (pipeMsg == "") pipeMsg = "EXCEPCION " + ex.Message; }
            }
            ed.WriteMessage($"\n[DIAG] Pipe StartPoint.Z: ok={pipeOk} fallo={pipeErr}  {pipeMsg}");

            // Estructuras: cada setter por separado para ver CUÁL falla, y leer de vuelta.
            int stOk = 0, stErr = 0; string stMsg = "";
            foreach (var kv in explicitRimSump)
            {
                try
                {
                    var st = (CivilDB.Structure)tr.GetObject(kv.Key, OpenMode.ForWrite);
                    // 1) Apagar el ajuste automático a superficie (o el rim vuelve a la sup).
                    try { st.AutomaticRimSurfaceAdjustment = false; } catch (Exception e1) { if (stMsg == "") stMsg = "autoAdj→" + e1.Message; }
                    // 2) Cambiar "Controlar sumidero por" a POR ELEVACIÓN. Sin esto Civil
                    //    calcula sump = rim − SumpDepth y anula SumpElevation.
                    { string err = SetSumpControlByElevation(st); if (err != null && stMsg == "") stMsg = "ctrlSump→" + err; }
                    // 3) Fijar sump primero (con ByElevation ya no lo pisa), luego rim.
                    try { st.SumpElevation = kv.Value.sump; } catch (Exception e3) { if (stMsg == "") stMsg = "sump→" + e3.Message; }
                    try { st.RimElevation = kv.Value.rim; } catch (Exception e2) { if (stMsg == "") stMsg = "rim→" + e2.Message; }
                    bool adj = st.AutomaticRimSurfaceAdjustment; double rb = st.RimElevation; double sb = st.SumpElevation;
                    bool okRim = Math.Abs(rb - kv.Value.rim) < 0.05;
                    bool okSump = Math.Abs(sb - kv.Value.sump) < 0.05;
                    if (!adj && okRim && okSump) stOk++;
                    else
                    {
                        stErr++;
                        // Siempre muestra el read-back real; útil para saber SI hubo cambios aunque el rim quede pegado por el tamaño.
                        string tag = $"rim pedí {kv.Value.rim:F2} quedó {rb:F2}, sump pedí {kv.Value.sump:F2} quedó {sb:F2}";
                        if (stMsg == "" || stMsg.StartsWith("height")) stMsg = tag;
                    }
                }
                catch (Exception ex) { stErr++; if (stMsg == "") stMsg = "EXCEPCION " + ex.Message; }
            }
            ed.WriteMessage($"\n[DIAG] Estructura rim/auto: ok={stOk} fallo={stErr}  {stMsg}");

            // Alineamiento (eje) para la red — permite después crear vistas de perfil
            ObjectId alignId = ComandosAlineamientos.CrearAlineamientoDesdePts(db, civilDoc, tr, trazaEje, nm + "-eje");
            if (alignId != ObjectId.Null)
            { try { net.ReferenceAlignmentId = alignId; } catch { } }

            ed.WriteMessage($"\n✓ Red gravedad '{nm}': {createdStructs.Count} buzones, {nPipes} tuberías" +
                            (alignId != ObjectId.Null ? " + eje." : "."));
            return netId;
        }

        // =================================================================
        //  RED DE PRESIÓN COMPLETA (per-pipe diameter + auto-connect + fittings)
        // =================================================================
        private ObjectId CrearRedPresionCompleta(
            Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
            string nombre, ObjectId surfId, double defaultDepth,
            List<ImportPipe> pipes)
        {
            PresStyles.PressurePartListCollection plc =
                PresStyles.StylesRootPressurePipesExtension.GetPressurePartLists(civilDoc.Styles);
            if (plc.Count == 0)
            { ed.WriteMessage($"\n'{nombre}': no hay Parts Lists de presión."); return ObjectId.Null; }

            ObjectId plId = plc[0];
            PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(plId, OpenMode.ForRead);

            var tubos = pl.GetParts(CivilDB.PressurePartDomainType.Pipe);
            if (tubos == null || tubos.Count == 0)
            { ed.WriteMessage($"\n'{nombre}': sin tubos en la Parts List de presión."); return ObjectId.Null; }

            ObjectId netId = CivilDB.PressurePipeNetwork.Create(db, nombre);
            CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netId, OpenMode.ForWrite);
            net.PartsListId = plId;

            // Crear tuberías con matching per-pipe por diámetro
            int nPipes = 0;
            var createdPipeIds = new List<ObjectId>();
            var pipeEndpoints = new List<(Point3d start, Point3d end, ObjectId id)>();
            var trazaEje = new List<Point3d>();

            foreach (var ip in pipes)
            {
                PresStyles.PressurePartSize tuboElegido = MatchPresionTubo(tubos, ip.Diameter, ip.PipeFamily);
                Dbg("PIPE_PRES_MATCH", ("pedido_fam", ip.PipeFamily ?? ""),
                    ("pedido_size", ip.PipeSize ?? ""), ("diam", ip.Diameter.ToString("F1")),
                    ("elegida", tuboElegido?.Description ?? "?"));

                int nVerts = ip.Vertices.Count;
                // Cota de rasante capturada. Antes caía a -defaultDepth (¡negativo!)
                // cuando faltaba el dato; ahora 0 (neutro). En el flujo normal viene
                // el invert del DXF (agua/gas también lo llevan).
                double zStart = ip.InvStart ?? 0.0;
                double zEnd = ip.InvEnd ?? zStart;
                // Por DISTANCIA (pendiente uniforme), no por índice de vértice.
                double[] zpv = ZalongByDistance(ip.Vertices, zStart, zEnd);

                for (int i = 0; i < nVerts - 1; i++)
                {
                    double z1 = zpv[i];
                    double z2 = zpv[i + 1];

                    Point3d p1 = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, z1);
                    Point3d p2 = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, z2);
                    if (p1.DistanceTo(p2) < 1e-6) continue;

                    ObjectId pid = net.AddLinePipe(new LineSegment3d(p1, p2), tuboElegido);
                    createdPipeIds.Add(pid);
                    pipeEndpoints.Add((p1, p2, pid));
                    if (trazaEje.Count == 0) trazaEje.Add(p1);
                    trazaEje.Add(p2);

                    if (!string.IsNullOrWhiteSpace(ip.Material))
                    {
                        try
                        {
                            CivilDB.PressurePipe pp = (CivilDB.PressurePipe)tr.GetObject(pid, OpenMode.ForWrite);
                            pp.Description = ip.Material;
                        }
                        catch { }
                    }

                    nPipes++;
                }
            }

            // Auto-conectar tuberías en vértices compartidos e insertar fittings
            int nFittings = 0;
            var fittings = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);
            bool hasFittings = fittings != null && fittings.Count > 0;

            for (int a = 0; a < pipeEndpoints.Count; a++)
            {
                for (int b = a + 1; b < pipeEndpoints.Count; b++)
                {
                    // Buscar extremos coincidentes (tolerancia 0.5 unidades)
                    int portA = -1, portB = -1;
                    double bestDist = 0.5;

                    Point3d[] ea = { pipeEndpoints[a].start, pipeEndpoints[a].end };
                    Point3d[] eb = { pipeEndpoints[b].start, pipeEndpoints[b].end };

                    for (int i = 0; i < 2; i++)
                        for (int j = 0; j < 2; j++)
                        {
                            double d = ea[i].DistanceTo(eb[j]);
                            if (d < bestDist) { bestDist = d; portA = i; portB = j; }
                        }

                    if (portA < 0) continue;

                    Point3d junta = new Point3d(
                        (ea[portA].X + eb[portB].X) / 2,
                        (ea[portA].Y + eb[portB].Y) / 2,
                        (ea[portA].Z + eb[portB].Z) / 2);

                    // Calcular deflexión
                    Vector3d v1 = portA == 0 ? ea[1] - ea[0] : ea[0] - ea[1];
                    Vector3d v2 = portB == 0 ? eb[1] - eb[0] : eb[0] - eb[1];
                    double deflex = 180.0 - v1.GetAngleTo(v2) * 180.0 / Math.PI;

                    if (hasFittings && Math.Abs(deflex) > 2.0)
                    {
                        // Insertar fitting (codo) en el cambio de dirección
                        try
                        {
                            CivilDB.PressurePipe ppA = (CivilDB.PressurePipe)tr.GetObject(
                                pipeEndpoints[a].id, OpenMode.ForRead);
                            double diam = ppA.NominalDiameter;
                            PresStyles.PressurePartSize elbow = MatchFitting(
                                fittings, CivilDB.PressurePartType.Elbow, diam, deflex);

                            if (elbow != null)
                            {
                                ObjectId fid = net.AddFitting(junta, elbow);
                                CivilDB.PressurePart parte = (CivilDB.PressurePart)tr.GetObject(
                                    fid, OpenMode.ForWrite);
                                try { parte.ConnectToPipe(0, pipeEndpoints[a].id, portA); } catch { }
                                try { parte.ConnectToPipe(1, pipeEndpoints[b].id, portB); } catch { }
                                nFittings++;
                                continue;
                            }
                        }
                        catch { }
                    }

                    // Conexión directa tubo-a-tubo si no hay fitting
                    try
                    {
                        CivilDB.PressurePipe ppA = (CivilDB.PressurePipe)tr.GetObject(
                            pipeEndpoints[a].id, OpenMode.ForWrite);
                        ppA.ConnectToPipe(portA, pipeEndpoints[b].id, portB);
                    }
                    catch { }
                }
            }

            // ── Reponer la cota (Z) de rasante en cada extremo ──────────────
            // Igual que en gravedad: al conectar tubos/fittings Civil 3D recalcula
            // las cotas. Aquí forzamos la Z capturada en el inicio/fin de cada tubo
            // (conservando su XY actual tras la conexión) para que agua/gas muestren
            // la elevación de rasante inicial/final que el DXF trae.
            foreach (var pe in pipeEndpoints)
            {
                try
                {
                    var pp = (CivilDB.PressurePipe)tr.GetObject(pe.id, OpenMode.ForWrite);
                    Point3d cs = pp.StartPoint, ce = pp.EndPoint;
                    pp.StartPoint = new Point3d(cs.X, cs.Y, pe.start.Z);
                    pp.EndPoint   = new Point3d(ce.X, ce.Y, pe.end.Z);
                }
                catch { }
            }

            // Alineamiento (eje) para la red de presión — para vistas de perfil
            ObjectId alignId = ComandosAlineamientos.CrearAlineamientoDesdePts(db, civilDoc, tr, trazaEje, nombre + "-eje");
            if (alignId != ObjectId.Null)
            {
                foreach (var pid in createdPipeIds)
                {
                    try
                    {
                        var pp = tr.GetObject(pid, OpenMode.ForWrite) as CivilDB.PressurePipe;
                        if (pp != null) pp.ReferenceAlignmentId = alignId;
                    }
                    catch { }
                }
            }

            ed.WriteMessage($"\n✓ Red presión '{nombre}': {nPipes} tubería(s), {nFittings} fitting(s)" +
                            (alignId != ObjectId.Null ? " + eje." : "."));
            return netId;
        }

        // =================================================================
        //  REPORTE CSV — lee de vuelta cada elemento creado (para revisión)
        //  Se escribe en Descargas\IMPORTAR_RED_reporte.csv. Todo lo que ve
        //  Civil 3D en las propiedades, en texto plano.
        // =================================================================
        private void EscribirReporteRed(Editor ed, Transaction tr,
            List<ObjectId> gravNets, List<ObjectId> presNets)
        {
            var sb = new System.Text.StringBuilder();
            sb.AppendLine("TIPO,RED,NOMBRE,DIAM_in,MATERIAL_DESC,COTA_INI,COTA_FIN,PENDIENTE_%,LONGITUD,RIM,SUMP,FAMILIA,TAMANO");

            // ── Redes de gravedad: estructuras + tuberías ──
            foreach (ObjectId nid in gravNets)
            {
                var net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                if (net == null) continue;
                string rn = net.Name;
                foreach (ObjectId sid in net.GetStructureIds())
                {
                    var st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                    if (st == null) continue;
                    string famName = "?", sizeName = "?";
                    try
                    {
                        var famDbg = tr.GetObject(st.PartFamilyId, OpenMode.ForRead) as PartsStyles.PartFamily;
                        famName = (famDbg?.Description ?? "").Replace(",", " ");
                        sizeName = (st.PartSizeName ?? "").Replace(",", " ");
                    }
                    catch { }
                    sb.AppendLine($"ESTRUCTURA,{rn},{st.Name},{st.InnerDiameterOrWidth * 12.0:F1},,,,,,{st.RimElevation:F3},{st.SumpElevation:F3},{famName},{sizeName}");
                }
                foreach (ObjectId pid in net.GetPipeIds())
                {
                    var p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                    if (p == null) continue;
                    double d = p.InnerDiameterOrWidth;
                    double invI = p.StartPoint.Z - d / 2.0;   // invert = eje - radio interior
                    double invF = p.EndPoint.Z - d / 2.0;
                    double len = p.StartPoint.DistanceTo(p.EndPoint);
                    string desc = (p.Description ?? "").Replace(",", " ");
                    sb.AppendLine($"TUBERIA_GRAV,{rn},{p.Name},{d * 12.0:F1},{desc},{invI:F3},{invF:F3},{p.Slope * 100:F2},{len:F3},,");
                }
            }

            // ── Redes de presión: tuberías (sin estructuras) ──
            foreach (ObjectId nid in presNets)
            {
                try
                {
                    var net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                    if (net == null) continue;
                    string rn = net.Name;
                    foreach (ObjectId pid in net.GetPipeIds())
                    {
                        var p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                        if (p == null) continue;
                        double zi = p.StartPoint.Z, zf = p.EndPoint.Z;
                        double len = p.StartPoint.DistanceTo(p.EndPoint);
                        double slope = len > 1e-6 ? (zi - zf) / len * 100.0 : 0.0;
                        string desc = (p.Description ?? "").Replace(",", " ");
                        sb.AppendLine($"TUBERIA_PRES,{rn},{p.Name},{p.NominalDiameter * 12.0:F1},{desc},{zi:F3},{zf:F3},{slope:F2},{len:F3},,");
                    }
                }
                catch { }
            }

            string dir = System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
            if (!System.IO.Directory.Exists(dir))
                dir = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string path = System.IO.Path.Combine(dir, "IMPORTAR_RED_reporte.csv");
            System.IO.File.WriteAllText(path, sb.ToString(), System.Text.Encoding.UTF8);
            ed.WriteMessage($"\n📄 Reporte escrito: {path}");
        }

        // =================================================================
        //  DIAGNÓSTICO INLINE
        // =================================================================
        private void DiagnosticarInline(Editor ed, Transaction tr, List<ObjectId> netIds)
        {
            int problemas = 0;
            foreach (ObjectId nid in netIds)
            {
                CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                if (net == null) continue;

                foreach (ObjectId pid in net.GetPipeIds())
                {
                    CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                    if (p == null) continue;
                    if (Math.Abs(p.Slope) < 0.0005)
                    {
                        problemas++;
                        ed.WriteMessage($"\n⚠ '{p.Name}': pendiente ≈ 0 ({p.Slope:P2}).");
                    }
                }

                foreach (ObjectId sid in net.GetStructureIds())
                {
                    CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                    if (st == null) continue;

                    if (st.RimElevation <= st.SumpElevation)
                    {
                        problemas++;
                        ed.WriteMessage($"\n⚠ '{st.Name}': rim ({st.RimElevation:F2}) ≤ sump ({st.SumpElevation:F2}).");
                    }
                    if (st.ConnectedPipesCount == 0)
                    {
                        problemas++;
                        ed.WriteMessage($"\n⚠ '{st.Name}': aislada (sin tuberías).");
                    }

                    double dEstr = st.InnerDiameterOrWidth;
                    for (int i = 0; i < st.ConnectedPipesCount; i++)
                    {
                        try
                        {
                            CivilDB.Pipe p = tr.GetObject(st.get_ConnectedPipe(i), OpenMode.ForRead) as CivilDB.Pipe;
                            if (p != null && dEstr > 0 && p.InnerDiameterOrWidth > dEstr + 1e-6)
                            {
                                problemas++;
                                ed.WriteMessage($"\n⚠ Tubo '{p.Name}' (Ø{p.InnerDiameterOrWidth:F0}) > estructura '{st.Name}' (Ø{dEstr:F0}).");
                            }
                        }
                        catch { }
                    }
                }
            }

            if (problemas == 0)
                ed.WriteMessage("\n✓ Diagnóstico: sin problemas detectados.");
            else
                ed.WriteMessage($"\n— Diagnóstico: {problemas} aviso(s).");
        }

        // =================================================================
        //  VERIFICAR CATÁLOGO IMPERIAL
        // =================================================================
        private void VerificarCatalogoImperial(Editor ed)
        {
            try
            {
                PartsStyles.DataPartFamily[] disp = PartsStyles.PartsList.GetAvailablePartFamilies(CivilDB.DomainType.Pipe);
                if (disp == null || disp.Length == 0)
                {
                    ed.WriteMessage("\n⚠ No hay familias en el catálogo. Ejecuta SETPIPENETWORKCATALOG y elige el catálogo Imperial.");
                    return;
                }
                bool hayMetric = false;
                bool hayImperial = false;
                foreach (var dpf in disp)
                {
                    string desc = (dpf.Description ?? "").ToLowerInvariant();
                    if (desc.Contains("metric") || desc.Contains("mm")) hayMetric = true;
                    if (desc.Contains("imperial") || desc.Contains("inch") || desc.Contains("in.") || desc.Contains("\"")) hayImperial = true;
                }
                if (hayMetric && !hayImperial)
                    ed.WriteMessage("\n⚠ El catálogo actual parece ser MÉTRICO. Ejecuta SETPIPENETWORKCATALOG y elige el Imperial.");
                else
                    ed.WriteMessage("\n✓ Catálogo: imperial detectado.");
            }
            catch { }
        }

        // =================================================================
        //  ASEGURAR BUZÓN REAL — evita "Estructura nula" (esfera en 3D)
        //  Si la Parts List NO tiene un buzón cilíndrico/rectangular con tapa,
        //  agrega uno del catálogo imperial (preferido: "Concentric Cylindrical
        //  Structure with Rectangular Frame" ≈ buzón estándar de saneamiento).
        // =================================================================
        // Setea Structure.ControlSumpBy = "ByElevation" por reflexión (el enum
        // vive en un namespace de Civil que cambia por versión; así no lo hardcodeamos).
        // Devuelve null si OK, o un mensaje de error corto si falló.
        private static string SetSumpControlByElevation(CivilDB.Structure st)
        {
            try
            {
                var prop = st.GetType().GetProperty("ControlSumpBy");
                if (prop == null) return "no-prop";
                var enumType = prop.PropertyType;
                if (!enumType.IsEnum) return "no-enum";
                object val;
                try { val = Enum.Parse(enumType, "ByElevation", true); }
                catch { return "no-value"; }
                prop.SetValue(st, val);
                return null;
            }
            catch (Exception e) { return e.Message; }
        }

        // Setea Structure.RimToSumpHeight = altura (ft). Con eso Civil calcula
        // rim = sump + RimToSumpHeight (respeta el barril variable de la familia).
        // Devuelve null si OK, o un mensaje corto si falló.
        private static string SetRimToSumpHeight(CivilDB.Structure st, double heightFt)
        {
            try
            {
                var prop = st.GetType().GetProperty("RimToSumpHeight");
                if (prop == null) return "no-prop";
                prop.SetValue(st, heightFt);
                return null;
            }
            catch (Exception e) { return e.Message; }
        }

        // Borra las polylines XDATA=PDFCAD_PIPE cuya NET_KIND sea 'gravity' o
        // 'pressure' (ya se convirtieron a Pipe/Pressure Networks). Las de
        // 'conduit' se conservan porque el plugin no las procesa.
        private void BorrarPolylinesConvertidas(Editor ed, Database db)
        {
            int nBorradas = 0;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var ms = (BlockTableRecord)tr.GetObject(
                        SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                    var toDelete = new List<ObjectId>();
                    foreach (ObjectId eid in ms)
                    {
                        var ent = tr.GetObject(eid, OpenMode.ForRead) as Entity;
                        if (ent is not Polyline) continue;
                        var xd = LeerXdataPdfcad(ent);
                        if (xd == null) continue;
                        if (!xd.TryGetValue("_MARKER", out string marker) || marker != "PDFCAD_PIPE") continue;
                        string netKind = XdStr(xd, "NET_KIND", "gravity");
                        if (netKind.Equals("gravity", StringComparison.OrdinalIgnoreCase) ||
                            netKind.Equals("pressure", StringComparison.OrdinalIgnoreCase))
                            toDelete.Add(eid);
                    }
                    foreach (var id in toDelete)
                    {
                        var e = tr.GetObject(id, OpenMode.ForWrite) as Entity;
                        if (e != null) { e.Erase(true); nBorradas++; }
                    }
                    tr.Commit();
                }
                catch (Exception ex) { ed.WriteMessage($"\n(No se pudieron borrar las polilíneas convertidas: {ex.Message})"); tr.Abort(); }
            }
            if (nBorradas > 0)
                ed.WriteMessage($"\n  · {nBorradas} polilínea(s) DXF de gravedad/presión eliminada(s) tras convertirse a redes.");
        }

        // Tokens (EN/ES) que indican familia NO-buzón. Cuando 'incluirSinTapa' es true,
        // se REMUEVEN los tokens de sin-tapa (headwall, cabecero, cabezal, boca, aleta)
        // para permitir usarlos como estructura "sin tapa".
        private static string[] NoBuzonTokens(bool incluirSinTapa)
        {
            if (incluirSinTapa) return new[] { "Null", "nula" };
            return new[] {
                "Null", "Headwall", "End Section", "Flared", "Culvert", "Winged", "Wing", "Apron",
                "nula", "cabecero", "cabezal", "boca", "aleta", "alcantarilla",
                // Términos ES adicionales (Civil 3D español):
                "Embocadura", "embocadura",
                "Sección final", "seccion final",
                "en ala", "de ala",
                "acampanada",
                "O.D.T.",
            };
        }

        // Asegura que la familia identificada por su ID de catálogo (basename del .xml,
        // p.ej. "AeccStructConcentricCylinderRectFrame_Imperial") esté en el PartsList
        // del dibujo. Si no está, la busca en el catálogo disponible y la agrega con
        // TODOS sus tamaños. Usa MatchCatalogId para comparar tokens EN↔ES entre el
        // catalogId (CamelCase EN) y la Description de la familia (idioma real).
        private void AsegurarFamiliaPorId(Editor ed, Transaction tr, PartsStyles.PartsList partsList,
                                          string catalogId, CivilDB.DomainType dominio = CivilDB.DomainType.Structure)
        {
            if (string.IsNullOrWhiteSpace(catalogId)) { Dbg("ASEGURAR_FAM_SKIP", ("motivo", "vacio")); return; }
            // ¿Ya está?
            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(dominio))
            {
                var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                bool m = MatchCatalogIdPublic(catalogId, fam.Description ?? "");
                Dbg("ASEGURAR_FAM_CHECK", ("pedido", catalogId), ("dominio", dominio.ToString()),
                    ("candidato", fam.Description ?? ""),
                    ("match", m ? "true" : "false"), ("sizes", fam.PartSizeCount));
                if (m) { Dbg("ASEGURAR_FAM_YA_ESTA", ("pedido", catalogId), ("descripcion", fam.Description ?? "")); return; }
            }
            try
            {
                PartsStyles.DataPartFamily[] disp =
                    PartsStyles.PartsList.GetAvailablePartFamilies(dominio);
                if (disp == null || disp.Length == 0) return;
                PartsStyles.DataPartFamily elegido = null;
                foreach (var dpf in disp)
                {
                    string desc = dpf.Description ?? "";
                    if (desc.IndexOf("Metric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    if (desc.IndexOf("métric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    if (MatchCatalogIdPublic(catalogId, desc))
                    { elegido = dpf; break; }
                }
                if (elegido == null)
                {
                    Dbg("ASEGURAR_FAM_NO_ENCONTRADA_EN_CATALOGO", ("pedido", catalogId),
                        ("candidatos_en_catalogo", disp.Length));
                    ed.WriteMessage($"\n⚠ Familia '{catalogId}' pedida desde Python no se encontró en el catálogo disponible.");
                    return;
                }
                Dbg("ASEGURAR_FAM_AGREGANDO", ("pedido", catalogId), ("elegida", elegido.Description ?? ""),
                    ("guid", elegido.GUID));
                partsList.UpgradeOpen();
                try { partsList.AddPartFamilyByGuid(dominio, elegido.GUID); } catch { }
                foreach (ObjectId fid2 in partsList.GetPartFamilyIdsByDomain(dominio))
                {
                    var fam = tr.GetObject(fid2, OpenMode.ForWrite) as PartsStyles.PartFamily;
                    if (fam == null || !string.Equals(fam.GUID, elegido.GUID, StringComparison.OrdinalIgnoreCase)) continue;
                    try
                    {
                        var filtro = new PartsStyles.SizeFilterRecord(fam);
                        for (int i = 0; i < filtro.ParamCount; i++)
                        {
                            var campo = filtro[i];
                            if (campo != null && !campo.IsReadOnly && campo.IsFromList)
                                campo.IsMultipleSelect = true;
                        }
                        fam.AddPartSize(filtro);
                    }
                    catch (Exception exSize)
                    { ed.WriteMessage($"\n  (No se pudieron agregar tamaños para '{catalogId}': {exSize.Message})"); }
                    ed.WriteMessage($"\n  + Familia solicitada '{elegido.Description}' agregada al PartsList ({fam.PartSizeCount} tamaño(s)).");
                    break;
                }
            }
            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo asegurar familia '{catalogId}': {ex.Message})"); }
        }

        private void AsegurarBuzonReal(Editor ed, Transaction tr, PartsStyles.PartsList partsList)
        {
            // Cada elemento es una lista de tokens que TODOS deben estar en la descripción.
            // Así "cilíndrica concéntrica" matchea "Estructura cilíndrica concéntrica con marco rectangular".
            string[][] prefConTapa = {
                new[]{"concentric","cylindrical","rectangular"},
                new[]{"concéntrica","cilíndrica","rectangular"},
                new[]{"concentrica","cilindrica","rectangular"},   // sin acentos
                new[]{"concentric","cylindrical"},
                new[]{"concéntrica","cilíndrica"},
                new[]{"concentrica","cilindrica"},
                new[]{"cylindrical","junction"},
                new[]{"cilíndrica","conexión"},
                new[]{"cilindrica","conexion"},
                new[]{"junction","structure"},
                new[]{"conexión"},
                new[]{"cilíndrica"},
                new[]{"cilindrica"},
                new[]{"cylindrical"},
                new[]{"rectangular","junction"},
                new[]{"rectangular","conexión"},
            };
            // Familias típicas para buzón "sin tapa": junction structure without frame,
            // headwalls, cabeceros/cabezales. Fallback: cualquier headwall/end section.
            string[][] prefSinTapa = {
                new[]{"junction","structure","without","frame"},
                new[]{"structure","without","frame"},
                new[]{"cylindrical","without","frame"},
                new[]{"sin","marco"},
                new[]{"cilíndrica","sin","tapa"},
                new[]{"cilindrica","sin","tapa"},
                new[]{"headwall"},
                new[]{"cabecero"},
                new[]{"cabezal"},
                new[]{"end","section"},
                new[]{"flared","end"},
            };
            AgregarFamiliaSiFalta(ed, tr, partsList, prefConTapa, incluirSinTapa: false, etiqueta: "con tapa");
            AgregarFamiliaSiFalta(ed, tr, partsList, prefSinTapa, incluirSinTapa: true, etiqueta: "sin tapa");
        }

        // Agrega una familia al PartsList si NINGUNA familia existente coincide con las preferencias.
        private void AgregarFamiliaSiFalta(Editor ed, Transaction tr, PartsStyles.PartsList partsList,
                                            string[][] pref, bool incluirSinTapa, string etiqueta)
        {
            string[] noBuzon = NoBuzonTokens(incluirSinTapa);
            // ¿Ya hay una familia que cumpla alguna preferencia?
            ObjectIdCollection fams = partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure);
            foreach (ObjectId fid in fams)
            {
                var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                string d = fam.Description ?? "";
                if (CoincideAlgunaPref(d, pref, noBuzon)) return;
            }
            try
            {
                PartsStyles.DataPartFamily[] disp =
                    PartsStyles.PartsList.GetAvailablePartFamilies(CivilDB.DomainType.Structure);
                if (disp == null || disp.Length == 0)
                { ed.WriteMessage($"\n⚠ Sin catálogo de estructuras ({etiqueta})."); return; }

                PartsStyles.DataPartFamily elegido = null;
                foreach (var tokens in pref)
                {
                    foreach (var dpf in disp)
                    {
                        string desc = (dpf.Description ?? "");
                        if (desc.IndexOf("Metric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                        if (desc.IndexOf("métric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                        if (desc.IndexOf("metric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                        bool esNoBuzon = false;
                        foreach (var k in noBuzon)
                            if (desc.IndexOf(k, StringComparison.OrdinalIgnoreCase) >= 0) { esNoBuzon = true; break; }
                        if (esNoBuzon) continue;
                        bool todos = true;
                        foreach (var tk in tokens)
                            if (desc.IndexOf(tk, StringComparison.OrdinalIgnoreCase) < 0) { todos = false; break; }
                        if (todos) { elegido = dpf; break; }
                    }
                    if (elegido != null) break;
                }
                if (elegido == null)
                {
                    ed.WriteMessage($"\n⚠ No hallé buzón '{etiqueta}' en el catálogo (buzones {etiqueta} usarán el default).");
                    return;
                }

                partsList.UpgradeOpen();
                try { partsList.AddPartFamilyByGuid(CivilDB.DomainType.Structure, elegido.GUID); } catch { }

                foreach (ObjectId fid2 in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure))
                {
                    var fam = tr.GetObject(fid2, OpenMode.ForWrite) as PartsStyles.PartFamily;
                    if (fam == null || !string.Equals(fam.GUID, elegido.GUID, StringComparison.OrdinalIgnoreCase)) continue;
                    try
                    {
                        var filtro = new PartsStyles.SizeFilterRecord(fam);
                        for (int i = 0; i < filtro.ParamCount; i++)
                        {
                            var campo = filtro[i];
                            if (campo != null && !campo.IsReadOnly && campo.IsFromList)
                                campo.IsMultipleSelect = true;
                        }
                        fam.AddPartSize(filtro);
                    }
                    catch (Exception exSize)
                    { ed.WriteMessage($"\n  (No se pudieron agregar tamaños: {exSize.Message})"); }
                    ed.WriteMessage($"\n  + Buzón '{etiqueta}' → '{elegido.Description}' agregado ({fam.PartSizeCount} tamaño(s)).");
                    break;
                }
            }
            catch (Exception ex) { ed.WriteMessage($"\n(No se pudo asegurar buzón {etiqueta}: {ex.Message})"); }
        }

        private static bool CoincideAlgunaPref(string desc, string[][] pref, string[] noBuzon)
        {
            if (string.IsNullOrEmpty(desc)) return false;
            foreach (var k in noBuzon)
                if (desc.IndexOf(k, StringComparison.OrdinalIgnoreCase) >= 0) return false;
            foreach (var tokens in pref)
            {
                bool todos = true;
                foreach (var tk in tokens)
                    if (desc.IndexOf(tk, StringComparison.OrdinalIgnoreCase) < 0) { todos = false; break; }
                if (todos) return true;
            }
            return false;
        }

        // Busca en el PartsList la primera familia de estructura que corresponda a
        // "sin tapa" (headwall / junction sin marco / cabecero…). Devuelve ObjectId.Null
        // si no hay ninguna. Se usa para buzones con Covered=false.
        private bool BuscarFamiliaSinTapa(Transaction tr, PartsStyles.PartsList partsList,
                                          out ObjectId famId, out ObjectId sizeId, out string nombre)
        {
            famId = ObjectId.Null; sizeId = ObjectId.Null; nombre = "";
            string[][] prefSinTapa = {
                new[]{"junction","structure","without","frame"},
                new[]{"structure","without","frame"},
                new[]{"cylindrical","without","frame"},
                new[]{"sin","marco"},
                new[]{"sin","tapa"},
                new[]{"headwall"},
                new[]{"cabecero"},
                new[]{"cabezal"},
                new[]{"end","section"},
                new[]{"flared","end"},
            };
            string[] noBuzon = { "Null", "nula" };
            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure))
            {
                var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                string d = fam.Description ?? "";
                if (!CoincideAlgunaPref(d, prefSinTapa, noBuzon)) continue;
                famId = fid;
                nombre = d;
                sizeId = fam[0];
                return true;
            }
            return false;
        }

        // =================================================================
        //  AUTO-POBLAR PARTS LIST DESDE CATÁLOGO (solo familias imperiales)
        // =================================================================
        private void AutoAgregarFamiliaCatalogo(Editor ed, Transaction tr,
            PartsStyles.PartsList partsList, CivilDB.DomainType domain, string material)
        {
            try
            {
                PartsStyles.DataPartFamily[] disp = PartsStyles.PartsList.GetAvailablePartFamilies(domain);
                if (disp == null || disp.Length == 0) return;

                string mN = Norm(material);
                PartsStyles.DataPartFamily match = null;
                foreach (var dpf in disp)
                {
                    string desc = (dpf.Description ?? "").ToLowerInvariant();
                    if (desc.Contains("metric") || desc.Contains("mm")) continue;
                    if (dpf.Description != null && Norm(dpf.Description).Contains(mN))
                    { match = dpf; break; }
                }
                if (match == null) return;

                try { partsList.UpgradeOpen(); } catch { }
                try { partsList.AddPartFamilyByGuid(domain, match.GUID); }
                catch { }

                ObjectIdCollection fams = partsList.GetPartFamilyIdsByDomain(domain);
                foreach (ObjectId fid in fams)
                {
                    PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                    if (fam == null) continue;
                    if (!string.Equals(fam.GUID, match.GUID, StringComparison.OrdinalIgnoreCase)) continue;

                    try
                    {
                        PartsStyles.SizeFilterRecord filtro = new PartsStyles.SizeFilterRecord(fam);
                        for (int i = 0; i < filtro.ParamCount; i++)
                        {
                            PartsStyles.SizeFilterField campo = filtro[i];
                            if (campo != null && !campo.IsReadOnly && campo.IsFromList)
                                campo.IsMultipleSelect = true;
                        }
                        fam.AddPartSize(filtro);
                    }
                    catch { }

                    ed.WriteMessage($"\n  + Familia '{match.Description}' agregada al catálogo ({fam.PartSizeCount} tamaño(s)).");
                    break;
                }
            }
            catch { }
        }

        // =================================================================
        //  HELPERS
        // =================================================================

        private PartsStyles.PartsList ObtenerPartsList(CivilDocument civilDoc, Transaction tr)
        {
            PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
            if (plSet.Count == 0) return null;
            ObjectId plId = plSet[0];
            for (int i = 0; i < plSet.Count; i++)
            {
                PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase))
                { plId = plSet[i]; break; }
            }
            return (PartsStyles.PartsList)tr.GetObject(plId, OpenMode.ForRead);
        }

        private static double[] InterpolateZ(ImportPipe ip, int nVerts)
        {
            double zStart = ip.InvStart ?? 0.0;
            double zEnd = ip.InvEnd ?? zStart;
            return ZalongByDistance(ip.Vertices, zStart, zEnd);
        }

        // Invert por vértice interpolado por DISTANCIA acumulada 2D (pendiente
        // uniforme). Repartir por índice de vértice daba pendientes absurdas en
        // los tramos cortos de los quiebres.
        private static double[] ZalongByDistance(List<Point2d> verts, double zStart, double zEnd)
        {
            int n = verts?.Count ?? 0;
            double[] z = new double[n];
            if (n == 0) return z;
            if (n == 1) { z[0] = zStart; return z; }
            double[] d = new double[n];
            for (int i = 1; i < n; i++)
                d[i] = d[i - 1] + verts[i - 1].GetDistanceTo(verts[i]);
            double total = d[n - 1];
            for (int i = 0; i < n; i++)
                z[i] = total > 1e-9 ? zStart + (zEnd - zStart) * (d[i] / total) : zStart;
            return z;
        }

        private static ImportStruct FindNearestStruct(List<ImportStruct> structs, Point2d v, double tol)
        {
            ImportStruct best = null;
            double bestDist = tol;
            foreach (var s in structs)
            {
                double d = s.Location.GetDistanceTo(v);
                if (d < bestDist) { bestDist = d; best = s; }
            }
            return best;
        }

        // Extrae el primer número seguido de "in" (o solo el primero) de una
        // descripción de PartSize. Ej "10 in Elbow 90°" → 10.0; "48 pulg. …" → 48.0.
        private static double ExtractInchesFromDesc(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return 0;
            // Preferir el número que precede "in"/"pulg" para no capturar ángulos.
            var m = System.Text.RegularExpressions.Regex.Match(
                desc, @"(\d+(?:\.\d+)?)\s*(?:in|pulg|""|\bin\b)", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (m.Success) { double v; if (double.TryParse(m.Groups[1].Value,
                System.Globalization.CultureInfo.InvariantCulture, out v)) return v; }
            m = System.Text.RegularExpressions.Regex.Match(desc, @"(\d+(?:\.\d+)?)");
            if (m.Success) { double v; if (double.TryParse(m.Groups[1].Value,
                System.Globalization.CultureInfo.InvariantCulture, out v)) return v; }
            return 0;
        }

        private static PresStyles.PressurePartSize MatchPresionTubo(
            List<PresStyles.PressurePartSize> tubos, double targetDiam, string pipeFamily = "")
        {
            if (tubos == null || tubos.Count == 0) return null;

            // 1) Si el usuario eligió una familia de Python (Imperial_AWWA_...|nombre),
            // filtrar el catálogo a los tubos cuya Description contenga el
            // PART_FAMILY_NAME (después del "|"). Compara tolerante a espacios/case.
            List<PresStyles.PressurePartSize> pool = tubos;
            if (!string.IsNullOrWhiteSpace(pipeFamily) && pipeFamily.Contains("|"))
            {
                string famName = pipeFamily.Substring(pipeFamily.IndexOf('|') + 1).Trim();
                string famNorm = famName.Replace(" ", "").Replace(",", "").ToLowerInvariant();
                var filtrados = new List<PresStyles.PressurePartSize>();
                foreach (var t in tubos)
                {
                    string dNorm = (t.Description ?? "").Replace(" ", "").Replace(",", "").ToLowerInvariant();
                    if (dNorm.Contains(famNorm) || famNorm.Contains(dNorm)) filtrados.Add(t);
                }
                if (filtrados.Count > 0) pool = filtrados;
            }

            if (targetDiam <= 0) return pool[0];
            // 2) De los tubos candidatos, elegir el NominalDiameter más cercano.
            PresStyles.PressurePartSize best = pool[0];
            double bestDiff = double.MaxValue;
            foreach (PresStyles.PressurePartSize t in pool)
            {
                double d = ExtractInchesFromDesc(t.Description);
                double diff = Math.Abs(d - targetDiam);
                if (diff < bestDiff) { bestDiff = diff; best = t; }
            }
            return best;
        }

        private static PresStyles.PressurePartSize MatchFitting(
            List<PresStyles.PressurePartSize> fittings,
            CivilDB.PressurePartType tipo, double diam, double deflex)
        {
            // Recolectar candidatos del tipo pedido y usar su NominalDiameter
            // numérico para elegir el MÁS CERCANO al diámetro de la pipe. Antes
            // este método hacía match por substring en la descripción y, si no
            // encontraba, devolvía el PRIMER fitting del tipo — que a menudo era
            // el más grande del catálogo (Elbow 48"), generando codos gigantes.
            var candidatos = new List<(PresStyles.PressurePartSize part, double diamF, double angleDiff)>();
            foreach (PresStyles.PressurePartSize f in fittings)
            {
                if (f.PartType != tipo) continue;
                double fDiam = ExtractInchesFromDesc(f.Description);
                // Extraer ángulo de la descripción (para codos) para desempatar.
                double fAng = 0;
                var m = System.Text.RegularExpressions.Regex.Match(
                    f.Description ?? "", @"(\d{2,3})\s*[°º]");
                if (m.Success) double.TryParse(m.Groups[1].Value, out fAng);
                double angleDiff = tipo == CivilDB.PressurePartType.Elbow
                    ? Math.Abs(fAng - Math.Abs(deflex)) : 0;
                candidatos.Add((f, fDiam, angleDiff));
            }
            if (candidatos.Count == 0) return null;

            // Preferencias:
            //   1) Diámetro dentro de 0.01" del pedido (empate por ángulo cercano).
            //   2) El más cercano al diámetro pedido; empate por ángulo.
            double target = diam;
            candidatos.Sort((a, b) =>
            {
                double dA = Math.Abs(a.diamF - target), dB = Math.Abs(b.diamF - target);
                if (Math.Abs(dA - dB) > 0.01) return dA.CompareTo(dB);
                return a.angleDiff.CompareTo(b.angleDiff);
            });
            return candidatos[0].part;
        }

        // =================================================================
        //  XDATA readers
        // =================================================================

        private static Dictionary<string, string> LeerXdataPdfcad(Entity ent)
        {
            ResultBuffer xdata = ent.GetXDataForApplication("PDFCAD");
            if (xdata == null) return null;
            var dict = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (TypedValue tv in xdata)
            {
                if (tv.TypeCode != 1000) continue;
                string s = tv.Value?.ToString() ?? "";
                if (s == "PDFCAD_PIPE" || s == "PDFCAD_STRUCT")
                { dict["_MARKER"] = s; continue; }
                int eq = s.IndexOf('=');
                if (eq > 0) dict[s.Substring(0, eq)] = s.Substring(eq + 1);
            }
            return dict.ContainsKey("_MARKER") ? dict : null;
        }

        private static string XdStr(Dictionary<string, string> xd, string key, string def)
        {
            string v;
            return xd.TryGetValue(key, out v) && !string.IsNullOrWhiteSpace(v) ? v.Trim() : def;
        }

        private static double XdDouble(Dictionary<string, string> xd, string key)
        {
            string v;
            if (xd.TryGetValue(key, out v))
            {
                v = (v ?? "").Trim().Replace(',', '.');
                double d;
                if (double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out d))
                    return d;
            }
            return 0.0;
        }

        // Factor para convertir un valor en la unidad de origen (XDATA "UNIT")
        // a las unidades del dibujo (db.Insunits). Devuelve 1.0 si no se puede determinar.
        private static double FactorConversion(string srcUnit, Database db)
        {
            double src = UnitToMeters(srcUnit);
            double dst = InsunitsToMeters(db.Insunits);
            if (src <= 0 || dst <= 0) return 1.0;
            return src / dst;
        }

        private static double UnitToMeters(string u)
        {
            switch ((u ?? "").Trim().ToLowerInvariant())
            {
                case "ft":
                case "feet":
                case "pie":
                case "pies": return 0.3048;
                case "in":
                case "inch":
                case "inches":
                case "pulg": return 0.0254;
                case "m":
                case "meter":
                case "metros": return 1.0;
                case "mm": return 0.001;
                case "cm": return 0.01;
                default: return 0.3048; // por defecto: pies (pipeline pdf-to-cad exporta en ft)
            }
        }

        private static double InsunitsToMeters(UnitsValue u)
        {
            switch (u)
            {
                case UnitsValue.Inches: return 0.0254;
                case UnitsValue.Feet: return 0.3048;
                case UnitsValue.Millimeters: return 0.001;
                case UnitsValue.Centimeters: return 0.01;
                case UnitsValue.Meters: return 1.0;
                case UnitsValue.Yards: return 0.9144;
                case UnitsValue.Kilometers: return 1000.0;
                case UnitsValue.Miles: return 1609.344;
                case UnitsValue.Undefined: return 0.3048; // por defecto: pies (US civil)
                default: return 0.0;
            }
        }

        private static double? MulNull(double? v, double k) => v.HasValue ? v.Value * k : (double?)null;

        private static double? XdNullDouble(Dictionary<string, string> xd, string key)
        {
            string v;
            if (xd.TryGetValue(key, out v) && !string.IsNullOrWhiteSpace(v))
            {
                v = v.Trim().Replace(',', '.');
                double d;
                if (double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out d))
                    return d;
            }
            return null;
        }

        private static void DictAdd<T>(Dictionary<string, List<T>> dict, string key, T item)
        {
            List<T> list;
            if (!dict.TryGetValue(key, out list)) { list = new List<T>(); dict[key] = list; }
            list.Add(item);
        }

        // =================================================================
        //  DTOs
        // =================================================================
        private class ImportPipe
        {
            public string Layer;
            public List<Point2d> Vertices;
            public double Diameter;
            public string Unit;
            public string Material;
            public string NetKind;
            public string NetType;
            public double? InvStart;
            public double? InvEnd;
            public double ManningsN;
            public double CoverMin;
            public string PipeFamily;     // catalogId elegido en Python (basename del .xml)
            public string PipeSize;       // p.ej. "48 in"
        }

        private class ImportStruct
        {
            public Point2d Location;
            public string Id;
            public double? Rim;
            public double? Sump;
            public string Part;
            public string PartSize;                 // tamaño elegido en el diálogo (ej "48 in")
            public bool Covered = true;
            public string NetKind = "gravity";      // "gravity" | "pressure"
        }
    }
}
