using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  MAQUETACIÓN — FILA DE TRAMOS Y COMPLEMENTOS (PURO; DISENO.md F.6.a, F.7, F.11)
//   · Fila de tramos (una línea / dos / tres, fila 1, fila 1 compartida,
//     fila 2 con leader, paso a callout vertical), paredes de límite,
//     estaciones de recubrimiento, estaciones de extremo, partición en hojas,
//     agrupación de cruces, cota de separación y fusión de paredes.
//   · Parte de la clase PerfilDiseno (ver PerfilDiseno.cs). Unidades: in / ft.
// ============================================================================

namespace Civil3DBasico
{
    internal static partial class PerfilDiseno
    {
        /// <summary>true si el tramo es demasiado corto para rotularse (F.7-1).</summary>
        public static bool EsTramoOmitido(double largoFt, double s) { return largoFt < Math.Max(TRAMO_MIN_FT, TRAMO_MIN_IN * s) - 1e-9; }

        /// <summary>Estaciones de pared (ft) antes de fusionar: EstIni, EstFin y fronteras entre tramos rotulados (F.6.a).</summary>
        private static List<double> EstacionesPared(EntradaMaquetacion e, double s)
        {
            var ts = e.Tramos.OrderBy(t => t.EstIni).ToList();
            var rot = ts.Where(t => !EsTramoOmitido(t.EstFin - t.EstIni, s)).ToList();
            if (rot.Count == 0) return new List<double>();
            var bordes = new List<double> { e.EstIni, e.EstFin };
            foreach (var t in rot) { bordes.Add(t.EstIni); bordes.Add(t.EstFin); }
            foreach (var t in ts.Where(t => EsTramoOmitido(t.EstFin - t.EstIni, s)))
            {
                bordes.RemoveAll(b => Math.Abs(b - t.EstIni) < 1e-6 || Math.Abs(b - t.EstFin) < 1e-6);
                bordes.Add((t.EstIni + t.EstFin) / 2.0);                   // sus fronteras → una sola pared
            }
            var r = new List<double>();
            foreach (double b in bordes.OrderBy(x => x)) if (r.Count == 0 || b - r[r.Count - 1] > 1e-6) r.Add(b);
            return r;
        }

        /// <summary>Paredes en x' (fusionadas) y r.Paredes en estaciones. F.6.a.</summary>
        private static List<double> ParedesRel(EntradaMaquetacion e, ResultadoMaquetacion r, double s)
        {
            var x = EstacionesPared(e, s).Select(est => (est - e.EstIni) / s).ToList();
            var f = FusionarParedes(x);
            r.Paredes = f.Select(xp => e.EstIni + xp * s).ToList();
            return f;
        }

        /// <summary>Fusiona las paredes (in) a menos de tol en su media. F.6.a.</summary>
        public static List<double> FusionarParedes(IReadOnlyList<double> xIn, double tol = FUSION_PAREDES)
        {
            var r = new List<double>();
            if (xIn == null || xIn.Count == 0) return r;
            var o = xIn.OrderBy(v => v).ToList();
            var grupo = new List<double> { o[0] };
            for (int i = 1; i < o.Count; i++)
            {
                if (o[i] - grupo[grupo.Count - 1] < tol) grupo.Add(o[i]);
                else { r.Add(grupo.Average()); grupo = new List<double> { o[i] }; }
            }
            r.Add(grupo.Average());
            return r;
        }

        // ------------------------------------------------------------ F.7

        /// <summary>Líneas de la variante de n líneas de un tramo: 1 = "L1 L2 L3"; 2 = L1 / "L2 L3"; 3 = L1 / L2 / L3. F.7.</summary>
        public static string[] LineasVariante(FilaTramo t, int numLineas)
        {
            bool hay3 = !string.IsNullOrWhiteSpace(t.L3);
            if (numLineas <= 1) return new[] { PerfilTextos.Unir(t.L1, t.L2, t.L3) };
            if (numLineas == 2 || !hay3) return new[] { t.L1 ?? "", PerfilTextos.Unir(t.L2, t.L3) };
            return new[] { t.L1 ?? "", t.L2 ?? "", t.L3 ?? "" };
        }

