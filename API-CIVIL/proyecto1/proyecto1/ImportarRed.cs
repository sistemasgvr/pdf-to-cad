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
        // Gate global para logs diagnósticos que ensucian la consola del cliente
        // (todos los mensajes con prefijo [TAG] tipo [ATP-*], [CURVA-*], [PIPE-CREADO], etc.).
        // Cambiar a true SOLO cuando se depura un problema puntual.
        internal const bool DEBUG_LOGS = false;
        internal static void Dl(Editor ed, string s) { if (DEBUG_LOGS) ed.WriteMessage(s); }

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
            // Registro de piezas sólidas de ESTE import (lo consultan las
            // conexiones verticales para reemplazar un codo por una Wye).
            WyeSolido.Creadas.Clear();
            Dbg("IMPORTAR_RED_INICIO", ("timestamp", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")));
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Qué DLL está corriendo de verdad. NETLOAD en la misma sesión NO
            // reemplaza un ensamblado ya cargado (.NET no los descarga): sin esta
            // línea, una prueba con el plugin viejo parece un fallo del nuevo.
            try
            {
                string dll = System.Reflection.Assembly.GetExecutingAssembly().Location;
                ed.WriteMessage($"\n· Plugin: {System.IO.Path.GetFileName(dll)} compilado " +
                    $"{System.IO.File.GetLastWriteTime(dll):yyyy-MM-dd HH:mm} — {dll}");
            }
            catch { }

            // ── 0. Forzar unidades imperiales (pies) antes de leer cotas ────
            ComandosUnidades.ForzarImperial(db, ed, true);

            // ── 0.b Familias PERSONALIZADAS (Bancoductos / Bancos Tubos / Buzones):
            //        NO agregarlas todas automáticamente. Antes se llamaba a
            //        `CatalogoBancos.AddBancosYBuzones` acá, pero eso metía TODAS las
            //        familias custom en la Parts List — y bastaba con eso para que
            //        una pipe sin `pipe_family` explícito terminara heredando una
            //        custom porque quedaba entre las candidatas del matcher.
            //        Ahora las custom SOLO se agregan bajo demanda: cada pipe/struct
            //        que traiga `PIPE_FAMILY`/`PART` en su XDATA dispara un
            //        `AsegurarFamiliaPorId` puntual más adelante en el flujo. Si el
            //        usuario no seteó familia para una pipe, esa pipe no toca custom.

            // ── 1. Escanear modelspace ──────────────────────────────────────
            var pipes = new List<ImportPipe>();
            var structs = new List<ImportStruct>();
            var curveCorners = new List<ImportCurveInfo>();
            var ductBanks = new List<ImportDuctBank>();
            var crossConns = new List<ImportCrossConnect>();
            string csCode = "";        // sistema de coordenadas (Huso) pedido desde Python (PDFCAD_META)

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

                        var noMan = new HashSet<int>();
                        string noManStr = XdStr(xd, "NO_MANHOLE_VERTS", "");
                        if (!string.IsNullOrWhiteSpace(noManStr))
                            foreach (string t in noManStr.Split(new[] { ',', ' ', ';' }, StringSplitOptions.RemoveEmptyEntries))
                                if (int.TryParse(t.Trim(), out int vi)) noMan.Add(vi);

                        // SEG_OVERRIDES: 'idx~family~size;idx~family~size'
                        var segOv = new Dictionary<int, (string fam, string size)>();
                        string segOvStr = XdStr(xd, "SEG_OVERRIDES", "");
                        if (!string.IsNullOrWhiteSpace(segOvStr))
                            foreach (string entry in segOvStr.Split(';'))
                            {
                                if (string.IsNullOrWhiteSpace(entry)) continue;
                                var parts = entry.Split('~');
                                if (parts.Length < 3) continue;
                                if (!int.TryParse(parts[0], out int idx)) continue;
                                segOv[idx] = (parts[1] ?? "", parts[2] ?? "");
                            }

                        // VERTEX_INV: 'idx~z;idx~z' — cota explícita para el lado
                        // SALIENTE del vértice (inicio del tramo siguiente).
                        // VERTEX_INV_IN: ídem pero para el lado ENTRANTE (fin del
                        // tramo anterior). Si VERTEX_INV_IN está vacío, se usa
                        // VERTEX_INV para ambos lados (retrocompat).
                        var vertexInv = ParseVertexInv(XdStr(xd, "VERTEX_INV", ""), k);
                        string viInStr = XdStr(xd, "VERTEX_INV_IN", "");
                        var vertexInvIn = string.IsNullOrWhiteSpace(viInStr)
                            ? new Dictionary<int, double>(vertexInv)
                            : ParseVertexInv(viInStr, k);

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
                            PipeGuid = XdStr(xd, "PIPE_GUID", ""),
                            PipeSize = XdStr(xd, "PIPE_SIZE", ""),
                            NoManholeVerts = noMan,
                            SegOverrides = segOv,
                            VertexInv = vertexInv,
                            VertexInvIn = vertexInvIn,
                            Abandoned = XdStr(xd, "ABANDONED", "0").Trim() == "1",
                            NetName = XdStr(xd, "NET_NAME", ""),
                            PipeIdx = string.IsNullOrWhiteSpace(XdStr(xd, "PIPE_IDX", "")) ? -1 : (int)XdDouble(xd, "PIPE_IDX"),
                            HasDuctBank = XdStr(xd, "HAS_DUCT_BANK", "0").Trim() == "1",
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
                            PartGuid = XdStr(xd, "PART_GUID", ""),
                            PartSize = XdStr(xd, "PART_SIZE", ""),
                            Covered = XdStr(xd, "COVERED", "1") != "0",
                            NetKind = XdStr(xd, "NET_KIND", "gravity"),
                            // Ya viene en pies desde Python (spinbox "Altura (Pies)") — sin
                            // aplicar el factor de conversión k que sí usan RIM/SUMP.
                            HeightFt = XdNullDouble(xd, "HEIGHT_FT"),
                            Hidden = XdStr(xd, "HIDDEN", "0") == "1",
                        };
                        structs.Add(newSt);
                        Dbg("XDATA_STRUCT", ("id", newSt.Id), ("x", pt.Position.X.ToString("F3")),
                            ("y", pt.Position.Y.ToString("F3")), ("net", newSt.NetKind),
                            ("part", newSt.Part), ("part_size", newSt.PartSize),
                            ("covered", newSt.Covered ? "1" : "0"),
                            ("rim", newSt.Rim?.ToString("F3") ?? ""),
                            ("sump", newSt.Sump?.ToString("F3") ?? ""),
                            ("height_ft", newSt.HeightFt?.ToString("F3") ?? ""),
                            ("hidden", newSt.Hidden ? "1" : "0"));
                    }
                    else if (marker == "PDFCAD_CURVE" && ent is DBPoint ptc)
                    {
                        // Esquina de un elemento curvo (p.ej. codo de bancoducto): la
                        // familia/tamaño de la curva NO se leen de aquí — se resuelven
                        // más abajo de la MISMA tubería recta que pasa por este vértice
                        // (ip.NoManholeVerts ya identifica cuál). Solo interesa la
                        // ubicación y el radio explícito (vacío = automático, 6× ancho).
                        var newCv = new ImportCurveInfo
                        {
                            Location = new Point2d(ptc.Position.X, ptc.Position.Y),
                            Id = XdStr(xd, "STRUCT_ID", ""),
                            RadiusFt = XdNullDouble(xd, "RADIUS_FT"),
                        };
                        curveCorners.Add(newCv);
                        Dbg("XDATA_CURVE", ("id", newCv.Id), ("x", ptc.Position.X.ToString("F3")),
                            ("y", ptc.Position.Y.ToString("F3")),
                            ("radius_ft", newCv.RadiusFt?.ToString("F3") ?? "(auto)"));
                    }
                    else if (marker == "PDFCAD_META")
                    {
                        string c = XdStr(xd, "CS_CODE", "");
                        if (!string.IsNullOrWhiteSpace(c)) csCode = c.Trim();
                        Dbg("XDATA_META", ("cs_code", csCode));
                    }
                    else if (marker == "PDFCAD_DUCTBANK" && ent is DBPoint ptDb)
                    {
                        var dbk = new ImportDuctBank
                        {
                            Anchor = new Point2d(ptDb.Position.X, ptDb.Position.Y),
                            PipeIdx = (int)XdDouble(xd, "PIPE_IDX"),
                            Name = XdStr(xd, "NAME", ""),
                            WidthIn = XdDouble(xd, "WIDTH_IN"),
                            HeightIn = XdDouble(xd, "HEIGHT_IN"),
                            MarginTop = XdDouble(xd, "MARGIN_TOP"),
                            MarginRight = XdDouble(xd, "MARGIN_RIGHT"),
                            MarginBottom = XdDouble(xd, "MARGIN_BOTTOM"),
                            MarginLeft = XdDouble(xd, "MARGIN_LEFT"),
                            CornerTL = XdDouble(xd, "CORNER_TL"),
                            CornerTR = XdDouble(xd, "CORNER_TR"),
                            CornerBR = XdDouble(xd, "CORNER_BR"),
                            CornerBL = XdDouble(xd, "CORNER_BL"),
                            // RENDER_ENVELOPE: 1 = crear sólido 3D (default), 0 = solo conductos.
                            // Si el DXF es viejo y no trae el flag, XdDouble devuelve 0
                            // pero eso sería incorrecto — chequear existencia con XdStr.
                            RenderEnvelope = (XdStr(xd, "RENDER_ENVELOPE", "1").Trim() != "0"),
                        };
                        string conduitsRaw = XdStr(xd, "CONDUITS", "");
                        if (!string.IsNullOrWhiteSpace(conduitsRaw))
                        {
                            foreach (string tok in conduitsRaw.Split('|'))
                            {
                                var p2 = tok.Split(',');
                                if (p2.Length < 3) continue;
                                double cx, cy, dm;
                                if (!double.TryParse(p2[0], NumberStyles.Float, CultureInfo.InvariantCulture, out cx)) continue;
                                if (!double.TryParse(p2[1], NumberStyles.Float, CultureInfo.InvariantCulture, out cy)) continue;
                                if (!double.TryParse(p2[2], NumberStyles.Float, CultureInfo.InvariantCulture, out dm)) continue;
                                dbk.Conduits.Add(new DuctConduit
                                {
                                    Cx = cx, Cy = cy, Diam = dm,
                                    Label = p2.Length > 3 ? p2[3] : "",
                                });
                            }
                        }
                        ductBanks.Add(dbk);
                        Dbg("XDATA_DUCTBANK", ("name", dbk.Name),
                            ("pipe_idx", dbk.PipeIdx), ("w", dbk.WidthIn), ("h", dbk.HeightIn),
                            ("conduits", dbk.Conduits.Count));
                    }
                    else if (marker == "PDFCAD_CROSS_CONNECT" && ent is DBPoint ptCC)
                    {
                        double k = pipes.Count > 0 ? FactorConversion(pipes[0].Unit, db) : 1.0;
                        var cc = new ImportCrossConnect
                        {
                            X = ptCC.Position.X * k,
                            Y = ptCC.Position.Y * k,
                            PipeA = string.IsNullOrWhiteSpace(XdStr(xd, "PIPE_A", "")) ? -1 : (int)XdDouble(xd, "PIPE_A"),
                            PipeB = string.IsNullOrWhiteSpace(XdStr(xd, "PIPE_B", "")) ? -1 : (int)XdDouble(xd, "PIPE_B"),
                            ZA = MulNull(XdNullDouble(xd, "Z_A"), k),
                            ZB = MulNull(XdNullDouble(xd, "Z_B"), k),
                            Valve = XdStr(xd, "VALVE", "1").Trim() != "0",
                        };
                        crossConns.Add(cc);
                    }
                }
                trScan.Commit();
            }

            // Setear el sistema de coordenadas (Huso) del dibujo con el código
            // pedido desde Python. Best-effort: si el código es inválido se avisa,
            // pero NO se aborta la importación de la red.
            if (!string.IsNullOrWhiteSpace(csCode))
                AplicarSistemaCoordenadas(ed, csCode);

            // Emparejar cada esquina curva con el vértice NoManholeVerts más cercano
            // de su tubería (tolerancia 1 ft, igual criterio que FindNearestStruct).
            foreach (var ip in pipes)
            {
                for (int vi = 0; vi < ip.Vertices.Count; vi++)
                {
                    if (!ip.NoManholeVerts.Contains(vi)) continue;
                    ImportCurveInfo best = null; double bestD = 1.0;
                    foreach (var cv in curveCorners)
                    {
                        double d = cv.Location.GetDistanceTo(ip.Vertices[vi]);
                        if (d < bestD) { bestD = d; best = cv; }
                    }
                    if (best != null && best.RadiusFt.HasValue)
                    {
                        ip.CurveRadiusByVert[vi] = best.RadiusFt.Value;
                        Dl(ed, $"\n  [CURVA-MATCH] '{ip.Layer}' v{vi} ↔ esquina '{best.Id}' dist={bestD:F3}ft → radio={best.RadiusFt.Value:F2}ft");
                    }
                    else if (best == null)
                        Dl(ed, $"\n  [CURVA-NO-MATCH] '{ip.Layer}' v{vi} — ninguna esquina PDFCAD_CURVE a ≤1ft → radio auto");
                    else
                        Dl(ed, $"\n  [CURVA-AUTO] '{ip.Layer}' v{vi} ↔ esquina '{best.Id}' — RADIUS_FT vacío → radio auto");
                }
            }

            if (pipes.Count == 0)
            {
                ed.WriteMessage("\nNo se encontraron polilíneas con XDATA 'PDFCAD'. " +
                                "¿Es un DXF exportado desde la app de marcado (pdf-to-cad)?");
                return;
            }

            string unit = pipes[0].Unit;
            double factor = FactorConversion(unit, db);
            ed.WriteMessage("\n\n╔══════════════════════════════════════════════════════════════════╗");
            ed.WriteMessage("\n║                    ▶▶▶  IMPORTAR RED — INICIO  ◀◀◀               ║");
            ed.WriteMessage("\n╚══════════════════════════════════════════════════════════════════╝");
            ed.WriteMessage($"\nDetectadas: {pipes.Count} tubería(s), {structs.Count} buzón(es). Unidad XDATA: {unit} · dibujo: {db.Insunits}.");
            if (Math.Abs(factor - 1.0) > 1e-9)
                ed.WriteMessage($"\n  → Conversión de elevaciones {unit} → {db.Insunits}: ×{factor:F4}");

            // ── 2. Agrupar por capa ─────────────────────────────────────────
            // Pipes con duct bank asignado (HAS_DUCT_BANK=1 en XDATA): a partir
            // de v1.1.1 se PROCESAN NORMALMENTE — así generan sus buzones en
            // cada vértice (1 por vértice, no N como antes cuando la pipe padre
            // se excluía y cada conducto interno creaba su propia estructura).
            // El sólido 3D del bancoducto se dibuja ENCIMA de la pipe padre
            // (opcional, según flag RENDER_ENVELOPE). Los conductos internos
            // se crean como pipes sin estructuras propias (NoStructuresAll).
            var pipeByIdx = new Dictionary<int, ImportPipe>();
            foreach (var ip in pipes)
            {
                if (ip.PipeIdx >= 0)
                    pipeByIdx[ip.PipeIdx] = ip;
            }
            foreach (var dbk in ductBanks)
            {
                ImportPipe match;
                if (pipeByIdx.TryGetValue(dbk.PipeIdx, out match))
                    dbk.MatchedPipe = match;
                else
                    ed.WriteMessage($"\n  ⚠ Duct bank '{dbk.Name}' (PIPE_IDX={dbk.PipeIdx}): no se encontró la pipe correspondiente.");
            }
            if (ductBanks.Count > 0)
                ed.WriteMessage($"\n  · {ductBanks.Count} bancoducto(s) — sus pipes padre se procesan normalmente para generar buzones.");

            // Forzar radio de curva del pipe padre = radio del sólido del
            // bancoducto en cada vértice curvo, cuando el usuario dejó "auto"
            // (sin entrada en CurveRadiusByVert). El fallback estándar del pipe
            // es 6× su diámetro interior (pequeño); si no lo forzamos aquí, el
            // pipe padre curva con radio distinto al del sólido y se sale.
            foreach (var dbk in ductBanks)
            {
                if (dbk.MatchedPipe == null) continue;
                var parent = dbk.MatchedPipe;
                double bancoRadioFt = 6.0 * (dbk.WidthIn / 12.0);
                foreach (int viCurve in parent.NoManholeVerts)
                {
                    if (!parent.CurveRadiusByVert.ContainsKey(viCurve))
                        parent.CurveRadiusByVert[viCurve] = bancoRadioFt;
                }
            }

            var gravedad = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);
            var presion = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);

            var conduit = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);
            var redPorTubo = RedesUnidasPorContacto(pipes);
            foreach (var p in pipes)
            {
                string grpKey = redPorTubo[p];
                if (p.NetKind.Equals("pressure", StringComparison.OrdinalIgnoreCase))
                    DictAdd(presion, grpKey, p);
                else if (p.NetKind.Equals("conduit", StringComparison.OrdinalIgnoreCase))
                    DictAdd(conduit, grpKey, p);
                else
                    DictAdd(gravedad, grpKey, p);
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
            var alignmentsPendientes = new List<DatosAlignment>();
            foreach (var kv in gravedad)
            {
                bool hasCustomName = kv.Value.Any(pp => !string.IsNullOrWhiteSpace(pp.NetName));
                string netName = hasCustomName ? kv.Key : $"RED-{kv.Key}";
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        ObjectId netId = CrearRedGravedadCompleta(ed, db, civilDoc, tr,
                            netName, surfId, defaultDepth, kv.Value, structsGravedad,
                            sinBuzones: false, out List<DatosAlignment> dAligns);
                        if (netId != ObjectId.Null) createdNetIds.Add(netId);
                        if (dAligns != null) alignmentsPendientes.AddRange(dAligns);
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
                bool hasCustomName = kv.Value.Any(pp => !string.IsNullOrWhiteSpace(pp.NetName));
                string netName = hasCustomName ? kv.Key : $"RED-{kv.Key}";
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        ObjectId netId = CrearRedGravedadCompleta(ed, db, civilDoc, tr,
                            netName, surfId, defaultDepth, kv.Value,
                            structsConduit, sinBuzones: true, out List<DatosAlignment> dAligns);
                        if (netId != ObjectId.Null) createdNetIds.Add(netId);
                        if (dAligns != null) alignmentsPendientes.AddRange(dAligns);
                        tr.Commit();
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n✗ Error red conduit '{netName}': {ex.Message}");
                        tr.Abort();
                    }
                }
            }

            // ── 4c. ALINEAMIENTOS — se crean POST-commit para que GeometricExtents
            //        de las structures ya esté rendido, y el recorté del eje al
            //        borde exterior del buzón funcione correctamente.
            foreach (var dAlign in alignmentsPendientes)
            {
                using (Transaction trAli = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        // Recortar extremos al borde visible del buzón conectado.
                        if (dAlign.Traza.Count >= 2)
                        {
                            // Nota: se conserva el Bulge de cada punto al reescribirlo
                            // (el recorte solo mueve X/Y del extremo).
                            if (!dAlign.StartStructId.IsNull)
                            {
                                try
                                {
                                    TrazaPt t0 = dAlign.Traza[0];
                                    Point3d p0 = t0.P, p1 = dAlign.Traza[1].P;
                                    Point3d p0Rec = RecortarAlBordeBuzon(trAli, dAlign.StartStructId, p0, p1);
                                    dAlign.Traza[0] = new TrazaPt(new Point3d(p0Rec.X, p0Rec.Y, p0.Z), t0.Bulge);
                                }
                                catch (Exception exR) { Dbg("RECORTE_START_ERR", ("msg", exR.Message)); }
                            }
                            if (!dAlign.EndStructId.IsNull)
                            {
                                try
                                {
                                    int lastIdx = dAlign.Traza.Count - 1;
                                    TrazaPt tN = dAlign.Traza[lastIdx];
                                    Point3d pN = tN.P, pPrev = dAlign.Traza[lastIdx - 1].P;
                                    Point3d pNRec = RecortarAlBordeBuzon(trAli, dAlign.EndStructId, pN, pPrev);
                                    dAlign.Traza[lastIdx] = new TrazaPt(new Point3d(pNRec.X, pNRec.Y, pN.Z), tN.Bulge);
                                }
                                catch (Exception exR) { Dbg("RECORTE_END_ERR", ("msg", exR.Message)); }
                            }
                        }
                        ObjectId alignId = ComandosAlineamientos.CrearAlineamientoDesdePts(
                            db, civilDoc, trAli, dAlign.Traza, dAlign.Nombre + "-eje");
                        // Asociar el alignment a la network SOLO para gravedad.
                        if (alignId != ObjectId.Null && dAlign.EsGravedad && !dAlign.NetId.IsNull)
                        {
                            try
                            {
                                var netW = trAli.GetObject(dAlign.NetId, OpenMode.ForWrite) as CivilDB.Network;
                                if (netW != null) netW.ReferenceAlignmentId = alignId;
                            }
                            catch { }
                        }
                        if (alignId != ObjectId.Null)
                            ed.WriteMessage($"\n  · Eje '{dAlign.Nombre}-eje' creado.");
                        trAli.Commit();
                    }
                    catch (Exception exAli)
                    {
                        Dbg("ALIGN_ERR", ("red", dAlign.Nombre), ("msg", exAli.Message));
                        ed.WriteMessage($"\n(No se pudo crear el eje '{dAlign.Nombre}-eje': {exAli.Message} — la red se dibuja igual.)");
                        trAli.Abort();
                    }
                }
            }

            // ── 5. Redes de PRESIÓN ─────────────────────────────────────────
            var createdPresIds = new List<ObjectId>();
            foreach (var kv in presion)
            {
                bool hasCustomName = kv.Value.Any(pp => !string.IsNullOrWhiteSpace(pp.NetName));
                string netName = hasCustomName ? kv.Key : $"RED-{kv.Key}";
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

            // ── 5c. Limpiar duplicados "-N" con dimensiones idénticas al padre ──
            // Debe correr DESPUÉS de crear las redes (pasos 4-5): CatalogoBancos.AddBancosYBuzones
            // (paso 0.b) y el propio AddPartSize de Civil3D pueden dejar variantes "- N" al
            // agregar tamaños del catálogo; limpiar antes (como estaba) no encontraba nada que limpiar.
            // NOTA: BuscarEstructura/BuscarTuberia ya NO crean tamaños dinámicamente — solo
            // eligen entre los que ya existen en el catálogo (ver RedesTuberia.cs, SizeMasCercano).
            LimpiarDuplicadosPartSize(ed, db);

            // ── 5d. Duct Banks — sólidos 3D ────────────────────────────────
            if (ductBanks.Count > 0)
            {
                using (Transaction trDb = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        CrearDuctBanks(ed, db, trDb, ductBanks, pipes);
                        trDb.Commit();
                    }
                    catch (Exception exDb)
                    {
                        ed.WriteMessage($"\n✗ Error duct banks: {exDb.Message}");
                        trDb.Abort();
                    }
                }
            }

            // ── 5e. Duct Bank — conductos internos como Pipe Network ────────
            var familyByDiam = new Dictionary<double, string>();
            // Cuando el diámetro pedido no lo acepta ninguna familia (típico
            // de Ø <2" en catálogos AWWA / DIP), guardamos aquí un fallback
            // con el TAMAÑO MÍNIMO existente en la primera familia — así el
            // conducto se dibuja con un pipe pequeño (2/3") en vez del
            // default gigante (12" Concrete Pipe).
            var fallbackByDiam = new Dictionary<double, (string fam, string size)>();
            {
                var conduitDiams = new HashSet<double>();
                foreach (var dbk in ductBanks)
                    foreach (var cond in dbk.Conduits)
                        if (cond.Diam > 0) conduitDiams.Add(cond.Diam);
                if (conduitDiams.Count > 0)
                {
                    using (Transaction trPre = db.TransactionManager.StartTransaction())
                    {
                        try
                        {
                            var plPre = ObtenerPartsList(civilDoc, trPre);
                            if (plPre != null)
                            {
                                try { plPre.UpgradeOpen(); } catch { }
                                foreach (double cd in conduitDiams)
                                {
                                    string famAceptante = null;
                                    // Pasada 1: familias con XML de Autodesk (DIP/HDPE/…).
                                    foreach (ObjectId fid in plPre.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
                                    {
                                        try
                                        {
                                            var fam = trPre.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                                            if (fam == null) continue;
                                            if (InyectarTamañoEnCatalogo(trPre, fam, cd, ed, wallOverride: 0.0))
                                            {
                                                famAceptante = fam.Description ?? "";
                                                break;
                                            }
                                        }
                                        catch { }
                                    }
                                    // Pasada 2: si nadie del catálogo Autodesk aceptó (típico
                                    // Ø1"), probar SizeFilter directo en TODAS las familias
                                    // (incluye customs de Part Builder que no tienen XML en
                                    // ProgramData — hasta ahora las saltábamos, y son las
                                    // más aptas para diámetros exóticos).
                                    if (famAceptante == null)
                                    {
                                        foreach (ObjectId fid in plPre.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
                                        {
                                            try
                                            {
                                                var fam = trPre.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                                                if (fam == null) continue;
                                                int antes = fam.PartSizeCount;
                                                if (ComandosRedes.AgregarTamañoPipePublico(trPre, fam, cd, ed))
                                                {
                                                    if (fam.PartSizeCount > antes)
                                                    {
                                                        famAceptante = fam.Description ?? "";
                                                        Dl(ed, $"\n  [DUCTBANK-FAMILY-CUSTOM] Ø{cd:F0}\" aceptado directo por '{famAceptante}'.");
                                                        break;
                                                    }
                                                }
                                            }
                                            catch { }
                                        }
                                    }
                                    if (famAceptante != null)
                                    {
                                        familyByDiam[cd] = famAceptante;
                                        Dl(ed, $"\n  [DUCTBANK-FAMILY] Ø{cd:F0}\" → familia '{famAceptante}'.");
                                    }
                                    else
                                    {
                                        // Fallback: elegir el tamaño MÁS CERCANO al pedido
                                        // (en cualquier familia, incluyendo customs). Así
                                        // Ø1" prefiere una familia custom con 1" (p.ej.
                                        // "Iluminacion CBA Imperial") sobre DIP con 2".
                                        // Además el override runtime forzará wall=0 y
                                        // ajustará el inner al pedido — con esto el visual
                                        // sale del tamaño correcto aunque el PartSize base
                                        // sea de otro diámetro.
                                        string famFB = null, sizeFB = null;
                                        double diamBestFB = 0.0;
                                        double bestDist = double.MaxValue;
                                        foreach (ObjectId fid in plPre.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
                                        {
                                            var f = trPre.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                                            if (f == null || f.PartSizeCount == 0) continue;
                                            for (int si = 0; si < f.PartSizeCount; si++)
                                            {
                                                var sz = trPre.GetObject(f[si], OpenMode.ForRead) as PartsStyles.PartSize;
                                                var mm = System.Text.RegularExpressions.Regex.Match(
                                                    (sz?.Name ?? "").Trim(), @"^(\d+(?:\.\d+)?)");
                                                if (!mm.Success) continue;
                                                if (double.TryParse(mm.Groups[1].Value,
                                                        System.Globalization.NumberStyles.Float,
                                                        System.Globalization.CultureInfo.InvariantCulture,
                                                        out double dv))
                                                {
                                                    double dist = Math.Abs(dv - cd);
                                                    if (dist < bestDist)
                                                    {
                                                        bestDist = dist;
                                                        diamBestFB = dv;
                                                        famFB = f.Description;
                                                        sizeFB = sz.Name;
                                                    }
                                                }
                                            }
                                        }
                                        if (famFB != null)
                                        {
                                            fallbackByDiam[cd] = (famFB, sizeFB);
                                            ed.WriteMessage($"\n  ⚠ Conducto Ø{cd:F0}\" no aceptado por ninguna familia — se usará el más cercano: '{famFB} / {sizeFB}' ({diamBestFB:F0}\"). El plugin sobrescribirá el inner runtime al pedido.");
                                        }
                                        else
                                            ed.WriteMessage($"\n  ⚠ Conducto Ø{cd:F0}\" no se pudo crear y no hay familias con tamaños válidos como fallback.");
                                    }
                                }
                            }
                            trPre.Commit();
                        }
                        catch (Exception exPre)
                        {
                            ed.WriteMessage($"\n  (Error pre-scan conductos: {exPre.Message})");
                            trPre.Abort();
                        }
                    }
                }
            }
            // Cada conducto se crea como su propia red independiente: dos conductos
            // con vértices idénticos en la misma red son rechazados por Civil 3D.
            // Los vértices se offsetean lateralmente según la posición cx del
            // conducto dentro de la envolvente, dando geometría única a cada uno.
            int conduitNetCount = 0;
            foreach (var dbk in ductBanks)
            {
                if (dbk.MatchedPipe == null || dbk.Conduits.Count == 0) continue;
                var parent = dbk.MatchedPipe;
                string baseName = string.IsNullOrWhiteSpace(dbk.Name) ? $"P{dbk.PipeIdx}" : dbk.Name;

                for (int ci = 0; ci < dbk.Conduits.Count; ci++)
                {
                    var cond = dbk.Conduits[ci];
                    if (cond.Diam <= 0) continue;

                    // Offset lateral (cx) relativo al centro de la envolvente.
                    // Offset vertical (cy) relativo al FONDO EXTERNO del bancoducto
                    // (cara inferior). La cota invert del pipe padre manda el fondo
                    // externo — igual que un pipe normal: invert = parte inferior.
                    //   cy=height_in (fondo del diseñador) → offset 0 ft (Z=invert)
                    //   cy=0         (tapa del diseñador)  → offset +hFt (Z=invert+hFt)
                    double cxOffsetFt = (cond.Cx - dbk.WidthIn / 2.0) / 12.0;
                    double cyOffsetFt = (dbk.HeightIn - cond.Cy) / 12.0;
                    ed.WriteMessage($"\n  [CONDUIT] {cond.Label ?? $"C{ci+1}"} Ø{cond.Diam:F1}\" " +
                        $"cx={cond.Cx:F2} cy={cond.Cy:F2} → lateral={cxOffsetFt:F4}ft " +
                        $"desde-fondo={cyOffsetFt:F4}ft (envolvente {dbk.WidthIn:F1}×{dbk.HeightIn:F1}\")");

                    // Z absoluta del conducto: parentInv (= fondo del bancoducto) +
                    // offset vertical (centro del conducto por encima del fondo) −
                    // radio (porque el flujo posterior sumará radio para pasar de
                    // invert→centerline; cy es el CENTRO del conducto).
                    double radiusFt = cond.Diam / 2.0 / 12.0;
                    double parentInvS = parent.InvStart ?? 0.0;
                    double parentInvE = parent.InvEnd ?? parentInvS;
                    double condInvS = parentInvS + cyOffsetFt - radiusFt;
                    double condInvE = parentInvE + cyOffsetFt - radiusFt;

                    // Cotas por tramo (VertexInv/VertexInvIn) del padre se
                    // propagan al conducto con el MISMO offset vertical — así las
                    // cotas por vértice que el usuario ajustó en la tubería padre
                    // aplican también al conducto interno.
                    var condVertexInv = new Dictionary<int, double>();
                    var condVertexInvIn = new Dictionary<int, double>();
                    if (parent.VertexInv != null)
                        foreach (var kv in parent.VertexInv)
                            condVertexInv[kv.Key] = kv.Value + cyOffsetFt - radiusFt;
                    if (parent.VertexInvIn != null)
                        foreach (var kv in parent.VertexInvIn)
                            condVertexInvIn[kv.Key] = kv.Value + cyOffsetFt - radiusFt;

                    // Calcular vértices offseteados perpendicular al path
                    var offsetVerts = new List<Point2d>();
                    for (int vi = 0; vi < parent.Vertices.Count; vi++)
                    {
                        Point2d v = parent.Vertices[vi];
                        // Dirección del segmento (hacia adelante o atrás según posición)
                        Point2d next = vi < parent.Vertices.Count - 1 ? parent.Vertices[vi + 1] : parent.Vertices[vi];
                        Point2d prev = vi > 0 ? parent.Vertices[vi - 1] : parent.Vertices[vi];
                        double dx, dy;
                        if (vi == 0)
                        { dx = next.X - v.X; dy = next.Y - v.Y; }
                        else if (vi == parent.Vertices.Count - 1)
                        { dx = v.X - prev.X; dy = v.Y - prev.Y; }
                        else
                        {
                            // Vértice intermedio: bisectriz de los segmentos adyacentes
                            double dx1 = v.X - prev.X, dy1 = v.Y - prev.Y;
                            double dx2 = next.X - v.X, dy2 = next.Y - v.Y;
                            double len1 = Math.Sqrt(dx1 * dx1 + dy1 * dy1);
                            double len2 = Math.Sqrt(dx2 * dx2 + dy2 * dy2);
                            if (len1 > 1e-9) { dx1 /= len1; dy1 /= len1; }
                            if (len2 > 1e-9) { dx2 /= len2; dy2 /= len2; }
                            dx = dx1 + dx2; dy = dy1 + dy2;
                        }
                        double len = Math.Sqrt(dx * dx + dy * dy);
                        if (len < 1e-9) { offsetVerts.Add(v); continue; }
                        // Perpendicular a la derecha: (dy, -dx) normalizado
                        double perpX = dy / len;
                        double perpY = -dx / len;
                        offsetVerts.Add(new Point2d(v.X + perpX * cxOffsetFt,
                                                    v.Y + perpY * cxOffsetFt));
                    }

                    string label = !string.IsNullOrWhiteSpace(cond.Label) ? cond.Label : $"C{ci + 1}";
                    string netName = $"DUCTBANK-{baseName}-{label}";
                    // Vértices curvos del padre se propagan al conducto interno
                    // — así si el usuario marcó una esquina como "curva" en la
                    // pipe padre, TODOS los conductos del bancoducto se
                    // dibujarán curvos en esa esquina (antes solo se curvaba
                    // uno arbitrario porque solo la pipe padre tenía la data).
                    var condNoManhole = new HashSet<int>(parent.NoManholeVerts);
                    var condCurveRadius = new Dictionary<int, double>(parent.CurveRadiusByVert);
                    // Radio AUTOMÁTICO del bancoducto: si el usuario dejó "auto"
                    // (no hay entrada en CurveRadiusByVert), calculamos el radio
                    // que el sólido del bancoducto usará (6 × ancho del banco)
                    // y lo forzamos como radio EXPLÍCITO en el conducto. Así
                    // sólido y conductos comparten exactamente el mismo arco —
                    // antes cada conducto calculaba su propio radio "6× ancho
                    // interior del conducto" (mucho menor), y los conductos se
                    // salían del sólido en la curva.
                    double bancoRadioFt = 6.0 * (dbk.WidthIn / 12.0);
                    foreach (int viCurve in parent.NoManholeVerts)
                    {
                        if (condCurveRadius.ContainsKey(viCurve)) continue;
                        // Radio del conducto = radio del sólido ± cxOffset,
                        // según de qué lado del giro esté el conducto (para que
                        // el arco quede CONCÉNTRICO con el sólido, no sólo
                        // paralelo). perp de la pipe padre = (dy,-dx) = LADO
                        // DERECHO del avance. Turn LEFT (cross>0) → derecha es
                        // exterior → radio mayor. Turn RIGHT (cross<0) → derecha
                        // es interior → radio menor.
                        double rCond = bancoRadioFt;
                        if (viCurve > 0 && viCurve < parent.Vertices.Count - 1)
                        {
                            var vp = parent.Vertices[viCurve - 1];
                            var vc = parent.Vertices[viCurve];
                            var vn = parent.Vertices[viCurve + 1];
                            double ax = vc.X - vp.X, ay = vc.Y - vp.Y;
                            double bx = vn.X - vc.X, by = vn.Y - vc.Y;
                            double cross = ax * by - ay * bx;
                            double signo = cross > 0 ? +1.0 : -1.0;
                            rCond = bancoRadioFt + signo * cxOffsetFt;
                            if (rCond < 0.01) rCond = 0.01;
                        }
                        condCurveRadius[viCurve] = rCond;
                    }
                    // Conductos de bancoducto: SIEMPRE se dibujan como Solid3d
                    // cilíndricos directos en la capa PDFCAD_DUCT_BANK.
                    //
                    // Motivo: las Pipe Network families añaden espesor de pared
                    // (outer = inner + 2·wall) que hace que los conductos se
                    // salgan de la envolvente y se pisen entre sí. En C3D 2027
                    // EN, además, el SizeFilter tiene una lista cerrada de
                    // diámetros y rechaza valores exóticos como Ø1".
                    //
                    // Solid3d resuelve las dos cosas: diámetro exacto (no hay
                    // wall thickness), y sirve para cualquier versión/idioma
                    // de Civil 3D. Trade-off: los conductos dejan de ser
                    // entidades editables como Pipe Network — quedan como
                    // geometría 3D pura. Aceptable porque son solo visuales
                    // (el ducto padre sigue siendo la Pipe Network real).
                    if (true)
                    {
                        int drawn = 0, seg = 0;
                        using (Transaction trCyl = db.TransactionManager.StartTransaction())
                        {
                            try
                            {
                                var bt = trCyl.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
                                var ms = trCyl.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;
                                // Construir Z's por vértice (invert + radio) idéntico
                                // a lo que hace CrearRedGravedadCompleta.
                                int nV = offsetVerts.Count;
                                double invS = condInvS, invE = condInvE;
                                var pts3d = new List<Point3d>();
                                for (int vi2 = 0; vi2 < nV; vi2++)
                                {
                                    double t = nV > 1 ? (double)vi2 / (nV - 1) : 0.0;
                                    double invZ;
                                    if (condVertexInv.TryGetValue(vi2, out double vz)) invZ = vz;
                                    else invZ = invS + t * (invE - invS);
                                    // Centerline = invert + radio (mismo criterio que Pipe Network)
                                    pts3d.Add(new Point3d(offsetVerts[vi2].X,
                                                          offsetVerts[vi2].Y,
                                                          invZ + radiusFt));
                                }
                                // Un cilindro por segmento (Solid3d.CreateFrustum es cilindro
                                // alineado al eje Z; luego lo trasladamos y rotamos).
                                for (int si = 0; si < pts3d.Count - 1; si++)
                                {
                                    Point3d a = pts3d[si], b = pts3d[si + 1];
                                    Vector3d dir = b - a;
                                    double len = dir.Length;
                                    if (len < 1e-6) continue;
                                    seg++;
                                    try
                                    {
                                        var cyl = new Solid3d();
                                        cyl.CreateFrustum(len, radiusFt, radiusFt, radiusFt);
                                        // CreateFrustum genera el cilindro centrado en origen,
                                        // eje Z, altura = len. Centrarlo entre a y b y rotarlo
                                        // para alinearlo con dir.
                                        Point3d mid = new Point3d((a.X + b.X) / 2, (a.Y + b.Y) / 2, (a.Z + b.Z) / 2);
                                        cyl.TransformBy(Matrix3d.Displacement(mid - Point3d.Origin));
                                        // Rotar de eje Z al vector dir
                                        Vector3d zAxis = Vector3d.ZAxis;
                                        Vector3d nDir = dir / len;
                                        Vector3d cross = zAxis.CrossProduct(nDir);
                                        double dot = zAxis.DotProduct(nDir);
                                        if (cross.Length > 1e-9)
                                        {
                                            double ang = Math.Acos(Math.Max(-1, Math.Min(1, dot)));
                                            cyl.TransformBy(Matrix3d.Rotation(ang, cross.GetNormal(), mid));
                                        }
                                        else if (dot < 0)
                                        {
                                            // dir anti-paralelo a Z: rotar 180° sobre X
                                            cyl.TransformBy(Matrix3d.Rotation(Math.PI, Vector3d.XAxis, mid));
                                        }
                                        cyl.Layer = "PDFCAD_DUCT_BANK";
                                        ms.AppendEntity(cyl);
                                        trCyl.AddNewlyCreatedDBObject(cyl, true);
                                        drawn++;
                                    }
                                    catch (Exception exCyl)
                                    { Dl(ed, $"\n    [CONDUIT-SOLID-ERR] seg{si} {exCyl.Message}"); }
                                }
                                trCyl.Commit();
                            }
                            catch (Exception exOut)
                            {
                                ed.WriteMessage($"\n  ✗ Error dibujando Ø{cond.Diam:F1}\" como Solid3d: {exOut.Message}");
                                trCyl.Abort();
                            }
                        }
                        ed.WriteMessage($"\n  · Ø{cond.Diam:F1}\" (cx={cond.Cx:F1} cy={cond.Cy:F1}) → {drawn}/{seg} Solid3d cilindro(s) en 'PDFCAD_DUCT_BANK'.");
                        conduitNetCount++;
                        continue; // No crear ImportPipe/Pipe Network para este conducto
                    }

                    var cp = new ImportPipe
                    {
                        Layer = "PDFCAD_DUCT_BANK",
                        Vertices = offsetVerts,
                        Diameter = cond.Diam,
                        Unit = "in",
                        Material = "",
                        NetKind = "conduit",
                        NetType = "pipe",
                        InvStart = condInvS,
                        InvEnd = condInvE,
                        VertexInv = condVertexInv,
                        VertexInvIn = condVertexInvIn,
                        NoManholeVerts = condNoManhole,
                        CurveRadiusByVert = condCurveRadius,
                        ManningsN = 0,
                        CoverMin = 0,
                        // Familia = la que aceptó el diámetro en el pre-scan.
                        // Fallback: si el diámetro no lo aceptó nadie (típico
                        // de Ø<2" en catálogos AWWA), usamos la familia y el
                        // tamaño mínimo disponible calculado en el pre-scan —
                        // así el conducto sale con un pipe pequeño (p.ej. 2")
                        // en vez del gigante default de 12".
                        PipeFamily = familyByDiam.TryGetValue(cond.Diam, out var famName)
                                     ? famName
                                     : (fallbackByDiam.TryGetValue(cond.Diam, out var fb) ? fb.fam : ""),
                        PipeGuid = "",
                        PipeSize = familyByDiam.ContainsKey(cond.Diam)
                                   ? $"{cond.Diam:F0} in"
                                   : (fallbackByDiam.TryGetValue(cond.Diam, out var fb2) ? fb2.size : $"{cond.Diam:F0} in"),
                        Abandoned = false,
                        PipeIdx = -1,
                        HasDuctBank = false,
                        // Sin buzones propios: los buzones del bancoducto los da
                        // la pipe padre. Sin esto, N conductos = N buzones
                        // superpuestos en cada vértice.
                        NoStructuresAll = true,
                        IsConduit = true,
                        ConduitTargetDiamIn = cond.Diam,
                    };
                    var singleList = new List<ImportPipe> { cp };
                    using (Transaction trCond = db.TransactionManager.StartTransaction())
                    {
                        try
                        {
                            ObjectId nId = CrearRedGravedadCompleta(ed, db, civilDoc, trCond,
                                netName, surfId, defaultDepth, singleList,
                                new List<ImportStruct>(), sinBuzones: true,
                                out List<DatosAlignment> _);
                            if (nId != ObjectId.Null) conduitNetCount++;
                            trCond.Commit();
                        }
                        catch (Exception exCond)
                        {
                            ed.WriteMessage($"\n  ✗ Error conducto '{netName}': {exCond.Message}");
                            trCond.Abort();
                        }
                    }
                }
            }
            if (conduitNetCount > 0)
                ed.WriteMessage($"\n  · {conduitNetCount} conducto(s) de duct bank creados como Pipe Network.");

            // ── 5f. Conexiones cruzadas aprobadas (vertical + válvula) ──────
            if (crossConns.Count > 0)
            {
                using (Transaction trCC = db.TransactionManager.StartTransaction())
                {
                    try
                    {
                        CrearConexionesCruzadas(ed, db, civilDoc, trCC, pipes, crossConns);
                        trCC.Commit();
                    }
                    catch (Exception exCC)
                    {
                        ed.WriteMessage($"\n✗ Error conexiones cruzadas: {exCC.Message}");
                        trCC.Abort();
                    }
                }
            }

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

            ed.WriteMessage("\n\n╔══════════════════════════════════════════════════════════════════╗");
            ed.WriteMessage("\n║                     ▶▶▶  IMPORTAR RED — FIN  ◀◀◀                ║");
            ed.WriteMessage("\n╚══════════════════════════════════════════════════════════════════╝\n");
        }

        // =================================================================
        //  RED DE GRAVEDAD COMPLETA (auto-populate + create + diagnostics)
        // =================================================================
        // Estado que se acumula durante la creación de cada red para poder
        // construir el alineamiento DESPUÉS del commit — así GeometricExtents
        // de los buzones ya está rendido y el recorté al borde funciona bien.
        internal class DatosAlignment
        {
            public string Nombre;
            public List<TrazaPt> Traza;     // cada punto lleva el bulge de su segmento
            public ObjectId StartStructId;
            public ObjectId EndStructId;
            public ObjectId NetId;
            public bool EsGravedad;
        }

        // PipeStyle reutilizable para tuberías ABANDONADAS. Se resuelve una sola
        // vez por ejecución de IMPORTAR_RED: se copia del estilo base de la primera
        // abandonada y se le fijan los display components (Planta + Perfil + Model)
        // a un linetype discontinuo con LinetypeScale grande (huecos obvios).
        // Nota: en la vista 3D **sombreada** (orbit shaded/rendered) el sólido no
        // honra el linetype — es una limitación de sólidos en AutoCAD. Los cortes
        // solo se ven en 2D Wireframe / vistas alámbricas.
        private ObjectId _abandonedPipeStyleId = ObjectId.Null;
        // Escala del linetype dentro del display style, para que los cortes sean
        // grandes y obvios (imagen 4 del usuario). El linetype "DASHED" nativo es
        // muy fino a escala de pies; 5x lo hace muy visible.
        private const double LT_SCALE_ABANDONADO = 5.0;

        // Aplica linetype + escala a un DisplayStyle si el destino no es Hatch/Solid.
        private void SetDashOn(PartsStyles.DisplayStyle ds, string ltName)
        {
            if (ds == null) return;
            ds.Linetype = ltName;
            ds.LinetypeScale = LT_SCALE_ABANDONADO;
            ds.Visible = true;
        }

        private ObjectId AsegurarEstiloAbandonado(
            Database db, CivilDocument civilDoc, Transaction tr, ObjectId basePipeStyleId)
        {
            if (_abandonedPipeStyleId != ObjectId.Null && !_abandonedPipeStyleId.IsErased)
                return _abandonedPipeStyleId;
            try
            {
                string ltName = AsegurarLinetypeDiscontinuo(db, tr);
                const string styleName = "Abandonado (PDFCAD)";
                var pipeStyles = civilDoc.Styles.PipeStyles;
                ObjectId styleId;
                if (pipeStyles.Contains(styleName))
                    styleId = pipeStyles[styleName];
                else if (basePipeStyleId != ObjectId.Null)
                {
                    var baseStyle = (PartsStyles.PipeStyle)tr.GetObject(basePipeStyleId, OpenMode.ForRead);
                    styleId = baseStyle.CopyAsSibling(styleName);
                }
                else
                    styleId = pipeStyles.Add(styleName);

                var st = (PartsStyles.PipeStyle)tr.GetObject(styleId, OpenMode.ForWrite);
                // 3D (Model)
                SetDashOn(st.GetDisplayStyleModel(), ltName);
                // Planta (sin Hatch/Solid — no aceptan linetype útil)
                foreach (var c in new[] {
                    PartsStyles.PipeDisplayStylePlanType.Centerline,
                    PartsStyles.PipeDisplayStylePlanType.InsideWalls,
                    PartsStyles.PipeDisplayStylePlanType.OutsideWalls,
                    PartsStyles.PipeDisplayStylePlanType.EndLine })
                    SetDashOn(st.GetDisplayStylePlan(c), ltName);
                // Perfil
                foreach (var c in new[] {
                    PartsStyles.PipeDisplayStyleProfileType.Centerline,
                    PartsStyles.PipeDisplayStyleProfileType.InsideWalls,
                    PartsStyles.PipeDisplayStyleProfileType.OutsideWalls,
                    PartsStyles.PipeDisplayStyleProfileType.EndLine })
                    SetDashOn(st.GetDisplayStyleProfile(c), ltName);
                _abandonedPipeStyleId = styleId;
                Dbg("ABANDONED_STYLE_OK", ("estilo", styleName), ("linetype", ltName), ("scale", LT_SCALE_ABANDONADO.ToString()));
            }
            catch (Exception ex)
            {
                Dbg("ABANDONED_STYLE_FAIL", ("error", ex.Message));
                _abandonedPipeStyleId = ObjectId.Null;
            }
            return _abandonedPipeStyleId;
        }

        // Igual que AsegurarEstiloAbandonado pero para redes de PRESIÓN
        // (PressurePipe / PressurePipeStyle). La colección de estilos de presión no
        // es una propiedad de StylesRoot: se obtiene por el método de extensión
        // StylesRootPressurePipesExtension.GetPressurePipeStyles(...).
        private ObjectId _abandonedPressPipeStyleId = ObjectId.Null;

        private ObjectId AsegurarEstiloAbandonadoPresion(
            Database db, CivilDocument civilDoc, Transaction tr, ObjectId basePipeStyleId)
        {
            if (_abandonedPressPipeStyleId != ObjectId.Null && !_abandonedPressPipeStyleId.IsErased)
                return _abandonedPressPipeStyleId;
            try
            {
                string ltName = AsegurarLinetypeDiscontinuo(db, tr);
                const string styleName = "Abandonado (PDFCAD)";
                PresStyles.PressurePipeStyleCollection pipeStyles =
                    PresStyles.StylesRootPressurePipesExtension.GetPressurePipeStyles(civilDoc.Styles);
                ObjectId styleId;
                if (pipeStyles.Contains(styleName))
                    styleId = pipeStyles[styleName];
                else if (basePipeStyleId != ObjectId.Null)
                {
                    var baseStyle = (PresStyles.PressurePipeStyle)tr.GetObject(basePipeStyleId, OpenMode.ForRead);
                    styleId = baseStyle.CopyAsSibling(styleName);
                }
                else
                    styleId = pipeStyles.Add(styleName);

                var st = (PresStyles.PressurePipeStyle)tr.GetObject(styleId, OpenMode.ForWrite);
                // 3D (Model)
                SetDashOn(st.GetDisplayStyleModel(), ltName);
                // Planta
                foreach (var c in new[] {
                    PresStyles.PressurePipeDisplayStylePlanType.Centerline,
                    PresStyles.PressurePipeDisplayStylePlanType.InsideWalls,
                    PresStyles.PressurePipeDisplayStylePlanType.OutsideWalls,
                    PresStyles.PressurePipeDisplayStylePlanType.EndLine })
                    SetDashOn(st.GetDisplayStylePlan(c), ltName);
                // Perfil
                foreach (var c in new[] {
                    PresStyles.PressurePipeDisplayStyleProfileType.Centerline,
                    PresStyles.PressurePipeDisplayStyleProfileType.InsideWalls,
                    PresStyles.PressurePipeDisplayStyleProfileType.OutsideWalls,
                    PresStyles.PressurePipeDisplayStyleProfileType.EndLine })
                    SetDashOn(st.GetDisplayStyleProfile(c), ltName);
                _abandonedPressPipeStyleId = styleId;
                Dbg("ABANDONED_STYLE_OK", ("tipo", "presion"), ("estilo", styleName), ("linetype", ltName), ("scale", LT_SCALE_ABANDONADO.ToString()));
            }
            catch (Exception ex)
            {
                Dbg("ABANDONED_STYLE_FAIL", ("tipo", "presion"), ("error", ex.Message));
                _abandonedPressPipeStyleId = ObjectId.Null;
            }
            return _abandonedPressPipeStyleId;
        }

        // Nombre de un linetype discontinuo cargado en el dibujo; si no hay ninguno,
        // intenta cargar "DASHED" desde acad.lin. Fallback seguro: "Continuous".
        private string AsegurarLinetypeDiscontinuo(Database db, Transaction tr)
        {
            var lt = (LinetypeTable)tr.GetObject(db.LinetypeTableId, OpenMode.ForRead);
            foreach (var n in new[] { "DASHED", "DASHED2", "HIDDEN", "ACAD_ISO02W100" })
                if (lt.Has(n)) return n;
            try { db.LoadLineTypeFile("DASHED", "acad.lin"); return "DASHED"; }
            catch { }
            return "Continuous";
        }

        private ObjectId CrearRedGravedadCompleta(
            Editor ed, Database db, CivilDocument civilDoc, Transaction tr,
            string nombre, ObjectId surfId, double defaultDepth,
            List<ImportPipe> pipes, List<ImportStruct> structs, bool sinBuzones,
            out List<DatosAlignment> datosAlignments)
        {
            datosAlignments = new List<DatosAlignment>();
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

            // Búsqueda de la familia "Estructura nula"/"Null Structure" — invisible
            // en 3D, tamaño 0, sirve para "cerrar" pipes sin dibujar buzón real
            // manteniendo la conexión de red. Factorizada porque hace falta en 2
            // casos: default de redes conduit (sinBuzones) Y en cualquier vértice
            // que Python marcó explícitamente "oculto" (match.Hidden), sin
            // importar si la red es de gravedad o conduit.
            bool BuscarEstructuraNula(out ObjectId fam, out ObjectId size)
            {
                fam = ObjectId.Null; size = ObjectId.Null;
                foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure))
                {
                    var f = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                    if (f == null || f.PartSizeCount == 0) continue;
                    string d = (f.Description ?? "").ToLower();
                    string n = (f.Name ?? "").ToLower();
                    if (d.Contains("null") || d.Contains("nula") ||
                        n.Contains("null") || n.Contains("nula"))
                    { fam = fid; size = f[0]; return true; }
                }
                return false;
            }

            ObjectId defStructFam, defStructSize; string defStructNom;
            if (sinBuzones)
            {
                // Para conduit: usar la "Estructura nula" del template como default.
                // Es una estructura invisible tamaño 0 que sirve para "cerrar" las
                // pipes sin dibujar buzón real.
                if (!BuscarEstructuraNula(out defStructFam, out defStructSize))
                {
                    // Sin Null Structure disponible: fallback a la primera real.
                    if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Structure,
                                      out defStructFam, out defStructSize, out defStructNom))
                    { ed.WriteMessage($"\n'{nombre}': sin familias de ESTRUCTURA."); return ObjectId.Null; }
                }
                else defStructNom = "Estructura nula";
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
            // Nula lista para usar en vértices "oculto" — si la red YA es conduit,
            // defStructFam ya ES la nula (o su fallback); si es gravedad, se busca
            // aparte sin cambiar el default general de la red.
            ObjectId hiddenStructFam = sinBuzones ? defStructFam : ObjectId.Null;
            ObjectId hiddenStructSize = sinBuzones ? defStructSize : ObjectId.Null;
            if (!sinBuzones)
            {
                if (!BuscarEstructuraNula(out hiddenStructFam, out hiddenStructSize))
                    ed.WriteMessage("\n⚠ No se encontró 'Estructura nula' en el catálogo — " +
                                   "los buzones marcados como ocultos se crearán como buzones por defecto. " +
                                   "Agregue una familia Null Structure al Parts List para que funcione la ocultación.");
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
                // Si el pipe ya trae familia explícita (conductos de ductbank
                // con la familia inyectada), NO ejecutar el pre-scan genérico
                // — usaría material vacío y elegiría la 1ª familia alfabética
                // (típicamente 'Concrete Pipe' en inglés), generando warnings
                // espurios y a veces cambiando la elección real. La familia
                // pedida ya sabe qué hacer más abajo.
                if (!string.IsNullOrWhiteSpace(ip.PipeFamily)) continue;
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

            // Pre-scan: agregar tamaños ESPECÍFICOS que faltan al catálogo.
            // ExisteTamañoPipeExacto busca por número en el nombre (no BuscarTuberia,
            // que retorna true incluso con fallback a otro tamaño).
            try { partsList.UpgradeOpen(); } catch { }
            var diamsFaltantes = new HashSet<double>();
            foreach (var ip in pipes)
                if (ip.Diameter > 0) diamsFaltantes.Add(ip.Diameter);
            foreach (double diam in diamsFaltantes)
            {
                if (ExisteTamañoPipeExacto(tr, partsList, diam))
                    continue;
                // Paso 1: intentar agregar desde el catálogo existente
                bool agregado = false;
                foreach (ObjectId epFid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
                {
                    try
                    {
                        var epFam = tr.GetObject(epFid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                        if (epFam == null) continue;
                        if (AgregarTamañoPipe(tr, epFam, diam, ed)) { agregado = true; break; }
                    }
                    catch { }
                }
                // Paso 2: si no existe en el catálogo, inyectar el tamaño en el XML
                if (!agregado)
                {
                    foreach (ObjectId epFid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
                    {
                        try
                        {
                            var epFam = tr.GetObject(epFid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                            if (epFam == null) continue;
                            if (InyectarTamañoEnCatalogo(tr, epFam, diam, ed)) { agregado = true; break; }
                        }
                        catch { }
                    }
                }
                if (!agregado)
                    ed.WriteMessage($"\n  ⚠ Diámetro {diam:F0}\" no se pudo crear en ninguna familia.");
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

            // Pre-scan: para cada familia única que llega del DXF, agregarla al
            // PartsList si aún no está. Se prefiere el GUID (clave estable,
            // independiente del idioma) sobre el Part (Descripción localizada, que
            // puede no calzar entre versiones/idiomas). Clave de dedup = GUID si
            // hay, si no el Part.
            var structPedidos = new Dictionary<string, (string part, string guid)>(StringComparer.OrdinalIgnoreCase);
            foreach (var st in structs)
            {
                if (string.IsNullOrWhiteSpace(st.Part) && string.IsNullOrWhiteSpace(st.PartGuid)) continue;
                string key = !string.IsNullOrWhiteSpace(st.PartGuid) ? "g:" + st.PartGuid : "p:" + st.Part;
                if (!structPedidos.ContainsKey(key)) structPedidos[key] = (st.Part, st.PartGuid);
            }
            foreach (var kv in structPedidos.Values)
                AsegurarFamiliaPorId(ed, tr, partsList, kv.part, CivilDB.DomainType.Structure, kv.guid);

            // Pre-scan de familias de TUBERÍA elegidas en Python (dominio Pipe).
            var pipesPedidas = new Dictionary<string, (string fam, string guid)>(StringComparer.OrdinalIgnoreCase);
            foreach (var ip2 in pipes)
            {
                if (string.IsNullOrWhiteSpace(ip2.PipeFamily) && string.IsNullOrWhiteSpace(ip2.PipeGuid)) continue;
                string key = !string.IsNullOrWhiteSpace(ip2.PipeGuid) ? "g:" + ip2.PipeGuid : "p:" + ip2.PipeFamily;
                if (!pipesPedidas.ContainsKey(key)) pipesPedidas[key] = (ip2.PipeFamily, ip2.PipeGuid);
            }
            foreach (var kv in pipesPedidas.Values)
                AsegurarFamiliaPorId(ed, tr, partsList, kv.fam, CivilDB.DomainType.Pipe, kv.guid);

            var createdStructs = new Dictionary<string, ObjectId>();
            int nPipes = 0;
            // Traza per-pipe (no un solo trazaEje global). Al final agrupamos por
            // componentes conectados y creamos un alignment por componente — así
            // 3 sub-redes desconectadas en la misma capa NUNCA se unen con un eje
            // que salta entre ellas.
            var pipeTrazas = new List<(List<TrazaPt> pts, ObjectId startSt, ObjectId endSt)>();
            // Cotas EXPLÍCITAS a reponer al final. Civil 3D, al conectar tuberías
            // (ConnectToStructure), re-aplica reglas por defecto (pendiente ~1% +
            // tapada) y, si la estructura tiene el ajuste automático de superficie
            // activo, ignora el rim manual. Guardamos lo que el DXF trae y lo
            // volvemos a fijar DESPUÉS de crear/conectar todo.
            var explicitRimSump = new Dictionary<ObjectId, (double rim, double sump)>();
            var explicitPipeInv = new List<(ObjectId id, double zStart, double zEnd)>();
            // Pipes de "padre" de un bancoducto: solo sirven para generar
            // los buzones/estructuras y la geometría de la red; su cilindro 3D
            // NO se muestra (el sólido del bancoducto lo reemplaza). Se
            // recogen aquí y se borran al final (después de conectar las
            // estructuras, para no romper la topología en el momento).
            var pipesToErase = new List<ObjectId>();

            foreach (var ip in pipes)
            {
                int nVerts = ip.Vertices.Count;
                double[] zOut = InterpolateZ(ip, nVerts, ip.VertexInv);
                double[] zIn  = InterpolateZ(ip, nVerts, ip.VertexInvIn);
                // Codos (vértices sin buzón visible, es decir hidden o curve):
                // forzar continuidad de elevación entre el tramo entrante y el
                // saliente. Sin esto, InterpolateZ puede dar zOut[i] != zIn[i]
                // en el vértice del codo → los dos tramos aparecen a alturas
                // distintas y visualmente NO se conectan. Solo tocamos vértices
                // internos y solo cuando el usuario no fijó un valor explícito
                // distinto para lados independientes (si lo hizo, respetamos).
                for (int i = 1; i < nVerts - 1; i++)
                {
                    if (!ip.NoManholeVerts.Contains(i)) continue;
                    bool hasOut = ip.VertexInv != null && ip.VertexInv.ContainsKey(i);
                    bool hasIn  = ip.VertexInvIn != null && ip.VertexInvIn.ContainsKey(i);
                    if (hasOut && hasIn) continue; // usuario los fijó a propósito
                    double z = hasOut ? zOut[i] : (hasIn ? zIn[i] : (zOut[i] + zIn[i]) * 0.5);
                    zOut[i] = z; zIn[i] = z;
                }
                // pipeTraza se construye MÁS ABAJO, después de calcular las esquinas
                // curvas — tiene que usar los puntos de tangencia recortados (p1/p2),
                // no el vértice original, o el Alignment que se arma con esta traza
                // queda pasando en línea recta justo por donde la tubería real ya se
                // desvió, y el eje termina cruzando el elemento curvo en el dibujo.

                // Prioridad para elegir familia+tamaño de esta pipe:
                //   1) PIPE_FAMILY del XDATA (elegida en Python del catálogo Civil 3D)
                //   2) BuscarTuberia por material + diámetro
                //   3) default
                string diamStr = !string.IsNullOrWhiteSpace(ip.PipeSize)
                    ? ip.PipeSize : ip.Diameter.ToString("F0");
                ObjectId pipeFam = ObjectId.Null, pipeSize = ObjectId.Null; string pipeNom = "";
                if (!string.IsNullOrWhiteSpace(ip.PipeFamily))
                {
                    BuscarTuberia(tr, partsList, ip.PipeFamily, diamStr,
                                  out pipeFam, out pipeSize, out pipeNom);
                    Dl(ed, $"\n    [FAM-PEDIDA] '{ip.PipeFamily}' size='{diamStr}' → {(pipeFam != ObjectId.Null ? $"encontrada '{pipeNom}'" : "NO ENCONTRADA")}");
                    Dbg("PIPE_FAMILY_MATCH", ("pedido", ip.PipeFamily), ("size", diamStr),
                        ("encontrada", pipeFam != ObjectId.Null ? "true" : "false"),
                        ("nombre", pipeNom));
                }
                if (pipeFam == ObjectId.Null)
                {
                    bool ok2 = BuscarTuberia(tr, partsList, ip.Material, diamStr,
                                       out pipeFam, out pipeSize, out pipeNom);
                    Dl(ed, $"\n    [FAM-FALLBACK] material='{ip.Material}' size='{diamStr}' → {(ok2 ? $"encontrada '{pipeNom}'" : $"NO ENCONTRADA — usando default '{defPipeNom}'")}");
                    if (!ok2) { pipeFam = defPipeFam; pipeSize = defPipeSize; pipeNom = defPipeNom; }
                }
                // RED DE SEGURIDAD: si esta tubería NO pidió familia personalizada
                // explícita pero el matcher devolvió una custom (Bancoducto/etc.),
                // la reemplazamos por la familia por defecto (siempre stock). Así
                // asignar una custom a UNA sola pipe NUNCA se propaga a las demás,
                // pase lo que pase en el matcher.
                if (string.IsNullOrWhiteSpace(ip.PipeFamily) &&
                    EsFamiliaCustomPorId(tr, pipeFam, CivilDB.DomainType.Pipe))
                {
                    Dbg("PIPE_FAMILY_CUSTOM_BLOQUEADA",
                        ("material", ip.Material ?? ""), ("reemplazo", defPipeNom));
                    pipeFam = defPipeFam; pipeSize = defPipeSize; pipeNom = defPipeNom;
                }

                // Geometría de las esquinas curvas de ESTA tubería (una por cada
                // vértice intermedio marcado "sin buzón"): puntos de tangencia sobre
                // cada recta vecina, arco resultante y sentido. Se calcula ANTES del
                // loop de vértices/segmentos porque el punto de tangencia (no el
                // vértice) es el extremo real de cada tramo recto adyacente.
                double? anchoInteriorCache = null;
                var curvasPorVertice = new Dictionary<int, CurveGeom>();
                foreach (int i in ip.NoManholeVerts)
                {
                    if (i <= 0 || i >= nVerts - 1) continue;      // solo vértices intermedios
                    Point3d corner = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zOut[i]);
                    Point3d prevV = new Point3d(ip.Vertices[i - 1].X, ip.Vertices[i - 1].Y, zOut[i - 1]);
                    Point3d nextV = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, zOut[i + 1]);
                    var dirPrev = new Vector3d(prevV.X - corner.X, prevV.Y - corner.Y, 0.0);
                    var dirNext = new Vector3d(nextV.X - corner.X, nextV.Y - corner.Y, 0.0);
                    double distPrev = dirPrev.Length, distNext = dirNext.Length;
                    if (distPrev < 1e-6 || distNext < 1e-6) continue;
                    dirPrev = dirPrev / distPrev; dirNext = dirNext / distNext;
                    double cosD = Math.Max(-1.0, Math.Min(1.0, dirPrev.DotProduct(dirNext)));
                    double deltaRad = Math.Acos(cosD);
                    double deltaDeg = deltaRad * 180.0 / Math.PI;
                    if (deltaDeg > 178.0)
                    {
                        Dbg("CURVA_SKIP_RECTA", ("pipe", ip.Layer), ("vertice", i.ToString()),
                            ("angulo", deltaDeg.ToString("F1")));
                        continue;                                  // prácticamente recto: no hace falta arco
                    }
                    double r;
                    bool rEsExplicito = false;
                    if (ip.CurveRadiusByVert.TryGetValue(i, out double rExplicito) && rExplicito > 0.01)
                    { r = rExplicito; rEsExplicito = true; }
                    else
                    {
                        if (anchoInteriorCache == null)
                            anchoInteriorCache = ResolveAnchoInterior(tr, net, pipeFam, pipeSize, ed);
                        r = 6.0 * anchoInteriorCache.Value;
                    }
                    Dl(ed, $"\n  [CURVA] '{ip.Layer}' v{i} ang={deltaDeg:F1}° radio-pedido={(rEsExplicito ? r.ToString("F2") + "ft (explícito)" : r.ToString("F2") + "ft (auto 6× ancho)")}");
                    double t = r / Math.Tan(deltaRad / 2.0);
                    // No recortar más allá de lo disponible en cada recta vecina (deja
                    // margen del 10% para que siga quedando un tramo recto visible).
                    // "Doble curva": si el vértice del OTRO extremo del segmento
                    // también está marcado como curva, hay que dejarle la MITAD del
                    // segmento a esa otra curva (si no, ambas se comen hasta el 90%
                    // y las tangentes se cruzan → tubería recta con orientación
                    // invertida entre ellas, se ve como un elipsoide alargado).
                    // Doble curva continua: cap 0.48 (no 0.5) para dejar un
                    // pequeño tramo recto entre los dos arcos y evitar puntos
                    // de tangencia coincidentes.
                    double capPrev = ip.NoManholeVerts.Contains(i - 1) ? 0.48 : 0.9;
                    double capNext = ip.NoManholeVerts.Contains(i + 1) ? 0.48 : 0.9;
                    double tMax = Math.Min(distPrev * capPrev, distNext * capNext);
                    if (t > tMax)
                    {
                        double rAjustado = tMax * Math.Tan(deltaRad / 2.0);
                        ed.WriteMessage($"\n⚠ Curva en '{ip.Layer}' vértice {i}: radio {r:F2}' no entra " +
                                        $"(tramos muy cortos); se ajusta a {rAjustado:F2}'.");
                        Dbg("CURVA_RADIO_AJUSTADO", ("pipe", ip.Layer), ("vertice", i.ToString()),
                            ("pedido", r.ToString("F3")), ("usado", rAjustado.ToString("F3")));
                        r = rAjustado; t = tMax;
                    }
                    CurveGeom cg;
                    try { cg = BuildCurveGeom(t, corner, dirPrev, dirNext, distPrev, distNext, prevV, nextV, deltaRad); }
                    catch (Exception exArc)
                    {
                        ed.WriteMessage($"\n⚠ No se pudo calcular el arco en '{ip.Layer}' vértice {i}: {exArc.Message}");
                        Dbg("CURVA_ARCO_FALLO", ("pipe", ip.Layer), ("vertice", i.ToString()), ("error", exArc.Message));
                        continue;
                    }
                    curvasPorVertice[i] = cg;
                    Dl(ed, $"\n  [CURVA-OK] '{ip.Layer}' v{i} → radio-usado={cg.Radio:F2}ft tangente={t:F2}ft");
                    Dbg("CURVA_GEOMETRIA", ("pipe", ip.Layer), ("vertice", i.ToString()),
                        ("angulo", deltaDeg.ToString("F1")), ("radio", cg.Radio.ToString("F3")),
                        ("t", t.ToString("F3")));
                }

                // Ajuste por "tramo recto mínimo" entre dos esquinas curvas
                // CONSECUTIVAS (vértices i e i+1, sin ningún vértice recto entre
                // medio): cada esquina ya se recortó como máximo al 90% de SU
                // PROPIO tramo — pero si las dos esquinas comparten el mismo tramo
                // corto, las dos zonas de recorte pueden solaparse igual (cada una
                // "cree" que tiene el 90% completo para sí sola). Se exige dejar
                // al menos 1× el ancho interior de la tubería como tramo recto
                // real entre ambas, avisando y reduciendo el radio de las dos
                // proporcionalmente si no entra.
                foreach (int i in new List<int>(curvasPorVertice.Keys))
                {
                    int j = i + 1;
                    // 'i' puede haber sido removido en una iteración anterior (si
                    // era la 'j' de un par previo sin espacio ni para el mínimo).
                    if (!curvasPorVertice.ContainsKey(i) || !curvasPorVertice.ContainsKey(j)) continue;
                    var cgI = curvasPorVertice[i]; var cgJ = curvasPorVertice[j];
                    double L = cgI.DistNext;    // == cgJ.DistPrev: mismo tramo (vértice i → vértice j)
                    if (anchoInteriorCache == null)
                        anchoInteriorCache = ResolveAnchoInterior(tr, net, pipeFam, pipeSize, ed);
                    double minRecto = 1.0 * anchoInteriorCache.Value;
                    double disponible = L - minRecto;
                    if (cgI.T + cgJ.T <= disponible) continue;   // ya entra con margen, no hace falta ajustar
                    if (disponible <= 1e-6)
                    {
                        // El tramo es tan corto que ni el mínimo entra: mejor sin
                        // curva en ninguna de las dos esquinas (quedan como el
                        // solape cosmético de siempre) que dejarlas solapadas.
                        ed.WriteMessage($"\n⚠ Curvas en '{ip.Layer}' vértices {i} y {j}: el tramo entre ambas " +
                                         $"({L:F2}') es más corto que el mínimo recto exigido ({minRecto:F2}') — " +
                                         "no se genera curva en ninguna de las dos, quedan como quiebre recto.");
                        Dbg("CURVA_MIN_RECTO_SIN_ESPACIO", ("pipe", ip.Layer), ("vertA", i.ToString()),
                            ("vertB", j.ToString()), ("tramo", L.ToString("F3")), ("minRecto", minRecto.ToString("F3")));
                        curvasPorVertice.Remove(i); curvasPorVertice.Remove(j);
                        continue;
                    }
                    double factor = disponible / (cgI.T + cgJ.T);
                    double tI2 = cgI.T * factor, tJ2 = cgJ.T * factor;
                    ed.WriteMessage($"\n⚠ Curvas en '{ip.Layer}' vértices {i} y {j} están muy cerca " +
                                     $"({L:F2}' de tramo) y se solapan — se reducen los radios de " +
                                     $"{cgI.Radio:F2}'/{cgJ.Radio:F2}' a {tI2 * Math.Tan(cgI.DeltaRad / 2.0):F2}'/" +
                                     $"{tJ2 * Math.Tan(cgJ.DeltaRad / 2.0):F2}' para dejar {minRecto:F2}' de tramo recto entre ellas.");
                    Dbg("CURVA_MIN_RECTO_AJUSTE", ("pipe", ip.Layer), ("vertA", i.ToString()), ("vertB", j.ToString()),
                        ("tramo", L.ToString("F3")), ("minRecto", minRecto.ToString("F3")),
                        ("tA_antes", cgI.T.ToString("F3")), ("tB_antes", cgJ.T.ToString("F3")),
                        ("tA_despues", tI2.ToString("F3")), ("tB_despues", tJ2.ToString("F3")));
                    try
                    {
                        curvasPorVertice[i] = BuildCurveGeom(tI2, cgI.Corner, cgI.DirPrev, cgI.DirNext,
                            cgI.DistPrev, cgI.DistNext, cgI.PrevV, cgI.NextV, cgI.DeltaRad);
                        curvasPorVertice[j] = BuildCurveGeom(tJ2, cgJ.Corner, cgJ.DirPrev, cgJ.DirNext,
                            cgJ.DistPrev, cgJ.DistNext, cgJ.PrevV, cgJ.NextV, cgJ.DeltaRad);
                    }
                    catch (Exception exArc)
                    {
                        ed.WriteMessage($"\n⚠ No se pudo reajustar el arco en '{ip.Layer}' vértices {i}/{j}: {exArc.Message}");
                        Dbg("CURVA_MIN_RECTO_FALLO", ("pipe", ip.Layer), ("vertA", i.ToString()), ("vertB", j.ToString()),
                            ("error", exArc.Message));
                    }
                }

                // Traza para el Alignment (más abajo) y para el Union-Find de
                // componentes conectados: en cada vértice curvo, los DOS puntos de
                // tangencia en vez del vértice original — si no, el eje pasaría en
                // línea recta justo por donde la tubería real ya se desvió.
                var pipeTraza = new List<TrazaPt>();
                for (int i = 0; i < nVerts; i++)
                {
                    if (curvasPorVertice.TryGetValue(i, out CurveGeom cgTraza))
                    {
                        // El bulge va en P1 (donde ARRANCA el arco): así el tramo
                        // P1→P2 del eje describe la misma curva que la tubería.
                        pipeTraza.Add(new TrazaPt(cgTraza.P1, BulgeDeCurva(cgTraza)));
                        pipeTraza.Add(new TrazaPt(cgTraza.P2));
                    }
                    else
                        pipeTraza.Add(new TrazaPt(new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zOut[i])));
                }

                var vertStructIds = new List<ObjectId>();
                // ─ Skip TOTAL de estructuras: cuando la pipe pertenece a los
                // conductos INTERNOS de un bancoducto, no queremos ninguna
                // structure propia (el buzón real lo da la pipe padre del
                // bancoducto, no los conductos internos). Sin este skip, N
                // conductos generaban N estructuras superpuestas por vértice.
                if (ip.NoStructuresAll)
                {
                    for (int i = 0; i < nVerts; i++) vertStructIds.Add(ObjectId.Null);
                    Dbg("STRUCT_SKIP_ALL", ("red", nombre), ("verts", nVerts.ToString()));
                    goto __endStructLoop;
                }
                for (int i = 0; i < nVerts; i++)
                {
                    // Vértice intermedio marcado "sin buzón" por el usuario en la UI:
                    // no crear structure aquí. Los pipes que llegan/salen simplemente
                    // quedarán sin conectar en ese extremo (quiebre visual sin manhole),
                    // SALVO que sea una esquina curva con geometría calculada arriba —
                    // en ese caso el arco (creado en el loop de segmentos, más abajo)
                    // sí queda conectado a ambos tramos rectos.
                    if (i > 0 && i < nVerts - 1 && ip.NoManholeVerts.Contains(i))
                    { vertStructIds.Add(ObjectId.Null); continue; }

                    Point2d v = ip.Vertices[i];
                    double zInv = Math.Min(zOut[i], zIn[i]);
                    double depth = ip.CoverMin > 0 ? ip.CoverMin : defaultDepth;

                    ImportStruct match = FindNearestStruct(structs, v, 1.0);

                    double rim, sump;
                    string structType = match != null ? (match.Part ?? "") : "";  // ← siempre respeta la familia elegida
                    if (match != null && match.Rim.HasValue && match.Sump.HasValue)
                    { rim = match.Rim.Value; sump = match.Sump.Value; }
                    else
                    {
                        // Sin buzón explícito del DXF: el sump debe coincidir EXACTO con
                        // la rasante de la tubería en ese vértice (zInv) — no restarle nada.
                        // Antes se restaba 0.5' "de sumidero", pero eso desalineaba el
                        // buzón respecto a la tubería que el usuario definió (se veía como
                        // que "el buzón recorta y redefine" la rasante 0.5' más abajo).
                        sump = zInv; rim = zInv + depth;
                    }
                    // "Altura (Pies)" explícita del usuario (Python): fuerza el Rim para que
                    // Rim − Sump = altura pedida, SIN tocar el Sump (que siempre refleja la
                    // rasante real de la tubería conectada — dato físico, no inventado).
                    bool alturaExplicita = match != null && match.HeightFt.HasValue && match.HeightFt.Value > 0.01;
                    if (alturaExplicita) rim = sump + match.HeightFt.Value;
                    // Garantía: rim ARRIBA (mín. 1' sobre sump) y sump por debajo del invert.
                    if (!alturaExplicita && rim - sump < 1.0) rim = sump + Math.Max(depth, 3.0);

                    string key = $"{Math.Round(v.X, 2)}_{Math.Round(v.Y, 2)}";
                    // En modo conduit (eléctrico/telecom): tanto si el usuario asignó
                    // familia como si NO, siempre se crea structure en cada nodo. Si no
                    // hay familia → se usa la "Estructura nula" default (invisible pero
                    // permite que Civil 3D marque el nodo y conecte los tramos).
                    // Nota: antes se saltaba con vertStructIds=Null, y algunos nodos
                    // quedaban sin buzón — el usuario lo reportó.
                    if (!createdStructs.ContainsKey(key))
                    {
                        ObjectId sFam, sSize;
                        string ruta;
                        if (match != null && match.Hidden)
                        {
                            // Ocultado desde Python: NO se crea ninguna estructura en
                            // este vértice (ni siquiera "Estructura nula"). Los pipes
                            // se conectan por extremo libre. El usuario lo pidió así:
                            // no debe aparecer NADA en la posición del buzón oculto.
                            Dbg("STRUCT_SKIP_HIDDEN", ("id", match.Id),
                                ("x", v.X.ToString("F3")), ("y", v.Y.ToString("F3")));
                            vertStructIds.Add(ObjectId.Null);
                            continue;
                        }
                        else if (match != null && !match.Covered && haySinTapa)
                        { sFam = defStructFamNoLid; sSize = defStructSizeNoLid; ruta = "sin_tapa"; }
                        else
                        {
                            string sizeHint = match != null ? (match.PartSize ?? "") : "";
                            BuscarEstructura(tr, partsList, structType, sizeHint,
                                             out sFam, out sSize, out _, match?.PartGuid ?? "");
                            if (sFam == ObjectId.Null)
                            { sFam = defStructFam; sSize = defStructSize; ruta = "fallback_default"; }
                            else ruta = "buscar_estructura_match";
                            // RED DE SEGURIDAD: si esta estructura NO pidió familia
                            // custom explícita (structType vacío) pero el matcher
                            // devolvió un buzón custom, lo reemplazamos por el default
                            // (stock). Evita que asignar una familia custom a UN solo
                            // buzón se propague a todos los demás nodos.
                            if (string.IsNullOrWhiteSpace(structType) &&
                                EsFamiliaCustomPorId(tr, sFam, CivilDB.DomainType.Structure))
                            {
                                sFam = defStructFam; sSize = defStructSize;
                                ruta = "custom_bloqueada_default";
                            }
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
                            if (match != null && match.Hidden)
                            {
                                Dbg("STRUCT_ADD_FAIL_HIDDEN_SKIP", ("id", match.Id));
                                vertStructIds.Add(ObjectId.Null);
                                continue;
                            }
                            bool fbHidden = match != null && match.Hidden && hiddenStructFam != ObjectId.Null;
                            ObjectId fbFam  = fbHidden ? hiddenStructFam  : defStructFam;
                            ObjectId fbSize = fbHidden ? hiddenStructSize : defStructSize;
                            try
                            {
                                net.AddStructure(fbFam, fbSize,
                                                 new Point3d(v.X, v.Y, rim), 0.0, ref sid, true);
                                Dbg("STRUCT_ADD_FALLBACK_OK", ("id", match?.Id ?? ""),
                                    ("familia_usada", fbHidden ? "nula(hidden)" : defStructNom));
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
                        // Una "Altura (Pies)" pedida también cuenta como rim explícito — si no,
                        // con superficie de referencia presente Civil3D reajustaría el rim
                        // automáticamente desde el terreno y pisaría la altura pedida.
                        bool holdRim = surfId == ObjectId.Null || (match != null && (match.Rim.HasValue || alturaExplicita));
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
                __endStructLoop: ;

                // Guardar la traza de ESTA pipe con los structIds de sus extremos.
                // Al final del método agrupamos por componentes conectados (Union-Find
                // sobre coordenadas de vértices) y creamos un alignment por componente.
                ObjectId pipeStart = vertStructIds.Count > 0 ? vertStructIds[0] : ObjectId.Null;
                ObjectId pipeEnd   = vertStructIds.Count > 0 ? vertStructIds[vertStructIds.Count - 1] : ObjectId.Null;
                pipeTrazas.Add((pipeTraza, pipeStart, pipeEnd));

                // Vértices "sin buzón" SIN geometría de curva calculada (ángulo casi
                // recto, o falló el cálculo del arco): mismo solape cosmético de
                // siempre, para que el quiebre se lea continuo sin dejar un hueco.
                double overlapFt = Math.Max(0.5, ip.Diameter / 24.0);   // ~½ diámetro en pies

                for (int i = 0; i < nVerts - 1; i++)
                {
                    Point3d p1 = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zOut[i]);
                    Point3d p2 = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, zIn[i + 1]);

                    bool startEsCurva = i > 0 && curvasPorVertice.ContainsKey(i);
                    bool endEsCurva = i + 1 < nVerts - 1 && curvasPorVertice.ContainsKey(i + 1);

                    if (startEsCurva)
                        p1 = curvasPorVertice[i].P2;              // tangencia de SALIDA del arco anterior
                    else if (i > 0 && ip.NoManholeVerts.Contains(i))
                    {
                        // Sin geometría de curva (ángulo casi recto): solape cosmético.
                        var p0 = new Point3d(ip.Vertices[i - 1].X, ip.Vertices[i - 1].Y, zOut[i - 1]);
                        Vector3d back = p0 - p1;
                        if (back.Length > 1e-6) p1 = p1 + back.GetNormal() * overlapFt;
                    }
                    if (endEsCurva)
                        p2 = curvasPorVertice[i + 1].P1;          // tangencia de ENTRADA al arco siguiente
                    else if (i + 1 < nVerts - 1 && ip.NoManholeVerts.Contains(i + 1))
                    {
                        var p3 = new Point3d(ip.Vertices[i + 2].X, ip.Vertices[i + 2].Y, zIn[i + 2]);
                        Vector3d fwd = p3 - p2;
                        if (fwd.Length > 1e-6) p2 = p2 + fwd.GetNormal() * overlapFt;
                    }
                    if (p1.DistanceTo(p2) < 1e-6) continue;

                    // Override por segmento: si Python marcó familia/tamaño distintos
                    // para este tramo, los resolvemos ahora contra la PartsList; si no
                    // se encuentra la familia, caemos a la global de la pipe.
                    ObjectId segFam = pipeFam, segSize = pipeSize;
                    if (ip.SegOverrides != null && ip.SegOverrides.TryGetValue(i, out var ov))
                    {
                        string ovFam = ov.fam ?? "";
                        string ovSize = !string.IsNullOrWhiteSpace(ov.size) ? ov.size : ip.PipeSize;
                        if (!string.IsNullOrWhiteSpace(ovFam))
                        {
                            ObjectId f2, s2; string nom2;
                            if (BuscarTuberia(tr, partsList, ovFam, ovSize, out f2, out s2, out nom2))
                            { segFam = f2; segSize = s2; }
                            Dbg("PIPE_SEG_OVERRIDE", ("tramo", i.ToString()),
                                ("fam", ovFam), ("size", ovSize),
                                ("encontrada", (segFam != pipeFam || segSize != pipeSize) ? "true" : "false"));
                        }
                        else if (!string.IsNullOrWhiteSpace(ov.size))
                        {
                            // Solo cambia el tamaño (misma familia global).
                            ObjectId f2, s2; string nom2;
                            if (BuscarTuberia(tr, partsList, ip.PipeFamily, ov.size, out f2, out s2, out nom2))
                            { segFam = f2; segSize = s2; }
                        }
                    }

                    ObjectId pid = ObjectId.Null;
                    // Conduit (sinBuzones): sin auto-conexión ni structures. Solo la pipe pura.
                    bool autoConexion = !sinBuzones;
                    net.AddLinePipe(segFam, segSize, new LineSegment3d(p1, p2), ref pid, autoConexion);
                    CivilDB.Pipe pipe = (CivilDB.Pipe)tr.GetObject(pid, OpenMode.ForWrite);
                    // Diagnóstico: leer el diámetro/nombre REAL que Civil 3D
                    // dejó en el pipe recién creado. Si el pedido era 3" y
                    // aquí sale 12", significa que la Parts List no tenía el
                    // tamaño y cayó al primer default sin advertir.
                    try
                    {
                        string famDesc = "", sizeName = "";
                        try
                        {
                            var famR = tr.GetObject(segFam, OpenMode.ForRead) as PartsStyles.PartFamily;
                            famDesc = famR?.Description ?? "";
                        }
                        catch { }
                        try
                        {
                            var szR = tr.GetObject(segSize, OpenMode.ForRead) as PartsStyles.PartSize;
                            sizeName = szR?.Name ?? "";
                        }
                        catch { }
                        double dInnerFt = 0, dOuterFt = 0;
                        try { dInnerFt = pipe.InnerDiameterOrWidth; } catch { }
                        try { dOuterFt = pipe.OuterDiameterOrWidth; } catch { }
                        double dInner = dInnerFt * 12.0, dOuter = dOuterFt * 12.0;
                        double wall = (dOuter - dInner) / 2.0;
                        Dl(ed, $"\n    [PIPE-CREADO] pedido='{ip.PipeFamily}' size='{ip.PipeSize}' → familia='{famDesc}' size='{sizeName}' inner={dInner:F2}\" outer={dOuter:F2}\" wall={wall:F3}\"");
                    }
                    catch { }

                    // Conducto de bancoducto: forzar wall=0 en el PartSize
                    // compartido (afecta a todos los pipes del mismo tamaño,
                    // pero como cada conducto es su propia red y usa un tamaño
                    // dedicado inyectado en el pre-scan, no hay efecto colateral).
                    if (ip.IsConduit)
                    {
                        try
                        {
                            var szW = tr.GetObject(segSize, OpenMode.ForWrite) as PartsStyles.PartSize;
                            if (szW != null)
                            {
                                var recSz = szW.SizeDataRecord;
                                bool changed = false;
                                double targetInnerFt = ip.ConduitTargetDiamIn / 12.0;
                                try
                                {
                                    var wF = recSz?.GetDataFieldBy(CivilDB.PartContextType.WallThickness);
                                    if (wF != null && !wF.IsReadOnly)
                                    {
                                        double curW = Convert.ToDouble(wF.Value ?? 0.0,
                                            System.Globalization.CultureInfo.InvariantCulture);
                                        if (curW > 1e-6) { wF.Value = 0.0; changed = true; }
                                    }
                                }
                                catch { }
                                try
                                {
                                    var iF = recSz?.GetDataFieldBy(CivilDB.PartContextType.PipeInnerDiameter);
                                    if (iF != null && !iF.IsReadOnly)
                                    {
                                        double curI = Convert.ToDouble(iF.Value ?? 0.0,
                                            System.Globalization.CultureInfo.InvariantCulture);
                                        if (Math.Abs(curI - targetInnerFt) > 1e-6)
                                        { iF.Value = targetInnerFt; changed = true; }
                                    }
                                }
                                catch { }
                                if (changed)
                                {
                                    try { szW.SizeDataRecord = recSz; }
                                    catch (Exception exSz)
                                    { Dl(ed, $"\n    [CONDUIT-SIZE-FAIL] {exSz.Message}"); }
                                    try
                                    {
                                        double dIn2 = pipe.InnerDiameterOrWidth * 12.0;
                                        double dOut2 = pipe.OuterDiameterOrWidth * 12.0;
                                        Dl(ed, $"\n    [CONDUIT-OVERRIDE] target={ip.ConduitTargetDiamIn:F0}\" → inner={dIn2:F2}\" outer={dOut2:F2}\"");
                                    }
                                    catch { }
                                }
                            }
                        }
                        catch (Exception exCo)
                        { Dl(ed, $"\n    [CONDUIT-OVERRIDE-ERR] {exCo.Message}"); }
                    }
                    // Abandonada: solo cambia el 3D (Model) a línea discontinua.
                    // Se basa en el estilo actual de la pipe (copia hermana) para no
                    // tocar planta/perfil; se resuelve una vez y se reusa.
                    if (ip.Abandoned)
                    {
                        ObjectId absId = AsegurarEstiloAbandonado(db, civilDoc, tr, pipe.StyleId);
                        if (absId != ObjectId.Null)
                        {
                            try { pipe.StyleId = absId; }
                            catch (Exception exAb) { Dbg("ABANDONED_APPLY_FAIL", ("error", exAb.Message)); }
                        }
                    }
                    // Solo conectar si la estructura correspondiente se creó bien.
                    // En modo conduit, vertStructIds[i] siempre es Null, así que no conecta.
                    // Envuelto en try/catch: si la structure asignada no admite la
                    // conexión (p.ej. una end-section que se elige por error), se
                    // registra pero no aborta la red entera.
                    if (startEsCurva)
                    {
                        // El extremo INICIAL es la tangencia de salida de un arco ya
                        // creado (al terminar el tramo anterior): coincide exactamente
                        // con el extremo del arco, así que quedan tocándose sin más.
                        // NO se usa Pipe.ConnectToPipe aquí: el SDK exige una estructura
                        // en la unión aunque sea "Null Structure" (tamaño cero), y esa
                        // igual dibuja un símbolo circular en planta — justo lo que no
                        // se quiere ver junto al elemento curvo.
                    }
                    else if (vertStructIds[i] != ObjectId.Null)
                    {
                        try { pipe.ConnectToStructure(CivilDB.ConnectorPositionType.Start, vertStructIds[i], true); }
                        catch (Exception exC) { Dbg("PIPE_CONNECT_FAIL", ("extremo", "start"), ("error", exC.Message)); }
                    }
                    // El extremo FINAL normal (sin curva) se conecta aquí; si endEsCurva,
                    // la conexión real es tubo-a-tubo contra el arco, más abajo.
                    if (!endEsCurva && vertStructIds[i + 1] != ObjectId.Null)
                    {
                        try { pipe.ConnectToStructure(CivilDB.ConnectorPositionType.End, vertStructIds[i + 1], true); }
                        catch (Exception exC) { Dbg("PIPE_CONNECT_FAIL", ("extremo", "end"), ("error", exC.Message)); }
                    }
                    explicitPipeInv.Add((pid, p1.Z, p2.Z));   // reponer invert al final
                    if (ip.HasDuctBank) pipesToErase.Add(pid);

                    if (!string.IsNullOrWhiteSpace(ip.Material))
                    { try { pipe.Description = ip.Material; } catch { } }

                    nPipes++;

                    if (endEsCurva)
                    {
                        // El extremo FINAL de este tramo es la tangencia de entrada al
                        // arco calculado para el vértice i+1: crear la tubería curva
                        // ahora, conectarla a este tramo recto, y dejar su Id disponible
                        // para que el tramo SIGUIENTE se conecte a su otro extremo.
                        var cg = curvasPorVertice[i + 1];
                        ObjectId arcId = ObjectId.Null;
                        try
                        {
                            // applyRules=false SIEMPRE (no depende de autoConexion): en un
                            // bancoducto las reglas de cover/pendiente de la parts list
                            // calculan mal la pendiente sobre la longitud de ARCO, no la
                            // recta — mismo criterio ya verificado en civil3d-mcp-bridge.
                            net.AddCurvePipe(segFam, segSize, cg.Arco, cg.Horario, ref arcId, false);
                            var arcoPipe = (CivilDB.Pipe)tr.GetObject(arcId, OpenMode.ForWrite);
                            if (!string.IsNullOrWhiteSpace(ip.Material))
                            { try { arcoPipe.Description = ip.Material; } catch { } }
                            explicitPipeInv.Add((arcId, cg.P1.Z, cg.P2.Z));
                            if (ip.HasDuctBank) pipesToErase.Add(arcId);
                            // Sin Pipe.ConnectToPipe (ver comentario arriba, extremo
                            // INICIAL): el arco arranca exactamente en el punto donde
                            // termina este tramo recto, tocándose sin estructura de por medio.
                            nPipes++;
                            Dbg("CURVA_CREADA", ("pipe", ip.Layer), ("vertice", (i + 1).ToString()),
                                ("radio", cg.Radio.ToString("F3")));
                        }
                        catch (Exception exArc)
                        {
                            ed.WriteMessage($"\n⚠ No se pudo crear la tubería curva en '{ip.Layer}' vértice {i + 1}: {exArc.Message}");
                            Dbg("CURVA_ADD_FAIL", ("pipe", ip.Layer), ("vertice", (i + 1).ToString()), ("error", exArc.Message));
                        }
                    }
                }
            }

            // ── Reponer cotas EXPLÍCITAS (Civil 3D las recalcula al conectar) ──
            // Se hace AL FINAL, cuando ya no hay conexiones que las pisen. Primero las
            // tuberías (fija la Z de cada extremo = invert capturado), luego rim/sump.
            // Tuberías: fijar Z de cada extremo y LEER DE VUELTA para saber si pegó.
            //
            // Convención de Civil 3D (aplica IGUAL a gravedad y a conduit):
            //  · Pipe.StartPoint.Z es el EJE del tubo (centerline).
            //  · La "Elevación de rasante" de Properties = eje − InnerHeight/2 (la
            //    mitad ALTA del pipe, no el ancho). Civil 3D aplica esta resta
            //    automáticamente para todo tipo de red.
            //  · Para que la rasante mostrada iguale lo que puso el usuario:
            //        StartPoint.Z = rasante_usuario + InnerHeight/2
            // Nota: `InnerHeight` (altura interior) es la propiedad correcta —
            // `InnerDiameterOrWidth` devuelve el ANCHO del banco rectangular, que
            // NO es el offset que aplica Civil 3D. Cuando InnerHeight no exista
            // (algunos pipes circulares antiguos), fallback a InnerDiameterOrWidth
            // (que en circulares == diámetro, y el offset queda correcto también).
            int pipeOk = 0, pipeErr = 0; string pipeMsg = "";
            foreach (var pv in explicitPipeInv)
            {
                try
                {
                    var pp = (CivilDB.Pipe)tr.GetObject(pv.id, OpenMode.ForWrite);
                    Point3d s = pp.StartPoint, e = pp.EndPoint;
                    double r = OffsetEjeARasante(pp);
                    double czS = pv.zStart + r, czE = pv.zEnd + r;
                    pp.StartPoint = new Point3d(s.X, s.Y, czS);
                    pp.EndPoint = new Point3d(e.X, e.Y, czE);
                    double back = pp.StartPoint.Z;
                    if (Math.Abs(back - czS) < 0.05) pipeOk++;
                    else { pipeErr++; if (pipeMsg == "") pipeMsg = $"pedí {czS:F2}, quedó {back:F2}"; }
                }
                catch (Exception ex) { pipeErr++; if (pipeMsg == "") pipeMsg = "EXCEPCION " + ex.Message; }
            }
            Dl(ed, $"\n[DIAG] Pipe StartPoint.Z: ok={pipeOk} fallo={pipeErr}  {pipeMsg}");

            // Estructuras: cada setter por separado para ver CUÁL falla, y leer de vuelta.
            int stOk = 0, stErr = 0; string stMsg = "";
            foreach (var kv in explicitRimSump)
            {
                try
                {
                    var st = (CivilDB.Structure)tr.GetObject(kv.Key, OpenMode.ForWrite);
                    // 1) Apagar el ajuste automático a superficie (o el rim vuelve a la sup).
                    try { st.AutomaticRimSurfaceAdjustment = false; } catch (Exception e1) { if (stMsg == "") stMsg = "autoAdj→" + e1.Message; }
                    // 2) Fijar el rim ANTES del sump: si el setter de RimElevation
                    //    reinicia "Controlar sumidero por" a POR PROFUNDIDAD (como
                    //    hace en algunas familias), sump quedaría pisado por
                    //    rim−SumpDepth (típico desfase fijo, ej. 0.5 ft) si sump se
                    //    fijara antes. Por eso rim va primero.
                    try { st.RimElevation = kv.Value.rim; } catch (Exception e2) { if (stMsg == "") stMsg = "rim→" + e2.Message; }
                    // 3) Reconfirmar POR ELEVACIÓN (por si el paso anterior lo reinició)
                    //    y recién ahí fijar sump — así queda como la ÚLTIMA escritura,
                    //    nada después puede volver a pisarlo.
                    { string err = SetSumpControlByElevation(st); if (err != null && stMsg == "") stMsg = "ctrlSump→" + err; }
                    try { st.SumpElevation = kv.Value.sump; } catch (Exception e3) { if (stMsg == "") stMsg = "sump→" + e3.Message; }
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
            Dl(ed, $"\n[DIAG] Estructura rim/auto: ok={stOk} fallo={stErr}  {stMsg}");

            // Alineamiento (eje) para la red — permite después crear vistas de perfil.
            // En conduit (eléctrico/telecom) NO se crea alineamiento: si hay varias
            // subredes desconectadas dentro de la misma capa, el eje las une con una
            // polilínea fina que aparenta ser una conexión real.
            // Agrupar pipes en COMPONENTES CONECTADOS (Union-Find sobre
            // coordenadas de vértices redondeadas). Cada componente = un
            // alineamiento independiente. Así 3 sub-redes desconectadas en la
            // misma capa producen 3 alignments separados, sin uniones espurias.
            var componentes = AgruparPipesPorComponente(pipes, pipeTrazas);
            int cIdx = 0;
            foreach (var comp in componentes)
            {
                cIdx++;
                // Nombre del alignment: si es único, sin sufijo. Si hay >1, "-1", "-2"…
                string nomAlign = componentes.Count == 1 ? nm : $"{nm}-{cIdx}";
                datosAlignments.Add(new DatosAlignment
                {
                    Nombre = nomAlign,
                    Traza = comp.traza,
                    StartStructId = comp.startSt,
                    EndStructId = comp.endSt,
                    NetId = netId,
                    // Solo asociamos el alignment a la Network cuando hay UN único
                    // componente (así la asociación es unívoca). Con varios
                    // componentes, quedan como alignments sueltos ligados al mismo
                    // Pipe Network — no rompe nada, solo no hay Reference único.
                    EsGravedad = !sinBuzones && componentes.Count == 1,
                });
            }

            // Borrar los pipes marcados como "padre de bancoducto": las
            // estructuras (buzones) creadas quedan intactas, pero el cilindro
            // 3D del pipe desaparece — el sólido del bancoducto ya lo
            // reemplaza. Se hace DESPUÉS de reponer invert/rim para no romper
            // esos ajustes (que aún referencian los pipes por ObjectId).
            int erased = 0;
            foreach (var eid in pipesToErase)
            {
                try
                {
                    var ent = tr.GetObject(eid, OpenMode.ForWrite) as Autodesk.AutoCAD.DatabaseServices.Entity;
                    if (ent != null && !ent.IsErased) { ent.Erase(true); erased++; }
                }
                catch { }
            }
            if (erased > 0)
                Dbg("PIPE_DUCTBANK_ERASED", ("red", nm), ("count", erased.ToString()));

            ed.WriteMessage($"\n✓ Red {(sinBuzones ? "conduit" : "gravedad")} '{nm}': " +
                             $"{createdStructs.Count} nodos, {nPipes} tuberías, " +
                             $"{componentes.Count} componente(s) para eje.");
            return netId;
        }

        // Agrupa los pipes en componentes conectados por coincidencia de
        // coordenadas de sus vértices (Union-Find). Devuelve, por cada
        // componente, la lista de puntos concatenada (traza para el alignment)
        // y los structIds de los extremos absolutos del componente.
        private static List<(List<TrazaPt> traza, ObjectId startSt, ObjectId endSt)>
            AgruparPipesPorComponente(
                List<ImportPipe> pipes,
                List<(List<TrazaPt> pts, ObjectId startSt, ObjectId endSt)> pipeTrazas)
        {
            int n = pipeTrazas.Count;
            var salida = new List<(List<TrazaPt>, ObjectId, ObjectId)>();
            if (n == 0) return salida;

            // Union-Find: cada pipe se identifica por su índice.
            int[] parent = new int[n];
            for (int i = 0; i < n; i++) parent[i] = i;
            int Find(int a) { while (parent[a] != a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; }
            void Union(int a, int b) { int ra = Find(a), rb = Find(b); if (ra != rb) parent[ra] = rb; }

            // Indexar por coordenada de vértice (redondeada a 2 decimales de pie,
            // ~6 mm de tolerancia — suficiente para coincidencias reales, evita
            // que ruido decimal desune pipes que sí se tocan).
            string Key(Point3d p) =>
                $"{Math.Round(p.X, 2)}|{Math.Round(p.Y, 2)}";
            var byVert = new Dictionary<string, int>();
            for (int i = 0; i < n; i++)
            {
                foreach (var v in pipeTrazas[i].pts)
                {
                    string k = Key(v.P);
                    if (byVert.TryGetValue(k, out int j)) Union(i, j);
                    else byVert[k] = i;
                }
            }

            // Agrupar por raíz de UF.
            var porRaiz = new Dictionary<int, List<int>>();
            for (int i = 0; i < n; i++)
            {
                int r = Find(i);
                if (!porRaiz.ContainsKey(r)) porRaiz[r] = new List<int>();
                porRaiz[r].Add(i);
            }

            // Para cada componente: armar CADENAS de tubos unidos extremo con
            // extremo, y un alineamiento por cadena.
            //
            // Antes se concatenaban las trazas de todo el componente en el orden
            // de la lista. Si un tubo no empezaba donde terminaba el anterior (en
            // una cruz, una T, una Y o una conexión vertical), la polilínea
            // saltaba en línea recta de un extremo a otro: aparecía un eje que no
            // pasaba por ningún tubo. Ahora una cadena solo continúa en un punto
            // donde se tocan EXACTAMENTE dos extremos y ningún otro tubo pasa por
            // ahí (un empalme simple). En cualquier otra juntura cada tubo sigue
            // en su propia cadena. Así cada tramo de un eje está sobre un tubo.
            foreach (var kv in porRaiz)
            {
                var miembros = kv.Value;
                // Extremos que caen en cada punto, y puntos por los que PASA un tubo.
                var extremosEn = new Dictionary<string, int>();
                var interiores = new HashSet<string>();
                foreach (int i in miembros)
                {
                    var pts = pipeTrazas[i].pts;
                    if (pts.Count < 2) continue;
                    foreach (string k in new[] { Key(pts[0].P), Key(pts[pts.Count - 1].P) })
                        extremosEn[k] = extremosEn.TryGetValue(k, out int c) ? c + 1 : 1;
                    for (int v = 1; v < pts.Count - 1; v++) interiores.Add(Key(pts[v].P));
                }
                bool EmpalmeSimple(string k) =>
                    extremosEn.TryGetValue(k, out int c) && c == 2 && !interiores.Contains(k);

                var usados = new HashSet<int>();
                foreach (int semilla in miembros)
                {
                    if (usados.Contains(semilla) || pipeTrazas[semilla].pts.Count < 2) continue;
                    usados.Add(semilla);
                    var cadena = new List<TrazaPt>(pipeTrazas[semilla].pts);
                    ObjectId startSt = pipeTrazas[semilla].startSt, endSt = pipeTrazas[semilla].endSt;

                    // Hacia adelante: el siguiente tubo EMPIEZA donde termina la cadena.
                    while (true)
                    {
                        string k = Key(cadena[cadena.Count - 1].P);
                        if (!EmpalmeSimple(k)) break;
                        int j = BuscarTuboConExtremo(miembros, usados, pipeTrazas, k, Key);
                        if (j < 0) break;
                        usados.Add(j);
                        var (pts, sSt, eSt) = pipeTrazas[j];
                        bool invertir = Key(pts[0].P) != k;
                        var t = invertir ? InvertirTraza(pts) : pts;
                        // El primer punto repite el último de la cadena: se omite,
                        // pero su bulge (arco que arranca ahí) pasa al que se queda.
                        cadena[cadena.Count - 1] = new TrazaPt(cadena[cadena.Count - 1].P, t[0].Bulge);
                        for (int v = 1; v < t.Count; v++) cadena.Add(t[v]);
                        endSt = invertir ? sSt : eSt;
                    }
                    // Hacia atrás: el tubo anterior TERMINA donde empieza la cadena.
                    while (true)
                    {
                        string k = Key(cadena[0].P);
                        if (!EmpalmeSimple(k)) break;
                        int j = BuscarTuboConExtremo(miembros, usados, pipeTrazas, k, Key);
                        if (j < 0) break;
                        usados.Add(j);
                        var (pts, sSt, eSt) = pipeTrazas[j];
                        bool invertir = Key(pts[pts.Count - 1].P) != k;
                        var t = invertir ? InvertirTraza(pts) : pts;
                        // Se antepone sin su último punto (repetido); ese último
                        // punto no lleva arco propio, así que no se pierde nada.
                        cadena.InsertRange(0, t.Take(t.Count - 1));
                        startSt = invertir ? eSt : sSt;
                    }
                    if (cadena.Count >= 2) salida.Add((cadena, startSt, endSt));
                }
            }
            return salida;
        }

        // Tubo del componente, aún sin usar, con un EXTREMO en el punto `k`.
        private static int BuscarTuboConExtremo(List<int> miembros, HashSet<int> usados,
            List<(List<TrazaPt> pts, ObjectId startSt, ObjectId endSt)> pipeTrazas,
            string k, Func<Point3d, string> key)
        {
            foreach (int j in miembros)
            {
                if (usados.Contains(j)) continue;
                var pts = pipeTrazas[j].pts;
                if (pts.Count < 2) continue;
                if (key(pts[0].P) == k || key(pts[pts.Count - 1].P) == k) return j;
            }
            return -1;
        }

        // Traza recorrida al revés. El bulge del vértice i describe el tramo
        // i→i+1; al invertir, ese tramo pasa a arrancar en el otro extremo y el
        // arco gira en sentido contrario (signo cambiado).
        private static List<TrazaPt> InvertirTraza(List<TrazaPt> pts)
        {
            int n = pts.Count;
            var r = new List<TrazaPt>(n);
            for (int k = 0; k < n; k++)
            {
                double b = k < n - 1 ? -pts[n - 2 - k].Bulge : 0.0;
                r.Add(new TrazaPt(pts[n - 1 - k].P, b));
            }
            return r;
        }

        // Offset entre StartPoint.Z (eje del tubo) y la "Elevación de rasante" que
        // Civil 3D muestra en Properties. En C3D 2020+ ese valor mostrado es
        //     invert = StartPoint.Z − InnerHeight/2
        // para pipes RECTANGULARES, y = StartPoint.Z − InnerDiameter/2 para
        // circulares. `InnerHeight` es la propiedad correcta en rectangulares:
        // `InnerDiameterOrWidth` en un banco rectangular devuelve el ANCHO, que
        // NO es lo que C3D usa para calcular el invert.
        //
        // Prueba InnerHeight por reflexión (existe en pipes rectangulares); si no
        // está disponible o devuelve 0, cae a InnerDiameterOrWidth (que en pipes
        // circulares == diámetro y produce el offset correcto también).
        private static double OffsetEjeARasante(CivilDB.Pipe pp)
        {
            try
            {
                var pInnerH = pp.GetType().GetProperty("InnerHeight");
                if (pInnerH != null)
                {
                    var v = pInnerH.GetValue(pp);
                    if (v is double h && h > 1e-6) return h / 2.0;
                }
            }
            catch { }
            try { return pp.InnerDiameterOrWidth / 2.0; } catch { }
            return 0.0;
        }

        // Recorta `propio` (que suele estar en el centro del buzón) hasta el BORDE
        // exterior del buzón, avanzando en dirección hacia `otro`. Intenta primero
        // vía GeometricExtents; si esos extents son degenerados (típico justo
        // después de crear la structure en la misma transacción), usa el diámetro
        // interior del buzón + un margen de pared. Preserva Z de `propio`.
        private static Point3d RecortarAlBordeBuzon(Transaction tr, ObjectId structId,
                                                     Point3d propio, Point3d otro)
        {
            try
            {
                // Camino primario — GeometricExtents del buzón renderizado.
                Point3d p = ComandosCotarTuberias.PuntoVisualExtremo(structId, propio, otro, tr);
                double d = Math.Sqrt((p.X - propio.X) * (p.X - propio.X) +
                                      (p.Y - propio.Y) * (p.Y - propio.Y));
                if (d > 0.05) return p;                    // GeometricExtents dio valor útil
            }
            catch { }
            // Fallback — usar el ancho/diámetro interior del buzón + estimación de
            // pared (0.5' típico). Aproximación circular; funciona bien para buzones
            // circulares y para rectangulares (queda ligeramente dentro del rectángulo,
            // lo cual es preferible a exceder el borde).
            try
            {
                var st = tr.GetObject(structId, OpenMode.ForRead) as CivilDB.Structure;
                if (st == null) return propio;
                double innerW = 0.0; try { innerW = st.InnerDiameterOrWidth; } catch { }
                // Estimación conservadora de pared exterior (Civil 3D no expone
                // WallThickness uniformemente por versión). 0.5' cubre la mayoría
                // de buzones estándar de concreto.
                double radioExterior = innerW * 0.5 + 0.5;
                double dx = otro.X - propio.X, dy = otro.Y - propio.Y;
                double len = Math.Sqrt(dx * dx + dy * dy);
                if (len < 1e-9 || radioExterior < 1e-6) return propio;
                double nx = dx / len, ny = dy / len;
                return new Point3d(propio.X + nx * radioExterior,
                                    propio.Y + ny * radioExterior, propio.Z);
            }
            catch { return propio; }
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

            ObjectId plId = SeleccionarListaPresion(db, tr, plc, pipes, ed);
            if (plId == ObjectId.Null) plId = plc[0];
            PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(plId, OpenMode.ForRead);
            ed.WriteMessage($"\n'{nombre}': Parts List de presión = '{pl.Name}'.");

            var tubos = pl.GetParts(CivilDB.PressurePartDomainType.Pipe);
            if (tubos == null || tubos.Count == 0)
            { ed.WriteMessage($"\n'{nombre}': sin tubos en la Parts List de presión."); return ObjectId.Null; }

            ObjectId netId = CivilDB.PressurePipeNetwork.Create(db, nombre);
            CivilDB.PressurePipeNetwork net = (CivilDB.PressurePipeNetwork)tr.GetObject(netId, OpenMode.ForWrite);
            net.PartsListId = plId;

            // Tubos que terminan a mitad de otro (misma cota) → T: se parte el
            // tramo que pasa ANTES de crear nada, para que la juntura tenga sus
            // 3 extremos.
            FusionarCodosSeguidos(pipes, ed);
            PartirTramosEnTes(pipes, ed);

            // Crear tuberías con matching per-pipe por diámetro
            int nPipes = 0;
            var createdPipeIds = new List<ObjectId>();
            var pipeEndpoints = new List<(Point3d start, Point3d end, ObjectId id)>();
            // Traza per-pipe (para Union-Find de componentes conectados).
            var pipeTrazasPres = new List<List<TrazaPt>>();

            // Trazabilidad Python → Civil 3D, por tubo creado: de qué utilidad de
            // la app viene, qué tramo (T1, T2… como en la tabla «Cotas por
            // tramo») y qué SOLERA pidió el usuario en cada extremo (puerto 0 =
            // inicio, 1 = fin). Sirve para no unir utilidades distintas a cotas
            // distintas y para contrastar al final lo pedido con lo obtenido.
            var fuenteTubo = new Dictionary<ObjectId, int>();
            var tramoTubo = new Dictionary<ObjectId, int>();
            var etiquetaFuente = new Dictionary<int, string>();
            var zPython = new Dictionary<(ObjectId, int), double>();
            var xyPython = new Dictionary<(ObjectId, int), Point2d>();
            int srcIdx = -1;

            foreach (var ip in pipes)
            {
                srcIdx++;
                etiquetaFuente[srcIdx] = ip.PipeIdx >= 0
                    ? $"utilidad #{ip.PipeIdx}"
                    : $"'{ip.Layer}' ({srcIdx + 1})";
                PresStyles.PressurePartSize tuboElegido = MatchPresionTubo(tubos, ip.Diameter, ip.PipeFamily);
                Dbg("PIPE_PRES_MATCH", ("pedido_fam", ip.PipeFamily ?? ""),
                    ("pedido_size", ip.PipeSize ?? ""), ("diam", ip.Diameter.ToString("F1")),
                    ("elegida", tuboElegido?.Description ?? "?"));
                Dl(ed, $"\n  [PIPE_PRES_MATCH] pedido: diam={ip.Diameter:F1} size='{ip.PipeSize}' fam='{ip.PipeFamily}' " +
                                $"→ elegida: '{tuboElegido?.Description ?? "NINGUNA"}'");

                int nVerts = ip.Vertices.Count;
                // Cotas por tramo (mismo patrón que gravedad, ver InterpolateZ en
                // el bucle de gravedad). VertexInv guarda la Z de SALIDA del
                // vértice (OUT, se usa como start del siguiente tramo) y
                // VertexInvIn la de ENTRADA (IN, se usa como end del tramo
                // anterior). Cuando los dicts están vacíos, InterpolateZ cae
                // solo a la interpolación lineal InvStart→InvEnd — el
                // comportamiento previo se preserva. Antes esta rama usaba
                // solamente ZalongByDistance(InvStart, InvEnd) y perdía toda
                // cota que el usuario editara por tramo en la tabla.
                double[] zOut = InterpolateZ(ip, nVerts, ip.VertexInv);
                double[] zIn  = InterpolateZ(ip, nVerts, ip.VertexInvIn);

                // Presión: sin tubos curvos (los quiebres son codos/fittings), así
                // que todos los puntos van con bulge 0 — el eje queda recto igual
                // que antes.
                var pipeTraza = new List<TrazaPt>();
                for (int i = 0; i < nVerts; i++)
                    pipeTraza.Add(new TrazaPt(new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zOut[i])));
                pipeTrazasPres.Add(pipeTraza);

                for (int i = 0; i < nVerts - 1; i++)
                {
                    // start = OUT del vértice i, end = IN del vértice i+1 — así
                    // cada tramo tiene su cota independiente (asimetría por
                    // tramo, igual que en gravedad).
                    double z1 = zOut[i];
                    double z2 = zIn[i + 1];

                    Point3d p1 = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, z1);
                    Point3d p2 = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, z2);
                    if (p1.DistanceTo(p2) < 1e-6) continue;

                    ObjectId pid = net.AddLinePipe(new LineSegment3d(p1, p2), tuboElegido);
                    createdPipeIds.Add(pid);
                    pipeEndpoints.Add((p1, p2, pid));
                    fuenteTubo[pid] = srcIdx;
                    tramoTubo[pid] = ip.TramoPython != null && i < ip.TramoPython.Count ? ip.TramoPython[i] : i;
                    zPython[(pid, 0)] = z1; zPython[(pid, 1)] = z2;
                    xyPython[(pid, 0)] = new Point2d(p1.X, p1.Y);
                    xyPython[(pid, 1)] = new Point2d(p2.X, p2.Y);

                    // Abandonada (presión): solo cambia el 3D (Model) a discontinuo.
                    if (ip.Abandoned)
                    {
                        try
                        {
                            CivilDB.PressurePipe ppAb = (CivilDB.PressurePipe)tr.GetObject(pid, OpenMode.ForWrite);
                            ObjectId absId = AsegurarEstiloAbandonadoPresion(db, civilDoc, tr, ppAb.StyleId);
                            if (absId != ObjectId.Null) ppAb.StyleId = absId;
                        }
                        catch (Exception exAb) { Dbg("ABANDONED_APPLY_FAIL", ("tipo", "presion"), ("error", exAb.Message)); }
                    }

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

            // ── Cotas en JUNTURAS de presión ───────────────────────────────
            // Antes se agrupaban los extremos SOLO por XY y se les imponía la Z
            // promedio. Dos utilidades DISTINTAS que se tocan en planta pero van
            // a cotas distintas (una pasa por encima de la otra) quedaban así
            // arrastradas a una cota intermedia que nadie pidió, y encima se
            // unían con una Y. Ahora:
            //   · Una MISMA utilidad en su propio vértice se unifica como antes
            //     (sus tramos consecutivos son la misma tubería).
            //   · Utilidades DISTINTAS solo se unen si están a la misma cota
            //     (±Z_TOL_JUNTA, el mismo criterio con que la app marca un cruce
            //     como conflicto). Si no, cada una conserva su cota y NO se unen:
            //     unirlas es cosa de una conexión vertical aprobada en la app.
            // Cada extremo recibe una etiqueta de grupo; AgruparJunturas solo une
            // extremos con la misma etiqueta.
            const double Z_TOL_JUNTA = 0.10;
            var grupoCota = new Dictionary<(ObjectId, int), int>();
            {
                string Nombre((ObjectId id, int port) k) =>
                    (fuenteTubo.TryGetValue(k.id, out int s) && etiquetaFuente.TryGetValue(s, out string et) ? et : "?") +
                    (tramoTubo.TryGetValue(k.id, out int t) ? $" T{t + 1}" : "") +
                    (k.port == 0 ? " inicio" : " fin");

                var pts = new List<(Point3d pos, ObjectId id, int port)>();
                foreach (var pe in pipeEndpoints)
                { pts.Add((pe.start, pe.id, 0)); pts.Add((pe.end, pe.id, 1)); }
                var usado = new bool[pts.Count];
                var zNueva = new Dictionary<(ObjectId, int), double>();
                int etiqueta = 0, nSeparadas = 0, nUnificadas = 0;

                for (int i = 0; i < pts.Count; i++)
                {
                    if (usado[i]) continue;
                    // 1) Extremos que coinciden en PLANTA (mismo criterio y
                    //    tolerancia que AgruparJunturas, pero sin mirar Z).
                    var cl = new List<int> { i }; usado[i] = true;
                    double ax = pts[i].pos.X, ay = pts[i].pos.Y;
                    for (int k = i + 1; k < pts.Count; k++)
                    {
                        if (usado[k]) continue;
                        double dx = pts[k].pos.X - ax / cl.Count, dy = pts[k].pos.Y - ay / cl.Count;
                        if (dx * dx + dy * dy > 0.25) continue;      // 0.5 ft
                        cl.Add(k); usado[k] = true;
                        ax += pts[k].pos.X; ay += pts[k].pos.Y;
                    }
                    if (cl.Count < 2) { grupoCota[(pts[i].id, pts[i].port)] = etiqueta++; continue; }
                    double cx = ax / cl.Count, cy = ay / cl.Count;

                    // 2) Por utilidad de origen: cada una, su cota en ese punto.
                    var subgrupos = cl
                        .GroupBy(ix => fuenteTubo.TryGetValue(pts[ix].id, out int s) ? s : -1 - ix)
                        .Select(g => (idxs: g.ToList(), z: g.Average(ix => pts[ix].pos.Z)))
                        .OrderBy(sg => sg.z).ToList();

                    // 3) Utilidades distintas: juntas solo si están a la misma cota.
                    var grupos = new List<List<(List<int> idxs, double z)>>();
                    foreach (var sg in subgrupos)
                    {
                        if (grupos.Count > 0 && Math.Abs(sg.z - grupos[grupos.Count - 1].Last().z) <= Z_TOL_JUNTA)
                            grupos[grupos.Count - 1].Add(sg);
                        else
                            grupos.Add(new List<(List<int> idxs, double z)> { sg });
                    }

                    foreach (var g in grupos)
                    {
                        var idxs = g.SelectMany(sg => sg.idxs).ToList();
                        int lab = etiqueta++;
                        double zMedia = idxs.Average(ix => pts[ix].pos.Z);
                        foreach (int ix in idxs)
                        {
                            grupoCota[(pts[ix].id, pts[ix].port)] = lab;
                            if (idxs.Count >= 2) zNueva[(pts[ix].id, pts[ix].port)] = zMedia;
                        }
                        // Contraste: si unificar movió alguna cota, decir cuánto.
                        if (idxs.Count >= 2 && idxs.Any(ix => Math.Abs(pts[ix].pos.Z - zMedia) > 0.005))
                        {
                            nUnificadas++;
                            string pedidas = string.Join(", ", idxs.Select(ix =>
                                $"{Nombre((pts[ix].id, pts[ix].port))} {pts[ix].pos.Z:F2}"));
                            ed.WriteMessage($"\n  · [COTAS] ({cx:F2},{cy:F2}): cotas unificadas a {zMedia:F2} ft " +
                                $"— en Python: {pedidas}.");
                        }
                    }
                    if (grupos.Count > 1)
                    {
                        nSeparadas++;
                        string detalle = string.Join(" | ", grupos.Select(g =>
                            string.Join(", ", g.Select(sg => Nombre((pts[sg.idxs[0]].id, pts[sg.idxs[0]].port)))) +
                            $" a {g.Average(sg => sg.z):F2} ft"));
                        ed.WriteMessage($"\n  · [COTAS] ({cx:F2},{cy:F2}): se tocan en planta pero a DISTINTA cota — " +
                            $"NO se unen, cada una conserva la suya: {detalle}. " +
                            "Para unirlas, aprueba una conexión vertical en la app.");
                    }
                }

                if (zNueva.Count > 0)
                {
                    var updated = new List<(Point3d start, Point3d end, ObjectId id)>();
                    foreach (var pe in pipeEndpoints)
                    {
                        Point3d s = pe.start, e = pe.end;
                        if (zNueva.TryGetValue((pe.id, 0), out double zs)) s = new Point3d(s.X, s.Y, zs);
                        if (zNueva.TryGetValue((pe.id, 1), out double ze)) e = new Point3d(e.X, e.Y, ze);
                        if (!s.IsEqualTo(pe.start) || !e.IsEqualTo(pe.end))
                        {
                            try
                            {
                                var pp = (CivilDB.PressurePipe)tr.GetObject(pe.id, OpenMode.ForWrite);
                                pp.StartPoint = s; pp.EndPoint = e;
                            }
                            catch { }
                        }
                        updated.Add((s, e, pe.id));
                    }
                    pipeEndpoints.Clear(); pipeEndpoints.AddRange(updated);
                }
                Dbg("PRES_JUNTAS_COTAS", ("separadas", nSeparadas.ToString()),
                    ("unificadas", nUnificadas.ToString()));
            }

            // ── SOLERA → EJE: subir los tubos ANTES de colocar los accesorios ──
            // ORDEN CRÍTICO — CAUSA RAÍZ del "codo un radio por debajo del tubo".
            // InvStart/InvEnd que trae el DXF son la SOLERA; PressurePipe.StartPoint.Z
            // es el EJE del tubo  →  eje = invert + NominalDiameter/2.
            //
            // Esta conversión TIENE que ocurrir ANTES de ProcesarJunturasPresion,
            // porque net.AddFitting(pos, pieza) toma la Z de 'pos' TAL CUAL, y esa
            // 'pos' es j.Ubicacion: el centroide de pipeEndpoints. Si se convertía
            // DESPUÉS (como antes), cada codo/tee nacía a nivel de SOLERA y quedaba
            // exactamente un radio por debajo del eje del tubo → el tubo parece
            // entrar por la parte alta del codo.
            //
            // Corregirlo a posteriori escribiendo PressurePart.Position NO sirve:
            // para entonces la pieza YA está conectada y Civil 3D re-resuelve la
            // conexión arrastrando los tubos con ella, así que el desfase RELATIVO
            // codo-tubo sobrevive (y el contador seguía diciendo "realineados N/N").
            // Los flujos que SÍ funcionan insertan el accesorio en un punto que ya
            // está a nivel de eje: UNIR_TUBERIAS_PRESION (RedesPresion.cs:799),
            // UNIR_VARIAS_PRESION (RedesPresionRamales.cs:81) y RAMAL
            // (RedesPresionRamales.cs:238). El import era el único que no lo hacía.
            //
            // Aquí los tubos todavía NO están conectados a nada, así que escribir
            // StartPoint/EndPoint es una operación libre y segura.
            //
            // NominalDiameter YA viene en unidades del dibujo (pies) — confirmado con
            // datos reales: un tubo "12 in" tiene NominalDiameter = 1.000. NO dividir
            // entre 12 acá (ese bug daba un radio ~12× más chico que el real).
            {
                var enEje = new List<(Point3d start, Point3d end, ObjectId id)>(pipeEndpoints.Count);
                int nSubidos = 0; double rMax = 0.0;
                foreach (var pe in pipeEndpoints)
                {
                    Point3d s = pe.start, e = pe.end;
                    try
                    {
                        var pp = (CivilDB.PressurePipe)tr.GetObject(pe.id, OpenMode.ForWrite);
                        double r = 0.0;
                        try { r = pp.NominalDiameter / 2.0; } catch { }
                        pp.StartPoint = new Point3d(pe.start.X, pe.start.Y, pe.start.Z + r);
                        pp.EndPoint   = new Point3d(pe.end.X,   pe.end.Y,   pe.end.Z   + r);
                        // Releer de la BD: pipeEndpoints es lo que alimenta
                        // AgruparJunturas y por tanto la Z con la que NACE cada
                        // accesorio — tiene que reflejar lo que quedó realmente
                        // guardado, no lo que pedimos.
                        s = pp.StartPoint; e = pp.EndPoint;
                        if (r > rMax) rMax = r;
                        nSubidos++;
                    }
                    catch { }
                    enEje.Add((s, e, pe.id));
                }
                pipeEndpoints.Clear();
                pipeEndpoints.AddRange(enEje);
                Dbg("PRES_SOLERA_A_EJE", ("red", nombre), ("tubos", nSubidos.ToString()),
                    ("radio_max_ft", rMax.ToString("F3")));
            }

            // Auto-conectar tuberías en vértices compartidos e insertar fittings
            int nFittings = 0;
            var fittings = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);

            // Agrupa TODOS los extremos por sitio físico (no por PAR) y decide un
            // solo accesorio por juntura — Codo/Reductor/Unión para 2 tuberías,
            // Tee/Cruz para 3/4 — reutilizando la misma lógica que
            // UNIR_TUBERIAS_PRESION/UNIR_VARIAS_PRESION (ver RedesPresionJunturas.cs).
            // Antes esto era un bucle PAREADO que, en un empalme de 3+ tuberías,
            // podía crear varios codos superpuestos conectados solo de a 2.
            var (nFit, nDirect, nFail) = ComandosPresion.ProcesarJunturasPresion(
                net, tr, ed, fittings, pipeEndpoints, grupoCota: grupoCota);
            nFittings = nFit;


            // Alineamiento (eje) por componente conectado — Union-Find igual
            // que en gravedad, para no unir sub-redes desconectadas con un eje.
            var pipeTrazasTuples = pipeTrazasPres.Select(pts =>
                (pts, ObjectId.Null, ObjectId.Null)).ToList();
            var componentesPres = AgruparPipesPorComponente(pipes, pipeTrazasTuples);
            int nAligns = 0;
            foreach (var comp in componentesPres)
            {
                int cIdx2 = nAligns + 1;
                string nomAlign = componentesPres.Count == 1
                    ? nombre + "-eje"
                    : $"{nombre}-{cIdx2}-eje";
                ObjectId alignId = ComandosAlineamientos.CrearAlineamientoDesdePts(
                    db, civilDoc, tr, comp.traza, nomAlign);
                if (alignId != ObjectId.Null)
                {
                    // Asociar solo si hay un único componente (Reference alignment unívoco).
                    if (componentesPres.Count == 1)
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
                    nAligns++;
                    ed.WriteMessage($"\n  · Eje '{nomAlign}' creado.");
                }
            }

            // Corrección automática de fittings: el DXF trae el fitting original
            // (p.ej. un codo 4x4) sin ajustarlo al diámetro real del tubo con el
            // que quedó conectado (p.ej. 12"). Reutiliza la misma lógica de
            // CORREGIR_FITTINGS_PRESION, sin preguntar (ver RedesPresion.cs).
            var (fitDetectados, fitCorregidos, fitFallidos) =
                ComandosPresion.CorregirFittingsDeRed(net, tr, ed, preguntar: false);
            if (fitDetectados > 0)
                ed.WriteMessage($"\n  · Fittings con diámetro incorrecto: {fitCorregidos}/{fitDetectados} corregido(s)" +
                                (fitFallidos > 0 ? $", {fitFallidos} sin pieza disponible en la Parts List" : "") + ".");

            // ── Verificación (SOLO LECTURA) accesorio vs. eje del tubo ──────────
            // La conversión solera → eje ya se hizo ARRIBA, ANTES de colocar los
            // accesorios, así que cada codo/tee nació ya a nivel de eje y aquí no
            // hay nada que mover. Este bloque solo MIDE y deja el número en el log:
            // si el desfase reapareciera, PRES_CHK_ACCESORIOS_EJE dice exactamente
            // cuántas piezas y cuántos pies, en vez de dejarlo en "se ve raro".
            //
            // Deliberadamente NO se reposiciona aquí: en este punto las piezas ya
            // están conectadas, y escribir PressurePart.Position sobre una pieza
            // conectada hace que Civil 3D re-resuelva la conexión y arrastre los
            // tubos, con lo que el desfase relativo no se corrige (ese fue el
            // intento fallido anterior).
            try
            {
                int nTot = 0, nDesal = 0; double peor = 0.0;

                // Δz de una pieza respecto al extremo de tubo conectado más cercano
                // EN 2D (en Z pueden diferir justo por lo que venimos a medir).
                Func<CivilDB.PressurePart, double?> desfaseZ = parte =>
                {
                    Point3d pos = parte.Position;
                    double mejorD = double.MaxValue; double? zTubo = null;
                    for (int i = 0; i < parte.ConnectionCount; i++)
                    {
                        var c = parte.GetConnectionAt(i);
                        if (c.ConnectedId == ObjectId.Null || !c.ConnectedId.IsValid) continue;
                        var pipe = tr.GetObject(c.ConnectedId, OpenMode.ForRead) as CivilDB.PressurePipe;
                        if (pipe == null) continue;
                        var p2 = new Point2d(pos.X, pos.Y);
                        double dS = p2.GetDistanceTo(new Point2d(pipe.StartPoint.X, pipe.StartPoint.Y));
                        double dE = p2.GetDistanceTo(new Point2d(pipe.EndPoint.X, pipe.EndPoint.Y));
                        double d = Math.Min(dS, dE);
                        if (d < mejorD) { mejorD = d; zTubo = (dS <= dE ? pipe.StartPoint : pipe.EndPoint).Z; }
                    }
                    return zTubo.HasValue ? Math.Abs(zTubo.Value - pos.Z) : (double?)null;
                };

                var idsPiezas = new List<ObjectId>();
                foreach (ObjectId fid in net.GetFittingIds()) idsPiezas.Add(fid);
                foreach (ObjectId aid in net.GetAppurtenanceIds()) idsPiezas.Add(aid);

                foreach (ObjectId pid in idsPiezas)
                {
                    var parte = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePart;
                    if (parte == null) continue;
                    nTot++;
                    double? dz = desfaseZ(parte);
                    if (!dz.HasValue) continue;      // pieza suelta: nada con qué comparar
                    if (dz.Value > peor) peor = dz.Value;
                    if (dz.Value > 1e-3) nDesal++;
                }

                Dbg("PRES_CHK_ACCESORIOS_EJE", ("red", nombre), ("total", nTot.ToString()),
                    ("desalineados", nDesal.ToString()), ("peor_dz_ft", peor.ToString("F4")));
                if (nDesal > 0)
                    ed.WriteMessage($"\n  ⚠ {nDesal}/{nTot} accesorio(s) no coinciden en Z con el eje del tubo " +
                                    $"(máx {peor:F3} ft) — ver PRES_CHK_ACCESORIOS_EJE en el CSV de depuración.");
                else if (nTot > 0)
                    ed.WriteMessage($"\n  · {nTot} accesorio(s) alineados al eje de las tuberías (Δz máx {peor:F4} ft).");
            }
            catch (Exception exChk)
            {
                ed.WriteMessage($"\n  ⚠ No se pudo verificar la alineación de los accesorios: {exChk.Message}");
            }

            // ── Contraste Python → Civil 3D: cota pedida vs. cota obtenida ──────
            // Para cada extremo de cada tramo: la solera que el usuario puso en
            // la app frente a la solera con la que quedó el tubo en el dibujo.
            // Los recortes contra accesorios deslizan el extremo sobre su propia
            // recta, así que la recta final se evalúa en el XY ORIGINAL: un
            // recorte no cuenta como cambio de cota, un desplazamiento en Z sí.
            try
            {
                const double TOL_CONTRASTE = 0.01;   // ft
                int nIguales = 0; var distintos = new List<string>();
                foreach (var kv in zPython)
                {
                    var (pid, port) = kv.Key;
                    if (!xyPython.TryGetValue(kv.Key, out Point2d xy)) continue;
                    CivilDB.PressurePipe pp;
                    try { pp = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe; } catch { continue; }
                    if (pp == null) continue;
                    Point3d s = pp.StartPoint, e = pp.EndPoint;
                    double dx = e.X - s.X, dy = e.Y - s.Y, l2 = dx * dx + dy * dy;
                    if (l2 < 1e-9) continue;
                    double t = ((xy.X - s.X) * dx + (xy.Y - s.Y) * dy) / l2;
                    double r = 0; try { r = pp.NominalDiameter / 2.0; } catch { }
                    double solFinal = s.Z + t * (e.Z - s.Z) - r;
                    double delta = solFinal - kv.Value;
                    if (Math.Abs(delta) <= TOL_CONTRASTE) { nIguales++; continue; }
                    string quien = (fuenteTubo.TryGetValue(pid, out int sIx) && etiquetaFuente.TryGetValue(sIx, out string et) ? et : "?") +
                        (tramoTubo.TryGetValue(pid, out int tIx) ? $" T{tIx + 1}" : "") +
                        (port == 0 ? " inicio" : " fin");
                    distintos.Add($"{quien}: Python {kv.Value:F2} ft → Civil 3D {solFinal:F2} ft (Δ {delta:+0.00;-0.00})");
                }
                int total = nIguales + distintos.Count;
                if (distintos.Count == 0)
                    ed.WriteMessage($"\n  · [COTAS] Contraste Python → Civil 3D: los {total} extremos coinciden (±{TOL_CONTRASTE} ft).");
                else
                {
                    ed.WriteMessage($"\n  ⚠ [COTAS] Contraste Python → Civil 3D: {distintos.Count} de {total} extremos NO quedaron a la cota pedida:");
                    foreach (string d in distintos.Take(30)) ed.WriteMessage($"\n      · {d}");
                    if (distintos.Count > 30) ed.WriteMessage($"\n      · (+{distintos.Count - 30} más)");
                }
            }
            catch (Exception exCot)
            {
                ed.WriteMessage($"\n  ⚠ [COTAS] No se pudo contrastar cotas: {exCot.Message}");
            }

            ed.WriteMessage($"\n✓ Red presión '{nombre}': {nPipes} tubería(s), {nFittings} fitting(s), " +
                            $"{componentesPres.Count} componente(s) para eje" +
                            (nDirect > 0 ? $", {nDirect} unión(es) directa(s)" : "") +
                            (nFail > 0 ? $", {nFail} juntura(s) sin resolver (ver avisos [JUNTURA] arriba)" : "") + ".");

            return netId;
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
        //  LIMPIAR DUPLICADOS PARTSIZE — quita variantes "Nombre - N"
        //  cuando existe el "Nombre" base con las MISMAS dimensiones (W/H).
        //  Estas variantes las genera Civil 3D al llamar AddPartSize sobre
        //  familias donde los valores no se lograron cambiar; acumulan basura.
        // =================================================================
        private void LimpiarDuplicadosPartSize(Editor ed, Database db)
        {
            try
            {
                CivilDocument civilDoc = CivilApplication.ActiveDocument;
                var plSet = civilDoc.Styles.PartsListSet;
                int totalBorrados = 0;
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        var pl = tr.GetObject(plSet[i], OpenMode.ForWrite) as PartsStyles.PartsList;
                        if (pl == null) continue;
                        foreach (CivilDB.DomainType dom in new[] { CivilDB.DomainType.Pipe, CivilDB.DomainType.Structure })
                        {
                            foreach (ObjectId fid in pl.GetPartFamilyIdsByDomain(dom))
                            {
                                var fam = tr.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                                if (fam == null || fam.PartSizeCount < 2) continue;
                                // Estrategia: agrupar PartSizes por "nombre base" (quitando el
                                // sufijo " - N"). En cada grupo con más de uno, dejar solo el
                                // primero (o el que NO tenga sufijo) y borrar los demás.
                                var rx = new System.Text.RegularExpressions.Regex(@"^(.*?)(\s-\s\d+)?$");
                                var grupos = new Dictionary<string, List<ObjectId>>(StringComparer.OrdinalIgnoreCase);
                                var keepPreferred = new Dictionary<string, ObjectId>(StringComparer.OrdinalIgnoreCase);
                                for (int k = 0; k < fam.PartSizeCount; k++)
                                {
                                    var sz = tr.GetObject(fam[k], OpenMode.ForRead) as PartsStyles.PartSize;
                                    string nm = sz?.Name ?? "";
                                    var m = rx.Match(nm);
                                    string baseName = m.Success ? m.Groups[1].Value : nm;
                                    bool hasSuffix = m.Success && !string.IsNullOrEmpty(m.Groups[2].Value);
                                    if (!grupos.ContainsKey(baseName)) grupos[baseName] = new List<ObjectId>();
                                    grupos[baseName].Add(fam[k]);
                                    // preferimos el que NO tenga sufijo; si todos lo tienen, el 1º
                                    if (!keepPreferred.ContainsKey(baseName) || !hasSuffix)
                                    {
                                        if (!keepPreferred.ContainsKey(baseName) || !hasSuffix)
                                            keepPreferred[baseName] = fam[k];
                                    }
                                }
                                var aBorrar = new List<ObjectId>();
                                foreach (var kv in grupos)
                                {
                                    if (kv.Value.Count < 2) continue;
                                    ObjectId keep = keepPreferred[kv.Key];
                                    foreach (var sid in kv.Value)
                                        if (sid != keep) aBorrar.Add(sid);
                                }
                                foreach (var sid in aBorrar)
                                {
                                    try { fam.RemovePartSize(sid); totalBorrados++; } catch { }
                                }
                            }
                        }
                    }
                    tr.Commit();
                }
                if (totalBorrados > 0)
                    ed.WriteMessage($"\n  · Duplicados de PartSize borrados: {totalBorrados}");
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n  · (limpieza de duplicados falló: {ex.Message})");
            }
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
                            netKind.Equals("pressure", StringComparison.OrdinalIgnoreCase) ||
                            netKind.Equals("conduit", StringComparison.OrdinalIgnoreCase))
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
                                          string catalogId, CivilDB.DomainType dominio = CivilDB.DomainType.Structure,
                                          string guid = null)
        {
            // Se prefiere el GUID (clave estable, independiente del idioma/versión)
            // sobre el catalogId (Descripción localizada, que puede no calzar). Con
            // GUID el emparejamiento es EXACTO y no cae en la familia equivocada.
            bool usaGuid = !string.IsNullOrWhiteSpace(guid);
            if (string.IsNullOrWhiteSpace(catalogId) && !usaGuid)
            { Dbg("ASEGURAR_FAM_SKIP", ("motivo", "vacio")); return; }
            // ¿Ya está?
            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(dominio))
            {
                var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                bool m = usaGuid
                    ? MismoGuid(fam.GUID, guid)
                    : MatchCatalogIdPublic(catalogId, fam.Description ?? "");
                Dbg("ASEGURAR_FAM_CHECK", ("pedido", usaGuid ? "guid:" + guid : catalogId), ("dominio", dominio.ToString()),
                    ("candidato", fam.Description ?? ""),
                    ("match", m ? "true" : "false"), ("sizes", fam.PartSizeCount));
                if (m)
                {
                    // La familia ya está, pero puede haber sido agregada al PartsList con
                    // solo 1 tamaño (típico en familias personalizadas hechas a mano en
                    // Part Builder). Rehidratamos TODOS los tamaños del catálogo para
                    // que los tamaños que el Python muestra en el combo existan de verdad.
                    // Los duplicados que esto pueda generar los limpia LimpiarDuplicadosPartSize.
                    int antes = fam.PartSizeCount;
                    try
                    {
                        var famW = tr.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                        if (famW != null)
                        {
                            var filtro = new PartsStyles.SizeFilterRecord(famW);
                            for (int i = 0; i < filtro.ParamCount; i++)
                            {
                                var campo = filtro[i];
                                if (campo != null && !campo.IsReadOnly && campo.IsFromList)
                                    campo.IsMultipleSelect = true;
                            }
                            famW.AddPartSize(filtro);
                            Dbg("ASEGURAR_FAM_REHIDRATA", ("pedido", catalogId),
                                ("antes", antes), ("despues", famW.PartSizeCount));
                        }
                    }
                    catch (Exception exRe)
                    { Dbg("ASEGURAR_FAM_REHIDRATA_ERROR", ("pedido", catalogId), ("msg", exRe.Message)); }
                    Dbg("ASEGURAR_FAM_YA_ESTA", ("pedido", catalogId), ("descripcion", fam.Description ?? ""));
                    return;
                }
            }
            try
            {
                PartsStyles.DataPartFamily[] disp =
                    PartsStyles.PartsList.GetAvailablePartFamilies(dominio);
                if (disp == null || disp.Length == 0) return;
                PartsStyles.DataPartFamily elegido = null;
                foreach (var dpf in disp)
                {
                    if (usaGuid)
                    {
                        // Con GUID: match exacto, sin filtros de texto (el GUID ya
                        // identifica la familia correcta e independiente del idioma).
                        if (MismoGuid(dpf.GUID, guid))
                        { elegido = dpf; break; }
                        continue;
                    }
                    string desc = dpf.Description ?? "";
                    if (desc.IndexOf("Metric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    if (desc.IndexOf("métric", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    if (MatchCatalogIdPublic(catalogId, desc))
                    { elegido = dpf; break; }
                }
                if (elegido == null)
                {
                    Dbg("ASEGURAR_FAM_NO_ENCONTRADA_EN_CATALOGO", ("pedido", usaGuid ? "guid:" + guid : catalogId),
                        ("candidatos_en_catalogo", disp.Length));
                    ed.WriteMessage($"\n⚠ Familia '{(usaGuid ? guid : catalogId)}' pedida desde Python no se encontró en el catálogo disponible.");
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

        // Setea el sistema de coordenadas (Huso) del dibujo activo con un código
        // CS-MAP nativo (ej. "CA83VF" = NAD83 California zona V en pies = EPSG:2229).
        // El usuario lo elige en la georreferenciación (Python) y viaja en el DXF
        // como PDFCAD_META/CS_CODE. Best-effort: re-lee para confirmar; si el código
        // no fue aceptado avisa pero NUNCA aborta la importación de la red.
        private static void AplicarSistemaCoordenadas(Editor ed, string code)
        {
            try
            {
                var civilDoc = CivilApplication.ActiveDocument;
                var uz = civilDoc.Settings.DrawingSettings.UnitZoneSettings;
                string antes = ""; try { antes = uz.CoordinateSystemCode ?? ""; } catch { }
                uz.CoordinateSystemCode = code;
                string despues = ""; try { despues = uz.CoordinateSystemCode ?? ""; } catch { }
                if (string.Equals(despues, code, StringComparison.OrdinalIgnoreCase))
                    ed.WriteMessage($"\n✓ Sistema de coordenadas (Huso) del dibujo seteado a '{code}'.");
                else
                    ed.WriteMessage($"\n⚠ El código de coordenadas '{code}' no fue aceptado por Civil 3D " +
                                    $"(quedó '{despues}'). Verifica el código en el diálogo nativo 'Huso'. " +
                                    "La red SÍ se importó.");
                Dbg("CS_APLICAR", ("pedido", code), ("antes", antes), ("despues", despues));
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n⚠ No se pudo setear el sistema de coordenadas '{code}': {ex.Message}. " +
                                "La red SÍ se importó.");
                Dbg("CS_APLICAR_ERROR", ("pedido", code), ("msg", ex.Message));
            }
        }

        private static Dictionary<int, double> ParseVertexInv(string raw, double k)
        {
            var dict = new Dictionary<int, double>();
            if (string.IsNullOrWhiteSpace(raw)) return dict;
            foreach (string entry in raw.Split(';'))
            {
                if (string.IsNullOrWhiteSpace(entry)) continue;
                var parts = entry.Split('~');
                if (parts.Length < 2) continue;
                if (!int.TryParse(parts[0].Trim(), out int idx)) continue;
                if (!double.TryParse(parts[1].Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out double z)) continue;
                dict[idx] = z * k;
            }
            return dict;
        }

        // ── T a mitad de tramo ─────────────────────────────────────────────
        // Un tubo que TERMINA a mitad de un tramo de otro, a la misma cota, es
        // una T. Pero las junturas se arman solo con EXTREMOS de tubos, y el
        // tubo que pasa no tiene vértice ahí: no salía ningún accesorio. Se le
        // inserta un vértice en ese punto; el punto queda con 3 extremos y
        // ProcesarJunturasPresion pone la Tee (o la Y) de siempre.
        //
        // A otra cota (> tolZ) NO se parte: es un cruce, no una T; si el
        // usuario quiere unirlos lo aprueba como conexión vertical en la app.
        // Las cotas no se mueven: el tubo partido recibe TODAS sus cotas por
        // vértice explícitas (las que ya tenía) y el vértice nuevo la cota
        // exacta de su tramo en ese punto.
        private static void PartirTramosEnTes(List<ImportPipe> pipes, Editor ed,
            double tolXY = 0.5, double tolZ = 0.10)
        {
            string Nombre(ImportPipe p) => p.PipeIdx >= 0 ? $"utilidad #{p.PipeIdx}" : $"'{p.Layer}'";
            for (int vuelta = 0; vuelta < 1000; vuelta++)
            {
                bool partido = false;
                foreach (var b in pipes)                       // el que TERMINA en el otro
                {
                    int nb = b.Vertices?.Count ?? 0;
                    if (nb < 2) continue;
                    double[] zbOut = InterpolateZ(b, nb, b.VertexInv);
                    double[] zbIn = InterpolateZ(b, nb, b.VertexInvIn);
                    var extremos = new[] { (p: b.Vertices[0], z: zbOut[0]), (p: b.Vertices[nb - 1], z: zbIn[nb - 1]) };
                    foreach (var ext in extremos)
                    {
                        foreach (var a in pipes)               // el que PASA
                        {
                            int na = a.Vertices?.Count ?? 0;
                            if (ReferenceEquals(a, b) || na < 2) continue;
                            double[] zaOut = InterpolateZ(a, na, a.VertexInv);
                            double[] zaIn = InterpolateZ(a, na, a.VertexInvIn);
                            for (int k = 0; k < na - 1; k++)
                            {
                                Point2d p0 = a.Vertices[k];
                                Vector2d seg = a.Vertices[k + 1] - p0;
                                double largo = seg.Length;
                                if (largo < 1e-9) continue;
                                double t = (ext.p - p0).DotProduct(seg) / (largo * largo);
                                // Solo en el INTERIOR del tramo: junto a un vértice ya
                                // hay extremos y la juntura se arma sola.
                                if (t * largo <= tolXY || (1 - t) * largo <= tolXY) continue;
                                Point2d q = p0 + seg * t;
                                if (q.GetDistanceTo(ext.p) > tolXY) continue;
                                double zA = zaOut[k] + (zaIn[k + 1] - zaOut[k]) * t;
                                if (Math.Abs(zA - ext.z) > tolZ) continue;   // cruce, no T

                                int tramoApp = a.TramoPython != null ? a.TramoPython[k] : k;
                                InsertarVerticeConCotas(a, k, q, zA, zaOut, zaIn);
                                ed?.WriteMessage($"\n  · [JUNTURA-T] {Nombre(b)} termina a mitad de {Nombre(a)} " +
                                    $"T{tramoApp + 1} en ({q.X:F2},{q.Y:F2}), misma cota ({zA:F2} ft): " +
                                    "se parte ese tramo para unirlos con una Tee.");
                                partido = true;
                                break;
                            }
                            if (partido) break;
                        }
                        if (partido) break;
                    }
                    if (partido) break;
                }
                if (!partido) return;                          // nada más que partir
            }
        }

        // Largo mínimo de un tramo ENTRE dos codos de una red a presión: por
        // debajo no entran los dos codos sólidos (cada uno recorta el tubo) y
        // Civil 3D los dibuja montados uno sobre otro. Misma regla que
        // model_ops.tramos_cortos_entre_codos en la app (que avisa con ▲ rojo).
        internal static double LargoMinEntreCodosFt(double diametro, string unidad)
        {
            double dFt = string.Equals(unidad, "mm", StringComparison.OrdinalIgnoreCase)
                ? diametro / 304.8 : diametro / 12.0;
            return Math.Max(1.0, 3.0 * dFt);
        }

        // Dos quiebres seguidos con un tramo más corto que LargoMinEntreCodosFt
        // se reemplazan por UN solo codo: el vértice queda en la intersección de
        // las rectas de los tramos vecinos (el mismo giro total), con la cota
        // promedio de los dos. Solo redes a presión (en gravedad hay buzón).
        private static void FusionarCodosSeguidos(List<ImportPipe> pipes, Editor ed)
        {
            foreach (var ip in pipes)
            {
                if (!string.Equals(ip.NetKind, "pressure", StringComparison.OrdinalIgnoreCase)) continue;
                double lMin = LargoMinEntreCodosFt(ip.Diameter, ip.Unit);
                for (int vuelta = 0; vuelta < 100; vuelta++)
                {
                    var v = ip.Vertices;
                    int n = v?.Count ?? 0;
                    int k = -1;
                    for (int i = 1; i + 2 < n; i++)
                    {
                        double largo = v[i].GetDistanceTo(v[i + 1]);
                        if (largo >= lMin - 1e-6 || largo < 1e-9) continue;
                        if (Giro(v[i - 1], v[i], v[i + 1]) < 5.0 || Giro(v[i], v[i + 1], v[i + 2]) < 5.0) continue;
                        k = i; break;
                    }
                    if (k < 0) break;

                    double[] zOut = InterpolateZ(ip, n, ip.VertexInv);
                    double[] zIn = InterpolateZ(ip, n, ip.VertexInvIn);
                    Point2d medio = new Point2d((v[k].X + v[k + 1].X) / 2, (v[k].Y + v[k + 1].Y) / 2);
                    Point2d x = InterseccionRectas(v[k - 1], v[k], v[k + 1], v[k + 2]) ?? medio;
                    if (x.GetDistanceTo(medio) > 3 * lMin) x = medio;   // casi paralelas: no disparar el vértice
                    double z = (zOut[k] + zIn[k + 1]) / 2;
                    ed?.WriteMessage($"\n  · [CODOS] {ip.Layer} #{ip.PipeIdx}: tramo de {v[k].GetDistanceTo(v[k + 1]):F2} ft " +
                                     $"entre dos codos (< {lMin:F2} ft) → un solo codo en ({x.X:F2},{x.Y:F2}).");

                    // Reindexar todo lo que va por vértice / tramo (se quita el vértice k+1 y el tramo k).
                    Func<int, int> nuevoV = i => i <= k ? i : i - 1;
                    var vOut = new Dictionary<int, double>();
                    var vIn = new Dictionary<int, double>();
                    for (int i = 1; i < n - 1; i++)
                    {
                        if (i == k + 1) continue;
                        vOut[nuevoV(i)] = i == k ? z : zOut[i];
                        vIn[nuevoV(i)] = i == k ? z : zIn[i];
                    }
                    ip.VertexInv = vOut; ip.VertexInvIn = vIn;
                    var curvas = new Dictionary<int, double>();
                    foreach (var kv in ip.CurveRadiusByVert)
                        if (kv.Key != k + 1 || !curvas.ContainsKey(k)) curvas[nuevoV(kv.Key)] = kv.Value;
                    ip.CurveRadiusByVert = curvas;
                    ip.NoManholeVerts = new HashSet<int>(ip.NoManholeVerts.Where(i => i != k + 1).Select(nuevoV));
                    var segs = new Dictionary<int, (string fam, string size)>();
                    foreach (var kv in ip.SegOverrides)
                        if (kv.Key != k) segs[kv.Key < k ? kv.Key : kv.Key - 1] = kv.Value;
                    ip.SegOverrides = segs;
                    var tramos = ip.TramoPython ?? Enumerable.Range(0, n - 1).ToList();
                    tramos.RemoveAt(k);
                    ip.TramoPython = tramos;
                    v[k] = x;
                    v.RemoveAt(k + 1);
                }
            }
        }

        // Giro (grados) en b del camino a→b→c; 0 = sigue recto.
        private static double Giro(Point2d a, Point2d b, Point2d c)
        {
            Vector2d u = b - a, w = c - b;
            if (u.Length < 1e-9 || w.Length < 1e-9) return 0;
            return u.GetAngleTo(w) * 180.0 / Math.PI;
        }

        // Intersección de la recta a1→a2 con la recta b1→b2 (null si son paralelas).
        private static Point2d? InterseccionRectas(Point2d a1, Point2d a2, Point2d b1, Point2d b2)
        {
            Vector2d r = a2 - a1, s = b2 - b1;
            double den = r.X * s.Y - r.Y * s.X;
            if (Math.Abs(den) < 1e-9) return null;
            Vector2d q = b1 - a1;
            double t = (q.X * s.Y - q.Y * s.X) / den;
            return a1 + r * t;
        }

        // Inserta el vértice q en el tramo k de `ip` sin mover ninguna cota: se
        // escriben explícitas las cotas de TODOS los vértices interiores (las
        // calculadas antes de insertar) y el nuevo lleva zNuevo a ambos lados.
        private static void InsertarVerticeConCotas(ImportPipe ip, int k, Point2d q, double zNuevo,
            double[] zOutAntes, double[] zInAntes)
        {
            int nAntes = ip.Vertices.Count;
            ip.Vertices.Insert(k + 1, q);
            var vOut = new Dictionary<int, double>();
            var vIn = new Dictionary<int, double>();
            for (int v = 1; v < nAntes; v++)                   // interiores del nuevo (0..nAntes)
            {
                if (v == k + 1) { vOut[v] = zNuevo; vIn[v] = zNuevo; continue; }
                int vAntes = v <= k ? v : v - 1;
                vOut[v] = zOutAntes[vAntes];
                vIn[v] = zInAntes[vAntes];
            }
            ip.VertexInv = vOut;
            ip.VertexInvIn = vIn;
            var tramos = ip.TramoPython ?? Enumerable.Range(0, nAntes - 1).ToList();
            tramos.Insert(k + 1, tramos[k]);                   // las dos mitades son el mismo tramo
            ip.TramoPython = tramos;
        }

        private static double[] InterpolateZ(ImportPipe ip, int nVerts, Dictionary<int, double> vertexInv)
        {
            double zStart = ip.InvStart ?? 0.0;
            double zEnd = ip.InvEnd ?? zStart;
            if (vertexInv == null || vertexInv.Count == 0 || nVerts < 3)
                return ZalongByDistance(ip.Vertices, zStart, zEnd);

            var anchors = new SortedDictionary<int, double> { [0] = zStart, [nVerts - 1] = zEnd };
            foreach (var kv in vertexInv)
                if (kv.Key > 0 && kv.Key < nVerts - 1) anchors[kv.Key] = kv.Value;

            double[] z = new double[nVerts];
            var keys = new List<int>(anchors.Keys);
            for (int seg = 0; seg < keys.Count - 1; seg++)
            {
                int a = keys[seg], b = keys[seg + 1];
                var sub = ip.Vertices.GetRange(a, b - a + 1);
                double[] subZ = ZalongByDistance(sub, anchors[a], anchors[b]);
                for (int i = 0; i < subZ.Length; i++) z[a + i] = subZ[i];
            }
            return z;
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

        // Arco que ARRANCA en p1 tangente a la dirección (v - p1) y TERMINA en p2.
        // v es el vértice de la esquina (donde se cruzarían las dos rectas
        // extendidas): da la tangente de arranque, igual que el comando CURVA de
        // AutoCAD (inicio/final/dirección). Puerto directo de la función
        // 'ArcoTangente' de civil3d-mcp-bridge/src/Handlers.cs (ya verificada
        // funcionando ahí para el mismo caso: bancoducto con esquina curva).
        private static CircularArc3d ArcoTangente(Point3d p1, Point3d p2, Point3d v,
                                                   out double radio, out bool horario)
        {
            double cz = (p1.X - v.X) * (p2.Y - v.Y) - (p1.Y - v.Y) * (p2.X - v.X);
            horario = cz > 0;

            var tang = new Vector3d(v.X - p1.X, v.Y - p1.Y, 0.0);
            if (tang.Length < 1e-9)
                throw new InvalidOperationException("El vértice de la esquina coincide con el punto de tangencia inicial.");
            tang = tang / tang.Length;
            var n = new Vector3d(-tang.Y, tang.X, 0.0);

            var d = new Vector3d(p1.X - p2.X, p1.Y - p2.Y, 0.0);
            if (d.Length < 1e-9)
                throw new InvalidOperationException("Los dos puntos de tangencia coinciden: no hay arco posible.");

            double nd = n.X * d.X + n.Y * d.Y;
            if (Math.Abs(nd) < 1e-9)
                throw new InvalidOperationException("El tramo queda recto: no hace falta arco.");

            double t = -(d.Length * d.Length) / (2.0 * nd);
            var c = new Point3d(p1.X + t * n.X, p1.Y + t * n.Y, (p1.Z + p2.Z) / 2.0);
            radio = Math.Abs(t);

            var med = new Point3d((p1.X + p2.X) / 2.0, (p1.Y + p2.Y) / 2.0, (p1.Z + p2.Z) / 2.0);
            var hacia = new Vector3d(med.X - c.X, med.Y - c.Y, 0.0);
            if (hacia.Length < 1e-9)
                throw new InvalidOperationException("Puntos diametralmente opuestos: el arco queda indefinido.");
            hacia = hacia / hacia.Length;
            var pMed = new Point3d(c.X + radio * hacia.X, c.Y + radio * hacia.Y, (p1.Z + p2.Z) / 2.0);

            return new CircularArc3d(p1, pMed, p2);
        }

        // Ancho/diámetro interior (pies) de una familia+tamaño de tubería, para el
        // radio de respaldo (6×) cuando el usuario deja "Radio" vacío. No hay forma
        // directa de leer InnerDiameterOrWidth/InnerHeight de un PartSize del
        // catálogo sin instanciarlo — se crea una tubería descartable lejos del
        // dibujo real, se lee la propiedad del objeto creado (mismo patrón que
        // OffsetEjeARasante más abajo en este archivo) y se borra enseguida.
        private static double ResolveAnchoInterior(Transaction tr, CivilDB.Network net,
                                                    ObjectId fam, ObjectId size, Editor ed)
        {
            const double fallback = 2.0;   // si todo falla, algo razonable en vez de reventar
            try
            {
                var p1 = new Point3d(1_000_000.0, 1_000_000.0, 0.0);
                var p2 = new Point3d(1_000_000.0 + 1.0, 1_000_000.0, 0.0);
                ObjectId dummyId = ObjectId.Null;
                net.AddLinePipe(fam, size, new LineSegment3d(p1, p2), ref dummyId, false);
                var dummy = (CivilDB.Pipe)tr.GetObject(dummyId, OpenMode.ForWrite);
                double ancho = fallback;
                try
                {
                    var pInnerH = dummy.GetType().GetProperty("InnerHeight");
                    double h = pInnerH != null ? (double)pInnerH.GetValue(dummy) : 0.0;
                    ancho = h > 0.01 ? h : dummy.InnerDiameterOrWidth;
                }
                catch { try { ancho = dummy.InnerDiameterOrWidth; } catch { } }
                dummy.Erase();
                return ancho > 0.01 ? ancho : fallback;
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n⚠ No se pudo leer el ancho interior para el radio automático de la curva; se usa {fallback}'. ({ex.Message})");
                return fallback;
            }
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

        // Selecciona la Parts List de presión para una red: PREFIERE una lista
        // donde una pieza Wye REALMENTE se pueda construir (AddFitting de prueba),
        // que es la creada por el comando oficial CREATEPRESSUREPARTLISTFULL (bien
        // registrada con su catálogo). Si ninguna construye la Y, cae a "Standard"
        // (que sí construye tubos/tees, aunque sin Y). Así nunca rompe el dibujo.
        private static ObjectId SeleccionarListaPresion(
            Database db, Transaction tr, PresStyles.PressurePartListCollection plc,
            List<ImportPipe> pipes, Editor ed)
        {
            ObjectId fallback = AsegurarPresionWye.ElegirPartsListStandard(plc, tr);
            if (plc == null || plc.Count == 0) return fallback;

            // Con las Y como sólido 3D ninguna lista necesita saber construir una
            // Wye de catálogo. La prueba de abajo, además, activa el catálogo
            // Steel de forma global y, si el dibujo aún tiene una 'Full Catalog'
            // de corridas anteriores, pasaría la red a tubos/codos de acero.
            if (ComandosPresion.FITTING_COMO_SOLIDO) return fallback;

            // Solo vale la pena cambiar de lista si esta red REALMENTE lleva una
            // Y. La lista 'Full Catalog' se crea con el catálogo AWWA Steel
            // activo, así que TODAS sus piezas (tubos, tees y sobre todo los
            // CODOS) salen en acero soldado en vez de los push-on ductile iron
            // de 'Standard'. Antes se cambiaba la red entera solo porque la
            // lista sabía construir una Wye, y los codos de redes SIN ninguna Y
            // salían con la forma equivocada.
            if (!RedNecesitaWye(pipes))
            {
                var plStd = tr.GetObject(fallback, OpenMode.ForRead) as PresStyles.PressurePartList;
                ed?.WriteMessage($"\n  · [PRESION] Sin junturas Y en esta red → se mantiene '{plStd?.Name ?? "Standard"}'.");
                return fallback;
            }

            for (int i = 0; i < plc.Count; i++)
            {
                var pl = tr.GetObject(plc[i], OpenMode.ForRead) as PresStyles.PressurePartList;
                if (pl == null) continue;
                if (ProbarListaWye(db, tr, plc[i], ed))
                {
                    ed?.WriteMessage($"\n  · [PRESION] Lista '{pl.Name}' SÍ construye Wye → se usa para esta red.");
                    return plc[i];
                }
            }
            return fallback;
        }

        // ¿Alguna juntura de esta red pide una Y? Se calcula sobre la geometría
        // del DXF (antes de crear nada en el dibujo) replicando el despiece que
        // hace CrearRedPresionCompleta: un tramo por cada par de vértices
        // consecutivos de cada ImportPipe. Mismo criterio de agrupación por
        // cercanía y misma decisión Tee/Wye que ProcesarJunturasPresion.
        private static bool RedNecesitaWye(List<ImportPipe> pipes, double tol = 0.5)
        {
            if (pipes == null || pipes.Count == 0) return false;
            try
            {
                // Extremos de cada TRAMO (no de cada polilínea).
                var extremos = new List<Point2d>();
                foreach (var ip in pipes)
                {
                    var v = ip?.Vertices;
                    if (v == null || v.Count < 2) continue;
                    for (int i = 0; i < v.Count - 1; i++)
                    { extremos.Add(v[i]); extremos.Add(v[i + 1]); }
                }
                if (extremos.Count == 0) return false;

                // Agrupar por cercanía; cada grupo es un sitio físico.
                var usado = new bool[extremos.Count];
                for (int i = 0; i < extremos.Count; i++)
                {
                    if (usado[i]) continue;
                    usado[i] = true;
                    var grupo = new List<int> { i };
                    double ax = extremos[i].X, ay = extremos[i].Y;
                    for (int k = i + 1; k < extremos.Count; k++)
                    {
                        if (usado[k]) continue;
                        var c = new Point2d(ax / grupo.Count, ay / grupo.Count);
                        if (c.GetDistanceTo(extremos[k]) <= tol)
                        {
                            grupo.Add(k); usado[k] = true;
                            ax += extremos[k].X; ay += extremos[k].Y;
                        }
                    }
                    if (grupo.Count != 3) continue;

                    // Vectores de salida: del centro hacia el OTRO extremo del tramo.
                    var centro = new Point2d(ax / grupo.Count, ay / grupo.Count);
                    var vecs = new List<Vector3d>();
                    foreach (int idx in grupo)
                    {
                        Point2d lejano = (idx % 2 == 0) ? extremos[idx + 1] : extremos[idx - 1];
                        vecs.Add(new Vector3d(lejano.X - centro.X, lejano.Y - centro.Y, 0));
                    }
                    if (ComandosPresion.DecidirTeeOWye(vecs) == CivilDB.PressurePartType.Wye)
                        return true;
                }
                return false;
            }
            catch { return false; }
        }

        // ¿La lista puede construir una pieza Wye? Crea una red de prueba, intenta
        // AddFitting de una Wye y la borra. true solo si AddFitting no lanzó.
        private static bool ProbarListaWye(Database db, Transaction tr, ObjectId plId, Editor ed)
        {
            try
            {
                var pl = tr.GetObject(plId, OpenMode.ForRead) as PresStyles.PressurePartList;
                var fittings = pl?.GetParts(CivilDB.PressurePartDomainType.Fitting);
                var wye = fittings?.FirstOrDefault(f => f != null && f.PartType == CivilDB.PressurePartType.Wye);
                if (wye == null) return false;
                AsegurarPresionWye.ActivarCatalogo(ed);
                ObjectId nid = CivilDB.PressurePipeNetwork.Create(db, "PROBE_WYE_" + Guid.NewGuid().ToString("N").Substring(0, 6));
                var n = tr.GetObject(nid, OpenMode.ForWrite) as CivilDB.PressurePipeNetwork;
                n.PartsListId = plId;
                bool ok = false;
                try { n.AddFitting(new Point3d(0, 0, 0), wye); ok = true; } catch { ok = false; }
                try { n.Erase(); } catch { }
                return ok;
            }
            catch { return false; }
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
                double d = ComandosPresion.ExtraerDiametroDeDescripcion(t.Description);
                double diff = Math.Abs(d - targetDiam);
                if (diff < bestDiff) { bestDiff = diff; best = t; }
            }
            return best;
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
                if (s == "PDFCAD_PIPE" || s == "PDFCAD_STRUCT" || s == "PDFCAD_CURVE" || s == "PDFCAD_META" || s == "PDFCAD_DUCTBANK" || s == "PDFCAD_CROSS_CONNECT")
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

        // Red de Civil 3D de cada tubería. Por defecto, su NOMBRE de red (o la capa
        // si no tiene). Pero las tuberías de la MISMA utilidad (capa + tipo de red)
        // que se tocan (un extremo sobre la otra, a ≤0.5 ft) van SIEMPRE a la misma
        // red, aunque en la app tengan nombres distintos: si no, el accesorio que
        // las une no se podría crear. Esa red toma el nombre de la primera tubería
        // del grupo que tenga nombre (menor PIPE_IDX); sin nombres, la capa.
        private static Dictionary<ImportPipe, string> RedesUnidasPorContacto(List<ImportPipe> pipes)
        {
            const double TOL = 0.5;
            int n = pipes.Count;
            var padre = Enumerable.Range(0, n).ToArray();
            Func<int, int> raiz = null;
            raiz = i => padre[i] == i ? i : (padre[i] = raiz(padre[i]));

            Func<Point2d, ImportPipe, bool> tocaA = (pt, q) =>
            {
                var v = q.Vertices;
                if (v == null || v.Count == 0) return false;
                if (v.Count == 1) return pt.GetDistanceTo(v[0]) <= TOL;
                for (int k = 0; k + 1 < v.Count; k++)
                {
                    Vector2d d = v[k + 1] - v[k];
                    double L2 = d.DotProduct(d);
                    double t = L2 < 1e-12 ? 0 : Math.Max(0, Math.Min(1, (pt - v[k]).DotProduct(d) / L2));
                    if (pt.GetDistanceTo(v[k] + d * t) <= TOL) return true;
                }
                return false;
            };

            for (int a = 0; a < n; a++)
                for (int b = a + 1; b < n; b++)
                {
                    ImportPipe pa = pipes[a], pb = pipes[b];
                    if (!string.Equals(pa.Layer, pb.Layer, StringComparison.OrdinalIgnoreCase)) continue;
                    if (!string.Equals(pa.NetKind, pb.NetKind, StringComparison.OrdinalIgnoreCase)) continue;
                    if (pa.Vertices == null || pb.Vertices == null || pa.Vertices.Count == 0 || pb.Vertices.Count == 0) continue;
                    // Un extremo sobre la otra tubería (Tee/Wye/codo) o un vértice
                    // compartido (cruz). Un cruce en X a mitad de tramo no las une.
                    bool toca = tocaA(pa.Vertices[0], pb) || tocaA(pa.Vertices[pa.Vertices.Count - 1], pb)
                             || tocaA(pb.Vertices[0], pa) || tocaA(pb.Vertices[pb.Vertices.Count - 1], pa)
                             || pa.Vertices.Any(va => pb.Vertices.Any(vb => va.GetDistanceTo(vb) <= TOL));
                    if (toca) padre[raiz(a)] = raiz(b);
                }

            var nombreGrupo = new Dictionary<int, string>();
            foreach (int i in Enumerable.Range(0, n)
                         .OrderBy(i => pipes[i].PipeIdx < 0 ? int.MaxValue : pipes[i].PipeIdx).ThenBy(i => i))
            {
                int r = raiz(i);
                if (!nombreGrupo.ContainsKey(r) && !string.IsNullOrWhiteSpace(pipes[i].NetName))
                    nombreGrupo[r] = pipes[i].NetName.Trim();
            }
            var res = new Dictionary<ImportPipe, string>();
            for (int i = 0; i < n; i++)
            {
                var p = pipes[i];
                string propio = string.IsNullOrWhiteSpace(p.NetName) ? p.Layer : p.NetName.Trim();
                string key = nombreGrupo.TryGetValue(raiz(i), out var ng) ? ng : propio;
                if (!string.Equals(key, propio, StringComparison.OrdinalIgnoreCase))
                {
                    // El nombre de red se hereda del grupo para que el sólido del accesorio los una.
                    System.Diagnostics.Debug.WriteLine($"[REDES] «{propio}» (PIPE_IDX {p.PipeIdx}) toca otra tubería de {p.Layer} → red «{key}».");
                    p.NetName = key;
                }
                res[p] = key;
            }
            return res;
        }

        private static void DictAdd<T>(Dictionary<string, List<T>> dict, string key, T item)
        {
            List<T> list;
            if (!dict.TryGetValue(key, out list)) { list = new List<T>(); dict[key] = list; }
            list.Add(item);
        }

        // =================================================================
        //  DUCT BANK — sólido 3D extruido a lo largo de la pipe asignada
        // =================================================================
        // Crea, en una red de presión "CROSS-CONNECTS", un tramo vertical por
        // cada conexión aprobada entre dos utilidades que se cruzan a cotas
        // distintas, más una válvula al medio. Diámetro = el menor de las dos
        // utilidades cruzadas; familia = primer tubo de la parts list.
        private void CrearConexionesCruzadas(Editor ed, Database db, CivilDocument civilDoc,
            Transaction tr, List<ImportPipe> pipes, List<ImportCrossConnect> crossConns)
        {
            ed.WriteMessage($"\n[CROSS] Iniciando: {crossConns.Count} conexión(es) cruzada(s) aprobada(s).");

            // 1) Parts list de presión + tubos disponibles.
            PresStyles.PressurePartListCollection plc =
                PresStyles.StylesRootPressurePipesExtension.GetPressurePartLists(civilDoc.Styles);
            ed.WriteMessage($"\n[CROSS] Parts Lists de presión disponibles: {plc.Count}.");
            if (plc.Count == 0)
            {
                ed.WriteMessage("\n[CROSS] ⚠ No hay Parts Lists de presión — necesarias para crear el tramo vertical.");
                return;
            }
            ObjectId plCrossId = AsegurarPresionWye.ElegirPartsListStandard(plc, tr);
            if (plCrossId == ObjectId.Null) plCrossId = plc[0];
            PresStyles.PressurePartList pl = (PresStyles.PressurePartList)tr.GetObject(plCrossId, OpenMode.ForRead);
            var tubos = pl.GetParts(CivilDB.PressurePartDomainType.Pipe);
            var fittings = pl.GetParts(CivilDB.PressurePartDomainType.Fitting);
            int nTubos = tubos?.Count ?? 0;
            int nFittings = fittings?.Count ?? 0;
            ed.WriteMessage($"\n[CROSS] Tubos disponibles en la Parts List '{pl.Name}': {nTubos}. Fittings: {nFittings}.");
            if (nTubos == 0)
            {
                ed.WriteMessage("\n[CROSS] ⚠ Sin tubos en la Parts List de presión — no se puede crear la vertical.");
                return;
            }

            // 2) Red separada.
            ObjectId netId = CivilDB.PressurePipeNetwork.Create(db, "CROSS-CONNECTS");
            var net = (CivilDB.PressurePipeNetwork)tr.GetObject(netId, OpenMode.ForWrite);
            net.PartsListId = plCrossId;
            ed.WriteMessage($"\n[CROSS] Red 'CROSS-CONNECTS' creada (id={netId.Handle}).");

            int nOk = 0, nFail = 0, idx = 0;
            foreach (var cc in crossConns)
            {
                idx++;
                ed.WriteMessage($"\n[CROSS #{idx}] Punto ({cc.X:F2},{cc.Y:F2}), pipe_a={cc.PipeA}, pipe_b={cc.PipeB}, z_a={FmtZ(cc.ZA)}, z_b={FmtZ(cc.ZB)}.");

                if (cc.PipeA < 0 || cc.PipeA >= pipes.Count || cc.PipeB < 0 || cc.PipeB >= pipes.Count)
                {
                    ed.WriteMessage($"\n[CROSS #{idx}] ⚠ pipe_idx inválido (fuera de rango 0..{pipes.Count - 1}).");
                    nFail++; continue;
                }
                var pA = pipes[cc.PipeA]; var pB = pipes[cc.PipeB];
                ed.WriteMessage($"\n[CROSS #{idx}]   pipe_a: layer='{pA.Layer}', Ø={pA.Diameter:F1}\", NetKind='{pA.NetKind}'");
                ed.WriteMessage($"\n[CROSS #{idx}]   pipe_b: layer='{pB.Layer}', Ø={pB.Diameter:F1}\", NetKind='{pB.NetKind}'");

                double? za = cc.ZA, zb = cc.ZB;
                if (!za.HasValue || !zb.HasValue)
                {
                    ed.WriteMessage($"\n[CROSS #{idx}] ⚠ Falta cota en alguna utilidad — no se puede dibujar la vertical.");
                    nFail++; continue;
                }
                double zLo = Math.Min(za.Value, zb.Value);
                double zHi = Math.Max(za.Value, zb.Value);
                double dz = zHi - zLo;
                ed.WriteMessage($"\n[CROSS #{idx}]   Δz = {dz:F3} ft (zLo={zLo:F2}, zHi={zHi:F2}).");
                if (dz < 0.01)
                {
                    ed.WriteMessage($"\n[CROSS #{idx}] ⚠ Cotas iguales — no requiere vertical.");
                    nFail++; continue;
                }

                // 3) Elegir tubo. Diámetro objetivo = menor de las dos utilidades.
                double diamPulgA = pA.Diameter;
                double diamPulgB = pB.Diameter;
                double diamPulg = Math.Min(diamPulgA > 0 ? diamPulgA : diamPulgB,
                                           diamPulgB > 0 ? diamPulgB : diamPulgA);
                if (diamPulg <= 0) diamPulg = 4.0;
                ed.WriteMessage($"\n[CROSS #{idx}]   Buscando tubo Ø{diamPulg:F1}\" en la Parts List…");
                PresStyles.PressurePartSize tuboSel = MatchPresionTubo(tubos, diamPulg, null);
                if (tuboSel == null)
                {
                    // Fallback: primer tubo cualquiera disponible.
                    tuboSel = tubos[0];
                    ed.WriteMessage($"\n[CROSS #{idx}]   ⚠ Sin tubo del diámetro pedido — usando el primero disponible: '{tuboSel.Description}'.");
                }
                else
                {
                    ed.WriteMessage($"\n[CROSS #{idx}]   Tubo elegido: '{tuboSel.Description}'.");
                }

                // 4) Convertir invert (Z_A/Z_B) a CENTERLINE de cada tubería
                //    horizontal. Las pipes de presión se colocaron en Civil 3D
                //    con StartPoint.Z = invert + radio (ver conversión solera→eje
                //    en CrearRedPresionCompleta). Para que los Tees queden ON
                //    las utilidades hay que usar el centerline, NO la solera.
                double rA = (pA.Diameter > 0 ? pA.Diameter : diamPulg) / 24.0;   // ft
                double rB = (pB.Diameter > 0 ? pB.Diameter : diamPulg) / 24.0;
                double zACenter = za.Value + rA;
                double zBCenter = zb.Value + rB;
                double zLoCenter = Math.Min(zACenter, zBCenter);
                double zHiCenter = Math.Max(zACenter, zBCenter);
                ed.WriteMessage($"\n[CROSS #{idx}]   Centerlines: Z_lo={zLoCenter:F3} (invert {Math.Min(za.Value, zb.Value):F2}+r), Z_hi={zHiCenter:F3}.");

                // 5) Cuál pipe está arriba y cuál abajo (por su Z en el cruce).
                bool aIsUpper = za.Value > zb.Value;
                var pipeUpper = aIsUpper ? pA : pB;
                var pipeLower = aIsUpper ? pB : pA;
                Vector3d dirUpper = TangenteImportPipeEn(pipeUpper, cc.X, cc.Y);
                Vector3d dirLower = TangenteImportPipeEn(pipeLower, cc.X, cc.Y);
                ed.WriteMessage($"\n[CROSS #{idx}]   Horizontal inferior '{pipeLower.Layer}' Ø{pipeLower.Diameter:F1}\" dir=({dirLower.X:F2},{dirLower.Y:F2}).");
                ed.WriteMessage($"\n[CROSS #{idx}]   Horizontal superior '{pipeUpper.Layer}' Ø{pipeUpper.Diameter:F1}\" dir=({dirUpper.X:F2},{dirUpper.Y:F2}).");

                // 5b) Caso Wye: una utilidad PASA por el punto con un QUIEBRE
                //     (ahí ya se le puso su codo) y la otra TERMINA en él. Un Tee
                //     recto no encaja en un tronco quebrado: diseño del modelador
                //     = Wye en el quiebre + tubo auxiliar de 1 ft + codo + vertical
                //     + codo hacia la otra utilidad. Si no es este caso (tronco
                //     recto, o ambas terminan/pasan) sigue el flujo de siempre.
                if (ComandosPresion.FITTING_COMO_SOLIDO)
                {
                    bool loTermina = EsExtremoDePipe(pipeLower, cc.X, cc.Y);
                    bool hiTermina = EsExtremoDePipe(pipeUpper, cc.X, cc.Y);
                    if (loTermina != hiTermina)
                    {
                        bool pasaEsSuperior = !hiTermina;
                        double zPasa = pasaEsSuperior ? zHiCenter : zLoCenter;
                        double zTermina = pasaEsSuperior ? zLoCenter : zHiCenter;
                        var codoQuiebre = WyeSolido.BuscarCreada("ELBOW",
                            new Point3d(cc.X, cc.Y, zPasa), 0.5, 0.35);
                        if (codoQuiebre != null)
                        {
                            ed.WriteMessage($"\n[CROSS #{idx}]   La utilidad {(pasaEsSuperior ? "superior" : "inferior")} " +
                                "tiene un QUIEBRE aquí (codo ya colocado) y la otra termina → Wye + tubo auxiliar de " +
                                $"{TUBO_AUX_CRUCE_FT:F2} ft + codos + vertical.");
                            bool ok = CrearCruceConWye(ed, tr, civilDoc, net, tuboSel, diamPulg,
                                codoQuiebre, new Point3d(cc.X, cc.Y, zPasa), zTermina, idx);
                            if (ok) nOk++; else nFail++;
                            continue;
                        }
                    }
                }

                // 6) Elegir accesorio POR CADA EXTREMO. Regla:
                //    - Si la utilidad TERMINA en el punto de cruce (endpoint) →
                //      usar CODO (elbow) 90°: 2 puertos, uno horizontal y uno
                //      vertical. Un Tee ahí dejaría un trunk suelto feo.
                //    - Si la utilidad PASA A TRAVÉS del cruce (punto en medio
                //      de un segmento o vértice intermedio) → usar TEE: 2
                //      puertos trunk (la utilidad continúa) + branch vertical.
                bool loIsEndpoint = EsExtremoDePipe(pipeLower, cc.X, cc.Y);
                bool hiIsEndpoint = EsExtremoDePipe(pipeUpper, cc.X, cc.Y);
                ed.WriteMessage($"\n[CROSS #{idx}]   Inferior termina en el cruce: {loIsEndpoint} → {(loIsEndpoint ? "CODO" : "TEE")}. Superior: {hiIsEndpoint} → {(hiIsEndpoint ? "CODO" : "TEE")}.");
                // Si la utilidad TERMINA en el cruce, el codo se orienta con
                // la dirección "desde el cruce hacia el resto del pipe"
                // (opuesta a la tangente natural cuando el endpoint es el END).
                if (loIsEndpoint) dirLower = DireccionAlejandoseDelCruce(pipeLower, cc.X, cc.Y);
                if (hiIsEndpoint) dirUpper = DireccionAlejandoseDelCruce(pipeUpper, cc.X, cc.Y);
                ed.WriteMessage($"\n[CROSS #{idx}]   Dir efectiva inferior=({dirLower.X:F2},{dirLower.Y:F2}), superior=({dirUpper.X:F2},{dirUpper.Y:F2}).");

                PresStyles.PressurePartSize partLo = null, partHi = null;
                CivilDB.PressurePartType tipoLo = CivilDB.PressurePartType.Tee;
                CivilDB.PressurePartType tipoHi = CivilDB.PressurePartType.Tee;
                // Diámetro de cada utilidad horizontal (tronco de su pieza). El
                // ramal que va a la vertical es del diámetro de la vertical.
                double trunkLoIn = pipeLower.Diameter > 0 ? pipeLower.Diameter : diamPulg;
                double trunkHiIn = pipeUpper.Diameter > 0 ? pipeUpper.Diameter : diamPulg;
                if (nFittings > 0)
                {
                    if (loIsEndpoint)
                    {
                        tipoLo = CivilDB.PressurePartType.Elbow;
                        partLo = ComandosPresion.BuscarFittingPorTipoYDiametro(
                            fittings, CivilDB.PressurePartType.Elbow, trunkLoIn, 90.0);
                    }
                    else
                    {
                        partLo = ComandosPresion.BuscarTeePorTrunkYBranch(fittings, trunkLoIn, diamPulg);
                    }
                    if (hiIsEndpoint)
                    {
                        tipoHi = CivilDB.PressurePartType.Elbow;
                        partHi = ComandosPresion.BuscarFittingPorTipoYDiametro(
                            fittings, CivilDB.PressurePartType.Elbow, trunkHiIn, 90.0);
                    }
                    else
                    {
                        partHi = ComandosPresion.BuscarTeePorTrunkYBranch(fittings, trunkHiIn, diamPulg);
                    }
                    ed.WriteMessage($"\n[CROSS #{idx}]   Inferior ({tipoLo}) trunk≈{trunkLoIn:F1}\": '{(partLo != null ? partLo.Description : "(no encontrado)")}'.");
                    ed.WriteMessage($"\n[CROSS #{idx}]   Superior ({tipoHi}) trunk≈{trunkHiIn:F1}\": '{(partHi != null ? partHi.Description : "(no encontrado)")}'.");
                }
                else
                {
                    ed.WriteMessage($"\n[CROSS #{idx}]   ⚠ Parts List sin Fittings — se dibujará solo la vertical.");
                }

                try
                {
                    // 7) Colocar Tees primero, cada uno con su propio Part.
                    //    Se retornan las posiciones REALES donde quedaron los
                    //    puertos branch — la vertical va entre esos dos puntos.
                    ObjectId teeLoId = ObjectId.Null, teeHiId = ObjectId.Null;
                    int teeLoBranchPort = -1, teeHiBranchPort = -1;
                    double alcanceLo = 0, alcanceHi = 0;
                    Point3d pLoBranch = new Point3d(cc.X, cc.Y, zLoCenter);
                    Point3d pHiBranch = new Point3d(cc.X, cc.Y, zHiCenter);
                    if (partLo != null)
                    {
                        var resLo = ColocarFittingYOrientar(ed, tr, net, partLo, tipoLo,
                            cc.X, cc.Y, zLoCenter, dirLower, branchArriba: true,
                            etiqueta: $"[CROSS #{idx}] inferior",
                            diamTroncoIn: trunkLoIn, diamRamalIn: diamPulg, out alcanceLo);
                        if (resLo.HasValue)
                        {
                            teeLoId = resLo.Value.teeId;
                            teeLoBranchPort = resLo.Value.branchPort;
                            pLoBranch = resLo.Value.branchWorldPos;
                        }
                    }
                    if (partHi != null)
                    {
                        var resHi = ColocarFittingYOrientar(ed, tr, net, partHi, tipoHi,
                            cc.X, cc.Y, zHiCenter, dirUpper, branchArriba: false,
                            etiqueta: $"[CROSS #{idx}] superior",
                            diamTroncoIn: trunkHiIn, diamRamalIn: diamPulg, out alcanceHi);
                        if (resHi.HasValue)
                        {
                            teeHiId = resHi.Value.teeId;
                            teeHiBranchPort = resHi.Value.branchPort;
                            pHiBranch = resHi.Value.branchWorldPos;
                        }
                    }

                    // 8) Dibujar la vertical entre los puertos branch (o
                    //    entre los centerlines si no había Tees).
                    if (pLoBranch.Z >= pHiBranch.Z)
                    {
                        ed.WriteMessage($"\n[CROSS #{idx}]   ⚠ Puertos branch cruzados o iguales (Lo.Z={pLoBranch.Z:F3}, Hi.Z={pHiBranch.Z:F3}) — ajusto a centerlines.");
                        pLoBranch = new Point3d(cc.X, cc.Y, zLoCenter);
                        pHiBranch = new Point3d(cc.X, cc.Y, zHiCenter);
                    }
                    ObjectId vertId = net.AddLinePipe(new LineSegment3d(pLoBranch, pHiBranch), tuboSel);
                    ed.WriteMessage($"\n[CROSS #{idx}] ✓ Vertical de Z {pLoBranch.Z:F3} → {pHiBranch.Z:F3} (handle={vertId.Handle}).");

                    // Re-fijar endpoints (por si AddLinePipe los recortó).
                    try
                    {
                        var pp = (CivilDB.PressurePipe)tr.GetObject(vertId, OpenMode.ForWrite);
                        pp.StartPoint = pLoBranch;
                        pp.EndPoint = pHiBranch;
                    }
                    catch { }

                    // 9) Conectar cada Tee (por su puerto branch) al extremo
                    //    correspondiente de la vertical.
                    if (teeLoId != ObjectId.Null && teeLoBranchPort >= 0)
                    {
                        try
                        {
                            var parte = (CivilDB.PressurePart)tr.GetObject(teeLoId, OpenMode.ForWrite);
                            parte.ConnectToPipe(teeLoBranchPort, vertId, 0);
                            ed.WriteMessage($"\n[CROSS #{idx}]   Tee inferior conectada a vertical (port {teeLoBranchPort}).");
                        }
                        catch (Exception exC) { ed.WriteMessage($"\n[CROSS #{idx}]   ⚠ ConnectToPipe inferior: {exC.Message}"); }
                    }
                    if (teeHiId != ObjectId.Null && teeHiBranchPort >= 0)
                    {
                        try
                        {
                            var parte = (CivilDB.PressurePart)tr.GetObject(teeHiId, OpenMode.ForWrite);
                            parte.ConnectToPipe(teeHiBranchPort, vertId, 1);
                            ed.WriteMessage($"\n[CROSS #{idx}]   Tee superior conectada a vertical (port {teeHiBranchPort}).");
                        }
                        catch (Exception exC) { ed.WriteMessage($"\n[CROSS #{idx}]   ⚠ ConnectToPipe superior: {exC.Message}"); }
                    }

                    // 10) Para los TEEs (pipe pasa a través del cruce) hay que
                    //     PARTIR el pipe original en dos mitades en el cruce,
                    //     porque un Tee mid-pipe no puede insertar por sí solo
                    //     un accesorio a mitad de un segmento existente.
                    //     Los codos (endpoint) no requieren split — el pipe ya
                    //     TERMINA en el cruce.
                    if (teeLoId != ObjectId.Null && !loIsEndpoint)
                        PartirPipeThroughEnCruce(ed, tr, civilDoc, net, tuboSel,
                            cc.X, cc.Y, zLoCenter, $"[CROSS #{idx}] inferior");
                    if (teeHiId != ObjectId.Null && !hiIsEndpoint)
                        PartirPipeThroughEnCruce(ed, tr, civilDoc, net, tuboSel,
                            cc.X, cc.Y, zHiCenter, $"[CROSS #{idx}] superior");

                    // 11) Conectar los puertos HORIZONTALES de cada accesorio al
                    //     pipe horizontal existente y RECORTAR su endpoint a
                    //     la posición del puerto — sin esto, el pipe horizontal
                    //     pasa a través del codo/Tee y se ve superpuesto en 3D.
                    // branchPort < 0 ⇒ la pieza es un Solid3d (no tiene puertos
                    // que leer), así que el recorte se hace por geometría.
                    if (teeLoId != ObjectId.Null)
                    {
                        if (teeLoBranchPort < 0)
                            RecortarHorizontalesASolido(ed, tr, civilDoc, alcanceLo,
                                cc.X, cc.Y, zLoCenter, $"[CROSS #{idx}] inferior");
                        else
                            ConectarHorizontalAFitting(ed, tr, civilDoc, teeLoId, teeLoBranchPort,
                                cc.X, cc.Y, zLoCenter, $"[CROSS #{idx}] inferior");
                    }
                    if (teeHiId != ObjectId.Null)
                    {
                        if (teeHiBranchPort < 0)
                            RecortarHorizontalesASolido(ed, tr, civilDoc, alcanceHi,
                                cc.X, cc.Y, zHiCenter, $"[CROSS #{idx}] superior");
                        else
                            ConectarHorizontalAFitting(ed, tr, civilDoc, teeHiId, teeHiBranchPort,
                                cc.X, cc.Y, zHiCenter, $"[CROSS #{idx}] superior");
                    }
                    nOk++;
                }
                catch (Exception exP)
                {
                    ed.WriteMessage($"\n[CROSS #{idx}] ✗ Excepción {exP.GetType().Name} al crear cruce: {exP.Message}");
                    nFail++;
                }
            }
            ed.WriteMessage($"\n[CROSS] RESUMEN: {nOk} vertical(es) creada(s), {nFail} con error.");
        }

        private static string FmtZ(double? z) => z.HasValue ? z.Value.ToString("F2") : "(null)";

        // Cuando un cruce usa Tee (el pipe PASA A TRAVÉS del punto, no
        // termina), hay que partir el pipe original en dos mitades en el
        // cruce: half1 = originalStart → crossPos, half2 = crossPos → original
        // End. Sin esto, el pipe atraviesa el Tee mid-body y se ve superpuesto.
        // Requisitos: la pipe debe pasar a ≤ 1.5 ft del cruce Y ninguno de
        // sus endpoints debe estar dentro de esa tolerancia (endpoint = codo,
        // no aplica). Copia el mismo PartSize del original en las mitades.
        private static void PartirPipeThroughEnCruce(Editor ed, Transaction tr,
            CivilDocument civilDoc, CivilDB.PressurePipeNetwork netCross,
            PresStyles.PressurePartSize tuboFallback,
            double xCross, double yCross, double zCenter, string etiqueta)
        {
            double tol = 1.5;   // ft
            double tol2 = tol * tol;
            Point3d cross = new Point3d(xCross, yCross, zCenter);
            var candidatos = new List<(ObjectId netId, ObjectId pid, Point3d closest, double dist2)>();
            foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
            {
                var n2 = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                if (n2 == null || n2.Name == "CROSS-CONNECTS") continue;
                foreach (ObjectId pid in n2.GetPipeIds())
                {
                    var pp = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                    if (pp == null) continue;
                    Point3d A = pp.StartPoint, B = pp.EndPoint;
                    // Endpoints cercanos = caso ELBOW, no aplica split.
                    if ((A - cross).LengthSqrd < tol2 || (B - cross).LengthSqrd < tol2) continue;
                    // Proyectar cross sobre el segmento AB.
                    Vector3d ab = B - A;
                    double abLen2 = ab.LengthSqrd;
                    if (abLen2 < 1e-9) continue;
                    double t = ((cross - A).DotProduct(ab)) / abLen2;
                    if (t < 0.05 || t > 0.95) continue;   // fuera del interior real
                    Point3d proj = A + ab * t;
                    double d2 = (proj - cross).LengthSqrd;
                    if (d2 > tol2) continue;
                    candidatos.Add((nid, pid, proj, d2));
                }
            }
            if (candidatos.Count == 0)
            {
                ed.WriteMessage($"\n{etiqueta}: sin pipe through-pasando por ({xCross:F2},{yCross:F2}) a tol {tol:F1}ft — no hay que partir.");
                return;
            }
            // Puede haber varias pipes solapadas (raro); partir todas.
            foreach (var c in candidatos.OrderBy(x => x.dist2))
            {
                var pp = tr.GetObject(c.pid, OpenMode.ForWrite) as CivilDB.PressurePipe;
                if (pp == null) continue;
                Point3d A = pp.StartPoint, B = pp.EndPoint;
                // Elegir PressurePartSize del original si podemos localizarlo
                // por Description; si no, cae al tuboFallback (el de la vertical).
                PresStyles.PressurePartSize tubo = tuboFallback;
                try
                {
                    var netOrig = tr.GetObject(c.netId, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                    if (netOrig != null && netOrig.PartsListId != ObjectId.Null)
                    {
                        var plOrig = tr.GetObject(netOrig.PartsListId, OpenMode.ForRead) as PresStyles.PressurePartList;
                        if (plOrig != null)
                        {
                            var tubosOrig = plOrig.GetParts(CivilDB.PressurePartDomainType.Pipe);
                            var match = tubosOrig?.FirstOrDefault(t =>
                                string.Equals(t.Description, pp.PartDescription, StringComparison.OrdinalIgnoreCase));
                            if (match != null) tubo = match;
                        }
                    }
                }
                catch { }
                var netTarget = tr.GetObject(c.netId, OpenMode.ForWrite) as CivilDB.PressurePipeNetwork;
                if (netTarget == null) netTarget = netCross;
                try
                {
                    ObjectId h1 = netTarget.AddLinePipe(new LineSegment3d(A, c.closest), tubo);
                    ObjectId h2 = netTarget.AddLinePipe(new LineSegment3d(c.closest, B), tubo);
                    pp.Erase();
                    ed.WriteMessage($"\n{etiqueta}: pipe through partida en ({c.closest.X:F2},{c.closest.Y:F2},{c.closest.Z:F3}) → half1={h1.Handle}, half2={h2.Handle}.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n{etiqueta}: ⚠ No se pudo partir pipe (handle={c.pid.Handle}): {ex.Message}");
                }
            }
        }

        // Post-paso al colocar codo/Tee del cruce: para cada puerto HORIZONTAL
        // del accesorio (todos los que no son el branch vertical), busca en
        // TODAS las redes de presión del dibujo la PressurePipe cuyo endpoint
        // cae más cerca de la posición del puerto y la conecta+recorta.
        // Sin esto, el pipe horizontal pasa a través del accesorio y en 3D
        // aparece superpuesto con el codo (el bug reportado).
        //
        // Radio de búsqueda: 1.5× el diámetro del accesorio (o 1.5 ft de piso).
        // El endpoint puede estar levemente desalineado por transformaciones,
        // pero nunca lejos — usamos el más cercano dentro del radio.
        private static void ConectarHorizontalAFitting(Editor ed, Transaction tr,
            CivilDocument civilDoc, ObjectId fittingId, int branchPort,
            double xCross, double yCross, double zCenter, string etiqueta)
        {
            try
            {
                var parte = (CivilDB.PressurePart)tr.GetObject(fittingId, OpenMode.ForWrite);
                // Radio de búsqueda: 1.5 ft de piso, o 1.5× el mayor Nominal-
                // Diameter de cualquier pipe ya conectada al accesorio (si la
                // hay). Suficiente para el desalineo típico tras rotar+inclinar.
                double diamFt = 0.0;
                for (int p = 0; p < parte.ConnectionCount; p++)
                {
                    try
                    {
                        var cx = parte.GetConnectionAt(p);
                        if (cx.ConnectedId != ObjectId.Null && cx.ConnectedId.IsValid)
                        {
                            var pp0 = tr.GetObject(cx.ConnectedId, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (pp0 != null && pp0.NominalDiameter > diamFt) diamFt = pp0.NominalDiameter;
                        }
                    }
                    catch { }
                }
                // Tolerancia bastante amplia: 3 ft de piso + 3× el diámetro más
                // grande de las pipes ya conectadas. La antigua (1.5 ft) dejaba
                // fuera de rango pipes que estaban a ~1.8 ft del puerto tras
                // aplicar rotación+tilt al fitting, sobre todo en cruces de
                // Ø14" donde el offset del puerto es alto.
                double tolFt = Math.Max(3.0, 3.0 * (diamFt > 0 ? diamFt : 1.0));
                double tol2 = tolFt * tolFt;

                for (int port = 0; port < parte.ConnectionCount; port++)
                {
                    if (port == branchPort) continue;   // el branch ya fue conectado a la vertical
                    CivilDB.PressurePartConnection conn;
                    try { conn = parte.GetConnectionAt(port); } catch { continue; }
                    if (conn.ConnectedId != ObjectId.Null && conn.ConnectedId.IsValid)
                    {
                        // Ya está conectado a algo — no lo toco.
                        continue;
                    }
                    Point3d portPos = conn.Position;
                    ed.WriteMessage($"\n{etiqueta}: port {port} horizontal en ({portPos.X:F2},{portPos.Y:F2},{portPos.Z:F3}) — buscando pipe cercano (tol={tolFt:F2}ft)…");

                    // Buscar la PressurePipe más cercana entre todas las redes,
                    // rompiendo empates con la DIRECCIÓN del puerto (pipes cuya
                    // dirección desde el endpoint hacia el OTRO extremo se
                    // alinea con la dirección de salida del puerto ganan).
                    // Sin este desempate, tras un split ambos halves quedan con
                    // endpoints AT el mismo punto y podríamos elegir el que
                    // apunta hacia dentro del fitting.
                    Vector3d portDir = conn.Direction;
                    try { portDir = portDir.GetNormal(); } catch { }
                    ObjectId bestPid = ObjectId.Null;
                    int bestEnd = 0;
                    double bestScore = double.NegativeInfinity;
                    foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
                    {
                        var n2 = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (n2 == null) continue;
                        // Saltar la red CROSS-CONNECTS: sus pipes son las
                        // verticales recién creadas, no las horizontales que
                        // quiero recortar.
                        if (n2.Name == "CROSS-CONNECTS") continue;
                        foreach (ObjectId pid in n2.GetPipeIds())
                        {
                            if (pid == fittingId) continue;
                            var pp = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (pp == null) continue;
                            void Evaluar(int endIdx, Point3d thisEnd, Point3d otherEnd)
                            {
                                double d2 = (thisEnd - portPos).LengthSqrd;
                                if (d2 > tol2) return;
                                // Direccion de la pipe SALIENDO desde thisEnd
                                // (hacia otherEnd). Si portDir · pipeDir > 0,
                                // el pipe se aleja del fitting por este puerto.
                                Vector3d pipeDir = otherEnd - thisEnd;
                                double L = pipeDir.Length;
                                if (L > 1e-9) pipeDir = pipeDir / L;
                                double align = portDir.DotProduct(pipeDir);
                                double dist = Math.Sqrt(d2);
                                // Score: cerca es mejor, alineación positiva es mejor.
                                // Un pipe a 0.1 ft mal alineado (-1) vale menos que
                                // un pipe a 0.5 ft bien alineado (+1).
                                double score = (tolFt - dist) * 2.0 + align;
                                if (score > bestScore)
                                { bestScore = score; bestPid = pid; bestEnd = endIdx; }
                            }
                            Evaluar(0, pp.StartPoint, pp.EndPoint);
                            Evaluar(1, pp.EndPoint, pp.StartPoint);
                        }
                    }
                    if (bestPid == ObjectId.Null)
                    {
                        ed.WriteMessage($"\n{etiqueta}:   ⚠ Ningún pipe horizontal a ≤{tolFt:F2}ft del puerto {port} — no se recorta.");
                        continue;
                    }
                    ed.WriteMessage($"\n{etiqueta}:   Pipe encontrada (handle={bestPid.Handle}) endpoint={bestEnd} score={bestScore:F2}. Conectando+recortando…");
                    // Intento 1: ConnectToPipe (conexión LÓGICA + trim). Falla
                    // con "A pipe from the same network is expected" cuando el
                    // fitting vive en la red CROSS-CONNECTS y el pipe está en
                    // AGUA/GAS/etc. (redes distintas).
                    bool conectadoLogico = false;
                    try
                    {
                        parte.ConnectToPipe(port, bestPid, bestEnd);
                        conectadoLogico = true;
                        var newConn = parte.GetConnectionAt(port);
                        var ppw = (CivilDB.PressurePipe)tr.GetObject(bestPid, OpenMode.ForWrite);
                        if (bestEnd == 0) ppw.StartPoint = newConn.Position;
                        else ppw.EndPoint = newConn.Position;
                        ed.WriteMessage($"\n{etiqueta}:   ✓ Conectado+recortado a ({newConn.Position.X:F2},{newConn.Position.Y:F2},{newConn.Position.Z:F3}).");
                    }
                    catch (Exception ex)
                    {
                        ed.WriteMessage($"\n{etiqueta}:   ConnectToPipe falló ({ex.Message}) — probando SOLO recorte geométrico.");
                    }
                    // Intento 2 (fallback si el 1 falló): recortar SOLO la
                    // geometría del pipe hasta la posición del puerto. Sin
                    // conexión lógica pero el pipe deja de superponerse con el
                    // fitting en el modelo 3D — que es lo que el usuario ve.
                    if (!conectadoLogico)
                    {
                        try
                        {
                            var ppw = (CivilDB.PressurePipe)tr.GetObject(bestPid, OpenMode.ForWrite);
                            if (bestEnd == 0) ppw.StartPoint = portPos;
                            else ppw.EndPoint = portPos;
                            ed.WriteMessage($"\n{etiqueta}:   ✓ Recorte geométrico (sin conexión lógica cross-red) a ({portPos.X:F2},{portPos.Y:F2},{portPos.Z:F3}).");
                        }
                        catch (Exception ex2)
                        {
                            ed.WriteMessage($"\n{etiqueta}:   ⚠ Recorte geométrico también falló: {ex2.Message}");
                        }
                    }
                }
            }
            catch (Exception exOut)
            {
                ed.WriteMessage($"\n{etiqueta}: ⚠ ConectarHorizontalAFitting: {exOut.Message}");
            }
        }

        // Identifica cuál de los N puertos de un fitting es el "branch"
        // (perpendicular a los otros dos, que son colineales entre sí).
        // Devuelve -1 si no se puede determinar. Para un Tee, los dos trunk
        // están anti-paralelos (dot ≈ -1) y el branch queda perpendicular
        // a ambos (dot ≈ 0). Se busca el puerto que MENOS se parezca a los
        // otros — típicamente el que tiene el mayor cross-product con ellos.
        private static int IdentificarBranchPortPorGeometria(CivilDB.PressurePart parte)
        {
            int n = parte.ConnectionCount;
            // Para un Codo (2 puertos), cualquiera puede ser "branch" (el que
            // conectaremos a la vertical). Por convención tomamos port 1 y
            // dejamos que port 0 sea el que se alinee con la horizontal.
            if (n == 2) return 1;
            if (n != 3) return -1;
            var dirs = new Vector3d[n];
            for (int i = 0; i < n; i++)
                dirs[i] = parte.GetConnectionAt(i).Direction;
            // Para cada puerto candidato "branch", los otros dos deben ser
            // anti-paralelos entre sí (|dot| ≈ 1). El branch es aquel que
            // maximiza la anti-paralelidad de los otros dos.
            int mejor = -1; double mejorScore = -1.0;
            for (int i = 0; i < n; i++)
            {
                int j = (i + 1) % n, k = (i + 2) % n;
                double dot = Math.Abs(dirs[j].DotProduct(dirs[k]));   // ≈ 1 si son colineales
                if (dot > mejorScore) { mejorScore = dot; mejor = i; }
            }
            return mejor;
        }

        // ¿El punto (x,y) coincide con un ENDPOINT (start o end) de la pipe?
        // Se usa para decidir si en el cruce hay un Tee (pipe pasa a través)
        // o un Codo (pipe termina ahí). Tolerancia 0.5 ft (mismo criterio
        // que AgruparJunturas de presión).
        private static bool EsExtremoDePipe(ImportPipe ip, double x, double y, double tol = 0.5)
        {
            if (ip?.Vertices == null || ip.Vertices.Count < 2) return false;
            var v0 = ip.Vertices[0];
            var vN = ip.Vertices[ip.Vertices.Count - 1];
            double dx0 = v0.X - x, dy0 = v0.Y - y;
            double dxN = vN.X - x, dyN = vN.Y - y;
            double tol2 = tol * tol;
            return (dx0 * dx0 + dy0 * dy0 <= tol2) || (dxN * dxN + dyN * dyN <= tol2);
        }

        // Dirección "alejándose del cruce" en un endpoint: si el cruce coincide
        // con el START (Vertices[0]) devuelve la tangente hacia Vertices[1];
        // si coincide con el END (Vertices[N-1]) devuelve el vector hacia
        // Vertices[N-2] (opuesto a la tangente natural). Se usa para orientar
        // un codo cuyo puerto horizontal debe apuntar por donde la utilidad
        // se aleja del cruce. Si el punto NO es endpoint, cae al tangente
        // normal (TangenteImportPipeEn).
        private static Vector3d DireccionAlejandoseDelCruce(ImportPipe ip, double x, double y, double tol = 0.5)
        {
            if (ip?.Vertices == null || ip.Vertices.Count < 2)
                return TangenteImportPipeEn(ip, x, y);
            var v0 = ip.Vertices[0];
            var vN = ip.Vertices[ip.Vertices.Count - 1];
            double tol2 = tol * tol;
            if ((v0.X - x) * (v0.X - x) + (v0.Y - y) * (v0.Y - y) <= tol2)
            {
                var v1 = ip.Vertices[1];
                var d = new Vector3d(v1.X - v0.X, v1.Y - v0.Y, 0);
                return d.Length > 1e-9 ? d.GetNormal() : Vector3d.XAxis;
            }
            if ((vN.X - x) * (vN.X - x) + (vN.Y - y) * (vN.Y - y) <= tol2)
            {
                var vPrev = ip.Vertices[ip.Vertices.Count - 2];
                var d = new Vector3d(vPrev.X - vN.X, vPrev.Y - vN.Y, 0);
                return d.Length > 1e-9 ? d.GetNormal() : Vector3d.XAxis;
            }
            // No es endpoint — usa la tangente normal.
            return TangenteImportPipeEn(ip, x, y);
        }

        // Largo EXACTO del tubo auxiliar entre la boca libre de la Wye y la boca
        // del codo que baja/sube a la otra utilidad (diseño del modelador).
        private const double TUBO_AUX_CRUCE_FT = 1.0;

        // Conexión vertical en un QUIEBRE: la utilidad que pasa tiene un codo en
        // el punto y la otra termina ahí. Recorrido (sólidos + tubos):
        //
        //   quiebre ─[Wye]─ tubo aux 1 ft (hacia la otra) ─[codo 90°]
        //                                                     │ vertical
        //                            otra utilidad ─────────[codo 90°]
        //
        // La boca libre de la Wye apunta EN PLANTA hacia la otra utilidad: la
        // vertical cae justo sobre su eje y el codo de abajo solo la gira hacia
        // ella, que se recorta contra él. El codo del quiebre se reemplaza por
        // la Wye, que sujeta los MISMOS tubos.
        private static bool CrearCruceConWye(Editor ed, Transaction tr, CivilDocument civilDoc,
            CivilDB.PressurePipeNetwork net, PresStyles.PressurePartSize tuboSel, double diamPulg,
            WyeSolido.Registro codo, Point3d cruce, double zTermina, int idx)
        {
            string tag = $"[CROSS #{idx}]";
            Database db = net.Database;
            try
            {
                // 1) Tubo de la utilidad que TERMINA: quedó suelto en el cruce
                //    porque a distinta cota no se une con la otra.
                var (eId, ePort) = BuscarExtremoPresionEn(tr, civilDoc, cruce.X, cruce.Y, zTermina);
                if (eId == ObjectId.Null)
                {
                    ed.WriteMessage($"\n{tag}   ⚠ No encontré el tubo de la utilidad que termina en el cruce " +
                        $"(eje Z≈{zTermina:F2}) — no se crea la conexión.");
                    return false;
                }
                var eTubo = (CivilDB.PressurePipe)tr.GetObject(eId, OpenMode.ForRead);
                Point3d eCerca = ePort == 0 ? eTubo.StartPoint : eTubo.EndPoint;
                Point3d eLejos = ePort == 0 ? eTubo.EndPoint : eTubo.StartPoint;
                Vector3d dE = new Vector3d(eLejos.X - eCerca.X, eLejos.Y - eCerca.Y, 0);
                if (dE.Length < 1e-6) return false;
                dE = dE.GetNormal();                          // en planta, hacia la otra utilidad
                Vector3d dE3 = (eLejos - eCerca).GetNormal(); // su eje real (puede tener pendiente)
                double dAux = diamPulg / 12.0;
                double dOtra = eTubo.NominalDiameter;         // ya viene en pies
                Point3d cT = codo.Centro;
                var codo90 = WyeSolido.BrazoDeCodo(dAux, Math.PI / 2.0);

                // 2) ¿Caben dos codos de 90° en el desnivel? Se comprueba ANTES
                //    de tocar el dibujo.
                double dzAprox = eCerca.Z - cT.Z;
                double minDz = 2.0 * codo90.BocaFt + 0.05;
                bool inclinada = Math.Abs(dzAprox) < minDz;
                if (inclinada)
                    ed.WriteMessage($"\n{tag}   ⚠ Desnivel de {Math.Abs(dzAprox):F2} ft: no caben dos codos de 90° " +
                        $"(mínimo {minDz:F2} ft) → Wye con ramal inclinado y la tubería que termina con pendiente.");

                // Red y material: los del codo que se reemplaza (su XDATA).
                string red = "", mat = tuboSel?.Description ?? "";
                try
                {
                    var xd = WyeSolido.LeerXData(tr.GetObject(codo.SolidId, OpenMode.ForRead) as Entity);
                    red = xd?.FirstOrDefault(s => s.StartsWith("RED="))?.Substring(4) ?? "";
                    string m = xd?.FirstOrDefault(s => s.StartsWith("MATERIAL="));
                    if (m != null) mat = m.Substring(9);
                }
                catch { }

                // 3) Wye en el quiebre: los brazos del codo (mismos tubos, que se
                //    re-recortan contra la Wye) + el ramal hacia la otra utilidad.
                // Desnivel chico: la tubería que termina sube/baja hasta el centro
                // de la Wye (su extremo cercano pasa a la cota del quiebre, el lejano
                // no se mueve → queda con pendiente) y entra DIRECTO al ramal, que
                // se orienta en 3D sobre su eje. Sin tubo auxiliar, codos ni vertical.
                if (inclinada)
                {
                    var eW = (CivilDB.PressurePipe)tr.GetObject(eId, OpenMode.ForWrite);
                    if (ePort == 0) eW.StartPoint = cT; else eW.EndPoint = cT;
                    Vector3d dInc = eLejos - cT;
                    if (dInc.Length < 1e-6) return false;
                    dInc = dInc.GetNormal();
                    double pendiente = Math.Abs(eLejos.Z - cT.Z) /
                        Math.Max(1e-6, new Vector2d(eLejos.X - cT.X, eLejos.Y - cT.Y).Length);
                    var ramalInc = new WyeSolido.Brazo { Direccion = dInc, DiamFt = dOtra, PipeId = eId, Port = ePort };
                    var brazosInc = codo.Brazos.Select(b => b.Copia()).ToList();
                    foreach (var b in brazosInc) b.EngroseFt = WyeSolido.ENGROSE_TRONCO_Y_FT;
                    brazosInc.Add(ramalInc);
                    double angInc = ComandosPresion.AnguloRamalDeTres(brazosInc.Select(b => b.Direccion).ToList());
                    var infoInc = new WyeSolido.Info
                    {
                        Tipo = "WYE", AnguloDeg = angInc,
                        DiamPrincipalIn = brazosInc.Max(b => b.DiamFt) * 12.0, DiamRamalIn = dOtra * 12.0,
                        Material = mat, Red = red,
                    };
                    if (WyeSolido.Crear(db, tr, cT, brazosInc, infoInc, ed) == ObjectId.Null)
                    {
                        ed.WriteMessage($"\n{tag}   ⚠ No se pudo generar la Wye inclinada — se deja el codo del quiebre.");
                        return false;
                    }
                    try { (tr.GetObject(codo.SolidId, OpenMode.ForWrite) as Entity)?.Erase(); } catch { }
                    WyeSolido.Creadas.Remove(codo);
                    ed.WriteMessage($"\n{tag}   · Codo del quiebre reemplazado por Wye con ramal inclinado ({angInc:F0}°); " +
                        $"la tubería que termina baja de Z {cT.Z:F2} a {eLejos.Z:F2} (pendiente {pendiente * 100:F1} %).");
                    return true;
                }

                var ramal = new WyeSolido.Brazo { Direccion = dE, DiamFt = dAux };
                var brazosWye = codo.Brazos.Select(b => b.Copia()).ToList();
                // El tronco es la utilidad que pasa (los brazos del codo), no el
                // par más recto: con un quiebre fuerte ese par podría incluir el ramal.
                foreach (var b in brazosWye) b.EngroseFt = WyeSolido.ENGROSE_TRONCO_Y_FT;
                brazosWye.Add(ramal);
                double angRamal = ComandosPresion.AnguloRamalDeTres(brazosWye.Select(b => b.Direccion).ToList());
                var infoWye = new WyeSolido.Info
                {
                    Tipo = "WYE", AnguloDeg = angRamal,
                    DiamPrincipalIn = brazosWye.Max(b => b.DiamFt) * 12.0, DiamRamalIn = diamPulg,
                    Material = mat, Red = red,
                };
                ObjectId wyeId = WyeSolido.Crear(db, tr, cT, brazosWye, infoWye, ed);
                if (wyeId == ObjectId.Null)
                {
                    ed.WriteMessage($"\n{tag}   ⚠ No se pudo generar la Wye — se deja el codo del quiebre.");
                    return false;
                }
                try { (tr.GetObject(codo.SolidId, OpenMode.ForWrite) as Entity)?.Erase(); } catch { }
                WyeSolido.Creadas.Remove(codo);
                ed.WriteMessage($"\n{tag}   · Codo del quiebre reemplazado por Wye (ramal a {angRamal:F0}°, Ø{diamPulg:F0}\").");

                // 4) Codo superior (a la cota de la Wye), a TUBO_AUX_CRUCE_FT de
                //    su boca libre. Codo inferior en la misma XY, sobre el eje de
                //    la otra utilidad.
                double sV = ramal.BocaFt + TUBO_AUX_CRUCE_FT + codo90.BocaFt;
                Point3d v1 = cT + dE * sV;
                Point3d v2 = new Point3d(v1.X, v1.Y, ZEnRecta(eCerca, eLejos, v1.X, v1.Y));
                Vector3d dirV = v2.Z > v1.Z ? Vector3d.ZAxis : Vector3d.ZAxis.Negate();

                var infoCodo = new WyeSolido.Info
                {
                    Tipo = "ELBOW", AnguloDeg = 90.0, DiamPrincipalIn = diamPulg,
                    DiamRamalIn = diamPulg, Material = mat, Red = red,
                };
                var supH = new WyeSolido.Brazo { Direccion = dE.Negate(), DiamFt = dAux };
                var supV = new WyeSolido.Brazo { Direccion = dirV, DiamFt = dAux };
                WyeSolido.Crear(db, tr, v1, new List<WyeSolido.Brazo> { supH, supV }, infoCodo, ed);

                // El brazo hacia la otra utilidad lleva su tubo: WyeSolido lo
                // recorta hasta la boca de este codo.
                var infV = new WyeSolido.Brazo { Direccion = dirV.Negate(), DiamFt = dAux };
                var infE = new WyeSolido.Brazo { Direccion = dE3, DiamFt = dOtra, PipeId = eId, Port = ePort };
                WyeSolido.Crear(db, tr, v2, new List<WyeSolido.Brazo> { infV, infE }, infoCodo, ed);

                // 5) Tubos auxiliar (Wye → codo sup.) y vertical (codo sup. → inf.).
                CrearTuboRecto(net, tr, tuboSel, cT + dE * ramal.AlcanceTuboFt, v1 - dE * supH.AlcanceTuboFt);
                Point3d w0 = v1 + dirV * supV.AlcanceTuboFt, w1 = v2 - dirV * infV.AlcanceTuboFt;
                CrearTuboRecto(net, tr, tuboSel, w0, w1);

                // Medido sobre lo construido, no sobre lo pedido.
                double auxVisible = sV - ramal.BocaFt - supH.BocaFt;
                ed.WriteMessage($"\n{tag}   · Tubo auxiliar: {auxVisible:F2} ft entre la boca de la Wye y la del codo.");
                ed.WriteMessage($"\n{tag}   · Vertical: eje Z {w0.Z:F2} → {w1.Z:F2} ({Math.Abs(w1.Z - w0.Z):F2} ft de tubo).");
                ed.WriteMessage($"\n{tag}   · Codo inferior a {sV:F2} ft del cruce, sobre el eje de la otra utilidad (recortada contra él).");
                return true;
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n{tag}   ⚠ Conexión con Wye: {ex.Message}");
                return false;
            }
        }

        // Extremo de un tubo de presión (fuera de CROSS-CONNECTS) que cae en el
        // punto (≤0.5 ft en planta) a la cota de eje dada (≤0.35 ft).
        private static (ObjectId id, int port) BuscarExtremoPresionEn(Transaction tr,
            CivilDocument civilDoc, double x, double y, double zEje)
        {
            ObjectId mejor = ObjectId.Null; int port = 0; double mejorD = double.MaxValue;
            foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
            {
                var red = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                if (red == null || red.Name == "CROSS-CONNECTS") continue;
                foreach (ObjectId pid in red.GetPipeIds())
                {
                    var pp = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                    if (pp == null) continue;
                    for (int k = 0; k < 2; k++)
                    {
                        Point3d q = k == 0 ? pp.StartPoint : pp.EndPoint;
                        double dxy = Math.Sqrt((q.X - x) * (q.X - x) + (q.Y - y) * (q.Y - y));
                        if (dxy > 0.5 || Math.Abs(q.Z - zEje) > 0.35) continue;
                        if (dxy < mejorD) { mejorD = dxy; mejor = pid; port = k; }
                    }
                }
            }
            return (mejor, port);
        }

        // Z de la recta a→b en el punto de planta (x, y) (proyección en XY).
        private static double ZEnRecta(Point3d a, Point3d b, double x, double y)
        {
            double dx = b.X - a.X, dy = b.Y - a.Y, l2 = dx * dx + dy * dy;
            if (l2 < 1e-12) return a.Z;
            double t = ((x - a.X) * dx + (y - a.Y) * dy) / l2;
            return a.Z + t * (b.Z - a.Z);
        }

        private static ObjectId CrearTuboRecto(CivilDB.PressurePipeNetwork net, Transaction tr,
            PresStyles.PressurePartSize tubo, Point3d a, Point3d b)
        {
            if (a.DistanceTo(b) < 0.02) return ObjectId.Null;
            ObjectId id = net.AddLinePipe(new LineSegment3d(a, b), tubo);
            // Re-fijar extremos: AddLinePipe puede ajustarlos.
            try
            {
                var pp = (CivilDB.PressurePipe)tr.GetObject(id, OpenMode.ForWrite);
                pp.StartPoint = a; pp.EndPoint = b;
            }
            catch { }
            return id;
        }

        // Recorta las tuberías horizontales que llegan a un accesorio SÓLIDO.
        // La versión de catálogo (ConectarHorizontalAFitting) lee los puertos
        // del PressurePart, pero un Solid3d no tiene puertos — por eso ahí
        // fallaba con "Unable to cast Solid3d to PressurePart" y las tuberías
        // se metían hasta el centro de la pieza.
        //
        // Aquí se recorta por geometría pura: toda tubería cuyo extremo caiga
        // cerca del cruce se DESLIZA sobre su propio eje (nunca se rota) hasta
        // quedar a `alcance` del centro, que es donde muere dentro de la campana.
        private static void RecortarHorizontalesASolido(Editor ed, Transaction tr,
            CivilDocument civilDoc, double alcance,
            double xCross, double yCross, double zCenter, string etiqueta)
        {
            if (alcance <= 1e-6)
            {
                ed.WriteMessage($"\n{etiqueta}: ⚠ [FITTING-SOLIDO] sin alcance de brazo — no se recorta.");
                return;
            }
            Point3d centro = new Point3d(xCross, yCross, zCenter);
            // Radio de búsqueda: el extremo puede estar a un par de pies si el
            // pipe se partió en el cruce. Generoso, pero el recorte solo mueve
            // el extremo a lo largo del propio eje, así que no puede desviarlo.
            double tol = Math.Max(3.0, alcance * 3.0);
            double tol2 = tol * tol;
            int n = 0;

            foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
            {
                var red = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                if (red == null) continue;
                // La red CROSS-CONNECTS son las verticales recién creadas: esas
                // ya nacen en el extremo correcto del brazo, no se recortan.
                if (red.Name == "CROSS-CONNECTS") continue;

                foreach (ObjectId pid in red.GetPipeIds())
                {
                    CivilDB.PressurePipe pp;
                    try { pp = tr.GetObject(pid, OpenMode.ForWrite) as CivilDB.PressurePipe; }
                    catch { continue; }
                    if (pp == null) continue;

                    // ¿Qué extremo (si alguno) llega al cruce?
                    double dS = (pp.StartPoint - centro).LengthSqrd;
                    double dE = (pp.EndPoint - centro).LengthSqrd;
                    bool usaStart = dS <= tol2 && dS <= dE;
                    bool usaEnd = dE <= tol2 && dE < dS;
                    if (!usaStart && !usaEnd) continue;

                    Point3d fijo = usaStart ? pp.EndPoint : pp.StartPoint;
                    Vector3d eje = (usaStart ? pp.StartPoint : pp.EndPoint) - fijo;
                    if (eje.Length < 1e-9) continue;
                    Vector3d u = eje.GetNormal();

                    // Proyectar el centro sobre el eje del tubo y retroceder el
                    // alcance del brazo: ahí muere el tubo.
                    double tCentro = (centro - fijo).DotProduct(u);
                    double tDestino = tCentro - alcance;
                    if (tDestino <= 0.05) continue;         // dejaría el tubo invertido
                    Point3d destino = fijo + u * tDestino;

                    double antes = (usaStart ? pp.StartPoint : pp.EndPoint).DistanceTo(centro);
                    if (usaStart) pp.StartPoint = destino; else pp.EndPoint = destino;
                    n++;
                    ed.WriteMessage($"\n{etiqueta}: [FITTING-SOLIDO] tubo recortado — " +
                        $"extremo pasó de {antes:F2} a {alcance:F2} ft del centro de la pieza.");
                }
            }
            if (n == 0)
                ed.WriteMessage($"\n{etiqueta}: ⚠ [FITTING-SOLIDO] ningún tubo horizontal a ≤{tol:F1} ft — no se recortó nada.");
        }

        // Versión en SÓLIDO 3D del accesorio de una conexión vertical. Los
        // brazos se arman a mano porque aquí la pieza no nace de una juntura de
        // tubos, sino de un cruce: el tronco sigue la utilidad horizontal y el
        // ramal sale en vertical hacia la otra utilidad.
        //
        // Devuelve la posición del extremo del brazo vertical, que es donde el
        // llamador engancha la tubería vertical.
        private static (ObjectId teeId, int branchPort, Point3d branchWorldPos)?
            ColocarFittingSolido(Editor ed, Transaction tr,
            CivilDB.PressurePipeNetwork net, PresStyles.PressurePartSize teePart,
            CivilDB.PressurePartType tipo, Point3d pos,
            Vector3d dirHoriz, bool branchArriba, string etiqueta,
            double diamTroncoIn, double diamRamalIn,
            out double alcanceHoriz)
        {
            alcanceHoriz = 0;
            try
            {
                // Cada brazo con el diámetro de SU tubo: el tronco, el de la
                // utilidad horizontal; el ramal vertical, el de la vertical.
                // Antes todos los brazos tomaban el diámetro de la pieza de
                // catálogo («tee-24 in x 12 in» → 24"), y con una vertical de
                // Ø12 el ramal salía de Ø24: una boca enorme para un tubo chico.
                // Con el ramal más delgado, SacarCampanasDelCuerpo lo alarga
                // hasta que su campana sale entera del tronco (Tee reductora).
                double diamPieza = ComandosPresion.ExtraerDiametroDeDescripcion(teePart?.Description);
                if (diamPieza <= 0) diamPieza = 12.0;
                double troncoIn = diamTroncoIn > 0 ? diamTroncoIn : diamPieza;
                double ramalIn = diamRamalIn > 0 ? diamRamalIn : troncoIn;
                double troncoFt = troncoIn / 12.0, ramalFt = ramalIn / 12.0;

                Vector3d dh = new Vector3d(dirHoriz.X, dirHoriz.Y, 0);
                if (dh.Length < 1e-9) dh = Vector3d.XAxis;
                dh = dh.GetNormal();
                Vector3d dv = branchArriba ? Vector3d.ZAxis : Vector3d.ZAxis.Negate();

                var brazos = new List<WyeSolido.Brazo>();
                // Codo = la utilidad MUERE en el cruce: un solo brazo horizontal
                // más el vertical (codo reductor si los diámetros difieren).
                // Tee = la utilidad SIGUE de largo: dos brazos horizontales
                // opuestos más el vertical.
                brazos.Add(new WyeSolido.Brazo { Direccion = dh, DiamFt = troncoFt });
                if (tipo != CivilDB.PressurePartType.Elbow)
                    brazos.Add(new WyeSolido.Brazo { Direccion = dh.Negate(), DiamFt = troncoFt });
                brazos.Add(new WyeSolido.Brazo { Direccion = dv, DiamFt = ramalFt });

                var info = new WyeSolido.Info
                {
                    Tipo = tipo == CivilDB.PressurePartType.Elbow ? "ELBOW" : "TEE",
                    AnguloDeg = 90.0,               // el ramal sale perpendicular
                    DiamPrincipalIn = troncoIn,
                    DiamRamalIn = ramalIn,
                    Material = teePart?.Description ?? "",
                    Red = net?.Name ?? "",
                };

                ObjectId sid = WyeSolido.Crear(net.Database, tr, pos, brazos, info, ed);
                if (sid == ObjectId.Null) return null;

                // Alcance del brazo HORIZONTAL: hasta ahí debe recortarse la
                // tubería horizontal que llega al cruce (WyeSolido no puede
                // hacerlo solo porque aquí los brazos no traen PipeId).
                alcanceHoriz = brazos[0].AlcanceTuboFt;
                // Extremo del brazo vertical: ahí engancha la tubería vertical.
                var brazoV = brazos[brazos.Count - 1];
                Point3d fin = pos + dv * brazoV.AlcanceTuboFt;
                string diams = Math.Abs(troncoIn - ramalIn) < 1e-6
                    ? $"Ø{troncoIn:F0}\"" : $"Ø{troncoIn:F0}\" con ramal Ø{ramalIn:F0}\" (reductora)";
                ed.WriteMessage($"\n{etiqueta}: [FITTING-SOLIDO] {info.Tipo} {diams} " +
                    $"en Z={pos.Z:F2}, ramal {(branchArriba ? "arriba" : "abajo")} " +
                    $"hasta Z={fin.Z:F2} (capa {WyeSolido.CAPA}).");
                // branchPort = -1: no hay puertos que conectar, es geometría.
                return (sid, -1, fin);
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n{etiqueta}: ⚠ [FITTING-SOLIDO] {ex.Message}");
                return null;
            }
        }

        // Coloca y orienta un fitting (Tee o Codo), devolviendo la posición
        // WORLD del puerto que apunta a la vertical (branch en un Tee, o el
        // puerto vertical en un Codo). NO conecta la vertical — eso lo hace
        // el llamador después de leer las dos posiciones y crear la vertical
        // entre ellas.
        //
        // Para un Tee: el puerto "branch" es el perpendicular a los dos trunk.
        // Para un Codo (2 puertos): el "branch" es el que apunta a Z.
        private static (ObjectId teeId, int branchPort, Point3d branchWorldPos)?
            ColocarFittingYOrientar(Editor ed, Transaction tr,
            CivilDB.PressurePipeNetwork net, PresStyles.PressurePartSize teePart,
            CivilDB.PressurePartType tipo,
            double xCross, double yCross, double zTee,
            Vector3d dirHoriz, bool branchArriba, string etiqueta,
            double diamTroncoIn, double diamRamalIn,
            out double alcanceHoriz)
        {
            alcanceHoriz = 0;
            try
            {
                Point3d posTee = new Point3d(xCross, yCross, zTee);

                // ── Pieza como SÓLIDO 3D ────────────────────────────────────
                // Este es el otro sitio del plugin donde nacen accesorios (las
                // conexiones verticales entre utilidades que se cruzan). Con el
                // modo sólido activo también se generan aquí, o si no la red
                // quedaba con piezas de catálogo mezcladas con sólidos.
                if (ComandosPresion.FITTING_COMO_SOLIDO)
                {
                    var resSolido = ColocarFittingSolido(ed, tr, net, teePart, tipo,
                        posTee, dirHoriz, branchArriba, etiqueta,
                        diamTroncoIn, diamRamalIn, out double alcSol);
                    if (resSolido.HasValue) { alcanceHoriz = alcSol; return resSolido; }
                    ed.WriteMessage($"\n{etiqueta}: ⚠ [FITTING-SOLIDO] falló — se usa la pieza de catálogo.");
                }

                ObjectId teeId = net.AddFitting(posTee, teePart);
                var parte = (CivilDB.PressurePart)tr.GetObject(teeId, OpenMode.ForWrite);

                // Detectar el puerto branch ANTES de rotar (así podemos leer
                // la dirección actual del trunk desde uno de los otros dos).
                int branchPort = IdentificarBranchPortPorGeometria(parte);

                // Loguea dirección de todos los puertos para debugging.
                for (int p = 0; p < parte.ConnectionCount; p++)
                {
                    var d = parte.GetConnectionAt(p).Direction;
                    ed.WriteMessage($"\n{etiqueta}:   port {p} dir=({d.X:F2},{d.Y:F2},{d.Z:F2}){(p == branchPort ? " ← BRANCH" : "")}");
                }

                // Paso 1: rotar en torno a Z para que el TRUNK quede paralelo
                //         a la utilidad cruzada. El trunk actual se lee de
                //         cualquier puerto ≠ branch (sus componentes Z se
                //         proyectan en XY para el ángulo en planta).
                double angRot = 0;
                if (branchPort >= 0)
                {
                    int trunkPortRef = -1;
                    for (int p = 0; p < parte.ConnectionCount; p++)
                        if (p != branchPort) { trunkPortRef = p; break; }
                    if (trunkPortRef >= 0)
                    {
                        Vector3d dtCur = parte.GetConnectionAt(trunkPortRef).Direction;
                        double curAng = Math.Atan2(dtCur.Y, dtCur.X);
                        double desAng = Math.Atan2(dirHoriz.Y, dirHoriz.X);
                        angRot = desAng - curAng;
                    }
                }
                else
                {
                    // Sin detección de branch, cae al viejo criterio "asume
                    // trunk en X" — puede quedar mal pero al menos no rompe.
                    angRot = Math.Atan2(dirHoriz.Y, dirHoriz.X);
                }
                try
                {
                    var rot = Matrix3d.Rotation(angRot, Vector3d.ZAxis, posTee);
                    parte.TransformBy(rot);
                    ed.WriteMessage($"\n{etiqueta}: Rotación Z aplicada: {angRot * 180.0 / Math.PI:F1}°.");
                }
                catch (Exception exR) { ed.WriteMessage($"\n{etiqueta}: (no se pudo rotar en Z: {exR.Message})"); }

                // Paso 2: inclinar el Tee 90° alrededor del eje del trunk para
                //         que el branch (que por defecto queda en XY tras el paso
                //         1) apunte hacia +Z (Tee inferior) o -Z (Tee superior).
                //         La rotación se calcula a partir de la DIRECCIÓN ACTUAL
                //         del puerto branch, comparada con la deseada.
                if (branchPort >= 0)
                {
                    try
                    {
                        Vector3d dirBranchActual = parte.GetConnectionAt(branchPort).Direction;
                        if (dirBranchActual.Length > 1e-9)
                        {
                            dirBranchActual = dirBranchActual.GetNormal();
                            Vector3d dirBranchDeseada = branchArriba ? Vector3d.ZAxis : Vector3d.ZAxis.Negate();
                            double dot = Math.Max(-1.0, Math.Min(1.0, dirBranchActual.DotProduct(dirBranchDeseada)));
                            if (dot < 0.999)   // no está ya casi alineada
                            {
                                double tiltAngle = Math.Acos(dot);
                                Vector3d axis = dirBranchActual.CrossProduct(dirBranchDeseada);
                                if (axis.Length < 1e-9)
                                {
                                    // Anti-paralelas (180°). Usar el trunk (dirHoriz) como eje.
                                    axis = dirHoriz;
                                }
                                axis = axis.GetNormal();
                                var tilt = Matrix3d.Rotation(tiltAngle, axis, posTee);
                                parte.TransformBy(tilt);
                                ed.WriteMessage($"\n{etiqueta}: Tilt {tiltAngle * 180.0 / Math.PI:F1}° alrededor de eje ({axis.X:F2},{axis.Y:F2},{axis.Z:F2}) — branch antes ({dirBranchActual.X:F2},{dirBranchActual.Y:F2},{dirBranchActual.Z:F2}) → deseado ({dirBranchDeseada.X:F1},{dirBranchDeseada.Y:F1},{dirBranchDeseada.Z:F1}).");
                            }
                            else
                            {
                                ed.WriteMessage($"\n{etiqueta}: Branch ya alineado con {(branchArriba ? "+Z" : "-Z")} (dot={dot:F3}).");
                            }
                        }
                    }
                    catch (Exception exT) { ed.WriteMessage($"\n{etiqueta}: (no se pudo inclinar: {exT.Message})"); }
                }
                if (branchPort < 0)
                {
                    ed.WriteMessage($"\n{etiqueta}: ⚠ No se pudo identificar el puerto branch — no se conectará vertical a este Tee.");
                    return null;
                }
                // Leer posición WORLD del puerto branch después de todas las
                // transformaciones — ahí es donde debe empezar/terminar la vertical.
                Point3d branchPos;
                try { branchPos = parte.GetConnectionAt(branchPort).Position; }
                catch { branchPos = new Point3d(xCross, yCross, zTee); }
                ed.WriteMessage($"\n{etiqueta}: Tee colocado en Z={zTee:F2}, ramal puerto {branchPort}, branchPos=({branchPos.X:F2},{branchPos.Y:F2},{branchPos.Z:F3}).");
                return (teeId, branchPort, branchPos);
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n{etiqueta}: ✗ No se pudo colocar Tee — {ex.Message}");
                return null;
            }
        }

        // Devuelve la tangente 2D (dirección de avance a lo largo de la
        // polilínea) de una ImportPipe en el punto (x, y) que está sobre
        // alguno de sus segmentos (o cerca). Elige el segmento más cercano.
        private static Vector3d TangenteImportPipeEn(ImportPipe ip, double x, double y)
        {
            int nBest = -1; double bestDist2 = double.MaxValue;
            for (int i = 0; i < ip.Vertices.Count - 1; i++)
            {
                var a = ip.Vertices[i]; var b = ip.Vertices[i + 1];
                double dx = b.X - a.X, dy = b.Y - a.Y;
                double len2 = dx * dx + dy * dy;
                if (len2 < 1e-12) continue;
                double t = ((x - a.X) * dx + (y - a.Y) * dy) / len2;
                if (t < 0) t = 0; else if (t > 1) t = 1;
                double px = a.X + t * dx, py = a.Y + t * dy;
                double d2 = (px - x) * (px - x) + (py - y) * (py - y);
                if (d2 < bestDist2) { bestDist2 = d2; nBest = i; }
            }
            if (nBest < 0) return Vector3d.XAxis;
            var pA = ip.Vertices[nBest]; var pB = ip.Vertices[nBest + 1];
            Vector3d v = new Vector3d(pB.X - pA.X, pB.Y - pA.Y, 0);
            return v.Length > 1e-9 ? v.GetNormal() : Vector3d.XAxis;
        }

        private void CrearDuctBanks(Editor ed, Database db, Transaction tr,
            List<ImportDuctBank> dbs, List<ImportPipe> pipes)
        {
            // Capa dedicada para los sólidos del duct bank
            LayerTable lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (!lt.Has("PDFCAD_DUCT_BANK"))
            {
                lt.UpgradeOpen();
                var lr = new LayerTableRecord { Name = "PDFCAD_DUCT_BANK", Color = Autodesk.AutoCAD.Colors.Color.FromColorIndex(Autodesk.AutoCAD.Colors.ColorMethod.ByAci, 8) };
                lt.Add(lr); tr.AddNewlyCreatedDBObject(lr, true);
            }

            BlockTableRecord ms = (BlockTableRecord)tr.GetObject(
                SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);

            int created = 0, skipped = 0, failed = 0;
            foreach (var dbk in dbs)
            {
                try
                {
                    var matchPipe = dbk.MatchedPipe;
                    if (matchPipe == null || matchPipe.Vertices == null || matchPipe.Vertices.Count < 2)
                    {
                        skipped++;
                        continue;
                    }
                    // RENDER_ENVELOPE=0 → el usuario NO quiere el sólido 3D del
                    // contenedor (los conductos se seguirán creando fuera de este
                    // método). Saltamos toda la extrusión.
                    if (!dbk.RenderEnvelope)
                    {
                        skipped++;
                        continue;
                    }

                    double wFt = dbk.WidthIn / 12.0;
                    double hFt = dbk.HeightIn / 12.0;

                    // El invert del pipe padre representa el FONDO EXTERNO del
                    // bancoducto (parte amarilla — cara inferior). Sumamos hFt/2
                    // al Z del path para que el CENTRO del sólido — donde se
                    // apoya el perfil — quede a media altura por encima del
                    // fondo, dejando el fondo del sólido exactamente en Z=invert.
                    //
                    // Se respetan las cotas por tramo (VertexInv) si el usuario
                    // las definió: el path del sólido las usa igual que los
                    // conductos internos, para que fondo y conductos sigan la
                    // misma línea segmento a segmento.
                    int nv = matchPipe.Vertices.Count;
                    double[] zOutDb = InterpolateZ(matchPipe, nv, matchPipe.VertexInv);
                    double[] zInDb  = InterpolateZ(matchPipe, nv, matchPipe.VertexInvIn);

                    // Z del centro del sólido en cada vértice (invert padre + hFt/2)
                    double[] zPath = new double[nv];
                    for (int vi = 0; vi < nv; vi++)
                        zPath[vi] = (zOutDb[vi] + zInDb[vi]) * 0.5 + hFt / 2.0;

                    // Precalcular geometría de arcos en los vértices marcados como
                    // curvos (NoManholeVerts). Usa la MISMA lógica que las pipes
                    // normales para que el sólido siga la misma curva.
                    var curvasDb = new Dictionary<int, CurveGeom>();
                    foreach (int i in matchPipe.NoManholeVerts)
                    {
                        if (i <= 0 || i >= nv - 1) continue;
                        Point3d corner = new Point3d(matchPipe.Vertices[i].X, matchPipe.Vertices[i].Y, zPath[i]);
                        Point3d prevV = new Point3d(matchPipe.Vertices[i - 1].X, matchPipe.Vertices[i - 1].Y, zPath[i - 1]);
                        Point3d nextV = new Point3d(matchPipe.Vertices[i + 1].X, matchPipe.Vertices[i + 1].Y, zPath[i + 1]);
                        var dirPrev = new Vector3d(prevV.X - corner.X, prevV.Y - corner.Y, 0.0);
                        var dirNext = new Vector3d(nextV.X - corner.X, nextV.Y - corner.Y, 0.0);
                        double distPrev = dirPrev.Length, distNext = dirNext.Length;
                        if (distPrev < 1e-6 || distNext < 1e-6) continue;
                        dirPrev = dirPrev / distPrev; dirNext = dirNext / distNext;
                        double cosD = Math.Max(-1.0, Math.Min(1.0, dirPrev.DotProduct(dirNext)));
                        double deltaRad = Math.Acos(cosD);
                        if (deltaRad * 180.0 / Math.PI > 178.0) continue;   // casi recto
                        double r;
                        if (matchPipe.CurveRadiusByVert.TryGetValue(i, out double rExpl) && rExpl > 0.01)
                            r = rExpl;
                        else
                            r = 6.0 * wFt;   // fallback: 6× el ancho del bancoducto
                        double t = r / Math.Tan(deltaRad / 2.0);
                        // Doble curva: si el vértice vecino también es curvo,
                        // reparte el segmento en dos mitades (ver comentario en
                        // CrearRedGravedadCompleta).
                        double capPrevDb = matchPipe.NoManholeVerts.Contains(i - 1) ? 0.48 : 0.9;
                        double capNextDb = matchPipe.NoManholeVerts.Contains(i + 1) ? 0.48 : 0.9;
                        double tMax = Math.Min(distPrev * capPrevDb, distNext * capNextDb);
                        if (t > tMax) { r = tMax * Math.Tan(deltaRad / 2.0); t = tMax; }
                        try
                        {
                            curvasDb[i] = BuildCurveGeom(t, corner, dirPrev, dirNext,
                                                          distPrev, distNext, prevV, nextV, deltaRad);
                        }
                        catch (Exception exArc)
                        {
                            ed.WriteMessage($"\n  ⚠ Duct bank '{dbk.Name}' vértice {i}: no se pudo curvar ({exArc.Message}).");
                        }
                    }

                    // Construir pathPts: para cada segmento entre vértices,
                    // si el vértice inicial o final tiene curva, insertar los
                    // puntos de tangencia + puntos INTERMEDIOS del arco (tesela
                    // el arco en ~16 pasos — el sólido queda visualmente curvo).
                    var rawPts = new List<Point3d>();
                    const int ARC_STEPS = 16;
                    for (int vi = 0; vi < nv; vi++)
                    {
                        Point2d v = matchPipe.Vertices[vi];
                        if (vi == 0 || vi == nv - 1 || !curvasDb.ContainsKey(vi))
                        {
                            rawPts.Add(new Point3d(v.X, v.Y, zPath[vi]));
                        }
                        else
                        {
                            var cg = curvasDb[vi];
                            rawPts.Add(cg.P1);
                            for (int s = 1; s < ARC_STEPS; s++)
                            {
                                double param = cg.Arco.StartAngle
                                    + (cg.Arco.EndAngle - cg.Arco.StartAngle) * s / (double)ARC_STEPS;
                                rawPts.Add(cg.Arco.EvaluatePoint(param));
                            }
                            rawPts.Add(cg.P2);
                        }
                    }
                    // Dedupe: quitar puntos consecutivos coincidentes (< 1e-4 ft).
                    // Cuando dos curvas adyacentes comparten un segmento, la
                    // tangente-salida de la primera y la tangente-entrada de la
                    // segunda pueden coincidir → punto duplicado en el path →
                    // ExtrudeAlongPath falla en silencio y deja sólo la cara.
                    var pathPts = new Point3dCollection();
                    Point3d? last = null;
                    foreach (var pt in rawPts)
                    {
                        if (last.HasValue && last.Value.DistanceTo(pt) < 1e-4) continue;
                        pathPts.Add(pt); last = pt;
                    }
                    if (pathPts.Count < 2) continue;

                    // Base ORTONORMAL a partir del tangente inicial del path.
                    // Antes usábamos up = ZAxis directamente, pero si dir tiene
                    // componente Z (path con pendiente) up ya no es perpendicular
                    // a dir → la matriz de alineación introduce shear y
                    // ExtrudeAlongPath lanza eCannotScaleNonUniformly.
                    // Corregido: right = dir × Zaxis (horizontal), y luego
                    // up = right × dir (perpendicular a dir en el plano
                    // vertical). Fallback si dir es casi vertical.
                    Vector3d dir = (pathPts[1] - pathPts[0]).GetNormal();
                    Vector3d rightCand = dir.CrossProduct(Vector3d.ZAxis);
                    if (rightCand.Length < 1e-9)   // dir ≈ vertical
                        rightCand = dir.CrossProduct(Vector3d.XAxis);
                    Vector3d right = rightCand.GetNormal();
                    Vector3d up = right.CrossProduct(dir).GetNormal();
                    Point3d origin = pathPts[0];

                    Matrix3d mat = Matrix3d.AlignCoordinateSystem(
                        Point3d.Origin, Vector3d.XAxis, Vector3d.YAxis, Vector3d.ZAxis,
                        origin, right, up, dir);

                    // ── Envolvente rectangular ──────────────────────────────
                    using (var pathPoly = new Polyline3d(Poly3dType.SimplePoly, pathPts, false))
                    {
                        ms.AppendEntity(pathPoly);
                        tr.AddNewlyCreatedDBObject(pathPoly, true);

                        using (var profile = new Polyline())
                        {
                            // Radios de fillet por esquina (en ft), acotados a
                            // la mitad del lado más corto para que no se pisen.
                            double halfMin = Math.Min(wFt, hFt) / 2.0;
                            double rTL = Math.Max(0, Math.Min(dbk.CornerTL / 12.0, halfMin));
                            double rTR = Math.Max(0, Math.Min(dbk.CornerTR / 12.0, halfMin));
                            double rBR = Math.Max(0, Math.Min(dbk.CornerBR / 12.0, halfMin));
                            double rBL = Math.Max(0, Math.Min(dbk.CornerBL / 12.0, halfMin));
                            const double B90 = 0.41421356237309503;   // tan(90°/4)
                            double xL = -wFt / 2, xR = wFt / 2;
                            double yB = -hFt / 2, yT = hFt / 2;
                            // Perfil recorrido en CCW: BL → BR → TR → TL.
                            // Para cada esquina con r>0 insertamos dos vértices
                            // (tangente-in con bulge=+tan(22.5°), tangente-out
                            // con bulge=0). Sin redondeo (r=0) va un solo vértice.
                            int vi = 0;
                            // BL
                            if (rBL > 0)
                            {
                                profile.AddVertexAt(vi++, new Point2d(xL, yB + rBL), 0, 0, 0);
                                profile.SetBulgeAt(vi - 1, B90);
                                profile.AddVertexAt(vi++, new Point2d(xL + rBL, yB), 0, 0, 0);
                            }
                            else profile.AddVertexAt(vi++, new Point2d(xL, yB), 0, 0, 0);
                            // BR
                            if (rBR > 0)
                            {
                                profile.AddVertexAt(vi++, new Point2d(xR - rBR, yB), 0, 0, 0);
                                profile.SetBulgeAt(vi - 1, B90);
                                profile.AddVertexAt(vi++, new Point2d(xR, yB + rBR), 0, 0, 0);
                            }
                            else profile.AddVertexAt(vi++, new Point2d(xR, yB), 0, 0, 0);
                            // TR
                            if (rTR > 0)
                            {
                                profile.AddVertexAt(vi++, new Point2d(xR, yT - rTR), 0, 0, 0);
                                profile.SetBulgeAt(vi - 1, B90);
                                profile.AddVertexAt(vi++, new Point2d(xR - rTR, yT), 0, 0, 0);
                            }
                            else profile.AddVertexAt(vi++, new Point2d(xR, yT), 0, 0, 0);
                            // TL
                            if (rTL > 0)
                            {
                                profile.AddVertexAt(vi++, new Point2d(xL + rTL, yT), 0, 0, 0);
                                profile.SetBulgeAt(vi - 1, B90);
                                profile.AddVertexAt(vi++, new Point2d(xL, yT - rTL), 0, 0, 0);
                            }
                            else profile.AddVertexAt(vi++, new Point2d(xL, yT), 0, 0, 0);
                            profile.Closed = true;
                            profile.TransformBy(mat);

                            ms.AppendEntity(profile);
                            tr.AddNewlyCreatedDBObject(profile, true);

                            var curves = new DBObjectCollection { profile };
                            var regions = Region.CreateFromCurves(curves);
                            if (regions.Count > 0)
                            {
                                var region = (Region)regions[0];
                                ms.AppendEntity(region);
                                tr.AddNewlyCreatedDBObject(region, true);

                                // Extrusión: si falla, hay que borrar TAMBIÉN la
                                // region (si no queda huérfana en modelspace y se
                                // ve como "solo la cara" del bancoducto).
                                bool extOk = false;
                                using (var solid = new Solid3d())
                                {
                                    try
                                    {
                                        solid.ExtrudeAlongPath(region, pathPoly, 0);
                                        solid.Layer = "PDFCAD_DUCT_BANK";
                                        ms.AppendEntity(solid);
                                        tr.AddNewlyCreatedDBObject(solid, true);
                                        extOk = true;
                                    }
                                    catch (Exception exExt)
                                    {
                                        ed.WriteMessage($"\n  ⚠ Duct bank '{dbk.Name}': " +
                                                         $"ExtrudeAlongPath falló ({exExt.Message}). Se omite el sólido.");
                                    }
                                }
                                profile.Erase();
                                pathPoly.Erase();
                                region.Erase();
                                if (extOk) created++;
                                else failed++;
                            }
                            else
                            {
                                profile.Erase();
                                pathPoly.Erase();
                                ed.WriteMessage($"\n  ⚠ Duct bank '{dbk.Name}': no se pudo crear la región del perfil.");
                                failed++;
                            }
                        }
                    }

                    // Los conductos internos se crean como Pipe Network (paso 5e).
                }
                catch (Exception exOne)
                {
                    ed.WriteMessage($"\n  ✗ Duct bank '{dbk.Name}': {exOne.Message}");
                    failed++;
                }
            }
            if (created > 0)
                ed.WriteMessage($"\n  · {created} duct bank(s) creados como sólidos 3D en capa PDFCAD_DUCT_BANK.");
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
            public string PipeGuid;       // GUID estable de la familia (Catalog_PartID); "" si custom/sin catálogo
            public string PipeSize;       // p.ej. "48 in"
            public HashSet<int> NoManholeVerts = new HashSet<int>();  // vértices intermedios sin structure
            // Overrides opcionales por segmento (idx del tramo → familia y/o tamaño).
            // Si un tramo no está aquí, usa PipeFamily/PipeSize globales.
            public Dictionary<int, (string fam, string size)> SegOverrides
                = new Dictionary<int, (string, string)>();
            // Radio explícito (pies) por vértice NoManholeVerts, desde PDFCAD_CURVE.
            // Si un vértice curvo no está aquí, se usa el radio automático (6× ancho).
            public Dictionary<int, double> CurveRadiusByVert = new Dictionary<int, double>();
            // Cota explícita por vértice INTERMEDIO, editada a mano en la app de
            // Python (un vértice = el punto donde dos tramos se juntan). Los
            // vértices que no están aquí siguen la interpolación lineal por
            // distancia entre las anclas (InvStart/InvEnd/estos overrides) más
            // cercanas — ver InterpolateZ. Ya viene convertida a unidades del dibujo.
            public Dictionary<int, double> VertexInv = new Dictionary<int, double>();
            public Dictionary<int, double> VertexInvIn = new Dictionary<int, double>();
            // Tubería marcada como ABANDONADA en la app (checkbox "Abandonado").
            // Solo cambia su representación en 3D (Model): se le asigna un PipeStyle
            // cuyo display 3D usa un linetype discontinuo. Planta/perfil quedan igual.
            public bool Abandoned;
            public string NetName = "";
            // Tramo de la app (0 = T1) al que corresponde cada tramo actual. Solo
            // difiere de la identidad si el plugin partió un tramo para una T
            // (PartirTramosEnTes); así los logs siguen nombrando los tramos
            // como la tabla «Cotas por tramo». null = identidad.
            public List<int> TramoPython;
            public int PipeIdx = -1;
            public bool HasDuctBank;
            // Si true, al crear la network, NO se generará ninguna estructura
            // (buzón) en ningún vértice — la pipe queda "flotante". Se usa
            // para los conductos INTERNOS del bancoducto: el buzón real vive
            // en la pipe padre del bancoducto (1 por vértice), no en cada
            // conducto (que si no, dejaría N buzones superpuestos).
            public bool NoStructuresAll;
            // Conducto interno de bancoducto — al crearse el Pipe se le fuerza
            // wall=0 (para que outer == inner en el 3D y no sobresalga de la
            // envolvente) y, si por el catálogo cayó a un tamaño distinto al
            // pedido (típico de Ø1" que no existe en DIP/HDPE → fallback a 2"),
            // se sobrescribe el inner diameter del pipe para que visualmente
            // coincida con lo que el usuario dibujó.
            public bool IsConduit;
            public double ConduitTargetDiamIn;
        }

        // Esquina de un elemento curvo (punto PDFCAD_CURVE, capa PDFCAD_CURVA).
        private class ImportCurveInfo
        {
            public Point2d Location;
            public string Id;
            public double? RadiusFt;   // null = automático (6× ancho/diámetro interior)
        }

        // Geometría ya resuelta del arco tangente en un vértice curvo: los puntos
        // de tangencia (extremos reales de los tramos rectos vecinos, no el vértice
        // original) y el arco que los une.
        private class CurveGeom
        {
            public Point3d P1;         // tangencia sobre el tramo ANTERIOR
            public Point3d P2;         // tangencia sobre el tramo SIGUIENTE
            public CircularArc3d Arco;
            public bool Horario;
            public double Radio;
            // Datos crudos guardados para poder RECALCULAR con un T más chico si
            // esta esquina y la siguiente comparten tramo y se solapan (ver ajuste
            // de "tramo recto mínimo" en CrearRedGravedadCompleta).
            public double T;
            public double DeltaRad;
            public Point3d Corner, PrevV, NextV;
            public Vector3d DirPrev, DirNext;   // unitarios
            public double DistPrev, DistNext;   // distancia esquina→vértice vecino ORIGINAL
        }

        // Punto de la traza del EJE (alignment) + bulge del segmento que EMPIEZA
        // en él (0 = recto). Mismo convenio que Polyline.AddVertexAt: así el eje
        // puede describir el mismo arco que la tubería curva en vez de cortar la
        // esquina en línea recta.
        public struct TrazaPt
        {
            public Point3d P;
            public double Bulge;
            public TrazaPt(Point3d p, double bulge = 0.0) { P = p; Bulge = bulge; }
        }

        // Bulge (tangente de un cuarto del ángulo barrido) del arco de una esquina
        // curva, para que la polilínea del alignment lleve la MISMA curva que la
        // tubería. Se deriva de la CUERDA y el RADIO real — NO de CurveGeom.DeltaRad,
        // que guarda el ángulo INTERIOR entre las dos patas de la esquina y no el
        // barrido del arco (Δ = π − DeltaRad; solo coinciden en esquinas de 90°).
        private static double BulgeDeCurva(CurveGeom cg)
        {
            if (cg == null || cg.Radio < 1e-9) return 0.0;
            double dx = cg.P2.X - cg.P1.X, dy = cg.P2.Y - cg.P1.Y;
            double chord = Math.Sqrt(dx * dx + dy * dy);
            if (chord < 1e-9) return 0.0;
            // Min(1) por ruido numérico cuando la cuerda ≈ 2r. En un fillet el
            // barrido siempre es < 180°, así que esta rama de asin es la correcta.
            double delta = 2.0 * Math.Asin(Math.Min(1.0, chord / (2.0 * cg.Radio)));
            double bulge = Math.Tan(delta / 4.0);
            // El bulge de Polyline es ANTIhorario-positivo.
            return cg.Horario ? -bulge : bulge;
        }

        // Reconstruye P1/P2/Arco/Horario/Radio para una esquina ya analizada,
        // con un T (distancia de recorte) distinto — se usa tanto en el cálculo
        // inicial como en el ajuste por "tramo recto mínimo".
        private static CurveGeom BuildCurveGeom(double t, Point3d corner, Vector3d dirPrev, Vector3d dirNext,
                                                 double distPrev, double distNext, Point3d prevV, Point3d nextV,
                                                 double deltaRad)
        {
            Point3d p1 = new Point3d(corner.X + t * dirPrev.X, corner.Y + t * dirPrev.Y,
                                      corner.Z + (t / distPrev) * (prevV.Z - corner.Z));
            Point3d p2 = new Point3d(corner.X + t * dirNext.X, corner.Y + t * dirNext.Y,
                                      corner.Z + (t / distNext) * (nextV.Z - corner.Z));
            double radioReal; bool horario;
            CircularArc3d arco = ArcoTangente(p1, p2, corner, out radioReal, out horario);
            return new CurveGeom
            {
                P1 = p1, P2 = p2, Arco = arco, Horario = horario, Radio = radioReal, T = t,
                DeltaRad = deltaRad, Corner = corner, PrevV = prevV, NextV = nextV,
                DirPrev = dirPrev, DirNext = dirNext, DistPrev = distPrev, DistNext = distNext,
            };
        }

        private class ImportStruct
        {
            public Point2d Location;
            public string Id;
            public double? Rim;
            public double? Sump;
            public string Part;
            public string PartGuid;                 // GUID estable de la familia (Catalog_PartID); "" si custom/sin catálogo
            public string PartSize;                 // tamaño elegido en el diálogo (ej "48 in")
            public bool Covered = true;
            public string NetKind = "gravity";      // "gravity" | "pressure"
            public double? HeightFt;                // "Altura (Pies)" de Python — fuerza Rim = Sump + esto
            public bool Hidden;                      // "Ocultar buzón" de Python — fuerza "Estructura nula"
        }

        private class DuctConduit
        {
            public double Cx, Cy, Diam;
            public string Label = "";
        }

        private class ImportDuctBank
        {
            public Point2d Anchor;
            public int PipeIdx;
            public string Name = "";
            public double WidthIn, HeightIn;
            public double MarginTop, MarginRight, MarginBottom, MarginLeft;
            public double CornerTL, CornerTR, CornerBR, CornerBL;
            // Si false, NO se crea el sólido 3D del contenedor — solo los
            // conductos internos como pipes. Default true para compatibilidad
            // con DXF antiguos que no traían el flag.
            public bool RenderEnvelope = true;
            public List<DuctConduit> Conduits = new List<DuctConduit>();
            public ImportPipe MatchedPipe;   // se asigna tras emparejar por anchor
        }

        // Conexión vertical aprobada entre dos utilidades que se cruzan a
        // cotas distintas. El plugin dibuja un tramo vertical entre las dos
        // Z en el punto (X,Y) y opcionalmente una válvula al medio.
        private class ImportCrossConnect
        {
            public double X, Y;
            public int PipeA, PipeB;
            public double? ZA, ZB;
            public bool Valve = true;
        }
    }
}
