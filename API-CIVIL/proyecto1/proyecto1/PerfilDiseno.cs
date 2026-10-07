using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  MAQUETACIÓN DEL PERFIL — PURO (DISENO.md B.3, F.1–F.4, F.9, F.10)
//   · Sin Autodesk: lo compila también el arnés PerfilPruebas.
//   · Una sola clase PerfilDiseno repartida en tres archivos parciales:
//       PerfilDiseno.cs        constantes, V/VE, intervalos, métrica, Maquetar,
//                              verificaciones y calibración.
//       PerfilDisenoFranjas.cs Empaquetar1D, segmentos por paredes, holgura y
//                              reglas «si no cabe» (F.5, F.6, F.8).
//       PerfilDisenoFila.cs    fila de tramos (F.7) y complementos (F.11).
//   · Unidades: PULGADAS DE PLOTEO salvo que se indique ft.
// ============================================================================

namespace Civil3DBasico
{
    // ---------------------------------------------------------------- B.3 tipos

    internal enum FranjaTipo { Superior, Inferior }

    internal sealed class BloqueTexto
    {
        public string Id = ""; public FranjaTipo Franja; public int Prioridad = 50;   // también es el PESO del empaquetado
        public bool PuedeCambiarFranja, PuedeAlternar = true, PuedeRecortar;
        public double EstAncla, ZAncla;                  // ft
        public string[] Lineas = new string[0]; public bool Vertical = true;
        public double Ancho, Alto; public bool Medido;   // in: extensión X / Y del bloque de texto (sin leader)
        public double DxEnganche = PerfilDiseno.H_TEXTO; // in: de X0 al punto de enganche del leader (cola de la línea 1)
        // salida
        public FranjaTipo FranjaFinal; public int Nivel = 1; public double X0, Y0;
        public bool Recortado, Descartado;
    }

    internal sealed class FilaTramo
    {
        public string Id = ""; public double EstIni, EstFin; public string L1 = "", L2 = "", L3 = "";
        public double KMedida = 1.0;                     // medido/predicho de la variante creada en T1
        public double ZCorona = double.NaN;              // [contrato] corona en la estación media (ancla si pasa a vertical, F.7-4)
        // salida
        public bool Omitido, ConLeader, AVertical; public int Fila = 1, NumLineas = 2;
        public double Ancho, Alto, X0, Y0, Cx;
    }

    internal sealed class CajaDibujo { public string Id = ""; public double EstIni, EstFin, ZMin, ZMax; } // elipses de cruce, en ft
    internal sealed class Caja { public string Id = ""; public double X0, Y0, X1, Y1; }
    internal sealed class Leader { public string Id = ""; public double X0, Y0, X1, Y1; }  // enganche → ancla (in)
    internal sealed class Intervalos { public double EstMayor, EstMenor, CotaMayor, CotaMenor; }

    internal sealed class EntradaMaquetacion
    {
        public double S; public double EstIni, EstFin;           // primer y último nodo de la HOJA
        public double EstMinPermitida, EstMaxPermitida;          // rango del eje (con prolongaciones)
        public double ZMinDibujo, ZMaxDibujo;                    // tubos, cruces, estructuras (SIN terreno)
        public double[] TerrenoEst = new double[0], TerrenoZ = new double[0];  // muestras (NaN admitido)
        public List<BloqueTexto> Bloques = new List<BloqueTexto>();
        public List<FilaTramo> Tramos = new List<FilaTramo>();
        public List<CajaDibujo> CajasDibujo = new List<CajaDibujo>();
        public double? VForzada; public Intervalos IntForzados;  // null = automático
    }

    internal sealed class ResultadoMaquetacion
    {
        public double V, VE; public Intervalos Int; public double VRecomendada;
        public double StationStart, StationEnd, ElevationMin, ElevationMax, AnchoMarco, AltoMarco;
        public double HolguraSup, HolguraInf, YBaseSup, YTopeInf, YFila1Base, YFila2Base = double.NaN;
        public List<double> Paredes = new List<double>();        // estaciones de las verticales de límite (fusionadas)
        public List<string> Avisos = new List<string>(), Recortados = new List<string>();
        public List<string> Solapes = new List<string>(), FueraDeMarco = new List<string>();
        public List<string> CrucesLeaders = new List<string>(), CortesLeaderCaja = new List<string>(), PendientesExcedidas = new List<string>();
        public bool SinSolapes;                                  // Solapes, FueraDeMarco y CrucesLeaders vacíos
    }

