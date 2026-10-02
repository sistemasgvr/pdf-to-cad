using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  EJE PROPIO DEL PERFIL (DISENO.md D)
//   · Nombre único «PERFIL {red} ({n})» contra ejes (con y sin sitio) y vistas.
//   · Creación del eje en la capa PDFCAD_PERFIL_EJE con
//     ComandosAlineamientos.CrearAlineamientoDesdePts (sobrecarga con capa/estilo/
//     juego) y ReferencePointStation para que N0 quede en 1+00.
//   · Estaciones definitivas con StationOffset (T1a) y consultas sobre el
//     recorrido: cota de eje, corona, fondo y terreno por estación (D.3, D.4).
//   · Muestreo del terreno en T0 con Surface.FindElevationAtXY (D.4).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilEje
    {
        /// <summary>D.1: nombre único "PERFIL {red saneada} ({n})" (sin choques con ejes, vistas ni hojas " - H"). n sale por out.</summary>
        internal static string NombreUnico(Transaction tr, CivilDocument civDoc, string nombreRed, out int n)
        {
            string red = PerfilTextos.SanearNombre(nombreRed);
            if (red.Length == 0) red = "RED";
            var usados = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var ejes = new List<ObjectId>();
            try { foreach (ObjectId id in civDoc.GetAlignmentIds()) ejes.Add(id); } catch { }
            try { foreach (ObjectId id in civDoc.GetSitelessAlignmentIds()) ejes.Add(id); } catch { }
            try
            {
                foreach (ObjectId sid in civDoc.GetSiteIds())
                    try { var site = (CivilDB.Site)tr.GetObject(sid, OpenMode.ForRead); foreach (ObjectId id in site.GetAlignmentIds()) ejes.Add(id); } catch { }
            }
            catch { }
            foreach (ObjectId id in ejes.Distinct())
            {
                try
                {
                    var a = (CivilDB.Alignment)tr.GetObject(id, OpenMode.ForRead);
                    usados.Add(a.Name);
                    foreach (ObjectId pv in a.GetProfileViewIds())
                        try { usados.Add(((CivilDB.ProfileView)tr.GetObject(pv, OpenMode.ForRead)).Name); } catch { }
                }
                catch { }
            }
            for (n = 1; n < 10000; n++)
            {
                string nom = "PERFIL " + red + " (" + n + ")";
                if (usados.Contains(nom)) continue;
                if (usados.Any(u => u.StartsWith(nom + " - H", StringComparison.OrdinalIgnoreCase))) continue;
                return nom;
            }
            n = 0;
            return "PERFIL " + red + " (" + Guid.NewGuid().ToString("N").Substring(0, 6) + ")";
        }

        /// <summary>D.1: nombre de la hoja k (0-based): k = 0 → nombre; si no nombre + " - H" + (k+1).</summary>
        internal static string NombreHoja(string nombre, int k) { return k == 0 ? nombre : nombre + " - H" + (k + 1); }

        /// <summary>D.1: nombre del perfil de terreno: nombre + " - EX. GRADE".</summary>
        internal static string NombreTerreno(string nombre) { return nombre + " - EX. GRADE"; }

        /// <summary>
        /// D.2 (T1a): crea el eje desde rec.Traza (capa CapaEjeId, EjeStyle, LabelSetEjeVacio; reintento con estilos [0]),
        /// fija ReferencePointStation = 100 − (s0 − StartingStation) y comprueba StationOffset(N0) = 100.00 ± 0.01.
        /// Devuelve ObjectId.Null si no se pudo crear (fatal para el comando).
        /// </summary>
        internal static ObjectId Crear(Transaction tr, Database db, CivilDocument civDoc, Recorrido rec, string nombre, EstilosPerfil est)
        {
            var pts = rec.Traza.Select(v => new ComandosRedes.TrazaPt(new Point3d(v.X, v.Y, 0), v.Bulge)).ToList();
            ObjectId id = ComandosAlineamientos.CrearAlineamientoDesdePts(db, civDoc, tr, pts, nombre, est.CapaEjeId, est.EjeStyle, est.LabelSetEjeVacio);
            if (id.IsNull)
            {
                PerfilLog.Log("EJE", "reintento con los estilos [0]");
                try
                {
                    id = ComandosAlineamientos.CrearAlineamientoDesdePts(db, civDoc, tr, pts, nombre, est.CapaEjeId,
                        civDoc.Styles.AlignmentStyles[0], civDoc.Styles.LabelSetStyles.AlignmentLabelSetStyles[0]);
                }
                catch (Exception ex) { PerfilLog.Error("EJE", "reintento", ex); }
            }
            if (id.IsNull) return ObjectId.Null;
            try
            {
                var a = (CivilDB.Alignment)tr.GetObject(id, OpenMode.ForWrite);
                var n0 = rec.Red.Nodos[rec.Nodos[0]];
                double s0 = 0, off = 0;
                a.StationOffset(n0.X, n0.Y, ref s0, ref off);
                a.ReferencePointStation = PerfilRecorrido.EST_INICIAL - (s0 - a.StartingStation);
                double chk = 0, off2 = 0;
                a.StationOffset(n0.X, n0.Y, ref chk, ref off2);
                if (Math.Abs(chk - PerfilRecorrido.EST_INICIAL) > 0.01) PerfilLog.Log("EJE", $"N0 queda en {chk:0.000} (esperado 100.00)");
            }
            catch (Exception ex) { PerfilLog.Error("EJE", "ReferencePointStation", ex); }
            return id;
        }

        private static bool Estacion(CivilDB.Alignment a, double x, double y, out double est)
        {
            est = double.NaN; double off = 0;
            try { a.StationOffset(x, y, ref est, ref off); return true; }
            catch
            {
                try
                {
                    bool fuera = false;
                    a.StationOffsetAcceptOutOfRange(x, y, ref est, ref off, ref fuera);
                    if (fuera) PerfilLog.Log("EJE", $"punto ({x:0.00},{y:0.00}) fuera del eje");
                    return true;
                }
                catch { return false; }
            }
        }

        /// <summary>
        /// D.3 (T1a): estaciones DEFINITIVAS con StationOffset (respaldo AcceptOutOfRange) de nodos, extremos de tubo (EstP*),
        /// EstDesde/EstHasta y cruces (Cruce.X/Y); log si difieren &gt; 0.05 ft; monotonía; EstMin/MaxPermitida = Starting/EndingStation.
        /// </summary>
        internal static void EstacionesDefinitivas(Transaction tr, ObjectId alignId, Recorrido rec, List<Cruce> cruces)
        {
            CivilDB.Alignment a;
            try { a = (CivilDB.Alignment)tr.GetObject(alignId, OpenMode.ForRead); }
            catch (Exception ex) { PerfilLog.Error("EJE", "abrir eje", ex); return; }
            double Def(string id, double x, double y, double pre)
            {
                if (!Estacion(a, x, y, out double e) || double.IsNaN(e)) return pre;
                if (Math.Abs(e - pre) > 0.05) PerfilLog.Log("EJE", $"estación {id}: {pre:0.00} → {e:0.00}");
                return e;
            }
            var nuevo = new Dictionary<int, double>();
            foreach (int nd in rec.Nodos.Distinct())
            {
                var n = rec.Red.Nodos[nd];
                nuevo[nd] = Def("nodo " + nd, n.X, n.Y, rec.EstNodo.TryGetValue(nd, out double p) ? p : 0);
            }
            var lista = rec.Nodos.Select(i => nuevo[i]).ToList();
            if (PerfilRecorrido.EsEstrictamenteCreciente(lista)) rec.EstNodo = nuevo;
            else PerfilLog.Aviso("EJE", "Estaciones de nodo no crecientes: se conservan las de la traza");
            foreach (var p in rec.Pasos)
            {
                p.EstDesde = rec.EstNodo[p.NodoDesde]; p.EstHasta = rec.EstNodo[p.NodoHasta];
                Point3d ini = p.Invertido ? p.Tramo.PFin : p.Tramo.PIni, fin = p.Invertido ? p.Tramo.PIni : p.Tramo.PFin;
                p.EstPIni = Def("tubo " + p.Tramo.Id + " ini", ini.X, ini.Y, p.EstPIni);
                p.EstPFin = Def("tubo " + p.Tramo.Id + " fin", fin.X, fin.Y, p.EstPFin);
            }
            if (cruces != null) foreach (var c in cruces) c.Estacion = Def("cruce " + c.PipeId.Handle, c.X, c.Y, c.Estacion);
            rec.EstIni = rec.EstNodo[rec.Nodos[0]]; rec.EstFin = rec.EstNodo[rec.Nodos[rec.Nodos.Count - 1]];
            try { rec.EstMinPermitida = a.StartingStation; rec.EstMaxPermitida = a.EndingStation; } catch { }
        }

        /// <summary>D.3 (T0): estaciones preliminares puras (DistanciaEnTraza) de nodos, extremos de tubo y rango permitido.</summary>
        internal static void EstacionesPreliminares(Recorrido rec)
        {
            double Est(double x, double y) { return PerfilRecorrido.EstacionPreliminar(rec.Traza, rec.DistN0, new V2(x, y)); }
            rec.EstNodo = new Dictionary<int, double>();
            double acum = PerfilRecorrido.EST_INICIAL;
            var lista = new List<double>();
            foreach (int nd in rec.Nodos) { var n = rec.Red.Nodos[nd]; lista.Add(Est(n.X, n.Y)); }
            if (!PerfilRecorrido.EsEstrictamenteCreciente(lista))
            {
                PerfilLog.Aviso("EJE", "Estaciones preliminares no crecientes: se usa la distancia acumulada");
                lista.Clear(); lista.Add(acum);
                foreach (var p in rec.Pasos) { acum += Math.Max(0.01, p.Tramo.Longitud2D); lista.Add(acum); }
            }
            for (int i = 0; i < rec.Nodos.Count; i++) rec.EstNodo[rec.Nodos[i]] = lista[i];
            foreach (var p in rec.Pasos)
            {
                p.EstDesde = rec.EstNodo[p.NodoDesde]; p.EstHasta = rec.EstNodo[p.NodoHasta];
                Point3d ini = p.Invertido ? p.Tramo.PFin : p.Tramo.PIni, fin = p.Invertido ? p.Tramo.PIni : p.Tramo.PFin;
                p.EstPIni = Est(ini.X, ini.Y); p.EstPFin = Est(fin.X, fin.Y);
                if (p.EstPFin < p.EstPIni) { p.EstPIni = p.EstDesde; p.EstPFin = p.EstHasta; }
            }
            rec.EstIni = lista[0]; rec.EstFin = lista[lista.Count - 1];
            rec.EstMinPermitida = PerfilRecorrido.EST_INICIAL - rec.DistN0;
            rec.EstMaxPermitida = PerfilRecorrido.EST_INICIAL + PerfilRecorrido.LargoTraza(rec.Traza) - rec.DistN0;
        }

        /// <summary>
        /// D.4 (T0): muestrea la superficie cada PASO_TERRENO ft sobre la traza en [EstMinPermitida, EstMaxPermitida]
        /// (FindElevationAtXY, cada muestra en try → NaN). false si no hay superficie o todas son NaN.
        /// </summary>
        internal static bool MuestrearTerreno(Transaction tr, Recorrido rec, ObjectId superficieId)
        {
            rec.TerrenoEst = new double[0]; rec.TerrenoZ = new double[0];
            if (superficieId.IsNull || !superficieId.IsValid) return false;
            CivilDB.Surface sup;
            try { sup = (CivilDB.Surface)tr.GetObject(superficieId, OpenMode.ForRead); } catch { return false; }
            var es = new List<double>(); var zs = new List<double>();
            for (double e = rec.EstMinPermitida; e <= rec.EstMaxPermitida + 1e-9; e += PerfilRecorrido.PASO_TERRENO)
            {
                V2 p = PerfilRecorrido.PuntoEnTraza(rec.Traza, e - PerfilRecorrido.EST_INICIAL + rec.DistN0);
                double z = double.NaN;
                try { z = sup.FindElevationAtXY(p.X, p.Y); } catch { }
                es.Add(e); zs.Add(z);
            }
            rec.TerrenoEst = es.ToArray(); rec.TerrenoZ = zs.ToArray();
            bool alguna = zs.Any(z => !double.IsNaN(z));
            PerfilLog.Log("EJE", $"terreno: {zs.Count(z => !double.IsNaN(z))}/{zs.Count} muestras válidas");
            return alguna;
        }

        /// <summary>D.3: cota de EJE del recorrido en una estación (lineal dentro del tubo; hasta el centro del accesorio en los huecos). ft.</summary>
        internal static double ZEjeRecorrido(Recorrido rec, double est)
        {
            var ps = rec.Pasos;
            if (ps.Count == 0) return double.NaN;
            if (est <= ps[0].EstPIni) return ps[0].ZIni;
            for (int i = 0; i < ps.Count; i++)
            {
                var p = ps[i];
                if (est >= p.EstPIni - 1e-9 && est <= p.EstPFin + 1e-9)
                    return PerfilRecorrido.Interpolar(est, p.EstPIni, p.ZIni, p.EstPFin, p.ZFin);
                if (i + 1 < ps.Count && est > p.EstPFin && est < ps[i + 1].EstPIni)
                {
                    var q = ps[i + 1];
                    var n = rec.Red.Nodos[p.NodoHasta];
                    double en = rec.EstNodo.TryGetValue(p.NodoHasta, out double v) ? v : (p.EstPFin + q.EstPIni) / 2.0;
                    if (!double.IsNaN(n.ZEje))
                        return est <= en ? PerfilRecorrido.Interpolar(est, p.EstPFin, p.ZFin, en, n.ZEje)
                                         : PerfilRecorrido.Interpolar(est, en, n.ZEje, q.EstPIni, q.ZIni);
                    return est <= en ? p.ZFin : q.ZIni;
                }
            }
            return ps[ps.Count - 1].ZFin;
        }

        /// <summary>D.3: alto exterior (ft) del tubo del recorrido en esa estación (el del paso más cercano).</summary>
        internal static double AltoExtEn(Recorrido rec, double est) { var p = PasoEn(rec, est); return p == null ? 0 : p.Tramo.AltoExtFt; }

        /// <summary>D.3: corona = ZEje + AltoExt/2 (ft).</summary>
        internal static double Corona(Recorrido rec, double est) { return ZEjeRecorrido(rec, est) + AltoExtEn(rec, est) / 2.0; }

        /// <summary>D.3: fondo exterior = ZEje − AltoExt/2 (ft).</summary>
        internal static double Fondo(Recorrido rec, double est) { return ZEjeRecorrido(rec, est) - AltoExtEn(rec, est) / 2.0; }

        /// <summary>D.4: cota de terreno interpolada de las muestras (NaN si no hay o cae en un hueco). ft.</summary>
        internal static double TerrenoEn(Recorrido rec, double est)
        {
            var e = rec.TerrenoEst; var z = rec.TerrenoZ;
            if (e == null || z == null || e.Length < 1) return double.NaN;
            for (int i = 0; i + 1 < e.Length; i++)
                if (est >= e[i] - 1e-9 && est <= e[i + 1] + 1e-9)
                {
                    if (double.IsNaN(z[i]) || double.IsNaN(z[i + 1])) return double.IsNaN(z[i]) ? z[i + 1] : z[i];
                    return PerfilRecorrido.Interpolar(est, e[i], z[i], e[i + 1], z[i + 1]);
                }
            return double.NaN;
        }

        /// <summary>Paso del recorrido que contiene la estación (o el más cercano); null si no hay pasos.</summary>
        internal static PasoRecorrido PasoEn(Recorrido rec, double est)
        {
            if (rec.Pasos.Count == 0) return null;
            foreach (var p in rec.Pasos) if (est >= p.EstDesde - 1e-9 && est <= p.EstHasta + 1e-9) return p;
            return rec.Pasos.OrderBy(p => Math.Min(Math.Abs(est - p.EstDesde), Math.Abs(est - p.EstHasta))).First();
        }
    }
}
