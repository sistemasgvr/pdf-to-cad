using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  Receta de la válvula de compuerta (2026-11-05) — PURA (sin Autodesk).
//   · ESPEJO de app/nucleo/valvula_receta.py: las mismas constantes, la misma tabla y las mismas piezas; así la
//     Vista 3D de la app y Civil 3D dibujan lo mismo (tests/test_valvulas.py::test_espejo_de_la_receta_en_el_plugin
//     compara constantes y tabla). Cambiar una sin la otra rompe esa prueba.
//   · Es la forma de los bloques del catálogo del plugin de válvulas del equipo (Valvulas_AWWA_3D.dwg, 3"–54"),
//     medida y escrita como fórmulas del diámetro N: sirve para CUALQUIER N de N_MIN a N_MAX. Un N fuera de la
//     tabla de normas se interpola (o se prolonga desde los extremos) y queda «estimado».
//   · Pulgadas. Origen = centro de la válvula sobre el eje de la tubería, X = eje, Z = vástago, Y = hacia el
//     volante. Capa 0 = cuerpo (V-PRES-VALV-DIA), 1 = vástago y tuerca (V-PRES-VALV-INT).
// ============================================================================

namespace Civil3DBasico
{
    internal enum PiezaValvulaTipo { Tubo, Brida, Caja, Cil, Toro }

    internal sealed class PiezaValvula
    {
        public PiezaValvulaTipo Tipo;
        public int Capa;
        // Tubo / Brida: X0, X1 a lo largo de X, R exterior, Ri interior; Brida además RPernos, NPernos, RAgujero.
        public double X0, X1, R, Ri, RPernos, RAgujero;
        public int NPernos;
        // Caja: Min / Max. Cil: Eje ('x'|'y'|'z'), Inicio, Largo, R. Toro: Centro, R (aro), Rt (tubo), eje Y.
        public double[] Min, Max, Inicio, Centro;
        public char Eje;
        public double Largo, Rt;
    }

    internal sealed class RecetaValvula
    {
        public double N;
        public string Tipo;          // FLG | RG | GEAR
        public string Bloque;        // VALV_8_FLG, VALV_24_FLG_GEAR…
        public double Largo;         // pulgadas, a lo largo del eje
        public double OdExtremo;     // pulgadas
        public bool Estimada;
        public List<PiezaValvula> Piezas = new List<PiezaValvula>();
    }

    internal static class ValvulaReceta
    {
        // N, OD brida, espesor brida, círculo de pernos, nº pernos, agujero, cara a cara FLG, OD tubo
        // (ASME B16.1 cl.125 / AWWA C207, AWWA C509/C515, AWWA C151) = CatalogoValvulas.T del plugin de válvulas.
        private static readonly double[][] TABLA =
        {
            new double[] { 3, 7.5, 0.75, 6.0, 4, 0.75, 8.0, 3.96 },
            new double[] { 4, 9.0, 0.94, 7.5, 8, 0.75, 9.0, 4.80 },
            new double[] { 6, 11.0, 1.0, 9.5, 8, 0.875, 10.0, 6.90 },
            new double[] { 8, 13.5, 1.12, 11.75, 8, 0.875, 11.5, 9.05 },
            new double[] { 10, 16.0, 1.19, 14.25, 12, 1.0, 13.0, 11.10 },
            new double[] { 12, 19.0, 1.25, 17.0, 12, 1.0, 14.0, 13.20 },
            new double[] { 14, 21.0, 1.38, 18.75, 12, 1.125, 15.0, 15.30 },
            new double[] { 16, 23.5, 1.44, 21.25, 16, 1.125, 16.0, 17.40 },
            new double[] { 18, 25.0, 1.56, 22.75, 16, 1.25, 17.0, 19.50 },
            new double[] { 20, 27.5, 1.69, 25.0, 20, 1.25, 18.0, 21.60 },
            new double[] { 24, 32.0, 1.88, 29.5, 20, 1.375, 20.0, 25.80 },
            new double[] { 30, 38.75, 2.12, 36.0, 28, 1.375, 24.0, 32.00 },
            new double[] { 36, 46.0, 2.38, 42.75, 32, 1.625, 28.0, 38.30 },
            new double[] { 42, 53.0, 2.62, 49.5, 36, 1.625, 32.0, 44.50 },
            new double[] { 48, 59.5, 2.75, 56.0, 44, 1.625, 36.0, 50.80 },
            new double[] { 54, 66.25, 3.0, 62.75, 44, 2.0, 40.0, 57.10 },
        };