    // ---------------------------------------------------------------- F.1 + F.2

    internal static partial class PerfilDiseno
    {
        public const double H_TEXTO = 0.12, H_NUM = 0.10, H_TITULO = 0.20;
        public const double PASO_LINEA = 0.20, ANCHO_CAR = 0.79;
        public const double GAP = 0.15, MARGEN_MARCO = 0.10, MARGEN_PARED = 0.05;
        public const double HOLGURA_DIBUJO = 0.20, HOLGURA_MAX = 1.50, PENDIENTE_LEADER_MAX = 1.7; // |dx|/dy ≈ 60°
        public const double SEP_FILA = 0.10, SEP_FILAS = 0.10, BASE_TEXTO_FILA = 0.05, MARGEN_CELDA = 0.10;
        public const double FRANJA_INF_MIN = 0.50, SEP_NIVEL = 0.10, HUECO_LEADER_MIN = 0.30;
        public const double PAD_MIN = 1.5, PAD_MAX = 4.0, SOBRANTE_MAX_ELEVMIN = 0.75;
        public const double ALTO_MAX_DIBUJO = 8.0, ALTO_MAX_MARCO = 12.0, ANCHO_MAX_MARCO = 30.0;
        public const double FUSION_PAREDES = 0.15, TRAMO_MIN_IN = 0.25, TRAMO_MIN_FT = 2.0;
        public const double TOL_SOLAPE = 0.02, TOL_CORRECCION = 0.02;
        public const double REDONDEO_EST = 5.0;                        // ft
        public static readonly double[] V_ESTANDAR = { 1, 2, 2.5, 4, 5, 10, 20, 25, 40, 50, 100 };
        private static readonly double[] COTA_MAYOR = { 1, 2, 5, 10, 20, 50, 100 };
        private static readonly double[] COTA_MENOR = { 0.5, 0.5, 1, 2, 5, 10, 20 };
        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        // ------------------------------------------------------------ F.3

        /// <summary>V (ft de cota por in) a partir de S según VEobj (F.3). VE = s/V.</summary>
        public static double ElegirV(double s)
        {
            double veObj = s <= 10 ? 2.5 : (s <= 20 ? s / 5.0 : Math.Min(10.0, s / 4.0));
            double vObj = s / veObj;
            foreach (double v in V_ESTANDAR) if (v >= vObj - 1e-9) return v;
            return Math.Ceiling(vObj / 100.0 - 1e-9) * 100.0;
        }

        /// <summary>Escala del dibujo por debajo de la cual el perfil elige la suya (1"=1'…1"=5'
        /// es escala de detalle: con S=1 la VE quedaba en 1 y el perfil salía aplanado, 2026-10-06).</summary>
        public const double S_MIN_PERFIL = 10.0;
        public const double ANCHO_OBJ_PERFIL = 24.0;                   // in de ploteo del recorrido
        public static readonly double[] S_ESTANDAR = { 10, 20, 30, 40, 50, 60, 100, 200, 500, 1000 };

        /// <summary>Escala del perfil (ft por in) para un recorrido de `largoFt`: la menor
        /// estándar con la que el recorrido mide ≤ ANCHO_OBJ_PERFIL in (como el plano de
        /// referencia: 1"=10' y VE 2.5 en un cruce de ~100 ft).</summary>
        public static double EscalaAuto(double largoFt)
        {
            if (double.IsNaN(largoFt) || largoFt <= 0) return S_ESTANDAR[0];
            foreach (double s in S_ESTANDAR) if (largoFt / s <= ANCHO_OBJ_PERFIL + 1e-9) return s;
            return S_ESTANDAR[S_ESTANDAR.Length - 1];
        }

        /// <summary>Siguiente V estándar mayor que v; s si lo supera (VE = 1); v si v ≥ s. F.3.</summary>
        public static double SiguienteV(double v, double s)
        {
            if (v >= s - 1e-9) return v;
            foreach (double c in V_ESTANDAR)
                if (c > v + 1e-9) return c > s + 1e-9 ? s : c;
            return s;
        }

