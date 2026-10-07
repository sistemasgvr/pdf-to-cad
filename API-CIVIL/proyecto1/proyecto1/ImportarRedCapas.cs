using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  CAPA DE LA UTILIDAD EN LAS PIEZAS DE CADA RED (pedido del usuario 2026-10-05)
//   IMPORTAR_RED arma las redes con las polilíneas del DXF (capas ELECTRICO,
//   TELECOM, AGUA… de la app) y después las borra. Las piezas nuevas quedaban en
//   la capa por defecto de Civil 3D para redes (Configuración del dibujo → Capas
//   de objeto), la misma para todas las utilidades. Al final del import cada pieza
//   de cada red creada (tuberías, buzones/cajas, accesorios) pasa a la capa de la
//   utilidad de la que salió. Si una red junta utilidades de capas distintas (dos
//   tipos con el mismo nombre propio), cada pieza toma la de la polilínea más
//   cercana. Los conductos de un bancoducto salen de polilíneas con capa
//   PDFCAD_DUCT_BANK y quedan con su sólido. Los sólidos no cambian de capa.
// ============================================================================

namespace Civil3DBasico
{
    public partial class ComandosRedes
    {
        /// <summary>Pone cada pieza de las redes creadas en la capa de su utilidad.
        /// `redes` = id de la red → polilíneas (ImportPipe) con las que se creó.</summary>
        private static void AsignarCapasDeUtilidad(Editor ed, Database db,
            Dictionary<ObjectId, List<ImportPipe>> redes)
        {
            if (redes == null || redes.Count == 0) return;
            int nCambiadas = 0, nFallos = 0;
            var porCapa = new SortedDictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    var capasListas = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (var kv in redes)
                    {
                        if (kv.Key.IsNull || kv.Key.IsErased) continue;
                        var fuentes = (kv.Value ?? new List<ImportPipe>())
                            .Where(p => p != null && !string.IsNullOrWhiteSpace(p.Layer)).ToList();
                        if (fuentes.Count == 0) continue;
                        bool unaCapa = fuentes.Select(p => p.Layer.Trim())
                                              .Distinct(StringComparer.OrdinalIgnoreCase).Count() == 1;
                        foreach (ObjectId id in PiezasDeRed(tr, kv.Key))
                        {
                            try
                            {
                                var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                                if (ent == null) continue;
                                string capa = unaCapa ? fuentes[0].Layer.Trim()
                                                      : CapaMasCercana(fuentes, PuntoDePieza(ent));
                                if (string.IsNullOrEmpty(capa)
                                    || string.Equals(ent.Layer, capa, StringComparison.OrdinalIgnoreCase)) continue;
                                if (!capasListas.Contains(capa))
                                {
                                    if (!AsegurarCapa(tr, db, capa)) { nFallos++; continue; }
                                    capasListas.Add(capa);
                                }
                                ent.UpgradeOpen();
                                ent.Layer = capa;
                                nCambiadas++;
                                porCapa[capa] = porCapa.TryGetValue(capa, out int c) ? c + 1 : 1;
                            }
                            catch { nFallos++; }          // p.ej. pieza en una capa bloqueada
                        }
                    }
                    tr.Commit();
                }
                catch (Exception ex)
                {
                    tr.Abort();
                    ed.WriteMessage($"\n(No se pudieron poner las piezas en la capa de su utilidad: {ex.Message})");
                    return;
                }
            }
            if (nCambiadas > 0)
                ed.WriteMessage($"\n  · {nCambiadas} pieza(s) en la capa de su utilidad: " +
                                string.Join(", ", porCapa.Select(kv => $"{kv.Key} {kv.Value}")) + ".");
            if (nFallos > 0)
                ed.WriteMessage($"\n  ⚠ {nFallos} pieza(s) no se pudieron pasar a la capa de su utilidad (¿capa bloqueada?).");
        }

        /// <summary>SÓLIDOS creados en este import → capa de su utilidad (pedido del usuario
        /// 2026-10-06): accesorios de presión dibujados como Solid3d (codo, Tee, Wye,
        /// cruz, reducción; capa PDFCAD_WYE_SOLIDO) y sólidos que representan buzones/
        /// cajas (PDFCAD_SOLIDOS). Solo los de handle ≥ `handleInicio` (los de imports
        /// anteriores no se tocan); el bancoducto (PDFCAD_DUCT_BANK) queda como está.
        /// Utilidad: la de la red que el accesorio guarda en su XDATA (RED=) y, dentro de
        /// ella o si no hay, la polilínea de origen más cercana.</summary>
        private static void AsignarCapasDeSolidos(Editor ed, Database db,
            Dictionary<ObjectId, List<ImportPipe>> redes, List<ImportPipe> pipes, long handleInicio)
        {
            // Polilíneas de UTILIDAD (no las auxiliares PDFCAD_*: conductos del bancoducto).
            var todas = (pipes ?? new List<ImportPipe>())
                .Where(p => p != null && !string.IsNullOrWhiteSpace(p.Layer)
                            && !p.Layer.StartsWith("PDFCAD_", StringComparison.OrdinalIgnoreCase)).ToList();
            if (todas.Count == 0) return;
            var capasSolidos = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                { WyeSolido.CAPA, "PDFCAD_SOLIDOS" };
            int nCambiadas = 0, nFallos = 0;
            var porCapa = new SortedDictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Red (nombre) → sus polilíneas de utilidad.
                    var porRed = new Dictionary<string, List<ImportPipe>>(StringComparer.OrdinalIgnoreCase);
                    foreach (var kv in redes ?? new Dictionary<ObjectId, List<ImportPipe>>())
                    {
                        if (kv.Key.IsNull || kv.Key.IsErased) continue;
                        string nom = NombreDeRed(tr, kv.Key);
                        var f = (kv.Value ?? new List<ImportPipe>()).Where(p => todas.Contains(p)).ToList();
                        if (nom.Length > 0 && f.Count > 0) porRed[nom] = f;
                    }
                    var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                    var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
                    var capasListas = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (ObjectId id in ms)
                    {
                        if (id.Handle.Value < handleInicio || id.IsErased) continue;
                        if (!id.ObjectClass.IsDerivedFrom(RXObject.GetClass(typeof(Solid3d)))) continue;
                        try
                        {
                            var sol = (Solid3d)tr.GetObject(id, OpenMode.ForRead);
                            if (!capasSolidos.Contains(sol.Layer)) continue;
                            Point2d? centro = null;
                            try
                            {
                                var ext = sol.GeometricExtents;
                                centro = new Point2d((ext.MinPoint.X + ext.MaxPoint.X) / 2.0,
                                                     (ext.MinPoint.Y + ext.MaxPoint.Y) / 2.0);
                            }
                            catch { }
                            if (centro == null) continue;
                            var candidatas = todas;
                            string red = RedDeXData(sol);
                            if (red.Length > 0 && porRed.TryGetValue(red, out var deRed)) candidatas = deRed;
                            string capa = FuenteMasCercana(candidatas, centro)?.Layer?.Trim();
                            if (string.IsNullOrEmpty(capa)) continue;
                            if (!capasListas.Contains(capa))
                            {
                                if (!AsegurarCapa(tr, db, capa)) { nFallos++; continue; }
                                capasListas.Add(capa);
                            }
                            sol.UpgradeOpen();
                            sol.Layer = capa;
                            nCambiadas++;
                            porCapa[capa] = porCapa.TryGetValue(capa, out int c) ? c + 1 : 1;
                        }
                        catch { nFallos++; }
                    }
                    tr.Commit();
                }
                catch (Exception ex)
                {
                    tr.Abort();
                    ed.WriteMessage($"\n(No se pudieron poner los sólidos en la capa de su utilidad: {ex.Message})");
                    return;
                }
            }
            if (nCambiadas > 0)
                ed.WriteMessage($"\n  · {nCambiadas} sólido(s) (accesorios y buzones) en la capa de su utilidad: " +
                                string.Join(", ", porCapa.Select(kv => $"{kv.Key} {kv.Value}")) + ".");
            if (nFallos > 0)
                ed.WriteMessage($"\n  ⚠ {nFallos} sólido(s) no se pudieron pasar a la capa de su utilidad (¿capa bloqueada?).");
        }

        /// <summary>Tuberías de cada red creada → «RED - (n)» en vez de «Pipe - (n)» (pedido del
        /// usuario 2026-10-06: con muchas redes no se sabía de cuál era cada tubería). Si el
        /// nombre ya existe (o Civil 3D lo rechaza), la tubería conserva el suyo.</summary>
        private static void NombrarTuberiasPorRed(Editor ed, Database db, IEnumerable<ObjectId> netIds)
        {
            int n = 0;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    foreach (ObjectId nid in netIds ?? Enumerable.Empty<ObjectId>())
                    {
                        if (nid.IsNull || nid.IsErased) continue;
                        string red = NombreDeRed(tr, nid);
                        if (string.IsNullOrWhiteSpace(red)) continue;
                        var tubos = new List<ObjectId>();
                        var obj = tr.GetObject(nid, OpenMode.ForRead);
                        if (obj is CivilDB.Network net) foreach (ObjectId id in net.GetPipeIds()) tubos.Add(id);
                        else if (obj is CivilDB.PressurePipeNetwork pn) foreach (ObjectId id in pn.GetPipeIds()) tubos.Add(id);
                        int k = 0;
                        foreach (ObjectId id in tubos)
                        {
                            k++;
                            try
                            {
                                var o = tr.GetObject(id, OpenMode.ForWrite);
                                string nuevo = $"{red} - ({k})";
                                if (o is CivilDB.Pipe gp) { if (gp.Name == nuevo) continue; gp.Name = nuevo; }
                                else if (o is CivilDB.PressurePipe pp) { if (pp.Name == nuevo) continue; pp.Name = nuevo; }
                                else continue;
                                n++;
                            }
                            catch { }                       // nombre repetido o pieza bloqueada: queda el de Civil 3D
                        }
                    }
                    tr.Commit();
                }
                catch (Exception ex)
                {
                    tr.Abort();
                    ed.WriteMessage($"\n(No se pudieron renombrar las tuberías por su red: {ex.Message})");
                    return;
                }
            }
            if (n > 0) ed.WriteMessage($"\n  · {n} tubería(s) nombradas con su red («RED - (n)»).");
        }

        /// <summary>Valor RED= del XDATA del accesorio sólido ("" si no tiene).</summary>
        private static string RedDeXData(Entity ent)
        {
            try
            {
                foreach (string s in WyeSolido.LeerXData(ent) ?? new List<string>())
                    if (s != null && s.StartsWith("RED=", StringComparison.OrdinalIgnoreCase))
                        return s.Substring(4).Trim();
            }
            catch { }
            return "";
        }

        /// <summary>Tuberías y estructuras (gravedad/conduit) o tuberías, accesorios y
        /// apurtenencias (presión) de una red.</summary>
        private static List<ObjectId> PiezasDeRed(Transaction tr, ObjectId netId)
        {
            var salida = new List<ObjectId>();
            DBObject obj;
            try { obj = tr.GetObject(netId, OpenMode.ForRead); }
            catch { return salida; }
            if (obj is CivilDB.Network net)
            {
                foreach (ObjectId id in net.GetPipeIds()) salida.Add(id);
                foreach (ObjectId id in net.GetStructureIds()) salida.Add(id);
            }
            else if (obj is CivilDB.PressurePipeNetwork pn)
            {
                foreach (ObjectId id in pn.GetPipeIds()) salida.Add(id);
                foreach (ObjectId id in pn.GetFittingIds()) salida.Add(id);
                foreach (ObjectId id in pn.GetAppurtenanceIds()) salida.Add(id);
            }
            return salida;
        }

        /// <summary>Punto representativo de la pieza en planta (medio del tubo o su posición).</summary>
        private static Point2d? PuntoDePieza(Entity ent)
        {
            Point2d Medio(Point3d a, Point3d b) => new Point2d((a.X + b.X) / 2.0, (a.Y + b.Y) / 2.0);
            try
            {
                switch (ent)
                {
                    case CivilDB.Pipe p: return Medio(p.StartPoint, p.EndPoint);
                    case CivilDB.PressurePipe pp: return Medio(pp.StartPoint, pp.EndPoint);
                    case CivilDB.Structure s: return new Point2d(s.Position.X, s.Position.Y);
                    case CivilDB.PressurePart pa: return new Point2d(pa.Position.X, pa.Position.Y);
                }
            }
            catch { }
            return null;
        }

        /// <summary>Capa de la polilínea de origen más cercana al punto (sin punto: la
        /// capa más repetida de la red).</summary>
        private static string CapaMasCercana(List<ImportPipe> fuentes, Point2d? punto)
        {
            if (punto == null)
                return fuentes.GroupBy(p => p.Layer.Trim(), StringComparer.OrdinalIgnoreCase)
                              .OrderByDescending(g => g.Count()).First().Key;
            return FuenteMasCercana(fuentes, punto)?.Layer.Trim() ?? fuentes[0].Layer.Trim();
        }

        /// <summary>Polilínea de origen más cercana al punto (sin punto: la primera).</summary>
        private static ImportPipe FuenteMasCercana(List<ImportPipe> fuentes, Point2d? punto)
        {
            if (fuentes == null || fuentes.Count == 0) return null;
            if (punto == null) return fuentes[0];
            Point2d q = punto.Value;
            ImportPipe mejor = fuentes[0];
            double dMin = double.MaxValue;
            foreach (var f in fuentes)
            {
                var v = f.Vertices;
                if (v == null || v.Count == 0) continue;
                for (int k = 0; k < v.Count; k++)
                {
                    Point2d a = v[k], b = v[Math.Min(k + 1, v.Count - 1)];
                    Vector2d d = b - a;
                    double L2 = d.DotProduct(d);
                    double t = L2 < 1e-12 ? 0.0 : Math.Max(0.0, Math.Min(1.0, (q - a).DotProduct(d) / L2));
                    double dist = q.GetDistanceTo(a + d * t);
                    if (dist < dMin) { dMin = dist; mejor = f; }
                }
            }
            return mejor;
        }

        /// <summary>La capa existe (si no, se crea con el color por defecto). False si
        /// el nombre no es válido.</summary>
        private static bool AsegurarCapa(Transaction tr, Database db, string nombre)
        {
            try
            {
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                if (lt.Has(nombre)) return true;
                SymbolUtilityServices.ValidateSymbolName(nombre, false);
                lt.UpgradeOpen();
                var ltr = new LayerTableRecord { Name = nombre };
                lt.Add(ltr);
                tr.AddNewlyCreatedDBObject(ltr, true);
                return true;
            }
            catch { return false; }
        }
    }
}
