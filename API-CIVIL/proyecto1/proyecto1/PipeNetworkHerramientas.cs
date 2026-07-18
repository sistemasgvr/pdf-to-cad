using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using ClosedXML.Excel;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.Windows;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  HERRAMIENTAS para la red de GRAVEDAD (Pipe Network) — análogas a las de
//  presión: diagnóstico de diámetros, exportar a Excel (CSV) y sólidos 3D.
//  Archivo separado de RedesTuberia.cs para no mezclar.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosPipeHerramientas
    {
        // =====================================================================
        // DIAGNOSTICAR_RED — revisa la red de gravedad y avisa problemas típicos:
        //   · tubo más grande que la estructura donde entra (no cabe)
        //   · estructura con tapa por debajo del fondo (rim <= sump)
        //   · tubo con pendiente casi nula (agua no corre)
        //   · estructura sin tuberías conectadas
        // =====================================================================
        [CommandMethod("DIAGNOSTICAR_RED")]
        public void DiagnosticarRed()
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
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes de tubería (gravedad)."); tr.Abort(); return; }

                    int nTubos = 0, nEstr = 0, problemas = 0;
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;

                        // Tubos: pendiente casi nula
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                            if (p == null) continue;
                            nTubos++;
                            if (Math.Abs(p.Slope) < 0.0005)
                            {
                                problemas++;
                                ed.WriteMessage($"\n⚠ Tubo '{p.Name}': pendiente casi nula ({p.Slope:P2}). El agua no correría bien.");
                            }
                        }

                        // Estructuras: diámetro vs tubos, rim/sump, aisladas
                        foreach (ObjectId sid in net.GetStructureIds())
                        {
                            CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                            if (st == null) continue;
                            nEstr++;
                            double dEstr = st.InnerDiameterOrWidth;

                            if (st.RimElevation <= st.SumpElevation)
                            {
                                problemas++;
                                ed.WriteMessage($"\n⚠ Estructura '{st.Name}': la tapa (rim {st.RimElevation:F2}) está por debajo o igual al fondo (sump {st.SumpElevation:F2}).");
                            }

                            int nCon = st.ConnectedPipesCount;
                            if (nCon == 0)
                            {
                                problemas++;
                                ed.WriteMessage($"\n⚠ Estructura '{st.Name}': no tiene tuberías conectadas (aislada).");
                            }
                            for (int i = 0; i < nCon; i++)
                            {
                                CivilDB.Pipe p = tr.GetObject(st.get_ConnectedPipe(i), OpenMode.ForRead) as CivilDB.Pipe;
                                if (p == null) continue;
                                double dTubo = p.InnerDiameterOrWidth;
                                if (dEstr > 0 && dTubo > dEstr + 1e-6)
                                {
                                    problemas++;
                                    ed.WriteMessage($"\n⚠ El tubo '{p.Name}' (Ø {dTubo:F0}) es MAYOR que la estructura '{st.Name}' (Ø/ancho {dEstr:F0}): no cabe / conexión forzada.");
                                }
                            }
                        }
                    }

                    tr.Commit();
                    if (problemas == 0)
                        ed.WriteMessage($"\n✓ Sin problemas detectados. Revisados {nTubos} tubo(s) y {nEstr} estructura(s).");
                    else
                        ed.WriteMessage($"\n— Diagnóstico terminado: {problemas} aviso(s) en {nTubos} tubo(s) y {nEstr} estructura(s).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // EXPORTAR_RED_CSV — vuelca la(s) red(es) de gravedad a un CSV que abre
        //   Excel: bloques de TUBERIAS y ESTRUCTURAS con sus datos.
        // =====================================================================
        [CommandMethod("EXPORTAR_RED_CSV")]
        public void ExportarRedCsv()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptSaveFileOptions opt = new PromptSaveFileOptions("\nGuardar datos de la red como CSV (Excel):");
            opt.Filter = "CSV para Excel (*.csv)|*.csv";
            opt.InitialFileName = "red_gravedad";
            PromptFileNameResult rF = ed.GetFileNameForSave(opt);
            if (rF.Status != PromptStatus.OK) return;
            string ruta = rF.StringResult;
            if (!ruta.ToLowerInvariant().EndsWith(".csv")) ruta += ".csv";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes de tubería."); tr.Abort(); return; }

                    CultureInfo ci = CultureInfo.CurrentCulture;
                    Func<double, string> N = v => v.ToString("0.###", ci);
                    Func<string, string> T = s => "\"" + (s ?? "").Replace("\"", "\"\"") + "\"";

                    var sb = new StringBuilder();
                    sb.AppendLine("sep=;");

                    // ---------- TUBERÍAS ----------
                    sb.AppendLine("TUBERIAS");
                    sb.AppendLine("Red;Nombre;Descripcion;Diametro_interno;X_ini;Y_ini;Z_ini;X_fin;Y_fin;Z_fin;Longitud;Pendiente;Capa");
                    int nTubos = 0, nEstr = 0;
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                            if (p == null) continue;
                            Point3d a = p.StartPoint, b = p.EndPoint;
                            sb.AppendLine(string.Join(";",
                                T(p.NetworkName), T(p.Name), T(p.PartDescription), N(p.InnerDiameterOrWidth),
                                N(a.X), N(a.Y), N(a.Z), N(b.X), N(b.Y), N(b.Z),
                                N(p.Length2DCenterToCenter), N(p.Slope), T(p.Layer)));
                            nTubos++;
                        }
                    }

                    // ---------- ESTRUCTURAS ----------
                    sb.AppendLine();
                    sb.AppendLine("ESTRUCTURAS");
                    sb.AppendLine("Red;Nombre;Descripcion;Diametro_ancho;X;Y;Cota_tapa;Cota_fondo;Tubos_conectados;Capa");
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;
                        foreach (ObjectId sid in net.GetStructureIds())
                        {
                            CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                            if (st == null) continue;
                            Point3d q = st.Position;
                            sb.AppendLine(string.Join(";",
                                T(st.NetworkName), T(st.Name), T(st.PartDescription), N(st.InnerDiameterOrWidth),
                                N(q.X), N(q.Y), N(st.RimElevation), N(st.SumpElevation),
                                st.ConnectedPipesCount.ToString(ci), T(st.Layer)));
                            nEstr++;
                        }
                    }

                    File.WriteAllText(ruta, sb.ToString(), new UTF8Encoding(true));
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Datos exportados a:\n  {ruta}\n  {nTubos} tubería(s) y {nEstr} estructura(s)." +
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
        // EXTRAER_SOLIDOS_RED — extrae los sólidos 3D de tubos y estructuras de
        //   la(s) red(es) de gravedad y los dibuja en el ModelSpace.
        // =====================================================================
        [CommandMethod("EXTRAER_SOLIDOS_RED")]
        public void ExtraerSolidosRed()
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
                    ObjectIdCollection nets = civilDoc.GetPipeNetworkIds();
                    if (nets.Count == 0) { ed.WriteMessage("\nNo hay redes de tubería."); tr.Abort(); return; }

                    AsegurarCapa(tr, db, capa);
                    BlockTable bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                    BlockTableRecord ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);

                    int nSol = 0;
                    foreach (ObjectId nid in nets)
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;

                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            try
                            {
                                CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                                Solid3d s = p?.Solid3dBody;
                                if (s == null) continue;
                                if (!string.IsNullOrWhiteSpace(capa)) s.Layer = capa;
                                ms.AppendEntity(s); tr.AddNewlyCreatedDBObject(s, true); nSol++;
                            }
                            catch { }
                        }
                        foreach (ObjectId sid in net.GetStructureIds())
                        {
                            try
                            {
                                CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                                Solid3d s = st?.Solid3dBody;
                                if (s == null) continue;
                                if (!string.IsNullOrWhiteSpace(capa)) s.Layer = capa;
                                ms.AppendEntity(s); tr.AddNewlyCreatedDBObject(s, true); nSol++;
                            }
                            catch { }
                        }
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ {nSol} sólido(s) 3D extraído(s)" +
                                    (string.IsNullOrWhiteSpace(capa) ? "." : $" en la capa '{capa}'."));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // ---------- Helpers de capa (locales, para no depender de otros archivos) ----------
        private static string PreguntarCapa(Editor ed)
        {
            PromptStringOptions pso = new PromptStringOptions("\nCapa de destino (Enter = capa actual):");
            pso.AllowSpaces = true;
            PromptResult r = ed.GetString(pso);
            return (r.Status == PromptStatus.OK && !string.IsNullOrWhiteSpace(r.StringResult)) ? r.StringResult.Trim() : "";
        }

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

        // =====================================================================
        // EXPORTAR_RED_EXCEL — exporta TODAS las redes (gravedad + presión) a
        //   un archivo .xlsx real con ClosedXML. Hojas separadas por tipo.
        // =====================================================================
        [CommandMethod("EXPORTAR_RED_EXCEL")]
        public void ExportarRedExcel()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptSaveFileOptions opt = new PromptSaveFileOptions("\nGuardar datos de las redes como Excel:");
            opt.Filter = "Libro Excel (*.xlsx)|*.xlsx";
            opt.InitialFileName = "redes_civil3d";
            PromptFileNameResult rF = ed.GetFileNameForSave(opt);
            if (rF.Status != PromptStatus.OK) return;
            string ruta = rF.StringResult;
            if (!ruta.ToLowerInvariant().EndsWith(".xlsx")) ruta += ".xlsx";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var wb = new XLWorkbook();

                    // ── GRAVEDAD ─────────────────────────────────────
                    ObjectIdCollection gNets = civilDoc.GetPipeNetworkIds();
                    if (gNets.Count > 0)
                    {
                        var wsTub = wb.AddWorksheet("Tuberias_Gravedad");
                        string[] hT = {"Red","Nombre","Descripcion","Ø_interno","X_ini","Y_ini","Z_ini","X_fin","Y_fin","Z_fin","Longitud","Pendiente","Capa"};
                        for (int c = 0; c < hT.Length; c++) wsTub.Cell(1, c + 1).Value = hT[c];
                        int row = 2;
                        foreach (ObjectId nid in gNets)
                        {
                            CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                            if (net == null) continue;
                            foreach (ObjectId pid in net.GetPipeIds())
                            {
                                CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                                if (p == null) continue;
                                Point3d a = p.StartPoint, b = p.EndPoint;
                                wsTub.Cell(row, 1).Value = p.NetworkName;
                                wsTub.Cell(row, 2).Value = p.Name;
                                wsTub.Cell(row, 3).Value = p.PartDescription;
                                wsTub.Cell(row, 4).Value = p.InnerDiameterOrWidth;
                                wsTub.Cell(row, 5).Value = a.X; wsTub.Cell(row, 6).Value = a.Y; wsTub.Cell(row, 7).Value = a.Z;
                                wsTub.Cell(row, 8).Value = b.X; wsTub.Cell(row, 9).Value = b.Y; wsTub.Cell(row, 10).Value = b.Z;
                                wsTub.Cell(row, 11).Value = p.Length2DCenterToCenter;
                                wsTub.Cell(row, 12).Value = p.Slope;
                                wsTub.Cell(row, 13).Value = p.Layer;
                                row++;
                            }
                        }
                        FormatHeaders(wsTub);

                        var wsEst = wb.AddWorksheet("Estructuras_Gravedad");
                        string[] hE = {"Red","Nombre","Descripcion","Ø_ancho","X","Y","Cota_tapa","Cota_fondo","Tubos_conectados","Capa"};
                        for (int c = 0; c < hE.Length; c++) wsEst.Cell(1, c + 1).Value = hE[c];
                        row = 2;
                        foreach (ObjectId nid in gNets)
                        {
                            CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                            if (net == null) continue;
                            foreach (ObjectId sid in net.GetStructureIds())
                            {
                                CivilDB.Structure st = tr.GetObject(sid, OpenMode.ForRead) as CivilDB.Structure;
                                if (st == null) continue;
                                Point3d q = st.Position;
                                wsEst.Cell(row, 1).Value = st.NetworkName;
                                wsEst.Cell(row, 2).Value = st.Name;
                                wsEst.Cell(row, 3).Value = st.PartDescription;
                                wsEst.Cell(row, 4).Value = st.InnerDiameterOrWidth;
                                wsEst.Cell(row, 5).Value = q.X; wsEst.Cell(row, 6).Value = q.Y;
                                wsEst.Cell(row, 7).Value = st.RimElevation;
                                wsEst.Cell(row, 8).Value = st.SumpElevation;
                                wsEst.Cell(row, 9).Value = st.ConnectedPipesCount;
                                wsEst.Cell(row, 10).Value = st.Layer;
                                row++;
                            }
                        }
                        FormatHeaders(wsEst);
                    }

                    // ── PRESIÓN ──────────────────────────────────────
                    ObjectIdCollection pNets = civilDoc.GetPressurePipeNetworkIds();
                    if (pNets.Count > 0)
                    {
                        var wsP = wb.AddWorksheet("Tuberias_Presion");
                        string[] hP = {"Red","Nombre","Descripcion","Ø_nominal","X_ini","Y_ini","Z_ini","X_fin","Y_fin","Z_fin","Longitud","Capa"};
                        for (int c = 0; c < hP.Length; c++) wsP.Cell(1, c + 1).Value = hP[c];
                        int row = 2;

                        var wsF = wb.AddWorksheet("Accesorios_Presion");
                        string[] hF = {"Red","Nombre","Tipo","Descripcion","X","Y","Z","Conexiones","Capa"};
                        for (int c = 0; c < hF.Length; c++) wsF.Cell(1, c + 1).Value = hF[c];
                        int rowF = 2;

                        var wsA = wb.AddWorksheet("Valvulas_Hidrantes");
                        string[] hA = {"Red","Nombre","Tipo","Descripcion","X","Y","Z","Conexiones","Capa"};
                        for (int c = 0; c < hA.Length; c++) wsA.Cell(1, c + 1).Value = hA[c];
                        int rowA = 2;

                        foreach (ObjectId nid in pNets)
                        {
                            CivilDB.PressurePipeNetwork net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                            if (net == null) continue;
                            string nn = net.Name;

                            foreach (ObjectId pid in net.GetPipeIds())
                            {
                                var p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                                if (p == null) continue;
                                Point3d a = p.StartPoint, b = p.EndPoint;
                                wsP.Cell(row, 1).Value = nn;
                                wsP.Cell(row, 2).Value = p.Name;
                                wsP.Cell(row, 3).Value = p.PartDescription;
                                wsP.Cell(row, 4).Value = p.NominalDiameter;
                                wsP.Cell(row, 5).Value = a.X; wsP.Cell(row, 6).Value = a.Y; wsP.Cell(row, 7).Value = a.Z;
                                wsP.Cell(row, 8).Value = b.X; wsP.Cell(row, 9).Value = b.Y; wsP.Cell(row, 10).Value = b.Z;
                                wsP.Cell(row, 11).Value = a.DistanceTo(b);
                                wsP.Cell(row, 12).Value = p.Layer;
                                row++;
                            }

                            foreach (ObjectId fid in net.GetFittingIds())
                            {
                                var f = tr.GetObject(fid, OpenMode.ForRead) as CivilDB.PressureFitting;
                                if (f == null) continue;
                                Point3d q = f.Position;
                                wsF.Cell(rowF, 1).Value = nn;
                                wsF.Cell(rowF, 2).Value = f.Name;
                                wsF.Cell(rowF, 3).Value = f.PartType.ToString();
                                wsF.Cell(rowF, 4).Value = f.PartDescription;
                                wsF.Cell(rowF, 5).Value = q.X; wsF.Cell(rowF, 6).Value = q.Y; wsF.Cell(rowF, 7).Value = q.Z;
                                wsF.Cell(rowF, 8).Value = f.ConnectionCount;
                                wsF.Cell(rowF, 9).Value = f.Layer;
                                rowF++;
                            }

                            foreach (ObjectId aid in net.GetAppurtenanceIds())
                            {
                                var ap = tr.GetObject(aid, OpenMode.ForRead) as CivilDB.PressureAppurtenance;
                                if (ap == null) continue;
                                Point3d q = ap.Position;
                                wsA.Cell(rowA, 1).Value = nn;
                                wsA.Cell(rowA, 2).Value = ap.Name;
                                wsA.Cell(rowA, 3).Value = ap.PartType.ToString();
                                wsA.Cell(rowA, 4).Value = ap.PartDescription;
                                wsA.Cell(rowA, 5).Value = q.X; wsA.Cell(rowA, 6).Value = q.Y; wsA.Cell(rowA, 7).Value = q.Z;
                                wsA.Cell(rowA, 8).Value = ap.ConnectionCount;
                                wsA.Cell(rowA, 9).Value = ap.Layer;
                                rowA++;
                            }
                        }
                        FormatHeaders(wsP);
                        FormatHeaders(wsF);
                        FormatHeaders(wsA);
                    }

                    if (wb.Worksheets.Count == 0)
                    {
                        ed.WriteMessage("\nNo hay redes (ni gravedad ni presión).");
                        tr.Abort(); return;
                    }

                    wb.SaveAs(ruta);
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Datos exportados a:\n  {ruta}");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        private static void FormatHeaders(IXLWorksheet ws)
        {
            var hdr = ws.Row(1);
            hdr.Style.Font.Bold = true;
            hdr.Style.Fill.BackgroundColor = XLColor.DarkBlue;
            hdr.Style.Font.FontColor = XLColor.White;
            ws.Columns().AdjustToContents();
        }
    }
}
