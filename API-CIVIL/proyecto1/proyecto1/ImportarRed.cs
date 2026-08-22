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

                        // VERTEX_INV: 'idx~z;idx~z' — cota explícita (unidad XDATA) en
                        // vértices intermedios editados individualmente desde Python.
                        // Los vértices no listados siguen la interpolación de siempre.
                        var vertexInv = new Dictionary<int, double>();
                        string vertexInvStr = XdStr(xd, "VERTEX_INV", "");
                        if (!string.IsNullOrWhiteSpace(vertexInvStr))
                            foreach (string entry in vertexInvStr.Split(';'))
                            {
                                if (string.IsNullOrWhiteSpace(entry)) continue;
                                var parts = entry.Split('~');
                                if (parts.Length < 2) continue;
                                if (!int.TryParse(parts[0], out int idx)) continue;
                                string zs = (parts[1] ?? "").Trim().Replace(',', '.');
                                double zv;
                                if (double.TryParse(zs, NumberStyles.Float, CultureInfo.InvariantCulture, out zv))
                                    vertexInv[idx] = zv * k;
                            }

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
                            NoManholeVerts = noMan,
                            SegOverrides = segOv,
                            VertexInv = vertexInv,
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
                            // Ya viene en pies desde Python (spinbox "Altura (Pies)") — sin
                            // aplicar el factor de conversión k que sí usan RIM/SUMP.
                            HeightFt = XdNullDouble(xd, "HEIGHT_FT"),
                        };
                        structs.Add(newSt);
                        Dbg("XDATA_STRUCT", ("id", newSt.Id), ("x", pt.Position.X.ToString("F3")),
                            ("y", pt.Position.Y.ToString("F3")), ("net", newSt.NetKind),
                            ("part", newSt.Part), ("part_size", newSt.PartSize),
                            ("covered", newSt.Covered ? "1" : "0"),
                            ("rim", newSt.Rim?.ToString("F3") ?? ""),
                            ("sump", newSt.Sump?.ToString("F3") ?? ""),
                            ("height_ft", newSt.HeightFt?.ToString("F3") ?? ""));
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
                }
                trScan.Commit();
            }

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
                        ip.CurveRadiusByVert[vi] = best.RadiusFt.Value;
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
            var alignmentsPendientes = new List<DatosAlignment>();
            foreach (var kv in gravedad)
            {
                string netName = $"RED-{kv.Key}";
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
                string netName = $"RED-{kv.Key}";
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
                            if (!dAlign.StartStructId.IsNull)
                            {
                                try
                                {
                                    Point3d p0 = dAlign.Traza[0], p1 = dAlign.Traza[1];
                                    Point3d p0Rec = RecortarAlBordeBuzon(trAli, dAlign.StartStructId, p0, p1);
                                    dAlign.Traza[0] = new Point3d(p0Rec.X, p0Rec.Y, p0.Z);
                                }
                                catch (Exception exR) { Dbg("RECORTE_START_ERR", ("msg", exR.Message)); }
                            }
                            if (!dAlign.EndStructId.IsNull)
                            {
                                try
                                {
                                    int lastIdx = dAlign.Traza.Count - 1;
                                    Point3d pN = dAlign.Traza[lastIdx], pPrev = dAlign.Traza[lastIdx - 1];
                                    Point3d pNRec = RecortarAlBordeBuzon(trAli, dAlign.EndStructId, pN, pPrev);
                                    dAlign.Traza[lastIdx] = new Point3d(pNRec.X, pNRec.Y, pN.Z);
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

            // ── 5c. Limpiar duplicados "-N" con dimensiones idénticas al padre ──
            // Debe correr DESPUÉS de crear las redes (pasos 4-5): CatalogoBancos.AddBancosYBuzones
            // (paso 0.b) y el propio AddPartSize de Civil3D pueden dejar variantes "- N" al
            // agregar tamaños del catálogo; limpiar antes (como estaba) no encontraba nada que limpiar.
            // NOTA: BuscarEstructura/BuscarTuberia ya NO crean tamaños dinámicamente — solo
            // eligen entre los que ya existen en el catálogo (ver RedesTuberia.cs, SizeMasCercano).
            LimpiarDuplicadosPartSize(ed, db);

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

            ed.WriteMessage("\n═══ IMPORTAR RED — fin ═══");
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
            public List<Point3d> Traza;
            public ObjectId StartStructId;
            public ObjectId EndStructId;
            public ObjectId NetId;
            public bool EsGravedad;
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
            // Traza per-pipe (no un solo trazaEje global). Al final agrupamos por
            // componentes conectados y creamos un alignment por componente — así
            // 3 sub-redes desconectadas en la misma capa NUNCA se unen con un eje
            // que salta entre ellas.
            var pipeTrazas = new List<(List<Point3d> pts, ObjectId startSt, ObjectId endSt)>();
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
                    Point3d corner = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zVerts[i]);
                    Point3d prevV = new Point3d(ip.Vertices[i - 1].X, ip.Vertices[i - 1].Y, zVerts[i - 1]);
                    Point3d nextV = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, zVerts[i + 1]);
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
                    if (ip.CurveRadiusByVert.TryGetValue(i, out double rExplicito) && rExplicito > 0.01)
                        r = rExplicito;
                    else
                    {
                        if (anchoInteriorCache == null)
                            anchoInteriorCache = ResolveAnchoInterior(tr, net, pipeFam, pipeSize, ed);
                        r = 6.0 * anchoInteriorCache.Value;
                    }
                    double t = r / Math.Tan(deltaRad / 2.0);
                    // No recortar más allá de lo disponible en cada recta vecina (deja
                    // margen del 10% para que siga quedando un tramo recto visible).
                    double tMax = Math.Min(distPrev, distNext) * 0.9;
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
                var pipeTraza = new List<Point3d>();
                for (int i = 0; i < nVerts; i++)
                {
                    if (curvasPorVertice.TryGetValue(i, out CurveGeom cgTraza))
                    { pipeTraza.Add(cgTraza.P1); pipeTraza.Add(cgTraza.P2); }
                    else
                        pipeTraza.Add(new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zVerts[i]));
                }

                var vertStructIds = new List<ObjectId>();
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
                    double zInv = zVerts[i];
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
                    Point3d p1 = new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zVerts[i]);
                    Point3d p2 = new Point3d(ip.Vertices[i + 1].X, ip.Vertices[i + 1].Y, zVerts[i + 1]);

                    bool startEsCurva = i > 0 && curvasPorVertice.ContainsKey(i);
                    bool endEsCurva = i + 1 < nVerts - 1 && curvasPorVertice.ContainsKey(i + 1);

                    if (startEsCurva)
                        p1 = curvasPorVertice[i].P2;              // tangencia de SALIDA del arco anterior
                    else if (i > 0 && ip.NoManholeVerts.Contains(i))
                    {
                        // Sin geometría de curva (ángulo casi recto): solape cosmético.
                        var p0 = new Point3d(ip.Vertices[i - 1].X, ip.Vertices[i - 1].Y, zVerts[i - 1]);
                        Vector3d back = p0 - p1;
                        if (back.Length > 1e-6) p1 = p1 + back.GetNormal() * overlapFt;
                    }
                    if (endEsCurva)
                        p2 = curvasPorVertice[i + 1].P1;          // tangencia de ENTRADA al arco siguiente
                    else if (i + 1 < nVerts - 1 && ip.NoManholeVerts.Contains(i + 1))
                    {
                        var p3 = new Point3d(ip.Vertices[i + 2].X, ip.Vertices[i + 2].Y, zVerts[i + 2]);
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
            ed.WriteMessage($"\n[DIAG] Estructura rim/auto: ok={stOk} fallo={stErr}  {stMsg}");

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

            ed.WriteMessage($"\n✓ Red {(sinBuzones ? "conduit" : "gravedad")} '{nm}': " +
                             $"{createdStructs.Count} nodos, {nPipes} tuberías, " +
                             $"{componentes.Count} componente(s) para eje.");
            return netId;
        }

        // Agrupa los pipes en componentes conectados por coincidencia de
        // coordenadas de sus vértices (Union-Find). Devuelve, por cada
        // componente, la lista de puntos concatenada (traza para el alignment)
        // y los structIds de los extremos absolutos del componente.
        private static List<(List<Point3d> traza, ObjectId startSt, ObjectId endSt)>
            AgruparPipesPorComponente(
                List<ImportPipe> pipes,
                List<(List<Point3d> pts, ObjectId startSt, ObjectId endSt)> pipeTrazas)
        {
            int n = pipeTrazas.Count;
            var salida = new List<(List<Point3d>, ObjectId, ObjectId)>();
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
                    string k = Key(v);
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

            // Para cada componente: concatenar trazas en el orden que aparecen,
            // pero dedupear vértices consecutivos idénticos (para evitar puntos
            // repetidos entre pipes que comparten un buzón interno).
            foreach (var kv in porRaiz)
            {
                var traza = new List<Point3d>();
                ObjectId startSt = ObjectId.Null, endSt = ObjectId.Null;
                foreach (int i in kv.Value)
                {
                    var (pts, sSt, eSt) = pipeTrazas[i];
                    foreach (var p in pts)
                    {
                        if (traza.Count > 0)
                        {
                            var prev = traza[traza.Count - 1];
                            if (Math.Round(prev.X, 2) == Math.Round(p.X, 2) &&
                                Math.Round(prev.Y, 2) == Math.Round(p.Y, 2))
                                continue;                 // duplicado en juntura
                        }
                        traza.Add(p);
                    }
                    if (startSt.IsNull) startSt = sSt;
                    endSt = eSt;
                }
                if (traza.Count >= 2) salida.Add((traza, startSt, endSt));
            }
            return salida;
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
            // Traza per-pipe (para Union-Find de componentes conectados).
            var pipeTrazasPres = new List<List<Point3d>>();

            foreach (var ip in pipes)
            {
                PresStyles.PressurePartSize tuboElegido = MatchPresionTubo(tubos, ip.Diameter, ip.PipeFamily);
                Dbg("PIPE_PRES_MATCH", ("pedido_fam", ip.PipeFamily ?? ""),
                    ("pedido_size", ip.PipeSize ?? ""), ("diam", ip.Diameter.ToString("F1")),
                    ("elegida", tuboElegido?.Description ?? "?"));

                int nVerts = ip.Vertices.Count;
                double zStart = ip.InvStart ?? 0.0;
                double zEnd = ip.InvEnd ?? zStart;
                double[] zpv = ZalongByDistance(ip.Vertices, zStart, zEnd);

                var pipeTraza = new List<Point3d>();
                for (int i = 0; i < nVerts; i++)
                    pipeTraza.Add(new Point3d(ip.Vertices[i].X, ip.Vertices[i].Y, zpv[i]));
                pipeTrazasPres.Add(pipeTraza);

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
            // Igual que en gravedad: StartPoint.Z es el EJE del tubo; el invert
            // (rasante) capturado desde Python es la SOLERA. Convertimos:
            //   eje = invert + radio_interior
            // Así la propiedad "Elevación de rasante" que muestra Civil 3D
            // queda igual al invert que trajo el DXF.
            foreach (var pe in pipeEndpoints)
            {
                try
                {
                    var pp = (CivilDB.PressurePipe)tr.GetObject(pe.id, OpenMode.ForWrite);
                    // NominalDiameter viene en pulgadas → convertir a pies para
                    // que el radio quede en la misma unidad que StartPoint.Z (ft).
                    double r = 0.0;
                    try { r = (pp.NominalDiameter / 12.0) / 2.0; } catch { }
                    Point3d cs = pp.StartPoint, ce = pp.EndPoint;
                    pp.StartPoint = new Point3d(cs.X, cs.Y, pe.start.Z + r);
                    pp.EndPoint   = new Point3d(ce.X, ce.Y, pe.end.Z   + r);
                }
                catch { }
            }

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

            ed.WriteMessage($"\n✓ Red presión '{nombre}': {nPipes} tubería(s), {nFittings} fitting(s), " +
                            $"{componentesPres.Count} componente(s) para eje.");
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
            if (ip.VertexInv == null || ip.VertexInv.Count == 0 || nVerts < 3)
                return ZalongByDistance(ip.Vertices, zStart, zEnd);

            // Anclas fijas: vértice 0 y último (InvStart/InvEnd) más cualquier
            // vértice intermedio con cota explícita (VERTEX_INV). Entre cada par
            // de anclas consecutivas se interpola por distancia, igual que antes.
            var anchors = new SortedDictionary<int, double> { [0] = zStart, [nVerts - 1] = zEnd };
            foreach (var kv in ip.VertexInv)
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
                if (s == "PDFCAD_PIPE" || s == "PDFCAD_STRUCT" || s == "PDFCAD_CURVE")
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
            public string PartSize;                 // tamaño elegido en el diálogo (ej "48 in")
            public bool Covered = true;
            public string NetKind = "gravity";      // "gravity" | "pressure"
            public double? HeightFt;                // "Altura (Pies)" de Python — fuerza Rim = Sump + esto
        }
    }
}
