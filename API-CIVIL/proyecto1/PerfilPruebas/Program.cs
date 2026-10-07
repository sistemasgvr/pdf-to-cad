using System;
using System.Collections.Generic;
using System.Linq;
using Civil3DBasico;

// Arnés de los módulos puros del perfil (DISENO.md F.12). `dotnet run -c Release` → 0 = todo OK.
internal static class Program
{
    static int fallos, total;

    static void Chequear(bool ok, string caso)
    {
        total++;
        if (!ok) { fallos++; Console.WriteLine("  ✗ " + caso); }
    }
    static bool Cerca(double a, double b, double tol = 1e-6) { return Math.Abs(a - b) <= tol; }
    static void Igual(string a, string b, string caso) { Chequear(a == b, caso + $" → «{a}» (esperado «{b}»)"); }
    static void Num(double a, double b, string caso, double tol = 1e-6) { Chequear(Cerca(a, b, tol), caso + $" → {a:G9} (esperado {b:G9})"); }

    static int Main()
    {
        Formatos(); Metrica(); VVE(); Empaquetado(); Recorrido();
        M1(); M2(); M2b(); M3(); M4(); M5(); M6(); M7(); M8(); M9(); M10(); M11(); Complementos(); Enderezar();
        Console.WriteLine($"\n{total - fallos}/{total} comprobaciones OK" + (fallos > 0 ? $" — {fallos} FALLO(S)" : ""));
        return fallos == 0 ? 0 : 1;
    }

    // ------------------------------------------------------------ PerfilTextos
    static void Formatos()
    {
        Igual(PerfilTextos.FormatoEstacion(105.144, 2), "1+05.14", "FormatoEstacion 105.144");
        Igual(PerfilTextos.FormatoEstacion(100, 2), "1+00.00", "FormatoEstacion 100");
        Igual(PerfilTextos.FormatoEstacion(99.996, 2), "1+00.00", "FormatoEstacion 99.996");
        Igual(PerfilTextos.FormatoEstacion(1234.5, 2), "12+34.50", "FormatoEstacion 1234.5");
        Igual(PerfilTextos.FormatoEstacion(85, 0), "0+85", "FormatoEstacion 85");
        Igual(PerfilTextos.FormatoEstacion(-15, 0), "-0+15", "FormatoEstacion -15");
        Igual(PerfilTextos.FormatoEstacion(160.584, 2), "1+60.58", "FormatoEstacion 160.584");
        Igual(PerfilTextos.FormatoEstacion(-0.004, 2), "0+00.00", "FormatoEstacion -0.004");
        Igual(PerfilTextos.FormatoCota(745.434), "745.43'", "FormatoCota 745.434");
        Igual(PerfilTextos.FormatoCota(745.436), "745.44'", "FormatoCota 745.436");
        Igual(PerfilTextos.FormatoCota(-3.2), "-3.20'", "FormatoCota -3.2");
        Igual(PerfilTextos.FormatoDiametro(8.0), "8\"", "FormatoDiametro 8");
        Igual(PerfilTextos.FormatoDiametro(7.97), "8\"", "FormatoDiametro 7.97");
        Igual(PerfilTextos.FormatoDiametro(0.75), "1\"", "FormatoDiametro 0.75");
        Igual(PerfilTextos.FormatoAngulo(44.6), "45%%d", "FormatoAngulo 44.6");
        Igual(PerfilTextos.FormatoAngulo(22.3), "22.5%%d", "FormatoAngulo 22.3");
        Igual(PerfilTextos.FormatoAngulo(11.0), "11.25%%d", "FormatoAngulo 11.0");
        Igual(PerfilTextos.FormatoAngulo(2.46), "2.5%%d", "FormatoAngulo 2.46");
        Igual(PerfilTextos.FormatoAngulo(30.0), "30%%d", "FormatoAngulo 30");
        Igual(PerfilTextos.FormatoLongitud(0.3), "1", "FormatoLongitud 0.3");
        Igual(PerfilTextos.FormatoLongitud(49.6), "50", "FormatoLongitud 49.6");
        var mats = new (string, string)[] { ("Fundición dúctil", "DI"), ("PVC", "PVC"), ("Hormigón armado", "RCP"), ("Acero corrugado", "CSP"),
            ("Plástico ABS", "ABS"), ("Acero", "STL"), ("Material sin definir", ""), ("", ""), ("HDPE", "HDPE"), ("Cobre", "COBRE") };
        foreach (var (m, esp) in mats) Igual(PerfilTextos.AbreviarMaterial(m), esp, "AbreviarMaterial " + m);
        Chequear(PerfilTextos.NumeroTolerante("745,431", out double v1) && Cerca(v1, 745.431), "NumeroTolerante 745,431");
        Chequear(PerfilTextos.NumeroTolerante("1.234,5", out double v2) && Cerca(v2, 1234.5), "NumeroTolerante 1.234,5");
        Chequear(PerfilTextos.NumeroTolerante("1,234.5", out double v3) && Cerca(v3, 1234.5), "NumeroTolerante 1,234.5");
        Chequear(PerfilTextos.NumeroTolerante(" 12 ", out double v4) && Cerca(v4, 12), "NumeroTolerante ' 12 '");
        Chequear(!PerfilTextos.NumeroTolerante("", out _) && !PerfilTextos.NumeroTolerante("abc", out _), "NumeroTolerante vacío/abc");
        var d = PerfilTextos.ParsearXData(new[] { "TIPO=TEE", "ANGULO=90,0", "COORD_X=6512345,123", "RED=RED-AGUA", "TIPO=WYE" });
        Igual(PerfilTextos.Txt(d, "TIPO"), "WYE", "ParsearXData clave repetida");
        Num(PerfilTextos.Num(d, "ANGULO"), 90, "ParsearXData ANGULO");
        Num(PerfilTextos.Num(d, "COORD_X"), 6512345.123, "ParsearXData COORD_X", 1e-6);
        Chequear(double.IsNaN(PerfilTextos.Num(d, "FALTA")), "ParsearXData FALTA = NaN");
        Igual(PerfilTextos.Sanear("Fundición {x}\\y"), "FUNDICION \\{X\\}\\\\Y", "Sanear llaves y barra");
        Igual(PerfilTextos.Sanear("45%%d bend"), "45%%d BEND", "Sanear conserva %%d");
    }

