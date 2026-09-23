using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;
using Autodesk.AutoCAD.EditorInput;

// ============================================================================
//  Wye de ÁNGULO A MEDIDA en el catálogo Imperial_AWWA_Steel
//  ---------------------------------------------------------------------------
//  PROBLEMA: el catálogo Steel solo trae Wye de 30/45/60/75/90°. Una juntura
//  real del plano casi nunca cae en esos valores (p.ej. 57°), así que la mejor
//  pieza disponible deja un residuo angular (~7° repartido en los 3 puertos)
//  que se ve como la Y ligeramente girada respecto a las tuberías.
//
//  SOLUCIÓN (misma técnica que PressureCatalogFiller usó para los tamaños Ø1"
//  que no existían): CLONAR en el .sqlite la Wye del ángulo más cercano y
//  ROTAR la geometría de su puerto de ramal hasta el ángulo pedido.
//
//  DIFERENCIA CLAVE con el filler de tamaños: ahí se ESCALA (ratio de
//  diámetros); aquí se ROTA. El ramal de una Wye vive en WA_CONNECTION_POINT
//  como POSITION_3D_X/Y/Z respecto al centro de la pieza; cambiar el ángulo =
//  girar ese punto (y su vector de dirección si la tabla lo guarda) alrededor
//  del eje perpendicular al plano de la Y.
//
//  Idempotente: el PID se deriva por hash de (familia|diámetro|ángulo), así que
//  re-ejecutar no duplica. Solo escribe si la pieza no existe ya.
// ============================================================================

namespace Civil3DBasico
{
    internal static class WyeAnguloCustom
    {
        const string TABLA = "WA_BRANCH_FITTING_MODEL";
        const int ID_TYPE_WYE = 4;

        // Ángulos que el catálogo trae de fábrica. Si el pedido cae a menos de
        // TOL_GRADOS de uno de ellos, no vale la pena crear nada.
        const double TOL_GRADOS = 2.0;

