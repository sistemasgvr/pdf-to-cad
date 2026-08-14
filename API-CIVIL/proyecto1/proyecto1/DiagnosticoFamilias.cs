using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  DIAG_FAMILIAS — diagnóstico simple para saber si el catálogo custom está
//  cargado en Civil 3D. Usa el mismo enfoque del proyecto de referencia:
//  llamar a PartsList.GetAvailablePartFamilies (que lee del catálogo actualmente
//  configurado vía SETPIPENETWORKCATALOG). NO revisa ProgramData ni borra .apc.
//
//  Si el catálogo está vacío o solo trae stock, muestra las instrucciones
//  exactas para apuntar Civil 3D al catálogo custom con SETPIPENETWORKCATALOG.
//
//  Comando complementario: RESTAURAR_CATALOGO (recupera los .apc que hayan
//  sido borrados por versiones anteriores del plugin).
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosDiagnosticoFamilias
    {
        [CommandMethod("DIAG_FAMILIAS")]
        public void DiagFamilias()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            var sb = new StringBuilder();
            void W(string s) { ed.WriteMessage("\n" + s); sb.AppendLine(s); }

            W("═══════════════════════════════════════════════════════════════");
            W("  DIAGNÓSTICO DE FAMILIAS — Asistente C3D");
            W("═══════════════════════════════════════════════════════════════");
            W($"Fecha: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            W("");
            W("Este diagnóstico usa la MISMA API que Civil 3D usa internamente:");
            W("  PartsList.GetAvailablePartFamilies(dominio)");
            W("Esa API lee el catálogo actualmente configurado vía SETPIPENETWORKCATALOG.");
            W("");

            // 1) Detectar qué catálogo tiene configurado ESTE dibujo específico.
            //    SETPIPENETWORKCATALOG es un ajuste POR DIBUJO — si el usuario
            //    lo configuró en otro .dwg, este NO lo tiene.
            W("── CATÁLOGO ACTIVO EN ESTE DIBUJO ───────────────────────────────");
            W($"  Nombre del dibujo activo: {Path.GetFileName(doc.Name)}");
            W("  IMPORTANTE: SETPIPENETWORKCATALOG guarda su valor DENTRO del .dwg.");
            W("  Si configuraste el catálogo en otro dibujo, este no lo hereda.");
            W("");
            // Intentar leer los sysvars de catálogo si Civil 3D los expone
            try
            {
                object pipeCat = Application.GetSystemVariable("AECCPIPECATALOG");
                if (pipeCat != null) W($"  AECCPIPECATALOG = {pipeCat}");
            }
            catch { }
            try
            {
                object structCat = Application.GetSystemVariable("AECCSTRUCTURECATALOG");
                if (structCat != null) W($"  AECCSTRUCTURECATALOG = {structCat}");
            }
            catch { }
            W("");

            // 2) Enumerar familias disponibles del catálogo activo
            var visPipes  = ListAvailable(CivilDB.DomainType.Pipe);
            var visStrs   = ListAvailable(CivilDB.DomainType.Structure);

            W("── LO QUE VE CIVIL 3D DEL CATÁLOGO ACTIVO ──────────────────────");
            W($"  Tuberías (Pipe):      {visPipes.Count} familia(s)");
            W($"  Estructuras (Struct): {visStrs.Count} familia(s)");
            W("");

            if (visPipes.Count == 0 && visStrs.Count == 0)
            {
                W("  ❌ CATÁLOGO VACÍO. Civil 3D no encuentra ninguna familia.");
                W("");
                W("  Causa más común: no has ejecutado SETPIPENETWORKCATALOG para");
                W("  apuntar a la carpeta del catálogo (ni el stock ni el custom).");
                MostrarInstrucciones(W);
                Guardar(sb, ed); return;
            }

            // 2) Listar las familias visibles con marcadores custom / stock
            //    Heurística: si la Description contiene "Buzon" / "Bancoducto" /
            //    "Iluminacion" / "Banco de Tubos" → probable custom. Si no, stock.
            W("── FAMILIAS CUSTOM DETECTADAS (por keywords en Description) ─────");
            var pipesCustom  = FiltrarCustom(visPipes,  KW_PIPE);
            var strsCustom   = FiltrarCustom(visStrs,   KW_STRUCT);
            if (pipesCustom.Count > 0)
            {
                W($"  Pipe custom ({pipesCustom.Count}):");
                foreach (var d in pipesCustom) W($"    · {d}");
            }
            if (strsCustom.Count > 0)
            {
                W($"  Structure custom ({strsCustom.Count}):");
                foreach (var d in strsCustom) W($"    · {d}");
            }
            if (pipesCustom.Count == 0 && strsCustom.Count == 0)
            {
                W("  ⚠️ No se detectaron familias custom en el catálogo activo.");
                W("  El catálogo actual parece ser SOLO stock de Autodesk.");
                W("");
                W("  Si esperas ver tus buzones/bancoductos custom, aún NO has apuntado");
                W("  Civil 3D al catálogo custom que instalaste con la app Python.");
                MostrarInstrucciones(W);
            }
            else
            {
                W("");
                W("  ✓ Hay familias custom en el catálogo. Para usarlas en la Parts List");
                W("  del dibujo actual, ejecuta el comando: BB  (o AGREGAR_BANCOS_Y_BUZONES)");
            }

            // 3) Estado de la Parts List del dibujo activo
            W("");
            W("── PARTSLIST DEL DIBUJO ACTIVO ──────────────────────────────────");
            try
            {
                CivilDocument civilDoc = CivilApplication.ActiveDocument;
                using (Transaction tr = db.TransactionManager.StartTransaction())
                {
                    PartsStyles.PartsListCollection plc = civilDoc.Styles.PartsListSet;
                    W($"  PartsLists en el dibujo: {plc.Count}");
                    for (int i = 0; i < plc.Count; i++)
                    {
                        var pl = tr.GetObject(plc[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (pl == null) continue;
                        int nPipe = pl.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe).Count;
                        int nStr  = pl.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure).Count;
                        W($"    [{i}] '{pl.Name}'  ·  {nPipe} pipe family(s), {nStr} structure family(s)");
                    }
                    tr.Commit();
                }
            }
            catch (Exception ex) { W("  (No pude leer PartsLists: " + ex.Message + ")"); }

            Guardar(sb, ed);
        }

        // Palabras clave para detectar familias custom del proyecto de GVR
        // (mismos criterios que CatalogoBancos.cs del proyecto de referencia)
        static readonly string[] KW_PIPE = new[]
        {
            "bancoducto", "bancoductos",
            "banco de tubos", "bancos de tubos",
            "iluminacion", "iluminación"
        };
        static readonly string[] KW_STRUCT = new[] { "buzon", "buzón" };

        static List<string> FiltrarCustom(List<string> descs, string[] keywords)
        {
            var out_ = new List<string>();
            foreach (var d in descs)
            {
                if (string.IsNullOrEmpty(d)) continue;
                string lower = d.ToLowerInvariant();
                foreach (var k in keywords)
                    if (lower.Contains(k)) { out_.Add(d); break; }
            }
            return out_;
        }

        static List<string> ListAvailable(CivilDB.DomainType dom)
        {
            var descs = new List<string>();
            try
            {
                var disp = PartsStyles.PartsList.GetAvailablePartFamilies(dom);
                if (disp != null)
                    foreach (var d in disp)
                        descs.Add(d.Description ?? "");
            }
            catch { }
            return descs;
        }

        static void MostrarInstrucciones(Action<string> W)
        {
            W("");
            W("  ── CÓMO CARGAR UN CATÁLOGO CUSTOM ─────────────────────────");
            W("");
            W("  A) Instala el paquete de catálogo custom con la app Python:");
            W("     Herramientas → 'Instalar familia personalizada…'");
            W("     (elige la carpeta del modelador con .apc adentro).");
            W("");
            W("  B) En Civil 3D 2025, apunta al catálogo instalado:");
            W("     1. Cinta 'Inicio' → panel 'Crear diseño'");
            W("     2. 'Establecer catálogo de redes de tuberías'");
            W("        (o comando  SETPIPENETWORKCATALOG)");
            W("     3. Apunta a la CARPETA PADRE del catálogo (la que contiene");
            W("        'US Imperial Pipes' y 'US Imperial Structures' como hermanas):");
            W("        ej.  %APPDATA%\\AsistenteC3D\\Catalog\\");
            W("     4. Cierra y reabre el dibujo.");
            W("");
            W("  C) Ejecuta el comando  BB  para agregar las familias custom");
            W("     a la Parts List del dibujo actual.");
            W("");
            W("  D) Ejecuta DIAG_FAMILIAS otra vez para confirmar. Debe listar");
            W("     tus buzones/bancoductos.");
        }

        static void Guardar(StringBuilder sb, Editor ed)
        {
            try
            {
                string dir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string path = Path.Combine(dir, "AsistenteC3D_DIAG_FAMILIAS.txt");
                File.WriteAllText(path, sb.ToString(), Encoding.UTF8);
                ed.WriteMessage($"\n\nReporte guardado en: {path}");
            }
            catch (Exception ex) { ed.WriteMessage($"\n(No pude guardar el reporte: {ex.Message})"); }
        }

        // ─────────────────────────────────────────────────────────────
        //  RESTAURAR_CATALOGO — recupera los .apc borrados por versiones
        //  anteriores del plugin (que intentaban regenerar borrando el .apc).
        //  Escanea ProgramData\Autodesk\C3D *\* y por cada carpeta busca los
        //  .apc.backup-<hora>. Si el .apc está ausente, restaura el más reciente.
        // ─────────────────────────────────────────────────────────────
        [CommandMethod("RESTAURAR_CATALOGO")]
        public void RestaurarCatalogo()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            Editor ed = doc.Editor;
            void W(string s) { ed.WriteMessage("\n" + s); }

            W("═══ RESTAURAR CATÁLOGO desde backup ═══");
            string pd = Environment.GetEnvironmentVariable("ProgramData") ?? @"C:\ProgramData";
            string autodeskDir = Path.Combine(pd, "Autodesk");
            if (!Directory.Exists(autodeskDir)) { W("No hay carpeta Autodesk en ProgramData."); return; }
            int nRest = 0;
            foreach (var c3d in Directory.EnumerateDirectories(autodeskDir, "C3D *"))
            {
                foreach (var lang in Directory.EnumerateDirectories(c3d))
                {
                    string pipesCat = Path.Combine(lang, "Pipes Catalog");
                    if (!Directory.Exists(pipesCat)) continue;
                    foreach (var cat in Directory.EnumerateDirectories(pipesCat))
                        RestaurarUno(cat, W, ref nRest);
                }
            }
            W("");
            W($"Total .apc restaurados: {nRest}");
            W("Cierra y reabre Civil 3D para que se cargue el catálogo restaurado.");
        }

        static void RestaurarUno(string dir, Action<string> W, ref int nRest)
        {
            try
            {
                var backups = Directory.GetFiles(dir, "*.apc.backup-*");
                if (backups.Length == 0) return;
                var grupos = new Dictionary<string, string>();
                foreach (var b in backups)
                {
                    int i = b.IndexOf(".apc.backup-", StringComparison.OrdinalIgnoreCase);
                    if (i < 0) continue;
                    string apc = b.Substring(0, i + 4);
                    if (!grupos.ContainsKey(apc) ||
                        File.GetLastWriteTime(b) > File.GetLastWriteTime(grupos[apc]))
                        grupos[apc] = b;
                }
                foreach (var kv in grupos)
                {
                    string apc = kv.Key, backup = kv.Value;
                    if (File.Exists(apc))
                        W($"  {Path.GetFileName(apc)}: ya existe, no toco.");
                    else
                    {
                        File.Copy(backup, apc, overwrite: false);
                        nRest++;
                        W($"  Restaurado: {Path.GetFileName(apc)}  ←  {Path.GetFileName(backup)}");
                    }
                }
            }
            catch (Exception ex) { W($"  Error en {dir}: {ex.Message}"); }
        }
    }
}
