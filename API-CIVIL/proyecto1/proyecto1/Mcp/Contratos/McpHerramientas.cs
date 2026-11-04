using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  CATÁLOGO CERRADO de herramientas del MCP (PURO). Una sola fuente: el host lo
//  publica en tools/list y el plugin lo usa para despachar. Descripciones CORTAS
//  (viajan en cada mensaje al modelo: cuestan tokens).
//
//  Perfiles: «completo» (Claude) ve todas; «basico» (modelos locales como Qwen,
//  que eligen peor entre muchas) ve solo las marcadas Basico. Una herramienta
//  nueva se agrega aquí y en el despachador de Aplicación; nada más cambia.
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

        /// <summary>El elemento como lo nombra el usuario: el plugin lo busca (no hace falta el handle).</summary>
        private const string ELEMENTO = "\"elemento\":{\"type\":\"string\",\"description\":\"nombre tal como lo dice el usuario, p. ej. ELECTRICO-4 - (1)\"}";
        private const string SIN_ARGS = "{\"type\":\"object\",\"properties\":{}}";

        public static readonly IReadOnlyList<Herramienta> Todas = new List<Herramienta>
        {
            new Herramienta
            {
                Nombre = "estado", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Dibujo abierto en Civil 3D: nombre, unidades, sistema de coordenadas y cuántas redes hay. Llamar primero.",
                Esquema = SIN_ARGS,
            },
            new Herramienta
            {
                Nombre = "resumen_modelo", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Resumen por red: tipo (gravedad/presión), nº de tuberías y estructuras, largo total (ft), diámetros (in) y capas. Usar antes de pedir detalle.",
                Esquema = "{\"type\":\"object\",\"properties\":{\"red\":{\"type\":\"string\",\"description\":\"Nombre de una red (opcional)\"}}}",
            },
            new Herramienta
            {
                Nombre = "buscar_tuberias", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Tuberías que cumplen los filtros (nombre, red, diámetro, cotas, pendiente). Máx. 'limite' filas; dice cuántas más hay.",
                Esquema = "{\"type\":\"object\",\"properties\":{" +
                          "\"red\":{\"type\":\"string\"},\"capa\":{\"type\":\"string\"}," +
                          "\"diametro_min_in\":{\"type\":\"number\"},\"diametro_max_in\":{\"type\":\"number\"}," +
                          "\"pendiente_max_pct\":{\"type\":\"number\",\"description\":\"p. ej. 0 = contrapendiente o nula\"}," +
                          "\"texto\":{\"type\":\"string\",\"description\":\"busca en nombre, tamaño y descripción\"}," +
                          "\"limite\":{\"type\":\"integer\",\"default\":30}}}",
            },
            new Herramienta
            {
                Nombre = "buscar_estructuras", Tipo = TipoHerramienta.Lectura, Basico = false,
                Descripcion = "Estructuras (buzones/cajas) de gravedad que cumplen los filtros: rim, sump, profundidad. Máx. 'limite'.",
                Esquema = "{\"type\":\"object\",\"properties\":{" +
                          "\"red\":{\"type\":\"string\"},\"texto\":{\"type\":\"string\"}," +
                          "\"profundidad_min_ft\":{\"type\":\"number\"},\"limite\":{\"type\":\"integer\",\"default\":30}}}",
            },
            new Herramienta
            {
                Nombre = "buscar_textos", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Textos del dibujo (TEXT y MTEXT): qué dicen, capa y posición. Sin 'texto' lista todos; con 'texto' busca los que lo contienen.",
                Esquema = "{\"type\":\"object\",\"properties\":{" +
                          "\"texto\":{\"type\":\"string\",\"description\":\"palabras a buscar (opcional)\"}," +
                          "\"capa\":{\"type\":\"string\"},\"limite\":{\"type\":\"integer\",\"default\":30}}}",
            },
            new Herramienta
            {
                Nombre = "detalle_elemento", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Todo lo que se sabe de un elemento (por su nombre): geometría, cotas, conexiones y Property Sets PDFCAD.",
                Esquema = "{\"type\":\"object\",\"properties\":{" + ELEMENTO + ",\"handle\":{\"type\":\"string\"}}}",
            },
            new Herramienta
            {
                Nombre = "ir_a", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Encuadra y resalta en Civil 3D uno o varios elementos (por nombre) para que el usuario los vea.",
                Esquema = "{\"type\":\"object\",\"properties\":{\"elementos\":{\"type\":\"array\",\"items\":{\"type\":\"string\"},\"description\":\"nombres tal como los dice el usuario\"},\"handles\":{\"type\":\"array\",\"items\":{\"type\":\"string\"}}}}",
            },
            new Herramienta
            {
                Nombre = "proponer_cambio", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Prepara un cambio SIN aplicarlo y devuelve id + antes/después + consecuencias. " +
                              "Tipos: cota_inicio | cota_fin (rasante de tubería de gravedad, ft), capa, descripcion. " +
                              "Para subir o bajar una cota usar 'sumar' (ft); para fijarla, 'valor'. " +
                              "Mostrar al usuario y aplicar solo con confirmar_cambio si él acepta.",
                Esquema = "{\"type\":\"object\",\"properties\":{" + ELEMENTO + "," +
                          "\"handle\":{\"type\":\"string\"}," +
                          "\"tipo\":{\"type\":\"string\",\"enum\":[\"cota_inicio\",\"cota_fin\",\"capa\",\"descripcion\"]}," +
                          "\"valor\":{\"type\":\"string\",\"description\":\"cota final en ft, nombre de capa o texto\"}," +
                          "\"sumar\":{\"type\":\"number\",\"description\":\"ft a sumar a la cota actual (negativo = bajar)\"}," +
                          "\"motivo\":{\"type\":\"string\"}},\"required\":[\"tipo\"]}",
            },
            new Herramienta
            {
                Nombre = "confirmar_cambio", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Aplica en Civil 3D un cambio propuesto (id). Solo tras el sí del usuario. Se puede deshacer con U.",
                Esquema = "{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"}},\"required\":[\"id\"]}",
            },
            new Herramienta
            {
                Nombre = "cancelar_cambio", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Descarta un cambio propuesto (id).",
                Esquema = "{\"type\":\"object\",\"properties\":{\"id\":{\"type\":\"string\"}},\"required\":[\"id\"]}",
            },
            new Herramienta
            {
                Nombre = "historial", Tipo = TipoHerramienta.Lectura, Basico = false,
                Descripcion = "Últimos cambios hechos por la IA en este dibujo (quién, cuándo, qué, antes/después).",
                Esquema = "{\"type\":\"object\",\"properties\":{\"limite\":{\"type\":\"integer\",\"default\":20}}}",
            },
        };

        public static Herramienta Buscar(string nombre) =>
            Todas.FirstOrDefault(h => string.Equals(h.Nombre, nombre, StringComparison.OrdinalIgnoreCase));

        public static IEnumerable<Herramienta> DelPerfil(string perfil) =>
            string.Equals(perfil, PERFIL_BASICO, StringComparison.OrdinalIgnoreCase) ? Todas.Where(h => h.Basico) : Todas;

        public static bool Permitida(string perfil, string nombre) =>
            DelPerfil(perfil).Any(h => string.Equals(h.Nombre, nombre, StringComparison.OrdinalIgnoreCase));
    }
}
