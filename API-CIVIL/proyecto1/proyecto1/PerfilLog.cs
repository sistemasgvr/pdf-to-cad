using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

// ============================================================================
//  LOG DEL PERFIL (DISENO.md A.1, G.0, G.13)
//   · %TEMP%\PDFCAD_Perfil.log: cada ejecución se AGREGA al final (CREAR_PERFIL_RED suelto o los
//     perfiles de IMPORTAR_RED); pasado MAX_BYTES se conserva solo la parte final.
//   · Lista de avisos para el resumen de la línea de comandos.
//   · Solo System.IO: nunca lanza (todo en try; un log roto no tumba el comando).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilLog
    {
        private static readonly List<string> _avisos = new List<string>();
        private static string _ruta;

        /// <summary>Ruta completa del log (%TEMP%\PDFCAD_Perfil.log).</summary>
        internal static string Ruta
        {
            get
            {
                if (_ruta == null)
                {
                    try { _ruta = Path.Combine(Path.GetTempPath(), "PDFCAD_Perfil.log"); }
                    catch { _ruta = "PDFCAD_Perfil.log"; }
                }
                return _ruta;
            }
        }

        /// <summary>Avisos acumulados en esta ejecución (texto en español, sin prefijo).</summary>
        internal static IReadOnlyList<string> Avisos { get { return _avisos; } }

        private static void Escribir(string linea)
        {
            try { File.AppendAllText(Ruta, linea + Environment.NewLine, Encoding.UTF8); } catch { }
        }

        /// <summary>Tope del archivo: al pasarlo, Iniciar deja solo la última mitad (se pierden los perfiles más viejos).</summary>
        internal const long MAX_BYTES = 4L * 1024 * 1024;

        /// <summary>Vacía avisos y AGREGA al archivo la cabecera (fecha, versión y nombre del perfil si se conoce). G.0.
        /// Antes reescribía el archivo y el log de un perfil se perdía con el siguiente («ELE-P1»).</summary>
        internal static void Iniciar(string nombre = null)
        {
            _avisos.Clear();
            try
            {
                Recortar();
                string ver = "";
                try { ver = typeof(PerfilLog).Assembly.GetName().Version?.ToString() ?? ""; } catch { }
                bool hay = File.Exists(Ruta) && new FileInfo(Ruta).Length > 0;
                var cab = (hay ? Environment.NewLine + new string('=', 70) + Environment.NewLine : "")
                          + "CREAR_PERFIL_RED — " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " — plugin " + ver
                          + (string.IsNullOrWhiteSpace(nombre) ? "" : " — perfil «" + nombre + "»") + Environment.NewLine;
                File.AppendAllText(Ruta, cab, Encoding.UTF8);
            }
            catch { }
        }

        private static void Recortar()
        {
            try
            {
                var fi = new FileInfo(Ruta);
                if (!fi.Exists || fi.Length <= MAX_BYTES) return;
                string txt = File.ReadAllText(Ruta, Encoding.UTF8);
                int corte = txt.IndexOf("CREAR_PERFIL_RED — ", txt.Length / 2, StringComparison.Ordinal);
                File.WriteAllText(Ruta, corte > 0 ? txt.Substring(corte) : txt.Substring(txt.Length / 2), Encoding.UTF8);
            }
            catch { }
        }

        /// <summary>Escribe una línea «[TAG] mensaje» (tag sin corchetes, p. ej. "GRAFO", "EJE", "ESTILO").</summary>
        internal static void Log(string tag, string mensaje) { Escribir("[" + (tag ?? "") + "] " + (mensaje ?? "")); }

        /// <summary>Registra un aviso: lo añade a Avisos y lo escribe como «[AVISO] mensaje».</summary>
        internal static void Aviso(string mensaje)
        {
            if (string.IsNullOrWhiteSpace(mensaje)) return;
            _avisos.Add(mensaje);
            Escribir("[AVISO] " + mensaje);
        }

        /// <summary>Registra un aviso con etiqueta: Avisos recibe «mensaje» y el log «[TAG] mensaje».</summary>
        internal static void Aviso(string tag, string mensaje)
        {
            if (string.IsNullOrWhiteSpace(mensaje)) return;
            _avisos.Add(mensaje);
            Escribir("[" + (tag ?? "") + "] " + mensaje);
        }

        /// <summary>Escribe «[TAG] ✗ contexto: tipo: mensaje» y la pila de la excepción.</summary>
        internal static void Error(string tag, string contexto, Exception ex)
        {
            if (ex == null) { Escribir("[" + tag + "] ✗ " + contexto); return; }
            Escribir("[" + tag + "] ✗ " + contexto + ": " + ex.GetType().Name + ": " + ex.Message);
            Escribir("    " + (ex.StackTrace ?? "").Replace(Environment.NewLine, Environment.NewLine + "    "));
        }

        /// <summary>Vuelca al log cada texto de una lista pura (avisos de PerfilDiseno, trazas de PerfilRecorrido) con su tag.</summary>
        internal static void Volcar(string tag, IEnumerable<string> lineas)
        {
            if (lineas == null) return;
            foreach (string l in lineas) Log(tag, l);
        }

        /// <summary>Los primeros <paramref name="max"/> avisos separados por "; " (G.13).</summary>
        internal static string ResumenAvisos(int max)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < _avisos.Count && i < max; i++)
            {
                if (i > 0) sb.Append("; ");
                sb.Append(_avisos[i]);
            }
            return sb.ToString();
        }
    }
}