        /// <summary>Intervalos de rejilla (cota mayor/menor en ft, estación mayor/menor en ft) para S y V. F.3.</summary>
        public static Intervalos ElegirIntervalos(double s, double v)
        {
            var it = new Intervalos();
            int k = COTA_MAYOR.Length - 1;
            for (int i = 0; i < COTA_MAYOR.Length; i++) if (COTA_MAYOR[i] / v >= 2.0 - 1e-9) { k = i; break; }
            it.CotaMayor = COTA_MAYOR[k]; it.CotaMenor = COTA_MENOR[k];
            it.EstMayor = 100.0 / s >= 0.75 - 1e-9 ? 100.0 : (500.0 / s >= 0.75 - 1e-9 ? 500.0 : 1000.0);
            it.EstMenor = it.EstMayor / 10.0;
            return it;
        }

        // ------------------------------------------------------------ métrica

        /// <summary>Ancho (in) de un bloque vertical de n líneas: h + (n−1)·PASO_LINEA. F.2.</summary>
        public static double AnchoBloqueVertical(int lineas, double h = H_TEXTO) { return h + Math.Max(0, lineas - 1) * PASO_LINEA; }

        /// <summary>Largo (in) de una línea: LongitudVisible·ANCHO_CAR·h. F.2.</summary>
        public static double LargoLinea(string texto, double h = H_TEXTO) { return LongitudVisible(texto) * ANCHO_CAR * h; }

        /// <summary>Caracteres visibles: "%%d" cuenta 1; "\P" 0; "\{", "\}", "\\" cuentan 1. F.2.</summary>
        public static int LongitudVisible(string texto)
        {
            if (string.IsNullOrEmpty(texto)) return 0;
            int n = 0;
            for (int i = 0; i < texto.Length; i++)
            {
                if (texto[i] == '%' && i + 2 < texto.Length && texto[i + 1] == '%' && (texto[i + 2] == 'd' || texto[i + 2] == 'D')) { n++; i += 2; continue; }
                if (texto[i] == '\\' && i + 1 < texto.Length)
                {
                    char c = texto[i + 1];
                    if (c == 'P') { i++; continue; }
                    if (c == '{' || c == '}' || c == '\\') { n++; i++; continue; }
                }
                n++;
            }
            return n;
        }

        /// <summary>Largo máximo de las líneas (in).</summary>
        internal static double LargoMax(IEnumerable<string> lineas, double h = H_TEXTO)
        {
            double m = 0;
            if (lineas != null) foreach (string l in lineas) m = Math.Max(m, LargoLinea(l, h));
            return m;
        }

        /// <summary>Tamaño predicho de un bloque vertical: Ancho = AnchoBloqueVertical(n), Alto = máx LargoLinea. F.2.</summary>
        public static void PredecirBloque(BloqueTexto b)
        {
            int n = b.Lineas == null ? 0 : b.Lineas.Length;
            if (b.Vertical) { b.Ancho = AnchoBloqueVertical(Math.Max(1, n)); b.Alto = LargoMax(b.Lineas); }
            else { b.Ancho = LargoMax(b.Lineas); b.Alto = AnchoBloqueVertical(Math.Max(1, n)); }
        }

        /// <summary>Tamaño predicho de un tramo en la variante de numLineas (1..3): Ancho = máx LargoLinea, Alto = h+(n−1)·PASO (×KMedida). F.2/F.7.</summary>
        public static void PredecirTramo(FilaTramo t, int numLineas)
        {
            var ls = LineasVariante(t, numLineas);
            double k = t.KMedida > 0 && !double.IsNaN(t.KMedida) ? t.KMedida : 1.0;
            t.NumLineas = ls.Length;
            t.Ancho = LargoMax(ls) * k;
            t.Alto = AnchoBloqueVertical(ls.Length) * k;
        }

        /// <summary>floor(v/paso + 1e-9)·paso.</summary>
        public static double RedondearAbajo(double v, double paso) { return paso <= 0 ? v : Math.Floor(v / paso + 1e-9) * paso; }

        /// <summary>ceil(v/paso − 1e-9)·paso.</summary>
        public static double RedondearArriba(double v, double paso) { return paso <= 0 ? v : Math.Ceiling(v / paso - 1e-9) * paso; }

        // ------------------------------------------------------------ F.4 (orquestación; el detalle vive en Franjas/Fila)

