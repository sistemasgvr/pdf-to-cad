using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO: pendientes, tamaños y perfiles (PURO). Todo queda PENDIENTE
//  hasta confirmar_cambio (botón del usuario). La pendiente de la normativa la
//  calcula la APP con sus reglas y llega en «objetivos» ({handle: {min, max,
//  fuente}}); la app además revisa cada propuesta con su validador.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed partial class Despachador
    {
        private void RegistrarRed()
        {
            Caso("proponer_pendiente", ProponerPendiente);
            Caso("proponer_tamano", ProponerTamano);
            Caso("crear_perfil", CrearPerfil);
        }

        private object ProponerPendiente(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            var ts = Seleccion(m, a);
            double? pct = Args.Numero(a, "pendiente_pct");
            if (pct.HasValue && (pct.Value <= 0 || pct.Value > 100))
                throw new ErrorUsuario($"Pendiente no válida: {pct.Value} %. Tiene que ser mayor que 0 (el agua baja del inicio al fin).");
            bool soloMalas = !pct.HasValue || ts.Count > 1;
            var cp = CambiosRed.Pendiente(m, ts, Objetivos(a), pct, Args.Texto(a, "mantener", "inicio"), soloMalas, out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Ajustar pendiente");
        }

        private object ProponerTamano(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            var ts = Seleccion(m, a);
            var cache = new Dictionary<string, List<TamanoDisponible>>(StringComparer.OrdinalIgnoreCase);
            List<TamanoDisponible> Disponibles(Tuberia t)
            {
                if (!cache.TryGetValue(t.Red ?? "", out var l)) cache[t.Red ?? ""] = l = _lector.Tamanos(t.Handle);
                return l;
            }
            var cp = CambiosRed.Tamano(m, ts, Disponibles, Args.Numero(a, "diametro_in"), Args.Texto(a, "material"), out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Cambiar tamaño");
        }

        private object CrearPerfil(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            Tuberia ini = UnaTuberia(m, Args.Texto(a, "desde") ?? Args.Texto(a, "elemento"), "desde");
            string q = Args.Texto(a, "hasta");
            Tuberia fin = string.IsNullOrWhiteSpace(q) ? null : UnaTuberia(m, q, "hasta");
            var cp = CambiosRed.Perfil(ini, fin, Args.Texto(a, "nombre"), out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Crear perfil");
        }

        /// <summary>Las tuberías pedidas: «red» (todas las de la red), o «elementos»/«elemento» = utilidad de la app
        /// («AGUA-20»: todas sus tuberías), nombre de red, o una tubería por su nombre.</summary>
        private static List<Tuberia> Seleccion(Modelo m, JsonObject a)
        {
            var r = new List<Tuberia>();
            string red = Args.Texto(a, "red");
            if (!string.IsNullOrWhiteSpace(red))
            {
                r.AddRange(m.Tuberias.Where(t => Referencias.Clave(t.Red) == Referencias.Clave(red)));
                if (r.Count == 0) throw new ErrorUsuario($"No hay ninguna red «{red}» con tuberías.");
            }
            var pedidos = Args.Lista(a, "elementos");
            string uno = Args.Texto(a, "elemento");
            if (!string.IsNullOrWhiteSpace(uno)) pedidos.Add(uno);
            foreach (string q in pedidos) r.AddRange(Utilidad(m, q));
            if (r.Count == 0) throw new ErrorUsuario("No se indicó qué tuberías (su nombre, la utilidad «AGUA-20» o la red).");
            return r.GroupBy(t => t.Handle, StringComparer.OrdinalIgnoreCase).Select(g => g.First()).ToList();
        }

        /// <summary>«AGUA-20» = las tuberías de esa utilidad de la app; si no, de esa red; si no, la tubería por su nombre.</summary>
        private static List<Tuberia> Utilidad(Modelo m, string q)
        {
            string k = Referencias.Clave(q);
            var util = m.Tuberias.Where(t => !string.IsNullOrEmpty(t.UtilidadNumero) && Referencias.Clave(t.Utilidad()) == k).ToList();
            if (util.Count == 0) util = m.Tuberias.Where(t => Referencias.Clave(t.Red) == k).ToList();
            if (util.Count == 0) util.Add(UnaTuberia(m, q, "elemento"));
            return util;
        }

        private static Tuberia UnaTuberia(Modelo m, string q, string arg)
        {
            if (string.IsNullOrWhiteSpace(q)) throw new ErrorUsuario($"Falta el argumento '{arg}' (nombre de una tubería).");
            Referencia r = Resolver(m, q);
            Tuberia t = m.Tuberias.FirstOrDefault(x => Calculos.Igual(x.Handle, r.Handle));
            if (t == null) throw new ErrorUsuario($"{r.Nombre} no es una tubería.");
            return t;
        }

        /// <summary>«objetivos»: {handle: {min, max, fuente}} (la pendiente que pide la normativa de la app).</summary>
        private static Dictionary<string, ObjetivoPendiente> Objetivos(JsonObject a)
        {
            var r = new Dictionary<string, ObjetivoPendiente>(StringComparer.OrdinalIgnoreCase);
            if (a == null || !(a["objetivos"] is JsonObject o)) return r;
            foreach (var kv in o)
                if (kv.Value is JsonObject x)
                    r[kv.Key] = new ObjetivoPendiente { Min = Args.Numero(x, "min"), Max = Args.Numero(x, "max"), Fuente = Args.Texto(x, "fuente") };
            return r;
        }
    }
}
