using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  RECORRIDO — núcleo geométrico PURO (DISENO.md B.2, C.4, C.5, C.6, C.7)
//   · Sin Autodesk: lo compila también el arnés PerfilPruebas.
//   · Grafo en planta (V2, GNodo, GArista), continuación por deflexión mínima,
//     recorrido, tangentes de arcos (bulge), traza del eje con prolongaciones,
//     distancias sobre la traza, cortes con otras tuberías y elección 3D del
//     accesorio sólido de presión.
//   · Unidades: pies en planta y cota; ángulos en GRADOS salvo que se diga.
// ============================================================================

namespace Civil3DBasico
{
    // ---------------------------------------------------------------- B.2 tipos

    internal struct V2
    {
        public double X, Y;
        public V2(double x, double y) { X = x; Y = y; }
        public static V2 operator +(V2 a, V2 b) { return new V2(a.X + b.X, a.Y + b.Y); }
        public static V2 operator -(V2 a, V2 b) { return new V2(a.X - b.X, a.Y - b.Y); }
        public static V2 operator *(V2 a, double k) { return new V2(a.X * k, a.Y * k); }
        public double Largo { get { return Math.Sqrt(X * X + Y * Y); } }
        public double Dot(V2 o) { return X * o.X + Y * o.Y; }
        public double Cross(V2 o) { return X * o.Y - Y * o.X; }
        public bool TryUnit(out V2 u)                   // NUNCA devuelve NaN
        {
            double l = Largo;
            if (l < 1e-9 || double.IsNaN(l)) { u = new V2(0, 0); return false; }
            u = new V2(X / l, Y / l); return true;
        }
    }

    internal struct V2Bulge { public double X, Y, Bulge; }          // bulge del segmento que EMPIEZA aquí
    internal sealed class GNodo { public int Id; public double X, Y; public List<int> Aristas = new List<int>(); }
    internal sealed class GArista
    {
        public int Id, A, B; public double Bulge, Largo;
        public V2 DirSalidaA, DirSalidaB;                            // tangentes unitarias que SALEN de A y de B
        public bool Valida;                                          // false si Largo < 1e-9 o TryUnit falla (C.4)
    }
    internal sealed class PasoG { public int Arista; public bool Invertida; }
    internal sealed class CorteTraza { public double Estacion, AnguloDeg, T; public V2 P; }
    internal sealed class CandidatoAccesorio { public int Id; public double X, Y, Z, DiamPrincipalFt, LargoTotalFt; public string Red = ""; }

    // ---------------------------------------------------------------- funciones

    internal static class PerfilRecorrido
    {
        // Constantes (C, C.4, C.6, D.4)
        public const double TOL_COINCIDE = 0.5;          // ft en planta
        public const double LARGO_MIN_TUBO = 2 * TOL_COINCIDE; // 1.0 ft: menos = tubo degenerado (vertical)
        public const double DEFLEXION_MAX_DEG = 45;
        public const double EMPATE_DEG = 10;
        public const double UMBRAL_PRESION_DEG = 1.0;    // C.6: nodo sin callout por debajo
        public const double UMBRAL_CONDUIT_DEG = 2.0;
        public const double PASO_TERRENO = 2.0;          // ft sobre la traza (D.4)
        public const double EST_INICIAL = 100.0;         // estación de N0 (1+00)
        public const double TOL_ARCO_VERIFICADO = 0.1;   // ft (C.2-3 / C.3-2)
        private const int CUERDAS_ARCO = 16;             // arcos discretizados (C.5 / C.7)

        // ------------------------------------------------------------ C.4

        private static bool EsUnitario(V2 v)
        {
            double l = v.Largo;
            return !double.IsNaN(l) && Math.Abs(l - 1.0) < 1e-6;
        }

        /// <summary>Deflexión 0..180° entre dirección de llegada y de salida (unitarias). NaN si alguna no es unitaria válida. C.4.</summary>
        internal static double Deflexion(V2 dirLlegada, V2 dirSalida)
        {
            if (!EsUnitario(dirLlegada) || !EsUnitario(dirSalida)) return double.NaN;
            double c = Math.Max(-1.0, Math.Min(1.0, dirLlegada.Dot(dirSalida)));
            return Math.Acos(c) * 180.0 / Math.PI;
        }

