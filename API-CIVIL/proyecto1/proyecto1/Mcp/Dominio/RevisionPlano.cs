using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: REVISIÓN DEL PLANO (PURO) — lo que un revisor marca en una lámina:
//    · guia_cruza_texto : una guía (flecha) pasa por encima de un texto que no es el suyo.
//    · guia_cruza_cota  : una guía cruza la línea o el texto de una cota.
//    · flecha_suelta    : una guía sin texto (flecha huérfana).
//    · texto_sobre_texto: dos textos se tapan.
//    · cota_sobre_texto : el texto de una cota tapa un texto.
//    · texto_en_trama   : un texto o una cota dentro de una trama chica, sin máscara (se lee mal).
//  Ids Q1… de arriba abajo y de izquierda a derecha. `Arreglo(q)` arma la propuesta
//  de cada uno (mover lo justo, borrar la flecha suelta o poner máscara); el usuario decide.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class ItemRevision
    {
        public string Id, Tipo, Texto;
        public double X, Y;
        public List<string> Handles = new List<string>();    // [0] = lo que se arreglaría
        public string Mover;                                   // handle del texto/cota a mover (si aplica)
        public bool MoverEsCota;
        public double Dx, Dy;                                  // lo justo para que deje de tapar
    }

    public static class RevisionPlano
    {
        public const string GUIA_TEXTO = "guia_cruza_texto", GUIA_COTA = "guia_cruza_cota", FLECHA_SUELTA = "flecha_suelta",
                            TEXTO_TEXTO = "texto_sobre_texto", COTA_TEXTO = "cota_sobre_texto", TRAMA = "texto_en_trama";
        public const double SOLAPE_MIN = 0.20;          // fracción de la caja más chica
        public const double ENCOGER = 0.08;             // las cajas de texto traen aire alrededor
        public const double TRAMA_MAX_X = 400.0;        // una trama hasta 400× el texto es «la de al lado», no el fondo de la lámina

        public static List<ItemRevision> Revisar(Modelo m, string capa = null)
        {
            bool Es(string c) => string.IsNullOrWhiteSpace(capa) || Calculos.Contiene(c, capa);
            var r = new List<ItemRevision>();
            var textos = m.Textos.Where(t => t.Caja.Valida).ToList();
            var cotas = m.Cotas.ToList();

            foreach (var g in m.Guias.Where(g => Es(g.Capa)))
            {
                if (!g.ConTexto && g.Vertices.Count > 0)
                    r.Add(new ItemRevision { Tipo = FLECHA_SUELTA, X = g.Vertices[0].x, Y = g.Vertices[0].y, Handles = { g.Handle },
                                             Texto = $"Flecha suelta (guía sin texto) en ({F(g.Vertices[0].x)}, {F(g.Vertices[0].y)})." });
                for (int k = 0; k + 1 < g.Vertices.Count; k++)
                {
                    var (ax, ay) = g.Vertices[k]; var (bx, by) = g.Vertices[k + 1];
                    foreach (var t in textos)
                    {
                        if (Calculos.Igual(t.Handle, g.TextoHandle) || Calculos.Igual(t.Handle, g.Handle)) continue;
                        Caja c = t.Caja.Encoger(ENCOGER);
                        if (!c.Corta(ax, ay, bx, by)) continue;
                        var (dx, dy) = Apartar(t.Caja, ax, ay, bx, by, t.Altura * 0.25);
                        r.Add(new ItemRevision { Tipo = GUIA_TEXTO, X = c.Cx, Y = c.Cy, Handles = { t.Handle, g.Handle }, Mover = t.Handle, Dx = dx, Dy = dy,
                                                 Texto = $"La guía {Desc(m, g)} cruza el texto «{CambiosTexto.Corto(t.Contenido)}» en ({F(c.Cx)}, {F(c.Cy)})." });
                    }
                    foreach (var d in cotas)
                    {
                        bool linea = Cruza(ax, ay, bx, by, d.A.x, d.A.y, d.B.x, d.B.y), texto = d.CajaTexto.Valida && d.CajaTexto.Encoger(ENCOGER).Corta(ax, ay, bx, by);
                        if (!linea && !texto) continue;
                        var (dx, dy) = texto ? Apartar(d.CajaTexto, ax, ay, bx, by, d.AlturaTexto * 0.25) : (0.0, 0.0);
                        r.Add(new ItemRevision { Tipo = GUIA_COTA, X = d.CajaTexto.Cx, Y = d.CajaTexto.Cy, Handles = { d.Handle, g.Handle },
                                                 Mover = texto ? d.Handle : null, MoverEsCota = true, Dx = dx, Dy = dy,
                                                 Texto = $"La guía {Desc(m, g)} cruza {(texto ? "el texto" : "la línea")} de la cota «{d.Texto}»." });
                    }
                }
            }
            for (int i = 0; i < textos.Count; i++)
                for (int j = i + 1; j < textos.Count; j++)
                {
                    TextoDibujo a = textos[i], b = textos[j];
                    if (!Es(a.Capa) && !Es(b.Capa)) continue;
                    Caja ca = a.Caja.Encoger(ENCOGER), cb = b.Caja.Encoger(ENCOGER);
                    double s = ca.Solape(cb);
                    if (s <= SOLAPE_MIN * Math.Min(ca.Area, cb.Area)) continue;
                    var chico = ca.Area <= cb.Area ? a : b; var otro = ReferenceEquals(chico, a) ? b : a;
                    var (dx, dy) = Separar(chico.Caja, otro.Caja, chico.Altura * 0.25);
                    r.Add(new ItemRevision { Tipo = TEXTO_TEXTO, X = (ca.Cx + cb.Cx) / 2, Y = (ca.Cy + cb.Cy) / 2, Handles = { chico.Handle, otro.Handle },
                                             Mover = chico.Handle, Dx = dx, Dy = dy,
                                             Texto = $"«{CambiosTexto.Corto(a.Contenido)}» y «{CambiosTexto.Corto(b.Contenido)}» se tapan." });
                }
            foreach (var d in cotas.Where(d => d.CajaTexto.Valida && Es(d.Capa)))
                foreach (var t in textos)
                {
                    Caja cd = d.CajaTexto.Encoger(ENCOGER), ct = t.Caja.Encoger(ENCOGER);
                    if (cd.Solape(ct) <= SOLAPE_MIN * Math.Min(cd.Area, ct.Area)) continue;
                    var (dx, dy) = Separar(d.CajaTexto, t.Caja, d.AlturaTexto * 0.25);
                    r.Add(new ItemRevision { Tipo = COTA_TEXTO, X = cd.Cx, Y = cd.Cy, Handles = { d.Handle, t.Handle }, Mover = d.Handle, MoverEsCota = true,
                                             Dx = dx, Dy = dy, Texto = $"La cota «{d.Texto}» tapa el texto «{CambiosTexto.Corto(t.Contenido)}»." });
                }
            foreach (var tr in m.Tramas)
            {
                foreach (var t in textos.Where(t => !t.Mascara && Es(t.Capa) && tr.Caja.Contiene(t.Caja.Cx, t.Caja.Cy) && tr.Caja.Area <= TRAMA_MAX_X * t.Caja.Area))
                    r.Add(new ItemRevision { Tipo = TRAMA, X = t.Caja.Cx, Y = t.Caja.Cy, Handles = { t.Handle, tr.Handle }, Mover = t.Handle,
                                             Texto = $"El texto «{CambiosTexto.Corto(t.Contenido)}» está dentro de una trama ({tr.Patron}) y se lee mal." });
                foreach (var d in cotas.Where(d => d.CajaTexto.Valida && Es(d.Capa) && tr.Caja.Contiene(d.CajaTexto.Cx, d.CajaTexto.Cy) && tr.Caja.Area <= TRAMA_MAX_X * d.CajaTexto.Area))
                    r.Add(new ItemRevision { Tipo = TRAMA, X = d.CajaTexto.Cx, Y = d.CajaTexto.Cy, Handles = { d.Handle, tr.Handle }, Mover = d.Handle, MoverEsCota = true,
                                             Texto = $"La cota «{d.Texto}» está dentro de una trama ({tr.Patron}) y se lee mal." });
            }
            r = r.OrderByDescending(i => Math.Round(i.Y, 1)).ThenBy(i => i.X).ToList();
            for (int i = 0; i < r.Count; i++) r[i].Id = "Q" + (i + 1);
            return r;
        }

        /// <summary>La propuesta que arregla el punto `q`: borrar la flecha suelta, mover lo justo o poner máscara.</summary>
        public static CambioPropuesto Arreglo(Modelo m, ItemRevision q, out string error)
        {
            error = null;
            if (q.Tipo == FLECHA_SUELTA)
            {
                var b = new CambioBorrar { Tipo = TiposTexto.BORRAR, Handle = q.Handles[0], Elemento = $"Flecha suelta {q.Id}",
                                           Antes = "flecha sin texto", Despues = "borrada", Borrar = { q.Handles[0] } };
                b.Handles.Add(q.Handles[0]);
                b.Consecuencias.Add("Se borra la guía que no lleva texto.");
                b.Huella = b.HuellaDe(m);
                return b;
            }
            if (q.Mover == null) { error = $"{q.Id}: la guía cruza la LÍNEA de la cota; muévela a mano o dime cuánto mover el texto."; return null; }
            var ed = new EdicionTexto { Handle = q.Mover, EsCota = q.MoverEsCota, Dx = q.Dx, Dy = q.Dy };
            var cp = new CambioTexto { Tipo = TiposTexto.TEXTO, Handle = q.Mover, Elemento = $"Arreglo de {q.Id}", Ediciones = { ed } };
            cp.Handles.Add(q.Mover);
            if (q.Tipo == TRAMA)
            {
                if (q.MoverEsCota || m.Textos.Any(t => Calculos.Igual(t.Handle, q.Mover) && t.Tipo == "TEXT"))
                { error = $"{q.Id}: ese texto no admite máscara; muévelo fuera de la trama (dime hacia dónde)."; return null; }
                ed.Mascara = true;
                cp.Antes = "sin fondo"; cp.Despues = "con máscara";
                cp.Consecuencias.Add("Se le pone fondo (máscara) al texto: tapa la trama detrás y se lee.");
            }
            else
            {
                cp.Antes = "donde está"; cp.Despues = $"{CambiosTexto.F(Math.Sqrt(q.Dx * q.Dx + q.Dy * q.Dy))} más allá";
                cp.Consecuencias.Add($"Se mueve {(q.MoverEsCota ? "el texto de la cota" : "el texto")} lo justo para que no se tapen " +
                                     $"(Δx {CambiosTexto.F(q.Dx)}, Δy {CambiosTexto.F(q.Dy)}).");
                // ¿queda tapando otra cosa?
                Caja nueva = Caja(m, q.Mover).Mover(q.Dx, q.Dy).Encoger(ENCOGER);
                var tapa = m.Textos.FirstOrDefault(t => !Calculos.Igual(t.Handle, q.Mover) && t.Caja.Valida &&
                                                        nueva.Solape(t.Caja.Encoger(ENCOGER)) > SOLAPE_MIN * Math.Min(nueva.Area, t.Caja.Area));
                if (tapa != null) cp.Advertencias.Add($"En el lugar nuevo tapa «{CambiosTexto.Corto(tapa.Contenido)}».");
            }
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        private static Caja Caja(Modelo m, string h) =>
            m.Textos.FirstOrDefault(t => Calculos.Igual(t.Handle, h))?.Caja ?? m.Cotas.FirstOrDefault(c => Calculos.Igual(c.Handle, h))?.CajaTexto ?? default;

        /// <summary>Lo mínimo (perpendicular al tramo a-b) para que la caja deje de tocar el tramo, + margen.</summary>
        public static (double dx, double dy) Apartar(Caja c, double ax, double ay, double bx, double by, double margen)
        {
            double L = Math.Sqrt((bx - ax) * (bx - ax) + (by - ay) * (by - ay));
            if (L < 1e-9) return (0, 0);
            double nx = -(by - ay) / L, ny = (bx - ax) / L;
            var d = new[] { (c.X0, c.Y0), (c.X1, c.Y0), (c.X0, c.Y1), (c.X1, c.Y1) }.Select(p => (p.Item1 - ax) * nx + (p.Item2 - ay) * ny).ToList();
            double sube = -d.Min() + margen, baja = d.Max() + margen;           // pasar todo a un lado u otro
            return sube <= baja ? (nx * sube, ny * sube) : (-nx * baja, -ny * baja);
        }

        /// <summary>Lo mínimo (en x o en y) para que la caja `a` deje de tapar a `b`, + margen.</summary>
        public static (double dx, double dy) Separar(Caja a, Caja b, double margen)
        {
            var op = new[] { (b.X1 - a.X0 + margen, 0.0), (-(a.X1 - b.X0 + margen), 0.0), (0.0, b.Y1 - a.Y0 + margen), (0.0, -(a.Y1 - b.Y0 + margen)) };
            return op.OrderBy(o => Math.Abs(o.Item1) + Math.Abs(o.Item2)).First();
        }

        private static bool Cruza(double ax, double ay, double bx, double by, double cx, double cy, double dx, double dy)
        {
            double d1 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax), d2 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax);
            double d3 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx), d4 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx);
            return d1 * d2 < 0 && d3 * d4 < 0;
        }

        private static string Desc(Modelo m, Guia g)
        {
            var t = m.Textos.FirstOrDefault(x => Calculos.Igual(x.Handle, g.TextoHandle) || Calculos.Igual(x.Handle, g.Handle));
            return t == null ? "" : $"de «{CambiosTexto.Corto(t.Contenido)}»";
        }

        private static string F(double v) => CambiosTexto.F(v);
    }
}
