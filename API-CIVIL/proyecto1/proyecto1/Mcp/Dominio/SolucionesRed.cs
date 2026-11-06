using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: SOLUCIONES de un conflicto (PURO), con el mismo criterio que
//  «Resolver conflictos» de la app (nucleo/soluciones.py): se baja o se sube UNA
//  utilidad ENTERA (todas sus tuberías y sus accesorios, la misma cantidad: la
//  pendiente no cambia) lo justo para dejar la separación de la normativa.
//
//  Cada opción se PRUEBA sobre la foto del modelo: ¿desaparece el conflicto?,
//  ¿aparece otro con las tuberías de alrededor?, ¿se separa alguna unión con una
//  tubería que no se mueve? Válida = resuelve, sin conflictos nuevos ni uniones
//  rotas. Orden: válidas primero; la de gravedad (alcantarillado, drenaje: con
//  pendiente y buzones) solo si no hay otra; menos movimiento; bajar antes que
//  subir (no le quita recubrimiento).
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    public sealed class OpcionSolucion
    {
        public string Id;                                   // P1, P2… (P1 = la recomendada)
        public string Mover;                                // la utilidad que se mueve («AGUA-20»)
        public string Otra;                                 // con la que choca
        public string Accion;                               // bajar | subir
        public double DeltaFt;                              // negativo = bajar
        public Tuberia Principal;                           // la tubería del conflicto que se mueve
        public List<Tuberia> Tuberias = new List<Tuberia>();
        public List<Accesorio> Accesorios = new List<Accesorio>();
        public bool Resuelve;
        public bool Gravedad;
        public List<string> Nuevos = new List<string>();    // conflictos que aparecerían
        public List<string> TambienResuelve = new List<string>();   // otros K# que desaparecen
        public List<string> UnionesRotas = new List<string>();
        public List<string> Avisos = new List<string>();
        public bool Valida => Resuelve && Nuevos.Count == 0 && UnionesRotas.Count == 0;

        public string Motivo()
        {
            if (!Resuelve) return "no resuelve el conflicto";
            if (UnionesRotas.Count > 0) return "separa una unión: " + UnionesRotas[0];
            if (Nuevos.Count > 0) return "crea otro conflicto: " + Nuevos[0];
            return Gravedad ? "válida, pero mueve una red de gravedad" : "válida";
        }
    }

    public static class SolucionesRed
    {
        public const double Z_UNION_FT = 0.10;              // puntas a la misma cota = unidas
        private static readonly string[] GRAVEDAD =
            { "ALCANT", "DRENAJE", "SSWR", "SEWR", "SEWER", "SANI", "STRM", "STORM" };

        /// <summary>Las tuberías que se mueven juntas: la misma utilidad de la app en la misma red, o la sola tubería.</summary>
        public static List<Tuberia> Grupo(Modelo m, Tuberia t) =>
            string.IsNullOrEmpty(t.UtilidadNumero) ? new List<Tuberia> { t }
            : m.Tuberias.Where(x => Calculos.Igual(x.Red, t.Red) && x.UtilidadNumero == t.UtilidadNumero &&
                                    Calculos.Igual(x.UtilidadCapa, t.UtilidadCapa)).ToList();

        public static bool EsGravedad(Tuberia t) =>
            t.TipoRed == TipoRed.Gravedad && GRAVEDAD.Any(g => Calculos.Contiene(t.Capa, g) || Calculos.Contiene(t.Red, g));

        /// <summary>Las opciones del conflicto `c`, probadas y ordenadas (P1 = la recomendada).</summary>
        public static List<OpcionSolucion> Opciones(Modelo m, ConflictoRed c, IList<ReglaSeparacion> reglas,
                                                    IList<ConflictoRed> todos = null)
        {
            var ops = new List<OpcionSolucion>();
            foreach (var (mov, otra, ejeM, ejeO) in new[] { (c.A, c.B, c.EjeA, c.EjeB), (c.B, c.A, c.EjeB, c.EjeA) })
            {
                double rm = Conflictos.Radio(mov), ro = Conflictos.Radio(otra), req = c.RequeridoFt;
                double bajar = -Arriba((ejeM + rm) - (ejeO - ro - req));     // su corona, req por debajo de la otra
                double subir = Arriba((ejeO + ro + req) - (ejeM - rm));      // su solera, req por encima de la otra
                foreach (var (accion, d) in new[] { ("bajar", bajar), ("subir", subir) })
                {
                    if ((accion == "bajar" && d >= 0) || (accion == "subir" && d <= 0)) continue;
                    if (c.Encima != null)
                    {
                        bool debeArriba = Calculos.Igual(c.Encima, mov.Capa);
                        if (debeArriba && accion == "bajar") continue;
                        if (!debeArriba && accion == "subir") continue;
                    }
                    ops.Add(Probar(m, c, mov, otra, accion, d, reglas, todos));
                }
            }
            ops = ops.OrderByDescending(o => o.Valida).ThenBy(o => o.Gravedad)
                     .ThenBy(o => Math.Abs(o.DeltaFt)).ThenBy(o => o.Accion == "bajar" ? 0 : 1).ToList();
            for (int i = 0; i < ops.Count; i++) ops[i].Id = "P" + (i + 1);
            return ops;
        }

        /// <summary>Redondeo HACIA ARRIBA a 0.01 ft (nunca queda corto).</summary>
        private static double Arriba(double x) => Math.Ceiling(x * 100.0 - 1e-6) / 100.0;

        private static OpcionSolucion Probar(Modelo m, ConflictoRed c, Tuberia mov, Tuberia otra, string accion,
                                             double d, IList<ReglaSeparacion> reglas, IList<ConflictoRed> todos)
        {
            var grupo = Grupo(m, mov);
            var o = new OpcionSolucion
            {
                Mover = mov.Utilidad(), Otra = otra.Utilidad(), Accion = accion, DeltaFt = d, Principal = mov,
                Tuberias = grupo, Gravedad = EsGravedad(mov),
            };
            var enGrupo = new HashSet<string>(grupo.Select(t => t.Handle));
            var dz = grupo.ToDictionary(t => t.Handle, t => d);
            var resto = m.Tuberias.Where(t => !enGrupo.Contains(t.Handle)).ToList();

            var antes = Conflictos.Entre(grupo, resto, reglas, null, out int _).Select(x => x.Clave()).ToHashSet();
            var despues = Conflictos.Entre(grupo, resto, reglas, dz, out int _);
            var clavesDespues = despues.Select(x => x.Clave()).ToHashSet();
            o.Resuelve = !clavesDespues.Contains(c.Clave());
            foreach (var n in despues.Where(x => !antes.Contains(x.Clave())))
                o.Nuevos.Add($"{n.A.Nombre} con {n.B.Nombre} ({Texto(n)})");
            if (todos != null)
                foreach (var k in todos)
                    if (k.Id != c.Id && antes.Contains(k.Clave()) && !clavesDespues.Contains(k.Clave()))
                        o.TambienResuelve.Add(k.Id);

            Accesorios(m, grupo, enGrupo, o);
            UnionesDirectas(m, grupo, enGrupo, o);
            Fondos(m, grupo, d, o);
            return o;
        }

        public static string Texto(ConflictoRed c) =>
            c.Tipo == Conflictos.CHOQUE ? "se chocan"
            : c.Tipo == Conflictos.SEPARACION ? $"{Conflictos.F(c.LibreFt)} ft libres, la normativa pide {Conflictos.F(c.RequeridoFt)}"
            : $"{c.Encima} debe ir encima";

        /// <summary>Los accesorios cuyas tuberías son todas del grupo se mueven con él; si unen una del grupo con
        /// otra que no se mueve, esa unión se rompería.</summary>
        private static void Accesorios(Modelo m, List<Tuberia> grupo, HashSet<string> enGrupo, OpcionSolucion o)
        {
            string red = grupo[0].Red;
            foreach (var a in m.Accesorios)
            {
                if (!string.IsNullOrEmpty(a.Red) && !Calculos.Igual(a.Red, red)) continue;
                var suyas = m.Tuberias.Where(t => Calculos.Igual(t.Red, red) && Toca(a, t)).ToList();
                if (suyas.Count == 0 || !suyas.Any(t => enGrupo.Contains(t.Handle))) continue;
                var fuera = suyas.Where(t => !enGrupo.Contains(t.Handle)).ToList();
                if (fuera.Count == 0) o.Accesorios.Add(a);
                else o.UnionesRotas.Add($"{Nombre(a)} en ({Conflictos.F(a.X)}, {Conflictos.F(a.Y)}) también une {fuera[0].Nombre}");
            }
        }

        private static bool Toca(Accesorio a, Tuberia t)
        {
            if (a.Conectadas.Count > 0) return a.Conectadas.Any(h => Calculos.Igual(h, t.Handle));
            double r = Math.Max(a.RadioFt, Conflictos.TOL_UNION_FT);
            return Dist(a.X, a.Y, t.XIni, t.YIni) <= r || Dist(a.X, a.Y, t.XFin, t.YFin) <= r;
        }

        /// <summary>Punta del grupo pegada a la punta de otra tubería de la misma red, a la misma cota y sin
        /// accesorio en medio (unión directa o estructura nula): se separaría.</summary>
        private static void UnionesDirectas(Modelo m, List<Tuberia> grupo, HashSet<string> enGrupo, OpcionSolucion o)
        {
            foreach (var g in grupo)
                foreach (var (gx, gy, gz) in Puntas(g))
                    foreach (var t in m.Tuberias)
                    {
                        if (enGrupo.Contains(t.Handle) || !Calculos.Igual(t.Red, g.Red)) continue;
                        foreach (var (tx, ty, tz) in Puntas(t))
                        {
                            if (Dist(gx, gy, tx, ty) > Conflictos.TOL_UNION_FT) continue;
                            if (gz.HasValue && tz.HasValue && Math.Abs(gz.Value - tz.Value) > Z_UNION_FT) continue;
                            if (m.Accesorios.Any(a => Dist(a.X, a.Y, gx, gy) <= Math.Max(a.RadioFt, Conflictos.TOL_UNION_FT))) continue;
                            if (BuzonReal(m, g.Red, gx, gy)) continue;     // llega a un buzón: solo cambia su cota ahí
                            string txt = $"{g.Nombre} con {t.Nombre} en ({Conflictos.F(gx)}, {Conflictos.F(gy)})";
                            if (!o.UnionesRotas.Contains(txt)) o.UnionesRotas.Add(txt);
                        }
                    }
        }

        /// <summary>En gravedad las estructuras no se mueven: aviso si la rasante queda bajo el fondo o sobre la tapa.</summary>
        private static void Fondos(Modelo m, List<Tuberia> grupo, double d, OpcionSolucion o)
        {
            foreach (var t in grupo)
                foreach (var (h, z) in new[] { (t.EstructuraIni, t.CotaIni), (t.EstructuraFin, t.CotaFin) })
                {
                    if (string.IsNullOrEmpty(h) || !z.HasValue) continue;
                    var s = m.Estructuras.FirstOrDefault(e => Calculos.Igual(e.Handle, h));
                    if (s == null) continue;
                    double nz = z.Value + d;
                    if (s.Sump.HasValue && nz < s.Sump.Value - 1e-6)
                        o.Avisos.Add($"{t.Nombre} queda {Conflictos.F(s.Sump.Value - nz)} ft bajo el fondo de {s.Nombre}.");
                    else if (s.Rim.HasValue && nz > s.Rim.Value)
                        o.Avisos.Add($"{t.Nombre} queda sobre la tapa de {s.Nombre}.");
                }
        }

        /// <summary>Buzón o caja de verdad (no la «estructura nula» de los conductos) en ese punto.</summary>
        private static bool BuzonReal(Modelo m, string red, double x, double y) =>
            m.Estructuras.Any(e => Calculos.Igual(e.Red, red) && Dist(e.X, e.Y, x, y) <= 3.0 &&
                                   !Calculos.Contiene(e.Tamano, "nul") && !Calculos.Contiene(e.Nombre, "nul"));

        private static IEnumerable<(double x, double y, double? z)> Puntas(Tuberia t)
        {
            yield return (t.XIni, t.YIni, Conflictos.EjeEn(t, 0));
            yield return (t.XFin, t.YFin, Conflictos.EjeEn(t, 1));
        }

        private static double Dist(double ax, double ay, double bx, double by) =>
            Math.Sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by));

        public static string Nombre(Accesorio a) => string.IsNullOrEmpty(a.Tipo) ? "el accesorio" : a.Tipo.ToLowerInvariant() switch
        {
            "codo" or "elbow" => "el codo",
            "tee" => "la Tee",
            "wye" => "la Wye",
            "cross" or "cruz" => "la cruz",
            "valve" => "la válvula",
            _ => a.Tipo,
        };
    }
}