        /// <summary>Maquetación completa de UNA hoja (bucle F.4: V, rango, franjas, fila, holguras, reglas, verificación).</summary>
        public static ResultadoMaquetacion Maquetar(EntradaMaquetacion e)
        {
            var r = new ResultadoMaquetacion();
            if (e == null) return r;
            double s = e.S > 0 && e.S <= 1000 ? e.S : 20.0;
            var st = PrepararEstado(e, s);
            double v = e.VForzada ?? ElegirV(s);
            Intervalos it = e.IntForzados ?? ElegirIntervalos(s, v);
            r.VRecomendada = v;
            bool reducida = false;
            for (int alt = 0; alt < 9; alt++)
            {
                r.V = v; r.VE = s / v; r.Int = it;
                for (int fix = 0; fix <= 3; fix++)                     // F.4-7: cruces de leaders → intercambio
                {
                    Horizontal(e, r, st, s);
                    Vertical(e, r, st, s);
                    if (fix == 3 || !IntercambiarCruces(e, r, st, s)) break;
                }
                bool excede = (st.ZMaxDib - st.ZMinDib) / v > ALTO_MAX_DIBUJO + 1e-9 || r.AltoMarco > ALTO_MAX_MARCO + 1e-9;
                if (!excede) break;
                double nv = SiguienteV(v, s);
                if (e.VForzada.HasValue)
                {
                    r.VRecomendada = Math.Max(r.VRecomendada, nv);
                    r.Avisos.Add("Altura excedida con V forzada " + v.ToString("0.##", INV) + " (recomendada " + r.VRecomendada.ToString("0.##", INV) + ")");
                    break;
                }
                if (nv <= v + 1e-9 || alt == 8) break;
                v = nv; it = e.IntForzados ?? ElegirIntervalos(s, v); reducida = true;
                r.VRecomendada = v;
            }
            if (reducida) r.Avisos.Add("VE reducida a " + r.VE.ToString("0.##", INV));
            Verificar(e, r, s);
            return r;
        }

        /// <summary>F.4-4: rango vertical, franjas, fila y posiciones Y (y convierte X de x' al marco).</summary>
        private static void Vertical(EntradaMaquetacion e, ResultadoMaquetacion r, EstadoMaq st, double s)
        {
            double v = r.V;
            double zMax = e.ZMaxDibujo, zMin = e.ZMinDibujo;
            if (e.TerrenoEst != null && e.TerrenoZ != null)
                for (int i = 0; i < Math.Min(e.TerrenoEst.Length, e.TerrenoZ.Length); i++)
                {
                    double te = e.TerrenoEst[i], tz = e.TerrenoZ[i];
                    if (double.IsNaN(te) || double.IsNaN(tz) || te < r.StationStart - 1e-9 || te > r.StationEnd + 1e-9) continue;
                    zMax = Math.Max(zMax, tz); zMin = Math.Min(zMin, tz);
                }
            st.ZMaxDib = zMax; st.ZMinDib = zMin;
            var vivos = e.Bloques.Where(b => !b.Descartado).ToList();
            double AltoMax(FranjaTipo f, int nivel) { return vivos.Where(b => b.FranjaFinal == f && b.Nivel == nivel).Select(b => b.Alto).DefaultIfEmpty(0).Max(); }
            double ht1 = AltoMax(FranjaTipo.Superior, 1), ht2 = AltoMax(FranjaTipo.Superior, 2);
            double hb1 = AltoMax(FranjaTipo.Inferior, 1), hb2 = AltoMax(FranjaTipo.Inferior, 2);
            double ht = ht1 + (ht2 > 0 ? SEP_NIVEL + ht2 : 0);
            bool hayInf = vivos.Any(b => b.FranjaFinal == FranjaTipo.Inferior);
            double hb = hayInf ? hb1 + (hb2 > 0 ? SEP_NIVEL + hb2 : 0) : FRANJA_INF_MIN - HOLGURA_DIBUJO - MARGEN_MARCO;
            var rot = e.Tramos.Where(t => !t.Omitido && !t.AVertical).ToList();
            double h1 = rot.Where(t => t.Fila == 1).Select(t => t.Alto).DefaultIfEmpty(0).Max();
            double h2 = rot.Where(t => t.Fila == 2).Select(t => t.Alto).DefaultIfEmpty(0).Max();
            double altoFila = rot.Count > 0 ? MARGEN_MARCO + (h2 > 0 ? h2 + BASE_TEXTO_FILA + SEP_FILAS : 0) + h1 + BASE_TEXTO_FILA : 0;

            double zNec = zMin - (r.HolguraInf + hb + MARGEN_MARCO) * v;
            r.ElevationMin = RedondearAbajo(zNec, r.Int.CotaMayor);
            if ((zNec - r.ElevationMin) / v > SOBRANTE_MAX_ELEVMIN) r.ElevationMin = RedondearAbajo(zNec, r.Int.CotaMenor);
            double Y(double z) { return (z - r.ElevationMin) / v; }
            r.YTopeInf = Y(zMin) - r.HolguraInf;
            r.YBaseSup = Y(zMax) + r.HolguraSup;
            double tope = r.YBaseSup + ht + (altoFila > 0 ? SEP_FILA + altoFila : MARGEN_MARCO);
            r.ElevationMax = RedondearArriba(r.ElevationMin + tope * v, r.Int.CotaMenor);
            r.AltoMarco = (r.ElevationMax - r.ElevationMin) / v;
            r.YFila2Base = h2 > 0 ? r.AltoMarco - MARGEN_MARCO - h2 - BASE_TEXTO_FILA : double.NaN;
            r.YFila1Base = (h2 > 0 ? r.YFila2Base - SEP_FILAS : r.AltoMarco - MARGEN_MARCO) - h1 - BASE_TEXTO_FILA;
            if (rot.Count == 0) r.YFila1Base = r.AltoMarco - MARGEN_MARCO;

            foreach (var b in vivos)
            {
                b.X0 += st.Off;                                         // x' → marco
                if (b.FranjaFinal == FranjaTipo.Superior)
                    b.Y0 = b.Nivel == 1 ? r.YBaseSup : r.YBaseSup + ht1 + SEP_NIVEL;
                else
                    b.Y0 = b.Nivel == 1 ? r.YTopeInf - hb1 : r.YTopeInf - hb1 - SEP_NIVEL - hb2;
            }
            foreach (var t in e.Tramos)
            {
                if (t.Omitido || t.AVertical) continue;
                t.X0 += st.Off; t.Cx += st.Off;                         // x' → marco
                t.Y0 = (t.Fila == 2 ? r.YFila2Base : r.YFila1Base) + BASE_TEXTO_FILA;
            }
        }