        // Cache por sesión: ángulos ya generados (evita reabrir el SQLite).
        private static readonly HashSet<string> _generados =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// Asegura que exista en el catálogo una Wye del diámetro y ángulo
        /// pedidos. Devuelve true si la creó (o ya existía por creación previa
        /// nuestra), false si no hizo falta o no se pudo.
        /// </summary>
        internal static bool AsegurarWyeDeAngulo(double diamIn, double anguloDeseado, Editor ed)
        {
            try
            {
                int angRound = (int)Math.Round(anguloDeseado);
                string clave = $"{diamIn:F0}|{angRound}";
                if (_generados.Contains(clave)) return true;

                string sqlite = AsegurarPresionWye.LocalizarSqlite();
                if (string.IsNullOrEmpty(sqlite) || !File.Exists(sqlite))
                {
                    ed?.WriteMessage("\n  ⚠ [WYE-CUSTOM] No encontré el .sqlite del catálogo Steel.");
                    return false;
                }

                var cs = new SqliteConnectionStringBuilder
                { DataSource = sqlite, Mode = SqliteOpenMode.ReadWrite }.ToString();
                using var conn = new SqliteConnection(cs);
                conn.Open();

                var cols   = GetColumns(conn, TABLA);
                var cpCols = GetColumns(conn, "WA_CONNECTION_POINT");

                // ── Plantilla: la Wye existente del MISMO diámetro cuyo ángulo
                //    esté más cerca del pedido.
                var (plantilla, angPlantilla) = BuscarWyePlantilla(conn, cols, diamIn, anguloDeseado, ed);
                if (plantilla == null)
                {
                    ed?.WriteMessage($"\n  ⚠ [WYE-CUSTOM] Sin Wye plantilla para Ø{diamIn:F0}\".");
                    return false;
                }
                if (Math.Abs(angPlantilla - anguloDeseado) <= TOL_GRADOS)
                {
                    // Ya hay una pieza suficientemente cercana de fábrica.
                    _generados.Add(clave);
                    return false;
                }

                string famPlantilla = plantilla.TryGetValue("PART_FAMILY_NAME", out var fnv)
                    ? fnv?.ToString() ?? "" : "";
                // Nombre de familia nuevo: "Wye 57_ GVR ..." (conserva el resto
                // del nombre original para que el catálogo lo agrupe igual).
                string famNueva = Regex.Replace(famPlantilla, @"\bWye\s*\d{1,3}",
                    $"Wye {angRound}", RegexOptions.IgnoreCase);
                if (famNueva == famPlantilla) famNueva = $"Wye {angRound}_ {famPlantilla}";

                string dn = plantilla.TryGetValue("DIAMETER_NOMINAL", out var dnv)
                    ? dnv?.ToString() ?? "" : "";

                // ¿Ya existe (creada en un run anterior)?
                using (var chk = conn.CreateCommand())
                {
                    chk.CommandText = $"SELECT COUNT(*) FROM {TABLA} " +
                                      "WHERE PART_FAMILY_NAME = @fam AND DIAMETER_NOMINAL = @dn";
                    chk.Parameters.AddWithValue("@fam", famNueva);
                    chk.Parameters.AddWithValue("@dn", dn);
                    if (Convert.ToInt64(chk.ExecuteScalar()) > 0)
                    {
                        _generados.Add(clave);
                        ed?.WriteMessage($"\n  · [WYE-CUSTOM] '{famNueva}' Ø{diamIn:F0}\" ya existía en el catálogo.");
                        return true;
                    }
                }

                // ── Connection points de la plantilla.
                var cps = new List<Dictionary<string, object>>();
                using (var cpCmd = conn.CreateCommand())
                {
                    cpCmd.CommandText = "SELECT * FROM WA_CONNECTION_POINT WHERE PID = @pid";
                    cpCmd.Parameters.AddWithValue("@pid", plantilla["PID"]);
                    using var rd = cpCmd.ExecuteReader();
                    while (rd.Read())
                    {
                        var cp = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                        for (int i = 0; i < cpCols.Count; i++)
                            cp[cpCols[i]] = rd.IsDBNull(i) ? null : rd.GetValue(i);
                        cps.Add(cp);
                    }
                }
                if (cps.Count < 3)
                {
                    ed?.WriteMessage($"\n  ⚠ [WYE-CUSTOM] La plantilla tiene {cps.Count} puertos (se esperaban 3).");
                    return false;
                }

                // ── Identificar el puerto de RAMAL: el que NO es colineal con el
                //    tronco. Se mide con las posiciones 3D respecto al origen de
                //    la pieza: los dos del tronco son casi opuestos entre sí.
                int idxRamal = IdentificarRamal(cps);
                if (idxRamal < 0)
                {
                    ed?.WriteMessage("\n  ⚠ [WYE-CUSTOM] No pude identificar el puerto de ramal en la plantilla.");
                    return false;
                }

                // ── Rotar el ramal desde angPlantilla hasta anguloDeseado.
                //    El giro se hace en el plano de la Y (definido por el eje del
                //    tronco y la posición del ramal), alrededor del origen local.
                double deltaGrados = anguloDeseado - angPlantilla;
                double delta = deltaGrados * Math.PI / 180.0;

                string newPid = GuidFromSeed($"{famNueva}|{dn}|{TABLA}|{angRound}");
                int fid = GetMaxFid(conn) + 100;

                string descOld = plantilla.TryGetValue("DESCRIPTION", out var dsv)
                    ? dsv?.ToString() ?? "" : "";
                string descNew = Regex.Replace(descOld, @"\bWye\s*\d{1,3}",
                    $"Wye {angRound}", RegexOptions.IgnoreCase);
                if (descNew == descOld) descNew = $"{descOld} ({angRound}°)";

                using var tx = conn.BeginTransaction();

                var filaNueva = new Dictionary<string, object>(plantilla, StringComparer.OrdinalIgnoreCase);
                filaNueva["FID"] = (long)fid;
                filaNueva["PID"] = newPid;
                filaNueva["PART_FAMILY_NAME"] = famNueva;
                filaNueva["DESCRIPTION"] = descNew;
                // PART_FAMILY_ID debe ser distinto para que Civil 3D la trate
                // como familia propia y no mezcle tamaños con la de 60°.
                if (filaNueva.ContainsKey("PART_FAMILY_ID"))
                    filaNueva["PART_FAMILY_ID"] = GuidFromSeed($"FAM|{famNueva}");
                InsertRow(conn, TABLA, cols, filaNueva);

                int nRot = 0;
                for (int i = 0; i < cps.Count; i++)
                {
                    fid++;
                    var cp = new Dictionary<string, object>(cps[i], StringComparer.OrdinalIgnoreCase);
                    cp["FID"] = (long)fid;
                    cp["PID"] = newPid;

                    if (i == idxRamal)
                    {
                        RotarPuerto(cp, delta);
                        nRot++;
                    }
                    InsertRow(conn, "WA_CONNECTION_POINT", cpCols, cp);
                }

                tx.Commit();
                _generados.Add(clave);
                ed?.WriteMessage($"\n  · [WYE-CUSTOM] Creada '{famNueva}' Ø{diamIn:F0}\" " +
                    $"(clonada de {angPlantilla:F0}°, ramal rotado {deltaGrados:+0.0;-0.0}° → {angRound}°).");
                return true;
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-CUSTOM] Error: {ex.Message}");
                return false;
            }
        }

