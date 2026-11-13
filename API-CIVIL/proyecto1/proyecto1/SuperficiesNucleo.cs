using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

// ============================================================================
//  Superficies de la app (2026-11-11, 2.1.0) — núcleo PURO (sin Autodesk)
//   · La app exporta cada superficie como un LandXML 1.2 (TIN) + un POINT
//     `PDFCAD_SUPERFICIE` en el DXF con lo esperado (puntos, triángulos, cotas,
//     recuadro, muestras). Aquí: leer ese XDATA, ubicar el archivo, igualar el
//     <Units> del LandXML a las unidades del DIBUJO (para que Civil 3D no convierta:
//     los números ya están en el sistema del dibujo) y comparar lo creado con lo
//     esperado. Lo usa ImportarRedSuperficies.cs; lo prueba PerfilPruebas.
// ============================================================================

namespace Civil3DBasico
{
    public static class SuperficiesNucleo
    {
        public const double TOL_Z = 1e-6;         // ZMIN/ZMAX
        public const double TOL_RECUADRO = 1e-6;  // XMIN…YMAX
        public const double TOL_MUESTRA = 1e-4;   // FindElevationAtXY

        /// <summary>Lo que la app dice de una superficie (XDATA de PDFCAD_SUPERFICIE).</summary>
        public sealed class Registro
        {
            public string Nombre = "", Archivo = "", ArchivoAbs = "", Sha1 = "", Unidad = "", Fuente = "", Crs = "";
            public int? NPuntos, NTriangulos;
            public double? ZMin, ZMax, XMin, YMin, XMax, YMax;
            public List<(double X, double Y, double Z)> Muestras = new List<(double, double, double)>();
        }

        /// <summary>Lo que Civil 3D dice de la superficie creada.</summary>
        public sealed class Medido
        {
            public int NPuntos, NTriangulos;
            public double ZMin, ZMax, XMin, YMin, XMax, YMax;
        }

        private static string Str(IDictionary<string, string> xd, string k)
        {
            return xd != null && xd.TryGetValue(k, out var v) && v != null ? v.Trim() : "";
        }

        public static double? Num(string s)
        {
            s = (s ?? "").Trim().Replace(',', '.');
            if (s.Length == 0) return null;
            return double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var d) && !double.IsNaN(d) && !double.IsInfinity(d)
                ? d : (double?)null;
        }

        private static int? Entero(string s)
        {
            var d = Num(s);
            return d.HasValue && d.Value >= 0 && d.Value <= int.MaxValue ? (int)Math.Round(d.Value) : (int?)null;
        }

        /// <summary>«x,y,z;x,y,z;…» → muestras. Una muestra incompleta o ilegible (p. ej. cortada) se ignora.</summary>
        public static List<(double X, double Y, double Z)> LeerMuestras(string s)
        {
            var r = new List<(double, double, double)>();
            foreach (var trozo in (s ?? "").Split(';'))
            {
                var p = trozo.Split(',');
                if (p.Length != 3) continue;
                var x = Num(p[0]); var y = Num(p[1]); var z = Num(p[2]);
                if (x.HasValue && y.HasValue && z.HasValue) r.Add((x.Value, y.Value, z.Value));
            }
            return r;
        }

        /// <summary>Diccionario CLAVE→valor del XDATA (como lo arma LeerXdataPdfcad) → Registro.</summary>
        public static Registro Leer(IDictionary<string, string> xd)
        {
            return new Registro
            {
                Nombre = Str(xd, "NAME"),
                Archivo = Str(xd, "ARCHIVO"),
                ArchivoAbs = Str(xd, "ARCHIVO_ABS"),
                Sha1 = Str(xd, "SHA1").ToLowerInvariant(),
                Unidad = Str(xd, "UNIDAD"),
                Fuente = Str(xd, "FUENTE"),
                Crs = Str(xd, "CRS"),
                NPuntos = Entero(Str(xd, "N_PUNTOS")),
                NTriangulos = Entero(Str(xd, "N_TRIANGULOS")),
                ZMin = Num(Str(xd, "ZMIN")), ZMax = Num(Str(xd, "ZMAX")),
                XMin = Num(Str(xd, "XMIN")), YMin = Num(Str(xd, "YMIN")),
                XMax = Num(Str(xd, "XMAX")), YMax = Num(Str(xd, "YMAX")),
                Muestras = LeerMuestrasNumeradas(xd),
            };
        }

