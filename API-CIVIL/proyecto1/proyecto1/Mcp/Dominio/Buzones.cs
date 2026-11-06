using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: buzones / cajas de gravedad (PURO). Revisar (tuberías bajo el fondo,
//  corona sobre la tapa, tapa bajo el fondo) y proponer tapa, fondo o altura.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class AvisoBuzon
    {
        public Estructura Estructura;
        public Tuberia Tuberia;          // null = es del buzón mismo
        public string Tipo;              // bajo_fondo | sobre_tapa | tapa_bajo_fondo | sin_cotas
        public string Texto;
        public double DiferenciaFt;
    }

    public static class Buzones
    {
        /// <summary>Las tuberías que llegan a la estructura y su rasante en esa punta.</summary>
        public static IEnumerable<(Tuberia t, double? z)> Llegadas(Modelo m, Estructura e) =>
            m.Tuberias.Where(t => Calculos.Igual(t.EstructuraIni, e.Handle)).Select(t => (t, t.CotaIni))
             .Concat(m.Tuberias.Where(t => Calculos.Igual(t.EstructuraFin, e.Handle)).Select(t => (t, t.CotaFin)));

        public static List<AvisoBuzon> Revisar(Modelo m, string red = null) => Revisar(m, m.Estructuras.Where(e =>
            !e.Nula && (string.IsNullOrWhiteSpace(red) || Calculos.Igual(e.Red, red))), null, null);

        /// <summary>Avisos de las estructuras `es` (con `rim`/`sump` nuevos si se pasan, para una propuesta).</summary>
        public static List<AvisoBuzon> Revisar(Modelo m, IEnumerable<Estructura> es, double? rimNuevo, double? sumpNuevo)
        {
            var r = new List<AvisoBuzon>();
            foreach (Estructura e in es)
            {
                double? rim = rimNuevo ?? e.Rim, sump = sumpNuevo ?? e.Sump;
                if (!rim.HasValue || !sump.HasValue)
                { r.Add(new AvisoBuzon { Estructura = e, Tipo = "sin_cotas", Texto = $"{e.Nombre} no tiene tapa o fondo." }); continue; }
                if (rim.Value <= sump.Value)
                    r.Add(new AvisoBuzon { Estructura = e, Tipo = "tapa_bajo_fondo", DiferenciaFt = sump.Value - rim.Value,
                                           Texto = $"La tapa de {e.Nombre} ({ReglasCambio.F(rim.Value)}) no está sobre su fondo ({ReglasCambio.F(sump.Value)})." });
                foreach (var (t, z) in Llegadas(m, e))
                {
                    if (!z.HasValue) continue;
                    if (z.Value < sump.Value - 1e-6)
                        r.Add(new AvisoBuzon { Estructura = e, Tuberia = t, Tipo = "bajo_fondo", DiferenciaFt = sump.Value - z.Value,
                                               Texto = $"{t.Nombre} llega {ReglasCambio.F(sump.Value - z.Value)} ft bajo el fondo de {e.Nombre}." });
                    double corona = z.Value + t.DiametroIn / 12.0;
                    if (corona > rim.Value + 1e-6)
                        r.Add(new AvisoBuzon { Estructura = e, Tuberia = t, Tipo = "sobre_tapa", DiferenciaFt = corona - rim.Value,
                                               Texto = $"La corona de {t.Nombre} queda {ReglasCambio.F(corona - rim.Value)} ft sobre la tapa de {e.Nombre}." });
                }
            }
            return r;
        }

        /// <summary>Tapa (`rim`), fondo (`sump`) o altura (fondo = tapa − altura). Cada uno: valor o null = no cambia.</summary>
        public static CambioBuzon Proponer(Modelo m, Estructura e, double? rim, double? sump, double? altura, out string error)
        {
            error = null;
            if (e.Nula) { error = $"{e.Nombre} es una estructura nula (un vértice de conducto): no tiene tapa ni fondo."; return null; }
            double? r = rim ?? e.Rim, s = sump ?? e.Sump;
            if (altura.HasValue)
            {
                if (altura.Value <= 0) { error = "La altura tiene que ser mayor que 0."; return null; }
                if (!r.HasValue) { error = $"{e.Nombre} no tiene tapa: dime la tapa o el fondo."; return null; }
                s = r.Value - altura.Value;
            }
            if (!rim.HasValue && !sump.HasValue && !altura.HasValue) { error = "Dime la tapa, el fondo o la altura."; return null; }
            foreach (double? z in new[] { r, s })
                if (z.HasValue && (z.Value < ReglasCambio.COTA_MIN_FT || z.Value > ReglasCambio.COTA_MAX_FT))
                { error = $"Cota fuera de rango: {z.Value}."; return null; }
            if (r.HasValue && s.HasValue && r.Value <= s.Value) { error = "La tapa tiene que quedar sobre el fondo."; return null; }

            string Txt(double? a, double? b) => $"tapa {(a.HasValue ? ReglasCambio.F(a.Value) : "—")} · fondo {(b.HasValue ? ReglasCambio.F(b.Value) : "—")}";
            var cp = new CambioBuzon
            {
                Tipo = TiposCambio.BUZON, Handle = e.Handle, Elemento = e.Nombre,
                Rim = Cambia(r, e.Rim), Sump = Cambia(s, e.Sump), Antes = Txt(e.Rim, e.Sump), Despues = Txt(r, s),
            };
            if (cp.Rim == null && cp.Sump == null) { error = $"{e.Nombre} ya tiene esa tapa y ese fondo."; return null; }
            if (r.HasValue && s.HasValue)
                cp.Consecuencias.Add($"Altura {(e.Profundidad().HasValue ? ReglasCambio.F(e.Profundidad().Value) : "—")} → {ReglasCambio.F(r.Value - s.Value)} ft.");
            int n = Llegadas(m, e).Count();
            if (n > 0) cp.Consecuencias.Add($"Las {n} tubería(s) que llegan no cambian.");
            foreach (var a in Revisar(m, new[] { e }, r, s)) cp.Advertencias.Add(a.Texto);
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        private static double? Cambia(double? nuevo, double? viejo) =>
            nuevo.HasValue && (!viejo.HasValue || Math.Abs(nuevo.Value - viejo.Value) > 1e-6) ? nuevo : null;
    }
}
