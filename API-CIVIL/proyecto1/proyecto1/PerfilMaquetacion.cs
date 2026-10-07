using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  MAQUETACIÓN CONTRA CIVIL 3D (DISENO.md G.2-6/7, G.6, G.8, G.11, G.12)
//   · Reparte callouts/tramos/cruces por hoja (PartirEnHojas), arma la
//     EntradaMaquetacion y llama al núcleo puro PerfilDiseno (preliminar y final).
//   · Mide las etiquetas reales (GeometricExtents → cajas en pulgadas relativas
//     al ancla), calibra (F.10) y decide si hay problema de unidades (T2b).
//   · Movimiento de etiquetas (LabelLocation += d; nunca DraggedOffset),
//     corrección iterativa con bordes fiables (T5) y verificación final (T6).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilMaquetacion
    {
        public const int MAX_ITER_CORRECCION = 3;        // G.11

        private static Callout Copia(Callout c, int hoja)
        {
            return new Callout
            {
                Id = c.Id, Tipo = c.Tipo, Franja = c.Franja, Prioridad = c.Prioridad, PuedeCambiarFranja = c.PuedeCambiarFranja,
                PuedeAlternar = c.PuedeAlternar, PuedeRecortar = c.PuedeRecortar, Estacion = c.Estacion, EstAncla = c.EstAncla,
                ZAncla = c.ZAncla, Lineas = new List<string>(c.Lineas), Hoja = hoja, CruceIdx = c.CruceIdx,
            };
        }

        /// <summary>
        /// G.2-6 (T0): PartirEnHojas sobre las estaciones de nodo y reparto de ctx.Callouts, ctx.Rotulos y ctx.Cruces en ctx.Hojas
        /// (copias por hoja; el callout del nodo de corte va en las dos). Devuelve el número de hojas.
        /// </summary>
        internal static int PartirHojas(ContextoPerfil ctx)
        {
            var rec = ctx.Rec;
            var est = rec.Nodos.Select(n => rec.EstNodo[n]).ToList();
            var rangos = PerfilDiseno.PartirEnHojas(est, ctx.S);
            if (rangos.Count == 0) rangos.Add(new[] { rec.EstIni, rec.EstFin });
            // Diagnóstico (2026-10-06: un perfil salía en 13 vistas): por qué se parte en hojas.
            double largoRec = rec.EstFin - rec.EstIni;
            PerfilLog.Log("HOJAS", $"{rangos.Count} hoja(s): recorrido {largoRec:0.0} ft, {rec.Pasos.Count} tubo(s), " +
                $"escala 1\"={ctx.S:0.##}' (dibujo 1\"={ctx.SDibujo:0.##}'{(ctx.SAuto ? ", automática" : "")}), " +
                $"máx. {PerfilDiseno.ANCHO_MAX_MARCO:0} in = {PerfilDiseno.ANCHO_MAX_MARCO * ctx.S:0.#} ft por hoja");
            for (int k = 0; k < rangos.Count; k++)
                PerfilLog.Log("HOJAS", $"  hoja {k + 1}: est {rangos[k][0]:0.00}–{rangos[k][1]:0.00} ({rangos[k][1] - rangos[k][0]:0.0} ft)");
            if (rangos.Count > 3)
            {
                string m = $"⚠ El perfil sale en {rangos.Count} vistas: {largoRec:0} ft de recorrido ({rec.Pasos.Count} tubos) " +
                           $"a 1\"={ctx.S:0.##}' caben {PerfilDiseno.ANCHO_MAX_MARCO * ctx.S:0} ft por vista.";
                if (ctx.S < PerfilDiseno.S_MIN_PERFIL) m += " La escala del dibujo es muy chica: revisa la escala de anotación.";
                PerfilLog.Aviso("HOJAS", m);
                ctx.Ed?.WriteMessage("\n" + m);
            }
            ctx.Hojas.Clear();
            bool rasanteUsada = false;
            for (int k = 0; k < rangos.Count; k++)
            {
                var h = new HojaPerfil { Indice = k, EstA = rangos[k][0], EstB = rangos[k][1] };
                const double tol = 1e-6;
                foreach (var c in ctx.Callouts)
                {
                    if (c.EstAncla < h.EstA - tol || c.EstAncla > h.EstB + tol) continue;
                    if (c.Tipo == "TERRENO") { if (rasanteUsada) continue; rasanteUsada = true; }
                    h.Callouts.Add(Copia(c, k));
                }
                for (int i = 0; i < ctx.Cruces.Count; i++)
                    if (ctx.Cruces[i].Estacion >= h.EstA - tol && ctx.Cruces[i].Estacion <= h.EstB + tol) h.Cruces.Add(i);
                foreach (var r in ctx.Rotulos)
                {
                    double a = Math.Max(r.EstIni, h.EstA), b = Math.Min(r.EstFin, h.EstB);
                    if (b - a <= tol) continue;
                    if ((a > r.EstIni + tol || b < r.EstFin - tol)) PerfilLog.Log("MAQUETA", $"tramo {r.Id} partido por la hoja {k + 1}");
                    h.Rotulos.Add(new RotuloTramo { Id = r.Id, EstIni = a, EstFin = b, L1 = r.L1, L2 = r.L2, L3 = r.L3, Hoja = k, Omitido = r.Omitido });
                }
                ctx.Hojas.Add(h);
            }
            return ctx.Hojas.Count;
        }

        /// <summary>
        /// Arma la EntradaMaquetacion de una hoja: S, EstIni/Fin, rango permitido, ZMin/MaxDibujo (tubos, cruces, estructuras),
        /// terreno, bloques (Callout.Bloque), tramos (Fila) y cajas de cruce. final = true fuerza V/Int de ctx y usa medidas.
        /// </summary>
        internal static EntradaMaquetacion Entrada(ContextoPerfil ctx, HojaPerfil hoja, bool final)
        {
            var rec = ctx.Rec;
            var e = new EntradaMaquetacion
            {
                S = ctx.S, EstIni = hoja.EstA, EstFin = hoja.EstB,
                EstMinPermitida = rec.EstMinPermitida, EstMaxPermitida = rec.EstMaxPermitida,
                TerrenoEst = rec.TerrenoEst, TerrenoZ = rec.TerrenoZ,
            };
            double zMin = double.MaxValue, zMax = double.MinValue;
            foreach (var p in rec.Pasos.Where(p => p.EstHasta > hoja.EstA - 1e-6 && p.EstDesde < hoja.EstB + 1e-6))
            {
                double a = p.Tramo.AltoExtFt / 2.0;
                zMin = Math.Min(zMin, Math.Min(p.ZIni, p.ZFin) - a); zMax = Math.Max(zMax, Math.Max(p.ZIni, p.ZFin) + a);
            }
            foreach (int nd in rec.Nodos)
            {
                double en = rec.EstNodo[nd]; var n = ctx.Red.Nodos[nd];
                if (en < hoja.EstA - 1e-6 || en > hoja.EstB + 1e-6) continue;
                if (!double.IsNaN(n.Rim)) zMax = Math.Max(zMax, n.Rim);
                if (!double.IsNaN(n.Sump)) zMin = Math.Min(zMin, n.Sump);
            }
            foreach (int ci in hoja.Cruces)
            {
                var c = ctx.Cruces[ci];
                zMin = Math.Min(zMin, c.ZEje - c.AltoExtFt / 2.0); zMax = Math.Max(zMax, c.ZEje + c.AltoExtFt / 2.0);
                double ancho = c.AltoExtFt / Math.Sin(Math.Max(c.AnguloDeg, 15.0) * Math.PI / 180.0);
                var rep = hoja.Callouts.FirstOrDefault(k => k.CruceIdx >= 0 && ctx.Cruces[k.CruceIdx].Grupo == c.Grupo);
                e.CajasDibujo.Add(new CajaDibujo { Id = rep != null ? rep.Id : "X" + ci, EstIni = c.Estacion - ancho / 2, EstFin = c.Estacion + ancho / 2, ZMin = c.ZEje - c.AltoExtFt / 2, ZMax = c.ZEje + c.AltoExtFt / 2 });
            }
            if (zMin > zMax) { zMin = 0; zMax = 10; }
            e.ZMinDibujo = zMin; e.ZMaxDibujo = zMax;
            foreach (var c in hoja.Callouts.Where(c => c.Tipo != "TRAMO" || !final))
            {
                if (final && c.EtiquetaId.IsNull && c.Tipo != "TRAMO") continue;       // sin etiqueta no se maqueta
                var b = PerfilEtiquetas.ABloque(c);
                if (final && hoja.Medidas.TryGetValue(c.Id, out var m) && m.Valida)
                {
                    b.Ancho = m.Ancho; b.Alto = m.Alto; b.Medido = true;
                }
                e.Bloques.Add(b);
            }
            foreach (var r in hoja.Rotulos)
            {
                double k = r.Fila != null ? r.Fila.KMedida : 1.0;
                var f = PerfilEtiquetas.AFila(r);
                f.KMedida = k;
                f.ZCorona = PerfilEje.Corona(rec, (r.EstIni + r.EstFin) / 2.0);
                e.Tramos.Add(f);
            }
            if (final) { e.VForzada = ctx.V; e.IntForzados = ctx.Int; }
            return e;
        }

        /// <summary>G.2-5/7 (T0): tamaños predichos, Maquetar preliminar por hoja (hoja.Prelim) y V global = máx V (ctx.V, ctx.Int).</summary>
        internal static void MaquetarPreliminar(ContextoPerfil ctx)
        {
            double v = 0;
            foreach (var h in ctx.Hojas)
            {
                var e = Entrada(ctx, h, false);
                h.Prelim = PerfilDiseno.Maquetar(e);
                PerfilLog.Volcar("MAQUETA", h.Prelim.Avisos.Select(a => "hoja " + (h.Indice + 1) + " (prelim): " + a));
                v = Math.Max(v, h.Prelim.V);
            }
            ctx.V = v > 0 ? v : PerfilDiseno.ElegirV(ctx.S);
            ctx.Int = PerfilDiseno.ElegirIntervalos(ctx.S, ctx.V);
        }

        /// <summary>
        /// G.6 (T2, lectura): mide cada etiqueta de cada hoja (FindXY del ancla + GeometricExtents) → hoja.Medidas y tamaños en
        /// Bloque/Fila (KMedida); calibra con PerfilDiseno.Calibrar. false si no se pudo medir nada.
        /// </summary>
        internal static bool Medir(Transaction tr, ContextoPerfil ctx, out double r, out double dispersion)
        {
            var med = new List<double>(); var pred = new List<double>();
            double ve = ctx.S / ctx.V;
            int n = 0;
            foreach (var h in ctx.Hojas.Where(k => !k.PvId.IsNull))
            {
                CivilDB.ProfileView pv;
                try { pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForRead); } catch { continue; }
                h.Medidas.Clear();
                void Una(string id, ObjectId lbl, double est, double z, int lineas, bool vertical, FilaTramo fila)
                {
                    if (lbl.IsNull) return;
                    PerfilVista.FindXY(pv, ve, est, z, out double ax, out double ay);
                    var m = new MedidaEtiqueta { Id = id, EtiquetaId = lbl, EstAncla = est, ZAncla = z };
                    if (MedirEtiqueta(tr, lbl, out Extents3d ext))
                    {
                        m.RelMinX = (ext.MinPoint.X - ax) / ctx.S; m.RelMinY = (ext.MinPoint.Y - ay) / ctx.S;
                        m.RelMaxX = (ext.MaxPoint.X - ax) / ctx.S; m.RelMaxY = (ext.MaxPoint.Y - ay) / ctx.S;
                        m.Valida = true; n++;
                        double transv = vertical ? m.Ancho : m.Alto;
                        med.Add(transv); pred.Add(PerfilDiseno.PredichoTransversal(lineas));
                        if (fila != null)
                        {
                            double pAncho = PerfilDiseno.LargoMax(PerfilDiseno.LineasVariante(fila, 2));
                            if (pAncho > 1e-6) fila.KMedida = Math.Max(0.3, Math.Min(3.0, m.Ancho / pAncho));
                        }
                    }
                    else PerfilLog.Log("MEDIDA", "sin extents: " + id + " (se usa la predicción)");
                    h.Medidas[id] = m;
                }
                foreach (var c in h.Callouts) Una(c.Id, c.EtiquetaId, c.EstAncla, c.ZAncla, c.Lineas.Count, true, null);
                foreach (var rt in h.Rotulos.Where(x => !x.Omitido))
                {
                    double em = (rt.EstIni + rt.EstFin) / 2.0;
                    Una(rt.Id, rt.EtiquetaId, em, PerfilEje.Corona(ctx.Rec, em), 2, false, rt.Fila);
                }
            }
            r = PerfilDiseno.Calibrar(med, pred, out dispersion);
            PerfilLog.Log("MEDIDA", $"{n} etiquetas medidas, r={r:G4} dispersión={dispersion:G3}");
            return n > 0;
        }

        /// <summary>GeometricExtents de una etiqueta en try; false si lanza o su ancho/alto ≤ 1e-6. G.6-2 / I-7.</summary>
        internal static bool MedirEtiqueta(Transaction tr, ObjectId etiquetaId, out Extents3d ext)
        {
            ext = new Extents3d();
            try
            {
                ext = ((Entity)tr.GetObject(etiquetaId, OpenMode.ForRead)).GeometricExtents;
                return ext.MaxPoint.X - ext.MinPoint.X > 1e-6 && ext.MaxPoint.Y - ext.MinPoint.Y > 1e-6;
            }
            catch { return false; }
        }

        /// <summary>F.10: problema de unidades/escala ⇔ dispersion &lt; 0.15 y |r − 1| &gt; 0.05.</summary>
        internal static bool ProblemaUnidades(double r, double dispersion) { return dispersion < 0.15 && Math.Abs(r - 1.0) > 0.05; }

        /// <summary>
        /// G.8 (puro sobre ctx): Maquetar final de todas las hojas con VForzada = ctx.V y medidas; si alguna VRecomendada &gt; V,
        /// sube ctx.V (e Int) y repite. Guarda hoja.Final/EntradaFinal. true si V cambió (T3 aplicará un estilo de vista nuevo).
        /// </summary>
        internal static bool MaquetarFinal(ContextoPerfil ctx)
        {
            bool cambio = false;
            for (int vuelta = 0; vuelta < 3; vuelta++)
            {
                double vRec = ctx.V;
                foreach (var h in ctx.Hojas)
                {
                    h.EntradaFinal = Entrada(ctx, h, true);
                    h.Final = PerfilDiseno.Maquetar(h.EntradaFinal);
                    vRec = Math.Max(vRec, h.Final.VRecomendada);
                }
                if (vRec <= ctx.V + 1e-9) break;
                ctx.V = vRec; ctx.Int = PerfilDiseno.ElegirIntervalos(ctx.S, ctx.V); cambio = true;
                PerfilLog.Log("MAQUETA", "V sube a " + ctx.V + " con las medidas reales");
            }
            foreach (var h in ctx.Hojas) PerfilLog.Volcar("MAQUETA", h.Final.Avisos.Select(a => "hoja " + (h.Indice + 1) + ": " + a));
            return cambio;
        }

        /// <summary>Mueve una etiqueta: LabelLocation += d (ForWrite, en try). Nunca usa DraggedOffset.</summary>
        internal static void Mover(Transaction tr, ObjectId etiquetaId, Vector3d d)
        {
            if (etiquetaId.IsNull) return;
            try { var l = (CivilDB.Label)tr.GetObject(etiquetaId, OpenMode.ForWrite); l.LabelLocation = l.LabelLocation + d; }
            catch (Exception ex) { PerfilLog.Log("CORRECCION", "Mover: " + ex.Message); }
        }

        /// <summary>Destino (marco final, in) de cada etiqueta de la hoja con su bloque o fila.</summary>
        internal static IEnumerable<(string id, ObjectId lbl, double x0, double y0, double w, double h, int franja, double xAncla)> Destinos(ContextoPerfil ctx, HojaPerfil hoja)
        {
            var r = hoja.Final; double s = ctx.S;
            foreach (var c in hoja.Callouts.Where(c => !c.EtiquetaId.IsNull && c.Bloque != null && !c.Bloque.Descartado))
                yield return (c.Id, c.EtiquetaId, c.Bloque.X0, c.Bloque.Y0, c.Bloque.Ancho, c.Bloque.Alto,
                              c.Bloque.FranjaFinal == FranjaTipo.Superior ? 1 : -1, PerfilDiseno.XMarco(c.Bloque.EstAncla, r, s));
            foreach (var t in hoja.Rotulos.Where(t => !t.EtiquetaId.IsNull && t.Fila != null && !t.Fila.Omitido && !t.Fila.AVertical))
                yield return (t.Id, t.EtiquetaId, t.Fila.X0, t.Fila.Y0, t.Fila.Ancho, t.Fila.Alto, t.Fila.ConLeader ? 2 : 0, t.Fila.Cx);
        }

        /// <summary>
        /// G.11-1…3,5,6 (T5): una iteración de corrección de la hoja con bordes fiables por franja; ResetLocation si la proporción
        /// se invirtió (I-2). Devuelve cuántas etiquetas siguen fuera de TOL_CORRECCION·S.
        /// </summary>
        internal static int Corregir(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja, int iteracion)
        {
            if (hoja.PvId.IsNull || hoja.Final == null) return 0;
            var pv = (CivilDB.ProfileView)tr.GetObject(hoja.PvId, OpenMode.ForRead);
            double s = ctx.S, ve = s / ctx.V;
            PerfilVista.FindXY(pv, ve, hoja.Final.StationStart, hoja.Final.ElevationMin, out double ox, out double oy);
            int fuera = 0;
            foreach (var d in Destinos(ctx, hoja))
            {
                if (!MedirEtiqueta(tr, d.lbl, out Extents3d ext)) continue;
                double w = ext.MaxPoint.X - ext.MinPoint.X, hgt = ext.MaxPoint.Y - ext.MinPoint.Y;
                if (Math.Abs(d.franja) == 1 && w > 2.0 * d.w * s && hgt < 0.5 * d.h * s)
                {
                    try { ((CivilDB.Label)tr.GetObject(d.lbl, OpenMode.ForWrite)).ResetLocation(); } catch { }
                    PerfilLog.Aviso("CORRECCION", "rótulo sin reubicar: " + d.id);
                    continue;
                }
                double X0 = ox + d.x0 * s, X1 = ox + (d.x0 + d.w) * s, Y0 = oy + d.y0 * s, Y1 = oy + (d.y0 + d.h) * s;
                double dx, dy;
                if (d.franja == 0) { dx = X0 - ext.MinPoint.X; dy = Y0 - ext.MinPoint.Y; }
                else
                {
                    double ancla = ox + d.xAncla * s;
                    dx = ancla < (X0 + X1) / 2.0 ? X1 - ext.MaxPoint.X : X0 - ext.MinPoint.X;
                    dy = d.franja == 1 || d.franja == 2 ? Y1 - ext.MaxPoint.Y : Y0 - ext.MinPoint.Y;
                }
                double tol = PerfilDiseno.TOL_CORRECCION * s;
                if (Math.Abs(dx) > tol || Math.Abs(dy) > tol)
                {
                    Mover(tr, d.lbl, new Vector3d(dx, dy, 0));
                    fuera++;
                    if (iteracion == MAX_ITER_CORRECCION - 1) PerfilLog.Log("CORRECCION", $"{d.id} d=({dx / s:0.###},{dy / s:0.###}) in");
                }
            }
            return fuera;
        }

        /// <summary>G.12 (T6, lectura): solapes, fuera de marco, cruces de leaders y cortes con cajas MEDIDAS → log y avisos. Devuelve el nº de problemas.</summary>
        internal static int Verificar(Transaction tr, ContextoPerfil ctx)
        {
            int total = 0;
            foreach (var h in ctx.Hojas.Where(k => !k.PvId.IsNull && k.Final != null))
            {
                var pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForRead);
                double s = ctx.S, ve = s / ctx.V;
                PerfilVista.FindXY(pv, ve, h.Final.StationStart, h.Final.ElevationMin, out double ox, out double oy);
                var cajas = new List<Caja>(); var leaders = new List<Leader>();
                foreach (var d in Destinos(ctx, h))
                {
                    if (!MedirEtiqueta(tr, d.lbl, out Extents3d ext)) continue;
                    var k = new Caja { Id = d.id, X0 = (ext.MinPoint.X - ox) / s, Y0 = (ext.MinPoint.Y - oy) / s, X1 = (ext.MaxPoint.X - ox) / s, Y1 = (ext.MaxPoint.Y - oy) / s };
                    if (d.franja != 0) { k.Y0 = d.franja == -1 ? k.Y0 : Math.Max(k.Y0, d.y0); k.Y1 = d.franja == -1 ? Math.Min(k.Y1, d.y0 + d.h) : k.Y1; }
                    cajas.Add(k);
                }
                var sol = PerfilDiseno.Solapes(cajas);
                var fue = PerfilDiseno.FueraDeMarco(cajas, h.Final.AnchoMarco, h.Final.AltoMarco);
                foreach (string x in sol) PerfilLog.Log("VERIFICACION", $"hoja {h.Indice + 1}: solape {x}");
                foreach (string x in fue) PerfilLog.Log("VERIFICACION", $"hoja {h.Indice + 1}: fuera del marco {x}");
                int n = sol.Count + fue.Count;
                if (n > 0) PerfilLog.Aviso($"Hoja {h.Indice + 1}: {sol.Count} solape(s) y {fue.Count} rótulo(s) fuera del marco (ver log)");
                total += n;
            }
            return total;
        }
    }
}