        /// <summary>MUESTRA_1 … MUESTRA_10 («x,y,z» cada una; un texto XDATA admite ≤255 caracteres).
        /// Las que faltan o no se leen se saltan. Compatibilidad: si no hay ninguna, «MUESTRAS=x,y,z;…».</summary>
        public static List<(double X, double Y, double Z)> LeerMuestrasNumeradas(IDictionary<string, string> xd)
        {
            var r = new List<(double, double, double)>();
            var claves = (xd?.Keys ?? Enumerable.Empty<string>())
                .Select(k => (k, n: k.StartsWith("MUESTRA_", StringComparison.OrdinalIgnoreCase)
                                    && int.TryParse(k.Substring(8), NumberStyles.None, CultureInfo.InvariantCulture, out int i) ? i : -1))
                .Where(t => t.n > 0).OrderBy(t => t.n);
            foreach (var (k, _) in claves) r.AddRange(LeerMuestras(Str(xd, k)));
            if (r.Count == 0) r = LeerMuestras(Str(xd, "MUESTRAS"));
            return r;
        }

        /// <summary>Ruta del LandXML: ARCHIVO relativo a cada carpeta candidata (la del dibujo/DXF), si no ARCHIVO_ABS. Null = no está.</summary>
        public static string ResolverRuta(Registro r, IEnumerable<string> carpetas, Func<string, bool> existe)
        {
            if (!string.IsNullOrWhiteSpace(r.Archivo))
            {
                string rel = r.Archivo.Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
                if (Path.IsPathRooted(rel) && existe(rel)) return rel;
                foreach (var c in carpetas ?? Enumerable.Empty<string>())
                {
                    if (string.IsNullOrWhiteSpace(c)) continue;
                    string p;
                    try { p = Path.GetFullPath(Path.Combine(c, rel)); } catch { continue; }
                    if (existe(p)) return p;
                }
            }
            if (!string.IsNullOrWhiteSpace(r.ArchivoAbs) && existe(r.ArchivoAbs)) return r.ArchivoAbs;
            return null;
        }

        public static string Sha1Hex(byte[] datos)
        {
            using (var h = System.Security.Cryptography.SHA1.Create())
                return string.Concat(h.ComputeHash(datos).Select(b => b.ToString("x2")));
        }

        /// <summary>Unidad LandXML que corresponde al dibujo: «meter», «USSurveyFoot» o «foot».</summary>
        public static string UnidadDelDibujo(bool metros, bool pieTopografico)
        {
            return metros ? "meter" : (pieTopografico ? "USSurveyFoot" : "foot");
        }

        /// <summary>Bloque &lt;Units&gt; completo de LandXML 1.2 para esa unidad lineal.</summary>
        public static string BloqueUnidades(string unidad)
        {
            if (string.Equals(unidad, "meter", StringComparison.OrdinalIgnoreCase))
                return "<Units><Metric linearUnit=\"meter\" areaUnit=\"squareMeter\" volumeUnit=\"cubicMeter\" " +
                       "temperatureUnit=\"celsius\" pressureUnit=\"milliBars\" angularUnit=\"decimal degrees\" " +
                       "directionUnit=\"decimal degrees\"/></Units>";
            string lin = string.Equals(unidad, "USSurveyFoot", StringComparison.OrdinalIgnoreCase) ? "USSurveyFoot" : "foot";
            return "<Units><Imperial linearUnit=\"" + lin + "\" areaUnit=\"squareFoot\" volumeUnit=\"cubicFeet\" " +
                   "temperatureUnit=\"fahrenheit\" pressureUnit=\"inchHG\" angularUnit=\"decimal degrees\" " +
                   "directionUnit=\"decimal degrees\"/></Units>";
        }

        private static readonly Regex RxUnits = new Regex(@"<Units\b[^>]*/>|<Units\b[^>]*>.*?</Units\s*>",
            RegexOptions.Singleline | RegexOptions.IgnoreCase);
        private static readonly Regex RxCs = new Regex(@"<CoordinateSystem\b[^>]*/>|<CoordinateSystem\b[^>]*>.*?</CoordinateSystem\s*>",
            RegexOptions.Singleline | RegexOptions.IgnoreCase);
        private static readonly Regex RxLandXml = new Regex(@"<LandXML\b[^>]*>", RegexOptions.IgnoreCase);
        private static readonly Regex RxLineal = new Regex(@"linearUnit\s*=\s*""([^""]*)""", RegexOptions.IgnoreCase);

        /// <summary>linearUnit del &lt;Units&gt; del LandXML («» si no hay).</summary>
        public static string UnidadDelArchivo(string xml)
        {
            var mu = RxUnits.Match(xml ?? "");
            if (!mu.Success) return "";
            var ml = RxLineal.Match(mu.Value);
            return ml.Success ? ml.Groups[1].Value : "";
        }

