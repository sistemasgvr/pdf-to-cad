using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

// ============================================================================
//  CONTRATOS del MCP (PUROS, sin Autodesk). Los comparten el plugin (servidor de
//  la tubería con nombre) y el host MCP (PdfCadMcp.exe, proceso aparte).
//
//  Protocolo de la tubería: UNA línea JSON por pedido y una por respuesta (UTF-8).
//    pedido    {"v":1,"id":"…","herramienta":"resumen_modelo","args":{…},"origen":"claude"}
//    respuesta {"v":1,"id":"…","ok":true,"datos":{…}}  |  {"…","ok":false,"error":"…"}
//  Regla de versiones: solo se AGREGAN campos y herramientas; nunca se cambia el
//  significado de uno existente. Un cambio incompatible sube VERSION.
// ============================================================================

namespace Civil3DBasico.Mcp.Contratos
{
    public static class Protocolo
    {
        public const int VERSION = 1;

        /// <summary>Prefijo de la tubería; se le suma el id del proceso de AutoCAD
        /// (puede haber varias instancias abiertas).</summary>
        public const string PREFIJO_TUBERIA = "pdfcad-civil3d-";

        public static readonly JsonSerializerOptions Json = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            WriteIndented = false,
            IncludeFields = true,                         // el dominio usa campos públicos
            Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        };
    }

    public sealed class Pedido
    {
        public int V { get; set; } = Protocolo.VERSION;
        public string Id { get; set; } = "";
        public string Herramienta { get; set; } = "";
        public JsonObject Args { get; set; } = new JsonObject();
        /// <summary>Quién lo pide: «claude», «qwen», «app»… Va al registro de cambios.</summary>
        public string Origen { get; set; } = "";
        /// <summary>Usuario del sistema que lanzó el cliente (para el registro).</summary>
        public string Usuario { get; set; } = "";
        /// <summary>Perfil de herramientas del cliente (Catalogo.PERFIL_*); el plugin
        /// también lo revisa, así un cliente no puede saltarse su perfil.</summary>
        public string Perfil { get; set; } = "";
    }

    public sealed class Respuesta
    {
        public int V { get; set; } = Protocolo.VERSION;
        public string Id { get; set; } = "";
        public bool Ok { get; set; }
        public JsonNode Datos { get; set; }
        public string Error { get; set; }

        public static Respuesta Bien(string id, object datos) => new Respuesta
        {
            Id = id, Ok = true,
            Datos = datos == null ? null : JsonSerializer.SerializeToNode(datos, datos.GetType(), Protocolo.Json),
        };

        public static Respuesta Mal(string id, string error) => new Respuesta { Id = id, Ok = false, Error = error };
    }

    /// <summary>Lectura segura de argumentos (la IA puede mandar números como texto).</summary>
    public static class Args
    {
        public static string Texto(JsonObject a, string clave, string defecto = null)
        {
            if (a == null || !a.TryGetPropertyValue(clave, out JsonNode n) || n == null) return defecto;
            return n is JsonValue v && v.TryGetValue(out string s) ? s : n.ToJsonString().Trim('"');
        }

        public static double? Numero(JsonObject a, string clave)
        {
            if (a == null || !a.TryGetPropertyValue(clave, out JsonNode n) || n == null) return null;
            if (n is JsonValue v)
            {
                if (v.TryGetValue(out double d)) return d;
                if (v.TryGetValue(out string s) &&
                    double.TryParse(s.Replace(',', '.'), System.Globalization.NumberStyles.Float,
                                    System.Globalization.CultureInfo.InvariantCulture, out d)) return d;
            }
            return null;
        }

        public static int Entero(JsonObject a, string clave, int defecto, int min, int max)
        {
            double? d = Numero(a, clave);
            int v = d.HasValue ? (int)Math.Round(d.Value) : defecto;
            return Math.Max(min, Math.Min(max, v));
        }

        public static List<string> Lista(JsonObject a, string clave)
        {
            var r = new List<string>();
            if (a == null || !a.TryGetPropertyValue(clave, out JsonNode n) || n == null) return r;
            if (n is JsonArray arr) { foreach (var x in arr) if (x != null) r.Add(x.ToString()); }
            else r.Add(n.ToString());
            return r;
        }
    }
}
