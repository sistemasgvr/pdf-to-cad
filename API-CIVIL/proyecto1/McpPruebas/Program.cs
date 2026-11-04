using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;
using Civil3DBasico.Mcp.Infraestructura;

// Pruebas del MCP sin Civil 3D:  dotnet run -c Release   (desde McpPruebas/)
// La de punta a punta necesita PdfCadMcp compilado:  dotnet build -c Release ../PdfCadMcp

internal static class Program
{
    private static int _ok, _mal;

    private static void Es(bool cond, string que)
    {
        if (cond) _ok++; else { _mal++; Console.WriteLine("  FALLA: " + que); }
    }

    private static int Main()
    {
        Dominio();
        Despachador_();
        Perfiles();
        PuntaAPunta();
        Console.WriteLine($"\n{_ok} correctas, {_mal} fallas");
        return _mal == 0 ? 0 : 1;
    }

    // ------------------------------------------------------------ dobles

    internal sealed class LectorFalso : IModeloLector
    {
        public Modelo M = Ejemplo();
        public HashSet<string> Capas = new HashSet<string> { "C-SSWR-PIPE" };
        public EstadoDibujo Estado() => new EstadoDibujo { Dibujo = "prueba.dwg", Unidades = "Foot", RedesGravedad = 1 };
        public Modelo Leer() => M;
        public Dictionary<string, object> Detalle(string h) => M.Tuberias.Any(t => t.Handle == h) ? new Dictionary<string, object> { ["capa"] = "x" } : null;
        public bool CapaExiste(string c) => Capas.Contains(c);
    }

    internal sealed class EditorFalso : IEditorDibujo
    {
        public LectorFalso L; public List<CambioPropuesto> Aplicados = new List<CambioPropuesto>();
        public void Aplicar(CambioPropuesto c)
        {
            Aplicados.Add(c);
            var t = L.M.Tuberias.First(x => x.Handle == c.Handle);
            if (c.Tipo == TiposCambio.COTA_INICIO) t.CotaIni = double.Parse(c.Despues, System.Globalization.CultureInfo.InvariantCulture);
            if (c.Tipo == TiposCambio.CAPA) t.Capa = c.Despues;
        }
        public int IrA(IReadOnlyList<string> h) => h.Count(x => L.M.Tuberias.Any(t => t.Handle == x));
    }

    internal sealed class RegistroFalso : IRegistroCambios
    {
        public List<RegistroCambio> R = new List<RegistroCambio>();
        public void Anotar(RegistroCambio r) => R.Add(r);
        public List<RegistroCambio> Ultimos(int n) => Enumerable.Reverse(R).Take(n).ToList();
    }

    private static Modelo Ejemplo()
    {
        var m = new Modelo();
        m.Estructuras.Add(new Estructura { Handle = "S1", Nombre = "MH-1", Red = "SEWER", Rim = 110, Sump = 100, Conexiones = 1 });
        m.Estructuras.Add(new Estructura { Handle = "S2", Nombre = "MH-2", Red = "SEWER", Rim = 108, Sump = 98, Conexiones = 1 });
        m.Tuberias.Add(new Tuberia
        {
            Handle = "A1", Nombre = "P-1", Red = "SEWER", TipoRed = TipoRed.Gravedad, Capa = "C-SSWR-PIPE", Tamano = "8 in",
            DiametroIn = 8, LargoFt = 100, CotaIni = 100, CotaFin = 99, PendientePct = 1, EstructuraIni = "S1", EstructuraFin = "S2",
        });
        for (int i = 0; i < 50; i++)
            m.Tuberias.Add(new Tuberia
            {
                Handle = "B" + i, Nombre = "W-" + i, Red = "WATER", TipoRed = TipoRed.Presion, Capa = "C-WATR-PIPE",
                DiametroIn = i % 2 == 0 ? 8 : 12, LargoFt = 20, CotaIni = 95, CotaFin = 95,
            });
        return m;
    }

    private static (Despachador d, LectorFalso l, EditorFalso e, RegistroFalso r) Armar()
    {
        var l = new LectorFalso(); var e = new EditorFalso { L = l }; var r = new RegistroFalso();
        return (new Despachador(l, e, r), l, e, r);
    }

    private static Respuesta Pedir(Despachador d, string h, string args = "{}", string perfil = "completo") =>
        d.Ejecutar(new Pedido { Id = "1", Herramienta = h, Args = JsonNode.Parse(args).AsObject(), Origen = "prueba", Perfil = perfil });

