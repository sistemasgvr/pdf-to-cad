using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO del MCP (PURO, sin Autodesk ni MCP): una FOTO del modelo de Civil 3D
//  en unidades imperiales (ft; diámetros en pulgadas) y las cuentas que la IA NO
//  debe hacer (resúmenes, filtros, profundidades). La IA solo elige y redacta.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public enum TipoRed { Gravedad, Presion }

    public sealed class Tuberia
    {
        public string Handle;
        public string Nombre;
        public string Red;
        public TipoRed TipoRed;
        public string Capa;
        public string Tamano;          // PartSizeName
        public string Familia;         // familia de la pieza (gravedad) o descripción del tubo (presión)
        public string Descripcion;
        public double DiametroIn;
        public double LargoFt;         // en planta
        public double XIni, YIni, XFin, YFin;
        public double? CotaIni, CotaFin;   // rasante (solera) en cada extremo
        public double? PendientePct;       // Slope de Civil 3D × 100
        public string EstructuraIni, EstructuraFin;   // handles
        /// <summary>Utilidad de la app de la que salió (Property Set «PDFCAD_Utilidad»): capa y número
        /// («AGUA», «20» = la AGUA-20 de la app). Vacío si el dibujo no viene de la app. Las tuberías de una
        /// misma utilidad se mueven juntas al resolver un conflicto.</summary>
        public string UtilidadCapa, UtilidadNumero;
        /// <summary>Tipo de la utilidad en la app (Property Set «PDFCAD_Utilidad», campo TIPO), p. ej.
        /// «DISTRIBUCION PRINCIPAL». Lo usan las normativas.</summary>
        public string TipoApp;
        /// <summary>Material: la importación lo escribe en la Descripción de la tubería.</summary>
        public string Material() => Descripcion;

        /// <summary>«AGUA-20» (como la nombra la app) o el nombre de la tubería si no viene de la app.</summary>
        public string Utilidad() => string.IsNullOrEmpty(UtilidadNumero) ? Nombre
            : $"{(string.IsNullOrEmpty(UtilidadCapa) ? Capa : UtilidadCapa)}-{UtilidadNumero}";

        public Tuberia Copia() => (Tuberia)MemberwiseClone();

        /// <summary>Pendiente calculada con las rasantes (la de Civil 3D puede faltar).</summary>
        public double? PendienteCalculada() =>
            CotaIni.HasValue && CotaFin.HasValue && LargoFt > 1e-6
                ? (CotaIni.Value - CotaFin.Value) / LargoFt * 100.0 : (double?)null;
    }

    public sealed class Estructura
    {
        public string Handle;
        public string Nombre;
        public string Red;
        public string Capa;
        public string Tamano;
        public double X, Y;
        public double? Rim, Sump;
        public int Conexiones;
        public bool Nula;             // estructura nula (vértice de conduit/presión), no es un buzón

        public double? Profundidad() => Rim.HasValue && Sump.HasValue ? Rim.Value - Sump.Value : (double?)null;
    }

    /// <summary>Accesorio de una red a presión: pieza de Civil 3D (codo, Tee… del catálogo) o sólido del plugin
    /// (XDATA PDFCAD_FITTING: codos, Tees, Wyes, cruces, válvulas). Se mueve junto con sus tuberías.</summary>
    public sealed class Accesorio
    {
        public string Handle;
        public string Tipo;
        public string Red;            // nombre de la red (vacío = no se sabe)
        public double X, Y;
        public double? ZEje;
        public double RadioFt;        // alcance en planta: las puntas de sus tuberías caen a esta distancia
        public bool EsPieza;          // pieza de Civil 3D (PressureFitting/Appurtenance); si no, sólido
        /// <summary>Handles de las tuberías conectadas (piezas de Civil 3D). Vacía en los sólidos: ahí se
        /// usan las puntas que caen a `RadioFt` de su centro.</summary>
        public List<string> Conectadas = new List<string>();
    }

    public sealed class EstadoDibujo
    {
        public string Dibujo;
        public string Unidades;
        public string SistemaCoordenadas;
        public int RedesGravedad, RedesPresion;
        public bool Ocupado;          // hay un comando en curso
        public string Comando;
    }

    public sealed class Modelo
    {
        public List<Tuberia> Tuberias = new List<Tuberia>();
        public List<Estructura> Estructuras = new List<Estructura>();
        public List<TextoDibujo> Textos = new List<TextoDibujo>();    // TEXT y MTEXT del espacio modelo
        public List<Accesorio> Accesorios = new List<Accesorio>();
        public List<Guia> Guias = new List<Guia>();                   // LEADER y MLEADER
        public List<Cota> Cotas = new List<Cota>();
        public List<Trama> Tramas = new List<Trama>();
    }

    // ---------------------------------------------------------------- resúmenes

    public sealed class ResumenRed
    {
        public string Red;
        public string Tipo;
        public int Tuberias;
        public int Estructuras;
        public double LargoFt;
        public Dictionary<string, int> DiametrosIn;   // «8» → 12 tuberías
        public List<string> Capas;
        public int SinCota;
        public int ContrapendienteONula;              // solo gravedad
    }

    public static class Calculos
    {
        public static double R2(double v) => Math.Round(v, 2);
        public static double? R2(double? v) => v.HasValue ? Math.Round(v.Value, 2) : (double?)null;

        public static List<ResumenRed> Resumen(Modelo m, string soloRed = null)
        {
            var redes = m.Tuberias.Select(t => t.Red)
                         .Concat(m.Estructuras.Select(e => e.Red))
                         .Where(r => r != null).Distinct()
                         .Where(r => string.IsNullOrEmpty(soloRed) || Igual(r, soloRed))
                         .OrderBy(r => r, StringComparer.OrdinalIgnoreCase);
            var res = new List<ResumenRed>();
            foreach (string red in redes)
            {
                var ts = m.Tuberias.Where(t => t.Red == red).ToList();
                var tipo = ts.Count > 0 ? ts[0].TipoRed : TipoRed.Gravedad;
                res.Add(new ResumenRed
                {
                    Red = red,
                    Tipo = tipo == TipoRed.Presion ? "presion" : "gravedad",
                    Tuberias = ts.Count,
                    Estructuras = m.Estructuras.Count(e => e.Red == red),
                    LargoFt = R2(ts.Sum(t => t.LargoFt)),
                    DiametrosIn = ts.GroupBy(t => Diam(t.DiametroIn))
                                    .OrderBy(g => double.Parse(g.Key, System.Globalization.CultureInfo.InvariantCulture))
                                    .ToDictionary(g => g.Key, g => g.Count()),
                    Capas = ts.Select(t => t.Capa).Where(c => !string.IsNullOrEmpty(c)).Distinct().OrderBy(c => c).Take(10).ToList(),
                    SinCota = ts.Count(t => !t.CotaIni.HasValue || !t.CotaFin.HasValue),
                    ContrapendienteONula = tipo == TipoRed.Gravedad ? ts.Count(t => (Pendiente(t) ?? 1) <= 0.0) : 0,
                });
            }
            return res;
        }

        public static string Diam(double inch) =>
            Math.Round(inch, 2).ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);

        public static double? Pendiente(Tuberia t) => t.PendientePct ?? t.PendienteCalculada();

        public static bool Igual(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);

        public static bool Contiene(string a, string texto) =>
            !string.IsNullOrEmpty(a) && a.IndexOf(texto, StringComparison.OrdinalIgnoreCase) >= 0;
    }

    // ---------------------------------------------------------------- filtros

    public sealed class FiltroTuberias
    {
        public string Red, Capa, Texto;
        public double? DiamMin, DiamMax, PendienteMax;

        public bool Cumple(Tuberia t)
        {
            if (!string.IsNullOrEmpty(Red) && !Calculos.Igual(t.Red, Red)) return false;
            if (!string.IsNullOrEmpty(Capa) && !Calculos.Contiene(t.Capa, Capa)) return false;
            if (DiamMin.HasValue && t.DiametroIn < DiamMin.Value - 1e-6) return false;
            if (DiamMax.HasValue && t.DiametroIn > DiamMax.Value + 1e-6) return false;
            if (PendienteMax.HasValue)
            {
                double? p = Calculos.Pendiente(t);
                if (t.TipoRed != TipoRed.Gravedad || !p.HasValue || p.Value > PendienteMax.Value + 1e-9) return false;
            }
            if (!string.IsNullOrEmpty(Texto) &&
                !(Calculos.Contiene(t.Nombre, Texto) || Calculos.Contiene(t.Tamano, Texto) ||
                  Calculos.Contiene(t.Descripcion, Texto) || Calculos.Contiene(t.Red, Texto))) return false;
            return true;
        }
    }

    public sealed class FiltroEstructuras
    {
        public string Red, Texto;
        public double? ProfundidadMin;

        public bool Cumple(Estructura e)
        {
            if (!string.IsNullOrEmpty(Red) && !Calculos.Igual(e.Red, Red)) return false;
            if (ProfundidadMin.HasValue && (e.Profundidad() ?? double.MinValue) < ProfundidadMin.Value) return false;
            if (!string.IsNullOrEmpty(Texto) &&
                !(Calculos.Contiene(e.Nombre, Texto) || Calculos.Contiene(e.Tamano, Texto))) return false;
            return true;
        }
    }
}