    static void Metrica()
    {
        Num(PerfilDiseno.AnchoBloqueVertical(3), 0.52, "AnchoBloqueVertical 3");
        Num(PerfilDiseno.AnchoBloqueVertical(4), 0.72, "AnchoBloqueVertical 4");
        Num(PerfilDiseno.AnchoBloqueVertical(1), 0.12, "AnchoBloqueVertical 1");
        Num(PerfilDiseno.LargoLinea("PIPE STA 1+00.00"), 1.5168, "LargoLinea PIPE STA");
        Chequear(PerfilDiseno.LongitudVisible("45%%d BEND") == 8, "LongitudVisible 45%%d BEND");
        Chequear(PerfilDiseno.LongitudVisible("A\\{B") == 3, "LongitudVisible A\\{B");
    }

    static void VVE()
    {
        var tabla = new (double s, double v, double ve, double cM, double cm, double eM, double em)[]
        {
            (5, 2, 2.5, 5, 1, 100, 10), (10, 4, 2.5, 10, 2, 100, 10), (20, 5, 4, 10, 2, 100, 10), (25, 4, 6.25, 10, 2, 100, 10),
            (30, 4, 7.5, 10, 2, 100, 10), (40, 4, 10, 10, 2, 100, 10), (50, 5, 10, 10, 2, 100, 10), (60, 10, 6, 20, 5, 100, 10),
            (100, 10, 10, 20, 5, 100, 10), (200, 20, 10, 50, 10, 500, 50),
        };
        foreach (var t in tabla)
        {
            double v = PerfilDiseno.ElegirV(t.s);
            var it = PerfilDiseno.ElegirIntervalos(t.s, v);
            Chequear(Cerca(v, t.v) && Cerca(t.s / v, t.ve) && Cerca(it.CotaMayor, t.cM) && Cerca(it.CotaMenor, t.cm)
                     && Cerca(it.EstMayor, t.eM) && Cerca(it.EstMenor, t.em),
                     $"Tabla F.3 S={t.s}: V={v} VE={t.s / v} int={it.CotaMayor}/{it.CotaMenor} {it.EstMayor}/{it.EstMenor}");
        }
        // Escala propia del perfil cuando el dibujo está a escala de detalle (S < 10).
        Num(PerfilDiseno.EscalaAuto(100), 10, "EscalaAuto(100 ft)");
        Num(PerfilDiseno.EscalaAuto(219), 10, "EscalaAuto(219 ft)");
        Num(PerfilDiseno.EscalaAuto(241), 20, "EscalaAuto(241 ft)");
        Num(PerfilDiseno.EscalaAuto(1500), 100, "EscalaAuto(1500 ft)");
        Num(PerfilDiseno.EscalaAuto(0), 10, "EscalaAuto(0)");
        Num(PerfilDiseno.EscalaAuto(1e7), 1000, "EscalaAuto(enorme)");
        Num(PerfilDiseno.SiguienteV(4, 10), 5, "SiguienteV(4,10)");
        Num(PerfilDiseno.SiguienteV(5, 10), 10, "SiguienteV(5,10)");
        Num(PerfilDiseno.SiguienteV(10, 10), 10, "SiguienteV(10,10)");
        Num(PerfilDiseno.SiguienteV(4, 30), 5, "SiguienteV(4,30)");
    }

    static List<double> Pack(double[] ideal, double[] anchos, double[] pesos, double min, double max, out double des)
    {
        return PerfilDiseno.Empaquetar1D(ideal, anchos, pesos, 0.15, min, max, out des);
    }

