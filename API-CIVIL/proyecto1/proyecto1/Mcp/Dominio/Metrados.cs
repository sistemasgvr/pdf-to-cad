using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: metrados (PURO) — largo de tubería por utilidad/red, diámetro y
//  material; accesorios por tipo; buzones/cajas por tamaño. Accesorios: los
//  sólidos de un mismo accesorio (varios cuerpos en el mismo punto) cuentan uno.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    /// <summary>Un accesorio «de verdad»: los sólidos/piezas del mismo tipo en el mismo punto, juntos. Id A1…</summary>
    public sealed class GrupoAccesorio
    {
        public string Id, Tipo, Red;
        public double X, Y;
        public double? ZEje;
        public double RadioFt;
        public bool EsPieza;
        public List<string> Handles = new List<string>();
        public List<string> Conectadas = new List<string>();

        public bool EsValvula => Calculos.Contiene(Tipo, "valve") || Calculos.Contiene(Tipo, "valv");
    }

    public static class Metrados
    {
        public const double MISMO_PUNTO_FT = 0.05;

        /// <summary>Accesorios agrupados y numerados (de arriba abajo, de izquierda a derecha).</summary>
        public static List<GrupoAccesorio> Accesorios(Modelo m)
        {
            var g = new List<GrupoAccesorio>();
            foreach (Accesorio a in m.Accesorios)
            {
                var x = g.FirstOrDefault(k => Calculos.Igual(k.Tipo, a.Tipo) && Math.Abs(k.X - a.X) <= MISMO_PUNTO_FT &&
                                              Math.Abs(k.Y - a.Y) <= MISMO_PUNTO_FT);
                if (x == null)
                {
                    x = new GrupoAccesorio { Tipo = a.Tipo, Red = a.Red, X = a.X, Y = a.Y, ZEje = a.ZEje, RadioFt = a.RadioFt, EsPieza = a.EsPieza };
                    g.Add(x);
                }
                x.Handles.Add(a.Handle);
                x.RadioFt = Math.Max(x.RadioFt, a.RadioFt);
                x.Conectadas.AddRange(a.Conectadas.Where(h => !x.Conectadas.Contains(h)));
            }
            g = g.OrderByDescending(k => Math.Round(k.Y, 1)).ThenBy(k => k.X).ToList();
            for (int i = 0; i < g.Count; i++) g[i].Id = "A" + (i + 1);
            return g;
        }

        /// <summary>Tuberías de la red que llegan al accesorio (conectadas o con una punta en su alcance).</summary>
        public static List<Tuberia> Tuberias(Modelo m, GrupoAccesorio a) =>
            m.Tuberias.Where(t => a.Conectadas.Count > 0 ? a.Conectadas.Any(h => Calculos.Igual(h, t.Handle))
                : (string.IsNullOrEmpty(a.Red) || Calculos.Igual(a.Red, t.Red)) &&
                  (D(a.X, a.Y, t.XIni, t.YIni) <= a.RadioFt || D(a.X, a.Y, t.XFin, t.YFin) <= a.RadioFt)).ToList();

        public static double D(double ax, double ay, double bx, double by) => Math.Sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by));

        /// <summary>Metrados del dibujo (o de una red): tablas listas para mostrar.</summary>
        public static object Calcular(Modelo m, string red)
        {
            bool Es(string r) => string.IsNullOrWhiteSpace(red) || Calculos.Igual(r, red);
            var ts = m.Tuberias.Where(t => Es(t.Red)).ToList();
            var tub = ts.GroupBy(t => (u: string.IsNullOrEmpty(t.UtilidadCapa) ? t.Red : t.UtilidadCapa, d: Calculos.Diam(t.DiametroIn),
                                       mat: string.IsNullOrWhiteSpace(t.Material()) ? "—" : t.Material()))
                        .OrderBy(g => g.Key.u).ThenBy(g => g.First().DiametroIn)
                        .Select(g => new object[] { g.Key.u, g.Key.d, g.Key.mat, g.Count(), Calculos.R2(g.Sum(t => t.LargoFt)) }).ToList();
            var acc = Accesorios(m).Where(a => Es(a.Red) || string.IsNullOrEmpty(a.Red))
                                   .GroupBy(a => string.IsNullOrWhiteSpace(a.Tipo) ? "—" : a.Tipo.ToUpperInvariant())
                                   .OrderBy(g => g.Key).Select(g => new object[] { g.Key, g.Count() }).ToList();
            var est = m.Estructuras.Where(e => Es(e.Red) && !e.Nula)
                                   .GroupBy(e => string.IsNullOrWhiteSpace(e.Tamano) ? "—" : e.Tamano)
                                   .OrderBy(g => g.Key).Select(g => new object[] { g.Key, g.Count(), Calculos.R2(g.Sum(e => e.Profundidad() ?? 0)) }).ToList();
            return new
            {
                tuberias = new { columnas = new[] { "utilidad", "diam_in", "material", "cantidad", "largo_ft" }, filas = tub },
                accesorios = new { columnas = new[] { "tipo", "cantidad" }, filas = acc },
                estructuras = new { columnas = new[] { "tamano", "cantidad", "profundidad_total_ft" }, filas = est },
                totales = new
                {
                    largo_ft = Calculos.R2(ts.Sum(t => t.LargoFt)), tuberias = ts.Count,
                    accesorios = acc.Sum(f => (int)f[1]), estructuras = est.Sum(f => (int)f[1]),
                },
            };
        }
    }
}
