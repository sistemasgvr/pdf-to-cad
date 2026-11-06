using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: mover en PLANTA una utilidad (o un tramo) para esquivar un choque de
//  lado (PURO). Se mueven juntas sus tuberías, los accesorios que solo las usan a
//  ellas y las estructuras que solo las usan a ellas; lo que las une con otras se
//  separaría (advertencia). Se compara cada conflicto antes/después (con las
//  separaciones de la normativa de la app) para decir qué resuelve y qué crea.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public static class MoverPlanta
    {
        public const double MAX_FT = 500.0;

        /// <summary>Vector (dx, dy): explícito, o `lado` (izquierda/derecha según el sentido de `ref`) × `distancia`.</summary>
        public static (double dx, double dy)? Vector(Tuberia referencia, double? dx, double? dy, string lado, double? distancia, out string error)
        {
            error = null;
            if (dx.HasValue || dy.HasValue) return (dx ?? 0.0, dy ?? 0.0);
            if (string.IsNullOrWhiteSpace(lado) || !distancia.HasValue)
            { error = "Dime cuánto y hacia dónde: 'dx'/'dy' en ft, o 'lado' (izquierda/derecha) y 'distancia' en ft."; return null; }
            double L = referencia.LargoFt;
            if (L < 1e-9) { error = $"{referencia.Nombre} no tiene largo."; return null; }
            double ux = (referencia.XFin - referencia.XIni) / L, uy = (referencia.YFin - referencia.YIni) / L;
            string l = Materiales.Plano(lado);
            double signo = l.StartsWith("izq") || l.StartsWith("left") ? 1.0 : l.StartsWith("der") || l.StartsWith("right") ? -1.0 : 0.0;
            if (signo == 0.0) { error = "El lado es «izquierda» o «derecha» (según el sentido de la tubería)."; return null; }
            return (-uy * distancia.Value * signo, ux * distancia.Value * signo);
        }

        public static CambioMover Proponer(Modelo m, List<Tuberia> grupo, double dx, double dy, IList<ReglaSeparacion> reglas, out string error)
        {
            error = null;
            double d = Math.Sqrt(dx * dx + dy * dy);
            if (d < 0.005) { error = "El movimiento es nulo."; return null; }
            if (d > MAX_FT) { error = $"Moverla {Materiales.F(d)} ft es demasiado (máx. {MAX_FT} ft)."; return null; }
            var en = new HashSet<string>(grupo.Select(t => t.Handle), StringComparer.OrdinalIgnoreCase);
            var cp = new CambioMover
            {
                Tipo = TiposCambio.MOVER_PLANTA, Dx = dx, Dy = dy, Handle = grupo[0].Handle,
                Handles = grupo.Select(t => t.Handle).ToList(),
                Elemento = grupo.Count == 1 ? grupo[0].Nombre : $"{CambiosRed.Grupo(grupo)} ({grupo.Count} tuberías)",
                Antes = "donde está", Despues = $"{Materiales.F(d)} ft (Δx {Materiales.F(dx)}, Δy {Materiales.F(dy)})",
            };
            // accesorios
            foreach (GrupoAccesorio a in Metrados.Accesorios(m))
            {
                var suyas = Metrados.Tuberias(m, a);
                if (!suyas.Any(t => en.Contains(t.Handle))) continue;
                var fuera = suyas.Where(t => !en.Contains(t.Handle)).ToList();
                if (fuera.Count == 0) cp.Accesorios.AddRange(a.Handles);
                else cp.Advertencias.Add($"Se separaría {SolucionesRed.Nombre(new Accesorio { Tipo = a.Tipo })} {a.Id}, que también une {fuera[0].Nombre}.");
            }
            // estructuras
            foreach (Estructura e in m.Estructuras)
            {
                var llegan = Buzones.Llegadas(m, e).Select(x => x.t).ToList();
                if (!llegan.Any(t => en.Contains(t.Handle))) continue;
                var fuera = llegan.Where(t => !en.Contains(t.Handle)).ToList();
                if (fuera.Count == 0) cp.Estructuras.Add(e.Handle);
                else cp.Advertencias.Add($"{e.Nombre} también recibe {fuera[0].Nombre}: esas tuberías quedarían separadas de ella.");
            }
            // uniones directas (puntas pegadas a otra tubería sin estructura ni accesorio)
            foreach (Tuberia g in grupo)
                foreach (var (px, py, sh) in new[] { (g.XIni, g.YIni, g.EstructuraIni), (g.XFin, g.YFin, g.EstructuraFin) })
                {
                    if (!string.IsNullOrEmpty(sh)) continue;
                    var otra = m.Tuberias.FirstOrDefault(t => !en.Contains(t.Handle) && Calculos.Igual(t.Red, g.Red) &&
                                                              Conflictos.DistSeg(px, py, t) <= CambiosRed.TOL_UNION_FT);
                    if (otra != null) cp.Advertencias.Add($"{g.Nombre} se separaría de {otra.Nombre} en ({ReglasCambio.F(px)}, {ReglasCambio.F(py)}).");
                }
            cp.Advertencias = cp.Advertencias.Distinct().ToList();
            // conflictos antes / después
            var copia = new Modelo { Estructuras = m.Estructuras, Accesorios = m.Accesorios, Textos = m.Textos };
            foreach (Tuberia t in m.Tuberias)
            {
                if (!en.Contains(t.Handle)) { copia.Tuberias.Add(t); continue; }
                var c = t.Copia();
                c.XIni += dx; c.YIni += dy; c.XFin += dx; c.YFin += dy;
                copia.Tuberias.Add(c);
            }
            var antes = Conflictos.Buscar(m, reglas, out int _).Where(k => en.Contains(k.A.Handle) || en.Contains(k.B.Handle)).ToList();
            var despues = Conflictos.Buscar(copia, reglas, out int _).Where(k => en.Contains(k.A.Handle) || en.Contains(k.B.Handle)).ToList();
            var claveD = despues.Select(k => k.Clave()).ToHashSet();
            var claveA = antes.Select(k => k.Clave()).ToHashSet();
            var resueltos = antes.Where(k => !claveD.Contains(k.Clave())).ToList();
            var nuevos = despues.Where(k => !claveA.Contains(k.Clave())).ToList();
            cp.Consecuencias.Add($"Se mueven en planta {grupo.Count} tubería(s)" +
                                 (cp.Accesorios.Count > 0 ? $", sus accesorios" : "") + (cp.Estructuras.Count > 0 ? $" y {cp.Estructuras.Count} estructura(s)" : "") +
                                 "; las cotas no cambian.");
            if (resueltos.Count > 0)
                cp.Consecuencias.Add("Deja de chocar con: " + string.Join(", ", resueltos.Select(k => Otra(k, en).Nombre).Distinct().Take(6)) + ".");
            foreach (var k in nuevos.Take(6))
                cp.Advertencias.Add($"Crearía un conflicto con {Otra(k, en).Nombre} ({SolucionesRed.Texto(k)}).");
            if (antes.Count > 0 && resueltos.Count == 0) cp.Advertencias.Add("No resuelve ninguno de sus conflictos actuales.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        private static Tuberia Otra(ConflictoRed k, HashSet<string> en) => en.Contains(k.A.Handle) ? k.B : k.A;
    }
}
