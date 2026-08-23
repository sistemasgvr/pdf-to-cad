using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace Civil3DBasico
{
    /// <summary>
    /// Detecta y llena gaps en los catálogos SQLite de Pressure Pipes de Civil 3D.
    /// Para cada diámetro de tubería que no tiene accesorios, clona el registro del
    /// tamaño más cercano y escala las dimensiones geométricas proporcionalmente.
    /// Idempotente: si ya no hay gaps, no modifica nada.
    /// </summary>
    public static class PressureCatalogFiller
    {
        static readonly string[] FittingTables = {
            "WA_ELBOW_MODEL",
            "WA_BRANCH_FITTING_MODEL",
            "WA_FITTING_MODEL"
        };

        public static string FindCatalogRoot()
        {
            var programData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            foreach (int year in new[] { 2026, 2025, 2024 })
            {
                foreach (string unit in new[] { "Imperial", "Metric" })
                {
                    string path = Path.Combine(programData, $"Autodesk\\C3D {year}\\enu\\Pressure Pipes Catalog\\{unit}");
                    if (Directory.Exists(path))
                        return path;
                }
            }
            return null;
        }

        public static List<string> FindAllCatalogRoots()
        {
            var roots = new List<string>();
            var programData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            foreach (int year in new[] { 2024, 2025, 2026 })
            {
                foreach (string unit in new[] { "Imperial", "Metric" })
                {
                    string path = Path.Combine(programData, $"Autodesk\\C3D {year}\\enu\\Pressure Pipes Catalog\\{unit}");
                    if (Directory.Exists(path))
                        roots.Add(path);
                }
            }
            return roots;
        }

        /// <summary>
        /// Procesa todos los catálogos en una raíz. Devuelve (catálogos procesados, registros creados).
        /// </summary>
        public static (int catalogs, int records) FillAllGaps(string catalogRoot, Action<string> log = null)
        {
            if (!Directory.Exists(catalogRoot))
                return (0, 0);

            var sqliteFiles = Directory.GetFiles(catalogRoot, "*.sqlite");
            int totalCatalogs = 0, totalRecords = 0;

            foreach (var dbPath in sqliteFiles)
            {
                int n = ProcessCatalog(dbPath, log);
                if (n > 0)
                {
                    totalCatalogs++;
                    totalRecords += n;
                }
            }
            return (totalCatalogs, totalRecords);
        }

        /// <summary>
        /// Procesa todos los catálogos de todas las versiones instaladas.
        /// </summary>
        public static (int catalogs, int records) FillAllGapsAllVersions(Action<string> log = null)
        {
            int tc = 0, tr = 0;
            foreach (var root in FindAllCatalogRoots())
            {
                log?.Invoke($"  Raíz: {root}");
                var (c, r) = FillAllGaps(root, log);
                tc += c;
                tr += r;
            }
            return (tc, tr);
        }

        static int ProcessCatalog(string dbPath, Action<string> log)
        {
            string name = Path.GetFileName(dbPath);

            try
            {
                var connStr = new SqliteConnectionStringBuilder
                {
                    DataSource = dbPath,
                    Mode = SqliteOpenMode.ReadWrite
                }.ToString();

                using var conn = new SqliteConnection(connStr);
                conn.Open();

                var pipeDiams = GetPipeDiams(conn);
                var allFittingDiams = GetAllFittingDiams(conn);
                var missing = pipeDiams.Except(allFittingDiams).OrderBy(d => d).ToList();

                if (missing.Count == 0)
                    return 0;

                log?.Invoke($"  {name}: {missing.Count} gaps → llenando...");

                var pipeDims = GetPipeDims(conn);
                var fittingDims = GetFittingDims(conn);
                int fidCounter = GetMaxFid(conn) + 100;
                int totalCreated = 0;

                using var transaction = conn.BeginTransaction();

                foreach (var table in FittingTables)
                {
                    var families = GetFamilies(conn, table);
                    foreach (var fam in families)
                    {
                        var existing = GetExistingDiams(conn, table, fam);
                        foreach (var diam in missing)
                        {
                            if (existing.Contains(diam))
                                continue;
                            int n;
                            (fidCounter, n) = CreateFittingForSize(conn, table, fam, diam,
                                pipeDims, fittingDims, fidCounter);
                            totalCreated += n;
                        }
                    }
                }

                if (totalCreated > 0)
                    transaction.Commit();
                else
                    transaction.Rollback();

                if (totalCreated > 0)
                    log?.Invoke($"  {name}: {totalCreated} registros creados");

                return totalCreated;
            }
            catch (Exception ex)
            {
                log?.Invoke($"  {name}: ERROR — {ex.Message}");
                return 0;
            }
        }

        static HashSet<double> GetPipeDiams(SqliteConnection conn)
        {
            var diams = new HashSet<double>();
            try
            {
                using var cmd = conn.CreateCommand();
                cmd.CommandText = "SELECT DISTINCT DIAMETER_NOMINAL FROM WA_PIPE_MODEL";
                using var reader = cmd.ExecuteReader();
                while (reader.Read())
                {
                    string dn = reader.GetString(0);
                    foreach (var d in ExtractNomDiams(dn))
                        diams.Add(d);
                }
            }
            catch { }
            return diams;
        }

        static HashSet<double> GetAllFittingDiams(SqliteConnection conn)
        {
            var diams = new HashSet<double>();
            foreach (var table in FittingTables)
            {
                try
                {
                    using var cmd = conn.CreateCommand();
                    cmd.CommandText = $"SELECT DIAMETER_NOMINAL FROM {table}";
                    using var reader = cmd.ExecuteReader();
                    while (reader.Read())
                    {
                        string dn = reader.IsDBNull(0) ? "" : reader.GetString(0);
                        foreach (var d in ExtractNomDiams(dn))
                            diams.Add(d);
                    }
                }
                catch { }
            }
            return diams;
        }

        static Dictionary<double, (double od, double? wt)> GetPipeDims(SqliteConnection conn)
        {
            var dims = new Dictionary<double, (double, double?)>();
            try
            {
                using var cmd = conn.CreateCommand();
                cmd.CommandText = @"SELECT DISTINCT cp.NOMINAL_DIAMETER, cp.OUTER_DIAMETER, cp.WALL_THICKNESS
                                    FROM WA_CONNECTION_POINT cp
                                    JOIN WA_PIPE_MODEL p ON cp.PID = p.PID";
                using var reader = cmd.ExecuteReader();
                while (reader.Read())
                {
                    double nom = reader.GetDouble(0);
                    double od = reader.IsDBNull(1) ? nom : reader.GetDouble(1);
                    double? wt = reader.IsDBNull(2) ? null : reader.GetDouble(2);
                    if (!dims.ContainsKey(nom))
                        dims[nom] = (od, wt);
                }
            }
            catch { }
            return dims;
        }

        static Dictionary<double, (double od, double? wt)> GetFittingDims(SqliteConnection conn)
        {
            var dims = new Dictionary<double, (double, double?)>();
            foreach (var table in FittingTables)
            {
                try
                {
                    using var cmd = conn.CreateCommand();
                    cmd.CommandText = $@"SELECT DISTINCT cp.NOMINAL_DIAMETER, cp.OUTER_DIAMETER, cp.WALL_THICKNESS
                                        FROM WA_CONNECTION_POINT cp
                                        JOIN {table} t ON cp.PID = t.PID";
                    using var reader = cmd.ExecuteReader();
                    while (reader.Read())
                    {
                        double nom = reader.GetDouble(0);
                        double od = reader.IsDBNull(1) ? nom : reader.GetDouble(1);
                        double? wt = reader.IsDBNull(2) ? null : reader.GetDouble(2);
                        if (!dims.ContainsKey(nom))
                            dims[nom] = (od, wt);
                    }
                }
                catch { }
            }
            return dims;
        }

        static int GetMaxFid(SqliteConnection conn)
        {
            int maxFid = 0;
            foreach (var table in FittingTables.Concat(new[] { "WA_CONNECTION_POINT" }))
            {
                try
                {
                    using var cmd = conn.CreateCommand();
                    cmd.CommandText = $"SELECT MAX(FID) FROM {table}";
                    var val = cmd.ExecuteScalar();
                    if (val != null && val != DBNull.Value)
                    {
                        int v = Convert.ToInt32(val);
                        if (v > maxFid) maxFid = v;
                    }
                }
                catch { }
            }
            return maxFid;
        }

        static List<string> GetColumns(SqliteConnection conn, string table)
        {
            var cols = new List<string>();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"PRAGMA table_info({table})";
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
                cols.Add(reader.GetString(1));
            return cols;
        }

        static List<string> GetFamilies(SqliteConnection conn, string table)
        {
            var families = new List<string>();
            try
            {
                using var cmd = conn.CreateCommand();
                cmd.CommandText = $"SELECT DISTINCT PART_FAMILY_NAME FROM {table} ORDER BY PART_FAMILY_NAME";
                using var reader = cmd.ExecuteReader();
                while (reader.Read())
                    families.Add(reader.GetString(0));
            }
            catch { }
            return families;
        }

        static HashSet<double> GetExistingDiams(SqliteConnection conn, string table, string familyName)
        {
            var diams = new HashSet<double>();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"SELECT DIAMETER_NOMINAL FROM {table} WHERE PART_FAMILY_NAME = @fam";
            cmd.Parameters.AddWithValue("@fam", familyName);
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                string dn = reader.IsDBNull(0) ? "" : reader.GetString(0);
                foreach (var d in ExtractNomDiams(dn))
                    diams.Add(d);
            }
            return diams;
        }

        static List<double> ExtractNomDiams(string dnStr)
        {
            var result = new List<double>();
            if (string.IsNullOrEmpty(dnStr)) return result;
            var parts = Regex.Split(dnStr, @"\s*x\s*");
            foreach (var p in parts)
            {
                var m = Regex.Match(p.Trim(), @"([\d.]+)");
                if (m.Success && double.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double d))
                    result.Add(d);
            }
            return result;
        }

        static bool DetectInSuffix(SqliteConnection conn, string table, string familyName)
        {
            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"SELECT DIAMETER_NOMINAL FROM {table} WHERE PART_FAMILY_NAME = @fam LIMIT 1";
            cmd.Parameters.AddWithValue("@fam", familyName);
            var val = cmd.ExecuteScalar();
            return val is string s && s.Contains(" in");
        }

        static string MakeDnString(IList<double> diams, bool useInSuffix)
        {
            string Fmt(double d)
            {
                string s = d == Math.Floor(d) ? ((int)d).ToString() : d.ToString(CultureInfo.InvariantCulture);
                return useInSuffix ? $"{s} in" : s;
            }
            return string.Join(" x ", diams.Select(Fmt));
        }

        static (Dictionary<string, object> row, double mainDiam)? FindClosestSize(
            SqliteConnection conn, string table, List<string> cols, string familyName, double targetDiam)
        {
            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"SELECT * FROM {table} WHERE PART_FAMILY_NAME = @fam";
            cmd.Parameters.AddWithValue("@fam", familyName);

            Dictionary<string, object> bestRow = null;
            double bestDist = double.MaxValue;
            double bestMainDiam = 0;

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                var row = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                for (int i = 0; i < cols.Count; i++)
                    row[cols[i]] = reader.IsDBNull(i) ? null : reader.GetValue(i);

                var dn = row.TryGetValue("DIAMETER_NOMINAL", out var dnVal) ? dnVal?.ToString() : "";
                var diams = ExtractNomDiams(dn);
                if (diams.Count == 0) continue;

                double mainDiam = diams[0];
                double dist = Math.Abs(mainDiam - targetDiam);
                if (dist < bestDist)
                {
                    bestDist = dist;
                    bestRow = row;
                    bestMainDiam = mainDiam;
                }
            }

            if (bestRow == null) return null;
            return (bestRow, bestMainDiam);
        }

        static (int newFidCounter, int created) CreateFittingForSize(
            SqliteConnection conn, string table, string familyName, double targetDiam,
            Dictionary<double, (double od, double? wt)> pipeDims,
            Dictionary<double, (double od, double? wt)> fittingDims,
            int fidCounter)
        {
            var cols = GetColumns(conn, table);
            var cpCols = GetColumns(conn, "WA_CONNECTION_POINT");

            var found = FindClosestSize(conn, table, cols, familyName, targetDiam);
            if (found == null) return (fidCounter, 0);

            var (template, templateDiam) = found.Value;
            bool useIn = DetectInSuffix(conn, table, familyName);

            // Get template's connection points
            var templateCps = new List<Dictionary<string, object>>();
            using (var cpCmd = conn.CreateCommand())
            {
                cpCmd.CommandText = "SELECT * FROM WA_CONNECTION_POINT WHERE PID = @pid";
                cpCmd.Parameters.AddWithValue("@pid", template["PID"]);
                using var cpReader = cpCmd.ExecuteReader();
                while (cpReader.Read())
                {
                    var cp = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                    for (int i = 0; i < cpCols.Count; i++)
                        cp[cpCols[i]] = cpReader.IsDBNull(i) ? null : cpReader.GetValue(i);
                    templateCps.Add(cp);
                }
            }
            if (templateCps.Count == 0) return (fidCounter, 0);

            var templateDiams = ExtractNomDiams(template.TryGetValue("DIAMETER_NOMINAL", out var tdnVal) ? tdnVal?.ToString() : "");
            int nDiams = templateDiams.Count;
            var newDiams = Enumerable.Repeat(targetDiam, nDiams).ToList();
            string newDn = MakeDnString(newDiams, useIn);

            // Check if already exists
            using (var chkCmd = conn.CreateCommand())
            {
                chkCmd.CommandText = $"SELECT COUNT(*) FROM {table} WHERE PART_FAMILY_NAME = @fam AND DIAMETER_NOMINAL = @dn";
                chkCmd.Parameters.AddWithValue("@fam", familyName);
                chkCmd.Parameters.AddWithValue("@dn", newDn);
                long cnt = (long)chkCmd.ExecuteScalar();
                if (cnt > 0) return (fidCounter, 0);
            }

            // Generate new IDs
            string newPid = GuidFromSeed($"{familyName}|{newDn}|{table}");
            fidCounter++;
            int newFid = fidCounter;

            // Build description
            string oldDesc = template.TryGetValue("DESCRIPTION", out var descVal) ? descVal?.ToString() ?? "" : "";
            string desc;
            if (useIn)
            {
                desc = Regex.Replace(oldDesc, @"\d+(?:\.\d+)?\s*in(?:\s*x\s*\d+(?:\.\d+)?\s*in)*",
                    newDn.Replace(" x ", " x "), RegexOptions.None, TimeSpan.FromSeconds(1));
                if (desc == oldDesc) desc = oldDesc; // fallback: keep original if regex didn't match
            }
            else
            {
                string tdStr = templateDiam == Math.Floor(templateDiam)
                    ? ((int)templateDiam).ToString() : templateDiam.ToString(CultureInfo.InvariantCulture);
                string ndStr = targetDiam == Math.Floor(targetDiam)
                    ? ((int)targetDiam).ToString() : targetDiam.ToString(CultureInfo.InvariantCulture);
                desc = ReplaceFirst(oldDesc, tdStr, ndStr);
            }

            // Dimensions for new size
            double odNew = targetDiam;
            double? wtNew = null;
            if (pipeDims.TryGetValue(targetDiam, out var pd))
            {
                odNew = pd.od;
                wtNew = pd.wt;
            }
            else if (fittingDims.TryGetValue(targetDiam, out var fd))
            {
                odNew = fd.od;
                wtNew = fd.wt;
            }
            else if (templateDiam > 0)
            {
                double ratio = targetDiam / templateDiam;
                var tcp = templateCps[0];
                if (tcp.TryGetValue("OUTER_DIAMETER", out var odObj) && odObj is double odVal)
                    odNew = odVal * ratio;
                if (tcp.TryGetValue("WALL_THICKNESS", out var wtObj) && wtObj is double wtVal)
                    wtNew = wtVal * ratio;
            }

            // Insert fitting record
            var newRow = new Dictionary<string, object>(template, StringComparer.OrdinalIgnoreCase);
            newRow["FID"] = (long)newFid;
            newRow["DIAMETER_NOMINAL"] = newDn;
            newRow["DESCRIPTION"] = desc;
            newRow["PID"] = newPid;

            InsertRow(conn, table, cols, newRow);

            // Insert connection points
            foreach (var tcp in templateCps)
            {
                fidCounter++;
                var newCp = new Dictionary<string, object>(tcp, StringComparer.OrdinalIgnoreCase);
                newCp["FID"] = (long)fidCounter;
                newCp["PID"] = newPid;
                newCp["NOMINAL_DIAMETER"] = targetDiam;
                newCp["OUTER_DIAMETER"] = odNew;
                newCp["WALL_THICKNESS"] = wtNew.HasValue ? (object)wtNew.Value : DBNull.Value;

                if (templateDiam > 0)
                {
                    double ratio = targetDiam / templateDiam;
                    foreach (var coord in new[] { "POSITION_3D_X", "POSITION_3D_Y", "POSITION_3D_Z" })
                    {
                        if (newCp.TryGetValue(coord, out var cVal) && cVal is double cv)
                            newCp[coord] = cv * ratio / (tcp.TryGetValue(coord, out var orig) && orig is double ov && ov != 0 ? 1.0 : 1.0);
                    }
                    // Simpler: just scale from template
                    foreach (var coord in new[] { "POSITION_3D_X", "POSITION_3D_Y", "POSITION_3D_Z" })
                    {
                        if (tcp.TryGetValue(coord, out var orig) && orig is double ov)
                            newCp[coord] = ov * ratio;
                    }
                    if (tcp.TryGetValue("ENGAGEMENT_LENGTH", out var elVal) && elVal is double el)
                        newCp["ENGAGEMENT_LENGTH"] = el * ratio;
                }

                InsertRow(conn, "WA_CONNECTION_POINT", cpCols, newCp);
            }

            return (fidCounter, 1);
        }

        static void InsertRow(SqliteConnection conn, string table, List<string> cols, Dictionary<string, object> row)
        {
            using var cmd = conn.CreateCommand();
            var colList = string.Join(",", cols);
            var paramList = string.Join(",", cols.Select((c, i) => $"@p{i}"));
            cmd.CommandText = $"INSERT INTO {table} ({colList}) VALUES ({paramList})";
            for (int i = 0; i < cols.Count; i++)
            {
                var val = row.TryGetValue(cols[i], out var v) ? v : DBNull.Value;
                cmd.Parameters.AddWithValue($"@p{i}", val ?? DBNull.Value);
            }
            cmd.ExecuteNonQuery();
        }

        static string GuidFromSeed(string seed)
        {
            using var md5 = System.Security.Cryptography.MD5.Create();
            // uuid5-style: namespace DNS + seed
            byte[] nsBytes = new Guid("6ba7b810-9dad-11d1-80b4-00c04fd430c8").ToByteArray();
            byte[] seedBytes = System.Text.Encoding.UTF8.GetBytes(seed);
            byte[] combined = nsBytes.Concat(seedBytes).ToArray();
            byte[] hash = md5.ComputeHash(combined);
            hash[6] = (byte)((hash[6] & 0x0F) | 0x50); // version 5
            hash[8] = (byte)((hash[8] & 0x3F) | 0x80); // variant
            return new Guid(hash).ToString();
        }

        static string ReplaceFirst(string str, string oldValue, string newValue)
        {
            int idx = str.IndexOf(oldValue, StringComparison.Ordinal);
            if (idx < 0) return str;
            return str.Substring(0, idx) + newValue + str.Substring(idx + oldValue.Length);
        }
    }
}
