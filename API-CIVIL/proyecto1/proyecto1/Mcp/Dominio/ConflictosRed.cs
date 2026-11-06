using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  DOMINIO: CONFLICTOS entre tuberías del dibujo de Civil 3D (PURO). Un conflicto
//  = dos tuberías que se cruzan en planta y, en el cruce, sus paredes se tocan
//  («choque»), quedan más cerca que la separación vertical de la normativa
//  («separacion») o van en el orden contrario al que pide («orden»).
//
//  Las separaciones NO las inventa el plugin: llegan como ReglaSeparacion (la app
//  las saca de sus normativas y se las pasa; sin reglas solo se buscan choques).
//  Cotas: la rasante (solera) de cada extremo; el eje = solera + diámetro/2; la
//  pared exterior se toma a diámetro/2 del eje (sin espesor: no se conoce).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class ReglaSeparacion
    {
        public const string CUALQUIERA = "*";
        public string A, B;          // capas de utilidad (AGUA, ELECTRICO…); B = «*» = con cualquiera
        public double SepVFt;        // separación vertical mínima libre entre paredes (ft)
        public string Encima;        // capa que debe ir ARRIBA (null = cualquiera)
        public string Debajo;        // capa que debe ir ABAJO (la normativa «por debajo de»; sirve con «*»)
        public string Fuente;

        public bool Aplica(string ca, string cb) =>
            (Calculos.Igual(A, ca) && (B == CUALQUIERA || Calculos.Igual(B, cb))) ||
            (Calculos.Igual(A, cb) && (B == CUALQUIERA || Calculos.Igual(B, ca)));
    }

    public sealed class ConflictoRed
    {
        public string Id;                  // K1, K2… en orden de lectura (de arriba abajo, de izquierda a derecha)
        public Tuberia A, B;
        public double X, Y;
        public double EjeA, EjeB;          // cota del eje de cada una en el cruce (ft)
        public double LibreFt;             // entre paredes (negativo = se meten una en la otra)
        public double RequeridoFt;
        public string Encima;              // capa que debe ir arriba según la normativa (o null)
        public string Fuente;
        public string Tipo;                // choque | separacion | orden

        public string Clave() => Par(A.Handle, B.Handle);

        public static string Par(string a, string b) =>
            string.CompareOrdinal(a, b) <= 0 ? a + "|" + b : b + "|" + a;
    }

    public static class Conflictos
    {
        public const double TOL_UNION_FT = 0.5;     // puntas a menos de esto = unidas
        public const double TOL_FT = 0.005;
        public const string CHOQUE = "choque", SEPARACION = "separacion", ORDEN = "orden";

        /// <summary>Radio exterior aproximado (ft).</summary>
        public static double Radio(Tuberia t) => Math.Max(t.DiametroIn, 0.0) / 24.0;

        /// <summary>Cota del eje en la fracción s (0 = inicio, 1 = fin) del tramo, + `dz` si se movió.</summary>
        public static double? EjeEn(Tuberia t, double s, double dz = 0.0)
        {
            if (!t.CotaIni.HasValue || !t.CotaFin.HasValue) return null;
            return t.CotaIni.Value + (t.CotaFin.Value - t.CotaIni.Value) * s + Radio(t) + dz;
        }

        /// <summary>Todos los conflictos del modelo, numerados K1… `sinCota` = cruces que no se pueden medir.</summary>
        public static List<ConflictoRed> Buscar(Modelo m, IList<ReglaSeparacion> reglas, out int sinCota)
        {
            var r = Entre(m.Tuberias, m.Tuberias, reglas, null, out sinCota);
            r.Sort((p, q) =>
            {
                int c = Math.Round(q.Y).CompareTo(Math.Round(p.Y));
                return c != 0 ? c : p.X.CompareTo(q.X);
            });
            for (int i = 0; i < r.Count; i++) r[i].Id = "K" + (i + 1);
            return r;
        }

        /// <summary>Conflictos entre las tuberías de `primeras` y las de `segundas` (sin repetir pares).
        /// `dz` = desplazamiento vertical de algunas (handle → ft), para probar una solución.</summary>
        public static List<ConflictoRed> Entre(IList<Tuberia> primeras, IList<Tuberia> segundas,
                                               IList<ReglaSeparacion> reglas, IDictionary<string, double> dz,
                                               out int sinCota)
        {
            sinCota = 0;
            var res = new List<ConflictoRed>();
            var vistos = new HashSet<string>();
            var cajas = segundas.Select(Caja).ToArray();
            foreach (Tuberia a in primeras)
            {
                var ca = Caja(a);
                for (int j = 0; j < segundas.Count; j++)
                {
                    Tuberia b = segundas[j];
                    if (ReferenceEquals(a, b) || a.Handle == b.Handle) continue;
                    var cb = cajas[j];
                    if (ca.x1 < cb.x0 - TOL_FT || cb.x1 < ca.x0 - TOL_FT || ca.y1 < cb.y0 - TOL_FT || cb.y1 < ca.y0 - TOL_FT)
                        continue;
                    if (!vistos.Add(ConflictoRed.Par(a.Handle, b.Handle))) continue;
                    if (Unidas(a, b)) continue;
                    if (!Cruce(a, b, out double x, out double y, out double sa, out double sb)) continue;
                    double da = 0, db = 0;
                    if (dz != null) { dz.TryGetValue(a.Handle, out da); dz.TryGetValue(b.Handle, out db); }
                    ConflictoRed c = Medir(a, b, x, y, sa, sb, da, db, reglas, out bool medible);
                    if (!medible) { sinCota++; continue; }
                    if (c != null) res.Add(c);
                }
            }
            return res;
        }

        /// <summary>Mide un cruce. Devuelve el conflicto, o null si cumple.</summary>
        public static ConflictoRed Medir(Tuberia a, Tuberia b, double x, double y, double sa, double sb,
                                         double dza, double dzb, IList<ReglaSeparacion> reglas, out bool medible)
        {
            double? ea = EjeEn(a, sa, dza), eb = EjeEn(b, sb, dzb);
            medible = ea.HasValue && eb.HasValue;
            if (!medible) return null;
            double libre = Math.Abs(ea.Value - eb.Value) - Radio(a) - Radio(b);
            double req = 0.0; string encima = null; var fuentes = new List<string>();
            foreach (var r in reglas ?? Array.Empty<ReglaSeparacion>())
            {
                if (r == null || !r.Aplica(a.Capa, b.Capa)) continue;
                if (r.SepVFt > req) req = r.SepVFt;
                if (encima == null && !Calculos.Igual(a.Capa, b.Capa))
                {
                    if (!string.IsNullOrEmpty(r.Encima) && (Calculos.Igual(r.Encima, a.Capa) || Calculos.Igual(r.Encima, b.Capa)))
                        encima = Calculos.Igual(r.Encima, a.Capa) ? a.Capa : b.Capa;
                    else if (!string.IsNullOrEmpty(r.Debajo) && (Calculos.Igual(r.Debajo, a.Capa) || Calculos.Igual(r.Debajo, b.Capa)))
                        encima = Calculos.Igual(r.Debajo, a.Capa) ? b.Capa : a.Capa;
                }
                if (!string.IsNullOrEmpty(r.Fuente) && !fuentes.Contains(r.Fuente)) fuentes.Add(r.Fuente);
            }
            string tipo = null;
            if (libre < -TOL_FT) tipo = CHOQUE;
            else if (libre < req - TOL_FT) tipo = SEPARACION;
            else if (encima != null)
            {
                bool aArriba = ea.Value > eb.Value;
                bool debeA = Calculos.Igual(encima, a.Capa);
                if (aArriba != debeA) tipo = ORDEN;
            }
            if (tipo == null) return null;
            return new ConflictoRed
            {
                A = a, B = b, X = x, Y = y, EjeA = ea.Value, EjeB = eb.Value, LibreFt = libre, RequeridoFt = req,
                Encima = encima, Fuente = string.Join("; ", fuentes), Tipo = tipo,
            };
        }

        /// <summary>Misma red y una punta sobre la otra tubería (unión, T) o la misma utilidad de la app.</summary>
        public static bool Unidas(Tuberia a, Tuberia b)
        {
            if (!Calculos.Igual(a.Red, b.Red)) return false;
            if (!string.IsNullOrEmpty(a.UtilidadNumero) && a.UtilidadNumero == b.UtilidadNumero &&
                Calculos.Igual(a.UtilidadCapa, b.UtilidadCapa)) return true;
            foreach (var (px, py) in new[] { (a.XIni, a.YIni), (a.XFin, a.YFin) })
                if (DistSeg(px, py, b) <= TOL_UNION_FT) return true;
            foreach (var (px, py) in new[] { (b.XIni, b.YIni), (b.XFin, b.YFin) })
                if (DistSeg(px, py, a) <= TOL_UNION_FT) return true;
            return false;
        }

        /// <summary>Cruce de los dos tramos en planta (incluye tocar con la punta). s = fracción en cada tramo.</summary>
        public static bool Cruce(Tuberia a, Tuberia b, out double x, out double y, out double sa, out double sb)
        {
            x = y = sa = sb = 0;
            double rx = a.XFin - a.XIni, ry = a.YFin - a.YIni, qx = b.XFin - b.XIni, qy = b.YFin - b.YIni;
            double den = rx * qy - ry * qx;
            double la = Math.Sqrt(rx * rx + ry * ry), lb = Math.Sqrt(qx * qx + qy * qy);
            if (la < 1e-9 || lb < 1e-9 || Math.Abs(den) < 1e-9 * la * lb) return false;   // paralelas
            double wx = b.XIni - a.XIni, wy = b.YIni - a.YIni;
            sa = (wx * qy - wy * qx) / den;
            sb = (wx * ry - wy * rx) / den;
            double ea = TOL_FT / la, eb = TOL_FT / lb;
            if (sa < -ea || sa > 1 + ea || sb < -eb || sb > 1 + eb) return false;
            sa = Math.Max(0, Math.Min(1, sa)); sb = Math.Max(0, Math.Min(1, sb));
            x = a.XIni + rx * sa; y = a.YIni + ry * sa;
            return true;
        }

        public static double DistSeg(double px, double py, Tuberia t)
        {
            double rx = t.XFin - t.XIni, ry = t.YFin - t.YIni, l2 = rx * rx + ry * ry;
            double s = l2 < 1e-12 ? 0 : Math.Max(0, Math.Min(1, ((px - t.XIni) * rx + (py - t.YIni) * ry) / l2));
            double dx = t.XIni + rx * s - px, dy = t.YIni + ry * s - py;
            return Math.Sqrt(dx * dx + dy * dy);
        }

        private static (double x0, double y0, double x1, double y1) Caja(Tuberia t) =>
            (Math.Min(t.XIni, t.XFin), Math.Min(t.YIni, t.YFin), Math.Max(t.XIni, t.XFin), Math.Max(t.YIni, t.YFin));

        public static string F(double v) => Math.Round(v, 2).ToString("0.00", CultureInfo.InvariantCulture);
    }
}