    // ------------------------------------------------------------ pruebas

    private static void Dominio()
    {
        Console.WriteLine("Dominio");
        var res = Calculos.Resumen(Ejemplo());
        Es(res.Count == 2, "dos redes");
        var w = res.First(r => r.Red == "WATER");
        Es(w.Tipo == "presion" && w.Tuberias == 50 && w.LargoFt == 1000, "resumen agua");
        Es(w.DiametrosIn["8"] == 25 && w.DiametrosIn["12"] == 25, "histograma de diámetros");
        Es(res.First(r => r.Red == "SEWER").ContrapendienteONula == 0, "sin contrapendientes");

        var c = ReglasCambio.Preparar(Ejemplo(), "A1", "cota_fin", "101", null, out string err);
        Es(c != null && c.Advertencias.Any(a => a.Contains("contrapendiente")), "cota que invierte la pendiente avisa");
        Es(c.Advertencias.Any(a => a.Contains("tapa")) == false, "101 no pasa la tapa (108)");
        c = ReglasCambio.Preparar(Ejemplo(), "A1", "cota_fin", "95", null, out err);
        Es(c.Advertencias.Any(a => a.Contains("MH-2")), "bajo el sump de la estructura avisa");
        Es(ReglasCambio.Preparar(Ejemplo(), "B1", "cota_ini", "90", null, out err) == null, "tipo inválido");
        Es(ReglasCambio.Preparar(Ejemplo(), "B1", "cota_inicio", "90", null, out err) == null && err.Contains("gravedad"), "presión no cambia cota");
        Es(ReglasCambio.Preparar(Ejemplo(), "A1", "cota_inicio", "1e9", null, out err) == null, "cota fuera de rango");
        Es(ReglasCambio.Preparar(Ejemplo(), "A1", "capa", "a/b", null, out err) == null, "capa con caracteres prohibidos");
        Es(ReglasCambio.Preparar(Ejemplo(), "ZZ", "capa", "X", null, out err) == null, "handle inexistente");
    }

    private static void Despachador_()
    {
        Console.WriteLine("Despachador");
        var (d, l, e, r) = Armar();
        Respuesta x = Pedir(d, "buscar_tuberias", "{\"red\":\"water\",\"diametro_min_in\":10,\"limite\":5}");
        Es(x.Ok && x.Datos["total"].GetValue<int>() == 25 && x.Datos["mostradas"].GetValue<int>() == 5, "filtro + tope");
        Es(x.Datos["nota"] != null, "avisa que hay más");
        Es(x.Datos["filas"].AsArray()[0].AsArray().Count == x.Datos["columnas"].AsArray().Count, "filas compactas");
        x = Pedir(d, "buscar_tuberias", "{\"diametro_min_in\":\"10\"}");   // número como texto
        Es(x.Ok && x.Datos["total"].GetValue<int>() == 25, "acepta números como texto");
        x = Pedir(d, "resumen_modelo");
        Es(x.Ok && x.Datos["redes"].AsArray().Count == 2, "resumen");
        Es(!Pedir(d, "inventada").Ok, "herramienta desconocida");
        Es(!Pedir(d, "detalle_elemento").Ok, "falta argumento");

        // propuesta → confirmación
        x = Pedir(d, "proponer_cambio", "{\"handle\":\"A1\",\"tipo\":\"cota_inicio\",\"valor\":\"100.5\",\"motivo\":\"m\"}");
        Es(x.Ok && e.Aplicados.Count == 0, "proponer NO aplica");
        string id = x.Datos["id"].GetValue<string>();
        Es(x.Datos["antes"].GetValue<string>() == "100.00" && x.Datos["despues"].GetValue<string>() == "100.50", "antes/después");
        x = Pedir(d, "confirmar_cambio", "{\"id\":\"" + id + "\"}");
        Es(x.Ok && e.Aplicados.Count == 1 && l.M.Tuberias[0].CotaIni == 100.5, "confirmar aplica");
        Es(r.R.Count == 1 && r.R[0].Origen == "prueba" && r.R[0].Antes == "100.00", "queda en el registro");
        Es(!Pedir(d, "confirmar_cambio", "{\"id\":\"" + id + "\"}").Ok, "no se aplica dos veces");

        // el dibujo cambió entre la propuesta y la confirmación
        x = Pedir(d, "proponer_cambio", "{\"handle\":\"A1\",\"tipo\":\"capa\",\"valor\":\"NUEVA\"}");
        Es(x.Datos["consecuencias"].AsArray().Count == 1, "avisa que se crea la capa");
        l.M.Tuberias[0].Capa = "OTRA";
        x = Pedir(d, "confirmar_cambio", "{\"id\":\"" + x.Datos["id"].GetValue<string>() + "\"}");
        Es(!x.Ok && x.Error.Contains("cambió"), "rechaza si el elemento cambió");

        // vencida
        var ahora = DateTime.Now;
        var d2 = new Despachador(l, e, r, () => ahora);
        x = Pedir(d2, "proponer_cambio", "{\"handle\":\"A1\",\"tipo\":\"descripcion\",\"valor\":\"hola\"}");
        ahora = ahora.AddHours(1);
        Es(!Pedir(d2, "confirmar_cambio", "{\"id\":\"" + x.Datos["id"].GetValue<string>() + "\"}").Ok, "propuesta vencida");
        Es(Pedir(d, "historial").Datos["cambios"].AsArray().Count == 1, "historial");
        Es(Pedir(d, "ir_a", "{\"handles\":[\"A1\",\"ZZ\"]}").Datos["encontrados"].GetValue<int>() == 1, "ir_a");
        Nombres();
    }