    static void Empaquetado()
    {
        double inf = double.PositiveInfinity;
        void Caso(string n, double[] ideal, double[] pesos, double min, double max, double[] esp, double? desEsp, double ancho = 0.52)
        {
            var c = Pack(ideal, ideal.Select(_ => ancho).ToArray(), pesos, min, max, out double des);
            bool ok = c.Count == esp.Length && c.Zip(esp, (a, b) => Cerca(a, b, 1e-9)).All(x => x);
            if (desEsp.HasValue) ok &= Cerca(des, desEsp.Value, 1e-9);
            Chequear(ok, $"Empaquetado {n}: [{string.Join(", ", c.Select(x => x.ToString("0.####")))}] des={des:0.####}");
        }
        Caso("E1", new[] { 1.0, 1.19 }, null, -inf, inf, new[] { 0.76, 1.43 }, null);
        Caso("E2", new[] { 1.0, 1.19 }, null, 0.6, 10, new[] { 0.86, 1.53 }, null);
        Caso("E3", new[] { 1.0, 1.19, 5.0 }, null, -inf, inf, new[] { 0.76, 1.43, 5.0 }, null);
        Caso("E4", new[] { 1.0, 1.5, 2.0 }, null, -inf, inf, new[] { 0.83, 1.50, 2.17 }, null);
        Caso("E5", new[] { 1.0, 1.19 }, null, 0, 1.0, new[] { 0.26, 0.93 }, 0.19);
        Caso("E6", new[] { 0.0, 3.0 }, null, -inf, inf, new[] { 0.0, 3.0 }, 0);
        Caso("E7", new[] { 1.0, 1.19 }, new[] { 100.0, 50.0 }, -inf, inf, new[] { 0.84, 1.51 }, null);
        Caso("E8", new[] { 9.2, 9.9 }, null, 0, 10, new[] { 9.07, 9.74 }, 0);
        Caso("E9", new double[0], null, -inf, inf, new double[0], 0);
        Caso("E10", new[] { 5.0 }, null, 0, 10, new[] { 6.0 }, 2, 12);
    }

    // ------------------------------------------------------------ PerfilRecorrido
    static (List<GNodo>, List<GArista>) Grafo((double x, double y)[] nodos, (int a, int b)[] aristas)
    {
        var n = nodos.Select((p, i) => new GNodo { Id = i, X = p.x, Y = p.y }).ToList();
        var a = new List<GArista>();
        for (int i = 0; i < aristas.Length; i++)
        {
            var e = new GArista { Id = i, A = aristas[i].a, B = aristas[i].b };
            PerfilRecorrido.CompletarArista(e, n[e.A], n[e.B]);
            a.Add(e); n[e.A].Aristas.Add(i); if (e.B != e.A) n[e.B].Aristas.Add(i);
        }
        return (n, a);
    }
    static string Ids(List<PasoG> p) { return string.Join(",", p.Select(x => x.Arista)); }

    static void Recorrido()
    {
        var (n1, a1) = Grafo(new[] { (0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0), (20.0, 10.0) }, new[] { (0, 1), (1, 2), (2, 3), (2, 4) });
        Igual(Ids(PerfilRecorrido.Recorrer(n1, a1, 0)), "0,1,2", "R1 recorrido");
        Igual(PerfilRecorrido.LadoRamal(new V2(1, 0), a1[3].DirSalidaA), "LT", "R1 ramal LT");
        double c30 = Math.Cos(Math.PI / 6), s30 = Math.Sin(Math.PI / 6), c35 = Math.Cos(35 * Math.PI / 180), s35 = Math.Sin(35 * Math.PI / 180);
        var (n2, a2) = Grafo(new[] { (0.0, 0.0), (10.0, 0.0), (10 + 10 * c30, 10 * s30), (10 + 10 * c35, -10 * s35) }, new[] { (0, 1), (1, 2), (1, 3) });
        Igual(Ids(PerfilRecorrido.Recorrer(n2, a2, 0)), "0", "R2 empate");
        double c50 = Math.Cos(50 * Math.PI / 180), s50 = Math.Sin(50 * Math.PI / 180);
        var (n3, a3) = Grafo(new[] { (0.0, 0.0), (10.0, 0.0), (10 + 10 * c50, 10 * s50) }, new[] { (0, 1), (1, 2) });
        Igual(Ids(PerfilRecorrido.Recorrer(n3, a3, 0)), "0", "R3 50° se para");
        // R4: lazo cerrado de 12 lados (30° en cada vértice; un cuadrado de 90° no pasaría el tope de 45°)
        var pol = Enumerable.Range(0, 12).Select(i => (10 * Math.Cos(i * Math.PI / 6), 10 * Math.Sin(i * Math.PI / 6))).ToArray();
        var (n4, a4) = Grafo(pol, Enumerable.Range(0, 12).Select(i => (i, (i + 1) % 12)).ToArray());
        var r4 = PerfilRecorrido.Recorrer(n4, a4, 0);
        Chequear(r4.Count == 12 && r4.Select(p => p.Arista).Distinct().Count() == 12, "R4 lazo sin repetir: " + Ids(r4));
        PerfilRecorrido.Tangentes(new V2(0, 0), new V2(10, 10), Math.Tan(22.5 * Math.PI / 180), out V2 t0, out V2 t1);
        Chequear(Cerca(t0.X, 1, 1e-9) && Cerca(t0.Y, 0, 1e-9) && Cerca(t1.X, 0, 1e-9) && Cerca(t1.Y, 1, 1e-9), "R5 tangentes");
        var pm = PerfilRecorrido.PuntoMedioArco(new V2(0, 0), new V2(10, 10), Math.Tan(22.5 * Math.PI / 180));
        double dist = (pm - new V2(5, 5)).Largo;
        bool derecha = new V2(10, 10).Cross(pm) < 0;      // bulge > 0 (antihorario) → arco a la DERECHA de la cuerda
        Chequear(Cerca(dist, 5 * Math.Sqrt(2) * Math.Tan(22.5 * Math.PI / 180), 1e-9) && derecha && Cerca(pm.X, 10 * Math.Cos(Math.PI / 4), 1e-9),
                 $"R5 punto medio del arco ({pm.X:0.###},{pm.Y:0.###})");
        var traza = new List<V2Bulge> { new V2Bulge { X = -50 }, new V2Bulge { X = 0 }, new V2Bulge { X = 100 }, new V2Bulge { X = 150 } };
        var c1 = PerfilRecorrido.CortarTraza(traza, 50, new V2(50, -10), new V2(50, 10));
        Chequear(c1.Count == 1 && Cerca(c1[0].Estacion, 150) && Cerca(c1[0].AnguloDeg, 90), "R6 corte a 90°");
        var c2 = PerfilRecorrido.CortarTraza(traza, 50, new V2(20, -1), new V2(30, 1));
        Chequear(c2.Count == 1 && Cerca(c2[0].AnguloDeg, 11.3099, 1e-3), "R6 corte a 11.31°");
        var c3 = PerfilRecorrido.CortarTraza(traza, 50, new V2(60, 5), new V2(60, 5));
        Chequear(c3.Count == 0, "R6 segmento degenerado");
        var (n7, a7) = Grafo(new[] { (0.0, 0.0), (10.0, 0.0), (-10.0, 0.0), (0.0, 10.0) }, new[] { (0, 1), (0, 2), (0, 3) });
        var r7 = PerfilRecorrido.RecorrerDesdeNodo(n7, a7, 0);
        Chequear(r7.Count == 2 && r7.Select(p => p.Arista).OrderBy(x => x).SequenceEqual(new[] { 0, 1 }), "R7 par 0°/180°: " + Ids(r7));
        var (n8, a8) = Grafo(new[] { (0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (20.0, 0.0) }, new[] { (0, 1), (1, 2), (1, 3) });
        Chequear(!a8[1].Valida, "R8 arista degenerada no válida");
        Igual(Ids(PerfilRecorrido.Recorrer(n8, a8, 0)), "0,2", "R8 recorrido salta la degenerada");
        Chequear(PerfilRecorrido.Recorrer(n8, a8, 1).Count == 0, "R9 vertical elegida → vacío");
        var cA = new CandidatoAccesorio { Id = 1, X = 1.5, Y = 0, Z = 100, Red = "CROSS-CONNECTS", DiamPrincipalFt = double.NaN, LargoTotalFt = double.NaN };
        var cB = new CandidatoAccesorio { Id = 2, X = 1.5, Y = 0, Z = 106, Red = "RED-AGUA", DiamPrincipalFt = double.NaN, LargoTotalFt = double.NaN };
        Chequear(PerfilRecorrido.ElegirAccesorio(0, 0, 100, new V2(1, 0), 0.667, new[] { cA, cB }, "RED-AGUA") == 1, "R10 filtro dz");
        var cO = new CandidatoAccesorio { Id = 3, X = 1.5, Y = 0, Z = 100, Red = "OTRA", DiamPrincipalFt = double.NaN, LargoTotalFt = double.NaN };
        var cR = new CandidatoAccesorio { Id = 4, X = 1.5, Y = 0, Z = 100, Red = "RED-AGUA", DiamPrincipalFt = double.NaN, LargoTotalFt = double.NaN };
        Chequear(PerfilRecorrido.ElegirAccesorio(0, 0, 100, new V2(1, 0), 0.667, new[] { cO, cR }, "red-agua") == 4, "R11 desempate por red");
        var cD = new CandidatoAccesorio { Id = 5, X = -1.5, Y = 0.2, Z = 100, DiamPrincipalFt = double.NaN, LargoTotalFt = double.NaN };
        Chequear(PerfilRecorrido.ElegirAccesorio(0, 0, 100, new V2(1, 0), 0.667, new[] { cD }, "") == -1, "R12 detrás");
        var cL = new CandidatoAccesorio { Id = 6, X = 3.0, Y = 0, Z = 100, DiamPrincipalFt = double.NaN, LargoTotalFt = 5.6 };
        Chequear(PerfilRecorrido.ElegirAccesorio(0, 0, 100, new V2(1, 0), 0.667, new[] { cL }, "") == 6, "R13 Ralc por LARGO_TOTAL_FT");
        var tz = PerfilRecorrido.Traza(new List<V2> { new V2(0, 0), new V2(10, 0), new V2(20, 0) }, new List<double> { 0, 0 }, 25);
        Chequear(tz.Count == 2 && Cerca(tz[0].X, -25) && Cerca(tz[1].X, 45), "R14 traza colineal");
    }

    // ------------------------------------------------------------ Maquetar
    static BloqueTexto B(string id, double est, double alto, int prio, FranjaTipo f, double z, bool alternar = true, double ancho = 0.52)
    {
        return new BloqueTexto { Id = id, EstAncla = est, ZAncla = z, Alto = alto, Ancho = ancho, Medido = true, Prioridad = prio, Franja = f,
                                 PuedeAlternar = alternar, Lineas = new[] { "A", "B", "C" } };
    }
    static FilaTramo T(string id, double a, double b, string l1, string l2, string l3 = "")
    { return new FilaTramo { Id = id, EstIni = a, EstFin = b, L1 = l1, L2 = l2, L3 = l3 }; }
    static double CentroX(BloqueTexto b) { return b.X0 + b.Ancho / 2; }

    static void M1()
    {
        var e = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 160.58, EstMinPermitida = 50, EstMaxPermitida = 210.58, ZMinDibujo = 743.60, ZMaxDibujo = 750.60 };
        var u1 = B("U1", 100.00, 1.52, 100, FranjaTipo.Superior, 745.0, false); var u2 = B("U2", 101.87, 1.42, 90, FranjaTipo.Superior, 745.0);
        var u3 = B("U3", 158.92, 1.30, 90, FranjaTipo.Superior, 745.0); var u4 = B("U4", 160.58, 1.52, 100, FranjaTipo.Superior, 745.0, false);
        var l1 = B("L1", 154.86, 1.60, 60, FranjaTipo.Inferior, 744.20);
        e.Bloques.AddRange(new[] { u1, u2, u3, u4, l1 });
        var t1 = T("T1", 100, 105, "INSTALL 5 LF OF", "NEW 8\" DI PIPE"); var t2 = T("T2", 105, 155, "INSTALL 50 LF OF", "NEW 8\" DI PIPE");
        var t3 = T("T3", 155, 160.58, "INSTALL 6 LF OF", "NEW 8\" DI PIPE");
        e.Tramos.AddRange(new[] { t1, t2, t3 });
        var r = PerfilDiseno.Maquetar(e);
        Num(r.V, 4, "M1 V"); Num(r.VE, 2.5, "M1 VE");
        Chequear(Cerca(r.Int.EstMayor, 100) && Cerca(r.Int.EstMenor, 10) && Cerca(r.Int.CotaMayor, 10) && Cerca(r.Int.CotaMenor, 2), "M1 Int");
        Num(r.StationStart, 85, "M1 StationStart"); Num(r.StationEnd, 180, "M1 StationEnd"); Num(r.AnchoMarco, 9.5, "M1 AnchoMarco");
        Num(r.ElevationMin, 734, "M1 ElevationMin"); Num(r.ElevationMax, 762, "M1 ElevationMax"); Num(r.AltoMarco, 7.0, "M1 AltoMarco");
        Num(r.HolguraSup, 0.658824, "M1 HolguraSup", 1e-6); Num(r.HolguraInf, 0.256471, "M1 HolguraInf", 1e-6);
        Num(r.YBaseSup, 4.808824, "M1 YBaseSup", 1e-6); Num(r.YTopeInf, 2.143529, "M1 YTopeInf", 1e-6);
        Num(CentroX(u1), 0.52, "M1 U1 x"); Num(CentroX(u2), 1.19, "M1 U2 x"); Num(CentroX(u3), 7.868, "M1 U3 x"); Num(CentroX(u4), 8.538, "M1 U4 x");
        Chequear(new[] { u1, u2, u3, u4 }.All(b => Cerca(b.Y0, 4.808824, 1e-6)), "M1 Y0 superiores");
        Num(CentroX(l1), 6.69, "M1 L1 x"); Num(l1.Y0, 0.543529, "M1 L1 Y0", 1e-6);
        Chequear(t1.Fila == 1 && t1.NumLineas == 2 && Cerca(t1.X0 + t1.Ancho / 2, 1.75), "M1 T1 fila 1, 2 líneas, centro 1.75");
        Chequear(t2.Fila == 1 && t2.NumLineas == 1 && Cerca(t2.X0 + t2.Ancho / 2, 4.5) && Cerca(t2.Ancho, 2.9388), "M1 T2 1 línea, centro 4.5, ancho 2.9388");
        Chequear(t3.Fila == 1 && t3.NumLineas == 2 && Cerca(t3.X0 + t3.Ancho / 2, 7.279), "M1 T3 fila 1, centro 7.279");
        Num(r.YFila1Base, 6.53, "M1 YFila1Base"); Chequear(double.IsNaN(r.YFila2Base), "M1 YFila2Base NaN");
        Chequear(r.SinSolapes && r.CortesLeaderCaja.Count == 0 && r.PendientesExcedidas.Count == 0,
                 "M1 verificaciones: " + string.Join(" ", r.Solapes.Concat(r.FueraDeMarco).Concat(r.CrucesLeaders).Concat(r.CortesLeaderCaja).Concat(r.PendientesExcedidas)));
    }

    static EntradaMaquetacion Apinados(int n, double estFin, double estMax, bool alternar, bool recortar = false, string[] lineas = null)
    {
        var e = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = estFin, EstMinPermitida = 50, EstMaxPermitida = estMax, ZMinDibujo = 740, ZMaxDibujo = 745 };
        for (int i = 0; i < n; i++)
        {
            var b = B("B" + i.ToString("00"), 100 + i, 1.0, 90, FranjaTipo.Superior, 745, alternar);
            b.PuedeRecortar = recortar; if (lineas != null) b.Lineas = lineas;
            e.Bloques.Add(b);
        }
        return e;
    }

