using System;
using System.Collections.Generic;
using System.Linq;

// ============================================================================
//  DOMINIO: pendientes, tamaños y perfiles (PURO). La IA solo elige QUÉ tuberías
//  y, si el usuario lo dijo, el valor; las cotas, los tamaños del catálogo y las
//  consecuencias los calcula esto. La NORMATIVA la pone la app (sus reglas, su
//  validador): aquí llegan solo los objetivos ya calculados (`ObjetivoPendiente`)
//  y la app revisa la propuesta con su validador antes de mostrarla.
// ============================================================================

namespace Civil3DBasico.Mcp.Dominio
{
    /// <summary>Un tamaño de la lista de piezas de la red (lo da el adaptador de Civil 3D).</summary>
    public sealed class TamanoDisponible
    {
        public string Clave;          // opaca: la entiende el adaptador para hacer el cambio
        public string Familia;        // familia (gravedad) o descripción del tubo (presión)
        public string Nombre;         // PartSizeName
        public double DiametroIn;
        public string Material;

        public string Texto() => $"{Materiales.F(DiametroIn)}\" {Material}".Trim();
    }

    /// <summary>Pendiente que pide la normativa de la app para una tubería (%, positivo = baja hacia el fin).</summary>
    public sealed class ObjetivoPendiente { public double? Min, Max; public string Fuente; }

    public static class CambiosRed
    {
        public const double TOL_PENDIENTE = 1e-6, TOL_DIAM_IN = 0.05, TOL_UNION_FT = 0.1;
        public const int LINEAS_MAX = 8;

        // ------------------------------------------------------------ pendiente