        /// <summary>Ángulo firmado (−180,180] de llegada a salida; + = giro a la izquierda. C.4.</summary>
        internal static double AnguloFirmado(V2 dirLlegada, V2 dirSalida)
        {
            double a = Math.Atan2(dirLlegada.Cross(dirSalida), dirLlegada.Dot(dirSalida)) * 180.0 / Math.PI;
            if (a <= -180.0) a += 360.0;
            return a;
        }

        /// <summary>Tangente que SALE de <paramref name="nodo"/> por la arista.</summary>
        private static V2 DirSalida(GArista e, int nodo) { return e.A == nodo ? e.DirSalidaA : e.DirSalidaB; }
        private static int Otro(GArista e, int nodo) { return e.A == nodo ? e.B : e.A; }

        /// <summary>Arista de continuación en <paramref name="nodo"/>: la de menor δ (≤45°, sin empate &lt;10°); null si no hay. C.4.</summary>
        internal static int? Continuacion(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int nodo, int aristaLlegada, V2 dirLlegada, ISet<int> usadas)
        {
            if (nodo < 0 || nodo >= n.Count) return null;
            var cand = new List<KeyValuePair<double, int>>();
            foreach (int e in n[nodo].Aristas)
            {
                if (e == aristaLlegada || e < 0 || e >= a.Count || !a[e].Valida) continue;
                if (usadas != null && usadas.Contains(e)) continue;
                double d = Deflexion(dirLlegada, DirSalida(a[e], nodo));
                if (double.IsNaN(d)) continue;                            // nunca se ordena un NaN
                cand.Add(new KeyValuePair<double, int>(d, e));
            }
            if (cand.Count == 0) return null;
            cand.Sort((x, y) => { int c = x.Key.CompareTo(y.Key); return c != 0 ? c : x.Value.CompareTo(y.Value); });
            if (cand[0].Key > DEFLEXION_MAX_DEG) return null;
            if (cand.Count > 1 && cand[1].Key - cand[0].Key < EMPATE_DEG) return null;
            return cand[0].Value;
        }

        /// <summary>Paso de avance (arista, desde, hasta).</summary>
        private struct Salto { public int Arista, Desde, Hasta; }

        /// <summary>Avanza desde <paramref name="cur"/> por continuación hasta que no hay o vuelve a un nodo visitado.</summary>
        private static List<Salto> Extender(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int cur, int llegada, V2 dirLlegada,
                                            HashSet<int> usadas, HashSet<int> visitados)
        {
            var r = new List<Salto>();
            for (int guard = 0; guard < a.Count + 2; guard++)
            {
                int? c = Continuacion(n, a, cur, llegada, dirLlegada, usadas);
                if (c == null) break;
                int e = c.Value, sig = Otro(a[e], cur);
                usadas.Add(e);
                r.Add(new Salto { Arista = e, Desde = cur, Hasta = sig });
                if (visitados.Contains(sig)) break;                      // lazo: se para
                visitados.Add(sig);
                dirLlegada = DirSalida(a[e], sig) * -1.0;
                llegada = e; cur = sig;
            }
            return r;
        }

        private static List<PasoG> Componer(IReadOnlyList<GArista> a, List<Salto> atras, List<Salto> centro, List<Salto> adelante)
        {
            var r = new List<PasoG>();
            for (int i = atras.Count - 1; i >= 0; i--)                   // atrás se recorre al revés
            {
                var s = atras[i];
                r.Add(new PasoG { Arista = s.Arista, Invertida = a[s.Arista].A != s.Hasta });
            }
            foreach (var s in centro.Concat(adelante))
                r.Add(new PasoG { Arista = s.Arista, Invertida = a[s.Arista].A != s.Desde });
            return r;
        }

