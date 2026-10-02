using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

// ============================================================================
//  TEXTOS DEL PERFIL — PURO (DISENO.md H)
//   · Formatos en cultura invariante, abreviatura de materiales, plantillas
//     EN INGLÉS de callouts / tramos / cruces / título, saneado para MText y
//     parser tolerante de la XDATA PDFCAD_FITTING.
//   · Sin Autodesk: lo compila también el arnés PerfilPruebas.
//   · Las funciones Lineas* devuelven las líneas SIN sanear; el saneado (H.8)
//     se aplica al escribir la etiqueta (UnirLineas) o al guardar en Callout.
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>Clase de red para las plantillas (mismo orden que TipoRed: el llamador hace (ClaseRed)(int)tipo).</summary>
    internal enum ClaseRed { Gravedad, Conduit, Presion }

    /// <summary>Entrada de invert en una estructura de gravedad (H.3, línea «INV IN»).</summary>
    internal sealed class EntradaInvert
    {
        public double Inv;                               // ft
        public double DiamIn;                            // in
        public string Lado = "";                         // "LT" | "RT" | "" (tubo del recorrido)
        public bool Ramal;
    }

    internal static class PerfilTextos
    {
        internal const string GRADO = "%%d";                               // única constante (I-5)
        internal const string TITULO_ESTACION = "STATION (FT)";            // E.8 «Eje Titulo»
        internal const string TITULO_ELEVACION = "ELEVATION (FT)";         // E.2 ejes izquierdo/derecho
        internal const string TEXTO_RASANTE = "EX. GRADE";                 // H.5
        internal const int MAX_LINEAS_ESTRUCTURA = 6;                      // H.3
        internal const int MAX_CAR_RED = 24;                               // H.5

        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;
        private static readonly double[] ANGULOS_ESTANDAR = { 11.25, 22.5, 45, 90 };

        // ------------------------------------------------------------ H.1 formatos

        /// <summary>"1+05.14": redondeo AwayFromZero; si |e| &lt; 0.5·10^-dec → 0 (sin "-0"). H.1.</summary>
        internal static string FormatoEstacion(double est, int decimales)
        {
            if (double.IsNaN(est) || double.IsInfinity(est)) return "";
            decimales = Math.Max(0, Math.Min(6, decimales));
            double r = Math.Round(Math.Abs(est), decimales, MidpointRounding.AwayFromZero);
            bool negativo = est < 0 && r > 0;
            double cientos = Math.Floor(r / 100.0 + 1e-9);
            double resto = r - cientos * 100.0;
            if (resto < 0) resto = 0;
            string fmt = decimales == 0 ? "00" : "00." + new string('0', decimales);
            string txt = resto.ToString(fmt, INV);
            // «100.00» por arrastre de coma flotante → sube una centena
            if (txt.StartsWith("100", StringComparison.Ordinal)) { cientos += 1; txt = 0.0.ToString(fmt, INV); }
            return (negativo ? "-" : "") + cientos.ToString("0", INV) + "+" + txt;
        }

        /// <summary>"745.43'" (dos decimales + apóstrofo). H.1.</summary>
        internal static string FormatoCota(double z)
        {
            double r = Math.Round(z, 2, MidpointRounding.AwayFromZero);
            if (r == 0) r = 0;                                          // sin "-0.00"
            return r.ToString("0.00", INV) + "'";
        }

        /// <summary>max(1, round(pulg)) + "\"". H.1.</summary>
        internal static string FormatoDiametro(double pulg)
        {
            double r = double.IsNaN(pulg) ? 1 : Math.Max(1, Math.Round(pulg, MidpointRounding.AwayFromZero));
            return r.ToString("0", INV) + "\"";
        }

        /// <summary>Estándar {11.25, 22.5, 45, 90} si |Δ| ≤ 1.0; si no F1 sin ".0"; + GRADO. H.1.</summary>
        internal static string FormatoAngulo(double grados)
        {
            double g = Math.Abs(grados);
            foreach (double s in ANGULOS_ESTANDAR)
                if (Math.Abs(g - s) <= 1.0) return s.ToString("0.##", INV) + GRADO;
            string t = Math.Round(g, 1, MidpointRounding.AwayFromZero).ToString("0.0", INV);
            if (t.EndsWith(".0", StringComparison.Ordinal)) t = t.Substring(0, t.Length - 2);
            return t + GRADO;
        }

        /// <summary>(|ratio|·100).ToString("0.00") + "%". H.1.</summary>
        internal static string FormatoPendiente(double ratio)
        {
            return Math.Round(Math.Abs(ratio) * 100.0, 2, MidpointRounding.AwayFromZero).ToString("0.00", INV) + "%";
        }

        /// <summary>max(1, round(ft, AwayFromZero)) como entero. H.1.</summary>
        internal static string FormatoLongitud(double ft)
        {
            double r = double.IsNaN(ft) ? 1 : Math.Max(1, Math.Round(ft, MidpointRounding.AwayFromZero));
            return r.ToString("0", INV);
        }

        /// <summary>Sin tildes y en minúsculas (para comparar).</summary>
        private static string Plano(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            string d = s.Normalize(NormalizationForm.FormD);
            var sb = new StringBuilder(d.Length);
            foreach (char c in d)
                if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(c);
            return sb.ToString().Normalize(NormalizationForm.FormC);
        }

        /// <summary>Abreviatura del material (DI, CSP, RCP, PVC, ABS, HDPE, STL…); "" si no definido. H.2.</summary>
        internal static string AbreviarMaterial(string m)
        {
            string p = Plano(m ?? "").Trim();
            string l = p.ToLowerInvariant();
            if (l.Length == 0 || l == "material sin definir") return "";
            if (l.Contains("ductil")) return "DI";
            if (l.Contains("corrugado")) return "CSP";
            if (l.Contains("hormigon") || l.Contains("concreto")) return "RCP";
            if (l.Contains("pvc")) return "PVC";
            if (l.Contains("abs")) return "ABS";
            if (l.Contains("hdpe") || l.Contains("polietileno")) return "HDPE";
            if (l.Contains("acero")) return "STL";
            string u = p.ToUpperInvariant();
            return u.Length > 10 ? u.Substring(0, 10).TrimEnd() : u;
        }

        /// <summary>Une con espacio las partes no vacías. H.2.</summary>
        internal static string Unir(params string[] partes)
        {
            if (partes == null) return "";
            return string.Join(" ", partes.Where(p => !string.IsNullOrWhiteSpace(p)).Select(p => p.Trim()));
        }

        /// <summary>Número con coma o punto decimal (el último separador manda). false si vacío o inválido. H.6.</summary>
        internal static bool NumeroTolerante(string s, out double v)
        {
            v = double.NaN;
            if (s == null) return false;
            string t = s.Trim();
            if (t.Length == 0) return false;
            int iComa = t.LastIndexOf(','), iPunto = t.LastIndexOf('.');
            if (iComa >= 0 && iPunto >= 0)
            {
                if (iComa > iPunto) t = t.Replace(".", "").Replace(',', '.');
                else t = t.Replace(",", "");
            }
            else if (iComa >= 0) t = t.Replace(',', '.');
            if (!double.TryParse(t, NumberStyles.Float, INV, out double r)) return false;
            if (double.IsNaN(r) || double.IsInfinity(r)) return false;
            v = r; return true;
        }

        /// <summary>"CLAVE=valor" → dic[CLAVE en mayúsculas] = valor (la última gana; sin '=' se ignora). H.6.</summary>
        internal static Dictionary<string, string> ParsearXData(IEnumerable<string> lineas)
        {
            var d = new Dictionary<string, string>(StringComparer.Ordinal);
            if (lineas == null) return d;
            foreach (string linea in lineas)
            {
                if (linea == null) continue;
                int eq = linea.IndexOf('=');
                if (eq <= 0) continue;
                string k = linea.Substring(0, eq).Trim().ToUpperInvariant();
                if (k.Length == 0) continue;
                d[k] = linea.Substring(eq + 1);
            }
            return d;
        }

        /// <summary>Valor numérico tolerante de una clave; NaN si falta o no es número. H.6.</summary>
        internal static double Num(Dictionary<string, string> d, string clave)
        {
            if (d == null || clave == null) return double.NaN;
            if (!d.TryGetValue(clave.Trim().ToUpperInvariant(), out string s)) return double.NaN;
            return NumeroTolerante(s, out double v) ? v : double.NaN;
        }

        /// <summary>Texto de una clave (trim); "" si falta. H.6.</summary>
        internal static string Txt(Dictionary<string, string> d, string clave)
        {
            if (d == null || clave == null) return "";
            return d.TryGetValue(clave.Trim().ToUpperInvariant(), out string s) ? (s ?? "").Trim() : "";
        }

        /// <summary>MAYÚSCULAS sin tildes, escapa \ { } y conserva "%%d" en minúscula. H.8.</summary>
        internal static string Sanear(string texto)
        {
            if (string.IsNullOrEmpty(texto)) return "";
            const string MARCA = "\u0001";
            string t = texto.Replace("%%d", MARCA).Replace("%%D", MARCA);
            t = Plano(t).ToUpperInvariant();
            t = t.Replace("\\", "\\\\").Replace("{", "\\{").Replace("}", "\\}");
            t = t.Replace("\r", " ").Replace("\n", " ");
            return t.Replace(MARCA, GRADO);
        }

        /// <summary>Sanea cada línea y las une con "\P"; nunca devuelve "" (mínimo " "). H.8 / G.5-3.</summary>
        internal static string UnirLineas(IEnumerable<string> lineas)
        {
            if (lineas == null) return " ";
            string r = string.Join("\\P", lineas.Where(l => l != null).Select(Sanear));
            return string.IsNullOrWhiteSpace(r) ? " " : r;
        }

        /// <summary>Nombre de red apto para nombres de objeto: cada carácter de &lt;&gt;/\":;?*|,=` → '-', con trim. D.1.</summary>
        internal static string SanearNombre(string nombre)
        {
            if (string.IsNullOrEmpty(nombre)) return "";
            const string MALOS = "<>/\\\":;?*|,=`";
            var sb = new StringBuilder(nombre.Length);
            foreach (char c in nombre) sb.Append(MALOS.IndexOf(c) >= 0 ? '-' : c);
            return sb.ToString().Trim();
        }

        // ------------------------------------------------------------ piezas comunes

        private static string Sta(double est) { return "PIPE STA " + FormatoEstacion(est, 2); }
        private static string Top(double z) { return "TOP ELEV " + FormatoCota(z); }
        private static string D(double pulg) { return FormatoDiametro(pulg); }
        private static string RedCorta(string red)
        {
            string r = (red ?? "").Trim().ToUpperInvariant();
            return r.Length > MAX_CAR_RED ? r.Substring(0, MAX_CAR_RED).TrimEnd() : r;
        }

        // ------------------------------------------------------------ H.3 callouts de nodo

        /// <summary>Inicio/fin en extremo libre: PIPE STA · END OF {D}" {MAT} PIPE · TOP ELEV (o INV ELEV en gravedad). H.3.</summary>
        internal static List<string> LineasExtremo(double est, double diamIn, string material, bool gravedad, double cota)
        {
            return new List<string>
            {
                Sta(est),
                Unir("END OF", D(diamIn), AbreviarMaterial(material), "PIPE"),
                (gravedad ? "INV ELEV " : "TOP ELEV ") + FormatoCota(cota),
            };
        }

        /// <summary>Tee con ramal en planta: PIPE STA · {Dm}" X {Dr}" TEE · {Dr}" BRANCH {LT|RT} · TOP ELEV. H.3.</summary>
        internal static List<string> LineasTee(double est, double dm, double dr, string lado, double top)
        {
            return new List<string> { Sta(est), D(dm) + " X " + D(dr) + " TEE", Unir(D(dr), "BRANCH", lado), Top(top) };
        }

        /// <summary>Tee con ramal vertical: … · {Dr}" VERT BRANCH {UP|DOWN} (sin sentido si ""). H.3.</summary>
        internal static List<string> LineasTeeVertical(double est, double dm, double dr, string sentido, double top)
        {
            return new List<string> { Sta(est), D(dm) + " X " + D(dr) + " TEE", Unir(D(dr), "VERT BRANCH", sentido), Top(top) };
        }

        /// <summary>Tee terminal: PIPE STA · {Dm}" X {Dr}" TEE · TOP ELEV. H.3.</summary>
        internal static List<string> LineasTeeTerminal(double est, double dm, double dr, double top)
        {
            return new List<string> { Sta(est), D(dm) + " X " + D(dr) + " TEE", Top(top) };
        }

        /// <summary>Wye: PIPE STA · {Dm}" X {Dr}" WYE · {Dr}" BRANCH {LT|RT} {ang} · TOP ELEV. H.3.</summary>
        internal static List<string> LineasWye(double est, double dm, double dr, string lado, double anguloDeg, double top)
        {
            return new List<string>
            {
                Sta(est), D(dm) + " X " + D(dr) + " WYE",
                Unir(D(dr), "BRANCH", lado, double.IsNaN(anguloDeg) ? "" : FormatoAngulo(anguloDeg)), Top(top),
            };
        }

        /// <summary>Cruz: PIPE STA · {Dm}" X {Dr}" CROSS · {Dr}" BRANCHES LT &amp; RT · TOP ELEV. H.3.</summary>
        internal static List<string> LineasCruz(double est, double dm, double dr, double top)
        {
            return new List<string> { Sta(est), D(dm) + " X " + D(dr) + " CROSS", D(dr) + " BRANCHES LT & RT", Top(top) };
        }

        /// <summary>Codo: PIPE STA · {D}" X {ang} {HORIZ|VERT} {MAT} BEND · TOP ELEV. H.3.</summary>
        internal static List<string> LineasCodo(double est, double diamIn, double anguloDeg, bool vertical, string material, double top)
        {
            return new List<string>
            {
                Sta(est),
                Unir(D(diamIn), "X", FormatoAngulo(anguloDeg), vertical ? "VERT" : "HORIZ", AbreviarMaterial(material), "BEND"),
                Top(top),
            };
        }

        /// <summary>Reducción: PIPE STA · {D1}" X {D2}" REDUCER · TOP ELEV. H.3.</summary>
        internal static List<string> LineasReduccion(double est, double d1, double d2, double top)
        {
            return new List<string> { Sta(est), D(d1) + " X " + D(d2) + " REDUCER", Top(top) };
        }

        /// <summary>Deflexión de unión de presión: PIPE STA · {defl} DEFLECTION · TOP ELEV. H.3.</summary>
        internal static List<string> LineasDeflexion(double est, double deflDeg, double top)
        {
            return new List<string> { Sta(est), FormatoAngulo(deflDeg) + " DEFLECTION", Top(top) };
        }

        /// <summary>Quiebre de conduit: PIPE STA · {defl} {HORIZ|VERT} BEND · TOP ELEV. H.3.</summary>
        internal static List<string> LineasQuiebreConduit(double est, double deflDeg, bool vertical, double top)
        {
            return new List<string> { Sta(est), Unir(FormatoAngulo(deflDeg), vertical ? "VERT" : "HORIZ", "BEND"), Top(top) };
        }

        /// <summary>Estructura de gravedad: STA · NOMBRE · RIM ELEV · INV IN… (máx. 6 líneas) · INV OUT (NaN = sin salida). H.3.</summary>
        internal static List<string> LineasEstructura(double est, string nombre, double rim, IReadOnlyList<EntradaInvert> entradas, double invOut)
        {
            var cab = new List<string> { "STA " + FormatoEstacion(est, 2) };
            if (!string.IsNullOrWhiteSpace(nombre)) cab.Add(nombre.Trim());
            if (!double.IsNaN(rim)) cab.Add("RIM ELEV " + FormatoCota(rim));
            var ins = new List<string>();
            var validas = (entradas ?? new List<EntradaInvert>()).Where(e => e != null && !double.IsNaN(e.Inv)).ToList();
            foreach (var e in validas)
                ins.Add(e.Ramal || !string.IsNullOrEmpty(e.Lado)
                    ? "INV IN " + FormatoCota(e.Inv) + " (" + Unir(D(e.DiamIn), e.Lado) + ")"
                    : "INV IN " + FormatoCota(e.Inv));
            var pie = new List<string>();
            if (!double.IsNaN(invOut)) pie.Add("INV OUT " + FormatoCota(invOut));
            if (cab.Count + ins.Count + pie.Count > MAX_LINEAS_ESTRUCTURA && validas.Count > 1)
                ins = new List<string> { "INV IN " + FormatoCota(validas.Min(e => e.Inv)) + " (" + validas.Count.ToString(INV) + " BRANCHES)" };
            var r = new List<string>(cab); r.AddRange(ins); r.AddRange(pie);
            return r;
        }

        /// <summary>Línea de tramo omitido añadida al callout: INSTALL {L} LF {D}" {MAT}. F.7-1.</summary>
        internal static string LineaTramoOmitido(double largoFt, double diamIn, string material)
        {
            return Unir("INSTALL", FormatoLongitud(largoFt), "LF", D(diamIn), AbreviarMaterial(material));
        }

        // ------------------------------------------------------------ H.4 tramos

        /// <summary>L1/L2/L3 del rótulo de tramo según la clase y si está abandonado (L3 "@ {S}" solo en gravedad). H.4.</summary>
        internal static void LineasTramo(ClaseRed clase, bool abandonado, double largoFt, double diamIn, string material, double pendiente,
                                         out string l1, out string l2, out string l3)
        {
            string L = FormatoLongitud(largoFt), mat = AbreviarMaterial(material);
            if (abandonado)
            {
                l1 = L + " LF OF EXIST";
                l2 = Unir(D(diamIn), mat, "PIPE (ABANDONED)");
                l3 = "";
                return;
            }
            l1 = "INSTALL " + L + " LF OF";
            l2 = Unir("NEW", D(diamIn), mat, clase == ClaseRed.Conduit ? "CONDUIT" : "PIPE");
            l3 = clase == ClaseRed.Gravedad && !double.IsNaN(pendiente) ? "@ " + FormatoPendiente(pendiente) : "";
        }

        // ------------------------------------------------------------ H.5 cruces

        /// <summary>Un solo cruce: {D}" {MAT} PIPE (+ " (ABAND.)") · {RED ≤24} · INV ELEV (gravedad) / TOP ELEV (presión). H.5.</summary>
        internal static List<string> LineasCruceUno(double diamIn, string material, bool abandonado, string red, bool gravedad, double cota)
        {
            var r = new List<string> { Unir(D(diamIn), AbreviarMaterial(material), "PIPE") + (abandonado ? " (ABAND.)" : "") };
            string rc = RedCorta(red);
            if (rc.Length > 0) r.Add(rc);
            r.Add((gravedad ? "INV ELEV " : "TOP ELEV ") + FormatoCota(cota));
            return r;
        }

        /// <summary>Grupo de n: ({n}) {D}" {MAT} {PIPES|CONDUITS} · {RED} · TOP ELEV {min}-{max}. H.5.</summary>
        internal static List<string> LineasCruceGrupo(int n, IReadOnlyList<double> diamsIn, string material, bool conduit, string red, double zMin, double zMax)
        {
            var ds = (diamsIn ?? new List<double>()).Where(d => !double.IsNaN(d))
                .Select(d => Math.Max(1, Math.Round(d, MidpointRounding.AwayFromZero))).Distinct().OrderByDescending(d => d)
                .Select(d => d.ToString("0", INV) + "\"").ToList();
            string diam = ds.Count == 0 ? "" : string.Join("/", ds);
            var r = new List<string> { Unir("(" + n.ToString(INV) + ")", diam, AbreviarMaterial(material), conduit ? "CONDUITS" : "PIPES") };
            string rc = RedCorta(red);
            if (rc.Length > 0) r.Add(rc);
            r.Add(Math.Abs(zMax - zMin) < 0.005 ? "TOP ELEV " + FormatoCota(zMin)
                                                 : "TOP ELEV " + FormatoCota(zMin) + "-" + FormatoCota(zMax));
            return r;
        }

        /// <summary>Línea extra de separación: "{FormatoCota(clr)} CLR". H.5.</summary>
        internal static string LineaClaro(double claroFt) { return FormatoCota(claroFt) + " CLR"; }

        // ------------------------------------------------------------ H.7 título

        /// <summary>
        /// Título en 2 líneas: PROFILE {n}[ ({k}/{K})] - {Dpred} INCH {MAIN|PIPE|CONDUIT} - {RED} · HORIZ 1"={S}'  VERT 1"={V}'.
        /// k es 1-based; sin sufijo si hojas == 1. H.7.
        /// </summary>
        internal static List<string> LineasTitulo(int n, int hoja, int hojas, double dPredIn, ClaseRed clase, string red, double s, double v)
        {
            string tipo = clase == ClaseRed.Presion ? "MAIN" : (clase == ClaseRed.Conduit ? "CONDUIT" : "PIPE");
            string num = "PROFILE " + n.ToString(INV) + (hojas > 1 ? " (" + hoja.ToString(INV) + "/" + hojas.ToString(INV) + ")" : "");
            string l1 = num + " - " + FormatoLongitud(dPredIn) + " INCH " + tipo;
            string rc = (red ?? "").Trim().ToUpperInvariant();
            if (rc.Length > 0) l1 += " - " + rc;
            string l2 = "HORIZ 1\"=" + s.ToString("0.##", INV) + "'  VERT 1\"=" + v.ToString("0.##", INV) + "'";
            return new List<string> { l1, l2 };
        }
    }
}
