using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

// ============================================================================
//  CATÁLOGO CERRADO de herramientas del MCP (PURO). Una sola fuente: el host lo
//  publica en tools/list y el plugin lo usa para despachar. Cada TEMA en su
//  archivo (Herramientas*.cs: lecturas, cambios, conflictos); aquí solo se juntan.
//  Descripciones CORTAS (viajan en cada mensaje al modelo: cuestan tokens).
//
//  Perfiles: «completo» (Claude) ve todas; «basico» (modelos locales como Qwen,
//  que eligen peor entre muchas) ve solo las marcadas Basico.
//  Herramienta nueva: su entrada en el archivo del tema + su caso registrado en el
//  despachador (`Despachador.Registrar…`). La prueba del catálogo falla si falta
//  uno de los dos.
// ============================================================================

namespace Civil3DBasico.Mcp.Contratos
{
    public enum TipoHerramienta { Lectura, Cambio }

    public sealed class Herramienta
    {
        public string Nombre;
        public string Descripcion;
        public string Esquema;      // JSON Schema de los argumentos
        public TipoHerramienta Tipo;
        public bool Basico;
    }

    public static class Catalogo
    {
        public const string PERFIL_COMPLETO = "completo";
        public const string PERFIL_BASICO = "basico";

        public static readonly IReadOnlyList<Herramienta> Todas =
            HerramientasLectura.Lista.Concat(HerramientasCambios.Lista).Concat(HerramientasConflictos.Lista)
                               .Concat(HerramientasPlano.Lista).ToList();

        public static Herramienta Buscar(string nombre) =>
            Todas.FirstOrDefault(h => string.Equals(h.Nombre, nombre, StringComparison.OrdinalIgnoreCase));

        public static IEnumerable<Herramienta> DelPerfil(string perfil) =>
            string.Equals(perfil, PERFIL_BASICO, StringComparison.OrdinalIgnoreCase) ? Todas.Where(h => h.Basico) : Todas;

        public static bool Permitida(string perfil, string nombre) =>
            DelPerfil(perfil).Any(h => string.Equals(h.Nombre, nombre, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>Escribe los JSON Schema sin cadenas a mano: E.Obj(E.Texto("red"), E.Num("x", "…")).</summary>
    internal static class E
    {
        public static string Obj(params string[] props) => Req(null, props);

        public static string Req(string[] requeridos, params string[] props) =>
            "{\"type\":\"object\",\"properties\":{" + string.Join(",", props) + "}" +
            (requeridos == null || requeridos.Length == 0 ? "" : ",\"required\":[" + string.Join(",", requeridos.Select(J)) + "]") + "}";

        public static string Texto(string n, string d = null) => P(n, "\"type\":\"string\"", d);
        public static string Num(string n, string d = null) => P(n, "\"type\":\"number\"", d);
        public static string Ent(string n, int defecto, string d = null) => P(n, $"\"type\":\"integer\",\"default\":{defecto}", d);
        public static string Lista(string n, string d = null) => P(n, "\"type\":\"array\",\"items\":{\"type\":\"string\"}", d);
        public static string ListaObj(string n, string d = null) => P(n, "\"type\":\"array\",\"items\":{\"type\":\"object\"}", d);
        public static string Opciones(string n, string[] vals, string d = null) =>
            P(n, "\"type\":\"string\",\"enum\":[" + string.Join(",", vals.Select(J)) + "]", d);
        public static string Objeto(string n, string d = null) => P(n, "\"type\":\"object\"", d);

        /// <summary>El elemento como lo nombra el usuario: el plugin lo busca (no hace falta el handle).</summary>
        public static string Elemento(string d = "nombre tal como lo dice el usuario, p. ej. ELECTRICO-4 - (1)") => Texto("elemento", d);
        public static string Elementos() => Lista("elementos", "tuberías o utilidades (AGUA-20 = todas sus tuberías)");
        public static string Limite(int defecto = 30) => Ent("limite", defecto);
        public static string Motivo() => Texto("motivo");
        /// <summary>Separaciones de la normativa de la APP (las pone la app, el modelo no las ve).</summary>
        public static string Reglas() => ListaObj("reglas", "separaciones verticales de la normativa de la app: [{a, b, sep_v_ft, encima, debajo, fuente}]");

        private static string P(string n, string tipo, string d) =>
            J(n) + ":{" + tipo + (string.IsNullOrEmpty(d) ? "" : ",\"description\":" + J(d)) + "}";

        private static string J(string s) => JsonSerializer.Serialize(s);
    }
}
