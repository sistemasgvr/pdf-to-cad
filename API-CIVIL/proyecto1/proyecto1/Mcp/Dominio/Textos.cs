using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: las ANOTACIONES del dibujo (PURO): textos (TEXT, MTEXT y el texto de
//  los MLEADER, ya sin códigos de formato), guías (LEADER/MLEADER), cotas y
//  tramas, con sus cajas en planta. Las usan buscar_textos, buscar_cotas y la
//  revisión del plano (RevisionPlano).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    /// <summary>Caja en planta (ejes alineados).</summary>
    public struct Caja
    {
        public double X0, Y0, X1, Y1;
        public Caja(double x0, double y0, double x1, double y1) { X0 = Math.Min(x0, x1); Y0 = Math.Min(y0, y1); X1 = Math.Max(x0, x1); Y1 = Math.Max(y0, y1); }
        public double Ancho => X1 - X0;
        public double Alto => Y1 - Y0;
        public double Area => Math.Max(Ancho, 0) * Math.Max(Alto, 0);
        public double Cx => (X0 + X1) / 2;
        public double Cy => (Y0 + Y1) / 2;
        public bool Valida => X1 > X0 && Y1 > Y0;
        public Caja Encoger(double f) { double dx = Ancho * f / 2, dy = Alto * f / 2; return new Caja(X0 + dx, Y0 + dy, X1 - dx, Y1 - dy); }
        public Caja Mover(double dx, double dy) => new Caja(X0 + dx, Y0 + dy, X1 + dx, Y1 + dy);
        public bool Contiene(double x, double y) => x >= X0 && x <= X1 && y >= Y0 && y <= Y1;

        public double Solape(Caja o)
        {
            double w = Math.Min(X1, o.X1) - Math.Max(X0, o.X0), h = Math.Min(Y1, o.Y1) - Math.Max(Y0, o.Y0);
            return w > 0 && h > 0 ? w * h : 0.0;
        }

        /// <summary>¿El segmento a-b pasa por la caja? (Liang–Barsky)</summary>
        public bool Corta(double ax, double ay, double bx, double by)
        {
            double t0 = 0, t1 = 1, dx = bx - ax, dy = by - ay;
            foreach (var (p, q) in new[] { (-dx, ax - X0), (dx, X1 - ax), (-dy, ay - Y0), (dy, Y1 - ay) })
            {
                if (Math.Abs(p) < 1e-12) { if (q < 0) return false; continue; }
                double r = q / p;
                if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; }
                else { if (r < t0) return false; if (r < t1) t1 = r; }
            }
            return t0 <= t1;
        }
    }

    public sealed class TextoDibujo
    {
        public string Handle;
        public string Tipo;          // TEXT | MTEXT | MLEADER
        public string Contenido;     // texto plano
        public string Capa;
        public double X, Y, Altura;
        public Caja Caja;            // en planta
        public bool Mascara;         // tiene fondo (máscara) que tapa lo de abajo
    }

    /// <summary>Guía (LEADER o MLEADER): sus tramos desde la flecha.</summary>
    public sealed class Guia
    {
        public string Handle, Tipo, Capa;
        public List<(double x, double y)> Vertices = new List<(double, double)>();   // [0] = la flecha
        public bool ConTexto;                // tiene su texto (anotación del LEADER o contenido del MLEADER)
        public string TextoHandle;           // el texto que lleva (el MLEADER es su propio texto)
    }

    public sealed class Cota
    {
        public string Handle, Tipo, Capa, Estilo, Texto;
        public double Medida, AlturaTexto, Flecha;
        public int Decimales;
        public Caja CajaTexto;
        public (double x, double y) A, B;    // la línea de cota
    }

    public sealed class Trama { public string Handle, Capa, Patron; public Caja Caja; }

    public sealed class FiltroTextos
    {
        public string Texto, Capa;

        public bool Cumple(TextoDibujo t)
        {
            if (!string.IsNullOrEmpty(Capa) && !Calculos.Contiene(t.Capa, Capa)) return false;
            if (string.IsNullOrEmpty(Texto)) return true;
            // por palabras: «hola mundo» encuentra «HOLA, MUNDO»; sin acentos ni mayúsculas
            string k = Referencias.Clave(t.Contenido);
            return Referencias.Clave(Texto).Trim('-').Split('-').All(w => w.Length == 0 || k.Contains(w));
        }
    }
}
