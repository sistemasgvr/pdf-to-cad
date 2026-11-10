using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  GRAFO DE LA RED DESDE CIVIL 3D — parte común y gravedad/conduit
//  (DISENO.md C.1, C.2, C.4 «sentido» y «ramales»)
//   · Identifica la red de la entidad elegida, su tipo y su superficie.
//   · Lee Network → nodos/tramos/verticales + grafo puro (GNodo/GArista),
//     excluyendo tubos degenerados y verificando el bulge de las curvas.
//   · Arma el Recorrido (pasos, sentido de estaciones, ramales, traza del eje,
//     estaciones preliminares) usando el núcleo puro PerfilRecorrido.
//   · La parte de presión está en PerfilGrafoPresion.cs (misma clase).
//   · Todo acceso frágil a Civil va en su propio try (G.15).
// ============================================================================

namespace Civil3DBasico
{
    internal static partial class PerfilGrafoCivil
    {
        private static double Dist2D(Point3d a, Point3d b) { return Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y)); }
        private static V2 V(Point3d p) { return new V2(p.X, p.Y); }

        /// <summary>Tubo VERTICAL (conexión cruzada): menos de LARGO_MIN_TUBO en planta Y sube más de lo que avanza.
        /// Antes bastaba lo primero y las curvas cortas de un conducto (≈0.6 ft, radio automático) salían del grafo:
        /// la red quedaba en trozos y el perfil se cortaba («ELE-P1», 2026-11-08).</summary>
        internal static bool EsVertical(Point3d a, Point3d b)
        {
            double d = Dist2D(a, b);
            return d < PerfilRecorrido.LARGO_MIN_TUBO && Math.Abs(b.Z - a.Z) >= d;
        }

        /// <summary>
        /// C.1: red de la entidad (Pipe/Structure/PressurePipe), TipoRed (Gravedad/Conduit/Presion), NombreRed y SuperficieId.
        /// null + <paramref name="mensaje"/> (español, con ✗/⚠) si no hay red o si la tubería elegida es vertical (&lt; LARGO_MIN_TUBO).
        /// </summary>
        internal static RedPerfil IdentificarRed(Transaction tr, CivilDocument civDoc, ObjectId entidadId, out string mensaje)
        {
            mensaje = "";
            const string VERTICAL = "⚠ La tubería seleccionada es vertical (conexión cruzada); seleccione una tubería horizontal.";
            try
            {
                var obj = tr.GetObject(entidadId, OpenMode.ForRead);
                var red = new RedPerfil();
                ObjectId netId = ObjectId.Null;
                if (obj is CivilDB.Pipe p)
                {
                    if (EsVertical(p.StartPoint, p.EndPoint)) { mensaje = VERTICAL; return null; }
                    netId = p.NetworkId;
                }
                else if (obj is CivilDB.Structure st) netId = st.NetworkId;
                else if (obj is CivilDB.PressurePipe pp)
                {
                    if (EsVertical(pp.StartPoint, pp.EndPoint)) { mensaje = VERTICAL; return null; }
                    netId = pp.NetworkId; red.Tipo = TipoRed.Presion;
                }
                if (netId.IsNull || !netId.IsValid) { mensaje = "✗ La entidad no pertenece a ninguna red."; return null; }
                red.RedId = netId;
                var netObj = tr.GetObject(netId, OpenMode.ForRead);
                ObjectId surf = ObjectId.Null;
                if (netObj is CivilDB.PressurePipeNetwork pnet)
                {
                    red.Tipo = TipoRed.Presion;
                    try { red.NombreRed = pnet.Name; } catch { }
                    try { surf = pnet.ReferenceSurfaceId; } catch { }
                }
                else if (netObj is CivilDB.Network net)
                {
                    try { red.NombreRed = net.Name; } catch { }
                    try { surf = net.ReferenceSurfaceId; } catch { }
                    int total = 0, nulas = 0;
                    try
                    {
                        foreach (ObjectId sid in net.GetStructureIds())
                        {
                            total++;
                            try { if (EsEstructuraNula((CivilDB.Structure)tr.GetObject(sid, OpenMode.ForRead))) nulas++; } catch { }
                        }
                    }
                    catch { }
                    red.Tipo = total == 0 || nulas == total ? TipoRed.Conduit : TipoRed.Gravedad;
                }
                else { mensaje = "✗ La entidad no pertenece a una red de tuberías."; return null; }
                red.SuperficieId = EsTin(tr, surf) ? surf : PrimeraTin(tr, civDoc);
                PerfilLog.Log("GRAFO", $"red '{red.NombreRed}' tipo {red.Tipo} superficie {(red.SuperficieId.IsNull ? "(ninguna)" : red.SuperficieId.Handle.ToString())}");
                return red;
            }
            catch (Exception ex)
            {
                PerfilLog.Error("GRAFO", "IdentificarRed", ex);
                mensaje = "✗ No se pudo leer la red: " + ex.Message;
                return null;
            }
        }

        private static bool EsTin(Transaction tr, ObjectId id)
        {
            if (id.IsNull || !id.IsValid || id.IsErased) return false;
            try { return tr.GetObject(id, OpenMode.ForRead) is CivilDB.TinSurface; } catch { return false; }
        }

        private static ObjectId PrimeraTin(Transaction tr, CivilDocument civDoc)
        {
            try { foreach (ObjectId id in civDoc.GetSurfaceIds()) if (EsTin(tr, id)) return id; } catch { }
            return ObjectId.Null;
        }

        /// <summary>
        /// C.2: rellena Nodos, Tramos, Verticales, GNodos y GAristas de una red de gravedad o conduit (Network).
        /// Tubos degenerados → Verticales; bulge verificado con el punto medio real. false si la red no tiene tubos válidos.
        /// </summary>
        internal static bool ConstruirGravedad(Transaction tr, RedPerfil red)
        {
            CivilDB.Network net;
            try { net = (CivilDB.Network)tr.GetObject(red.RedId, OpenMode.ForRead); }
            catch (Exception ex) { PerfilLog.Error("GRAFO", "abrir red", ex); return false; }
            var porEstructura = new Dictionary<ObjectId, int>();
            ObjectIdCollection pipes;
            try { pipes = net.GetPipeIds(); } catch (Exception ex) { PerfilLog.Error("GRAFO", "GetPipeIds", ex); return false; }
            foreach (ObjectId pid in pipes)
            {
                CivilDB.Pipe p;
                try { p = (CivilDB.Pipe)tr.GetObject(pid, OpenMode.ForRead); }
                catch (Exception ex) { PerfilLog.Aviso("GRAFO", "Tubo ilegible " + pid.Handle + ": " + ex.Message); continue; }
                Point3d a, b;
                try { a = p.StartPoint; b = p.EndPoint; } catch { continue; }
                if (EsVertical(a, b))
                {
                    PerfilLog.Log("GRAFO", "tubo degenerado excluido " + pid.Handle);
                    red.Verticales.Add(new VerticalConexion { X = a.X, Y = a.Y, ZMin = Math.Min(a.Z, b.Z), ZMax = Math.Max(a.Z, b.Z), Red = red.NombreRed, PipeId = pid });
                    continue;
                }
                var t = new TramoRed { Id = red.Tramos.Count, PipeId = pid, EsPresion = false, PIni = a, PFin = b, NombreRed = red.NombreRed };
                double inner = 0, innerH = 0, outerH = 0, outerD = 0;
                try { inner = p.InnerDiameterOrWidth; } catch { }
                try { innerH = p.InnerHeight; } catch { }
                try { outerH = p.OuterHeight; } catch { }
                try { outerD = p.OuterDiameterOrWidth; } catch { }
                t.DiamIn = inner * 12.0;
                t.AltoExtFt = outerH > 0 ? outerH : (outerD > 0 ? outerD : t.DiamIn / 12.0);
                t.RadioIntFt = innerH > 0 ? innerH / 2.0 : inner / 2.0;
                try { t.MaterialOriginal = p.Description; } catch { }
                if (string.IsNullOrWhiteSpace(t.MaterialOriginal)) try { t.MaterialOriginal = p.PartDescription; } catch { }
                t.Material = PerfilTextos.AbreviarMaterial(t.MaterialOriginal);
                try { t.Abandonado = string.Equals(p.StyleName, "Abandonado (PDFCAD)", StringComparison.OrdinalIgnoreCase); } catch { }
                try { t.Longitud2D = p.Length2DCenterToCenter; } catch { try { t.Longitud2D = p.Length2D; } catch { t.Longitud2D = Dist2D(a, b); } }
                t.Bulge = BulgeGravedad(p, a, b, pid);
                t.Curva = t.Bulge != 0;
                t.NodoA = NodoExtremo(tr, red, porEstructura, SafeId(() => p.StartStructureId), a);
                t.NodoB = NodoExtremo(tr, red, porEstructura, SafeId(() => p.EndStructureId), b);
                red.Tramos.Add(t);
                red.Nodos[t.NodoA].Tramos.Add(t.Id); red.Nodos[t.NodoB].Tramos.Add(t.Id);
                PerfilLog.Log("GRAFO", $"  tubo {pid.Handle}{(t.Curva ? " (curvo)" : "")}: ({a.X:0.##},{a.Y:0.##}) nodo {t.NodoA}" +
                                       $" → ({b.X:0.##},{b.Y:0.##}) nodo {t.NodoB}");
            }
            foreach (var n in red.Nodos)
                if (n.Tipo == TipoNodo.Extremo && n.Tramos.Count >= 2) n.Tipo = TipoNodo.Union;
            PerfilLog.Log("GRAFO", $"red '{red.NombreRed}': {red.Tramos.Count} tubos ({red.Tramos.Count(x => x.Curva)} curvos), " +
                                   $"{red.Nodos.Count} nodos, {red.Nodos.Count(x => x.Tramos.Count == 1)} puntas sueltas");
            ArmarGrafoPuro(red);
            return red.GAristas.Any(e => e.Valida);
        }

        private static ObjectId SafeId(Func<ObjectId> f) { try { return f(); } catch { return ObjectId.Null; } }

        /// <summary>Nodo del extremo: el de su estructura (clave por id) o un extremo libre agrupado a ≤ TOL_COINCIDE.</summary>
        private static int NodoExtremo(Transaction tr, RedPerfil red, Dictionary<ObjectId, int> porEstructura, ObjectId sid, Point3d p)
        {
            if (!sid.IsNull && sid.IsValid)
            {
                if (porEstructura.TryGetValue(sid, out int ex)) return ex;
                // otra estructura (o punta suelta) en el MISMO punto = la misma unión: en los conductos cada tubo
                // puede llevar su propia estructura en la punta y el recorrido se cortaba ahí («ELE-P1»)
                foreach (var o in red.Nodos)
                        if (Math.Sqrt((o.X - p.X) * (o.X - p.X) + (o.Y - p.Y) * (o.Y - p.Y)) <= PerfilRecorrido.TOL_COINCIDE)
                        { porEstructura[sid] = o.Id; return o.Id; }
                var n = new NodoPerfil { Id = red.Nodos.Count, Tipo = TipoNodo.Estructura, X = p.X, Y = p.Y, EstructuraId = sid };
                try
                {
                    var st = (CivilDB.Structure)tr.GetObject(sid, OpenMode.ForRead);
                    try { var l = st.Location; n.X = l.X; n.Y = l.Y; } catch { }
                    try { n.Nombre = st.Name; } catch { }
                    try { n.Rim = st.RimElevation; } catch { }
                    try { n.Sump = st.SumpElevation; } catch { }
                    if (EsEstructuraNula(st)) n.Tipo = TipoNodo.EstructuraNula;
                }
                catch (Exception e) { PerfilLog.Log("GRAFO", "estructura ilegible " + sid.Handle + ": " + e.Message); }
                red.Nodos.Add(n); porEstructura[sid] = n.Id;
                return n.Id;
            }
            // punta SIN estructura (el tubo curvo de un conducto se une al recto sin pieza): la misma unión que la
            // estructura NULA del tubo vecino en ese punto (si no, el recorrido se cortaba en la curva: «ELE-P1»)
            foreach (var n in red.Nodos)
                if ((n.EstructuraId.IsNull || n.Tipo == TipoNodo.EstructuraNula) && Math.Sqrt((n.X - p.X) * (n.X - p.X) + (n.Y - p.Y) * (n.Y - p.Y)) <= PerfilRecorrido.TOL_COINCIDE) return n.Id;
            var nuevo = new NodoPerfil { Id = red.Nodos.Count, Tipo = TipoNodo.Extremo, X = p.X, Y = p.Y };
            red.Nodos.Add(nuevo);
            return nuevo.Id;
        }

        /// <summary>C.2-3: bulge verificado de un tubo de gravedad (cuerda si no es un arco comprobado).</summary>
        private static double BulgeGravedad(CivilDB.Pipe p, Point3d a, Point3d b, ObjectId pid)
        {
            try
            {
                var tipo = p.SubEntityType;
                if (tipo == CivilDB.PipeSubEntityType.Straight) return 0;
                if (tipo != CivilDB.PipeSubEntityType.Curved) { PerfilLog.Log("GRAFO", $"tubo {tipo}: se usa la cuerda ({pid.Handle})"); return 0; }
                var arc = p.Curve2d;
                var iv = arc.GetInterval();
                Point2d pm = arc.EvaluatePoint((iv.LowerBound + iv.UpperBound) / 2.0);
                double barrido = arc.GetLength(iv.LowerBound, iv.UpperBound) / arc.Radius;
                double bb = Math.Tan(barrido / 4.0);
                V2 p0 = V(a), p1 = V(b), vm = new V2(pm.X, pm.Y);
                double signo = Math.Sign((vm - p0).Cross(p1 - vm));
                bb *= signo == 0 ? 1 : signo;
                var chk = PerfilRecorrido.PuntoMedioArco(p0, p1, bb);
                if ((chk - vm).Largo <= PerfilRecorrido.TOL_ARCO_VERIFICADO) return bb;
                var chk2 = PerfilRecorrido.PuntoMedioArco(p0, p1, -bb);
                if ((chk2 - vm).Largo <= PerfilRecorrido.TOL_ARCO_VERIFICADO) { PerfilLog.Log("GRAFO", "bulge invertido " + pid.Handle); return -bb; }
                PerfilLog.Aviso("GRAFO", "Curva no verificada en " + pid.Handle + ": se usa la cuerda");
                return 0;
            }
            catch (Exception ex) { PerfilLog.Log("GRAFO", "bulge de " + pid.Handle + ": " + ex.Message + " → cuerda"); return 0; }
        }

        /// <summary>GNodos/GAristas desde Nodos/Tramos (bulge solo si los extremos coinciden con sus nodos a ≤ 0.5 ft).</summary>
        internal static void ArmarGrafoPuro(RedPerfil red)
        {
            red.GNodos = red.Nodos.Select(n => new GNodo { Id = n.Id, X = n.X, Y = n.Y }).ToList();
            red.GAristas = new List<GArista>();
            foreach (var t in red.Tramos)
            {
                var na = red.GNodos[t.NodoA]; var nb = red.GNodos[t.NodoB];
                bool pegados = Math.Sqrt((t.PIni.X - na.X) * (t.PIni.X - na.X) + (t.PIni.Y - na.Y) * (t.PIni.Y - na.Y)) <= 0.5
                            && Math.Sqrt((t.PFin.X - nb.X) * (t.PFin.X - nb.X) + (t.PFin.Y - nb.Y) * (t.PFin.Y - nb.Y)) <= 0.5;
                var e = new GArista { Id = t.Id, A = t.NodoA, B = t.NodoB, Bulge = pegados ? t.Bulge : 0 };
                PerfilRecorrido.CompletarArista(e, na, nb);
                red.GAristas.Add(e);
                na.Aristas.Add(e.Id); if (nb.Id != na.Id) nb.Aristas.Add(e.Id);
            }
        }

        /// <summary>
        /// C.4 + C.5 + D.3 (T0): recorrido desde la entidad elegida (tubo → Recorrer; estructura → RecorrerDesdeNodo),
        /// sentido de estaciones (gravedad: menor invert; resto: oeste/sur), Pasos, Ramales, Traza sin prolongar (el eje = la tubería),
        /// DistN0, estaciones PRELIMINARES (EstNodo, EstP*, Z*) y EstMin/MaxPermitida. null + mensaje si queda sin tubos.
        /// </summary>
        /// <summary>Inicio/fin del perfil que mandó la app (`PDFCAD_PERFIL` INI/FIN). null = recorrido completo
        /// (CREAR_PERFIL_RED interactivo). Lo pone y lo quita `ComandosPerfil.CrearAutomatico`.</summary>
        internal static Point2d? LimiteIni, LimiteFin;
        private const double LIMITE_TOL_FT = 2.0;

        /// <summary>Solo los pasos entre el tramo más cercano a LimiteIni y el más cercano a LimiteFin (los dos
        /// incluidos). Sin límites, o si alguno no cae sobre el recorrido (≤ LIMITE_TOL_FT), sin cambios.</summary>
        private static List<PasoG> RecortarALimites(RedPerfil red, List<PasoG> pasos)
        {
            if (LimiteIni == null || LimiteFin == null || pasos.Count < 2) return pasos;
            int Cercano(Point2d p)
            {
                int mejor = -1; double dmin = LIMITE_TOL_FT;
                for (int i = 0; i < pasos.Count; i++)
                {
                    var t = red.Tramos[pasos[i].Arista];
                    double ax = t.PIni.X, ay = t.PIni.Y, dx = t.PFin.X - ax, dy = t.PFin.Y - ay;
                    double l2 = dx * dx + dy * dy;
                    double u = l2 <= 1e-12 ? 0 : Math.Max(0, Math.Min(1, ((p.X - ax) * dx + (p.Y - ay) * dy) / l2));
                    double d = Math.Sqrt(Math.Pow(ax + dx * u - p.X, 2) + Math.Pow(ay + dy * u - p.Y, 2));
                    if (d <= dmin) { dmin = d; mejor = i; }
                }
                return mejor;
            }
            int a = Cercano(LimiteIni.Value), b = Cercano(LimiteFin.Value);
            if (a < 0 || b < 0) { PerfilLog.Aviso("GRAFO", "Límites de la app fuera del recorrido: se usa completo"); return pasos; }
            int i0 = Math.Min(a, b), i1 = Math.Max(a, b);
            PerfilLog.Log("GRAFO", $"límites de la app: pasos {i0}..{i1} de {pasos.Count}");
            return pasos.GetRange(i0, i1 - i0 + 1);
        }

        /// <summary>Con inicio A y fin B de la app: el camino más corto por la red del tramo de A al de B, como hace la app
        /// (`perfil_recorrido.entre`). null sin límites o si no hay camino (entonces se recorta el recorrido automático).</summary>
        private static List<PasoG> CaminoEntreLimites(RedPerfil red)
        {
            if (LimiteIni == null || LimiteFin == null) return null;
            var tramos = red.Tramos.Select(t => (t.PIni.X, t.PIni.Y, t.PFin.X, t.PFin.Y, red.GAristas[t.Id].Valida)).ToList();
            int eA = PerfilRecorridoEntre.MasCercana(tramos, LimiteIni.Value.X, LimiteIni.Value.Y, LIMITE_TOL_FT);
            int eB = PerfilRecorridoEntre.MasCercana(tramos, LimiteFin.Value.X, LimiteFin.Value.Y, LIMITE_TOL_FT);
            if (eA < 0 || eB < 0) { PerfilLog.Aviso("GRAFO", $"Inicio o fin de la app a más de {LIMITE_TOL_FT} ft de un tubo de la red: se usa el recorrido automático"); return null; }
            var p = PerfilRecorridoEntre.Entre(red.GNodos, red.GAristas, eA, eB);
            if (p.Count == 0) { PerfilLog.Aviso("GRAFO", "El inicio y el fin de la app no están unidos en la red de Civil 3D: se usa el recorrido automático"); return null; }
            PerfilLog.Log("GRAFO", $"camino de A a B (como la app): {p.Count} tubo(s), del {red.Tramos[eA].PipeId.Handle} al {red.Tramos[eB].PipeId.Handle}");
            return p;
        }

        internal static Recorrido ArmarRecorrido(RedPerfil red, ObjectId entidadId, double s, out string mensaje)
        {
            mensaje = "";
            List<PasoG> pasos;
            int it = TramoDePipe(red, entidadId);
            if (it >= 0) pasos = PerfilRecorrido.Recorrer(red.GNodos, red.GAristas, it);
            else
            {
                int nd = NodoDeEstructura(red, entidadId);
                if (nd < 0) { mensaje = "✗ La entidad elegida no está en el grafo de la red."; return null; }
                if (red.GNodos[nd].Aristas.Count == 0) { mensaje = "✗ La estructura no tiene tuberías."; return null; }
                pasos = PerfilRecorrido.RecorrerDesdeNodo(red.GNodos, red.GAristas, nd);
            }
            if (pasos == null || pasos.Count == 0) { mensaje = "✗ No se pudo formar un recorrido desde esa entidad."; return null; }
            var entreAB = CaminoEntreLimites(red);
            pasos = entreAB ?? RecortarALimites(red, pasos);
            var rec = new Recorrido { Red = red };
            Func<PasoG, int> desde = p => p.Invertida ? red.GAristas[p.Arista].B : red.GAristas[p.Arista].A;
            Func<PasoG, int> hasta = p => p.Invertida ? red.GAristas[p.Arista].A : red.GAristas[p.Arista].B;
            bool invertir;
            var t0 = red.Tramos[pasos[0].Arista]; var tk = red.Tramos[pasos[pasos.Count - 1].Arista];
            if (red.Tipo == TipoRed.Gravedad)
            {
                double inv0 = (pasos[0].Invertida ? t0.PFin.Z : t0.PIni.Z) - t0.RadioIntFt;
                double invK = (pasos[pasos.Count - 1].Invertida ? tk.PIni.Z : tk.PFin.Z) - tk.RadioIntFt;
                invertir = inv0 > invK + 1e-9;
            }
            else
            {
                var n0 = red.GNodos[desde(pasos[0])]; var nk = red.GNodos[hasta(pasos[pasos.Count - 1])];
                invertir = PerfilRecorrido.DebeInvertirOesteSur(n0.X, n0.Y, nk.X, nk.Y);
            }
            // Perfil elegido en la app con inicio A y fin B (2026-11-06): las estaciones empiezan en A (LimiteIni),
            // aunque la regla automática (solera más baja / oeste-sur) diga lo contrario.
            if (LimiteIni != null && LimiteFin != null && pasos.Count > 0)
            {
                double DistA(TramoRed t)
                {
                    var p = LimiteIni.Value;
                    double ax = t.PIni.X, ay = t.PIni.Y, dx = t.PFin.X - ax, dy = t.PFin.Y - ay, l2 = dx * dx + dy * dy;
                    double u = l2 <= 1e-12 ? 0 : Math.Max(0, Math.Min(1, ((p.X - ax) * dx + (p.Y - ay) * dy) / l2));
                    return Math.Sqrt(Math.Pow(ax + dx * u - p.X, 2) + Math.Pow(ay + dy * u - p.Y, 2));
                }
                if (pasos.Count > 1) invertir = DistA(tk) < DistA(t0);
                else
                {
                    // A y B en el MISMO tubo: de A hacia B a lo largo del tubo (antes quedaba la regla oeste/sur y el
                    // perfil podía salir al revés que en la app). A y B son los clics sobre el tubo, no sus puntas.
                    var n0 = red.GNodos[desde(pasos[0])]; var nk = red.GNodos[hasta(pasos[0])];
                    double ux = nk.X - n0.X, uy = nk.Y - n0.Y;
                    double tA = (LimiteIni.Value.X - n0.X) * ux + (LimiteIni.Value.Y - n0.Y) * uy;
                    double tB = (LimiteFin.Value.X - n0.X) * ux + (LimiteFin.Value.Y - n0.Y) * uy;
                    invertir = tA > tB;
                }
            }
            if (invertir)
            {
                pasos.Reverse();
                pasos = pasos.Select(p => new PasoG { Arista = p.Arista, Invertida = !p.Invertida }).ToList();
            }
            rec.Nodos.Add(desde(pasos[0]));
            foreach (var p in pasos)
            {
                var t = red.Tramos[p.Arista];
                rec.Pasos.Add(new PasoRecorrido
                {
                    Tramo = t, Invertido = p.Invertida, NodoDesde = desde(p), NodoHasta = hasta(p),
                    ZIni = p.Invertida ? t.PFin.Z : t.PIni.Z, ZFin = p.Invertida ? t.PIni.Z : t.PFin.Z,
                });
                rec.Nodos.Add(hasta(p));
            }
            // traza del eje (C.5)
            var nodosV = rec.Nodos.Select(i => new V2(red.GNodos[i].X, red.GNodos[i].Y)).ToList();
            var bulges = pasos.Select(p => (p.Invertida ? -1 : 1) * red.GAristas[p.Arista].Bulge).ToList();
            // el eje mide JUSTO lo que la tubería (pedido del usuario 2026-11-09): antes se prolongaba max(25, PAD_MAX·s + 10)
            // ft a cada lado para dar margen a la vista (ELE-P1: eje de 505 ft para 325 ft de tubería, empezando en 0+10).
            // La vista ya se limita al eje (EstMin/MaxPermitida): empieza en 1+00 y termina en el fin de la tubería.
            const double ext = 0.0;
            var logTraza = new List<string>();
            try { rec.Traza = PerfilRecorrido.Traza(nodosV, bulges, ext, logTraza); }
            catch (InvalidOperationException ex) { mensaje = ex.Message; return null; }
            PerfilLog.Volcar("GRAFO", logTraza);
            rec.DistN0 = PerfilRecorrido.DistanciaEnTraza(rec.Traza, nodosV[0]);
            PerfilEje.EstacionesPreliminares(rec);
            ArmarRamales(rec);
            PerfilLog.Log("GRAFO", $"recorrido: {rec.Pasos.Count} tubos, {rec.Nodos.Count} nodos, {rec.EstFin - rec.EstIni:0.00} ft, invertido={invertir}");
            return rec;
        }

        /// <summary>C.4 «Ramales»: aristas válidas fuera del recorrido en cada nodo del recorrido.</summary>
        private static void ArmarRamales(Recorrido rec)
        {
            var red = rec.Red;
            var usadas = new HashSet<int>(rec.Pasos.Select(p => p.Tramo.Id));
            for (int i = 0; i < rec.Nodos.Count; i++)
            {
                int nd = rec.Nodos[i];
                V2 llegada;
                if (i > 0)
                {
                    var e = red.GAristas[rec.Pasos[i - 1].Tramo.Id];
                    llegada = (e.A == nd ? e.DirSalidaA : e.DirSalidaB) * -1.0;
                }
                else
                {
                    var e = red.GAristas[rec.Pasos[0].Tramo.Id];
                    llegada = e.A == nd ? e.DirSalidaA : e.DirSalidaB;
                }
                foreach (int ai in red.GNodos[nd].Aristas)
                {
                    if (usadas.Contains(ai) || !red.GAristas[ai].Valida) continue;
                    var e = red.GAristas[ai]; var t = red.Tramos[ai];
                    V2 dir = e.A == nd ? e.DirSalidaA : e.DirSalidaB;
                    var r = new Ramal
                    {
                        NodoId = nd, Tramo = t, DiamIn = t.DiamIn, Lado = PerfilRecorrido.LadoRamal(llegada, dir),
                        AnguloDeg = PerfilRecorrido.Deflexion(llegada, dir),
                    };
                    if (red.Tipo == TipoRed.Gravedad)
                    {
                        double invNodo = (e.A == nd ? t.PIni.Z : t.PFin.Z) - t.RadioIntFt;
                        double invLejos = (e.A == nd ? t.PFin.Z : t.PIni.Z) - t.RadioIntFt;
                        r.EntraAlNodo = invLejos > invNodo;
                    }
                    if (!rec.Ramales.TryGetValue(nd, out var lst)) rec.Ramales[nd] = lst = new List<Ramal>();
                    lst.Add(r);
                }
            }
        }

        /// <summary>Índice del TramoRed de un PipeId/PressurePipe id; −1 si no está en el grafo (p. ej. degenerado).</summary>
        internal static int TramoDePipe(RedPerfil red, ObjectId pipeId)
        {
            for (int i = 0; i < red.Tramos.Count; i++) if (red.Tramos[i].PipeId == pipeId) return i;
            return -1;
        }

        /// <summary>Índice del NodoPerfil de una estructura; −1 si no está.</summary>
        internal static int NodoDeEstructura(RedPerfil red, ObjectId estructuraId)
        {
            for (int i = 0; i < red.Nodos.Count; i++) if (red.Nodos[i].EstructuraId == estructuraId) return i;
            return -1;
        }

        /// <summary>C.1: estructura nula ⇔ PartFamilyName contiene "null"/"nula" (lectura en try; si falla, no nula).</summary>
        internal static bool EsEstructuraNula(CivilDB.Structure st)
        {
            try
            {
                string f = (st.PartFamilyName ?? "").ToLowerInvariant();
                return f.Contains("null") || f.Contains("nula");
            }
            catch { return false; }
        }

        /// <summary>
        /// Invert (ft) en el extremo A (true) o B (false) de un tramo: gravedad/conduit con ComandosCotarTuberias.InvertEnNodo
        /// (nunca SumpElevation); presión = z eje − RadioIntFt. H.3.
        /// </summary>
        internal static double InvertExtremo(Transaction tr, TramoRed t, bool extremoA)
        {
            Point3d c = extremoA ? t.PIni : t.PFin;
            if (!t.EsPresion)
                try { return ComandosCotarTuberias.InvertEnNodo(ObjectId.Null, c, (CivilDB.Pipe)tr.GetObject(t.PipeId, OpenMode.ForRead), tr); }
                catch { }
            return c.Z - t.RadioIntFt;
        }
    }
}
