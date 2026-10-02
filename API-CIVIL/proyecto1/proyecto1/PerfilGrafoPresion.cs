using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  GRAFO DE LA RED DESDE CIVIL 3D — presión (DISENO.md C.3)
//   · Accesorios = sólidos 3DSOLID con XDATA PDFCAD_FITTING (WyeSolido.LeerXData
//     + PerfilTextos.ParsearXData), SIN filtrar por RED.
//   · Tubos PressurePipe (degenerados → Verticales), bulge verificado.
//   · Asignación extremo → accesorio en 3D (PerfilRecorrido.ElegirAccesorio),
//     uniones/extremos libres, aristas y ramales verticales.
//   · Parte de PerfilGrafoCivil (ver PerfilGrafoCivil.cs).
// ============================================================================

namespace Civil3DBasico
{
    internal static partial class PerfilGrafoCivil
    {
        /// <summary>Extremo de tubo de presión pendiente de nodo.</summary>
        private sealed class ExtremoP { public TramoRed T; public bool EsA; public Point3d P; public V2 U; public int Acc = -1; public double D3; }

        /// <summary>
        /// C.3-1…5: rellena Nodos (Accesorio/Union/Extremo), Tramos, Verticales, GNodos y GAristas de una PressurePipeNetwork.
        /// Recorre ModelSpace para los accesorios sólidos dentro de la caja de la red + 10 ft. false si no hay tubos válidos.
        /// </summary>
        internal static bool ConstruirPresion(Transaction tr, Database db, RedPerfil red)
        {
            CivilDB.PressurePipeNetwork net;
            try { net = (CivilDB.PressurePipeNetwork)tr.GetObject(red.RedId, OpenMode.ForRead); }
            catch (Exception ex) { PerfilLog.Error("PRESION", "abrir red", ex); return false; }
            double x0 = double.MaxValue, y0 = double.MaxValue, x1 = double.MinValue, y1 = double.MinValue;
            ObjectIdCollection ids;
            try { ids = net.GetPipeIds(); } catch (Exception ex) { PerfilLog.Error("PRESION", "GetPipeIds", ex); return false; }
            foreach (ObjectId pid in ids)
            {
                CivilDB.PressurePipe pp;
                try { pp = (CivilDB.PressurePipe)tr.GetObject(pid, OpenMode.ForRead); } catch { continue; }
                Point3d a, b;
                try { a = pp.StartPoint; b = pp.EndPoint; } catch { continue; }
                x0 = Math.Min(x0, Math.Min(a.X, b.X)); y0 = Math.Min(y0, Math.Min(a.Y, b.Y));
                x1 = Math.Max(x1, Math.Max(a.X, b.X)); y1 = Math.Max(y1, Math.Max(a.Y, b.Y));
                if (Dist2D(a, b) < PerfilRecorrido.LARGO_MIN_TUBO)
                {
                    red.Verticales.Add(new VerticalConexion { X = a.X, Y = a.Y, ZMin = Math.Min(a.Z, b.Z), ZMax = Math.Max(a.Z, b.Z), Red = red.NombreRed, PipeId = pid });
                    continue;
                }
                var t = new TramoRed { Id = red.Tramos.Count, PipeId = pid, EsPresion = true, PIni = a, PFin = b, NombreRed = red.NombreRed };
                double nom = 0, outer = 0;
                try { nom = pp.NominalDiameter; } catch { }
                try { outer = pp.OuterDiameter; } catch { }
                t.DiamIn = nom * 12.0;
                t.AltoExtFt = outer > 0 ? outer : nom;
                t.RadioIntFt = nom / 2.0;
                try { t.MaterialOriginal = pp.Description; } catch { }
                if (string.IsNullOrWhiteSpace(t.MaterialOriginal)) try { t.MaterialOriginal = pp.PartDescription; } catch { }
                t.Material = PerfilTextos.AbreviarMaterial(t.MaterialOriginal);
                try { t.Abandonado = string.Equals(pp.StyleName, "Abandonado (PDFCAD)", StringComparison.OrdinalIgnoreCase); } catch { }
                try { t.Longitud2D = pp.Length2DCenterToCenter; } catch { t.Longitud2D = Dist2D(a, b); }
                t.Bulge = BulgePresion(pp, a, b, pid);
                t.Curva = t.Bulge != 0;
                red.Tramos.Add(t);
            }
            if (red.Tramos.Count == 0) return false;
            var solidos = new Dictionary<int, ObjectId>();
            var xdatas = new Dictionary<int, Dictionary<string, string>>();
            var cands = LeerAccesorios(tr, db, x0 - 10, y0 - 10, x1 + 10, y1 + 10, solidos, xdatas);
            PerfilLog.Log("PRESION", $"{red.Tramos.Count} tubos, {red.Verticales.Count} verticales, {cands.Count} accesorios candidatos");

            // C.3-3: asignación de cada extremo a un accesorio en 3D
            var ext = new List<ExtremoP>();
            foreach (var t in red.Tramos)
            {
                V2 a = V(t.PIni), b = V(t.PFin);
                V2 ua, ub;
                if (t.Bulge != 0 && PerfilRecorrido.Tangentes(a, b, t.Bulge, out V2 t0, out V2 t1)) { ua = t0 * -1.0; ub = t1; }
                else { (a - b).TryUnit(out ua); (b - a).TryUnit(out ub); }
                ext.Add(new ExtremoP { T = t, EsA = true, P = t.PIni, U = ua });
                ext.Add(new ExtremoP { T = t, EsA = false, P = t.PFin, U = ub });
            }
            foreach (var e in ext)
            {
                e.Acc = PerfilRecorrido.ElegirAccesorio(e.P.X, e.P.Y, e.P.Z, e.U, e.T.DiamIn / 12.0, cands, red.NombreRed);
                if (e.Acc < 0) continue;
                var c = cands.First(k => k.Id == e.Acc);
                double d2 = Math.Sqrt((c.X - e.P.X) * (c.X - e.P.X) + (c.Y - e.P.Y) * (c.Y - e.P.Y));
                double dz = double.IsNaN(c.Z) ? 0 : Math.Abs(c.Z - e.P.Z);
                e.D3 = Math.Sqrt(d2 * d2 + dz * dz);
                if (!string.Equals((c.Red ?? "").Trim(), red.NombreRed.Trim(), StringComparison.OrdinalIgnoreCase))
                    PerfilLog.Log("PRESION", $"accesorio de otra red: {(solidos.TryGetValue(c.Id, out var sid) ? sid.Handle.ToString() : "?")} RED={c.Red}");
            }
            foreach (var g in ext.GroupBy(e => e.T))                 // los dos extremos de un tubo no van al mismo accesorio
            {
                var l = g.ToList();
                if (l.Count == 2 && l[0].Acc >= 0 && l[0].Acc == l[1].Acc) (l[0].D3 >= l[1].D3 ? l[0] : l[1]).Acc = -1;
            }
            // C.3-5: nodos de accesorio con tubos asignados
            var nodoDeAcc = new Dictionary<int, int>();
            foreach (int accId in ext.Where(e => e.Acc >= 0).Select(e => e.Acc).Distinct().OrderBy(i => i))
            {
                var c = cands.First(k => k.Id == accId);
                var d = xdatas.TryGetValue(accId, out var dd) ? dd : new Dictionary<string, string>();
                var n = new NodoPerfil
                {
                    Id = red.Nodos.Count, Tipo = TipoNodo.Accesorio, X = c.X, Y = c.Y, ZEje = c.Z,
                    SolidoId = solidos.TryGetValue(accId, out var sid) ? sid : ObjectId.Null,
                    Accesorio = TipoAcc(PerfilTextos.Txt(d, "TIPO")), AnguloXData = PerfilTextos.Num(d, "ANGULO"),
                    DiamPrincipalIn = PerfilTextos.Num(d, "DIAM_PRINCIPAL_IN"), DiamRamalIn = PerfilTextos.Num(d, "DIAM_RAMAL_IN"),
                    MaterialXData = PerfilTextos.Txt(d, "MATERIAL"), RedXData = PerfilTextos.Txt(d, "RED"),
                    LargoTotalFt = PerfilTextos.Num(d, "LARGO_TOTAL_FT"),
                };
                red.Nodos.Add(n); nodoDeAcc[accId] = n.Id;
            }
            // C.3-4: extremos sin accesorio → uniones / extremos libres (≤ 0.5 ft en planta y |Δz| ≤ 0.5)
            foreach (var e in ext)
            {
                int nodo;
                if (e.Acc >= 0) nodo = nodoDeAcc[e.Acc];
                else
                {
                    var n = red.Nodos.FirstOrDefault(k => k.Tipo != TipoNodo.Accesorio
                        && Math.Sqrt((k.X - e.P.X) * (k.X - e.P.X) + (k.Y - e.P.Y) * (k.Y - e.P.Y)) <= 0.5
                        && Math.Abs((double.IsNaN(k.ZEje) ? e.P.Z : k.ZEje) - e.P.Z) <= 0.5);
                    if (n == null)
                    {
                        n = new NodoPerfil { Id = red.Nodos.Count, Tipo = TipoNodo.Extremo, X = e.P.X, Y = e.P.Y, ZEje = e.P.Z };
                        red.Nodos.Add(n);
                    }
                    nodo = n.Id;
                }
                if (e.EsA) e.T.NodoA = nodo; else e.T.NodoB = nodo;
                red.Nodos[nodo].Tramos.Add(e.T.Id);
            }
            foreach (var n in red.Nodos)
            {
                if (n.Tipo == TipoNodo.Extremo && n.Tramos.Count >= 2) n.Tipo = TipoNodo.Union;
                if (n.Tipo != TipoNodo.Accesorio) n.ZEje = double.NaN;      // B.1: solo el accesorio lleva ZEje
            }
            int huecos = red.Nodos.Count(n => n.Tipo == TipoNodo.Accesorio);
            if (huecos > 0) PerfilLog.Log("PRESION", "huecos: " + huecos);
            ArmarGrafoPuro(red);
            return red.GAristas.Any(g => g.Valida);
        }