        private static (double ancho, double alto, int n) TamVariante(FilaTramo t, int n)
        {
            var ls = LineasVariante(t, n);
            double k = t.KMedida > 0 && !double.IsNaN(t.KMedida) ? t.KMedida : 1.0;
            return (LargoMax(ls) * k, AnchoBloqueVertical(ls.Length) * k, ls.Length);
        }

        private static List<int> Variantes(FilaTramo t) { return string.IsNullOrWhiteSpace(t.L3) ? new List<int> { 1, 2 } : new List<int> { 1, 2, 3 }; }

        private static int MasEstrecha(FilaTramo t) { return Variantes(t).OrderBy(n => TamVariante(t, n).ancho).ThenBy(n => n).First(); }

        private static void Fijar(FilaTramo t, int n) { var v = TamVariante(t, n); t.Ancho = v.ancho; t.Alto = v.alto; t.NumLineas = v.n; }

        /// <summary>Coloca la fila de tramos (F.7): omitidos, fila 1, fila 1 compartida y fila 2; devuelve el desborde de la fila 2.</summary>
        internal static double ColocarFila(EntradaMaquetacion e, ResultadoMaquetacion r, bool conLimites, double xMin, double xMax)
        {
            double s = e.S > 0 ? e.S : 20.0;
            double lo = conLimites ? xMin : double.NegativeInfinity, hi = conLimites ? xMax : double.PositiveInfinity;
            var ts = e.Tramos.OrderBy(t => t.EstIni).ThenBy(t => t.Id, StringComparer.Ordinal).ToList();
            var activos = new List<FilaTramo>();
            foreach (var t in ts)
            {
                t.Omitido = EsTramoOmitido(t.EstFin - t.EstIni, s);
                t.ConLeader = false;
                if (t.Omitido || t.AVertical) continue;
                t.Cx = ((t.EstIni + t.EstFin) / 2.0 - e.EstIni) / s;
                activos.Add(t);
            }
            var fila1 = new List<FilaTramo>();
            var pendientes = new List<FilaTramo>();
            // 2. cabe en su celda
            foreach (var t in activos)
            {
                double celda = (t.EstFin - t.EstIni) / s;
                int elegida = Variantes(t).FirstOrDefault(n => TamVariante(t, n).ancho + MARGEN_CELDA <= celda + 1e-9);
                if (elegida > 0) { Fijar(t, elegida); t.Fila = 1; t.X0 = t.Cx - t.Ancho / 2.0; fila1.Add(t); }
                else pendientes.Add(t);
            }
            // 3. fila 1 compartida (variante más estrecha)
            var fila2 = new List<FilaTramo>();
            foreach (var t in pendientes)
            {
                Fijar(t, MasEstrecha(t));
                double x0 = t.Cx - t.Ancho / 2.0, x1 = t.Cx + t.Ancho / 2.0;
                bool libre = fila1.All(o => x1 + GAP <= o.X0 + 1e-9 || x0 >= o.X0 + o.Ancho + GAP - 1e-9);
                bool noTapa = activos.Where(o => o != t).All(o => x1 <= o.Cx - 0.10 + 1e-9 || x0 >= o.Cx + 0.10 - 1e-9);
                bool dentro = !conLimites || (x0 >= lo - 1e-9 && x1 <= hi + 1e-9);
                if (libre && noTapa && dentro) { t.Fila = 1; t.X0 = x0; fila1.Add(t); }
                else fila2.Add(t);
            }
            // 4. fila 2 con leader
            double desborde = 0;
            if (fila2.Count > 0)
            {
                var c = Empaquetar1D(fila2.Select(t => t.Cx).ToList(), fila2.Select(t => t.Ancho).ToList(), null, GAP, lo, hi, out desborde);
                for (int i = 0; i < fila2.Count; i++) { var t = fila2[i]; t.Fila = 2; t.ConLeader = true; t.X0 = c[i] - t.Ancho / 2.0; }
            }
            return desborde;
        }

