using System;
using System.Collections.Generic;
using Civil3DBasico;

// Casos de AlturaBuzonNucleo (IMPORTAR_RED: tapa y fondo del buzón sin que Civil 3D corrija la altura;
// reporte 2026-11-13, «Structure - (6)… exceeded the allowed 'Rim to Sump Height' range»).
internal static partial class Program
{
    // Simula a Civil 3D: aplica cada escritura y, si la altura sale de [min, max], la corrige (lo que avisa).
    static (double rim, double sump, int correcciones) Simular(double rim0, double sump0,
        List<(bool tapa, double valor)> pasos, double min, double max)
    {
        double r = rim0, s = sump0; int n = 0;
        foreach (var (tapa, valor) in pasos)
        {
            if (tapa) { r = valor; if (r - s > max + 1e-9) { r = s + max; n++; } else if (r - s < min - 1e-9) { r = s + min; n++; } }
            else { s = valor; if (r - s > max + 1e-9) { s = r - max; n++; } else if (r - s < min - 1e-9) { s = r - min; n++; } }
        }
        return (r, s, n);
    }

    static void CasoAltura(string nombre, double rim0, double sump0, double rim, double sump, double min, double max,
                           bool conRango = true)
    {
        var pasos = conRango ? AlturaBuzonNucleo.Pasos(rim0, sump0, rim, sump, min, max)
                             : AlturaBuzonNucleo.Pasos(rim0, sump0, rim, sump);
        var (r, s, n) = Simular(rim0, sump0, pasos, min, max);
        Chequear(n == 0 && Cerca(r, rim, 1e-6) && Cerca(s, sump, 1e-6),
            $"AlturaBuzon {nombre} → tapa {r:F3} fondo {s:F3}, {n} corrección(es) de Civil 3D, {pasos.Count} paso(s)");
    }

    static void AlturaBuzon()
    {
        // Lo de antes (tapa y luego fondo) hacía que Civil 3D corrigiera: buzón creado a la cota de la tapa con la
        // altura por defecto, fondo pedido mucho más abajo.
        var viejo = new List<(bool, double)> { (true, 100.0), (false, 85.0) };
        Chequear(Simular(100, 95, viejo, 4, 20).correcciones == 0, "AlturaBuzon: control (tapa→fondo sin salir del rango)");
        Chequear(Simular(100, 95, new List<(bool, double)> { (true, 50.0), (false, 45.0) }, 4, 20).correcciones >= 1, "AlturaBuzon: control (tapa→fondo con traslado grande corrige)");

        CasoAltura("tapa primero", 100, 95, 100, 85, 4, 20);
        CasoAltura("fondo primero", 100, 95, 92, 85, 4, 20);           // tapa primero daría 92−95 < 0
        CasoAltura("traslado grande hacia abajo", 100, 95, 50, 45, 4, 20);
        CasoAltura("traslado grande hacia arriba", 0, -5, 300, 290, 4, 20);
        CasoAltura("sin rango conocido: entre la altura actual y la pedida", 100, 95, 50, 40, 4, 20, conRango: false);
        Chequear(AlturaBuzonNucleo.Pasos(10, 5, 10, 5, 4, 20).Count == 0, "AlturaBuzon: sin cambios, sin escrituras");
        var sinHolgura = AlturaBuzonNucleo.Pasos(100, 95, 50, 45);     // h = 5 antes y después, sin rango: no hay pasos que valgan
        Chequear(sinHolgura.Count == 2 && sinHolgura[0].tapa, "AlturaBuzon: sin holgura ni rango, orden de siempre");

        // Unidades del rango
        Chequear(AlturaBuzonNucleo.FactorUnidades(60, 5, "") == 1.0 / 12.0, "AlturaBuzon: valor ×12 = pulgadas");
        Chequear(AlturaBuzonNucleo.FactorUnidades(5, 5, "inch") == 1.0, "AlturaBuzon: valor ×1 = pies (manda sobre «inch»)");
        Chequear(AlturaBuzonNucleo.FactorUnidades(7, 5, "inch") == 1.0 / 12.0, "AlturaBuzon: valor distinto → unidad escrita");
        Chequear(AlturaBuzonNucleo.FactorUnidades(null, 5, "ft") == 1.0, "AlturaBuzon: sin valor, «ft»");
        Chequear(AlturaBuzonNucleo.FactorUnidades(7, 5, "") == null, "AlturaBuzon: sin pista de unidades → null");
    }
}
