using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Dominio;
using CivilDB = Autodesk.Civil.DatabaseServices;

// ============================================================================
//  ADAPTADOR de escritura (Dominio → Civil 3D). Cada cambio corre en contexto de
//  comando (un paso de deshacer). Solo los tipos de la lista cerrada de
//  Dominio.TiposCambio: nada de código libre en AutoCAD.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed class Civil3DEditor : IEditorDibujo
    {
        public void Aplicar(CambioPropuesto c) => HiloAutoCAD.Escribir(d =>
        {
            Database db = d.Database;
            ObjectId id = Ids.De(db, c.Handle);
            if (id.IsNull) throw new ErrorUsuario($"El elemento {c.Handle} ya no existe.");
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                var ent = (Entity)tr.GetObject(id, OpenMode.ForWrite);
                switch (c.Tipo)
                {
                    case TiposCambio.COTA_INICIO:
                    case TiposCambio.COTA_FIN:
                        if (!(ent is CivilDB.Pipe p)) throw new ErrorUsuario("El elemento no es una tubería de gravedad.");
                        double z = double.Parse(c.Despues, System.Globalization.CultureInfo.InvariantCulture)
                                   + Civil3DLector.RadioInterior(p);          // rasante → eje
                        if (c.Tipo == TiposCambio.COTA_INICIO) { Point3d s = p.StartPoint; p.StartPoint = new Point3d(s.X, s.Y, z); }
                        else { Point3d e = p.EndPoint; p.EndPoint = new Point3d(e.X, e.Y, z); }
                        break;
                    case TiposCambio.CAPA:
                        AsegurarCapa(db, tr, c.Despues);
                        ent.Layer = c.Despues;
                        break;
                    case TiposCambio.DESCRIPCION:
                        if (!(ent is CivilDB.Part parte)) throw new ErrorUsuario("El elemento no admite descripción.");
                        parte.Description = c.Despues;
                        break;
                    default:
                        throw new ErrorUsuario($"Tipo de cambio no soportado: {c.Tipo}.");
                }
                tr.Commit();
            }
            d.Editor.WriteMessage($"\n[IA] {c.Elemento}: {c.Tipo} {c.Antes} → {c.Despues}  (U para deshacer)");
        });

        public int IrA(IReadOnlyList<string> handles) => HiloAutoCAD.Leer(d =>
        {
            Database db = d.Database;
            var ids = handles.Select(h => Ids.De(db, h)).Where(i => !i.IsNull).ToList();
            if (ids.Count == 0) return 0;
            Extents3d? caja = null;
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                foreach (ObjectId id in ids)
                {
                    try
                    {
                        var ent = (Entity)tr.GetObject(id, OpenMode.ForRead);
                        Extents3d e = ent.GeometricExtents;
                        if (caja.HasValue) { var c = caja.Value; c.AddExtents(e); caja = c; } else caja = e;
                    }
                    catch { }
                }
                tr.Commit();
            }
            Editor ed = d.Editor;
            if (caja.HasValue)
            {
                Extents3d c = caja.Value;
                double w = Math.Max(c.MaxPoint.X - c.MinPoint.X, 1.0), h = Math.Max(c.MaxPoint.Y - c.MinPoint.Y, 1.0);
                using (ViewTableRecord v = ed.GetCurrentView())
                {
                    v.CenterPoint = new Point2d((c.MinPoint.X + c.MaxPoint.X) / 2.0, (c.MinPoint.Y + c.MaxPoint.Y) / 2.0);
                    v.Width = w * 1.6; v.Height = h * 1.6;
                    ed.SetCurrentView(v);
                }
            }
            try { ed.SetImpliedSelection(ids.ToArray()); } catch { }
            return ids.Count;
        });

        private static void AsegurarCapa(Database db, Transaction tr, string nombre)
        {
            var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (lt.Has(nombre)) return;
            lt.UpgradeOpen();
            var ltr = new LayerTableRecord { Name = nombre };
            lt.Add(ltr);
            tr.AddNewlyCreatedDBObject(ltr, true);
        }
    }
}