        /// <summary>F.7-4: el tramo de fila 2 más corto pasa a callout vertical en la franja superior. true si pasó alguno.</summary>
        private static bool PasarTramoAVertical(EntradaMaquetacion e, EstadoMaq st, double s)
        {
            var t = e.Tramos.Where(x => !x.Omitido && !x.AVertical && x.Fila == 2)
                            .OrderBy(x => x.EstFin - x.EstIni).ThenBy(x => x.EstIni).FirstOrDefault();
            if (t == null) return false;
            t.AVertical = true; t.ConLeader = false;
            var b = new BloqueTexto
            {
                Id = t.Id, Franja = FranjaTipo.Superior, Prioridad = 40, PuedeCambiarFranja = true, PuedeAlternar = true,
                EstAncla = (t.EstIni + t.EstFin) / 2.0, ZAncla = double.IsNaN(t.ZCorona) ? e.ZMaxDibujo : t.ZCorona,
                Lineas = LineasVariante(t, string.IsNullOrWhiteSpace(t.L3) ? 2 : 3), Vertical = true,
            };
            PredecirBloque(b);
            b.FranjaFinal = b.Franja; b.Nivel = 1;
            st.AltoPred[b] = LargoMax(b.Lineas);
            e.Bloques.Add(b);
            int pos = st.Orden.FindIndex(o => o.EstAncla > b.EstAncla);
            if (pos < 0) st.Orden.Add(b); else st.Orden.Insert(pos, b);
            return true;
        }

        // ------------------------------------------------------------ F.11

        private static double DistIntervalo(double x, double[] iv)
        {
            double a = Math.Min(iv[0], iv[1]), b = Math.Max(iv[0], iv[1]);
            return x < a ? a - x : (x > b ? x - b : 0);
        }

        /// <summary>Estaciones (ft) para las cotas de recubrimiento, libres de leaders y cruces. F.11.</summary>
        public static List<double> ElegirEstacionesRecubrimiento(double estIni, double estFin, double s,
                IReadOnlyList<double[]> ocupadosLeader, IReadOnlyList<double[]> ocupadosCruce, double estCoberturaMin)
        {
            double m = Math.Max(3.0, 0.3 * s);
            double mid = (estIni + estFin) / 2.0;
            var obj = new List<double>();
            if (estFin - estIni < 2 * m + 0.75 * s) obj.Add(mid);
            else
            {
                double s1 = estIni + m, s2 = estFin - m;
                obj.Add(s1); obj.Add(s2);
                if (!double.IsNaN(estCoberturaMin) && Math.Abs(estCoberturaMin - s1) >= 0.75 * s && Math.Abs(estCoberturaMin - s2) >= 0.75 * s)
                    obj.Add(estCoberturaMin);
            }
            bool Libre(double x)
            {
                if (x < estIni - 1e-9 || x > estFin + 1e-9) return false;
                if (ocupadosLeader != null && ocupadosLeader.Any(iv => iv != null && iv.Length >= 2 && DistIntervalo(x, iv) < 0.10 * s - 1e-9)) return false;
                if (ocupadosCruce != null && ocupadosCruce.Any(iv => iv != null && iv.Length >= 2 && DistIntervalo(x, iv) < 0.30 * s - 1e-9)) return false;
                return true;
            }
            var res = new List<double>();
            double paso = 0.05 * s, rango = 0.75 * s;
            foreach (double t in obj)
            {
                double? elegido = null;
                for (int k = 0; k * paso <= rango + 1e-9 && elegido == null; k++)
                {
                    var cand = k == 0 ? new[] { t } : new[] { t - k * paso, t + k * paso }.OrderBy(x => Math.Abs(x - mid)).ToArray();
                    foreach (double x in cand) if (Libre(x)) { elegido = Math.Round(x, 6); break; }
                }
                if (elegido.HasValue) res.Add(elegido.Value);
            }
            var fin = new List<double>();
            foreach (double x in res.OrderBy(x => x)) if (fin.Count == 0 || x - fin[fin.Count - 1] >= 0.75 * s - 1e-9) fin.Add(x);
            return fin;
        }