        /// <summary>Recorrido que contiene la arista inicial (avanza desde B y retrocede desde A); vacío si !a[aristaInicial].Valida. C.4.</summary>
        internal static List<PasoG> Recorrer(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int aristaInicial)
        {
            if (aristaInicial < 0 || aristaInicial >= a.Count || !a[aristaInicial].Valida) return new List<PasoG>();
            var e0 = a[aristaInicial];
            var usadas = new HashSet<int> { aristaInicial };
            var visit = new HashSet<int> { e0.A, e0.B };
            var adelante = Extender(n, a, e0.B, aristaInicial, e0.DirSalidaB * -1.0, usadas, visit);
            var atras = Extender(n, a, e0.A, aristaInicial, e0.DirSalidaA * -1.0, usadas, visit);
            return Componer(a, atras, new List<Salto> { new Salto { Arista = aristaInicial, Desde = e0.A, Hasta = e0.B } }, adelante);
        }

        /// <summary>Recorrido que pasa por un nodo: par de aristas de menor deflexión (o la más larga si δ&gt;45°). C.4.</summary>
        internal static List<PasoG> RecorrerDesdeNodo(IReadOnlyList<GNodo> n, IReadOnlyList<GArista> a, int nodo)
        {
            if (nodo < 0 || nodo >= n.Count) return new List<PasoG>();
            var ars = n[nodo].Aristas.Where(e => e >= 0 && e < a.Count && a[e].Valida).Distinct().OrderBy(e => e).ToList();
            if (ars.Count == 0) return new List<PasoG>();
            if (ars.Count == 1) return Recorrer(n, a, ars[0]);
            double best = double.MaxValue; int bi = -1, bj = -1;
            for (int x = 0; x < ars.Count; x++)
                for (int y = x + 1; y < ars.Count; y++)
                {
                    double d = Deflexion(DirSalida(a[ars[x]], nodo) * -1.0, DirSalida(a[ars[y]], nodo));
                    if (double.IsNaN(d)) continue;
                    if (d < best - 1e-12) { best = d; bi = ars[x]; bj = ars[y]; }
                }
            if (bi < 0 || best > DEFLEXION_MAX_DEG)
            {
                int larga = ars.OrderByDescending(e => a[e].Largo).ThenBy(e => e).First();
                return Recorrer(n, a, larga);
            }
            int oi = Otro(a[bi], nodo), oj = Otro(a[bj], nodo);
            var usadas = new HashSet<int> { bi, bj };
            var visit = new HashSet<int> { nodo, oi, oj };
            var atras = Extender(n, a, oi, bi, DirSalida(a[bi], oi) * -1.0, usadas, visit);
            var adelante = Extender(n, a, oj, bj, DirSalida(a[bj], oj) * -1.0, usadas, visit);
            var centro = new List<Salto>
            {
                new Salto { Arista = bi, Desde = oi, Hasta = nodo },
                new Salto { Arista = bj, Desde = nodo, Hasta = oj },
            };
            return Componer(a, atras, centro, adelante);
        }

        /// <summary>"LT" si el ramal sale a la izquierda de la dirección de llegada (AnguloFirmado &gt; 0); si no "RT". C.4.</summary>
        internal static string LadoRamal(V2 dirLlegada, V2 dirRamal) { return AnguloFirmado(dirLlegada, dirRamal) > 0 ? "LT" : "RT"; }

        /// <summary>true si el recorrido debe invertirse para empezar al OESTE (o al SUR si |ΔX| &lt; 0.3·|ΔY|): conduit y presión. C.4.</summary>
        internal static bool DebeInvertirOesteSur(double x0, double y0, double x1, double y1)
        {
            double dx = x1 - x0, dy = y1 - y0;
            if (Math.Abs(dx) < 0.3 * Math.Abs(dy)) return y0 > y1;
            return x0 > x1;
        }

        // ------------------------------------------------------------ C.5 tangentes

        private static V2 Rot(V2 v, double ang) { double c = Math.Cos(ang), s = Math.Sin(ang); return new V2(v.X * c - v.Y * s, v.X * s + v.Y * c); }

        /// <summary>Tangentes unitarias de un segmento con bulge: salida en P0 y llegada en P1. false si |P1−P0| ≈ 0. C.5.</summary>
        internal static bool Tangentes(V2 p0, V2 p1, double bulge, out V2 t0, out V2 t1)
        {
            t0 = new V2(0, 0); t1 = new V2(0, 0);
            if (!(p1 - p0).TryUnit(out V2 c)) return false;
            if (double.IsNaN(bulge)) bulge = 0;
            double th = 4.0 * Math.Atan(bulge);
            t0 = Rot(c, -th / 2.0); t1 = Rot(c, th / 2.0);
            return true;
        }

