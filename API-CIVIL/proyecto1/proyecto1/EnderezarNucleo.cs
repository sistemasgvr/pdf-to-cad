using System;
using System.Collections.Generic;

// ============================================================================
//  Núcleo PURO (sin Autodesk) del enderezado de quiebres mínimos — lo usa
//  ImportarRedEnderezar.cs y lo prueba el arnés API-CIVIL/proyecto1/PerfilPruebas.
//   Un vértice interior se quita si el camino gira ≤ giroMax en él, no está
//   bloqueado (estructura, curva, otra tubería…), no es el ANCLA de una curva
//   (su vecino actual es un vértice curvo: el plugin mide con él cuánto tubo tiene
//   el codo; sin él dos codos pasarían a compartir tramo y podría bajar el radio),
//   la pieza es la misma a ambos
//   lados y, contra la recta que une a sus vecinos que QUEDAN, él y todos los ya
//   quitados en ese tramo están a ≤ tolXY y con su cota sobre la pendiente (≤ tolZ,
//   sin caída en el vértice). Los extremos nunca se mueven.
// ============================================================================

namespace Civil3DBasico
{
    internal static class EnderezarNucleo
    {
        public const double GIRO_MAX_DEG = 2.0;
        public const double DESVIO_MAX_FT = 0.25;
        public const double COTA_TOL_FT = 0.01;

        /// <summary>Giro (grados) en b del camino a→b→c; 0 = sigue recto.</summary>
        public static double Giro(double ax, double ay, double bx, double by, double cx, double cy)
        {
            double ux = bx - ax, uy = by - ay, wx = cx - bx, wy = cy - by;
            double lu = Math.Sqrt(ux * ux + uy * uy), lw = Math.Sqrt(wx * wx + wy * wy);
            if (lu < 1e-9 || lw < 1e-9) return 0;
            double c = Math.Max(-1.0, Math.Min(1.0, (ux * wx + uy * wy) / (lu * lw)));
            return Math.Acos(c) * 180.0 / Math.PI;
        }

        /// <summary>
        /// Índices ORIGINALES (ascendentes) de los vértices a quitar. `zOut`/`zIn` =
        /// cota saliente/entrante de cada vértice; `bloqueado[i]` = no se puede quitar;
        /// `pieza[s]` = familia/tamaño del tramo s (s → s+1); `curva[i]` = vértice de
        /// codo (null = ninguno): sus vecinos que queden son su ancla y no se quitan.
        /// </summary>
        public static List<int> VerticesAQuitar(IList<double> xs, IList<double> ys,
            IList<double> zOut, IList<double> zIn, IList<bool> bloqueado, IList<string> pieza,
            double tolXY, double tolZ, IList<bool> curva = null, double giroMax = GIRO_MAX_DEG)
        {
            int n0 = xs.Count;
            var vivos = new List<int>();
            for (int i = 0; i < n0; i++) vivos.Add(i);
            var quitados = new List<int>();
            bool cambio = true;
            while (cambio)
            {
                cambio = false;
                for (int k = 1; k + 1 < vivos.Count; k++)
                {
                    int a = vivos[k - 1], m = vivos[k], b = vivos[k + 1];
                    if (bloqueado[m]) continue;
                    if (curva != null && (curva[a] || curva[b])) continue;   // ancla de un codo
                    if (Giro(xs[a], ys[a], xs[m], ys[m], xs[b], ys[b]) > giroMax) continue;
                    if ((pieza[a] ?? "") != (pieza[m] ?? "")) continue;
                    if (!SobreLaRecta(xs, ys, zOut, zIn, a, b, tolXY, tolZ)) continue;
                    vivos.RemoveAt(k);
                    quitados.Add(m);
                    cambio = true;
                    k--;
                }
            }
            quitados.Sort();
            return quitados;
        }

        /// <summary>
        /// Todos los vértices originales entre a y b (exclusive) quedan a ≤ tolXY de la
        /// recta a→b y con cota (sin caída) a ≤ tolZ de la pendiente zOut[a] → zIn[b].
        /// </summary>
        private static bool SobreLaRecta(IList<double> xs, IList<double> ys, IList<double> zOut, IList<double> zIn,
                                         int a, int b, double tolXY, double tolZ)
        {
            double dx = xs[b] - xs[a], dy = ys[b] - ys[a];
            double l = Math.Sqrt(dx * dx + dy * dy);
            if (l < 1e-9) return false;
            for (int j = a + 1; j < b; j++)
            {
                double px = xs[j] - xs[a], py = ys[j] - ys[a];
                if (Math.Abs(dx * py - dy * px) / l > tolXY) return false;
                if (Math.Abs(zOut[j] - zIn[j]) > tolZ) return false;
                double t = Math.Max(0.0, Math.Min(1.0, (dx * px + dy * py) / (l * l)));
                double zRecta = zOut[a] + (zIn[b] - zOut[a]) * t;
                if (Math.Abs(zRecta - zIn[j]) > tolZ) return false;
            }
            return true;
        }
    }
}
