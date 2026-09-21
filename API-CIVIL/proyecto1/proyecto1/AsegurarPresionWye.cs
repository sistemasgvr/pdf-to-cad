using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Microsoft.Data.Sqlite;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;

// ============================================================================
//  Wye reales del catálogo Imperial_AWWA_Steel
//
//  Cuando la detección de junturas encuentra una unión Y (3 tuberías con
//  ángulos ~120°) el orquestador busca en la PressurePartList activa una
//  pieza `PressurePartType.Wye`. Si el usuario no cargó manualmente la
//  familia "Wye ..." del catálogo Imperial_AWWA_Steel en su PartsList,
//  esa búsqueda devuelve null y caemos a Tee. Aquí resolvemos eso: leemos
//  el .sqlite del catálogo, filtramos las familias con ID_TYPE=4 (wye) y
//  las agregamos a la PartsList vía PressurePartList.AddPart(GUID) —
//  el mismo API que usa la UI cuando el usuario tilda una familia.
//
//  Notas de implementación:
//    · La ruta del catálogo se resuelve por versión detectada (2027/26/25/24).
//    · El API AddPart de PressurePartList no está uniformemente expuesto en
//      todas las versiones; se llama por reflexión con manejo defensivo. Si
//      no está disponible, el fallback (Tee) se conserva y se avisa por
//      consola una única vez.
// ============================================================================

namespace Civil3DBasico
{
    internal static class AsegurarPresionWye
    {
        // Nombre del catálogo dentro de <ProgramData>\Autodesk\C3D <year>\enu\Pressure Pipes Catalog\Imperial\
        internal const string CATALOGO = "Imperial_AWWA_Steel";

        // Cache por sesión para no re-leer el SQLite cada juntura.
        private static List<(Guid famId, string famName, string desc, List<double> diams, int angle)> _wyeCache;
        private static bool _addPartTried, _addPartWorks;

        // Localiza el .sqlite del catálogo Imperial_AWWA_Steel probando TODAS
        // las combinaciones (versión × idioma) instaladas en la máquina.
        // El catálogo binario y sus GUIDs de PART_FAMILY_ID son idénticos entre
        // idiomas (verificado con C3D 2025 esp y C3D 2027 enu), así que
        // cualquier locale que exista sirve. Las carpetas de idioma son
        // subdirectorios directos de "C3D <year>" (ej. enu, esp, deu, fra,
        // ita, jpn, chs, cht, kor, plk, ptb, rus, csy...). Iterando por FS
        // no dependemos de una lista fija de códigos.
        //
        // Prioridad: primero se prefiere el LOCALE con el que la sesión de
        // Civil 3D está corriendo (LCID → carpeta) — así la ruta es la del
        // instalado del usuario, no una carpeta hermana que quizás tenga el
        // catálogo desactualizado —, y de fallback probamos todos los otros.
        internal static string LocalizarSqlite()
        {
            var pd = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            string autodeskRoot = Path.Combine(pd, "Autodesk");
            if (!Directory.Exists(autodeskRoot)) return null;
            // Orden de versión: la MÁS NUEVA instalada primero, para
            // aprovechar cualquier corrección de catálogo posterior.
            int[] years = new[] { 2027, 2026, 2025, 2024 };
            string prefLocale = LocaleActual();
            foreach (int year in years)
            {
                string yearDir = Path.Combine(autodeskRoot, $"C3D {year}");
                if (!Directory.Exists(yearDir)) continue;
                // 1) Preferir el idioma actual de C3D si esa subcarpeta existe.
                if (!string.IsNullOrEmpty(prefLocale))
                {
                    string cand = Path.Combine(yearDir, prefLocale,
                        $"Pressure Pipes Catalog\\Imperial\\{CATALOGO}.sqlite");
                    if (File.Exists(cand)) return cand;
                }
                // 2) Cualquier otra carpeta de idioma que exista bajo el año.
                foreach (string localeDir in Directory.GetDirectories(yearDir))
                {
                    string cand = Path.Combine(localeDir,
                        $"Pressure Pipes Catalog\\Imperial\\{CATALOGO}.sqlite");
                    if (File.Exists(cand)) return cand;
                }
            }
            return null;
        }