        /// <summary>Rasantes nuevas para que cada tubería tenga `pct` (o lo que pide la normativa de la app en
        /// `objetivos`). `mantener` = «inicio» (se mueve el fin, por defecto) o «fin». `soloMalas`: solo las que no cumplen.</summary>
        public static CambioPendiente Pendiente(Modelo m, List<Tuberia> ts, IDictionary<string, ObjetivoPendiente> objetivos,
                                                double? pct, string mantener, bool soloMalas, out string error)
        {
            error = null;
            bool fijaFin = Calculos.Igual((mantener ?? "").Trim(), "fin");
            var cp = new CambioPendiente { Tipo = TiposCambio.PENDIENTE };
            var sinRegla = new List<string>(); var sinCota = new List<string>(); var fuentes = new List<string>();
            var antes = new List<double>(); var despues = new List<double>(); var lineas = new List<string>();
            var nuevas = new Dictionary<string, (double ini, double fin)>(StringComparer.OrdinalIgnoreCase);
            foreach (Tuberia t in ts)
            {
                if (t.TipoRed != TipoRed.Gravedad) continue;
                if (!t.CotaIni.HasValue || !t.CotaFin.HasValue || t.LargoFt < 1e-6) { sinCota.Add(t.Nombre); continue; }
                double p0 = (t.CotaIni.Value - t.CotaFin.Value) / t.LargoFt * 100.0;
                ObjetivoPendiente q = null;
                objetivos?.TryGetValue(t.Handle, out q);
                if (q != null && !string.IsNullOrWhiteSpace(q.Fuente)) fuentes.Add(q.Fuente);
                double? meta = pct;
                if (!meta.HasValue)
                {
                    if (q == null || (!q.Min.HasValue && !q.Max.HasValue)) { sinRegla.Add(t.Nombre); continue; }
                    if (q.Min.HasValue && p0 < q.Min.Value - TOL_PENDIENTE) meta = q.Min.Value;
                    else if (q.Max.HasValue && p0 > q.Max.Value + TOL_PENDIENTE) meta = q.Max.Value;
                    else if (soloMalas) continue;
                    else meta = q.Min ?? q.Max;
                }
                else if (soloMalas && Math.Abs(p0 - meta.Value) <= 1e-4) continue;
                double zi = t.CotaIni.Value, zf = t.CotaFin.Value;
                if (fijaFin) zi = zf + t.LargoFt * meta.Value / 100.0; else zf = zi - t.LargoFt * meta.Value / 100.0;
                nuevas[t.Handle] = (zi, zf);
                cp.Cotas.Add(new CotaNueva { Handle = t.Handle, Ini = zi, Fin = zf });
                cp.Handles.Add(t.Handle);
                antes.Add(p0); despues.Add(meta.Value);
                lineas.Add($"{t.Nombre}: {Materiales.F(p0)} % → {Materiales.F(meta.Value)} % " +
                           (fijaFin ? $"(rasante de inicio {ReglasCambio.F(t.CotaIni.Value)} → {ReglasCambio.F(zi)} ft)"
                                    : $"(rasante de fin {ReglasCambio.F(t.CotaFin.Value)} → {ReglasCambio.F(zf)} ft)"));
            }
            if (cp.Cotas.Count == 0)
            {
                error = sinRegla.Count > 0 && !pct.HasValue
                    ? $"Las normativas de la app no tienen pendiente para {Lista(sinRegla)}: dime qué pendiente quieres."
                    : sinCota.Count > 0 && sinCota.Count == ts.Count(x => x.TipoRed == TipoRed.Gravedad)
                        ? $"{Lista(sinCota)} no tiene(n) cotas en los dos extremos."
                        : ts.All(x => x.TipoRed != TipoRed.Gravedad)
                            ? "La pendiente solo se cambia en tuberías de gravedad o conduit."
                            : "Todas cumplen ya la pendiente: no hay nada que cambiar.";
                return null;
            }
            Tuberia t0 = ts.First(x => Calculos.Igual(x.Handle, cp.Handles[0]));
            cp.Handle = t0.Handle;
            cp.Elemento = cp.Cotas.Count == 1 ? t0.Nombre : $"{cp.Cotas.Count} tuberías de {Grupo(ts)}";
            cp.Antes = Rango(antes, " %"); cp.Despues = Rango(despues, " %");
            cp.Consecuencias.AddRange(lineas.Take(LINEAS_MAX));
            if (lineas.Count > LINEAS_MAX) cp.Consecuencias.Add($"… y {lineas.Count - LINEAS_MAX} tubería(s) más.");
            if (!pct.HasValue)
                cp.Consecuencias.Add("Pendiente según las normativas de la app" +
                                     (fuentes.Count > 0 ? $" ({string.Join("; ", fuentes.Distinct().Take(3))})." : "."));
            if (sinRegla.Count > 0 && !pct.HasValue) cp.Consecuencias.Add($"Sin regla de pendiente (no se tocan): {Lista(sinRegla)}.");
            if (sinCota.Count > 0) cp.Consecuencias.Add($"Sin cotas (no se tocan): {Lista(sinCota)}.");
            Uniones(m, nuevas, cp.Advertencias);
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        /// <summary>Lo que dejan las rasantes nuevas en los buzones: bajo el fondo, sobre la tapa, o una tubería que
        /// llega más abajo que la que sale (el agua no sale).</summary>
        public static void Uniones(Modelo m, Dictionary<string, (double ini, double fin)> nuevas, List<string> adv)
        {
            double Ini(Tuberia t) => nuevas.TryGetValue(t.Handle, out var z) ? z.ini : t.CotaIni ?? double.NaN;
            double Fin(Tuberia t) => nuevas.TryGetValue(t.Handle, out var z) ? z.fin : t.CotaFin ?? double.NaN;
            foreach (string h in nuevas.Keys)
            {
                Tuberia t = m.Tuberias.First(x => Calculos.Igual(x.Handle, h));
                foreach (var (sh, z) in new[] { (t.EstructuraIni, Ini(t)), (t.EstructuraFin, Fin(t)) })
                {
                    Estructura s = m.Estructuras.FirstOrDefault(x => Calculos.Igual(x.Handle, sh));
                    if (s == null || s.Nula) continue;
                    if (s.Sump.HasValue && z < s.Sump.Value - 1e-6)
                        adv.Add($"{t.Nombre} queda {ReglasCambio.F(s.Sump.Value - z)} ft bajo el fondo de {s.Nombre}.");
                    if (s.Rim.HasValue && z > s.Rim.Value)
                        adv.Add($"{t.Nombre} queda sobre la tapa de {s.Nombre}.");
                }
                foreach (Tuberia sig in m.Tuberias.Where(x => x != t && x.TipoRed == TipoRed.Gravedad && Sigue(t, x)))
                {
                    double llega = Fin(t), sale = Ini(sig);
                    if (!double.IsNaN(llega) && !double.IsNaN(sale) && llega < sale - 0.005)
                        adv.Add($"{t.Nombre} llega {ReglasCambio.F(sale - llega)} ft más abajo que {sig.Nombre}, que sale de ahí: el agua no saldría.");
                }
            }
        }

        /// <summary>¿`b` sale de donde termina `a`? (misma estructura o puntas juntas).</summary>
        public static bool Sigue(Tuberia a, Tuberia b) =>
            (!string.IsNullOrEmpty(a.EstructuraFin) && Calculos.Igual(a.EstructuraFin, b.EstructuraIni)) ||
            (string.IsNullOrEmpty(a.EstructuraFin) && Math.Abs(a.XFin - b.XIni) <= TOL_UNION_FT && Math.Abs(a.YFin - b.YIni) <= TOL_UNION_FT);

        // ------------------------------------------------------------ tamaño

        /// <summary>Otro tamaño de la lista de piezas para cada tubería: el de `diamIn` (o el actual) y `material`
        /// (o la familia actual). `disponibles(t)` = los tamaños de la lista de piezas de su red.</summary>
        public static CambioTamano Tamano(Modelo m, List<Tuberia> ts, Func<Tuberia, List<TamanoDisponible>> disponibles,
                                          double? diamIn, string material, out string error)
        {
            error = null;
            if (!diamIn.HasValue && string.IsNullOrWhiteSpace(material)) { error = "Dime el diámetro (pulgadas) o el material."; return null; }
            var cp = new CambioTamano { Tipo = TiposCambio.TAMANO };
            var lineas = new List<string>(); var iguales = new List<string>();
            var antes = new List<string>(); var despues = new List<string>();
            foreach (Tuberia t in ts)
            {
                var lista = disponibles(t) ?? new List<TamanoDisponible>();
                double d = diamIn ?? t.DiametroIn;
                var cand = lista.Where(x => Math.Abs(x.DiametroIn - d) <= TOL_DIAM_IN).ToList();
                if (!string.IsNullOrWhiteSpace(material))
                    cand = cand.Where(x => Materiales.Mismo($"{x.Material} {x.Familia} {x.Nombre}", material)).ToList();
                else
                {
                    var misma = cand.Where(x => Calculos.Igual(x.Familia, t.Familia)).ToList();
                    if (misma.Count > 0) cand = misma;
                }
                if (cand.Count == 0)
                {
                    error = $"En la lista de piezas de la red {t.Red} no hay un tubo de " +
                            $"{(diamIn.HasValue ? Materiales.F(d) + "\"" : "")}{(string.IsNullOrWhiteSpace(material) ? "" : " " + material)}. " +
                            "Hay: " + Disponibles(lista) + ". Se puede agregar el tamaño con el «+» de la app y volver a importar.";
                    return null;
                }
                TamanoDisponible e = cand.FirstOrDefault(x => Calculos.Igual(x.Nombre, t.Tamano) || Calculos.Igual(x.Familia, t.Familia)) ?? cand[0];
                if (Calculos.Igual(e.Nombre, t.Tamano) && Calculos.Igual(e.Familia, t.Familia)) { iguales.Add(t.Nombre); continue; }
                cp.Tamanos.Add(new TamanoNuevo
                {
                    Handle = t.Handle, Clave = e.Clave, Nombre = e.Nombre, DiametroIn = e.DiametroIn,
                    Material = string.IsNullOrWhiteSpace(material) ? t.Material() : material,
                });
                cp.Handles.Add(t.Handle);
                antes.Add($"{Materiales.F(t.DiametroIn)}\" {t.Material()}".Trim()); despues.Add(e.Texto());
                lineas.Add($"{t.Nombre}: {t.Tamano} → {e.Nombre}");
                Vecinas(m, t, e, cp.Advertencias);
            }
            if (cp.Tamanos.Count == 0) { error = $"{Lista(iguales)} ya tiene(n) ese tamaño: no hay nada que cambiar."; return null; }
            Tuberia t0 = ts.First(x => Calculos.Igual(x.Handle, cp.Handles[0]));
            cp.Handle = t0.Handle;
            cp.Elemento = cp.Tamanos.Count == 1 ? t0.Nombre : $"{cp.Tamanos.Count} tuberías de {Grupo(ts)}";
            cp.Antes = string.Join(", ", antes.Distinct()); cp.Despues = string.Join(", ", despues.Distinct());
            cp.Consecuencias.AddRange(lineas.Take(LINEAS_MAX));
            if (lineas.Count > LINEAS_MAX) cp.Consecuencias.Add($"… y {lineas.Count - LINEAS_MAX} tubería(s) más.");
            cp.Consecuencias.Add(t0.TipoRed == TipoRed.Gravedad
                ? "La rasante (solera) no cambia: la tubería crece o se achica hacia arriba."
                : "El eje no cambia.");
            if (iguales.Count > 0) cp.Consecuencias.Add($"Ya tienen ese tamaño (no se tocan): {Lista(iguales)}.");
            cp.Huella = cp.HuellaDe(m);
            return cp;
        }

