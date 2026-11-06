using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO: conflictos entre tuberías y su solución (PURO).
//    buscar_conflictos  → tabla K1… con lo que se chocan o quedan sin la separación.
//    proponer_solucion  → prueba subir/bajar cada utilidad del conflicto y deja
//                         PENDIENTE la mejor (o la que pida el usuario: «mover»,
//                         «accion», «opcion»); se aplica con confirmar_cambio.
//  Las separaciones llegan en «reglas» (la app las saca de sus normativas).
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed partial class Despachador
    {
        private void RegistrarConflictos()
        {
            Caso("buscar_conflictos", (a, p) => BuscarConflictos(a));
            Caso("proponer_solucion", ProponerSolucion);
        }

        private object BuscarConflictos(JsonObject a)
        {
            var reglas = Reglas(a);
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            var todos = Conflictos.Buscar(_lector.Leer(), reglas, out int sinCota);
            var tabla = Tabla(todos.Count, lim,
                new[] { "id", "tipo", "tuberia_a", "utilidad_a", "tuberia_b", "utilidad_b", "x", "y",
                        "libre_ft", "requerido_ft", "encima" },
                todos.Take(lim).Select(c => new object[]
                {
                    c.Id, c.Tipo, c.A.Nombre, c.A.Utilidad(), c.B.Nombre, c.B.Utilidad(), Calculos.R2(c.X), Calculos.R2(c.Y),
                    Calculos.R2(c.LibreFt), Calculos.R2(c.RequeridoFt), c.Encima,
                }));
            return new
            {
                conflictos = tabla,
                sin_cota = sinCota > 0 ? $"{sinCota} cruce(s) sin cotas: no se pueden medir." : null,
                normativas = reglas.Count == 0
                    ? "Sin separaciones de normativa: solo se buscaron choques (paredes que se tocan)."
                    : $"{reglas.Count} regla(s) de separación de las normativas de la app.",
                siguiente = todos.Count > 0 ? "Para cada conflicto, proponer_solucion con su id (K1…)." : null,
            };
        }

        private object ProponerSolucion(JsonObject a, Pedido p)
        {
            var reglas = Reglas(a);
            Modelo m = _lector.Leer();
            var todos = Conflictos.Buscar(m, reglas, out int _);
            string q = Requerido(a, "conflicto");
            ConflictoRed c = todos.FirstOrDefault(k => Calculos.Igual(k.Id, NormalizarId(q, "K")));
            if (c == null)
                throw new ErrorUsuario(todos.Count == 0 ? "Ya no hay conflictos entre tuberías."
                    : $"No hay un conflicto «{q}». Hay {todos.Count}: {string.Join(", ", todos.Take(12).Select(k => k.Id))}" +
                      (todos.Count > 12 ? "…" : "") + ".");
            var ops = SolucionesRed.Opciones(m, c, reglas, todos);
            if (ops.Count == 0) throw new ErrorUsuario($"No encontré cómo mover {c.A.Nombre} ni {c.B.Nombre} para resolver {c.Id}.");

            IEnumerable<OpcionSolucion> elegibles = ops;
            string mover = Args.Texto(a, "mover"), accion = Args.Texto(a, "accion"), opcion = Args.Texto(a, "opcion");
            if (!string.IsNullOrWhiteSpace(opcion))
                elegibles = elegibles.Where(o => Calculos.Igual(o.Id, NormalizarId(opcion, "P")));
            if (!string.IsNullOrWhiteSpace(mover))
                elegibles = elegibles.Where(o => Mueve(m, o, mover));
            if (!string.IsNullOrWhiteSpace(accion))
                elegibles = elegibles.Where(o => Calculos.Contiene(o.Accion, accion.Trim().ToLowerInvariant().StartsWith("sub") ? "subir" : "bajar"));
            OpcionSolucion elegida = elegibles.FirstOrDefault();
            if (elegida == null)
                throw new ErrorUsuario("Ninguna opción cumple lo pedido. Opciones: " +
                                       string.Join("; ", ops.Select(o => $"{o.Id} {o.Accion} {o.Mover} {Conflictos.F(Math.Abs(o.DeltaFt))} ft ({o.Motivo()})")));

            var cp = ReglasCambio.Desplazar(m, elegida, c);
            cp.Motivo = Args.Texto(a, "motivo", $"Resolver {c.Id}");
            Propuesta(cp, a, p, $"Resolver {c.Id}");
            return new
            {
                cp.Id, cp.Handle, cp.Elemento, cp.Tipo, cp.Antes, cp.Despues, cp.Consecuencias, cp.Advertencias,
                efecto = cp.Efecto(),
                conflicto = c.Id,
                opcion = elegida.Id,
                valida = elegida.Valida,
                opciones = new
                {
                    columnas = new[] { "opcion", "mover", "accion", "ft", "tuberias", "accesorios", "resultado" },
                    filas = ops.Select(o => new object[]
                    {
                        o.Id, o.Mover, o.Accion, Calculos.R2(Math.Abs(o.DeltaFt)), o.Tuberias.Count, o.Accesorios.Count, o.Motivo(),
                    }).ToList(),
                },
                instruccion = "Mostrar al usuario la opción elegida y que hay otras. Se aplica solo con el botón del usuario.",
            };
        }

        /// <summary>¿La opción mueve lo que nombró el usuario? (tubería, utilidad «AGUA-20», red o capa).</summary>
        private static bool Mueve(Modelo m, OpcionSolucion o, string q)
        {
            string k = Referencias.Clave(q);
            if (Referencias.Clave(o.Mover).Contains(k) || o.Tuberias.Any(t =>
                    Referencias.Clave(t.Nombre) == k || Referencias.Clave(t.Red).Contains(k) || Referencias.Clave(t.Capa).Contains(k)))
                return true;
            Referencia r = Referencias.Resolver(m, q, out string _);
            return r != null && o.Tuberias.Any(t => Calculos.Igual(t.Handle, r.Handle));
        }

        /// <summary>«K3», «3», «conflicto 3», «k-3» → «K3».</summary>
        private static string NormalizarId(string q, string prefijo)
        {
            string d = new string((q ?? "").Where(char.IsDigit).ToArray());
            return d.Length > 0 ? prefijo + int.Parse(d, CultureInfo.InvariantCulture) : (q ?? "").Trim();
        }

        /// <summary>«reglas»: [{a, b, sep_v_ft, encima, debajo, fuente}] (b = «*» = con cualquiera).</summary>
        private static List<ReglaSeparacion> Reglas(JsonObject a)
        {
            var r = new List<ReglaSeparacion>();
            if (a == null || !a.TryGetPropertyValue("reglas", out JsonNode n) || !(n is JsonArray arr)) return r;
            foreach (JsonNode x in arr)
            {
                if (!(x is JsonObject o)) continue;
                double? sep = Args.Numero(o, "sep_v_ft");
                string ca = Args.Texto(o, "a"), cb = Args.Texto(o, "b");
                if (string.IsNullOrWhiteSpace(ca) || string.IsNullOrWhiteSpace(cb)) continue;
                r.Add(new ReglaSeparacion
                {
                    A = ca.Trim(), B = cb.Trim(), SepVFt = Math.Max(0.0, Math.Min(sep ?? 0.0, 100.0)),
                    Encima = Args.Texto(o, "encima"), Debajo = Args.Texto(o, "debajo"), Fuente = Args.Texto(o, "fuente"),
                });
            }
            return r;
        }
    }
}
