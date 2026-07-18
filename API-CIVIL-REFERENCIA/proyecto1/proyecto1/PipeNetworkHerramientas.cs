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
using Autodesk.AutoCAD.Windows;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;   // Property Sets
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
                    var solidos = new List<ObjectId>();   // para poder adjuntarles un Property Set
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
                                ms.AppendEntity(s); tr.AddNewlyCreatedDBObject(s, true); nSol++; solidos.Add(s.ObjectId);
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
                                ms.AppendEntity(s); tr.AddNewlyCreatedDBObject(s, true); nSol++; solidos.Add(s.ObjectId);
                            }
                            catch { }
                        }
                    }

                    // ¿Adjuntar un Property Set a los sólidos recién creados? (ventana con botones)
                    int nPS = 0;
                    if (nSol > 0)
                    {
                        PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Adjuntar un Property Set a los sólidos? [Si/No] <No>:", "Si No");
                        pk.AllowNone = true;
                        PromptResult rk = ed.GetKeywords(pk);
                        if (rk.Status == PromptStatus.OK && rk.StringResult == "Si")
                            nPS = AdjuntarPropertySetVentana(ed, tr, db, solidos);
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ {nSol} sólido(s) 3D extraído(s)" +
                                    (string.IsNullOrWhiteSpace(capa) ? "." : $" en la capa '{capa}'.") +
                                    (nPS > 0 ? $" Property Set adjuntado a {nPS}." : ""));
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

        // Lee los Property Sets del dibujo, los muestra en una VENTANA con botones y adjunta
        // el elegido a la lista de objetos. Devuelve cuántos objetos recibieron el Property Set.
        private static int AdjuntarPropertySetVentana(Editor ed, Transaction tr, Database db, List<ObjectId> objetos)
        {
            var nombres = new List<string>();
            var psdIds = new List<ObjectId>();
            AecPS.DictionaryPropertySetDefinitions dict = new AecPS.DictionaryPropertySetDefinitions(db);
            ObjectIdCollection recs = dict.Records;
            if (recs != null)
                foreach (ObjectId id in recs)
                {
                    AecPS.PropertySetDefinition d = tr.GetObject(id, OpenMode.ForRead) as AecPS.PropertySetDefinition;
                    if (d != null) { nombres.Add(d.Name); psdIds.Add(id); }
                }
            if (nombres.Count == 0)
            {
                ed.WriteMessage("\nNo hay definiciones de Property Set en el dibujo. Créalas (Administrador de estilos) y reintenta.");
                return 0;
            }

            VentanaPropertySet win = new VentanaPropertySet(nombres);
            Application.ShowModalWindow(win);
            if (win.SelectedIndex < 0) { ed.WriteMessage("\n(Property Set: cancelado.)"); return 0; }
            ObjectId psdId = psdIds[win.SelectedIndex];

            int n = 0, fallo = 0;
            foreach (ObjectId id in objetos)
            {
                try
                {
                    Entity ent = tr.GetObject(id, OpenMode.ForWrite) as Entity;
                    if (ent == null) continue;
                    AecPS.PropertyDataServices.AddPropertySet(ent, psdId);
                    n++;
                }
                catch { fallo++; }
            }
            if (fallo > 0)
                ed.WriteMessage($"\n⚠ {fallo} objeto(s) no aceptaron el Property Set (su 'Applies To' quizá no incluye ese tipo).");
            return n;
        }
    }
}