        private static TipoAccesorio TipoAcc(string tipo)
        {
            switch ((tipo ?? "").Trim().ToUpperInvariant())
            {
                case "ELBOW": return TipoAccesorio.Codo;
                case "TEE": return TipoAccesorio.Tee;
                case "WYE": return TipoAccesorio.Wye;
                case "CROSS": return TipoAccesorio.Cruz;
                default: return TipoAccesorio.Ninguno;
            }
        }

        /// <summary>C.3-2: bulge del tubo de presión verificado con el punto medio real (−b con log; si no, cuerda con aviso).</summary>
        private static double BulgePresion(CivilDB.PressurePipe pp, Point3d a, Point3d b, ObjectId pid)
        {
            try
            {
                if (!pp.IsCurve) return 0;
                double bb = pp.Bulge;
                if (bb == 0) return 0;
                Point3d pm = pp.GetPointAtParameter((pp.StartParam + pp.EndParam) / 2.0);
                V2 p0 = V(a), p1 = V(b), vm = V(pm);
                if ((PerfilRecorrido.PuntoMedioArco(p0, p1, bb) - vm).Largo <= PerfilRecorrido.TOL_ARCO_VERIFICADO) return bb;
                if ((PerfilRecorrido.PuntoMedioArco(p0, p1, -bb) - vm).Largo <= PerfilRecorrido.TOL_ARCO_VERIFICADO)
                { PerfilLog.Log("GRAFO", "bulge de presión invertido " + pid.Handle); return -bb; }
                PerfilLog.Aviso("GRAFO", "Curva de presión no verificada en " + pid.Handle + ": se usa la cuerda");
                return 0;
            }
            catch (Exception ex) { PerfilLog.Log("GRAFO", "bulge de presión " + pid.Handle + ": " + ex.Message + " → cuerda"); return 0; }
        }