        // ------------------------------------------------------------ F.9 geometría final

        /// <summary>Cajas finales (in, marco) de bloques y tramos no descartados/omitidos. F.2.</summary>
        public static List<Caja> CajasFinales(EntradaMaquetacion e, ResultadoMaquetacion r)
        {
            var c = new List<Caja>();
            foreach (var b in e.Bloques.Where(b => !b.Descartado))
                c.Add(new Caja { Id = b.Id, X0 = b.X0, Y0 = b.Y0, X1 = b.X0 + b.Ancho, Y1 = b.Y0 + b.Alto });
            foreach (var t in e.Tramos.Where(t => !t.Omitido && !t.AVertical))
                c.Add(new Caja { Id = t.Id, X0 = t.X0, Y0 = t.Y0, X1 = t.X0 + t.Ancho, Y1 = t.Y0 + t.Alto });
            return c;
        }

        /// <summary>Leaders finales enganche → ancla (in, marco). F.9.</summary>
        public static List<Leader> LeadersFinales(EntradaMaquetacion e, ResultadoMaquetacion r)
        {
            double s = e.S > 0 ? e.S : 20.0;
            var l = new List<Leader>();
            foreach (var b in e.Bloques.Where(b => !b.Descartado))
            {
                double yEng = b.FranjaFinal == FranjaTipo.Superior ? b.Y0 : b.Y0 + b.Alto;
                l.Add(new Leader { Id = b.Id, X0 = b.X0 + b.DxEnganche, Y0 = yEng, X1 = XMarco(b.EstAncla, r, s), Y1 = YMarco(b.ZAncla, r) });
            }
            foreach (var t in e.Tramos.Where(t => !t.Omitido && !t.AVertical && t.ConLeader))
                l.Add(new Leader { Id = t.Id, X0 = t.X0 + t.Ancho / 2.0, Y0 = t.Y0, X1 = t.Cx, Y1 = r.YFila1Base });
            return l;
        }

