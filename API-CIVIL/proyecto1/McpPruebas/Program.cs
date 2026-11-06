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
        ConflictosYSoluciones();
        PendientesTamanosPerfiles();
        Obra();
        Plano();
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
        public List<TamanoDisponible> T = new List<TamanoDisponible>();
        public List<TamanoDisponible> Tamanos(string h) => T;
        public List<Cuerpo> C = new List<Cuerpo>();
        public List<Interferencia> I = new List<Interferencia>();
        public List<(string a, string b)> Probados;
        public List<Cuerpo> Cuerpos() => C;
        public List<Interferencia> Interferencias(IList<(string a, string b)> pares)
        { Probados = pares.ToList(); return I.Where(i => pares.Any(p => (p.a == i.A && p.b == i.B) || (p.a == i.B && p.b == i.A))).ToList(); }
    }

    internal sealed class EditorFalso : IEditorDibujo
    {
        public LectorFalso L; public List<CambioPropuesto> Aplicados = new List<CambioPropuesto>();
        public void Aplicar(CambioPropuesto c)
        {
            Aplicados.Add(c);
            Tuberia T(string h) => L.M.Tuberias.First(x => x.Handle == h);
            switch (c)
            {
                case CambioMover mv:
                    foreach (var tt in L.M.Tuberias.Where(x => mv.Handles.Contains(x.Handle)))
                    { tt.CotaIni += mv.Dz; tt.CotaFin += mv.Dz; tt.XIni += mv.Dx; tt.XFin += mv.Dx; tt.YIni += mv.Dy; tt.YFin += mv.Dy; }
                    return;
                case CambioPendiente pe:
                    foreach (var z in pe.Cotas) { T(z.Handle).CotaIni = z.Ini; T(z.Handle).CotaFin = z.Fin; }
                    return;
                case CambioTamano ta:
                    foreach (var z in ta.Tamanos) { T(z.Handle).Tamano = z.Nombre; T(z.Handle).DiametroIn = z.DiametroIn; }
                    return;
                case CambioBuzon bz:
                    var e = L.M.Estructuras.First(x => x.Handle == bz.Handle);
                    if (bz.Rim.HasValue) e.Rim = bz.Rim; if (bz.Sump.HasValue) e.Sump = bz.Sump;
                    return;
                case CambioSimple si:
                    if (si.Tipo == TiposCambio.COTA_INICIO) T(si.Handle).CotaIni = double.Parse(si.Despues, System.Globalization.CultureInfo.InvariantCulture);
                    if (si.Tipo == TiposCambio.CAPA) T(si.Handle).Capa = si.Despues;
                    return;
            }
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

    // ------------------------------------------------------------ conflictos

    /// <summary>Agua AGUA-20 (dos tubos de 12" con un codo sólido en medio) cruzada por TELECOM-31 (4"), que
    /// sigue sin accesorio en TELECOM-32 (unión directa, misma cota).</summary>
    private static Modelo Cruce()
    {
        var m = new Modelo();
        Tuberia T(string h, string red, TipoRed tr, string capa, string num, double d, double x0, double y0, double x1, double y1, double z) =>
            new Tuberia { Handle = h, Nombre = $"{red} - ({h})", Red = red, TipoRed = tr, Capa = capa, UtilidadCapa = capa,
                          UtilidadNumero = num, DiametroIn = d, XIni = x0, YIni = y0, XFin = x1, YFin = y1, CotaIni = z, CotaFin = z,
                          LargoFt = Math.Sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0)) };
        m.Tuberias.Add(T("W1", "AGUA-7", TipoRed.Presion, "AGUA", "20", 12, 0, 0, 49, 0, -5.0));
        m.Tuberias.Add(T("W2", "AGUA-7", TipoRed.Presion, "AGUA", "20", 12, 51, 0, 100, 0, -5.0));
        m.Accesorios.Add(new Accesorio { Handle = "S1", Tipo = "ELBOW", Red = "AGUA-7", X = 50, Y = 0, ZEje = -4.5, RadioFt = 1.5 });
        m.Tuberias.Add(T("T1", "TELECOM-31", TipoRed.Gravedad, "TELECOM", "31", 4, 30, -20, 30, 20, -4.8));
        m.Tuberias.Add(T("T2", "TELECOM-31", TipoRed.Gravedad, "TELECOM", "32", 4, 30, 20, 60, 20, -4.8));
        m.Tuberias.Add(T("A1", "ALCANTARILLADO-34", TipoRed.Gravedad, "ALCANTARILLADO", "34", 8, 0, 200, 100, 200, -9));
        return m;
    }

    private const string REGLAS = "[{\"a\":\"AGUA\",\"b\":\"TELECOM\",\"sep_v_ft\":1.0,\"fuente\":\"Normativa X\"}]";

    private static void ConflictosYSoluciones()
    {
        Console.WriteLine("Conflictos y soluciones");
        var m = Cruce();
        var reglas = new List<ReglaSeparacion> { new ReglaSeparacion { A = "AGUA", B = "TELECOM", SepVFt = 1.0 } };
        var ks = Conflictos.Buscar(m, reglas, out int sinCota);
        Es(ks.Count == 1 && ks[0].Id == "K1" && ks[0].Tipo == Conflictos.CHOQUE && sinCota == 0, "un choque agua × telecom");
        Es(Math.Abs(ks[0].X - 30) < 1e-9 && Math.Abs(ks[0].Y) < 1e-9, "en el cruce");
        Es(Conflictos.Buscar(m, null, out _).Count == 1, "sin normativa: el choque sigue");

        var ops = SolucionesRed.Opciones(m, ks[0], reglas, ks);
        Es(ops.Count == 4, "cuatro opciones: bajar/subir cada una");
        var p1 = ops[0];
        Es(p1.Valida && p1.Mover == "AGUA-20" && p1.Accion == "subir" && Math.Abs(p1.DeltaFt - 1.54) < 1e-9,
           "P1 = subir el agua 1.54 ft (telecom separaría su unión directa)");
        Es(p1.Tuberias.Count == 2 && p1.Accesorios.Count == 1, "el agua se mueve entera, con su codo");
        var tel = ops.First(o => o.Mover == "TELECOM-31" && o.Accion == "bajar");
        Es(!tel.Valida && tel.UnionesRotas.Count == 1 && Math.Abs(tel.DeltaFt + 1.54) < 1e-9, "bajar telecom: válida no, separa la unión");
        // con la opción elegida, ya no hay conflicto y queda justo la separación
        var dz = p1.Tuberias.ToDictionary(t => t.Handle, t => p1.DeltaFt);
        var despues = Conflictos.Entre(p1.Tuberias, m.Tuberias.Where(t => !dz.ContainsKey(t.Handle)).ToList(), reglas, dz, out _);
        Es(despues.Count == 0, "la solución deja la separación de la normativa");

        // «encima»: el agua debe ir arriba → no se propone bajarla ni subir telecom
        var enc = new List<ReglaSeparacion> { new ReglaSeparacion { A = "AGUA", B = "TELECOM", SepVFt = 1.0, Encima = "AGUA" } };
        var k2 = Conflictos.Buscar(m, enc, out _)[0];
        Es(SolucionesRed.Opciones(m, k2, enc).All(o => (o.Mover == "AGUA-20") == (o.Accion == "subir")), "respeta qué va encima");
        var deb = new List<ReglaSeparacion> { new ReglaSeparacion { A = "TELECOM", B = ReglaSeparacion.CUALQUIERA, SepVFt = 1.0, Debajo = "TELECOM" } };
        Es(SolucionesRed.Opciones(m, Conflictos.Buscar(m, deb, out _)[0], deb).All(o => (o.Mover == "AGUA-20") == (o.Accion == "subir")),
           "«telecom por debajo de cualquiera» = lo mismo");
        // separación (no choque): telecom 1.4 ft más abajo → libre 0.87 < 1
        foreach (var t in m.Tuberias.Where(t => t.Capa == "TELECOM")) { t.CotaIni -= 1.4; t.CotaFin -= 1.4; }
        Es(Conflictos.Buscar(m, reglas, out _).Single().Tipo == Conflictos.SEPARACION, "le falta separación");
        Es(Conflictos.Buscar(m, null, out _).Count == 0, "sin normativa no es conflicto");

        // por el despachador: buscar → proponer → confirmar
        var (d, l, e, r) = Armar();
        l.M = Cruce();
        var x = Pedir(d, "buscar_conflictos", "{\"reglas\":" + REGLAS + "}", "basico");
        Es(x.Ok && x.Datos["conflictos"]["total"].GetValue<int>() == 1, "buscar_conflictos (básico)");
        x = Pedir(d, "proponer_solucion", "{\"conflicto\":\"conflicto 1\",\"reglas\":" + REGLAS + "}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.DESPLAZAR && x.Datos["opcion"].GetValue<string>() == "P1"
           && e.Aplicados.Count == 0, "propone sin aplicar");
        Es(x.Datos["opciones"]["filas"].AsArray().Count == 4 && x.Datos["antes"].GetValue<string>() == "-5.00"
           && x.Datos["despues"].GetValue<string>() == "-3.46", "antes/después y las opciones");
        string id = x.Datos["id"].GetValue<string>();
        var y = Pedir(d, "proponer_solucion", "{\"conflicto\":\"K1\",\"mover\":\"telecom\",\"reglas\":" + REGLAS + "}");
        Es(y.Ok && y.Datos["elemento"].GetValue<string>().StartsWith("TELECOM-31") && !y.Datos["valida"].GetValue<bool>()
           && y.Datos["advertencias"].AsArray().Count > 0, "otra opción a pedido, con su advertencia");
        Es(Pedir(d, "proponer_solucion", "{\"conflicto\":\"K9\"}").Error.Contains("K1"), "conflicto inexistente: dice cuáles hay");
        x = Pedir(d, "confirmar_cambio", "{\"id\":\"" + id + "\"}");
        Es(x.Ok && l.M.Tuberias.Where(t => t.Capa == "AGUA").All(t => Math.Abs(t.CotaIni.Value + 3.46) < 1e-9), "confirmar sube el agua entera");
        Es(Pedir(d, "buscar_conflictos", "{\"reglas\":" + REGLAS + "}").Datos["conflictos"]["total"].GetValue<int>() == 0, "ya no hay conflictos");
        // el dibujo cambió entre propuesta y confirmación
        l.M = Cruce();
        x = Pedir(d, "proponer_solucion", "{\"conflicto\":\"K1\",\"reglas\":" + REGLAS + "}");
        l.M.Tuberias[0].CotaIni = -6;
        Es(!Pedir(d, "confirmar_cambio", "{\"id\":\"" + x.Datos["id"].GetValue<string>() + "\"}").Ok, "rechaza si las cotas cambiaron");
    }

    // ------------------------------------------------------------ pendientes, tamaños y perfiles

    /// <summary>ALCANTARILLADO-5: MH-1 → P1 → MH-2 → P2 → MH-3 (P1 a 0.1 %, P2 en contrapendiente) y la regla
    /// «pendiente mínima 0.5 % en 6–10"»; P3 es de DRENAJE-9, sin reglas.</summary>
    private static Modelo Gravedad()
    {
        var m = new Modelo();
        m.Estructuras.Add(new Estructura { Handle = "M1", Nombre = "MH-1", Red = "SS", Rim = 110, Sump = 99.5 });
        m.Estructuras.Add(new Estructura { Handle = "M2", Nombre = "MH-2", Red = "SS", Rim = 110, Sump = 99.6 });
        m.Estructuras.Add(new Estructura { Handle = "M3", Nombre = "MH-3", Red = "SS", Rim = 110, Sump = 98.0 });
        Tuberia T(string h, string ei, string ef, double zi, double zf, double x0, double x1) => new Tuberia
        {
            Handle = h, Nombre = $"SS - ({h})", Red = "SS", TipoRed = TipoRed.Gravedad, Capa = "C-SSWR", UtilidadCapa = "ALCANTARILLADO",
            UtilidadNumero = "5", TipoApp = "COLECTOR", DiametroIn = 8, Tamano = "8 in", Familia = "PVC Pipe", Descripcion = "PVC",
            XIni = x0, XFin = x1, LargoFt = x1 - x0, CotaIni = zi, CotaFin = zf, EstructuraIni = ei, EstructuraFin = ef,
        };
        m.Tuberias.Add(T("P1", "M1", "M2", 100, 99.9, 0, 100));          // 0.1 %
        m.Tuberias.Add(T("P2", "M2", "M3", 99.0, 99.2, 100, 200));       // −0.2 %
        var p3 = T("P3", "", "", 50, 49, 500, 600);
        p3.UtilidadCapa = "DRENAJE"; p3.UtilidadNumero = "9"; p3.Red = "SD"; p3.Nombre = "SD - (1)";
        m.Tuberias.Add(p3);
        return m;
    }

    /// <summary>La pendiente que la APP calculó con sus normativas (MRDC: 0.5 %) para P1 y P2.</summary>
    private const string NORMAS = "{\"P1\":{\"min\":0.5,\"fuente\":\"MRDC\"},\"P2\":{\"min\":0.5,\"fuente\":\"MRDC\"}}";

    private static string Id(Respuesta x) => x.Datos["id"].GetValue<string>();
    private static string Avisos(Respuesta x) => string.Join(" | ", x.Datos["advertencias"].AsArray().Select(a => a.GetValue<string>()));

    private static void PendientesTamanosPerfiles()
    {
        Console.WriteLine("Pendientes, tamaños y perfiles");
        var (d, l, e, _) = Armar();
        l.M = Gravedad();
        var x = Pedir(d, "datos_red", "{}", "basico");
        Es(x.Ok && x.Datos["tuberias"]["filas"].AsArray().Count == 3 && x.Datos["estructuras"]["filas"].AsArray().Count == 3, "datos_red da todo");
        Es(x.Ok && x.Datos["tuberias"]["filas"][0][6].GetValue<string>() == "COLECTOR", "con el tipo de la app");

        // pendiente según la normativa: toda la utilidad, solo las que no cumplen
        x = Pedir(d, "proponer_pendiente", "{\"elemento\":\"ALCANTARILLADO-5\",\"objetivos\":" + NORMAS + "}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.PENDIENTE && x.Datos["tuberias"].GetValue<int>() == 2, "propone P1 y P2");
        Es(x.Ok && x.Datos["despues"].GetValue<string>() == "0.5 %" && x.Datos["antes"].GetValue<string>() == "-0.2 a 0.1 %", "a 0.5 %");
        Es(x.Ok && x.Datos["consecuencias"].AsArray().Any(c => c.GetValue<string>().Contains("MRDC")), "dice de qué normativa sale");
        Es(x.Ok && Avisos(x).Contains("bajo el fondo de MH-2"), "P1 queda bajo el fondo de MH-2: avisa");
        Es(e.Aplicados.Count == 0, "no aplica nada");
        Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(x) + "\"}");
        Es(Math.Abs(l.M.Tuberias[0].CotaFin.Value - 99.5) < 1e-9 && Math.Abs(l.M.Tuberias[1].CotaFin.Value - 98.5) < 1e-9, "rasantes de fin nuevas");
        Es(!Pedir(d, "proponer_pendiente", "{\"elemento\":\"ALCANTARILLADO-5\",\"objetivos\":" + NORMAS + "}").Ok, "ya cumplen: nada que cambiar");
        Es(Pedir(d, "proponer_pendiente", "{\"elemento\":\"DRENAJE-9\",\"objetivos\":" + NORMAS + "}").Error.Contains("dime qué pendiente"),
           "sin regla: pide la pendiente");
        x = Pedir(d, "proponer_pendiente", "{\"elemento\":\"SS - (P1)\",\"pendiente_pct\":0.2,\"mantener\":\"fin\",\"objetivos\":" + NORMAS + "}");
        Es(x.Ok && x.Datos["efecto"]["cotas"].AsArray().Count == 1, "devuelve su efecto (la app revisa su normativa)");
        Es(x.Ok && x.Datos["consecuencias"][0].GetValue<string>().Contains("rasante de inicio"), "mantener el fin mueve el inicio");
        Es(!Pedir(d, "proponer_pendiente", "{\"elemento\":\"SS - (P1)\",\"pendiente_pct\":-1}").Ok, "pendiente negativa: no");
        // P2 llega más abajo que la tubería que sale de MH-3
        l.M = Gravedad();
        l.M.Tuberias.Add(new Tuberia { Handle = "P4", Nombre = "SS - (P4)", Red = "SS", TipoRed = TipoRed.Gravedad, UtilidadCapa = "ALCANTARILLADO",
                                       UtilidadNumero = "6", DiametroIn = 8, LargoFt = 50, CotaIni = 98.9, CotaFin = 98.6, EstructuraIni = "M3" });
        x = Pedir(d, "proponer_pendiente", "{\"elemento\":\"SS - (P2)\",\"objetivos\":" + NORMAS + "}");
        Es(x.Ok && Avisos(x).Contains("el agua no saldría"), "salto: el agua no sale");

        // tamaño
        l.M = Gravedad();
        l.T = new List<TamanoDisponible>
        {
            new TamanoDisponible { Clave = "a", Familia = "PVC Pipe", Nombre = "8 in", DiametroIn = 8, Material = "PVC" },
            new TamanoDisponible { Clave = "b", Familia = "PVC Pipe", Nombre = "10 in", DiametroIn = 10, Material = "PVC" },
            new TamanoDisponible { Clave = "c", Familia = "Concrete Pipe", Nombre = "10 inch RCP", DiametroIn = 10, Material = "Concrete" },
            new TamanoDisponible { Clave = "d", Familia = "PVC Pipe", Nombre = "6 in", DiametroIn = 6, Material = "PVC" },
        };
        x = Pedir(d, "proponer_tamano", "{\"elemento\":\"SS - (P1)\",\"diametro_in\":10,\"objetivos\":" + NORMAS + "}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.TAMANO && x.Datos["despues"].GetValue<string>() == "10\" PVC",
           "10\" en la misma familia (PVC)");
        Es(x.Ok && Avisos(x).Contains("más grande") && Avisos(x).Contains("SS - (P2)"), "más grande que la que sigue: avisa");
        x = Pedir(d, "proponer_tamano", "{\"elemento\":\"ALCANTARILLADO-5\",\"diametro_in\":10,\"material\":\"concreto\",\"objetivos\":" + NORMAS + "}");
        Es(x.Ok && x.Datos["tuberias"].GetValue<int>() == 2 && x.Datos["despues"].GetValue<string>() == "10\" Concrete", "concreto = Concrete, toda la utilidad");
        Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(x) + "\"}");
        Es(l.M.Tuberias.Take(2).All(t => t.Tamano == "10 inch RCP"), "confirmar cambia las dos");
        l.M = Gravedad();
        x = Pedir(d, "proponer_tamano", "{\"elemento\":\"SS - (P1)\",\"diametro_in\":6,\"objetivos\":" + NORMAS + "}");
        Es(x.Ok && x.Datos["efecto"]["tamanos"][0]["diam_in"].GetValue<double>() == 6, "6\": el efecto va a la app para su normativa");
        var y = Pedir(d, "proponer_tamano", "{\"elemento\":\"SS - (P1)\",\"diametro_in\":15}");
        Es(!y.Ok && y.Error.Contains("Hay:") && y.Error.Contains("10\""), "sin ese tamaño: dice cuáles hay");
        Es(!Pedir(d, "proponer_tamano", "{\"elemento\":\"SS - (P1)\",\"diametro_in\":8}").Ok, "ya tiene ese tamaño");
        l.M.Tuberias[0].Tamano = "otro";
        Es(!Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(x) + "\"}").Ok, "rechaza si el tamaño cambió");
        Es(Materiales.Mismo("Ductile Iron Pipe", "Hierro dúctil") && !Materiales.Mismo("PVC Pipe", "Concreto"), "sinónimos de material");

        // perfil
        l.M = Gravedad();
        x = Pedir(d, "crear_perfil", "{\"desde\":\"SS - (P1)\",\"hasta\":\"SS - (P2)\"}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.PERFIL && x.Datos["tuberias"].GetValue<int>() == 2, "propone el perfil P1 → P2");
        Es(!Pedir(d, "crear_perfil", "{\"desde\":\"SS - (P1)\",\"hasta\":\"SD - (1)\"}").Ok, "redes distintas: no");
        x = Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(x) + "\"}");
        var ult = (CambioPerfil)e.Aplicados.Last();
        Es(x.Ok && ult.Tipo == TiposCambio.PERFIL && Math.Abs(ult.SemillaX - 50) < 1e-9 && Math.Abs(ult.FinX.Value - 150) < 1e-9,
           "semilla y fin en el medio de cada tramo");
    }

    // ------------------------------------------------------------ obra: buzones, válvulas, accesorios, planta, 3D

    private static void Obra()
    {
        Console.WriteLine("Buzones, metrados, válvulas, accesorios, conexión vertical, planta y 3D");
        var (d, l, e, _) = Armar();
        Es(!d.Descuadres().Any(), "catálogo y casos cuadran: " + string.Join(", ", d.Descuadres()));

        // buzones
        l.M = Gravedad();
        var x = Pedir(d, "revisar_buzones", "{}", "basico");
        Es(x.Ok && x.Datos["filas"].AsArray().Any(f => f[0].GetValue<string>() == "MH-2" && f[2].GetValue<string>() == "bajo_fondo"),
           "P2 sale de MH-2 bajo su fondo");
        x = Pedir(d, "proponer_buzon", "{\"elemento\":\"MH-2\",\"sumar_fondo\":-1}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.BUZON && !x.Datos["advertencias"].AsArray().Any(a => a.GetValue<string>().Contains("bajo el fondo")),
           "bajar el fondo 1 ft resuelve el aviso");
        Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(x) + "\"}");
        Es(Math.Abs(l.M.Estructuras[1].Sump.Value - 98.6) < 1e-9, "fondo nuevo aplicado");
        Es(!Pedir(d, "proponer_buzon", "{\"elemento\":\"MH-2\",\"altura\":-3}").Ok, "altura negativa: no");
        x = Pedir(d, "proponer_buzon", "{\"elemento\":\"MH-1\",\"altura\":2}");
        Es(x.Ok && Avisos(x).Contains("bajo el fondo"), "fondo sobre la tubería: avisa");

        // metrados y accesorios
        l.M = Cruce();
        l.M.Accesorios.Add(new Accesorio { Handle = "S2", Tipo = "ELBOW", Red = "AGUA-7", X = 50, Y = 0, ZEje = -4.5, RadioFt = 1.5 });
        x = Pedir(d, "metrados", "{}", "basico");
        Es(x.Ok && x.Datos["totales"]["accesorios"].GetValue<int>() == 1, "dos sólidos del mismo codo = un accesorio");
        Es(x.Ok && x.Datos["tuberias"]["filas"].AsArray().Any(f => f[0].GetValue<string>() == "AGUA" && f[4].GetValue<double>() == 98), "98 ft de agua");
        x = Pedir(d, "buscar_accesorios", "{\"tipo\":\"codo\"}", "basico");
        Es(x.Ok && x.Datos["total"].GetValue<int>() == 1 && x.Datos["filas"][0][0].GetValue<string>() == "A1", "el codo es A1 (por su nombre en español)");

        // quitar accesorio
        x = Pedir(d, "proponer_quitar_accesorio", "{\"accesorio\":\"A1\"}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.QUITAR_ACCESORIO && x.Datos["tuberias"].GetValue<int>() == 2, "quita el codo, llegan sus dos tuberías");

        // válvula
        x = Pedir(d, "proponer_valvula", "{\"elemento\":\"AGUA-7 - (W2)\"}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.PONER_VALVULA, "pone una válvula en el medio de W2");
        Es(!Pedir(d, "proponer_valvula", "{\"elemento\":\"TELECOM-31 - (T1)\"}").Ok, "en gravedad no");
        x = Pedir(d, "proponer_valvula", "{\"elemento\":\"AGUA-7 - (W2)\",\"union\":\"RG\",\"distancia_ft\":0}");
        Es(x.Ok && Avisos(x).Contains("corrió"), "RG en 12\" vale; pegada al codo se corre");
        l.M.Accesorios.Add(new Accesorio { Handle = "V1", Tipo = "VALVE", Red = "AGUA-7", X = 75, Y = 0, RadioFt = 1.2 });
        x = Pedir(d, "proponer_valvula", "{\"accion\":\"quitar\",\"elemento\":\"A2\"}");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.QUITAR_VALVULA, "quita la válvula A2");

        // conexión vertical: telecom (-4.8) toca agua (-5) en planta → de una con el conflicto K1
        x = Pedir(d, "proponer_conexion_vertical", "{\"elementos\":[\"AGUA-7 - (W1)\",\"TELECOM-31 - (T1)\"]}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.CONEXION_VERTICAL, "conexión vertical agua ↔ telecom");
        Es(!Pedir(d, "proponer_conexion_vertical", "{\"elementos\":[\"AGUA-7 - (W1)\",\"ALCANTARILLADO-34 - (A1)\"]}").Ok, "si no se tocan: no");

        // mover en planta: telecom 25 ft a la derecha → deja de cruzar el agua
        l.M = Cruce();
        x = Pedir(d, "proponer_mover_planta", "{\"elemento\":\"TELECOM-31 - (T1)\",\"solo_tramo\":\"si\",\"dx\":25,\"reglas\":" + REGLAS + "}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposCambio.MOVER_PLANTA, "mueve en planta");
        Es(x.Ok && x.Datos["advertencias"].AsArray().Any(a => a.GetValue<string>().Contains("se separaría")), "T1 se separa de T2: avisa");
        x = Pedir(d, "proponer_mover_planta", "{\"elemento\":\"AGUA-7 - (W1)\",\"lado\":\"izquierda\",\"distancia\":30,\"reglas\":" + REGLAS + "}");
        Es(x.Ok && x.Datos["consecuencias"].AsArray().Any(c => c.GetValue<string>().Contains("Deja de chocar")), "el agua 30 ft al norte deja de chocar");
        Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(x) + "\"}");
        Es(l.M.Tuberias.Where(t => t.Capa == "AGUA").All(t => Math.Abs(t.YIni - 30) < 1e-9), "confirmar mueve las dos del agua");
        Es(!Pedir(d, "proponer_mover_planta", "{\"elemento\":\"AGUA-7 - (W1)\"}").Ok, "sin cuánto: pregunta");

        // choques 3D: solo se prueban los pares que no están unidos a propósito
        Cuerpo C(string h, string tipo, string util, string red, double x0, double x1, params (double, double)[] puntas)
        {
            var c = new Cuerpo { Handle = h, Tipo = tipo, Nombre = h, Utilidad = util, Red = red, Min = new[] { x0, 0, 0.0 }, Max = new[] { x1, 1, 1.0 } };
            c.Puntas.AddRange(puntas);
            return c;
        }
        l.C = new List<Cuerpo>
        {
            C("P1", "tuberia", "AGUA-1", "W", 0, 10, (0, 0.5), (10, 0.5)),
            C("P2", "tuberia", "AGUA-1", "W", 10, 20, (10, 0.5), (20, 0.5)),       // misma utilidad
            C("Q1", "tuberia", "GAS-2", "G", 5, 6, (5, 0.5), (6, 0.5)),            // cruza a P1
            C("B1", "solido", "", "", 19.5, 22),                                    // bancoducto donde llega P2
            C("Z1", "estructura", "", "X", 100, 101),                               // lejos
        };
        l.I = new List<Interferencia> { new Interferencia { A = "P1", B = "Q1", X = 5.5, Y = 0.5, Z = 0.5, VolumenFt3 = 0.1 } };
        x = Pedir(d, "buscar_choques_3d", "{}", "basico");
        Es(x.Ok && x.Datos["choques"]["total"].GetValue<int>() == 1 && x.Datos["choques"]["filas"][0][1].GetValue<string>() == "P1", "un choque real P1 × Q1");
        Es(l.Probados.Count == 1, "solo se probó ese par (lo unido a propósito no)");
    }

    // ------------------------------------------------------------ revisión del plano

    private static void Plano()
    {
        Console.WriteLine("Revisión del plano");
        var (d, l, e, _) = Armar();
        var m = new Modelo();
        TextoDibujo T(string h, string tipo, string c, double x0, double y0, double x1, double y1) =>
            new TextoDibujo { Handle = h, Tipo = tipo, Contenido = c, Capa = "ANNO", X = x0, Y = y0, Altura = y1 - y0, Caja = new Caja(x0, y0, x1, y1) };
        m.Textos.Add(T("T1", "MTEXT", "R/W LINE", 0, 0, 10, 1));                     // la guía de la foto lo cruza
        m.Textos.Add(T("T2", "MLEADER", "PHOTO", 30, 0, 36, 1));
        m.Textos.Add(T("T3", "MTEXT", "15.0 ft ALONG BW", 50, 0, 60, 1));
        m.Textos.Add(T("T4", "TEXT", "EX. TREE", 51, 0.2, 58, 1.2));                 // se tapa con T3
        m.Textos.Add(T("T5", "MTEXT", "DWS", 80, 0, 83, 1));                          // dentro de una trama chica
        m.Guias.Add(new Guia { Handle = "T2", Tipo = "MLEADER", ConTexto = true, TextoHandle = "T2", Vertices = { (5, -3), (5, 7), (30, 0.5) } });
        m.Guias.Add(new Guia { Handle = "G2", Tipo = "LEADER", ConTexto = false, Vertices = { (19.6, 16), (25, 20) } });
        m.Cotas.Add(new Cota { Handle = "D1", Texto = "19.9", Medida = 19.9, Estilo = "PDFCAD", Decimales = 1, AlturaTexto = 1,
                               CajaTexto = new Caja(1, 5, 4, 6), A = (0, 5.5), B = (20, 5.5) });
        m.Tramas.Add(new Trama { Handle = "H1", Patron = "ANSI31", Caja = new Caja(78, -2, 86, 3) });
        l.M = m;

        var x = Pedir(d, "revisar_plano", "{}", "basico");
        var tipos = x.Datos["revision"]["filas"].AsArray().Select(f => f[1].GetValue<string>()).ToList();
        Es(x.Ok && tipos.Contains(RevisionPlano.GUIA_TEXTO) && tipos.Contains(RevisionPlano.FLECHA_SUELTA) &&
           tipos.Contains(RevisionPlano.TEXTO_TEXTO) && tipos.Contains(RevisionPlano.TRAMA) && tipos.Contains(RevisionPlano.GUIA_COTA),
           "encuentra guía sobre texto, flecha suelta, textos que se tapan, trama y guía sobre cota: " + string.Join(",", tipos));
        var items = RevisionPlano.Revisar(m);
        Es(!items.Any(i => i.Tipo == RevisionPlano.GUIA_TEXTO && i.Handles[0] == "T2"), "la guía no cruza su propio texto");

        // arreglos
        string Q(string tipo) => items.First(i => i.Tipo == tipo).Id;
        x = Pedir(d, "proponer_arreglo_revision", "{\"punto\":\"" + Q(RevisionPlano.FLECHA_SUELTA) + "\"}", "basico");
        Es(x.Ok && x.Datos["tipo"].GetValue<string>() == TiposTexto.BORRAR, "flecha suelta → borrarla");
        var gt = items.First(i => i.Tipo == RevisionPlano.GUIA_TEXTO);
        var movido = m.Textos.First(t => t.Handle == gt.Mover).Caja.Mover(gt.Dx, gt.Dy);
        Es(!movido.Encoger(RevisionPlano.ENCOGER).Corta(5, -3, 5, 7), "mover lo justo: el texto deja de tocar la guía");
        x = Pedir(d, "proponer_arreglo_revision", "{\"punto\":\"" + Q(RevisionPlano.TRAMA) + "\"}");
        Es(x.Ok && x.Datos["despues"].GetValue<string>() == "con máscara", "en la trama → máscara");
        var tt = items.First(i => i.Tipo == RevisionPlano.TEXTO_TEXTO);
        var a = m.Textos.First(t => t.Handle == tt.Mover).Caja.Mover(tt.Dx, tt.Dy);
        var b = m.Textos.First(t => t.Handle == tt.Handles[1]).Caja;
        Es(a.Solape(b) == 0, "textos que se tapan → se separan");

        // textos
        x = Pedir(d, "proponer_texto", "{\"buscar\":\"ALONG BW\",\"reemplazar\":\"ALONG BW\",\"por\":\"\"}", "basico");
        Es(x.Ok && x.Datos["despues"].GetValue<string>() == "15.0 ft", "quita «ALONG BW» → «15.0 ft»");
        Es(!Pedir(d, "proponer_texto", "{\"buscar\":\"NADA\",\"reemplazar\":\"NADA\"}").Ok, "si no hay ese texto: no");
        x = Pedir(d, "proponer_texto", "{\"elemento\":\"EX. TREE\",\"mascara\":\"si\"}");
        Es(x.Ok && x.Datos["advertencias"].AsArray().Count == 1, "máscara en un TEXT: avisa que no se puede");
        Pedir(d, "confirmar_cambio", "{\"id\":\"" + Id(Pedir(d, "proponer_texto", "{\"elemento\":\"T3\",\"dy\":2}")) + "\"}");
        Es(e.Aplicados.Last() is CambioTexto ct && ct.Ediciones[0].Dy == 2, "confirmar mueve el texto");

        // cotas
        x = Pedir(d, "buscar_cotas", "{}", "basico");
        Es(x.Ok && x.Datos["total"].GetValue<int>() == 1, "una cota");
        x = Pedir(d, "proponer_cota", "{\"estilo_actual\":\"PDFCAD\",\"decimales\":2}", "basico");
        Es(x.Ok && x.Datos["despues"].GetValue<string>() == "decimales 2", "cambia decimales de las de ese estilo");
        x = Pedir(d, "proponer_cota", "{\"accion\":\"crear\",\"x1\":0,\"y1\":0,\"x2\":3,\"y2\":4}");
        Es(x.Ok && x.Datos["despues"].GetValue<string>() == "5", "crea una cota de 5");
        Es(!Pedir(d, "proponer_cota", "{\"accion\":\"crear\",\"x1\":1,\"y1\":1,\"x2\":1,\"y2\":1}").Ok, "dos puntos iguales: no");
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