        // Rota la posición (y el vector de dirección si la tabla lo guarda) de un
        // connection point `delta` radianes en el plano XY local de la pieza.
        // En los catálogos AWWA el eje del tronco es X y la Y se abre en XY, así
        // que el giro alrededor de Z local es el correcto.
        static void RotarPuerto(Dictionary<string, object> cp, double delta)
        {
            double cos = Math.Cos(delta), sin = Math.Sin(delta);

            void RotarPar(string cx, string cy)
            {
                if (!cp.TryGetValue(cx, out var ox) || !cp.TryGetValue(cy, out var oy)) return;
                if (!(ox is double x) || !(oy is double y)) return;
                cp[cx] = x * cos - y * sin;
                cp[cy] = x * sin + y * cos;
            }

            // Posición del puerto.
            RotarPar("POSITION_3D_X", "POSITION_3D_Y");
            // Vector de dirección/normal, si existe con estos nombres habituales.
            RotarPar("DIRECTION_3D_X", "DIRECTION_3D_Y");
            RotarPar("NORMAL_3D_X", "NORMAL_3D_Y");
            RotarPar("VECTOR_3D_X", "VECTOR_3D_Y");
        }

        // El ramal es el puerto cuya posición NO es casi opuesta a otra: los dos
        // del tronco forman ~180° entre sí vistos desde el origen de la pieza.
        static int IdentificarRamal(List<Dictionary<string, object>> cps)
        {
            var v = new List<(double x, double y)>();
            foreach (var cp in cps)
            {
                double x = ToD(cp, "POSITION_3D_X"), y = ToD(cp, "POSITION_3D_Y");
                double L = Math.Sqrt(x * x + y * y);
                v.Add(L > 1e-9 ? (x / L, y / L) : (1.0, 0.0));
            }
            // Para cada candidato a ramal, los otros dos deben ser lo más
            // opuestos posible (dot ≈ -1).
            int mejor = -1; double mejorDot = double.MaxValue;
            for (int i = 0; i < v.Count; i++)
            {
                int a = (i + 1) % v.Count, b = (i + 2) % v.Count;
                double dot = v[a].x * v[b].x + v[a].y * v[b].y;
                if (dot < mejorDot) { mejorDot = dot; mejor = i; }
            }
            return mejor;
        }