        /// <summary>
        /// Punto medio del arco P0→P1 con bulge b (b = 0 → punto medio de la cuerda). Con la convención de AutoCAD
        /// (b &gt; 0 = antihorario) el arco queda a la DERECHA del sentido de la cuerda. C.5 (el texto del diseño dice
        /// «izquierda»: es un error; sus propias tangentes de R5 lo contradicen).
        /// </summary>
        internal static V2 PuntoMedioArco(V2 p0, V2 p1, double bulge)
        {
            V2 m = (p0 + p1) * 0.5;
            if (bulge == 0 || double.IsNaN(bulge) || !(p1 - p0).TryUnit(out V2 c)) return m;
            double s = bulge * (p1 - p0).Largo / 2.0;
            V2 derecha = new V2(c.Y, -c.X);
            return m + derecha * s;
        }

        /// <summary>Largo en planta del segmento P0→P1 con bulge (cuerda si b = 0). ft.</summary>
        internal static double LargoSegmento(V2 p0, V2 p1, double bulge)
        {
            double cuerda = (p1 - p0).Largo;
            if (bulge == 0 || double.IsNaN(bulge) || cuerda < 1e-12) return cuerda;
            double th = 4.0 * Math.Atan(Math.Abs(bulge));
            double sinm = Math.Sin(th / 2.0);
            if (sinm < 1e-12) return cuerda;
            return cuerda / (2.0 * sinm) * th;
        }

        /// <summary>Punto a la fracción <paramref name="t"/> del largo del segmento (arco o recta).</summary>
        private static V2 PuntoSegmento(V2 p0, V2 p1, double bulge, double t)
        {
            if (bulge == 0 || double.IsNaN(bulge) || !Tangentes(p0, p1, bulge, out V2 t0, out _)) return p0 + (p1 - p0) * t;
            double th = 4.0 * Math.Atan(bulge);
            double cuerda = (p1 - p0).Largo;
            double r = cuerda / (2.0 * Math.Sin(Math.Abs(th) / 2.0));
            V2 izq = new V2(-t0.Y, t0.X);
            V2 centro = p0 + izq * (r * Math.Sign(th));
            return centro + Rot(p0 - centro, th * t);
        }

        /// <summary>Completa Largo, DirSalidaA/B (DirSalidaB = −t1) y Valida de una arista a partir de sus nodos. C.2-4 / C.5.</summary>
        internal static void CompletarArista(GArista a, GNodo na, GNodo nb)
        {
            V2 p0 = new V2(na.X, na.Y), p1 = new V2(nb.X, nb.Y);
            a.Largo = LargoSegmento(p0, p1, a.Bulge);
            bool ok = Tangentes(p0, p1, a.Bulge, out V2 t0, out V2 t1);
            a.DirSalidaA = t0; a.DirSalidaB = t1 * -1.0;
            a.Valida = ok && a.Largo >= 1e-9 && !double.IsNaN(a.Largo);
        }

        // ------------------------------------------------------------ C.5 traza

