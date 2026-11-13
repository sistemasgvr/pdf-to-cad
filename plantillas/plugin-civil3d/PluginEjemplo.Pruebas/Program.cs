using System;
using Civil3DBasico.Ejemplo;

// Arnés de la lógica pura. `dotnet run -c Release` → código de salida 0 = todo PASA.
// Regla: cada bug corregido suma aquí un caso que FALLABA antes del arreglo.
internal static class Program
{
    static int fallos, total;

    static void Chequear(bool ok, string caso)
    {
        total++;
        if (ok) Console.WriteLine("  PASA   " + caso);
        else { fallos++; Console.WriteLine("  FALLA  " + caso); }
    }

    static void Num(double real, double esperado, string caso, double tol = 1e-6)
    {
        Chequear(Math.Abs(real - esperado) <= tol, caso + $" → {real:G9} (esperado {esperado:G9})");
    }

    static int Main()
    {
        Brida();
        Console.WriteLine($"\n{total - fallos}/{total} comprobaciones PASAN" + (fallos > 0 ? $" — {fallos} FALLA(N)" : ""));
        return fallos == 0 ? 0 : 1;
    }

    static void Brida()
    {
        Console.WriteLine("CalculoBrida");

        ResultadoBrida b8 = CalculoBrida.Calcular(8);
        Chequear(b8.Valido, "8\" es válido");
        Num(b8.DiametroExteriorIn, 13.5, "8\" diámetro exterior");
        Chequear(b8.NumeroPernos == 8 && b8.Agujeros.Count == 8, "8\" lleva 8 pernos y 8 agujeros");
        Num(b8.Agujeros[0].X, 11.75 / 2, "8\" primer agujero sobre +X");
        Num(b8.Agujeros[0].Y, 0, "8\" primer agujero en Y = 0");
        // Todos los agujeros sobre el círculo de pernos.
        bool enCirculo = true;
        foreach (Punto2D p in b8.Agujeros)
            enCirculo &= Math.Abs(Math.Sqrt(p.X * p.X + p.Y * p.Y) - 11.75 / 2) < 1e-9;
        Chequear(enCirculo, "8\" agujeros sobre el círculo de pernos");

        // Tolerancia: 7.999 es la de 8".
        Chequear(CalculoBrida.Calcular(7.999).Valido, "7.999\" se toma como 8\"");

        // Entradas inválidas: nunca excepción, siempre un Error legible.
        ResultadoBrida b5 = CalculoBrida.Calcular(5);
        Chequear(!b5.Valido && b5.Error.Length > 0, "5\" no está en la tabla → error con mensaje");
        Chequear(!CalculoBrida.Calcular(0).Valido, "0\" es inválido");
        Chequear(!CalculoBrida.Calcular(double.NaN).Valido, "NaN es inválido");

        Num(CalculoBrida.APies(6), 0.5, "6 pulgadas = 0.5 pies");
    }
}
