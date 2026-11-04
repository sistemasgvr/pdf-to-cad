using System;
using System.Linq;

// ============================================================================
//  DOMINIO: textos del dibujo (TEXT y MTEXT del espacio modelo), ya sin códigos de
//  formato. La IA los consulta con buscar_textos: «¿qué dice el texto?», «¿hay una
//  nota que diga HOLA?», «¿dónde está el rótulo de la calle?».
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class TextoDibujo
    {
        public string Handle;
        public string Tipo;          // TEXT | MTEXT
        public string Contenido;     // texto plano
        public string Capa;
        public double X, Y, Altura;
    }

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
