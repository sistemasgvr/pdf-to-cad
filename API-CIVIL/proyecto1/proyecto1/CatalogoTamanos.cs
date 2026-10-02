using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;
using Exception = System.Exception;

// ============================================================================
//  TAMAÑOS NUEVOS agregados desde la app (botón verde «+», app/catalogo_tamanos.py)
//   · La app escribe el tamaño en el catálogo (XML de la familia / SQLite de
//     presión) de cada C3D ≥ 2025 e idioma, y deja la marca
//     «Pipes Catalog\pdfcad_regenerar.txt» cuando tocó un catálogo de gravedad.
//   · RegenerarCatalogoSiPendiente (al empezar IMPORTAR_RED): si la marca está en
//     el catálogo de ESTA sesión, encola PARTCATALOGREGEN Pipe y Structure y
//     vuelve a lanzar IMPORTAR_RED (mismo patrón que PREPARAR_FAMILIAS: los
//     comandos encolados corren después, cada uno en su contexto).
//   · AgregarTamanoExacto: pone en la lista de piezas del dibujo la medida EXACTA
//     pedida (ancho × alto / ancho × largo / diámetro). Técnica de
//     PrepararFamilias.AddTamanosPorAnchoYAlto: un AddPartSize con cada eje fijo
//     a su valor y los demás campos de lista en su primer valor, sin selección
//     múltiple (si no, AddPartSize duplica).
//   · AsegurarTuboPresion: el tubo de presión del diámetro pedido que no está en
//     la lista de la red se copia de SU catálogo (pl.Catalog, por reflexión: el
//     tipo no es accesible al compilar) con AddPart.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        internal const string MARCA_REGEN = "pdfcad_regenerar.txt";

        /// <summary>Carpetas «Pipes Catalog» del catálogo activo de esta sesión.</summary>
        internal static List<string> CarpetasPipesCatalog()
        {
            var salida = new List<string>();
            foreach (var sv in new[] { "AECCPIPECATALOG", "AECCSTRUCTURECATALOG" })
            {
                try
                {
                    string p = Application.GetSystemVariable(sv) as string;
                    var d = string.IsNullOrWhiteSpace(p) ? null
                        : (File.Exists(p) ? new FileInfo(p).Directory : new DirectoryInfo(p));
                    while (d != null && !string.Equals(d.Name, "Pipes Catalog", StringComparison.OrdinalIgnoreCase))
                        d = d.Parent;
                    if (d != null && d.Exists && !salida.Contains(d.FullName, StringComparer.OrdinalIgnoreCase))
                        salida.Add(d.FullName);
                }
                catch { }
            }
            return salida;
        }

        /// <summary>Borra las marcas (lo llama también PREPARAR_FAMILIAS, que ya regenera).</summary>
        internal static List<string> TomarMarcasRegen()
        {
            var lineas = new List<string>();
            foreach (var dir in CarpetasPipesCatalog())
            {
                string m = Path.Combine(dir, MARCA_REGEN);
                if (!File.Exists(m)) continue;
                try { lineas.AddRange(File.ReadAllLines(m).Where(l => l.Trim().Length > 0)); } catch { }
                try { File.Delete(m); } catch { }
            }
            return lineas.Distinct().ToList();
        }

        /// <summary>True si encoló la regeneración (y `comandoTras` después): el
        /// llamador debe terminar ahí.</summary>
        internal static bool RegenerarCatalogoSiPendiente(Document doc, Editor ed, string comandoTras)
        {
            var lineas = TomarMarcasRegen();
            if (lineas.Count == 0) return false;
            ed.WriteMessage("\n↻ La app agregó tamaños nuevos al catálogo (" +
                            string.Join("; ", lineas.Take(6)) + (lineas.Count > 6 ? "…" : "") +
                            "). Se regenera el catálogo de piezas y luego sigue «" + comandoTras + "».");
            ed.WriteMessage("\n  Si aparece la pregunta del catálogo, elige Tubería (Pipe) y después Estructura (Structure).");
            doc.SendStringToExecute("_PARTCATALOGREGEN _P ", true, false, false);
            doc.SendStringToExecute("_PARTCATALOGREGEN _S ", true, false, false);
            if (!string.IsNullOrWhiteSpace(comandoTras))
                doc.SendStringToExecute(comandoTras + " ", true, false, false);
            return true;
        }

        /// <summary>Agrega a la familia de la lista de piezas el tamaño con estos
        /// valores exactos (pulgadas, ±0.01 contra los valores del catálogo). False si
        /// el catálogo no los trae (no regenerado) o Civil 3D no creó nada.</summary>
        internal static bool AgregarTamanoExacto(PartsStyles.PartFamily fam,
            Dictionary<CivilDB.PartContextType, double> valores, Editor ed)
        {
            try
            {
                try { fam.UpgradeOpen(); } catch { }
                var filtro = new PartsStyles.SizeFilterRecord(fam);
                int puestos = 0;
                for (int i = 0; i < filtro.ParamCount; i++)
                {
                    var campo = filtro[i];
                    if (campo == null) continue;
                    if (valores.TryGetValue(campo.Context, out double v))
                    {
                        // Tabla por FILAS: el 2.º eje lo fija la fila elegida (campo de
                        // solo lectura). El llamador comprueba después con SizeExacto.
                        if (campo.IsReadOnly) { puestos++; continue; }
                        if (!campo.IsFromList)
                        {
                            try { campo.Value = v; puestos++; } catch { }
                            continue;
                        }
                        object elegido = null;
                        for (int k = 0; k < campo.ValueList.Count; k++)
                        {
                            try
                            {
                                double dv = Convert.ToDouble(campo.ValueList[k], CultureInfo.InvariantCulture);
                                if (Math.Abs(dv - v) < 0.01) { elegido = campo.ValueList[k]; break; }
                            }
                            catch { }
                        }
                        if (elegido == null)
                        {
                            Dl(ed, $"\n    [ATE] '{fam.Description}': {campo.Context}={v:0.###} no está en el catálogo (¿falta regenerar?).");
                            return false;
                        }
                        campo.IsMultipleSelect = false; campo.Value = elegido; puestos++;
                    }
                    else if (!campo.IsReadOnly && campo.IsFromList && campo.ValueList.Count > 0)
                    {
                        campo.IsMultipleSelect = false;
                        campo.Value = campo.ValueList[0];
                    }
                }
                if (puestos < valores.Count) return false;
                int antes = fam.PartSizeCount;
                fam.AddPartSize(filtro);
                bool ok = fam.PartSizeCount > antes;
                if (ok)
                    ed?.WriteMessage($"\n  + Tamaño {string.Join(" x ", valores.Values.Select(x => x.ToString("0.##", CultureInfo.InvariantCulture)))} " +
                                     $"agregado a '{fam.Description}'.");
                return ok;
            }
            catch (Exception ex)
            {
                Dl(ed, $"\n    [ATE] '{fam.Description}': {ex.Message}");
                return false;
            }
        }

        /// <summary>Tamaño de la familia cuyos campos (por contexto) valen exactamente
        /// esto (±0.01). ObjectId.Null si no hay.</summary>
        internal static ObjectId SizeExacto(Transaction tr, PartsStyles.PartFamily fam,
            Dictionary<CivilDB.PartContextType, double> valores, out string nombre)
        {
            nombre = "";
            for (int i = 0; i < fam.PartSizeCount; i++)
            {
                var sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                if (sz == null) continue;
                bool ok = true;
                try
                {
                    var rec = sz.SizeDataRecord;
                    foreach (var kv in valores)
                    {
                        var f = rec?.GetDataFieldBy(kv.Key);
                        if (f?.Value == null ||
                            Math.Abs(Convert.ToDouble(f.Value, CultureInfo.InvariantCulture) - kv.Value) >= 0.01)
                        { ok = false; break; }
                    }
                }
                catch { ok = false; }
                if (ok) { nombre = sz.Name; return fam[i]; }
            }
            return ObjectId.Null;
        }

        /// <summary>Tamaño pedido «W x L» o «D» → valores por contexto para una familia
        /// de estructura (ancho × largo, o diámetro interior).</summary>
        internal static Dictionary<CivilDB.PartContextType, double> ValoresEstructura(string radio)
        {
            if (TryParseRectSize(radio, out double? w, out double? l) && w.HasValue && l.HasValue)
                return new Dictionary<CivilDB.PartContextType, double>
                { [CivilDB.PartContextType.StructInnerWidth] = w.Value, [CivilDB.PartContextType.StructInnerLength] = l.Value };
            var m = System.Text.RegularExpressions.Regex.Match(radio ?? "", @"^\s*(\d+(?:\.\d+)?)");
            if (m.Success && double.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double d))
                return new Dictionary<CivilDB.PartContextType, double> { [CivilDB.PartContextType.StructInnerDiameter] = d };
            return null;
        }

        /// <summary>Si la lista de la red no tiene el tubo de presión de esta familia y
        /// diámetro, lo copia del catálogo de la lista. Devuelve la lista de tubos
        /// actualizada (la misma si no hizo falta o no se pudo).</summary>
        internal static List<PresStyles.PressurePartSize> AsegurarTuboPresion(PresStyles.PressurePartList pl,
            List<PresStyles.PressurePartSize> tubos, double diam, string pipeFamily, Editor ed)
        {
            if (pl == null || diam <= 0 || string.IsNullOrWhiteSpace(pipeFamily) || !pipeFamily.Contains("|"))
                return tubos;
            string fam = pipeFamily.Substring(pipeFamily.IndexOf('|') + 1);
            string famNorm = fam.Replace(" ", "").Replace(",", "").ToLowerInvariant();
            bool EsDeLaFamilia(PresStyles.PressurePartSize t)
            {
                string d = (t?.Description ?? "").Replace(" ", "").Replace(",", "").ToLowerInvariant();
                return d.Length > 0 && (d.Contains(famNorm) || DescripcionDeFamilia(t?.Description, fam));
            }
            bool DelDiametro(PresStyles.PressurePartSize t) =>
                Math.Abs(ComandosPresion.ExtraerDiametroDeDescripcion(t?.Description) - diam) < 0.01;
            if (tubos != null && tubos.Any(t => EsDeLaFamilia(t) && DelDiametro(t))) return tubos;
            try
            {
                object cat = pl.GetType().GetProperty("Catalog", BindingFlags.Public | BindingFlags.Instance)?.GetValue(pl);
                var mGet = cat?.GetType().GetMethod("GetParts", BindingFlags.Public | BindingFlags.Instance, null,
                    new[] { typeof(CivilDB.PressurePartDomainType) }, null);
                if (mGet == null) return tubos;
                var partes = ((IEnumerable)mGet.Invoke(cat, new object[] { CivilDB.PressurePartDomainType.Pipe }))
                    .Cast<PresStyles.PressurePartSize>().ToList();
                var ps = partes.FirstOrDefault(t => EsDeLaFamilia(t) && DelDiametro(t));
                if (ps == null)
                {
                    Dl(ed, $"\n    [ATP-PRES] '{fam}' {diam:0.##} in no está en el catálogo de la lista '{pl.Name}' " +
                           "(si se agregó con Civil 3D abierto, reinícialo).");
                    return tubos;
                }
                try { pl.UpgradeOpen(); } catch { }
                pl.AddPart(ps);
                ed?.WriteMessage($"\n  + Tubo de presión '{ps.Description}' agregado a la lista '{pl.Name}'.");
                return pl.GetParts(CivilDB.PressurePartDomainType.Pipe);
            }
            catch (Exception ex)
            {
                Dl(ed, $"\n    [ATP-PRES] '{fam}' {diam:0.##} in: {ex.InnerException?.Message ?? ex.Message}");
                return tubos;
            }
        }

        /// <summary>La descripción de un tamaño («pipe-9 in-push on-ductile iron-250 psi-…»)
        /// corresponde a la familia («pipe-push on-ductile iron-250 psi») sin su «N in-».</summary>
        private static bool DescripcionDeFamilia(string desc, string familia)
        {
            if (string.IsNullOrEmpty(desc) || string.IsNullOrEmpty(familia)) return false;
            string sin = System.Text.RegularExpressions.Regex.Replace(desc, @"(?<![\d.])\d+(?:[._]\d+)?\s*in\b-?", "",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            string n(string s) => s.Replace(" ", "").Replace("-", "").Replace("_", "").Replace(",", "").ToLowerInvariant();
            return n(sin).Contains(n(familia));
        }
    }
}