        /// <summary>
        /// Traza del eje: [N0 − t0·ext, N0…Nk, Nk + tk·ext] con bulges [0, b0…b(k−1), 0], sin duplicados (&lt;0.01 ft)
        /// ni vértices colineales. Lanza InvalidOperationException si quedan &lt; 2 vértices. <paramref name="log"/> recibe «[GRAFO] …». C.5.
        /// </summary>
        internal static List<V2Bulge> Traza(List<V2> nodos, List<double> bulges, double ext, List<string> log = null)
        {
            if (nodos == null || nodos.Count < 2) throw new InvalidOperationException("✗ No se pudo formar la traza del eje");
            int k = nodos.Count - 1;
            double B(int i) { return bulges != null && i < bulges.Count && !double.IsNaN(bulges[i]) ? bulges[i] : 0.0; }
            // tangentes de los extremos (del primer y último segmento no degenerado)
            V2 t0 = new V2(1, 0), tk = new V2(1, 0);
            for (int i = 0; i < k; i++) if (Tangentes(nodos[i], nodos[i + 1], B(i), out V2 a0, out _)) { t0 = a0; break; }
            for (int i = k - 1; i >= 0; i--) if (Tangentes(nodos[i], nodos[i + 1], B(i), out _, out V2 a1)) { tk = a1; break; }
            var v = new List<V2Bulge>();
            var esNodo = new List<bool>();
            v.Add(new V2Bulge { X = nodos[0].X - t0.X * ext, Y = nodos[0].Y - t0.Y * ext, Bulge = 0 }); esNodo.Add(false);
            for (int i = 0; i <= k; i++) { v.Add(new V2Bulge { X = nodos[i].X, Y = nodos[i].Y, Bulge = i < k ? B(i) : 0 }); esNodo.Add(true); }
            v.Add(new V2Bulge { X = nodos[k].X + tk.X * ext, Y = nodos[k].Y + tk.Y * ext, Bulge = 0 }); esNodo.Add(false);

            // 1. duplicados consecutivos (< 0.01 ft): se conserva el bulge no nulo
            for (int i = 0; i + 1 < v.Count;)
            {
                double d = Math.Sqrt((v[i + 1].X - v[i].X) * (v[i + 1].X - v[i].X) + (v[i + 1].Y - v[i].Y) * (v[i + 1].Y - v[i].Y));
                if (d < 0.01)
                {
                    if (esNodo[i] && esNodo[i + 1] && log != null) log.Add("[GRAFO] conexión vertical");
                    var keep = v[i];
                    keep.Bulge = v[i + 1].Bulge != 0 ? v[i + 1].Bulge : 0.0;
                    v[i] = keep; esNodo[i] = esNodo[i] || esNodo[i + 1];
                    v.RemoveAt(i + 1); esNodo.RemoveAt(i + 1);
                    continue;
                }
                i++;
            }
            // 2. colineales interiores entre dos rectas
            for (int i = 1; i + 1 < v.Count;)
            {
                if (v[i - 1].Bulge == 0 && v[i].Bulge == 0)
                {
                    V2 a = new V2(v[i].X - v[i - 1].X, v[i].Y - v[i - 1].Y), b = new V2(v[i + 1].X - v[i].X, v[i + 1].Y - v[i].Y);
                    if (a.TryUnit(out V2 ua) && b.TryUnit(out V2 ub))
                    {
                        double defl = Math.Abs(Math.Atan2(ua.Cross(ub), ua.Dot(ub)));
                        if (defl < 1e-6) { v.RemoveAt(i); esNodo.RemoveAt(i); continue; }
                    }
                }
                i++;
            }
            if (v.Count < 2) throw new InvalidOperationException("✗ No se pudo formar la traza del eje");
            var ult = v[v.Count - 1]; ult.Bulge = 0; v[v.Count - 1] = ult;
            return v;
        }

        private static V2 P(V2Bulge b) { return new V2(b.X, b.Y); }

        /// <summary>Largo total de la traza en planta (arcos incluidos). ft. C.5.</summary>
        internal static double LargoTraza(List<V2Bulge> traza)
        {
            double L = 0;
            if (traza == null) return 0;
            for (int i = 0; i + 1 < traza.Count; i++) L += LargoSegmento(P(traza[i]), P(traza[i + 1]), traza[i].Bulge);
            return L;
        }

        /// <summary>Punto de la traza a la distancia <paramref name="dist"/> desde el primer vértice (acotado a [0, largo]). C.5.</summary>
        internal static V2 PuntoEnTraza(List<V2Bulge> traza, double dist)
        {
            if (traza == null || traza.Count == 0) return new V2(0, 0);
            if (traza.Count == 1 || dist <= 0) return P(traza[0]);
            double acum = 0;
            for (int i = 0; i + 1 < traza.Count; i++)
            {
                double l = LargoSegmento(P(traza[i]), P(traza[i + 1]), traza[i].Bulge);
                if (dist <= acum + l || i + 2 == traza.Count)
                {
                    double t = l < 1e-12 ? 0 : Math.Max(0, Math.Min(1, (dist - acum) / l));
                    return PuntoSegmento(P(traza[i]), P(traza[i + 1]), traza[i].Bulge, t);
                }
                acum += l;
            }
            return P(traza[traza.Count - 1]);
        }