    static void M2()
    {
        var e = Apinados(10, 109, 159, true);
        var r = PerfilDiseno.Maquetar(e);
        var sup = e.Bloques.Where(b => b.FranjaFinal == FranjaTipo.Superior).ToList();
        var inf = e.Bloques.Where(b => b.FranjaFinal == FranjaTipo.Inferior).ToList();
        Chequear(sup.Count == 5 && inf.Count == 5 && sup.All(b => int.Parse(b.Id.Substring(1)) % 2 == 0), "M2 alterna pares/impares");
        Num(r.StationStart, 85, "M2 StationStart"); Num(r.StationEnd, 125, "M2 StationEnd");
        Num(r.HolguraSup, 0.552941, "M2 HolguraSup", 1e-6); Num(r.HolguraInf, 0.552941, "M2 HolguraInf", 1e-6);
        Num(r.ElevationMin, 732, "M2 ElevationMin"); Num(r.ElevationMax, 752, "M2 ElevationMax");
        Chequear(e.Bloques.All(b => b.Nivel == 1) && r.SinSolapes, "M2 niveles 1 y sin solapes");
    }

    static void M2b()
    {
        var e = Apinados(4, 103, 153, true);
        var r = PerfilDiseno.Maquetar(e);
        Num(r.StationStart, 85, "M2b StationStart"); Num(r.StationEnd, 120, "M2b StationEnd");
        Num(r.HolguraSup, 0.502941, "M2b HolguraSup", 1e-6); Num(r.ElevationMin, 738, "M2b ElevationMin");
        Num(r.YBaseSup, 2.252941, "M2b YBaseSup", 1e-6); Num(r.ElevationMax, 752, "M2b ElevationMax");
        Chequear(e.Bloques.All(b => b.FranjaFinal == FranjaTipo.Superior) && r.SinSolapes && r.PendientesExcedidas.Count == 0, "M2b todos arriba, sin solapes");
    }