        /// <summary>
        /// Copia del LandXML con el &lt;Units&gt; igual a la unidad del dibujo y sin
        /// &lt;CoordinateSystem&gt;: Civil 3D no escala ni transforma, los números quedan
        /// tal cual. Lo demás del texto no cambia. Sin &lt;Units&gt;, se agrega tras &lt;LandXML&gt;.
        /// </summary>
        public static string ReescribirUnidades(string xml, string unidadDibujo)
        {
            if (xml == null) throw new ArgumentNullException(nameof(xml));
            string bloque = BloqueUnidades(unidadDibujo);
            string r = RxCs.Replace(xml, "");
            if (RxUnits.IsMatch(r))
                return RxUnits.Replace(r, bloque, 1);
            var ml = RxLandXml.Match(r);
            if (!ml.Success) throw new FormatException("No es un LandXML: falta <LandXML>.");
            return r.Insert(ml.Index + ml.Length, bloque);
        }

        /// <summary>Texto del archivo respetando el BOM (UTF-8 por defecto).</summary>
        public static string Texto(byte[] datos)
        {
            using (var sr = new StreamReader(new MemoryStream(datos), new UTF8Encoding(false), true))
                return sr.ReadToEnd();
        }

        /// <summary>Nombre libre: «NAME», si no «NAME (2)», «NAME (3)»…</summary>
        public static string NombreLibre(string nombre, ICollection<string> existentes)
        {
            bool usado(string n) => existentes.Any(e => string.Equals(e, n, StringComparison.OrdinalIgnoreCase));
            if (!usado(nombre)) return nombre;
            for (int i = 2; ; i++)
            {
                string n = $"{nombre} ({i})";
                if (!usado(n)) return n;
            }
        }

        /// <summary>Una comprobación: ok + texto para la consola.</summary>
        public sealed class Linea
        {
            public bool Ok; public string Texto;
            public override string ToString() => (Ok ? "✔ " : "⚠ ") + Texto;
        }

        private static string F(double v) => v.ToString("0.######", CultureInfo.InvariantCulture);

        private static void Valor(List<Linea> r, string que, double? esperado, double medido, double tol)
        {
            if (!esperado.HasValue) return;
            double d = Math.Abs(esperado.Value - medido);
            r.Add(new Linea
            {
                Ok = d <= tol,
                Texto = d <= tol ? $"{que} = {F(medido)}" : $"{que}: Civil 3D {F(medido)}, esperado {F(esperado.Value)} (difiere {d:G3})",
            });
        }

        private static void Cuenta(List<Linea> r, string que, int? esperado, int medido)
        {
            if (!esperado.HasValue) return;
            bool ok = esperado.Value == medido;
            r.Add(new Linea { Ok = ok, Texto = ok ? $"{que} = {medido}" : $"{que}: Civil 3D {medido}, esperado {esperado.Value}" });
        }

        /// <summary>
        /// Compara lo creado con lo esperado: puntos y triángulos exactos, ZMIN/ZMAX y
        /// recuadro ±1e-6, cada muestra ±1e-4 con <paramref name="cota"/> (null = fuera de la superficie).
        /// </summary>
        public static List<Linea> Comparar(Registro e, Medido m, Func<double, double, double?> cota)
        {
            var r = new List<Linea>();
            Cuenta(r, "Puntos", e.NPuntos, m.NPuntos);
            Cuenta(r, "Triángulos", e.NTriangulos, m.NTriangulos);
            Valor(r, "ZMIN", e.ZMin, m.ZMin, TOL_Z);
            Valor(r, "ZMAX", e.ZMax, m.ZMax, TOL_Z);
            Valor(r, "XMIN", e.XMin, m.XMin, TOL_RECUADRO);
            Valor(r, "YMIN", e.YMin, m.YMin, TOL_RECUADRO);
            Valor(r, "XMAX", e.XMax, m.XMax, TOL_RECUADRO);
            Valor(r, "YMAX", e.YMax, m.YMax, TOL_RECUADRO);
            if (cota != null && e.Muestras.Count > 0)
            {
                int ok = 0;
                foreach (var (x, y, z) in e.Muestras)
                {
                    double? zc = null;
                    try { zc = cota(x, y); } catch { zc = null; }
                    if (zc.HasValue && Math.Abs(zc.Value - z) <= TOL_MUESTRA) { ok++; continue; }
                    r.Add(new Linea
                    {
                        Ok = false,
                        Texto = zc.HasValue
                            ? $"Muestra ({F(x)}, {F(y)}): Civil 3D {F(zc.Value)}, esperado {F(z)} (difiere {Math.Abs(zc.Value - z):G3})"
                            : $"Muestra ({F(x)}, {F(y)}): fuera de la superficie (esperado {F(z)})",
                    });
                }
                if (ok > 0) r.Add(new Linea { Ok = true, Texto = $"Muestras con su cota: {ok} de {e.Muestras.Count}" });
            }
            return r;
        }

        /// <summary>¿Una superficie existente es ya ésta? (cuentas, cotas y recuadro iguales; sin muestras).</summary>
        public static bool Coincide(Registro e, Medido m)
        {
            if (!e.NPuntos.HasValue || !e.NTriangulos.HasValue) return false;
            return Comparar(e, m, null).All(l => l.Ok);
        }
    }
}