        // Locale-tag de la sesión actual de Civil 3D. Windows expone el LCID
        // del proceso vía CultureInfo — Autodesk usa 3 letras (enu/esp/deu/…)
        // que mapean así. Los planos del cliente pueden estar mezclados, pero
        // la sesión que ejecuta el plugin tiene UN SOLO idioma, y ese es el
        // que tiene el catálogo instalado. Devolvemos "" cuando no hay match
        // (el llamador cae a enumerar carpetas de idioma).
        private static string LocaleActual()
        {
            try
            {
                var lcid = System.Globalization.CultureInfo.InstalledUICulture.LCID;
                // Solo listamos los idiomas de Civil 3D que se distribuyen —
                // basta cubrir esp/enu para el usuario actual; el resto queda
                // como fallback por enumeración de carpetas.
                switch (lcid)
                {
                    case 0x0409: case 0x0009: return "enu"; // English
                    case 0x040A: case 0x0C0A: case 0x080A: case 0x000A: return "esp"; // Español
                    case 0x0407: case 0x0007: return "deu"; // Deutsch
                    case 0x040C: case 0x0007 + 5: return "fra"; // Français (0x040C)
                    case 0x0410: return "ita";  // Italiano
                    case 0x0411: return "jpn";  // 日本語
                    case 0x0804: return "chs";  // 简体中文
                    case 0x0404: return "cht";  // 繁體中文
                    case 0x0412: return "kor";  // 한국어
                    case 0x0415: return "plk";  // Polski
                    case 0x0416: return "ptb";  // Português (BR)
                    case 0x0419: return "rus";  // Русский
                    case 0x0405: return "csy";  // Čeština
                }
            }
            catch { }
            return "";
        }

        // Lee todas las familias Wye del catálogo — una entrada por familia
        // (no por tamaño): PART_FAMILY_ID es lo que consume AddPart(). Cada
        // familia también trae el conjunto de diámetros disponibles y el
        // ángulo (parseado del nombre "Wye 30_ BV_ ..."), para elegir en
        // frío la que mejor calza con la juntura.
        internal static List<(Guid famId, string famName, string desc, List<double> diams, int angle)> LeerWyes()
        {
            if (_wyeCache != null) return _wyeCache;
            var lista = new List<(Guid, string, string, List<double>, int)>();
            string sqlite = LocalizarSqlite();
            if (sqlite == null) { _wyeCache = lista; return lista; }
            try
            {
                var cs = new SqliteConnectionStringBuilder
                { DataSource = sqlite, Mode = SqliteOpenMode.ReadOnly }.ToString();
                using var conn = new SqliteConnection(cs);
                conn.Open();
                // ID_TYPE = 4 = "wye" en WA_BRANCH_FITTING_TYPE_TBD.
                using var cmd = conn.CreateCommand();
                cmd.CommandText = @"SELECT PART_FAMILY_ID, PART_FAMILY_NAME, DESCRIPTION, DIAMETER_NOMINAL
                                    FROM WA_BRANCH_FITTING_MODEL WHERE ID_TYPE = 4";
                var porFam = new Dictionary<Guid, (string name, string desc, HashSet<double> diams)>();
                using (var rd = cmd.ExecuteReader())
                {
                    while (rd.Read())
                    {
                        string gs = rd.IsDBNull(0) ? "" : rd.GetString(0);
                        if (!Guid.TryParse(gs, out Guid g)) continue;
                        string fn = rd.IsDBNull(1) ? "" : rd.GetString(1);
                        string dsc = rd.IsDBNull(2) ? "" : rd.GetString(2);
                        string dn = rd.IsDBNull(3) ? "" : rd.GetString(3);
                        var diams = ExtraerDiams(dn);
                        if (!porFam.TryGetValue(g, out var acc))
                        { acc = (fn, dsc, new HashSet<double>()); porFam[g] = acc; }
                        foreach (var d in diams) acc.diams.Add(d);
                    }
                }
                foreach (var kv in porFam)
                {
                    int ang = ExtraerAngulo(kv.Value.name);
                    lista.Add((kv.Key, kv.Value.name, kv.Value.desc,
                               kv.Value.diams.OrderBy(x => x).ToList(), ang));
                }
            }
            catch { }
            _wyeCache = lista;
            return lista;
        }

