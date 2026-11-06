using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  DOMINIO: cambios que la IA puede PROPONER (lista cerrada). Cada tipo es una
//  CLASE con sus datos, cómo comprueba que sigue valiendo al confirmar
//  (`Vigente`) y lo que hace en datos (`Efecto`: la app lo aplica a una copia para
//  revisar SUS normativas). El adaptador de Civil 3D aplica cada clase.
//  Un cambio solo se aplica con confirmar_cambio (lo decide el usuario).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public static class TiposCambio
    {
        public const string COTA_INICIO = "cota_inicio";
        public const string COTA_FIN = "cota_fin";
        public const string CAPA = "capa";
        public const string DESCRIPCION = "descripcion";

        /// <summary>Los de proponer_cambio.</summary>
        public static readonly string[] Todos = { COTA_INICIO, COTA_FIN, CAPA, DESCRIPCION };

        public const string DESPLAZAR = "desplazar_vertical";        // proponer_solucion
        public const string MOVER_PLANTA = "mover_planta";           // proponer_mover_planta
        public const string PENDIENTE = "pendiente";                 // proponer_pendiente
        public const string TAMANO = "tamano";                       // proponer_tamano
        public const string PERFIL = "perfil";                       // crear_perfil
        public const string BUZON = "buzon";                         // proponer_buzon
        public const string PONER_VALVULA = "poner_valvula";         // proponer_valvula
        public const string QUITAR_VALVULA = "quitar_valvula";       // proponer_valvula (quitar)
        public const string QUITAR_ACCESORIO = "quitar_accesorio";   // proponer_quitar_accesorio
        public const string CONEXION_VERTICAL = "conexion_vertical"; // proponer_conexion_vertical
    }

    /// <summary>Lo común a todo cambio propuesto.</summary>
    public abstract class CambioPropuesto
    {
        public string Id;
        public string Handle;           // el elemento principal (para «Ver en Civil 3D»)
        public string Elemento;         // nombre legible
        public string Tipo;
        public string Antes;
        public string Despues;
        public string Motivo;
        public List<string> Consecuencias = new List<string>();
        public List<string> Advertencias = new List<string>();
        /// <summary>Tuberías que toca (o la principal): con ellas se calcula la huella.</summary>
        public List<string> Handles = new List<string>();
        public string Huella;
        public DateTime Creado;
        public string Origen;
        public string Usuario;

        /// <summary>Huella de lo que el cambio toca en el dibujo de ahora (por defecto: cotas de sus tuberías).</summary>
        public virtual string HuellaDe(Modelo m) => ReglasCambio.Huella(m, Handles);

        /// <summary>Null si se puede aplicar sobre el dibujo de ahora; si no, por qué hay que volver a proponerlo.</summary>
        public virtual string Vigente(Modelo m, Func<string, bool> capaExiste) =>
            HuellaDe(m) == Huella ? null : "El dibujo cambió desde la propuesta (cotas, tamaños o posición). Volver a proponerlo.";

        /// <summary>Lo que hace, en datos (la app lo aplica a una copia y revisa sus normativas). Null = nada que revisar.</summary>
        public virtual object Efecto() => null;

        /// <summary>Lo que vuelve al cliente (la tarjeta de la propuesta).</summary>
        public object Resumen() => new
        {
            Id, Handle, Elemento, Tipo, Antes, Despues, Consecuencias, Advertencias,
            tuberias = Handles.Count, efecto = Efecto(),
            instruccion = "Mostrar al usuario. Se aplica solo con el botón del usuario.",
        };
    }

    // ------------------------------------------------------------ cambio simple (proponer_cambio)

    /// <summary>Cota de inicio/fin, capa o descripción de UN elemento.</summary>
    public sealed class CambioSimple : CambioPropuesto
    {
        public override string Vigente(Modelo m, Func<string, bool> capaExiste)
        {
            var ahora = ReglasCambio.Preparar(m, Handle, Tipo, Despues, capaExiste, out string error);
            if (ahora == null) return error;
            return string.Equals(ahora.Antes ?? "", Antes ?? "", StringComparison.Ordinal) ? null
                : $"El elemento cambió desde la propuesta (antes «{Antes}», ahora «{ahora.Antes}»). Volver a proponer.";
        }

        public override object Efecto()
        {
            if (Tipo != TiposCambio.COTA_INICIO && Tipo != TiposCambio.COTA_FIN) return null;
            double z = double.Parse(Despues, CultureInfo.InvariantCulture);
            object c = Tipo == TiposCambio.COTA_INICIO ? new { handle = Handle, ini = z } : (object)new { handle = Handle, fin = z };
            return new { cotas = new[] { c } };
        }
    }

    // ------------------------------------------------------------ mover (vertical y en planta)

    /// <summary>Mueve una utilidad (o un tramo) ENTERA: sus tuberías, accesorios y estructuras propias, el mismo
    /// vector. Dz = subir/bajar (la pendiente no cambia); Dx/Dy = en planta.</summary>
    public sealed class CambioMover : CambioPropuesto
    {
        public List<string> Accesorios = new List<string>();      // piezas de Civil 3D y sólidos del plugin
        public List<string> Estructuras = new List<string>();     // estructuras que solo usan tuberías del grupo
        public double Dx, Dy, Dz;
        public double DeltaFt => Dz;

        public override string HuellaDe(Modelo m) => ReglasCambio.Huella(m, Handles) + "#" + ReglasCambio.HuellaPlanta(m, Handles);

        public override object Efecto() => new { mover = new { handles = Handles, estructuras = Estructuras, dx = Dx, dy = Dy, dz = Dz } };
    }

    // ------------------------------------------------------------ pendiente, tamaño, perfil

    /// <summary>Rasantes nuevas de una tubería.</summary>
    public sealed class CotaNueva { public string Handle; public double Ini, Fin; }

    public sealed class CambioPendiente : CambioPropuesto
    {
        public List<CotaNueva> Cotas = new List<CotaNueva>();
        public override object Efecto() => new { cotas = Cotas.Select(c => new { handle = c.Handle, ini = c.Ini, fin = c.Fin }) };
    }

    /// <summary>Tamaño nuevo de una tubería: `Clave` la entiende el adaptador de Civil 3D.</summary>
    public sealed class TamanoNuevo { public string Handle, Clave, Nombre, Material; public double DiametroIn; }

    public sealed class CambioTamano : CambioPropuesto
    {
        public List<TamanoNuevo> Tamanos = new List<TamanoNuevo>();
        public override string HuellaDe(Modelo m) => ReglasCambio.HuellaTamano(m, Handles);
        public override object Efecto() =>
            new { tamanos = Tamanos.Select(t => new { handle = t.Handle, diam_in = t.DiametroIn, material = t.Material }) };
    }

    public sealed class CambioPerfil : CambioPropuesto
    {
        public double SemillaX, SemillaY;        // punto sobre el tramo de inicio
        public double? FinX, FinY;               // punto sobre el tramo final (null = recorrido completo)

        public override string Vigente(Modelo m, Func<string, bool> capaExiste) =>
            Handles.All(h => m.Tuberias.Any(t => Calculos.Igual(t.Handle, h))) ? null
                : "Una de las tuberías del perfil ya no existe. Volver a proponerlo.";
    }

    // ------------------------------------------------------------ buzones

    public sealed class CambioBuzon : CambioPropuesto
    {
        public double? Rim, Sump;                // nuevos (null = no cambia)
        public override string HuellaDe(Modelo m) => ReglasCambio.HuellaEstructura(m, Handle);
        public override object Efecto() => new { estructuras = new[] { new { handle = Handle, rim = Rim, sump = Sump } } };
    }

    // ------------------------------------------------------------ válvulas y accesorios

    public sealed class CambioValvula : CambioPropuesto
    {
        public bool Poner;                       // false = quitar
        public double X, Y, DirX, DirY;          // centro y rumbo del tramo
        public double DiametroIn, LargoIn;
        public string Union = "FLG", Material = "";
        public List<string> Solidos = new List<string>();      // quitar: los sólidos de la válvula

        public override string HuellaDe(Modelo m) =>
            ReglasCambio.Huella(m, Handles) + "#" + ReglasCambio.HuellaPlanta(m, Handles) + "#" + string.Join(",", Solidos);
    }

    public sealed class CambioQuitarAccesorio : CambioPropuesto
    {
        public double X, Y;
        public List<string> Accesorios = new List<string>();   // la pieza o los sólidos del accesorio
        public override string HuellaDe(Modelo m) =>
            ReglasCambio.Huella(m, Handles) + "#" + ReglasCambio.HuellaPlanta(m, Handles) + "#" + string.Join(",", Accesorios);
    }

    /// <summary>Conexión vertical entre dos utilidades que se tocan en planta a distinta cota (tramo vertical con
    /// sus codos/Tees, como las aprobadas en la app).</summary>
    public sealed class CambioConexionVertical : CambioPropuesto
    {
        public double X, Y;
        public string TuberiaA, TuberiaB;        // handles de las dos tuberías que se tocan
        public double ZA, ZB;                    // rasantes en el punto
    }

    // ------------------------------------------------------------ registro y reglas

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

        /// <summary>Valida y arma un cambio SIMPLE. Devuelve null y `error` si no se puede.</summary>
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

            var c = new CambioSimple { Handle = handle, Tipo = tipo, Elemento = t?.Nombre ?? e?.Nombre };
            c.Handles.Add(handle);
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

        /// <summary>El cambio «mover la utilidad entera» de una opción ya probada (SolucionesRed).</summary>
        public static CambioMover Desplazar(Modelo m, OpcionSolucion o, ConflictoRed c)
        {
            var zs = o.Tuberias.SelectMany(t => new[] { t.CotaIni, t.CotaFin }).Where(z => z.HasValue).Select(z => z.Value).ToList();
            string Rango(double d) => zs.Count == 0 ? "—" : zs.Min() == zs.Max() ? F(zs.Min() + d) : $"{F(zs.Min() + d)} a {F(zs.Max() + d)}";
            var cp = new CambioMover
            {
                Handle = o.Principal.Handle, Tipo = TiposCambio.DESPLAZAR, Dz = o.DeltaFt,
                Elemento = $"{o.Mover} ({o.Tuberias.Count} tubería(s){(o.Accesorios.Count > 0 ? $", {o.Accesorios.Count} accesorio(s)" : "")})",
                Antes = Rango(0), Despues = Rango(o.DeltaFt),
                Handles = o.Tuberias.Select(t => t.Handle).ToList(),
                Accesorios = o.Accesorios.Select(a => a.Handle).ToList(),
            };
            cp.Huella = cp.HuellaDe(m);
            cp.Consecuencias.Add($"{(o.Accion == "bajar" ? "Baja" : "Sube")} {F(Math.Abs(o.DeltaFt))} ft toda la utilidad {o.Mover}: " +
                                 "sus tuberías y accesorios juntos, la pendiente no cambia.");
            cp.Consecuencias.Add($"Resuelve el conflicto {c.Id} con {o.Otra} ({SolucionesRed.Texto(c)})" +
                                 (c.RequeridoFt > 0 ? $": quedan {F(c.RequeridoFt)} ft libres, lo que pide la normativa." : "."));
            if (o.TambienResuelve.Count > 0) cp.Consecuencias.Add("También resuelve: " + string.Join(", ", o.TambienResuelve) + ".");
            foreach (var n in o.Nuevos) cp.Advertencias.Add("Crearía otro conflicto: " + n + ".");
            foreach (var u in o.UnionesRotas) cp.Advertencias.Add("Se separaría una unión: " + u + ".");
            cp.Advertencias.AddRange(o.Avisos);
            return cp;
        }

        /// <summary>Cotas actuales de esas tuberías: si cambian entre la propuesta y la confirmación, se vuelve a proponer.</summary>
        public static string Huella(Modelo m, IEnumerable<string> handles) =>
            string.Join("|", handles.Select(h =>
            {
                Tuberia t = m.Tuberias.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                return t == null ? h + ":-" : $"{h}:{(t.CotaIni.HasValue ? F(t.CotaIni.Value) : "-")}/{(t.CotaFin.HasValue ? F(t.CotaFin.Value) : "-")}";
            }));

        /// <summary>Puntas en planta de esas tuberías.</summary>
        public static string HuellaPlanta(Modelo m, IEnumerable<string> handles) =>
            string.Join("|", handles.Select(h =>
            {
                Tuberia t = m.Tuberias.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                return t == null ? h + ":-" : $"{h}:{F(t.XIni)},{F(t.YIni)},{F(t.XFin)},{F(t.YFin)}";
            }));

        public static string HuellaTamano(Modelo m, IEnumerable<string> handles) =>
            string.Join("|", handles.Select(h =>
            {
                Tuberia t = m.Tuberias.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                return t == null ? h + ":-" : $"{h}:{t.Familia}/{t.Tamano}";
            }));

        public static string HuellaEstructura(Modelo m, string handle)
        {
            Estructura e = m.Estructuras.FirstOrDefault(x => Calculos.Igual(x.Handle, handle));
            return e == null ? "-" : $"{(e.Rim.HasValue ? F(e.Rim.Value) : "-")}/{(e.Sump.HasValue ? F(e.Sump.Value) : "-")}";
        }

        public static string F(double v) => Math.Round(v, 2).ToString("0.00", CultureInfo.InvariantCulture);
    }
}
