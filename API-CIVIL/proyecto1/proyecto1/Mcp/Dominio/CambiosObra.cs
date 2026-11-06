using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: válvulas, accesorios y conexiones verticales (PURO).
//    · Válvula (poner): en un tramo RECTO de una tubería a presión, con espacio
//      para ella y, junto a un accesorio, 1.7·D de margen (la misma regla que
//      `nucleo/valvulas` de la app). Quitar: la tubería vuelve a ser una sola.
//    · Quitar accesorio («aquí no va codo/Tee»): se borra y sus tuberías llegan
//      a su centro sin unirse (lo mismo que «No hay accesorio» de la app).
//    · Conexión vertical: dos utilidades que se tocan en planta a distinta cota.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public static class CambiosObra
    {
        public const double MARGEN_ACC_D = 1.7;        // × diámetro, junto a un accesorio (`ALCANCE_ACC_D` de la app)
        public const double TUBO_MIN_FT = 0.5;         // en una punta libre
        public const double RG_MAX_IN = 16.0;          // unión RG solo hasta 16"
        public const double TOCA_FT = 0.5;

        // ------------------------------------------------------------ válvulas

        /// <summary>Válvula de `largoIn` en la tubería `t`, en el punto más cercano a (x, y), a `distancia` ft de su
        /// inicio o en su medio.</summary>
        public static CambioValvula PonerValvula(Modelo m, Tuberia t, double? x, double? y, double? distancia, string union,
                                                 double largoIn, out string error)
        {
            error = null;
            if (t.TipoRed != TipoRed.Presion) { error = "Las válvulas van en tuberías a presión (agua o gas)."; return null; }
            string u = string.IsNullOrWhiteSpace(union) ? "FLG" : union.Trim().ToUpperInvariant();
            if (u != "FLG" && u != "RG") { error = "La unión es FLG (bridada) o RG (junta)."; return null; }
            if (u == "RG" && t.DiametroIn > RG_MAX_IN) { error = $"La unión RG llega hasta {RG_MAX_IN}\": esta tubería es de {Materiales.F(t.DiametroIn)}\"."; return null; }
            double L = t.LargoFt, dx = t.XFin - t.XIni, dy = t.YFin - t.YIni;
            if (L < 1e-6) { error = $"{t.Nombre} no tiene largo."; return null; }
            double s = distancia ?? (x.HasValue && y.HasValue ? ((x.Value - t.XIni) * dx + (y.Value - t.YIni) * dy) / L : L / 2.0);
            double medio = largoIn / 24.0;
            double mIni = medio + Margen(m, t, true), mFin = medio + Margen(m, t, false);
            if (mIni + mFin > L) { error = $"La válvula no cabe en {t.Nombre} ({Materiales.F(L)} ft): necesita {Materiales.F(mIni + mFin)} ft con su espacio."; return null; }
            bool corrida = s < mIni || s > L - mFin;
            s = Math.Max(mIni, Math.Min(L - mFin, s));
            var cp = new CambioValvula
            {
                Tipo = TiposCambio.PONER_VALVULA, Poner = true, Handle = t.Handle, Elemento = t.Nombre,
                X = t.XIni + dx * s / L, Y = t.YIni + dy * s / L, DirX = dx / L, DirY = dy / L,
                DiametroIn = t.DiametroIn, LargoIn = largoIn, Union = u, Material = t.Material() ?? "",
                Antes = "sin válvula", Despues = $"válvula {Materiales.F(t.DiametroIn)}\" {u}",
            };
            cp.Handles.Add(t.Handle);
            cp.Consecuencias.Add($"Válvula de compuerta de {Materiales.F(t.DiametroIn)}\" ({(u == "FLG" ? "bridada" : "junta RG")}, " +
                                 $"{Materiales.F(largoIn)}\" de largo) a {Materiales.F(s)} ft del inicio de {t.Nombre}.");
            cp.Consecuencias.Add("La tubería se parte en las dos caras de la válvula (dos tubos con la misma pieza).");
            if (corrida) cp.Advertencias.Add("Se corrió para que quepa con su espacio junto a los accesorios.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        /// <summary>Espacio que necesita la válvula en esa punta: 1.7·D si llega a un accesorio, si no lo mínimo.</summary>
        private static double Margen(Modelo m, Tuberia t, bool ini)
        {
            double px = ini ? t.XIni : t.XFin, py = ini ? t.YIni : t.YFin;
            bool acc = m.Accesorios.Any(a => (a.Conectadas.Any(h => Calculos.Igual(h, t.Handle)) && Metrados.D(a.X, a.Y, px, py) <= a.RadioFt + 1.0) ||
                                             (a.Conectadas.Count == 0 && Metrados.D(a.X, a.Y, px, py) <= a.RadioFt));
            return acc ? MARGEN_ACC_D * t.DiametroIn / 12.0 : TUBO_MIN_FT;
        }

        public static CambioValvula QuitarValvula(Modelo m, GrupoAccesorio v, out string error)
        {
            error = null;
            if (!v.EsValvula) { error = $"{v.Id} no es una válvula."; return null; }
            var ts = Metrados.Tuberias(m, v);
            var cp = new CambioValvula
            {
                Tipo = TiposCambio.QUITAR_VALVULA, Poner = false, X = v.X, Y = v.Y, Solidos = v.Handles.ToList(),
                Handle = v.Handles[0], Elemento = $"Válvula {v.Id}", Antes = "válvula", Despues = "sin válvula",
            };
            cp.Handles.AddRange(ts.Select(t => t.Handle));
            if (ts.Count == 2)
            {
                cp.Consecuencias.Add($"Se borra la válvula y {ts[0].Nombre} y {ts[1].Nombre} vuelven a ser una sola tubería.");
                double a = Math.Abs(Dir(ts[0]).x * Dir(ts[1]).x + Dir(ts[0]).y * Dir(ts[1]).y);
                if (a < Math.Cos(2.0 * Math.PI / 180.0)) cp.Advertencias.Add("Las dos tuberías no van en línea recta: revisa la unión.");
            }
            else
                cp.Advertencias.Add($"La válvula toca {ts.Count} tubería(s) (se esperaban 2): solo se borra la válvula, las tuberías quedan como están.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        private static (double x, double y) Dir(Tuberia t) =>
            t.LargoFt < 1e-9 ? (1, 0) : ((t.XFin - t.XIni) / t.LargoFt, (t.YFin - t.YIni) / t.LargoFt);

        // ------------------------------------------------------------ quitar accesorio

        public static CambioQuitarAccesorio QuitarAccesorio(Modelo m, GrupoAccesorio a, out string error)
        {
            error = null;
            if (a.EsValvula) { error = $"{a.Id} es una válvula: para quitarla, proponer_valvula con accion=quitar."; return null; }
            var ts = Metrados.Tuberias(m, a);
            var cp = new CambioQuitarAccesorio
            {
                Tipo = TiposCambio.QUITAR_ACCESORIO, X = a.X, Y = a.Y, Accesorios = a.Handles.ToList(), Handle = a.Handles[0],
                Elemento = $"{SolucionesRed.Nombre(new Accesorio { Tipo = a.Tipo })} {a.Id}", Antes = a.Tipo, Despues = "sin accesorio",
            };
            cp.Handles.AddRange(ts.Select(t => t.Handle));
            cp.Consecuencias.Add($"Se borra {SolucionesRed.Nombre(new Accesorio { Tipo = a.Tipo })} y " +
                                 (ts.Count == 0 ? "no hay tuberías que la toquen." :
                                  $"{ts.Count} tubería(s) llegan hasta su centro sin unirse ({string.Join(", ", ts.Select(t => t.Nombre).Take(4))})."));
            cp.Consecuencias.Add("Es lo mismo que «No hay accesorio» en la app: márcalo también allá para no perderlo al reimportar.");
            if (ts.Count == 0) cp.Advertencias.Add("No encontré tuberías en ese accesorio.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        // ------------------------------------------------------------ conexión vertical

        /// <summary>Punto donde se tocan dos tuberías en planta (cruce, o la punta de una sobre la otra) y la
        /// fracción de cada una; null si no se tocan.</summary>
        public static (double x, double y, double sa, double sb)? Toque(Tuberia a, Tuberia b)
        {
            if (Conflictos.Cruce(a, b, out double x, out double y, out double sa, out double sb)) return (x, y, sa, sb);
            foreach (var (p, q, ini) in new[] { (a, b, true), (a, b, false), (b, a, true), (b, a, false) })
            {
                double px = ini ? p.XIni : p.XFin, py = ini ? p.YIni : p.YFin;
                if (Conflictos.DistSeg(px, py, q) > TOCA_FT) continue;
                double sq = Fraccion(q, px, py), sp = ini ? 0.0 : 1.0;
                return ReferenceEquals(p, a) ? (px, py, sp, sq) : (px, py, sq, sp);
            }
            return null;
        }

        private static double Fraccion(Tuberia t, double x, double y)
        {
            double dx = t.XFin - t.XIni, dy = t.YFin - t.YIni, L2 = dx * dx + dy * dy;
            return L2 < 1e-12 ? 0.0 : Math.Max(0.0, Math.Min(1.0, ((x - t.XIni) * dx + (y - t.YIni) * dy) / L2));
        }

        public static CambioConexionVertical ConexionVertical(Modelo m, Tuberia a, Tuberia b, out string error)
        {
            error = null;
            if (!string.IsNullOrEmpty(a.UtilidadNumero) && a.Utilidad() == b.Utilidad())
            { error = $"{a.Nombre} y {b.Nombre} son de la misma utilidad."; return null; }
            var p = Toque(a, b);
            if (p == null) { error = $"{a.Nombre} y {b.Nombre} no se tocan en planta."; return null; }
            var (x, y, sa, sb) = p.Value;
            double? ea = Conflictos.EjeEn(a, sa), eb = Conflictos.EjeEn(b, sb);
            if (!ea.HasValue || !eb.HasValue) { error = "Una de las dos no tiene cotas."; return null; }
            double za = ea.Value - Conflictos.Radio(a), zb = eb.Value - Conflictos.Radio(b);
            if (Math.Abs(ea.Value - eb.Value) < 0.05) { error = "Están a la misma cota: no hace falta una conexión vertical."; return null; }
            var arriba = ea.Value > eb.Value ? a : b;
            double alto = Math.Abs(ea.Value - eb.Value), d = Math.Min(a.DiametroIn, b.DiametroIn);
            var cp = new CambioConexionVertical
            {
                Tipo = TiposCambio.CONEXION_VERTICAL, Handle = a.Handle, X = x, Y = y, TuberiaA = a.Handle, TuberiaB = b.Handle, ZA = za, ZB = zb,
                Elemento = $"{a.Utilidad()} ↔ {b.Utilidad()}", Antes = "sin conexión", Despues = $"vertical de {Materiales.F(alto)} ft",
            };
            cp.Handles.Add(a.Handle); cp.Handles.Add(b.Handle);
            cp.Consecuencias.Add($"Tramo vertical de {Materiales.F(alto)} ft en ({ReglasCambio.F(x)}, {ReglasCambio.F(y)}), de {Materiales.F(d)}\" " +
                                 $"(el menor), con codo o Tee en cada una (como las conexiones verticales aprobadas en la app).");
            cp.Consecuencias.Add($"{arriba.Nombre} queda arriba; las tuberías no cambian de cota.");
            if (a.TipoRed != b.TipoRed) cp.Advertencias.Add("Una es de gravedad y otra a presión: revisa que la conexión tenga sentido.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }
    }
}