        // Busca, entre las Wye del diámetro pedido, la de ángulo más cercano.
        static (Dictionary<string, object> fila, double angulo) BuscarWyePlantilla(
            SqliteConnection conn, List<string> cols, double diamIn, double angDeseado, Editor ed)
        {
            Dictionary<string, object> mejor = null;
            double mejorAng = 0, mejorDif = double.MaxValue;

            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"SELECT * FROM {TABLA} WHERE ID_TYPE = {ID_TYPE_WYE}";
            using var rd = cmd.ExecuteReader();
            while (rd.Read())
            {
                var fila = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                for (int i = 0; i < cols.Count; i++)
                    fila[cols[i]] = rd.IsDBNull(i) ? null : rd.GetValue(i);

                string dn = fila.TryGetValue("DIAMETER_NOMINAL", out var v) ? v?.ToString() ?? "" : "";
                var diams = AsegurarPresionWye.ExtraerDiams(dn);
                if (diams.Count == 0) continue;
                // Solo plantillas del mismo diámetro nominal principal.
                if (Math.Abs(diams[0] - diamIn) > 0.51) continue;

                string fam = fila.TryGetValue("PART_FAMILY_NAME", out var fv) ? fv?.ToString() ?? "" : "";
                int ang = AsegurarPresionWye.ExtraerAngulo(fam);
                if (ang <= 0) continue;
                // No usar como plantilla una que hayamos generado nosotros.
                if (fam.IndexOf("GVR", StringComparison.OrdinalIgnoreCase) >= 0) continue;

                double dif = Math.Abs(ang - angDeseado);
                if (dif < mejorDif) { mejorDif = dif; mejor = fila; mejorAng = ang; }
            }
            return (mejor, mejorAng);
        }

        // ── Utilidades SQLite (mismo patrón que PressureCatalogFiller) ────────
        static double ToD(Dictionary<string, object> d, string k)
            => d.TryGetValue(k, out var v) && v is double x ? x : 0.0;

        static List<string> GetColumns(SqliteConnection conn, string table)
        {
            var cols = new List<string>();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"PRAGMA table_info({table})";
            using var rd = cmd.ExecuteReader();
            while (rd.Read()) cols.Add(rd.GetString(1));
            return cols;
        }

        static int GetMaxFid(SqliteConnection conn)
        {
            int max = 0;
            foreach (var t in new[] { TABLA, "WA_CONNECTION_POINT" })
            {
                try
                {
                    using var cmd = conn.CreateCommand();
                    cmd.CommandText = $"SELECT MAX(FID) FROM {t}";
                    var v = cmd.ExecuteScalar();
                    if (v != null && v != DBNull.Value)
                    {
                        int n = Convert.ToInt32(v);
                        if (n > max) max = n;
                    }
                }
                catch { }
            }
            return max;
        }

        static void InsertRow(SqliteConnection conn, string table,
            List<string> cols, Dictionary<string, object> row)
        {
            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"INSERT INTO {table} ({string.Join(",", cols)}) " +
                              $"VALUES ({string.Join(",", cols.Select((c, i) => "@p" + i))})";
            for (int i = 0; i < cols.Count; i++)
            {
                var val = row.TryGetValue(cols[i], out var v) ? v : DBNull.Value;
                cmd.Parameters.AddWithValue("@p" + i, val ?? DBNull.Value);
            }
            cmd.ExecuteNonQuery();
        }

        // UUID v5 determinista — re-ejecutar no duplica (igual que el filler).
        static string GuidFromSeed(string seed)
        {
            using var md5 = System.Security.Cryptography.MD5.Create();
            byte[] ns = new Guid("6ba7b810-9dad-11d1-80b4-00c04fd430c8").ToByteArray();
            byte[] sd = System.Text.Encoding.UTF8.GetBytes(seed);
            byte[] hash = md5.ComputeHash(ns.Concat(sd).ToArray());
            hash[6] = (byte)((hash[6] & 0x0F) | 0x50);
            hash[8] = (byte)((hash[8] & 0x3F) | 0x80);
            return new Guid(hash).ToString();
        }
    }
}
