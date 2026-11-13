using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Civil3DBasico;

// Casos de SuperficiesNucleo (IMPORTAR_RED paso 6b, superficies de la app; 2026-11-11, 2.1.0).
internal static partial class Program
{
    const string XmlPies =
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" +
        "<LandXML xmlns=\"http://www.landxml.org/schema/LandXML-1.2\" version=\"1.2\">\n" +
        "  <Units><Imperial linearUnit=\"USSurveyFoot\" areaUnit=\"squareFoot\" volumeUnit=\"cubicYard\"/></Units>\n" +
        "  <Surfaces><Surface name=\"TERRENO\"><Definition surfType=\"TIN\" elevMin=\"10\" elevMax=\"12\">\n" +
        "    <Pnts><P id=\"1\">2000.5 1000.25 10</P><P id=\"2\">2000.5 1100.25 11</P><P id=\"3\">2100.5 1000.25 12</P></Pnts>\n" +
        "    <Faces><F>1 2 3</F></Faces></Definition></Surface></Surfaces>\n</LandXML>\n";

    static void Superficies()
    {
        // Lectura del XDATA
        var xd = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["NAME"] = "TERRENO", ["ARCHIVO"] = "Proyecto_superficies/TERRENO.xml", ["ARCHIVO_ABS"] = @"C:\x\TERRENO.xml",
            ["SHA1"] = "ABCDEF", ["N_PUNTOS"] = "3", ["N_TRIANGULOS"] = "1", ["ZMIN"] = "10", ["ZMAX"] = "12.000000000001",
            ["XMIN"] = "1000.25", ["YMIN"] = "2000.5", ["XMAX"] = "1100.25", ["YMAX"] = "2100.5", ["UNIDAD"] = "USSurveyFoot",
            ["MUESTRA_2"] = "1033.583333,2033.833333,11", ["MUESTRA_1"] = "1000.25,2000.5,10", ["MUESTRA_3"] = "1,2",
            ["FUENTE"] = "cliente.tif", ["CRS"] = "EPSG:32717",
        };
        var r = SuperficiesNucleo.Leer(xd);
        Igual(r.Nombre, "TERRENO", "Superficies: NAME");
        Igual(r.Sha1, "abcdef", "Superficies: SHA1 en minúsculas");
        Chequear(r.NPuntos == 3 && r.NTriangulos == 1, "Superficies: N_PUNTOS / N_TRIANGULOS");
        Num(r.ZMax ?? 0, 12.000000000001, "Superficies: ZMAX con precisión completa", 1e-15);
        Chequear(r.Muestras.Count == 2, "Superficies: la muestra incompleta («1,2») se ignora");
        Chequear(r.Muestras.Count == 2 && r.Muestras[0].X == 1000.25 && r.Muestras[1].Z == 11, "Superficies: MUESTRA_n en orden de n");
        var xd10 = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int i = 1; i <= 10; i++) xd10["MUESTRA_" + i] = $"{i}.5,{i * 2},{i * 3}";
        var r10 = SuperficiesNucleo.Leer(xd10);
        Chequear(r10.Muestras.Count == 10 && r10.Muestras[9].X == 10.5 && r10.Muestras[1].X == 2.5, "Superficies: 10 muestras, MUESTRA_10 después de MUESTRA_2");
        var sinAbs = new Dictionary<string, string>(xd, StringComparer.OrdinalIgnoreCase);
        sinAbs.Remove("ARCHIVO_ABS");
        var rSinAbs = SuperficiesNucleo.Leer(sinAbs);
        Chequear(rSinAbs.ArchivoAbs == "", "Superficies: ARCHIVO_ABS puede faltar");
        Igual(SuperficiesNucleo.ResolverRuta(rSinAbs, new[] { @"D:\obra" }, p => p == @"D:\obra\Proyecto_superficies\TERRENO.xml") ?? "",
            @"D:\obra\Proyecto_superficies\TERRENO.xml", "Superficies: sin ARCHIVO_ABS usa el relativo");
        Chequear(SuperficiesNucleo.ResolverRuta(rSinAbs, new[] { @"D:\otra" }, _ => false) == null, "Superficies: sin ARCHIVO_ABS y sin relativo → null");
        Chequear(SuperficiesNucleo.Leer(new Dictionary<string, string>()).NPuntos == null, "Superficies: sin datos → null");

        // Ruta: relativa a la carpeta del dibujo, si no la absoluta
        var hay = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { @"D:\obra\Proyecto_superficies\TERRENO.xml", @"C:\x\TERRENO.xml" };
        Igual(SuperficiesNucleo.ResolverRuta(r, new[] { @"D:\otra", @"D:\obra" }, hay.Contains) ?? "", @"D:\obra\Proyecto_superficies\TERRENO.xml",
            "Superficies: ARCHIVO relativo a la carpeta del dibujo");
        Igual(SuperficiesNucleo.ResolverRuta(r, new[] { @"D:\otra" }, hay.Contains) ?? "", @"C:\x\TERRENO.xml", "Superficies: si no, ARCHIVO_ABS");
        Chequear(SuperficiesNucleo.ResolverRuta(r, new[] { @"D:\otra" }, _ => false) == null, "Superficies: ninguno → null");

        // SHA1 conocido de «abc»
        Igual(SuperficiesNucleo.Sha1Hex(Encoding.ASCII.GetBytes("abc")), "a9993e364706816aba3e25717850c26c9cd0d89d", "Superficies: SHA1");

        // Unidades
        Igual(SuperficiesNucleo.UnidadDelDibujo(false, false), "foot", "Superficies: dibujo en pies");
        Igual(SuperficiesNucleo.UnidadDelDibujo(false, true), "USSurveyFoot", "Superficies: dibujo en pie topográfico");
        Igual(SuperficiesNucleo.UnidadDelDibujo(true, true), "meter", "Superficies: dibujo en metros");
        Igual(SuperficiesNucleo.UnidadDelArchivo(XmlPies), "USSurveyFoot", "Superficies: unidad del archivo");
        string a = SuperficiesNucleo.ReescribirUnidades(XmlPies, "foot");
        Igual(SuperficiesNucleo.UnidadDelArchivo(a), "foot", "Superficies: <Units> reescrito a foot");
        Chequear(a.Contains("<P id=\"3\">2100.5 1000.25 12</P>") && a.Contains("<F>1 2 3</F>"), "Superficies: puntos y caras intactos");
        Chequear(Recortar(a) == Recortar(XmlPies), "Superficies: fuera de <Units> nada cambia");
        string m = SuperficiesNucleo.ReescribirUnidades(XmlPies, "meter");
        Chequear(m.Contains("<Metric linearUnit=\"meter\"") && !m.Contains("<Imperial"), "Superficies: <Units> a metros");
        string conCs = XmlPies.Replace("<Surfaces>", "<CoordinateSystem epsgCode=\"32717\"></CoordinateSystem><Surfaces>");
        Chequear(!SuperficiesNucleo.ReescribirUnidades(conCs, "foot").Contains("CoordinateSystem"), "Superficies: se quita <CoordinateSystem>");
        string sinUnits = XmlPies.Replace("  <Units><Imperial linearUnit=\"USSurveyFoot\" areaUnit=\"squareFoot\" volumeUnit=\"cubicYard\"/></Units>\n", "");
        string b = SuperficiesNucleo.ReescribirUnidades(sinUnits, "foot");
        Chequear(b.IndexOf("<Units>") > b.IndexOf("<LandXML") && SuperficiesNucleo.UnidadDelArchivo(b) == "foot", "Superficies: sin <Units> se agrega tras <LandXML>");
        string auto = XmlPies.Replace("<Units><Imperial linearUnit=\"USSurveyFoot\" areaUnit=\"squareFoot\" volumeUnit=\"cubicYard\"/></Units>", "<Units/>");
        Igual(SuperficiesNucleo.UnidadDelArchivo(SuperficiesNucleo.ReescribirUnidades(auto, "foot")), "foot", "Superficies: <Units/> vacío");
        bool fallo = false;
        try { SuperficiesNucleo.ReescribirUnidades("<algo/>", "foot"); } catch (FormatException) { fallo = true; }
        Chequear(fallo, "Superficies: no es LandXML → error");
        Igual(SuperficiesNucleo.Texto(new byte[] { 0xEF, 0xBB, 0xBF, (byte)'<', (byte)'a' }), "<a", "Superficies: BOM fuera");

        // Nombres
        Igual(SuperficiesNucleo.NombreLibre("TERRENO", new[] { "otra" }), "TERRENO", "Superficies: nombre libre");
        Igual(SuperficiesNucleo.NombreLibre("TERRENO", new[] { "terreno", "TERRENO (2)" }), "TERRENO (3)", "Superficies: «(3)» si «(2)» está");

        // Comparar
        var med = new SuperficiesNucleo.Medido { NPuntos = 3, NTriangulos = 1, ZMin = 10, ZMax = 12, XMin = 1000.25, YMin = 2000.5, XMax = 1100.25, YMax = 2100.5 };
        Func<double, double, double?> plano = (x, y) => 10 + (y - 2000.5) / 100.0 * 2 + (x - 1000.25) / 100.0 * 1;
        var l = SuperficiesNucleo.Comparar(r, med, plano);
        Chequear(l.All(q => q.Ok), "Superficies: todo coincide → ✔ (" + string.Join(" | ", l.Where(q => !q.Ok)) + ")");
        Chequear(SuperficiesNucleo.Coincide(r, med), "Superficies: Coincide");
        var med2 = new SuperficiesNucleo.Medido { NPuntos = 4, NTriangulos = 1, ZMin = 10, ZMax = 12, XMin = 1000.25, YMin = 2000.5, XMax = 1100.25, YMax = 2100.5 };
        Chequear(!SuperficiesNucleo.Coincide(r, med2), "Superficies: otro número de puntos → no coincide");
        var med3 = new SuperficiesNucleo.Medido { NPuntos = 3, NTriangulos = 1, ZMin = 10, ZMax = 12.00001, XMin = 1000.25, YMin = 2000.5, XMax = 1100.25, YMax = 2100.5 };
        Chequear(SuperficiesNucleo.Comparar(r, med3, null).Count(q => !q.Ok) == 1, "Superficies: ZMAX fuera de ±1e-6 → ⚠");
        var lm = SuperficiesNucleo.Comparar(r, med, (x, y) => plano(x, y) + 0.001);
        Chequear(lm.Count(q => !q.Ok) == 2, "Superficies: muestra fuera de ±1e-4 → ⚠ con detalle");
        var lf = SuperficiesNucleo.Comparar(r, med, (x, y) => null);
        Chequear(lf.Any(q => !q.Ok && q.Texto.Contains("fuera")), "Superficies: muestra fuera de la superficie → ⚠");
        var lt = SuperficiesNucleo.Comparar(r, med, (x, y) => throw new InvalidOperationException());
        Chequear(lt.Count(q => !q.Ok) == 2, "Superficies: FindElevationAtXY que falla → ⚠, no rompe");
    }

    static string Recortar(string xml)
    {
        int i = xml.IndexOf("<Units"), j = xml.IndexOf("</Units>") + "</Units>".Length;
        return xml.Substring(0, i) + xml.Substring(j);
    }
}