        /// <summary>Cuerdas de un segmento: (inicio, fin, distancia acumulada al inicio, largo de arco que representa).</summary>
        private static IEnumerable<(V2 a, V2 b, double d0, double largo)> Cuerdas(List<V2Bulge> traza)
        {
            double acum = 0;
            for (int i = 0; i + 1 < traza.Count; i++)
            {
                V2 p0 = P(traza[i]), p1 = P(traza[i + 1]);
                double b = traza[i].Bulge, l = LargoSegmento(p0, p1, b);
                int n = b == 0 ? 1 : CUERDAS_ARCO;
                for (int j = 0; j < n; j++)
                {
                    V2 qa = PuntoSegmento(p0, p1, b, (double)j / n), qb = PuntoSegmento(p0, p1, b, (double)(j + 1) / n);
                    yield return (qa, qb, acum + l * j / n, l / n);
                }
                acum += l;
            }
        }

        /// <summary>Distancia sobre la traza de la proyección de p en el segmento más cercano (arcos en 16 cuerdas). ft. C.5.</summary>
        internal static double DistanciaEnTraza(List<V2Bulge> traza, V2 p)
        {
            if (traza == null || traza.Count < 2) return 0;
            double best = double.MaxValue, res = 0;
            foreach (var c in Cuerdas(traza))
            {
                V2 ab = c.b - c.a; double L2 = ab.Dot(ab);
                double t = L2 < 1e-18 ? 0 : Math.Max(0, Math.Min(1, (p - c.a).Dot(ab) / L2));
                V2 q = c.a + ab * t;
                double d = (p - q).Largo;
                if (d < best - 1e-12) { best = d; res = c.d0 + c.largo * t; }
            }
            return res;
        }

        /// <summary>Estación preliminar de un punto: 100 + DistanciaEnTraza − distN0. D.3 (T0).</summary>
        internal static double EstacionPreliminar(List<V2Bulge> traza, double distN0, V2 p)
        {
            return EST_INICIAL + DistanciaEnTraza(traza, p) - distN0;
        }

        // ------------------------------------------------------------ C.6

        /// <summary>Deflexión vertical |atan(sOut) − atan(sIn)| en GRADOS, con s = pendiente (ratio). C.6.</summary>
        internal static double DeflexionVertical(double sIn, double sOut)
        {
            return Math.Abs(Math.Atan(sOut) - Math.Atan(sIn)) * 180.0 / Math.PI;
        }

        /// <summary>Pendiente de un tubo: (zFin − zIni)/max(largo2D, 0.01). C.6.</summary>
        internal static double Pendiente(double zIni, double zFin, double largo2D) { return (zFin - zIni) / Math.Max(largo2D, 0.01); }

        // ------------------------------------------------------------ C.7

        /// <summary>
        /// Cortes del segmento a→b con la traza (arcos en 16 cuerdas). Estación = estPrimerVertice + distancia; AnguloDeg 0..90;
        /// T = parámetro 0..1 sobre a→b. Lista vacía si |b − a| &lt; 1e-9. C.7.
        /// </summary>
        internal static List<CorteTraza> CortarTraza(List<V2Bulge> traza, double estPrimerVertice, V2 a, V2 b)
        {
            var r = new List<CorteTraza>();
            V2 ab = b - a;
            if (traza == null || traza.Count < 2 || !ab.TryUnit(out V2 uab)) return r;
            foreach (var c in Cuerdas(traza))
            {
                V2 cd = c.b - c.a;
                double den = cd.Cross(ab);
                if (Math.Abs(den) < 1e-12) continue;                          // paralelos
                V2 w = a - c.a;
                double u = w.Cross(ab) / den;                                  // sobre la cuerda
                double t = w.Cross(cd) / den;                                  // sobre a→b
                if (u < -1e-9 || u > 1 + 1e-9 || t < -1e-9 || t > 1 + 1e-9) continue;
                u = Math.Max(0, Math.Min(1, u)); t = Math.Max(0, Math.Min(1, t));
                double est = estPrimerVertice + c.d0 + c.largo * u;
                if (r.Any(x => Math.Abs(x.Estacion - est) < 1e-6)) continue;   // vértice compartido entre cuerdas
                cd.TryUnit(out V2 ucd);
                double ang = Math.Acos(Math.Min(1.0, Math.Abs(ucd.Dot(uab)))) * 180.0 / Math.PI;
                r.Add(new CorteTraza { Estacion = est, AnguloDeg = ang, T = t, P = a + ab * t });
            }
            r.Sort((x, y) => x.Estacion.CompareTo(y.Estacion));
            return r;
        }