        /// <summary>
        /// C.3-6: marca RamalVertical/SentidoVertical ("UP"/"DOWN"/"") en cada nodo accesorio con una VerticalConexion
        /// de CUALQUIER red de presión a ≤ Ralc en planta. Se llama tras PerfilCruces.BuscarCandidatos.
        /// </summary>
        internal static void MarcarRamalesVerticales(RedPerfil red, IReadOnlyList<VerticalConexion> todas)
        {
            if (red == null || todas == null) return;
            foreach (var n in red.Nodos.Where(k => k.Tipo == TipoNodo.Accesorio))
            {
                double dm = double.IsNaN(n.DiamPrincipalIn) ? n.Tramos.Select(i => red.Tramos[i].DiamIn).DefaultIfEmpty(12).Max() / 12.0 : n.DiamPrincipalIn / 12.0;
                double ralc = 1.5 * dm + 0.75;
                if (!double.IsNaN(n.LargoTotalFt)) ralc = Math.Max(ralc, n.LargoTotalFt / 2.0 + 0.5);
                var v = todas.Where(k => Math.Sqrt((k.X - n.X) * (k.X - n.X) + (k.Y - n.Y) * (k.Y - n.Y)) <= ralc)
                             .OrderBy(k => Math.Sqrt((k.X - n.X) * (k.X - n.X) + (k.Y - n.Y) * (k.Y - n.Y))).FirstOrDefault();
                if (v == null) continue;
                n.RamalVertical = true;
                double z = double.IsNaN(n.ZEje) ? (v.ZMin + v.ZMax) / 2.0 : n.ZEje;
                n.SentidoVertical = v.ZMax > z + 0.5 ? "UP" : (v.ZMin < z - 0.5 ? "DOWN" : "");
                PerfilLog.Log("PRESION", $"ramal vertical en nodo {n.Id} ({n.SentidoVertical})");
            }
        }