        /// <summary>Aleja StationStart/End de la estación mayor vecina si sus números se tocarían (ft). F.11.</summary>
        public static void AjustarEstacionesExtremo(ref double start, ref double end, double s, double estMayor, double estMin, double estMax)
        {
            if (estMayor <= 0) return;
            double Lim(double est) { return (LargoLinea(PerfilTextos.FormatoEstacion(est, 0), H_NUM) + 0.15) * s; }
            double mAnt = Math.Floor(end / estMayor + 1e-9) * estMayor;
            if (end - mAnt > 1e-9 && end - mAnt < Lim(end))
            {
                double n = RedondearArriba(mAnt + 0.6 * s, REDONDEO_EST);
                if (!double.IsInfinity(estMax) && n > estMax) n = RedondearAbajo(estMax, REDONDEO_EST);
                if (n > end) end = n;
            }
            double mSig = Math.Ceiling(start / estMayor - 1e-9) * estMayor;
            if (mSig - start > 1e-9 && mSig - start < Lim(start))
            {
                double n = RedondearAbajo(mSig - 0.6 * s, REDONDEO_EST);
                if (!double.IsInfinity(estMin) && n < estMin) n = RedondearArriba(estMin, REDONDEO_EST);
                if (n < start) start = n;
            }
        }

        /// <summary>Rangos [EstA, EstB] (ft) de cada hoja cortando en nodos; el nodo de corte pertenece a ambas. F.11.</summary>
        public static List<double[]> PartirEnHojas(IReadOnlyList<double> estNodos, double s, double anchoMax = ANCHO_MAX_MARCO)
        {
            var r = new List<double[]>();
            if (estNodos == null || estNodos.Count == 0) return r;
            var n = estNodos.OrderBy(x => x).ToList();
            double ini = n[0], fin = n[n.Count - 1], L = fin - ini;
            double lmax = Math.Max(1e-6, (anchoMax - 2 * PAD_MIN) * s);
            if (n.Count < 2 || L <= lmax + 1e-9) { r.Add(new[] { ini, fin }); return r; }
            int k = (int)Math.Ceiling(L / lmax - 1e-9);
            for (; k <= n.Count - 1; k++)
            {
                var cortes = new List<int> { 0 };
                for (int j = 1; j < k; j++)
                {
                    double obj = ini + j * L / k;
                    int prev = cortes[cortes.Count - 1], best = -1;
                    for (int i = prev + 1; i < n.Count - 1; i++)
                        if (best < 0 || Math.Abs(n[i] - obj) < Math.Abs(n[best] - obj) - 1e-9) best = i;
                    if (best > 0) cortes.Add(best);
                }
                cortes.Add(n.Count - 1);
                r = new List<double[]>();
                for (int i = 0; i + 1 < cortes.Count; i++) r.Add(new[] { n[cortes[i]], n[cortes[i + 1]] });
                if (r.All(h => h[1] - h[0] <= lmax + 1e-9)) return r;
            }
            return r;
        }

        /// <summary>Grupos de índices de cruces (misma red y ≤ max(2, 0.3·S) ft del último del grupo), por estación. F.11.</summary>
        public static List<List<int>> AgruparCruces(IReadOnlyList<double> est, IReadOnlyList<string> red, double s)
        {
            var grupos = new List<List<int>>();
            if (est == null) return grupos;
            double tol = Math.Max(2.0, 0.3 * s);
            string R(int i) { return red != null && i < red.Count ? (red[i] ?? "").Trim().ToUpperInvariant() : ""; }
            foreach (int i in Enumerable.Range(0, est.Count).OrderBy(i => est[i]).ThenBy(i => i))
            {
                var g = grupos.LastOrDefault(x => R(x[0]) == R(i));
                if (g != null && est[i] - est[g[g.Count - 1]] <= tol + 1e-9) g.Add(i);
                else grupos.Add(new List<int> { i });
            }
            return grupos;
        }

        /// <summary>true si la cota de separación cabe: claroFt/V ≥ LargoLinea("0.00'", h) + 0.10. F.11.</summary>
        public static bool CotaSeparacionCabe(double claroFt, double v, double hTexto = H_TEXTO)
        {
            return v > 0 && claroFt / v >= LargoLinea("0.00'", hTexto) + 0.10 - 1e-9;
        }
    }
}