        private static void Vecinas(Modelo m, Tuberia t, TamanoDisponible e, List<string> adv)
        {
            if (t.TipoRed == TipoRed.Gravedad)
            {
                foreach (Tuberia sig in m.Tuberias.Where(x => x != t && Sigue(t, x) && x.DiametroIn < e.DiametroIn - TOL_DIAM_IN))
                    adv.Add($"{t.Nombre} queda más grande ({Materiales.F(e.DiametroIn)}\") que {sig.Nombre} ({Materiales.F(sig.DiametroIn)}\"), que sigue aguas abajo.");
                return;
            }
            int n = m.Accesorios.Count(a => a.EsPieza && a.Conectadas.Any(h => Calculos.Igual(h, t.Handle)));
            if (n > 0)
                adv.Add($"{t.Nombre} tiene {n} accesorio(s) conectado(s) del diámetro anterior: Civil 3D puede desconectarlos; revisa las uniones.");
        }

        private static string Disponibles(List<TamanoDisponible> lista)
        {
            if (lista.Count == 0) return "ningún tubo";
            var porMat = lista.GroupBy(x => string.IsNullOrWhiteSpace(x.Material) ? x.Familia : x.Material)
                              .Select(g => $"{string.Join(", ", g.Select(x => Materiales.F(x.DiametroIn) + "\"").Distinct())} ({g.Key})");
            return string.Join("; ", porMat.Take(6));
        }

        // ------------------------------------------------------------ perfil

        /// <summary>Perfil longitudinal desde la tubería `ini` hasta `fin` (null = el recorrido entero que haría
        /// CREAR_PERFIL_RED eligiendo `ini`).</summary>
        public static CambioPerfil Perfil(Tuberia ini, Tuberia fin, string nombre, out string error)
        {
            error = null;
            if (fin != null && !Calculos.Igual(ini.Red, fin.Red))
            { error = $"{ini.Nombre} y {fin.Nombre} son de redes distintas ({ini.Red}, {fin.Red}): un perfil sigue una sola red."; return null; }
            string n = string.IsNullOrWhiteSpace(nombre) ? (fin == null ? $"Perfil {ini.Red}" : $"Perfil {ini.Nombre} a {fin.Nombre}") : nombre.Trim();
            if (n.Length > ReglasCambio.TEXTO_MAX) n = n.Substring(0, ReglasCambio.TEXTO_MAX);
            var cp = new CambioPerfil
            {
                Tipo = TiposCambio.PERFIL, Handle = ini.Handle, Elemento = n, Antes = "", Despues = n,
                SemillaX = (ini.XIni + ini.XFin) / 2.0, SemillaY = (ini.YIni + ini.YFin) / 2.0,
                FinX = fin == null ? (double?)null : (fin.XIni + fin.XFin) / 2.0,
                FinY = fin == null ? (double?)null : (fin.YIni + fin.YFin) / 2.0,
            };
            cp.Handles.Add(ini.Handle);
            if (fin != null) cp.Handles.Add(fin.Handle);
            cp.Consecuencias.Add(fin == null
                ? $"Perfil de la red {ini.Red} siguiendo su recorrido desde {ini.Nombre} (como CREAR_PERFIL_RED)."
                : $"Perfil de la red {ini.Red} desde {ini.Nombre} hasta {fin.Nombre}.");
            cp.Consecuencias.Add("Se coloca debajo del dibujo, con su eje, terreno, rótulos y cruces.");
            if (!ini.CotaIni.HasValue || !ini.CotaFin.HasValue) cp.Advertencias.Add($"{ini.Nombre} no tiene cotas: el perfil puede salir plano.");
            return cp;
        }

        // ------------------------------------------------------------ textos

        public static string Grupo(List<Tuberia> ts)
        {
            var us = ts.Select(t => t.Utilidad()).Distinct().ToList();
            if (us.Count == 1) return us[0];
            var rs = ts.Select(t => t.Red).Distinct().ToList();
            return rs.Count == 1 ? "la red " + rs[0] : $"{rs.Count} redes";
        }

        private static string Rango(List<double> vs, string u)
        {
            if (vs.Count == 0) return "";
            double a = vs.Min(), b = vs.Max();
            return Math.Abs(a - b) < 0.005 ? Materiales.F(a) + u : $"{Materiales.F(a)} a {Materiales.F(b)}{u}";
        }

        public static string Lista(List<string> xs) =>
            string.Join(", ", xs.Take(6)) + (xs.Count > 6 ? $" (y {xs.Count - 6} más)" : "");
    }
}
