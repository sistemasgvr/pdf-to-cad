using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  EL MOÑO Y LA CAJA DE LA VÁLVULA SIGUEN A SU VISTA DE PERFIL (2026-11-08)
//   Son polilíneas sueltas (la vista solo dibuja piezas de red): si el usuario cambiaba
//   el rango de estaciones/cotas o movía la vista, quedaban en su sitio viejo.
//   · Cada polilínea lleva XDATA `PDFCAD_PERFIL_VALV`: handle de su ProfileView, la VE
//     y cada vértice en (estación, cota).
//   · Al terminar un comando que modificó o borró una ProfileView, sus polilíneas se
//     recolocan con FindXY (o se borran si la vista ya no existe). Deshacer/rehacer no
//     dispara nada: ya repone las polilíneas con la vista.
//   · PDFCAD_PERFIL_VALVULAS lo hace a mano en todo el dibujo.
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilValvulasSeguir
    {
        internal const string APP = "PDFCAD_PERFIL_VALV";
        private static readonly HashSet<Database> _activas = new HashSet<Database>();
        private static readonly Dictionary<Database, HashSet<Handle>> _cambiadas = new Dictionary<Database, HashSet<Handle>>();
        private static readonly HashSet<string> SIN_SEGUIR = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            { "U", "UNDO", "REDO", "MREDO", "OOPS" };

        /// <summary>Guarda en la polilínea su vista y sus vértices en (estación, cota).</summary>
        internal static void Etiquetar(Transaction tr, Database db, Polyline pl, ObjectId pvId, double ve, Point2d[] estZ)
        {
            var rat = (RegAppTable)tr.GetObject(db.RegAppTableId, OpenMode.ForRead);
            if (!rat.Has(APP))
            {
                rat.UpgradeOpen();
                var rar = new RegAppTableRecord { Name = APP };
                rat.Add(rar);
                tr.AddNewlyCreatedDBObject(rar, true);
            }
            var vals = new List<TypedValue>
            {
                new TypedValue((int)DxfCode.ExtendedDataRegAppName, APP),
                new TypedValue((int)DxfCode.ExtendedDataHandle, pvId.Handle.ToString()),
                new TypedValue((int)DxfCode.ExtendedDataReal, ve),
            };
            foreach (var p in estZ)
            {
                vals.Add(new TypedValue((int)DxfCode.ExtendedDataReal, p.X));
                vals.Add(new TypedValue((int)DxfCode.ExtendedDataReal, p.Y));
            }
            using (var rb = new ResultBuffer(vals.ToArray())) pl.XData = rb;
        }

        /// <summary>Escucha los cambios de las ProfileView de este dibujo (una vez por dibujo).</summary>
        internal static void Activar(Document doc)
        {
            if (doc == null) return;
            var db = doc.Database;
            lock (_activas) { if (!_activas.Add(db)) return; }
            try
            {
                db.ObjectModified += (s, e) => Marcar(db, e.DBObject);
                db.ObjectErased += (s, e) => Marcar(db, e.DBObject);
                doc.CommandEnded += (s, e) => AlTerminar(doc, e.GlobalCommandName);
                doc.BeginDocumentClose += (s, e) => { lock (_activas) { _activas.Remove(db); _cambiadas.Remove(db); } };
            }
            catch { }
        }

        private static void Marcar(Database db, DBObject o)
        {
            try
            {
                if (!(o is CivilDB.ProfileView)) return;
                lock (_activas)
                {
                    if (!_cambiadas.TryGetValue(db, out var hs)) _cambiadas[db] = hs = new HashSet<Handle>();
                    hs.Add(o.Handle);
                }
            }
            catch { }
        }

        private static void AlTerminar(Document doc, string comando)
        {
            HashSet<Handle> hs;
            lock (_activas)
            {
                if (!_cambiadas.TryGetValue(doc.Database, out hs) || hs.Count == 0) return;
                _cambiadas.Remove(doc.Database);
            }
            if (SIN_SEGUIR.Contains((comando ?? "").Trim('.', '_', '-'))) return;
            try { using (doc.LockDocument()) Reubicar(doc.Database, hs); } catch { }
        }

        /// <summary>Recoloca las polilíneas de válvula de las vistas <paramref name="vistas"/> (null = todas). Devuelve cuántas.</summary>
        internal static int Reubicar(Database db, HashSet<Handle> vistas)
        {
            int n = 0;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                foreach (ObjectId id in ms)
                {
                    if (!id.ObjectClass.IsDerivedFrom(RXObject.GetClass(typeof(Polyline)))) continue;
                    try
                    {
                        var pl = (Polyline)tr.GetObject(id, OpenMode.ForRead);
                        var rb = pl.GetXDataForApplication(APP);
                        if (rb == null) continue;
                        var v = rb.AsArray();
                        rb.Dispose();
                        if (v.Length < 3) continue;
                        var h = new Handle(Convert.ToInt64((string)v[1].Value, 16));
                        if (vistas != null && !vistas.Contains(h)) continue;
                        double ve = (double)v[2].Value;
                        ObjectId pvId = ObjectId.Null;
                        try { pvId = db.GetObjectId(false, h, 0); } catch { }
                        pl.UpgradeOpen();
                        if (pvId.IsNull || pvId.IsErased) { pl.Erase(); n++; continue; }
                        var pv = (CivilDB.ProfileView)tr.GetObject(pvId, OpenMode.ForRead);
                        int k = 0;
                        for (int i = 3; i + 1 < v.Length && k < pl.NumberOfVertices; i += 2, k++)
                        {
                            PerfilVista.FindXY(pv, ve, (double)v[i].Value, (double)v[i + 1].Value, out double x, out double y);
                            pl.SetPointAt(k, new Point2d(x, y));
                        }
                        n++;
                    }
                    catch { }
                }
                tr.Commit();
            }
            return n;
        }

    }

    public class ComandosPerfilValvulas
    {
        [CommandMethod("PDFCAD_PERFIL_VALVULAS")]
        public void RecolocarTodas()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            PerfilValvulasSeguir.Activar(doc);
            int n = PerfilValvulasSeguir.Reubicar(doc.Database, null);
            doc.Editor.WriteMessage($"\n✓ {n} trazo(s) de válvula recolocados en sus vistas de perfil.");
        }
    }
}
