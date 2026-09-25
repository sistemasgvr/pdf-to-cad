using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

// ============================================================================
//  LOG DEL PERFIL (DISENO.md A.1, G.0, G.13)
//   · %TEMP%\PDFCAD_Perfil.log, se SOBRESCRIBE en cada ejecución.
//   · Lista de avisos para el resumen de la línea de comandos.
//   · Solo System.IO: nunca lanza (todo en try; un log roto no tumba el comando).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilLog
    {
        /// <summary>Ruta completa del log (%TEMP%\PDFCAD_Perfil.log).</summary>
        internal static string Ruta { get { return default; } }

        /// <summary>Avisos acumulados en esta ejecución (texto en español, sin prefijo).</summary>
        internal static IReadOnlyList<string> Avisos { get { return default; } }

        /// <summary>Vacía avisos y reescribe el archivo con la cabecera (fecha, versión). G.0.</summary>
        internal static void Iniciar() { throw new NotImplementedException(); }

        /// <summary>Escribe una línea «[TAG] mensaje» (tag sin corchetes, p. ej. "GRAFO", "EJE", "ESTILO").</summary>
        internal static void Log(string tag, string mensaje) { throw new NotImplementedException(); }

        /// <summary>Registra un aviso: lo añade a Avisos y lo escribe como «[AVISO] mensaje».</summary>
        internal static void Aviso(string mensaje) { throw new NotImplementedException(); }

        /// <summary>Registra un aviso con etiqueta: Avisos recibe «mensaje» y el log «[TAG] mensaje».</summary>
        internal static void Aviso(string tag, string mensaje) { throw new NotImplementedException(); }

        /// <summary>Escribe «[TAG] ✗ contexto: tipo: mensaje» y la pila de la excepción.</summary>
        internal static void Error(string tag, string contexto, Exception ex) { throw new NotImplementedException(); }

        /// <summary>Vuelca al log cada texto de una lista pura (avisos de PerfilDiseno, trazas de PerfilRecorrido) con su tag.</summary>
        internal static void Volcar(string tag, IEnumerable<string> lineas) { throw new NotImplementedException(); }

        /// <summary>Los primeros <paramref name="max"/> avisos separados por "; " (G.13).</summary>
        internal static string ResumenAvisos(int max) { throw new NotImplementedException(); }
    }
}
