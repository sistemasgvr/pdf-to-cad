using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Text.RegularExpressions;
using ClosedXML.Excel;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;
using AecPD = Autodesk.Aec.PropertyData;
using Exception = System.Exception;

// ============================================================================
//  Flujo Excel ↔ Property Sets
//    1. EXPORTAR_TUBERIAS_PS: escribe un .xlsx con [Nombre, Tipo] por tubería
//       (gravedad + presión). El usuario agrega columnas adicionales; cada
//       columna extra = un PropertySet nuevo con una propiedad "Valor".
//    2. IMPORTAR_TUBERIAS_PS: lee el .xlsx; para cada columna extra crea la
//       definición del PS si no existe y adjunta+setea el valor a la tubería
//       que coincida por Name.
//  Idempotente: re-importar no duplica.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosPropertySetsExcel
    {
        private const string HOJA = "Tuberias";
        private const string PROP_VALOR = "Valor";

        // =====================================================================
        // EXPORTAR_TUBERIAS_PS
        // =====================================================================
        [CommandMethod("EXPORTAR_TUBERIAS_PS")]
        public void ExportarTuberiasPS()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptSaveFileOptions opt = new PromptSaveFileOptions(
                "\nGuardar formato Excel de tuberías (para editar Property Sets):");
            opt.Filter = "Libro Excel (*.xlsx)|*.xlsx";
            opt.InitialFileName = "tuberias_property_sets";
            PromptFileNameResult r = ed.GetFileNameForSave(opt);
            if (r.Status != PromptStatus.OK) return;
            string ruta = r.StringResult;
            if (!ruta.ToLowerInvariant().EndsWith(".xlsx")) ruta += ".xlsx";

            int nG = 0, nP = 0;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var wb = new XLWorkbook();
                    var ws = wb.AddWorksheet(HOJA);
                    ws.Cell(1, 1).Value = "Nombre";
                    ws.Cell(1, 2).Value = "Tipo";
                    ws.Cell(1, 1).Style.Font.Bold = true;
                    ws.Cell(1, 2).Style.Font.Bold = true;

                    int row = 2;

                    // Gravedad
                    foreach (ObjectId nid in civilDoc.GetPipeNetworkIds())
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                            if (p == null || string.IsNullOrWhiteSpace(p.Name)) continue;
                            ws.Cell(row, 1).Value = p.Name;
                            ws.Cell(row, 2).Value = "gravity";
                            row++; nG++;
                        }
                    }

                    // Presión
                    foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
                    {
                        CivilDB.PressurePipeNetwork net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (net == null) continue;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.PressurePipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (p == null || string.IsNullOrWhiteSpace(p.Name)) continue;
                            ws.Cell(row, 1).Value = p.Name;
                            ws.Cell(row, 2).Value = "pressure";
                            row++; nP++;
                        }
                    }

                    ws.Columns().AdjustToContents();
                    wb.SaveAs(ruta);
                    tr.Commit();

                    ed.WriteMessage($"\n✓ Excel exportado: {ruta}");
                    ed.WriteMessage($"\n   Tuberías gravedad: {nG}   presión: {nP}");
                    ed.WriteMessage("\n   Agrega columnas extras (Material, Fecha, etc.) y reimporta con IMPORTAR_TUBERIAS_PS.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n✗ Error exportando: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // IMPORTAR_TUBERIAS_PS
        // =====================================================================
        [CommandMethod("IMPORTAR_TUBERIAS_PS")]
        public void ImportarTuberiasPS()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptOpenFileOptions opt = new PromptOpenFileOptions("\nSeleccionar Excel con Property Sets:");
            opt.Filter = "Libro Excel (*.xlsx)|*.xlsx";
            PromptFileNameResult r = ed.GetFileNameForOpen(opt);
            if (r.Status != PromptStatus.OK) return;
            string ruta = r.StringResult;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var wb = new XLWorkbook(ruta);
                    IXLWorksheet ws = null;
                    foreach (var s in wb.Worksheets) if (s.Name.Equals(HOJA, StringComparison.OrdinalIgnoreCase)) { ws = s; break; }
                    if (ws == null) { ed.WriteMessage($"\n✗ No se encontró la hoja '{HOJA}' en el archivo."); tr.Abort(); return; }

                    // Cabecera
                    var lastCol = ws.LastColumnUsed();
                    var lastRow = ws.LastRowUsed();
                    if (lastCol == null || lastRow == null || lastRow.RowNumber() < 2)
                    { ed.WriteMessage("\n✗ Excel vacío."); tr.Abort(); return; }

                    int cols = lastCol.ColumnNumber();
                    if (cols < 3)
                    { ed.WriteMessage("\n(!) No hay columnas extras que importar (solo Nombre/Tipo)."); tr.Commit(); return; }

                    // Cols 3..N son PS a crear/actualizar
                    var psHeaders = new List<string>();       // nombre visible original
                    var psNames = new List<string>();         // sanitizado
                    for (int c = 3; c <= cols; c++)
                    {
                        string h = (ws.Cell(1, c).GetString() ?? "").Trim();
                        if (string.IsNullOrWhiteSpace(h)) { psHeaders.Add(""); psNames.Add(""); continue; }
                        psHeaders.Add(h);
                        psNames.Add(Sanitizar(h));
                    }

                    // Índice de pipes del dwg por nombre
                    var idxPipes = new Dictionary<string, ObjectId>(StringComparer.OrdinalIgnoreCase);
                    foreach (ObjectId nid in civilDoc.GetPipeNetworkIds())
                    {
                        CivilDB.Network net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.Network;
                        if (net == null) continue;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.Pipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.Pipe;
                            if (p == null || string.IsNullOrWhiteSpace(p.Name)) continue;
                            idxPipes[p.Name] = pid;
                        }
                    }
                    foreach (ObjectId nid in civilDoc.GetPressurePipeNetworkIds())
                    {
                        CivilDB.PressurePipeNetwork net = tr.GetObject(nid, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
                        if (net == null) continue;
                        foreach (ObjectId pid in net.GetPipeIds())
                        {
                            CivilDB.PressurePipe p = tr.GetObject(pid, OpenMode.ForRead) as CivilDB.PressurePipe;
                            if (p == null || string.IsNullOrWhiteSpace(p.Name)) continue;
                            idxPipes[p.Name] = pid;
                        }
                    }

                    // Crear PS definitions si faltan; devolver map nombre→ObjectId
                    AecPS.DictionaryPropertySetDefinitions dict = new AecPS.DictionaryPropertySetDefinitions(db);
                    var psDefIds = new Dictionary<string, ObjectId>();
                    int nPsNuevos = 0;
                    for (int i = 0; i < psNames.Count; i++)
                    {
                        string name = psNames[i];
                        if (string.IsNullOrWhiteSpace(name)) continue;
                        ObjectId psdId = ObjectId.Null;
                        if (dict.Has(name, tr))
                        {
                            psdId = dict.GetAt(name);
                        }
                        else
                        {
                            psdId = CrearPSDefinicion(db, tr, dict, name);
                            nPsNuevos++;
                        }
                        psDefIds[name] = psdId;
                    }

                    // Recorrer filas de datos
                    int nActualizadas = 0, nNoEncontradas = 0, nSetsEscritos = 0;
                    int startRow = 2;
                    int endRow = lastRow.RowNumber();
                    for (int row = startRow; row <= endRow; row++)
                    {
                        string nombre = (ws.Cell(row, 1).GetString() ?? "").Trim();
                        if (string.IsNullOrWhiteSpace(nombre)) continue;
                        if (!idxPipes.TryGetValue(nombre, out ObjectId entId))
                        { nNoEncontradas++; continue; }

                        Entity ent = tr.GetObject(entId, OpenMode.ForWrite) as Entity;
                        if (ent == null) continue;

                        bool tocada = false;
                        for (int i = 0; i < psNames.Count; i++)
                        {
                            string psName = psNames[i];
                            if (string.IsNullOrWhiteSpace(psName)) continue;
                            var cell = ws.Cell(row, 3 + i);
                            string val = cell.IsEmpty() ? "" : cell.GetString().Trim();
                            if (string.IsNullOrEmpty(val)) continue;

                            ObjectId psdId = psDefIds[psName];
                            // Adjuntar si no lo tiene ya
                            ObjectId psId = ObjectIdDelPS(tr, ent, psdId);
                            if (psId.IsNull)
                            {
                                try { AecPS.PropertyDataServices.AddPropertySet(ent, psdId); } catch { }
                                psId = ObjectIdDelPS(tr, ent, psdId);
                            }
                            if (psId.IsNull) continue;

                            var ps = tr.GetObject(psId, OpenMode.ForWrite) as AecPS.PropertySet;
                            if (ps == null) continue;
                            int propId = ps.PropertyNameToId(PROP_VALOR);
                            if (propId < 0) continue;
                            ps.SetAt(propId, val);
                            nSetsEscritos++;
                            tocada = true;
                        }
                        if (tocada) nActualizadas++;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Property Sets importados.");
                    ed.WriteMessage($"\n   Definiciones nuevas creadas: {nPsNuevos}");
                    ed.WriteMessage($"\n   Tuberías actualizadas:       {nActualizadas}");
                    ed.WriteMessage($"\n   Valores escritos:            {nSetsEscritos}");
                    if (nNoEncontradas > 0)
                        ed.WriteMessage($"\n   (Ignoradas {nNoEncontradas} fila(s) con nombre no encontrado en el dibujo.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\n✗ Error importando: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // ---------------------------------------------------------------------
        // Helpers
        // ---------------------------------------------------------------------
        private static string Sanitizar(string s)
        {
            // Deja letras/dígitos/guion bajo. Todo lo demás → "_". No inicia con dígito.
            string x = Regex.Replace(s, @"[^A-Za-z0-9_]", "_");
            x = Regex.Replace(x, @"_+", "_").Trim('_');
            if (x.Length == 0) x = "PS";
            if (char.IsDigit(x[0])) x = "_" + x;
            return x;
        }

        private static ObjectId CrearPSDefinicion(Database db, Transaction tr,
            AecPS.DictionaryPropertySetDefinitions dict, string name)
        {
            var psd = new AecPS.PropertySetDefinition();
            psd.SetToStandard(db);
            psd.SubSetDatabaseDefaults(db);
            psd.AlternateName = name;
            var filter = new StringCollection();
            filter.Add("AecDbPipe");
            filter.Add("AecDbPressurePipe");
            psd.SetAppliesToFilter(filter, false);

            var pd = new AecPS.PropertyDefinition();
            pd.SetToStandard(db);
            pd.SubSetDatabaseDefaults(db);
            pd.Name = PROP_VALOR;
            pd.DataType = AecPD.DataType.Text;
            pd.DefaultData = "";
            psd.Definitions.Add(pd);

            dict.AddNewRecord(name, psd);
            tr.AddNewlyCreatedDBObject(psd, true);
            return dict.GetAt(name);
        }

        private static ObjectId ObjectIdDelPS(Transaction tr, Entity ent, ObjectId psdId)
        {
            try
            {
                ObjectIdCollection ids = AecPS.PropertyDataServices.GetPropertySets(ent);
                if (ids == null) return ObjectId.Null;
                foreach (ObjectId pid in ids)
                {
                    var ps = tr.GetObject(pid, OpenMode.ForRead) as AecPS.PropertySet;
                    if (ps != null && ps.PropertySetDefinition == psdId) return pid;
                }
            }
            catch { }
            return ObjectId.Null;
        }
    }
}