    static void M3()
    {
        var ls = new[] { "PIPE STA 1+00.00", "8\" X 45%%d BEND", "TOP ELEV 745.43'" };
        var e = Apinados(20, 119, 169, false, true, ls);
        var r = PerfilDiseno.Maquetar(e);
        Chequear(r.Recortados.Count == 20 && e.Bloques.All(b => Cerca(b.Ancho, 0.32) && Cerca(b.Alto, 1.0)), "M3 recortados 20 (0.32 × 1.0)");
        Num(r.StationStart, 60, "M3 StationStart"); Num(r.StationEnd, 160, "M3 StationEnd"); Num(r.HolguraSup, 1.50, "M3 HolguraSup");
        Chequear(e.Bloques.All(b => b.Nivel == 1), "M3 escalonado no viable");
        Chequear(r.Avisos.Contains("Rótulos apretados en franja sup"), "M3 aviso");
        Chequear(r.SinSolapes && r.PendientesExcedidas.Count > 0, "M3 sin solapes y con pendientes excedidas: sol=" + string.Join(" ", r.Solapes)
                 + " fuera=" + string.Join(" ", r.FueraDeMarco) + " cruces=" + string.Join(" ", r.CrucesLeaders) + " pend=" + r.PendientesExcedidas.Count);
    }