        // ------------------------------------------------------------ C.3-3

        private static int RangoRed(string red, string nombreRed)
        {
            string r = (red ?? "").Trim();
            if (string.Equals(r, (nombreRed ?? "").Trim(), StringComparison.OrdinalIgnoreCase)) return 0;
            if (string.Equals(r, "CROSS-CONNECTS", StringComparison.OrdinalIgnoreCase)) return 1;
            return 2;
        }

        /// <summary>
        /// Accesorio sólido al que pertenece el extremo E=(ex,ey,ez eje) con dirección de salida u (planta) y diámetro
        /// dTuboFt: filtro Ralc/dz/ángulo ≤25°, menor d3 y desempate por red. Devuelve CandidatoAccesorio.Id o −1. C.3-3.
        /// </summary>
        internal static int ElegirAccesorio(double ex, double ey, double ez, V2 u, double dTuboFt, IReadOnlyList<CandidatoAccesorio> candidatos, string nombreRed)
        {
            if (candidatos == null) return -1;
            bool uOk = u.TryUnit(out V2 uu);
            var ok = new List<(CandidatoAccesorio c, double d3)>();
            foreach (var c in candidatos)
            {
                if (c == null) continue;
                double dp = double.IsNaN(c.DiamPrincipalFt) ? 0 : c.DiamPrincipalFt;
                double dm = Math.Max(double.IsNaN(dTuboFt) ? 0 : dTuboFt, dp);
                double ralc = 1.5 * dm + 0.75;
                if (!double.IsNaN(c.LargoTotalFt)) ralc = Math.Max(ralc, c.LargoTotalFt / 2.0 + 0.5);
                V2 dv = new V2(c.X - ex, c.Y - ey);
                double d2 = dv.Largo;
                double dz = double.IsNaN(c.Z) || double.IsNaN(ez) ? 0 : Math.Abs(c.Z - ez);
                if (d2 > ralc || dz > dm / 2.0 + 0.5) continue;
                if (d2 > 0.25)
                {
                    if (!uOk || !dv.TryUnit(out V2 ud)) continue;
                    double ang = Math.Acos(Math.Max(-1, Math.Min(1, ud.Dot(uu)))) * 180.0 / Math.PI;
                    if (ang > 25.0) continue;
                }
                ok.Add((c, Math.Sqrt(d2 * d2 + dz * dz)));
            }
            if (ok.Count == 0) return -1;
            double min = ok.Min(x => x.d3);
            var mejor = ok.Where(x => x.d3 < min + 0.05)
                          .OrderBy(x => RangoRed(x.c.Red, nombreRed)).ThenBy(x => x.d3).ThenBy(x => x.c.Id).First();
            return mejor.c.Id;
        }

        // ------------------------------------------------------------ utilidades

        /// <summary>Interpolación lineal de z en e entre (e0,z0) y (e1,z1); si e0 ≈ e1 devuelve z0. D.3.</summary>
        internal static double Interpolar(double e, double e0, double z0, double e1, double z1)
        {
            if (Math.Abs(e1 - e0) < 1e-9) return z0;
            return z0 + (z1 - z0) * (e - e0) / (e1 - e0);
        }

        /// <summary>true si la lista crece estrictamente (monotonía de EstNodo, D.3).</summary>
        internal static bool EsEstrictamenteCreciente(IReadOnlyList<double> v)
        {
            if (v == null) return true;
            for (int i = 1; i < v.Count; i++) if (!(v[i] > v[i - 1])) return false;
            return true;
        }
    }
}
