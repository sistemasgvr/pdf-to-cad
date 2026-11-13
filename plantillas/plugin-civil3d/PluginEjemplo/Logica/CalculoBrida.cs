using System;
using System.Collections.Generic;

// LÓGICA PURA: sin «using Autodesk». Entradas (números) → resultado (números y geometría).
// Se prueba en PluginEjemplo.Pruebas sin abrir AutoCAD y es lo que se integra en el plugin principal.
namespace Civil3DBasico.Ejemplo
{
    /// <summary>Punto 2D en pulgadas, en el plano de la cara de la brida (centro = 0,0).</summary>
    public struct Punto2D
    {
        public double X;
        public double Y;
        public Punto2D(double x, double y) { X = x; Y = y; }
    }

    /// <summary>Medidas de una brida, en PULGADAS. Si <see cref="Valido"/> es false, ver <see cref="Error"/>.</summary>
    public sealed class ResultadoBrida
    {
        public bool Valido;
        public string Error = "";
        public double DiametroNominalIn;
        public double DiametroExteriorIn;
        public double EspesorIn;
        public double DiametroInteriorIn;
        public double CirculoPernosIn;
        public double DiametroAgujeroIn;
        public int NumeroPernos;
        /// <summary>Centros de los agujeros de pernos (pulgadas), el primero sobre +X, sentido antihorario.</summary>
        public List<Punto2D> Agujeros = new List<Punto2D>();
    }

    /// <summary>
    /// Ejemplo: medidas de una brida a partir del diámetro nominal de la tubería.
    /// Valores de EJEMPLO tipo ASME B16.5 clase 150 (verificar con la norma antes de usarlos en serio).
    /// </summary>
    public static class CalculoBrida
    {
        // nominal, exterior, espesor, círculo de pernos, diámetro de agujero, nº de pernos (pulgadas)
        static readonly double[,] Tabla =
        {
            {  4,  9.00, 0.94,  7.50, 0.75,  8 },
            {  6, 11.00, 1.00,  9.50, 0.88,  8 },
            {  8, 13.50, 1.12, 11.75, 0.88,  8 },
            { 12, 19.00, 1.25, 17.00, 1.00, 12 },
        };

        public const double TOLERANCIA_IN = 0.01;

        /// <summary>Diámetros nominales disponibles (pulgadas), de menor a mayor.</summary>
        public static double[] Diametros()
        {
            var d = new double[Tabla.GetLength(0)];
            for (int i = 0; i < d.Length; i++) d[i] = Tabla[i, 0];
            return d;
        }

        public static ResultadoBrida Calcular(double diametroIn)
        {
            var r = new ResultadoBrida { DiametroNominalIn = diametroIn };
            if (double.IsNaN(diametroIn) || diametroIn <= 0)
            {
                r.Error = "El diámetro debe ser mayor que 0.";
                return r;
            }
            for (int i = 0; i < Tabla.GetLength(0); i++)
            {
                if (Math.Abs(Tabla[i, 0] - diametroIn) > TOLERANCIA_IN) continue;
                r.Valido = true;
                r.DiametroNominalIn = Tabla[i, 0];
                r.DiametroExteriorIn = Tabla[i, 1];
                r.EspesorIn = Tabla[i, 2];
                r.CirculoPernosIn = Tabla[i, 3];
                r.DiametroAgujeroIn = Tabla[i, 4];
                r.NumeroPernos = (int)Tabla[i, 5];
                r.DiametroInteriorIn = Tabla[i, 0];
                r.Agujeros = CentrosEnCirculo(r.CirculoPernosIn / 2.0, r.NumeroPernos);
                return r;
            }
            r.Error = "No hay brida de " + diametroIn.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture)
                      + "\" en la tabla (hay 4, 6, 8 y 12).";
            return r;
        }

        /// <summary>n puntos repartidos en un círculo de radio r, el primero sobre +X.</summary>
        public static List<Punto2D> CentrosEnCirculo(double radio, int n)
        {
            var puntos = new List<Punto2D>(n);
            for (int k = 0; k < n; k++)
            {
                double a = 2.0 * Math.PI * k / n;
                puntos.Add(new Punto2D(radio * Math.Cos(a), radio * Math.Sin(a)));
            }
            return puntos;
        }

        /// <summary>El dibujo de Civil 3D va en PIES: pulgadas → pies.</summary>
        public static double APies(double pulgadas) { return pulgadas / 12.0; }
    }
}