    static void M4()
    {
        var e = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 208, EstMinPermitida = 50, EstMaxPermitida = 258, ZMinDibujo = 740, ZMaxDibujo = 745 };
        for (int j = 0; j < 25; j++) e.Bloques.Add(B("B" + j.ToString("00"), 100 + 4.5 * j, 1.0, 90, FranjaTipo.Superior, 745, false));
        var r = PerfilDiseno.Maquetar(e);
        bool niveles = e.Bloques.Select((b, j) => b.Nivel == (j % 2 == 0 ? 1 : 2)).All(x => x);
        Chequear(niveles, "M4 niveles alternos");
        bool xs = true;
        for (int j = 0; j < 25; j++) xs &= Cerca(CentroX(e.Bloques[j]), j % 2 == 0 ? 1.64 + 0.9 * (j / 2) : 2.23 + 0.9 * (j / 2), 1e-6);
        Chequear(xs, "M4 centros X por nivel");
        Num(r.StationStart, 85, "M4 StationStart"); Num(r.StationEnd, 225, "M4 StationEnd"); Num(r.HolguraSup, 0.20, "M4 HolguraSup");
        double ht = e.Bloques.Where(b => b.Nivel == 2).Min(b => b.Y0) + 1.0 - r.YBaseSup;
        Num(ht, 2.1, "M4 Ht");
        Chequear(r.SinSolapes && r.CortesLeaderCaja.Count == 0, "M4 sin solapes ni cortes: " + string.Join(" ", r.Solapes.Concat(r.CortesLeaderCaja)));
    }

    static void M5()
    {
        var r = PerfilDiseno.Maquetar(new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 150, EstMinPermitida = 50, EstMaxPermitida = 200, ZMinDibujo = 700, ZMaxDibujo = 740 });
        Chequear(Cerca(r.V, 5) && Cerca(r.VE, 2) && r.Avisos.Contains("VE reducida a 2"), $"M5 V={r.V} VE={r.VE} avisos={string.Join(";", r.Avisos)}");
    }

    static void M6()
    {
        var e = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 130, EstMinPermitida = 50, EstMaxPermitida = 180, ZMinDibujo = 743, ZMaxDibujo = 750.6 };
        var a = B("A", 100.0, 1.0, 90, FranjaTipo.Superior, 750.4); var b = B("B", 100.3, 1.0, 90, FranjaTipo.Superior, 744.0);
        e.Bloques.Add(a); e.Bloques.Add(b);
        e.Tramos.Add(T("T1", 100, 130, "INSTALL 30 LF OF", "NEW 8\" DI PIPE"));
        var r = PerfilDiseno.Maquetar(e);
        Chequear(r.CrucesLeaders.Count == 0 && b.X0 < a.X0 && r.SinSolapes, $"M6 sin cruces, B a la izquierda (A.X0={a.X0:0.###} B.X0={b.X0:0.###})");
        var l1 = new Leader { Id = "L1", X0 = 5.0, Y0 = 3, X1 = 1.0, Y1 = 0 }; var l2 = new Leader { Id = "L2", X0 = 5.7, Y0 = 3, X1 = 1.1, Y1 = 2.7 };
        var cr = PerfilDiseno.CrucesLeaders(new[] { l1, l2 });
        Chequear(cr.Count == 1 && cr[0] == "L1|L2", "M6 CrucesLeaders directo");
    }

    static void M7()
    {
        var e = new EntradaMaquetacion { S = 50, EstIni = 100, EstFin = 700, EstMinPermitida = 0, EstMaxPermitida = 900, ZMinDibujo = 740, ZMaxDibujo = 750 };
        for (int i = 0; i < 30; i++) e.Tramos.Add(T("T" + i.ToString("00"), 100 + 20 * i, 120 + 20 * i, "INSTALL 20 LF OF", "NEW 8\" PVC PIPE", "@ 0.52%"));
        var r = PerfilDiseno.Maquetar(e);
        var rot = e.Tramos.Where(t => !t.AVertical).ToList();
        Chequear(r.FueraDeMarco.Count == 0, "M7 nada fuera del marco: " + string.Join(" ", r.FueraDeMarco));
        Chequear(rot.Where(t => t.Fila == 2).All(t => t.ConLeader), "M7 fila 2 con leader");
        Chequear(e.Tramos.Any(t => t.AVertical) || rot.All(t => t.Fila == 1), "M7 desbordados a vertical");
    }

    static void M8()
    {
        var e = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 100.3, EstMinPermitida = 50, EstMaxPermitida = 150, ZMinDibujo = 740, ZMaxDibujo = 741 };
        e.Tramos.Add(T("T1", 100, 100.3, "INSTALL 1 LF OF", "NEW 8\" PVC PIPE"));
        var r = PerfilDiseno.Maquetar(e);
        Chequear(e.Tramos[0].Omitido && r.Paredes.Count == 0, "M8 tramo omitido sin paredes");
    }

    static void M9()
    {
        foreach (double s in new[] { 10.0, 50.0 })
        {
            var e = new EntradaMaquetacion { S = s, EstIni = 100, EstFin = 120, EstMinPermitida = 0, EstMaxPermitida = 400, ZMinDibujo = 740, ZMaxDibujo = 741 };
            e.Tramos.Add(T("T1", 100, 120, "INSTALL 20 LF OF", "NEW 8\" PVC PIPE"));
            var r = PerfilDiseno.Maquetar(e);
            Chequear(r.FueraDeMarco.Count == 0, $"M9 S={s} dentro del marco: " + string.Join(" ", r.FueraDeMarco));
        }
        var c10 = PerfilDiseno.ElegirEstacionesRecubrimiento(100, 120, 10, null, null, double.NaN);
        var c50 = PerfilDiseno.ElegirEstacionesRecubrimiento(100, 120, 50, null, null, double.NaN);
        Chequear(c10.Count == 2 && Cerca(c10[0], 103) && Cerca(c10[1], 117), "M9 recubrimientos S=10: " + string.Join(",", c10));
        Chequear(c50.Count == 1 && Cerca(c50[0], 110), "M9 recubrimientos S=50: " + string.Join(",", c50));
    }

    static void M10()
    {
        var e = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 150, EstMinPermitida = 0, EstMaxPermitida = 2000, ZMinDibujo = 740, ZMaxDibujo = 745 };
        e.TerrenoEst = new[] { 120.0, 125.0, 130.0, 1500.0, 140.0 };
        e.TerrenoZ = new[] { 744.0, 736.0, double.NaN, 800.0, 750.0 };
        var r = PerfilDiseno.Maquetar(e);
        var e0 = new EntradaMaquetacion { S = 10, EstIni = 100, EstFin = 150, EstMinPermitida = 0, EstMaxPermitida = 2000, ZMinDibujo = 740, ZMaxDibujo = 745 };
        var r0 = PerfilDiseno.Maquetar(e0);
        Chequear(r.ElevationMax < 790 && r.ElevationMin < r0.ElevationMin, $"M10 loma fuera ignorada y vaguada incluida (min {r.ElevationMin} vs {r0.ElevationMin}, max {r.ElevationMax})");
    }

    static void M11()
    {
        var r = PerfilDiseno.Maquetar(new EntradaMaquetacion { S = 20, EstIni = 100, EstFin = 200, EstMinPermitida = 0, EstMaxPermitida = 400, ZMinDibujo = 700, ZMaxDibujo = 760 });
        Chequear(Cerca(r.V, 10) && Cerca(r.VE, 2) && r.AltoMarco <= 12 + 1e-9, $"M11 V={r.V} VE={r.VE} alto={r.AltoMarco}");
    }

    static void Complementos()
    {
        var c = PerfilDiseno.ElegirEstacionesRecubrimiento(100, 120, 10, new List<double[]> { new[] { 102.5, 103.5 } }, null, double.NaN);
        Chequear(c.Count == 2 && Cerca(c[0], 104.5) && Cerca(c[1], 117), "Recubrimiento con leader: " + string.Join(",", c));
        double st = 85, en = 1205; PerfilDiseno.AjustarEstacionesExtremo(ref st, ref en, 40, 100, 0, 2000); Num(en, 1225, "AjustarEstacionesExtremo end");
        st = 95; en = 1300; PerfilDiseno.AjustarEstacionesExtremo(ref st, ref en, 40, 100, 0, 2000); Num(st, 75, "AjustarEstacionesExtremo start");
        st = 85; en = 180; PerfilDiseno.AjustarEstacionesExtremo(ref st, ref en, 10, 100, 0, 2000); Chequear(Cerca(st, 85) && Cerca(en, 180), "AjustarEstacionesExtremo sin cambios");
        var nod = new double[] { 100, 150, 230, 380, 560, 610, 790, 950, 1100 };
        var h20 = PerfilDiseno.PartirEnHojas(nod, 20);
        Chequear(h20.Count == 2 && Cerca(h20[0][0], 100) && Cerca(h20[0][1], 610) && Cerca(h20[1][1], 1100), "PartirEnHojas S=20: " + string.Join(" ", h20.Select(h => $"[{h[0]},{h[1]}]")));
        Chequear(PerfilDiseno.PartirEnHojas(nod, 40).Count == 1, "PartirEnHojas S=40 una hoja");
        var g = PerfilDiseno.AgruparCruces(new double[] { 120, 121, 122, 123, 124, 122 }, new[] { "ELEC", "ELEC", "ELEC", "ELEC", "ELEC", "AGUA" }, 10);
        Chequear(g.Count == 2 && g.Any(x => x.Count == 5) && g.Any(x => x.Count == 1), "AgruparCruces 5+1");
        Chequear(PerfilDiseno.AgruparCruces(new double[] { 120, 126 }, new[] { "ELEC", "ELEC" }, 10).Count == 2, "AgruparCruces separados");
        Chequear(!PerfilDiseno.CotaSeparacionCabe(1.0, 4) && PerfilDiseno.CotaSeparacionCabe(3.0, 4), "CotaSeparacionCabe");
        var k0 = new Caja { Id = "a", X0 = 0, Y0 = 0, X1 = 1, Y1 = 1 };
        Chequear(PerfilDiseno.Solapes(new[] { k0, new Caja { Id = "b", X0 = 0.99, Y0 = 0, X1 = 2, Y1 = 1 } }).Count == 0, "Solapes tolerancia");
        Chequear(PerfilDiseno.Solapes(new[] { k0, new Caja { Id = "b", X0 = 0.9, Y0 = 0, X1 = 2, Y1 = 1 } }).Count == 1, "Solapes real");
        Chequear(PerfilDiseno.FueraDeMarco(new[] { new Caja { Id = "f", X0 = 1, Y0 = 7.85, X1 = 2, Y1 = 8.02 } }, 10, 8).Count == 1, "FueraDeMarco");
        double r1 = PerfilDiseno.Calibrar(new[] { 12.0, 24, 36, 48, 60 }, new[] { 1.0, 2, 3, 4, 5 }, out double d1);
        Chequear(Cerca(r1, 12) && Cerca(d1, 0), "Calibrar 12×");
        double r2 = PerfilDiseno.Calibrar(new[] { 1.0, 1.02, 0.98, 2.5 }, new[] { 1.0, 1, 1, 1 }, out _);
        Chequear(Cerca(r2, 1.01, 1e-9) && Math.Abs(2.5 / r2 - 1) > 0.5, "Calibrar atípico");
    }
    // ------------------------------------------------------------ EnderezarNucleo (quiebres mínimos)
    static List<int> Quitar(double[] x, double[] y, double[] z = null, bool[] bloq = null, string[] pieza = null, double[] zIn = null)
    {
        int n = x.Length;
        z ??= Enumerable.Repeat(100.0, n).ToArray();
        return EnderezarNucleo.VerticesAQuitar(x, y, z, zIn ?? z, bloq ?? new bool[n], pieza ?? new string[n], 0.25, 0.01);
    }
    static string L(List<int> l) => "[" + string.Join(",", l) + "]";

    static void Enderezar()
    {
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.2, 0 })), "[1]", "Enderezar: quiebre 0.23° a 0.2 ft");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.5, 0 })), "[]", "Enderezar: desvío 0.5 ft > 0.25 (aunque gire 0.57°)");
        Igual(L(Quitar(new[] { 0.0, 10, 20 }, new[] { 0.0, 0.2, 0 })), "[]", "Enderezar: giro 2.3° > 2° (tramos cortos)");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 10, 0 })), "[]", "Enderezar: giro real 11°");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.2, 0 }, bloq: new[] { false, true, false })), "[]", "Enderezar: vértice con buzón/curva/ramal");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.2, 0 }, pieza: new[] { "", "HDPE~4 in", "" })), "[]", "Enderezar: pieza distinta a cada lado");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.2, 0 }, z: new[] { 100.0, 99.0, 98.0 })), "[1]", "Enderezar: pendiente uniforme");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.2, 0 }, z: new[] { 100.0, 99.5, 98.0 })), "[]", "Enderezar: cambio de pendiente en el vértice");
        Igual(L(Quitar(new[] { 0.0, 100, 200 }, new[] { 0.0, 0.2, 0 }, z: new[] { 100.0, 99.0, 98.0 }, zIn: new[] { 100.0, 99.2, 98.0 })), "[]", "Enderezar: caída en el vértice");
        // Muchos quiebres de 0.2 ft del mismo lado: se quitan mientras la recta final
        // no se aparte más de 0.25 ft de NINGÚN vértice original (no se acumula).
        var xs = new[] { 0.0, 100, 200, 300, 400, 500, 600 };
        var ys = new[] { 0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2 };
        Igual(L(Quitar(xs, ys)), "[1,2,3,4,5]", "Enderezar: recta inclinada con vértices colineales → un tubo");
        var ys2 = new[] { 0.0, 0.2, 0.4, 0.6, 0.4, 0.2, 0.0 };       // arco muy abierto: flecha 0.6 ft
        var q = Quitar(xs, ys2);
        bool ok = true; var viv = Enumerable.Range(0, 7).Where(i => !q.Contains(i)).ToList();
        for (int k = 0; k + 1 < viv.Count; k++)
            for (int j = viv[k] + 1; j < viv[k + 1]; j++)
            {
                double ax = xs[viv[k]], ay = ys2[viv[k]], bx = xs[viv[k + 1]], by = ys2[viv[k + 1]];
                double dist = Math.Abs((bx - ax) * (ys2[j] - ay) - (by - ay) * (xs[j] - ax)) / Math.Sqrt((bx - ax) * (bx - ax) + (by - ay) * (by - ay));
                if (dist > 0.25 + 1e-9) ok = false;
            }
        Chequear(ok && q.Count > 0 && q.Count < 5, "Enderezar: curva abierta (flecha 0.6) → desvío ≤ 0.25 en cada tramo " + L(q));
        Igual(L(Quitar(new[] { 0.0, 100 }, new[] { 0.0, 0 })), "[]", "Enderezar: dos vértices, nada que quitar");
        // Ancla de un codo: 0 = inicio, 1 = CURVA, 2 = ancla recta (0°), 3 = CURVA, 4 = fin.
        var cx = new[] { 0.0, 100, 150, 200, 300 }; var cy = new[] { 0.0, 50, 50, 50, 0 };
        var cv = new[] { false, true, false, true, false };
        Igual(L(EnderezarNucleo.VerticesAQuitar(cx, cy, new double[5], new double[5], cv, new string[5], 0.25, 0.01, cv)), "[]",
              "Enderezar: el ancla recta entre dos codos se conserva");
        // Dos vértices casi rectos junto a un codo: el que queda pegado al codo es su ancla.
        var kx = new[] { 0.0, 100, 150, 200, 250 }; var ky = new[] { 0.0, 50, 50.1, 50, 50 };
        var av = new[] { false, true, false, false, false };
        Igual(L(EnderezarNucleo.VerticesAQuitar(kx, ky, new double[5], new double[5], av, new string[5], 0.25, 0.01, av)), "[3]",
              "Enderezar: junto a un codo solo se quita el que no es ancla");
    }
}
