using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

// ============================================================================
//  DOMINIO: encontrar un elemento por lo que dice el USUARIO («ELECTRICO-4 - (1)»,
//  «electrico 4 (1)», «la tubería ELECTRICO-4») y no solo por su handle. La IA no
//  tiene que adivinar handles: el plugin resuelve el nombre o explica qué hay.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class Referencia
    {
        public string Handle;
        public string Nombre;
        public bool EsTuberia;
    }

    public static class Referencias
    {
        public const int PARECIDOS_MAX = 6;

        /// <summary>Nombre normalizado por PALABRAS: minúsculas, sin acentos, cada tramo de letras/números
        /// separado por «-» («ELECTRICO-4 - (1)» = «electrico 4 (1)» = «-electrico-4-1-»).</summary>
        public static string Clave(string s)
        {
            var sb = new StringBuilder("-");
            foreach (char ch in (s ?? "").Normalize(NormalizationForm.FormD))
            {
                if (System.Globalization.CharUnicodeInfo.GetUnicodeCategory(ch) == System.Globalization.UnicodeCategory.NonSpacingMark) continue;
                if (char.IsLetterOrDigit(ch)) sb.Append(char.ToLowerInvariant(ch));
                else if (sb[sb.Length - 1] != '-') sb.Append('-');
            }
            if (sb[sb.Length - 1] != '-') sb.Append('-');
            return sb.ToString();
        }

        private static IEnumerable<Referencia> Todas(Modelo m) =>
            m.Tuberias.Select(t => new Referencia { Handle = t.Handle, Nombre = t.Nombre, EsTuberia = true })
             .Concat(m.Estructuras.Select(e => new Referencia { Handle = e.Handle, Nombre = e.Nombre }));

        /// <summary>Handle exacto → nombre exacto (normalizado) → único nombre que lo contiene. Si no, null + error
        /// con los parecidos (para que el usuario elija) en palabras simples.</summary>
        public static Referencia Resolver(Modelo m, string texto, out string error)
        {
            error = null;
            string q = (texto ?? "").Trim();
            if (q.Length == 0) { error = "No se indicó qué elemento."; return null; }
            var todas = Todas(m).ToList();

            var r = todas.FirstOrDefault(x => Calculos.Igual(x.Handle, q));
            if (r != null) return r;
            var tx = m.Textos.FirstOrDefault(x => Calculos.Igual(x.Handle, q));      // un texto, para ir_a
            if (tx != null) return new Referencia { Handle = tx.Handle, Nombre = tx.Contenido };

            string k = Clave(q);
            if (k.Length <= 1) { error = $"No entendí qué elemento es «{q}»."; return null; }
            var exactas = todas.Where(x => Clave(x.Nombre) == k).ToList();
            if (exactas.Count == 1) return exactas[0];
            if (exactas.Count > 1)
            {
                error = $"Hay {exactas.Count} elementos que se llaman «{q}». Indica la red o elígelo en el dibujo.";
                return null;
            }

            var contienen = todas.Where(x => Clave(x.Nombre).Contains(k)).ToList();
            if (contienen.Count == 1) return contienen[0];
            if (contienen.Count > 1)
            {
                error = $"«{q}» puede ser: {Lista(contienen)}. ¿Cuál?";
                return null;
            }

            var parecidos = Parecidos(todas, k);
            error = parecidos.Count == 0
                ? $"No encontré ningún elemento llamado «{q}» en el dibujo."
                : $"No encontré «{q}». ¿Quisiste decir: {Lista(parecidos)}?";
            return null;
        }

        private static string Lista(List<Referencia> rs)
        {
            var nombres = rs.Select(x => x.Nombre).Distinct().Take(PARECIDOS_MAX).ToList();
            string s = string.Join(", ", nombres);
            return rs.Count > nombres.Count ? s + $" (y {rs.Count - nombres.Count} más)" : s;
        }

        /// <summary>Los que comparten el comienzo más largo (al menos 3 letras) con lo pedido.</summary>
        private static List<Referencia> Parecidos(List<Referencia> todas, string k)
        {
            for (int n = Math.Min(k.Length, 13); n >= 4; n--)
            {
                string pre = k.Substring(0, n);
                var rs = todas.Where(x => Clave(x.Nombre).StartsWith(pre, StringComparison.Ordinal)).ToList();
                if (rs.Count > 0) return rs;
            }
            return new List<Referencia>();
        }
    }
}
