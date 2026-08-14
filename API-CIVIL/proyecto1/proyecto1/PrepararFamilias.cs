using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Xml;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  PREPARAR_FAMILIAS
//  ---------------------------------------------------------------------------
//  Flujo del botón "Preparar Familias para Dibujar" del panel Python:
//
//    Paso 1: PARTCATALOGREGEN para Pipe y para Structure — recarga en Civil 3D
//            los .apc que la app Python acaba de tocar.
//    Paso 2: enumera Part Families disponibles, muestra CheckedListBox WPF y
//            para cada familia marcada crea/completa una PartsList del mismo
//            nombre con TODOS sus tamaños.
//
//  Estrategia de espera: SendStringToExecute encadenado. Los comandos que se
//  envían por esa API se ejecutan en orden estrictamente secuencial en el hilo
//  de UI de AutoCAD, así que `_PARTCATALOGREGEN` (paso 1) siempre termina
//  antes de que arranque `PREPARAR_FAMILIAS_STEP2` (paso 2). Es más limpio que
//  registrarse a Application.Idle porque no requiere de-registrarse, no lanza
//  timeouts y respeta el modelo de comandos de AutoCAD.
//
//  Comando registrado en:  Civil3DBasico.ComandosPrepararFamilias
//    - PREPARAR_FAMILIAS         → dispara la cadena (regen + step2)
//    - PREPARAR_FAMILIAS_STEP2   → interno, no llamar a mano
//
//  Clases del SDK Civil 3D usadas:
//    - PartsStyles.PartsList.GetAvailablePartFamilies(DomainType)  → enumera
//      familias del catálogo actualmente activo (Pipe o Structure).
//    - CivilDocument.Styles.PartsListSet  → colección de PartsLists del dibujo.
//    - PartsList.Create(civilDoc, name)   → crea PartsList nueva.
//    - PartsList.AddPartFamilyByGuid(dom, guid)   → añade la family.
//    - PartsList.GetPartFamilyIdsByDomain(dom)    → ids de families ya presentes.
//    - PartFamily.AddPartSize(SizeFilterRecord)   → añade tamaños; el filtro
//      con IsMultipleSelect=true en cada campo IsFromList equivale al checkbox
//      "Añadir todos los tamaños" del diálogo manual.
//
//  Si el catálogo devuelve cero familias (o sólo stock) el paso 2 muestra el
//  aviso "PARTCATALOGREGEN no completó. Ejecuta el comando manualmente" — no
//  se hace ningún cambio en el dibujo.
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosPrepararFamilias
    {
        [CommandMethod("PREPARAR_FAMILIAS")]
        public void PrepararFamilias()
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            var ed = doc.Editor;
            ed.WriteMessage("\n═══ PREPARAR FAMILIAS ═══");
            ed.WriteMessage("\n→ Regenerando catálogo de Pipe…");
            // TODO(2025-ESP): PARTCATALOGREGEN en Civil 3D 2020+ abre un TaskDialog
            // "¿Qué catálogo?" con Pipe/Structure/Both. `_PARTCATALOGREGEN _P `
            // no siempre lo pasa desde línea de comandos porque el diálogo no
            // acepta tokens inline en todas las builds. Si en tu build no
            // avanza automáticamente, elige Pipe (paso 1) y Structure (paso 2)
            // manualmente cuando aparezca el diálogo — el resto sigue igual.
            doc.SendStringToExecute("_PARTCATALOGREGEN _P ", true, false, false);
            doc.SendStringToExecute("_PARTCATALOGREGEN _S ", true, false, false);
            // Paso 2 se enqueua acá y por eso corre DESPUÉS de los dos regens.
            doc.SendStringToExecute("PREPARAR_FAMILIAS_STEP2 ", true, false, false);
        }

        [CommandMethod("PREPARAR_FAMILIAS_STEP2", CommandFlags.Modal)]
        public void PrepararFamiliasStep2()
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            var ed = doc.Editor;
            var db = doc.Database;

            // Debug log — se guarda al final en el Desktop del usuario.
            var log = new StringBuilder();
            void L(string s) { log.AppendLine(s); ed.WriteMessage("\n" + s); }
            void D(string s) { log.AppendLine(s); }             // solo al archivo

            L("═══════════════════════════════════════════════════════════════");
            L($"  PREPARAR_FAMILIAS_STEP2 — {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            L("═══════════════════════════════════════════════════════════════");

            // 0) Contexto del sistema
            DumpSystemContext(db, ed, L);

            // 1) Enumerar familias disponibles del catálogo activo.
            var pipes   = SafeList(CivilDB.DomainType.Pipe,      L);
            var structs = SafeList(CivilDB.DomainType.Structure, L);
            L("");
            L($"→ GetAvailablePartFamilies:  Pipe={pipes.Count}   Structure={structs.Count}");
            foreach (var f in pipes)    D($"    [Pipe]  GUID={f.GUID}  Desc='{f.Description}'");
            foreach (var f in structs)  D($"    [Struct] GUID={f.GUID}  Desc='{f.Description}'");

            if (pipes.Count == 0 && structs.Count == 0)
            {
                var path = SaveLog(log);
                MessageBox.Show(
                    "PARTCATALOGREGEN no completó — no encontré ninguna familia en el catálogo.\n\n" +
                    "Ejecuta el comando manualmente (para Pipe y para Structure) y vuelve a intentar.\n\n" +
                    $"Log guardado en:\n{path}",
                    "Preparar familias",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            // 2) Diálogo WPF de selección
            var items = new List<FamiliaItem>();
            foreach (var f in pipes)    items.Add(new FamiliaItem(f, CivilDB.DomainType.Pipe));
            foreach (var f in structs)  items.Add(new FamiliaItem(f, CivilDB.DomainType.Structure));

            var wnd = new PrepararFamiliasWindow(items);
            try { wnd.Owner = System.Windows.Interop.HwndSource
                    .FromHwnd(AcadApp.MainWindow.Handle)?.RootVisual as Window; }
            catch { }
            bool? result = AcadApp.ShowModalWindow(AcadApp.MainWindow.Handle, wnd, false);
            if (result != true) { L(""); L("(Cancelado por el usuario)"); SaveLog(log); return; }

            var seleccionadas = items.Where(x => x.IsChecked).ToList();
            if (seleccionadas.Count == 0)
            {
                L(""); L("(No marcaste ninguna familia.)"); SaveLog(log); return;
            }
            L(""); L($"→ Familias seleccionadas: {seleccionadas.Count}");
            foreach (var it in seleccionadas)
                D($"    · [{it.DomainLabel}] {it.DisplayName}  ({it.Guid})");

            // 3) Procesar cada familia dentro de una única transacción
            int totalFams = 0, totalSizes = 0;
            var errores = new List<string>();
            bool saltarTodas = false, preguntaHecha = false;

            using (var tr = db.TransactionManager.StartTransaction())
            {
                CivilDocument civilDoc;
                try { civilDoc = CivilApplication.ActiveDocument; }
                catch (Exception ex)
                {
                    L($"✗ No hay Civil Document activo: {ex.Message}");
                    tr.Abort(); SaveLog(log); return;
                }
                PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                L($"→ PartsListSet del dibujo: {plSet.Count} listas existentes.");
                for (int i = 0; i < plSet.Count; i++)
                {
                    try
                    {
                        var p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (p != null) D($"    · '{p.Name}'");
                    }
                    catch { }
                }

                foreach (var item in seleccionadas)
                {
                    string nombreFam = item.DisplayName;
                    L("");
                    L($"─── Procesando '{nombreFam}' [{item.DomainLabel}] ───");
                    D($"    GUID = {item.Guid}");

                    try
                    {
                        // a) ¿Ya existe una PartsList con ese nombre?
                        ObjectId existente = ObjectId.Null;
                        for (int i = 0; i < plSet.Count; i++)
                        {
                            var p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                            if (p != null && string.Equals(p.Name, nombreFam, StringComparison.OrdinalIgnoreCase))
                            { existente = plSet[i]; break; }
                        }
                        ObjectId partsListId;
                        if (!existente.IsNull)
                        {
                            L($"  ≡ PartsList '{nombreFam}' ya existía — usaré esa.");
                            if (!preguntaHecha)
                            {
                                var dlg = new PregSobrescribirWindow(nombreFam);
                                try { dlg.Owner = wnd; } catch { }
                                AcadApp.ShowModalWindow(AcadApp.MainWindow.Handle, dlg, false);
                                saltarTodas    = !dlg.Sobreescribir;
                                if (dlg.AplicarATodos) preguntaHecha = true;
                                else preguntaHecha = false;
                            }
                            if (saltarTodas) { L("  → Saltada por decisión del usuario."); continue; }
                            partsListId = existente;
                        }
                        else
                        {
                            L($"  + Creando nueva PartsList '{nombreFam}' (plSet.Add).");
                            partsListId = plSet.Add(nombreFam);
                        }

                        var partsList = tr.GetObject(partsListId, OpenMode.ForWrite) as PartsStyles.PartsList;
                        if (partsList == null)
                        {
                            errores.Add($"{nombreFam}: no pude abrir la PartsList.");
                            L("  ✗ No pude abrir la PartsList (GetObject devolvió null).");
                            continue;
                        }

                        // b) Añadir la Part Family (si no está ya).
                        bool yaEstabaLaFam = false;
                        ObjectIdCollection idsExist = partsList.GetPartFamilyIdsByDomain(item.Domain);
                        foreach (ObjectId fid in idsExist)
                        {
                            var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                            if (fam != null && string.Equals(fam.GUID, item.Guid, StringComparison.OrdinalIgnoreCase))
                            { yaEstabaLaFam = true; break; }
                        }
                        if (!yaEstabaLaFam)
                        {
                            L($"  + AddPartFamilyByGuid({item.Domain}, {item.Guid})");
                            try { partsList.AddPartFamilyByGuid(item.Domain, item.Guid); }
                            catch (Exception exA)
                            {
                                errores.Add($"{nombreFam}: AddPartFamilyByGuid falló — {exA.Message}");
                                L($"  ✗ AddPartFamilyByGuid falló: {exA.Message}");
                                D($"     Stack: {exA.StackTrace}");
                                continue;
                            }
                        }
                        else L("  ≡ Familia ya estaba dentro de la PartsList.");

                        // c) Localizar el PartFamily recién añadido
                        PartsStyles.PartFamily famNew = null;
                        ObjectIdCollection famIds = partsList.GetPartFamilyIdsByDomain(item.Domain);
                        foreach (ObjectId fid in famIds)
                        {
                            var fam = tr.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                            if (fam == null) continue;
                            if (string.Equals(fam.GUID, item.Guid, StringComparison.OrdinalIgnoreCase))
                            { famNew = fam; break; }
                        }
                        if (famNew == null)
                        {
                            errores.Add($"{nombreFam}: familia añadida pero no la pude localizar después.");
                            L("  ✗ Post-add: no encontré el PartFamily con este GUID en la lista.");
                            continue;
                        }

                        int nSizesAntes = famNew.PartSizeCount;
                        L($"  · PartSizeCount ANTES: {nSizesAntes}");

                        // d) Añadir TODOS los tamaños del catálogo — uno por uno.
                        //    Estrategia: leer el .xml de la familia (localizado vía la
                        //    variable AECC…CATALOG), extraer cada "fila lógica" del
                        //    design table (o cada combinación paramétrica), y por cada
                        //    una construir un SizeFilterRecord con valores específicos
                        //    y llamar AddPartSize(filter). Esto equivale exactamente a
                        //    marcar TODOS los checkboxes del diálogo manual.
                        int nAgregados = 0;
                        try
                        {
                            nAgregados = AddAllPartSizesFromCatalog(famNew, item, L, D);
                        }
                        catch (Exception exS)
                        {
                            L($"  ✗ AddAllPartSizesFromCatalog falló: {exS.Message}");
                            D($"     Stack: {exS.StackTrace}");
                        }

                        int nSizesDespues = famNew.PartSizeCount;
                        L($"  · PartSizeCount DESPUÉS: {nSizesDespues}  (Δ = {nAgregados})");

                        // Log del count total (los nombres específicos requieren API distinto)
                        D($"      PartSizeCount total = {famNew.PartSizeCount}");

                        totalFams++;
                        totalSizes += nAgregados;
                    }
                    catch (Exception ex)
                    {
                        errores.Add($"{nombreFam}: {ex.Message}");
                        L($"  ✗ {nombreFam}: {ex.Message}");
                        D($"     Stack: {ex.StackTrace}");
                    }
                }

                tr.Commit();
            }

            // 4) Resumen y guardado del log
            L("");
            L("═══════════════════════════════════════════════════════════════");
            L($"  RESUMEN: {totalFams} familias procesadas, {totalSizes} tamaños añadidos");
            if (errores.Count > 0)
            {
                L($"  ERRORES ({errores.Count}):");
                foreach (var e in errores) L("    · " + e);
            }
            L("═══════════════════════════════════════════════════════════════");
            var logPath = SaveLog(log);

            var msg = $"Familias procesadas: {totalFams}\n" +
                      $"Tamaños añadidos en total: {totalSizes}\n\n" +
                      (errores.Count > 0
                          ? "Con errores. Ver log:\n" + logPath
                          : "Log completo en:\n" + logPath);
            MessageBox.Show(msg, "Preparar familias — resumen",
                MessageBoxButton.OK,
                errores.Count > 0 ? MessageBoxImage.Warning : MessageBoxImage.Information);
        }

        // ───────────── Contexto del sistema (sysvars y catálogos) ─────────────
        static void DumpSystemContext(Database db, Autodesk.AutoCAD.EditorInput.Editor ed,
                                        Action<string> W)
        {
            W("");
            W("→ Contexto del sistema:");
            foreach (var sv in new[] { "AECCPIPECATALOG", "AECCSTRUCTURECATALOG",
                                        "AECCPIPESTORMSEWERSCATALOG",
                                        "AECCPIPEWATERWORKSCATALOG" })
            {
                try
                {
                    object val = AcadApp.GetSystemVariable(sv);
                    W($"    {sv} = {val}");
                }
                catch (Exception ex) { W($"    {sv} = <error: {ex.Message}>"); }
            }
            // Listar contenido físico del catálogo apuntado por AECCPIPECATALOG
            try
            {
                object pv = AcadApp.GetSystemVariable("AECCPIPECATALOG");
                if (pv is string pipeCat && !string.IsNullOrEmpty(pipeCat) && Directory.Exists(pipeCat))
                {
                    W($"    Contenido de {pipeCat}:");
                    foreach (var d in Directory.EnumerateDirectories(pipeCat))
                        W($"      · {Path.GetFileName(d)}/");
                }
            }
            catch { }
            try
            {
                object sv2 = AcadApp.GetSystemVariable("AECCSTRUCTURECATALOG");
                if (sv2 is string sc && !string.IsNullOrEmpty(sc) && Directory.Exists(sc))
                {
                    W($"    Contenido de {sc}:");
                    foreach (var d in Directory.EnumerateDirectories(sc))
                        W($"      · {Path.GetFileName(d)}/");
                }
            }
            catch { }
        }

        // =====================================================================
        //  AddAllPartSizesFromCatalog
        //  Añade a la PartFamily del dibujo (`fam`) UN PartSize por cada
        //  "combinación válida" del catálogo. Localiza el .xml de la familia
        //  vía AECCPIPECATALOG / AECCSTRUCTURECATALOG y soporta los DOS layouts
        //  típicos que Civil 3D admite en Part Builder:
        //
        //    A) DESIGN TABLE — <Column context="XXX"> con <Row id="rN">v</Row>
        //       Cada fila r_i define un tamaño con los valores paralelos de
        //       cada columna (p.ej. r0 = {PIW=13, PIH=8}). Este es el formato
        //       de Bancos de Tubos.
        //
        //    B) PARAMÉTRICA — <ColumnConstList context="XXX"> con <Item>v</Item>
        //       Cada Item es un valor permitido; los tamaños son el producto
        //       cartesiano de todos los valores de todas las columnas. Este es
        //       el formato de Bancoductos AGL, Buzones, etc.
        //
        //  Devuelve el número de PartSize añadidos.
        // =====================================================================
        static int AddAllPartSizesFromCatalog(PartsStyles.PartFamily fam, FamiliaItem item,
                                                Action<string> L, Action<string> D)
        {
            string xmlPath = LocateFamilyXml(item, D);
            if (xmlPath == null || !File.Exists(xmlPath))
            {
                L($"  ✗ No encontré el .xml de la familia (kind={item.DomainLabel}). Se omiten los tamaños.");
                return 0;
            }
            D($"      XML fuente: {xmlPath}");

            var xdoc = new XmlDocument();
            try { xdoc.Load(xmlPath); }
            catch (Exception ex) { L($"  ✗ No pude cargar el XML: {ex.Message}"); return 0; }

            // 1) DESIGN TABLE — <Column>/<Row>
            var rowsTable = new Dictionary<string, List<double>>();
            foreach (XmlNode col in xdoc.SelectNodes("//Column"))
            {
                string name = col.Attributes?["name"]?.Value ?? "";
                if (string.IsNullOrEmpty(name)) continue;
                var vals = new List<double>();
                foreach (XmlNode r in col.SelectNodes("Row"))
                {
                    if (double.TryParse(r.InnerText?.Trim(),
                            System.Globalization.NumberStyles.Any,
                            System.Globalization.CultureInfo.InvariantCulture, out double d))
                        vals.Add(d);
                }
                if (vals.Count > 0) rowsTable[name] = vals;
            }

            // 2) PARAMÉTRICA — <ColumnConstList>/<Item>
            var paramLists = new Dictionary<string, List<double>>();
            foreach (XmlNode col in xdoc.SelectNodes("//ColumnConstList"))
            {
                string name = col.Attributes?["name"]?.Value ?? "";
                if (string.IsNullOrEmpty(name)) continue;
                var vals = new List<double>();
                foreach (XmlNode it in col.SelectNodes("Item"))
                {
                    if (double.TryParse(it.InnerText?.Trim(),
                            System.Globalization.NumberStyles.Any,
                            System.Globalization.CultureInfo.InvariantCulture, out double d))
                        vals.Add(d);
                }
                if (vals.Count > 0) paramLists[name] = vals;
            }

            D($"      Columnas <Column>/<Row>:        {rowsTable.Count}");
            D($"      Columnas <ColumnConstList>/<Item>: {paramLists.Count}");

            // Generar la lista de combinaciones {nombre → valor} a instanciar.
            List<Dictionary<string, double>> combinaciones;
            if (rowsTable.Count > 0)
            {
                int nRows = rowsTable.Values.Min(v => v.Count);
                combinaciones = new List<Dictionary<string, double>>(nRows);
                for (int r = 0; r < nRows; r++)
                {
                    var combo = new Dictionary<string, double>();
                    foreach (var kv in rowsTable) combo[kv.Key] = kv.Value[r];
                    combinaciones.Add(combo);
                }
                L($"  · Design table: {rowsTable.Count} columnas × {nRows} filas = {combinaciones.Count} tamaños");
            }
            else if (paramLists.Count > 0)
            {
                combinaciones = CartesianProduct(paramLists);
                L($"  · Paramétrica: {paramLists.Count} columnas → {combinaciones.Count} combinaciones");
            }
            else
            {
                L("  ⚠ XML no tiene <Column>/<Row> ni <ColumnConstList>/<Item> — no puedo enumerar tamaños.");
                return 0;
            }

            // PartSizeCount previo — si un tamaño ya existe (re-ejecución) el
            // AddPartSize lanza excepción silenciosa o no incrementa el contador;
            // usamos ese delta para saber si de verdad se añadió algo nuevo.
            D($"      PartSizeCount antes de iterar: {fam.PartSizeCount}");

            // Iterar combinaciones y añadir cada tamaño como PartSize específico.
            int nAgregados = 0, nSaltados = 0, nFallos = 0;
            for (int idx = 0; idx < combinaciones.Count; idx++)
            {
                var combo = combinaciones[idx];
                try
                {
                    var filtro = new PartsStyles.SizeFilterRecord(fam);
                    for (int i = 0; i < filtro.ParamCount; i++)
                    {
                        var campo = filtro[i];
                        if (campo == null || campo.IsReadOnly) continue;
                        string cn = SafeGetProp<string>(campo, "Name") ?? "";
                        if (!combo.TryGetValue(cn, out double val)) continue;
                        // Setear el valor específico y desactivar multi-select del campo.
                        try
                        {
                            if (campo.IsFromList) campo.IsMultipleSelect = false;
                            SetFieldValueRobust(campo, val, D);
                        }
                        catch (Exception exSv)
                        { D($"        combo[{idx}] campo '{cn}': setter fall {exSv.Message}"); }
                    }
                    int before = fam.PartSizeCount;
                    fam.AddPartSize(filtro);
                    int delta = fam.PartSizeCount - before;
                    if (delta > 0) nAgregados += delta;
                    else nSaltados++;
                }
                catch (Exception exAP)
                {
                    nFallos++;
                    // Duplicados suelen lanzar mensaje específico: silenciar al usuario
                    // pero logear al archivo.
                    D($"      combo[{idx}] AddPartSize excepción: {exAP.Message}");
                }
            }
            L($"  ✓ Añadidos: {nAgregados}  |  Saltados (dup): {nSaltados}  |  Fallos: {nFallos}");
            return nAgregados;
        }

        // Producto cartesiano de N listas de doubles ordenadas por clave.
        static List<Dictionary<string, double>> CartesianProduct(Dictionary<string, List<double>> lists)
        {
            var keys = lists.Keys.ToList();
            var result = new List<Dictionary<string, double>>();
            void Recurse(int k, Dictionary<string, double> partial)
            {
                if (k == keys.Count) { result.Add(new Dictionary<string, double>(partial)); return; }
                foreach (var v in lists[keys[k]])
                {
                    partial[keys[k]] = v;
                    Recurse(k + 1, partial);
                }
                partial.Remove(keys[k]);
            }
            Recurse(0, new Dictionary<string, double>());
            return result;
        }

        // Setter defensivo — prueba varios nombres/firmas que el SDK de Civil 3D
        // usa según la versión: Value property, SetValue(double), SelectValue(double).
        static void SetFieldValueRobust(PartsStyles.SizeFilterField campo, double v, Action<string> D)
        {
            var t = campo.GetType();
            // 1) property Value con setter
            var pValue = t.GetProperty("Value");
            if (pValue != null && pValue.CanWrite)
            {
                try
                {
                    object cast = pValue.PropertyType == typeof(double)
                        ? (object)v
                        : Convert.ChangeType(v, pValue.PropertyType);
                    pValue.SetValue(campo, cast);
                    return;
                }
                catch (Exception ex) { D($"        Value setter: {ex.Message}"); }
            }
            // 2) SetValue(double|object)
            foreach (var m in t.GetMethods().Where(m => m.Name == "SetValue"))
            {
                var pars = m.GetParameters();
                if (pars.Length != 1) continue;
                try
                {
                    object arg = pars[0].ParameterType == typeof(double)
                        ? (object)v
                        : Convert.ChangeType(v, pars[0].ParameterType);
                    m.Invoke(campo, new object[] { arg });
                    return;
                }
                catch { }
            }
            // 3) SelectValue(double) — para campos IsFromList
            var mSel = t.GetMethod("SelectValue", new[] { typeof(double) })
                       ?? t.GetMethod("SelectValue", new[] { typeof(object) });
            if (mSel != null)
            {
                try { mSel.Invoke(campo, new object[] { v }); return; }
                catch (Exception ex) { D($"        SelectValue: {ex.Message}"); }
            }
            D($"        (sin setter válido en SizeFilterField para valor {v})");
        }

        static string LocateFamilyXml(FamiliaItem item, Action<string> D)
        {
            // El nombre técnico del .xml suele ser Catalog_PartName (que a menudo
            // coincide con Description del PartFamily o con un basename). Recorremos
            // el catálogo configurado y buscamos un XML cuya PartName o PartDesc
            // coincida.
            string sysvar = item.Domain == CivilDB.DomainType.Pipe
                ? "AECCPIPECATALOG" : "AECCSTRUCTURECATALOG";
            string catRoot;
            try { catRoot = AcadApp.GetSystemVariable(sysvar) as string; }
            catch { return null; }
            if (string.IsNullOrEmpty(catRoot) || !Directory.Exists(catRoot)) return null;

            foreach (var xml in Directory.EnumerateFiles(catRoot, "*.xml", SearchOption.AllDirectories))
            {
                if (Path.GetFileName(xml).StartsWith("AecbIDrop", StringComparison.OrdinalIgnoreCase)) continue;
                if (Path.GetFileName(xml).Equals("AeccSharedPropertyLists.xml", StringComparison.OrdinalIgnoreCase)) continue;
                try
                {
                    var xdoc = new XmlDocument(); xdoc.Load(xml);
                    // Buscar Catalog_PartDesc y Catalog_PartName
                    var partDesc = xdoc.SelectSingleNode("//ColumnConst[@context='Catalog_PartDesc']")?.InnerText?.Trim();
                    var partName = xdoc.SelectSingleNode("//ColumnConst[@context='Catalog_PartName']")?.InnerText?.Trim();
                    if (string.Equals(partDesc, item.DisplayName, StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(partName, item.DisplayName, StringComparison.OrdinalIgnoreCase))
                        return xml;
                }
                catch { }
            }
            return null;
        }

        static T SafeGetProp<T>(object o, string name)
        {
            try
            {
                var p = o.GetType().GetProperty(name);
                if (p == null) return default;
                var v = p.GetValue(o);
                if (v == null) return default;
                return (T)Convert.ChangeType(v, typeof(T));
            }
            catch { return default; }
        }

        static string SaveLog(StringBuilder log)
        {
            try
            {
                string dir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string path = Path.Combine(dir,
                    $"PREPARAR_FAMILIAS_DEBUG_{DateTime.Now:yyyyMMdd-HHmmss}.txt");
                File.WriteAllText(path, log.ToString(), Encoding.UTF8);
                return path;
            }
            catch { return "(no pude guardar el log)"; }
        }

        // Wrapper defensivo — GetAvailablePartFamilies puede lanzar si el
        // catálogo está mal cargado. Loguea excepciones.
        static List<PartsStyles.DataPartFamily> SafeList(CivilDB.DomainType dom, Action<string> L)
        {
            try
            {
                var arr = PartsStyles.PartsList.GetAvailablePartFamilies(dom);
                return arr != null ? arr.ToList() : new List<PartsStyles.DataPartFamily>();
            }
            catch (Exception ex)
            {
                L($"    GetAvailablePartFamilies({dom}) excepción: {ex.Message}");
                return new List<PartsStyles.DataPartFamily>();
            }
        }
    }

    // Ítem del CheckedListBox — encapsula GUID + description + dominio.
    public class FamiliaItem : System.ComponentModel.INotifyPropertyChanged
    {
        public string Guid { get; }
        public string DisplayName { get; }
        public CivilDB.DomainType Domain { get; }
        public string DomainLabel => Domain == CivilDB.DomainType.Pipe ? "Tubería" : "Estructura";

        bool _checked;
        public bool IsChecked
        {
            get => _checked;
            set { _checked = value; PropertyChanged?.Invoke(this,
                    new System.ComponentModel.PropertyChangedEventArgs(nameof(IsChecked))); }
        }

        public FamiliaItem(PartsStyles.DataPartFamily f, CivilDB.DomainType dom)
        {
            Guid = f.GUID ?? "";
            DisplayName = string.IsNullOrEmpty(f.Description) ? f.GUID : f.Description;
            Domain = dom;
        }

        public event System.ComponentModel.PropertyChangedEventHandler PropertyChanged;
    }

    // Diálogo WPF ligero — un ListBox con checkboxes por familia.
    public class PrepararFamiliasWindow : Window
    {
        readonly ObservableCollection<FamiliaItem> _items;

        public PrepararFamiliasWindow(IEnumerable<FamiliaItem> items)
        {
            _items = new ObservableCollection<FamiliaItem>(items);
            Title = "Preparar familias — elige cuáles añadir a la lista de piezas";
            Width = 640; Height = 520;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            Background = System.Windows.Media.Brushes.WhiteSmoke;

            var grid = new Grid { Margin = new Thickness(12) };
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            var header = new TextBlock
            {
                Text = "Marca las familias personalizadas que quieres añadir. Por cada una se " +
                       "creará (o completará) una lista de piezas con el mismo nombre, con TODOS " +
                       "sus tamaños disponibles.",
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 8)
            };
            Grid.SetRow(header, 0); grid.Children.Add(header);

            var list = new ListBox
            {
                ItemsSource = _items,
                SelectionMode = System.Windows.Controls.SelectionMode.Single
            };
            list.ItemTemplate = BuildItemTemplate();
            Grid.SetRow(list, 1); grid.Children.Add(list);

            var botones = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(0, 10, 0, 0)
            };
            var btnTodo = new Button { Content = "Marcar todo", Width = 110, Margin = new Thickness(0, 0, 6, 0) };
            btnTodo.Click += (s, e) => { foreach (var i in _items) i.IsChecked = true; };
            var btnNada = new Button { Content = "Desmarcar todo", Width = 110, Margin = new Thickness(0, 0, 20, 0) };
            btnNada.Click += (s, e) => { foreach (var i in _items) i.IsChecked = false; };
            var btnOK = new Button { Content = "Preparar",   Width = 100, Margin = new Thickness(0, 0, 6, 0),
                                     IsDefault = true };
            btnOK.Click += (s, e) => { DialogResult = true; Close(); };
            var btnCa = new Button { Content = "Cancelar", Width = 100, IsCancel = true };
            botones.Children.Add(btnTodo); botones.Children.Add(btnNada);
            botones.Children.Add(btnOK);   botones.Children.Add(btnCa);
            Grid.SetRow(botones, 2); grid.Children.Add(botones);

            Content = grid;
        }

        static DataTemplate BuildItemTemplate()
        {
            var factory = new FrameworkElementFactory(typeof(DockPanel));
            var chk = new FrameworkElementFactory(typeof(CheckBox));
            chk.SetBinding(CheckBox.IsCheckedProperty,
                new Binding(nameof(FamiliaItem.IsChecked)) { Mode = BindingMode.TwoWay });
            chk.SetValue(CheckBox.MarginProperty, new Thickness(4, 3, 8, 3));
            factory.AppendChild(chk);
            var lbl = new FrameworkElementFactory(typeof(TextBlock));
            lbl.SetBinding(TextBlock.TextProperty, new Binding(nameof(FamiliaItem.DisplayName)));
            lbl.SetValue(TextBlock.MarginProperty, new Thickness(2, 3, 6, 3));
            factory.AppendChild(lbl);
            var tag = new FrameworkElementFactory(typeof(TextBlock));
            tag.SetBinding(TextBlock.TextProperty, new Binding(nameof(FamiliaItem.DomainLabel)));
            tag.SetValue(TextBlock.ForegroundProperty, System.Windows.Media.Brushes.Gray);
            tag.SetValue(TextBlock.FontStyleProperty, FontStyles.Italic);
            tag.SetValue(DockPanel.DockProperty, Dock.Right);
            factory.AppendChild(tag);
            return new DataTemplate { VisualTree = factory };
        }
    }

    // Diálogo "existe PartsList con ese nombre — ¿sobrescribir?"
    public class PregSobrescribirWindow : Window
    {
        public bool Sobreescribir { get; private set; }
        public bool AplicarATodos { get; private set; }

        public PregSobrescribirWindow(string nombre)
        {
            Title = "PartsList existente";
            Width = 480; Height = 200;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;

            var grid = new Grid { Margin = new Thickness(14) };
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            var txt = new TextBlock
            {
                Text = $"Ya existe una PartsList llamada '{nombre}'.\n\n¿Sobrescribirla (añadir " +
                       $"la familia dentro) o saltarla?",
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 12)
            };
            Grid.SetRow(txt, 0); grid.Children.Add(txt);

            var chk = new CheckBox { Content = "Aplicar la misma decisión a las siguientes",
                                     Margin = new Thickness(0, 0, 0, 12) };
            Grid.SetRow(chk, 1); grid.Children.Add(chk);

            var botones = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right
            };
            var btnOv = new Button { Content = "Sobrescribir", Width = 110, Margin = new Thickness(0, 0, 6, 0),
                                     IsDefault = true };
            btnOv.Click += (s, e) => { Sobreescribir = true;  AplicarATodos = chk.IsChecked == true; Close(); };
            var btnSk = new Button { Content = "Saltar", Width = 110, IsCancel = true };
            btnSk.Click += (s, e) => { Sobreescribir = false; AplicarATodos = chk.IsChecked == true; Close(); };
            botones.Children.Add(btnOv); botones.Children.Add(btnSk);
            Grid.SetRow(botones, 2); grid.Children.Add(botones);

            Content = grid;
        }
    }
}
