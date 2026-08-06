using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  Añade a la Parts List "Standard" todas las familias de las subcarpetas
//  personalizadas del catálogo imperial:
//    US Imperial Pipes\Bancoductos, \Bancos Tubos
//    US Imperial Structures\BuzonesElectricas
//
//  Comandos:
//    BB                       — alias corto, ejecuta la carga.
//    AGREGAR_BANCOS_Y_BUZONES — nombre largo, hace lo mismo.
//
//  Además, IMPORTAR_RED llama automáticamente a AddBancosYBuzones() al inicio.
// ============================================================================

namespace Civil3DBasico
{
    public class CatalogoBancos
    {
        // Palabras clave (case-insensitive) que identifican las familias objetivo.
        // No dependemos de resolver rutas de C:\ProgramData\Autodesk\C3D <año>.
        private static readonly string[] KW_PIPE = new[]
        {
            "bancoducto", "bancoductos",
            "banco de tubos", "bancos de tubos",
            "iluminacion", "iluminación"   // 'Iluminacion CBA' vive en Bancoductos
        };
        private static readonly string[] KW_STRUCT = new[] { "buzon", "buzón" };

        private static bool Matches(string desc, string[] keywords)
        {
            if (string.IsNullOrEmpty(desc)) return false;
            string d = desc.ToLowerInvariant();
            foreach (string k in keywords) if (d.Contains(k)) return true;
            return false;
        }

        [CommandMethod("BB")]
        public void BB() { AgregarBancosYBuzones(); }

        [CommandMethod("AGREGAR_BANCOS_Y_BUZONES")]
        public void AgregarBancosYBuzones()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    AddBancosYBuzones(tr, db, ed, verbose: true);
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
        //  Núcleo reutilizable: agrega las familias a la Parts List "Standard".
        //  Se llama con una transacción activa. `verbose=false` imprime solo un
        //  resumen (útil al llamarlo automáticamente desde IMPORTAR_RED).
        // =====================================================================
        public static void AddBancosYBuzones(Transaction tr, Database db, Editor ed, bool verbose)
        {
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // 1) Localizar la Parts List "Standard" (o la primera).
            PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
            if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists en el dibujo."); return; }
            ObjectId plId = plSet[0];
            for (int i = 0; i < plSet.Count; i++)
            {
                PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                if (p != null && string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase))
                { plId = plSet[i]; break; }
            }
            PartsStyles.PartsList partsList =
                (PartsStyles.PartsList)tr.GetObject(plId, OpenMode.ForWrite);
            if (verbose) ed.WriteMessage($"\n→ Parts List destino: '{partsList.Name}'");

            // 2) Recorrer los dos dominios (Pipe y Structure).
            int totalFams = 0, totalSizes = 0, totalYaEstaban = 0, totalNuevas = 0;
            var pares = new (CivilDB.DomainType dom, string[] kws, string tag)[]
            {
                (CivilDB.DomainType.Pipe,      KW_PIPE,   "Tubería"),
                (CivilDB.DomainType.Structure, KW_STRUCT, "Estructura")
            };

            foreach (var par in pares)
            {
                PartsStyles.DataPartFamily[] disp =
                    PartsStyles.PartsList.GetAvailablePartFamilies(par.dom);
                if (disp == null || disp.Length == 0)
                {
                    if (verbose) ed.WriteMessage($"\n[{par.tag}] catálogo vacío. ¿Seteaste el catálogo con 'Set Pipe Network Catalog'?");
                    continue;
                }

                var candidatas = new List<PartsStyles.DataPartFamily>();
                foreach (var f in disp) if (Matches(f.Description, par.kws)) candidatas.Add(f);
                if (verbose) ed.WriteMessage($"\n[{par.tag}] candidatas en catálogo: {candidatas.Count}");

                var yaPresentes = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                ObjectIdCollection ya = partsList.GetPartFamilyIdsByDomain(par.dom);
                foreach (ObjectId fid in ya)
                {
                    PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                    if (fam != null && !string.IsNullOrEmpty(fam.GUID)) yaPresentes.Add(fam.GUID);
                }

                foreach (var cand in candidatas)
                {
                    bool yaEstaba = yaPresentes.Contains(cand.GUID);
                    if (!yaEstaba)
                    {
                        try { partsList.AddPartFamilyByGuid(par.dom, cand.GUID); totalNuevas++; }
                        catch (Exception exA)
                        {
                            if (verbose) ed.WriteMessage($"\n  ✗ {cand.Description}: no se pudo añadir ({exA.Message})");
                            continue;
                        }
                    }
                    else totalYaEstaban++;

                    ObjectIdCollection famIds = partsList.GetPartFamilyIdsByDomain(par.dom);
                    int nSizes = 0;
                    foreach (ObjectId fid in famIds)
                    {
                        PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                        if (fam == null) continue;
                        if (!string.Equals(fam.GUID, cand.GUID, StringComparison.OrdinalIgnoreCase)) continue;
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
                        catch (Exception exS)
                        {
                            if (verbose) ed.WriteMessage($"\n  (tamaños de {cand.Description}: {exS.Message})");
                        }
                        nSizes = fam.PartSizeCount;
                        break;
                    }
                    totalFams++;
                    totalSizes += nSizes;
                    if (verbose)
                    {
                        string prefijo = yaEstaba ? "≡" : "+";
                        ed.WriteMessage($"\n  {prefijo} {cand.Description}  ({nSizes} tamaños)");
                    }
                }
            }

            if (verbose)
            {
                ed.WriteMessage($"\n\n✓ Listo. Familias procesadas: {totalFams} " +
                                $"(nuevas: {totalNuevas}, ya estaban: {totalYaEstaban}). " +
                                $"Tamaños totales: {totalSizes}.");
                ed.WriteMessage("\n  Revisa con LISTAR_PIEZAS y en la UI: 'Network Parts List'.");
            }
            else
            {
                ed.WriteMessage($"\n[Bancos/Buzones] +{totalNuevas} familias añadidas, " +
                                $"{totalYaEstaban} ya estaban ({totalSizes} tamaños en total).");
            }
        }
    }
}
