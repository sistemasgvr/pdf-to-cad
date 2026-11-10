using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  RECORRIDO ENTRE DOS TRAMOS (PURO, sin Autodesk) — espejo de
//  `app/nucleo/perfil_recorrido.entre`: el camino más corto por la red de la arista
//  de inicio a la de fin (las dos incluidas). Lo usa el perfil con inicio A y fin B
//  que manda la app: el recorrido automático (C.4) se detiene en una unión dudosa o
//  en un giro > 45° y, si B quedaba fuera, el perfil salía cortado («ELE-P1»).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilRecorridoEntre
    {
        /// <summary>Pasos de la arista <paramref name="eIni"/> a la <paramref name="eFin"/> por el camino más corto
        /// (largo en planta). Vacío si no hay camino o alguna no es válida.</summary>
        internal static List<PasoG> Entre(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int eIni, int eFin)
        {
            var r = new List<PasoG>();
            if (eIni < 0 || eFin < 0 || eIni >= a.Count || eFin >= a.Count || !a[eIni].Valida || !a[eFin].Valida) return r;
            if (eIni == eFin) { r.Add(new PasoG { Arista = eIni, Invertida = false }); return r; }
            GArista A = a[eIni], B = a[eFin];
            double mejor = double.MaxValue; List<int> mejorNodos = null, mejorAristas = null;
            foreach (int s in new[] { A.A, A.B })
            {
                var dist = new Dictionary<int, double> { [s] = 0 };
                var prev = new Dictionary<int, (int nodo, int arista)>();
                var cola = new SortedSet<(double d, int nodo)> { (0, s) };
                while (cola.Count > 0)
                {
                    var (d, nd) = cola.Min; cola.Remove(cola.Min);
                    foreach (int e in n[nd].Aristas)
                    {
                        if (e == eIni || e < 0 || e >= a.Count || !a[e].Valida) continue;
                        int m = a[e].A == nd ? a[e].B : a[e].A;
                        double nd2 = d + a[e].Largo;
                        if (dist.TryGetValue(m, out double dm) && dm <= nd2) continue;
                        if (dist.ContainsKey(m)) cola.Remove((dm, m));
                        dist[m] = nd2; prev[m] = (nd, e); cola.Add((nd2, m));
                    }
                }
                foreach (int t in new[] { B.A, B.B })
                {
                    if (!dist.TryGetValue(t, out double dt) || dt >= mejor) continue;
                    var nodos = new List<int> { t }; var aristas = new List<int>();
                    for (int x = t; x != s; x = prev[x].nodo) { aristas.Add(prev[x].arista); nodos.Add(prev[x].nodo); }
                    nodos.Reverse(); aristas.Reverse();
                    nodos.Insert(0, s == A.A ? A.B : A.A); aristas.Insert(0, eIni);
                    if (!aristas.Contains(eFin)) { nodos.Add(t == B.A ? B.B : B.A); aristas.Add(eFin); }
                    mejor = dt; mejorNodos = nodos; mejorAristas = aristas;
                }
            }
            if (mejorAristas == null) return r;
            for (int k = 0; k < mejorAristas.Count; k++)
                r.Add(new PasoG { Arista = mejorAristas[k], Invertida = a[mejorAristas[k]].A != mejorNodos[k] });
            return r;
        }

        /// <summary>Índice de la arista de <paramref name="tramos"/> (puntas en planta) más cercana a (x, y), a ≤ tol; −1 si ninguna.</summary>
        internal static int MasCercana(IReadOnlyList<(double ax, double ay, double bx, double by, bool valida)> tramos,
                                       double x, double y, double tol)
        {
            int mejor = -1; double dmin = tol;
            for (int i = 0; i < tramos.Count; i++)
            {
                var t = tramos[i];
                if (!t.valida) continue;
                double dx = t.bx - t.ax, dy = t.by - t.ay, l2 = dx * dx + dy * dy;
                double u = l2 <= 1e-12 ? 0 : System.Math.Max(0, System.Math.Min(1, ((x - t.ax) * dx + (y - t.ay) * dy) / l2));
                double px = t.ax + dx * u - x, py = t.ay + dy * u - y, d = System.Math.Sqrt(px * px + py * py);
                if (d < dmin - 1e-12) { dmin = d; mejor = i; }
            }
            return mejor;
        }
    }
}
