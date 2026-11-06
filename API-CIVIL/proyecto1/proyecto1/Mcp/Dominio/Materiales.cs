using System;
using System.Globalization;
using System.Linq;
using System.Text;

// ============================================================================
//  DOMINIO: materiales (PURO). El catálogo de Civil 3D los nombra en inglés
//  («Concrete Pipe») y la app y el usuario en español («Concreto»): sinónimos.
//  Las NORMATIVAS no viven aquí: las revisa la app con su propio validador
//  (`app/ia/civil3d_normativas.py`) y manda al plugin solo lo que hace falta
//  (p. ej. la pendiente objetivo de cada tubería).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public static class Materiales
    {
        private static readonly string[][] SINONIMOS =
        {
            new[] { "concreto", "concrete", "hormigon", "rcp" },
            new[] { "hierro ductil", "ductile iron", "di", "dip" },
            new[] { "hierro fundido", "cast iron", "ci" },
            new[] { "acero", "steel" },
            new[] { "cobre", "copper" },
            new[] { "polietileno", "polyethylene", "hdpe", "pead" },
            new[] { "pvc", "polivinilo", "polyvinyl" },
            new[] { "arcilla vitrificada", "vitrified clay", "vcp", "clay" },
            new[] { "asbesto cemento", "asbestos cement", "acp" },
            new[] { "corrugado", "corrugated", "cmp" },
        };

        /// <summary>¿El texto `a` (material, familia o descripción del catálogo) es del material `b`?</summary>
        public static bool Mismo(string a, string b)
        {
            string x = Plano(a), y = Plano(b);
            if (x.Length == 0 || y.Length == 0) return false;
            if (Palabra(x, y) || Palabra(y, x)) return true;
            foreach (var g in SINONIMOS)
                if (g.Any(s => Palabra(y, s) || y == s) && g.Any(s => Palabra(x, s))) return true;
            return false;
        }

        private static bool Palabra(string texto, string buscado) => (" " + texto + " ").Contains(" " + buscado + " ");

        public static string Plano(string s)
        {
            var sb = new StringBuilder();
            foreach (char ch in (s ?? "").Normalize(NormalizationForm.FormD))
            {
                if (CharUnicodeInfo.GetUnicodeCategory(ch) == UnicodeCategory.NonSpacingMark) continue;
                sb.Append(char.IsLetterOrDigit(ch) ? char.ToLowerInvariant(ch) : ' ');
            }
            return string.Join(" ", sb.ToString().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));
        }

        /// <summary>Número corto («0.5», «12»).</summary>
        public static string F(double v) => Math.Round(v, 2).ToString("0.##", CultureInfo.InvariantCulture);
    }
}
