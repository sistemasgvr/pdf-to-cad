using System;
using System.Collections.Generic;

// ============================================================================
//  Altura del buzón (tapa − fondo) dentro del rango de la pieza — núcleo PURO
//  (sin Autodesk; lo usa ImportarRed.cs y lo prueba PerfilPruebas).
//
//  Civil 3D comprueba el rango «Rim to Sump Height» de la pieza en CADA escritura
//  de RimElevation o SumpElevation: si la altura de ese momento se sale, la cambia
//  sola y avisa en el Event Viewer («exceeded the allowed 'Rim to Sump Height'
//  range… closest height used»; reporte del usuario 2026-11-13, Structure - (6) y
//  (8), aunque la altura final pedida estaba dentro del rango). Por eso no basta con
//  que la altura FINAL sea válida: también la intermedia, entre escribir la tapa y
//  escribir el fondo. `Pasos` da el orden (y, si hace falta, pasos intermedios) para
//  que ninguna altura intermedia se salga.
// ============================================================================

namespace Civil3DBasico
{
    public static class AlturaBuzonNucleo
    {
        public const double TOL = 1e-4;
        const int MAX_PASOS = 60;

        /// <summary>Escrituras (esTapa, valor) para ir de (rim0, sump0) a (rim, sump) sin que la altura
        /// intermedia salga de [min, max]. Sin rango conocido se usa el intervalo entre la altura actual y la
        /// pedida (las dos valen para Civil 3D: la actual porque la tiene, la pedida porque se ajustó antes).
        /// Si no hay forma (sin holgura y hay que trasladar), devuelve el orden de siempre: tapa y fondo.</summary>
        public static List<(bool tapa, double valor)> Pasos(double rim0, double sump0, double rim, double sump,
                                                             double? min = null, double? max = null)
        {
            double h0 = rim0 - sump0, h1 = rim - sump;
            double lo = min ?? Math.Min(h0, h1), hi = max ?? Math.Max(h0, h1);
            bool Vale(double h) => h >= lo - TOL && h <= hi + TOL;
            var pasos = new List<(bool, double)>();
            if (Math.Abs(rim - rim0) <= TOL && Math.Abs(sump - sump0) <= TOL) return pasos;
            if (Vale(rim - sump0)) { pasos.Add((true, rim)); pasos.Add((false, sump)); return pasos; }
            if (Vale(rim0 - sump)) { pasos.Add((false, sump)); pasos.Add((true, rim)); return pasos; }
            // Trasladar con pasos cortos: cada escritura lleva la cota lo más cerca posible de su destino sin salir
            // del rango (con holgura hi − lo; sin holgura no se avanza).
            double r = rim0, s = sump0;
            if (hi - lo > TOL && Vale(h0))
            {
                for (int i = 0; i < MAX_PASOS; i++)
                {
                    double rn = Math.Min(Math.Max(rim, s + lo), s + hi);
                    if (Math.Abs(rn - r) > TOL) { pasos.Add((true, rn)); r = rn; }
                    double sn = Math.Min(Math.Max(sump, r - hi), r - lo);
                    if (Math.Abs(sn - s) > TOL) { pasos.Add((false, sn)); s = sn; }
                    if (Math.Abs(r - rim) <= TOL && Math.Abs(s - sump) <= TOL) return pasos;
                }
            }
            return new List<(bool, double)> { (true, rim), (false, sump) };
        }

        /// <summary>Factor para pasar el rango del catálogo a pies, o null si no se sabe. `valorCampo` es el valor
        /// del campo «Rim to Sump Height» de la pieza y `alturaActual` (pies) la de la estructura: si coinciden ×1 son
        /// pies, ×12 pulgadas. Si no coinciden (p. ej. el campo aún no refleja la altura), manda la unidad escrita
        /// del campo («in», «inch», «ft», «foot»).</summary>
        public static double? FactorUnidades(double? valorCampo, double alturaActual, string unidades)
        {
            if (valorCampo.HasValue && valorCampo.Value > 0 && alturaActual > 1e-6)
            {
                double r = valorCampo.Value / alturaActual;
                if (Math.Abs(r - 12.0) < 0.6) return 1.0 / 12.0;
                if (Math.Abs(r - 1.0) <= 0.05) return 1.0;
            }
            string u = (unidades ?? "").Trim().ToLowerInvariant();
            if (u.Length == 0) return null;
            if (u.Contains("inch") || u == "in" || u.EndsWith("_in") || u.Contains("pulg")) return 1.0 / 12.0;
            if (u.Contains("foot") || u.Contains("feet") || u == "ft" || u.EndsWith("_ft") || u.Contains("pie")) return 1.0;
            return null;
        }
    }
}