        /// <summary>Cajas (in, marco) de las elipses de cruce. F.9.</summary>
        public static List<Caja> CajasDeDibujo(EntradaMaquetacion e, ResultadoMaquetacion r)
        {
            double s = e.S > 0 ? e.S : 20.0;
            return e.CajasDibujo.Select(c => new Caja
            {
                Id = c.Id, X0 = XMarco(Math.Min(c.EstIni, c.EstFin), r, s), X1 = XMarco(Math.Max(c.EstIni, c.EstFin), r, s),
                Y0 = YMarco(Math.Min(c.ZMin, c.ZMax), r), Y1 = YMarco(Math.Max(c.ZMin, c.ZMax), r),
            }).ToList();
        }

        /// <summary>Parejas de cajas que se solapan ("idA|idB"). F.9.</summary>
        public static List<string> Solapes(IReadOnlyList<Caja> c, double tol = TOL_SOLAPE)
        {
            var r = new List<string>();
            for (int i = 0; i < c.Count; i++)
                for (int j = i + 1; j < c.Count; j++)
                    if (Solapan(c[i], c[j], tol)) r.Add(c[i].Id + "|" + c[j].Id);
            return r;
        }

        /// <summary>true si las cajas se solapan más de tol en ambos ejes. F.9.</summary>
        public static bool Solapan(Caja a, Caja b, double tol)
        {
            double ox = Math.Min(a.X1, b.X1) - Math.Max(a.X0, b.X0);
            double oy = Math.Min(a.Y1, b.Y1) - Math.Max(a.Y0, b.Y0);
            return ox > tol && oy > tol;
        }

        /// <summary>Ids de cajas fuera de [margen, ancho−margen]×[margen, alto−margen] (±tol). F.9.</summary>
        public static List<string> FueraDeMarco(IReadOnlyList<Caja> c, double ancho, double alto, double margen = MARGEN_MARCO, double tol = TOL_SOLAPE)
        {
            return c.Where(k => k.X0 < margen - tol || k.X1 > ancho - margen + tol || k.Y0 < margen - tol || k.Y1 > alto - margen + tol)
                    .Select(k => k.Id).ToList();
        }

        private static bool CruzanSegmentos(double ax, double ay, double bx, double by, double cx, double cy, double dx, double dy, bool excluirExtremos)
        {
            double r1x = bx - ax, r1y = by - ay, r2x = dx - cx, r2y = dy - cy;
            double den = r1x * r2y - r1y * r2x;
            if (Math.Abs(den) < 1e-12) return false;
            double t = ((cx - ax) * r2y - (cy - ay) * r2x) / den;
            double u = ((cx - ax) * r1y - (cy - ay) * r1x) / den;
            double eps = excluirExtremos ? 1e-9 : -1e-9;
            return t > eps && t < 1 - eps && u > eps && u < 1 - eps;
        }

        /// <summary>Parejas de leaders que se cruzan ("idA|idB"), sin contar extremos compartidos. F.9.</summary>
        public static List<string> CrucesLeaders(IReadOnlyList<Leader> l)
        {
            var r = new List<string>();
            for (int i = 0; i < l.Count; i++)
                for (int j = i + 1; j < l.Count; j++)
                    if (CruzanSegmentos(l[i].X0, l[i].Y0, l[i].X1, l[i].Y1, l[j].X0, l[j].Y0, l[j].X1, l[j].Y1, true))
                        r.Add(l[i].Id + "|" + l[j].Id);
            return r;
        }

        /// <summary>Leaders que cortan una caja ajena reducida en TOL_SOLAPE ("leader|caja"). F.9.</summary>
        public static List<string> CortesLeaderCaja(IReadOnlyList<Leader> l, IReadOnlyList<Caja> c)
        {
            var r = new List<string>();
            foreach (var ld in l)
                foreach (var k in c)
                {
                    if (k.Id == ld.Id) continue;
                    double x0 = k.X0 + TOL_SOLAPE, x1 = k.X1 - TOL_SOLAPE, y0 = k.Y0 + TOL_SOLAPE, y1 = k.Y1 - TOL_SOLAPE;
                    if (x1 <= x0 || y1 <= y0) continue;
                    bool dentro(double x, double y) { return x > x0 && x < x1 && y > y0 && y < y1; }
                    bool corta = dentro(ld.X0, ld.Y0) || dentro(ld.X1, ld.Y1)
                        || CruzanSegmentos(ld.X0, ld.Y0, ld.X1, ld.Y1, x0, y0, x1, y0, false)
                        || CruzanSegmentos(ld.X0, ld.Y0, ld.X1, ld.Y1, x1, y0, x1, y1, false)
                        || CruzanSegmentos(ld.X0, ld.Y0, ld.X1, ld.Y1, x1, y1, x0, y1, false)
                        || CruzanSegmentos(ld.X0, ld.Y0, ld.X1, ld.Y1, x0, y1, x0, y0, false);
                    if (corta) r.Add(ld.Id + "|" + k.Id);
                }
            return r;
        }