        // Asegura que la PartsList activa tenga cargadas TODAS las familias Wye
        // del catálogo Imperial_AWWA_Steel. Idempotente: si la familia ya
        // aparece entre los fittings actuales, no la vuelve a agregar. Devuelve
        // el número de familias nuevas realmente agregadas.
        internal static int AsegurarEnPartsList(PresStyles.PressurePartList pl,
            List<PresStyles.PressurePartSize> fittingsExistentes, Editor ed)
        {
            var wyes = LeerWyes();
            if (wyes.Count == 0) return 0;
            // Set de familias que ya están en la lista (por descripción, que en
            // catálogos AWWA incluye el nombre de familia como sufijo). Es una
            // heurística conservadora: si algo huele a "Wye N_" ya está.
            var existentes = new HashSet<string>(
                (fittingsExistentes ?? new List<PresStyles.PressurePartSize>())
                    .Where(f => f.PartType == CivilDB.PressurePartType.Wye)
                    .Select(f => (f.Description ?? "").ToLowerInvariant()),
                StringComparer.OrdinalIgnoreCase);
            int agregadas = 0;
            var mi = ResolverAddPart(pl);
            if (mi == null)
            {
                if (!_addPartTried)
                {
                    _addPartTried = true;
                    ed?.WriteMessage("\n  ⚠ Wye AWWA Steel: esta versión de Civil 3D no expone AddPart en la PressurePartList — no se puede cargar automáticamente. Añade las familias manualmente (Prospector → Parts Lists → Wye ... AWWA C208).");
                }
                return 0;
            }
            _addPartTried = true; _addPartWorks = true;
            try { pl.UpgradeOpen(); } catch { }
            foreach (var w in wyes)
            {
                // Si al menos UN Wye con el nombre de la familia ya está, saltamos.
                bool ya = existentes.Any(k => k.Contains(w.famName.ToLowerInvariant())) ||
                          existentes.Any(k => k.Contains(w.desc.ToLowerInvariant()));
                if (ya) continue;
                try
                {
                    mi.Invoke(pl, new object[] { w.famId });
                    agregadas++;
                    ed?.WriteMessage($"\n  · Wye cargada: '{w.famName}' ({w.diams.Count} diámetros).");
                }
                catch (Exception ex)
                {
                    ed?.WriteMessage($"\n  ⚠ No se pudo agregar Wye '{w.famName}': {ex.InnerException?.Message ?? ex.Message}");
                }
            }
            return agregadas;
        }

        // Busca por reflexión un método AddPart en PressurePartList que acepte
        // un Guid — el nombre exacto y sobrecargas varían entre versiones de
        // AeccPressurePipesMgd.dll (2025/26/27 tienen firmas ligeramente
        // distintas). Aceptamos la primera sobrecarga que compile con (Guid,).
        private static MethodInfo ResolverAddPart(PresStyles.PressurePartList pl)
        {
            if (pl == null) return null;
            var t = pl.GetType();
            foreach (string nombre in new[] { "AddPart", "AddParts", "AddPartByGuid" })
            {
                var mm = t.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                    .Where(m => m.Name == nombre).ToList();
                foreach (var m in mm)
                {
                    var ps = m.GetParameters();
                    if (ps.Length == 1 && ps[0].ParameterType == typeof(Guid))
                        return m;
                }
            }
            return null;
        }

        internal static List<double> ExtraerDiams(string dnStr)
        {
            var r = new List<double>();
            if (string.IsNullOrEmpty(dnStr)) return r;
            foreach (var p in System.Text.RegularExpressions.Regex.Split(dnStr, @"\s*x\s*"))
            {
                var mm = System.Text.RegularExpressions.Regex.Match(p.Trim(), @"([\d.]+)");
                if (mm.Success && double.TryParse(mm.Groups[1].Value, NumberStyles.Float,
                        CultureInfo.InvariantCulture, out double d))
                    r.Add(d);
            }
            return r;
        }

        internal static int ExtraerAngulo(string nombre)
        {
            if (string.IsNullOrEmpty(nombre)) return 0;
            var m = System.Text.RegularExpressions.Regex.Match(nombre, @"Wye\s*(\d{1,3})",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (m.Success && int.TryParse(m.Groups[1].Value, out int a)) return a;
            return 0;
        }
    }
}
