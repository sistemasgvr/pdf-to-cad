using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  PREPARAR_FAMILIAS_STEP2  (botón "⚙️ Preparar familias para dibujar")
//  ---------------------------------------------------------------------------
//  100% automático, sin diálogo de selección:
//
//    1) Escanea el modelspace del dibujo actual buscando el XDATA "PDFCAD" que
//       exporta la app Python en cada tubería/buzón (PIPE_FAMILY=.../PART=...,
//       el mismo texto de Description que usa Civil3D — ver _resolve_family en
//       app/dxf_export.py). Junta el conjunto de nombres de familia realmente
//       usados en ESTE proyecto.
//    2) De esos nombres, descarta los que son de fábrica (Autodesk) usando el
//       mismo filtro de palabras clave que ya usa el resto del plugin para
//       distinguir familias custom del proyecto GVR — ComandosRedes.
//       EsFamiliaCustomPipe/EsFamiliaCustomStruct (RedesTuberia.cs) — así solo
//       se procesan las familias "nuevas" que de verdad necesitan tamaños.
//    3) Para cada una: la añade a la Parts List "Standard" del dibujo (si no
//       estaba) y le agrega TODOS los tamaños que resultan de variar Inner
//       Pipe Width × Inner Pipe Height (tuberías) o Inner Structure Width ×
//       Inner Structure Length (estructuras) — el mismo resultado que el
//       flujo manual: Redes de tuberías → Lista de piezas → Estándar → clic
//       derecho en la familia → Añadir tamaño de pieza → tildar "todos los
//       tamaños" en esos 2 parámetros → Aceptar. El resto de parámetros
//       (marco, pared, losa, altura, etc.) quedan en su valor por defecto.
//
//  Si el dibujo no tiene XDATA "PDFCAD" (el DXF de Python no se insertó/abrió
//  todavía) o el catálogo de Civil3D no tiene ninguna familia cargada, se
//  avisa con un mensaje claro y no se toca el dibujo.
//
//  Comando registrado en:  Civil3DBasico.ComandosPrepararFamilias
//    - PREPARAR_FAMILIAS         → alternativa manual: regenera catálogo
//      (_PARTCATALOGREGEN Pipe/Structure) y encadena STEP2. Solo hace falta
//      tras instalar una familia nueva en esta misma sesión de Civil3D — el
//      botón del panel llama a STEP2 directo porque el diálogo de
//      PARTCATALOGREGEN no siempre deja encadenar el siguiente comando.
//    - PREPARAR_FAMILIAS_STEP2   → el comando real (botón del panel apunta acá).
//
//  Clases del SDK Civil 3D usadas:
//    - PartsStyles.PartsList.GetAvailablePartFamilies(DomainType)  → enumera
//      familias del catálogo actualmente activo (Pipe o Structure).
//    - CivilDocument.Styles.PartsListSet  → colección de PartsLists del dibujo;
//      se usa siempre la llamada "Standard" (o se crea si no existe ninguna).
//    - PartsList.AddPartFamilyByGuid(dom, guid)   → añade la family.
//    - PartsList.GetPartFamilyIdsByDomain(dom)    → ids de families ya presentes.
//    - SizeFilterField.Context (PartContextType)  → identifica el parámetro
//      real (PipeInnerWidth/PipeInnerHeight/StructInnerWidth/StructInnerLength),
//      confirmado por reflexión sobre AeccDbMgd.dll — es el MISMO nombre que
//      usa el atributo `context` en el XML del catálogo que lee el lado Python
//      (app/civil_catalog.py), así que ambos lados apuntan a los mismos 2
//      parámetros por diseño.
//    - PartFamily.AddPartSize(SizeFilterRecord)   → añade tamaños; UN
//      AddPartSize POR combinación real (confirmado con log real de un
//      dibujo: NO expande el producto cartesiano solo, ni con
//      IsMultipleSelect=true — ver AddTamanosPorAnchoYAlto más abajo).
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
                MessageBox.Show(
                    "PARTCATALOGREGEN no completó — no encontré ninguna familia en el catálogo.\n\n" +
                    "Ejecuta el comando '_PARTCATALOGREGEN' manualmente (una vez para Pipe, otra para " +
                    "Structure) y vuelve a intentar.",
                    "Preparar familias",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            // 2) Detectar automáticamente qué familias usa ESTE dibujo, leyendo el
            //    XDATA "PDFCAD" que exportó la app Python (PIPE_FAMILY=/PART=,
            //    el texto real de Description) — y quedarnos solo con las que NO
            //    son de fábrica (EsFamiliaCustomPipe/Struct).
            var usadasPipe = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var usadasStruct = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int nEntidadesPdfcad = 0;
            using (var trScan = db.TransactionManager.StartTransaction())
            {
                var ms = trScan.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead) as BlockTableRecord;
                foreach (ObjectId eid in ms)
                {
                    var ent = trScan.GetObject(eid, OpenMode.ForRead) as Entity;
                    if (ent == null) continue;
                    var xd = LeerXdataPdfcadLite(ent);
                    if (xd == null) continue;
                    nEntidadesPdfcad++;
                    xd.TryGetValue("_MARKER", out string marker);
                    if (marker == "PDFCAD_PIPE" && xd.TryGetValue("PIPE_FAMILY", out string pf) && !string.IsNullOrWhiteSpace(pf))
                        usadasPipe.Add(pf.Trim());
                    else if (marker == "PDFCAD_STRUCT" && xd.TryGetValue("PART", out string pa) && !string.IsNullOrWhiteSpace(pa))
                        usadasStruct.Add(pa.Trim());
                }
                trScan.Commit();
            }
            D($"      Entidades con XDATA PDFCAD encontradas: {nEntidadesPdfcad}");
            D($"      Nombres de familia de tubería referenciados: [{string.Join(", ", usadasPipe)}]");
            D($"      Nombres de familia de estructura referenciados: [{string.Join(", ", usadasStruct)}]");

            var seleccionadas = new List<FamiliaItem>();
            foreach (var f in pipes)
                if (usadasPipe.Contains((f.Description ?? "").Trim()) && ComandosRedes.EsFamiliaCustomPipe(f.Description))
                    seleccionadas.Add(new FamiliaItem(f, CivilDB.DomainType.Pipe));
            foreach (var f in structs)
                if (usadasStruct.Contains((f.Description ?? "").Trim()) && ComandosRedes.EsFamiliaCustomStruct(f.Description))
                    seleccionadas.Add(new FamiliaItem(f, CivilDB.DomainType.Structure));

            if (seleccionadas.Count == 0)
            {
                MessageBox.Show(
                    nEntidadesPdfcad == 0
                        ? "No encontré tuberías/buzones con datos de Python (XDATA 'PDFCAD') en el dibujo " +
                          "actual. Abre/inserta primero el DXF exportado desde la app y vuelve a intentar."
                        : "El dibujo referencia familias, pero ninguna parece personalizada (nueva) — " +
                          "las que sí uses del catálogo estándar de Civil3D ya traen sus tamaños de fábrica, " +
                          "no hace falta añadir nada.",
                    "Preparar familias", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }
            L(""); L($"→ Familias personalizadas detectadas en el dibujo: {seleccionadas.Count}");
            foreach (var it in seleccionadas)
                L($"    · [{it.DomainLabel}] {it.DisplayName}");

            // 3) Procesar cada familia dentro de una única transacción — todo va a
            //    la Parts List "Standard" (igual que el flujo manual), no a una
            //    lista nueva por familia.
            int totalFams = 0, totalSizes = 0;
            var errores = new List<string>();

            using (var tr = db.TransactionManager.StartTransaction())
            {
                CivilDocument civilDoc;
                try { civilDoc = CivilApplication.ActiveDocument; }
                catch (Exception ex)
                {
                    L($"✗ No hay Civil Document activo: {ex.Message}");
                    tr.Abort(); return;
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

                ObjectId plId;
                if (plSet.Count == 0)
                {
                    L("  + No hay ninguna Parts List en el dibujo — creando 'Standard'.");
                    plId = plSet.Add("Standard");
                }
                else
                {
                    plId = plSet[0];
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        var p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (p != null && string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase))
                        { plId = plSet[i]; break; }
                    }
                }
                var partsList = tr.GetObject(plId, OpenMode.ForWrite) as PartsStyles.PartsList;
                if (partsList == null)
                {
                    L("✗ No pude abrir la Parts List destino.");
                    tr.Abort(); return;
                }
                L($"→ Parts List destino: '{partsList.Name}'");

                foreach (var item in seleccionadas)
                {
                    string nombreFam = item.DisplayName;
                    L("");
                    L($"─── Procesando '{nombreFam}' [{item.DomainLabel}] ───");
                    D($"    GUID = {item.Guid}");

                    try
                    {
                        // a) Añadir la Part Family a "Standard" (si no está ya).
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
                        else L("  ≡ Familia ya estaba dentro de 'Standard'.");

                        // b) Localizar el PartFamily recién añadido
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

                        // c) Añadir todos los tamaños variando SOLO Inner Width/Height
                        //    (tubería) o Inner Width/Length (estructura) — equivale
                        //    exactamente al checkbox "Añadir todos los tamaños" del
                        //    diálogo manual, marcado solo en esos 2 parámetros.
                        int nAgregados = AddTamanosPorAnchoYAlto(famNew, item.Domain, L, D);

                        int nSizesDespues = famNew.PartSizeCount;
                        L($"  · PartSizeCount DESPUÉS: {nSizesDespues}  (Δ = {nAgregados})");

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
            Guardar(log, ed);

            var msg = $"Familias procesadas en 'Standard': {totalFams}\n" +
                      $"Tamaños añadidos en total: {totalSizes}" +
                      (errores.Count > 0 ? "\n\nCon errores — revisa la línea de comandos de Civil3D." : "");
            MessageBox.Show(msg, "Preparar familias — resumen",
                MessageBoxButton.OK,
                errores.Count > 0 ? MessageBoxImage.Warning : MessageBoxImage.Information);
        }

        // Vuelca el log completo (incluye las líneas D(), que no se muestran en
        // pantalla) al Desktop — mismo patrón que DiagnosticoFamilias.cs. Antes
        // el StringBuilder se llenaba pero nunca se escribía a disco: los
        // valores reales de PipeInnerWidth/Height (o StructInnerWidth/Length)
        // que lee AddTamanosPorAnchoYAlto directo del SDK se perdían, aunque
        // son justo el dato que hace falta para comparar contra los tamaños
        // que muestra el desplegable de la app Python (civil_catalog.py).
        static void Guardar(StringBuilder log, Editor ed)
        {
            try
            {
                string dir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string path = Path.Combine(dir, "AsistenteC3D_PREPARAR_FAMILIAS.txt");
                File.WriteAllText(path, log.ToString(), Encoding.UTF8);
                ed.WriteMessage($"\n\nLog completo guardado en: {path}");
            }
            catch (Exception ex) { ed.WriteMessage($"\n(No pude guardar el log: {ex.Message})"); }
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
        //  AddTamanosPorAnchoYAlto
        //  IMPORTANTE (confirmado con log real de un dibujo, no solo lectura de
        //  API): AddPartSize NO expande un producto cartesiano por sí solo, ni
        //  aunque se marque IsMultipleSelect=true en los 2 campos objetivo —
        //  cada llamada añade EXACTAMENTE la combinación que tengan puesta los
        //  campos .Value en ese momento. IsMultipleSelect es solo metadata para
        //  la UI del diálogo manual (que internamente sí itera y llama
        //  AddPartSize una vez por cada combinación marcada).
        //
        //  Por eso replicamos ese mismo bucle: leemos con .ValueList el listado
        //  REAL de valores que Civil 3D acepta para Inner Pipe Width/Height (o
        //  Inner Structure Width/Length) directamente del SDK — sin tocar
        //  ningún XML de catálogo — y llamamos AddPartSize una vez por cada
        //  combinación (Width_i, Height_j). Equivale exactamente a tildar
        //  "añadir todos los tamaños" en esos 2 parámetros y aceptar.
        //  Devuelve el número de PartSize nuevos (delta de PartSizeCount).
        // =====================================================================
        static int AddTamanosPorAnchoYAlto(PartsStyles.PartFamily fam, CivilDB.DomainType domain,
                                             Action<string> L, Action<string> D)
        {
            CivilDB.PartContextType ctxA, ctxB;
            if (domain == CivilDB.DomainType.Pipe)
            {
                ctxA = CivilDB.PartContextType.PipeInnerWidth;
                ctxB = CivilDB.PartContextType.PipeInnerHeight;
            }
            else
            {
                ctxA = CivilDB.PartContextType.StructInnerWidth;
                ctxB = CivilDB.PartContextType.StructInnerLength;
            }

            // 1) Leer del SDK la lista real de valores de cada campo objetivo.
            var filtroRef = new PartsStyles.SizeFilterRecord(fam);
            // Diagnóstico: el fix de fijar "cualquier otro campo tipo lista a su
            // primer valor" (ver más abajo) NO evitó que 56 combinaciones sigan
            // generando 112 tamaños — significa que la causa NO es (solo) un
            // tercer eje tipo ValueList sin fijar, o que fijar .Value no evita
            // que AddPartSize lo expanda igual. Se listan TODOS los campos con
            // su IsFromList/IsReadOnly/ValueList.Count para encontrar cuál es.
            D($"      -- TODOS los campos de '{fam.Description}' --");
            for (int i = 0; i < filtroRef.ParamCount; i++)
            {
                var c = filtroRef[i];
                if (c == null) { D($"        [{i}] (null)"); continue; }
                int vc = -1;
                try { vc = c.IsFromList ? c.ValueList.Count : -1; } catch { vc = -2; }
                D($"        [{i}] Context={c.Context}  IsFromList={c.IsFromList}  " +
                  $"IsReadOnly={c.IsReadOnly}  ValueList.Count={vc}  Value={c.Value}");
            }
            List<object> valoresA = null, valoresB = null;
            for (int i = 0; i < filtroRef.ParamCount; i++)
            {
                var campo = filtroRef[i];
                if (campo == null || campo.IsReadOnly || !campo.IsFromList) continue;
                if (campo.Context == ctxA)
                {
                    valoresA = new List<object>();
                    for (int k = 0; k < campo.ValueList.Count; k++) valoresA.Add(campo.ValueList[k]);
                }
                else if (campo.Context == ctxB)
                {
                    valoresB = new List<object>();
                    for (int k = 0; k < campo.ValueList.Count; k++) valoresB.Add(campo.ValueList[k]);
                }
            }
            if (valoresA == null || valoresB == null)
            {
                L($"  ⚠ No encontré los campos {ctxA}/{ctxB} en esta familia — no se añaden tamaños.");
                return 0;
            }
            D($"      {ctxA}: {valoresA.Count} valores [{string.Join(", ", valoresA)}]");
            D($"      {ctxB}: {valoresB.Count} valores [{string.Join(", ", valoresB)}]");
            // Línea de una sola pieza, fácil de diffear a mano contra la salida
            // de civil_catalog.raw_size_axes() del lado Python — mismos valores
            // crudos leídos del SDK (no el Name calculado del PartSize).
            D($"COMPARAR|{fam.Description}|{ctxA}={string.Join(",", valoresA)}|{ctxB}={string.Join(",", valoresB)}");
            L($"  · {valoresA.Count} × {valoresB.Count} = {valoresA.Count * valoresB.Count} combinaciones a intentar.");

            // 2) Un AddPartSize por combinación (Width_i, Height_j / Width_i, Length_j).
            int before = fam.PartSizeCount;
            int nFallos = 0;
            int nCombo = 0;
            foreach (var va in valoresA)
            {
                foreach (var vb in valoresB)
                {
                    nCombo++;
                    int antesDeEsta = fam.PartSizeCount;
                    try
                    {
                        var filtro = new PartsStyles.SizeFilterRecord(fam);
                        for (int i = 0; i < filtro.ParamCount; i++)
                        {
                            var campo = filtro[i];
                            if (campo == null) continue;
                            // IsMultipleSelect=false en TODOS los campos que se van a fijar
                            // a un solo valor — visto en otro lado del plugin (RedesTuberia.cs,
                            // técnica inversa: IsMultipleSelect=true SÍ hace que AddPartSize
                            // expanda un campo solo) que este flag sí influye en el SDK, pese
                            // al comentario de arriba que decía lo contrario para ctxA/ctxB.
                            // Diagnóstico confirmó 'Material' con 8 valores en la familia de
                            // tubería (única familia que duplicaba x2, ninguna estructura) —
                            // sospecha directa de que su IsMultipleSelect seguía en true.
                            if (campo.Context == ctxA) { campo.IsMultipleSelect = false; campo.Value = va; }
                            else if (campo.Context == ctxB) { campo.IsMultipleSelect = false; campo.Value = vb; }
                            else if (!campo.IsReadOnly && campo.IsFromList && campo.ValueList.Count > 0)
                            {
                                campo.IsMultipleSelect = false;
                                campo.Value = campo.ValueList[0];
                            }
                        }
                        fam.AddPartSize(filtro);
                    }
                    catch (Exception ex)
                    {
                        nFallos++;
                        D($"      combo ({va}, {vb}) AddPartSize excepción: {ex.Message}");
                    }
                    // Diagnóstico fino: cuántos PartSize agregó ESTA llamada en concreto
                    // (solo las primeras 3 — el fix de fijar el 3er eje a ValueList[0]
                    // NO evitó que 56 combinaciones sigan generando 112 tamaños, así que
                    // hay que ver si una sola llamada ya agrega más de uno).
                    if (nCombo <= 3)
                    {
                        int deltaEsta = fam.PartSizeCount - antesDeEsta;
                        D($"      combo #{nCombo} ({va}, {vb}): PartSizeCount {antesDeEsta} → {fam.PartSizeCount}  (+{deltaEsta})");
                    }
                }
            }
            int delta = fam.PartSizeCount - before;
            L($"  ✓ Tamaños añadidos: {delta} de {valoresA.Count * valoresB.Count} combinaciones " +
              $"(variando {ctxA} × {ctxB}){(nFallos > 0 ? $"  |  fallos/duplicados: {nFallos}" : "")}");
            return delta;
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

        // Lectura mínima del XDATA "PDFCAD" — solo lo que hace falta acá
        // (_MARKER + PIPE_FAMILY/PART). Réplica reducida de LeerXdataPdfcad en
        // ImportarRed.cs (archivo separado, mismo patrón ya usado en el resto
        // del plugin para helpers chicos duplicados por archivo).
        static Dictionary<string, string> LeerXdataPdfcadLite(Entity ent)
        {
            ResultBuffer xdata;
            try { xdata = ent.GetXDataForApplication("PDFCAD"); }
            catch { return null; }
            if (xdata == null) return null;
            var dict = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (TypedValue tv in xdata)
            {
                if (tv.TypeCode != 1000) continue;
                string s = tv.Value?.ToString() ?? "";
                if (s == "PDFCAD_PIPE" || s == "PDFCAD_STRUCT") { dict["_MARKER"] = s; continue; }
                int eq = s.IndexOf('=');
                if (eq > 0) dict[s.Substring(0, eq)] = s.Substring(eq + 1);
            }
            return dict.ContainsKey("_MARKER") ? dict : null;
        }
    }

    // Familia detectada como "nueva"/personalizada en el dibujo actual.
    public class FamiliaItem
    {
        public string Guid { get; }
        public string DisplayName { get; }
        public CivilDB.DomainType Domain { get; }
        public string DomainLabel => Domain == CivilDB.DomainType.Pipe ? "Tubería" : "Estructura";

        public FamiliaItem(PartsStyles.DataPartFamily f, CivilDB.DomainType dom)
        {
            Guid = f.GUID ?? "";
            DisplayName = string.IsNullOrEmpty(f.Description) ? f.GUID : f.Description;
            Domain = dom;
        }
    }
}