        /// <summary>Ids de leaders con |dx|/max(dy,1e-6) &gt; max. F.9.</summary>
        public static List<string> PendientesExcedidas(IReadOnlyList<Leader> l, double max = PENDIENTE_LEADER_MAX)
        {
            return l.Where(k => Math.Abs(k.X1 - k.X0) / Math.Max(Math.Abs(k.Y1 - k.Y0), 1e-6) > max + 1e-9).Select(k => k.Id).ToList();
        }

        /// <summary>F.4-8: rellena las listas de verificación y SinSolapes.</summary>
        private static void Verificar(EntradaMaquetacion e, ResultadoMaquetacion r, double s)
        {
            var cajas = CajasFinales(e, r);
            var leaders = LeadersFinales(e, r);
            r.Solapes = Solapes(cajas);
            r.FueraDeMarco = FueraDeMarco(cajas, r.AnchoMarco, r.AltoMarco);
            r.CrucesLeaders = CrucesLeaders(leaders);
            var todas = new List<Caja>(cajas); todas.AddRange(CajasDeDibujo(e, r));
            r.CortesLeaderCaja = CortesLeaderCaja(leaders, todas);
            r.PendientesExcedidas = PendientesExcedidas(leaders);
            foreach (string c in r.CortesLeaderCaja) r.Avisos.Add("Leader corta " + c.Split('|')[1]);
            foreach (string p in r.PendientesExcedidas) r.Avisos.Add("Leader inclinado " + p);
            r.SinSolapes = r.Solapes.Count == 0 && r.FueraDeMarco.Count == 0 && r.CrucesLeaders.Count == 0;
        }

        // ------------------------------------------------------------ F.10

        private static double Mediana(List<double> v)
        {
            if (v.Count == 0) return double.NaN;
            var o = v.OrderBy(x => x).ToList();
            int n = o.Count;
            return n % 2 == 1 ? o[n / 2] : (o[n / 2 - 1] + o[n / 2]) / 2.0;
        }

        /// <summary>Razón medido/predicho r = mediana (1 con &lt;3 muestras) y dispersión relativa. F.10.</summary>
        public static double Calibrar(IReadOnlyList<double> medidos, IReadOnlyList<double> predichos, out double dispersion)
        {
            dispersion = 0;
            var ri = new List<double>();
            if (medidos != null && predichos != null)
                for (int i = 0; i < Math.Min(medidos.Count, predichos.Count); i++)
                    if (predichos[i] > 1e-9 && medidos[i] > 1e-9 && !double.IsNaN(medidos[i])) ri.Add(medidos[i] / predichos[i]);
            if (ri.Count < 3) return 1.0;
            double r = Mediana(ri);
            dispersion = Mediana(ri.Select(x => Math.Abs(x - r)).ToList()) / r;
            return r;
        }

        // -------------------------------------------------- [contrato] utilidades de coordenadas

        /// <summary>X (in) en el marco final de una estación: (est − StationStart)/s.</summary>
        public static double XMarco(double est, ResultadoMaquetacion r, double s) { return (est - r.StationStart) / s; }

        /// <summary>Y (in) en el marco final de una cota: (z − ElevationMin)/V.</summary>
        public static double YMarco(double z, ResultadoMaquetacion r) { return (z - r.ElevationMin) / r.V; }

        /// <summary>Cota (ft) de una Y del marco: ElevationMin + y·V (G.10-3).</summary>
        public static double ZDeY(double y, ResultadoMaquetacion r) { return r.ElevationMin + y * r.V; }

        /// <summary>Estación (ft) de una X del marco: StationStart + x·s.</summary>
        public static double EstDeX(double x, ResultadoMaquetacion r, double s) { return r.StationStart + x * s; }

        /// <summary>Predicción transversal para calibrar: h + (n−1)·PASO_LINEA (F.10).</summary>
        public static double PredichoTransversal(int lineas, double h = H_TEXTO) { return AnchoBloqueVertical(lineas, h); }
    }
}
