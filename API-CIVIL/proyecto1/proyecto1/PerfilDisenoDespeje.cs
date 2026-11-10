using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DESPEJE FINAL DE RÓTULOS (PURO, sin Autodesk; 2026-11-08)
//   La verificación (G.12) medía rótulos encimados o fuera del marco y solo avisaba:
//   la corrección (G.11) lleva cada rótulo a SU destino y, si los destinos ya se
//   pisaban con las medidas reales, no había nada que mover (log de Agua-1-pp:
//   «solape N3|N4», «fuera del marco T0»). Con las cajas MEDIDAS (in, marco):
//    1. cada caja entra al marco (si es más grande que él, pegada al borde izq./inf.);
//    2. barrido de izquierda a derecha: una caja que pisa a otra de su misma altura
//       se corre a la derecha; si así sale del marco, barrido de derecha a izquierda;
//    3. lo que aún se pisa (no cabe a lo ancho) sube encima de la otra, o baja si
//       arriba no cabe.
//   Devuelve el desplazamiento (in) de cada caja que se mueve más de la tolerancia.
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilDisenoDespeje
    {
        public const double SEPARACION = 0.04;   // in entre rótulos despejados

        internal static Dictionary<string, (double dx, double dy)> Despejar(IReadOnlyList<Caja> cajas, double ancho, double alto,
                                                                         double margen = PerfilDiseno.MARGEN_MARCO,
                                                                         double tol = PerfilDiseno.TOL_SOLAPE)
        {
            var c = cajas.Select(k => new Caja { Id = k.Id, X0 = k.X0, Y0 = k.Y0, X1 = k.X1, Y1 = k.Y1 }).ToList();
            double xMin = margen, xMax = ancho - margen, yMin = margen, yMax = alto - margen;
            foreach (var k in c) AlMarco(k, xMin, xMax, yMin, yMax);

            bool MismaAltura(Caja a, Caja b) => Math.Min(a.Y1, b.Y1) - Math.Max(a.Y0, b.Y0) > tol;
            // 2. izquierda → derecha
            var orden = c.OrderBy(k => k.X0).ThenBy(k => k.Id, StringComparer.Ordinal).ToList();
            for (int i = 1; i < orden.Count; i++)
                for (int j = 0; j < i; j++)
                {
                    var a = orden[j]; var b = orden[i];
                    if (MismaAltura(a, b) && b.X0 < a.X1 + SEPARACION - tol && b.X1 > a.X0 + tol) Correr(b, a.X1 + SEPARACION - b.X0, 0);
                }
            // derecha → izquierda si alguna salió del marco
            if (c.Any(k => k.X1 > xMax + tol))
            {
                orden = c.OrderByDescending(k => k.X1).ThenBy(k => k.Id, StringComparer.Ordinal).ToList();
                foreach (var k in orden) if (k.X1 > xMax) Correr(k, xMax - k.X1, 0);
                for (int i = 1; i < orden.Count; i++)
                    for (int j = 0; j < i; j++)
                    {
                        var a = orden[j]; var b = orden[i];
                        if (MismaAltura(a, b) && b.X1 > a.X0 - SEPARACION + tol && b.X0 < a.X1 - tol) Correr(b, a.X0 - SEPARACION - b.X1, 0);
                    }
                foreach (var k in c) if (k.X0 < xMin) Correr(k, xMin - k.X0, 0);
            }
            // 3. lo que no cupo a lo ancho: arriba de la otra (o abajo)
            for (int vuelta = 0; vuelta < c.Count; vuelta++)
            {
                bool movio = false;
                for (int i = 0; i < c.Count; i++)
                    for (int j = i + 1; j < c.Count; j++)
                    {
                        if (!PerfilDiseno.Solapan(c[i], c[j], tol)) continue;
                        var b = c[j].Y0 >= c[i].Y0 ? c[j] : c[i]; var a = ReferenceEquals(b, c[j]) ? c[i] : c[j];
                        double sube = a.Y1 + SEPARACION - b.Y0, baja = a.Y0 - SEPARACION - b.Y1;
                        if (b.Y1 + sube <= yMax + tol) Correr(b, 0, sube);
                        else if (b.Y0 + baja >= yMin - tol) Correr(b, 0, baja);
                        else continue;
                        movio = true;
                    }
                if (!movio) break;
            }

            var r = new Dictionary<string, (double, double)>();
            for (int i = 0; i < c.Count; i++)
            {
                double dx = c[i].X0 - cajas[i].X0, dy = c[i].Y0 - cajas[i].Y0;
                if (Math.Abs(dx) > tol || Math.Abs(dy) > tol) r[c[i].Id] = (dx, dy);
            }
            return r;
        }

        private static void AlMarco(Caja k, double xMin, double xMax, double yMin, double yMax)
        {
            if (k.X1 - k.X0 > xMax - xMin || k.X0 < xMin) Correr(k, xMin - k.X0, 0);
            else if (k.X1 > xMax) Correr(k, xMax - k.X1, 0);
            if (k.Y1 - k.Y0 > yMax - yMin || k.Y0 < yMin) Correr(k, 0, yMin - k.Y0);
            else if (k.Y1 > yMax) Correr(k, 0, yMax - k.Y1);
        }

        private static void Correr(Caja k, double dx, double dy) { k.X0 += dx; k.X1 += dx; k.Y0 += dy; k.Y1 += dy; }
    }
}