    /// <summary>El usuario nombra las tuberías como las ve («ELECTRICO-4 - (1)»), nunca por handle.</summary>
    private static void Nombres()
    {
        Console.WriteLine("Nombres");
        var (d, l, e, r) = Armar();
        foreach (var (h, n) in new[] { ("E1", "ELECTRICO-4 - (1)"), ("E2", "ELECTRICO-4 - (11)"), ("E3", "ELECTRICO-41 - (1)") })
            l.M.Tuberias.Add(new Tuberia
            {
                Handle = h, Nombre = n, Red = "ELECTRICO-4", TipoRed = TipoRed.Gravedad, Capa = "C-ELEC",
                DiametroIn = 4, LargoFt = 50, CotaIni = 90, CotaFin = 89,
            });
        foreach (string q in new[] { "ELECTRICO-4 - (1)", "electrico 4 (1)", "Eléctrico-4-(1)", "E1" })
        {
            var x = Pedir(d, "proponer_cambio", "{\"elemento\":\"" + q + "\",\"tipo\":\"cota_inicio\",\"sumar\":10}");
            Es(x.Ok && x.Datos["handle"].GetValue<string>() == "E1" && x.Datos["despues"].GetValue<string>() == "100.00",
               "«" + q + "» = ELECTRICO-4 - (1), sube 10 ft");
        }
        var y = Pedir(d, "proponer_cambio", "{\"elemento\":\"ELECTRICO-4 - (1)\",\"tipo\":\"cota_fin\",\"sumar\":-2.5}");
        Es(y.Ok && y.Datos["despues"].GetValue<string>() == "86.50", "baja 2.5 ft el final");
        y = Pedir(d, "proponer_cambio", "{\"elemento\":\"ELECTRICO-4\",\"tipo\":\"cota_inicio\",\"sumar\":1}");
        Es(!y.Ok && y.Error.Contains("ELECTRICO-4 - (1)") && y.Error.Contains("ELECTRICO-4 - (11)") && !y.Error.Contains("ELECTRICO-41"),
           "nombre incompleto: lista las candidatas, no la de otra red");
        y = Pedir(d, "proponer_cambio", "{\"elemento\":\"ELECTRICO-9 - (1)\",\"tipo\":\"cota_inicio\",\"sumar\":1}");
        Es(!y.Ok && y.Error.Contains("¿Quisiste decir") && !y.Error.ToLowerInvariant().Contains("handle"), "inexistente: sugiere sin hablar de handles");
        Es(Pedir(d, "detalle_elemento", "{\"elemento\":\"electrico 4 (11)\"}").Ok, "detalle por nombre");
        Es(Pedir(d, "ir_a", "{\"elementos\":[\"ELECTRICO-41 - (1)\"]}").Ok, "ir_a por nombre");
        Es(e.Aplicados.Count == 0, "nada se aplicó sin confirmar");
        l.M.Textos.Add(new TextoDibujo { Handle = "T1", Tipo = "MTEXT", Contenido = "HOLA", Capa = "0", X = 10, Y = 20, Altura = 2.5 });
        l.M.Textos.Add(new TextoDibujo { Handle = "T2", Tipo = "TEXT", Contenido = "Calle Ñuñoa", Capa = "ANNO" });
        var tx = Pedir(d, "buscar_textos", "{}", "basico");
        Es(tx.Ok && tx.Datos["total"].GetValue<int>() == 2, "lista todos los textos (perfil básico)");
        tx = Pedir(d, "buscar_textos", "{\"texto\":\"hola\"}");
        Es(tx.Ok && tx.Datos["total"].GetValue<int>() == 1 && tx.Datos["filas"][0][2].GetValue<string>() == "HOLA", "busca «hola» = HOLA");
        Es(Pedir(d, "buscar_textos", "{\"texto\":\"nunoa\"}").Datos["total"].GetValue<int>() == 1, "sin acentos");
        Es(Pedir(d, "ir_a", "{\"handles\":[\"T1\"]}").Ok, "ir_a a un texto");
    }

