using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// ============================================================================
//  DOMINIO: cambios de ANOTACIONES (PURO): textos y rótulos (cambiar o quitar una
//  parte, mover, altura, máscara), cotas (crear o corregir estilo, decimales,
//  flecha, altura, texto) y borrar guías sueltas. Mismo flujo: proponer → el
//  usuario aplica (un paso de U).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public static class TiposTexto
    {
        public const string TEXTO = "texto";                 // proponer_texto / arreglo de la revisión
        public const string BORRAR = "borrar_anotacion";
        public const string COTA = "cota";
    }

    /// <summary>Lo que se le hace a UN texto (TEXT, MTEXT, MLEADER) o al texto de una cota.</summary>
    public sealed class EdicionTexto
    {
        public string Handle;
        public bool EsCota;
        public List<(string de, string a)> Reemplazos = new List<(string, string)>();
        public double Dx, Dy;
        public double? Altura;
        public bool? Mascara;
    }

    public sealed class CambioTexto : CambioPropuesto
    {
        public List<EdicionTexto> Ediciones = new List<EdicionTexto>();
        public override string HuellaDe(Modelo m) => AnotacionesHuella.De(m, Ediciones.Select(e => e.Handle));
    }

    public sealed class CambioBorrar : CambioPropuesto
    {
        public List<string> Borrar = new List<string>();
        public override string HuellaDe(Modelo m) => AnotacionesHuella.De(m, Borrar);
    }

    public sealed class CambioCota : CambioPropuesto
    {
        public bool Crear;
        public double X1, Y1, X2, Y2, Desplazamiento;          // crear: alineada de P1 a P2, a esa distancia
        public List<string> Cotas = new List<string>();        // cambiar: esas cotas
        public string Estilo;
        public int? Decimales;
        public double? Flecha, AlturaTexto;
        public string TextoNuevo;                              // null = no cambia; "" = la medida real
        public override string HuellaDe(Modelo m) => Crear ? "" : AnotacionesHuella.De(m, Cotas);
    }

    public static class AnotacionesHuella
    {
        public static string De(Modelo m, IEnumerable<string> handles) =>
            string.Join("|", handles.Select(h =>
            {
                var t = m.Textos.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                if (t != null) return $"{h}:{t.Contenido}@{R(t.X)},{R(t.Y)}/{R(t.Altura)}";
                var c = m.Cotas.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                if (c != null) return $"{h}:{c.Texto}@{R(c.CajaTexto.Cx)},{R(c.CajaTexto.Cy)}/{c.Estilo}/{c.Decimales}";
                var g = m.Guias.FirstOrDefault(x => Calculos.Igual(x.Handle, h));
                return g != null ? $"{h}:guia{g.Vertices.Count}" : h + ":-";
            }));

        private static string R(double v) => Math.Round(v, 3).ToString(CultureInfo.InvariantCulture);
    }

    public static class CambiosTexto
    {
        public const int MAX_TEXTOS = 100;

        /// <summary>Textos a cambiar: buscar «de» y poner «a» («a» vacío = quitar), mover (dx, dy), altura, máscara.</summary>
        public static CambioTexto Editar(Modelo m, List<TextoDibujo> textos, string de, string a, double dx, double dy,
                                         double? altura, bool? mascara, out string error)
        {
            error = null;
            if (textos.Count == 0) { error = "No encontré esos textos."; return null; }
            if (textos.Count > MAX_TEXTOS) { error = $"Son {textos.Count} textos: afina la búsqueda (máx. {MAX_TEXTOS} por cambio)."; return null; }
            bool reemplaza = !string.IsNullOrEmpty(de);
            if (!reemplaza && Math.Abs(dx) < 1e-9 && Math.Abs(dy) < 1e-9 && !altura.HasValue && !mascara.HasValue)
            { error = "Dime qué cambiar: 'reemplazar' (y 'por'), mover ('dx'/'dy'), 'altura' o 'mascara'."; return null; }
            if (altura.HasValue && (altura.Value <= 0 || altura.Value > 100)) { error = $"Altura no válida: {altura.Value}."; return null; }
            var cp = new CambioTexto { Tipo = TiposTexto.TEXTO };
            var antes = new List<string>(); var despues = new List<string>(); var sin = new List<string>();
            foreach (var t in textos)
            {
                string nuevo = t.Contenido;
                if (reemplaza)
                {
                    int i = (t.Contenido ?? "").IndexOf(de, StringComparison.OrdinalIgnoreCase);
                    if (i < 0) { sin.Add(Corto(t.Contenido)); continue; }
                    nuevo = Limpio(t.Contenido.Remove(i, de.Length).Insert(i, a ?? ""));
                }
                cp.Ediciones.Add(new EdicionTexto
                {
                    Handle = t.Handle, Dx = dx, Dy = dy, Altura = altura, Mascara = mascara,
                    Reemplazos = reemplaza ? new List<(string, string)> { (de, a ?? "") } : new List<(string, string)>(),
                });
                cp.Handles.Add(t.Handle);
                antes.Add(Corto(t.Contenido)); despues.Add(Corto(nuevo));
            }
            if (cp.Ediciones.Count == 0) { error = $"Ninguno de esos textos contiene «{de}»."; return null; }
            cp.Handle = cp.Ediciones[0].Handle;
            cp.Elemento = cp.Ediciones.Count == 1 ? $"Texto «{antes[0]}»" : $"{cp.Ediciones.Count} textos";
            cp.Antes = reemplaza ? string.Join(" · ", antes.Distinct().Take(3)) : "";
            cp.Despues = reemplaza ? string.Join(" · ", despues.Distinct().Take(3)) : "";
            if (reemplaza) cp.Consecuencias.Add(string.IsNullOrEmpty(a) ? $"Se quita «{de}» de {cp.Ediciones.Count} texto(s)." : $"«{de}» → «{a}» en {cp.Ediciones.Count} texto(s).");
            if (Math.Abs(dx) > 1e-9 || Math.Abs(dy) > 1e-9) cp.Consecuencias.Add($"Se mueve(n) {F(Math.Sqrt(dx * dx + dy * dy))} (Δx {F(dx)}, Δy {F(dy)}).");
            if (altura.HasValue) cp.Consecuencias.Add($"Altura del texto: {F(altura.Value)}.");
            if (mascara == true) cp.Consecuencias.Add("Fondo (máscara) que tapa lo que hay debajo: se lee sobre tramas y líneas.");
            if (sin.Count > 0) cp.Advertencias.Add($"No contienen «{de}» (no se tocan): {string.Join(", ", sin.Take(4))}.");
            if (mascara == true && textos.Any(t => t.Tipo == "TEXT")) cp.Advertencias.Add("Los TEXT de una línea no admiten máscara: solo MTEXT y MLEADER.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        /// <summary>«15.0 ft ALONG BW» sin «ALONG BW» → «15.0 ft» (sin espacios dobles ni en los bordes).</summary>
        public static string Limpio(string s) => string.Join(" ", (s ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));

        public static CambioCota Crear(double x1, double y1, double x2, double y2, double desp, string estilo, out string error)
        {
            error = null;
            double L = Math.Sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
            if (L < 1e-6) { error = "Los dos puntos de la cota son el mismo."; return null; }
            var cp = new CambioCota
            {
                Tipo = TiposTexto.COTA, Crear = true, X1 = x1, Y1 = y1, X2 = x2, Y2 = y2, Desplazamiento = desp, Estilo = estilo,
                Elemento = "Cota nueva", Antes = "", Despues = $"{F(L)}",
            };
            cp.Consecuencias.Add($"Cota alineada de ({F(x1)}, {F(y1)}) a ({F(x2)}, {F(y2)}): mide {F(L)}, a {F(desp)} de la línea" +
                                 (string.IsNullOrWhiteSpace(estilo) ? " (estilo actual)." : $", estilo «{estilo}»."));
            return cp;
        }

        public static CambioCota Cambiar(Modelo m, List<Cota> cotas, string estilo, int? dec, double? flecha, double? altura,
                                         string texto, out string error)
        {
            error = null;
            if (cotas.Count == 0) { error = "No encontré esas cotas."; return null; }
            if (estilo == null && !dec.HasValue && !flecha.HasValue && !altura.HasValue && texto == null)
            { error = "Dime qué cambiar: 'estilo', 'decimales', 'flecha', 'altura_texto' o 'texto' (vacío = la medida real)."; return null; }
            if (dec.HasValue && (dec.Value < 0 || dec.Value > 8)) { error = "Decimales entre 0 y 8."; return null; }
            var cp = new CambioCota
            {
                Tipo = TiposTexto.COTA, Cotas = cotas.Select(c => c.Handle).ToList(), Estilo = estilo, Decimales = dec,
                Flecha = flecha, AlturaTexto = altura, TextoNuevo = texto, Handle = cotas[0].Handle,
                Elemento = cotas.Count == 1 ? $"Cota «{cotas[0].Texto}»" : $"{cotas.Count} cotas",
            };
            cp.Handles.AddRange(cp.Cotas);
            var a = new List<string>(); var d = new List<string>();
            if (estilo != null) { a.Add("estilo " + string.Join("/", cotas.Select(c => c.Estilo).Distinct().Take(2))); d.Add("estilo " + estilo); }
            if (dec.HasValue) { a.Add("decimales " + string.Join("/", cotas.Select(c => c.Decimales).Distinct().Take(2))); d.Add("decimales " + dec); }
            if (flecha.HasValue) { a.Add("flecha " + string.Join("/", cotas.Select(c => F(c.Flecha)).Distinct().Take(2))); d.Add("flecha " + F(flecha.Value)); }
            if (altura.HasValue) { a.Add("texto " + string.Join("/", cotas.Select(c => F(c.AlturaTexto)).Distinct().Take(2))); d.Add("texto " + F(altura.Value)); }
            if (texto != null) { a.Add("«" + string.Join("/", cotas.Select(c => c.Texto).Distinct().Take(2)) + "»"); d.Add(texto.Length == 0 ? "la medida real" : "«" + texto + "»"); }
            cp.Antes = string.Join(", ", a); cp.Despues = string.Join(", ", d);
            if (texto == null && cotas.Any(c => !string.IsNullOrEmpty(c.Texto) && !c.Texto.Contains(F(c.Medida))))
                cp.Advertencias.Add("Alguna de estas cotas tiene el texto escrito a mano (no muestra su medida real).");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        public static string Corto(string s) => (s ?? "").Length <= 40 ? s ?? "" : s.Substring(0, 40) + "…";
        public static string F(double v) => Math.Round(v, 2).ToString("0.##", CultureInfo.InvariantCulture);
    }
}