        internal const double N_MIN = 3.0, N_MAX = 72.0;
        internal const double RG_MAX_IN = 16.0;
        internal const double ENGRANES_MIN_IN = 18.0;
        internal const double CUERPO_K = 0.54, CUERPO_B = 0.9;
        internal const double CAMPANA_SOBRE_TUBO = 1.35;
        internal const double ARO_SOBRE_CAMPANA = 0.6;
        internal const double CAMPANA_LARGO = 2.5, ARO_LARGO = 1.0;
        internal const double RG_EXTRA = 3.0, RG_K = 0.17;
        internal const double CAJA_X_K = 0.275, CAJA_X_MIN = 2.3;
        internal const double CAJA_Y_K = 0.52, CAJA_Y_B = 1.2;
        internal const double TAPA_Z_K = 1.55, TAPA_Z_B = 2.1;
        internal const double TAPA_E_B = 1.0, TAPA_E_K = 0.03;
        internal const double TAPA_X_SOBRE = 0.6, TAPA_Y_K = 0.52, TAPA_Y_B = 1.9;
        internal const double YUGO_TOPE_K = 1.98, YUGO_TOPE_B = 6.3;
        internal const double YUGO_R_K = 0.205, YUGO_R_B = 0.34, YUGO_R_K2 = 0.1, YUGO_R_B2 = 0.9;
        internal const double VASTAGO_R_K = 0.1, VASTAGO_R_B = 0.45;
        internal const double VASTAGO_Z0_B = 0.5;
        internal const double VASTAGO_TOPE_B = 7.9;
        internal const double TUERCA_LADO = 2.0, TUERCA_ALTO = 1.75, TUERCA_SOBRE = 0.275;
        internal const double EJE_GEAR_R_K = 0.1, EJE_GEAR_R_B = 0.55;
        internal const double ENGR_X_K = 0.175, ENGR_X_B = 3.0;
        internal const double ENGR_Z_K = 1.98, ENGR_Z_B = 5.3;
        internal const double ENGR_H_K = 0.3, ENGR_H_B = 4.0;
        internal const double VOL_Y_K = 0.375, VOL_Y_B = 7.0;
        internal const double VOL_R_K = 0.25, VOL_R_B = 8.0;
        internal const double VOL_T_K = 0.015, VOL_T_B = 0.7;
        internal const double VOL_CUBO_K = 0.05, VOL_CUBO_B = 2.0, VOL_CUBO_L = 3.0;
        internal const double VOL_EJE_K = 0.03, VOL_EJE_B = 1.0;
        internal const double VOL_RAYO_K = 0.012, VOL_RAYO_B = 0.565;

        /// <summary>Medidas de norma para N: la fila de la tabla o la recta entre las dos vecinas (fuera del rango, la
        /// de los dos extremos). Nº de pernos: múltiplo de 4.</summary>
        private static double[] Interpolar(double n, out bool estimada)
        {
            foreach (var f in TABLA)
                if (f[0] == n) { estimada = false; return f; }
            estimada = true;
            double[] a, b;
            if (n < TABLA[0][0]) { a = TABLA[0]; b = TABLA[1]; }
            else if (n > TABLA[TABLA.Length - 1][0]) { a = TABLA[TABLA.Length - 2]; b = TABLA[TABLA.Length - 1]; }
            else
            {
                a = TABLA.Last(f => f[0] < n);
                b = TABLA.First(f => f[0] > n);
            }
            double t = (n - a[0]) / (b[0] - a[0]);
            var r = new double[8];
            for (int k = 0; k < 8; k++) r[k] = a[k] + (b[k] - a[k]) * t;
            r[4] = Math.Max(4, Math.Round(r[4] / 4.0, MidpointRounding.ToEven) * 4);
            return r;
        }

        internal static string TipoDe(double n, string union)
        {
            if (n >= ENGRANES_MIN_IN) return "GEAR";
            return union == "RG" && n <= RG_MAX_IN ? "RG" : "FLG";
        }

        internal static string Nombre(double n, string tipo)
        {
            string s = n.ToString("0.##", CultureInfo.InvariantCulture);
            return tipo == "GEAR" ? $"VALV_{s}_FLG_GEAR" : $"VALV_{s}_{tipo}";
        }

        private static PiezaValvula Tubo(int capa, double x0, double x1, double r, double ri)
            => new PiezaValvula { Tipo = PiezaValvulaTipo.Tubo, Capa = capa, X0 = x0, X1 = x1, R = r, Ri = ri };

        private static PiezaValvula Caja(int capa, double x0, double y0, double z0, double x1, double y1, double z1)
            => new PiezaValvula { Tipo = PiezaValvulaTipo.Caja, Capa = capa, Min = new[] { x0, y0, z0 }, Max = new[] { x1, y1, z1 } };

        private static PiezaValvula Cil(int capa, char eje, double x, double y, double z, double largo, double r)
            => new PiezaValvula { Tipo = PiezaValvulaTipo.Cil, Capa = capa, Eje = eje, Inicio = new[] { x, y, z }, Largo = largo, R = r };

