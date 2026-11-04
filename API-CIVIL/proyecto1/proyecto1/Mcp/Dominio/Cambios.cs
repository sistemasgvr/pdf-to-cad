using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  DOMINIO: cambios que la IA puede PROPONER (lista cerrada) y sus reglas. La
//  validación y las consecuencias las calcula la app, nunca la IA. Un cambio solo
//  se aplica con confirmar_cambio (lo decide el usuario).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public static class TiposCambio
    {
        public const string COTA_INICIO = "cota_inicio";
        public const string COTA_FIN = "cota_fin";
        public const string CAPA = "capa";
        public const string DESCRIPCION = "descripcion";

        public static readonly string[] Todos = { COTA_INICIO, COTA_FIN, CAPA, DESCRIPCION };
    }

    public sealed class CambioPropuesto
    {
        public string Id;
        public string Handle;
        public string Elemento;         // nombre legible
        public string Tipo;
        public string Antes;
        public string Despues;
        public string Motivo;
        public List<string> Consecuencias = new List<string>();
        public List<string> Advertencias = new List<string>();
        public DateTime Creado;
        public string Origen;
        public string Usuario;
    }

    public sealed class RegistroCambio
    {
        public string Fecha;
        public string Origen;
        public string Usuario;
        public string Handle;
        public string Elemento;
        public string Tipo;
        public string Antes;
        public string Despues;
        public string Motivo;
    }

    public static class ReglasCambio
    {
        /// <summary>Cota razonable en pies (evita que un error de la IA ponga 1e6).</summary>
        public const double COTA_MIN_FT = -1000.0, COTA_MAX_FT = 30000.0;
        public const int TEXTO_MAX = 250;

        /// <summary>Valida y arma el cambio. Devuelve null y `error` si no se puede.</summary>
        public static CambioPropuesto Preparar(Modelo m, string handle, string tipo, string valor,
                                               Func<string, bool> capaExiste, out string error)
        {
            error = null;
            tipo = (tipo ?? "").Trim().ToLowerInvariant();
            if (!TiposCambio.Todos.Contains(tipo))
            { error = $"Tipo de cambio «{tipo}» no permitido. Permitidos: {string.Join(", ", TiposCambio.Todos)}."; return null; }

            Tuberia t = m.Tuberias.FirstOrDefault(x => Calculos.Igual(x.Handle, handle));
            Estructura e = t == null ? m.Estructuras.FirstOrDefault(x => Calculos.Igual(x.Handle, handle)) : null;
            if (t == null && e == null) { error = $"No hay ninguna tubería ni estructura con handle {handle}."; return null; }

            var c = new CambioPropuesto { Handle = handle, Tipo = tipo, Elemento = t?.Nombre ?? e?.Nombre };
            switch (tipo)
            {
                case TiposCambio.COTA_INICIO:
                case TiposCambio.COTA_FIN:
                    return PrepararCota(m, t, c, valor, out error);
                case TiposCambio.CAPA:
                    string capa = (valor ?? "").Trim();
                    if (capa.Length == 0 || capa.IndexOfAny("<>/\\\":;?*|,=`".ToCharArray()) >= 0)
                    { error = $"Nombre de capa no válido: «{valor}»."; return null; }
                    c.Antes = t?.Capa ?? e?.Capa;
                    c.Despues = capa;
                    if (capaExiste != null && !capaExiste(capa))
                        c.Consecuencias.Add($"La capa «{capa}» no existe: se creará.");
                    return c;
                default:   // descripcion
                    if (t == null) { error = "La descripción solo se cambia en tuberías."; return null; }
                    string d = valor ?? "";
                    if (d.Length > TEXTO_MAX) { error = $"Descripción demasiado larga (máx. {TEXTO_MAX})."; return null; }
                    c.Antes = t.Descripcion ?? "";
                    c.Despues = d;
                    return c;
            }
        }

        private static CambioPropuesto PrepararCota(Modelo m, Tuberia t, CambioPropuesto c, string valor, out string error)
        {
            error = null;
            if (t == null) { error = "Las cotas solo se cambian en tuberías."; return null; }
            if (t.TipoRed != TipoRed.Gravedad)
            { error = "Por ahora solo se cambian rasantes de tuberías de gravedad/conduit."; return null; }
            if (!double.TryParse((valor ?? "").Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out double z))
            { error = $"Cota no numérica: «{valor}»."; return null; }
            if (z < COTA_MIN_FT || z > COTA_MAX_FT)
            { error = $"Cota fuera de rango ({COTA_MIN_FT}–{COTA_MAX_FT} ft): {z}."; return null; }

            bool ini = c.Tipo == TiposCambio.COTA_INICIO;
            double? antes = ini ? t.CotaIni : t.CotaFin;
            c.Antes = antes.HasValue ? F(antes.Value) : "";
            c.Despues = F(z);

            double? zi = ini ? z : t.CotaIni, zf = ini ? t.CotaFin : z;
            if (zi.HasValue && zf.HasValue && t.LargoFt > 1e-6)
            {
                double p = (zi.Value - zf.Value) / t.LargoFt * 100.0;
                double? p0 = Calculos.Pendiente(t);
                c.Consecuencias.Add($"Pendiente {(p0.HasValue ? F(p0.Value) + " %" : "—")} → {F(p)} %.");
                if (p <= 0) c.Advertencias.Add("Queda en contrapendiente o sin pendiente.");
            }
            string sh = ini ? t.EstructuraIni : t.EstructuraFin;
            Estructura s = m.Estructuras.FirstOrDefault(x => Calculos.Igual(x.Handle, sh));
            if (s != null)
            {
                if (s.Sump.HasValue && z < s.Sump.Value - 1e-6)
                    c.Advertencias.Add($"Queda {F(s.Sump.Value - z)} ft bajo el fondo (sump) de {s.Nombre}.");
                if (s.Rim.HasValue && z > s.Rim.Value)
                    c.Advertencias.Add($"Queda sobre la tapa (rim) de {s.Nombre}.");
            }
            return c;
        }

        public static string F(double v) => Math.Round(v, 2).ToString("0.00", CultureInfo.InvariantCulture);
    }
}