        /// <summary>C.3-1: candidatos a accesorio (XDATA con COORD_X/COORD_Y) dentro de la caja [min, max] en planta (ft).</summary>
        internal static List<CandidatoAccesorio> LeerAccesorios(Transaction tr, Database db, double xMin, double yMin, double xMax, double yMax,
                                                                 Dictionary<int, ObjectId> solidoDeCandidato,
                                                                 Dictionary<int, Dictionary<string, string>> xdataDeCandidato)
        {
            var r = new List<CandidatoAccesorio>();
            try
            {
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                foreach (ObjectId id in ms)
                {
                    try
                    {
                        if (id.ObjectClass.DxfName != "3DSOLID") continue;
                        var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                        var lista = ent == null ? null : WyeSolido.LeerXData(ent);
                        if (lista == null) continue;
                        var d = PerfilTextos.ParsearXData(lista);
                        double x = PerfilTextos.Num(d, "COORD_X"), y = PerfilTextos.Num(d, "COORD_Y");
                        if (double.IsNaN(x) || double.IsNaN(y) || x < xMin || x > xMax || y < yMin || y > yMax) continue;
                        var c = new CandidatoAccesorio
                        {
                            Id = r.Count, X = x, Y = y, Z = PerfilTextos.Num(d, "COTA_EJE_FT"),
                            DiamPrincipalFt = PerfilTextos.Num(d, "DIAM_PRINCIPAL_IN") / 12.0,
                            LargoTotalFt = PerfilTextos.Num(d, "LARGO_TOTAL_FT"), Red = PerfilTextos.Txt(d, "RED"),
                        };
                        if (double.IsNaN(c.Z)) PerfilLog.Log("PRESION", "accesorio sin COTA_EJE_FT " + id.Handle);
                        r.Add(c);
                        if (solidoDeCandidato != null) solidoDeCandidato[c.Id] = id;
                        if (xdataDeCandidato != null) xdataDeCandidato[c.Id] = d;
                    }
                    catch { }
                }
            }
            catch (Exception ex) { PerfilLog.Error("PRESION", "LeerAccesorios", ex); }
            return r;
        }
    }
}