    private static void Perfiles()
    {
        Console.WriteLine("Perfiles");
        var (d, _, _, _) = Armar();
        Es(!Pedir(d, "historial", "{}", "basico").Ok, "básico no ve historial");
        Es(Pedir(d, "resumen_modelo", "{}", "basico").Ok, "básico sí ve el resumen");
        Es(Catalogo.DelPerfil("basico").Count() < Catalogo.Todas.Count, "perfil básico más chico");
        foreach (var h in Catalogo.Todas)
            Es(JsonNode.Parse(h.Esquema)?["type"]?.GetValue<string>() == "object", "esquema válido: " + h.Nombre);
    }

    // ------------------------------------------------------------ punta a punta

    private static void PuntaAPunta()
    {
        Console.WriteLine("Punta a punta (PdfCadMcp.exe ↔ tubería ↔ despachador)");
        string exe = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..",
                                                   "PdfCadMcp", "bin", "Release", "net8.0", "PdfCadMcp.exe"));
        if (!File.Exists(exe)) { Console.WriteLine("  (omitida: compilar PdfCadMcp primero) " + exe); return; }
        if (Directory.GetFiles(@"\\.\pipe\").Any(n => Path.GetFileName(n).StartsWith(Protocolo.PREFIJO_TUBERIA)))
        { Console.WriteLine("  (omitida: hay un Civil 3D con la IA encendida)"); return; }

        var (d, _, e, _) = Armar();
        using (var srv = new ServidorTuberia(d))
        {
            srv.Iniciar();
            foreach (string perfil in new[] { "completo", "basico" })
            {
                var psi = new ProcessStartInfo(exe, $"--perfil {perfil} --origen qwen")
                { RedirectStandardInput = true, RedirectStandardOutput = true, UseShellExecute = false };
                using (var p = Process.Start(psi))
                {
                    JsonNode Rpc(string json) { p.StandardInput.WriteLine(json); return JsonNode.Parse(p.StandardOutput.ReadLine()); }

                    var ini = Rpc("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\"}}");
                    Es(ini["result"]["protocolVersion"].GetValue<string>() == "2025-03-26", "negocia la versión");
                    p.StandardInput.WriteLine("{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}");
                    var tools = Rpc("{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}")["result"]["tools"].AsArray();
                    Es(tools.Count == Catalogo.DelPerfil(perfil).Count(), "tools/list por perfil " + perfil);
                    var r = Rpc("{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"resumen_modelo\",\"arguments\":{}}}");
                    Es(!r["result"]["isError"].GetValue<bool>() && r["result"]["content"][0]["text"].GetValue<string>().Contains("WATER"), "tools/call llega al plugin");
                    r = Rpc("{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"historial\",\"arguments\":{}}}");
                    Es(r["result"]["isError"].GetValue<bool>() == (perfil == "basico"), "perfil filtra en el host");
                    var pr = Rpc("{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"proponer_cambio\",\"arguments\":{\"handle\":\"A1\",\"tipo\":\"descripcion\",\"valor\":\"x\"}}}");
                    string id = JsonNode.Parse(pr["result"]["content"][0]["text"].GetValue<string>())["id"].GetValue<string>();
                    int antes = e.Aplicados.Count;
                    Rpc("{\"jsonrpc\":\"2.0\",\"id\":6,\"method\":\"tools/call\",\"params\":{\"name\":\"confirmar_cambio\",\"arguments\":{\"id\":\"" + id + "\"}}}");
                    Es(e.Aplicados.Count == antes + 1 && e.Aplicados.Last().Origen == "qwen", "cambio por MCP con origen");
                    Es(Rpc("{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"nada\"}")["error"] != null, "método desconocido = error JSON-RPC");
                    p.StandardInput.Close();
                    p.WaitForExit(5000);
                }
            }
        }
    }
}