        /// <summary>Receta de la válvula de n pulgadas (las mismas piezas, en el mismo orden, que valvula_receta.receta).</summary>
        internal static RecetaValvula Receta(double n, string union)
        {
            double[] f = Interpolar(n, out bool estimada);
            double odB = f[1], esp = f[2], bc = f[3], agujero = f[5], cc = f[6], odTubo = f[7];
            int pernos = (int)f[4];
            string t = TipoDe(n, union);
            double L = t == "RG" ? cc + RG_EXTRA + RG_K * n : cc;
            double h = L / 2.0, rc = CUERPO_K * n + CUERPO_B, ri = n / 2.0;
            var rec = new RecetaValvula { N = n, Tipo = t, Bloque = Nombre(n, t), Largo = L, Estimada = estimada };
            var p = rec.Piezas;
            if (t == "RG")
            {
                double rCamp = odTubo / 2.0 + CAMPANA_SOBRE_TUBO, rAro = rCamp + ARO_SOBRE_CAMPANA;
                double xc = h - ARO_LARGO - CAMPANA_LARGO;
                p.Add(Tubo(0, -xc, xc, rc, ri));
                foreach (int s in new[] { -1, 1 })
                {
                    double a = s * xc, b = s * (h - ARO_LARGO);
                    p.Add(Tubo(0, Math.Min(a, b), Math.Max(a, b), rCamp, ri));
                    a = s * (h - ARO_LARGO); b = s * h;
                    p.Add(Tubo(0, Math.Min(a, b), Math.Max(a, b), rAro, ri));
                }
                rec.OdExtremo = 2 * rAro;
            }
            else
            {
                p.Add(Tubo(0, -(h - esp), h - esp, rc, ri));
                foreach (int s in new[] { -1, 1 })
                {
                    double a = s * (h - esp), b = s * h;
                    p.Add(new PiezaValvula
                    {
                        Tipo = PiezaValvulaTipo.Brida, Capa = 0, X0 = Math.Min(a, b), X1 = Math.Max(a, b),
                        R = odB / 2.0, Ri = ri, RPernos = bc / 2.0, NPernos = pernos, RAgujero = agujero / 2.0,
                    });
                }
                rec.OdExtremo = odB;
            }
            double bx = Math.Max(CAJA_X_K * L, CAJA_X_MIN), by = CAJA_Y_K * n + CAJA_Y_B;
            double z0 = TAPA_Z_K * n + TAPA_Z_B, z1 = z0 + TAPA_E_B + TAPA_E_K * n;
            p.Add(Caja(0, -bx, -by, 0.0, bx, by, z0));
            double cx = bx + TAPA_X_SOBRE, cy = TAPA_Y_K * n + TAPA_Y_B;
            p.Add(Caja(0, -cx, -cy, z0, cx, cy, z1));
            double rv = VASTAGO_R_K * n + VASTAGO_R_B, zv0 = n + VASTAGO_Z0_B;
            if (t == "GEAR")
            {
                double g0 = ENGR_Z_K * n + ENGR_Z_B, g1 = g0 + ENGR_H_K * n + ENGR_H_B, gx = ENGR_X_K * n + ENGR_X_B;
                p.Add(Cil(0, 'z', 0, 0, z1, g0 - z1, EJE_GEAR_R_K * n + EJE_GEAR_R_B));
                p.Add(Caja(0, -gx, -gx, g0, gx, gx, g1));
                double zg = (g0 + g1) / 2.0, yv = VOL_Y_K * n + VOL_Y_B;
                double cuboR = VOL_CUBO_K * n + VOL_CUBO_B, yCubo = yv - VOL_CUBO_L / 2.0;
                p.Add(Cil(0, 'y', 0, gx, zg, yCubo - gx, VOL_EJE_K * n + VOL_EJE_B));
                p.Add(Cil(0, 'y', 0, yCubo, zg, VOL_CUBO_L, cuboR));
                double R = VOL_R_K * n + VOL_R_B;
                p.Add(new PiezaValvula { Tipo = PiezaValvulaTipo.Toro, Capa = 0, Centro = new[] { 0.0, yv, zg }, R = R, Rt = VOL_T_K * n + VOL_T_B });
                double rr = VOL_RAYO_K * n + VOL_RAYO_B;
                p.Add(Cil(0, 'x', 0, yv, zg, R, rr));
                p.Add(Cil(0, 'x', -R, yv, zg, R, rr));
                p.Add(Cil(0, 'z', 0, yv, zg, R, rr));
                p.Add(Cil(0, 'z', 0, yv, zg - R, R, rr));
                p.Add(Cil(1, 'z', 0, 0, zv0, g0 - zv0, rv));
            }
            else
            {
                double zy = YUGO_TOPE_K * n + YUGO_TOPE_B;
                double ry = Math.Max(YUGO_R_K * n + YUGO_R_B, YUGO_R_K2 * n + YUGO_R_B2);
                p.Add(Cil(0, 'z', 0, 0, z1, zy - z1, ry));
                double zt = YUGO_TOPE_K * n + VASTAGO_TOPE_B;
                p.Add(Cil(1, 'z', 0, 0, zv0, zt - zv0, rv));
                double a = TUERCA_LADO / 2.0;
                p.Add(Caja(1, -a, -a, zt + TUERCA_SOBRE - TUERCA_ALTO, a, a, zt + TUERCA_SOBRE));
            }
            return rec;
        }
    }
}
