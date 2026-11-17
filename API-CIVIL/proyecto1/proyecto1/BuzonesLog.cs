using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

// ============================================================================
//  Registro de tapa / fondo de cada buzón en IMPORTAR_RED (2026-11-14).
//
//  Reporte del usuario: el Event Viewer de Civil 3D sigue avisando «Rim to Sump Height» en
//  Structure - (6) y (8) aunque la altura final de cada buzón queda dentro del rango. Ese
//  nombre por defecto es el que tiene el buzón ANTES de que IMPORTAR_RED le ponga su código,
//  así que el aviso nace al crearlo o al escribir su tapa/fondo por primera vez. Para saber
//  en cuál escritura y con qué valores, cada paso queda anotado en %TEMP%\PDFCAD_Buzones.log
//  (se reescribe en cada IMPORTAR_RED): altura justo después de crear, rango leído de la pieza,
//  cada escritura con lo que Civil 3D dejó, y lo mismo al reponer las cotas tras conectar.
// ============================================================================

namespace Civil3DBasico
{
    public static class BuzonesLog
    {
        static readonly StringBuilder _sb = new StringBuilder();
        public static int FueraDeRango { get; private set; }

        public static string Ruta
        {
            get
            {
                try { return Path.Combine(Path.GetTempPath(), "PDFCAD_Buzones.log"); }
                catch { return "PDFCAD_Buzones.log"; }
            }
        }

        public static void Empezar()
        {
            _sb.Clear();
            FueraDeRango = 0;
            _sb.AppendLine($"IMPORTAR_RED {DateTime.Now:yyyy-MM-dd HH:mm:ss} — tapa / fondo de cada buzón (pies)");
        }

        public static string Rango((double min, double max)? r) =>
            r.HasValue ? $"{r.Value.min:F3}–{r.Value.max:F3}" : "no leído";

        /// <summary>Una línea; si la altura (tapa − fondo) cae fuera del rango la marca con «FUERA».</summary>
        public static void Anotar(string buzon, string paso, double rim, double sump, (double min, double max)? r)
        {
            double h = rim - sump;
            bool fuera = r.HasValue && (h < r.Value.min - 1e-4 || h > r.Value.max + 1e-4);
            if (fuera) FueraDeRango++;
            _sb.AppendLine($"{buzon,-28} {paso,-28} tapa {rim,10:F3}  fondo {sump,10:F3}  altura {h,8:F3}  " +
                           $"rango {Rango(r)}{(fuera ? "   ← FUERA DEL RANGO" : "")}");
        }

        public static void Texto(string linea) => _sb.AppendLine(linea);

        public static bool Guardar()
        {
            try { File.WriteAllText(Ruta, _sb.ToString(), Encoding.UTF8); return true; }
            catch { return false; }
        }
    }
}
