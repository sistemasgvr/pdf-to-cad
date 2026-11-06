using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: choques en 3D DE VERDAD (PURO). El adaptador de Civil 3D da los
//  CUERPOS (tuberías, estructuras, accesorios de presión, sólidos del plugin:
//  accesorios, válvulas, buzones sólidos, bancoductos) con su caja; aquí se
//  eligen los pares a probar (cajas que se tocan y que NO están unidos a
//  propósito) y, con lo que el adaptador midió (sólidos que se interfieren), se
//  arma la tabla S1, S2…
//  «Unidos a propósito»: la misma utilidad de la app; una tubería con su
//  estructura; tubería con tubería punta con punta; un accesorio, buzón sólido o
//  bancoducto con las tuberías que llegan a él (una punta dentro de su caja).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class Cuerpo
    {
        public string Handle, Tipo, Nombre, Red, Utilidad, Capa;   // Tipo: tuberia | estructura | accesorio | solido
        public double[] Min = new double[3], Max = new double[3];
        /// <summary>Tuberías: sus dos puntas (x, y). Vacío en los demás.</summary>
        public List<(double x, double y)> Puntas = new List<(double, double)>();
        public string EstructuraIni, EstructuraFin;
    }

    public sealed class Interferencia
    {
        public string A, B;          // handles
        public double X, Y, Z;       // centro de lo que se interfiere
        public double VolumenFt3;    // 0 = solo se tocan
    }

    public static class Choques3D
    {
        public const double HOLGURA_FT = 0.05;      // cajas que casi se tocan también se prueban
        public const double PUNTA_FT = 0.5;

        /// <summary>Pares (a, b) a probar: cajas que se tocan y que no están unidos a propósito.</summary>
        public static List<(Cuerpo a, Cuerpo b)> Pares(IList<Cuerpo> cs)
        {
            var r = new List<(Cuerpo, Cuerpo)>();
            var orden = cs.OrderBy(c => c.Min[0]).ToList();
            for (int i = 0; i < orden.Count; i++)
            {
                Cuerpo a = orden[i];
                for (int j = i + 1; j < orden.Count && orden[j].Min[0] <= a.Max[0] + HOLGURA_FT; j++)
                {
                    Cuerpo b = orden[j];
                    if (!Tocan(a, b, HOLGURA_FT) || Unidos(a, b)) continue;
                    r.Add((a, b));
                }
            }
            return r;
        }

        public static bool Tocan(Cuerpo a, Cuerpo b, double h) =>
            Enumerable.Range(0, 3).All(k => a.Min[k] <= b.Max[k] + h && b.Min[k] <= a.Max[k] + h);

        public static bool Unidos(Cuerpo a, Cuerpo b)
        {
            if (!string.IsNullOrEmpty(a.Utilidad) && Calculos.Igual(a.Utilidad, b.Utilidad)) return true;
            if (a.Tipo == "tuberia" && b.Tipo == "tuberia")
                return Calculos.Igual(a.Red, b.Red) && a.Puntas.Any(p => b.Puntas.Any(q => Metrados.D(p.x, p.y, q.x, q.y) <= PUNTA_FT));
            if (a.Tipo == "tuberia" || b.Tipo == "tuberia")
            {
                Cuerpo t = a.Tipo == "tuberia" ? a : b, o = a.Tipo == "tuberia" ? b : a;
                if (o.Tipo == "estructura" && (Calculos.Igual(t.EstructuraIni, o.Handle) || Calculos.Igual(t.EstructuraFin, o.Handle))) return true;
                return t.Puntas.Any(p => p.x >= o.Min[0] - PUNTA_FT && p.x <= o.Max[0] + PUNTA_FT &&
                                         p.y >= o.Min[1] - PUNTA_FT && p.y <= o.Max[1] + PUNTA_FT) &&
                       (string.IsNullOrEmpty(o.Red) || string.IsNullOrEmpty(t.Red) || Calculos.Igual(o.Red, t.Red) || o.Tipo == "solido");
            }
            // dos no-tuberías de la misma red en el mismo lugar (cuerpo y vástago de una válvula, brazos de una Wye…)
            return !string.IsNullOrEmpty(a.Red) && Calculos.Igual(a.Red, b.Red);
        }

        /// <summary>La tabla S1… de lo que de verdad se interfiere.</summary>
        public static object Tabla(IList<Cuerpo> cs, IList<Interferencia> hay, int limite, out int total)
        {
            var por = cs.ToDictionary(c => c.Handle, StringComparer.OrdinalIgnoreCase);
            var filas = hay.Where(i => por.ContainsKey(i.A) && por.ContainsKey(i.B))
                           .OrderByDescending(i => Math.Round(i.Y, 1)).ThenBy(i => i.X).ToList();
            total = filas.Count;
            return new
            {
                total,
                columnas = new[] { "id", "a", "tipo_a", "utilidad_a", "b", "tipo_b", "utilidad_b", "x", "y", "z", "volumen_ft3" },
                filas = filas.Take(limite).Select((i, k) => new object[]
                {
                    "S" + (k + 1), por[i.A].Nombre, por[i.A].Tipo, por[i.A].Utilidad, por[i.B].Nombre, por[i.B].Tipo, por[i.B].Utilidad,
                    Calculos.R2(i.X), Calculos.R2(i.Y), Calculos.R2(i.Z), Math.Round(i.VolumenFt3, 3),
                }).ToList(),
            };
        }
    }
}
