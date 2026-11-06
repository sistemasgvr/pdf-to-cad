using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO: revisión del plano (PURO) — revisar, cotas, textos y arreglos.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed partial class Despachador
    {
        private void RegistrarPlano()
        {
            Caso("revisar_plano", (a, p) => RevisarPlano(a));
            Caso("buscar_cotas", (a, p) => BuscarCotas(a));
            Caso("proponer_arreglo_revision", ArregloRevision);
            Caso("proponer_texto", ProponerTexto);
            Caso("proponer_cota", ProponerCota);
        }

        private object RevisarPlano(JsonObject a)
        {
            string tipo = Args.Texto(a, "tipo");
            var items = RevisionPlano.Revisar(_lector.Leer(), Args.Texto(a, "capa"))
                                     .Where(i => string.IsNullOrWhiteSpace(tipo) || Calculos.Igual(i.Tipo, tipo.Trim())).ToList();
            int lim = Args.Entero(a, "limite", 40, 1, LIMITE_MAX);
            object t = Tabla(items.Count, lim, new[] { "id", "tipo", "x", "y", "que", "arreglo" },
                items.Take(lim).Select(i => new object[]
                {
                    i.Id, i.Tipo, Calculos.R2(i.X), Calculos.R2(i.Y), i.Texto,
                    i.Tipo == RevisionPlano.FLECHA_SUELTA ? "borrarla" : i.Tipo == RevisionPlano.TRAMA ? "máscara" : i.Mover != null ? "mover el texto" : "a mano",
                }));
            return new
            {
                revision = t,
                por_tipo = items.GroupBy(i => i.Tipo).ToDictionary(g => g.Key, g => g.Count()),
                siguiente = items.Count > 0 ? "Mostrar la lista numerada al usuario; para cada uno que quiera: proponer_arreglo_revision con su Q#." : null,
            };
        }

        private object BuscarCotas(JsonObject a)
        {
            string texto = Args.Texto(a, "texto"), estilo = Args.Texto(a, "estilo"), capa = Args.Texto(a, "capa");
            var cs = _lector.Leer().Cotas.Where(c => (string.IsNullOrWhiteSpace(texto) || Calculos.Contiene(c.Texto, texto)) &&
                                                     (string.IsNullOrWhiteSpace(estilo) || Calculos.Igual(c.Estilo, estilo)) &&
                                                     (string.IsNullOrWhiteSpace(capa) || Calculos.Contiene(c.Capa, capa))).ToList();
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            return Tabla(cs.Count, lim, new[] { "handle", "tipo", "texto", "medida", "estilo", "decimales", "flecha", "altura_texto", "capa", "x", "y" },
                cs.Take(lim).Select(c => new object[]
                {
                    c.Handle, c.Tipo, c.Texto, Math.Round(c.Medida, 3), c.Estilo, c.Decimales, Math.Round(c.Flecha, 3), Math.Round(c.AlturaTexto, 3),
                    c.Capa, Calculos.R2(c.CajaTexto.Cx), Calculos.R2(c.CajaTexto.Cy),
                }));
        }

        private object ArregloRevision(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            string id = NormalizarId(Requerido(a, "punto"), "Q");
            var items = RevisionPlano.Revisar(m);
            var q = items.FirstOrDefault(i => Calculos.Igual(i.Id, id))
                    ?? throw new ErrorUsuario(items.Count == 0 ? "La revisión ya no encuentra nada." : $"No hay un punto «{id}» (hay {items.Count}: Q1…Q{items.Count}).");
            var cp = RevisionPlano.Arreglo(m, q, out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Revisión " + q.Id);
        }

        private object ProponerTexto(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            var textos = Textos(m, a);
            string mas = Args.Texto(a, "mascara");
            var cp = CambiosTexto.Editar(m, textos, Args.Texto(a, "reemplazar"), Args.Texto(a, "por", ""),
                                         Args.Numero(a, "dx") ?? 0, Args.Numero(a, "dy") ?? 0, Args.Numero(a, "altura"),
                                         string.IsNullOrWhiteSpace(mas) ? (bool?)null : mas.Trim().ToLowerInvariant().StartsWith("s"), out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Texto");
        }

        /// <summary>«elemento» = un texto (handle o su contenido exacto); «buscar» = todos los que lo contienen.</summary>
        private static List<TextoDibujo> Textos(Modelo m, JsonObject a)
        {
            string capa = Args.Texto(a, "capa");
            bool EnCapa(TextoDibujo t) => string.IsNullOrWhiteSpace(capa) || Calculos.Contiene(t.Capa, capa);
            string q = Args.Texto(a, "elemento");
            if (!string.IsNullOrWhiteSpace(q))
            {
                var uno = m.Textos.Where(t => Calculos.Igual(t.Handle, q.Trim())).ToList();
                if (uno.Count == 0) uno = m.Textos.Where(t => EnCapa(t) && Referencias.Clave(t.Contenido) == Referencias.Clave(q)).ToList();
                if (uno.Count == 0) throw new ErrorUsuario($"No encontré un texto «{q}». Usa 'buscar' para todos los que lo contienen.");
                return uno;
            }
            string b = Args.Texto(a, "buscar");
            if (string.IsNullOrWhiteSpace(b)) b = Args.Texto(a, "reemplazar");
            if (string.IsNullOrWhiteSpace(b)) throw new ErrorUsuario("Dime qué texto: 'elemento' o 'buscar'.");
            return m.Textos.Where(t => EnCapa(t) && Calculos.Contiene(t.Contenido, b.Trim())).ToList();
        }

        private object ProponerCota(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            string accion = (Args.Texto(a, "accion") ?? "").Trim().ToLowerInvariant();
            double? x1 = Args.Numero(a, "x1"), y1 = Args.Numero(a, "y1"), x2 = Args.Numero(a, "x2"), y2 = Args.Numero(a, "y2");
            CambioCota cp;
            string error;
            if (accion.StartsWith("crea") || (accion.Length == 0 && x1.HasValue))
            {
                if (!x1.HasValue || !y1.HasValue || !x2.HasValue || !y2.HasValue) throw new ErrorUsuario("Para crear una cota: 'x1','y1','x2','y2'.");
                cp = CambiosTexto.Crear(x1.Value, y1.Value, x2.Value, y2.Value, Args.Numero(a, "desplazamiento") ?? 3.0, Args.Texto(a, "estilo"), out error);
            }
            else
            {
                var hs = Args.Lista(a, "cotas");
                string b = Args.Texto(a, "buscar"), ea = Args.Texto(a, "estilo_actual");
                var cs = m.Cotas.Where(c => (hs.Count > 0 && hs.Any(h => Calculos.Igual(h, c.Handle))) ||
                                            (hs.Count == 0 && ((!string.IsNullOrWhiteSpace(b) && Calculos.Contiene(c.Texto, b)) ||
                                                               (!string.IsNullOrWhiteSpace(ea) && Calculos.Igual(c.Estilo, ea))))).ToList();
                double? dec = Args.Numero(a, "decimales");
                cp = CambiosTexto.Cambiar(m, cs, Args.Texto(a, "estilo"), dec.HasValue ? (int)Math.Round(dec.Value) : (int?)null,
                                          Args.Numero(a, "flecha"), Args.Numero(a, "altura_texto"), Args.Texto(a, "texto"), out error);
            }
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Cota");
        }
    }
}
