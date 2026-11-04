using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;

// ============================================================================
//  PdfCadMcp — servidor MCP por stdio (JSON-RPC 2.0, una línea por mensaje).
//  Es la capa de PRESENTACIÓN: publica el catálogo de Contratos y reenvía cada
//  llamada al plugin. No tiene reglas propias: las reglas viven en el plugin.
//
//    PdfCadMcp.exe [--perfil completo|basico] [--origen claude|qwen|app]
//
//  Claude Code:  claude mcp add pdfcad-civil3d -- "<ruta>\PdfCadMcp.exe" --origen claude
//  App (Qwen):   lanza el mismo .exe con --perfil basico --origen qwen
//  stdout es SOLO del protocolo; los diagnósticos van a stderr.
// ============================================================================

namespace PdfCadMcp
{
    internal static class Program
    {
        private const string VERSION_MCP = "2025-06-18";
        private static readonly string[] VERSIONES = { "2025-06-18", "2025-03-26", "2024-11-05" };

        internal const string INSTRUCCIONES =
            "Herramientas de un dibujo de Civil 3D abierto (redes de utilidad de PDF-a-CAD). Reglas:\n" +
            "1) Unidades imperiales: cotas y largos en pies, diámetros en pulgadas.\n" +
            "2) Los números los da la herramienta: no calcular ni inventar cifras.\n" +
            "3) Identificar cada elemento por su NOMBRE (argumento 'elemento', p. ej. «ELECTRICO-4 - (1)»): el plugin lo busca. Nunca pedir el handle al usuario.\n" +
            "4) Ante una pregunta sobre el dibujo, consultarlo con las herramientas antes de responder (textos: buscar_textos); no preguntar al usuario lo que se puede buscar.\n" +
            "5) Empezar por 'estado' y 'resumen_modelo'; pedir detalle solo de lo necesario (filtros y 'limite').\n" +
            "6) Cambios: proponer_cambio → mostrar antes/después, consecuencias y advertencias → confirmar_cambio SOLO si el usuario dice que sí. «Súbela/bájala N pies» = 'sumar'.\n" +
            "7) Si algo no está en los datos, decirlo; no suponer.\n" +
            "8) Hablar con el usuario en lenguaje simple: sin handles, nombres de herramientas ni JSON.";

        private static string _perfil = Catalogo.PERFIL_COMPLETO;
        private static string _origen = "claude";

        private static int Main(string[] args)
        {
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == "--perfil") _perfil = args[i + 1];
                if (args[i] == "--origen") _origen = args[i + 1];
            }
            if (args.Contains("--probar")) return Probar();

            var utf8 = new UTF8Encoding(false);
            var entrada = new StreamReader(Console.OpenStandardInput(), utf8);
            var salida = new StreamWriter(Console.OpenStandardOutput(), utf8) { AutoFlush = true, NewLine = "\n" };
            using (var civil = new ClienteCivil3D())
            {
                string linea;
                while ((linea = entrada.ReadLine()) != null)
                {
                    if (linea.Trim().Length == 0) continue;
                    JsonNode respuesta;
                    try { respuesta = Atender(JsonNode.Parse(linea) as JsonObject, civil); }
                    catch (JsonException) { respuesta = Error(null, -32700, "JSON inválido."); }
                    catch (Exception ex) { Console.Error.WriteLine(ex); respuesta = Error(null, -32603, ex.Message); }
                    if (respuesta != null) salida.WriteLine(respuesta.ToJsonString());
                }
            }
            return 0;
        }

        /// <summary>Atiende un mensaje JSON-RPC; null = notificación (sin respuesta).</summary>
        internal static JsonNode Atender(JsonObject msg, ClienteCivil3D civil)
        {
            if (msg == null) return Error(null, -32600, "Mensaje no válido.");
            JsonNode id = msg["id"]?.DeepClone();
            string metodo = msg["method"]?.GetValue<string>() ?? "";
            var prm = msg["params"] as JsonObject ?? new JsonObject();
            if (id == null) return null;   // notificaciones (notifications/initialized, cancelled…)

            switch (metodo)
            {
                case "initialize":
                    string pedida = prm["protocolVersion"]?.GetValue<string>();
                    return Bien(id, new JsonObject
                    {
                        ["protocolVersion"] = VERSIONES.Contains(pedida) ? pedida : VERSION_MCP,
                        ["capabilities"] = new JsonObject { ["tools"] = new JsonObject { ["listChanged"] = false } },
                        ["serverInfo"] = new JsonObject { ["name"] = "pdfcad-civil3d", ["version"] = Protocolo.VERSION.ToString() },
                        ["instructions"] = INSTRUCCIONES,
                    });
                case "ping":
                    return Bien(id, new JsonObject());
                case "tools/list":
                    var lista = new JsonArray();
                    foreach (Herramienta h in Catalogo.DelPerfil(_perfil))
                        lista.Add(new JsonObject
                        {
                            ["name"] = h.Nombre,
                            ["description"] = h.Descripcion,
                            ["inputSchema"] = JsonNode.Parse(h.Esquema),
                            ["annotations"] = new JsonObject
                            {
                                ["readOnlyHint"] = h.Tipo == TipoHerramienta.Lectura,
                                ["destructiveHint"] = h.Nombre == "confirmar_cambio",
                            },
                        });
                    return Bien(id, new JsonObject { ["tools"] = lista });
                case "tools/call":
                    return Bien(id, Llamar(prm, civil));
                default:
                    return Error(id, -32601, "Método no soportado: " + metodo);
            }
        }

        private static JsonObject Llamar(JsonObject prm, ClienteCivil3D civil)
        {
            string nombre = prm["name"]?.GetValue<string>() ?? "";
            Respuesta r;
            if (!Catalogo.Permitida(_perfil, nombre))
                r = Respuesta.Mal("", $"Herramienta «{nombre}» no disponible en el perfil {_perfil}.");
            else
                r = civil.Enviar(new Pedido
                {
                    Id = Guid.NewGuid().ToString("N"), Herramienta = nombre,
                    Args = prm["arguments"] as JsonObject ?? new JsonObject(),
                    Origen = _origen, Usuario = Environment.UserName, Perfil = _perfil,
                });
            string texto = r.Ok ? (r.Datos?.ToJsonString() ?? "{}") : r.Error;
            return new JsonObject
            {
                ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = texto }),
                ["isError"] = !r.Ok,
            };
        }

        private static JsonObject Bien(JsonNode id, JsonNode resultado) =>
            new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["result"] = resultado };

        private static JsonObject Error(JsonNode id, int codigo, string mensaje) =>
            new JsonObject
            {
                ["jsonrpc"] = "2.0", ["id"] = id,
                ["error"] = new JsonObject { ["code"] = codigo, ["message"] = mensaje },
            };

        /// <summary>Diagnóstico para el usuario: ¿hay un Civil 3D con la IA encendida?</summary>
        private static int Probar()
        {
            string[] t = ClienteCivil3D.Disponibles();
            Console.WriteLine(t.Length == 0 ? ClienteCivil3D.SIN_CONEXION : "Tuberías: " + string.Join(", ", t));
            if (t.Length == 0) return 1;
            using (var c = new ClienteCivil3D())
            {
                Respuesta r = c.Enviar(new Pedido { Id = "probar", Herramienta = "estado", Origen = "probar", Perfil = _perfil });
                Console.WriteLine(r.Ok ? r.Datos?.ToJsonString() : "Error: " + r.Error);
                return r.Ok ? 0 : 1;
            }
        }
    }
}
