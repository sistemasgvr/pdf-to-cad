using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;

// ============================================================================
//  MAQUETACIÓN — FRANJAS (PURO; DISENO.md F.4-3, F.5, F.6, F.8)
//   · Empaquetar1D ponderado y exacto, segmentos entre paredes activas,
//     holgura por franja, bucle horizontal y reglas «si no cabe» (un paso por
//     pasada; orden estricto).
//   · Parte de la clase PerfilDiseno (ver PerfilDiseno.cs). Unidades: in.
//   · Durante el bucle horizontal X0/Cx están en x' (relativos a EstIni de la
//     hoja); Vertical() los pasa al marco sumando Off.
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>Estado de una maquetación en curso (orden explícito, reglas aplicadas, paredes desactivadas).</summary>
    internal sealed class EstadoMaq
    {
        public List<BloqueTexto> Orden = new List<BloqueTexto>();
        public HashSet<string> Hechas = new HashSet<string>();
        public HashSet<BloqueTexto> NoMover = new HashSet<BloqueTexto>();
        public Dictionary<FranjaTipo, HashSet<double>> Inactivas = new Dictionary<FranjaTipo, HashSet<double>>
            { { FranjaTipo.Superior, new HashSet<double>() }, { FranjaTipo.Inferior, new HashSet<double>() } };
        public Dictionary<BloqueTexto, double> AltoPred = new Dictionary<BloqueTexto, double>();
        public List<double> Paredes = new List<double>();              // x' fusionadas
        public double Off, XMin = double.NegativeInfinity, XMax = double.PositiveInfinity;
        public double ZMaxDib, ZMinDib;
    }

    internal static partial class PerfilDiseno
    {
        private static readonly ConditionalWeakTable<EntradaMaquetacion, EstadoMaq> ESTADOS = new ConditionalWeakTable<EntradaMaquetacion, EstadoMaq>();

        private static EstadoMaq Estado(EntradaMaquetacion e) { return ESTADOS.GetValue(e, _ => new EstadoMaq()); }

        private static EstadoMaq PrepararEstado(EntradaMaquetacion e, double s)
        {
            ESTADOS.Remove(e);
            var st = Estado(e);
            foreach (var b in e.Bloques)
            {
                if (!b.Medido) PredecirBloque(b);
                st.AltoPred[b] = LargoMax(b.Lineas);
                b.FranjaFinal = b.Franja; b.Nivel = 1; b.Recortado = false; b.Descartado = false;
            }
            foreach (var t in e.Tramos) { t.Omitido = false; t.ConLeader = false; t.AVertical = false; t.Fila = 1; }
            st.Orden = e.Bloques.OrderBy(b => b.EstAncla).ThenBy(b => b.Id, StringComparer.Ordinal).ToList();
            return st;
        }

        // ------------------------------------------------------------ F.5

        /// <summary>
        /// Empaquetado 1D ponderado (F.5): centros en el orden de entrada, separados ≥ gap, dentro de [min, max]
        /// (±∞ = sin límite). pesos null = 1. desborde = Σ exceso de los grupos que no caben.
        /// </summary>
        public static List<double> Empaquetar1D(IReadOnlyList<double> ideal, IReadOnlyList<double> anchos, IReadOnlyList<double> pesos,
                                                double gap, double min, double max, out double desborde)
        {
            desborde = 0;
            int n = ideal == null ? 0 : ideal.Count;
            var res = new List<double>();
            if (n == 0) return res;
            double W(int i) { return anchos[i]; }
            double P(int i) { double p = pesos == null ? 1.0 : pesos[i]; return p > 0 ? p : 1e-6; }
            var grupos = new List<List<int>>();
            for (int i = 0; i < n; i++) grupos.Add(new List<int> { i });
            var inicio = new List<double>(); var ancho = new List<double>(); var desb = new List<double>();
            for (int guard = 0; guard <= n; guard++)
            {
                inicio.Clear(); ancho.Clear(); desb.Clear();
                foreach (var g in grupos)
                {
                    double w = 0, sp = 0, sx = 0;
                    for (int j = 0; j < g.Count; j++)
                    {
                        double off = w + W(g[j]) / 2.0;
                        sx += P(g[j]) * (ideal[g[j]] - off); sp += P(g[j]);
                        w += W(g[j]) + gap;
                    }
                    w -= gap;
                    double ini = sx / sp, d = 0;
                    if (w > max - min) { ini = min; d = w - (max - min); }
                    else ini = Math.Max(min, Math.Min(max - w, ini));
                    inicio.Add(ini); ancho.Add(w); desb.Add(d);
                }
                int k = -1;
                for (int g = 0; g + 1 < grupos.Count; g++)
                    if (inicio[g] + ancho[g] + gap > inicio[g + 1] + 1e-9) { k = g; break; }
                if (k < 0) break;
                grupos[k].AddRange(grupos[k + 1]); grupos.RemoveAt(k + 1);
            }
            for (int i = 0; i < n; i++) res.Add(0);
            for (int g = 0; g < grupos.Count; g++)
            {
                double w = 0;
                foreach (int i in grupos[g]) { res[i] = inicio[g] + w + W(i) / 2.0; w += W(i) + gap; }
                if (!double.IsInfinity(desb[g])) desborde += desb[g];
            }
            return res;
        }

        // ------------------------------------------------------------ F.6.b segmentos

        private sealed class Seg
        {
            public List<BloqueTexto> B = new List<BloqueTexto>();
            public double Min, Max; public int Izq = -1, Der = -1;       // índices en la lista de paredes activas
            public double Desborde, MaxDx;
            public bool Desborda { get { return Desborde > 1e-9 || MaxDx > HOLGURA_MAX * PENDIENTE_LEADER_MAX + 1e-9; } }
        }

        private static double XAncla(BloqueTexto b, double estIni, double s) { return (b.EstAncla - estIni) / s; }

        /// <summary>Segmentos de una franja (nivel 1) entre paredes activas, empaquetados. X0 en x'.</summary>
        private static List<Seg> Segmentar(List<BloqueTexto> bloques, IReadOnlyList<double> paredes, double estIni, double s,
                                           bool conLimites, double xMin, double xMax, HashSet<double> inactivas, out List<double> activas)
        {
            double lo = conLimites ? xMin : double.NegativeInfinity, hi = conLimites ? xMax : double.PositiveInfinity;
            var lado = new Dictionary<BloqueTexto, (double pared, bool izq)>();
            var usadas = new HashSet<double>();
            foreach (var b in bloques)
            {
                if (paredes.Count == 0) break;
                double xa = XAncla(b, estIni, s);
                int iw = 0;
                for (int i = 1; i < paredes.Count; i++) if (Math.Abs(xa - paredes[i]) < Math.Abs(xa - paredes[iw])) iw = i;
                double w = paredes[iw];
                if (inactivas != null && inactivas.Contains(w)) continue;
                if (Math.Abs(xa - w) >= b.Ancho) continue;
                bool izq;
                if (iw == 0 && paredes.Count > 1) izq = true;
                else if (iw == paredes.Count - 1 && paredes.Count > 1) izq = false;
                else
                {
                    double celdaIzq = iw > 0 ? w - paredes[iw - 1] : w - lo;
                    double celdaDer = iw + 1 < paredes.Count ? paredes[iw + 1] - w : hi - w;
                    izq = celdaIzq >= celdaDer;
                }
                lado[b] = (w, izq); usadas.Add(w);
            }
            activas = paredes.Where(usadas.Contains).OrderBy(x => x).ToList();
            var segs = new List<Seg>();
            for (int k = 0; k <= activas.Count; k++)
            {
                var sg = new Seg
                {
                    Min = k == 0 ? lo : Math.Max(lo, activas[k - 1] + MARGEN_PARED),
                    Max = k == activas.Count ? hi : Math.Min(hi, activas[k] - MARGEN_PARED),
                    Izq = k - 1, Der = k < activas.Count ? k : -1,
                };
                segs.Add(sg);
            }
            foreach (var b in bloques)
            {
                int k;
                if (lado.TryGetValue(b, out var lw)) { int iw = activas.IndexOf(lw.pared); k = lw.izq ? iw : iw + 1; }
                else { double xa = XAncla(b, estIni, s); k = activas.Count(w => w < xa); }
                segs[k].B.Add(b);
            }
            foreach (var sg in segs.Where(g => g.B.Count > 0))
            {
                var ideal = sg.B.Select(b => XAncla(b, estIni, s) + b.Ancho / 2.0 - b.DxEnganche).ToList();
                var c = Empaquetar1D(ideal, sg.B.Select(b => b.Ancho).ToList(), sg.B.Select(b => (double)b.Prioridad).ToList(),
                                     GAP, sg.Min, sg.Max, out double d);
                sg.Desborde = d;
                for (int i = 0; i < sg.B.Count; i++)
                {
                    var b = sg.B[i]; b.X0 = c[i] - b.Ancho / 2.0;
                    sg.MaxDx = Math.Max(sg.MaxDx, Math.Abs(b.X0 + b.DxEnganche - XAncla(b, estIni, s)));
                }
            }
            return segs;
        }

        /// <summary>
        /// Empaqueta los bloques de una franja y nivel con segmentos entre paredes activas (F.6.b), en x' relativos (sin límites
        /// si conLimites = false). Escribe X0 en cada bloque y devuelve el desborde total.
        /// </summary>
        internal static double EmpaquetarFranja(List<BloqueTexto> bloques, IReadOnlyList<double> paredesX, double estIni, double s,
                                                bool conLimites, double xMin, double xMax, HashSet<double> paredesInactivas)
        {
            return Segmentar(bloques, paredesX, estIni, s, conLimites, xMin, xMax, paredesInactivas, out _).Sum(g => g.Desborde);
        }

        /// <summary>Nivel 2 (escalonado): cada bloque apunta al hueco de nivel 1 más cercano a su ancla. Devuelve el ancho mínimo de hueco usado.</summary>
        private static double EmpaquetarNivel2(List<BloqueTexto> n1, List<BloqueTexto> n2, double estIni, double s, bool conLimites, double xMin, double xMax, out double desborde)
        {
            desborde = 0;
            if (n2.Count == 0) return double.PositiveInfinity;
            var cajas = n1.OrderBy(b => b.X0).ToList();
            var huecos = new List<(double c, double w)>();
            if (cajas.Count > 0) huecos.Add((cajas[0].X0 - HUECO_LEADER_MIN, double.PositiveInfinity));
            for (int i = 0; i + 1 < cajas.Count; i++)
            {
                double a = cajas[i].X0 + cajas[i].Ancho, b = cajas[i + 1].X0;
                huecos.Add(((a + b) / 2.0, b - a));
            }
            if (cajas.Count > 0) { var u = cajas[cajas.Count - 1]; huecos.Add((u.X0 + u.Ancho + HUECO_LEADER_MIN, double.PositiveInfinity)); }
            double minHueco = double.PositiveInfinity;
            var ideal = new List<double>();
            foreach (var b in n2)
            {
                double xa = XAncla(b, estIni, s);
                var h = huecos.Count == 0 ? (xa, double.PositiveInfinity) : huecos.OrderBy(q => Math.Abs(q.c - xa)).First();
                minHueco = Math.Min(minHueco, h.Item2);
                ideal.Add(h.Item1 + b.Ancho / 2.0 - b.DxEnganche);
            }
            var c = Empaquetar1D(ideal, n2.Select(b => b.Ancho).ToList(), n2.Select(b => (double)b.Prioridad).ToList(), GAP,
                                 conLimites ? xMin : double.NegativeInfinity, conLimites ? xMax : double.PositiveInfinity, out desborde);
            for (int i = 0; i < n2.Count; i++) n2[i].X0 = c[i] - n2[i].Ancho / 2.0;
            return minHueco;
        }

        private static List<BloqueTexto> DeFranja(EstadoMaq st, FranjaTipo f, int nivel)
        {
            return st.Orden.Where(b => !b.Descartado && b.FranjaFinal == f && b.Nivel == nivel).ToList();
        }

        /// <summary>Holgura de una franja: clamp(máx dx / PENDIENTE_LEADER_MAX, HOLGURA_DIBUJO, HOLGURA_MAX). F.6.c.</summary>
        internal static double Holgura(IReadOnlyList<BloqueTexto> bloques, Func<double, double> xDeEstacion)
        {
            double m = 0;
            foreach (var b in bloques) m = Math.Max(m, Math.Abs(b.X0 + b.DxEnganche - xDeEstacion(b.EstAncla)));
            return Math.Max(HOLGURA_DIBUJO, Math.Min(HOLGURA_MAX, m / PENDIENTE_LEADER_MAX));
        }

        // ------------------------------------------------------------ F.4-3 bucle horizontal

        private sealed class Empaque { public Dictionary<FranjaTipo, List<Seg>> Segs = new Dictionary<FranjaTipo, List<Seg>>(); public Dictionary<FranjaTipo, double> DesN2 = new Dictionary<FranjaTipo, double>(); public double Lmin, Rmax; }

        private static Empaque EmpaquetarTodo(EntradaMaquetacion e, EstadoMaq st, double s, bool conLim, double xMin, double xMax)
        {
            var r = new Empaque { Lmin = double.PositiveInfinity, Rmax = double.NegativeInfinity };
            foreach (FranjaTipo f in new[] { FranjaTipo.Superior, FranjaTipo.Inferior })
            {
                var n1 = DeFranja(st, f, 1);
                r.Segs[f] = Segmentar(n1, st.Paredes, e.EstIni, s, conLim, xMin, xMax, st.Inactivas[f], out _);
                EmpaquetarNivel2(n1, DeFranja(st, f, 2), e.EstIni, s, conLim, xMin, xMax, out double d2);
                r.DesN2[f] = d2;
            }
            foreach (var b in e.Bloques.Where(b => !b.Descartado)) { r.Lmin = Math.Min(r.Lmin, b.X0); r.Rmax = Math.Max(r.Rmax, b.X0 + b.Ancho); }
            return r;
        }

        private static void Horizontal(EntradaMaquetacion e, ResultadoMaquetacion r, EstadoMaq st, double s)
        {
            double lr = (e.EstFin - e.EstIni) / s;
            st.Paredes = ParedesRel(e, r, s);
            int maxIter = e.Bloques.Count + e.Tramos.Count + 3 + 2 * st.Paredes.Count;
            bool acotado = e.EstMaxPermitida > e.EstMinPermitida;
            for (int it = 0; it < maxIter; it++)
            {
                // a. sin límites
                var a = EmpaquetarTodo(e, st, s, false, double.NegativeInfinity, double.PositiveInfinity);
                ColocarFila(e, r, false, double.NegativeInfinity, double.PositiveInfinity);
                double lmin = a.Lmin, rmax = a.Rmax;
                foreach (var t in e.Tramos.Where(t => !t.Omitido && !t.AVertical)) { lmin = Math.Min(lmin, t.X0); rmax = Math.Max(rmax, t.X0 + t.Ancho); }
                if (double.IsInfinity(lmin)) lmin = 0;
                if (double.IsInfinity(rmax)) rmax = lr;
                // b. relleno y rango horizontal
                double padL = Math.Max(PAD_MIN, Math.Min(PAD_MAX, Math.Max(PAD_MIN, -lmin + MARGEN_MARCO)));
                double padR = Math.Max(PAD_MIN, Math.Min(PAD_MAX, Math.Max(PAD_MIN, rmax - lr + MARGEN_MARCO)));
                double start = RedondearAbajo(e.EstIni - padL * s, REDONDEO_EST);
                if (start < 0)
                {
                    if (e.EstIni - (Math.Max(0, -lmin) + MARGEN_MARCO) * s >= 0) start = 0;
                    else if (!st.Hechas.Contains("neg")) { st.Hechas.Add("neg"); r.Avisos.Add("Estaciones negativas en el marco"); }
                }
                if (acotado && start < e.EstMinPermitida) start = RedondearArriba(e.EstMinPermitida, REDONDEO_EST);
                double end = RedondearArriba(e.EstFin + padR * s, REDONDEO_EST);
                if (acotado) end = Math.Min(end, RedondearAbajo(e.EstMaxPermitida, REDONDEO_EST));
                if (end <= start) end = start + REDONDEO_EST;
                AjustarEstacionesExtremo(ref start, ref end, s, r.Int.EstMayor, acotado ? e.EstMinPermitida : double.NegativeInfinity,
                                         acotado ? e.EstMaxPermitida : double.PositiveInfinity);
                r.StationStart = start; r.StationEnd = end; r.AnchoMarco = (end - start) / s;
                st.Off = (e.EstIni - start) / s;
                st.XMin = MARGEN_MARCO - st.Off; st.XMax = r.AnchoMarco - MARGEN_MARCO - st.Off;
                // c. con límites
                var c = EmpaquetarTodo(e, st, s, true, st.XMin, st.XMax);
                double desFila = ColocarFila(e, r, true, st.XMin, st.XMax);
                // d. holgura
                Func<double, double> xr = est => (est - e.EstIni) / s;
                r.HolguraSup = Holgura(e.Bloques.Where(b => !b.Descartado && b.FranjaFinal == FranjaTipo.Superior).ToList(), xr);
                r.HolguraInf = Holgura(e.Bloques.Where(b => !b.Descartado && b.FranjaFinal == FranjaTipo.Inferior).ToList(), xr);
                // e/f. evaluación y un paso de regla
                if (DesactivarPared(st, c)) continue;
                bool cambio = false;
                foreach (FranjaTipo f in new[] { FranjaTipo.Superior, FranjaTipo.Inferior })
                {
                    var mal = c.Segs[f].FirstOrDefault(g => g.Desborda);
                    if (mal == null && c.DesN2[f] <= 1e-9) continue;
                    var grupo = mal != null ? mal.B : DeFranja(st, f, 2);
                    cambio = AplicarRegla(e, r, f, 1, grupo);
                    if (cambio) break;
                }
                if (!cambio && desFila > 1e-9) cambio = PasarTramoAVertical(e, st, s);
                if (!cambio)
                {
                    // una regla probada y deshecha (escalonar) deja posiciones de su simulación: se reempaqueta
                    EmpaquetarTodo(e, st, s, true, st.XMin, st.XMax);
                    ColocarFila(e, r, true, st.XMin, st.XMax);
                    r.HolguraSup = Holgura(e.Bloques.Where(x => !x.Descartado && x.FranjaFinal == FranjaTipo.Superior).ToList(), xr);
                    r.HolguraInf = Holgura(e.Bloques.Where(x => !x.Descartado && x.FranjaFinal == FranjaTipo.Inferior).ToList(), xr);
                    break;
                }
            }
        }

        /// <summary>Si un segmento desborda y lo limita una pared activa, desactiva la que da al vecino con más hueco. F.6.b.</summary>
        private static bool DesactivarPared(EstadoMaq st, Empaque c)
        {
            foreach (FranjaTipo f in new[] { FranjaTipo.Superior, FranjaTipo.Inferior })
            {
                var segs = c.Segs[f];
                for (int k = 0; k < segs.Count; k++)
                {
                    var g = segs[k];
                    if (!g.Desborda || (k == 0 && k == segs.Count - 1)) continue;
                    double Libre(Seg sg) { return (sg.Max - sg.Min) - (sg.B.Sum(b => b.Ancho) + Math.Max(0, sg.B.Count - 1) * GAP); }
                    Seg izq = k > 0 ? segs[k - 1] : null, der = k + 1 < segs.Count ? segs[k + 1] : null;
                    bool usarIzq = izq != null && (der == null || Libre(izq) >= Libre(der));
                    // pared entre g y su vecino: frontera Max de izq / Min de der (± MARGEN_PARED)
                    double pared = usarIzq ? izq.Max + MARGEN_PARED : der.Min - MARGEN_PARED;
                    double cercana = st.Paredes.OrderBy(w => Math.Abs(w - pared)).FirstOrDefault();
                    if (st.Paredes.Count == 0 || st.Inactivas[f].Contains(cercana)) continue;
                    st.Inactivas[f].Add(cercana);
                    return true;
                }
            }
            return false;
        }

        // ------------------------------------------------------------ F.8 reglas

        private static FranjaTipo Otra(FranjaTipo f) { return f == FranjaTipo.Superior ? FranjaTipo.Inferior : FranjaTipo.Superior; }

        private static bool FranjaDesborda(EntradaMaquetacion e, EstadoMaq st, FranjaTipo f, double s)
        {
            var segs = Segmentar(DeFranja(st, f, 1), st.Paredes, e.EstIni, s, true, st.XMin, st.XMax, st.Inactivas[f], out _);
            return segs.Any(g => g.Desborda);
        }

        /// <summary>Aplica UN paso de las reglas F.8 (cambiar franja, alternar, recortar, escalonar, aviso) al grupo desbordado. true si cambió algo.</summary>
        internal static bool AplicarRegla(EntradaMaquetacion e, ResultadoMaquetacion r, FranjaTipo franja, int nivel, List<BloqueTexto> grupo)
        {
            var st = Estado(e);
            double s = e.S > 0 ? e.S : 20.0;
            string fn = franja == FranjaTipo.Superior ? "sup" : "inf";
            grupo = grupo ?? new List<BloqueTexto>();
            // 1. cambiar de franja (el movible de MENOR prioridad), si la otra no desborda después
            foreach (var b in grupo.Where(b => b.PuedeCambiarFranja && !st.NoMover.Contains(b)).OrderBy(b => b.Prioridad).ThenBy(b => b.EstAncla))
            {
                b.FranjaFinal = Otra(franja);
                if (!FranjaDesborda(e, st, Otra(franja), s)) return true;
                b.FranjaFinal = franja; st.NoMover.Add(b);
            }
            // 2. alternar franjas (índices impares; una vez por franja)
            if (st.Hechas.Add("alt:" + fn))
            {
                bool c = false;
                var orden = grupo.OrderBy(b => b.EstAncla).ThenBy(b => b.Id, StringComparer.Ordinal).ToList();
                for (int i = 1; i < orden.Count; i += 2)
                    if (orden[i].PuedeAlternar) { orden[i].FranjaFinal = Otra(franja); c = true; }
                if (c) return true;
            }
            // 3. recortar la última línea (una vez)
            if (st.Hechas.Add("rec:" + fn))
            {
                bool c = false;
                foreach (var b in e.Bloques.Where(b => !b.Descartado && b.FranjaFinal == franja && b.PuedeRecortar && !b.Recortado && b.Lineas.Length >= 3))
                {
                    double altoPred = st.AltoPred.TryGetValue(b, out double ap) && ap > 1e-9 ? ap : LargoMax(b.Lineas);
                    var resto = b.Lineas.Take(b.Lineas.Length - 1).ToArray();
                    double nuevoPred = LargoMax(resto);
                    b.Ancho -= PASO_LINEA;
                    b.Alto = b.Medido ? nuevoPred * (b.Alto / altoPred) : nuevoPred;
                    b.Lineas = resto; b.Recortado = true; r.Recortados.Add(b.Id); c = true;
                }
                if (c) return true;
            }
            // 4. escalonar (condicionado a huecos ≥ HUECO_LEADER_MIN y sin cortes con nivel 1)
            if (st.Hechas.Add("esc:" + fn) && Escalonar(e, st, franja, grupo, s)) return true;
            // 5. aviso (y se descarta EX. GRADE de esa franja)
            if (st.Hechas.Add("avi:" + fn))
            {
                r.Avisos.Add("Rótulos apretados en franja " + fn);
                bool c = false;
                foreach (var b in e.Bloques.Where(b => b.FranjaFinal == franja && !b.Descartado && b.Id.StartsWith("TERRENO", StringComparison.Ordinal)))
                { b.Descartado = true; c = true; }
                return c;
            }
            return false;
        }

        private static bool Escalonar(EntradaMaquetacion e, EstadoMaq st, FranjaTipo f, List<BloqueTexto> grupo, double s)
        {
            var orden = grupo.Where(b => b.Nivel == 1).OrderBy(b => b.EstAncla).ThenBy(b => b.Id, StringComparer.Ordinal).ToList();
            var subir = new List<BloqueTexto>();
            for (int i = 1; i < orden.Count; i += 2) subir.Add(orden[i]);
            if (subir.Count == 0) return false;
            foreach (var b in subir) b.Nivel = 2;
            var n1 = DeFranja(st, f, 1); var n2 = DeFranja(st, f, 2);
            Segmentar(n1, st.Paredes, e.EstIni, s, true, st.XMin, st.XMax, st.Inactivas[f], out _);
            double hueco = EmpaquetarNivel2(n1, n2, e.EstIni, s, true, st.XMin, st.XMax, out _);
            // cortes en coordenadas normalizadas: ancla y=0, nivel 1 en [H, H+Alto], nivel 2 en H+Ht1+SEP
            double ht1 = n1.Select(b => b.Alto).DefaultIfEmpty(0).Max();
            double h0 = HOLGURA_DIBUJO, y2 = h0 + ht1 + SEP_NIVEL;
            var cajas = n1.Select(b => new Caja { Id = b.Id, X0 = b.X0, Y0 = h0, X1 = b.X0 + b.Ancho, Y1 = h0 + b.Alto }).ToList();
            var leaders = n2.Select(b => new Leader { Id = b.Id, X0 = b.X0 + b.DxEnganche, Y0 = y2, X1 = XAncla(b, e.EstIni, s), Y1 = 0 }).ToList();
            bool viable = hueco >= HUECO_LEADER_MIN - 1e-9 && CortesLeaderCaja(leaders, cajas).Count == 0;
            if (!viable) foreach (var b in subir) b.Nivel = 1;
            return viable;
        }

        /// <summary>F.4-7: intercambia el orden de dos bloques de la misma franja y nivel cuyos leaders se cruzan. true si cambió algo.</summary>
        private static bool IntercambiarCruces(EntradaMaquetacion e, ResultadoMaquetacion r, EstadoMaq st, double s)
        {
            var ls = LeadersFinales(e, r);
            var porId = e.Bloques.Where(b => !b.Descartado).GroupBy(b => b.Id).ToDictionary(g => g.Key, g => g.First());
            bool c = false;
            foreach (string par in CrucesLeaders(ls))
            {
                var ids = par.Split('|');
                if (!porId.TryGetValue(ids[0], out var a) || !porId.TryGetValue(ids[1], out var b)) continue;
                if (a.FranjaFinal != b.FranjaFinal || a.Nivel != b.Nivel) continue;
                int ia = st.Orden.IndexOf(a), ib = st.Orden.IndexOf(b);
                if (ia < 0 || ib < 0) continue;
                st.Orden[ia] = b; st.Orden[ib] = a; c = true;
            }
            return c;
        }
    }
}
